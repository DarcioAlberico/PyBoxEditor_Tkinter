"""
PD-14 (`docs/ROADMAP_PENDENCIAS.md`) — a prosa do ClearScan conserta a palavra do OCR.

A página do ClearScan é recusada pela régua da F110 (a notação dele é ilegível),
mas a prosa dele é quase limpa. `livro.reparar_pela_camada` troca só a palavra
de prosa que o OCR leu e o léxico não conhece pela palavra da camada alinhada a
ela, quando essa é conhecida e parecida. Medido nas três páginas do corpus de
referência com camada (`scripts/medir_prosa_da_camada.py`): a p. 47 do Yusupov,
a do painel sobre trama, vai de 11,51% para 9,93% de CER na prosa; as outras
duas saem iguais.
"""

import sys
from array import array
from math import nan

import pytest

from core import livro, pdf_nativo
from core.lexico import Lexico
from core.livro import PaginaExtraida, Paragrafo

LEX = Lexico(palavras={"the", "king", "walks", "to", "queenside", "and",
                       "rook", "stays", "behind", "white", "wins"})


def _pagina(*textos, **kw):
    return PaginaExtraida(numero=0, blocos=[Paragrafo(t, **kw) for t in textos])


def test_a_palavra_desconhecida_vem_da_camada():
    pagina = _pagina("the kiug walks to the queenside")
    n = livro.reparar_pela_camada(pagina, "The king walks to the queenside.", LEX)
    assert n == 1
    assert pagina.blocos[0].texto == "the king walks to the queenside"


def test_a_pontuacao_das_pontas_e_a_do_ocr():
    pagina = _pagina("and the r0ok, stays behind")
    livro.reparar_pela_camada(pagina, "and the rook; stays behind", LEX)
    assert pagina.blocos[0].texto == "and the rook, stays behind"


def test_a_notacao_e_a_palavra_conhecida_nao_mudam():
    pagina = _pagina("1.♖a1 the king wins")
    livro.reparar_pela_camada(pagina, "1.Ea1 the kings walks", LEX)
    assert pagina.blocos[0].texto == "1.♖a1 the king wins"


def test_palavra_da_camada_desconhecida_ou_diferente_demais_nao_entra():
    pagina = _pagina("the kiug walks", "and qzx stays")
    livro.reparar_pela_camada(pagina, "the kimg walks and white stays", LEX)
    # `kimg` o léxico não conhece; `white` conhece, mas não se parece com `qzx`.
    assert [b.texto for b in pagina.blocos] == ["the kiug walks", "and qzx stays"]


def test_os_vetores_e_os_comecos_andam_junto():
    texto = "the kiiug walks to the queenside"
    p = Paragrafo(texto, pesos=array("d", [0.1] * len(texto)),
                  lacunas=array("d", [nan] * len(texto)),
                  inicios=[0, texto.index("to")])
    pagina = PaginaExtraida(numero=0, blocos=[p])
    livro.reparar_pela_camada(pagina, "the king walks to the queenside", LEX)
    assert p.texto == "the king walks to the queenside"
    assert len(p.pesos) == len(p.texto) and len(p.lacunas) == len(p.texto)
    assert p.inicios == [0, p.texto.index("to")]


def test_sem_lexico_ou_sem_camada_nada_muda():
    pagina = _pagina("the kiug walks")
    assert livro.reparar_pela_camada(pagina, "the king walks", None) == 0
    assert livro.reparar_pela_camada(pagina, "", LEX) == 0
    assert pagina.blocos[0].texto == "the kiug walks"


@pytest.mark.parametrize("lido, outro", [
    ("ofstud", "study"), ("theresult", "result"), ("J.Nunn", "Nunn"),
    ("Zamodiakin", "akin"), ("lity", "possibility"), ("fering", "transferring"),
])
def test_pedaco_nao_e_leitura_errada(lido, outro):
    """Da listagem do Nunn e do Yusupov: a camada alinhada a só um pedaço da
    palavra lida — ou o contrário — apagaria a outra metade."""
    assert not livro._pontas_casam(lido, outro)


@pytest.mark.parametrize("lido, outro", [
    ("hrstly", "firstly"), ("reciproca", "reciprocal"), ("Diagrram", "Diagram"),
    ("proht", "profit"), ("C.ss", "Chess"),
])
def test_letra_trocada_passa(lido, outro):
    assert livro._pontas_casam(lido, outro)


def test_a_ponta_que_e_pedaco_de_letra_sai():
    lex = Lexico(palavras={"reciprocal", "otherwise", "the", "zugzwang"})
    pagina = _pagina("the reciproca1 zugzwang", "()therwise the zugzwang")
    livro.reparar_pela_camada(
        pagina, "the reciprocal zugzwang Otherwise the zugzwang", lex)
    assert [b.texto for b in pagina.blocos] == [
        "the reciprocal zugzwang", "Otherwise the zugzwang"]


def test_o_veredito_diz_quando_e_clearscan():
    clearscan = pdf_nativo.Veredito(
        0, False, f"{pdf_nativo.MOTIVO_CLEARSCAN} (900 de 1000 caracteres)")
    invisivel = pdf_nativo.Veredito(0, False, "texto invisível sobre a imagem")
    aceita = pdf_nativo.Veredito(0, True, "camada tipográfica")
    assert clearscan.clearscan
    assert not invisivel.clearscan and not aceita.clearscan


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
