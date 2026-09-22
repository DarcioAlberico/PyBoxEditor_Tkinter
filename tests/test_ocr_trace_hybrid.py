import numpy as np

from core.box_model import BoxEntry
from core.ocr_hybrid import HybridOCRPipeline
from core.ocr_result import OCRTrace, RegionResult


def test_pipeline_registra_linha_e_pagina_no_trace():
    trace = OCRTrace(enabled=True)
    pipeline = HybridOCRPipeline(
        lambda _imagem: ("texto", 0.8),
        lambda _imagem: ("t", 0.9),
        trace=trace,
    )
    box = BoxEntry("t", 1, 1, 10, 12)
    region = RegionResult("r1", "prose", 0, 0.9, (1, 1, 10, 12))
    pagina = pipeline.read_page(np.zeros((20, 20), dtype=np.uint8),
                                [(region, [[box]])], page_id="p1")
    assert pagina.text == "texto"
    assert [evento["name"] for evento in trace.events] == [
        "line_result", "page_result"]
    assert trace.events[0]["confidence"] == 0.8
    assert trace.events[1]["page_id"] == "p1"
