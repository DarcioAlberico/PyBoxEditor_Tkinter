"""
O livro em HTML — um arquivo só, ou uma pasta — e o HTML/XHTML solto que vira livro
(ED-10; SPEC_EDITOR §10.2, §10.6, §10.7, §10.8).

## Escrever: HTML5, não XHTML

O capítulo é escrito pelo `xhtml.escrever` de sempre e **relido como árvore**
(`xhtml.analisar`), e é a árvore que sai como HTML5: sem declaração XML, sem
`xmlns:epub`, `epub:type` traduzido para o `role` DPUB-ARIA (o do `<body>` vai para a
`<section>` do capítulo), elemento vazio como `<br>` e elemento **não vazio** vazio
como `<span></span>` — num HTML servido como `text/html`, um `<span …/>` não fecha
nada e engole o resto do parágrafo, e é por isso que o texto do XHTML não pode ser
copiado com um `replace`.

**Arquivo único**: a CSS entra inline (com os `url()` das fontes e imagens em `data:`),
toda imagem vira `data:`, cada capítulo é uma `<section role="doc-chapter"
id="<arquivo>">`, todo `id` ganha o prefixo `<arquivo>__` (um `id="title"` em cada
capítulo é comum, INV-01) e todo link interno é reescrito para `#<arquivo>__<id>`.
**Pasta**: um `index.html` com o sumário e os marcos, um `.html` por capítulo no lugar
do `.xhtml`, os recursos copiados byte a byte onde estavam, e os links `.xhtml` →
`.html`.

## Ler: o que se aceita, e o que se registra

Um HTML5 solto raramente é XML: `<meta charset>` sem barra, `<b>` sem fechar, `&nbsp;`.
O texto passa por `consertar` (ED-07), e **cada conserto é um aviso** no relatório; os
sinônimos (`<b>`, `<i>`, `<strike>`, `<del>`, `<ins>`) são contados antes e registrados
como normalização; `role="doc-…"` sem `epub:type` ganha o `epub:type` de volta, para o
dialeto reconhecer nota, marca de página e referência do nosso próprio HTML. As
imagens relativas são lidas do disco e entram em `Images/`, as folhas em `Styles/`, um
`data:` vira recurso; o que não existe no disco é aviso. O livro nasce na disposição do
livro novo e é dividido por `<h1>` (`livro_ops.dividir_por_titulo`) — um HTML de um
livro inteiro tem vários.
"""

from __future__ import annotations

import base64
import html
import os
import posixpath
import re
from typing import Any, Sequence
from urllib.parse import quote, unquote
from xml.sax.saxutils import escape

from core.editor import consertar, epub, fontes, livro_ops, modelo, sumario, xhtml
from core.editor.conversao import Cronometro, OpcoesDeConversao, RelatorioDeConversao
from core.editor.modelo import (Capitulo, Diagrama, EntradaDeSumario, Figura, IlhaBruta, Livro, Metadados,
                                Paragrafo, Pessoa, Recurso, Titulo)
from core.editor.xhtml import PI, Comentario, ErroDeXhtml, No, Texto

#: `epub:type` → `role` DPUB-ARIA 1.1. Vazio: não há papel correspondente (sai só o `epub:type`… que sai nada).
ROLE_DO_TIPO = {
    "cover": "doc-cover", "dedication": "doc-dedication", "epigraph": "doc-epigraph", "foreword": "doc-foreword",
    "preface": "doc-preface", "introduction": "doc-introduction", "toc": "doc-toc", "chapter": "doc-chapter",
    "part": "doc-part", "glossary": "doc-glossary", "bibliography": "doc-bibliography", "index": "doc-index",
    "appendix": "doc-appendix", "acknowledgments": "doc-acknowledgments", "colophon": "doc-colophon",
    "endnotes": "doc-endnotes", "endnote": "doc-endnote", "footnote": "doc-footnote", "noteref": "doc-noteref",
    "pagebreak": "doc-pagebreak", "page-list": "doc-pagelist", "abstract": "doc-abstract",
    "afterword": "doc-afterword", "conclusion": "doc-conclusion", "epilogue": "doc-epilogue",
    "prologue": "doc-prologue", "errata": "doc-errata", "credits": "doc-credits", "notice": "doc-notice",
    "pullquote": "doc-pullquote", "qna": "doc-qna", "subtitle": "doc-subtitle", "tip": "doc-tip",
    "backlink": "doc-backlink", "biblioentry": "doc-biblioentry", "biblioref": "doc-biblioref",
    "glossref": "doc-glossref", "example": "doc-example",
}
TIPO_DO_ROLE = {v: k for k, v in ROLE_DO_TIPO.items()}
#: Elementos vazios do HTML5: saem sem fechamento; qualquer outro vazio sai `<x></x>`.
VAZIOS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
                    "track", "wbr"})
#: Atributos que carregam caminho, e em que elemento.
ATRIBUTOS_DE_CAMINHO = ("src", "href", "xlink:href", "poster", "data")
NS_SVG = "http://www.w3.org/2000/svg"
NS_MATHML = "http://www.w3.org/1998/Math/MathML"
NS_XLINK = "http://www.w3.org/1999/xlink"
SINONIMOS = (("b", "strong", "negrito"), ("i", "em", "itálico"), ("strike", "s", "tachado"), ("del", "s", "tachado"),
             ("ins", "u", "sublinhado"))
_RE_URL_CSS = re.compile(r"""url\(\s*(['"]?)([^)'"]+)\1\s*\)""")
_RE_TAG_DE_ABERTURA = re.compile(
    r"<([A-Za-z][A-Za-z0-9:-]*)((?:\s+[^\s=>/]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?)*)\s*/?>")
