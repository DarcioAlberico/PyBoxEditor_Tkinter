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
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

from core.editorial_model import (
    FAIXAS_DO_TEXTO,
    DECISION_STATUSES,
    EditorialDocument,
    EditorialBlock,
    Evidence,
    ReviewEvent,
    SourceRef,
)
from core.editorial_suspeitas import PESOS, PROCEDENCIA, descrever_codigos
from core.log import logger

log = logger(__name__)


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
    "side_to_move_legalidade",
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
    """Persistência JSONL append-only; cada linha é um evento completo.

    **A leitura tolera o que a escrita deixou pela metade** (RG-07, R-09). As linhas se
    separam só por `\\n` — `splitlines()` quebrava também em U+2028, e um bloco editado
    para `Hello\\u2028world` tornava o diário ilegível —, e a linha que não se lê (a
    truncada por uma queda no meio da escrita) é pulada com WARNING, sem derrubar as
    outras. Antes de acrescentar, se o arquivo não termina em `\\n`, vai um `\\n`: o
    evento novo não sai colado na linha quebrada. **Sem truncar**: a ponte do
    `appy --editor` e o diálogo de revisão podem escrever no mesmo diário, e cortar o
    fim apagaria o evento do outro. Cada gravação termina em `fsync`.
    """

    def __init__(self, path: str | Path | None = None, *, anteriores: Iterable[str | Path] = ()):
        self.path = Path(path) if path is not None else None
        #: Diários lidos **antes** de `path` e nunca escritos: o de nome sem sha, anterior à
        #: identidade no nome (RG-07, R-10). Os eventos deles continuam valendo.
        self.anteriores = tuple(Path(p) for p in anteriores if self.path is None or Path(p) != self.path)
        self._events: list[ReviewEvent] = []

    def append(self, event: ReviewEvent) -> ReviewEvent:
        self.append_lote([event])
        return event

    def append_lote(self, events: Iterable[ReviewEvent]) -> None:
        """Os eventos de uma transação, numa gravação e num `fsync` (RG-07, R-12)."""
        events = list(events)
        if not events:
            return
        self._events.extend(events)
        if self.path is not None:
            self._gravar(events)

    def _gravar(self, events: Iterable[ReviewEvent]) -> None:
        linhas = "".join(json.dumps(event.to_dict(), ensure_ascii=False) + "\n" for event in events)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as stream:
            if stream.tell() and not _termina_em_quebra(self.path):
                stream.write(b"\n")
            stream.write(linhas.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())

    def read(self) -> tuple[ReviewEvent, ...]:
        if self.path is None:
            return tuple(self._events)
        eventos: list[ReviewEvent] = []
        vistos: set[str] = set()
        for caminho in self.anteriores + (self.path,):
            for event in _ler_diario(caminho):
                if event.event_id not in vistos:
                    vistos.add(event.event_id)
                    eventos.append(event)
        return tuple(eventos)


def _ler_diario(caminho: Path) -> list[ReviewEvent]:
    if not caminho.exists():
        return []
    texto = caminho.read_bytes().decode("utf-8", errors="replace")
    eventos = []
    for numero, linha in enumerate(texto.split("\n"), start=1):
        if not linha.strip():
            continue
        try:
            eventos.append(ReviewEvent.from_dict(json.loads(linha)))
        except (ValueError, KeyError, TypeError) as erro:
            log.warning("diário %s: a linha %d não se lê e foi pulada (%s)", caminho, numero, erro)
    return eventos


#: O sufixo do diário de revisão; o nome com identidade é `<saida>.<sha12>.review.jsonl`.
SUFIXO_DO_DIARIO = ".review.jsonl"
_SHA_NO_NOME = re.compile(r"\.([0-9a-f]{12})$")


@dataclass(frozen=True)
class CaminhosDoDiario:
    """Onde a sessão de um documento grava o diário e o que ela lê, na ordem."""

    escrita: str
    leitura: tuple[str, ...]
    aviso: str = ""


