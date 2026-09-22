"""Cria um pacote verificável de pesos para distribuição."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.ocr_phase8 import ModelPackage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Empacota pesos OCR com checksums")
    parser.add_argument("modelo", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--pipeline-version", default="")
    parser.add_argument("--config", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    files = {f"weights/{args.modelo.name}": args.modelo}
    files.update({path.name: path for path in args.config})
    destino = ModelPackage.create(
        args.output, files, model_id=args.model_id,
        pipeline_version=args.pipeline_version,
    )
    verificacao = ModelPackage.verify(destino)
    print(json.dumps({"package": str(destino), "valid": verificacao.valid,
                      "errors": list(verificacao.errors)}, ensure_ascii=False))
    return 0 if verificacao.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
