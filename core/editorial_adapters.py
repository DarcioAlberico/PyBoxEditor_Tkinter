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


def _kind_da_figura(origem: str) -> str:
    """
    O tipo de bloco de uma `livro.Figura`, pela origem dela.

    Três das quatro origens **não** são um tabuleiro: a `faixa` é o cabeçalho
    impresso acima do diagrama (legenda), a `pagina` é a página inteira que
    virou imagem, e só `render` e `recorte` são o diagrama. Mandar as quatro
    como ``diagram`` punha `data-fen` num cabeçalho e fazia o editor procurar
    posição onde não há (item 4 da revisão de 2026-09-18).
    """
    return {"faixa": "caption", "pagina": "figure"}.get(str(origem), "diagram")


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
    # A página lida da camada do PDF (F110) não é leitura do modelo: a
    # procedência dela é o texto do arquivo, e é isso que a evidência diz.
    leitura = str(getattr(pagina, "leitura", "imagem") or "imagem")
    procedencia = "pdf_text" if leitura == "camada" else "legacy"
    pagina_ref = _source_ref(document_id, indice, source_kind=procedencia)
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
            metadata = {"legacy_type": tipo, "top": legado.topo, "bottom": legado.pe,
                        # As linhas impressas de que este parágrafo saiu: o
                        # começo de cada uma no texto e o registro de
                        # roteamento dela. É o que a volta
                        # (`pagina_editorial_para_extraida`) repõe, e sem isso
                        # o parágrafo que ia e voltava perdia de que linhas
                        # tinha saído — e com elas a fila de revisão.
                        "line_starts": [int(i) for i in getattr(legado, "inicios", []) or []],
                        "routing_rows": [int(i) for i in getattr(legado, "registros", []) or []]}
            # A caixa do parágrafo, em pixels da imagem lida: a faixa vertical
            # que `topo`/`pe` delimitam, na largura da página. É o que deixa o
            # PDF pesquisável pôr a camada invisível na altura certa — sem
            # caixa, todo bloco caía no mesmo canto da página.
            if (legado.topo is not None and legado.pe is not None
                    and largura > 0 and legado.pe > legado.topo):
                bloco_ref = _source_ref(
                    document_id, indice, source_kind=procedencia,
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
                # `""`, e não `None`: quem lê o IR escreve `data-fen` com o que
                # achar aqui, e um `None` virava a string "None" no arquivo
                # exportado. A volta devolve o `None` ao recorte.
                "fen": legado.fen or "",
                "origin": legado.origem,
                "warning": legado.aviso,
                "width": legado.largura,
                "height": legado.altura,
                "orientation": legado.orientacao,
                "lines": legado.linhas,
                "font": legado.fonte,
                "coordinates": legado.coordenadas,
                "framed_lines": legado.linhas_emolduradas,
                # A largura da figura **medida em casas** (F97): é o que faz o
                # corpo em pontos valer para a imagem, e sem ela o diagrama que
                # ia e voltava saía noutro tamanho no mesmo livro.
                "squares_wide": legado.casas_de_largura,
                "png_base64": base64.b64encode(legado.png).decode("ascii"),
                # De quem é a vez, e se isso foi lido ou assumido (item 3 da
                # revisão de 2026-09-18). Sem os dois campos, o `w` do FEN
                # chega na exportação sem nada que o distinga de uma leitura.
                # O lado **lido** manda sobre o campo do FEN: é ele que a volta
                # repõe, e o FEN de um recorte nem sempre existe.
                "side_to_move": (legado.lado_a_jogar
                                 or lado_jogar.do_fen(legado.fen or "") or "w"),
                "side_to_move_source": {"legenda": "legend"}.get(
                    legado.lado_origem, "assumed"),
                # As casas que o livro marcou (F110): sem elas, o diagrama que
                # ia e voltava perdia o `x` das casas-chave no redesenho.
                "marks": [str(casa) for casa in getattr(legado, "marcas", None) or []],
            }
            kind = _kind_da_figura(legado.origem)
            texto = legado.fen or ""
            style = {}
            metadata = {"legacy_type": tipo}
            caixa = _caixa(getattr(legado, "caixa", None))
            if caixa:
                value["bbox"] = list(caixa)
                bloco_ref = _source_ref(document_id, indice, source_kind=procedencia,
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
            engine=procedencia, metadata=dict(metadata),
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
            "leitura": leitura,
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


# ----------------------------------------------------------------------
# A volta: IR → `PaginaExtraida`
# ----------------------------------------------------------------------
#
# A ida existe desde a Fase 1; a volta, não, e a falta dela custava caro: o
# documento revisado só sabia virar arquivo pelos escritores do IR, e os dois
# que embutem fonte de símbolos e redesenham diagrama — `exportar.para_epub` e
# `para_docx` — pedem `PaginaExtraida`. Quem quisesse os dois mundos guardava a
# lista de páginas ao lado do IR (`ExtratorDeLivro.ultimas_paginas`) e rezava
# para as duas não divergirem.
#
# O que a volta promete é o que o item 4 da revisão de 2026-09-18 pede: o
# round-trip `PaginaExtraida → IR → PaginaExtraida` devolve blocos iguais, e o
# EPUB escrito dos dois sai byte a byte igual. O que ela **não** repõe são
# `Paragrafo.pesos` e `Paragrafo.lacunas` — as medidas por caractere que
# `partir_coladas` e `negrito.marcar` consomem **dentro** de `livro.extrair`,
# antes de existir IR. Repô-las seria gravar dois floats por caractere de livro
# num JSON para ninguém os ler; `editorial_legacy._bloco_revisado` já as
# descarta pela mesma razão quando o texto muda.


def _figura_do_valor(valor: Mapping[str, Any]) -> Any:
    """Uma `livro.Figura` de volta do IR, com tudo que o escritor lê dela."""
    from core import livro

    png = b""
    codificado = valor.get("png_base64")
    if codificado:
        try:
            png = base64.b64decode(str(codificado), validate=True)
        except (ValueError, TypeError):
            png = b""
    lado = str(valor.get("side_to_move") or "")
    origem_do_lado = str(valor.get("side_to_move_source") or "assumed")
    caixa = _caixa(valor.get("bbox"))
    return livro.Figura(
        png=png, largura=int(valor.get("width") or 0),
        altura=int(valor.get("height") or 0),
        fen=str(valor.get("fen") or "") or None,
        origem=str(valor.get("origin") or "recorte"),
        aviso=str(valor.get("warning") or "") or None,
        linhas=list(valor.get("lines") or []) or None,
        fonte=str(valor.get("font") or "") or None,
        coordenadas=bool(valor.get("coordinates")),
        orientacao=str(valor.get("orientation") or "branca"),
        casas_de_largura=(float(valor["squares_wide"])
                          if valor.get("squares_wide") is not None else None),
        linhas_emolduradas=bool(valor.get("framed_lines")),
        caixa=caixa,
        # O lado só volta como leitura quando foi lido: o que o adapter
        # declarou convenção não pode voltar afirmado (DEC-06).
        lado_a_jogar=(lado if lado in ("w", "b") and origem_do_lado != "assumed"
                      else None),
        lado_origem=("legenda" if origem_do_lado in ("legend", "legenda")
                     else "convencao"),
        marcas=[str(casa) for casa in valor.get("marks") or []],
    )


def _bloco_de_volta(block: EditorialBlock) -> Any:
    """O bloco legado que este bloco do IR era — ou `None` se não era nenhum."""
    from core import livro

    valor = block.decision.value
    tipo = str(block.metadata.get("legacy_type") or "")
    if tipo == "Figura" or (isinstance(valor, Mapping)
                            and "png_base64" in valor and not tipo):
        return _figura_do_valor(valor if isinstance(valor, Mapping) else {})
    if tipo == "Tabela" or (not tipo and block.kind == "table"):
        filas = (valor.get("rows") if isinstance(valor, Mapping) else None) or []
        return livro.Tabela([[str(celula) for celula in fila] for fila in filas])
    texto = valor if isinstance(valor, str) else _texto_do_valor(valor)
    estilo = block.style or {}
    nivel = estilo.get("heading_level")
    return livro.Paragrafo(
        texto=texto,
        titulo=block.kind == "heading",
        nivel=int(nivel) if nivel else 2,
        negrito=[(int(a), int(b)) for a, b in estilo.get("bold_spans") or []],
        topo=_inteiro_ou_nada(block.metadata.get("top")),
        pe=_inteiro_ou_nada(block.metadata.get("bottom")),
        inicios=[int(i) for i in block.metadata.get("line_starts") or []],
        registros=[int(i) for i in block.metadata.get("routing_rows") or []],
    )


def _inteiro_ou_nada(valor: Any) -> int | None:
    return None if valor is None else int(valor)


def _texto_do_valor(valor: Any) -> str:
    if isinstance(valor, Mapping):
        for chave in ("text", "fen"):
            if valor.get(chave):
                return str(valor[chave])
        return ""
    return "" if valor is None else str(valor)


def pagina_editorial_para_extraida(page: EditorialPage, *,
                                   incluir_rejeitados: bool = False) -> Any:
    """A `PaginaExtraida` de volta de uma `EditorialPage`.

    A página histórica é remontada de `observations["legacy_page"]` — o que a
    ida guardou inteiro — e os blocos, de `metadata["legacy_type"]`; um IR que
    não veio do leitor medido (a Fase 4, um JSON de fora) também volta, pelo
    `kind` e pelo formato do valor, e aí só se recupera o que ele tinha.

    O bloco **rejeitado na revisão fica de fora** por padrão: é o que
    `aplicar_revisao` faz, e é o que quem exporta o documento revisado espera.
    """
    from core import livro

    legado = dict(page.observations.get("legacy_page") or {})
    blocos = [_bloco_de_volta(block)
              for block in sorted(page.blocks, key=lambda item: item.order)
              if incluir_rejeitados or block.decision.status != "rejected"]
    pagina = livro.PaginaExtraida(
        numero=int(legado.get("numero", page.page_index)), blocos=blocos)
    for campo in ("caracteres", "descartados_por_confianca",
                  "respingos_descartados", "diagramas", "diagramas_desenhados",
                  "colunas", "reparos", "cortes", "altura", "largura", "dpi"):
        if legado.get(campo) is not None:
            setattr(pagina, campo, int(legado[campo]))
    pagina.pagina_de_imagem = bool(legado.get("pagina_de_imagem", False))
    pagina.cabecalhos = [str(item) for item in legado.get("cabecalhos") or []]
    pagina.roteamento = [dict(item) for item in legado.get("roteamento") or []]
    pagina.motor_indisponivel = str(legado.get("motor_indisponivel") or "")
    pagina.leitura = str(legado.get("leitura") or "imagem")
    if not pagina.largura:
        pagina.largura = int(page.metadata.get("image_width") or 0)
    if not pagina.altura:
        pagina.altura = int(page.metadata.get("image_height") or 0)
    if not pagina.dpi:
        pagina.dpi = int(page.metadata.get("dpi") or 0)
    return pagina


def documento_para_paginas_extraidas(documento: EditorialDocument, *,
                                     incluir_rejeitados: bool = False) -> list[Any]:
    """As páginas do documento **na ordem em que ele as traz**.

    Não ordenada por `page_index`, e é o que a volta exige: quem exporta uma
    seleção de páginas passa a lista na ordem que quer, e o EPUB numera os
    arquivos por ela. Ordenar aqui trocaria a ordem do livro exportado num
    round-trip — e o `page_index` continua sendo o número impresso, que é
    outra coisa.
    """
    return [pagina_editorial_para_extraida(page, incluir_rejeitados=incluir_rejeitados)
            for page in documento.pages]
