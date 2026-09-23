"""
A tabela de atalhos da janela de edição (SPEC_EDITOR §7.4) e a sua ligação aos
widgets (ED-02).

## Uma tabela, uma fonte

Cada linha da §7.4 é um `Atalho`: o texto que o menu mostra (`Ctrl+Shift+S`), a
sequência Tk que o dispara, o **nome do comando** em `janela.comandos`, os modos em
que vale e o rótulo da ajuda. É daqui que `ui/editor/menus.py` tira o `accelerator`
de cada item (AC-ED02-1: todo atalho tem item de menu) e que "Ajuda → Atalhos" é
escrita (`texto_de_ajuda`). `verificar_unicidade` garante que um acorde tem um
comando por modo.

## Por que a bindtag vai na frente do widget

O `tk.Text` traz os acordes do emacs (`Ctrl+D` apaga, `Ctrl+O` abre linha, `Ctrl+T`
troca letras, `Ctrl+K` mata a linha…) e os dois editores (ED-03, ED-07) já os
neutralizam na própria bindtag devolvendo `"break"` — o que também impede que a
janela os veja. Por isso `ligar` põe a bindtag da janela **antes** da do editor:
o acorde da tabela é despachado para `janela.comandos[nome]` e devolve `"break"`
— também quando o acorde é de outro modo (`Ctrl+Shift+Space` no código não faz
nada, em vez de cair no `Ctrl+Space` do widget) ou quando o comando ainda não
existe (a fase seguinte); só o que a tabela não conhece devolve `None` e segue
para o editor e para a classe `Text`. O despacho consulta o dicionário **na
hora**, e é o que deixa o teste trocar um comando por um espião (§14).

Os acordes com dígito (`Ctrl+1`, `Alt+3`, `Ctrl+Shift+8`, `Ctrl+0`) são casados por
**keycode**, porque o keysym depende do leiaute (`Shift+8` é `asterisk` no ABNT2 e
`parenleft` no americano); no Windows o keycode do dígito é o seu ASCII. O `Alt`
exige `Control` solto — `AltGr` chega como `Control+Alt`.

## Escopos

`janela`: vale com o foco em qualquer lugar (arquivo, exibir, navegação, ajuda):
entra na frente dos editores **e** na própria janela. `editor`: só na frente dos
editores — recortar, colar e negrito com o foco numa caixa de busca não devem agir
sobre o capítulo. `fundo`: só na janela, depois de o widget ter a sua vez (`Esc`
fecha a lista de sugestões do código antes de devolver o foco ao editor).
"""

from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

AMBOS = ("texto", "codigo")
TEXTO = ("texto",)
CODIGO = ("codigo",)
BINDTAG_BASE = "EditorJanela"
#: Estado do evento no Tk: Shift, Control e (no Windows) Alt.
SHIFT, CONTROL, ALT = 0x1, 0x4, 0x20000
GENERICAS = ("<Control-Key>", "<Control-Shift-Key>", "<Alt-Key>")


@dataclass(frozen=True)
class Atalho:
    """Uma linha da §7.4."""

    atalho: str                        # como aparece no menu e na ajuda: "Ctrl+Shift+S"
    sequencia: str                     # a sequência Tk ("<<Paste>>", "<Control-Shift-S>", genérica com keycode)
    comando: str                       # nome em `janela.comandos`; "" quando nativo ou contextual
    modos: tuple[str, ...]             # TEXTO, CODIGO ou AMBOS
    rotulo: str                        # o que a ajuda lista
    escopo: str = "editor"             # "janela" | "editor" | "fundo"
    keycode: int | None = None         # dígito casado por keycode (o ASCII do dígito no Windows)
    tipo: str = "comando"              # "comando" | "nativo" | "contextual"

    def chave(self) -> tuple[str, int | None]:
        return self.sequencia, self.keycode


def _a(atalho: str, sequencia: str, comando: str, modos: tuple[str, ...], rotulo: str, escopo: str = "editor",
       keycode: int | None = None, tipo: str = "comando") -> Atalho:
    return Atalho(atalho, sequencia, comando, modos, rotulo, escopo, keycode, tipo)


