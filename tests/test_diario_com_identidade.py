"""O diário de revisão tem identidade (RG-07, R-10).

O nome era `<saida>.review.jsonl` e o `document_id` é o nome do arquivo: reexportar outro
livro para o mesmo destino reabria o diário do primeiro, e o mesmo `except` tratava igual
um diário truncado, um de outro livro e um conflito de valor — a sessão nova continuava
acrescentando ali, e o primeiro evento estranho fazia `from_journal` falhar para sempre.

Agora a identidade vai no nome (`<saida>.<sha12>.review.jsonl`, os doze primeiros dígitos
do `source_sha256`); o diário sem sha no nome é lido e nunca escrito; e o conflito de
valor se resolve por alvo, pela cadeia que termina no último evento.
"""

import logging

from core.editor import importar_ir
from core.editorial_model import Decision, EditorialBlock, EditorialDocument, EditorialPage, SourceRef
from core.editorial_review import ReviewJournal, ReviewSession, abrir_diario, caminhos_do_diario

SHA_A = "a" * 64
SHA_B = "b" * 64


def _documento(sha=SHA_A, valores=("texto 0", "texto 1", "texto 2")):
    ref = SourceRef("saida", 0)
    blocos = [EditorialBlock(id=f"b{i}", kind="paragraph", order=i, source_refs=[ref],
                             decision=Decision(v, [], "automatic", ["legacy_adapter"]))
              for i, v in enumerate(valores)]
    return EditorialDocument("saida", "Doc", "pt", [EditorialPage("p1", 0, [ref], blocos, [])],
                             source_sha256=sha)


def _valor(sessao, alvo):
    return next(b for b in sessao.document.pages[0].blocks if b.id == alvo).decision.value


def _sessao(documento, caminho):
    diario, avisos = abrir_diario(str(caminho), documento)
    sessao = ReviewSession.from_journal(documento, diario)
    return sessao, avisos + sessao.avisos


def test_o_nome_leva_o_sha_e_o_sem_sha_so_se_le(tmp_path):
    caminhos = caminhos_do_diario(str(tmp_path / "saida.review.jsonl"), SHA_A)
    assert caminhos.escrita == str(tmp_path / "saida.aaaaaaaaaaaa.review.jsonl")
    assert caminhos.leitura == (str(tmp_path / "saida.review.jsonl"), caminhos.escrita)
    # O nome que já leva o sha é a própria escrita.
    assert caminhos_do_diario(caminhos.escrita, SHA_A).escrita == caminhos.escrita
    # Sem identidade no documento, o nome fica como era.
    sem = caminhos_do_diario(str(tmp_path / "saida.review.jsonl"), "")
    assert sem.escrita == str(tmp_path / "saida.review.jsonl")


def test_reexportar_outro_livro_para_o_mesmo_destino_nao_toca_no_diario_antigo(tmp_path):
    destino = tmp_path / "saida.review.jsonl"
    sessao_a, _ = _sessao(_documento(SHA_A), destino)
    sessao_a.edit("b0", "correção do livro A")
    diario_a = tmp_path / "saida.aaaaaaaaaaaa.review.jsonl"
    antes = diario_a.read_bytes()

    sessao_b, avisos = _sessao(_documento(SHA_B), destino)
    assert any("outro documento" in a for a in avisos), "o diário de outro livro não foi avisado"
    assert _valor(sessao_b, "b0") == "texto 0", "a correção do livro A entrou no livro B"
    sessao_b.edit("b1", "correção do livro B")
    assert diario_a.read_bytes() == antes, "o diário do livro A recebeu escrita"
    assert (tmp_path / "saida.bbbbbbbbbbbb.review.jsonl").exists()


def test_o_caminho_com_o_sha_de_outro_livro_nao_recebe_escrita(tmp_path):
    sessao_a, _ = _sessao(_documento(SHA_A), tmp_path / "saida.review.jsonl")
    sessao_a.edit("b0", "A")
    guardado = tmp_path / "saida.aaaaaaaaaaaa.review.jsonl"
    antes = guardado.read_bytes()
    sessao_b, avisos = _sessao(_documento(SHA_B), guardado)          # o caminho guardado é o do A
    assert any("outro documento" in a for a in avisos)
    sessao_b.edit("b1", "B")
    assert guardado.read_bytes() == antes


