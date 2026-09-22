"""A fila de suspeitas de páginas reais, para conferir a régua contra o impresso.

    python scripts/fila_de_suspeitas.py "PDF/.../livro.pdf" --paginas 30
    python scripts/fila_de_suspeitas.py livro.pdf --paginas 34 47 --limite 4

Lê as páginas pedidas com o leitor de produção pela fachada editorial
(`core.editorial_legacy.pipeline_de_producao` — o mesmo caminho do menu
"Documento editorial") e imprime a fila de revisão de cada uma: os blocos
que entraram, por que entraram (em frase), e as linhas suspeitas com a
leitura da cadeia própria e a do motor. Com `--referencia`, marca cada linha
suspeita que **não** está na referência humana (`pNNN.txt`, ver
`preview_ocr/referencia/LEIA-ME.txt`) como acerto da régua — e conta, do
lado de lá, as linhas erradas que a régua deixou passar. É o instrumento do
aceite do item 2 da lista de `docs/REVISAO_MODOS_OCR.md`: "a fila contém os
resíduos e mais nada além de N por página". Só o interpretador do `.venv`
tem o torch que o modelo pede.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.editorial_legacy import OpcoesDeLeitura, pipeline_de_producao  # noqa: E402
from core.editorial_pipeline import DocumentSource, ProcessOptions  # noqa: E402
from core.editorial_review import build_review_queue  # noqa: E402
from core.ocr_ab import normalizar_tipografia  # noqa: E402


def _na_referencia(texto: str, referencia: str) -> bool:
    """A linha está na referência como está (ignorando a tipografia que o
    A/B também ignora e as quebras de linha)?"""
    alvo = " ".join(normalizar_tipografia(texto).split())
    # Inteira, e não como prefixo: `35.♔h3 1` está dentro de `35.♔h3 1–0`.
    return bool(alvo) and f" {alvo} " in f" {referencia} "


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--paginas", nargs="+", type=int, default=[30],
                        help="páginas visíveis, começando em 1")
    parser.add_argument("--idioma", default="en")
    parser.add_argument("--limite", type=int, default=0,
                        help="teto de itens por página (0 = todos)")
    parser.add_argument("--referencia", type=Path, default=None,
                        help="pasta com pNNN.txt para conferir as linhas suspeitas")
    parser.add_argument("--saida", type=Path, default=None,
                        help="grava a fila em JSON")
    args = parser.parse_args()
    if not args.pdf.exists():
        raise FileNotFoundError(args.pdf)

    from core.services.learning_service import LearningService
    from core.services.ocr_service import OCRService

    pipeline, extrator = pipeline_de_producao(
        LearningService(), OCRService(),
        OpcoesDeLeitura(idioma=args.idioma, diagramas="render"))
    documento = pipeline.process(
        DocumentSource.from_path(args.pdf),
        ProcessOptions(language=args.idioma, use_cache=False,
                       page_indices=tuple(n - 1 for n in args.paginas)))
    fila = build_review_queue(documento, limite_por_pagina=args.limite or None)
    inteira = build_review_queue(documento)

    resumo = {}
    for numero in args.paginas:
        referencia = ""
        if args.referencia is not None:
            caminho = args.referencia / f"p{numero:03d}.txt"
            if caminho.exists():
                referencia = " ".join(normalizar_tipografia(
                    caminho.read_text(encoding="utf-8")).split())
        pagina = next(p for p in documento.pages if p.page_index == numero - 1)
        itens = fila.filter(page_index=numero - 1).items
        todos = inteira.filter(page_index=numero - 1).items
        blocos = len(pagina.blocks)
        print(f"\n=== página {numero}: {len(itens)} de {blocos} blocos na fila"
              f"{'' if len(todos) == len(itens) else f' (de {len(todos)} suspeitos)'} ===")
        acertos = falsos = 0
        suspeitas_ids = set()
        for item in itens:
            print(f"[{item.severity:3d}] {item.kind:10s} conf={item.confidence:.2f} "
                  f"{item.status}")
            for motivo in item.motivos:
                print(f"       • {motivo}")
            for linha in item.linhas_suspeitas:
                suspeitas_ids.add(linha.evidence_id)
                veredito = ""
                if referencia:
                    certa = _na_referencia(linha.texto, referencia)
                    veredito = "  [linha CERTA na referência]" if certa else "  [erro real]"
                    acertos += 0 if certa else 1
                    falsos += 1 if certa else 0
                print(f"       ~ {linha.texto!r}{veredito}")
                print(f"           cadeia: {linha.ancora!r}")
                print(f"           motor : {linha.motor!r}")
                for motivo in linha.motivos:
                    print(f"           → {motivo}")
        escapadas = []
        if referencia:
            for block in pagina.blocks:
                for meta in block.metadata.get("linhas", ()):
                    if meta["evidence_id"] in suspeitas_ids or not meta["texto"].strip():
                        continue
                    if not _na_referencia(meta["texto"], referencia):
                        escapadas.append(meta["texto"])
            print(f"\n  régua: {acertos} linha(s) suspeita(s) com erro real, {falsos} "
                  f"falso(s) positivo(s); {len(escapadas)} linha(s) erradas fora da fila:")
            for texto in escapadas:
                print(f"    - {texto!r}")
        resumo[numero] = {"blocos": blocos, "na_fila": len(itens), "suspeitos": len(todos),
                          "erros_reais": acertos, "falsos_positivos": falsos,
                          "escapadas": escapadas,
                          "itens": [item.to_dict() for item in itens]}
    if args.saida is not None:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(json.dumps(resumo, ensure_ascii=False, indent=1) + "\n",
                              encoding="utf-8")
        print(f"\nfila gravada em {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
