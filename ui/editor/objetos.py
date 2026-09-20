"""
Os objetos embutidos no modo texto: o registro que liga a janela embutida ao bloco
(ou ao trecho-ilha), e o `ObjetoGenerico` que desenha qualquer bloco que ainda não
tem desenho próprio (ED-03; SPEC_EDITOR DEC-03 "Objetos").

Um diagrama, uma figura, uma tabela ou uma ilha entram no `tk.Text` por
`window_create`, como um caractere. O `RegistroDeObjetos` guarda `nome da janela →
bloco`, e é de lá que o `dump` recupera o bloco **intacto** — a ilha byte a byte, o
diagrama com o FEN e a orientação, sem nada passar por tag. Enquanto a ED-04/05 não
dá a cada tipo o seu desenho, todos saem como `ObjetoGenerico`: uma caixa cinza com o
tipo do bloco e um resumo, protegida — o capítulo abre e sobrevive ao `dump` antes de
os objetos existirem de verdade.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from core.editor import modelo
from core.editor.modelo import (Bloco, Diagrama, Figura, IlhaBruta, MarcaDePagina, QuebraDePagina, Separador,
                                Tabela, Trecho)

ROTULOS = {
    "Diagrama": "Diagrama", "Figura": "Figura", "Tabela": "Tabela", "IlhaBruta": "Fora do dialeto",
    "MarcaDePagina": "Página", "QuebraDePagina": "Quebra de página", "Separador": "Separador",
}
DICA_DA_ILHA = "conteúdo fora do dialeto — editável no modo código (F11)"


def resumo_de(objeto: Any) -> str:
    """O que a caixa cinza escreve ao lado do tipo."""
    if isinstance(objeto, Diagrama):
        lado = {"w": "brancas", "b": "pretas"}.get(objeto.lado, "lado?")
        return f"{objeto.posicao}  ({lado}{', revisar' if objeto.estado == 'revisar' else ''})"
    if isinstance(objeto, Figura):
        return objeto.recurso + (f" — {objeto.alt}" if objeto.alt else "")
    if isinstance(objeto, Tabela):
        return f"{len(objeto.filas)}×{objeto.colunas}"
    if isinstance(objeto, IlhaBruta):
        return f"<{objeto.elemento}>"
    if isinstance(objeto, MarcaDePagina):
        return str(objeto.pagina)
    if isinstance(objeto, Trecho) and objeto.ilha:
        nome = objeto.ilha.lstrip("<").split(None, 1)[0].rstrip("/>") if objeto.ilha.startswith("<") else "…"
        return f"<{nome}>"
    if isinstance(objeto, (QuebraDePagina, Separador)):
        return ""
    return modelo.texto_de(objeto)[:40] if isinstance(objeto, Bloco) else ""


class RegistroDeObjetos:
    """`nome da janela → bloco ou trecho`, e o inverso — o que o `dump` e a seleção de objeto consultam."""

    def __init__(self) -> None:
        self._por_nome: dict[str, Any] = {}
        self._por_id: dict[str, str] = {}

    def registrar(self, nome: str, objeto: Any) -> None:
        self._por_nome[nome] = objeto
        if isinstance(objeto, Bloco):
            self._por_id[objeto.id] = nome

    def objeto(self, nome: str) -> Any:
        return self._por_nome.get(nome)

    def nome_de(self, bloco_id: str) -> str | None:
        return self._por_id.get(bloco_id)

    def esquecer(self, nome: str) -> None:
        objeto = self._por_nome.pop(nome, None)
        if isinstance(objeto, Bloco):
            self._por_id.pop(objeto.id, None)

    def limpar(self) -> None:
        self._por_nome.clear()
        self._por_id.clear()

    def __contains__(self, nome: str) -> bool:
        return nome in self._por_nome

    def __len__(self) -> int:
        return len(self._por_nome)

    def como_dicionario(self) -> dict[str, Any]:
        return dict(self._por_nome)


class ObjetoGenerico(ttk.Frame):
    """
    A caixa cinza: o tipo do bloco, um resumo, e uma dica para a ilha. É um botão de
    verdade por dentro (`ttk.Label` com `takefocus`), para o teclado alcançar (§13.2).
    """

    def __init__(self, master: tk.Misc, objeto: Any, inline: bool = False, ao_ativar: Any = None, **kw: Any):
        super().__init__(master, **kw)
        self.objeto = objeto
        self.inline = inline
        tipo = type(objeto).__name__
        if isinstance(objeto, Trecho):
            rotulo = "ilha"
            texto = resumo_de(objeto)
        else:
            rotulo = ROTULOS.get(tipo, tipo)
            resumo = resumo_de(objeto)
            texto = f"{rotulo}: {resumo}" if resumo else rotulo
        self.rotulo = tk.Label(self, text=texto, relief="groove", borderwidth=1, padx=6 if not inline else 3,
                               pady=3 if not inline else 0, background="#e6e6e6", foreground="#333333",
                               takefocus=1, cursor="arrow", highlightthickness=2, highlightbackground="#e6e6e6",
                               highlightcolor="#0645ad")
        self.rotulo.pack(fill="x")
        self.dica = DICA_DA_ILHA if isinstance(objeto, (IlhaBruta, Trecho)) else ""
        if ao_ativar is not None:
            self.rotulo.bind("<Double-Button-1>", lambda e: ao_ativar(objeto))
            self.rotulo.bind("<Return>", lambda e: ao_ativar(objeto))
        self.rotulo.bind("<Enter>", self._mostrar_dica)
        self.rotulo.bind("<Leave>", self._esconder_dica)
        self._janela_da_dica: tk.Toplevel | None = None

    @property
    def texto(self) -> str:
        return self.rotulo.cget("text")

    def selecionar(self, sim: bool) -> None:
        self.rotulo.configure(background="#b8d4ff" if sim else "#e6e6e6")

    def _mostrar_dica(self, _evento: Any = None) -> None:
        if not self.dica or self._janela_da_dica is not None:
            return
        try:
            dica = tk.Toplevel(self)
            dica.overrideredirect(True)
            tk.Label(dica, text=self.dica, relief="solid", borderwidth=1, background="#ffffe0",
                     foreground="#1f1f1f", padx=4, pady=2).pack()
            dica.geometry(f"+{self.winfo_rootx()}+{self.winfo_rooty() + self.winfo_height() + 2}")
            self._janela_da_dica = dica
        except tk.TclError:
            self._janela_da_dica = None

    def _esconder_dica(self, _evento: Any = None) -> None:
        if self._janela_da_dica is not None:
            try:
                self._janela_da_dica.destroy()
            except tk.TclError:
                pass
            self._janela_da_dica = None
