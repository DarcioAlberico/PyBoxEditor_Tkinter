"""
Tudo pelo teclado (ED-13; SPEC_EDITOR AC-006, §13.2): os painéis por `F6`/`Shift+F6` de
verdade — `event_generate` numa janela com `deiconify` + `focus_force` (`gui`); os acordes
da tabela têm item de menu ou comando registrado; `Shift+F10` e a tecla de menu abrem o
contexto; o editor de posição inteiro pelo teclado (setas, letra, Shift+letra, Delete, F,
Enter); e o roteiro `docs/roteiros/editor_teclado.md` existe com a tabela preenchida.

Rodar sem pytest:      .venv/Scripts/python.exe tests/test_editor_teclado.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import modelo as m
from editor_ambiente import Janela
from ui.editor import atalhos as atalhos_mod, menus
from ui.editor.janela import ORDEM_DOS_PAINEIS

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Evento:
    def __init__(self, keysym="", char="", state=0):
        self.keysym, self.char, self.state = keysym, char, state


@pytest.mark.gui
def test_gui_f6_percorre_os_paineis_e_shift_f6_volta():
    with Janela() as t:
        j = t.j
        j.deiconify()
        j.focus_force()
        j.update()
        j.paineis["navegador"].foco()
        j.update()
        assert j._painel_com_foco() == "navegador"
        percorridos = []
        for _ in range(len(ORDEM_DOS_PAINEIS)):
            alvo = j.focus_get() or j
            alvo.event_generate("<F6>")
            j.update()
            percorridos.append(j._painel_com_foco())
        assert percorridos == list(ORDEM_DOS_PAINEIS[1:]) + [ORDEM_DOS_PAINEIS[0]]
        (j.focus_get() or j).event_generate("<Shift-F6>")
        j.update()
        assert j._painel_com_foco() == ORDEM_DOS_PAINEIS[-1]
        j.withdraw()


def test_toda_tecla_da_tabela_tem_comando_e_todo_comando_de_menu_tem_lar():
    with Janela() as t:
        j = t.j
        sem_comando = [a.comando for a in atalhos_mod.TABELA
                       if a.comando and a.tipo != "nativo" and a.comando not in j.comandos]
        assert sem_comando == [], sem_comando                        # toda tecla da §7.4 chega a um comando
        sem_menu = [a.comando for a in atalhos_mod.TABELA if menus.item_de(a.comando) is None
                    and a.comando not in ("painel_seguinte", "painel_anterior", "escape", "foco_no_editor",
                                          "menu_de_contexto", "aumentar_fonte", "diminuir_fonte")]
        assert len(sem_menu) <= 12, sem_menu                           # os acordes de navegação não têm item (§7.4)
        # o contexto por Shift+F10 e pela tecla de menu
        sequencias = {a.sequencia for a in atalhos_mod.TABELA}
        assert "<Shift-F10>" in sequencias and any("App" in s or "Menu" in s for s in sequencias)
        assert "menu_de_contexto" in j.comandos and j.menus.contexto("texto") is not None
        # o texto de ajuda dos atalhos lista a tabela inteira
        ajuda = atalhos_mod.texto_de_ajuda()
        assert "F6" in ajuda and "Ctrl+Shift+D" in ajuda and "Shift+F10" in ajuda


def test_o_editor_de_posicao_inteiro_pelo_teclado():
    from core.tabuleiro_edicao import TabuleiroEdicao
    from ui.editor.diagrama import DialogoDeDiagrama

    with Janela() as t:
        j = t.j
        texto = t.texto
        texto.ir_para(texto.ordem[1], 0)
        t.caixas.diagrama_resposta = m.Diagrama(fen="8/8/8/8/8/8/8/8 w - - 0 1", lado="")
        bloco_id = j.executar("inserir_diagrama")                    # Ctrl+Shift+D → a caixa
        texto.selecionar_objeto(bloco_id)
        caixa = DialogoDeDiagrama(j, texto.modelo_de(bloco_id), idioma="pt")
        caixa.construir()
        tab = caixa.tabuleiro
        tab.selecionada = (7, 0)                                       # a1
        for _ in range(4):
            assert tab._na_tecla(_Evento("Right")) == "break"
        assert tab._na_tecla(_Evento("r", "r")) == "break"             # R de rei (pt), branco, em e1
        for _ in range(7):
            tab._na_tecla(_Evento("Up"))
        assert tab._na_tecla(_Evento("R", "R", state=0x1)) == "break"  # Shift: rei preto, em e8
        tab._na_tecla(_Evento("Left"))
        tab._na_tecla(_Evento("d", "d"))                               # dama branca em d8
        tab._na_tecla(_Evento("Delete"))                               # apagada
        assert tab._na_tecla(_Evento("f", "f")) == "break" and tab.orientacao == "preta"
        assert tab._na_tecla(_Evento("Return")) is None                # o Enter sobe para a caixa (OK)
        novo = caixa.confirmar()
        posicao = TabuleiroEdicao.de_fen(novo.fen)
        assert posicao.casa(7, 4).simbolo == "K" and posicao.casa(0, 4).simbolo == "k" and posicao.casa(0, 3).simbolo is None
        assert novo.orientacao == "preta"
        texto.selecionar_objeto(bloco_id)
        assert j.executar("editar_posicao", novo).fen == novo.fen      # Ctrl+Shift+P / Enter sobre o diagrama
        assert texto.modelo_de(bloco_id).orientacao == "preta"


def test_o_roteiro_do_teclado_existe_e_esta_preenchido():
    caminho = os.path.join(RAIZ, "docs", "roteiros", "editor_teclado.md")
    assert os.path.isfile(caminho)
    texto = open(caminho, encoding="utf-8").read()
    assert "F6" in texto and "Shift+F10" in texto and "Alt+" in texto and "AnelDeFoco" in texto
    linhas = [li for li in texto.splitlines() if li.startswith("| ") and li[2:3].isdigit()]
    assert len(linhas) >= 10 and all("✅" in li or "—" in li for li in linhas)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
