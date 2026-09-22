"""Treino seguro, active learning e calibração da Fase 7.

O módulo é a seam de dados da cadeia editorial: recebe correções já decididas
por humanos e produz artefatos versionados, splits sem vazamento, amostras de
maior valor, relatórios de confiabilidade e manifestos verificáveis de pesos.
Não treina um modelo silenciosamente nem mistura holdout real com dados
sintéticos.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from core.editorial_model import EditorialDocument


CORRECTION_SCHEMA = "pyboxeditor.ocr-corrections/v1"
WEIGHT_SCHEMA = "pyboxeditor.ocr-weights/v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str).encode("utf-8")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class CorrectionRecord:
    record_id: str
    document_id: str
    page_id: str
    target_id: str
    domain: str
    kind: str
    before: Any
    after: Any
    source_id: str
    editor: str
    created_at: str
    confidence: float = 0.0
    impact: float = 0.0
    synthetic: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.record_id = str(self.record_id)
        self.document_id = str(self.document_id)
        self.page_id = str(self.page_id)
        self.target_id = str(self.target_id)
        self.domain = str(self.domain or "unknown")
        self.kind = str(self.kind or "unknown")
        self.source_id = str(self.source_id or self.document_id)
        self.editor = str(self.editor or "unknown")
        self.created_at = str(self.created_at or _now())
        self.confidence = min(1.0, max(0.0, float(self.confidence)))
        self.impact = max(0.0, float(self.impact))
        self.metadata = dict(self.metadata or {})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CorrectionRecord":
        return cls(**dict(data))


@dataclass
class CorrectionDataset:
    name: str
    records: list[CorrectionRecord] = field(default_factory=list)
    version: str = "1"
    schema: str = CORRECTION_SCHEMA
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema != CORRECTION_SCHEMA:
            raise ValueError(f"schema de correções não suportado: {self.schema!r}")
        self.name = str(self.name).strip()
        if not self.name:
            raise ValueError("dataset de correções precisa de nome")
        self.version = str(self.version)
        self.records = list(self.records)
        self.metadata = dict(self.metadata or {})
        ids = [record.record_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("dataset contém correções duplicadas")

    @classmethod
    def from_document(cls, document: EditorialDocument, *,
                      name: str = "editorial-corrections") -> "CorrectionDataset":
        pages = {page.page_id: page for page in document.pages}
        blocks = {block.id: (page, block) for page in document.pages for block in page.blocks}
        evidence = {item.id: item for page in document.pages for item in page.evidence}
        records: list[CorrectionRecord] = []
        for event in document.review_events:
            if "undo" in event.reason_codes:
                continue
            page, block = blocks.get(event.target_id, (pages.get(event.page_id), None))
            if page is None or block is None:
                continue
            refs = block.source_refs or page.source_refs
            source_id = refs[0].document_id if refs else document.document_id
            confidences = [evidence[item].confidence for item in block.decision.evidence_ids
                           if item in evidence]
            confidence = min(confidences) if confidences else 0.0
            impact = (100.0 if block.kind == "diagram" else
                      85.0 if block.kind == "chess_sequence" else 50.0)
            records.append(CorrectionRecord(
                record_id=event.event_id, document_id=document.document_id,
                page_id=event.page_id, target_id=event.target_id,
                domain=str(block.metadata.get("domain", block.kind)), kind=block.kind,
                before=copy.deepcopy(event.before), after=copy.deepcopy(event.after),
                source_id=source_id, editor=event.user, created_at=event.created_at,
                confidence=confidence, impact=impact,
                metadata={"reason_codes": list(event.reason_codes),
                          "source_refs": [ref.to_dict() for ref in refs]},
            ))
        return cls(name, records, metadata={"document_id": document.document_id})

    def append(self, record: CorrectionRecord) -> None:
        if any(item.record_id == record.record_id for item in self.records):
            raise ValueError(f"correção já registrada: {record.record_id}")
        self.records.append(record)

    def corpus_items(self) -> list["CorpusItem"]:
        """Converte correções em itens de split sem perder a proveniência."""
        return [CorpusItem(
            id=record.record_id, document_id=record.document_id,
            book_id=str(record.metadata.get("book_id", record.document_id)),
            editor_id=record.editor, source_id=record.source_id,
            layout=str(record.metadata.get("layout", "unknown")),
            domain=record.domain, synthetic=record.synthetic,
            holdout=bool(record.metadata.get("holdout", False)
                         or record.metadata.get("split") == "holdout"),
            payload=record.to_dict(),
        ) for record in self.records]

    def to_dict(self, *, include_checksum: bool = True) -> dict[str, Any]:
        data = {"schema": self.schema, "name": self.name, "version": self.version,
                "records": [item.to_dict() for item in self.records],
                "metadata": dict(self.metadata)}
        if include_checksum:
            data["checksum"] = self.digest()
        return data

    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict(include_checksum=False))).hexdigest()

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        temporary.replace(target)
        return target

    @classmethod
    def load(cls, path: str | Path) -> "CorrectionDataset":
        target = Path(path)
        data = json.loads(target.read_text(encoding="utf-8"))
        expected = str(data.get("checksum", ""))
        dataset = cls(str(data["name"]),
                      [CorrectionRecord.from_dict(item) for item in data.get("records", ())],
                      version=str(data.get("version", "1")),
                      schema=str(data.get("schema", CORRECTION_SCHEMA)),
                      metadata=dict(data.get("metadata", {})))
        if expected and expected != dataset.digest():
            raise ValueError("checksum do dataset de correções não corresponde")
        return dataset


@dataclass(frozen=True)
class ActiveSample:
    item_id: str
    score: float
    uncertainty: float
    impact: float
    domain: str
    kind: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


def _active_values(item: Any) -> tuple[str, float, float, str, str, Mapping[str, Any]]:
    if isinstance(item, CorrectionRecord):
        return (item.record_id, 1.0 - item.confidence, item.impact,
                item.domain, item.kind, item.metadata)
    if isinstance(item, Mapping):
        confidence = float(item.get("confidence", item.get("score", 0.0)))
        return (str(item.get("id", item.get("target_id", ""))), 1.0 - confidence,
                float(item.get("impact", item.get("severity", 0.0))),
                str(item.get("domain", "unknown")), str(item.get("kind", "unknown")), item)
    metadata = getattr(item, "metadata", {}) or {}
    confidence = float(getattr(item, "confidence", 0.0))
    return (str(getattr(item, "target_id", getattr(item, "id", ""))), 1.0 - confidence,
            float(getattr(item, "severity", 0.0)),
            str(getattr(item, "domain", metadata.get("domain", "unknown"))),
            str(getattr(item, "kind", "unknown")), metadata)


def sample_active(items: Iterable[Any], limit: int, *, seed: int = 42) -> list[ActiveSample]:
    """Seleciona casos difíceis sem aleatoriedade opaca ou repetição silenciosa."""
    candidates: list[ActiveSample] = []
    for item in items:
        item_id, uncertainty, impact, domain, kind, metadata = _active_values(item)
        if not item_id:
            continue
        normalized_impact = impact / 100.0 if impact > 1.0 else max(0.0, impact)
        score = .65 * uncertainty + .35 * min(1.0, normalized_impact)
        candidates.append(ActiveSample(item_id, score, uncertainty, normalized_impact,
                                       domain, kind, dict(metadata)))
    rng = random.Random(seed)
    rng.shuffle(candidates)
    candidates.sort(key=lambda item: (-item.score, item.item_id))
    return candidates[:max(0, int(limit))]


class ActiveSampler:
    """Interface pequena para o seletor usado por CLI, UI e benchmarks."""

    def __init__(self, *, seed: int = 42):
        self.seed = int(seed)

    def select(self, items: Iterable[Any], limit: int) -> list[ActiveSample]:
        return sample_active(items, limit, seed=self.seed)


@dataclass
class CorpusItem:
    id: str
    document_id: str
    book_id: str
    editor_id: str
    source_id: str
    layout: str
    domain: str
    synthetic: bool = False
    holdout: bool = False
    payload: Any = None


@dataclass
class CorpusSplit:
    train: list[CorpusItem] = field(default_factory=list)
    validation: list[CorpusItem] = field(default_factory=list)
    test: list[CorpusItem] = field(default_factory=list)
    holdout: list[CorpusItem] = field(default_factory=list)
    synthetic: list[CorpusItem] = field(default_factory=list)

    def all_real(self) -> list[CorpusItem]:
        return [*self.train, *self.validation, *self.test, *self.holdout]

    def to_dict(self) -> dict[str, Any]:
        return {name: [asdict(item) for item in getattr(self, name)]
                for name in ("train", "validation", "test", "holdout", "synthetic")}

    def validate(self) -> None:
        """Levanta `ValueError` no primeiro vazamento. Não devolve avisos:
        tudo que esta checagem encontra é fatal — um split que vaza não serve
        para medir nada."""
        if any(item.synthetic for item in self.holdout):
            raise ValueError("holdout real não pode conter item sintético")
        seen: dict[tuple[str, str], str] = {}
        # O holdout entra na checagem: é o conjunto que **nunca** pode
        # compartilhar livro, editor, fonte ou layout com o que treinou, e
        # ficava de fora do laço — `evaluate_holdout` mediria contra um
        # holdout contaminado sem que nada acusasse.
        for split_name in ("train", "validation", "test", "holdout"):
            for item in getattr(self, split_name):
                for field_name in ("book_id", "editor_id", "source_id", "layout"):
                    value = str(getattr(item, field_name) or "")
                    if not value:
                        continue
                    key = (field_name, value)
                    previous = seen.get(key)
                    if previous is not None and previous != split_name:
                        raise ValueError(f"vazamento de {field_name}: {value}")
                    seen[key] = split_name


def _union_groups(items: Sequence[CorpusItem]) -> list[list[CorpusItem]]:
    parents = list(range(len(items)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parents[b] = a

    seen: dict[tuple[str, str], int] = {}
    for index, item in enumerate(items):
        for field_name in ("book_id", "editor_id", "source_id", "layout"):
            value = str(getattr(item, field_name) or "")
            if value:
                key = (field_name, value)
                if key in seen:
                    union(index, seen[key])
                else:
                    seen[key] = index
    groups: dict[int, list[CorpusItem]] = {}
    for index, item in enumerate(items):
        groups.setdefault(find(index), []).append(item)
    return sorted(groups.values(), key=lambda group: min(item.id for item in group))


def split_corpus(records: Sequence[CorpusItem], *, validation_fraction: float = .15,
                 test_fraction: float = .15, seed: int = 42) -> CorpusSplit:
    if validation_fraction < 0 or test_fraction < 0 or validation_fraction + test_fraction >= 1:
        raise ValueError("frações de validação e teste inválidas")
    resultado = CorpusSplit()
    reais = [item for item in records if not item.synthetic and not item.holdout]
    resultado.synthetic = [item for item in records if item.synthetic]
    resultado.holdout = [item for item in records if item.holdout and not item.synthetic]
    groups = _union_groups(reais)
    random.Random(seed).shuffle(groups)
    n_test = min(len(groups), max(0, round(len(groups) * test_fraction)))
    n_validation = min(len(groups) - n_test,
                       max(0, round(len(groups) * validation_fraction)))
    if len(groups) >= 3 and test_fraction and n_test == 0:
        n_test = 1
    if len(groups) - n_test >= 2 and validation_fraction and n_validation == 0:
        n_validation = 1
    for index, group in enumerate(groups):
        destination = (resultado.test if index < n_test else
                       resultado.validation if index < n_test + n_validation else resultado.train)
        destination.extend(sorted(group, key=lambda item: item.id))
    for values in (resultado.train, resultado.validation, resultado.test,
                   resultado.holdout, resultado.synthetic):
        values.sort(key=lambda item: item.id)
    resultado.validate()
    return resultado


def split_corrections(dataset: CorrectionDataset, *, validation_fraction: float = .15,
                      test_fraction: float = .15, seed: int = 42) -> CorpusSplit:
    return split_corpus(dataset.corpus_items(), validation_fraction=validation_fraction,
                        test_fraction=test_fraction, seed=seed)


@dataclass(frozen=True)
class HoldoutResult:
    before: float
    after: float
    delta: float
    improved: bool
    samples: int
    minimum_delta: float
    higher_is_better: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mean_metric(values: Sequence[bool | float] | Mapping[str, bool | float]) -> tuple[float, int]:
    raw = list(values.values()) if isinstance(values, Mapping) else list(values)
    if not raw:
        raise ValueError("holdout sem observações")
    return sum(float(value) for value in raw) / len(raw), len(raw)


def evaluate_holdout(before: Sequence[bool | float] | Mapping[str, bool | float],
                     after: Sequence[bool | float] | Mapping[str, bool | float], *,
                     minimum_delta: float = 0.0, higher_is_better: bool = True) -> HoldoutResult:
    """Gateia uma rodada contra o holdout, nunca contra o corpus de correções."""
    before_score, before_count = _mean_metric(before)
    after_score, after_count = _mean_metric(after)
    if before_count != after_count:
        raise ValueError("avaliações do holdout têm tamanhos diferentes")
    raw_delta = after_score - before_score
    delta = raw_delta if higher_is_better else -raw_delta
    return HoldoutResult(before_score, after_score, delta, delta >= minimum_delta,
                         after_count, float(minimum_delta), higher_is_better)


@dataclass(frozen=True)
class CalibrationObservation:
    domain: str
    confidence: float
    correct: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain", str(self.domain or "unknown"))
        object.__setattr__(self, "confidence", min(1.0, max(0.0, float(self.confidence))))
        object.__setattr__(self, "correct", bool(self.correct))


def _ece(confidences: Sequence[float], correct: Sequence[bool], bins: int) -> float:
    if not confidences:
        return float("nan")
    total = 0.0
    for index in range(bins):
        lo, hi = index / bins, (index + 1) / bins
        selected = [i for i, value in enumerate(confidences)
                    if (value > lo or index == 0 and value == lo) and value <= hi]
        if selected:
            accuracy = sum(bool(correct[i]) for i in selected) / len(selected)
            confidence = sum(confidences[i] for i in selected) / len(selected)
            total += len(selected) / len(confidences) * abs(accuracy - confidence)
    return total


def _calibrated(value: float, temperature: float) -> float:
    epsilon = 1e-6
    clipped = min(1.0 - epsilon, max(epsilon, value))
    logit = math.log(clipped / (1.0 - clipped))
    return 1.0 / (1.0 + math.exp(-logit / temperature))


@dataclass(frozen=True)
class DomainCalibration:
    domain: str
    temperature: float
    samples: int
    before_ece: float
    after_ece: float
    reliability: tuple[Mapping[str, float], ...]

    def apply(self, confidence: float) -> float:
        return _calibrated(float(confidence), self.temperature)


@dataclass(frozen=True)
class ReliabilityReport:
    calibrations: Mapping[str, DomainCalibration]
    bins: int

    @property
    def domains(self) -> tuple[str, ...]:
        return tuple(sorted(self.calibrations))

    @property
    def reliability(self) -> dict[str, tuple[Mapping[str, float], ...]]:
        return {domain: item.reliability for domain, item in self.calibrations.items()}

    def for_domain(self, domain: str) -> DomainCalibration:
        return self.calibrations.get(domain, self.calibrations.get("unknown", DomainCalibration(
            domain, 1.0, 0, float("nan"), float("nan"), ())))

    def apply(self, domain: str, confidence: float) -> float:
        return self.for_domain(domain).apply(confidence)

    def to_dict(self) -> dict[str, Any]:
        return {"bins": self.bins, "domains": {
            domain: {**asdict(calibration), "reliability": list(calibration.reliability)}
            for domain, calibration in self.calibrations.items()
        }}


def calibrate_domains(observations: Sequence[CalibrationObservation], *,
                      bins: int = 15) -> ReliabilityReport:
    if bins < 1:
        raise ValueError("bins deve ser positivo")
    grouped: dict[str, list[CalibrationObservation]] = {}
    for item in observations:
        if not isinstance(item, CalibrationObservation):
            item = CalibrationObservation(str(item["domain"]), item["confidence"], item["correct"])
        grouped.setdefault(item.domain, []).append(item)
    calibrations: dict[str, DomainCalibration] = {}
    for domain, values in grouped.items():
        confidences = [item.confidence for item in values]
        correct = [item.correct for item in values]
        before = _ece(confidences, correct, bins)
        best_temperature, best_ece = 1.0, before
        for step in range(1, 101):
            temperature = .5 + step * .05
            calibrated = [_calibrated(value, temperature) for value in confidences]
            candidate = _ece(calibrated, correct, bins)
            if candidate < best_ece:
                best_temperature, best_ece = temperature, candidate
        calibrated = [_calibrated(value, best_temperature) for value in confidences]
        reliability = []
        for index in range(bins):
            lo, hi = index / bins, (index + 1) / bins
            selected = [i for i, value in enumerate(calibrated)
                        if (value > lo or index == 0 and value == lo) and value <= hi]
            if selected:
                reliability.append({"lower": lo, "upper": hi,
                                    "confidence": sum(calibrated[i] for i in selected) / len(selected),
                                    "accuracy": sum(correct[i] for i in selected) / len(selected),
                                    "count": float(len(selected))})
        calibrations[domain] = DomainCalibration(
            domain, best_temperature, len(values), before, _ece(calibrated, correct, bins),
            tuple(reliability))
    return ReliabilityReport(calibrations, bins)


@dataclass(frozen=True)
class WeightCompatibility:
    compatible: bool
    errors: tuple[str, ...] = ()


@dataclass
class WeightManifest:
    model_id: str
    path: str
    sha256: str
    schema: str = WEIGHT_SCHEMA
    pipeline_version: str = ""
    config_hash: str = ""
    domains: tuple[str, ...] = ()
    created_at: str = field(default_factory=_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.model_id = str(self.model_id).strip()
        if not self.model_id:
            raise ValueError("manifesto de pesos precisa de model_id")
        self.path = str(self.path)
        self.sha256 = str(self.sha256).lower()
        self.schema = str(self.schema)
        self.pipeline_version = str(self.pipeline_version)
        self.config_hash = str(self.config_hash)
        self.domains = tuple(str(item) for item in self.domains)
        self.metadata = dict(self.metadata or {})

    @classmethod
    def from_file(cls, path: str | Path, *, model_id: str,
                  schema: str = WEIGHT_SCHEMA, pipeline_version: str = "",
                  config: Mapping[str, Any] | None = None,
                  domains: Iterable[str] = ()) -> "WeightManifest":
        if not Path(path).is_file():
            raise FileNotFoundError(path)
        return cls(str(model_id), str(path), sha256_file(path), schema,
                   str(pipeline_version),
                   hashlib.sha256(_canonical(config)).hexdigest() if config is not None else "",
                   tuple(sorted(set(str(item) for item in domains))))

    def verify(self, path: str | Path | None = None) -> bool:
        target = Path(path or self.path)
        return target.is_file() and sha256_file(target) == self.sha256

    def validate(self, path: str | Path | None = None, **kwargs: Any) -> WeightCompatibility:
        return verify_weight_compatibility(self, path, **kwargs)

    def compatibility(self, *, schema: str | None = None,
                      pipeline_version: str | None = None,
                      config: Mapping[str, Any] | None = None) -> WeightCompatibility:
        errors: list[str] = []
        if schema is not None and schema != self.schema:
            errors.append(f"schema incompatível: esperado {schema}, manifesto {self.schema}")
        if pipeline_version is not None and pipeline_version != self.pipeline_version:
            errors.append("pipeline_version incompatível")
        if config is not None:
            config_hash = hashlib.sha256(_canonical(config)).hexdigest()
            if config_hash != self.config_hash:
                errors.append("configuração incompatível")
        return WeightCompatibility(not errors, tuple(errors))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"domains": list(self.domains)}

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: str | Path) -> "WeightManifest":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        stored_path = Path(str(data["path"]))
        if not stored_path.is_absolute():
            stored_path = Path(path).parent / stored_path
        return cls(model_id=str(data["model_id"]), path=str(stored_path),
                   sha256=str(data["sha256"]), schema=str(data.get("schema", WEIGHT_SCHEMA)),
                   pipeline_version=str(data.get("pipeline_version", "")),
                   config_hash=str(data.get("config_hash", "")),
                   domains=tuple(data.get("domains", ())),
                   created_at=str(data.get("created_at", "")),
                   metadata=dict(data.get("metadata", {})))


def build_weight_manifest(path: str | Path, **kwargs: Any) -> WeightManifest:
    return WeightManifest.from_file(path, **kwargs)


def verify_weight_compatibility(manifest: WeightManifest, path: str | Path | None = None,
                                **kwargs: Any) -> WeightCompatibility:
    errors = [] if manifest.verify(path) else ["checksum dos pesos não corresponde"]
    result = manifest.compatibility(**kwargs)
    return WeightCompatibility(not errors and result.compatible,
                               tuple(errors) + result.errors)
