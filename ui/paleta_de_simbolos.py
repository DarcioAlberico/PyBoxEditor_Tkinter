"""Paleta compacta e rolavel de simbolos usada nas janelas de OCR."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from ui import fontes


def simbolos_da_paleta() -> tuple[str, ...]:
    """Usa a lista canonica da janela de rotulagem, sem duplica-la."""
    from ui.dialogo_rotulagem import _simbolos_da_paleta

    return _simbolos_da_paleta()


def criar_paleta_de_simbolos(parent: tk.Misc, ao_inserir: Callable[[str], None], *,
                             altura: int = 176, largura: int = 260) -> tk.LabelFrame:
    """Cria a paleta mantendo todos os botoes dentro da largura visivel."""
    paleta = tk.LabelFrame(parent, text="Glifos e s\u00edmbolos", padx=3, pady=3)
    paleta.columnconfigure(0, weight=1)
    area = tk.Frame(paleta)
    area.grid(row=0, column=0, sticky="ew")
    area.columnconfigure(0, weight=1)
    canvas = tk.Canvas(area, height=altura, width=largura, highlightthickness=0)
    barra = ttk.Scrollbar(area, orient="vertical", command=canvas.yview)
    conteudo = tk.Frame(canvas)
    janela = canvas.create_window((0, 0), window=conteudo, anchor="nw")
    canvas.configure(yscrollcommand=barra.set)
    canvas.grid(row=0, column=0, sticky="ew")
    barra.grid(row=0, column=1, sticky="ns")
    conteudo.bind("<Configure>",
                  lambda _evento: canvas.configure(scrollregion=canvas.bbox("all")))

    def ajustar_largura(evento):
        canvas.itemconfigure(janela, width=max(1, evento.width))
        canvas.configure(scrollregion=canvas.bbox("all"))

    canvas.bind("<Configure>", ajustar_largura)

    def rolar(evento):
        if getattr(evento, "num", None) == 4:
            passos = -1
        elif getattr(evento, "num", None) == 5:
            passos = 1
        else:
            passos = -int(evento.delta / 120) or (-1 if evento.delta > 0 else 1)
        canvas.yview_scroll(passos, "units")
        return "break"

    for sequencia in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        canvas.bind(sequencia, rolar)

    colunas = 5
    for coluna in range(colunas):
        conteudo.columnconfigure(coluna, weight=1)
    base_fonte = ("Segoe UI Symbol", 10, "normal")
    for pos, simbolo in enumerate(simbolos_da_paleta()):
        botao = tk.Button(conteudo, text=simbolo,
                          width=max(2, min(4, len(simbolo) + 1)),
                          font=fontes.fonte_do_rotulo(simbolo, base_fonte),
                          command=lambda s=simbolo: ao_inserir(s))
        botao.grid(row=pos // colunas, column=pos % colunas,
                   padx=1, pady=1, sticky="ew")
        for sequencia in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            botao.bind(sequencia, rolar)
    return paleta
