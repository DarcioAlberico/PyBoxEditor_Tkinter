"""
A exportação do documento editorial (Fase 6). Desde a PD-21 (2026-10-10) o EPUB e
o DOCX do IR saem do escritor de produção (`core/exportar.py`), e os testes
conferem a semântica dele; HTML, TXT e PDF pesquisável continuam do IR.
"""

from __future__ import annotations

import zipfile

import fitz
import pytest

from core.editorial_model import Decision, EditorialBlock, EditorialDocument, EditorialPage, Evidence, SourceRef
from core.editorial_export import EditorialExporter, ExportOptions


def _document(tmp_path=None) -> EditorialDocument:
    ref = SourceRef("book", 0, (10, 20, 180, 100), "hash", "raster")
    evidence = Evidence("ev", ref, observed_text="Livro", confidence=.9)
    blocks = [
        EditorialBlock("h", "heading", 0, [ref], Decision("Capítulo 1", ["ev"], "reviewed")),
        EditorialBlock("p", "paragraph", 1, [ref], Decision("Texto editorial", ["ev"], "reviewed")),
        EditorialBlock("n", "chess_sequence", 2, [ref], Decision("1. e4 e5", ["ev"], "reviewed")),
        EditorialBlock("d", "diagram", 3, [ref], Decision(
            {"fen": "8/8/8/8/8/8/8/4K2k w - - 0 1", "review_status": "reviewed"},
            ["ev"], "reviewed")),
    ]
    return EditorialDocument("book", "Livro de xadrez", "pt", [
        EditorialPage("book-p0001", 0, [ref], blocks, [evidence])
    ], pipeline_version="v4")


def test_html_semantico_preserva_ordem_fen_alt_e_modo(tmp_path):
    destino = tmp_path / "livro.html"
    report = EditorialExporter().export(
        _document(), destino, ExportOptions(format="html", mode="hybrid"))
    html = destino.read_text(encoding="utf-8")

    assert report.format == "html"
    assert '<html lang="pt">' in html
    assert 'data-fen="8/8/8/8/8/8/8/4K2k w - - 0 1"' in html
    assert 'aria-label="Sequência de xadrez"' in html
    assert "Texto editorial" in html
    assert "hybrid" in html


def test_o_epub_sai_do_escritor_de_producao_com_mimetype_nav_css_e_os_blocos(tmp_path):
    """
    O EPUB do IR é o do `exportar.py` (PD-21): o `mimetype` primeiro e sem
    compressão, o `content.opf`, o `nav.xhtml` e o `estilo.css`, uma página por
    arquivo XHTML, o diagrama desenhado do FEN como PNG no zip — e não o
    `content.xhtml` único com a imagem em base64 que o escritor do IR fazia.
    """
    destino = tmp_path / "livro.epub"
    report = EditorialExporter().export(_document(), destino, ExportOptions(format="epub"))

    assert report.files == (str(destino),)
    assert report.metadata["escritor"] == "exportar" and report.metadata["paginas"] == "ir"
    with zipfile.ZipFile(destino) as arquivo:
        nomes = arquivo.namelist()
        assert nomes[0] == "mimetype"
        assert arquivo.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        assert arquivo.read("mimetype") == b"application/epub+zip"
        assert {"OEBPS/content.opf", "OEBPS/nav.xhtml", "OEBPS/estilo.css",
                "OEBPS/imagens/fig-0001-1.png"} <= set(nomes)
        assert "OEBPS/content.xhtml" not in nomes
        xhtml = arquivo.read("OEBPS/pagina-0001.xhtml").decode("utf-8")
    assert (xhtml.index("Capítulo 1") < xhtml.index("Texto editorial")
            < xhtml.index("1. e4 e5") < xhtml.index("<figure>"))
    assert 'alt="8/8/8/8/8/8/8/4K2k w - - 0 1 — brancas a jogar (assumido: a página não diz)"' in xhtml
    assert "não revisado" not in xhtml, "o diagrama revisado não leva ressalva"


def test_docx_mapeia_heading_notacao_e_diagrama(tmp_path):
    """O DOCX também é o de produção: o título em estilo de título, o lance no
    texto, o diagrama como figura com o FEN no texto alternativo (`descr`), que
    é onde o leitor de tela o lê e a busca do Word o acha."""
    pytest.importorskip("docx")
    destino = tmp_path / "livro.docx"
    EditorialExporter().export(_document(), destino, ExportOptions(format="docx"))
    from docx import Document
    doc = Document(destino)
    texto = "\n".join(par.text for par in doc.paragraphs)
    assert "Capítulo 1" in texto
    assert "1. e4 e5" in texto
    assert doc.paragraphs[0].style.name.startswith("Heading")
    [forma] = doc.inline_shapes
    assert "4K2k" in forma._inline.docPr.get("descr")
    assert "não revisado" not in texto


def test_pdf_semantico_e_pesquisavel_tem_relatorio_de_itens(tmp_path):
    destino = tmp_path / "livro.pdf"
    report = EditorialExporter().export(_document(), destino, ExportOptions(format="pdf"))
    assert report.metadata["text_items"] >= 3
    documento = fitz.open(destino)
    texto = documento[0].get_text()
    documento.close()
    assert "Texto editorial" in texto and "1. e4 e5" in texto


def test_modo_invalido_e_formato_invalido_sao_rejeitados():
    with pytest.raises(ValueError):
        ExportOptions(format="epub", mode="inexistente")
    with pytest.raises(ValueError):
        ExportOptions(format="xlsx")
