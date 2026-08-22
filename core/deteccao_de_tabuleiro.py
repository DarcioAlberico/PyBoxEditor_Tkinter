"""
O tabuleiro achado sem passar pela segmentação de caracteres (F96).

## Por que existe uma segunda maneira de achar o mesmo tabuleiro

`diagrama.localizar` acha o diagrama entre os contornos que a F1.8 descartou —
é o desenho da F7.1, e ele é bom: recolhe de graça o que outra etapa já pagou.
O preço está em **quem paga essa etapa**. Para ter os contornos é preciso
`boxes_antes_do_descarte`, que binariza, tira trama, aplica negativo, junta
pilhas verticais e funde pingos: todo o aparato de medir caractere, montado
para achar um quadrado.

Quanto custa esse aparato, medido em 24 páginas de cada um de cinco livros
(**antes** do índice espacial que a mesma F96 pôs no `merge_vertical_boxes`):

| livro | mediana | pior página |
|---|---:|---:|
| Dvoretsky | 0,50 s | 0,71 s |
| Nunn | 0,80 s | 1,07 s |
| Darcy Lima | 0,97 s | 1,27 s |
| Aagaard | 1,01 s | 1,64 s |
| **Yusupov** | 0,66 s | **256,54 s** |

A última linha não é o custo de achar tabuleiro: é a página 96 do Yusupov, que
tem 85.903 contornos, e o merge sobre eles levava 250,81 s. Com o índice caiu
para 62,77 s — quatro vezes menos, e ainda longe de tempo de tela.

**E o teto de contornos não resolve, resolve pior.** O `MAX_CONTORNOS_DE_TEXTO`
existe para esse caso e diz "acima disto a página não é de texto". A página 96
é de texto: duas colunas de prosa, um diagrama e um painel de sumário — os
85.903 contornos são a trama do painel. Armar o teto ali troca a espera por
perder a página inteira, texto e diagrama junto.

Este módulo procura o tabuleiro pelo que ele é — um quadrilátero grande, quase
quadrado, com xadrez dentro —, sem passar por caractere nenhum. Nas mesmas
páginas: 0,26 a 0,48 s por página, pior caso 0,82 s. **Na página 96 ele leva
0,76 s e acha o diagrama** — é o caso de uso que justifica ele existir aqui.

## O que ele acrescenta além do custo

**Os quatro cantos, e não o retângulo envolvente.** `localizar` devolve o bbox
do contorno e `ler` recorta esse retângulo. Num diagrama torto o recorte certo
é um losango: o bbox é maior que o tabuleiro por `cos θ + sen θ`, e essa sobra
vira deslocamento acumulado ao dividir por 8.

**A partir de que giro isso importa** — medido num tabuleiro sintético, contando
quantas das 64 casas ainda caem na cor que deveriam (`test_f96`):

| giro | recorte pelo bbox | recorte pelos cantos |
|---:|---:|---:|
| 1° a 3° | 64 | 64 |
| 4° | 62 | **64** |
| 5° | 57 | **64** |
| 6° | 46 | **64** |
| 10° | 23 | **64** |

Ou seja: **até 3° o bbox serve** e a homografia não paga nada, e a partir de 4°
ela é a diferença entre ler o diagrama e ler metade de duas casas por casa. É
o caso do livro digitalizado torto, não o do PDF nativo.

## O que ele **não** faz

Não decide o que está impresso em volta (`ler_rotulos`, `ler_titulo`) nem lê a
posição (`ler`): devolve caixa e recorte na mesma forma que o resto do módulo
`diagrama` já consome, e é lá que a leitura continua.

## Procedência

Portado do visualizador do ChessVisionOFF (fases S-12 a S-71), com três coisas
trocadas para caber aqui, e as três são de conteúdo:

1. **A ordem de leitura é a da casa** (`diagrama.ordem_de_leitura`). O original
   traz a sua, equivalente; duas implementações da mesma ordem divergem com o
   tempo, e o dia em que divergirem o "diagrama 2" da tela deixa de ser o
   `[Diagram "2"]` do PGN — que é o defeito que a F95 corrigiu aqui.
2. **A página pode ser cinza.** O original assume RGB; neste projeto a página
   vem de `get_pixmap(colorspace=csGRAY)` e é 2-D.
3. **A prova do xadrez da F95 entra como peneira opcional**
   (`piso_do_xadrez`). O score de padrão herdado do original mistura xadrez e
   grade num número só, e não foi medido neste acervo;
   `diagrama.pontuacao_de_tabuleiro` foi, com vão de seis vezes entre texto e
   tabuleiro. Ver a medição na F96 do ROADMAP.
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

#: Lado do recorte endireitado, em pixels. 100 px por casa — acima da resolução
#: nativa de quase todo diagrama impresso, então a homografia interpola em vez
#: de jogar detalhe fora.
LADO_DO_RECORTE = 800

#: Teto de tabuleiros por página. Cobre grade 3x3 e 3x4 com folga; quem filtra
#: é o piso de pontuação, não este número.
MAXIMO_DE_TABULEIROS = 12

#: Proporção largura/altura aceita para um quadrilátero ser candidato.
#: Mais folgada que a `TOLERANCIA_QUADRADO` de `diagrama` (1,12) porque aqui o
#: candidato ainda **não** foi endireitado: um tabuleiro digitalizado torto tem
#: bbox retangular e só fica quadrado depois da homografia.
PROPORCAO_MINIMA, PROPORCAO_MAXIMA = 0.62, 1.62

#: Área mínima do candidato, em fração da página. Abaixo disto é ruído.
AREA_MINIMA_DA_PAGINA = 0.004

#: Quanto do bbox precisa estar dentro da página. Um quadrilátero que sai pela
#: borda costuma ser a moldura da página inteira, não diagrama.
VISIVEL_MINIMO = 0.65

#: Sobreposição a partir da qual dois candidatos são o mesmo tabuleiro.
SOBREPOSICAO_DE_REPETIDO = 0.25

#: Piso de pontuação, absoluto e relativo ao melhor candidato da página.
PISO_ABSOLUTO = 0.06
PISO_RELATIVO = 0.25


@dataclass
class Tabuleiro:
    """Um tabuleiro achado: onde está, com que cantos, e quanto se confia nele."""

    caixa: Tuple[int, int, int, int]
    """(x1, y1, x2, y2) em pixels da página — a mesma forma que `diagrama.localizar` devolve."""

    quad: np.ndarray
    """Os quatro cantos em pixels da página, em topo-esq, topo-dir, base-dir, base-esq."""

    pontuacao: float
    """Confiança do detector nesta caixa, em 0..1. **Não** é confiança de leitura."""

    def recorte(self, imagem, lado: int = LADO_DO_RECORTE) -> np.ndarray:
        """O tabuleiro endireitado, pronto para `diagrama.ler`."""
        return endireitar(imagem, self.quad, lado)


def _cinza(imagem) -> np.ndarray:
    """A página em cinza, venha ela em cinza, RGB ou PIL."""
    arr = np.asarray(imagem)
    if arr.ndim == 3:
        return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    return arr


def ordenar_cantos(pontos: np.ndarray) -> np.ndarray:
    """Os quatro cantos em topo-esq, topo-dir, base-dir, base-esq.

    A soma das coordenadas é mínima no canto de cima à esquerda e máxima no de
    baixo à direita; a diferença separa os outros dois. Vale para qualquer
    rotação menor que 45°, que é toda a que um scan de livro tem.
    """
    pts = np.array(pontos, dtype=np.float32).reshape(4, 2)
    soma = pts.sum(axis=1)
    dif = np.diff(pts, axis=1).reshape(-1)

    saida = np.zeros((4, 2), dtype=np.float32)
    saida[0] = pts[np.argmin(soma)]
    saida[1] = pts[np.argmin(dif)]
    saida[2] = pts[np.argmax(soma)]
    saida[3] = pts[np.argmax(dif)]
    return saida


def endireitar(imagem, quad: np.ndarray, lado: int = LADO_DO_RECORTE) -> np.ndarray:
    """O quadrilátero desentortado num quadrado de `lado` px, por homografia.

    É o que `diagrama.ler` não tinha: recortar o bbox de um tabuleiro torto
    deixa a grade 8x8 fora de registro, e a grade fora de registro é o que
    manda a leitura para `TOO_MANY_KINGS` — a casa fica com metade de duas.
    """
    origem = ordenar_cantos(quad)
    destino = np.array([[0, 0], [lado - 1, 0], [lado - 1, lado - 1], [0, lado - 1]],
                       dtype=np.float32)
    matriz = cv2.getPerspectiveTransform(origem, destino)
    return cv2.warpPerspective(np.asarray(imagem), matriz, (lado, lado))


def _sobrepoe(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    """Interseção sobre união de duas caixas `(x1, y1, x2, y2)`."""
    lx = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    ly = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = lx * ly
    uniao = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / max(1, uniao)


def _caixa_do_quad(quad: np.ndarray) -> Tuple[int, int, int, int]:
    xs, ys = quad[:, 0], quad[:, 1]
    return int(np.min(xs)), int(np.min(ys)), int(np.max(xs)), int(np.max(ys))


def _pontuacao_geometrica(quad: np.ndarray, area_da_pagina: float) -> float:
    """Quanto este quadrilátero **parece** um tabuleiro, só pela forma.

    Zero elimina o candidato. O quadrado pesa quase ao cubo (expoente 2,4)
    porque a forma é o sinal barato e confiável: um retângulo 1,5:1 quase nunca
    é tabuleiro, e deixá-lo empatar com um quadrado pela área faria a moldura
    do exercício ganhar do tabuleiro que está dentro dela.
    """
    area = cv2.contourArea(quad.astype(np.float32))
    if area <= 0 or area < area_da_pagina * AREA_MINIMA_DA_PAGINA:
        return 0.0

    _x, _y, largura, altura = cv2.boundingRect(quad.astype(np.int32))
    if altura == 0:
        return 0.0
    proporcao = largura / float(altura)
    if not (PROPORCAO_MINIMA <= proporcao <= PROPORCAO_MAXIMA):
        return 0.0

    tamanho = min(area / area_da_pagina / 0.12, 1.0)
    quadratura = max(0.0, 1.0 - abs(math.log(proporcao)) / math.log(PROPORCAO_MAXIMA))
    return tamanho * (quadratura ** 2.4)


def _visivel(caixa: Tuple[int, int, int, int], forma) -> float:
    """Fração do bbox que cai dentro da página."""
    x1, y1, x2, y2 = caixa
    if x2 <= x1 or y2 <= y1:
        return 0.0
    altura, largura = forma[:2]
    dentro = (max(0, min(largura, x2) - max(0, x1))
              * max(0, min(altura, y2) - max(0, y1)))
    return dentro / float((x2 - x1) * (y2 - y1))


def _pico_periodico(perfil: np.ndarray, periodo: int) -> float:
    """Quanto o perfil tem picos nos múltiplos de `periodo` — as 7 linhas da grade."""
    if perfil.size <= periodo:
        return 0.0
    raio = max(2, periodo // 8)
    picos = []
    for centro in (periodo * i for i in range(1, 8)):
        esquerda, direita = max(0, centro - raio), min(perfil.size, centro + raio + 1)
        if direita > esquerda:
            picos.append(float(np.max(perfil[esquerda:direita])))
    if not picos:
        return 0.0
    base = float(np.percentile(perfil, 55))
    faixa = float(np.percentile(perfil, 90) - base)
    if faixa <= 1e-6:
        return 0.0
    return float(np.clip((np.mean(picos) - base) / faixa, 0.0, 1.0))


def _pontuacao_de_padrao(recorte: np.ndarray) -> float:
    """Xadrez **e** grade, no recorte já endireitado, em 0..1.

    Os dois sinais entram porque nenhum dos dois cobre o acervo sozinho: o
    xadrez enfraquece no diagrama de casa clara com moldura fina, e a grade some
    no de casa hachurada, onde a fronteira entre casas é textura e não traço.
    """
    cinza = _cinza(recorte).astype(np.float32)
    pequeno = cv2.resize(cinza, (160, 160), interpolation=cv2.INTER_AREA)

    medias = pequeno.reshape(8, 20, 8, 20).mean(axis=(1, 3))
    par = (np.indices((8, 8)).sum(axis=0) % 2) == 0
    contraste = abs(float(medias[par].mean()) - float(medias[~par].mean())) / 255.0
    dispersao = (float(medias[par].std()) + float(medias[~par].std())) / (2.0 * 255.0)
    xadrez = float(np.clip(contraste * 2.4 - dispersao * 0.9, 0.0, 1.0))

    gx = np.abs(np.diff(pequeno, axis=1)).mean(axis=0)
    gy = np.abs(np.diff(pequeno, axis=0)).mean(axis=1)
    grade = (_pico_periodico(gx, 20) + _pico_periodico(gy, 20)) / 2.0

    return float(np.clip(0.6 * xadrez + 0.4 * grade, 0.0, 1.0))


def _candidatos(imagem) -> List[Tuple[np.ndarray, float, Tuple[int, int, int, int]]]:
    """Todo quadrilátero da página que passa nas provas de forma, com sua pontuação."""
    cinza = _cinza(imagem)
    borrada = cv2.GaussianBlur(cinza, (5, 5), 0)
    binaria = cv2.adaptiveThreshold(borrada, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY_INV, 41, 8)
    nucleo = np.ones((3, 3), np.uint8)
    # Duas passadas: a moldura fina de alguns livros só fecha depois do
    # fechamento morfológico, e a de outros só sobrevive sem ele.
    passadas = [binaria, cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, nucleo, iterations=1)]

    area_da_pagina = float(cinza.shape[0] * cinza.shape[1])
    crus = []
    for passada in passadas:
        # `RETR_LIST` e não `RETR_EXTERNAL`: é o que acha o tabuleiro impresso
        # dentro de um painel — o caso que a F95 teve de resolver por fora.
        contornos, _ = cv2.findContours(passada, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contorno in contornos:
            if len(contorno) < 4:
                continue
            perimetro = cv2.arcLength(contorno, True)
            if perimetro <= 0:
                continue
            aprox = cv2.approxPolyDP(contorno, 0.02 * perimetro, True)
            if len(aprox) == 4:
                quad = aprox.reshape(4, 2).astype(np.float32)
            else:
                quad = cv2.boxPoints(cv2.minAreaRect(contorno)).astype(np.float32)

            forma = _pontuacao_geometrica(quad, area_da_pagina)
            if forma <= 0:
                continue
            caixa = _caixa_do_quad(quad)
            if _visivel(caixa, cinza.shape) < VISIVEL_MINIMO:
                continue

            padrao = _pontuacao_de_padrao(endireitar(cinza, quad, 320))
            crus.append((quad, float(forma * (0.55 + 0.45 * padrao)), caixa,
                         float(cv2.contourArea(quad.astype(np.float32)))))

    if not crus:
        return []

    # As duas passadas acham o mesmo tabuleiro duas vezes; fica o de maior
    # pontuação. O 0,9 é dedup de repetição, não escolha entre vizinhos — quem
    # separa tabuleiros vizinhos é o `SOBREPOSICAO_DE_REPETIDO`, adiante.
    crus.sort(key=lambda item: item[1], reverse=True)
    unicos = []
    for candidato in crus:
        if any(_sobrepoe(candidato[2], mantido[2]) > 0.9 for mantido in unicos):
            continue
        unicos.append(candidato)

    maior = max(item[3] for item in unicos)
    return [item[:3] for item in unicos if item[3] >= maior * 0.02]


def detectar(imagem, *, maximo: int = MAXIMO_DE_TABULEIROS,
             piso_do_xadrez: Optional[float] = None) -> List["Tabuleiro"]:
    """
    Os tabuleiros da página, na ordem de leitura de `diagrama.ordem_de_leitura`.

    `imagem` é a página inteira, em cinza ou RGB. Nada aqui depende de a página
    ter passado pelo pipeline de caracteres — é o ponto do módulo.

    `piso_do_xadrez` liga a peneira da F95 (`diagrama.pontuacao_de_tabuleiro`)
    por cima da pontuação própria do detector: o candidato só passa se o
    recorte endireitado também tiver a diferença de tinta entre casas pares e
    ímpares que um tabuleiro tem. `None` a desliga. O que a F96 mediu com e sem
    ela está no ROADMAP.
    """
    from core import diagrama as diag

    candidatos = _candidatos(imagem)
    if not candidatos:
        return []

    piso = max(PISO_ABSOLUTO, candidatos[0][1] * PISO_RELATIVO)
    escolhidos: List[Tuple[np.ndarray, float, Tuple[int, int, int, int]]] = []
    for quad, pontos, caixa in candidatos:
        if pontos < piso:
            continue
        if any(_sobrepoe(caixa, outra) > SOBREPOSICAO_DE_REPETIDO
               for _q, _p, outra in escolhidos):
            continue
        if piso_do_xadrez is not None:
            recorte = endireitar(_cinza(imagem), quad, LADO_DO_RECORTE)
            if diag.pontuacao_de_tabuleiro(recorte) < piso_do_xadrez:
                continue
        if len(escolhidos) >= maximo:
            break
        escolhidos.append((quad, pontos, caixa))

    achados = [Tabuleiro(caixa=c, quad=q, pontuacao=p) for q, p, c in escolhidos]
    return _na_ordem_de_leitura(achados)


def _na_ordem_de_leitura(tabuleiros: Sequence["Tabuleiro"]) -> List["Tabuleiro"]:
    """A ordem é a de `diagrama.ordem_de_leitura`, e é **a mesma da casa**.

    Não é reimplementada aqui de propósito: duas ordens fazem o "diagrama 2" da
    tela não ser o `[Diagram "2"]` da exportação, que é o defeito que a F95
    corrigiu. Se ela mudar, esta muda junto.
    """
    from core import diagrama as diag

    if len(tabuleiros) <= 1:
        return list(tabuleiros)

    por_caixa: dict = {}
    for i, t in enumerate(tabuleiros):
        por_caixa.setdefault(t.caixa, []).append(i)
    return [tabuleiros[por_caixa[c].pop(0)]
            for c in diag.ordem_de_leitura([t.caixa for t in tabuleiros])]


def localizar(imagem, *, maximo: int = MAXIMO_DE_TABULEIROS,
              piso_do_xadrez: Optional[float] = None
              ) -> List[Tuple[int, int, int, int]]:
    """Só as caixas, na mesma forma que `diagrama.localizar` devolve.

    É a porta para medir os dois caminhos com o mesmo instrumento
    (`medir_rotulos.py --por-contorno`) e para trocar um pelo outro sem tocar
    em `ler_rotulos`, `ler_titulo` ou `ler`.
    """
    return [t.caixa for t in detectar(imagem, maximo=maximo,
                                      piso_do_xadrez=piso_do_xadrez)]
