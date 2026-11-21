"""Nenhum caminho vindo de pacote ou de HTML importado sai da raiz dele (RG-04, R-05; invariante 18).

`escrever_pasta` gravava cada arquivo em `pasta/<href>`, com o `href` relativo ao OPF: um
EPUB com a entrada `../../ESCAPOU.txt` gravou fora da pasta escolhida, e um EPUB legítimo
com o OPF em `OEBPS/opf/` e os capítulos em `../Text/` também escapava. A leitura do zip
regravava entradas `..` e absolutas no EPUB salvo. E `_trazer_do_disco` embutia qualquer
arquivo legível que um HTML importado apontasse.

Agora `core.caminho_seguro` recusa o que sai da raiz, o caminho absoluto, o UNC e a letra de
unidade; a pasta HTML grava pelo nome da entrada no zip relativo à raiz comum do livro (o
leiaute de sempre no caso comum); a leitura do zip recusa a entrada que sai da raiz do
pacote; e a importação de HTML aceita relativo de qualquer profundidade, mas só embute
extensão de recurso, e nunca caminho absoluto.
"""

import os
import zipfile
from pathlib import Path

import pytest

from core import caminho_seguro as cs
from core.editor import epub, html_io

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8cfc0f01f0005000"
    "1ff0aa5f0e50000000049454e44ae426082")

CAP = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml"><head>'
       '<title>c</title></head><body><h1 id="t">Capítulo</h1><p>Texto.</p></body></html>')


def _epub(pasta: Path, opf: str, cap_href: str, extras: dict[str, bytes] | None = None) -> str:
    """Um EPUB mínimo com o OPF em `opf` e um capítulo em `cap_href` (relativo ao OPF)."""
    caminho = pasta / "livro.epub"
    nome_do_cap = os.path.normpath(os.path.join(os.path.dirname(opf), cap_href)).replace("\\", "/")
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" '
                   'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                   f'<rootfile full-path="{opf}" media-type="application/oebps-package+xml"/>'
                   "</rootfiles></container>")
        z.writestr(opf, '<?xml version="1.0" encoding="utf-8"?>'
                   '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
                   '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">x</dc:identifier>'
                   '<dc:title>T</dc:title><dc:language>pt</dc:language></metadata>'
                   f'<manifest><item id="c" href="{cap_href}" media-type="application/xhtml+xml"/></manifest>'
                   '<spine><itemref idref="c"/></spine></package>')
        z.writestr(nome_do_cap, CAP)
        for nome, dados in (extras or {}).items():
            z.writestr(nome, dados)
    return str(caminho)


def _arquivos_fora(raiz: Path, dentro: Path) -> list[str]:
    dentro = dentro.resolve()
    return sorted(str(p) for p in raiz.rglob("*")
                  if p.is_file() and dentro not in p.resolve().parents and p.suffix != ".epub")


@pytest.mark.parametrize("relativo", ["../x", "a/../../x", "/abs", "\\abs", "C:/x", "c:x",
                                      "\\\\servidor\\pasta\\x", "//servidor/x"])
def test_recusa_o_que_sai_da_raiz(tmp_path, relativo):
    assert not cs.e_relativo_seguro(relativo)
    with pytest.raises(cs.CaminhoInseguro):
        cs.caminho_seguro(tmp_path, relativo)


@pytest.mark.parametrize("relativo", ["a.txt", "a/b/c.png", "a/../b.css", "./x"])
def test_aceita_o_que_fica_dentro(tmp_path, relativo):
    assert cs.e_relativo_seguro(relativo)
    assert tmp_path.resolve() in cs.caminho_seguro(tmp_path, relativo).resolve().parents


def test_entrada_que_escapa_nao_sai_da_pasta_html(tmp_path):
    origem = _epub(tmp_path, "OEBPS/content.opf", "Text/c.xhtml", {"../../ESCAPOU.txt": b"fora"})
    livro, relatorio = epub.ler(origem)
    assert any("ESCAPOU" in a for a in relatorio.avisos)
    saida = tmp_path / "out" / "a" / "b" / "saida"
    html_io.escrever_pasta(livro, str(saida))
    assert _arquivos_fora(tmp_path, saida) == []


def test_epub_legitimo_com_text_ao_lado_do_opf_exporta_dentro_da_pasta(tmp_path):
    origem = _epub(tmp_path, "OEBPS/opf/content.opf", "../Text/c.xhtml")
    livro, _relatorio = epub.ler(origem)
    saida = tmp_path / "saida"
    html_io.escrever_pasta(livro, str(saida))
    assert _arquivos_fora(tmp_path, saida) == []
    assert (saida / "Text" / "c.html").is_file()
    assert 'href="Text/c.html' in (saida / "index.html").read_text(encoding="utf-8")


def test_entrada_ponto_ponto_no_zip_nao_volta_no_epub_salvo(tmp_path):
    origem = _epub(tmp_path, "OEBPS/content.opf", "Text/c.xhtml", {"../sobra.txt": b"x", "/abs.txt": b"y"})
    livro, _relatorio = epub.ler(origem)
    novo = tmp_path / "novo.epub"
    epub.escrever(livro, str(novo))
    with zipfile.ZipFile(novo) as z:
        assert [n for n in z.namelist() if not cs.e_relativo_seguro(n)] == []


def test_html_importado_so_embute_recurso_e_nunca_caminho_absoluto(tmp_path):
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "a.png").write_bytes(PNG)
    (tmp_path / "x.txt").write_text("segredo", encoding="utf-8")
    segredo = tmp_path / "segredo.png"
    segredo.write_bytes(PNG)
    pasta = tmp_path / "livro" / "sub"
    pasta.mkdir(parents=True)
    html = pasta / "doc.html"
    html.write_text('<html><body><p>a</p><img src="../../img/a.png" alt="a">'
                    '<img src="../../x.txt" alt="b">'
                    f'<img src="{segredo}" alt="c"></body></html>', encoding="utf-8")
    livro, relatorio = html_io.ler(str(html))
    embutidos = {r.caminho: r for r in livro.recursos.values() if r.dados}
    assert any(c.endswith("a.png") for c in embutidos)
    assert not any(c.endswith(".txt") for c in embutidos)
    assert not any(r.dados == PNG and c.endswith("segredo.png") for c, r in embutidos.items())
