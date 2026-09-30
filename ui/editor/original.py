"""
A página original do PDF ao lado do texto (ED-18; docs/ANALISE_JANELA_EDITOR.md §4.4) — o
modo de conferência do ABBYY FineReader dentro do editor.

`PainelOriginal` desenha a página do PDF na largura do painel e contorna a caixa do bloco
sob o cursor (laranja) e as dos blocos suspeitos da mesma página (vermelho); um clique na
página leva o editor ao bloco daquele ponto. `Original` é o controlador: `F9` liga e desliga
o painel na aba (texto **ou** código — ele sobrevive à troca de modo), `F4`/`Shift+F4` andam
pelas suspeitas do livro, e "Reler a página do PDF…" lê de novo a página do bloco, pelo
mesmo processo do "Abrir PDF" (ED-17), e troca os blocos dela no livro.

A conta da caixa (pixels da leitura → pontos → tela) e a navegação moram em
`core/editor/original.py`, sem Tk.
"""

from __future__ import annotations

import os
import tempfile
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from core.editor import abrir_pdf as ap
from core.editor import original as co

COR_DO_BLOCO = "#f0a000"
COR_DA_SUSPEITA = "#d01c1c"
ATRASO_MS = 120


class PainelOriginal(ttk.Frame):
    """A página `pagina` (0-based) do `pdf`, na largura do painel, com as caixas por cima."""

    def __init__(self, master: tk.Misc, pdf: str, dpis: dict[int, int] | None = None,
                 ao_clicar: Callable[[int, float, float], Any] | None = None, **kw: Any):
        super().__init__(master, **kw)
        self.pdf = pdf
        self.dpis = dict(dpis or {})
        self.ao_clicar = ao_clicar
        self.pagina: int | None = None
        self.caixa: tuple | None = None
        self.suspeitas: list[tuple] = []
        self.escala = 1.0
        self._doc: Any = None
        self._imagem: tk.PhotoImage | None = None
        self._desenhada: tuple[int, int] | None = None       # (página, largura) da imagem atual
        self.rotulo = ttk.Label(self, text=f"Original — {os.path.basename(pdf)}", anchor="w", padding=(6, 2))
        self.rotulo.pack(side="top", fill="x")
        self.rodape = ttk.Label(self, text="", anchor="w", padding=(6, 2), foreground="#555555")
        self.rodape.pack(side="bottom", fill="x")
        corpo = ttk.Frame(self)
        corpo.pack(fill="both", expand=True)
        self.rolagem = ttk.Scrollbar(corpo, orient="vertical")
        self.rolagem.pack(side="right", fill="y")
        self.canvas = tk.Canvas(corpo, background="#808080", highlightthickness=0, takefocus=1,
                                yscrollcommand=self.rolagem.set, yscrollincrement=20)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.rolagem.configure(command=self.canvas.yview)
        # O painel ganha o tamanho final depois do primeiro desenho: a caixa volta para a vista.
        self.canvas.bind("<Configure>", lambda e: self._redesenhar(rolar=True), add="+")
        self.canvas.bind("<Button-1>", self._clique, add="+")
        self.canvas.bind("<MouseWheel>", lambda e: (self.canvas.yview_scroll(-int(e.delta / 120) * 3, "units"),
                                                    "break")[1], add="+")

    # -- mostrar --------------------------------------------------------------------

    def dpi(self, pagina: int | None = None) -> int:
        return int(self.dpis.get(self.pagina if pagina is None else pagina) or co.DPI_PADRAO)

    def mostrar(self, pagina: int | None, caixa: tuple | None = None, suspeitas: list[tuple] | None = None,
                texto: str = "") -> None:
        """A página (ou a mensagem, sem página), com a caixa do bloco e as suspeitas dela."""
        self.pagina, self.caixa, self.suspeitas = pagina, caixa, list(suspeitas or [])
        self.rodape.configure(text=texto)
        self._redesenhar(rolar=True)

    def _largura(self) -> int:
        largura = self.canvas.winfo_width()
        return largura if largura > 1 else int(self.canvas.cget("width") or 360)

    def _redesenhar(self, rolar: bool) -> None:
        if self.pagina is None:
            self.canvas.delete("all")
            self._desenhada = None
            self.canvas.create_text(12, 12, anchor="nw", width=max(120, self._largura() - 24), fill="#ffffff",
                                    text="O bloco sob o cursor não veio do PDF.", tags=("aviso",))
            return
        largura = self._largura()
        if self._desenhada != (self.pagina, largura):
            if not self._desenhar_pagina(largura):
                return
        self.canvas.delete("caixa")
        topo = None
        for caixa in self.suspeitas:
            self._contorno(caixa, COR_DA_SUSPEITA, (4, 3))
        if self.caixa:
            topo = self._contorno(self.caixa, COR_DO_BLOCO, None, largura_da_linha=3)
        if rolar and topo is not None:
            y0, y1 = topo
            altura_total = float(self.canvas.bbox("pagina")[3]) if self.canvas.bbox("pagina") else 1.0
            visivel_topo = self.canvas.canvasy(0)
            visivel_fundo = visivel_topo + self.canvas.winfo_height()
            if y0 < visivel_topo or y1 > visivel_fundo:
                self.canvas.yview_moveto(max(0.0, y0 - self.canvas.winfo_height() / 4) / max(1.0, altura_total))

    def _desenhar_pagina(self, largura: int) -> bool:
        import fitz

        try:
            if self._doc is None:
                self._doc = fitz.open(self.pdf)
            pag = self._doc[self.pagina]
        except Exception as erro:      # noqa: BLE001 — PDF sumiu, página fora
            self.canvas.delete("all")
            self.canvas.create_text(12, 12, anchor="nw", fill="#ffffff", text=f"Página indisponível: {erro}")
            return False
        self.escala = largura / pag.rect.width
        pix = pag.get_pixmap(matrix=fitz.Matrix(self.escala, self.escala), alpha=False)
        self._imagem = tk.PhotoImage(master=self.canvas, data=pix.tobytes("ppm"), format="PPM")
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._imagem, anchor="nw", tags=("pagina",))
        self.canvas.configure(scrollregion=(0, 0, pix.width, pix.height))
        self.rotulo.configure(text=f"Original — {os.path.basename(self.pdf)}, página {self.pagina + 1} "
                                   f"de {len(self._doc)}")
        self._desenhada = (self.pagina, largura)
        return True

    def _contorno(self, caixa: tuple, cor: str, traco: tuple | None, largura_da_linha: int = 2) -> tuple[float, float]:
        x0, y0, x1, y1 = (v * self.escala for v in co.caixa_em_pontos(caixa, self.dpi()))
        opcoes: dict[str, Any] = {"outline": cor, "width": largura_da_linha, "tags": ("caixa",)}
        if traco:
            opcoes["dash"] = traco
        else:
            # A caixa do leitor costuma ir de margem a margem: o contorno some nas bordas do painel,
            # e é a trama que mostra a faixa do bloco.
            opcoes.update(fill=cor, stipple="gray12")
        self.canvas.create_rectangle(x0 - 2, y0 - 2, x1 + 2, y1 + 2, **opcoes)
        return y0, y1

    def ponto_em_pontos(self, x: float, y: float) -> tuple[float, float]:
        """Um ponto do canvas (coordenadas do canvas) em pontos do PDF."""
        return x / self.escala, y / self.escala

    def _clique(self, evento: Any) -> None:
        self.canvas.focus_set()
        if self.pagina is None or self.ao_clicar is None:
            return
        x, y = self.ponto_em_pontos(self.canvas.canvasx(evento.x), self.canvas.canvasy(evento.y))
        self.ao_clicar(self.pagina, x, y)

    def destroy(self) -> None:
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:      # noqa: BLE001
                pass
            self._doc = None
        super().destroy()


