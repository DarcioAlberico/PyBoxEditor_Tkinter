"""
O negrito do texto impresso, medido no traço (F105).

**O que distingue negrito de redondo é a espessura do traço, e nada mais.** O
desenho é o mesmo, o corpo é o mesmo, a altura é a mesma — o que muda é quanta
tinta o traço tem. Medido nas dez famílias que o Windows traz, nos três corpos
que estes livros usam, o traço do negrito é de 1,22 a 1,91 vezes o do redondo.

O problema é que espessura em pixels não diz nada sozinha: um `m` de corpo 12 é
mais espesso que um `m` de corpo 9 na mesma família e no mesmo peso. É preciso
uma régua, e ela tem duas normalizações encaixadas:

    espessura   a largura do traço dividida pela altura da tinta do glifo.
                Tira o corpo: é uma razão dentro do próprio glifo.

    relativo    a espessura dividida pela **daquele mesmo caractere** no resto
                do livro. Tira o desenho: um `.` é grosso e um `l` é fino, e
                comparar os dois nunca disse nada sobre peso.

A segunda é a que faz a medida funcionar, e ela só existe porque este projeto
**lê o caractere antes de medi-lo**. Medido nas 40 páginas do Dvoretsky contra
o que a camada de texto dele declara (`TimesNewRomanPS-BoldMT` ×
`TimesNewRomanPSMT`), palavra a palavra:

    régua                                        acerta   falso
    espessura ÷ mediana da página                 63,1%   0,04%
    espessura ÷ quantil da página                 92,0%   0,06%
    espessura ÷ mediana do mesmo caractere        94,8%   0,16%
    espessura ÷ quantil do mesmo caractere        97,1%   0,22%

**A decisão é por palavra, e não por glifo.** Glifo a glifo a mesma régua acerta
83,8% com 1,35% de alarme falso, e o que ela perde é a pontuação: 31,3% dos
sinais, contra 95,4% das letras e 99,7% dos dígitos. Um `.` tem meia dúzia de
pixels de altura, e meio pixel de erro na medida dele é 10% de espessura. A
mediana dos glifos da palavra passa por cima disso, e é o que a tipografia diz
de todo modo: negrito é propriedade de trecho, não de letra.

Ponta a ponta — o que o livro exportado traria contra o que o PDF declara —, a
régua desta fase acerta **98,5%** dos trechos em negrito e marca 0,22% dos
redondos. `medir_negrito.py` refaz todas as tabelas.
"""

from array import array
from collections import defaultdict
from math import isnan, nan
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import cv2
import numpy as np

from core import preprocess

#: Pixels de tinta abaixo dos quais o recorte não tem o que medir.
#:
#: Não é filtro de qualidade: é o piso em que a transformada de distância deixa
#: de ter miolo. Num borrão de três pixels toda distância é 1, e a espessura sai
#: 2 — o dobro da de um traço de verdade, e do lado errado da régua.
MINIMO_DE_TINTA = 8

#: O quantil que estima o peso **redondo** de cada caractere.
#:
#: **Não é a mediana, e a diferença vale 2,3 pontos de acerto** (97,1% contra
#: 94,8%, palavra a palavra no Dvoretsky). A mediana supõe que a maior parte das
#: aparições daquele caractere está no peso normal, e num livro de xadrez isso é
#: falso para meia dúzia de classes: o dígito mora na notação, a notação é
#: negrito, e a mediana de `4` neste livro **é** o peso negrito. Um quantil
#: baixo pega o redondo mesmo quando ele é minoria, e não estraga o caso comum:
#: onde o caractere é quase todo redondo, o p25 e a mediana medem a mesma coisa.
QUANTIL_DO_REDONDO = 25

