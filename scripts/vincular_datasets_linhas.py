"""Cria o vínculo humano entre grupos de ``rec_gt`` e um split da Fase 7.

Exemplo::

    python scripts/vincular_datasets_linhas.py split.json -o line-binding.json \
      --dataset train=training_data_linhas \
      --dataset holdout=training_data_linhas_holdout \
      --grupo livro-a=train-item --grupo livro-h=holdout-item
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.ocr_line_binding import bind_line_datasets


def _pares(valores: list[str], nome: str) -> dict[str, str]:
    resultado = {}
    for valor in valores:
        if "=" not in valor:
            raise ValueError(f"{nome} precisa estar no formato chave=valor: {valor}")
        chave, conteudo = valor.split("=", 1)
        chave, conteudo = chave.strip(), conteudo.strip()
        if not chave or not conteudo:
            raise ValueError(f"{nome} não pode ter chave ou valor vazio: {valor}")
        if chave in resultado:
            raise ValueError(f"{nome} duplicado: {chave}")
        resultado[chave] = conteudo
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split_manifest", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--dataset", action="append", default=[],
                        help="papel=caminho do dataset rec_gt")
    parser.add_argument("--grupo", action="append", default=[],
                        help="grupo_do_arquivo=id_do_item_do_split")
    args = parser.parse_args(argv)
    try:
        datasets = _pares(args.dataset, "--dataset")
        grupos = _pares(args.grupo, "--grupo")
        vinculo = bind_line_datasets(args.split_manifest, datasets, grupos)
    except (OSError, ValueError) as erro:
        raise SystemExit(str(erro)) from erro
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(vinculo, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"schema": vinculo["schema"],
                      "datasets": list(vinculo["datasets"]),
                      "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
