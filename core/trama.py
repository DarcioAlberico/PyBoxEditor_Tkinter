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

#: Quanto o bloco tem de fugir do quadrado para valer uma olhada dentro. Vem do
#: `diagrama.TOLERANCIA_QUADRADO`, importado e não copiado — ver `candidatos`.
#:
#: **Era 1,5, e a tabela caía no vão** (F71). O valor foi posto "no meio do vão
#: de propósito", com a observação de que nada no material caía entre 1,3 e 2,6.
#: Caía: a tabela de finais da página 236 do Nunn mede 1342×1099, razão **1,22**.
#: Moldura fechada, `RETR_EXTERNAL`, e as 276 caixas de caractere de dentro dela
#: sumiam do livro sem aviso nenhum — não saíam fora de ordem, não saíam.
#:
#: E a régua deixa de ser só "mais largo que alto": uma tabela pode ser mais
#: alta que larga, e a de antes nem olhava para ela.

#: Faixa de altura, em escalas de texto da página, para um componente de dentro
#: do bloco ser caractere. Larga porque o painel mistura corpo grande ("19") com
#: corpo pequeno ("Maximum number of points is 22").
ALTURA_GLIFO = (0.35, 2.5)

#: Quantos caracteres fazem o bloco valer a substituição. Três é o mesmo mínimo
#: da F10, e pelo mesmo motivo: para *decidir*, um punhado basta.
MIN_GLIFOS = 3

#: E quantos são caracteres demais para serem caractere (F71).
#:
#: **A página que é uma fotografia tem escala de texto degenerada**, e é isso
#: que fabrica o número. Medida a capa do *Chess Evolution 1*,
#: `preprocess.escala_de_texto` devolve **2 px** — não há texto na página para
#: pesar —, e com ela `ALTURA_GLIFO` aceita como caractere qualquer grão de
#: 0,7 a 5 px: o bloco rende **40.382** "glifos" e a página sai de 1 box para
#: 24 mil. A régua da capacidade não pega isso, e por construção: com escala de
#: 2 px cabem 1,4 milhão de caracteres na capa, e 40 mil parecem pouco.
#:
#: O vão está na contagem, e é largo — 71 no painel da F11, 276 na tabela do
#: Nunn e 392 na capa do Aagaard, contra 40.382. O teto fica 5× acima do maior
#: caso bom e 20× abaixo do único caso ruim.
MAX_GLIFOS = 2000


def candidatos(boxes: Sequence[BoxEntry], escala: int) -> List[BoxEntry]:
    """
    Blocos grandes, largos — os que valem uma segunda olhada.

    Nada aqui afirma que o bloco tem texto: quem afirma é `aplicar`, depois de
    reler o recorte.

    **A peneira é o complemento exato da do `diagrama`** (F71). Lá, "é
    tabuleiro" é `razão <= TOLERANCIA_QUADRADO`; aqui se abre o que sobra. Ter
    as duas presas à mesma constante é o que impede o caso do meio — um bloco
    que não é quadrado o bastante para virar diagrama e é quadrado demais para
    ser lido, que era exatamente a tabela do Nunn a 1,22.

    O import é tardio: quem só quer `candidatos` não precisa carregar o
    `python-chess` que o `diagrama` traz atrás.
    """
    from core import diagrama

    if escala <= 0:
        return []
    piso = escala * TAMANHO_MINIMO
    return [b for b in boxes
            if b.height >= piso and b.width >= piso
            and max(b.width / max(1, b.height),
                    b.height / max(1, b.width)) > diagrama.TOLERANCIA_QUADRADO]


#: Quanto se tira de cada lado do recorte antes de olhar dentro, em escalas de
#: texto (F71).
#:
#: **A moldura fechada reaparece dentro do próprio recorte.** Recortar o bloco
#: pelo seu retângulo traz a borda junto, e ali dentro ela é de novo o contorno
#: externo: o `RETR_EXTERNAL` devolve a moldura, e o conteúdo continua sendo
#: filho de alguém. Na tabela do Nunn o defeito não aparece porque o scan quebra
#: a borda em pedaços — numa moldura que fecha de verdade, como a de um PDF
#: vetorial, ele sobreviveria à própria correção. Medido na montagem do
#: `test_f71`: 0 glifos com a borda dentro, 12 sem ela.
MARGEM_DA_MOLDURA = 0.25


def _margem(escala: int) -> int:
    return max(2, int(escala * MARGEM_DA_MOLDURA))


def binarizar_bloco(cinza: np.ndarray, bloco: BoxEntry,
                    escala: int = 0) -> np.ndarray:
    """
    O recorte binarizado **com o limiar dele**, não com o da página.

    Otsu local, tinta em branco — a mesma convenção de `preprocess.binarize`.

    Vem sem a própria borda: ver `MARGEM_DA_MOLDURA`. Quem chama tem de passar
    a mesma `escala` ao `glifos`, que é quem devolve a margem às coordenadas.
    """
    m = _margem(escala)
    recorte = cinza[bloco.y1 + m:bloco.y2 - m, bloco.x1 + m:bloco.x2 - m]
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
    # A mesma margem que o `binarizar_bloco` tirou, devolvida às coordenadas.
    m = _margem(escala)
    saida = []
    for c in contornos:
        x, y, w, h = cv2.boundingRect(c)
        if not (piso <= h <= teto) or w > teto * 3:
            continue
        saida.append(BoxEntry("", bloco.x1 + m + x, bloco.y1 + m + y,
                              bloco.x1 + m + x + w, bloco.y1 + m + y + h))
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
        dentro = glifos(binarizar_bloco(cinza, b, escala), b, escala)
        if not MIN_GLIFOS <= len(dentro) <= MAX_GLIFOS:
            continue
        # A marca é o que sobra do bloco: a moldura some aqui, e sem ela nada na
        # página diria onde estava a tabela (F72). Quem decide se aquilo vira
        # `<table>` é a estrutura, não a marca.
        for g in dentro:
            g.moldura = True
        novas = [o for o in novas if o is not b] + dentro
        lidos.append(b)

    if lidos:
        novas.sort(key=lambda o: (o.y1, o.x1))
    return novas, lidos
