"""
Testes da F122 — a moldura do diagrama em texto é desenhada pela própria fonte.

O usuário (2026-09-24) pediu a borda como o plugin ChessMeridaOCR do Sigil a escreve:

    !""""""""#
    $ + + + +%
    …
    /(((((((()

Até aqui a moldura sem coordenada saía da CSS (`div.diagrama.caixa`) e da borda da
célula no DOCX; agora, com moldura pedida, o tabuleiro sai na grade de dez por dez em
glifo. A Chess Merida sempre teve os glifos; a SkakNew de 2004 não tinha nenhum, e a
cópia do projeto ganhou 24 (`gerar_moldura_da_skaknew.py`), sem tocar nos originais.

Rodar sem pytest:      python tests/test_f122_moldura_na_fonte.py
"""

import os
import re
import shutil
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core import exportar, livro
from core import render_diagrama as rd
from core.editor import dialeto, epub, fontes, modelo as m, pdf_io, xhtml
from core.editor.conversao import OpcoesDeConversao

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MERIDA = "ChessMerida-Diagram"
SKAK = "SkakNew-Diagram"
FEN = "1r4k1/8/5PK1/8/8/8/R7/8 w - - 0 1"

#: O diagrama que o usuário colou, e a posição dele.
EXEMPLO = ['!""""""""#', "$ + + + +%", "$+ + +l+ %", "$ + + + +%", "$+ + +k+ %",
           "$ + + P +%", "$+ + + + %", "$ + + + +%", "$+ + + + %", "/(((((((()"]
FEN_DO_EXEMPLO = "8/5k2/8/5K2/5P2/8/8/8 w - - 0 1"

COMBINACOES = [(fonte, moldura, cantos) for fonte in (MERIDA, SKAK)
               for moldura in ("simples", "dupla") for cantos in ("reto", "arredondado")]


def _figura(nome, moldura="simples", cantos="reto", coordenadas=False, orientacao="branca"):
    """A figura como o `livro` a monta: as linhas saem de `linhas_do_diagrama`."""
    png, largura, altura = rd.desenhar(FEN, fonte=nome, lado_px=96, moldura=moldura, cantos=cantos,
                                       coordenadas=coordenadas, orientacao=orientacao)
    linhas, emolduradas = rd.linhas_do_diagrama(FEN, rd.carregar(nome), orientacao, moldura, cantos, coordenadas)
    return livro.Figura(png, largura, altura, fen=FEN, origem="render", linhas=linhas,
                        linhas_emolduradas=emolduradas, fonte=nome, coordenadas=coordenadas,
                        orientacao=orientacao)


def _epub(*figuras, pasta=None, **kw):
    caminho = os.path.join(pasta or tempfile.mkdtemp(), "livro.epub")
    exportar.para_epub([livro.PaginaExtraida(numero=0, blocos=[livro.Paragrafo("Prosa."), *figuras])],
                       caminho, diagramas="fonte", **kw)
    return caminho


def _ler(caminho):
    with zipfile.ZipFile(caminho) as z:
        return {n: z.read(n) for n in z.namelist()}


def _pres(pagina: str) -> list[list[str]]:
    import html
    return [html.unescape(pre).split("\n") for pre in re.findall(r"<pre>(.*?)</pre>", pagina, re.S)]


# ----------------------------------------------------------------------
# A grade
# ----------------------------------------------------------------------

def test_a_moldura_dupla_da_merida_e_a_do_exemplo_do_usuario():
    assert rd.grade(FEN_DO_EXEMPLO, rd.carregar(MERIDA), "branca", "dupla", "reto", com_rotulos=False) == EXEMPLO


@pytest.mark.parametrize("fonte,moldura,cantos", COMBINACOES)
def test_com_moldura_o_texto_sai_emoldurado_na_fonte_e_volta_igual(fonte, moldura, cantos):
    mapa = rd.carregar(fonte)
    for orientacao in ("branca", "preta"):
        linhas, emolduradas = rd.linhas_do_diagrama(FEN, mapa, orientacao, moldura, cantos)
        assert emolduradas and len(linhas) == 10 and {len(li) for li in linhas} == {10}
        assert [li[1:9] for li in linhas[1:9]] == rd.linhas(FEN, mapa, orientacao)
        assert rd.moldura_da_grade(linhas, mapa) == (moldura, cantos, False)
        assert rd.fen_de_linhas(linhas, mapa)[0] == rd.fen_de_linhas(rd.linhas(FEN, mapa, orientacao), mapa)[0]