def _digito(d: str) -> int:
    return ord(d)


#: A §7.4, linha a linha. A ordem é a da spec; é a ordem da ajuda.
TABELA: tuple[Atalho, ...] = (
    _a("Ctrl+N", "<Control-n>", "novo", AMBOS, "novo livro", "janela"),
    _a("Ctrl+O", "<Control-o>", "abrir", AMBOS, "abrir…", "janela"),
    _a("Ctrl+S", "<Control-s>", "salvar", AMBOS, "salvar", "janela"),
    _a("Ctrl+Shift+S", "<Control-Shift-S>", "salvar_como", AMBOS, "salvar como…", "janela"),
    _a("Ctrl+Shift+E", "<Control-Shift-E>", "exportar", AMBOS, "exportar… (caixa de formato)", "janela"),
    _a("Ctrl+P", "<Control-p>", "imprimir", AMBOS, "imprimir (PDF paginado)", "janela"),
    _a("Ctrl+W", "<Control-w>", "fechar_aba", AMBOS, "fechar aba", "janela"),
    _a("Ctrl+Shift+W", "<Control-Shift-W>", "fechar_livro", AMBOS, "fechar livro", "janela"),
    _a("Ctrl+Z", "<<Undo>>", "desfazer", AMBOS, "desfazer"),
    _a("Ctrl+Y", "<<Redo>>", "refazer", AMBOS, "refazer"),
    _a("Ctrl+X", "<<Cut>>", "recortar", AMBOS, "recortar"),
    _a("Ctrl+C", "<<Copy>>", "copiar", AMBOS, "copiar"),
    _a("Ctrl+V", "<<Paste>>", "colar", AMBOS, "colar"),
    _a("Ctrl+Shift+V", "<Control-Shift-V>", "colar_sem_formatacao", AMBOS, "colar sem formatação"),
    _a("Ctrl+A", "<<SelectAll>>", "selecionar_tudo", AMBOS, "selecionar tudo"),
    _a("Ctrl+F", "<Control-f>", "localizar", AMBOS, "localizar…", "janela"),
    _a("Ctrl+H", "<Control-h>", "substituir", AMBOS, "substituir…", "janela"),
    _a("F3", "<F3>", "localizar_proximo", AMBOS, "localizar próximo (circular)", "janela"),
    _a("Shift+F3", "<Shift-F3>", "localizar_anterior", AMBOS, "localizar anterior (circular)", "janela"),
    _a("Ctrl+G", "<Control-g>", "ir_para", AMBOS, "ir para…", "janela"),
    _a("Ctrl+B", "<Control-b>", "negrito", AMBOS, "negrito (código: envolve em <strong>)"),
    _a("Ctrl+I", "<Control-i>", "italico", AMBOS, "itálico (código: envolve em <em>)"),
    _a("Ctrl+U", "<Control-u>", "sublinhado", AMBOS, "sublinhado (código: envolve em <u>)"),
    _a("Ctrl+Shift+K", "<Control-Shift-K>", "versalete", TEXTO, "versalete"),
    _a("Ctrl+=", "<Control-equal>", "subscrito", TEXTO, "subscrito"),
    _a("Ctrl+Shift+=", "<Control-plus>", "sobrescrito", TEXTO, "sobrescrito"),
    _a("Ctrl+Shift+>", "<Control-greater>", "aumentar_fonte", TEXTO, "aumentar fonte"),
    _a("Ctrl+Shift+<", "<Control-less>", "diminuir_fonte", TEXTO, "diminuir fonte"),
    _a("Ctrl+D", "<Control-d>", "fonte", TEXTO, "fonte…"),
    _a("Ctrl+L", "<Control-l>", "alinhar_esquerda", TEXTO, "alinhar à esquerda"),
    _a("Ctrl+E", "<Control-e>", "alinhar_centro", TEXTO, "centralizar"),
    _a("Ctrl+R", "<Control-r>", "alinhar_direita", TEXTO, "alinhar à direita"),
    _a("Ctrl+J", "<Control-j>", "justificar", TEXTO, "justificar"),
    _a("Ctrl+M", "<Control-m>", "recuar", TEXTO, "recuar"),
    _a("Ctrl+Shift+M", "<Control-Shift-M>", "diminuir_recuo", TEXTO, "diminuir recuo"),
    _a("Ctrl+1", "<Control-Key>", "entrelinha_1", TEXTO, "entrelinha simples", keycode=_digito("1")),
    _a("Ctrl+5", "<Control-Key>", "entrelinha_15", TEXTO, "entrelinha 1,5", keycode=_digito("5")),
    _a("Ctrl+2", "<Control-Key>", "entrelinha_2", TEXTO, "entrelinha dupla", keycode=_digito("2")),
    _a("Alt+1", "<Alt-Key>", "estilo_titulo1", TEXTO, "título 1", keycode=_digito("1")),
    _a("Alt+2", "<Alt-Key>", "estilo_titulo2", TEXTO, "título 2", keycode=_digito("2")),
    _a("Alt+3", "<Alt-Key>", "estilo_titulo3", TEXTO, "título 3", keycode=_digito("3")),
    _a("Alt+4", "<Alt-Key>", "estilo_titulo4", TEXTO, "título 4", keycode=_digito("4")),
    _a("Alt+5", "<Alt-Key>", "estilo_titulo5", TEXTO, "título 5", keycode=_digito("5")),
    _a("Alt+6", "<Alt-Key>", "estilo_titulo6", TEXTO, "título 6", keycode=_digito("6")),
    _a("Ctrl+Shift+N", "<Control-Shift-N>", "estilo_corpo", TEXTO, "estilo corpo"),
    _a("Ctrl+Shift+L", "<Control-Shift-L>", "marcadores", TEXTO, "marcadores"),
    _a("Ctrl+Shift+O", "<Control-Shift-O>", "numeracao", TEXTO, "numeração"),
    _a("Ctrl+Space", "<Control-space>", "limpar_caractere", TEXTO, "limpar formatação de caractere"),
    _a("Ctrl+Space", "<Control-space>", "autocompletar", CODIGO, "autocompletar"),
    _a("Ctrl+Q", "<Control-q>", "limpar_paragrafo", TEXTO, "limpar formatação de parágrafo"),
    _a("Ctrl+BackSpace", "<Control-BackSpace>", "apagar_palavra_anterior", AMBOS, "apagar palavra anterior"),
    _a("Ctrl+Delete", "<Control-Delete>", "apagar_palavra_seguinte", AMBOS, "apagar palavra seguinte"),
    _a("Ctrl+K", "<Control-k>", "inserir_link", AMBOS, "link…"),
    _a("Enter", "<Return>", "", TEXTO, "sobre um objeto: a ação principal (diagrama → editor de posição; "
       "tabela → primeira célula; referência de nota → a nota; demais → propriedades)", tipo="contextual"),
    _a("Alt+Enter", "<Alt-Return>", "propriedades_do_objeto", TEXTO, "propriedades do objeto ou parágrafo"),
    _a("Shift+Enter", "<Shift-Return>", "quebra_de_linha", TEXTO, "quebra de linha suave"),
    _a("Ctrl+Enter", "<Control-Return>", "quebra_de_pagina", TEXTO, "quebra de página"),
    _a("Ctrl+Enter", "<Control-Return>", "dividir_capitulo", CODIGO, "dividir capítulo no cursor"),
    _a("Ctrl+Shift+Enter", "<Control-Shift-Return>", "dividir_capitulo", TEXTO, "dividir capítulo aqui"),
    _a("Ctrl+Shift+Space", "<Control-Shift-space>", "espaco_inseparavel", TEXTO, "espaço inseparável"),
    _a("Ctrl+Shift+-", "<Control-underscore>", "hifen_inseparavel", TEXTO, "hífen inseparável"),
    _a("Ctrl+-", "<Control-minus>", "hifen_opcional", TEXTO, "hífen opcional"),
    _a("Ctrl+Shift+X", "<Control-Shift-X>", "codigo_unicode", TEXTO, "código Unicode ↔ caractere"),
    _a("Ctrl+Shift+D", "<Control-Shift-D>", "inserir_diagrama", AMBOS, "inserir diagrama…", "janela"),
    _a("Ctrl+Shift+P", "<Control-Shift-P>", "editar_posicao", AMBOS, "editar posição…", "janela"),
    _a("Ctrl+Shift+G", "<Control-Shift-G>", "diagrama_dos_lances", AMBOS, "diagrama a partir dos lances", "janela"),
    _a("Ctrl+Shift+F", "<Control-Shift-F>", "paleta_de_figurinas", AMBOS, "foco na paleta de figurinas", "janela"),
    _a("F7", "<F7>", "ortografia", AMBOS, "verificar ortografia…", "janela"),
    _a("Ctrl+Shift+8", "<Control-Shift-Key>", "invisiveis", TEXTO, "mostrar invisíveis", keycode=_digito("8")),
    _a("Ctrl+Num +", "<Control-KP_Add>", "zoom_mais", AMBOS, "zoom (mais Ctrl+roda)", "janela"),
    _a("Ctrl+Num -", "<Control-KP_Subtract>", "zoom_menos", AMBOS, "zoom", "janela"),
    _a("Ctrl+0", "<Control-Key>", "zoom_zero", AMBOS, "zoom 100%", "janela", keycode=_digito("0")),
    _a("F11", "<F11>", "alternar_modo", AMBOS, "alternar modo texto/código", "janela"),
    _a("F12", "<F12>", "previa", CODIGO, "prévia", "janela"),
    _a("Ctrl+PageDown", "<Control-Next>", "capitulo_seguinte", AMBOS, "capítulo seguinte", "janela"),
    _a("Ctrl+PageUp", "<Control-Prior>", "capitulo_anterior", AMBOS, "capítulo anterior", "janela"),
    _a("Ctrl+Tab", "<Control-Tab>", "foco_seguinte", AMBOS, "sair do editor (nativo do Text)", tipo="nativo"),
    _a("Ctrl+Shift+Tab", "<Control-Shift-Tab>", "foco_anterior", AMBOS, "sair do editor, para trás (nativo)",
       tipo="nativo"),
    _a("Ctrl+T", "<Control-t>", "sumario_editar", AMBOS, "sumário (editar)", "janela"),
    _a("F8", "<F8>", "metadados", AMBOS, "metadados…", "janela"),
    _a("Alt+F7", "<Alt-F7>", "bem_formado", CODIGO, "verificar bem-formado", "janela"),
    _a("Alt+F8", "<Alt-F8>", "consertar", CODIGO, "consertar HTML", "janela"),
    _a("Alt+F9", "<Alt-F9>", "validar_epub", CODIGO, "validar EPUB", "janela"),
    _a("Ctrl+Shift+I", "<Control-Shift-I>", "reformatar", CODIGO, "reformatar XHTML"),
    _a("Ctrl+/", "<Control-slash>", "comentar", CODIGO, "comentar / descomentar"),
    _a("Ctrl+Shift+J", "<Control-Shift-J>", "clipes", CODIGO, "clipes…", "janela"),
    _a("F6", "<F6>", "painel_seguinte", AMBOS, "painel seguinte", "janela"),
    _a("Shift+F6", "<Shift-F6>", "painel_anterior", AMBOS, "painel anterior", "janela"),
    _a("Shift+F10", "<Shift-F10>", "menu_de_contexto", AMBOS, "menu de contexto", "janela", tipo="contextual"),
    _a("Menu", "<Key-App>", "menu_de_contexto", AMBOS, "menu de contexto (tecla de menu, Windows)", "janela",
       tipo="contextual"),
    _a("Menu", "<Key-Menu>", "menu_de_contexto", AMBOS, "menu de contexto (tecla de menu, X11)", "janela",
       tipo="contextual"),
    _a("F1", "<F1>", "atalhos", AMBOS, "atalhos de teclado…", "janela"),
    _a("Esc", "<Escape>", "escape", AMBOS, "foco de volta ao editor; fecha a busca; sai de tabela, objeto ou nota",
       "fundo", tipo="contextual"),
)

