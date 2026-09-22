"""Processa um PDF/imagem pela fachada editorial da Fase 2.

Exemplos:
    python scripts/processar_editorial.py livro.pdf -o saida.json
    python scripts/processar_editorial.py scan.png -o saida.html --formato html
    python scripts/processar_editorial.py livro.pdf --inspect
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.editorial_pipeline import (
    DocumentSource,
    EditorialPipeline,
    ExportOptions,
    ProcessOptions,
)


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OCR editorial de produção")
    parser.add_argument("origem", type=Path)
    parser.add_argument("-o", "--output", type=Path,
                        help="arquivo editorial de saída")
    parser.add_argument("--formato", choices=("json", "html", "txt", "epub", "docx", "pdf"),
                        default=None)
    parser.add_argument("--modo", choices=("faithful", "clean", "hybrid"),
                        default="clean", help="estratégia de preservação editorial")
    parser.add_argument("--idioma", default="en")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--paginas", nargs="*", type=int, metavar="N",
                        help="páginas 1-based; por padrão, todas")
    parser.add_argument("--sem-cache", action="store_true")
    parser.add_argument("--usar-engines", action="store_true",
                        help="usa adapters opcionais de OCR além da camada PDF")
    parser.add_argument("--gpu", action="store_true",
                        help="solicita GPU aos adapters que a suportam")
    parser.add_argument("--inspect", action="store_true",
                        help="grava somente o relatório de inspeção em stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    indices = None if args.paginas is None else tuple(numero - 1 for numero in args.paginas)
    if indices is not None and any(numero < 0 for numero in indices):
        raise SystemExit("--paginas usa números 1-based positivos")
    source = DocumentSource.from_path(args.origem, page_indices=indices)
    options = ProcessOptions(
        dpi=args.dpi, language=args.idioma, page_indices=indices,
        use_cache=not args.sem_cache,
    )
    if args.usar_engines:
        from core.ocr_phase3 import Phase3Processor
        from core.ocr_phase4 import Phase4Processor
        from core.services.ocr_service import OCRService
        text_processor = Phase3Processor.from_ocr_service(
            OCRService(), language=args.idioma, languages=(args.idioma,), gpu=args.gpu,
        )
        processor = Phase4Processor(text_processor=text_processor)
        pipeline = EditorialPipeline(recognizer=processor)
    else:
        pipeline = EditorialPipeline()
    if args.inspect:
        print(json.dumps(pipeline.inspect(source, options).to_dict(),
                         ensure_ascii=False, indent=2))
        return 0
    if args.output is None:
        raise SystemExit("--output é obrigatório quando --inspect não é usado")
    formato = args.formato or args.output.suffix.lstrip(".").lower() or "json"
    documento = pipeline.process(source, options)
    relatorio = pipeline.export(documento, args.output,
                                ExportOptions(format=formato, mode=args.modo))
    print(json.dumps({"format": relatorio.format,
                      "files": list(relatorio.files),
                      "pages": len(documento.pages),
                      "warnings": list(relatorio.warnings)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
