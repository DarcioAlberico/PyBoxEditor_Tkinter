"""
Pré-visualização do lote da F3.6.

O critério de `core.semelhanca` acerta ~99,3% dos pares, e o que sobra são
homóglifos que nenhuma medida de imagem separa (`0`×`o`, `1`×`i`, `B`×`b`).
Num lote de 300 isso são dois boxes estragados em silêncio, num box que o
usuário nunca olhou — pior que o erro do OCR, porque sai marcado como revisado.

Daí este diálogo. Os recortes ficam à vista, **ordenados por distância**: o
casamento seguro no começo, o duvidoso no fim. Com botão direito num recorte,
desmarca dali para frente — que é o gesto certo dada a ordenação, e transforma
"conferir 300" em "achar onde a fila começa a estranhar".
"""

import tkinter as tk
from tkinter import ttk
from typing import List, Optional

import numpy as np
from PIL import Image, ImageTk

from core import semelhanca


COLUNAS = 10
ALTURA_MINIATURA = 44
LARGURA_MAXIMA_MINIATURA = 64

#: Teto de recortes exibidos. Acima disso a montagem do grid trava a janela por
#: segundos. O lote aplica **só o que está na tela** — cortar a exibição e
#: aplicar no resto seria mudar o que o usuário não viu.
MAX_EXIBIDOS = 400

COR_MARCADO = "#2E9B4F"
COR_DESMARCADO = "#BDBDBD"
COR_FUNDO_MARCADO = "#E8F5E9"


