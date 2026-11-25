"""Tabela irregular, tabela vazia, título e idioma vazios (RG-17, R-33)."""

import zipfile

import pytest

from core import exportar, livro
from core.editorial_adapters import paginas_extraidas_para_documento
from core.editorial_export import EditorialExporter, ExportOptions


def _pagina(*blocos):
    return livro.PaginaExtraida(numero=0, blocos=list(blocos), largura=1000, altura=1400, dpi=200)


def _docx(tmp_path, *blocos, **kw):
    docx = pytest.importorskip("docx")
    exportar.para_docx([_pagina(*blocos)], str(tmp_path / "l.docx"), **kw)
    return docx.Document(str(tmp_path / "l.docx"))


def _epub(tmp_path, *blocos, **kw):
    exportar.para_epub([_pagina(*blocos)], str(tmp_path / "l.epub"), **kw)
    with zipfile.ZipFile(tmp_path / "l.epub") as z:
        return {n: z.read(n).decode("utf-8") for n in z.namelist() if n.endswith((".xhtml", ".opf"))}


IRREGULAR = [["W", "Win"], ["B", "Draw", "com lance"], ["só uma"]]
COMPLETA = [["W", "Win", ""], ["B", "Draw", "com lance"], ["só uma", "", ""]]


def test_a_tabela_irregular_nao_perde_celula_no_docx(tmp_path):
    [tabela] = _docx(tmp_path, livro.Tabela([list(f) for f in IRREGULAR])).tables
    assert [[c.text for c in fila.cells] for fila in tabela.rows] == COMPLETA


def test_a_tabela_irregular_sai_retangular_no_epub(tmp_path):
    xhtml = _epub(tmp_path, livro.Tabela([list(f) for f in IRREGULAR]))["OEBPS/pagina-0001.xhtml"]
    filas = xhtml.split("<tr>")[1:]
    assert [fila.count("<td>") for fila in filas] == [3, 3, 3] and "com lance" in xhtml


@pytest.mark.parametrize("linhas", [[], [[]], [[], []]])
def test_a_tabela_vazia_e_pulada(tmp_path, linhas):
    blocos = (livro.Paragrafo("Antes."), livro.Tabela(linhas), livro.Paragrafo("Depois."))
    doc = _docx(tmp_path, *blocos)
    assert not doc.tables and "Depois." in [p.text for p in doc.paragraphs]
    xhtml = _epub(tmp_path, *blocos)["OEBPS/pagina-0001.xhtml"]
    assert "<table>" not in xhtml and "Depois." in xhtml


@pytest.mark.parametrize("vazio", ["", "   ", None])
def test_o_titulo_e_o_idioma_vazios_tem_padrao(tmp_path, vazio):
    opf = _epub(tmp_path, livro.Paragrafo("x"), titulo=vazio, idioma=vazio)["OEBPS/content.opf"]
    assert f"<dc:title>{exportar.TITULO_PADRAO}</dc:title>" in opf
    assert f"<dc:language>{exportar.IDIOMA_PADRAO}</dc:language>" in opf
    xhtml = _epub(tmp_path, livro.Paragrafo("x"), idioma=vazio)["OEBPS/pagina-0001.xhtml"]
    assert 'lang=""' not in xhtml
    doc = _docx(tmp_path, livro.Paragrafo("x"), titulo=vazio, idioma=vazio)
    assert doc.core_properties.title == exportar.TITULO_PADRAO


def test_o_documento_sem_titulo_nem_idioma_exporta_com_os_dois(tmp_path):
    documento = paginas_extraidas_para_documento([_pagina(livro.Paragrafo("x"))],
                                                 document_id="livro", title="", language="")
    EditorialExporter().export(documento, tmp_path / "l.epub", ExportOptions(format="epub"))
    with zipfile.ZipFile(tmp_path / "l.epub") as z:
        opf = z.read("OEBPS/content.opf").decode("utf-8")
    assert f"<dc:title>{exportar.TITULO_PADRAO}</dc:title>" in opf
    assert "<dc:language></dc:language>" not in opf
    EditorialExporter().export(documento, tmp_path / "l.html", ExportOptions(format="html"))
    pagina = (tmp_path / "l.html").read_text(encoding="utf-8")
    assert f"<title>{exportar.TITULO_PADRAO}</title>" in pagina and '<html lang="und">' in pagina


def test_o_titulo_do_documento_vale_quando_o_pdf_nao_tem(tmp_path, monkeypatch):
    documento = paginas_extraidas_para_documento([_pagina(livro.Paragrafo("x"))],
                                                 document_id="livro", title="Do documento")
    documento.metadata["source_path"] = "origem.pdf"
    monkeypatch.setattr(livro, "titulo_e_autor", lambda caminho: ("", "Autora"))
    EditorialExporter().export(documento, tmp_path / "l.epub", ExportOptions(format="epub"))
    with zipfile.ZipFile(tmp_path / "l.epub") as z:
        opf = z.read("OEBPS/content.opf").decode("utf-8")
    assert "<dc:title>Do documento</dc:title>" in opf and "Autora" in opf
