"""
Testes de `core/editor/estatisticas.py` (ED-06; SPEC_EDITOR §8.15): a contagem bate com
o modelo (AC-ED06-5) — palavras, caracteres, parágrafos, objetos, notas, páginas —, o
livro soma os capítulos, o capítulo em texto cru é contado pelo texto sem as tags, e a
janela mostra a caixa com o mesmo número da barra de status.

Rodar sem pytest:      python tests/test_editor_estatisticas.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import estatisticas, modelo as m
from core.editor.modelo import Capitulo, Paragrafo, Trecho
from editor_ambiente import Janela


def _p(texto, **kw):
    return Paragrafo(trechos=[Trecho(texto=texto)], **kw)


def test_ac5_a_contagem_bate_com_o_modelo():
    cap = Capitulo(arquivo="c.xhtml", blocos=[
        m.Titulo(trechos=[Trecho(texto="Um título")], nivel=1),
        Paragrafo(trechos=[Trecho(texto="Duas "), Trecho(texto="palavras", negrito=True),
                           Trecho(texto="e mais três", quebra_antes=True)]),
        Paragrafo(trechos=[Trecho(texto="12.Nf3", papel="lance"), Trecho(texto=" "), Trecho(nota="n1"),
                           Trecho(texto="aqui", pagina=4)]),
        _p(""), m.MarcaDePagina(pagina=5), m.Separador(),
        m.Lista(ordenada=False, itens=[m.ItemDeLista(paragrafos=[_p("item um")]),
                                       m.ItemDeLista(paragrafos=[_p("item dois")])]),
        m.Tabela(filas=[[m.Celula(blocos=[_p("célula")])]], legenda=[Trecho(texto="Legenda da tabela")]),
        m.Figura(recurso="Images/a.png", legenda=[Trecho(texto="foto")]),
        m.Diagrama(fen="8/8/8/8/8/8/8/K6k w - - 0 1"),
        m.Citacao(blocos=[_p("citação aqui")]),
    ], notas=[m.Nota(id="n1", blocos=[_p("nota de rodapé")])])
    c = estatisticas.contar_capitulo(cap)
    textos = ["Um título", "Duas palavras\ne mais três", "12.Nf3 aqui", "", "item um", "item dois", "célula",
              "citação aqui"]
    esperado_palavras = sum(len(re.findall(r"\w+", t)) for t in textos) + 3 + 1 + 3     # legendas e nota
    assert c.palavras == esperado_palavras
    assert c.caracteres == sum(len(t) for t in textos) + len("Legenda da tabela") + len("foto") + len("nota de rodapé")
    assert c.caracteres_sem_espacos == c.caracteres - sum(t.count(" ") + t.count("\n") for t in textos) - 2 - 0 - 2
    assert c.paragrafos == 7 and c.titulos == 1 and c.blocos == 11
    assert (c.diagramas, c.figuras, c.tabelas, c.listas, c.notas, c.lances, c.paginas) == (1, 1, 1, 1, 1, 1, 2)
    assert c.avisos == []
    linhas = c.linhas()
    assert linhas[0].startswith("Palavras: ") and any("Notas: 1" in li for li in linhas)


def test_o_livro_soma_os_capitulos_e_o_texto_cru_e_contado_sem_as_tags():
    livro = editor_livros.livro_completo()
    total = estatisticas.contar_livro(livro)
    partes = [estatisticas.contar_capitulo(c) for c in livro.capitulos]
    assert total.palavras == sum(p.palavras for p in partes) and total.capitulos == 2
    assert total.diagramas == 4 and total.figuras == 2 and total.tabelas == 1 and total.notas == 2
    assert total.linhas()[0] == "Capítulos: 2"
    cru = Capitulo(arquivo="x.xhtml", texto_cru="<html><body><p>três <b>palavras</b> aqui</p></body></html>")
    c = estatisticas.contar_capitulo(cru)
    assert c.palavras == 3 and c.blocos == 0 and c.avisos == ["x.xhtml: contado pelo texto cru (modo código)"]
    assert estatisticas.palavras_de("um dois-três") == 3


def test_a_janela_mostra_a_caixa_e_o_numero_bate_com_a_barra_de_status():
    with Janela() as t:
        j = t.j
        total = j.executar("estatisticas")
        chamada = next(c for c in t.caixas.chamadas if c[0] == "texto" and c[1] == "Estatísticas do livro")
        assert f"Palavras: {total.palavras}" in chamada[2] and "Por capítulo:" in chamada[2]
        assert "cap1.xhtml:" in chamada[2] and "cap2.xhtml:" in chamada[2]
        # o total do livro é o que "Contagem de palavras" (ED-02) diz
        contagem = j.executar("contagem")
        assert contagem["livro"] == total.palavras
        # a barra de status do capítulo bate com a contagem do capítulo
        j._atualizar_contagem()
        cap1 = estatisticas.contar_capitulo(t.texto.sincronizar())
        assert j.campos["palavras"].cget("text") == f"{cap1.palavras:,} palavras".replace(",", ".")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
