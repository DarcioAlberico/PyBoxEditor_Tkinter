"""A fila de suspeitas do documento editorial, com a evidência ao lado.

Até 2026-09-19 esta janela listava os blocos e mostrava, de cada um, o
valor e um `str()` das referências de origem — sem recorte, sem as duas
leituras, com o motivo em código (`low_confidence`) e a edição por
`askstring`. A revisão de 2026-09-18 (`docs/REVISAO_MODOS_OCR.md`, §5.2)
pediu o que um revisor precisa para decidir sem sair daqui, e é o que esta
janela passa a ter:

- **o recorte da página** no lugar do bloco e, linha a linha, no lugar de
  cada linha (`ProvedorDePaginas` rasteriza a página na escala em que ela
  foi lida, e as caixas do IR caem em cima);
- **as duas leituras** de cada linha — a âncora da cadeia própria e a linha
  do motor de prosa — com um botão para ficar com uma delas;
- **o motivo em frase**, vindo de `core.editorial_suspeitas`;
- **filtro** por página e tipo, e um teto de itens por página;
- **lote com amostra**: "aceitar semelhantes" mostra quantos e quais antes;
- **desfazer em pilha**, com a contagem no botão;
- o diagrama abre no `DialogoDiagrama` ao lado do recorte impresso, e o FEN
  que sai de lá entra no documento;
- **exportar com as correções**, quando quem abriu a janela sabe exportar.

O estado mora em `core.editorial_review.ReviewSession`; aqui só se desenha e
se despacham cliques. As teclas de atalho (`A`, `E`, `R`, `D`, `S`, `G`,
`N`) não valem com o foco num campo de texto — a mesma guarda das setas da
rotulagem —, senão digitar "a" no valor aceitava o bloco.
"""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Mapping, Optional

import numpy as np
from PIL import Image, ImageTk

from core.editorial_review import LinhaRevisao, ReviewItem, ReviewSession

#: Largura máxima do recorte na tela, em pixels; a linha pode ser ampliada
#: até `AMPLIACAO_MAXIMA` vezes para caber legível.
LARGURA_DO_RECORTE = 640
ALTURA_DO_RECORTE = 140
AMPLIACAO_MAXIMA = 2.5
#: Folga em volta da caixa, em pixels da página: a linha recortada justa
#: perde a haste do `p` e o pingo do `i`.
FOLGA_DO_RECORTE = 6

TIPOS = {"paragraph": "parágrafo", "heading": "título", "caption": "legenda",
         "chess_sequence": "lances", "diagram": "diagrama", "table": "tabela",
         "figure": "figura",
         "header": "cabeçalho", "footer": "rodapé", "page_break": "quebra",
         "unknown": "desconhecido"}
ESTADOS = {"automatic": "automático", "reviewed": "revisado",
           "rejected": "rejeitado", "unresolved": "sem solução"}
TODAS = "todas"
TODOS = "todos"

#: Quantos itens a amostra do lote mostra antes de pedir confirmação.
AMOSTRA_DO_LOTE = 5


def _recortar(imagem: np.ndarray, caixa, *, ampliar: float = 1.0,
              largura_maxima: int = LARGURA_DO_RECORTE) -> Optional[Image.Image]:
    """O recorte de `caixa` na página, com folga, redimensionado para caber."""
    if imagem is None or not caixa:
        return None
    x1, y1, x2, y2 = (int(v) for v in caixa)
    altura, largura = imagem.shape[:2]
    x1, y1 = max(0, x1 - FOLGA_DO_RECORTE), max(0, y1 - FOLGA_DO_RECORTE)
    x2, y2 = min(largura, x2 + FOLGA_DO_RECORTE), min(altura, y2 + FOLGA_DO_RECORTE)
    if x2 <= x1 or y2 <= y1:
        return None
    recorte = Image.fromarray(np.ascontiguousarray(imagem[y1:y2, x1:x2]))
    escala = min(largura_maxima / recorte.width, ALTURA_DO_RECORTE / recorte.height,
                 ampliar)
    if escala <= 0:
        return None
    tamanho = (max(1, int(recorte.width * escala)), max(1, int(recorte.height * escala)))
    return recorte.resize(tamanho, Image.LANCZOS)


