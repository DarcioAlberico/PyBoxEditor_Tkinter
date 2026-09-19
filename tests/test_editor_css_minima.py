"""
Testes de `core/editor/css_minima.py` (ED-00; SPEC_EDITOR §6.4, AC-ED00-6).

O que se prende: a folha padrão do livro é lida do jeito que o modo texto precisa
(`p` com recuo, `p.primeira` sem), o que o parser não entende é pulado **sem perder**
(`@media`, `@import`, seletores compostos, comentários, `!important`), a cascata de
duas folhas dá a última a vencer, e `escrever` só reescreve a regra tocada.

Rodar sem pytest:      python tests/test_editor_css_minima.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.editor import css_minima, dialeto

EXTRA = """
/* comentário que fica */
@media print { p { color: red; } }
p > span.x { color: blue; }
@import url(x.css);
@font-face { font-family: "SkakNew-Diagram"; src: url("../Fonts/SkakNew-Diagram.otf"); }
p.comentario { font-style: italic !important; color: #444; }
.versalete, span.destaque { font-variant: small-caps; }
"""


def _folha():
    return css_minima.ler(dialeto.css_padrao(16, "simples", "reto") + EXTRA)


def test_a_folha_padrao_e_lida_como_o_modo_texto_precisa():
    f = _folha()
    assert f.estilo_de("p")["text-indent"] == "1.2em"
    assert f.estilo_de("p", ["primeira"])["text-indent"] == "0"
    assert f.estilo_de("p", ["primeira"])["text-align"] == "justify"   # herdado de `p`
    assert f.estilo_de("h1") == {}


def test_important_e_tolerado_e_a_ultima_regra_do_mesmo_seletor_vence():
    f = _folha()
    estilo = f.estilo_de("p", ["comentario"])
    assert estilo["font-style"] == "italic" and estilo["color"] == "#444"
    assert f.regra("p.comentario").declaracoes["color"] == "#444"


def test_o_que_nao_e_da_css_minima_e_pulado_e_listado():
    f = _folha()
    assert "@media print" in f.ignoradas and "p > span.x" in f.ignoradas
    assert any(i.startswith("@import") for i in f.ignoradas)
    assert "td p" in f.ignoradas          # seletor composto da CSS de sempre
    assert f.fontes[0].familia == "SkakNew-Diagram"
    assert f.familia_da_fonte('"SkakNew-Diagram"') == "../Fonts/SkakNew-Diagram.otf"


def test_seletor_com_virgula_da_uma_regra_por_parte():
    f = _folha()
    assert f.estilo_de("span", ["versalete"])["font-variant"] == "small-caps"
    assert f.estilo_de("span", ["destaque"])["font-variant"] == "small-caps"
    assert f.estilo_de("em", ["versalete"])["font-variant"] == "small-caps"


def test_escrever_so_reescreve_a_regra_tocada_e_preserva_o_resto():
    css = dialeto.css_padrao() + EXTRA
    f = css_minima.ler(css)
    regra = f.regra("p.comentario")
    f.definir("p.comentario", color="#000")
    f.definir("p.novo", font_weight="bold")
    novo = css_minima.escrever(f)
    assert novo[:regra.inicio] == css[:regra.inicio]
    assert css[regra.fim:].strip() in novo
    assert "p.comentario { font-style: italic; color: #000; }" in novo
    assert novo.rstrip().endswith("p.novo { font-weight: bold; }")
    assert "/* comentário que fica */" in novo and "@media print { p { color: red; } }" in novo


def test_definir_recusa_seletor_fora_da_css_minima():
    f = _folha()
    with pytest.raises(ValueError):
        f.definir("p > span", color="#000")


def test_cascata_de_duas_folhas_a_segunda_vence():
    a = css_minima.ler("p { color: #111; text-indent: 1em; }")
    b = css_minima.ler("p { color: #222; }")
    juntas = css_minima.cascata([a, b], ["a.css", "b.css"])
    assert juntas.estilo_de("p") == {"color": "#222", "text-indent": "1em"}
    assert [r.origem for r in juntas.regras] == ["a.css", "b.css"]


def test_o_peso_da_classe_ganha_do_elemento_e_o_elemento_classe_ganha_da_classe():
    f = css_minima.ler(".x { color: #1; } p { color: #2; } p.x { color: #3; }")
    assert f.estilo_de("p", ["x"])["color"] == "#3"
    assert f.estilo_de("em", ["x"])["color"] == "#1"
    assert f.estilo_de("p")["color"] == "#2"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
