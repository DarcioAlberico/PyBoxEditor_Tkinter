import json

import pytest

from core.ocr_result import (
    GlyphResult,
    LineResult,
    OCRHypothesis,
    OCRTrace,
    PageResult,
    RegionResult,
    WordResult,
)


def test_resultado_de_pagina_serializa_e_recarrega_hierarquia(tmp_path):
    pagina = PageResult(
        "p1", text="Casa azul", confidence=0.91,
        regions=[RegionResult("r1", "body", 0, 0.95, (0, 0, 100, 50), ["l1"])],
        words=[WordResult(
            "w1", "Casa", 0.9, (1, 2, 30, 20), "l1", "fused",
            glyph_ids=["g1"],
            alternatives=[OCRHypothesis("Cesa", 0.4, "paddleocr")],
        )],
        glyphs=[GlyphResult("g1", "C", 0.99, (1, 2, 8, 20), "neural")],
    )
    caminho = tmp_path / "page.json"
    pagina.save_json(caminho)
    recarregada = PageResult.load_json(caminho)
    assert recarregada.to_dict() == pagina.to_dict()
    assert recarregada.words[0].alternatives[0].source == "paddleocr"


def test_roundtrip_preserva_alternativas_de_linha(tmp_path):
    pagina = PageResult(
        "p2",
        lines=[LineResult(
            "l1", "texto", .8, bbox=(0, 0, 40, 10),
            alternatives=[OCRHypothesis("texto", .8, "line"),
                          OCRHypothesis("t0xto", .4, "glyph")],
        )],
    )
    caminho = tmp_path / "line.json"
    pagina.save_json(caminho)
    recarregada = PageResult.load_json(caminho)
    assert [item.text for item in recarregada.lines[0].alternatives] == [
        "texto", "t0xto"
    ]


def test_contratos_validam_confianca_e_bbox():
    with pytest.raises(ValueError):
        OCRHypothesis("A", 1.1, "neural")
    with pytest.raises(ValueError):
        GlyphResult("g", "A", 0.5, (1, 2, 3), "neural")


def test_trace_desligado_nao_cria_artefatos(tmp_path):
    trace = OCRTrace(tmp_path, enabled=False)
    trace.event("start", page="p1")
    assert trace.save_text("x.txt", "abc") is None
    assert trace.events == []
    assert not list(tmp_path.iterdir())


def test_trace_grava_eventos_e_json(tmp_path):
    trace = OCRTrace(tmp_path)
    trace.event("start", page="p1")
    trace.save_text("steps/result.txt", "Casa")
    caminho = trace.close()
    assert caminho is not None and caminho.exists()
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    assert [event["name"] for event in dados["events"]] == ["start", "artifact"]
