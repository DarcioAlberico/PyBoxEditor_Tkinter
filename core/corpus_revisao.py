"""Fila segura para a conferencia humana de candidatos do corpus."""

from __future__ import annotations

import string
from typing import Any, Mapping

from core import familias_de_pagina


SCHEMA = "pyboxeditor.ocr-corpus-review/v1"


def _selecionados(plano: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    plan = plano.get("plan")
    if not isinstance(plan, Mapping):
        raise ValueError("plano de corpus sem plan")
    itens = plan.get("selecionados")
    if not isinstance(itens, list):
        raise ValueError("plano de corpus sem selecionados")
    if not all(isinstance(item, Mapping) for item in itens):
        raise ValueError("selecionado de corpus invalido")
    return itens


def _familias(item: Mapping[str, Any]) -> list[str]:
    valores = item.get("familias") or ()
    if isinstance(valores, str):
        valores = (valores,)
    desconhecidas = {
        str(valor) for valor in valores
    } - set(familias_de_pagina.FAMILIAS)
    if desconhecidas:
        raise ValueError(f"familia desconhecida no candidato: {sorted(desconhecidas)}")
    presentes = {str(valor) for valor in valores}
    return [familia for familia in familias_de_pagina.FAMILIAS
            if familia in presentes]


def _sha256(item: Mapping[str, Any], identificador: str) -> str:
    valor = str(item.get("source_pdf_sha256") or "").strip().lower()
    if len(valor) != 64 or any(caractere not in string.hexdigits for caractere in valor):
        raise ValueError(f"source_pdf_sha256 invalido: {identificador}")
    return valor


def preparar_fila_revisao(plano: Mapping[str, Any]) -> dict[str, Any]:
    """Converte selecoes preliminares em uma fila explicitamente pendente.

    A fila nao contem ``reference`` nem ``holdout``. Portanto, mesmo que seja
    passada por engano ao fluxo de promocao, ela nao satisfaz o contrato de
    revisao humana. O arquivo da fila conserva apenas a proveniencia e sinais
    sugeridos pelo OCR; familias e texto continuam sujeitos a conferencia.
    """
    if not isinstance(plano, Mapping):
        raise ValueError("plano de corpus invalido")
    itens = _selecionados(plano)
    if not itens:
        raise ValueError("plano de corpus sem candidatos selecionados")

    saida: list[dict[str, Any]] = []
    ids: set[str] = set()
    for item in itens:
        identificador = str(item.get("id") or "").strip()
        if not identificador:
            raise ValueError("selecionado de corpus sem id")
        if identificador in ids:
            raise ValueError(f"selecionado duplicado: {identificador}")
        ids.add(identificador)
        if "reference" in item or "holdout" in item:
            raise ValueError(f"fila nao pode conter reference/holdout: {identificador}")
        if str(item.get("status") or "") != "unreviewed":
            raise ValueError(f"candidato precisa estar unreviewed: {identificador}")
        documento = str(item.get("documento") or "").strip()
        if not documento:
            raise ValueError(f"selecionado sem documento: {identificador}")
        try:
            page_index = int(item["page_index"])
        except (KeyError, TypeError, ValueError) as erro:
            raise ValueError(f"page_index invalido: {identificador}") from erro
        if page_index < 1:
            raise ValueError(f"page_index invalido: {identificador}")
        source_pdf = str(item.get("source_pdf") or "").strip()
        if not source_pdf:
            raise ValueError(f"candidato sem source_pdf: {identificador}")
        familias = _familias(item)
        principal = str(item.get("principal") or "").strip()
        if principal and principal not in familias:
            raise ValueError(f"principal nao pertence as familias: {identificador}")
        artifacts = item.get("artifacts") or {}
        if not isinstance(artifacts, Mapping):
            raise ValueError(f"artifacts invalidos: {identificador}")
        saida.append({
            "candidate_id": identificador,
            "documento": documento,
            "page_index": page_index,
            "source_pdf": source_pdf,
            "source_pdf_sha256": _sha256(item, identificador),
            "draft": str(artifacts.get("draft") or ""),
            "routing": str(artifacts.get("routing") or ""),
            "familias_sugeridas": familias,
            "principal_sugerida": principal,
            "status": "pending_review",
        })

    return {
        "schema": SCHEMA,
        "items": saida,
        "review_policy": {
            "requires_image_confirmation": True,
            "promotion_status": "reviewed",
        },
    }
