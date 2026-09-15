"""
Testes da F70 — uma letra do cabeçalho apagava a calha da página inteira.

A projeção de `detectar_colunas` era um OR: `ocupado[x]` valia se **qualquer**
box cobrisse aquele x. O cabeçalho corrente é centralizado, e centralizado é em
cima da calha — medido no Nunn, um único box de 25×27 px derruba a calha de 31
px para 7, e a página sai com as duas colunas intercaladas.

É a queixa da F61 na sua última forma, e explica por que o defeito era errático:
a variável é onde a letra do cabeçalho calha de cair. Medido nas 352 páginas de
prosa do Nunn, 8 páginas saíam misturadas (o capítulo *Solutions to Exercises*) e
outras 5 passavam por 0–1 px de folga. No Aagaard, 27 de 30.

A projeção passa a contar **linhas**: o cabeçalho é uma só, e o miolo de uma
página de coluna única é coberto por todas as quarenta.

Rodar sem pytest:      python tests/test_f70_calha_do_cabecalho.py
"""

import contextlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.box_model import BoxEntry
from core.services.box_service import BoxService


# ----------------------------------------------------------------------
# Apoio
# ----------------------------------------------------------------------

def _linha(x_ini, y, n, larg=17, alt=22, passo=20, rotulo=""):
    return [BoxEntry(f"{rotulo}{i}" if rotulo else "",
                     x_ini + i * passo, y, x_ini + i * passo + larg, y + alt)
            for i in range(n)]


CALHA = 19
LARGURA_DA_COLUNA = 32 * 20 - 3
INICIO_DA_DIREITA = LARGURA_DA_COLUNA + CALHA
MEIO_DA_CALHA = LARGURA_DA_COLUNA + CALHA // 2


def _duas_colunas(linhas=20, n=32):
    """A geometria do Nunn: calha de 19 px onde o caractere mediano tem 17."""
    boxes = []
    for i in range(linhas):
        y = i * 30
        boxes += _linha(0, y, n, rotulo=f"e{i}_")
        boxes += _linha(INICIO_DA_DIREITA, y, n, rotulo=f"d{i}_")
    return boxes


def _cabecalho(y=-40, x1=MEIO_DA_CALHA - 12, larg=25, alt=27, rotulo="cab"):
    """
    Uma caixa só, pousada em cima da calha — o caractere central do cabeçalho.

    As medidas são as do box culpado medido no Nunn: 25×27 px, na banda de cima
    da página, cobrindo o meio da calha.
    """
    return [BoxEntry(rotulo, x1, y, x1 + larg, y + alt)]


@contextlib.contextmanager
def _sem_tolerancia():
    """A régua de antes da F70 — nenhuma linha tolerada, isto é, o OR."""
    antes = BoxService.LINHAS_PARA_TOLERAR
    BoxService.LINHAS_PARA_TOLERAR = 10 ** 9
    try:
        yield
    finally:
        BoxService.LINHAS_PARA_TOLERAR = antes


# ----------------------------------------------------------------------
# O defeito
# ----------------------------------------------------------------------

def test_uma_letra_do_cabecalho_apagava_a_calha():
    """
    Fixa o defeito, e não o comportamento: se a régua mudar de forma, é este
    teste que diz contra o que a de hoje está sendo comparada.

    O box do cabeçalho corrente, sozinho e centrado, hoje nem entra na
    projeção — é mobília (ver `test_a_mobilia_da_pagina_nao_apaga_a_calha`).
    O que exibe o defeito de então é uma linha larga cruzando a calha: sem
    tolerância, um box dela em cima da calha tem de apagá-la.
    """
    boxes = _duas_colunas() + _linha(200, -40, 40, rotulo="t_")
    with _sem_tolerancia():
        assert len(BoxService.detectar_colunas(boxes)) == 1, \
            "sem tolerância, um box no meio da calha tem de apagá-la"


def test_a_calha_sobrevive_a_uma_linha_atravessada():
    boxes = _duas_colunas() + _cabecalho()
    colunas = BoxService.detectar_colunas(boxes)
    assert len(colunas) == 2, \
        f"o cabeçalho apagou a calha da página inteira: {colunas}"


def test_a_pagina_sem_cabecalho_continua_de_duas_colunas():
    """A tolerância não pode ser o que faz a calha aparecer."""
    assert len(BoxService.detectar_colunas(_duas_colunas())) == 2


# ----------------------------------------------------------------------
# Os limites da tolerância
# ----------------------------------------------------------------------

