"""Lote transacional, e a ponte do editor por lote (RG-07, R-12).

- `apply_batch` aplicava metade do lote e levantava no alvo inexistente: o diário ficava
  com a metade.
- A ponte do editor gravava um evento por bloco, sem lote: cada Ctrl+S eram N passos de
  desfazer; só percorria os blocos de topo, e o bloco com origem dentro de uma citação
  virava "apagado"; e o capítulo em modo código virava um `reject` de cada bloco dele no
  documento editorial, sem aviso.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.editor import importar_ir, modelo as m, xhtml  # noqa: E402
from core.editorial_model import Decision, EditorialBlock, EditorialDocument, EditorialPage, SourceRef  # noqa: E402
from core.editorial_review import Pedido, ReviewJournal, ReviewSession  # noqa: E402
from test_editor_importar_ir import _bloco_de, _livro_e_documento  # noqa: E402


def _documento():
    ref = SourceRef("doc", 0)
    blocos = [EditorialBlock(id=f"b{i}", kind="paragraph", order=i, source_refs=[ref],
                             decision=Decision(f"texto {i}", [], "automatic", ["legacy_adapter"]))
              for i in range(3)]
    return EditorialDocument("doc", "Doc", "pt", [EditorialPage("p1", 0, [ref], blocos, [])])


def test_o_lote_com_alvo_inexistente_nao_grava_nada(tmp_path):
    caminho = tmp_path / "d.review.jsonl"
    sessao = ReviewSession(_documento(), journal=ReviewJournal(caminho))
    with pytest.raises(KeyError):
        sessao.apply_batch(["b0", "nao-existe", "b1"], confirm=True)
    assert not caminho.exists() and sessao.document.review_events == []
    with pytest.raises(KeyError):
        sessao.aplicar_lote([Pedido("b0", "x"), Pedido("nao-existe", "y")])
    assert not caminho.exists() and sessao.document.review_events == []


def test_aplicar_lote_e_um_passo_de_desfazer_com_status_por_evento(tmp_path):
    sessao = ReviewSession(_documento(), journal=ReviewJournal(tmp_path / "d.review.jsonl"))
    sessao.aplicar_lote([Pedido("b0", "novo 0"), Pedido("b1", "texto 1", status="rejected",
                                                         reason_codes=("rejected",))])
    blocos = sessao.document.pages[0].blocks
    assert (blocos[0].decision.value, blocos[0].decision.status) == ("novo 0", "reviewed")
    assert blocos[1].decision.status == "rejected"
    assert sessao.passos_desfaziveis() == 1
    sessao.undo()
    assert [(b.decision.value, b.decision.status) for b in sessao.document.pages[0].blocks[:2]] == \
        [("texto 0", "automatic"), ("texto 1", "automatic")]
    with pytest.raises(ValueError):
        sessao.aplicar_lote([Pedido("b0", "x", reason_codes=("undo",))])


def test_desfazer_depois_de_um_salvamento_desfaz_o_salvamento_inteiro(tmp_path):
    livro, doc = _livro_e_documento(tmp_path)
    _bloco_de(livro, "block-doc-p0001-b0001").trechos = [m.Trecho(texto="Primeira mudança.")]
    _bloco_de(livro, "block-doc-p0003-b0001").trechos = [m.Trecho(texto="Segunda mudança.")]
    diario = importar_ir.caminho_do_diario(doc)
    ponte = importar_ir.gravar_eventos(livro, doc, diario)
    assert ponte.eventos == 2
    sessao = ReviewSession.from_journal(doc, ReviewJournal(diario))
    assert sessao.passos_desfaziveis() == 1, "cada bloco do Ctrl+S virou um passo de desfazer"
    sessao.undo()
    valores = {b.id: b.decision.value for p in sessao.document.pages for b in p.blocks}
    assert valores["block-doc-p0001-b0001"] == "Texto com negrito no meio."
    assert valores["block-doc-p0003-b0001"] == "Fim."


def test_o_capitulo_em_modo_codigo_nao_rejeita_nada_e_avisa(tmp_path):
    livro, doc = _livro_e_documento(tmp_path)
    cap = livro.capitulos[0]
    cap.texto_cru = xhtml.escrever(cap)
    cap.blocos = []                                     # aberto do disco em código: sem blocos
    ponte = importar_ir.gravar_eventos(livro, doc, importar_ir.caminho_do_diario(doc))
    assert ponte.apagados == 0, "o capítulo em modo código virou rejeição no documento editorial"
    assert any(cap.arquivo in a and "modo código" in a for a in ponte.avisos)


def test_o_bloco_aninhado_com_origem_propria_gera_evento(tmp_path):
    livro, doc = _livro_e_documento(tmp_path)
    par = _bloco_de(livro, "block-doc-p0003-b0001")
    cap = next(c for c in livro.capitulos if par in c.blocos)
    indice = cap.blocos.index(par)
    par.trechos = [m.Trecho(texto="Fim, dentro de uma citação.")]
    cap.blocos[indice] = m.Citacao(blocos=[par])
    [mudanca] = [mu for mu in importar_ir.eventos_de(livro, doc) if mu.bloco_id == "block-doc-p0003-b0001"]
    assert (mudanca.motivo, mudanca.after) == ("editado", "Fim, dentro de uma citação.")
