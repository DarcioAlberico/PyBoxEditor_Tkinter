"""Prepara uma fila de conferencia humana a partir de um plano de corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.corpus_revisao import preparar_fila_revisao  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plano", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    plano = json.loads(args.plano.read_text(encoding="utf-8"))
    fila = preparar_fila_revisao(plano)
    fila["source_plan"] = str(args.plano)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(fila, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "items": len(fila["items"]),
        "output": str(args.output),
        "status": "pending_review",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
