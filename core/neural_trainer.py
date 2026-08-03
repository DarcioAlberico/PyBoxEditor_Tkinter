import os
import glob
import json
import random
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import cv2
import numpy as np
from core.neural_model import SimpleCNN, get_device
from core.learner import folder_to_char


# -------------------------------------------------------
# Data Augmentation Functions
# -------------------------------------------------------

def augment_rotate(img, max_angle=15):
    """Rotaciona a imagem aleatoriamente."""
    angle = random.uniform(-max_angle, max_angle)
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), borderValue=255)

def augment_shift(img, max_shift=3):
    """Translada (desloca) a imagem em X e Y."""
    dx = random.randint(-max_shift, max_shift)
    dy = random.randint(-max_shift, max_shift)
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), borderValue=255)

def augment_noise(img, intensity=15):
    """Adiciona ruido gaussiano."""
    noise = np.random.normal(0, intensity, img.shape).astype(np.float32)
    noisy = img.astype(np.float32) + noise
    return np.clip(noisy, 0, 255).astype(np.uint8)

def augment_scale(img, scale_range=(0.8, 1.2)):
    """Redimensiona e recorta/padda de volta para o tamanho original."""
    h, w = img.shape[:2]
    scale = random.uniform(*scale_range)
    new_w, new_h = int(w * scale), int(h * scale)
    if new_w < 1 or new_h < 1:
        return img
    resized = cv2.resize(img, (new_w, new_h))
    
    # Pad ou crop de volta para (w, h)
    canvas = np.full((h, w), 255, dtype=np.uint8)
    
    # Centro
    cx = (w - new_w) // 2
    cy = (h - new_h) // 2
    
    # Calcular regioes de copia
    src_x1 = max(0, -cx)
    src_y1 = max(0, -cy)
    src_x2 = min(new_w, w - cx)
    src_y2 = min(new_h, h - cy)
    
    dst_x1 = max(0, cx)
    dst_y1 = max(0, cy)
    dst_x2 = dst_x1 + (src_x2 - src_x1)
    dst_y2 = dst_y1 + (src_y2 - src_y1)
    
    if dst_x2 > dst_x1 and dst_y2 > dst_y1:
        canvas[dst_y1:dst_y2, dst_x1:dst_x2] = resized[src_y1:src_y2, src_x1:src_x2]
    
    return canvas

def augment_erode_dilate(img):
    """Aplica erosao ou dilatacao aleatoria (engrossa ou afina tracos)."""
    kernel = np.ones((2, 2), np.uint8)
    if random.random() > 0.5:
        return cv2.erode(img, kernel, iterations=1)
    else:
        return cv2.dilate(img, kernel, iterations=1)

def augment_brightness(img, delta_range=(-30, 30)):
    """Altera brilho aleatoriamente."""
    delta = random.randint(*delta_range)
    return np.clip(img.astype(np.int16) + delta, 0, 255).astype(np.uint8)

def apply_random_augmentation(img):
    """Aplica uma combinacao aleatoria de augmentacoes."""
    result = img.copy()
    
    # Cada augmentacao tem uma probabilidade de ser aplicada
    if random.random() > 0.3:
        result = augment_rotate(result)
    if random.random() > 0.4:
        result = augment_shift(result)
    if random.random() > 0.5:
        result = augment_noise(result)
    if random.random() > 0.5:
        result = augment_scale(result)
    if random.random() > 0.6:
        result = augment_erode_dilate(result)
    if random.random() > 0.5:
        result = augment_brightness(result)
    
    return result


# -------------------------------------------------------
# Dataset with Augmentation
# -------------------------------------------------------

class CharDataset(Dataset):
    def __init__(self, data_dir="training_data", augment=True, augment_factor=8):
        self.data = []
        self.labels = []
        self.label_map = {}  # char -> int
        self.idx_to_char = {}  # int -> char
        self.augment = augment
        self.augment_factor = augment_factor
        
        self.load_data(data_dir)
        
    def load_data(self, data_dir):
        if not os.path.exists(data_dir):
            return

        classes = sorted([d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))])
        
        for idx, char_name in enumerate(classes):
            # Decodificar nome da pasta para o caractere real
            real_char = folder_to_char(char_name)
            self.label_map[char_name] = idx
            self.idx_to_char[idx] = real_char
            
            folder_path = os.path.join(data_dir, char_name)
            for img_path in glob.glob(os.path.join(folder_path, "*.png")):
                try:
                    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                    if img is None:
                        continue
                    
                    img = cv2.resize(img, (32, 32))
                    
                    # Original sample
                    normalized = img.astype(np.float32) / 255.0
                    self.data.append(np.expand_dims(normalized, axis=0))
                    self.labels.append(idx)
                    
                    # Augmented samples
                    if self.augment:
                        for _ in range(self.augment_factor):
                            aug_img = apply_random_augmentation(img)
                            aug_img = cv2.resize(aug_img, (32, 32))
                            normalized_aug = aug_img.astype(np.float32) / 255.0
                            self.data.append(np.expand_dims(normalized_aug, axis=0))
                            self.labels.append(idx)

                except Exception as e:
                    print(f"Skipping {img_path}: {e}")
        
        if self.augment:
            print(f"Data Augmentation: {len(self.data)} amostras totais (x{self.augment_factor + 1})")
                    
    def __len__(self):
        return len(self.data)
    
    def __getitem__(self, idx):
        return torch.tensor(self.data[idx]), torch.tensor(self.labels[idx])


