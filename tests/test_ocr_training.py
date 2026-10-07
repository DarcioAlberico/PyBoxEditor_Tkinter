from __future__ import annotations

import json
import os
import sys
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from core.ocr_training import (EngineTrainingStatus, OCRTrainingSummary,
                               salvar_estado)


def test_portao_rejeita_metadados_anteriores_ao_peso(tmp_path):
    from core.linha_trainer import modelo_utilizavel

    pesos = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    pesos.write_bytes(b"pesos-novos")
    meta.write_text(json.dumps({"cer_validacao": 0.01}), encoding="utf-8")
    os.utime(meta, ns=(2_000_000_000, 2_000_000_000))
    os.utime(pesos, ns=(3_000_000_000, 3_000_000_000))

    utilizavel, motivo = modelo_utilizavel(meta, pesos)

    assert utilizavel is False
    assert "desencontrados" in motivo


def test_avaliar_usa_os_caminhos_padrao_quando_omitidos(tmp_path, monkeypatch):
    from config import paths
    from core import linha_trainer

    modelo = tmp_path / "text_line_model.pth"
    meta = tmp_path / "text_line_model.json"
    dataset = tmp_path / "training_data_linhas"
    (dataset / "images").mkdir(parents=True)
    imagem = dataset / "images" / "livro_linha_00001.png"
    Image.new("L", (80, 24), 255).save(imagem)
    (dataset / "rec_gt.txt").write_text(
        "images/livro_linha_00001.png\ttexto\n", encoding="utf-8")
    modelo.write_bytes(b"peso")
    meta.write_text("{}", encoding="utf-8")

    class PreditorFalso:
        def __init__(self, destino, metadados):
            assert (destino, metadados) == (modelo, meta)

        def predict_conf(self, _imagem):
            return "texto", 0.9

    monkeypatch.setattr(paths, "caminhos_modelo_linha",
                        lambda: (modelo, meta))
    monkeypatch.setattr(paths, "pasta_de_linhas", lambda: dataset)
    monkeypatch.setattr(linha_trainer, "LinhaPredictor", PreditorFalso)

    resultado = linha_trainer.avaliar()

    assert resultado["modelo"] == str(modelo)
    assert resultado["meta"] == str(meta)
    assert resultado["dataset"] == str(dataset / "rec_gt.txt")
    assert resultado["cer"] == 0.0


def test_portao_rejeita_hash_de_peso_incompatível(tmp_path):
    from core.linha_trainer import modelo_utilizavel

    pesos = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    pesos.write_bytes(b"pesos-reais")
    meta.write_text(json.dumps({
        "cer_validacao": 0.01,
        "model_sha256": hashlib.sha256(b"outros-pesos").hexdigest(),
    }), encoding="utf-8")

    utilizavel, motivo = modelo_utilizavel(meta, pesos)

    assert utilizavel is False
    assert "hash" in motivo


def test_portao_rejeita_pacote_marcado_com_holdout_nao_avaliado(tmp_path):
    from core.linha_trainer import modelo_utilizavel

    pesos = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    pesos.write_bytes(b"pesos")
    meta.write_text(json.dumps({
        "cer_validacao": 0.01,
        "holdout_required": True,
        "holdout_evaluated": False,
    }), encoding="utf-8")

    utilizavel, motivo = modelo_utilizavel(meta, pesos)

    assert utilizavel is False
    assert "holdout" in motivo.lower()


def test_portao_rejeita_proveniencia_de_holdout_sem_dataset_de_linhas(tmp_path):
    from core.linha_trainer import modelo_utilizavel

    pesos = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    pesos.write_bytes(b"pesos")
    meta.write_text(json.dumps({
        "cer_validacao": 0.01,
        "model_sha256": hashlib.sha256(b"pesos").hexdigest(),
        "holdout_required": True,
        "holdout_evaluated": True,
        "holdout_cer": 0.04,
        "holdout_provenance": str(tmp_path / "selection.json"),
    }), encoding="utf-8")

    utilizavel, motivo = modelo_utilizavel(meta, pesos)

    assert utilizavel is False
    assert "linhas" in motivo.lower()


def test_portao_rejeita_proveniencia_obrigatoria_do_dataset_ausente(tmp_path):
    from core.linha_trainer import modelo_utilizavel

    pesos = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    pesos.write_bytes(b"pesos")
    meta.write_text(json.dumps({
        "cer_validacao": 0.01,
        "model_sha256": hashlib.sha256(b"pesos").hexdigest(),
        "dataset_provenance_required": True,
    }), encoding="utf-8")

    utilizavel, motivo = modelo_utilizavel(meta, pesos)

    assert utilizavel is False
    assert "proveniência" in motivo.lower()


