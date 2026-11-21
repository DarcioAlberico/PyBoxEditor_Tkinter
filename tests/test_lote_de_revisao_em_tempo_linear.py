"""Aplicar N eventos custa O(N), e o Ctrl+S do editor relê só a cauda do diário (RG-08, R-13).

`apply_review` copiava e validava o documento inteiro a cada evento, e conferia o id
repetido varrendo todos os eventos: reabrir 200 edições num documento de 300 páginas × 12
blocos levava 18 s nesta máquina (`scripts/medidas/medir_lote_de_revisao.py`). E a ponte do
editor relia e reaplicava o diário inteiro a cada salvamento — O(N²) na sessão.
"""

import pytest

from core import editorial_review
from core.editor import importar_ir, modelo as m
from core.editorial_model import Decision, EditorialBlock, EditorialDocument, EditorialPage, ReviewEvent, SourceRef
from core.editorial_review import Pedido, ReviewJournal, ReviewSession
from tests.test_editor_importar_ir import _bloco_de, _livro_e_documento


def _documento(paginas=4, blocos=3):
    pages = []
    for p in range(paginas):
        ref = SourceRef("doc", p)
        lista = [EditorialBlock(id=f"p{p}b{o}", kind="paragraph", order=o, source_refs=[ref],
                                decision=Decision(f"texto {p}.{o}", [], "automatic", ["legacy_adapter"]))
                 for o in range(blocos)]
        pages.append(EditorialPage(f"p{p}", p, [ref], lista, []))
    return EditorialDocument("doc", "Doc", "pt", pages)


def test_aplicar_varios_e_o_mesmo_que_aplicar_um_a_um():
    sessao = ReviewSession(_documento())
    sessao.edit("p0b0", "a")
    sessao.edit("p1b2", "b")
    sessao.edit("p0b0", "c")                     # o mesmo alvo duas vezes
    sessao.reject("p3b1")
    eventos = sessao.document.review_events
    um_a_um = _documento()
    for event in eventos:
        um_a_um = um_a_um.apply_review(event)
    assert _documento().apply_reviews(eventos).to_dict() == um_a_um.to_dict()


def test_uma_copia_e_uma_validacao_por_lote(monkeypatch):
    sessao = ReviewSession(_documento())
    for i in range(6):
        sessao.edit(f"p{i % 4}b{i % 3}", f"v{i}")
    eventos = sessao.document.review_events
    validacoes = []
    original = EditorialDocument.validate
    monkeypatch.setattr(EditorialDocument, "validate", lambda self: (validacoes.append(1), original(self))[1])
    _documento().apply_reviews(eventos)
    assert len(validacoes) == 1, "o documento foi validado a cada evento"


def test_o_evento_recusado_no_meio_nao_muda_nada():
    sessao = ReviewSession(_documento())
    sessao.edit("p0b0", "a")
    bom = sessao.document.review_events[0]
    ruim = ReviewEvent.from_dict({**bom.to_dict(), "event_id": "x", "target_id": "nao-existe"})
    documento = _documento()
    antes = documento.to_dict()
    with pytest.raises(ValueError):
        documento.apply_reviews([bom, ruim])
    assert documento.to_dict() == antes


def test_o_ctrl_s_le_so_a_cauda_e_ve_o_evento_de_outro_gravador(tmp_path, monkeypatch):
    livro, doc = _livro_e_documento(tmp_path)
    diario = importar_ir.caminho_do_diario(doc)
    # 200 eventos anteriores, de outra sessão (o diálogo de revisão da janela principal), no
    # cabeçalho corrido — que não é bloco do livro, e por isso a ponte não o devolve ao texto dele.
    outra = ReviewSession(doc, journal=ReviewJournal(diario))
    for i in range(200):
        outra.edit("block-doc-p0001-b0004", f"cabeçalho {i}")

    _bloco_de(livro, "block-doc-p0001-b0001").trechos = [m.Trecho(texto="Primeiro salvamento.")]
    primeira = importar_ir.gravar_eventos(livro, doc, diario)
    assert len(primeira.documento.review_events) == 201

    # Entre os dois salvamentos, o diálogo de revisão acrescenta um evento.
    ReviewSession.from_journal(doc, ReviewJournal(diario)).edit("block-doc-p0001-b0004", "Da janela.")

    lidas = []
    original = editorial_review.ReviewEvent.from_dict
    monkeypatch.setattr(editorial_review.ReviewEvent, "from_dict",
                        classmethod(lambda cls, d: (lidas.append(1), original(d))[1]))
    _bloco_de(livro, "block-doc-p0001-b0001").trechos = [m.Trecho(texto="Segundo salvamento.")]
    segunda = importar_ir.gravar_eventos(livro, primeira.documento, diario, journal=primeira.journal)
    assert len(lidas) <= 3, f"o salvamento releu o diário inteiro ({len(lidas)} linhas)"
    valores = {b.id: b.decision.value for p in segunda.documento.pages for b in p.blocks}
    assert valores["block-doc-p0001-b0004"] == "Da janela.", "o evento do outro gravador não foi visto"
    assert valores["block-doc-p0001-b0001"] == "Segundo salvamento."


def test_o_projeto_reusa_o_diario_entre_salvamentos(tmp_path):
    from core.editor.projeto import Projeto

    livro, doc = _livro_e_documento(tmp_path)
    projeto = Projeto(livro, None)
    projeto.documento_editorial = doc
    projeto.diario = importar_ir.caminho_do_diario(doc)
    _bloco_de(livro, "block-doc-p0001-b0001").trechos = [m.Trecho(texto="Um.")]
    projeto.salvar_como(str(tmp_path / "livro.epub"))
    primeiro = projeto.ponte.journal
    _bloco_de(livro, "block-doc-p0001-b0001").trechos = [m.Trecho(texto="Dois.")]
    projeto.salvar()
    assert projeto.ponte.journal is primeiro
    assert projeto.religar_documento_editorial() is False or projeto.ponte is None


def test_a_cauda_espera_a_linha_inteira(tmp_path):
    caminho = tmp_path / "d.review.jsonl"
    sessao = ReviewSession(_documento(), journal=ReviewJournal(caminho))
    sessao.aplicar_lote([Pedido("p0b0", "a"), Pedido("p0b1", "b")])
    leitor = ReviewJournal(caminho)
    assert len(leitor.read_cauda()) == 2
    texto = caminho.read_bytes()
    linha = texto.split(b"\n")[0]
    caminho.write_bytes(texto + linha[:20])                      # um gravador no meio da linha
    assert leitor.read_cauda() == ()
    caminho.write_bytes(texto + linha.replace(b'"a"', b'"z"').replace(bom_id(linha), b"0" * 32) + b"\n")
    assert [e.after for e in leitor.read_cauda()] == ["z"]


def bom_id(linha: bytes) -> bytes:
    import json
    return json.loads(linha)["event_id"].encode()