#: O que o `Text` faria sozinho e a janela não deixa: colar a seleção primária.
NEUTRALIZADAS = ("<Key-Insert>", "<<PasteSelection>>")

#: A tecla de menu tem dois nomes, `App` no Tk do Windows e `Menu` no X11, e a tabela traz
#: os dois. O Tk do Windows aceita os dois; o do X11 recusa `App` no `bind` ("bad event type
#: or keysym") e derruba a janela inteira — por isso `ligar` o deixa de fora fora do Windows.
SO_NO_WINDOWS = frozenset({"<Key-App>"})


# ----------------------------------------------------------------------
# Consultas à tabela
# ----------------------------------------------------------------------

def por_comando(tabela: Sequence[Atalho] = TABELA) -> dict[str, list[Atalho]]:
    saida: dict[str, list[Atalho]] = {}
    for a in tabela:
        if a.comando:
            saida.setdefault(a.comando, []).append(a)
    return saida


def acelerador(comando: str, tabela: Sequence[Atalho] = TABELA) -> str:
    """O texto do `accelerator` do item de menu: o primeiro atalho do comando, ou ""."""
    for a in tabela:
        if a.comando == comando and a.tipo == "comando":
            return a.atalho
    return ""


def verificar_unicidade(tabela: Sequence[Atalho] = TABELA) -> list[str]:
    """
    Os conflitos: o mesmo acorde (sequência + keycode) com dois comandos no mesmo
    modo, ou o mesmo comando com dois acordes no mesmo modo sem ser variante da tecla
    de menu. Vazio é o que se quer.
    """
    conflitos: list[str] = []
    vistos: dict[tuple[str, int | None, str], Atalho] = {}
    for a in tabela:
        for modo in a.modos:
            chave = (a.sequencia, a.keycode, modo)
            outro = vistos.get(chave)
            if outro is not None and outro.comando != a.comando:
                conflitos.append(f"{a.atalho} ({modo}): {outro.comando or outro.tipo!r} e {a.comando or a.tipo!r}")
            vistos.setdefault(chave, a)
    textos: dict[tuple[str, str], str] = {}
    for a in tabela:
        for modo in a.modos:
            chave = (a.atalho, modo)
            if chave in textos and textos[chave] != a.comando:
                conflitos.append(f"o texto {a.atalho!r} ({modo}) aparece com {textos[chave]!r} e {a.comando!r}")
            textos.setdefault(chave, a.comando)
    return conflitos