def test_portao_rejeita_proveniencia_obrigatoria_do_dataset_alterada(tmp_path):
    from core.linha_trainer import modelo_utilizavel

    pesos = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    proveniencia = tmp_path / "dataset-proveniencia.json"
    pesos.write_bytes(b"pesos")
    proveniencia.write_bytes(b"manifesto-original")
    meta.write_text(json.dumps({
        "cer_validacao": 0.01,
        "model_sha256": hashlib.sha256(b"pesos").hexdigest(),
        "dataset_provenance_required": True,
        "dataset_provenance_verified": True,
        "dataset_provenance_path": str(proveniencia),
        "dataset_provenance_sha256": hashlib.sha256(
            b"manifesto-diferente").hexdigest(),
    }), encoding="utf-8")

    utilizavel, motivo = modelo_utilizavel(meta, pesos)

    assert utilizavel is False
    assert "sha" in motivo.lower()


def test_portao_rejeita_calibracao_declarada_sem_relatorio(tmp_path):
    from core.linha_trainer import modelo_utilizavel

    pesos = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    pesos.write_bytes(b"pesos")
    meta.write_text(json.dumps({
        "cer_validacao": 0.01,
        "model_sha256": hashlib.sha256(b"pesos").hexdigest(),
        "calibration_evaluated": True,
    }), encoding="utf-8")

    utilizavel, motivo = modelo_utilizavel(meta, pesos)

    assert utilizavel is False
    assert "calibração" in motivo.lower()


def test_portao_rejeita_relatorio_de_calibracao_adulterado(tmp_path):
    from core.linha_trainer import modelo_utilizavel

    pesos = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    relatorio = tmp_path / "modelo_calibration.json"
    pesos.write_bytes(b"pesos")
    relatorio.write_text(json.dumps({
        "schema": "pyboxeditor.ocr-line-calibration/v1",
        "domains": {"domains": {}},
    }), encoding="utf-8")
    meta.write_text(json.dumps({
        "cer_validacao": 0.01,
        "model_sha256": hashlib.sha256(b"pesos").hexdigest(),
        "calibration_evaluated": True,
        "calibration_report": str(relatorio),
        "calibration_report_sha256": hashlib.sha256(b"outro").hexdigest(),
    }), encoding="utf-8")

    utilizavel, motivo = modelo_utilizavel(meta, pesos)

    assert utilizavel is False
    assert "sha" in motivo.lower()


def test_portao_aceita_relatorio_de_calibracao_integro(tmp_path):
    from core.linha_trainer import modelo_utilizavel

    pesos = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    relatorio = tmp_path / "modelo_calibration.json"
    pesos.write_bytes(b"pesos")
    relatorio.write_text(json.dumps({
        "schema": "pyboxeditor.ocr-line-calibration/v1",
        "domains": {"domains": {}},
    }), encoding="utf-8")
    meta.write_text(json.dumps({
        "cer_validacao": 0.01,
        "model_sha256": hashlib.sha256(b"pesos").hexdigest(),
        "calibration_evaluated": True,
        "calibration_report": str(relatorio),
        "calibration_report_sha256": hashlib.sha256(
            relatorio.read_bytes()).hexdigest(),
    }), encoding="utf-8")

    utilizavel, motivo = modelo_utilizavel(meta, pesos)

    assert utilizavel is True
    assert "1.0%" in motivo


def test_portao_rejeita_split_obrigatorio_ausente(tmp_path):
    from core.linha_trainer import modelo_utilizavel

    pesos = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    pesos.write_bytes(b"pesos")
    meta.write_text(json.dumps({
        "cer_validacao": 0.01,
        "model_sha256": hashlib.sha256(b"pesos").hexdigest(),
        "split_required": True,
    }), encoding="utf-8")

    utilizavel, motivo = modelo_utilizavel(meta, pesos)

    assert utilizavel is False
    assert "split" in motivo.lower()


def test_treino_rejeita_grupo_de_linhas_compartilhado_entre_splits(tmp_path):
    from core.linha_trainer import validar_datasets_disjuntos

    treino = tmp_path / "treino"
    validacao = tmp_path / "validacao"
    for pasta in (treino, validacao):
        (pasta / "images").mkdir(parents=True)
        Image.new("L", (80, 24), 255).save(
            pasta / "images" / "livro1_linha_00001.png")
        (pasta / "rec_gt.txt").write_text(
            "images/livro1_linha_00001.png\ttexto\n", encoding="utf-8")

    with pytest.raises(ValueError, match="grupo"):
        validar_datasets_disjuntos({"treino": treino, "validacao": validacao})


