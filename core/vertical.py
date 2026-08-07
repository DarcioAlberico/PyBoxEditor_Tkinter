"""
Texto impresso na vertical (F8.1).

Livros de xadrez põem rótulos girados ao lado do diagrama — *"Analysis
diagram"* é o caso desta fase. Antes dela o programa **lia esse texto errado
sem dizer que leu**: medido nos 10.606 caracteres rotulados, o classificador
acerta 94,2% no recorte de pé e **8,4%** no mesmo recorte girado 90°. Não é
falhar; é devolver outra letra, com confiança de leitura normal e origem
`neural` como qualquer outra.

## O ângulo é do texto, não do recorte

`BoxEntry.angulo` são graus **anti-horários do texto impresso**, a mesma
convenção do PDF:

    0    texto normal
    90   o texto sobe (lê-se de baixo para cima); o glifo saiu girado 90° AH
    270  o texto desce (lê-se de cima para baixo); o glifo saiu girado 90° H

Quem classifica não quer o recorte como está na página, quer o glifo de pé —
`endireitar` faz essa volta num lugar só, para ninguém ter de refazer o
raciocínio do sinal. **Girar por múltiplo de 90° é transposição**, não
reamostragem: medido, os mesmos 9.987 caracteres que o modelo acerta de pé
voltam a ser acertados depois de ir e voltar, um a um.

## A geometria propõe, o classificador dispõe

A geometria sozinha não distingue um rótulo girado de uma coluna de primeiras
letras de parágrafo — as duas são caixas empilhadas com a mesma faixa de x.
`candidatos` só recolhe pilhas plausíveis (mesma faixa de x, vãos de espaço
entre letras, alta e estreita, e **sem vizinha ao lado**) e quem decide o
ângulo é o classificador, pela confiança **média da pilha inteira**: é o
critério da F1.5b, onde o árbitro confirma cada corte, e o da F7.1, onde a
legalidade arbitra a leitura.

Medido em 1.312 linhas reais simuladas nos quatro ângulos, o argmax da média
bate com o ângulo impresso em **99,7%** — a única falha é um empate de 0,001.
Uma pilha que não é texto girado responde 0° e fica como estava. Nas 322
páginas do livro, que não têm texto vertical nenhum: 7 pilhas propostas e
**nenhuma aceita**.

**Sem árbitro este módulo não faz nada**, e isso é a lição da F1.5b: lá,
separar glifo colado sem classificador que confirmasse custava 2,3 pontos de F1.
Marcar ângulo por geometria pura teria o mesmo defeito — mexeria em texto normal
para acertar o raro.

## 180° não é candidato

Livro impresso não traz linha de cabeça para baixo, e cada ângulo a mais é uma
chance a mais de virar uma pilha curta pelo lado errado. A medição mostra que o
classificador *saberia* separar 180° (99,7% também); ele não entra por não
existir no material, e não por não dar.
"""

import bisect
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from core.box_model import BoxEntry


#: Ângulos de texto girado que esta fase reconhece.
ANGULOS = (90, 270)

#: Mínimo de caixas para uma pilha ser candidata.
#:
#: **Cinco, e o quinto foi comprado com medição.** Com quatro, 81 páginas reais
#: sem nenhum texto vertical produzem 5 pilhas aceitas por engano — e as cinco
#: são **colunas de peças dentro do diagrama**, não texto. Uma coluna de quatro
#: peças é pilha alta, estreita, encostada e de vão zero: passa em toda a
#: geometria, e com quatro amostras a média da confiança ainda é ruído.
#:
#: Cinco não bastou sozinho: na varredura das 322 páginas ainda sobravam três
#: aceitas, duas delas com cinco e nove caixas. Quem as recusa é
#: `_com_vizinho_lateral`.
MIN_ITENS = 5

#: A pilha tem de ser bem mais alta que larga. Uma palavra girada de 4 letras
#: já passa de 2,5; texto normal empilhado não chega aqui sem também passar no
#: vão, que é o filtro que importa.
RAZAO_BBOX = 2.5

