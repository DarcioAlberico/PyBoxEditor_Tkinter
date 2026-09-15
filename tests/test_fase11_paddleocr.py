import numpy as np

from core.services.ocr_service import OCRService


def test_resultado_paddle_api_3_extrai_texto_e_confianca():
    resultado = {"res": {"rec_text": "A1", "rec_score": 0.876}}
    assert OCRService._resultado_paddle(resultado) == ("A", 0.876)


def test_resultado_paddle_3_com_listas_e_resposta_vazia():
    assert OCRService._resultado_paddle({
        "res": {"rec_texts": ["B2"], "rec_scores": [0.734]},
    }) == ("B", 0.734)
    assert OCRService._resultado_paddle({
        "res": {"rec_texts": [], "rec_scores": []},
    }) == ("", 0.0)


def test_resultado_paddle_api_2_continua_compativel():
    resultado = [[[[0, 0], [1, 0], [1, 1], [0, 1]], ("z", 0.91)]]
    assert OCRService._resultado_paddle(resultado) == ("z", 0.91)


def test_paddleocr_usa_predict_e_cacheia_modelo(monkeypatch):
    class ModeloFalso:
        chamadas = 0

        def predict(self, *, input, batch_size):
            self.chamadas += 1
            assert input.shape == (12, 12, 3)
            assert batch_size == 1
            return iter([{"res": {"rec_text": "q", "rec_score": 0.8}}])

    modelo = ModeloFalso()
    service = OCRService()
    monkeypatch.setattr(service, "_init_paddleocr", lambda language, gpu: modelo)
    crop = np.zeros((12, 12), dtype=np.uint8)
    assert service.paddleocr_ocr_conf(crop) == ("q", 0.8)
    assert service.paddleocr_ocr_conf(crop) == ("q", 0.8)
    assert modelo.chamadas == 2


def test_paddleocr_informa_como_instalar_quando_backend_falta(monkeypatch):
    service = OCRService()

    def ausente(_language, _gpu):
        raise RuntimeError(
            "PaddleOCR não está disponível neste interpretador "
            "(módulo ausente: paddleocr). Instale com: "
            "python -m pip install -e \".[paddle]\""
        )

    monkeypatch.setattr(service, "_init_paddleocr", ausente)
    try:
        service.paddleocr_ocr_conf(np.zeros((4, 4), dtype=np.uint8))
    except RuntimeError as exc:
        assert ".[paddle]" in str(exc)
    else:
        raise AssertionError("backend ausente deveria gerar mensagem acionável")
