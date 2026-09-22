"""Fila de revisão humana e diário append-only do documento editorial.

Este módulo mantém a revisão independente da interface.  A UI pode projetar a
fila como quiser; o estado autoritativo continua sendo o documento mais a
sequência de :class:`ReviewEvent`.

O que a fila mostra de cada bloco (`ReviewItem`) é o que o revisor precisa
para decidir sem abrir outra janela: o valor lido, **por que** o bloco está
aqui em frases (`motivos`), e as linhas de que ele saiu (`linhas`), cada uma
com a caixa na página, a leitura da cadeia própria, a do motor de prosa e os
motivos dela. É o que `core.editorial_adapters` guarda na evidência de cada
linha e `core.editorial_suspeitas` traduz.

Desfazer é uma **pilha**: cada `undo` volta um passo do revisor — o evento
mais recente que ainda não foi desfeito —, e um lote conta como um passo só.
Era "o último evento que não é undo", e dois `undo` seguidos voltavam o
mesmo passo duas vezes.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

from core.editorial_model import (
    DECISION_STATUSES,
    EditorialDocument,
    EditorialBlock,
    Evidence,
    ReviewEvent,
    SourceRef,
)
from core.editorial_suspeitas import PESOS, PROCEDENCIA, descrever_codigos


_KIND_PRIORITY = {
    "diagram": 0,
    "figure": 3,
    "chess_sequence": 1,
    "paragraph": 2,
    "heading": 2,
    "caption": 2,
    "table": 3,
    "header": 4,
    "footer": 4,
    "unknown": 5,
    "page_break": 6,
}
_HIGH_IMPACT_REASONS = {
    "low_confidence", "orientation_missing", "fen_invalid", "notation_conflict",
    "diagram_uncertain", "layout_ambiguous", "manual_review",
}
#: O prefixo que marca um evento de lote: `batch:<id>`. Todos os eventos do
#: mesmo lote levam o mesmo id, e `undo` os desfaz juntos.
_LOTE = "batch:"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _decision_requires_review(block: EditorialBlock) -> bool:
    """Se o bloco é uma **suspeita** — e não só "ainda não foi revisado".

    `automatic` é o estado normal de um bloco bem lido, e entrava na fila
    inteiro: com o primeiro operando sempre verdadeiro, avisos, motivos e
    `review_required` eram letra morta, e a fila era o livro todo. Vai para a
    fila o que não se resolveu (`unresolved`), o que pediu revisão, o que tem
    aviso e o que carrega um motivo de alto impacto.
    """
    decision = block.decision
    if decision.status in {"reviewed", "rejected"}:
        return False
    return bool(
        decision.status == "unresolved"
        or block.metadata.get("review_required")
        or block.warnings
        or set(decision.reason_codes) & _HIGH_IMPACT_REASONS
    )


def _evidence_map(document: EditorialDocument) -> dict[str, Evidence]:
    return {item.id: item for page in document.pages for item in page.evidence}


def _is_line(evidence: Evidence) -> bool:
    return "motivos" in evidence.metadata


def _confidence(evidence: Mapping[str, Evidence], block: EditorialBlock) -> float:
    values = [evidence[item].confidence for item in block.decision.evidence_ids
              if item in evidence]
    return min(values) if values else 0.0


def _alternatives(evidence: Mapping[str, Evidence], block: EditorialBlock) -> tuple[Any, ...]:
    """As alternativas do bloco inteiro — as das linhas ficam em `linhas`."""
    values: list[Any] = []
    for evidence_id in block.decision.evidence_ids:
        item = evidence.get(evidence_id)
        if item and not _is_line(item):
            values.extend(hypothesis.text for hypothesis in item.alternatives)
    if isinstance(block.decision.value, Mapping):
        values.extend(block.decision.value.get("alternatives", ()) or ())
    return tuple(values)


@dataclass(frozen=True)
class LinhaRevisao:
    """Uma linha impressa do bloco, como a tela a mostra."""

    evidence_id: str
    texto: str
    ancora: str = ""
    motor: str = ""
    caixa: tuple[int, int, int, int] | None = None
    confianca: float = 1.0
    codigos: tuple[str, ...] = ()
    motivos: tuple[str, ...] = ()
    celula: tuple[int, int, int] | None = None

    @property
    def suspeita(self) -> bool:
        return bool(self.codigos)

    def to_dict(self) -> dict[str, Any]:
        return {"evidence_id": self.evidence_id, "texto": self.texto,
                "ancora": self.ancora, "motor": self.motor,
                "caixa": list(self.caixa) if self.caixa else None,
                "confianca": self.confianca, "codigos": list(self.codigos),
                "motivos": list(self.motivos),
                "celula": list(self.celula) if self.celula else None}


def _linhas(evidence: Mapping[str, Evidence], block: EditorialBlock) -> tuple[LinhaRevisao, ...]:
    saida = []
    for evidence_id in block.decision.evidence_ids:
        item = evidence.get(evidence_id)
        if item is None or not _is_line(item):
            continue
        por_fonte = {h.source: h.text for h in item.alternatives}
        caixa = item.metadata.get("caixa") or (item.ref.bbox if item.ref else None)
        celula = item.metadata.get("celula")
        saida.append(LinhaRevisao(
            evidence_id=item.id, texto=item.observed_text,
            ancora=por_fonte.get("glyph_chain", ""),
            motor=por_fonte.get("line_engine", ""),
            caixa=tuple(int(v) for v in caixa) if caixa else None,
            confianca=item.confidence,
            codigos=tuple(str(c) for c in item.metadata.get("motivos", ())),
            motivos=tuple(item.diagnostics),
            celula=_celula_de(celula)))
    return tuple(saida)


_RE_CELULA = re.compile(r"^t(\d+)c(\d+)l(\d+)$")


def _celula_de(rotulo: Any) -> tuple[int, int, int] | None:
    achado = _RE_CELULA.match(str(rotulo or ""))
    return tuple(int(v) for v in achado.groups()) if achado else None


def _motivos(block: EditorialBlock) -> tuple[str, ...]:
    """As frases do bloco: as que o adapter guardou, as dos códigos da decisão
    que não têm frase guardada, e os avisos do bloco."""
    guardadas = block.metadata.get("motivos")
    # Com frases guardadas pelo adapter, os códigos já estão ditos — e ditos
    # com o token dentro; a frase genérica do código só entra sem elas.
    frases = ([str(f) for f in guardadas] if guardadas
              else descrever_codigos(block.decision.reason_codes))
    for aviso in block.warnings:
        if aviso not in frases:
            frases.append(str(aviso))
    return tuple(frases)


@dataclass(frozen=True)
class ReviewItem:
    """Projeção pronta para a tela de revisão."""

    target_id: str
    document_id: str
    page_id: str
    page_index: int
    kind: str
    value: Any
    original_value: Any
    status: str
    confidence: float
    severity: int
    reason_codes: tuple[str, ...] = ()
    source_refs: tuple[SourceRef, ...] = ()
    alternatives: tuple[Any, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    motivos: tuple[str, ...] = ()
    linhas: tuple[LinhaRevisao, ...] = ()

    @property
    def bbox(self) -> tuple[int, int, int, int] | None:
        for ref in self.source_refs:
            if ref.bbox:
                return ref.bbox
        return None

    @property
    def linhas_suspeitas(self) -> tuple[LinhaRevisao, ...]:
        return tuple(linha for linha in self.linhas if linha.suspeita)

    @property
    def assinatura(self) -> tuple[str, tuple[str, ...]]:
        """O que faz dois itens serem "semelhantes": o tipo e os motivos."""
        return self.kind, tuple(sorted(set(self.reason_codes) - PROCEDENCIA))

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id, "document_id": self.document_id,
            "page_id": self.page_id, "page_index": self.page_index,
            "kind": self.kind, "value": self.value,
            "original_value": self.original_value, "status": self.status,
            "confidence": self.confidence, "severity": self.severity,
            "reason_codes": list(self.reason_codes),
            "source_refs": [item.to_dict() for item in self.source_refs],
            "alternatives": list(self.alternatives), "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "motivos": list(self.motivos),
            "linhas": [linha.to_dict() for linha in self.linhas],
        }


@dataclass(frozen=True)
class ReviewQueue:
    items: list[ReviewItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", list(self.items))

    def filter(self, *, page_index: int | None = None, page_id: str | None = None,
               target_id: str | None = None, kind: str | None = None,
               min_severity: int = 0, status: str | None = None) -> "ReviewQueue":
        return ReviewQueue([item for item in self.items if
            (page_index is None or item.page_index == page_index)
            and (page_id is None or item.page_id == page_id)
            and (target_id is None or item.target_id == target_id)
            and (kind is None or item.kind == kind)
            and item.severity >= min_severity
            and (status is None or item.status == status)])

    def next(self) -> ReviewItem | None:
        return self.items[0] if self.items else None

    @property
    def pages(self) -> tuple[int, ...]:
        return tuple(sorted({item.page_index for item in self.items}))

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted({item.kind for item in self.items}))

    def to_dict(self) -> dict[str, Any]:
        return {"items": [item.to_dict() for item in self.items], "count": len(self.items)}


def _severity(block: EditorialBlock, confidence: float,
              linhas: tuple[LinhaRevisao, ...]) -> int:
    """Impacto estimado, na ordem da spec (§9): o que muda o lance ou a
    posição antes do que muda a palavra, e a linha com motivo pesado antes
    da que só perdeu confiança."""
    impact = _KIND_PRIORITY.get(block.kind, 5)
    severity = (100 - impact * 10) + (0 if confidence >= .8 else 20)
    reasons = set(block.decision.reason_codes)
    if reasons & _HIGH_IMPACT_REASONS:
        severity += 10
    pesos = [PESOS.get(codigo, 0.0) for linha in linhas for codigo in linha.codigos]
    pesos += [PESOS.get(codigo, 0.0) for codigo in reasons]
    if pesos:
        severity += int(50 * max(pesos))
    if block.decision.status == "unresolved":
        severity += 15
    return severity


def build_review_queue(document: EditorialDocument, *,
                       limite_por_pagina: int | None = None) -> ReviewQueue:
    """Constrói a fila global, com diagramas e conflitos de maior impacto primeiro.

    `limite_por_pagina` deixa na fila só os `N` blocos de maior impacto de
    cada página — o que um revisor confere por página, e não o que a régua
    achou. Sem limite, entra tudo o que é suspeito.
    """
    evidence = _evidence_map(document)
    result: list[ReviewItem] = []
    for page in document.pages:
        da_pagina: list[ReviewItem] = []
        for block in page.blocks:
            if not _decision_requires_review(block):
                continue
            reasons = tuple(block.decision.reason_codes)
            confidence = _confidence(evidence, block)
            linhas = _linhas(evidence, block)
            da_pagina.append(ReviewItem(
                target_id=block.id, document_id=document.document_id,
                page_id=page.page_id, page_index=page.page_index, kind=block.kind,
                value=copy.deepcopy(block.decision.value),
                original_value=copy.deepcopy(block.decision.original_value),
                status=block.decision.status, confidence=confidence,
                severity=_severity(block, confidence, linhas), reason_codes=reasons,
                source_refs=tuple(block.source_refs),
                alternatives=_alternatives(evidence, block),
                warnings=tuple(block.warnings), metadata=dict(block.metadata),
                motivos=_motivos(block), linhas=linhas,
            ))
        if limite_por_pagina is not None:
            da_pagina.sort(key=lambda item: (-item.severity, item.target_id))
            da_pagina = da_pagina[:max(0, int(limite_por_pagina))]
        result.extend(da_pagina)
    result.sort(key=lambda item: (-item.severity, item.page_index,
                                  _KIND_PRIORITY.get(item.kind, 5), item.target_id))
    return ReviewQueue(result)


class ReviewJournal:
    """Persistência JSONL append-only; cada linha é um evento completo."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else None
        self._events: list[ReviewEvent] = []

    def append(self, event: ReviewEvent) -> ReviewEvent:
        self._events.append(event)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return event

    def read(self) -> tuple[ReviewEvent, ...]:
        if self.path is None:
            return tuple(self._events)
        if not self.path.exists():
            return ()
        return tuple(ReviewEvent.from_dict(json.loads(line)) for line in
                     self.path.read_text(encoding="utf-8").splitlines() if line.strip())


