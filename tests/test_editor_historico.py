"""
Testes de `core/editor/historico.py` (ED-00; SPEC_EDITOR DEC-04, AC-ED00-10): desfazer e
refazer por capítulo, coalescência da digitação com relógio injetado, limite da pilha, e
`aplicar` devolvendo o capítulo ao estado do ponto.

Rodar sem pytest:      python tests/test_editor_historico.py
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.editor import historico, modelo as m


class Relogio:
    def __init__(self):
        self.agora = 0.0

    def __call__(self):
        return self.agora


def _cap(*textos):
    return m.Capitulo(arquivo="Text/c.xhtml",
                      blocos=[m.Paragrafo(trechos=[m.Trecho(texto=t)]) for t in textos])


def _editar(h, cap, indice, texto, coalescer=False):
    antes = [cap.blocos[indice]]
    depois = [copy.deepcopy(cap.blocos[indice])]
    depois[0].trechos[0].texto = texto
    h.ponto(cap.arquivo, [antes[0].id], antes, depois, coalescer=coalescer)
    cap.blocos[indice] = depois[0]


def test_dez_pontos_desfeitos_um_a_um_devolvem_o_inicio_e_refeitos_o_fim():
    relogio = Relogio()
    h = historico.Historico(relogio=relogio)
    cap = _cap("a", "b", "c")
    inicial = m.para_dict(cap)
    for i in range(10):
        relogio.agora += 5
        _editar(h, cap, i % 3, f"v{i}")
    final = m.para_dict(cap)
    assert final != inicial
    while h.pode_desfazer(cap.arquivo):
        historico.aplicar(cap, h.desfazer(cap.arquivo), "antes")
    assert m.para_dict(cap) == inicial
    while h.pode_refazer(cap.arquivo):
        historico.aplicar(cap, h.refazer(cap.arquivo), "depois")
    assert m.para_dict(cap) == final


def test_digitacao_continua_e_um_ponto_so():
    relogio = Relogio()
    h = historico.Historico(coalescencia_s=0.7, relogio=relogio)
    cap = _cap("")
    for i, letra in enumerate("abc"):
        relogio.agora += 0.3
        _editar(h, cap, 0, "abc"[:i + 1], coalescer=True)
    assert len(h._de(cap.arquivo).desfazer) == 1
    relogio.agora += 2.0
    _editar(h, cap, 0, "abcd", coalescer=True)
    assert len(h._de(cap.arquivo).desfazer) == 2
    historico.aplicar(cap, h.desfazer(cap.arquivo), "antes")
    assert m.texto_de(cap.blocos[0]) == "abc"
    historico.aplicar(cap, h.desfazer(cap.arquivo), "antes")
    assert m.texto_de(cap.blocos[0]) == ""


def test_um_ponto_novo_apaga_o_refazer_e_o_limite_vale():
    h = historico.Historico(limite=3, relogio=Relogio())
    cap = _cap("a")
    for i in range(5):
        _editar(h, cap, 0, str(i))
    assert len(h._de(cap.arquivo).desfazer) == 3
    h.desfazer(cap.arquivo)
    assert h.pode_refazer(cap.arquivo)
    _editar(h, cap, 0, "novo")
    assert not h.pode_refazer(cap.arquivo)


def test_capitulos_sao_independentes():
    h = historico.Historico(relogio=Relogio())
    a, b = _cap("a"), _cap("b")
    b.arquivo = "Text/d.xhtml"
    _editar(h, a, 0, "a2")
    assert h.pode_desfazer(a.arquivo) and not h.pode_desfazer(b.arquivo)
    assert h.capitulos_com_historico() == [a.arquivo]
    h.limpar(a.arquivo)
    assert not h.pode_desfazer(a.arquivo)


def test_aplicar_reinsere_bloco_apagado_e_remove_bloco_criado():
    h = historico.Historico(relogio=Relogio())
    cap = _cap("a", "b", "c")
    apagado = cap.blocos[1]
    h.ponto(cap.arquivo, [apagado.id], [apagado], [], rotulo="apagar", indices={apagado.id: 1})
    del cap.blocos[1]
    novo = m.Paragrafo(trechos=[m.Trecho(texto="n")])
    h.ponto(cap.arquivo, [novo.id], [], [novo], rotulo="inserir")
    cap.blocos.append(novo)
    assert [m.texto_de(b) for b in cap.blocos] == ["a", "c", "n"]
    historico.aplicar(cap, h.desfazer(cap.arquivo), "antes")
    assert [m.texto_de(b) for b in cap.blocos] == ["a", "c"]
    historico.aplicar(cap, h.desfazer(cap.arquivo), "antes")
    assert [m.texto_de(b) for b in cap.blocos] == ["a", "b", "c"]


def test_aplicar_tambem_cobre_notas():
    h = historico.Historico(relogio=Relogio())
    cap = _cap("a")
    nota = m.Nota(blocos=[m.Paragrafo(trechos=[m.Trecho(texto="n1")])])
    cap.notas.append(nota)
    depois = copy.deepcopy(nota)
    depois.blocos[0].trechos[0].texto = "n2"
    h.ponto(cap.arquivo, [nota.id], [nota], [depois])
    cap.notas[0] = depois
    historico.aplicar(cap, h.desfazer(cap.arquivo), "antes")
    assert m.texto_de(cap.notas[0]) == "n1"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