class DialogoSemelhantes:
    """Devolve os índices escolhidos, ou None se o usuário desistiu."""

    def __init__(self, parent, imagem, boxes, indice, char_novo,
                 leitura=None, rigor="normal"):
        self.parent = parent
        self.imagem = imagem
        self.boxes = boxes
        self.indice = indice
        self.char_novo = char_novo
        self.leitura = leitura
        self.rigor = rigor

        self.achados = []          # [(indice, distancia)]
        self.marcados = {}         # indice -> bool
        self._celulas = {}         # indice -> (frame, label)
        self._fotos = []           # PhotoImage vivas enquanto o diálogo existir
        self.resultado: Optional[List[int]] = None

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def construir(self):
        """
        Monta a janela e roda a busca, sem bloquear.

        Separado de `mostrar` para que os testes possam exercer a marcação e o
        corte de cauda sem um usuário para clicar.
        """
        self.top = tk.Toplevel(self.parent)
        self.top.title("Aplicar a todos os semelhantes")
        self.top.transient(self.parent)

        self._montar_cabecalho()
        self._montar_grade()
        self._montar_rodape()

        self._buscar()

        self.top.bind("<Escape>", lambda e: self._cancelar())
        self.top.bind("<Return>", lambda e: self._confirmar())
        self.top.protocol("WM_DELETE_WINDOW", self._cancelar)
        return self.top

    def mostrar(self) -> Optional[List[int]]:
        self.construir()
        self.top.grab_set()
        self.top.focus_set()
        self.parent.wait_window(self.top)
        return self.resultado

    def _montar_cabecalho(self):
        topo = ttk.Frame(self.top, padding=(10, 8))
        topo.pack(fill="x")

        # O modelo do lote nem sempre é o box selecionado — depois de corrigir,
        # a seleção já avançou (F3.1). Mostrar o recorte é o que deixa isso
        # visível em vez de implícito: se o modelo não for o que o usuário
        # espera, ele vê antes de aplicar em 300 boxes.
        ttk.Label(topo, text="Modelo:").pack(side="left", padx=(0, 6))
        self._foto_modelo = self._miniatura(np.asarray(self.imagem),
                                            self.boxes[self.indice])
        tk.Label(topo, image=self._foto_modelo, background="white",
                 bd=1, relief="solid").pack(side="left", padx=(0, 10))

        self.lbl_titulo = ttk.Label(topo, font=("Segoe UI", 10, "bold"))
        self.lbl_titulo.pack(side="left")

        ttk.Label(topo, text="Rigor:").pack(side="left", padx=(20, 4))
        self.var_rigor = tk.StringVar(value=self.rigor)
        for nome in ("estrito", "normal", "amplo"):
            ttk.Radiobutton(topo, text=nome, value=nome, variable=self.var_rigor,
                            command=self._buscar).pack(side="left")

        self.lbl_ajuda = ttk.Label(
            self.top, foreground="#555", padding=(10, 0),
            text="Clique num recorte para desmarcá-lo. Botão direito desmarca "
                 "dali para o fim — a fila está ordenada do mais parecido ao "
                 "menos.")
        self.lbl_ajuda.pack(fill="x")

    def _montar_grade(self):
        moldura = ttk.Frame(self.top, padding=(10, 6))
        moldura.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(moldura, width=760, height=380,
                                highlightthickness=0, background="white")
        barra = ttk.Scrollbar(moldura, orient="vertical",
                              command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=barra.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")

        self.grade = ttk.Frame(self.canvas)
        self.janela_grade = self.canvas.create_window((0, 0), window=self.grade,
                                                      anchor="nw")
        self.grade.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind_all("<MouseWheel>", self._rolar)

    def _montar_rodape(self):
        rodape = ttk.Frame(self.top, padding=(10, 8))
        rodape.pack(fill="x")

        self.btn_aplicar = ttk.Button(rodape, text="Aplicar",
                                      command=self._confirmar)
        self.btn_aplicar.pack(side="right")
        ttk.Button(rodape, text="Cancelar",
                   command=self._cancelar).pack(side="right", padx=(0, 6))
        ttk.Button(rodape, text="Marcar todos",
                   command=lambda: self._marcar_todos(True)).pack(side="left")
        ttk.Button(rodape, text="Desmarcar todos",
                   command=lambda: self._marcar_todos(False)).pack(side="left",
                                                                   padx=(6, 0))

    # ------------------------------------------------------------------
    # Busca e desenho
    # ------------------------------------------------------------------

    def _buscar(self):
        limiar = semelhanca.RIGOR.get(self.var_rigor.get(),
                                      semelhanca.LIMIAR_PADRAO)
        self.achados = semelhanca.encontrar_semelhantes(
            self.imagem, self.boxes, self.indice, limiar, self.leitura)
        self.marcados = {i: True for i, _ in self.achados[:MAX_EXIBIDOS]}
        self._desenhar()

    def _desenhar(self):
        for filho in self.grade.winfo_children():
            filho.destroy()
        self._celulas.clear()
        self._fotos.clear()

        arr = np.asarray(self.imagem)
        exibidos = self.achados[:MAX_EXIBIDOS]

        for pos, (indice, dist) in enumerate(exibidos):
            b = self.boxes[indice]
            celula = tk.Frame(self.grade, bd=2, relief="solid",
                              highlightthickness=0)
            celula.grid(row=pos // COLUNAS, column=pos % COLUNAS, padx=3, pady=3)

            foto = self._miniatura(arr, b)
            self._fotos.append(foto)
            rotulo = tk.Label(celula, image=foto, background="white")
            rotulo.pack()
            tk.Label(celula, text=f"{dist:.2f}", font=("Segoe UI", 7),
                     foreground="#777").pack()

            for alvo in (celula, rotulo):
                alvo.bind("<Button-1>", lambda e, i=indice: self._alternar(i))
                alvo.bind("<Button-3>", lambda e, p=pos: self._cortar_cauda(p))

            self._celulas[indice] = celula
            self._pintar(indice)

        self._atualizar_contadores()

    def _miniatura(self, arr, b) -> ImageTk.PhotoImage:
        recorte = semelhanca._recortar(arr, b)
        if recorte.size == 0:
            recorte = np.full((8, 8), 255, dtype=np.uint8)
        img = Image.fromarray(recorte).convert("L")
        escala = ALTURA_MINIATURA / max(1, img.height)
        largura = max(1, min(LARGURA_MAXIMA_MINIATURA, int(img.width * escala)))
        return ImageTk.PhotoImage(
            img.resize((largura, ALTURA_MINIATURA), Image.LANCZOS))

    def _pintar(self, indice):
        celula = self._celulas.get(indice)
        if celula is None:
            return
        marcado = self.marcados.get(indice, False)
        celula.configure(
            background=COR_FUNDO_MARCADO if marcado else "white",
            highlightbackground=COR_MARCADO if marcado else COR_DESMARCADO)
        celula.configure(bd=2, relief="solid" if marcado else "flat")

    def _atualizar_contadores(self):
        n = sum(1 for v in self.marcados.values() if v)
        alvo = self.char_novo if self.char_novo else "(vazio)"
        de = f" (lidos como “{self.leitura}”)" if self.leitura else ""
        self.lbl_titulo.config(text=f"Marcar {n} box(es) como “{alvo}”{de}")
        self.btn_aplicar.config(text=f"Aplicar ({n})",
                                state="normal" if n else "disabled")

        if len(self.achados) > MAX_EXIBIDOS:
            self.lbl_ajuda.config(
                foreground="#B71C1C",
                text=f"{len(self.achados)} semelhantes encontrados; a tela "
                     f"mostra os {MAX_EXIBIDOS} mais parecidos e o lote aplica "
                     f"só esses. Repita a operação para alcançar o resto.")

    # ------------------------------------------------------------------
    # Interação
    # ------------------------------------------------------------------

    def _alternar(self, indice):
        self.marcados[indice] = not self.marcados.get(indice, False)
        self._pintar(indice)
        self._atualizar_contadores()

    def _cortar_cauda(self, posicao):
        """Desmarca da posição clicada até o fim da fila."""
        for indice, _ in self.achados[posicao:MAX_EXIBIDOS]:
            self.marcados[indice] = False
            self._pintar(indice)
        self._atualizar_contadores()

    def _marcar_todos(self, valor):
        for indice in self.marcados:
            self.marcados[indice] = valor
            self._pintar(indice)
        self._atualizar_contadores()

    def _rolar(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _fechar(self):
        # O binding da roda é global (bind_all); deixá-lo vivo depois de
        # fechar faria a roda do mouse rolar um Canvas que já não existe.
        self.canvas.unbind_all("<MouseWheel>")
        try:
            self.top.grab_release()
        except tk.TclError:
            pass
        self.top.destroy()

    def _confirmar(self):
        self.resultado = [i for i, _ in self.achados[:MAX_EXIBIDOS]
                          if self.marcados.get(i)]
        self._fechar()

    def _cancelar(self):
        self.resultado = None
        self._fechar()
