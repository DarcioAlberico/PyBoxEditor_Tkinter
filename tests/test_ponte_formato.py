"""
A ponte transporta o formato (pedido registrado da ED-pré, feito em 2026-11-07).

Até aqui o `ReviewEvent` só levava o valor: o negrito e o itálico de um parágrafo
editado no editor de livros morriam na ponte (DEC-10, §10.7), e `aplicar_revisao`
zerava o negrito de todo parágrafo revisado. Agora o evento tem `metadata`, com a
chave `style` para `bold_spans`/`italic_spans` do texto novo; `apply_review` funde
no bloco e descarta as faixas do texto velho quando o texto muda; `undo` repõe o que
havia (`before_metadata`); a ponte do editor calcula as faixas dos trechos; e
`_bloco_revisado` lê as faixas do bloco em vez de zerá-las — o EPUB e o DOCX do
documento revisado saem com o negrito que o editor pôs.
"""

from __future__ import annotations

import json
import zipfile

from core import exportar, livro
from core.editor import importar_ir, modelo as m
from core.editorial_adapters import documento_para_paginas_extraidas, paginas_extraidas_para_documento
from core.editorial_legacy import aplicar_revisao
from core.editorial_model import EditorialBlock, EditorialDocument, ReviewEvent
from core.editorial_review import ReviewJournal, ReviewSession
from tests.test_editor_importar_ir import documento_sintetico

TEXTO = "Texto com negrito no meio."
BLOCO = "block-doc-p0001-b0001"


def _evento(documento: EditorialDocument, after, **campos) -> ReviewEvent:
    base = dict(event_id="e1", document_id=documento.document_id, page_id="doc-p0001", target_id=BLOCO,
                before=TEXTO, after=after, status="reviewed", reason_codes=("editor",), user="editor",
                created_at="2026-11-07T00:00:00+00:00")
    base.update(campos)
    return ReviewEvent(**base)


def _bloco(documento: EditorialDocument, bloco_id: str = BLOCO) -> EditorialBlock:
    return next(b for p in documento.pages for b in p.blocks if b.id == bloco_id)


# ----------------------------------------------------------------------
# O modelo: o evento leva metadata, e `apply_review` funde no bloco
# ----------------------------------------------------------------------

def test_o_evento_leva_metadata_e_volta_igual_do_json():
    evento = _evento(documento_sintetico(), "Outro texto.",
                     metadata={"style": {"bold_spans": [[0, 5]]}, "origem": "editor"},
                     before_metadata={"style": {"bold_spans": [[10, 17]], "italic_spans": None}})
    relido = ReviewEvent.from_dict(json.loads(json.dumps(evento.to_dict())))
    assert relido.metadata == {"style": {"bold_spans": [[0, 5]]}, "origem": "editor"}
    assert relido.before_metadata == {"style": {"bold_spans": [[10, 17]], "italic_spans": None}}
    # o evento gravado antes do canal existir lê sem o campo
    antigo = dict(evento.to_dict())
    del antigo["metadata"], antigo["before_metadata"]
    assert ReviewEvent.from_dict(antigo).metadata == {}


def test_apply_review_funde_o_estilo_no_bloco_e_o_resto_no_metadata():
    documento = documento_sintetico()
    novo = documento.apply_review(_evento(
        documento, "Texto com NEGRITO no meio e um fim.",
        metadata={"style": {"bold_spans": [[10, 17]], "italic_spans": [[27, 30]]}, "nota": "do editor"}))
    bloco = _bloco(novo)
    assert bloco.style["bold_spans"] == [[10, 17]] and bloco.style["italic_spans"] == [[27, 30]]
    assert bloco.metadata["nota"] == "do editor"
    assert _bloco(documento).style == {"bold_spans": [[10, 17]]}, "o documento de origem não muda"


def test_o_texto_novo_nao_herda_as_faixas_do_velho_e_o_aceite_as_mantem():
    documento = documento_sintetico()
    # a fila edita só o texto: as faixas do texto velho saem, em vez de marcar o que calhar na posição
    editado = documento.apply_review(_evento(documento, "Um texto bem diferente."))
    assert "bold_spans" not in _bloco(editado).style
    # aceitar sem mudar o valor mantém as faixas
    aceito = documento.apply_review(_evento(documento, TEXTO, reason_codes=("accepted",)))
    assert _bloco(aceito).style["bold_spans"] == [[10, 17]]
    # `None` tira a chave
    sem = documento.apply_review(_evento(documento, TEXTO, metadata={"style": {"bold_spans": None}}))
    assert "bold_spans" not in _bloco(sem).style


