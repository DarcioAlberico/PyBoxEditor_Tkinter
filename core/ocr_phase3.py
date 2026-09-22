"""Reconhecimento, alinhamento, fusão e notação da Fase 3.

Este módulo é o seam entre engines de OCR e o resultado editorial. Ele não
decide por uma string isolada: cada leitura chega como hipótese, passa por uma
calibração explícita e sai com alternativas, alinhamento e motivo.
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
    """Adapter de ``EngineRegistry`` para o contrato de linha da Fase 3."""

    def __init__(self, registry: Any, *, level: str = "line"):
        self.registry = registry
        self.level = str(level)
        self.name = "engine_registry"
        self.capabilities = frozenset({self.level, "confidence"})

    def recognize(self, crop: Any, context: RecognitionContext) -> list[OCRHypothesis]:
        resultado = self.registry.recognize(crop, level=self.level)
        return list(getattr(resultado, "hypotheses", ()))


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "chosen": {"text": self.chosen.text, "confidence": self.chosen.confidence,
                       "source": self.chosen.source},
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
            return FusionResult(vazio, (), 0.0, ("no_text",), review_required=True)
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
        if len(grupos[_normal(selected.text)]) > 1:
            reasons.append("consensus")
        if lexical:
            reasons.append("lexicon_support")
        alternative_texts = tuple(dict.fromkeys(item.text for _, _, _, item in ranqueadas
                                              if item.text != selected.text))
        review_required = selected_score - second_score < self.minimum_margin
        warnings = []
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
                            evidence_ids, review_required, alignment)


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
                 pdf_confidence: float = .72,
                 context_decoder: Any | None = None):
        if not 0.0 <= pdf_confidence <= 1.0:
            raise ValueError("pdf_confidence deve estar entre 0 e 1")
        self.line_recognizers = list(line_recognizers)
        self.language_model = language_model
        self.fusion = fusion or FusionEngine(calibrator, language_model=language_model)
        self.pdf_confidence = pdf_confidence
        self.parser = NotationParser()
        if context_decoder is None and language_model is not None:
            from core.ocr_context import ContextDecoder
            context_decoder = ContextDecoder(language_model)
        self.context_decoder = context_decoder

    @classmethod
    def from_ocr_service(cls, service: Any, *, languages: tuple[str, ...] = ("en",),
                         language: str = "en", gpu: bool = False,
                         trained_line: bool | None = None,
                         model_path: str = "text_line_model.pth",
                         meta_path: str = "text_line_model.json",
                         **kwargs: Any) -> "Phase3Processor":
        """Liga os adapters opcionais já existentes sem inicializá-los agora."""
        from core.ocr_engines import OCRServiceAdapters
        registry = OCRServiceAdapters.registry(
            service, languages=languages, language=language, gpu=gpu,
            trained_line=trained_line, model_path=model_path, meta_path=meta_path,
        )
        return cls(line_recognizers=[RegistryRecognizer(registry)], **kwargs)

    @staticmethod
    def _crop(image: Any, bbox: Sequence[int] | None) -> np.ndarray:
        if image is None or bbox is None:
            return np.empty((0, 0), dtype=np.uint8)
        x1, y1, x2, y2 = (int(item) for item in bbox)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(image.shape[1], x2), min(image.shape[0], y2)
        return image[y1:y2, x1:x2]

    @staticmethod
    def _specs(evidence: Any) -> list[dict[str, Any]]:
        blocks = [item for item in evidence.text_blocks if item.get("type", 0) == 0]
        if not blocks and evidence.text_layer.strip():
            altura = max(16, evidence.height // max(1, len(evidence.text_layer.splitlines())))
            blocks = [{"bbox": [0, i * altura, evidence.width, (i + 1) * altura],
                       "lines": [{"bbox": [0, i * altura, evidence.width, (i + 1) * altura],
                                  "spans": [{"text": line, "size": 10}]}]}
                      for i, line in enumerate(evidence.text_layer.splitlines()) if line.strip()]
        if not blocks and evidence.raster is not None:
            blocks = [{"bbox": [0, 0, evidence.width, evidence.height],
                       "lines": [{"bbox": [0, 0, evidence.width, evidence.height],
                                  "spans": [{"text": "", "size": 10}]}]}]
        specs = []
        for index, block in enumerate(blocks):
            linhas = []
            for line in block.get("lines", []) or []:
                text = "".join(str(span.get("text", ""))
                               for span in line.get("spans", [])).strip()
                if text or evidence.raster is not None:
                    bbox = tuple(int(round(float(item))) for item in
                                 (line.get("bbox") or block.get("bbox")))
                    linhas.append((text, bbox))
            if linhas:
                specs.append({"id": f"region-{evidence.page_index:04d}-{index:04d}",
                              "order": index, "bbox": tuple(block.get("bbox", (0, 0, 1, 1))),
                              "lines": linhas})
        return specs

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
        for spec in specs:
            region_lines = []
            for line_index, (original, bbox) in enumerate(spec["lines"]):
                token.raise_if_cancelled()
                line_id = f"{spec['id']}-line-{line_index:03d}"
                domain = self._domain(original)
                context = RecognitionContext(
                    evidence.document_id, evidence.page_index, spec["id"], line_id,
                    domain, bbox, original,
                )
                candidates = []
                if original:
                    candidates.append(OCRHypothesis(
                        original, self.pdf_confidence, "pdf_text", bbox=bbox,
                        metadata={"evidence_id": f"pdf-{evidence.page_index}-{line_id}"},
                    ))
                crop = self._crop(evidence.raster, bbox)
                for recognizer in self.line_recognizers:
                    try:
                        candidates.extend(recognizer.recognize(crop, context))
                    except Exception as error:  # engine opcional isolado
                        warnings.append(f"{recognizer.name}:{type(error).__name__}: {error}")
                result = self.fusion.fuse(candidates, context, original_text=original or None)
                if self.context_decoder is not None and domain == "prose":
                    decoded = self.context_decoder.decode(result.chosen)
                    if decoded.text != result.chosen.text:
                        original_value = result.original_text or result.chosen.text
                        result = replace(
                            result, chosen=decoded,
                            alternatives=tuple(dict.fromkeys(
                                [result.chosen.text, *result.alternatives])),
                            original_text=original_value,
                            reason_codes=tuple(dict.fromkeys(
                                [*result.reason_codes, "context_decoder"])),
                            review_required=True,
                        )
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
                              "fusion": fusion_data,
                              "review_required": result.review_required},
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
            tipo = "chess_sequence" if any(
                item.metadata.get("domain") == "notation" for item in region_lines
            ) else "paragraph"
            regions.append(RegionResult(
                spec["id"], tipo, spec["order"], confidence, spec["bbox"],
                line_ids=[item.id for item in region_lines], text=region_text,
                warnings=[warning for item in region_lines for warning in item.warnings],
                metadata={"phase3": True, "domain": "notation" if tipo == "chess_sequence" else "prose"},
            ))
        return PageResult(
            page_id=f"page-{evidence.page_index:04d}",
            text="\n\n".join(region.text for region in regions),
            confidence=(sum(item.confidence for item in lines) / len(lines)
                        if lines else 0.0),
            regions=regions, lines=lines, words=words, warnings=warnings,
            metadata={"phase3": True, "fusions": fusions,
                      "notation_sequences": notation,
                      "recognizers": [getattr(item, "name", type(item).__name__)
                                      for item in self.line_recognizers]},
        )
