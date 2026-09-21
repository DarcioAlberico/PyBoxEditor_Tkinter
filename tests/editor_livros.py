"""
Os livros de prova da ED-01, compartilhados por `test_editor_epub.py`,
`test_editor_livro_ops.py` e `test_editor_projeto.py`.

- `epub_de_hoje(pasta, modo)`: o que `exportar.para_epub` escreve hoje — negrito,
  títulos 1 e 2, diagrama em imagem e em fonte (com e sem coordenadas, dos dois
  lados), tabela, figurina e um recorte de scan.
- `epub_de_fora(pasta)`: um EPUB montado à mão à moda do Sigil/Calibre — `content.opf`
  com `refines`, dois identificadores, `calibre:series` com prefixo, capa com
  `linear="no"`, NCX **sem** nav, duas folhas por capítulo (uma com `@media`), um
  `<svg>` com `&nbsp;` dentro, `id="title"` em dois capítulos, um arquivo fora do
  manifesto e um `META-INF/com.apple.ibooks.display-options.xml`.
- `livro_de_teste()`: um `Livro` de três capítulos com notas, links cruzados, sumário,
  marcos, uma figura e uma folha — o que as operações de livro precisam.
- `livro_completo()`: o livro sintético da ED-09 — todo estilo de parágrafo e todo
  atributo de trecho da §6.2/§6.3, listas (aninhada, alfabética a partir de 3, romana),
  tabela com cabeçalho e legenda, figura PNG e SVG, diagrama em imagem e em fonte (com e
  sem coordenadas, nas duas fontes), notas de rodapé e de fim, doze marcas de página, uma
  quebra de página, separador, ilha de bloco e inline, links e referências cruzadas.
"""

from __future__ import annotations

import os
import zipfile

from core.editor import modelo as m
from core.editor import sumario

FEN = "r1bqk2r/pp2bppp/2n1pn2/3p4/3P4/2N1PN2/PP2BPPP/R1BQK2R w - - 0 1"


# ----------------------------------------------------------------------
# O EPUB de hoje
# ----------------------------------------------------------------------

def _figura(fonte_nome, coordenadas, orientacao, texto=True, emoldurada=False):
    from core import livro, render_diagrama as rd
    png, largura, altura = rd.desenhar(FEN, lado_px=96)
    if not texto:
        return livro.Figura(png, largura, altura, origem="recorte")
    fonte = rd.carregar(fonte_nome)
    linhas = (rd.grade(FEN, fonte, orientacao, "simples", "reto") if emoldurada
              else rd.linhas(FEN, fonte, orientacao))
    return livro.Figura(png, largura, altura, fen=FEN, origem="render", linhas=linhas,
                        fonte=fonte.nome, coordenadas=coordenadas, orientacao=orientacao,
                        linhas_emolduradas=emoldurada)


def epub_de_hoje(pasta: str, modo: str = "png", titulo: str = "Livro de hoje", autor: str = "Autora") -> str:
    from core import exportar, livro
    paginas = [
        livro.PaginaExtraida(numero=0, blocos=[
            livro.Paragrafo("Capítulo um", titulo=True, nivel=1),
            livro.Paragrafo("Prosa com negrito e ♕ figurina.", negrito=[(10, 17)]),
            _figura("SkakNew-Diagram", True, "branca"),
            _figura("SkakNew-Diagram", False, "preta"),
            livro.Paragrafo("Depois", titulo=True, nivel=2),
            livro.Tabela([["a", "b"], ["c", "d"]]),
        ]),
        livro.PaginaExtraida(numero=1, blocos=[
            livro.Paragrafo("Página dois."),
            _figura("ChessMerida-Diagram", True, "preta", emoldurada=True),
            _figura("SkakNew-Diagram", False, "branca", texto=False),
        ]),
    ]
    caminho = os.path.join(pasta, f"hoje-{modo}.epub")
    exportar.para_epub(paginas, caminho, diagramas=modo, titulo=titulo, autor=autor)
    return caminho


# ----------------------------------------------------------------------
# Um EPUB "de fora"
# ----------------------------------------------------------------------