_RE_ROLE = re.compile(r"""\brole\s*=\s*["']([^"']*)["']""")
_RE_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_RE_LANG = re.compile(r"""<html\b[^>]*\blang\s*=\s*["']([^"']+)["']""", re.I)
_RE_AUTOR = re.compile(r"""<meta\b[^>]*name\s*=\s*["']author["'][^>]*content\s*=\s*["']([^"']*)["']""", re.I)
_RE_CHARSET = re.compile(rb"""<meta\b[^>]*charset\s*=\s*["']?\s*([A-Za-z0-9._-]+)""", re.I)
_RE_XML_ENCODING = re.compile(rb"""^\s*<\?xml[^>]*encoding\s*=\s*["']([A-Za-z0-9._-]+)["']""")
_RE_IMG = re.compile(r"^<img\b[^>]*>$", re.S)
_RE_ATRIBUTO = re.compile(r"""([A-Za-z_:][-\w:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""")


def _attr(valor: str) -> str:
    return html.escape(valor, quote=True)


def _e_externo(alvo: str) -> bool:
    return "://" in alvo or alvo.startswith(("mailto:", "tel:", "data:", "javascript:"))


def _nome_de_tag(nome: str) -> tuple[str, str]:
    """`(nome local, xmlns a declarar)` de um nome da árvore (`{uri}svg` → `svg` + o xmlns)."""
    if nome.startswith("{"):
        uri, local = nome[1:].split("}", 1)
        return local, uri
    return nome, ""


def _id_de_secao(arquivo: str) -> str:
    return arquivo


# ----------------------------------------------------------------------
# A árvore → HTML5
# ----------------------------------------------------------------------

class _Serializador:
    """Escreve a árvore de um capítulo como HTML5; `modo` é `"unico"` ou `"pasta"`."""

    def __init__(self, livro: Livro, cap: Capitulo, modo: str, relatorio: RelatorioDeConversao,
                 dados_de_recurso: Any):
        self.livro = livro
        self.cap = cap
        self.modo = modo
        self.relatorio = relatorio
        self.dados_de_recurso = dados_de_recurso
        self.pasta = posixpath.dirname(cap.arquivo)
        self.arquivos = {c.arquivo for c in livro.capitulos}
        self.avisou_pi = False

    # -- caminhos -------------------------------------------------------------

    def _absoluto(self, valor: str) -> str:
        caminho, _, ancora = valor.partition("#")
        caminho = unquote(caminho)
        if caminho and self.pasta:
            caminho = posixpath.normpath(posixpath.join(self.pasta, caminho))
        return caminho + ("#" + ancora if ancora else "")

    def _link(self, valor: str) -> str:
        """Um `href` de `<a>`: interno reescrito (único) ou com `.html` (pasta); externo como está."""
        if not valor or _e_externo(valor):
            return valor
        if valor.startswith("#"):
            return f"#{self.cap.arquivo}__{valor[1:]}" if self.modo == "unico" else valor
        absoluto = self._absoluto(valor)
        arquivo, _, ancora = absoluto.partition("#")
        if arquivo in self.arquivos:
            if self.modo == "unico":
                return f"#{arquivo}__{ancora}" if ancora else f"#{arquivo}"
            caminho, _, _anc = valor.partition("#")
            return _com_html(caminho) + ("#" + ancora if ancora else "")
        if arquivo in self.livro.recursos and self.modo == "unico":
            return self._data(arquivo) or valor
        return valor

    def _data(self, href: str) -> str:
        recurso = self.livro.recurso(href)
        if recurso is None:
            self.relatorio.aviso(f"{self.cap.arquivo}: recurso que não está no livro: {href}")
            return ""
        dados = self.dados_de_recurso(recurso)
        if dados is None:
            self.relatorio.aviso(f"{self.cap.arquivo}: recurso sem dados: {href}")
            return ""
        return f"data:{recurso.tipo_mime or epub.tipo_mime_de(href)};base64,{base64.b64encode(dados).decode('ascii')}"

    def _caminho(self, valor: str) -> str:
        """`src`, `poster`, `xlink:href`…: `data:` no arquivo único; como está na pasta."""
        if not valor or _e_externo(valor) or valor.startswith("#"):
            return valor
        if self.modo != "unico":
            return valor
        return self._data(self._absoluto(valor).partition("#")[0]) or valor

    # -- nós ------------------------------------------------------------------

    def filhos(self, no: No) -> str:
        return "".join(self.no(f) for f in no.filhos)

    def no(self, no: Any) -> str:
        if isinstance(no, Texto):
            return escape(no.texto)
        if isinstance(no, Comentario):
            return f"<!--{no.texto}-->"
        if isinstance(no, PI):
            if not self.avisou_pi:
                self.relatorio.aviso(f"{self.cap.arquivo}: instrução de processamento não sai em HTML5")
                self.avisou_pi = True
            return ""
        nome, xmlns = _nome_de_tag(no.nome)
        attrs = self._atributos(no, nome, xmlns)
        abre = f"<{nome}" + "".join(f' {k}="{_attr(v)}"' for k, v in attrs.items()) + ">"
        if nome in VAZIOS and not no.filhos:
            return abre
        return abre + self.filhos(no) + f"</{nome}>"

    def _atributos(self, no: No, nome: str, xmlns: str) -> dict[str, str]:
        saida: dict[str, str] = {}
        if xmlns and not self._pai_no_mesmo_namespace(no, xmlns):
            saida["xmlns"] = xmlns
        tipo = no.attrs.get("epub:type", "")
        for chave, valor in no.attrs.items():
            if chave == "epub:type":
                # o `role` derivado fica onde o `epub:type` estava (a ordem dos atributos é a do dialeto)
                if "role" not in no.attrs:
                    papeis = [ROLE_DO_TIPO[t] for t in valor.split() if t in ROLE_DO_TIPO]
                    if papeis:
                        saida["role"] = " ".join(papeis)
                continue
            if chave.startswith("xmlns:"):
                continue
            if chave == "xmlns" and valor == xhtml.NS_XHTML:
                continue
            if chave == "id" and self.modo == "unico":
                valor = f"{self.cap.arquivo}__{valor}"
            elif chave == "href" and nome == "a":
                valor = self._link(valor)
            elif chave == "href" and nome == "link" and self.modo == "pasta":
                pass
            elif chave in ATRIBUTOS_DE_CAMINHO:
                valor = self._caminho(valor)
            elif chave == "xml:lang":
                if "lang" in no.attrs:
                    continue
                chave = "lang"
            saida[chave] = valor
        del tipo
        return saida

    def _pai_no_mesmo_namespace(self, no: No, xmlns: str) -> bool:
        return getattr(no, "_pai_xmlns", "") == xmlns

    def secao(self, corpo: No) -> tuple[str, str]:
        """`(role da seção, miolo)` do `<body>` de um capítulo."""
        for filho in corpo.elementos():
            _marcar_pais(filho, "")
        semantica = corpo.attrs.get("epub:type", "")
        papel = next((ROLE_DO_TIPO[t] for t in semantica.split() if t in ROLE_DO_TIPO and t != "chapter"),
                     "doc-chapter")
        return papel, self.filhos(corpo)


