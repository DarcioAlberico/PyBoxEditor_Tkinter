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

E a terceira vez (2026-11-07): a fila de cabeçalho da tabela era lida pela
abertura do corpo e engolida pelo merge vertical, que devolvia os glifos ao
pedaço da moldura em que estavam — `_pedacos_da_moldura`.

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


# ----------------------------------------------------------------------
# A célula fechada (página 236 do Nunn, segunda vez)
# ----------------------------------------------------------------------

def test_o_glifo_dentro_da_celula_fechada_sai():
    """
    Dentro da tabela cada célula é um retângulo fechado pelas réguas, e com
    `RETR_EXTERNAL` o que está dentro dele era contorno filho e não saía: a
    coluna do meio da tabela vinha vazia em quatro das seis filas. O
    caractere não toca a régua, então é componente próprio.
    """
    img = np.full((400, 600), 245, np.uint8)
    # A moldura fechada de uma célula, e um glifo do tamanho de um caractere
    # dentro dela, sem tocar a régua.
    cv2.rectangle(img, (100, 100), (400, 300), 0, 3)
    cv2.rectangle(img, (200, 180), (220, 210), 0, -1)
    bloco = _bloco(600, 400)
    dentro = trama.glifos(trama.binarizar_bloco(img, bloco, ESCALA), bloco, ESCALA)
    assert any(b.x1 <= 200 and b.x2 >= 220 and b.y1 <= 180 and b.y2 >= 210
               for b in dentro), "o glifo de dentro da célula fechada não saiu"
    # E a régua da célula não vira glifo: cai pela altura.
    assert not any(b.y2 - b.y1 > ESCALA * trama.ALTURA_GLIFO[1] for b in dentro)


def test_a_pontuacao_da_celula_passa_pelo_piso():
    """
    Os dois pontos de `W: Win` e as reticências de `1...♖h2!` têm 5 px numa
    escala de 29 — 0,17 —, e o piso de 0,35 os deixava na página, fora da
    tabela, como linhas de `: : :`. O ponto da trama tem 2 px e continua fora.
    """
    escala = 29
    assert escala * trama.ALTURA_GLIFO[0] <= 5
    assert escala * trama.ALTURA_GLIFO[0] > 2


# ----------------------------------------------------------------------
# A fila de cabeçalho (página 237 do Nunn, terceira vez): o pedaço da moldura
# ----------------------------------------------------------------------

