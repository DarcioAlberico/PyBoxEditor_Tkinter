"""A revisão do diagrama vale inteira: FEN, lado a jogar e orientação (RG-17, R-34).

O lado e a orientação revisados eram ignorados em silêncio — a figura saía carimbada
"assumido" e "não revisado", mesmo com a decisão `reviewed`.
"""

import zipfile

import pytest

from core import exportar, lado_a_jogar, livro, render_diagrama
from core.editorial_adapters import (_ORIGEM_DO_LADO, _ORIGEM_NO_IR,
                                     paginas_extraidas_para_documento)
from core.editorial_export import (EditorialExporter, ExportOptions, com_fen_revisado,
                                   fen_do_bloco, imagem_do_diagrama, lado_revisado,
                                   origem_do_lado, revisao_pendente)
from core.editorial_legacy import OpcoesDeFigura, aplicar_revisao
from core.editorial_review import ReviewSession

FEN = "8/1k6/1p6/1K6/P1P5/8/8/8 w - - 0 1"
FEN_B = FEN.replace(" w ", " b ")
OUTRO = "8/8/8/8/8/8/8/4K2k w - - 0 1"


def _desenho(**kw):
    return render_diagrama.desenhar(FEN, lado_px=64, **kw)


def _figura(origem="render", **kw):
    png, largura, altura = _desenho()
    campos = dict(fen=FEN, origem=origem, caixa=(10, 10, 90, 90), casas_de_largura=8.0)
    if origem == "render":
        campos.update(linhas=["x"] * 8, fonte=render_diagrama.FONTE_PADRAO)
    campos.update(kw)
    return livro.Figura(png, largura, altura, **campos)


def _pagina(figura):
    return livro.PaginaExtraida(numero=0, blocos=[livro.Paragrafo("Antes."), figura],
                                largura=1000, altura=1400, dpi=200)


def _revisado(figura, aceitar=False, **mudancas):
    """`(página do leitor, documento revisado)`, com `mudancas` no valor do diagrama."""
    pagina = _pagina(figura)
    sessao = ReviewSession(paginas_extraidas_para_documento([pagina], document_id="livro"))
    alvo = sessao.document.pages[0].blocks[1]
    if aceitar:
        sessao.accept(alvo.id)
    else:
        sessao.edit(alvo.id, {**alvo.decision.value, **mudancas})
    return pagina, sessao.document


def _dos_dois_ramos(pagina, documento):
    """A figura pelas páginas do leitor e de volta do IR — os dois caminhos da exportação."""
    return [aplicar_revisao(paginas, documento, opcoes=OpcoesDeFigura())[0].blocos[1]
            for paginas in ([pagina], [])]


# ----------------------------------------------------------------------
# O lado
# ----------------------------------------------------------------------

@pytest.mark.parametrize("mudancas", [
    {"side_to_move": "b", "side_to_move_source": "manual"},
    {"side_to_move": "b", "side_to_move_source": "usuario"},
    {"side_to_move": "b"},
    {"fen": FEN_B},                                   # o que o diálogo da fila grava
    {"fen": FEN_B, "side_to_move": "b", "side_to_move_source": "manual"},
])
@pytest.mark.parametrize("origem", ["render", "recorte"])
def test_o_lado_revisado_chega_sem_redesenhar(mudancas, origem):
    pagina, documento = _revisado(_figura(origem), **mudancas)
    for figura in _dos_dois_ramos(pagina, documento):
        assert (figura.lado_a_jogar, figura.lado_origem) == ("b", "usuario")
        assert figura.fen == FEN_B and figura.origem == origem
        assert figura.png == pagina.blocos[1].png, "redesenhou para trocar de quem é a vez"
        assert not figura.revisao_pendente
    assert pagina.blocos[1].lado_origem == "convencao", "mexeu na página do leitor"


def test_o_indicador_desenhado_do_lado_de_antes_se_redesenha():
    """A figura que já é desenho, com o quadradinho das brancas: o arquivo diria as duas."""
    com_indicador = _figura(lado_a_jogar="w", lado_origem="legenda")
    com_indicador.png, com_indicador.largura, com_indicador.altura = _desenho(lado_a_jogar="w")
    pagina, documento = _revisado(com_indicador, side_to_move="b", side_to_move_source="manual",
                                  fen=FEN_B)
    for figura in _dos_dois_ramos(pagina, documento):
        assert figura.lado_a_jogar == "b" and figura.png != com_indicador.png
        esperado = render_diagrama.desenhar(FEN_B, fonte=OpcoesDeFigura().fonte,
                                            lado_px=OpcoesDeFigura().lado, lado_a_jogar="b")[0]
        assert figura.png == esperado