# ----------------------------------------------------------------------
# A sessão: `edit(metadata=)`, `before_metadata` e o `undo`
# ----------------------------------------------------------------------

def test_a_sessao_guarda_o_que_havia_e_o_undo_repoe(tmp_path):
    diario = ReviewJournal(tmp_path / "d.review.jsonl")
    sessao = ReviewSession(documento_sintetico(), journal=diario)
    sessao.edit(BLOCO, "Trecho com negrito no meio.", reason_codes=("editor",),
                metadata={"style": {"bold_spans": [[11, 18]], "italic_spans": []}})
    evento = sessao.document.review_events[-1]
    assert evento.metadata == {"style": {"bold_spans": [[11, 18]], "italic_spans": []}}
    assert evento.before_metadata == {"style": {"bold_spans": [[10, 17]], "italic_spans": None}}
    assert _bloco(sessao.document).style["bold_spans"] == [[11, 18]]

    sessao.undo()
    bloco = _bloco(sessao.document)
    assert bloco.decision.value == TEXTO and bloco.style.get("bold_spans") == [[10, 17]]
    assert "italic_spans" not in bloco.style
    # o diário relido repete os dois eventos com o metadata
    relida = ReviewSession.from_journal(documento_sintetico(), ReviewJournal(tmp_path / "d.review.jsonl"))
    assert [e.metadata.get("style", {}).get("bold_spans") for e in relida.document.review_events] == [
        [[11, 18]], [[10, 17]]]
    assert _bloco(relida.document).style["bold_spans"] == [[10, 17]]


def test_a_edicao_da_fila_sem_estilo_guarda_as_faixas_para_o_undo():
    sessao = ReviewSession(documento_sintetico())
    sessao.edit(BLOCO, "Reescrito à mão.")
    assert "bold_spans" not in _bloco(sessao.document).style
    assert sessao.document.review_events[-1].before_metadata == {"style": {"bold_spans": [[10, 17]],
                                                                          "italic_spans": None}}
    sessao.undo()
    assert _bloco(sessao.document).style["bold_spans"] == [[10, 17]]


# ----------------------------------------------------------------------
# A volta ao livro: as páginas do leitor e as de volta do IR
# ----------------------------------------------------------------------

def _pagina() -> livro.PaginaExtraida:
    return livro.PaginaExtraida(numero=0, blocos=[
        livro.Paragrafo("Texto com negrito no meio.", negrito=[(10, 17)]),
        livro.Paragrafo("Sem formato nenhum."),
    ], largura=800, altura=1000, dpi=200)


def test_aplicar_revisao_leva_o_negrito_do_evento_e_nao_zera_o_do_texto_igual():
    paginas = [_pagina()]
    documento = paginas_extraidas_para_documento(paginas, document_id="livro")
    sessao = ReviewSession(documento)
    # o editor trocou o texto e pôs o negrito noutra palavra
    sessao.edit("block-livro-p0001-b0000", "Texto com itálico e negrito no fim.",
                metadata={"style": {"bold_spans": [[20, 27]], "italic_spans": [[10, 17]]}})
    # a fila editou o segundo só no texto
    sessao.edit("block-livro-p0001-b0001", "Reescrito na fila.")
    [copia] = aplicar_revisao(paginas, sessao.document)
    assert copia.blocos[0].texto == "Texto com itálico e negrito no fim."
    assert copia.blocos[0].negrito == [(20, 27)] and copia.blocos[0].italico == [(10, 17)]
    assert copia.blocos[1].texto == "Reescrito na fila." and copia.blocos[1].negrito == []
    assert paginas[0].blocos[0].negrito == [(10, 17)], "a página do leitor não muda"
    # de volta do IR, sem as páginas do leitor, o mesmo
    [de_volta] = documento_para_paginas_extraidas(sessao.document)
    assert de_volta.blocos[0].negrito == [(20, 27)] and de_volta.blocos[0].italico == [(10, 17)]


