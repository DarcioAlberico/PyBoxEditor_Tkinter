"""Valida manifesto de corpus e imprime a divisão por documento."""

from __future__ import annotations

import argparse

from core.ocr_corpus import carregar_manifesto


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="manifesto JSON do corpus")
    parser.add_argument("--require-files", action="store_true")
    args = parser.parse_args()
    manifesto = carregar_manifesto(args.manifest, validate_paths=True,
                                   require_files=args.require_files)
    avisos = manifesto.validate()
    paginas = sum(len(document.pages) for document in manifesto.documents)
    print(f"Corpus: {manifesto.name}")
    print(f"Documentos: {len(manifesto.documents)} | páginas: {paginas}")
    for documento in manifesto.documents:
        print(f"- {documento.id}: {documento.split}, {len(documento.pages)} páginas")
    if avisos:
        print(f"Avisos: {len(avisos)}")
        for aviso in avisos:
            print(f"  - {aviso}")
    print(f"SHA-256: {manifesto.corpus_sha256 or '(não calculado)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