def test_duas_linhas_largas_atravessadas_ainda_apagam():
    """
    A tolerância é de **uma** linha, e este é o teste que a mantém apertada.

    Duas linhas **largas** cruzando a calha — um título de duas linhas que
    ocupa a página de lado a lado — ainda dizem coluna única. O que deixou de
    apagar a calha foi a mobília (ver abaixo), e não uma tolerância maior.
    """
    larga = _linha(200, -40, 40, rotulo="t1_")          # 200..997, cruza a calha
    larga2 = _linha(200, -80, 40, rotulo="t2_")
    assert len(BoxService.detectar_colunas(_duas_colunas() + larga)) == 2
    assert len(BoxService.detectar_colunas(_duas_colunas() + larga + larga2)) == 1


def test_a_mobilia_da_pagina_nao_apaga_a_calha():
    """
    O que a F70 deixou em aberto — "o título de duas linhas sobre a calha
    ainda a apaga" —, na forma em que a página 34 do Chess Evolution 1 o
    trouxe: o título «Solutions» em cima e o número da página centrado
    embaixo. São duas linhas cruzando a calha contra uma tolerada, e a página
    de duas colunas saía intercalada. A mobília — compacta e centrada — não
    entra na projeção.
    """
    titulo = _cabecalho(y=-80, rotulo="tit")
    numero = _cabecalho(y=20 * 30 + 40, rotulo="num")
    colunas = BoxService.detectar_colunas(_duas_colunas() + titulo + numero)
    assert len(colunas) == 2, f"a mobília apagou a calha: {colunas}"
    # E com o cabeçalho corrente por cima das duas, que é o caso da F70.
    boxes = _duas_colunas() + titulo + numero + _cabecalho()
    assert len(BoxService.detectar_colunas(boxes)) == 2


def test_o_que_e_mobilia_e_o_que_nao_e():
    """
    A primeira versão tirava da projeção toda linha curta, e abriu calha falsa
    no sumário do «Calculation» (título à esquerda, número à direita: pouca
    tinta, mas de ponta a ponta) e numa página do Seirawan com títulos
    encostados à esquerda. Só a linha compacta **e** centrada é mobília.
    """
    x_min, x_max = 0, 1000
    centrada_curta = _linha(440, 0, 6)                    # 440..557, no meio
    sumario = _linha(0, 0, 8) + [BoxEntry("7", 960, 0, 977, 22)]
    titulo_a_esquerda = _linha(0, 0, 6)
    larga_centrada = _linha(200, 0, 30)                  # 200..597
    assert BoxService._e_mobilia(centrada_curta, x_min, x_max)
    assert not BoxService._e_mobilia(sumario, x_min, x_max)
    assert not BoxService._e_mobilia(titulo_a_esquerda, x_min, x_max)
    assert not BoxService._e_mobilia(larga_centrada, x_min, x_max)


def test_a_pagina_curta_nao_tolera_nada():
    """
    **Uma linha de cinco é 20% da página.** Medido no recorte de página real do
    `test_f16_colunas` — cinco linhas, duas colunas —, tolerar uma abre uma
    terceira faixa no vão entre palavras que calham de se alinhar. Abaixo de
    `LINHAS_PARA_TOLERAR` vale a régua de antes.
    """
    curta = _duas_colunas(linhas=5) + _linha(200, -40, 40, rotulo="t_")
    assert len(BoxService.detectar_colunas(curta)) == 1, \
        "página de 6 bandas não pode desprezar uma delas"

    assert len(BoxService.detectar_colunas(_duas_colunas(linhas=5))) == 2, \
        "sem a linha atravessada, a calha da página curta continua sendo calha"
    # A mobília não é tolerância: o cabeçalho centrado fica fora da projeção
    # em qualquer página, curta ou não.
    assert len(BoxService.detectar_colunas(
        _duas_colunas(linhas=5) + _cabecalho())) == 2


def test_o_piso_esta_entre_o_recorte_e_a_pagina_de_prosa():
    """5 linhas é o recorte do teste da F1.6; 15 é a menor página do Nunn."""
    assert 5 < BoxService.LINHAS_PARA_TOLERAR < 15


# ----------------------------------------------------------------------
# O controle: a página de coluna única
# ----------------------------------------------------------------------

def _coluna_unica(linhas=20, n=65):
    """
    Texto corrido de margem a margem, com o espaço entre palavras andando.

    O deslocamento por linha é o que faz deste um controle e não um arranjo:
    numa página justificada de verdade o vão entre palavras cai num x diferente
    a cada linha, e é por isso que nenhum x central sobrevive à contagem.
    """
    boxes = []
    for i in range(linhas):
        boxes += _linha(i % 5, i * 30, n, rotulo=f"u{i}_")
    return boxes


def test_a_coluna_unica_nao_se_parte():
    assert len(BoxService.detectar_colunas(_coluna_unica())) == 1


