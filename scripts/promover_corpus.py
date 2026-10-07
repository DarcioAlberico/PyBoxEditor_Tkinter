"""Promove transcrições humanas revisadas para uma nova versão do corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from core.corpus_promocao import promover_revisoes, validar_revisoes_com_candidatos
from core.ocr_corpus import carregar_manifesto, salvar_manifesto


def _revisoes(dados: Any) -> list[dict[str, Any]]:
    valores = dados if isinstance(dados, list) else (
        dados.get("revisoes") if isinstance(dados, Mapping) else None)
    if not isinstance(valores, list) or not all(isinstance(item, Mapping) for item in valores):
        raise ValueError("JSON de revisões precisa conter uma lista de objetos")
    return [dict(item) for item in valores]


def _candidatos(dados: Any) -> list[dict[str, Any]]:
    valores = dados if isinstance(dados, list) else (
        dados.get("candidatos") if isinstance(dados, Mapping) else None)
    if not isinstance(valores, list) or not all(isinstance(item, Mapping) for item in valores):
        raise ValueError("JSON de candidatos precisa conter uma lista de objetos")
    return [dict(item) for item in valores]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifesto", type=Path, required=True)
    parser.add_argument("--revisoes", type=Path, required=True)
    parser.add_argument("--candidatos", type=Path, nargs="+",
                        help="filas de candidatos para conferir a proveniencia")
    parser.add_argument("--revisor", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    base = args.manifesto.resolve().parent
    if args.output.resolve().parent != base:
        raise SystemExit("--output precisa ficar na mesma pasta do manifesto")
    manifesto = carregar_manifesto(args.manifesto, validate_paths=False)
    revisoes = _revisoes(json.loads(args.revisoes.read_text(encoding="utf-8")))
    proveniencia = None
    if args.candidatos:
        candidatos = []
        for caminho in args.candidatos:
            candidatos.extend(_candidatos(
                json.loads(caminho.read_text(encoding="utf-8"))))
        proveniencia = validar_revisoes_com_candidatos(
            revisoes, candidatos, base_dir=base)
    promovido = promover_revisoes(
        manifesto, revisoes, base_dir=base, revisor=args.revisor)
    if proveniencia is not None:
        promovido.metadata = dict(promovido.metadata)
        promovido.metadata["promotion_provenance"] = {
            "schema": "pyboxeditor.ocr-promotion-provenance/v1",
            **proveniencia,
        }
    salvar_manifesto(promovido, args.output, base_dir=base)
    print(json.dumps({
        "pages": sum(len(documento.pages) for documento in promovido.documents),
        "promoted": len(revisoes),
        "output": str(args.output),
        "corpus_sha256": promovido.corpus_sha256,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