def _marcar_pais(no: No, xmlns_do_pai: str) -> None:
    """Anota em cada nó o xmlns do pai, para o `xmlns` só sair na raiz de uma subárvore estrangeira."""
    no._pai_xmlns = xmlns_do_pai      # type: ignore[attr-defined]
    _nome, xmlns = _nome_de_tag(no.nome)
    for filho in no.elementos():
        _marcar_pais(filho, xmlns)


def _com_html(caminho: str) -> str:
    raiz, ext = posixpath.splitext(caminho)
    return raiz + ".html" if ext.lower() in (".xhtml", ".htm", ".xml") else caminho


# ----------------------------------------------------------------------
# O que os dois modos compartilham
# ----------------------------------------------------------------------

class _Escritor:
    def __init__(self, livro: Livro, relatorio: RelatorioDeConversao, opcoes: OpcoesDeConversao):
        self.livro = livro
        self.relatorio = relatorio
        self.opcoes = opcoes
        self.pasta_de_imagens = epub.pasta_de_imagens(livro)

    def dados(self, recurso: Recurso) -> bytes | None:
        try:
            return epub.dados_de(self.livro, recurso)
        except FileNotFoundError as erro:
            self.relatorio.aviso(str(erro))
            return None

    def preparar(self) -> list[tuple[Capitulo, No, No]]:
        """Fontes embutidas, PNG dos diagramas desenhados, e a árvore de cada capítulo."""
        livro = self.livro

        def ler(recurso: Recurso) -> str:
            return epub.dados_de(livro, recurso).decode("utf-8", errors="replace").lstrip("﻿")

        try:
            _novas, avisos = fontes.embutir(livro, ler_recurso=ler)
        except Exception as erro:      # noqa: BLE001 — fonte ilegível não derruba a exportação
            avisos = [f"fontes não embutidas ({erro})"]
        for aviso in avisos:
            self.relatorio.aviso(aviso)
        saida: list[tuple[Capitulo, No, No]] = []
        for cap in livro.capitulos:
            if cap.texto_cru is not None:
                texto = cap.texto_cru.lstrip("﻿")
            else:
                texto = xhtml.escrever(cap, pasta_de_imagens=self.pasta_de_imagens)
                self._desenhar_diagramas(cap)
            try:
                doc = xhtml.analisar(texto)
            except ErroDeXhtml as erro:
                self.relatorio.aviso(f"{cap.arquivo}: XHTML mal-formado, capítulo não exportado ({erro})")
                continue
            corpo = next((e for e in doc.raiz.elementos() if e.nome == "body"), None)
            cabeca = next((e for e in doc.raiz.elementos() if e.nome == "head"), None)
            if corpo is None:
                self.relatorio.aviso(f"{cap.arquivo}: sem <body>, capítulo não exportado")
                continue
            saida.append((cap, cabeca if cabeca is not None else No("head", {}), corpo))
        return saida

    def _desenhar_diagramas(self, cap: Capitulo) -> None:
        for bloco in modelo.blocos_do_capitulo(cap):
            if not isinstance(bloco, Diagrama) or bloco.modo != "png":
                continue
            href = xhtml.imagem_do_diagrama(bloco, self.pasta_de_imagens)
            if href in self.livro.recursos:
                continue
            try:
                png, _largura, _altura = epub.png_do_diagrama(bloco)
            except Exception as erro:      # noqa: BLE001 — fonte ausente não derruba a exportação
                self.relatorio.aviso(f"{cap.arquivo}: diagrama {bloco.id} não desenhado ({erro})")
                continue
            self.livro.recursos[href] = Recurso(caminho=href, tipo_mime=epub.MIME_PNG, dados=png)

    def folhas_em_ordem(self, capitulos: Sequence[Capitulo]) -> list[str]:
        vistas: list[str] = []
        for href in list(self.livro.folhas) + [f for c in capitulos for f in c.folhas]:
            if href not in vistas and self.livro.recurso(href) is not None:
                vistas.append(href)
        return vistas

    def css_inline(self, hrefs: Sequence[str]) -> str:
        """As folhas concatenadas, com os `url()` (relativos à folha) em `data:`."""
        partes: list[str] = []
        for href in hrefs:
            recurso = self.livro.recurso(href)
            if recurso is None:
                continue
            dados = self.dados(recurso)
            if dados is None:
                continue
            texto = dados.decode("utf-8", errors="replace").lstrip("﻿")
            pasta = posixpath.dirname(href)

            def trocar(m: re.Match) -> str:
                alvo = m.group(2).strip()
                if _e_externo(alvo) or alvo.startswith("#"):
                    return m.group(0)
                absoluto = posixpath.normpath(posixpath.join(pasta, unquote(alvo))) if pasta else unquote(alvo)
                alvo_recurso = self.livro.recurso(absoluto)
                if alvo_recurso is None:
                    self.relatorio.aviso(f"{href}: url() para recurso que não está no livro: {alvo}")
                    return m.group(0)
                bytes_ = self.dados(alvo_recurso)
                if bytes_ is None:
                    return m.group(0)
                mime = alvo_recurso.tipo_mime or epub.tipo_mime_de(absoluto)
                return f'url("data:{mime};base64,{base64.b64encode(bytes_).decode("ascii")}")'

            texto = _RE_URL_CSS.sub(trocar, texto)
            if "@import" in texto:
                self.relatorio.aviso(f"{href}: @import não é resolvido no HTML")
            partes.append(f"/* {href} */\n" + texto.replace("</", "<\\/"))
        return "\n".join(partes)

    def cabeca_html(self, titulo: str, extra: str = "") -> str:
        md = self.livro.metadados
        idioma = md.idioma or "und"
        linhas = ["<!DOCTYPE html>", f'<html lang="{_attr(idioma)}">', "<head>", '<meta charset="utf-8">',
                  f"<title>{escape(titulo)}</title>",
                  '<meta name="viewport" content="width=device-width, initial-scale=1">',
                  '<meta name="generator" content="PyBoxEditor">']
        if md.autores:
            linhas.append(f'<meta name="author" content="{_attr("; ".join(p.nome for p in md.autores))}">')
        if md.descricao:
            linhas.append(f'<meta name="description" content="{_attr(md.descricao)}">')
        if extra:
            linhas.append(extra)
        linhas.append("</head>")
        return "\n".join(linhas)

    def sumario_html(self, entradas: Sequence[EntradaDeSumario], destino: Any, nivel: int = 0) -> str:
        recuo = "  " * nivel
        itens = []
        for entrada in entradas:
            filhos = ("\n" + self.sumario_html(entrada.filhos, destino, nivel + 2) + "\n" + recuo + "  ") \
                if entrada.filhos else ""
            itens.append(f'{recuo}  <li><a href="{_attr(destino(entrada.destino))}">{escape(entrada.rotulo)}</a>'
                         f"{filhos}</li>")
        return f"{recuo}<ol>\n" + "\n".join(itens) + f"\n{recuo}</ol>"


