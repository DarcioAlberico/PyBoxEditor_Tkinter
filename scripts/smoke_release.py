"""Smoke test estático do wheel de release."""

from __future__ import annotations

import argparse
import json

from core.ocr_phase8 import smoke_test_installation, smoke_test_wheel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida conteúdo mínimo de um wheel")
    parser.add_argument("wheel")
    parser.add_argument("--install", action="store_true",
                        help="instala em venv temporário e importa os módulos")
    args = parser.parse_args(argv)
    smoke = smoke_test_installation if args.install else smoke_test_wheel
    report = smoke(args.wheel, required_modules=(
        "core.editorial_model", "core.ocr_phase7", "core.ocr_phase8",
    ))
    print(json.dumps({"valid": report.valid, "errors": list(report.errors)},
                     ensure_ascii=False))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
