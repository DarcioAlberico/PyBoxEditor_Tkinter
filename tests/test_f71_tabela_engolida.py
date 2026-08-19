"""
Testes da F71 — a tabela com moldura não saía partida, não saía.

`findContours` roda com `RETR_EXTERNAL`. Moldura fechada, e tudo que está dentro
dela vira contorno **filho**, que não é devolvido: a tabela de finais da página
236 do Nunn sai como **um** box de 1342×1099, o descarte o joga fora por ser
grande, e as 24 células vão junto. Medido, 0 boxes dentro do retângulo contra as
276 caixas de caractere que há ali.

A F11 já tinha a manobra — olhar dentro do bloco antes de jogá-lo fora —, e a
peneira que protege o diagrama (`tabuleiro é quadrado`) estava em 1,5, "no meio
do vão" porque nada no material caía entre 1,3 e 2,6. A tabela cai: 1,22. A
régua passa a ser a mesma que o `diagrama` usa para dizer o que é tabuleiro, e
assim o caso do meio deixa de existir por construção.

E abrir mais blocos escancarou o que a régua de antes escondia: a capa que é uma
fotografia tem escala de texto de 2 px, e com ela o bloco rende 40.382 "glifos".
Daí o teto.

Rodar sem pytest:      python tests/test_f71_tabela_engolida.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from core import diagrama, trama
from core.box_model import BoxEntry


ESCALA = 30


def _bloco(largura, altura):
    return BoxEntry("", 0, 0, largura, altura)


# ----------------------------------------------------------------------
# A peneira: o que se abre e o que não se abre
# ----------------------------------------------------------------------

def test_a_tabela_do_nunn_passa_a_ser_candidata():
    """1342×1099 é a medida real, e razão 1,22 é o que ficava no vão."""
    tabela = _bloco(1342, 1099)
    assert trama.candidatos([tabela], ESCALA) == [tabela]


def test_o_tabuleiro_continua_fora():
    """Ler dentro de um tabuleiro daria uma caixa por casa — medido, ~450."""
    for larg, alt in ((550, 546), (549, 549), (578, 579), (613, 611)):
        assert trama.candidatos([_bloco(larg, alt)], ESCALA) == [], \
            f"o tabuleiro {larg}x{alt} foi aberto"


def test_a_regua_e_a_mesma_do_diagrama():
    """
    **O caso do meio deixa de existir por construção.** Com duas constantes
    soltas volta a haver bloco que não é quadrado o bastante para virar diagrama
    e é quadrado demais para ser lido — que era exatamente a tabela a 1,22.
    """
    limiar = diagrama.TOLERANCIA_QUADRADO
    quase = _bloco(int(100 * limiar) - 2, 100)      # logo abaixo: é tabuleiro
    passa = _bloco(int(100 * limiar) + 2, 100)      # logo acima: abre

    assert trama.candidatos([quase], 1) == []
    assert trama.candidatos([passa], 1) == [passa]


def test_a_tabela_mais_alta_que_larga_tambem_abre():
    """A régua de antes só olhava para bloco mais largo que alto."""
    em_pe = _bloco(1099, 1342)
    assert trama.candidatos([em_pe], ESCALA) == [em_pe]


def test_o_painel_largo_da_f11_continua_candidato():
    """1049×390, o caso que abriu a F11 — a régua nova não pode perdê-lo."""
    painel = _bloco(1049, 390)
    assert trama.candidatos([painel], ESCALA) == [painel]


# ----------------------------------------------------------------------
# O teto: caractere demais para ser caractere
# ----------------------------------------------------------------------

def _pagina_de_ruido(largura=800, altura=600, passo=3):
    """
    Uma fotografia, do ponto de vista do pipeline: grão por toda parte.

    É a capa do *Chess Evolution 1*, que rende 40.382 "glifos" porque a escala
    de texto da página desaba para 2 px — e com ela `ALTURA_GLIFO` aceita como
    caractere qualquer coisa entre 0,7 e 5 px.

    **Os grãos têm de estar separados**, como no meio-tom: ruído aleatório denso
    se solda num blob só, que é alto demais para passar por glifo e não
    reproduz o defeito.
    """
    img = np.full((altura, largura), 245, np.uint8)
    img[::passo, ::passo] = 60
    return img


def test_bloco_que_rende_glifo_demais_fica_como_estava():
    img = _pagina_de_ruido()
    bloco = _bloco(800, 600)
    dentro = trama.glifos(trama.binarizar_bloco(img, bloco, 2), bloco, 2)
    assert len(dentro) > trama.MAX_GLIFOS, \
        "a montagem não reproduz a página-fotografia"

    novas, lidos = trama.aplicar(img, [bloco], 2)
    assert lidos == [], "a fotografia foi lida como se fosse texto"
    assert novas == [bloco], "o bloco tinha de ficar como estava"


def test_o_teto_esta_acima_do_maior_caso_bom():
    """71 no painel da F11, 276 na tabela do Nunn, 392 na capa do Aagaard."""
    assert trama.MAX_GLIFOS > 392 * 4


def test_o_minimo_continua_valendo():
    """Bloco sem texto dentro continua intocado — sombra, filete, moldura."""
    branco = np.full((600, 800), 245, np.uint8)
    bloco = _bloco(800, 600)
    novas, lidos = trama.aplicar(branco, [bloco], ESCALA)
    assert lidos == []
    assert novas == [bloco]


# ----------------------------------------------------------------------
# De ponta a ponta
# ----------------------------------------------------------------------

def _pagina_com_tabela():
    """
    Texto normal e, embaixo, uma tabela com moldura fechada.

    A moldura é o que faz o defeito: fechada, ela vira um contorno só e o que
    está dentro não chega a existir como box.
    """
    img = np.full((900, 900), 245, np.uint8)
    for k in range(4):
        cv2.putText(img, "ABCDEFGH", (40, 60 + k * 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, 15, 2)
    # a moldura, e as divisórias
    cv2.rectangle(img, (60, 300), (840, 860), 15, 3)
    cv2.line(img, (450, 300), (450, 860), 15, 3)
    for y in (400, 500, 600, 700, 780):
        cv2.line(img, (60, y), (840, y), 15, 3)
    for linha, y in enumerate((370, 470, 570, 670, 750, 840)):
        cv2.putText(img, "Win", (90, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 15, 2)
        cv2.putText(img, "Draw", (480, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 15, 2)
    return img


def test_a_tabela_deixa_de_sumir_da_pagina():
    from core.services.box_service import BoxService
    from PIL import Image

    img = _pagina_com_tabela()
    boxes = BoxService.generate_boxes_opencv(Image.fromarray(img))
    dentro = [b for b in boxes
              if 300 < (b.y1 + b.y2) / 2 < 860 and 60 < (b.x1 + b.x2) / 2 < 840]
    assert len(dentro) >= 10, \
        f"o conteúdo da tabela continua engolido pela moldura: {len(dentro)}"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
