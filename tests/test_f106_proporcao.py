"""
F106 — o veto geométrico: a proporção que o esticão para 32×32 joga fora.

O primeiro teste é o motivo de a fase existir e não uma verificação de borda: se
um dia o pré-processamento passar a preservar proporção, ele falha, e o módulo
inteiro perde a razão de ser. Os outros travam o que faz a regra ser segura —
ela veta, não vota; não opina sobre quem não está no envelope; e sem substituta
devolve a leitura como estava, em vez de apagá-la.
"""

import cv2
import numpy as np
import pytest

from core import proporcao
from core.box_model import BoxEntry
from core.services.ocr_service import OCRService


def _box(x1, y1, x2, y2):
    return BoxEntry("?", x1, y1, x2, y2)


class PredictorFalso:
    """A rede que responde sempre o mesmo, com as candidatas na ordem dada."""

    loaded = True

    def __init__(self, candidatas):
        self.candidatas = list(candidatas)
        self.consultas = 0

    def predict(self, crop):
        return self.candidatas[0]

    def predict_topk(self, crop, k=3):
        self.consultas += 1
        return self.candidatas[:k]


# ----------------------------------------------------------------------
# O achado: o esticão apaga a diferença
# ----------------------------------------------------------------------

def test_a_barra_em_pe_e_a_deitada_viram_o_mesmo_recorte():
    """
    É a razão de existir do módulo, e não um caso de borda.

    `cv2.resize(g, (32, 32))` — o que `NeuralPredictor._probabilidades` e
    `CharacterLearner._quadrados_ate` fazem antes de olhar — não preserva
    proporção. Uma barra em pé e uma deitada não chegam *parecidas* ao
    classificador: chegam iguais byte a byte. Se isto passar a falhar, o
    pré-processamento mudou e o veto deixou de ser necessário.
    """
    em_pe = np.zeros((20, 5), np.uint8)
    deitada = np.zeros((5, 20), np.uint8)
    assert np.array_equal(cv2.resize(em_pe, (32, 32)),
                          cv2.resize(deitada, (32, 32)))


# ----------------------------------------------------------------------
# O envelope
# ----------------------------------------------------------------------

def test_o_travessao_nao_cabe_num_recorte_em_pe():
    assert not proporcao.cabe("—", 8, 19)
    assert not proporcao.cabe("-", 8, 19)
    assert proporcao.cabe("—", 24, 6)


def test_a_barra_em_pe_nao_cabe_num_recorte_deitado():
    assert not proporcao.cabe("I", 24, 6)
    assert not proporcao.cabe("l", 24, 6)
    assert proporcao.cabe("I", 8, 19)


def test_quem_nao_esta_no_envelope_nunca_e_vetado():
    """A regra não tem opinião sobre o resto do alfabeto, e não ter é dizer sim."""
    for char in "aeoxwmKQ♔♞":
        assert proporcao.cabe(char, 8, 19)
        assert proporcao.cabe(char, 24, 6)
        assert proporcao.cabe(char, 40, 40, 20)


def test_recorte_degenerado_passa():
    """Lado zero é problema de quem recortou, e dividir por ele seria pior."""
    assert proporcao.cabe("—", 0, 19)
    assert proporcao.cabe("—", 8, 0)


# ----------------------------------------------------------------------
# O ponto e o quadrado, que a proporção não separa
# ----------------------------------------------------------------------

def test_o_ponto_e_o_quadrado_so_se_separam_pelo_tamanho():
    """Os dois são quadrados; o que os distingue é serem pequeno e grande."""
    # Sem referência, a proporção admite os dois nos dois tamanhos.
    assert proporcao.cabe(".", 5, 5)
    assert proporcao.cabe("■", 5, 5)
    # Com ela — mediana de 20 px de altura na página — cada um fica no seu.
    assert proporcao.cabe(".", 5, 5, 20)
    assert not proporcao.cabe("■", 5, 5, 20)
    assert proporcao.cabe("■", 33, 33, 20)
    assert not proporcao.cabe(".", 33, 33, 20)


