"""
A altura relativa à linha: o instrumento de medida, e o que ele mediu (F19).

**Nada em produção chama este módulo, e é de propósito.** Ele existe para
`medir_altura.py`, como `core/avaliacao_pagina.py` existe para `medir_paginas.py`.
O que ele serve é a resposta a uma pergunta que a F14 deixou em aberto — e a
resposta foi **não**.

## A pergunta

A F14 mediu e nomeou: homóglifo e caixa somam 23% dos erros de leitura, e **não
são erro de treino — são o mesmo desenho**. Um `0` e um `o` da mesma fonte
diferem em altura, não em traço; `c` e `C` também. O recorte de 32x32 que o
classificador recebe é normalizado em escala, então a informação que separaria
os dois **foi jogada fora antes de ele ver**. A F14 concluiu pedindo "entrada
nova — altura relativa à linha junto do recorte".

**Pôr a entrada na rede não dá para treinar.** A base são 127 mil PNGs de 32x32
já normalizados (`training_data/`), e a altura relativa não é recuperável deles:
foi descartada na gravação. Seria preciso reextrair e rerrotular a base inteira,
e o rótulo é trabalho humano de meses.

O que dava para testar sem retreinar nada era desempatar **depois**: a rede
oferece as candidatas, a altura escolhe entre elas. É o que `desambiguar` faz, e
é o que não funciona.

## Por que não funciona, e o motivo não é o sinal

O sinal existe e é forte — a tabela de d' abaixo mostra separação de 3 desvios.
O que derruba é a aritmética da precisão. `medir_altura.py` varre 63
combinações de normalizador (faixa da linha; mediana de `y1`/`y2` da linha),
corte, faixa de incerteza e margem de probabilidade, em 9.178 caracteres:

    rede como está (argmax)                98,29%
    melhor combinação com desambiguação    nenhuma passa de 98,29%

Testei também restringir a troca só aos pares confundíveis, em vez de a toda
divergência de classe: também sem ganho.

A conta que explica: numa amostra de 2.257 caracteres a rede erra 62, e 21 deles
são de classe de topo — o alvo. Para render, a medida geométrica teria de
disparar nesses 21 e quase nunca nos 2.195 acertos; a 2% de falso positivo já
seriam 44 quebras contra 21 consertos possíveis. **Uma base a 98% não tolera um
canal lateral a 97%.**

Isso não desmente a F14 — reforça a parte dela que este módulo não alcança. A
altura tem de entrar **na** rede, treinada junto, onde o modelo aprende quanto
confiar nela; pendurada depois, ela só vota, e vota pior que quem já decidia.

## O discriminante é o topo, e não a altura

Medido nos `.box` rotulados, em distância entre médias por desvio combinado
(d'), sobre as três medidas possíveis:

    par      d'(topo)   d'(base)   d'(altura)
    s/S         3,78       0,60        3,18
    o/0         3,24       0,60        2,66
    w/W         3,10       0,20        2,78
    c/C         3,00       0,30        1,82
    g/9         2,32       1,24        0,78
    l/1         1,93       1,02        0,06
    p/P         1,14       0,56        0,74
    i/1         0,01       0,90        0,86

O topo ganha em toda linha da tabela, e a razão é tipográfica: todo glifo se
apoia na mesma linha de base, então a **base** não distingue nada; o que muda é
até onde o glifo sobe. Minúscula de x-height começa em 0,30 da faixa; maiúscula
e dígito, em 0,08.

**A altura sozinha erraria o `p`.** Ele desce abaixo da base, então mede quase o
mesmo que um `P` (0,703 contra 0,771) — e é por isso que `p/P` fica em 1,14 e
não entra. Um módulo que usasse "altura" como a F14 escreveu erraria justamente
o par que a F14 lista como o maior da família de caixa.

## O que a geometria não separa de jeito nenhum

`p/P`, `i/1`, `k/K`: os dois lados do par sobem à mesma altura. Ficam para o
contexto — que é a F17, e lá funcionam.
"""

from typing import Iterable, List, Optional, Sequence, Tuple

from core.box_model import BoxEntry