def _lote_de(event: ReviewEvent) -> str | None:
    return next((code[len(_LOTE):] for code in event.reason_codes
                 if code.startswith(_LOTE)), None)


def _passos(events: Iterable[ReviewEvent]) -> list[list[ReviewEvent]]:
    """Os eventos agrupados em passos do revisor: um evento, ou o lote inteiro
    (eventos seguidos com o mesmo `batch:<id>`)."""
    passos: list[list[ReviewEvent]] = []
    for event in events:
        lote = _lote_de(event)
        if passos and lote is not None and _lote_de(passos[-1][-1]) == lote \
                and ("undo" in event.reason_codes) == ("undo" in passos[-1][-1].reason_codes):
            passos[-1].append(event)
        else:
            passos.append([event])
    return passos


def pilha_de_revisao(events: Iterable[ReviewEvent]) -> list[list[ReviewEvent]]:
    """Os passos do revisor que ainda estão de pé, do mais antigo ao mais
    recente. Cada `undo` tira o passo mais recente da pilha; o próximo `undo`
    desfaz o que ficou no topo. É o que faz dois `undo` voltarem dois passos.
    """
    pilha: list[list[ReviewEvent]] = []
    for passo in _passos(events):
        if "undo" in passo[-1].reason_codes:
            if pilha:
                pilha.pop()
        else:
            pilha.append(passo)
    return pilha


