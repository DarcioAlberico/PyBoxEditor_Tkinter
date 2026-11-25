"""A ortografia não puxa o OpenCV (RG-20, R-46)."""

import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("modulo", ["core.editor.ortografia", "core.notacao"])
def test_o_import_nao_traz_o_opencv(modulo):
    codigo = (f"import sys, {modulo}; "
              "print([m for m in ('cv2', 'torch', 'core.services.box_service') if m in sys.modules])")
    saida = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True,
                           encoding="utf-8", timeout=120)
    assert saida.returncode == 0, saida.stderr
    assert saida.stdout.strip() == "[]"


def test_a_notacao_continua_pedindo_a_ordem_ao_box_service(monkeypatch):
    """O AbbyChessCraft observa a ordem pelo `BoxService` (passo 10): mudar o dono dela
    quebrava a suíte dele."""
    from core import notacao
    from core.box_model import BoxEntry
    from core.services.box_service import BoxService

    pedidas = []
    monkeypatch.setattr(BoxService, "sort_boxes_reading_order",
                        staticmethod(lambda boxes, deteccao=None: pedidas.append(len(boxes)) or boxes))
    notacao.texto_da_pagina([BoxEntry("e", 0, 0, 10, 20), BoxEntry("4", 12, 0, 20, 20)])
    assert pedidas and set(pedidas) == {2}
