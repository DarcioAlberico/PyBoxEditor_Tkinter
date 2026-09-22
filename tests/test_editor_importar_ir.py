"""
Testes de `core/editor/importar_ir.py` (ED-11; SPEC_EDITOR §10.6.5, §10.7, DEC-10, AC-008):
o documento editorial sintético vira livro com o mapa da §10.6.5 na letra, a `Origem` em
todo bloco (`data-origem-*`, sem colidir com `data-pagina`) e o `data-suspeito`
(AC-ED11-1); a volta gera no diário do `review_journal_path` os eventos de AC-008 por
`from_journal` (AC-ED11-2); desfazer antes de salvar não gera evento, editar/salvar/
editar de volta/salvar dá dois, e o bloco já editado na fila tem `before` igual ao `after`
da fila (AC-ED11-3); a fusão dá `edit` no primeiro e `reject` no segundo (AC-ED11-4).

Rodar sem pytest:      .venv/Scripts/python.exe tests/test_editor_importar_ir.py
"""

import base64
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import epub, importar_ir, modelo as m, xhtml
from core.editorial_model import Decision, EditorialBlock, EditorialDocument, EditorialPage, Evidence, SourceRef

FEN_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"
FEN_REIS = "8/8/8/8/8/8/8/K6k"


def png_cinza(lado: int = 24, tom: int = 200) -> str:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("L", (lado, lado), tom).save(buffer, "PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _ref(indice: int, bbox=None) -> SourceRef:
    return SourceRef("doc", indice, bbox=bbox)


def _bloco(page_id: str, indice: int, kind: str, order: int, value, *, status="automatic", style=None, meta=None,
           codes=("legacy_adapter",), bbox=None, evidence_ids=()) -> EditorialBlock:
    return EditorialBlock(id=f"block-{page_id}-b{order:04d}", kind=kind, order=order, source_refs=[_ref(indice, bbox)],
                          decision=Decision(value, list(evidence_ids), status, list(codes)), style=style or {},
                          metadata=meta or {})


def documento_sintetico(document_id: str = "doc") -> EditorialDocument:
    """
    O documento do AC-ED11-1: 3 páginas, 2 `heading` 1, `diagram` com `fen` + `png_base64`,
    `diagram` sem `fen`, `table`, `paragraph` com `bold_spans`, `caption`, `unknown`,
    `unresolved`, um `header` e um `page_break`.
    """
    p1 = "doc-p0001"
    evidencia = Evidence("ev-linha", _ref(1, (10, 20, 300, 40)), observed_text="Suspeito por motor.",
                         engine="livro.extrair", confidence=0.4, diagnostics=["o motor de prosa faltou nesta linha"])
    evidencia.alternatives = []
    from core.editorial_model import Hypothesis

    evidencia.alternatives = [Hypothesis("ev-linha-ancora", "Suspeito p0r m0tor.", 0.5, "glyph_chain",
                                         metadata={"papel": "âncora da cadeia própria"}),
                              Hypothesis("ev-linha-motor", "Suspeito por motor.", 0.9, "line_engine",
                                         metadata={"papel": "linha do motor de prosa"})]
    paginas = [
        EditorialPage(p1, 0, [_ref(0)], [
            _bloco(p1, 0, "heading", 0, "Capítulo um", style={"heading_level": 1}),
            _bloco(p1, 0, "paragraph", 1, "Texto com negrito no meio.", style={"bold_spans": [[10, 17]]},
                   bbox=(0, 100, 800, 140)),
            _bloco(p1, 0, "diagram", 2, {"fen": FEN_E4, "origin": "recorte", "warning": None, "width": 24,
                                         "height": 24, "orientation": "branca", "lines": None,
                                         "font": "SkakNew-Diagram", "coordinates": False, "framed_lines": None,
                                         "png_base64": png_cinza(), "bbox": [10, 10, 34, 34]}),
            _bloco(p1, 0, "caption", 3, "Após 1.e4"),
            _bloco(p1, 0, "header", 4, "Cabeçalho corrido"),
        ], []),
        EditorialPage("doc-p0002", 1, [_ref(1)], [
            _bloco("doc-p0002", 1, "diagram", 0, {"fen": None, "origin": "recorte", "warning": "ocupação a 0,71",
                                                  "png_base64": png_cinza(20, 120), "bbox": [5, 5, 25, 25]},
                   status="unresolved", codes=("legacy_adapter", "diagram_uncertain"),
                   meta={"motivos": ["o porteiro não confiou no tabuleiro: ocupação a 0,71"],
                         "review_required": True}),
            _bloco("doc-p0002", 1, "table", 1, {"rows": [["a", "b"], ["c"]]}),
            _bloco("doc-p0002", 1, "unknown", 2, "coisa estranha", meta={"legacy_type": "Xis"}),
            _bloco("doc-p0002", 1, "paragraph", 3, "Suspeito por motor.",
                   codes=("legacy_adapter", "motor_indisponivel"), evidence_ids=["ev-linha"],
                   meta={"motivos": ["o motor de prosa faltou"], "review_required": True,
                         "linhas": [{"evidence_id": "ev-linha", "texto": "Suspeito por motor.", "registro": 0}]}),
            _bloco("doc-p0002", 1, "page_break", 4, None),
            _bloco("doc-p0002", 1, "chess_sequence", 5, "1.e4 e5 2.Nf3"),
        ], [evidencia]),
        EditorialPage("doc-p0003", 2, [_ref(2)], [
            _bloco("doc-p0003", 2, "heading", 0, "Capítulo dois", style={"heading_level": 1}),
            _bloco("doc-p0003", 2, "paragraph", 1, "Fim."),
            _bloco("doc-p0003", 2, "paragraph", 2, "Rejeitado antes.", status="rejected"),
        ], []),
    ]
    doc = EditorialDocument(document_id, "Livro sintético", "pt", paginas)
    doc.validate()
    return doc


def _tipos(cap):
    return [type(b).__name__ for b in cap.blocos]


# ----------------------------------------------------------------------
# AC-ED11-1
# ----------------------------------------------------------------------

def test_ac1_o_documento_sintetico_vira_livro_com_o_mapa_da_spec(tmp_path):
    doc = documento_sintetico()
    livro, rel = importar_ir.de_documento(doc)
    assert rel.formato == "editorial" and rel.capitulos == 2 and rel.metadados["paginas"] == 3
    c1, c2 = livro.capitulos
    assert _tipos(c1) == ["MarcaDePagina", "Titulo", "Paragrafo", "Diagrama", "Paragrafo", "MarcaDePagina", "Figura",
                          "Tabela", "Paragrafo", "Paragrafo", "QuebraDePagina", "Paragrafo"]
    assert _tipos(c2) == ["MarcaDePagina", "Titulo", "Paragrafo"]
    assert [b.pagina for b in c1.blocos if isinstance(b, m.MarcaDePagina)] == [1, 2]      # page_index + 1
    assert c2.blocos[0].pagina == 3
    # o parágrafo com negrito
    par = c1.blocos[2]
    assert [(t.texto, t.negrito) for t in par.trechos] == [("Texto com ", False), ("negrito", True), (" no meio.", False)]
    # o diagrama: lado desconhecido (DEC-06), o recorte como recurso
    d = c1.blocos[3]
    assert isinstance(d, m.Diagrama) and d.posicao == FEN_E4 and d.lado == "" and d.modo == "png"
    assert d.fonte == "SkakNew-Diagram" and d.recorte == "Images/recorte-doc-p0001-0002.png"
    assert d.recorte in livro.recursos and livro.recursos[d.recorte].dados.startswith(b"\x89PNG")
    # a legenda, o suspeito sem posição (figura com aviso), a tabela retangular, o desconhecido, a notação
    assert c1.blocos[4].estilo == "legenda" and m.texto_de(c1.blocos[4]) == "Após 1.e4"
    fig = c1.blocos[6]
    assert isinstance(fig, m.Figura) and fig.alt == "ocupação a 0,71" and fig.extras["title"] == "ocupação a 0,71"
    assert fig.extras["data-suspeito"] == "diagram_uncertain"
    tab = c1.blocos[7]
    assert isinstance(tab, m.Tabela) and [[m.texto_de(c.blocos[0]) for c in f] for f in tab.filas] == [["a", "b"],
                                                                                                        ["c", ""]]
    assert m.texto_de(c1.blocos[8]) == "coisa estranha" and c1.blocos[8].estilo == "corpo"
    assert c1.blocos[9].extras["data-suspeito"] == "motor_indisponivel"
    assert c1.blocos[11].estilo == "notacao"
    # a origem em todo bloco (não nas marcas nem nas quebras de página), com a caixa quando há
    for cap in livro.capitulos:
        for b in cap.blocos:
            if isinstance(b, (m.MarcaDePagina, m.QuebraDePagina)):
                assert b.origem is None
            else:
                assert b.origem is not None and b.origem.page_id.startswith("doc-p") and b.origem.bloco_id.startswith("block-")
    assert par.origem.caixa == (0, 100, 800, 140) and d.origem.caixa == (10, 10, 34, 34) and par.origem.pagina == 0
    # os avisos: header ignorado, sem fen, desconhecido
    assert any("header ignorado" in a for a in rel.avisos)
    assert any("ficou como figura" in a for a in rel.avisos) and any("tipo desconhecido" in a for a in rel.avisos)
    assert rel.metadados["ignorados"] == 1 and rel.metadados["rejeitados"] == 1
    # o XHTML leva data-origem-* e data-suspeito, e a marca de página continua com data-pagina
    x = xhtml.escrever(c1)
    assert 'data-origem-pagina="doc-p0001" data-origem-bloco="block-doc-p0001-b0001" data-origem-caixa="0,100,800,140"' in x
    assert 'data-suspeito="motor_indisponivel"' in x and 'data-suspeito="diagram_uncertain"' in x
    assert x.count('epub:type="pagebreak"') == 2 and "data-origem-pagina=\"doc-p0002\" epub:type=\"pagebreak\"" not in x
    # salvo e reaberto: a origem e a suspeita voltam
    caminho = str(tmp_path / "ir.epub")
    epub.escrever(livro, caminho)
    relido, _r = epub.ler(caminho)
    par2 = next(b for b in relido.capitulos[0].blocos if isinstance(b, m.Paragrafo) and m.texto_de(b).startswith("Texto"))
    assert par2.origem is not None and par2.origem.bloco_id == "block-doc-p0001-b0001" and par2.origem.caixa == (0, 100, 800, 140)
    assert any(b.extras.get("data-suspeito") == "motor_indisponivel" for b in relido.capitulos[0].blocos)
    # metadados do livro
    assert livro.metadados.titulo == "Livro sintético" and livro.metadados.idioma == "pt"
    assert livro.marcos == [("bodymatter", "Text/cap-0001.xhtml")]


def test_ac1_dividir_por_pagina_e_o_json_gravado(tmp_path):
    doc = documento_sintetico()
    doc.metadata["review_journal_path"] = str(tmp_path / "saida.review.jsonl")
    doc.metadata["source_path"] = str(tmp_path / "livro.pdf")
    livro, _rel = importar_ir.de_documento(doc, dividir="pagina")
    assert [c.arquivo for c in livro.capitulos] == ["Text/cap-0001.xhtml", "Text/cap-0002.xhtml", "Text/cap-0003.xhtml"]
    assert [b.pagina for c in livro.capitulos for b in c.blocos if isinstance(b, m.MarcaDePagina)] == [1, 2, 3]
    assert livro.origem.diario == str(tmp_path / "saida.review.jsonl") and livro.origem.pdf == str(tmp_path / "livro.pdf")
    with pytest.raises(ValueError):
        importar_ir.de_documento(doc, dividir="capitulo")
    # o JSON gravado pelo pipeline
    caminho = str(tmp_path / "doc.json")
    doc.save_json(caminho)
    livro2, rel2 = importar_ir.ler(caminho)
    assert rel2.arquivos == [caminho] and livro2.origem.documento_editorial == os.path.abspath(caminho)
    assert importar_ir.caminho_do_diario(doc, caminho) == str(tmp_path / "saida.review.jsonl")
    doc.metadata.pop("review_journal_path")
    assert importar_ir.caminho_do_diario(doc, caminho) == str(tmp_path / "doc.review.jsonl")
    assert importar_ir.caminho_do_diario(doc) == ""
    (tmp_path / "nada.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        importar_ir.ler(str(tmp_path / "nada.json"))
    # sem título nem heading: o document_id; documento vazio: um capítulo com um parágrafo
    vazio = EditorialDocument("vazio", "", "und", [])
    livro3, rel3 = importar_ir.de_documento(vazio)
    assert livro3.metadados.titulo == "vazio" and rel3.capitulos == 1 and _tipos(livro3.capitulos[0]) == ["Paragrafo"]


def test_de_paginas_passa_pelo_adapter(tmp_path):
    from core import livro as livro_mod

    pagina = livro_mod.PaginaExtraida(numero=4, blocos=[
        livro_mod.Paragrafo("Título da página", titulo=True, nivel=1),
        livro_mod.Paragrafo("Corpo com negrito.", negrito=[(10, 17)]),
        livro_mod.Figura(base64.b64decode(png_cinza()), 24, 24, fen=FEN_REIS + " w - - 0 1", origem="render"),
        livro_mod.Tabela([["x", "y"]]),
    ], largura=800, altura=1000)
    livro, rel = importar_ir.de_paginas([pagina], document_id="livro", titulo="Das páginas", idioma="pt")
    cap = livro.capitulos[0]
    assert _tipos(cap) == ["MarcaDePagina", "Titulo", "Paragrafo", "Diagrama", "Tabela"] and cap.blocos[0].pagina == 5
    assert cap.blocos[1].origem.bloco_id == "block-livro-p0005-b0000" and cap.blocos[2].trechos[1].negrito
    assert cap.blocos[3].posicao == FEN_REIS and cap.blocos[3].recorte == ""            # render: sem recorte
    assert livro.metadados.titulo == "Das páginas" and rel.blocos == 7          # as duas células contam


# ----------------------------------------------------------------------
# AC-ED11-2 (AC-008), AC-ED11-3, AC-ED11-4
# ----------------------------------------------------------------------

def _livro_e_documento(tmp_path):
    doc = documento_sintetico()
    doc.metadata["review_journal_path"] = str(tmp_path / "saida.review.jsonl")
    livro, _rel = importar_ir.de_documento(doc)
    return livro, doc


def _bloco_de(livro, bloco_id):
    return next(b for c in livro.capitulos for b in c.blocos if b.origem is not None and b.origem.bloco_id == bloco_id)


def test_ac2_ac008_os_eventos_no_diario_do_review_journal_path(tmp_path):
    livro, doc = _livro_e_documento(tmp_path)
    diario = importar_ir.caminho_do_diario(doc)
    # dois blocos com origem editados, um sem origem novo, um quarto com origem apagado
    par = _bloco_de(livro, "block-doc-p0001-b0001")
    par.trechos = [m.Trecho(texto="Texto "), m.Trecho(texto="corrigido", negrito=True), m.Trecho(texto=" no meio.")]
    fim = _bloco_de(livro, "block-doc-p0003-b0001")
    fim.trechos = [m.Trecho(texto="Fim de verdade.")]
    livro.capitulos[1].blocos.append(m.Paragrafo(trechos=[m.Trecho(texto="Novo, sem origem.")]))
    cap1 = livro.capitulos[0]
    cap1.blocos.remove(_bloco_de(livro, "block-doc-p0002-b0002"))                   # o "coisa estranha"
    mudancas = importar_ir.eventos_de(livro, doc)
    assert [(mu.bloco_id, mu.motivo) for mu in mudancas] == [("block-doc-p0001-b0001", "editado"),
                                                             ("block-doc-p0002-b0002", "apagado"),
                                                             ("block-doc-p0003-b0001", "editado")]
    assert mudancas[0].after == "Texto corrigido no meio." and mudancas[1].after is None
    ponte = importar_ir.gravar_eventos(livro, doc, diario)
    assert ponte.eventos == 3 and ponte.editados == 2 and ponte.apagados == 1 and ponte.fundidos == 0
    assert ponte.novos == [livro.capitulos[1].blocos[-1].id] and ponte.diario == diario
    assert any("não viaja" in a for a in ponte.avisos)                                # o negrito editado
    # o diário: dois reviewed e um rejected, before/after certos, reason_codes ("editor",), user "editor"
    linhas = [json.loads(li) for li in open(diario, encoding="utf-8").read().splitlines() if li.strip()]
    assert [(e["target_id"], e["status"], e["reason_codes"], e["user"], e["before"], e["after"]) for e in linhas] == [
        ("block-doc-p0001-b0001", "reviewed", ["editor"], "editor", "Texto com negrito no meio.",
         "Texto corrigido no meio."),
        ("block-doc-p0002-b0002", "rejected", ["rejected"], "editor", "coisa estranha", "coisa estranha"),
        ("block-doc-p0003-b0001", "reviewed", ["editor"], "editor", "Fim.", "Fim de verdade."),
    ]
    # o documento projetado, com o original preservado
    projetado = ponte.documento
    bloco = next(b for p in projetado.pages for b in p.blocks if b.id == "block-doc-p0001-b0001")
    assert bloco.decision.value == "Texto corrigido no meio." and bloco.decision.status == "reviewed"
    assert bloco.decision.original_value == "Texto com negrito no meio."
    assert next(b for p in projetado.pages for b in p.blocks if b.id == "block-doc-p0002-b0002").decision.status == "rejected"
    assert len(projetado.review_events) == 3 and doc.review_events == []                # o de entrada não muda
    # de novo, sem mudar nada: from_journal repete os eventos e não grava outros
    ponte2 = importar_ir.gravar_eventos(livro, doc, diario)
    assert ponte2.eventos == 0 and len(ponte2.documento.review_events) == 3
    assert len(open(diario, encoding="utf-8").read().splitlines()) == 3
    # o bloco já editado na fila: before igual ao after da fila
    from core.editorial_review import ReviewJournal, ReviewSession

    ReviewSession(doc, journal=ReviewJournal(diario)).edit("block-doc-p0001-b0003", "Após 1.e4 (fila)")
    legenda = _bloco_de(livro, "block-doc-p0001-b0003")
    legenda.trechos = [m.Trecho(texto="Após 1.e4 (editor)")]
    ponte3 = importar_ir.gravar_eventos(livro, doc, diario)
    evento = ponte3.documento.review_events[-1]
    assert ponte3.eventos == 1 and evento.target_id == "block-doc-p0001-b0003"
    assert evento.before == "Após 1.e4 (fila)" and evento.after == "Após 1.e4 (editor)"


def test_ac3_desfazer_antes_de_salvar_nao_gera_evento_e_editar_de_volta_gera_o_segundo(tmp_path):
    livro, doc = _livro_e_documento(tmp_path)
    diario = importar_ir.caminho_do_diario(doc)
    par = _bloco_de(livro, "block-doc-p0001-b0001")
    original = [m.Trecho(**{k: v for k, v in m.para_dict(t).items() if k != "tipo"}) for t in par.trechos]
    par.trechos = [m.Trecho(texto="mexido")]
    par.trechos = original                                                              # desfeito antes de salvar
    assert importar_ir.eventos_de(livro, doc) == [] and importar_ir.gravar_eventos(livro, doc, diario).eventos == 0
    assert not os.path.exists(diario) or open(diario, encoding="utf-8").read() == ""
    par.trechos = [m.Trecho(texto="Texto mexido no meio.")]
    p1 = importar_ir.gravar_eventos(livro, doc, diario)
    par.trechos = [m.Trecho(**{k: v for k, v in m.para_dict(t).items() if k != "tipo"}) for t in original]
    p2 = importar_ir.gravar_eventos(livro, doc, diario)
    assert p1.eventos == 1 and p2.eventos == 1
    eventos = p2.documento.review_events
    assert [(e.before, e.after) for e in eventos] == [("Texto com negrito no meio.", "Texto mexido no meio."),
                                                       ("Texto mexido no meio.", "Texto com negrito no meio.")]
    assert eventos[-1].before == eventos[0].after


def test_ac4_a_fusao_da_edit_no_primeiro_e_reject_no_segundo(tmp_path):
    livro, doc = _livro_e_documento(tmp_path)
    diario = importar_ir.caminho_do_diario(doc)
    cap = livro.capitulos[0]
    a = _bloco_de(livro, "block-doc-p0002-b0002")                                       # "coisa estranha"
    b = _bloco_de(livro, "block-doc-p0002-b0003")                                       # "Suspeito por motor."
    juntado = m.juntar_paragrafos(a, b)
    assert [o.bloco_id for o in juntado.origem.fundidas] == ["block-doc-p0002-b0003"]
    i = cap.blocos.index(a)
    cap.blocos[i] = juntado
    cap.blocos.remove(b)
    mudancas = importar_ir.eventos_de(livro, doc)
    assert [(mu.bloco_id, mu.motivo) for mu in mudancas] == [("block-doc-p0002-b0002", "fundido"),
                                                             ("block-doc-p0002-b0003", "fundido_apagado")]
    assert mudancas[0].after == "coisa estranhaSuspeito por motor."
    ponte = importar_ir.gravar_eventos(livro, doc, diario)
    assert ponte.fundidos == 2 and ponte.editados == 0 and ponte.apagados == 0
    eventos = ponte.documento.review_events
    assert [(e.target_id, e.status) for e in eventos] == [("block-doc-p0002-b0002", "reviewed"),
                                                          ("block-doc-p0002-b0003", "rejected")]
    assert eventos[0].after == "coisa estranhaSuspeito por motor." and eventos[0].reason_codes == ("editor",)
    # a origem fundida volta do XHTML
    x = xhtml.escrever(cap)
    assert 'data-origem-fundidas="doc-p0002|block-doc-p0002-b0003"' in x


def test_o_diagrama_e_a_tabela_viajam_inteiros_e_o_diario_alheio_e_ignorado(tmp_path):
    livro, doc = _livro_e_documento(tmp_path)
    diario = importar_ir.caminho_do_diario(doc)
    d = _bloco_de(livro, "block-doc-p0001-b0002")
    # só o lado a jogar mudou: a posição é a mesma, e o IR não tem lado — nada a dizer
    d.fen = FEN_E4 + " b KQkq e3 0 1"
    assert importar_ir.eventos_de(livro, doc) == []
    d.fen = FEN_REIS + " w - - 0 1"
    d.orientacao = "preta"
    [mudanca] = importar_ir.eventos_de(livro, doc)
    assert mudanca.bloco_id == "block-doc-p0001-b0002" and mudanca.after["fen"] == FEN_REIS + " w - - 0 1"
    assert mudanca.after["orientation"] == "preta" and mudanca.after["png_base64"] == png_cinza()
    assert mudanca.after["font"] == "SkakNew-Diagram" and mudanca.after["bbox"] == [10, 10, 34, 34]
    tab = _bloco_de(livro, "block-doc-p0002-b0001")
    tab.filas[0][0].blocos[0].trechos[0].texto = "A"
    mudancas = importar_ir.eventos_de(livro, doc)
    assert mudancas[1].after == {"rows": [["A", "b"], ["c", ""]]}
    # a figura que veio de um diagrama sem fen não tem valor comparável; apagada, é rejeitada
    fig = _bloco_de(livro, "block-doc-p0002-b0000")
    livro.capitulos[0].blocos.remove(fig)
    assert ("block-doc-p0002-b0000", None, "apagado") in importar_ir.eventos_de(livro, doc)
    # o diário de outro documento no mesmo caminho: ignorado, com aviso, e o livro continua gravando
    from core.editorial_review import ReviewJournal, ReviewSession

    outro = documento_sintetico("outro")
    ReviewSession(outro, journal=ReviewJournal(diario)).accept("block-doc-p0001-b0001")   # outro document_id
    ponte = importar_ir.gravar_eventos(livro, doc, diario)
    assert any("não é deste documento" in a for a in ponte.avisos) and ponte.eventos == 3
    assert len(ponte.documento.review_events) == 3
    # sem diário (caminho vazio): a sessão grava só na memória
    ponte2 = importar_ir.gravar_eventos(livro, doc, "")
    assert ponte2.eventos == 3 and ponte2.diario == ""


def test_o_bloco_novo_e_a_origem_repetida_vao_ao_relatorio_e_nao_ao_diario(tmp_path):
    livro, doc = _livro_e_documento(tmp_path)
    cap = livro.capitulos[1]
    fim = _bloco_de(livro, "block-doc-p0003-b0001")
    copia = m.Paragrafo(trechos=[m.Trecho(texto="Fim.")], origem=m.Origem(page_id="doc-p0003",
                                                                             bloco_id="block-doc-p0003-b0001", pagina=2))
    cap.blocos.append(copia)
    cap.blocos.append(m.QuebraDePagina())
    ponte = importar_ir.gravar_eventos(livro, doc, importar_ir.caminho_do_diario(doc))
    assert ponte.eventos == 0 and ponte.novos == [copia.id] and fim.id != copia.id
    assert any("repete a origem" in a for a in ponte.avisos)
    assert "Blocos novos" in " ".join(ponte.linhas())


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