def texto_de_ajuda(tabela: Sequence[Atalho] = TABELA) -> str:
    """"Ajuda → Atalhos": uma linha por acorde, com o modo; os nativos e contextuais constam."""
    largura = max(len(a.atalho) for a in tabela)
    linhas = ["Atalhos de teclado do editor de livros", "", f"{'Atalho':{largura}}  Ação  [modo]", ""]
    for a in tabela:
        modo = "ambos" if set(a.modos) == set(AMBOS) else a.modos[0]
        sufixo = {"nativo": " (nativo)", "contextual": " (contextual)"}.get(a.tipo, "")
        linhas.append(f"{a.atalho:{largura}}  {a.rotulo}{sufixo}  [{modo}]")
    linhas += ["", "Numa tabela: Tab/Shift+Tab entre células; seta para cima na primeira fila e para baixo na "
               "última saem para o bloco vizinho; Esc sai.",
               "Sobre um objeto: Enter, Alt+Enter, Del.",
               "Nenhum Ctrl+Alt (AltGr) e nenhum Alt+letra (mnemônicos dos menus)."]
    return "\n".join(linhas)


# ----------------------------------------------------------------------
# Ligação
# ----------------------------------------------------------------------

def _casa_keycode(a: Atalho, evento: Any) -> bool:
    keycode = getattr(evento, "keycode", None)
    estado = getattr(evento, "state", 0) or 0
    if not isinstance(estado, int):
        estado = 0
    if a.sequencia == "<Alt-Key>" and estado & CONTROL:
        return False                                         # AltGr
    if a.sequencia == "<Control-Key>" and estado & SHIFT:
        return False
    if keycode == a.keycode:
        return True
    # Fora do Windows o keycode é outro; o keysym do dígito sem Shift ainda serve.
    keysym = getattr(evento, "keysym", "")
    return not sys.platform.startswith("win") and keysym == chr(a.keycode)


