"""A camada de texto do PDF, medida: a régua nos livros, e a camada contra o OCR.

    python scripts/medir_camada.py
    python scripts/medir_camada.py "PDF/.../livro.pdf"
    python scripts/medir_camada.py "PDF/Dvoretsky.../livro.pdf" --comparar 21 22 46 783

É o instrumento que a SPEC-CONVERSAO §5.1 pede (`medir_camada.py`) e que decide
a F110 por número. Sem `--comparar` roda só a régua (`pdf_nativo.avaliar`) em
toda página de cada PDF — por padrão, todo PDF de `PDF/` — e imprime, por livro,
quantas páginas ela aceita, por que recusa as outras e quanto tempo levou. Não
precisa de modelo nem de Tesseract.

Com `--comparar` (páginas visíveis, começando em 1) lê as páginas pedidas pelos
**dois** caminhos: a camada (`pdf_nativo.extrair`) e o OCR de produção
(`livro.extrair` como a exportação o chama: cadeia própria, Tesseract, fusão por
palavra, diagramas redesenhados). Num livro nascido digital a camada é o texto
que o autor escreveu, e serve de referência: o CER e o WER do OCR saem por
domínio, prosa e notação em separado (`ocr_ab.medir_por_dominio`), e cada
diagrama do OCR é conferido contra o FEN da camada — igual, diferente, ou caído
para o recorte. O tempo dos dois caminhos sai por página. Só o `.venv` tem o
torch que o OCR pede.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core import livro, pdf_nativo  # noqa: E402


def _regua(pdf: Path) -> dict:
    inicio = time.time()
    vereditos = pdf_nativo.avaliar(str(pdf))
    tempo = time.time() - inicio
    motivos = collections.Counter(v.motivo.split(" (")[0].split(":")[0]
                                  for v in vereditos if not v.aceita)
    return {"livro": pdf.name, "paginas": len(vereditos),
            "aceitas": sum(v.aceita for v in vereditos),
            "recusadas": dict(motivos.most_common()),
            "segundos": round(tempo, 2)}


def _imprimir_regua(linha: dict) -> None:
    aceitas, total = linha["aceitas"], linha["paginas"]
    print(f"{linha['livro'][:62]:62s} {aceitas:5d}/{total:<5d} "
          f"({aceitas / max(1, total):6.1%})  {linha['segundos']:6.1f}s")
    for motivo, n in list(linha["recusadas"].items())[:3]:
        print(f"{'':66s}recusa {n:5d}: {motivo}")


def _sobreposicao(a, b) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    uniao = ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)
    return inter / uniao


def _diagramas(nativa, ocr) -> collections.Counter:
    """Cada tabuleiro da camada contra o do OCR no mesmo lugar da página."""
    conta: collections.Counter = collections.Counter()
    do_ocr = [b for b in ocr.blocos if isinstance(b, livro.Figura) and b.caixa]
    for figura in nativa.blocos:
        if not (isinstance(figura, livro.Figura) and figura.fen and figura.caixa):
            continue
        par = max(do_ocr, key=lambda b: _sobreposicao(b.caixa, figura.caixa), default=None)
        if par is None or _sobreposicao(par.caixa, figura.caixa) < 0.5:
            conta["o OCR não achou"] += 1
        elif not par.fen:
            conta["o OCR caiu para o recorte"] += 1
        elif par.fen.split()[0] == figura.fen.split()[0]:
            conta["posição igual"] += 1
            if par.fen.split()[1] != figura.fen.split()[1]:
                conta["  (lado diferente)"] += 1
        else:
            conta["posição diferente"] += 1
    return conta


def _comparar(pdf: Path, visiveis, idioma: str) -> dict:
    from core.ocr_ab import medir_por_dominio
    from core.services.learning_service import LearningService
    from core.services.ocr_service import OCRService

    servico = LearningService()
    if not servico.load_predictor():
        raise RuntimeError(servico.motivo_do_modelo())
    classificar = servico.leitor_de_texto(idioma)
    ocr = OCRService()
    numeros = [n - 1 for n in visiveis]

    inicio = time.time()
    extracao = pdf_nativo.extrair(str(pdf), numeros, idioma=idioma)
    tempo_camada = time.time() - inicio
    nativas = {p.numero: p for p in extracao.paginas}

    inicio = time.time()
    lidas = livro.extrair(
        str(pdf), classificar, paginas=numeros, idioma_ocr=idioma,
        ler_pagina=lambda img: ocr.tesseract_pagina_detalhada_conf(img, idioma),
        ler_faixa=lambda img: ocr.tesseract_faixa_detalhada_conf(img, idioma),
        diagramas="render")
    tempo_ocr = time.time() - inicio

    totais = collections.Counter()
    diagramas = collections.Counter()
    por_pagina = []
    for pagina in lidas:
        nativa = nativas.get(pagina.numero)
        if nativa is None:
            print(f"  p{pagina.numero + 1}: a régua recusou — sem referência da camada")
            continue
        medida = medir_por_dominio(nativa.texto, pagina.texto)
        for dominio in ("prose", "notation", "total"):
            for chave in ("caracteres", "erros_de_caractere", "tokens", "erros"):
                totais[(dominio, chave)] += medida[dominio][chave]
        desta = _diagramas(nativa, pagina)
        diagramas.update(desta)
        por_pagina.append({"pagina": pagina.numero + 1,
                           "cer_prosa": round(medida["prose"]["cer"], 4),
                           "cer_notacao": round(medida["notation"]["cer"], 4),
                           "cer_total": round(medida["total"]["cer"], 4),
                           "diagramas": dict(desta)})
        print(f"  p{pagina.numero + 1:4d}  CER prosa {medida['prose']['cer']:6.2%}  "
              f"notação {medida['notation']['cer']:6.2%}  total "
              f"{medida['total']['cer']:6.2%}  diagramas {dict(desta)}")

    def cer(dominio):
        chars = totais[(dominio, "caracteres")]
        return totais[(dominio, "erros_de_caractere")] / chars if chars else 0.0

    def wer(dominio):
        tokens = totais[(dominio, "tokens")]
        return totais[(dominio, "erros")] / tokens if tokens else 0.0

    n = max(1, len(numeros))
    resumo = {"livro": pdf.name, "paginas": visiveis,
              "ocr_contra_camada": {d: {"cer": round(cer(d), 4), "wer": round(wer(d), 4)}
                                    for d in ("prose", "notation", "total")},
              "diagramas": dict(diagramas),
              "segundos_por_pagina": {"camada": round(tempo_camada / n, 3),
                                      "ocr": round(tempo_ocr / n, 3)},
              "por_pagina": por_pagina}
    print()
    print(f"OCR contra a camada, {len(por_pagina)} página(s): CER prosa "
          f"{cer('prose'):.2%}, notação {cer('notation'):.2%}, total {cer('total'):.2%}"
          f"  (WER total {wer('total'):.2%})")
    print(f"diagramas: {dict(diagramas)}")
    print(f"tempo por página: camada {tempo_camada / n:.2f}s, OCR {tempo_ocr / n:.2f}s")
    return resumo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pdfs", nargs="*", type=Path,
                        help="os PDFs (padrão: todo PDF de PDF/)")
    parser.add_argument("--comparar", nargs="+", type=int,
                        help="páginas visíveis (base 1) para ler pelos dois caminhos")
    parser.add_argument("--idioma", default="en")
    parser.add_argument("--saida", type=Path,
                        help="grava o resultado em JSON neste arquivo")
    args = parser.parse_args()

    pdfs = args.pdfs or [Path(p) for p in sorted(glob.glob(str(RAIZ / "PDF" / "**" / "*.pdf"),
                                                            recursive=True))]
    if not pdfs:
        print("nenhum PDF")
        return 1
    if args.comparar:
        if len(pdfs) != 1:
            parser.error("--comparar mede um PDF só")
        if any(n < 1 for n in args.comparar):
            parser.error("páginas começam em 1")
        resultado = _comparar(pdfs[0], args.comparar, args.idioma)
    else:
        resultado = []
        for pdf in pdfs:
            linha = _regua(pdf)
            _imprimir_regua(linha)
            resultado.append(linha)
    if args.saida:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=1) + "\n",
                              encoding="utf-8")
        print(f"-> {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