def test_o_recorte_da_legenda_fica_mesmo_com_o_lado_trocado():
    pagina, documento = _revisado(_figura("recorte", lado_a_jogar="w", lado_origem="legenda"),
                                  side_to_move="b", side_to_move_source="manual", fen=FEN_B)
    for figura in _dos_dois_ramos(pagina, documento):
        assert figura.origem == "recorte" and figura.png == pagina.blocos[1].png
        assert (figura.lado_a_jogar, figura.lado_origem) == ("b", "usuario")


def test_aceitar_nao_inventa_lado():
    """O `w` do FEN é convenção, e aceitar o diagrama não o torna leitura (DEC-06)."""
    pagina, documento = _revisado(_figura(), aceitar=True)
    bloco = documento.pages[0].blocks[1]
    assert lado_revisado(bloco) is None and origem_do_lado(bloco) == "assumed"
    figura, de_volta = _dos_dois_ramos(pagina, documento)
    assert figura.lado_origem == de_volta.lado_origem == "convencao"
    assert figura is pagina.blocos[1]


# ----------------------------------------------------------------------
# A orientação e a posição
# ----------------------------------------------------------------------

def test_a_orientacao_revisada_redesenha_o_desenho():
    pagina, documento = _revisado(_figura(), orientation="preta")
    for figura in _dos_dois_ramos(pagina, documento):
        assert figura.orientacao == "preta" and figura.fen == FEN
        assert figura.png == render_diagrama.desenhar(
            FEN, fonte=OpcoesDeFigura().fonte, lado_px=OpcoesDeFigura().lado,
            orientacao="preta")[0]


def test_a_orientacao_revisada_nao_troca_o_recorte():
    pagina, documento = _revisado(_figura("recorte"), orientation="preta")
    for figura in _dos_dois_ramos(pagina, documento):
        assert figura.orientacao == "preta" and figura.origem == "recorte"
        assert figura.png == pagina.blocos[1].png


@pytest.mark.parametrize("origem", ["render", "recorte"])
def test_a_posicao_revisada_redesenha_na_orientacao_e_com_o_lado(origem):
    pagina, documento = _revisado(_figura(origem), fen=OUTRO.replace(" w ", " b "),
                                  orientation="preta")
    for figura in _dos_dois_ramos(pagina, documento):
        assert figura.origem == "render" and figura.orientacao == "preta"
        assert (figura.lado_a_jogar, figura.lado_origem) == ("b", "usuario")
        assert figura.png == render_diagrama.desenhar(
            OUTRO, fonte=OpcoesDeFigura().fonte, lado_px=OpcoesDeFigura().lado,
            orientacao="preta", lado_a_jogar="b")[0]


def test_o_roque_revisado_nao_redesenha():
    fen = FEN.replace(" - - ", " KQ - ")
    pagina, documento = _revisado(_figura("recorte"), fen=fen)
    for figura in _dos_dois_ramos(pagina, documento):
        assert figura.fen == fen and figura.origem == "recorte"


def test_o_redesenho_guarda_as_marcas_do_livro():
    pagina, documento = _revisado(_figura(marcas=["e4"]), fen=OUTRO)
    for figura in _dos_dois_ramos(pagina, documento):
        assert figura.marcas == ["e4"]
        assert figura.png == render_diagrama.desenhar(
            OUTRO, fonte=OpcoesDeFigura().fonte, lado_px=OpcoesDeFigura().lado, marcas=["e4"])[0]


# ----------------------------------------------------------------------
# O estado
# ----------------------------------------------------------------------

@pytest.mark.parametrize("status, pendente", [
    ("reviewed", False), ("rejected", False), ("unresolved", True), ("automatic", True)])
def test_a_decisao_responde_antes_do_valor(status, pendente):
    _pagina_, documento = _revisado(_figura(), aceitar=True)
    bloco = documento.pages[0].blocks[1]
    bloco.decision.value["review_required"] = True
    bloco.decision.value["review_status"] = "review_required"
    object.__setattr__(bloco.decision, "status", status)
    assert revisao_pendente(bloco) is pendente


def test_desfazer_devolve_o_lado_da_leitura():
    pagina = _pagina(_figura())
    sessao = ReviewSession(paginas_extraidas_para_documento([pagina], document_id="livro"))
    alvo = sessao.document.pages[0].blocks[1]
    sessao.edit(alvo.id, {**alvo.decision.value, "fen": FEN_B})
    sessao.undo()
    assert lado_revisado(sessao.document.pages[0].blocks[1]) is None


