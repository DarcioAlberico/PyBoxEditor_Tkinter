from __future__ import annotations

import numpy as np

from core.editorial_pipeline import DocumentSource, EditorialPipeline, ProcessOptions, SourcePage
from core.ocr_phase3 import (
    CallableRecognizer,
    ConfidenceCalibrator,
    FusionEngine,
    NotationParser,
    Phase3Processor,
    RecognitionContext,
    align_text,
)
from core.ocr_result import OCRHypothesis
from core.ocr_language import LanguageModel


def test_alignment_expoe_insercao_remocao_substituicao_e_ligadura():
    assert any(item.kind == "insert" for item in align_text("e4", "e 4").operations)
    assert any(item.kind == "delete" for item in align_text("e 4", "e4").operations)
    assert any(item.kind == "substitute"
               for item in align_text("Amaz1ng", "Amazing").operations)
    ligadura = align_text("ﬁle", "file")
    assert ligadura.distance == 0
    assert any(item.kind == "ligature" for item in ligadura.operations)


def test_fusao_calibra_por_dominio_e_preserva_original():
    modelo = LanguageModel.from_texts(["Amazing calculation"])
    engine = FusionEngine(
        ConfidenceCalibrator(temperature=1.0), language_model=modelo,
        minimum_margin=0.01,
    )
    resultado = engine.fuse([
        OCRHypothesis("Amaz1ng calculation", .70, "pdf_text"),
        OCRHypothesis("Amazing calculation", .78, "trained_line"),
    ], RecognitionContext("doc", 0, "r0", "l0", "prose"))

    assert resultado.chosen.text == "Amazing calculation"
    assert resultado.original_text == "Amaz1ng calculation"
    assert "original_preserved" in resultado.reason_codes
    assert resultado.chosen.metadata["original_text"] == "Amaz1ng calculation"


def test_fusao_de_notacao_conflictiva_vai_para_revisao_e_nao_corrige_silenciosamente():
    resultado = FusionEngine(minimum_margin=0.01).fuse([
        OCRHypothesis("1. e4", .60, "pdf_text"),
        OCRHypothesis("1. d4", .99, "trained_line"),
    ], RecognitionContext("doc", 0, "r0", "l0", "notation"))

    assert resultado.chosen.text == "1. e4"
    assert resultado.review_required is True
    assert "notation_conflict" in resultado.reason_codes


def test_parser_de_notacao_preserva_original_normaliza_figurinas_e_variantes():
    parsed = NotationParser().parse(
        "1. e4 e5 2. Nf3 (2... ♞c6) {comentário} $1 1-0"
    )

    assert parsed.original_text.startswith("1. e4")
    assert any(token.kind == "comment" for token in parsed.tokens)
    assert any(token.kind == "nag" for token in parsed.tokens)
    assert parsed.variants
    assert any(token.normalized == "Nc6" for token in parsed.variants[0].tokens)
    assert parsed.final_result == "1-0"


def test_phase3_processa_linha_e_entra_na_editorial_pipeline():
    def leitor(imagem, contexto):
        assert imagem.shape[0] > 0
        assert contexto.domain == "prose"
        return [OCRHypothesis("Amazing calculation", .95, "trained_line")]

    processor = Phase3Processor(
        line_recognizers=[CallableRecognizer("trained_line", leitor,
                                             capabilities={"line", "confidence"})],
        language_model=LanguageModel.from_texts(["Amazing calculation"]),
    )
    source = DocumentSource.from_pages([
        SourcePage(0, raster=np.zeros((80, 300), dtype=np.uint8),
                   text_layer="Amaz1ng calculation")
    ], source_id="phase3")

    document = EditorialPipeline(recognizer=processor).process(
        source, ProcessOptions(use_cache=False)
    )

    page = document.pages[0]
    page_result = page.observations["page_result"]
    assert page_result["metadata"]["phase3"] is True
    assert page_result["lines"][0]["text"] == "Amazing calculation"
    assert page_result["lines"][0]["metadata"]["original_text"] == "Amaz1ng calculation"
