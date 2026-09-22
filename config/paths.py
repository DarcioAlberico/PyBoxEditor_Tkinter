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


def caminhos_dos_pesos() -> dict[str, Path]:
    """Os três pesos que decidem a leitura de uma página.

    São eles que o cache do caminho novo tem de levar na chave: trocar o modelo
    e reaproveitar o resultado gravado é servir a leitura do modelo velho como
    se fosse a do novo (item 7 da revisão de 2026-09-18). Os nomes são os
    mesmos de `core.diagrama.CAMINHO_MODELO`/`CAMINHO_OCUPACAO` e do padrão do
    `LearningService` — e há teste que prende os três a estes caminhos, porque
    a duplicação aqui é o preço de não importar `cv2` para saber onde eles
    estão.
    """
    raiz = projeto_dir()
    return {"glifos": raiz / "custom_model.pth",
            "diagrama": raiz / "core" / "dados" / "diagrama_modelo.pth",
            "ocupacao": raiz / "core" / "dados" / "ocupacao_modelo.pth"}


def cache_ocr_dir() -> Path:
    """Onde o resultado por página do caminho novo é guardado.

    Fora do projeto, junto do resto do que é do usuário: o cwd de quem abre o
    programa por atalho não é a raiz, e um cache que cai na pasta corrente é um
    cache que nunca acerta duas vezes. `PYBOXEDITOR_CACHE_DIR` reaponta a pasta
    — é o que mantém a suíte de testes fora do `AppData` de quem a roda.

    **Ele não é podado por ninguém.** Cada página guardada é um JSON de alguns
    KB, e a chave inclui os pesos, então uma troca de modelo deixa o que ficou
    para trás sem uso — apagar a pasta é seguro a qualquer momento.
    """
    base = os.environ.get("PYBOXEDITOR_CACHE_DIR")
    return (Path(base) if base else data_dir() / "cache") / "ocr"


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
