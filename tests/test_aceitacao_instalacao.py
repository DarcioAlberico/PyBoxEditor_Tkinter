"""
O smoke da instalação de verdade (item 10 da `docs/REVISAO_MODOS_OCR.md`).

O gate de release (`docs/OPERATIONS.md`) conferia o wheel só por dentro —
`smoke_test_wheel` abre o zip e procura os arquivos. O
`core.ocr_phase8.smoke_test_installation`, que cria um venv limpo, instala o
wheel **sem dependências** e importa os módulos, existia e nenhum teste o
rodava. Aqui ele roda sobre o wheel da árvore de hoje, com os módulos que
precisam abrir sem o OCR: a configuração, o documento editorial e o editor de
livros (a DEC-07 da SPEC_EDITOR: o editor não carrega torch, cv2, numpy nem
fitz).

Construir o wheel leva ~7 s e instalar, ~9 s: `slow`, no passo das medições.
O setuptools usa a pasta `build/` da raiz, que o `.gitignore` já ignora — é a
mesma que o gate usa.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from core.ocr_phase8 import smoke_test_installation

RAIZ = Path(__file__).resolve().parents[1]

#: Os módulos que abrem sem dependência nenhuma, e por isso entram no smoke.
SEM_DEPENDENCIAS = ("config.paths", "config.settings", "core.editorial_model",
                    "core.ocr_phase7", "core.ocr_phase8", "core.editor.modelo",
                    "core.editor.epub", "core.editor.xhtml", "core.editor.projeto")


@pytest.mark.slow
def test_o_wheel_instala_num_venv_limpo_e_os_modulos_abrem(tmp_path):
    subprocess.run([sys.executable, "-m", "pip", "wheel", str(RAIZ), "--no-deps",
                    "--no-build-isolation", "-q", "-w", str(tmp_path)],
                   check=True, capture_output=True, text=True, cwd=str(RAIZ))
    [wheel] = tmp_path.glob("pyboxeditor-*.whl")
    relatorio = smoke_test_installation(wheel, required_modules=SEM_DEPENDENCIAS)
    assert relatorio.valid, relatorio.errors
