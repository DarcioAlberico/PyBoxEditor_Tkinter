"""Processa um PDF pela fachada editorial, com o leitor de produção.

Exemplos:
    python scripts/processar_editorial.py livro.pdf -o saida.json
    python scripts/processar_editorial.py livro.pdf -o saida.epub --paginas 30 31
    python scripts/processar_editorial.py livro.pdf --inspect
    python scripts/processar_editorial.py livro.pdf -o b.json --biblioteca --usar-engines

Por padrão lê como a janela ("Exportar → Documento editorial"): o leitor
medido de `core/livro.py` atrás da fachada, montado por
`core.editorial_legacy.pipeline_de_producao` — o que pede o modelo de glifos e
o Tesseract, e falha dizendo qual faltou —, com a camada de texto do PDF
nascido digital lida como texto (F110). EPUB e DOCX saem do escritor histórico,
como na janela; JSON, HTML, TXT e PDF, do documento editorial.

`--biblioteca` troca o leitor pela biblioteca de inspeção das Fases 3 e 4, que
lê a camada de texto do PDF sem modelo nenhum e, numa página digitalizada, não
lê nada; `--usar-engines` soma a ela os adapters opcionais de linha
(Tesseract, EasyOCR, PaddleOCR) e consolida somente hipóteses com consenso de
fontes distintas; conflitos permanecem marcados para revisão. É para comparar,
e não para produzir: foi
esse o padrão até 2026-09-23, e numa página digitalizada ele devolvia um bloco
vazio sem aviso (`docs/REVISAO_MODOS_OCR.md` §3.1 e §4.11).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.editorial_pipeline import (  # noqa: E402
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
                        default="clean",
                        help="estratégia de preservação editorial (HTML e PDF do documento)")
    parser.add_argument("--idioma", default="en")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--paginas", nargs="*", type=int, metavar="N",
                        help="páginas 1-based; por padrão, todas")
    parser.add_argument("--camada", choices=("auto", "nunca", "sempre"), default="auto",
                        help="a camada de texto do PDF nascido digital (F110): "
                             "auto decide por página, como a janela")
    parser.add_argument("--sem-cache", action="store_true",
                        help="não usa o cache de páginas (só a biblioteca guarda)")
    parser.add_argument("--cache-max-idade-horas", type=float,
                        help="remove entradas do cache mais antigas que este limite")
    parser.add_argument("--cache-max-mb", type=int,
                        help="mantém o cache abaixo deste tamanho, removendo os itens mais antigos")
    parser.add_argument("--biblioteca", action="store_true",
                        help="lê pela biblioteca de inspeção das Fases 3 e 4, "
                             "e não pelo leitor de produção")
    parser.add_argument("--usar-engines", action="store_true",
                        help="soma à biblioteca os adapters opcionais de OCR "
                             "(implica --biblioteca)")
    parser.add_argument("--gpu", action="store_true",
                        help="solicita GPU aos adapters que a suportam")
    parser.add_argument("--usar-ensemble", action="store_true",
                        help="usa consenso conservador de engines nas faixas do leitor")
    parser.add_argument("--validar-qualidade", action="store_true",
                        help="executa o gate estrutural antes de exportar")
    parser.add_argument("--exigir-resolvido", action="store_true",
                        help="com o gate, recusa blocos unresolved")
    parser.add_argument("--inspect", action="store_true",
                        help="grava somente o relatório de inspeção em stdout")
    return parser


def montar_pipeline(args: argparse.Namespace, *, servicos=None):
    """`(pipeline, extrator)` — o `extrator` é `None` na biblioteca.

    `servicos` é o par `(LearningService, OCRService)` do leitor de produção;
    os testes o injetam.
    """
    if args.biblioteca or args.usar_engines:
        if not args.usar_engines:
            return EditorialPipeline(), None
        from core.services.ocr_service import OCRService
        return EditorialPipeline.from_ocr_service(
            OCRService(), language=args.idioma, languages=(args.idioma,), gpu=args.gpu,
        ), None
    from core.editorial_legacy import OpcoesDeLeitura, pipeline_de_producao
    if servicos is None:
        from core.services.learning_service import LearningService
        from core.services.ocr_service import OCRService
        servicos = (LearningService(), OCRService())
    return pipeline_de_producao(*servicos, OpcoesDeLeitura(
        idioma=args.idioma, dpi=args.dpi, camada=args.camada,
        usar_ensemble=args.usar_ensemble,
        candidatas=servicos[0].candidatas))


def escrever(pipeline, documento, extrator, destino: Path, formato: str,
             args: argparse.Namespace) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`(arquivos, avisos)` — o mesmo caminho de `MainWindow._escrever_documento_editorial`.

    EPUB e DOCX saem de `exportar.exportar` pela fachada (PD-21): sobre as
    `PaginaExtraida` lidas quando há leitor de produção, e de volta do IR na
    biblioteca — é o escritor que embute a fonte dos símbolos e redesenha os
    diagramas.
    """
    relatorio = pipeline.export(documento, destino,
                                ExportOptions(format=formato, mode=args.modo))
    return tuple(relatorio.files), tuple(relatorio.warnings)


def main(argv: list[str] | None = None, *, servicos=None) -> int:
    args = construir_parser().parse_args(argv)
    indices = None if args.paginas is None else tuple(numero - 1 for numero in args.paginas)
    if indices is not None and any(numero < 0 for numero in indices):
        raise SystemExit("--paginas usa números 1-based positivos")
    source = DocumentSource.from_path(args.origem, page_indices=indices)
    options = ProcessOptions(
        dpi=args.dpi, language=args.idioma, page_indices=indices,
        use_cache=not args.sem_cache,
        cache_prune_max_age_seconds=(None if args.cache_max_idade_horas is None
                                     else args.cache_max_idade_horas * 3600),
        cache_prune_max_bytes=(None if args.cache_max_mb is None
                               else args.cache_max_mb * 1024 * 1024),
    )
    if args.inspect:
        # A inspeção não lê: é a geometria e o roteamento, iguais em qualquer montagem.
        print(json.dumps(EditorialPipeline().inspect(source, options).to_dict(),
                         ensure_ascii=False, indent=2))
        return 0
    if args.output is None:
        raise SystemExit("--output é obrigatório quando --inspect não é usado")
    formato = args.formato or args.output.suffix.lstrip(".").lower() or "json"
    pipeline, extrator = montar_pipeline(args, servicos=servicos)
    documento = pipeline.process(source, options)
    quality_gate = None
    if args.validar_qualidade or args.exigir_resolvido:
        from core.editorial_quality_gate import validar_documento
        quality_gate = validar_documento(
            documento, exigir_resolvido=args.exigir_resolvido)
        if not quality_gate.valid:
            print(json.dumps({"format": formato,
                              "quality_gate": quality_gate.to_dict()},
                             ensure_ascii=False, indent=2))
            return 2
    arquivos, avisos = escrever(pipeline, documento, extrator, args.output, formato, args)
    resumo = {"format": formato,
                      "reader": "biblioteca" if extrator is None else "livro.extrair",
                      "files": list(arquivos),
                      "pages": len(documento.pages),
                      "warnings": list(avisos)}
    if quality_gate is not None:
        resumo["quality_gate"] = quality_gate.to_dict()
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
