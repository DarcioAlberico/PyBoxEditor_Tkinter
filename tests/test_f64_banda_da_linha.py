"""
Testes da F64 — o apóstrofo deixa de abrir banda sozinho.

A F63 consertou onde a **linha** se corta; sobrou onde a **banda** se forma.
`BoxService._linhas` agrupa por sobreposição vertical, ordenando por `y1`, e o
apóstrofo mora na altura de ascendente: ele chega antes da letra que segue e
abre a banda sozinho, com o fundo dela cravado na altura de x. Nenhuma letra da
linha consegue entrar depois disso, e a banda da aspa sai antes — `White's`
virava `' White s`.

Medido nas 10 páginas rotuladas: **7 bandas feitas só de caixa curta, todas
aspas ou apóstrofo, contra 0** depois. As bandas caem de 346 para 339 — as sete
órfãs, e nada além delas.

Rodar sem pytest:      python tests/test_f64_banda_da_linha.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import leitura_de_linha as ldl
from core.box_model import BoxEntry
from core.services.box_service import BoxService

#: A geometria da página 13 do Kasparov, em px, medida no `.box`: linha de base
#: a 440, altura de x 19, ascendente 28, entrelinha 51.
BASE, ALTURA, ASCENDENTE, ENTRELINHA = 440, 19, 28, 51


def _letra(char, x, larg=17, alt=ALTURA):
    return BoxEntry(char, x, BASE - alt, x + larg, BASE)


def _alta(char, x, larg=17):
    """Maiúscula ou ascendente: sobe até a altura de ascendente."""
    return BoxEntry(char, x, BASE - ASCENDENTE, x + larg, BASE)


def _apostrofo(x):
    """
    Mora **no alto** e é curto: começa acima de tudo e acaba acima da altura
    de x. É o `y1` menor que faz dele o primeiro da ordenação.
    """
    return BoxEntry("'", x, BASE - ASCENDENTE - 3, x + 5, BASE - ALTURA - 3)


def _palavra_com_apostrofo():
    """`White's`, na geometria da página."""
    return ([_alta("W", 1001, larg=30)]
            + [_alta("h", 1033, larg=14), _alta("i", 1049, larg=6),
               _alta("t", 1057, larg=10), _letra("e", 1069, larg=15)]
            + [_apostrofo(1086)]
            + [_letra("s", 1093, larg=13)])


# ----------------------------------------------------------------------
# O defeito
# ----------------------------------------------------------------------

def test_o_apostrofo_nao_abre_banda_sozinho():
    bandas = BoxService._linhas(_palavra_com_apostrofo())
    assert len(bandas) == 1, [
        "".join(b.char for b in banda) for banda in bandas]


def test_a_palavra_sai_na_ordem():
    saida = BoxService.sort_boxes_reading_order(_palavra_com_apostrofo())
    assert "".join(b.char for b in saida) == "White's"


def test_a_aspa_que_abre_a_linha_nao_fica_sozinha():
    """A aspa de abertura chega antes de tudo, e a linha é dela."""
    linha = [_apostrofo(100)] + [_letra("a", 110 + i * 20) for i in range(6)]
    assert len(BoxService._linhas(linha)) == 1


def test_nenhum_box_se_perde():
    linha = _palavra_com_apostrofo()
    bandas = BoxService._linhas(linha)
    soltos = [b for banda in bandas for b in banda]
    assert len(soltos) == len(linha)
    assert {id(b) for b in soltos} == {id(b) for b in linha}


# ----------------------------------------------------------------------
# O que não pode ter mudado
# ----------------------------------------------------------------------

def test_a_linha_seguinte_continua_abrindo_banda():
    primeira = [_letra("a", 100 + i * 20) for i in range(6)]
    segunda = [BoxEntry("b", 100 + i * 20, BASE - ALTURA + ENTRELINHA,
                        117 + i * 20, BASE + ENTRELINHA) for i in range(6)]
    bandas = BoxService._linhas(primeira + segunda)
    assert len(bandas) == 2, [
        "".join(b.char for b in banda) for banda in bandas]


def test_a_banda_da_aspa_nao_engole_a_linha_de_baixo():
    """
    A aspa deixa de ter fundo, mas quem entra depois dela **tem**: uma linha
    inteira abaixo não pode ser absorvida por causa de uma aspa solta em cima.
    """
    solta = [_apostrofo(100)]
    linha = [_letra("a", 110 + i * 20) for i in range(6)]
    abaixo = [BoxEntry("b", 110 + i * 20, BASE - ALTURA + ENTRELINHA,
                       127 + i * 20, BASE + ENTRELINHA) for i in range(6)]
    bandas = BoxService._linhas(solta + linha + abaixo)
    assert len(bandas) == 2
    assert "".join(b.char for b in bandas[0]) == "'aaaaaa"


def test_a_regua_e_a_mesma_da_f63():
    """
    Uma régua de caixa curta, e não duas: foi cópia divergente que deixou a
    F1.5 medir uma coisa e a aplicação fazer outra.
    """
    linha = _palavra_com_apostrofo()
    curto = ldl.CAIXA_CURTA
    ldl.CAIXA_CURTA = 0.0
    try:
        assert len(BoxService._linhas(linha)) == 2, (
            "sem a régua da F63 o caso não se reproduz, e o teste deixou de "
            "medir o que diz medir")
    finally:
        ldl.CAIXA_CURTA = curto


def test_sem_boxes():
    assert BoxService._linhas([]) == []


# ----------------------------------------------------------------------
# Execução direta
# ----------------------------------------------------------------------

def _main():
    testes = [(n, o) for n, o in sorted(globals().items())
              if n.startswith("test_") and callable(o)]
    falhas = 0
    for nome, teste in testes:
        try:
            teste()
            print(f"  ok   {nome}")
        except AssertionError as erro:
            falhas += 1
            print(f"  FALHA {nome}: {erro}")
    print(f"\n{len(testes) - falhas}/{len(testes)} passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(_main())
