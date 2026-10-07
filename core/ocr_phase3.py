"""Reconhecimento, alinhamento, fusão e notação da Fase 3 — biblioteca de inspeção.

Este módulo é o seam entre engines de OCR e o resultado editorial. Ele não
decide por uma string isolada: cada leitura chega como hipótese, passa por uma
calibração explícita e sai com alternativas, alinhamento e motivo.

**Não é o leitor de produção.** Quem lê o livro é `core/livro.py` — a cadeia
própria de glifos ancorando o lance, o Tesseract lendo a prosa, a fusão
palavra a palavra —, e a fachada o usa por
`core.editorial_legacy.pipeline_de_producao`, como a janela. A `FusionEngine`
daqui escolhe por linha inteira, e 23 das 25 linhas da p. 30 do Aagaard são
mistas; em notação ela prefere a camada de texto do PDF, que nos livros do
corpus é OCR de fábrica (`docs/REVISAO_MODOS_OCR.md` §3.1). O que fica aqui
serve à fachada sem leitor — que lê a camada de texto de um PDF sem modelo
nenhum, e numa página digitalizada não lê nada — e à comparação de motores por
script (`scripts/processar_editorial.py --biblioteca --usar-engines`).
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

import numpy as np

from core.notacao import FIGURINAS, e_token_de_notacao, normalizar_saida
from core.ocr_language import LanguageModel
from core.ocr_result import LineResult, OCRHypothesis, PageResult, RegionResult, WordResult
from core.ocr_routing import OCRRouter


@dataclass(frozen=True)
class RecognitionContext:
    document_id: str
    page_index: int
    region_id: str
    line_id: str
    domain: str
    bbox: tuple[int, int, int, int] | None = None
    original_text: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


class Recognizer(Protocol):
    name: str
    capabilities: frozenset[str]

    def recognize(self, crop: Any, context: RecognitionContext
                  ) -> Sequence[OCRHypothesis]: ...


def _hypotheses(value: Any, source: str) -> list[OCRHypothesis]:
    if isinstance(value, OCRHypothesis):
        return [value]
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and isinstance(value[0], str):
            return [OCRHypothesis(value[0], float(value[1]), source)]
        resultado = []
        for item in value:
            resultado.extend(_hypotheses(item, source))
        return resultado
    if value is None:
        return []
    return [OCRHypothesis(str(value), 0.0, source)]


class CallableRecognizer:
    """Adapter pequeno para funções de engine e doubles de teste."""

    def __init__(self, name: str, function: Callable[..., Any], *,
                 capabilities: Iterable[str] = ("line", "confidence"),
                 model_version: str = ""):
        self.name = str(name)
        self._function = function
        self.capabilities = frozenset(str(item) for item in capabilities)
        self.model_version = str(model_version)

    def recognize(self, crop: Any, context: RecognitionContext) -> list[OCRHypothesis]:
        try:
            valor = self._function(crop, context)
        except TypeError as error:
            # Adapters antigos aceitam apenas o recorte. A tentativa é limitada
            # ao contrato de compatibilidade; erros de engine continuam sendo
            # tratados pelo registry da pipeline.
            try:
                valor = self._function(crop)
            except TypeError:
                raise error
        resultado = _hypotheses(valor, self.name)
        return [replace(item, source=item.source or self.name,
                        model_version=item.model_version or self.model_version)
                for item in resultado]


class RegistryRecognizer:
    """Adapter de ``EngineRegistry`` para o contrato de linha da Fase 3.

    A decisão de roteamento é executável: o nível primário é tentado primeiro
    e o fallback só é consultado quando não há texto. Falhas do primário não
    são apagadas quando o fallback recupera uma hipótese; elas continuam
    evidência de revisão no resultado editorial.
    """

    def __init__(self, registry: Any, *, level: str = "line",
                 consensus: bool = False):
        self.registry = registry
        self.level = str(level)
        self.consensus = bool(consensus)
        self.name = "engine_registry"
        self.capabilities = frozenset({self.level, "confidence"})
        self.errors: dict[str, str] = {}

    def recognize(self, crop: Any, context: RecognitionContext) -> list[OCRHypothesis]:
        self.errors = {}
        routing = context.metadata.get("routing", {}) if context.metadata else {}
        primary = str(routing.get("primary") or self.level)
        fallback = str(routing.get("fallback") or "")
        levels = [primary]
        if fallback and fallback != primary:
            levels.append(fallback)
        selected_level = primary
        hypotheses: list[OCRHypothesis] = []
        fallback_used = False
        for index, level in enumerate(levels):
            resultado = self.registry.recognize(crop, level=level)
            self.errors.update({
                str(name): str(message)
                for name, message in dict(getattr(resultado, "errors", {}) or {}).items()
            })
            current = list(getattr(resultado, "hypotheses", ()))
            tem_texto = any(str(item.text).strip() for item in current)
            if index == 0 or tem_texto:
                selected_level = level
                hypotheses = current
            if tem_texto:
                fallback_used = index > 0
                break

        def with_engine_errors(items: Sequence[OCRHypothesis]) -> list[OCRHypothesis]:
            if not self.errors:
                enriched = list(items)
            else:
                enriched = [replace(item, metadata={**item.metadata,
                                                     "engine_errors": dict(self.errors)})
                            for item in items]
            return [replace(item, metadata={
                **item.metadata,
                "ocr_level": selected_level,
                "routing_fallback": fallback_used,
            })
                    for item in enriched]

        if self.consensus and hasattr(resultado, "consolidate"):
            consolidated = resultado.consolidate()
            if consolidated.consensus:
                return with_engine_errors([consolidated.chosen])
            if consolidated.review_required:
                return with_engine_errors([replace(
                    item,
                    metadata={**item.metadata,
                              "ensemble_review_required": True,
                              "ensemble_reason_codes": list(consolidated.reason_codes),
                              "ensemble_alternatives": list(consolidated.alternatives)},
                ) for item in hypotheses])
        return with_engine_errors(hypotheses)


@dataclass(frozen=True)
class ConfidenceCalibrator:
    """Calibração logística simples, versionável e separada por domínio."""

    temperature: float = 1.0
    bias: float = 0.0
    domain_bias: Mapping[str, float] = field(default_factory=dict)
    source_bias: Mapping[str, float] = field(default_factory=dict)
    version: str = "calibration/v1"

    def __post_init__(self) -> None:
        if self.temperature <= 0:
            raise ValueError("temperature deve ser positiva")
        object.__setattr__(self, "domain_bias", dict(self.domain_bias))
        object.__setattr__(self, "source_bias", dict(self.source_bias))

    def calibrate(self, confidence: float, *, domain: str = "unknown",
                  source: str = "") -> float:
        valor = max(1e-6, min(1.0 - 1e-6, float(confidence)))
        logit = math.log(valor / (1.0 - valor))
        logit = (logit + self.bias + self.domain_bias.get(domain, 0.0)
                 + self.source_bias.get(source, 0.0)) / self.temperature
        return max(0.0, min(1.0, 1.0 / (1.0 + math.exp(-logit))))

    @classmethod
    def fit(cls, samples: Iterable[Mapping[str, Any]], *, version: str = "calibration/v1"):
        """Estima vieses por domínio/fonte sem tocar no holdout.

        Cada amostra precisa de ``confidence``, ``correct`` e pode informar
        ``domain``/``source``. O ajuste é deliberadamente pequeno: só aprende
        deslocamentos logísticos, evitando transformar um corpus curto em um
        modelo superajustado.
        """
        residuos: list[float] = []
        por_dominio: dict[str, list[float]] = {}
        por_fonte: dict[str, list[float]] = {}
        for sample in samples:
            confidence = max(1e-4, min(.9999, float(sample["confidence"])))
            alvo = .9 if bool(sample["correct"]) else .1
            residual = math.log(alvo / (1 - alvo)) - math.log(
                confidence / (1 - confidence))
            residuos.append(residual)
            por_dominio.setdefault(str(sample.get("domain", "unknown")), []).append(residual)
            por_fonte.setdefault(str(sample.get("source", "")), []).append(residual)
        def media(values):
            return sum(values) / len(values) if values else 0.0
        bias = media(residuos)
        return cls(
            bias=bias,
            domain_bias={key: media(value) - bias for key, value in por_dominio.items()},
            source_bias={key: media(value) - bias for key, value in por_fonte.items()},
            version=version,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ConfidenceCalibrator":
        return cls(float(data.get("temperature", 1.0)), float(data.get("bias", 0.0)),
                   dict(data.get("domain_bias", {})), dict(data.get("source_bias", {})),
                   str(data.get("version", "calibration/v1")))

    def to_dict(self) -> dict[str, Any]:
        return {"temperature": self.temperature, "bias": self.bias,
                "domain_bias": dict(self.domain_bias),
                "source_bias": dict(self.source_bias), "version": self.version}


@dataclass(frozen=True)
class AlignmentOperation:
    kind: str
    source_start: int
    source_end: int
    target_start: int
    target_end: int
    source_text: str
    target_text: str
    cost: float

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class AlignmentResult:
    source: str
    target: str
    operations: tuple[AlignmentOperation, ...]
    distance: float

    @property
    def normalized_distance(self) -> float:
        return self.distance / max(1, len(self.source), len(self.target))

    @property
    def changed(self) -> bool:
        return any(item.kind not in {"equal", "ligature"} for item in self.operations)

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target,
                "distance": self.distance,
                "normalized_distance": self.normalized_distance,
                "operations": [item.to_dict() for item in self.operations]}


def align_text(source: str, target: str, *, ligatures: Mapping[str, str] | None = None
               ) -> AlignmentResult:
    """Alinha duas leituras e marca ligaduras sem fabricar caixas."""
    source, target = str(source), str(target)
    ligatures = dict(ligatures or {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff",
                                  "ﬃ": "ffi", "ﬄ": "ffl"})
    n, m = len(source), len(target)
    costs = [[float("inf")] * (m + 1) for _ in range(n + 1)]
    choices: dict[tuple[int, int], tuple[str, int, int, float]] = {}
    costs[n][m] = 0.0
    for i in range(n, -1, -1):
        for j in range(m, -1, -1):
            if i == n and j == m:
                continue
            candidatos = []
            if i < n:
                candidatos.append((0.8 + costs[i + 1][j], "delete", 1, 0, 0.8))
            if j < m:
                candidatos.append((0.45 + costs[i][j + 1], "insert", 0, 1, 0.45))
            if i < n and j < m:
                iguais = source[i] == target[j]
                candidatos.append(((0.0 if iguais else 1.0) + costs[i + 1][j + 1],
                                   "equal" if iguais else "substitute", 1, 1,
                                   0.0 if iguais else 1.0))
                expansao = ligatures.get(source[i])
                if expansao and target.startswith(expansao, j):
                    candidatos.append((costs[i + 1][j + len(expansao)],
                                       "ligature", 1, len(expansao), 0.0))
            melhor = min(candidatos, key=lambda item: (item[0],
                                                        0 if item[1] in {"equal", "ligature"} else 1))
            costs[i][j] = melhor[0]
            choices[(i, j)] = melhor[1:]
    operations = []
    i = j = 0
    while i < n or j < m:
        kind, source_len, target_len, cost = choices[(i, j)]
        operations.append(AlignmentOperation(
            kind, i, i + source_len, j, j + target_len,
            source[i:i + source_len], target[j:j + target_len], cost,
        ))
        i += source_len
        j += target_len
    return AlignmentResult(source, target, tuple(operations), costs[0][0])


def align_tokens(source: str, target: str) -> AlignmentResult:
    """Alinhamento público por tokens, mantendo os espaços no texto-base."""
    origem = " ".join(str(source).split())
    destino = " ".join(str(target).split())
    return align_text(origem, destino)


@dataclass(frozen=True)
class FusionResult:
    chosen: OCRHypothesis
    alternatives: tuple[str, ...]
    calibrated_confidence: float
    reason_codes: tuple[str, ...]
    original_text: str | None = None
    warnings: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    review_required: bool = False
    alignment: AlignmentResult | None = None
    hypotheses: tuple[OCRHypothesis, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        def hypothesis(item: OCRHypothesis) -> dict[str, Any]:
            return {
                "text": item.text,
                "confidence": item.confidence,
                "source": item.source,
                "bbox": list(item.bbox) if item.bbox is not None else None,
                "alternatives": list(item.alternatives),
                "model_version": item.model_version,
                "preprocessing": item.preprocessing,
                "metadata": dict(item.metadata),
            }

        return {
            "chosen": hypothesis(self.chosen),
            "hypotheses": [hypothesis(item) for item in self.hypotheses],
            "alternatives": list(self.alternatives),
            "calibrated_confidence": self.calibrated_confidence,
            "reason_codes": list(self.reason_codes),
            "original_text": self.original_text,
            "warnings": list(self.warnings),
            "evidence_ids": list(self.evidence_ids),
            "review_required": self.review_required,
            "alignment": self.alignment.to_dict() if self.alignment else None,
        }


def _normal(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text or "")).strip().casefold()


class FusionEngine:
    """Escolhe uma leitura apoiada por confiança, léxico e domínio."""

    def __init__(self, calibrator: ConfidenceCalibrator | None = None,
                 *, language_model: LanguageModel | None = None,
                 minimum_margin: float = 0.08):
        if minimum_margin < 0:
            raise ValueError("minimum_margin não pode ser negativo")
        self.calibrator = calibrator or ConfidenceCalibrator()
        self.language_model = language_model
        self.minimum_margin = float(minimum_margin)

    def _lexical_bonus(self, text: str, domain: str) -> float:
        if self.language_model is None or domain not in {"prose", "header", "footer", "caption"}:
            return 0.0
        words = [item for item in re.findall(r"[\wÀ-ÿ]+", text)
                 if len(item) > 1]
        if not words:
            return 0.0
        return 0.10 * sum(self.language_model.conhece(item) for item in words) / len(words)

    def fuse(self, hypotheses: Sequence[OCRHypothesis], context: RecognitionContext,
             *, original_text: str | None = None) -> FusionResult:
        validas = [item for item in hypotheses if item.text]
        if not validas:
            vazio = OCRHypothesis("", 0.0, "fused")
            return FusionResult(vazio, (), 0.0, ("no_text",), review_required=True,
                                hypotheses=())
        baseline = original_text or next(
            (item.text for item in validas if item.source in {"pdf_text", "pdf_layer"}),
            "",
        )
        grupos: dict[str, list[OCRHypothesis]] = {}
        for item in validas:
            grupos.setdefault(_normal(item.text), []).append(item)
        ranqueadas = []
        for item in validas:
            confidence = self.calibrator.calibrate(
                item.confidence, domain=context.domain, source=item.source)
            score = confidence + min(.08, (.04 * (len(grupos[_normal(item.text)]) - 1)))
            lexical = self._lexical_bonus(item.text, context.domain)
            score += lexical
            ranqueadas.append((score, confidence, lexical, item))
        ranqueadas.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selected_score, calibrated, lexical, selected = ranqueadas[0]
        second_score = ranqueadas[1][0] if len(ranqueadas) > 1 else -float("inf")
        reasons = ["calibrated_confidence"]
        has_engine_errors = any(item.metadata.get("engine_errors") for item in validas)
        if has_engine_errors:
            reasons.append("engine_unavailable")
        if any(item.metadata.get("ensemble_review_required") for item in validas):
            reasons.append("ensemble_conflict")
        if len(grupos[_normal(selected.text)]) > 1:
            reasons.append("consensus")
        if lexical:
            reasons.append("lexicon_support")
        alternative_texts = tuple(dict.fromkeys(item.text for _, _, _, item in ranqueadas
                                              if item.text != selected.text))
        review_required = (selected_score - second_score < self.minimum_margin
                           or has_engine_errors
                           or any(item.metadata.get("ensemble_review_required")
                                  for item in validas))
        warnings = []
        if has_engine_errors:
            warnings.append("engine_unavailable_requires_review")
        if any(item.metadata.get("ensemble_review_required") for item in validas):
            warnings.append("ensemble_conflict_requires_review")
        if review_required:
            reasons.append("low_margin")
            warnings.append("fusion_margin_below_threshold")
        original = baseline if baseline and baseline != selected.text else None
        alignment = align_text(baseline, selected.text) if original else None
        if alignment and alignment.changed:
            reasons.extend(sorted({f"alignment_{item.kind}" for item in alignment.operations
                                   if item.kind not in {"equal"}}))
        if context.domain == "notation" and original:
            # Legalidade ou confiança de linha não substituem a evidência
            # visual. Até a Fase 4, a camada PDF permanece escolhida e a outra
            # leitura é uma alternativa que exige revisão.
            pdf = next((item for item in validas if item.text == baseline), None)
            if pdf is not None:
                selected = pdf
                calibrated = self.calibrator.calibrate(
                    pdf.confidence, domain=context.domain, source=pdf.source)
                reasons.extend(["notation_conflict", "original_preserved"])
                review_required = True
                warnings.append("notation_candidate_conflicts_with_original")
        if original and selected.text != original:
            reasons.append("original_preserved")
        metadata = {
            **selected.metadata, "original_text": original,
            "selected_source": selected.source,
            "calibration": self.calibrator.to_dict(),
        }
        chosen = replace(selected, confidence=max(0.0, min(1.0, calibrated)),
                         source="fused", alternatives=list(alternative_texts),
                         metadata=metadata)
        evidence_ids = tuple(str(item.metadata["evidence_id"]) for item in validas
                             if item.metadata.get("evidence_id"))
        return FusionResult(chosen, alternative_texts, chosen.confidence,
                            tuple(dict.fromkeys(reasons)), original, tuple(warnings),
                            evidence_ids, review_required, alignment,
                            tuple(validas))


@dataclass(frozen=True)
class NotationToken:
    original: str
    normalized: str
    kind: str
    start: int
    end: int
    valid_shape: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"original": self.original, "normalized": self.normalized,
                "kind": self.kind, "start": self.start, "end": self.end,
                "valid_shape": self.valid_shape, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class NotationSequence:
    original_text: str
    tokens: tuple[NotationToken, ...]
    variants: tuple["NotationSequence", ...] = ()
    warnings: tuple[str, ...] = ()
    initial_fen: str | None = None
    final_fen: str | None = None
    final_result: str | None = None

    @property
    def normalized_text(self) -> str:
        return " ".join(token.normalized for token in self.tokens
                         if token.kind not in {"comment", "variation_start", "variation_end"})

    def to_dict(self) -> dict[str, Any]:
        return {"original_text": self.original_text,
                "normalized_text": self.normalized_text,
                "tokens": [item.to_dict() for item in self.tokens],
                "variants": [item.to_dict() for item in self.variants],
                "warnings": list(self.warnings), "initial_fen": self.initial_fen,
                "final_fen": self.final_fen, "final_result": self.final_result}


_TOKEN_RE = re.compile(r"\{[^}]*\}|;[^\n]*|\(|\)|\$\d+|\d+\.(?:\.\.)?|1-0|0-1|1/2-1/2|½-½|[^\s()]+")
_RESULTS = {"1-0", "0-1", "1/2-1/2", "½-½"}


def _normalizar_token(token: str) -> str:
    valor = normalizar_saida(token)
    for figurina, letra in FIGURINAS.items():
        valor = valor.replace(figurina, letra)
    if valor in {"0-0", "0-0-0"}:
        return valor.replace("0", "O")
    return valor


class NotationParser:
    """Parser estrutural conservador para SAN/LAN e anotações editoriais."""

    def parse(self, text: str, *, initial_fen: str | None = None) -> NotationSequence:
        bruto = str(text or "")
        lexemas = [(match.group(), match.start(), match.end())
                   for match in _TOKEN_RE.finditer(bruto)]
        tokens, variants, warnings = self._parse_range(lexemas, 0, None)
        final_result = next((item.normalized for item in reversed(tokens)
                             if item.kind == "result"), None)
        final_fen = None
        if initial_fen:
            final_fen, legal_warnings = self._validate(tokens, initial_fen)
            warnings.extend(legal_warnings)
        return NotationSequence(bruto, tuple(tokens), tuple(variants), tuple(warnings),
                                initial_fen, final_fen, final_result)

    @staticmethod
    def _validate(tokens: Sequence[NotationToken], initial_fen: str):
        try:
            import chess
            board = chess.Board(initial_fen)
        except (ImportError, ValueError) as error:
            return None, [f"invalid_initial_fen:{error}"]
        warnings = []
        for token in tokens:
            if token.kind != "move":
                continue
            try:
                board.push(board.parse_san(token.normalized))
            except (chess.IllegalMoveError, chess.InvalidMoveError,
                    chess.AmbiguousMoveError) as error:
                code = "ambiguous_move" if isinstance(error, chess.AmbiguousMoveError) else "illegal_move"
                warnings.append(f"{code}:{token.original}")
        return board.fen(), warnings

    def _parse_range(self, lexemas, inicio: int, fim: int | None):
        tokens: list[NotationToken] = []
        variants: list[NotationSequence] = []
        warnings: list[str] = []
        i = inicio
        while i < len(lexemas) and (fim is None or i < fim):
            original, start, end = lexemas[i]
            if original == "(":
                fechamento = self._find_close(lexemas, i + 1)
                if fechamento is None:
                    warnings.append("unclosed_variation")
                    tokens.append(NotationToken(original, original, "variation_start",
                                                start, end))
                    i += 1
                    continue
                tokens.append(NotationToken(original, original, "variation_start", start, end))
                interior, nested, child_warnings = self._parse_range(
                    lexemas, i + 1, fechamento)
                if interior:
                    variante = NotationSequence(
                        " ".join(item[0] for item in lexemas[i + 1:fechamento]),
                        tuple(interior), tuple(nested), tuple(child_warnings),
                    )
                    variants.append(variante)
                tokens.append(NotationToken(")", ")", "variation_end",
                                            lexemas[fechamento][1], lexemas[fechamento][2]))
                i = fechamento + 1
                continue
            if original == ")":
                warnings.append("unexpected_variation_end")
                i += 1
                continue
            token = self._token(original, start, end)
            tokens.append(token)
            if token.kind == "unknown":
                warnings.append(f"unknown_token:{original}")
            i += 1
        return tokens, variants, warnings

    @staticmethod
    def _find_close(lexemas, inicio: int) -> int | None:
        depth = 1
        for index in range(inicio, len(lexemas)):
            if lexemas[index][0] == "(":
                depth += 1
            elif lexemas[index][0] == ")":
                depth -= 1
                if depth == 0:
                    return index
        return None

    @staticmethod
    def _token(original: str, start: int, end: int) -> NotationToken:
        normalized = _normalizar_token(original)
        if original.startswith("{") or original.startswith(";"):
            return NotationToken(original, original, "comment", start, end)
        if original.startswith("$"):
            return NotationToken(original, original, "nag", start, end, True)
        if re.fullmatch(r"\d+\.(?:\.\.)?", original):
            return NotationToken(original, original, "move_number", start, end, True)
        if original in _RESULTS:
            return NotationToken(original, normalized, "result", start, end, True)
        valido = e_token_de_notacao(original) or e_token_de_notacao(normalized)
        if valido:
            return NotationToken(original, normalized, "move", start, end, True)
        if re.fullmatch(r"[!?+#=±⩲⩱∞]+", original):
            return NotationToken(original, normalized, "annotation", start, end, True)
        return NotationToken(original, normalized, "unknown", start, end, False)


class Phase3Processor:
    """Reconhece linhas, funde engines e serializa notação no ``PageResult``."""

    def __init__(self, *, line_recognizers: Sequence[Recognizer] = (),
                 language_model: LanguageModel | None = None,
                 calibrator: ConfidenceCalibrator | None = None,
                 fusion: FusionEngine | None = None,
                 pdf_confidence: float = .72):
        if not 0.0 <= pdf_confidence <= 1.0:
            raise ValueError("pdf_confidence deve estar entre 0 e 1")
        self.line_recognizers = list(line_recognizers)
        self.language_model = language_model
        self.fusion = fusion or FusionEngine(calibrator, language_model=language_model)
        self.pdf_confidence = pdf_confidence
        self.parser = NotationParser()
        self.router = OCRRouter()

    @classmethod
    def from_ocr_service(cls, service: Any, *, languages: tuple[str, ...] = ("en",),
                         language: str = "en", gpu: bool = False,
                         trained_line: bool | None = None,
                         model_path: str | None = None,
                         meta_path: str | None = None,
                         consensus: bool = True,
                         **kwargs: Any) -> "Phase3Processor":
        """Liga os adapters opcionais já existentes sem inicializá-los agora."""
        from core.ocr_engines import OCRServiceAdapters
        registry = OCRServiceAdapters.registry(
            service, languages=languages, language=language, gpu=gpu,
            trained_line=trained_line, model_path=model_path, meta_path=meta_path,
        )
        return cls(line_recognizers=[RegistryRecognizer(registry,
                                                        consensus=consensus)], **kwargs)

    @staticmethod
    def _crop(image: Any, bbox: Sequence[int] | None) -> np.ndarray:
        if image is None or bbox is None:
            return np.empty((0, 0), dtype=np.uint8)
        x1, y1, x2, y2 = (int(item) for item in bbox)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(image.shape[1], x2), min(image.shape[0], y2)
        return image[y1:y2, x1:x2]

    @staticmethod
    def _overlaps(left: Sequence[int], right: Sequence[int]) -> bool:
        lx1, ly1, lx2, ly2 = (int(item) for item in left)
        rx1, ry1, rx2, ry2 = (int(item) for item in right)
        return min(lx2, rx2) > max(lx1, rx1) and min(ly2, ry2) > max(ly1, ry1)

    @staticmethod
    def _diagram_bboxes(evidence: Any) -> tuple[tuple[int, int, int, int], ...]:
        values = (getattr(evidence, "metadata", {}) or {}).get("diagram_bboxes", ())
        result = []
        for value in values or ():
            try:
                bbox = tuple(int(item) for item in value)
                if len(bbox) == 4 and bbox[2] > bbox[0] and bbox[3] > bbox[1]:
                    result.append(bbox)
            except (TypeError, ValueError):
                continue
        return tuple(result)

    @staticmethod
    def _is_table_block(block: Mapping[str, Any]) -> bool:
        tipo = str(block.get("type", "")).casefold()
        metadata = block.get("metadata") or {}
        return tipo in {"table", "tabela"} or bool(
            block.get("table") or metadata.get("table"))

    @staticmethod
    def _table_spec(block: Mapping[str, Any], evidence: Any,
                    order: int) -> dict[str, Any]:
        raw_rows = block.get("rows", block.get("cells", ())) or ()
        rows: list[list[str]] = []
        cell_boxes: list[list[Sequence[int] | None]] = []
        for raw_row in raw_rows:
            cells = (raw_row.get("cells", raw_row.get("columns", ()))
                     if isinstance(raw_row, Mapping) else raw_row)
            if not isinstance(cells, (list, tuple)):
                cells = (cells,)
            textos: list[str] = []
            caixas: list[Sequence[int] | None] = []
            for cell in cells:
                if isinstance(cell, Mapping):
                    spans = cell.get("spans", ()) or ()
                    text = cell.get("text")
                    if text is None:
                        text = "".join(str(span.get("text", ""))
                                       for span in spans if isinstance(span, Mapping))
                    caixas.append(cell.get("bbox"))
                else:
                    text, caixas_value = cell, None
                    caixas.append(caixas_value)
                textos.append(str(text or "").strip())
            rows.append(textos)
            cell_boxes.append(caixas)
        bbox = tuple(int(round(float(item))) for item in
                     (block.get("bbox") or (0, 0, evidence.width, evidence.height)))
        max_columns = max((len(row) for row in rows), default=0)
        linhas: list[tuple[str, tuple[int, int, int, int]]] = []
        for row_index, row in enumerate(rows):
            for column_index, text in enumerate(row):
                caixa = cell_boxes[row_index][column_index]
                if caixa is None:
                    largura = max(1, bbox[2] - bbox[0])
                    x1 = bbox[0] + (largura * column_index) // max(1, max_columns)
                    x2 = bbox[0] + (largura * (column_index + 1)) // max(1, max_columns)
                    altura = max(1, bbox[3] - bbox[1])
                    y1 = bbox[1] + (altura * row_index) // max(1, len(rows))
                    y2 = bbox[1] + (altura * (row_index + 1)) // max(1, len(rows))
                    caixa = (x1, y1, max(x1 + 1, x2), max(y1 + 1, y2))
                linhas.append((text, tuple(int(item) for item in caixa)))
        return {
            "id": f"region-{evidence.page_index:04d}-{order:04d}",
            "order": order, "bbox": bbox, "lines": linhas, "type": "table",
            "table_rows": rows, "table_shape": [len(row) for row in rows],
        }

    @staticmethod
    def _order_specs(specs: Sequence[dict[str, Any]], width: int
                     ) -> list[dict[str, Any]]:
        """Ordena caixas textuais em coluna, sem mover regiões especiais."""
        ordenadas = sorted(specs, key=lambda item: int(item["order"]))
        textuais = [item for item in ordenadas
                    if item.get("type") in {"prose", "notation"}]
        if len(textuais) < 2 or len(textuais) != len(ordenadas):
            return ordenadas
        centers = [((int(item["bbox"][0]) + int(item["bbox"][2])) / 2)
                   for item in textuais]
        if max(centers) - min(centers) <= width * .30:
            return ordenadas
        corte = (min(centers) + max(centers)) / 2
        ordenadas = sorted(
            ordenadas,
            key=lambda item: (
                0 if ((int(item["bbox"][0]) + int(item["bbox"][2])) / 2) < corte else 1,
                int(item["bbox"][1]), int(item["bbox"][0])),
        )
        return [{**item, "order": order} for order, item in enumerate(ordenadas)]

    @staticmethod
    def _raster_specs(evidence: Any) -> list[dict[str, Any]]:
        """Segmenta um scan em regiões/linhas antes de consultar os engines."""
        if evidence.raster is None:
            return []
        try:
            import cv2
        except ImportError:
            return []
        try:
            from core.ocr_layout import LayoutAnalyzer
            raster = np.asarray(evidence.raster)
            if raster.size == 0:
                return []
            # A evidência sintética/testada pode já ser uma máscara. Para um
            # scan normal, a variante adaptativa transforma fundo claro em
            # máscara de tinta; a escala permanece a da origem para as caixas
            # continuarem válidas no recorte original.
            escala = float((raster > 0).mean())
            if raster.ndim == 2 and 0.0005 <= escala <= 0.35:
                binaria = raster
            else:
                from core.preprocess import PreprocessConfig, preparar_adaptativo
                variante = preparar_adaptativo(
                    raster,
                    PreprocessConfig(target_dpi=int(evidence.raster_dpi),
                                     source_dpi=int(evidence.raster_dpi),
                                     methods=("auto",)),
                )
                binaria = variante.binary
            layout = LayoutAnalyzer().analyze(binaria)
        except (ImportError, TypeError, ValueError, cv2.error):
            return []
        if not layout.lines:
            return []

        diagram_bboxes = Phase3Processor._diagram_bboxes(evidence)
        specs: list[dict[str, Any]] = []
        for region_index, region in enumerate(layout.regions):
            rx1, ry1, rx2, ry2 = region.bbox
            linhas = []
            for detected in layout.lines:
                cx = (detected.x1 + detected.x2) / 2
                cy = (detected.y1 + detected.y2) / 2
                if (rx1 <= cx <= rx2 and ry1 <= cy <= ry2
                        and not any(Phase3Processor._overlaps(
                            (detected.x1, detected.y1, detected.x2, detected.y2),
                            diagram_bbox) for diagram_bbox in diagram_bboxes)):
                    linhas.append(("", (detected.x1, detected.y1,
                                         detected.x2, detected.y2)))
            if linhas:
                specs.append({
                    "id": f"region-{evidence.page_index:04d}-{region_index:04d}",
                    "order": region_index, "bbox": tuple(region.bbox),
                    "lines": linhas, "type": region.type,
                })
        return specs

    @staticmethod
    def _specs(evidence: Any) -> list[dict[str, Any]]:
        diagram_bboxes = Phase3Processor._diagram_bboxes(evidence)
        fallback_text = False
        table_specs = []
        blocks = []
        for source_index, item in enumerate(evidence.text_blocks):
            if Phase3Processor._is_table_block(item):
                table_specs.append(Phase3Processor._table_spec(
                    item, evidence, source_index))
                continue
            if item.get("type", 0) != 0:
                continue
            linhas = []
            for line in item.get("lines", []) or []:
                bbox = line.get("bbox") or item.get("bbox")
                if bbox and any(Phase3Processor._overlaps(bbox, diagram_bbox)
                                for diagram_bbox in diagram_bboxes):
                    continue
                linhas.append(line)
            if item.get("lines") and not linhas:
                continue
            if linhas != list(item.get("lines", []) or []):
                item = {**item, "lines": linhas}
            block_bbox = item.get("bbox")
            if (block_bbox and any(Phase3Processor._overlaps(block_bbox, diagram_bbox)
                                   for diagram_bbox in diagram_bboxes)
                    and not linhas):
                continue
            blocks.append({**item, "_source_index": source_index})
        if not blocks and evidence.text_layer.strip():
            fallback_text = True
            altura = max(16, evidence.height // max(1, len(evidence.text_layer.splitlines())))
            blocks = [{"bbox": [0, i * altura, evidence.width, (i + 1) * altura],
                       "lines": [{"bbox": [0, i * altura, evidence.width, (i + 1) * altura],
                                  "spans": [{"text": line, "size": 10}]}]}
                      for i, line in enumerate(evidence.text_layer.splitlines()) if line.strip()]
            blocks = [{**block, "_source_index": len(evidence.text_blocks) + index}
                      for index, block in enumerate(blocks)]
        if not blocks and not table_specs and evidence.raster is not None:
            raster_specs = Phase3Processor._raster_specs(evidence)
            if raster_specs:
                return raster_specs
            blocks = [{"bbox": [0, 0, evidence.width, evidence.height],
                       "lines": [{"bbox": [0, 0, evidence.width, evidence.height],
                                  "spans": [{"text": "", "size": 10}]}]}]
        specs = list(table_specs)
        for index, block in enumerate(blocks):
            linhas = []
            for line in block.get("lines", []) or []:
                text = "".join(str(span.get("text", ""))
                               for span in line.get("spans", [])).strip()
                if text or evidence.raster is not None:
                    bbox = tuple(int(round(float(item))) for item in
                                 (line.get("bbox") or block.get("bbox")))
                    if (not fallback_text and any(
                            Phase3Processor._overlaps(bbox, diagram_bbox)
                            for diagram_bbox in diagram_bboxes)):
                        continue
                    linhas.append((text, bbox))
            if linhas:
                region_type = ("notation" if any(Phase3Processor._domain(text) == "notation"
                                                 for text, _bbox in linhas)
                               else "prose")
                source_index = int(block.get("_source_index", index))
                specs.append({"id": f"region-{evidence.page_index:04d}-{source_index:04d}",
                              "order": source_index,
                              "bbox": tuple(block.get("bbox", (0, 0, 1, 1))),
                              "lines": linhas, "type": region_type})
        return Phase3Processor._order_specs(specs, evidence.width)

    @staticmethod
    def _domain(text: str) -> str:
        return "notation" if any(e_token_de_notacao(item)
                                  for item in text.split()) else "prose"

    @staticmethod
    def _words(text: str, bbox: tuple[int, int, int, int], line_id: str,
               confidence: float, original: str | None) -> list[WordResult]:
        resultado = []
        tokens = list(re.finditer(r"\S+", text))
        for index, token in enumerate(tokens):
            x1, y1, x2, y2 = bbox
            inicio = x1 + int((x2 - x1) * token.start() / max(1, len(text)))
            fim = x1 + int((x2 - x1) * token.end() / max(1, len(text)))
            resultado.append(WordResult(
                f"{line_id}-word-{index:03d}", token.group(), confidence,
                (inicio, y1, max(inicio + 1, fim), y2), line_id, "fused",
                original_text=(original if original and original != text else None),
            ))
        return resultado

    def process(self, evidence: Any, options: Any, token: Any) -> PageResult:
        specs = self._specs(evidence)
        lines: list[LineResult] = []
        words: list[WordResult] = []
        regions: list[RegionResult] = []
        fusions = []
        notation = []
        warnings = []
        engine_errors: dict[str, str] = {}
        routing: list[dict[str, Any]] = []
        for spec in specs:
            region_lines = []
            route_metadata = ({"domain": "notation"}
                              if spec.get("type") == "notation" else {})
            route = self.router.decide(RegionResult(
                spec["id"], spec.get("type", "prose"), spec["order"], .75,
                spec["bbox"], metadata=route_metadata,
            )).to_dict()
            routing.append(route)
            for line_index, (original, bbox) in enumerate(spec["lines"]):
                token.raise_if_cancelled()
                line_id = f"{spec['id']}-line-{line_index:03d}"
                domain = self._domain(original)
                context = RecognitionContext(
                    evidence.document_id, evidence.page_index, spec["id"], line_id,
                    domain, bbox, original,
                    metadata={"routing": route},
                )
                candidates = []
                line_engine_errors: dict[str, str] = {}
                if original:
                    candidates.append(OCRHypothesis(
                        original, self.pdf_confidence, "pdf_text", bbox=bbox,
                        metadata={"evidence_id": f"pdf-{evidence.page_index}-{line_id}"},
                    ))
                crop = self._crop(evidence.raster, bbox)
                for recognizer in self.line_recognizers:
                    try:
                        candidates.extend(recognizer.recognize(crop, context))
                        for engine, message in dict(getattr(recognizer, "errors", {}) or {}).items():
                            key = f"{getattr(recognizer, 'name', type(recognizer).__name__)}.{engine}"
                            engine_errors[key] = str(message)
                            line_engine_errors[key] = str(message)
                            warnings.append(f"engine_error:{key}:{message}")
                    except Exception as error:  # engine opcional isolado
                        warnings.append(f"{recognizer.name}:{type(error).__name__}: {error}")
                result = self.fusion.fuse(candidates, context, original_text=original or None)
                if result.review_required:
                    warnings.extend(result.warnings)
                fusion_data = result.to_dict()
                fusions.append({"line_id": line_id, **fusion_data})
                texto = result.chosen.text
                line = LineResult(
                    line_id, texto, result.calibrated_confidence, bbox=bbox,
                    region_id=spec["id"],
                    alternatives=[OCRHypothesis(item, result.calibrated_confidence,
                                                 "alternative")
                                 for item in result.alternatives],
                    warnings=list(result.warnings),
                    metadata={"domain": domain, "source": result.chosen.source,
                              "original_text": result.original_text,
                              "fusion": fusion_data, "routing": route,
                              "review_required": result.review_required},
                )
                line.warnings.extend(
                    f"engine_error:{key}:{message}"
                    for key, message in line_engine_errors.items()
                    if f"engine_error:{key}:{message}" not in line.warnings
                )
                if domain == "notation" and texto:
                    parsed = self.parser.parse(texto)
                    notation.append(parsed.to_dict())
                    line.metadata["notation"] = parsed.to_dict()
                    line.warnings.extend(parsed.warnings)
                line_words = self._words(texto, bbox, line_id,
                                         result.calibrated_confidence,
                                         result.original_text)
                line.word_ids = [item.id for item in line_words]
                words.extend(line_words)
                lines.append(line)
                region_lines.append(line)
            region_text = "\n".join(item.text for item in region_lines)
            confidence = (sum(item.confidence for item in region_lines)
                          / len(region_lines) if region_lines else 0.0)
            tipo = "table" if spec.get("type") == "table" else (
                "chess_sequence" if any(
                item.metadata.get("domain") == "notation" for item in region_lines
                ) else "paragraph")
            region_metadata = {
                "phase3": True,
                "routing": route,
                "review_required": any(
                    item.metadata.get("review_required") for item in region_lines),
            }
            if tipo == "table":
                rows = []
                inicio = 0
                for quantidade in spec.get("table_shape", ()):
                    fim = inicio + int(quantidade)
                    rows.append([item.text for item in region_lines[inicio:fim]])
                    inicio = fim
                if not rows:
                    rows = [list(row) for row in spec.get("table_rows", ())]
                region_metadata.update({"domain": "table",
                                        "rows": rows})
            else:
                region_metadata["domain"] = ("notation" if tipo == "chess_sequence"
                                              else "prose")
            regions.append(RegionResult(
                spec["id"], tipo, spec["order"], confidence, spec["bbox"],
                line_ids=[item.id for item in region_lines], text=region_text,
                warnings=[warning for item in region_lines for warning in item.warnings],
                metadata=region_metadata,
            ))
        return PageResult(
            page_id=f"page-{evidence.page_index:04d}",
            text="\n\n".join(region.text for region in regions),
            confidence=(sum(item.confidence for item in lines) / len(lines)
                        if lines else 0.0),
            regions=regions, lines=lines, words=words, warnings=warnings,
            metadata={"phase3": True, "fusions": fusions,
                      "notation_sequences": notation,
                      "engine_errors": engine_errors,
                      "routing": routing,
                      "recognizers": [getattr(item, "name", type(item).__name__)
                                      for item in self.line_recognizers]},
        )
