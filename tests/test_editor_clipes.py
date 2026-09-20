"""
Testes de `core/editor/clipes.py` e `ui/editor/clipes.py` (ED-07; SPEC_EDITOR §9
"Clips"): o `\\1` e os grupos do padrão, o cursor onde o `\\1` estava, a coleção
(grupos, ordem, nomes únicos), a persistência em `Settings` e em JSON (AC-ED07-5), e
a barra que aplica o clipe ao editor.

Rodar sem pytest:      python tests/test_editor_clipes.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from config.settings import Settings
from conftest import raiz_tk
from core.editor import clipes as m


def test_ac5_o_clipe_troca_o_1_pela_selecao_e_o_cursor_fica_onde_ele_estava():
    c = m.Clipe(nome="Lance", texto='<span class="lance">\\1</span>')
    assert c.aplicar("23.Rxe4") == ('<span class="lance">23.Rxe4</span>', 34)
    assert c.aplicar("") == ('<span class="lance"></span>', 20)         # o cursor no meio, para digitar
    assert m.Clipe(nome="b", texto="<br/>").aplicar("x") == ("<br/>", 5)
    assert m.Clipe(nome="z", texto="\\0|\\1").aplicar("s") == ("s|s", 3)
    # Grupos de um padrão: \2… são os grupos casados contra a seleção.
    d = m.Clipe(nome="Sep", texto='<span class="n">\\2</span> <span class="l">\\3</span>', padrao=r"(\d+\.+)\s*(\S+)")
    assert d.aplicar("23... Rxe4") == ('<span class="n">23...</span> <span class="l">Rxe4</span>', 56)
    assert d.aplicar("nada") == ('<span class="n"></span> <span class="l"></span>', 47)
    with pytest.raises(ValueError):
        m.Clipe(nome="ruim", texto="x", padrao="(")
    with pytest.raises(ValueError):
        m.Clipe(nome="  ", texto="x")


def test_a_colecao_tem_grupos_ordem_e_nomes_unicos_por_grupo():
    c = m.Clipes()
    c.adicionar(m.Clipe(nome="A", texto="a"))
    c.adicionar(m.Clipe(nome="B", texto="b", grupo="Xadrez"))
    c.adicionar(m.Clipe(nome="A", texto="a2", grupo="Xadrez"))          # o mesmo nome noutro grupo: pode
    with pytest.raises(ValueError):
        c.adicionar(m.Clipe(nome="A", texto="a3"))
    assert c.grupos() == ["Geral", "Xadrez"] and [x.nome for x in c.do_grupo("Xadrez")] == ["B", "A"]
    assert c.por_nome("A").texto == "a" and c.por_nome("A", "Xadrez").texto == "a2"
    c.renomear("B", "C", "Xadrez")
    assert c.por_nome("C", "Xadrez") is not None
    with pytest.raises(ValueError):
        c.renomear("C", "A", "Xadrez")
    c.mover("C", 0, "Xadrez")
    assert [x.nome for x in c][0] == "C"
    assert c.remover("C", "Xadrez").texto == "b" and len(c) == 2
    with pytest.raises(KeyError):
        c.remover("nada")
    padrao = m.Clipes.padrao()
    assert len(padrao) == len(m.CLIPES_DE_FABRICA) and padrao.grupos()[0] == "Geral"


def test_ac5_persistencia_em_settings_e_em_json(tmp_path):
    settings = Settings(path=str(tmp_path / "settings.json"))
    c = m.Clipes.carregar(settings)                                       # sem nada gravado: os de fábrica
    assert c.por_nome("Negrito") is not None
    c.adicionar(m.Clipe(nome="Meu", texto="<q>\\1</q>", grupo="Meus", padrao="", atalho="Ctrl+Shift+1"))
    c.salvar(settings)
    gravado = json.load(open(settings.path, encoding="utf-8"))
    assert any(item["nome"] == "Meu" and item["atalho"] == "Ctrl+Shift+1" for item in gravado["editor"]["clipes"])
    de_novo = m.Clipes.carregar(settings)
    assert de_novo.por_nome("Meu", "Meus").texto == "<q>\\1</q>" and len(de_novo) == len(c)
    # Uma lista vazia gravada é "nenhum clipe", não "os de fábrica".
    m.Clipes().salvar(settings)
    assert len(m.Clipes.carregar(settings)) == 0
    # Exportar e importar.
    caminho = str(tmp_path / "clipes.json")
    c.exportar(caminho)
    outro = m.Clipes()
    assert outro.importar(caminho) == len(c)
    assert outro.importar(caminho) == 0                                    # repetidos ficam de fora
    outro.por_nome("Meu", "Meus").texto = "velho"
    assert outro.importar(caminho, substituir=True) == len(c) and outro.por_nome("Meu", "Meus").texto == "<q>\\1</q>"
    # Entradas estragadas no JSON não derrubam as boas.
    assert len(m.Clipes.de_lista([{"nome": "ok", "texto": "x"}, {"texto": "sem nome"}, "lixo",
                                  {"nome": "ruim", "texto": "y", "padrao": "("}])) == 1


def test_a_barra_mostra_o_grupo_e_aplica_o_clipe_no_editor():
    from ui.editor.clipes import BarraDeClipes
    from ui.editor.codigo import EditorDeCodigo
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        editor = EditorDeCodigo(raiz, "xhtml")
        editor.pack()
        editor.carregar("23.Rxe4")
        colecao = m.Clipes.padrao()
        barra = BarraDeClipes(raiz, colecao, editor.aplicar_clipe)
        barra.pack()
        assert barra.grupo == "Geral" and [b.cget("text") for b in barra.botoes][:2] == ["Negrito", "Itálico"]
        barra.escolher_grupo("Xadrez")
        assert [b.cget("text") for b in barra.botoes][0] == "Lance"
        editor.texto.tag_add("sel", "1.0", "1.7")
        barra.botoes[0].invoke()
        assert editor.texto_todo() == '<span class="lance">23.Rxe4</span>'
        editor.carregar("")
        assert barra.aplicar_por_nome("Negrito") == "<strong></strong>" and editor.posicao == (1, 9)
        colecao.adicionar(m.Clipe(nome="Novo", texto="n", grupo="Xadrez"))
        barra.atualizar()
        assert [b.cget("text") for b in barra.botoes][-1] == "Novo"
        with pytest.raises(ValueError):
            barra.escolher_grupo("nada")
        with pytest.raises(KeyError):
            barra.aplicar_por_nome("nada")
    finally:
        raiz.destroy()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