#: Quanto o traço da palavra precisa passar do peso normal do livro.
#:
#: **O gabarito não escolhe este número: ele diz que qualquer número numa faixa
#: larga serve.** Varrido nas 9.338 palavras das 40 páginas do Dvoretsky, o
#: alarme falso é o mesmo 0,22% de 1,02 a 1,20 — as palavras redondas
#: simplesmente não ocupam essa faixa —, e o acerto cai devagar:
#:
#:     limiar   acerta   falso
#:      1,00     98,0%  22,04%   (a régua desligada)
#:      1,02     98,0%   0,22%
#:      1,15     97,1%   0,22%
#:      1,20     96,6%   0,22%
#:      1,30     92,9%   0,21%
#:
#: **Quem o escolhe são as duas populações e o desenho das fontes.** Em pesos
#: redondos, a palavra redonda tem percentil 99 em **1,006** e a negrito tem
#: percentil 1 em **1,167** (mediana 1,518): o vão entre as duas é onde o limiar
#: mora. E do lado de cima ele tem de caber sob a razão que as fontes desenham —
#: negrito ÷ redondo, medida caractere a caractere nas dez famílias do Windows,
#: vai de **1,22** (Constantia a 30 px, que é a nota de rodapé) a 1,91.
#:
#: 1,15 está acima de 99 em cada 100 palavras redondas e abaixo da mais
#: apertada das famílias. O 0,22% que sobra não é limiar nenhum: são o `B?` e o
#: `W?` que o Dvoretsky imprime em Arial no meio de uma página em Times, e
#: nenhum valor os tira — ver `marcar`.
LIMIAR = 1.15


#: Glifos medidos que uma palavra precisa para decidir o próprio peso.
#:
#: **Uma palavra de um glifo só não tem medida que preste**, e é a mesma razão
#: pela qual a decisão é por palavra e não por caractere — só que aqui não há
#: mediana que salve. Medido no Dvoretsky, com a régua solta em toda palavra:
#:
#:     glifos na palavra   quantas   acerta   falso
#:      1                    1.261    29,2%  11,48%
#:      2                    1.081    87,7%   1,67%
#:      3 ou mais            6.996    99,7%   0,02%
#:
#: O que sobra de fora são o travessão entre os nomes dos jogadores e o `!` do
#: lance — que *são* negrito no impresso — e a fileira de coordenadas do
#: diagrama, `a b c d e f g h`, que não é. Os dois primeiros se resolvem por
#: vizinhança; ver `_decidir`.
MINIMO_DE_GLIFOS = 2


def espessura(recorte: np.ndarray) -> Optional[float]:
    """
    A espessura do traço deste glifo, em alturas dele — `None` se não dá medir.

    A transformada de distância dá, em cada pixel de tinta, o quanto falta para
    a borda; num traço de largura *w* ela vale 1 na borda e cresce até o meio, e
    a média sobre o traço é `w/4 + 1/2`. Daí a conta: `2 × média − 1` vale
    exatamente `w/2`, e a divisão pela altura da tinta tira o corpo. Que a
    medida seja meia largura e não a largura não muda nada: o que a régua
    compara são razões entre duas destas medidas.

    **O `− 1` não é ajuste fino: sem ele a medida cresce quando o corpo
    encolhe.** O meio pixel que a transformada soma em cada borda pesa muito num
    glifo pequeno e pouco num grande, e uma nota de rodapé mediria mais espessa
    que a prosa em negrito da mesma página. Medido, ele vale 0,9 ponto de acerto
    ponta a ponta (98,5% contra 97,6%) e mais que dobra a folga do limiar: a
    razão negrito ÷ redondo da família mais apertada sobe de 1,13 para 1,22.

    É a média sobre a tinta toda, e não o máximo: o máximo mede a junção do `x`,
    que é grossa em qualquer peso.

    O denominador é a altura **da tinta**, e não a do box: o box do `.` tem a
    altura da linha em quem o desenhou por PDF e a do ponto em quem o segmentou
    da imagem, e as duas medidas têm de ser a mesma coisa.
    """
    if recorte.size == 0:
        return None
    tinta = preprocess.binarize(recorte, "otsu")
    ys, _xs = np.nonzero(tinta)
    if len(ys) < MINIMO_DE_TINTA:
        return None
    # **O recorte todo preto não tem traço**, e não é hipótese: um pedaço de
    # tarja ou de moldura que sobre como box vem assim. Sem fundo não há borda
    # de onde medir distância, e o OpenCV devolve `FLT_MAX` em todo pixel — a
    # média estoura e a "espessura" sairia astronômica.
    if len(ys) == tinta.size:
        return None
    altura = int(ys.max() - ys.min()) + 1
    dentro = cv2.distanceTransform(tinta, cv2.DIST_L2, 5)[tinta > 0]
    return (2.0 * float(dentro.mean()) - 1.0) / altura


