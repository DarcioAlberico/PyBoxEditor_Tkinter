import numpy as np

from core.ocr_engines import CallableAdapter, EngineRegistry


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


def test_consenso_preserva_erros_de_engines_indisponiveis_na_evidencia():
    from core.ocr_engines import EngineRun, EnsembleLineReader
    from core.ocr_result import OCRHypothesis

    class Registro:
        def recognize(self, image, *, level):
            return EngineRun(
                [OCRHypothesis("texto", .8, "tesseract")],
                errors={"easyocr": "RuntimeError: offline"},
            )

    leitor = EnsembleLineReader(Registro())
    registros = leitor(np.zeros((8, 20), np.uint8))

    assert registros == []
    assert leitor.last_result is not None
    assert dict(leitor.last_result.errors)["easyocr"] == "RuntimeError: offline"
    assert leitor.last_result.to_dict()["errors"]["easyocr"] == "RuntimeError: offline"


def test_consenso_preserva_hipoteses_e_exige_fontes_distintas():
    from core.ocr_engines import EngineRun
    from core.ocr_result import OCRHypothesis

    resultado = EngineRun([
        OCRHypothesis("texto certo", .72, "tesseract"),
        OCRHypothesis("texto certo", .68, "easyocr"),
        OCRHypothesis("texto errado", .99, "paddleocr"),
    ]).consolidate()

    assert resultado.chosen.text == "texto certo"
    assert resultado.consensus is True
    assert resultado.support == 2
    assert resultado.review_required is False
    assert len(resultado.hypotheses) == 3
    assert "texto errado" in resultado.alternatives


def test_consenso_em_conflito_nao_finge_decisao_segura():
    from core.ocr_engines import EngineRun
    from core.ocr_result import OCRHypothesis

    resultado = EngineRun([
        OCRHypothesis("um", .90, "tesseract"),
        OCRHypothesis("dois", .90, "easyocr"),
    ]).consolidate()

    assert resultado.consensus is False
    assert resultado.review_required is True
    assert "no_consensus" in resultado.reason_codes


def test_consenso_com_dois_grupos_de_mesmo_suporte_nao_escolhe_pela_confianca():
    from core.ocr_engines import EngineRun
    from core.ocr_result import OCRHypothesis

    resultado = EngineRun([
        OCRHypothesis("um", .99, "tesseract"),
        OCRHypothesis("um", .60, "easyocr"),
        OCRHypothesis("dois", .80, "paddleocr"),
        OCRHypothesis("dois", .70, "trained_line"),
    ]).consolidate()

    assert resultado.support == 2
    assert resultado.consensus is False
    assert resultado.review_required is True
    assert resultado.reason_codes == ("conflicting_consensus", "no_consensus")


def test_consenso_com_engine_indisponivel_exige_revisao_mesmo_com_duas_fontes():
    from core.ocr_engines import EngineRun
    from core.ocr_result import OCRHypothesis

    resultado = EngineRun(
        [
            OCRHypothesis("texto", .90, "tesseract"),
            OCRHypothesis("texto", .80, "easyocr"),
        ],
        errors={"paddleocr": "RuntimeError: offline"},
    ).consolidate()

    assert resultado.consensus is True
    assert resultado.review_required is True
    assert "engine_unavailable" in resultado.reason_codes
    assert dict(resultado.errors)["paddleocr"] == "RuntimeError: offline"


def test_adapter_da_fase3_entrega_a_leitura_de_consenso():
    from core.ocr_engines import EngineRun
    from core.biblioteca.ocr_phase3 import RecognitionContext, RegistryRecognizer
    from core.ocr_result import OCRHypothesis

    class Registro:
        def recognize(self, image, *, level):
            return EngineRun([
                OCRHypothesis("linha", .65, "tesseract"),
                OCRHypothesis("linha", .60, "easyocr"),
                OCRHypothesis("l1nha", .99, "paddleocr"),
            ])

    reconhecedor = RegistryRecognizer(Registro(), consensus=True)
    hipoteses = reconhecedor.recognize(
        np.zeros((2, 2), np.uint8),
        RecognitionContext("doc", 0, "reg", "linha", "prose"),
    )

    assert len(hipoteses) == 1
    assert hipoteses[0].text == "linha"
    assert hipoteses[0].source == "ensemble"
    assert hipoteses[0].metadata["sources"] == ["tesseract", "easyocr"]


def test_adapter_da_fase3_marca_conflito_para_revisao():
    from core.ocr_engines import EngineRun
    from core.biblioteca.ocr_phase3 import RecognitionContext, RegistryRecognizer
    from core.ocr_result import OCRHypothesis

    class Registro:
        def recognize(self, image, *, level):
            return EngineRun([
                OCRHypothesis("um", .99, "tesseract"),
                OCRHypothesis("dois", .50, "easyocr"),
            ])

    reconhecedor = RegistryRecognizer(Registro(), consensus=True)
    hipoteses = reconhecedor.recognize(
        np.zeros((2, 2), np.uint8),
        RecognitionContext("doc", 0, "reg", "linha", "prose"),
    )

    assert len(hipoteses) == 2
    assert all(item.metadata["ensemble_review_required"] for item in hipoteses)


def test_leitor_de_faixa_ensemble_so_devolve_consenso():
    from core.ocr_engines import EngineRun, EnsembleLineReader
    from core.ocr_result import OCRHypothesis

    class Registro:
        def __init__(self, hypotheses):
            self.hypotheses = hypotheses

        def recognize(self, image, *, level):
            return EngineRun(self.hypotheses)

    leitor = EnsembleLineReader(Registro([
        OCRHypothesis("linha", .6, "tesseract"),
        OCRHypothesis("linha", .7, "easyocr"),
    ]))
    registros = leitor(np.zeros((12, 40), np.uint8))

    assert registros[0][0] == "linha"
    assert registros[0][2] == (0, 0, 40, 12)
    assert registros[0][4]["consensus"] is True
