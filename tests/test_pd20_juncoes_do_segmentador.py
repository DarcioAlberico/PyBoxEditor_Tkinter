"""
PD-20 (`docs/ROADMAP_PENDENCIAS.md`) — a letra que o segmentador partiu em duas.

Nas aberturas de lição do Yusupov *Chess Evolution 1* a prosa está sobre trama, e
a cadeia própria lê `tlie`, `vvith`, `niake`, `bisliop`: o `h` partido em `l`+`i`,
o `w` em `v`+`v`, o `m` em `n`+`i`. `_corrigir_juncoes` desfaz a junção só onde o
léxico não conhece a palavra lida e conhece **uma** variante comum.
"""

import sys

import pytest

from core import livro
from core.lexico import Lexico

pytest.importorskip("wordfreq")

LEX = Lexico(palavras={"the", "with", "pawn", "pawns", "most", "chess",
                       "make", "bishop", "queen", "diagonal", "very", "this",
                       "history", "die", "vm"})


def test_o_termo_de_xadrez_passa_abaixo_da_frequencia():
    """`pawns` (2,99) e `diagonal` (3,36) ficam abaixo da frequência mínima e
    passam pela lista do domínio; `vm` (3,22), com a mesma frequência, não."""
    assert livro._corrigir_juncoes("two pavvns", LEX) == "two pawns"
    assert livro._corrigir_juncoes("vrn", LEX) == "vrn"


@pytest.mark.parametrize("lido, certo", [
    ("tlie", "the"),
    ("Tlie", "The"),
    ("vvith", "with"),
    ("pavvns", "pawns"),
    ("niost", "most"),
    ("cliess", "chess"),
    ("bisliop", "bishop"),
    ("qLieen", "queen"),
    ("diagona[", "diagonal"),
    ("veryr", "very"),
    ("liistoryr", "history"),
])
def test_a_juncao_se_desfaz(lido, certo):
    assert livro._corrigir_juncoes(f"on {lido} square", LEX) == f"on {certo} square"


@pytest.mark.parametrize("texto", [
    "the bishop is strong",          # conhecidas não mudam
    "Nimzowitsch and Vladimirov",    # nomes sem variante conhecida
    "i.e. the rook",                 # pontuação e palavras curtas
    "vrn",                           # `vm` é conhecida de algum léxico, e rara
    "",
])
def test_o_que_nao_e_juncao_fica(texto):
    assert livro._corrigir_juncoes(texto, LEX) == texto


def test_sem_lexico_e_o_texto_de_antes():
    assert livro._corrigir_juncoes("tlie", None) == "tlie"
    assert livro._corrigir_juncoes("tlie", Lexico(palavras=set())) == "tlie"


def test_duas_variantes_conhecidas_nao_escolhe():
    """Com `tl`→`d` na lista, `tlie` seria `the` ou `die`; ela ficou de fora
    por isso. Aqui a ambiguidade vem de `li`→`h` em dois lugares."""
    lex = Lexico(palavras={"ahb", "hab"})
    assert livro._corrigir_juncoes("lilib", lex) == "lilib"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
