"""O diário de revisão se lê mesmo com o que a escrita deixou pela metade (RG-07, R-09).

- `read` usava `splitlines()`, que quebra também em U+2028: editar um bloco para
  `Hello world` tornava o diário ilegível para sempre.
- Uma linha truncada no fim (queda no meio da escrita) levantava `JSONDecodeError`, e a
  janela abria uma sessão vazia, sem log, que continuava gravando no arquivo corrompido —
  o evento seguinte saía colado na linha quebrada.
"""

import json
import logging
import os

from core.editorial_model import Decision, EditorialBlock, EditorialDocument, EditorialPage, SourceRef
from core.editorial_review import ReviewJournal, ReviewSession


def _documento():
    ref = SourceRef("doc", 0)
    blocos = [EditorialBlock(id=f"b{i}", kind="paragraph", order=i, source_refs=[ref],
                             decision=Decision(f"texto {i}", [], "automatic", ["legacy_adapter"]))
              for i in range(3)]
    return EditorialDocument("doc", "Doc", "pt", [EditorialPage("p1", 0, [ref], blocos, [])])


def test_o_separador_de_linha_unicode_nao_quebra_o_diario(tmp_path):
    caminho = tmp_path / "saida.review.jsonl"
    sessao = ReviewSession(_documento(), journal=ReviewJournal(caminho))
    sessao.edit("b0", "Hello world")
    sessao.edit("b1", "outro")
    eventos = ReviewJournal(caminho).read()
    assert [e.after for e in eventos] == ["Hello world", "outro"]
    reaberta = ReviewSession.from_journal(_documento(), ReviewJournal(caminho))
    assert reaberta.document.pages[0].blocks[0].decision.value == "Hello world"


def test_a_linha_truncada_e_pulada_e_o_evento_seguinte_e_lido(tmp_path, caplog):
    caminho = tmp_path / "saida.review.jsonl"
    sessao = ReviewSession(_documento(), journal=ReviewJournal(caminho))
    sessao.edit("b0", "primeiro")
    inteira = caminho.read_bytes()
    caminho.write_bytes(inteira + inteira[: len(inteira) // 2])     # a queda no meio da escrita

    with caplog.at_level(logging.WARNING):
        reaberta = ReviewSession.from_journal(_documento(), ReviewJournal(caminho))
    assert any("linha" in r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)
    reaberta.edit("b2", "depois da queda")
    assert caminho.read_bytes().startswith(inteira + inteira[: len(inteira) // 2] + b"\n"), \
        "o evento novo saiu colado na linha truncada (ou a truncada foi apagada)"

    eventos = ReviewJournal(caminho).read()
    assert [e.after for e in eventos] == ["primeiro", "depois da queda"]
    terceira = ReviewSession.from_journal(_documento(), ReviewJournal(caminho))
    assert terceira.document.pages[0].blocks[2].decision.value == "depois da queda"


def test_cada_gravacao_vai_ao_disco(tmp_path, monkeypatch):
    chamadas = []
    original = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (chamadas.append(fd), original(fd))[1])
    caminho = tmp_path / "saida.review.jsonl"
    ReviewSession(_documento(), journal=ReviewJournal(caminho)).edit("b0", "x")
    assert chamadas, "o evento ficou no cache do sistema"
    assert json.loads(caminho.read_text(encoding="utf-8").split("\n")[0])["after"] == "x"
