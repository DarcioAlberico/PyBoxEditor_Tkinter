"""
Testes da F65 — o apóstrofo deixa de virar troca de coluna.

O terceiro e último lugar em que o mesmo glifo partia a palavra. A F61 cortou a
linha onde a sequência **sobe**, porque é assim que se sai da coluna da esquerda
para a da direita. Só que o apóstrofo mora na altura de ascendente: chegando
depois de `can`, que é todo altura de x, ele fica inteiro acima do topo da linha
— e a régua o lia como coluna vizinha. `we can` / `'t say that`.

Medido nas 10 páginas rotuladas, o `subiu` dispara 10 vezes e os dois montes não
se tocam:

    apóstrofo subindo dentro da linha    0,08 – 0,14 alturas medianas   (3)
    troca de coluna                     66,22 – 104,23                 (7)

O vão é de **470×**. `FOLGA_DE_COLUNA = 1,0` fica dentro dele com 7× de margem
de um lado e 66× do outro, e varrido o platô vai de 0,25 a 60 — a 80 começa a
comer troca de coluna de verdade.

Rodar sem pytest:      python tests/test_f65_folga_de_coluna.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import leitura_de_linha as ldl
from core.box_model import BoxEntry

#: A geometria da página 13 do Kasparov: altura de x 19, ascendente 28.
BASE, ALTURA, ASCENDENTE = 700, 19, 28


def _letra(char, x, larg=15, base=BASE, alt=ALTURA):
    return BoxEntry(char, x, base - alt, x + larg, base)


def _apostrofo(x, base=BASE):
    """Sobe até a altura de ascendente e para acima da altura de x."""
    return BoxEntry("'", x, base - ASCENDENTE - 3, x + 5, base - ALTURA - 3)


def _cant():
    """`can't`, com o `can` todo em altura de x — é o que arma o defeito."""
    return [_letra("c", 124), _letra("a", 143), _letra("n", 160),
            _apostrofo(185), _letra("t", 193, larg=10)]


# ----------------------------------------------------------------------
# O defeito
# ----------------------------------------------------------------------

def test_o_apostrofo_depois_de_altura_de_x_nao_troca_de_coluna():
    linha = _cant()
    assert len(ldl.quebrar_em_linhas(linha)) == 1, [
        "".join(b.char for b in L) for L in ldl.quebrar_em_linhas(linha)]


def test_sem_a_folga_o_caso_se_reproduz():
    """Se este passar a não falhar, o teste acima deixou de medir algo."""
    folga = ldl.FOLGA_DE_COLUNA
    ldl.FOLGA_DE_COLUNA = 0.0
    try:
        assert len(ldl.quebrar_em_linhas(_cant())) == 2
    finally:
        ldl.FOLGA_DE_COLUNA = folga


# ----------------------------------------------------------------------
# O que não pode ter mudado
# ----------------------------------------------------------------------

def test_a_troca_de_coluna_continua_cortando():
    esquerda = [_letra("e", 100 + i * 20, base=2400) for i in range(6)]
    direita = [_letra("d", 900 + i * 20, base=300) for i in range(6)]
    assert len(ldl.quebrar_em_linhas(esquerda + direita)) == 2


def test_a_coluna_que_comeca_com_aspas_tambem_corta():
    """
    É por isto que a régua é folga, e não "a caixa tem de ser alta": uma coluna
    que abre com aspas sobe centenas de alturas, e tem de ser cortada mesmo
    sendo a caixa curta que dispara.
    """
    esquerda = [_letra("e", 100 + i * 20, base=2400) for i in range(6)]
    direita = [_apostrofo(900, base=300)] + [
        _letra("d", 910 + i * 20, base=300) for i in range(5)]
    assert len(ldl.quebrar_em_linhas(esquerda + direita)) == 2


def test_a_pilha_girada_continua_inteira():
    pilha = []
    for i in range(5):
        b = BoxEntry(f"v{i}", 100, 200 - i * 24, 120, 220 - i * 24)
        b.angulo = 90
        pilha.append(b)
    assert len(ldl.quebrar_em_linhas(pilha)) == 1


def test_a_linha_seguinte_continua_cortando():
    primeira = [_letra("a", 100 + i * 20) for i in range(6)]
    segunda = [_letra("b", 100 + i * 20, base=BASE + 51) for i in range(6)]
    assert len(ldl.quebrar_em_linhas(primeira + segunda)) == 2


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