class Ligacao:
    """O que `ligar` devolve: a bindtag, os atalhos por sequência e os handlers (o teste os chama com um evento)."""

    def __init__(self, bindtag: str, sequencias: dict[str, list[Atalho]],
                 handlers: dict[str, Callable[[Any], str | None]]):
        self.bindtag = bindtag
        self.sequencias = sequencias
        self.handlers = handlers


def ligar(widget: tk.Misc, tabela: Sequence[Atalho], comandos: dict[str, Callable[..., Any]],
          modo: Callable[[], str] = lambda: "texto", *, escopos: Iterable[str] = ("janela", "editor"),
          frente: bool = True, bindtag: str | None = None) -> Ligacao:
    """
    Liga os acordes de `tabela` (dos `escopos` dados) a `widget`.

    `frente=True`: numa bindtag própria, posta antes das do widget — é o modo dos dois
    editores. `frente=False`: no próprio widget (`bind`), para a janela, que assim
    recebe o acorde de qualquer filho depois de o filho ter a sua vez. O despacho
    consulta `comandos` e `modo()` a cada tecla.
    """
    escopos = set(escopos)
    sequencias: dict[str, list[Atalho]] = {}
    for a in tabela:
        if a.escopo in escopos and a.sequencia:
            sequencias.setdefault(a.sequencia, []).append(a)
    nome = bindtag or f"{BINDTAG_BASE}{widget.winfo_toplevel()._w.replace('.', '_')}"

    def fazer_handler(sequencia: str) -> Callable[[Any], str | None]:
        candidatos = sequencias[sequencia]

        def despachar(evento: Any) -> str | None:
            atual = modo()
            e_da_tabela = False
            for a in candidatos:
                if a.keycode is not None and not _casa_keycode(a, evento):
                    continue
                e_da_tabela = True
                if atual not in a.modos or not (a.comando or a.tipo == "nativo"):
                    continue
                if a.tipo == "nativo":
                    alvo = getattr(evento, "widget", widget)
                    proximo = alvo.tk_focusNext() if a.comando == "foco_seguinte" else alvo.tk_focusPrev()
                    if proximo is not None:
                        proximo.focus_set()
                    return "break"
                comando = comandos.get(a.comando)
                if comando is not None:
                    comando()
                return "break"
            # Acorde da tabela, mas de outro modo (ou só contextual): não faz nada aqui e não deixa o
            # `Text` fazer o dele — um acorde, um comando por modo. Acorde que a tabela não conhece
            # (o `<Control-Key>` genérico com outro dígito) segue para o widget.
            return "break" if e_da_tabela else None
        return despachar

    handlers = {sequencia: fazer_handler(sequencia) for sequencia in sequencias}
    fora = frozenset() if str(widget.tk.call("tk", "windowingsystem")) == "win32" else SO_NO_WINDOWS
    if frente:
        tags = list(widget.bindtags())
        if nome not in tags:
            tags.insert(1, nome)
            widget.bindtags(tuple(tags))
        for sequencia, handler in handlers.items():
            if sequencia not in fora:
                widget.bind_class(nome, sequencia, handler)
        for sequencia in NEUTRALIZADAS:
            widget.bind_class(nome, sequencia, lambda e: "break")
    else:
        for sequencia, handler in handlers.items():
            if sequencia not in fora:
                widget.bind(sequencia, handler)
    return Ligacao(nome, sequencias, handlers)


__all__ = ["Atalho", "TABELA", "AMBOS", "TEXTO", "CODIGO", "NEUTRALIZADAS", "GENERICAS", "ligar", "Ligacao",
           "verificar_unicidade", "texto_de_ajuda", "acelerador", "por_comando"]
