"""Vocabulário Unicode de símbolos usados em anotação de xadrez."""

from __future__ import annotations


# Símbolos de avaliação/NAG e variantes tipográficas encontradas nas linhas
# impressas. O catálogo é um vocabulário inicial; a imagem rotulada continua
# sendo a fonte de verdade do reconhecimento.
CHESS_ANNOTATION_CHARACTERS = frozenset(
    "♔♕♖♗♘♙♚♛♜♝♞♟"
    "!?#=~±∓∞⩲⩱⨀⟳↑→⯹⇆⨁∆∇⌓≤○⊕⊙□☒"
    "+−–—†‡"
)

CHESS_SYMBOL_SOURCES = (
    "https://rpb-chessboard.yo35.org/documentation/chess-assessment-symbols/",
    "https://en.wikipedia.org/wiki/Chess_annotation_symbols",
)

# Par inseparável da avaliação de posição: o sinal de mais sobre/contra o
# sinal de igualdade. Mantemos nomes explícitos porque são fáceis de confundir
# visualmente e ambos precisam estar disponíveis na paleta de correção.
VANTAGEM_LIGEIRA_BRANCAS = "⩲"
VANTAGEM_LIGEIRA_PRETAS = "⩱"


def caracteres_de_xadrez() -> str:
    return "".join(sorted(CHESS_ANNOTATION_CHARACTERS))
