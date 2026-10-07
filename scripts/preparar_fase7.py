"""Ferramentas operacionais da Fase 7: correções, splits, calibração e pesos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from core.editorial_model import EditorialDocument
from core.ocr_phase7 import (
    CalibrationObservation,
    CorrectionDataset,
    WeightManifest,
    calibrate_domains,
    sha256_file,
    split_corrections,
)
from core.ocr_holdout import selecionar_holdout


def _entradas_ocr14(relatorio: Any) -> list[dict[str, Any]]:
    """Achata os recortes revisados do relatório por página."""
    if isinstance(relatorio, list):
        return [dict(item) for item in relatorio]
    if not isinstance(relatorio, Mapping):
        raise ValueError("relatório OCR-14 inválido")
    status = relatorio.get("status")
    if status is not None and (
            str(status) != "reviewed" or relatorio.get("pending")):
        raise ValueError(
            "relatório OCR-14 não está revisado por completo")
    document_id = str(relatorio.get("pdf", "ocr14") or "ocr14")
    entradas = relatorio.get("entradas")
    if isinstance(entradas, list):
        resultado = [dict(item) for item in entradas]
        for item in resultado:
            item.setdefault("document_id", document_id)
        return resultado
    paginas = relatorio.get("paginas", {})
    if not isinstance(paginas, Mapping):
        raise ValueError("relatório OCR-14 sem páginas")
    resultado: list[dict[str, Any]] = []
    for numero, pagina in paginas.items():
        if not isinstance(pagina, Mapping):
            continue
        recortes = pagina.get("recortes", ())
        if not isinstance(recortes, list):
            continue
        for recorte in recortes:
            item = dict(recorte)
            item.setdefault("pagina", numero)
            item.setdefault("document_id", document_id)
            resultado.append(item)
    return resultado


def _validar_proveniencia_ocr14(relatorio: Any, caminho_revisado: Path, *,
                                exigir: bool) -> dict[str, Any]:
    """Confere os artefatos que deram origem a uma revisão OCR-14."""
    if not isinstance(relatorio, Mapping):
        if exigir:
            raise ValueError("relatório OCR-14 sem proveniência verificável")
        return {"verified": False, "reason": "metadata absent"}

    pares = (
        ("source_report", "source_report_sha256"),
        ("source_labels", "source_labels_sha256"),
    )
    presentes = [(caminho, sha)
                 for caminho, sha in pares
                 if relatorio.get(caminho) is not None
                 or relatorio.get(sha) is not None]
    if not presentes:
        if exigir:
            raise ValueError("relatório OCR-14 sem proveniência verificável")
        return {"verified": False, "reason": "metadata absent"}

    resultado: dict[str, Any] = {"verified": True}
    for campo_caminho, campo_sha in presentes:
        valor_caminho = relatorio.get(campo_caminho)
        esperado = str(relatorio.get(campo_sha, "")).lower()
        if not valor_caminho or len(esperado) != 64:
            raise ValueError(f"proveniência OCR-14 incompleta: {campo_caminho}")
        informado = Path(str(valor_caminho))
        candidatos = ([informado.resolve()] if informado.is_absolute() else [
            (Path.cwd() / informado).resolve(),
            (caminho_revisado.parent / informado).resolve(),
        ])
        arquivo = next((item for item in candidatos if item.is_file()), None)
        if arquivo is None:
            raise FileNotFoundError(
                f"arquivo de proveniência OCR-14 ausente: {valor_caminho}")
        atual = sha256_file(arquivo)
        if atual != esperado:
            raise ValueError(
                f"SHA-256 divergente em {campo_caminho}: "
                f"esperado {esperado}, encontrado {atual}")
        resultado[campo_caminho] = str(arquivo)
        resultado[campo_sha] = atual
    return resultado


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preparação segura de treino OCR Fase 7")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    corrections = subparsers.add_parser("correcoes", help="extrai eventos de um documento editorial")
    corrections.add_argument("documento", type=Path)
    corrections.add_argument("-o", "--output", type=Path, required=True)
    corrections.add_argument("--nome", default="editorial-corrections")

    ocr14 = subparsers.add_parser(
        "ocr14", help="importa recortes OCR-14 confirmados pelo revisor")
    ocr14.add_argument("relatorio", type=Path)
    ocr14.add_argument("-o", "--output", type=Path, required=True)
    ocr14.add_argument("--nome", default="ocr14-reviewed")
    ocr14.add_argument("--editor", default="reviewer")
    ocr14.add_argument("--base-dir", type=Path, default=None,
                       help="base para resolver os caminhos dos recortes")
    ocr14.add_argument("--exigir-arquivos", action="store_true",
                       help="recusa recortes ausentes e guarda seu SHA-256")
    ocr14.add_argument("--exigir-registros", action="store_true",
                       help="recusa relatório sem recortes confirmados")

    split = subparsers.add_parser("split", help="separa treino, validação, teste e holdout")
    ocr14.add_argument("--exigir-proveniencia", action="store_true",
                       help="exige e confere os hashes da quarentena e dos rótulos")

    split.add_argument("dataset", type=Path)
    split.add_argument("-o", "--output", type=Path, required=True)
    split.add_argument("--seed", type=int, default=42)

    holdout = subparsers.add_parser(
        "holdout", help="valida e materializa o holdout real do corpus")
    holdout.add_argument("manifesto", type=Path)
    holdout.add_argument("-o", "--output", type=Path, required=True)

    weights = subparsers.add_parser("pesos", help="cria manifesto e checksum de pesos")
    weights.add_argument("modelo", type=Path)
    weights.add_argument("-o", "--output", type=Path, required=True)
    weights.add_argument("--model-id", required=True)
    weights.add_argument("--pipeline-version", default="")
    weights.add_argument("--schema", default="pyboxeditor.ocr-weights/v1")

    calibration = subparsers.add_parser("calibrar", help="calibra observações por domínio")
    calibration.add_argument("observacoes", type=Path, help="JSON com domain, confidence e correct")
    calibration.add_argument("-o", "--output", type=Path, required=True)
    calibration.add_argument("--bins", type=int, default=15)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    if args.comando == "correcoes":
        documento = EditorialDocument.load_json(args.documento)
        dataset = CorrectionDataset.from_document(documento, name=args.nome)
        dataset.save(args.output)
        print(json.dumps({"records": len(dataset.records), "version": dataset.version,
                          "checksum": dataset.digest()}, ensure_ascii=False))
    elif args.comando == "ocr14":
        relatorio = json.loads(args.relatorio.read_text(encoding="utf-8"))
        proveniencia = _validar_proveniencia_ocr14(
            relatorio, args.relatorio, exigir=args.exigir_proveniencia)
        dataset = CorrectionDataset.from_ocr14(
            _entradas_ocr14(relatorio), name=args.nome, editor=args.editor,
            base_dir=args.base_dir, exigir_arquivos=args.exigir_arquivos,
            exigir_registros=args.exigir_registros)
        dataset.metadata["review_provenance"] = proveniencia
        dataset.save(args.output)
        print(json.dumps({"records": len(dataset.records), "version": dataset.version,
                          "checksum": dataset.digest(), "source": "ocr14"},
                         ensure_ascii=False))
    elif args.comando == "split":
        dataset = CorrectionDataset.load(args.dataset)
        resultado = split_corrections(dataset, seed=args.seed)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(resultado.to_dict(), ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        print(json.dumps({name: len(getattr(resultado, name))
                          for name in ("train", "validation", "test", "holdout", "synthetic")}))
    elif args.comando == "pesos":
        manifesto = WeightManifest.from_file(
            args.modelo, model_id=args.model_id, schema=args.schema,
            pipeline_version=args.pipeline_version,
        )
        manifesto.save(args.output)
        print(json.dumps(manifesto.to_dict(), ensure_ascii=False))
    elif args.comando == "holdout":
        try:
            selecao = selecionar_holdout(args.manifesto)
        except (FileNotFoundError, ValueError) as erro:
            raise SystemExit(f"Holdout inválido: {erro}") from erro
        selecao.salvar(args.output)
        print(json.dumps({
            "pages": len(selecao.pages),
            "documents": len(selecao.document_ids),
            "corpus_sha256": selecao.corpus_sha256,
            "output": str(args.output),
        }, ensure_ascii=False))
    else:
        observations = [CalibrationObservation(str(item["domain"]), item["confidence"], item["correct"])
                        for item in json.loads(args.observacoes.read_text(encoding="utf-8"))]
        report = calibrate_domains(observations, bins=args.bins)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        print(json.dumps({"domains": list(report.domains)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
