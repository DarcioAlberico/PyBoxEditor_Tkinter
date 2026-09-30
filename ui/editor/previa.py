"""
A prévia do modo código (ED-08, refeita na ED-14; docs/ANALISE_JANELA_EDITOR.md §4.1): o
XHTML da aba **desenhado de verdade** — a CSS do capítulo, as fontes e as imagens do livro —
pelo `fitz.Story` (`core/editor/previa_story.py`), em fatias da largura do painel empilhadas
num `Canvas` que rola sem emenda, como a prévia do Sigil. Antes era o próprio `TextoRico`
só de leitura, que não aplicava a CSS e mostrava as ilhas do modo texto.

`atualizar(texto)` espera `atraso_ms` (300 ms; o teste usa 0) e redesenha; um XHTML
mal-formado, ou um que o MuPDF recuse, **mantém a prévia anterior** e escreve o erro no
rodapé (AC-ED08-7). `ir_ao_bloco(linha)` rola até o bloco cuja linha da fonte é a última
≤ `linha` e o contorna — é o que o cursor do código chama —, e um clique na prévia devolve
a linha do bloco clicado por `ao_clicar(linha)`, para o código ir até lá.

Só as fatias visíveis (e uma de cada lado) viram imagem; mudar a largura do painel
redesenha na largura nova.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from core.editor import xhtml
from core.editor import previa_story as ps

ATRASO_PADRAO_MS = 300
#: Cor do contorno do bloco sob o cursor do código.
COR_DO_BLOCO = "#f0a000"


class Previa(ttk.Frame):
    def __init__(self, master: tk.Misc, atraso_ms: int = ATRASO_PADRAO_MS,
                 ao_clicar: Callable[[int], Any] | None = None, estilo_de_tela: Any = None,
                 folhas: Any = (), recursos: Callable[[str], bytes | None] | None = None,
                 livro: Any = None, **kw: Any):
        super().__init__(master, **kw)
        self.atraso_ms = int(atraso_ms)
        self.ao_clicar = ao_clicar
        self.folhas = list(folhas or ())
        self.zoom = float(getattr(estilo_de_tela, "zoom", 1.0) or 1.0)
        self.montador = ps.Montador(recursos=recursos, livro=livro)
        self.desenho: ps.Desenho | None = None
        self.erro: Exception | None = None
        self.linha_marcada: int | None = None
        self._doc: Any = None
        self._imagens: dict[int, tk.PhotoImage] = {}
        self._texto: str | None = None          # o último texto bem desenhado (para a largura nova)
        self._pendente: str | None = None
        self._agendado: str | None = None
        self._largura_agendada: str | None = None
        self._arquivo = ""
        self.rotulo = ttk.Label(self, text="Prévia", anchor="w", padding=(6, 2))
        self.rotulo.pack(side="top", fill="x")
        self.rodape = ttk.Label(self, text="", anchor="w", foreground="#b00020", padding=(6, 2))
        self.rodape.pack(side="bottom", fill="x")
        corpo = ttk.Frame(self)
        corpo.pack(fill="both", expand=True)
        self.rolagem = ttk.Scrollbar(corpo, orient="vertical")
        self.rolagem.pack(side="right", fill="y")
        self.canvas = tk.Canvas(corpo, background="#ffffff", highlightthickness=0, takefocus=1,
                                yscrollcommand=self._rolou, cursor="arrow")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.rolagem.configure(command=self._rolar)
        self.canvas.bind("<Button-1>", self._clique, add="+")
        self.canvas.bind("<Configure>", self._mudou_de_tamanho, add="+")
        self.canvas.bind("<MouseWheel>", self._roda, add="+")
        self.canvas.bind("<Button-4>", lambda e: self._rolar("scroll", -3, "units"), add="+")
        self.canvas.bind("<Button-5>", lambda e: self._rolar("scroll", 3, "units"), add="+")
        self.canvas.bind("<Prior>", lambda e: self._rolar("scroll", -1, "pages"), add="+")
        self.canvas.bind("<Next>", lambda e: self._rolar("scroll", 1, "pages"), add="+")
        self.canvas.configure(yscrollincrement=20)

    # -- escala --------------------------------------------------------------------

    def px_por_pt(self) -> float:
        try:
            base = float(self.winfo_fpixels("1i")) / 72.0
        except tk.TclError:
            base = 96.0 / 72.0
        return base * self.zoom

    def _largura_pt(self) -> float:
        largura = self.canvas.winfo_width()
        if largura <= 1:
            largura = int(self.canvas.cget("width") or 400)
        return max(120.0, largura / self.px_por_pt())

    @property
    def pronta(self) -> bool:
        return self.desenho is not None

    # -- atualizar ----------------------------------------------------------------

    def atualizar(self, texto: str, arquivo: str = "") -> None:
        """Agenda o redesenho (`atraso_ms`); chamadas seguidas ficam com a última."""
        self._pendente = texto
        self._arquivo = arquivo or self._arquivo
        self._cancelar("_agendado")
        if self.atraso_ms <= 0:
            self.mostrar_agora()
            return
        try:
            self._agendado = self.after(self.atraso_ms, self.mostrar_agora)
        except tk.TclError:
            self.mostrar_agora()

    def _cancelar(self, nome: str) -> None:
        agendado = getattr(self, nome)
        if agendado is not None:
            try:
                self.after_cancel(agendado)
            except tk.TclError:
                pass
            setattr(self, nome, None)

    def mostrar_agora(self) -> bool:
        """Desenha o pendente; `False` (e a prévia anterior fica) quando o XHTML não serve."""
        self._agendado = None
        texto = self._pendente
        if texto is None:
            return False
        self._pendente = None
        erro = xhtml.bem_formado(texto)
        if erro is not None:
            self.erro = erro
            self.rodape.configure(text=f"XHTML mal-formado (linha {erro.linha}, col {erro.coluna}): {erro.mensagem} "
                                       f"— a prévia mostra a última versão válida")
            return False
        try:
            desenho = ps.desenhar(texto, self._arquivo, self.folhas, largura_pt=self._largura_pt(),
                                  montador=self.montador)
        except Exception as falha:      # noqa: BLE001 — o MuPDF recusou: fica a anterior
            self.erro = falha
            self.rodape.configure(text=f"A prévia não desenhou: {falha} — a prévia mostra a última versão válida")
            return False
        self.erro = None
        self.rodape.configure(text="; ".join(desenho.avisos[:2]))
        self._texto = texto
        self._trocar_desenho(desenho)
        return True

    def _trocar_desenho(self, desenho: ps.Desenho) -> None:
        import fitz

        topo = self.canvas.canvasy(0)
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:      # noqa: BLE001
                pass
        self.desenho = desenho
        self._doc = fitz.open("pdf", desenho.pdf)
        self._imagens.clear()
        self.canvas.delete("all")
        escala = self.px_por_pt()
        altura = desenho.paginas * desenho.altura_pt * escala
        self.canvas.configure(scrollregion=(0, 0, desenho.largura_pt * escala, max(1.0, altura)))
        # A rolagem fica onde estava (quem digita não quer a prévia pulando ao topo).
        if altura > 0:
            self.canvas.yview_moveto(max(0.0, topo) / altura)
        self._desenhar_visiveis()
        if self.linha_marcada is not None:
            self._contornar(self.linha_marcada, rolar=False)

    # -- as fatias -------------------------------------------------------------------

    def _desenhar_visiveis(self) -> None:
        if self.desenho is None or self._doc is None:
            return
        escala = self.px_por_pt()
        fatia_px = self.desenho.altura_pt * escala
        topo = self.canvas.canvasy(0)
        altura = max(1, self.canvas.winfo_height())
        primeira = max(0, int(topo // fatia_px) - 1)
        ultima = min(self.desenho.paginas - 1, int((topo + altura) // fatia_px) + 1)
        for n in range(primeira, ultima + 1):
            if n in self._imagens:
                continue
            import fitz

            pix = self._doc[n].get_pixmap(matrix=fitz.Matrix(escala, escala), alpha=False)
            imagem = tk.PhotoImage(master=self.canvas, data=pix.tobytes("ppm"), format="PPM")
            self._imagens[n] = imagem
            self.canvas.create_image(0, n * fatia_px, image=imagem, anchor="nw", tags=("fatia",))
        self.canvas.tag_raise("bloco")

    def _rolou(self, primeiro: str, ultimo: str) -> None:
        self.rolagem.set(primeiro, ultimo)
        self._desenhar_visiveis()

    def _rolar(self, *args: Any) -> None:
        self.canvas.yview(*args)
        self._desenhar_visiveis()

    def _roda(self, evento: Any) -> str:
        passos = -int(evento.delta / 120) if evento.delta else 0
        self._rolar("scroll", passos * 3, "units")
        return "break"

    def _mudou_de_tamanho(self, evento: Any) -> None:
        if self.desenho is None or self._texto is None:
            return
        if abs(self._largura_pt() - self.desenho.largura_pt) < 2.0:
            self._desenhar_visiveis()
            return
        self._cancelar("_largura_agendada")

        def refazer() -> None:
            self._largura_agendada = None
            if self._pendente is None and self._texto is not None:
                self._pendente = self._texto
                self.mostrar_agora()

        try:
            self._largura_agendada = self.after(150, refazer)
        except tk.TclError:
            pass

    # -- ir e voltar ------------------------------------------------------------------

    def ir_ao_bloco(self, linha: int) -> int | None:
        """Rola até o bloco da linha da fonte (o último que começa em ≤ `linha`) e o contorna."""
        self.linha_marcada = int(linha)
        return self._contornar(int(linha), rolar=True)

    def _contornar(self, linha: int, rolar: bool) -> int | None:
        self.canvas.delete("bloco")
        if self.desenho is None:
            return None
        achado = self.desenho.posicao_da_linha(linha)
        if achado is None:
            return None
        linha_do_bloco, pagina, (x0, y0, x1, y1) = achado
        escala = self.px_por_pt()
        base = pagina * self.desenho.altura_pt * escala
        topo, fundo = base + y0 * escala, base + y1 * escala
        self.canvas.create_rectangle(x0 * escala - 3, topo - 2, x1 * escala + 3, fundo + 2,
                                     outline=COR_DO_BLOCO, width=2, tags=("bloco",))
        if rolar:
            altura_total = self.desenho.paginas * self.desenho.altura_pt * escala
            visivel_topo = self.canvas.canvasy(0)
            visivel_fundo = visivel_topo + self.canvas.winfo_height()
            if altura_total > 0 and (topo < visivel_topo or fundo > visivel_fundo):
                self.canvas.yview_moveto(max(0.0, topo - self.canvas.winfo_height() / 4) / altura_total)
                self._desenhar_visiveis()
        return linha_do_bloco

    def linha_em(self, x: float, y: float) -> int | None:
        """A linha da fonte do bloco no ponto `(x, y)` do canvas (coordenadas do canvas)."""
        if self.desenho is None:
            return None
        escala = self.px_por_pt()
        fatia_px = self.desenho.altura_pt * escala
        pagina = int(y // fatia_px)
        return self.desenho.linha_em(pagina, x / escala, (y - pagina * fatia_px) / escala)

    def _clique(self, evento: Any) -> None:
        self.canvas.focus_set()
        linha = self.linha_em(self.canvas.canvasx(evento.x), self.canvas.canvasy(evento.y))
        if linha is not None and self.ao_clicar is not None:
            self.ao_clicar(linha)

    def limpar(self) -> None:
        self._pendente = None
        self._texto = None
        self.desenho = None
        self._imagens.clear()
        self.canvas.delete("all")

    def destroy(self) -> None:
        self._cancelar("_agendado")
        self._cancelar("_largura_agendada")
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:      # noqa: BLE001
                pass
            self._doc = None
        super().destroy()


__all__ = ["Previa", "ATRASO_PADRAO_MS"]
