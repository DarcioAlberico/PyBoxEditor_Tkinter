"""
Como o diagrama sai no arquivo: a fonte, a moldura e o tamanho (F97, F98, F101).

Quatro perguntas, e uma caixa só. Até 2026-09-18 as outras escolhas da
exportação saíam em `messagebox` encadeados — catorze, contadas —, e estas
quatro eram a única caixa de verdade; hoje **todas** cabem numa
(`ui.dialogo_de_exportacao`), e o que está aqui é o painel do diagrama que
essa caixa embute (`PainelDoDiagrama`). `DialogoDoDiagrama` continua
existindo como a mesma caixa de antes, sozinha, para quem só quer a fonte,
a moldura e o corpo.

Perguntadas em caixas separadas, quem escolhesse a moldura dupla não teria
como ver que a escolheu para um diagrama de 4,5 cm na fonte errada — por isso
a amostra fica ao lado das escolhas.

**A quina é caixinha e não um quarto feitio de moldura** (F101). "Sem moldura
arredondada" não quer dizer nada, e cinco radiobuttons fariam o usuário procurar
a combinação em vez de escolhê-la. Por isso ela desliga junto com a moldura:
sem filete não há quina.

**A amostra é o diagrama de verdade, e não um desenho de mentira.** Ela sai do
`render_diagrama.desenhar`, com a fonte e a moldura escolhidas — o mesmo código
que vai escrever o livro. Foi um tabuleiro de brinquedo desenhado no `Canvas`
por uma versão, e ele mentia justamente onde a escolha importa: as peças eram as
mesmas nas duas fontes.

**O tamanho é a casa, e não o tabuleiro.** A fonte de diagrama mapeia caractere
→ casa inteira, e a casa é o quadrado do em — então o corpo em pontos *é* o lado
da casa, e o tabuleiro mede oito vezes isso. É o número que o tipógrafo de livro
de xadrez usa, e é por isso que o padrão é 16 pt e não "4,5 cm": quem já sabe
com que corpo quer o diagrama não precisa dividir nada.

**O passo é de meio ponto porque o DOCX não fecha noutro.** O Word escreve o
corpo em meios-pontos e a entrelinha em twips, e o tabuleiro em texto só sai
quadrado quando os dois dizem o mesmo número — ver `PASSO_DO_CORPO_PT`, no
`core/exportar.py`, que é quem arredonda de verdade. O `Spinbox` daqui só evita
que o usuário digite um número que seria mudado debaixo dele sem aviso.
"""

import io
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Tuple

from PIL import Image, ImageTk

from core import render_diagrama
from core.exportar import CORPO_PADRAO_PT, PASSO_DO_CORPO_PT

#: (valor, rótulo, explicação) de cada feitio, na ordem em que aparecem.
FEITIOS = (
    ("sem", "sem moldura",
     "o tabuleiro nu, como a fonte o desenha"),
    ("simples", "moldura simples",
     "um filete em volta — é o padrão"),
    ("dupla", "moldura dupla",
     "dois filetes, o grosso por fora, como no livro impresso"),
)

#: Limites do corpo, em pontos. Abaixo de 6 a peça não se distingue impressa;
#: acima de 48 o tabuleiro não cabe na largura de uma página A4 com margens.
CORPO_MINIMO = 6.0
CORPO_MAXIMO = 48.0

#: A posição que a amostra desenha, e o lado dela em pixels de tela.
#:
#: **Não é a inicial**, e não é por variedade: numa posição de abertura as oito
#: casas do meio ficam vazias e metade das peças some atrás da fileira de peões.
#: Um final com peças espalhadas mostra rei, dama, torre, bispo, cavalo e peão
#: das duas cores em casa clara e escura, que é o que se está escolhendo.
FEN_DA_AMOSTRA = "3qkb2/5p2/2n5/1B2P3/3P1r2/2N5/5P2/2RQK3 w - - 0 1"
LADO_DA_AMOSTRA = 184

#: Pontos por centímetro. É a conta que transforma o corpo pedido na medida que
#: se confere com uma régua sobre o papel.
PT_POR_CM = 72.0 / 2.54


