"""
A posição lida, ao lado do diagrama de onde ela saiu — e editável (F7.1, F8.2).

A leitura acerta 94,5% das casas — cerca de três e meia erradas num tabuleiro de
64. Um FEN abre em qualquer programa de xadrez e vira fato; ninguém confere 64
casas depois. Então o diálogo não pergunta "quer salvar?": ele põe o recorte
impresso e a leitura **lado a lado, na mesma escala**, que é o único jeito de a
conferência custar segundos em vez de minutos.

É a mesma decisão da F3.6, pelo mesmo motivo: o que o programa não tem como
garantir, ele mostra.

## O que a F8.2 acrescentou

Mostrar sem deixar corrigir devolvia o trabalho para fora do programa: quem via
um bispo lido como peão copiava um FEN errado ou desistia. Agora a casa se
edita, e o estado disso mora em `core/tabuleiro_edicao.py` — aqui só se desenha
e se despacham cliques.

**Clicar seleciona; quem escreve é a tecla ou a paleta.** Um clique que já
apagasse a casa transformaria a conferência num campo minado. Com uma peça
escolhida na paleta o clique passa a pintar, e clicar na peça escolhida de novo
volta ao modo seguro.
"""

import tkinter as tk
from tkinter import ttk
from typing import List, Optional

import numpy as np
from PIL import Image, ImageTk

from core import diagrama as diag
from core.tabuleiro_edicao import SIMBOLOS, TabuleiroEdicao


LADO_CASA = 44
COR_CLARA = "#F0D9B5"
COR_ESCURA = "#B58863"
COR_ARBITRADA = "#E53935"       # a legalidade mexeu nesta casa
COR_DUVIDA = "#FB8C00"
COR_CORRIGIDA = "#2E7D32"       # a mão do usuário mexeu nesta casa (F8.2)
COR_SELECAO = "#1E88E5"

#: Glifos Unicode das peças. O tabuleiro desenhado usa fonte do sistema; se ela
#: não tiver as figurinas, o `_FALLBACK` mantém a posição legível com letras.
GLIFOS = {"K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
          "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟"}

#: Abaixo disto a leitura da casa é duvidosa mesmo quando ninguém a arbitrou.
CONFIANCA_BAIXA = 0.55

AJUDA = ("Clique numa casa e digite a letra (maiúscula = branca, minúscula = "
         "preta); Delete esvazia. Ou escolha uma peça na paleta e clique para "
         "pintar. Arrastar move a peça. Ctrl+Z desfaz.")


