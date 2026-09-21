"""
Testes do léxico do português (ED-06b; SPEC_EDITOR §8.13): `core/afixos.py` reconhece as
flexões pelas regras Hunspell (cavalos, jogariam, desfizeram) e recusa o que não existe;
`sugestoes("cavalu", lex_pt)` contém "cavalo" (AC-ED06b-2); o pacote
`assets/lexico/pt.hunspell.gz` carrega em menos de um segundo; e uma amostra da expansão
completa (o `unmunch` de `scripts/gerar_lexico_pt.py`) é toda reconhecida.

Rodar sem pytest:      python tests/test_lexico_pt.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import afixos, lexico
from core.editor import ortografia

PACOTE = os.path.join(ortografia.PASTA_DOS_LEXICOS, "pt.hunspell.gz")
AFF_EXEMPLO = """SET UTF-8
SFX D Y 3
SFX D 0 s [oeu]
SFX D o a o
SFX D o as o
SFX B Y 1
SFX B 0 s .
PFX R Y 1
PFX R 0 re .
PFX N N 1
PFX N 0 anti .
---
cavalo/DR
bispo/DN
xeque
Torre/B
"""


def test_o_verificador_minimo_reconhece_raiz_sufixo_prefixo_e_o_cruzado():
    a = afixos.Afixos.ler(AFF_EXEMPLO.splitlines())
    assert len(a) == 4 and a.conhece("cavalo") and a.conhece("Xeque") and a.conhece("torre")
    assert a.conhece("cavalos") and a.conhece("cavala") and a.conhece("cavalas") and a.conhece("torres")
    assert a.conhece("recavalo") and a.conhece("recavalos")           # prefixo, e prefixo + sufixo (cruzados)
    assert a.conhece("antibispo") and not a.conhece("antibispos")     # `N` não é cruzado
    assert not a.conhece("cavalu") and not a.conhece("rebispo") and not a.conhece("") and not a.conhece("s")
    assert not a.conhece("xeques")                                    # sem flag, sem flexão


@pytest.fixture(scope="module")
def lex_pt():
    if not os.path.exists(PACOTE):
        pytest.skip("assets/lexico/pt.hunspell.gz ausente (scripts/gerar_lexico_pt.py)")
    return ortografia.Lexicos(None)("pt")


def test_o_pacote_carrega_rapido_e_conhece_flexoes(lex_pt):
    inicio = time.perf_counter()
    a = afixos.Afixos.carregar(PACOTE)
    assert time.perf_counter() - inicio < 3.0 and len(a) > 300_000
    assert os.path.getsize(PACOTE) < 2_000_000
    for palavra in ("cavalo", "cavalos", "bispo", "jogaram", "jogariam", "desfizeram", "rainha", "peões", "torres",
                    "amaríamos", "rapidamente", "xeque-mate", "abertura", "aberturas"):
        assert lex_pt.conhece(palavra), palavra
    for palavra in ("cavalu", "peao", "Nimzowitsch", "knight"):
        assert not lex_pt.conhece(palavra), palavra
    assert lex_pt.sinaliza and lex_pt.idioma == "pt"


def test_ac2_sugestoes_de_cavalu_contem_cavalo(lex_pt):
    achadas = lexico.sugestoes("cavalu", lex_pt)
    assert "cavalo" in achadas and achadas[0] == "cavalo"
    assert lexico.sugestoes("Bispu", lex_pt)[0].startswith("Bisp")


def test_verificar_em_portugues_acusa_so_a_palavra_errada(lex_pt):
    from core.editor.modelo import Capitulo, Paragrafo, Trecho

    cap = Capitulo(arquivo="c.xhtml", blocos=[Paragrafo(trechos=[
        Trecho(texto="O cavalu saltou e o bispo dormiu 12.Nf3 xeque-mate, disse Nimzowitsch.")])], idioma="pt-BR")
    lexicos = ortografia.Lexicos(None)
    assert [s.palavra for s in ortografia.verificar(cap, lexicos)] == ["cavalu", "Nimzowitsch"]
    lexicos.ignorar("Nimzowitsch")
    assert [s.palavra for s in ortografia.verificar(cap, lexicos, ignoradas=lexicos.ignoradas)] == ["cavalu"]


@pytest.mark.slow
def test_uma_amostra_da_expansao_completa_e_toda_reconhecida():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import random

    import gerar_lexico_pt as g

    dic = next((c for c in g.CANDIDATOS if os.path.exists(c)), None)
    if dic is None or not os.path.exists(PACOTE):
        pytest.skip("dicionário Hunspell pt_BR não instalado")
    sufixos, prefixos, codificacao = g.ler_aff(os.path.splitext(dic)[0] + ".aff")
    raizes = list(g.ler_dic(dic, codificacao))
    random.seed(7)
    a = afixos.Afixos.carregar(PACOTE)
    faltas = []
    for raiz, flags in random.sample(raizes, 400):
        for forma in g.expandir(raiz, flags, sufixos, prefixos):
            if "-" not in forma and not a.conhece(forma):
                faltas.append((raiz, forma))
    assert faltas == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
