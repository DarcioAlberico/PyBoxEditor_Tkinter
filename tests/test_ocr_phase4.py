from __future__ import annotations

import numpy as np

from core.editorial_adapters import page_result_para_pagina
from core.editorial_pipeline import PageEvidence, ProcessOptions
from core.ocr_phase4 import (
    BoardCandidate,
    DiagramProcessor,
    Phase4Processor,
    SquareCandidate,
    SquareRecognizer,
    resolve_position,
    resolve_orientation,
    diagram_metrics,
)
from core.ocr_result import PageResult
from core.ocr_runtime import CancellationToken


def _candidates(symbol: str, confidence: float = 0.95):
    return (
        SquareCandidate(symbol, confidence, "test"),
        SquareCandidate(".", 1.0 - confidence, "test"),
    )


class FakeSquareRecognizer(SquareRecognizer):
    name = "fake-squares"

    def __init__(self, values):
        self.values = values

    def recognize(self, image, board, square, context):
        return self.values.get(square, _candidates("."))


def _board_candidate():
    return BoardCandidate(
        id="board-0", bbox=(10, 20, 170, 180), quad=((10, 20), (170, 20),
                                                        (170, 180), (10, 180)),
        confidence=0.96, source="test", orientation="branca",
    )


def _evidence():
    raster = np.zeros((220, 200), dtype=np.uint8)
    return PageEvidence(
        document_id="book", page_index=0, raster=raster, text_layer="Texto da página",
        raster_hash="hash", raster_dpi=300, source_kind="memory",
        text_blocks=[], metadata={},
    )


def test_resolve_position_usa_top_k_e_filtra_posicao_impossivel():
    values = {"e1": _candidates("K"), "e8": _candidates("k")}
    values["a8"] = (
        SquareCandidate("K", 0.92, "test"),
        SquareCandidate(".", 0.07, "test"),
    )
    resultado = resolve_position(values, orientation="branca", top_k=2)

    assert resultado.fen == "4k3/8/8/8/8/8/8/4K3 w - - 0 1"
    assert resultado.squares[0].square == "a8"
    assert resultado.squares[0].chosen == "."
    assert "legal_filter" in resultado.reason_codes
    assert resultado.review_required


def test_orientation_preserva_incerteza_quando_nao_ha_rotulos():
    assert resolve_orientation(None).value == "desconhecida"
    assert resolve_orientation({"colunas": "hgfedcba", "filas": "12345678"}).value == "preta"
    assert resolve_orientation({"colunas": "abcdefgh", "filas": "87654321"}).value == "branca"


def test_diagram_processor_produz_diagrama_com_anotacoes_e_estado_de_revisao():
    values = {"e1": _candidates("K"), "e8": _candidates("k")}
    processor = DiagramProcessor(
        detector=lambda image, **kwargs: [_board_candidate()],
        recognizer=FakeSquareRecognizer(values),
    )
    result = processor.process(_evidence(), ProcessOptions(use_cache=False), CancellationToken(),
                               annotations={"legend": "Exercise 1", "arrows": ["e2-e4"]})

    assert len(result) == 1
    diagram = result[0]
    assert diagram.fen.endswith(" w - - 0 1")
    assert diagram.annotations.legend == "Exercise 1"
    assert diagram.annotations.arrows == ("e2-e4",)
    assert diagram.review_status == "automatic"
    assert len(diagram.squares) == 64


def test_phase4_integra_diagramas_ao_pageresult_e_ao_documento_editorial():
    values = {"e1": _candidates("K"), "e8": _candidates("k")}
    diagram_processor = DiagramProcessor(
        detector=lambda image, **kwargs: [_board_candidate()],
        recognizer=FakeSquareRecognizer(values),
    )
    processor = Phase4Processor(
        text_processor=lambda evidence, options, token: PageResult(
            "page-0000", text="Texto", confidence=.9,
            metadata={"engine": "fake"},
        ),
        diagram_processor=diagram_processor,
    )

    page = processor.process(_evidence(), ProcessOptions(use_cache=False), CancellationToken())
    diagram_regions = [region for region in page.regions if region.type == "diagram"]
    assert len(diagram_regions) == 1
    assert diagram_regions[0].metadata["diagram"]["fen"].endswith(" w - - 0 1")

    editorial = page_result_para_pagina(page, document_id="book", page_index=0)
    block = next(item for item in editorial.blocks if item.kind == "diagram")
    assert isinstance(block.decision.value, dict)
    assert block.decision.value["fen"].endswith(" w - - 0 1")
    assert block.decision.status == "automatic"


def test_diagram_result_review_aplica_correcao_sem_apagar_original():
    values = {"e1": _candidates("K"), "e8": _candidates("k")}
    resultado = resolve_position(values, orientation="branca", top_k=2)
    revisado = resultado.review({"a1": "R"})

    assert next(item for item in revisado.squares if item.square == "a1").chosen == "R"
    assert revisado.original_fen == resultado.fen
    assert revisado.review_status == "reviewed"
    assert revisado.fen != resultado.fen


def test_modelo_ausente_vira_diagrama_unresolved_e_nao_falha_a_pagina():
    class BrokenRecognizer(SquareRecognizer):
        name = "broken"

        def recognize(self, image, board, square, context):
            raise RuntimeError("pesos ausentes")

    processor = DiagramProcessor(
        detector=lambda image, **kwargs: [_board_candidate()],
        recognizer=BrokenRecognizer(),
    )
    result = processor.process(_evidence(), ProcessOptions(use_cache=False), CancellationToken())

    assert result[0].review_status == "unresolved"
    assert "recognizer_unavailable" in result[0].reason_codes
    assert "pesos ausentes" in result[0].warnings[-1]


def test_metricas_separam_fen_casas_orientacao_e_legenda():
    values = {"e1": _candidates("K"), "e8": _candidates("k")}
    result = resolve_position(values, orientation="branca", top_k=2,
                              annotations={"legend": "Exercise 1"})
    metricas = diagram_metrics([result], [{
        "fen": result.fen, "orientation": "branca", "legend": "Exercise 1",
        "squares": {"e1": "K", "e8": "k"},
    }])

    assert metricas == {
        "fen_exact": 1.0, "square_accuracy": 1.0,
        "orientation_accuracy": 1.0, "legend_association": 1.0,
    }
