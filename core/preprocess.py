"""
Pré-processamento de imagem para detecção de caracteres.

Substitui o threshold fixo em 180 que estava replicado por três módulos. Um
valor fixo funciona numa página limpa e falha em scan com iluminação irregular
— o caso normal em livro digitalizado, onde a borda da página costuma ficar
mais escura que o miolo.

A binarização Otsu daqui veio de `core/opencv_autobox.py`, módulo que nunca foi
importado por ninguém e caiu na F5.1 (`git show 6a4b7a1:core/opencv_autobox.py`).
Ele já tinha a lógica melhor que a em uso.
"""

from typing import Tuple

import cv2
import numpy as np


METODOS = ("auto", "otsu", "adaptive", "fixed")


def _cinza(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    return img


# Fração de pixels de tinta que uma página de texto pode plausivelmente ter.
# Texto corrido fica em torno de 3–15%; acima de 35% não é texto, é mancha.
TINTA_PLAUSIVEL = (0.0005, 0.35)


def fracao_de_tinta(img_bin: np.ndarray) -> float:
    return float((img_bin > 0).mean())


def tinta_plausivel(img_bin: np.ndarray) -> bool:
    """
    O resultado da binarização parece texto?

    Este é o critério de escolha do modo "auto", e ele avalia o **resultado**,
    não o histograma. A primeira versão testava bimodalidade do histograma e
    errava justamente no caso que interessa: numa página com sombra de
    encadernação, o Otsu separa "metade escura" de "metade clara" — duas
    classes perfeitamente bimodais — e devolve 47% de tinta, o que não segmenta
    nada. Medido nesse cenário: limiar fixo 61%, Otsu 48%, adaptativo 3%.
    """
    return TINTA_PLAUSIVEL[0] <= fracao_de_tinta(img_bin) <= TINTA_PLAUSIVEL[1]


def binarize(img: np.ndarray, method: str = "auto",
             fixed_threshold: int = 180) -> np.ndarray:
    """
    Binariza deixando a tinta em branco (255) e o fundo em preto — o formato
    que `cv2.findContours` espera.

    auto     — Otsu se o histograma for bimodal, senão adaptativo
    otsu     — sempre Otsu
    adaptive — threshold adaptativo gaussiano (iluminação irregular)
    fixed    — limiar fixo (comportamento antigo, mantido para comparação)
    """
    if method not in METODOS:
        raise ValueError(f"método inválido: {method!r} (use um de {METODOS})")

    cinza = _cinza(img)

    if method == "auto":
        # Tenta o Otsu e confere se o que saiu parece texto. Se não parece,
        # cai no adaptativo, que lida com iluminação irregular.
        _, otsu = cv2.threshold(cinza, 0, 255,
                                cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        if tinta_plausivel(otsu):
            return otsu
        method = "adaptive"

    if method == "otsu":
        _, th = cv2.threshold(cinza, 0, 255,
                              cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return th

    if method == "adaptive":
        # Janela ímpar e proporcional à página: pequena demais recorta o miolo
        # dos glifos, grande demais volta a se comportar como limiar global.
        lado = max(15, (min(cinza.shape[:2]) // 20) | 1)
        return cv2.adaptiveThreshold(
            cinza, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, lado, 10)

    _, th = cv2.threshold(cinza, fixed_threshold, 255, cv2.THRESH_BINARY_INV)
    return th


def deskew(img: np.ndarray, max_angle: float = 15.0) -> Tuple[np.ndarray, float]:
    """
    Corrige inclinação da página. Devolve (imagem, ângulo aplicado em graus).

    Mede pelo retângulo de área mínima que envolve os pixels de tinta. Só
    corrige dentro de `max_angle`: acima disso a estimativa provavelmente pegou
    um diagrama ou a borda da página, e girar pioraria.
    """
    cinza = _cinza(img)
    tinta = binarize(cinza, "otsu")

    pontos = cv2.findNonZero(tinta)
    if pontos is None or len(pontos) < 50:
        return img, 0.0

    angulo = cv2.minAreaRect(pontos)[-1]
    if angulo < -45:
        angulo += 90
    elif angulo > 45:
        angulo -= 90

    if abs(angulo) < 0.1 or abs(angulo) > max_angle:
        return img, 0.0

    h, w = cinza.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angulo, 1.0)
    girada = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC,
                            borderMode=cv2.BORDER_REPLICATE)
    return girada, float(angulo)


def denoise(img_bin: np.ndarray, fracao_minima: float = 0.02) -> np.ndarray:
    """
    Remove partículas pequenas demais para serem caractere.

    O limiar é relativo à altura mediana dos componentes da própria página, não
    um número absoluto: o mesmo livro escaneado a 150 e a 300 dpi tem sujeira
    de tamanhos diferentes.
    """
    n, _, stats, _ = cv2.connectedComponentsWithStats(img_bin, connectivity=8)
    if n <= 2:
        return img_bin

    alturas = sorted(stats[1:, cv2.CC_STAT_HEIGHT])
    mediana = alturas[len(alturas) // 2] or 1
    area_minima = max(2.0, (mediana * fracao_minima) ** 2)

    saida = img_bin.copy()
    _, labels, stats, _ = cv2.connectedComponentsWithStats(img_bin, connectivity=8)
    for i in range(1, len(stats)):
        if stats[i, cv2.CC_STAT_AREA] < area_minima:
            saida[labels == i] = 0
    return saida


def normalize_dpi(img: np.ndarray, source_dpi: int,
                  target_dpi: int = 300) -> np.ndarray:
    """Reamostra para o DPI em que o modelo foi treinado."""
    if source_dpi <= 0 or source_dpi == target_dpi:
        return img
    escala = target_dpi / source_dpi
    interp = cv2.INTER_AREA if escala < 1 else cv2.INTER_CUBIC
    return cv2.resize(img, None, fx=escala, fy=escala, interpolation=interp)


def preparar_pagina(img: np.ndarray, method: str = "auto",
                    corrigir_inclinacao: bool = True,
                    limpar_ruido: bool = True) -> Tuple[np.ndarray, float]:
    """
    Pipeline completo. Devolve (imagem binária, ângulo corrigido).

    Ordem: deskew → binarize → denoise. O deskew vem antes porque gira a imagem
    em tons de cinza, onde a interpolação não cria degraus na tinta.
    """
    angulo = 0.0
    if corrigir_inclinacao:
        img, angulo = deskew(img)

    binaria = binarize(img, method)

    if limpar_ruido:
        binaria = denoise(binaria)

    return binaria, angulo
