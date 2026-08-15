"""
F16 — o EasyOCR usado como reconhecedor, e não como detector.

Medido nos 2.278 caracteres das páginas rotuladas (`.box` + imagem real):

    como estava (readtext)              53,6%
    recognize() no lugar de readtext    66,7%
    + quantize=False                    66,9%
    + faixa vertical da linha           74,2%

Os três primeiros itens estão na primeira metade deste arquivo. O quarto tem
teste próprio no fim, porque o que ele conserta é geometria de box, e não
chamada de biblioteca.
"""

import sys

import numpy as np
import pytest

from core.box_model import BoxEntry
from core.services.box_service import faixas_de_linha
from core.services.ocr_service import OCRService


class _ReaderFalso:
    """Registra como foi chamado. **Não tem `readtext`**: chamar quebra."""

    def __init__(self, texto="x", conf=0.42):
        self.texto, self.conf = texto, conf
        self.imagens = []
        self.caixas = []

    def recognize(self, img, horizontal_list=None, free_list=None, detail=1):
        self.imagens.append(img)
        self.caixas.append(horizontal_list)
        return [([[0, 0]], self.texto, self.conf)]


def _crop(h=12, w=10, tom=255):
    return np.full((h, w), tom, dtype=np.uint8)


# ----------------------------------------------------------------------
# 1. Reconhecer sem detectar
# ----------------------------------------------------------------------

def test_nao_chama_mais_o_detector():
    """
    O box já veio do OpenCV; o CRAFT rodava de novo e devolvia vazio em 18%
    dos recortes. Um reader sem `readtext` prova que o caminho mudou.
    """
    svc = OCRService()
    r = _ReaderFalso("e", 0.9)
    assert svc.fallback_chain(_crop(), reader=r) == ("e", "easyocr", 0.9)
    assert len(r.imagens) == 1, "o reconhecedor não foi chamado"


def test_a_caixa_e_a_imagem_inteira():
    """Sem detector, quem diz onde está o texto é a chamada."""
    svc = OCRService()
    r = _ReaderFalso()
    svc.fallback_chain(_crop(h=12, w=10), reader=r)

    (caixa,) = r.caixas
    x1, x2, y1, y2 = caixa[0]
    alt, larg = r.imagens[0].shape[:2]
    assert (x1, y1) == (0, 0)
    assert (x2, y2) == (larg, alt), "a caixa não cobre a imagem toda"


def test_recognize_recebe_cinza():
    """`recognize` documenta `img_cv_grey`; passar RGB lê errado calado."""
    svc = OCRService()
    r = _ReaderFalso()
    svc.fallback_chain(np.full((12, 10, 3), 255, dtype=np.uint8), reader=r)
    assert r.imagens[0].ndim == 2


def test_rgba_nao_quebra():
    """PIL com canal alfa chegava ao cvtColor de 3 canais e levantava."""
    svc = OCRService()
    r = _ReaderFalso()
    assert svc.fallback_chain(
        np.full((12, 10, 4), 255, dtype=np.uint8), reader=r)[1] == "easyocr"


# ----------------------------------------------------------------------
# 2. O contexto de linha chega ao EasyOCR, e só a ele
# ----------------------------------------------------------------------

def test_o_contexto_substitui_o_recorte_justo():
    """
    Quem lê é o EasyOCR, e ele quer a faixa da linha — é nela que `c` deixa
    de ser igual a `C`.
    """
    justo, faixa = _crop(h=10), _crop(h=40)

    com = _ReaderFalso()
    OCRService().fallback_chain(justo, reader=com, contexto=faixa)
    sem = _ReaderFalso()
    OCRService().fallback_chain(justo, reader=sem)

    # O pré-processo padroniza a altura, então a prova está na proporção: o
    # recorte justo é quadrado, e a faixa da linha chega mais alta que larga.
    def proporcao(r):
        alt, larg = r.imagens[0].shape[:2]
        return alt / larg

    assert proporcao(com) > proporcao(sem), "chegou o recorte justo, não a faixa"


def test_sem_contexto_fica_como_estava():
    svc = OCRService()
    r = _ReaderFalso()
    svc.fallback_chain(_crop(h=10, w=10), reader=r)
    alt, larg = r.imagens[0].shape[:2]
    assert abs(alt - larg) <= 1, "sem faixa, o recorte deve ir justo"


def test_a_rede_e_o_knn_recebem_o_recorte_justo():
    """
    Eles treinaram no recorte justo. Mandar a faixa da linha para eles seria
    trocar um ganho medido no último elo por uma regressão nos dois primeiros.
    """
    vistos = {}

    class _Pred:
        loaded = True

        def predict(self, crop):
            vistos["neural"] = crop.shape
            return ("N", 0.1)

    class _Learner:
        # A cadeia consulta o k-NN por `predict_e_margem` desde a F44 — uma
        # busca só para a confiança e a margem.
        def predict_e_margem(self, crop):
            vistos["learner"] = crop.shape
            return ("R", 0.1, 0.5)

    svc = OCRService()
    justo, faixa = _crop(h=10), _crop(h=40)
    svc.fallback_chain(justo, predictor=_Pred(), learner=_Learner(),
                       reader=_ReaderFalso(), contexto=faixa)

    assert vistos["neural"] == justo.shape
    assert vistos["learner"] == justo.shape


