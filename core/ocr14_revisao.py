"""Join auditavel entre a quarentena OCR-14 e uma revisao humana.

Este modulo e deliberadamente pequeno: ele nao infere rotulos, nao move
recortes e nao escreve diretamente no dataset. Seu contrato e transformar um
relatorio de quarentena mais uma lista explicita de decisoes humanas em um
artefato versionado que ``CorrectionDataset.from_ocr14`` consegue consumir.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from core.ocr14 import confirmar_entrada_de_quarentena


REVIEW_SCHEMA = "pyboxeditor.ocr14-review/v1"


def _copiar_entradas(relatorio: Any) -> tuple[str, list[dict[str, Any]]]:
    """Achata os formatos de relatorio emitidos pela OCR-14 sem muta-los."""
    if isinstance(relatorio, list):
        return "ocr14", [_validar_entrada(item, index)
                          for index, item in enumerate(relatorio)]
    if not isinstance(relatorio, Mapping):
        raise ValueError("relatorio OCR-14 invalido")

    document_id = str(relatorio.get("pdf", "ocr14") or "ocr14")
    entradas = relatorio.get("entradas")
    if entradas is not None:
        if not isinstance(entradas, list):
            raise ValueError("relatorio OCR-14 com entradas invalidas")
        resultado = [_validar_entrada(item, index)
                     for index, item in enumerate(entradas)]
    else:
        paginas = relatorio.get("paginas", {})
        if not isinstance(paginas, Mapping):
            raise ValueError("relatorio OCR-14 sem paginas")
        resultado = []
        for numero, pagina in paginas.items():
            if not isinstance(pagina, Mapping):
                raise ValueError(f"pagina OCR-14 invalida: {numero}")
            recortes = pagina.get("recortes", ())
            if not isinstance(recortes, list):
                raise ValueError(f"recortes OCR-14 invalidos na pagina: {numero}")
            for recorte in recortes:
                item = _validar_entrada(recorte, len(resultado))
                item.setdefault("pagina", numero)
                item.setdefault("document_id", document_id)
                resultado.append(item)

    for item in resultado:
        item.setdefault("document_id", document_id)
    _rejeitar_duplicados(resultado)
    return document_id, resultado


def _validar_entrada(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise ValueError(f"entrada OCR-14 invalida na posicao {index}")
    resultado = dict(item)
    arquivo = str(resultado.get("arquivo", "")).strip()
    if not arquivo:
        raise ValueError(f"entrada OCR-14 {index} sem arquivo")
    resultado["arquivo"] = arquivo
    return resultado


def _rejeitar_duplicados(entradas: list[Mapping[str, Any]]) -> None:
    vistos: set[str] = set()
    for entrada in entradas:
        arquivo = str(entrada["arquivo"])
        if arquivo in vistos:
            raise ValueError(f"recorte OCR-14 duplicado: {arquivo}")
        vistos.add(arquivo)


def _copiar_rotulos(rotulos: Any) -> dict[str, str]:
    """Aceita mapa simples ou lista versionavel de decisoes humanas."""
    if isinstance(rotulos, Mapping) and "revisoes" in rotulos:
        rotulos = rotulos["revisoes"]
    if isinstance(rotulos, Mapping):
        pares = [{"arquivo": arquivo, "rotulo": rotulo}
                 for arquivo, rotulo in rotulos.items()]
    elif isinstance(rotulos, list):
        pares = rotulos
    else:
        raise ValueError("rotulos OCR-14 invalidos")

    resultado: dict[str, str] = {}
    for index, par in enumerate(pares):
        if not isinstance(par, Mapping):
            raise ValueError(f"revisao OCR-14 invalida na posicao {index}")
        arquivo = str(par.get("arquivo", "")).strip()
        if not arquivo:
            raise ValueError(f"revisao OCR-14 {index} sem arquivo")
        if arquivo in resultado:
            raise ValueError(f"revisao OCR-14 duplicada: {arquivo}")
        if "rotulo" not in par:
            raise ValueError(f"revisao OCR-14 sem rotulo: {arquivo}")
        # A validacao final fica em confirmar_entrada_de_quarentena, que e a
        # mesma seam usada pelo importador da Fase 7.
        resultado[arquivo] = str(par["rotulo"])
    return resultado


def revisar_relatorio(relatorio: Any, rotulos: Any, *,
                      revisor: str = "reviewer",
                      revisado_em: str | None = None,
                      exigir_todos: bool = True) -> dict[str, Any]:
    """Confirma apenas os recortes cobertos por decisoes humanas explicitas.

    ``exigir_todos`` e estrito por padrao: uma revisao parcial precisa ser uma
    escolha declarada do operador, nunca o resultado de uma chave esquecida.
    """
    document_id, entradas = _copiar_entradas(relatorio)
    decisoes = _copiar_rotulos(rotulos)
    conhecidos = {str(item["arquivo"]) for item in entradas}
    desconhecidos = sorted(set(decisoes) - conhecidos)
    if desconhecidos:
        raise ValueError("revisao nao pertence ao relatorio: " + ", ".join(desconhecidos))

    faltantes = sorted(conhecidos - set(decisoes))
    if exigir_todos and faltantes:
        raise ValueError("recortes sem revisao: " + ", ".join(faltantes))

    momento = revisado_em or datetime.now(timezone.utc).isoformat(timespec="seconds")
    confirmadas: list[dict[str, Any]] = []
    pendentes: list[dict[str, Any]] = []
    for entrada in entradas:
        arquivo = str(entrada["arquivo"])
        if arquivo not in decisoes:
            pendentes.append(dict(entrada))
            continue
        confirmadas.append(confirmar_entrada_de_quarentena(
            entrada, decisoes[arquivo], revisor=revisor, revisado_em=momento))

    return {
        "schema": REVIEW_SCHEMA,
        "pdf": document_id,
        "status": "reviewed" if not pendentes else "pending_review",
        "revisor": str(revisor).strip() or "reviewer",
        "revisado_em": str(momento),
        "entradas": confirmadas,
        "pending": pendentes,
        "counts": {
            "candidates": len(entradas),
            "reviewed": len(confirmadas),
            "pending": len(pendentes),
        },
    }
