"""Adapters dos resultados existentes para o documento editorial.

O adapter da `PaginaExtraida` (o leitor medido, `core.livro`) é o que enche
a fila de revisão: cada linha impressa vira uma `Evidence` com as **duas
leituras** — a âncora da cadeia própria e a linha do motor de prosa —, a
caixa dela na página e os motivos de suspeita que `core.editorial_suspeitas`
tirou do registro de roteamento. O bloco que tem linha suspeita entra na
fila com esses motivos; o que não tem, não entra. Antes disto todo bloco
saía `automatic` a 1,0 e a fila de um livro inteiro era vazia.
"""

from __future__ import annotations

import base64
import re
from typing import Any, Iterable, Mapping, Sequence

from core import lado_a_jogar as lado_jogar
from core.editorial_model import (
    Decision,
    EditorialBlock,
    EditorialDocument,
    EditorialPage,
    Evidence,
    Hypothesis,
    SourceRef,
)
from core.editorial_suspeitas import (
    Motivo,
    confianca_da_linha,
    descrever,
    motivos_da_linha,
)

_RE_CELULA = re.compile(r"^t(\d+)c(\d+)l(\d+)$")


def _kind(region_type: str) -> str:
    return {
        "body": "paragraph", "quote": "paragraph", "heading": "heading",
        "caption": "caption", "notation": "chess_sequence",
        "chess_sequence": "chess_sequence", "paragraph": "paragraph",
        "prose": "paragraph", "diagram": "diagram",
        "table": "table", "header": "header", "footer": "footer",
    }.get(str(region_type), "unknown")


def _source_ref(document_id: str, page_index: int, *, bbox=None,
                metadata: Mapping[str, Any] | None = None,
                source_kind: str = "derived") -> SourceRef:
    metadata = metadata or {}
    source = metadata.get("source_ref")
    if isinstance(source, Mapping):
        base = SourceRef.from_dict({
            "document_id": source.get("document_id", document_id),
            "page_index": source.get("page_index", page_index),
            "bbox": source.get("bbox", bbox),
            "image_hash": source.get("image_hash", metadata.get("image_hash", "")),
            "source_kind": source.get("source_kind", source_kind),
        })
        return base
    return SourceRef(
        document_id=document_id,
        page_index=page_index,
        bbox=bbox,
        image_hash=str(metadata.get("image_hash", "")),
        source_kind=str(metadata.get("source_kind", source_kind)),
    )


def page_result_para_pagina(page, *, document_id: str | None = None,
                            page_index: int | None = None) -> EditorialPage:
    """Converte um ``PageResult`` sem importar engines ou a UI."""
    metadata = dict(getattr(page, "metadata", {}) or {})
    documento = str(document_id or metadata.get("document_id", "document"))
    indice = int(page_index if page_index is not None else metadata.get("page_index", 0))
    pagina_ref = _source_ref(documento, indice, metadata=metadata)
    evidence: list[Evidence] = []
    blocks: list[EditorialBlock] = []
    for order, region in enumerate(getattr(page, "regions", []) or []):
        region_ref = _source_ref(documento, indice, bbox=region.bbox, metadata=metadata)
        evidence_id = f"evidence-{page.page_id}-{region.id}"
        texto = str(region.text or "")
        region_metadata = dict(getattr(region, "metadata", {}) or {})
        diagram = region_metadata.get("diagram")
        value = diagram if region.type == "diagram" and isinstance(diagram, Mapping) else texto
        review_status = str(region_metadata.get("review_status", "automatic"))
        decision_status = ("unresolved" if review_status in {"review_required", "unresolved"}
                           else "reviewed" if review_status == "reviewed" else "automatic")
        evidencia = Evidence(
            id=evidence_id, ref=region_ref, observed_text=texto,
            engine=str(metadata.get("engine", "")),
            model_version=str(metadata.get("model_version", "")),
            confidence=float(region.confidence),
            preprocessing=str(metadata.get("preprocessing", "original")),
            metadata={"region_type": region.type, "region_id": region.id,
                      **region_metadata},
        )
        evidence.append(evidencia)
        blocks.append(EditorialBlock(
            id=f"block-{page.page_id}-{region.id}", kind=_kind(region.type), order=order,
            source_refs=[region_ref],
            decision=Decision(
                value=value, evidence_ids=[evidence_id],
                status=decision_status if texto or diagram else "unresolved",
                reason_codes=(list(diagram.get("reason_codes", []))
                              if isinstance(diagram, Mapping) else ["page_result_region"]),
                original_value=(diagram.get("original_fen")
                                if isinstance(diagram, Mapping) else None),
            ),
            children=list(region.line_ids),
            warnings=list(getattr(region, "warnings", []) or []),
            metadata={"region_type": region.type, "region_order": region.order,
                      **region_metadata},
        ))
    if not blocks:
        texto = str(getattr(page, "text", "") or "")
        if not texto:
            texto = "\n".join(str(line.text) for line in getattr(page, "lines", [])
                                 if getattr(line, "text", ""))
        if texto:
            evidence_id = f"evidence-{page.page_id}-text"
            evidence.append(Evidence(
                evidence_id, pagina_ref, observed_text=texto,
                engine=str(metadata.get("engine", "")), confidence=float(getattr(page, "confidence", 0.0)),
            ))
            blocks.append(EditorialBlock(
                id=f"block-{page.page_id}-text", kind="paragraph", order=0,
                source_refs=[pagina_ref],
                decision=Decision(texto, [evidence_id], "automatic", ["page_result_text"]),
            ))
    return EditorialPage(
        page_id=str(page.page_id), page_index=indice, source_refs=[pagina_ref],
        blocks=blocks, evidence=evidence,
        observations={
            "page_result": page.to_dict(),
            # These are pipeline decisions, not presentation metadata. Keep
            # them at page level so inspection and review can reach the same
            # routing/layout record after the PageResult adapter runs.
            **{chave: metadata[chave] for chave in
               ("layout", "routing", "source_kind", "dpi", "text_layer")
               if chave in metadata},
        },
        warnings=list(getattr(page, "warnings", []) or []), metadata=metadata,
    )


