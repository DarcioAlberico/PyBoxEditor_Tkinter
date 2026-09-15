"""
A fusão por palavra da leitura de livro (OCR-11 e OCR-12 em produção).

A linha destes livros é mista — `25.♖xc7! Amazingly Gashimov missed his
chance` —, e os dois leitores erram em lugares diferentes: a cadeia própria
acerta o lance e erra a prosa (`1n.ssed b.s cbance`), o motor de linha acerta
a prosa e omite a figurina (`25.Exc7!`). O que estes testes fixam é a regra de
quem escreve cada token, a peneira que diz o que é lance, a semelhança que
recusa o registro da linha errada e a métrica que mede prosa e notação cada
uma por si — que é o que a página 30 do Aagaard exigiu.

Rodar sem pytest:      python tests/test_ocr_fusao_por_palavra.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
import pytest

from core import livro, notacao
from core.box_model import BoxEntry
from core.ocr_ab import alinhar_tokens, medir_por_dominio, normalizar_tipografia


# ----------------------------------------------------------------------
# A peneira: o que é lance, e o que é prosa
# ----------------------------------------------------------------------

@pytest.mark.parametrize("token", [
    "25.", "25...", "25.♖xc7!", "exf5", "a6", "O-O", "O-O-O+", "♕d1+", "e8=♕",
    "±", "!?", "26♕g5", "26...g16", "57..♖xc4?", "28.♖xf7+", "hxg7+", "(25.g4?)",
    "Nf3", "Bxc6±", "1-0", "1–0", "40.",
])
def test_o_token_com_forma_de_lance_e_notacao(token):
    assert notacao.e_token_de_notacao(token), token


@pytest.mark.parametrize("token", [
    "and", "a1]d", "2012", "2012.", "40", "Wh6", "Gashimov", "b.s", "move",
    "be", "The", "ab", "a", "I", "Debs", "check.", "68,", "h-pawn", "",
])
def test_a_palavra_de_prosa_nao_e_notacao(token):
    # `a1]d` é o caso que `notacao.parece_lance` aceita e este não pode: é o
    # `and` lido com `1]` no lugar do `n`, e o motor de linha o lê certo.
    assert not notacao.e_token_de_notacao(token), token


def test_o_dominio_da_linha_e_contado_nos_tokens():
    assert livro._dominio_da_linha("28.♖xf7+ ♔e6 29.♖b4!? ♗c3+") == "notation"
    assert livro._dominio_da_linha("Amazingly Gashimov missed his chance") == "prose"
    assert livro._dominio_da_linha("The unprotected knight on c6 is a target.") == "mixed"
    assert livro._dominio_da_linha("— 2012 —") == "unknown"
    assert livro._dominio_da_linha("") == "unknown"


def test_a_semelhanca_separa_a_mesma_linha_da_linha_errada():
    mesma = livro._semelhanca_de_linha(
        "a this pe.1t B]ack n1issed t1e cha[1cc t0 wi[1 t1e gan1c with:",
        "at this point Black missed the chance to win the game with:")
    outra = livro._semelhanca_de_linha(
        "9. Bl Ibet Valhndo Morales' Gibra]tar 201 2 .",
        "The unprotected knight on G is a target. 18.223 Wh6 19.95!")
    assert mesma >= livro.SEMELHANCA_MINIMA_DA_LINHA, mesma
    assert outra < livro.SEMELHANCA_MINIMA_DA_LINHA, outra
    assert livro._semelhanca_de_linha("", "abc") == 0.0


# ----------------------------------------------------------------------
# A fusão: lance da âncora, prosa do motor
# ----------------------------------------------------------------------

def _linha_de_boxes(texto: str, x0: int = 100, largura: int = 10,
                    y1: int = 200, y2: int = 230):
    """Um box por caractere que não é espaço, lado a lado, e o `caixas`."""
    boxes, caixas = [], []
    x = x0
    for c in texto:
        if c == " ":
            caixas.append(-1)
            x += largura
            continue
        boxes.append(BoxEntry("", x, y1, x + largura, y2))
        caixas.append(len(boxes) - 1)
        x += largura
    return boxes, caixas


def _palavras_do_motor(texto: str, ancora: str, x0: int = 100, largura: int = 10,
                       conf: float = 0.95, y1: int = 200, y2: int = 230):
    """As palavras de `texto` com as caixas dos caracteres que ocupam em
    `ancora`, posição a posição — é o que o Tesseract devolve para a mesma
    linha impressa."""
    detalhes = []
    posicao = 0
    for palavra in texto.split(" "):
        inicio = posicao
        fim = posicao + len(palavra)
        detalhes.append((palavra, conf,
                         (x0 + inicio * largura, y1, x0 + fim * largura, y2)))
        posicao = fim + 1
    return tuple(detalhes)


def test_o_lance_fica_com_a_ancora_e_a_prosa_vai_para_o_motor():
    ancora = "A1nazing]y 25.♖xc7! a1]d"
    boxes, caixas = _linha_de_boxes(ancora)
    detalhes = _palavras_do_motor("Amazingly  25.Exc7!  and", ancora)

    texto, contas = livro._fundir_por_palavra(ancora, caixas, boxes, detalhes)

    assert texto == "Amazingly 25.♖xc7! and"
    assert contas["tokens_da_ancora"] == 1
    assert contas["palavras_do_motor"] == 2


def test_a_palavra_que_a_ancora_partiu_sai_uma_vez_so():
    # `2012` lido como `20] 2`: dois tokens da âncora, uma palavra do motor.
    # O espaço da âncora é falso — a tinta é contígua —, e os boxes dizem isso.
    ancora = "Zee 20] 2"
    boxes = [BoxEntry("", 100 + 10 * i, 200, 110 + 10 * i, 230) for i in range(3)]
    boxes += [BoxEntry("", 140 + 10 * i, 200, 150 + 10 * i, 230) for i in range(4)]
    caixas = [0, 1, 2, -1, 3, 4, 5, -1, 6]
    detalhes = (("Zee", 0.95, (100, 200, 130, 230)),
                ("2012", 0.95, (140, 200, 180, 230)))

    texto, contas = livro._fundir_por_palavra(ancora, caixas, boxes, detalhes)

    assert texto == "Zee 2012"
    assert contas["palavras_do_motor"] == 2


def test_as_palavras_que_a_ancora_colou_saem_as_duas():
    ancora = "wi[1t1e game"
    boxes, caixas = _linha_de_boxes(ancora)
    detalhes = _palavras_do_motor("win the game", ancora)

    texto, _contas = livro._fundir_por_palavra(ancora, caixas, boxes, detalhes)

    assert texto == "win the game"


def test_a_palavra_do_motor_sem_token_na_ancora_entra_no_lugar_dela():
    # O caractere derrubado por confiança não abre token na âncora, mas o
    # motor o leu: ele entra na posição em x, e não no fim.
    ancora = "Black is"
    # `Black` em 100–150, um buraco onde estava `just`, e o `is` em 200–220.
    boxes = [BoxEntry("", 100 + 10 * i, 200, 110 + 10 * i, 230) for i in range(5)]
    boxes += [BoxEntry("", 200, 200, 210, 230), BoxEntry("", 210, 200, 220, 230)]
    caixas = [0, 1, 2, 3, 4, -1, 5, 6]
    detalhes = (("Black", 0.95, (100, 200, 150, 230)),
                ("just", 0.95, (160, 200, 190, 230)),
                ("mated.", 0.95, (200, 200, 250, 230)))

    texto, contas = livro._fundir_por_palavra(ancora, caixas, boxes, detalhes)

    assert texto == "Black just mated."
    assert contas["palavras_do_motor"] == 3


def test_a_palavra_fraca_e_a_de_outra_linha_ficam_de_fora():
    ancora = "27.♖g7+ ♔h8 is jus [nate."
    boxes, caixas = _linha_de_boxes(ancora)
    detalhes = list(_palavras_do_motor("27.Eg7t Hh8 is just mate.", ancora))
    # O lance lido sem figurina vem com confiança baixa, e não pode entrar.
    detalhes[0] = (detalhes[0][0], 0.0, detalhes[0][2])
    detalhes[1] = (detalhes[1][0], 0.03, detalhes[1][2])
    # Uma palavra da linha impressa de baixo, dentro do mesmo registro.
    detalhes.append(("Finally,", 0.95, (100, 240, 180, 270)))

    texto, contas = livro._fundir_por_palavra(ancora, caixas, boxes, tuple(detalhes))

    assert texto == "27.♖g7+ ♔h8 is just mate."
    assert contas["palavras_fracas"] == 2
    assert contas["palavras_fora_da_faixa"] == 1


def test_a_prosa_cuja_palavra_foi_para_o_lance_vizinho_fica_com_a_ancora():
    # O motor colou o lance à palavra: `after:25.g4?` cobre os dois tokens da
    # âncora. O lance consome a palavra, e a prosa não pode sumir por isso.
    ancora = "aftcr: 25.g4."
    boxes, caixas = _linha_de_boxes(ancora)
    detalhes = (("after:25.g4?", 0.9, (100, 200, 230, 230)),)

    texto, _contas = livro._fundir_por_palavra(ancora, caixas, boxes, detalhes)

    assert texto == "aftcr: 25.g4."


def test_sem_palavra_do_motor_a_ancora_sai_como_esta():
    ancora = "25.♖xc7! B]ack"
    boxes, caixas = _linha_de_boxes(ancora)

    texto, contas = livro._fundir_por_palavra(ancora, caixas, boxes, ())

    assert texto == ancora
    assert contas["palavras_do_motor"] == 0


def test_o_corretor_nao_toca_no_lance():
    pytest.importorskip("wordfreq")
    # `axb4` são três letras minúsculas e `ab` está no vocabulário: a busca
    # aproximada trocava a captura de peão por `ab4`.
    resultado = livro._corrigir_prosa_contextual(
        "29.exf5 axb4 cxd5 bxa3 the bese ic arc")

    assert resultado == "29.exf5 axb4 cxd5 bxa3 the best it are"


# ----------------------------------------------------------------------
# O laço de `extrair_pagina`: roteamento, registro e os dois modos
# ----------------------------------------------------------------------

def _pagina(linhas):
    doc = fitz.open()
    p = doc.new_page(width=300, height=200)
    for i, linha in enumerate(linhas):
        p.insert_text((30, 40 + i * 20), linha, fontsize=10)
    return doc


def _classificador(char="x", confianca=0.99):
    return lambda recorte: (char, confianca)


def _texto_da_linha_roteirizado(ancoras):
    """Devolve as âncoras na ordem das linhas, com um `caixas` espalhado
    pelos boxes reais da linha — é a geometria que a fusão usa."""
    fila = list(ancoras)

    def falso(img, linha, classificar, conf_minima, coletor=None, pagina=0,
              marcador_glifo=None):
        texto = fila.pop(0)
        n = len(linha)
        caixas = [-1 if c == " " else min(n - 1, i * n // len(texto))
                  for i, c in enumerate(texto)]
        return texto, 0, [None] * len(texto), [None] * len(texto), caixas
    return falso


def _ler_pagina_roteirizado(palavras_por_linha, classificar):
    """Um registro por linha impressa, com as palavras espalhadas pela
    largura real da linha — o que `tesseract_pagina_detalhada_conf` devolve."""
    def ler(img):
        boxes = livro.caixas_e_diagramas(img, classificar)[0]
        registros = []
        for palavras, linha in zip(palavras_por_linha,
                                   livro.quebrar_em_linhas(boxes)):
            x1 = min(b.x1 for b in linha)
            y1 = min(b.y1 for b in linha)
            x2 = max(b.x2 for b in linha)
            y2 = max(b.y2 for b in linha)
            largura = (x2 - x1) / len(palavras)
            detalhes = tuple(
                (palavra, 0.95, (int(x1 + i * largura), y1,
                                 int(x1 + (i + 1) * largura), y2))
                for i, palavra in enumerate(palavras))
            registros.append((" ".join(palavras), 0.9, (x1, y1, x2, y2), detalhes))
        return registros
    return ler


ANCORAS = ("Amaz1ngly m1ssed", "25.♖xc7! B]ack", "28.♖xf7+ ♔e6")
PALAVRAS = (["Amazingly", "missed"], ["25.Exc7!", "Black"], ["28.Bxf7t", "He6"])


def _extrair(monkeypatch, fusao):
    classificar = _classificador()
    monkeypatch.setattr(livro, "_texto_da_linha",
                        _texto_da_linha_roteirizado(ANCORAS))
    doc = _pagina(("aaaaaaaaaaaaaa", "bbbbbbbbbbbbbb", "cccccccccccccc"))
    try:
        return livro.extrair_pagina(
            doc[0], classificar, dpi=150,
            ler_pagina=_ler_pagina_roteirizado(PALAVRAS, classificar),
            fusao=fusao)
    finally:
        doc.close()


def test_a_fusao_por_palavra_guarda_o_lance_e_toma_a_prosa(monkeypatch):
    pagina = _extrair(monkeypatch, "palavra")

    textos = [r["texto"] for r in pagina.roteamento]
    assert textos == ["Amazingly missed", "25.♖xc7! Black", "28.♖xf7+ ♔e6"]
    assert [r["dominio"] for r in pagina.roteamento] == ["prose", "mixed", "notation"]
    assert [r["fonte"] for r in pagina.roteamento] == ["fusao", "fusao", "glyph"]
    # A linha só de lances nem paga o motor: o roteador a manda para a cadeia.
    assert pagina.roteamento[2]["primario"] == "glyph"
    assert pagina.roteamento[2]["linha_ocr"] == "28.Bxf7t He6"
    assert all(r["semelhanca"] is not None for r in pagina.roteamento)
    assert "25.♖xc7! Black" in pagina.texto


def test_o_modo_linha_e_o_de_antes_e_perde_a_figurina(monkeypatch):
    # É o modo que o A/B compara: a linha inteira do motor, com a figurina
    # reposta por coordenada — e aqui não há figurina marcada para repor.
    pagina = _extrair(monkeypatch, "linha")

    textos = [r["texto"] for r in pagina.roteamento]
    assert textos[0] == "Amazingly missed"
    assert textos[1] == "25.Exc7! Black"
    assert textos[2] == "28.♖xf7+ ♔e6"
    assert [r["fonte"] for r in pagina.roteamento] == ["line", "line", "glyph"]


def test_sem_motor_contextual_a_pagina_e_so_da_cadeia(monkeypatch):
    monkeypatch.setattr(livro, "_texto_da_linha",
                        _texto_da_linha_roteirizado(ANCORAS))
    doc = _pagina(("aaaaaaaaaaaaaa", "bbbbbbbbbbbbbb", "cccccccccccccc"))
    try:
        pagina = livro.extrair_pagina(doc[0], _classificador(), dpi=150)
    finally:
        doc.close()

    assert [r["texto"] for r in pagina.roteamento] == list(ANCORAS)
    assert {r["fonte"] for r in pagina.roteamento} == {"glyph"}


def test_modo_de_fusao_invalido_reclama_antes_de_ler():
    doc = _pagina(("aaaa",))
    try:
        with pytest.raises(ValueError, match="fusão"):
            livro.extrair_pagina(doc[0], _classificador(), dpi=150, fusao="frase")
    finally:
        doc.close()


# ----------------------------------------------------------------------
# A métrica: prosa e notação cada uma por si
# ----------------------------------------------------------------------

def test_o_alinhamento_de_tokens_e_o_de_levenshtein():
    assert alinhar_tokens("a b c".split(), "a x c d".split()) == [
        ("a", "a"), ("b", "x"), ("c", "c"), (None, "d")]
    assert alinhar_tokens([], ["a"]) == [(None, "a")]
    assert alinhar_tokens(["a"], []) == [("a", None)]


def test_a_tipografia_e_dobrada_dos_dois_lados():
    assert normalizar_tipografia("Gashimov – Navara 28.♕g5† ‘The’") == \
        "Gashimov - Navara 28.♕g5+ 'The'"


def test_o_erro_vai_para_o_dominio_do_token_da_referencia():
    referencia = "25.♖xc7! Amazingly Gashimov missed his chance 26.♘g3⩲"
    predicao = "25.♖xc7! A1nazing]y Gashimov missed his 26.♘g3t extra"

    contas = medir_por_dominio(referencia, predicao)

    assert contas["prose"]["tokens"] == 5
    assert contas["notation"]["tokens"] == 2
    # São três edições, e não quatro: o alinhamento de Levenshtein prefere
    # duas substituições (`chance`→`26.♘g3t`, `26.♘g3⩲`→`extra`) a remover,
    # substituir e inserir. `A1nazing]y` e `chance` são da prosa; o token da
    # notação substituído é da notação.
    assert contas["prose"]["erros"] == 2
    assert contas["notation"]["erros"] == 1
    assert contas["total"]["erros"] == 3
    assert contas["total"]["tokens"] == 7
    assert contas["prose"]["wer"] == pytest.approx(0.4)
    assert contas["notation"]["cer"] > 0
    assert medir_por_dominio("", "")["total"]["wer"] == 0.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
