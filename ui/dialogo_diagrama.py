"""
A posição lida, ao lado do diagrama de onde ela saiu (F7.1).

A leitura acerta 94,5% das casas — cerca de três e meia erradas num tabuleiro de
64. Um FEN abre em qualquer programa de xadrez e vira fato; ninguém confere 64
casas depois. Então o diálogo não pergunta "quer salvar?": ele põe o recorte
impresso e a leitura **lado a lado, na mesma escala**, que é o único jeito de a
conferência custar segundos em vez de minutos.

É a mesma decisão da F3.6, pelo mesmo motivo: o que o programa não tem como
garantir, ele mostra.
"""

import tkinter as tk
from tkinter import ttk
from typing import List, Optional

import numpy as np
from PIL import Image, ImageTk

from core import diagrama as diag


LADO_CASA = 44
COR_CLARA = "#F0D9B5"
COR_ESCURA = "#B58863"
COR_ARBITRADA = "#E53935"       # a legalidade mexeu nesta casa
COR_DUVIDA = "#FB8C00"

#: Glifos Unicode das peças. O tabuleiro desenhado usa fonte do sistema; se ela
#: não tiver as figurinas, o `_FALLBACK` mantém a posição legível com letras.
GLIFOS = {"K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
          "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟"}

#: Abaixo disto a leitura da casa é duvidosa mesmo quando ninguém a arbitrou.
CONFIANCA_BAIXA = 0.55


