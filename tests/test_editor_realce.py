"""
Testes de `ui/editor/realce.py` (ED-07; SPEC_EDITOR §9.2, §13.2): o tokenizador de XHTML
e de CSS, o estado por linha e a convergência da re-tokenização (o `<!--` na linha 10
de 200 realça as seguintes e fechá-lo as devolve — AC-ED07-1), o contraste ≥ 4,5:1
dos dois temas (AC-ED07-8) e, num teste `slow`, o tempo da faixa visível de um
arquivo de 200 KB.

Rodar sem pytest:      python tests/test_editor_realce.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from ui.editor import realce

XHTML = ('<?xml version="1.0" encoding="utf-8"?>\n'
         '<html xmlns="http://www.w3.org/1999/xhtml">\n'
         "<head><title>T</title>\n"
         "<style>\np { color: red; } /* x\ny */ @media print { p > span.x { margin: 0 } }\n</style></head>\n"
         '<body><p class="a b" id=\'x\'>Texto &amp; <b>neg</b><br/> <!-- com\nentario --> fim</p>\n'
         "<![CDATA[ a < b ]]><script>if (a < b) {}</script>\n"
         "</body></html>")


def _tipos(tokens, linha):
    return [(linha[a:b], t) for a, b, t in tokens]


def test_tokeniza_xhtml_com_estados_por_linha():
    linhas = XHTML.split("\n")
    r = realce.Realce("xhtml")
    r.carregar(linhas)
    assert len(r.estados) == len(linhas) + 1
    assert _tipos(r.tokens(linhas, 0), linhas[0]) == [('<?xml version="1.0" encoding="utf-8"?>', "pi")]
    assert _tipos(r.tokens(linhas, 1), linhas[1])[:4] == [("<html", "tag"), ("xmlns", "atributo"), ("=", "pontuacao"),
                                                          ('"http://www.w3.org/1999/xhtml"', "valor")]
    assert r.estados[4] == ("css_fora", 0)                               # dentro de <style>
    assert ("p", "seletor") in _tipos(r.tokens(linhas, 4), linhas[4])
    assert r.estados[5] == ("css_comentario_fora", 0)                    # o /* atravessou a linha
    tipos5 = _tipos(r.tokens(linhas, 5), linhas[5])
    assert tipos5[0] == ("y */", "comentario") and ("@media print", "arroba") in tipos5
    assert ("p > span.x", "seletor") in tipos5 and ("margin", "propriedade") in tipos5
    assert r.estados[6] == ("css_fora", 0) and _tipos(r.tokens(linhas, 6), linhas[6])[0] == ("</style", "tag")
    tipos7 = _tipos(r.tokens(linhas, 7), linhas[7])
    assert ('"a b"', "valor") in tipos7 and ("'x'", "valor") in tipos7 and ("&amp;", "entidade") in tipos7
    assert ("<br", "tag") in tipos7 and ("/>", "tag") in tipos7 and tipos7[-1] == ("<!-- com", "comentario")
    assert r.estados[8] == ("comentario", "")
    tipos8 = _tipos(r.tokens(linhas, 8), linhas[8])
    assert tipos8[0] == ("entario -->", "comentario") and ("</p", "tag") in tipos8
    tipos9 = _tipos(r.tokens(linhas, 9), linhas[9])
    assert tipos9[0] == ("<![CDATA[ a < b ]]>", "cdata") and ("if (a < b) {}", "script") in tipos9
    assert r.estados[-1] == ("texto", "")


def test_tokeniza_css_com_blocos_aninhados_e_comentarios():
    linhas = ["/* x", "y */ @media print { p > span.x { margin: 0 } }",
              "@font-face { font-family: 'A'; src: url(a.otf) }", "p.x, h1 { color: #fff; }", '.q { content: "}" }']
    r = realce.Realce("css")
    r.carregar(linhas)
    assert r.estados[1] == ("css_comentario_fora", 0)
    assert ("p > span.x", "seletor") in _tipos(r.tokens(linhas, 1), linhas[1])
    t2 = _tipos(r.tokens(linhas, 2), linhas[2])
    assert t2[0] == ("@font-face", "arroba") and ("font-family", "propriedade") in t2 and (" 'A'", "valor") in t2
    assert ("p.x, h1", "seletor") in _tipos(r.tokens(linhas, 3), linhas[3])
    assert ('"}"', "valor") in _tipos(r.tokens(linhas, 4), linhas[4]) or (' "}"', "valor") in _tipos(r.tokens(linhas, 4), linhas[4])
    assert r.estados[-1] == ("css_fora", 0)
    with pytest.raises(ValueError):
        realce.Tokenizador("python")


def test_ac1_o_comentario_aberto_na_linha_10_propaga_e_fechado_devolve():
    linhas = ["<p>linha %d</p>" % i for i in range(200)]
    r = realce.Realce("xhtml")
    r.carregar(linhas)
    assert all(e == ("texto", "") for e in r.estados)
    # Abre um comentário na linha 10 (índice 9): tudo depois vira comentário.
    linhas[9] = "<!-- " + linhas[9]
    r.editar(9, 1, 1)
    de, ate = r.reprocessar(linhas, 9)
    assert (de, ate) == (9, 200)                       # foi até o fim: nada convergiu
    assert all(e == ("comentario", "") for e in r.estados[10:])
    assert _tipos(r.tokens(linhas, 150), linhas[150]) == [(linhas[150], "comentario")]
    # Fecha na linha 20: da 21 em diante volta ao que era, e a re-tokenização para lá.
    linhas[19] = linhas[19] + " -->"
    r.editar(19, 1, 1)
    de, ate = r.reprocessar(linhas, 19)
    assert (de, ate) == (19, 200)                      # todas começavam em comentário: todas mudam de novo
    assert r.estados[20] == ("texto", "") and all(e == ("texto", "") for e in r.estados[21:])
    # Reabrir e fechar na linha seguinte para na primeira linha que já começava em "texto".
    linhas[30] = "<!-- " + linhas[30] + " -->"
    r.editar(30, 1, 1)
    assert r.reprocessar(linhas, 30) == (30, 32)
    assert ("<p", "tag") in _tipos(r.tokens(linhas, 150), linhas[150])
    # Editar uma linha comum re-tokeniza só ela.
    linhas[100] = "<p><b>x</b></p>"
    r.editar(100, 1, 1)
    assert r.reprocessar(linhas, 100) == (100, 102)


def test_editar_ajusta_a_lista_de_estados_a_linhas_inseridas_e_removidas():
    linhas = ["<p>a", "b</p>", "<!-- c", "d -->", "<p>e</p>"]
    r = realce.Realce("xhtml")
    r.carregar(linhas)
    assert r.estados[3] == ("comentario", "")
    # Duas linhas inseridas depois da 1 (dentro do parágrafo).
    linhas[2:2] = ["x", "y"]
    r.editar(1, 1, 3)
    r.reprocessar(linhas, 1)
    assert len(r.estados) == len(linhas) + 1 and r.estados[5] == ("comentario", "")
    # As duas removidas de novo.
    del linhas[2:4]
    r.editar(1, 3, 1)
    r.reprocessar(linhas, 1)
    assert len(r.estados) == len(linhas) + 1 and r.estados[3] == ("comentario", "")
    # Uma lista desalinhada é recarregada inteira.
    r.estados.pop()
    assert r.reprocessar(linhas, 2) == (0, 5)


def test_ac8_contraste_dos_dois_temas_e_pelo_menos_4_5_para_1():
    for nome in ("claro", "escuro"):
        t = realce.tema(nome)
        for tipo in realce.TIPOS:
            assert realce.contraste(t[tipo], t["fundo"]) >= 4.5, (nome, tipo)
            for fundo in ("linha_atual", "casamento", "erro"):
                assert realce.contraste(t[tipo], t[fundo]) >= 4.5, (nome, tipo, fundo)
        assert realce.contraste(t["texto"], t["fundo"]) >= 4.5
        assert realce.contraste(t["selecao_texto"], t["selecao"]) >= 4.5
        assert realce.contraste(t["calha_texto"], t["calha_fundo"]) >= 4.5
    assert round(realce.contraste("#000000", "#ffffff"), 1) == 21.0
    with pytest.raises(ValueError):
        realce.tema("sepia")


@pytest.mark.slow
def test_faixa_visivel_de_um_arquivo_de_200kb_realca_em_menos_de_50ms():
    paragrafo = '<p class="corpo">Uma linha de prosa com <b>negrito</b>, <i>itálico</i> e &amp; entidade.</p>'
    linhas = [paragrafo] * (200 * 1024 // (len(paragrafo) + 1))
    r = realce.Realce("xhtml")
    inicio = time.perf_counter()
    r.carregar(linhas)
    carga = time.perf_counter() - inicio
    inicio = time.perf_counter()
    for _i, _tokens in r.faixa(linhas, 1000, 1060):
        pass
    faixa = time.perf_counter() - inicio
    assert faixa < 0.05, f"faixa de 60 linhas em {faixa * 1000:.1f} ms (carga inteira em {carga * 1000:.0f} ms)"
    assert carga < 2.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
