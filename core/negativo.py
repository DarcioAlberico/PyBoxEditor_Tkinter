r"""
Texto impresso em negativo — branco sobre tarja preta ou colorida (F10).

Livro de xadrez põe o cabeçalho da partida numa tarja: *"J.Bolbochan –
L.Pachman"* em branco sobre um retângulo preto. Antes desta fase o programa
**não lia esse texto, e não dizia que não leu**: `binarize` deixa a tinta em
branco, então a tarja inteira vira um borrão de tinta, `findContours` com
RETR_EXTERNAL devolve **um** box de 663x55 e os vinte caracteres de dentro
somem. Medido na página 33 do Yusupov: 6 tarjas, 6 boxes, zero caracteres.

Não é um caso raro deste livro. No *Chess Evolution 1* são 264 páginas com
tarja em quase toda partida e todo exercício; o nome dos jogadores é
justamente o que a F9.2 quer no dicionário do usuário.

## A polaridade é do box, não da página

`BoxEntry.negativo` diz que **aquele** glifo está impresso claro sobre escuro.
É a mesma escolha da F8.1 para `angulo`, e pelo mesmo motivo: quem classifica
não quer o recorte como está na página, quer o glifo como o modelo o viu no
treino — escuro sobre claro, de pé. `vertical.recorte_de_pe` é o funil onde as
duas voltas acontecem, e `positivar` é a desta fase.

Inverter a página inteira seria mais simples e está descartado de propósito: o
usuário confere o box contra a página impressa, e mexer no que ele vê para
consertar o que o modelo lê troca um problema de leitura por um de revisão.

## O retângulo cheio se acha pelas bordas

Acima da tarja do Yusupov há uma tira decorativa hachurada. Ela é clara o
bastante para virar tinta na inversão, encosta no topo das letras e funde meia
linha num componente só — medido, uma tarja de 20 caracteres devolvia 88
componentes, dois deles com 343x55 (metade da tarja cada).

Por isso a faixa é **aparada antes de ser lida**: linha de retângulo cheio tem
~100% de tinta, linha de tira hachurada tem 55%–75%. Encolhe-se de fora para
dentro até achar a primeira linha (e coluna) cheia. Na tarja medida, o perfil
de tinta por linha é

    0.27 0.54 0.58 ... 0.74 | 0.98 1.00 0.99 0.97 | 0.86 ... 0.90 | 0.99 0.99 | 0.24
    \___ tira hachurada ___/ \___ borda da tarja _/ \__ o texto __/ \_ borda _/

e a apara devolve exatamente as linhas 12–53, que são o retângulo preto.

## O que decide não é o formato da faixa, é o que tem dentro

Uma faixa cheia pode ser tarja, foto, logotipo ou barra de rodapé. O critério
aqui é o mesmo de `preprocess.tinta_plausivel`: avalia o **resultado**, não a
aparência do candidato. Inverte-se a faixa e conta-se quantos componentes têm
tamanho de caractere *em relação à altura da própria faixa* — a régua está
dentro dela, e não na mediana da página, que não é confiável para medir glifo:
medido, a página 31 do Yusupov tem mediana de 4 px (respingo do adaptativo)
contra 18 px da página 30.

**O preço dessa régua é a tarja de várias linhas.** Com o glifo medido contra a
altura da faixa, a razão cai a cada linha a mais: a de duas linhas do Kasparov
(715x112, letras de ~35 px) passa em 0,31, raspando no piso de 0,30, e uma de
três linhas não passaria. Está registrado como limite, e não corrigido, porque
a correção óbvia — deduzir a altura da linha agrupando os próprios componentes
— é também a que aceitaria a palavra sublinhada, cujos vazados se agrupam tão
bem quanto letras. Ver `ALTURA_TARJA`.
"""

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from core.box_model import BoxEntry


#: Fração de tinta acima da qual a caixa é bloco cheio, e não traço de glifo.
#: Medido, a tarja com o texto já carvado fica em 0,73–0,86 no Yusupov e em
#: 0,66–0,88 no Kasparov; o limiar fica abaixo das duas faixas de propósito,
#: porque tarja de tom fraco perde tinta na binarização.
#:
#: **Sozinho ele não separa nada**, e é bom não confundir: palavra em negrito
#: com sublinhado chega a 0,68, dentro da faixa da tarja. Quem separa são
#: `RAZAO` e `ALTURA_TARJA`; este limiar só evita gastar inversão em traço de
#: letra comum.
PREENCHIMENTO = 0.55

