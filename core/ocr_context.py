"""Decodificação contextual conservadora para linhas OCR."""

from __future__ import annotations

import re
from dataclasses import replace
from core.ocr_benchmark import distancia_edicao
from core.ocr_language import LanguageModel, normalizar_palavra
from core.ocr_result import OCRHypothesis


_WORD = re.compile(r"[\wÀ-ÖØ-öø-ÿ]+", re.UNICODE)


class ContextDecoder:
    """Corrige apenas palavras próximas e conhecidas pelo modelo.

    A política nunca inventa uma correção distante. A palavra original é
    preservada em ``metadata`` e as alternativas ficam disponíveis para revisão.
    """

    def __init__(self, model: LanguageModel, *, max_distance: int | None = None,
                 minimum_gain: float = 0.12):
        self.model = model
        self.max_distance = max_distance
        self.minimum_gain = float(minimum_gain)

    def _best_word(self, word: str) -> tuple[str, float] | None:
        chave = normalizar_palavra(word)
        if not chave or self.model.conhece(chave):
            return None
        limite = self.max_distance if self.max_distance is not None else max(1, len(chave) // 3)
        candidates = []
        for item in self.model.palavras | self.model.dominio:
            item = normalizar_palavra(item)
            distance = distancia_edicao(chave, item)
            if distance <= limite:
                # Distância domina; frequência/domínio desempata.
                score = 1.0 - distance / max(len(chave), len(item), 1)
                score += 0.20 * self.model.score(item)
                candidates.append((score, item))
        if not candidates:
            return None
        return max(candidates)[1], max(candidates)[0]

    def decode(self, hypothesis: OCRHypothesis) -> OCRHypothesis:
        original = hypothesis.text
        replacements: list[tuple[str, str]] = []
        alternativas_originais = []
        for item in hypothesis.alternatives:
            # Admite tanto o contrato antigo (strings) quanto hipóteses
            # estruturadas produzidas pela fusão de engines.
            valor = getattr(item, "text", item)
            if str(valor) not in alternativas_originais:
                alternativas_originais.append(str(valor))

        def repl(match: re.Match[str]) -> str:
            word = match.group(0)
            best = self._best_word(word)
            if best is None or best[0] == normalizar_palavra(word):
                return word
            candidate, score = best
            # Exige melhora suficiente sobre a leitura desconhecida e respeita
            # caixa inicial, sem destruir capitalização de títulos.
            baseline = 1.0 - min(1.0, 1 / max(1, len(word)))
            if score - baseline < self.minimum_gain:
                return word
            corrected = candidate.capitalize() if word[:1].isupper() else candidate
            replacements.append((word, corrected))
            return corrected

        text = _WORD.sub(repl, original)
        if not replacements:
            return hypothesis
        return replace(hypothesis, text=text, source="context",
                       alternatives=list(dict.fromkeys([original, *alternativas_originais])),
                       metadata={**hypothesis.metadata, "original_text": original,
                                 "context_corrections": replacements})


def decodificar_linha(hypothesis: OCRHypothesis, model: LanguageModel,
                      **kwargs) -> OCRHypothesis:
    """Atalho funcional para o decoder contextual de linhas."""
    return ContextDecoder(model, **kwargs).decode(hypothesis)
