"""
Testes de `core/estilo_do_livro.py` (ED-00; SPEC_EDITOR DEC-07, AC-ED00-8): as constantes
saíram de `core/exportar.py` **sem mudar de nome**, e o núcleo do editor abre num
processo sem `fitz`, `numpy`, `cv2`, `PIL` ou `tkinter`.

A conferência de importações roda num **subprocesso**, e não é frescura: dentro do
pytest o `conftest.py` já importou `torch` e companhia antes de qualquer teste, e
`sys.modules` do processo do pytest não diz nada sobre a leveza dos módulos.

Rodar sem pytest:      python tests/test_estilo_do_livro.py
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import estilo_do_livro, exportar
from core.editor import dialeto

PESADOS = ("fitz", "numpy", "cv2", "PIL", "tkinter", "torch")


def test_o_exportar_reexporta_as_constantes_com_o_mesmo_objeto():
    for nome in estilo_do_livro.__all__:
        assert getattr(exportar, nome) is getattr(estilo_do_livro, nome), nome
    assert exportar.CSS is estilo_do_livro.CSS


def test_a_css_padrao_preenche_so_os_moldes():
    css = dialeto.css_padrao(16, "simples", "reto")
    assert "%(" not in css and "margin: 0 6%" in css
    assert "font-size: 16pt" in css and "border: 0.06em solid #000" in css
    dupla = dialeto.css_padrao(18.5, "dupla", "arredondado")
    assert "font-size: 18.5pt" in dupla and "border-radius: 0.40em" in dupla
    with pytest.raises(ValueError):
        dialeto.css_padrao(16, "tripla", "reto")


def test_o_nucleo_do_editor_abre_sem_as_importacoes_pesadas():
    codigo = (
        "import sys, json\n"
        "import core.editor.modelo, core.editor.dialeto, core.editor.xhtml, core.editor.css_minima\n"
        "import core.editor.historico, core.editor.conversao, core.editor.sumario, core.estilo_do_livro\n"
        "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in %r)))\n" % (PESADOS,)
    )
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    saida = subprocess.run([sys.executable, "-c", codigo], cwd=raiz, capture_output=True, text=True,
                           timeout=120)
    assert saida.returncode == 0, saida.stderr
    assert saida.stdout.strip() == "[]", saida.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