#: A tarja é bem mais larga que alta. Além de não gastar inversão em cada peça
#: preta de diagrama que escape do RETR_EXTERNAL, é **metade do filtro que
#: separa tarja de palavra em negrito** — a outra metade é `ALTURA_TARJA`.
#: Medido nos 66 candidatos do Kasparov e nos 50 do Yusupov:
#:
#:     tarja de verdade      5,34 – 13,70 de proporção
#:     palavra sublinhada    3,00 –  4,72
#:
#: O preço está registrado: uma tarja mais curta que 4:1 — um rótulo colorido
#: de uma palavra só — não é vista. Abaixo dessa proporção ela é
#: indistinguível de uma palavra em negrito com sublinhado, e essa palavra o
#: caminho normal já lê certo.
RAZAO = 4.0

#: Altura mínima, em pixels, para valer a pena olhar dentro. Abaixo disto não
#: cabe caractere legível nem a 150 dpi.
ALTURA_MINIMA = 8

#: A tarja tem de ser mais alta que isto, em alturas medianas de caractere da
#: página. **É a outra metade do filtro contra palavra em negrito**, e cobre o
#: que a proporção não cobre. Medido nas mesmas 588 páginas:
#:
#:     tarja de verdade      2,57 – 28,50 alturas
#:     palavra sublinhada    0,41 –  1,21
#:
#: A palavra sublinhada é o caso perigoso desta fase, e não um detalhe: o
#: sublinhado gruda as letras num componente cheio e largo, os *vazados* do
#: 'n' e do 'a' viram "glifos" plausíveis, e aceitá-la **substituiria por lixo
#: um texto que o caminho normal já lia certo**.
#:
#: **A mediana falha num lugar conhecido, e quem cobre é a proporção.** Numa
#: página de sumário, com centenas de pontos de preenchimento, ela desce a 8 px
#: enquanto a letra mede 22 — e o fragmento *"ening"* do título em negrito
#: chega a 2,75 alturas. Ele é recusado por ter proporção 3,09. Trocar a
#: mediana pelo percentil 75 resolveria esse caso e criaria outro pior: nas
#: páginas de exercício do Yusupov o percentil 75 vai a 30 px e o piso passa a
#: 60, acima das tarjas de 55 que são o alvo da fase.
ALTURA_TARJA = 2.0

#: Tinta de uma linha (ou coluna) da borda do retângulo cheio.
SOLIDO = 0.90

#: Quanto a apara pode comer de cada eixo. Passando disto ela não está achando
#: a borda de um retângulo, está comendo o miolo — e o eixo volta inteiro, para
#: a decisão ficar com o conteúdo (ver `_apara`).
MAX_APARA = 0.40

#: Altura de um glifo em frações da altura da faixa. O piso deixa passar a
#: pontuação (o ponto de "J.Bolbochan" tem 0,07 e entra por `MIN_RUIDO`, não
#: por aqui); o teto recusa o que atravessa a tarja de borda a borda.
ALTURA_GLIFO = (0.30, 0.95)

#: Largura máxima de um glifo, em alturas da faixa. Componente mais largo que
#: isto é fusão de letras coladas, e não conta para a decisão — mas continua
#: virando box, que é o que `dividir_glifos_colados` sabe separar.
LARGURA_GLIFO = 1.5

#: Quantos glifos de tamanho plausível fazem uma faixa ser texto.
MIN_GLIFOS = 3

#: Abaixo disto, em frações da altura da faixa, o componente é respingo do
#: papel dentro da tarja e não vira box. O ponto final e a vírgula ficam acima.
MIN_RUIDO = 0.06

#: Folga vertical, em frações da altura do texto, para um componente ainda ser
#: da linha (ver `na_linha`). Cobre acento e pingo acima da altura das
#: maiúsculas sem alcançar a tira decorativa, que fica bem mais longe.
MARGEM_LINHA = 0.15


# ----------------------------------------------------------------------
# Inverter
# ----------------------------------------------------------------------

def positivar(recorte: np.ndarray) -> np.ndarray:
    """
    O recorte com a tinta escura sobre fundo claro, como o modelo o viu.

    É a volta que `vertical.endireitar` é para o ângulo, e mora aqui pelo mesmo
    motivo: um lugar só, para ninguém ter de lembrar do sinal.
    """
    return 255 - recorte


# ----------------------------------------------------------------------
# A geometria propõe
# ----------------------------------------------------------------------

def _preenchimento(th: np.ndarray, box: BoxEntry) -> float:
    recorte = th[box.y1:box.y2, box.x1:box.x2]
    if recorte.size == 0:
        return 0.0
    return float((recorte > 0).mean())