def test_validador_aceita_registros_de_um_split_já_carregado(tmp_path):
    from core.linha_trainer import validar_datasets_disjuntos

    treino = tmp_path / "treino"
    validacao = tmp_path / "validacao"
    for pasta in (treino, validacao):
        (pasta / "images").mkdir(parents=True)
    imagem_treino = treino / "images" / "livro-t_linha_00001.png"
    imagem_validacao = validacao / "images" / "livro-v_linha_00001.png"
    Image.new("L", (80, 24), 255).save(imagem_treino)
    Image.new("L", (80, 24), 255).save(imagem_validacao)
    (treino / "rec_gt.txt").write_text(
        "images/livro-t_linha_00001.png\ttexto\n", encoding="utf-8")
    (validacao / "rec_gt.txt").write_text(
        "images/livro-v_linha_00001.png\ttexto\n", encoding="utf-8")

    validar_datasets_disjuntos({
        "treino": [(imagem_treino, "texto")],
        "validacao": [(imagem_validacao, "texto")],
    })


def test_pacote_rejeita_vazamento_entre_validacao_e_calibracao(tmp_path, monkeypatch):
    """Todo dataset usado pelo pacote precisa ter grupos de origem disjuntos."""
    from core import ocr_training

    def criar_dataset(nome, grupo):
        pasta = tmp_path / nome
        (pasta / "images").mkdir(parents=True)
        Image.new("L", (80, 24), 255).save(
            pasta / "images" / f"{grupo}_linha_00001.png")
        (pasta / "rec_gt.txt").write_text(
            f"images/{grupo}_linha_00001.png\ttexto\n", encoding="utf-8")
        return pasta

    treino = criar_dataset("treino", "livro-t")
    validacao = criar_dataset("validacao", "livro-compartilhado")
    calibracao = criar_dataset("calibracao", "livro-compartilhado")
    monkeypatch.setattr(
        "core.linha_trainer.treinar",
        lambda **_kwargs: pytest.fail("o treino não deveria começar"),
    )
    monkeypatch.setattr(
        ocr_training,
        "construir_modelo_linguagem",
        lambda *args, **kwargs: tmp_path / "lexico.json",
    )

    with pytest.raises(ValueError, match="grupo"):
        ocr_training.treinar_pacote(
            pasta=treino, validacao=validacao, calibracao=calibracao,
            destino=tmp_path / "modelo.pth", meta=tmp_path / "modelo.json",
            preparar_pesos=False)


def test_estado_do_pacote_e_serializavel(tmp_path: Path):
    resumo = OCRTrainingSummary(
        True, "ocr_language_model.json",
        [EngineTrainingStatus("EasyOCR", True, True, message="ok")],
        "ocr_training_state.json", production_eligible=False,
        production_gate_reason="CER acima do limite")
    caminho = salvar_estado(resumo, tmp_path / "estado.json")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    assert dados["line_model"] is True
    assert dados["engines"][0]["prepared"] is True
    assert dados["production_eligible"] is False
    assert dados["production_gate_reason"] == "CER acima do limite"


def test_treinar_pacote_encaminha_controles_e_versao_do_dataset(tmp_path, monkeypatch):
    from core import ocr_training

    chamadas = {}
    modelo = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    lexico = tmp_path / "ocr_language_model.json"

    def falso_treinar(**kwargs):
        chamadas.update(kwargs)
        return True

    monkeypatch.setattr("core.linha_trainer.treinar", falso_treinar)
    monkeypatch.setattr(
        ocr_training, "construir_modelo_linguagem", lambda *args, **kwargs: lexico)
    monkeypatch.setattr(ocr_training, "preparar_engines", lambda *args, **kwargs: [])

    resumo = ocr_training.treinar_pacote(
        pasta=tmp_path / "dataset", destino=modelo, meta=meta,
        epocas=2, batch_size=3, paciencia=4, semente=17,
        taxa_aprendizado=0.0002, dispositivo="cpu", retomar=False,
        alfabeto_automatico=False, preparar_pesos=False,
        dataset_version="correcoes-v3",
    )

    assert chamadas["semente"] == 17
    assert chamadas["taxa_aprendizado"] == 0.0002
    assert chamadas["dispositivo"] == "cpu"
    assert chamadas["retomar"] is False
    assert chamadas["alfabeto_automatico"] is False
    assert resumo.dataset_version == "correcoes-v3"
    assert resumo.production_eligible is False
    assert "modelo de linha" in resumo.production_gate_reason