def test_a_leitura_diferente_aplica_o_que_confere_e_pula_o_resto(tmp_path, caplog):
    destino = tmp_path / "saida.review.jsonl"
    sessao, _ = _sessao(_documento(), destino)
    sessao.edit("b0", "corrigido 0")
    sessao.edit("b1", "corrigido 1")
    # A versão nova do pipeline lê o bloco 0 de outro jeito.
    nova = _documento(valores=("texto 0 lido de novo", "texto 1", "texto 2"))
    with caplog.at_level(logging.WARNING):
        reaberta, avisos = _sessao(nova, destino)
    assert _valor(reaberta, "b1") == "corrigido 1"
    assert _valor(reaberta, "b0") == "texto 0 lido de novo"
    assert any("b0" in a for a in avisos)
    assert any("b0" in r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)


def test_a_correcao_velha_nao_volta_por_cima_da_nova(tmp_path):
    destino = tmp_path / "saida.review.jsonl"
    # E1: sobre a leitura v1.
    sessao, _ = _sessao(_documento(valores=("v1", "x", "y")), destino)
    sessao.edit("b0", "correção E1")
    # Leitura v2: E1 é pulado; o revisor grava E2.
    sessao, _ = _sessao(_documento(valores=("v2", "x", "y")), destino)
    assert _valor(sessao, "b0") == "v2"
    sessao.edit("b0", "correção E2")
    # Leitura v3, que volta ao texto de E1: E1 não ressuscita.
    sessao, avisos = _sessao(_documento(valores=("v1", "x", "y")), destino)
    assert _valor(sessao, "b0") != "correção E1", "a correção velha voltou por cima da nova"
    assert any("b0" in a for a in avisos)
    # E na leitura v2, a de E2, vale E2.
    sessao, _ = _sessao(_documento(valores=("v2", "x", "y")), destino)
    assert _valor(sessao, "b0") == "correção E2"


def test_o_diario_sem_sha_no_nome_continua_valendo_e_nao_recebe_escrita(tmp_path):
    legado = tmp_path / "saida.review.jsonl"
    ReviewSession(_documento(), journal=ReviewJournal(legado)).edit("b0", "corrigido no legado")
    antes = legado.read_bytes()

    sessao, _ = _sessao(_documento(), legado)
    assert _valor(sessao, "b0") == "corrigido no legado"
    sessao.edit("b1", "novo")
    assert legado.read_bytes() == antes, "o diário sem sha no nome recebeu escrita"

    reaberta, _ = _sessao(_documento(), legado)
    assert (_valor(reaberta, "b0"), _valor(reaberta, "b1")) == ("corrigido no legado", "novo")


def test_o_caminho_guardado_no_json_e_no_epub_segue_a_regra(tmp_path):
    documento = _documento()
    documento.metadata["review_journal_path"] = str(tmp_path / "saida.review.jsonl")
    assert importar_ir.caminho_do_diario(documento) == str(tmp_path / "saida.aaaaaaaaaaaa.review.jsonl")
    sem_guardado = _documento()
    assert importar_ir.caminho_do_diario(sem_guardado, str(tmp_path / "livro.epub")) == \
        str(tmp_path / "livro.aaaaaaaaaaaa.review.jsonl")


def test_evento_de_outro_documento_no_diario_e_pulado(tmp_path):
    destino = tmp_path / "saida.aaaaaaaaaaaa.review.jsonl"
    outro = EditorialDocument("outro", "Outro", "pt", _documento().pages, source_sha256=SHA_A)
    ReviewSession(outro, journal=ReviewJournal(destino)).edit("b0", "do outro")
    ReviewSession(_documento(), journal=ReviewJournal(destino)).edit("b1", "deste")
    sessao, avisos = _sessao(_documento(), destino)
    assert (_valor(sessao, "b0"), _valor(sessao, "b1")) == ("texto 0", "deste")
    assert any("outro documento" in a for a in avisos)
