"""
Testes de `ui/editor/atalhos.py` (ED-02; SPEC_EDITOR §7.4): a tabela é única por
acorde e por modo, todo acorde de comando tem item de menu (AC-ED02-1), a ajuda
lista tudo — inclusive o `Ctrl+Tab` nativo e o `Enter` contextual —, e `ligar`
despacha para `comandos[nome]` consultado na hora, devolvendo `"break"` onde a
tabela manda e `None` onde o widget é quem decide.

Rodar sem pytest:      python tests/test_editor_atalhos.py
"""

import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from conftest import raiz_tk
from ui.editor import atalhos, menus


class _Evento:
    def __init__(self, keysym="", keycode=0, state=0, widget=None):
        self.keysym, self.keycode, self.state, self.widget = keysym, keycode, state, widget


def test_a_tabela_e_unica_por_acorde_e_por_modo_e_todo_comando_tem_item_de_menu():
    assert atalhos.verificar_unicidade() == []
    sem_item = [a.atalho for a in atalhos.TABELA if a.tipo == "comando" and menus.item_de(a.comando) is None]
    assert sem_item == []
    assert {a.atalho for a in atalhos.TABELA if a.tipo == "nativo"} == {"Ctrl+Tab", "Ctrl+Shift+Tab"}
    assert {a.comando for a in atalhos.TABELA if a.tipo == "contextual"} == {"", "menu_de_contexto", "escape"}
    for a in atalhos.TABELA:                       # nenhum Ctrl+Alt (AltGr), nenhum Alt+letra (mnemônicos)
        assert "Ctrl+Alt" not in a.atalho, a.atalho
        assert not (a.atalho.startswith("Alt+") and len(a.atalho) == 5 and a.atalho[4].isalpha()), a.atalho
    # um acorde só muda de sentido entre modos quando é o mesmo acorde em modos distintos (†)
    por_acorde = {}
    for a in atalhos.TABELA:
        for modo in a.modos:
            assert por_acorde.setdefault((a.sequencia, a.keycode, modo), a.comando) == a.comando


def test_a_ajuda_lista_todos_os_acordes_e_o_acelerador_vem_da_tabela():
    ajuda = atalhos.texto_de_ajuda()
    for a in atalhos.TABELA:
        assert a.atalho in ajuda, a.atalho
    assert "Ctrl+Tab" in ajuda and "(nativo)" in ajuda and "(contextual)" in ajuda
    assert atalhos.acelerador("salvar_como") == "Ctrl+Shift+S"
    assert atalhos.acelerador("comando_que_nao_existe") == ""
    assert menus.acelerador_no_modo("dividir_capitulo", "texto") == "Ctrl+Shift+Enter"
    assert menus.acelerador_no_modo("dividir_capitulo", "codigo") == "Ctrl+Enter"
    assert menus.acelerador_no_modo("limpar_caractere", "codigo") == "Ctrl+Space"


def test_ligar_despacha_pelo_dicionario_na_hora_respeita_o_modo_e_o_keycode():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        texto = tk.Text(raiz)
        chamados = []
        comandos = {"salvar": lambda: chamados.append("salvar"), "fonte": lambda: chamados.append("fonte"),
                    "entrelinha_15": lambda: chamados.append("entrelinha_15"),
                    "estilo_titulo3": lambda: chamados.append("titulo3"), "zoom_zero": lambda: chamados.append("zoom0"),
                    "versalete": lambda: chamados.append("versalete")}
        modo = {"atual": "texto"}
        ligacao = atalhos.ligar(texto, atalhos.TABELA, comandos, lambda: modo["atual"])
        assert texto.bindtags()[1] == ligacao.bindtag
        for seq in ("<Control-s>", "<Control-d>", "<Control-Key>", "<Alt-Key>", "<Key-Insert>", "<<PasteSelection>>",
                    "<<Paste>>", "<Control-Tab>", "<Control-space>"):
            assert texto.bind_class(ligacao.bindtag, seq), seq
        assert "<Escape>" not in ligacao.handlers                    # é de fundo: só na janela
        h = ligacao.handlers
        assert h["<Control-s>"](_Evento("s", 0x53, atalhos.CONTROL)) == "break" and chamados[-1] == "salvar"
        assert h["<Control-d>"](_Evento("d", 0x44, atalhos.CONTROL)) == "break" and chamados[-1] == "fonte"
        # keycode: Ctrl+5 → entrelinha 1,5; Ctrl+7 não é de ninguém → None (segue para o widget)
        assert h["<Control-Key>"](_Evento("5", 0x35, atalhos.CONTROL)) == "break" and chamados[-1] == "entrelinha_15"
        assert h["<Control-Key>"](_Evento("7", 0x37, atalhos.CONTROL)) is None
        # Ctrl+0 → zoom 100%; Alt+3 → título 3; AltGr+3 (Control+Alt) não
        assert h["<Control-Key>"](_Evento("0", 0x30, atalhos.CONTROL)) == "break" and chamados[-1] == "zoom0"
        assert h["<Alt-Key>"](_Evento("3", 0x33, atalhos.ALT)) == "break" and chamados[-1] == "titulo3"
        assert h["<Alt-Key>"](_Evento("3", 0x33, atalhos.ALT | atalhos.CONTROL)) is None
        # comando com lar mas ainda sem função (fase seguinte): "break", para o Text não agir
        assert h["<Control-f>"](_Evento("f", 0x46, atalhos.CONTROL)) == "break" and chamados[-1] == "titulo3"
        # fora do modo: "break" sem chamar ninguém (Ctrl+Shift+K é só do texto; no código não é do Text)
        n = len(chamados)
        assert h["<Control-Shift-K>"](_Evento("K", 0x4B, atalhos.CONTROL | atalhos.SHIFT)) == "break"
        assert chamados[-1] == "versalete"
        modo["atual"] = "codigo"
        assert h["<Control-Shift-K>"](_Evento("K", 0x4B, atalhos.CONTROL | atalhos.SHIFT)) == "break"
        assert len(chamados) == n + 1
        assert h["<Control-Key>"](_Evento("5", 0x35, atalhos.CONTROL)) == "break" and len(chamados) == n + 1
        assert h["<Control-Key>"](_Evento("7", 0x37, atalhos.CONTROL)) is None
        # o dicionário é consultado na hora: um espião posto depois é o que roda
        comandos["salvar"] = lambda: chamados.append("espiao")
        assert h["<Control-s>"](_Evento("s", 0x53, atalhos.CONTROL)) == "break" and chamados[-1] == "espiao"
        # neutralizações
        assert texto.bind_class(ligacao.bindtag, "<Key-Insert>") and texto.bind_class(ligacao.bindtag, "<<PasteSelection>>")
    finally:
        raiz.destroy()


def test_ligar_na_janela_liga_so_os_escopos_de_janela_e_fundo():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        chamados = []
        ligacao = atalhos.ligar(raiz, atalhos.TABELA, {"escape": lambda: chamados.append("esc"),
                                                      "salvar": lambda: chamados.append("salvar")},
                                lambda: "texto", escopos=("janela", "fundo"), frente=False)
        assert "<Escape>" in ligacao.handlers and "<Control-s>" in ligacao.handlers
        assert "<<Paste>>" not in ligacao.handlers and "<Control-b>" not in ligacao.handlers
        assert raiz.bind("<Escape>") and raiz.bind("<Control-s>")
        assert ligacao.handlers["<Escape>"](_Evento("Escape", 27, 0)) == "break" and chamados == ["esc"]
    finally:
        raiz.destroy()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