# ----------------------------------------------------------------------
# Arquivo único
# ----------------------------------------------------------------------

def escrever_unico(livro: Livro, caminho: str, opcoes: OpcoesDeConversao | None = None) -> RelatorioDeConversao:
    """O livro num HTML5 só, sem referência externa (§10.2). Devolve o relatório."""
    caminho = os.fspath(caminho)
    opcoes = opcoes or OpcoesDeConversao()
    relatorio = RelatorioDeConversao(formato="html", arquivos=[caminho])
    with Cronometro(relatorio):
        escritor = _Escritor(livro, relatorio, opcoes)
        capitulos = escritor.preparar()
        md = livro.metadados
        css = escritor.css_inline(escritor.folhas_em_ordem([c for c, _h, _b in capitulos]))
        extra = f"<style>\n{css}\n</style>" if css else ""
        partes = [escritor.cabeca_html(md.titulo or "Livro", extra), "<body>",
                  "<header>", f"<h1 class=\"titulo-do-livro\">{escape(md.titulo or 'Livro')}</h1>"]
        if md.autores:
            partes.append(f"<p class=\"autor-do-livro\">{escape('; '.join(p.nome for p in md.autores))}</p>")
        partes.append("</header>")
        entradas = livro.sumario or sumario.gerar_dos_titulos(livro)
        if entradas:
            def destino(alvo: str) -> str:
                arquivo, _, ancora = alvo.partition("#")
                return f"#{arquivo}__{ancora}" if ancora else f"#{arquivo}"
            partes.append('<nav role="doc-toc" aria-label="Sumário">\n' + escritor.sumario_html(entradas, destino)
                          + "\n</nav>")
        for cap, _cabeca, corpo in capitulos:
            serializador = _Serializador(livro, cap, "unico", relatorio, escritor.dados)
            papel, miolo = serializador.secao(corpo)
            lang = f' lang="{_attr(cap.idioma)}"' if cap.idioma and cap.idioma != md.idioma else ""
            partes.append(f'<section role="{papel}" id="{_attr(_id_de_secao(cap.arquivo))}"{lang}>\n{miolo}\n'
                          "</section>")
        partes.append("</body>\n</html>\n")
        _gravar(caminho, "\n".join(partes))
    relatorio.contar(livro)
    relatorio.fontes_embutidas = epub.fontes_embutidas(livro)
    return relatorio


def _gravar(caminho: str, texto: str) -> None:
    pasta = os.path.dirname(os.path.abspath(caminho))
    os.makedirs(pasta, exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)


# ----------------------------------------------------------------------
# Pasta
# ----------------------------------------------------------------------

