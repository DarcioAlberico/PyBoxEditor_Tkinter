"""
O painel Sumário e o editor de sumário (ED-08; SPEC_EDITOR §9 "TOC painel / Generate /
Edit / HTML TOC"): a árvore do `Livro.sumario` que leva ao destino, e a caixa que o edita —
renomear, subir, descer, aumentar e diminuir nível, remover, acrescentar, gerar dos títulos
(níveis 1–2 ou 1–3). "Sumário como página" é `sumario.pagina_de_sumario` (o comando fica
com a janela).

A caixa trabalha sobre uma **cópia** das entradas e devolve a lista nova em `confirmar()`;
`cancelar()` não muda nada. Constrói-se sem mostrar para o teste (`construir`, `escolher`,
`renomear`, `subir`, `descer`, `aumentar_nivel`, `diminuir_nivel`, `remover`, `acrescentar`,
`gerar`).
"""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import ttk
from typing import Any, Sequence

from core.editor import sumario as core_sumario
from core.editor.modelo import EntradaDeSumario, Livro
from ui.editor.dialogos import _Dialogo


class PainelDeSumario(ttk.Frame):
    """A árvore do sumário; `arvore` é o `janela.arvore_do_sumario` de sempre."""

    def __init__(self, master: tk.Misc, janela: Any, **kw: Any):
        super().__init__(master, **kw)
        self.janela = janela
        self.arvore = ttk.Treeview(self, show="tree", selectmode="browse", height=8)
        barra = ttk.Scrollbar(self, orient="vertical", command=self.arvore.yview)
        self.arvore.configure(yscrollcommand=barra.set)
        self.arvore.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self.destinos: dict[str, str] = {}
        self.arvore.bind("<Double-Button-1>", lambda e: self._ir())
        self.arvore.bind("<Return>", lambda e: self._ir())
        self.arvore.bind("<Button-3>", self._botao_direito, add="+")
        self._menu: tk.Menu | None = None

    def atualizar(self, entradas: Sequence[EntradaDeSumario]) -> None:
        arvore = self.arvore
        arvore.delete(*arvore.get_children())
        self.destinos = {}

        def inserir(lista: Sequence[EntradaDeSumario], pai: str, prefixo: str) -> None:
            for k, entrada in enumerate(lista):
                iid = f"{prefixo}{k}"
                arvore.insert(pai, "end", iid=iid, text=entrada.rotulo, open=True)
                self.destinos[iid] = entrada.destino
                inserir(entrada.filhos, iid, iid + ".")

        inserir(entradas, "", "s")

    def destino_selecionado(self) -> str | None:
        iid = self.arvore.focus()
        return self.destinos.get(iid) if iid else None

    def _ir(self) -> str:
        destino = self.destino_selecionado()
        if destino:
            self.janela.executar("ir_para_destino", destino)
        return "break"

    def _botao_direito(self, evento: Any) -> str:
        iid = self.arvore.identify_row(evento.y)
        if iid:
            self.arvore.focus(iid)
            self.arvore.selection_set(iid)
        self.arvore.focus_set()
        self.menu_de_contexto(evento.x_root, evento.y_root)
        return "break"

    def menu_de_contexto(self, x: int | None = None, y: int | None = None) -> tk.Menu:
        if self._menu is not None:
            try:
                self._menu.destroy()
            except tk.TclError:
                pass
        menu = tk.Menu(self, tearoff=0)
        janela = self.janela
        for nome, rotulo in (("sumario_gerar", "Gerar…"), ("sumario_editar", "Editar…"), ("sumario_gravar", "Gravar"),
                             ("sumario_como_pagina", "Sumário como página do livro")):
            menu.add_command(label=rotulo, command=lambda n=nome: janela.executar(n),
                             state="normal" if janela.disponivel(nome) else "disabled")
        self._menu = menu
        if x is not None and y is not None and self.winfo_viewable():
            try:
                menu.tk_popup(int(x), int(y))
            finally:
                try:
                    menu.grab_release()
                except tk.TclError:
                    pass
        return menu


