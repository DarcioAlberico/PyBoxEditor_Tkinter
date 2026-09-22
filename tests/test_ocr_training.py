from __future__ import annotations

import json
from pathlib import Path

from core.ocr_training import (EngineTrainingStatus, OCRTrainingSummary,
                               salvar_estado)


def test_estado_do_pacote_e_serializavel(tmp_path: Path):
    resumo = OCRTrainingSummary(
        True, "ocr_language_model.json",
        [EngineTrainingStatus("EasyOCR", True, True, message="ok")],
        "ocr_training_state.json")
    caminho = salvar_estado(resumo, tmp_path / "estado.json")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    assert dados["line_model"] is True
    assert dados["engines"][0]["prepared"] is True
