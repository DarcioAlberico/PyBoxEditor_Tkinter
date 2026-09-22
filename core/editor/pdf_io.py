"""
O PDF paginado do livro (ED-12; SPEC_EDITOR §10.5, §10.8, §5 `FormatoDePagina`).

## Um `fitz.Story` para o livro inteiro

Os capítulos saem do `xhtml.escrever` — o mesmo XHTML do EPUB — e entram, um atrás do
outro, num `fitz.Story` só, com a CSS do livro como `user_css` e os recursos (imagens,
fontes, os PNG dos diagramas desenhados na hora) num `fitz.Archive` em memória. Cada
capítulo é um `div` com `page-break-before` (menos o primeiro) e um id próprio; os ids
dos blocos ganham o prefixo do capítulo (`cap1__dia1`) e os `href` internos são
reescritos para eles — é o que faz o link entre capítulos cair na página certa.

## A página é de `Livro.pagina`

`FormatoDePagina` dá o papel em mm e as margens (superior, externa, inferior, interna);
com `espelhadas`, a página ímpar (recto) tem a margem interna à esquerda e a par
(verso) à direita — dois `rect`s alternados. O cabeçalho par/ímpar é o título do livro
ou o do capítulo corrente (`cabecalho_par`/`cabecalho_impar`: `"titulo"`, `"capitulo"`
ou `""`), o rodapé é o número da página; ambos entram depois, com `Page.insert_text`,
porque o `Story` não sabe em que página está. O sumário do PDF vem dos títulos que
`Story.element_positions` devolve (`set_toc`), os links de `insert_link` (internos por
posição do id; externos por URI), os metadados de `set_metadata`.

## O que o PDF não faz

Notas saem no fim do capítulo (é onde o XHTML as põe); a hifenização é a do MuPDF; o
cabeçalho usa a Helvetica de base (Latin-1 — o que não cabe sai como `?`).
"""

from __future__ import annotations

import copy
import io
import os
import posixpath
import re
from typing import Any

from core.editor import dialeto, epub, fontes, modelo, xhtml
from core.editor.conversao import Cronometro, OpcoesDeConversao, RelatorioDeConversao
from core.editor.modelo import Capitulo, Diagrama, Livro, Titulo

PT_POR_MM = 72.0 / 25.4
#: Tamanho do cabeçalho e do rodapé, em pt.
CORPO_DO_CABECALHO = 9.0
_RE_BODY = re.compile(r"<body[^>]*>(.*)</body>", re.S)
_RE_ATRIBUTO = re.compile(r'\b(src|href|id)="([^"]*)"')
_RE_URL = re.compile(r"url\((['\"]?)([^)'\"]+)\1\)")


def mm(valor: float) -> float:
    return float(valor) * PT_POR_MM


