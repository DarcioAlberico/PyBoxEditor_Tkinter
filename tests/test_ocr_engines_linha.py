from core.ocr_engines import OCRServiceAdapters
from core.linha_trainer import _imagem
import numpy as np


class _Servico:
    def paddleocr_ocr_conf(self, imagem, idioma, gpu):
        return "a", 0.8

    def paddleocr_linha_conf(self, imagem, idioma, gpu):
        return "a b", 0.9

    def linha_treinada_conf(self, imagem, modelo, meta):
        return "1. e4", 0.7


def test_adaptador_paddle_preserva_texto_da_linha():
    adapter = OCRServiceAdapters.paddleocr(_Servico())
    resultado = adapter.recognize(object(), level="line")
    assert resultado.text == "a b"
    assert resultado.metadata["line_model"] is True
    assert resultado.metadata["line_mode"] == "full_line"


def test_adaptador_modelo_local_eh_de_linha():
    adapter = OCRServiceAdapters.trained_line(_Servico())
    resultado = adapter.recognize(object(), level="line")
    assert resultado.text == "1. e4"
    assert resultado.metadata["engine"] == "custom_neural"
    assert resultado.metadata["line_model"] is True


def test_imagem_de_recorte_uint8_e_normalizada():
    matriz = _imagem(np.full((8, 16), 255, dtype=np.uint8))
    assert matriz.dtype == np.float32
    assert float(matriz.max()) == 0.0
