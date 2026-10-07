"""Executa o gate estrutural de release sobre um documento editorial JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.editorial_model import EditorialDocument
from core.editorial_quality_gate import validar_documento


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida um documento editorial completo")
    parser.add_argument("documento", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--exigir-resolvido", action="store_true",
                        help="recusa blocos ainda unresolved")
    parser.add_argument("--permitir-sem-proveniencia", action="store_true",
                        help="nao exige source_refs em paginas e blocos")
    args = parser.parse_args(argv)
    documento = EditorialDocument.load_json(args.documento)
    resultado = validar_documento(
        documento, exigir_resolvido=args.exigir_resolvido,
        exigir_proveniencia=not args.permitir_sem_proveniencia)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(resultado.to_dict(), ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(resultado.to_dict(), ensure_ascii=False))
    return 0 if resultado.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
