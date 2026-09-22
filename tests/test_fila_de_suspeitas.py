"""A fila de suspeitas com evidência (2026-09-19; `docs/REVISAO_MODOS_OCR.md`, §4.5).

A régua em si está em `test_editorial_suspeitas.py`. Aqui, de baixo para cima:

- o **adapter** (`core.editorial_adapters`): cada linha do parágrafo vira
  uma evidência com a âncora, a linha do motor, a caixa e os motivos, e o
  bloco com linha suspeita entra na fila com eles — o sem, não;
- a **fila** (`core.editorial_review`): motivo em frase, linhas no item,
  teto por página, desfazer em pilha (dois `undo` voltam dois passos, e um
  lote volta inteiro), a troca de uma linha pela outra leitura;
- a **volta** (`core.editorial_legacy`): o documento revisado aplicado às
  `PaginaExtraida` que o EPUB/DOCX leem, o FEN redesenhado, o rejeitado
  fora, e o provedor que rasteriza a página na escala em que foi lida.
"""

import numpy as np
import pytest

from core import livro
from core.editorial_adapters import pagina_extraida_para_pagina, paginas_extraidas_para_documento
from core.editorial_legacy import (OpcoesDeFigura, ProvedorDePaginas, aplicar_revisao,
                                   leitura_de_fen)
from core.editorial_review import (ReviewJournal, ReviewSession, build_review_queue,
                                   pilha_de_revisao)
from core.render_diagrama import FONTE_PADRAO
from tests.test_editorial_suspeitas import _pdf, _registro


# ----------------------------------------------------------------------
# O adapter: linha a linha, com as duas leituras
# ----------------------------------------------------------------------

def _pagina(numero=29):
    roteamento = [
        _registro("25♖xc7! Amazingly Gashimov missed his chance",
                  ancora="25♖xc7! A1nazing]y Gasbi1n0v 1nissed bis cbance",
                  linha_ocr="25.8xc7! Amazingly Gashimov missed his chance", caixa=(100, 200, 900, 240)),
        _registro("and only drew on move 40 after: 25.g4? ♖g6",
                  ancora="and on]y drew on movc 40 aftcr: 25.g4? ♖g6",
                  linha_ocr="and only drew on move 40 after: 25.¢4? Hg6", caixa=(100, 250, 880, 290)),
        _registro("White won on move 68, although some difficulties persists here.",
                  ancora="White won on move 68' a]though some diffic1ties pesists here.",
                  linha_ocr="White won on move 68, although some difficulties persists here.",
                  caixa=(100, 320, 700, 360)),
        _registro("", ancora="", linha_ocr="*", dominio="unknown", fonte="glyph",
                  semelhanca=0.0, confianca_ocr=0.92, descartados=1, celula="t0c1l0",
                  caixa=(400, 500, 420, 520)),
        _registro("B♖h2", dominio="notation", fonte="glyph", primario="glyph", semelhanca=None,
                  confianca_ocr=0.0, celula="t0c0l0", caixa=(100, 500, 180, 520)),
    ]
    suspeito = livro.Paragrafo("25♖xc7! Amazingly Gashimov missed his chance and only drew on "
                               "move 40 after: 25.g4? ♖g6", topo=200, pe=290,
                               inicios=[0, 45], registros=[0, 1])
    limpo = livro.Paragrafo("White won on move 68, although some difficulties persists here.",
                            topo=320, pe=360, inicios=[0], registros=[2])
    tabela = livro.Tabela([["B♖h2", ""]])
    recusado = livro.Figura(b"png", 80, 80, origem="recorte", aviso="ocupação a 0,71",
                            caixa=(500, 600, 900, 1000))
    desenhado = livro.Figura(b"png", 80, 80, fen="8/8/8/8/8/8/8/4K2k w - - 0 1", origem="render",
                             caixa=(500, 1100, 900, 1500))
    return livro.PaginaExtraida(numero=numero, blocos=[suspeito, limpo, tabela, recusado, desenhado],
                                largura=1200, altura=1600, dpi=200, roteamento=roteamento)


