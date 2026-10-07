"""Candidatos preliminares para ampliar o corpus OCR.

Este módulo é a fronteira entre a extração de produção e a revisão humana.
Ele descreve sinais observados em uma ``PaginaExtraida``; não cria referência,
holdout, rótulo dourado nem movimenta recortes.
"""

from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
from typing import Any, Iterable

from core import familias_de_pagina


def _rotuladas(declaradas: Iterable[str]) -> list[str]:
    return [familia for familia in familias_de_pagina.FAMILIAS
            if familia in set(declaradas)]


def _sinais(pagina: Any) -> dict[str, Any]:
    roteamento = list(getattr(pagina, "roteamento", []) or [])
    dominios = Counter(
        str(registro.get("dominio") or "desconhecido")
        for registro in roteamento
        if hasattr(registro, "get")
    )
    return {
        "pagina_de_imagem": bool(getattr(pagina, "pagina_de_imagem", False)),
        "colunas": int(getattr(pagina, "colunas", 1) or 1),
        "diagramas": int(getattr(pagina, "diagramas", 0) or 0),
        "leitura": str(getattr(pagina, "leitura", "imagem") or "imagem"),
        "roteamento": {
            "linhas": len(roteamento),
            "dominios": dict(sorted(dominios.items())),
        },
    }


def candidato_de_pagina(documento: str, page_index: int, pagina: Any, *,
                        pdf: str | None = None,
                        source_pdf_sha256: str | None = None,
                        declaradas: Iterable[str] = (),
                        contornos: int | None = None) -> dict[str, Any]:
    """Converte uma página extraída em uma entrada revisável e não oficial.

    ``page_index`` usa a convenção humana do manifesto: começa em 1. Os sinais
    automáticos vêm de ``familias_de_pagina``; ``declaradas`` conserva apenas
    rótulos explicitamente fornecidos por quem selecionou a página. A saída é
    deliberadamente incompatível com uma referência: o estado é sempre
    ``unreviewed`` e os campos ``reference``/``holdout`` não são emitidos.
    """
    documento = str(documento or "").strip()
    if not documento:
        raise ValueError("documento do candidato precisa ser informado")
    if "/" in documento or "\\" in documento or documento in {".", ".."}:
        raise ValueError("documento do candidato não pode conter separadores")
    try:
        page_index = int(page_index)
    except (TypeError, ValueError) as erro:
        raise ValueError("page_index do candidato precisa ser inteiro") from erro
    if page_index < 1:
        raise ValueError("page_index do candidato deve começar em 1")

    declaradas = _rotuladas(declaradas)
    achadas = familias_de_pagina.familias(
        pagina, contornos=contornos, declaradas=declaradas)
    candidato = {
        "id": f"{documento}-p{page_index:03d}",
        "documento": documento,
        "page_index": page_index,
        "familias": [familia for familia in familias_de_pagina.FAMILIAS
                     if familia in achadas],
        "principal": familias_de_pagina.principal(
            pagina, contornos=contornos, declaradas=declaradas),
        "status": "unreviewed",
        "declared_families": declaradas,
        "signals": _sinais(pagina),
    }
    if pdf is not None:
        candidato["source_pdf"] = str(pdf)
    if source_pdf_sha256 is not None:
        candidato["source_pdf_sha256"] = str(source_pdf_sha256)
    return candidato


def sha256_arquivo(caminho: str | Path) -> str:
    """Calcula a identidade do arquivo-fonte usado para gerar candidatos."""
    digest = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()
