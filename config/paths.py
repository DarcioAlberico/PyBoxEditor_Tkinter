"""Caminhos persistentes da aplicação, separados do código instalado."""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "PyBoxEditor"


def projeto_dir() -> Path:
    """Diretório do projeto/aplicação onde ficam os pesos empacotados."""
    return Path(__file__).resolve().parent.parent


def caminhos_modelo_linha() -> tuple[Path, Path]:
    """Localiza os pesos do OCR de linhas independentemente do cwd.

    A UI pode ser aberta por atalho, IDE ou pelo terminal. Nesses casos o
    diretório de trabalho nem sempre é a raiz do projeto, embora os pesos
    continuem ao lado do código. Mantemos compatibilidade com um modelo
    criado no cwd quando ele existe e, caso contrário, usamos a raiz real.
    """
    candidatos = (Path.cwd(), projeto_dir())
    for raiz in candidatos:
        modelo, meta = raiz / "text_line_model.pth", raiz / "text_line_model.json"
        if modelo.exists() and meta.exists():
            return modelo, meta
    raiz = projeto_dir()
    return raiz / "text_line_model.pth", raiz / "text_line_model.json"


def data_dir() -> Path:
    """Diretório gravável por usuário para configurações e diagnósticos."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
    elif os.environ.get("XDG_DATA_HOME"):
        return Path(os.environ["XDG_DATA_HOME"]) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def settings_path() -> Path:
    return data_dir() / "settings.json"


def crash_log_path() -> Path:
    return data_dir() / "crash_log.txt"


def ensure_data_dir() -> Path:
    caminho = data_dir()
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho
