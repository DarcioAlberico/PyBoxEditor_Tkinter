from core.ocr_engines import OCRServiceAdapters
import numpy as np


class _Servico:
    def tesseract_ocr_conf(self, imagem):
        return "t", 0.6

    def tesseract_linha_conf(self, imagem, idioma="en"):
        self.idioma_do_tesseract = idioma
        return "tesseract line", 0.65

    def easyocr_ocr_conf(self, imagem, idiomas, gpu):
        return "e", 0.7

    def easyocr_linha_conf(self, imagem, idiomas, gpu):
        return "easy line", 0.8

    def paddleocr_ocr_conf(self, imagem, idioma, gpu):
        return "p", 0.5

    def paddleocr_linha_conf(self, imagem, idioma, gpu):
        return "paddle line", 0.75

    def linha_treinada_conf(self, imagem, modelo, meta):
        return "trained line", 0.9


def test_registry_expoe_todos_os_adapters_de_linha():
    registry = OCRServiceAdapters.registry(_Servico(), languages=("en", "pt"),
                                           trained_line=True)
    resultado = registry.recognize(np.zeros((4, 4), dtype=np.uint8), level="line")
    assert {item.source for item in resultado.hypotheses} == {
        "tesseract", "easyocr", "paddleocr", "trained_line"}
    assert {item.text for item in resultado.hypotheses} == {
        "tesseract line", "easy line", "paddle line", "trained line"}


def test_registry_encaminha_checkpoint_de_linha():
    registry = OCRServiceAdapters.registry(
        _Servico(), model_path="modelos/linha.pth",
        meta_path="modelos/linha.json", trained_line=True)
    treinado = next(item for item in registry.adapters if item.name == "trained_line")
    assert treinado.metadata["model_path"] == "modelos/linha.pth"


def test_o_idioma_chega_ao_tesseract():
    """`registry(language="pt")` configurava o EasyOCR e o PaddleOCR em
    português e o Tesseract, sem parâmetro de idioma, lia sempre em inglês."""
    servico = _Servico()
    registry = OCRServiceAdapters.registry(servico, language="pt",
                                           languages=("pt",), trained_line=False)
    registry.recognize(np.zeros((4, 4), dtype=np.uint8), level="line")
    assert servico.idioma_do_tesseract == "pt"


def test_sem_trained_line_o_portao_de_producao_decide(tmp_path):
    """O modelo de linha só entra no registro se passa no portão: com CER de
    validação acima do limite (o treinado em 2026-09-17 estava em 96%) ele
    fica de fora, e com CER abaixo entra."""
    import json
    pesos = tmp_path / "linha.pth"
    pesos.write_bytes(b"x")
    meta = tmp_path / "linha.json"
    meta.write_text(json.dumps({"historico": [{"perda_validacao": 1.0, "cer": 0.96}]}),
                    encoding="utf-8")
    registry = OCRServiceAdapters.registry(_Servico(), model_path=str(pesos),
                                           meta_path=str(meta))
    assert "trained_line" not in {item.name for item in registry.adapters}

    meta.write_text(json.dumps({"historico": [{"perda_validacao": 1.0, "cer": 0.04}]}),
                    encoding="utf-8")
    registry = OCRServiceAdapters.registry(_Servico(), model_path=str(pesos),
                                           meta_path=str(meta))
    assert "trained_line" in {item.name for item in registry.adapters}
