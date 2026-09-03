"""
F111 — o arquivo julgado como arquivo.

Nenhum defeito desta fase é de reconhecimento: são os que o usuário vê **mesmo
quando o OCR acerta**, no Word e no leitor de EPUB. A tabela da fase tem doze
linhas, e cada teste abaixo é uma delas — mais os três que a F115 registrou.

**E o arquivo passa a ser aberto como arquivo.** Todo teste de exportação até
aqui conferia por substring, e a F59 já narrou o precedente: um `<Default>`
inserido fora do `<Types>` passou por todas as substrings e tinha deixado de
ser XML. Aqui cada parte XML dos dois formatos passa pelo `ElementTree`, e o
EPUB passa pelo `epubcheck` quando ele está instalado — é o critério de
"não regredir" que a fase pediu.

Rodar sem pytest:      python tests/test_f111_arquivo.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
import pytest

from core import exportar, livro
from core import render_diagrama as rd

FEN = "r1bqk2r/pp2bppp/2n1pn2/3p4/3P4/2N1PN2/PP2BPPP/R1BQK2R w - - 0 1"


def _figura(texto=True):
    png, largura, altura = rd.desenhar(FEN, lado_px=128)
    fonte = rd.carregar()
    if not texto:
        return livro.Figura(png, largura, altura, origem="recorte")
    return livro.Figura(png, largura, altura, fen=FEN, origem="render",
                        linhas=rd.linhas(FEN, fonte), fonte=fonte.nome)


def _livro():
    """Um livro pequeno com tudo o que a fase mede: capítulo, faixa, figura,
    tabela com figurina, prosa com negrito."""
    return [
        livro.PaginaExtraida(numero=0, blocos=[
            livro.Paragrafo("Chapter 1", titulo=True, nivel=1),
            livro.Paragrafo("Diagram 1-1", titulo=True),
            _figura(),
            livro.Paragrafo("A prosa da página, com 1.e4 em negrito.",
                            negrito=[(19, 23)]),
            livro.Tabela([["B♖h2", "W: Win (1 ♖e1!)"], ["W♔d1", "Draw"]]),
            livro.Paragrafo("Prosa depois da tabela."),
        ]),
        livro.PaginaExtraida(numero=1, blocos=[
            livro.Paragrafo("Prosa da segunda página."),
            _figura(texto=False),
        ]),
    ]


def _epub(paginas=None, **kw):
    tmp = tempfile.mkdtemp()
    return exportar.para_epub(paginas or _livro(), os.path.join(tmp, "l.epub"),
                              **kw)


def _docx(paginas=None, **kw):
    tmp = tempfile.mkdtemp()
    return exportar.para_docx(paginas or _livro(), os.path.join(tmp, "l.docx"),
                              **kw)


def _partes_xml(caminho):
    with zipfile.ZipFile(caminho) as z:
        for nome in z.namelist():
            if nome.endswith((".xml", ".xhtml", ".opf", ".rels")):
                yield nome, z.read(nome)


# ----------------------------------------------------------------------
# O arquivo como arquivo
# ----------------------------------------------------------------------

def test_toda_parte_xml_do_epub_e_xml():
    for nome, dados in _partes_xml(_epub(diagramas="fonte")):
        ET.fromstring(dados)


def test_toda_parte_xml_do_docx_e_xml():
    for nome, dados in _partes_xml(_docx(diagramas="fonte")):
        ET.fromstring(dados)


def _epubcheck():
    exe = shutil.which("epubcheck")
    if exe:
        return [exe]
    try:
        import epubcheck  # noqa: F401
        return [sys.executable, "-m", "epubcheck"]
    except ImportError:
        return None


@pytest.mark.skipif(_epubcheck() is None, reason="epubcheck não instalado")
def test_o_epubcheck_da_zero():
    """
    O critério de não regredir. O `epubcheck` já dava zero antes da fase, nos
    dois modos — e o que a fase acrescenta (`lang`, `id`, `schema:*`, URN) é
    exatamente o tipo de coisa que um validador de esquema reprova quando sai
    mal escrita.
    """
    caminho = _epub(diagramas="fonte")
    saida = subprocess.run(_epubcheck() + [caminho], capture_output=True,
                           text=True, timeout=180)
    # Conferido à mão: um EPUB sem `dc:language` devolve 1 e `RSC-005`.
    assert saida.returncode == 0, saida.stdout + saida.stderr


# ----------------------------------------------------------------------
# EPUB — a tabela da fase
# ----------------------------------------------------------------------

def _opf(caminho):
    return zipfile.ZipFile(caminho).read("OEBPS/content.opf").decode()


def test_o_identificador_e_uma_urn_por_livro():
    a = _opf(_epub(titulo="Livro A"))
    b = _opf(_epub(titulo="Livro B"))
    assert "pyboxeditor</dc:identifier>" not in a
    assert '<dc:identifier id="pub-id">urn:uuid:' in a
    marca = '<dc:identifier id="pub-id">'
    assert a.split(marca)[1][:50] != b.split(marca)[1][:50]
    # E o mesmo livro exportado de novo mantém a identidade.
    assert exportar.identificador_de("Livro A") == exportar.identificador_de("Livro A")


def test_a_data_de_modificacao_e_a_de_hoje_ou_a_reprodutivel(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert "2023-11-14T22:13:20Z" in _opf(_epub())
    monkeypatch.delenv("SOURCE_DATE_EPOCH")
    assert "2026-01-01T00:00:00Z" not in _opf(_epub())


def test_o_lang_esta_no_html_e_no_nav():
    z = zipfile.ZipFile(_epub(idioma="pt"))
    assert 'lang="pt" xml:lang="pt"' in z.read("OEBPS/pagina-0001.xhtml").decode()
    assert 'lang="pt"' in z.read("OEBPS/nav.xhtml").decode()


def test_o_capitulo_sai_h1_com_ancora_e_o_nav_o_lista():
    z = zipfile.ZipFile(_epub())
    pagina = z.read("OEBPS/pagina-0001.xhtml").decode()
    assert '<h1 id="t1-1">Chapter 1</h1>' in pagina
    assert '<h2 id="t1-2">Diagram 1-1</h2>' in pagina
    nav = z.read("OEBPS/nav.xhtml").decode()
    assert '<a href="pagina-0001.xhtml#t1-1">Chapter 1</a>' in nav
    assert "Página 1" not in nav, "com capítulo, o sumário não lista página"


def test_sem_capitulo_o_nav_cai_para_as_paginas():
    paginas = [livro.PaginaExtraida(numero=0, blocos=[livro.Paragrafo("a")]),
               livro.PaginaExtraida(numero=1, blocos=[livro.Paragrafo("b")])]
    nav = zipfile.ZipFile(_epub(paginas)).read("OEBPS/nav.xhtml").decode()
    assert "Página 1" in nav and "Página 2" in nav


def test_os_metadados_de_acessibilidade_estao_no_opf():
    opf = _opf(_epub())
    for propriedade in ("schema:accessMode", "schema:accessModeSufficient",
                        "schema:accessibilityFeature",
                        "schema:accessibilityHazard",
                        "schema:accessibilitySummary"):
        assert f'property="{propriedade}"' in opf, propriedade
    assert ">visual</meta>" in opf, "há figura, e o modo visual é declarado"


def test_as_linhas_do_diagrama_saem_escapadas():
    f = _figura()
    f.linhas = ["<&>" + linha[3:] for linha in f.linhas]
    paginas = [livro.PaginaExtraida(numero=0, blocos=[f])]
    pagina = zipfile.ZipFile(_epub(paginas, diagramas="fonte")).read(
        "OEBPS/pagina-0001.xhtml").decode()
    assert "<p>&lt;&amp;&gt;" in pagina
    ET.fromstring(pagina.encode("utf-8"))


def test_trechos_ordena_o_negrito_na_entrada():
    assert exportar.trechos("abcdefghijklmnop", [(10, 15), (2, 5)]) == [
        ("ab", False), ("cde", True), ("fghij", False), ("klmno", True),
        ("p", False)]


def test_o_simbolo_que_nenhuma_fonte_desenha_e_dito():
    assert exportar.simbolos_sem_fonte("Prosa com ♔ e 1.e4") == ""
    # O ideograma não está em fonte de símbolo nenhuma; a figurina, que está, some.
    assert exportar.simbolos_sem_fonte("♔ \u4e2d") == "\u4e2d"


# ----------------------------------------------------------------------
# DOCX — a tabela da fase
# ----------------------------------------------------------------------

def _parte(caminho, nome):
    return zipfile.ZipFile(caminho).read(nome).decode("utf-8")


def test_o_docx_e_do_livro_e_nao_da_biblioteca(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    caminho = _docx(titulo="Livro", autor="Autora")
    core = _parte(caminho, "docProps/core.xml")
    assert "python-docx" not in core
    assert "<dc:creator>Autora</dc:creator>" in core
    assert "2013-12-23" not in core and "2023-11-14" in core
    assert "docProps/thumbnail.jpeg" not in zipfile.ZipFile(caminho).namelist()
    assert "thumbnail" not in _parte(caminho, "_rels/.rels")


def test_sem_autor_o_criador_fica_vazio():
    core = _parte(_docx(autor=""), "docProps/core.xml")
    assert "python-docx" not in core


def test_a_figurina_na_celula_leva_a_fonte():
    from docx import Document

    doc = Document(_docx())
    celula = doc.tables[-1].cell(0, 0)
    runs = celula.paragraphs[0].runs
    com_fonte = [r for r in runs if "♖" in r.text]
    assert com_fonte and com_fonte[0].font.name, "a figurina saía na Calibri"


def test_o_diagrama_em_fonte_tem_texto_alternativo():
    documento = _parte(_docx(diagramas="fonte"), "word/document.xml")
    assert 'w:tblCaption w:val="Diagrama"' in documento
    assert f'w:tblDescription w:val="{FEN}"' in documento


def test_o_fen_chega_ao_descr_da_figura_desenhada():
    """
    A tabela da fase dizia "nenhum FEN chega ao `descr`", e a causa não era
    de código: os 151 do livro medido eram recortes, e o recorte não tem
    posição lida. A figura desenhada leva o FEN, e o recorte leva o rótulo.
    """
    documento = _parte(_docx(), "word/document.xml")
    assert f'descr="{FEN}"' in documento
    assert 'descr="Diagrama"' in documento


def test_a_tabela_e_seguida_do_separador():
    """Tabela seguida de diagrama em modo de fonte saía fundida no Word."""
    from docx import Document

    paginas = [livro.PaginaExtraida(numero=0, blocos=[
        livro.Tabela([["a", "b"]]), _figura()])]
    doc = Document(_docx(paginas, diagramas="fonte"))
    corpo = doc.element.body
    filhos = [c.tag.split("}")[1] for c in corpo]
    assert filhos[:4] == ["tbl", "p", "tbl", "p"], filhos


def test_o_capitulo_sai_heading_1_e_a_faixa_heading_2():
    from docx import Document

    doc = Document(_docx())
    estilos = [p.style.name for p in doc.paragraphs]
    assert "Heading 1" in estilos and "Heading 2" in estilos


def test_o_desenho_de_pagina_e_de_livro():
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document(_docx())
    normal = doc.styles["Normal"]
    assert normal.paragraph_format.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY
    assert normal.paragraph_format.first_line_indent.pt > 0
    assert normal.font.name == exportar.FONTE_DO_TEXTO
    assert round(doc.sections[0].left_margin.cm, 1) == exportar.MARGEM_DA_PAGINA_CM
    assert 'w:lang w:val="en"' in _parte(_docx(), "word/styles.xml")


def test_o_primeiro_paragrafo_depois_da_figura_sai_sem_recuo():
    from docx import Document

    doc = Document(_docx())
    depois = [p for p in doc.paragraphs if p.text.startswith("A prosa da página")]
    assert depois and depois[0].paragraph_format.first_line_indent.pt == 0


# ----------------------------------------------------------------------
# O título de capítulo pela altura, e o título e autor do arquivo
# ----------------------------------------------------------------------

def _linha(texto, topo, altura, esquerda=100):
    return livro.Linha(topo=topo, esquerda=esquerda, altura=altura, texto=texto)


@pytest.fixture
def com_capitulos(monkeypatch):
    """A régua está desligada em produção (ver `livro.DETECTAR_CAPITULOS`);
    o que se testa é a régua, ligada."""
    monkeypatch.setattr(livro, "DETECTAR_CAPITULOS", True)


def test_a_deteccao_de_capitulo_esta_desligada_em_producao():
    linhas = [_linha("Chapter 3", 100, 40),
              _linha("A prosa que segue, com muitas palavras.", 200, 20),
              _linha("E mais prosa depois da primeira.", 260, 20)]
    assert not livro._agrupar_em_paragrafos(linhas)[0].titulo


def test_a_linha_alta_e_curta_e_capitulo(com_capitulos):
    linhas = [_linha("Chapter 3", 100, 40),
              _linha("A prosa que segue, com muitas palavras.", 200, 20),
              _linha("E mais prosa depois da primeira.", 260, 20),
              _linha("E ainda outra linha de prosa comum.", 320, 20)]
    paragrafos = livro._agrupar_em_paragrafos(linhas)
    assert paragrafos[0].titulo and paragrafos[0].nivel == 1
    assert not paragrafos[1].titulo


def test_a_linha_alta_com_lance_ou_longa_nao_e_capitulo(com_capitulos):
    for texto in ("1.e4 c5 2.♘f3", "uma linha comprida de prosa em corpo "
                                   "maior com mais de oito palavras nela"):
        linhas = [_linha(texto, 100, 40),
                  _linha("prosa", 200, 20), _linha("prosa", 260, 20),
                  _linha("prosa", 320, 20)]
        assert not livro._agrupar_em_paragrafos(linhas)[0].titulo, texto


def test_a_linha_alta_de_numero_ou_de_simbolo_nao_e_capitulo(com_capitulos):
    """O número de página em corpo grande, e o pedaço de diagrama."""
    for texto in ("35", "1 7", "gH♗", "S ."):
        linhas = [_linha(texto, 100, 40),
                  _linha("prosa", 200, 20), _linha("prosa", 260, 20),
                  _linha("prosa", 320, 20)]
        assert not livro._agrupar_em_paragrafos(linhas)[0].titulo, texto


def test_o_titulo_abaixo_do_terco_de_cima_volta_a_ser_paragrafo():
    """A caixa de pontuação dos exercícios é prosa em corpo maior no pé da
    página, e não capítulo."""
    pagina = livro.PaginaExtraida(numero=0, altura=1000, blocos=[
        livro.Paragrafo("Solutions", titulo=True, nivel=1, topo=100),
        livro.Paragrafo("If you scored less", titulo=True, nivel=1, topo=800)])
    livro._confirmar_titulos(pagina)
    assert pagina.blocos[0].titulo and pagina.blocos[0].nivel == 1
    assert not pagina.blocos[1].titulo and pagina.blocos[1].nivel == 2


def test_a_faixa_do_diagrama_continua_nivel_2():
    assert livro.Paragrafo("Diagram 1-1", titulo=True).nivel == 2


def _pdf(tmp, nome, titulo="", autor=""):
    caminho = os.path.join(tmp, nome)
    doc = fitz.open()
    doc.new_page()
    doc.set_metadata({"title": titulo, "author": autor})
    doc.save(caminho)
    doc.close()
    return caminho


def test_o_titulo_e_o_autor_vem_do_pdf_ou_do_nome():
    with tempfile.TemporaryDirectory() as tmp:
        assert livro.titulo_e_autor(_pdf(tmp, "x.pdf", "Xadrez", "Yasser S.")) \
            == ("Xadrez", "Yasser S.")
        assert livro.titulo_e_autor(_pdf(tmp, "Nunn - Secrets of Rook Endings.pdf")) \
            == ("Secrets of Rook Endings", "Nunn")
        assert livro.titulo_e_autor(_pdf(tmp, "Yusupov_Complete.pdf")) \
            == ("Yusupov_Complete", "")
        # `cipun` não é nome de ninguém.
        assert livro.titulo_e_autor(_pdf(tmp, "Nunn - Rook.pdf", "", "cipun")) \
            == ("Rook", "Nunn")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