def test_sem_referencia_o_teste_de_tamanho_nao_roda():
    """
    Quem lê recorte a recorte não tem a página à mão, e ali a regra fica só com
    a proporção — não com um denominador inventado.
    """
    for referencia in (None, 0, 0.0):
        assert proporcao.cabe("■", 5, 5, referencia)


def test_a_altura_de_referencia_e_a_mediana_da_pagina():
    boxes = [_box(0, 0, 8, 19), _box(0, 0, 8, 20), _box(0, 0, 8, 20),
             _box(0, 0, 8, 21),
             _box(0, 0, 300, 300)]      # o diagrama, que a mediana ignora
    assert proporcao.altura_de_referencia(boxes) == 20.0


def test_altura_de_referencia_sem_boxes_e_none():
    assert proporcao.altura_de_referencia([]) is None
    assert proporcao.altura_de_referencia([_box(0, 5, 8, 5)]) is None


# ----------------------------------------------------------------------
# Escolher: veto, e não voto
# ----------------------------------------------------------------------

def test_escolher_pula_o_impossivel_e_mantem_a_ordem_de_quem_leu():
    """A regra não reordena nada — só desce a lista até uma que caiba."""
    candidatas = [("—", 0.60), ("-", 0.20), ("l", 0.10), ("I", 0.05)]
    assert proporcao.escolher(candidatas, 8, 19) == ("l", 0.10)


def test_escolher_sem_nenhuma_que_caiba_devolve_none():
    """
    `None` quer dizer "não tenho substituta", e quem chama fica com o que tinha.
    Inventar classe que o elo não ofereceu seria o voto que a F19 reprovou.
    """
    assert proporcao.escolher([("—", 0.9), ("-", 0.1)], 8, 19) is None


def test_escolher_devolve_a_primeira_quando_ela_ja_cabe():
    candidatas = [("l", 0.9), ("I", 0.1)]
    assert proporcao.escolher(candidatas, 8, 19) == ("l", 0.9)


# ----------------------------------------------------------------------
# Na cadeia
# ----------------------------------------------------------------------

def test_a_cadeia_troca_o_travessao_impossivel_pela_candidata_que_cabe():
    predictor = PredictorFalso([("—", 0.95), ("■", 0.90), ("l", 0.85)])
    char, fonte, conf = OCRService().fallback_chain(
        np.zeros((19, 8), np.uint8), predictor=predictor)
    assert (char, fonte, conf) == ("l", "neural", 0.85)


def test_a_fonte_da_leitura_nao_muda_com_o_veto():
    """
    A geometria não lê nada: ela veta e o mesmo elo dá a seguinte. Dizer
    "geometria" avisaria o roteamento e a fila de revisão de um classificador
    novo que não existe.
    """
    predictor = PredictorFalso([("—", 0.95), ("l", 0.85)])
    _char, fonte, _conf = OCRService().fallback_chain(
        np.zeros((19, 8), np.uint8), predictor=predictor)
    assert fonte == "neural"


def test_a_cadeia_nao_pede_candidatas_quando_a_leitura_cabe():
    """O caminho de sempre não paga nada por o veto existir."""
    predictor = PredictorFalso([("l", 0.95), ("I", 0.03)])
    OCRService().fallback_chain(np.zeros((19, 8), np.uint8),
                                predictor=predictor)
    assert predictor.consultas == 0


def test_a_confianca_que_sai_e_a_da_candidata_escolhida():
    """
    E não a do vetado. Ela roteia a cadeia e colore o box; herdar a confiança de
    uma resposta que a geometria acabou de derrubar seria afirmar o que não se
    mediu — aqui ela cai abaixo do limiar e o box vai ao elo seguinte.
    """
    predictor = PredictorFalso([("—", 0.99), ("l", 0.30)])
    servico = OCRService()
    _char, fonte, _conf = servico.fallback_chain(
        np.zeros((19, 8), np.uint8), predictor=predictor,
        learner=None, reader=_ReaderVazio())
    assert fonte == "none"


class _ReaderVazio:
    """Um EasyOCR que não acha nada — para o teste não subir o de verdade."""

    def recognize(self, *args, **kwargs):
        return []