# ----------------------------------------------------------------------
# O arquivo, nos formatos
# ----------------------------------------------------------------------

def test_o_arquivo_diz_o_lado_do_revisor_e_nao_diz_nao_revisado(tmp_path):
    pagina, documento = _revisado(_figura(), fen=FEN_B, orientation="preta", review_required=True)
    alt = f"{FEN_B} — pretas a jogar (informado na revisão)"
    for nome, paginas in (("leitor", aplicar_revisao([pagina], documento)), ("ir", ())):
        destino = tmp_path / f"{nome}.epub"
        EditorialExporter().export(documento, destino, ExportOptions(
            format="epub", paginas=paginas, escritor={"titulo": "Livro"}))
        with zipfile.ZipFile(destino) as z:
            xhtml = z.read("OEBPS/pagina-0001.xhtml").decode("utf-8")
        assert f'alt="{alt}"' in xhtml and "não revisado" not in xhtml, nome
    destino = tmp_path / "l.html"
    EditorialExporter().export(documento, destino, ExportOptions(format="html"))
    html = destino.read_text(encoding="utf-8")
    assert f'data-fen="{FEN_B}"' in html and 'data-side-source="manual"' in html
    assert "pretas a jogar (informado na revisão)" in html and "não revisado" not in html
    destino = tmp_path / "l.txt"
    EditorialExporter().export(documento, destino, ExportOptions(format="txt"))
    assert f"FEN: {FEN_B}" in destino.read_text(encoding="utf-8")


def test_o_html_desenha_a_posicao_revisada():
    _p, documento = _revisado(_figura(), fen=OUTRO)
    bloco = documento.pages[0].blocks[1]
    assert imagem_do_diagrama(bloco)[1] == "desenho"
    assert imagem_do_diagrama(bloco)[0] != bloco.decision.value["png_base64"]


def test_o_docx_tambem(tmp_path):
    docx = pytest.importorskip("docx")
    pagina, documento = _revisado(_figura("recorte"), fen=FEN_B)
    exportar.para_docx(aplicar_revisao([pagina], documento), str(tmp_path / "l.docx"))
    [forma] = docx.Document(str(tmp_path / "l.docx")).inline_shapes
    assert forma._inline.docPr.get("descr") == f"{FEN_B} — pretas a jogar (informado na revisão)"


# ----------------------------------------------------------------------
# O mapa do lado e quem grava
# ----------------------------------------------------------------------

def test_toda_origem_do_lado_vai_e_volta():
    for origem in ("legenda", "legalidade", "lance", "usuario"):
        assert _ORIGEM_DO_LADO[_ORIGEM_NO_IR[origem]] == origem
        documento = paginas_extraidas_para_documento(
            [_pagina(_figura(lado_a_jogar="b", lado_origem=origem, fen=FEN_B))], document_id="l")
        [de_volta] = [p.blocos[1] for p in aplicar_revisao([], documento)]
        assert (de_volta.lado_a_jogar, de_volta.lado_origem) == ("b", origem)
    assert "assumido" not in lado_a_jogar.marca("b", "manual")


def test_a_legenda_ambigua_nao_volta_como_lida():
    """O IR que diz `ambiguous` não sabe o lado (DEC-06): voltava afirmado."""
    documento = paginas_extraidas_para_documento([_pagina(_figura())], document_id="l")
    documento.pages[0].blocks[1].decision.value.update(
        side_to_move="b", side_to_move_source="ambiguous")
    [figura] = [p.blocos[1] for p in aplicar_revisao([], documento)]
    assert figura.lado_a_jogar is None and figura.lado_origem == "convencao"


def test_o_dialogo_grava_o_lado_nos_campos_dele():
    valor = {"fen": FEN, "side_to_move": "w", "side_to_move_source": "legend", "marks": ["e4"]}
    novo = com_fen_revisado(valor, FEN_B)
    assert (novo["side_to_move"], novo["side_to_move_source"]) == ("b", "manual")
    novo["marks"].append("x")
    assert valor["marks"] == ["e4"], "mexeu no valor de antes"
    assert com_fen_revisado(valor, OUTRO)["side_to_move_source"] == "legend"
    assert "side_to_move" not in com_fen_revisado({"fen": ""}, FEN)


def test_o_editor_importa_o_lado_do_revisor():
    from core.editor import importar_ir

    _p, documento = _revisado(_figura(), fen=FEN_B)
    bloco = documento.pages[0].blocks[1]
    assert fen_do_bloco(bloco) == FEN_B
    assert importar_ir._lado_lido(dict(bloco.decision.value), bloco) == "b"
