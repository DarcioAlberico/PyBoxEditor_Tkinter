"""Suspeitas, revisão auditável e exportação para active learning."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Sequence

from core.ocr_language import LanguageModel, normalizar_palavra
from core.ocr_result import WordResult


@dataclass(frozen=True)
class ReviewConfig:
    confidence_threshold: float = 0.60
    unknown_words: bool = True
    disagreement: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError("confidence_threshold deve estar entre 0 e 1")


@dataclass
class Suspect:
    id: str
    text: str
    reason: str
    severity: float
    confidence: float
    bbox: tuple[int, int, int, int]
    alternatives: list[str] = field(default_factory=list)
    original_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def detectar_suspeitas(words: Sequence[WordResult],
                       modelo: LanguageModel | None = None,
                       config: ReviewConfig | None = None) -> list[Suspect]:
    config = config or ReviewConfig()
    resultado = []
    for word in words:
        motivos = []
        texto = word.text
        if word.confidence < config.confidence_threshold:
            motivos.append("low_confidence")
        if config.disagreement and word.alternatives:
            motivos.append("engine_disagreement")
        nucleo = normalizar_palavra(texto)
        if (config.unknown_words and modelo is not None and nucleo.isalpha()
                and not modelo.conhece(nucleo)):
            motivos.append("unknown_word")
        motivos.extend(item for item in word.warnings if item not in motivos)
        if not motivos:
            continue
        severidade = min(1.0, (1.0 - word.confidence)
                         + (0.25 if "unknown_word" in motivos else 0.0)
                         + (0.15 if "engine_disagreement" in motivos else 0.0))
        resultado.append(Suspect(
            id=word.id, text=texto, reason="+".join(motivos),
            severity=severidade, confidence=word.confidence,
            bbox=word.bbox,
            alternatives=[getattr(item, "text", str(item)) for item in word.alternatives],
            original_text=word.original_text,
        ))
    return sorted(resultado, key=lambda item: (-item.severity, item.id))


@dataclass
class CorrectionEvent:
    suspect_id: str
    before: str
    after: str
    source: str = "manual"
    metadata: dict[str, Any] = field(default_factory=dict)


class ReviewStore:
    """Armazena correções e exemplos confirmados em JSON."""

    def __init__(self, caminho: str | Path | None = None):
        self.caminho = Path(caminho) if caminho is not None else None
        self.events: list[CorrectionEvent] = []
        if self.caminho and self.caminho.exists():
            dados = json.loads(self.caminho.read_text(encoding="utf-8"))
            self.events = [CorrectionEvent(**item) for item in dados]

    def add(self, event: CorrectionEvent) -> None:
        self.events.append(event)
        self.save()

    def undo(self) -> CorrectionEvent | None:
        """Remove e devolve a última correção, persistindo o novo histórico.

        A alteração do ``WordResult`` continua sendo responsabilidade da camada
        de UI/controlador; este store só administra a trilha auditável. Retornar
        o evento removido permite ao chamador restaurar ``before`` sem perder
        os metadados da operação desfeita.
        """
        if not self.events:
            return None
        evento = self.events.pop()
        self.save()
        return evento

    def save(self) -> None:
        if self.caminho is None:
            return
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = self.caminho.with_suffix(self.caminho.suffix + ".tmp")
        temporario.write_text(json.dumps([asdict(item) for item in self.events],
                                         ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
        temporario.replace(self.caminho)

    def apply(self, word: WordResult, texto: str) -> WordResult:
        texto = str(texto)
        if not texto.strip():
            raise ValueError("correção não pode ser vazia")
        self.add(CorrectionEvent(word.id, word.text, texto,
                                 metadata={"bbox": list(word.bbox)}))
        return replace(word, text=texto, original_text=word.original_text or word.text,
                       confidence=1.0, source="manual", warnings=[])

    def export_active_learning(self, caminho: str | Path) -> int:
        destino = Path(caminho)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("w", encoding="utf-8") as arquivo:
            for item in self.events:
                arquivo.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
        return len(self.events)
