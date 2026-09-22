"""Diagramas de xadrez como objetos editoriais da Fase 4.

O módulo concentra a complexidade visual e de domínio atrás de dois pontos de
entrada pequenos: :class:`DiagramProcessor` para uma página e
:class:`Phase4Processor` para a integração com o ``PageResult`` da Fase 3.
Modelos neurais, detectores legados e doubles de teste entram por adapters; a
posição final nunca é escolhida por uma string sem top-k, legalidade e estado
de revisão.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

import numpy as np

from core.ocr_result import PageResult, RegionResult


SYMBOLS = frozenset("BKNPQRbknpqr.")
FILES = "abcdefgh"
RANKS = "87654321"
ORIENTATIONS = frozenset({"branca", "preta", "desconhecida"})
REVIEW_STATES = frozenset({"automatic", "review_required", "reviewed", "unresolved"})


def _confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _square(value: str) -> str:
    value = str(value).strip().lower()
    if len(value) != 2 or value[0] not in FILES or value[1] not in "12345678":
        raise ValueError(f"casa inválida: {value!r}")
    return value


def _fen_from_symbols(symbols: Mapping[str, str], *, side_to_move: str = "w",
                      castling: str = "-", en_passant: str = "-",
                      halfmove: int = 0, fullmove: int = 1) -> str:
    rows = []
    for rank in RANKS:
        empty = 0
        row = []
        for file in FILES:
            symbol = symbols.get(f"{file}{rank}", ".")
            if symbol == ".":
                empty += 1
            else:
                if empty:
                    row.append(str(empty))
                    empty = 0
                row.append(symbol)
        if empty:
            row.append(str(empty))
        rows.append("".join(row) or "8")
    return (f"{'/'.join(rows)} {side_to_move} {castling or '-'} "
            f"{en_passant or '-'} {int(halfmove)} {int(fullmove)}")


def _position_plausible(symbols: Mapping[str, str]) -> bool:
    values = [value for value in symbols.values() if value != "."]
    if values.count("K") != 1 or values.count("k") != 1:
        return False
    if values.count("P") > 8 or values.count("p") > 8:
        return False
    if sum(value in "PNBRQK" for value in values) > 16:
        return False
    if sum(value in "pnbrqk" for value in values) > 16:
        return False
    return not any(value in "Pp" and square[1] in "18"
                   for square, value in symbols.items())


@dataclass(frozen=True)
class SquareCandidate:
    """Uma hipótese de peça/vazio para uma casa, preservando a origem."""

    symbol: str
    confidence: float
    source: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        symbol = "." if self.symbol in {"", " ", None} else str(self.symbol)
        if symbol not in SYMBOLS:
            raise ValueError(f"símbolo de casa inválido: {symbol!r}")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "confidence", _confidence(self.confidence))
        object.__setattr__(self, "source", str(self.source or "unknown"))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "confidence": self.confidence,
                "source": self.source, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class SquareResult:
    row: int
    column: int
    square: str
    candidates: tuple[SquareCandidate, ...]
    chosen: str
    confidence: float
    occupancy_confidence: float
    review_required: bool = False
    original_symbol: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "square", _square(self.square))
        if self.chosen not in SYMBOLS:
            raise ValueError(f"símbolo escolhido inválido: {self.chosen!r}")
        object.__setattr__(self, "confidence", _confidence(self.confidence))
        object.__setattr__(self, "occupancy_confidence",
                           _confidence(self.occupancy_confidence))
        object.__setattr__(self, "candidates", tuple(self.candidates))

    def to_dict(self) -> dict[str, Any]:
        return {
            "row": self.row, "column": self.column, "square": self.square,
            "candidates": [item.to_dict() for item in self.candidates],
            "chosen": self.chosen, "confidence": self.confidence,
            "occupancy_confidence": self.occupancy_confidence,
            "review_required": self.review_required,
            "original_symbol": self.original_symbol,
        }


@dataclass(frozen=True)
class OrientationDecision:
    value: str
    confidence: float
    source: str
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.value not in ORIENTATIONS:
            raise ValueError(f"orientação inválida: {self.value!r}")
        object.__setattr__(self, "confidence", _confidence(self.confidence))

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "confidence": self.confidence,
                "source": self.source, "reason_codes": list(self.reason_codes)}


def resolve_orientation(value: Any = None) -> OrientationDecision:
    """Resolve orientação apenas quando há evidência explícita.

    Um tabuleiro sem coordenadas não contém informação suficiente para decidir
    qual lado está embaixo. Nesse caso o resultado é ``desconhecida`` e a
    revisão fica obrigatória; a implementação não adivinha a orientação.
    """
    if isinstance(value, OrientationDecision):
        return value
    if hasattr(value, "orientacao"):
        value = getattr(value, "orientacao")
    if isinstance(value, Mapping):
        direct = value.get("orientation", value.get("orientacao"))
        if direct:
            return resolve_orientation(direct)
        columns = str(value.get("colunas", value.get("columns", ""))).lower()
        ranks = str(value.get("filas", value.get("ranks", ""))).lower()
        if columns == "abcdefgh" and ranks == "87654321":
            return OrientationDecision("branca", 1.0, "coordinates",
                                       ("coordinates_consensus",))
        if columns == "hgfedcba" and ranks == "12345678":
            return OrientationDecision("preta", 1.0, "coordinates",
                                       ("coordinates_consensus",))
        if columns or ranks:
            return OrientationDecision("desconhecida", .25, "coordinates",
                                       ("coordinates_incomplete",))
        return OrientationDecision("desconhecida", 0.0, "missing",
                                   ("orientation_missing",))
    aliases = {
        "branca": "branca", "white": "branca", "white_bottom": "branca",
        "preta": "preta", "black": "preta", "black_bottom": "preta",
        "desconhecida": "desconhecida", "unknown": "desconhecida",
        "": "desconhecida", "none": "desconhecida",
    }
    normalized = aliases.get(str(value or "").strip().casefold(), "desconhecida")
    if normalized == "desconhecida":
        return OrientationDecision(normalized, 0.0, "missing",
                                   ("orientation_missing",))
    return OrientationDecision(normalized, 1.0, "explicit", ("orientation_explicit",))


@dataclass(frozen=True)
class DiagramAnnotations:
    arrows: tuple[Any, ...] = ()
    highlights: tuple[Any, ...] = ()
    legend: str = ""
    coordinates: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "DiagramAnnotations":
        value = value or {}
        return cls(
            arrows=tuple(value.get("arrows", value.get("setas", ())) or ()),
            highlights=tuple(value.get("highlights", value.get("destaques", ())) or ()),
            legend=str(value.get("legend", value.get("legenda", "")) or ""),
            coordinates=dict(value.get("coordinates", value.get("coordenadas", {})) or {}),
            metadata={key: item for key, item in value.items()
                      if key not in {"arrows", "setas", "highlights", "destaques",
                                     "legend", "legenda", "coordinates", "coordenadas"}},
        )

    def to_dict(self) -> dict[str, Any]:
        return {"arrows": list(self.arrows), "highlights": list(self.highlights),
                "legend": self.legend, "coordinates": dict(self.coordinates),
                "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class DiagramResult:
    id: str
    bbox: tuple[int, int, int, int]
    source: str
    orientation: str
    orientation_confidence: float
    squares: tuple[SquareResult, ...]
    fen: str
    confidence: float
    review_status: str
    review_required: bool
    side_to_move: str = "w"
    castling_rights: str = "-"
    en_passant: str = "-"
    annotations: DiagramAnnotations = field(default_factory=DiagramAnnotations)
    warnings: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    image_ref: Mapping[str, Any] = field(default_factory=dict)
    original_fen: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.review_status not in REVIEW_STATES:
            raise ValueError(f"estado de revisão inválido: {self.review_status!r}")
        if self.side_to_move not in {"w", "b"}:
            raise ValueError("lado a jogar deve ser 'w' ou 'b'")
        if self.castling_rights != "-" and any(item not in "KQkq"
                                                for item in self.castling_rights):
            raise ValueError("direitos de roque inválidos")
        if self.en_passant != "-":
            _square(self.en_passant)
        if len(self.squares) != 64:
            raise ValueError("um diagrama precisa conter exatamente 64 casas")
        object.__setattr__(self, "orientation_confidence",
                           _confidence(self.orientation_confidence))
        object.__setattr__(self, "confidence", _confidence(self.confidence))
        object.__setattr__(self, "bbox", tuple(int(item) for item in self.bbox))
        object.__setattr__(self, "warnings", tuple(str(item) for item in self.warnings))
        object.__setattr__(self, "reason_codes", tuple(str(item) for item in self.reason_codes))
        object.__setattr__(self, "image_ref", dict(self.image_ref or {}))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "bbox": list(self.bbox), "source": self.source,
            "orientation": self.orientation,
            "orientation_confidence": self.orientation_confidence,
            "squares": [item.to_dict() for item in self.squares], "fen": self.fen,
            "confidence": self.confidence, "review_status": self.review_status,
            "review_required": self.review_required,
            "side_to_move": self.side_to_move,
            "castling_rights": self.castling_rights,
            "en_passant": self.en_passant,
            "annotations": self.annotations.to_dict(),
            "warnings": list(self.warnings), "reason_codes": list(self.reason_codes),
            "image_ref": dict(self.image_ref), "original_fen": self.original_fen,
            "metadata": dict(self.metadata),
        }

    def review(self, corrections: Mapping[str, str]) -> "DiagramResult":
        """Aplica correções humanas mantendo FEN original e todas as hipóteses."""
        corrected = dict(corrections)
        squares = []
        symbols = {item.square: item.chosen for item in self.squares}
        for item in self.squares:
            if item.square not in corrected:
                squares.append(item)
                continue
            symbol = corrected[item.square]
            if symbol not in SYMBOLS:
                raise ValueError(f"símbolo de correção inválido: {symbol!r}")
            symbols[item.square] = symbol
            candidates = tuple(item.candidates) + (
                SquareCandidate(symbol, 1.0, "manual", {"review": True}),)
            squares.append(replace(item, candidates=candidates, chosen=symbol,
                                   confidence=1.0, review_required=False,
                                   original_symbol=item.chosen))
        fen = _fen_from_symbols(symbols, side_to_move=self.side_to_move,
                                castling=self.castling_rights,
                                en_passant=self.en_passant)
        return replace(self, squares=tuple(squares), fen=fen,
                       review_status="reviewed", review_required=False,
                       original_fen=self.original_fen or self.fen,
                       reason_codes=tuple(dict.fromkeys((*self.reason_codes,
                                                          "manual_review"))))


@dataclass(frozen=True)
class BoardCandidate:
    id: str
    bbox: tuple[int, int, int, int]
    quad: tuple[tuple[float, float], ...] | None
    confidence: float
    source: str
    orientation: str = "desconhecida"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.bbox) != 4 or self.bbox[2] <= self.bbox[0] or self.bbox[3] <= self.bbox[1]:
            raise ValueError("bbox de tabuleiro inválida")
        object.__setattr__(self, "confidence", _confidence(self.confidence))
        object.__setattr__(self, "orientation", resolve_orientation(self.orientation).value)
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def crop(self, image: Any) -> np.ndarray:
        if image is None:
            return np.empty((0, 0), dtype=np.uint8)
        x1, y1, x2, y2 = self.bbox
        return np.asarray(image)[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "bbox": list(self.bbox),
                "quad": [list(point) for point in self.quad] if self.quad else None,
                "confidence": self.confidence, "source": self.source,
                "orientation": self.orientation, "metadata": dict(self.metadata)}


class SquareRecognizer(Protocol):
    name: str

    def recognize(self, image: Any, board: BoardCandidate, square: str,
                  context: Mapping[str, Any]) -> Sequence[SquareCandidate]: ...


class BoardDetector:
    """Adapter para o detector visual legado ou uma implementação substituta."""

    name = "board_detector"

    def __init__(self, detector: Callable[..., Any] | None = None):
        self._detector = detector

    def detect(self, image: Any, *, max_boards: int = 8,
               orientation: Any = None, metadata: Mapping[str, Any] | None = None
               ) -> list[BoardCandidate]:
        if image is None:
            return []
        if self._detector is None:
            from core import deteccao_de_tabuleiro
            raw = deteccao_de_tabuleiro.detectar(image, maximo=max_boards)
        else:
            raw = self._detector(image, max_boards=max_boards, metadata=metadata or {})
        result = []
        default_orientation = resolve_orientation(orientation or metadata).value
        for index, item in enumerate(raw or ()):
            if isinstance(item, BoardCandidate):
                result.append(item)
                continue
            candidate_metadata = dict(getattr(item, "metadata", {}) or {})
            if isinstance(item, Mapping):
                bbox = tuple(int(value) for value in item["bbox"])
                quad = item.get("quad")
                score = item.get("confidence", item.get("pontuacao", 0.0))
                source = str(item.get("source", self.name))
                item_orientation = item.get("orientation", default_orientation)
                candidate_metadata.update(item.get("metadata", {}))
            else:
                bbox = tuple(int(value) for value in item.caixa)
                quad_value = getattr(item, "quad", None)
                quad = (tuple(map(float, point)) for point in quad_value) if quad_value is not None else None
                quad = tuple(quad) if quad is not None else None
                score = getattr(item, "pontuacao", 0.0)
                source = str(getattr(item, "source", self.name))
                item_orientation = getattr(item, "orientation", default_orientation)
            result.append(BoardCandidate(
                id=f"diagram-{index:04d}", bbox=bbox, quad=quad,
                confidence=score, source=source,
                orientation=resolve_orientation(item_orientation).value,
                metadata=candidate_metadata,
            ))
        return result[:max_boards]


class LegacySquareRecognizer:
    """Adapter dos dois modelos existentes em ``core.diagrama``.

    ``pontuacoes_de_casas`` calcula probabilidade conjunta de vazio/peça, em
    vez de expor os detalhes das duas redes ao pipeline editorial.
    """

    name = "diagrama-models"

    def recognize_board(self, image: Any, board: BoardCandidate,
                        context: Mapping[str, Any]) -> Mapping[str, Sequence[SquareCandidate]]:
        from core import diagrama
        scores = diagrama.pontuacoes_de_casas(image, top_k=int(context.get("top_k", 5)))
        result = {}
        for (row, column), candidates in scores.items():
            if board.orientation == "preta":
                row, column = 7 - row, 7 - column
            square = f"{FILES[column]}{RANKS[row]}"
            result[square] = tuple(
                SquareCandidate(symbol, confidence, self.name)
                for symbol, confidence in candidates
            )
        return result

    def recognize(self, image: Any, board: BoardCandidate, square: str,
                  context: Mapping[str, Any]) -> Sequence[SquareCandidate]:
        return self.recognize_board(image, board, context).get(square, ())


def _normalise_candidates(values: Iterable[Any], *, source: str = "unknown",
                          top_k: int = 5) -> tuple[SquareCandidate, ...]:
    result = []
    for value in values:
        if isinstance(value, SquareCandidate):
            result.append(value)
        elif isinstance(value, Mapping):
            result.append(SquareCandidate(str(value.get("symbol", ".")),
                                          float(value.get("confidence", 0.0)),
                                          str(value.get("source", source)),
                                          dict(value.get("metadata", {}))))
        elif isinstance(value, (tuple, list)) and len(value) >= 2:
            result.append(SquareCandidate(str(value[0]), float(value[1]), source))
        else:
            result.append(SquareCandidate(str(value), 0.0, source))
    unique = {}
    for candidate in result:
        old = unique.get(candidate.symbol)
        if old is None or candidate.confidence > old.confidence:
            unique[candidate.symbol] = candidate
    return tuple(sorted(unique.values(), key=lambda item: item.confidence, reverse=True)[:top_k])


def resolve_position(candidates: Mapping[str, Sequence[SquareCandidate]], *,
                     orientation: Any = None, top_k: int = 5,
                     side_to_move: str = "w", castling: str = "-",
                     en_passant: str = "-", board_id: str = "diagram-0",
                     bbox: tuple[int, int, int, int] = (0, 0, 1, 1),
                     source: str = "square-recognizer",
                     annotations: DiagramAnnotations | None = None,
                     image_ref: Mapping[str, Any] | None = None,
                     metadata: Mapping[str, Any] | None = None) -> DiagramResult:
    """Ranqueia posições sem fabricar peças e usa legalidade como filtro.

    A busca é beam-search sobre as 64 casas. O beam limita custo e mantém as
    alternativas de cada casa; no final apenas posições com exatamente um rei
    por cor, limites materiais e peões fora das duas últimas filas são aceitas.
    Se nenhuma hipótese passar, a melhor leitura fica ``unresolved``.
    """
    if top_k <= 0:
        raise ValueError("top_k deve ser positivo")
    orientation_decision = resolve_orientation(orientation)
    ordered = [f"{file}{rank}" for rank in RANKS for file in FILES]
    candidate_map: dict[str, Sequence[SquareCandidate]] = {}
    for key, value in candidates.items():
        if isinstance(key, (tuple, list)) and len(key) == 2:
            row, column = int(key[0]), int(key[1])
            if 0 <= row < 8 and 0 <= column < 8:
                key = f"{FILES[column]}{RANKS[row]}"
        candidate_map[str(key).lower()] = value
    prepared: dict[str, tuple[SquareCandidate, ...]] = {}
    missing = []
    for square in ordered:
        current = _normalise_candidates(candidate_map.get(square, ()), source=source,
                                         top_k=top_k)
        if not current:
            missing.append(square)
            current = (SquareCandidate(".", .5, "missing", {"missing": True}),)
        prepared[square] = current

    # score, chosen symbols; pruning material impossible before the next square
    beam: list[tuple[float, dict[str, str]]] = [(0.0, {})]
    for square in ordered:
        next_states = []
        for score, state in beam:
            for candidate in prepared[square]:
                symbol = candidate.symbol
                new_state = {**state, square: symbol}
                values = list(new_state.values())
                if values.count("K") > 1 or values.count("k") > 1:
                    continue
                if values.count("P") > 8 or values.count("p") > 8:
                    continue
                if sum(value in "PNBRQK" for value in values) > 16:
                    continue
                if sum(value in "pnbrqk" for value in values) > 16:
                    continue
                if symbol in "Pp" and square[1] in "18":
                    continue
                next_states.append((score + math.log(max(candidate.confidence, 1e-6)),
                                    new_state))
        next_states.sort(key=lambda item: item[0], reverse=True)
        beam = next_states[:128]
        if not beam:
            break

    legal = [(score, state) for score, state in beam if _position_plausible(state)]
    reason_codes = []
    if legal:
        score, selected_state = max(legal, key=lambda item: item[0])
    elif beam:
        score, selected_state = beam[0]
        reason_codes.append("legal_filter_failed")
    else:
        score, selected_state = 0.0, {square: "." for square in ordered}
        reason_codes.append("no_position_candidate")

    greedy_state = {square: prepared[square][0].symbol for square in ordered}
    if selected_state != greedy_state:
        reason_codes.append("legal_filter")
    symbols = selected_state
    selected_squares = []
    for row, rank in enumerate(RANKS):
        for column, file in enumerate(FILES):
            square = f"{file}{rank}"
            candidates_for_square = prepared[square]
            selected = symbols[square]
            chosen_candidate = next((item for item in candidates_for_square
                                     if item.symbol == selected), None)
            confidence = chosen_candidate.confidence if chosen_candidate else 0.0
            occupancy = max((item.confidence for item in candidates_for_square
                             if (item.symbol == ".") == (selected == ".")),
                            default=confidence)
            top_confidence = candidates_for_square[0].confidence
            second_confidence = (candidates_for_square[1].confidence
                                 if len(candidates_for_square) > 1 else 0.0)
            low_margin = (len(candidates_for_square) > 1
                          and top_confidence - second_confidence < .10)
            selected_squares.append(SquareResult(
                row, column, square, candidates_for_square, selected,
                confidence, occupancy, low_margin or selected != candidates_for_square[0].symbol,
            ))

    fen = _fen_from_symbols(symbols, side_to_move=side_to_move,
                            castling=castling, en_passant=en_passant)
    selected_confidences = [item.confidence for item in selected_squares]
    confidence = min(selected_confidences) if selected_confidences else 0.0
    if missing:
        reason_codes.append("missing_square_candidates")
    if orientation_decision.value == "desconhecida":
        reason_codes.append("orientation_missing")
    review_required = bool(
        missing or orientation_decision.value == "desconhecida"
        or not legal or any(item.review_required for item in selected_squares)
    )
    warnings = []
    if orientation_decision.value == "desconhecida":
        warnings.append("orientação do tabuleiro não foi confirmada")
    if not legal:
        warnings.append("nenhuma posição candidata passou pelo filtro de legalidade")
    if missing:
        warnings.append(f"{len(missing)} casa(s) sem candidatos visuais")
    status = "unresolved" if not legal else ("review_required" if review_required else "automatic")
    annotation_value = (annotations if isinstance(annotations, DiagramAnnotations)
                        else DiagramAnnotations.from_mapping(annotations))
    return DiagramResult(
        id=str(board_id), bbox=bbox, source=source,
        orientation=orientation_decision.value,
        orientation_confidence=orientation_decision.confidence,
        squares=tuple(selected_squares), fen=fen, confidence=confidence,
        review_status=status, review_required=review_required,
        side_to_move=side_to_move, castling_rights=castling,
        en_passant=en_passant,
        annotations=annotation_value, warnings=tuple(warnings),
        reason_codes=tuple(dict.fromkeys((*reason_codes,
                                          *orientation_decision.reason_codes))),
        image_ref=image_ref or {}, metadata=metadata or {},
    )


class DiagramProcessor:
    """Detecta, classifica e materializa diagramas de uma evidência de página."""

    def __init__(self, *, detector: BoardDetector | Callable[..., Any] | None = None,
                 recognizer: SquareRecognizer | None = None, top_k: int = 5,
                 max_boards: int = 8, include_annotations: bool = True):
        if top_k <= 0 or max_boards <= 0:
            raise ValueError("top_k e max_boards devem ser positivos")
        self.detector = detector if isinstance(detector, BoardDetector) else BoardDetector(detector)
        self.recognizer = recognizer or LegacySquareRecognizer()
        self.top_k = int(top_k)
        self.max_boards = int(max_boards)
        self.include_annotations = bool(include_annotations)

    def process(self, evidence: Any, options: Any, token: Any,
                *, annotations: Mapping[str, Any] | None = None) -> list[DiagramResult]:
        image = getattr(evidence, "raster", None)
        if image is None:
            return []
        page_annotations = annotations or getattr(evidence, "metadata", {}).get("diagrams", {})
        boards = self.detector.detect(
            image, max_boards=self.max_boards,
            metadata=getattr(evidence, "metadata", {}) or {},
        )
        results = []
        for board in boards:
            token.raise_if_cancelled()
            board_annotation = page_annotations.get(board.id, page_annotations) \
                if isinstance(page_annotations, Mapping) else {}
            parsed_annotations = (DiagramAnnotations.from_mapping(board_annotation)
                                  if self.include_annotations else DiagramAnnotations())
            context = {
                "document_id": evidence.document_id, "page_index": evidence.page_index,
                "top_k": self.top_k, "orientation": board.orientation,
            }
            crop = board.crop(image)
            recognizer_warning = ""
            try:
                if hasattr(self.recognizer, "recognize_board"):
                    all_candidates = self.recognizer.recognize_board(crop, board, context)
                else:
                    all_candidates = {}
                    for rank in RANKS:
                        for file in FILES:
                            square = f"{file}{rank}"
                            all_candidates[square] = self.recognizer.recognize(
                                crop, board, square, context)
            except (ImportError, OSError, RuntimeError, ValueError) as error:
                # Model ausente ou recorte inválido não derruba a página. O
                # objeto unresolved conserva o tabuleiro e entra na revisão.
                all_candidates = {}
                recognizer_warning = (
                    f"classificador de casas indisponível: {type(error).__name__}: {error}")
            image_ref = {
                "document_id": evidence.document_id,
                "page_index": evidence.page_index,
                "bbox": list(board.bbox),
                "image_hash": getattr(evidence, "raster_hash", ""),
                "crop_hash": hashlib.sha256(np.asarray(crop).tobytes()).hexdigest(),
            }
            result = resolve_position(
                all_candidates, orientation=board.orientation, top_k=self.top_k,
                board_id=board.id, bbox=board.bbox, source=getattr(self.recognizer, "name", "recognizer"),
                annotations=parsed_annotations, image_ref=image_ref,
                metadata={"board": board.to_dict(), "options": {
                    "dpi": getattr(options, "dpi", None),
                    "top_k": self.top_k,
                }},
            )
            result = replace(result, confidence=min(result.confidence, board.confidence),
                             reason_codes=tuple(dict.fromkeys(("board_detected",
                                                                *result.reason_codes))))
            if board.confidence < .75 and result.review_status == "automatic":
                result = replace(
                    result, review_status="review_required", review_required=True,
                    warnings=tuple((*result.warnings,
                                    "confiança de detecção do tabuleiro abaixo do limiar")),
                    reason_codes=tuple(dict.fromkeys((*result.reason_codes,
                                                      "low_board_confidence"))),
                )
            if recognizer_warning:
                result = replace(
                    result,
                    review_status="unresolved", review_required=True,
                    warnings=tuple((*result.warnings, recognizer_warning)),
                    reason_codes=tuple(dict.fromkeys((*result.reason_codes,
                                                      "recognizer_unavailable"))),
                )
            results.append(result)
        return results


class Phase4Processor:
    """Fachada da Fase 4: texto da Fase 3 mais regiões de diagrama."""

    def __init__(self, *, text_processor: Any | None = None,
                 diagram_processor: DiagramProcessor | None = None):
        if text_processor is None:
            from core.ocr_phase3 import Phase3Processor
            text_processor = Phase3Processor()
        self.text_processor = text_processor
        self.diagram_processor = diagram_processor or DiagramProcessor()

    def process(self, evidence: Any, options: Any, token: Any) -> PageResult:
        if hasattr(self.text_processor, "process"):
            page = self.text_processor.process(evidence, options, token)
        else:
            page = self.text_processor(evidence, options, token)
        if not isinstance(page, PageResult):
            raise TypeError("text_processor deve retornar PageResult")
        if (not str(getattr(evidence, "text_layer", "") or "").strip()
                and not getattr(evidence, "text_blocks", ())
                and not any(line.text.strip() for line in page.lines)):
            # Um scan sem camada textual pode ter diagrama sem ter um
            # parágrafo vazio. A região diagram será adicionada abaixo.
            page.regions = [region for region in page.regions if region.text.strip()]
            page.text = "\n\n".join(region.text for region in page.regions)
        diagrams = self.diagram_processor.process(evidence, options, token)
        regions = list(page.regions)
        for diagram in diagrams:
            region = RegionResult(
                id=diagram.id, type="diagram", order=len(regions),
                confidence=diagram.confidence, bbox=diagram.bbox,
                text=diagram.fen, warnings=list(diagram.warnings),
                metadata={"phase4": True, "diagram": diagram.to_dict(),
                          "review_status": diagram.review_status,
                          "review_required": diagram.review_required},
            )
            regions.append(region)
        page.regions = regions
        page.metadata.update({
            "phase4": True,
            "diagrams": [item.to_dict() for item in diagrams],
            "diagram_count": len(diagrams),
        })
        if any(item.review_required for item in diagrams):
            page.warnings.append("há diagrama aguardando revisão")
        return page


def diagram_metrics(predicted: Sequence[DiagramResult], truth: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Métricas independentes da Fase 4 para o benchmark congelado."""
    total = min(len(predicted), len(truth))
    if total == 0:
        return {"fen_exact": 0.0, "square_accuracy": 0.0,
                "orientation_accuracy": 0.0, "legend_association": 0.0}
    fen_exact = orientation = legend = square_hits = square_total = 0
    for result, expected in zip(predicted[:total], truth[:total]):
        expected_fen = str(expected.get("fen", ""))
        fen_exact += result.fen == expected_fen
        expected_orientation = str(expected.get("orientation", "desconhecida"))
        orientation += result.orientation == expected_orientation
        expected_legend = str(expected.get("legend", ""))
        legend += result.annotations.legend == expected_legend
        expected_board = expected.get("squares", {})
        for square in FILES:
            for rank in "12345678":
                name = f"{square}{rank}"
                if name in expected_board:
                    square_total += 1
                    square_hits += next(item for item in result.squares
                                        if item.square == name).chosen == expected_board[name]
    return {"fen_exact": fen_exact / total,
            "square_accuracy": square_hits / max(1, square_total),
            "orientation_accuracy": orientation / total,
            "legend_association": legend / total}