def test_a_coluna_unica_com_cabecalho_nao_se_parte():
    """O controle que a F61 não tinha — o Aagaard não era de coluna única."""
    boxes = _coluna_unica() + _cabecalho(x1=600)
    assert len(BoxService.detectar_colunas(boxes)) == 1, \
        "a tolerância abriu calha onde há só texto corrido"


# ----------------------------------------------------------------------
# Nenhum box se perde
# ----------------------------------------------------------------------

def test_o_vao_da_margem_esquerda_nao_abre_faixa():
    """
    **O vão que encosta na margem esquerda não é calha.** Com o OR ele não tinha
    como existir — algum box começa em `x_min` por definição —, mas a tolerância
    o cria na página em que só o cabeçalho alcança a margem. Faixa aberta ali
    deixaria os boxes dele fora de toda coluna, e o `_por_colunas` os despeja no
    fim da página.
    """
    fora = _cabecalho(x1=-100, larg=25, rotulo="margem")
    boxes = _duas_colunas() + fora
    saida = BoxService.sort_boxes_reading_order(boxes)

    assert len(saida) == len(boxes), "sumiu box"
    assert saida[-1].char != "margem", \
        "o box da margem foi parar no fim da página"


def test_quem_mora_na_calha_nao_vai_para_o_fim():
    """
    **A calha certa é larga, e aí cabe gente dentro dela.** O `_por_colunas`
    despejava no fim da página o box que não caísse em faixa nenhuma — o que era
    inofensivo enquanto a calha tinha 20 px. Com os 56 px do Nunn, quem mora ali
    é o caractere central do cabeçalho, e ele saía depois da página inteira.
    """
    boxes = _duas_colunas() + _cabecalho()
    saida = BoxService.sort_boxes_reading_order(boxes)

    assert saida[-1].char != "cab", "o box da calha saiu depois da página toda"
    assert saida.index([b for b in saida if b.char == "cab"][0]) < len(boxes) // 2, \
        "o cabeçalho tem de ser lido no alto, e não perto do fim"


def test_nenhum_box_se_perde_com_o_cabecalho():
    boxes = _duas_colunas() + _cabecalho()
    saida = BoxService.sort_boxes_reading_order(boxes)
    assert sorted(id(b) for b in saida) == sorted(id(b) for b in boxes)


def test_a_ordem_de_leitura_deixa_de_intercalar():
    """O que a fase existe para consertar, visto de fora."""
    boxes = _duas_colunas() + _cabecalho()
    saida = [b.char for b in BoxService.sort_boxes_reading_order(boxes)]
    lados = [c[0] for c in saida if c and c[0] in "ed"]
    saltos = sum(1 for a, b in zip(lados, lados[1:]) if a != b)
    assert saltos == 1, f"a leitura pulou de coluna {saltos} vezes, e não 1"


def test_o_titulo_centrado_sobre_a_calha_sai_inteiro_e_antes():
    """
    «Solutions», centrado sobre as duas colunas da página 34 do Chess
    Evolution 1: letra a letra, nenhuma cruza a calha, mas a linha cruza. Saía
    partido — `Solu` no fim da esquerda, `tions` no começo da direita. A linha
    de mobília que cruza a calha é um elemento transversal: sai inteira, no
    lugar dela, antes do que está abaixo.
    """
    titulo = _linha(MEIO_DA_CALHA - 90, -60, 9, rotulo="t")   # 9 letras, 180 px
    saida = [b.char for b in BoxService.sort_boxes_reading_order(
        _duas_colunas() + titulo)]
    assert saida[:9] == [f"t{i}" for i in range(9)], saida[:12]
    lados = [c[0] for c in saida if c and c[0] in "ed"]
    assert sum(1 for a, b in zip(lados, lados[1:]) if a != b) == 1


def test_a_orelha_na_margem_nao_tira_o_titulo_da_mobilia():
    """
    A banda de `_linhas` junta ao título as letras da orelha do capítulo, lá
    na margem direita, na mesma altura. Julgada pela banda inteira, a linha
    deixava de ser compacta; julgada pelo maior grupo, o título continua sendo
    mobília e a orelha vai junto no elemento.
    """
    titulo = _linha(MEIO_DA_CALHA - 90, -60, 9, rotulo="t")
    orelha = [BoxEntry("o", INICIO_DA_DIREITA + 32 * 20 + 40, -55, INICIO_DA_DIREITA + 32 * 20 + 52, -35)]
    banda = titulo + orelha
    x_min, x_max = 0, INICIO_DA_DIREITA + 32 * 20 + 52
    assert [b.char for b in BoxService._nucleo_da_banda(banda)] == [f"t{i}" for i in range(9)]
    assert BoxService._e_mobilia(banda, x_min, x_max)
    saida = [b.char for b in BoxService.sort_boxes_reading_order(
        _duas_colunas() + banda)]
    assert saida[:10] == [f"t{i}" for i in range(9)] + ["o"]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