class PainelDoDiagrama(ttk.Frame):
    """A amostra, a fonte, a moldura, a quina e o corpo, num `Frame`.

    `valores()` devolve `(fonte, moldura, cantos, corpo_pt)`, ou `None`
    enquanto o corpo digitado não é um número no intervalo; `ao_mudar` é
    chamado a cada mudança, para quem embute o painel ligar e desligar o
    botão de confirmar.
    """

    def __init__(self, master, *, fonte: str = render_diagrama.FONTE_PADRAO,
                 moldura: str = render_diagrama.MOLDURA_PADRAO,
                 cantos: str = render_diagrama.CANTO_PADRAO,
                 corpo_pt: float = CORPO_PADRAO_PT,
                 ao_mudar: Optional[Callable[[], None]] = None,
                 compacto: bool = False, **kw):
        """`compacto` põe fonte, tamanho e moldura ao lado da amostra, em
        três colunas e sem as explicações longas — é o feitio que cabe na caixa
        de exportação numa tela de 768 px de altura. O feitio de sempre, em
        coluna, é o da caixa sozinha."""
        super().__init__(master, **kw)
        self.ao_mudar = ao_mudar
        self.compacto = compacto
        self._foto = None      # o Tk descarta a imagem que ninguém segura

        self.amostra = tk.Canvas(self, width=LADO_DA_AMOSTRA + 24,
                                 height=LADO_DA_AMOSTRA + 24,
                                 highlightthickness=0, background="white")
        self.amostra.grid(row=0, column=0, rowspan=3, padx=(0, 14), sticky="n")
        if compacto:
            self._construir_compacto(fonte, moldura, cantos, corpo_pt)
            self._mudou_o_corpo()
            self._mudou_a_moldura()
            return

        quadro = ttk.LabelFrame(self, text="fonte do diagrama", padding=6)
        quadro.grid(row=0, column=1, sticky="ew")
        disponiveis = render_diagrama.fontes()
        inicial = (fonte if fonte in disponiveis
                   else (disponiveis[0] if disponiveis else ""))
        self.var_fonte = tk.StringVar(value=inicial)
        self.combo_fonte = ttk.Combobox(quadro, values=disponiveis, width=26,
                                        state="readonly",
                                        textvariable=self.var_fonte)
        self.combo_fonte.pack(anchor="w")
        self.combo_fonte.bind("<<ComboboxSelected>>",
                              lambda _e: self._desenhar_amostra())
        ttk.Label(quadro, foreground="gray30", wraplength=240, justify="left",
                  text="Vale para o diagrama redesenhado. O recorte do scan sai "
                       "como está na página, em qualquer fonte."
                  ).pack(anchor="w", pady=(4, 0))

        feitio = ttk.LabelFrame(self, text="moldura", padding=6)
        feitio.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        self.var_moldura = tk.StringVar(
            value=moldura if moldura in {v for v, _r, _e in FEITIOS}
            else render_diagrama.MOLDURA_PADRAO)
        for valor, rotulo, explicacao in FEITIOS:
            ttk.Radiobutton(feitio, text=rotulo, value=valor,
                            variable=self.var_moldura,
                            command=self._mudou_a_moldura).pack(anchor="w")
            ttk.Label(feitio, text=explicacao, foreground="gray30",
                      wraplength=240).pack(anchor="w", padx=(20, 0),
                                           pady=(0, 4))
        self.var_cantos = tk.BooleanVar(value=cantos == "arredondado")
        self.chk_cantos = ttk.Checkbutton(
            feitio, text="cantos arredondados", variable=self.var_cantos,
            command=self._desenhar_amostra)
        self.chk_cantos.pack(anchor="w", pady=(2, 0))

        tamanho = ttk.LabelFrame(self, text="tamanho", padding=6)
        tamanho.grid(row=2, column=1, sticky="ew", pady=(8, 0))
        linha = ttk.Frame(tamanho)
        linha.pack(anchor="w")
        self.var_corpo = tk.StringVar(value=f"{corpo_pt:g}")
        ttk.Spinbox(linha, from_=CORPO_MINIMO, to=CORPO_MAXIMO,
                    increment=PASSO_DO_CORPO_PT, width=6,
                    textvariable=self.var_corpo,
                    command=self._mudou_o_corpo).pack(side="left")
        ttk.Label(linha, text="pt por casa").pack(side="left", padx=(6, 0))
        self.var_corpo.trace_add("write", lambda *_a: self._mudou_o_corpo())
        self.lbl_medida = ttk.Label(tamanho, foreground="gray30",
                                    wraplength=240, justify="left")
        self.lbl_medida.pack(anchor="w", pady=(4, 0))

        ttk.Label(self, wraplength=430, foreground="gray30", justify="left",
                  text="A casa é o quadrado do tipo: o tabuleiro mede oito "
                       "vezes o corpo. Vale para o diagrama redesenhado e para "
                       "o recorte do scan, para os dois saírem do mesmo "
                       "tamanho no mesmo livro."
                  ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))

        self._mudou_o_corpo()
        self._mudou_a_moldura()

    def _construir_compacto(self, fonte, moldura, cantos, corpo_pt):
        """Amostra | fonte e tamanho | moldura e quina — três colunas."""
        disponiveis = render_diagrama.fontes()
        inicial = (fonte if fonte in disponiveis
                   else (disponiveis[0] if disponiveis else ""))
        meio = ttk.Frame(self)
        meio.grid(row=0, column=1, sticky="nw", padx=(0, 14))
        ttk.Label(meio, text="Fonte do diagrama:").pack(anchor="w")
        self.var_fonte = tk.StringVar(value=inicial)
        self.combo_fonte = ttk.Combobox(meio, values=disponiveis, width=24,
                                        state="readonly",
                                        textvariable=self.var_fonte)
        self.combo_fonte.pack(anchor="w", pady=(2, 0))
        self.combo_fonte.bind("<<ComboboxSelected>>",
                              lambda _e: self._desenhar_amostra())
        ttk.Label(meio, foreground="gray30", wraplength=220, justify="left",
                  text="O recorte do scan sai como está, em qualquer fonte."
                  ).pack(anchor="w", pady=(2, 0))
        ttk.Label(meio, text="Tamanho:").pack(anchor="w", pady=(10, 0))
        linha = ttk.Frame(meio)
        linha.pack(anchor="w", pady=(2, 0))
        self.var_corpo = tk.StringVar(value=f"{corpo_pt:g}")
        ttk.Spinbox(linha, from_=CORPO_MINIMO, to=CORPO_MAXIMO,
                    increment=PASSO_DO_CORPO_PT, width=6,
                    textvariable=self.var_corpo,
                    command=self._mudou_o_corpo).pack(side="left")
        ttk.Label(linha, text="pt por casa").pack(side="left", padx=(6, 0))
        self.var_corpo.trace_add("write", lambda *_a: self._mudou_o_corpo())
        self.lbl_medida = ttk.Label(meio, foreground="gray30", wraplength=220,
                                    justify="left")
        self.lbl_medida.pack(anchor="w", pady=(2, 0))

        direita = ttk.Frame(self)
        direita.grid(row=0, column=2, sticky="nw")
        ttk.Label(direita, text="Moldura:").pack(anchor="w")
        self.var_moldura = tk.StringVar(
            value=moldura if moldura in {v for v, _r, _e in FEITIOS}
            else render_diagrama.MOLDURA_PADRAO)
        for valor, rotulo, _explicacao in FEITIOS:
            ttk.Radiobutton(direita, text=rotulo, value=valor,
                            variable=self.var_moldura,
                            command=self._mudou_a_moldura).pack(anchor="w", pady=(2, 0))
        self.var_cantos = tk.BooleanVar(value=cantos == "arredondado")
        self.chk_cantos = ttk.Checkbutton(
            direita, text="cantos arredondados", variable=self.var_cantos,
            command=self._desenhar_amostra)
        self.chk_cantos.pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------
    # Reagir
    # ------------------------------------------------------------------

    def corpo_digitado(self) -> Optional[float]:
        """O corpo do campo, ou `None` se ele não é um número no intervalo."""
        try:
            valor = float(self.var_corpo.get().replace(",", "."))
        except ValueError:
            return None
        if not CORPO_MINIMO <= valor <= CORPO_MAXIMO:
            return None
        return round(valor / PASSO_DO_CORPO_PT) * PASSO_DO_CORPO_PT

    def _mudou_o_corpo(self):
        """
        A medida do tabuleiro, e o OK que só aceita número.

        Dizer o lado em centímetros ao lado do corpo em pontos é o que fecha a
        conta para quem pensa a página em centímetros — 16 pt não parece um
        tamanho até virar 4,5 cm.
        """
        corpo = self.corpo_digitado()
        if corpo is None:
            self.lbl_medida.config(
                text=f"digite um número entre {CORPO_MINIMO:g} e "
                     f"{CORPO_MAXIMO:g} pontos")
        else:
            lado_pt = corpo * 8
            self.lbl_medida.config(
                text=f"tabuleiro de {lado_pt:g} pt — {lado_pt / PT_POR_CM:.1f} cm "
                     f"de lado".replace(".", ","))
        if self.ao_mudar is not None:
            self.ao_mudar()

    def _mudou_a_moldura(self):
        """Sem filete não há quina — a caixinha desliga junto com a moldura."""
        sem = self.var_moldura.get() == "sem"
        self.chk_cantos.state(["disabled"] if sem else ["!disabled"])
        self._desenhar_amostra()

    def cantos(self) -> str:
        """`"arredondado"` só quando há moldura para arredondar."""
        if self.var_moldura.get() == "sem" or not self.var_cantos.get():
            return "reto"
        return "arredondado"

    def valores(self) -> Optional[Tuple[str, str, str, float]]:
        corpo = self.corpo_digitado()
        if corpo is None or not self.var_fonte.get():
            return None
        return (self.var_fonte.get(), self.var_moldura.get(), self.cantos(), corpo)

    def _desenhar_amostra(self):
        """
        O diagrama de verdade, na fonte e na moldura escolhidas.

        **A amostra não muda de tamanho com o corpo**, e é de propósito: ela
        está aqui para mostrar as peças e o filete, e um tabuleiro que
        encolhesse a cada tecla no campo do corpo faria o olho perseguir a coisa
        errada. O tamanho quem diz é a linha de texto embaixo do campo, em
        pontos e em centímetros.

        Fonte que não carrega não derruba o diálogo: ela vira um recado no lugar
        do desenho, e o usuário escolhe outra. É o mesmo critério do `livro`,
        que cai para o recorte em vez de perder a exportação inteira.
        """
        self.amostra.delete("all")
        centro = (LADO_DA_AMOSTRA + 24) // 2
        try:
            png, largura, altura = render_diagrama.desenhar(
                FEN_DA_AMOSTRA, fonte=self.var_fonte.get(),
                lado_px=LADO_DA_AMOSTRA, moldura=self.var_moldura.get(),
                cantos=self.cantos(), tons=0)
        except (render_diagrama.FonteDesconhecida,
                render_diagrama.FonteIncompleta, ValueError) as erro:
            self.amostra.create_text(centro, centro, width=LADO_DA_AMOSTRA,
                                     justify="center", fill="#B71C1C",
                                     text=f"não deu para desenhar:\n{erro}")
            return
        imagem = Image.open(io.BytesIO(png)).convert("L")
        self._foto = ImageTk.PhotoImage(imagem)
        self.amostra.create_image(centro, centro, image=self._foto)


