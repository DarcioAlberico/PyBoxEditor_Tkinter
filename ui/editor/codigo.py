"""
`EditorDeCodigo`: o `tk.Text` do modo código — realce, números de linha, linha atual,
casamento de tags, auto-indentação, `</` que completa, `Ctrl+Space`, comentar,
reformatar, envolver, inserir link/id/imagem, bem-formado, consertar, dividir no
cursor, ir ao alvo e voltar, zoom, desfazer próprio (ED-07; SPEC_EDITOR §9.1–§9.3,
§13.2, DEC-03 "Ligações de teclado").

## Como o widget sabe que o texto mudou

O `tk.Text` não avisa quem o edita por dentro — `tk::TextInsert`, o colar, o
arrastar. O truque dos editores em Tkinter é renomear o comando Tcl do widget e pôr
um *proxy* Python no lugar: toda chamada (`insert`, `delete`, `yview`, `mark set
insert`…) passa por `_proxy`, que executa o comando original e, depois, faz o que
tem de fazer — re-tokenizar da linha alterada (`realce.Realce`), pintar a faixa
visível, redesenhar os números, registrar a operação na pilha de desfazer, marcar
sujo. É por isso que o `Text` nasce com `undo=False`: o desfazer é próprio, por
operação, e não guarda cópias do documento.

## Ligações de teclado

Toda ligação entra na bindtag `EditorAtalhos`, posta **antes** de `Text` na lista
de bindtags, e todo handler devolve `"break"` (DEC-03): é o que impede o `Ctrl+I`
da classe `Text` de inserir um tabulador quando o que se quer é `<em>`. O que
precisa de diálogo (ir para linha, link, clipes, dividir) não abre diálogo aqui: o
widget gera um evento virtual (`<<IrParaLinha>>`, `<<InserirLink>>`, `<<Clipes>>`,
`<<DividirNoCursor>>`) e a janela (ED-02) decide; os comandos com argumentos
(`ir_para_linha(n)`, `inserir_link(href, texto)`) são os que os testes chamam.

## Testes sem teclado

A janela dos testes é `withdraw`n e não recebe teclas (§14): tudo aqui é chamável
por método — `comentar()`, `envolver("strong")`, `sugerir()` —, e `sincronizar()`
faz na hora o que o `after` faria no laço de eventos.
"""

from __future__ import annotations

import re
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any, Callable, Sequence

from core.editor import consertar as consertar_mod
from core.editor import css_minima, xhtml
from core.editor.xhtml import ErroDeXhtml
from ui.editor import realce as realce_mod

BINDTAG = "EditorAtalhos"
TAGS_DE_TELA = ("linha_atual", "casamento", "erro")
CORPO_MINIMO, CORPO_MAXIMO = 6, 40
COALESCENCIA_S = 0.7

#: Elementos do XHTML que o `</` e o `Ctrl+Space` conhecem (os do dialeto e os comuns).
TAGS_XHTML = sorted({
    "a", "abbr", "aside", "b", "blockquote", "body", "br", "caption", "cite", "code", "dd", "del", "dfn", "div",
    "dl", "dt", "em", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "head", "header",
    "hr", "html", "i", "img", "ins", "kbd", "li", "link", "main", "mark", "meta", "nav", "ol", "p", "pre", "q",
    "s", "samp", "section", "small", "span", "strong", "style", "sub", "sup", "table", "tbody", "td", "tfoot",
    "th", "thead", "title", "tr", "u", "ul", "var",
})
#: Os `epub:type` da §9.7.
SEMANTICAS = ("cover", "titlepage", "copyright-page", "dedication", "epigraph", "foreword", "preface",
              "introduction", "toc", "bodymatter", "chapter", "glossary", "bibliography", "index", "appendix",
              "acknowledgments", "colophon", "endnotes", "footnote", "noteref", "pagebreak")
VAZIOS = consertar_mod.VAZIOS

_RE_TAG = re.compile(
    r"<(/?)([A-Za-z_:][\w:.-]*)"                                                    # </ e o nome
    r"((?:\s+[^\s=/>\"']+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'=<>`]+))?)*)"        # os atributos
    r"\s*(/?)>", re.S)
_RE_COMENTARIO_OU_PI = re.compile(r"<!--.*?-->|<\?.*?\?>|<!\[CDATA\[.*?\]\]>|<![^>]*>", re.S)
_RE_ATRIBUTO_NO_CURSOR = re.compile(r"""([\w:.-]+)\s*=\s*"([^"]*)\"""")
_RE_PALAVRA = re.compile(r"\w+|\W+")


