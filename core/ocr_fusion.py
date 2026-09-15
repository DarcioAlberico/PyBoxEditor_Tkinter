"""Fusão de hipóteses e decodificação contextual inicial."""

from __future__ import annotations

import math
import unicodedata
from collections import defaultdict
from dataclasses import replace
from typing import Iterable, Sequence

from core.ocr_result import OCRHypothesis


PESOS_FONTE = {
    "manual": 1.10,
    "neural": 1.00,
    "learner": 0.98,
    "easyocr": 0.92,
    "paddleocr": 0.90,
    "tesseract": 0.85,
    "line": 0.92,
}


def _normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKC", texto or "").strip().casefold()


def _score(hipotese: OCRHypothesis, consenso: int) -> float:
    peso = PESOS_FONTE.get(hipotese.source, 0.80)
    # Consenso é bônus pequeno: duas respostas medianas não podem vencer uma
    # resposta muito forte apenas por votação.
    return hipotese.confidence * peso + min(0.20, max(0, consenso - 1) * 0.10)


def fundir(hipoteses: Sequence[OCRHypothesis], *, source: str = "fused"
           ) -> OCRHypothesis:
    """Escolhe a hipótese mais apoiada e preserva todas as alternativas."""
    validas = [item for item in hipoteses if item.text]
    if not validas:
        return OCRHypothesis("", 0.0, source, metadata={"reason": "no_text"})
    grupos: dict[str, list[OCRHypothesis]] = defaultdict(list)
    for item in validas:
        grupos[_normalizar(item.text)].append(item)
    melhor = max(validas, key=lambda item: _score(item, len(grupos[_normalizar(item.text)])))
    consenso = len(grupos[_normalizar(melhor.text)])
    score = min(1.0, _score(melhor, consenso))
    alternativas = []
    for item in sorted(validas, key=lambda item: _score(item, len(grupos[_normalizar(item.text)])), reverse=True):
        if item.text != melhor.text and item.text not in alternativas:
            alternativas.append(item.text)
    return replace(melhor, confidence=score, source=source,
                   alternatives=alternativas,
                   metadata={**melhor.metadata, "consensus": consenso,
                             "sources": sorted({item.source for item in validas})})


def decodificar_palavra(hipoteses: Sequence[OCRHypothesis],
                        dicionario: Iterable[str] = ()) -> OCRHypothesis:
    """Prefere uma palavra do dicionário somente quando há evidência visual.

    A palavra reconhecida continua sendo preservada em ``metadata`` quando a
    escolha contextual muda o resultado.
    """
    fundida = fundir(hipoteses)
    palavras = {_normalizar(item) for item in dicionario if item}
    if not palavras or _normalizar(fundida.text) in palavras:
        return fundida
    candidatas = [item for item in hipoteses if _normalizar(item.text) in palavras]
    if not candidatas:
        return fundida
    escolhida = max(candidatas, key=lambda item: item.confidence)
    if escolhida.confidence + 0.10 < fundida.confidence:
        return fundida
    return replace(escolhida, source="context", alternatives=list(dict.fromkeys(
        [fundida.text, *fundida.alternatives])),
        metadata={**fundida.metadata, "original_text": fundida.text,
                  "contextual_dictionary": True})


def decodificar_sequencia(candidatos: Sequence[Sequence[OCRHypothesis]], *,
                          dicionario: Iterable[str] = (), beam_width: int = 5
                          ) -> OCRHypothesis:
    """Beam search simples para uma sequência de glifos.

    Cada posição pode conter várias hipóteses. O score usa log-confiança; ao
    final, palavras presentes no dicionário recebem pequeno bônus.
    """
    if beam_width < 1:
        raise ValueError("beam_width deve ser positivo")
    beam: list[tuple[str, float, list[str]]] = [("", 0.0, [])]
    for posicao in candidatos:
        proximos = []
        for texto, score, fontes in beam:
            for hipotese in posicao:
                if not hipotese.text:
                    continue
                valor = max(1e-6, hipotese.confidence)
                proximos.append((texto + hipotese.text, score + math.log(valor),
                                 [*fontes, hipotese.source]))
        beam = sorted(proximos, key=lambda item: item[1], reverse=True)[:beam_width]
        if not beam:
            return OCRHypothesis("", 0.0, "context", metadata={"reason": "no_candidates"})
    palavras = {_normalizar(item) for item in dicionario if item}
    ranqueadas = [(texto, score + (0.25 if _normalizar(texto) in palavras else 0.0), fontes)
                  for texto, score, fontes in beam]
    texto, score, fontes = max(ranqueadas, key=lambda item: item[1])
    confianca = min(1.0, math.exp(score / max(1, len(candidatos))))
    alternativas = [item[0] for item in sorted(ranqueadas, key=lambda item: item[1], reverse=True)
                    if item[0] != texto]
    return OCRHypothesis(texto, confianca, "context", alternatives=alternativas,
                         metadata={"sources": fontes, "beam_width": beam_width,
                                   "dictionary_match": _normalizar(texto) in palavras})
