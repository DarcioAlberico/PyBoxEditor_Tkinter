"""
A caixa de conclusão de uma exportação: o relatório e o que fazer com o arquivo
— "Abrir arquivo", "Abrir pasta" e, quando cabe, "Abrir no editor" (ED-02;
SPEC_EDITOR §7.2, §10.8).

Substitui o `messagebox.showinfo("Livro exportado", …)` do fim de "Exportar
livro": uma caixa de informação termina e o arquivo fica onde ficou; esta
termina com o arquivo aberto no leitor, na pasta ou no editor de livros. As
ações são dados — `(rótulo, callback)` —, e o callback recebe o **caminho**
(AC-ED02-10): a janela principal passa `abrir_no_editor` quando o formato foi
EPUB; as outras exportações e a fila passam o que tiverem (ED-11). Construída
sem `mostrar()` para o teste: `construir()`, `acoes`, `invocar(rótulo)`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Sequence

Acao = tuple[str, Callable[[str], Any]]


def abrir_arquivo(caminho: str) -> None:
    """Abre o arquivo no programa padrão do sistema."""
    if sys.platform.startswith("win"):
        os.startfile(caminho)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", caminho])
    else:
        subprocess.Popen(["xdg-open", caminho])


def abrir_pasta(caminho: str) -> None:
    """Abre a pasta do arquivo (no Windows, com o arquivo selecionado)."""
    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(caminho)])
    else:
        abrir_arquivo(os.path.dirname(caminho) or ".")


class DialogoDeConclusao:
    def __init__(self, master: tk.Misc, titulo: str, linhas: Sequence[str], caminho: str,
                 acoes: Sequence[Acao] = (), abrir_no_editor: Callable[[str], Any] | None = None):
        self.master = master
        self.titulo = titulo
        self.linhas = list(linhas)
        self.caminho = os.fspath(caminho)
        self.acoes: list[Acao] = [("Abrir arquivo", abrir_arquivo), ("Abrir pasta", abrir_pasta)]
        if abrir_no_editor is not None:
            self.acoes.append(("Abrir no editor", abrir_no_editor))
        self.acoes.extend(acoes)
        self.top: tk.Toplevel | None = None
        self.botoes: dict[str, ttk.Button] = {}
        self.escolha: str | None = None

    def construir(self) -> tk.Toplevel:
        if self.top is not None:
            return self.top
        top = tk.Toplevel(self.master)
        top.title(self.titulo)
        try:
            top.transient(self.master.winfo_toplevel())
        except tk.TclError:
            pass
        top.protocol("WM_DELETE_WINDOW", self.fechar)
        top.bind("<Escape>", lambda e: self.fechar())
        corpo = ttk.Frame(top, padding=12)
        corpo.grid(row=0, column=0, sticky="nsew")
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        self.texto = tk.Text(corpo, width=84, height=min(28, max(8, len(self.linhas) + 2)), wrap="word",
                             font=("Segoe UI", 10), highlightthickness=2, exportselection=False)
        self.texto.insert("1.0", "\n".join(self.linhas))
        self.texto.configure(state="disabled")
        barra = ttk.Scrollbar(corpo, orient="vertical", command=self.texto.yview)
        self.texto.configure(yscrollcommand=barra.set)
        self.texto.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        corpo.rowconfigure(0, weight=1)
        corpo.columnconfigure(0, weight=1)
        ttk.Label(corpo, text=self.caminho, wraplength=560, justify="left").grid(row=1, column=0, columnspan=2,
                                                                                 sticky="w", pady=(8, 0))
        botoes = ttk.Frame(corpo)
        botoes.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        self.botao_fechar = ttk.Button(botoes, text="Fechar", command=self.fechar, default="active")
        self.botao_fechar.pack(side="right", padx=(6, 0))
        for rotulo, _acao in reversed(self.acoes):
            botao = ttk.Button(botoes, text=rotulo, command=lambda r=rotulo: self.invocar(r))
            botao.pack(side="right", padx=(6, 0))
            self.botoes[rotulo] = botao
        top.bind("<Return>", lambda e: self.fechar())
        self.top = top
        return top

    def invocar(self, rotulo: str) -> Any:
        """Chama a ação do botão com o caminho; a caixa fecha depois."""
        for nome, acao in self.acoes:
            if nome == rotulo:
                self.escolha = rotulo
                resultado = acao(self.caminho)
                self.fechar()
                return resultado
        raise KeyError(f"ação desconhecida: {rotulo!r}")

    def fechar(self) -> None:
        if self.top is not None:
            try:
                self.top.grab_release()
                self.top.destroy()
            except tk.TclError:
                pass
            self.top = None

    def mostrar(self) -> str | None:
        """Modal; devolve o rótulo da ação escolhida, ou `None` para "Fechar"."""
        top = self.construir()
        try:
            top.grab_set()
        except tk.TclError:
            pass
        self.botao_fechar.focus_set()
        top.wait_window()
        return self.escolha


__all__ = ["DialogoDeConclusao", "abrir_arquivo", "abrir_pasta"]
