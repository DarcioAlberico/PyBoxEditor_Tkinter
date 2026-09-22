"""Métricas e contrato de benchmark para OCR de documentos.

O módulo não executa nenhum engine. Ele compara uma referência (ground truth)
com uma predição produzida por qualquer engine, permitindo medir reconhecimento
de texto e estrutura separadamente.

Formato mínimo de página:

    {
        "text": "texto completo",
        "lines": ["primeira linha", "segunda linha"],
        "paragraphs": ["primeiro parágrafo"],
        "regions": [{"type": "body", "order": 0}],
        "boxes": [{"char": "A", "x1": 1, "y1": 2, "x2": 9, "y2": 14}]
    }

Todos os campos estruturais são opcionais. A métrica correspondente fica
indisponível quando não existe referência e predição para aquele campo.
"""

from __future__ import annotations

import json
import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def normalizar_texto(texto: str, *, ignorar_maiusculas: bool = False) -> str:
    """Normaliza texto sem apagar pontuação ou espaços significativos."""
    valor = unicodedata.normalize("NFKC", str(texto)).replace("\r\n", "\n")
    valor = valor.replace("\r", "\n")
    valor = "\n".join(" ".join(linha.split()) for linha in valor.split("\n"))
    valor = valor.strip()
    return valor.casefold() if ignorar_maiusculas else valor


def tokenizar(texto: str, *, ignorar_maiusculas: bool = False) -> list[str]:
    """Divide palavras e pontuação, preservando a pontuação como token."""
    return _TOKEN_RE.findall(normalizar_texto(texto,
                                             ignorar_maiusculas=ignorar_maiusculas))


def distancia_edicao(esquerda: Sequence[Any], direita: Sequence[Any]) -> int:
    """Distância de Levenshtein com memória linear."""
    if len(esquerda) < len(direita):
        esquerda, direita = direita, esquerda
    anterior = list(range(len(direita) + 1))
    for i, item_esquerda in enumerate(esquerda, 1):
        atual = [i]
        for j, item_direita in enumerate(direita, 1):
            atual.append(min(
                atual[-1] + 1,
                anterior[j] + 1,
                anterior[j - 1] + (item_esquerda != item_direita),
            ))
        anterior = atual
    return anterior[-1]


def taxa_erro(referencia: Sequence[Any], predicao: Sequence[Any]) -> tuple[int, int, float]:
    erros = distancia_edicao(referencia, predicao)
    total = len(referencia)
    return erros, total, (erros / total if total else (0.0 if not predicao else 1.0))


def _percentual(acertos: int, total: int) -> float | None:
    return 100.0 * acertos / total if total else None


@dataclass
class TextMetrics:
    erros: int
    total: int
    cer: float
    referencia: str
    predicao: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SequenceMetrics:
    erros: int
    total: int
    taxa_erro: float
    itens_exatos: int
    acuracia_exata: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BoxMetrics:
    referencia: int
    predicao: int
    casados: int
    certos: int
    espurios: int
    perdidos: int
    precisao: float | None
    recall: float | None
    f1: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LayoutMetrics:
    referencia: int
    predicao: int
    tipos_corretos: int
    ordem_corretamente_classificada: bool | None
    acuracia_tipos: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PageMetrics:
    page_id: str
    text: TextMetrics | None = None
    words: TextMetrics | None = None
    lines: SequenceMetrics | None = None
    paragraphs: SequenceMetrics | None = None
    boxes: BoxMetrics | None = None
    layout: LayoutMetrics | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        resultado: dict[str, Any] = {"page_id": self.page_id}
        for nome in ("text", "words", "lines", "paragraphs", "boxes", "layout"):
            valor = getattr(self, nome)
            if valor is not None:
                resultado[nome] = valor.to_dict()
        if self.metadata:
            resultado["metadata"] = self.metadata
        return resultado


@dataclass
class AggregateMetrics:
    pages: int
    text: TextMetrics | None
    words: TextMetrics | None
    lines: SequenceMetrics | None
    paragraphs: SequenceMetrics | None
    boxes: BoxMetrics | None
    layout: LayoutMetrics | None
    page_results: list[PageMetrics] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        resultado: dict[str, Any] = {"pages": self.pages}
        for nome in ("text", "words", "lines", "paragraphs", "boxes", "layout"):
            valor = getattr(self, nome)
            if valor is not None:
                resultado[nome] = valor.to_dict()
        resultado["page_results"] = [pagina.to_dict() for pagina in self.page_results]
        if self.metadata:
            resultado["metadata"] = dict(self.metadata)
        return resultado


