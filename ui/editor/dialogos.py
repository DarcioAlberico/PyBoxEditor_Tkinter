"""
As caixas da janela de edição, atrás de um ponto de injeção só (ED-02; SPEC_EDITOR
§13.3, §14).

`Caixas` é o que a janela chama para perguntar, avisar, pedir um caminho ou um
formulário. O teste troca o método que quiser por um espião ou por uma resposta
pronta (`janela.caixas.pergunta = lambda *a, **k: True`) — é a "resposta injetável"
da guarda ao fechar (AC-ED02-6) e o que deixa a suíte correr sem uma caixa modal.

As duas camadas de erro da §13.3: `entrada` é a caixa simples, com o que fazer
(um `ValueError` de comando); `falha` é a `DialogoDeFalha`, com o traceback
dobrado e o botão "Copiar", rotulada como defeito do programa (qualquer outra
exceção). As caixas com formulário (`DialogoDeFormulario`, `DialogoDeLista`,
`DialogoDeTexto`, `DialogoDeParagrafo`) se constroem sem `mostrar()` para o teste
preencher as variáveis e chamar `confirmar()`.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Any, Callable, Sequence

TITULO = "Editor de livro"
TIPOS_DE_LIVRO = (("Livro EPUB", "*.epub"), ("Todos os arquivos", "*.*"))


class _Dialogo:
    """A base das caixas construíveis sem mostrar: `top`, `confirmar`, `cancelar`, `mostrar`."""

    def __init__(self, master: tk.Misc, titulo: str):
        self.master = master
        self.titulo = titulo
        self.top: tk.Toplevel | None = None
        self.resultado: Any = None

    def _abrir(self, redimensionavel: tuple[bool, bool] = (False, False)) -> tk.Toplevel:
        top = tk.Toplevel(self.master)
        top.title(self.titulo)
        try:
            top.transient(self.master.winfo_toplevel())
        except tk.TclError:
            pass
        top.resizable(*redimensionavel)
        top.protocol("WM_DELETE_WINDOW", self.cancelar)
        top.bind("<Escape>", lambda e: self.cancelar())
        self.top = top
        return top

    def _construir(self) -> tk.Toplevel:      # pragma: no cover — cada caixa faz o seu
        raise NotImplementedError

    def construir(self) -> tk.Toplevel:
        if self.top is None:
            self._construir()
        assert self.top is not None
        return self.top

    def confirmar(self) -> Any:
        self.resultado = self._ler()
        self._fechar()
        return self.resultado

    def _ler(self) -> Any:
        return True

    def cancelar(self) -> None:
        self.resultado = None
        self._fechar()

    def _fechar(self) -> None:
        if self.top is not None:
            try:
                self.top.grab_release()
                self.top.destroy()
            except tk.TclError:
                pass
            self.top = None

    def mostrar(self) -> Any:
        top = self.construir()
        try:
            top.grab_set()
        except tk.TclError:
            pass
        self._foco_inicial()
        top.wait_window()
        return self.resultado

    def _foco_inicial(self) -> None:
        if self.top is not None:
            self.top.focus_set()

    def _botoes(self, pai: tk.Misc, ok: str = "OK", cancelar: str = "Cancelar") -> ttk.Frame:
        botoes = ttk.Frame(pai)
        self.botao_ok = ttk.Button(botoes, text=ok, command=self.confirmar, default="active")
        self.botao_ok.pack(side="right", padx=(6, 0))
        if cancelar:
            ttk.Button(botoes, text=cancelar, command=self.cancelar).pack(side="right")
        assert self.top is not None
        self.top.bind("<Return>", lambda e: self.confirmar())
        return botoes


class DialogoDeFormulario(_Dialogo):
    """Campos `(chave, rótulo, inicial)` → `dict` com os valores; `opcoes` faz `Combobox` de um campo."""

    def __init__(self, master: tk.Misc, titulo: str, campos: Sequence[tuple[str, str, str]],
                 opcoes: dict[str, Sequence[str]] | None = None, texto: str = ""):
        super().__init__(master, titulo)
        self.campos = list(campos)
        self.opcoes = dict(opcoes or {})
        self.texto = texto
        self.variaveis: dict[str, tk.StringVar] = {}
        self.entradas: dict[str, tk.Widget] = {}

    def _construir(self) -> tk.Toplevel:
        top = self._abrir()
        corpo = ttk.Frame(top, padding=12)
        corpo.grid(row=0, column=0, sticky="nsew")
        linha = 0
        if self.texto:
            ttk.Label(corpo, text=self.texto, wraplength=420, justify="left").grid(
                row=linha, column=0, columnspan=2, sticky="w", pady=(0, 8))
            linha += 1
        for chave, rotulo, inicial in self.campos:
            variavel = tk.StringVar(master=top, value=str(inicial))
            self.variaveis[chave] = variavel
            ttk.Label(corpo, text=rotulo).grid(row=linha, column=0, sticky="w", padx=(0, 8), pady=2)
            if chave in self.opcoes:
                entrada: tk.Widget = ttk.Combobox(corpo, textvariable=variavel, values=list(self.opcoes[chave]),
                                                  width=36)
            else:
                entrada = ttk.Entry(corpo, textvariable=variavel, width=40)
            entrada.grid(row=linha, column=1, sticky="ew", pady=2)
            self.entradas[chave] = entrada
            linha += 1
        corpo.columnconfigure(1, weight=1)
        self._botoes(corpo).grid(row=linha, column=0, columnspan=2, sticky="e", pady=(12, 0))
        return top

    def _ler(self) -> dict[str, str]:
        return {chave: var.get() for chave, var in self.variaveis.items()}

    def _foco_inicial(self) -> None:
        if self.campos:
            self.entradas[self.campos[0][0]].focus_set()


class DialogoDeLista(_Dialogo):
    """Escolher um item de `opcoes` (rótulos); o resultado é o índice."""

    def __init__(self, master: tk.Misc, titulo: str, rotulo: str, opcoes: Sequence[str], ok: str = "OK"):
        super().__init__(master, titulo)
        self.rotulo = rotulo
        self.opcoes = list(opcoes)
        self.ok = ok
        self.lista: tk.Listbox | None = None

    def _construir(self) -> tk.Toplevel:
        top = self._abrir((True, True))
        corpo = ttk.Frame(top, padding=12)
        corpo.grid(row=0, column=0, sticky="nsew")
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        ttk.Label(corpo, text=self.rotulo).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.lista = tk.Listbox(corpo, height=min(12, max(4, len(self.opcoes))), width=60, exportselection=False,
                                highlightthickness=2, activestyle="dotbox")
        for opcao in self.opcoes:
            self.lista.insert("end", opcao)
        if self.opcoes:
            self.lista.selection_set(0)
            self.lista.activate(0)
        barra = ttk.Scrollbar(corpo, orient="vertical", command=self.lista.yview)
        self.lista.configure(yscrollcommand=barra.set)
        self.lista.grid(row=1, column=0, sticky="nsew")
        barra.grid(row=1, column=1, sticky="ns")
        corpo.rowconfigure(1, weight=1)
        corpo.columnconfigure(0, weight=1)
        self.lista.bind("<Double-Button-1>", lambda e: self.confirmar())
        self._botoes(corpo, self.ok).grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        return top

    def escolher(self, indice: int) -> None:
        assert self.lista is not None
        self.lista.selection_clear(0, "end")
        self.lista.selection_set(indice)
        self.lista.activate(indice)

    def _ler(self) -> int | None:
        if self.lista is None:
            return None
        selecao = self.lista.curselection()
        return int(selecao[0]) if selecao else None

    def _foco_inicial(self) -> None:
        if self.lista is not None:
            self.lista.focus_set()


class DialogoDeTexto(_Dialogo):
    """Um texto longo, percorrível, só de leitura (atalhos, dialeto, diferença de um ponto de verificação)."""

    def __init__(self, master: tk.Misc, titulo: str, texto: str, monoespaco: bool = True):
        super().__init__(master, titulo)
        self.texto = texto
        self.monoespaco = monoespaco
        self.caixa: tk.Text | None = None

    def _construir(self) -> tk.Toplevel:
        top = self._abrir((True, True))
        corpo = ttk.Frame(top, padding=8)
        corpo.grid(row=0, column=0, sticky="nsew")
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        fonte = ("Consolas", 10) if self.monoespaco else ("Segoe UI", 10)
        self.caixa = tk.Text(corpo, width=96, height=32, wrap="none" if self.monoespaco else "word", font=fonte,
                             highlightthickness=2, exportselection=False)
        self.caixa.insert("1.0", self.texto)
        self.caixa.configure(state="disabled")
        barra_v = ttk.Scrollbar(corpo, orient="vertical", command=self.caixa.yview)
        barra_h = ttk.Scrollbar(corpo, orient="horizontal", command=self.caixa.xview)
        self.caixa.configure(yscrollcommand=barra_v.set, xscrollcommand=barra_h.set)
        self.caixa.grid(row=0, column=0, sticky="nsew")
        barra_v.grid(row=0, column=1, sticky="ns")
        barra_h.grid(row=1, column=0, sticky="ew")
        corpo.rowconfigure(0, weight=1)
        corpo.columnconfigure(0, weight=1)
        botoes = ttk.Frame(corpo)
        botoes.grid(row=2, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(botoes, text="Copiar", command=self.copiar).pack(side="right", padx=(6, 0))
        self.botao_ok = ttk.Button(botoes, text="Fechar", command=self.confirmar, default="active")
        self.botao_ok.pack(side="right")
        top.bind("<Return>", lambda e: self.confirmar())
        return top

    def copiar(self) -> None:
        try:
            self.master.clipboard_clear()
            self.master.clipboard_append(self.texto)
        except tk.TclError:
            pass

    def _foco_inicial(self) -> None:
        if self.caixa is not None:
            self.caixa.focus_set()


class DialogoDeFalha(_Dialogo):
    """A falha interna (§13.3): a mensagem, o traceback dobrado em "Detalhes" e "Copiar"."""

    def __init__(self, master: tk.Misc, mensagem: str, detalhe: str, titulo: str = "Defeito do programa"):
        super().__init__(master, titulo)
        self.mensagem = mensagem
        self.detalhe = detalhe
        self.detalhes_abertos = False
        self.caixa: tk.Text | None = None

    def _construir(self) -> tk.Toplevel:
        top = self._abrir((True, True))
        corpo = ttk.Frame(top, padding=12)
        corpo.grid(row=0, column=0, sticky="nsew")
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        ttk.Label(corpo, text="Isto é um defeito do programa, não do livro nem do que você fez.",
                  wraplength=520, justify="left").grid(row=0, column=0, sticky="w")
        ttk.Label(corpo, text=self.mensagem, wraplength=520, justify="left", foreground="#b00020").grid(
            row=1, column=0, sticky="w", pady=(6, 6))
        self.botao_detalhes = ttk.Button(corpo, text="Detalhes ▸", command=self.alternar_detalhes)
        self.botao_detalhes.grid(row=2, column=0, sticky="w")
        self.caixa = tk.Text(corpo, width=80, height=14, wrap="none", font=("Consolas", 9), highlightthickness=2)
        self.caixa.insert("1.0", self.detalhe)
        self.caixa.configure(state="disabled")
        corpo.columnconfigure(0, weight=1)
        botoes = ttk.Frame(corpo)
        botoes.grid(row=4, column=0, sticky="e", pady=(12, 0))
        self.botao_ok = ttk.Button(botoes, text="Fechar", command=self.confirmar, default="active")
        self.botao_ok.pack(side="right", padx=(6, 0))
        ttk.Button(botoes, text="Copiar", command=self.copiar).pack(side="right")
        top.bind("<Return>", lambda e: self.confirmar())
        return top

    def alternar_detalhes(self) -> bool:
        assert self.caixa is not None
        self.detalhes_abertos = not self.detalhes_abertos
        if self.detalhes_abertos:
            self.caixa.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
            self.botao_detalhes.configure(text="Detalhes ▾")
        else:
            self.caixa.grid_forget()
            self.botao_detalhes.configure(text="Detalhes ▸")
        return self.detalhes_abertos

    def copiar(self) -> str:
        texto = f"{self.mensagem}\n\n{self.detalhe}"
        try:
            self.master.clipboard_clear()
            self.master.clipboard_append(texto)
        except tk.TclError:
            pass
        return texto

    def _foco_inicial(self) -> None:
        self.botao_ok.focus_set()


ALINHAMENTOS = (("(como está)", ""), ("Esquerda", "esquerda"), ("Centro", "centro"), ("Direita", "direita"),
                ("Justificado", "justificado"))
ENTRELINHAS = (("(como está)", ""), ("Simples", "1"), ("1,5", "1.5"), ("Dupla", "2"))


class DialogoDeParagrafo(_Dialogo):
    """"Parágrafo…": alinhamento, recuos, espaço antes e depois, entrelinha — só o que mudou."""

    def __init__(self, master: tk.Misc, atual: dict[str, Any] | None = None):
        super().__init__(master, "Parágrafo")
        self.atual = dict(atual or {})
        self.variaveis: dict[str, tk.StringVar] = {}

    def _construir(self) -> tk.Toplevel:
        top = self._abrir()
        corpo = ttk.Frame(top, padding=12)
        corpo.grid(row=0, column=0, sticky="nsew")
        v = self.variaveis
        v["alinhamento"] = tk.StringVar(master=top, value=str(self.atual.get("alinhamento") or ""))
        v["entrelinha"] = tk.StringVar(master=top, value=_numero(self.atual.get("entrelinha")))
        for chave in ("recuo_primeira_em", "recuo_esquerda_em", "recuo_direita_em", "antes_em", "depois_em"):
            v[chave] = tk.StringVar(master=top, value=_numero(self.atual.get(chave)))
        ttk.Label(corpo, text="Alinhamento:").grid(row=0, column=0, sticky="w")
        self.caixa_alinhamento = ttk.Combobox(corpo, textvariable=v["alinhamento"], state="readonly", width=16,
                                              values=[valor for _r, valor in ALINHAMENTOS])
        self.caixa_alinhamento.grid(row=0, column=1, sticky="w", pady=2)
        rotulos = (("recuo_primeira_em", "Recuo da primeira linha (em):"),
                   ("recuo_esquerda_em", "Recuo à esquerda (em):"), ("recuo_direita_em", "Recuo à direita (em):"),
                   ("antes_em", "Espaço antes (em):"), ("depois_em", "Espaço depois (em):"))
        for k, (chave, rotulo) in enumerate(rotulos, start=1):
            ttk.Label(corpo, text=rotulo).grid(row=k, column=0, sticky="w")
            ttk.Entry(corpo, textvariable=v[chave], width=8).grid(row=k, column=1, sticky="w", pady=2)
        ttk.Label(corpo, text="Entrelinha:").grid(row=6, column=0, sticky="w")
        ttk.Combobox(corpo, textvariable=v["entrelinha"], width=8, values=[valor for _r, valor in ENTRELINHAS]).grid(
            row=6, column=1, sticky="w", pady=2)
        ttk.Label(corpo, text="Vazio = como está. Recuo e espaço em em (1 em = o corpo da fonte).",
                  foreground="#555555", wraplength=360, justify="left").grid(row=7, column=0, columnspan=2,
                                                                              sticky="w", pady=(8, 0))
        self._botoes(corpo).grid(row=8, column=0, columnspan=2, sticky="e", pady=(12, 0))
        return top

    def _ler(self) -> dict[str, Any]:
        """Só o que difere do `atual`, no vocabulário de `TextoRico.paragrafo`."""
        saida: dict[str, Any] = {}
        v = self.variaveis
        alinhamento = v["alinhamento"].get()
        if alinhamento != (self.atual.get("alinhamento") or ""):
            saida["alinhamento"] = alinhamento
        for chave in ("recuo_primeira_em", "recuo_esquerda_em", "recuo_direita_em", "antes_em", "depois_em",
                      "entrelinha"):
            texto = v[chave].get().strip().replace(",", ".")
            if not texto:
                continue
            try:
                valor = float(texto)
            except ValueError as erro:
                raise ValueError(f"{chave}: {texto!r} não é um número") from erro
            if valor != self.atual.get(chave):
                saida[chave] = valor
        return saida

    def _foco_inicial(self) -> None:
        self.caixa_alinhamento.focus_set()


def _numero(valor: Any) -> str:
    if valor in (None, ""):
        return ""
    return f"{float(valor):g}"


class Caixas:
    """O ponto de injeção: a janela chama estes métodos; o teste os troca."""

    def __init__(self, master: tk.Misc):
        self.master = master

    # -- avisos ----------------------------------------------------------------

    def entrada(self, mensagem: str, titulo: str = TITULO) -> None:
        messagebox.showwarning(titulo, mensagem, parent=self.master)

    def informar(self, mensagem: str, titulo: str = TITULO) -> None:
        messagebox.showinfo(titulo, mensagem, parent=self.master)

    def falha(self, mensagem: str, detalhe: str) -> None:
        DialogoDeFalha(self.master, mensagem, detalhe).mostrar()

    def pergunta(self, mensagem: str, titulo: str = TITULO, cancelar: bool = True) -> bool | None:
        """Sim → `True`, Não → `False`, Cancelar (ou fechar) → `None`."""
        if cancelar:
            return messagebox.askyesnocancel(titulo, mensagem, parent=self.master)
        return bool(messagebox.askyesno(titulo, mensagem, parent=self.master))

    # -- arquivos --------------------------------------------------------------

    def abrir(self, tipos: Sequence[tuple[str, str]] = TIPOS_DE_LIVRO, diretorio: str = "",
              titulo: str = "Abrir livro") -> str:
        return filedialog.askopenfilename(title=titulo, filetypes=list(tipos), initialdir=diretorio or None,
                                          parent=self.master) or ""

    def salvar_como(self, sugestao: str = "", tipos: Sequence[tuple[str, str]] = TIPOS_DE_LIVRO,
                    diretorio: str = "", extensao: str = ".epub", titulo: str = "Salvar livro como") -> str:
        return filedialog.asksaveasfilename(title=titulo, filetypes=list(tipos), defaultextension=extensao,
                                            initialfile=os.path.basename(sugestao) if sugestao else None,
                                            initialdir=diretorio or (os.path.dirname(sugestao) if sugestao else None),
                                            parent=self.master) or ""

    # -- formulários -----------------------------------------------------------

    def formulario(self, titulo: str, campos: Sequence[tuple[str, str, str]],
                   opcoes: dict[str, Sequence[str]] | None = None, texto: str = "") -> dict[str, str] | None:
        return DialogoDeFormulario(self.master, titulo, campos, opcoes, texto).mostrar()

    def pedir_texto(self, titulo: str, rotulo: str, inicial: str = "") -> str | None:
        resposta = self.formulario(titulo, [("valor", rotulo, inicial)])
        return None if resposta is None else resposta["valor"]

    def pedir_inteiro(self, titulo: str, rotulo: str, inicial: int = 1, minimo: int = 1,
                      maximo: int | None = None) -> int | None:
        texto = self.pedir_texto(titulo, rotulo, str(inicial))
        if texto is None:
            return None
        try:
            valor = int(texto.strip())
        except ValueError:
            raise ValueError(f"{texto!r} não é um número inteiro") from None
        if valor < minimo or (maximo is not None and valor > maximo):
            fim = f" e {maximo}" if maximo is not None else ""
            raise ValueError(f"o valor precisa estar entre {minimo}{fim}")
        return valor

    def escolher(self, titulo: str, rotulo: str, opcoes: Sequence[str], ok: str = "OK") -> int | None:
        if not opcoes:
            return None
        return DialogoDeLista(self.master, titulo, rotulo, opcoes, ok).mostrar()

    def texto(self, titulo: str, conteudo: str, monoespaco: bool = True) -> None:
        DialogoDeTexto(self.master, titulo, conteudo, monoespaco).mostrar()

    def paragrafo(self, atual: dict[str, Any]) -> dict[str, Any] | None:
        return DialogoDeParagrafo(self.master, atual).mostrar()

    def cor(self, inicial: str = "") -> str:
        escolha = colorchooser.askcolor(color=inicial or None, parent=self.master)
        return (escolha[1] or "") if escolha else ""

    def fonte(self, atual: dict[str, Any]) -> dict[str, Any] | None:
        from ui.editor.fonte import DialogoDeFonte

        return DialogoDeFonte(self.master, atual).mostrar()

    def conclusao(self, titulo: str, linhas: Sequence[str], caminho: str,
                  abrir_no_editor: Callable[[str], Any] | None = None) -> str | None:
        from ui.dialogo_de_conclusao import DialogoDeConclusao

        return DialogoDeConclusao(self.master, titulo, linhas, caminho, abrir_no_editor=abrir_no_editor).mostrar()


__all__ = ["Caixas", "DialogoDeFormulario", "DialogoDeLista", "DialogoDeTexto", "DialogoDeFalha",
           "DialogoDeParagrafo", "TIPOS_DE_LIVRO", "TITULO"]
