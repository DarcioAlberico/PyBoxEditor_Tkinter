"""Valida rótulos unitários usados por recortes de glifo."""

from __future__ import annotations

import unicodedata
from typing import Any


def validar_rotulo(rotulo: Any) -> str:
    """Normaliza e exige um único glifo Unicode não vazio."""
    label = unicodedata.normalize("NFC", str(rotulo).strip())
    if not label:
        raise ValueError("rótulo confirmado não pode ser vazio")
    if len(label) != 1:
        raise ValueError("rótulo confirmado precisa ser um único glifo")
    return label