def test_sem_moldura_e_na_skaknew_com_coordenada_sai_o_de_sempre():
    merida, skak = rd.carregar(MERIDA), rd.carregar(SKAK)
    assert rd.linhas_do_diagrama(FEN, merida, "branca", "sem") == (rd.linhas(FEN, merida), False)
    # a SkakNew tem a moldura, mas não o rótulo: com coordenada, a moldura e as letras ficam de fora
    assert rd.linhas_do_diagrama(FEN, skak, "branca", "simples", "reto", True) == (rd.linhas(FEN, skak), False)
    rotulada, emolduradas = rd.linhas_do_diagrama(FEN, merida, "preta", "dupla", "reto", True)
    assert emolduradas and rd.moldura_da_grade(rotulada, merida) == ("dupla", "reto", True)


# ----------------------------------------------------------------------
# A fonte
# ----------------------------------------------------------------------

def test_a_skaknew_do_projeto_e_a_original_mais_a_moldura():
    pytest.importorskip("fontTools")
    from scripts.medidas import gerar_moldura_da_skaknew as gerador

    assert gerador.conferir(gerador.DESTINO, gerador.ORIGEM) == []
    import hashlib
    with open(gerador.DESTINO, "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == rd._mapas()[SKAK]["sha256"], (
            "a fonte mudou e o sha do fontes_de_diagrama.json não")


def test_a_skaknew_regerada_sai_igual(tmp_path):
    """O gerador é reprodutível: o `head` leva a data da F122, e não a hora de rodar."""
    pytest.importorskip("fontTools")
    from scripts.medidas import gerar_moldura_da_skaknew as gerador

    destino = str(tmp_path / "SkakNew-Diagram.otf")
    gerador.acrescentar(gerador.ORIGEM, destino, gerador.teclas_do_mapa())
    with open(destino, "rb") as a, open(gerador.DESTINO, "rb") as b:
        assert a.read() == b.read()


