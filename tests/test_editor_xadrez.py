"""
Testes de `core/editor/xadrez.py` (ED-05; SPEC_EDITOR §11.3–§11.7): tokens e segmentos,
`posicao_apos` com variantes e re-sincronização por diagrama (AC-ED05-3), `validar` com a
sugestão (AC-ED05-4, a parte pura), figurinas ↔ letras e `figurina_ao_digitar`
(AC-ED05-5), `marcar_nags` (AC-ED05-6), `numerar_objetos` com `ref`, jogador/abertura,
`cabecalho_em_legenda`, `fonte_do_livro` (AC-ED05-7) — e a paridade de
`melhor_lance_legal` com `notacao._melhor_lance_legal`.

Rodar sem pytest:      python tests/test_editor_xadrez.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import modelo as m, xadrez

RUY = "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"


def p(texto, **kw):
    return m.Paragrafo(trechos=[m.Trecho(texto=texto)], **kw)


def test_tokens_separam_numero_lance_variante_nag_e_resultado():
    t = xadrez.tokens("1.e4 e5 2.Nf3 (2.f4 exf4) Nc6 3.Bb5!? ± 23…♖xe4+ 24.O-O e8=♕# 1-0")
    tipos = [(x.tipo, x.texto) for x in t]
    assert tipos[:6] == [("numero", "1."), ("lance", "e4"), ("lance", "e5"), ("numero", "2."), ("lance", "Nf3"),
                         ("abre", "(")]
    assert ("nag", "!?") in tipos and ("nag", "±") in tipos and ("fecha", ")") in tipos
    assert ("numero", "23…") in tipos and ("lance", "♖xe4+") in tipos and ("lance", "O-O") in tipos
    assert ("lance", "e8=♕#") in tipos and ("resultado", "1-0") in tipos
    numero = next(x for x in t if x.texto == "23…")
    assert numero.numero == 23 and numero.lado == "b"
    assert xadrez.lance_em_san("♘f3") == "Nf3" and xadrez.lance_em_san("0-0-0") == "O-O-O"
    assert [x.texto for x in xadrez.tokens("after Nf3 the bishop")] == ["Nf3"]     # a peneira é do parágrafo


def test_ac3_posicao_apos_ruy_lopez_variante_erro_segmentos_e_diagrama_que_nao_bate():
    blocos = [m.Titulo(trechos=[m.Trecho(texto="Partida")], nivel=2),
              p("1.e4 e5 2.Nf3 (2.f4 exf4) Nc6 3.Bb5", estilo="notacao"),
              p("after Nf3 the bishop goes to b5", estilo="corpo"),
              p("3...a6", estilo="notacao")]
    linha = "1.e4 e5 2.Nf3 (2.f4 exf4) Nc6 3.Bb5"
    board, lado, erro = xadrez.posicao_apos(blocos, (1, len(linha)))
    assert board.fen() == RUY and lado == "b" and erro is None                    # Ruy Lopez, pretas propostas
    board, lado, erro = xadrez.posicao_apos(blocos, (1, len("1.e4 e5 2.Nf3 (2.f4 exf4")))
    assert board.fen().startswith("rnbqkbnr/pppp1ppp/8/8/4Pp2/8/PPPP2PP/RNBQKBNR w") and erro is None   # a variante
    board, lado, erro = xadrez.posicao_apos(blocos, (1, len("1.e4 e5 2.Nf3 (2.f4 exf4) Nc6")))
    assert board.fen().startswith("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w")    # de volta à linha
    # prosa em corpo com "Nf3" é ignorada: a posição depois de 3...a6 vem da linha principal
    board, lado, erro = xadrez.posicao_apos(blocos, (3, 6))
    assert board.fen().startswith("r1bqkbnr/1ppp1ppp/p1n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w") and lado == "w"
    # o lance ilegal interrompe e é mostrado
    ruim = [p("1.e4 e5 2.Nf3 Nc6 3.Bb6 a6", estilo="notacao")]
    pos = xadrez.posicao_apos(ruim, (0, 100))
    assert pos.erro == "Bb6" and pos.board.fullmove_number == 3
    # um segundo 1.e4 depois de um Titulo começa outro segmento
    dois = [p("1.e4 e5", estilo="notacao"), m.Titulo(trechos=[m.Trecho(texto="Outra")], nivel=2),
            p("1.e4 c5 2.Nf3", estilo="notacao")]
    segmentos = xadrez.segmentos(dois)
    assert [(s.inicio, s.fim) for s in segmentos] == [(0, 1), (1, 3)]
    board, _l, _e = xadrez.posicao_apos(dois, (2, 100))
    assert "2p5" in board.fen().split()[0]                                         # a Siciliana, não o e5
    # um 1.e4 depois de lances, sem título, também abre segmento
    tres = [p("1.e4 e5 2.Nf3 1.d4 d5", estilo="notacao")]
    assert len(xadrez.segmentos(tres)) == 1                                        # no mesmo parágrafo: um só
    quatro = [p("1.e4 e5 2.Nf3", estilo="notacao"), p("1.d4 d5", estilo="notacao")]
    assert [(s.inicio, s.fim) for s in xadrez.segmentos(quatro)] == [(0, 1), (1, 2)]
    # um Diagrama cujo FEN difere re-sincroniza com o aviso
    cinco = [p("1.e4 c5 2.Nf3", estilo="notacao"),
             m.Diagrama(fen="rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2", numero=7),
             p("2.c3 d5", estilo="notacao")]
    pos = xadrez.posicao_apos(cinco, (2, 100))
    assert pos.avisos == ["diagrama 7 não bate com a linha; a linha continua dele"]
    assert pos.board.fen().startswith("rnbqkbnr/pp2pppp/8/2pp4/4P3/2P5/PP1P1PPP/RNBQKBNR w")
    # um diagrama que bate não avisa e não abre segmento
    seis = [p("1.e4 c5", estilo="notacao"),
            m.Diagrama(fen="rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"),
            p("2.Nf3 d6", estilo="notacao")]
    assert len(xadrez.segmentos(seis)) == 1 and xadrez.posicao_apos(seis, (2, 100)).avisos == []
    # fora de uma linha de jogo
    assert "não está numa linha de jogo" in xadrez.posicao_apos([p("prosa")], (0, 2)).avisos[0]


def test_ac4_validar_marca_o_ilegal_com_sugestao_e_o_ilegal_dentro_de_variante():
    blocos = [p("1.e4 e5 2.Nf3 Nc6 3.Bb6 a6 4.Ba4", estilo="notacao"),
              p("4...Nf6 5.O-O (5.d3 exf5) Be7", estilo="notacao")]
    problemas = xadrez.validar(blocos)
    assert [(pr.i_bloco, pr.texto, pr.sugestao) for pr in problemas] == [(0, "Bb6", "Bb5"), (1, "exf5", "")]
    assert problemas[0].mensagem == "Bb6 não é legal aqui; talvez Bb5" and problemas[0].bloco_id == blocos[0].id
    assert (problemas[0].inicio, problemas[0].fim) == (len("1.e4 e5 2.Nf3 Nc6 3."), len("1.e4 e5 2.Nf3 Nc6 3.Bb6"))
    assert m.texto_de(blocos[0]) == "1.e4 e5 2.Nf3 Nc6 3.Bb6 a6 4.Ba4"           # o texto não muda
    assert xadrez.validar([p("1.e4 e5 2.Nf3 Nc6 3.Bb5 a6", estilo="notacao")]) == []


def test_melhor_lance_legal_e_custo_da_troca_batem_com_o_notacao():
    notacao = pytest.importorskip("core.notacao")
    import chess

    board = chess.Board()
    for lido in ("e4", "Nf3", "d5", "Qxd7", "O-O", "exd5"):
        conf = [1.0] * len(lido)
        assert xadrez.custo_da_troca(lido, "e4", conf) == notacao.custo_da_troca(lido, "e4", conf)
        meu = xadrez.melhor_lance_legal(board, lido)
        deles = notacao._melhor_lance_legal(board, lido, conf)
        assert meu[2] == deles[2] and set(meu[1]) <= set(deles[1])    # o desempate por prefixo só estreita
    board.push_san("e4"), board.push_san("e5"), board.push_san("Nf3"), board.push_san("Nc6")
    assert xadrez.melhor_lance_legal(board, "Bb6")[0] == "Bb5"


def test_ac5_para_letras_para_figurinas_e_figurina_ao_digitar_so_em_notacao():
    assert xadrez.para_letras("1.♘f3 ♗b5 O-O e8=♕+", "figurinas", "pt") == "1.Cf3 Bb5 O-O e8=D+"
    assert xadrez.para_letras("1.♘f3 ♗b5 O-O e8=♕+", "figurinas", "en") == "1.Nf3 Bb5 O-O e8=Q+"
    assert xadrez.para_letras("1.Cf3 Bb5 e8=D+ e o cavalo", "pt", "en") == "1.Nf3 Bb5 e8=Q+ e o cavalo"
    assert xadrez.para_figurinas("1.Nf3 Bb5 O-O e8=Q+ and the knight", "en") == "1.♘f3 ♗b5 O-O e8=♕+ and the knight"
    assert xadrez.para_figurinas("1.Cf3 Bb5", "pt") == "1.♘f3 ♗b5"
    # a leitura aceita figurinas pretas, a escrita emite as brancas
    assert xadrez.para_letras("1.♞f3 ♝b5", "figurinas", "en") == "1.Nf3 Bb5"
    par = p("1.Nf3 ", estilo="notacao")
    assert xadrez.figurina_ao_digitar(par, 5) and m.texto_de(par) == "1.♘f3 "
    par = p("1.Cf3 ", estilo="comentario")
    assert xadrez.figurina_ao_digitar(par, 5, "pt") and m.texto_de(par) == "1.♘f3 "
    par = p("1.Nf3 ", estilo="corpo")
    assert not xadrez.figurina_ao_digitar(par, 5) and m.texto_de(par) == "1.Nf3 "
    par = m.Paragrafo(trechos=[m.Trecho(texto="1."), m.Trecho(texto="Nf3", negrito=True), m.Trecho(texto=" ")],
                      estilo="notacao")
    assert xadrez.figurina_ao_digitar(par, 5) and [t.texto for t in par.trechos] == ["1.", "♘f3", " "]
    assert par.trechos[1].negrito                                                   # o formato do trecho fica


def test_ac6_marcar_nags_marca_o_univoco_e_lista_o_ambiguo_e_marcar_lances():
    blocos = [p("1.e4 e5 2.Nf3± Nc6 ⩲ = ∞ 3.Bb5!?", estilo="notacao"), p("± na prosa não conta", estilo="corpo")]
    n, ambiguos = xadrez.marcar_nags(blocos)
    nags = [(t.texto, t.nag) for t in blocos[0].trechos if t.papel == "nag"]
    assert n == 3 and nags == [("±", 16), ("⩲", 14), ("!?", 5)] and sorted(ambiguos) == ["=", "∞"]
    assert not any(t.papel for t in blocos[1].trechos)
    assert xadrez.marcar_lances(blocos) == 5
    assert [t.texto for t in blocos[0].trechos if t.papel == "lance"] == ["e4", "e5", "Nf3", "Nc6", "Bb5"]


def test_ac7_numerar_objetos_refaz_a_referencia_e_jogador_abertura_cabecalho_e_fonte():
    livro = editor_livros.livro_completo()
    cap = livro.capitulos[0]
    ref = next(t for t in m.trechos_do_capitulo(cap) if t.ref == "diagrama")
    assert ref.texto == "Diagrama 1"
    m.numerar_objetos(livro, "diagrama")
    assert ref.texto == "Diagrama 1"
    i = cap.blocos.index(next(b for b in cap.blocos if isinstance(b, m.Diagrama)))
    cap.blocos.insert(i, m.Diagrama(fen=editor_livros.FEN))
    numeros = m.numerar_objetos(livro, "diagrama")
    assert ref.texto == "Diagrama 2" and len(numeros) == 5                       # "12" → "13": inserção renumera
    assert xadrez.texto_da_referencia(cap.blocos[i + 1]) == "Diagrama 2"
    alvos = xadrez.alvos_de_referencia(livro)
    assert ("cap1.xhtml", cap.blocos[i + 1].id, "diagrama", "Diagrama 2") in alvos
    assert any(tipo == "titulo" and rot == "Capítulo um" for _a, _i, tipo, rot in alvos)
    # jogador/abertura
    blocos = [m.Titulo(trechos=[m.Trecho(texto="Kasparov – Karpov")], nivel=2),
              p("Siciliana [B90]", estilo="cabecalho-diagrama"),
              p("Garry Kasparov – Anatoly Karpov, Moscou 1985", estilo="legenda")]
    sugestoes = xadrez.sugerir_jogadores_e_aberturas(blocos)
    assert [(s.texto, s.papel, s.chave) for s in sugestoes][:3] == [
        ("Kasparov", "jogador", "Kasparov, Garry"), ("Karpov", "jogador", "Karpov, Anatoly"), ("B90", "abertura", "B90")]
    assert ("Garry Kasparov", "jogador", "Kasparov, Garry") in [(s.texto, s.papel, s.chave) for s in sugestoes]
    assert xadrez.marcar_jogador_abertura(blocos) == 5
    assert [(t.texto, t.papel, t.chave) for t in blocos[0].trechos] == [
        ("Kasparov", "jogador", "Kasparov, Garry"), (" – ", "", ""), ("Karpov", "jogador", "Karpov, Anatoly")]
    assert next(t for t in blocos[1].trechos if t.papel == "abertura").chave == "B90"
    assert xadrez.chave_de_jogador("Ding") == "Ding, Liren" and xadrez.chave_de_jogador("Silva") == "Silva"
    assert xadrez.chave_de_jogador("Silva", {"Silva": "Ana"}) == "Silva, Ana"
    # cabeçalho em legenda: o h2 vira a legenda do diagrama seguinte
    capitulo = m.Capitulo(arquivo="x.xhtml", blocos=[m.Titulo(trechos=[m.Trecho(texto="Kasparov – Karpov")], nivel=2),
                                                     m.MarcaDePagina(pagina=3),
                                                     m.Diagrama(fen="8/8/8/8/8/8/8/K6k w - - 0 1")])
    d = xadrez.cabecalho_em_legenda(capitulo, 0)
    assert d is not None and [t.texto for t in d.legenda] == ["Kasparov – Karpov"] and len(capitulo.blocos) == 2
    assert xadrez.cabecalho_em_legenda(capitulo, 0) is None                       # a marca não é cabeçalho
    # fonte do livro
    assert xadrez.fonte_do_livro(livro, "ChessMerida-Diagram") >= 4
    assert all(b.fonte == "ChessMerida-Diagram" for c in livro.capitulos for b in c.blocos if isinstance(b, m.Diagrama))
    assert xadrez.fonte_do_livro(livro, "ChessMerida-Diagram") == 0
    # a fonte dos símbolos
    livro2 = editor_livros.livro_completo()
    n = xadrez.fonte_dos_simbolos_do_livro(livro2, "simbolos")
    assert n >= 1 and all(t.familia == "simbolos" for c in livro2.capitulos for t in m.trechos_do_capitulo(c)
                          if any(ord(ch) >= 0x2000 for ch in t.texto))
    assert xadrez.fonte_dos_simbolos_do_livro(livro2, "") >= 1
    # a legenda de lado e o alt
    d = m.Diagrama(fen=editor_livros.FEN, lado="b")
    assert xadrez.legenda_de_lado(d, "pt") == "Pretas jogam" and xadrez.legenda_de_lado(d, "en") == "Black to move"
    assert xadrez.legenda_de_lado(m.Diagrama(fen=editor_livros.FEN)) == ""       # lado desconhecido: nada (DEC-06)
    assert xadrez.alt_de(d, "pt").startswith("Brancas: ")


def test_diagrama_dos_lances_grava_o_lado_proposto():
    blocos = [p("1.e4 e5 2.Nf3 Nc6 3.Bb5", estilo="notacao")]
    d, posicao = xadrez.diagrama_dos_lances(blocos, (0, 100), lado_indicador="marca")
    assert d.fen == RUY and d.lado == "b" and d.lado_indicador == "marca" and posicao.erro is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