def chave_do_capitulo(arquivo: str) -> str:
    """O prefixo dos ids de um capítulo no PDF: o arquivo sem o que não cabe num id."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", arquivo)


# ----------------------------------------------------------------------
# O HTML do livro
# ----------------------------------------------------------------------

class _Montador:
    def __init__(self, livro: Livro, opcoes: OpcoesDeConversao, relatorio: RelatorioDeConversao):
        self.livro = livro
        self.opcoes = opcoes
        self.relatorio = relatorio
        self.pasta = epub.pasta_de_imagens(livro)
        self.arquivos = {c.arquivo for c in livro.capitulos}
        self.dados: dict[str, bytes] = {}          # caminho no arquivo (relativo ao OPF) → bytes
        self.fontes_embutidas: list[str] = []

    # -- recursos -------------------------------------------------------------

    def _recursos(self) -> None:
        for caminho, recurso in self.livro.recursos.items():
            if recurso.tipo_mime in ("text/css", "application/xhtml+xml", "text/html"):
                continue
            try:
                self.dados[caminho] = recurso.dados if recurso.dados is not None else epub.dados_de(self.livro, recurso)
            except (FileNotFoundError, OSError) as erro:
                self.relatorio.aviso(f"recurso sem dados, fora do PDF: {caminho} ({erro})")

    def _fontes(self) -> str:
        """As fontes de diagrama e de símbolos que o livro precisa, no arquivo e em `@font-face`."""
        diagramas, simbolos, avisos = fontes.necessarias(self.livro)
        for aviso in avisos:
            self.relatorio.aviso(aviso)
        regras: list[str] = []
        for nome, arquivo in diagramas.items():
            caminho = self._fonte_no_arquivo(arquivo)
            if caminho:
                classe = fontes.classe_da_fonte(nome)
                regras.append(f'@font-face {{ font-family: "{nome}"; src: url({caminho}); }}\n'
                              f'div.diagrama.{classe} p {{ font-family: "{nome}", monospace; }}\n')
                if nome not in self.fontes_embutidas:
                    self.fontes_embutidas.append(nome)
        if simbolos is not None:
            familia, arquivo, _ = simbolos
            caminho = self._fonte_no_arquivo(arquivo)
            if caminho:
                regras.append(f'@font-face {{ font-family: "{familia}"; src: url({caminho}); }}\n'
                              f'span.sim {{ font-family: "{familia}", serif; }}\n')
                if familia not in self.fontes_embutidas:
                    self.fontes_embutidas.append(familia)
        return "".join(regras)

    def _fonte_no_arquivo(self, arquivo: str) -> str:
        base = os.path.basename(arquivo)
        for caminho in self.dados:
            if posixpath.basename(caminho).lower() == base.lower():
                return caminho
        try:
            with open(arquivo, "rb") as f:
                self.dados[f"Fonts/{base}"] = f.read()
        except OSError as erro:
            self.relatorio.aviso(f"fonte ilegível, fora do PDF: {arquivo} ({erro})")
            return ""
        return f"Fonts/{base}"

    def _diagramas(self, capitulos: list[Capitulo]) -> None:
        """Os PNG dos diagramas em imagem que o livro ainda não tem, desenhados agora."""
        for cap in capitulos:
            for bloco in modelo.blocos_do_capitulo(cap):
                if not isinstance(bloco, Diagrama) or bloco.modo != "png":
                    continue
                caminho = xhtml.imagem_do_diagrama(bloco, self.pasta)
                if caminho in self.dados:
                    continue
                try:
                    png, _largura, _altura = epub.png_do_diagrama(bloco)
                except Exception as erro:      # noqa: BLE001 — um diagrama que não desenha não derruba o PDF
                    self.relatorio.aviso(f"diagrama {bloco.id} não desenhado: {erro}")
                    continue
                self.dados[caminho] = png

    # -- CSS ------------------------------------------------------------------------

    def _css(self) -> str:
        partes: list[str] = []
        for folha in self.livro.folhas:
            recurso = self.livro.recurso(folha)
            if recurso is None:
                continue
            texto = recurso.texto_cru
            if texto is None:
                try:
                    dados = recurso.dados if recurso.dados is not None else epub.dados_de(self.livro, recurso)
                    texto = dados.decode("utf-8", errors="replace")
                except (FileNotFoundError, OSError):
                    continue
            pasta = posixpath.dirname(folha)
            partes.append(_RE_URL.sub(lambda m: f"url({_resolver(pasta, m.group(2))})", texto))
        if not partes:
            partes.append(dialeto.css_padrao(corpo_pt=self.opcoes.corpo_pt))
        partes.append(self._fontes())
        partes.append(
            "body { line-height: 1.35; }\n"
            "figure { margin: 0.6em auto; text-align: center; }\n"
            "figure img { max-width: 100%; }\n"
            "figcaption { font-size: 0.85em; text-align: center; }\n"
            "table { border-collapse: collapse; }\n"
            "td, th { border: 0.5pt solid #444; padding: 2pt 4pt; }\n"
            + ("body { hyphens: auto; }\n" if self.livro.pagina.hifenizar else ""))
        return "\n".join(partes)

    # -- HTML -----------------------------------------------------------------------

    def _capitulo_para_pdf(self, cap: Capitulo) -> Capitulo:
        """Uma cópia rasa com os diagramas no modo pedido (o PNG sai do arquivo, a fonte da CSS)."""
        if self.opcoes.modo_de_diagrama != "png":
            return cap
        copia = copy.copy(cap)
        copia.blocos = []
        for bloco in cap.blocos:
            if isinstance(bloco, Diagrama) and bloco.modo != "png":
                novo = copy.copy(bloco)
                novo.modo = "png"
                bloco = novo
            copia.blocos.append(bloco)
        return copia

    def _html_do_capitulo(self, cap: Capitulo, primeiro: bool) -> str:
        chave = chave_do_capitulo(cap.arquivo)
        pasta = posixpath.dirname(cap.arquivo)
        texto = xhtml.escrever(cap, pasta_de_imagens=self.pasta)
        achado = _RE_BODY.search(texto)
        corpo = achado.group(1) if achado else texto

        def atributo(m: re.Match) -> str:
            nome, valor = m.group(1), m.group(2)
            if nome == "id":
                return f'id="{chave}__{valor}"'
            if nome == "src":
                return f'src="{_resolver(pasta, valor)}"'
            if not valor or "://" in valor or valor.startswith(("mailto:", "data:")):
                return m.group(0)
            if valor.startswith("#"):
                return f'href="#{chave}__{valor[1:]}"'
            arquivo, _, ancora = valor.partition("#")
            destino = _resolver(pasta, arquivo)
            if destino in self.arquivos:
                return f'href="#{chave_do_capitulo(destino)}__{ancora}"'
            return m.group(0)

        corpo = _RE_ATRIBUTO.sub(atributo, corpo)
        corpo = corpo.replace("epub:type=", "data-epub-type=")
        quebra = "" if primeiro else ' style="page-break-before: always"'
        return f'<div class="capitulo" id="{chave}__"{quebra}>{corpo}</div>'

    def montar(self) -> tuple[str, str]:
        """`(html, css)` do livro inteiro, com os recursos em `dados`."""
        self._recursos()
        capitulos = [self._capitulo_para_pdf(c) for c in self.livro.capitulos]
        self._diagramas(capitulos)
        css = self._css()
        partes = [self._html_do_capitulo(cap, k == 0) for k, cap in enumerate(capitulos)]
        idioma = self.livro.metadados.idioma or "und"
        html = f'<html lang="{idioma}"><body>{"".join(partes)}</body></html>'
        return html, css


def _resolver(pasta: str, valor: str) -> str:
    """Um caminho relativo ao capítulo/folha → relativo ao OPF (o nome no arquivo)."""
    if not valor or "://" in valor or valor.startswith(("#", "data:", "mailto:")):
        return valor
    return posixpath.normpath(posixpath.join(pasta, valor)) if pasta else posixpath.normpath(valor)


# ----------------------------------------------------------------------
# A paginação
# ----------------------------------------------------------------------

def _rects(pagina: modelo.FormatoDePagina, n: int) -> tuple[Any, Any]:
    """`(mediabox, rect do texto)` da página `n` (0-based): a ímpar tem a margem interna à esquerda."""
    import fitz

    largura, altura = mm(pagina.largura_mm), mm(pagina.altura_mm)
    superior, externa, inferior, interna = (mm(v) for v in pagina.margens_mm)
    recto = n % 2 == 0
    if pagina.espelhadas:
        esquerda, direita = (interna, externa) if recto else (externa, interna)
    else:
        esquerda, direita = interna, externa
    mediabox = fitz.Rect(0, 0, largura, altura)
    return mediabox, fitz.Rect(esquerda, superior, largura - direita, altura - inferior)


def _latin1(texto: str) -> str:
    return texto.encode("latin-1", errors="replace").decode("latin-1")


def _cabecalho(livro: Livro, tipo: str, capitulo_atual: str) -> str:
    if tipo == "titulo":
        return livro.metadados.titulo
    if tipo == "capitulo":
        return capitulo_atual or livro.metadados.titulo
    return ""


def _fundir_rects(posicoes: list[Any]) -> list[Any]:
    """Os pedaços de um link na mesma linha (o Story dá um por palavra) num retângulo só."""
    import fitz

    saida: list[Any] = []
    for pos in posicoes:
        r = fitz.Rect(pos.rect)
        if saida and abs(saida[-1].y0 - r.y0) < 1.5 and r.x0 <= saida[-1].x1 + 6:
            saida[-1] = saida[-1] | r
        else:
            saida.append(r)
    return saida


def escrever(livro: Livro, caminho: str, opcoes: OpcoesDeConversao | None = None) -> RelatorioDeConversao:
    """
    Escreve o PDF paginado de `livro` em `caminho` (§10.5) e devolve o relatório (§10.8), com
    `metadados["paginas"]`. `opcoes.modo_de_diagrama` decide se os diagramas saem como PNG
    (padrão) ou na fonte; a página é `livro.pagina`.
    """
    import fitz

    opcoes = opcoes or OpcoesDeConversao()
    caminho = os.fspath(caminho)
    relatorio = RelatorioDeConversao(formato="pdf", arquivos=[caminho])
    with Cronometro(relatorio):
        montador = _Montador(livro, opcoes, relatorio)
        html, css = montador.montar()
        arquivo = fitz.Archive()
        for nome, dados in montador.dados.items():
            arquivo.add(dados, nome)
        story = fitz.Story(html=html, user_css=css, em=float(opcoes.corpo_pt) if opcoes.corpo_pt else 11.0,
                           archive=arquivo)
        pagina = livro.pagina
        buffer = io.BytesIO()
        writer = fitz.DocumentWriter(buffer)
        posicoes: list[Any] = []
        n = 0
        while True:
            mediabox, rect = _rects(pagina, n)
            dev = writer.begin_page(mediabox)
            more, _filled = story.place(rect)
            story.element_positions(lambda pos: posicoes.append(pos), {"page": n})
            story.draw(dev)
            writer.end_page()
            n += 1
            if not more or n > 5000:
                break
        writer.close()
        doc = fitz.open("pdf", buffer.getvalue())
        try:
            _acabamento(doc, livro, posicoes, relatorio)
            temporario = caminho + ".tmp"
            doc.save(temporario, garbage=3, deflate=True)
        finally:
            doc.close()
        os.replace(temporario, caminho)
        relatorio.metadados["paginas"] = n
        relatorio.fontes_embutidas = list(montador.fontes_embutidas)
    relatorio.contar(livro)
    return relatorio


def _acabamento(doc: Any, livro: Livro, posicoes: list[Any], relatorio: RelatorioDeConversao) -> None:
    """Cabeçalhos, rodapés, sumário, links e metadados sobre o PDF já paginado."""
    import fitz

    pagina = livro.pagina
    superior, _externa, inferior, _interna = (mm(v) for v in pagina.margens_mm)
    titulos = [p for p in posicoes if p.heading and p.open_close & 1 and p.text]
    capitulo_por_pagina: dict[int, str] = {}
    atual = ""
    h1 = [p for p in titulos if p.heading == 1]
    for k in range(doc.page_count):
        for p in h1:
            if p.page == k:
                atual = p.text
        capitulo_por_pagina[k] = atual
        if not atual:
            for p in h1:
                if p.page > k:
                    capitulo_por_pagina[k] = p.text      # antes do primeiro título: o que vem
                    break
    for k, page in enumerate(doc):
        mediabox, rect = _rects(pagina, k)
        par = k % 2 == 1
        tipo = pagina.cabecalho_par if par else pagina.cabecalho_impar
        texto = _cabecalho(livro, tipo, capitulo_por_pagina.get(k, ""))
        if texto:
            largura = fitz.get_text_length(_latin1(texto), fontname="helv", fontsize=CORPO_DO_CABECALHO)
            x = rect.x0 if par else max(rect.x0, rect.x1 - largura)
            page.insert_text((x, superior * 0.6), _latin1(texto), fontname="helv", fontsize=CORPO_DO_CABECALHO,
                             color=(0.25, 0.25, 0.25))
        if pagina.numerar_paginas:
            numero = str(k + 1)
            largura = fitz.get_text_length(numero, fontname="helv", fontsize=CORPO_DO_CABECALHO)
            page.insert_text(((rect.x0 + rect.x1 - largura) / 2, mediabox.height - inferior * 0.45), numero,
                             fontname="helv", fontsize=CORPO_DO_CABECALHO, color=(0.25, 0.25, 0.25))
    # o sumário: os títulos, com os níveis sem salto
    toc: list[list[Any]] = []
    anterior = 0
    for p in titulos:
        nivel = max(1, min(int(p.heading), anterior + 1))
        destino = {"kind": fitz.LINK_GOTO, "page": p.page, "to": fitz.Point(p.rect[0], p.rect[1])}
        toc.append([nivel, p.text, p.page + 1, destino])
        anterior = nivel
    if toc:
        try:
            doc.set_toc(toc)
        except Exception as erro:      # noqa: BLE001 — um sumário torto não derruba o PDF
            relatorio.aviso(f"sumário do PDF não escrito: {erro}")
    # os links: internos por posição do id, externos por URI
    alvos: dict[str, Any] = {}
    for p in posicoes:
        if p.id and p.open_close & 1 and p.id not in alvos:
            alvos[p.id] = p
    por_link: dict[tuple[int, str], list[Any]] = {}
    for p in posicoes:
        if p.href and p.open_close & 1:
            por_link.setdefault((p.page, p.href), []).append(p)
    perdidos = 0
    for (numero, href), pedacos in por_link.items():
        page = doc[numero]
        for r in _fundir_rects(pedacos):
            if href.startswith("#"):
                alvo = alvos.get(href[1:])
                if alvo is None:
                    perdidos += 1
                    continue
                page.insert_link({"kind": fitz.LINK_GOTO, "from": r, "page": alvo.page,
                                  "to": fitz.Point(alvo.rect[0], alvo.rect[1])})
            elif "://" in href or href.startswith("mailto:"):
                page.insert_link({"kind": fitz.LINK_URI, "from": r, "uri": href})
    if perdidos:
        relatorio.aviso(f"{perdidos} link(s) interno(s) sem alvo no PDF")
    metadados = {"title": livro.metadados.titulo, "author": "; ".join(a.nome for a in livro.metadados.autores),
                 "creator": "PyBoxEditor", "producer": "PyBoxEditor (MuPDF)"}
    doc.set_metadata(metadados)
    if livro.metadados.idioma:
        try:
            doc.set_language(livro.metadados.idioma)
        except Exception:      # noqa: BLE001 — idioma que o MuPDF não aceita
            pass


def titulo_do_capitulo(cap: Capitulo) -> str:
    for bloco in cap.blocos:
        if isinstance(bloco, Titulo):
            return modelo.texto_de(bloco)
    return cap.titulo or cap.arquivo


__all__ = ["escrever", "chave_do_capitulo", "mm", "PT_POR_MM", "CORPO_DO_CABECALHO"]
