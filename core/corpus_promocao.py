"""Promoção explícita de transcrições revisadas para o corpus oficial.

O módulo é deliberadamente conservador: candidatos preliminares não entram no
manifesto. Só uma revisão humana com estado ``reviewed``, revisor e arquivo de
referência existente pode criar uma ``CorpusPage``. A função devolve uma cópia
do manifesto para que a chamada não altere o estado em memória.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from core import familias_de_pagina
from core.corpus_candidatos import sha256_arquivo
from core.ocr_corpus import CorpusManifest, CorpusPage


def _lista_de_familias(item: Mapping[str, Any]) -> list[str]:
    valores = item.get("familias") or ()
    if isinstance(valores, str):
        valores = (valores,)
    familias = {str(valor) for valor in valores}
    desconhecidas = familias - set(familias_de_pagina.FAMILIAS)
    if desconhecidas:
        raise ValueError(f"família desconhecida na revisão: {sorted(desconhecidas)}")
    return [familia for familia in familias_de_pagina.FAMILIAS if familia in familias]


def _revisado_em(item: Mapping[str, Any]) -> str:
    valor = str(item.get("revisado_em") or "").strip()
    return valor or datetime.now(timezone.utc).isoformat(timespec="seconds")


def _documento(manifesto: CorpusManifest, identificador: str):
    for documento in manifesto.documents:
        if documento.id == identificador:
            return documento
    raise ValueError(f"documento não encontrado no manifesto: {identificador}")


def _caminho_fonte(valor: Any, base_dir: str | Path) -> Path:
    texto = str(valor or "").strip()
    if not texto:
        raise ValueError("candidato sem source_pdf")
    caminho = Path(texto)
    return caminho if caminho.is_absolute() else Path(base_dir) / caminho


def validar_revisoes_com_candidatos(
        revisoes: Iterable[Mapping[str, Any]],
        candidatos: Iterable[Mapping[str, Any]], *,
        base_dir: str | Path = ".") -> dict[str, Any]:
    """Confere a proveniencia das revisoes antes da promocao.

    Cada revisao aponta para um candidato ``unreviewed`` por ``candidate_id``,
    repete documento/pagina e declara o SHA-256 do PDF. O hash e recalculado no
    arquivo atual, evitando promover texto conferido contra outra fonte.
    """
    entradas = list(revisoes)
    candidatos_por_id: dict[str, Mapping[str, Any]] = {}
    for candidato in candidatos:
        if not isinstance(candidato, Mapping):
            raise ValueError("candidato de corpus invalido")
        identificador = str(candidato.get("id") or "").strip()
        if not identificador:
            raise ValueError("candidato sem id")
        if identificador in candidatos_por_id:
            raise ValueError(f"candidato duplicado: {identificador}")
        candidatos_por_id[identificador] = candidato

    if not entradas:
        raise ValueError("nenhuma revisao para validar")
    ids_revisados: list[str] = []
    hashes: list[str] = []
    for revisao in entradas:
        if not isinstance(revisao, Mapping):
            raise ValueError("revisao de corpus invalida")
        candidate_id = str(revisao.get("candidate_id") or "").strip()
        if not candidate_id or candidate_id not in candidatos_por_id:
            raise ValueError(f"candidato nao encontrado: {candidate_id or '?'}")
        candidato = candidatos_por_id[candidate_id]
        if str(candidato.get("status") or "") != "unreviewed":
            raise ValueError(f"candidato nao esta unreviewed: {candidate_id}")
        if str(revisao.get("status") or "") != "reviewed":
            raise ValueError(f"revisao precisa estar em status reviewed: {candidate_id}")

        if str(revisao.get("documento") or "") != str(candidato.get("documento") or ""):
            raise ValueError(f"documento nao corresponde ao candidato: {candidate_id}")
        try:
            pagina_revisao = int(revisao["page_index"])
            pagina_candidato = int(candidato["page_index"])
        except (KeyError, TypeError, ValueError) as erro:
            raise ValueError(f"page_index invalido no candidato: {candidate_id}") from erro
        if pagina_revisao != pagina_candidato:
            raise ValueError(f"pagina nao corresponde ao candidato: {candidate_id}")

        esperado = str(candidato.get("source_pdf_sha256") or "").strip().lower()
        informado = str(revisao.get("source_pdf_sha256") or "").strip().lower()
        if not esperado or not informado:
            raise ValueError(f"source_pdf_sha256 obrigatorio: {candidate_id}")
        if esperado != informado:
            raise ValueError(f"source_pdf_sha256 nao corresponde: {candidate_id}")
        fonte = _caminho_fonte(candidato.get("source_pdf"), base_dir)
        if not fonte.is_file():
            raise FileNotFoundError(f"source_pdf ausente: {fonte}")
        atual = sha256_arquivo(fonte).lower()
        if atual != esperado:
            raise ValueError(f"hash do source_pdf mudou: {candidate_id}")
        ids_revisados.append(candidate_id)
        hashes.append(esperado)

    return {
        "candidates": len(candidatos_por_id),
        "reviewed": len(ids_revisados),
        "candidate_ids": ids_revisados,
        "source_pdf_sha256": sorted(set(hashes)),
    }


def promover_revisoes(manifesto: CorpusManifest,
                      revisoes: Iterable[Mapping[str, Any]], *,
                      base_dir: str | Path,
                      revisor: str = "") -> CorpusManifest:
    """Adiciona ao manifesto apenas páginas explicitamente revisadas.

    ``base_dir`` é a raiz dos caminhos relativos do manifesto. O arquivo de
    referência é verificado antes da alteração da cópia; o manifesto original
    e os objetos de entrada permanecem intactos.
    """
    resultado = copy.deepcopy(manifesto)
    base = Path(base_dir)
    revisor_padrao = str(revisor or "").strip()
    ids_existentes = {
        pagina.id
        for documento in resultado.documents
        for pagina in documento.pages
    }
    indices_por_documento = {
        documento.id: {pagina.page_index for pagina in documento.pages}
        for documento in resultado.documents
    }
    entradas = list(revisoes)
    if not entradas:
        raise ValueError("nenhuma revisão para promover")
    ids_novos: set[str] = set()

    for item in entradas:
        if not isinstance(item, Mapping):
            raise ValueError("revisão de corpus inválida")
        identificador = str(item.get("id") or "").strip()
        documento_id = str(item.get("documento") or "").strip()
        if not identificador:
            raise ValueError("revisão sem id")
        if identificador in ids_existentes or identificador in ids_novos:
            raise ValueError(f"página duplicada na promoção: {identificador}")
        documento = _documento(resultado, documento_id)
        try:
            page_index = int(item["page_index"])
        except (KeyError, TypeError, ValueError) as erro:
            raise ValueError(f"page_index inválido na revisão: {identificador}") from erro
        if page_index < 0:
            raise ValueError(f"page_index inválido na revisão: {identificador}")
        if page_index in indices_por_documento[documento_id]:
            raise ValueError(
                f"page_index duplicado em {documento_id}: {page_index}")
        if str(item.get("status") or "").strip() != "reviewed":
            raise ValueError(f"revisão {identificador} precisa estar em status reviewed")
        revisor_da_entrada = str(item.get("revisor") or revisor_padrao).strip()
        if not revisor_da_entrada:
            raise ValueError(f"revisão {identificador} precisa de revisor")
        referencia = str(item.get("reference") or "").strip()
        if not referencia:
            raise ValueError(f"revisão {identificador} precisa de referência")
        # CorpusPage aplica a política de caminho relativo e impede traversal.
        familias = _lista_de_familias(item)
        principal = str(item.get("principal") or "").strip()
        if principal and principal not in familias:
            raise ValueError(f"principal não pertence às famílias: {identificador}")
        metadata = {
            "annotation_status": "reviewed",
            "familias": familias,
            "principal": principal or (familias[0] if familias else ""),
            "candidate_id": str(item.get("candidate_id") or identificador),
            "reviewer": revisor_da_entrada,
            "reviewed_at": _revisado_em(item),
        }
        source_pdf_sha256 = str(item.get("source_pdf_sha256") or "").strip()
        if source_pdf_sha256:
            metadata["source_pdf_sha256"] = source_pdf_sha256
        pagina = CorpusPage(
            id=identificador,
            page_index=page_index,
            reference=referencia,
            domains=tuple(str(valor) for valor in (item.get("domains") or ())),
            metadata=metadata,
        )
        caminho = base / pagina.reference if pagina.reference else None
        if caminho is None or not caminho.is_file():
            raise FileNotFoundError(
                f"referência não encontrada para {identificador}: {referencia}")
        documento.pages.append(pagina)
        indices_por_documento[documento_id].add(page_index)
        ids_novos.add(identificador)

    resultado.corpus_sha256 = ""
    return resultado
