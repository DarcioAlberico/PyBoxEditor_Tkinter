"""A medida do corpus de referência, sem o script em volta (PD-23).

O que está aqui é o miolo de `scripts/rodada_do_corpus.py`: ler o manifesto,
rodar o leitor de produção — `livro.extrair` com fusão por palavra, o mesmo de
"Exportar Livro" — em cada página com referência humana, e medir CER e WER de
prosa e notação. O script continua sendo quem grava a rodada, compara com a
anterior e aplica o portão de qualidade; ele importa daqui.

**Por que saiu do script.** O treino da rede de glifos precisa desta medida para
decidir se o peso que acabou de gravar pode ficar no lugar do anterior
(`core/portao_do_modelo.py`), e o núcleo não importa script. O retreino de
2026-11-09 mostrou o custo de não medir: validação de 99,7% no split e, no
corpus, a notação com o dobro de erro (0,97% → 1,99%), em produção sem ninguém
saber.

`medir_paginas` recebe o serviço de glifos pronto, e não o carrega: é assim que
o portão mede dois pesos diferentes no mesmo processo.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from core import familias_de_pagina
from core.ocr_ab import medir_por_dominio
from core.ocr_benchmark import medir_pagina
from core.log import logger
from core.ocr_corpus import carregar_manifesto

log = logger(__name__)


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


def medir_paginas(paginas: list[dict], service: Any, ocr_service: Any, *,
                  dpi: int = 300, ensemble: bool = False, geometria: bool = True,
                  avisar: Callable[[str], None] | None = None) -> list[dict]:
    """A medida de cada página do manifesto, na ordem dele.

    `service` é o `LearningService` com o peso a medir já carregado; `ocr_service`,
    o do Tesseract. Página sem PDF ou sem referência volta com `metricas` vazia e
    o motivo em `erro`, e não some: quem compara rodadas precisa saber que ela
    não foi medida, e não que ela não existe.
    """
    from core import livro
    from core.editorial_legacy import leitor_de_faixa_com_ensemble

    avisar = avisar or log.info
    medidas: list[dict] = []
    por_pdf: dict[Path, list[dict]] = {}
    for pagina in paginas:
        por_pdf.setdefault(pagina["pdf"], []).append(pagina)

    for pdf, do_pdf in por_pdf.items():
        if not pdf.exists():
            for pagina in do_pdf:
                medidas.append({**_sem_pdf(pagina), "erro": f"PDF ausente: {pdf}"})
            avisar(f"{pdf}: ausente — {len(do_pdf)} página(s) puladas")
            continue
        idioma = do_pdf[0]["idioma"]
        classificar = service.leitor_de_texto(idioma)
        ler = _leitor_memorizado(
            lambda imagem, i=idioma: ocr_service.tesseract_pagina_detalhada_conf(imagem, i))

        def ler_faixa_base(imagem, i=idioma):
            return ocr_service.tesseract_faixa_detalhada_conf(imagem, i)
        if ensemble:
            ler_faixa_base = leitor_de_faixa_com_ensemble(
                ler_faixa_base, ocr_service, idioma, modelo_de_linha=False)
        ler_faixa = _leitor_memorizado(ler_faixa_base)
        numeros = [pagina["page_index"] - pagina["page_index_base"]
                   for pagina in do_pdf]
        lidas = list(livro.extrair(
            str(pdf), classificar, paginas=numeros,
            ler_pagina=ler, ler_faixa=ler_faixa,
            fusao="palavra", diagramas="recorte",
            idioma_ocr=idioma, dpi=dpi,
            candidatas=service.candidatas if geometria else None))
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
    return medidas
