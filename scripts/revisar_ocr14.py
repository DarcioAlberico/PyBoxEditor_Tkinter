"""Confirma manualmente recortes em quarentena da OCR-14."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from core.ocr14_revisao import revisar_relatorio


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for bloco in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Confirma rotulos humanos para a quarentena OCR-14")
    parser.add_argument("relatorio", type=Path,
                        help="JSON emitido por erros_confiantes.py")
    parser.add_argument("rotulos", type=Path,
                        help="JSON mapa arquivo -> rotulo ou lista de revisoes")
    parser.add_argument("-o", "--output", type=Path, required=True,
                        help="artefato JSON revisado")
    parser.add_argument("--revisor", default="reviewer")
    parser.add_argument("--permitir-pendentes", action="store_true",
                        help="permite gerar revisao parcial explicitamente")
    return parser


def _ler_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    resultado = revisar_relatorio(
        _ler_json(args.relatorio), _ler_json(args.rotulos),
        revisor=args.revisor, exigir_todos=not args.permitir_pendentes)
    resultado["source_report"] = str(args.relatorio)
    resultado["source_report_sha256"] = _sha256(args.relatorio)
    resultado["source_labels"] = str(args.rotulos)
    resultado["source_labels_sha256"] = _sha256(args.rotulos)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporario = args.output.with_suffix(args.output.suffix + ".tmp")
    temporario.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    temporario.replace(args.output)
    print(json.dumps({"status": resultado["status"],
                      "reviewed": resultado["counts"]["reviewed"],
                      "pending": resultado["counts"]["pending"],
                      "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
