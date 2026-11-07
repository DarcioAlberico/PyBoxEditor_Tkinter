"""A prosa colada ao lance, o parêntese partido e o espaço que só o motor viu.

Os 35 tokens que sobravam na p. 237 do Nunn (a tabela) eram quase todos o
mesmo defeito em três formas: a cadeia cola a prosa ao lance num token só
(`W:W1n(1♖d1!)`, `Draw(1...♖h2!)`) e o token com figurina é lance inteiro
para a fusão — ficava com a âncora, com o motor lendo `W:` `Win` `(1` a 0,9
no mesmo lugar; o `(` sai solto na frente do número (`( 1...♔h6`); e a
régua do espaço da célula de poucos boxes não vê o espaço impresso entre o
número e o lance (`(1♖d1!)`), que o motor vê. Medido em 2026-09-18, na p.
237: 8,19% → 1,87% de CER total; p. 30 do Aagaard 2,40% → 1,37%; as duas do
Yusupov não mudam.
"""

import sys

import pytest

from core import livro
from core.box_model import BoxEntry


def _vetores(texto):
    """Os quatro vetores de `_texto_da_linha` para um texto: box `i` no
    caractere `i`, `-1` no espaço."""
    return (texto, [None] * len(texto), [None] * len(texto),
            [i if c != " " else -1 for i, c in enumerate(texto)])


def _colar(texto):
    saida, pesos, lacunas, caixas = livro._colar_numero_de_lance(*_vetores(texto))
    assert len(saida) == len(pesos) == len(lacunas) == len(caixas)
    return saida


def _partir(texto):
    saida, pesos, lacunas, caixas = livro._partir_prosa_colada_ao_lance(*_vetores(texto))
    assert len(saida) == len(pesos) == len(lacunas) == len(caixas)
    return saida, caixas


# ----------------------------------------------------------------------
# As colagens lexicais
# ----------------------------------------------------------------------

@pytest.mark.parametrize("antes, depois", [
    ("( 1...♔h6/h8)", "(1...♔h6/h8)"),
    ("( 1 ♖e1!)", "(1 ♖e1!)"),
    ("( 1. ..♖d2/e2/h2)", "(1...♖d2/e2/h2)"),
    ("( 1 . ..♖d2/e2/h2)", "(1...♖d2/e2/h2)"),
    ("♖e8 !", "♖e8!"),
    ("W: Win (1 ♖e1 !)", "W: Win (1 ♖e1!)"),
    ("58...♕c1 ! 59.♕xd5", "58...♕c1! 59.♕xd5"),
    ("(l...♖a2!)", "(1...♖a2!)"),
    ("l ...♘g4!", "1...♘g4!"),
])
def test_as_colagens_da_tabela_do_nunn(antes, depois):
    assert _colar(antes) == depois


@pytest.mark.parametrize("antes, depois", [
    # O terceiro ponto encostado na torre (Nunn p. 237): o box é da figurina.
    ("W3a) 1..♖b2? (1...♖f2?", "W3a) 1...♖b2? (1...♖f2?"),
    ("(4..♔f7?", "(4...♔f7?"),
    ("21..Nxd4 22.e5", "21...Nxd4 22.e5"),
    ("12..e5", "12...e5"),
    ("7..O-O", "7...O-O"),
])
def test_a_reticencia_com_um_ponto_a_menos_ganha_o_ponto(antes, depois):
    saida, pesos, lacunas, caixas = livro._colar_numero_de_lance(*_vetores(antes))
    assert saida == depois
    assert len(saida) == len(pesos) == len(lacunas) == len(caixas)
    # O ponto devolvido não tem box nem medida; os outros guardam o deles.
    novo = saida.index("..") + 2
    assert caixas[novo] == -1 and pesos[novo] is None
    assert [c for c in caixas if c >= 0] == [i for i, c in enumerate(antes) if c != " "]


