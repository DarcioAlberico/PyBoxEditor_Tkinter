"""
Testes de `core/editor/pgn_io.py` (ED-12; SPEC_EDITOR §11.8, AC-ED12-2): o PGN de
"1.e4 e5 2.Nf3 (2.f4 exf4 {gambito}) Nc6 3.Bb5 ⩲" é lido pelo `chess.pgn` com a variante,
o comentário, o `$14` e o STR; o exercício a partir de um diagrama leva `SetUp`/`FEN`; um
capítulo com dois segmentos dá duas partidas; o NAG ambíguo sai como comentário com aviso;
o lance ilegal encerra a partida nele; `escrever` grava UTF-8 e devolve o relatório.

Rodar sem pytest:      .venv/Scripts/python.exe tests/test_editor_pgn.py
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import modelo as m, pgn_io


def p(texto, **kw):
    return m.Paragrafo(trechos=[m.Trecho(texto=texto)], **kw)


def _ler(texto):
    import chess.pgn

    jogos = []
    f = io.StringIO(texto)
    while True:
        jogo = chess.pgn.read_game(f)
        if jogo is None:
            break
        jogos.append(jogo)
    return jogos


def _capitulo():
    return m.Capitulo(arquivo="Text/cap1.xhtml", blocos=[
        m.Titulo(trechos=[m.Trecho(texto="Partidas comentadas")], nivel=1),
        m.Titulo(trechos=[m.Trecho(texto="Kasparov – Karpov (C42)")], nivel=2),
        p("1.e4 e5 2.Nf3 (2.f4 exf4 {gambito}) Nc6 3.Bb5 ⩲ a6 4.Ba4 Nf6 5.O-O Be7 1-0", estilo="notacao"),
        p("Um comentário entre as partidas.", estilo="comentario"),
        m.Titulo(trechos=[m.Trecho(texto="Exercício 1")], nivel=2),
        m.Diagrama(fen="6k1/5ppp/8/8/4r3/8/5PPP/4R1K1 w - - 0 23"),
        m.Paragrafo(trechos=[m.Trecho(texto="23.Rxe4 Kf8 24.Rd4"), m.Trecho(texto="±", papel="nag", nag=16),
                             m.Trecho(texto=" e as brancas estão melhor ½-½")], estilo="notacao"),
    ])


def test_ac2_o_pgn_do_capitulo_com_variante_comentario_nag_str_e_setup(tmp_path):
    cap = _capitulo()
    livro = m.Livro(metadados=m.Metadados(titulo="Livro de partidas"), capitulos=[cap])
    texto = pgn_io.texto_do_capitulo(cap, livro)
    jogos = _ler(texto)
    assert len(jogos) == 2                                                   # dois segmentos → duas partidas
    g1, g2 = jogos
    assert dict(g1.headers) == {"Event": "Partidas comentadas", "Site": "?", "Date": "????.??.??", "Round": "1",
                                "White": "Kasparov", "Black": "Karpov", "Result": "1-0"}
    lances = [nd.san() for nd in g1.mainline()]
    assert lances == ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7"]
    nf3 = g1.next().next().next()
    assert nf3.san() == "Nf3" and len(g1.next().next().variations) == 2
    variante = g1.next().next().variations[1]
    assert variante.san() == "f4" and variante.next().san() == "exf4" and variante.next().comment == "gambito"
    bb5 = next(nd for nd in g1.mainline() if nd.san() == "Bb5")
    assert bb5.nags == {14}                                                  # ⩲ digitado, unívoco
    ultimo = list(g1.mainline())[-1]
    assert ultimo.comment == "Um comentário entre as partidas."             # o parágrafo `comentario` do segmento
    # o exercício: SetUp/FEN, o NAG marcado e a prosa como comentário, resultado normalizado
    assert g2.headers["SetUp"] == "1" and g2.headers["FEN"] == "6k1/5ppp/8/8/4r3/8/5PPP/4R1K1 w - - 0 23"
    assert g2.headers["White"] == "?" and g2.headers["Result"] == "1/2-1/2" and g2.headers["Round"] == "2"
    rd4 = list(g2.mainline())[-1]
    assert rd4.san() == "Rd4" and rd4.nags == {16} and rd4.comment == "e as brancas estão melhor"
    assert "[SetUp \"1\"]" in texto and "$14" in texto and "$16" in texto and "{ gambito }" in texto
    # os cabeçalhos sem o chess.pgn
    assert [t["White"] for t in pgn_io.tags(texto)] == ["Kasparov", "?"]
    # gravado
    caminho = str(tmp_path / "cap1.pgn")
    rel = pgn_io.escrever(cap, caminho, livro)
    assert rel.formato == "pgn" and rel.metadados["partidas"] == 2 and rel.arquivos == [caminho]
    assert rel.capitulos == 1 and rel.blocos == len(cap.blocos) and rel.diagramas_png == 1
    gravado = open(caminho, encoding="utf-8", newline="").read()
    assert gravado == texto and "\r" not in gravado


def test_o_nag_ambiguo_o_lance_ilegal_e_o_capitulo_sem_partida():
    cap = m.Capitulo(arquivo="Text/c.xhtml", blocos=[
        m.Titulo(trechos=[m.Trecho(texto="Só prosa")], nivel=1),
        p("Aqui não há lances, só Nf3 na prosa."),
    ])
    rel = pgn_io.RelatorioDeConversao(formato="pgn")
    assert pgn_io.texto_do_capitulo(cap, None, rel) == "" and rel.metadados["partidas"] == 0
    cap2 = m.Capitulo(arquivo="Text/d.xhtml", blocos=[
        m.Titulo(trechos=[m.Trecho(texto="Fischer – Spassky")], nivel=2),
        p("1.e4 e5 2.Nf3 = Nc6 3.Bb6 a6 4.Ba4", estilo="notacao"),
    ])
    rel2 = pgn_io.RelatorioDeConversao(formato="pgn")
    texto = pgn_io.texto_do_capitulo(cap2, None, rel2)
    [g] = _ler(texto)
    assert [nd.san() for nd in g.mainline()] == ["e4", "e5", "Nf3", "Nc6"]         # parou no Bb6
    assert any("Bb6 não é legal" in a for a in rel2.avisos) and any("NAG sem código" in a for a in rel2.avisos)
    assert list(g.mainline())[2].comment == "="                                    # o ambíguo virou comentário
    assert g.headers["White"] == "Fischer" and g.headers["Black"] == "Spassky" and g.headers["Event"] == "?"
    # duas partidas em segmentos separados por um "1." depois de já haver lances
    cap3 = m.Capitulo(arquivo="Text/e.xhtml", blocos=[
        p("1.e4 e5 2.Nf3 Nc6", estilo="notacao"),
        p("1.d4 d5 2.c4 e6", estilo="notacao"),
    ])
    jogos = _ler(pgn_io.texto_do_capitulo(cap3))
    assert [[nd.san() for nd in g.mainline()] for g in jogos] == [["e4", "e5", "Nf3", "Nc6"], ["d4", "d5", "c4", "e6"]]
    livro = m.Livro(metadados=m.Metadados(titulo="L"), capitulos=[cap, cap2, cap3])
    assert [(n, w, b) for _c, n, w, b in pgn_io.partidas_do_livro(livro)] == [(1, "Fischer", "Spassky"), (2, "?", "?"),
                                                                              (3, "?", "?")]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
