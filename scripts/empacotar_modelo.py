"""Cria um pacote verificável de pesos para distribuição."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from core.ocr_phase8 import ModelPackage


_ARTEFATOS_META = (
    ("dataset_provenance_path", "dataset_provenance", "dataset_provenance_sha256"),
    ("calibration_report", "calibration_report", "calibration_report_sha256"),
    ("split_manifest", "split_manifest", "split_manifest_sha256"),
    ("line_binding", "line_binding", "line_binding_sha256"),
    ("holdout_provenance", "holdout_provenance", ""),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for bloco in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _coletar_artefatos_meta(meta: Path) -> tuple[dict[str, Path], list[dict[str, str]]]:
    """Copia para o release as evidências referenciadas pelo treino.

    Os caminhos gravados no JSON de treino continuam sendo caminhos de
    proveniência externa. O pacote, porém, passa a carregar uma cópia
    verificável de cada evidência, sem fingir que os datasets de imagens
    inteiros são autocontidos no ZIP.
    """
    try:
        dados = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise ValueError(f"metadata do modelo invalido: {erro}") from erro
    if not isinstance(dados, dict):
        raise ValueError("metadata do modelo deve ser um objeto JSON")

    files: dict[str, Path] = {}
    manifestos: list[dict[str, str]] = []
    for campo, nome, campo_hash in _ARTEFATOS_META:
        referencia = str(dados.get(campo, "")).strip()
        if not referencia:
            continue
        origem = Path(referencia)
        if not origem.is_absolute():
            origem = (meta.parent / origem).resolve()
        if not origem.is_file():
            raise ValueError(f"artefato {campo} ausente: {origem}")
        atual = _sha256(origem)
        esperado = str(dados.get(campo_hash, "")).strip().lower() if campo_hash else ""
        if esperado and esperado != atual:
            raise ValueError(f"SHA-256 do artefato {campo} nao corresponde")
        pacote = f"metadata/artifacts/{nome}{origem.suffix or '.json'}"
        if pacote in files and files[pacote] != origem:
            raise ValueError(f"artefatos duplicados no pacote: {pacote}")
        files[pacote] = origem
        manifestos.append({
            "kind": nome,
            "source": str(origem),
            "path": pacote,
            "sha256": atual,
        })
    return files, manifestos


def _validar_proveniencia_dataset(meta: Path) -> str | None:
    try:
        dados = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        return f"metadata do modelo invÃ¡lido: {erro}"
    if dados.get("dataset_provenance_verified") is not True:
        return "dataset sem proveniÃªncia verificada"
    caminho = str(dados.get("dataset_provenance_path", ""))
    esperado = str(dados.get("dataset_provenance_sha256", "")).lower()
    if not caminho or len(esperado) != 64:
        return "metadata sem caminho ou SHA-256 da proveniÃªncia do dataset"
    arquivo = Path(caminho)
    if not arquivo.is_absolute():
        arquivo = (meta.parent / arquivo).resolve()
    if not arquivo.is_file():
        return f"proveniÃªncia do dataset ausente: {arquivo}"
    atual = _sha256(arquivo)
    if atual != esperado:
        return "SHA-256 da proveniÃªncia do dataset nÃ£o corresponde"
    return None


def _validar_rodada_corpus(caminho: Path, *, exigir_gate: bool) -> dict[str, object]:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise ValueError(f"rodada OCR invÃ¡lida: {erro}") from erro
    if not isinstance(dados, dict):
        raise ValueError("rodada OCR deve ser um objeto JSON")
    gate = dados.get("quality_gate")
    if exigir_gate and (not isinstance(gate, dict) or gate.get("enabled") is not True):
        raise ValueError("rodada OCR sem gate de qualidade habilitado")
    if exigir_gate and not isinstance(dados.get("semanticas"), dict):
        raise ValueError("rodada OCR sem mÃ©tricas semÃ¢nticas")
    if exigir_gate and gate.get("passed") is not True:
        falhas = "; ".join(str(item) for item in gate.get("failures", ()))
        raise ValueError("gate da rodada OCR reprovado" + (f": {falhas}" if falhas else ""))
    return {
        "sha256": _sha256(caminho),
        "gate_enabled": bool(isinstance(gate, dict) and gate.get("enabled")),
        "gate_passed": bool(isinstance(gate, dict) and gate.get("passed")),
    }


def _validar_gate_editorial(caminho: Path, *, exigir_gate: bool) -> dict[str, object]:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise ValueError(f"gate editorial invÃ¡lido: {erro}") from erro
    if not isinstance(dados, dict):
        raise ValueError("gate editorial deve ser um objeto JSON")
    if exigir_gate and dados.get("schema") != "pyboxeditor.editorial-quality/v1":
        raise ValueError("schema do gate editorial invÃ¡lido")
    if exigir_gate and dados.get("valid") is not True:
        erros = "; ".join(str(item) for item in dados.get("errors", ()))
        raise ValueError("gate editorial reprovado" + (f": {erros}" if erros else ""))
    return {"sha256": _sha256(caminho), "valid": dados.get("valid") is True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Empacota pesos OCR com checksums")
    parser.add_argument("modelo", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--pipeline-version", default="")
    parser.add_argument("--config", type=Path, action="append", default=[])
    parser.add_argument("--meta", type=Path, default=None,
                        help="JSON de metadados produzido pelo treino")
    parser.add_argument("--manifesto-pesos", type=Path, default=None,
                        help="manifesto WeightManifest correspondente ao peso")
    parser.add_argument("--exigir-portao", action="store_true",
                        help="so cria pacote se o modelo passar o portao de producao")
    parser.add_argument("--exigir-proveniencia-dataset", action="store_true",
                        help="exige proveniencia verificavel do dataset de treino")
    parser.add_argument("--rodada-corpus", type=Path, default=None,
                        help="relatorio JSON da rodada OCR usada no release")
    parser.add_argument("--exigir-gate-corpus", action="store_true",
                        help="exige gate de qualidade aprovado na rodada OCR")
    parser.add_argument("--gate-editorial", type=Path, default=None,
                        help="relatorio JSON do gate estrutural editorial")
    parser.add_argument("--exigir-gate-editorial", action="store_true",
                        help="exige gate estrutural editorial aprovado")
    args = parser.parse_args(argv)
    files = {f"weights/{args.modelo.name}": args.modelo}
    files.update({path.name: path for path in args.config})
    if args.meta is not None:
        files["metadata/model.json"] = args.meta
    release_artifacts: list[dict[str, str]] = []
    if args.meta is not None:
        try:
            artifacts, release_artifacts = _coletar_artefatos_meta(args.meta)
        except (OSError, ValueError) as erro:
            print(json.dumps({"valid": False, "errors": [str(erro)]},
                             ensure_ascii=False))
            return 2
        files.update(artifacts)
    if args.manifesto_pesos is not None:
        files["manifests/weights.json"] = args.manifesto_pesos
        from core.ocr_phase7 import WeightManifest
        try:
            manifesto = WeightManifest.load(args.manifesto_pesos)
        except (OSError, KeyError, TypeError, ValueError) as erro:
            print(json.dumps({"valid": False,
                              "errors": [f"manifesto de pesos invalido: {erro}"]},
                             ensure_ascii=False))
            return 2
        erros_manifesto = []
        if manifesto.model_id != args.model_id:
            erros_manifesto.append("model_id do manifesto nao corresponde ao pacote")
        if args.pipeline_version and manifesto.pipeline_version != args.pipeline_version:
            erros_manifesto.append("pipeline_version do manifesto nao corresponde ao pacote")
        if not manifesto.verify(args.modelo):
            erros_manifesto.append("checksum do manifesto nao corresponde ao peso")
        if erros_manifesto:
            print(json.dumps({"valid": False, "errors": erros_manifesto},
                             ensure_ascii=False))
            return 2
    if args.exigir_portao:
        if args.meta is None:
            print(json.dumps({"valid": False,
                              "errors": ["--exigir-portao requer --meta"]},
                             ensure_ascii=False))
            return 2
        from core.linha_trainer import modelo_utilizavel
        elegivel, motivo = modelo_utilizavel(
            args.meta, args.modelo, exigir_holdout=True)
        if not elegivel:
            print(json.dumps({"valid": False, "errors": [motivo]},
                             ensure_ascii=False))
            return 2
    if args.exigir_proveniencia_dataset:
        if args.meta is None:
            print(json.dumps({"valid": False,
                              "errors": ["--exigir-proveniencia-dataset requer --meta"]},
                             ensure_ascii=False))
            return 2
        erro_proveniencia = _validar_proveniencia_dataset(args.meta)
        if erro_proveniencia:
            print(json.dumps({"valid": False, "errors": [erro_proveniencia]},
                             ensure_ascii=False))
            return 2
    rodada_corpus = None
    if args.rodada_corpus is not None:
        try:
            rodada_corpus = _validar_rodada_corpus(
                args.rodada_corpus, exigir_gate=args.exigir_gate_corpus)
        except (OSError, ValueError) as erro:
            print(json.dumps({"valid": False, "errors": [str(erro)]},
                             ensure_ascii=False))
            return 2
        files["metadata/ocr_round.json"] = args.rodada_corpus
    elif args.exigir_gate_corpus:
        print(json.dumps({"valid": False,
                          "errors": ["--exigir-gate-corpus requer --rodada-corpus"]},
                         ensure_ascii=False))
        return 2
    gate_editorial = None
    if args.gate_editorial is not None:
        try:
            gate_editorial = _validar_gate_editorial(
                args.gate_editorial, exigir_gate=args.exigir_gate_editorial)
        except (OSError, ValueError) as erro:
            print(json.dumps({"valid": False, "errors": [str(erro)]},
                             ensure_ascii=False))
            return 2
        files["metadata/editorial_quality.json"] = args.gate_editorial
    elif args.exigir_gate_editorial:
        print(json.dumps({"valid": False,
                          "errors": ["--exigir-gate-editorial requer --gate-editorial"]},
                         ensure_ascii=False))
        return 2
    metadata = {
        "model_sha256": _sha256(args.modelo),
        "model_metadata_sha256": _sha256(args.meta) if args.meta else "",
        "weight_manifest_sha256": (_sha256(args.manifesto_pesos)
                                    if args.manifesto_pesos else ""),
        "production_gate_required": bool(args.exigir_portao),
        "dataset_provenance_required": bool(args.exigir_proveniencia_dataset),
        "ocr_round_sha256": (rodada_corpus["sha256"] if rodada_corpus else ""),
        "ocr_round_gate_passed": (rodada_corpus["gate_passed"] if rodada_corpus else False),
        "editorial_quality_sha256": (gate_editorial["sha256"] if gate_editorial else ""),
        "editorial_quality_passed": (gate_editorial["valid"] if gate_editorial else False),
        "release_artifacts": release_artifacts,
    }
    destino = ModelPackage.create(
        args.output, files, model_id=args.model_id,
        pipeline_version=args.pipeline_version,
        metadata=metadata,
    )
    verificacao = ModelPackage.verify(destino)
    print(json.dumps({"package": str(destino), "valid": verificacao.valid,
                      "errors": list(verificacao.errors)}, ensure_ascii=False))
    return 0 if verificacao.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
