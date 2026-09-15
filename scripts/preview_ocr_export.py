"""Converte páginas selecionadas usando o pipeline de livro do PyBoxEditor."""

from __future__ import annotations

import argparse
from pathlib import Path

from core import exportar, livro
from core.services.learning_service import LearningService


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--pages", nargs="+", type=int, default=[30, 31],
                        help="páginas visíveis, começando em 1")
    parser.add_argument("--output-dir", type=Path, default=Path("preview_ocr"))
    args = parser.parse_args()

    if not args.pdf.exists():
        raise FileNotFoundError(args.pdf)
    if any(numero < 1 for numero in args.pages):
        raise ValueError("páginas devem começar em 1")

    service = LearningService()
    print("Carregando modelo neural...")
    if not service.load_predictor():
        raise RuntimeError(service.motivo_do_modelo())

    paginas_pdf = [numero - 1 for numero in args.pages]

    def progresso(atual: int, total: int) -> None:
        print(f"Extraindo página {atual}/{total}...", flush=True)

    paginas = livro.extrair(
        str(args.pdf),
        service.leitor_de_texto("en"),
        paginas=paginas_pdf,
        diagramas="recorte",
        coordenadas=False,
        progress_callback=progresso,
    )
    titulo, autor = livro.titulo_e_autor(str(args.pdf))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    base = args.pdf.stem + "_paginas_30_31"
    epub = args.output_dir / f"{base}.epub"
    docx = args.output_dir / f"{base}.docx"

    print("Escrevendo EPUB...", flush=True)
    exportar.exportar(paginas, str(epub), formato="epub", titulo=titulo,
                     autor=autor, diagramas="png")
    print("Escrevendo DOCX...", flush=True)
    exportar.exportar(paginas, str(docx), formato="docx", titulo=titulo,
                     autor=autor, diagramas="png")
    print(f"EPUB: {epub}")
    print(f"DOCX: {docx}")
    print(f"Páginas processadas: {len(paginas)}")
    print(f"Caracteres reconhecidos: {sum(p.caracteres for p in paginas)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
