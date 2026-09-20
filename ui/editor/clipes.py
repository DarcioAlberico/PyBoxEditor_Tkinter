"""
A barra de clipes: um seletor de grupo e um botão por clipe, que aplica o clipe ao
editor ativo (ED-07; SPEC_EDITOR §9 "Clips"). A regra (o `\\1`, os grupos, a
persistência) mora em `core/editor/clipes.py`; aqui só se desenha e despacha.

Quem recebe o clique é `ao_aplicar(clipe)`, injetado pela janela: ela sabe qual aba
está ativa — o editor de código (`EditorDeCodigo.aplicar_clipe`) ou, na ED-08, o modo
texto. Botões reais (`ttk.Button` com `text`), alcançáveis por `Tab`, com a dica no
`tooltip` simples da própria barra (§13.2).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from core.editor.clipes import Clipe, Clipes


class BarraDeClipes(ttk.Frame):
    def __init__(self, master: tk.Misc, clipes: Clipes, ao_aplicar: Callable[[Clipe], Any],
                 grupo: str | None = None, **kw: Any):
        super().__init__(master, **kw)
        self.clipes = clipes
        self.ao_aplicar = ao_aplicar
        self._grupo = tk.StringVar(value=grupo or (clipes.grupos()[0] if clipes.grupos() else ""))
        self.seletor = ttk.Combobox(self, textvariable=self._grupo, state="readonly", width=14)
        self.seletor.pack(side="left", padx=(4, 8), pady=2)
        self.seletor.bind("<<ComboboxSelected>>", lambda e: self.atualizar())
        self.botoes_frame = ttk.Frame(self)
        self.botoes_frame.pack(side="left", fill="x", expand=True)
        self.botoes: list[ttk.Button] = []
        self._dica = None
        self.atualizar()

    @property
    def grupo(self) -> str:
        return self._grupo.get()

    def escolher_grupo(self, nome: str) -> None:
        if nome not in self.clipes.grupos():
            raise ValueError(f"grupo inexistente: {nome}")
        self._grupo.set(nome)
        self.atualizar()

    def atualizar(self) -> None:
        """Refaz o seletor e os botões — depois de editar a coleção ou trocar de grupo."""
        grupos = self.clipes.grupos()
        self.seletor.configure(values=grupos)
        if self._grupo.get() not in grupos:
            self._grupo.set(grupos[0] if grupos else "")
        for botao in self.botoes:
            botao.destroy()
        self.botoes = []
        for clipe in self.clipes.do_grupo(self._grupo.get()):
            botao = ttk.Button(self.botoes_frame, text=clipe.nome, command=lambda c=clipe: self.aplicar(c))
            botao.pack(side="left", padx=2, pady=2)
            botao.bind("<Enter>", lambda e, c=clipe: self._mostrar_dica(e.widget, c))
            botao.bind("<Leave>", lambda e: self._esconder_dica())
            self.botoes.append(botao)

    def aplicar(self, clipe: Clipe) -> Any:
        return self.ao_aplicar(clipe)

    def aplicar_por_nome(self, nome: str) -> Any:
        clipe = self.clipes.por_nome(nome, self._grupo.get()) or self.clipes.por_nome(nome)
        if clipe is None:
            raise KeyError(f"clipe inexistente: {nome}")
        return self.aplicar(clipe)

    def _mostrar_dica(self, widget: tk.Misc, clipe: Clipe) -> None:
        self._esconder_dica()
        try:
            dica = tk.Toplevel(widget)
            dica.overrideredirect(True)
            rotulo = tk.Label(dica, text=clipe.texto, justify="left", relief="solid", borderwidth=1,
                              background="#ffffe0", foreground="#1f1f1f", padx=4, pady=2)
            rotulo.pack()
            dica.geometry(f"+{widget.winfo_rootx()}+{widget.winfo_rooty() + widget.winfo_height() + 2}")
            self._dica = dica
        except tk.TclError:
            self._dica = None

    def _esconder_dica(self) -> None:
        if self._dica is not None:
            try:
                self._dica.destroy()
            except tk.TclError:
                pass
            self._dica = None
