"""
A prévia do modo código (ED-08; SPEC_EDITOR DEC-05, §9.6): o XHTML da aba, lido pelo
dialeto (`xhtml.ler`) e desenhado por um `TextoRico` só de leitura — a pré-visualização
**própria**, sem navegador embutido (o `tkinterweb` é o extra `editor-previa`, opcional;
DEC-07). O que não é dialeto aparece como ilha, como no modo texto.

`atualizar(texto)` espera `atraso_ms` (300 ms; o teste usa 0 + `update()`) e redesenha;
um XHTML mal-formado **mantém a prévia anterior** e escreve o erro no rodapé (AC-ED08-7).
`ir_ao_bloco(linha)` rola até o bloco cuja `linha_fonte` é a última ≤ `linha` — é o que o
cursor do código chama —, e um clique na prévia devolve a `linha_fonte` do bloco clicado
por `ao_clicar(linha)`, para o código ir até lá.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from core.editor import xhtml
from core.editor.modelo import Capitulo
from ui.editor.tags import EstiloDeTela
from ui.editor.texto_rico import TextoRico

ATRASO_PADRAO_MS = 300


class Previa(ttk.Frame):
    def __init__(self, master: tk.Misc, atraso_ms: int = ATRASO_PADRAO_MS,
                 ao_clicar: Callable[[int], Any] | None = None, estilo_de_tela: EstiloDeTela | None = None,
                 folhas: Any = (), recursos: Any = None, **kw: Any):
        super().__init__(master, **kw)
        self.atraso_ms = int(atraso_ms)
        self.ao_clicar = ao_clicar
        self.capitulo: Capitulo | None = None
        self.erro: xhtml.ErroDeXhtml | None = None
        self._pendente: str | None = None
        self._agendado: str | None = None
        self._arquivo = ""
        self.rotulo = ttk.Label(self, text="Prévia", anchor="w", padding=(6, 2))
        self.rotulo.pack(side="top", fill="x")
        self.texto_rico = TextoRico(self, estilo_de_tela=estilo_de_tela, folhas=folhas, recursos=recursos)
        self.texto_rico.pack(fill="both", expand=True)
        self.texto_rico.texto.configure(state="disabled", cursor="arrow", takefocus=1)
        self.rodape = ttk.Label(self, text="", anchor="w", foreground="#b00020", padding=(6, 2))
        self.rodape.pack(side="bottom", fill="x")
        self.texto_rico.texto.bind("<Button-1>", self._clique, add="+")
        self.texto_rico.texto.bind("<Key>", lambda e: "break", add="+")

    # -- atualizar ----------------------------------------------------------------

    def atualizar(self, texto: str, arquivo: str = "") -> None:
        """Agenda o redesenho (`atraso_ms`); chamadas seguidas ficam com a última."""
        self._pendente = texto
        self._arquivo = arquivo or self._arquivo
        if self._agendado is not None:
            try:
                self.after_cancel(self._agendado)
            except tk.TclError:
                pass
            self._agendado = None
        if self.atraso_ms <= 0:
            self.mostrar_agora()
            return
        try:
            self._agendado = self.after(self.atraso_ms, self.mostrar_agora)
        except tk.TclError:
            self.mostrar_agora()

    def mostrar_agora(self) -> bool:
        """Desenha o pendente; `False` (e a prévia anterior fica) quando o XHTML não está bem-formado."""
        self._agendado = None
        texto = self._pendente
        if texto is None:
            return False
        self._pendente = None
        erro = xhtml.bem_formado(texto)
        if erro is None:
            try:
                cap = xhtml.ler(texto, self._arquivo)
            except xhtml.ErroDeXhtml as e:
                erro = e
        if erro is not None:
            self.erro = erro
            self.rodape.configure(text=f"XHTML mal-formado (linha {erro.linha}, col {erro.coluna}): {erro.mensagem} "
                                       f"— a prévia mostra a última versão válida")
            return False
        self.erro = None
        self.rodape.configure(text="")
        self.capitulo = cap
        t = self.texto_rico.texto
        t.configure(state="normal")
        try:
            self.texto_rico.carregar(cap)
        finally:
            t.configure(state="disabled")
        return True

    # -- ir e voltar ------------------------------------------------------------------

    def bloco_da_linha(self, linha: int) -> str | None:
        """O id do bloco de cima cuja `linha_fonte` é a última ≤ `linha`."""
        if self.capitulo is None:
            return None
        escolhido = None
        for bloco in self.capitulo.blocos:
            if bloco.linha_fonte is not None and bloco.linha_fonte <= linha:
                escolhido = bloco.id
            elif bloco.linha_fonte is not None and bloco.linha_fonte > linha:
                break
        return escolhido or (self.capitulo.blocos[0].id if self.capitulo.blocos else None)

    def ir_ao_bloco(self, linha: int) -> str | None:
        bloco_id = self.bloco_da_linha(int(linha))
        if bloco_id is None or bloco_id not in self.texto_rico.ordem:
            return None
        t = self.texto_rico.texto
        t.configure(state="normal")
        try:
            self.texto_rico.ir_para(bloco_id, 0)
            t.tag_remove("suspeito", "1.0", "end")
            t.tag_add("suspeito", self.texto_rico._inicio_de(bloco_id), self.texto_rico._fim_de(bloco_id))
        finally:
            t.configure(state="disabled")
        return bloco_id

    def linha_do_indice(self, indice: str = "insert") -> int | None:
        """A `linha_fonte` do bloco do índice do widget (`None` fora de bloco)."""
        bloco_id, _desloc = self.texto_rico.posicao_de(indice)
        if bloco_id is None or self.capitulo is None:
            return None
        bloco = self.capitulo.bloco(bloco_id)
        if bloco is None:
            for candidato in self.capitulo.blocos:
                if candidato.id == bloco_id:
                    bloco = candidato
        return bloco.linha_fonte if bloco is not None else None

    def _clique(self, evento: Any) -> None:
        try:
            indice = self.texto_rico.texto.index(f"@{evento.x},{evento.y}")
        except tk.TclError:
            return
        linha = self.linha_do_indice(indice)
        if linha is not None and self.ao_clicar is not None:
            self.ao_clicar(linha)

    def limpar(self) -> None:
        self.capitulo = None
        self._pendente = None
        t = self.texto_rico.texto
        t.configure(state="normal")
        try:
            self.texto_rico.carregar(Capitulo(arquivo="previa"))
        finally:
            t.configure(state="disabled")


__all__ = ["Previa", "ATRASO_PADRAO_MS"]