@pytest.mark.parametrize("antes, depois", [
    # A p. 30 do Aagaard: o ponto encosta na torre, ou no `6`.
    ("25♖xc7! Amazingly ... after: 25.g4? ♖g6", "25.♖xc7! Amazingly ... after: 25.g4? ♖g6"),
    ("26♕g5 g6 Perhaps ... 26...♖g6 27.♕xg6!. 27.♕xh6",
     "26.♕g5 g6 Perhaps ... 26...♖g6 27.♕xg6!. 27.♕xh6"),
])
def test_o_ponto_unico_volta_onde_a_linha_usa_ponto(antes, depois):
    assert _colar(antes) == depois


@pytest.mark.parametrize("texto", [
    # O Nunn imprime o lance das brancas com espaço: a linha não tem prova
    # do ponto, e o que se perdeu ali seria o espaço.
    "W: Win (1♖d1!) B: Draw (1...♖h2!)",
    "2 ♖e8! ♔g4 3♖e2! ♖b8",
    # Prova dos dois estilos na mesma linha: não decide.
    "25.g4 26♕g5 27 ♖e1",
    # Sem lance com ponto na linha, nada.
    "26♕g5 g6 Perhaps",
    # A casa antes da figurina não é número de lance.
    "W♔d1 W♔c1 25.g4",
])
def test_o_ponto_unico_nao_volta_sem_a_prova_da_linha(texto):
    assert _colar(texto) == texto


@pytest.mark.parametrize("texto", [
    "1...♖b2?",           # a reticência inteira não ganha um quarto ponto
    "see p. 12.. and",    # dois pontos sem lance depois
    "a2..b3",             # o número tem de começar o token
    "Fig. 3..",           # nada depois
    "1120..♖b2",          # quatro dígitos não são número de lance
])
def test_dois_pontos_sem_numero_e_lance_ficam(texto):
    assert _colar(texto) == texto


@pytest.mark.parametrize("texto", [
    "wins ! and",            # `!` depois de palavra é pontuação da prosa
    "he said 1 . 2 . 3 .",   # números soltos com ponto não são lance
    "201 2 .",               # o ano partido não é `2.`
    "I ... suppose",         # o `I` do diálogo não tem lance depois
    "a ( b",                 # parêntese solto sem número não cola
])
def test_o_que_nao_e_lance_fica_como_esta(texto):
    assert _colar(texto) == texto


# ----------------------------------------------------------------------
# A prosa colada ao lance
# ----------------------------------------------------------------------

@pytest.mark.parametrize("antes, depois", [
    ("W:W1n(1♖d1!)", "W:W1n (1♖d1!)"),
    ("B: Draw(1...♖h2!)", "B: Draw (1...♖h2!)"),
    ("Draw(1...♖h2!) W:", "Draw (1...♖h2!) W:"),
])
def test_o_token_parte_onde_o_lance_comeca(antes, depois):
    saida, caixas = _partir(antes)
    assert saida == depois
    # O espaço novo não tem box; os outros caracteres guardam o deles.
    assert caixas[saida.index(" (")] == -1 if " (" in saida else True


@pytest.mark.parametrize("texto", [
    "T♕ eas",               # uma letra antes da figurina não é prosa
    "W♔d1 W♔c1 W♔b1",       # a fila de cabeçalho da tabela fica inteira
    "ex♕fange fiees",       # figurina no meio da palavra, sem casa depois
    "W: Win (1 ♖e1!)",      # já partido, nada a fazer
    "25.♖xc7! Amazingly",   # lance com forma de lance fica inteiro
    "the ♘ is strong",      # figurina solta na prosa
])
def test_o_que_nao_e_prosa_colada_fica_inteiro(texto):
    saida, _caixas = _partir(texto)
    assert saida == texto


# ----------------------------------------------------------------------
# O espaço que o motor viu dentro do lance
# ----------------------------------------------------------------------

def _linha_de_boxes(larguras, vaos):
    """Boxes lado a lado, com o vão pedido antes de cada um."""
    boxes = []
    x = 100
    for largura, vao in zip(larguras, vaos):
        x += vao
        boxes.append(BoxEntry("", x, 200, x + largura, 230))
        x += largura
    return boxes


