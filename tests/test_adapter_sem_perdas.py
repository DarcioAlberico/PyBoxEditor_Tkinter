"""
O adapter vai e volta sem perder nada (item 4 da revisão de 2026-09-18).

A ida existe desde a Fase 1; a volta não existia, e sem ela o documento
revisado só sabia virar arquivo pelos escritores do IR — os dois que embutem
fonte de símbolos e redesenham diagrama (`exportar.para_epub`/`para_docx`)
pedem `PaginaExtraida`, e quem queria os dois mundos guardava a lista de
páginas ao lado do IR.

Os dois critérios de aceite do roadmap estão em
`test_o_round_trip_devolve_a_pagina_igual` e
`test_o_epub_do_round_trip_e_byte_identico`.
"""

from __future__ import annotations

import zipfile

import pytest

from core import exportar, livro
from core.editorial_adapters import (documento_para_paginas_extraidas,
                                     pagina_editorial_para_extraida,
                                     pagina_extraida_para_pagina,
                                     paginas_extraidas_para_documento)
from core.editorial_model import EditorialDocument


def _png() -> bytes:
    from core import render_diagrama

    png, _largura, _altura = render_diagrama.desenhar(
        "8/8/8/8/8/8/8/4K2k w - - 0 1", lado_px=64)
    return png


FEN = "r1bqk2r/pp2bppp/2n1pn2/3p4/3P4/2N1PN2/PP2BPPP/R1BQK2R w - - 0 1"


def _pagina() -> livro.PaginaExtraida:
    """Uma página com as quatro origens de figura, tabela e parágrafos."""
    png = _png()
    return livro.PaginaExtraida(
        numero=3,
        blocos=[
            livro.Paragrafo("Chapter 5", titulo=True, nivel=1, topo=10, pe=40,
                            inicios=[0], registros=[0]),
            livro.Paragrafo("O texto com um trecho em negrito e o resto não.",
                            negrito=[(25, 32)], topo=50, pe=90,
                            inicios=[0, 24], registros=[1, 2]),
            livro.Figura(png, 64, 64, fen=FEN, origem="render", fonte="SkakNew-Diagram",
                         linhas=["1" * 8] * 8, coordenadas=True, orientacao="preta",
                         casas_de_largura=8.75, linhas_emolduradas=False,
                         caixa=(10, 100, 200, 290), lado_a_jogar="b",
                         lado_origem="legenda"),
            livro.Figura(png, 32, 12, origem="faixa", casas_de_largura=8.0),
            livro.Figura(png, 64, 64, origem="recorte", aviso="porteiro recusou",
                         casas_de_largura=8.0, caixa=(10, 300, 200, 490)),
            livro.Tabela([["W: Win", "B: Draw"], ["1 ♖e1!", ""]]),
        ],
        caracteres=120, descartados_por_confianca=2, respingos_descartados=1,
        diagramas=2, diagramas_desenhados=1, colunas=2, reparos=3, cortes=1,
        altura=1000, largura=800, dpi=300, cabecalhos=["SECRETS OF ROOK ENDINGS"],
        roteamento=[{"linha": i, "dominio": "mixed"} for i in range(3)],
    )


def _pagina_de_imagem() -> livro.PaginaExtraida:
    return livro.PaginaExtraida(numero=0, blocos=[livro.Figura(_png(), 800, 1000,
                                                               origem="pagina")],
                                pagina_de_imagem=True, largura=800, altura=1000)


def _ida_e_volta(pagina: livro.PaginaExtraida) -> livro.PaginaExtraida:
    return pagina_editorial_para_extraida(
        pagina_extraida_para_pagina(pagina, document_id="book"))


# ----------------------------------------------------------------------
# O aceite
# ----------------------------------------------------------------------

def test_o_round_trip_devolve_a_pagina_igual():
    """
    Tudo que a página histórica sabe volta — menos `pesos` e `lacunas`, as
    medidas por caractere que `partir_coladas` e `negrito.marcar` consomem
    **dentro** de `livro.extrair`, antes de existir IR. Guardá-las seria pôr
    dois floats por caractere de livro num JSON para ninguém os ler.
    """
    original = _pagina()
    volta = _ida_e_volta(original)

    assert volta.numero == original.numero
    for campo in ("caracteres", "descartados_por_confianca", "respingos_descartados",
                  "diagramas", "diagramas_desenhados", "pagina_de_imagem", "colunas",
                  "reparos", "cortes", "altura", "largura", "dpi", "cabecalhos",
                  "roteamento", "motor_indisponivel"):
        assert getattr(volta, campo) == getattr(original, campo), campo
    assert len(volta.blocos) == len(original.blocos)
    for antes, depois in zip(original.blocos, volta.blocos):
        assert type(antes) is type(depois)
        assert depois == antes, f"{type(antes).__name__} não voltou igual"


