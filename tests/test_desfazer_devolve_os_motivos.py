"""Desfazer devolve o que havia, motivos inclusive (RG-07, R-11).

`undo` gravava `("undo",)` nos motivos da decisão: o bloco que só estava na fila por um
motivo de alto impacto (`low_confidence`, `fen_invalid`…) voltava a `automatic` sem ele, e
saía da fila para sempre — contra as invariantes 9 e 11 do `CONTEXT.md`. E
`edit(..., reason_codes=("undo",))` passava, e a pilha de desfazer o tomava por um undo.
"""

import pytest

from core.editorial_model import Decision, EditorialBlock, EditorialDocument, EditorialPage, SourceRef
from core.editorial_review import ReviewJournal, ReviewSession


def _documento():
    ref = SourceRef("doc", 0)
    blocos = [
        EditorialBlock(id="suspeito", kind="paragraph", order=0, source_refs=[ref],
                       decision=Decision("lido com dúvida", [], "automatic", ["legacy_adapter", "low_confidence"])),
        EditorialBlock(id="limpo", kind="paragraph", order=1, source_refs=[ref],
                       decision=Decision("bem lido", [], "automatic", ["legacy_adapter"])),
        EditorialBlock(id="outro", kind="diagram", order=2, source_refs=[ref],
                       decision=Decision({"fen": None}, [], "automatic", ["legacy_adapter", "fen_invalid"])),
    ]
    return EditorialDocument("doc", "Doc", "pt", [EditorialPage("p1", 0, [ref], blocos, [])])


def _item(sessao, alvo):
    return next((i for i in sessao.queue.items if i.target_id == alvo), None)


def test_aceitar_e_desfazer_devolve_o_item_a_fila_com_os_mesmos_motivos(tmp_path):
    sessao = ReviewSession(_documento(), journal=ReviewJournal(tmp_path / "d.review.jsonl"))
    antes = _item(sessao, "suspeito")
    assert antes is not None
    sessao.accept("suspeito")
    assert _item(sessao, "suspeito") is None
    sessao.undo()
    depois = _item(sessao, "suspeito")
    assert depois is not None, "o bloco desfeito saiu da fila para sempre"
    assert (depois.reason_codes, depois.motivos, depois.severity, depois.status) == \
        (antes.reason_codes, antes.motivos, antes.severity, antes.status)

    # E do diário, numa sessão nova, sai igual.
    reaberta = ReviewSession.from_journal(_documento(), ReviewJournal(tmp_path / "d.review.jsonl"))
    assert _item(reaberta, "suspeito").reason_codes == antes.reason_codes


def test_desfazer_um_lote_devolve_os_motivos_de_cada_bloco():
    sessao = ReviewSession(_documento())
    antes = {alvo: _item(sessao, alvo).reason_codes for alvo in ("suspeito", "outro")}
    sessao.apply_batch(["suspeito", "outro"], confirm=True)
    sessao.undo()
    assert {alvo: _item(sessao, alvo).reason_codes for alvo in ("suspeito", "outro")} == antes


def test_desfazer_duas_vezes_volta_dois_passos_com_os_motivos():
    sessao = ReviewSession(_documento())
    antes = _item(sessao, "suspeito").reason_codes
    sessao.edit("suspeito", "corrigido")
    sessao.accept("suspeito")
    sessao.undo()
    sessao.undo()
    assert _item(sessao, "suspeito").reason_codes == antes
    assert sessao.document.pages[0].blocks[0].decision.value == "lido com dúvida"


@pytest.mark.parametrize("codigos", [("undo",), ("human_correction", "batch:abc"), ("batch:x",)])
def test_undo_e_batch_sao_reservados(codigos):
    sessao = ReviewSession(_documento())
    with pytest.raises(ValueError):
        sessao.edit("limpo", "x", reason_codes=codigos)
    assert sessao.document.review_events == []
