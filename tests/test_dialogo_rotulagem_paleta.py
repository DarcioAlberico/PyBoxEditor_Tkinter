from core import nags
from core.chess_symbols import (CHESS_ANNOTATION_CHARACTERS,
                                VANTAGEM_LIGEIRA_BRANCAS,
                                VANTAGEM_LIGEIRA_PRETAS)
from ui.dialogo_rotulagem import _simbolos_da_paleta


def test_paleta_contem_todos_os_simbolos_da_tabela_nag():
    paleta = set(_simbolos_da_paleta())
    assert {nag.simbolo for nag in nags.TABELA if nag.simbolo} <= paleta


def test_paleta_contem_catalogo_de_caracteres_de_xadrez():
    assert CHESS_ANNOTATION_CHARACTERS <= set(_simbolos_da_paleta())


def test_paleta_contem_o_par_de_vantagem_ligeira():
    paleta = _simbolos_da_paleta()
    assert VANTAGEM_LIGEIRA_BRANCAS in paleta
    assert VANTAGEM_LIGEIRA_PRETAS in paleta


def test_paleta_nao_exibe_o_dois_sobrescrito():
    assert "²" not in _simbolos_da_paleta()