class DialogoDoDiagrama:
    """Pergunta fonte, moldura, quina e corpo. Devolve a quádrupla, ou `None`."""

    def __init__(self, parent, fonte: str = render_diagrama.FONTE_PADRAO,
                 moldura: str = render_diagrama.MOLDURA_PADRAO,
                 cantos: str = render_diagrama.CANTO_PADRAO,
                 corpo_pt: float = CORPO_PADRAO_PT):
        self.parent = parent
        self.fonte_inicial = fonte
        self.moldura_inicial = moldura
        self.cantos_iniciais = cantos
        self.corpo_inicial = corpo_pt
        self.resultado: Optional[Tuple[str, str, str, float]] = None

    def mostrar(self) -> Optional[Tuple[str, str, str, float]]:
        self._construir()
        self.top.grab_set()
        self.top.focus_set()
        self.parent.wait_window(self.top)
        return self.resultado

    def _construir(self):
        self.top = tk.Toplevel(self.parent)
        self.top.title("Fonte, moldura e tamanho do diagrama")
        self.top.transient(self.parent)
        self.top.resizable(False, False)
        self.top.protocol("WM_DELETE_WINDOW", self._cancelar)

        corpo = ttk.Frame(self.top, padding=12)
        corpo.pack(fill="both", expand=True)
        self.painel = PainelDoDiagrama(
            corpo, fonte=self.fonte_inicial, moldura=self.moldura_inicial,
            cantos=self.cantos_iniciais, corpo_pt=self.corpo_inicial,
            ao_mudar=self._mudou)
        self.painel.pack(fill="both", expand=True)

        botoes = ttk.Frame(corpo)
        botoes.pack(fill="x", pady=(10, 0))
        self.btn_ok = ttk.Button(botoes, text="OK", command=self._confirmar)
        self.btn_ok.pack(side="right")
        ttk.Button(botoes, text="Cancelar",
                   command=self._cancelar).pack(side="right", padx=(0, 6))

        self.top.bind("<Return>", lambda _e: self._confirmar())
        self.top.bind("<Escape>", lambda _e: self._cancelar())
        self._mudou()

    def _mudou(self):
        if not hasattr(self, "btn_ok"):
            return
        self.btn_ok.state(["disabled"] if self.painel.valores() is None
                          else ["!disabled"])

    def _confirmar(self):
        valores = self.painel.valores()
        if valores is None:
            return
        self.resultado = valores
        self.top.destroy()

    def _cancelar(self):
        self.resultado = None
        self.top.destroy()
