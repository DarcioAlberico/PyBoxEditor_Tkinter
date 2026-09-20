"""
A calha do modo texto: um `Canvas` à esquerda do `tk.Text`, alinhado por `dlineinfo`,
que desenha um ícone por bloco marcado — `!` suspeito, `✗` notação ilegal, `?`
ortografia (ED-03; SPEC_EDITOR DEC-03 "Calha", §13.2).

É a "margem" que o Tk não tem: o widget de texto não desenha nada fora do texto, e
um aviso que dependesse só da cor do fundo falharia para quem não distingue cores.
O ícone é texto (cabe no leitor de tela como qualquer rótulo) e vai na linha em que
o bloco começa.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

ICONES = {"suspeito": ("!", "#8a5a00"), "notacao-ilegal": ("✗", "#b00020"), "orto": ("?", "#b00020"),
          "objeto": ("▣", "#555555"), "nota": ("¹", "#7a3e00")}


class Calha(tk.Canvas):
    def __init__(self, master: tk.Misc, texto: tk.Text, largura: int = 22, **kw: Any):
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("background", "#f4f4f4")
        super().__init__(master, width=largura, takefocus=0, **kw)
        self.texto = texto
        self._icones: dict[str, str] = {}      # id do bloco → tipo do ícone
        self.bind("<Configure>", lambda e: self.redesenhar())

    def marcar(self, bloco_id: str, tipo: str | None) -> None:
        """Dá ao bloco um ícone (`None` tira); redesenha."""
        if tipo is None:
            self._icones.pop(bloco_id, None)
        else:
            if tipo not in ICONES:
                raise ValueError(f"ícone desconhecido: {tipo!r} (há: {', '.join(ICONES)})")
            self._icones[bloco_id] = tipo
        self.redesenhar()

    def icone_de(self, bloco_id: str) -> str | None:
        return self._icones.get(bloco_id)

    def limpar(self) -> None:
        self._icones.clear()
        self.redesenhar()

    def redesenhar(self) -> None:
        self.delete("all")
        if not self._icones:
            return
        for bloco_id, tipo in self._icones.items():
            try:
                indice = self.texto.index(f"bloco:{bloco_id}")
                caixa = self.texto.dlineinfo(indice)
            except tk.TclError:
                continue
            if caixa is None:
                continue          # fora da tela, ou janela ainda não mapeada
            simbolo, cor = ICONES[tipo]
            self.create_text(int(self.cget("width")) // 2, caixa[1] + caixa[3] // 2, text=simbolo, fill=cor,
                             font=("Segoe UI Symbol", 10, "bold"), tags=(f"icone:{bloco_id}", tipo))

    def desenhados(self) -> list[str]:
        """Os ids dos blocos cujo ícone está desenhado agora (os visíveis)."""
        saida = []
        for item in self.find_all():
            for tag in self.gettags(item):
                if tag.startswith("icone:"):
                    saida.append(tag[6:])
        return saida
