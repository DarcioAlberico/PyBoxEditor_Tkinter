"""
O sumário do livro: gerar dos títulos, e ler e escrever `nav.xhtml` e `toc.ncx`
(SPEC_EDITOR §9 "Table of Contents", §10.1).

**Os caminhos.** No modelo, todo `href` é relativo ao OPF (é a convenção de
`Capitulo.arquivo` e de `EntradaDeSumario.destino`). O `nav.xhtml` e o `toc.ncx`
podem morar noutra pasta (`OEBPS/nav.xhtml` hoje; `Text/nav.xhtml` no Sigil), e os
links dentro deles são relativos **a eles** — daí a conversão nos dois sentidos.

**A `page-list`.** Sai quando o livro tem marcas de página impressa
(`MarcaDePagina` e `Trecho.pagina`), e é o que o Thorium e o Apple Books usam para
"ir à página do impresso" (§6.1).

Nasce na ED-00 porque a ED-01 (`epub.escrever`) e a ED-08 (o painel) o consomem.
"""

from __future__ import annotations

import posixpath
from typing import Sequence
from xml.sax.saxutils import escape

from core.editor import modelo
from core.editor.modelo import (Capitulo, EntradaDeSumario, Lista, ItemDeLista, Livro, MarcaDePagina,
                                Paragrafo, Titulo, Trecho)

NS_XHTML = "http://www.w3.org/1999/xhtml"
NS_EPUB = "http://www.idpf.org/2007/ops"
NS_NCX = "http://www.daisy.org/z3986/2005/ncx/"


def _attr(valor: str) -> str:
    return escape(valor, {'"': "&quot;"})


def _relativo(destino: str, de_arquivo: str) -> str:
    """`destino` (relativo ao OPF) visto de dentro de `de_arquivo` (idem)."""
    caminho, _, ancora = destino.partition("#")
    pasta = posixpath.dirname(de_arquivo)
    if caminho and pasta:
        caminho = posixpath.relpath(caminho, pasta)
    return caminho + ("#" + ancora if ancora else "")


def _absoluto(href: str, de_arquivo: str) -> str:
    """O inverso: um `href` de dentro de `de_arquivo` → relativo ao OPF."""
    caminho, _, ancora = href.partition("#")
    pasta = posixpath.dirname(de_arquivo)
    if caminho and pasta:
        caminho = posixpath.normpath(posixpath.join(pasta, caminho))
    return caminho + ("#" + ancora if ancora else "")


# ----------------------------------------------------------------------
# Gerar dos títulos
# ----------------------------------------------------------------------

def gerar_dos_titulos(livro: Livro, niveis: Sequence[int] = (1, 2)) -> list[EntradaDeSumario]:
    """
    Uma entrada por `Titulo` de nível em `niveis`, aninhada pelo nível. Num livro sem
    nenhum título desses níveis, uma entrada por capítulo (o "Página N" de hoje) —
    um sumário vazio é o que o leitor mostra como livro sem navegação.
    """
    niveis = tuple(sorted(set(int(n) for n in niveis)))
    raiz: list[EntradaDeSumario] = []
    pilha: list[tuple[int, EntradaDeSumario]] = []
    for cap in livro.capitulos:
        for bloco in cap.blocos:
            if not isinstance(bloco, Titulo) or bloco.nivel not in niveis:
                continue
            bloco.id_persistente = True
            entrada = EntradaDeSumario(rotulo=modelo.texto_de(bloco).strip() or cap.titulo_efetivo,
                                       destino=f"{cap.arquivo}#{bloco.id}")
            while pilha and pilha[-1][0] >= bloco.nivel:
                pilha.pop()
            (pilha[-1][1].filhos if pilha else raiz).append(entrada)
            pilha.append((bloco.nivel, entrada))
    if not raiz:
        raiz = [EntradaDeSumario(rotulo=cap.titulo_efetivo, destino=cap.arquivo) for cap in livro.capitulos]
    return raiz


def marcas_de_pagina(livro: Livro) -> list[tuple[int, str]]:
    """`(página, destino)` de toda marca impressa, na ordem de leitura."""
    saida: list[tuple[int, str]] = []
    for cap in livro.capitulos:
        for bloco in modelo.blocos_do_capitulo(cap):
            if isinstance(bloco, MarcaDePagina):
                saida.append((bloco.pagina, f"{cap.arquivo}#{bloco.id}"))
            for trecho in modelo._todos_os_trechos(bloco):
                if trecho.pagina is not None:
                    saida.append((trecho.pagina, f"{cap.arquivo}#pg-{trecho.pagina}"))
    return saida


# ----------------------------------------------------------------------
# nav.xhtml
# ----------------------------------------------------------------------

def _ol(entradas: Sequence[EntradaDeSumario], de_arquivo: str, nivel: int) -> str:
    recuo = "  " * nivel
    itens = []
    for entrada in entradas:
        filhos = ("\n" + _ol(entrada.filhos, de_arquivo, nivel + 2) + "\n" + recuo + "  ") if entrada.filhos else ""
        itens.append(f'{recuo}  <li><a href="{_attr(_relativo(entrada.destino, de_arquivo))}">'
                     f"{escape(entrada.rotulo)}</a>{filhos}</li>")
    return f"{recuo}<ol>\n" + "\n".join(itens) + f"\n{recuo}</ol>"


