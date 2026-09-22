"""Calcula e grava o hash de um manifesto de corpus já preenchido."""

from __future__ import annotations

import argparse
from pathlib import Path

from core.ocr_corpus import carregar_manifesto, salvar_manifesto


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="manifesto JSON a congelar")
    parser.add_argument("--require-files", action="store_true")
    args = parser.parse_args()
    manifesto = carregar_manifesto(args.manifest, validate_paths=False)
    salvar_manifesto(manifesto, args.manifest, base_dir=Path(args.manifest).parent)
    if args.require_files:
        carregar_manifesto(args.manifest, validate_paths=True, require_files=True)
    print(f"Corpus congelado: {args.manifest}")
    print(f"SHA-256: {manifesto.corpus_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
