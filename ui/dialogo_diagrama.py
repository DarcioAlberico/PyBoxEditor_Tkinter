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

## O tabuleiro é o `TabuleiroEditavel` (ED-05)

O canvas, o desenho, o clique, o arrasto e as teclas moram em
`ui/editor/tabuleiro.py` desde a ED-05, porque o editor de livros precisa do mesmo
tabuleiro sem esta janela (e sem o `cv2` que ela traz pelo `core.diagrama`). Este
diálogo o embute e mantém o que era seu: o recorte, a paleta, o lado, o roque, o
treino e o FEN. `canvas`, `figuras`, `selecionada` e `pincel` continuam acessíveis
daqui — delegam ao widget.
"""

import tkinter as tk
from tkinter import ttk
from typing import List, Optional

import numpy as np
from PIL import Image, ImageTk

from core import diagrama as diag
from core.tabuleiro_edicao import SIMBOLOS, TabuleiroEdicao
from ui import pecas
from ui.editor.tabuleiro import (  # noqa: F401 — LADO_CASA, GLIFOS e SEM_FIGURAS continuam importáveis daqui
    CONFIANCA_BAIXA, GLIFOS, LADO_CASA, PALETAS, SEM_FIGURAS, TabuleiroEditavel)

#: O lado do botão da paleta.
LADO_PALETA = 30
COR_CLARA, COR_ESCURA = PALETAS["normal"]
COR_ARBITRADA = "#E53935"       # a legalidade mexeu nesta casa
COR_DUVIDA = "#FB8C00"
COR_CORRIGIDA = "#2E7D32"       # a mão do usuário mexeu nesta casa (F8.2)
COR_SELECAO = "#1E88E5"

AJUDA = ("Clique numa casa e digite a letra (maiúscula = branca, minúscula = "
         "preta); Delete esvazia. Ou escolha uma peça na paleta e clique para "
         "pintar — clicando de novo na mesma casa ela alterna entre a peça e "
         "vazia. Arrastar move a peça. Ctrl+Z desfaz.")

class DialogoDiagrama:
    """Mostra e edita as leituras de uma página. Devolve o FEN escolhido."""

    def __init__(self, parent, imagem, leituras: List[diag.Leitura],
                 origem: str = ""):
        self.parent = parent
        self.imagem = imagem
        self.leituras = leituras
        # De onde vieram estes diagramas, para a amostra guardada saber voltar
        # à origem (F8.3). Vazio quando quem abriu não soube dizer.
        self.origem = origem
        self.atual = 0
        self.resultado: Optional[str] = None
        self._fotos = []
        # Um tabuleiro por leitura, criado na primeira visita: trocar de
        # diagrama e voltar não pode perder o que já foi corrigido.
        self.tabuleiros = {}
        self.editavel: Optional[TabuleiroEditavel] = None
        self.guardadas = {}          # diagrama -> amostras gravadas
        # As figuras da paleta (as do tabuleiro são do `TabuleiroEditavel`).
        # Ficam no diálogo, e não num cache de módulo: ver `ui/pecas.py`.
        self.figuras_paleta = {}

    # -- o que era do diálogo e passou ao tabuleiro editável (ED-05) ------------------

    @property
    def canvas(self):
        return self.editavel.canvas

    @property
    def figuras(self):
        return self.editavel.figuras if self.editavel is not None else {}

    @property
    def selecionada(self):
        return self.editavel.selecionada if self.editavel is not None else None

    @selecionada.setter
    def selecionada(self, valor):
        if self.editavel is not None:
            self.editavel.selecionada = valor

    @property
    def pincel(self):
        return self.editavel.pincel if self.editavel is not None else None

    @pincel.setter
    def pincel(self, valor):
        if self.editavel is not None:
            self.editavel.pincel = valor

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

        # Depois do Toplevel: `PhotoImage` precisa de uma janela viva.
        self.figuras_paleta = pecas.carregar(LADO_PALETA)

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
        self.editavel = TabuleiroEditavel(direita, self.tabuleiro(), ao_mudar=self._depois_do_tabuleiro)
        self.editavel.pack()

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

    def _depois_do_tabuleiro(self):
        """O tabuleiro editável mudou (clique, tecla, arrasto): o resto da janela acompanha."""
        if self._desenhando or self.editavel is None:
            return
        self._desenhar(so_o_resto=True)

    def _construir_paleta(self, corpo):
        """A paleta, o lado a jogar e o roque — tudo que não é a casa."""
        painel = ttk.Frame(corpo, padding=(10, 0))
        painel.pack(side="left", fill="y")

        paleta = ttk.LabelFrame(painel, text="peça", padding=4)
        paleta.pack(fill="x")
        self.botoes_paleta = {}
        for i, simbolo in enumerate(SIMBOLOS):
            figura = self.figuras_paleta.get(simbolo)
            if figura is not None:
                b = tk.Button(paleta, image=figura, relief="raised",
                              command=lambda s=simbolo: self._escolher(s))
            else:
                b = tk.Button(paleta, text=GLIFOS.get(simbolo, simbolo),
                              width=2, font=("Segoe UI Symbol", 14),
                              relief="raised",
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
                                command=lambda valor=letra: self._mudar_roque(valor))
            c.pack(anchor="w")
            self.vars_roque[letra] = var
            self.checks_roque[letra] = c

        # Treino (F8.3). Silêncio não é confirmação: sem marcar "conferi", o
        # que vai para a base é só o que a mão mexeu.
        treino = ttk.LabelFrame(painel, text="treino", padding=4)
        treino.pack(fill="x", pady=(8, 0))
        self.var_conferido = tk.BooleanVar(value=False)
        ttk.Checkbutton(treino, text="conferi o diagrama\ninteiro",
                        variable=self.var_conferido,
                        command=self._desenhar).pack(anchor="w")
        self.btn_amostras = ttk.Button(treino, text="Guardar amostras",
                                       command=self._guardar_amostras)
        self.btn_amostras.pack(fill="x", pady=(4, 0))
        self.lbl_amostras = ttk.Label(treino, text="", foreground="gray30",
                                      wraplength=140, justify="left")
        self.lbl_amostras.pack(anchor="w", pady=(2, 0))

    def mostrar(self) -> Optional[str]:
        self.construir()
        self.top.grab_set()
        self.top.focus_set()
        self.parent.wait_window(self.top)
        return self.resultado

    # ------------------------------------------------------------------
    # Editar
    # ------------------------------------------------------------------

    def _no_clique(self, evento):
        """O clique no tabuleiro (ver `TabuleiroEditavel._no_clique`): pinta com pincel, senão seleciona."""
        self.editavel._no_clique(evento)

    def _no_solta(self, evento):
        self.editavel._no_solta(evento)

    def _no_direito(self, evento):
        self.editavel._no_direito(evento)

    def _na_tecla(self, evento):
        """
        A letra da peça escreve na casa selecionada. Maiúscula é branca (a caixa do
        caractere, como sempre foi aqui; no `TabuleiroEditavel` focado, o `Shift`).
        `Delete` e `Backspace` esvaziam. Só age quando há casa selecionada.
        """
        if self.selecionada is None or (getattr(evento, "state", 0) or 0) & 0x4:      # Ctrl: não
            return
        tecla = getattr(evento, "char", "")
        keysym = getattr(evento, "keysym", "")
        if tecla in SIMBOLOS:
            self.tabuleiro().colocar(*self.selecionada, tecla)
        elif keysym in ("Delete", "BackSpace", "space"):
            self.tabuleiro().limpar(*self.selecionada)
        else:
            return
        self._desenhar()
        return "break"

    def _escolher(self, simbolo):
        """Escolhe (ou desescolhe) o pincel da paleta."""
        self.editavel.escolher(simbolo)

    def _mudar_lado(self):
        self.tabuleiro().definir_lado(self.var_lado.get())
        self._desenhar()

    def _mudar_roque(self, letra):
        self.tabuleiro().alternar_roque(letra)
        self._desenhar()

    def procedencia(self) -> str:
        """
        De onde esta amostra veio, com detalhe suficiente para voltar lá.

        Leva a caixa do diagrama na página, e não só o número dele: o número
        depende da ordem de leitura da página, que muda se a segmentação mudar.
        A caixa é onde o tabuleiro está.
        """
        caixa = "-".join(str(v) for v in self._leitura().caixa)
        return f"{self.origem or 'pagina'}_d{self.atual + 1}_{caixa}"

    def _guardar_amostras(self):
        """Grava as amostras deste diagrama na base de treino (F8.3)."""
        from core import treino_diagrama

        tudo = bool(self.var_conferido.get())
        try:
            caminhos = treino_diagrama.colher(
                self.imagem, self._leitura(), self.tabuleiro(),
                self.procedencia(), tudo)
        except Exception as e:                      # disco cheio, pasta sem permissão
            self.lbl_amostras.config(text=f"não deu para guardar: {e}")
            return

        self.guardadas[self.atual] = len(caminhos)
        if caminhos:
            texto = (f"{len(caminhos)} amostra(s) guardadas. Treine o modelo "
                     f"para elas valerem.")
        else:
            texto = ("nada a guardar: corrija alguma casa ou marque "
                     "\"conferi o diagrama inteiro\".")
        self.lbl_amostras.config(text=texto)
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
            self.editavel.tabuleiro = self.tabuleiro()
            self.selecionada = None
            # "Conferi" vale para o diagrama que estava na tela, e não para o
            # próximo: levá-lo junto faria o gesto explícito virar automático.
            self.var_conferido.set(False)
            guardadas = self.guardadas.get(self.atual)
            self.lbl_amostras.config(
                text=f"{guardadas} amostra(s) guardadas." if guardadas else "")
            self._desenhar()

    def _leitura(self) -> diag.Leitura:
        return self.leituras[self.atual]

    def _cabecalho(self) -> str:
        """
        A linha de cima: qual diagrama é, como está lido, e como o livro o
        chama (F95).

        **O título do livro vem antes do número da lista**, quando há. É por ele
        que alguém acha a posição — `Ex. 22-4` é o que está impresso na página
        e o que se procuraria depois; "Diagrama 4 de 6" só diz onde ele caiu
        nesta leitura.
        """
        leitura = self._leitura()
        partes = [f"Diagrama {self.atual + 1} de {len(self.leituras)}"]
        if leitura.titulo.texto:
            partes.insert(0, leitura.titulo.texto)
        partes.append(self.tabuleiro().resumo())
        if leitura.rotulos.presentes:
            partes.append(leitura.rotulos.resumo())
        return "  —  ".join(partes)

    _desenhando = False

    def _desenhar(self, so_o_resto: bool = False):
        tabuleiro = self.tabuleiro()
        self.lbl_titulo.config(text=self._cabecalho())
        self.var_fen.set(tabuleiro.fen())
        self.lbl_avisos.config(
            text="\n".join(self._avisos_da_leitura() + tabuleiro.avisos()))
        self._desenhar_recorte()
        if not so_o_resto:
            self._desenhando = True
            try:
                self.editavel.desenhar()
            finally:
                self._desenhando = False
        self._legenda_do_tabuleiro(tabuleiro)
        self._atualizar_controles(tabuleiro)

    def _avisos_da_leitura(self) -> List[str]:
        """
        O que a **página** deixou em aberto neste diagrama.

        `TabuleiroEdicao.avisos` fala do FEN — lado, roque, en passant. Falta o
        aviso de antes dele: para que lado o tabuleiro foi impresso. Sem
        coordenadas em volta não há como saber, e a leitura gira as casas
        assumindo brancas embaixo (`ler_pagina`, F95). Assumir em silêncio é o
        pior dos dois mundos: um diagrama do lado das pretas sai plausível,
        legal e espelhado, e quem confere casa a casa não desconfia de nada —
        porque *a leitura* bate com o que está na tela, e as duas estão erradas
        do mesmo jeito.

        Quem imprimiu as coordenadas não paga por isto: ali a orientação é
        leitura, e o aviso não aparece.
        """
        leitura = self._leitura()
        if leitura.rotulos.orientacao is not None:
            return []
        motivo = ("as coordenadas impressas não bastaram para decidir"
                  if leitura.rotulos.presentes
                  else "não há coordenadas impressas em volta do tabuleiro")
        return [f"Orientação não confirmada: {motivo}. A leitura assume as "
                f"brancas embaixo; se o diagrama estiver impresso do lado das "
                f"pretas, esta posição sai girada 180°."]

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

    def _legenda_do_tabuleiro(self, tabuleiro):
        legenda = []
        if not self.figuras:
            legenda.append(SEM_FIGURAS)
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

        # Só há o que guardar se a mão mexeu em alguma casa ou se o diagrama
        # inteiro foi conferido — o botão diz isso ficando cinza.
        tem_o_que_guardar = (bool(self.var_conferido.get())
                             or tabuleiro.corrigidas > 0)
        self.btn_amostras.config(
            state="normal" if tem_o_que_guardar else "disabled")

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