def test_o_epub_do_round_trip_e_byte_identico(tmp_path, monkeypatch):
    """O outro critério: o arquivo entregue não muda por ter passado pelo IR."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    paginas = [_pagina(), _pagina_de_imagem()]
    documento = paginas_extraidas_para_documento(paginas, document_id="book",
                                                 title="Livro")
    volta = documento_para_paginas_extraidas(documento)

    direto = exportar.para_epub(paginas, str(tmp_path / "a.epub"), titulo="Livro",
                                identificador="urn:uuid:fixo")
    pelo_ir = exportar.para_epub(volta, str(tmp_path / "b.epub"), titulo="Livro",
                                 identificador="urn:uuid:fixo")
    assert (tmp_path / "a.epub").read_bytes() == (tmp_path / "b.epub").read_bytes()
    assert zipfile.ZipFile(direto).namelist() == zipfile.ZipFile(pelo_ir).namelist()


def test_o_docx_do_round_trip_tem_o_mesmo_documento(tmp_path, monkeypatch):
    pytest.importorskip("docx")
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    paginas = [_pagina()]
    volta = documento_para_paginas_extraidas(
        paginas_extraidas_para_documento(paginas, document_id="book"))

    def corpo(caminho):
        return zipfile.ZipFile(caminho).read("word/document.xml").decode("utf-8")

    assert corpo(exportar.para_docx(paginas, str(tmp_path / "a.docx"))) == \
        corpo(exportar.para_docx(volta, str(tmp_path / "b.docx")))


# ----------------------------------------------------------------------
# O que se perdia, campo a campo
# ----------------------------------------------------------------------

def test_a_origem_da_figura_vira_tipo_de_bloco():
    """
    Três das quatro origens não são tabuleiro: mandar as quatro como `diagram`
    punha `data-fen` num cabeçalho de exercício e fazia o editor procurar
    posição onde não há.
    """
    pagina = pagina_extraida_para_pagina(_pagina(), document_id="book")
    por_origem = {bloco.decision.value.get("origin"): bloco.kind
                  for bloco in pagina.blocks if bloco.metadata.get("legacy_type") == "Figura"}
    assert por_origem == {"render": "diagram", "faixa": "caption",
                          "recorte": "diagram"}

    de_imagem = pagina_extraida_para_pagina(_pagina_de_imagem(), document_id="book")
    assert de_imagem.blocks[0].kind == "figure"


def test_a_largura_em_casas_e_o_negrito_sobrevivem():
    pagina = pagina_extraida_para_pagina(_pagina(), document_id="book")
    diagrama = next(bloco for bloco in pagina.blocks if bloco.kind == "diagram")
    assert diagrama.decision.value["squares_wide"] == 8.75
    paragrafo = next(bloco for bloco in pagina.blocks if bloco.kind == "paragraph")
    assert paragrafo.style["bold_spans"] == [[25, 32]]

    volta = _ida_e_volta(_pagina())
    assert volta.blocos[2].casas_de_largura == 8.75
    assert volta.blocos[1].negrito == [(25, 32)]


def test_o_recorte_sem_posicao_nao_fica_com_fen_none():
    """`data-fen="None"` saía no arquivo: o valor era `null` e quem escreve o
    converteu para texto."""
    pagina = pagina_extraida_para_pagina(_pagina(), document_id="book")
    recorte = [bloco for bloco in pagina.blocks
               if isinstance(bloco.decision.value, dict)
               if bloco.decision.value.get("origin") == "recorte"][0]
    assert recorte.decision.value["fen"] == ""
    assert _ida_e_volta(_pagina()).blocos[4].fen is None


def test_as_linhas_impressas_do_paragrafo_voltam():
    volta = _ida_e_volta(_pagina())
    assert volta.blocos[1].inicios == [0, 24]
    assert volta.blocos[1].registros == [1, 2]
    assert volta.blocos[1].linhas_impressas == 2


def test_o_lado_assumido_nao_volta_como_lido():
    """DEC-06 no round-trip: convenção declarada não vira leitura na volta."""
    assumido = livro.PaginaExtraida(
        numero=0, blocos=[livro.Figura(_png(), 64, 64, fen=FEN, origem="render")])
    volta = _ida_e_volta(assumido)
    assert volta.blocos[0].lado_a_jogar is None
    assert volta.blocos[0].lado_origem == "convencao"

    lido = _ida_e_volta(_pagina()).blocos[2]
    assert lido.lado_a_jogar == "b" and lido.lado_origem == "legenda"


def test_o_bloco_rejeitado_na_revisao_fica_de_fora():
    pagina = pagina_extraida_para_pagina(_pagina(), document_id="book")
    pagina.blocks[0].decision.status = "rejected"
    assert len(pagina_editorial_para_extraida(pagina).blocos) == 5
    assert len(pagina_editorial_para_extraida(
        pagina, incluir_rejeitados=True).blocos) == 6


def test_a_volta_aceita_um_ir_que_nao_veio_do_leitor_medido():
    """Um documento gravado e relido (sem os objetos, só o JSON) volta igual."""
    documento = paginas_extraidas_para_documento([_pagina()], document_id="book")
    relido = EditorialDocument.from_dict(documento.to_dict())
    assert (documento_para_paginas_extraidas(relido)
            == documento_para_paginas_extraidas(documento))


# ----------------------------------------------------------------------
# O que a volta destrava
# ----------------------------------------------------------------------

def test_o_negrito_vira_run_no_html_e_no_docx(tmp_path):
    """
    O adapter guarda o negrito em `style["bold_spans"]` desde a Fase 1, e os
    escritores do IR o ignoravam: o parágrafo saía inteiro em redondo e a
    ênfase impressa no livro sumia.
    """
    from core.editorial_export import EditorialExporter, ExportOptions

    documento = paginas_extraidas_para_documento([_pagina()], document_id="book")
    destino = tmp_path / "livro.html"
    EditorialExporter().export(documento, destino, ExportOptions(format="html"))
    assert "<strong>negrito</strong>" in destino.read_text(encoding="utf-8")

    pytest.importorskip("docx")
    from docx import Document

    EditorialExporter().export(documento, tmp_path / "livro.docx",
                               ExportOptions(format="docx"))
    runs = [run for par in Document(tmp_path / "livro.docx").paragraphs
            for run in par.runs if run.bold]
    assert [run.text for run in runs] == ["negrito"]


def test_a_faixa_do_exercicio_nao_sai_como_diagrama(tmp_path):
    """Uma imagem de cabeçalho com `data-fen` era o que o tipo único produzia."""
    from core.editorial_export import EditorialExporter, ExportOptions

    documento = paginas_extraidas_para_documento([_pagina()], document_id="book")
    destino = tmp_path / "livro.html"
    EditorialExporter().export(documento, destino, ExportOptions(format="html"))
    html = destino.read_text(encoding="utf-8")
    faixa = [linha for linha in html.split("<figure") if 'data-kind="caption"' in linha]
    assert faixa and "data-fen" not in faixa[0]
    assert "data:image/png;base64," in faixa[0]


def test_a_exportacao_revisada_sai_de_um_ir_de_outra_sessao(tmp_path, monkeypatch):
    """
    Sem a volta, exportar EPUB de um documento gravado noutra sessão era
    impossível: os escritores históricos pedem `PaginaExtraida` e a lista do
    leitor já não existia.
    """
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    from core.editorial_legacy import aplicar_revisao

    documento = paginas_extraidas_para_documento([_pagina()], document_id="book")
    relido = EditorialDocument.from_dict(documento.to_dict())

    paginas = aplicar_revisao([], relido)      # nenhuma página do leitor à mão
    assert [p.numero for p in paginas] == [3]
    assert len(paginas[0].blocos) == 6

    caminho = exportar.para_epub(paginas, str(tmp_path / "x.epub"), titulo="Livro",
                                 identificador="urn:uuid:fixo")
    with zipfile.ZipFile(caminho) as arquivo:
        assert "OEBPS/pagina-0004.xhtml" in arquivo.namelist()


def test_a_revisao_de_um_ir_de_outra_sessao_entra_no_arquivo(tmp_path):
    from core.editorial_legacy import aplicar_revisao

    documento = paginas_extraidas_para_documento([_pagina()], document_id="book")
    relido = EditorialDocument.from_dict(documento.to_dict())
    bloco = relido.pages[0].blocks[1]
    bloco.decision.value = "O texto que o revisor escreveu."
    bloco.decision.status = "reviewed"
    relido.pages[0].blocks[0].decision.status = "rejected"

    paginas = aplicar_revisao([], relido)
    assert len(paginas[0].blocos) == 5, "o bloco rejeitado ficou no livro"
    assert paginas[0].blocos[0].texto == "O texto que o revisor escreveu."
