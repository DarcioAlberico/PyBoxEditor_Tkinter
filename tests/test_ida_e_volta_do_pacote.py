"""Ida e volta sem perda silenciosa: o pacote (RG-10, R-26).

O OPF perdia `page-progression-direction` da espinha, `id` e `properties` do `itemref`,
`fallback` do `item`, `opf:scheme` do identificador e `xml:lang` dos `dc:*`; o `xml:lang` do
pacote virava o do `dc:language`; e o escritor renomeava os ids do manifesto (`c1` →
`c1.xhtml`), quebrando o `refines="#c1"`.
"""

import zipfile

from core.editor import epub

_OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" xmlns:opf="http://www.idpf.org/2007/opf" version="3.0"
         unique-identifier="uid" xml:lang="en" dir="ltr">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="uid" opf:scheme="ISBN">9780000000001</dc:identifier>
<dc:title id="t" xml:lang="en">The Package</dc:title>
<dc:language>pt</dc:language>
<meta property="dcterms:modified">2020-01-01T00:00:00Z</meta>
<meta refines="#c1" property="media:duration">0:00:10</meta>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="c1" href="Text/c1.xhtml" media-type="application/xhtml+xml"/>
<item id="figura-svg" href="Images/a.svg" media-type="image/svg+xml" fallback="figura-png"/>
<item id="figura-png" href="Images/a.png" media-type="image/png"/>
</manifest>
<spine page-progression-direction="rtl">
<itemref idref="c1" id="ir-1" properties="page-spread-right"/>
</spine>
</package>
"""

_NAV = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Nav</title></head>
<body><nav epub:type="toc"><ol><li><a href="Text/c1.xhtml">Um</a></li></ol></nav></body></html>
"""

_CAP = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Um</title></head><body><h1>Um</h1><p>Texto.</p></body></html>
"""


def _epub(tmp_path):
    caminho = str(tmp_path / "pacote.epub")
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:'
                   'container"><rootfiles><rootfile full-path="OEBPS/content.opf" '
                   'media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("OEBPS/content.opf", _OPF)
        z.writestr("OEBPS/nav.xhtml", _NAV)
        z.writestr("OEBPS/Text/c1.xhtml", _CAP)
        z.writestr("OEBPS/Images/a.svg", '<svg xmlns="http://www.w3.org/2000/svg"/>')
        z.writestr("OEBPS/Images/a.png", b"\x89PNG\r\n\x1a\n")
    return caminho


def _opf_gravado(tmp_path):
    livro, _ = epub.ler(_epub(tmp_path))
    saida = str(tmp_path / "volta.epub")
    epub.escrever(livro, saida)
    with zipfile.ZipFile(saida) as z:
        return z.read(next(n for n in z.namelist() if n.endswith(".opf"))).decode("utf-8"), saida


def test_os_atributos_do_pacote_da_espinha_e_do_manifesto_voltam(tmp_path):
    opf, _ = _opf_gravado(tmp_path)
    for trecho in ('page-progression-direction="rtl"', 'id="ir-1"', 'properties="page-spread-right"',
                   'fallback="figura-png"', 'opf:scheme="ISBN"', 'xml:lang="en">The Package</dc:title>',
                   'dir="ltr"'):
        assert trecho in opf, f"perdeu {trecho}"
    pacote = opf.split("<metadata")[0]
    assert 'xml:lang="en"' in pacote, "o xml:lang do pacote virou o do dc:language"
    assert ">pt</dc:language>" in opf


def test_os_ids_do_manifesto_ficam_e_o_refines_continua_valendo(tmp_path):
    opf, saida = _opf_gravado(tmp_path)
    assert '<item id="c1" href="Text/c1.xhtml"' in opf, "o id do manifesto foi renomeado"
    assert 'idref="c1"' in opf and 'refines="#c1"' in opf
    assert 'id="figura-svg"' in opf and 'id="figura-png"' in opf
    # E de novo: a segunda volta é igual à primeira.
    livro, _ = epub.ler(saida)
    segunda = str(tmp_path / "segunda.epub")
    epub.escrever(livro, segunda)
    with zipfile.ZipFile(segunda) as z:
        opf2 = z.read(next(n for n in z.namelist() if n.endswith(".opf"))).decode("utf-8")
    import re
    sem_data = lambda t: re.sub(r"<meta property=\"dcterms:modified\">[^<]*</meta>", "", t)  # noqa: E731
    assert sem_data(opf2) == sem_data(opf)
