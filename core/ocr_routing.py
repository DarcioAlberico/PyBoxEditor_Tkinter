"""Roteamento de regiões OCR por domínio de conteúdo."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from core.ocr_result import RegionResult


# Cabeçalho e rodapé continuam com o seu tipo original no layout, mas são
# texto para fins de reconhecimento. Mantê-los em ``unknown`` fazia o pipeline
# ignorar justamente o contexto de linha e deixava a filtragem/reconstrução
# posterior sem uma hipótese contextual auditável.
PROSE_TYPES = frozenset({"body", "heading", "caption", "quote", "header", "footer"})
GLYPH_TYPES = frozenset({"notation", "symbol"})
SPECIAL_TYPES = frozenset({"diagram", "table"})


@dataclass(frozen=True)
class RoutingDecision:
    region_id: str
    domain: str
    primary: str
    fallback: str
    reason: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class OCRRouter:
    """Decide o caminho de OCR sem executar engine algum."""

    def decide(self, region: RegionResult) -> RoutingDecision:
        tipo = str(region.type).casefold()
        metadata = region.metadata or {}
        dominio_forcado = metadata.get("domain")
        if dominio_forcado:
            tipo = str(dominio_forcado).casefold()
            motivo = "metadata.domain"
        else:
            motivo = f"region_type={region.type}"

        if tipo in PROSE_TYPES or tipo == "prose":
            return RoutingDecision(region.id, "prose", "line", "glyph",
                                   motivo, 0.90 if tipo != "prose" else 0.95)
        if tipo in GLYPH_TYPES:
            return RoutingDecision(region.id, tipo, "glyph", "line", motivo, 0.95)
        if tipo == "unknown":
            return RoutingDecision(region.id, "unknown", "glyph", "line", motivo, 0.45)
        if tipo in SPECIAL_TYPES:
            return RoutingDecision(region.id, tipo, "special", "line", motivo, 0.85)
        return RoutingDecision(region.id, "unknown", "glyph", "line", motivo, 0.35)

    def decide_all(self, regions: Sequence[RegionResult]) -> list[RoutingDecision]:
        return [self.decide(region) for region in regions]


def rotear_regiao(region: RegionResult) -> RoutingDecision:
    return OCRRouter().decide(region)


def registrar_roteamento(regions: Iterable[RegionResult]) -> list[dict[str, Any]]:
    """Retorna um registro serializável para benchmark e diagnóstico."""
    return [item.to_dict() for item in OCRRouter().decide_all(list(regions))]
