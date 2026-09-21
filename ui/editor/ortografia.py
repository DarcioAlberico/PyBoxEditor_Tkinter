"""
A ortografia na tela: o sublinhado `orto` no modo texto, a caixa do `F7` e a do
dicionário do livro (ED-06; SPEC_EDITOR §8.13).

O `tk.Text` não desenha sublinhado ondulado (§15): a suspeita leva a tag `orto` —
sublinhado vermelho, tag de tela que o `dump` descarta. A caixa do `F7` é **uma só
para a verificação inteira**: mostra a palavra, o contexto e as sugestões, e espera a
resposta (`wait_variable`); a janela chama `perguntar(suspeita, sugestoes)` por
suspeita e `fechar()` no fim — e o teste chama `responder(acao, palavra)` em vez de
esperar. As ações são as da §8.13: Ignorar, Ignorar todas, Adicionar, Trocar (e Trocar
todas, que o Word tem e custa nada).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Sequence

from core.editor.ortografia import Suspeita
from ui.editor.dialogos import _Dialogo

ACOES = ("ignorar", "ignorar_todas", "adicionar", "trocar", "trocar_todas", "fechar")


def marcar(texto_rico: Any, suspeitas: Sequence[Suspeita]) -> int:
    """A tag `orto` em cada suspeita endereçável do widget; devolve quantas marcou."""
    texto = texto_rico.texto
    texto.tag_remove("orto", "1.0", "end")
    marcadas = 0
    for s in suspeitas:
        if not s.alvo.enderecavel:
            continue
        base = s.alvo.deslocamento or 0
        a = texto_rico.indice_de(s.alvo.bloco_id, base + s.ini)
        b = texto_rico.indice_de(s.alvo.bloco_id, base + s.fim)
        if a is None or b is None:
            continue
        texto.tag_add("orto", a, b)
        marcadas += 1
    return marcadas


def desmarcar(texto_rico: Any) -> None:
    texto_rico.texto.tag_remove("orto", "1.0", "end")


class DialogoDeOrtografia(_Dialogo):
    """A caixa do `F7` (ver o cabeçalho)."""

    def __init__(self, master: tk.Misc, titulo: str = "Verificar ortografia"):
        super().__init__(master, titulo)
        self.suspeita: Suspeita | None = None
        self.var_palavra: tk.StringVar | None = None
        self.var_troca: tk.StringVar | None = None
        self.var_contexto: tk.StringVar | None = None
        self.var_idioma: tk.StringVar | None = None
        self._resposta: tk.StringVar | None = None
        self.lista: tk.Listbox | None = None
        self.resposta: tuple[str, str] | None = None

    def _construir(self) -> tk.Toplevel:
        top = self._abrir((True, False))
        self.var_palavra = tk.StringVar(master=top)
        self.var_troca = tk.StringVar(master=top)
        self.var_contexto = tk.StringVar(master=top)
        self.var_idioma = tk.StringVar(master=top)
        self._resposta = tk.StringVar(master=top)
        corpo = ttk.Frame(top, padding=12)
        corpo.grid(row=0, column=0, sticky="nsew")
        top.columnconfigure(0, weight=1)
        corpo.columnconfigure(1, weight=1)
        ttk.Label(corpo, text="Palavra desconhecida:").grid(row=0, column=0, sticky="w")
        ttk.Label(corpo, textvariable=self.var_palavra, font=("Segoe UI", 11, "bold")).grid(row=0, column=1,
                                                                                            sticky="w")
        ttk.Label(corpo, textvariable=self.var_idioma, foreground="#555555").grid(row=0, column=2, sticky="e")
        ttk.Label(corpo, textvariable=self.var_contexto, wraplength=460, justify="left", foreground="#333333").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(4, 8))
        ttk.Label(corpo, text="Sugestões:").grid(row=2, column=0, sticky="nw")
        self.lista = tk.Listbox(corpo, height=6, width=40, exportselection=False, highlightthickness=2,
                                activestyle="dotbox")
        self.lista.grid(row=2, column=1, sticky="ew")
        self.lista.bind("<<ListboxSelect>>", self._escolheu)
        self.lista.bind("<Double-Button-1>", lambda e: self.responder("trocar"))
        ttk.Label(corpo, text="Trocar por:").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.campo_troca = ttk.Entry(corpo, textvariable=self.var_troca, width=40)
        self.campo_troca.grid(row=3, column=1, sticky="ew", pady=(6, 0))
        botoes = ttk.Frame(corpo)
        botoes.grid(row=2, column=2, rowspan=2, sticky="ne", padx=(10, 0))
        self.botoes: dict[str, ttk.Button] = {}
        for acao, rotulo in (("ignorar", "Ignorar"), ("ignorar_todas", "Ignorar todas"), ("adicionar", "Adicionar"),
                             ("trocar", "Trocar"), ("trocar_todas", "Trocar todas"), ("fechar", "Fechar")):
            botao = ttk.Button(botoes, text=rotulo, command=lambda a=acao: self.responder(a), width=14)
            botao.pack(fill="x", pady=1)
            self.botoes[acao] = botao
        top.bind("<Return>", lambda e: self.responder("trocar"))
        top.protocol("WM_DELETE_WINDOW", lambda: self.responder("fechar"))
        top.bind("<Escape>", lambda e: self.responder("fechar"))
        return top

    def _escolheu(self, _evento: Any = None) -> None:
        assert self.lista is not None and self.var_troca is not None
        selecao = self.lista.curselection()
        if selecao:
            self.var_troca.set(self.lista.get(selecao[0]))

    def mostrar_suspeita(self, suspeita: Suspeita, sugestoes: Sequence[str]) -> None:
        """Põe a suspeita na caixa (sem esperar)."""
        self.construir()
        assert self.lista is not None and self.var_palavra is not None and self.var_troca is not None
        assert self.var_contexto is not None and self.var_idioma is not None
        self.suspeita = suspeita
        self.resposta = None
        self.var_palavra.set(suspeita.palavra)
        self.var_idioma.set(f"[{suspeita.idioma}]" if suspeita.idioma else "")
        self.var_contexto.set(suspeita.contexto)
        self.lista.delete(0, "end")
        for s in sugestoes:
            self.lista.insert("end", s)
        self.var_troca.set(sugestoes[0] if sugestoes else suspeita.palavra)
        if sugestoes:
            self.lista.selection_set(0)
            self.lista.activate(0)

    def perguntar(self, suspeita: Suspeita, sugestoes: Sequence[str]) -> tuple[str, str]:
        """Mostra a suspeita e espera a ação; `(ação, palavra da troca)`."""
        self.mostrar_suspeita(suspeita, sugestoes)
        assert self.top is not None and self._resposta is not None
        self.top.deiconify()
        self.campo_troca.focus_set()
        self._resposta.set("")
        self.top.wait_variable(self._resposta)
        return self.resposta or ("fechar", "")

    def responder(self, acao: str, palavra: str | None = None) -> tuple[str, str]:
        """A resposta (o botão, ou o teste): solta `perguntar`."""
        if acao not in ACOES:
            raise ValueError(f"ação desconhecida: {acao!r}")
        if palavra is None:
            palavra = self.var_troca.get() if self.var_troca is not None else ""
        self.resposta = (acao, palavra)
        if self._resposta is not None:
            self._resposta.set(acao)
        return self.resposta

    def fechar(self) -> None:
        if self._resposta is not None and self.top is not None:
            self.resposta = ("fechar", "")
            self._resposta.set("fechar")
        self._fechar()

    def _foco_inicial(self) -> None:
        self.campo_troca.focus_set()


class DialogoDoDicionario(_Dialogo):
    """"Dicionário do livro…": as palavras de `<livro>.lexico.txt`, com acrescentar e remover."""

    def __init__(self, master: tk.Misc, lexicos: Any, titulo: str = "Dicionário do livro"):
        super().__init__(master, titulo)
        self.lexicos = lexicos
        self.lista: tk.Listbox | None = None
        self.var_nova: tk.StringVar | None = None

    def _construir(self) -> tk.Toplevel:
        top = self._abrir((True, True))
        self.var_nova = tk.StringVar(master=top)
        corpo = ttk.Frame(top, padding=12)
        corpo.grid(row=0, column=0, sticky="nsew")
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        corpo.rowconfigure(1, weight=1)
        corpo.columnconfigure(0, weight=1)
        caminho = self.lexicos.caminho_do_livro or ""
        ttk.Label(corpo, text=f"Palavras deste livro ({caminho or 'livro ainda não salvo'}):", wraplength=460,
                  justify="left").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.lista = tk.Listbox(corpo, height=14, width=48, exportselection=False, highlightthickness=2,
                                activestyle="dotbox")
        barra = ttk.Scrollbar(corpo, orient="vertical", command=self.lista.yview)
        self.lista.configure(yscrollcommand=barra.set)
        self.lista.grid(row=1, column=0, sticky="nsew")
        barra.grid(row=1, column=1, sticky="ns")
        self.recarregar()
        linha = ttk.Frame(corpo)
        linha.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.campo_nova = ttk.Entry(linha, textvariable=self.var_nova, width=30)
        self.campo_nova.pack(side="left", fill="x", expand=True)
        ttk.Button(linha, text="Adicionar", command=self.adicionar).pack(side="left", padx=(6, 0))
        ttk.Button(linha, text="Remover", command=self.remover).pack(side="left", padx=(6, 0))
        self.campo_nova.bind("<Return>", lambda e: self.adicionar())
        botoes = ttk.Frame(corpo)
        botoes.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        self.botao_ok = ttk.Button(botoes, text="Fechar", command=self.confirmar, default="active")
        self.botao_ok.pack(side="right")
        return top

    def recarregar(self) -> list[str]:
        assert self.lista is not None
        palavras = list(self.lexicos.palavras_do_livro())
        self.lista.delete(0, "end")
        for p in palavras:
            self.lista.insert("end", p)
        return palavras

    def adicionar(self, palavra: str | None = None) -> bool:
        assert self.var_nova is not None
        palavra = (palavra if palavra is not None else self.var_nova.get()).strip()
        if not palavra:
            return False
        nova = self.lexicos.adicionar(palavra)
        self.var_nova.set("")
        self.recarregar()
        return nova

    def remover(self, palavra: str | None = None) -> bool:
        assert self.lista is not None
        if palavra is None:
            selecao = self.lista.curselection()
            if not selecao:
                return False
            palavra = self.lista.get(selecao[0])
        estava = self.lexicos.remover(palavra)
        self.recarregar()
        return estava

    def _foco_inicial(self) -> None:
        self.campo_nova.focus_set()


class Corretor:
    """
    O `F7` na janela: verifica o capítulo ativo, sublinha, e percorre as suspeitas
    perguntando à caixa (`janela.caixas.ortografia`, que o teste troca por respostas
    prontas). Uma troca desloca as suspeitas seguintes do mesmo alvo; "Ignorar todas" e
    "Adicionar" valem para o resto da verificação (e a segunda, para sempre: vai ao
    `<livro>.lexico.txt`). No modo código, as suspeitas vão para Resultados com a linha.
    """

    def __init__(self, janela: Any):
        self.j = janela
        self.comandos = {"ortografia": self.verificar, "dicionario": self.dicionario}

    def lexicos(self) -> Any:
        return self.j.lexicos()

    def verificar(self) -> dict[str, int]:
        from core.editor import ortografia as core_orto
        from core.editor import busca as busca_mod
        from ui.editor import busca as busca_ui

        j = self.j
        projeto = j._exigir_projeto()
        aba = j.aba_ativa()
        if aba is None or aba.tipo != "capitulo":
            raise ValueError("abra um capítulo para verificar a ortografia")
        lexicos = self.lexicos()
        idioma = projeto.livro.metadados.idioma
        if aba.modo == "codigo":
            return self._no_codigo(aba, lexicos, idioma)
        widget = j._texto()
        cap = widget.sincronizar()
        suspeitas = core_orto.verificar(cap, lexicos, idioma, lexicos.ignoradas)
        marcar(widget, suspeitas)
        contagem = {"suspeitas": len(suspeitas), "trocadas": 0, "adicionadas": 0, "ignoradas": 0}
        if not suspeitas:
            j.status("Ortografia: nenhuma palavra desconhecida.")
            j.caixas.informar("Nenhuma palavra desconhecida neste capítulo.", "Verificar ortografia")
            return contagem
        trocas_todas: dict[str, str] = {}
        k = 0
        try:
            while k < len(suspeitas):
                s = suspeitas[k]
                if s.palavra.lower() in lexicos.ignoradas or core_orto.conhecida(s.palavra, lexicos(s.idioma)):
                    k += 1
                    continue
                if s.palavra in trocas_todas:
                    self._trocar(widget, s, trocas_todas[s.palavra], suspeitas, k)
                    contagem["trocadas"] += 1
                    k += 1
                    continue
                busca_ui.selecionar_ocorrencia(widget, busca_mod.Ocorrencia(s.arquivo, s.ini, s.fim, s.palavra,
                                                                              s.alvo))
                acao, palavra = j.caixas.ortografia(s, lexicos.sugestoes(s.palavra, s.idioma))
                if acao == "fechar":
                    break
                if acao == "ignorar":
                    contagem["ignoradas"] += 1
                elif acao == "ignorar_todas":
                    lexicos.ignorar(s.palavra)
                    contagem["ignoradas"] += 1
                elif acao == "adicionar":
                    lexicos.adicionar(s.palavra)
                    contagem["adicionadas"] += 1
                elif acao in ("trocar", "trocar_todas"):
                    palavra = (palavra or "").strip()
                    if not palavra:
                        raise ValueError("digite a palavra que entra no lugar")
                    if acao == "trocar_todas":
                        trocas_todas[s.palavra] = palavra
                    self._trocar(widget, s, palavra, suspeitas, k)
                    contagem["trocadas"] += 1
                k += 1
        finally:
            j.caixas.ortografia_fim()
        restantes = core_orto.verificar(widget.sincronizar(), lexicos, idioma, lexicos.ignoradas)
        marcar(widget, restantes)
        j.status(f"Ortografia: {contagem['trocadas']} trocada(s), {contagem['adicionadas']} adicionada(s), "
                 f"{len(restantes)} ainda desconhecida(s).")
        j.log.info("Ortografia em %s: %s.", aba.nome, contagem)
        return contagem

    def _trocar(self, widget: Any, s: Any, por: str, suspeitas: list, k: int) -> None:
        from core.editor import busca as busca_mod
        from ui.editor import busca as busca_ui

        cap = widget.sincronizar()
        ocorrencia = busca_mod.Ocorrencia(s.arquivo, s.ini, s.fim, s.palavra, s.alvo)
        busca_ui.aplicar_no_widget(widget, cap, ocorrencia, por)
        delta = len(por) - (s.fim - s.ini)
        if delta:
            for t in suspeitas[k + 1:]:
                if t.alvo.bloco_id == s.alvo.bloco_id and t.alvo.caminho == s.alvo.caminho and t.ini >= s.fim:
                    t.ini += delta
                    t.fim += delta

    def _no_codigo(self, aba: Any, lexicos: Any, idioma: str) -> dict[str, int]:
        from core.editor import ortografia as core_orto
        from core.editor import xhtml
        from ui.editor.resultados import Resultado

        j = self.j
        texto = aba.widget.texto_todo()
        erro = xhtml.bem_formado(texto)
        if erro is not None:
            raise ValueError(f"o XHTML precisa estar bem-formado para a ortografia: {erro}")
        cap = xhtml.ler(texto, aba.arquivo)
        suspeitas = core_orto.verificar(cap, lexicos, idioma, lexicos.ignoradas)
        itens = []
        for s in suspeitas:
            bloco = cap.bloco(s.alvo.bloco_id)
            linha = getattr(bloco, "linha_fonte", None) or 1
            itens.append(Resultado(aba.arquivo, f"linha {linha}", f"{s.palavra}: {s.contexto}",
                                   {"linha": linha, "coluna": 1}))
        j.resultados.definir(itens, f"Ortografia: {len(itens)} palavra(s) desconhecida(s)")
        j._focar_inferior(j.resultados, j.resultados.foco)
        j.status(f"Ortografia: {len(itens)} palavra(s) desconhecida(s) (modo código: veja Resultados).")
        return {"suspeitas": len(itens), "trocadas": 0, "adicionadas": 0, "ignoradas": 0}

    def dicionario(self) -> Any:
        self.j._exigir_projeto()
        lexicos = self.lexicos()
        self.j.caixas.dicionario(lexicos)
        return lexicos


__all__ = ["marcar", "desmarcar", "DialogoDeOrtografia", "DialogoDoDicionario", "Corretor", "ACOES"]
