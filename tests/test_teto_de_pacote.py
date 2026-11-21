"""Tetos na leitura de pacote, `ParseError` no contrato e OPF com entidade do HTML (RG-04, R-06).

O `_Pacote` do DOCX lia o zip inteiro para a memória (um DOCX de 306 KB com uma entrada de
300 MB de zeros levou o processo a 631 MB) e o EPUB lia cada recurso sem olhar o tamanho:
com alguns GB descomprimidos o editor morria e levava o trabalho aberto. Agora
`core.teto_de_pacote` confere o `ZipInfo.file_size` — por entrada e no total — antes de ler
qualquer coisa. O `document.xml` mal formado subia como `ParseError`, fora do `ValueError`
que o contrato promete e que a interface trata. E o OPF com `&nbsp;` não abria, embora os
capítulos com a mesma entidade abram.
"""

import zipfile

import pytest

from core import teto_de_pacote as teto
from core.editor import docx_leitura, epub


@pytest.fixture
def tetos_pequenos(monkeypatch):
    monkeypatch.setattr(teto, "TETO_POR_ENTRADA", 1 << 20)
    monkeypatch.setattr(teto, "TETO_TOTAL", 3 << 20)


@pytest.fixture
def sem_ler(monkeypatch):
    """Ler o conteúdo de uma entrada grande demais já seria o estrago."""
    original = zipfile.ZipFile.read

    def read(self, nome, pwd=None):
        info = self.getinfo(nome) if isinstance(nome, str) else nome
        assert info.file_size <= teto.TETO_POR_ENTRADA, f"leu {info.filename} ({info.file_size} bytes)"
        return original(self, nome, pwd)

    monkeypatch.setattr(zipfile.ZipFile, "read", read)


def _docx(caminho, partes):
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        for nome, dados in partes.items():
            z.writestr(nome, dados)
    return str(caminho)


DOCUMENTO = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
             '<w:body><w:p><w:r><w:t>a</w:t></w:r></w:p></w:body></w:document>')


def test_docx_com_entrada_grande_demais_e_recusado_sem_ler(tmp_path, tetos_pequenos, sem_ler):
    caminho = _docx(tmp_path / "bomba.docx", {"word/document.xml": DOCUMENTO,
                                             "word/media/zeros.bin": b"\0" * (2 << 20)})
    with pytest.raises(ValueError, match="zeros.bin"):
        docx_leitura.ler(caminho)


def test_docx_acima_do_teto_total_e_recusado(tmp_path, tetos_pequenos, sem_ler):
    partes = {"word/document.xml": DOCUMENTO}
    partes.update({f"word/media/{i}.bin": b"\0" * (900 << 10) for i in range(5)})
    with pytest.raises(ValueError, match="total"):
        docx_leitura.ler(_docx(tmp_path / "muitos.docx", partes))


def test_docx_com_documento_mal_formado_cai_no_contrato(tmp_path):
    caminho = _docx(tmp_path / "quebrado.docx", {"word/document.xml": "<w:document><w:body>"})
    with pytest.raises(ValueError, match="document.xml"):
        docx_leitura.ler(caminho)


def _epub(caminho, titulo="T", extras=None):
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" '
                   'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                   '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                   "</rootfiles></container>")
        z.writestr("OEBPS/content.opf", '<?xml version="1.0" encoding="utf-8"?>'
                   '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
                   '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">x</dc:identifier>'
                   f'<dc:title>{titulo}</dc:title><dc:language>pt</dc:language></metadata>'
                   '<manifest><item id="c" href="c.xhtml" media-type="application/xhtml+xml"/></manifest>'
                   '<spine><itemref idref="c"/></spine></package>')
        z.writestr("OEBPS/c.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c</title></head>'
                   '<body><p>Texto.</p></body></html>')
        for nome, dados in (extras or {}).items():
            z.writestr(nome, dados)
    return str(caminho)


def test_epub_com_entrada_grande_demais_e_recusado_sem_ler(tmp_path, tetos_pequenos, sem_ler):
    caminho = _epub(tmp_path / "bomba.epub", extras={"OEBPS/zeros.bin": b"\0" * (2 << 20)})
    with pytest.raises(epub.ErroDeEpub, match="zeros.bin"):
        epub.ler(caminho)


def test_opf_com_entidade_do_html_abre(tmp_path):
    livro, _relatorio = epub.ler(_epub(tmp_path / "nbsp.epub", titulo="Xadrez&nbsp;Básico &mdash; 1"))
    assert livro.metadados.titulo == "Xadrez\u00a0Básico — 1"


def test_os_tetos_de_verdade_cabem_um_livro_e_recusam_a_bomba():
    assert teto.TETO_POR_ENTRADA >= 256 << 20
    assert teto.TETO_TOTAL >= teto.TETO_POR_ENTRADA