def escrever_pasta(livro: Livro, pasta: str, opcoes: OpcoesDeConversao | None = None) -> RelatorioDeConversao:
    """
    O livro numa pasta: `index.html` com sumário e marcos, um `.html` por capítulo no
    lugar de cada `.xhtml`, os recursos onde estavam. Devolve o relatório (com todos
    os arquivos escritos).
    """
    pasta = os.fspath(pasta)
    opcoes = opcoes or OpcoesDeConversao()
    relatorio = RelatorioDeConversao(formato="html-pasta", arquivos=[])
    with Cronometro(relatorio):
        escritor = _Escritor(livro, relatorio, opcoes)
        capitulos = escritor.preparar()
        os.makedirs(pasta, exist_ok=True)
        escritos: list[str] = []
        for cap, cabeca, corpo in capitulos:
            serializador = _Serializador(livro, cap, "pasta", relatorio, escritor.dados)
            papel, miolo = serializador.secao(corpo)
            folhas = [f'<link rel="stylesheet" href="{_attr(_relativo(f, cap.arquivo))}">' for f in cap.folhas
                      if livro.recurso(f) is not None]
            extra_da_cabeca = [c for c in cabeca.elementos() if c.nome not in ("title", "link", "meta")]
            extra = "\n".join(folhas + [serializador.no(e) for e in extra_da_cabeca])
            idioma = cap.idioma or livro.metadados.idioma or "und"
            texto = "\n".join([
                "<!DOCTYPE html>", f'<html lang="{_attr(idioma)}">', "<head>", '<meta charset="utf-8">',
                f"<title>{escape(cap.titulo_efetivo)}</title>", extra, "</head>",
                f'<body role="{papel}">', miolo, "</body>", "</html>", ""])
            destino = os.path.join(pasta, *_com_html(cap.arquivo).split("/"))
            _gravar(destino, texto)
            escritos.append(destino)
        for href, recurso in livro.recursos.items():
            if not recurso.no_manifesto and href.startswith("META-INF/"):
                continue
            dados = escritor.dados(recurso)
            if dados is None:
                continue
            destino = os.path.join(pasta, *href.split("/"))
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with open(destino, "wb") as f:
                f.write(dados)
            escritos.append(destino)
        indice = os.path.join(pasta, "index.html")
        _gravar(indice, _index(livro, escritor))
        relatorio.arquivos = [indice] + escritos
    relatorio.contar(livro)
    relatorio.fontes_embutidas = epub.fontes_embutidas(livro)
    return relatorio


def _relativo(href: str, de_arquivo: str) -> str:
    pasta = posixpath.dirname(de_arquivo)
    return quote(posixpath.relpath(href, pasta) if pasta else href, safe=xhtml.SEGUROS_NA_URL)


def _index(livro: Livro, escritor: _Escritor) -> str:
    md = livro.metadados

    def destino(alvo: str) -> str:
        arquivo, _, ancora = alvo.partition("#")
        return quote(_com_html(arquivo), safe=xhtml.SEGUROS_NA_URL) + ("#" + ancora if ancora else "")

    partes = [escritor.cabeca_html(md.titulo or "Livro"), "<body>", "<header>",
              f"<h1>{escape(md.titulo or 'Livro')}</h1>"]
    if md.autores:
        partes.append(f"<p>{escape('; '.join(p.nome for p in md.autores))}</p>")
    if md.capa and livro.recurso(md.capa) is not None:
        partes.append(f'<p><img src="{_attr(quote(md.capa, safe=xhtml.SEGUROS_NA_URL))}" alt="Capa"></p>')
    partes.append("</header>")
    entradas = livro.sumario or sumario.gerar_dos_titulos(livro)
    partes.append('<nav role="doc-toc" aria-label="Sumário">\n<h2>Sumário</h2>\n'
                  + escritor.sumario_html(entradas, destino) + "\n</nav>")
    if livro.marcos:
        itens = "\n".join(f'  <li><a href="{_attr(destino(alvo))}">{escape(sumario.ROTULOS_DOS_MARCOS.get(tipo, tipo))}'
                          "</a></li>" for tipo, alvo in livro.marcos)
        partes.append(f'<nav aria-label="Marcos">\n<h2>Marcos</h2>\n<ul>\n{itens}\n</ul>\n</nav>')
    partes.append("</body>\n</html>\n")
    return "\n".join(partes)


# ----------------------------------------------------------------------
# Ler
# ----------------------------------------------------------------------

def _decodificar(dados: bytes, relatorio: RelatorioDeConversao) -> str:
    if dados.startswith(b"\xef\xbb\xbf"):
        return dados[3:].decode("utf-8", errors="replace")
    declarada = _RE_XML_ENCODING.match(dados) or _RE_CHARSET.search(dados[:4096])
    if declarada:
        nome = declarada.group(1).decode("ascii", errors="replace")
        try:
            return dados.decode(nome)
        except (LookupError, UnicodeDecodeError):
            relatorio.aviso(f"codificação declarada ({nome}) não serviu; lido como UTF-8")
    try:
        return dados.decode("utf-8")
    except UnicodeDecodeError:
        relatorio.aviso("o arquivo não é UTF-8; lido como Windows-1252")
        return dados.decode("cp1252", errors="replace")


def _contar_sinonimos(texto: str, relatorio: RelatorioDeConversao) -> None:
    for tag, canonico, nome in SINONIMOS:
        n = len(re.findall(rf"<{tag}\b", texto, re.IGNORECASE))
        if n:
            relatorio.aviso(f"normalizado: <{tag}> → <{canonico}> ({nome}), {n} vez(es)")