def escrever_nav(livro: Livro, titulo_do_sumario: str = "Sumário") -> str:
    """O `nav.xhtml` com `toc`, `landmarks` (quando há marcos) e `page-list` (quando há marcas)."""
    nav = livro.nav
    partes = [
        '<?xml version="1.0" encoding="utf-8"?>',
        "<!DOCTYPE html>",
        f'<html xmlns="{NS_XHTML}" xmlns:epub="{NS_EPUB}" lang="{_attr(livro.metadados.idioma)}" '
        f'xml:lang="{_attr(livro.metadados.idioma)}">',
        f"<head>\n<title>{escape(titulo_do_sumario)}</title>\n</head>",
        "<body>",
        f'<nav epub:type="toc" id="toc">\n<h1>{escape(titulo_do_sumario)}</h1>',
        _ol(livro.sumario, nav, 0) if livro.sumario else "<ol>\n</ol>",
        "</nav>",
    ]
    if livro.marcos:
        itens = "\n".join(
            f'  <li><a epub:type="{_attr(tipo)}" href="{_attr(_relativo(destino, nav))}">'
            f"{escape(_rotulo_do_marco(tipo))}</a></li>"
            for tipo, destino in livro.marcos)
        partes.append(f'<nav epub:type="landmarks" hidden="hidden">\n<ol>\n{itens}\n</ol>\n</nav>')
    marcas = marcas_de_pagina(livro)
    if marcas:
        itens = "\n".join(f'  <li><a href="{_attr(_relativo(destino, nav))}">{pagina}</a></li>'
                          for pagina, destino in marcas)
        partes.append(f'<nav epub:type="page-list" hidden="hidden">\n<ol>\n{itens}\n</ol>\n</nav>')
    partes.append("</body>\n</html>\n")
    return "\n".join(partes)


ROTULOS_DOS_MARCOS = {
    "cover": "Capa", "toc": "Sumário", "bodymatter": "Início do texto", "titlepage": "Folha de rosto",
    "frontmatter": "Pré-texto", "backmatter": "Pós-texto", "preface": "Prefácio", "index": "Índice",
    "glossary": "Chave de símbolos", "bibliography": "Bibliografia", "appendix": "Apêndice",
}


def _rotulo_do_marco(tipo: str) -> str:
    return ROTULOS_DOS_MARCOS.get(tipo, tipo)


Sumario = list[EntradaDeSumario]


def ler_nav(texto: str | bytes, nav: str) -> tuple[Sumario, list[tuple[str, str]], list[tuple[int, str]]]:
    """`(sumário, marcos, page-list)` de um `nav.xhtml`; os destinos voltam relativos ao OPF."""
    from core.editor import xhtml

    doc = xhtml.analisar(texto)
    sumario: list[EntradaDeSumario] = []
    marcos: list[tuple[str, str]] = []
    paginas: list[tuple[int, str]] = []

    def entradas(ol: xhtml.No) -> list[EntradaDeSumario]:
        saida = []
        for li in ol.elementos():
            if li.nome != "li":
                continue
            ancora = next((e for e in li.elementos() if e.nome == "a"), None)
            rotulo = (ancora.texto() if ancora is not None
                      else next((e.texto() for e in li.elementos() if e.nome == "span"), "")).strip()
            destino = _absoluto(ancora.attrs.get("href", ""), nav) if ancora is not None else ""
            filhos_ol = next((e for e in li.elementos() if e.nome == "ol"), None)
            saida.append(EntradaDeSumario(rotulo=rotulo, destino=destino,
                                          filhos=entradas(filhos_ol) if filhos_ol is not None else []))
        return saida

    def navs(no: xhtml.No):
        for e in no.elementos():
            if e.nome == "nav":
                yield e
            else:
                yield from navs(e)

    for nav_no in navs(doc.raiz):
        tipo = nav_no.attrs.get("epub:type", "")
        ol = next((e for e in nav_no.elementos() if e.nome == "ol"), None)
        if ol is None:
            continue
        if "toc" in tipo.split():
            sumario = entradas(ol)
        elif "landmarks" in tipo.split():
            for li in ol.elementos():
                a = next((e for e in li.elementos() if e.nome == "a"), None)
                if a is not None and a.attrs.get("epub:type"):
                    marcos.append((a.attrs["epub:type"], _absoluto(a.attrs.get("href", ""), nav)))
        elif "page-list" in tipo.split():
            for li in ol.elementos():
                a = next((e for e in li.elementos() if e.nome == "a"), None)
                if a is not None and a.texto().strip().isdigit():
                    paginas.append((int(a.texto().strip()), _absoluto(a.attrs.get("href", ""), nav)))
    return sumario, marcos, paginas


# ----------------------------------------------------------------------
# toc.ncx (compatibilidade)
# ----------------------------------------------------------------------

