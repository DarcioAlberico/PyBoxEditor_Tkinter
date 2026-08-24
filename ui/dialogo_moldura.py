"""
Como o diagrama sai no arquivo: a moldura e o tamanho (F97).

Duas perguntas, e uma caixa só. As outras escolhas da exportação saem em
`messagebox` encadeados, e é o que elas pedem — são sim-ou-não, e cada uma se
explica sozinha. Estas duas não: uma tem três respostas, a outra é um número, e
as duas mexem no **mesmo desenho**. Perguntadas em caixas separadas, quem
escolhesse a moldura dupla não teria como ver que a escolheu para um diagrama de
4,5 cm; aqui a amostra à esquerda muda enquanto se escolhe.

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

import tkinter as tk
from tkinter import ttk
from typing import Optional, Tuple

from core.exportar import CORPO_PADRAO_PT, PASSO_DO_CORPO_PT
from core.render_diagrama import MOLDURA_PADRAO

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

#: A amostra: lado do tabuleiro desenhado, em pixels de tela.
LADO_DA_AMOSTRA = 144
COR_CLARA = "#F0D9B5"
COR_ESCURA = "#B58863"

#: Quanto o desenho da amostra reserva em volta, para a moldura dupla caber.
FOLGA_DA_AMOSTRA = 12

#: Pontos por centímetro. É a conta que transforma o corpo pedido na medida que
#: se confere com uma régua sobre o papel.
PT_POR_CM = 72.0 / 2.54


class DialogoMoldura:
    """Pergunta a moldura e o corpo. Devolve `(moldura, corpo_pt)` ou `None`."""

    def __init__(self, parent, moldura: str = MOLDURA_PADRAO,
                 corpo_pt: float = CORPO_PADRAO_PT):
        self.parent = parent
        self.moldura_inicial = moldura
        self.corpo_inicial = corpo_pt
        self.resultado: Optional[Tuple[str, float]] = None

    # ------------------------------------------------------------------
    # Construir
    # ------------------------------------------------------------------

    def mostrar(self) -> Optional[Tuple[str, float]]:
        self._construir()
        self.top.grab_set()
        self.top.focus_set()
        self.parent.wait_window(self.top)
        return self.resultado

    def _construir(self):
        self.top = tk.Toplevel(self.parent)
        self.top.title("Moldura e tamanho do diagrama")
        self.top.transient(self.parent)
        self.top.resizable(False, False)
        self.top.protocol("WM_DELETE_WINDOW", self._cancelar)

        corpo = ttk.Frame(self.top, padding=12)
        corpo.pack(fill="both", expand=True)

        self.amostra = tk.Canvas(
            corpo, width=LADO_DA_AMOSTRA + 2 * FOLGA_DA_AMOSTRA,
            height=LADO_DA_AMOSTRA + 2 * FOLGA_DA_AMOSTRA,
            highlightthickness=0, background="white")
        self.amostra.grid(row=0, column=0, rowspan=2, padx=(0, 14), sticky="n")

        quadro = ttk.LabelFrame(corpo, text="moldura", padding=6)
        quadro.grid(row=0, column=1, sticky="ew")
        self.var_moldura = tk.StringVar(value=self.moldura_inicial)
        for valor, rotulo, explicacao in FEITIOS:
            ttk.Radiobutton(quadro, text=rotulo, value=valor,
                            variable=self.var_moldura,
                            command=self._desenhar_amostra).pack(anchor="w")
            ttk.Label(quadro, text=explicacao, foreground="gray30",
                      wraplength=240).pack(anchor="w", padx=(20, 0),
                                           pady=(0, 4))

        tamanho = ttk.LabelFrame(corpo, text="tamanho", padding=6)
        tamanho.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        linha = ttk.Frame(tamanho)
        linha.pack(anchor="w")
        self.var_corpo = tk.StringVar(value=f"{self.corpo_inicial:g}")
        ttk.Spinbox(linha, from_=CORPO_MINIMO, to=CORPO_MAXIMO,
                    increment=PASSO_DO_CORPO_PT, width=6,
                    textvariable=self.var_corpo,
                    command=self._mudou_o_corpo).pack(side="left")
        ttk.Label(linha, text="pt por casa").pack(side="left", padx=(6, 0))
        self.var_corpo.trace_add("write", lambda *_a: self._mudou_o_corpo())
        self.lbl_medida = ttk.Label(tamanho, foreground="gray30",
                                    wraplength=240, justify="left")
        self.lbl_medida.pack(anchor="w", pady=(4, 0))

        ttk.Label(corpo, wraplength=380, foreground="gray30", justify="left",
                  text="A casa é o quadrado do tipo: o tabuleiro mede oito "
                       "vezes o corpo. Vale para o diagrama redesenhado e para "
                       "o recorte do scan, para os dois saírem do mesmo "
                       "tamanho no mesmo livro."
                  ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 0))

        botoes = ttk.Frame(corpo)
        botoes.grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        self.btn_ok = ttk.Button(botoes, text="OK", command=self._confirmar)
        self.btn_ok.pack(side="right")
        ttk.Button(botoes, text="Cancelar",
                   command=self._cancelar).pack(side="right", padx=(0, 6))

        self.top.bind("<Return>", lambda _e: self._confirmar())
        self.top.bind("<Escape>", lambda _e: self._cancelar())
        self._mudou_o_corpo()

    # ------------------------------------------------------------------
    # Reagir
    # ------------------------------------------------------------------

    def _corpo_digitado(self) -> Optional[float]:
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
        corpo = self._corpo_digitado()
        if corpo is None:
            self.lbl_medida.config(
                text=f"digite um número entre {CORPO_MINIMO:g} e "
                     f"{CORPO_MAXIMO:g} pontos")
            self.btn_ok.state(["disabled"])
            return
        lado_pt = corpo * 8
        self.lbl_medida.config(
            text=f"tabuleiro de {lado_pt:g} pt — {lado_pt / PT_POR_CM:.1f} cm "
                 f"de lado".replace(".", ","))
        self.btn_ok.state(["!disabled"])
        self._desenhar_amostra()

    def _desenhar_amostra(self):
        """
        Um tabuleiro de brinquedo com a moldura escolhida.

        **A amostra não muda de tamanho com o corpo**, e é de propósito: ela
        está aqui para mostrar a moldura, e um tabuleiro que encolhesse a cada
        tecla no campo do corpo faria o olho perseguir a coisa errada. O tamanho
        quem diz é a linha de texto embaixo do campo, em pontos e em
        centímetros.
        """
        self.amostra.delete("all")
        casa = LADO_DA_AMOSTRA / 8.0
        x0 = y0 = FOLGA_DA_AMOSTRA
        for i in range(8):
            for j in range(8):
                cor = COR_CLARA if (i + j) % 2 == 0 else COR_ESCURA
                self.amostra.create_rectangle(
                    x0 + j * casa, y0 + i * casa,
                    x0 + (j + 1) * casa, y0 + (i + 1) * casa,
                    fill=cor, outline=cor)

        moldura = self.var_moldura.get()
        if moldura == "sem":
            return
        # As mesmas proporções do PNG (`render_diagrama.MOLDURA_DUPLA`), na
        # escala da amostra: o filete de fora é o grosso.
        tracos = ([(0, 2)] if moldura == "simples"
                  else [(0, 1), (3, 3)])
        for recuo, espessura in tracos:
            meio = recuo + espessura / 2.0
            self.amostra.create_rectangle(
                x0 - meio, y0 - meio,
                x0 + LADO_DA_AMOSTRA + meio, y0 + LADO_DA_AMOSTRA + meio,
                outline="black", width=espessura)

    # ------------------------------------------------------------------
    # Fechar
    # ------------------------------------------------------------------

    def _confirmar(self):
        corpo = self._corpo_digitado()
        if corpo is None:
            return
        self.resultado = (self.var_moldura.get(), corpo)
        self.top.destroy()

    def _cancelar(self):
        self.resultado = None
        self.top.destroy()
