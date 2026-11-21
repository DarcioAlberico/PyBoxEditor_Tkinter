"""Texto legal em XML na fronteira dos escritores (RG-04, R-07).

O EPUB do OCR gravava `"linha\\x0c fim"` e o XHTML saía mal formado; o `python-docx`
levantava `All strings must be XML compatible` e a exportação inteira caía; o editor fazia o
mesmo, e um `\\ud800` solto levantava `UnicodeEncodeError`. A entrada desses caracteres não
foi vista no OCR (que usa `image_to_data`); as portas são a camada do PDF e o TXT, HTML e
DOCX importados — a defesa fica na fronteira, onde o texto vira nó XML, nunca antes do
cálculo das faixas de negrito e itálico, que ficariam deslocadas. E o TXT em UTF-16 era lido
como Windows-1252.
"""

import logging
import zipfile
import xml.etree.ElementTree as ET

from core.texto_legal import texto_legal_em_xml


def test_tira_so_o_que_o_xml_nao_aceita(caplog):
    with caplog.at_level(logging.WARNING):
        assert texto_legal_em_xml("a\x0cb\x00c\x0b\ud800d￿e\tf\ng\rh", "teste-1") == "abcde\tf\ng\rh"
    assert any("5" in r.getMessage() and "teste-1" in r.getMessage() for r in caplog.records)
    assert texto_legal_em_xml("1.e4 ♘f6 — ½", "teste-2") == "1.e4 ♘f6 — ½"


def _paginas(texto, negrito=()):
    from core import livro
    return [livro.PaginaExtraida(numero=0, blocos=[livro.Paragrafo(texto, negrito=list(negrito))])]


def test_o_epub_do_ocr_sai_bem_formado_e_o_negrito_no_lugar(tmp_path):
    from core import exportar
    caminho = tmp_path / "o.epub"
    exportar.para_epub(_paginas("linha\x0c fim", negrito=[(7, 10)]), str(caminho))
    with zipfile.ZipFile(caminho) as z:
        paginas = [n for n in z.namelist() if n.endswith(".xhtml") and "nav" not in n]
        texto = z.read(paginas[0]).decode("utf-8")
    raiz = ET.fromstring(texto)
    assert "\x0c" not in texto and "linha fim" in "".join(raiz.itertext())
    assert "<strong>fim</strong>" in texto or "<b>fim</b>" in texto


def test_o_docx_do_ocr_grava_e_o_negrito_no_lugar(tmp_path):
    import docx

    from core import exportar
    caminho = tmp_path / "o.docx"
    exportar.para_docx(_paginas("linha\x0c fim", negrito=[(7, 10)]), str(caminho))
    paragrafos = [p for p in docx.Document(str(caminho)).paragraphs if "linha" in p.text]
    assert paragrafos and paragrafos[0].text == "linha fim"
    assert [r.text for r in paragrafos[0].runs if r.bold] == ["fim"]


def test_o_editor_salva_epub_legivel_com_controle_e_surrogate(tmp_path):
    from core.editor import epub, modelo as m, xhtml
    livro = m.Livro(metadados=m.Metadados(titulo="T", idioma="pt", identificador="urn:uuid:t"),
                    capitulos=[m.Capitulo(arquivo="Text/c.xhtml", blocos=[
        m.Paragrafo(trechos=[m.Trecho(texto="um\x0cdois\ud800três")])])])
    caminho = tmp_path / "e.epub"
    epub.escrever(livro, str(caminho))
    with zipfile.ZipFile(caminho) as z:
        nome = next(n for n in z.namelist() if n.endswith("c.xhtml"))
        dados = z.read(nome)
    cap = xhtml.ler(dados, "Text/c.xhtml")
    assert cap.blocos[0].trechos[0].texto == "umdoistrês"


def test_txt_em_utf16_importa_legivel(tmp_path):
    from core.editor import txt_io
    caminho = tmp_path / "t.txt"
    caminho.write_bytes(b"\xff\xfe" + "Xadrez básico\n\nTexto em UTF-16.".encode("utf-16-le"))
    livro, _relatorio = txt_io.ler(str(caminho))
    textos = [t.texto for c in livro.capitulos for b in c.blocos for t in getattr(b, "trechos", [])]
    assert "Xadrez básico" in textos and not any("\x00" in t for t in textos)