def caminhos_do_diario(caminho: str, sha256: str) -> CaminhosDoDiario:
    """
    A regra do nome do diário (RG-07, R-10): **a identidade vai no nome**,
    `<saida>.<sha12>.review.jsonl`, com os doze primeiros dígitos do `source_sha256`.

    `caminho` é o guardado (`review_journal_path` no JSON, `origem.diario` no EPUB) ou o
    derivado da saída, e passa pela regra — não por cima dela. O diário de nome sem sha
    é lido antes do com sha e nunca escrito: regravá-lo carimbaria o sha atual num
    diário que pode ser de outro livro de mesmo nome, e uma linha de cabeçalho quebraria
    quem conta as linhas. O de sha **diferente** é de outro documento: não é lido nem
    escrito, e o aviso diz para onde as revisões deste vão. Documento sem `source_sha256`
    não tem identidade, e o nome fica como era.
    """
    if not caminho:
        return CaminhosDoDiario("", ())
    texto = os.fspath(caminho)
    base = texto[:-len(SUFIXO_DO_DIARIO)] if texto.endswith(SUFIXO_DO_DIARIO) else os.path.splitext(texto)[0]
    achado = _SHA_NO_NOME.search(base)
    do_nome = ""
    if achado:
        base, do_nome = base[:achado.start()], achado.group(1)
    sha12 = (sha256 or "")[:12].lower()
    if not sha12:
        return CaminhosDoDiario(texto, (texto,))
    legado = base + SUFIXO_DO_DIARIO
    escrita = f"{base}.{sha12}{SUFIXO_DO_DIARIO}"
    outros = [p for p in _diarios_com_sha(base) if p != escrita]
    aviso = ""
    if (do_nome and do_nome != sha12) or outros:
        de_outro = texto if do_nome and do_nome != sha12 else outros[0]
        aviso = (f"o diário {de_outro} é de outro documento (outra origem): fica como está, "
                 f"e as revisões deste vão para {escrita}")
    return CaminhosDoDiario(escrita, (legado, escrita), aviso)


def _diarios_com_sha(base: str) -> list[str]:
    pasta, nome = os.path.split(base)
    try:
        nomes = os.listdir(pasta or ".")
    except OSError:
        return []
    padrao = re.compile(re.escape(nome) + r"\.[0-9a-f]{12}" + re.escape(SUFIXO_DO_DIARIO) + "$")
    return sorted(os.path.join(pasta, n) for n in nomes if padrao.match(n))


def abrir_diario(caminho: str, documento: EditorialDocument) -> tuple[ReviewJournal, list[str]]:
    """O diário do `documento` pela regra do nome, e os avisos dela (RG-07, R-10)."""
    caminhos = caminhos_do_diario(caminho, documento.source_sha256)
    if not caminhos.escrita:
        return ReviewJournal(), []
    avisos = [caminhos.aviso] if caminhos.aviso else []
    for aviso in avisos:
        log.warning("%s", aviso)
    return ReviewJournal(caminhos.escrita, anteriores=caminhos.leitura), avisos


def _termina_em_quebra(caminho: Path) -> bool:
    with caminho.open("rb") as stream:
        stream.seek(-1, os.SEEK_END)
        return stream.read(1) == b"\n"


def _metadata_de_antes(block: EditorialBlock, metadata: Mapping[str, Any],
                       texto_muda: bool) -> dict[str, Any]:
    """O valor atual das chaves que o evento vai mexer — e das faixas do texto,
    quando o valor muda e `apply_review` as descarta —, para o `undo` repor."""
    antes: dict[str, Any] = {}
    estilo = metadata.get("style")
    chaves_de_estilo = set(estilo) if isinstance(estilo, Mapping) else set()
    if texto_muda:
        chaves_de_estilo.update(FAIXAS_DO_TEXTO)
    if chaves_de_estilo:
        antes["style"] = {chave: copy.deepcopy(block.style.get(chave)) for chave in sorted(chaves_de_estilo)}
    for chave in metadata:
        if chave != "style":
            antes[chave] = copy.deepcopy(block.metadata.get(chave))
    return antes


def _recusar_reservados(reason_codes: Iterable[str]) -> None:
    """`undo` e `batch:<id>` são marcas da pilha de desfazer (RG-07, R-11): vindos de fora,
    um `edit` com `("undo",)` era tomado por um desfazer e corrompia a pilha."""
    for codigo in reason_codes:
        if codigo == "undo" or str(codigo).startswith(_LOTE):
            raise ValueError(f"motivo reservado para desfazer e lote: {codigo!r}")


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


@dataclass(frozen=True)
class Pedido:
    """Um evento de `ReviewSession.aplicar_lote`: o alvo, o valor novo e, por evento, o
    status, os motivos e o metadata (RG-07, R-12)."""

    target_id: str
    after: Any
    status: str = "reviewed"
    reason_codes: tuple[str, ...] = ("human_correction",)
    metadata: Mapping[str, Any] | None = None


def _bloco_em(documento: EditorialDocument, target_id: str) -> tuple[str, EditorialBlock]:
    for page in documento.pages:
        for block in page.blocks:
            if block.id == target_id:
                return page.page_id, block
    raise KeyError(f"alvo editorial inexistente: {target_id}")


