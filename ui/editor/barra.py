"""
As barras de ferramentas da janela de edição — arquivo, formatação (modo texto),
código (modo código) e a barra de xadrez, **vazia** até a ED-05 — e o `AnelDeFoco`
que dá foco visível aos widgets `ttk` (ED-02; SPEC_EDITOR §7.1, §13.2).

## Botões reais

Cada botão é um `ttk.Button` com `text` (o leitor de tela lê), uma dica ao passar o
mouse e o eco na barra de status ao receber o foco — é o que a §13.2 pede de um
alvo. Nenhum botão sabe fazer nada: chama `janela.executar(nome)`, o mesmo caminho
do menu e do atalho, e por isso o teste que troca `comandos[nome]` por um espião
vale para os três.

## O anel de foco

O tema `vista` do `ttk` não desenha `focuscolor`; um `ttk.Button` focado é
indistinguível do vizinho. `AnelDeFoco` embrulha o widget num `tk.Frame` cujo
`highlightthickness` vai a 2 no `<FocusIn>` e a 0 no `<FocusOut>` (AC-ED02-12).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Sequence

COR_DO_ANEL = "#1a5fb4"
ESPESSURA_DO_ANEL = 2


class AnelDeFoco(tk.Frame):
    """`AnelDeFoco(master, lambda pai: ttk.Button(pai, …))` → o frame; o widget fica em `.widget`."""

    def __init__(self, master: tk.Misc, criar: Callable[[tk.Misc], tk.Misc], cor: str = COR_DO_ANEL,
                 espessura: int = ESPESSURA_DO_ANEL, **kw: Any):
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("highlightbackground", cor)
        kw.setdefault("highlightcolor", cor)
        super().__init__(master, **kw)
        self.espessura = int(espessura)
        self.widget = criar(self)
        self.widget.pack(fill="both", expand=True)
        self.widget.bind("<FocusIn>", self._entrou, add="+")
        self.widget.bind("<FocusOut>", self._saiu, add="+")

    def _entrou(self, _evento: Any = None) -> None:
        self.configure(highlightthickness=self.espessura)

    def _saiu(self, _evento: Any = None) -> None:
        self.configure(highlightthickness=0)


class Dica:
    """A dica de um widget: um `Toplevel` sem moldura, ao passar o mouse; some ao sair."""

    def __init__(self, widget: tk.Misc, texto: str):
        self.widget = widget
        self.texto = texto
        self._janela: tk.Toplevel | None = None
        widget.bind("<Enter>", self.mostrar, add="+")
        widget.bind("<Leave>", self.esconder, add="+")
        widget.bind("<ButtonPress>", self.esconder, add="+")

    def mostrar(self, _evento: Any = None) -> None:
        self.esconder()
        if not self.texto:
            return
        try:
            janela = tk.Toplevel(self.widget)
            janela.overrideredirect(True)
            rotulo = tk.Label(janela, text=self.texto, justify="left", relief="solid", borderwidth=1,
                              background="#ffffe0", foreground="#1f1f1f", padx=4, pady=2)
            rotulo.pack()
            x, y = self.widget.winfo_rootx(), self.widget.winfo_rooty() + self.widget.winfo_height() + 2
            janela.geometry(f"+{x}+{y}")
            self._janela = janela
        except tk.TclError:
            self._janela = None

    def esconder(self, _evento: Any = None) -> None:
        if self._janela is not None:
            try:
                self._janela.destroy()
            except tk.TclError:
                pass
            self._janela = None


#: (comando, texto do botão, dica)
BOTOES_DE_ARQUIVO = (
    ("novo", "Novo", "Novo livro (Ctrl+N)"),
    ("abrir", "Abrir", "Abrir… (Ctrl+O)"),
    ("salvar", "Salvar", "Salvar (Ctrl+S)"),
    ("-", "", ""),
    ("desfazer", "Desfazer", "Desfazer (Ctrl+Z)"),
    ("refazer", "Refazer", "Refazer (Ctrl+Y)"),
    ("-", "", ""),
    ("modo_texto", "Texto", "Modo texto: o livro como se lê (F11 alterna)"),
    ("modo_codigo", "Código", "Modo código: só o XHTML (F11 alterna)"),
    ("modo_dividido", "Dividido", "Código com a prévia ao lado (Ctrl+F11; F12 liga/desliga a prévia)"),
)
#: Os botões da vista da aba: um só fica marcado, o da vista atual (ED-15).
VISTAS = {"modo_texto": "texto", "modo_codigo": "codigo", "modo_dividido": "dividido"}
#: Os botões de alternância da formatação (ED-16b): ficam marcados conforme o cursor, cada um na sua letra.
ALTERNAVEIS = {"negrito": ("bold",), "italico": ("italic",), "sublinhado": ("underline",),
               "tachado": ("overstrike",)}
BOTOES_DE_FORMATACAO = (
    ("negrito", "N", "Negrito (Ctrl+B)"),
    ("italico", "I", "Itálico (Ctrl+I)"),
    ("sublinhado", "S", "Sublinhado (Ctrl+U)"),
    ("tachado", "T", "Tachado"),
    ("-", "", ""),
    ("alinhar_esquerda", "Esq", "Alinhar à esquerda (Ctrl+L)"),
    ("alinhar_centro", "Centro", "Centralizar (Ctrl+E)"),
    ("alinhar_direita", "Dir", "Alinhar à direita (Ctrl+R)"),
    ("justificar", "Just", "Justificar (Ctrl+J)"),
    ("-", "", ""),
    ("marcadores", "• Lista", "Marcadores (Ctrl+Shift+L)"),
    ("numeracao", "1. Lista", "Numeração (Ctrl+Shift+O)"),
    ("-", "", ""),
    ("fonte", "Fonte…", "Fonte… (Ctrl+D)"),
    ("limpar_caractere", "Limpar", "Limpar formatação de caractere (Ctrl+Space)"),
)
BOTOES_DE_CODIGO = (
    ("bem_formado", "Bem-formado", "Verificar bem-formado (Alt+F7)"),
    ("consertar", "Consertar", "Consertar HTML (Alt+F8)"),
    ("reformatar", "Reformatar", "Reformatar XHTML (Ctrl+Shift+I)"),
    ("comentar", "Comentar", "Comentar/descomentar (Ctrl+/)"),
    ("-", "", ""),
    ("autocompletar", "Completar", "Autocompletar (Ctrl+Space)"),
    ("inserir_link", "Link…", "Inserir link (Ctrl+K)"),
    ("dividir_capitulo", "Dividir", "Dividir capítulo no cursor (Ctrl+Enter)"),
    ("clipes", "Clipes", "Clipes… (Ctrl+Shift+J)"),
)


class Barra(ttk.Frame):
    """Uma barra de botões; `janela` dá `executar(nome)` e `status(texto)`."""

    def __init__(self, master: tk.Misc, janela: Any, botoes: Sequence[tuple[str, str, str]], nome: str = "",
                 **kw: Any):
        super().__init__(master, **kw)
        self.janela = janela
        self.nome = nome
        self.botoes: dict[str, ttk.Button] = {}
        self.aneis: dict[str, AnelDeFoco] = {}
        self.estilo_combo: ttk.Combobox | None = None
        self.vista: tk.StringVar | None = None
        self.formato: dict[str, tk.BooleanVar] = {}
        for comando, texto, dica in botoes:
            if comando == "-":
                ttk.Separator(self, orient="vertical").pack(side="left", fill="y", padx=4, pady=2)
                continue
            self.adicionar(comando, texto, dica)

    def adicionar(self, comando: str, texto: str, dica: str = "") -> ttk.Button:
        if comando in ALTERNAVEIS:
            self.formato[comando] = tk.BooleanVar(self, value=False)
            estilo = _estilo_da_letra(self, comando)
            anel = AnelDeFoco(self, lambda pai, c=comando, t=texto: ttk.Checkbutton(
                pai, text=t, command=lambda: self._alternar_formato(c), variable=self.formato[c],
                style=estilo, width=max(3, len(t) + 2)))
        elif comando in VISTAS:
            if self.vista is None:
                self.vista = tk.StringVar(self, value="")
            anel = AnelDeFoco(self, lambda pai, c=comando, t=texto: ttk.Radiobutton(
                pai, text=t, command=lambda: self._escolher_vista(c), variable=self.vista, value=VISTAS[c],
                style="Toolbutton", width=max(3, len(t) + 2)))
        else:
            anel = AnelDeFoco(self, lambda pai, c=comando, t=texto: ttk.Button(
                pai, text=t, command=lambda: self.janela.executar(c), width=max(3, len(t) + 2)))
        anel.pack(side="left", padx=1, pady=2)
        botao = anel.widget
        Dica(botao, dica)
        botao.bind("<FocusIn>", lambda e, d=dica or texto: self.janela.status(d), add="+")
        self.botoes[comando] = botao
        self.aneis[comando] = anel
        return botao

    def atualizar(self, comandos: dict[str, Any], modo: str, modos_do_comando: dict[str, tuple[str, ...]]) -> None:
        for comando, botao in self.botoes.items():
            existe = comando in comandos and modo in modos_do_comando.get(comando, ("texto", "codigo"))
            botao.state(["!disabled"] if existe else ["disabled"])
        self.marcar_vista()

    def marcar_vista(self) -> None:
        """O botão da vista da aba ativa fica marcado (a janela diz qual por `vista_atual()`)."""
        if self.vista is None:
            return
        operacoes = getattr(self.janela, "operacoes", None)
        atual = operacoes.vista_atual() if operacoes is not None else ""
        self.vista.set(atual)

    def marcar_formato(self, estado: dict[str, bool] | None) -> None:
        """Os botões N/I/S/T mostram o formato do cursor (`None`: nenhum ligado — o modo código)."""
        for nome, variavel in self.formato.items():
            variavel.set(bool((estado or {}).get(nome, False)))

    def _alternar_formato(self, comando: str) -> None:
        # O `Checkbutton` já trocou a marca; quem manda é o editor, que devolve o estado real.
        try:
            self.janela.executar(comando)
        finally:
            atualizar = getattr(self.janela, "_atualizar_formato", None)
            if atualizar is not None:
                atualizar()

    def _escolher_vista(self, comando: str) -> None:
        # O `Radiobutton` já marcou; se a troca não aconteceu (XHTML mal-formado, sem aba), volta à real.
        try:
            self.janela.executar(comando)
        finally:
            self.marcar_vista()

    def primeiro(self) -> ttk.Button | None:
        for botao in self.botoes.values():
            if "disabled" not in botao.state():
                return botao
        return None


def _estilo_da_letra(widget: tk.Misc, comando: str) -> str:
    """O estilo `ttk` do botão de alternância: o *Toolbutton* com a letra em negrito, itálico, etc."""
    import tkinter.font as tkfont

    nome = f"{comando.capitalize()}.Toolbutton"
    estilo = ttk.Style(widget)
    if not estilo.configure(nome):
        base = tkfont.nametofont("TkDefaultFont").actual()
        fonte = (base["family"], base["size"], *ALTERNAVEIS[comando])
        estilo.configure(nome, font=fonte, anchor="center")
    return nome


class BarraDeXadrez(Barra):
    """Vazia na ED-02: a ED-05 a preenche (figurinas brancas, NAGs, Diagrama, Posição, Validar)."""

    def __init__(self, master: tk.Misc, janela: Any, **kw: Any):
        super().__init__(master, janela, (), "xadrez", **kw)
        self.aviso = ttk.Label(self, text="Barra de xadrez — preenchida na ED-05", foreground="#555555")
        self.aviso.pack(side="left", padx=6, pady=2)


__all__ = ["AnelDeFoco", "Dica", "Barra", "BarraDeXadrez", "BOTOES_DE_ARQUIVO", "BOTOES_DE_FORMATACAO", "VISTAS",
           "ALTERNAVEIS",
           "BOTOES_DE_CODIGO"]
