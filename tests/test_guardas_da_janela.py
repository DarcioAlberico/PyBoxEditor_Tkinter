"""Guardas de foco e de tarefa na janela principal.

Dois defeitos que a revisão de 2026-09-18 encontrou lendo o código:

- `Delete`/`Backspace` estavam ligados na raiz sem guarda de foco. A binding
  de classe do `Entry` rodava primeiro (apagava a letra) e a da raiz rodava
  depois (apagava o **box**): corrigir o campo "Caractere" — o destino do Tab
  e do Enter — custava um box.
- `_run_task` ignorava o `False` de `task.start()`: o handler que esquecia o
  `_busy` (o treino de diagramas esquecia) reiniciava a barra de status com o
  título novo e o trabalho não rodava — a tela dizia que sim.
"""

import sys
import time
from tkinter import messagebox

import pytest
from PIL import Image

from conftest import raiz_tk
from core.box_model import BoxEntry


class _App:
    def __enter__(self):
        from ui.main_window import MainWindow
        self._info, self._erro = messagebox.showinfo, messagebox.showerror
        self.avisos = []
        messagebox.showinfo = lambda t="", m="", *a, **k: self.avisos.append(m)
        messagebox.showerror = lambda *a, **k: None
        self.root = raiz_tk()
        if self.root is None:
            pytest.skip("sem display")
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


def _pagina(win, n=3):
    win.boxes = [BoxEntry(chr(ord("a") + i), i * 20, 0, i * 20 + 15, 15,
                          confidence=0.5, source="neural") for i in range(n)]
    win.selected_index = 1
    win.update_sidebar()


class _Tecla:
    def __init__(self, char=""):
        self.char = char
        self.keysym = ""
        self.state = 0


def test_delete_com_foco_num_campo_de_texto_nao_exclui_o_box():
    with _App() as app:
        w = app.win
        _pagina(w)
        w._foco_em_campo_de_texto = lambda: True
        assert w._on_key_delete(_Tecla()) is None
        assert w._on_key_backspace(_Tecla("\x08")) is None
        assert len(w.boxes) == 3


def test_delete_fora_de_campo_de_texto_ainda_exclui():
    with _App() as app:
        w = app.win
        _pagina(w)
        w._foco_em_campo_de_texto = lambda: False
        w._on_key_delete(_Tecla())
        assert len(w.boxes) == 2


def test_run_task_recusa_uma_segunda_tarefa_e_avisa():
    with _App() as app:
        w = app.win
        primeira = w._run_task("Primeira", lambda h: time.sleep(0.3), lambda r: None)
        assert primeira is True
        segunda = w._run_task("Segunda", lambda h: None, lambda r: None)
        assert segunda is False
        assert any("Segunda" in aviso and "em andamento" in aviso
                   for aviso in app.avisos)
        limite = time.time() + 5
        while w.task.is_running() and time.time() < limite:
            app.root.update()
            time.sleep(0.01)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
