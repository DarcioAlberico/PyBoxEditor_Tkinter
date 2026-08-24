"""
Testes da F98 — a segunda fonte de diagrama, e o que ela quebrou ao entrar.

Até aqui "a fonte" era uma só, e por isso várias suposições sobre ela não
precisavam ser ditas. A Chess Merida disse todas de uma vez:

    cmap        a MERIFONT.TTF de 1998 só tem tabela de símbolo, e o `fitz`
                não enxerga um glifo sequer nela — desenha `·` sem erro nenhum
    família     o nome de dentro do arquivo tem de bater com a chave do mapa,
                ou o DOCX embute uma fonte que o Word não liga ao texto
    casa vazia  a da SkakNew é o `0` e o `Z`; a da Merida é o **espaço**, e
                espaço no fim da linha não conta para o Word centrar

As três falham em silêncio, e as três estão presas aqui. A quarta prova — que o
mapa está certo peça a peça — não mora nesta suíte: ela é o
`medir_fonte_diagrama.py`, que rende o FEN e relê o desenho com as duas redes da
F7.4/F7.5, e que precisa do modelo e do corpus. O que cabe aqui é a ida e volta
pelo próprio mapa, que é barata e pega troca de letra.

Rodar sem pytest:      python tests/test_f98_merida.py
"""

import os
import re
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import exportar, livro
from core import render_diagrama as rd

MERIDA = "ChessMerida-Diagram"

#: Um final com peças espalhadas: rei, dama, torre, bispo, cavalo e peão das
#: duas cores, e cada um em casa clara e escura ao longo do tabuleiro.
FEN = "3qkb2/5p2/2n5/1B2P3/3P1r2/2N5/5P2/2RQK3"

#: A fonte de 1998, como ela veio. **Não é a que o mapa usa** — ver o teste.
ORIGINAL = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "fonts", "MERIFONT.TTF")


def _fens_de_volta(linhas, fonte: rd.Fonte) -> str:
    """As oito linhas de volta a FEN, lidas pelo próprio mapa."""
    filas = []
    for linha in linhas:
        fila, vazias = "", 0
        for ch in linha:
            simbolo, _cor = fonte.casas[ch]
            if simbolo is None:
                vazias += 1
                continue
            if vazias:
                fila += str(vazias)
                vazias = 0
            fila += simbolo
        if vazias:
            fila += str(vazias)
        filas.append(fila)
    return "/".join(filas)


# ----------------------------------------------------------------------
# A fonte
# ----------------------------------------------------------------------

def test_a_merida_esta_no_mapa_e_carrega():
    assert MERIDA in rd.fontes()
    fonte = rd.carregar(MERIDA)
    assert fonte.em == 2048, "a Merida é de 2048 unidades por em, e não 1000"
    assert len(fonte.casas) == 26


def test_o_fitz_nao_enxerga_a_fonte_original():
    """
    **É por isto que existe o `gerar_fonte_de_diagrama.py`**, e é o teste que
    impede alguém de "simplificar" apontando o mapa para a MERIFONT.TTF.

    Ela só tem cmap Mac Roman (1,0) e Symbol (3,0), esta com os caracteres em
    `0xF020`–`0xF0EF`. O `fitz` não lê nenhuma das duas: varridos os 65.536
    codepoints do plano básico, encontra zero glifos — e `insert_text` desenha
    um ponto no lugar de cada peça, sem levantar erro (SPEC §4.2).
    """
    import fitz

    if not os.path.exists(ORIGINAL):
        pytest.skip("a MERIFONT.TTF original não está no repositório")

    f = fitz.Font(fontfile=ORIGINAL)
    assert not any(f.has_glyph(c) for c in range(0x10000)), (
        "a fonte original ganhou cmap Unicode — o remendo pode ser dispensado")

    remendada = fitz.Font(fontfile=rd.carregar(MERIDA).arquivo)
    faltando = [c for c in rd.carregar(MERIDA).casas
                if not remendada.has_glyph(ord(c))]
    assert not faltando, f"o remendo não cobre {''.join(faltando)!r}"


def test_a_familia_de_dentro_do_arquivo_bate_com_a_chave_do_mapa():
    """
    **Invariante do DOCX, e ele falha calado.** Quem embute a fonte escreve
    `<w:font w:name="...">` com a chave do mapa e pede a mesma chave no run: se
    a família de dentro do arquivo disser outra coisa, o Word não liga uma na
    outra e o tabuleiro sai na fonte do usuário. Vale para toda fonte do mapa,
    e não só para esta — é o que a próxima vai ter de respeitar também.
    """
    for nome in rd.fontes():
        arquivo = rd.carregar(nome).arquivo
        assert exportar._familia(arquivo) == nome, (
            f"{nome} está gravada como {exportar._familia(arquivo)!r} dentro "
            f"de {arquivo}")


