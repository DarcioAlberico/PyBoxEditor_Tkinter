"""
A tabela de NAGs — os símbolos do "Key to symbols used" destes livros.

O teste que importa aqui é o **da fonte**. Um símbolo acrescentado à tabela sem
conferir a cobertura vira caixa vazia na tela e no PDF, sem erro nenhum no
caminho — é o defeito do `·` da SPEC §4.2, onde a Helvetica trocava cada peça por
um ponto e o usuário só descobria ao abrir o PDF pronto. `missing_glyphs` já
existe justamente para isso.

Rodar sem pytest:      python tests/test_nags.py
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.chess_pdf_processor import CHESS_FONT_CANDIDATES, missing_glyphs
from ui.main_window import NAGS, NAGS_POR_FAMILIA


def _fontes_no_disco():
    return [p for p in CHESS_FONT_CANDIDATES if os.path.exists(p)]


def test_tabela_achatada_bate_com_as_familias():
    assert NAGS == [par for _, fam in NAGS_POR_FAMILIA for par in fam]


def test_sem_simbolo_repetido():
    """Dois botões com o mesmo símbolo seriam o mesmo botão duas vezes."""
    simbolos = [s for s, _ in NAGS]
    assert len(simbolos) == len(set(simbolos))


def test_toda_familia_tem_nome_e_conteudo():
    for titulo, familia in NAGS_POR_FAMILIA:
        assert titulo and familia


def test_todo_nag_tem_descricao():
    """A descrição é o tooltip e o rótulo do menu — sem ela o botão é charada."""
    assert all(desc.strip() for _, desc in NAGS)


def test_a_fonte_do_pdf_desenha_todos_os_simbolos():
    """
    Alguma fonte candidata cobre a tabela inteira.

    Conferido quando esta tabela cresceu para 23: `Segoe UI Symbol` desenha
    todos; `MS Gothic`, a candidata seguinte, não tem `⩲`, `⩱` nem `⌓` — e
    também não tinha o `⨀`, que já estava na tabela antes. Por isso o teste
    pergunta se **alguma** cobre, e não se todas cobrem.
    """
    fontes = _fontes_no_disco()
    if not fontes:
        pytest.skip("nenhuma fonte candidata neste sistema")

    alvo = "".join(s for s, _ in NAGS if len(s) == 1)
    faltas = {}
    for caminho in fontes:
        try:
            falta = missing_glyphs(caminho, alvo)
        except Exception as e:                      # fonte ilegível não é falha
            faltas[os.path.basename(caminho)] = f"erro: {e}"
            continue
        if not falta:
            return
        faltas[os.path.basename(caminho)] = "".join(falta)

    pytest.fail("nenhuma fonte desenha todos os NAGs: %s" % faltas)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
