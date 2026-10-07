"""
Os testes de aceitação do documento editorial (item 10 da `docs/REVISAO_MODOS_OCR.md`).

**Invariante 10 do `CONTEXT.md`: todos os formatos percorrem a mesma sequência
ordenada de blocos editoriais.** Nenhum teste a conferia: cada escritor tinha os
seus, e cada um olhava o próprio arquivo. Aqui uma página com título de
capítulo, prosa com negrito, lance com figurina, o cabeçalho impresso de um
diagrama, o diagrama, uma tabela e o fecho vai ao documento editorial e sai
pelos escritores de produção — HTML e PDF pesquisável do documento
(`EditorialExporter`), EPUB e DOCX do `exportar.py` a partir do documento de
volta (`pagina_editorial_para_extraida`, o caminho da exportação revisada) —, e
cada arquivo é relido para a sequência de blocos que ele de fato contém.

O que o teste achou na primeira rodada, e que foi corrigido junto:
o PDF pesquisável e o TXT do documento escreviam a tabela como o JSON do valor
(`{"rows": [["W", "Win"], …]}`) e a figura sem posição como o PNG inteiro em
base64 — na camada de texto invisível do PDF, que é o que a busca encontra.
"""

import base64
import html.parser
import re
import zipfile
from xml.etree import ElementTree

import fitz

from core import exportar, livro, render_diagrama
from core.editorial_adapters import (pagina_editorial_para_extraida,
                                     paginas_extraidas_para_documento)
from core.editorial_export import EditorialExporter, ExportOptions

FEN = "8/1k6/1p6/1K6/P1P5/8/8/8"
TABULEIRO = re.compile(r"(?:[pnbrqkPNBRQK1-8]{1,8}/){7}[pnbrqkPNBRQK1-8]{1,8}")


def _png_do_diagrama():
    """`(png, largura, altura)` do tabuleiro desenhado do FEN."""
    return render_diagrama.desenhar(FEN + " b - - 0 1", lado_px=96)


def _png_liso(lado=40):
    imagem = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, lado, lado), False)
    imagem.clear_with(200)
    return imagem.tobytes("png")


def _pagina():
    """A página de prova: tudo que um livro de xadrez põe numa página."""
    png, largura, altura = _png_do_diagrama()
    diagrama = livro.Figura(png, largura, altura, fen=FEN + " b - - 0 1",
                            origem="render", lado_a_jogar="b", lado_origem="legenda")
    cabecalho = livro.Figura(_png_liso(), 40, 12, origem="faixa")
    return livro.PaginaExtraida(numero=0, blocos=[
        livro.Paragrafo("Chapter 1 Pawn Endgames", titulo=True, nivel=1),
        livro.Paragrafo("White has the opposition, but it is not enough to win.",
                        negrito=[(0, 5)]),
        livro.Paragrafo("1...♔c7! is the only move, and 2.♘f3 changes nothing."),
        cabecalho,
        diagrama,
        livro.Tabela([["W", "Win"], ["D", "Draw"], ["B♖h2", "W♔d1"]]),
        livro.Paragrafo("Since 2.c5 would be useless, the king starts an outflanking maneuver."),
    ], largura=1240, altura=1754, dpi=150)


def _sequencia_do_documento(documento):
    """A sequência que todo formato tem de percorrer, lida do próprio IR."""
    saida = []
    for pagina in documento.pages:
        for bloco in sorted(pagina.blocks, key=lambda b: b.order):
            valor = bloco.decision.value
            if bloco.kind == "heading":
                saida.append(("titulo", str(valor)))
            elif bloco.kind in ("paragraph", "chess_sequence"):
                saida.append(("texto", str(valor)))
            elif bloco.kind == "diagram":
                saida.append(("diagrama", TABULEIRO.search(valor["fen"]).group(0)))
            elif bloco.kind in ("figure", "caption"):
                saida.append(("figura",))
            elif bloco.kind == "table":
                saida.append(("tabela", tuple(c for fila in valor["rows"] for c in fila)))
    return saida


