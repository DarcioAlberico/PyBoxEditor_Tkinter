"""Pipeline híbrido: linha para prosa, glifo para notação."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from typing import Any, Callable, Sequence

import numpy as np

from core.box_model import BoxEntry
from core.leitura_de_linha import distribuir, faixa_da_linha
from core.ocr_context import ContextDecoder
from core.ocr_result import (GlyphResult, LineResult, OCRHypothesis, OCRTrace,
                              PageResult, RegionResult)
from core.ocr_routing import OCRRouter, RoutingDecision


def _crop(image: np.ndarray, box: BoxEntry) -> np.ndarray:
    y1, y2 = max(0, box.y1), min(image.shape[0], box.y2)
    x1, x2 = max(0, box.x1), min(image.shape[1], box.x2)
    if y2 <= y1 or x2 <= x1:
        return np.empty((0, 0), dtype=image.dtype)
    return image[y1:y2, x1:x2]


def _alignment_summary(anchor: str, line: str) -> dict[str, Any]:
    """Resume as edições necessárias para auditar uma leitura de linha."""
    matcher = SequenceMatcher(None, anchor, line, autojunk=False)
    counts = {"insertions": 0, "deletions": 0, "substitutions": 0}
    for operation, start_a, end_a, start_b, end_b in matcher.get_opcodes():
        if operation == "insert":
            counts["insertions"] += end_b - start_b
        elif operation == "delete":
            counts["deletions"] += end_a - start_a
        elif operation == "replace":
            comuns = min(end_a - start_a, end_b - start_b)
            counts["substitutions"] += comuns
            counts["deletions"] += (end_a - start_a) - comuns
            counts["insertions"] += (end_b - start_b) - comuns
    counts["distance"] = sum(counts.values())
    counts["anchor_length"] = len(anchor)
    counts["line_length"] = len(line)
    counts["normalized_distance"] = (
        counts["distance"] / max(1, max(len(anchor), len(line)))
    )
    return counts


@dataclass
class HybridLineOutput:
    line: LineResult
    glyphs: list[GlyphResult] = field(default_factory=list)
    decision: RoutingDecision | None = None


class HybridOCRPipeline:
    """Executa reconhecimento por região sem misturar domínios.

    ``line_reader`` e ``glyph_reader`` recebem uma imagem numpy e devolvem
    ``OCRHypothesis`` (ou tuple ``(texto, confiança)``). A linha é mantida com
    espaços; a distribuição para caixas serve apenas para rastreabilidade.
    """

    def __init__(self, line_reader: Callable[[Any], Any],
                 glyph_reader: Callable[[Any], Any], *,
                 router: OCRRouter | None = None,
                 context_decoder: ContextDecoder | None = None,
                 unknown_fallback_confidence: float = 0.75,
                 trace: OCRTrace | None = None):
        if not 0.0 <= unknown_fallback_confidence <= 1.0:
            raise ValueError("limiar de fallback deve estar entre 0 e 1")
        self.line_reader = line_reader
        self.glyph_reader = glyph_reader
        self.router = router or OCRRouter()
        self.context_decoder = context_decoder
        self.unknown_fallback_confidence = unknown_fallback_confidence
        self.trace = trace

    @staticmethod
    def _hypothesis(value: Any, source: str) -> OCRHypothesis:
        if isinstance(value, OCRHypothesis):
            return value
        text, confidence = value if isinstance(value, tuple) and len(value) >= 2 else (value, 0.0)
        return OCRHypothesis(str(text or "").strip(), float(confidence or 0.0), source)

    def read_line(self, image: np.ndarray, boxes: Sequence[BoxEntry],
                  *, region: RegionResult, line_id: str) -> HybridLineOutput:
        decision = self.router.decide(region)
        glyphs: list[GlyphResult] = []
        anchors: list[OCRHypothesis] = []
        for index, box in enumerate(boxes):
            hypothesis = self._hypothesis(self.glyph_reader(_crop(image, box)), "glyph")
            anchors.append(hypothesis)
            glyphs.append(GlyphResult(f"{line_id}-g{index}", hypothesis.text,
                                      hypothesis.confidence,
                                      bbox=(box.x1, box.y1, box.x2, box.y2),
                                      source=hypothesis.source,
                                      line_id=line_id,
                                      metadata={"domain": decision.domain}))

        text = "".join(item.text for item in anchors)
        confidence = (sum(item.confidence for item in anchors) / len(anchors)
                      if anchors else 0.0)
        source = "glyph"
        line_engine = ""
        warnings: list[str] = []
        line_fallback: OCRHypothesis | None = None
        if decision.primary == "line" and boxes:
            faixa = faixa_da_linha(image, boxes)
            if faixa is not None:
                try:
                    line = self._hypothesis(self.line_reader(faixa), "line")
                    if line.text:
                        text, confidence, source = line.text, line.confidence, "line"
                        line_engine = line.source
                except Exception as error:  # fallback explícito para a âncora
                    warnings.append(f"line_reader:{type(error).__name__}: {error}")
            else:
                warnings.append("line_reader:empty_crop")

        # Notação e símbolos mantêm o reconhecedor especializado como fonte
        # principal, mas a linha é uma hipótese útil para revisão. Para uma
        # região ainda sem classificação, só pagamos o engine contextual quando
        # a âncora está fraca; isso evita transformar um fallback em uma segunda
        # leitura obrigatória de toda a página.
        media_ancora = (sum(item.confidence for item in anchors) / len(anchors)
                        if anchors else 0.0)
        deve_tentar_fallback = (
            decision.primary == "glyph" and boxes and
            (decision.domain in {"notation", "symbol"}
             or (decision.domain == "unknown"
                 and media_ancora < self.unknown_fallback_confidence))
        )
        if deve_tentar_fallback:
            faixa = faixa_da_linha(image, boxes)
            if faixa is not None:
                try:
                    candidato = self._hypothesis(
                        self.line_reader(faixa), "line-fallback")
                    if candidato.text:
                        line_fallback = candidato
                except Exception as error:
                    warnings.append(
                        f"line_fallback:{type(error).__name__}: {error}")

        anchor_text = "".join(a.text for a in anchors)
        result = OCRHypothesis(text, max(0.0, min(1.0, confidence)), source,
                               metadata={"domain": decision.domain,
                                         "routing": decision.to_dict(),
                                         "anchor_text": anchor_text,
                                         **({"line_fallback": line_fallback.text,
                                            "line_fallback_confidence": line_fallback.confidence,
                                            "line_fallback_source": line_fallback.source}
                                            if line_fallback else {}),
                                         **({"line_engine": line_engine} if line_engine else {})})
        if line_fallback is not None and line_fallback.text.replace(" ", "") != anchor_text:
            result.alternatives.append(line_fallback.text)
        if source == "line" and anchor_text:
            result.metadata["alignment"] = _alignment_summary(
                anchor_text, text.replace(" ", ""))
        if source == "line" and anchor_text and text.replace(" ", "") != anchor_text:
            # A linha contextual continua sendo o texto principal, mas o
            # desacordo é evidência de risco e precisa chegar à revisão.
            warnings.append("line_anchor_disagreement")
            result.metadata["line_text"] = text
            result.metadata["anchor_confidence"] = (
                sum(item.confidence for item in anchors) / len(anchors)
                if anchors else 0.0
            )
            result.alternatives = [anchor_text]
            # Reutiliza o alinhador validado do caminho de produção para
            # mostrar como a leitura contextual se distribuiria pelos boxes.
            # Isso não sobrescreve o texto da linha (que preserva espaços), mas
            # torna inserções, remoções e ligaduras observáveis para revisão.
            result.metadata["aligned_anchor"] = distribuir(
                [item.text for item in anchors], text.replace(" ", "")
            )
            result.metadata["alignment_changed"] = any(
                atual != antes for atual, antes in zip(
                    result.metadata["aligned_anchor"],
                    [item.text for item in anchors],
                )
            )
        if self.context_decoder is not None and decision.domain == "prose":
            result = self.context_decoder.decode(result)
        bbox = ((min((b.x1 for b in boxes), default=0),
                 min((b.y1 for b in boxes), default=0),
                 max((b.x2 for b in boxes), default=0),
                 max((b.y2 for b in boxes), default=0)) if boxes else None)
        line_result = LineResult(line_id, result.text, result.confidence, bbox=bbox,
                                 region_id=region.id,
                                 glyph_ids=[item.id for item in glyphs],
                                 alternatives=[OCRHypothesis(item, result.confidence, "alternative")
                                               for item in result.alternatives],
                                 warnings=warnings, metadata={**result.metadata,
                                                               "source": result.source})
        if self.trace is not None:
            self.trace.event(
                "line_result", line_id=line_id, region_id=region.id,
                domain=decision.domain, primary=decision.primary,
                source=result.source, text=result.text,
                confidence=result.confidence, alternatives=list(result.alternatives),
                warnings=list(warnings), metadata=dict(result.metadata),
            )
        return HybridLineOutput(line_result, glyphs, decision)

    def read_region(self, image: np.ndarray, boxes: Sequence[Sequence[BoxEntry]], *,
                    region: RegionResult, line_prefix: str = "line") -> list[HybridLineOutput]:
        """Lê uma região já segmentada em linhas pelo chamador."""
        # A segmentação geométrica é responsabilidade de ocr_layout/box_service;
        # aceitar linhas prontas evita reordenar colunas silenciosamente.
        return [self.read_line(image, line, region=region,
                               line_id=f"{line_prefix}-{i}")
                for i, line in enumerate(boxes)]

    def read_page(
        self,
        image: np.ndarray,
        regions: Sequence[tuple[RegionResult, Sequence[Sequence[BoxEntry]]]],
        *,
        page_id: str = "page-0",
    ) -> PageResult:
        """Reconhece uma página já segmentada e devolve ``PageResult``.

        A detecção de layout continua sendo responsabilidade do chamador. Isso
        é importante para a exportação: uma região pode atravessar várias linhas,
        mas a ordem entre colunas não deve ser inventada pelo OCR. Cada item de
        ``regions`` é ``(RegionResult, linhas_de_boxes)`` e a sequência recebida
        é a ordem de leitura definida pelo layout.

        O método é deliberadamente um agregador fino sobre ``read_region``.
        Assim, a decisão de roteamento, as âncoras e os warnings continuam
        exatamente iguais no uso unitário e passam a chegar também ao JSON de
        página.
        """
        saida_regioes: list[RegionResult] = []
        linhas = []
        glifos = []
        warnings: list[str] = []
        textos: list[str] = []
        confiancas: list[float] = []
        vistos: set[str] = set()

        for region, linhas_boxes in sorted(regions, key=lambda item: item[0].order):
            if region.id in vistos:
                raise ValueError(f"região repetida: {region.id}")
            vistos.add(region.id)
            outputs = self.read_region(
                image, linhas_boxes, region=region,
                line_prefix=f"{region.id}-line",
            )
            region_lines = [output.line for output in outputs]
            region_text = "\n".join(line.text for line in region_lines if line.text)
            region_conf = (
                sum(line.confidence for line in region_lines) / len(region_lines)
                if region_lines else 0.0
            )
            region_warnings = [warning for line in region_lines
                               for warning in line.warnings]
            saida_regioes.append(replace(
                region,
                text=region_text,
                confidence=region_conf,
                line_ids=[line.id for line in region_lines],
                warnings=list(region.warnings) + region_warnings,
                metadata={**region.metadata,
                          "routing": outputs[0].decision.to_dict()
                          if outputs and outputs[0].decision else None},
            ))
            linhas.extend(region_lines)
            glifos.extend(glyph for output in outputs for glyph in output.glyphs)
            warnings.extend(f"{region.id}:{warning}"
                            for warning in region_warnings)
            if region_text:
                textos.append(region_text)
                confiancas.append(region_conf)

        page_confidence = (sum(confiancas) / len(confiancas)
                           if confiancas else 0.0)
        pagina = PageResult(
            page_id=page_id,
            text="\n\n".join(textos),
            confidence=page_confidence,
            regions=saida_regioes,
            lines=linhas,
            glyphs=glifos,
            warnings=warnings,
            metadata={"pipeline": "hybrid", "region_count": len(saida_regioes),
                      "line_count": len(linhas), "glyph_count": len(glifos)},
        )
        if self.trace is not None:
            self.trace.event("page_result", page_id=page_id,
                             confidence=page_confidence,
                             region_count=len(saida_regioes),
                             line_count=len(linhas), glyph_count=len(glifos),
                             warning_count=len(warnings))
        return pagina
