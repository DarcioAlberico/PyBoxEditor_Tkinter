"""
PD-04 — o bloco de largura inteira deixa de apagar a calha. PD-11 — a linha de
prosa encostada no tabuleiro deixa de virar título.

**PD-04.** A F70 tolera uma linha na calha, e a mobília (título centrado, número
da página) fica fora da conta. Sobravam os blocos de largura inteira que não são
mobília: no Nunn, o título de seção com o sumário dele no meio da página (duas
colunas em cima, cinco linhas de lado a lado, duas colunas embaixo); no
Yusupov, o quadro «Scoring» e o parágrafo em itálico do fim de todo capítulo,
embaixo das duas colunas das soluções. A página saía de uma coluna só, com as
duas intercaladas. `BoxService._calha_por_blocos` parte a página pelos vãos
verticais e acha a calha no maior bloco; o bloco que ela rejeita sai, na ordem
de leitura, no lugar dele (`_colunas_e_transversais`).

**PD-11.** A faixa do diagrama recolhia o fim de uma linha de prosa encostada no
topo do tabuleiro (Darcy Lima, p. 144: `A essência deste método`). A letra dentro
do retângulo de exclusão acima da borda passa a poder voltar pela vizinhança,
como já voltava a que a faixa pegava pelo pé.

**PD-05.** Duas faixas de largura muito desigual cujas linhas casam fileira a
fileira são uma tabela sem moldura (o glossário de símbolos), e a calha estreita
da régua adaptada só vale entre colunas de texto.

Os testes de geometria montam as caixas à mão; os do fim rodam sobre o Nunn, o
Yusupov e o Darcy Lima quando eles e o modelo estão na máquina.
"""

import glob
import os
import random

import pytest

from core.box_model import BoxEntry
from core.services.box_service import BoxService

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LARG, ALT, PASSO_X, PASSO_Y = 17, 22, 20, 30
N_COLUNA = 20                       # caracteres por linha de coluna
CALHA = 40
DIREITA = N_COLUNA * PASSO_X + CALHA


def _linha(x, y, n, rotulo):
    return [BoxEntry(rotulo, x + i * PASSO_X, y, x + i * PASSO_X + LARG, y + ALT)
            for i in range(n)]


def _duas_colunas(y0, linhas, rotulo):
    caixas = []
    for i in range(linhas):
        y = y0 + i * PASSO_Y
        caixas += _linha(0, y, N_COLUNA, f"{rotulo}e{i}")
        caixas += _linha(DIREITA, y, N_COLUNA, f"{rotulo}d{i}")
    return caixas


def _bloco_largo(y0, linhas, rotulo, x=0, n=None):
    n = n or (DIREITA + N_COLUNA * PASSO_X) // PASSO_X
    return [b for i in range(linhas)
            for b in _linha(x, y0 + i * PASSO_Y, n, f"{rotulo}{i}")]


def _rotulos_em_ordem(caixas):
    vistos = []
    for b in BoxService.sort_boxes_reading_order(caixas):
        if not vistos or vistos[-1] != b.char:
            vistos.append(b.char)
    return vistos


def _sumario_no_meio():
    """A p. 128 do Nunn: 8 linhas em duas colunas, 4 de lado a lado, 8 em duas."""
    return (_duas_colunas(0, 8, "a")
            + _bloco_largo(8 * PASSO_Y + 60, 4, "s")
            + _duas_colunas(8 * PASSO_Y + 60 + 4 * PASSO_Y + 60, 8, "b"))


# ----------------------------------------------------------------------
# A calha
# ----------------------------------------------------------------------

def test_o_sumario_no_meio_da_pagina_nao_apaga_a_calha():
    colunas = BoxService.detectar_colunas(_sumario_no_meio())
    assert len(colunas) == 2, colunas
    assert colunas[0][1] < DIREITA and colunas[1][0] > N_COLUNA * PASSO_X - PASSO_X


