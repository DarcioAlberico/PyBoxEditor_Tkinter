import cv2
import numpy as np
import pytest

from core.ocr_layout import LayoutAnalyzer, LayoutConfig, analisar_layout, detectar_colunas


def _duas_colunas():
    imagem = np.zeros((300, 500), np.uint8)
    for y in (50, 75, 100, 125, 205, 230):
        cv2.rectangle(imagem, (30, y), (205, y + 8), 255, -1)
        cv2.rectangle(imagem, (295, y), (470, y + 8), 255, -1)
    return imagem


def test_config_validacao():
    with pytest.raises(ValueError):
        LayoutConfig(min_line_width=0)
    with pytest.raises(ValueError):
        LayoutConfig(horizontal_kernel_fraction=0)


def test_layout_detecta_linhas_colunas_e_ordem():
    layout = analisar_layout(_duas_colunas())
    assert len(layout.lines) >= 6
    assert len(layout.columns) == 2
    assert len(layout.regions) >= 2
    assert layout.reading_order == [region.id for region in layout.regions]
    assert [region.metadata["column"] for region in layout.regions[:2]] == [0, 0]


def test_coluna_unica_nao_confunde_espacos():
    imagem = np.zeros((160, 500), np.uint8)
    for y in (40, 70, 100):
        cv2.rectangle(imagem, (30, y), (470, y + 8), 255, -1)
    layout = LayoutAnalyzer().analyze(imagem)
    assert len(layout.columns) == 1
    assert all(region.type == "body" for region in layout.regions)


def test_classifica_cabecalho_rodape_e_titulo():
    imagem = np.zeros((400, 500), np.uint8)
    cv2.rectangle(imagem, (100, 20), (400, 29), 255, -1)
    cv2.rectangle(imagem, (50, 160), (450, 168), 255, -1)
    cv2.rectangle(imagem, (50, 185), (450, 193), 255, -1)
    cv2.rectangle(imagem, (140, 350), (360, 359), 255, -1)
    layout = LayoutAnalyzer().analyze(imagem)
    tipos = {region.type for region in layout.regions}
    assert "header" in tipos
    assert "footer" in tipos


def test_pagina_vazia_produz_aviso():
    layout = analisar_layout(np.zeros((40, 60), np.uint8))
    assert layout.lines == []
    assert layout.warnings
    assert detectar_colunas([], 60) == []