def altura_de_texto(boxes: Sequence[BoxEntry]) -> int:
    """Altura mediana de caractere da página — ver `ALTURA_TARJA`."""
    alturas = sorted(b.height for b in boxes)
    return alturas[len(alturas) // 2] if alturas else 0


def candidatos(th: np.ndarray, boxes: Sequence[BoxEntry]) -> List[BoxEntry]:
    """
    Caixas cheias, largas e mais altas que um caractere — só geometria.

    Nada aqui afirma que a caixa é tarja: quem afirma é `aplicar`, depois de
    olhar o que há dentro.
    """
    piso = max(ALTURA_MINIMA, ALTURA_TARJA * altura_de_texto(boxes))

    saida = []
    for b in boxes:
        if b.height < piso or b.width < b.height * RAZAO:
            continue
        if _preenchimento(th, b) >= PREENCHIMENTO:
            saida.append(b)
    return saida


def _apara(perfil: np.ndarray) -> Tuple[int, int]:
    """
    (início, fim) do miolo cheio. Eixo sem borda cheia volta inteiro.

    Não aparar é a resposta certa para o caso sem borda, e não uma desistência:
    é a tarja de tom fraco, onde a binarização marca 60%–87% da faixa e nenhuma
    linha chega a `SOLIDO`. Medido na página 264 do Kasparov, quando a apara era
    condição de aceite: a tarja *"6...♘bd7"* — cinza, legível, com nove
    caracteres — era recusada por não ter linha cheia, e o texto ficava perdido
    do mesmo jeito de antes da fase.
    """
    ini, fim = 0, len(perfil)
    while ini < fim and perfil[ini] < SOLIDO:
        ini += 1
    while fim > ini and perfil[fim - 1] < SOLIDO:
        fim -= 1
    if ini >= fim or (ini + len(perfil) - fim) > MAX_APARA * len(perfil):
        return 0, len(perfil)
    return ini, fim


def faixa_solida(th: np.ndarray, box: BoxEntry) -> Optional[BoxEntry]:
    """
    A caixa encolhida até o retângulo cheio.

    Apara as duas pontas de cada eixo enquanto a linha (ou coluna) não estiver
    cheia de tinta. Parar na **primeira** linha cheia é o que impede a apara de
    comer o miolo: as linhas do meio da tarja são as que o texto carvou, e são
    justamente as que não passam de `SOLIDO`.

    Devolve None só para caixa vazia. Quem recusa candidato é `parece_texto`,
    e é lá que a recusa tem de ficar: a apara mede a **moldura**, e moldura
    boa não é o que distingue tarja de foto.
    """
    regiao = th[box.y1:box.y2, box.x1:box.x2] > 0
    if regiao.size == 0:
        return None

    y0, y1 = _apara(regiao.mean(axis=1))
    x0, x1 = _apara(regiao[y0:y1].mean(axis=0))

    return BoxEntry("", box.x1 + x0, box.y1 + y0, box.x1 + x1, box.y1 + y1)


# ----------------------------------------------------------------------
# O conteúdo dispõe
# ----------------------------------------------------------------------

def binarizar_faixa(cinza: np.ndarray, faixa: BoxEntry) -> np.ndarray:
    """
    A faixa binarizada com a polaridade trocada: o claro é que vira tinta.

    Otsu local, e não o limiar da página: o contraste dentro da tarja é outro,
    e o limiar global foi calculado para separar texto preto de papel branco.
    """
    recorte = cinza[faixa.y1:faixa.y2, faixa.x1:faixa.x2]
    if recorte.size == 0:
        return np.zeros((0, 0), np.uint8)
    if recorte.ndim == 3:
        recorte = cv2.cvtColor(recorte, cv2.COLOR_RGB2GRAY)
    _, inv = cv2.threshold(recorte, 0, 255,
                           cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return inv


def glifos(inv: np.ndarray, faixa: BoxEntry) -> List[BoxEntry]:
    """
    Os componentes claros da faixa que não são respingo, em coordenadas da
    página.

    Vem tudo o que tem tamanho de tinta, e não só o que tem tamanho de
    caractere: o que sai daqui vira box e segue o caminho normal da página, onde
    `merge_vertical_boxes` junta o pingo do 'i' e `dividir_glifos_colados`
    separa a letra colada. Filtrar aqui seria fazer de novo, pior, o que o
    pipeline já faz.
    """
    if inv.size == 0:
        return []

    contornos, _ = cv2.findContours(inv, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    piso = max(2.0, faixa.height * MIN_RUIDO)

    saida = []
    for c in contornos:
        x, y, w, h = cv2.boundingRect(c)
        if w < 2 or h < 2 or (w < piso and h < piso):
            continue
        saida.append(BoxEntry("", faixa.x1 + x, faixa.y1 + y,
                              faixa.x1 + x + w, faixa.y1 + y + h,
                              negativo=True))
    return saida


def plausiveis(caixas: Sequence[BoxEntry], faixa: BoxEntry) -> List[BoxEntry]:
    """
    Os componentes com tamanho de caractere **em relação à altura da faixa**.

    Letra colada em letra dá um componente largo, que não entra aqui e não
    precisa entrar: estes são os que decidem se a faixa é texto e onde está a
    linha, não os que viram box.
    """
    piso, teto = faixa.height * ALTURA_GLIFO[0], faixa.height * ALTURA_GLIFO[1]
    largura_max = faixa.height * LARGURA_GLIFO
    return [b for b in caixas
            if piso <= b.height <= teto and b.width <= largura_max]


def parece_texto(caixas: Sequence[BoxEntry], faixa: BoxEntry) -> bool:
    """
    Os componentes da faixa são uma linha de texto?

    Bastam três inequívocos: para *decidir*, um punhado de caracteres é prova
    suficiente, e exigir mais recusaria a tarja de nome curto.
    """
    return len(plausiveis(caixas, faixa)) >= MIN_GLIFOS


def na_linha(caixas: Sequence[BoxEntry],
             marcados: Sequence[BoxEntry]) -> List[BoxEntry]:
    """
    Descarta o que está fora da faixa vertical ocupada pelo texto.

    **É a rede que apara a decoração quando a apara falha**, e ela falha:
    medido nas 438 tarjas do Yusupov, três têm a tira hachurada escura o
    bastante para que as linhas dela passem de `SOLIDO` — `faixa_solida` para na
    primeira linha "cheia", que ali é a primeira linha da *tira*, e o recorte
    entra com a decoração dentro. Essas três devolviam 119, 112 e 22 boxes para
    nomes de ~20 caracteres; o excedente é hachura.

    A linha se mede pelos componentes que já se sabe serem caractere
    (`plausiveis`), e o que fica fora dela pelo centro é decoração. Tarja de
    duas linhas não se perde: os plausíveis das duas entram na conta, e o vão
    entre elas fica dentro do intervalo.
    """
    if not marcados:
        return list(caixas)

    topo = min(b.y1 for b in marcados)
    base = max(b.y2 for b in marcados)
    folga = max(2.0, (base - topo) * MARGEM_LINHA)

    return [b for b in caixas
            if topo - folga <= (b.y1 + b.y2) / 2 <= base + folga]


# ----------------------------------------------------------------------
# A fase inteira
# ----------------------------------------------------------------------

def aplicar(cinza: np.ndarray, th: np.ndarray, boxes: Sequence[BoxEntry]
            ) -> Tuple[List[BoxEntry], np.ndarray, List[BoxEntry]]:
    """
    Troca cada tarja pelos caracteres de dentro dela.

    Devolve `(boxes, th, faixas)`: as caixas com as tarjas substituídas, a
    binarização da página **com as faixas aceitas invertidas**, e as faixas.

    O `th` corrigido não é detalhe: `dividir_glifos_colados` corta pelo perfil
    de tinta, e dentro de uma tarja não corrigida o perfil é o do fundo — o vale
    entre duas letras seria um pico. Com a faixa invertida ali, o separador vê
    o que veria em texto normal.

    Roda **antes** do merge vertical e do descarte de bloco não-texto: o que sai
    daqui é caractere, e tem de passar por tudo que caractere passa. Depois do
    descarte seria tarde — a tarja é larga e o descarte a levaria junto com o
    diagrama.

    **Devolve a lista ordenada por (y1, x1), e isso não é cortesia.**
    `merge_vertical_boxes` mede a distância vertical como `b2.y1 - b1.y2` e
    aceita valor negativo — numa lista fora de ordem, uma letra da tarja lá em
    cima casa com um box lá embaixo, o par vira uma caixa que atravessa a
    página e ela passa a absorver tudo que cruza a sua coluna. Medido ao
    devolver as caixas novas no fim da lista: os 1.889 boxes da página 33
    saíram do merge como **27**.
    """
    faixas: List[BoxEntry] = []
    novas = list(boxes)
    th_corrigido = th

    for b in candidatos(th, boxes):
        faixa = faixa_solida(th, b)
        if faixa is None:
            continue

        inv = binarizar_faixa(cinza, faixa)
        dentro = glifos(inv, faixa)
        marcados = plausiveis(dentro, faixa)
        if len(marcados) < MIN_GLIFOS:
            continue
        dentro = na_linha(dentro, marcados)

        if th_corrigido is th:
            th_corrigido = th.copy()
        th_corrigido[faixa.y1:faixa.y2, faixa.x1:faixa.x2] = inv

        # A tarja sai da lista inteira, tira decorativa e tudo: ela é o box que
        # sobrou de RETR_EXTERNAL, e o que interessa dela são as letras.
        novas = [o for o in novas if o is not b] + dentro
        faixas.append(faixa)

    if faixas:
        novas.sort(key=lambda o: (o.y1, o.x1))
    return novas, th_corrigido, faixas