def _texto_do_valor(item: ReviewItem) -> str:
    """O valor do bloco como texto editável: o parágrafo como está, a tabela
    uma fila por linha com ` | ` entre células, o diagrama pelo FEN."""
    valor = item.value
    if isinstance(valor, str):
        return valor
    if isinstance(valor, Mapping):
        if "rows" in valor:
            return "\n".join(" | ".join(str(c) for c in fila) for fila in valor["rows"])
        if "fen" in valor:
            return str(valor.get("fen") or "")
    return "" if valor is None else str(valor)


def _valor_do_texto(item: ReviewItem, texto: str) -> Any:
    """O inverso de `_texto_do_valor`: o que `session.edit` recebe."""
    valor = item.value
    if isinstance(valor, Mapping):
        if "rows" in valor:
            filas = [[c.strip() for c in linha.split("|")] for linha in texto.splitlines()]
            return {**copy.deepcopy(valor), "rows": filas}
        if "fen" in valor:
            return {**copy.deepcopy(valor), "fen": texto.strip()}
    return texto


class DialogoRevisaoEditorial(tk.Toplevel):
    """Fila global com contexto de origem, hipótese e decisão."""

    def __init__(self, parent: tk.Misc, session: ReviewSession, *,
                 imagem_da_pagina: Optional[Callable[[int], Optional[np.ndarray]]] = None,
                 abrir_diagrama: Optional[Callable[[ReviewItem, Optional[np.ndarray]],
                                                   Optional[str]]] = None,
                 ao_exportar: Optional[Callable[[Any], None]] = None,
                 aviso_da_exportacao: str = ""):
        super().__init__(parent)
        self.session = session
        self.imagem_da_pagina = imagem_da_pagina
        self.abrir_diagrama = abrir_diagrama
        self.ao_exportar = ao_exportar
        #: Com texto, "Exportar com as correções" fica desabilitado e o texto diz por quê
        #: (SPEC_EDITOR DEC-10: o livro está no editor de livros; exporte por ele).
        self.aviso_da_exportacao = aviso_da_exportacao
        self.title("Revisão editorial — OCR de xadrez")
        # Cabe em 768 px de altura com a barra de tarefas e a moldura da
        # janela, como a caixa de exportação (586): a 720 e a 660 a fileira
        # de baixo dos botões ficava debaixo da barra. Quem tem tela maior
        # maximiza, e o recorte e o valor crescem com ela.
        # E encostada no alto da tela: o Windows abre cada janela nova um
        # pouco mais abaixo que a anterior, e a terceira já entrava debaixo
        # da barra de tarefas.
        largura, altura = min(1180, self.winfo_screenwidth() - 20), 600
        x = max(0, (self.winfo_screenwidth() - largura) // 2)
        self.geometry(f"{largura}x{altura}+{x}+0")
        self.minsize(900, 520)
        self._ids: list[str] = []
        self._itens: dict[str, ReviewItem] = {}
        self._fotos: list = []
        self._linha_selecionada: Optional[LinhaRevisao] = None
        self.var_pagina = tk.StringVar(value=TODAS)
        self.var_tipo = tk.StringVar(value=TODOS)
        self.var_limite = tk.StringVar(value="0")
        self.var_contagem = tk.StringVar(value="")
        self._build()
        self._refresh()

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.columnconfigure(0, weight=2)
        self.columnconfigure(1, weight=3)
        self.rowconfigure(1, weight=1)

        filtros = ttk.Frame(self, padding=(10, 8, 10, 0))
        filtros.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(filtros, text="Página:").pack(side="left")
        self.cb_pagina = ttk.Combobox(filtros, textvariable=self.var_pagina, width=8,
                                      state="readonly")
        self.cb_pagina.pack(side="left", padx=(4, 12))
        ttk.Label(filtros, text="Tipo:").pack(side="left")
        self.cb_tipo = ttk.Combobox(filtros, textvariable=self.var_tipo, width=12,
                                    state="readonly")
        self.cb_tipo.pack(side="left", padx=(4, 12))
        ttk.Label(filtros, text="Por página (0 = todos):").pack(side="left")
        self.sp_limite = ttk.Spinbox(filtros, from_=0, to=99, width=4,
                                     textvariable=self.var_limite,
                                     command=self._refresh)
        self.sp_limite.pack(side="left", padx=(4, 12))
        ttk.Label(filtros, textvariable=self.var_contagem).pack(side="left", padx=(8, 0))
        for widget in (self.cb_pagina, self.cb_tipo):
            widget.bind("<<ComboboxSelected>>", lambda _e: self._refresh())
        self.sp_limite.bind("<Return>", lambda _e: self._refresh())

        self.tree = ttk.Treeview(self, columns=("kind", "page", "severity", "status", "resumo"),
                                 show="headings", selectmode="browse")
        for column, title, width, stretch in (
                ("kind", "Tipo", 90, False), ("page", "Pág.", 50, False),
                ("severity", "Impacto", 60, False), ("status", "Estado", 90, False),
                ("resumo", "Motivo", 260, True)):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="w", stretch=stretch)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=10)
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)

        panel = ttk.Frame(self, padding=(5, 10, 10, 10))
        panel.grid(row=1, column=1, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(3, weight=1)
        panel.rowconfigure(5, weight=1)

        self.summary = ttk.Label(panel, text="", justify="left", anchor="w",
                                 font=("Segoe UI", 10, "bold"))
        self.summary.grid(row=0, column=0, sticky="ew")
        self.lbl_motivos = ttk.Label(panel, text="", justify="left", anchor="w",
                                     wraplength=620, foreground="#8a3b00")
        self.lbl_motivos.grid(row=1, column=0, sticky="ew", pady=(2, 6))

        recorte = ttk.LabelFrame(panel, text="Recorte da página", padding=4)
        recorte.grid(row=2, column=0, sticky="ew")
        self.lbl_recorte = ttk.Label(recorte, text="(sem imagem da página)", anchor="center")
        self.lbl_recorte.pack(fill="x")

        linhas = ttk.LabelFrame(panel, text="Linhas do bloco — cadeia própria × motor de prosa",
                                padding=4)
        linhas.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
        linhas.columnconfigure(0, weight=1)
        linhas.rowconfigure(0, weight=1)
        self.tree_linhas = ttk.Treeview(linhas, columns=("n", "texto", "motivo"),
                                        show="headings", selectmode="browse", height=4)
        for column, title, width, stretch in (("n", "#", 32, False),
                                              ("texto", "Texto", 300, True),
                                              ("motivo", "Motivo", 260, True)):
            self.tree_linhas.heading(column, text=title)
            self.tree_linhas.column(column, width=width, anchor="w", stretch=stretch)
        self.tree_linhas.tag_configure("suspeita", foreground="#b00020")
        self.tree_linhas.grid(row=0, column=0, sticky="nsew")
        self.tree_linhas.bind("<<TreeviewSelect>>", self._show_line)
        leituras = ttk.Frame(linhas)
        leituras.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        leituras.columnconfigure(1, weight=1)
        ttk.Label(leituras, text="Cadeia:").grid(row=0, column=0, sticky="nw")
        self.lbl_ancora = ttk.Label(leituras, text="", wraplength=520, justify="left")
        self.lbl_ancora.grid(row=0, column=1, sticky="ew")
        self.btn_ancora = ttk.Button(leituras, text="Usar cadeia", width=12,
                                     command=lambda: self._usar_leitura("ancora"))
        self.btn_ancora.grid(row=0, column=2, padx=(6, 0))
        ttk.Label(leituras, text="Motor:").grid(row=1, column=0, sticky="nw")
        self.lbl_motor = ttk.Label(leituras, text="", wraplength=520, justify="left")
        self.lbl_motor.grid(row=1, column=1, sticky="ew")
        self.btn_motor = ttk.Button(leituras, text="Usar motor", width=12,
                                    command=lambda: self._usar_leitura("motor"))
        self.btn_motor.grid(row=1, column=2, padx=(6, 0))

        ttk.Label(panel, text="Valor (edite e salve com Ctrl+Enter):").grid(
            row=4, column=0, sticky="w", pady=(6, 0))
        self.detail = tk.Text(panel, wrap="word", height=3, undo=True)
        self.detail.grid(row=5, column=0, sticky="nsew")
        self.detail.bind("<Control-Return>", lambda _e: (self._edit(), "break")[1])

        # Duas fileiras: a da decisão sobre o item e a da navegação, com a
        # exportação à direita. Numa só, a oitava não cabia em 1180 px.
        buttons = ttk.Frame(panel)
        buttons.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        navegacao = ttk.Frame(panel)
        navegacao.grid(row=7, column=0, sticky="ew", pady=(4, 0))
        self.botoes: dict[str, ttk.Button] = {}
        for fileira, label, key, command in (
                (buttons, "Aceitar", "A", self._accept),
                (buttons, "Salvar edição", "Ctrl+Enter", self._edit),
                (buttons, "Rejeitar", "R", self._reject),
                (buttons, "Adiar", "D", self._defer),
                (buttons, "Semelhantes", "S", self._batch),
                (navegacao, "Diagrama", "G", self._diagrama),
                (navegacao, "Próximo", "N", self._next),
                (navegacao, "Desfazer", "Ctrl+Z", self._undo)):
            botao = ttk.Button(fileira, text=f"{label} [{key}]", command=command)
            botao.pack(side="left", padx=2)
            self.botoes[label] = botao
        if self.ao_exportar is not None:
            self.btn_exportar = ttk.Button(navegacao, text="Exportar com as correções…",
                                           command=self._exportar)
            self.btn_exportar.pack(side="right", padx=2)
            if self.aviso_da_exportacao:
                self.btn_exportar.state(["disabled"])
                self.lbl_exportacao = ttk.Label(navegacao, text=self.aviso_da_exportacao,
                                                foreground="#8a5a00")
                self.lbl_exportacao.pack(side="right", padx=6)
        for key, command in (("a", self._accept), ("r", self._reject),
                             ("d", self._defer), ("s", self._batch),
                             ("g", self._diagrama), ("n", self._next),
                             ("space", self._next)):
            self.bind(f"<{key}>", lambda _event, callback=command: self._atalho(callback))
        self.bind("<Control-z>", lambda _event: self._undo())
        self.bind("<Escape>", lambda _event: self.destroy())

    # ------------------------------------------------------------------
    # A fila
    # ------------------------------------------------------------------

    def _atalho(self, callback) -> None:
        """A tecla solta só vale fora dos campos de texto: com o foco no
        valor, `a` é a letra `a`."""
        foco = self.focus_get()
        if isinstance(foco, (tk.Text, tk.Entry, ttk.Entry, ttk.Spinbox, ttk.Combobox)):
            return
        callback()

    def _limite(self) -> Optional[int]:
        try:
            limite = int(self.var_limite.get() or 0)
        except ValueError:
            limite = 0
        return limite if limite > 0 else None

    def _fila(self):
        fila = self.session.fila(limite_por_pagina=self._limite())
        pagina = self.var_pagina.get()
        tipo = self.var_tipo.get()
        indice = int(pagina) - 1 if pagina not in ("", TODAS) and pagina.isdigit() else None
        return fila, fila.filter(page_index=indice,
                                 kind=None if tipo in ("", TODOS) else tipo)

    def _refresh(self) -> None:
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        inteira, fila = self._fila()
        self.cb_pagina["values"] = [TODAS] + [str(p + 1) for p in inteira.pages]
        self.cb_tipo["values"] = [TODOS] + list(inteira.kinds)
        if self.var_pagina.get() not in self.cb_pagina["values"]:
            self.var_pagina.set(TODAS)
        if self.var_tipo.get() not in self.cb_tipo["values"]:
            self.var_tipo.set(TODOS)
        self._ids = [item.target_id for item in fila.items]
        self._itens = {item.target_id: item for item in fila.items}
        for item in fila.items:
            self.tree.insert("", "end", iid=item.target_id,
                             values=(TIPOS.get(item.kind, item.kind), item.page_index + 1,
                                     item.severity, ESTADOS.get(item.status, item.status),
                                     item.motivos[0] if item.motivos else ""))
        self.var_contagem.set(f"{len(fila.items)} de {len(inteira.items)} pendente(s)")
        self.botoes["Desfazer"].configure(
            text=f"Desfazer ({self.session.passos_desfaziveis()}) [Ctrl+Z]")
        if selected and selected[0] in self._ids:
            self.tree.selection_set(selected[0])
        elif self._ids:
            self.tree.selection_set(self._ids[0])
        else:
            self._limpar_painel("Fila concluída. Não há itens pendentes.")

    def _selected(self) -> Optional[ReviewItem]:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._itens.get(selection[0])

    def _selecionado_ou_aviso(self) -> Optional[ReviewItem]:
        item = self._selected()
        if item is None:
            messagebox.showinfo("Revisão editorial", "Selecione um item da fila.", parent=self)
        return item

    def _imagem(self, item: ReviewItem) -> Optional[np.ndarray]:
        if self.imagem_da_pagina is None:
            return None
        try:
            return self.imagem_da_pagina(item.page_index)
        except Exception:  # noqa: BLE001 — sem imagem a tela mostra o texto
            return None

    def _mostrar_recorte(self, imagem: Optional[np.ndarray], caixa, *, ampliar: float = 1.0) -> None:
        self._fotos.clear()
        # A largura é a do painel na hora, e não um número fixo: a linha da
        # página de duas colunas cabia, a de coluna única saía cortada.
        largura = max(300, self.lbl_recorte.winfo_width() - 8)
        recorte = (_recortar(imagem, caixa, ampliar=ampliar, largura_maxima=largura)
                   if imagem is not None else None)
        if recorte is None:
            self.lbl_recorte.configure(image="", text=("(sem imagem da página)" if imagem is None
                                                       else "(bloco sem caixa na página)"))
            return
        foto = ImageTk.PhotoImage(recorte)
        self._fotos.append(foto)
        self.lbl_recorte.configure(image=foto, text="")

    def _show_selected(self, _event=None) -> None:
        item = self._selected()
        if item is None:
            return
        self._linha_selecionada = None
        self.summary.configure(
            text=(f"{TIPOS.get(item.kind, item.kind)} · página {item.page_index + 1} · "
                  f"{ESTADOS.get(item.status, item.status)} · confiança {item.confidence:.0%} · "
                  f"impacto {item.severity}"))
        motivos = list(item.motivos)
        self.lbl_motivos.configure(text="\n".join(f"• {m}" for m in motivos) or "sem motivo registrado")
        self._mostrar_recorte(self._imagem(item), item.bbox)
        self.tree_linhas.delete(*self.tree_linhas.get_children())
        for k, linha in enumerate(item.linhas):
            self.tree_linhas.insert(
                "", "end", iid=linha.evidence_id,
                values=(k + 1, linha.texto, "; ".join(linha.motivos)),
                tags=("suspeita",) if linha.suspeita else ())
        self.lbl_ancora.configure(text="")
        self.lbl_motor.configure(text="")
        for botao in (self.btn_ancora, self.btn_motor):
            botao.state(["disabled"])
        self.botoes["Diagrama"].state(["!disabled"] if item.kind == "diagram"
                                      and self.abrir_diagrama is not None else ["disabled"])
        self._set_detail(_texto_do_valor(item))
        primeira = next((linha for linha in item.linhas if linha.suspeita), None)
        if primeira is not None:
            self.tree_linhas.selection_set(primeira.evidence_id)
            self.tree_linhas.see(primeira.evidence_id)

    def _show_line(self, _event=None) -> None:
        item = self._selected()
        selection = self.tree_linhas.selection()
        if item is None or not selection:
            return
        linha = next((cada for cada in item.linhas
                      if cada.evidence_id == selection[0]), None)
        if linha is None:
            return
        self._linha_selecionada = linha
        self.lbl_ancora.configure(text=linha.ancora or "—")
        self.lbl_motor.configure(text=linha.motor or "—")
        self.btn_ancora.state(["!disabled"] if linha.ancora and linha.ancora != linha.texto
                              else ["disabled"])
        self.btn_motor.state(["!disabled"] if linha.motor and linha.motor != linha.texto
                             else ["disabled"])
        self._mostrar_recorte(self._imagem(item), linha.caixa or item.bbox,
                              ampliar=AMPLIACAO_MAXIMA)

    def _limpar_painel(self, texto: str) -> None:
        self.summary.configure(text="")
        self.lbl_motivos.configure(text="")
        self.lbl_recorte.configure(image="", text="")
        self._fotos.clear()
        self.tree_linhas.delete(*self.tree_linhas.get_children())
        self.lbl_ancora.configure(text="")
        self.lbl_motor.configure(text="")
        self._set_detail(texto)

    def _set_detail(self, text: str) -> None:
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.edit_reset()

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------

    def _accept(self) -> None:
        item = self._selecionado_ou_aviso()
        if item:
            self.session.accept(item.target_id)
            self._refresh()

    def _edit(self) -> None:
        item = self._selecionado_ou_aviso()
        if not item:
            return
        texto = self.detail.get("1.0", "end-1c")
        valor = _valor_do_texto(item, texto)
        if valor == item.value:
            # Nada mudou no valor: salvar é aceitar como está.
            self.session.accept(item.target_id)
        else:
            self.session.edit(item.target_id, valor)
        self._refresh()

    def _usar_leitura(self, qual: str) -> None:
        item = self._selected()
        linha = self._linha_selecionada
        if item is None or linha is None:
            return
        novo = linha.ancora if qual == "ancora" else linha.motor
        if not novo:
            return
        try:
            self.session.substituir_linha(item.target_id, linha.evidence_id, novo)
        except ValueError as erro:
            messagebox.showinfo("Revisão editorial", str(erro), parent=self)
            return
        self._refresh()
        # O bloco saiu da fila (virou `reviewed`); quem quiser continuar a
        # mexer nele desfaz ou edita o valor antes de salvar.

    def _reject(self) -> None:
        item = self._selecionado_ou_aviso()
        if item:
            self.session.reject(item.target_id)
            self._refresh()

    def _defer(self) -> None:
        item = self._selecionado_ou_aviso()
        if item:
            self.session.defer(item.target_id)
            self._refresh()

    def _batch(self) -> None:
        """Aceita os itens com o mesmo tipo e os mesmos motivos do
        selecionado — depois de mostrar quantos são e uma amostra."""
        item = self._selecionado_ou_aviso()
        if not item:
            return
        ids = self.session.semelhantes(item.target_id)
        if not ids:
            return
        amostra = [self._itens[i] for i in ids if i in self._itens][:AMOSTRA_DO_LOTE]
        exemplos = "\n".join(
            f"• p. {ex.page_index + 1}: {_texto_do_valor(ex)[:70]!s}" for ex in amostra)
        if not self.confirmar_lote(len(ids), exemplos, item):
            return
        self.session.apply_batch(ids, confirm=True)
        self._refresh()

    def confirmar_lote(self, quantos: int, exemplos: str, item: ReviewItem) -> bool:
        """Costura de teste: a pergunta do lote."""
        return messagebox.askyesno(
            "Aceitar semelhantes",
            f"Aceitar {quantos} item(ns) do tipo «{TIPOS.get(item.kind, item.kind)}» "
            f"com os mesmos motivos?\n\n{exemplos}\n\n"
            "Cada um vira um evento de revisão; Desfazer volta o lote inteiro.",
            parent=self)

    def _diagrama(self) -> None:
        item = self._selecionado_ou_aviso()
        if not item or item.kind != "diagram" or self.abrir_diagrama is None:
            return
        fen = self.abrir_diagrama(item, self._imagem(item))
        if not fen:
            return
        valor = ({**copy.deepcopy(item.value), "fen": fen}
                 if isinstance(item.value, Mapping) else fen)
        if valor == item.value:
            self.session.accept(item.target_id)
        else:
            self.session.edit(item.target_id, valor)
        self._refresh()

    def _next(self) -> None:
        if not self._ids:
            return
        selection = self.tree.selection()
        indice = self._ids.index(selection[0]) + 1 if selection and selection[0] in self._ids else 0
        alvo = self._ids[indice % len(self._ids)]
        self.tree.selection_set(alvo)
        self.tree.see(alvo)

    def _undo(self) -> None:
        try:
            self.session.undo()
        except ValueError as error:
            messagebox.showinfo("Revisão editorial", str(error), parent=self)
        self._refresh()

    def _exportar(self) -> None:
        if self.aviso_da_exportacao:
            messagebox.showinfo("Exportar com as correções", self.aviso_da_exportacao, parent=self)
            return
        if self.ao_exportar is not None:
            self.ao_exportar(self.session.document)

    def mostrar(self) -> "DialogoRevisaoEditorial":
        self.transient(self.master)
        self.grab_set()
        return self


EditorialReviewDialog = DialogoRevisaoEditorial
