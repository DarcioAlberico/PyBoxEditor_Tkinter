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
