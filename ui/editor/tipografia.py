"""
"Ferramentas → Tipografia…" e "Juntar palavras hifenizadas" na janela (ED-06b; SPEC_EDITOR
§8.14): a caixa com a prévia por ocorrência — cada troca proposta com o contexto antes e
depois, marcada por padrão, desmarcável — e o controlador que aplica o que ficou marcado:
na aba de texto aberta pelo widget (um ponto de desfazer só), nos capítulos fechados pelo
modelo (um ponto por capítulo), e a hifenização na folha padrão.

A caixa constrói-se sem mostrar (`construir`, `marcar`, `confirmar`) para o teste; a
janela chama `janela.caixas.tipografia(propostas, regras, hifenizar)`, que o teste troca
por uma resposta pronta `(índices escolhidos, regras, hifenizar)`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Sequence

from core.editor import tipografia as core_tipo
from ui.editor.dialogos import _Dialogo

MARCADA, DESMARCADA = "☑", "☐"


class DialogoDeTipografia(_Dialogo):
    """`propostas` são `(arquivo, onde, alvo, troca)`; o resultado é `(índices, regras, hifenizar)`."""

    def __init__(self, master: tk.Misc, propostas: Sequence[tuple], regras: Sequence[str] = core_tipo.REGRAS,
                 hifenizar: bool = False, titulo: str = "Tipografia"):
        super().__init__(master, titulo)
        self.propostas = list(propostas)
        self.regras_iniciais = tuple(regras)
        self.hifenizar_inicial = bool(hifenizar)
        self.marcadas: list[bool] = [True] * len(self.propostas)
        self.arvore: ttk.Treeview | None = None
        self.var_regras: dict[str, tk.BooleanVar] = {}
        self.var_hifenizar: tk.BooleanVar | None = None

    def _construir(self) -> tk.Toplevel:
        top = self._abrir((True, True))
        self.var_hifenizar = tk.BooleanVar(master=top, value=self.hifenizar_inicial)
        corpo = ttk.Frame(top, padding=10)
        corpo.grid(row=0, column=0, sticky="nsew")
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        corpo.rowconfigure(1, weight=1)
        corpo.columnconfigure(0, weight=1)
        regras = ttk.Frame(corpo)
        regras.grid(row=0, column=0, columnspan=2, sticky="w")
        for k, nome in enumerate(core_tipo.REGRAS):
            var = tk.BooleanVar(master=top, value=nome in self.regras_iniciais)
            self.var_regras[nome] = var
            ttk.Checkbutton(regras, text=core_tipo.ROTULOS_DAS_REGRAS[nome], variable=var).grid(
                row=k // 3, column=k % 3, sticky="w", padx=(0, 10))
        ttk.Checkbutton(regras, text="Hifenização automática na folha padrão (hyphens: auto)",
                        variable=self.var_hifenizar).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 6))
        self.arvore = ttk.Treeview(corpo, columns=("ok", "arquivo", "onde", "antes", "depois", "motivo"),
                                   show="headings", selectmode="browse", height=14)
        for coluna, rotulo, largura in (("ok", "", 30), ("arquivo", "Arquivo", 110), ("onde", "Onde", 90),
                                        ("antes", "Como está", 220), ("depois", "Como fica", 220),
                                        ("motivo", "Regra", 120)):
            self.arvore.heading(coluna, text=rotulo)
            self.arvore.column(coluna, width=largura, stretch=coluna in ("antes", "depois"))
        barra = ttk.Scrollbar(corpo, orient="vertical", command=self.arvore.yview)
        self.arvore.configure(yscrollcommand=barra.set)
        self.arvore.grid(row=1, column=0, sticky="nsew")
        barra.grid(row=1, column=1, sticky="ns")
        for k, (arquivo, onde, alvo, troca) in enumerate(self.propostas):
            antes, depois = troca.contexto(alvo.texto)
            self.arvore.insert("", "end", iid=str(k), values=(MARCADA, arquivo, onde, antes, depois,
                                                               core_tipo.ROTULOS_DAS_REGRAS.get(troca.motivo,
                                                                                                troca.motivo)))
        self.arvore.bind("<Button-1>", self._clique)
        self.arvore.bind("<space>", lambda e: self._alternar_selecionada())
        botoes_extra = ttk.Frame(corpo)
        botoes_extra.grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Button(botoes_extra, text="Marcar todas", command=lambda: self.marcar_todas(True)).pack(side="left")
        ttk.Button(botoes_extra, text="Desmarcar todas", command=lambda: self.marcar_todas(False)).pack(
            side="left", padx=(6, 0))
        self.rotulo = ttk.Label(corpo, text=self._resumo())
        self.rotulo.grid(row=3, column=0, sticky="w", pady=(6, 0))
        self._botoes(corpo, "Aplicar").grid(row=4, column=0, columnspan=2, sticky="e", pady=(8, 0))
        return top

    def _resumo(self) -> str:
        return f"{sum(self.marcadas)} de {len(self.propostas)} troca(s) marcada(s)"

    def _clique(self, evento: Any) -> None:
        assert self.arvore is not None
        if self.arvore.identify_column(evento.x) != "#1":
            return
        iid = self.arvore.identify_row(evento.y)
        if iid:
            self.marcar(int(iid), not self.marcadas[int(iid)])

    def _alternar_selecionada(self) -> None:
        assert self.arvore is not None
        selecao = self.arvore.selection()
        if selecao:
            k = int(selecao[0])
            self.marcar(k, not self.marcadas[k])

    def marcar(self, indice: int, valor: bool = True) -> None:
        self.marcadas[indice] = bool(valor)
        if self.arvore is not None:
            self.arvore.set(str(indice), "ok", MARCADA if valor else DESMARCADA)
            self.rotulo.configure(text=self._resumo())

    def marcar_todas(self, valor: bool) -> None:
        for k in range(len(self.propostas)):
            self.marcar(k, valor)

    def regras(self) -> tuple[str, ...]:
        if not self.var_regras:
            return self.regras_iniciais
        return tuple(nome for nome, var in self.var_regras.items() if var.get())

    def _ler(self) -> tuple[list[int], tuple[str, ...], bool]:
        hifenizar = self.var_hifenizar.get() if self.var_hifenizar is not None else self.hifenizar_inicial
        return [k for k, marcada in enumerate(self.marcadas) if marcada], self.regras(), bool(hifenizar)

    def _foco_inicial(self) -> None:
        if self.arvore is not None:
            self.arvore.focus_set()
            if self.propostas:
                self.arvore.selection_set("0")
                self.arvore.focus("0")


class Tipografo:
    """Os dois comandos da §8.14 na janela."""

    def __init__(self, janela: Any):
        self.j = janela
        self.comandos = {"tipografia": self.tipografia, "juntar_hifenizadas": self.juntar_hifenizadas}

    # -- propostas ---------------------------------------------------------------

    def _capitulo_de(self, arquivo: str) -> Any:
        """O capítulo como está agora: do widget se a aba está aberta em texto, senão do modelo."""
        j = self.j
        aba = j.abas.por_arquivo(arquivo)
        if aba is not None and aba.modo == "texto" and aba.widget is not None:
            return aba.widget.sincronizar()
        return j._exigir_projeto().livro.capitulo(arquivo)

    def _arquivos(self, escopo: str) -> list[str]:
        j = self.j
        projeto = j._exigir_projeto()
        if escopo == "livro":
            return [c.arquivo for c in projeto.livro.capitulos]
        aba = j.aba_ativa()
        if aba is None or aba.tipo != "capitulo":
            raise ValueError("abra um capítulo (ou escolha o escopo livro)")
        return [aba.arquivo]

    def propostas(self, escopo: str = "capitulo", regras: Sequence[str] = core_tipo.REGRAS) -> list[tuple]:
        """`(arquivo, onde, alvo, troca)` para o escopo."""
        j = self.j
        idioma = j._exigir_projeto().livro.metadados.idioma
        saida: list[tuple] = []
        for arquivo in self._arquivos(escopo):
            cap = self._capitulo_de(arquivo)
            if cap is None:
                continue
            for alvo, troca in core_tipo.propor_capitulo(cap, idioma, regras):
                saida.append((arquivo, self._onde(alvo, cap), alvo, troca))
        return saida

    @staticmethod
    def _onde(alvo: Any, cap: Any) -> str:
        caminho = alvo.caminho
        if caminho[0] == "nota":
            return f"nota {caminho[1]}"
        if caminho[0] == "celula":
            return f"célula {caminho[1] + 1},{caminho[2] + 1}"
        if caminho[0] == "legenda":
            return "legenda"
        posicao = next((k + 1 for k, b in enumerate(cap.blocos) if b.id == alvo.bloco_id), 0)
        return f"bloco {posicao}" if posicao else f"bloco {alvo.bloco_id}"

    # -- comandos ----------------------------------------------------------------

    def tipografia(self, escopo: str | None = None, regras: Sequence[str] | None = None) -> dict[str, int]:
        """Ferramentas → Tipografia…: propõe, pergunta (prévia por ocorrência) e aplica o marcado."""
        j = self.j
        projeto = j._exigir_projeto()
        if escopo is None:
            indice = j.caixas.escolher("Tipografia", "Onde:", ["Capítulo atual", "Livro inteiro"], "Propor")
            if indice is None:
                return {}
            escopo = "livro" if indice == 1 else "capitulo"
        regras = tuple(regras) if regras is not None else self._regras_preferidas()
        propostas = self.propostas(escopo, regras)
        resposta = j.caixas.tipografia(propostas, regras, projeto.livro.pagina.hifenizar)
        if resposta is None:
            return {}
        escolhidas, regras_escolhidas, hifenizar = resposta
        self._gravar_regras(regras_escolhidas)
        # Uma regra desmarcada na caixa tira as propostas dela; o resto é o que ficou marcado.
        ativas = set(regras_escolhidas)
        pares = [propostas[k] for k in escolhidas if 0 <= k < len(propostas) and propostas[k][3].motivo in ativas]
        contagem = self.aplicar(pares)
        self.hifenizar(bool(hifenizar))          # idempotente: só marca sujo se algo mudou
        total = sum(contagem.values())
        j.status(f"Tipografia: {total} troca(s) em {len(contagem)} arquivo(s)")
        j.log.info("Tipografia: %d troca(s) em %d arquivo(s).", total, len(contagem))
        return contagem

    def _regras_preferidas(self) -> tuple[str, ...]:
        regras = self.j._preferencia("tipografia", None)
        if isinstance(regras, list) and regras:
            return tuple(r for r in regras if r in core_tipo.REGRAS)
        return core_tipo.REGRAS

    def _gravar_regras(self, regras: Sequence[str]) -> None:
        self.j._gravar_preferencia("tipografia", list(regras))

    def juntar_hifenizadas(self, escopo: str | None = None) -> dict[str, int]:
        """Ferramentas → Juntar palavras hifenizadas: o `lexico.juntar_hifenizadas` sobre o capítulo (ou o livro)."""
        j = self.j
        projeto = j._exigir_projeto()
        escopo = escopo or "capitulo"
        lexicos = j.lexicos()
        idioma = projeto.livro.metadados.idioma
        propostas: list[tuple] = []
        for arquivo in self._arquivos(escopo):
            cap = self._capitulo_de(arquivo)
            if cap is None:
                continue
            lex = lexicos(cap.idioma or idioma)
            for alvo, troca in core_tipo.propor_juncoes(cap, lex):
                propostas.append((arquivo, self._onde(alvo, cap), alvo, troca))
        if not propostas:
            j.status("Nenhuma palavra hifenizada para juntar.")
            j.caixas.informar("Nenhuma palavra partida por hífen no fim de linha que o léxico saiba juntar.",
                              "Juntar palavras hifenizadas")
            return {}
        resposta = j.caixas.tipografia(propostas, ("juncao",), projeto.livro.pagina.hifenizar)
        if resposta is None:
            return {}
        escolhidas = resposta[0]
        contagem = self.aplicar([propostas[k] for k in escolhidas if 0 <= k < len(propostas)])
        j.status(f"Juntadas: {sum(contagem.values())} palavra(s)")
        return contagem

    # -- aplicar ---------------------------------------------------------------------

    def aplicar(self, pares: Sequence[tuple]) -> dict[str, int]:
        """As trocas `(arquivo, onde, alvo, troca)`: pelo widget na aba de texto aberta, pelo modelo no resto."""
        from core.editor.busca import Ocorrencia
        from ui.editor.busca import aplicar_no_widget

        j = self.j
        projeto = j._exigir_projeto()
        por_arquivo: dict[str, list[tuple]] = {}
        for par in pares:
            por_arquivo.setdefault(par[0], []).append(par)
        contagem: dict[str, int] = {}
        for arquivo, lista in por_arquivo.items():
            aba = j.abas.por_arquivo(arquivo)
            if aba is not None and aba.modo == "texto" and aba.widget is not None:
                widget = aba.widget
                ordenada = sorted(lista, key=lambda p: (p[2].indice, p[3].ini), reverse=True)
                widget._abrir_composto("tipografia")
                try:
                    for _a, _onde, alvo, troca in ordenada:
                        cap = widget.sincronizar()
                        aplicar_no_widget(widget, cap, Ocorrencia(arquivo, troca.ini, troca.fim, troca.de, alvo),
                                          troca.para)
                finally:
                    widget._fechar_composto()
                contagem[arquivo] = len(lista)
            else:
                cap = projeto.livro.capitulo(arquivo)
                if cap is None:
                    continue
                n = core_tipo.aplicar_no_capitulo(cap, [(p[2], p[3]) for p in lista], projeto.historico)
                if n:
                    projeto.marcar_sujo()
                    contagem[arquivo] = n
                    aba_codigo = j.abas.por_arquivo(arquivo)
                    if aba_codigo is not None:
                        j._recarregar_aba(aba_codigo)
        if contagem:
            j.atualizar()
        return contagem

    def hifenizar(self, ligar: bool) -> bool:
        """`FormatoDePagina.hifenizar` e o `hyphens: auto` na folha padrão (o DOCX lê o mesmo campo)."""
        j = self.j
        projeto = j._exigir_projeto()
        mudou_a_marca = bool(ligar) != bool(projeto.livro.pagina.hifenizar)
        projeto.livro.pagina.hifenizar = bool(ligar)
        mudou_a_folha = core_tipo.aplicar_hifenizacao(projeto.livro, lambda r: j._texto_do_recurso(r))
        if mudou_a_folha and projeto.livro.folhas:
            recurso = projeto.livro.recurso(projeto.livro.folhas[0])
            if recurso is not None and recurso.texto_cru is not None:
                j._gravar_folha_padrao(recurso.texto_cru)
        if mudou_a_marca or mudou_a_folha:
            projeto.marcar_sujo()
            j.log.info("Hifenização: %s.", "ligada" if ligar else "desligada")
        return mudou_a_folha


__all__ = ["DialogoDeTipografia", "Tipografo", "MARCADA", "DESMARCADA"]
