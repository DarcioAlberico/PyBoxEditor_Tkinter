import numpy as np

from core.box_model import BoxEntry
from core.ocr_ab import ABCase, comparar_modos
from core.ocr_context import ContextDecoder
from core.ocr_hybrid import HybridOCRPipeline
from core.ocr_language import LanguageModel
from core.ocr_result import OCRHypothesis, RegionResult


def test_comparar_modos_usa_as_mesmas_paginas_e_expoe_delta():
    cases = [ABCase("p1", {"text": "hello"}, input="x")]
    report = comparar_modos(cases, lambda _: {"text": "hallo"},
                            lambda _: {"text": "hello"})
    assert report.baseline.pages == report.candidate.pages == 1
    assert report.delta_cer < 0
    assert report.candidate_improved is True
    assert report.to_dict()["metadata"]["cases"] == 1


def test_contexto_corrige_apenas_palavra_proxima_e_preserva_original():
    model = LanguageModel.from_texts(["amazing calculation"], idioma="en")
    decoder = ContextDecoder(model)
    result = decoder.decode(OCRHypothesis("Amaz1ng calculation", .8, "line"))
    assert result.text == "Amazing calculation"
    assert result.metadata["original_text"] == "Amaz1ng calculation"
    assert result.source == "context"


def test_hibrido_usa_linha_na_prosa_e_glifo_na_notacao():
    image = np.full((30, 80), 255, dtype=np.uint8)
    boxes = [BoxEntry("a", 2, 5, 12, 20), BoxEntry("b", 15, 5, 25, 20)]
    def line(_image):
        return OCRHypothesis("ab prose", .91, "easyocr")

    def glyph(_image):
        return OCRHypothesis("X", .99, "neural")
    pipeline = HybridOCRPipeline(line, glyph)
    prose = RegionResult("r1", "body", 0, .9, (0, 0, 30, 30))
    notation = RegionResult("r2", "notation", 0, .9, (0, 0, 30, 30))
    assert pipeline.read_line(image, boxes, region=prose, line_id="l1").line.text == "ab prose"
    output = pipeline.read_line(image, boxes, region=notation, line_id="l2")
    assert output.line.text == "XX"
    assert output.decision.primary == "glyph"
    assert len(output.glyphs) == 2


def test_hibrido_registra_divergencia_da_linha_com_a_ancora():
    image = np.full((60, 100), 255, dtype=np.uint8)
    boxes = [BoxEntry("a", 10, 20, 25, 45)]
    pipeline = HybridOCRPipeline(
    lambda _image: OCRHypothesis("word", .9, "easyocr"),
        lambda _image: OCRHypothesis("X", .9, "neural"),
    )
    region = RegionResult("r", "body", 0, .9, (0, 0, 100, 60))
    output = pipeline.read_line(image, boxes, region=region, line_id="l")
    assert output.line.text == "word"
    assert "line_anchor_disagreement" in output.line.warnings
    assert output.line.alternatives[0].text == "X"
    assert output.line.metadata["alignment"]["distance"] == 4
    assert output.line.metadata["alignment"]["anchor_length"] == 1
    assert output.line.metadata["alignment"]["line_length"] == 4


def test_hibrido_agrega_pagina_na_ordem_das_regioes_e_serializa():
    image = np.full((40, 100), 255, dtype=np.uint8)
    boxes = [[BoxEntry("a", 2, 5, 12, 20)]]
    pipeline = HybridOCRPipeline(
        lambda _image: OCRHypothesis("linha", .9, "easyocr"),
        lambda _image: OCRHypothesis("A", .8, "neural"),
    )
    regiao_baixo = RegionResult("baixo", "body", 1, .5, (0, 20, 30, 40))
    regiao_cima = RegionResult("cima", "notation", 0, .5, (0, 0, 30, 20))

    pagina = pipeline.read_page(
        image,
        [(regiao_baixo, boxes), (regiao_cima, boxes)],
        page_id="p7",
    )

    assert pagina.page_id == "p7"
    assert [region.id for region in pagina.regions] == ["cima", "baixo"]
    assert pagina.text == "A\n\nlinha"
    assert len(pagina.lines) == len(pagina.glyphs) == 2
    assert pagina.regions[0].metadata["routing"]["primary"] == "glyph"
    assert pagina.to_dict()["metadata"]["region_count"] == 2


def test_hibrido_recusa_regiao_repetida():
    image = np.full((20, 40), 255, dtype=np.uint8)
    boxes = [[BoxEntry("a", 2, 2, 10, 12)]]
    pipeline = HybridOCRPipeline(lambda _: ("a", .9), lambda _: ("a", .9))
    regiao = RegionResult("r", "body", 0, .5, (0, 0, 20, 20))
    try:
        pipeline.read_page(image, [(regiao, boxes), (regiao, boxes)])
    except ValueError as erro:
        assert "repetida" in str(erro)
    else:
        raise AssertionError("região repetida deveria ser rejeitada")


def test_notacao_preserva_glifo_e_registra_linha_como_hipotese():
    image = np.full((30, 80), 255, dtype=np.uint8)
    boxes = [BoxEntry("a", 2, 5, 12, 20)]
    chamadas = []
    pipeline = HybridOCRPipeline(
        lambda faixa: (chamadas.append(faixa.shape) or ("e4", .88)),
        lambda _crop: ("♘", .97),
    )
    region = RegionResult("r", "notation", 0, .9, (0, 0, 30, 30))
    output = pipeline.read_line(image, boxes, region=region, line_id="l")

    assert output.line.text == "♘"
    assert output.line.metadata["line_fallback"] == "e4"
    assert output.line.alternatives[0].text == "e4"
    assert chamadas