# ----------------------------------------------------------------------
# O mapa
# ----------------------------------------------------------------------

def test_a_ida_e_volta_pelo_mapa_devolve_o_mesmo_fen():
    """Barata e pega troca de letra — dama por rei, torre por bispo."""
    for nome in rd.fontes():
        fonte = rd.carregar(nome)
        assert _fens_de_volta(rd.linhas(FEN, fonte), fonte) == FEN, nome


def test_as_duas_fontes_desenham_o_mesmo_tabuleiro():
    """
    A geometria é do renderizador, e não da fonte: mesmo lado pedido, mesmo
    lado desenhado, com ou sem moldura. Uma fonte cujo em não fosse a casa
    sairia daqui com outra medida.
    """
    for moldura in ("sem", "simples", "dupla"):
        lados = {rd.desenhar(FEN, fonte=n, lado_px=352, moldura=moldura)[1]
                 for n in rd.fontes()}
        assert len(lados) == 1, f"as fontes divergiram em {moldura}: {lados}"


def test_a_casa_clara_vazia_da_merida_e_o_espaco():
    """
    O que faz a F98 mexer no DOCX. Preso aqui para o dia em que alguém trocar
    o `" "` do mapa por outra coisa e o alinhamento parecer sobra de código.
    """
    fonte = rd.carregar(MERIDA)
    assert fonte.caractere(None, "clara") == " "
    assert fonte.caractere(None, "escura") == "+"
    assert any(" " in linha for linha in rd.linhas(FEN, fonte))


# ----------------------------------------------------------------------
# O arquivo escrito
# ----------------------------------------------------------------------

def _figura(nome=MERIDA, lado=352):
    png, largura, altura = rd.desenhar(FEN, fonte=nome, lado_px=lado)
    return livro.Figura(png, largura, altura, fen=FEN, origem="render",
                        linhas=rd.linhas(FEN, rd.carregar(nome)), fonte=nome,
                        casas_de_largura=largura * 8.0 / rd.lado_efetivo(lado))


def test_o_docx_preserva_o_espaco_da_casa_vazia():
    """
    Sem `xml:space="preserve"` o Word come o espaço da ponta da fila, e a fila
    inteira anda uma casa. O `python-docx` o escreve sozinho — o que este teste
    prende é que ele continue escrevendo.
    """
    tmp = tempfile.mkdtemp()
    caminho = exportar.para_docx(
        [livro.PaginaExtraida(numero=0, blocos=[_figura()])],
        os.path.join(tmp, "m.docx"), diagramas="fonte")
    with zipfile.ZipFile(caminho) as z:
        xml = z.read("word/document.xml").decode("utf-8")

    filas = re.findall(r'<w:t xml:space="preserve">([^<]*)</w:t>', xml)
    esperadas = rd.linhas(FEN, rd.carregar(MERIDA))
    com_espaco = [f for f in esperadas if f.startswith(" ") or f.endswith(" ")]
    assert com_espaco, "esta posição não exercita o caso — troque o FEN"
    for fila in com_espaco:
        assert fila in filas, f"a fila {fila!r} perdeu o espaço"


def test_a_merida_vai_embutida_com_o_nome_que_o_run_pede():
    tmp = tempfile.mkdtemp()
    caminho = exportar.para_docx(
        [livro.PaginaExtraida(numero=0, blocos=[_figura()])],
        os.path.join(tmp, "m.docx"), diagramas="fonte")
    with zipfile.ZipFile(caminho) as z:
        documento = z.read("word/document.xml").decode("utf-8")
        tabela = z.read("word/fontTable.xml").decode("utf-8")
        nomes = z.namelist()

    assert f'w:ascii="{MERIDA}"' in documento
    assert f'<w:font w:name="{MERIDA}">' in tabela
    assert [n for n in nomes if n.startswith("word/fonts/")]


def test_o_epub_declara_a_merida_na_css():
    tmp = tempfile.mkdtemp()
    caminho = exportar.para_epub(
        [livro.PaginaExtraida(numero=0, blocos=[_figura()])],
        os.path.join(tmp, "m.epub"), diagramas="fonte")
    with zipfile.ZipFile(caminho) as z:
        css = z.read("OEBPS/estilo.css").decode("utf-8")
        nomes = z.namelist()

    assert f'font-family: "{MERIDA}"' in css
    assert "OEBPS/fonts/ChessMerida-Diagram.ttf" in nomes


def test_fonte_sem_mapa_reclama_antes_de_desenhar():
    """A lista do diálogo sai de `fontes()`; pedir outra tem de doer na hora."""
    with pytest.raises(rd.FonteDesconhecida):
        rd.desenhar(FEN, fonte="Merida")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
