from __future__ import annotations

from core.editorial_adapters import (
    pagina_extraida_para_documento,
    page_result_para_documento,
)
from core.livro import Figura, PaginaExtraida, Paragrafo, Tabela
from core.ocr_result import PageResult, RegionResult


def test_page_result_vira_documento_sem_perder_regioes_e_metadados():
    pagina = PageResult(
        "p1", text="Capítulo\nTexto", metadata={
            "document_id": "book", "image_hash": "hash", "page_index": 3,
            "engine": "test",
        },
        regions=[
            RegionResult("r1", "heading", 0, 0.95, (0, 0, 100, 20), text="Capítulo"),
            RegionResult("r2", "body", 1, 0.80, (0, 25, 100, 80), text="Texto"),
        ],
    )

    documento = page_result_para_documento(pagina)

    assert documento.document_id == "book"
    assert documento.pages[0].page_index == 3
    assert [block.kind for block in documento.pages[0].blocks] == ["heading", "paragraph"]
    assert documento.pages[0].blocks[0].decision.value == "Capítulo"
    assert documento.pages[0].blocks[0].decision.evidence_ids
    assert documento.pages[0].observations["page_result"]["page_id"] == "p1"


def test_pagina_extraida_mapeia_paragrafo_figura_e_tabela():
    pagina = PaginaExtraida(
        numero=2,
        blocos=[
            Paragrafo("Capítulo", titulo=True, nivel=1),
            Figura(b"png", 10, 10, fen="8/8/8/8/8/8/8/K6k w - - 0 1"),
            Tabela([["A", "B"], ["1", "2"]]),
        ],
    )

    documento = pagina_extraida_para_documento(pagina, document_id="legacy")

    assert [block.kind for block in documento.pages[0].blocks] == [
        "heading", "diagram", "table"
    ]
    figura = documento.pages[0].blocks[1].decision.value
    assert figura["fen"].startswith("8/8")
    assert figura["png_base64"]
    assert documento.pages[0].blocks[2].decision.value["rows"] == [["A", "B"], ["1", "2"]]
    assert documento.validate() == []

