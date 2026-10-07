from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from core.ocr_phase7 import CorpusItem, split_corpus
from core.ocr_line_binding import bind_line_datasets, load_line_binding


def _dataset(root: Path, group: str) -> Path:
    (root / "images").mkdir(parents=True)
    Image.new("L", (80, 24), 255).save(
        root / "images" / f"{group}_linha_00001.png")
    (root / "rec_gt.txt").write_text(
        f"images/{group}_linha_00001.png\ttexto\n", encoding="utf-8")
    return root


def _split(tmp_path: Path) -> Path:
    split = split_corpus([
        CorpusItem("train-item", "doc-t", "book-t", "editor-t", "source-t",
                   "single-column", "body"),
        CorpusItem("holdout-item", "doc-h", "book-h", "editor-h", "source-h",
                   "two-column", "body", holdout=True),
    ], validation_fraction=0, test_fraction=0)
    path = tmp_path / "split.json"
    path.write_text(json.dumps(split.to_dict()), encoding="utf-8")
    return path


def test_vinculo_de_linhas_exige_mapa_e_valida_fingerprint(tmp_path):
    split = _split(tmp_path)
    treino = _dataset(tmp_path / "treino", "book-t")
    holdout = _dataset(tmp_path / "holdout", "book-h")

    vinculo = bind_line_datasets(
        split, {"train": treino, "holdout": holdout},
        {"book-t": "train-item", "book-h": "holdout-item"})
    path = tmp_path / "line-binding.json"
    path.write_text(json.dumps(vinculo), encoding="utf-8")

    carregado = load_line_binding(path, expected_datasets={
        "train": treino, "holdout": holdout,
    }, require_holdout=True)

    assert carregado["schema"] == "pyboxeditor.ocr-line-binding/v1"
    assert carregado["datasets"]["train"]["groups"] == ["book-t"]


def test_vinculo_rejeita_grupo_sem_item_do_split(tmp_path):
    split = _split(tmp_path)
    treino = _dataset(tmp_path / "treino", "desconhecido")

    with pytest.raises(ValueError, match="grupo.*split"):
        bind_line_datasets(split, {"train": treino}, {"desconhecido": "x"})


def test_carregamento_rejeita_imagem_alterada(tmp_path):
    split = _split(tmp_path)
    treino = _dataset(tmp_path / "treino", "book-t")
    holdout = _dataset(tmp_path / "holdout", "book-h")
    path = tmp_path / "line-binding.json"
    path.write_text(json.dumps(bind_line_datasets(
        split, {"train": treino, "holdout": holdout},
        {"book-t": "train-item", "book-h": "holdout-item"})),
        encoding="utf-8")

    (treino / "images" / "book-t_linha_00001.png").write_bytes(b"alterada")

    with pytest.raises(ValueError, match="fingerprint"):
        load_line_binding(path, expected_datasets={
            "train": treino, "holdout": holdout,
        })


def test_cli_cria_vinculo_com_mapa_explicito(tmp_path):
    from scripts import vincular_datasets_linhas

    split = _split(tmp_path)
    treino = _dataset(tmp_path / "treino", "book-t")
    holdout = _dataset(tmp_path / "holdout", "book-h")
    saida = tmp_path / "line-binding.json"

    assert vincular_datasets_linhas.main([
        str(split), "-o", str(saida),
        "--dataset", f"train={treino}",
        "--dataset", f"holdout={holdout}",
        "--grupo", "book-t=train-item",
        "--grupo", "book-h=holdout-item",
    ]) == 0
    assert json.loads(saida.read_text(encoding="utf-8"))["schema"] == (
        "pyboxeditor.ocr-line-binding/v1")


def test_portao_de_producao_revalida_vinculo_de_linhas(tmp_path):
    split = _split(tmp_path)
    treino = _dataset(tmp_path / "treino", "book-t")
    holdout = _dataset(tmp_path / "holdout", "book-h")
    binding = tmp_path / "line-binding.json"
    binding.write_text(json.dumps(bind_line_datasets(
        split, {"train": treino, "holdout": holdout},
        {"book-t": "train-item", "book-h": "holdout-item"})),
        encoding="utf-8")
    pesos = tmp_path / "modelo.pth"
    meta = tmp_path / "modelo.json"
    pesos.write_bytes(b"pesos")
    meta.write_text(json.dumps({
        "cer_validacao": 0.01,
        "model_sha256": hashlib.sha256(b"pesos").hexdigest(),
        "line_binding_required": True,
        "line_binding": str(binding),
        "line_binding_sha256": hashlib.sha256(binding.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    (holdout / "images" / "book-h_linha_00001.png").write_bytes(b"alterada")

    from core.linha_trainer import modelo_utilizavel
    utilizavel, motivo = modelo_utilizavel(meta, pesos)

    assert utilizavel is False
    assert "vínculo" in motivo.lower()
