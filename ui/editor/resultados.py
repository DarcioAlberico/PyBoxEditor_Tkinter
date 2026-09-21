"""
O painel Resultados (e o Validação, que é o mesmo widget): uma lista clicável e
genérica — arquivo, onde (bloco ou linha), mensagem — com um callback por item
(ED-02; SPEC_EDITOR §7.1, §13.2).

É o painel que a busca (ED-06), a validação (ED-07/08), os relatórios (ED-08) e a
conversão (ED-10) preenchem: cada um entrega `Resultado`s e diz o que fazer quando
um é ativado (`Enter`, duplo clique). O widget não sabe o que é um resultado —
só o mostra e devolve o objeto inteiro ao callback, com o `dados` que quem
preencheu quiser levar (o id do bloco, a linha e a coluna, o `Trecho`).
Foco visível (`highlightthickness=2` no `Treeview` não existe: o anel vai no
`Frame` de fora, ver `AnelDeFoco` em `ui/editor/barra.py`).
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Any, Callable, Sequence


@dataclass
class Resultado:
    arquivo: str
    onde: str                       # "bloco 12", "linha 40, col 3", "" — o que fizer sentido
    mensagem: str
    dados: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        onde = f" ({self.onde})" if self.onde else ""
        return f"{self.arquivo}{onde}: {self.mensagem}"


class PainelDeResultados(ttk.Frame):
    def __init__(self, master: tk.Misc, ao_ativar: Callable[[Resultado], Any] | None = None,
                 titulo: str = "", **kw: Any):
        super().__init__(master, **kw)
        self.ao_ativar = ao_ativar
        self.itens: list[Resultado] = []
        self.rotulo = ttk.Label(self, text=titulo, anchor="w")
        if titulo:
            self.rotulo.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=(2, 0))
        self.arvore = ttk.Treeview(self, columns=("arquivo", "onde", "mensagem"), show="headings",
                                   selectmode="browse", height=6)
        self.arvore.heading("arquivo", text="Arquivo")
        self.arvore.heading("onde", text="Onde")
        self.arvore.heading("mensagem", text="Mensagem")
        self.arvore.column("arquivo", width=180, stretch=False)
        self.arvore.column("onde", width=120, stretch=False)
        self.arvore.column("mensagem", width=400, stretch=True)
        barra = ttk.Scrollbar(self, orient="vertical", command=self.arvore.yview)
        self.arvore.configure(yscrollcommand=barra.set)
        self.arvore.grid(row=1, column=0, sticky="nsew")
        barra.grid(row=1, column=1, sticky="ns")
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        self.arvore.bind("<Double-Button-1>", lambda e: self.ativar())
        self.arvore.bind("<Return>", lambda e: self.ativar())
        self.arvore.bind("<KP_Enter>", lambda e: self.ativar())

    def definir(self, itens: Sequence[Resultado], titulo: str | None = None) -> None:
        """Troca a lista inteira; `titulo` (opcional) é o rótulo acima dela."""
        self.itens = list(itens)
        self.arvore.delete(*self.arvore.get_children())
        for k, item in enumerate(self.itens):
            self.arvore.insert("", "end", iid=str(k), values=(item.arquivo, item.onde, item.mensagem))
        if titulo is not None:
            self.rotulo.configure(text=titulo)
            if not self.rotulo.winfo_ismapped():
                self.rotulo.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=(2, 0))

    def acrescentar(self, item: Resultado) -> None:
        self.itens.append(item)
        self.arvore.insert("", "end", iid=str(len(self.itens) - 1), values=(item.arquivo, item.onde, item.mensagem))

    def limpar(self) -> None:
        self.definir([])

    def selecionado(self) -> Resultado | None:
        selecao = self.arvore.selection()
        if not selecao:
            return None
        return self.itens[int(selecao[0])]

    def selecionar(self, indice: int) -> None:
        self.arvore.selection_set(str(indice))
        self.arvore.focus(str(indice))
        self.arvore.see(str(indice))

    def ativar(self, indice: int | None = None) -> Resultado | None:
        """Ativa o item dado (ou o selecionado): chama `ao_ativar` e devolve o item."""
        item = self.itens[indice] if indice is not None else self.selecionado()
        if item is None:
            return None
        if self.ao_ativar is not None:
            self.ao_ativar(item)
        return item

    def foco(self) -> None:
        self.arvore.focus_set()
        if self.itens and not self.arvore.selection():
            self.selecionar(0)

    def __len__(self) -> int:
        return len(self.itens)


__all__ = ["Resultado", "PainelDeResultados"]