def test_o_adapter_da_a_cada_linha_a_ancora_o_motor_a_caixa_e_o_motivo():
    pagina = pagina_extraida_para_pagina(_pagina(), document_id="livro")
    bloco = pagina.blocks[0]
    assert bloco.decision.status == "automatic"
    assert bloco.metadata["review_required"] is True
    assert "malformed_move" in bloco.decision.reason_codes
    assert bloco.metadata["motivos"] == ["«25♖xc7!» tem figurina mas não tem forma de lance"]
    evidencias = {e.id: e for e in pagina.evidence}
    assert bloco.decision.evidence_ids == ["evidence-livro-p0030-b0000",
                                           "evidence-livro-p0030-b0000-l000",
                                           "evidence-livro-p0030-b0000-l001"]
    linha = evidencias["evidence-livro-p0030-b0000-l000"]
    assert linha.ref.bbox == (100, 200, 900, 240)
    assert {h.source: h.text for h in linha.alternatives} == {
        "glyph_chain": "25♖xc7! A1nazing]y Gasbi1n0v 1nissed bis cbance",
        "line_engine": "25.8xc7! Amazingly Gashimov missed his chance"}
    assert linha.diagnostics == ["«25♖xc7!» tem figurina mas não tem forma de lance"]
    assert linha.metadata["motivos"] == ["malformed_move"]
    assert linha.confidence < 0.5
    segunda = evidencias["evidence-livro-p0030-b0000-l001"]
    assert segunda.diagnostics == [] and segunda.confidence == pytest.approx(0.9)
    assert bloco.metadata["linhas"][1]["registro"] == 1


def test_o_bloco_sem_linha_suspeita_fica_fora_da_fila_e_o_com_entra():
    documento = paginas_extraidas_para_documento([_pagina()], document_id="livro")
    fila = build_review_queue(documento)
    ids = [item.target_id for item in fila.items]
    assert "block-livro-p0030-b0001" not in ids           # a prosa limpa
    assert "block-livro-p0030-b0004" not in ids           # o diagrama desenhado
    assert ids[0] == "block-livro-p0030-b0003"            # o diagrama recusado primeiro
    assert set(ids) == {"block-livro-p0030-b0000", "block-livro-p0030-b0002",
                        "block-livro-p0030-b0003"}


def test_o_item_da_fila_fala_em_frases_e_traz_as_linhas():
    documento = paginas_extraidas_para_documento([_pagina()], document_id="livro")
    fila = build_review_queue(documento)
    paragrafo = fila.filter(target_id="block-livro-p0030-b0000").items[0]
    assert paragrafo.motivos == ("«25♖xc7!» tem figurina mas não tem forma de lance",)
    assert paragrafo.bbox == (0, 200, 1200, 290)
    assert [linha.suspeita for linha in paragrafo.linhas] == [True, False]
    assert paragrafo.linhas[0].caixa == (100, 200, 900, 240)
    assert paragrafo.linhas[0].motor.startswith("25.8xc7!")
    assert paragrafo.linhas_suspeitas[0].evidence_id.endswith("-l000")
    tabela = fila.filter(target_id="block-livro-p0030-b0002").items[0]
    assert tabela.motivos == ("a linha ficou vazia: a cadeia derrubou 1 caractere(s) por "
                              "confiança; o motor leu «*»",)
    assert tabela.linhas[0].celula == (0, 1, 0)
    diagrama = fila.filter(target_id="block-livro-p0030-b0003").items[0]
    assert diagrama.status == "unresolved"
    assert diagrama.bbox == (500, 600, 900, 1000)
    assert diagrama.motivos[0].startswith("o modelo não confiou na leitura do diagrama")
    assert "ocupação a 0,71" in diagrama.motivos[0]


def test_o_teto_por_pagina_deixa_os_de_maior_impacto():
    documento = paginas_extraidas_para_documento([_pagina(1), _pagina(2)], document_id="livro")
    assert len(build_review_queue(documento).items) == 6
    fila = build_review_queue(documento, limite_por_pagina=1)
    assert [item.kind for item in fila.items] == ["diagram", "diagram"]
    assert fila.pages == (1, 2)
    assert build_review_queue(documento, limite_por_pagina=2).filter(page_index=1).items[1].kind \
        == "table"


def test_a_pagina_sem_motor_marca_a_prosa():
    pagina = _pagina()
    pagina.motor_indisponivel = "página: Tesseract indisponível"
    editorial = pagina_extraida_para_pagina(pagina, document_id="livro")
    limpo = editorial.blocks[1]
    assert "motor_indisponivel" in limpo.decision.reason_codes
    assert limpo.metadata["motivos"][0].startswith("o motor de prosa faltou nesta página")


# ----------------------------------------------------------------------
# A sessão: pilha, lote, troca de linha
# ----------------------------------------------------------------------