def test_sem_os_blocos_a_pagina_saia_de_uma_coluna(monkeypatch):
    """O defeito: as quatro linhas largas passam da linha tolerada."""
    monkeypatch.setattr(BoxService, "_calha_por_blocos",
                        staticmethod(lambda *a: ([], [])))
    assert len(BoxService.detectar_colunas(_sumario_no_meio())) == 1


def test_a_ordem_le_as_colunas_de_cima_o_sumario_e_as_de_baixo():
    ordem = _rotulos_em_ordem(_sumario_no_meio())
    esperado = ([f"ae{i}" for i in range(8)] + [f"ad{i}" for i in range(8)]
                + [f"s{i}" for i in range(4)]
                + [f"be{i}" for i in range(8)] + [f"bd{i}" for i in range(8)])
    assert ordem == esperado


def test_o_quadro_scoring_embaixo_e_a_orelha_na_margem():
    """O Yusupov: 14 linhas em duas colunas, a orelha do capítulo girada na
    margem esquerda (que abre um vão espúrio, e ele se funde), e o quadro
    centrado embaixo, mais estreito que a página mas cruzando a calha."""
    orelha = [BoxEntry("o", -40, i * PASSO_Y, -25, i * PASSO_Y + ALT) for i in range(4)]
    largura = DIREITA + N_COLUNA * PASSO_X
    quadro = _bloco_largo(14 * PASSO_Y + 80, 4, "q", x=largura // 4,
                          n=largura // 2 // PASSO_X)
    caixas = orelha + _duas_colunas(0, 14, "") + quadro
    colunas = BoxService.detectar_colunas(caixas)
    assert len(colunas) == 2, colunas
    ordem = _rotulos_em_ordem([b for b in caixas if b.char != "o"])
    assert ordem[-4:] == [f"q{i}" for i in range(4)]
    assert ordem[:14] == [f"e{i}" for i in range(14)]


def test_pagina_de_coluna_unica_com_bloco_separado_continua_uma():
    """O controle: prosa justificada — o espaço entre palavras cai num x
    diferente a cada linha — com um título e um bloco apartados."""
    sorteio = random.Random(7)
    caixas = []
    y = 0
    for bloco in (2, 14, 3, 9):
        for _ in range(bloco):
            x, linha = 0, []
            while x < 820:
                palavra = sorteio.randint(2, 9)
                linha += _linha(x, y, palavra, "p")
                x += palavra * PASSO_X + 12
            caixas += linha
            y += PASSO_Y
        y += 70
    assert len(BoxService.detectar_colunas(caixas)) == 1


def test_pagina_que_a_f70_ja_lia_nao_ganha_transversal():
    """Três linhas das duas colunas apartadas do resto (um diagrama embaixo
    delas) e um caractere avançando sobre a calha: a régua da F70 tolera a
    linha, e a ordem fica a de antes — coluna a coluna. A primeira versão
    chamava o bloco de cima de transversal e o lia de lado a lado."""
    caixas = _duas_colunas(0, 3, "a") + _duas_colunas(3 * PASSO_Y + 200, 12, "b")
    caixas.append(BoxEntry("ae0", N_COLUNA * PASSO_X + 5, 0,
                           N_COLUNA * PASSO_X + 5 + LARG, ALT))
    colunas, transversais = BoxService._colunas_e_transversais(caixas)
    assert len(colunas) == 2
    assert transversais == []
    ordem = _rotulos_em_ordem(caixas)
    assert ordem[:6] == ["ae0", "ae1", "ae2", "be0", "be1", "be2"]


def test_a_calha_estreita_nao_abre_coluna_de_dez_por_cento():
    """PD-05: o Seirawan. Texto de coluna única com um espaço entre palavras
    alinhado em todas as linhas a 13% da largura, mais estreito que a régua
    (0,8 caractere) e mais largo que a adaptada (0,55): ela o aceitava, e o
    começo de cada linha saía antes de todo o resto."""
    caixas = []
    for i in range(20):
        y = i * PASSO_Y
        caixas += _linha(0, y, 7, f"a{i}")
        caixas += _linha(7 * PASSO_X - 3 + 11, y, 43, f"b{i}")
    assert len(BoxService.detectar_colunas(caixas)) == 1


def test_a_calha_estreita_entre_colunas_de_texto_continua():
    """A calha estreita do Yusupov, entre duas colunas de meia página."""
    caixas = []
    for i in range(20):
        y = i * PASSO_Y
        caixas += _linha(0, y, N_COLUNA, f"e{i}")
        caixas += _linha(N_COLUNA * PASSO_X - 3 + 11, y, N_COLUNA, f"d{i}")
    assert len(BoxService.detectar_colunas(caixas)) == 2


def _glossario():
    """O glossário do Darcy Lima: símbolo à esquerda, descrição à direita,
    fileira a fileira."""
    caixas = []
    for i in range(15):
        y = i * PASSO_Y
        caixas += _linha(0, y, 6, f"s{i}")
        caixas += _linha(6 * PASSO_X + 60, y, 32 - i % 5, f"d{i}")
    return caixas


def test_o_glossario_sai_fileira_a_fileira():
    """PD-05: lido como duas colunas, saíam todos os símbolos e depois todas
    as descrições."""
    assert len(BoxService.detectar_colunas(_glossario())) == 1
    ordem = _rotulos_em_ordem(_glossario())
    assert ordem[:4] == ["s0", "d0", "s1", "d1"]


def test_sem_a_regra_o_glossario_saia_em_duas_colunas(monkeypatch):
    monkeypatch.setattr(BoxService, "_e_tabela", staticmethod(lambda *a: False))
    assert len(BoxService.detectar_colunas(_glossario())) == 2


def test_colunas_de_texto_nao_sao_tabela():
    """As duas colunas do Nunn casam fileira a fileira também, mas têm a
    mesma largura."""
    assert len(BoxService.detectar_colunas(_duas_colunas(0, 15, ""))) == 2


def test_blocos_cortam_na_folga_e_nao_no_entrelinha():
    caixas = _sumario_no_meio()
    blocos = BoxService._blocos(BoxService._linhas(caixas))
    assert [len(b) for b in blocos] == [8, 4, 8]


# ----------------------------------------------------------------------
# Os livros, quando estão na máquina
# ----------------------------------------------------------------------

def _pdf(padrao):
    pasta = os.environ.get("PDF_DO_CORPUS") or os.path.join(RAIZ, "PDF")
    achados = sorted(glob.glob(os.path.join(pasta, padrao)))
    if not achados:
        pytest.skip(f"PDF do corpus ausente: {padrao}")
    return achados[0]


@pytest.fixture(scope="module")
def ler():
    from config import paths
    if not paths.caminhos_dos_pesos()["glifos"].exists():
        pytest.skip("custom_model.pth fica fora do git")
    from core.services.learning_service import LearningService
    servico = LearningService()
    if not servico.load_predictor():
        pytest.skip(servico.motivo_do_modelo())
    return servico.ler_texto


def _colunas(caminho, pagina, ler):
    import fitz
    from core import livro
    with fitz.open(caminho) as doc:
        img = livro._pagina_cinza(doc[pagina - 1], 300)
    return livro.caixas_e_diagramas(img, ler)


@pytest.mark.slow
@pytest.mark.parametrize("pagina", [128, 202, 210])
def test_nunn_o_sumario_da_secao(ler, pagina):
    caminho = _pdf("Nunn*/*.pdf")
    assert len(_colunas(caminho, pagina, ler)[4]) == 2


@pytest.mark.slow
@pytest.mark.parametrize("pagina", [131, 946, 1896])
def test_yusupov_o_quadro_scoring(ler, pagina):
    caminho = _pdf("Yusupov_Artur_Complete/*.pdf")
    assert len(_colunas(caminho, pagina, ler)[4]) == 2


@pytest.mark.slow
def test_darcy_a_linha_encostada_no_tabuleiro_volta_a_prosa(ler):
    caminho = _pdf("Darcy*/*.pdf")
    _caixas, diagramas, *_ = _colunas(caminho, 143, ler)
    assert all(not getattr(d, "caixas_da_faixa", None) or d.faixa is None
               or len(d.caixas_da_faixa) < 3 for d in diagramas)
