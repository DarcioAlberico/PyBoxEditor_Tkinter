"""
Mede quanto custa aplicar eventos de revisão num documento editorial grande (RG-07/RG-08,
R-13 da revisão geral 2).

Existe porque `apply_review` copiava e validava o documento inteiro a cada evento, e
conferia o id repetido varrendo todos os eventos: reabrir um diário de 200 edições num
documento de 300 páginas × 12 blocos custava dezenas de segundos. A RG-08 tem de baixar
isso para menos de 2 s com o documento final **idêntico** — por isso o script fixa os ids
de evento e o relógio, e grava o documento reaberto em JSON, para comparar byte a byte o
de antes com o de depois.

Mede três coisas, com os mesmos 200 eventos:

- `interativo`: as 200 edições uma a uma (`ReviewSession.edit`), como o revisor as faz —
  cada uma é uma foto nova do documento, e isso a RG-08 não muda; fica como referência;
- `reabrir`: `ReviewSession.from_journal` sobre o diário com os 200 eventos — o que a
  janela e a ponte do editor fazem a cada abertura (o alvo da RG-08);
- `lote`: os 200 como um lote só (`aplicar_lote`) — o salvamento do editor.

    python scripts/medidas/medir_lote_de_revisao.py --saida preview_ocr/ab/lote-antes
    python scripts/medidas/medir_lote_de_revisao.py --paginas 30 --edicoes 20   # rápido

Grava `<saida>/documento_final.json` (o reaberto) e `<saida>/tempo.json`.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
import tempfile
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core import editorial_review  # noqa: E402
from core.editorial_model import (Decision, EditorialBlock, EditorialDocument,  # noqa: E402
                                  EditorialPage, SourceRef)
from core.editorial_review import Pedido, ReviewJournal, ReviewSession  # noqa: E402


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


def _alvos(doc: EditorialDocument, edicoes: int) -> list[str]:
    alvos = [b.id for page in doc.pages for b in page.blocks]
    passo = max(1, len(alvos) // max(1, edicoes))
    return [alvos[(i * passo) % len(alvos)] for i in range(edicoes)]


def medir(paginas: int, blocos: int, edicoes: int, pasta: str) -> tuple[dict, EditorialDocument]:
    _deterministico()
    diario = os.path.join(pasta, "doc.review.jsonl")
    sessao = ReviewSession(documento(paginas, blocos), journal=ReviewJournal(diario))
    escolhidos = _alvos(sessao.document, edicoes)
    inicio = time.perf_counter()
    for i, alvo in enumerate(escolhidos):
        sessao.edit(alvo, f"Corrigido na edição {i}.")
    interativo = time.perf_counter() - inicio

    inicio = time.perf_counter()
    reaberta = ReviewSession.from_journal(documento(paginas, blocos), ReviewJournal(diario))
    reabrir = time.perf_counter() - inicio

    pedidos = [Pedido(alvo, f"Corrigido no lote {i}.") for i, alvo in enumerate(escolhidos)]
    lote_sessao = ReviewSession(documento(paginas, blocos), journal=ReviewJournal())
    inicio = time.perf_counter()
    lote_sessao.aplicar_lote(pedidos)
    lote = time.perf_counter() - inicio
    return {"interativo": interativo, "reabrir": reabrir, "lote": lote}, reaberta.document


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--paginas", type=int, default=300)
    ap.add_argument("--blocos", type=int, default=12)
    ap.add_argument("--edicoes", type=int, default=200)
    ap.add_argument("--saida", default="")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as pasta:
        tempos, final = medir(args.paginas, args.blocos, args.edicoes, pasta)
    print(f"{args.edicoes} eventos em {args.paginas} páginas × {args.blocos} blocos: "
          + ", ".join(f"{nome} {segundos:.2f} s" for nome, segundos in tempos.items()))
    if args.saida:
        os.makedirs(args.saida, exist_ok=True)
        with open(os.path.join(args.saida, "documento_final.json"), "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(final.to_dict(), ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        with open(os.path.join(args.saida, "tempo.json"), "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({**{nome: round(s, 3) for nome, s in tempos.items()}, "paginas": args.paginas,
                                "blocos": args.blocos, "edicoes": args.edicoes}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
