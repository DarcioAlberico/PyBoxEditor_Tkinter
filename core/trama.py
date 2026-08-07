r"""
Texto sobre trama de meio-tom (F11).

O quadro de pontuação que fecha cada capítulo do Yusupov é um painel chapado, e
o escaneamento o devolve como uma nuvem de pontos. O estrago é em dois tempos, e
o segundo é o que apaga o texto:

1. **A trama envenena toda régua relativa.** Medido na página 18 do *Chess
   Evolution 1*: 6.765 contornos, 95,8% deles de 6x6 px ou menos, e a mediana
   das alturas em **2 px**. Com essa mediana, `descartar_blocos_nao_texto` joga
   fora tudo acima de 8 px — isto é, os caracteres. Quem conserta é
   `preprocess.escala_de_texto`, que pesa por tinta.
2. **A trama solda o texto ao fundo.** Os pontos encostam nas letras e as letras
   umas nas outras: o painel inteiro sai como **um** contorno de 1049x390, e o
   que estava escrito dentro dele não chega a existir como box.

Este módulo trata o segundo. O primeiro está no `preprocess`.

## Olhar dentro do bloco antes de jogá-lo fora

É a lição da F1.8 outra vez: lá, o bloco grande descartado como "não é texto"
guardava o diagrama, e a F7.1 só precisou recolher o que era jogado fora. Aqui o
bloco guarda uma linha de texto.

**Rebinarizar o recorte é o que desfaz a solda**, e o motivo é o histograma: na
página inteira o papel branco domina e o Otsu global corta em ~50, abaixo da
trama — que vira tinta e gruda em tudo. Dentro do painel o papel some da conta e
sobram duas populações, trama (tom ~99) e texto (tom ~5); ali o Otsu corta em
**143**, acima da trama. Medido no painel da página 18: 71 componentes com
tamanho de caractere onde antes havia zero.

É a mesma manobra da F10 — bloco cheio, Otsu local, o conteúdo decide —, com a
polaridade normal em vez de invertida.

## O que impede o diagrama de virar 32 boxes de peça

Um tabuleiro também é bloco grande de tinta esparsa, e ler dentro dele daria uma
caixa por peça — exatamente o que a F1.8 mediu não acontecer e não deve passar a
acontecer. A peneira é do domínio e tem margem larga: **tabuleiro é quadrado.**
Medido nas páginas 30 e 31, os seis diagramas medem 578x579, 579x579, 580x584 —
proporção 1,00 a 1,01. O painel de pontuação mede 1049x390, proporção 2,69.

A cobertura por células diria o mesmo com margem estreita (99,9% no painel
contra 82%–91% nos diagramas) e não é usada por isso.
"""

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from core.box_model import BoxEntry


#: Quantas alturas de caractere o bloco precisa ter, nos dois eixos, para valer
#: a pena olhar dentro. Abaixo disso é palavra grande, não painel.
TAMANHO_MINIMO = 4.0

#: O bloco tem de ser bem mais largo que alto. **É o que separa painel de
#: tabuleiro** (1,00–1,01 contra 2,69 de proporção, medido), e o valor fica no
#: meio do vão de propósito: nada no material cai entre 1,3 e 2,6.
RAZAO_MINIMA = 1.5

#: Faixa de altura, em escalas de texto da página, para um componente de dentro
#: do bloco ser caractere. Larga porque o painel mistura corpo grande ("19") com
#: corpo pequeno ("Maximum number of points is 22").
ALTURA_GLIFO = (0.35, 2.5)

#: Quantos caracteres fazem o bloco valer a substituição. Três é o mesmo mínimo
#: da F10, e pelo mesmo motivo: para *decidir*, um punhado basta.
MIN_GLIFOS = 3


def candidatos(boxes: Sequence[BoxEntry], escala: int) -> List[BoxEntry]:
    """
    Blocos grandes, largos — os que valem uma segunda olhada.

    Nada aqui afirma que o bloco tem texto: quem afirma é `aplicar`, depois de
    reler o recorte.
    """
    if escala <= 0:
        return []
    piso = escala * TAMANHO_MINIMO
    return [b for b in boxes
            if b.height >= piso and b.width >= piso
            and b.width >= b.height * RAZAO_MINIMA]


def binarizar_bloco(cinza: np.ndarray, bloco: BoxEntry) -> np.ndarray:
    """
    O recorte binarizado **com o limiar dele**, não com o da página.

    Otsu local, tinta em branco — a mesma convenção de `preprocess.binarize`.
    """
    recorte = cinza[bloco.y1:bloco.y2, bloco.x1:bloco.x2]
    if recorte.size == 0:
        return np.zeros((0, 0), np.uint8)
    if recorte.ndim == 3:
        recorte = cv2.cvtColor(recorte, cv2.COLOR_RGB2GRAY)
    _, local = cv2.threshold(recorte, 0, 255,
                             cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return local


def glifos(local: np.ndarray, bloco: BoxEntry, escala: int) -> List[BoxEntry]:
    """
    Os componentes do recorte que têm tamanho de caractere, em coordenadas da
    página.

    **A régua é a da página, e não a do bloco** — ao contrário da F10, onde a
    tarja tem a altura de uma linha e serve de escala. Aqui o bloco tem 390 px
    para texto de 30, e medir contra ele recusaria tudo.

    O que não tem tamanho de caractere fica de fora e é a própria trama: dos
    5.168 componentes do painel da página 18, 71 são caractere.
    """
    if local.size == 0 or escala <= 0:
        return []

    piso, teto = escala * ALTURA_GLIFO[0], escala * ALTURA_GLIFO[1]
    contornos, _ = cv2.findContours(local, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    saida = []
    for c in contornos:
        x, y, w, h = cv2.boundingRect(c)
        if not (piso <= h <= teto) or w > teto * 3:
            continue
        saida.append(BoxEntry("", bloco.x1 + x, bloco.y1 + y,
                              bloco.x1 + x + w, bloco.y1 + y + h))
    return saida


def aplicar(cinza: np.ndarray, boxes: Sequence[BoxEntry], escala: int
            ) -> Tuple[List[BoxEntry], List[BoxEntry]]:
    """
    Troca cada bloco de trama pelos caracteres que houver dentro dele.

    Devolve `(boxes, blocos lidos)`. Bloco que não rende caractere nenhum fica
    como estava — e é o que acontece com sombra, filete e moldura, que também
    são blocos largos.

    **Seguro por construção:** só mexe em bloco que o `descartar_blocos_nao_texto`
    ia jogar fora de qualquer jeito. O pior caso é continuar sem o texto, que é
    o estado anterior a esta fase.

    Devolve a lista ordenada por (y1, x1), pela mesma razão da F10:
    `merge_vertical_boxes` aceita distância vertical negativa, e uma lista fora
    de ordem faz o merge atravessar a página.
    """
    lidos: List[BoxEntry] = []
    novas = list(boxes)

    for b in candidatos(boxes, escala):
        dentro = glifos(binarizar_bloco(cinza, b), b, escala)
        if len(dentro) < MIN_GLIFOS:
            continue
        novas = [o for o in novas if o is not b] + dentro
        lidos.append(b)

    if lidos:
        novas.sort(key=lambda o: (o.y1, o.x1))
    return novas, lidos
