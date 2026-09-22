"""Fachada de produção da Fase 2 do OCR editorial.

O módulo concentra a complexidade de ingestão, evidência, layout, roteamento,
cancelamento e adaptação para o IR editorial. Os callers conhecem somente
``DocumentSource``, ``ProcessOptions`` e ``EditorialPipeline``; engines e
formatos de origem ficam atrás desse seam.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import fitz
import cv2
import numpy as np

from core.editorial_adapters import (
    pagina_extraida_para_pagina,
    page_result_para_pagina,
)
from core.editorial_model import EditorialDocument, EditorialPage, ReviewEvent
from core.ocr_layout import LayoutAnalyzer
from core.ocr_result import (
    LineResult,
    PageResult,
    RegionResult,
    WordResult,
)
from core.ocr_routing import OCRRouter
from core.ocr_runtime import (
    BatchProcessor,
    CancellationToken,
    Profiler,
    RuntimeConfig,
)
from core.preprocess import PreprocessConfig, preparar_adaptativo


# Fases 3 e 4 mudam a semântica da página: notação passa pelo fusionador e
# diagramas passam a ser regiões de xadrez com FEN e estado de revisão. O salto
# de versão invalida caches das fases anteriores.
PIPELINE_VERSION = "editorial-pipeline/v4"
SUPPORTED_SOURCE_KINDS = frozenset({"auto", "pdf", "image", "memory"})
SUPPORTED_EXPORTS = frozenset({"json", "html", "txt", "epub", "docx", "pdf"})


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _array_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        return (str(array.dtype).encode() + repr(array.shape).encode()
                + array.tobytes())
    return repr(value).encode("utf-8")


def _raster(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    if isinstance(value, np.ndarray):
        if value.size == 0:
            return None
        return value
    if isinstance(value, bytes):
        try:
            from PIL import Image
            from io import BytesIO
            return np.asarray(Image.open(BytesIO(value)).convert("RGB"))
        except (ImportError, OSError, ValueError) as error:
            raise ValueError("raster em bytes não é uma imagem válida") from error
    raise TypeError("raster deve ser ndarray, bytes ou None")


@dataclass(frozen=True)
class SourcePage:
    """Página fornecida por um adapter de memória ou teste."""

    page_index: int
    raster: Any = field(default=None, repr=False, compare=False)
    text_layer: str = ""
    text_blocks: tuple[Mapping[str, Any], ...] = ()
    dpi: int = 300
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if int(self.page_index) < 0:
            raise ValueError("page_index não pode ser negativo")
        if int(self.dpi) <= 0:
            raise ValueError("dpi deve ser positivo")
        object.__setattr__(self, "page_index", int(self.page_index))
        object.__setattr__(self, "text_layer", str(self.text_layer or ""))
        object.__setattr__(self, "text_blocks", tuple(dict(item) for item in self.text_blocks))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        _raster(self.raster)


@dataclass(frozen=True)
class DocumentSource:
    """Origem somente leitura: PDF, imagem ou páginas já materializadas."""

    source_id: str
    path: Path | None = None
    kind: str = "auto"
    pages: tuple[SourcePage, ...] = ()
    title: str = ""
    language: str = "und"
    page_indices: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        source_id = str(self.source_id).strip()
        if not source_id:
            raise ValueError("source_id não pode ser vazio")
        kind = str(self.kind).casefold()
        if kind not in SUPPORTED_SOURCE_KINDS:
            raise ValueError(f"tipo de origem inválido: {self.kind!r}")
        caminho = Path(self.path) if self.path is not None else None
        paginas = tuple(self.pages)
        page_ids = [int(page.page_index) for page in paginas]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("DocumentSource não pode repetir page_index")
        indices = None if self.page_indices is None else tuple(int(i) for i in self.page_indices)
        if any(i < 0 for i in indices or ()):
            raise ValueError("page_indices não pode conter valores negativos")
        if caminho is None and not paginas:
            raise ValueError("DocumentSource exige path ou pages")
        if caminho is not None and paginas:
            raise ValueError("DocumentSource não mistura path e pages")
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "path", caminho)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "pages", paginas)
        object.__setattr__(self, "title", str(self.title or ""))
        object.__setattr__(self, "language", str(self.language or "und"))
        object.__setattr__(self, "page_indices", indices)

    @classmethod
    def from_path(cls, path: str | Path, *, source_id: str | None = None,
                  kind: str = "auto", title: str = "", language: str = "und",
                  page_indices: Sequence[int] | None = None) -> "DocumentSource":
        caminho = Path(path)
        return cls(source_id or caminho.stem or "document", caminho, kind, (),
                   title, language,
                   None if page_indices is None else tuple(page_indices))

    @classmethod
    def from_pages(cls, pages: Sequence[SourcePage], *, source_id: str,
                   title: str = "", language: str = "und") -> "DocumentSource":
        return cls(source_id, None, "memory", tuple(pages), title, language)

    @property
    def sha256(self) -> str:
        if self.path is not None:
            return _sha256_bytes(self.path.read_bytes())
        digest = hashlib.sha256()
        for page in self.pages:
            digest.update(str(page.page_index).encode())
            digest.update(_array_bytes(page.raster))
            digest.update(page.text_layer.encode("utf-8"))
            digest.update(json.dumps(list(page.text_blocks), sort_keys=True,
                                     ensure_ascii=False, default=str).encode("utf-8"))
        return digest.hexdigest()

    def _indices(self, total: int) -> list[int]:
        indices = list(range(total)) if self.page_indices is None else list(self.page_indices)
        if any(index >= total for index in indices):
            raise IndexError("page_indices contém página fora da origem")
        return indices

    def evidences(self, options: "ProcessOptions") -> list["PageEvidence"]:
        if self.pages:
            paginas = {page.page_index: page for page in self.pages}
            indices = (sorted(paginas) if self.page_indices is None
                       else list(self.page_indices))
            ausentes = [index for index in indices if index not in paginas]
            if ausentes:
                raise IndexError(f"páginas ausentes na origem: {ausentes}")
            return [self._evidence_from_memory(paginas[index], options)
                    for index in indices]
        if self.path is None:
            raise ValueError("origem sem arquivo ou páginas")
        if not self.path.exists():
            raise FileNotFoundError(str(self.path))
        kind = self.kind
        if kind == "auto":
            kind = "pdf" if self.path.suffix.casefold() == ".pdf" else "image"
        if kind == "pdf":
            return self._evidences_pdf(options)
        if kind == "image":
            return self._evidences_image(options)
        raise ValueError(f"tipo de origem não pode ser lido: {kind!r}")

    def _evidence_from_memory(self, page: SourcePage,
                              options: "ProcessOptions") -> "PageEvidence":
        raster = _raster(page.raster)
        raster_hash = (_sha256_bytes(_array_bytes(raster)) if raster is not None
                       else _sha256_bytes(page.text_layer.encode("utf-8")))
        return PageEvidence(
            document_id=self.source_id, page_index=page.page_index,
            source_kind="memory", raster=raster, raster_hash=raster_hash,
            raster_dpi=int(page.dpi or options.dpi), text_layer=page.text_layer,
            text_blocks=page.text_blocks,
            metadata={**dict(page.metadata), "source_sha256": self.sha256},
        )

    def _evidences_pdf(self, options: "ProcessOptions") -> list["PageEvidence"]:
        evidencias = []
        with fitz.open(self.path) as documento:
            for index in self._indices(len(documento)):
                page = documento[index]
                texto = page.get_text("text") or ""
                bruto = page.get_text("dict") or {}
                pixmap = page.get_pixmap(dpi=options.dpi, alpha=False)
                canais = pixmap.n
                raster = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                    pixmap.height, pixmap.width, canais)
                if canais == 4:
                    raster = raster[:, :, :3]
                blocos = tuple(_scale_pdf_block(block, options.dpi)
                               for block in bruto.get("blocks", [])
                               if isinstance(block, Mapping))
                raster_hash = _sha256_bytes(_array_bytes(raster))
                evidencias.append(PageEvidence(
                    document_id=self.source_id, page_index=index,
                    source_kind="pdf_text" if texto.strip() else "pdf_raster",
                    raster=raster, raster_hash=raster_hash,
                    raster_dpi=options.dpi, text_layer=texto,
                    text_blocks=blocos,
                    metadata={"pdf_page_rect": list(page.rect),
                              "pdf_rotation": page.rotation,
                              "drawings": len(page.get_drawings()),
                              "source_sha256": self.sha256},
                ))
        return evidencias

    def _evidences_image(self, options: "ProcessOptions") -> list["PageEvidence"]:
        from PIL import Image
        raster = np.asarray(Image.open(self.path).convert("RGB"))
        return [PageEvidence(
            document_id=self.source_id, page_index=0, source_kind="image",
            raster=raster, raster_hash=_sha256_bytes(_array_bytes(raster)),
            raster_dpi=options.dpi,
            metadata={"path": str(self.path), "source_sha256": self.sha256},
        )]


@dataclass(frozen=True)
class PageEvidence:
    """Evidência imutável que chega ao processamento de uma página."""

    document_id: str
    page_index: int
    source_kind: str
    raster: Any = field(default=None, repr=False, compare=False)
    raster_hash: str = ""
    raster_dpi: int = 300
    text_layer: str = ""
    text_blocks: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if int(self.page_index) < 0:
            raise ValueError("page_index não pode ser negativo")
        if int(self.raster_dpi) <= 0:
            raise ValueError("raster_dpi deve ser positivo")
        _raster(self.raster)
        object.__setattr__(self, "document_id", str(self.document_id))
        object.__setattr__(self, "page_index", int(self.page_index))
        object.__setattr__(self, "source_kind", str(self.source_kind))
        object.__setattr__(self, "raster_hash", str(self.raster_hash or ""))
        object.__setattr__(self, "raster_dpi", int(self.raster_dpi))
        object.__setattr__(self, "text_layer", str(self.text_layer or ""))
        object.__setattr__(self, "text_blocks", tuple(dict(item) for item in self.text_blocks))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    @property
    def width(self) -> int:
        return int(self.raster.shape[1]) if self.raster is not None else 1

    @property
    def height(self) -> int:
        return int(self.raster.shape[0]) if self.raster is not None else 1

    @property
    def cache_key(self) -> str:
        return f"{self.document_id}:{self.page_index}:{self.raster_hash}:{_sha256_bytes(self.text_layer.encode())}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id, "page_index": self.page_index,
            "source_kind": self.source_kind, "raster_hash": self.raster_hash,
            "raster_dpi": self.raster_dpi, "text_layer": self.text_layer,
            "text_blocks": [dict(item) for item in self.text_blocks],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ProcessOptions:
    dpi: int = 300
    language: str = "en"
    engine: str = "auto"
    page_indices: tuple[int, ...] | None = None
    workers: int = 1
    cache_dir: str | Path | None = None
    use_cache: bool = True
    preprocess_method: str = "auto"
    model_manifest: str = ""
    max_memory_mb: int | None = None
    per_worker_memory_mb: int | None = None

    def __post_init__(self) -> None:
        if self.dpi <= 0 or self.workers <= 0:
            raise ValueError("dpi e workers devem ser positivos")
        if self.max_memory_mb is not None and self.max_memory_mb < 1:
            raise ValueError("max_memory_mb deve ser positivo")
        if self.per_worker_memory_mb is not None and self.per_worker_memory_mb < 1:
            raise ValueError("per_worker_memory_mb deve ser positivo")
        if self.engine not in {"auto", "native", "tesseract", "none"}:
            raise ValueError("engine deve ser auto, native, tesseract ou none")
        if self.page_indices is not None and any(int(i) < 0 for i in self.page_indices):
            raise ValueError("page_indices não pode conter valores negativos")
        object.__setattr__(self, "page_indices", None if self.page_indices is None
                           else tuple(int(i) for i in self.page_indices))
        if self.preprocess_method not in {"auto", "otsu", "adaptive", "fixed"}:
            raise ValueError("preprocess_method inválido")

    def cache_key(self, pipeline_version: str) -> dict[str, Any]:
        model_identity: Any = self.model_manifest
        if self.model_manifest and Path(self.model_manifest).is_file():
            from core.ocr_runtime import modelo_assinatura
            model_identity = modelo_assinatura(self.model_manifest)
        return {"pipeline_version": pipeline_version, "dpi": self.dpi,
                "language": self.language, "engine": self.engine,
                "preprocess_method": self.preprocess_method,
                "model_manifest": model_identity,
                "code_version": pipeline_version,
                "schema_version": "pyboxeditor.editorial-document/v1"}


@dataclass(frozen=True)
class ExportOptions:
    format: str = "json"
    include_diagnostics: bool = True
    mode: str = "clean"

    def __post_init__(self) -> None:
        formato = str(self.format).casefold().lstrip(".")
        if formato not in SUPPORTED_EXPORTS:
            raise ValueError(f"formato editorial não suportado na Fase 2: {formato!r}")
        modo = str(self.mode).casefold()
        if modo not in {"faithful", "clean", "hybrid"}:
            raise ValueError(f"modo editorial não suportado: {modo!r}")
        object.__setattr__(self, "format", formato)
        object.__setattr__(self, "mode", modo)


@dataclass(frozen=True)
class ExportReport:
    format: str
    files: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PageInspection:
    page_index: int
    source_kind: str
    text_characters: int
    raster_hash: str
    dpi: int
    layout: Mapping[str, Any]
    routing: tuple[Mapping[str, Any], ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class InspectionReport:
    source_id: str
    source_sha256: str
    pages: tuple[PageInspection, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id, "source_sha256": self.source_sha256,
            "pages": [{"page_index": page.page_index,
                        "source_kind": page.source_kind,
                        "text_characters": page.text_characters,
                        "raster_hash": page.raster_hash, "dpi": page.dpi,
                        "layout": dict(page.layout),
                        "routing": [dict(item) for item in page.routing],
                        "warnings": list(page.warnings)} for page in self.pages],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class _PageWork:
    evidence: PageEvidence

    def __repr__(self) -> str:
        return self.evidence.cache_key


def _scale_pdf_block(block: Mapping[str, Any], dpi: int) -> dict[str, Any]:
    escala = dpi / 72.0
    resultado = dict(block)
    bbox = block.get("bbox")
    if bbox and len(bbox) == 4:
        resultado["bbox"] = [round(float(value) * escala, 2) for value in bbox]
    linhas = []
    for line in block.get("lines", []) or []:
        linha = dict(line)
        if line.get("bbox"):
            linha["bbox"] = [round(float(value) * escala, 2)
                              for value in line["bbox"]]
        spans = []
        for span in line.get("spans", []) or []:
            item = dict(span)
            if span.get("bbox"):
                item["bbox"] = [round(float(value) * escala, 2)
                                 for value in span["bbox"]]
            spans.append(item)
        linha["spans"] = spans
        linhas.append(linha)
    resultado["lines"] = linhas
    return resultado


def _bbox(value: Sequence[float] | None, width: int = 1, height: int = 1) -> tuple[int, int, int, int]:
    if value is None or len(value) != 4:
        return (0, 0, max(1, width), max(1, height))
    x1, y1, x2, y2 = (int(round(float(item))) for item in value)
    return (min(x1, x2), min(y1, y2), max(x1 + 1, x2), max(y1 + 1, y2))


def _classification(text: str, *, y1: int, y2: int, height: int,
                   font_size: float = 0.0, median_font: float = 0.0,
                   metadata: Mapping[str, Any] | None = None) -> str:
    metadata = metadata or {}
    if metadata.get("diagram") or metadata.get("image"):
        return "diagram"
    if metadata.get("table") or "\t" in text:
        return "table"
    normalizado = text.strip()
    notation = bool(re.search(r"(?:\d+\s*[.…)…]|[KQRBN][a-h][1-8]|[♔♕♖♗♘♙])", normalizado))
    if notation:
        return "notation"
    if y1 <= height * 0.10 and len(normalizado) <= 90:
        return "header"
    if y2 >= height * 0.90 and len(normalizado) <= 90:
        return "footer"
    if font_size and median_font and font_size >= median_font * 1.30:
        return "heading"
    return "body"


def _text_specs(evidence: PageEvidence) -> list[dict[str, Any]]:
    blocos = [block for block in evidence.text_blocks if block.get("type", 0) == 0]
    if not blocos and evidence.text_layer.strip():
        linhas = evidence.text_layer.splitlines()
        altura = max(16, evidence.height // max(1, len(linhas)))
        blocos = [{"bbox": [0, i * altura, evidence.width, (i + 1) * altura],
                   "lines": [{"bbox": [0, i * altura, evidence.width, (i + 1) * altura],
                              "spans": [{"text": linha, "size": 10.0}]}]}
                  for i, linha in enumerate(linhas) if linha.strip()]
    tamanhos = [float(span.get("size", 0.0))
                for block in blocos for line in block.get("lines", [])
                for span in line.get("spans", []) if span.get("size")]
    mediana = float(np.median(tamanhos)) if tamanhos else 0.0
    specs = []
    for index, block in enumerate(blocos):
        linhas = block.get("lines", []) or []
        textos = []
        for line in linhas:
            texto = "".join(str(span.get("text", "")) for span in line.get("spans", [])).strip()
            if texto:
                textos.append((texto, _bbox(line.get("bbox"), evidence.width, evidence.height),
                               max((float(span.get("size", 0.0)) for span in line.get("spans", [])),
                                   default=0.0)))
        if not textos:
            continue
        caixa = _bbox(block.get("bbox"), evidence.width, evidence.height)
        texto = "\n".join(item[0] for item in textos)
        tipo = _classification(texto, y1=caixa[1], y2=caixa[3], height=evidence.height,
                                font_size=max(item[2] for item in textos),
                                median_font=mediana, metadata=block)
        specs.append({"id": f"region-{evidence.page_index:04d}-{index:04d}",
                      "order": index, "type": tipo, "bbox": caixa, "text": texto,
                      "lines": textos, "metadata": {
                          "spanning": caixa[0] <= evidence.width * .05
                          and caixa[2] >= evidence.width * .95,
                          "source_block": index,
                      }})
    return specs


def _layout(evidence: PageEvidence, specs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    colunas: list[tuple[int, int]] = []
    if specs:
        centros = sorted((int((item["bbox"][0] + item["bbox"][2]) / 2) for item in specs))
        if centros and max(centros) - min(centros) > evidence.width * .30:
            corte = int((min(centros) + max(centros)) / 2)
            colunas = [(0, corte), (corte, evidence.width)]
        else:
            colunas = [(0, evidence.width)]
    else:
        colunas = [(0, evidence.width)]
    ordem = [str(item["id"]) for item in specs]
    grafo = {item: ([ordem[i + 1]] if i + 1 < len(ordem) else [])
             for i, item in enumerate(ordem)}
    return {"width": evidence.width, "height": evidence.height,
            "regions": [dict(item) for item in specs],
            "columns": [list(item) for item in colunas],
            "reading_order": ordem, "reading_graph": grafo,
            "spanning_regions": [item["id"] for item in specs
                                 if item["metadata"].get("spanning")],
            "special_regions": [item["id"] for item in specs
                                if item["type"] in {"table", "diagram"}],
            "warnings": []}


def _raster_specs(evidence: PageEvidence, options: ProcessOptions) -> list[dict[str, Any]]:
    """Cria regiões geométricas para scan mesmo antes do OCR.

    A segmentação é uma observação, nunca texto inventado. Isso permite ao
    inspector persistir colunas/regiões e ao reconhecimento posterior trocar o
    engine sem recalcular a evidência original.
    """
    if evidence.raster is None:
        return []
    try:
        variant = preparar_adaptativo(
            evidence.raster,
            PreprocessConfig(target_dpi=options.dpi,
                             source_dpi=evidence.raster_dpi,
                             methods=(options.preprocess_method,)),
        )
        layout = LayoutAnalyzer().analyze(variant.binary)
    except (TypeError, ValueError, cv2.error) as error:
        return [{"id": f"region-{evidence.page_index:04d}-0000",
                 "order": 0, "type": "unknown",
                 "bbox": (0, 0, evidence.width, evidence.height), "text": "",
                 "lines": [], "metadata": {"layout_error": str(error)}}]
    return [{"id": region.id, "order": region.order, "type": region.type,
             "bbox": region.bbox, "text": "", "lines": [],
             "metadata": {**region.metadata, "layout_only": True}}
            for region in layout.regions]


def _words_for_line(text: str, caixa: tuple[int, int, int, int], line_id: str,
                    confidence: float, prefix: str) -> list[WordResult]:
    tokens = list(re.finditer(r"\S+", text))
    if not tokens:
        return []
    x1, y1, x2, y2 = caixa
    largura = max(1, x2 - x1)
    resultado = []
    for index, token in enumerate(tokens):
        inicio = x1 + int(largura * token.start() / max(1, len(text)))
        fim = x1 + int(largura * token.end() / max(1, len(text)))
        resultado.append(WordResult(
            id=f"{prefix}-w{index:03d}", text=token.group(), confidence=confidence,
            bbox=(inicio, y1, max(inicio + 1, fim), y2), line_id=line_id,
            source="text_layer",
        ))
    return resultado


def _page_from_text(evidence: PageEvidence, specs: Sequence[Mapping[str, Any]],
                    *, pipeline_version: str) -> PageResult:
    linhas: list[LineResult] = []
    palavras: list[WordResult] = []
    regioes: list[RegionResult] = []
    for spec in specs:
        line_ids = []
        for line_index, (text, caixa, _size) in enumerate(spec["lines"]):
            line_id = f"{spec['id']}-line-{line_index:03d}"
            items = _words_for_line(text, caixa, line_id, .98, line_id)
            line_ids.append(line_id)
            linhas.append(LineResult(line_id, text, .98, bbox=caixa,
                                     region_id=spec["id"],
                                     word_ids=[item.id for item in items],
                                     metadata={"source": "pdf_text"}))
            palavras.extend(items)
        regioes.append(RegionResult(
            id=str(spec["id"]), type=str(spec["type"]), order=int(spec["order"]),
            confidence=.98, bbox=spec["bbox"], line_ids=line_ids,
            text=str(spec["text"]), metadata=dict(spec["metadata"]),
        ))
    return PageResult(
        page_id=f"page-{evidence.page_index:04d}",
        text="\n\n".join(str(spec["text"]) for spec in specs), confidence=.98,
        regions=regioes, lines=linhas, words=palavras,
        metadata={"engine": "pdf_text", "pipeline_version": pipeline_version},
    )


class EditorialPipeline:
    """Fachada única para inspeção, processamento, revisão e exportação base."""

    def __init__(self, *, page_processor: Callable[[PageEvidence, ProcessOptions,
                                                      CancellationToken], PageResult] | None = None,
                 recognizer: Any | None = None,
                 legacy_extractor: Callable[..., Sequence[Any]] | None = None,
                 pipeline_version: str = PIPELINE_VERSION,
                 profiler: Profiler | None = None):
        if sum(item is not None for item in
               (page_processor, recognizer, legacy_extractor)) > 1:
            raise ValueError("use somente um processor, recognizer ou legacy_extractor")
        self.page_processor = page_processor
        self.recognizer = recognizer
        self.legacy_extractor = legacy_extractor
        self.pipeline_version = str(pipeline_version)
        self.router = OCRRouter()
        self.layout_analyzer = LayoutAnalyzer()
        self.profiler = profiler or Profiler(enabled=False)

    def inspect(self, source: DocumentSource,
                options: ProcessOptions | None = None) -> InspectionReport:
        options = options or ProcessOptions()
        if options.page_indices is not None:
            source = DocumentSource(source.source_id, source.path, source.kind, source.pages,
                                    source.title, source.language, options.page_indices)
        evidencias = source.evidences(options)
        paginas = []
        warnings = []
        for evidence in evidencias:
            specs = _text_specs(evidence)
            if not specs:
                specs = _raster_specs(evidence, options)
            layout = _layout(evidence, specs)
            regions = [RegionResult(item["id"], item["type"], item["order"], .75,
                                    item["bbox"], text=item["text"],
                                    metadata=item["metadata"])
                       for item in specs]
            routing = tuple(self.router.decide(region).to_dict() for region in regions)
            paginas.append(PageInspection(
                page_index=evidence.page_index, source_kind=evidence.source_kind,
                text_characters=len(evidence.text_layer), raster_hash=evidence.raster_hash,
                dpi=evidence.raster_dpi, layout=layout, routing=routing,
                warnings=tuple(layout.get("warnings", [])),
            ))
        return InspectionReport(source.source_id, source.sha256, tuple(paginas), tuple(warnings))

    def process(self, source: DocumentSource, options: ProcessOptions | None = None,
                cancellation: CancellationToken | None = None) -> EditorialDocument:
        options = options or ProcessOptions()
        token = cancellation or CancellationToken()
        if options.page_indices is not None:
            source = DocumentSource(source.source_id, source.path, source.kind, source.pages,
                                    source.title, source.language, options.page_indices)
        if self.legacy_extractor is not None:
            return self._process_legacy(source, options, token)
        evidencias = source.evidences(options)

        def process_one(work: _PageWork, page_token: CancellationToken) -> PageResult:
            return self._process_page(work.evidence, options, page_token)

        runtime = RuntimeConfig(
            cache_dir=options.cache_dir, workers=options.workers,
            use_cache=options.use_cache, max_memory_mb=options.max_memory_mb,
            engine=options.engine, per_worker_memory_mb=options.per_worker_memory_mb,
            code_version=self.pipeline_version,
            schema_version="pyboxeditor.editorial-document/v1",
            model_version=options.model_manifest,
        )
        batch = BatchProcessor(process_one, config=runtime, profiler=self.profiler)
        resultado = batch.process(
            [_PageWork(evidence) for evidence in evidencias], token=token,
            config_key=options.cache_key(self.pipeline_version),
        )
        por_id = {int(page.metadata.get("page_index", -1)): page
                  for page in resultado.results}
        paginas: list[EditorialPage] = []
        for evidence in evidencias:
            page = por_id.get(evidence.page_index)
            if page is None:
                mensagem = resultado.errors.get(str(evidencias.index(evidence)),
                                                "página não processada")
                page = PageResult(f"page-{evidence.page_index:04d}", warnings=[mensagem])
                self._enrich_page(page, evidence, options, error=mensagem)
            paginas.append(page_result_para_pagina(
                page, document_id=source.source_id, page_index=evidence.page_index))
        documento = EditorialDocument(
            document_id=source.source_id, title=source.title or source.source_id,
            language=source.language if source.language != "und" else options.language,
            pages=paginas, pipeline_version=self.pipeline_version,
            source_sha256=source.sha256, model_manifest=options.model_manifest,
            metadata={"phase": 4, "source_kind": source.kind,
                      "source_path": str(source.path) if source.path else "",
                      "errors": dict(resultado.errors),
                      "cancelled": resultado.cancelled,
                      "processed_pages": resultado.processed,
                      "effective_workers": runtime.effective_workers,
                      "cached_pages": resultado.cached,
                      "inspection": self.inspect(source, options).to_dict()},
        )
        documento.validate()
        return documento

    def apply(self, document: EditorialDocument, event: ReviewEvent) -> EditorialDocument:
        return document.apply_review(event)

    def export(self, document: EditorialDocument, target: str | Path | "ExportTarget",
               options: ExportOptions | None = None) -> ExportReport:
        options = options or ExportOptions()
        caminho = Path(target.path if isinstance(target, ExportTarget) else target)
        formato = (target.format if isinstance(target, ExportTarget) and target.format
                    else options.format).casefold().lstrip(".")
        if formato not in SUPPORTED_EXPORTS:
            raise ValueError(f"formato editorial não suportado: {formato!r}")
        caminho.parent.mkdir(parents=True, exist_ok=True)
        if formato in {"html", "epub", "docx", "pdf"}:
            from core.editorial_export import EditorialExporter, ExportOptions as EditorialExportOptions
            report = EditorialExporter().export(
                document, caminho,
                EditorialExportOptions(
                    format=formato, mode=options.mode,
                    include_diagnostics=options.include_diagnostics,
                    source_pdf=document.metadata.get("source_path") or None,
                ),
            )
            return ExportReport(report.format, report.files, report.warnings, report.metadata)
        if formato == "json":
            document.save_json(caminho)
        elif formato == "html":
            _write_atomic(caminho, _html_document(document, options))
        else:
            _write_atomic(caminho, _text_document(document, options))
        return ExportReport(formato, (str(caminho),), metadata={"schema": document.schema})

    def _process_page(self, evidence: PageEvidence, options: ProcessOptions,
                      token: CancellationToken) -> PageResult:
        token.raise_if_cancelled()
        if self.recognizer is not None:
            page = self.recognizer.process(evidence, options, token)
            if not isinstance(page, PageResult):
                raise TypeError("recognizer.process deve retornar PageResult")
        elif self.page_processor is not None:
            page = self.page_processor(evidence, options, token)
            if not isinstance(page, PageResult):
                raise TypeError("page_processor deve retornar PageResult")
        elif options.engine != "none" and (evidence.text_layer.strip()
                                            or evidence.raster is not None):
            # A fachada padrão atravessa Fases 3 e 4. Para tesseract, preserva
            # o leitor histórico como processador textual e acrescenta os
            # diagramas; para texto nativo/scan, usa o processador editorial.
            from core.ocr_phase4 import Phase4Processor
            text_processor = None
            if options.engine == "tesseract":
                def tesseract_page(page_evidence, page_options, page_token):
                    return self._process_raster(page_evidence, page_options, page_token)
                text_processor = tesseract_page
            page = Phase4Processor(text_processor=text_processor).process(
                evidence, options, token)
        else:
            page = self._process_raster(evidence, options, token)
        return self._enrich_page(page, evidence, options)

    def _process_raster(self, evidence: PageEvidence, options: ProcessOptions,
                        token: CancellationToken) -> PageResult:
        token.raise_if_cancelled()
        if options.engine == "none":
            return PageResult(f"page-{evidence.page_index:04d}",
                              warnings=["engine desabilitado; OCR não executado"])
        if evidence.raster is None:
            return PageResult(f"page-{evidence.page_index:04d}",
                              warnings=["raster ausente; OCR não executado"])
        try:
            from core.services.ocr_service import OCRService
            registros = OCRService().tesseract_pagina_detalhada_conf(
                evidence.raster, options.language)
        except Exception as error:  # noqa: BLE001 — este método existe para degradar com aviso
            return PageResult(f"page-{evidence.page_index:04d}",
                              warnings=[f"engine indisponível: {error}"])
        regions = []
        lines = []
        words = []
        for index, registro in enumerate(registros or []):
            texto, confianca, caixa, detalhes = registro
            line_id = f"page-{evidence.page_index:04d}-line-{index:03d}"
            region_id = f"page-{evidence.page_index:04d}-region-{index:03d}"
            tipo = _classification(texto, y1=caixa[1], y2=caixa[3],
                                   height=evidence.height)
            ids = []
            for word_index, (word, word_conf, word_box) in enumerate(detalhes or ()):
                word_id = f"{line_id}-word-{word_index:03d}"
                words.append(WordResult(word_id, word, word_conf, word_box, line_id,
                                        "tesseract"))
                ids.append(word_id)
            lines.append(LineResult(line_id, texto, confianca, bbox=caixa,
                                    region_id=region_id, word_ids=ids,
                                    metadata={"source": "tesseract"}))
            regions.append(RegionResult(region_id, tipo, index, confianca, caixa,
                                        line_ids=[line_id], text=texto,
                                        metadata={"source": "tesseract"}))
        return PageResult(
            page_id=f"page-{evidence.page_index:04d}",
            text="\n".join(line.text for line in lines),
            confidence=(sum(line.confidence for line in lines) / len(lines)
                        if lines else 0.0), regions=regions, lines=lines, words=words,
            warnings=[] if lines else ["engine não retornou texto"],
            metadata={"engine": "tesseract"},
        )

    def _enrich_page(self, page: PageResult, evidence: PageEvidence,
                     options: ProcessOptions, error: str = "") -> PageResult:
        specs = _text_specs(evidence)
        if not specs:
            specs = _raster_specs(evidence, options)
        layout = _layout(evidence, specs)
        routing = [self.router.decide(region).to_dict() for region in page.regions]
        page.metadata.update({
            "document_id": evidence.document_id, "page_index": evidence.page_index,
            "source_sha256": evidence.metadata.get("source_sha256", evidence.raster_hash),
            "image_hash": evidence.raster_hash,
            "source_kind": evidence.source_kind, "dpi": evidence.raster_dpi,
            "image_width": evidence.width, "image_height": evidence.height,
            "pipeline_version": self.pipeline_version,
            "source_ref": {"document_id": evidence.document_id,
                           "page_index": evidence.page_index,
                           "bbox": None, "image_hash": evidence.raster_hash,
                           "source_kind": evidence.source_kind},
            "layout": layout, "routing": routing,
            "text_layer": evidence.text_layer,
        })
        if error:
            page.warnings.append(error)
        return page

    def _process_legacy(self, source: DocumentSource, options: ProcessOptions,
                        token: CancellationToken) -> EditorialDocument:
        if source.path is None:
            raise ValueError("legacy_extractor exige source.path")
        token.raise_if_cancelled()
        paginas = self.legacy_extractor(source.path, options, token)
        paginas_editoriais = []
        for pagina in paginas:
            token.raise_if_cancelled()
            paginas_editoriais.append(pagina_extraida_para_pagina(
                pagina, document_id=source.source_id))
        documento = EditorialDocument(
            document_id=source.source_id, title=source.title or source.source_id,
            # `und` é "não informado", e cai no idioma das opções — como no
            # caminho por página; era aqui que o documento saía sem idioma.
            language=(source.language if source.language != "und"
                      else options.language),
            pages=paginas_editoriais,
            pipeline_version=self.pipeline_version, source_sha256=source.sha256,
            model_manifest=options.model_manifest,
            metadata={"phase": 2, "adapter": "legacy_extractor",
                      "source_kind": source.kind,
                      "source_path": str(source.path),
                      "language": options.language,
                      "engine": "livro.extrair"},
        )
        documento.validate()
        return documento


@dataclass(frozen=True)
class ExportTarget:
    path: str | Path
    format: str | None = None


def _write_atomic(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _text_document(document: EditorialDocument, options: ExportOptions) -> str:
    paginas = []
    for page in document.pages:
        blocos = []
        for block in sorted(page.blocks, key=lambda item: item.order):
            value = block.decision.value
            blocos.append(value if isinstance(value, str) else json.dumps(
                value, ensure_ascii=False, sort_keys=True))
        paginas.append("\n\n".join(blocos))
    return "\n\n".join(paginas) + "\n"


def _html_document(document: EditorialDocument, options: ExportOptions) -> str:
    corpo = []
    for page in document.pages:
        corpo.append(f'<section id="page-{page.page_index + 1}" data-page="{page.page_index}">')
        for block in sorted(page.blocks, key=lambda item: item.order):
            value = block.decision.value
            texto = value if isinstance(value, str) else ""
            if block.kind == "heading":
                corpo.append(f"<h2 id=\"{html.escape(block.id)}\">{html.escape(texto)}</h2>")
            elif block.kind == "diagram" and isinstance(value, Mapping):
                fen = html.escape(str(value.get("fen", "")), quote=True)
                imagem = value.get("png_base64")
                if imagem:
                    corpo.append(f'<figure id="{html.escape(block.id)}" data-fen="{fen}">'
                                 f'<img src="data:image/png;base64,{html.escape(str(imagem))}" '
                                 f'alt="Diagrama de xadrez{": " + fen if fen else ""}"></figure>')
                else:
                    corpo.append(f'<figure id="{html.escape(block.id)}" data-fen="{fen}">'
                                 f'<figcaption>{fen}</figcaption></figure>')
            else:
                tag = "p" if block.kind not in {"table", "caption"} else "div"
                corpo.append(f'<{tag} id="{html.escape(block.id)}" '
                             f'data-kind="{html.escape(block.kind)}">{html.escape(texto)}</{tag}>')
        corpo.append("</section>")
    return ("<!doctype html>\n<html lang=\"" + html.escape(document.language) + "\">\n"
            "<head><meta charset=\"utf-8\"><title>" + html.escape(document.title)
            + "</title></head><body><main>" + "\n".join(corpo)
            + "</main></body></html>\n")