def test_treino_registra_proveniencia_do_dataset_no_metadata(tmp_path, monkeypatch):
    from core import ocr_training

    modelo = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    lexico = tmp_path / "ocr_language_model.json"
    proveniencia = tmp_path / "dataset-proveniencia.json"
    proveniencia.write_text(json.dumps({
        "schema": "pyboxeditor.ocr-corrections/v1",
        "metadata": {
            "source": "ocr14",
            "review_provenance": {"verified": True},
        },
    }), encoding="utf-8")

    def falso_treinar(**_kwargs):
        modelo.write_bytes(b"pesos")
        meta.write_text(json.dumps({"cer_validacao": 0.01}), encoding="utf-8")
        return True

    monkeypatch.setattr("core.linha_trainer.treinar", falso_treinar)
    monkeypatch.setattr("core.linha_trainer.modelo_utilizavel",
                        lambda *args: (False, "sem holdout"))
    monkeypatch.setattr(ocr_training, "construir_modelo_linguagem",
                        lambda *args, **kwargs: lexico)
    monkeypatch.setattr(ocr_training, "preparar_engines",
                        lambda *args, **kwargs: [])

    ocr_training.treinar_pacote(
        pasta=tmp_path / "dataset", destino=modelo, meta=meta,
        preparar_pesos=False, retomar=False,
        dataset_provenance=proveniencia,
        exigir_proveniencia_dataset=True,
    )

    dados = json.loads(meta.read_text(encoding="utf-8"))
    assert dados["dataset_provenance_verified"] is True
    assert dados["dataset_provenance_sha256"]
    assert dados["dataset_provenance_source"] == "ocr14"


def test_pacote_novo_nao_elegivel_sem_holdout_real(tmp_path, monkeypatch):
    from core import ocr_training

    modelo = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"

    def falso_treinar(**kwargs):
        modelo.write_bytes(b"pesos")
        meta.write_text(json.dumps({"cer_validacao": 0.01}), encoding="utf-8")
        return True

    monkeypatch.setattr("core.linha_trainer.treinar", falso_treinar)
    monkeypatch.setattr("core.linha_trainer.modelo_utilizavel",
                        lambda *args: (True, "modelo de linha com 1,0% de CER"))
    monkeypatch.setattr(ocr_training, "construir_modelo_linguagem",
                        lambda *args, **kwargs: tmp_path / "lexico.json")
    monkeypatch.setattr(ocr_training, "preparar_engines", lambda *args, **kwargs: [])

    resumo = ocr_training.treinar_pacote(
        pasta=tmp_path / "dataset", destino=modelo, meta=meta,
        preparar_pesos=False)

    assert resumo.production_eligible is False
    assert "holdout" in resumo.production_gate_reason.lower()


def test_pacote_registra_holdout_e_so_promove_com_cer_aprovado(tmp_path, monkeypatch):
    from core import ocr_training

    modelo = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    holdout = tmp_path / "holdout"
    (holdout / "images").mkdir(parents=True)
    Image.new("L", (80, 24), 255).save(holdout / "images" / "h_linha_00001.png")
    (holdout / "rec_gt.txt").write_text(
        "images/h_linha_00001.png\ttexto limpo\n", encoding="utf-8")

    def falso_treinar(**kwargs):
        modelo.write_bytes(b"pesos")
        meta.write_text(json.dumps({"cer_validacao": 0.01}), encoding="utf-8")
        return True

    monkeypatch.setattr("core.linha_trainer.treinar", falso_treinar)
    monkeypatch.setattr("core.linha_trainer.modelo_utilizavel",
                        lambda *args: (True, "modelo de linha com 1,0% de CER"))
    monkeypatch.setattr("core.linha_trainer.avaliar", lambda *args: {
        "cer": 0.04, "wer": 0.08, "exatas": 1, "linhas": 1,
    })
    monkeypatch.setattr(ocr_training, "construir_modelo_linguagem",
                        lambda *args, **kwargs: tmp_path / "lexico.json")
    monkeypatch.setattr(ocr_training, "preparar_engines", lambda *args, **kwargs: [])

    resumo = ocr_training.treinar_pacote(
        pasta=tmp_path / "dataset", holdout=holdout,
        destino=modelo, meta=meta, preparar_pesos=False)

    metadados = json.loads(meta.read_text(encoding="utf-8"))
    assert resumo.production_eligible is True
    assert resumo.holdout_evaluated is True
    assert resumo.holdout_cer == 0.04
    assert metadados["holdout_required"] is True
    assert metadados["holdout_evaluated"] is True
    assert metadados["holdout_cer"] == 0.04
    assert metadados["holdout_sha256"]


