"""O texto da linha e as medidas dela andam juntos (RG-15, R-22) — a propriedade P-2.

Três passagens mudavam o texto sem levar a espessura e a lacuna de cada caractere, e o
`negrito.marcar` pula, calado, o parágrafo cujo vetor não tem o comprimento do texto: o
negrito dele sumia. `partir_coladas` também deixava o começo das linhas impressas velho.

A P-2 é conferida aqui em **toda** passada, e nunca por `assert` no tipo: o AbbyChessCraft
monta `Paragrafo` com medidas dele.
"""

import logging

import fitz
import pytest

from core import livro, negrito, pdf_nativo
from core.lexico import Lexico
from core.pagina import PaginaExtraida, Paragrafo
from tests.test_passadas_de_livro import _pdf


def conferir(paginas, onde=""):
    """A P-2: medida do comprimento do texto, ou medida nenhuma; começos dentro do texto,
    em ordem."""
    for pagina in paginas:
        for bloco in pagina.blocos:
            if not isinstance(bloco, Paragrafo):
                continue
            for nome in ("pesos", "lacunas"):
                vetor = getattr(bloco, nome)
                assert vetor is None or len(vetor) == len(bloco.texto), (onde, nome, bloco.texto)
            assert list(bloco.inicios) == sorted(bloco.inicios), (onde, bloco.texto)
            assert all(0 <= i < max(1, len(bloco.texto)) for i in bloco.inicios), (onde, bloco.texto)
            assert all(0 <= a < z <= len(bloco.texto) for a, z in bloco.negrito), (onde, bloco.texto)


def _medidas(texto):
    """Uma espessura por caractere, que diz de quem é: o código da letra."""
    return [float(ord(c)) for c in texto], [float(i) for i in range(len(texto))]


def _linha(texto, **kw):
    pesos, lacunas = _medidas(texto)
    return livro.Linha(topo=10, esquerda=10, altura=20, texto=texto, pesos=pesos,
                       lacunas=lacunas, registro=0, **kw)


def _cada_peso_no_seu_caractere(p):
    return all(peso != peso or peso == ord(c) for c, peso in zip(p.texto, p.pesos))


# ----------------------------------------------------------------------
# Os três cenários
# ----------------------------------------------------------------------

def test_a_linha_da_cadeia_corrigida_leva_as_medidas(tmp_path, monkeypatch):
    """`the knight , and` — a correção tira o espaço, e a espessura ficava com ele."""
    texto = "the knight , and the rook"
    pesos, vaos = _medidas(texto)
    monkeypatch.setattr(livro, "_ler_linha", lambda img, linha, *a, **k: (
        texto, 0, list(pesos), list(vaos), list(range(len(texto))), "glyph", "prose", {}))
    paginas = livro.extrair(_pdf(tmp_path / "l.pdf", 1), lambda r, ref=None: ("a", 0.99), dpi=150)
    paragrafos = [b for p in paginas for b in p.blocos if isinstance(b, Paragrafo)]
    assert paragrafos and all("knight, and" in p.texto for p in paragrafos)
    conferir(paginas)
    assert all(_cada_peso_no_seu_caractere(p) for p in paragrafos)


def test_o_box_de_cada_caractere_acompanha_a_correcao(tmp_path, monkeypatch):
    """O reparo de colagem indexa os boxes pelo caractere do texto: fora de passo, media o
    box do vizinho."""
    texto = "the knight , and the rook"
    pesos, vaos = _medidas(texto)
    monkeypatch.setattr(livro, "_ler_linha", lambda img, linha, *a, **k: (
        texto, 0, list(pesos), list(vaos), [0] * 10 + [1] * (len(texto) - 10), "glyph", "prose", {}))
    monkeypatch.setattr(livro.lexico, "boxes_largos", lambda boxes: {0})
    vistos = []

    def reparar(texto, pesos, vaos, caixas, *resto):
        vistos.append((texto, list(caixas)))
        return texto, pesos, vaos, 0

    monkeypatch.setattr(livro, "_reparar_texto", reparar)
    livro.extrair(_pdf(tmp_path / "l.pdf", 1), lambda r, ref=None: ("a", 0.99), dpi=150,
                  lex=_lexico(), probabilidade=lambda r, c: 0.0)
    assert vistos and all(len(t) == len(c) for t, c in vistos)
    assert all(t[10] == "," for t, c in vistos)


def test_o_paragrafo_corrigido_leva_as_medidas_e_os_comecos():
    """`Blackhasto move`: 17 caracteres contra 15 espessuras."""
    p = livro._paragrafo_de([_linha("It is won. Blackhasto"), _linha("move the king")])
    assert p.texto == "It is won. Black has to move the king"
    conferir([PaginaExtraida(0, [p])])
    assert _cada_peso_no_seu_caractere(p)
    assert [p.texto[i:].split()[0] for i in p.inicios] == ["It", "move"]


def test_o_comeco_que_a_correcao_atravessa():
    """A correção que junta as duas linhas: o começo da segunda cai no que sobrou dela."""
    p = livro._paragrafo_de([_linha("where a a"), _linha("strike wins")])
    assert p.texto == "where a strike wins"
    conferir([PaginaExtraida(0, [p])])
    assert p.texto[p.inicios[1]:] == "strike wins"


