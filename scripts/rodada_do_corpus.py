"""A rodada do corpus de referência: mede tudo, compara com a anterior, grava.

    python scripts/rodada_do_corpus.py
    python scripts/rodada_do_corpus.py --manifesto benchmarks/corpus_v2.json
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
from typing import Any, Mapping

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core import familias_de_pagina  # noqa: E402
from core.ocr_ab import medir_por_dominio  # noqa: E402
from core.ocr_benchmark import medir_pagina  # noqa: E402
from core.ocr_corpus import carregar_manifesto  # noqa: E402

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


def _ler_referencia(caminho: Path) -> dict[str, Any]:
    """Lê referência textual legada ou referência estruturada JSON.

    O formato `.txt` continua sendo o contrato do corpus atual. Uma referência
    `.json` pode acrescentar `notation`, `diagrams` e `regions` sem obrigar
    corpus antigos a inventar metadados que ainda não foram anotados.
    """
    conteudo = caminho.read_text(encoding="utf-8")
    if caminho.suffix.casefold() != ".json":
        return {"text": conteudo}
    valor = json.loads(conteudo)
    if not isinstance(valor, Mapping):
        raise ValueError(f"referência estruturada deve ser objeto: {caminho}")
    return dict(valor)


def _predicao_estruturada(pagina: Any) -> dict[str, Any]:
    """Projeta `PaginaExtraida` para os domínios semânticos do benchmark."""
    from core import livro

    predicao: dict[str, Any] = {"text": str(pagina.texto)}
    notacao = [str(registro.get("texto", ""))
               for registro in getattr(pagina, "roteamento", ())
               if str(registro.get("dominio", "")) == "notation"
               and str(registro.get("texto", ""))]
    if notacao:
        predicao["notation"] = notacao

    figuras = [bloco for bloco in getattr(pagina, "blocos", ())
               if isinstance(bloco, livro.Figura)]
    if figuras:
        # Figura sem FEN é uma hipótese de diagrama ainda não resolvida; ela
        # permanece na contagem e falha legalidade, em vez de desaparecer.
        predicao["diagrams"] = [{"fen": str(figura.fen or "")}
                                 for figura in figuras]

    tipos = []
    for bloco in getattr(pagina, "blocos", ()):
        if isinstance(bloco, livro.Figura):
            tipo = "diagram"
        elif isinstance(bloco, livro.Tabela):
            tipo = "table"
        elif isinstance(bloco, livro.Paragrafo):
            tipo = "paragraph"
        else:
            tipo = "unknown"
        tipos.append({"type": tipo})
    if tipos:
        predicao["regions"] = tipos
    return predicao


def _medir_referencia(referencia: Mapping[str, Any],
                      predicao: Mapping[str, Any], page_id: str) -> dict[str, Any]:
    """Calcula CER/WER legado e métricas semânticas na mesma página."""
    referencia_texto = str(referencia.get("text", ""))
    predicao_texto = str(predicao.get("text", ""))
    metricas = medir_por_dominio(referencia_texto, predicao_texto)
    estruturadas = medir_pagina(page_id, referencia, predicao).to_dict()
    semantica = {nome: estruturadas[nome]
                 for nome in ("diagrams", "notation", "layout")
                 if nome in estruturadas}
    return {"text": referencia_texto, "metricas": metricas,
            "semantica": semantica}


def _totais_semanticos(paginas: list[dict]) -> dict[str, dict[str, Any]]:
    """Agrega semântica por contagem, sem média de percentuais de páginas."""
    saida: dict[str, dict[str, Any]] = {}
    for nome in ("diagrams", "notation"):
        itens = [pagina.get("semantica", {}).get(nome)
                 for pagina in paginas if pagina.get("semantica", {}).get(nome)]
        if not itens:
            continue
        referencia = sum(int(item.get("referencia", 0)) for item in itens)
        predicao = sum(int(item.get("predicao", 0)) for item in itens)
        exatos = sum(int(item.get("exatos", item.get("exatas", 0)))
                    for item in itens)
        legais = sum(int(item.get("legais", 0)) for item in itens)
        total = max(referencia, predicao)
        saida[nome] = {
            "referencia": referencia, "predicao": predicao,
            "exatos": exatos, "legais": legais,
            "acuracia_exata": exatos / total if total else None,
            "acuracia_legal": legais / predicao if predicao else None,
        }
    layouts = [pagina.get("semantica", {}).get("layout")
               for pagina in paginas if pagina.get("semantica", {}).get("layout")]
    if layouts:
        saida["layout"] = {
            "paginas": len(layouts),
            "ordem_corretamente_classificada": all(
                item.get("ordem_corretamente_classificada") is True
                for item in layouts),
        }
    return saida


def paginas_do_manifesto(caminho: Path) -> list[dict]:
    """As páginas com referência, já resolvidas em caminhos absolutos.

    Os caminhos do manifesto são relativos a ele (`../PDF/...`), que é o que o
    torna movível junto com a pasta `benchmarks/`.
    """
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    base = caminho.parent
    metadata_manifesto = dados.get("metadata") or {}
    try:
        page_index_base = int(metadata_manifesto.get("page_index_base", 1))
    except (TypeError, ValueError) as erro:
        raise ValueError("metadata.page_index_base deve ser 0 ou 1") from erro
    if page_index_base not in (0, 1):
        raise ValueError("metadata.page_index_base deve ser 0 ou 1")
    saida: list[dict] = []
    for documento in dados.get("documents", []):
        pdf = (base / str(documento.get("source") or "")).resolve()
        for pagina in documento.get("pages", []):
            referencia = pagina.get("reference")
            if not referencia:
                continue
            metadata = pagina.get("metadata") or {}
            dificuldade = str(metadata.get("difficulty", ""))
            declaradas = metadata.get("familias") or ()
            if isinstance(declaradas, str):
                declaradas = (declaradas,)
            declaradas = {str(familia) for familia in declaradas
                          if str(familia) in familias_de_pagina.FAMILIAS}
            familia_da_dificuldade = familias_de_pagina.FAMILIA_DA_DIFICULDADE.get(
                dificuldade)
            if familia_da_dificuldade:
                declaradas.add(familia_da_dificuldade)
            saida.append({
                "documento": str(documento.get("id") or "?"),
                "titulo": str(documento.get("title") or ""),
                "idioma": str(documento.get("language") or "en"),
                "pdf": pdf,
                "id": str(pagina.get("id") or "?"),
                "page_index": int(pagina.get("page_index") or 0),
                "page_index_base": page_index_base,
                "referencia": (base / str(referencia)).resolve(),
                "dificuldade": dificuldade,
                "declaradas": [familia for familia in familias_de_pagina.FAMILIAS
                               if familia in declaradas],
            })
    return saida


def identidade_do_manifesto(caminho: Path) -> dict[str, object]:
    """Valida e descreve o corpus que uma rodada está autorizada a medir.

    A rodada de produção não deve aceitar um manifesto cujo hash ficou
    obsoleto depois da anotação ou materialização de uma página. O resultado
    também carrega essa identidade para que comparações e releases sejam
    auditáveis fora do processo que os gerou.
    """
    manifesto = carregar_manifesto(caminho, validate_paths=True, require_files=True)
    return {
        "schema": manifesto.schema,
        "version": manifesto.version,
        "corpus_sha256": manifesto.corpus_sha256 or manifesto.digest(caminho.parent),
        "page_index_base": int((manifesto.metadata or {}).get("page_index_base", 1)),
        "documents": [document.id for document in manifesto.documents],
    }


def _ultima_rodada(pasta: Path) -> dict | None:
    encontrada = _ultima_rodada_com_caminho(pasta)
    return encontrada[1] if encontrada is not None else None


def _carregar_rodada(caminho: Path) -> dict:
    try:
        valor = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        raise ValueError(f"rodada de baseline ilegível: {caminho}") from erro
    if not isinstance(valor, dict):
        raise ValueError(f"rodada de baseline precisa ser um objeto: {caminho}")
    return valor


def _ultima_rodada_com_caminho(pasta: Path) -> tuple[Path, dict] | None:
    anteriores = sorted(pasta.glob("*.json"))
    if not anteriores:
        return None
    caminho = anteriores[-1]
    return caminho, _carregar_rodada(caminho)


def _validar_baseline(rodada: Mapping[str, Any], identidade: Mapping[str, Any],
                      caminho: Path) -> None:
    corpus_atual = str(identidade.get("corpus_sha256") or "")
    corpus_anterior = str(
        (rodada.get("corpus") or {}).get("corpus_sha256") or "")
    if corpus_atual and corpus_anterior and corpus_atual != corpus_anterior:
        raise ValueError(
            "baseline pertence a outro corpus: "
            f"{caminho} ({corpus_anterior} != {corpus_atual})")


def _falhas_de_comparacao(pioraram: list[str]) -> list[str]:
    return [f"regressão por página: {item}" for item in pioraram]


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


def falhas_de_qualidade(totais: dict[str, dict[str, float]],
                        cobertura: dict[str, object], *,
                        max_cer_total: float | None = None,
                        max_cer_prose: float | None = None,
                        max_cer_notation: float | None = None,
                        exigir_cobertura: bool = False,
                        semanticas: Mapping[str, Mapping[str, Any]] | None = None,
                        min_diagram_exact: float | None = None,
                        min_diagram_legal: float | None = None,
                        min_notation_exact: float | None = None,
                        min_notation_legal: float | None = None,
                        exigir_ordem_layout: bool = False) -> list[str]:
    """Aplica limites absolutos opcionais à rodada já calculada.

    A comparação com a rodada anterior detecta regressão; este gate responde
    outra pergunta: ``esta`` saída está abaixo do limite aceitável? Os limites
    são opt-in porque um corpus em expansão pode ser medido sem ainda estar
    pronto para release. Quando um limite é informado, a métrica ausente é
    falha explícita, nunca um zero conveniente.
    """
    limites = {
        "total": (max_cer_total, "total"),
        "prose": (max_cer_prose, "prosa"),
        "notation": (max_cer_notation, "notação"),
    }
    falhas: list[str] = []
    for dominio, (limite, rotulo) in limites.items():
        if limite is None:
            continue
        limite = float(limite)
        if limite < 0:
            raise ValueError(f"limite de CER inválido para {rotulo}: {limite}")
        medidas = totais.get(dominio)
        if not isinstance(medidas, dict) or "cer" not in medidas:
            falhas.append(f"métrica ausente para CER {rotulo}")
            continue
        atual = float(medidas["cer"])
        if atual > limite:
            falhas.append(
                f"CER {rotulo} {atual:.2%} excede limite {limite:.2%}")
    if exigir_cobertura:
        faltando = [str(item) for item in (cobertura.get("faltando") or ())]
        if faltando:
            falhas.append("cobertura insuficiente: " + ", ".join(faltando))

    semanticas = semanticas or {}

    def exigir_semantica(nome: str, chave: str, limite: float | None,
                         rotulo: str) -> None:
        if limite is None:
            return
        limite = float(limite)
        if not 0.0 <= limite <= 1.0:
            raise ValueError(f"limite semântico inválido para {rotulo}: {limite}")
        valor = semanticas.get(nome, {}).get(chave)
        if valor is None:
            falhas.append(f"métrica semântica ausente para {rotulo}")
        elif float(valor) < limite:
            falhas.append(f"{rotulo} {float(valor):.2%} abaixo do limite {limite:.2%}")

    exigir_semantica("diagrams", "acuracia_exata", min_diagram_exact,
                     "FEN exato")
    exigir_semantica("diagrams", "acuracia_legal", min_diagram_legal,
                     "legalidade de diagramas")
    exigir_semantica("notation", "acuracia_exata", min_notation_exact,
                     "notação exata")
    exigir_semantica("notation", "acuracia_legal", min_notation_legal,
                     "legalidade de notação")
    if exigir_ordem_layout:
        ordem = semanticas.get("layout", {}).get(
            "ordem_corretamente_classificada")
        if ordem is not True:
            falhas.append("ordem de layout incorreta ou métrica ausente")
    return falhas


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


def _limite_semantico(valor: str) -> float:
    try:
        limite = float(valor)
    except ValueError as erro:
        raise argparse.ArgumentTypeError("use um valor entre 0 e 1") from erro
    if not 0.0 <= limite <= 1.0:
        raise argparse.ArgumentTypeError("use um valor entre 0 e 1")
    return limite


def configurar_saida_terminal(stream=None):
    """Mantém relatórios Unicode imprimíveis em consoles Windows legados."""
    stream = stream or sys.stdout
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass
    return stream


def main(argv: list[str] | None = None) -> int:
    configurar_saida_terminal()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifesto", type=Path,
                        default=Path("benchmarks/corpus_v2.json"))
    parser.add_argument("--rodadas", type=Path, default=PASTA_DAS_RODADAS)
    parser.add_argument("--comparar-com", type=Path, default=None,
                        help="JSON de baseline; sem ele usa a última rodada da pasta")
    parser.add_argument("--tolerancia", type=float, default=0.001,
                        help="quanto o CER de uma página pode piorar sem "
                             "derrubar a rodada (0,001 = 0,1 ponto percentual)")
    parser.add_argument("--rotulo", default="",
                        help="uma linha sobre o que esta rodada estava medindo")
    parser.add_argument("--minimo-por-familia", type=int, default=3)
    parser.add_argument("--max-cer-total", type=float, default=None,
                        help="falha se o CER total do corpus exceder este limite")
    parser.add_argument("--max-cer-prosa", type=float, default=None,
                        help="falha se o CER de prosa exceder este limite")
    parser.add_argument("--max-cer-notacao", type=float, default=None,
                        help="falha se o CER de notação exceder este limite")
    parser.add_argument("--min-fen-exato", type=_limite_semantico, default=None)
    parser.add_argument("--min-fen-legal", type=_limite_semantico, default=None)
    parser.add_argument("--min-notacao-exata", type=_limite_semantico, default=None)
    parser.add_argument("--min-notacao-legal", type=_limite_semantico, default=None)
    parser.add_argument("--exigir-ordem-layout", action="store_true")
    parser.add_argument("--exigir-cobertura", action="store_true",
                        help="falha se alguma família tiver menos páginas que --minimo-por-familia")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--usar-ensemble", action="store_true",
                        help="mede o consenso de engines nas faixas de fallback")
    parser.add_argument("--sem-geometria", action="store_true",
                        help="lê sem a caixa pela geometria da linha (F112), "
                             "que a exportação liga — para o A/B dela")
    args = parser.parse_args(argv)

    if not args.manifesto.exists():
        raise FileNotFoundError(args.manifesto)
    identidade = identidade_do_manifesto(args.manifesto)
    paginas = paginas_do_manifesto(args.manifesto)
    if not paginas:
        raise SystemExit("o manifesto não tem página com referência")

    from core import livro
    from core.editorial_legacy import leitor_de_faixa_com_ensemble
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
        def ler_faixa_base(imagem, i=idioma):
            return ocr_service.tesseract_faixa_detalhada_conf(imagem, i)
        if args.usar_ensemble:
            ler_faixa_base = leitor_de_faixa_com_ensemble(
                ler_faixa_base, ocr_service, idioma, modelo_de_linha=False)
        ler_faixa = _leitor_memorizado(ler_faixa_base)
        numeros = [pagina["page_index"] - pagina["page_index_base"]
                   for pagina in do_pdf]
        lidas = list(livro.extrair(
            str(pdf), classificar, paginas=numeros,
            ler_pagina=ler, ler_faixa=ler_faixa,
            fusao="palavra", diagramas="recorte",
            idioma_ocr=idioma, dpi=args.dpi,
            candidatas=(None if args.sem_geometria
                        else service.candidatas)))
        if len(lidas) != len(do_pdf):
            esperado = len(do_pdf)
            medidas.extend(_medidas_sem_saida(
                do_pdf,
                f"leitor retornou {len(lidas)} página(s), esperado {esperado}"))
            continue
        for pagina, lida in zip(do_pdf, lidas):
            if not pagina["referencia"].exists():
                medidas.append({**_sem_pdf(pagina),
                                "erro": f"referência ausente: {pagina['referencia']}"})
                continue
            referencia = _ler_referencia(pagina["referencia"])
            medicao = _medir_referencia(
                referencia, _predicao_estruturada(lida), pagina["id"])
            medidas.append({
                "id": pagina["id"], "documento": pagina["documento"],
                "page_index": pagina["page_index"],
                "dificuldade": pagina["dificuldade"],
                "familias": sorted(familias_de_pagina.familias(
                    lida, declaradas=pagina["declaradas"])),
                "principal": familias_de_pagina.principal(
                    lida, declaradas=pagina["declaradas"]),
                "metricas": medicao["metricas"],
                "semantica": medicao["semantica"],
            })

    totais = _totais(medidas)
    semanticas = _totais_semanticos(medidas)
    cobertura = familias_de_pagina.resumo(
        medidas, minimo=args.minimo_por_familia)
    limites = {
        "max_cer_total": args.max_cer_total,
        "max_cer_prosa": args.max_cer_prosa,
        "max_cer_notacao": args.max_cer_notacao,
        "min_fen_exato": args.min_fen_exato,
        "min_fen_legal": args.min_fen_legal,
        "min_notacao_exata": args.min_notacao_exata,
        "min_notacao_legal": args.min_notacao_legal,
        "exigir_ordem_layout": args.exigir_ordem_layout,
    }
    falhas_qualidade = falhas_de_qualidade(
        totais, cobertura, max_cer_total=args.max_cer_total,
        max_cer_prose=args.max_cer_prosa,
        max_cer_notation=args.max_cer_notacao,
        exigir_cobertura=args.exigir_cobertura,
        semanticas=semanticas,
        min_diagram_exact=args.min_fen_exato,
        min_diagram_legal=args.min_fen_legal,
        min_notation_exact=args.min_notacao_exata,
        min_notation_legal=args.min_notacao_legal,
        exigir_ordem_layout=args.exigir_ordem_layout,
    )
    falhas_qualidade.extend(
        f"{medida['id']}: {medida['erro']}"
        for medida in medidas if medida.get("erro"))
    if args.comparar_com is not None:
        baseline_path = args.comparar_com.resolve()
        anterior = _carregar_rodada(baseline_path)
    else:
        encontrada = _ultima_rodada_com_caminho(args.rodadas)
        baseline_path = encontrada[0].resolve() if encontrada else None
        anterior = encontrada[1] if encontrada else None
    if anterior is not None and baseline_path is not None:
        _validar_baseline(anterior, identidade, baseline_path)
    antes = _cer_por_pagina(anterior)
    pioraram = pioras(medidas, antes, args.tolerancia)
    falhas_comparacao = _falhas_de_comparacao(pioraram)
    falhas_gate = [*falhas_qualidade, *falhas_comparacao]

    rodada = {
        "data": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "rotulo": args.rotulo,
        "manifesto": str(args.manifesto),
        "corpus": identidade,
        "engine": ("livro.extrair+ensemble" if args.usar_ensemble
                    else "livro.extrair"),
        "config": {
            "dpi": args.dpi,
            "fusao": "palavra",
            "diagramas": "recorte",
            "geometria": not args.sem_geometria,
            "ensemble": bool(args.usar_ensemble),
        },
        "comparison": {
            "baseline": str(baseline_path) if baseline_path else None,
            "baseline_corpus_sha256": (
                str((anterior.get("corpus") or {}).get("corpus_sha256") or "")
                if anterior else None),
            "matched_pages": len(antes),
        },
        "tempo_s": round(time.time() - inicio, 1),
        "paginas": medidas,
        "totais": totais,
        "semanticas": semanticas,
        "cobertura": cobertura,
        "quality_gate": {
            "enabled": bool(args.exigir_cobertura or any(
                valor is not None for chave, valor in limites.items()
                if chave != "exigir_ordem_layout")
                 or args.exigir_ordem_layout or anterior is not None
                 or bool(falhas_gate)),
            "passed": not falhas_gate,
            "limits": limites,
            "require_coverage": bool(args.exigir_cobertura),
            "failures": falhas_gate,
        },
    }
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
    if semanticas.get("diagrams"):
        diagramas = semanticas["diagrams"]
        print("semântica: FEN exato "
              f"{_percentual(float(diagramas['acuracia_exata'] or 0))}  "
              "legalidade "
              f"{_percentual(float(diagramas['acuracia_legal'] or 0))}")
    if semanticas.get("notation"):
        notacao = semanticas["notation"]
        print("semântica: notação exata "
              f"{_percentual(float(notacao['acuracia_exata'] or 0))}  "
              "legalidade "
              f"{_percentual(float(notacao['acuracia_legal'] or 0))}")
    cobertura = rodada["cobertura"]
    print("cobertura por família: "
          + ", ".join(f"{familia} {n}" for familia, n in cobertura["cobertura"].items()))
    if cobertura["faltando"]:
        print(f"famílias com menos de {cobertura['minimo_por_familia']} páginas: "
              + ", ".join(cobertura["faltando"])
              + "  ← é o que o corpus ainda não mede")
    for documento, faltantes in cobertura.get("faltando_por_livro", {}).items():
        if faltantes:
            print(f"  {documento}: faltam " + ", ".join(faltantes))
    if falhas_gate:
        print("GATE DE QUALIDADE REPROVADO:")
        for falha in falhas_gate:
            print(f"  {falha}")

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
    if falhas_gate:
        return 1
    return 0


def _sem_pdf(pagina: dict) -> dict:
    return {"id": pagina["id"], "documento": pagina["documento"],
            "page_index": pagina["page_index"],
            "dificuldade": pagina["dificuldade"],
            "familias": list(pagina["declaradas"]),
            "principal": (pagina["declaradas"] or ["prosa"])[0], "metricas": None}


def _medidas_sem_saida(paginas: list[dict], erro: str) -> list[dict]:
    """Mantém a cardinalidade do manifesto quando o leitor falha parcialmente."""
    return [{**_sem_pdf(pagina), "erro": erro}
            for pagina in paginas]


if __name__ == "__main__":
    raise SystemExit(main())
