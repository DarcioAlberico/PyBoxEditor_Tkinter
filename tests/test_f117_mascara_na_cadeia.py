"""
F117 — a máscara de alfabeto chega à cadeia, e a tela passa o idioma do livro.

A F109 pôs a máscara em `LearningService.ler_texto`, que só o caminho do livro
chama. As duas ações «Detectar e Preencher» leem pela cadeia de
`ocr_service`, que não a tinha — na tela `É` e `ê` continuavam competindo num
livro em inglês. Aqui a máscara entra na cadeia com a forma do veto da F106
(filtra as candidatas e escolhe entre as que sobram), vale para a rede **e**
para o k-NN, e a janela descobre o idioma uma vez por documento.
"""

import inspect
import os
import sys

import numpy as np
import pytest

from core.box_model import SEM_MARGEM
from core.services.ocr_service import OCRService


class _PredictorFalso:
    loaded = True

    def __init__(self, candidatas):
        self.candidatas = list(candidatas)
        self.consultas = 0

    def predict(self, _crop):
        return self.candidatas[0]

    def predict_topk(self, _crop, k=3):
        self.consultas += 1
        return self.candidatas[:k]


class _LearnerFalso:
    def __init__(self, candidatas, margem=0.8):
        self.lista = list(candidatas)
        self.margem = margem
        self.consultas = 0

    def predict_e_margem(self, _crop):
        char, conf = self.lista[0]
        return char, conf, self.margem

    def candidatas(self, _crop, n=5):
        self.consultas += 1
        return self.lista[:n]


class _ReaderVazio:
    def recognize(self, *args, **kwargs):
        return []


# Proporção neutra: a geometria da F106 não opina.
_RECORTE = np.zeros((20, 14), np.uint8)


def _cadeia(**kw):
    return OCRService().fallback_chain_detalhado(
        _RECORTE, reader=_ReaderVazio(), neural_threshold=0.5,
        learner_threshold=0.5, **kw)


# ----------------------------------------------------------------------
# Na rede
# ----------------------------------------------------------------------

def test_a_rede_cai_para_a_candidata_que_o_idioma_admite():
    p = _PredictorFalso([("É", 0.90), ("E", 0.85), ("F", 0.10)])
    leitura = _cadeia(predictor=p, idioma="en")
    assert (leitura.char, leitura.fonte, leitura.confianca) == ("E", "neural", 0.85)


def test_sem_idioma_a_cadeia_e_a_de_antes():
    p = _PredictorFalso([("É", 0.90), ("E", 0.85)])
    leitura = _cadeia(predictor=p)
    assert (leitura.char, leitura.confianca) == ("É", 0.90)
    assert p.consultas == 0, "o caminho de sempre não paga nada"


def test_no_portugues_o_acento_fica():
    p = _PredictorFalso([("ç", 0.90), ("c", 0.85)])
    assert _cadeia(predictor=p, idioma="pt").char == "ç"


def test_a_mascara_e_a_geometria_valem_juntas_na_rede():
    """A candidata que o idioma admite ainda precisa caber no recorte."""
    p = _PredictorFalso([("É", 0.90), ("—", 0.80), ("E", 0.70)])
    alto = np.zeros((19, 8), np.uint8)       # em pé: o travessão não cabe
    leitura = OCRService().fallback_chain_detalhado(
        alto, predictor=p, reader=_ReaderVazio(), neural_threshold=0.5,
        idioma="en")
    assert leitura.char == "E"


def test_sem_candidata_admitida_a_leitura_fica_e_a_confianca_tambem():
    p = _PredictorFalso([("É", 0.90), ("Š", 0.80)])
    leitura = _cadeia(predictor=p, idioma="en")
    assert (leitura.char, leitura.confianca) == ("É", 0.90)


# ----------------------------------------------------------------------
# No k-NN — as classes são as mesmas pastas, com as mesmas letras acentuadas
# ----------------------------------------------------------------------

def test_o_knn_tambem_e_mascarado():
    learner = _LearnerFalso([("ê", 0.95), ("e", 0.90)])
    leitura = _cadeia(learner=learner, idioma="en")
    assert (leitura.char, leitura.fonte, leitura.confianca) == ("e", "learner", 0.90)
    assert leitura.margem == SEM_MARGEM, "a margem media o vencedor derrubado"


def test_o_knn_sem_idioma_nao_pede_candidatas():
    learner = _LearnerFalso([("ê", 0.95), ("e", 0.90)])
    leitura = _cadeia(learner=learner)
    assert leitura.char == "ê"
    assert learner.consultas == 0