#: Fração da menor largura que duas caixas vizinhas precisam ter em comum.
SOBREPOSICAO_X = 0.55

#: Vão máximo entre letras vizinhas da pilha, em alturas medianas de caractere.
#: É o joelho da curva, e foi varrido em 81 páginas reais contra uma linha real
#: colada girada: com 0,7 a pilha colada sai partida (9 das 16 caixas) e com 0,9
#: as páginas normais passam a propor 554 pilhas em vez de 103. Em 0,8 a pilha
#: sai inteira e sobra ~1,3 candidata por página — que o classificador recusa.
VAO_MAXIMO = 0.8

#: Quanto a confiança média no ângulo escolhido precisa superar a do texto de
#: pé para a pilha ser aceita como vertical. A mediana da folga medida é 0,074;
#: o valor aqui é conservador de propósito — na dúvida, não mexer.
MARGEM = 0.05

#: Fração das caixas da pilha que pode ter vizinho lateral de tamanho de
#: caractere. Acima disto a pilha não é palavra girada: é a coluna das
#: primeiras letras de linhas seguidas. Ver `_com_vizinho_lateral`.
COM_VIZINHO_LATERAL = 0.5


# ----------------------------------------------------------------------
# Girar
# ----------------------------------------------------------------------

def _voltas(angulo: int) -> int:
    """Quantos giros anti-horários de 90° desfazem `angulo`."""
    if angulo % 360 == 90:
        return -1
    if angulo % 360 == 270:
        return 1
    if angulo % 360 == 180:
        return 2
    return 0


def endireitar(recorte: np.ndarray, angulo: int) -> np.ndarray:
    """
    O recorte com o glifo de pé, pronto para o classificador.

    Devolve array contíguo: `np.rot90` devolve uma vista de passo negativo, e
    o OpenCV recusa isso mais adiante no caminho.
    """
    voltas = _voltas(angulo)
    if voltas == 0:
        return recorte
    return np.ascontiguousarray(np.rot90(recorte, voltas))


def recorte_de_pe(imagem, box: BoxEntry) -> np.ndarray:
    """
    O recorte do box na página, pronto para o classificador.

    Endireita pelo ângulo (F8.1) e positiva o que estiver impresso em negativo
    (F10). É o funil das duas voltas: quem classifica pede o glifo como o
    modelo o viu no treino, e não como ele está na página.
    """
    from core import negativo

    arr = np.asarray(imagem)
    recorte = arr[box.y1:box.y2, box.x1:box.x2]
    if getattr(box, "negativo", False):
        recorte = negativo.positivar(recorte)
    return endireitar(recorte, getattr(box, "angulo", 0))


# ----------------------------------------------------------------------
# A geometria propõe
# ----------------------------------------------------------------------

