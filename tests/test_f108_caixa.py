"""
F108 — o dicionário era cego a caixa, e por isso ninguém via `biShop`.

`Lexico.conhece` baixa os dois lados antes de comparar. O primeiro teste é a
razão de a fase existir: enquanto ele passar, um erro de caixa **não é erro**
para o dicionário, e nem o sinalizador nem o reparo da F66 podem alcançá-lo.

Os outros travam o que faz a regra ser segura: ela é tipográfica e não de
dicionário; o portão separa prosa de lixo de segmentação; a correção preserva o
comprimento, porque as fatias de negrito da F105 são índices sobre o mesmo
texto; e o `I` se acusa sem se corrigir, que é o único caso em que baixar a
maiúscula não devolve a letra certa.

Rodar sem pytest:      python tests/test_f108_caixa.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

from core import lexico, livro
from core.box_model import BoxEntry


def _lex(*palavras):
    return lexico.Lexico(palavras=set(palavras))


# ----------------------------------------------------------------------
# O achado
# ----------------------------------------------------------------------

def test_o_dicionario_nao_ve_erro_de_caixa():
    """
    É a razão de existir da fase, e não um caso de borda.

    `conhece` baixa os dois lados, então a palavra com maiúscula no meio é
    conhecida. Se isto passar a falhar, o dicionário aprendeu forma e a regra
    tipográfica deixou de ser a única saída.
    """
    lex = _lex("bishop", "the", "pianos")
    assert lex.conhece("biShop")
    assert lex.conhece("tHe")
    assert lex.conhece("pIanos")


# ----------------------------------------------------------------------
# A regra
# ----------------------------------------------------------------------

@pytest.mark.parametrize("palavra", ["bishop", "Bishop", "BISHOP", "das"])
def test_os_tres_padroes_legitimos_passam(palavra):
    assert not lexico.caixa_estranha(palavra)


@pytest.mark.parametrize("palavra", ["biShop", "daS", "pIanos", "XadreZ",
                                     "YaSSer"])
def test_a_maiuscula_no_meio_e_acusada(palavra):
    assert lexico.caixa_estranha(palavra)


@pytest.mark.parametrize("palavra", ["Bxf7", "Nxe4", "Kh1", "Rfe1", "NN"])
def test_o_lance_de_xadrez_nao_e_acusado(palavra):
    """
    A notação sobrevive por construção, e vale ter medido.

    `Bxf7` tem inicial maiúscula e o resto minúsculo — é o padrão Capitalizado.
    `Kh1` e `NN` não chegam ao mínimo de letras. Se a régua um dia acusasse
    lance, ela apagaria a figurina do livro inteiro.
    """
    assert not lexico.caixa_estranha(palavra)


@pytest.mark.parametrize("palavra", ["Spassky,B", "Hulak,K",
                                     "mau—Bispo", "Kasparov-Karpov"])
def test_a_maiuscula_depois_de_nao_letra_e_comeco_de_parte(palavra):
    """
    Enumerar separadores foi o erro da primeira versão, e a medição o mostrou.

    `Hulak,K` é nome com inicial, `mau—Bispo` usa travessão — que não está em
    `HIFENS`. Nos três a maiúscula abre parte nova, e acusá-los custava quatro
    palavras certas na medição.
    """
    assert not lexico.caixa_estranha(palavra)


def test_a_correcao_preserva_o_comprimento():
    """
    Não é estética: as fatias de negrito da F105 e o vetor de espessuras são
    índices sobre este mesmo texto. Uma correção que encurtasse a palavra os
    desalinharia em silêncio, e o negrito sairia no caractere errado.
    """
    for palavra in ("biShop", "YaSSer", "Kasparov-KarPov", "abc.DeF"):
        assert len(lexico.com_a_caixa_arrumada(palavra)) == len(palavra)


# ----------------------------------------------------------------------
# O portão
# ----------------------------------------------------------------------

def test_o_portao_separa_prosa_de_lixo_de_segmentacao():
    """
    E funciona **por causa** da cegueira de `conhece`, não apesar dela:
    `biShop` baixa para palavra conhecida e `tbitBl` não baixa para nada.
    """
    lex = _lex("bishop")
    assert lexico.arrumar_caixa("biShop tbitBl", lex) == "bishop tbitBl"


def test_sem_dicionario_nada_acontece():
    """A mesma porta que `separar_colados='auto'` — lista vazia, régua quieta."""
    assert lexico.arrumar_caixa("biShop", lexico.Lexico()) == "biShop"


def test_a_palavra_de_outro_idioma_fica_como_esta():
    """
    O teto que a fase não levanta, fixado para não surpreender.

    `defesa` não está na lista inglesa, então o portão não abre e `defeSa`
    atravessa. É o mesmo teto que barra o livro em português no
    `medir_confusao_no_livro`, e quem o levanta é uma lista de português.
    """
    assert lexico.arrumar_caixa("defeSa", _lex("bishop")) == "defeSa"


# ----------------------------------------------------------------------
# O `I`, que se acusa e não se baixa
# ----------------------------------------------------------------------

def test_o_i_e_acusado_mas_nao_corrigido():
    """
    A correção supõe que a letra certa é a minúscula da que se leu, e para o
    `I` isso é falso: ele entra no lugar do `l`, e `I`.lower() é `i`.

    Medido, **todas** as palavras que a regra acusava e não consertava eram
    desta família. Corrigi-las trocava `planos` lido `pIanos` por `pianos` —
    que é palavra, e portanto um erro que ninguém mais vê.
    """
    assert lexico.caixa_estranha("pIanos")
    assert not lexico.pode_baixar("pIanos")
    assert lexico.arrumar_caixa("pIanos", _lex("pianos")) == "pIanos"


def test_o_s_e_o_o_continuam_baixando():
    """O `I` sai da correção sozinho, e não leva a família junto."""
    lex = _lex("position", "also", "points")
    assert (lexico.arrumar_caixa("poSition alSo pointS", lex)
            == "position also points")


# ----------------------------------------------------------------------
# A fila de revisão
# ----------------------------------------------------------------------

def test_a_palavra_conhecida_com_caixa_estranha_acende():
    """
    Antes da fase ela saía do `sinalizar` sem acender nada — `conhece` dizia
    que estava boa. O motivo vai separado porque as duas suspeitas não se
    revisam igual: uma pede que se leia a palavra, a outra já diz que letra
    olhar.
    """
    lex = _lex("bishop")
    palavra = [(c, i) for i, c in enumerate("biShop")]
    suspeitas = lexico.sinalizar([palavra], lex)
    assert len(suspeitas) == 1
    assert suspeitas[0].palavra == "biShop"
    assert suspeitas[0].motivo == lexico.MOTIVO_CAIXA
    assert suspeitas[0].indices == list(range(6))


def test_a_palavra_certa_nao_acende():
    lex = _lex("bishop")
    palavra = [(c, i) for i, c in enumerate("bishop")]
    assert lexico.sinalizar([palavra], lex) == []


def test_a_fora_do_dicionario_mantem_o_motivo_de_sempre():
    """A suspeita antiga não muda de nome por causa da nova."""
    lex = _lex("bishop")
    palavra = [(c, i) for i, c in enumerate("bisxop")]
    suspeitas = lexico.sinalizar([palavra], lex)
    assert len(suspeitas) == 1
    assert suspeitas[0].motivo == "fora-do-dicionario"


# ----------------------------------------------------------------------
# Ponta a ponta, no caminho do livro
# ----------------------------------------------------------------------

def _pagina_com(texto: str):
    """Uma imagem e as caixas de uma linha, uma por caractere."""
    larg = 14 * len(texto) + 20
    img = np.full((40, larg), 255, np.uint8)
    boxes = []
    for i, c in enumerate(texto):
        x1 = 10 + i * 14
        b = BoxEntry(c, x1, 10, x1 + 10, 30)
        img[b.y1 + 1:b.y2 - 1, b.x1 + 1:b.x2 - 1] = 0
        boxes.append(b)
    return img, boxes


def test_a_linha_do_livro_sai_com_a_caixa_arrumada():
    """
    Ponta a ponta: é a **primeira vez que o dicionário entra no caminho do
    livro**. Até a F108 ele só existia na revisão da UI, e o arquivo exportado
    saía sem nenhuma ajuda dele.
    """
    texto = "the biShop"
    img, boxes = _pagina_com(texto)
    ler = lambda r, i=iter(texto): (next(i), 0.99)

    saida, _fracos, pesos, _lac, _cx = livro._texto_da_linha(
        img, boxes, ler, conf_minima=0.5)
    assert saida == "the biShop"

    arrumado = lexico.arrumar_caixa(saida, _lex("the", "bishop"))
    assert arrumado == "the bishop"
    # O alinhamento que a F105 depende: mesmo comprimento, mesmos índices.
    assert len(arrumado) == len(saida) == len(pesos)


def test_o_livro_sem_lexico_sai_como_antes():
    """`lex=None` é o padrão, e com ele nada muda — nem para quem já chamava."""
    import inspect
    assert inspect.signature(livro.extrair).parameters["lex"].default is None
    assert (inspect.signature(livro.extrair_pagina)
            .parameters["lex"].default is None)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