def _sessao(tmp_path=None):
    documento = paginas_extraidas_para_documento([_pagina()], document_id="livro")
    journal = ReviewJournal(tmp_path / "revisao.jsonl") if tmp_path else None
    return ReviewSession(documento, journal=journal, user="editor")


def test_dois_undo_voltam_dois_passos_e_o_aceito_volta_para_a_fila(tmp_path):
    sessao = _sessao(tmp_path)
    paragrafo, tabela = "block-livro-p0030-b0000", "block-livro-p0030-b0002"
    sessao.edit(paragrafo, "25.♖xc7! Amazingly Gashimov missed his chance and only drew on "
                           "move 40 after: 25.g4? ♖g6")
    sessao.accept(tabela)
    assert sessao.passos_desfaziveis() == 2
    pendentes = {item.target_id for item in sessao.queue.items}
    assert paragrafo not in pendentes and tabela not in pendentes

    sessao.undo()
    pendentes = {item.target_id for item in sessao.queue.items}
    assert tabela in pendentes and paragrafo not in pendentes
    assert sessao.passos_desfaziveis() == 1

    sessao.undo()
    pendentes = {item.target_id for item in sessao.queue.items}
    assert tabela in pendentes and paragrafo in pendentes
    bloco = next(b for p in sessao.document.pages for b in p.blocks if b.id == paragrafo)
    assert bloco.decision.value.startswith("25♖xc7!")
    assert bloco.decision.status == "automatic"
    assert sessao.passos_desfaziveis() == 0
    with pytest.raises(ValueError):
        sessao.undo()
    # O diário guarda tudo, inclusive o estado anterior de cada evento.
    eventos = ReviewJournal(tmp_path / "revisao.jsonl").read()
    assert [e.before_status for e in eventos] == ["automatic", "automatic", "reviewed", "reviewed"]
    assert len(sessao.document.review_events) == 4


def test_um_passo_novo_depois_do_undo_e_o_que_o_proximo_undo_desfaz():
    sessao = _sessao()
    paragrafo, tabela = "block-livro-p0030-b0000", "block-livro-p0030-b0002"
    sessao.accept(paragrafo)
    sessao.undo()
    sessao.accept(tabela)
    sessao.undo()
    pendentes = {item.target_id for item in sessao.queue.items}
    assert paragrafo in pendentes and tabela in pendentes
    assert pilha_de_revisao(sessao.document.review_events) == []


def test_o_lote_e_um_passo_so_e_a_amostra_vem_dos_semelhantes():
    documento = paginas_extraidas_para_documento([_pagina(1), _pagina(2)], document_id="livro")
    sessao = ReviewSession(documento)
    semelhantes = sessao.semelhantes("block-livro-p0002-b0000")
    assert semelhantes == ["block-livro-p0002-b0000", "block-livro-p0003-b0000"]
    sessao.apply_batch(semelhantes, confirm=True)
    assert sessao.passos_desfaziveis() == 1
    assert not {item.target_id for item in sessao.queue.items} & set(semelhantes)
    sessao.undo()
    assert {item.target_id for item in sessao.queue.items} >= set(semelhantes)
    assert sessao.passos_desfaziveis() == 0


def test_a_linha_troca_pela_leitura_do_motor_dentro_do_paragrafo():
    sessao = _sessao()
    alvo = "block-livro-p0030-b0000"
    item = sessao.queue.filter(target_id=alvo).items[0]
    linha = item.linhas[0]
    sessao.substituir_linha(alvo, linha.evidence_id, linha.motor)
    bloco = next(b for p in sessao.document.pages for b in p.blocks if b.id == alvo)
    assert bloco.decision.value == ("25.8xc7! Amazingly Gashimov missed his chance and only drew "
                                    "on move 40 after: 25.g4? ♖g6")
    assert bloco.decision.status == "reviewed"
    assert "line_replaced" in bloco.decision.reason_codes


def test_a_linha_vazia_da_tabela_recebe_o_que_o_motor_leu():
    sessao = _sessao()
    alvo = "block-livro-p0030-b0002"
    item = sessao.queue.filter(target_id=alvo).items[0]
    vazia = next(linha for linha in item.linhas if linha.celula == (0, 1, 0))
    sessao.substituir_linha(alvo, vazia.evidence_id, "*")
    bloco = next(b for p in sessao.document.pages for b in p.blocks if b.id == alvo)
    assert bloco.decision.value["rows"] == [["B♖h2", "*"]]


