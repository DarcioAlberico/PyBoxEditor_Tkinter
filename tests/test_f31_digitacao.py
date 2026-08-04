"""
Testes da F3.1 — modo digitação contínua.

Fora do modo, rotular um caractere custa duas teclas: o caractere e o Enter.
Numa página de 2.000 caracteres são 2.000 teclas a mais.

Rodar sem pytest:      python tests/test_f31_digitacao.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import raiz_tk

import tkinter as tk
from tkinter import messagebox
from PIL import Image

from core.box_model import BoxEntry
from ui import confidence as cf


class _Tecla:
    """Evento de tecla suficiente para o handler."""
    def __init__(self, char=""):
        self.char = char


class _App:
    def __enter__(self):
        from ui.main_window import MainWindow
        self._info, self._erro = messagebox.showinfo, messagebox.showerror
        messagebox.showinfo = lambda *a, **k: None
        messagebox.showerror = lambda *a, **k: None
        self.root = raiz_tk()
        self.win = MainWindow(self.root)
        self.win.image = Image.new("L", (400, 100), color=255)
        # Janela retirada da tela não tem foco de verdade; o handler consulta
        # focus_get() para não roubar teclas de campos de texto.
        self.win.parent.focus_get = lambda: self.win.canvas
        return self

    def __exit__(self, *a):
        messagebox.showinfo, messagebox.showerror = self._info, self._erro
        try:
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass


def _pagina(win, n=5):
    win.boxes = [BoxEntry("", i * 10, 0, i * 10 + 9, 9) for i in range(n)]
    win.selected_index = 0
    win.update_sidebar()
    win.select_box(0)


# ----------------------------------------------------------------------
# Ligar / desligar
# ----------------------------------------------------------------------

def test_f2_liga_e_desliga():
    with _App() as app:
        w = app.win
        _pagina(w)
        assert w.modo_digitacao is False

        w.alternar_modo_digitacao()
        assert w.modo_digitacao is True
        assert "DIGITAÇÃO" in w.lbl_modo.cget("text")

        w.alternar_modo_digitacao()
        assert w.modo_digitacao is False
        assert w.lbl_modo.cget("text") == ""


def test_esc_sai_do_modo():
    with _App() as app:
        w = app.win
        _pagina(w)
        w.alternar_modo_digitacao(True)
        w._on_key_escape(_Tecla("\x1b"))
        assert w.modo_digitacao is False


def test_nao_liga_sem_boxes():
    with _App() as app:
        w = app.win
        w.boxes = []
        w.update_sidebar()
        w.alternar_modo_digitacao(True)
        assert w.modo_digitacao is False
        assert "não tem boxes" in w.status.lbl.cget("text")


# ----------------------------------------------------------------------
# O comportamento central
# ----------------------------------------------------------------------

def test_tecla_aplica_e_avanca():
    """Uma tecla = um caractere rotulado. Sem Enter."""
    with _App() as app:
        w = app.win
        _pagina(w)
        w.alternar_modo_digitacao(True)

        for ch in "abc":
            w._on_tecla_digitacao(_Tecla(ch))

        assert [b.char for b in w.boxes[:3]] == ["a", "b", "c"]
        assert w.selected_index == 3, "não avançou sozinho"


def test_digitar_marca_como_manual():
    """O usuário é autoridade: o box tem que sair do vermelho (ver F3.2)."""
    with _App() as app:
        w = app.win
        w.boxes = [BoxEntry("c", 0, 0, 9, 9, confidence=0.2, source="easyocr")]
        w.update_sidebar()
        w.select_box(0)
        w.alternar_modo_digitacao(True)

        w._on_tecla_digitacao(_Tecla("e"))

        b = w.boxes[0]
        assert (b.char, b.source, b.confidence) == ("e", "manual", 1.0)
        assert cf.cor_do_box(b) == cf.COR_ALTA


def test_espaco_pula_sem_alterar():
    """Na revisão a maioria está certa: dá para passar sem digitar nada."""
    with _App() as app:
        w = app.win
        w.boxes = [
            BoxEntry("a", 0, 0, 9, 9, confidence=0.9, source="neural"),
            BoxEntry("b", 10, 0, 19, 9, confidence=0.9, source="neural"),
        ]
        w.update_sidebar()
        w.select_box(0)
        w.alternar_modo_digitacao(True)

        w._on_tecla_digitacao(_Tecla(" "))

        assert w.boxes[0].char == "a", "espaço não pode alterar o caractere"
        assert w.boxes[0].source == "neural", "espaço não pode marcar como manual"
        assert w.selected_index == 1


def test_backspace_volta_sem_excluir():
    """Fora do modo, Backspace exclui o box. Dentro, volta um."""
    with _App() as app:
        w = app.win
        _pagina(w, 3)
        w.alternar_modo_digitacao(True)
        w._on_tecla_digitacao(_Tecla("a"))
        w._on_tecla_digitacao(_Tecla("b"))
        assert w.selected_index == 2

        w._on_key_backspace(_Tecla("\x08"))

        assert len(w.boxes) == 3, "Backspace excluiu um box no modo digitação"
        assert w.selected_index == 1


def test_backspace_fora_do_modo_ainda_exclui():
    with _App() as app:
        w = app.win
        _pagina(w, 3)
        w.select_box(1)
        w._on_key_backspace(_Tecla("\x08"))
        assert len(w.boxes) == 2


# ----------------------------------------------------------------------
# O que NÃO pode acontecer
# ----------------------------------------------------------------------

def test_teclas_de_controle_passam_direto():
    """Setas, F3 e Ctrl+algo têm char vazio ou não imprimível: o modo os ignora
    para que sigam para seus atalhos."""
    with _App() as app:
        w = app.win
        _pagina(w)
        w.alternar_modo_digitacao(True)
        antes = w.selected_index

        for ch in ("", "\x13", "\x1a", "\r", "\t"):     # nada, Ctrl+S, Ctrl+Z, Enter, Tab
            assert w._on_tecla_digitacao(_Tecla(ch)) is None, f"consumiu {ch!r}"

        assert w.selected_index == antes
        assert all(b.char == "" for b in w.boxes), "escreveu caractere de controle"


def test_campo_de_texto_com_foco_tem_prioridade():
    """Digitar na busca não pode rotular boxes."""
    with _App() as app:
        w = app.win
        _pagina(w)
        w.alternar_modo_digitacao(True)
        w.parent.focus_get = lambda: w.entry_busca

        assert w._on_tecla_digitacao(_Tecla("a")) is None
        assert w.boxes[0].char == "", "a tecla foi para o box em vez do campo"


def test_fora_do_modo_a_tecla_nao_faz_nada():
    with _App() as app:
        w = app.win
        _pagina(w)
        assert w._on_tecla_digitacao(_Tecla("a")) is None
        assert w.boxes[0].char == ""


def test_d_nao_divide_mais_box():
    """
    'd' estava ligado a "dividir box" na janela inteira. Com o modo digitação
    isso seria um bug: digitar 'd' partiria um box em dois.
    """
    with _App() as app:
        w = app.win
        _pagina(w, 3)

        assert w.parent.bind("d") == "", "'d' ainda dispara comando"
        assert w.parent.bind("<Control-d>") != "", "Ctrl+D não foi ligado"

        w.alternar_modo_digitacao(True)
        w._on_tecla_digitacao(_Tecla("d"))

        assert len(w.boxes) == 3, "digitar 'd' dividiu um box"
        assert w.boxes[0].char == "d"


def test_foco_fica_no_canvas_durante_o_modo():
    """Se o Entry recuperar o foco, ele passa a consumir as teclas e o modo
    para de funcionar."""
    with _App() as app:
        w = app.win
        _pagina(w)
        w.alternar_modo_digitacao(True)

        chamou = []
        w.char_entry.focus_set = lambda: chamou.append(True)

        w._on_tecla_digitacao(_Tecla("a"))
        w.apply_char_and_next()

        assert not chamou, "o modo digitação devolveu o foco ao campo de texto"


# ----------------------------------------------------------------------
# Interação com os filtros da F3.3
# ----------------------------------------------------------------------

def test_avanca_dentro_do_filtro():
    with _App() as app:
        w = app.win
        w.boxes = [
            BoxEntry("", 0, 0, 9, 9),                                        # 0 pendente
            BoxEntry("x", 10, 0, 19, 9, confidence=0.99, source="neural"),   # 1 ok
            BoxEntry("", 20, 0, 29, 9),                                      # 2 pendente
        ]
        w.update_sidebar()
        w.var_so_pendentes.set(True)
        w.on_boxes_changed_view()
        w.select_box(0)
        w.alternar_modo_digitacao(True)

        w._on_tecla_digitacao(_Tecla("a"))

        # corrigido, o box 0 sai do filtro; a lista encolhe e o cursor fica
        # sobre o próximo pendente, sem pular o 2
        assert w.boxes[0].char == "a"
        assert w.selected_index == 2, "pulou um pendente"


def test_status_mostra_progresso():
    with _App() as app:
        w = app.win
        _pagina(w, 4)
        w.alternar_modo_digitacao(True)
        texto = w.status.lbl.cget("text")
        assert "DIGITAÇÃO" in texto
        assert "4 pendentes" in texto

        w._on_tecla_digitacao(_Tecla("a"))
        assert "3 pendentes" in w.status.lbl.cget("text")


# ----------------------------------------------------------------------
# Execução direta
# ----------------------------------------------------------------------

def _main():
    testes = [(n, o) for n, o in sorted(globals().items())
              if n.startswith("test_") and callable(o)]
    falhas = []
    for nome, fn in testes:
        try:
            fn()
            print(f"  PASS  {nome}")
        except Exception as e:
            falhas.append(nome)
            print(f"  FALHA {nome}\n          {type(e).__name__}: {e}")
    print(f"\n{len(testes) - len(falhas)}/{len(testes)} testes passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(_main())