# ----------------------------------------------------------------------
# Relendo cada formato
# ----------------------------------------------------------------------

class _Leitor(html.parser.HTMLParser):
    """Os blocos de um HTML/XHTML, na ordem: títulos, parágrafos, figuras, tabelas."""

    TEXTO = {"p", "h1", "h2", "h3"}

    def __init__(self, so_dentro_de=None):
        super().__init__(convert_charrefs=True)
        self.blocos, self._pilha, self._texto, self._celulas = [], [], None, None
        self._dentro = so_dentro_de is None
        self._marca = so_dentro_de

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self._marca and tag == self._marca:
            self._dentro = True
        if not self._dentro:
            return
        if tag in self.TEXTO or (tag == "div" and "chess-sequence" in attrs.get("class", "")):
            self._pilha.append(("titulo" if tag.startswith("h") else "texto"))
            self._texto = []
        elif tag == "figure":
            fen = attrs.get("data-fen")
            self._pilha.append("figure")
            self._figura = fen
        elif tag == "img" and self._pilha and self._pilha[-1] == "figure" and self._figura is None:
            achado = TABULEIRO.search(attrs.get("alt", ""))
            self._figura = achado.group(0) if achado else ""
        elif tag == "table":
            self._celulas = []
        elif tag == "td" and self._celulas is not None:
            self._texto = []

    def handle_endtag(self, tag):
        if not self._dentro:
            return
        if self._marca and tag == self._marca:
            self._dentro = False
        if tag in self.TEXTO or tag == "div":
            if self._pilha and self._pilha[-1] in ("titulo", "texto") and self._texto is not None:
                tipo = self._pilha.pop()
                texto = " ".join("".join(self._texto).split())
                if texto:
                    self.blocos.append((tipo, texto))
                self._texto = None
        elif tag == "figure" and self._pilha and self._pilha[-1] == "figure":
            self._pilha.pop()
            achado = TABULEIRO.search(self._figura or "")
            self.blocos.append(("diagrama", achado.group(0)) if achado else ("figura",))
        elif tag == "td" and self._celulas is not None:
            self._celulas.append(" ".join("".join(self._texto).split()))
            self._texto = None
        elif tag == "table" and self._celulas is not None:
            self.blocos.append(("tabela", tuple(self._celulas)))
            self._celulas = None

    def handle_data(self, dados):
        if self._texto is not None and not (self._pilha and self._pilha[-1] == "figure"):
            self._texto.append(dados)


def _do_html(caminho):
    leitor = _Leitor(so_dentro_de="section")
    leitor.feed(caminho.read_text(encoding="utf-8"))
    return leitor.blocos


def _do_epub(caminho):
    blocos = []
    with zipfile.ZipFile(caminho) as epub:
        for nome in sorted(n for n in epub.namelist()
                           if re.search(r"pagina-\d{4}\.xhtml$", n)):
            leitor = _Leitor(so_dentro_de="body")
            leitor.feed(epub.read(nome).decode("utf-8"))
            blocos.extend(leitor.blocos)
    return blocos


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"


def _do_docx(caminho):
    with zipfile.ZipFile(caminho) as docx:
        corpo = ElementTree.fromstring(docx.read("word/document.xml")).find(f"{W}body")
    blocos = []
    for filho in corpo:
        if filho.tag == f"{W}p":
            forma = filho.find(f".//{WP}docPr")
            if forma is not None:
                achado = TABULEIRO.search(forma.get("descr", ""))
                blocos.append(("diagrama", achado.group(0)) if achado else ("figura",))
                continue
            texto = " ".join("".join(t.text or "" for t in filho.iter(f"{W}t")).split())
            if not texto:
                continue                                   # o separador de 1 pt
            estilo = filho.find(f"{W}pPr/{W}pStyle")
            titulo = estilo is not None and estilo.get(f"{W}val", "").startswith("Heading")
            blocos.append(("titulo" if titulo else "texto", texto))
        elif filho.tag == f"{W}tbl":
            celulas = tuple(" ".join("".join(t.text or "" for t in c.iter(f"{W}t")).split())
                            for c in filho.iter(f"{W}tc"))
            blocos.append(("tabela", celulas))
    return blocos


def _texto_do_pdf(caminho):
    with fitz.open(caminho) as pdf:
        return " ".join(" ".join(pagina.get_text("text") for pagina in pdf).split())


def _pdf_de_origem(caminho, pagina):
    """A digitalização da página, do tamanho que a largura e o dpi dizem."""
    pontos = pagina.largura * 72 / pagina.dpi, pagina.altura * 72 / pagina.dpi
    with fitz.open() as pdf:
        pdf.new_page(width=pontos[0], height=pontos[1])
        pdf.save(caminho)
    return caminho


# ----------------------------------------------------------------------
# A aceitação
# ----------------------------------------------------------------------

def _exportar_os_quatro(tmp_path, pagina):
    documento = paginas_extraidas_para_documento([pagina], document_id="aceite")
    documento.metadata["source_path"] = str(_pdf_de_origem(tmp_path / "scan.pdf", pagina))
    exportador = EditorialExporter()
    exportador.export(documento, tmp_path / "livro.html",
                      ExportOptions(format="html", mode="clean"))
    relatorio_pdf = exportador.export(documento, tmp_path / "livro.pdf",
                                      ExportOptions(format="pdf", mode="clean",
                                                    source_pdf=documento.metadata["source_path"]))
    volta = [pagina_editorial_para_extraida(p) for p in documento.pages]
    exportar.exportar(volta, str(tmp_path / "livro.epub"), formato="epub", titulo="Aceite")
    exportar.exportar(volta, str(tmp_path / "livro.docx"), formato="docx", titulo="Aceite")
    return documento, relatorio_pdf


def test_os_quatro_formatos_percorrem_a_mesma_sequencia_de_blocos(tmp_path):
    documento, _ = _exportar_os_quatro(tmp_path, _pagina())
    esperado = _sequencia_do_documento(documento)
    assert [b[0] for b in esperado] == ["titulo", "texto", "texto", "figura",
                                        "diagrama", "tabela", "texto"]
    assert _do_html(tmp_path / "livro.html") == esperado
    assert _do_epub(tmp_path / "livro.epub") == esperado
    assert _do_docx(tmp_path / "livro.docx") == esperado


def test_o_pdf_pesquisavel_tem_o_texto_de_cada_bloco_na_ordem_e_nada_mais(tmp_path):
    documento, relatorio = _exportar_os_quatro(tmp_path, _pagina())
    texto = _texto_do_pdf(tmp_path / "livro.pdf")
    posicao = 0
    for bloco in _sequencia_do_documento(documento):
        if bloco[0] in ("titulo", "texto"):
            procurado = " ".join(bloco[1].split())
        elif bloco[0] == "diagrama":
            procurado = bloco[1]
        elif bloco[0] == "tabela":
            procurado = " ".join(bloco[1])
        else:
            continue                                        # figura sem texto
        achado = texto.find(procurado, posicao)
        assert achado >= 0, f"{procurado!r} fora de ordem ou ausente em {texto!r}"
        posicao = achado + len(procurado)
    # o que não é texto do livro não entra na camada que a busca lê
    assert "rows" not in texto and "png_base64" not in texto and "{" not in texto
    assert relatorio.metadata["failed_items"] == 0


def test_a_tabela_sai_como_tabela_nos_quatro_formatos(tmp_path):
    _exportar_os_quatro(tmp_path, _pagina())
    celulas = ("W", "Win", "D", "Draw", "B♖h2", "W♔d1")
    for relida in (_do_html(tmp_path / "livro.html"), _do_epub(tmp_path / "livro.epub"),
                   _do_docx(tmp_path / "livro.docx")):
        assert ("tabela", celulas) in relida
    assert "W Win D Draw B♖h2 W♔d1" in _texto_do_pdf(tmp_path / "livro.pdf")


