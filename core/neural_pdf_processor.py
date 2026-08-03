import os
import cv2
import numpy as np
import pdf2image
from PIL import Image, ImageDraw, ImageFont

from core.neural_trainer import NeuralPredictor

# Dicionário de peças que queremos detectar e garantir que são desenhadas
# O modelo Neural *precisa* ter sido treinado para prever essas chaves.
CHESS_PIECES = {"♔", "♕", "♖", "♗", "♘", "♙", "♚", "♛", "♜", "♝", "♞", "♟"}

def generate_boxes_opencv(img_np):
    """
    Retorna bounding boxes básicos dos caracteres encontrados na imagem.
    """
    _, th = cv2.threshold(img_np, 180, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w < 3 or h < 3: # Filtro de ruído
            continue
        boxes.append({"x1": x, "y1": y, "x2": x + w, "y2": y + h})
    return boxes

def get_unicode_font(size):
    """
    Tenta carregar uma fonte do sistema que suporte caracteres Unicode de xadrez.
    """
    fonts_to_try = ["seguisym.ttf", "seguiemj.ttf", "segoeui.ttf", "arial.ttf", "dejavusans.ttf", "FreeSerif.ttf"]
    for f in fonts_to_try:
        try:
            return ImageFont.truetype(f, size)
        except IOError:
            continue
    return ImageFont.load_default()

def process_scanned_pdf(input_pdf: str, output_pdf: str, model_path: str = "custom_model.pth", meta_path: str = "model_meta.json", progress_callback=None) -> tuple:
    """
    Processa um PDF escaneado iterando sobre boxes do OpenCV, rodando inferência 
    na rede neural e desenhando símbolos de xadrez sobre as detecções.
    
    Returns:
        tuple: (total_pages, replaced_count)
    """
    if not os.path.exists(input_pdf):
        raise FileNotFoundError(f"Arquivo não encontrado: {input_pdf}")

    predictor = NeuralPredictor(model_path, meta_path)
    if not predictor.load():
        raise Exception("Falha ao carregar modelo neural (custom_model.pth) ou metadata (model_meta.json).")
        
    try:
        # Tenta carregar PDF como imagens (requer o pacote poppler nativo do sistema)
        with open(input_pdf, "rb") as f:
            pdf_bytes = f.read()
            pages = pdf2image.convert_from_bytes(pdf_bytes)
    except Exception as e:
        raise Exception(f"Erro ao converter PDF em imagens. Verifique se o Poppler está instalado:\n{e}")

    total_pages = len(pages)
    replaced_count = 0
    final_pages = []

    for i, page_img in enumerate(pages):
        if progress_callback:
            progress_callback(i, total_pages)
            
        img_gray = page_img.convert("L")
        img_np = np.array(img_gray)
        
        # Cria uma cópia colorida (RGB) para que o PIL permita desenhar símbolos nítidos
        img_color = page_img.convert("RGB")
        draw = ImageDraw.Draw(img_color)
        
        boxes = generate_boxes_opencv(img_np)
        
        for b in boxes:
            x1, y1, x2, y2 = b["x1"], b["y1"], b["x2"], b["y2"]
            crop_np = img_np[y1:y2, x1:x2]
            
            # Passa o cropzinho do OpenCV para a IA
            char, conf = predictor.predict(crop_np)
            
            # Se a IA diz que é K, Q, R, B, N, P com alta confiança, nós substituímos
            # TODO: O modelo pode confundir o texto "K" normal com o Cavalo/Rei dependendo 
            # de como foi treinado. O limiar (0.6) ajustável e o dicionário direcionam a ação.
            # A IA informará o que ela "olhou" na imagem cropada. 
            # A IA DEVE ter sido treinada para classificar a imagem da peça como o símbolo Unicode correto.
            if conf > 0.6 and char in CHESS_PIECES:
                # Apaga o glifo original desenhando uma caixa branca 
                # (Assumindo fundo branco do PDF)
                draw.rectangle([x1, y1, x2, y2], fill=(255, 255, 255))
                
                # Desenha o rei/peão translado em Unicode
                font_size = max(12, int((y2 - y1) * 1.1))  # Símbolos costumam precisar de font maior     
                font = get_unicode_font(font_size)
                
                # Centraliza em x/y
                draw.text((x1, int(y1 - font_size*0.1)), char, fill=(0, 0, 0), font=font)
                replaced_count += 1
                
        final_pages.append(img_color)

    if progress_callback:
        progress_callback(total_pages, total_pages) # Finalizado

    # Junta as imagens RGB num único PDF novamente e salva
    if final_pages:
        try:
            # save_all agrupa lista de imagens num PDF
            final_pages[0].save(
                output_pdf,
                save_all=True,
                append_images=final_pages[1:],
                resolution=200.0
            )
        except Exception as e:
            raise Exception(f"Erro ao salvar PDF final: {e}")

    return total_pages, replaced_count
