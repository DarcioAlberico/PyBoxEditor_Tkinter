"""A/B da leitura de livro: cadeia própria, linha do motor, fusão por palavra.

    python scripts/ab_ocr_livro.py "PDF/.../livro.pdf" --paginas 30
    python scripts/ab_ocr_livro.py livro.pdf --paginas 30 31 --modos glifo palavra

Roda as páginas pedidas pelo `livro.extrair` de produção, uma vez por modo, e
grava o texto e o registro de roteamento de cada uma em `--saida`. Com uma
referência em `--referencia/pNNN.txt` (ver `preview_ocr/referencia/LEIA-ME.txt`),
imprime CER e WER de **prosa e notação em separado** (`ocr_ab.medir_por_dominio`)
para cada modo — que é o que a OCR-11 pede: o número que diz de qual dos dois
leitores é o defeito. Sem referência, grava o rascunho dela a partir do modo
`palavra`, para ser revisado à mão.

Os três modos são os três valores de `fusao`/`ler_pagina` de `extrair_pagina`:

- `glifo`: só a cadeia própria (`ler_pagina=None`), o pipeline de antes;
- `linha`: a linha inteira do Tesseract substitui a âncora e as figurinas são
  repostas por coordenada (`fusao="linha"`);
- `palavra`: lance da âncora, prosa do motor, token a token (`fusao="palavra"`).

Nos dois modos com motor, a linha que a passada de página não devolveu é
lida pela faixa dela (`ler_faixa`, `--psm 7`).

O Tesseract roda **uma** vez por página, e não uma por modo: a leitura é
memorizada pelos bytes da imagem, para os modos `linha` e `palavra` comparem o
mesmo registro. Só o interpretador do `.venv` tem o torch que o modelo pede.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core import livro  # noqa: E402
from core.ocr_ab import medir_por_dominio  # noqa: E402

MODOS = ("glifo", "linha", "palavra")


def _leitor_memorizado(leitor):
    """Um `ler_pagina`/`ler_faixa` que chama o Tesseract uma vez por imagem."""
    memoria: dict = {}

    def ler(imagem):
        chave = hashlib.sha1(imagem.tobytes()).hexdigest()
        if chave not in memoria:
            memoria[chave] = leitor(imagem)
        return memoria[chave]
    return ler


def _extrair(pdf: Path, numeros, classificar, ler, ler_faixa, idioma: str,
             modo: str):
    kwargs = {"diagramas": "recorte", "idioma_ocr": idioma}
    if modo != "glifo":
        kwargs.update(ler_pagina=ler, ler_faixa=ler_faixa,
                      fusao="palavra" if modo == "palavra" else "linha")
    return livro.extrair(str(pdf), classificar, paginas=numeros, **kwargs)


def _percentual(valor: float) -> str:
    return f"{valor * 100:6.2f}%"


def _resumo_do_roteamento(pagina) -> dict:
    por_dominio = collections.Counter(
        (r["dominio"], r["fonte"]) for r in pagina.roteamento)
    rejeitadas = [r for r in pagina.roteamento
                  if r["semelhanca"] is not None
                  and r["semelhanca"] < livro.SEMELHANCA_MINIMA_DA_LINHA]
    return {"linhas": len(pagina.roteamento),
            "por_dominio_e_fonte": {f"{d}/{f}": n for (d, f), n
                                    in sorted(por_dominio.items())},
            "linhas_do_motor_rejeitadas": [
                {"semelhanca": round(r["semelhanca"], 2),
                 "ancora": r["ancora"], "linha_ocr": r["linha_ocr"]}
                for r in rejeitadas]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--paginas", nargs="+", type=int, default=[30],
                        help="páginas visíveis, começando em 1")
    parser.add_argument("--modos", nargs="+", choices=MODOS, default=list(MODOS))
    parser.add_argument("--idioma", default="en")
    parser.add_argument("--saida", type=Path, default=Path("preview_ocr/ab"))
    parser.add_argument("--referencia", type=Path,
                        default=Path("preview_ocr/referencia"))
    args = parser.parse_args()

    if not args.pdf.exists():
        raise FileNotFoundError(args.pdf)
    if any(numero < 1 for numero in args.paginas):
        raise ValueError("páginas começam em 1")

    from core.services.learning_service import LearningService
    from core.services.ocr_service import OCRService

    service = LearningService()
    if not service.load_predictor():
        raise RuntimeError(service.motivo_do_modelo())
    classificar = service.leitor_de_texto(args.idioma)
    ocr_service = OCRService()
    ler = _leitor_memorizado(
        lambda imagem: ocr_service.tesseract_pagina_detalhada_conf(imagem, args.idioma))
    ler_faixa = _leitor_memorizado(
        lambda imagem: ocr_service.tesseract_faixa_detalhada_conf(imagem, args.idioma))
    numeros = [numero - 1 for numero in args.paginas]

    textos: dict[str, dict[int, str]] = {}
    tempos: dict[str, float] = {}
    roteamentos: dict[str, dict[int, dict]] = {}
    for modo in args.modos:
        inicio = time.time()
        paginas = _extrair(args.pdf, numeros, classificar, ler, ler_faixa,
                           args.idioma, modo)
        tempos[modo] = time.time() - inicio
        textos[modo] = {}
        roteamentos[modo] = {}
        pasta = args.saida / modo
        pasta.mkdir(parents=True, exist_ok=True)
        for numero, pagina in zip(args.paginas, paginas):
            textos[modo][numero] = pagina.texto
            (pasta / f"p{numero:03d}.txt").write_text(pagina.texto + "\n",
                                                      encoding="utf-8")
            (pasta / f"p{numero:03d}_roteamento.json").write_text(
                json.dumps(pagina.roteamento, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8")
            roteamentos[modo][numero] = _resumo_do_roteamento(pagina)
        print(f"{modo:8s} {tempos[modo]:5.1f}s  ->  {pasta}")

    relatorio: dict = {"pdf": str(args.pdf), "paginas": args.paginas,
                       "modos": args.modos, "tempo_s": tempos,
                       "roteamento": roteamentos, "metricas": {}}
    for numero in args.paginas:
        caminho = args.referencia / f"p{numero:03d}.txt"
        if not caminho.exists():
            modo_base = "palavra" if "palavra" in textos else args.modos[-1]
            rascunho = args.referencia / f"p{numero:03d}.rascunho.txt"
            rascunho.parent.mkdir(parents=True, exist_ok=True)
            rascunho.write_text(textos[modo_base][numero] + "\n", encoding="utf-8")
            print(f"\npágina {numero}: sem referência em {caminho}; rascunho do "
                  f"modo {modo_base} gravado em {rascunho} — revise-o à mão e "
                  f"renomeie para {caminho.name}.")
            continue
        referencia = caminho.read_text(encoding="utf-8")
        print(f"\npágina {numero} — contra {caminho}")
        print(f"{'modo':8s} {'CER prosa':>10s} {'WER prosa':>10s} "
              f"{'CER notação':>12s} {'WER notação':>12s} {'CER total':>10s}")
        for modo in args.modos:
            contas = medir_por_dominio(referencia, textos[modo][numero])
            relatorio["metricas"].setdefault(str(numero), {})[modo] = contas
            print(f"{modo:8s} {_percentual(contas['prose']['cer']):>10s} "
                  f"{_percentual(contas['prose']['wer']):>10s} "
                  f"{_percentual(contas['notation']['cer']):>12s} "
                  f"{_percentual(contas['notation']['wer']):>12s} "
                  f"{_percentual(contas['total']['cer']):>10s}")
        print(f"tokens de referência: prosa "
              f"{contas['prose']['tokens']}, notação {contas['notation']['tokens']}")

    for modo in ("palavra", "linha"):
        if modo not in roteamentos:
            continue
        for numero, resumo in roteamentos[modo].items():
            print(f"\nroteamento ({modo}, página {numero}): "
                  f"{resumo['por_dominio_e_fonte']}")
            for item in resumo["linhas_do_motor_rejeitadas"]:
                print(f"  rejeitada ({item['semelhanca']:.2f}): "
                      f"{item['ancora'][:50]!r} vs {item['linha_ocr'][:50]!r}")

    args.saida.mkdir(parents=True, exist_ok=True)
    destino = args.saida / "relatorio.json"
    destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
    print(f"\nrelatório: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