@pytest.mark.parametrize("fonte", [MERIDA, SKAK])
def test_cada_peca_da_moldura_tem_tinta_do_lado_do_tabuleiro(fonte):
    """O filete do `topo` mora no pé da casa, o da `esquerda` no lado direito, e assim por diante."""
    fitz = pytest.importorskip("fitz")
    mapa = rd.carregar(fonte)
    f = fitz.Font(fontfile=mapa.arquivo)
    for moldura, pecas in mapa.molduras.items():
        for peca, lado in (("topo", "baixo"), ("base", "cima"), ("esquerda", "direita"), ("direita", "esquerda")):
            doc = fitz.open()
            pagina = doc.new_page(width=100, height=100)
            pagina.insert_text((0, 100), pecas[peca], fontsize=100, fontname="d", fontfile=mapa.arquivo)
            pix = pagina.get_pixmap(colorspace=fitz.csGRAY, alpha=False)
            tinta = [(i % pix.width, i // pix.width) for i, v in enumerate(pix.samples) if v < 128]
            doc.close()
            assert tinta, f"{fonte} {moldura} {peca}: glifo vazio"
            xs, ys = [p[0] for p in tinta], [p[1] for p in tinta]
            onde = {"baixo": min(ys) > 60, "cima": max(ys) < 40, "direita": min(xs) > 60,
                    "esquerda": max(xs) < 40}[lado]
            assert onde, f"{fonte} {moldura} {peca}: a tinta não está do lado do tabuleiro"
            assert f.glyph_advance(ord(pecas[peca])) == 1.0


# ----------------------------------------------------------------------
# O arquivo
# ----------------------------------------------------------------------

def test_no_epub_a_moldura_vem_no_pre_e_a_caixa_sai_so_sem_glifo(tmp_path):
    caminho = _epub(_figura(MERIDA, "dupla"), _figura(SKAK, "simples", "arredondado"),
                    _figura(SKAK, "simples", coordenadas=True), _figura(MERIDA, "sem"), pasta=str(tmp_path))
    pagina = _ler(caminho)["OEBPS/pagina-0001.xhtml"].decode("utf-8")
    classes = re.findall(r'<div class="(diagrama[^"]*)"', pagina)
    assert classes == [f"diagrama fonte-{MERIDA}", f"diagrama fonte-{SKAK}",
                       f"diagrama caixa fonte-{SKAK}", f"diagrama caixa fonte-{MERIDA}"]
    merida_dupla, skak_simples, _skak_rotulada, merida_sem = _pres(pagina)
    assert merida_dupla[0] == '!""""""""#' and merida_dupla[-1] == "/(((((((()"
    assert skak_simples[0] == "g========h" and skak_simples[-1] == "d88888888f"
    assert len(merida_sem) == 8


def test_desenhado_com_a_folha_e_a_fonte_do_epub_a_moldura_fecha(tmp_path):
    """No `fitz.Story`, cada fila da grade tem dez casas: a moldura é glifo, e glifo de 1 em."""
    fitz = pytest.importorskip("fitz")
    caminho = _epub(_figura(MERIDA, "dupla", "arredondado"), _figura(SKAK, "dupla"), pasta=str(tmp_path))
    entradas = _ler(caminho)
    pagina = entradas["OEBPS/pagina-0001.xhtml"].decode("utf-8")
    folha = entradas["OEBPS/estilo.css"].decode("utf-8")
    arquivo = fitz.Archive()
    for nome, dados in entradas.items():
        if nome.startswith("OEBPS/fonts/"):
            arquivo.add(dados, nome[len("OEBPS/"):])
    corpo = pagina[pagina.index("<body>") + 6:pagina.index("</body>")]
    story = fitz.Story(html=f"<html><body>{corpo}</body></html>", user_css=folha, archive=arquivo)
    saida = str(tmp_path / "desenho.pdf")
    escritor = fitz.DocumentWriter(saida)
    mais = True
    while mais:
        dispositivo = escritor.begin_page(fitz.paper_rect("a4"))
        mais, _ = story.place(fitz.Rect(36, 36, 559, 806))
        story.draw(dispositivo)
        escritor.end_page()
    escritor.close()
    doc = fitz.open(saida)
    try:
        for familia, esperadas in (("Merida", _figura(MERIDA, "dupla", "arredondado").linhas),
                                   ("SkakNew", _figura(SKAK, "dupla").linhas)):
            filas = {}
            for bloco in doc[0].get_text("rawdict")["blocks"]:
                for linha in bloco.get("lines", []):
                    for span in linha["spans"]:
                        if familia in span["font"]:
                            for c in span["chars"]:
                                filas.setdefault(round(c["origin"][1], 1), []).append((c, span["size"]))
            textos, larguras = [], set()
            for _y, chars in sorted(filas.items()):
                chars.sort(key=lambda par: par[0]["origin"][0])
                textos.append("".join(c["c"] for c, _ in chars))
                larguras.add(round((max(c["bbox"][2] for c, _ in chars)
                                    - min(c["bbox"][0] for c, _ in chars)) / chars[0][1], 2))
            assert textos == esperadas, familia
            assert larguras == {10.0}, familia
    finally:
        doc.close()


def test_no_docx_a_moldura_vem_no_texto_e_a_celula_fica_sem_borda(tmp_path):
    docx = pytest.importorskip("docx")
    caminho = exportar.para_docx([livro.PaginaExtraida(numero=0, blocos=[_figura(SKAK, "dupla")])],
                                 str(tmp_path / "a.docx"), diagramas="fonte", moldura="dupla", corpo_pt=16)
    documento = docx.Document(caminho)
    celula = documento.tables[0].cell(0, 0)
    assert [p.text for p in celula.paragraphs] == _figura(SKAK, "dupla").linhas
    with zipfile.ZipFile(caminho) as z:
        xml = z.read("word/document.xml").decode("utf-8")
        embutidas = [n for n in z.namelist() if n.startswith("word/fonts/")]
    assert 'w:val="nil"' in xml and "double" not in xml, "a célula desenhou uma segunda moldura"
    assert embutidas, "a SkakNew com a moldura não foi embutida"


# ----------------------------------------------------------------------
# O editor
# ----------------------------------------------------------------------

@pytest.mark.parametrize("fonte,moldura,cantos", COMBINACOES)
def test_o_editor_le_a_moldura_da_grade_e_a_escreve_igual(fonte, moldura, cantos):
    pagina = _ler(_epub(_figura(fonte, moldura, cantos)))["OEBPS/pagina-0001.xhtml"].decode("utf-8")
    cap = xhtml.ler(pagina.encode("utf-8"), "pagina-0001.xhtml")
    d = [b for b in cap.blocos if isinstance(b, m.Diagrama)][0]
    assert (d.moldura, d.cantos, d.coordenadas, d.estado) == (moldura, cantos, False, "ok"), d.aviso
    assert _pres(xhtml.escrever(cap)) == _pres(pagina)


@pytest.mark.parametrize("moldura,cantos,primeira", [("sem", "reto", " T + +l+"),
                                                      ("simples", "reto", "1222222223"),
                                                      ("dupla", "arredondado", 'A""""""""S')])
def test_o_livro_de_antes_guarda_a_moldura_da_folha(tmp_path, moldura, cantos, primeira):
    """
    O livro de antes da F122 tem o `div.diagrama caixa` com as oito linhas, e quem diz a
    moldura é a regra da folha. O que não tinha moldura continua sem; o que tinha a
    ganha da fonte.
    """
    antes = livro.Figura(b"", 1, 1, fen=FEN, origem="render", fonte=MERIDA,
                         linhas=rd.linhas(FEN, rd.carregar(MERIDA)))
    caminho = _epub(antes, pasta=str(tmp_path), moldura=moldura, cantos=cantos)
    aberto, _r = epub.ler(caminho)
    d = [b for c in aberto.capitulos for b in c.blocos if isinstance(b, m.Diagrama)][0]
    assert (d.moldura, d.cantos) == (moldura, cantos)
    regravado = str(tmp_path / "regravado.epub")
    epub.escrever(aberto, regravado)
    pre = _pres(_ler(regravado)["OEBPS/pagina-0001.xhtml"].decode("utf-8"))[0]
    assert pre[0] == primeira


def test_a_moldura_da_folha_e_lida_da_regra_da_caixa():
    assert dialeto.moldura_da_folha("div.diagrama.caixa {  }") == ("sem", "reto")
    assert dialeto.moldura_da_folha("div.diagrama.caixa { border: 0.06em solid #000; padding: 0.30em; }") \
        == ("simples", "reto")
    assert dialeto.moldura_da_folha("div.diagrama.caixa { border: 0.16em double #000; padding: 0.24em; "
                                    "border-radius: 0.40em; }") == ("dupla", "arredondado")
    assert dialeto.moldura_da_folha("p { margin: 0; }") is None


def test_o_livro_com_a_skaknew_de_2004_ganha_a_fonte_com_a_moldura(tmp_path):
    """
    O livro de antes embutiu a SkakNew sem moldura, com o mesmo nome de arquivo: ao
    gravar, o editor troca os bytes dela pelos da do projeto — senão o `@font-face` do
    livro continuaria desenhando o `[` e o `=` com uma fonte que não os tem. O PDF também.
    """
    fitz = pytest.importorskip("fitz")
    caminho = _epub(_figura(SKAK, "simples"), pasta=str(tmp_path))
    antigo = str(tmp_path / "antigo.epub")
    original = os.path.join(RAIZ, "fonts", "SkakNew-Diagram-original.otf")
    with zipfile.ZipFile(caminho) as z, zipfile.ZipFile(antigo, "w") as novo:
        for info in z.infolist():
            dados = z.read(info)
            if info.filename.endswith("SkakNew-Diagram.otf"):
                with open(original, "rb") as f:
                    dados = f.read()
            novo.writestr(info, dados)
    aberto, _r = epub.ler(antigo)
    assert fontes.desatualizada(epub.dados_de(aberto, aberto.recursos["fonts/SkakNew-Diagram.otf"]), SKAK)
    regravado = str(tmp_path / "regravado.epub")
    relatorio = epub.escrever(aberto, regravado)
    with open(os.path.join(RAIZ, "fonts", "SkakNew-Diagram.otf"), "rb") as f:
        assert _ler(regravado)["OEBPS/fonts/SkakNew-Diagram.otf"] == f.read()
    assert any("fonte de diagrama atualizada" in a for a in relatorio.avisos)

    pdf = str(tmp_path / "livro.pdf")
    pdf_io.escrever(epub.ler(antigo)[0], pdf, OpcoesDeConversao(modo_de_diagrama="fonte"))
    doc = fitz.open(pdf)
    try:
        texto = "".join(c["c"] for p in doc for b in p.get_text("rawdict")["blocks"]
                        for li in b.get("lines", []) for s in li["spans"] if "SkakNew" in s["font"]
                        for c in s["chars"])
    finally:
        doc.close()
    assert "[========]" in texto


def test_o_pipeline_do_livro_decide_a_moldura_como_o_texto(monkeypatch):
    """`livro.extrair_pagina` com moldura dupla na Merida: a figura já sai com a grade."""
    import test_f26_livro as t26

    monkeypatch.setattr(livro.diagrama, "ler", lambda img, caixa=None, **k: t26._leitura_firme())
    pagina = t26._pagina_com_diagrama(diagramas="render", fonte=MERIDA, moldura="dupla")
    figura = [b for b in pagina.blocos if isinstance(b, livro.Figura)][0]
    assert figura.linhas_emolduradas and figura.linhas[0] == '!""""""""#'
    sem = t26._pagina_com_diagrama(diagramas="render", fonte=MERIDA, moldura="sem")
    assert not [b for b in sem.blocos if isinstance(b, livro.Figura)][0].linhas_emolduradas


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