def _mediana(valores: Sequence[int]) -> int:
    ordenados = sorted(valores)
    return ordenados[len(ordenados) // 2] if ordenados else 0


def _com_vizinho_lateral(pilha: Sequence[BoxEntry],
                         caracteres: Sequence[BoxEntry],
                         mediana: float) -> float:
    """
    Fração das caixas da pilha que têm outro caractere **encostado ao lado**.

    É o que separa uma palavra girada de uma coluna de primeiras letras de
    linhas seguidas, e a diferença é estrutural: letra de linha horizontal tem
    vizinha ao lado; letra de linha vertical tem vizinha em cima e embaixo. Só
    contam vizinhas de tamanho de caractere — o box do diagrama fica ao lado do
    rótulo que esta fase existe para ler, e ele não é vizinho de palavra.
    """
    ids = set(id(b) for b in pilha)
    alcance = max(4.0, mediana * 1.5)
    com = 0
    for b in pilha:
        for o in caracteres:
            if id(o) in ids:
                continue
            sobreposicao = min(b.y2, o.y2) - max(b.y1, o.y1)
            if sobreposicao <= 0.5 * min(b.height, o.height):
                continue
            if 0 <= o.x1 - b.x2 <= alcance or 0 <= b.x1 - o.x2 <= alcance:
                com += 1
                break
    return com / max(1, len(pilha))


def candidatos(boxes: Sequence[BoxEntry],
               min_itens: Optional[int] = None) -> List[List[BoxEntry]]:
    """
    Pilhas verticais plausíveis — só geometria, sem classificador.

    Uma pilha é uma cadeia de caixas de tamanho de caractere em que cada uma
    encosta na de baixo (vão pequeno) e divide com ela a faixa de x. O que
    sobra da cadeia é candidato se tiver `min_itens` caixas e for bem mais
    alta que larga.

    Nada aqui afirma que a pilha é texto girado: quem afirma é `marcar`.

    Os limiares chegam por parâmetro **lido na chamada**, e não como valor
    padrão: `def f(x=MIN_ITENS)` congela a constante na definição, e quem
    ajusta o módulo para medir mexeria numa variável que ninguém mais lê.
    """
    min_itens = MIN_ITENS if min_itens is None else min_itens
    if len(boxes) < min_itens:
        return []

    mediana = _mediana([b.height for b in boxes]) or 1
    piso, teto = mediana * 0.25, mediana * 3.0
    cand = [b for b in boxes
            if piso <= b.height <= teto and piso <= b.width <= teto]
    if len(cand) < min_itens:
        return []

    cand.sort(key=lambda b: (b.y1, b.x1))
    topos = [b.y1 for b in cand]
    vao_max = max(2.0, mediana * VAO_MAXIMO)

    usados = set()
    cadeias = []

    for i in range(len(cand)):
        if i in usados:
            continue
        cadeia = [i]
        usados.add(i)

        while True:
            u = cand[cadeia[-1]]
            # Só quem começa na faixa [um pouco antes do fim de `u`, `u` + vão].
            lo = bisect.bisect_left(topos, int(u.y2 - u.height * 0.3))
            hi = bisect.bisect_right(topos, int(u.y2 + vao_max))

            melhor, menor_vao = None, None
            for j in range(lo, hi):
                if j in usados:
                    continue
                o = cand[j]
                comum = min(u.x2, o.x2) - max(u.x1, o.x1)
                if comum <= 0:
                    continue
                if comum / max(1, min(u.width, o.width)) < SOBREPOSICAO_X:
                    continue
                vao = o.y1 - u.y2
                if menor_vao is None or vao < menor_vao:
                    melhor, menor_vao = j, vao

            if melhor is None:
                break
            cadeia.append(melhor)
            usados.add(melhor)

        if len(cadeia) < min_itens:
            continue
        caixas = [cand[j] for j in cadeia]
        largura = max(b.x2 for b in caixas) - min(b.x1 for b in caixas)
        altura = max(b.y2 for b in caixas) - min(b.y1 for b in caixas)
        if altura < RAZAO_BBOX * max(1, largura):
            continue
        if _com_vizinho_lateral(caixas, cand, mediana) > COM_VIZINHO_LATERAL:
            continue
        cadeias.append(caixas)

    return cadeias


# ----------------------------------------------------------------------
# O classificador dispõe
# ----------------------------------------------------------------------

def _confianca_media(imagem, caixas: Sequence[BoxEntry], angulo: int,
                     arbitro: Callable) -> float:
    """
    Confiança média do árbitro na pilha, endireitada por `angulo`.

    Árbitro que levanta devolve 0 para este ângulo, e não derruba a geração de
    boxes da página: sem confiança nenhuma o de pé ganha, que é o estado
    anterior a esta fase. Falhar aqui não pode custar a página inteira.
    """
    arr = np.asarray(imagem)
    confs = []
    for b in caixas:
        recorte = arr[b.y1:b.y2, b.x1:b.x2]
        if recorte.size == 0 or min(recorte.shape[:2]) < 3:
            continue
        try:
            confs.append(float(arbitro(endireitar(recorte, angulo))[1]))
        except Exception:
            return 0.0
    return float(np.mean(confs)) if confs else 0.0


def decidir_angulo(imagem, caixas: Sequence[BoxEntry], arbitro: Callable,
                   margem: Optional[float] = None) -> Tuple[int, dict]:
    """
    (ângulo da pilha, confiança média por ângulo).

    0 é a hipótese "não é texto girado" e ganha por padrão: um ângulo só é
    escolhido se superar o de pé por `margem`. Empate fica de pé — mexer numa
    pilha de texto normal custa mais do que deixar um rótulo por ler.
    """
    margem = MARGEM if margem is None else margem
    medias = {a: _confianca_media(imagem, caixas, a, arbitro)
              for a in (0,) + tuple(ANGULOS)}
    melhor = max(ANGULOS, key=lambda a: medias[a])
    if medias[melhor] > medias[0] + margem:
        return melhor, medias
    return 0, medias


def _absorver_vizinhos(cadeia: Sequence[BoxEntry],
                       boxes: Sequence[BoxEntry]) -> List[BoxEntry]:
    """
    Caixas soltas dentro da faixa da pilha — o pingo do 'i' girado.

    A cadeia é uma corrente de vizinhos, e o pingo não está *na* corrente: ele
    fica ao lado da haste, na mesma faixa. Sem recolhê-lo aqui, ele sobraria
    como um box de ângulo 0 no meio de uma pilha girada.
    """
    x1 = min(b.x1 for b in cadeia)
    y1 = min(b.y1 for b in cadeia)
    x2 = max(b.x2 for b in cadeia)
    y2 = max(b.y2 for b in cadeia)
    dentro = set(id(b) for b in cadeia)

    saida = []
    for b in boxes:
        if id(b) in dentro:
            continue
        cx, cy = (b.x1 + b.x2) / 2, (b.y1 + b.y2) / 2
        if x1 <= cx <= x2 and y1 <= cy <= y2 and b.width <= (x2 - x1) * 1.5:
            saida.append(b)
    return saida


def marcar(imagem, boxes: Sequence[BoxEntry], arbitro: Optional[Callable],
           margem: Optional[float] = None,
           min_itens: Optional[int] = None) -> List[List[BoxEntry]]:
    """
    Grava `angulo` nas caixas das pilhas aceitas. Devolve as pilhas aceitas.

    Sem `arbitro` não faz nada e devolve lista vazia — ver o cabeçalho do
    módulo para o motivo.
    """
    if arbitro is None:
        return []

    aceitas = []
    for cadeia in candidatos(boxes, min_itens):
        angulo, _ = decidir_angulo(imagem, cadeia, arbitro, margem)
        if angulo:
            for b in cadeia:
                b.angulo = angulo
            aceitas.append(ordenar(cadeia, angulo))
    return aceitas


def aplicar(imagem, boxes: Sequence[BoxEntry], arbitro: Optional[Callable],
            margem: Optional[float] = None, min_itens: Optional[int] = None
            ) -> Tuple[List[BoxEntry], List[List[BoxEntry]]]:
    """
    A fase inteira num passo: (boxes já com ângulo, pilhas aceitas).

    Roda **antes** do merge vertical do `BoxService`, e é por isso que ela
    fecha o assunto: as caixas que saem daqui marcadas ficam fora daquele
    merge, que colaria a pilha inteira num box só (medido: uma linha real de
    17 caracteres saía como 7 caixas).
    """
    if arbitro is None:
        return list(boxes), []

    novas = list(boxes)
    pilhas = []
    consumidos = set()

    for cadeia in candidatos(boxes, min_itens):
        if any(id(b) in consumidos for b in cadeia):
            continue
        angulo, _ = decidir_angulo(imagem, cadeia, arbitro, margem)
        if not angulo:
            continue

        grupo = list(cadeia) + _absorver_vizinhos(cadeia, novas)
        ids = set(id(b) for b in grupo)
        for b in grupo:
            b.angulo = angulo

        fundidas = fundir_pingos(grupo)
        for b in fundidas:
            b.angulo = angulo

        novas = [b for b in novas if id(b) not in ids] + fundidas
        consumidos |= ids
        pilhas.append(ordenar(fundidas, angulo))

    return novas, pilhas


# ----------------------------------------------------------------------
# A pilha como unidade
# ----------------------------------------------------------------------

def ordenar(pilha: Sequence[BoxEntry],
            angulo: Optional[int] = None) -> List[BoxEntry]:
    """
    A pilha na ordem em que se lê.

    Texto a 90° sobe — a primeira letra é a **de baixo**. A 270° desce. Sem
    `angulo` vale o das caixas, que só está preenchido depois de `marcar`.
    """
    if angulo is None:
        angulo = getattr(pilha[0], "angulo", 0) if pilha else 0
    return sorted(pilha, key=lambda b: b.y1, reverse=(angulo % 360 == 90))


def runs(boxes: Sequence[BoxEntry]) -> List[List[BoxEntry]]:
    """
    Agrupa em pilhas as caixas já marcadas, cada uma em ordem de leitura.

    Reagrupa por geometria em vez de confiar num identificador de pilha: o
    ângulo é o dado que se guarda no `.box`, e um arquivo lido do disco chega
    com os ângulos e sem os grupos.
    """
    marcados = [b for b in boxes if getattr(b, "angulo", 0)]
    if not marcados:
        return []

    saida = []
    for angulo in ANGULOS:
        desta = [b for b in marcados if b.angulo % 360 == angulo]
        if len(desta) < 2:
            saida.extend([b] for b in desta)
            continue
        for cadeia in _cadeias_soltas(desta):
            saida.append(ordenar(cadeia))
    return saida


def _cadeias_soltas(boxes: Sequence[BoxEntry]) -> List[List[BoxEntry]]:
    """Agrupa caixas já marcadas em pilhas, sem exigir tamanho mínimo."""
    mediana = _mediana([b.height for b in boxes]) or 1
    vao_max = max(4.0, mediana * 1.2)

    restantes = sorted(boxes, key=lambda b: (b.y1, b.x1))
    cadeias = []
    while restantes:
        cadeia = [restantes.pop(0)]
        mudou = True
        while mudou:
            mudou = False
            u = cadeia[-1]
            for i, o in enumerate(restantes):
                comum = min(u.x2, o.x2) - max(u.x1, o.x1)
                if comum <= 0 or not (-u.height <= o.y1 - u.y2 <= vao_max):
                    continue
                if comum / max(1, min(u.width, o.width)) < SOBREPOSICAO_X:
                    continue
                cadeia.append(restantes.pop(i))
                mudou = True
                break
        cadeias.append(cadeia)
    return cadeias


def fundir_pingos(pilha: Sequence[BoxEntry]) -> List[BoxEntry]:
    """
    O merge de diacrítico, no eixo certo para texto girado.

    Num 'i' girado o pingo fica **ao lado** da haste, não em cima. Em vez de
    escrever um segundo merge, transpõe as coordenadas, chama o que já existe
    e desfaz a transposição — a regra é a mesma, o eixo é que mudou.
    """
    from core.services.box_service import BoxService

    if len(pilha) < 2:
        return list(pilha)

    # O ângulo fica de fora da ida: `merge_vertical_boxes` deixa passar quem
    # está marcado, justamente para não colar pilha girada (F8.1). No espaço
    # transposto quem manda é a geometria, e ela já está no eixo certo.
    angulo = getattr(pilha[0], "angulo", 0)
    transposto = [BoxEntry(b.char, b.y1, b.x1, b.y2, b.x2,
                           b.confidence, b.source,
                           negativo=getattr(b, "negativo", False))
                  for b in pilha]
    fundidos = BoxService.merge_vertical_boxes(transposto)
    return [BoxEntry(b.char, b.y1, b.x1, b.y2, b.x2,
                     b.confidence, b.source, angulo, b.negativo)
            for b in fundidos]