def vetor(espessuras: Sequence[Optional[float]]) -> array:
    """
    As espessuras de uma linha como vetor de 4 bytes, com `nan` no que faltou.

    **É `array` e não lista porque isto acompanha o livro inteiro na memória.**
    São 2,3 milhões de caracteres num livro de 900 páginas: 9 MB aqui, contra
    ~60 MB numa lista de `float` do Python. O que sobra dessa conta são os PNG
    dos diagramas, que já custam mais.
    """
    return array("f", [nan if e is None else e for e in espessuras])


def referencia(amostras: Mapping[str, Sequence[float]]) -> Dict[str, float]:
    """
    {caractere: espessura dele no peso redondo}, do material medido.

    Ver `QUANTIL_DO_REDONDO` para por que não é a mediana.
    """
    return {ch: float(np.percentile(v, QUANTIL_DO_REDONDO))
            for ch, v in amostras.items() if v}


def relativo(palavra: Sequence[Tuple[str, float]],
             ref: Mapping[str, float]) -> Optional[float]:
    """
    O peso desta palavra, em pesos redondos — `None` se nenhum glifo serve.

    `palavra` é `(caractere, espessura)` glifo a glifo. Mediana e não média: uma
    palavra de prosa que encoste num respingo, ou um `l` que tenha vindo colado
    ao vizinho, não pode arrastar o trecho inteiro para o negrito.
    """
    razoes = [e / ref[ch] for ch, e in palavra
              if ch in ref and ref[ch] > 0 and not isnan(e)]
    if not razoes:
        return None
    return float(np.median(razoes))


def escala(pesos: Sequence[float]) -> float:
    """
    O peso normal deste material: a mediana das palavras.

    **Supõe que a maior parte do livro é redonda**, e é a suposição que a régua
    inteira faz. No Dvoretsky o negrito é 12,8% das palavras; um material em que
    ele fosse a maioria sairia com a marcação invertida — e nesse material não
    haveria como saber, olhando só o traço, qual dos dois pesos é o texto.
    """
    return float(np.median(pesos)) if len(pesos) else 1.0


def e_negrito(peso: float, normal: float, limiar: float = LIMIAR) -> bool:
    """A regra, num lugar só — ver `LIMIAR`."""
    return normal > 0 and peso > limiar * normal


def _palavras(texto: str) -> List[Tuple[int, int]]:
    """(início, fim) de cada corrida sem espaço."""
    saida, inicio = [], None
    for i, ch in enumerate(texto):
        if ch.isspace():
            if inicio is not None:
                saida.append((inicio, i))
                inicio = None
        elif inicio is None:
            inicio = i
    if inicio is not None:
        saida.append((inicio, len(texto)))
    return saida


def _juntar(trechos: Sequence[Tuple[int, int]], texto: str
            ) -> List[Tuple[int, int]]:
    """
    Palavras negrito vizinhas viram um trecho só, espaço incluído.

    Duas palavras seguidas em negrito são um `<strong>` de duas palavras, e não
    dois `<strong>` grudados: no EPUB a diferença é invisível, mas no DOCX cada
    trecho é um `run`, e um `run` por palavra é o que faz o Word abrir um
    arquivo de 900 páginas com dezenas de milhares de runs a mais.
    """
    saida: List[Tuple[int, int]] = []
    for inicio, fim in trechos:
        if saida and texto[saida[-1][1]:inicio].strip() == "":
            saida[-1] = (saida[-1][0], fim)
        else:
            saida.append((inicio, fim))
    return saida