def _texto(dados: Mapping[str, Any]) -> str:
    return str(dados.get("text", ""))


def _sequencia(referencia: Sequence[str], predicao: Sequence[str],
               *, ignorar_maiusculas: bool) -> SequenceMetrics:
    ref = [normalizar_texto(v, ignorar_maiusculas=ignorar_maiusculas) for v in referencia]
    pred = [normalizar_texto(v, ignorar_maiusculas=ignorar_maiusculas) for v in predicao]
    erros, total, taxa = taxa_erro(ref, pred)
    return SequenceMetrics(
        erros=erros,
        total=total,
        taxa_erro=taxa,
        itens_exatos=sum(a == b for a, b in zip(ref, pred)) if len(ref) == len(pred) else 0,
        acuracia_exata=(1.0 if ref == pred else 0.0) if ref or pred else None,
    )


def _boxes(dados: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    valor = dados.get("boxes", [])
    return [item for item in valor if isinstance(item, Mapping)]


def _centro_dentro(gerado: Mapping[str, Any], rotulado: Mapping[str, Any]) -> bool:
    cx = (float(gerado["x1"]) + float(gerado["x2"])) / 2
    cy = (float(gerado["y1"]) + float(gerado["y2"])) / 2
    return (float(rotulado["x1"]) <= cx <= float(rotulado["x2"])
            and float(rotulado["y1"]) <= cy <= float(rotulado["y2"]))


def _iou(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    ix = max(0.0, min(float(a["x2"]), float(b["x2"]))
             - max(float(a["x1"]), float(b["x1"])))
    iy = max(0.0, min(float(a["y2"]), float(b["y2"]))
             - max(float(a["y1"]), float(b["y1"])))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    area_a = max(0.0, float(a["x2"]) - float(a["x1"])) * max(0.0, float(a["y2"]) - float(a["y1"]))
    area_b = max(0.0, float(b["x2"]) - float(b["x1"])) * max(0.0, float(b["y2"]) - float(b["y1"]))
    uniao = area_a + area_b - inter
    return inter / uniao if uniao > 0 else 0.0


def medir_boxes(referencia: Sequence[Mapping[str, Any]],
                predicao: Sequence[Mapping[str, Any]],
                *, ignorar_maiusculas: bool = False) -> BoxMetrics:
    """Mede detecção e caractere correto com casamento um-para-um.

    O centro da caixa prevista deve cair na caixa de referência. Em candidatos
    concorrentes, o maior IoU vence. Caixas sem coordenadas válidas são ignoradas
    para evitar que uma predição malformada derrube o benchmark inteiro.
    """
    ref = [b for b in referencia if all(k in b for k in ("x1", "y1", "x2", "y2"))]
    pred = [b for b in predicao if all(k in b for k in ("x1", "y1", "x2", "y2"))]
    usados: set[int] = set()
    casados = certos = 0
    for esperado in ref:
        candidatos = [(i, _iou(previsto, esperado)) for i, previsto in enumerate(pred)
                      if i not in usados and _centro_dentro(previsto, esperado)]
        if not candidatos:
            continue
        i, _ = max(candidatos, key=lambda item: item[1])
        usados.add(i)
        casados += 1
        a = normalizar_texto(str(pred[i].get("char", "")),
                             ignorar_maiusculas=ignorar_maiusculas)
        b = normalizar_texto(str(esperado.get("char", "")),
                             ignorar_maiusculas=ignorar_maiusculas)
        certos += a == b
    espurios = len(pred) - casados
    perdidos = len(ref) - casados
    precisao = _percentual(certos, len(pred))
    recall = _percentual(certos, len(ref))
    f1 = (2 * precisao * recall / (precisao + recall)
          if precisao is not None and recall is not None and precisao + recall
          else None)
    return BoxMetrics(len(ref), len(pred), casados, certos, espurios, perdidos,
                      precisao, recall, f1)


def medir_layout(referencia: Sequence[Mapping[str, Any]],
                 predicao: Sequence[Mapping[str, Any]]) -> LayoutMetrics:
    ref = list(referencia)
    pred = list(predicao)
    tipos_ref = [str(item.get("type", "unknown")) for item in ref]
    tipos_pred = [str(item.get("type", "unknown")) for item in pred]
    corretos = sum(a == b for a, b in zip(tipos_ref, tipos_pred))
    # Acurácia de tipo não pode esconder regiões extras ou ausentes: a ordem
    # só é correta quando a sequência completa coincide.
    return LayoutMetrics(
        referencia=len(ref),
        predicao=len(pred),
        tipos_corretos=corretos,
        ordem_corretamente_classificada=(tipos_ref == tipos_pred) if ref or pred else None,
        acuracia_tipos=_percentual(corretos, max(len(ref), len(pred))),
    )


def medir_pagina(page_id: str, referencia: Mapping[str, Any],
                 predicao: Mapping[str, Any], *,
                 ignorar_maiusculas: bool = False,
                 metadata: Mapping[str, Any] | None = None) -> PageMetrics:
    resultado = PageMetrics(page_id=page_id, metadata=dict(metadata or {}))
    texto_ref = normalizar_texto(_texto(referencia), ignorar_maiusculas=ignorar_maiusculas)
    texto_pred = normalizar_texto(_texto(predicao), ignorar_maiusculas=ignorar_maiusculas)
    erros, total, cer = taxa_erro(list(texto_ref), list(texto_pred))
    resultado.text = TextMetrics(erros, total, cer, texto_ref, texto_pred)

    tokens_ref = tokenizar(texto_ref)
    tokens_pred = tokenizar(texto_pred)
    erros, total, wer = taxa_erro(tokens_ref, tokens_pred)
    resultado.words = TextMetrics(erros, total, wer, " ".join(tokens_ref), " ".join(tokens_pred))

    for campo in ("lines", "paragraphs"):
        if campo in referencia and campo in predicao:
            setattr(resultado, campo, _sequencia(referencia[campo], predicao[campo],
                                                 ignorar_maiusculas=ignorar_maiusculas))
    if "boxes" in referencia and "boxes" in predicao:
        resultado.boxes = medir_boxes(_boxes(referencia), _boxes(predicao),
                                      ignorar_maiusculas=ignorar_maiusculas)
    if "regions" in referencia and "regions" in predicao:
        resultado.layout = medir_layout(referencia["regions"], predicao["regions"])
    return resultado


def _agregar_texto(resultados: Iterable[PageMetrics], campo: str) -> TextMetrics | None:
    itens = [getattr(item, campo) for item in resultados if getattr(item, campo) is not None]
    if not itens:
        return None
    erros = sum(item.erros for item in itens)
    total = sum(item.total for item in itens)
    return TextMetrics(erros, total, erros / total if total else 0.0,
                       "", "")


def _agregar_sequencia(resultados: Iterable[PageMetrics], campo: str) -> SequenceMetrics | None:
    itens = [getattr(item, campo) for item in resultados if getattr(item, campo) is not None]
    if not itens:
        return None
    erros = sum(item.erros for item in itens)
    total = sum(item.total for item in itens)
    exatos = sum(item.itens_exatos for item in itens)
    return SequenceMetrics(erros, total, erros / total if total else 0.0, exatos,
                           sum(item.acuracia_exata or 0.0 for item in itens) / len(itens))


def _agregar_boxes(resultados: Iterable[PageMetrics]) -> BoxMetrics | None:
    itens = [item.boxes for item in resultados if item.boxes is not None]
    if not itens:
        return None
    ref = sum(item.referencia for item in itens)
    pred = sum(item.predicao for item in itens)
    casados = sum(item.casados for item in itens)
    certos = sum(item.certos for item in itens)
    precisao = _percentual(certos, pred)
    recall = _percentual(certos, ref)
    f1 = (2 * precisao * recall / (precisao + recall)
          if precisao is not None and recall is not None and precisao + recall
          else None)
    return BoxMetrics(ref, pred, casados, certos, pred - casados, ref - casados,
                      precisao, recall, f1)


def _agregar_layout(resultados: Iterable[PageMetrics]) -> LayoutMetrics | None:
    itens = [item.layout for item in resultados if item.layout is not None]
    if not itens:
        return None
    ref = sum(item.referencia for item in itens)
    pred = sum(item.predicao for item in itens)
    corretos = sum(item.tipos_corretos for item in itens)
    ordens = [item.ordem_corretamente_classificada for item in itens
              if item.ordem_corretamente_classificada is not None]
    return LayoutMetrics(ref, pred, corretos,
                         all(ordens) if ordens else None,
                         _percentual(corretos, max(ref, pred)))


def agregar(resultados: Sequence[PageMetrics], *, metadata: Mapping[str, Any] | None = None) -> AggregateMetrics:
    return AggregateMetrics(
        pages=len(resultados),
        text=_agregar_texto(resultados, "text"),
        words=_agregar_texto(resultados, "words"),
        lines=_agregar_sequencia(resultados, "lines"),
        paragraphs=_agregar_sequencia(resultados, "paragraphs"),
        boxes=_agregar_boxes(resultados),
        layout=_agregar_layout(resultados),
        page_results=list(resultados),
        metadata=dict(metadata or {}),
    )


def carregar_json(caminho: str | Path) -> dict[str, Any]:
    with Path(caminho).open(encoding="utf-8") as arquivo:
        valor = json.load(arquivo)
    if not isinstance(valor, dict):
        raise ValueError(f"Esperado objeto JSON em {caminho}")
    return valor


def assinatura_manifesto(caminho: str | Path) -> str:
    """Calcula uma assinatura estável dos pares avaliados no manifesto.

    A assinatura inclui os bytes dos JSONs de referência e predição, além dos
    ids e caminhos relativos. Assim, um relatório pode ser associado ao
    conteúdo efetivamente medido mesmo quando o arquivo do manifesto mantém o
    mesmo nome.
    """
    manifesto_path = Path(caminho)
    manifesto = carregar_json(manifesto_path)
    paginas = manifesto.get("pages")
    if not isinstance(paginas, list):
        raise ValueError("O manifesto precisa conter 'pages' como lista")
    digest = hashlib.sha256()
    digest.update(b"pyboxeditor-ocr-benchmark-v1\0")
    for numero, pagina in enumerate(paginas, 1):
        if not isinstance(pagina, Mapping):
            raise ValueError(f"Página {numero} do manifesto não é um objeto")
        for chave in ("id", "reference", "prediction"):
            if chave not in pagina:
                raise ValueError(f"Página {numero} sem {chave!r}")
            valor = str(pagina[chave])
            digest.update(chave.encode("utf-8") + b"=" + valor.encode("utf-8") + b"\0")
        for chave in ("reference", "prediction"):
            arquivo = manifesto_path.parent / str(pagina[chave])
            if not arquivo.is_file():
                raise FileNotFoundError(str(arquivo))
            digest.update(chave.encode("utf-8") + b"\0")
            digest.update(arquivo.read_bytes())
    return digest.hexdigest()


def executar_manifesto(caminho: str | Path, *, ignorar_maiusculas: bool = False) -> AggregateMetrics:
    """Executa um manifesto.

    O manifesto contém ``pages``. Cada item deve possuir ``id``, ``reference``
    e ``prediction`` apontando para JSONs de página. Caminhos relativos são
    resolvidos a partir da pasta do manifesto.
    """
    manifesto_path = Path(caminho)
    manifesto = carregar_json(manifesto_path)
    paginas = manifesto.get("pages")
    if not isinstance(paginas, list):
        raise ValueError("O manifesto precisa conter 'pages' como lista")
    resultados = []
    for numero, pagina in enumerate(paginas, 1):
        if not isinstance(pagina, Mapping):
            raise ValueError(f"Página {numero} do manifesto não é um objeto")
        page_id = str(pagina.get("id", numero))
        try:
            ref_path = manifesto_path.parent / str(pagina["reference"])
            pred_path = manifesto_path.parent / str(pagina["prediction"])
        except KeyError as erro:
            raise ValueError(f"Página {page_id} sem caminho {erro.args[0]!r}") from erro
        resultados.append(medir_pagina(page_id, carregar_json(ref_path),
                                       carregar_json(pred_path),
                                       ignorar_maiusculas=ignorar_maiusculas,
                                       metadata={k: v for k, v in pagina.items()
                                                 if k not in {"id", "reference", "prediction"}}))
    return agregar(resultados, metadata={
        "manifest": str(manifesto_path),
        "corpus_sha256": assinatura_manifesto(manifesto_path),
        "ignore_case": ignorar_maiusculas,
    })


def salvar_relatorio(caminho: str | Path, relatorio: AggregateMetrics) -> None:
    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8") as arquivo:
        json.dump(relatorio.to_dict(), arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")