def _epub_type_dos_roles(texto: str) -> str:
    """`role="doc-footnote"` sem `epub:type` ganha `epub:type="footnote"`: é o nosso próprio HTML voltando."""
    if "role=" not in texto:
        return texto

    def trocar(m: re.Match) -> str:
        tag = m.group(0)
        if "epub:type" in tag:
            return tag
        papel = _RE_ROLE.search(tag)
        if not papel:
            return tag
        tipos = [TIPO_DO_ROLE[r] for r in papel.group(1).split() if r in TIPO_DO_ROLE]
        if not tipos:
            return tag
        insercao = f' epub:type="{" ".join(tipos)}"'
        if tag.endswith("/>"):
            return tag[:-2].rstrip() + insercao + "/>"
        return tag[:-1] + insercao + ">"

    return _RE_TAG_DE_ABERTURA.sub(trocar, texto)


def _metadados_do_texto(texto: str, caminho: str) -> Metadados:
    titulo = ""
    m = _RE_TITLE.search(texto)
    if m:
        titulo = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", m.group(1)))).strip()
    idioma = ""
    m = _RE_LANG.search(texto)
    if m:
        idioma = m.group(1).strip()
    autor = ""
    m = _RE_AUTOR.search(texto)
    if m:
        autor = html.unescape(m.group(1)).strip()
    md = Metadados(titulo=titulo or os.path.splitext(os.path.basename(caminho))[0], idioma=idioma or "und")
    if autor:
        md.autores = [Pessoa(nome=autor)]
    return md


def ler(caminho: str, dividir_por_titulo: bool = True, nivel: int = 1) -> tuple[Livro, RelatorioDeConversao]:
    """
    Um HTML/XHTML solto → `Livro` (§10.6): consertado com aviso, sinônimos registrados,
    imagens e folhas relativas lidas do disco, dividido por `<h1>` quando pedido. O
    nosso próprio arquivo único volta pelas `<section role="doc-…" id="<arquivo>">`: uma
    por capítulo, com os ids e links desprefixados.
    """
    caminho = os.fspath(caminho)
    relatorio = RelatorioDeConversao(formato="html", arquivos=[caminho])
    with Cronometro(relatorio):
        try:
            with open(caminho, "rb") as f:
                dados = f.read()
        except OSError as erro:
            raise ValueError(f"não deu para ler {caminho}: {erro}") from None
        texto = _decodificar(dados, relatorio)
        _contar_sinonimos(texto, relatorio)
        texto = _epub_type_dos_roles(texto)
        consertado, avisos = consertar.consertar(texto)
        for aviso in avisos[:50]:
            relatorio.aviso(f"consertado: {aviso}")
        if len(avisos) > 50:
            relatorio.aviso(f"… e mais {len(avisos) - 50} consertos")
        nome = os.path.basename(caminho)
        try:
            doc = xhtml.analisar(consertado)
        except ErroDeXhtml as erro:
            raise ValueError(f"{nome} não deu para ler nem depois de consertado: {erro}") from None
        estilos_inline = _estilos_da_cabeca(doc)
        capitulos = _capitulos_das_secoes(doc, relatorio)
        de_secoes = capitulos is not None
        if capitulos is None:
            try:
                capitulos = [xhtml.ler(consertado, "Text/cap-0001.xhtml")]
            except ErroDeXhtml as erro:
                raise ValueError(f"{nome} não deu para ler nem depois de consertado: {erro}") from None
        figuras = 0
        for cap in capitulos:
            for aviso in cap.avisos:
                relatorio.aviso(f"{nome}: {aviso}")
            cap.avisos = []
            cap.titulo = ""            # o <title> do arquivo é o do livro (metadados); o capítulo é o seu <h1>
            figuras += _imagens_em_figuras(cap)
        if figuras:
            relatorio.aviso(f"normalizado: <img> sozinho no parágrafo → figura, {figuras} vez(es)")
        pasta_do_arquivo = os.path.dirname(os.path.abspath(caminho))
        livro = _livro_de(capitulos, _metadados_do_texto(texto, caminho), pasta_do_arquivo, estilos_inline,
                          relatorio)
        if dividir_por_titulo and not de_secoes:
            livro_ops.dividir_por_titulo(livro, "Text/cap-0001.xhtml", nivel)
            livro_ops.renomear_varios(livro, "cap-%04d")
        livro.sumario = sumario.gerar_dos_titulos(livro)
        primeiro = next((c.arquivo for c in livro.capitulos if not c.semantica or c.semantica == "bodymatter"),
                        livro.capitulos[0].arquivo)
        livro.marcos = [(c.semantica, c.arquivo) for c in livro.capitulos
                        if c.semantica in livro_ops.SEMANTICAS_QUE_SAO_MARCO] or [("bodymatter", primeiro)]
    relatorio.contar(livro)
    return livro, relatorio


def _estilos_da_cabeca(doc: xhtml.Documento) -> list[str]:
    """O texto de cada `<style>` do `<head>` (o arquivo único traz a CSS inline)."""
    cabeca = next((e for e in doc.raiz.elementos() if e.nome == "head"), None)
    if cabeca is None:
        return []
    return [e.texto().replace("<" + "\\" + "/", "</") for e in cabeca.elementos()
            if e.nome == "style" and e.texto().strip()]


_RE_HREF_INTERNO = re.compile(r'href="#([^"]*)"')
_RE_ID = re.compile(r'\bid="([^"]*)"')