def test_pacote_calibra_dataset_independente_e_persiste_relatorio(tmp_path, monkeypatch):
    from core import ocr_training

    modelo = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    calibracao = tmp_path / "calibracao"
    (calibracao / "images").mkdir(parents=True)
    Image.new("L", (80, 24), 255).save(calibracao / "images" / "c_linha.png")
    (calibracao / "rec_gt.txt").write_text(
        "images/c_linha.png\ttexto calibracao\n", encoding="utf-8")

    def falso_treinar(**_kwargs):
        modelo.write_bytes(b"pesos")
        meta.write_text(json.dumps({"cer_validacao": 0.01}), encoding="utf-8")
        return True

    monkeypatch.setattr("core.linha_trainer.treinar", falso_treinar)
    monkeypatch.setattr("core.linha_trainer.modelo_utilizavel",
                        lambda *args: (False, "sem holdout"))
    monkeypatch.setattr("core.linha_trainer.avaliar", lambda *args: {
        "calibration_observations": [
            {"domain": "body", "confidence": 0.8, "correct": True},
            {"domain": "body", "confidence": 0.7, "correct": False},
        ],
    })
    monkeypatch.setattr(ocr_training, "construir_modelo_linguagem",
                        lambda *args, **kwargs: tmp_path / "lexico.json")
    monkeypatch.setattr(ocr_training, "preparar_engines", lambda *args, **kwargs: [])

    resumo = ocr_training.treinar_pacote(
        pasta=tmp_path / "treino", calibracao=calibracao,
        destino=modelo, meta=meta, preparar_pesos=False)

    relatorio = Path(resumo.calibration_report)
    dados = json.loads(relatorio.read_text(encoding="utf-8"))
    metadados = json.loads(meta.read_text(encoding="utf-8"))
    assert relatorio.is_file()
    assert dados["schema"] == "pyboxeditor.ocr-line-calibration/v1"
    assert dados["domains"]["domains"]["body"]["samples"] == 2
    assert resumo.calibration_domains == ("body",)
    assert metadados["calibration_evaluated"] is True
    assert metadados["calibration_report_sha256"]


def test_pacote_recusa_calibracao_no_mesmo_dataset_do_treino(tmp_path):
    from core import ocr_training

    with pytest.raises(ValueError, match="calibra"):
        ocr_training.treinar_pacote(
            pasta=tmp_path, calibracao=tmp_path,
            destino=tmp_path / "modelo.pth", meta=tmp_path / "modelo.json",
            preparar_pesos=False)


def test_pacote_registra_manifesto_de_split_obrigatorio(tmp_path, monkeypatch):
    from core import ocr_training
    from core.ocr_phase7 import CorpusItem, split_corpus

    modelo = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    split_path = tmp_path / "split.json"
    split_path.write_text(json.dumps(split_corpus([
        CorpusItem("train", "doc-t", "book-t", "editor-t", "source-t",
                   "single-column", "body"),
        CorpusItem("holdout", "doc-h", "book-h", "editor-h", "source-h",
                   "two-column", "body", holdout=True),
    ], validation_fraction=0, test_fraction=0).to_dict()), encoding="utf-8")

    def falso_treinar(**_kwargs):
        modelo.write_bytes(b"pesos")
        meta.write_text(json.dumps({"cer_validacao": 0.01}), encoding="utf-8")
        return True

    monkeypatch.setattr("core.linha_trainer.treinar", falso_treinar)
    monkeypatch.setattr("core.linha_trainer.modelo_utilizavel",
                        lambda *args: (False, "sem holdout"))
    monkeypatch.setattr(ocr_training, "construir_modelo_linguagem",
                        lambda *args, **kwargs: tmp_path / "lexico.json")
    monkeypatch.setattr(ocr_training, "preparar_engines", lambda *args, **kwargs: [])

    resumo = ocr_training.treinar_pacote(
        pasta=tmp_path / "treino", split_manifest=split_path,
        exigir_split=True, destino=modelo, meta=meta, preparar_pesos=False)

    dados = json.loads(meta.read_text(encoding="utf-8"))
    assert dados["split_required"] is True
    assert dados["split_schema"] == "pyboxeditor.ocr-split/v1"
    assert dados["split_counts"]["holdout"] == 1
    assert resumo.split_manifest_sha256