def test_o_espaco_entre_numero_e_lance_vem_do_motor():
    """`(1♖d1!)`: o motor leu `(1` e `&d1!)` com um vão entre eles, e o vão
    cai entre o box do `1` e o da figurina — ali havia espaço impresso."""
    texto = "(1♖d1!)"
    linha = _linha_de_boxes([8, 10, 16, 12, 10, 4, 8], [0, 2, 12, 2, 2, 2, 2])
    caixas = list(range(len(texto)))
    palavras = [(linha[0].x1, linha[1].x2), (linha[2].x1 - 1, linha[6].x2)]
    assert livro._espacos_do_motor(texto, caixas, linha, palavras) == "(1 ♖d1!)"


def test_o_motor_nao_parte_o_numero_do_ponto_nem_a_peca_da_casa():
    """`21.♗xc6±`: o motor leu `21 b`, com o vão antes do ponto; e nunca se
    parte a peça da casa, a letra do dígito, a captura do que vem depois."""
    texto = "21.♗xc6±"
    linha = _linha_de_boxes([10, 10, 4, 16, 10, 12, 12, 10], [0, 2, 12, 12, 12, 12, 12, 12])
    caixas = list(range(len(texto)))
    palavras = [(linha[0].x1, linha[1].x2), (linha[2].x1 - 1, linha[7].x2)]
    assert livro._espacos_do_motor(texto, caixas, linha, palavras) == texto
    palavras = [(linha[0].x1, linha[3].x2), (linha[4].x1 - 1, linha[7].x2)]
    assert livro._espacos_do_motor(texto, caixas, linha, palavras) == texto
    palavras = [(linha[0].x1, linha[5].x2), (linha[6].x1 - 1, linha[7].x2)]
    assert livro._espacos_do_motor(texto, caixas, linha, palavras) == texto


@pytest.mark.parametrize("texto", ["O-O", "O-O-O", "1-0", "0-1", "O–O", "1–0", "1—0"])
def test_o_traco_do_roque_e_do_resultado_nao_ganha_espaco(texto):
    """O motor perde o traço fino e devolve `O` e `O` como duas palavras; o
    roque e o resultado ficam inteiros, com qualquer dos três traços."""
    linha = _linha_de_boxes([10] * len(texto), [0] + [4] * (len(texto) - 1))
    caixas = list(range(len(texto)))
    palavras = [(linha[0].x1, linha[0].x2), (linha[2].x1 - 1, linha[-1].x2)]
    assert livro._espacos_do_motor(texto, caixas, linha, palavras) == texto


@pytest.mark.parametrize("texto", ["I...exchange the bishop", "I...exit", "I...example"])
def test_o_i_da_prosa_antes_de_palavra_com_ex_nao_vira_um(texto):
    """`I...exchange` casava `ex` como se fosse casa: a régua pede a casa
    inteira (`e5`, `exd5`, `Nxf4+`), e a palavra da prosa fica como está."""
    assert _colar(texto) == texto


@pytest.mark.parametrize("antes, depois", [
    ("l...exd5", "1...exd5"), ("I...Nxf4+", "1...Nxf4+"), ("l...e5", "1...e5"),
])
def test_o_l_antes_do_lance_inteiro_vira_um(antes, depois):
    assert _colar(antes) == depois


def test_sem_vao_na_ancora_o_motor_nao_manda():
    """Dois boxes encostados não ganham espaço só porque o motor partiu ali."""
    texto = "(1♖d1!)"
    linha = _linha_de_boxes([8, 10, 16, 12, 10, 4, 8], [0, 0, 0, 0, 0, 0, 0])
    caixas = list(range(len(texto)))
    palavras = [(linha[0].x1, linha[1].x2), (linha[2].x1, linha[6].x2)]
    assert livro._espacos_do_motor(texto, caixas, linha, palavras) == texto


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
