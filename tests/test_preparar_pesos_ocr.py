from __future__ import annotations

from pathlib import Path

from core.services.ocr_service import OCRService


def test_preparar_easyocr_encaminha_idiomas_gpu_e_diretorio(monkeypatch, tmp_path: Path):
    service = OCRService()
    chamadas = []

    def fake_init(languages, gpu, model_storage_directory=None):
        chamadas.append((languages, gpu, model_storage_directory))
        return object()

    monkeypatch.setattr(service, "_init_easyocr", fake_init)
    service.preparar_easyocr(("en", "pt"), True, str(tmp_path))
    assert chamadas == [(('en', 'pt'), True, str(tmp_path))]
