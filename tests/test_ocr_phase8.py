from __future__ import annotations

import zipfile

from core.ocr_phase8 import (
    BenchmarkCase,
    BenchmarkProtocol,
    ModelPackage,
    ResourceBudget,
    compare_engines,
    cache_identity,
    smoke_test_wheel,
)


def test_cache_invalida_por_codigo_schema_modelo_e_configuracao():
    base = cache_identity(
        b"page", code_version="code-1", schema_version="schema-1",
        model_version="model-1", config={"dpi": 300},
    )
    assert base != cache_identity(
        b"page", code_version="code-2", schema_version="schema-1",
        model_version="model-1", config={"dpi": 300},
    )
    assert base != cache_identity(
        b"page", code_version="code-1", schema_version="schema-2",
        model_version="model-1", config={"dpi": 300},
    )
    assert base != cache_identity(
        b"page", code_version="code-1", schema_version="schema-1",
        model_version="model-2", config={"dpi": 300},
    )
    assert base != cache_identity(
        b"page", code_version="code-1", schema_version="schema-1",
        model_version="model-1", config={"dpi": 600},
    )


def test_orcamento_limita_workers_por_memoria_e_engine():
    budget = ResourceBudget("paddleocr", requested_workers=8, memory_limit_mb=2000,
                            per_worker_mb=700, available_memory_mb=4000)
    assert budget.effective_workers == 2
    assert budget.to_dict()["effective_workers"] == 2


def test_pacote_de_modelo_tem_manifesto_checksum_e_extracao_segura(tmp_path):
    weights = tmp_path / "line.pth"
    config = tmp_path / "config.json"
    weights.write_bytes(b"weights")
    config.write_text('{"alphabet":"abc"}', encoding="utf-8")
    package_path = ModelPackage.create(
        tmp_path / "models.zip", {"weights/line.pth": weights, "config.json": config},
        model_id="line-crnn", pipeline_version="editorial-pipeline/v4",
    )

    verification = ModelPackage.verify(package_path)
    assert verification.valid is True
    with zipfile.ZipFile(package_path) as archive:
        assert "manifest.json" in archive.namelist()
    installed = ModelPackage.install(package_path, tmp_path / "installed")
    assert installed["weights/line.pth"].read_bytes() == b"weights"


def test_benchmark_compara_runners_com_mesmo_protocolo_e_mede_custo():
    protocol = BenchmarkProtocol("corpus-sha", language="pt", dpi=300,
                                 review_cost_per_item=2.5)
    cases = [BenchmarkCase("p1", {"text": "texto correto"}, "page", {"review_items": 2})]
    report = compare_engines(
        protocol, cases,
        {"pyboxeditor": lambda _input: {"text": "texto correto"},
         "abbyy": lambda _input: {"text": "texto cor"}},
    )
    assert report.engines["pyboxeditor"].quality["cer"] == 0.0
    assert report.engines["abbyy"].quality["cer"] > 0.0
    assert report.engines["pyboxeditor"].review_cost == 5.0
    assert report.compare("pyboxeditor", "abbyy")["cer_delta"] < 0


def test_smoke_wheel_rejeita_arquivo_sem_modulo(tmp_path):
    package = tmp_path / "fake.whl"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("pkg/__init__.py", "")
    report = smoke_test_wheel(package, required_modules=("core.ocr_phase8",))
    assert report.valid is False
    assert report.errors