class EditorDeCodigo(ttk.Frame):
    """O editor de código de um arquivo (XHTML ou CSS); ver o cabeçalho do módulo."""

    def __init__(self, master: tk.Misc, linguagem: str = "xhtml", folhas: Any = (),
                 abrir_alvo: Callable[[str, str], None] | None = None, tema: str = "claro",
                 familia: str = "Consolas", corpo: int = 11, tabulacao: int = 2,
                 relogio: Callable[[], float] = time.monotonic, **kw: Any):
        super().__init__(master, **kw)
        if linguagem not in ("xhtml", "css"):
            raise ValueError(f"linguagem desconhecida: {linguagem!r}")
        self.linguagem = linguagem
        self.abrir_alvo = abrir_alvo
        self.relogio = relogio
        self.tabulacao = " " * int(tabulacao)
        self._tema = realce_mod.tema(tema)
        self._corpo_base = int(corpo)
        self._corpo = int(corpo)
        self._fonte = tkfont.Font(family=familia, size=self._corpo)
        self._fonte_negrito = tkfont.Font(family=familia, size=self._corpo, weight="bold")
        self.definir_folhas(folhas)

        self.calha = tk.Canvas(self, width=44, highlightthickness=0, takefocus=0,
                               background=self._tema["calha_fundo"])
        self.texto = tk.Text(self, undo=False, wrap="none", highlightthickness=2, font=self._fonte,
                             background=self._tema["fundo"], foreground=self._tema["texto"],
                             insertbackground=self._tema["cursor"], selectbackground=self._tema["selecao"],
                             selectforeground=self._tema["selecao_texto"],
                             inactiveselectbackground=self._tema["selecao"], insertwidth=2,
                             tabs=(self._fonte.measure(self.tabulacao),), exportselection=False)
        self.barra_v = ttk.Scrollbar(self, orient="vertical", command=self.texto.yview)
        self.barra_h = ttk.Scrollbar(self, orient="horizontal", command=self.texto.xview)
        self.texto.configure(yscrollcommand=self._rolagem_v, xscrollcommand=self.barra_h.set)
        self.calha.grid(row=0, column=0, sticky="ns")
        self.texto.grid(row=0, column=1, sticky="nsew")
        self.barra_v.grid(row=0, column=2, sticky="ns")
        self.barra_h.grid(row=1, column=1, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        self._realce = realce_mod.Realce(linguagem)
        self._sujo = False
        self._em_carga = False
        self._em_desfazer = False
        self._desfazer: list[list[tuple]] = []
        self._refazer: list[list[tuple]] = []
        self._ultima_operacao = 0.0
        self._grupo_aberto = 0
        self._voltas: list[str] = []
        self._sugestoes: list[str] = []
        self._popup: tk.Toplevel | None = None
        self._lista: tk.Listbox | None = None
        self._pintura_agendada: str | None = None

        for tipo in realce_mod.TIPOS:
            self.texto.tag_configure(tipo, foreground=self._tema[tipo])
        self.texto.tag_configure("linha_atual", background=self._tema["linha_atual"])
        self.texto.tag_configure("casamento", background=self._tema["casamento"])
        self.texto.tag_configure("erro", background=self._tema["erro"])
        self.texto.tag_raise("sel")
        self.texto.tag_lower("linha_atual")

        self._instalar_proxy()
        self._instalar_ligacoes()
        self.calha.bind("<Configure>", lambda e: self._desenhar_calha())
        self.texto.bind("<Configure>", lambda e: self._agendar_pintura())
        self.texto.bind("<FocusIn>", lambda e: self._cursor_moveu())
        self.comandos: dict[str, Callable[..., Any]] = {
            "desfazer": self.desfazer, "refazer": self.refazer, "comentar": self.comentar,
            "reformatar": self.reformatar, "completar_tag": self.completar_tag, "sugerir": self.sugerir,
            "negrito": lambda: self.envolver("strong"), "italico": lambda: self.envolver("em"),
            "sublinhado": lambda: self.envolver("u"), "inserir_link": self.inserir_link,
            "inserir_id": self.inserir_id, "inserir_imagem": self.inserir_imagem,
            "ir_para_linha": self.ir_para_linha, "bem_formado": self.verificar_bem_formado,
            "consertar": self.consertar, "dividir_no_cursor": self.dividir_no_cursor,
            "ir_ao_alvo": self.ir_ao_alvo, "voltar": self.voltar, "zoom_mais": lambda: self.zoom(1),
            "zoom_menos": lambda: self.zoom(-1), "zoom_zero": self.zoom_zero,
            "apagar_palavra_anterior": lambda: self.apagar_palavra(-1),
            "apagar_palavra_seguinte": lambda: self.apagar_palavra(1),
            "selecionar_tudo": self.selecionar_tudo, "indentar": self.indentar,
            "desindentar": lambda: self.indentar(-1), "aplicar_clipe": self.aplicar_clipe,
        }

    # ------------------------------------------------------------------
    # Proxy do comando Tcl
    # ------------------------------------------------------------------

    def _instalar_proxy(self) -> None:
        self._original = self.texto._w + "_orig"
        self.texto.tk.call("rename", self.texto._w, self._original)
        self.texto.tk.createcommand(self.texto._w, self._proxy)

    def _proxy(self, comando: str, *args: Any) -> Any:
        antes = None
        chamar = self.texto.tk.call
        if comando == "insert" and len(args) >= 2:
            antes = (str(chamar(self._original, "index", args[0])), str(args[1]))
        elif comando == "delete" and args:
            ini = str(chamar(self._original, "index", args[0]))
            if len(args) > 1:
                fim = str(chamar(self._original, "index", args[1]))
            else:
                fim = str(chamar(self._original, "index", f"{ini}+1c"))
            antes = (ini, fim, str(chamar(self._original, "get", ini, fim)))
        resultado = self.texto.tk.call((self._original, comando) + args)
        if comando == "insert" and antes is not None:
            self._registrar(("insert", antes[0], antes[1]))
            self._depois_de_editar(antes[0], 0, antes[1].count("\n"))
        elif comando == "delete" and antes is not None:
            ini, fim, apagado = antes
            if apagado:
                self._registrar(("delete", ini, fim, apagado))
                self._depois_de_editar(ini, apagado.count("\n"), 0)
        elif comando in ("yview", "xview") and args:
            self._agendar_pintura()
        elif comando == "mark" and len(args) >= 3 and args[0] == "set" and args[1] == "insert":
            self._cursor_moveu()
        return resultado

    def _depois_de_editar(self, indice: str, removidas: int, inseridas: int) -> None:
        linha = int(str(indice).split(".")[0]) - 1
        self._realce.editar(linha, removidas, inseridas)
        de, ate = self._realce.reprocessar(self._linhas(), linha)
        self._ultima_faixa_alterada = (de, ate)
        if not self._em_carga:
            self._sujo = True
        self.texto.tag_remove("erro", "1.0", "end")
        self._pintar_faixa()
        self._desenhar_calha()
        self._cursor_moveu()

    # ------------------------------------------------------------------
    # Desfazer próprio
    # ------------------------------------------------------------------

    def _registrar(self, operacao: tuple) -> None:
        if self._em_desfazer or self._em_carga:
            return
        agora = self.relogio()
        self._refazer.clear()
        if self._grupo_aberto and self._desfazer and self._grupo_aberto > 1:
            self._desfazer[-1].append(operacao)
        elif self._grupo_aberto:
            self._desfazer.append([operacao])
            self._grupo_aberto = 2          # o grupo já tem a sua primeira operação
        elif self._desfazer and agora - self._ultima_operacao <= COALESCENCIA_S \
                and self._coalesce(self._desfazer[-1][-1], operacao):
            self._desfazer[-1].append(operacao)
        else:
            self._desfazer.append([operacao])
        del self._desfazer[:-500]
        self._ultima_operacao = agora

    class _Grupo:
        """`with self._grupo():` — tudo que se edita dentro é um ponto só de desfazer."""

        def __init__(self, editor: "EditorDeCodigo"):
            self.editor = editor

        def __enter__(self) -> None:
            self.editor._grupo_aberto = 1

        def __exit__(self, *args: Any) -> None:
            self.editor._grupo_aberto = 0
            self.editor._ultima_operacao = 0.0      # o que vier depois não se cola ao grupo

    def _grupo(self) -> "EditorDeCodigo._Grupo":
        return EditorDeCodigo._Grupo(self)

    @staticmethod
    def _coalesce(anterior: tuple, nova: tuple) -> bool:
        """Digitação contínua (um caractere de cada vez, colado ao anterior) é um ponto só."""
        if anterior[0] != nova[0]:
            return False
        if nova[0] == "insert":
            return len(nova[2]) == 1 and nova[2] != "\n" and len(anterior[2]) <= 1 \
                and _depois(anterior[1], len(anterior[2])) == nova[1]
        return len(nova[3]) == 1 and nova[3] != "\n" and len(anterior[3]) == 1 \
            and (nova[2] == anterior[1] or nova[1] == anterior[1])

    def desfazer(self) -> bool:
        if not self._desfazer:
            return False
        grupo = self._desfazer.pop()
        self._em_desfazer = True
        try:
            for operacao in reversed(grupo):
                if operacao[0] == "insert":
                    _, indice, texto = operacao
                    self.texto.delete(indice, f"{indice}+{len(texto)}c")
                    self.texto.mark_set("insert", indice)
                else:
                    _, ini, _fim, texto = operacao
                    self.texto.insert(ini, texto)
                    self.texto.mark_set("insert", f"{ini}+{len(texto)}c")
        finally:
            self._em_desfazer = False
        self._refazer.append(grupo)
        self.texto.see("insert")
        return True

    def refazer(self) -> bool:
        if not self._refazer:
            return False
        grupo = self._refazer.pop()
        self._em_desfazer = True
        try:
            for operacao in grupo:
                if operacao[0] == "insert":
                    _, indice, texto = operacao
                    self.texto.insert(indice, texto)
                    self.texto.mark_set("insert", f"{indice}+{len(texto)}c")
                else:
                    _, ini, fim, _texto = operacao
                    self.texto.delete(ini, fim)
                    self.texto.mark_set("insert", ini)
        finally:
            self._em_desfazer = False
        self._desfazer.append(grupo)
        self.texto.see("insert")
        return True

    @property
    def pode_desfazer(self) -> bool:
        return bool(self._desfazer)

    @property
    def pode_refazer(self) -> bool:
        return bool(self._refazer)

    # ------------------------------------------------------------------
    # Carga, texto, estado
    # ------------------------------------------------------------------

    def carregar(self, texto: str) -> None:
        """Põe o texto no widget, limpo e sem histórico; realça e desenha."""
        self._em_carga = True
        try:
            self.texto.delete("1.0", "end")
            self.texto.insert("1.0", texto.lstrip("﻿").replace("\r\n", "\n"))
            self.texto.mark_set("insert", "1.0")
            self.texto.see("1.0")
        finally:
            self._em_carga = False
        self._desfazer.clear()
        self._refazer.clear()
        self._voltas.clear()
        self._sujo = False
        self._realce.carregar(self._linhas())
        self.sincronizar()

    def texto_todo(self) -> str:
        return self.texto.get("1.0", "end-1c")

    def _linhas(self) -> list[str]:
        return self.texto_todo().split("\n")

    @property
    def sujo(self) -> bool:
        return self._sujo

    def marcar_limpo(self) -> None:
        self._sujo = False

    def foco(self) -> None:
        self.texto.focus_set()

    @property
    def posicao(self) -> tuple[int, int]:
        """`(linha, coluna)`, ambas a partir de 1."""
        linha, coluna = self.texto.index("insert").split(".")
        return int(linha), int(coluna) + 1

    def ir_para(self, linha: int, coluna: int = 1) -> None:
        total = int(self.texto.index("end-1c").split(".")[0])
        linha = max(1, min(int(linha), total))
        self.texto.mark_set("insert", f"{linha}.{max(0, int(coluna) - 1)}")
        self.texto.see("insert")
        self._cursor_moveu()

    def ir_para_linha(self, linha: int | None = None) -> None:
        """Com `linha`, vai; sem, pede à janela (`<<IrParaLinha>>`)."""
        if linha is None:
            self.texto.event_generate("<<IrParaLinha>>")
            return
        self.ir_para(linha)

    def selecao(self) -> tuple[str, str] | None:
        try:
            return self.texto.index("sel.first"), self.texto.index("sel.last")
        except tk.TclError:
            return None

    def selecionar_tudo(self) -> None:
        self.texto.tag_add("sel", "1.0", "end-1c")

    def definir_folhas(self, folhas: Any) -> None:
        """As folhas de estilo do capítulo: `{href: texto}` ou pares `(href, texto)`."""
        if isinstance(folhas, dict):
            self._folhas = list(folhas.items())
        else:
            self._folhas = [tuple(par) for par in folhas]
        self._classes: dict[str, str] = {}
        for href, texto in self._folhas:
            try:
                folha = css_minima.ler(texto)
            except Exception:      # noqa: BLE001 — folha ilegível não impede o editor de abrir
                continue
            for regra in folha.regras:
                for classe in regra.classes:
                    self._classes.setdefault(classe, href)

    # ------------------------------------------------------------------
    # Realce, calha, linha atual, casamento
    # ------------------------------------------------------------------

    def _rolagem_v(self, *args: Any) -> None:
        self.barra_v.set(*args)
        self._agendar_pintura()

    def _agendar_pintura(self) -> None:
        if self._pintura_agendada is None:
            try:
                self._pintura_agendada = self.after_idle(self._pintar_agendado)
            except tk.TclError:
                pass

    def _pintar_agendado(self) -> None:
        self._pintura_agendada = None
        self._pintar_faixa()
        self._desenhar_calha()

    def sincronizar(self, tudo: bool = False) -> None:
        """Pinta agora (a faixa visível, ou `tudo`) e redesenha a calha — o que o `after_idle` faria."""
        if self._pintura_agendada is not None:
            try:
                self.after_cancel(self._pintura_agendada)
            except tk.TclError:
                pass
            self._pintura_agendada = None
        self._pintar_faixa(tudo=tudo)
        self._desenhar_calha()
        self._cursor_moveu()

    def _faixa_visivel(self) -> tuple[int, int]:
        """Linhas (1-based, fim exclusivo) que a tela mostra — pelo menos 60 a partir do topo."""
        total = int(self.texto.index("end-1c").split(".")[0])
        primeira = int(self.texto.index("@0,0").split(".")[0])
        altura = max(self.texto.winfo_height(), 1)
        por_linha = max(self._fonte.metrics("linespace"), 1)
        visiveis = max(60, altura // por_linha + 2)
        return primeira, min(total + 1, primeira + visiveis)

    def _pintar_faixa(self, tudo: bool = False) -> None:
        linhas = self._linhas()
        if tudo:
            de, ate = 1, len(linhas) + 1
        else:
            de, ate = self._faixa_visivel()
        texto = self.texto
        for tipo in realce_mod.TIPOS:
            texto.tag_remove(tipo, f"{de}.0", f"{ate}.0")
        for i, tokens in self._realce.faixa(linhas, de - 1, ate - 1):
            n = i + 1
            for inicio, fim, tipo in tokens:
                texto.tag_add(tipo, f"{n}.{inicio}", f"{n}.{fim}")

    def _desenhar_calha(self) -> None:
        calha = self.calha
        calha.delete("all")
        total = int(self.texto.index("end-1c").split(".")[0])
        digitos = max(2, len(str(total)))
        largura = self._fonte.measure("0" * digitos) + 14
        if int(calha.cget("width")) != largura:
            calha.configure(width=largura)
        atual = int(self.texto.index("insert").split(".")[0])
        i = self.texto.index("@0,0")
        while True:
            caixa = self.texto.dlineinfo(i)
            if caixa is None:
                break
            linha = int(i.split(".")[0])
            cor = self._tema["calha_atual"] if linha == atual else self._tema["calha_texto"]
            calha.create_text(largura - 6, caixa[1], anchor="ne", text=str(linha), fill=cor,
                              font=self._fonte_negrito if linha == atual else self._fonte)
            i = self.texto.index(f"{i}+1line")
            if int(i.split(".")[0]) > total:
                break

    def _cursor_moveu(self) -> None:
        texto = self.texto
        texto.tag_remove("linha_atual", "1.0", "end")
        texto.tag_add("linha_atual", "insert linestart", "insert lineend+1c")
        self._casar()
        if self.texto.winfo_ismapped():
            self._desenhar_calha()

    def _casar(self) -> None:
        """Realça o par da tag (ou do parêntese/chave) junto ao cursor."""
        texto = self.texto
        texto.tag_remove("casamento", "1.0", "end")
        par = self._par_no_cursor()
        if par is None:
            return
        for ini, fim in par:
            texto.tag_add("casamento", ini, fim)

    def _par_no_cursor(self) -> list[tuple[str, str]] | None:
        texto = self.texto
        linha, coluna = (int(v) for v in texto.index("insert").split("."))
        conteudo = texto.get(f"{linha}.0", f"{linha}.end")
        for c in (coluna - 1, coluna):
            if 0 <= c < len(conteudo) and conteudo[c] in "(){}[]":
                alvo = self._parente(f"{linha}.{c}", conteudo[c])
                if alvo is not None:
                    return [(f"{linha}.{c}", f"{linha}.{c + 1}"), (alvo, f"{alvo}+1c")]
                return None
        if self.linguagem != "xhtml":
            return None
        tag = self._tag_no_cursor()
        if tag is None:
            return None
        ini_l, ini_c, fim_l, fim_c, fecha, nome, vazia = tag
        if vazia:
            return [(f"{ini_l}.{ini_c}", f"{fim_l}.{fim_c}")]
        par = self._tag_par(nome, fecha, f"{ini_l}.{ini_c}" if fecha else f"{fim_l}.{fim_c}")
        if par is None:
            return [(f"{ini_l}.{ini_c}", f"{fim_l}.{fim_c}")]
        return [(f"{ini_l}.{ini_c}", f"{fim_l}.{fim_c}"), par]

    def _parente(self, indice: str, c: str) -> str | None:
        pares = {"(": ")", "{": "}", "[": "]"}
        inversos = {v: k for k, v in pares.items()}
        texto = self.texto
        if c in pares:
            abre, fecha, direcao = c, pares[c], 1
        else:
            abre, fecha, direcao = inversos[c], c, -1
        profundidade = 0
        pos = indice
        conteudo = texto.get(indice, "end-1c") if direcao > 0 else texto.get("1.0", f"{indice}+1c")
        if direcao > 0:
            for i, ch in enumerate(conteudo):
                if ch == abre:
                    profundidade += 1
                elif ch == fecha:
                    profundidade -= 1
                    if profundidade == 0:
                        return texto.index(f"{pos}+{i}c")
        else:
            for i in range(len(conteudo) - 1, -1, -1):
                ch = conteudo[i]
                if ch == fecha:
                    profundidade += 1
                elif ch == abre:
                    profundidade -= 1
                    if profundidade == 0:
                        return texto.index(f"1.0+{i}c")
        return None

    def _tag_no_cursor(self):
        """`(linha_ini, col_ini, linha_fim, col_fim, fecha, nome, vazia)` da tag sob o cursor, ou `None`."""
        texto = self.texto
        cursor = texto.index("insert")
        inicio = texto.search("<", cursor, backwards=True, regexp=False)
        if not inicio:
            return None
        fim = texto.search(">", inicio, regexp=False)
        if not fim or texto.compare(fim, "<", f"{cursor}-1c"):
            return None
        cru = texto.get(inicio, f"{fim}+1c")
        m = _RE_TAG.match(cru)
        if not m:
            return None
        ini_l, ini_c = (int(v) for v in inicio.split("."))
        fim_l, fim_c = (int(v) for v in texto.index(f"{fim}+1c").split("."))
        nome = m.group(2)
        vazia = bool(m.group(4)) or nome.lower() in VAZIOS
        return ini_l, ini_c, fim_l, fim_c, bool(m.group(1)), nome, vazia

    def _tag_par(self, nome: str, fecha: bool, de: str) -> tuple[str, str] | None:
        """A tag que fecha (ou abre) `nome` a partir de `de`, contando as aninhadas."""
        texto = self.texto
        if fecha:
            conteudo = texto.get("1.0", de)
            profundidade = 0
            for m in reversed(list(_RE_TAG.finditer(conteudo))):
                if m.group(2) != nome or m.group(4):
                    continue
                if m.group(1):
                    profundidade += 1
                elif profundidade == 0:
                    return texto.index(f"1.0+{m.start()}c"), texto.index(f"1.0+{m.end()}c")
                else:
                    profundidade -= 1
            return None
        conteudo = texto.get(de, "end-1c")
        profundidade = 0
        for m in _RE_TAG.finditer(conteudo):
            if m.group(2) != nome or m.group(4):
                continue
            if not m.group(1):
                profundidade += 1
            elif profundidade == 0:
                return texto.index(f"{de}+{m.start()}c"), texto.index(f"{de}+{m.end()}c")
            else:
                profundidade -= 1
        return None

    # ------------------------------------------------------------------
    # Ligações
    # ------------------------------------------------------------------

    def _instalar_ligacoes(self) -> None:
        texto = self.texto
        tags = list(texto.bindtags())
        tags.insert(1, BINDTAG)
        texto.bindtags(tuple(tags))
        ligacoes = {
            "<Return>": self._tecla_enter, "<KP_Enter>": self._tecla_enter,
            "<Tab>": lambda e: self._quebra(self.indentar_ou_tab()),
            "<Shift-Tab>": lambda e: self._quebra(self.indentar(-1)),
            "<Key-slash>": self._tecla_barra,
            "<Control-slash>": lambda e: self._quebra(self.comentar()),
            "<Control-Shift-I>": lambda e: self._quebra(self.reformatar()),
            "<Control-space>": lambda e: self._quebra(self.sugerir()),
            "<Control-b>": lambda e: self._quebra(self.envolver("strong")),
            "<Control-i>": lambda e: self._quebra(self.envolver("em")),
            "<Control-u>": lambda e: self._quebra(self.envolver("u")),
            "<Control-BackSpace>": lambda e: self._quebra(self.apagar_palavra(-1)),
            "<Control-Delete>": lambda e: self._quebra(self.apagar_palavra(1)),
            "<Control-KP_Add>": lambda e: self._quebra(self.zoom(1)),
            "<Control-KP_Subtract>": lambda e: self._quebra(self.zoom(-1)),
            "<Control-plus>": lambda e: self._quebra(self.zoom(1)),
            "<Control-minus>": lambda e: self._quebra(self.zoom(-1)),
            "<Control-Key-0>": lambda e: self._quebra(self.zoom_zero()),
            "<Control-MouseWheel>": self._roda_com_control,
            "<<Undo>>": lambda e: self._quebra(self.desfazer()),
            "<<Redo>>": lambda e: self._quebra(self.refazer()),
            "<<SelectAll>>": lambda e: self._quebra(self.selecionar_tudo()),
            "<Alt-F7>": lambda e: self._quebra(self.verificar_bem_formado()),
            "<Alt-F8>": lambda e: self._quebra(self.consertar()),
            "<Control-Return>": lambda e: self._evento("<<DividirNoCursor>>"),
            "<Control-k>": lambda e: self._evento("<<InserirLink>>"),
            "<Control-g>": lambda e: self._evento("<<IrParaLinha>>"),
            "<Control-Shift-J>": lambda e: self._evento("<<Clipes>>"),
            "<Escape>": self._tecla_escape,
            "<Up>": lambda e: self._navegar_popup(-1), "<Down>": lambda e: self._navegar_popup(1),
            "<Key-Insert>": lambda e: "break", "<<PasteSelection>>": lambda e: "break",
            "<Control-d>": lambda e: "break", "<Control-o>": lambda e: "break", "<Control-t>": lambda e: "break",
        }
        for sequencia, handler in ligacoes.items():
            texto.bind_class(BINDTAG, sequencia, handler)
        self.ligacoes = ligacoes

    @staticmethod
    def _quebra(_resultado: Any = None) -> str:
        return "break"

    def _evento(self, nome: str) -> str:
        self.texto.event_generate(nome)
        return "break"

    def _tecla_enter(self, evento: Any) -> str:
        if self._popup is not None and self._lista is not None:
            self.escolher_sugestao()
            return "break"
        self.enter()
        return "break"

    def _tecla_barra(self, evento: Any) -> str | None:
        texto = self.texto
        if self.linguagem == "xhtml" and texto.get("insert-1c", "insert") == "<":
            texto.insert("insert", "/")
            self.completar_tag()
            return "break"
        return None

    def _tecla_escape(self, evento: Any) -> str | None:
        if self._popup is not None:
            self.fechar_sugestoes()
            return "break"
        return None

    def _navegar_popup(self, passo: int) -> str | None:
        if self._popup is None or self._lista is None:
            return None
        atual = self._lista.curselection()
        i = (atual[0] if atual else -passo) + passo
        i = max(0, min(i, self._lista.size() - 1))
        self._lista.selection_clear(0, "end")
        self._lista.selection_set(i)
        self._lista.activate(i)
        self._lista.see(i)
        return "break"

    def _roda_com_control(self, evento: Any) -> str:
        self.zoom(1 if getattr(evento, "delta", 0) > 0 else -1)
        return "break"

    # ------------------------------------------------------------------
    # Edição: enter, tab, apagar palavra, comentar, envolver, inserir
    # ------------------------------------------------------------------

    def enter(self) -> None:
        """Quebra a linha mantendo o recuo; abre um nível depois de uma tag ou chave aberta."""
        texto = self.texto
        selecao = self.selecao()
        with self._grupo():
            self._enter(texto, selecao)

    def _enter(self, texto: tk.Text, selecao: tuple[str, str] | None) -> None:
        if selecao:
            texto.delete(*selecao)
        linha = texto.get("insert linestart", "insert")
        recuo = re.match(r"[ \t]*", linha).group(0)
        depois = texto.get("insert", "insert lineend")
        abre = False
        m = list(_RE_TAG.finditer(linha))
        if m and m[-1].end() == len(linha) and not m[-1].group(1) and not m[-1].group(4) \
                and m[-1].group(2).lower() not in VAZIOS:
            abre = True
        if linha.rstrip().endswith("{"):
            abre = True
        texto.insert("insert", "\n" + recuo + (self.tabulacao if abre else ""))
        if abre and (depois.startswith("</") or depois.startswith("}")):
            # `<p>|</p>` → o fechamento desce uma linha, alinhado com a abertura.
            marca = texto.index("insert")
            texto.insert("insert", "\n" + recuo)
            texto.mark_set("insert", marca)
        texto.see("insert")

    def indentar_ou_tab(self) -> None:
        if self.selecao() and self.texto.get("sel.first", "sel.last").count("\n"):
            self.indentar(1)
        else:
            self.texto.insert("insert", self.tabulacao)

    def indentar(self, sentido: int = 1) -> int:
        """Recua (ou desrecua) as linhas da seleção, ou a atual; devolve quantas mudaram."""
        texto = self.texto
        selecao = self.selecao()
        if selecao:
            ini = int(selecao[0].split(".")[0])
            fim = int(selecao[1].split(".")[0])
            if fim > ini and texto.compare(selecao[1], "==", f"{selecao[1]} linestart"):
                fim -= 1        # a seleção que termina no começo de uma linha não a inclui
        else:
            ini = fim = int(texto.index("insert").split(".")[0])
        n = 0
        with self._grupo():
            n = self._indentar(texto, ini, fim, sentido)
        if selecao:
            texto.tag_add("sel", f"{ini}.0", f"{fim}.end")
        return n

    def _indentar(self, texto: tk.Text, ini: int, fim: int, sentido: int) -> int:
        n = 0
        for linha in range(ini, fim + 1):
            if sentido > 0:
                texto.insert(f"{linha}.0", self.tabulacao)
                n += 1
            else:
                atual = texto.get(f"{linha}.0", f"{linha}.end")
                espacos = len(atual) - len(atual.lstrip(" "))
                tirar = min(espacos, len(self.tabulacao))
                if atual.startswith("\t"):
                    tirar = 1
                if tirar:
                    texto.delete(f"{linha}.0", f"{linha}.{tirar}")
                    n += 1
        return n

    def apagar_palavra(self, sentido: int) -> str:
        """Apaga a palavra anterior (`-1`) ou seguinte (`1`) — o `Ctrl+BackSpace` que o `Text` não tem."""
        texto = self.texto
        self._ultima_operacao = 0.0          # apagar palavra não se cola à digitação anterior
        if self.selecao():
            apagado = texto.get("sel.first", "sel.last")
            texto.delete("sel.first", "sel.last")
            return apagado
        if sentido < 0:
            trecho = texto.get("insert linestart", "insert")
            if not trecho:
                if texto.compare("insert", "==", "1.0"):
                    return ""
                texto.delete("insert-1c", "insert")
                return "\n"
            m = re.search(r"(\w+|\W+)$", trecho)
            quantos = len(m.group(0)) if m else 1
            apagado = texto.get(f"insert-{quantos}c", "insert")
            texto.delete(f"insert-{quantos}c", "insert")
            return apagado
        trecho = texto.get("insert", "insert lineend")
        if not trecho:
            if texto.compare("insert", ">=", "end-1c"):
                return ""
            texto.delete("insert", "insert+1c")
            return "\n"
        m = _RE_PALAVRA.match(trecho)
        quantos = len(m.group(0)) if m else 1
        apagado = texto.get("insert", f"insert+{quantos}c")
        texto.delete("insert", f"insert+{quantos}c")
        return apagado

    def comentar(self) -> bool:
        """Comenta as linhas da seleção (ou a atual); se já estão comentadas, descomenta. Devolve o que fez."""
        texto = self.texto
        abre, fecha = ("<!--", "-->") if self.linguagem == "xhtml" else ("/*", "*/")
        selecao = self.selecao()
        if selecao:
            ini = texto.index(f"{selecao[0]} linestart")
            fim = texto.index(f"{selecao[1]} lineend") if texto.compare(selecao[1], ">", f"{selecao[1]} linestart") \
                else texto.index(f"{selecao[1]}-1c lineend")
        else:
            ini, fim = texto.index("insert linestart"), texto.index("insert lineend")
        conteudo = texto.get(ini, fim)
        sem = conteudo.strip()
        recuo = conteudo[: len(conteudo) - len(conteudo.lstrip())]
        with self._grupo():
            if sem.startswith(abre) and sem.endswith(fecha):
                miolo = sem[len(abre):-len(fecha)]
                if miolo.startswith(" "):
                    miolo = miolo[1:]
                if miolo.endswith(" "):
                    miolo = miolo[:-1]
                texto.delete(ini, fim)
                texto.insert(ini, recuo + miolo)
                comentou = False
            else:
                texto.delete(ini, fim)
                texto.insert(ini, f"{recuo}{abre} {conteudo.lstrip()} {fecha}")
                comentou = True
        texto.tag_add("sel", ini, f"{ini} lineend")
        return comentou

    def envolver(self, tag: str) -> None:
        """A seleção dentro de `<tag>…</tag>`; sem seleção, o par vazio com o cursor no meio (`Ctrl+B/I/U`)."""
        texto = self.texto
        selecao = self.selecao()
        with self._grupo():
            if selecao:
                ini, fim = selecao
                conteudo = texto.get(ini, fim)
                texto.delete(ini, fim)
                texto.insert(ini, f"<{tag}>{conteudo}</{tag}>")
                texto.tag_add("sel", ini, f"{ini}+{len(conteudo) + len(tag) * 2 + 5}c")
                texto.mark_set("insert", f"{ini}+{len(conteudo) + len(tag) * 2 + 5}c")
            else:
                texto.insert("insert", f"<{tag}></{tag}>")
                texto.mark_set("insert", f"insert-{len(tag) + 3}c")

    def inserir_link(self, href: str | None = None, rotulo: str | None = None) -> None:
        """`<a href="…">rótulo</a>` (o rótulo é a seleção quando não vem); sem `href`, pede à janela."""
        if href is None:
            self.texto.event_generate("<<InserirLink>>")
            return
        texto = self.texto
        selecao = self.selecao()
        if rotulo is None:
            rotulo = texto.get(*selecao) if selecao else href
        with self._grupo():
            if selecao:
                texto.delete(*selecao)
            texto.insert("insert", f'<a href="{_attr(href)}">{_escapar(rotulo)}</a>')

    def inserir_id(self, id_: str) -> None:
        """`id="…"` na tag de abertura sob o cursor; fora de tag, um `<span id="…">` envolvendo a seleção."""
        texto = self.texto
        selecao = self.selecao()
        tag = self._tag_no_cursor() if selecao is None else None
        if tag is not None and not tag[4]:
            ini_l, ini_c, _fl, _fc, _fecha, nome, _vazia = tag
            texto.insert(f"{ini_l}.{ini_c + 1 + len(nome)}", f' id="{_attr(id_)}"')
            return
        with self._grupo():
            if selecao:
                conteudo = texto.get(*selecao)
                texto.delete(*selecao)
                texto.insert(selecao[0], f'<span id="{_attr(id_)}">{conteudo}</span>')
            else:
                texto.insert("insert", f'<span id="{_attr(id_)}"></span>')
                texto.mark_set("insert", "insert-7c")

    def inserir_imagem(self, href: str, alt: str = "") -> None:
        self.texto.insert("insert", f'<img src="{_attr(href)}" alt="{_attr(alt)}"/>')

    def aplicar_clipe(self, clipe: Any) -> str:
        """`clipe.aplicar(seleção)` inserido no lugar da seleção, com o cursor onde o `\\1` estava."""
        selecao = self.selecao()
        conteudo = self.texto.get(*selecao) if selecao else ""
        texto, cursor = clipe.aplicar(conteudo)
        self.inserir(texto, cursor_em=None if selecao else cursor)
        return texto

    def inserir(self, texto: str, cursor_em: int | None = None) -> None:
        """Insere no cursor (troca a seleção); `cursor_em` é a posição, dentro do texto, onde o cursor fica."""
        selecao = self.selecao()
        with self._grupo():
            if selecao:
                self.texto.delete(*selecao)
            inicio = self.texto.index("insert")
            self.texto.insert("insert", texto)
            if cursor_em is not None:
                self.texto.mark_set("insert", f"{inicio}+{cursor_em}c")

    # ------------------------------------------------------------------
    # Completar e sugerir
    # ------------------------------------------------------------------

    def _tags_abertas(self, ate: str = "insert") -> list[str]:
        """A pilha de elementos abertos antes de `ate` (sem os vazios e sem os fechados)."""
        conteudo = _RE_COMENTARIO_OU_PI.sub(lambda m: " " * len(m.group(0)), self.texto.get("1.0", ate))
        pilha: list[str] = []
        for m in _RE_TAG.finditer(conteudo):
            nome = m.group(2)
            if m.group(4) or nome.lower() in VAZIOS:
                continue
            if m.group(1):
                if nome in pilha:
                    while pilha and pilha.pop() != nome:
                        pass
            else:
                pilha.append(nome)
        return pilha

    def completar_tag(self) -> str | None:
        """Depois de `</`, o nome da tag aberta mais interna e o `>`; devolve o nome, ou `None`."""
        texto = self.texto
        if texto.get("insert-2c", "insert") != "</":
            return None
        pilha = self._tags_abertas("insert-2c")
        if not pilha:
            return None
        nome = pilha[-1]
        texto.insert("insert", f"{nome}>")
        return nome

    def _contexto_do_cursor(self) -> tuple[str, str]:
        """`("tag" | "classe" | "semantica" | "atributo" | "texto", prefixo_digitado)`."""
        texto = self.texto
        antes = texto.get("insert linestart", "insert")
        m = re.search(r"<([A-Za-z_:][\w:.-]*)?$", antes)
        if m:
            return "tag", m.group(1) or ""
        m = re.search(r"""class\s*=\s*"([^"]*)$""", antes)
        if m:
            return "classe", m.group(1).split()[-1] if m.group(1).strip() and not m.group(1).endswith(" ") else ""
        m = re.search(r"""epub:type\s*=\s*"([^"]*)$""", antes)
        if m:
            return "semantica", m.group(1).split()[-1] if m.group(1).strip() and not m.group(1).endswith(" ") else ""
        m = re.search(r"<[A-Za-z_:][\w:.-]*(?:\s+[^<>]*)?\s+([\w:.-]*)$", antes)
        if m and '"' not in antes[m.start():].split("=")[-1]:
            return "atributo", m.group(1)
        return "texto", ""

    def sugerir(self) -> list[str]:
        """
        As sugestões para o cursor (`Ctrl+Space`): tags, classes das folhas dentro de
        `class="…"`, semânticas dentro de `epub:type="…"`, atributos dentro de tag — e
        abre a lista flutuante quando há mais de uma. Devolve a lista.
        """
        if self.linguagem == "css":
            antes = self.texto.get("insert linestart", "insert")
            contexto, prefixo = "propriedade", re.search(r"([\w-]*)$", antes).group(1)
            candidatos = [p for p in PROPRIEDADES_CSS if p.startswith(prefixo)]
        else:
            contexto, prefixo = self._contexto_do_cursor()
            if contexto == "tag":
                candidatos = [t for t in TAGS_XHTML if t.startswith(prefixo)]
            elif contexto == "classe":
                candidatos = sorted(c for c in self._classes if c.startswith(prefixo))
            elif contexto == "semantica":
                candidatos = [s for s in SEMANTICAS if s.startswith(prefixo)]
            elif contexto == "atributo":
                candidatos = [a for a in ATRIBUTOS_XHTML if a.startswith(prefixo)]
            else:
                candidatos = []
        self._sugestoes = candidatos
        self._prefixo = prefixo
        self._contexto = contexto
        self.fechar_sugestoes()
        if len(candidatos) == 1:
            self.escolher_sugestao(0)
        elif candidatos:
            self._abrir_popup(candidatos)
        return candidatos

    def _abrir_popup(self, candidatos: Sequence[str]) -> None:
        popup = tk.Toplevel(self.texto)
        popup.overrideredirect(True)
        try:
            popup.transient(self.winfo_toplevel())
        except tk.TclError:
            pass
        lista = tk.Listbox(popup, height=min(8, len(candidatos)), font=self._fonte, exportselection=False,
                           background=self._tema["fundo"], foreground=self._tema["texto"],
                           selectbackground=self._tema["selecao"], selectforeground=self._tema["selecao_texto"],
                           highlightthickness=1)
        for c in candidatos:
            lista.insert("end", c)
        lista.selection_set(0)
        lista.activate(0)
        lista.pack(fill="both", expand=True)
        lista.bind("<Double-Button-1>", lambda e: self.escolher_sugestao())
        lista.bind("<Return>", lambda e: self.escolher_sugestao())
        lista.bind("<Escape>", lambda e: self.fechar_sugestoes())
        caixa = self.texto.bbox("insert")
        if caixa and self.texto.winfo_ismapped():
            x = self.texto.winfo_rootx() + caixa[0]
            y = self.texto.winfo_rooty() + caixa[1] + caixa[3]
            popup.geometry(f"+{x}+{y}")
        else:
            popup.withdraw()
        self._popup, self._lista = popup, lista

    def fechar_sugestoes(self) -> None:
        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass
        self._popup, self._lista = None, None

    def escolher_sugestao(self, indice: int | None = None) -> str | None:
        """Aplica a sugestão escolhida (a marcada na lista, ou `indice`); devolve o texto inserido."""
        if not self._sugestoes:
            return None
        if indice is None:
            if self._lista is None:
                return None
            marcada = self._lista.curselection()
            indice = marcada[0] if marcada else 0
        escolha = self._sugestoes[indice]
        self.fechar_sugestoes()
        texto = self.texto
        complemento = escolha
        if self._contexto == "tag":
            complemento = escolha + ("/>" if escolha in VAZIOS else f"></{escolha}>")
        elif self._contexto == "atributo":
            complemento = escolha + '=""'
        elif self._contexto == "propriedade":
            complemento = escolha + ": "
        with self._grupo():
            if self._prefixo:
                texto.delete(f"insert-{len(self._prefixo)}c", "insert")
            texto.insert("insert", complemento)
            if self._contexto == "tag" and escolha not in VAZIOS:
                texto.mark_set("insert", f"insert-{len(escolha) + 3}c")
            elif self._contexto == "atributo":
                texto.mark_set("insert", "insert-1c")
        self._sugestoes, self._prefixo = [], ""       # aplicada: uma segunda chamada não faz nada
        return complemento

    # ------------------------------------------------------------------
    # Bem-formado, consertar, reformatar, dividir
    # ------------------------------------------------------------------

    def verificar_bem_formado(self) -> ErroDeXhtml | None:
        """Para XHTML: o erro com linha e coluna (e a linha marcada, o cursor nela), ou `None`."""
        self.texto.tag_remove("erro", "1.0", "end")
        if self.linguagem != "xhtml":
            return None
        erro = xhtml.bem_formado(self.texto_todo())
        if erro is not None:
            self.texto.tag_add("erro", f"{erro.linha}.0", f"{erro.linha}.0 lineend+1c")
            self.ir_para(erro.linha, erro.coluna)
        return erro

    def consertar(self) -> list[str]:
        """Conserta o XHTML mal-formado (`consertar.consertar`) e devolve os avisos; vazio = nada a fazer."""
        if self.linguagem != "xhtml":
            return []
        novo, avisos = consertar_mod.consertar(self.texto_todo())
        if novo != self.texto_todo():
            self._substituir_tudo(novo)
        self.texto.tag_remove("erro", "1.0", "end")
        return avisos

    def reformatar(self) -> ErroDeXhtml | None:
        """XHTML → `xhtml.canonico` (recusa o mal-formado, com o erro); CSS → `reformatar_css`. Idempotente."""
        atual = self.texto_todo()
        if self.linguagem == "xhtml":
            erro = self.verificar_bem_formado()
            if erro is not None:
                return erro
            novo = xhtml.canonico(atual)
        else:
            novo = consertar_mod.reformatar_css(atual)
        if novo != atual:
            self._substituir_tudo(novo)
        return None

    def _substituir_tudo(self, novo: str) -> None:
        linha = self.posicao[0]
        with self._grupo():
            self.texto.delete("1.0", "end")
            self.texto.insert("1.0", novo)
        self.ir_para(linha)
        self.sincronizar()

    def dividir_no_cursor(self) -> tuple[str, str] | None:
        """
        O documento partido no cursor: a primeira parte fecha o que estava aberto; a
        segunda repete a cabeça e reabre os elementos. Bem-formados os dois. `None`
        quando o cursor não está dentro de `<body>` ou o documento não está bem-formado.
        """
        if self.linguagem != "xhtml" or xhtml.bem_formado(self.texto_todo()) is not None:
            return None
        texto = self.texto
        cursor = texto.index("insert")
        antes, depois = texto.get("1.0", cursor), texto.get(cursor, "end-1c")
        pilha = self._tags_abertas(cursor)
        if "body" not in pilha:
            return None
        m_body = re.search(r"<body\b[^>]*>", antes)
        if not m_body:
            return None
        cabeca = antes[: m_body.end()]
        abertos = pilha[pilha.index("body") + 1:]
        fecha = "".join(f"</{n}>" for n in reversed(abertos))
        primeira = antes + fecha + "\n</body>\n</html>\n"
        reabre = "".join(self._tag_de_abertura(antes, n) for n in abertos)
        resto = re.sub(r"\s*</body>\s*</html>\s*$", "", depois)
        segunda = cabeca + "\n" + reabre + resto + "\n</body>\n</html>\n"
        if xhtml.bem_formado(primeira) is not None or xhtml.bem_formado(segunda) is not None:
            return None
        return primeira, segunda

    @staticmethod
    def _tag_de_abertura(antes: str, nome: str) -> str:
        """A última tag `<nome …>` aberta em `antes`, sem o `id` (que não pode repetir)."""
        ultima = None
        for m in _RE_TAG.finditer(antes):
            if m.group(2) == nome and not m.group(1) and not m.group(4):
                ultima = m
        if ultima is None:
            return f"<{nome}>"
        atributos = re.sub(r"""\s+id\s*=\s*("[^"]*"|'[^']*')""", "", ultima.group(3))
        return f"<{nome}{atributos}>"

    # ------------------------------------------------------------------
    # Ir ao alvo e voltar
    # ------------------------------------------------------------------

    def _atributo_no_cursor(self) -> tuple[str, str] | None:
        """`(nome, valor)` do atributo sob o cursor, dentro da tag sob o cursor."""
        tag = self._tag_no_cursor()
        if tag is None:
            return None
        ini_l, ini_c, fim_l, fim_c, _fecha, _nome, _vazia = tag
        texto = self.texto
        inicio = f"{ini_l}.{ini_c}"
        cru = texto.get(inicio, f"{fim_l}.{fim_c}")
        deslocamento = len(texto.get(inicio, "insert"))
        for m in _RE_ATRIBUTO_NO_CURSOR.finditer(cru):
            if m.start() <= deslocamento <= m.end():
                return m.group(1), m.group(2)
        # Fora de qualquer atributo: o primeiro href/src/class da tag serve.
        for m in _RE_ATRIBUTO_NO_CURSOR.finditer(cru):
            if m.group(1) in ("href", "src", "class"):
                return m.group(1), m.group(2)
        return None

    def ir_ao_alvo(self) -> tuple[str, str] | None:
        """
        `href`/`src` sob o cursor → `abrir_alvo(arquivo, âncora)`; `class="x"` → `abrir_alvo(folha, ".x")`
        com a folha que define `.x`. Guarda a posição para `voltar()`. Devolve o que chamou.
        """
        atributo = self._atributo_no_cursor()
        if atributo is None:
            return None
        nome, valor = atributo
        if nome in ("href", "src", "xlink:href"):
            if "://" in valor or valor.startswith(("mailto:", "data:")):
                return None
            arquivo, _, ancora = valor.partition("#")
            alvo = (arquivo, ancora)
        elif nome == "class":
            classes = valor.split()
            if not classes:
                return None
            classe = classes[0]
            folha = self._classes.get(classe)
            if folha is None:
                return None
            alvo = (folha, "." + classe)
        else:
            return None
        self._voltas.append(self.texto.index("insert"))
        if self.abrir_alvo is not None:
            self.abrir_alvo(*alvo)
        return alvo

    def voltar(self) -> bool:
        if not self._voltas:
            return False
        self.texto.mark_set("insert", self._voltas.pop())
        self.texto.see("insert")
        self._cursor_moveu()
        return True

    # ------------------------------------------------------------------
    # Zoom e tema
    # ------------------------------------------------------------------

    def zoom(self, passo: int) -> int:
        """Muda o corpo da fonte (só a superfície de edição); devolve o corpo novo."""
        novo = max(CORPO_MINIMO, min(CORPO_MAXIMO, self._corpo + int(passo)))
        if novo != self._corpo:
            self._corpo = novo
            self._fonte.configure(size=novo)
            self._fonte_negrito.configure(size=novo)
            self.texto.configure(tabs=(self._fonte.measure(self.tabulacao),))
            self._agendar_pintura()
        return novo

    def zoom_zero(self) -> int:
        return self.zoom(self._corpo_base - self._corpo)

    @property
    def corpo(self) -> int:
        return self._corpo

    def aplicar_tema(self, nome: str) -> None:
        self._tema = realce_mod.tema(nome)
        t = self._tema
        self.texto.configure(background=t["fundo"], foreground=t["texto"], insertbackground=t["cursor"],
                             selectbackground=t["selecao"], selectforeground=t["selecao_texto"],
                             inactiveselectbackground=t["selecao"])
        self.calha.configure(background=t["calha_fundo"])
        for tipo in realce_mod.TIPOS:
            self.texto.tag_configure(tipo, foreground=t[tipo])
        self.texto.tag_configure("linha_atual", background=t["linha_atual"])
        self.texto.tag_configure("casamento", background=t["casamento"])
        self.texto.tag_configure("erro", background=t["erro"])
        self._desenhar_calha()

    @property
    def tema(self) -> dict[str, str]:
        return dict(self._tema)


# ----------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------

def _depois(indice: str, n: int) -> str:
    linha, coluna = indice.split(".")
    return f"{linha}.{int(coluna) + n}"


def _attr(valor: str) -> str:
    return str(valor).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def _escapar(valor: str) -> str:
    return str(valor).replace("&", "&amp;").replace("<", "&lt;")


ATRIBUTOS_XHTML = sorted({"alt", "aria-label", "class", "dir", "epub:type", "href", "id", "lang", "rel", "role",
                          "src", "style", "title", "type", "xml:lang", "xmlns", "xmlns:epub"})
PROPRIEDADES_CSS = sorted({
    "background", "background-color", "border", "border-bottom", "border-top", "color", "display", "font",
    "font-family", "font-size", "font-style", "font-variant", "font-weight", "height", "line-height", "margin",
    "margin-bottom", "margin-left", "margin-right", "margin-top", "max-width", "orphans", "padding",
    "page-break-after", "page-break-before", "page-break-inside", "text-align", "text-decoration", "text-indent",
    "vertical-align", "white-space", "widows", "width",
})

