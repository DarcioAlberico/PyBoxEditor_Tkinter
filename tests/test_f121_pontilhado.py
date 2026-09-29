"""
F121 — o pontilhado do sumário virava a régua de tamanho, e o ponto saía `'`.

O veto de tamanho da F106 mede o maior lado do recorte contra
`proporcao.altura_de_referencia`, a mediana da altura dos boxes da página. Num
sumário de pontilhado os pontos são a maioria dos boxes, a mediana vira a altura
de um ponto, e o ponto passa a medir 1,0 da referência — acima do 0,7 do `.`. A
rede dava então a candidata seguinte que cabe, e na p. 8 do Seirawan 1.431 dos
2.173 boxes saíam `'`.

Os primeiros testes reproduzem o defeito e falham sem a correção. Os outros
prendem o que a correção não pode mexer: a página comum fica com a mediana de
sempre, a página de rosto não troca o texto pelo título, e o que decide é o ponto
morar dentro da altura das letras da **própria linha**, e não o formato da
distribuição das alturas.
"""

import numpy as np

from core import proporcao
from core.box_model import BoxEntry
from core.services.learning_service import LearningService
from core.services.ocr_service import OCRService

#: A página de mentira tem as proporções da p. 8 do Seirawan: ponto de 6 px,
#: letra de altura de x 20 e maiúscula 28, todos na mesma base.
PONTO = 6
X = 20
MAIUSCULA = 28


class PredictorFalso:
    """A rede que lê o ponto como ponto, com o `'` logo atrás."""

    loaded = True

    def __init__(self, candidatas):
        self.candidatas = list(candidatas)

    def predict(self, crop):
        return self.candidatas[0]

    def predict_topk(self, crop, k=3):
        return self.candidatas[:k]


class _ReaderVazio:
    """Um EasyOCR que não acha nada — para o teste não subir o de verdade."""

    def recognize(self, *args, **kwargs):
        return []


def _letras(x, base, alturas):
    """Uma palavra: as letras lado a lado, todas apoiadas na mesma base."""
    boxes = []
    for h in alturas:
        boxes.append(BoxEntry("?", x, base - h, x + 12, base))
        x += 14
    return boxes, x


def _linha_do_sumario(base, pontos):
    """`Introdução ........ 17`: o título, o pontilhado e o número da página."""
    titulo, x = _letras(40, base, [MAIUSCULA] + [X] * 9)
    pontilhado = [BoxEntry("?", x + 10 + 12 * i, base - PONTO,
                           x + 10 + 12 * i + PONTO, base)
                  for i in range(pontos)]
    numero, _x = _letras(x + 20 + 12 * pontos, base, [MAIUSCULA] * 2)
    return titulo + pontilhado + numero


def _sumario(linhas=20, pontos=40):
    boxes = []
    for i in range(linhas):
        boxes += _linha_do_sumario(100 + 45 * i, pontos)
    return boxes


def _linha_de_texto(base, letras=40):
    """Prosa: três em cada cinco letras na altura de x, e um ponto no fim."""
    alturas = [MAIUSCULA if i % 5 in (1, 3) else X for i in range(letras)]
    boxes, x = _letras(40, base, alturas)
    return boxes + [BoxEntry("?", x, base - PONTO, x + PONTO, base)]


# ----------------------------------------------------------------------
# O defeito
# ----------------------------------------------------------------------

def test_no_sumario_o_ponto_cabe_como_ponto():
    """
    O achado da F112, reduzido. Sem a correção a referência é a altura do
    ponto, e o `.` de 6×6 mede 1,0 dela: o veto o recusa.
    """
    boxes = _sumario()
    pontos = sum(1 for b in boxes if b.y2 - b.y1 == PONTO)
    assert pontos > 0.75 * len(boxes)   # os pontos são a maioria, como lá

    referencia = proporcao.altura_de_referencia(boxes)

    assert proporcao.cabe(".", PONTO, PONTO, referencia)


def test_no_sumario_a_referencia_e_a_das_letras():
    referencia = proporcao.altura_de_referencia(_sumario())
    assert X <= referencia <= MAIUSCULA


def test_no_sumario_o_ponto_sai_ponto_pela_janela():
    """
    O caminho da janela inteiro: a cadeia recebe a referência da página e a rede
    lê `.`. Sem a correção o `.` é vetado e sai a candidata seguinte, o `'`.
    """
    referencia = proporcao.altura_de_referencia(_sumario())
    predictor = PredictorFalso([(".", 0.92), ("'", 0.05), (",", 0.02)])

    char, fonte, _conf = OCRService().fallback_chain(
        np.full((PONTO, PONTO), 0, np.uint8), predictor=predictor,
        reader=_ReaderVazio(), altura_de_referencia=referencia, idioma="pt")

    assert (char, fonte) == (".", "neural")


