"""Caminhos persistentes da aplicação, separados do código instalado."""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "PyBoxEditor"


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