OPF_DE_FORA = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId" prefix="calibre: https://calibre-ebook.com">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">urn:uuid:11111111-2222-3333-4444-555555555555</dc:identifier>
    <dc:identifier id="isbn">urn:isbn:9780000000000</dc:identifier>
    <meta refines="#isbn" property="identifier-type" scheme="onix:codelist5">15</meta>
    <dc:title id="title">Livro de Fora</dc:title>
    <meta refines="#title" property="title-type">main</meta>
    <dc:title id="sub">Um subtítulo</dc:title>
    <meta refines="#sub" property="title-type">subtitle</meta>
    <dc:language>pt-BR</dc:language>
    <dc:creator id="creator01">Ana Silva</dc:creator>
    <meta refines="#creator01" property="role" scheme="marc:relators">aut</meta>
    <meta refines="#creator01" property="file-as">Silva, Ana</meta>
    <meta refines="#creator01" property="display-seq">1</meta>
    <dc:contributor id="ed1" opf:role="edt">Bruno Costa</dc:contributor>
    <dc:publisher>Editora X</dc:publisher>
    <dc:date>2020-01-02</dc:date>
    <dc:subject>Xadrez</dc:subject>
    <dc:description>Uma descrição &amp; tal.</dc:description>
    <dc:rights>© 2020</dc:rights>
    <dc:source id="src">urn:isbn:9780000000000</dc:source>
    <meta refines="#src" property="source-of">pagination</meta>
    <meta property="belongs-to-collection" id="c01">Série Y</meta>
    <meta refines="#c01" property="collection-type">series</meta>
    <meta refines="#c01" property="group-position">3</meta>
    <meta property="dcterms:modified">2020-01-02T03:04:05Z</meta>
    <meta property="calibre:series">Série Y</meta>
    <meta name="calibre:series_index" content="3"/>
    <meta name="cover" content="capa"/>
    <meta property="schema:accessMode">textual</meta>
    <meta property="schema:accessibilityFeature">displayTransformability</meta>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="capa" href="Images/capa.png" media-type="image/png" properties="cover-image"/>
    <item id="capa_xhtml" href="Text/capa.xhtml" media-type="application/xhtml+xml" properties="svg"/>
    <item id="cap1" href="Text/cap%201.xhtml" media-type="application/xhtml+xml" properties="svg"/>
    <item id="cap2" href="Text/cap2.xhtml" media-type="application/xhtml+xml"/>
    <item id="notas" href="Text/notas.xhtml" media-type="application/xhtml+xml"/>
    <item id="a" href="Styles/a.css" media-type="text/css"/>
    <item id="b" href="Styles/b.css" media-type="text/css"/>
    <item id="fig" href="Images/fig.png" media-type="image/png"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="capa_xhtml" linear="no"/>
    <itemref idref="cap1"/>
    <itemref idref="cap2"/>
    <itemref idref="notas" linear="no"/>
  </spine>
  <guide>
    <reference type="cover" title="Capa" href="Text/capa.xhtml"/>
    <reference type="text" title="Início" href="Text/cap%201.xhtml"/>
  </guide>
</package>
"""

CAPA_DE_FORA = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Capa</title><link rel="stylesheet" type="text/css" href="../Styles/a.css"/></head>
<body epub:type="cover">
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" width="100%" height="100%" viewBox="0 0 600 800" preserveAspectRatio="xMidYMid meet"><image width="600" height="800" xlink:href="../Images/capa.png"/></svg>
</body>
</html>
"""

CAP1_DE_FORA = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
<title>Capítulo 1</title>
<link rel="stylesheet" type="text/css" href="../Styles/a.css"/>
<link rel="stylesheet" type="text/css" href="../Styles/b.css"/>
</head>
<body>
<h1 id="title">Capítulo&nbsp;um</h1>
<p class="primeira">Texto com <b>negrito</b>, <cite>uma citação</cite> e um link para <a href="cap2.xhtml#title">o dois</a>.</p>
<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><text x="1" y="1">a&nbsp;b</text></svg>
<p>Uma nota<a epub:type="noteref" href="notas.xhtml#n1">1</a> e uma figura.</p>
<figure><img src="../Images/fig.png" alt="uma figura"/></figure>
</body>
</html>
"""

CAP2_DE_FORA = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<title>Capítulo 2</title>
<link rel="stylesheet" type="text/css" href="../Styles/b.css"/>
<link rel="stylesheet" type="text/css" href="../Styles/a.css"/>
</head>
<body>
<h1 id="title">Capítulo dois</h1>
<p>Volta para <a href="cap%201.xhtml#title">o um</a>.</p>
</body>
</html>
"""

NOTAS_DE_FORA = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Notas</title></head>
<body>
<aside epub:type="footnote" id="n1"><p>A nota.</p></aside>
</body>
</html>
"""

NCX_DE_FORA = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<head><meta name="dtb:uid" content="urn:uuid:11111111-2222-3333-4444-555555555555"/></head>
<docTitle><text>Livro de Fora</text></docTitle>
<navMap>
<navPoint id="np1" playOrder="1"><navLabel><text>Capítulo um</text></navLabel><content src="Text/cap%201.xhtml#title"/></navPoint>
<navPoint id="np2" playOrder="2"><navLabel><text>Capítulo dois</text></navLabel><content src="Text/cap2.xhtml#title"/></navPoint>
</navMap>
</ncx>
"""