# -------------------------------------------------------
# Trainer with LR Scheduler
# -------------------------------------------------------

class NeuralTrainer:
    def __init__(self, data_dir="training_data", model_path="custom_model.pth", meta_path="model_meta.json"):
        self.data_dir = data_dir
        self.model_path = model_path
        self.meta_path = meta_path
        self.device = get_device()
        
    def train(self, epochs=20, callback=None, should_stop=None):
        """
        should_stop: callable sem argumentos consultado a cada época. Se devolver
        True, o treino para e o melhor modelo até ali fica salvo. Necessário para
        que a UI consiga cancelar (o treino chega a durar minutos).
        """
        dataset = CharDataset(self.data_dir, augment=True, augment_factor=8)
        if len(dataset) == 0:
            if callback: callback("Nenhum dado encontrado para treinamento.")
            return False
            
        dataloader = DataLoader(dataset, batch_size=64, shuffle=True)
        
        num_classes = len(dataset.label_map)
        model = SimpleCNN(num_classes).to(self.device)
        
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(model.parameters(), lr=0.001)
        
        # Learning Rate Scheduler: reduz o LR ao longo do treinamento
        scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=7, gamma=0.5)
        
        model.train()
        
        original_count = len(dataset) // (dataset.augment_factor + 1)
        if callback: callback(f"Treinando: {original_count} originais -> {len(dataset)} com augmentation ({num_classes} classes)")
        
        best_loss = float('inf')
        
        accuracy = 0.0
        for epoch in range(epochs):
            if should_stop is not None and should_stop():
                if callback:
                    callback(f"Treino interrompido na epoch {epoch+1}. "
                             "O melhor modelo até aqui está salvo.")
                return True

            running_loss = 0.0
            correct = 0
            total_samples = 0

            for inputs, labels in dataloader:
                inputs, labels = inputs.to(self.device), labels.to(self.device)
                
                optimizer.zero_grad()
                outputs = model(inputs)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()
                
                running_loss += loss.item()
                
                # Accuracy tracking
                _, predicted = torch.max(outputs, 1)
                correct += (predicted == labels).sum().item()
                total_samples += labels.size(0)
            
            scheduler.step()
            
            avg_loss = running_loss / len(dataloader)
            accuracy = 100.0 * correct / total_samples
            lr = optimizer.param_groups[0]['lr']
            
            if avg_loss < best_loss:
                best_loss = avg_loss
                # Save Best Model immediately
                torch.save(model.state_dict(), self.model_path)
                
                # Save Metadata
                meta = {
                    "label_map": dataset.label_map,
                    "idx_to_char": dataset.idx_to_char,
                    "num_classes": num_classes
                }
                with open(self.meta_path, "w") as f:
                    json.dump(meta, f)
            
            if callback: callback(f"Epoch {epoch+1}/{epochs} - Loss: {avg_loss:.4f} - Acc: {accuracy:.1f}% - LR: {lr:.6f}")
            
        if callback: callback(f"Treinamento concluido! Acc final: {accuracy:.1f}% | Modelo salvo.")
        return True

class NeuralPredictor:
    def __init__(self, model_path="custom_model.pth", meta_path="model_meta.json"):
        self.model_path = model_path
        self.meta_path = meta_path
        self.model = None
        self.idx_to_char = {}
        self.device = get_device()
        self.loaded = False
        
    def load(self):
        if not os.path.exists(self.model_path) or not os.path.exists(self.meta_path):
            return False
            
        try:
            with open(self.meta_path, "r") as f:
                meta = json.load(f)
            
            self.idx_to_char = {int(k): v for k, v in meta["idx_to_char"].items()}
            num_classes = meta["num_classes"]
            
            self.model = SimpleCNN(num_classes).to(self.device)
            self.model.load_state_dict(torch.load(self.model_path, map_location=self.device))
            self.model.eval()
            self.loaded = True
            return True
        except Exception as e:
            print(f"Erro ao carregar modelo: {e}")
            return False
            
    def predict(self, img_np):
        if not self.loaded:
            return "?", 0.0
            
        # Preprocess
        if len(img_np.shape) == 3:
            img_gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        else:
            img_gray = img_np
            
        img = cv2.resize(img_gray, (32, 32))
        img = img.astype(np.float32) / 255.0
        img = np.expand_dims(img, axis=0) # (1, 32, 32)
        img = np.expand_dims(img, axis=0) # (1, 1, 32, 32)
        
        tensor = torch.tensor(img).to(self.device)
        
        with torch.no_grad():
            outputs = self.model(tensor)
            probs = F.softmax(outputs, dim=1)
            
            conf, predicted = torch.max(probs, 1)
            
            idx = predicted.item()
            confidence = conf.item()
            
            char = self.idx_to_char.get(idx, "?")
            
            return char, confidence
