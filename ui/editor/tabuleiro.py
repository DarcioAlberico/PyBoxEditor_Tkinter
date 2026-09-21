"""
`TabuleiroEditavel`: o tabuleiro que se edita com o mouse **e com o teclado** (ED-05;
SPEC_EDITOR §11.2, §13.2).

Extraído de `ui/dialogo_diagrama.py` (F8.2), que passa a usá-lo: o estado continua em
`core/tabuleiro_edicao.py: TabuleiroEdicao` (peças, lado, roque, desfazer) e aqui só se
desenha e se despacha — cliques, arrasto, e as teclas da §11.2:

- setas movem a casa selecionada, cujo anel é de **dois tons** (2 px pretos por dentro,
  1 px branco por fora — ≥ 3:1 sobre qualquer casa, nas duas paletas);
- `K Q R B N P` põem a peça branca e `Shift+letra` a preta — a cor vem de
  `event.state & 0x1`, nunca da caixa do caractere (o Caps Lock a inverteria); no
  idioma `pt` o mapa é `R D T B C P`;
- `Delete`, `BackSpace` e `0` esvaziam; `F` gira; `Tab` sai para os controles; `Enter`
  e `Esc` sobem para o diálogo.

A paleta é `#F0D9B5/#B58863` (a de sempre) ou a de alto contraste `#FFFFFF/#7A7A7A`.
As figuras vêm de `ui/pecas.py` (`pieces/`); sem elas, os glifos da fonte e um aviso
(`sem_figuras`). O `recorte` — o diagrama impresso — vai ao lado quando existe.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

from core.tabuleiro_edicao import SIMBOLOS, TabuleiroEdicao
from ui import pecas

LADO_CASA = 44
FOLGA_DA_CASA = 4
PALETAS = {"normal": ("#F0D9B5", "#B58863"), "alto_contraste": ("#FFFFFF", "#7A7A7A")}
COR_ARBITRADA = "#E53935"
COR_DUVIDA = "#FB8C00"
COR_CORRIGIDA = "#2E7D32"
CONFIANCA_BAIXA = 0.55
GLIFOS = {"K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
          "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟"}
#: A letra da peça por idioma (maiúscula), na ordem `KQRBNP`.
MAPAS = {"en": "KQRBNP", "pt": "RDTBCP", "es": "RDTACP", "fr": "RDTFCP", "de": "KDTLSB", "it": "RDTACP"}
SEM_FIGURAS = ("as figuras não foram encontradas em pieces/ — o tabuleiro está "
               "usando os símbolos da fonte")


class TabuleiroEditavel(tk.Frame):
    """Ver o cabeçalho. `ao_mudar()` é chamado a cada mudança de posição ou seleção."""

    def __init__(self, master: tk.Misc, tabuleiro: TabuleiroEdicao | None = None, recorte: Any = None,
                 idioma: str = "en", alto_contraste: bool = False, lado_casa: int = LADO_CASA,
                 ao_mudar: Callable[[], Any] | None = None, **kw: Any):
        super().__init__(master, **kw)
        self.tabuleiro = tabuleiro if tabuleiro is not None else TabuleiroEdicao()
        self.idioma = idioma if idioma in MAPAS else "en"
        self.alto_contraste = alto_contraste
        self.lado_casa = lado_casa
        self.ao_mudar = ao_mudar
        self.orientacao = "branca"
        self.selecionada: tuple[int, int] | None = None
        self.pincel: str | None = None
        self._arrasto: tuple[int, int] | None = None
        self._fotos: list[Any] = []
        self.figuras: dict[str, Any] = pecas.carregar(lado_casa - FOLGA_DA_CASA)
        self.lbl_recorte: tk.Label | None = None
        if recorte is not None:
            self.lbl_recorte = tk.Label(self, background="white")
            self.lbl_recorte.pack(side="left", padx=(0, 8))
            self.definir_recorte(recorte)
        self.canvas = tk.Canvas(self, width=8 * lado_casa, height=8 * lado_casa, highlightthickness=2,
                                highlightbackground="#d0d0d0", highlightcolor="#1E88E5", takefocus=1)
        self.canvas.pack(side="left")
        self.canvas.bind("<ButtonPress-1>", self._no_clique)
        self.canvas.bind("<ButtonRelease-1>", self._no_solta)
        self.canvas.bind("<Button-3>", self._no_direito)
        self.canvas.bind("<Key>", self._na_tecla)
        self.canvas.bind("<FocusIn>", lambda e: self._selecionar_primeira())
        self.desenhar()

    # -- desenho ----------------------------------------------------------------

    def definir_recorte(self, imagem: Any) -> None:
        """A imagem impressa (PIL) ao lado, na altura do tabuleiro."""
        if self.lbl_recorte is None:
            return
        try:
            from PIL import Image, ImageTk

            lado = 8 * self.lado_casa
            img = imagem.convert("L").resize((lado, lado), Image.LANCZOS)
            foto = ImageTk.PhotoImage(img)
            self._fotos = [foto]
            self.lbl_recorte.config(image=foto)
        except Exception:      # noqa: BLE001 — um recorte ilegível fica sem imagem
            self.lbl_recorte.config(image="", text="(recorte ilegível)")

    def _xy(self, linha: int, coluna: int) -> tuple[int, int]:
        """O canto da casa na tela, respeitando a orientação (girado: a fila 1 fica em cima)."""
        if self.orientacao == "preta":
            linha, coluna = 7 - linha, 7 - coluna
        return coluna * self.lado_casa, linha * self.lado_casa

    def _casa_do_ponto(self, x: int, y: int) -> tuple[int, int] | None:
        linha, coluna = int(y) // self.lado_casa, int(x) // self.lado_casa
        if not (0 <= linha < 8 and 0 <= coluna < 8):
            return None
        if self.orientacao == "preta":
            linha, coluna = 7 - linha, 7 - coluna
        return linha, coluna

    def desenhar(self) -> None:
        clara, escura = PALETAS["alto_contraste" if self.alto_contraste else "normal"]
        c = self.canvas
        lado = self.lado_casa
        c.delete("all")
        for casa in self.tabuleiro.casas:
            x, y = self._xy(casa.linha, casa.coluna)
            fundo = clara if (casa.linha + casa.coluna) % 2 == 0 else escura
            c.create_rectangle(x, y, x + lado, y + lado, fill=fundo, outline="", tags=("casa",))
            if casa.corrigida:
                borda = COR_CORRIGIDA
            elif casa.arbitrada:
                borda = COR_ARBITRADA
            elif casa.simbolo and casa.confianca < CONFIANCA_BAIXA:
                borda = COR_DUVIDA
            else:
                borda = None
            if borda:
                c.create_rectangle(x + 2, y + 2, x + lado - 2, y + lado - 2, outline=borda, width=3, tags=("borda",))
            if casa.simbolo:
                figura = self.figuras.get(casa.simbolo)
                if figura is not None:
                    c.create_image(x + lado // 2, y + lado // 2, image=figura, tags=("peca",))
                else:
                    c.create_text(x + lado // 2, y + lado // 2, text=GLIFOS.get(casa.simbolo, casa.simbolo),
                                  font=("Segoe UI Symbol", int(lado * 0.62)), fill="black", tags=("peca",))
        if self.selecionada is not None:
            x, y = self._xy(*self.selecionada)
            # o anel de dois tons: o branco por fora e o preto por dentro contrastam com qualquer casa
            c.create_rectangle(x + 0.5, y + 0.5, x + lado - 0.5, y + lado - 0.5, outline="#ffffff", width=1,
                               tags=("anel", "anel-fora"))
            c.create_rectangle(x + 2, y + 2, x + lado - 2, y + lado - 2, outline="#000000", width=2,
                               tags=("anel", "anel-dentro"))
        if self.ao_mudar is not None:
            self.ao_mudar()

    @property
    def sem_figuras(self) -> str:
        return "" if self.figuras else SEM_FIGURAS

    # -- mouse ------------------------------------------------------------------

    def _no_clique(self, evento: Any) -> None:
        alvo = self._casa_do_ponto(evento.x, evento.y)
        if alvo is None:
            return
        self.canvas.focus_set()
        self._arrasto = alvo
        if self.pincel:
            atual = self.tabuleiro.casa(*alvo)
            novo = None if atual and atual.simbolo == self.pincel else self.pincel
            self.tabuleiro.colocar(*alvo, novo)
        elif self.pincel == "":
            self.tabuleiro.limpar(*alvo)
        self.selecionada = alvo
        self.desenhar()

    def _no_solta(self, evento: Any) -> None:
        origem, self._arrasto = self._arrasto, None
        destino = self._casa_do_ponto(evento.x, evento.y)
        if origem is None or destino is None or origem == destino:
            return
        if self.pincel is None and self.tabuleiro.mover(origem, destino):
            self.selecionada = destino
            self.desenhar()

    def _no_direito(self, evento: Any) -> None:
        alvo = self._casa_do_ponto(evento.x, evento.y)
        if alvo and self.tabuleiro.limpar(*alvo):
            self.selecionada = alvo
            self.desenhar()

    # -- teclado ----------------------------------------------------------------

    def _selecionar_primeira(self) -> None:
        if self.selecionada is None:
            self.selecionada = (7, 4)          # e1: onde o rei branco costuma estar
            self.desenhar()

    def _na_tecla(self, evento: Any) -> str | None:
        keysym = getattr(evento, "keysym", "")
        estado = getattr(evento, "state", 0) or 0
        if estado & 0x4:                                   # Ctrl: desfazer, etc. — não é peça
            return None
        setas = {"Up": (-1, 0), "Down": (1, 0), "Left": (0, -1), "Right": (0, 1)}
        if keysym in setas:
            self.mover_selecao(*setas[keysym])
            return "break"
        if keysym in ("Delete", "BackSpace", "0", "KP_0", "space"):
            self.limpar_casa()
            return "break"
        if keysym in ("Return", "KP_Enter", "Escape", "Tab", "ISO_Left_Tab"):
            return None                                    # sobem para o diálogo / a travessia do Tk
        letra = (getattr(evento, "char", "") or keysym[:1]).upper()
        if keysym.lower() == "f" and not (estado & 0x1):
            self.girar()
            return "break"
        if letra in MAPAS[self.idioma]:
            self.por_peca(letra, preta=bool(estado & 0x1))
            return "break"
        return None

    def mover_selecao(self, dlinha: int, dcoluna: int) -> tuple[int, int]:
        """Move a casa selecionada; a orientação girada inverte as setas para a tela continuar certa."""
        if self.selecionada is None:
            self.selecionada = (7, 4)
        if self.orientacao == "preta":
            dlinha, dcoluna = -dlinha, -dcoluna
        linha, coluna = self.selecionada
        self.selecionada = (min(7, max(0, linha + dlinha)), min(7, max(0, coluna + dcoluna)))
        self.desenhar()
        return self.selecionada

    def por_peca(self, letra: str, preta: bool = False) -> bool:
        """A peça da `letra` (no mapa do idioma) na casa selecionada; `preta` decide a cor."""
        mapa = MAPAS[self.idioma]
        letra = letra.upper()
        if letra not in mapa or self.selecionada is None:
            return False
        simbolo = "KQRBNP"[mapa.index(letra)]
        if preta:
            simbolo = simbolo.lower()
        if simbolo not in SIMBOLOS:
            return False
        mudou = self.tabuleiro.colocar(*self.selecionada, simbolo)
        self.desenhar()
        return mudou

    def limpar_casa(self) -> bool:
        if self.selecionada is None:
            return False
        mudou = self.tabuleiro.limpar(*self.selecionada)
        self.desenhar()
        return mudou

    def girar(self) -> str:
        self.orientacao = "preta" if self.orientacao == "branca" else "branca"
        self.desenhar()
        return self.orientacao

    def escolher(self, simbolo: str | None) -> None:
        """O pincel da paleta: uma peça, `""` (borracha) ou `None` (nenhum); escolher de novo desliga."""
        self.pincel = None if self.pincel == simbolo else simbolo
        self.desenhar()

    # -- posição ------------------------------------------------------------------

    def carregar_fen(self, fen: str, lado: str = "") -> None:
        """Troca a posição inteira (Colar FEN, Posição inicial, Limpar)."""
        self.tabuleiro = TabuleiroEdicao.de_fen(fen, lado)
        self.selecionada = None
        self.desenhar()

    def limpar_tudo(self) -> None:
        for casa in self.tabuleiro.casas:
            self.tabuleiro.colocar(casa.linha, casa.coluna, None)
        self.desenhar()

    def espelhar(self) -> None:
        """As brancas viram pretas e vice-versa, espelhadas na fila (o exercício "de quem é a vez?")."""
        casas = {(c.linha, c.coluna): c.simbolo for c in self.tabuleiro.casas}
        for (linha, coluna), simbolo in casas.items():
            novo = casas.get((7 - linha, coluna))
            self.tabuleiro.colocar(linha, coluna, novo.swapcase() if novo else None)
        self.desenhar()

    def fen(self) -> str:
        return self.tabuleiro.fen()

    def foco(self) -> None:
        self.canvas.focus_set()


__all__ = ["TabuleiroEditavel", "LADO_CASA", "PALETAS", "MAPAS", "GLIFOS", "SEM_FIGURAS", "CONFIANCA_BAIXA"]