def test_so_o_negrito_mudou_e_a_copia_muda_sem_tocar_no_texto():
    paginas = [_pagina()]
    documento = paginas_extraidas_para_documento(paginas, document_id="livro")
    sessao = ReviewSession(documento)
    sessao.edit("block-livro-p0001-b0000", TEXTO, metadata={"style": {"bold_spans": [[0, 5]], "italic_spans": []}})
    [copia] = aplicar_revisao(paginas, sessao.document)
    assert copia.blocos[0].texto == TEXTO and copia.blocos[0].negrito == [(0, 5)]
    assert copia.blocos[0] is not paginas[0].blocos[0]
    assert copia.blocos[1] is paginas[0].blocos[1], "o bloco não tocado é o mesmo objeto"


# ----------------------------------------------------------------------
# A ponte do editor: as faixas dos trechos viajam no evento
# ----------------------------------------------------------------------

def _livro_e_documento(tmp_path):
    documento = documento_sintetico()
    documento.metadata["review_journal_path"] = str(tmp_path / "saida.review.jsonl")
    livro_, _relatorio = importar_ir.de_documento(documento)
    return livro_, documento


def _paragrafo(livro_, bloco_id):
    return next(b for cap in livro_.capitulos for b in cap.blocos
                if b.origem is not None and b.origem.bloco_id == bloco_id)


def test_as_faixas_dos_trechos_viajam_no_evento_e_a_mudanca_so_de_formato_tambem(tmp_path):
    livro_, documento = _livro_e_documento(tmp_path)
    par = _paragrafo(livro_, BLOCO)
    assert [(t.texto, t.negrito) for t in par.trechos] == [("Texto com ", False), ("negrito", True),
                                                             (" no meio.", False)]
    # só o formato: o negrito vai para a primeira palavra
    par.trechos = [m.Trecho(texto="Texto", negrito=True), m.Trecho(texto=" com negrito no meio.")]
    [mudanca] = importar_ir.eventos_de(livro_, documento)
    assert mudanca.after == TEXTO and mudanca.metadata == {"style": {"bold_spans": [[0, 5]], "italic_spans": []}}
    ponte = importar_ir.gravar_eventos(livro_, documento, importar_ir.caminho_do_diario(documento))
    assert ponte.eventos == 1 and ponte.formatados == 1 and not ponte.avisos
    assert _bloco(ponte.documento).style["bold_spans"] == [[0, 5]]
    # texto e formato: dois trechos contíguos em negrito são uma faixa só, e o itálico vai junto
    par.trechos = [m.Trecho(texto="Tre", negrito=True), m.Trecho(texto="cho", negrito=True),
                   m.Trecho(texto=" com "), m.Trecho(texto="negrito", italico=True), m.Trecho(texto=" no meio.")]
    [mudanca] = importar_ir.eventos_de(livro_, ponte.documento)
    assert mudanca.after == "Trecho com negrito no meio."
    assert mudanca.metadata == {"style": {"bold_spans": [[0, 6]], "italic_spans": [[11, 18]]}}
    # o que o IR não guarda continua avisado
    par.trechos = [m.Trecho(texto="Trecho com negrito no meio.", sublinhado=True)]
    ponte2 = importar_ir.gravar_eventos(livro_, ponte.documento, importar_ir.caminho_do_diario(documento))
    assert ponte2.eventos == 1 and any("sublinhado" in a for a in ponte2.avisos)


def test_o_negrito_editado_chega_ao_epub_do_documento_revisado(tmp_path):
    paginas = [_pagina()]
    documento = paginas_extraidas_para_documento(paginas, document_id="livro", title="Livro")
    sessao = ReviewSession(documento)
    sessao.edit("block-livro-p0001-b0000", "Texto com negrito no fim.",
                metadata={"style": {"bold_spans": [[21, 24]], "italic_spans": []}})
    [revisada] = aplicar_revisao(paginas, sessao.document)
    caminho = exportar.para_epub([revisada], str(tmp_path / "livro.epub"), titulo="Livro")
    with zipfile.ZipFile(caminho) as arquivo:
        xhtml = arquivo.read("OEBPS/pagina-0001.xhtml").decode("utf-8")
    assert "<strong>fim</strong>" in xhtml and "<strong>negrito</strong>" not in xhtml
