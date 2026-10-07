"""
O EPUB e o DOCX saem com os mesmos bytes quando o instante é o mesmo.

O `test_o_epub_do_round_trip_e_byte_identico` (`test_adapter_sem_perdas.py`)
caía às vezes com a máquina carregada e passava rodado de novo. O
`SOURCE_DATE_EPOCH` fixava o `dcterms:modified`, mas as entradas do zip eram
gravadas por nome (`z.writestr("OEBPS/content.opf", opf)`), e com nome em texto
o `zipfile` carimba cada uma com a hora local do momento em que ela passa: dois
livros gravados dos dois lados de uma virada de 2 s — a resolução da data do
zip — saíam diferentes. O DOCX tinha o mesmo, e em dois lugares: no `doc.save`
do `python-docx` e na regravação que embute as fontes.

O relógio daqui anda 7 s a cada consulta, o que troca a corrida rara por uma
certeza: sem a correção, os testes de bytes iguais e o do instante único caem
em toda rodada, e não só com a máquina carregada.
"""

from __future__ import annotations

import time
import zipfile

import pytest

from core import exportar, livro

#: O mesmo instante do `test_adapter_sem_perdas`: 2023-11-14T22:13:20Z.
EPOCA = "1700000000"
DATA_DA_EPOCA = (2023, 11, 14, 22, 13, 20)


@pytest.fixture
def relogio(monkeypatch):
    """Um `time.time` que anda 7 s a cada consulta — mais que os 2 s da data do zip."""
    atual = [1_750_000_001.0]

    def tempo() -> float:
        atual[0] += 7.0
        return atual[0]

    monkeypatch.setattr(time, "time", tempo)


def _png() -> bytes:
    from core import render_diagrama

    png, _largura, _altura = render_diagrama.desenhar(
        "8/8/8/8/8/8/8/4K2k w - - 0 1", lado_px=64)
    return png


def _livro(texto: str = "1.e4 ♘f6: a figurina traz a fonte dos símbolos junto."):
    """Título, prosa e um recorte: entradas de texto, de fonte e de imagem no zip."""
    return [livro.PaginaExtraida(numero=0, blocos=[
        livro.Paragrafo("Chapter 1", titulo=True, nivel=1),
        livro.Paragrafo(texto),
        livro.Figura(_png(), 64, 64, origem="recorte", casas_de_largura=8.0),
    ])]


def _datas(caminho) -> set:
    with zipfile.ZipFile(caminho) as z:
        return {info.date_time for info in z.infolist()}


def _no_zip(iso: str) -> tuple:
    """A data como o zip a guarda: a resolução é de 2 s, e o segundo ímpar cai no par."""
    t = time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")[:6]
    return t[:5] + (t[5] - t[5] % 2,)


# ----------------------------------------------------------------------
# EPUB
# ----------------------------------------------------------------------

def test_dois_epubs_com_o_mesmo_source_date_epoch_saem_com_os_mesmos_bytes(
        tmp_path, monkeypatch, relogio):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", EPOCA)
    paginas = _livro()
    a = exportar.para_epub(paginas, str(tmp_path / "a.epub"))
    exportar.para_epub(paginas, str(tmp_path / "b.epub"))

    assert (tmp_path / "a.epub").read_bytes() == (tmp_path / "b.epub").read_bytes()
    assert _datas(a) == {DATA_DA_EPOCA}


def test_sem_source_date_epoch_o_livro_inteiro_leva_um_instante_so(
        tmp_path, monkeypatch, relogio):
    """
    Sem a variável, é agora — mas **um agora só**, tomado uma vez para o
    arquivo inteiro: toda entrada do zip com a data do `dcterms:modified`.
    """
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    caminho = exportar.para_epub(_livro(), str(tmp_path / "l.epub"))

    opf = zipfile.ZipFile(caminho).read("OEBPS/content.opf").decode("utf-8")
    modificado = opf.split('<meta property="dcterms:modified">')[1].split("<")[0]
    assert _datas(caminho) == {_no_zip(modificado)}


def test_o_mimetype_segue_primeiro_e_guardado_e_o_resto_comprimido(tmp_path,
                                                                   monkeypatch):
    """
    O `ZipInfo` nasce sem compressão, e o `writestr` só usa a do zip quando
    recebe o nome em texto: passar a gravar por `ZipInfo` guardaria o livro
    inteiro sem comprimir se a compressão não fosse posta à mão.
    """
    monkeypatch.setenv("SOURCE_DATE_EPOCH", EPOCA)
    caminho = exportar.para_epub(_livro(), str(tmp_path / "l.epub"))

    with zipfile.ZipFile(caminho) as z:
        infos = z.infolist()
    assert infos[0].filename == "mimetype"
    assert infos[0].compress_type == zipfile.ZIP_STORED
    assert {info.compress_type for info in infos[1:]} == {zipfile.ZIP_DEFLATED}
    # O que o leitor confere de fato: o nome e o tipo nos primeiros bytes.
    dados = (tmp_path / "l.epub").read_bytes()
    assert dados[30:38] == b"mimetype"
    assert dados[38:58] == b"application/epub+zip"


def test_source_date_epoch_antes_de_1980_cai_no_primeiro_dia_do_zip(tmp_path,
                                                                    monkeypatch):
    """
    A data do zip conta os anos a partir de 1980, e o `ZipInfo` recusa o que
    vier antes — `SOURCE_DATE_EPOCH=0` derrubaria a exportação se o instante
    fosse direto para a entrada. O `dcterms:modified` fica com o instante
    pedido: ele sabe dizer 1970.
    """
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    caminho = exportar.para_epub(_livro(), str(tmp_path / "l.epub"))

    assert _datas(caminho) == {(1980, 1, 1, 0, 0, 0)}
    opf = zipfile.ZipFile(caminho).read("OEBPS/content.opf").decode("utf-8")
    assert '<meta property="dcterms:modified">1970-01-01T00:00:00Z</meta>' in opf


# ----------------------------------------------------------------------
# DOCX
# ----------------------------------------------------------------------

@pytest.mark.parametrize("texto, embute", [
    ("Prosa sem símbolo: o pacote sai do python-docx e mais nada.", False),
    ("1.e4 ♘f6: a figurina embute a fonte, e o pacote é regravado.", True),
], ids=["sem-fonte", "com-fonte"])
def test_dois_docx_com_o_mesmo_source_date_epoch_saem_com_os_mesmos_bytes(
        tmp_path, monkeypatch, relogio, texto, embute):
    pytest.importorskip("docx")
    monkeypatch.setenv("SOURCE_DATE_EPOCH", EPOCA)
    paginas = _livro(texto)
    a = exportar.para_docx(paginas, str(tmp_path / "a.docx"))
    exportar.para_docx(paginas, str(tmp_path / "b.docx"))

    assert (tmp_path / "a.docx").read_bytes() == (tmp_path / "b.docx").read_bytes()
    assert _datas(a) == {DATA_DA_EPOCA}
    with zipfile.ZipFile(a) as z:
        infos = z.infolist()
    assert infos[0].filename == "[Content_Types].xml"
    assert {info.compress_type for info in infos} == {zipfile.ZIP_DEFLATED}
    assert any(info.filename.startswith("word/fonts/") for info in infos) == embute