def test_pacote_exige_vinculo_fisico_das_linhas(tmp_path, monkeypatch):
    from core import ocr_training
    from core.ocr_line_binding import bind_line_datasets
    from core.ocr_phase7 import CorpusItem, split_corpus

    modelo = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    treino = tmp_path / "treino"
    holdout = tmp_path / "holdout"
    for pasta, grupo in ((treino, "book-t"), (holdout, "book-h")):
        (pasta / "images").mkdir(parents=True)
        Image.new("L", (80, 24), 255).save(
            pasta / "images" / f"{grupo}_linha_00001.png")
        (pasta / "rec_gt.txt").write_text(
            f"images/{grupo}_linha_00001.png\ttexto\n", encoding="utf-8")
    split_path = tmp_path / "split.json"
    split_path.write_text(json.dumps(split_corpus([
        CorpusItem("train-item", "doc-t", "book-t", "editor-t", "source-t",
                   "single-column", "body"),
        CorpusItem("holdout-item", "doc-h", "book-h", "editor-h", "source-h",
                   "two-column", "body", holdout=True),
    ], validation_fraction=0, test_fraction=0).to_dict()), encoding="utf-8")
    binding = tmp_path / "line-binding.json"
    binding.write_text(json.dumps(bind_line_datasets(
        split_path, {"train": treino, "holdout": holdout},
        {"book-t": "train-item", "book-h": "holdout-item"})),
        encoding="utf-8")

    def falso_treinar(**_kwargs):
        modelo.write_bytes(b"pesos")
        meta.write_text(json.dumps({"cer_validacao": 0.01}), encoding="utf-8")
        return True

    monkeypatch.setattr("core.linha_trainer.treinar", falso_treinar)
    monkeypatch.setattr("core.linha_trainer.modelo_utilizavel",
                        lambda *args: (False, "sem promoção"))
    monkeypatch.setattr("core.linha_trainer.avaliar", lambda *args: {
        "cer": 0.04, "wer": 0.08, "exatas": 1, "linhas": 1,
    })
    monkeypatch.setattr(ocr_training, "construir_modelo_linguagem",
                        lambda *args, **kwargs: tmp_path / "lexico.json")
    monkeypatch.setattr(ocr_training, "preparar_engines", lambda *args, **kwargs: [])

    resumo = ocr_training.treinar_pacote(
        pasta=treino, holdout=holdout, line_binding=binding,
        exigir_line_binding=True, destino=modelo, meta=meta,
        preparar_pesos=False)

    dados = json.loads(meta.read_text(encoding="utf-8"))
    assert dados["line_binding_required"] is True
    assert dados["line_binding_schema"] == "pyboxeditor.ocr-line-binding/v1"
    assert resumo.line_binding_sha256


def test_treino_com_proveniencia_valida_o_dataset_de_linhas(tmp_path, monkeypatch):
    from core import ocr_training

    modelo = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    treino = tmp_path / "treino"
    holdout = tmp_path / "holdout"
    (holdout / "images").mkdir(parents=True)
    Image.new("L", (80, 24), 255).save(holdout / "images" / "h.png")
    (holdout / "rec_gt.txt").write_text(
        "images/h.png\ttexto\n", encoding="utf-8")

    class Page:
        page_id = "book-p001"

    class Selection:
        corpus_sha256 = "corpus-hash"
        document_ids = ("book",)
        pages = (Page(),)

    chamadas = {}

    def falso_treinar(**kwargs):
        modelo.write_bytes(b"pesos")
        meta.write_text(json.dumps({"cer_validacao": 0.01}), encoding="utf-8")
        return True

    def falso_proveniencia(dataset, selecao):
        chamadas["proveniencia"] = (dataset, selecao)
        return {"schema": "pyboxeditor.ocr-line-holdout/v1",
                "dataset_sha256": "line-hash", "lines": 1,
                "page_ids": ["book-p001"]}

    monkeypatch.setattr("core.linha_trainer.treinar", falso_treinar)
    monkeypatch.setattr("core.linha_trainer.modelo_utilizavel",
                        lambda *args: (False, "sem promoção"))
    monkeypatch.setattr("core.linha_trainer.avaliar", lambda *args: {
        "cer": 0.04, "wer": 0.08, "exatas": 1, "linhas": 1,
    })
    monkeypatch.setattr(ocr_training, "construir_modelo_linguagem",
                        lambda *args, **kwargs: tmp_path / "lexico.json")
    monkeypatch.setattr(ocr_training, "preparar_engines", lambda *args, **kwargs: [])
    monkeypatch.setattr("core.ocr_holdout.carregar_selecao",
                        lambda caminho: Selection())
    monkeypatch.setattr("core.ocr_holdout.validar_proveniencia_de_linhas",
                        falso_proveniencia)

    ocr_training.treinar_pacote(
        pasta=treino, holdout=holdout,
        holdout_provenance=tmp_path / "selection.json",
        destino=modelo, meta=meta, preparar_pesos=False)

    assert chamadas["proveniencia"] == (holdout, chamadas["proveniencia"][1])
    dados = json.loads(meta.read_text(encoding="utf-8"))
    assert dados["holdout_line_dataset_sha256"] == "line-hash"
    assert dados["holdout_line_count"] == 1
    assert dados["holdout_source_pages"] == ["book-p001"]


