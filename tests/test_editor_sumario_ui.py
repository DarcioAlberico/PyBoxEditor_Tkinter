"""
Testes do painel e do editor de sumário (ED-08; SPEC_EDITOR §9 "TOC"): gerar 1–2 → nav
com árvore e `page-list`; editar e reordenar; NCX coerente; "Sumário como página" cria
`Text/sumario.xhtml` com `epub:type="toc"` (AC-ED08-2); o editor sem mostrar (renomear,
subir, descer, níveis, remover, acrescentar); o painel leva ao destino; "Gravar" refaz o
nav; a semântica e os marcos gravados são lidos de volta do nav (parte do AC-ED08-1).

Rodar sem pytest:      python tests/test_editor_sumario_ui.py
"""

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import epub, modelo as m, sumario
from core.editor.modelo import EntradaDeSumario
from editor_ambiente import Janela
from ui.editor.sumario import EditorDeSumario


def _e(rotulo, destino, filhos=()):
    return EntradaDeSumario(rotulo=rotulo, destino=destino, filhos=list(filhos))


def test_o_editor_de_sumario_renomeia_move_muda_nivel_remove_acrescenta_e_gera():
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        entradas = [_e("Um", "cap1.xhtml#cap1-t", [_e("Um.a", "cap1.xhtml#a"), _e("Um.b", "cap1.xhtml#b")]),
                    _e("Dois", "cap2.xhtml"), _e("Três", "cap2.xhtml#alvo")]
        caixa = EditorDeSumario(j, entradas, livro)
        caixa.construir()
        # trabalha numa cópia: o original não muda
        um = caixa.entradas[0]
        caixa.renomear("Um!", um)
        assert entradas[0].rotulo == "Um" and caixa.entradas[0].rotulo == "Um!"
        # descer/subir
        assert caixa.descer(um) and [e.rotulo for e in caixa.entradas] == ["Dois", "Um!", "Três"]
        assert caixa.subir(um) and [e.rotulo for e in caixa.entradas] == ["Um!", "Dois", "Três"]
        assert not caixa.subir(um)
        # aumentar nível: "Dois" vira filho de "Um!"; diminuir: volta, levando as irmãs seguintes como filhas
        dois = caixa.entradas[1]
        assert caixa.aumentar_nivel(dois) and [e.rotulo for e in um.filhos] == ["Um.a", "Um.b", "Dois"]
        assert caixa.diminuir_nivel(um.filhos[0]) and [e.rotulo for e in caixa.entradas] == ["Um!", "Um.a", "Três"]
        assert [e.rotulo for e in caixa.entradas[1].filhos] == ["Um.b", "Dois"]
        assert not caixa.diminuir_nivel(caixa.entradas[0])
        # remover sobe os filhos; acrescentar entra depois da escolhida
        assert caixa.remover(caixa.entradas[1]) and [e.rotulo for e in caixa.entradas] == ["Um!", "Um.b", "Dois",
                                                                                            "Três"]
        nova = caixa.acrescentar("Quatro", "cap2.xhtml#alvo", depois_de=caixa.entradas[-1])
        assert caixa.entradas[-1] is nova and caixa.escolhida() is nova
        with pytest.raises(ValueError):
            caixa.acrescentar("", "x")
        # gerar dos títulos 1–2
        geradas = caixa.gerar((1, 2))
        assert [e.rotulo for e in geradas] == ["Capítulo um", "Capítulo dois"]
        assert [e.rotulo for e in geradas[0].filhos] == ["Título 2"] and geradas[1].filhos[0].rotulo == "Seção"
        assert caixa.confirmar() == geradas


def test_ac2_gerar_editar_gravar_e_o_nav_com_arvore_page_list_e_ncx_coerente():
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        livro.ncx = "toc.ncx"
        gerado = j.executar("sumario_gerar", (1, 2))
        assert [e.rotulo for e in gerado] == ["Capítulo um", "Capítulo dois"] and j.projeto.sujo
        assert j.arvore_do_sumario.item("s0", "text") == "Capítulo um" and j.arvore_do_sumario.exists("s0.0")
        # editar pela caixa (resposta injetada): reordena
        j.caixas.sumario = lambda entradas, livro=None, destino="": [entradas[1], entradas[0]]
        editado = j.executar("sumario_editar")
        assert [e.rotulo for e in editado] == ["Capítulo dois", "Capítulo um"]
        assert j.arvore_do_sumario.item("s0", "text") == "Capítulo dois"
        # gravar refaz o nav (a aba de leitura acompanha)
        aba_nav = j.abrir_leitura(livro.nav)
        texto = j.executar("sumario_gravar")
        assert 'epub:type="toc"' in texto and 'epub:type="page-list"' in texto and "Capítulo dois" in texto
        assert "Capítulo dois" in aba_nav.widget.texto_todo()
        # salvar: nav e NCX coerentes, page-list com as 13 páginas do livro completo
        j.executar("salvar")
        with zipfile.ZipFile(t.epub) as z:
            nav = z.read(epub.nome_no_zip(livro, livro.nav)).decode("utf-8")
            ncx = z.read(epub.nome_no_zip(livro, livro.ncx)).decode("utf-8")
        assert nav.index("Capítulo dois") < nav.index("Capítulo um") and nav.count("<li>") >= 13 + 4
        assert ncx.index("Capítulo dois") < ncx.index("Capítulo um") and ncx.count("<navPoint") == 4
        sum_nav, _marcos, paginas = sumario.ler_nav(nav, livro.nav)
        assert [e.rotulo for e in sum_nav] == ["Capítulo dois", "Capítulo um"] and len(paginas) == 13
        assert [e.rotulo for e in sumario.ler_ncx(ncx, livro.ncx)] == ["Capítulo dois", "Capítulo um"]


