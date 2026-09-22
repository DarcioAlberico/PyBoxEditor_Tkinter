"""Documento editorial intermediário versionado.

Este módulo é o seam da Fase 1. Ele não conhece Tkinter, PyMuPDF, OCR engines
ou exportadores. Guarda evidência, hipóteses, decisões e eventos de revisão em
uma árvore estável que todos os formatos de saída poderão consumir.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "pyboxeditor.editorial-document/v1"
#: Os tipos de bloco do IR.
#:
#: ``figure`` entrou no item 4 da revisão de 2026-09-18: o adapter do leitor
#: medido mandava **toda** `livro.Figura` como ``diagram``, e três das quatro
#: origens dela não são um tabuleiro — a faixa impressa acima do diagrama é
#: legenda (``caption``), e a página inteira que virou imagem é figura. Com um
#: tipo só, quem exportava punha `data-fen` numa imagem de cabeçalho e o editor
#: tentava ler uma posição onde não havia nenhuma.
BLOCK_KINDS = frozenset({
    "paragraph", "heading", "caption", "chess_sequence", "diagram", "figure",
    "table", "header", "footer", "page_break", "unknown",
})
DECISION_STATUSES = frozenset({"automatic", "reviewed", "rejected", "unresolved"})


def _bbox(value: Sequence[int | float] | None) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    if len(value) != 4:
        raise ValueError("bounding box deve conter quatro coordenadas")
    result = tuple(int(round(float(item))) for item in value)
    if result[2] <= result[0] or result[3] <= result[1]:
        raise ValueError("bounding box precisa ter área positiva")
    return result  # type: ignore[return-value]


def _confidence(value: float) -> float:
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError("confiança deve estar entre 0 e 1")
    return result


def _required(value: str, name: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{name} não pode ser vazio")
    return result


@dataclass(frozen=True)
class SourceRef:
    document_id: str
    page_index: int
    bbox: tuple[int, int, int, int] | None = None
    image_hash: str = ""
    source_kind: str = "derived"

    def __post_init__(self) -> None:
        object.__setattr__(self, "document_id", _required(self.document_id, "document_id"))
        if int(self.page_index) < 0:
            raise ValueError("page_index não pode ser negativo")
        object.__setattr__(self, "page_index", int(self.page_index))
        object.__setattr__(self, "bbox", _bbox(self.bbox))
        object.__setattr__(self, "image_hash", str(self.image_hash or ""))
        object.__setattr__(self, "source_kind", _required(self.source_kind, "source_kind"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "page_index": self.page_index,
            "bbox": list(self.bbox) if self.bbox else None,
            "image_hash": self.image_hash,
            "source_kind": self.source_kind,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourceRef":
        return cls(
            document_id=str(data["document_id"]),
            page_index=int(data["page_index"]),
            bbox=data.get("bbox"),
            image_hash=str(data.get("image_hash", "")),
            source_kind=str(data.get("source_kind", "derived")),
        )


@dataclass
class Hypothesis:
    id: str
    text: str
    confidence: float
    source: str
    bbox: tuple[int, int, int, int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _required(self.id, "hypothesis.id")
        self.text = str(self.text)
        self.confidence = _confidence(self.confidence)
        self.source = _required(self.source, "hypothesis.source")
        self.bbox = _bbox(self.bbox)
        self.metadata = dict(self.metadata or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "text": self.text, "confidence": self.confidence,
            "source": self.source,
            "bbox": list(self.bbox) if self.bbox else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Hypothesis":
        return cls(
            id=str(data["id"]), text=str(data.get("text", "")),
            confidence=float(data.get("confidence", 0.0)),
            source=str(data.get("source", "unknown")), bbox=data.get("bbox"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class Evidence:
    id: str
    ref: SourceRef
    observed_text: str = ""
    alternatives: list[Hypothesis] = field(default_factory=list)
    engine: str = ""
    model_version: str = ""
    confidence: float = 0.0
    preprocessing: str = "original"
    diagnostics: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _required(self.id, "evidence.id")
        self.alternatives = list(self.alternatives)
        self.confidence = _confidence(self.confidence)
        self.engine = str(self.engine or "")
        self.model_version = str(self.model_version or "")
        self.preprocessing = str(self.preprocessing or "original")
        self.diagnostics = [str(item) for item in self.diagnostics]
        self.metadata = dict(self.metadata or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "ref": self.ref.to_dict(),
            "observed_text": self.observed_text,
            "alternatives": [item.to_dict() for item in self.alternatives],
            "engine": self.engine, "model_version": self.model_version,
            "confidence": self.confidence, "preprocessing": self.preprocessing,
            "diagnostics": list(self.diagnostics), "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Evidence":
        return cls(
            id=str(data["id"]), ref=SourceRef.from_dict(data["ref"]),
            observed_text=str(data.get("observed_text", "")),
            alternatives=[Hypothesis.from_dict(item)
                          for item in data.get("alternatives", [])],
            engine=str(data.get("engine", "")),
            model_version=str(data.get("model_version", "")),
            confidence=float(data.get("confidence", 0.0)),
            preprocessing=str(data.get("preprocessing", "original")),
            diagnostics=list(data.get("diagnostics", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class Decision:
    value: Any
    evidence_ids: list[str]
    status: str
    reason_codes: list[str] = field(default_factory=list)
    original_value: Any = None

    def __post_init__(self) -> None:
        self.evidence_ids = [str(item) for item in self.evidence_ids]
        self.status = str(self.status)
        if self.status not in DECISION_STATUSES:
            raise ValueError(f"status de decisão inválido: {self.status!r}")
        self.reason_codes = [str(item) for item in self.reason_codes]

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "evidence_ids": list(self.evidence_ids),
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "original_value": self.original_value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Decision":
        return cls(
            value=data.get("value"), evidence_ids=list(data.get("evidence_ids", [])),
            status=str(data.get("status", "unresolved")),
            reason_codes=list(data.get("reason_codes", [])),
            original_value=data.get("original_value"),
        )


@dataclass
class EditorialBlock:
    id: str
    kind: str
    order: int
    source_refs: list[SourceRef]
    decision: Decision
    children: list[str] = field(default_factory=list)
    style: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _required(self.id, "block.id")
        self.kind = str(self.kind)
        if self.kind not in BLOCK_KINDS:
            raise ValueError(f"tipo de bloco inválido: {self.kind!r}")
        self.order = int(self.order)
        self.source_refs = list(self.source_refs)
        self.children = [str(item) for item in self.children]
        self.style = dict(self.style or {})
        self.warnings = [str(item) for item in self.warnings]
        self.metadata = dict(self.metadata or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "order": self.order,
            "source_refs": [item.to_dict() for item in self.source_refs],
            "decision": self.decision.to_dict(), "children": list(self.children),
            "style": dict(self.style), "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EditorialBlock":
        return cls(
            id=str(data["id"]), kind=str(data["kind"]), order=int(data["order"]),
            source_refs=[SourceRef.from_dict(item) for item in data.get("source_refs", [])],
            decision=Decision.from_dict(data["decision"]),
            children=list(data.get("children", [])), style=dict(data.get("style", {})),
            warnings=list(data.get("warnings", [])), metadata=dict(data.get("metadata", {})),
        )


@dataclass
class EditorialPage:
    page_id: str
    page_index: int
    source_refs: list[SourceRef]
    blocks: list[EditorialBlock]
    evidence: list[Evidence]
    observations: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.page_id = _required(self.page_id, "page_id")
        self.page_index = int(self.page_index)
        if self.page_index < 0:
            raise ValueError("page_index não pode ser negativo")
        self.source_refs = list(self.source_refs)
        self.blocks = list(self.blocks)
        self.evidence = list(self.evidence)
        self.observations = dict(self.observations or {})
        self.warnings = [str(item) for item in self.warnings]
        self.metadata = dict(self.metadata or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id, "page_index": self.page_index,
            "source_refs": [item.to_dict() for item in self.source_refs],
            "blocks": [item.to_dict() for item in self.blocks],
            "evidence": [item.to_dict() for item in self.evidence],
            "observations": dict(self.observations), "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EditorialPage":
        return cls(
            page_id=str(data["page_id"]), page_index=int(data["page_index"]),
            source_refs=[SourceRef.from_dict(item) for item in data.get("source_refs", [])],
            blocks=[EditorialBlock.from_dict(item) for item in data.get("blocks", [])],
            evidence=[Evidence.from_dict(item) for item in data.get("evidence", [])],
            observations=dict(data.get("observations", {})),
            warnings=list(data.get("warnings", [])), metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class ReviewEvent:
    event_id: str
    document_id: str
    page_id: str
    target_id: str
    before: Any
    after: Any
    status: str
    reason_codes: tuple[str, ...]
    user: str
    created_at: str
    model_version: str = ""
    source_refs: tuple[SourceRef, ...] = ()
    #: O estado da decisão **antes** deste evento. É o que deixa `undo`
    #: devolver o bloco ao estado em que estava — o aceito e desfeito volta
    #: para a fila —, e não só ao valor. Vazio no evento gravado antes de
    #: existir (2026-09-19), que desfaz para `reviewed` como sempre desfez.
    before_status: str = ""

    def __post_init__(self) -> None:
        for name in ("event_id", "document_id", "page_id", "target_id", "user", "created_at"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        if self.status not in DECISION_STATUSES:
            raise ValueError(f"status de evento inválido: {self.status!r}")
        object.__setattr__(self, "reason_codes", tuple(str(item) for item in self.reason_codes))
        object.__setattr__(self, "model_version", str(self.model_version or ""))
        object.__setattr__(self, "source_refs", tuple(self.source_refs))
        object.__setattr__(self, "before_status", str(self.before_status or ""))
        if self.before_status and self.before_status not in DECISION_STATUSES:
            raise ValueError(f"estado anterior inválido: {self.before_status!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id, "document_id": self.document_id,
            "page_id": self.page_id, "target_id": self.target_id,
            "before": self.before, "after": self.after, "status": self.status,
            "reason_codes": list(self.reason_codes), "user": self.user,
            "created_at": self.created_at, "model_version": self.model_version,
            "source_refs": [item.to_dict() for item in self.source_refs],
            "before_status": self.before_status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReviewEvent":
        return cls(
            event_id=str(data["event_id"]), document_id=str(data["document_id"]),
            page_id=str(data["page_id"]), target_id=str(data["target_id"]),
            before=data.get("before"), after=data.get("after"),
            status=str(data.get("status", "reviewed")),
            reason_codes=tuple(data.get("reason_codes", ())),
            user=str(data.get("user", "unknown")),
            created_at=str(data["created_at"]),
            model_version=str(data.get("model_version", "")),
            source_refs=tuple(SourceRef.from_dict(item)
                             for item in data.get("source_refs", [])),
            before_status=str(data.get("before_status", "")),
        )


@dataclass
class EditorialDocument:
    document_id: str
    title: str
    language: str
    pages: list[EditorialPage]
    schema: str = SCHEMA
    pipeline_version: str = ""
    source_sha256: str = ""
    model_manifest: str = ""
    review_events: list[ReviewEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.document_id = _required(self.document_id, "document_id")
        self.title = str(self.title)
        self.language = str(self.language)
        self.pages = list(self.pages)
        self.schema = str(self.schema)
        self.pipeline_version = str(self.pipeline_version or "")
        self.source_sha256 = str(self.source_sha256 or "")
        self.model_manifest = str(self.model_manifest or "")
        self.review_events = list(self.review_events)
        self.metadata = dict(self.metadata or {})
        if self.schema != SCHEMA:
            raise ValueError(f"schema editorial não suportado: {self.schema!r}")

    def validate(self) -> list[str]:
        warnings: list[str] = []
        page_ids: set[str] = set()
        block_ids: set[str] = set()
        event_ids: set[str] = set()
        for page in self.pages:
            if page.page_id in page_ids:
                raise ValueError(f"página editorial duplicada: {page.page_id}")
            page_ids.add(page.page_id)
            evidence_ids = {item.id for item in page.evidence}
            if len(evidence_ids) != len(page.evidence):
                raise ValueError(f"evidência duplicada na página {page.page_id}")
            orders: set[int] = set()
            for block in page.blocks:
                if block.id in block_ids:
                    raise ValueError(f"bloco editorial duplicado: {block.id}")
                block_ids.add(block.id)
                if block.order in orders:
                    raise ValueError(f"ordem de bloco duplicada na página {page.page_id}")
                orders.add(block.order)
                faltantes = set(block.decision.evidence_ids) - evidence_ids
                if faltantes:
                    raise ValueError(
                        f"bloco {block.id} referencia evidência inexistente: {sorted(faltantes)}")
        for event in self.review_events:
            if event.event_id in event_ids:
                raise ValueError(f"evento de revisão duplicado: {event.event_id}")
            event_ids.add(event.event_id)
            if event.document_id != self.document_id:
                raise ValueError(f"evento {event.event_id} pertence a outro documento")
            if event.page_id not in page_ids:
                raise ValueError(f"evento {event.event_id} referencia página inexistente")
            if event.target_id not in block_ids:
                raise ValueError(f"evento {event.event_id} referencia alvo inexistente")
        return warnings

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema": self.schema, "document_id": self.document_id,
            "title": self.title, "language": self.language,
            "pipeline_version": self.pipeline_version,
            "source_sha256": self.source_sha256,
            "model_manifest": self.model_manifest,
            "pages": [item.to_dict() for item in self.pages],
            "review_events": [item.to_dict() for item in self.review_events],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EditorialDocument":
        resultado = cls(
            document_id=str(data["document_id"]), title=str(data.get("title", "")),
            language=str(data.get("language", "und")),
            pages=[EditorialPage.from_dict(item) for item in data.get("pages", [])],
            schema=str(data.get("schema", SCHEMA)),
            pipeline_version=str(data.get("pipeline_version", "")),
            source_sha256=str(data.get("source_sha256", "")),
            model_manifest=str(data.get("model_manifest", "")),
            review_events=[ReviewEvent.from_dict(item)
                           for item in data.get("review_events", [])],
            metadata=dict(data.get("metadata", {})),
        )
        resultado.validate()
        return resultado

    def save_json(self, caminho: str | Path) -> Path:
        destino = Path(caminho)
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_suffix(destino.suffix + ".tmp")
        temporario.write_text(json.dumps(self.to_dict(), ensure_ascii=False,
                                         indent=2) + "\n", encoding="utf-8")
        temporario.replace(destino)
        return destino

    @classmethod
    def load_json(cls, caminho: str | Path) -> "EditorialDocument":
        with Path(caminho).open(encoding="utf-8") as arquivo:
            valor = json.load(arquivo)
        if not isinstance(valor, Mapping):
            raise ValueError("documento editorial precisa ser um objeto JSON")
        return cls.from_dict(valor)

    def apply_review(self, event: ReviewEvent) -> "EditorialDocument":
        if event.document_id != self.document_id:
            raise ValueError("evento pertence a outro documento")
        if any(item.event_id == event.event_id for item in self.review_events):
            raise ValueError(f"evento já aplicado: {event.event_id}")
        atualizado = copy.deepcopy(self)
        pagina = next((item for item in atualizado.pages if item.page_id == event.page_id), None)
        if pagina is None:
            raise ValueError(f"alvo do evento referencia página inexistente: {event.page_id}")
        bloco = next((item for item in pagina.blocks if item.id == event.target_id), None)
        if bloco is None:
            raise ValueError(f"alvo do evento inexistente: {event.target_id}")
        if bloco.decision.value != event.before:
            raise ValueError(f"valor anterior do alvo {event.target_id} não confere")
        original = (copy.deepcopy(bloco.decision.original_value)
                    if bloco.decision.original_value is not None
                    else copy.deepcopy(event.before))
        bloco.decision = Decision(
            value=copy.deepcopy(event.after),
            evidence_ids=list(bloco.decision.evidence_ids),
            status=event.status,
            reason_codes=list(event.reason_codes),
            original_value=original,
        )
        atualizado.review_events.append(event)
        atualizado.validate()
        return atualizado