def test_a_linha_que_ja_nao_esta_no_bloco_pede_edicao_a_mao():
    sessao = _sessao()
    alvo = "block-livro-p0030-b0000"
    linha = sessao.queue.filter(target_id=alvo).items[0].linhas[0]
    sessao.edit(alvo, "outro texto")
    sessao.undo()
    sessao.edit(alvo, "outro texto")
    with pytest.raises(ValueError, match="edite o bloco inteiro"):
        sessao.substituir_linha(alvo, linha.evidence_id, "x")


# ----------------------------------------------------------------------
# A volta para o leitor
# ----------------------------------------------------------------------

def test_a_revisao_volta_para_as_paginas_do_leitor():
    original = _pagina()
    sessao = _sessao()
    sessao.edit("block-livro-p0030-b0000", "Texto revisado.")
    sessao.reject("block-livro-p0030-b0002")
    sessao.edit("block-livro-p0030-b0003",
                {"fen": "8/8/8/8/8/8/8/4K2k w - - 0 1", "origin": "recorte"})
    sessao.accept("block-livro-p0030-b0004")

    paginas = aplicar_revisao([original], sessao.document, opcoes=OpcoesDeFigura(fonte=FONTE_PADRAO))
    revisada = paginas[0]
    assert revisada.blocos[0].texto == "Texto revisado."
    assert revisada.blocos[0].registros == [] and revisada.blocos[0].pesos is None
    assert [type(b).__name__ for b in revisada.blocos] == ["Paragrafo", "Paragrafo", "Figura", "Figura"]
    figura = revisada.blocos[2]
    assert figura.fen == "8/8/8/8/8/8/8/4K2k w - - 0 1"
    assert figura.origem == "render" and figura.aviso is None
    assert figura.png != b"png" and figura.largura > 80 and len(figura.linhas) == 8
    assert figura.caixa == (500, 600, 900, 1000)
    # O que não foi tocado é o mesmo objeto; a página original não mudou.
    assert revisada.blocos[3] is original.blocos[4]
    assert original.blocos[0].texto.startswith("25♖xc7!")
    assert len(original.blocos) == 5


def test_a_figura_sem_fonte_fica_com_o_fen_e_o_aviso():
    original = _pagina()
    sessao = _sessao()
    sessao.edit("block-livro-p0030-b0003", {"fen": "8/8/8/8/8/8/8/4K2k w - - 0 1"})
    paginas = aplicar_revisao([original], sessao.document,
                              opcoes=OpcoesDeFigura(fonte="Fonte-Que-Nao-Existe"))
    figura = paginas[0].blocos[3]
    assert figura.fen == "8/8/8/8/8/8/8/4K2k w - - 0 1"
    assert figura.origem == "recorte" and figura.png == b"png"
    assert figura.aviso.startswith("FEN revisado, mas não deu para redesenhar")


def test_a_leitura_de_fen_abre_a_posicao_do_ir_no_dialogo():
    leitura = leitura_de_fen("r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1", (5, 6, 105, 106),
                             orientacao="preta")
    assert leitura.caixa == (5, 6, 105, 106)
    assert leitura.orientacao == "preta"
    assert len(leitura.casas) == 64
    assert leitura.tabuleiro().board_fen() == "r3k2r/8/8/8/8/8/8/R3K2R"
    assert leitura.fen().startswith("r3k2r/8/8/8/8/8/8/R3K2R w")
    vazia = leitura_de_fen("lixo", None)
    assert vazia.ocupadas == [] and vazia.caixa == (0, 0, 8, 8)


def test_o_provedor_rasteriza_a_pagina_na_escala_em_que_ela_foi_lida(tmp_path):
    pdf = _pdf(tmp_path / "livro.pdf", paginas=3)
    primeira, segunda = _pagina(0), _pagina(1)
    primeira.dpi = segunda.dpi = 144
    documento = paginas_extraidas_para_documento([primeira, segunda], document_id="livro")
    documento.metadata["source_path"] = str(pdf)
    provedor = ProvedorDePaginas(documento)
    imagem = provedor.imagem(0)
    assert isinstance(imagem, np.ndarray) and imagem.dtype == np.uint8
    # 300 × 200 pt a 144 dpi: o dobro dos pontos.
    assert imagem.shape == (400, 600)
    assert provedor(0) is imagem                       # memorizada
    assert provedor.imagem(1).shape == (400, 600)
    # A página que o documento não tem sai a 300 dpi, a régua do leitor.
    assert provedor.imagem(2).shape == (834, 1250)
    assert provedor.imagem(7) is None
    provedor.fechar()
    assert ProvedorDePaginas(paginas_extraidas_para_documento([primeira])).imagem(0) is None