def test_ac2_sumario_como_pagina_cria_o_xhtml_com_toc_e_o_painel_leva_ao_destino():
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        arquivo = j.executar("sumario_como_pagina")
        assert arquivo == "Text/sumario.xhtml"     # a pasta de texto padrão, como a capa
        cap = livro.capitulo(arquivo)
        assert cap is not None and cap.semantica == "toc" and livro.capitulos[0] is cap
        assert ("toc", arquivo) in livro.marcos and j.aba_ativa().arquivo == arquivo
        assert isinstance(cap.blocos[1], m.Lista) and cap.blocos[1].itens[0].paragrafos[0].trechos[0].link
        # de novo: reescreve o mesmo arquivo
        assert j.executar("sumario_como_pagina") == arquivo and [c.arquivo for c in livro.capitulos].count(
            arquivo) == 1
        j.executar("salvar")
        relido, _rel = epub.ler(t.epub)
        assert relido.capitulo(arquivo).semantica == "toc" and ("toc", arquivo) in relido.marcos
        with zipfile.ZipFile(t.epub) as z:
            xhtml = z.read(epub.nome_no_zip(relido, arquivo)).decode("utf-8")
        assert 'epub:type="toc"' in xhtml
        # o painel Sumário leva ao destino
        j.arvore_do_sumario.focus("s0")
        aba = j._ir_pelo_sumario()
        assert aba.arquivo == livro.sumario[0].destino.partition("#")[0]
        assert j.executar("ir_para_destino", "cap2.xhtml#alvo").arquivo == "cap2.xhtml"
        assert j.painel_sumario.menu_de_contexto() is not None


def test_ac1_semantica_e_marcos_gravados_sao_lidos_do_nav():
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        j.navegador.focus("cap2.xhtml")
        assert j.executar("semantica", "bodymatter") == "bodymatter"
        assert livro.capitulo("cap2.xhtml").semantica == "bodymatter" and ("bodymatter", "cap2.xhtml") in livro.marcos
        assert "[bodymatter]" in j.navegador.item("cap2.xhtml", "text")
        # a mesma semântica de novo desliga; uma única (toc) sai do outro capítulo ao entrar neste
        assert j.executar("semantica", "bodymatter") == "" and ("bodymatter", "cap2.xhtml") not in livro.marcos
        j.executar("semantica", "toc", "cap1.xhtml")
        j.executar("semantica", "toc", "cap2.xhtml")
        assert livro.capitulo("cap1.xhtml").semantica == "" and livro.capitulo("cap2.xhtml").semantica == "toc"
        assert [d for tp, d in livro.marcos if tp == "toc"] == ["cap2.xhtml"]
        # o submenu dinâmico marca a atual
        itens = j.itens_dinamicos["semantica"]()
        assert any(r.startswith("✓ ") and "Sumário" in r for r, _a in itens)
        # marcos pela caixa (resposta injetada)
        j.caixas.marcos = lambda marcos, tipos, destinos: [("bodymatter", "cap1.xhtml#cap1-t"), ("toc", "cap2.xhtml")]
        assert j.executar("marcos") == [("bodymatter", "cap1.xhtml#cap1-t"), ("toc", "cap2.xhtml")]
        j.caixas.marcos = lambda marcos, tipos, destinos: [("cover", "nada.xhtml")]
        j.executar("marcos")
        assert "não existe" in t.caixas.entradas()[-1]
        j.executar("salvar")
        relido, _rel = epub.ler(t.epub)
        assert relido.capitulo("cap2.xhtml").semantica == "toc"
        assert set(relido.marcos) == {("bodymatter", "cap1.xhtml#cap1-t"), ("toc", "cap2.xhtml")}
        with zipfile.ZipFile(t.epub) as z:
            nav = z.read(epub.nome_no_zip(relido, relido.nav)).decode("utf-8")
        assert 'epub:type="landmarks"' in nav and 'epub:type="bodymatter"' in nav


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
