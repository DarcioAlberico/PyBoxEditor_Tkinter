"""
Testes de `core/editor/sumario.py` (ED-00; SPEC_EDITOR §9 "Table of Contents", §10.1,
AC-ED00-11): gerar dos títulos com níveis, `nav.xhtml` com `toc`, `landmarks` e
`page-list`, `toc.ncx` com `dtb:uid`, ida e volta dos dois, a página de sumário visível
e os caminhos relativos ao arquivo do nav.

Rodar sem pytest:      python tests/test_editor_sumario.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.editor import modelo as m, sumario, xhtml


def _livro(nav="nav.xhtml", ncx="toc.ncx"):
    livro = m.Livro(metadados=m.Metadados(titulo="Livro", identificador="urn:uuid:1", idioma="pt"),
                    nav=nav, ncx=ncx, folhas=["Styles/estilo.css"])
    for i in range(3):
        cap = m.Capitulo(arquivo=f"Text/cap-{i:04d}.xhtml", blocos=[
            m.Titulo(trechos=[m.Trecho(texto=f"Capítulo {i}")], nivel=1, id=f"c{i}"),
            m.Paragrafo(trechos=[m.Trecho(texto="x")]),
            m.Titulo(trechos=[m.Trecho(texto=f"Seção {i}")], nivel=2),
            m.Titulo(trechos=[m.Trecho(texto="Sub")], nivel=3),
            m.MarcaDePagina(pagina=10 + i),
            m.Paragrafo(trechos=[m.Trecho(texto="y", pagina=20 + i)]),
        ])
        livro.capitulos.append(cap)
    livro.marcos = [("bodymatter", "Text/cap-0000.xhtml"), ("toc", "Text/cap-0000.xhtml#c0")]
    return livro


def test_gerar_dos_titulos_aninha_pelo_nivel_e_so_nos_niveis_pedidos():
    livro = _livro()
    livro.sumario = sumario.gerar_dos_titulos(livro, (1, 2))
    assert [e.rotulo for e in livro.sumario] == ["Capítulo 0", "Capítulo 1", "Capítulo 2"]
    assert [f.rotulo for f in livro.sumario[0].filhos] == ["Seção 0"]
    assert livro.sumario[0].destino == "Text/cap-0000.xhtml#c0"
    assert livro.sumario[0].filhos[0].filhos == []          # o nível 3 ficou de fora
    so_nivel_3 = sumario.gerar_dos_titulos(livro, (3,))
    assert [e.rotulo for e in so_nivel_3] == ["Sub", "Sub", "Sub"]


def test_sem_titulo_nos_niveis_uma_entrada_por_capitulo():
    livro = _livro()
    entradas = sumario.gerar_dos_titulos(livro, (5,))
    assert [e.destino for e in entradas] == [c.arquivo for c in livro.capitulos]
    assert entradas[0].rotulo == "Capítulo 0"      # titulo_efetivo = o primeiro título


def test_nav_com_toc_landmarks_e_page_list_e_a_volta():
    livro = _livro()
    livro.sumario = sumario.gerar_dos_titulos(livro, (1, 2))
    nav = sumario.escrever_nav(livro)
    assert xhtml.bem_formado(nav) is None
    assert 'epub:type="toc"' in nav and 'epub:type="landmarks"' in nav and 'epub:type="page-list"' in nav
    assert nav.count("<li>") == 6 + 2 + 6
    s, marcos, paginas = sumario.ler_nav(nav, livro.nav)
    assert m.para_dict(s) == m.para_dict(livro.sumario)
    assert marcos == livro.marcos
    assert paginas == [(10, "Text/cap-0000.xhtml#pg-10"), (20, "Text/cap-0000.xhtml#pg-20"),
                       (11, "Text/cap-0001.xhtml#pg-11"), (21, "Text/cap-0001.xhtml#pg-21"),
                       (12, "Text/cap-0002.xhtml#pg-12"), (22, "Text/cap-0002.xhtml#pg-22")]


def test_os_links_do_nav_sao_relativos_ao_arquivo_do_nav():
    livro = _livro(nav="Text/nav.xhtml")
    livro.sumario = sumario.gerar_dos_titulos(livro, (1,))
    nav = sumario.escrever_nav(livro)
    assert 'href="cap-0000.xhtml#c0"' in nav
    s, _, _ = sumario.ler_nav(nav, "Text/nav.xhtml")
    assert s[0].destino == "Text/cap-0000.xhtml#c0"
    raiz = _livro(nav="nav.xhtml")
    raiz.sumario = sumario.gerar_dos_titulos(raiz, (1,))
    assert 'href="Text/cap-0000.xhtml#c0"' in sumario.escrever_nav(raiz)


def test_ncx_com_dtb_uid_e_a_volta():
    livro = _livro()
    livro.sumario = sumario.gerar_dos_titulos(livro, (1, 2))
    ncx = sumario.escrever_ncx(livro)
    assert xhtml.bem_formado(ncx) is None
    assert '<meta name="dtb:uid" content="urn:uuid:1"/>' in ncx
    assert '<meta name="dtb:depth" content="2"/>' in ncx
    assert ncx.count("<navPoint") == 6 and 'playOrder="6"' in ncx
    assert m.para_dict(sumario.ler_ncx(ncx, livro.ncx)) == m.para_dict(livro.sumario)


def test_pagina_de_sumario_visivel():
    livro = _livro()
    livro.sumario = sumario.gerar_dos_titulos(livro, (1, 2))
    pagina = sumario.pagina_de_sumario(livro)
    assert pagina.semantica == "toc" and pagina.folhas == ["Styles/estilo.css"]
    saida = xhtml.escrever(pagina)
    assert xhtml.bem_formado(saida) is None
    assert 'epub:type="toc"' in saida and saida.count("<li>") == 6
    assert 'href="cap-0000.xhtml#c0"' in saida        # relativo a Text/sumario.xhtml


def test_destinos_quebrados_e_renomear():
    livro = _livro()
    livro.sumario = sumario.gerar_dos_titulos(livro, (1,))
    livro.sumario.append(m.EntradaDeSumario(rotulo="órfã", destino="Text/nao.xhtml#z"))
    livro.sumario.append(m.EntradaDeSumario(rotulo="âncora", destino="Text/cap-0000.xhtml#zz"))
    assert sumario.destinos_quebrados(livro) == ["Text/nao.xhtml#z", "Text/cap-0000.xhtml#zz"]
    assert sumario.renomear_destinos(livro.sumario, "Text/cap-0000.xhtml", "Text/abertura.xhtml") == 2
    assert livro.sumario[0].destino == "Text/abertura.xhtml#c0"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
