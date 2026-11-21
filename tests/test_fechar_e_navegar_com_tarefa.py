"""Fechar e navegar com tarefa rodando (RG-13, R-17).

- Fechar a janela cancelava a tarefa antes de confirmar o descarte: recusar deixava a
  tarefa cancelada e a janela aberta; e destruía sem esperar a thread, que podia estar no
  meio de uma gravação.
- Durante a sondagem de "Exportar livro" (que não é tarefa), PgDn entrava no
  `_load_pdf_page`, que só consultava `task.is_running()`: a página era arquivada, os botões
  desabilitados, e o `_run_task` recusava sem religá-los.
"""

import os
import tempfile
import threading
import time

from tkinter import messagebox

from PIL import Image

from core.box_model import BoxEntry
from tests.test_trabalho_fora_da_interface import _App


def _pagina_suja(app, tmp):
    imagem = os.path.join(tmp, "pagina.png")
    Image.new("L", (200, 80), 255).save(imagem)
    app.win.open_image(imagem)
    app.win.boxes.append(BoxEntry("a", 10, 10, 20, 30))
    app.win._commit_change()


def _tarefa_que_espera(app):
    terminou = threading.Event()

    def trabalho(h):
        while not h.cancelled:
            time.sleep(0.02)
        time.sleep(0.2)                      # o fim de uma gravação, depois do pedido
        terminou.set()
        h.raise_if_cancelled()

    app.win._run_task("Gravando", trabalho, lambda r: None)
    assert app.win.task.is_running()
    return terminou


def test_recusar_o_descarte_nao_cancela_a_tarefa(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        _pagina_suja(app, tmp)
        terminou = _tarefa_que_espera(app)
        respostas = {"Operação em andamento": True, "Trabalho não salvo": False}
        monkeypatch.setattr(messagebox, "askyesno", lambda titulo, *a, **k: respostas[titulo])
        canceladas = []
        cancelar = app.win.task.cancel
        monkeypatch.setattr(app.win.task, "cancel", lambda: (canceladas.append(1), cancelar())[1])
        app.win._on_close()
        assert app.win.task.is_running() and not canceladas, "recusar o descarte deixou a tarefa cancelada"
        assert app.root.winfo_exists()
        app.win.task.cancel()
        terminou.wait(5)
        app.aguardar()


def test_fechar_espera_a_thread_antes_de_destruir(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        _pagina_suja(app, tmp)
        terminou = _tarefa_que_espera(app)
        monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
        monkeypatch.setattr(app.win, "gravar_estado_da_janela", lambda: None)
        app.win._on_close()
        assert terminou.is_set(), "a janela foi destruída com a thread no meio do trabalho"


def test_virar_a_pagina_durante_a_sondagem_avisa_e_nao_trava_os_botoes(monkeypatch):
    with _App() as app:
        win = app.win
        caixas = []
        monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: caixas.append(a))
        arquivadas = []
        win.session = type("S", (), {"store": lambda self, p, b: arquivadas.append(p)})()
        win._sondando = "Conferindo a camada de texto do PDF"
        win.navigation.target = lambda i: None
        win.btn_next_page.config(state="normal")
        win._load_pdf_page(1)
        assert "Aguarde" in win.status.lbl.cget("text"), "a página não virou e a barra não disse por quê"
        assert not arquivadas, "a página foi arquivada sem virar"
        assert str(win.btn_next_page.cget("state")) != "disabled", "os botões ficaram desabilitados"
        assert not caixas, "virar a página abriu caixa em vez de avisar na barra"
        assert win._motivo_de_espera() and "camada" in win._motivo_de_espera()
        win._sondando = None
        assert win._motivo_de_espera() is None