def _capitulos_das_secoes(doc: xhtml.Documento, relatorio: RelatorioDeConversao) -> list[Capitulo] | None:
    """
    As `<section role="doc-…" id="<arquivo>">` de um arquivo único → capítulos; `None`
    quando o `<body>` não é feito delas (um HTML qualquer). O `<header>` e o `<nav>` do
    topo não entram (o sumário é regenerado dos títulos).
    """
    corpo = next((e for e in doc.raiz.elementos() if e.nome == "body"), None)
    if corpo is None:
        return None
    secoes = [e for e in corpo.elementos() if e.nome == "section" and e.attrs.get("id")
              and (e.attrs.get("role", "").startswith("doc-") or e.attrs.get("epub:type"))]
    if not secoes:
        return None
    for filho in corpo.filhos:
        if isinstance(filho, No) and filho not in secoes and filho.nome not in ("header", "nav", "footer"):
            return None
        if isinstance(filho, Texto) and filho.texto.strip():
            return None
    arquivos = [sec.attrs["id"] for sec in secoes]
    capitulos: list[Capitulo] = []
    for sec in secoes:
        arquivo = sec.attrs["id"]
        pasta = posixpath.dirname(arquivo)
        prefixo = arquivo + "__"
        miolo = "".join(escape(f.texto) if isinstance(f, Texto) else doc.cru(f) for f in sec.filhos)
        miolo = _RE_ID.sub(lambda m: f'id="{m.group(1)[len(prefixo):]}"' if m.group(1).startswith(prefixo)
                           else m.group(0), miolo)

        def link(m: re.Match) -> str:
            alvo = m.group(1)
            arq, sep, anc = alvo.partition("__")
            if not sep or arq not in arquivos:
                if alvo in arquivos:
                    relativo = posixpath.relpath(alvo, pasta) if pasta else alvo
                    return f'href="{quote(relativo, safe=xhtml.SEGUROS_NA_URL)}"'
                return m.group(0)
            if arq == arquivo:
                return f'href="#{anc}"'
            relativo = posixpath.relpath(arq, pasta) if pasta else arq
            return f'href="{quote(relativo, safe=xhtml.SEGUROS_NA_URL)}#{anc}"'

        miolo = _RE_HREF_INTERNO.sub(link, miolo)
        tipo = sec.attrs.get("epub:type") or TIPO_DO_ROLE.get(sec.attrs.get("role", "").split()[0]
                                                                if sec.attrs.get("role") else "", "")
        if tipo == "chapter":
            tipo = ""
        lang = sec.attrs.get("lang") or sec.attrs.get("xml:lang") or doc.raiz.attrs.get("lang", "")
        raiz = (f'<html xmlns="{xhtml.NS_XHTML}" xmlns:epub="{xhtml.NS_EPUB}"'
                + (f' lang="{_attr(lang)}" xml:lang="{_attr(lang)}"' if lang else "") + ">")
        corpo_xhtml = "<body" + (f' epub:type="{_attr(tipo)}"' if tipo else "") + ">"
        texto = f"{raiz}\n<head>\n<title></title>\n</head>\n{corpo_xhtml}\n{miolo}\n</body>\n</html>\n"
        try:
            capitulos.append(xhtml.ler(texto, arquivo))
        except ErroDeXhtml as erro:
            relatorio.aviso(f"seção {arquivo}: não deu para ler ({erro}); ficou em modo código")
            capitulos.append(Capitulo(arquivo=arquivo, texto_cru=texto))
    return capitulos


def ler_texto(texto: str, arquivo: str = "Text/cap-0001.xhtml") -> tuple[Capitulo, list[str]]:
    """Um fragmento ou documento XHTML/HTML em texto → capítulo consertado, e os avisos (para colar e testes)."""
    consertado, avisos = consertar.consertar(_epub_type_dos_roles(texto))
    cap = xhtml.ler(consertado, arquivo)
    _imagens_em_figuras(cap)
    return cap, avisos + cap.avisos


def _imagens_em_figuras(cap: Capitulo) -> int:
    """
    Um `<p>` que só tem um `<img>` (o jeito do HTML solto de pôr figura), ou um `<img>`
    solto no `<body>`, vira `Figura` — no dialeto ele seria ilha (DEC-02), e uma figura
    importada tem de ser figura. Devolve quantos virou.
    """
    pasta = posixpath.dirname(cap.arquivo)
    novos: list = []
    n = 0
    for bloco in cap.blocos:
        cru = ""
        if isinstance(bloco, Paragrafo) and not isinstance(bloco, Titulo):
            reais = [t for t in bloco.trechos if t.texto.strip() or t.ilha or t.nota or t.pagina is not None]
            if len(reais) == 1 and reais[0].ilha and _RE_IMG.match(reais[0].ilha.strip()):
                cru = reais[0].ilha.strip()
        elif isinstance(bloco, IlhaBruta) and bloco.elemento == "img":
            cru = bloco.xhtml.strip()
        if not cru:
            novos.append(bloco)
            continue
        attrs = {m.group(1): html.unescape(m.group(2) if m.group(2) is not None else m.group(3))
                 for m in _RE_ATRIBUTO.finditer(cru)}
        src = attrs.get("src", "")
        if not src:
            novos.append(bloco)
            continue
        if not _e_externo(src) and not src.startswith("#"):
            src = posixpath.normpath(posixpath.join(pasta, unquote(src))) if pasta else unquote(src)
        largura = None
        m_largura = re.search(r"width\s*:\s*([\d.]+)\s*(pt|px)", attrs.get("style", ""))
        if m_largura:
            largura = float(m_largura.group(1)) * (0.75 if m_largura.group(2) == "px" else 1.0)
        elif attrs.get("width", "").isdigit():
            largura = int(attrs["width"]) * 0.75
        novos.append(Figura(recurso=src, alt=attrs.get("alt", ""), largura_pt=largura, id=bloco.id,
                            id_persistente=bloco.id_persistente, classe=bloco.classe, linha_fonte=bloco.linha_fonte))
        n += 1
    cap.blocos = novos
    return n


