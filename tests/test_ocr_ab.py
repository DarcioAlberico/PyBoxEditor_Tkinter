from core.ocr_ab import ABCase, comparar_modos


def test_comparar_modos_usa_as_mesmas_paginas_e_expoe_delta():
    cases = [ABCase("p1", {"text": "hello"}, input="x")]
    report = comparar_modos(cases, lambda _: {"text": "hallo"},
                            lambda _: {"text": "hello"})
    assert report.baseline.pages == report.candidate.pages == 1
    assert report.delta_cer < 0
    assert report.candidate_improved is True
    assert report.to_dict()["metadata"]["cases"] == 1
