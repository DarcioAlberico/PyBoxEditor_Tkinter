"""Execução robusta, cache e profiling do pipeline OCR."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Sized
from typing import Any, Callable, Iterable, Sequence

import numpy as np

from core.ocr_result import PageResult
from core.services.task_service import Cancelled


class OCRCancelled(Cancelled):
    """Sinal interno de cancelamento cooperativo.

    Herda de `task_service.Cancelled` para que a tarefa em segundo plano da
    interface o entenda como **cancelamento**, e não como erro: antes, cancelar
    o processamento editorial terminava num "OCRCancelled: ..." em vermelho.
    """


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise OCRCancelled("processamento OCR cancelado")


@dataclass(frozen=True)
class RuntimeConfig:
    cache_dir: str | Path | None = None
    workers: int = 1
    use_cache: bool = True
    max_memory_mb: int | None = None
    engine: str = "auto"
    per_worker_memory_mb: int | None = None
    code_version: str = "runtime/v1"
    schema_version: str = "ocr-result/v1"
    model_version: str = ""

    def __post_init__(self) -> None:
        if self.workers < 1:
            raise ValueError("workers deve ser positivo")
        if self.max_memory_mb is not None and self.max_memory_mb < 1:
            raise ValueError("max_memory_mb deve ser positivo")
        if self.per_worker_memory_mb is not None and self.per_worker_memory_mb < 1:
            raise ValueError("per_worker_memory_mb deve ser positivo")

    @property
    def effective_workers(self) -> int:
        from core.ocr_phase8 import resolve_resource_budget
        return resolve_resource_budget(
            self.engine, workers=self.workers, memory_limit_mb=self.max_memory_mb,
            per_worker_mb=self.per_worker_memory_mb,
        ).effective_workers


def fingerprint(data: Any, *, config: Any = None) -> str:
    """Hash estável do conteúdo de entrada e configuração do pipeline."""
    digest = hashlib.sha256()
    if isinstance(data, np.ndarray):
        digest.update(str(data.shape).encode())
        digest.update(str(data.dtype).encode())
        digest.update(data.tobytes())
    elif isinstance(data, bytes):
        digest.update(data)
    else:
        digest.update(repr(data).encode("utf-8"))
    if config is not None:
        digest.update(json.dumps(config, ensure_ascii=False, sort_keys=True,
                                default=str).encode("utf-8"))
    return digest.hexdigest()


def modelo_assinatura(caminho: str | Path) -> dict[str, Any]:
    """Identidade barata e verificável de um peso usado pelo cache."""
    arquivo = Path(caminho)
    try:
        stat = arquivo.stat()
    except OSError:
        return {"path": str(arquivo), "missing": True}
    return {"path": str(arquivo), "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns, "sha256": _sha256_file(arquivo)}


def _sha256_file(caminho: Path) -> str:
    digest = hashlib.sha256()
    try:
        with caminho.open("rb") as arquivo:
            for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
                digest.update(bloco)
    except OSError:
        return ""
    return digest.hexdigest()


def configuracao_cache(*, engine: str, idioma: str = "en", dpi: int | None = None,
                       preprocessamento: str = "original",
                       variante: str = "", modelos: Sequence[str | Path] = (),
                       extra: Any = None, code_version: str = "runtime/v1",
                       schema_version: str = "ocr-result/v1",
                       model_version: str = "") -> dict[str, Any]:
    """Monta a configuração canônica de cache de um resultado OCR."""
    return {"engine": engine, "idioma": idioma, "dpi": dpi,
            "preprocessamento": preprocessamento, "variante": variante,
            "modelos": [modelo_assinatura(item) for item in modelos],
            "extra": extra, "code_version": code_version,
            "schema_version": schema_version, "model_version": model_version}


class OCRCache:
    """Cache JSON atômico para `PageResult`. Cada entrada é imutável por hash."""

    def __init__(self, pasta: str | Path | None):
        self.pasta = Path(pasta) if pasta is not None else None
        if self.pasta:
            self.pasta.mkdir(parents=True, exist_ok=True)

    def _path(self, chave: str) -> Path | None:
        return self.pasta / f"{chave}.json" if self.pasta else None

    def load(self, chave: str) -> PageResult | None:
        caminho = self._path(chave)
        if caminho is None or not caminho.exists():
            return None
        try:
            return PageResult.load_json(caminho)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            # Cache corrompido é miss, não falha do OCR.
            return None

    def save(self, chave: str, resultado: PageResult) -> Path | None:
        caminho = self._path(chave)
        if caminho is None:
            return None
        temporario = caminho.with_suffix(".tmp")
        resultado.save_json(temporario)
        temporario.replace(caminho)
        return caminho


@dataclass
class StageTiming:
    name: str
    seconds: float
    peak_memory_mb: float | None = None


class Profiler:
    def __init__(self, *, enabled: bool = True):
        self.enabled = enabled
        self.timings: list[StageTiming] = []

    def stage(self, name: str):
        return _Stage(self, name)

    def to_dict(self) -> dict[str, Any]:
        return {"stages": [timing.__dict__.copy() for timing in self.timings],
                "total_seconds": sum(item.seconds for item in self.timings)}


class _Stage:
    def __init__(self, profiler: Profiler, name: str):
        self.profiler = profiler
        self.name = name
        self.start = 0.0
        self.memory_started = False

    def __enter__(self):
        if self.profiler.enabled:
            self.start = time.perf_counter()
            tracemalloc.start()
            self.memory_started = True
        return self

    def __exit__(self, exc_type, exc, traceback):
        if not self.profiler.enabled:
            return False
        atual, pico = tracemalloc.get_traced_memory()
        if self.memory_started:
            tracemalloc.stop()
        self.profiler.timings.append(StageTiming(
            self.name, time.perf_counter() - self.start, pico / (1024 * 1024)))
        return False


@dataclass
class BatchResult:
    results: list[PageResult] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    cached: int = 0
    processed: int = 0
    cancelled: bool = False
    profiler: Profiler | None = None


class BatchProcessor:
    """Processa páginas com cache, progresso e cancelamento cooperativo."""

    def __init__(self, processor: Callable[[Any, CancellationToken], PageResult],
                 *, config: RuntimeConfig | None = None,
                 profiler: Profiler | None = None):
        self.processor = processor
        self.config = config or RuntimeConfig()
        self.cache = OCRCache(self.config.cache_dir)
        self.profiler = profiler or Profiler(enabled=False)

    def _one(self, item: Any, index: int, token: CancellationToken,
             config_key: Any) -> tuple[int, PageResult, bool]:
        token.raise_if_cancelled()
        chave = fingerprint(item, config=config_key)
        if self.config.use_cache:
            cached = self.cache.load(chave)
            if cached is not None:
                return index, cached, True
        with self.profiler.stage(f"page_{index}"):
            resultado = self.processor(item, token)
        if not isinstance(resultado, PageResult):
            raise TypeError("processor deve retornar PageResult")
        if self.config.use_cache:
            self.cache.save(chave, resultado)
        return index, resultado, False

    def process(self, items: Iterable[Any], *, token: CancellationToken | None = None,
                config_key: Any = None,
                progress: Callable[[int, int], None] | None = None) -> BatchResult:
        """Processa os itens, em fluxo quando há um trabalhador só.

        `items` pode ser um gerador desde 2026-09-22 (item 7 da revisão de
        2026-09-18): com `workers == 1` — o padrão — a página é lida, processada
        e esquecida antes de a próxima nascer, e a memória para de crescer com o
        tamanho do livro. Com mais de um trabalhador o `ThreadPoolExecutor`
        submete tudo de uma vez, e aí o gerador é consumido inteiro; é o preço
        do paralelismo, e não uma regressão deste laço.
        """
        token = token or CancellationToken()
        retorno = BatchResult(profiler=self.profiler)
        ordenados: dict[int, PageResult] = {}
        total = len(items) if isinstance(items, Sized) else 0

        def complete(indice: int, resultado: PageResult, foi_cache: bool) -> None:
            ordenados[indice] = resultado
            retorno.cached += int(foi_cache)
            retorno.processed += 1
            if progress:
                progress(retorno.processed, total or retorno.processed)

        workers = self.config.effective_workers
        if workers == 1:
            for indice, item in enumerate(items):
                try:
                    complete(*self._one(item, indice, token, config_key))
                except OCRCancelled:
                    retorno.cancelled = True
                    break
                except Exception as erro:
                    retorno.errors[str(indice)] = f"{type(erro).__name__}: {erro}"
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futuros = {executor.submit(self._one, item, indice, token, config_key): indice
                           for indice, item in enumerate(items)}
                for futuro in as_completed(futuros):
                    indice = futuros[futuro]
                    try:
                        complete(*futuro.result())
                    except OCRCancelled:
                        retorno.cancelled = True
                        token.cancel()
                    except Exception as erro:
                        retorno.errors[str(indice)] = f"{type(erro).__name__}: {erro}"
        retorno.results = [ordenados[indice] for indice in sorted(ordenados)]
        return retorno
