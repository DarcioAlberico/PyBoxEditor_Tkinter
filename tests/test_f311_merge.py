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
# Execução direta
# ----------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
