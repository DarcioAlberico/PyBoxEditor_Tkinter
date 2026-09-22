"""Ferramentas operacionais da Fase 7: correções, splits, calibração e pesos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.editorial_model import EditorialDocument
from core.ocr_phase7 import (
    CalibrationObservation,
    CorrectionDataset,
    WeightManifest,
    calibrate_domains,
    split_corrections,
)


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preparação segura de treino OCR Fase 7")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    corrections = subparsers.add_parser("correcoes", help="extrai eventos de um documento editorial")
    corrections.add_argument("documento", type=Path)
    corrections.add_argument("-o", "--output", type=Path, required=True)
    corrections.add_argument("--nome", default="editorial-corrections")

    split = subparsers.add_parser("split", help="separa treino, validação, teste e holdout")
    split.add_argument("dataset", type=Path)
    split.add_argument("-o", "--output", type=Path, required=True)
    split.add_argument("--seed", type=int, default=42)

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
