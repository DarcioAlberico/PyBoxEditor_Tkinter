"""Valida o holdout real do corpus antes de qualquer treino ou promoção."""

import argparse
import json

from core.ocr_holdout import (selecionar_holdout,
                              validar_proveniencia_de_linhas)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Valida e materializa a seleção auditável do holdout do corpus"
    )
    parser.add_argument("manifesto", help="manifesto JSON do corpus")
    parser.add_argument(
        "--saida",
        default=None,
        help="JSON da seleção validada; sem este argumento imprime no terminal",
    )
    parser.add_argument(
        "--dataset-linhas",
        default=None,
        help="dataset de linhas cujo provenance.json será conferido contra o holdout",
    )
    args = parser.parse_args(argv)
    try:
        selecao = selecionar_holdout(args.manifesto)
    except (FileNotFoundError, ValueError) as erro:
        raise SystemExit(f"Holdout inválido: {erro}") from erro
    if args.saida:
        caminho = selecao.salvar(args.saida)
        print(f"Holdout validado: {caminho}")
    else:
        print(json.dumps(selecao.to_dict(), ensure_ascii=False, indent=2))
    if args.dataset_linhas:
        try:
            linhas = validar_proveniencia_de_linhas(args.dataset_linhas, selecao)
        except (FileNotFoundError, ValueError) as erro:
            raise SystemExit(f"Proveniência de linhas inválida: {erro}") from erro
        print(json.dumps({
            "line_dataset_sha256": linhas["dataset_sha256"],
            "lines": linhas["lines"],
            "page_ids": linhas["page_ids"],
        }, ensure_ascii=False))
    print(
        f"Páginas: {len(selecao.pages)} | "
        f"documentos: {len(selecao.document_ids)} | "
        f"corpus_sha256: {selecao.corpus_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
