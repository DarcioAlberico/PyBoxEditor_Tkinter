"""Descobre páginas candidatas sem alterar o corpus oficial.

Exemplo::

    python scripts/descobrir_candidatos_corpus.py livro.pdf \
        --documento aagaard --paginas 30 31 32 -o candidatos.json

As páginas são lidas pelo mesmo ``core.livro.extrair`` usado na exportação.
O arquivo produzido é uma fila preliminar: ainda exige conferência humana e
nunca é aceito diretamente como referência.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core import familias_de_pagina, livro  # noqa: E402
from core.corpus_candidatos import candidato_de_pagina, sha256_arquivo  # noqa: E402


def _leitor_memorizado(leitor):
    memoria: dict[str, object] = {}

    def ler(imagem):
        chave = imagem.tobytes()
        if chave not in memoria:
            memoria[chave] = leitor(imagem)
        return memoria[chave]

    return ler


def _extrair_paginas(*, pdf: Path, page_indexes: list[int], idioma: str,
                     dpi: int, sem_geometria: bool = False):
    """Executa a extração de produção para os índices zero-based recebidos."""
    from core.services.learning_service import LearningService
    from core.services.ocr_service import OCRService

    service = LearningService()
    if not service.load_predictor():
        raise RuntimeError(service.motivo_do_modelo())
    ocr_service = OCRService()
    classificar = service.leitor_de_texto(idioma)
    ler_pagina = _leitor_memorizado(
        lambda imagem: ocr_service.tesseract_pagina_detalhada_conf(
            imagem, idioma))
    ler_faixa = _leitor_memorizado(
        lambda imagem: ocr_service.tesseract_faixa_detalhada_conf(
            imagem, idioma))
    return livro.extrair(
        str(pdf), classificar, paginas=page_indexes,
        ler_pagina=ler_pagina, ler_faixa=ler_faixa,
        fusao="palavra", diagramas="recorte", idioma_ocr=idioma, dpi=dpi,
        candidatas=None if sem_geometria else service.candidatas,
    )


def _gravar_artefatos(candidato: dict, pagina, base: Path) -> dict:
    """Grava o rascunho e o roteamento sem mudar o estado editorial."""
    identificador = str(candidato["id"])
    rascunho = base / "rascunhos" / f"{identificador}.txt"
    roteamento = base / "roteamento" / f"{identificador}.json"
    rascunho.parent.mkdir(parents=True, exist_ok=True)
    roteamento.parent.mkdir(parents=True, exist_ok=True)

    texto = str(getattr(pagina, "texto", "") or "")
    rascunho.write_text(texto + "\n", encoding="utf-8")
    roteamento.write_text(
        json.dumps(list(getattr(pagina, "roteamento", []) or []),
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    candidato["artifacts"] = {
        "draft": rascunho.relative_to(base).as_posix(),
        "routing": roteamento.relative_to(base).as_posix(),
        "draft_source": "livro.extrair/fusao=palavra",
    }
    return candidato


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--documento", required=True,
                        help="identificador estável do livro")
    parser.add_argument("--paginas", type=int, nargs="+", required=True,
                        help="páginas humanas, começando em 1")
    parser.add_argument("--idioma", default="en")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--declarada", action="append", default=[],
                        choices=familias_de_pagina.FAMILIAS,
                        help="família explicitamente informada para estas páginas")
    parser.add_argument("--sem-geometria", action="store_true")
    parser.add_argument("-o", "--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    pdf = args.pdf.resolve()
    if not pdf.exists():
        raise SystemExit(f"PDF ausente: {pdf}")
    if any(pagina < 1 for pagina in args.paginas):
        raise SystemExit("--paginas deve usar índices começando em 1")
    if len(set(args.paginas)) != len(args.paginas):
        raise SystemExit("--paginas não pode conter página repetida")
    if args.dpi < 1:
        raise SystemExit("--dpi deve ser positivo")

    source_pdf_sha256 = sha256_arquivo(pdf)

    lidas = _extrair_paginas(
        pdf=pdf, page_indexes=[pagina - 1 for pagina in args.paginas],
        idioma=args.idioma, dpi=args.dpi, sem_geometria=args.sem_geometria)
    if len(lidas) != len(args.paginas):
        raise RuntimeError(
            f"extração devolveu {len(lidas)} página(s), esperado {len(args.paginas)}")
    esperados = [pagina - 1 for pagina in args.paginas]
    recebidos = [int(getattr(pagina, "numero", -1)) for pagina in lidas]
    if recebidos != esperados:
        raise RuntimeError(
            f"extração devolveu páginas {recebidos}, esperado {esperados}")

    candidatos = []
    for page_index, pagina in zip(args.paginas, lidas):
        candidato = candidato_de_pagina(
            args.documento, page_index, pagina, pdf=str(pdf),
            source_pdf_sha256=source_pdf_sha256,
            declaradas=args.declarada)
        candidatos.append(_gravar_artefatos(candidato, pagina, args.output.parent))
    dados = {
        "schema": "pyboxeditor.ocr-corpus-candidates/v1",
        "source": {
            "pdf": str(pdf),
            "documento": args.documento,
            "idioma": args.idioma,
            "dpi": args.dpi,
            "page_index_base": 1,
            "pdf_sha256": source_pdf_sha256,
        },
        "candidatos": candidatos,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"{len(candidatos)} candidato(s) gravado(s) em {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