class ReviewSession:
    """Serviço transacional pequeno para aceitar, editar, rejeitar e desfazer."""

    def __init__(self, document: EditorialDocument, *, journal: ReviewJournal | None = None,
                 user: str = "editor", model_version: str = ""):
        self.document = document
        self.journal = journal or ReviewJournal()
        self.user = user
        self.model_version = model_version or document.model_manifest
        #: O que `from_journal` deixou de aplicar, em frases (RG-07, R-10).
        self.avisos: list[str] = []

    @property
    def queue(self) -> ReviewQueue:
        return build_review_queue(self.document)

    def fila(self, *, limite_por_pagina: int | None = None) -> ReviewQueue:
        return build_review_queue(self.document, limite_por_pagina=limite_por_pagina)

    def _block(self, target_id: str) -> tuple[str, EditorialBlock]:
        return _bloco_em(self.document, target_id)

    def _apply(self, target_id: str, after: Any, status: str,
               reason_codes: Iterable[str],
               metadata: Mapping[str, Any] | None = None, *, interno: bool = False) -> EditorialDocument:
        reason_codes = tuple(reason_codes)
        if not interno:
            _recusar_reservados(reason_codes)
        return self._aplicar_varios([(target_id, after, status, reason_codes, metadata)])

    def _aplicar_varios(self, pedidos: list[tuple[str, Any, str, tuple[str, ...], Mapping[str, Any] | None]]) \
            -> EditorialDocument:
        """
        Aplica os pedidos `(alvo, valor, status, motivos, metadata)` como **uma**
        transação (RG-07, R-12): os eventos se montam e se aplicam a um documento de
        trabalho, e só depois de todos passarem vão ao diário, numa gravação. Um alvo
        que não existe, ou um evento que o documento recusa, levanta sem gravar nada —
        antes, o lote aplicava a metade e levantava, e o diário ficava com ela.
        """
        documento = self.document
        eventos: list[ReviewEvent] = []
        for target_id, after, status, reason_codes, metadata in pedidos:
            page_id, block = _bloco_em(documento, target_id)
            metadata = dict(metadata or {})
            event = ReviewEvent(
                event_id=uuid4().hex, document_id=documento.document_id,
                page_id=page_id, target_id=target_id,
                before=copy.deepcopy(block.decision.value), after=copy.deepcopy(after),
                status=status, reason_codes=tuple(reason_codes), user=self.user,
                created_at=_now(), model_version=self.model_version,
                source_refs=tuple(block.source_refs),
                before_status=block.decision.status,
                metadata=metadata,
                before_metadata=_metadata_de_antes(block, metadata, after != block.decision.value),
                before_reason_codes=tuple(block.decision.reason_codes),
            )
            documento = documento.apply_review(event)
            eventos.append(event)
        self.journal.append_lote(eventos)
        self.document = documento
        return documento

    def accept(self, target_id: str) -> EditorialDocument:
        page_id, block = self._block(target_id)
        return self._apply(target_id, block.decision.value, "reviewed", ("accepted",))

    def edit(self, target_id: str, value: Any,
             reason_codes: Iterable[str] = ("human_correction",),
             metadata: Mapping[str, Any] | None = None) -> EditorialDocument:
        """O valor novo e, em `metadata`, o que a revisão sabe além dele — a chave
        `style` com `bold_spans`/`italic_spans` do texto novo é o que leva o
        negrito e o itálico do editor de livros ao documento (ED-pré)."""
        return self._apply(target_id, value, "reviewed", reason_codes, metadata)

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
        # Os alvos se conferem antes do primeiro evento (RG-07, R-12), e o lote é uma
        # transação só: o alvo inexistente não deixa a metade do lote no diário.
        valores = {target_id: self._block(target_id)[1].decision.value for target_id in ids}
        lote = uuid4().hex[:12]
        return self._aplicar_varios([(target_id, valores[target_id], status, ("batch", f"{_LOTE}{lote}"), None)
                                     for target_id in ids])

    def aplicar_lote(self, pedidos: Iterable["Pedido"]) -> EditorialDocument:
        """
        Um lote com status por evento (RG-07, R-12) — o que a ponte do editor grava a cada
        salvamento, e que por isso é um passo só de desfazer. `apply_batch` exige
        `confirm` e um status para todos; este recebe os pedidos prontos, confere os
        alvos, os status e os motivos antes do primeiro evento, e não grava nada se um
        deles não serve.
        """
        pedidos = list(pedidos)
        for pedido in pedidos:
            if pedido.status not in DECISION_STATUSES:
                raise ValueError(f"status de evento inválido: {pedido.status!r}")
            _recusar_reservados(pedido.reason_codes)
            self._block(pedido.target_id)
        if not pedidos:
            return self.document
        lote = uuid4().hex[:12]
        return self._aplicar_varios([(p.target_id, p.after, p.status,
                                      tuple(p.reason_codes) + (f"{_LOTE}{lote}",), p.metadata)
                                     for p in pedidos])

    def passos_desfaziveis(self) -> int:
        """Quantos passos o revisor ainda pode desfazer."""
        return len(pilha_de_revisao(self.document.review_events))

    def undo(self) -> EditorialDocument:
        passo = passos_para_desfazer(self.document.review_events)
        if not passo:
            raise ValueError("não há evento para desfazer")
        pedidos = []
        for event in reversed(passo):
            # O bloco volta ao valor **e ao estado** de antes do passo: o que
            # foi aceito e desfeito volta para a fila (`automatic`), e o que
            # estava sem solução volta a estar. Evento antigo, sem o estado
            # guardado, fica `reviewed` — o comportamento de antes.
            status = event.before_status if event.before_status in DECISION_STATUSES else "reviewed"
            lote = _lote_de(event)
            # As marcas primeiro, os motivos de antes depois (RG-07, R-11): a decisão
            # volta com os motivos que tinha, e o bloco que estava na fila volta a ela.
            codigos = ("undo",) + ((f"{_LOTE}{lote}",) if lote else ()) + tuple(event.before_reason_codes)
            # O estilo e o metadata voltam ao que eram (`before_metadata`), como o valor.
            pedidos.append((event.target_id, event.before, status, codigos, dict(event.before_metadata) or None))
        # O passo inteiro se desfaz numa transação: ou volta todo, ou nada (RG-07, R-12).
        return self._aplicar_varios(pedidos)

    @classmethod
    def from_journal(cls, document: EditorialDocument, journal: ReviewJournal, *,
                     user: str = "editor", model_version: str = "") -> "ReviewSession":
        """
        A sessão com o que o diário já decidiu (RG-07, R-10). Não levanta pelo que o
        diário traz: o evento de outro documento é pulado, e o conflito de valor se
        resolve **por alvo**, pela cadeia que termina no último evento gravado — os
        eventos seguidos em que o valor anterior de cada um é o posterior do outro. Se o
        valor anterior do primeiro da cadeia confere com o bloco, ela aplica; se não, o
        alvo é pulado com WARNING, e os outros aplicam. Um evento que tem sucessor nunca
        se aplica sozinho: a leitura que volta ao texto antigo não ressuscita a correção
        velha por cima da nova (invariante 2). O que se pulou fica em `avisos`.
        """
        session = cls(document, journal=journal, user=user, model_version=model_version)
        ja = {item.event_id for item in session.document.review_events}
        deste: list[ReviewEvent] = []
        de_outro = 0
        for event in journal.read():
            if event.document_id != document.document_id:
                de_outro += 1
            elif event.event_id not in ja:
                ja.add(event.event_id)
                deste.append(event)
        if de_outro:
            session._avisar(f"{de_outro} evento(s) do diário são de outro documento e ficaram de fora")
        por_alvo: dict[tuple[str, str], list[ReviewEvent]] = {}
        for event in deste:
            por_alvo.setdefault((event.page_id, event.target_id), []).append(event)
        valores = {(page.page_id, block.id): block.decision.value
                   for page in session.document.pages for block in page.blocks}
        aplicar: set[str] = set()
        for (page_id, alvo), eventos in por_alvo.items():
            inicio = len(eventos) - 1
            while inicio > 0 and eventos[inicio - 1].after == eventos[inicio].before:
                inicio -= 1
            cadeia = eventos[inicio:]
            if (page_id, alvo) not in valores:
                session._avisar(f"o alvo {alvo} do diário não existe neste documento; "
                                f"{len(eventos)} evento(s) ficaram de fora")
            elif valores[(page_id, alvo)] != cadeia[0].before:
                session._avisar(f"o bloco {alvo} foi lido de outro jeito desde a revisão: "
                                f"as correções do diário para ele ficaram de fora")
            else:
                aplicar.update(event.event_id for event in cadeia)
        for event in deste:
            if event.event_id in aplicar:
                session.document = session.document.apply_review(event)
        return session

    def _avisar(self, aviso: str) -> None:
        log.warning("%s", aviso)
        self.avisos.append(aviso)
