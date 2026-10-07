"""Planeja pÃ¡ginas para ampliar o corpus sem promover palpites a ground truth.

    python scripts/planejar_corpus.py --rodada benchmarks/rodadas/ultima.json \
        --candidatos benchmarks/candidatos_layout.json -o benchmarks/plano.json

O arquivo de candidatos Ã© produzido por uma inspeÃ§Ã£o preliminar de layout e
pode conter apenas famÃ­lias previstas. A referÃªncia humana e a inclusÃ£o no
manifesto oficial continuam sendo passos separados.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from core.corpus_planejamento import planejar_amostragem


def _lista(dados: Any, chave: str) -> list[dict[str, Any]]:
    if isinstance(dados, list):
        valores = dados
    elif isinstance(dados, Mapping):
        valores = dados.get(chave)
    else:
        valores = None
    if not isinstance(valores, list):
        raise ValueError(f"JSON precisa conter uma lista em {chave!r}")
    if not all(isinstance(item, Mapping) for item in valores):
        raise ValueError(f"itens de {chave!r} precisam ser objetos JSON")
    return [dict(item) for item in valores]


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rodada", type=Path, required=True,
                        help="rodada medida, com páginas e famílias observadas")
    parser.add_argument("--candidatos", type=Path, nargs="+", required=True,
                        help="JSON de páginas preliminares, ainda não revisadas")
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--minimo", type=int, default=3,
                        help="piso de páginas por família em cada livro")
    parser.add_argument("--limite", type=int, default=None,
                        help="máximo de candidatos selecionados")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    rodada = json.loads(args.rodada.read_text(encoding="utf-8"))
    candidatos: list[dict[str, Any]] = []
    for caminho in args.candidatos:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        candidatos.extend(_lista(dados, "candidatos"))
    if not isinstance(rodada, Mapping):
        raise ValueError("rodada inválida")
    plano = planejar_amostragem(
        _lista(rodada, "paginas"), candidatos,
        minimo=args.minimo, limite=args.limite)
    documento = {
        "schema": "pyboxeditor.ocr-corpus-plan/v1",
        "rodada": str(args.rodada),
        "candidatos": [str(caminho) for caminho in args.candidatos],
        "plan": plano,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(documento, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    print(json.dumps({"selecionados": len(plano["selecionados"]),
                      "livros_com_deficit": len(plano["faltando"]),
                      "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
