"""
Testes de `core/lexico.py: sugestoes` (ED-06; SPEC_EDITOR §8.13): `sugestoes("knigt",
lex)[0] == "knight"` (AC-ED06-3), a inicial maiúscula é respeitada, o léxico vazio não
sugere nada, e importar `core.lexico` não traz o `cv2` (AC-ED06-8: o `notacao` passou a
ser importado só onde é usado).

Rodar sem pytest:      python tests/test_lexico_sugestoes.py
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import lexico

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def lex():
    carregado = lexico.carregar()
    if not carregado.sinaliza:
        pytest.skip("assets/lexico/en.txt.gz ausente")
    return carregado


def test_ac3_knigt_sugere_knight_primeiro(lex):
    achadas = lexico.sugestoes("knigt", lex)
    assert achadas and achadas[0] == "knight" and len(achadas) <= 5
    assert lexico.sugestoes("knigt", lex, n=2) == achadas[:2]


def test_a_inicial_maiuscula_e_a_pontuacao_das_pontas_sao_respeitadas(lex):
    assert lexico.sugestoes("Knigt", lex)[0] == "Knight"
    assert lexico.sugestoes("knigt,", lex)[0] == "knight"
    assert lexico.sugestoes("Nimzowitch", lex)[0] == "Nimzowitsch"


def test_o_lexico_vazio_e_a_palavra_sem_letras_nao_sugerem_nada():
    assert lexico.sugestoes("knigt", lexico.Lexico()) == []
    assert lexico.sugestoes("1234", lexico.carregar(caminho=os.devnull)) == []


def test_a_palavra_do_usuario_tambem_e_sugerida():
    lex = lexico.Lexico(palavras={"the"})
    lex.acrescentar("Zukertort")
    assert lexico.sugestoes("Zukertorf", lex) == ["Zukertort"]


def test_ac8_importar_core_lexico_nao_traz_cv2_nem_numpy():
    codigo = ("import sys; import core.lexico; from core.editor import ortografia; "
              "print(sorted(m for m in ('cv2', 'numpy', 'torch', 'fitz') if m in sys.modules))")
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, cwd=RAIZ, timeout=120)
    assert saida.returncode == 0, saida.stderr
    assert saida.stdout.strip() == "[]", saida.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
