"""
Testes de `core/editor/buscas_salvas.py` e `ui/editor/buscas_salvas.py` (ED-06b; SPEC_EDITOR
§8.12): um grupo de três buscas em lote com resumo, exportar e importar JSON (AC-ED06b-3);
guardar a busca da caixa, carregá-la de volta, remover; a persistência nas preferências;
e a caixa construída sem mostrar.

Rodar sem pytest:      python tests/test_editor_buscas_salvas.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import buscas_salvas as bs, modelo as m
from core.editor.busca import Opcoes
from core.editor.modelo import Capitulo, Paragrafo, Trecho
from editor_ambiente import Janela


def _p(texto):
    return Paragrafo(trechos=[Trecho(texto=texto)])


def test_a_colecao_guarda_troca_remove_e_grava_nas_preferencias():
    gravadas = []
    colecao = bs.Colecao.carregar([{"nome": "a", "grupo": "g", "opcoes": {"texto": "x", "lua": 1}}, {"errado": 1}],
                                  gravadas.append)
    assert colecao.nomes() == ["a"] and colecao.por_nome("a").opcoes == {"texto": "x"}
    colecao.guardar(bs.BuscaSalva.de_opcoes("b", Opcoes(texto="y", substituto="z", regex=True), "g"))
    colecao.guardar(bs.BuscaSalva("a", "g", {"texto": "x2"}))
    assert colecao.nomes() == ["a", "b"] and colecao.por_nome("a").opcoes["texto"] == "x2"
    assert colecao.grupos() == ["g"] and [b.nome for b in colecao.do_grupo("g")] == ["a", "b"]
    assert colecao.por_nome("b").como_opcoes() == Opcoes(texto="y", substituto="z", regex=True)
    assert colecao.remover("a") is True and colecao.remover("a") is False and colecao.nomes() == ["b"]
    assert len(gravadas) == 3 and gravadas[-1] == colecao.como_lista()
    with pytest.raises(ValueError):
        bs.BuscaSalva("  ")


def test_ac3_o_lote_de_tres_resume_e_o_json_vai_e_volta(tmp_path):
    colecao = bs.Colecao()
    for k in range(1, 4):
        colecao.guardar(bs.BuscaSalva(f"b{k}", "limpeza", {"texto": f"x{k}", "substituto": "y"}))
    colecao.guardar(bs.BuscaSalva("solta", "", {"texto": "z"}))
    chamadas = []

    def executar(opcoes):
        chamadas.append(opcoes.texto)
        if opcoes.texto == "x2":
            raise ValueError("regex inválida")
        return {"a.xhtml": 2, "b.xhtml": 1} if opcoes.texto == "x1" else {}

    resumo = colecao.grupo_em_lote("limpeza", executar)
    assert chamadas == ["x1", "x2", "x3"] and resumo.total == 3
    assert resumo.por_busca == {"b1": {"a.xhtml": 2, "b.xhtml": 1}, "b3": {}} and resumo.erros == {"b2": "regex inválida"}
    linhas = resumo.linhas()
    assert linhas[0] == "Lote: 3 substituição(ões) em 2 busca(s)" and "b2: erro" in linhas[-1]
    assert colecao.em_lote(["nada"], executar).erros == {"nada": "não existe"}
    caminho = str(tmp_path / "buscas.json")
    assert colecao.exportar_json(caminho, ["b1", "b3"]) == 2
    dados = json.load(open(caminho, encoding="utf-8"))
    assert dados["formato"] == "pybox-buscas" and [b["nome"] for b in dados["buscas"]] == ["b1", "b3"]
    outra = bs.Colecao()
    assert outra.importar_json(caminho) == 2 and outra.nomes() == ["b1", "b3"]
    assert outra.por_nome("b3").grupo == "limpeza"
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({"formato": "outro"}, f)
    with pytest.raises(ValueError, match="não é um arquivo de buscas"):
        outra.importar_json(caminho)


def test_na_janela_guardar_carregar_executar_o_lote_e_persistir(tmp_path):
    with Janela() as t:
        j = t.j
        texto = t.texto
        texto.carregar(Capitulo(arquivo="cap1.xhtml", blocos=[_p("aaa bbb ccc"), _p("aaa e ccc")], idioma="pt"))
        j.busca.definir(texto="aaa", substituto="A", escopo="capitulo", maiusculas=True)
        bsj = j.buscas_salvas
        assert bsj.guardar_atual("a→A", "limpeza").opcoes["maiusculas"] is True
        j.busca.definir(texto="ccc", substituto="C")
        bsj.guardar_atual("c→C", "limpeza")
        j.busca.definir(texto="bbb", substituto="B", regex=True)
        bsj.guardar_atual("b→B", "limpeza")
        assert t.settings.get("editor")["buscas_salvas"][0]["nome"] == "a→A"
        # carregar põe a busca de volta na caixa
        j.busca.definir(texto="outra", substituto="", regex=False)
        assert j.executar("_buscas_salvas_carregar", "b→B").nome == "b→B"
        assert j.busca.opcoes().texto == "bbb" and j.busca.opcoes().regex is True
        # o lote roda as três e o resumo vai ao status e à caixa; a caixa da busca volta como estava
        j.busca.definir(texto="guardada", substituto="", regex=False)
        resumo = j.executar("_buscas_salvas_lote", "limpeza")
        assert resumo.total == 5 and resumo.por_busca == {"a→A": {"cap1.xhtml": 2}, "c→C": {"cap1.xhtml": 2},
                                                          "b→B": {"cap1.xhtml": 1}}
        assert [m.texto_de(b) for b in texto.sincronizar().blocos] == ["A B C", "A e C"]
        assert j.busca.opcoes().texto == "guardada" and "Lote: 5" in j.campos["aviso"].cget("text")
        assert any(c[0] == "texto" and c[1] == "Lote: limpeza" for c in t.caixas.chamadas)
        # executar uma só
        texto.carregar(Capitulo(arquivo="cap1.xhtml", blocos=[_p("aaa")], idioma="pt"))
        assert j.executar("_buscas_salvas_executar", "a→A") == {"cap1.xhtml": 1}
        # exportar e importar pela janela
        caminho = str(tmp_path / "b.json")
        assert bsj.exportar(caminho) == 3 and bsj.remover("a→A") and bsj.importar(caminho) == 3
        assert bsj.colecao.nomes() == ["c→C", "b→B", "a→A"]
        # a caixa, construída sem mostrar
        caixa = j.executar("buscas_salvas")
        assert caixa is not None and caixa.arvore.exists("grupo:limpeza") and caixa.arvore.exists("busca:a→A")
        caixa.escolher("a→A")
        assert caixa.selecionada() == ("busca", "a→A")
        caixa.escolher("limpeza", grupo=True)
        assert caixa.selecionada() == ("grupo", "limpeza")
        caixa.cancelar()
        # erros de entrada
        j.executar("_buscas_salvas_carregar", "nada")
        assert "não há busca salva" in t.caixas.entradas()[-1]
        j.executar("_buscas_salvas_lote", "vazio")
        assert "não tem buscas" in t.caixas.entradas()[-1]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
