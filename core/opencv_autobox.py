from typing import List
from .box_model import BoxEntry


def generate_boxes_with_opencv(pil_image) -> List[BoxEntry]:
    """
    Gera boxes automaticamente usando OpenCV (estilo projeto antigo).
    Usa threshold + contornos. Pode ser refinado depois.
    """
    import cv2
    import numpy as np

    gray = pil_image.convert("L")
    img = np.array(gray)

    # binarização com OTSU (inverte para pegar letras escuras)
    _, th = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # encontrar contornos
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes: List[BoxEntry] = []
    H, W = img.shape[:2]

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)

        # filtros básicos: ignorar ruído pequeno e blocos gigantes
        if w < 5 or h < 5:
            continue
        if w > W * 0.6 or h > H * 0.6:
            continue

        boxes.append(BoxEntry("?", x, y, x + w, y + h))

    # ordenar de cima para baixo, esquerda para direita
    boxes.sort(key=lambda b: (b.y1, b.x1))
    return boxes
