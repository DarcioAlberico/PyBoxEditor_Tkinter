"""
Testes da F103 — o parágrafo medido em passos de linha, e não em glifos.

A regra do salto comparava o vão entre duas linhas com a **altura mediana dos
glifos** da linha. Numa fonte de texto essa mediana é a altura de x — sem
ascendente nem descendente — e o passo entre linhas mede quase o triplo dela.
Com o limite em 1,6 alturas, todo passo normal já parecia vão de parágrafo:

    livro                          mediana do salto ÷ altura   abria parágrafo
    Aagaard  Endgame Technique                          2,60             99,2%
    Aagaard  Attacking Manual I                         2,74             99,8%
    Dvoretsky Endgame Manual                            2,41            100,0%
    Nunn  Secrets of Rook Endings                       1,92             96,3%
    Darcy Lima  A Estrategia                            1,91             92,3%
    Yusupov  Chess Evolution 1                          2,33             86,1%

Não era defeito de um livro: **todo EPUB e DOCX que este projeto já escreveu saiu
com um parágrafo por linha impressa.** Sobre o passo da coluna a mediana é 1,00
nos seis, que é o que se espera de uma medida normalizada por si mesma.

O que estes testes prendem é a unidade — e que a regra nova continue vendo o que
a antiga via de verdade: o vão maior, o recuo e a virada de coluna.

Rodar sem pytest:      python tests/test_f102_paragrafo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import livro

#: A geometria que quebrava tudo, tirada do Aagaard: glifos de 20 px de altura
#: mediana e linhas de 52 px de passo — a razão 2,6 que a fase mediu.
ALTURA = 20
PASSO = 52
MARGEM = 100


def _linhas(quantas=6, coluna=0, esquerda=MARGEM, topo=0, passo=PASSO,
            altura=ALTURA):
    return [livro.Linha(topo=topo + i * passo, esquerda=esquerda,
                        altura=altura, texto=f"l{i}", coluna=coluna)
            for i in range(quantas)]


# ----------------------------------------------------------------------
# A métrica
# ----------------------------------------------------------------------

def test_a_metrica_traz_o_passo_de_cada_coluna():
    linhas = _linhas(5) + _linhas(5, coluna=1, esquerda=900, passo=30)
    metricas = livro._metricas_por_coluna(linhas)
    assert metricas[0] == (MARGEM, ALTURA, PASSO)
    assert metricas[1] == (900, ALTURA, 30)


def test_o_passo_e_a_mediana_e_nao_o_maior_vao():
    """
    Um diagrama no meio da coluna abre um vão enorme. A mediana não se abala;
    a média se abalaria, e o resto da coluna deixaria de quebrar em lugar nenhum.
    """
    linhas = _linhas(4)
    linhas.append(livro.Linha(topo=linhas[-1].topo + 900, esquerda=MARGEM,
                              altura=ALTURA, texto="depois do diagrama"))
    assert livro._metricas_por_coluna(linhas)[0][2] == PASSO


def test_a_coluna_de_uma_linha_so_nao_divide_por_zero():
    """Não há vão para medir, e também não há segunda linha para quebrar."""
    linhas = _linhas(4) + [livro.Linha(topo=10, esquerda=900, altura=ALTURA,
                                       texto="sozinha", coluna=1)]
    metricas = livro._metricas_por_coluna(linhas)
    assert metricas[1][2] == PASSO, "devia cair para o passo da página"

    sozinha = [livro.Linha(topo=10, esquerda=900, altura=ALTURA, texto="só eu")]
    passo = livro._metricas_por_coluna(sozinha)[0][2]
    assert passo == int(ALTURA * livro.PASSO_POR_ALTURA)
    assert len(livro._agrupar_em_paragrafos(sozinha)) == 1


def test_o_passo_ignora_o_vao_negativo_da_virada_de_coluna():
    """
    A lista vem em ordem de leitura, e ali a última linha da esquerda é seguida
    da primeira da direita — vão negativo. O passo sai dos topos **ordenados**.
    """
    linhas = _linhas(4) + _linhas(4, coluna=1, esquerda=900)
    linhas = linhas[:4] + list(reversed(linhas[4:]))
    assert livro._metricas_por_coluna(linhas)[1][2] == PASSO


# ----------------------------------------------------------------------
# A regra
# ----------------------------------------------------------------------

def test_o_passo_normal_deixou_de_abrir_paragrafo():
    """
    **O teste da fase.** Com a altura de glifo no denominador, 52 > 20×1,6 e
    cada uma destas seis linhas virava um parágrafo. Com o passo, 52 < 52×1,6.
    """
    paragrafos = livro._agrupar_em_paragrafos(_linhas(6))
    assert len(paragrafos) == 1, [p.texto for p in paragrafos]
    assert paragrafos[0].texto == "l0 l1 l2 l3 l4 l5"


def test_o_vao_de_verdade_continua_abrindo_paragrafo():
    """
    Meio passo a mais não; o dobro do passo, sim — que é o vão impresso.

    São oito linhas normais e não três, e a diferença não é enfeite: a mediana
    só é robusta com vãos normais em maioria. Numa coluna de três linhas mais
    dois vãos grandes, a mediana **é** um dos grandes, e nada mais quebra. As
    colunas destes livros têm de vinte a quarenta linhas.
    """
    linhas = _linhas(8)
    linhas.append(livro.Linha(topo=linhas[-1].topo + int(PASSO * 1.4),
                              esquerda=MARGEM, altura=ALTURA, texto="quase"))
    linhas.append(livro.Linha(topo=linhas[-1].topo + PASSO * 2,
                              esquerda=MARGEM, altura=ALTURA, texto="longe"))
    textos = [p.texto for p in livro._agrupar_em_paragrafos(linhas)]
    assert textos == ["l0 l1 l2 l3 l4 l5 l6 l7 quase", "longe"], textos


def test_o_recuo_continua_abrindo_e_agora_mede_em_passos():
    """
    O recuo mudou de unidade junto, e não por simetria: `0,8 × altura de glifo`
    são 16 px de limite, menos que o espaço entre duas palavras. Em passos são
    41, que é a ordem de grandeza de um recuo de parágrafo impresso.
    """
    limite = MARGEM + PASSO * livro.RECUO_DE_PARAGRAFO
    linhas = _linhas(3)
    linhas.append(livro.Linha(topo=linhas[-1].topo + PASSO,
                              esquerda=int(limite) - 10, altura=ALTURA,
                              texto="tremida"))
    linhas.append(livro.Linha(topo=linhas[-1].topo + PASSO,
                              esquerda=int(limite) + 10, altura=ALTURA,
                              texto="recuada"))
    textos = [p.texto for p in livro._agrupar_em_paragrafos(linhas)]
    assert textos == ["l0 l1 l2 tremida", "recuada"], textos


def test_a_troca_de_coluna_continua_abrindo_paragrafo():
    """Ali o vão é negativo, e nenhuma das outras duas regras o vê."""
    linhas = _linhas(4) + _linhas(4, coluna=1, esquerda=900)
    assert len(livro._agrupar_em_paragrafos(linhas)) == 2


def test_a_altura_do_glifo_deixou_de_pesar():
    """
    A prova da troca de unidade: mexer só na altura dos glifos, com o mesmo
    passo e a mesma margem, não pode mudar mais nada.
    """
    grosso = livro._agrupar_em_paragrafos(_linhas(6, altura=ALTURA))
    fino = livro._agrupar_em_paragrafos(_linhas(6, altura=ALTURA // 2))
    assert [p.texto for p in grosso] == [p.texto for p in fino]


def test_agrupar_nao_perde_nem_inventa_texto():
    """
    A garantia que vale mais que a contagem: a fase **reagrupa**, e não reescreve.
    Foi assim que se conferiu no livro de 898 páginas.
    """
    linhas = (_linhas(4) + [livro.Linha(topo=4 * PASSO + PASSO * 3,
                                        esquerda=MARGEM + 60, altura=ALTURA,
                                        texto="nova")]
              + _linhas(3, coluna=1, esquerda=900, topo=0))
    paragrafos = livro._agrupar_em_paragrafos(linhas)
    assert (" ".join(p.texto for p in paragrafos)
            == " ".join(l.texto for l in linhas))


def test_a_geometria_do_aagaard_dava_um_paragrafo_por_linha():
    """
    O número da fase, reproduzido em miniatura: com a razão 2,6 medida no livro,
    a regra antiga abria parágrafo em toda linha e a nova em nenhuma.
    """
    linhas = _linhas(10)
    antiga = sum(1 for a, b in zip(linhas, linhas[1:])
                 if b.topo - a.topo > ALTURA * (1 + livro.SALTO_DE_PARAGRAFO))
    assert antiga == 9, "a geometria de teste não reproduz o defeito"
    assert len(livro._agrupar_em_paragrafos(linhas)) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
