"""
A caixa de símbolos (Inserir → Símbolo…): categorias à esquerda, a grade de
caracteres à direita, busca por nome Unicode em cima, e o nome e o código do
caractere apontado embaixo (ED-06; SPEC_EDITOR §9 "Special Characters").

O que é regra mora em `core/editor/simbolos.py` (as categorias, a busca por nome, o
código ↔ caractere); aqui só a caixa. É modal e devolve o caractere escolhido (duplo
clique, `Enter` ou "Inserir"); o teste constrói sem mostrar, chama `procurar`/
`escolher` e lê `confirmar()`. Um caractere invisível (o espaço inseparável) aparece
pelo nome, entre colchetes, para dar para escolhê-lo.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from core.editor import simbolos as simbolos_mod
from ui.editor.dialogos import _Dialogo

COLUNAS = 12


class DialogoDeSimbolos(_Dialogo):
    def __init__(self, master: tk.Misc, titulo: str = "Símbolo", familia: str = ""):
        super().__init__(master, titulo)
        self.familia = familia
        self.escolhido: str | None = None
        self.simbolos: list[simbolos_mod.Simbolo] = []
        self.botoes: list[tk.Button] = []
        self.var_busca: tk.StringVar | None = None
        self.var_nome: tk.StringVar | None = None
        self.lista: tk.Listbox | None = None
        self.grade: ttk.Frame | None = None

    def _construir(self) -> tk.Toplevel:
        top = self._abrir((True, True))
        self.var_busca = tk.StringVar(master=top)
        self.var_nome = tk.StringVar(master=top, value="")
        corpo = ttk.Frame(top, padding=10)
        corpo.grid(row=0, column=0, sticky="nsew")
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        corpo.rowconfigure(1, weight=1)
        corpo.columnconfigure(1, weight=1)
        ttk.Label(corpo, text="Buscar pelo nome ou código:").grid(row=0, column=0, sticky="w")
        self.campo_busca = ttk.Entry(corpo, textvariable=self.var_busca, width=40)
        self.campo_busca.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.campo_busca.bind("<Return>", lambda e: self.procurar())
        self.campo_busca.bind("<KeyRelease>", lambda e: self.procurar() if len(self.var_busca.get()) >= 3 else None)
        self.lista = tk.Listbox(corpo, height=12, width=20, exportselection=False, highlightthickness=2,
                                activestyle="dotbox")
        for rotulo, _c in simbolos_mod.CATEGORIAS:
            self.lista.insert("end", rotulo)
        self.lista.grid(row=1, column=0, sticky="ns", pady=(8, 0))
        self.lista.bind("<<ListboxSelect>>", self._categoria_escolhida)
        moldura = ttk.Frame(corpo)
        moldura.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(8, 0))
        moldura.rowconfigure(0, weight=1)
        moldura.columnconfigure(0, weight=1)
        self.tela = tk.Canvas(moldura, highlightthickness=0, width=COLUNAS * 34, height=260)
        barra = ttk.Scrollbar(moldura, orient="vertical", command=self.tela.yview)
        self.tela.configure(yscrollcommand=barra.set)
        self.tela.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.grade = ttk.Frame(self.tela)
        self._janela_da_grade = self.tela.create_window((0, 0), window=self.grade, anchor="nw")
        self.grade.bind("<Configure>", lambda e: self.tela.configure(scrollregion=self.tela.bbox("all")))
        ttk.Label(corpo, textvariable=self.var_nome, foreground="#333333").grid(row=2, column=0, columnspan=2,
                                                                                sticky="w", pady=(6, 0))
        self._botoes(corpo, "Inserir").grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        self.lista.selection_set(0)
        self.lista.activate(0)
        self._categoria_escolhida()
        return top

    # -- conteúdo ----------------------------------------------------------

    def _categoria_escolhida(self, _evento: Any = None) -> None:
        assert self.lista is not None
        selecao = self.lista.curselection()
        if not selecao:
            return
        rotulo = self.lista.get(selecao[0])
        self.mostrar(simbolos_mod.simbolos_da_categoria(rotulo))

    def procurar(self, consulta: str | None = None) -> list[simbolos_mod.Simbolo]:
        assert self.var_busca is not None
        if consulta is not None:
            self.var_busca.set(consulta)
        achados = simbolos_mod.procurar(self.var_busca.get())
        self.mostrar(achados)
        return achados

    def mostrar(self, simbolos: list[simbolos_mod.Simbolo]) -> None:
        assert self.grade is not None
        for botao in self.botoes:
            botao.destroy()
        self.botoes = []
        self.simbolos = list(simbolos)
        self.escolhido = None
        fonte = (self.familia or "Segoe UI Symbol", 14)
        for k, s in enumerate(self.simbolos):
            invisivel = s.caractere in simbolos_mod.NOMES_DOS_INVISIVEIS
            rotulo = f"[{s.nome[:6]}]" if invisivel else s.caractere
            botao = tk.Button(self.grade, text=rotulo, font=fonte if not invisivel else ("Segoe UI", 7), width=2,
                              relief="flat", highlightthickness=1, takefocus=1,
                              command=lambda i=k: self.escolher(i))
            botao.grid(row=k // COLUNAS, column=k % COLUNAS, padx=1, pady=1, sticky="nsew")
            botao.bind("<Double-Button-1>", lambda e, i=k: (self.escolher(i), self.confirmar()))
            botao.bind("<Return>", lambda e, i=k: (self.escolher(i), self.confirmar()))
            botao.bind("<FocusIn>", lambda e, i=k: self._apontar(i))
            botao.bind("<Enter>", lambda e, i=k: self._apontar(i))
            self.botoes.append(botao)
        if self.simbolos:
            self._apontar(0)
        elif self.var_nome is not None:
            self.var_nome.set("nada encontrado")

    def _apontar(self, indice: int) -> None:
        if self.var_nome is None or not 0 <= indice < len(self.simbolos):
            return
        s = self.simbolos[indice]
        self.var_nome.set(f"{s.nome}  (U+{s.codigo})")

    def escolher(self, indice: int) -> str | None:
        if not 0 <= indice < len(self.simbolos):
            return None
        self.escolhido = self.simbolos[indice].caractere
        self._apontar(indice)
        for k, botao in enumerate(self.botoes):
            botao.configure(relief="sunken" if k == indice else "flat")
        return self.escolhido

    def _ler(self) -> str | None:
        return self.escolhido

    def _foco_inicial(self) -> None:
        self.campo_busca.focus_set()


__all__ = ["DialogoDeSimbolos", "COLUNAS"]
