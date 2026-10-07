"""Gate estrutural para liberar um documento editorial para exportacao.

O IR garante referencias e ids; este modulo verifica invariantes que so podem
ser avaliadas no documento completo: ordem, FEN, tabelas e sequencias jogaveis.
Ele apenas relata problemas e nunca corrige silenciosamente o documento.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

import chess
import chess.pgn

from core.editorial_model import EditorialDocument


QUALITY_SCHEMA = "pyboxeditor.editorial-quality/v1"
_HIGH_IMPACT_REASONS = frozenset({
    "low_confidence", "orientation_missing", "fen_invalid", "notation_conflict",
    "diagram_uncertain", "layout_ambiguous", "manual_review",
    "side_to_move_legalidade",
})


@dataclass(frozen=True)
class QualityGateResult:
    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metrics: dict[str, int] | None = None
    schema: str = QUALITY_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metrics": dict(self.metrics or {}),
        }


def _validar_fen(valor: Any, identificador: str) -> str | None:
    if not isinstance(valor, dict):
        return f"bloco {identificador}: diagrama sem objeto FEN"
    fen = str(valor.get("fen", "")).strip()
    if not fen:
        return f"bloco {identificador}: diagrama sem FEN"
    try:
        tabuleiro = chess.Board(fen)
    except ValueError as erro:
        return f"bloco {identificador}: FEN invalido ({erro})"
    if not tabuleiro.is_valid():
        return f"bloco {identificador}: FEN invalido (posicao ilegal)"
    return None


def _validar_sequencia(valor: Any, identificador: str) -> str | None:
    texto = str(valor or "").strip()
    if not texto:
        return f"bloco {identificador}: sequencia vazia"
    jogo = chess.pgn.read_game(io.StringIO('[Result "*"]\n\n' + texto + "\n"))
    if jogo is None:
        return f"bloco {identificador}: sequencia nao pode ser carregada"
    erros = getattr(jogo, "errors", ())
    if erros:
        return f"bloco {identificador}: sequencia ilegal ({erros[0]})"
    return None


def _validar_tabela(valor: Any, identificador: str) -> str | None:
    if not isinstance(valor, dict) or not isinstance(valor.get("rows"), list):
        return f"bloco {identificador}: tabela sem rows"
    rows = valor["rows"]
    if not rows:
        return f"bloco {identificador}: tabela vazia"
    larguras = []
    for index, row in enumerate(rows):
        if not isinstance(row, list) or not row:
            return f"bloco {identificador}: linha de tabela invalida ({index})"
        larguras.append(len(row))
    if len(set(larguras)) != 1:
        return f"bloco {identificador}: tabela com linhas de larguras diferentes"
    return None


def validar_documento(documento: EditorialDocument, *,
                      exigir_resolvido: bool = False,
                      exigir_proveniencia: bool = True) -> QualityGateResult:
    """Valida um IR completo sem modificar nenhuma decisao."""
    errors: list[str] = []
    warnings: list[str] = []
    try:
        documento.validate()
    except ValueError as erro:
        errors.append(str(erro))

    pages = list(documento.pages)
    page_indexes = [int(page.page_index) for page in pages]
    if len(set(page_indexes)) != len(page_indexes):
        errors.append("ordem de paginas duplicada")
    if page_indexes != sorted(page_indexes):
        errors.append("ordem de paginas nao monotona")

    metrics = {"pages": len(pages), "blocks": 0, "diagrams": 0,
               "sequences": 0, "tables": 0, "unresolved": 0,
               "review_required": 0}
    for page in pages:
        if exigir_proveniencia and not page.source_refs:
            errors.append(f"pagina {page.page_id}: sem proveniencia")
        block_orders = [int(block.order) for block in page.blocks]
        if len(set(block_orders)) != len(block_orders):
            errors.append(f"pagina {page.page_id}: ordem de bloco duplicada")
        if block_orders != sorted(block_orders):
            errors.append(f"pagina {page.page_id}: ordem de bloco nao monotona")
        for block in page.blocks:
            metrics["blocks"] += 1
            if exigir_proveniencia and not block.source_refs:
                errors.append(f"bloco {block.id}: sem proveniencia")
            status = block.decision.status
            if status == "unresolved":
                metrics["unresolved"] += 1
            requer_revisao = status == "unresolved"
            if status not in {"reviewed", "rejected"}:
                requer_revisao = requer_revisao or bool(
                    block.metadata.get("review_required"))
                requer_revisao = requer_revisao or bool(
                    set(block.decision.reason_codes) & _HIGH_IMPACT_REASONS)
            if requer_revisao:
                metrics["review_required"] += 1
                if exigir_resolvido:
                    if status == "unresolved":
                        errors.append(f"bloco {block.id}: status unresolved")
                    else:
                        errors.append(f"bloco {block.id}: requer revisão")
            erro = None
            if block.kind == "diagram":
                metrics["diagrams"] += 1
                erro = _validar_fen(block.decision.value, block.id)
            elif block.kind == "chess_sequence":
                metrics["sequences"] += 1
                erro = _validar_sequencia(block.decision.value, block.id)
            elif block.kind == "table":
                metrics["tables"] += 1
                erro = _validar_tabela(block.decision.value, block.id)
            if erro:
                errors.append(erro)
    if not documento.source_sha256:
        warnings.append("documento sem SHA-256 da fonte")
    if not documento.pipeline_version:
        warnings.append("documento sem versao do pipeline")
    return QualityGateResult(not errors, tuple(errors), tuple(warnings), metrics)
