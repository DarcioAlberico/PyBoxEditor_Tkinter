from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from core.editorial_model import (
    Decision,
    EditorialBlock,
    EditorialDocument,
    EditorialPage,
    Evidence,
    ReviewEvent,
    SourceRef,
)


def _document() -> EditorialDocument:
    source = SourceRef("book", 0, (1, 2, 30, 40), "img-hash", "raster")
    evidence = Evidence("ev-1", source, observed_text="1. e4", confidence=0.8)
    block = EditorialBlock(
        id="block-1", kind="chess_sequence", order=0,
        source_refs=[source],
        decision=Decision("1. e4", ["ev-1"], "automatic", ["engine_consensus"]),
    )
    page = EditorialPage("book-p001", 0, [source], [block], [evidence])
    return EditorialDocument("book", "Livro", "en", [page],
                             pipeline_version="test", source_sha256="source")


def test_documento_valida_ids_origem_e_referencias():
    documento = _document()

    assert documento.validate() == []
    assert documento.to_dict()["schema"] == "pyboxeditor.editorial-document/v1"


def test_documento_rejeita_decisao_com_evidencia_inexistente():
    documento = _document()
    documento.pages[0].blocks[0].decision.evidence_ids = ["missing"]

    with pytest.raises(ValueError, match="evidência"):
        documento.validate()


def test_evento_de_revisao_e_imutavel_e_aplicacao_preserva_original():
    documento = _document()
    evento = ReviewEvent(
        event_id="event-1", document_id="book", page_id="book-p001",
        target_id="block-1", before="1. e4", after="1. e5",
        status="reviewed", reason_codes=("human_correction",),
        user="editor", created_at="2026-09-17T00:00:00+00:00",
    )

    atualizado = documento.apply_review(evento)

    assert atualizado is not documento
    assert atualizado.pages[0].blocks[0].decision.value == "1. e5"
    assert atualizado.pages[0].blocks[0].decision.original_value == "1. e4"
    assert documento.pages[0].blocks[0].decision.value == "1. e4"
    assert len(atualizado.review_events) == 1
    with pytest.raises(FrozenInstanceError):
        evento.after = "1. d4"  # type: ignore[misc]


def test_documento_roundtrip_json(tmp_path):
    documento = _document()
    caminho = tmp_path / "editorial.json"

    documento.save_json(caminho)
    carregado = EditorialDocument.load_json(caminho)

    assert carregado.to_dict() == documento.to_dict()
    assert json.loads(caminho.read_text(encoding="utf-8"))["pages"][0]["blocks"]


def test_evento_rejeita_alvo_ou_valor_anterior_incompatível():
    documento = _document()
    evento = ReviewEvent(
        "event-1", "book", "book-p001", "missing", "x", "y", "reviewed",
        ("human_correction",), "editor", "2026-09-17T00:00:00+00:00",
    )

    with pytest.raises(ValueError, match="alvo"):
        documento.apply_review(evento)
