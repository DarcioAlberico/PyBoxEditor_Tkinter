"""
Testes da F62 — o recorte da fonte de símbolos.

O `gerar_fonte_de_simbolos.py` roda à mão e o produto dele é versionado, o que
cria um jeito silencioso de o livro sair errado: **o alfabeto do modelo cresce e
o recorte não**. Aí o símbolo novo vira quadradinho no EPUB, e nada acusa.

É isso que os testes abaixo prendem, e é por isso que eles leem o
`model_meta.json` em vez de uma lista fixa: a fonte de verdade sobre o que o
livro pode conter é o modelo, não este arquivo.

Rodar sem pytest:      python tests/test_f62_simbolos.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import exportar
from gerar_fonte_de_simbolos import ORIGEM, cobertura, simbolos_do_modelo


def test_o_recorte_cobre_o_que_a_fonte_inteira_cobre():
    """
    Se o modelo aprender um símbolo que só a fonte inteira desenha, este teste
    acusa e o remédio é uma linha: `python gerar_fonte_de_simbolos.py`.
    """
    if not os.path.exists(exportar.SUBSET_DOS_SIMBOLOS):
        pytest.skip("recorte não gerado (rode gerar_fonte_de_simbolos.py)")

    simbolos = simbolos_do_modelo()
    inteira = cobertura(ORIGEM, simbolos)
    recorte = cobertura(exportar.SUBSET_DOS_SIMBOLOS, simbolos)
    faltando = [c for c in inteira if c not in recorte]

    assert not faltando, (
        f"o recorte não desenha {' '.join(faltando)} — rode "
        f"`python gerar_fonte_de_simbolos.py`")


def test_o_recorte_e_muito_menor_que_a_fonte_inteira():
    """A razão de ele existir. 641 KB para desenhar quinze glifos."""
    if not os.path.exists(exportar.SUBSET_DOS_SIMBOLOS):
        pytest.skip("recorte não gerado (rode gerar_fonte_de_simbolos.py)")

    assert (os.path.getsize(exportar.SUBSET_DOS_SIMBOLOS)
            < os.path.getsize(ORIGEM) * 0.05)


def test_as_figurinas_estao_no_recorte():
    if not os.path.exists(exportar.SUBSET_DOS_SIMBOLOS):
        pytest.skip("recorte não gerado (rode gerar_fonte_de_simbolos.py)")
    assert cobertura(exportar.SUBSET_DOS_SIMBOLOS, "♔♕♖♗♘♙") == "♔♕♖♗♘♙"


def test_o_recorte_e_o_escolhido_quando_basta():
    """Entre duas fontes que cobrem o mesmo, ganha a que pesa 1,2% da outra."""
    escolha = exportar.fonte_dos_simbolos("1.e4 ♖xf3 ♕d5")
    assert escolha
    if os.path.exists(exportar.SUBSET_DOS_SIMBOLOS):
        assert escolha[1] == exportar.SUBSET_DOS_SIMBOLOS


def test_sem_recorte_a_fonte_inteira_assume():
    """
    O recorte é produto de script; ele pode não ter sido gerado num clone novo.
    Nesse caso o livro sai maior, e não sai errado.
    """
    original = exportar.SUBSET_DOS_SIMBOLOS
    exportar.SUBSET_DOS_SIMBOLOS = os.path.join(os.path.dirname(original),
                                                "nao-existe.ttf")
    try:
        escolha = exportar.fonte_dos_simbolos("1.e4 ♖xf3")
        assert escolha and escolha[1] == ORIGEM
    finally:
        exportar.SUBSET_DOS_SIMBOLOS = original


def test_a_familia_do_recorte_nao_se_passa_pela_original():
    """
    Subset é modificação, e a OFL pede que a modificada não use o nome da
    original. Há um motivo prático junto: uma família com o nome da Noto
    instalada na máquina de quem abre o arquivo brigaria com esta, que tem
    quinze glifos.
    """
    if not os.path.exists(exportar.SUBSET_DOS_SIMBOLOS):
        pytest.skip("recorte não gerado (rode gerar_fonte_de_simbolos.py)")

    familia = exportar._familia(exportar.SUBSET_DOS_SIMBOLOS)
    assert "Noto" not in familia
    assert familia == "Simbolos de Xadrez"


# ----------------------------------------------------------------------
# O que estava errado no arquivo e ninguém via
# ----------------------------------------------------------------------

def test_o_idioma_do_livro_nao_e_o_do_programa():
    """
    Era `pt` fixo, e estes livros são em inglês — a mesma distinção que a §5.8
    da SPEC faz para o léxico. Livro declarado no idioma errado é hifenização
    errada e leitor de tela lendo notação inglesa com fonemas portugueses.
    """
    import tempfile
    import zipfile

    from core import livro

    paginas = [livro.PaginaExtraida(numero=0,
                                    blocos=[livro.Paragrafo("The rook is bad.")])]
    with tempfile.TemporaryDirectory() as tmp:
        caminho = exportar.para_epub(paginas, os.path.join(tmp, "a.epub"))
        with zipfile.ZipFile(caminho) as z:
            opf = z.read("OEBPS/content.opf").decode("utf-8")
            pagina = z.read("OEBPS/pagina-0001.xhtml").decode("utf-8")

        assert "<dc:language>en</dc:language>" in opf
        assert 'xml:lang="en"' in pagina

        outro = exportar.para_epub(paginas, os.path.join(tmp, "b.epub"),
                                   idioma="pt")
        with zipfile.ZipFile(outro) as z:
            assert "<dc:language>pt</dc:language>" in z.read(
                "OEBPS/content.opf").decode("utf-8")


def test_o_titulo_do_paragrafo_deixa_de_ser_letra_morta():
    """
    O campo existe na `Paragrafo` desde a F2.6 e os dois exportadores o
    ignoravam. Nada o marca ainda — isso é trabalho de quem detectar título na
    página —, mas quem marcar agora encontra os dois formatos prontos.
    """
    import tempfile
    import zipfile

    from docx import Document

    from core import livro

    paginas = [livro.PaginaExtraida(
        numero=0, blocos=[livro.Paragrafo("Chapter 1", titulo=True),
                          livro.Paragrafo("Prosa comum.")])]
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(exportar.para_epub(
                paginas, os.path.join(tmp, "a.epub"))) as z:
            pagina = z.read("OEBPS/pagina-0001.xhtml").decode("utf-8")
        assert "<h2>Chapter 1</h2>" in pagina
        assert "<p>Prosa comum.</p>" in pagina or (
            '<p class="primeira">Prosa comum.</p>' in pagina)

        doc = Document(exportar.para_docx(paginas, os.path.join(tmp, "a.docx")))
        assert doc.paragraphs[0].style.name == "Heading 2"
        assert doc.paragraphs[1].style.name != "Heading 2"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