def _lexico():
    return Lexico(palavras={"the", "of", "positions", "this", "book", "are", "won", "knight", "rook"})


def test_a_colada_partida_empurra_os_comecos_e_o_negrito(monkeypatch):
    texto = "of positions of positions ofpositions are won this book"
    pesos, lacunas = _medidas(texto)
    corte = texto.index("ofpositions") + 2
    p = Paragrafo(texto, pesos=negrito.vetor(pesos), lacunas=negrito.vetor(lacunas),
                  inicios=[0, texto.index("ofpositions"), texto.index("this")],
                  negrito=[(texto.index("won"), texto.index("won") + 3)])
    monkeypatch.setattr(livro, "_cortes_do_paragrafo", lambda *a: [corte])
    pagina = PaginaExtraida(0, [p])
    assert livro.partir_coladas([pagina], _lexico()) == 1
    conferir([pagina])
    assert [p.texto[i:].split()[0] for i in p.inicios] == ["of", "of", "this"]
    assert [p.texto[a:z] for a, z in p.negrito] == ["won"]


def test_o_corte_no_comeco_da_linha_fica_na_linha_de_baixo():
    """A palavra que o hífen juntou começa a linha no meio dela: o espaço entra antes."""
    assert [livro._empurrado(i, [4]) for i in (0, 3, 4, 9)] == [0, 3, 5, 10]


# ----------------------------------------------------------------------
# O pulo do negrito fala
# ----------------------------------------------------------------------

def test_o_negrito_pulado_e_contado_por_pagina(caplog):
    certo = Paragrafo("abc", pesos=negrito.vetor([0.1] * 3))
    errado = Paragrafo("abc d", pesos=negrito.vetor([0.1] * 3))
    with caplog.at_level(logging.WARNING):
        negrito.marcar([PaginaExtraida(4, [certo]), PaginaExtraida(6, [errado, certo])])
    [registro] = [r for r in caplog.records if "negrito" in r.getMessage()]
    assert "7" in registro.getMessage() and "1 par" in registro.getMessage()


# ----------------------------------------------------------------------
# A P-2 em toda passada
# ----------------------------------------------------------------------

PASSADAS = [(livro, "retirar_cabecalhos"), (livro, "partir_coladas"), (livro, "reparar_pela_camada"),
            (livro.negrito, "marcar"), (pdf_nativo, "ligar_legendas"),
            (pdf_nativo, "retirar_mobilia"), (pdf_nativo, "juntar_entre_paginas"),
            (pdf_nativo, "lados_pelos_lances")]


@pytest.mark.parametrize("camada", ["nunca", "sempre"])
def test_a_p2_vale_depois_de_toda_passada(tmp_path, monkeypatch, camada):
    conferidas = set()
    for modulo, nome in PASSADAS:
        original = getattr(modulo, nome)

        def embrulhada(paginas, *args, _original=original, _nome=nome, **kwargs):
            lista = paginas if isinstance(paginas, (list, tuple)) else [paginas]
            conferir(lista, f"antes de {_nome}")
            feito = _original(paginas, *args, **kwargs)
            conferir(lista, f"depois de {_nome}")
            conferidas.add(_nome)
            return feito

        monkeypatch.setattr(modulo, nome, embrulhada)
    linhas = _linhas_em_roda()
    monkeypatch.setattr(livro, "_ler_linha", lambda img, linha, *a, **k: next(linhas))
    paginas = livro.extrair(_pdf(tmp_path / "l.pdf", 4), lambda r, ref=None: ("a", 0.99), dpi=150,
                            lex=_lexico(), camada=camada)
    conferir(paginas, "no fim")
    # O guarda por página engole o `assert` de dentro dela: a falha é que o denuncia.
    assert not [p.falha for p in paginas if p.falha]
    assert {"retirar_cabecalhos", "partir_coladas", "marcar", "juntar_entre_paginas",
            "lados_pelos_lances"} <= conferidas


def _linhas_em_roda():
    """Linhas que disparam as correções, em roda: cabeçalho, pontuação solta, colada,
    frase de duas linhas, começo em minúscula."""
    textos = ["Attacking Manual 1", "the knight , and Blackhasto", "move of positions of positions",
              "ofpositions where a a", "strike and this was"]
    n = 0
    while True:
        texto = textos[n % len(textos)]
        n += 1
        pesos, vaos = _medidas(texto)
        yield texto, 0, pesos, vaos, list(range(len(texto))), "glyph", "prose", {}


def test_a_p2_na_leitura_de_verdade(tmp_path):
    """Sem dublê de linha: a cadeia inteira, num PDF desenhado, com cada passada embrulhada."""
    with fitz.open() as doc:
        for n in range(3):
            p = doc.new_page(width=400, height=300)
            for i in range(8):
                p.insert_text((30, 40 + i * 18), "Uma linha de prosa, e outra .", fontsize=11)
        doc.save(tmp_path / "l.pdf")
    paginas = livro.extrair(str(tmp_path / "l.pdf"), lambda r, ref=None: ("a", 0.99), dpi=150,
                            lex=_lexico())
    conferir(paginas)
    assert not [p.falha for p in paginas if p.falha]
