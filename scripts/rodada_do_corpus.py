"""A rodada do corpus de referência: mede tudo, compara com a anterior, grava.

    python scripts/rodada_do_corpus.py
    python scripts/rodada_do_corpus.py --manifesto benchmarks/ocr_corpus_v1.json
    python scripts/rodada_do_corpus.py --tolerancia 0.002 --rotulo "antes do fine-tune"

Lê o manifesto congelado (`pyboxeditor.ocr-corpus/v1`), roda o leitor de
produção — `livro.extrair` com fusão por palavra, o mesmo de "Exportar Livro" —
em **cada página que tem referência humana**, mede CER e WER de prosa e notação
em separado (`ocr_ab.medir_por_dominio`) e grava o resultado em
`benchmarks/rodadas/<data>.json`.

Três coisas que o A/B página a página não dá, e que o item 6 da revisão de
2026-09-18 pede:

- **o total do corpus**, e não uma tabela por página solta: é o número que uma
  promessa comercial citaria, e ele só existe se for calculado sobre o corpus
  inteiro de uma vez;
- **a cobertura por família de layout** (`core/familias_de_pagina.py`), que diz
  o que o corpus ainda **não** mede — trinta páginas de prosa mediriam uma coisa
  só, com três casas decimais;
- **a comparação com a rodada anterior**, com saída diferente de zero quando
  alguma página piora além da tolerância. É o portão: mudança em `core/livro.py`
  se mede aqui antes de ser commitada.

Só o interpretador do `.venv` tem o torch que o modelo pede.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core import familias_de_pagina  # noqa: E402
from core.ocr_ab import medir_por_dominio  # noqa: E402

PASTA_DAS_RODADAS = Path("benchmarks/rodadas")


def _leitor_memorizado(leitor):
    """O Tesseract roda uma vez por imagem, e não uma vez por medição."""
    memoria: dict = {}

    def ler(imagem):
        chave = hashlib.sha1(imagem.tobytes()).hexdigest()
        if chave not in memoria:
            memoria[chave] = leitor(imagem)
        return memoria[chave]
    return ler


def paginas_do_manifesto(caminho: Path) -> list[dict]:
    """As páginas com referência, já resolvidas em caminhos absolutos.

    Os caminhos do manifesto são relativos a ele (`../PDF/...`), que é o que o
    torna movível junto com a pasta `benchmarks/`.
    """
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    base = caminho.parent
    saida: list[dict] = []
    for documento in dados.get("documents", []):
        pdf = (base / str(documento.get("source") or "")).resolve()
        for pagina in documento.get("pages", []):
            referencia = pagina.get("reference")
            if not referencia:
                continue
            dificuldade = str((pagina.get("metadata") or {}).get("difficulty", ""))
            saida.append({
                "documento": str(documento.get("id") or "?"),
                "titulo": str(documento.get("title") or ""),
                "idioma": str(documento.get("language") or "en"),
                "pdf": pdf,
                "id": str(pagina.get("id") or "?"),
                "page_index": int(pagina.get("page_index") or 0),
                "referencia": (base / str(referencia)).resolve(),
                "dificuldade": dificuldade,
                "declaradas": [familias_de_pagina.FAMILIA_DA_DIFICULDADE[dificuldade]]
                if dificuldade in familias_de_pagina.FAMILIA_DA_DIFICULDADE else [],
            })
    return saida


def _ultima_rodada(pasta: Path) -> dict | None:
    anteriores = sorted(pasta.glob("*.json"))
    if not anteriores:
        return None
    return json.loads(anteriores[-1].read_text(encoding="utf-8"))


def _cer_por_pagina(rodada: dict | None) -> dict[str, float]:
    if not rodada:
        return {}
    return {pagina["id"]: float(pagina["metricas"]["total"]["cer"])
            for pagina in rodada.get("paginas", [])
            if pagina.get("metricas")}


def _totais(paginas: list[dict]) -> dict[str, dict[str, float]]:
    """CER e WER do corpus inteiro, ponderados pelo tamanho de cada página.

    Ponderado, e não média das páginas: a média de páginas faria uma página de
    doze tokens pesar o mesmo que uma de trezentos, e o número que se cita é o
    do livro, não o da página.
    """
    contas = {dominio: {"caracteres": 0.0, "erros_de_caractere": 0.0,
                        "tokens": 0.0, "erros": 0.0}
              for dominio in ("prose", "notation", "total")}
    for pagina in paginas:
        for dominio, valores in (pagina.get("metricas") or {}).items():
            if dominio not in contas:
                continue
            for chave in contas[dominio]:
                contas[dominio][chave] += float(valores.get(chave, 0) or 0)
    for valores in contas.values():
        valores["cer"] = (valores["erros_de_caractere"] / valores["caracteres"]
                          if valores["caracteres"] else 0.0)
        valores["wer"] = (valores["erros"] / valores["tokens"]
                          if valores["tokens"] else 0.0)
    return contas


def pioras(medidas: list[dict], antes: dict[str, float],
           tolerancia: float) -> list[str]:
    """As páginas que pioraram além da tolerância, em frase.

    É o portão desta rodada: mudança em `core/livro.py` se mede aqui antes de
    ser commitada, e uma página que piora derruba a rodada. Página nova — sem
    número anterior — não pode piorar, e por isso não entra.
    """
    saida: list[str] = []
    for medida in medidas:
        contas = medida.get("metricas")
        if not contas:
            continue
        anterior = antes.get(medida["id"])
        atual = float(contas["total"]["cer"])
        if anterior is not None and atual > anterior + tolerancia:
            saida.append(f"{medida['id']}: {anterior * 100:.2f}% → {atual * 100:.2f}%")
    return saida


def _percentual(valor: float) -> str:
    return f"{valor * 100:6.2f}%"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifesto", type=Path,
                        default=Path("benchmarks/ocr_corpus_v1.json"))
    parser.add_argument("--rodadas", type=Path, default=PASTA_DAS_RODADAS)
    parser.add_argument("--tolerancia", type=float, default=0.001,
                        help="quanto o CER de uma página pode piorar sem "
                             "derrubar a rodada (0,001 = 0,1 ponto percentual)")
    parser.add_argument("--rotulo", default="",
                        help="uma linha sobre o que esta rodada estava medindo")
    parser.add_argument("--minimo-por-familia", type=int, default=3)
    parser.add_argument("--dpi", type=int, default=300)
    args = parser.parse_args()

    if not args.manifesto.exists():
        raise FileNotFoundError(args.manifesto)
    paginas = paginas_do_manifesto(args.manifesto)
    if not paginas:
        raise SystemExit("o manifesto não tem página com referência")

    from core import livro
    from core.services.learning_service import LearningService
    from core.services.ocr_service import OCRService

    service = LearningService()
    if not service.load_predictor():
        raise RuntimeError(service.motivo_do_modelo())
    ocr_service = OCRService()

    medidas: list[dict] = []
    inicio = time.time()
    por_pdf: dict[Path, list[dict]] = {}
    for pagina in paginas:
        por_pdf.setdefault(pagina["pdf"], []).append(pagina)

    for pdf, do_pdf in por_pdf.items():
        if not pdf.exists():
            for pagina in do_pdf:
                medidas.append({**_sem_pdf(pagina), "erro": f"PDF ausente: {pdf}"})
            print(f"{pdf}: ausente — {len(do_pdf)} página(s) puladas")
            continue
        idioma = do_pdf[0]["idioma"]
        classificar = service.leitor_de_texto(idioma)
        ler = _leitor_memorizado(
            lambda imagem, i=idioma: ocr_service.tesseract_pagina_detalhada_conf(imagem, i))
        ler_faixa = _leitor_memorizado(
            lambda imagem, i=idioma: ocr_service.tesseract_faixa_detalhada_conf(imagem, i))
        numeros = [pagina["page_index"] - 1 for pagina in do_pdf]
        lidas = livro.extrair(str(pdf), classificar, paginas=numeros,
                              ler_pagina=ler, ler_faixa=ler_faixa,
                              fusao="palavra", diagramas="recorte",
                              idioma_ocr=idioma, dpi=args.dpi)
        for pagina, lida in zip(do_pdf, lidas):
            if not pagina["referencia"].exists():
                medidas.append({**_sem_pdf(pagina),
                                "erro": f"referência ausente: {pagina['referencia']}"})
                continue
            contas = medir_por_dominio(
                pagina["referencia"].read_text(encoding="utf-8"), lida.texto)
            medidas.append({
                "id": pagina["id"], "documento": pagina["documento"],
                "page_index": pagina["page_index"],
                "dificuldade": pagina["dificuldade"],
                "familias": sorted(familias_de_pagina.familias(
                    lida, declaradas=pagina["declaradas"])),
                "principal": familias_de_pagina.principal(
                    lida, declaradas=pagina["declaradas"]),
                "metricas": contas,
            })

    rodada = {
        "data": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "rotulo": args.rotulo,
        "manifesto": str(args.manifesto),
        "tempo_s": round(time.time() - inicio, 1),
        "paginas": medidas,
        "totais": _totais(medidas),
        "cobertura": familias_de_pagina.resumo(
            medidas, minimo=args.minimo_por_familia),
    }

    anterior = _ultima_rodada(args.rodadas)
    antes = _cer_por_pagina(anterior)
    pioraram = pioras(medidas, antes, args.tolerancia)
    print(f"{'página':28s} {'família':14s} {'CER prosa':>10s} {'CER notação':>12s} "
          f"{'CER total':>10s} {'antes':>10s}")
    for medida in medidas:
        if not medida.get("metricas"):
            print(f"{medida['id']:28s} {medida.get('erro', 'sem métrica')}")
            continue
        contas = medida["metricas"]
        cer = float(contas["total"]["cer"])
        anterior_da_pagina = antes.get(medida["id"])
        print(f"{medida['id']:28s} {medida['principal']:14s} "
              f"{_percentual(contas['prose']['cer']):>10s} "
              f"{_percentual(contas['notation']['cer']):>12s} "
              f"{_percentual(cer):>10s} "
              f"{_percentual(anterior_da_pagina) if anterior_da_pagina is not None else '—':>10s}")

    totais = rodada["totais"]
    print(f"\ncorpus ({len(medidas)} página(s)): CER total "
          f"{_percentual(totais['total']['cer'])}  prosa "
          f"{_percentual(totais['prose']['cer'])}  notação "
          f"{_percentual(totais['notation']['cer'])}")
    cobertura = rodada["cobertura"]
    print("cobertura por família: "
          + ", ".join(f"{familia} {n}" for familia, n in cobertura["cobertura"].items()))
    if cobertura["faltando"]:
        print(f"famílias com menos de {cobertura['minimo_por_familia']} páginas: "
              + ", ".join(cobertura["faltando"])
              + "  ← é o que o corpus ainda não mede")

    args.rodadas.mkdir(parents=True, exist_ok=True)
    destino = args.rodadas / (
        datetime.datetime.now().strftime("%Y-%m-%d-%H%M") + ".json")
    destino.write_text(json.dumps(rodada, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
    print(f"rodada: {destino}")

    if pioraram:
        print("\nPIOROU além da tolerância "
              f"({args.tolerancia * 100:.2f} ponto(s) percentual(is)):")
        for linha in pioraram:
            print(f"  {linha}")
        return 1
    return 0


def _sem_pdf(pagina: dict) -> dict:
    return {"id": pagina["id"], "documento": pagina["documento"],
            "page_index": pagina["page_index"],
            "dificuldade": pagina["dificuldade"],
            "familias": list(pagina["declaradas"]),
            "principal": (pagina["declaradas"] or ["prosa"])[0], "metricas": None}


if __name__ == "__main__":
    raise SystemExit(main())
