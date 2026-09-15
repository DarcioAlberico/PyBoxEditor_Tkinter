"""Mostra dependências e recursos disponíveis para executar o PyBoxEditor."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


DEPENDENCIAS = {
    "Pillow": "PIL",
    "NumPy": "numpy",
    "OpenCV": "cv2",
    "PyMuPDF": "fitz",
    "python-chess": "chess",
    "python-docx": "docx",
    "PyTorch": "torch",
    "EasyOCR": "easyocr",
    "PaddleOCR": "paddleocr",
    "PaddlePaddle": "paddle",
    "pytesseract": "pytesseract",
}

RECURSOS = {
    "modelo neural": Path("custom_model.pth"),
    "metadados neural": Path("model_meta.json"),
    "modelo de diagramas": Path("core/dados/diagrama_modelo.pth"),
    "modelo de ocupação": Path("core/dados/ocupacao_modelo.pth"),
    "léxico": Path("assets/lexico/en.txt.gz"),
}


def main() -> int:
    print(f"Python: {sys.version.split()[0]}")
    print(f"Executável: {sys.executable}")
    print(f"Diretório do projeto: {Path.cwd()}")
    print("\nDependências:")

    faltantes = []
    for nome, modulo in DEPENDENCIAS.items():
        disponivel = importlib.util.find_spec(modulo) is not None
        print(f"  {'OK ' if disponivel else '---'} {nome}")
        if not disponivel:
            faltantes.append(nome)

    print("\nRecursos versionados:")
    for nome, caminho in RECURSOS.items():
        print(f"  {'OK ' if caminho.is_file() else '---'} {nome}: {caminho}")

    if faltantes:
        print("\nRecursos opcionais ausentes não impedem o modo básico:")
        print("  " + ", ".join(faltantes))
        print("Instalação completa: python -m pip install -e .[all]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
