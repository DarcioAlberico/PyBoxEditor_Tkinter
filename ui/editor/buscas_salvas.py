"""
"Ferramentas → Buscas salvas…" (ED-06b; SPEC_EDITOR §8.12): a caixa com as buscas
guardadas por grupo, e o controlador que as liga ao painel Busca — guardar a busca da
caixa, carregar uma na caixa, executar uma (substituir todos) ou um grupo em lote com o
resumo, exportar e importar JSON.

O que é regra mora em `core/editor/buscas_salvas.py` (`Colecao`); aqui a caixa é
**modeless** e chama o controlador, e o controlador é o que o teste chama por comando
(`guardar_atual`, `carregar`, `executar`, `lote`, `exportar`, `importar`).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Sequence

from core.editor import buscas_salvas as core_bs
from core.editor.buscas_salvas import BuscaSalva, Colecao, Resumo
from ui.editor.dialogos import _Dialogo

TIPOS_DE_JSON = (("Buscas salvas (JSON)", "*.json"), ("Todos os arquivos", "*.*"))


class DialogoDeBuscasSalvas(_Dialogo):
    def __init__(self, master: tk.Misc, controlador: "BuscasSalvas", titulo: str = "Buscas salvas"):
        super().__init__(master, titulo)
        self.controlador = controlador
        self.arvore: ttk.Treeview | None = None

    def _construir(self) -> tk.Toplevel:
        top = self._abrir((True, True))
        corpo = ttk.Frame(top, padding=10)
        corpo.grid(row=0, column=0, sticky="nsew")
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        corpo.rowconfigure(0, weight=1)
        corpo.columnconfigure(0, weight=1)
        self.arvore = ttk.Treeview(corpo, columns=("texto", "substituto", "escopo"), show="tree headings",
                                   selectmode="browse", height=12)
        self.arvore.heading("#0", text="Nome")
        self.arvore.heading("texto", text="Localizar")
        self.arvore.heading("substituto", text="Substituir por")
        self.arvore.heading("escopo", text="Escopo")
        self.arvore.column("#0", width=180)
        self.arvore.column("texto", width=180)
        self.arvore.column("substituto", width=140)
        self.arvore.column("escopo", width=90, stretch=False)
        barra = ttk.Scrollbar(corpo, orient="vertical", command=self.arvore.yview)
        self.arvore.configure(yscrollcommand=barra.set)
        self.arvore.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        botoes = ttk.Frame(corpo)
        botoes.grid(row=0, column=2, sticky="n", padx=(8, 0))
        self.botoes: dict[str, ttk.Button] = {}
        for nome, rotulo, acao in (
                ("guardar", "Guardar a busca da caixa…", self._guardar),
                ("carregar", "Carregar na caixa", self._carregar),
                ("executar", "Executar (substituir todos)", self._executar),
                ("lote", "Executar o grupo em lote", self._lote),
                ("exportar", "Exportar…", self._exportar),
                ("importar", "Importar…", self._importar),
                ("remover", "Remover", self._remover)):
            botao = ttk.Button(botoes, text=rotulo, command=acao, width=28)
            botao.pack(fill="x", pady=1)
            self.botoes[nome] = botao
        self.botao_ok = ttk.Button(botoes, text="Fechar", command=self.confirmar, default="active", width=28)
        self.botao_ok.pack(fill="x", pady=(10, 0))
        self.arvore.bind("<Double-Button-1>", lambda e: self._carregar())
        top.bind("<Return>", lambda e: self._carregar())
        self.recarregar()
        return top

    def recarregar(self) -> None:
        assert self.arvore is not None
        self.arvore.delete(*self.arvore.get_children())
        colecao = self.controlador.colecao
        grupos = colecao.grupos()
        for grupo in grupos:
            self.arvore.insert("", "end", iid=f"grupo:{grupo}", text=grupo, open=True)
        for busca in colecao.buscas:
            pai = f"grupo:{busca.grupo}" if busca.grupo else ""
            self.arvore.insert(pai, "end", iid=f"busca:{busca.nome}", text=busca.nome,
                               values=(busca.opcoes.get("texto", ""), busca.opcoes.get("substituto", ""),
                                       core_bs.Opcoes(**busca.opcoes).escopo))

    def selecionada(self) -> tuple[str, str] | None:
        """`("busca", nome)` ou `("grupo", nome)` — o que está escolhido na árvore."""
        assert self.arvore is not None
        selecao = self.arvore.selection()
        if not selecao:
            return None
        tipo, _, nome = selecao[0].partition(":")
        return tipo, nome

    def escolher(self, nome: str, grupo: bool = False) -> None:
        assert self.arvore is not None
        iid = f"grupo:{nome}" if grupo else f"busca:{nome}"
        self.arvore.selection_set(iid)
        self.arvore.focus(iid)

    # -- ações ---------------------------------------------------------------

    def _nome_escolhido(self) -> str:
        escolha = self.selecionada()
        if escolha is None or escolha[0] != "busca":
            raise ValueError("escolha uma busca na lista")
        return escolha[1]

    def _guardar(self) -> None:
        resposta = self.controlador.j.caixas.formulario(
            "Guardar a busca", [("nome", "Nome:", self.controlador.painel.var_texto.get()[:40]),
                                ("grupo", "Grupo (opcional):", "")],
            {"grupo": self.controlador.colecao.grupos()})
        if resposta is None:
            return
        self.controlador.guardar_atual(resposta["nome"], resposta["grupo"])
        self.recarregar()

    def _carregar(self) -> None:
        self.controlador.j.executar("_buscas_salvas_carregar", self._nome_escolhido())

    def _executar(self) -> None:
        self.controlador.j.executar("_buscas_salvas_executar", self._nome_escolhido())

    def _lote(self) -> None:
        escolha = self.selecionada()
        if escolha is None:
            raise ValueError("escolha um grupo (ou uma busca de um grupo)")
        tipo, nome = escolha
        grupo = nome if tipo == "grupo" else (self.controlador.colecao.por_nome(nome) or BuscaSalva("x")).grupo
        if not grupo:
            raise ValueError("essa busca não está num grupo")
        self.controlador.j.executar("_buscas_salvas_lote", grupo)

    def _exportar(self) -> None:
        caminho = self.controlador.j.caixas.salvar_como("buscas.json", TIPOS_DE_JSON, extensao=".json",
                                                        titulo="Exportar buscas salvas")
        if caminho:
            self.controlador.exportar(caminho)

    def _importar(self) -> None:
        caminho = self.controlador.j.caixas.abrir(TIPOS_DE_JSON, titulo="Importar buscas salvas")
        if caminho:
            self.controlador.importar(caminho)
            self.recarregar()

    def _remover(self) -> None:
        self.controlador.remover(self._nome_escolhido())
        self.recarregar()


class BuscasSalvas:
    """O controlador: a coleção nas preferências, e as ações que a caixa (e o teste) chamam."""

    def __init__(self, janela: Any, painel: Any):
        self.j = janela
        self.painel = painel
        self.colecao = Colecao.carregar(janela._preferencia(core_bs.CHAVE, []),
                                        lambda lista: janela._gravar_preferencia(core_bs.CHAVE, lista))
        self.dialogo: DialogoDeBuscasSalvas | None = None
        self.comandos = {"buscas_salvas": self.abrir, "_buscas_salvas_carregar": self.carregar,
                         "_buscas_salvas_executar": self.executar, "_buscas_salvas_lote": self.lote}

    def abrir(self) -> DialogoDeBuscasSalvas:
        if self.dialogo is None or self.dialogo.top is None:
            self.dialogo = DialogoDeBuscasSalvas(self.j, self)
            self.dialogo.construir()
        else:
            self.dialogo.recarregar()
        if self.j.winfo_viewable() and self.dialogo.top is not None:
            self.dialogo.top.deiconify()
            self.dialogo.top.lift()
        return self.dialogo

    def guardar_atual(self, nome: str, grupo: str = "") -> BuscaSalva:
        """A busca que está na caixa, com nome e grupo."""
        busca = BuscaSalva.de_opcoes(nome, self.painel.opcoes(), grupo)
        self.colecao.guardar(busca)
        self.j.status(f"Busca guardada: {busca.nome}" + (f" ({busca.grupo})" if busca.grupo else ""))
        return busca

    def carregar(self, nome: str) -> BuscaSalva:
        busca = self.colecao.por_nome(nome)
        if busca is None:
            raise ValueError(f"não há busca salva chamada {nome!r}")
        opcoes = busca.como_opcoes()
        self.painel.definir(texto=opcoes.texto, substituto=opcoes.substituto, escopo=opcoes.escopo,
                            maiusculas=opcoes.maiusculas, palavra_inteira=opcoes.palavra_inteira, regex=opcoes.regex,
                            dotall=opcoes.dotall, minimo=opcoes.minimo, espaco_casa_nbsp=opcoes.espaco_casa_nbsp,
                            circular=opcoes.circular)
        self.j.status(f"Busca carregada: {nome}")
        return busca

    def _substituir_todos(self, opcoes: Any) -> dict[str, int]:
        """O "substituir todos" do `Buscador` com estas opções, sem mexer no que está na caixa."""
        painel = self.painel
        guardadas = painel.opcoes()
        try:
            painel.definir(texto=opcoes.texto, substituto=opcoes.substituto, escopo=opcoes.escopo,
                           maiusculas=opcoes.maiusculas, palavra_inteira=opcoes.palavra_inteira, regex=opcoes.regex,
                           dotall=opcoes.dotall, minimo=opcoes.minimo, espaco_casa_nbsp=opcoes.espaco_casa_nbsp,
                           circular=opcoes.circular)
            return self.j.buscador.substituir_todos()
        finally:
            painel.definir(texto=guardadas.texto, substituto=guardadas.substituto, escopo=guardadas.escopo,
                           maiusculas=guardadas.maiusculas, palavra_inteira=guardadas.palavra_inteira,
                           regex=guardadas.regex, dotall=guardadas.dotall, minimo=guardadas.minimo,
                           espaco_casa_nbsp=guardadas.espaco_casa_nbsp, circular=guardadas.circular)

    def executar(self, nome: str) -> dict[str, int]:
        busca = self.colecao.por_nome(nome)
        if busca is None:
            raise ValueError(f"não há busca salva chamada {nome!r}")
        return self._substituir_todos(busca.como_opcoes())

    def lote(self, grupo: str) -> Resumo:
        """O grupo inteiro, em ordem; o resumo vai a Mensagens, ao status e a uma caixa."""
        nomes = [b.nome for b in self.colecao.do_grupo(grupo)]
        if not nomes:
            raise ValueError(f"o grupo {grupo!r} não tem buscas")
        resumo = self.colecao.em_lote(nomes, self._substituir_todos)
        linhas = resumo.linhas()
        for linha in linhas:
            self.j.log.info("%s", linha)
        self.j.status(linhas[0])
        self.j.caixas.texto(f"Lote: {grupo}", "\n".join(linhas), monoespaco=False)
        return resumo

    def exportar(self, caminho: str, nomes: Sequence[str] | None = None) -> int:
        n = self.colecao.exportar_json(caminho, nomes)
        self.j.status(f"{n} busca(s) exportada(s) para {caminho}")
        return n

    def importar(self, caminho: str) -> int:
        n = self.colecao.importar_json(caminho)
        self.j.status(f"{n} busca(s) importada(s) de {caminho}")
        return n

    def remover(self, nome: str) -> bool:
        return self.colecao.remover(nome)


__all__ = ["DialogoDeBuscasSalvas", "BuscasSalvas", "TIPOS_DE_JSON"]