def _livro_de(capitulos: list[Capitulo], metadados: Metadados, pasta_do_arquivo: str,
              estilos_inline: Sequence[str], relatorio: RelatorioDeConversao) -> Livro:
    livro = epub.novo_livro(metadados.titulo, metadados.autores[0].nome if metadados.autores else "",
                            metadados.idioma, ncx=True)
    if not metadados.identificador:
        metadados.identificador = livro.metadados.identificador
    livro.metadados = metadados
    padrao = livro.folhas[0]
    livro.capitulos = list(capitulos)
    # As folhas: as do HTML lidas do disco para `Styles/`, os `<style>` inline como folhas
    # próprias; a folha padrão do livro novo entra antes de todas.
    folhas_lidas: list[str] = []
    for k, css in enumerate(estilos_inline, start=1):
        href = livro_ops.nome_livre(livro, f"Styles/inline-{k}.css")
        livro.recursos[href] = Recurso(caminho=href, tipo_mime=epub.MIME_CSS, dados=css.strip().encode("utf-8") + b"\n")
        folhas_lidas.append(href)
    for cap in livro.capitulos:
        proprias: list[str] = []
        for href in cap.folhas:
            novo = _trazer_do_disco(livro, href, pasta_do_arquivo, "Styles", epub.MIME_CSS, relatorio, cap.arquivo)
            if novo:
                proprias.append(novo)
                if novo not in folhas_lidas:
                    folhas_lidas.append(novo)
        cap.folhas = [padrao] + [f for f in folhas_lidas if f.startswith("Styles/inline-")] + proprias
    livro.folhas = [padrao] + folhas_lidas
    # As imagens: relativas lidas do disco; `data:` decodificado.
    for cap in livro.capitulos:
        for bloco in modelo.blocos_do_capitulo(cap):
            if isinstance(bloco, Figura):
                bloco.recurso = _recurso_de_imagem(livro, bloco.recurso, pasta_do_arquivo, relatorio,
                                                   cap.arquivo) or bloco.recurso
            elif isinstance(bloco, Diagrama):
                if bloco.recorte:
                    bloco.recorte = _recurso_de_imagem(livro, bloco.recorte, pasta_do_arquivo, relatorio,
                                                       cap.arquivo) or bloco.recorte
                if bloco.imagem:
                    bloco.imagem = _recurso_de_imagem(livro, bloco.imagem, pasta_do_arquivo, relatorio,
                                                      cap.arquivo) or ""
    return livro


_contador_de_embutidas = [0]


def _recurso_de_imagem(livro: Livro, href: str, pasta: str, relatorio: RelatorioDeConversao,
                       capitulo: str = "Text/cap-0001.xhtml") -> str | None:
    if href.startswith("data:"):
        cabeca, _, corpo = href.partition(",")
        mime = cabeca[5:].split(";")[0] or "application/octet-stream"
        try:
            dados = base64.b64decode(corpo) if ";base64" in cabeca else unquote(corpo).encode("latin-1")
        except (ValueError, UnicodeEncodeError):
            relatorio.aviso("imagem data: ilegível, deixada como está")
            return None
        ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/svg+xml": ".svg",
               "image/webp": ".webp"}.get(mime, ".bin")
        _contador_de_embutidas[0] += 1
        nome = livro_ops.nome_livre(livro, f"Images/embutida-{_contador_de_embutidas[0]:03d}{ext}")
        livro.recursos[nome] = Recurso(caminho=nome, tipo_mime=mime, dados=dados)
        return nome
    if _e_externo(href):
        relatorio.aviso(f"imagem externa, deixada como link: {href}")
        return None
    return _trazer_do_disco(livro, href, pasta, "Images", "", relatorio, capitulo)


def _trazer_do_disco(livro: Livro, href: str, pasta: str, destino: str, mime: str,
                     relatorio: RelatorioDeConversao, capitulo: str = "Text/cap-0001.xhtml") -> str | None:
    """Um href relativo ao OPF (calculado do capítulo) → o arquivo no disco → recurso em `destino/`; `None` sem ele."""
    if href in livro.recursos:
        return href
    pasta_do_capitulo = posixpath.dirname(capitulo)
    relativo = posixpath.relpath(href, pasta_do_capitulo) if pasta_do_capitulo else href
    caminho = os.path.normpath(os.path.join(pasta, *relativo.split("/")))
    if not os.path.isfile(caminho):
        relatorio.aviso(f"arquivo referenciado não encontrado: {relativo}")
        return None
    with open(caminho, "rb") as f:
        dados = f.read()
    nome = livro_ops.nome_livre(livro, posixpath.join(destino, posixpath.basename(href)))
    livro.recursos[nome] = Recurso(caminho=nome, tipo_mime=mime or epub.tipo_mime_de(nome), dados=dados)
    if nome != href:
        _trocar_href(livro, href, nome)
    return nome


def _trocar_href(livro: Livro, de: str, para: str) -> None:
    """O href antigo (que nunca existiu como recurso) vira o novo em blocos, folhas e ilhas."""
    for cap in livro.capitulos:
        cap.folhas = [para if f == de else f for f in cap.folhas]
        for bloco in modelo.blocos_do_capitulo(cap):
            if isinstance(bloco, Figura) and bloco.recurso == de:
                bloco.recurso = para
            elif isinstance(bloco, Diagrama):
                if bloco.recorte == de:
                    bloco.recorte = para
                if bloco.imagem == de:
                    bloco.imagem = para
        for trecho in modelo.trechos_do_capitulo(cap):
            if trecho.link == de:
                trecho.link = para
    livro.folhas = [para if f == de else f for f in livro.folhas]


__all__ = ["escrever_unico", "escrever_pasta", "ler", "ler_texto", "ROLE_DO_TIPO", "TIPO_DO_ROLE"]
