import numpy as np

from core.ocr_engines import CallableAdapter, EngineRegistry
from core.ocr_fusion import decodificar_palavra, decodificar_sequencia, fundir
from core.ocr_result import OCRHypothesis


def h(text, conf, source):
    return OCRHypothesis(text, conf, source)


def test_callable_adapter_normaliza_tupla():
    adapter = CallableAdapter("fake", lambda image: ("texto", 0.8))
    resultado = adapter.recognize(np.zeros((2, 2), np.uint8), level="word")
    assert (resultado.text, resultado.confidence, resultado.source) == ("texto", 0.8, "fake")


def test_registry_isola_falha_de_engine():
    registry = EngineRegistry([
        CallableAdapter("ok", lambda image: ("A", 0.9)),
        CallableAdapter("falho", lambda image: (_ for _ in ()).throw(RuntimeError("offline"))),
    ])
    resultado = registry.recognize(np.zeros((2, 2), np.uint8), level="word")
    assert [item.text for item in resultado.hypotheses] == ["A"]
    assert "falho" in resultado.errors


def test_fundir_prefere_consenso_e_preserva_alternativas():
    resultado = fundir([h("Casa", 0.80, "easyocr"), h("Casa", 0.70, "paddleocr"),
                        h("Cesa", 0.95, "tesseract")])
    assert resultado.text == "Casa"
    assert resultado.source == "fused"
    assert "Cesa" in resultado.alternatives
    assert resultado.metadata["consensus"] == 2


def test_decodificar_palavra_respeita_dicionario_sem_forcar():
    resultado = decodificar_palavra([h("Cesa", 0.90, "line"),
                                    h("Casa", 0.76, "neural")], ["Casa"])
    assert resultado.text == "Casa"
    assert resultado.metadata["contextual_dictionary"] is True


def test_decodificar_sequencia_usa_beam_search():
    resultado = decodificar_sequencia([
        [h("C", 0.9, "neural"), h("G", 0.4, "neural")],
        [h("a", 0.8, "neural"), h("o", 0.5, "neural")],
        [h("s", 0.8, "neural"), h("z", 0.3, "neural")],
        [h("a", 0.8, "neural"), h("o", 0.4, "neural")],
    ], dicionario=["Casa"])
    assert resultado.text == "Casa"
    assert resultado.metadata["dictionary_match"] is True
