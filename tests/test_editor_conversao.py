"""
Testes de `core/editor/conversao.py` (ED-00; SPEC_EDITOR §10.8): as oito contagens do
relatório, o resumo, o cronômetro e a validação das opções.

Rodar sem pytest:      python tests/test_editor_conversao.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.editor import conversao, modelo as m

FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _livro():
    cap = m.Capitulo(arquivo="Text/c.xhtml", blocos=[
        m.Paragrafo(trechos=[m.Trecho(texto="a"), m.Trecho(ilha="<cite>x</cite>")]),
        m.Diagrama(fen=FEN), m.Diagrama(fen=FEN, modo="fonte"),
        m.Figura(recurso="Images/i.png", alt="i"),
        m.IlhaBruta(xhtml="<svg/>", elemento="svg"),
        m.Lista(ordenada=False, itens=[m.ItemDeLista(paragrafos=[m.Paragrafo(trechos=[m.Trecho(texto="i")])])]),
    ], notas=[m.Nota(blocos=[m.Paragrafo(trechos=[m.Trecho(texto="n")])])])
    return m.Livro(metadados=m.Metadados(titulo="T"), capitulos=[cap, m.Capitulo(arquivo="Text/d.xhtml")])


def test_contar_preenche_as_oito_contagens():
    r = conversao.RelatorioDeConversao("epub").contar(_livro())
    # 8 blocos: os seis de cima, o paragrafo do item da lista e o paragrafo da nota.
    assert (r.capitulos, r.blocos, r.diagramas_png, r.diagramas_fonte, r.figuras, r.notas, r.ilhas) == (
        2, 8, 1, 1, 1, 1, 2)
    assert r.fontes_embutidas == [] and r.tempo_s == 0.0


def test_resumo_lista_as_contagens_e_os_avisos():
    r = conversao.RelatorioDeConversao("docx").contar(_livro())
    for i in range(25):
        r.aviso(f"aviso {i}")
    linhas = r.resumo().splitlines()
    assert linhas[0] == "Formato: docx" and "Diagramas: 1 em imagem, 1 em fonte" in linhas
    assert "Avisos: 25" in linhas and "  … e mais 5" in linhas


def test_cronometro_grava_o_tempo():
    r = conversao.RelatorioDeConversao("txt")
    with conversao.Cronometro(r):
        pass
    assert r.tempo_s >= 0.0


def test_opcoes_validam_os_vocabularios():
    o = conversao.OpcoesDeConversao(modo_de_diagrama="fonte", notas="fim", corpo_pt="18")
    assert o.corpo_pt == 18.0 and o.ncx and o.sumario
    with pytest.raises(ValueError):
        conversao.OpcoesDeConversao(modo_de_diagrama="jpg")
    with pytest.raises(ValueError):
        conversao.OpcoesDeConversao(notas="margem")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
