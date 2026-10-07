"""Vinculo explicito entre splits de corpus e datasets ``rec_gt.txt``.

Um nome de arquivo nao prova de qual documento veio uma linha. Este modulo
exige um mapa fornecido pelo revisor e valida, em cada uso, os fingerprints,
grupos e o manifesto de split. Nenhuma origem e inferida pelo conteudo OCR.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from core.ocr_phase7 import SPLIT_SCHEMA, load_split_manifest


LINE_BINDING_SCHEMA = "pyboxeditor.ocr-line-binding/v1"
_ROLE_TO_SPLIT = {
    "train": "train", "validation": "validation", "test": "test",
    "holdout": "holdout", "calibration": "test",
}


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dataset_info(path: str | Path) -> tuple[str, list[str]]:
    from core.linha_trainer import grupos_de_linhas, fingerprint_dataset

    alvo = Path(path).resolve()
    return fingerprint_dataset(alvo), list(grupos_de_linhas(alvo))


def _split_items(split) -> dict[str, str]:
    resultado = {}
    for split_name in ("train", "validation", "test", "holdout"):
        for item in getattr(split, split_name):
            resultado[str(item.id)] = split_name
    return resultado


def bind_line_datasets(split_manifest: str | Path,
                       datasets: Mapping[str, str | Path],
                       group_to_item: Mapping[str, str]) -> dict[str, Any]:
    """Cria um vínculo assinado por conteúdo entre corpus e ``rec_gt``.

    ``group_to_item`` é a confirmação humana: cada prefixo de linha deve
    apontar para o ``CorpusItem.id`` correspondente no manifesto.
    """
    nomes_validos = set(_ROLE_TO_SPLIT)
    desconhecidos = set(datasets) - nomes_validos
    if desconhecidos:
        raise ValueError(f"datasets de linha desconhecidos: {sorted(desconhecidos)}")
    if not datasets:
        raise ValueError("vínculo de linhas precisa de ao menos um dataset")
    split_path = Path(split_manifest).resolve()
    split = load_split_manifest(split_path)
    ids = _split_items(split)
    caminhos = {str(nome): Path(path).resolve() for nome, path in datasets.items()}
    from core.linha_trainer import validar_datasets_disjuntos
    validar_datasets_disjuntos(caminhos)

    resultado_datasets: dict[str, dict[str, Any]] = {}
    grupos_usados: set[str] = set()
    for role, path in caminhos.items():
        fingerprint, groups = _dataset_info(path)
        grupo_item: dict[str, str] = {}
        esperado = _ROLE_TO_SPLIT[role]
        for group in groups:
            item_id = str(group_to_item.get(group, ""))
            if not item_id:
                raise ValueError(f"grupo de linha sem item do split: {group}")
            if item_id not in ids:
                raise ValueError(f"grupo de linha aponta para item inexistente no split: {item_id}")
            if ids[item_id] != esperado:
                raise ValueError(
                    f"grupo {group} pertence a {ids[item_id]}, não ao split {esperado}")
            grupo_item[group] = item_id
        grupos_usados.update(groups)
        resultado_datasets[role] = {
            "path": str(path), "fingerprint": fingerprint,
            "groups": groups, "group_to_item": grupo_item,
        }
    mapa = {str(key): str(value) for key, value in group_to_item.items()}
    extras = set(mapa) - grupos_usados
    if extras:
        raise ValueError(f"mapa contém grupos ausentes dos datasets: {sorted(extras)}")
    return {
        "schema": LINE_BINDING_SCHEMA,
        "split_schema": SPLIT_SCHEMA,
        "split_manifest": str(split_path),
        "split_manifest_sha256": _sha256(split_path),
        "datasets": resultado_datasets,
        "group_to_item": mapa,
    }


def load_line_binding(path: str | Path, *,
                      expected_datasets: Mapping[str, str | Path] | None = None,
                      require_holdout: bool = False) -> dict[str, Any]:
    """Carrega e revalida um vínculo de linhas antes do treino/release."""
    caminho = Path(path).resolve()
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise ValueError(f"vínculo de linhas ilegível: {erro}") from erro
    if not isinstance(dados, Mapping) or dados.get("schema") != LINE_BINDING_SCHEMA:
        raise ValueError(f"schema de vínculo incompatível: esperado {LINE_BINDING_SCHEMA}")
    split_path = Path(str(dados.get("split_manifest", ""))).resolve()
    expected_split_hash = str(dados.get("split_manifest_sha256", "")).lower()
    if not split_path.is_file() or len(expected_split_hash) != 64:
        raise ValueError("vínculo sem manifesto de split verificável")
    if _sha256(split_path) != expected_split_hash:
        raise ValueError("SHA-256 do manifesto de split não corresponde")
    raw_datasets = dados.get("datasets")
    raw_map = dados.get("group_to_item")
    if not isinstance(raw_datasets, Mapping) or not isinstance(raw_map, Mapping):
        raise ValueError("vínculo de linhas sem datasets ou mapa de grupos")
    dataset_paths = {}
    for role, info in raw_datasets.items():
        if not isinstance(info, Mapping):
            raise ValueError(f"dataset de linha inválido: {role}")
        dataset_paths[str(role)] = Path(str(info.get("path", ""))).resolve()
    if expected_datasets is not None:
        for role, expected in expected_datasets.items():
            if role not in dataset_paths:
                raise ValueError(f"vínculo não registra o dataset {role}")
            if dataset_paths[role] != Path(expected).resolve():
                raise ValueError(f"caminho do dataset {role} não corresponde ao vínculo")
    if require_holdout and "holdout" not in dataset_paths:
        raise ValueError("vínculo de linhas sem holdout")
    canonical = bind_line_datasets(split_path, dataset_paths, raw_map)
    if canonical["datasets"] != dict(raw_datasets):
        raise ValueError("fingerprint ou grupos do vínculo de linhas não correspondem")
    if canonical["group_to_item"] != {str(k): str(v) for k, v in raw_map.items()}:
        raise ValueError("mapa do vínculo de linhas não corresponde")
    return canonical
