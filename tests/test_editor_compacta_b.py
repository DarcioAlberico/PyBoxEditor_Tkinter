"""
Testes da ED-16b (o que ficou da janela compacta): os botões N/I/S/T acompanham o cursor;
o painel Xadrez traz Diagrama/Posição/Validar e, à vista, dispensa a barra de xadrez; o painel
Propriedades vazio encolhe e devolve a altura quando volta a ter o que mostrar; a coluna
esquerda é um caderno de abas (Navegador · Sumário · Estilos).

Rodar sem pytest:      python tests/test_editor_compacta_b.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import modelo as m
from editor_ambiente import Janela


def _formato(j):
    return {nome: var.get() for nome, var in j.barra_de_formatacao.formato.items()}


def test_nist_acompanham_o_cursor_a_selecao_e_o_ctrl_b():
    with Janela() as t:
        j, texto = t.j, t.texto
        assert set(j.barra_de_formatacao.formato) == {"negrito", "italico", "sublinhado", "tachado"}
        assert str(j.barra_de_formatacao.botoes["negrito"].cget("style")) == "Negrito.Toolbutton"
        bloco = t.bloco(lambda b: isinstance(b, m.Paragrafo) and not isinstance(b, m.Titulo)
                        and len(m.texto_de(b)) > 6)
        texto.ir_para(bloco.id, 3)
        j._cursor_moveu(j.aba_ativa())
        assert not any(_formato(j).values())
        # com seleção: o botão liga o negrito, e a marca segue o estado real
        texto.selecionar(0, 4, bloco.id)
        j.barra_de_formatacao.botoes["negrito"].invoke()
        assert _formato(j)["negrito"] is True
        j.barra_de_formatacao.botoes["negrito"].invoke()
        assert _formato(j)["negrito"] is False
        # sem seleção, o Ctrl+B deixa o próximo caractere em negrito: a barra mostra
        texto.ir_para(bloco.id, 3)
        texto.alternar("italico")
        j.update()
        assert _formato(j)["italico"] is True
        # no código não há formato no cursor
        j.executar("alternar_modo")
        assert not any(_formato(j).values())


def test_o_painel_xadrez_tem_as_acoes_e_dispensa_a_barra():
    with Janela() as t:
        j = t.j
        painel = j.xadrez_controlador.painel
        assert set(painel.acoes) == {"Diagrama", "Posição", "Validar"}
        chamados = []
        j.comandos["validar_notacao"] = lambda: chamados.append("validar")
        painel.acoes["Validar"].invoke()
        assert chamados == ["validar"]
        assert j.paineis["xadrez"].visivel and not j.barra_de_xadrez.winfo_manager()
        j.mostrar_painel("xadrez", False)
        assert j.barra_de_xadrez.winfo_manager() == "pack"
        # a barra desligada no menu não volta nem com o painel fechado
        j.mostrar_barra("xadrez", False)
        assert not j.barra_de_xadrez.winfo_manager()


def test_propriedades_vazias_encolhem_e_devolvem_a_altura():
    with Janela() as t:
        j = t.j
        j.deiconify()
        j.geometry("1200x700+0+0")
        j.update()
        painel = j.painel_de_propriedades
        assert painel.vazio is False and painel.titulo.cget("text")
        antes = j.direita.sashpos(0)
        assert antes > j.ALTURA_DAS_PROPRIEDADES_VAZIAS + 8
        j.executar("alternar_modo")                 # no código não há nada sob o cursor do texto
        j.update()
        assert painel.vazio is True and painel.titulo.cget("text") == "" and not painel.rodape.winfo_ismapped()
        assert j.direita.sashpos(0) == j.ALTURA_DAS_PROPRIEDADES_VAZIAS
        j.executar("alternar_modo")
        j.update()
        assert painel.vazio is False and painel.rodape.winfo_ismapped()
        assert j.direita.sashpos(0) == antes
        j.withdraw()


def test_a_coluna_esquerda_em_abas():
    from ui.editor.janela import ColunaEmAbas

    with Janela() as t:
        j = t.j
        assert isinstance(j.esquerda, ColunaEmAbas)
        assert [j.esquerda.tab(q, "text") for q in j.esquerda.panes()] == ["Navegador", "Sumário", "Estilos"]
        # o foco num painel traz a aba dele à frente
        j.paineis["sumario"].foco()
        assert j.esquerda.select() == str(j.quadro_sumario)
        j.paineis["estilos"].foco()
        assert j.esquerda.select() == str(j.quadro_estilos)
        # esconder e mostrar: a aba sai e volta no lugar dela
        j.mostrar_painel("navegador", False)
        assert str(j.quadro_navegador) not in j.esquerda.panes()
        j.mostrar_painel("navegador", True)
        assert j.esquerda.panes()[0] == str(j.quadro_navegador)
        assert j.esquerda.tab(j.quadro_navegador, "text") == "Navegador"
        # sem nenhuma aba, a coluna sai da janela
        for nome in ("navegador", "sumario", "estilos"):
            j.mostrar_painel(nome, False)
        assert str(j.esquerda) not in j.paned.panes()
        j.mostrar_painel("estilos", True)
        assert str(j.esquerda) in j.paned.panes()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
