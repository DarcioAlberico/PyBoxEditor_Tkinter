"""Executa o baseline de um engine sobre um manifesto de corpus."""

from __future__ import annotations

import argparse

from core.ocr_benchmark import salvar_relatorio
from core.ocr_corpus import executar_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="manifesto JSON do corpus")
    parser.add_argument("--engine", required=True, help="chave em page.predictions")
    parser.add_argument("-o", "--output", required=True, help="relatório JSON")
    parser.add_argument("--split", choices=("train", "validation", "test", "holdout", "unsplit"))
    parser.add_argument("--ignore-case", action="store_true")
    args = parser.parse_args()
    relatorio = executar_corpus(
        args.manifest, engine=args.engine, split=args.split,
        ignorar_maiusculas=args.ignore_case,
    )
    salvar_relatorio(args.output, relatorio)
    print(f"Benchmark concluído: {relatorio.pages} páginas")
    print(f"Relatório: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
