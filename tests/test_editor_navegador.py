"""
Testes de `ui/editor/navegador.py` (ED-08; SPEC_EDITOR §9 "Book Browser"): a árvore por
grupos com a capa, a folha padrão e a semântica marcadas; o menu de contexto com toda
ação (cada uma com item na barra); renomear pelo navegador atualiza tudo (AC-ED08-1);
`Delete`/`F2`/`Espaço`; arrastar reordena a espinha; e a seleção que sobrevive à
atualização.

Rodar sem pytest:      python tests/test_editor_navegador.py
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import modelo as m
from editor_ambiente import Janela
from ui.editor import menus
from ui.editor.navegador import CONTEXTO, GRUPOS


def test_a_arvore_mostra_os_grupos_a_capa_a_folha_padrao_e_a_semantica():
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        nav = j.painel_navegador
        assert [g.split(":")[1] for g in j.navegador.get_children()] == list(GRUPOS)
        assert nav.capitulos_visiveis() == ["cap1.xhtml", "cap2.xhtml"]
        assert "Capítulo um" in j.navegador.item("cap1.xhtml", "text")
        livro.recursos["Styles/e.css"] = m.Recurso(caminho="Styles/e.css", tipo_mime="text/css", dados=b"p{}")
        livro.folhas = ["Styles/e.css"]
        livro.metadados.capa = "Images/foto.png"
        livro.capitulos[1].semantica = "bodymatter"
        j.navegador.focus("cap2.xhtml")
        j.atualizar_navegador()
        assert "(padrão)" in j.navegador.item("Styles/e.css", "text")
        assert "(capa)" in j.navegador.item("Images/foto.png", "text")
        assert "[bodymatter]" in j.navegador.item("cap2.xhtml", "text")
        assert nav.selecionado() == "cap2.xhtml"          # a seleção sobrevive à atualização
        assert nav.selecionar("Images/foto.png") and nav.selecionado() == "Images/foto.png"
        assert not nav.selecionar("nada.png")
        j.navegador.focus("grupo:Texto")
        assert nav.selecionado() is None
        # o OPF e o nav aparecem em Outros e abrem só para leitura
        assert j.navegador.exists(livro.opf) and j.navegador.parent(livro.opf) == "grupo:Outros"
        nav.selecionar(livro.opf)
        assert j._abrir_do_navegador().somente_leitura


def test_o_menu_de_contexto_tem_toda_acao_e_cada_uma_tem_item_na_barra():
    with Janela() as t:
        j = t.j
        nav = j.painel_navegador
        for nome in CONTEXTO:
            if nome == "semantica_do_capitulo":
                assert any(i.rotulo == "Semântica do capítulo" for i in menus.LIVRO)     # o submenu da barra
            elif nome != "-":
                assert menus.item_de(nome) is not None, nome
        nav.selecionar("cap1.xhtml")
        menu = nav.menu_de_contexto()
        rotulos = [menu.entrycget(k, "label") for k in range(menu.index("end") + 1) if menu.type(k) != "separator"]
        assert rotulos[0] == "Abrir" and "Renomear…" in rotulos and "Semântica do capítulo" in rotulos
        assert "Marcar arquivo para a busca" in rotulos and "Abrir com…" in rotulos
        k = rotulos.index("Renomear…")
        indice = [i for i in range(menu.index("end") + 1) if menu.type(i) != "separator"][k]
        assert str(menu.entrycget(indice, "state")) == "normal"
        # sem nada escolhido, o que precisa de alvo fica desabilitado
        j.navegador.focus("grupo:Texto")
        j.navegador.selection_set("grupo:Texto")
        menu = nav.menu_de_contexto()
        indice = [i for i in range(menu.index("end") + 1) if menu.type(i) != "separator"][k]
        assert str(menu.entrycget(indice, "state")) == "disabled"


def test_ac1_renomear_pelo_navegador_atualiza_links_sumario_abas_e_arvore():
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        aba1 = j.abrir_capitulo("cap1.xhtml")
        j.abrir_capitulo("cap2.xhtml")
        j.painel_navegador.selecionar("cap2.xhtml")
        novo = j.executar("renomear", "Text/dois.xhtml")
        assert novo == "Text/dois.xhtml" and livro.capitulo("Text/dois.xhtml") is not None
        # o link do cap1 para cap2#alvo foi reescrito, o sumário também, a aba mudou de nome
        cap1 = aba1.widget.sincronizar()
        links = [tr.link for b in cap1.blocos if isinstance(b, m.Paragrafo) for tr in b.trechos if tr.link]
        assert "Text/dois.xhtml#alvo" in links and "cap2.xhtml#alvo" not in links
        assert any(e.destino.startswith("Text/dois.xhtml") for e in livro.sumario)
        assert j.abas.por_arquivo("Text/dois.xhtml") is not None and j.abas.por_arquivo("cap2.xhtml") is None
        assert j.navegador.exists("Text/dois.xhtml") and j.painel_navegador.selecionado() == "Text/dois.xhtml"
        assert j.projeto.sujo and "referência(s) reescrita(s)" in j.campos["aviso"].cget("text")
        # nome só (sem pasta) fica na pasta de origem; nome repetido e o nav são erros de entrada
        assert j.executar("renomear", "tres.xhtml", "Text/dois.xhtml") == "Text/tres.xhtml"
        j.executar("renomear", "Text/tres.xhtml", "cap1.xhtml")
        assert "já existe" in t.caixas.entradas()[-1]
        j.executar("renomear", "x.xhtml", livro.nav)
        assert "regenerado" in t.caixas.entradas()[-1]
        # renomear vários
        mapa = j.executar("renomear_varios", "cap-%03d")
        assert mapa == {"cap1.xhtml": "cap-001.xhtml", "Text/tres.xhtml": "Text/cap-002.xhtml"}
        assert [a.arquivo for a in j.abas.abas] == ["cap-001.xhtml", "Text/cap-002.xhtml"]
        assert [c.arquivo for c in livro.capitulos] == ["cap-001.xhtml", "Text/cap-002.xhtml"]


def test_delete_f2_espaco_e_arrastar():
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        nav = j.painel_navegador
        chamados = []
        for nome in ("excluir", "renomear", "marcar_arquivo"):
            j.comandos[nome] = (lambda n=nome: chamados.append(n))
        nav.selecionar("cap2.xhtml")
        # (uma janela `withdraw`n não recebe tecla por `event_generate`: as ligações existem, e os handlers
        # vão por comando)
        ligadas = set(nav.arvore.bind())
        assert {"<Key-Delete>", "<Key-F2>", "<Key-space>"} <= ligadas
        for nome in ("excluir", "renomear", "marcar_arquivo"):
            assert nav._executar(nome) == "break"
        assert chamados == ["excluir", "renomear", "marcar_arquivo"]
        # arrastar cap2 para cima de cap1 reordena a espinha
        nav._arrastando = "cap2.xhtml"
        nav.arvore.move("cap2.xhtml", "grupo:Texto", 0)
        nav._solta(SimpleNamespace())
        assert [c.arquivo for c in livro.capitulos] == ["cap2.xhtml", "cap1.xhtml"] and j.projeto.sujo
        assert nav.capitulos_visiveis() == ["cap2.xhtml", "cap1.xhtml"]
        assert j.executar("ordenar_por_nome") == ["cap1.xhtml", "cap2.xhtml"]
        assert j.executar("mover_para_baixo") is not None
        nav.selecionar("cap1.xhtml")
        assert j.executar("mover_para_baixo") == 1 and [c.arquivo for c in livro.capitulos] == ["cap2.xhtml",
                                                                                                 "cap1.xhtml"]
        assert j.executar("mover_para_baixo") == 1 and "último" in j.campos["aviso"].cget("text")
        assert j.executar("mover_para_cima") == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
