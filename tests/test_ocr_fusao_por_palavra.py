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
    "±", "!?", "26♕g5", "57..♖xc4?", "28.♖xf7+", "hxg7+", "(25.g4?)",
    "Nf3", "Bxc6±", "1-0", "1–0", "40.",
])
def test_o_token_com_forma_de_lance_e_notacao(token):
    assert notacao.e_token_de_notacao(token), token


@pytest.mark.parametrize("token", [
    "and", "a1]d", "2012", "2012.", "40", "Wh6", "Gashimov", "b.s", "move",
    "be", "The", "ab", "a", "I", "Debs", "check.", "68,", "h-pawn", "",
    # O pingo do `i` que não fundiu vira `1.`, e a palavra não é lance: ela
    # tem de ir para o motor, que a lê certa. (`26...g16`, o lance lido torto,
    # paga o preço e também vai — era o único caso do outro lado.)
    "1.s", "1.n", "1.mportant", "1.z1.n", "26...g16",
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


def _ler_pagina_roteirizado(palavras_por_linha, classificar, pular=()):
    """Um registro por linha impressa, com as palavras espalhadas pela
    largura real da linha — o que `tesseract_pagina_detalhada_conf` devolve.
    As linhas em `pular` ficam sem registro, como um cabeçalho que o
    `--psm 3` deixou passar."""
    def ler(img):
        boxes = livro.caixas_e_diagramas(img, classificar)[0]
        registros = []
        for indice, (palavras, linha) in enumerate(zip(
                palavras_por_linha, livro.quebrar_em_linhas(boxes))):
            if indice in pular:
                continue
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


def _ler_faixa_roteirizado(palavras, chamadas):
    """O `tesseract_faixa_detalhada_conf` de mentira: espalha `palavras` pela
    largura da faixa recebida, em coordenadas **da faixa**, e anota cada
    chamada — o fallback tem de rodar só para a linha sem registro."""
    def ler(faixa):
        chamadas.append(faixa.shape)
        altura, largura = faixa.shape[:2]
        margem = livro.MARGEM_DA_FAIXA
        util = largura - 2 * margem
        passo = util / len(palavras)
        detalhes = tuple(
            (palavra, 0.95, (int(margem + i * passo), margem,
                             int(margem + (i + 1) * passo), altura - margem))
            for i, palavra in enumerate(palavras))
        return [(" ".join(palavras), 0.9,
                 (margem, margem, largura - margem, altura - margem), detalhes)]
    return ler


ANCORAS = ("Amaz1ngly m1ssed", "25.♖xc7! B]ack", "28.♖xf7+ ♔e6")
PALAVRAS = (["Amazingly", "missed"], ["25.Exc7!", "Black"], ["28.Bxf7t", "He6"])


def _extrair(monkeypatch, fusao, pular=(), ler_faixa=None):
    classificar = _classificador()
    monkeypatch.setattr(livro, "_texto_da_linha",
                        _texto_da_linha_roteirizado(ANCORAS))
    doc = _pagina(("aaaaaaaaaaaaaa", "bbbbbbbbbbbbbb", "cccccccccccccc"))
    try:
        return livro.extrair_pagina(
            doc[0], classificar, dpi=150,
            ler_pagina=_ler_pagina_roteirizado(PALAVRAS, classificar, pular),
            ler_faixa=ler_faixa, fusao=fusao)
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


def test_a_linha_sem_registro_e_lida_pela_faixa_dela(monkeypatch):
    # A passada de página pulou a segunda linha; a faixa dela é lida sozinha,
    # e só ela — o fallback custa uma chamada de processo por linha.
    chamadas = []
    pagina = _extrair(monkeypatch, "palavra", pular=(1,),
                      ler_faixa=_ler_faixa_roteirizado(["25.Exc7!", "Black"],
                                                       chamadas))

    textos = [r["texto"] for r in pagina.roteamento]
    assert textos == ["Amazingly missed", "25.♖xc7! Black", "28.♖xf7+ ♔e6"]
    assert pagina.roteamento[1]["fonte"] == "fusao"
    assert pagina.roteamento[1]["faixa"] is True
    assert "faixa" not in pagina.roteamento[0]
    assert len(chamadas) == 1


def test_sem_leitor_de_faixa_a_linha_sem_registro_fica_com_a_cadeia(monkeypatch):
    pagina = _extrair(monkeypatch, "palavra", pular=(1,))

    assert pagina.roteamento[1]["texto"] == "25.♖xc7! B]ack"
    assert pagina.roteamento[1]["fonte"] == "glyph"


def test_a_faixa_que_falha_nao_derruba_a_pagina(monkeypatch):
    def quebra(_faixa):
        raise RuntimeError("tesseract ausente")

    pagina = _extrair(monkeypatch, "palavra", pular=(1,), ler_faixa=quebra)

    assert pagina.roteamento[1]["texto"] == "25.♖xc7! B]ack"


def test_o_registro_da_faixa_volta_em_coordenadas_da_pagina():
    import numpy as np
    img = np.full((400, 600), 255, dtype=np.uint8)
    linha = [BoxEntry("", 100, 200, 110, 230), BoxEntry("", 120, 200, 130, 230)]
    margem = livro.MARGEM_DA_FAIXA

    def ler(faixa):
        # Uma linha curta e uma mais larga: fica a mais larga.
        return [("x", 0.5, (margem, margem, margem + 4, margem + 10), ()),
                ("ab cd", 0.9, (margem, margem, margem + 30, margem + 30),
                 (("ab", 0.9, (margem, margem, margem + 10, margem + 30)),
                  ("cd", 0.8, (margem + 20, margem, margem + 30, margem + 30))))]

    texto, conf, detalhes = livro._registro_da_faixa(img, linha, ler)

    # A faixa começa `FOLGA_DA_FAIXA_EM_LARGURAS` boxes medianos antes do
    # primeiro box (10 px de largura mediana), mais a margem.
    folga = int(10 * livro.FOLGA_DA_FAIXA_EM_LARGURAS)
    assert (texto, conf) == ("ab cd", 0.9)
    assert detalhes == (("ab", 0.9, (100 - folga, 200, 110 - folga, 230)),
                        ("cd", 0.8, (120 - folga, 200, 130 - folga, 230)))
    assert livro._registro_da_faixa(img, linha, lambda faixa: []) is None


def test_o_agrupador_do_tesseract_junta_as_palavras_da_mesma_linha():
    from core.services.ocr_service import OCRService
    dados = {
        "text": ["", "Amazingly", "Gashimov", "", "missed", "25.g4?"],
        "conf": ["-1", "93", "92", "-1", "96", "73"],
        "left": [0, 100, 200, 0, 100, 180],
        "top": [0, 50, 50, 0, 90, 92],
        "width": [10, 90, 80, 10, 60, 50],
        "height": [10, 20, 20, 10, 20, 18],
        "block_num": [1, 1, 1, 1, 1, 1],
        "par_num": [1, 1, 1, 1, 1, 1],
        "line_num": [1, 1, 1, 2, 2, 2],
    }

    linhas = OCRService._agrupar_dados_do_tesseract(dados)

    assert [linha[0] for linha in linhas] == ["Amazingly Gashimov", "missed 25.g4?"]
    assert linhas[0][1] == pytest.approx(0.925)
    assert linhas[0][2] == (100, 50, 280, 70)
    assert linhas[1][3] == (("missed", 0.96, (100, 90, 160, 110)),
                            ("25.g4?", 0.73, (180, 92, 230, 110)))


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


# ----------------------------------------------------------------------
# A segunda página (Yusupov, Chess Evolution 1, p. 34): número partido,
# cabeçalho em negativo e as lacunas do lance
# ----------------------------------------------------------------------

@pytest.mark.parametrize("antes, depois", [
    ("for: 1 .NUMf6! Qe7", "for: 1.NUMf6! Qe7"),
    ("If 1 ...Qxe2 then", "If 1...Qxe2 then"),
    ("Ke8 1 1.Qg7+-", "Ke8 11.Qg7+-"),
    ("get 1 point", "get 1 point"),
    ("Gibraltar 201 2 .", "Gibraltar 201 2 ."),
    ("move 40 . then", "move 40 . then"),
])
def test_o_numero_de_lance_partido_do_lance_e_colado(antes, depois):
    # O `1` em negrito do Chess Evolution 1 tem avanço largo, e o vão até o
    # ponto passa da régua do espaço. Os quatro vetores encolhem juntos.
    antes = antes.replace("NUM", "\u2658")
    depois = depois.replace("NUM", "\u2658")
    pesos = [float(i) for i in range(len(antes))]
    texto, novos_pesos, lacunas, caixas = livro._colar_numero_de_lance(
        antes, pesos, list(pesos), list(range(len(antes))))
    assert texto == depois
    assert len(novos_pesos) == len(lacunas) == len(caixas) == len(texto)
    if texto != antes:
        # O que saiu foi só o espaço; o resto continua alinhado ao texto.
        for indice, char in enumerate(texto):
            assert antes[caixas[indice]] == char


def test_o_alinhamento_do_lance_trata_figurina_e_lacuna_como_curinga():
    # O Tesseract escreve a figurina como uma ou duas letras, e a lacuna é o
    # que se quer ler dele.
    assert livro._alinhar_lance(list("3.\u2655h4+") + ["\0"], "3.Wfh4+\u2014") == ["\u2014"]
    assert livro._alinhar_lance(list("1...") + ["\0"] + list("f4"), "1...exf4") == ["ex"]
    # A palavra que não é este lance não alinha: mais de um quinto de edições.
    assert livro._alinhar_lance(list("3.\u2655h4+") + ["\0"], "Amazingly") is None


def _linha_com_lacuna(texto: str, derrubado: str, posicao: int):
    """Boxes lado a lado para `texto`, mais um box derrubado (sem caractere)
    inserido na posição `posicao` da linha. Devolve (boxes, caixas)."""
    boxes, caixas = [], []
    x = 100
    indice_box = 0
    for k, c in enumerate(texto):
        if k == posicao:
            boxes.append(BoxEntry("", x, 200, x + 10, 230))     # o derrubado
            x += 12
            indice_box += 1
        boxes.append(BoxEntry("", x, 200, x + 10, 230))
        caixas.append(indice_box)
        indice_box += 1
        x += 12
    if posicao >= len(texto):
        boxes.append(BoxEntry("", x, 200, x + 10, 230))
    return boxes, caixas


def test_a_lacuna_do_lance_e_preenchida_pelo_motor():
    # `+\u2013`: o traço a 0,40 caiu; o box dele encosta no `+`, e o Tesseract
    # leu `3.Wfh4+\u2014`. Entra como o traço da cadeia.
    boxes, caixas = _linha_com_lacuna("3.\u2655h4+", "\u2013", posicao=6)
    detalhes = (("3.Wfh4+\u2014", 0.3, (100, 200, 200, 230)),)
    texto, contas = livro._fundir_por_palavra("3.\u2655h4+", caixas, boxes, detalhes,
                                              so_lacunas=True)
    assert texto == "3.\u2655h4+\u2013"
    assert contas["lacunas_preenchidas"] == 1

    # `exf4`: a ligadura `\u2657x` a 0,43 caiu no meio; o Tesseract leu `1...exf4`.
    boxes, caixas = _linha_com_lacuna("1...f4", "ex", posicao=4)
    detalhes = (("1...exf4", 0.6, (100, 200, 200, 230)),)
    texto, _contas = livro._fundir_por_palavra("1...f4", caixas, boxes, detalhes,
                                               so_lacunas=True)
    assert texto == "1...exf4"


def test_a_lacuna_nao_recebe_lixo_nem_desfaz_a_forma_do_lance():
    boxes, caixas = _linha_com_lacuna("26...g16", "E", posicao=7)
    # O motor leu `\u00a2xh6`: o `h` cabe no alfabeto, mas `26...g1h6` não é lance.
    detalhes = (("26...\u00a2xh6", 0.4, (100, 200, 200, 230)),)
    texto, contas = livro._fundir_por_palavra("26...g16", caixas, boxes, detalhes,
                                              so_lacunas=True)
    assert texto == "26...g16"
    assert contas["lacunas_preenchidas"] == 0
    # E a palavra fraca de prosa continua fora, mesmo com `so_lacunas`.
    boxes, caixas = _linha_de_boxes("B]ack")
    detalhes = (("Black", 0.95, (100, 200, 150, 230)),)
    texto, _contas = livro._fundir_por_palavra("B]ack", caixas, boxes, detalhes,
                                               so_lacunas=True)
    assert texto == "B]ack"


def test_a_linha_so_de_lances_com_box_derrubado_pede_a_lacuna_ao_motor(monkeypatch):
    # A terceira linha da página sintética é só notação; aqui ela perde um
    # box (o traço de `+\u2013`), e o registro da página traz o lance inteiro.
    chamadas = []
    ancoras = ("Amaz1ngly m1ssed", "25.\u2656xc7! B]ack", "28.\u2656xf7+ \u2654e6")

    def falso(img, linha, classificar, conf_minima, coletor=None, pagina=0,
              marcador_glifo=None, marcador_confianca=None):
        texto = ancoras[len(chamadas)]
        chamadas.append(texto)
        n = len(linha)
        if texto.startswith("28."):
            # O último box da linha é o derrubado: nenhum caractere aponta para ele.
            caixas = [-1 if c == " " else min(n - 2, i * (n - 1) // len(texto))
                      for i, c in enumerate(texto)]
            return texto, 1, [None] * len(texto), [None] * len(texto), caixas
        caixas = [-1 if c == " " else min(n - 1, i * n // len(texto))
                  for i, c in enumerate(texto)]
        return texto, 0, [None] * len(texto), [None] * len(texto), caixas

    classificar = _classificador()
    monkeypatch.setattr(livro, "_texto_da_linha", falso)
    palavras = (["Amazingly", "missed"], ["25.Exc7!", "Black"],
                ["28.Bxf7t", "He6+\u2014"])
    doc = _pagina(("aaaaaaaaaaaaaa", "bbbbbbbbbbbbbb", "cccccccccccccc"))
    try:
        pagina = livro.extrair_pagina(
            doc[0], classificar, dpi=150,
            ler_pagina=_ler_pagina_roteirizado(palavras, classificar))
    finally:
        doc.close()

    registro = pagina.roteamento[2]
    assert registro["dominio"] == "notation"
    assert registro["fonte"] == "lacunas"
    assert registro["texto"] == "28.\u2656xf7+ \u2654e6+\u2013"
    assert registro["lacunas_preenchidas"] == 1


def test_a_faixa_em_negativo_e_invertida_so_no_miolo():
    import numpy as np
    img = np.full((400, 600), 255, dtype=np.uint8)
    img[195:235, 90:140] = 0                         # a tarja preta
    img[205:225, 100:130] = 255                      # as letras brancas
    linha = [BoxEntry("", 100, 200, 110, 230, negativo=True),
             BoxEntry("", 120, 200, 130, 230, negativo=True)]
    recebidas = []

    def ler(faixa):
        recebidas.append(faixa.copy())
        return [("ab", 0.9, (8, 8, 38, 38), (("ab", 0.9, (8, 8, 38, 38)),))]

    livro._registro_da_faixa(img, linha, ler)
    faixa = recebidas[0]
    margem = livro.MARGEM_DA_FAIXA
    assert faixa[:margem].min() == 255, "a margem tem de continuar branca"
    miolo = faixa[margem:-margem, margem:-margem]
    # A tarja não ganha a folga dos lados: a faixa é a dos boxes, 100–130, e
    # o miolo inteiro é invertido.
    assert miolo.shape[1] == 30, "a tarja em negativo não tem folga"
    assert miolo[0, 0] == 255, "o fundo da tarja virou branco"
    assert miolo[10, 5] == 0, "as letras viraram pretas"
    assert img[200, 100] == 0, "a imagem da página não pode ser alterada"


def test_a_faixa_sobre_trama_e_limpa_para_o_motor():
    import numpy as np
    rng = np.random.default_rng(7)
    img = np.full((400, 600), 255, dtype=np.uint8)
    # Uma nuvem de pontos escuros de 1 px (a trama) em volta de duas letras.
    pontos = rng.random((60, 200)) < 0.08
    img[190:250, 80:280][pontos] = 40
    img[205:225, 100:110] = 0                        # a letra
    img[205:225, 120:130] = 0
    linha = [BoxEntry("", 100, 200, 110, 230), BoxEntry("", 120, 200, 130, 230)]
    recebidas = []

    def ler(faixa):
        recebidas.append(faixa.copy())
        return [("ab", 0.9, (8, 8, 38, 38), (("ab", 0.9, (8, 8, 38, 38)),))]

    livro._registro_da_faixa(img, linha, ler)
    faixa = recebidas[0]
    margem = livro.MARGEM_DA_FAIXA
    miolo = faixa[margem:-margem, margem:-margem]
    assert (miolo == 40).sum() == 0, "a trama tinha de sair"
    assert miolo.min() == 0, "as letras tinham de ficar"
    assert set(np.unique(miolo)) <= {0, 255}, "a faixa limpa é binária"
    # Sem trama, a faixa fica como está — cinza e tudo.
    limpa = np.full((400, 600), 255, dtype=np.uint8)
    limpa[205:225, 100:110] = 30
    limpa[205:225, 120:130] = 30
    recebidas.clear()
    livro._registro_da_faixa(limpa, linha, ler)
    assert recebidas[0].min() == 30, "sem trama a faixa não é binarizada"


@pytest.mark.parametrize("antes, depois", [
    ("l ...Ng4! is", "1...Ng4! is"),
    ("10.c6 Qxf4 1 l .Nxf4+)", "10.c6 Qxf4 11.Nxf4+)"),
    ("I like it", "I like it"),
    ("all . the", "all . the"),
])
def test_o_l_solto_na_frente_do_lance_e_o_um(antes, depois):
    # A cadeia lê o `1` do Chess Evolution 1 como `l`; na frente de reticências
    # e lance ele é número, e sai como `1`. Cola em dois passos: `1 l .`.
    texto, pesos, lacunas, caixas = livro._colar_numero_de_lance(
        antes, [None] * len(antes), [None] * len(antes), list(range(len(antes))))
    assert texto == depois
    assert len(pesos) == len(lacunas) == len(caixas) == len(texto)