class DialogoDiagrama:
    """Mostra as leituras de uma página. Devolve o FEN escolhido, ou None."""

    def __init__(self, parent, imagem, leituras: List[diag.Leitura]):
        self.parent = parent
        self.imagem = imagem
        self.leituras = leituras
        self.atual = 0
        self.resultado: Optional[str] = None
        self._fotos = []

    # ------------------------------------------------------------------

    def construir(self):
        self.top = tk.Toplevel(self.parent)
        self.top.title("Posição lida do diagrama")
        self.top.transient(self.parent)

        cabecalho = ttk.Frame(self.top, padding=(10, 8))
        cabecalho.pack(fill="x")
        self.lbl_titulo = ttk.Label(cabecalho, font=("Segoe UI", 10, "bold"))
        self.lbl_titulo.pack(side="left")
        if len(self.leituras) > 1:
            ttk.Button(cabecalho, text="◀", width=3,
                       command=lambda: self._ir(-1)).pack(side="right")
            ttk.Button(cabecalho, text="▶", width=3,
                       command=lambda: self._ir(1)).pack(side="right", padx=(0, 4))

        corpo = ttk.Frame(self.top, padding=(10, 0))
        corpo.pack(fill="both", expand=True)

        esquerda = ttk.LabelFrame(corpo, text="o que está impresso", padding=6)
        esquerda.pack(side="left", padx=(0, 10))
        self.lbl_recorte = tk.Label(esquerda, background="white")
        self.lbl_recorte.pack()

        direita = ttk.LabelFrame(corpo, text="o que foi lido", padding=6)
        direita.pack(side="left")
        self.canvas = tk.Canvas(direita, width=8 * LADO_CASA,
                                height=8 * LADO_CASA, highlightthickness=0)
        self.canvas.pack()

        rodape = ttk.Frame(self.top, padding=(10, 8))
        rodape.pack(fill="x")

        ttk.Label(rodape, text="FEN:").grid(row=0, column=0, sticky="w")
        self.var_fen = tk.StringVar()
        entrada = ttk.Entry(rodape, textvariable=self.var_fen, width=64)
        entrada.grid(row=0, column=1, sticky="ew", padx=6)
        rodape.columnconfigure(1, weight=1)
        ttk.Button(rodape, text="Copiar",
                   command=self._copiar).grid(row=0, column=2)

        self.lbl_avisos = ttk.Label(rodape, foreground="#B71C1C",
                                    wraplength=680, justify="left")
        self.lbl_avisos.grid(row=1, column=0, columnspan=3, sticky="w",
                             pady=(8, 0))

        botoes = ttk.Frame(self.top, padding=(10, 8))
        botoes.pack(fill="x")
        ttk.Button(botoes, text="Fechar",
                   command=self._fechar).pack(side="right")
        ttk.Button(botoes, text="Usar este FEN",
                   command=self._confirmar).pack(side="right", padx=(0, 6))

        self.top.bind("<Escape>", lambda e: self._fechar())
        self.top.bind("<Left>", lambda e: self._ir(-1))
        self.top.bind("<Right>", lambda e: self._ir(1))
        self.top.protocol("WM_DELETE_WINDOW", self._fechar)
        self._desenhar()
        return self.top

    def mostrar(self) -> Optional[str]:
        self.construir()
        self.top.grab_set()
        self.top.focus_set()
        self.parent.wait_window(self.top)
        return self.resultado

    # ------------------------------------------------------------------

    def _ir(self, passo):
        if len(self.leituras) > 1:
            self.atual = (self.atual + passo) % len(self.leituras)
            self._desenhar()

    def _leitura(self) -> diag.Leitura:
        return self.leituras[self.atual]

    def _desenhar(self):
        leitura = self._leitura()
        self.lbl_titulo.config(
            text=f"Diagrama {self.atual + 1} de {len(self.leituras)}  —  "
                 f"{leitura.resumo()}")
        self.var_fen.set(leitura.fen())
        self.lbl_avisos.config(text="\n".join(leitura.avisos))

        self._fotos.clear()
        arr = np.asarray(self.imagem)
        x1, y1, x2, y2 = leitura.caixa
        recorte = arr[max(0, y1):y2, max(0, x1):x2]
        if recorte.size:
            img = Image.fromarray(recorte).convert("L").resize(
                (8 * LADO_CASA, 8 * LADO_CASA), Image.LANCZOS)
            foto = ImageTk.PhotoImage(img)
            self._fotos.append(foto)
            self.lbl_recorte.config(image=foto)

        self.canvas.delete("all")
        for casa in leitura.casas:
            x, y = casa.coluna * LADO_CASA, casa.linha * LADO_CASA
            fundo = COR_CLARA if (casa.linha + casa.coluna) % 2 == 0 else COR_ESCURA
            self.canvas.create_rectangle(x, y, x + LADO_CASA, y + LADO_CASA,
                                         fill=fundo, outline="")
            if casa.arbitrada:
                borda = COR_ARBITRADA
            elif casa.simbolo and casa.confianca < CONFIANCA_BAIXA:
                borda = COR_DUVIDA
            else:
                borda = None
            if borda:
                self.canvas.create_rectangle(x + 2, y + 2, x + LADO_CASA - 2,
                                             y + LADO_CASA - 2, outline=borda,
                                             width=3)
            if casa.simbolo:
                self.canvas.create_text(
                    x + LADO_CASA // 2, y + LADO_CASA // 2,
                    text=GLIFOS.get(casa.simbolo, casa.simbolo),
                    font=("Segoe UI Symbol", int(LADO_CASA * 0.62)),
                    fill="black")

        legenda = []
        if any(c.arbitrada for c in leitura.casas):
            legenda.append("vermelho: trocada pela legalidade")
        if any(c.simbolo and c.confianca < CONFIANCA_BAIXA
               for c in leitura.casas):
            legenda.append("laranja: leitura duvidosa")
        if legenda:
            self.lbl_avisos.config(
                text=self.lbl_avisos.cget("text") + "\n" + "   ".join(legenda))

    def _copiar(self):
        self.top.clipboard_clear()
        self.top.clipboard_append(self.var_fen.get())

    def _confirmar(self):
        self.resultado = self.var_fen.get()
        self._fechar()

    def _fechar(self):
        try:
            self.top.grab_release()
        except tk.TclError:
            pass
        self.top.destroy()