def escrever_ncx(livro: Livro) -> str:
    """O NCX do EPUB 2, para leitores antigos: `dtb:uid` igual ao identificador (`NCX-001`)."""
    ncx = livro.ncx or "toc.ncx"
    contador = [0]

    def pontos(entradas: Sequence[EntradaDeSumario], nivel: int) -> str:
        recuo = "  " * nivel
        saida = []
        for entrada in entradas:
            contador[0] += 1
            n = contador[0]
            filhos = ("\n" + pontos(entrada.filhos, nivel + 1)) if entrada.filhos else ""
            saida.append(
                f'{recuo}<navPoint id="navPoint-{n}" playOrder="{n}">\n'
                f"{recuo}  <navLabel><text>{escape(entrada.rotulo)}</text></navLabel>\n"
                f'{recuo}  <content src="{_attr(_relativo(entrada.destino, ncx))}"/>{filhos}\n'
                f"{recuo}</navPoint>")
        return "\n".join(saida)

    profundidade = _profundidade(livro.sumario)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<ncx xmlns="{NS_NCX}" version="2005-1">\n'
        "<head>\n"
        f'  <meta name="dtb:uid" content="{_attr(livro.metadados.identificador)}"/>\n'
        f'  <meta name="dtb:depth" content="{max(profundidade, 1)}"/>\n'
        '  <meta name="dtb:totalPageCount" content="0"/>\n'
        '  <meta name="dtb:maxPageNumber" content="0"/>\n'
        "</head>\n"
        f"<docTitle><text>{escape(livro.metadados.titulo)}</text></docTitle>\n"
        "<navMap>\n" + pontos(livro.sumario, 1) + "\n</navMap>\n</ncx>\n"
    )


def _profundidade(entradas: Sequence[EntradaDeSumario]) -> int:
    return max((1 + _profundidade(e.filhos) for e in entradas), default=0)


def ler_ncx(texto: str | bytes, ncx: str) -> list[EntradaDeSumario]:
    """O sumário de um `toc.ncx`, com destinos relativos ao OPF."""
    from core.editor import xhtml

    doc = xhtml.analisar(texto)

    def pontos(no: xhtml.No) -> list[EntradaDeSumario]:
        saida = []
        for filho in no.elementos():
            if not filho.nome.endswith("navPoint"):
                continue
            rotulo = ""
            destino = ""
            for e in filho.elementos():
                if e.nome.endswith("navLabel"):
                    rotulo = e.texto().strip()
                elif e.nome.endswith("content"):
                    destino = _absoluto(e.attrs.get("src", ""), ncx)
            saida.append(EntradaDeSumario(rotulo=rotulo, destino=destino, filhos=pontos(filho)))
        return saida

    mapa = next((e for e in doc.raiz.elementos() if e.nome.endswith("navMap")), None)
    return pontos(mapa) if mapa is not None else []


# ----------------------------------------------------------------------
# A página de sumário visível
# ----------------------------------------------------------------------

def pagina_de_sumario(livro: Livro, arquivo: str = "Text/sumario.xhtml",
                      titulo: str = "Sumário") -> Capitulo:
    """
    O sumário como página do livro (`epub:type="toc"` visível) — o `nav` não aparece
    em todo leitor, e o Sigil tem "Create HTML TOC" por isso.
    """
    def lista(entradas: Sequence[EntradaDeSumario]) -> Lista:
        itens = []
        for entrada in entradas:
            paragrafo = Paragrafo(trechos=[Trecho(texto=entrada.rotulo, link=entrada.destino)])
            itens.append(ItemDeLista(paragrafos=[paragrafo],
                                     filhos=lista(entrada.filhos) if entrada.filhos else None))
        return Lista(ordenada=False, itens=itens)

    cap = Capitulo(arquivo=arquivo, titulo=titulo, semantica="toc")
    cap.blocos = [Titulo(trechos=[Trecho(texto=titulo)], nivel=1), lista(livro.sumario)]
    cap.folhas = list(livro.folhas[:1])
    return cap


def _todos(entradas: Sequence[EntradaDeSumario]) -> list[EntradaDeSumario]:
    saida: list[EntradaDeSumario] = []
    for e in entradas:
        saida.append(e)
        saida.extend(_todos(e.filhos))
    return saida


def destinos_quebrados(livro: Livro) -> list[str]:
    """As entradas do sumário cujo destino não existe (capítulo ou âncora)."""
    ids = {cap.arquivo: {b.id for b in modelo.blocos_do_capitulo(cap)} | {n.id for n in cap.notas}
           for cap in livro.capitulos}
    quebrados = []
    for entrada in _todos(livro.sumario):
        arquivo, _, ancora = entrada.destino.partition("#")
        if arquivo not in ids or (ancora and ancora not in ids[arquivo] and not ancora.startswith("pg-")):
            quebrados.append(entrada.destino)
    return quebrados


def renomear_destinos(entradas: Sequence[EntradaDeSumario], de: str, para: str) -> int:
    """Troca o arquivo dos destinos (quem renomeou um capítulo chama isto); devolve quantos."""
    n = 0
    for entrada in _todos(entradas):
        arquivo, sep, ancora = entrada.destino.partition("#")
        if arquivo == de:
            entrada.destino = para + sep + ancora
            n += 1
    return n

