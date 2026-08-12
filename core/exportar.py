"""
EPUB e DOCX a partir do que o `livro` extraiu (F2.6).

Os dois formatos saem do **mesmo intermediário** — a lista de `PaginaExtraida`
—, e é de propósito: o trabalho difícil é ler a página, não escrever o arquivo.
Trocar de formato aqui custa uma função; trocar a extração custaria o módulo
inteiro.

**EPUB sai com a biblioteca padrão.** Um EPUB é um zip com XHTML dentro, e
escrevê-lo à mão são cem linhas — contra uma dependência a mais no
`requirements.txt`, que este projeto recusa quando não precisa (ver a nota do
`pyspellchecker` no ROADMAP). O DOCX é o contrário: o OOXML tem relacionamento,
tipo de conteúdo e parte de mídia para cada imagem, e errar um detalhe dá um
arquivo que o Word recusa abrir sem dizer por quê. Ali a dependência
(`python-docx`) paga.
"""

import html
import os
import zipfile
from typing import List, Optional, Sequence

from core.livro import Figura, PaginaExtraida, Paragrafo


CSS = """\
body { font-family: serif; line-height: 1.45; margin: 0 6%; }
p { margin: 0 0 0.35em; text-indent: 1.2em; text-align: justify; }
p.primeira { text-indent: 0; }
figure { margin: 1.2em 0; text-align: center; page-break-inside: avoid; }
img { max-width: 88%; height: auto; }
hr.pagina { border: 0; border-top: 1px solid #ccc; margin: 1.6em 0 1em; }
"""

_CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def _xhtml_da_pagina(pagina: PaginaExtraida, imagens: Sequence[str]) -> str:
    corpo, i = [], 0
    primeiro = True
    for bloco in pagina.blocos:
        if isinstance(bloco, Figura):
            corpo.append(f'<figure><img src="{imagens[i]}" alt="Diagrama"/></figure>')
            i += 1
            primeiro = True
        else:
            classe = ' class="primeira"' if primeiro else ""
            corpo.append(f"<p{classe}>{html.escape(bloco.texto)}</p>")
            primeiro = False
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="pt">\n'
        f"<head><title>Página {pagina.numero + 1}</title>"
        '<link rel="stylesheet" type="text/css" href="estilo.css"/></head>\n'
        "<body>\n" + "\n".join(corpo) + "\n</body>\n</html>\n"
    )


def para_epub(paginas: Sequence[PaginaExtraida], caminho: str, *,
              titulo: str = "Livro", autor: str = "",
              identificador: str = "pyboxeditor") -> str:
    """
    Escreve o EPUB. Devolve o caminho.

    O `mimetype` vai **primeiro e sem compressão**, que é a única exigência
    posicional do formato: leitor que valide o arquivo procura a assinatura nos
    primeiros bytes, e um zip que comprima essa entrada é recusado.
    """
    arquivos, imagens_por_pagina = [], []
    for pagina in paginas:
        nomes = []
        for j, bloco in enumerate(b for b in pagina.blocos if isinstance(b, Figura)):
            nome = f"imagens/fig-{pagina.numero + 1:04d}-{j + 1}.png"
            arquivos.append((f"OEBPS/{nome}", bloco.png))
            nomes.append(nome)
        imagens_por_pagina.append(nomes)

    capitulos = []
    for pagina, imagens in zip(paginas, imagens_por_pagina):
        nome = f"pagina-{pagina.numero + 1:04d}.xhtml"
        capitulos.append(nome)
        arquivos.append((f"OEBPS/{nome}",
                         _xhtml_da_pagina(pagina, imagens).encode("utf-8")))

    itens = [f'<item id="c{i}" href="{n}" media-type="application/xhtml+xml"/>'
             for i, n in enumerate(capitulos)]
    itens += [f'<item id="img{i}" href="{n[len("OEBPS/"):]}" media-type="image/png"/>'
              for i, (n, _d) in enumerate(arquivos) if n.endswith(".png")]
    itens.append('<item id="css" href="estilo.css" media-type="text/css"/>')
    itens.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
                 'properties="nav"/>')
    espinha = "".join(f'<itemref idref="c{i}"/>' for i in range(len(capitulos)))

    opf = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="pub-id">\n'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        f'<dc:identifier id="pub-id">{html.escape(identificador)}</dc:identifier>\n'
        f"<dc:title>{html.escape(titulo)}</dc:title>\n"
        '<dc:language>pt</dc:language>\n'
        + (f"<dc:creator>{html.escape(autor)}</dc:creator>\n" if autor else "")
        + '<meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>\n'
        "</metadata>\n<manifest>\n" + "\n".join(itens) + "\n</manifest>\n"
        f"<spine>{espinha}</spine>\n</package>\n"
    )

    nav = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
           '<html xmlns="http://www.w3.org/1999/xhtml" '
           'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Sumário</title>'
           "</head><body><nav epub:type=\"toc\"><h1>Sumário</h1><ol>"
           + "".join(f'<li><a href="{n}">Página {i + 1}</a></li>'
                     for i, n in enumerate(capitulos))
           + "</ol></nav></body></html>\n")

    pasta = os.path.dirname(os.path.abspath(caminho))
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                   compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", _CONTAINER)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav)
        z.writestr("OEBPS/estilo.css", CSS)
        for nome, dados in arquivos:
            z.writestr(nome, dados)
    return caminho


def para_docx(paginas: Sequence[PaginaExtraida], caminho: str, *,
              titulo: str = "Livro", autor: str = "",
              largura_figura_cm: float = 9.0) -> str:
    """
    Escreve o DOCX. Devolve o caminho.

    A figura entra com largura fixa em centímetros, e não no tamanho em pixels:
    o recorte sai a 300 dpi e teria 700 px de largura, que o Word põe como 700
    pontos e estoura a página.
    """
    import io as _io
    from docx import Document
    from docx.shared import Cm

    doc = Document()
    doc.core_properties.title = titulo
    if autor:
        doc.core_properties.author = autor

    for i, pagina in enumerate(paginas):
        if i:
            doc.add_page_break()
        for bloco in pagina.blocos:
            if isinstance(bloco, Figura):
                doc.add_picture(_io.BytesIO(bloco.png), width=Cm(largura_figura_cm))
                doc.paragraphs[-1].alignment = 1   # centralizado
            else:
                doc.add_paragraph(bloco.texto)

    pasta = os.path.dirname(os.path.abspath(caminho))
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    doc.save(caminho)
    return caminho


FORMATOS = {"epub": para_epub, "docx": para_docx}


def exportar(paginas: Sequence[PaginaExtraida], caminho: str, *,
             formato: Optional[str] = None, **kw) -> str:
    """Escreve no formato pedido, ou no que a extensão do caminho indicar."""
    if formato is None:
        formato = os.path.splitext(caminho)[1].lstrip(".").lower()
    if formato not in FORMATOS:
        raise ValueError(f"formato inválido: {formato!r} "
                         f"(use um de {tuple(FORMATOS)})")
    return FORMATOS[formato](paginas, caminho, **kw)