def page_result_para_documento(page, *, document_id: str | None = None,
                               title: str = "", language: str = "und",
                               pipeline_version: str = "") -> EditorialDocument:
    metadata = dict(getattr(page, "metadata", {}) or {})
    documento_id = str(document_id or metadata.get("document_id", "document"))
    documento = EditorialDocument(
        document_id=documento_id, title=title or str(metadata.get("title", "")),
        language=language if language != "und" else str(metadata.get("language", "und")),
        pages=[page_result_para_pagina(page, document_id=documento_id)],
        pipeline_version=pipeline_version or str(metadata.get("pipeline_version", "")),
        source_sha256=str(metadata.get("source_sha256", "")),
        model_manifest=str(metadata.get("model_manifest", "")),
    )
    documento.validate()
    return documento


def _caixa(valor) -> tuple[int, int, int, int] | None:
    """Uma caixa `(x1, y1, x2, y2)` válida, ou `None`."""
    if not valor or len(valor) != 4:
        return None
    x1, y1, x2, y2 = (int(round(float(v))) for v in valor)
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _evidencia_da_linha(registro: Mapping[str, Any], *, evidence_id: str,
                        document_id: str, indice: int,
                        fallback: SourceRef) -> tuple[Evidence, list[Motivo]]:
    """Uma linha lida vira `Evidence`: o texto final como observação, a
    âncora e a linha do motor como hipóteses, a caixa da linha como origem,
    e os motivos de suspeita nos diagnósticos — em frase — e no metadata —
    em código."""
    motivos = motivos_da_linha(registro)
    caixa = _caixa(registro.get("caixa"))
    ref = (_source_ref(document_id, indice, source_kind="legacy", bbox=caixa)
           if caixa else fallback)
    ancora = str(registro.get("ancora") or "")
    linha_ocr = str(registro.get("linha_ocr") or "")
    descartados = int(registro.get("descartados") or 0)
    hipoteses = []
    if ancora.strip():
        hipoteses.append(Hypothesis(
            id=f"{evidence_id}-ancora", text=ancora, source="glyph_chain",
            confidence=max(0.1, min(1.0, 1.0 - 0.1 * descartados)), bbox=caixa,
            metadata={"papel": "âncora da cadeia própria"}))
    if linha_ocr.strip():
        hipoteses.append(Hypothesis(
            id=f"{evidence_id}-motor", text=linha_ocr, source="line_engine",
            confidence=max(0.0, min(1.0, float(registro.get("confianca_ocr") or 0.0))),
            bbox=caixa, metadata={"papel": "linha do motor de prosa"}))
    metadata = {chave: registro.get(chave) for chave in
                ("linha", "celula", "dominio", "primario", "motivo", "fonte",
                 "semelhanca", "confianca_ocr", "descartados", "fragmento")
                if chave in registro}
    metadata["caixa"] = list(caixa) if caixa else None
    metadata["motivos"] = [m.codigo for m in motivos]
    return Evidence(
        id=evidence_id, ref=ref, observed_text=str(registro.get("texto") or ""),
        alternatives=hipoteses, engine="livro.extrair",
        confidence=confianca_da_linha(registro, motivos),
        diagnostics=[m.frase for m in motivos], metadata=metadata,
    ), motivos


def _celula(registro: Mapping[str, Any]) -> tuple[int, int, int] | None:
    achado = _RE_CELULA.match(str(registro.get("celula") or ""))
    return tuple(int(v) for v in achado.groups()) if achado else None


