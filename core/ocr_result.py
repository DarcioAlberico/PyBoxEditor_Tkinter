"""Contratos rastreáveis para o pipeline de OCR.

Os objetos deste módulo são independentes da UI e dos engines opcionais. Eles
permitem guardar, para cada resultado, texto, geometria, confiança, origem,
alternativas e a versão do processamento que tomou a decisão.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


def _bbox(valor: Sequence[int | float] | None) -> tuple[int, int, int, int] | None:
    if valor is None:
        return None
    if len(valor) != 4:
        raise ValueError("bounding box deve conter quatro coordenadas")
    return tuple(int(round(float(v))) for v in valor)  # type: ignore[return-value]


def _confiança(valor: float) -> float:
    valor = float(valor)
    if not 0.0 <= valor <= 1.0:
        raise ValueError("confiança deve estar entre 0 e 1")
    return valor


@dataclass
class OCRHypothesis:
    text: str
    confidence: float
    source: str
    bbox: tuple[int, int, int, int] | None = None
    alternatives: list[str] = field(default_factory=list)
    model_version: str = ""
    preprocessing: str = "original"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.text = str(self.text)
        self.source = str(self.source)
        self.confidence = _confiança(self.confidence)
        self.bbox = _bbox(self.bbox)


@dataclass
class GlyphResult:
    id: str
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]
    source: str
    line_id: str | None = None
    word_id: str | None = None
    alternatives: list[OCRHypothesis] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id)
        self.text = str(self.text)
        self.confidence = _confiança(self.confidence)
        caixa = _bbox(self.bbox)
        if caixa is None:
            raise ValueError("glifo precisa de bounding box")
        self.bbox = caixa
        self.source = str(self.source)


@dataclass
class WordResult:
    id: str
    text: str
    confidence: float
    bbox: tuple[int, int, int, int]
    line_id: str
    source: str
    glyph_ids: list[str] = field(default_factory=list)
    alternatives: list[OCRHypothesis] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    original_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id)
        self.text = str(self.text)
        self.confidence = _confiança(self.confidence)
        caixa = _bbox(self.bbox)
        if caixa is None:
            raise ValueError("palavra precisa de bounding box")
        self.bbox = caixa
        self.line_id = str(self.line_id)
        self.source = str(self.source)


@dataclass
class LineResult:
    id: str
    text: str
    confidence: float
    bbox: tuple[int, int, int, int] | None = None
    region_id: str | None = None
    word_ids: list[str] = field(default_factory=list)
    glyph_ids: list[str] = field(default_factory=list)
    alternatives: list[OCRHypothesis] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id)
        self.text = str(self.text)
        self.confidence = _confiança(self.confidence)
        self.bbox = _bbox(self.bbox)


@dataclass
class RegionResult:
    id: str
    type: str
    order: int
    confidence: float
    bbox: tuple[int, int, int, int]
    line_ids: list[str] = field(default_factory=list)
    text: str = ""
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id)
        self.type = str(self.type)
        self.confidence = _confiança(self.confidence)
        caixa = _bbox(self.bbox)
        if caixa is None:
            raise ValueError("região precisa de bounding box")
        self.bbox = caixa


@dataclass
class PageResult:
    page_id: str
    text: str = ""
    confidence: float = 0.0
    regions: list[RegionResult] = field(default_factory=list)
    lines: list[LineResult] = field(default_factory=list)
    words: list[WordResult] = field(default_factory=list)
    glyphs: list[GlyphResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.page_id = str(self.page_id)
        self.confidence = _confiança(self.confidence)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, dados: Mapping[str, Any]) -> "PageResult":
        def hypotheses(values: Any) -> list[OCRHypothesis]:
            """Reconstitui alternativas de linha/glifo de formatos antigos."""
            resultado: list[OCRHypothesis] = []
            for value in values or []:
                if isinstance(value, OCRHypothesis):
                    resultado.append(value)
                elif isinstance(value, Mapping):
                    resultado.append(OCRHypothesis(**value))
                else:
                    resultado.append(OCRHypothesis(str(value), 0.0, "alternative"))
            return resultado

        return cls(
            page_id=str(dados["page_id"]),
            text=str(dados.get("text", "")),
            confidence=float(dados.get("confidence", 0.0)),
            regions=[RegionResult(**item) for item in dados.get("regions", [])],
            lines=[LineResult(
                **{**item, "alternatives": hypotheses(item.get("alternatives", []))}
            ) for item in dados.get("lines", [])],
            words=[WordResult(
                **{**item, "alternatives": [OCRHypothesis(**h) for h in item.get("alternatives", [])]}
            ) for item in dados.get("words", [])],
            glyphs=[GlyphResult(
                **{**item, "alternatives": [OCRHypothesis(**h) for h in item.get("alternatives", [])]}
            ) for item in dados.get("glyphs", [])],
            warnings=list(dados.get("warnings", [])),
            metadata=dict(dados.get("metadata", {})),
        )

    def save_json(self, caminho: str | Path) -> None:
        destino = Path(caminho)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("w", encoding="utf-8") as arquivo:
            json.dump(self.to_dict(), arquivo, ensure_ascii=False, indent=2)
            arquivo.write("\n")

    @classmethod
    def load_json(cls, caminho: str | Path) -> "PageResult":
        with Path(caminho).open(encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        if not isinstance(dados, Mapping):
            raise ValueError("resultado OCR precisa ser um objeto JSON")
        return cls.from_dict(dados)


class OCRTrace:
    """Registro opcional de eventos e artefatos de uma execução."""

    def __init__(self, pasta: str | Path | None = None, *, enabled: bool = True):
        self.enabled = bool(enabled)
        self.pasta = Path(pasta) if pasta is not None else None
        self.events: list[dict[str, Any]] = []
        if self.enabled and self.pasta is not None:
            self.pasta.mkdir(parents=True, exist_ok=True)

    def event(self, event_name: str, **data: Any) -> None:
        if not self.enabled:
            return
        self.events.append({"name": str(event_name), **data})

    def save_bytes(self, name: str, data: bytes, *, kind: str = "binary") -> Path | None:
        if not self.enabled or self.pasta is None:
            return None
        destino = self.pasta / name
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(data)
        self.event("artifact", artifact_name=name, kind=kind, path=str(destino))
        return destino

    def save_text(self, name: str, data: str) -> Path | None:
        return self.save_bytes(name, data.encode("utf-8"), kind="text")

    def save_json(self, name: str, data: Mapping[str, Any]) -> Path | None:
        return self.save_text(name, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    def save_image(self, name: str, image: Any) -> Path | None:
        """Salva ndarray usando OpenCV somente quando o diagnóstico for usado."""
        if not self.enabled or self.pasta is None:
            return None
        try:
            import cv2
        except ImportError as erro:
            raise RuntimeError("salvar imagem exige opencv-python") from erro
        ok, buffer = cv2.imencode(Path(name).suffix or ".png", image)
        if not ok:
            raise ValueError(f"não foi possível codificar o artefato {name}")
        return self.save_bytes(name, buffer.tobytes(), kind="image")

    def close(self) -> Path | None:
        return self.save_json("trace.json", {"events": self.events})
