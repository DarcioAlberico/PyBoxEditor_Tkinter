"""
Arquivo → Abrir PDF… (ED-17; docs/ANALISE_JANELA_EDITOR.md §4.4): a caixa que escolhe as
páginas e o jeito de ler, e a janelinha de progresso da leitura.

`DialogoAbrirPdf` mostra as miniaturas das páginas (o `fitz` desenha a ~12 dpi só as que
aparecem, na hora em que aparecem), e a seleção anda nos dois sentidos: clicar numa
miniatura (Shift+clique marca a faixa desde a última) muda o campo "Páginas", e digitar
"30-45, 60" no campo marca as miniaturas. Como em toda caixa do editor (`dialogos._Dialogo`),
ela se constrói sem `mostrar()`, para o teste preencher e chamar `confirmar()`.

`ProgressoDePdf` é não modal: a janela do editor continua usável enquanto o outro
processo lê; "Cancelar" mata o processo.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any, Callable

from core.editor import abrir_pdf as ap
from ui.editor.dialogos import _Dialogo

LARGURA_DA_MINIATURA = 84
ALTURA_DA_MINIATURA = 118
FOLGA = 10
COR_MARCADA = "#1a5fb4"


class DialogoAbrirPdf(_Dialogo):
    """O resultado é um `abrir_pdf.Pedido`, ou `None`."""

    def __init__(self, master: tk.Misc, pdf: str, preferencias: dict[str, Any] | None = None):
        super().__init__(master, "Abrir PDF no editor")
        self.pdf = os.path.abspath(pdf)
        self.prefs = dict(preferencias or {})
        info = ap.informacoes(self.pdf)
        self.total = int(info["paginas"])
        self.com_texto = (int(info["com_texto"]), int(info["amostradas"]))
        self.marcadas: set[int] = set()
        self._ultima: int | None = None
        self._imagens: dict[int, tk.PhotoImage] = {}
        self._doc: Any = None
        self._sincronizando = False
        self.canvas: tk.Canvas | None = None
        self.var_paginas: tk.StringVar | None = None
        self.var_leitura: tk.StringVar | None = None
        self.var_idioma: tk.StringVar | None = None
        self.var_dividir: tk.StringVar | None = None
        self.var_reparar: tk.BooleanVar | None = None
        self.var_saida: tk.StringVar | None = None
        self.var_saida_tocada = False
        self.aviso: ttk.Label | None = None

    # -- construir -------------------------------------------------------------------

    def _construir(self) -> tk.Toplevel:
        top = self._abrir((True, True))
        top.geometry("660x560")
        top.minsize(560, 480)
        corpo = ttk.Frame(top, padding=10)
        corpo.grid(row=0, column=0, sticky="nsew")
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        corpo.columnconfigure(1, weight=1)

        nome = os.path.basename(self.pdf)
        texto, amostra = self.com_texto
        tipo = ("tem texto (nascido digital ou com camada de OCR)" if texto * 2 >= amostra
                else "é digitalização (imagem): vai pelo OCR")
        ttk.Label(corpo, text=f"{nome} — {self.total} página(s); o PDF {tipo}.",
                  wraplength=620, justify="left").grid(row=0, column=0, columnspan=3, sticky="w")

        moldura = ttk.Frame(corpo, borderwidth=1, relief="sunken")
        moldura.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(8, 6))
        corpo.rowconfigure(1, weight=1)
        self.canvas = tk.Canvas(moldura, background="#e8e8e8", highlightthickness=0, takefocus=1, height=250)
        rolagem = ttk.Scrollbar(moldura, orient="vertical", command=self._rolar)
        self.canvas.configure(yscrollcommand=lambda a, b: (rolagem.set(a, b), self._desenhar_visiveis()))
        self.canvas.pack(side="left", fill="both", expand=True)
        rolagem.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", lambda e: self._dispor(), add="+")
        self.canvas.bind("<Button-1>", self._clique, add="+")
        self.canvas.bind("<Shift-Button-1>", lambda e: self._clique(e, faixa=True), add="+")
        self.canvas.bind("<MouseWheel>", self._roda, add="+")

        linha = 2
        ttk.Label(corpo, text="Páginas:").grid(row=linha, column=0, sticky="w")
        self.var_paginas = tk.StringVar(top, value="")
        entrada = ttk.Entry(corpo, textvariable=self.var_paginas)
        entrada.grid(row=linha, column=1, sticky="ew", padx=(6, 6))
        self.var_paginas.trace_add("write", lambda *a: self._digitou())
        botoes = ttk.Frame(corpo)
        botoes.grid(row=linha, column=2, sticky="e")
        ttk.Button(botoes, text="Todas", command=lambda: self.marcar(range(1, self.total + 1))).pack(side="left")
        ttk.Button(botoes, text="Nenhuma", command=lambda: self.marcar(())).pack(side="left", padx=(4, 0))

        linha += 1
        ttk.Label(corpo, text="Leitura:").grid(row=linha, column=0, sticky="w", pady=(6, 0))
        rotulos = [r for r, _v in ap.LEITURAS]
        inicial = next((r for r, v in ap.LEITURAS if v == self.prefs.get("camada")), rotulos[0])
        self.var_leitura = tk.StringVar(top, value=inicial)
        ttk.Combobox(corpo, textvariable=self.var_leitura, values=rotulos, state="readonly").grid(
            row=linha, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=(6, 0))

        linha += 1
        opcoes = ttk.Frame(corpo)
        opcoes.grid(row=linha, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(opcoes, text="Idioma do OCR:").pack(side="left")
        self.var_idioma = tk.StringVar(top, value=str(self.prefs.get("idioma") or "en"))
        ttk.Combobox(opcoes, textvariable=self.var_idioma, values=ap.IDIOMAS, width=5).pack(side="left", padx=(6, 14))
        ttk.Label(opcoes, text="Um capítulo por:").pack(side="left")
        self.var_dividir = tk.StringVar(top, value=str(self.prefs.get("dividir") or "pagina"))
        ttk.Radiobutton(opcoes, text="página", value="pagina", variable=self.var_dividir).pack(side="left", padx=(6, 0))
        ttk.Radiobutton(opcoes, text="título", value="titulo", variable=self.var_dividir).pack(side="left", padx=(4, 14))
        self.var_reparar = tk.BooleanVar(top, value=bool(self.prefs.get("reparar", False)))
        ttk.Checkbutton(opcoes, text="Reparo de colagem (mais lento)", variable=self.var_reparar).pack(side="left")

        linha += 1
        ttk.Label(corpo, text="Gravar em:").grid(row=linha, column=0, sticky="w", pady=(6, 0))
        self.var_saida = tk.StringVar(top, value="")
        saida = ttk.Entry(corpo, textvariable=self.var_saida)
        saida.grid(row=linha, column=1, sticky="ew", padx=(6, 6), pady=(6, 0))
        saida.bind("<Key>", lambda e: setattr(self, "var_saida_tocada", True), add="+")
        ttk.Button(corpo, text="…", width=3, command=self._escolher_saida).grid(row=linha, column=2, sticky="e",
                                                                              pady=(6, 0))

        linha += 1
        self.aviso = ttk.Label(corpo, text="", foreground="#b00020", wraplength=620, justify="left")
        self.aviso.grid(row=linha, column=0, columnspan=3, sticky="w", pady=(6, 0))
        linha += 1
        self._botoes(corpo, "Ler páginas").grid(row=linha, column=0, columnspan=3, sticky="e", pady=(8, 0))
        top.bind("<Return>", lambda e: self.confirmar() if e.widget is not entrada else None)
        self.var_paginas.set(str(self.prefs.get("paginas") or ""))
        self._atualizar_saida()
        return top

    def _foco_inicial(self) -> None:
        if self.canvas is not None:
            self.canvas.focus_set()

    # -- miniaturas ------------------------------------------------------------------

    def _colunas(self) -> int:
        largura = self.canvas.winfo_width() if self.canvas is not None else 0
        if largura <= 1:
            largura = 620
        return max(1, (largura - FOLGA) // (LARGURA_DA_MINIATURA + FOLGA))

    def _posicao(self, pagina: int) -> tuple[int, int]:
        k = pagina - 1
        colunas = self._colunas()
        x = FOLGA + (k % colunas) * (LARGURA_DA_MINIATURA + FOLGA)
        y = FOLGA + (k // colunas) * (ALTURA_DA_MINIATURA + FOLGA + 14)
        return x, y

    def _dispor(self) -> None:
        if self.canvas is None:
            return
        self.canvas.delete("all")
        self._imagens.clear()
        _x, y = self._posicao(self.total)
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), y + ALTURA_DA_MINIATURA + 30))
        for pagina in range(1, self.total + 1):
            x, y = self._posicao(pagina)
            self.canvas.create_rectangle(x - 3, y - 3, x + LARGURA_DA_MINIATURA + 3, y + ALTURA_DA_MINIATURA + 3,
                                         outline="", width=3, tags=(f"moldura{pagina}", "moldura"))
            self.canvas.create_rectangle(x, y, x + LARGURA_DA_MINIATURA, y + ALTURA_DA_MINIATURA, fill="#ffffff",
                                         outline="#aaaaaa", tags=(f"folha{pagina}",))
            self.canvas.create_text(x + LARGURA_DA_MINIATURA / 2, y + ALTURA_DA_MINIATURA + 8, text=str(pagina),
                                    tags=(f"numero{pagina}",))
        self._pintar_marcas()
        self._desenhar_visiveis()

    def _desenhar_visiveis(self) -> None:
        if self.canvas is None or not self.total:
            return
        topo = self.canvas.canvasy(0)
        fundo = topo + max(1, self.canvas.winfo_height())
        colunas = self._colunas()
        passo = ALTURA_DA_MINIATURA + FOLGA + 14
        primeira = max(1, int(topo // passo) * colunas + 1)
        ultima = min(self.total, (int(fundo // passo) + 1) * colunas)
        for pagina in range(primeira, ultima + 1):
            if pagina not in self._imagens:
                self._miniatura(pagina)

    def _miniatura(self, pagina: int) -> None:
        import fitz

        try:
            if self._doc is None:
                self._doc = fitz.open(self.pdf)
            pag = self._doc[pagina - 1]
            escala = min(LARGURA_DA_MINIATURA / pag.rect.width, ALTURA_DA_MINIATURA / pag.rect.height)
            pix = pag.get_pixmap(matrix=fitz.Matrix(escala, escala), alpha=False)
            imagem = tk.PhotoImage(master=self.canvas, data=pix.tobytes("ppm"), format="PPM")
        except Exception:      # noqa: BLE001 — uma página que não desenha fica em branco
            return
        self._imagens[pagina] = imagem
        x, y = self._posicao(pagina)
        self.canvas.create_image(x, y, image=imagem, anchor="nw", tags=(f"imagem{pagina}",))

    def _pintar_marcas(self) -> None:
        if self.canvas is None:
            return
        self.canvas.itemconfigure("moldura", outline="")
        for pagina in self.marcadas:
            self.canvas.itemconfigure(f"moldura{pagina}", outline=COR_MARCADA)

    def pagina_em(self, x: float, y: float) -> int | None:
        """A página da miniatura no ponto `(x, y)` do canvas (coordenadas do canvas)."""
        colunas = self._colunas()
        coluna = int((x - FOLGA / 2) // (LARGURA_DA_MINIATURA + FOLGA))
        fila = int((y - FOLGA / 2) // (ALTURA_DA_MINIATURA + FOLGA + 14))
        if coluna < 0 or coluna >= colunas or fila < 0:
            return None
        pagina = fila * colunas + coluna + 1
        return pagina if 1 <= pagina <= self.total else None

    def _clique(self, evento: Any, faixa: bool = False) -> str:
        assert self.canvas is not None
        self.canvas.focus_set()
        pagina = self.pagina_em(self.canvas.canvasx(evento.x), self.canvas.canvasy(evento.y))
        if pagina is not None:
            self.alternar(pagina, faixa=faixa)
        return "break"

    def _rolar(self, *args: Any) -> None:
        if self.canvas is not None:
            self.canvas.yview(*args)
            self._desenhar_visiveis()

    def _roda(self, evento: Any) -> str:
        self._rolar("scroll", -int(evento.delta / 120) * 2 if evento.delta else 0, "units")
        return "break"

    # -- seleção nos dois sentidos -----------------------------------------------------

    def alternar(self, pagina: int, faixa: bool = False) -> None:
        """O clique numa miniatura; com `faixa` (Shift), marca da última clicada até esta."""
        if faixa and self._ultima is not None:
            a, b = sorted((self._ultima, pagina))
            self.marcar(self.marcadas | set(range(a, b + 1)))
        else:
            self.marcar(self.marcadas ^ {pagina})
        self._ultima = pagina

    def marcar(self, paginas: Any) -> None:
        self.marcadas = {int(p) for p in paginas if 1 <= int(p) <= self.total}
        self._pintar_marcas()
        if self.var_paginas is not None:
            self._sincronizando = True
            try:
                self.var_paginas.set(ap.texto_da_faixa(self.marcadas))
            finally:
                self._sincronizando = False
        self._atualizar_saida()

    def _digitou(self) -> None:
        if self._sincronizando or self.var_paginas is None:
            return
        try:
            paginas = ap.faixa_de(self.var_paginas.get(), self.total) if self.var_paginas.get().strip() else []
        except ValueError as erro:
            self._avisar(str(erro))
            return
        self._avisar("")
        self.marcadas = set(paginas)
        self._pintar_marcas()
        self._atualizar_saida()

    def _avisar(self, texto: str) -> None:
        if self.aviso is not None:
            self.aviso.configure(text=texto)

    def _atualizar_saida(self) -> None:
        if self.var_saida is not None and not self.var_saida_tocada:
            self.var_saida.set(ap.saida_padrao(self.pdf, sorted(self.marcadas)) if self.marcadas else "")

    def _escolher_saida(self) -> None:
        atual = self.var_saida.get() if self.var_saida is not None else ""
        caminho = filedialog.asksaveasfilename(
            title="Gravar o documento editorial em", defaultextension=".json",
            filetypes=[("Documento editorial", "*.json")], initialfile=os.path.basename(atual) or None,
            initialdir=os.path.dirname(atual) or None, parent=self.top)
        if caminho and self.var_saida is not None:
            self.var_saida.set(caminho)
            self.var_saida_tocada = True

    # -- resultado -------------------------------------------------------------------

    def confirmar(self) -> Any:
        try:
            pedido = self._ler()
        except ValueError as erro:
            self._avisar(str(erro))
            return None
        self.resultado = pedido
        self._fechar()
        return pedido

    def _ler(self) -> ap.Pedido:
        assert self.var_paginas is not None and self.var_leitura is not None
        texto = self.var_paginas.get().strip()
        if not texto:
            raise ValueError("escolha as páginas: clique nas miniaturas ou digite (ex.: 30-45, 60)")
        paginas = ap.faixa_de(texto, self.total)
        camada = dict(ap.LEITURAS).get(self.var_leitura.get(), "auto")
        idioma = (self.var_idioma.get() if self.var_idioma is not None else "en").strip() or "en"
        saida = (self.var_saida.get() if self.var_saida is not None else "").strip()
        return ap.Pedido(pdf=self.pdf, paginas=paginas, idioma=idioma, camada=camada,
                         reparar=bool(self.var_reparar.get()) if self.var_reparar is not None else False,
                         dividir=self.var_dividir.get() if self.var_dividir is not None else "pagina",
                         saida=saida)

    def _fechar(self) -> None:
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:      # noqa: BLE001
                pass
            self._doc = None
        super()._fechar()


class ProgressoDePdf:
    """A janelinha não modal da leitura: a barra, a frase e "Cancelar"."""

    def __init__(self, master: tk.Misc, titulo: str, ao_cancelar: Callable[[], Any]):
        self.top = tk.Toplevel(master)
        self.top.title(titulo)
        self.top.resizable(False, False)
        try:
            self.top.transient(master.winfo_toplevel())
        except tk.TclError:
            pass
        self.top.protocol("WM_DELETE_WINDOW", ao_cancelar)
        corpo = ttk.Frame(self.top, padding=12)
        corpo.pack(fill="both", expand=True)
        self.rotulo = ttk.Label(corpo, text="Preparando…", width=56)
        self.rotulo.pack(anchor="w")
        self.barra = ttk.Progressbar(corpo, mode="indeterminate", length=380)
        self.barra.pack(fill="x", pady=(8, 8))
        self.barra.start(80)
        self.botao = ttk.Button(corpo, text="Cancelar", command=ao_cancelar)
        self.botao.pack(anchor="e")

    def texto(self, texto: str) -> None:
        self.rotulo.configure(text=texto)

    def progresso(self, atual: int, total: int) -> None:
        if total > 0:
            if str(self.barra.cget("mode")) != "determinate":
                self.barra.stop()
                self.barra.configure(mode="determinate", maximum=total)
            self.barra.configure(value=atual)
            self.rotulo.configure(text=f"Lendo página {min(atual + 1, total)} de {total}…" if atual < total
                                  else "Montando o livro…")

    def fechar(self) -> None:
        try:
            self.barra.stop()
            self.top.destroy()
        except tk.TclError:
            pass


__all__ = ["DialogoAbrirPdf", "ProgressoDePdf"]
