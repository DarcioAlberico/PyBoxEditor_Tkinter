"""
Testes da F3.11 — o merge vertical parava de respeitar a linha de texto.

O defeito relatado: o box da figurina saía com o ponto da linha de cima dentro,
e onde havia '...' saía com os três. A régua de folga era uma só
(`max(10, min(30, mediana * 0,8))` ≈ 0,8 altura mediana), e a pontuação da linha
de cima está a 0,55–0,79 do topo de um glifo **alto** da linha de baixo: cabia.

Rodar sem pytest:      python tests/test_f311_merge.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.box_model import BoxEntry
from core.services.box_service import BoxService


# ----------------------------------------------------------------------
# Apoio
# ----------------------------------------------------------------------

#: Altura de box mediana da página 0020 do Kasparov, medida. Todas as
#: coordenadas abaixo são as dela, em pixels.
#:
#: É a página com a maior mediana das onze rotuladas, e por isso a mais atingida:
#: a régua antiga valia `min(30, mediana * 0,8)`, ou seja **23,2 px** ali contra
#: 17,6 nas páginas de mediana 22. A contagem de merges entre linhas segue a
#: mediana sem exceção — 29→36 casos, 27→22, 23→11, 22→de 1 a 3.
MEDIANA = 29


def _corpo_de_texto(n=30):
    """Boxes comuns o bastante para fixar a mediana em `MEDIANA`."""
    return [BoxEntry("x", 40 * i, 1000, 40 * i + 18, 1000 + MEDIANA)
            for i in range(n)]


def _dono_de(saida, alvo):
    """O box de saída que cobre o centro de `alvo`."""
    return next(b for b in saida
                if b.x1 <= (alvo.x1 + alvo.x2) / 2 <= b.x2
                and b.y1 <= (alvo.y1 + alvo.y2) / 2 <= b.y2)


def _dentro(dono, b):
    return (dono.x1 <= b.x1 and b.x2 <= dono.x2
            and dono.y1 <= b.y1 and b.y2 <= dono.y2)


def _merge(boxes):
    # Ordenado por (y1, x1) como `generate_boxes_opencv` entrega: a função mede
    # a folga como `b2.y1 - b1.y2` e aceita valor negativo, então numa lista
    # fora de ordem ela funde o que quer que venha depois.
    return BoxService.merge_vertical_boxes(sorted(boxes, key=lambda b: (b.y1, b.x1)))


def _funde(alvo, *extras):
    """Os boxes de `extras` acabaram dentro do box que cobre `alvo`?"""
    dono = _dono_de(_merge(_corpo_de_texto() + [alvo, *extras]), alvo)
    return [e for e in extras if _dentro(dono, e)]


# ----------------------------------------------------------------------
# O defeito
# ----------------------------------------------------------------------

def test_ponto_da_linha_de_cima_nao_entra_no_glifo_alto():
    """
    Coordenadas reais da página 0020 do Kasparov: o '.' da linha de cima
    (y 281–287) e o '2' da linha de baixo (y 309–339). Folga de 22 px, uma
    altura mediana inteira — e mesmo assim entrava.
    """
    digito = BoxEntry("2", 1210, 309, 1231, 339)
    ponto = BoxEntry(".", 1210, 281, 1217, 287)
    assert _funde(digito, ponto) == [], "o ponto da linha de cima foi engolido"


def test_reticencias_da_linha_de_cima_nao_entram():
    """
    'se tiver ... pega os 3' — e pegava mesmo. O laço refaz a busca com a caixa
    já crescida, então o primeiro ponto engolido alarga o box para a esquerda e
    põe o vizinho ao alcance. Bastava o primeiro passar.
    """
    rei = BoxEntry("♔", 1180, 309, 1215, 339)
    pontos = [BoxEntry(".", 1150 + 14 * i, 281, 1157 + 14 * i, 287)
              for i in range(3)]
    assert _funde(rei, *pontos) == [], "as reticências da linha de cima entraram"


def test_a_figurina_e_a_vitima_preferida_por_ser_alta():
    """
    Não é o desenho do rei: é a altura. O 'a' de x-height, na mesma coluna e com
    o mesmo ponto acima, nunca chegou perto da régua — o topo dele fica 15 px
    mais baixo. Por isso o defeito aparecia em ♔♕♖♗♘, B, R, K, d, f, h e nos
    dígitos, e nunca em 'a', 'e', 'o'.
    """
    ponto = BoxEntry(".", 1210, 281, 1217, 287)
    baixo = BoxEntry("a", 1210, 324, 1228, 339)          # só x-height
    assert _funde(baixo, ponto) == [], "nem antes isto deveria fundir"


# ----------------------------------------------------------------------
# O que o merge existe para fazer, e continua fazendo
# ----------------------------------------------------------------------

def test_pingo_do_i_continua_fundindo():
    """386 casos medidos, folga de até 0,23 mediana — a mais comum de todas."""
    haste = BoxEntry("i", 100, 300, 106, 330)
    pingo = BoxEntry("", 99, 291, 106, 297)              # folga de 3 px
    assert _funde(haste, pingo) == [pingo], "o pingo do 'i' deixou de fundir"


@pytest.mark.parametrize("folga", [0, 3, 5, 6])
def test_pingo_funde_ate_o_limite_medido(folga):
    """A folga do diacrítico medida vai a 5 px (0,23 mediana); a régua é 6,6."""
    haste = BoxEntry("i", 100, 300, 106, 330)
    pingo = BoxEntry("", 99, 300 - folga - 6, 106, 300 - folga)
    assert _funde(haste, pingo) == [pingo], f"folga de {folga} px deveria fundir"


def test_dois_pontos_e_ponto_e_virgula_continuam_fundindo():
    """
    ':' e ';' são dois pedaços **curtos** separados por meia altura de x — 10 px
    medidos, 0,45 mediana. É por isso que a folga de curto+curto é maior que a
    de curto+alto: com a régua do diacrítico eles se partiriam em dois boxes.
    """
    de_cima = BoxEntry(":", 200, 310, 207, 317)
    de_baixo = BoxEntry("", 200, 327, 207, 334)          # folga de 10 px
    assert _funde(de_cima, de_baixo) == [de_baixo], "o ':' se partiu em dois"


def test_dois_altos_encostados_nao_fundem():
    """
    A regra de alto+alto (2 px) não mudou: são duas letras de linhas vizinhas,
    e fundi-las faria um box de duas linhas.
    """
    de_cima = BoxEntry("h", 300, 300, 318, 330)
    de_baixo = BoxEntry("n", 300, 336, 318, 366)
    assert _funde(de_cima, de_baixo) == [], "dois glifos altos não podem fundir"


def test_a_folga_e_relativa_a_escala_da_pagina():
    """
    A régua antiga tinha piso e teto **em pixels** (`max(10, min(30, ...))`), o
    que a fazia significar coisas diferentes a 200 e a 300 dpi. Dobrar a página
    inteira não pode mudar quem funde com quem.
    """
    def dobrado(b):
        return BoxEntry(b.char, b.x1 * 2, b.y1 * 2, b.x2 * 2, b.y2 * 2)

    haste = BoxEntry("i", 100, 300, 106, 330)
    pingo = BoxEntry("", 99, 291, 106, 297)
    ponto_de_cima = BoxEntry(".", 1210, 281, 1217, 287)
    digito = BoxEntry("2", 1210, 309, 1231, 339)

    grande = _merge([dobrado(b) for b in
                     _corpo_de_texto() + [haste, pingo, digito, ponto_de_cima]])

    def cobre(alvo, outro):
        return _dentro(_dono_de(grande, dobrado(alvo)), dobrado(outro))

    assert cobre(haste, pingo), "o pingo parou de fundir no dobro do tamanho"
    assert not cobre(digito, ponto_de_cima), "o ponto entrou no dobro do tamanho"


# ----------------------------------------------------------------------
# A poda da F96 — o laço deixa de ser quadrático e o resultado não muda
# ----------------------------------------------------------------------

def _merge_de_referencia(boxes):
    """O laço **antes** da poda da F96, transcrito.

    Existe para que a poda seja provada em vez de argumentada: o que ela
    promete é economia de comparações, e nenhuma mudança no que sai. A prova
    é comparar com isto, e não reler o `if`.
    """
    if not boxes:
        return []

    girados = [b for b in boxes if getattr(b, "angulo", 0)]
    if girados:
        de_pe = [b for b in boxes if not getattr(b, "angulo", 0)]
        return _merge_de_referencia(de_pe) + girados

    heights = [b.y2 - b.y1 for b in boxes]
    if not heights:
        return boxes

    median_h = max(10, sorted(heights)[len(heights) // 2])
    curto = median_h * 0.6

    saida, usados = [], set()
    for i in range(len(boxes)):
        if i in usados:
            continue
        b1 = boxes[i]
        atual = BoxEntry(b1.char, b1.x1, b1.y1, b1.x2, b1.y2,
                         negativo=getattr(b1, "negativo", False),
                         moldura=getattr(b1, "moldura", False))
        usados.add(i)

        fundiu = True
        while fundiu:
            fundiu = False
            for j in range(i + 1, len(boxes)):
                if j in usados:
                    continue
                b2 = boxes[j]
                alto1 = (atual.y2 - atual.y1) > curto
                alto2 = (b2.y2 - b2.y1) > curto
                if alto1 and alto2:
                    folga = 2
                elif alto1 or alto2:
                    folga = median_h * BoxService.FOLGA_DE_DIACRITICO
                else:
                    folga = median_h * BoxService.FOLGA_DE_PONTUACAO
                if b2.y1 - atual.y2 > folga:
                    continue

                juntos = max(0, min(atual.x2, b2.x2) - max(atual.x1, b2.x1))
                menor = min(atual.x2 - atual.x1, b2.x2 - b2.x1)
                if menor <= 0 or (juntos / menor) <= 0.3:
                    continue

                atual.x1 = min(atual.x1, b2.x1)
                atual.y1 = min(atual.y1, b2.y1)
                atual.x2 = max(atual.x2, b2.x2)
                atual.y2 = max(atual.y2, b2.y2)
                atual.moldura = atual.moldura or getattr(b2, "moldura", False)
                usados.add(j)
                fundiu = True
                break
        saida.append(atual)
    return saida


def _forma(boxes):
    return [(b.x1, b.y1, b.x2, b.y2, bool(getattr(b, "moldura", False)))
            for b in boxes]


def _pagina_sintetica(semente, linhas=25, por_linha=40, com_pingos=True):
    """Uma página de texto plausível: linhas de glifos e diacríticos soltos."""
    import random

    rng = random.Random(semente)
    boxes = []
    for linha in range(linhas):
        base = 100 + linha * (MEDIANA + 12)
        for k in range(por_linha):
            x = 60 + k * 24
            altura = rng.choice([MEDIANA, MEDIANA, MEDIANA - 8, MEDIANA - 12])
            boxes.append(BoxEntry("x", x, base + (MEDIANA - altura),
                                  x + rng.randint(10, 20), base + MEDIANA))
            if com_pingos and rng.random() < 0.18:
                topo = base - rng.randint(2, 10)
                boxes.append(BoxEntry(".", x + 2, topo - 6, x + 8, topo))
    boxes.sort(key=lambda b: (b.y1, b.x1))
    return boxes


@pytest.mark.parametrize("semente", [1, 7, 42, 2026])
def test_a_poda_nao_muda_o_que_sai(semente):
    """A prova da F96: mesma saída, caixa a caixa, com e sem a poda."""
    boxes = _pagina_sintetica(semente)
    assert _forma(BoxService.merge_vertical_boxes(list(boxes))) \
        == _forma(_merge_de_referencia(list(boxes)))


def test_a_poda_nao_muda_o_que_sai_em_pagina_densa():
    """Sem os pingos, quase nada funde — e é aí que o laço antigo mais gastava."""
    boxes = _pagina_sintetica(3, linhas=40, por_linha=60, com_pingos=False)
    assert _forma(BoxService.merge_vertical_boxes(list(boxes))) \
        == _forma(_merge_de_referencia(list(boxes)))


def test_lista_fora_de_ordem_continua_pelo_laco_de_antes():
    """A poda desliga sozinha quando a lista não chega ordenada por `y1`.

    É o caso de `vertical.fundir_pingos`, que chama isto com as coordenadas
    transpostas: ali `y1` é o `x1` de origem e a lista não vem ordenada por
    ele. A prova é que a saída continua igual à do laço de referência.
    """
    boxes = _pagina_sintetica(11, linhas=6, por_linha=10)
    fora = boxes[len(boxes) // 2:] + boxes[:len(boxes) // 2]
    assert any(fora[k].y1 > fora[k + 1].y1 for k in range(len(fora) - 1)), \
        "a lista de prova precisa estar fora de ordem"
    assert _forma(BoxService.merge_vertical_boxes(list(fora))) \
        == _forma(_merge_de_referencia(list(fora)))


def test_pagina_de_dezenas_de_milhares_de_caixas_nao_trava():
    """O que a fase foi consertar, em forma de teste.

    Eram 275 s na página 96 do Yusupov (85.883 contornos). O teto aqui é
    folgado de propósito — o que ele pega é a volta do quadrático, não uma
    variação de máquina: sem a poda, estas 24.000 caixas levam minutos.
    """
    import time

    boxes = _pagina_sintetica(5, linhas=120, por_linha=200, com_pingos=False)
    assert len(boxes) >= 20000

    comeco = time.perf_counter()
    saida = BoxService.merge_vertical_boxes(boxes)
    gasto = time.perf_counter() - comeco

    assert saida
    assert gasto < 10.0, f"o merge levou {gasto:.1f} s em {len(boxes)} caixas"


# ----------------------------------------------------------------------
# Execução direta
# ----------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