#: Glifos cujo topo fica na altura de x — não sobem à linha de ascendente.
#: Inclui os descendentes (`g p q y`), que descem mas começam em x-height.
TOPO_EM_X = set("acemnorsuvwxz") | set("gpqy")

#: Glifos cujo topo alcança a linha de ascendente ou de caixa alta.
#: `i` e `j` entram pelo pingo: medido, o topo do `i` é o do `1` (d' = 0,01).
TOPO_ALTO = (set("bdfhklt") | set("ij")
             | set("ABCDEFGHIJKLMNOPQRSTUVWXYZ") | set("0123456789"))

#: Onde cortar entre um e outro, em frações da altura da faixa da linha.
#: Medido: x-height fica em 0,30 (desvio 0,07) e caixa alta em 0,08 (0,06).
#: O corte é o meio, e a varredura confirma (ver F19 no ROADMAP).
CORTE = 0.19

#: Folga em volta do corte em que a medida não decide nada. A faixa da linha é
#: `max(y2) - min(y1)` dos boxes dela, então uma linha sem descendente ou sem
#: ascendente encolhe a faixa e desloca todas as frações juntas. Perto do corte
#: essa deriva vale mais que o sinal, e ali o certo é não opinar.
INCERTEZA = 0.05


def classe_do_char(char: str) -> Optional[str]:
    """`"x"`, `"alto"` ou `None` para quem a tipografia não classifica."""
    if not char or len(char) != 1:
        return None
    if char in TOPO_EM_X:
        return "x"
    if char in TOPO_ALTO:
        return "alto"
    return None


def topo_relativo(box: BoxEntry, topo_linha: int, altura_linha: int) -> Optional[float]:
    """Onde o topo do box cai dentro da faixa da linha, de 0 a 1."""
    if altura_linha <= 0:
        return None
    return (box.y1 - topo_linha) / altura_linha


def classe_medida(box: BoxEntry, topo_linha: int,
                  altura_linha: int) -> Optional[str]:
    """
    A classe que a geometria diz, ou `None` quando ela não decide.

    Box girado (F8.1) devolve `None`: ali a faixa da linha é horizontal e esta
    medida não quer dizer nada.
    """
    if getattr(box, "angulo", 0):
        return None
    t = topo_relativo(box, topo_linha, altura_linha)
    if t is None or abs(t - CORTE) < INCERTEZA:
        return None
    return "x" if t > CORTE else "alto"


def desambiguar(candidatos: Sequence[Tuple[str, float]],
                medida: Optional[str],
                margem: float = 0.02) -> Optional[Tuple[str, float]]:
    """
    Escolhe entre as candidatas da rede a que **cabe na altura medida**.

    Devolve `(char, probabilidade)` da escolhida, ou `None` para não mexer.

    Não mexe quando: a geometria não decidiu; a vencedora já cabe; nenhuma
    candidata cabe; ou a substituta é fraca demais. A `margem` é o mínimo de
    probabilidade que a substituta precisa ter — sem ela, a cauda da
    distribuição decidiria a leitura, e uma classe que a rede deu 0,001 não é
    uma segunda opinião, é ruído.

    **Quem a tipografia não classifica fica como está**, e isso é metade da
    segurança do módulo: figurina, ligadura, pontuação e símbolo não têm classe
    de topo, então nunca são trocados nem servem de troca.
    """
    if not candidatos or medida is None:
        return None

    vencedora, _p = candidatos[0]
    classe_vencedora = classe_do_char(vencedora)
    if classe_vencedora is None or classe_vencedora == medida:
        return None

    for char, p in candidatos[1:]:
        if p < margem:
            break
        if classe_do_char(char) == medida:
            return (char, p)
    return None


def faixas_por_linha(linhas: Iterable[Sequence[BoxEntry]]
                     ) -> List[Tuple[int, int]]:
    """`(topo, altura)` da faixa de cada linha, na ordem em que vieram."""
    saida = []
    for linha in linhas:
        if not linha:
            saida.append((0, 0))
            continue
        topo = min(b.y1 for b in linha)
        saida.append((topo, max(b.y2 for b in linha) - topo))
    return saida