def _pagina_com_fila_de_cabecalho():
    """
    Texto normal e uma tabela cuja fila de cabeçalho é um contorno à parte,
    com o centro dentro do retângulo do corpo — é como o scan parte a moldura
    da página 237 do Nunn: a régua da esquerda sobe até o topo e estica o
    retângulo do corpo sobre a fila, mas as réguas da fila não a tocam.
    """
    img = np.full((900, 900), 245, np.uint8)
    for k in range(4):
        cv2.putText(img, "ABCDEFGH", (40, 60 + k * 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, 15, 2)
    # O corpo: moldura fechada, divisória e filas — e a régua da esquerda
    # subindo até o topo da fila de cabeçalho.
    cv2.rectangle(img, (60, 380), (840, 860), 15, 3)
    cv2.line(img, (60, 300), (60, 380), 15, 3)
    cv2.line(img, (450, 380), (450, 860), 15, 3)
    for y in (500, 620, 740):
        cv2.line(img, (60, y), (840, y), 15, 3)
    for y in (470, 590, 710, 830):
        cv2.putText(img, "Win", (90, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 15, 2)
        cv2.putText(img, "Draw", (480, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 15, 2)
    # A fila de cabeçalho: um contorno só, a 10 px da régua da esquerda e a
    # 12 px do corpo, baixo demais para ser candidato.
    cv2.line(img, (72, 300), (840, 300), 15, 3)
    cv2.line(img, (72, 365), (840, 365), 15, 3)
    cv2.line(img, (840, 300), (840, 365), 15, 3)
    cv2.line(img, (450, 300), (450, 365), 15, 3)
    cv2.putText(img, "Wd1", (200, 350), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 15, 2)
    cv2.putText(img, "Wc1", (600, 350), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 15, 2)
    return img


def _na_fila_de_cabecalho(boxes):
    return [b for b in boxes
            if 302 < (b.y1 + b.y2) / 2 < 363 and 74 < (b.x1 + b.x2) / 2 < 838]


def test_o_pedaco_da_moldura_e_o_largo_e_baixo_com_o_centro_dentro():
    """937×91 e 392×91 dentro do corpo de 1340×1098, na escala 29 do Nunn."""
    escala = 29
    corpo = BoxEntry("", 156, 327, 156 + 1340, 327 + 1098)
    esquerda = BoxEntry("", 155, 326, 155 + 937, 326 + 91)
    direita = BoxEntry("", 1100, 326, 1100 + 392, 326 + 91)
    fora = BoxEntry("", 155, 1500, 155 + 937, 1500 + 91)        # abaixo do corpo
    travessao = BoxEntry("", 400, 600, 400 + 4 * escala - 1, 608)  # estreito: fica
    tabuleiro = BoxEntry("", 400, 500, 400 + 578, 500 + 579)     # alto: fica
    pedacos = trama._pedacos_da_moldura(
        corpo, [corpo, esquerda, direita, fora, travessao, tabuleiro], escala)
    assert pedacos == {id(esquerda), id(direita)}


def test_a_regua_do_pedaco_e_a_do_glifo():
    """O pedaço começa exatamente onde `glifos` deixa de devolver o componente."""
    escala = 29
    limite = int(escala * trama.LARGURA_DO_GLIFO)
    corpo = BoxEntry("", 0, 0, 2000, 2000)
    glifo = BoxEntry("", 100, 100, 100 + limite, 130)
    pedaco = BoxEntry("", 100, 100, 100 + limite + 1, 130)
    assert trama._pedacos_da_moldura(corpo, [glifo, pedaco], escala) == {id(pedaco)}

    def componente(largura):
        local = np.zeros((200, 400), np.uint8)
        local[50:80, 10:10 + largura] = 255
        return trama.glifos(local, corpo, escala)

    assert len(componente(limite)) == 1
    assert componente(limite + 1) == []


def test_o_pedaco_nunca_e_candidato():
    """
    Pedaço é mais baixo que o piso de `candidatos`, por construção: nenhum
    bloco do laço de `aplicar` some da lista antes da própria vez.
    """
    escala = 29
    piso = int(escala * trama.TAMANHO_MINIMO)
    corpo = BoxEntry("", 0, 0, 2000, 2000)
    baixo = BoxEntry("", 10, 10, 10 + 937, 10 + piso - 1)
    alto = BoxEntry("", 10, 10, 10 + 937, 10 + piso)
    assert trama._pedacos_da_moldura(corpo, [baixo, alto], escala) == {id(baixo)}
    assert trama.candidatos([baixo, alto], escala) == [alto]


def test_aplicar_consome_o_pedaco_e_poupa_o_vizinho_de_fora():
    img = _pagina_com_fila_de_cabecalho()
    escala = 25
    corpo = BoxEntry("", 58, 298, 842, 862)
    pedaco = BoxEntry("", 70, 298, 842, 367)
    vizinho = BoxEntry("", 70, 880, 842, 895)          # largo e baixo, fora do corpo
    novas, lidos = trama.aplicar(img, [corpo, pedaco, vizinho], escala)
    assert lidos == [corpo]
    assert pedaco not in novas and vizinho in novas
    assert len(_na_fila_de_cabecalho(novas)) >= 6


def test_a_fila_de_cabecalho_sobrevive_ao_merge_e_ao_descarte():
    """
    A abertura do corpo lia a fila de cabeçalho — e o merge vertical devolvia
    os glifos ao pedaço da moldura em que estavam, que o descarte do filete
    jogava fora em seguida. Medido na página 237 do Nunn: 12 glifos lidos,
    0 na página.
    """
    from PIL import Image

    from core.services.box_service import BoxService

    img = _pagina_com_fila_de_cabecalho()
    antes, _th, escala, _cinza = BoxService.boxes_antes_do_descarte(Image.fromarray(img))
    depois = BoxService.descartar_blocos_nao_texto(antes, escala=escala)
    fila = _na_fila_de_cabecalho(depois)
    assert len(fila) >= 6, f"a fila de cabeçalho não chegou ao descarte: {len(fila)}"
    assert all(b.width < escala * trama.LARGURA_DO_GLIFO for b in fila), \
        "o pedaço da moldura da fila continua na página"
    assert all(getattr(b, "moldura", False) for b in fila)
    corpo = [b for b in depois if 382 < (b.y1 + b.y2) / 2 < 858]
    assert len(corpo) >= 20, "o corpo da tabela deixou de ser lido"
