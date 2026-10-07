from __future__ import annotations

import numpy as np

from core.editorial_pipeline import DocumentSource, EditorialPipeline, ProcessOptions, SourcePage
from core.biblioteca.ocr_phase3 import (
    CallableRecognizer,
    ConfidenceCalibrator,
    FusionEngine,
    NotationParser,
    Phase3Processor,
    RegistryRecognizer,
    RecognitionContext,
    align_text,
)
from core.ocr_engines import EngineRun
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


def test_phase3_preserva_erros_dos_motores_no_resultado_editorial():
    class Registry:
        def recognize(self, image, *, level="line"):
            return EngineRun(
                hypotheses=[OCRHypothesis("texto confiavel", .91, "tesseract")],
                errors={"paddleocr": "RuntimeError: modelo ausente"},
            )

    processor = Phase3Processor(line_recognizers=[RegistryRecognizer(Registry())])
    source = DocumentSource.from_pages([
        SourcePage(0, raster=np.zeros((80, 300), dtype=np.uint8)),
    ], source_id="phase3-errors")

    document = EditorialPipeline(recognizer=processor).process(
        source, ProcessOptions(use_cache=False)
    )

    page_result = document.pages[0].observations["page_result"]
    assert page_result["metadata"]["engine_errors"] == {
        "engine_registry.paddleocr": "RuntimeError: modelo ausente"
    }
    assert any("paddleocr" in warning for warning in page_result["warnings"])
    assert any("paddleocr" in warning
               for warning in page_result["lines"][0]["warnings"])


def test_fusao_promove_erro_de_engine_para_revisao():
    contexto = RecognitionContext("doc", 0, "reg", "linha", "prose")
    resultado = FusionEngine().fuse([
        OCRHypothesis("texto confiavel", .91, "tesseract",
                       metadata={"engine_errors": {"easyocr": "offline"}}),
    ], contexto)

    assert resultado.review_required is True
    assert "engine_unavailable" in resultado.reason_codes
    assert "engine_unavailable_requires_review" in resultado.warnings


def test_phase3_preserva_todas_as_hipoteses_da_fusao():
    def leitor(imagem, contexto):
        return [OCRHypothesis(
            "leitura do motor", .81, "easyocr", model_version="easy/v2",
            metadata={"line_mode": "full_line"},
        )]

    processor = Phase3Processor(
        line_recognizers=[CallableRecognizer("easyocr", leitor)],
    )
    source = DocumentSource.from_pages([
        SourcePage(0, raster=np.zeros((80, 300), dtype=np.uint8),
                   text_layer="leitura original"),
    ], source_id="phase3-evidence")

    document = EditorialPipeline(recognizer=processor).process(
        source, ProcessOptions(use_cache=False)
    )

    fusion = document.pages[0].observations["page_result"]["lines"][0]["metadata"]["fusion"]
    assert {item["source"] for item in fusion["hypotheses"]} == {
        "pdf_text", "easyocr"
    }
    easy = next(item for item in fusion["hypotheses"] if item["source"] == "easyocr")
    assert easy["model_version"] == "easy/v2"
    assert easy["metadata"]["line_mode"] == "full_line"


def test_phase3_registra_rota_semantica_da_linha():
    processor = Phase3Processor()
    source = DocumentSource.from_pages([
        SourcePage(0, text_layer="1. e4 e5"),
    ], source_id="phase3-routing")

    document = EditorialPipeline(recognizer=processor).process(
        source, ProcessOptions(use_cache=False)
    )

    routing = document.pages[0].observations["page_result"]["metadata"]["routing"]
    assert routing[0]["domain"] == "notation"
    assert routing[0]["primary"] == "glyph"
    assert document.pages[0].observations["page_result"]["lines"][0]["metadata"]["routing"] == routing[0]


def test_registry_aplica_nivel_do_roteamento_ao_motor():
    niveis = []

    class Registry:
        def recognize(self, image, *, level="line"):
            niveis.append(level)
            return EngineRun([OCRHypothesis("1. e4", .9, "engine")])

    processor = Phase3Processor(line_recognizers=[RegistryRecognizer(Registry())])
    source = DocumentSource.from_pages([
        SourcePage(0, text_layer="1. e4 e5"),
    ], source_id="phase3-routing-level")

    EditorialPipeline(recognizer=processor).process(
        source, ProcessOptions(use_cache=False)
    )

    assert niveis == ["glyph"]


def test_registry_consulta_fallback_quando_o_nivel_primario_nao_tem_texto():
    niveis = []

    class Registry:
        def recognize(self, image, *, level="line"):
            niveis.append(level)
            if level == "glyph":
                return EngineRun(errors={"glyph_engine": "sem leitura"})
            return EngineRun([OCRHypothesis("leitura de linha", .88, "tesseract")])

    reconhecedor = RegistryRecognizer(Registry())
    contexto = RecognitionContext(
        "doc", 0, "reg", "linha", "notation",
        metadata={"routing": {"primary": "glyph", "fallback": "line"}},
    )

    hipoteses = reconhecedor.recognize(np.zeros((4, 20), dtype=np.uint8), contexto)

    assert niveis == ["glyph", "line"]
    assert [item.text for item in hipoteses] == ["leitura de linha"]
    assert hipoteses[0].metadata["routing_fallback"] is True
    assert hipoteses[0].metadata["ocr_level"] == "line"
    assert reconhecedor.errors == {"glyph_engine": "sem leitura"}


def test_fallback_de_rota_chega_ao_ir_com_erro_evidenciado():
    class Registry:
        def recognize(self, image, *, level="line"):
            if level == "glyph":
                return EngineRun(errors={"glyph_engine": "sem leitura"})
            return EngineRun([OCRHypothesis("1. e4 e5", .88, "tesseract")])

    processor = Phase3Processor(line_recognizers=[RegistryRecognizer(Registry())])
    source = DocumentSource.from_pages([
        SourcePage(0, raster=np.zeros((80, 300), dtype=np.uint8),
                   text_layer="1. e4 e5"),
    ], source_id="phase3-fallback-ir")

    document = EditorialPipeline(recognizer=processor).process(
        source, ProcessOptions(use_cache=False)
    )

    page_result = document.pages[0].observations["page_result"]
    fusion = page_result["lines"][0]["metadata"]["fusion"]
    fallback = next(item for item in fusion["hypotheses"]
                    if item["source"] == "tesseract")
    assert fallback["metadata"]["routing_fallback"] is True
    assert fallback["metadata"]["ocr_level"] == "line"
    assert page_result["metadata"]["engine_errors"] == {
        "engine_registry.glyph_engine": "sem leitura"
    }
    assert page_result["lines"][0]["metadata"]["review_required"] is True


def test_fusionador_preserva_conflito_do_ensemble_para_revisao():
    from core.biblioteca.ocr_phase3 import FusionEngine, RecognitionContext

    contexto = RecognitionContext("doc", 0, "reg", "linha", "prose")
    hipoteses = [
        OCRHypothesis("um", .99, "tesseract",
                      metadata={"ensemble_review_required": True}),
        OCRHypothesis("dois", .50, "easyocr",
                      metadata={"ensemble_review_required": True}),
    ]

    resultado = FusionEngine().fuse(hipoteses, contexto)

    assert resultado.review_required is True
    assert "ensemble_conflict" in resultado.reason_codes
    assert "ensemble_conflict_requires_review" in resultado.warnings
