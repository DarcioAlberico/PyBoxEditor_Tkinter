"""
Mede as passadas de livro inteiro (RG-14, R-20 da revisão geral 2): quantos parágrafos que a
paginação partiu voltaram a ser um, quantos diagramas ganharam o lado pelo lance anterior, e
quantos FEN saíram.

Existe porque o A/B e o corpus leem páginas avulsas, e as passadas entre páginas só agem com
páginas seguidas. Lê o livro com o leitor de produção (`ExtratorDeLivro`, o do "Abrir PDF" e
do documento editorial) e grava o resumo e o texto de cada página, para comparar o de antes
com o de depois; as junções saem por extenso, para o olho conferir cada uma.

    python scripts/medidas/medir_passadas_de_livro.py LIVRO.pdf --saida preview_ocr/ab/RG-14-antes
    python scripts/medidas/medir_passadas_de_livro.py LIVRO.pdf --saida … --paginas 30 60

Grava `<saida>/resumo.json` e `<saida>/paginas.json`.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core import lexico, livro, pdf_nativo  # noqa: E402
from core.editorial_legacy import ExtratorDeLivro, OpcoesDeLeitura  # noqa: E402
from core.editorial_pipeline import ProcessOptions  # noqa: E402


def _contar(contas: dict, nome: str) -> None:
    """Embrulha a passada `nome` de `pdf_nativo` para somar o que ela devolve."""
    original = getattr(pdf_nativo, nome)

    def embrulhada(*args, **kwargs):
        feito = original(*args, **kwargs)
        contas[nome] += int(feito)
        return feito

    setattr(pdf_nativo, nome, embrulhada)


def _observar_juncoes(juncoes: list) -> None:
    """Cada junção entre páginas, por extenso: a página, o fim dela e o começo da outra."""
    original = pdf_nativo.juntar_entre_paginas

    def embrulhada(paginas, **kwargs):
        antes = [(p, p.blocos[-1] if p.blocos else None,
                  p.blocos[-1].texto if p.blocos and isinstance(p.blocos[-1], livro.Paragrafo) else "")
                 for p in paginas]
        feito = original(paginas, **kwargs)
        for pagina, bloco, texto in antes:
            if texto and bloco.texto != texto:
                juncoes.append({"pagina": pagina.numero + 1, "fim": texto[-60:],
                                "comeco": bloco.texto[len(texto.rstrip()):][:60]})
        return feito

    pdf_nativo.juntar_entre_paginas = embrulhada


def resumo(paginas) -> dict:
    figuras = [b for p in paginas for b in p.blocos
               if isinstance(b, livro.Figura) and b.origem in ("render", "recorte")]
    paragrafos = [b for p in paginas for b in p.blocos if isinstance(b, livro.Paragrafo)]
    return {
        "paginas": len(paginas),
        "paragrafos": sum(1 for p in paragrafos if not p.titulo),
        "titulos": sum(1 for p in paragrafos if p.titulo),
        "diagramas": len(figuras),
        "fen": sum(1 for f in figuras if f.fen),
        "lado_origem": dict(sorted(collections.Counter(
            f.lado_origem for f in figuras if f.fen).items())),
        "caracteres": sum(p.caracteres for p in paginas),
        # O negrito, e os parágrafos que ele pula por a medida não ter o comprimento do
        # texto (a propriedade P-2 da spec, RG-15).
        "trechos_em_negrito": sum(len(p.negrito) for p in paragrafos),
        "caracteres_em_negrito": sum(z - a for p in paragrafos for a, z in p.negrito),
        "sem_medida_no_comprimento": sum(
            1 for p in paragrafos if p.pesos is not None and len(p.pesos) != len(p.texto)),
        "com_falha": [p.numero + 1 for p in paginas if getattr(p, "falha", "")],
        "sem_motor": [p.numero + 1 for p in paginas if p.motor_indisponivel],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--idioma", default="en")
    parser.add_argument("--camada", choices=pdf_nativo.MODOS, default="nunca")
    parser.add_argument("--paginas", nargs=2, type=int, metavar=("DE", "ATE"),
                        help="o intervalo 1-based; por padrão, o livro todo")
    args = parser.parse_args(argv)

    from core.services.learning_service import LearningService
    from core.services.ocr_service import OCRService
    aprendiz = LearningService()
    extrator = ExtratorDeLivro(aprendiz, OCRService(), OpcoesDeLeitura(
        idioma=args.idioma, camada=args.camada, lex=lexico.carregar(idioma=args.idioma),
        candidatas=aprendiz.candidatas))
    contas: collections.Counter = collections.Counter()
    juncoes: list = []
    _observar_juncoes(juncoes)
    for nome in ("juntar_entre_paginas", "lados_pelos_lances"):
        contas[nome] = 0
        _contar(contas, nome)
    indices = (None if args.paginas is None
               else tuple(range(args.paginas[0] - 1, args.paginas[1])))
    inicio = time.perf_counter()
    paginas = list(extrator(args.pdf, ProcessOptions(
        dpi=300, language=args.idioma, page_indices=indices)))
    saida = {**resumo(paginas), **contas, "tempo_s": round(time.perf_counter() - inicio, 1),
             "juncoes": juncoes}
    args.saida.mkdir(parents=True, exist_ok=True)
    (args.saida / "resumo.json").write_text(
        json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    (args.saida / "paginas.json").write_text(json.dumps(
        [{"pagina": p.numero + 1, "texto": p.texto,
          "negrito": [[b.texto[a:z] for a, z in b.negrito] for b in p.blocos
                      if isinstance(b, livro.Paragrafo) and b.negrito],
          "fen": [[b.fen, b.lado_origem] for b in p.blocos
                  if isinstance(b, livro.Figura) and b.fen]} for p in paginas],
        ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in saida.items() if k != "juncoes"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
