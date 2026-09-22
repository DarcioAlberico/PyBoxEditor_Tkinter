from __future__ import annotations

import json

import pytest

from core.editorial_model import (
    Decision,
    EditorialBlock,
    EditorialDocument,
    EditorialPage,
    Evidence,
    SourceRef,
)
from core.editorial_review import (
    ReviewJournal,
    ReviewSession,
    build_review_queue,
)


def _document() -> EditorialDocument:
    ref = SourceRef("book", 0, (10, 20, 300, 400), "image-hash", "raster")
    evidence = Evidence("ev-1", ref, observed_text="posição", confidence=.4)
    paragraph = EditorialBlock(
        "block-paragraph", "paragraph", 0, [ref],
        Decision("texto original", ["ev-1"], "automatic", ["low_confidence"]),
    )
    diagram = EditorialBlock(
        "block-diagram", "diagram", 1, [ref],
        Decision({"fen": "8/8/8/8/8/8/8/4K2k w - - 0 1"}, ["ev-1"],
                 "unresolved", ["orientation_missing"]),
        warnings=["orientação pendente"], metadata={"review_required": True},
    )
    page = EditorialPage("book-p0001", 0, [ref], [paragraph, diagram], [evidence])
    return EditorialDocument("book", "Livro", "pt", [page], pipeline_version="v4")


def test_fila_prioriza_diagrama_e_expoe_origem_alternativas_e_impacto():
    fila = build_review_queue(_document())

    assert [item.target_id for item in fila.items] == ["block-diagram", "block-paragraph"]
    assert fila.items[0].kind == "diagram"
    assert fila.items[0].page_index == 0
    assert fila.items[0].source_refs[0].bbox == (10, 20, 300, 400)
    assert fila.filter(kind="paragraph").items[0].target_id == "block-paragraph"


def test_session_edit_aplica_evento_persiste_e_undo_preserva_append_only(tmp_path):
    journal_path = tmp_path / "review.jsonl"
    session = ReviewSession(_document(), journal=ReviewJournal(journal_path), user="editor")
    atualizado = session.edit("block-diagram", {"fen": "8/8/8/8/8/8/4k3/4K3 w - - 0 1"})

    assert atualizado.pages[0].blocks[1].decision.status == "reviewed"
    assert len(atualizado.review_events) == 1
    assert journal_path.exists()
    assert json.loads(journal_path.read_text(encoding="utf-8").splitlines()[0])["target_id"] == "block-diagram"

    desfeito = session.undo()
    assert desfeito.pages[0].blocks[1].decision.value["fen"] == "8/8/8/8/8/8/8/4K2k w - - 0 1"
    assert len(desfeito.review_events) == 2
    assert desfeito.review_events[-1].reason_codes == ("undo",)


def test_aceitar_adiar_e_lote_exigem_decisao_explicita():
    session = ReviewSession(_document(), user="editor")
    session.accept("block-paragraph")
    assert session.document.pages[0].blocks[0].decision.status == "reviewed"

    session.defer("block-diagram")
    assert session.document.pages[0].blocks[1].decision.status == "unresolved"

    with pytest.raises(ValueError, match="confirmação"):
        session.apply_batch(["block-diagram"], status="reviewed")

    session.apply_batch(["block-diagram"], status="reviewed", confirm=True)
    assert session.document.pages[0].blocks[1].decision.status == "reviewed"


def test_journal_reabre_eventos_e_fila_reflete_o_estado_atual(tmp_path):
    caminho = tmp_path / "journal.jsonl"
    primeira = ReviewSession(_document(), journal=ReviewJournal(caminho), user="editor")
    primeira.accept("block-diagram")
    reaberta = ReviewSession.from_journal(_document(), ReviewJournal(caminho), user="outro")

    assert reaberta.document.pages[0].blocks[1].decision.status == "reviewed"
    assert build_review_queue(reaberta.document).filter(target_id="block-diagram").items == []
