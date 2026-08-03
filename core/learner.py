import os
import cv2
import numpy as np
import uuid
import glob
from typing import Tuple, List, Optional


def char_to_folder(char: str) -> str:
    """
    Converte um caractere em um nome de pasta seguro para Windows,
    diferenciando maiusculas de minusculas.
    Mantem apenas alfanumericos ASCII puros como legiveis.
    Todo o resto vira 'sym_{ord}'.
    Ligaduras (len > 1) viram 'ligature_{char}'.
    """
    if not char:
        return "unknown"

    # Ligaduras (ex: 'fi', 'ffi')
    if len(char) > 1:
        # Se contiver apenas letras, usa o nome da ligadura direto
        if char.isalpha() and char.isascii():
             return f"ligature_{char}"
        else:
             # Se tiver simbolos estranhos, codifica tudo em hex para garantir
             hex_str = "".join([f"{ord(c):x}" for c in char])
             return f"ligature_hex_{hex_str}"

    # Apenas A-Z, a-z e 0-9 sao mantidos "legíveis"
    if 'A' <= char <= 'Z':
        return f"upper_{char}"
    elif 'a' <= char <= 'z':
        return f"lower_{char}"
    elif '0' <= char <= '9':
        return f"digit_{char}"
    else:
        # Qualquer outro (acentos, simbolos, pontuacao, espaco) vira codigo ASCII
        return f"sym_{ord(char)}"


def folder_to_char(folder_name: str) -> str:
    """
    Converte um nome de pasta de volta para o caractere original.
    Ex: 'upper_A' -> 'A', 'lower_a' -> 'a', 'digit_1' -> '1', 'sym_46' -> '.'
    """
    if folder_name.startswith("ligature_hex_"):
        try:
            hex_str = folder_name[13:]
            # decodificar de 2 em 2 ou assumir unicode variable length?
            # Melhor simplificar: se usou hex, eh pq era estranho.
            # Mas espera, ord(c):x pode ter tamanho variavel.
            # Vamos assumir que ligaduras sao chars ASCII por enquanto para simplificar
            # Se cair no hex, a volta pode ser complicada se nao tiver delimitador.
            # Como fallback, retorne o proprio nome se der ruim.
            return "?" # TODO: Implementar decodificacao robusta se necessario
        except:
            return "?"
            
    if folder_name.startswith("ligature_"):
        return folder_name[9:]

    if folder_name.startswith("upper_"):
        return folder_name[6:]
    elif folder_name.startswith("lower_"):
        return folder_name[6:]
    elif folder_name.startswith("digit_"):
        return folder_name[6:]
    elif folder_name.startswith("sym_"):
        try:
            return chr(int(folder_name[4:]))
        except:
            return "?"
    elif folder_name.startswith("ASCII_"):
        # Compatibilidade com formato antigo
        try:
            return chr(int(folder_name[6:]))
        except:
            return "?"
    else:
        # Formato antigo (pasta = caractere diretamente)
        # Manter compatibilidade
        return folder_name


class CharacterLearner:
    def __init__(self, data_dir="training_data"):
        self.data_dir = data_dir
        self.reference_images = []  # List of (char, image_array)
        self.ensure_dir()
        self.load_references()

    def ensure_dir(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def load_references(self):
        """Loads all reference images into memory."""
        self.reference_images = []
        if not os.path.exists(self.data_dir):
            return

        for char_folder in os.listdir(self.data_dir):
            folder_path = os.path.join(self.data_dir, char_folder)
            if not os.path.isdir(folder_path):
                continue
            
            # Decodificar nome da pasta para o caractere real
            char = folder_to_char(char_folder)

            for img_file in glob.glob(os.path.join(folder_path, "*.png")):
                try:
                    img = cv2.imread(img_file, cv2.IMREAD_GRAYSCALE)
                    if img is not None:
                        img = cv2.resize(img, (32, 32))
                        self.reference_images.append((char, img))
                except Exception as e:
                    print(f"Error loading {img_file}: {e}")
        
        print(f"Loaded {len(self.reference_images)} reference samples.")

    def learn(self, crop_np: np.ndarray, char: str):
        """Saves a new reference sample."""
        if not char or len(char) != 1:
            return

        # Usar codificacao segura para o nome da pasta
        safe_folder = char_to_folder(char)
        
        save_dir = os.path.join(self.data_dir, safe_folder)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # Grayscale
        if len(crop_np.shape) == 3:
             img_gray = cv2.cvtColor(crop_np, cv2.COLOR_RGB2GRAY)
        else:
             img_gray = crop_np

        img_resized = cv2.resize(img_gray, (32, 32))

        filename = f"{uuid.uuid4()}.png"
        path = os.path.join(save_dir, filename)

        cv2.imwrite(path, img_resized)
        
        self.reference_images.append((char, img_resized))

    def predict(self, crop_np: np.ndarray, threshold=2000.0) -> Tuple[str, float]:
        """
        Finds the nearest neighbor.
        Returns (character, confidence). 
        """
        if not self.reference_images:
            return "?", 0.0

        if len(crop_np.shape) == 3:
             img_gray = cv2.cvtColor(crop_np, cv2.COLOR_RGB2GRAY)
        else:
             img_gray = crop_np

        target = cv2.resize(img_gray, (32, 32))
        
        best_dist = float('inf')
        best_char = "?"

        for char, ref_img in self.reference_images:
            dist = cv2.norm(target, ref_img, cv2.NORM_L2)
            if dist < best_dist:
                best_dist = dist
                best_char = char
        
        confidence = 0.0
        if best_dist < threshold:
             confidence = 1.0 - (best_dist / threshold)
             confidence = max(0.0, confidence)
        
        return best_char, confidence
