"""
Testes de `ui/editor/fonte.py` (ED-03; §8.2, AC-ED03-4): o `DialogoDeFonte` construído
sem `mostrar()`, operado pelas variáveis, devolve só o que mudou; cancelar devolve
`None`; o resultado entra em `TextoRico.aplicar`.

Rodar sem pytest:      python tests/test_editor_fonte.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from conftest import raiz_tk
from core.editor import modelo as m
from ui.editor.fonte import DialogoDeFonte
from ui.editor.texto_rico import TextoRico


def test_ac4_o_dialogo_devolve_os_atributos_escolhidos_e_so_o_que_mudou():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        atual = {"familia": "Georgia", "corpo_pt": 12.0, "negrito": True, "posicao": "", "cor": ""}
        caixa = DialogoDeFonte(raiz, atual, familias=["Arial", "Georgia"])
        caixa._construir()
        v = caixa.variaveis
        assert v["familia"].get() == "Georgia" and v["corpo_pt"].get() == "12" and v["negrito"].get() is True
        assert caixa.diferencas() == {}                                       # nada mudou ainda
        v["italico"].set(True)
        v["corpo_pt"].set("14")
        v["posicao"].set("sobre")
        v["cor"].set("#c00000")
        v["negrito"].set(False)
        resultado = caixa.confirmar()
        assert resultado == {"italico": True, "corpo_pt": 14.0, "sobrescrito": True, "cor": "#c00000", "negrito": False}
        assert caixa.resultado == resultado and caixa.top is None
        # O resultado entra direto em `aplicar`.
        texto = TextoRico(raiz)
        texto.pack()
        texto.carregar(m.Capitulo(arquivo="c", blocos=[m.Paragrafo(trechos=[m.Trecho(texto="abc")])]))
        texto.selecionar_indices("1.0", "1.3")
        texto.aplicar(**resultado)
        trecho = texto.sincronizar().blocos[0].trechos[0]
        assert trecho.italico and trecho.corpo_pt == 14.0 and trecho.posicao == "sobre" and trecho.cor == "#c00000"
        assert not trecho.negrito
        # Cancelar devolve None; valor de corpo inválido não derruba.
        caixa = DialogoDeFonte(raiz, {"corpo_pt": 12.0})
        caixa._construir()
        caixa.variaveis["corpo_pt"].set("x")
        assert caixa.escolhas()["corpo_pt"] is None
        caixa.cancelar()
        assert caixa.resultado is None and caixa.top is None
        caixa = DialogoDeFonte(raiz, {})
        caixa._construir()
        assert int(caixa.amostra.cget("highlightthickness")) >= 1 and caixa.botao_ok.cget("text") == "OK"
        caixa.cancelar()
    finally:
        raiz.destroy()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