class Original:
    """Os comandos da ED-18 na janela."""

    def __init__(self, janela: Any):
        self.j = janela
        self._agendado: str | None = None
        #: O painel está ligado na janela: toda aba de capítulo que fica ativa o ganha.
        self.ligado = False
        self.comandos = {"painel_original": self.alternar, "proxima_suspeita": lambda: self.suspeita(1),
                         "suspeita_anterior": lambda: self.suspeita(-1), "reler_do_pdf": self.reler}

    # -- o painel ---------------------------------------------------------------------

    def _pdf(self) -> str:
        projeto = self.j._exigir_projeto()
        pdf = co.pdf_do_livro(projeto.livro, getattr(projeto, "documento_editorial", None))
        if not pdf:
            raise ValueError("este livro não veio de um PDF (Arquivo → Abrir PDF… lê as páginas de um)")
        if not os.path.isfile(pdf):
            raise ValueError(f"o PDF de onde o livro veio não está mais lá: {pdf}")
        return pdf

    def alternar(self, ligar: bool | None = None, aba: Any = None) -> Any:
        """`F9`: a página original ao lado do editor da aba (liga/desliga)."""
        j = self.j
        aba = aba or j.aba_ativa()
        if aba is None or aba.tipo != "capitulo":
            raise ValueError("a página original é de um capítulo: abra um")
        atual = aba.dados.get("original")
        if ligar is None:
            ligar = atual is None
        if not ligar:
            self.ligado = False
            for outra in j.abas.abas:
                j.operacoes.tirar_do_lado(outra, "original")
            j.status("Página original fechada.")
            j.atualizar()
            return None
        if atual is not None:
            self.seguir(aba)
            return atual
        pdf = self._pdf()
        projeto = j._exigir_projeto()
        dpis = co.dpis_do_documento(getattr(projeto, "documento_editorial", None))
        painel = j.operacoes.por_ao_lado(aba, "original", lambda divisao: PainelOriginal(
            divisao, pdf, dpis, ao_clicar=lambda pagina, x, y: self._clicou(aba, pagina, x, y)))
        self.ligado = True
        self._ligar_cursor(aba)
        self.seguir(aba)
        j.status("Página original aberta (F9 fecha; F4 vai à próxima suspeita).")
        j.atualizar()
        return painel

    def _ligar_cursor(self, aba: Any) -> None:
        widget = aba.widget
        if widget is not None and not getattr(widget, "_segue_original", False):
            widget.texto.bind("<<CursorMoveu>>", lambda e: self._agendar(aba), add="+")
            widget._segue_original = True

    def reabrir(self, aba: Any) -> None:
        """Depois da troca de modo, ou ao ficar ativa: a aba de capítulo ganha o painel, se ele está ligado."""
        if self.ligado and aba is not None and aba.tipo == "capitulo" and aba.widget is not None \
                and aba.dados.get("original") is None:
            try:
                self.alternar(True, aba)
            except ValueError as erro:
                self.ligado = False
                self.j.status(str(erro))

    def _agendar(self, aba: Any) -> None:
        if self._agendado is not None:
            try:
                self.j.after_cancel(self._agendado)
            except tk.TclError:
                pass
        self._agendado = self.j.after(ATRASO_MS, lambda: self.seguir(aba))

    def origem_no_cursor(self, aba: Any) -> tuple[Any, Any]:
        """`(origem, bloco)` do cursor da aba: no texto, o bloco do modelo; no código, a tag da linha."""
        from ui.editor.codigo import EditorDeCodigo

        widget = aba.widget
        if isinstance(widget, EditorDeCodigo):
            return co.origem_na_linha(widget.texto_todo(), widget.posicao[0]), None
        bloco_id = widget.bloco_atual() if widget is not None else None
        projeto = self.j._exigir_projeto()
        cap = projeto.livro.capitulo(aba.arquivo)
        if cap is None or bloco_id is None:
            return None, None
        from core.editor import modelo

        bloco = next((b for b in modelo.blocos_do_capitulo(cap) if b.id == bloco_id), None)
        if bloco is None:                       # o bloco é novo: o modelo ainda não o tem
            bloco = next((b for b in widget.sincronizar().blocos if b.id == bloco_id), None)
        return (getattr(bloco, "origem", None), bloco)

    def seguir(self, aba: Any) -> None:
        self._agendado = None
        painel = aba.dados.get("original")
        if painel is None:
            return
        origem, bloco = self.origem_no_cursor(aba)
        if origem is None:
            painel.mostrar(None)
            return
        livro = self.j._exigir_projeto().livro
        suspeitas = [b.origem.caixa for _a, b in co.blocos_da_pagina(livro, origem.pagina)
                     if b.origem.caixa and b.extras.get("data-suspeito") and b.origem.bloco_id != origem.bloco_id]
        texto = ""
        if bloco is not None and bloco.extras.get("data-suspeito"):
            motivos, _leituras = self.j.descrever_suspeita(bloco)
            texto = "Suspeito: " + "; ".join(motivos[:2])
        painel.mostrar(origem.pagina, origem.caixa, suspeitas, texto)

    # -- ir ao bloco ------------------------------------------------------------------

    def ir_ao_bloco(self, arquivo: str, bloco: Any) -> None:
        """Abre o capítulo (na vista que a aba já tem) e põe o cursor no bloco."""
        from ui.editor.codigo import EditorDeCodigo

        j = self.j
        aba = j.abrir_capitulo(arquivo)
        self.reabrir(aba)
        widget = aba.widget
        if isinstance(widget, EditorDeCodigo):
            origem = getattr(bloco, "origem", None)
            alvo = f'data-origem-bloco="{origem.bloco_id}"' if origem is not None else f'id="{bloco.id}"'
            indice = widget.texto.search(alvo, "1.0")
            if indice:
                widget.ir_para(int(indice.split(".")[0]))
        else:
            widget.ir_para(bloco.id, 0)
        widget.foco()
        if aba.dados.get("original") is not None:
            self.seguir(aba)

    def _clicou(self, aba: Any, pagina: int, x: float, y: float) -> None:
        painel = aba.dados.get("original")
        livro = self.j._exigir_projeto().livro
        achado = co.bloco_no_ponto(livro, pagina, x, y, painel.dpi(pagina) if painel is not None else co.DPI_PADRAO)
        if achado is None:
            self.j.status("Nenhum bloco do livro veio deste ponto da página.")
            return
        self.ir_ao_bloco(*achado)

    def suspeita(self, sentido: int = 1) -> tuple[str, str] | None:
        """`F4` / `Shift+F4`: a suspeita seguinte ou a anterior, dando a volta no livro."""
        j = self.j
        projeto = j._exigir_projeto()
        j._sincronizar_tudo()
        aba = j.aba_ativa()
        arquivo = aba.arquivo if aba is not None else ""
        bloco_id = None
        if aba is not None and aba.tipo == "capitulo" and aba.modo == "texto":
            bloco_id = aba.widget.bloco_atual()
        elif aba is not None and aba.tipo == "capitulo":
            origem, _ = self.origem_no_cursor(aba)
            cap = projeto.livro.capitulo(arquivo)
            if origem is not None and cap is not None:
                bloco_id = next((b.id for b in co.blocos_com_origem(cap) if b.origem.bloco_id == origem.bloco_id),
                                None)
        alvo = co.vizinha_suspeita(projeto.livro, arquivo, bloco_id, sentido)
        if alvo is None:
            j.status("Nenhum bloco suspeito no livro.")
            return None
        cap = projeto.livro.capitulo(alvo[0])
        from core.editor import modelo

        bloco = next(b for b in modelo.blocos_do_capitulo(cap) if b.id == alvo[1])
        self.ir_ao_bloco(alvo[0], bloco)
        total = len(co.suspeitos(projeto.livro))
        j.status(f"Suspeita {co.suspeitos(projeto.livro).index(alvo) + 1} de {total} ({alvo[0]}).")
        return alvo

    # -- reler ------------------------------------------------------------------------

    def reler(self, camada: str | None = None, confirmar: bool = True) -> Any:
        """Ferramentas → Reler a página do PDF…: a página do bloco sob o cursor, lida de novo."""
        j = self.j
        aba = j.aba_ativa()
        if aba is None or aba.tipo != "capitulo":
            raise ValueError("ponha o cursor num bloco que veio do PDF")
        origem, _bloco = self.origem_no_cursor(aba)
        if origem is None:
            raise ValueError("o bloco sob o cursor não veio do PDF: não há o que reler")
        pdf = self._pdf()
        if camada is None:
            rotulos = [r for r, _v in ap.LEITURAS]
            indice = j.caixas.escolher(f"Reler a página {origem.pagina + 1} do PDF", "Como ler:", rotulos, "Reler")
            if indice is None:
                return None
            camada = ap.LEITURAS[indice][1]
        prefs = j._preferencia("abrir_pdf", {}) or {}
        pasta = tempfile.mkdtemp(prefix="pbe-reler-")
        pedido = ap.Pedido(pdf=pdf, paginas=[origem.pagina + 1], idioma=str(prefs.get("idioma") or "en"),
                           camada=camada, dividir="pagina",
                           saida=os.path.join(pasta, f"pagina-{origem.pagina + 1}.json"))
        pagina = origem.pagina
        return j.leitura_de_pdf.iniciar(pedido, ao_fim=lambda json_: self._trocar(pagina, json_, confirmar))

    def _trocar(self, pagina: int, arquivo_json: str, confirmar: bool) -> Any:
        from core.editor import importar_ir
        from core.editorial_model import EditorialDocument

        j = self.j
        projeto = j._exigir_projeto()
        livro = projeto.livro
        novo, _relatorio = importar_ir.de_documento(EditorialDocument.load_json(arquivo_json), dividir="pagina")
        novos = [b for cap in novo.capitulos for b in cap.blocos]
        antes = len(co.blocos_da_pagina(livro, pagina))
        entram = sum(1 for b in novos if b.__class__.__name__ != "MarcaDePagina")
        if confirmar and not j.caixas.pergunta(
                f"Trocar os {antes} bloco(s) da página {pagina + 1} pelos {entram} relidos?\n\n"
                "Antes, um ponto de verificação é criado (Arquivo → Ponto de verificação → Restaurar desfaz).",
                cancelar=False):
            j.status("Releitura descartada.")
            return None
        try:
            j.checkpoint_criar(f"antes de reler a página {pagina + 1}")
        except Exception as erro:      # noqa: BLE001 — livro nunca salvo: segue, avisando
            j.log.warning("Sem ponto de verificação antes de reler: %s", erro)
        j._sincronizar_tudo()
        for href, recurso in novo.recursos.items():       # as imagens das figuras e dos diagramas relidos
            if href not in livro.recursos and not (recurso.tipo_mime or "").startswith(("text/", "application/")):
                livro.recursos[href] = recurso
        troca = co.trocar_pagina(livro, pagina, novos)
        j.operacoes._depois(*troca.capitulos, sumario=False)
        j.log.info("Página %d relida: %d bloco(s) saíram, %d entraram (%s). A ponte com a revisão não cobre os "
                   "blocos relidos.", pagina + 1, troca.saidos, troca.entrados, ", ".join(troca.capitulos))
        j.status(f"Página {pagina + 1} relida: {troca.saidos} → {troca.entrados} bloco(s).")
        aba = j.aba_ativa()
        if aba is not None and aba.dados.get("original") is not None:
            self.seguir(aba)
        return troca


__all__ = ["PainelOriginal", "Original"]
