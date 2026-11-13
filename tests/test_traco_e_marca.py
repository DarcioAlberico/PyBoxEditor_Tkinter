"""
O traço espaçado de um lado fica espaçado dos dois, e a marca de verificação é uma só.

Na p. 237 do Nunn, `and wins – see diagram` saía `and wins —see diagram`: a cadeia
e o motor perdem o espaço depois do traço (o vão ali é mais curto que o de
antes), e nenhum dos dois o perde antes. No painel de conteúdo do Chess
Evolution 1 (p. 47) a cadeia escreve a marca de verificação como 🗸 (a classe do
modelo) e a referência transcrita tem ✓ — a mesma marca, contada como erro.

Rodar sem pytest:      python tests/test_traco_e_marca.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import livro
from core.ocr_ab import medir_por_dominio, normalizar_tipografia


def test_o_traco_espacado_de_um_lado_fica_espacado_dos_dois():
    assert livro._espacar_traco("and wins —see diagram") == "and wins — see diagram"
    assert livro._espacar_traco("and wins –see diagram") == "and wins – see diagram"
    assert livro._espacar_traco("wins— see") == "wins — see"
    # E pelo corretor da linha, que é por onde a linha fundida passa.
    assert (livro._corrigir_prosa_contextual("4...♔f7? 5 ♔b2! and wins —see diagram", fuzzy=False)
            == "4...♔f7? 5 ♔b2! and wins — see diagram")


@pytest.mark.parametrize("texto", [
    "1–0", "½–½", "0–1",            # o resultado
    "a-file", "and wins -see",      # o hífen não é traço
    "e4 –+", "–+ and wins",         # a avaliação
    "Gibraltar 2012 –", "– 31",     # número de um lado
    "word—word", "A.Yusupov – M.Chandler",   # fechado dos dois lados, ou já espaçado
])
def test_o_que_nao_e_traco_entre_palavras_fica(texto):
    assert livro._espacar_traco(texto) == texto


def test_a_marca_de_verificacao_e_uma_so_na_medida():
    assert normalizar_tipografia("🗸 Two methods") == normalizar_tipografia("✓ Two methods")
    contas = medir_por_dominio("✓ Two methods", "🗸 Two methods")
    assert contas["total"]["erros"] == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