def _bloco_suspeito(reason_codes: list[str], motivos: Sequence[Motivo],
                    metadata: dict[str, Any]) -> None:
    """Põe no bloco o que a fila lê: os códigos na decisão, as frases e a
    marca de revisão no metadata. Sem motivo, nada muda — o bloco continua
    `automatic` e fora da fila."""
    if not motivos:
        return
    for motivo in motivos:
        if motivo.codigo not in reason_codes:
            reason_codes.append(motivo.codigo)
    frases = metadata.setdefault("motivos", [])
    for motivo in motivos:
        if motivo.frase not in frases:
            frases.append(motivo.frase)
    metadata["review_required"] = True


def pagina_extraida_para_pagina(pagina, *, document_id: str = "document") -> EditorialPage:
    """Converte uma ``PaginaExtraida`` sem alterar o objeto histórico.

    Cada parágrafo traz, além da evidência do bloco inteiro, **uma evidência
    por linha impressa** (`Paragrafo.registros` → `PaginaExtraida.roteamento`),
    com a âncora, a linha do motor, a caixa da linha e os motivos de suspeita;
    a tabela faz o mesmo por célula. O bloco com linha suspeita sai marcado
    (`review_required`, códigos na decisão, frases em `metadata["motivos"]`),
    e é o que `build_review_queue` põe na fila.
    """
    indice = int(pagina.numero)
    page_id = f"{document_id}-p{indice + 1:04d}"
    pagina_ref = _source_ref(document_id, indice, source_kind="legacy")
    largura = int(getattr(pagina, "largura", 0) or 0)
    altura = int(getattr(pagina, "altura", 0) or 0)
    roteamento = list(getattr(pagina, "roteamento", []) or [])
    motor_indisponivel = str(getattr(pagina, "motor_indisponivel", "") or "")
    evidence: list[Evidence] = []
    blocks: list[EditorialBlock] = []
    for order, legado in enumerate(pagina.blocos):
        tipo = type(legado).__name__
        evidence_id = f"evidence-{page_id}-b{order:04d}"
        bloco_ref = pagina_ref
        registros: list[int] = []
        motivos: list[Motivo] = []
        status = "automatic"
        reason_codes = ["legacy_adapter"]
        if tipo == "Paragrafo":
            texto = str(legado.texto)
            kind = "heading" if legado.titulo else "paragraph"
            value: Any = texto
            style = {
                "heading_level": legado.nivel if legado.titulo else None,
                "bold_spans": [list(item) for item in legado.negrito],
            }
            metadata = {"legacy_type": tipo, "top": legado.topo, "bottom": legado.pe}
            # A caixa do parágrafo, em pixels da imagem lida: a faixa vertical
            # que `topo`/`pe` delimitam, na largura da página. É o que deixa o
            # PDF pesquisável pôr a camada invisível na altura certa — sem
            # caixa, todo bloco caía no mesmo canto da página.
            if (legado.topo is not None and legado.pe is not None
                    and largura > 0 and legado.pe > legado.topo):
                bloco_ref = _source_ref(
                    document_id, indice, source_kind="legacy",
                    bbox=(0, int(legado.topo), largura, int(legado.pe)))
            registros = [i for i in getattr(legado, "registros", []) or []
                         if 0 <= int(i) < len(roteamento)]
            if motor_indisponivel and any(
                    str(roteamento[i].get("dominio")) in ("prose", "mixed")
                    for i in registros):
                motivos.append(Motivo("motor_indisponivel",
                                      descrever("motor_indisponivel")))
        elif tipo == "Figura":
            value = {
                "fen": legado.fen,
                "origin": legado.origem,
                "warning": legado.aviso,
                "width": legado.largura,
                "height": legado.altura,
                "orientation": legado.orientacao,
                "lines": legado.linhas,
                "font": legado.fonte,
                "coordinates": legado.coordenadas,
                "framed_lines": legado.linhas_emolduradas,
                "png_base64": base64.b64encode(legado.png).decode("ascii"),
                # De quem é a vez, e se isso foi lido ou assumido (item 3 da
                # revisão de 2026-09-18). Sem os dois campos, o `w` do FEN
                # chega na exportação sem nada que o distinga de uma leitura.
                "side_to_move": lado_jogar.do_fen(legado.fen or "") or "w",
                "side_to_move_source": {"legenda": "legend"}.get(
                    legado.lado_origem, "assumed"),
            }
            kind = "diagram"
            texto = legado.fen or ""
            style = {}
            metadata = {"legacy_type": tipo}
            caixa = _caixa(getattr(legado, "caixa", None))
            if caixa:
                value["bbox"] = list(caixa)
                bloco_ref = _source_ref(document_id, indice, source_kind="legacy",
                                        bbox=caixa)
            # O diagrama que o porteiro recusou saiu como recorte, e o aviso
            # diz por quê: não é uma posição lida, e a fila tem de mostrá-lo.
            # O recorte pedido (`diagramas="recorte"`, sem aviso) é escolha do
            # usuário, e não dúvida.
            if legado.origem == "recorte" and legado.aviso:
                status = "unresolved"
                motivos.append(Motivo("diagram_uncertain",
                                      f"{descrever('diagram_uncertain')}: {legado.aviso}"))
        elif tipo == "Tabela":
            value = {"rows": [list(row) for row in legado.linhas]}
            kind = "table"
            texto = "\n".join(" ".join(row) for row in legado.linhas)
            style = {}
            metadata = {"legacy_type": tipo, "rows": len(legado.linhas)}
            registros = [i for i, r in enumerate(roteamento) if _celula(r)]
        else:
            value = str(legado)
            texto = value
            kind = "unknown"
            style = {}
            metadata = {"legacy_type": tipo}
        # A evidência do bloco inteiro: 1,0 no que o leitor decidiu, 0 no
        # diagrama que o porteiro recusou — a confiança é o que ordena a
        # fila, e o recorte sem posição tem de vir antes de qualquer linha.
        evidence.append(Evidence(
            evidence_id, bloco_ref, observed_text=texto,
            confidence=0.0 if status == "unresolved" else 1.0,
            engine="legacy", metadata=dict(metadata),
        ))
        evidence_ids = [evidence_id]
        linhas: list[dict[str, Any]] = []
        for k, i in enumerate(registros):
            registro = roteamento[i]
            item, motivos_da_linha_i = _evidencia_da_linha(
                registro, evidence_id=f"{evidence_id}-l{k:03d}",
                document_id=document_id, indice=indice, fallback=bloco_ref)
            evidence.append(item)
            evidence_ids.append(item.id)
            motivos.extend(motivos_da_linha_i)
            celula = _celula(registro)
            linhas.append({"evidence_id": item.id, "registro": i,
                           "texto": item.observed_text,
                           "celula": list(celula) if celula else None})
        if linhas:
            metadata["linhas"] = linhas
        _bloco_suspeito(reason_codes, motivos, metadata)
        blocks.append(EditorialBlock(
            id=f"block-{page_id}-b{order:04d}", kind=kind, order=order,
            source_refs=[bloco_ref],
            decision=Decision(value, evidence_ids, status, reason_codes),
            style=style, metadata=metadata,
        ))
    observations = {
        "legacy_page": {
            "numero": pagina.numero, "caracteres": pagina.caracteres,
            "descartados_por_confianca": pagina.descartados_por_confianca,
            "respingos_descartados": pagina.respingos_descartados,
            "diagramas": pagina.diagramas, "diagramas_desenhados": pagina.diagramas_desenhados,
            "pagina_de_imagem": pagina.pagina_de_imagem, "colunas": pagina.colunas,
            "reparos": pagina.reparos, "cortes": pagina.cortes, "altura": pagina.altura,
            "largura": largura, "dpi": int(getattr(pagina, "dpi", 0) or 0),
            "cabecalhos": list(pagina.cabecalhos), "roteamento": roteamento,
            "motor_indisponivel": motor_indisponivel,
        }
    }
    # `image_width`/`dpi` no metadata da página é o que o PDF pesquisável lê
    # para converter as caixas (pixels) em pontos; `warnings` é o que a fila
    # de revisão lê — a página em que o motor de prosa faltou é suspeita
    # inteira, e o aviso diz por quê.
    metadata_pagina: dict[str, Any] = {}
    if largura > 0:
        metadata_pagina["image_width"] = largura
    if altura > 0:
        metadata_pagina["image_height"] = altura
    if getattr(pagina, "dpi", 0):
        metadata_pagina["dpi"] = int(pagina.dpi)
    warnings = ([f"motor de prosa indisponível: {motor_indisponivel}"]
                if motor_indisponivel else [])
    return EditorialPage(
        page_id=page_id, page_index=indice, source_refs=[pagina_ref], blocks=blocks,
        evidence=evidence, observations=observations, warnings=warnings,
        metadata=metadata_pagina,
    )


def paginas_extraidas_para_documento(paginas: Iterable[Any], *,
                                     document_id: str = "document",
                                     title: str = "", language: str = "und",
                                     pipeline_version: str = "legacy") -> EditorialDocument:
    documento = EditorialDocument(
        document_id=document_id, title=title, language=language,
        pages=[pagina_extraida_para_pagina(pagina, document_id=document_id)
               for pagina in paginas], pipeline_version=pipeline_version,
    )
    documento.validate()
    return documento


def pagina_extraida_para_documento(pagina, *, document_id: str = "document",
                                   title: str = "", language: str = "und") -> EditorialDocument:
    return paginas_extraidas_para_documento(
        [pagina], document_id=document_id, title=title, language=language)
