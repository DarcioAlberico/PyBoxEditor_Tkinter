"""
F3.5 — os atalhos que faltavam: Ctrl+O e Tab/Shift+Tab.

Ctrl+S, Ctrl+Shift+S e PgUp/PgDn já tinham entrado junto com a F3.7, quando os
boxes passaram a persistir por página; sem eles não haveria como gravar o
trabalho acumulado.

O que estes testes protegem é menos o atalho e mais o que ele não pode quebrar:
o Tab devolve "break" e por isso **desliga a travessia de foco do Tk** na
janela principal. Se algum dia isso passar a valer também dentro dos diálogos,
o usuário fica sem como andar entre os campos deles.

Rodar sem pytest:      python tests/test_f35_atalhos.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from tkinter import messagebox

import pytest
from PIL import Image

from core.box_model import BoxEntry


class _App:
    def __enter__(self):
        from ui.main_window import MainWindow
        self._info, self._erro = messagebox.showinfo, messagebox.showerror
        messagebox.showinfo = lambda *a, **k: None
        messagebox.showerror = lambda *a, **k: None
        self.root = tk.Tk()
        self.root.withdraw()
        self.win = MainWindow(self.root)
        self.win.image = Image.new("L", (400, 100), color=255)
        return self

    def __exit__(self, *a):
        messagebox.showinfo, messagebox.showerror = self._info, self._erro
        try:
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass


def _pagina(win, n=5):
    win.boxes = [BoxEntry(chr(ord("a") + i), i * 20, 0, i * 20 + 15, 15,
                          confidence=0.5, source="neural") for i in range(n)]
    win.selected_index = 0
    win.update_sidebar()


# ----------------------------------------------------------------------
# Tab e Shift+Tab
# ----------------------------------------------------------------------

def test_tab_avanca_um_box():
    with _App() as app:
        w = app.win
        _pagina(w)
        w.select_box(1)
        w._on_key_tab(1)
        assert w.selected_index == 2


def test_shift_tab_volta_um_box():
    with _App() as app:
        w = app.win
        _pagina(w)
        w.select_box(3)
        w._on_key_tab(-1)
        assert w.selected_index == 2


def test_tab_para_na_ponta_em_vez_de_dar_a_volta():
    """Igual às setas. Dar a volta faria o revisor perder o lugar sem notar."""
    with _App() as app:
        w = app.win
        _pagina(w, 3)
        w.select_box(2)
        w._on_key_tab(1)
        assert w.selected_index == 2

        w.select_box(0)
        w._on_key_tab(-1)
        assert w.selected_index == 0


def test_tab_devolve_break_para_o_tk_nao_mover_o_foco():
    with _App() as app:
        w = app.win
        _pagina(w)
        assert w._on_key_tab(1) == "break"


def test_tab_sem_boxes_nao_quebra():
    with _App() as app:
        w = app.win
        w.boxes = []
        w.selected_index = -1
        assert w._on_key_tab(1) == "break"


def test_tab_deixa_o_foco_pronto_para_digitar():
    """
    Numa janela retirada da tela o Tk não atribui foco de verdade, então
    `focus_get()` não serve de asserção — a via é espiar a chamada, como já
    faz `test_f31_digitacao`.
    """
    with _App() as app:
        w = app.win
        _pagina(w)
        pediu = []
        w.char_entry.focus_set = lambda: pediu.append(True)

        w._on_key_tab(1)
        assert pediu == [True]


def test_tab_no_modo_digitacao_nao_rouba_o_foco():
    """Lá quem recebe as teclas é a janela; tirar o foco desligaria o modo."""
    with _App() as app:
        w = app.win
        _pagina(w)
        w.alternar_modo_digitacao(True)
        pediu = []
        w.char_entry.focus_set = lambda: pediu.append(True)

        w._on_key_tab(1)
        assert w.selected_index == 1
        assert pediu == []


def test_tab_respeita_o_filtro_da_lista():
    """Com filtro ativo, o Tab anda no que está visível, não no que está oculto."""
    with _App() as app:
        w = app.win
        _pagina(w, 5)
        w.boxes[1].confidence = 0.99
        w.boxes[3].confidence = 0.99
        w.var_so_pendentes.set(True)
        w.update_sidebar()

        visiveis = w.boxes_visiveis()
        assert 1 not in visiveis and 3 not in visiveis

        w.select_box(visiveis[0])
        w._on_key_tab(1)
        assert w.selected_index == visiveis[1]


def test_tab_esta_ligado_nas_tres_formas():
    with _App() as app:
        ligadas = app.win.parent.bind()
        assert "<Key-Tab>" in ligadas
        # ISO_Left_Tab é como o X11 entrega o Shift+Tab.
        assert "<Shift-Key-Tab>" in ligadas or "<Key-ISO_Left_Tab>" in ligadas


# ----------------------------------------------------------------------
# Ctrl+O
# ----------------------------------------------------------------------

def test_ctrl_o_esta_ligado():
    with _App() as app:
        assert "<Control-Key-o>" in app.win.parent.bind()


def test_abrir_documento_manda_pdf_para_o_leitor_de_pdf(tmp_path):
    with _App() as app:
        w = app.win
        chamadas = []
        w.open_pdf = lambda p=None: chamadas.append(("pdf", p))
        w.open_image = lambda p=None: chamadas.append(("imagem", p))

        w.abrir_documento(str(tmp_path / "livro.PDF"))
        assert chamadas == [("pdf", str(tmp_path / "livro.PDF"))]


@pytest.mark.parametrize("nome", ["p.png", "p.JPG", "p.jpeg", "p.tif", "p.bmp"])
def test_abrir_documento_manda_imagem_para_o_leitor_de_imagem(nome, tmp_path):
    with _App() as app:
        w = app.win
        chamadas = []
        w.open_pdf = lambda p=None: chamadas.append(("pdf", p))
        w.open_image = lambda p=None: chamadas.append(("imagem", p))

        w.abrir_documento(str(tmp_path / nome))
        assert chamadas[0][0] == "imagem"


def test_cancelar_o_dialogo_de_abrir_nao_faz_nada():
    with _App() as app:
        w = app.win
        chamadas = []
        w.open_pdf = lambda p=None: chamadas.append("pdf")
        w.open_image = lambda p=None: chamadas.append("imagem")

        w.abrir_documento("")
        assert chamadas == []


# ----------------------------------------------------------------------
# Os que já existiam continuam existindo
# ----------------------------------------------------------------------

@pytest.mark.parametrize("atalho", [
    "<Control-Key-s>",      # salvar página
    "<Control-Key-S>",      # salvar todas
    "<Key-Prior>",          # PgUp
    "<Key-Next>",           # PgDn
    "<Control-Key-e>",      # aplicar aos semelhantes (F3.6)
    "<Control-Key-d>",      # dividir box
    "<Control-Key-f>",      # busca
    "<Control-Key-b>",      # rascunho
    "<Control-Key-z>",      # desfazer
    "<Key-F2>", "<Key-F3>", "<Key-F4>",
])
def test_atalho_continua_ligado(atalho):
    with _App() as app:
        assert atalho in app.win.parent.bind()


def test_nenhum_atalho_esta_ligado_duas_vezes():
    with _App() as app:
        ligadas = list(app.win.parent.bind())
        assert len(ligadas) == len(set(ligadas))


def _comandos(menu):
    """[(rótulo, acelerador)] das entradas de comando de um menu."""
    saida = []
    for i in range(menu.index("end") + 1):
        if menu.type(i) == "command":
            saida.append((menu.entrycget(i, "label"),
                          menu.entrycget(i, "accelerator")))
    return saida


def _submenu(janela, rotulo):
    barra = janela.parent.nametowidget(janela.parent.cget("menu"))
    for i in range(barra.index("end") + 1):
        if barra.type(i) == "cascade" and barra.entrycget(i, "label") == rotulo:
            return barra.nametowidget(barra.entrycget(i, "menu"))
    raise AssertionError(f"menu {rotulo!r} não existe")


def test_menu_anuncia_os_atalhos():
    """Atalho que não aparece no menu é atalho que ninguém descobre."""
    with _App() as app:
        arquivo = dict(_comandos(_submenu(app.win, "Arquivo")))
        assert arquivo["Abrir..."] == "Ctrl+O"
        assert arquivo["Salvar .box (página atual)"] == "Ctrl+S"
        assert arquivo["Salvar todas as páginas..."] == "Ctrl+Shift+S"

        ferramentas = dict(_comandos(_submenu(app.win, "Ferramentas")))
        assert ferramentas["Aplicar a todos os semelhantes..."] == "Ctrl+E"
        assert ferramentas["Dividir box selecionado"] == "Ctrl+D"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