def test_o_txt_do_documento_tem_a_tabela_e_nao_o_png(tmp_path):
    """Pelos dois caminhos: o exportador e a fachada, que tinha o TXT dela."""
    from core import editorial_pipeline

    documento = paginas_extraidas_para_documento([_pagina()], document_id="aceite")
    for exportador in (lambda d, c: EditorialExporter().export(
                           d, c, ExportOptions(format="txt")),
                       lambda d, c: editorial_pipeline.EditorialPipeline().export(
                           d, c, editorial_pipeline.ExportOptions(format="txt"))):
        destino = tmp_path / "livro.txt"
        exportador(documento, destino)
        texto = destino.read_text(encoding="utf-8")
        assert "W Win" in texto and "B♖h2 W♔d1" in texto
        assert "png_base64" not in texto and '"rows"' not in texto
        assert len(texto) < 2000, "o PNG da figura foi parar no texto"


ESQUERDA = (["The first column opens the chapter, and its",
             "lines run down the left half of the page."],
            ["A second paragraph in the same column keeps",
             "the reader on the left before the gutter."])
DIREITA = (["The right column starts at the same height,",
            "so reading across the page would mix them."],
           ["Its last paragraph closes the page, and it",
            "must come after everything on the left."])


def _pdf_de_duas_colunas(caminho):
    """Uma página nascida digital em duas colunas, com as linhas das duas na
    mesma altura: quem lê de cima para baixo intercala as colunas."""
    with fitz.open() as pdf:
        pagina = pdf.new_page(width=600, height=800)
        for x, coluna in ((50, ESQUERDA), (320, DIREITA)):
            y = 100
            for paragrafo in coluna:
                for i, linha in enumerate(paragrafo):
                    pagina.insert_text((x + (10 if i == 0 else 0), y), linha,
                                       fontname="helv", fontsize=9)
                    y += 12
                y += 6
        pdf.save(caminho)
    return str(caminho)


def test_duas_colunas_de_ponta_a_ponta(tmp_path):
    """A página de duas colunas vai do leitor ao arquivo na ordem de leitura:
    a coluna da esquerda inteira, depois a da direita — no documento, no EPUB
    e no HTML."""
    paginas = livro.extrair(_pdf_de_duas_colunas(tmp_path / "duas.pdf"),
                            lambda recorte, referencia=None: ("a", 0.99), camada="auto")
    assert [p.leitura for p in paginas] == ["camada"] and paginas[0].colunas == 2
    documento = paginas_extraidas_para_documento(paginas, document_id="colunas")
    EditorialExporter().export(documento, tmp_path / "duas.html",
                               ExportOptions(format="html", mode="clean"))
    volta = [pagina_editorial_para_extraida(p) for p in documento.pages]
    exportar.exportar(volta, str(tmp_path / "duas.epub"), formato="epub", titulo="Colunas")

    ordem = [" ".join(p) for p in (*ESQUERDA, *DIREITA)]
    for relida in (_sequencia_do_documento(documento), _do_html(tmp_path / "duas.html"),
                   _do_epub(tmp_path / "duas.epub")):
        texto = " ".join(b[1] for b in relida if b[0] == "texto")
        posicoes = [texto.find(trecho) for trecho in ordem]
        assert -1 not in posicoes and posicoes == sorted(posicoes), relida


def test_a_figura_sem_posicao_nao_vira_base64_em_lugar_nenhum(tmp_path):
    _exportar_os_quatro(tmp_path, _pagina())
    png = base64.b64encode(_png_liso()).decode("ascii")[:40]
    assert png not in _texto_do_pdf(tmp_path / "livro.pdf")
    # no HTML ela é a imagem mesmo, com o rótulo no alt
    html_texto = (tmp_path / "livro.html").read_text(encoding="utf-8")
    assert 'alt="Cabeçalho do diagrama"' in html_texto
