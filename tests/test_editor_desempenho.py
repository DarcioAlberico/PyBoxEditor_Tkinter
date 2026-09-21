"""
Os orçamentos do editor (ED-03; SPEC_EDITOR §13.1, AC-ED03-13), medidos por
`scripts/medir_editor.py` num capítulo de 20 páginas: `carregar` ≤ 300 ms, `dump`
(o capítulo inteiro relido do widget) ≤ 100 ms, tecla ≤ 50 ms — e a tabela de 20×20 da
ED-04 (AC-ED04-2): carregar a grade de 400 células ≤ 1,5 s, tecla numa célula ≤ 50 ms.
É `slow`: fica fora do gate padrão (`-m "not slow"`) porque mede tempo, e tempo
depende da máquina.

Rodar:      .venv/Scripts/python.exe -m pytest tests/test_editor_desempenho.py -q -m slow
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import pytest

from conftest import raiz_tk


@pytest.mark.slow
def test_carregar_dump_e_tecla_de_um_capitulo_de_20_paginas_cabem_no_orcamento():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    raiz.destroy()
    import medir_editor

    resultado = medir_editor.medir(paginas=20, repeticoes=3)
    assert resultado["blocos"] == 200
    assert resultado["carregar"] <= 0.300, f"carregar em {resultado['carregar'] * 1000:.0f} ms"
    assert resultado["dump"] <= 0.100, f"dump em {resultado['dump'] * 1000:.0f} ms"
    assert resultado["tecla"] <= 0.050, f"tecla em {resultado['tecla'] * 1000:.0f} ms"


@pytest.mark.slow
def test_a_tabela_de_20x20_carrega_como_grade_e_uma_tecla_numa_celula_cabe_no_orcamento():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    raiz.destroy()
    import medir_editor

    resultado = medir_editor.medir_tabela(20, 20, repeticoes=2)
    assert resultado["celulas"] == 400
    assert resultado["carregar_tabela"] <= 1.5, f"carregar em {resultado['carregar_tabela'] * 1000:.0f} ms"
    assert resultado["tecla_na_celula"] <= 0.050, f"tecla em {resultado['tecla_na_celula'] * 1000:.0f} ms"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-m", "slow"]))