def test_no_sumario_o_ponto_sai_ponto_pelo_ler_texto():
    """`LearningService.ler_texto(recorte, referencia)`, a porta do achado."""
    servico = LearningService()
    servico._predictor = PredictorFalso([(".", 0.92), ("'", 0.05)])
    referencia = proporcao.altura_de_referencia(_sumario())

    char, _conf = servico.ler_texto(np.full((PONTO, PONTO), 0, np.uint8),
                                    referencia, idioma="pt")

    assert char == "."


def test_no_sumario_o_quadrado_continua_quadrado():
    """
    O par que o veto de tamanho existe para separar continua separado: o ponto
    do sumário não vira `■`, e um `■` do tamanho de uma maiúscula não vira `.`.
    """
    referencia = proporcao.altura_de_referencia(_sumario())
    assert not proporcao.cabe("■", PONTO, PONTO, referencia)
    assert proporcao.cabe("■", 34, 34, referencia)
    assert not proporcao.cabe(".", 34, 34, referencia)


def test_o_pontilhado_quase_todo_ainda_acha_as_letras():
    """
    Uma fração alta não fecha a regra. É o que reprovou o percentil: na p. 8 do
    Seirawan os pontos são 85% dos boxes e o p75 da altura já é de ponto; aqui
    são 90%, e com o p90 também seria.
    """
    boxes = _sumario(pontos=110)
    pontos = sum(1 for b in boxes if b.y2 - b.y1 == PONTO)
    assert pontos > 0.9 * len(boxes)

    referencia = proporcao.altura_de_referencia(boxes)

    assert X <= referencia <= MAIUSCULA
    assert proporcao.cabe(".", PONTO, PONTO, referencia)


# ----------------------------------------------------------------------
# O que a correção não pode mexer
# ----------------------------------------------------------------------

def test_a_pagina_comum_fica_com_a_mediana_de_sempre():
    """
    Numa página de prosa o ponto é minoria e a regra não fala: a referência é a
    mediana até o último pixel. É sobre ela que o envelope da F106 foi medido.
    """
    boxes = []
    for i in range(30):
        boxes += _linha_de_texto(100 + 45 * i)
    alturas = sorted(b.y2 - b.y1 for b in boxes)

    assert proporcao.altura_de_referencia(boxes) == float(
        alturas[len(alturas) // 2])


def test_a_pagina_de_rosto_nao_troca_o_texto_pelo_titulo():
    """
    A distribuição sozinha não separa esta página do sumário: 85% de boxes
    pequenos e 15% de letras quatro vezes maiores, como lá. O que separa é que
    o texto não mora na linha do título — e a referência fica com o texto.
    """
    boxes = []
    for i in range(3):                        # o título, em três linhas
        boxes += _letras(40, 300 + 150 * i, [100] * 10)[0]
    for i in range(10):                       # o texto, abaixo
        boxes += _letras(40, 900 + 45 * i, [35] * 17)[0]
    grandes = sum(1 for b in boxes if b.y2 - b.y1 == 100)
    assert 0.1 < grandes / len(boxes) < 0.2

    assert proporcao.altura_de_referencia(boxes) == 35.0


def test_a_moldura_nao_abriga_a_pagina():
    """
    Um box dez vezes mais alto que a mediana não é letra: é moldura, fio de
    tabela, figura. A faixa dele cobriria todas as linhas, e a página inteira
    passaria por pontilhado.
    """
    boxes = []
    for i in range(30):
        boxes += _letras(40, 100 + 45 * i, [X] * 12)[0]
    boxes.append(BoxEntry("?", 10, 60, 1200, 1500))  # o quadro em volta

    assert proporcao.altura_de_referencia(boxes) == float(X)


def test_o_ponto_abaixo_da_base_continua_na_linha():
    """
    A faixa pede o centro do miúdo, e não ele inteiro: o ponto que desce um
    pixel abaixo da base das letras continua sendo da linha delas.
    """
    boxes = []
    for b in _sumario():
        if b.y2 - b.y1 == PONTO:
            b = BoxEntry("?", b.x1, b.y1 + 1, b.x2, b.y2 + 1)
        boxes.append(b)

    assert X <= proporcao.altura_de_referencia(boxes) <= MAIUSCULA


def test_miudo_que_nao_mora_em_linha_nao_e_pontilhado():
    """
    A regra pergunta à linha, e não ao tamanho. Miúdos que não moram na altura
    de letra nenhuma — o cisco entre as linhas de uma página suja — não são
    pontilhado, e a referência fica com a mediana, como era antes da F121.
    """
    boxes = []
    for i in range(10):
        base = 100 + 90 * i
        boxes += _letras(40, base, [MAIUSCULA] + [X] * 9)[0]
        boxes += [BoxEntry("?", 40 + 12 * k, base + 30, 40 + 12 * k + PONTO,
                           base + 30 + PONTO) for k in range(20)]

    assert proporcao.altura_de_referencia(boxes) == float(PONTO)
