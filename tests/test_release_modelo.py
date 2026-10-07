from __future__ import annotations

import hashlib
import json
import zipfile

from core.ocr_phase8 import ModelPackage
from core.ocr_phase7 import WeightManifest
from scripts.empacotar_modelo import main


def _meta(modelo, *, holdout: bool = True) -> dict:
    dados = {
        "model_sha256": hashlib.sha256(modelo.read_bytes()).hexdigest(),
        "cer_validacao": 0.01,
        "holdout_required": holdout,
        "holdout_evaluated": holdout,
        "holdout_cer": 0.04 if holdout else None,
    }
    return dados


def test_empacotamento_anexa_metadados_e_manifesto_de_pesos(tmp_path):
    modelo = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    manifesto = tmp_path / "modelo.manifest.json"
    saida = tmp_path / "modelo.zip"
    modelo.write_bytes(b"pesos")
    meta.write_text(json.dumps(_meta(modelo)), encoding="utf-8")
    WeightManifest.from_file(
        modelo, model_id="line-crnn", pipeline_version="editorial-pipeline/v4",
    ).save(manifesto)

    assert main([
        str(modelo), "-o", str(saida), "--model-id", "line-crnn",
        "--pipeline-version", "editorial-pipeline/v4",
        "--meta", str(meta), "--manifesto-pesos", str(manifesto),
    ]) == 0
    assert ModelPackage.verify(saida).valid is True
    with zipfile.ZipFile(saida) as arquivo:
        nomes = set(arquivo.namelist())
    assert "weights/modelo.pth" in nomes
    assert "metadata/model.json" in nomes
    assert "manifests/weights.json" in nomes


def test_empacotamento_rejeita_manifesto_de_pesos_incompativel(tmp_path):
    modelo = tmp_path / "modelo.pth"
    manifesto = tmp_path / "modelo.manifest.json"
    saida = tmp_path / "modelo.zip"
    modelo.write_bytes(b"pesos")
    manifesto.write_text(json.dumps({
        "model_id": "line-crnn", "path": str(modelo),
        "sha256": "0" * 64, "pipeline_version": "editorial-pipeline/v4",
    }), encoding="utf-8")

    assert main([
        str(modelo), "-o", str(saida), "--model-id", "line-crnn",
        "--manifesto-pesos", str(manifesto),
    ]) == 2
    assert not saida.exists()


def test_empacotamento_exige_proveniencia_do_dataset(tmp_path):
    modelo = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    saida = tmp_path / "modelo.zip"
    modelo.write_bytes(b"pesos")
    meta.write_text(json.dumps(_meta(modelo)), encoding="utf-8")

    assert main([
        str(modelo), "-o", str(saida), "--model-id", "line-crnn",
        "--pipeline-version", "editorial-pipeline/v4",
        "--meta", str(meta), "--exigir-proveniencia-dataset",
    ]) == 2
    assert not saida.exists()


def test_empacotamento_aceita_proveniencia_do_dataset_verificada(tmp_path):
    modelo = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    dataset = tmp_path / "dataset.json"
    saida = tmp_path / "modelo.zip"
    modelo.write_bytes(b"pesos")
    dataset.write_bytes(b"dataset revisado")
    dados = _meta(modelo) | {
        "dataset_provenance_verified": True,
        "dataset_provenance_path": str(dataset),
        "dataset_provenance_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
    }
    meta.write_text(json.dumps(dados), encoding="utf-8")

    assert main([
        str(modelo), "-o", str(saida), "--model-id", "line-crnn",
        "--pipeline-version", "editorial-pipeline/v4",
        "--meta", str(meta), "--exigir-proveniencia-dataset",
    ]) == 0
    assert ModelPackage.verify(saida).valid is True


def test_empacotamento_anexa_evidencias_referenciadas_pelo_treino(tmp_path):
    modelo = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    dataset = tmp_path / "dataset.json"
    calibracao = tmp_path / "calibracao.json"
    split = tmp_path / "split.json"
    vinculo = tmp_path / "line-binding.json"
    holdout = tmp_path / "holdout.json"
    saida = tmp_path / "modelo.zip"
    modelo.write_bytes(b"pesos")
    dataset.write_bytes(b"dataset")
    calibracao.write_text(json.dumps({
        "schema": "pyboxeditor.ocr-line-calibration/v1",
    }), encoding="utf-8")
    split.write_bytes(b"split")
    vinculo.write_bytes(b"vinculo")
    holdout.write_bytes(b"holdout")
    referencias = {
        "dataset_provenance_path": str(dataset),
        "dataset_provenance_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "calibration_report": str(calibracao),
        "calibration_report_sha256": hashlib.sha256(calibracao.read_bytes()).hexdigest(),
        "split_manifest": str(split),
        "split_manifest_sha256": hashlib.sha256(split.read_bytes()).hexdigest(),
        "line_binding": str(vinculo),
        "line_binding_sha256": hashlib.sha256(vinculo.read_bytes()).hexdigest(),
        "holdout_provenance": str(holdout),
    }
    meta.write_text(json.dumps(_meta(modelo) | referencias), encoding="utf-8")

    assert main([
        str(modelo), "-o", str(saida), "--model-id", "line-crnn",
        "--pipeline-version", "editorial-pipeline/v4", "--meta", str(meta),
    ]) == 0
    verificacao = ModelPackage.verify(saida)
    assert verificacao.valid is True
    artefatos = verificacao.manifest["metadata"]["release_artifacts"]
    assert {item["kind"] for item in artefatos} == {
        "dataset_provenance", "calibration_report", "split_manifest",
        "line_binding", "holdout_provenance",
    }
    assert {item["path"] for item in artefatos} <= set(
        item["path"] for item in verificacao.manifest["files"])


