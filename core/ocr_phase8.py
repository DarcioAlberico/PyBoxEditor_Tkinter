"""Performance, distribuição e benchmark protocolado da Fase 8."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import tracemalloc
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Mapping, Sequence


PHASE8_SCHEMA = "pyboxeditor.ocr-release/v1"
MODEL_PACKAGE_SCHEMA = "pyboxeditor.model-package/v1"
_ENGINE_MEMORY_MB = {
    "native": 128, "tesseract": 256, "trained_line": 512,
    "easyocr": 768, "paddleocr": 1024, "auto": 512,
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_identity(input_data: Any, *, code_version: str, schema_version: str,
                   model_version: str, config: Mapping[str, Any] | None = None) -> str:
    """Gera a chave completa do cache, incluindo todas as dependências semânticas."""
    if isinstance(input_data, bytes):
        input_digest = hashlib.sha256(input_data).hexdigest()
    else:
        try:
            import numpy as np
            if isinstance(input_data, np.ndarray):
                input_digest = hashlib.sha256(input_data.tobytes()).hexdigest()
            else:
                input_digest = hashlib.sha256(_canonical(input_data)).hexdigest()
        except ImportError:
            input_digest = hashlib.sha256(_canonical(input_data)).hexdigest()
    payload = {
        "schema": PHASE8_SCHEMA, "input": input_digest,
        "code_version": str(code_version), "schema_version": str(schema_version),
        "model_version": str(model_version), "config": dict(config or {}),
    }
    return hashlib.sha256(_canonical(payload)).hexdigest()


@dataclass(frozen=True)
class ResourceBudget:
    engine: str
    requested_workers: int = 1
    max_workers: int | None = None
    memory_limit_mb: int | None = None
    per_worker_mb: int | None = None
    available_memory_mb: int | None = None

    def __post_init__(self) -> None:
        if self.requested_workers < 1:
            raise ValueError("requested_workers deve ser positivo")
        if self.max_workers is not None and self.max_workers < 1:
            raise ValueError("max_workers deve ser positivo")
        for name in ("memory_limit_mb", "per_worker_mb", "available_memory_mb"):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} deve ser positivo")

    @property
    def memory_per_worker(self) -> int:
        return self.per_worker_mb or _ENGINE_MEMORY_MB.get(self.engine, 256)

    @property
    def effective_workers(self) -> int:
        result = self.requested_workers
        if self.max_workers is not None:
            result = min(result, self.max_workers)
        limits = [value for value in (self.memory_limit_mb, self.available_memory_mb)
                  if value is not None]
        if limits:
            result = min(result, max(1, min(limits) // self.memory_per_worker))
        return max(1, result)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update({"memory_per_worker": self.memory_per_worker,
                     "effective_workers": self.effective_workers})
        return data


def resolve_resource_budget(engine: str, *, workers: int = 1,
                            memory_limit_mb: int | None = None,
                            available_memory_mb: int | None = None,
                            max_workers: int | None = None,
                            per_worker_mb: int | None = None) -> ResourceBudget:
    return ResourceBudget(str(engine), workers, max_workers, memory_limit_mb,
                          per_worker_mb, available_memory_mb)


@dataclass(frozen=True)
class PackageVerification:
    valid: bool
    errors: tuple[str, ...] = ()
    manifest: Mapping[str, Any] = field(default_factory=dict)


class ModelPackage:
    """Pacote zip de pesos com manifesto e extração protegida contra traversal."""

    @staticmethod
    def create(destination: str | Path, files: Mapping[str, str | Path], *,
               model_id: str, pipeline_version: str, schema: str = MODEL_PACKAGE_SCHEMA,
               metadata: Mapping[str, Any] | None = None) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        entries: list[dict[str, Any]] = []
        sources: dict[str, Path] = {}
        for name, source in sorted(files.items()):
            normalized = ModelPackage._safe_name(name)
            path = Path(source)
            if not path.is_file():
                raise FileNotFoundError(path)
            entries.append({"path": normalized, "sha256": _sha256(path),
                            "size": path.stat().st_size})
            sources[normalized] = path
        manifest = {"schema": schema, "model_id": str(model_id),
                    "pipeline_version": str(pipeline_version),
                    "files": entries, "metadata": dict(metadata or {})}
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False,
                                                         sort_keys=True, indent=2))
            for name in sorted(sources):
                archive.write(sources[name], name)
        return target

    @staticmethod
    def _safe_name(name: str) -> str:
        texto = str(name).replace("\\", "/")
        path = PurePosixPath(texto)
        # A peneira é a do Windows **sempre**, e não a do sistema em que o
        # pacote está sendo aberto: `PurePosixPath("C:evil")` não é absoluto,
        # passava, e `target / "C:evil"` descartava o `target` inteiro. O
        # `:` não tem lugar num nome de arquivo do pacote, em sistema nenhum.
        janela = PureWindowsPath(texto)
        if (path.is_absolute() or janela.is_absolute() or janela.drive
                or janela.root or ":" in texto or ".." in path.parts
                or not path.parts or any(not parte.strip() for parte in path.parts)):
            raise ValueError(f"caminho inseguro no pacote: {name!r}")
        normalized = str(path)
        if normalized == "manifest.json" or normalized.startswith("manifest/"):
            raise ValueError("manifest.json é reservado pelo pacote")
        return normalized

    @staticmethod
    def verify(package: str | Path) -> PackageVerification:
        errors: list[str] = []
        try:
            with zipfile.ZipFile(package) as archive:
                if "manifest.json" not in archive.namelist():
                    return PackageVerification(False, ("manifest.json ausente",))
                manifest = json.loads(archive.read("manifest.json"))
                names = set(archive.namelist())
                for entry in manifest.get("files", ()):
                    name = ModelPackage._safe_name(entry["path"])
                    if name not in names:
                        errors.append(f"arquivo ausente: {name}")
                        continue
                    info = archive.getinfo(name)
                    if info.is_dir():
                        errors.append(f"arquivo é diretório: {name}")
                        continue
                    data = archive.read(name)
                    if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
                        errors.append(f"checksum inválido: {name}")
                    if len(data) != int(entry.get("size", len(data))):
                        errors.append(f"tamanho inválido: {name}")
                return PackageVerification(not errors, tuple(errors), manifest)
        except (OSError, zipfile.BadZipFile, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            return PackageVerification(False, (f"pacote inválido: {error}",))

    @staticmethod
    def install(package: str | Path, destination: str | Path) -> dict[str, Path]:
        verification = ModelPackage.verify(package)
        if not verification.valid:
            raise ValueError("; ".join(verification.errors))
        target = Path(destination)
        target.mkdir(parents=True, exist_ok=True)
        installed: dict[str, Path] = {}
        with zipfile.ZipFile(package) as archive:
            for entry in verification.manifest.get("files", ()):
                name = ModelPackage._safe_name(entry["path"])
                output = (target / name).resolve()
                if target.resolve() not in output.parents:
                    raise ValueError(f"extração insegura: {name}")
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(archive.read(name))
                installed[name] = output
        return installed


@dataclass(frozen=True)
class WheelSmokeReport:
    valid: bool
    errors: tuple[str, ...] = ()
    files: tuple[str, ...] = ()


def smoke_test_wheel(wheel: str | Path, *,
                     required_modules: Sequence[str] = ("core.editorial_pipeline",)) -> WheelSmokeReport:
    errors: list[str] = []
    try:
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
            files = tuple(sorted(names))
            if not any(name.endswith(".dist-info/METADATA") for name in names):
                errors.append("METADATA do wheel ausente")
            for module in required_modules:
                path = module.replace(".", "/") + ".py"
                if path not in names:
                    errors.append(f"módulo ausente no wheel: {module}")
            return WheelSmokeReport(not errors, tuple(errors), files)
    except (OSError, zipfile.BadZipFile) as error:
        return WheelSmokeReport(False, (f"wheel inválido: {error}",))


def smoke_test_installation(wheel: str | Path, *,
                            required_modules: Sequence[str] = ("core.ocr_phase8",),
                            python_executable: str | None = None) -> WheelSmokeReport:
    """Instala o wheel sem dependências em um venv temporário e importa os módulos."""
    static = smoke_test_wheel(wheel, required_modules=required_modules)
    if not static.valid:
        return static
    executable = python_executable or sys.executable
    errors: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="pyboxeditor-smoke-") as folder:
            venv_dir = Path(folder) / "venv"
            subprocess.run([executable, "-m", "venv", str(venv_dir)],
                           check=True, capture_output=True, text=True)
            interpreter = venv_dir / ("Scripts/python.exe" if sys.platform == "win32"
                                      else "bin/python")
            subprocess.run([str(interpreter), "-m", "pip", "install", "--no-deps",
                            "--disable-pip-version-check", str(Path(wheel).resolve())],
                           check=True, capture_output=True, text=True)
            code = ";".join(f"import {module}" for module in required_modules)
            subprocess.run([str(interpreter), "-c", code], check=True,
                           capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as error:
        errors.append(f"instalação smoke falhou: {error}")
    return WheelSmokeReport(not errors, tuple(errors), static.files)


@dataclass(frozen=True)
class BenchmarkCase:
    page_id: str
    reference: Mapping[str, Any]
    input: Any
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BenchmarkProtocol:
    corpus_sha256: str
    language: str = "und"
    dpi: int = 300
    preprocessing: str = "fixed"
    output_mode: str = "editorial"
    revision_policy: str = "same_queue"
    review_cost_per_item: float = 0.0

    def __post_init__(self) -> None:
        if self.dpi < 1:
            raise ValueError("dpi deve ser positivo")
        if self.review_cost_per_item < 0:
            raise ValueError("review_cost_per_item não pode ser negativo")

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(_canonical(asdict(self))).hexdigest()


@dataclass(frozen=True)
class EngineMeasurement:
    engine: str
    quality: Mapping[str, float | None]
    seconds: float
    peak_memory_mb: float
    pages: int
    review_items: int
    review_cost: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkReport:
    protocol: BenchmarkProtocol
    engines: dict[str, EngineMeasurement]

    def compare(self, first: str, second: str) -> dict[str, Any]:
        left, right = self.engines[first], self.engines[second]
        return {
            "first": first, "second": second,
            "cer_delta": (left.quality.get("cer") or 0.0) - (right.quality.get("cer") or 0.0),
            "wer_delta": (left.quality.get("wer") or 0.0) - (right.quality.get("wer") or 0.0),
            "latency_delta_seconds": left.seconds - right.seconds,
            "memory_delta_mb": left.peak_memory_mb - right.peak_memory_mb,
            "review_cost_delta": left.review_cost - right.review_cost,
        }

    def to_dict(self) -> dict[str, Any]:
        return {"protocol": asdict(self.protocol),
                "protocol_fingerprint": self.protocol.fingerprint,
                "engines": {name: item.to_dict() for name, item in self.engines.items()}}


def _prediction(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    converter = getattr(value, "to_dict", None)
    if callable(converter):
        result = converter()
        if isinstance(result, Mapping):
            return result
    raise TypeError("runner deve retornar mapping ou objeto com to_dict()")


def compare_engines(protocol: BenchmarkProtocol, cases: Sequence[BenchmarkCase],
                    runners: Mapping[str, Callable[[Any], Any]]) -> BenchmarkReport:
    """Executa runners comerciais e próprio com a mesma entrada e protocolo."""
    from core.ocr_benchmark import agregar, medir_pagina

    if not runners:
        raise ValueError("pelo menos um engine é necessário")
    measurements: dict[str, EngineMeasurement] = {}
    for name, runner in runners.items():
        page_results = []
        review_items = 0
        tracemalloc.start()
        started = time.perf_counter()
        try:
            for case in cases:
                prediction = _prediction(runner(case.input))
                page_results.append(medir_pagina(case.page_id, case.reference, prediction,
                                                 metadata={**dict(case.metadata), "engine": name}))
                review_items += int(case.metadata.get("review_items", 0))
        finally:
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        aggregate = agregar(page_results)
        seconds = time.perf_counter() - started
        measurements[str(name)] = EngineMeasurement(
            str(name), {
                "cer": aggregate.text.cer if aggregate.text else None,
                "wer": aggregate.words.cer if aggregate.words else None,
                "boxes_f1": aggregate.boxes.f1 if aggregate.boxes else None,
                "layout_accuracy": (aggregate.layout.acuracia_tipos
                                     if aggregate.layout else None),
                "pages": float(aggregate.pages),
            }, seconds, peak / (1024 * 1024), aggregate.pages, review_items,
            review_items * protocol.review_cost_per_item,
        )
    return BenchmarkReport(protocol, measurements)


compare_commercial_engines = compare_engines