CSS_A_DE_FORA = "@import url(b.css);\nbody { margin: 0 6%; }\n@media print { p { orphans: 3; } }\np > span.x { color: red }\n"
CSS_B_DE_FORA = "h1 { background: url(../Images/fig.png) no-repeat; }\n"
DISPLAY_OPTIONS_DE_FORA = ('<?xml version="1.0" encoding="UTF-8"?>\n<display_options><platform name="*">'
                           '<option name="specified-fonts">true</option></platform></display_options>\n')

PNG_MINIMO = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8cfc0f01f0005000"
    "1ff0aa5f0e50000000049454e44ae426082")


def epub_de_fora(pasta: str) -> str:
    caminho = os.path.join(pasta, "de-fora.epub")
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" '
                   'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                   '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                   "</rootfiles></container>")
        z.writestr("META-INF/com.apple.ibooks.display-options.xml", DISPLAY_OPTIONS_DE_FORA)
        z.writestr("OEBPS/content.opf", OPF_DE_FORA)
        z.writestr("OEBPS/toc.ncx", NCX_DE_FORA)
        z.writestr("OEBPS/Text/capa.xhtml", CAPA_DE_FORA)
        z.writestr("OEBPS/Text/cap 1.xhtml", CAP1_DE_FORA)
        z.writestr("OEBPS/Text/cap2.xhtml", CAP2_DE_FORA)
        z.writestr("OEBPS/Text/notas.xhtml", NOTAS_DE_FORA)
        z.writestr("OEBPS/Styles/a.css", CSS_A_DE_FORA)
        z.writestr("OEBPS/Styles/b.css", CSS_B_DE_FORA)
        z.writestr("OEBPS/Images/capa.png", PNG_MINIMO)
        z.writestr("OEBPS/Images/fig.png", PNG_MINIMO)
        z.writestr("OEBPS/sobra.txt", "esquecido")
    return caminho


# ----------------------------------------------------------------------
# Um modelo montado à mão
# ----------------------------------------------------------------------

def _p(texto: str, **kw) -> m.Paragrafo:
    return m.Paragrafo(trechos=[m.Trecho(texto=texto)], **kw)


def livro_de_teste() -> m.Livro:
    folha = "Styles/estilo.css"
    c1 = m.Capitulo(arquivo="Text/cap-0001.xhtml", folhas=[folha], blocos=[
        m.Titulo(trechos=[m.Trecho(texto="Um")], nivel=1, id="t1"),
        m.Paragrafo(trechos=[m.Trecho(texto="Vai para "), m.Trecho(texto="o alvo", link="Text/cap-0002.xhtml#alvo")],
                    id="x", id_persistente=True),
    ])
    c2 = m.Capitulo(arquivo="Text/cap-0002.xhtml", folhas=[folha], blocos=[
        m.Titulo(trechos=[m.Trecho(texto="Dois")], nivel=1, id="t2"),
        m.Paragrafo(trechos=[m.Trecho(texto="Antes"), m.Trecho(nota="n1")], id="a", id_persistente=True),
        m.Paragrafo(trechos=[m.Trecho(texto="Meio "), m.Trecho(texto="interno", link="#alvo")], id="meio",
                    id_persistente=True),
        m.Figura(recurso="Images/fig.png", alt="figura", id="fig", id_persistente=True),
        m.Paragrafo(trechos=[m.Trecho(texto="Alvo")], id="alvo", id_persistente=True),
        m.Paragrafo(trechos=[m.Trecho(texto="Depois"), m.Trecho(nota="n2"),
                             m.Trecho(texto=" e o um", link="Text/cap-0001.xhtml#t1")], id="d", id_persistente=True),
    ], notas=[m.Nota(id="n1", blocos=[_p("nota um")]), m.Nota(id="n2", blocos=[_p("nota dois")])])
    c3 = m.Capitulo(arquivo="Text/cap-0003.xhtml", folhas=[folha], blocos=[
        m.Titulo(trechos=[m.Trecho(texto="Três")], nivel=1, id="t3"),
        m.Paragrafo(trechos=[m.Trecho(texto="Para o meio", link="Text/cap-0002.xhtml#meio")], id="y",
                    id_persistente=True),
        m.IlhaBruta(xhtml='<svg xmlns="http://www.w3.org/2000/svg"><image href="../Images/fig.png"/></svg>',
                    elemento="svg"),
    ])
    livro = m.Livro(
        metadados=m.Metadados(titulo="Teste", idioma="pt", identificador="urn:uuid:teste"),
        capitulos=[c1, c2, c3],
        recursos={
            folha: m.Recurso(caminho=folha, tipo_mime="text/css",
                             dados=b"h1 { background: url(../Images/fig.png); }\n"),
            "Images/fig.png": m.Recurso(caminho="Images/fig.png", tipo_mime="image/png", dados=PNG_MINIMO),
        },
        folhas=[folha], marcos=[("bodymatter", "Text/cap-0001.xhtml")],
        opf="OEBPS/package.opf", nav="nav.xhtml", ncx="toc.ncx",
    )
    livro.sumario = sumario.gerar_dos_titulos(livro)
    return livro


