"""
O diagrama na tela e a sua caixa de propriedades (ED-05; SPEC_EDITOR §11.1, §11.2,
DEC-06, DEC-07).

## `ObjetoDeDiagrama`: um `Canvas`, não um PNG

O bloco `Diagrama` é desenhado num `tk.Canvas` com as figuras de `pieces/`
(`ui/pecas.py`): casas, peças, coordenadas, o quadradinho de quem joga, as marcas e
as setas (ED-05b), o número e a legenda embaixo, e o aviso quando há. A spec pedia o
PNG de `render_diagrama.desenhar` no zoom da tela; o canvas foi a escolha porque
`render_diagrama` traz `fitz` e o capítulo com diagramas abre no processo do editor
sem carregar o OCR (AC-ED02-7 confere `fitz`), e porque um canvas escala com o zoom
sem redesenhar fonte nenhuma. O PNG continua sendo o do arquivo (EPUB, DOCX): o que se
vê aqui é o mesmo tabuleiro, com as mesmas peças do editor de posição ao lado.

## `DialogoDeDiagrama`: três grupos

**Posição** (o `TabuleiroEditavel` com teclado, o FEN — onde o foco nasce —, o lado a
jogar brancas/pretas/desconhecido, a orientação, as coordenadas, e Posição inicial,
Limpar, Espelhar, Colar FEN, Copiar FEN); **Aparência** (modo `png`/`fonte`, fonte,
moldura, cantos, corpo, indicador de lado); **Identificação** (número, legenda, alt,
estado e aviso). O recorte impresso fica ao lado do tabuleiro quando existe. A
legalidade é aviso com ícone e texto, nunca recusa: uma posição de estudo pode ser
impossível de propósito.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from core.editor import modelo, xadrez
from core.editor.modelo import Diagrama, Trecho
from core.tabuleiro_edicao import TabuleiroEdicao
from ui import pecas
from ui.editor.dialogos import _Dialogo
from ui.editor.objetos import FUNDO_SELECIONADO, ObjetoBase
from ui.editor.tabuleiro import GLIFOS, PALETAS, TabuleiroEditavel

#: O lado da casa na tela, em px, no zoom 1.
CASA_PX = 26
COR_DO_FOCO = "#0645ad"
COR_DA_MARCA = "#c0392b"
COR_DA_SETA = "#1f5fbf"
FONTES_DE_DIAGRAMA_DE_RESERVA = ("SkakNew-Diagram", "ChessMerida-Diagram")
_figuras_cache: dict[tuple[int, int], dict[str, Any]] = {}


def figuras_para(master: tk.Misc, lado: int) -> dict[str, Any]:
    """As doze figuras no tamanho, uma vez por interpretador e tamanho (500 diagramas não carregam 6.000 PNG)."""
    chave = (id(master.tk), lado)
    imagens = _figuras_cache.get(chave)
    if imagens:
        try:
            next(iter(imagens.values())).width()
            return imagens
        except (tk.TclError, RuntimeError):
            pass
    imagens = pecas.carregar(lado)
    _figuras_cache[chave] = imagens
    return imagens


def fontes_de_diagrama() -> list[str]:
    """Os nomes das fontes de diagrama com mapa — sem importar `render_diagrama` (fitz)."""
    from core.editor import fontes

    nomes = list(fontes._mapas())
    return nomes or list(FONTES_DE_DIAGRAMA_DE_RESERVA)


def desenhar_no_canvas(canvas: tk.Canvas, d: Diagrama, casa: int, figuras: dict[str, Any],
                       alto_contraste: bool = False, x0: int = 0, y0: int = 0) -> None:
    """O tabuleiro do diagrama no canvas, a partir de `(x0, y0)`: casas, peças, coordenadas, marcas, setas."""
    clara, escura = PALETAS["alto_contraste" if alto_contraste else "normal"]
    filas = d.posicao.split("/")
    girado = d.orientacao == "preta"
    casas: dict[tuple[int, int], str] = {}
    for i, fila in enumerate(filas[:8]):
        coluna = 0
        for ch in fila:
            if ch.isdigit():
                coluna += int(ch)
                continue
            if coluna < 8:
                casas[(i, coluna)] = ch
            coluna += 1
    for linha in range(8):
        for coluna in range(8):
            l_tela, c_tela = (7 - linha, 7 - coluna) if girado else (linha, coluna)
            x, y = x0 + c_tela * casa, y0 + l_tela * casa
            fundo = clara if (linha + coluna) % 2 == 0 else escura
            canvas.create_rectangle(x, y, x + casa, y + casa, fill=fundo, outline="", tags=("casa",))
            simbolo = casas.get((linha, coluna))
            if simbolo:
                figura = figuras.get(simbolo)
                if figura is not None:
                    canvas.create_image(x + casa // 2, y + casa // 2, image=figura, tags=("peca",))
                else:
                    canvas.create_text(x + casa // 2, y + casa // 2, text=GLIFOS.get(simbolo, simbolo),
                                       font=("Segoe UI Symbol", max(8, int(casa * 0.62))), fill="black",
                                       tags=("peca",))
    lado = 8 * casa
    canvas.create_rectangle(x0, y0, x0 + lado, y0 + lado, outline="#000000", width=1 if d.moldura == "sem" else 2,
                            tags=("moldura",))
    if d.moldura == "dupla":
        canvas.create_rectangle(x0 - 3, y0 - 3, x0 + lado + 3, y0 + lado + 3, outline="#000000", width=1,
                                tags=("moldura",))
    for nome in d.marcas:
        xy = _centro(nome, casa, girado, x0, y0)
        if xy is not None:
            raio = casa * 0.38
            canvas.create_oval(xy[0] - raio, xy[1] - raio, xy[0] + raio, xy[1] + raio, outline=COR_DA_MARCA,
                               width=max(2, casa // 10), tags=("marca",))
    for de, para in d.setas:
        a, b = _centro(de, casa, girado, x0, y0), _centro(para, casa, girado, x0, y0)
        if a is not None and b is not None and a != b:
            canvas.create_line(a[0], a[1], b[0], b[1], fill=COR_DA_SETA, width=max(2, casa // 9),
                               arrow="last", arrowshape=(casa * 0.45, casa * 0.55, casa * 0.2), tags=("seta",))
    if d.coordenadas:
        colunas = list("abcdefgh")
        numeros = [str(n) for n in range(8, 0, -1)]
        if girado:
            colunas.reverse()
            numeros.reverse()
        corpo = max(7, int(casa * 0.36))
        for k in range(8):
            canvas.create_text(x0 - corpo * 0.7, y0 + k * casa + casa / 2, text=numeros[k],
                               font=("Segoe UI", corpo), fill="#333333", tags=("coordenada",))
            canvas.create_text(x0 + k * casa + casa / 2, y0 + lado + corpo * 0.8, text=colunas[k],
                               font=("Segoe UI", corpo), fill="#333333", tags=("coordenada",))


def _centro(nome: str, casa: int, girado: bool, x0: int, y0: int) -> tuple[float, float] | None:
    if len(nome) != 2 or nome[0] not in "abcdefgh" or nome[1] not in "12345678":
        return None
    coluna, fila = "abcdefgh".index(nome[0]), int(nome[1]) - 1
    if girado:
        coluna, fila = 7 - coluna, 7 - fila
    return x0 + (coluna + 0.5) * casa, y0 + (7 - fila + 0.5) * casa


class ObjetoDeDiagrama(ObjetoBase):
    """O diagrama no modo texto (ver o cabeçalho); `Enter` → editor de posição, `Alt+Enter` → propriedades."""

    def _montar(self) -> tk.Widget:
        d: Diagrama = self.objeto
        zoom = getattr(self.contexto, "zoom", 1.0) or 1.0
        casa = max(14, int(round(CASA_PX * zoom)))
        self.casa = casa
        self.figuras = figuras_para(self, casa - 2)
        margem = int(casa * 0.6) if d.coordenadas else 6
        calha = int(casa * 0.6) if (d.lado_indicador == "marca" and d.lado in ("w", "b")) else 0
        largura = margem + 8 * casa + 6 + calha
        altura = 8 * casa + (int(casa * 0.6) if d.coordenadas else 6) + 6
        canvas = tk.Canvas(self, width=largura, height=altura, background="#ffffff", highlightthickness=2,
                           highlightbackground="#ffffff", highlightcolor=COR_DO_FOCO, takefocus=1, cursor="arrow")
        x0, y0 = margem, 6
        desenhar_no_canvas(canvas, d, casa, self.figuras, x0=x0, y0=y0)
        if calha:
            quadro = casa * 0.4
            x = x0 + 8 * casa + 6 + (calha - quadro) / 2
            y = (y0 + 8 * casa - quadro) if d.lado == "w" else y0
            canvas.create_rectangle(x, y, x + quadro, y + quadro, fill="#ffffff" if d.lado == "w" else "#000000",
                                    outline="#000000", width=max(1, casa // 14), tags=("indicador",))
        canvas.pack()
        self.canvas = canvas
        legenda = self._legenda()
        if legenda:
            tk.Label(self, text=legenda, foreground="#444444", background="#ffffff",
                     wraplength=max(140, largura), justify="center").pack()
        if d.lado_indicador == "legenda" and d.lado:
            tk.Label(self, text=xadrez.legenda_de_lado(d, getattr(self.contexto, "idioma", "pt")),
                     foreground="#444444", background="#ffffff", font=("Segoe UI", 9, "italic")).pack()
        if d.aviso or d.estado == "revisar" or not d.lado:
            aviso = d.aviso or ("posição a revisar" if d.estado == "revisar" else "")
            if not d.lado:
                aviso = (aviso + "; " if aviso else "") + "lado a jogar desconhecido"
            tk.Label(self, text="⚠ " + aviso, foreground="#8a5a00", background="#ffffff",
                     wraplength=max(140, largura), justify="center").pack()
        return canvas

    def _legenda(self) -> str:
        d: Diagrama = self.objeto
        texto = "".join(t.texto for t in d.legenda)
        prefixo = f"Diagrama {d.numero}" if d.numero is not None else ""
        if prefixo and texto:
            return f"{prefixo}. {texto}"
        return prefixo or texto

    def dica(self) -> str:
        d: Diagrama = self.objeto
        lado = {"w": "brancas jogam", "b": "pretas jogam"}.get(d.lado, "lado a jogar desconhecido")
        return f"{d.fen}\n{lado} · {d.modo} · {d.fonte}\nEnter: editar posição · Alt+Enter: propriedades"

    def selecionar(self, sim: bool) -> None:
        try:
            self.canvas.configure(highlightbackground=FUNDO_SELECIONADO if sim else "#ffffff",
                                  background=FUNDO_SELECIONADO if sim else "#ffffff")
            for filho in self.winfo_children():
                if isinstance(filho, tk.Label):
                    filho.configure(background=FUNDO_SELECIONADO if sim else "#ffffff")
        except tk.TclError:
            pass


# ----------------------------------------------------------------------
# A caixa de propriedades / o editor de posição
# ----------------------------------------------------------------------

class DialogoDeDiagrama(_Dialogo):
    """Ver o cabeçalho. `mostrar()` devolve o `Diagrama` novo, ou `None`."""

    def __init__(self, master: tk.Misc, diagrama: Diagrama | None = None, recorte: Any = None,
                 idioma: str = "en", alto_contraste: bool = False, titulo: str = "Diagrama",
                 fontes: Callable[[], list[str]] | None = None):
        super().__init__(master, titulo)
        self.original = diagrama
        self.diagrama = modelo.de_dict(modelo.para_dict(diagrama)) if diagrama is not None else Diagrama(
            fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        self.recorte = recorte
        self.idioma = idioma if idioma in ("en", "pt", "es", "fr", "de", "it") else "en"
        self.alto_contraste = alto_contraste
        self._fontes = fontes or fontes_de_diagrama
        self.tabuleiro: TabuleiroEditavel | None = None
        self._sincronizando = False

    # -- construção -------------------------------------------------------------

    def _construir(self) -> tk.Toplevel:
        top = self._abrir((False, False))
        d = self.diagrama
        corpo = ttk.Frame(top, padding=10)
        corpo.pack(fill="both", expand=True)

        # Posição
        posicao = ttk.LabelFrame(corpo, text="Posição", padding=6)
        posicao.grid(row=0, column=0, rowspan=2, sticky="nsew")
        tab = TabuleiroEdicao.de_fen(d.fen, d.lado)
        self.tabuleiro = TabuleiroEditavel(posicao, tab, recorte=self.recorte, idioma=self.idioma,
                                           alto_contraste=self.alto_contraste, ao_mudar=self._do_tabuleiro)
        self.tabuleiro.orientacao = d.orientacao
        self.tabuleiro.grid(row=0, column=0, columnspan=3, sticky="w")
        self.tabuleiro.desenhar()
        ttk.Label(posicao, text="FEN:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.var_fen = tk.StringVar(master=top, value=d.fen)
        self.entrada_fen = ttk.Entry(posicao, textvariable=self.var_fen, width=60)
        self.entrada_fen.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(6, 0))
        self.entrada_fen.bind("<FocusOut>", lambda e: self._do_fen())
        self.entrada_fen.bind("<Return>", lambda e: (self._do_fen(), "break")[1])
        botoes = ttk.Frame(posicao)
        botoes.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        for texto, acao in (("Posição inicial", self.posicao_inicial), ("Limpar", self.limpar),
                            ("Espelhar", self.espelhar), ("Colar FEN", self.colar_fen),
                            ("Copiar FEN", self.copiar_fen)):
            ttk.Button(botoes, text=texto, command=acao).pack(side="left", padx=(0, 4))
        controles = ttk.Frame(posicao)
        controles.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(controles, text="Lado a jogar:").grid(row=0, column=0, sticky="w")
        self.var_lado = tk.StringVar(master=top, value=d.lado)
        for k, (valor, rotulo) in enumerate((("w", "brancas"), ("b", "pretas"), ("", "desconhecido"))):
            ttk.Radiobutton(controles, text=rotulo, value=valor, variable=self.var_lado,
                            command=self._do_lado).grid(row=0, column=1 + k, sticky="w", padx=(4, 0))
        ttk.Label(controles, text="Orientação:").grid(row=1, column=0, sticky="w")
        self.var_orientacao = tk.StringVar(master=top, value=d.orientacao)
        for k, (valor, rotulo) in enumerate((("branca", "brancas embaixo"), ("preta", "pretas embaixo"))):
            ttk.Radiobutton(controles, text=rotulo, value=valor, variable=self.var_orientacao,
                            command=self._do_orientacao).grid(row=1, column=1 + k, sticky="w", padx=(4, 0))
        self.var_coordenadas = tk.BooleanVar(master=top, value=d.coordenadas)
        ttk.Checkbutton(controles, text="coordenadas", variable=self.var_coordenadas).grid(
            row=1, column=3, sticky="w", padx=(4, 0))
        self.lbl_legalidade = ttk.Label(posicao, text="", foreground="#8a5a00", wraplength=420, justify="left")
        self.lbl_legalidade.grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))

        # Aparência
        aparencia = ttk.LabelFrame(corpo, text="Aparência", padding=6)
        aparencia.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ttk.Label(aparencia, text="Modo:").grid(row=0, column=0, sticky="w")
        self.var_modo = tk.StringVar(master=top, value=d.modo)
        for k, (valor, rotulo) in enumerate((("png", "imagem"), ("fonte", "fonte"))):
            ttk.Radiobutton(aparencia, text=rotulo, value=valor, variable=self.var_modo).grid(
                row=0, column=1 + k, sticky="w")
        ttk.Label(aparencia, text="Fonte:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        fontes = self._fontes()
        self.var_fonte = tk.StringVar(master=top, value=d.fonte if d.fonte in fontes or not fontes else fontes[0])
        self.combo_fonte = ttk.Combobox(aparencia, values=fontes, textvariable=self.var_fonte, width=22,
                                        state="readonly" if fontes else "normal")
        self.combo_fonte.grid(row=1, column=1, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Label(aparencia, text="Moldura:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.var_moldura = tk.StringVar(master=top, value=d.moldura)
        for k, (valor, rotulo) in enumerate((("sem", "sem"), ("simples", "simples"), ("dupla", "dupla"))):
            ttk.Radiobutton(aparencia, text=rotulo, value=valor, variable=self.var_moldura).grid(
                row=2 + (k // 3), column=1 + k % 3, sticky="w", pady=(4, 0))
        self.var_cantos = tk.BooleanVar(master=top, value=d.cantos == "arredondado")
        ttk.Checkbutton(aparencia, text="cantos arredondados", variable=self.var_cantos).grid(
            row=3, column=1, columnspan=2, sticky="w")
        ttk.Label(aparencia, text="Corpo (pt por casa):").grid(row=4, column=0, sticky="w", pady=(4, 0))
        self.var_corpo = tk.StringVar(master=top, value=f"{d.corpo_pt:g}")
        ttk.Spinbox(aparencia, from_=6, to=40, increment=0.5, width=6, textvariable=self.var_corpo).grid(
            row=4, column=1, sticky="w", pady=(4, 0))
        ttk.Label(aparencia, text="Indicador de lado:").grid(row=5, column=0, sticky="w", pady=(4, 0))
        self.var_indicador = tk.StringVar(master=top, value=d.lado_indicador)
        for k, (valor, rotulo) in enumerate((("", "nenhum"), ("marca", "marca"), ("legenda", "legenda"))):
            ttk.Radiobutton(aparencia, text=rotulo, value=valor, variable=self.var_indicador).grid(
                row=5, column=1 + k, sticky="w", pady=(4, 0))

        # Identificação
        ident = ttk.LabelFrame(corpo, text="Identificação", padding=6)
        ident.grid(row=1, column=1, sticky="nsew", padx=(10, 0), pady=(8, 0))
        ttk.Label(ident, text="Número:").grid(row=0, column=0, sticky="w")
        self.var_numero = tk.StringVar(master=top, value="" if d.numero is None else str(d.numero))
        ttk.Entry(ident, textvariable=self.var_numero, width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(ident, text="Legenda:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.var_legenda = tk.StringVar(master=top, value="".join(t.texto for t in d.legenda))
        ttk.Entry(ident, textvariable=self.var_legenda, width=30).grid(row=1, column=1, sticky="ew", pady=(4, 0))
        ttk.Label(ident, text="Alt:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.var_alt = tk.StringVar(master=top, value=d.alt)
        ttk.Entry(ident, textvariable=self.var_alt, width=30).grid(row=2, column=1, sticky="ew", pady=(4, 0))
        ttk.Label(ident, text="(vazio: gerado da posição)", foreground="#666666").grid(row=3, column=1, sticky="w")
        estado = f"estado: {d.estado}" + (f" — {d.aviso}" if d.aviso else "")
        ttk.Label(ident, text=estado, foreground="#8a5a00" if d.estado != "ok" else "#666666",
                  wraplength=280, justify="left").grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))

        self._botoes(corpo, "OK").grid(row=2, column=0, columnspan=2, sticky="e", pady=(10, 0))
        self._atualizar_legalidade()
        return top

    def _foco_inicial(self) -> None:
        if self.top is not None:
            self.entrada_fen.focus_set()
            self.entrada_fen.selection_range(0, "end")

    # -- sincronia entre tabuleiro, FEN e lado --------------------------------------

    def _do_tabuleiro(self) -> None:
        """O tabuleiro mudou (tecla, clique): o FEN acompanha, com o lado escolhido."""
        if self._sincronizando or self.tabuleiro is None or not hasattr(self, "var_fen"):
            return
        self._sincronizando = True
        try:
            self.var_fen.set(self._fen_atual())
            self._atualizar_legalidade()
        finally:
            self._sincronizando = False

    def _fen_atual(self) -> str:
        assert self.tabuleiro is not None
        board = self.tabuleiro.tabuleiro.tabuleiro()
        lado = self.var_lado.get() if hasattr(self, "var_lado") else self.diagrama.lado
        import chess

        board.turn = chess.BLACK if lado == "b" else chess.WHITE
        return board.fen()

    def _do_fen(self) -> None:
        """O FEN digitado vai para o tabuleiro (inválido: aviso, e o tabuleiro fica)."""
        if self._sincronizando or self.tabuleiro is None:
            return
        fen = self.var_fen.get().strip()
        if not modelo.fen_valido(fen):
            self.lbl_legalidade.config(text="⚠ FEN inválido — o tabuleiro não mudou")
            return
        self._sincronizando = True
        try:
            self.tabuleiro.carregar_fen(fen, self.var_lado.get())
            self.tabuleiro.orientacao = self.var_orientacao.get()
            self.tabuleiro.desenhar()
            self.var_fen.set(self._fen_atual())       # o lado do FEN não vira lado conhecido sozinho (DEC-06)
            self._atualizar_legalidade()
        finally:
            self._sincronizando = False

    def _do_lado(self) -> None:
        if self.tabuleiro is not None:
            self.tabuleiro.tabuleiro.definir_lado(self.var_lado.get() or "w")
        self._do_tabuleiro()

    def _do_orientacao(self) -> None:
        if self.tabuleiro is not None:
            self.tabuleiro.orientacao = self.var_orientacao.get()
            self.tabuleiro.desenhar()

    def _atualizar_legalidade(self) -> None:
        if self.tabuleiro is None or not hasattr(self, "lbl_legalidade"):
            return
        problemas = self.tabuleiro.tabuleiro.problemas()
        partes = []
        if self.tabuleiro.sem_figuras:
            partes.append(self.tabuleiro.sem_figuras)
        if problemas:
            partes.append("⚠ posição impossível: " + "; ".join(problemas))
        if self.var_lado.get() == "":
            partes.append("⚠ lado a jogar desconhecido: sem indicador nem legenda de lado (DEC-06)")
        self.lbl_legalidade.config(text="\n".join(partes))

    # -- os botões da posição ----------------------------------------------------------

    def posicao_inicial(self) -> None:
        self.var_fen.set("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        self._do_fen()

    def limpar(self) -> None:
        self.var_fen.set("8/8/8/8/8/8/8/8 w - - 0 1")
        self._do_fen()

    def espelhar(self) -> None:
        if self.tabuleiro is not None:
            self.tabuleiro.espelhar()
            self._do_tabuleiro()

    def colar_fen(self) -> None:
        assert self.top is not None
        try:
            texto = self.top.clipboard_get().strip()
        except tk.TclError:
            return
        if modelo.fen_valido(texto):
            self.var_fen.set(texto)
            self._do_fen()
        else:
            self.lbl_legalidade.config(text="⚠ a área de transferência não tem um FEN")

    def copiar_fen(self) -> None:
        assert self.top is not None
        self.top.clipboard_clear()
        self.top.clipboard_append(self.var_fen.get())

    # -- resultado ---------------------------------------------------------------------

    def _ler(self) -> Diagrama:
        self._do_fen()
        d = self.diagrama
        fen = self._fen_atual()
        if not modelo.fen_valido(fen):
            raise ValueError(f"FEN inválido: {fen!r}")
        numero_txt = self.var_numero.get().strip()
        numero = int(numero_txt) if numero_txt.isdigit() else None
        legenda_txt = self.var_legenda.get()
        legenda = [Trecho(texto=legenda_txt)] if legenda_txt else []
        if legenda_txt == "".join(t.texto for t in d.legenda):
            legenda = list(d.legenda)
        try:
            corpo = float(self.var_corpo.get().replace(",", "."))
        except ValueError:
            corpo = d.corpo_pt
        novo = Diagrama(
            id=d.id, id_persistente=d.id_persistente, classe=d.classe, extras=dict(d.extras), origem=d.origem,
            fen=fen, lado=self.var_lado.get(), orientacao=self.var_orientacao.get(),
            coordenadas=bool(self.var_coordenadas.get()), lado_indicador=self.var_indicador.get(),
            marcas=list(d.marcas), setas=list(d.setas), fonte=self.var_fonte.get() or d.fonte,
            moldura=self.var_moldura.get(), cantos="arredondado" if self.var_cantos.get() else "reto",
            corpo_pt=max(1.0, corpo), modo=self.var_modo.get(), numero=numero, legenda=legenda,
            alt=self.var_alt.get().strip(), recorte=d.recorte, estado="ok", aviso="")
        if novo.lado == "" and novo.lado_indicador:
            novo.lado_indicador = ""          # sem lado, sem indicador (DEC-06)
        return novo


__all__ = ["ObjetoDeDiagrama", "DialogoDeDiagrama", "desenhar_no_canvas", "figuras_para", "fontes_de_diagrama",
           "CASA_PX", "COR_DA_MARCA", "COR_DA_SETA"]
