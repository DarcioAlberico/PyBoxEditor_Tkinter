"""
Mede quanto custa aplicar edições de revisão num documento editorial grande (RG-07/RG-08,
R-13 da revisão geral 2).

Existe porque `apply_review` copia e valida o documento inteiro a cada evento, e confere
o id duplicado varrendo todos os eventos: o revisor mediu 54,6 s para 200 edições num
documento de 300 páginas × 12 blocos. A RG-08 tem de baixar isso para menos de 2 s com o
documento final **idêntico** — por isso o script fixa os ids de evento e o relógio, e
grava o documento final em JSON, para comparar byte a byte o de antes com o de depois.

    python scripts/medidas/medir_lote_de_revisao.py --saida preview_ocr/ab/lote-antes
    python scripts/medidas/medir_lote_de_revisao.py --paginas 30 --edicoes 20   # rápido

Grava `<saida>/documento_final.json` e `<saida>/tempo.json` (segundos, parâmetros).
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core import editorial_review  # noqa: E402
from core.editorial_model import (Decision, EditorialBlock, EditorialDocument,  # noqa: E402
                                  EditorialPage, SourceRef)
from core.editorial_review import ReviewJournal, ReviewSession  # noqa: E402


def documento(paginas: int = 300, blocos: int = 12) -> EditorialDocument:
    """`paginas` × `blocos` parágrafos automáticos, com ids e valores previsíveis."""
    pages = []
    for p in range(paginas):
        page_id = f"doc-p{p + 1:04d}"
        ref = SourceRef("doc", p)
        lista = [EditorialBlock(id=f"block-{page_id}-b{o:04d}", kind="paragraph", order=o,
                                source_refs=[ref],
                                decision=Decision(f"Texto da página {p + 1}, bloco {o}.", [], "automatic",
                                                  ["legacy_adapter"]))
                 for o in range(blocos)]
        pages.append(EditorialPage(page_id, p, [ref], lista, []))
    return EditorialDocument("doc", "Medida do lote de revisão", "pt", pages, source_sha256="0" * 64)


def _deterministico() -> None:
    """Ids de evento e relógio fixos: o documento final sai igual em toda rodada."""
    contador = itertools.count(1)
    editorial_review.uuid4 = lambda: uuid.UUID(int=next(contador))
    editorial_review._now = lambda: "2026-11-21T00:00:00+00:00"


def medir(paginas: int, blocos: int, edicoes: int) -> tuple[float, EditorialDocument]:
    _deterministico()
    sessao = ReviewSession(documento(paginas, blocos), journal=ReviewJournal())
    alvos = [b.id for page in sessao.document.pages for b in page.blocks]
    passo = max(1, len(alvos) // max(1, edicoes))
    escolhidos = [alvos[(i * passo) % len(alvos)] for i in range(edicoes)]
    inicio = time.perf_counter()
    for i, alvo in enumerate(escolhidos):
        sessao.edit(alvo, f"Corrigido na edição {i}.")
    return time.perf_counter() - inicio, sessao.document


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--paginas", type=int, default=300)
    ap.add_argument("--blocos", type=int, default=12)
    ap.add_argument("--edicoes", type=int, default=200)
    ap.add_argument("--saida", default="")
    args = ap.parse_args(argv)
    segundos, final = medir(args.paginas, args.blocos, args.edicoes)
    print(f"{args.edicoes} edições em {args.paginas} páginas × {args.blocos} blocos: {segundos:.2f} s")
    if args.saida:
        os.makedirs(args.saida, exist_ok=True)
        with open(os.path.join(args.saida, "documento_final.json"), "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(final.to_dict(), ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        with open(os.path.join(args.saida, "tempo.json"), "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"segundos": round(segundos, 3), "paginas": args.paginas,
                                "blocos": args.blocos, "edicoes": args.edicoes}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