def test_pacote_rejeita_regressao_no_holdout_anterior(tmp_path, monkeypatch):
    from core import ocr_training

    modelo = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    holdout = tmp_path / "holdout"
    (holdout / "images").mkdir(parents=True)
    Image.new("L", (80, 24), 255).save(holdout / "images" / "h_linha_00001.png")
    (holdout / "rec_gt.txt").write_text(
        "images/h_linha_00001.png\ttexto limpo\n", encoding="utf-8")
    modelo.write_bytes(b"peso-anterior")
    meta.write_text(json.dumps({"cer_validacao": 0.01}), encoding="utf-8")
    leituras = iter((0.04, 0.06))

    def falso_treinar(**kwargs):
        modelo.write_bytes(b"peso-novo")
        meta.write_text(json.dumps({"cer_validacao": 0.01}), encoding="utf-8")
        return True

    monkeypatch.setattr("core.linha_trainer.treinar", falso_treinar)
    monkeypatch.setattr("core.linha_trainer.modelo_utilizavel",
                        lambda *args: (True, "modelo de linha com 1,0% de CER"))
    monkeypatch.setattr("core.linha_trainer.avaliar", lambda *args: {
        "cer": next(leituras), "wer": 0.08, "exatas": 1, "linhas": 1,
    })
    monkeypatch.setattr(ocr_training, "construir_modelo_linguagem",
                        lambda *args, **kwargs: tmp_path / "lexico.json")
    monkeypatch.setattr(ocr_training, "preparar_engines", lambda *args, **kwargs: [])

    resumo = ocr_training.treinar_pacote(
        pasta=tmp_path / "dataset", holdout=holdout,
        destino=modelo, meta=meta, preparar_pesos=False)

    assert resumo.production_eligible is False
    assert "regress" in resumo.production_gate_reason.lower()


def test_manifesto_de_pesos_registra_decisao_do_portao(tmp_path, monkeypatch):
    from core import ocr_training

    modelo = tmp_path / "modelo.pth"
    manifest = tmp_path / "modelo.manifest.json"
    config = {}

    def falso_treinar(**kwargs):
        modelo.write_bytes(b"pesos")
        return True

    class ManifestoFalso:
        @classmethod
        def from_file(cls, caminho, **kwargs):
            config.update(kwargs["config"])
            return cls()

        def save(self, caminho):
            Path(caminho).write_text("{}", encoding="utf-8")

    monkeypatch.setattr("core.linha_trainer.treinar", falso_treinar)
    monkeypatch.setattr("core.linha_trainer.modelo_utilizavel",
                        lambda *args: (False, "CER alto"))
    monkeypatch.setattr(ocr_training, "construir_modelo_linguagem",
                        lambda *args, **kwargs: tmp_path / "lexico.json")
    monkeypatch.setattr(ocr_training, "preparar_engines", lambda *args, **kwargs: [])
    monkeypatch.setattr("core.ocr_phase7.WeightManifest", ManifestoFalso)

    resumo = ocr_training.treinar_pacote(
        pasta=tmp_path / "dataset", destino=modelo,
        meta=tmp_path / "modelo.json", manifest_path=manifest,
        dataset_version="v4", preparar_pesos=False)

    assert config["dataset_version"] == "v4"
    assert config["production_eligible"] is False
    assert config["production_gate_reason"] == "CER alto"
    assert resumo.weight_manifest == str(manifest)
    assert Path(resumo.state_path).exists()


