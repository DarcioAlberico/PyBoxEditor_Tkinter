"""
A paleta de xadrez: o painel "Xadrez" (figurinas, os 23 NAGs da barra rápida, o padrão
inteiro por família e, quando importável, os símbolos de `core.chess_symbols`) e o
conteúdo da barra de xadrez (ED-05; SPEC_EDITOR §11.6, §13.2, DEC-07).

## Botões de verdade, e o código junto do símbolo

Cada símbolo é um `tk.Button` de ≥ 24×24 px com o símbolo como texto, a descrição
como dica e na barra de status, e o **código** do NAG ao lado no rótulo do padrão
(`$14 ⩲ Brancas ligeiramente melhor`) — é `$14` que vai para o PGN, não `⩲`. O
botão insere o símbolo **e** o código: um `Trecho(papel="nag", nag=14)` para o NAG
unívoco, `papel="figurina"` para a figurina, e `familia="simbolos"` quando o
caractere está acima de `PISO_DO_SIMBOLO` (a Times New Roman não o desenha).

## Teclado

`Ctrl+Shift+F` põe o foco na paleta; setas andam entre os botões (o Tk só anda com
`Tab`), `Enter` insere, `Esc` devolve o foco ao editor. `chess_symbols` (ED-pré, do
usuário) entra só quando existe: a paleta pergunta com `try`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from core import nags
from core.estilo_do_livro import PISO_DO_SIMBOLO
from ui.editor.barra import Barra, Dica

FIGURINAS = (("♔", "Rei"), ("♕", "Dama"), ("♖", "Torre"), ("♗", "Bispo"), ("♘", "Cavalo"), ("♙", "Peão"))
LADO_DO_BOTAO_PX = 24


def simbolos_extras() -> list[tuple[str, str]]:
    """Os símbolos de `core.chess_symbols` (ED-pré) como `(símbolo, descrição)`, ou vazio quando o módulo não existe."""
    try:
        from core import chess_symbols
    except Exception:      # noqa: BLE001 — ImportError, ou um módulo que ainda não roda: a paleta vive sem ele
        return []
    saida: list[tuple[str, str]] = []
    for nome in ("SIMBOLOS", "SYMBOLS", "TABELA", "CHESS_SYMBOLS"):
        tabela = getattr(chess_symbols, nome, None)
        if isinstance(tabela, dict):
            for simbolo, descricao in tabela.items():
                if isinstance(simbolo, str) and simbolo:
                    saida.append((simbolo, str(descricao)))
        elif isinstance(tabela, (list, tuple)):
            for item in tabela:
                if isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[0], str):
                    saida.append((item[0], str(item[1])))
                elif isinstance(item, str):
                    saida.append((item, ""))
        if saida:
            break
    vistos: set[str] = set()
    unicos = []
    for simbolo, descricao in saida:
        if simbolo not in vistos:
            vistos.add(simbolo)
            unicos.append((simbolo, descricao))
    return unicos


def codigo_do_simbolo(simbolo: str) -> int | None:
    """O código do NAG de um símbolo unívoco da tabela (`⩲` → 14); `None` para os ambíguos e os que não são NAG."""
    from core.editor import xadrez

    return xadrez._codigo_do_simbolo().get(simbolo)


def precisa_da_fonte_de_simbolos(simbolo: str) -> bool:
    return any(ord(c) >= PISO_DO_SIMBOLO for c in simbolo)


class _Grade(ttk.Frame):
    """Uma grade de botões com setas entre eles, `Enter` para inserir e `Esc` para sair."""

    def __init__(self, master: tk.Misc, colunas: int, ao_escolher: Callable[[str], Any],
                 ao_sair: Callable[[], Any] | None = None, **kw: Any):
        super().__init__(master, **kw)
        self.colunas = colunas
        self.ao_escolher = ao_escolher
        self.ao_sair = ao_sair
        self.botoes: list[tk.Button] = []
        self.por_simbolo: dict[str, tk.Button] = {}

    def adicionar(self, simbolo: str, descricao: str, rotulo: str | None = None) -> tk.Button:
        k = len(self.botoes)
        botao = tk.Button(self, text=rotulo or simbolo, width=3 if rotulo is None else None, padx=4, pady=2,
                          font=("Segoe UI Symbol", 11), relief="raised", takefocus=1, highlightthickness=2,
                          highlightcolor="#0645ad", command=lambda s=simbolo: self.ao_escolher(s))
        botao.grid(row=k // self.colunas, column=k % self.colunas, padx=1, pady=1, sticky="nsew")
        Dica(botao, f"{simbolo}  {descricao}".strip())
        botao.bind("<Up>", lambda e, i=k: self._mover(i, -self.colunas))
        botao.bind("<Down>", lambda e, i=k: self._mover(i, self.colunas))
        botao.bind("<Left>", lambda e, i=k: self._mover(i, -1))
        botao.bind("<Right>", lambda e, i=k: self._mover(i, 1))
        botao.bind("<Return>", lambda e, s=simbolo: (self.ao_escolher(s), "break")[1])
        botao.bind("<Escape>", lambda e: (self.ao_sair() if self.ao_sair else None, "break")[1])
        self.botoes.append(botao)
        self.por_simbolo[simbolo] = botao
        return botao

    def _mover(self, i: int, passo: int) -> str:
        alvo = i + passo
        if 0 <= alvo < len(self.botoes):
            self.botoes[alvo].focus_set()
        return "break"

    def foco(self) -> None:
        if self.botoes:
            self.botoes[0].focus_set()


class PainelDeXadrez(ttk.Frame):
    """
    O painel "Xadrez" da direita (§7.1): a paleta de figurinas, a barra rápida de NAGs por
    família, o padrão inteiro (por família, com `nags.rotulo`) e os símbolos extras.
    `ao_inserir(simbolo)` é quem põe o símbolo no editor (o controlador `Xadrez`).
    """

    def __init__(self, master: tk.Misc, ao_inserir: Callable[[str], Any], ao_sair: Callable[[], Any] | None = None,
                 status: Callable[[str], Any] | None = None, **kw: Any):
        super().__init__(master, **kw)
        self.ao_inserir = ao_inserir
        self.ao_sair = ao_sair
        self.status = status or (lambda texto: None)
        self.grades: list[_Grade] = []
        self.descricoes: dict[str, str] = {}
        rolagem = ttk.Frame(self)
        rolagem.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(rolagem, highlightthickness=0, borderwidth=0)
        barra = ttk.Scrollbar(rolagem, orient="vertical", command=self.canvas.yview)
        self.miolo = ttk.Frame(self.canvas)
        self.miolo.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.miolo, anchor="nw")
        self.canvas.configure(yscrollcommand=barra.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        self._construir()

    def _grade(self, titulo: str, colunas: int) -> _Grade:
        quadro = ttk.LabelFrame(self.miolo, text=titulo, padding=4)
        quadro.pack(fill="x", padx=4, pady=(4, 0))
        grade = _Grade(quadro, colunas, self._escolher, self.ao_sair)
        grade.pack(anchor="w")
        self.grades.append(grade)
        return grade

    def _construir(self) -> None:
        figurinas = self._grade("Figurinas", 6)
        for simbolo, nome in FIGURINAS:
            figurinas.adicionar(simbolo, nome)
            self.descricoes[simbolo] = nome
        for familia, pares in nags.NAGS_POR_FAMILIA:
            grade = self._grade(familia, 4)
            for simbolo, descricao in pares:
                grade.adicionar(simbolo, descricao)
                self.descricoes.setdefault(simbolo, descricao)
        extras = simbolos_extras()
        if extras:
            grade = self._grade("Símbolos do livro (chess_symbols)", 6)
            for simbolo, descricao in extras:
                grade.adicionar(simbolo, descricao)
                self.descricoes.setdefault(simbolo, descricao)
        # O padrão inteiro, por família, num combobox + lista (169 botões não cabem em tela nenhuma)
        quadro = ttk.LabelFrame(self.miolo, text="Todos os NAGs (padrão PGN)", padding=4)
        quadro.pack(fill="x", padx=4, pady=(4, 4))
        self.var_familia = tk.StringVar(master=self, value=nags.FAMILIAS[0][0])
        combo = ttk.Combobox(quadro, values=[f for f, _n in nags.FAMILIAS], textvariable=self.var_familia,
                             state="readonly", width=24)
        combo.pack(anchor="w")
        combo.bind("<<ComboboxSelected>>", lambda e: self._listar_familia())
        self.lista = tk.Listbox(quadro, height=6, width=34, exportselection=False, activestyle="dotbox",
                                highlightthickness=2, highlightcolor="#0645ad")
        self.lista.pack(fill="x", pady=(4, 0))
        self.lista.bind("<Return>", lambda e: (self._inserir_da_lista(), "break")[1])
        self.lista.bind("<Double-Button-1>", lambda e: self._inserir_da_lista())
        self.lista.bind("<Escape>", lambda e: (self.ao_sair() if self.ao_sair else None, "break")[1])
        self._listar_familia()

    def _listar_familia(self) -> None:
        self.lista.delete(0, "end")
        self._da_lista: list[nags.Nag] = []
        for familia, entradas in nags.FAMILIAS:
            if familia != self.var_familia.get():
                continue
            for nag in entradas:
                if nag.simbolo:
                    self.lista.insert("end", nags.rotulo(nag))
                    self._da_lista.append(nag)

    def _inserir_da_lista(self) -> None:
        selecao = self.lista.curselection()
        if not selecao:
            return
        nag = self._da_lista[int(selecao[0])]
        self.ao_inserir(nag.simbolo)

    def _escolher(self, simbolo: str) -> None:
        self.status(f"{simbolo}  {self.descricoes.get(simbolo, '')}".strip())
        self.ao_inserir(simbolo)

    def foco(self) -> None:
        if self.grades:
            self.grades[0].foco()

    def botao(self, simbolo: str) -> tk.Button | None:
        for grade in self.grades:
            if simbolo in grade.por_simbolo:
                return grade.por_simbolo[simbolo]
        return None


def preencher_barra_de_xadrez(barra: Barra, janela: Any) -> None:
    """
    A barra de xadrez (§7.3 "Barra de xadrez"): as figurinas brancas, os 23 da barra
    rápida, e Diagrama, Posição e Validar — botões ≥ 24 px, com dica e eco na barra de status.
    """
    for filho in barra.winfo_children():
        filho.destroy()
    barra.botoes.clear()
    barra.aneis.clear()
    barra.simbolos = {}
    for simbolo, nome in FIGURINAS:
        _botao_de_simbolo(barra, janela, simbolo, nome)
    ttk.Separator(barra, orient="vertical").pack(side="left", fill="y", padx=4, pady=2)
    for _familia, pares in nags.NAGS_POR_FAMILIA:
        for simbolo, descricao in pares:
            _botao_de_simbolo(barra, janela, simbolo, descricao)
        ttk.Separator(barra, orient="vertical").pack(side="left", fill="y", padx=4, pady=2)
    barra.adicionar("inserir_diagrama", "Diagrama", "Inserir diagrama… (Ctrl+Shift+D)")
    barra.adicionar("editar_posicao", "Posição", "Editar posição… (Ctrl+Shift+P)")
    barra.adicionar("validar_notacao", "Validar", "Validar notação do capítulo")


def _botao_de_simbolo(barra: Barra, janela: Any, simbolo: str, descricao: str) -> tk.Button:
    botao = tk.Button(barra, text=simbolo, width=2, padx=3, pady=1, font=("Segoe UI Symbol", 10), relief="raised",
                      takefocus=1, highlightthickness=2, highlightcolor="#0645ad",
                      command=lambda s=simbolo: janela.executar("inserir_simbolo_de_xadrez", s))
    botao.pack(side="left", padx=1, pady=2)
    Dica(botao, f"{simbolo}  {descricao}")
    botao.bind("<FocusIn>", lambda e, d=f"{simbolo}  {descricao}": janela.status(d), add="+")
    barra.simbolos[simbolo] = botao
    return botao


__all__ = ["PainelDeXadrez", "preencher_barra_de_xadrez", "simbolos_extras", "codigo_do_simbolo",
           "precisa_da_fonte_de_simbolos", "FIGURINAS", "LADO_DO_BOTAO_PX"]