def passos_para_desfazer(events: Iterable[ReviewEvent]) -> list[ReviewEvent]:
    """Os eventos que o próximo `undo` desfaz — o topo da pilha, ou nada."""
    pilha = pilha_de_revisao(events)
    return list(pilha[-1]) if pilha else []


class ReviewSession:
    """Serviço transacional pequeno para aceitar, editar, rejeitar e desfazer."""

    def __init__(self, document: EditorialDocument, *, journal: ReviewJournal | None = None,
                 user: str = "editor", model_version: str = ""):
        self.document = document
        self.journal = journal or ReviewJournal()
        self.user = user
        self.model_version = model_version or document.model_manifest

    @property
    def queue(self) -> ReviewQueue:
        return build_review_queue(self.document)

    def fila(self, *, limite_por_pagina: int | None = None) -> ReviewQueue:
        return build_review_queue(self.document, limite_por_pagina=limite_por_pagina)

    def _block(self, target_id: str) -> tuple[str, EditorialBlock]:
        for page in self.document.pages:
            for block in page.blocks:
                if block.id == target_id:
                    return page.page_id, block
        raise KeyError(f"alvo editorial inexistente: {target_id}")

    def _apply(self, target_id: str, after: Any, status: str,
               reason_codes: Iterable[str]) -> EditorialDocument:
        page_id, block = self._block(target_id)
        event = ReviewEvent(
            event_id=uuid4().hex, document_id=self.document.document_id,
            page_id=page_id, target_id=target_id,
            before=copy.deepcopy(block.decision.value), after=copy.deepcopy(after),
            status=status, reason_codes=tuple(reason_codes), user=self.user,
            created_at=_now(), model_version=self.model_version,
            source_refs=tuple(block.source_refs),
            before_status=block.decision.status,
        )
        atualizado = self.document.apply_review(event)
        self.journal.append(event)
        self.document = atualizado
        return atualizado

    def accept(self, target_id: str) -> EditorialDocument:
        page_id, block = self._block(target_id)
        return self._apply(target_id, block.decision.value, "reviewed", ("accepted",))

    def edit(self, target_id: str, value: Any,
             reason_codes: Iterable[str] = ("human_correction",)) -> EditorialDocument:
        return self._apply(target_id, value, "reviewed", reason_codes)

    def reject(self, target_id: str, value: Any = None) -> EditorialDocument:
        _, block = self._block(target_id)
        return self._apply(target_id, block.decision.value if value is None else value,
                           "rejected", ("rejected",))

    def defer(self, target_id: str) -> EditorialDocument:
        _, block = self._block(target_id)
        return self._apply(target_id, block.decision.value, "unresolved", ("deferred",))

    # ------------------------------------------------------------------
    # As linhas de um bloco
    # ------------------------------------------------------------------

    def linha(self, target_id: str, evidence_id: str) -> LinhaRevisao:
        _, block = self._block(target_id)
        for linha in _linhas(_evidence_map(self.document), block):
            if linha.evidence_id == evidence_id:
                return linha
        raise KeyError(f"linha inexistente no bloco {target_id}: {evidence_id}")

    def valor_com_linha(self, target_id: str, evidence_id: str, novo_texto: str) -> Any:
        """O valor do bloco com o texto de uma linha trocado — sem aplicar.

        A linha é achada pelo texto dela dentro do valor (o parágrafo já
        passou por hífen, caixa e coladas, e o deslocamento guardado pode
        estar velho); na tabela, dentro da célula dela. Se o texto da linha
        já não está lá, `None`: quem chama edita à mão.
        """
        _, block = self._block(target_id)
        linha = self.linha(target_id, evidence_id)
        valor = copy.deepcopy(block.decision.value)
        atual = linha.texto
        if isinstance(valor, str):
            # A linha vazia (a que a cadeia derrubou inteira) não tem onde
            # ser achada no parágrafo: é caso de editar o bloco.
            return valor.replace(atual, novo_texto, 1) if atual and atual in valor else None
        if isinstance(valor, Mapping) and "rows" in valor and linha.celula:
            fila, coluna, _k = linha.celula
            rows = valor["rows"]
            if fila < len(rows) and coluna < len(rows[fila]):
                celula = str(rows[fila][coluna])
                if atual and atual in celula:
                    rows[fila][coluna] = celula.replace(atual, novo_texto, 1)
                    return valor
                if not atual:
                    rows[fila][coluna] = (celula + " " + novo_texto).strip()
                    return valor
        return None

    def substituir_linha(self, target_id: str, evidence_id: str,
                         novo_texto: str) -> EditorialDocument:
        """Troca o texto de uma linha pelo que o revisor escolheu — a âncora,
        a linha do motor, ou o que ele digitou — e registra a decisão."""
        valor = self.valor_com_linha(target_id, evidence_id, novo_texto)
        if valor is None:
            raise ValueError("o texto da linha já não está no bloco; edite o bloco inteiro")
        return self.edit(target_id, valor, ("human_correction", "line_replaced"))

    # ------------------------------------------------------------------
    # Lote e pilha
    # ------------------------------------------------------------------

    def semelhantes(self, target_id: str) -> list[str]:
        """Os alvos da fila com o mesmo tipo e os mesmos motivos deste —
        o que "aceitar semelhantes" aceita, com este incluído."""
        fila = self.queue
        alvo = next((item for item in fila.items if item.target_id == target_id), None)
        if alvo is None:
            return []
        return [item.target_id for item in fila.items
                if item.assinatura == alvo.assinatura]

    def apply_batch(self, target_ids: Iterable[str], *, status: str = "reviewed",
                    confirm: bool = False, sample_size: int | None = None) -> EditorialDocument:
        if not confirm:
            raise ValueError("confirmação explícita exigida para operação em lote")
        if status not in DECISION_STATUSES:
            raise ValueError(f"status de lote inválido: {status}")
        ids = list(target_ids)
        if sample_size is not None:
            ids = ids[:max(0, int(sample_size))]
        lote = uuid4().hex[:12]
        for target_id in ids:
            _, block = self._block(target_id)
            self._apply(target_id, block.decision.value, status, ("batch", f"{_LOTE}{lote}"))
        return self.document

    def passos_desfaziveis(self) -> int:
        """Quantos passos o revisor ainda pode desfazer."""
        return len(pilha_de_revisao(self.document.review_events))

    def undo(self) -> EditorialDocument:
        passo = passos_para_desfazer(self.document.review_events)
        if not passo:
            raise ValueError("não há evento para desfazer")
        for event in reversed(passo):
            # O bloco volta ao valor **e ao estado** de antes do passo: o que
            # foi aceito e desfeito volta para a fila (`automatic`), e o que
            # estava sem solução volta a estar. Evento antigo, sem o estado
            # guardado, fica `reviewed` — o comportamento de antes.
            status = event.before_status if event.before_status in DECISION_STATUSES else "reviewed"
            lote = _lote_de(event)
            codigos = ("undo",) + ((f"{_LOTE}{lote}",) if lote else ())
            self._apply(event.target_id, event.before, status, codigos)
        return self.document

    @classmethod
    def from_journal(cls, document: EditorialDocument, journal: ReviewJournal, *,
                     user: str = "editor", model_version: str = "") -> "ReviewSession":
        session = cls(document, journal=journal, user=user, model_version=model_version)
        for event in journal.read():
            if not any(item.event_id == event.event_id for item in session.document.review_events):
                session.document = session.document.apply_review(event)
        return session
