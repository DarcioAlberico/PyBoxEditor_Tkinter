"""
O painel Estilos do modo texto: os estilos nomeados da §6.3 e os das folhas do
capítulo; aplicar, "novo estilo a partir da seleção", "selecionar tudo com este
estilo", e a regra em texto para "modificar" (ED-03; SPEC_EDITOR §8.4, DEC-12).

A regra mora em `core/editor/css_minima.py`: um estilo novo é `p.<nome> { … }`
definido na **folha padrão** do livro (`Folha.definir` + `css_minima.escrever`), e
o painel só sabe disso por `ao_gravar(texto_da_folha)` — quem tem o `Recurso` é a
janela (ED-02), que o põe em `texto_cru` ou em `dados`. Botões reais, lista com
foco visível (§13.2).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from core.editor import css_minima, dialeto
from ui.editor.barra import AnelDeFoco
from ui.editor.texto_rico import TextoRico

ROTULOS = {
    "corpo": "Corpo", "primeira": "Primeira linha", "titulo1": "Título 1", "titulo2": "Título 2",
    "titulo3": "Título 3", "titulo4": "Título 4", "titulo5": "Título 5", "titulo6": "Título 6",
    "notacao": "Notação", "comentario": "Comentário", "legenda": "Legenda", "citacao": "Citação",
    "nota": "Nota", "destaque": "Destaque", "epigrafe": "Epígrafe", "assinatura": "Assinatura",
    "cabecalho-diagrama": "Cabeçalho de diagrama",
}
#: O que uma regra `p.<nome>` grava quando o estilo nasce da seleção (o que a tela sabe ler, §6.4).
PROPRIEDADES_DO_NOVO = ("font-weight", "font-style", "font-variant", "font-size", "font-family", "color",
                        "background-color", "text-align", "text-indent", "text-decoration")


class PainelDeEstilos(ttk.Frame):
    def __init__(self, master: tk.Misc, texto: TextoRico, folha_padrao: str = "",
                 ao_gravar: Callable[[str], Any] | None = None, **kw: Any):
        super().__init__(master, **kw)
        self.texto_rico = texto
        self.folha_padrao = folha_padrao or ""
        self.ao_gravar = ao_gravar
        self.lista = tk.Listbox(self, exportselection=False, height=14, highlightthickness=2, activestyle="dotbox")
        self.lista.grid(row=0, column=0, columnspan=2, sticky="nsew")
        barra = ttk.Scrollbar(self, orient="vertical", command=self.lista.yview)
        barra.grid(row=0, column=2, sticky="ns")
        self.lista.configure(yscrollcommand=barra.set)
        # Os botões `ttk` dentro de um `AnelDeFoco` (§13.2, AC-006): o tema `vista` não desenha o foco.
        anel_aplicar = AnelDeFoco(self, lambda pai: ttk.Button(pai, text="Aplicar", command=self.aplicar))
        anel_aplicar.grid(row=1, column=0, sticky="ew", padx=(0, 2), pady=4)
        self.botao_aplicar = anel_aplicar.widget
        anel_selecionar = AnelDeFoco(self, lambda pai: ttk.Button(pai, text="Selecionar tudo com este estilo",
                                                                  command=self.selecionar_tudo_com))
        anel_selecionar.grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)
        self.botao_selecionar = anel_selecionar.widget
        self.entrada_nome = ttk.Entry(self)
        self.entrada_nome.grid(row=2, column=0, sticky="ew", padx=(0, 2))
        anel_novo = AnelDeFoco(self, lambda pai: ttk.Button(pai, text="Novo estilo a partir da seleção",
                                                            command=self._novo_do_botao))
        anel_novo.grid(row=2, column=1, columnspan=2, sticky="ew")
        self.botao_novo = anel_novo.widget
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.lista.bind("<Double-Button-1>", lambda e: self.aplicar())
        self.lista.bind("<Return>", lambda e: self.aplicar())
        self._nomes: list[str] = []
        self.atualizar()

    # -- a lista ----------------------------------------------------------

    def estilos(self) -> list[str]:
        """Os da §6.3 e, depois, os `p.<classe>` da folha padrão que não estão lá."""
        nomes = list(dialeto.ESTILOS_DE_PARAGRAFO)
        if self.folha_padrao:
            try:
                folha = css_minima.ler(self.folha_padrao)
            except Exception:      # noqa: BLE001 — folha ilegível: só os fixos
                return nomes
            for regra in folha.regras + folha.novas:
                if regra.elemento in ("p", "") and len(regra.classes) == 1:
                    classe = regra.classes[0]
                    if classe not in nomes and classe not in dialeto.ESTILO_DA_CLASSE:
                        nomes.append(classe)
        return nomes

    def atualizar(self) -> None:
        self._nomes = self.estilos()
        self.lista.delete(0, "end")
        for nome in self._nomes:
            self.lista.insert("end", ROTULOS.get(nome, nome))
        if self._nomes:
            self.lista.selection_set(0)

    def escolhido(self) -> str | None:
        marcado = self.lista.curselection()
        if not marcado:
            return None
        return self._nomes[marcado[0]]

    def escolher(self, nome: str) -> None:
        if nome not in self._nomes:
            raise ValueError(f"estilo fora da lista: {nome!r}")
        self.lista.selection_clear(0, "end")
        self.lista.selection_set(self._nomes.index(nome))
        self.lista.activate(self._nomes.index(nome))

    # -- ações --------------------------------------------------------------

    def aplicar(self, nome: str | None = None) -> list[str]:
        nome = nome or self.escolhido()
        if nome is None:
            return []
        if nome in dialeto.ESTILOS_DE_PARAGRAFO:
            return self.texto_rico.estilo(nome)
        # Um estilo da folha (`p.<classe>`) é o estilo `corpo` com a classe no bloco.
        return self._aplicar_classe(nome)

    def _aplicar_classe(self, classe: str) -> list[str]:
        texto = self.texto_rico
        ids = texto.estilo("corpo")
        for bloco_id in ids:
            bloco = texto.modelo_de(bloco_id)
            if bloco is not None:
                bloco.classe = classe
                texto._reescrever_bloco(bloco_id, bloco)
        return ids

    def selecionar_tudo_com(self, nome: str | None = None) -> int:
        """Seleciona (no widget) todos os blocos com este estilo; devolve quantos."""
        nome = nome or self.escolhido()
        if nome is None:
            return 0
        texto = self.texto_rico
        alvos = []
        for bloco_id in texto.ordem:
            bloco = texto.modelo_de(bloco_id)
            estilo = getattr(bloco, "estilo", "")
            if estilo == nome or (estilo == "corpo" and getattr(bloco, "classe", "") == nome):
                alvos.append(bloco_id)
        if not alvos:
            texto.texto.tag_remove("sel", "1.0", "end")
            return 0
        texto.texto.tag_remove("sel", "1.0", "end")
        for bloco_id in alvos:
            texto.texto.tag_add("sel", texto._inicio_de(bloco_id), f"{texto._fim_de(bloco_id)}-1c")
        texto.texto.mark_set("insert", texto._inicio_de(alvos[0]))
        return len(alvos)

    def _novo_do_botao(self) -> None:
        nome = self.entrada_nome.get().strip()
        if nome:
            self.novo_estilo_da_selecao(nome)

    def novo_estilo_da_selecao(self, nome: str) -> str:
        """
        Grava `p.<nome> { … }` na folha padrão com o formato do cursor (negrito, itálico,
        corpo, família, cor, fundo) e aplica ao bloco. Devolve o texto novo da folha.
        """
        nome = nome.strip().replace(" ", "-")
        if not nome or not nome.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"nome de estilo inválido: {nome!r}")
        estado = self.texto_rico.estilo_no_cursor()
        declaracoes: dict[str, str] = {}
        if estado.get("negrito"):
            declaracoes["font-weight"] = "bold"
        if estado.get("italico"):
            declaracoes["font-style"] = "italic"
        if estado.get("versalete"):
            declaracoes["font-variant"] = "small-caps"
        if estado.get("fam"):
            declaracoes["font-family"] = estado["fam"]
        if estado.get("corpo"):
            declaracoes["font-size"] = f"{float(estado['corpo']):g}pt"
        if estado.get("cor"):
            declaracoes["color"] = estado["cor"]
        if estado.get("fundo"):
            declaracoes["background-color"] = estado["fundo"]
        if estado.get("sublinhado"):
            declaracoes["text-decoration"] = "underline"
        folha = css_minima.ler(self.folha_padrao)
        folha.definir(f"p.{nome}", **declaracoes) if declaracoes else folha.definir(f"p.{nome}")
        self.folha_padrao = css_minima.escrever(folha, self.folha_padrao)
        if self.ao_gravar is not None:
            self.ao_gravar(self.folha_padrao)
        self.atualizar()
        self.escolher(nome)
        self._aplicar_classe(nome)
        return self.folha_padrao

    def regra_de(self, nome: str) -> str:
        """O texto da regra (`p.<nome> { … }`) na folha padrão — o que "Modificar estilo…" abre no código."""
        try:
            folha = css_minima.ler(self.folha_padrao)
        except Exception:      # noqa: BLE001
            return ""
        elemento, classe, _docx = dialeto.ESTILOS_DE_PARAGRAFO.get(nome, ("p", nome, ""))
        seletor = f"{elemento}.{classe}" if classe else elemento
        regra = folha.regra(seletor)
        if regra is None:
            return ""
        if regra.fim > regra.inicio:
            return self.folha_padrao[regra.inicio:regra.fim]
        return css_minima._texto_da_regra(regra)
