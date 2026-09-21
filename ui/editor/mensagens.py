"""
O painel Mensagens: o texto percorrível que ecoa o logger `pyboxeditor.editor`
(ED-02; SPEC_EDITOR §7.5, §13.4).

A barra de status é só visual — um leitor de tela não a anuncia, e uma mensagem
que passou já passou. O painel é o canal redundante: tudo o que importa (modo,
salvo, erro de validação, exportação, abertura) vai também para cá como INFO e
fica. O `logging.Handler` recebe o registro em qualquer thread: na thread da
interface escreve na hora; de outra, põe numa fila que o painel esvazia por
`after` — chamar o Tk de outra thread (mesmo `after`) levanta "main thread is not
in main loop" fora do `mainloop`, e a fila é o que o `task_service` também usa.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Any

NOME_DO_LOGGER = "pyboxeditor.editor"
LIMITE_DE_LINHAS = 2000
INTERVALO_DA_FILA_MS = 200


def logger() -> logging.Logger:
    return logging.getLogger(NOME_DO_LOGGER)


class PainelDeMensagens(ttk.Frame):
    def __init__(self, master: tk.Misc, **kw: Any):
        super().__init__(master, **kw)
        self.texto = tk.Text(self, height=6, wrap="word", state="disabled", highlightthickness=2,
                             font=("Segoe UI", 9), exportselection=False)
        barra = ttk.Scrollbar(self, orient="vertical", command=self.texto.yview)
        self.texto.configure(yscrollcommand=barra.set)
        self.texto.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.texto.tag_configure("WARNING", foreground="#8a5a00")
        self.texto.tag_configure("ERROR", foreground="#b00020")
        self.texto.tag_configure("CRITICAL", foreground="#b00020")
        self.linhas: list[tuple[str, str]] = []
        self._fila: queue.SimpleQueue = queue.SimpleQueue()
        self._handler = _HandlerDoPainel(self)
        self._esvaziar_id: str | None = None
        self._agendar_esvaziamento()

    def _agendar_esvaziamento(self) -> None:
        try:
            self._esvaziar_id = self.after(INTERVALO_DA_FILA_MS, self.esvaziar)
        except tk.TclError:
            self._esvaziar_id = None

    def esvaziar(self) -> int:
        """Escreve o que outras threads deixaram na fila; devolve quantas linhas entraram."""
        n = 0
        try:
            while True:
                mensagem, nivel, quando = self._fila.get_nowait()
                self.escrever(mensagem, nivel, quando)
                n += 1
        except queue.Empty:
            pass
        if self.winfo_exists():
            self._agendar_esvaziamento()
        return n

    @property
    def handler(self) -> logging.Handler:
        return self._handler

    def escrever(self, mensagem: str, nivel: str = "INFO", quando: float | None = None) -> None:
        hora = time.strftime("%H:%M:%S", time.localtime(quando if quando is not None else time.time()))
        linha = f"{hora}  {mensagem}"
        self.linhas.append((nivel, linha))
        try:
            self.texto.configure(state="normal")
            self.texto.insert("end", linha + "\n", (nivel,))
            excesso = int(self.texto.index("end-1c").split(".")[0]) - LIMITE_DE_LINHAS
            if excesso > 0:
                self.texto.delete("1.0", f"{excesso + 1}.0")
            self.texto.configure(state="disabled")
            self.texto.see("end")
        except tk.TclError:
            pass

    def limpar(self) -> None:
        self.linhas.clear()
        self.texto.configure(state="normal")
        self.texto.delete("1.0", "end")
        self.texto.configure(state="disabled")

    def contem(self, trecho: str) -> bool:
        return any(trecho in linha for _n, linha in self.linhas)

    def foco(self) -> None:
        self.texto.focus_set()

    def instalar(self, log: logging.Logger | None = None) -> None:
        """Pendura o handler no logger (uma vez); INFO passa a chegar aqui."""
        log = log or logger()
        if self._handler not in log.handlers:
            log.addHandler(self._handler)
        if log.level == logging.NOTSET or log.level > logging.INFO:
            log.setLevel(logging.INFO)

    def desinstalar(self, log: logging.Logger | None = None) -> None:
        log = log or logger()
        if self._handler in log.handlers:
            log.removeHandler(self._handler)


class _HandlerDoPainel(logging.Handler):
    def __init__(self, painel: PainelDeMensagens):
        super().__init__(logging.INFO)
        self.painel = painel

    def emit(self, registro: logging.LogRecord) -> None:
        try:
            mensagem = registro.getMessage()
        except Exception:      # noqa: BLE001 — um registro mal formatado não derruba o painel
            mensagem = str(registro.msg)
        nivel, quando = registro.levelname, registro.created
        if threading.current_thread() is threading.main_thread():
            self.painel.escrever(mensagem, nivel, quando)
            return
        self.painel._fila.put((mensagem, nivel, quando))


__all__ = ["PainelDeMensagens", "NOME_DO_LOGGER", "logger"]