def test_empacotamento_rejeita_evidencia_referenciada_ausente(tmp_path):
    modelo = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    saida = tmp_path / "modelo.zip"
    modelo.write_bytes(b"pesos")
    meta.write_text(json.dumps(_meta(modelo) | {
        "calibration_report": str(tmp_path / "calibracao-inexistente.json"),
    }), encoding="utf-8")

    assert main([
        str(modelo), "-o", str(saida), "--model-id", "line-crnn",
        "--pipeline-version", "editorial-pipeline/v4", "--meta", str(meta),
    ]) == 2
    assert not saida.exists()


def test_empacotamento_rejeita_rodada_ocr_com_gate_semantico_reprovado(tmp_path):
    modelo = tmp_path / "modelo.pth"
    rodada = tmp_path / "rodada.json"
    saida = tmp_path / "modelo.zip"
    modelo.write_bytes(b"pesos")
    rodada.write_text(json.dumps({
        "semanticas": {"notation": {"acuracia_legal": 0.0}},
        "quality_gate": {
            "enabled": True,
            "passed": False,
            "failures": ["legalidade de notacao abaixo do limite"],
        },
    }), encoding="utf-8")

    assert main([
        str(modelo), "-o", str(saida), "--model-id", "line-crnn",
        "--pipeline-version", "editorial-pipeline/v4",
        "--rodada-corpus", str(rodada), "--exigir-gate-corpus",
    ]) == 2
    assert not saida.exists()


def test_empacotamento_anexa_rodada_ocr_semantica_aprovada(tmp_path):
    modelo = tmp_path / "modelo.pth"
    rodada = tmp_path / "rodada.json"
    saida = tmp_path / "modelo.zip"
    modelo.write_bytes(b"pesos")
    rodada.write_text(json.dumps({
        "semanticas": {
            "notation": {"acuracia_exata": 1.0, "acuracia_legal": 1.0},
        },
        "quality_gate": {"enabled": True, "passed": True, "failures": []},
    }), encoding="utf-8")

    assert main([
        str(modelo), "-o", str(saida), "--model-id", "line-crnn",
        "--pipeline-version", "editorial-pipeline/v4",
        "--rodada-corpus", str(rodada), "--exigir-gate-corpus",
    ]) == 0
    verificacao = ModelPackage.verify(saida)
    assert verificacao.valid is True
    assert "metadata/ocr_round.json" in {
        item["path"] for item in verificacao.manifest["files"]
    }


def test_empacotamento_rejeita_gate_editorial_reprovado(tmp_path):
    modelo = tmp_path / "modelo.pth"
    gate = tmp_path / "quality.json"
    saida = tmp_path / "modelo.zip"
    modelo.write_bytes(b"pesos")
    gate.write_text(json.dumps({
        "schema": "pyboxeditor.editorial-quality/v1",
        "valid": False,
        "errors": ["bloco d1: FEN invalido"],
        "metrics": {"pages": 1, "blocks": 1},
    }), encoding="utf-8")

    assert main([
        str(modelo), "-o", str(saida), "--model-id", "line-crnn",
        "--pipeline-version", "editorial-pipeline/v4",
        "--gate-editorial", str(gate), "--exigir-gate-editorial",
    ]) == 2
    assert not saida.exists()


def test_empacotamento_anexa_gate_editorial_aprovado(tmp_path):
    modelo = tmp_path / "modelo.pth"
    gate = tmp_path / "quality.json"
    saida = tmp_path / "modelo.zip"
    modelo.write_bytes(b"pesos")
    gate.write_text(json.dumps({
        "schema": "pyboxeditor.editorial-quality/v1",
        "valid": True,
        "errors": [],
        "metrics": {"pages": 1, "blocks": 2},
    }), encoding="utf-8")

    assert main([
        str(modelo), "-o", str(saida), "--model-id", "line-crnn",
        "--pipeline-version", "editorial-pipeline/v4",
        "--gate-editorial", str(gate), "--exigir-gate-editorial",
    ]) == 0
    verificacao = ModelPackage.verify(saida)
    assert verificacao.valid is True
    assert "metadata/editorial_quality.json" in {
        item["path"] for item in verificacao.manifest["files"]
    }


def test_empacotamento_com_portao_recusa_modelo_sem_holdout(tmp_path):
    modelo = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    saida = tmp_path / "modelo.zip"
    modelo.write_bytes(b"pesos")
    meta.write_text(json.dumps(_meta(modelo, holdout=False)), encoding="utf-8")

    assert main([
        str(modelo), "-o", str(saida), "--model-id", "line-crnn",
        "--meta", str(meta), "--exigir-portao",
    ]) == 2
    assert not saida.exists()