def _decidir(texto: str, palavras: Sequence[Tuple[int, int, list]],
             ref: Mapping[str, float], normal: float, limiar: float
             ) -> List[Tuple[int, int]]:
    """
    Quais palavras deste parágrafo saem em negrito.

    **A palavra curta demais para se medir herda dos vizinhos, e só ela**
    (ver `MINIMO_DE_GLIFOS`). É o travessão de `Nimzovitch — Tarrasch` e o `!`
    de `1.♖h1 !`, que estão impressos no mesmo peso do que vem antes e depois e
    não têm glifo que chegue para provar isso sozinhos.

    **A herança não vale para palavra alfanumérica**, e a diferença é o artigo:
    a fileira de coordenadas do diagrama e o `a` da prosa são palavras de uma
    letra, e um `a` colado a um lance viraria negrito toda vez que o livro
    dissesse "played 1.e4 a strong move". Medido no Dvoretsky, herdar em toda
    palavra curta vale 0,6 ponto de acerto (98,2% contra 97,6%) e não custa
    alarme falso nenhum **naquele livro** — mas ali o caso do artigo não chega a
    aparecer, e é ele que decide.
    """
    firmes, pesos = [], []
    for inicio, fim, glifos in palavras:
        firme = len(glifos) >= MINIMO_DE_GLIFOS
        peso = relativo(glifos, ref) if firme else None
        firmes.append(firme and peso is not None)
        pesos.append(peso)

    forte = [f and e_negrito(p, normal, limiar)
             for f, p in zip(firmes, pesos)]
    for i, (inicio, fim, _glifos) in enumerate(palavras):
        if firmes[i] or any(c.isalnum() for c in texto[inicio:fim]):
            continue
        antes = next((forte[j] for j in range(i - 1, -1, -1) if firmes[j]), False)
        depois = next((forte[j] for j in range(i + 1, len(palavras))
                       if firmes[j]), False)
        forte[i] = antes or depois

    return _juntar([(inicio, fim) for (inicio, fim, _g), f
                    in zip(palavras, forte) if f], texto)


def marcar(paginas, *, limiar: float = LIMIAR) -> int:
    """
    Preenche o `negrito` dos parágrafos destas páginas. Devolve quantos trechos.

    **A referência é o material que se passa aqui**, e é por isso que a função
    recebe páginas em vez de uma só: quanto mais texto, melhor o peso redondo de
    cada caractere é estimado. Medido no Dvoretsky, palavra a palavra: com a
    página por referência acerta 90,2% (0,09% de falso), com as 40 páginas,
    96,7% (0,37%). O `livro.extrair_pagina` marca com a página que acabou de
    ler, e o `livro.extrair` **remarca** o livro inteiro no fim — a marcação é
    idempotente, e a segunda passada é a que vale.

    **Título não recebe marca.** Ele já sai `<h2>` no EPUB e `Heading 2` no
    DOCX, e os dois desenham negrito por conta própria; um `<strong>` dentro do
    `<h2>` não muda um pixel e ainda faria o cabeçalho de um livro inteiro
    carregar marcação que ninguém pediu.

    **O que esta régua não sabe é família.** Ela mede peso, e uma segunda
    família de traço mais gordo passa por negrito: no Dvoretsky, o `B?` e o `W?`
    que marcam de quem é a vez estão em Arial dentro de uma página em Times, e
    saem marcados — 12 das 18 palavras que ela erra naquele livro. Distinguir os
    dois exigiria reconhecer a fonte, que é outra pergunta.
    """
    from core.livro import Paragrafo

    alvos = [b for p in paginas for b in p.blocos
             if isinstance(b, Paragrafo) and not b.titulo
             and b.pesos is not None and len(b.pesos) == len(b.texto)]
    for p in alvos:
        p.negrito = []

    amostras: Dict[str, List[float]] = defaultdict(list)
    por_paragrafo = []
    for p in alvos:
        palavras = []
        for inicio, fim in _palavras(p.texto):
            glifos = [(ch, e) for ch, e in
                      zip(p.texto[inicio:fim], p.pesos[inicio:fim])
                      if not isnan(e)]
            palavras.append((inicio, fim, glifos))
            for ch, e in glifos:
                amostras[ch].append(e)
        por_paragrafo.append((p, palavras))

    ref = referencia(amostras)
    # O peso normal sai só das palavras que decidem por si (`MINIMO_DE_GLIFOS`):
    # a mediana das outras é ruído, e é ruído que puxa para cima — a palavra de
    # um glifo é quase sempre pontuação.
    firmes = [peso for _p, palavras in por_paragrafo
              for inicio, fim, glifos in palavras
              if len(glifos) >= MINIMO_DE_GLIFOS
              for peso in [relativo(glifos, ref)] if peso is not None]
    normal = escala(firmes)

    total = 0
    for p, palavras in por_paragrafo:
        p.negrito = _decidir(p.texto, palavras, ref, normal, limiar)
        total += len(p.negrito)
    return total
