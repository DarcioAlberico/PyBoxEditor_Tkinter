"""
As páginas de um PDF lidas para o editor de livro (ED-17; docs/ANALISE_JANELA_EDITOR.md §4.4).

O editor é leve de propósito (SPEC_EDITOR DEC-07: nem `torch`, nem `numpy` no processo
dele), e o OCR é o contrário. Por isso "Arquivo → Abrir PDF…" roda **este** script num
processo à parte: ele monta o leitor de produção como a janela principal monta o
"Documento editorial" (`core.editorial_legacy.pipeline_de_producao`, com a camada de texto
do PDF nascido digital em `auto`, F110), lê só as páginas pedidas e grava o documento
editorial em JSON — que o editor abre como livro novo pela ponte da ED-11
(`importar_ir.de_documento`), com as marcas de página e a origem de cada bloco.

## O canal

Uma linha JSON por evento no stdout, e nada mais nele:

    {"evento": "inicio", "paginas": [30, 31]}
    {"evento": "etapa", "texto": "Carregando o modelo…"}
    {"evento": "progresso", "atual": 1, "total": 2}
    {"evento": "fim", "arquivo": "…json", "paginas": 2, "avisos": […]}
    {"evento": "erro", "mensagem": "…"}

O que as bibliotecas imprimem vai para o stderr (o stdout de `print` alheio é desviado),
para não quebrar o canal. Sai com 0 no fim, 1 no erro. O cancelamento é o editor matar o
processo: o JSON só é gravado no fim, então não fica meio arquivo.

    python scripts/pdf_para_editor.py livro.pdf -o saida.json --paginas 30 31 --idioma en
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

_CANAL = sys.stdout


def emitir(evento: str, **dados) -> None:
    _CANAL.write(json.dumps({"evento": evento, **dados}, ensure_ascii=False) + "\n")
    _CANAL.flush()


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lê páginas de um PDF para o editor de livro")
    parser.add_argument("origem", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True, help="o JSON editorial de saída")
    parser.add_argument("--paginas", nargs="*", type=int, metavar="N", help="páginas 1-based; por padrão, todas")
    parser.add_argument("--idioma", default="en")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--camada", choices=("auto", "nunca", "sempre"), default="auto")
    parser.add_argument("--reparar", action="store_true",
                        help="a prova visual do reparo de colagem (mais lenta; a mesma opção da exportação)")
    return parser


def opcoes_de_leitura(args: argparse.Namespace, aprendiz) -> object:
    """As opções da janela principal que valem sem a caixa de exportação."""
    from core import lexico
    from core.editorial_legacy import OpcoesDeLeitura

    campos = {f.name for f in dataclasses.fields(OpcoesDeLeitura)}
    kw = dict(idioma=args.idioma, dpi=args.dpi, camada=args.camada,
              lex=lexico.carregar(idioma=args.idioma),
              probabilidade=aprendiz.probabilidade_de if args.reparar else None)
    if "candidatas" in campos:            # a poda da caixa pela geometria (F112), onde ela já existe
        kw["candidatas"] = aprendiz.candidatas
    return OpcoesDeLeitura(**kw)


def main(argv: list[str] | None = None, *, servicos=None) -> int:
    args = construir_parser().parse_args(argv)
    paginas = list(args.paginas) if args.paginas else None
    if paginas is not None and any(n < 1 for n in paginas):
        emitir("erro", mensagem="--paginas usa números 1-based positivos")
        return 1
    emitir("inicio", paginas=paginas)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            from core.editorial_legacy import pipeline_de_producao
            from core.editorial_pipeline import DocumentSource, ExportOptions, ProcessOptions

            if servicos is None:
                emitir("etapa", texto="Carregando o modelo…")
                from core.services.learning_service import LearningService
                from core.services.ocr_service import OCRService

                servicos = (LearningService(), OCRService())
            pipeline, _extrator = pipeline_de_producao(
                *servicos, opcoes_de_leitura(args, servicos[0]),
                progresso=lambda atual, total: emitir("progresso", atual=int(atual), total=int(total)))
            indices = None if paginas is None else tuple(n - 1 for n in paginas)
            source = DocumentSource.from_path(args.origem, page_indices=indices)
            options = ProcessOptions(dpi=args.dpi, language=args.idioma, page_indices=indices)
            emitir("etapa", texto="Lendo as páginas…")
            documento = pipeline.process(source, options)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            relatorio = pipeline.export(documento, args.output, ExportOptions(format="json", mode="clean"))
    except Exception as erro:      # noqa: BLE001 — o editor mostra a frase; o traceback vai ao stderr
        import traceback

        traceback.print_exc(file=sys.stderr)
        emitir("erro", mensagem=f"{type(erro).__name__}: {erro}")
        return 1
    emitir("fim", arquivo=str(args.output), paginas=len(documento.pages), avisos=list(relatorio.warnings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