# ----------------------------------------------------------------------
# 3. O cache do reader
# ----------------------------------------------------------------------

def test_cache_por_idioma_e_gpu(monkeypatch):
    """
    Era `if self._reader is None`: a segunda chamada com outro idioma recebia
    calada o reader da primeira.
    """
    criados = []

    class _EasyocrFalso:
        def Reader(self, langs, gpu=False, quantize=True, **kw):
            criados.append((tuple(langs), gpu, quantize))
            return _ReaderFalso()

    monkeypatch.setitem(sys.modules, "easyocr", _EasyocrFalso())

    svc = OCRService()
    svc._init_easyocr(("en",), False)
    svc._init_easyocr(("en",), False)      # mesmo par: reaproveita
    assert len(criados) == 1

    svc._init_easyocr(("pt",), False)      # outro idioma: reader novo
    svc._init_easyocr(("en",), True)       # outra gpu: reader novo
    assert len(criados) == 3
    assert {c[0] for c in criados} == {("en",), ("pt",)}


def test_quantize_desligado(monkeypatch):
    """Medido: quantizar não paga (66,7% contra 66,9%) e saiu 2x mais lento."""
    criados = []

    class _EasyocrFalso:
        def Reader(self, langs, gpu=False, quantize=True, **kw):
            criados.append(quantize)
            return _ReaderFalso()

    monkeypatch.setitem(sys.modules, "easyocr", _EasyocrFalso())
    OCRService()._init_easyocr()
    assert criados == [False]


def test_o_ssl_do_processo_e_restaurado(monkeypatch):
    """
    O remendo era global e permanente: a primeira chamada de OCR desligava a
    verificação de certificado do programa inteiro e nunca a religava.
    """
    import ssl

    class _EasyocrFalso:
        def Reader(self, langs, **kw):
            assert (ssl._create_default_https_context
                    is ssl._create_unverified_context), \
                "o remendo tem que valer durante o download do modelo"
            return _ReaderFalso()

    monkeypatch.setitem(sys.modules, "easyocr", _EasyocrFalso())

    antes = ssl._create_default_https_context
    OCRService()._init_easyocr()
    assert ssl._create_default_https_context is antes, \
        "a verificação de certificado ficou desligada no processo"


def test_o_ssl_volta_mesmo_se_o_reader_levantar(monkeypatch):
    import ssl

    class _EasyocrFalso:
        def Reader(self, langs, **kw):
            raise RuntimeError("sem rede")

    monkeypatch.setitem(sys.modules, "easyocr", _EasyocrFalso())

    antes = ssl._create_default_https_context
    with pytest.raises(RuntimeError):
        OCRService()._init_easyocr()
    assert ssl._create_default_https_context is antes


# ----------------------------------------------------------------------
# 4. A faixa vertical da linha
# ----------------------------------------------------------------------

def _linha(caixas):
    return [BoxEntry("a", x, y1, x + 8, y2) for x, y1, y2 in caixas]


def test_a_faixa_e_a_da_linha_inteira():
    """
    Um `o` de x-height entre duas maiúsculas tem que sair com a faixa das
    vizinhas — é a altura relativa dele nela que diz que ele é minúsculo.
    """
    boxes = _linha([(0, 10, 30), (10, 18, 30), (20, 10, 30)])
    assert faixas_de_linha(boxes) == [(10, 30), (10, 30), (10, 30)]


def test_linha_de_baixo_nao_entra():
    boxes = _linha([(0, 10, 30), (10, 10, 30)]) + _linha([(0, 60, 80)])
    assert faixas_de_linha(boxes) == [(10, 30), (10, 30), (60, 80)]


def test_o_diagrama_nao_estica_a_faixa():
    """Um bloco alto engoliria a linha toda e apagaria a pista de tamanho."""
    boxes = _linha([(0, 10, 30), (10, 10, 30)])
    boxes.append(BoxEntry("d", 40, 0, 300, 260))   # diagrama
    faixas = faixas_de_linha(boxes)
    assert faixas[0] == (10, 30) and faixas[1] == (10, 30)


def test_box_girado_fica_com_a_propria_caixa():
    """Para texto vertical (F8.1) a faixa da linha é horizontal; não mexer."""
    b = BoxEntry("a", 0, 10, 8, 30)
    b.angulo = 90
    vizinho = BoxEntry("b", 10, 5, 18, 35)
    assert faixas_de_linha([b, vizinho])[0] == (10, 30)


def test_sem_boxes():
    assert faixas_de_linha([]) == []


def test_a_faixa_nao_encadeia_pela_pagina():
    """
    Vizinhança de um salto, não fecho transitivo: com sobreposições parciais
    em cascata, um fecho levaria a faixa do primeiro até o último.
    """
    boxes = _linha([(0, 0, 20), (10, 14, 34), (20, 28, 48), (30, 42, 62)])
    assert faixas_de_linha(boxes)[0][1] < 48, "a faixa atravessou a cascata"