# ----------------------------------------------------------------------
# O livro sintético completo (ED-09; AC-ED09-1)
# ----------------------------------------------------------------------

FEN_COMPLETO = FEN
#: Um PNG 40×30 vermelho, para a figura (o `PNG_MINIMO` é 1×1).
PNG_40x30 = None


def _png_40x30() -> bytes:
    global PNG_40x30
    if PNG_40x30 is None:
        import io as _io

        from PIL import Image

        buffer = _io.BytesIO()
        Image.new("RGB", (40, 30), (200, 30, 30)).save(buffer, "PNG")
        PNG_40x30 = buffer.getvalue()
    return PNG_40x30


def _t(texto: str = "", **kw) -> m.Trecho:
    return m.Trecho(texto=texto, **kw)


def _par(*trechos, **kw) -> m.Paragrafo:
    return m.Paragrafo(trechos=[t if isinstance(t, m.Trecho) else _t(t) for t in trechos], **kw)


def livro_completo() -> m.Livro:
    """Ver o cabeçalho. Dois capítulos: o primeiro tem tudo; o segundo é o alvo dos links."""
    blocos: list = []
    blocos.append(m.Titulo(trechos=[_t("Capítulo um")], nivel=1, id="cap1-t", id_persistente=True))
    blocos.append(_par("Primeira linha sem recuo.", estilo="primeira"))
    blocos.append(_par(
        _t("neg", negrito=True), _t(" ita", italico=True), _t(" sub", sublinhado=True), _t(" tach", tachado=True),
        _t(" Versalete", versalete=True), _t(" x", posicao="sobre"), _t("2", posicao="sub"),
        _t(" ♕", familia="simbolos"), _t(" arial", familia="Arial", corpo_pt=9, cor="#ff0000"),
        _t(" escuro", fundo="#003366"), _t(" amarelo", fundo="#ffff00"), _t(" english", lang="en"),
        _t(" 23.Nf3", papel="lance"), _t("!?", papel="nag", nag=5), _t(" ♘", papel="figurina"),
        _t(" (comentário)", papel="comentario"), _t(" Carlsen", papel="jogador", chave="carlsen"),
        _t(" Siciliana", papel="abertura", chave="B90"), _t(" cod", codigo=True),
        _t("nova linha", quebra_antes=True)))
    blocos.append(_par(
        _t("Página marcada "), _t("aqui", pagina=7), _t(" e uma ilha "), _t(ilha="<cite>Obra</cite>"),
        _t(" e um link "), _t("externo", link="https://example.org/x"), _t(" e outro "),
        _t("interno", link="cap2.xhtml#alvo"), _t(" e ver "), _t("Tabela 1", ref="tabela", link="#tab1"),
        _t(", "), _t("Figura 1", ref="figura", link="#fig1"), _t(", "), _t("Diagrama 1", ref="diagrama", link="#dia1"),
        _t(" e "), _t("Capítulo um", ref="titulo", link="#cap1-t"), _t("."), _t(nota="n1"), _t(" fim"), _t(nota="n2")))
    for estilo in ("notacao", "comentario", "legenda", "destaque", "epigrafe", "assinatura", "cabecalho-diagrama"):
        blocos.append(_par(f"Parágrafo {estilo}.", estilo=estilo))
    blocos.append(_par("Formatado.", alinhamento="direita", recuo_primeira_em=0, recuo_esquerda_em=1.5,
                       recuo_direita_em=0.5, antes_em=1, depois_em=0.5, entrelinha=1.5, manter_com_proximo=True,
                       manter_linhas=True))
    for n in range(2, 7):
        blocos.append(m.Titulo(trechos=[_t(f"Título {n}")], nivel=n))
    blocos.append(m.Citacao(blocos=[_par("Citação um."), _par("Citação dois.")]))
    blocos.append(m.Lista(ordenada=False, itens=[
        m.ItemDeLista(paragrafos=[_par("item a")]),
        m.ItemDeLista(paragrafos=[_par("item b"), _par("continuação de b")],
                      filhos=m.Lista(ordenada=False, itens=[m.ItemDeLista(paragrafos=[_par("sub b1")])])),
    ]))
    blocos.append(m.Lista(ordenada=True, inicio=3, marcador="alfa", itens=[
        m.ItemDeLista(paragrafos=[_par("primeiro")]), m.ItemDeLista(paragrafos=[_par("segundo")])]))
    blocos.append(m.Lista(ordenada=True, marcador="romano", itens=[m.ItemDeLista(paragrafos=[_par("um")])]))
    blocos.append(m.Tabela(id="tab1", id_persistente=True, primeira_fila_cabecalho=True, numero=1,
                           legenda=[_t("Resultados")], largura_pct=80, filas=[
        [m.Celula(blocos=[_par("Jogador")], cabecalho=True),
         m.Celula(blocos=[_par("Pontos")], cabecalho=True, alinhamento="direita")],
        [m.Celula(blocos=[_par("A")]), m.Celula(blocos=[_par("1")], alinhamento="direita")],
        [m.Celula(blocos=[_par("B")]), m.Celula(blocos=[_par("½")], alinhamento="direita")]]))
    blocos.append(m.Figura(id="fig1", id_persistente=True, recurso="Images/foto.png", alt="Uma foto",
                           legenda=[_t("A foto")], largura_pt=120))
    blocos.append(m.Figura(recurso="Images/desenho.svg", alt="Um desenho"))
    blocos.append(m.Diagrama(id="dia1", id_persistente=True, fen=FEN, legenda=[_t("Posição")], modo="png"))
    blocos.append(m.Diagrama(fen=FEN, fonte="SkakNew-Diagram", modo="fonte"))
    blocos.append(m.Diagrama(id="dia-skak-coord", fen=FEN, fonte="SkakNew-Diagram", coordenadas=True, modo="fonte"))
    blocos.append(m.Diagrama(fen=FEN, fonte="ChessMerida-Diagram", coordenadas=True, modo="fonte",
                             orientacao="preta"))
    blocos.append(m.Separador())
    blocos.append(m.IlhaBruta(xhtml='<svg xmlns="http://www.w3.org/2000/svg"><text>SVG solto</text></svg>',
                              elemento="svg"))
    for k in range(1, 13):
        blocos.append(m.MarcaDePagina(pagina=k + 10))
        blocos.append(_par(f"Texto da página {k + 10}."))
    blocos.append(m.QuebraDePagina())
    blocos.append(_par("Depois da quebra."))
    notas = [m.Nota(id="n1", tipo="rodape",
                    blocos=[_par("Nota de rodapé com ", _t("link", link="https://example.org/n"), ".")]),
             m.Nota(id="n2", tipo="fim", blocos=[_par("Nota de fim."), _par("Segundo parágrafo.")])]
    cap1 = m.Capitulo(arquivo="cap1.xhtml", blocos=blocos, notas=notas, idioma="pt-BR")
    cap2 = m.Capitulo(arquivo="cap2.xhtml", blocos=[
        m.Titulo(trechos=[_t("Capítulo dois")], nivel=1),
        _par("Alvo do link.", id="alvo", id_persistente=True),
        m.Titulo(trechos=[_t("Seção")], nivel=2), m.Titulo(trechos=[_t("Subseção")], nivel=3),
        m.Titulo(trechos=[_t("Fora do sumário")], nivel=4),
        _par("Fim.")])
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30">'
           b'<rect width="40" height="30" fill="blue"/></svg>')
    recursos = {"Images/foto.png": m.Recurso(caminho="Images/foto.png", tipo_mime="image/png", dados=_png_40x30()),
                "Images/desenho.svg": m.Recurso(caminho="Images/desenho.svg", tipo_mime="image/svg+xml", dados=svg)}
    return m.Livro(metadados=m.Metadados(titulo="Livro completo", autores=[m.Pessoa(nome="Autora")], idioma="pt-BR"),
                   capitulos=[cap1, cap2], recursos=recursos,
                   pagina=m.FormatoDePagina(largura_mm=140, altura_mm=210, margens_mm=(15, 12, 18, 20),
                                            espelhadas=True, hifenizar=True))
