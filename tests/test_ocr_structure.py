import cv2
import numpy as np
import pytest

from core.ocr_layout import analisar_layout
from core.ocr_result import OCRTrace
from core.ocr_structure import (
    StructureConfig,
    agrupar_glifos_em_linhas,
    agrupar_glifos_em_palavras,
    construir_estrutura,
)


def _box(char, x, y, width=8, height=16, confidence=0.9, ident=None):
    return {"id": ident or f"g-{char}-{x}-{y}", "char": char,
            "x1": x, "y1": y, "x2": x + width, "y2": y + height,
            "confidence": confidence}


def test_config_validacao():
    with pytest.raises(ValueError):
        StructureConfig(line_tolerance=0)
    with pytest.raises(ValueError):
        StructureConfig(paragraph_gap_factor=0)


def test_agrupar_linhas_ignora_box_vazio_e_ordena():
    boxes = [_box("b", 30, 42), _box("a", 10, 40), _box("c", 10, 80),
             _box("", 100, 100)]
    linhas = agrupar_glifos_em_linhas(boxes)
    assert [[item["char"] for item in linha] for linha in linhas] == [["a", "b"], ["c"]]


def test_agrupar_palavras_usa_vao_relativo():
    linha = [_box("A", 10, 20), _box("B", 20, 20), _box("C", 60, 20),
             _box("D", 70, 20)]
    palavras = agrupar_glifos_em_palavras(linha, "line-0000")
    assert [item.text for item in palavras] == ["AB", "CD"]
    assert all(item.line_id == "line-0000" for item in palavras)


def test_construir_estrutura_reconstroi_paragrafos():
    boxes = [
        _box("A", 10, 10), _box("B", 20, 10), _box("C", 60, 10),
        _box("D", 10, 32), _box("E", 20, 32),
        _box("F", 10, 82), _box("G", 20, 82),
    ]
    estrutura = construir_estrutura(boxes)
    assert [linha.text for linha in estrutura.lines] == ["AB C", "DE", "FG"]
    assert estrutura.paragraphs == ["AB C DE", "FG"]
    assert estrutura.text == "AB C DE\n\nFG"
    assert len(estrutura.words) == 4


def test_colunas_separam_paragrafos_mesmo_com_y_proximo():
    boxes = [_box("A", 10, 20), _box("B", 20, 20),
             _box("C", 300, 22), _box("D", 310, 22)]
    mascara = np.zeros((100, 400), np.uint8)
    cv2.rectangle(mascara, (10, 20), (35, 35), 255, -1)
    cv2.rectangle(mascara, (300, 22), (330, 37), 255, -1)
    layout = analisar_layout(mascara)
    estrutura = construir_estrutura(boxes, layout=layout)
    assert len(estrutura.paragraphs) == 2


def test_layout_expoe_grafo_de_ordem_de_leitura():
    mascara = np.zeros((100, 200), np.uint8)
    cv2.rectangle(mascara, (10, 10), (100, 20), 255, -1)
    cv2.rectangle(mascara, (10, 70), (100, 80), 255, -1)
    layout = analisar_layout(mascara)
    assert layout.reading_order
    assert layout.reading_graph[layout.reading_order[0]] == [layout.reading_order[1]]


def test_trace_registra_estrutura(tmp_path):
    trace = OCRTrace(tmp_path)
    construir_estrutura([_box("A", 1, 1)], trace=trace)
    trace.close()
    assert (tmp_path / "text_structure.json").exists()
    assert any(event["name"] == "text_structure" for event in trace.events)
