"""
Testes de `core/editor/simbolos.py` e `ui/editor/simbolos.py` (ED-06; SPEC_EDITOR §9
"Special Characters", §8.15): "BLACK CHESS" lista `♚♛♜♝♞♟` e `codigo_para_caractere
("2A72")` é `⩲` (AC-ED06-6); o `Ctrl+Shift+X` nos dois sentidos; a caixa construída sem
mostrar; e os inseparáveis (AC-ED06-7): o NBSP grava U+00A0, os invisíveis mostram `°`,
e a busca com espaço casa o inseparável.

Rodar sem pytest:      python tests/test_editor_simbolos.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import modelo as m, simbolos, xhtml
from core.editor.modelo import Capitulo, Paragrafo, Trecho
from editor_ambiente import Janela
from ui.editor.simbolos import DialogoDeSimbolos

NBSP = chr(0xA0)


def test_ac6_black_chess_lista_as_pecas_pretas_e_o_codigo_vira_caractere():
    assert [s.caractere for s in simbolos.procurar("BLACK CHESS")] == list("♚♛♜♝♞♟")
    assert [s.caractere for s in simbolos.procurar("black chess king")] == ["♚"]
    assert simbolos.codigo_para_caractere("2A72") == "⩲" == simbolos.codigo_para_caractere("U+2a72")
    assert simbolos.codigo_para_caractere("zz") is None and simbolos.codigo_para_caractere("1") is None
    assert simbolos.caractere_para_codigo("⩲") == "2A72"
    # a consulta por código também lista o caractere, com o nome
    achado = simbolos.procurar("2A72")[0]
    assert achado.caractere == "⩲" and achado.nome == "plus sign above equals sign" and achado.codigo == "2A72"
    assert simbolos.procurar("") == [] and simbolos.procurar("xyzzy nada") == []
    assert [rotulo for rotulo, _c in simbolos.CATEGORIAS][:2] == ["Figurinas", "Avaliação e NAGs"]
    assert simbolos.simbolos_da_categoria("Figurinas")[0].nome == "white chess king"
    assert simbolos.nome_de(NBSP) == "espaço inseparável"


def test_alternar_vai_e_volta_e_nao_engole_um_lance():
    assert simbolos.alternar("ver 2A72") == (4, "⩲")
    assert simbolos.alternar("U+00A0") == (6, NBSP)
    assert simbolos.alternar("x⩲") == (1, "2A72")
    assert simbolos.alternar("e4") == (1, "0034")          # dois dígitos sem prefixo: não é código
    assert simbolos.alternar("") is None


def test_a_caixa_procura_escolhe_e_confirma_sem_mostrar():
    with Janela(abrir=False) as t:
        caixa = DialogoDeSimbolos(t.j)
        caixa.construir()
        assert len(caixa.botoes) == 12 and caixa.simbolos[0].caractere == "♔"
        achados = caixa.procurar("black chess")
        assert [s.caractere for s in achados] == list("♚♛♜♝♞♟") and len(caixa.botoes) == 6
        assert caixa.escolher(1) == "♛" and "black chess queen" in caixa.var_nome.get()
        assert caixa.confirmar() == "♛"


def test_inserir_simbolo_e_ctrl_shift_x_na_janela():
    with Janela() as t:
        j = t.j
        texto = t.texto
        texto.carregar(Capitulo(arquivo="cap1.xhtml", blocos=[Paragrafo(trechos=[Trecho(texto="ver 2A72 e ")])]))
        texto.ir_para(texto.ordem[0], 8)
        assert j.executar("codigo_unicode") == "⩲"
        assert m.texto_de(texto.sincronizar().blocos[0]) == "ver ⩲ e "
        assert j.executar("codigo_unicode") == "2A72"
        assert m.texto_de(texto.sincronizar().blocos[0]) == "ver 2A72 e "
        j.caixas.simbolo = lambda familia="": "♞"
        texto.ir_para(texto.ordem[0], 11)
        assert j.executar("inserir_simbolo") == "♞"
        assert m.texto_de(texto.sincronizar().blocos[0]) == "ver 2A72 e ♞"
        # no código, o símbolo entra no texto cru
        j.executar("alternar_modo")
        editor = j.aba_ativa().widget
        editor.texto.mark_set("insert", "1.0")
        assert j.executar("inserir_simbolo", "♚") == "♚" and editor.texto_todo().startswith("♚")


def test_ac7_nbsp_grava_u00a0_os_invisiveis_mostram_o_grau_e_a_busca_casa_o_inseparavel():
    with Janela() as t:
        j = t.j
        texto = t.texto
        texto.carregar(Capitulo(arquivo="cap1.xhtml", blocos=[Paragrafo(trechos=[Trecho(texto="Diagrama")])]))
        texto.ir_para(texto.ordem[0], 8)
        j.executar("espaco_inseparavel")
        j.executar("inserir_simbolo", "12")
        cap = texto.sincronizar()
        assert m.texto_de(cap.blocos[0]) == f"Diagrama{NBSP}12"
        assert f"Diagrama{NBSP}12" in xhtml.escrever(cap) and "&nbsp;" not in xhtml.escrever(cap)
        texto.invisiveis(True)
        assert "°" in texto.texto.get("1.0", "end") and m.texto_de(texto.sincronizar().blocos[0]) == f"Diagrama{NBSP}12"
        texto.invisiveis(False)
        j.busca.definir(texto="Diagrama 12")
        assert j.executar("localizar_proximo") is not None
        assert texto.texto.get("sel.first", "sel.last") == f"Diagrama{NBSP}12"
        j.busca.definir(texto="Diagrama 12", espaco_casa_nbsp=False)
        assert j.executar("localizar_proximo") is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
