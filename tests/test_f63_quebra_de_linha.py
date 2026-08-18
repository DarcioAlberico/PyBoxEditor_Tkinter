"""
Testes da F63 — o apóstrofo deixa de partir a linha ao meio.

`quebrar_em_linhas` cortava onde a caixa nova descia em relação à **caixa
anterior sozinha**. Um apóstrofo é uma caixa curta plantada no alto: o fundo
dele fica na altura de x, e qualquer letra depois dele tem o centro abaixo
disso. A linha se partia ali, e no livro exportado a prosa saía picada —
`following fresh` / `high-` / `quality encounter` em três parágrafos.

Medido nas 10 páginas rotuladas (`medir_quebra_de_linha.py`): **69 cortes no
meio de linha em 532, contra 15 em 476** depois. E as linhas altas — a medida do
risco oposto, régua frouxa fundindo duas linhas numa — **caem** de 71 para 68,
então o conserto não pagou com o outro defeito.

Rodar sem pytest:      python tests/test_f63_quebra_de_linha.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import leitura_de_linha as ldl
from core.box_model import BoxEntry

#: A geometria destas páginas, em px: linha de base a 222, altura de x 22,
#: altura de ascendente 30, entrelinha 48.
BASE, ALTURA, ASCENDENTE, ENTRELINHA = 222, 22, 30, 48


def _letras(x, topo=BASE - ALTURA, n=6, larg=17, alt=ALTURA, passo=20):
    return [BoxEntry("a", x + i * passo, topo, x + i * passo + larg, topo + alt)
            for i in range(n)]


def _apostrofo(x, base=BASE):
    """
    Curto e **alto**: ele mora na altura de ascendente, e o fundo dele fica
    acima da altura de x. É essa posição que faz a letra seguinte parecer ter
    descido uma linha.
    """
    return BoxEntry("'", x, base - ASCENDENTE, x + 6, base - ASCENDENTE + 9)


def _hifen(x, topo=BASE - ALTURA):
    """Curto e no meio da altura de x."""
    return BoxEntry("-", x, topo + 10, x + 11, topo + 13)


# ----------------------------------------------------------------------
# O defeito
# ----------------------------------------------------------------------

def test_o_apostrofo_no_meio_nao_corta():
    linha = _letras(100, n=3) + [_apostrofo(165)] + _letras(175, n=3)
    assert len(ldl.quebrar_em_linhas(linha)) == 1


def test_o_hifen_no_meio_nao_corta():
    linha = _letras(100, n=3) + [_hifen(165)] + _letras(180, n=3)
    assert len(ldl.quebrar_em_linhas(linha)) == 1


def test_a_linha_que_comeca_com_aspas_nao_corta():
    """
    É o caso que a `CAIXA_CURTA` existe para pegar, e o único: com a base saindo
    de qualquer caixa, a aspa do começo da linha fixa a régua na altura de x e o
    defeito volta pela porta dos fundos. Nas 10 páginas rotuladas ele não
    aparece — por isso a varredura da constante é plana lá, e por isso este
    teste é a justificativa dela.
    """
    linha = [_apostrofo(100)] + _letras(110)
    assert len(ldl.quebrar_em_linhas(linha)) == 1

    curto = ldl.CAIXA_CURTA
    ldl.CAIXA_CURTA = 0.0
    try:
        assert len(ldl.quebrar_em_linhas(linha)) == 2, (
            "sem a régua de caixa curta o caso não se reproduz, e o teste "
            "deixou de medir o que diz medir")
    finally:
        ldl.CAIXA_CURTA = curto


def test_a_virgula_que_raspa_a_base_nao_corta():
    """
    A vírgula desce um fio abaixo da linha de base, então o centro dela fica
    **meio pixel** abaixo do fundo das letras. Sem a `FOLGA_DE_LINHA` isso é
    "desceu uma linha": `On the whole` e `, the author tries to` saíam
    separados. Medido, o excesso é 0,02 alturas medianas contra 0,66 da menor
    quebra de verdade.
    """
    virgula = BoxEntry(",", 200, BASE - 4, 206, BASE + 5)
    linha = _letras(100, n=5) + [virgula] + _letras(215, n=4)
    assert len(ldl.quebrar_em_linhas(linha)) == 1

    folga = ldl.FOLGA_DE_LINHA
    ldl.FOLGA_DE_LINHA = 0.0
    try:
        assert len(ldl.quebrar_em_linhas(linha)) > 1, (
            "sem folga o caso não se reproduz, e o teste deixou de medir o "
            "que diz medir")
    finally:
        ldl.FOLGA_DE_LINHA = folga


def test_a_pontuacao_no_fim_nao_cola_a_linha_seguinte():
    """O ponto final é curto e baixo; ele não pode virar a base da linha."""
    primeira = _letras(100, n=5) + [BoxEntry(".", 200, BASE - 5, 205, BASE)]
    segunda = _letras(100, topo=BASE - ALTURA + ENTRELINHA, n=5)
    assert len(ldl.quebrar_em_linhas(primeira + segunda)) == 2


# ----------------------------------------------------------------------
# O que não pode ter mudado
# ----------------------------------------------------------------------

def test_a_linha_seguinte_continua_cortando():
    primeira = _letras(100, n=6)
    segunda = _letras(100, topo=BASE - ALTURA + ENTRELINHA, n=6)
    assert len(ldl.quebrar_em_linhas(primeira + segunda)) == 2


def test_a_linha_seguinte_recuada_tambem_corta():
    """
    O caso em que só o `desceu` pode cortar: a linha nova começa **à direita**
    da anterior, então `voltou` não dispara. É o que a régua frouxa demais
    fundiria, e é o risco do conserto.
    """
    primeira = _letras(100, n=6)
    segunda = _letras(140, topo=BASE - ALTURA + ENTRELINHA, n=6)
    assert len(ldl.quebrar_em_linhas(primeira + segunda)) == 2


def test_o_descendente_nao_impede_o_corte():
    """`g` desce abaixo da base, e a régua sai do maior fundo da linha."""
    g = BoxEntry("g", 220, BASE - ALTURA, 237, BASE + 10)
    primeira = _letras(100, n=6) + [g]
    segunda = _letras(100, topo=BASE - ALTURA + ENTRELINHA, n=6)
    assert len(ldl.quebrar_em_linhas(primeira + segunda)) == 2


def test_a_pilha_girada_continua_inteira():
    pilha = []
    for i in range(5):
        b = BoxEntry(f"v{i}", 100, 200 - i * 24, 120, 220 - i * 24)
        b.angulo = 90
        pilha.append(b)
    assert len(ldl.quebrar_em_linhas(pilha)) == 1


def test_a_troca_de_coluna_continua_cortando():
    """A regra da F61 não pode ter sido comida pela desta."""
    esquerda = _letras(100, topo=900, n=6)
    direita = _letras(900, topo=100, n=6)
    assert len(ldl.quebrar_em_linhas(esquerda + direita)) == 2


def test_sem_boxes():
    assert ldl.quebrar_em_linhas([]) == []


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
