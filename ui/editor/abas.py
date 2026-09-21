"""
As abas da janela de edição: uma por arquivo, com o modo (texto ou código) e o
widget que o desenha (ED-02; SPEC_EDITOR §7.1, §9.1, DEC-11).

O modo é **da aba** — o título mostra `[código]`, o `•` de sujo é o do livro. Um
capítulo alterna entre `TextoRico` e `EditorDeCodigo` no mesmo `frame`
(`trocar_widget`); uma folha de estilo só abre em código; o `nav.xhtml` e o NCX
abrem em código **somente leitura**, porque são regenerados ao salvar (DEC-01).
O `Notebook` não sabe o que há em cada aba: quem cria o widget é a janela, por
`criar(frame, aba)`, e é ela que decide o que fazer ao trocar de aba (`ao_trocar`).
"""

from __future__ import annotations

import posixpath
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Any, Callable


@dataclass
class Aba:
    arquivo: str                      # href relativo ao OPF ("Text/cap-0001.xhtml", "Styles/estilo.css")
    tipo: str                         # "capitulo" | "css" | "leitura"
    modo: str                         # "texto" | "codigo"
    frame: ttk.Frame
    widget: Any = None                # TextoRico | EditorDeCodigo
    somente_leitura: bool = False
    dados: dict[str, Any] = field(default_factory=dict)

    @property
    def nome(self) -> str:
        return posixpath.basename(self.arquivo)

    @property
    def sujo(self) -> bool:
        return bool(getattr(self.widget, "sujo", False))

    def titulo(self, sujo_do_livro: bool = False) -> str:
        sufixo = " [código]" if self.modo == "codigo" and self.tipo == "capitulo" else ""
        if self.somente_leitura:
            sufixo += " (leitura)"
        return self.nome + sufixo + (" •" if (self.sujo or sujo_do_livro) else "")


class Abas(ttk.Notebook):
    def __init__(self, master: tk.Misc, ao_trocar: Callable[[Aba | None], Any] | None = None, **kw: Any):
        super().__init__(master, **kw)
        self.ao_trocar = ao_trocar
        self._abas: list[Aba] = []
        self.bind("<<NotebookTabChanged>>", self._trocou)
        self.enable_traversal()

    # -- consultas -------------------------------------------------------------

    @property
    def abas(self) -> list[Aba]:
        return list(self._abas)

    def por_arquivo(self, arquivo: str) -> Aba | None:
        return next((a for a in self._abas if a.arquivo == arquivo), None)

    def ativa(self) -> Aba | None:
        try:
            atual = self.select()
        except tk.TclError:
            return None
        if not atual:
            return None
        return next((a for a in self._abas if str(a.frame) == atual), None)

    def indice(self, aba: Aba) -> int:
        return self._abas.index(aba)

    def __len__(self) -> int:
        return len(self._abas)

    # -- abrir, trocar, fechar -------------------------------------------------

    def abrir(self, arquivo: str, tipo: str, modo: str, criar: Callable[[ttk.Frame, Aba], Any],
              somente_leitura: bool = False) -> Aba:
        """A aba do arquivo (a que já existe, selecionada; senão uma nova com o widget de `criar`)."""
        existente = self.por_arquivo(arquivo)
        if existente is not None:
            self.select(existente.frame)
            return existente
        frame = ttk.Frame(self)
        aba = Aba(arquivo, tipo, modo, frame, somente_leitura=somente_leitura)
        aba.widget = criar(frame, aba)
        if aba.widget is not None:
            aba.widget.pack(fill="both", expand=True)
        self._abas.append(aba)
        self.add(frame, text=aba.titulo())
        self.select(frame)
        return aba

    def trocar_widget(self, aba: Aba, modo: str, criar: Callable[[ttk.Frame, Aba], Any]) -> Any:
        """Destrói o widget da aba e põe outro no lugar (a troca de modo)."""
        if aba.widget is not None:
            try:
                aba.widget.destroy()
            except tk.TclError:
                pass
        aba.modo = modo
        aba.widget = criar(aba.frame, aba)
        if aba.widget is not None:
            aba.widget.pack(fill="both", expand=True)
        self.rotular(aba)
        return aba.widget

    def fechar(self, aba: Aba) -> None:
        if aba not in self._abas:
            return
        self._abas.remove(aba)
        try:
            self.forget(aba.frame)
            aba.frame.destroy()
        except tk.TclError:
            pass

    def fechar_todas(self) -> None:
        for aba in list(self._abas):
            self.fechar(aba)

    def selecionar(self, aba: Aba) -> None:
        self.select(aba.frame)

    # -- rótulos ---------------------------------------------------------------

    def rotular(self, aba: Aba | None = None, sujo_do_livro: bool = False) -> None:
        for a in ([aba] if aba is not None else self._abas):
            try:
                self.tab(a.frame, text=a.titulo(sujo_do_livro))
            except tk.TclError:
                pass

    def _trocou(self, _evento: Any = None) -> None:
        if self.ao_trocar is not None:
            self.ao_trocar(self.ativa())


__all__ = ["Aba", "Abas"]