def test_a_rede_mascarada_abaixo_do_limiar_passa_ao_knn():
    """A confiança que sai é a da candidata escolhida, e é ela que roteia."""
    p = _PredictorFalso([("É", 0.90), ("E", 0.20)])
    learner = _LearnerFalso([("E", 0.95)])
    leitura = _cadeia(predictor=p, learner=learner, idioma="en")
    assert leitura.fonte == "learner"


def test_fallback_chain_repassa_o_idioma():
    p = _PredictorFalso([("É", 0.90), ("E", 0.85)])
    char, fonte, _conf = OCRService().fallback_chain(
        _RECORTE, predictor=p, reader=_ReaderVazio(), neural_threshold=0.5,
        idioma="en")
    assert (char, fonte) == ("E", "neural")


# ----------------------------------------------------------------------
# A janela: o idioma do documento, uma vez por documento
# ----------------------------------------------------------------------

def _janela():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from conftest import raiz_tk
    from ui.main_window import MainWindow

    raiz = raiz_tk()
    if raiz is None:
        return None, None
    return raiz, MainWindow(raiz)


def test_imagem_solta_fica_sem_idioma_e_sem_pergunta(monkeypatch):
    from tkinter import messagebox
    from core.services.document_service import DocumentSession

    raiz, win = _janela()
    if win is None:
        pytest.skip("sem display")
    try:
        perguntas = []
        monkeypatch.setattr(messagebox, "askyesno",
                            lambda *a, **k: perguntas.append(1) or True)
        win.session = DocumentSession("pagina.png", num_pages=1, is_pdf=False)
        win._esquecer_lexico()
        assert win.idioma_da_sessao() is None
        assert perguntas == []
    finally:
        raiz.destroy()


def test_o_pdf_com_camada_de_texto_responde_sem_perguntar(monkeypatch):
    from tkinter import messagebox
    from core import livro
    from core.services.document_service import DocumentSession

    raiz, win = _janela()
    if win is None:
        pytest.skip("sem display")
    try:
        lidas = []
        monkeypatch.setattr(livro, "idioma_do_pdf",
                            lambda caminho, *a, **k: lidas.append(caminho) or "en")
        monkeypatch.setattr(messagebox, "askyesno",
                            lambda *a, **k: pytest.fail("não devia perguntar"))
        win.session = DocumentSession("livro.pdf", num_pages=3, is_pdf=True)
        win._esquecer_lexico()

        assert win.idioma_da_sessao() == "en"
        assert win.idioma_da_sessao() == "en"
        assert lidas == ["livro.pdf"], "conferido uma vez por documento"
    finally:
        raiz.destroy()


def test_a_digitalizacao_pergunta_uma_vez_e_o_proximo_documento_de_novo(monkeypatch):
    from tkinter import messagebox
    from core import livro
    from core.services.document_service import DocumentSession

    raiz, win = _janela()
    if win is None:
        pytest.skip("sem display")
    try:
        monkeypatch.setattr(livro, "idioma_do_pdf", lambda *a, **k: None)
        perguntas = []
        monkeypatch.setattr(messagebox, "askyesno",
                            lambda *a, **k: perguntas.append(1) or True)
        win.session = DocumentSession("scan.pdf", num_pages=3, is_pdf=True)
        win._esquecer_lexico()

        assert win.idioma_da_sessao() == "pt"
        assert win.idioma_da_sessao() == "pt"
        assert len(perguntas) == 1

        win.session = DocumentSession("outro.pdf", num_pages=3, is_pdf=True)
        win._esquecer_lexico()
        win.idioma_da_sessao()
        assert len(perguntas) == 2, "outro documento, outra pergunta"
    finally:
        raiz.destroy()


def test_as_duas_acoes_e_a_exportacao_passam_o_mesmo_idioma():
    """
    Uma pergunta só (`_idioma_do_livro`), três consumidores: a exportação e as
    duas ações «Detectar e Preencher». Um caminho sem `idioma=` seria a tela
    voltando a competir com o `É` num livro em inglês.
    """
    from ui.main_window import MainWindow

    for acao in ("generate_and_fill_neural", "generate_and_fill_combined"):
        fonte = inspect.getsource(getattr(MainWindow, acao))
        assert "idioma_da_sessao()" in fonte, acao
        assert "idioma=idioma" in fonte, acao
    assert "_idioma_do_livro(" in inspect.getsource(MainWindow.idioma_da_sessao)
    assert "_idioma_do_livro(input_pdf)" in inspect.getsource(MainWindow)