def test_cli_de_treino_usa_o_pacote_integrado(monkeypatch, tmp_path):
    from scripts import treinar_ocr_linhas

    chamadas = {}
    dataset = tmp_path / "dataset"

    monkeypatch.setattr(treinar_ocr_linhas, "validar_dataset", lambda caminho: {
        "linhas": 4, "caracteres": 20, "vazias": 0, "ilegiveis": 0,
        "ausentes": 0, "malformadas": 0,
    })

    def falso_pacote(**kwargs):
        chamadas.update(kwargs)
        return SimpleNamespace(weight_manifest="", state_path="estado.json")

    monkeypatch.setattr(treinar_ocr_linhas, "treinar_pacote", falso_pacote)
    monkeypatch.setattr(sys, "argv", [
        "treinar_ocr_linhas.py", "--dataset", str(dataset), "--epocas", "2",
        "--batch-size", "3", "--paciencia", "4", "--semente", "17",
        "--lr", "0.0002", "--device", "cpu", "--novo",
        "--versao-dataset", "correcoes-v3", "--holdout", str(tmp_path / "holdout"),
        "--calibracao", str(tmp_path / "calibracao"),
        "--holdout-proveniencia", str(tmp_path / "holdout.selection.json"),
        "--dataset-proveniencia", str(tmp_path / "dataset-proveniencia.json"),
        "--exigir-proveniencia-dataset", "--split-manifest",
        str(tmp_path / "split.json"), "--exigir-split", "--line-binding",
        str(tmp_path / "line-binding.json"), "--exigir-line-binding",
    ])

    with pytest.raises(SystemExit) as encerramento:
        treinar_ocr_linhas.main()

    assert encerramento.value.code == 0
    assert chamadas["pasta"] == str(dataset)
    assert chamadas["epocas"] == 2
    assert chamadas["batch_size"] == 3
    assert chamadas["paciencia"] == 4
    assert chamadas["semente"] == 17
    assert chamadas["taxa_aprendizado"] == 0.0002
    assert chamadas["dispositivo"] == "cpu"
    assert chamadas["retomar"] is False
    assert chamadas["dataset_version"] == "correcoes-v3"
    assert chamadas["dataset_provenance"] == str(tmp_path / "dataset-proveniencia.json")
    assert chamadas["exigir_proveniencia_dataset"] is True
    assert chamadas["holdout"] == str(tmp_path / "holdout")
    assert chamadas["calibracao"] == str(tmp_path / "calibracao")
    assert chamadas["holdout_provenance"] == str(tmp_path / "holdout.selection.json")
    assert chamadas["split_manifest"] == str(tmp_path / "split.json")
    assert chamadas["exigir_split"] is True
    assert chamadas["line_binding"] == str(tmp_path / "line-binding.json")
    assert chamadas["exigir_line_binding"] is True


def test_cli_pode_exigir_o_portao_de_producao(monkeypatch, tmp_path):
    from scripts import treinar_ocr_linhas

    monkeypatch.setattr(treinar_ocr_linhas, "validar_dataset", lambda caminho: {
        "linhas": 1, "caracteres": 1, "vazias": 0, "ilegiveis": 0,
        "ausentes": 0, "malformadas": 0,
    })
    monkeypatch.setattr(
        treinar_ocr_linhas, "treinar_pacote",
        lambda **kwargs: SimpleNamespace(
            weight_manifest="", state_path="estado.json",
            production_eligible=False, production_gate_reason="CER alto"),
    )
    monkeypatch.setattr(sys, "argv", [
        "treinar_ocr_linhas.py", "--dataset", str(tmp_path / "dataset"),
        "--exigir-portao",
    ])

    with pytest.raises(SystemExit) as encerramento:
        treinar_ocr_linhas.main()

    assert encerramento.value.code == 2


def test_cli_de_avaliacao_exibe_o_portao_real(monkeypatch, tmp_path, capsys):
    from scripts import treinar_ocr_linhas

    monkeypatch.setattr(treinar_ocr_linhas, "validar_dataset", lambda caminho: {
        "linhas": 1, "caracteres": 1, "vazias": 0, "ilegiveis": 0,
        "ausentes": 0, "malformadas": 0,
    })
    monkeypatch.setattr(treinar_ocr_linhas, "avaliar", lambda *args: {
        "cer": 0.04, "wer": 0.08, "exatas": 9, "linhas": 10, "piores": [],
    })
    monkeypatch.setattr(treinar_ocr_linhas, "salvar_avaliacao", lambda *args: None)
    monkeypatch.setattr(treinar_ocr_linhas, "modelo_utilizavel",
                        lambda *args: (False, "peso e metadados desencontrados"))
    monkeypatch.setattr(sys, "argv", [
        "treinar_ocr_linhas.py", "--dataset", str(tmp_path / "dataset"),
        "--avaliar",
    ])

    treinar_ocr_linhas.main()

    saida = capsys.readouterr().out
    assert "CER=4.00%" in saida
    assert "desencontrados" in saida
def test_proveniencia_do_dataset_de_treino_exige_review_ocr14_verificado(tmp_path):
    import pytest
    from core.ocr_training import carregar_proveniencia_dataset

    caminho = tmp_path / "ocr14-reviewed.json"
    caminho.write_text(json.dumps({
        "schema": "pyboxeditor.ocr-corrections/v1",
        "name": "ocr14-reviewed",
        "metadata": {
            "source": "ocr14",
            "review_provenance": {"verified": True},
        },
    }), encoding="utf-8")

    resultado = carregar_proveniencia_dataset(caminho)

    assert resultado["verified"] is True
    assert resultado["source"] == "ocr14"
    assert len(resultado["sha256"]) == 64

    caminho.write_text(json.dumps({
        "schema": "pyboxeditor.ocr-corrections/v1",
        "metadata": {"source": "ocr14"},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="proveni"):
        carregar_proveniencia_dataset(caminho)