class EditorDeSumario(_Dialogo):
    """Ver o cabeçalho. `livro` serve só para "Gerar dos títulos"."""

    def __init__(self, master: tk.Misc, entradas: Sequence[EntradaDeSumario], livro: Livro | None = None,
                 destino_atual: str = "", titulo: str = "Editar sumário"):
        super().__init__(master, titulo)
        self.entradas: list[EntradaDeSumario] = copy.deepcopy(list(entradas))
        self.livro = livro
        self.destino_atual = destino_atual
        self.arvore: ttk.Treeview | None = None
        self._por_iid: dict[str, EntradaDeSumario] = {}

    # -- construção ----------------------------------------------------------------

    def _construir(self) -> tk.Toplevel:
        top = self._abrir((True, True))
        corpo = ttk.Frame(top, padding=10)
        corpo.grid(row=0, column=0, sticky="nsew")
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        corpo.rowconfigure(0, weight=1)
        corpo.columnconfigure(0, weight=1)
        self.arvore = ttk.Treeview(corpo, columns=("destino",), show="tree headings", selectmode="browse", height=16)
        self.arvore.heading("#0", text="Entrada")
        self.arvore.heading("destino", text="Destino")
        self.arvore.column("#0", width=280)
        self.arvore.column("destino", width=220)
        barra = ttk.Scrollbar(corpo, orient="vertical", command=self.arvore.yview)
        self.arvore.configure(yscrollcommand=barra.set)
        self.arvore.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        botoes = ttk.Frame(corpo)
        botoes.grid(row=0, column=2, sticky="n", padx=(8, 0))
        self.botoes: dict[str, ttk.Button] = {}
        for nome, rotulo, acao in (("renomear", "Renomear…", self._renomear), ("subir", "Subir", self.subir),
                                   ("descer", "Descer", self.descer),
                                   ("aumentar", "Aumentar nível", self.aumentar_nivel),
                                   ("diminuir", "Diminuir nível", self.diminuir_nivel),
                                   ("remover", "Remover", self.remover),
                                   ("acrescentar", "Acrescentar…", self._acrescentar),
                                   ("gerar2", "Gerar dos títulos 1–2", lambda: self.gerar((1, 2))),
                                   ("gerar3", "Gerar dos títulos 1–3", lambda: self.gerar((1, 2, 3)))):
            botao = ttk.Button(botoes, text=rotulo, command=acao, width=22)
            botao.pack(fill="x", pady=1)
            self.botoes[nome] = botao
        self.arvore.bind("<Double-Button-1>", lambda e: self._renomear())
        self._botoes(corpo).grid(row=1, column=0, columnspan=3, sticky="e", pady=(10, 0))
        self.recarregar()
        return top

    def recarregar(self, escolher: EntradaDeSumario | None = None) -> None:
        assert self.arvore is not None
        self.arvore.delete(*self.arvore.get_children())
        self._por_iid = {}

        def inserir(lista: Sequence[EntradaDeSumario], pai: str, prefixo: str) -> None:
            for k, entrada in enumerate(lista):
                iid = f"{prefixo}{k}"
                self.arvore.insert(pai, "end", iid=iid, text=entrada.rotulo, values=(entrada.destino,), open=True)
                self._por_iid[iid] = entrada
                inserir(entrada.filhos, iid, iid + ".")

        inserir(self.entradas, "", "s")
        if escolher is not None:
            for iid, entrada in self._por_iid.items():
                if entrada is escolher:
                    self.arvore.focus(iid)
                    self.arvore.selection_set(iid)
                    break

    # -- a entrada escolhida e onde ela mora -------------------------------------------

    def escolhida(self) -> EntradaDeSumario | None:
        if self.arvore is None:
            return None
        iid = self.arvore.focus()
        return self._por_iid.get(iid) if iid else None

    def escolher(self, entrada: EntradaDeSumario) -> None:
        self.recarregar(entrada)

    def _lista_e_indice(self, entrada: EntradaDeSumario) -> tuple[list[EntradaDeSumario], int] | None:
        def procurar(lista: list[EntradaDeSumario]) -> tuple[list[EntradaDeSumario], int] | None:
            for k, e in enumerate(lista):
                if e is entrada:
                    return lista, k
                achado = procurar(e.filhos)
                if achado is not None:
                    return achado
            return None

        return procurar(self.entradas)

    def _pai_de(self, lista: list[EntradaDeSumario]) -> tuple[list[EntradaDeSumario], int] | None:
        """`(lista do pai, índice do pai)` de uma lista de filhos; `None` quando `lista` é a raiz."""
        def procurar(pais: list[EntradaDeSumario]) -> tuple[list[EntradaDeSumario], int] | None:
            for k, e in enumerate(pais):
                if e.filhos is lista:
                    return pais, k
                achado = procurar(e.filhos)
                if achado is not None:
                    return achado
            return None

        return None if lista is self.entradas else procurar(self.entradas)

    # -- as ações --------------------------------------------------------------------

    def _exigir(self) -> EntradaDeSumario:
        entrada = self.escolhida()
        if entrada is None:
            raise ValueError("escolha uma entrada do sumário")
        return entrada

    def renomear(self, rotulo: str, entrada: EntradaDeSumario | None = None) -> EntradaDeSumario:
        entrada = entrada or self._exigir()
        rotulo = rotulo.strip()
        if not rotulo:
            raise ValueError("a entrada precisa de um rótulo")
        entrada.rotulo = rotulo
        self.recarregar(entrada)
        return entrada

    def _renomear(self) -> None:
        from ui.editor.dialogos import DialogoDeFormulario

        entrada = self._exigir()
        resposta = DialogoDeFormulario(self.top or self.master, "Renomear entrada",
                                       [("rotulo", "Rótulo:", entrada.rotulo),
                                        ("destino", "Destino:", entrada.destino)]).mostrar()
        if resposta is None:
            return
        entrada.destino = resposta["destino"].strip() or entrada.destino
        self.renomear(resposta["rotulo"], entrada)

    def subir(self, entrada: EntradaDeSumario | None = None) -> bool:
        entrada = entrada or self._exigir()
        onde = self._lista_e_indice(entrada)
        if onde is None or onde[1] == 0:
            return False
        lista, k = onde
        lista[k - 1], lista[k] = lista[k], lista[k - 1]
        self.recarregar(entrada)
        return True

    def descer(self, entrada: EntradaDeSumario | None = None) -> bool:
        entrada = entrada or self._exigir()
        onde = self._lista_e_indice(entrada)
        if onde is None or onde[1] >= len(onde[0]) - 1:
            return False
        lista, k = onde
        lista[k + 1], lista[k] = lista[k], lista[k + 1]
        self.recarregar(entrada)
        return True

    def aumentar_nivel(self, entrada: EntradaDeSumario | None = None) -> bool:
        """A entrada vira filha da irmã anterior."""
        entrada = entrada or self._exigir()
        onde = self._lista_e_indice(entrada)
        if onde is None or onde[1] == 0:
            return False
        lista, k = onde
        del lista[k]
        lista[k - 1].filhos.append(entrada)
        self.recarregar(entrada)
        return True

    def diminuir_nivel(self, entrada: EntradaDeSumario | None = None) -> bool:
        """A entrada sobe um nível, logo depois do pai (as irmãs seguintes vão com ela, como filhas)."""
        entrada = entrada or self._exigir()
        onde = self._lista_e_indice(entrada)
        if onde is None:
            return False
        lista, k = onde
        pai = self._pai_de(lista)
        if pai is None:
            return False
        lista_do_pai, indice_do_pai = pai
        seguintes = lista[k + 1:]
        del lista[k:]
        entrada.filhos.extend(seguintes)
        lista_do_pai.insert(indice_do_pai + 1, entrada)
        self.recarregar(entrada)
        return True

    def remover(self, entrada: EntradaDeSumario | None = None) -> bool:
        """Tira a entrada; os filhos sobem para o lugar dela."""
        entrada = entrada or self._exigir()
        onde = self._lista_e_indice(entrada)
        if onde is None:
            return False
        lista, k = onde
        lista[k:k + 1] = entrada.filhos
        self.recarregar()
        return True

    def acrescentar(self, rotulo: str, destino: str, depois_de: EntradaDeSumario | None = None) -> EntradaDeSumario:
        rotulo = rotulo.strip()
        if not rotulo:
            raise ValueError("a entrada precisa de um rótulo")
        if not destino.strip():
            raise ValueError("a entrada precisa de um destino (arquivo#id)")
        nova = EntradaDeSumario(rotulo=rotulo, destino=destino.strip())
        alvo = depois_de or self.escolhida()
        onde = self._lista_e_indice(alvo) if alvo is not None else None
        if onde is None:
            self.entradas.append(nova)
        else:
            onde[0].insert(onde[1] + 1, nova)
        self.recarregar(nova)
        return nova

    def _acrescentar(self) -> None:
        from ui.editor.dialogos import DialogoDeFormulario

        resposta = DialogoDeFormulario(self.top or self.master, "Acrescentar entrada",
                                       [("rotulo", "Rótulo:", ""),
                                        ("destino", "Destino:", self.destino_atual)]).mostrar()
        if resposta is None:
            return
        self.acrescentar(resposta["rotulo"], resposta["destino"])

    def gerar(self, niveis: Sequence[int] = (1, 2)) -> list[EntradaDeSumario]:
        if self.livro is None:
            raise ValueError("sem livro para gerar o sumário")
        self.entradas = core_sumario.gerar_dos_titulos(self.livro, niveis)
        self.recarregar()
        return self.entradas

    def _ler(self) -> list[EntradaDeSumario]:
        return self.entradas


__all__ = ["PainelDeSumario", "EditorDeSumario"]
