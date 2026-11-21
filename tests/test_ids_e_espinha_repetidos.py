"""Livros de terceiros com ids e espinha repetidos (RG-11, R-28).

- A espinha com o mesmo `itemref` duas vezes abria e dava `ValueError: dois capítulos com
  o mesmo arquivo` ao salvar.
- Ids de bloco repetidos abriam e não salvavam (`id duplicado no capítulo`), e a busca
  trocava no primeiro bloco do id, não no certo.
- Juntar capítulos deduplicava a marca de página só por id: duas marcas da mesma página
  com ids diferentes ficavam as duas.
"""

import zipfile

from tests.test_ida_e_volta_do_pacote import _CAP, _NAV, _OPF

from core.editor import epub, livro_ops, modelo as m, xhtml


def _epub(tmp_path, opf=_OPF, capitulo=_CAP):
    caminho = str(tmp_path / "repetidos.epub")
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:'
                   'container"><rootfiles><rootfile full-path="OEBPS/content.opf" '
                   'media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", _NAV)
        z.writestr("OEBPS/Text/c1.xhtml", capitulo)
        z.writestr("OEBPS/Images/a.svg", '<svg xmlns="http://www.w3.org/2000/svg"/>')
        z.writestr("OEBPS/Images/a.png", b"\x89PNG\r\n\x1a\n")
    return caminho


def test_a_espinha_repetida_abre_salva_e_avisa(tmp_path):
    opf = _OPF.replace('<itemref idref="c1" id="ir-1" properties="page-spread-right"/>',
                       '<itemref idref="c1"/><itemref idref="c1"/>')
    livro, relatorio = epub.ler(_epub(tmp_path, opf=opf))
    assert [c.arquivo for c in livro.capitulos] == ["Text/c1.xhtml"]
    assert any("repete" in a and "c1" in a for a in relatorio.avisos)
    epub.escrever(livro, str(tmp_path / "salvo.epub"))          # não levanta mais


def test_ids_repetidos_sao_renumerados_e_o_livro_salva(tmp_path):
    capitulo = _CAP.replace("<p>Texto.</p>", '<p id="x">Primeiro.</p><p id="x">Segundo.</p><ol><li id="x">Item.</li></ol>')
    livro, relatorio = epub.ler(_epub(tmp_path, capitulo=capitulo))
    cap = livro.capitulos[0]
    ids = [b.id for b in m.blocos_do_capitulo(cap) if isinstance(b, m.Paragrafo) and b.id.startswith("x")]
    assert ids == ["x", "x-2"], ids
    itens = [i for b in cap.blocos if isinstance(b, m.Lista) for i in b.itens]
    assert itens[0].extras["id"] == "x-3", "o id do item de lista colidia com os dos blocos"
    assert any("x" in a and "repetido" in a for a in relatorio.avisos + cap.avisos)
    epub.escrever(livro, str(tmp_path / "salvo.epub"))
    # E a troca acha o bloco certo: o segundo, pelo id dele.
    assert m.texto_de(cap.bloco("x-2")) == "Segundo."


def test_juntar_deduplica_a_marca_de_pagina_pelo_numero():
    livro = epub.novo_livro("Marcas")
    a = livro.capitulos[0]
    a.blocos.append(m.MarcaDePagina(pagina=27, id="pg-27"))
    b = m.Capitulo(arquivo="Text/cap-0002.xhtml", folhas=list(a.folhas),
                   blocos=[m.MarcaDePagina(pagina=27, id="pagina-27-copia"), m.Paragrafo(trechos=[m.Trecho(texto="x")])])
    livro.capitulos.append(b)
    livro_ops.juntar(livro, b.arquivo)
    marcas = [bl for bl in livro.capitulos[0].blocos if isinstance(bl, m.MarcaDePagina)]
    assert [mk.pagina for mk in marcas] == [27], "a marca da mesma página ficou duas vezes"


def test_o_leitor_de_xhtml_sozinho_tambem_deduplica():
    cap = xhtml.ler(_CAP.replace("<p>Texto.</p>", '<p id="y">a</p><p id="y">b</p>'), "Text/c.xhtml")
    assert len({b.id for b in m.blocos_do_capitulo(cap)}) == len(m.blocos_do_capitulo(cap))
