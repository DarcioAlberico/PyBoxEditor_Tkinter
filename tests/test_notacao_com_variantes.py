"""Notação com variantes e PGN válido (RG-11, R-30).

- `segmentos` jogava os lances da variante no tabuleiro principal: o diagrama depois de
  uma variante "não batia com a linha", e a partida se partia ao meio, com aviso falso.
- A `(` antes do primeiro lance ficava presa na raiz do PGN: a variante virava a linha
  principal.
- O cabeçalho do PGN levava a quebra de linha do título (`Kasparov,⏎Garry`), e o arquivo
  saía inválido.
"""

import io

import chess
import chess.pgn

from core.editor import modelo as m, pgn_io, xadrez


def p(texto, **kw):
    return m.Paragrafo(trechos=[m.Trecho(texto=texto)], **kw)


def _fen_depois(*lances):
    board = chess.Board()
    for lance in lances:
        board.push_san(lance)
    return board.fen()


def test_a_variante_nao_anda_no_tabuleiro_da_linha():
    blocos = [m.Titulo(trechos=[m.Trecho(texto="Partida")], nivel=2),
              p("1.e4 e5 (1...c5 2.Nf3 d6) 2.Nf3 Nc6", estilo="notacao"),
              m.Diagrama(fen=_fen_depois("e4", "e5", "Nf3", "Nc6")),
              p("3.Bb5 a6", estilo="notacao")]
    segs = xadrez.segmentos(blocos)
    assert len(segs) == 1, "a variante partiu a partida ao meio"
    assert not segs[0].aviso
    assert xadrez.validar(blocos) == []
    posicao = xadrez.posicao_apos(blocos, (3, len("3.Bb5 a6")))
    assert posicao.erro is None and posicao.board.board_fen() == chess.Board(
        _fen_depois("e4", "e5", "Nf3", "Nc6", "Bb5", "a6")).board_fen()


def test_duas_variantes_seguidas_saem_do_mesmo_lugar():
    blocos = [p("1.e4 (1.d4 d5) (1.c4 e5) 1...e5 2.Nf3", estilo="notacao")]
    assert xadrez.validar(blocos) == [], "a segunda variante saiu do lugar errado"


def _pgn(blocos):
    cap = m.Capitulo(arquivo="Text/c.xhtml", blocos=blocos)
    livro = m.Livro(metadados=m.Metadados(titulo="Livro"), capitulos=[cap])
    texto = pgn_io.texto_do_capitulo(cap, livro)
    return texto, chess.pgn.read_game(io.StringIO(texto))


def test_a_variante_antes_do_primeiro_lance_pende_do_primeiro_lance():
    texto, jogo = _pgn([m.Titulo(trechos=[m.Trecho(texto="Abertura")], nivel=2),
                        p("(1.d4 d5) 1.e4 e5 2.Nf3", estilo="notacao")])
    assert [nd.san() for nd in jogo.mainline()] == ["e4", "e5", "Nf3"], "a variante virou a linha principal"
    assert [v.san() for v in jogo.variations] == ["e4", "d4"]
    assert jogo.variations[1].next().san() == "d5"


def test_o_cabecalho_do_pgn_fica_numa_linha():
    titulo = m.Titulo(trechos=[m.Trecho(texto="Kasparov,"), m.Trecho(texto="Garry – Karpov", quebra_antes=True)],
                      nivel=2)
    texto, jogo = _pgn([titulo, p("1.e4 e5", estilo="notacao")])
    for linha in texto.splitlines():
        if linha.startswith("["):
            assert linha.endswith('"]'), f"cabeçalho partido: {linha!r}"
    assert jogo.headers["White"] == "Kasparov, Garry"