class DialogoDiagrama:
    """Mostra e edita as leituras de uma página. Devolve o FEN escolhido."""

    def __init__(self, parent, imagem, leituras: List[diag.Leitura]):
        self.parent = parent
        self.imagem = imagem
        self.leituras = leituras
        self.atual = 0
        self.resultado: Optional[str] = None
        self._fotos = []
        # Um tabuleiro por leitura, criado na primeira visita: trocar de
        # diagrama e voltar não pode perder o que já foi corrigido.
        self.tabuleiros = {}
        self.selecionada = None      # (linha, coluna) em edição
        self.pincel = None           # peça da paleta, ou None (modo seguro)
        self._arrasto = None

    # ------------------------------------------------------------------

    def tabuleiro(self, indice: Optional[int] = None) -> TabuleiroEdicao:
        indice = self.atual if indice is None else indice
        if indice not in self.tabuleiros:
            self.tabuleiros[indice] = TabuleiroEdicao(self.leituras[indice])
        return self.tabuleiros[indice]

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

        direita = ttk.LabelFrame(corpo, text="o que foi lido — clique para corrigir",
                                 padding=6)
        direita.pack(side="left")
        self.canvas = tk.Canvas(direita, width=8 * LADO_CASA,
                                height=8 * LADO_CASA, highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<ButtonPress-1>", self._no_clique)
        self.canvas.bind("<ButtonRelease-1>", self._no_solta)
        self.canvas.bind("<Button-3>", self._no_direito)

        self._construir_paleta(corpo)

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
        ttk.Label(rodape, text=AJUDA, foreground="gray30", wraplength=680,
                  justify="left").grid(row=2, column=0, columnspan=3,
                                       sticky="w", pady=(6, 0))

        botoes = ttk.Frame(self.top, padding=(10, 8))
        botoes.pack(fill="x")
        ttk.Button(botoes, text="Fechar",
                   command=self._fechar).pack(side="right")
        ttk.Button(botoes, text="Usar este FEN",
                   command=self._confirmar).pack(side="right", padx=(0, 6))
        self.btn_desfazer = ttk.Button(botoes, text="Desfazer",
                                       command=self._desfazer)
        self.btn_desfazer.pack(side="left")
        self.btn_refazer = ttk.Button(botoes, text="Refazer",
                                      command=self._refazer)
        self.btn_refazer.pack(side="left", padx=(6, 0))

        self.top.bind("<Escape>", lambda e: self._fechar())
        self.top.bind("<Left>", lambda e: self._ir(-1))
        self.top.bind("<Right>", lambda e: self._ir(1))
        self.top.bind("<Control-z>", lambda e: self._desfazer())
        self.top.bind("<Control-y>", lambda e: self._refazer())
        self.top.bind("<Control-Shift-Z>", lambda e: self._refazer())
        self.top.bind("<Key>", self._na_tecla)
        self.top.protocol("WM_DELETE_WINDOW", self._fechar)
        self._desenhar()
        return self.top

    def _construir_paleta(self, corpo):
        """A paleta, o lado a jogar e o roque — tudo que não é a casa."""
        painel = ttk.Frame(corpo, padding=(10, 0))
        painel.pack(side="left", fill="y")

        paleta = ttk.LabelFrame(painel, text="peça", padding=4)
        paleta.pack(fill="x")
        self.botoes_paleta = {}
        for i, simbolo in enumerate(SIMBOLOS):
            b = tk.Button(paleta, text=GLIFOS.get(simbolo, simbolo), width=2,
                          font=("Segoe UI Symbol", 14), relief="raised",
                          command=lambda s=simbolo: self._escolher(s))
            b.grid(row=i % 6, column=i // 6, padx=1, pady=1)
            self.botoes_paleta[simbolo] = b
        self.btn_borracha = tk.Button(paleta, text="vazia", width=6,
                                      command=lambda: self._escolher(""))
        self.btn_borracha.grid(row=6, column=0, columnspan=2, pady=(4, 0))

        lado = ttk.LabelFrame(painel, text="lado a jogar", padding=4)
        lado.pack(fill="x", pady=(8, 0))
        self.var_lado = tk.StringVar(value="w")
        for valor, texto in (("w", "brancas"), ("b", "pretas")):
            ttk.Radiobutton(lado, text=texto, value=valor,
                            variable=self.var_lado,
                            command=self._mudar_lado).pack(anchor="w")

        roque = ttk.LabelFrame(painel, text="roque", padding=4)
        roque.pack(fill="x", pady=(8, 0))
        self.vars_roque = {}
        self.checks_roque = {}
        for letra, texto in (("K", "brancas O-O"), ("Q", "brancas O-O-O"),
                             ("k", "pretas O-O"), ("q", "pretas O-O-O")):
            var = tk.BooleanVar(value=False)
            c = ttk.Checkbutton(roque, text=texto, variable=var,
                                command=lambda l=letra: self._mudar_roque(l))
            c.pack(anchor="w")
            self.vars_roque[letra] = var
            self.checks_roque[letra] = c

    def mostrar(self) -> Optional[str]:
        self.construir()
        self.top.grab_set()
        self.top.focus_set()
        self.parent.wait_window(self.top)
        return self.resultado

    # ------------------------------------------------------------------
    # Editar
    # ------------------------------------------------------------------

    def _casa_do_ponto(self, x, y):
        linha, coluna = int(y) // LADO_CASA, int(x) // LADO_CASA
        if 0 <= linha < 8 and 0 <= coluna < 8:
            return linha, coluna
        return None

    def _no_clique(self, evento):
        alvo = self._casa_do_ponto(evento.x, evento.y)
        if alvo is None:
            return
        self._arrasto = alvo
        if self.pincel is not None:
            self.tabuleiro().colocar(*alvo, self.pincel or None)
        self.selecionada = alvo
        self._desenhar()

    def _no_solta(self, evento):
        """Soltar noutra casa é mover a peça; na mesma casa, só selecionar."""
        origem, self._arrasto = self._arrasto, None
        destino = self._casa_do_ponto(evento.x, evento.y)
        if origem is None or destino is None or origem == destino:
            return
        if self.pincel is None and self.tabuleiro().mover(origem, destino):
            self.selecionada = destino
            self._desenhar()

    def _no_direito(self, evento):
        alvo = self._casa_do_ponto(evento.x, evento.y)
        if alvo and self.tabuleiro().limpar(*alvo):
            self.selecionada = alvo
            self._desenhar()

    def _na_tecla(self, evento):
        """
        A letra da peça escreve na casa selecionada. Maiúscula é branca.

        `Delete` e `Backspace` esvaziam. Só age quando há casa selecionada —
        senão a tecla cairia num tabuleiro inteiro sem alvo.
        """
        if self.selecionada is None or evento.state & 0x4:      # Ctrl: não
            return
        tecla = evento.char
        if tecla in SIMBOLOS:
            self.tabuleiro().colocar(*self.selecionada, tecla)
        elif evento.keysym in ("Delete", "BackSpace", "space"):
            self.tabuleiro().limpar(*self.selecionada)
        else:
            return
        self._desenhar()
        return "break"

    def _escolher(self, simbolo):
        """Escolhe (ou desescolhe) o pincel da paleta."""
        self.pincel = None if self.pincel == simbolo else simbolo
        self._desenhar()

    def _mudar_lado(self):
        self.tabuleiro().definir_lado(self.var_lado.get())
        self._desenhar()

    def _mudar_roque(self, letra):
        self.tabuleiro().alternar_roque(letra)
        self._desenhar()

    def _desfazer(self):
        if self.tabuleiro().desfazer():
            self._desenhar()

    def _refazer(self):
        if self.tabuleiro().refazer():
            self._desenhar()

    # ------------------------------------------------------------------
    # Desenhar
    # ------------------------------------------------------------------

    def _ir(self, passo):
        if len(self.leituras) > 1:
            self.atual = (self.atual + passo) % len(self.leituras)
            self.selecionada = None
            self._desenhar()

    def _leitura(self) -> diag.Leitura:
        return self.leituras[self.atual]

    def _desenhar(self):
        tabuleiro = self.tabuleiro()
        self.lbl_titulo.config(
            text=f"Diagrama {self.atual + 1} de {len(self.leituras)}  —  "
                 f"{tabuleiro.resumo()}")
        self.var_fen.set(tabuleiro.fen())
        self.lbl_avisos.config(text="\n".join(tabuleiro.avisos()))
        self._desenhar_recorte()
        self._desenhar_tabuleiro(tabuleiro)
        self._atualizar_controles(tabuleiro)

    def _desenhar_recorte(self):
        self._fotos.clear()
        arr = np.asarray(self.imagem)
        x1, y1, x2, y2 = self._leitura().caixa
        recorte = arr[max(0, y1):y2, max(0, x1):x2]
        if recorte.size:
            img = Image.fromarray(recorte).convert("L").resize(
                (8 * LADO_CASA, 8 * LADO_CASA), Image.LANCZOS)
            foto = ImageTk.PhotoImage(img)
            self._fotos.append(foto)
            self.lbl_recorte.config(image=foto)

    def _desenhar_tabuleiro(self, tabuleiro):
        self.canvas.delete("all")
        for casa in tabuleiro.casas:
            x, y = casa.coluna * LADO_CASA, casa.linha * LADO_CASA
            fundo = COR_CLARA if (casa.linha + casa.coluna) % 2 == 0 else COR_ESCURA
            self.canvas.create_rectangle(x, y, x + LADO_CASA, y + LADO_CASA,
                                         fill=fundo, outline="")

            # A cor conta uma coisa só, e a mais recente ganha: uma casa
            # corrigida à mão não é mais "trocada pela legalidade".
            if casa.corrigida:
                borda = COR_CORRIGIDA
            elif casa.arbitrada:
                borda = COR_ARBITRADA
            elif casa.simbolo and casa.confianca < CONFIANCA_BAIXA:
                borda = COR_DUVIDA
            else:
                borda = None
            if borda:
                self.canvas.create_rectangle(x + 2, y + 2, x + LADO_CASA - 2,
                                             y + LADO_CASA - 2, outline=borda,
                                             width=3)
            if (casa.linha, casa.coluna) == self.selecionada:
                self.canvas.create_rectangle(x + 1, y + 1, x + LADO_CASA - 1,
                                             y + LADO_CASA - 1,
                                             outline=COR_SELECAO, width=2)
            if casa.simbolo:
                self.canvas.create_text(
                    x + LADO_CASA // 2, y + LADO_CASA // 2,
                    text=GLIFOS.get(casa.simbolo, casa.simbolo),
                    font=("Segoe UI Symbol", int(LADO_CASA * 0.62)),
                    fill="black")

        legenda = []
        if any(c.corrigida for c in tabuleiro.casas):
            legenda.append("verde: corrigida por você")
        if any(c.arbitrada for c in tabuleiro.casas):
            legenda.append("vermelho: trocada pela legalidade")
        if any(c.simbolo and not c.corrigida and c.confianca < CONFIANCA_BAIXA
               for c in tabuleiro.casas):
            legenda.append("laranja: leitura duvidosa")
        if legenda:
            self.lbl_avisos.config(
                text=self.lbl_avisos.cget("text") + "\n" + "   ".join(legenda))

    def _atualizar_controles(self, tabuleiro):
        self.var_lado.set(tabuleiro.lado)
        possiveis = tabuleiro.roques_possiveis()
        for letra, var in self.vars_roque.items():
            var.set(letra in tabuleiro.roque)
            self.checks_roque[letra].config(
                state="normal" if letra in possiveis else "disabled")

        for simbolo, botao in self.botoes_paleta.items():
            botao.config(relief="sunken" if self.pincel == simbolo else "raised")
        self.btn_borracha.config(
            relief="sunken" if self.pincel == "" else "raised")

        self.btn_desfazer.config(
            state="normal" if tabuleiro.pode_desfazer else "disabled")
        self.btn_refazer.config(
            state="normal" if tabuleiro.pode_refazer else "disabled")

    # ------------------------------------------------------------------

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
