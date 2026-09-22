"""Cria e valida um manifesto de benchmark por pares de JSON.

Estrutura esperada:

    referencias/p030.json
    predicoes/p030.json

Uso:
    python scripts/criar_manifesto_benchmark.py referencias predicoes -o benchmark.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _arquivos(pasta: Path) -> dict[str, Path]:
    return {arquivo.stem: arquivo for arquivo in sorted(pasta.glob("*.json"))}


def _hash_corpus(itens: list[dict], base: Path) -> str:
    digest = hashlib.sha256(b"pyboxeditor-ocr-corpus-v1\0")
    for item in itens:
        for chave in ("id", "reference", "prediction"):
            digest.update(str(item[chave]).encode("utf-8") + b"\0")
        for chave in ("reference", "prediction"):
            digest.update((base / item[chave]).read_bytes())
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("referencias", type=Path)
    parser.add_argument("predicoes", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--nome", default="ocr-corpus")
    args = parser.parse_args()
    if not args.referencias.is_dir() or not args.predicoes.is_dir():
        parser.error("referencias e predicoes precisam ser pastas existentes")
    referencias = _arquivos(args.referencias)
    predicoes = _arquivos(args.predicoes)
    faltantes = sorted(set(referencias) - set(predicoes))
    extras = sorted(set(predicoes) - set(referencias))
    if faltantes or extras:
        if faltantes:
            print("Predições ausentes: " + ", ".join(faltantes))
        if extras:
            print("Predições sem referência: " + ", ".join(extras))
        return 2
    base = args.output.parent.resolve()
    itens = []
    for stem in sorted(referencias):
        referencia = referencias[stem].resolve()
        predicao = predicoes[stem].resolve()
        try:
            ref_rel = referencia.relative_to(base)
            pred_rel = predicao.relative_to(base)
        except ValueError as erro:
            raise SystemExit(
                "O arquivo de saída precisa ficar em uma pasta ancestral "
                "das referências e previsões") from erro
        itens.append({"id": stem, "reference": str(ref_rel),
                      "prediction": str(pred_rel)})
    manifesto = {"schema": "pyboxeditor.ocr-benchmark/v1",
                 "name": args.nome, "pages": itens}
    manifesto["corpus_sha256"] = _hash_corpus(itens, base)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(f"Manifesto criado: {args.output} ({len(itens)} páginas, "
          f"sha256={manifesto['corpus_sha256']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
