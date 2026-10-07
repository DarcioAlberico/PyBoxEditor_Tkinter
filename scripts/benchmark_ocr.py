"""Executa o benchmark de OCR a partir de um manifesto JSON."""

from __future__ import annotations

import argparse
from pathlib import Path

from core.ocr_benchmark import (AggregateMetrics, executar_manifesto,
                                falhas_de_dominio, salvar_relatorio)


def _percentual(valor: float | None) -> str:
    return "n/d" if valor is None else f"{valor * 100:.2f}%"


def _limite(valor: str) -> float:
    try:
        limite = float(valor)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use um valor entre 0 e 1") from exc
    if not 0.0 <= limite <= 1.0:
        raise argparse.ArgumentTypeError("use um valor entre 0 e 1")
    return limite


def _imprimir(relatorio: AggregateMetrics) -> None:
    print(f"Páginas: {relatorio.pages}")
    if relatorio.text:
        print(f"CER: {_percentual(relatorio.text.cer)} ({relatorio.text.erros}/{relatorio.text.total})")
    if relatorio.words:
        print(f"WER: {_percentual(relatorio.words.cer)} ({relatorio.words.erros}/{relatorio.words.total})")
    if relatorio.lines:
        print(f"Linhas: {_percentual(relatorio.lines.acuracia_exata)} exatas; "
              f"erro de sequência {_percentual(relatorio.lines.taxa_erro)}")
    if relatorio.paragraphs:
        print(f"Parágrafos: {_percentual(relatorio.paragraphs.acuracia_exata)} exatos; "
              f"erro de sequência {_percentual(relatorio.paragraphs.taxa_erro)}")
    if relatorio.boxes:
        print(f"Boxes: precisão {_percentual((relatorio.boxes.precisao or 0) / 100)}, "
              f"recall {_percentual((relatorio.boxes.recall or 0) / 100)}, "
              f"F1 {_percentual((relatorio.boxes.f1 or 0) / 100)}")
    if relatorio.layout:
        print(f"Layout: {_percentual((relatorio.layout.acuracia_tipos or 0) / 100)} tipos corretos")


    if relatorio.diagrams:
        print(f"Diagramas: {_percentual(relatorio.diagrams.acuracia_exata)} exatos; "
              f"legalidade {_percentual(relatorio.diagrams.acuracia_legal)}")
    if relatorio.notation:
        print(f"Notacao: {_percentual(relatorio.notation.acuracia_exata)} exata; "
              f"legalidade {_percentual(relatorio.notation.acuracia_legal)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="manifesto JSON do corpus")
    parser.add_argument("-o", "--output", type=Path, help="relatório JSON de saída")
    parser.add_argument("--ignore-case", action="store_true",
                        help="ignora maiúsculas/minúsculas no texto")
    parser.add_argument("--min-diagram-exact", type=_limite, default=None)
    parser.add_argument("--min-diagram-legal", type=_limite, default=None)
    parser.add_argument("--min-notation-exact", type=_limite, default=None)
    parser.add_argument("--min-notation-legal", type=_limite, default=None)
    parser.add_argument("--exigir-ordem-layout", action="store_true")
    args = parser.parse_args(argv)

    relatorio = executar_manifesto(args.manifest, ignorar_maiusculas=args.ignore_case)
    _imprimir(relatorio)
    if args.output:
        salvar_relatorio(args.output, relatorio)
        print(f"Relatório salvo em: {args.output}")
    falhas = falhas_de_dominio(
        relatorio,
        min_diagram_exact=args.min_diagram_exact,
        min_diagram_legal=args.min_diagram_legal,
        min_notation_exact=args.min_notation_exact,
        min_notation_legal=args.min_notation_legal,
        exigir_ordem_layout=args.exigir_ordem_layout,
    )
    if falhas:
        print("GATE SEMANTICO REPROVADO:")
        for falha in falhas:
            print(f"  {falha}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
