"""
Testes de `ui/dialogo_de_conclusao.py` (ED-02; SPEC_EDITOR §7.2, AC-ED02-10): a caixa
lista as ações — "Abrir arquivo", "Abrir pasta" e, quando há, "Abrir no editor" — e o
callback de cada uma recebe o **caminho**; sem `abrir_no_editor`, o botão não existe.

Rodar sem pytest:      python tests/test_dialogo_de_conclusao.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from conftest import raiz_tk
from ui.dialogo_de_conclusao import DialogoDeConclusao


def test_a_caixa_lista_as_acoes_e_o_callback_recebe_o_caminho(tmp_path):
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        caminho = str(tmp_path / "livro.epub")
        recebidos = []
        caixa = DialogoDeConclusao(raiz, "Livro exportado", ["Páginas: 3", "Figuras: 1"], caminho,
                                   acoes=[("Outra coisa", lambda c: recebidos.append(("outra", c)))],
                                   abrir_no_editor=lambda c: recebidos.append(("editor", c)))
        top = caixa.construir()
        top.withdraw()
        assert [rotulo for rotulo, _a in caixa.acoes] == ["Abrir arquivo", "Abrir pasta", "Abrir no editor", "Outra coisa"]
        assert set(caixa.botoes) == {"Abrir arquivo", "Abrir pasta", "Abrir no editor", "Outra coisa"}
        assert "Páginas: 3" in caixa.texto.get("1.0", "end")
        caixa.invocar("Abrir no editor")
        assert recebidos == [("editor", caminho)] and caixa.escolha == "Abrir no editor"
        assert caixa.top is None                       # fechou depois da ação
        caixa2 = DialogoDeConclusao(raiz, "x", [], caminho)
        caixa2.construir().withdraw()
        assert [rotulo for rotulo, _a in caixa2.acoes] == ["Abrir arquivo", "Abrir pasta"]
        with pytest.raises(KeyError):
            caixa2.invocar("Abrir no editor")
        caixa2.fechar()
        assert caixa2.top is None
    finally:
        raiz.destroy()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
