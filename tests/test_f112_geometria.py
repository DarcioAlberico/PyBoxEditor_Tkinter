"""
F112 — a geometria decide a caixa: a poda de Baird, que não pede rótulo.

A rede lê cada recorte esticado em 32×32 e não tem como separar `s` de `S`; a
linha tem. Cada leitura propõe uma altura de x, a linha vota a dela, e a leitura
que não cabe no corpo votado é trocada pela candidata **do mesmo desenho** que
cabe (`core.geometria_da_linha`).

As linhas destes testes são desenhadas: cada glifo é um retângulo de tinta com o
topo e o pé onde a tipografia os põe, numa base e numa altura de x conhecidas.
A tabela das classes também é montada aqui, para o teste dizer o que a poda faz
e não o que a tabela gravada mediu — essa tem um teste próprio, no fim.

Rodar sem pytest:      python tests/test_f112_geometria.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

from core import geometria_da_linha as gl
from core import livro
from core.box_model import BoxEntry

BASE = 100
ALTURA_DE_X = 20


def _classe(topo, base=0.0, desvio_topo=0.0, desvio_base=0.0, n=500):
    return gl.Classe(topo, desvio_topo, base, desvio_base, n)


#: Uma tabela como a medida, só com o que os testes usam.
TABELA = {
    **{c: _classe(1.0) for c in "aemnrsuocxvwz"},
    **{c: _classe(1.5, desvio_topo=0.05) for c in "hdtbfk"},
    "i": _classe(1.0),
    "l": _classe(1.53, desvio_topo=0.18),
    "1": _classe(1.39, desvio_topo=0.09),
    "I": _classe(1.42, desvio_topo=0.10, n=52),
    "S": _classe(1.42, desvio_topo=0.15, n=41),
    "C": _classe(1.40, desvio_topo=0.07, n=51),
    "O": _classe(1.40, desvio_topo=0.06, n=29),
    "W": _classe(1.45, desvio_topo=0.04, n=51),
    "0": _classe(1.40, desvio_topo=0.11, n=133),
    "p": _classe(1.0, base=-0.45, desvio_base=0.11, n=470),
    "P": _classe(1.41, desvio_topo=0.28, n=31),
    ",": _classe(0.25, base=-0.25, desvio_topo=0.06, desvio_base=0.02, n=186),
    "'": _classe(1.58, base=1.1, desvio_topo=0.19, desvio_base=0.09, n=51),
    ".": _classe(0.27, base=0.04, desvio_topo=0.03, desvio_base=0.05, n=2922),
    ")": _classe(1.45, base=-0.3, desvio_topo=0.07, n=60),
    "J": _classe(1.40, desvio_topo=0.06, n=30),
}

#: Onde o corpo de cada classe fica, para desenhar — `(topo, pé)` em alturas
#: de x acima da base.
CORPO = {c: (e.topo, e.base) for c, e in TABELA.items()}


def _linha(glifos, vao=4, largura=12):
    """
    `(imagem, caixas)` de uma linha desenhada.

    `glifos` é uma sequência de `(corpo, espaço_antes)` — o corpo é a chave de
    `CORPO` cujo topo e pé o glifo tem (o que ele **é**, e não o que se lê), e o
    espaço é o vão extra antes dele, em pixels. Um `"i"` ganha o pingo destacado
    acima da haste, como o `i` impresso.
    """
    x = 10
    caixas, retangulos = [], []
    for corpo, espaco in glifos:
        x += espaco
        topo, pe = CORPO[corpo]
        y1 = int(round(BASE - topo * ALTURA_DE_X))
        y2 = int(round(BASE - pe * ALTURA_DE_X))
        caixa_y1 = y1
        if corpo == "i":
            caixa_y1 = int(round(BASE - 1.45 * ALTURA_DE_X))
        caixas.append(BoxEntry("", x, caixa_y1, x + largura, y2))
        retangulos.append((x, y1, x + largura, y2, corpo == "i"))
        x += largura + vao
    img = np.full((160, x + 20), 255, np.uint8)
    for x1, y1, x2, y2, pingo in retangulos:
        img[y1:y2, x1 + 2:x2 - 2] = 0
        if pingo:
            topo_do_pingo = int(round(BASE - 1.45 * ALTURA_DE_X))
            img[topo_do_pingo:topo_do_pingo + 3, x1 + 4:x2 - 4] = 0
    return img, caixas


def _recortes(img, caixas):
    return [img[b.y1:b.y2, b.x1:b.x2] for b in caixas]


class _Candidatas:
    """O top-k por índice do box, e quantas vezes cada um foi pedido."""

    def __init__(self, recortes, por_indice):
        self._indice = {id(r): i for i, r in enumerate(recortes)}
        self.por_indice = por_indice
        self.pedidos = []

    def __call__(self, recorte, k):
        i = self._indice[id(recorte)]
        self.pedidos.append(i)
        return self.por_indice.get(i, [])


def _podar(glifos, leituras, por_indice, **kw):
    img, caixas = _linha([(g, 0) for g in glifos])
    recortes = _recortes(img, caixas)
    candidatas = _Candidatas(recortes, por_indice)
    kw.setdefault("tabela", TABELA)
    trocas = gl.podar(caixas, recortes, leituras, candidatas, **kw)
    return trocas, candidatas


# ----------------------------------------------------------------------
# A medida do corpo
# ----------------------------------------------------------------------

def test_o_corpo_deixa_o_pingo_destacado_de_fora():
    """
    O `i` tem o topo da **haste** na altura de x. É o que separa o `i` do `l`,
    e o que a F19 media como impossível com a caixa inteira (d' = 0,01).
    """
    img, caixas = _linha([("i", 0)])
    glifo = gl.medir(_recortes(img, caixas)[0], caixas[0])
    assert glifo.topo == BASE - ALTURA_DE_X
    assert glifo.base == BASE


def test_a_caixa_frouxa_e_aparada_a_tinta():
    """
    A caixa que a segmentação esticou (o pingo do vizinho a puxou para cima) é
    medida pela tinta que tem dentro — era a causa das quebras reais `w`→`W`.
    """
    img, caixas = _linha([("s", 0)])
    caixa = BoxEntry("", caixas[0].x1, caixas[0].y1 - 9, caixas[0].x2, caixas[0].y2)
    glifo = gl.medir(img[caixa.y1:caixa.y2, caixa.x1:caixa.x2], caixa)
    assert glifo.topo == BASE - ALTURA_DE_X


def test_sem_contraste_ou_girado_nao_ha_medida():
    caixa = BoxEntry("", 0, 0, 10, 10)
    assert gl.medir(np.full((10, 10), 200, np.uint8), caixa) is None
    girada = BoxEntry("", 0, 0, 10, 10, angulo=90)
    tinta = np.zeros((10, 10), np.uint8)
    assert gl.medir(tinta, girada) is None


# ----------------------------------------------------------------------
# A linha
# ----------------------------------------------------------------------

def test_a_reta_robusta_acha_a_inclinacao_e_ignora_o_ponto_fora():
    xs = [0, 100, 200, 300, 400, 500]
    ys = [100 + 0.01 * x for x in xs]
    ys[2] += 15
    a, b = gl.reta_robusta(xs, ys)
    assert b == pytest.approx(0.01, abs=1e-6)
    assert a == pytest.approx(100, abs=0.5)


def test_a_inclinacao_absurda_e_cortada():
    a, b = gl.reta_robusta([0, 10, 20, 30], [0, 5, 10, 15])
    assert b == gl.INCLINACAO_MAXIMA


def test_a_linha_vota_a_altura_de_x_mesmo_sem_ascendente():
    """
    A régua da F19 era a faixa dos boxes, que encolhe na linha só de altura de
    x. A votada não: cada `s` e cada `o` dizem 20, e o `S` lido errado é voto
    vencido — e vale um quarto, por ser de grupo.
    """
    img, caixas = _linha([(c, 0) for c in "sssoS"[:4]] + [("s", 0)])
    glifos = [gl.medir(r, b) for r, b in zip(_recortes(img, caixas), caixas)]
    leituras = [("s", 0.9), ("s", 0.9), ("s", 0.9), ("o", 0.9), ("S", 0.9)]
    linha = gl.ajustar(glifos, leituras, TABELA)
    assert linha.altura_de_x == pytest.approx(ALTURA_DE_X)
    assert linha.base_em(50) == pytest.approx(BASE)


def test_linha_com_poucos_votos_nao_tem_corpo():
    img, caixas = _linha([("s", 0), ("o", 0), ("S", 0)])
    glifos = [gl.medir(r, b) for r, b in zip(_recortes(img, caixas), caixas)]
    assert gl.ajustar(glifos, [("s", .9), ("o", .9), ("S", .9)], TABELA) is None


# ----------------------------------------------------------------------
# A poda
# ----------------------------------------------------------------------

def test_o_o_lido_maiusculo_volta_a_minusculo_com_a_confianca_do_desenho():
    """
    O caso da F107 (`o` lido `O`, 8 em 122 erros no Seirawan): a rede dá quase
    tudo ao `O` e o recorte é o mesmo desenho. A troca sai com a massa do grupo
    — sem isso o `o` de 0,08 seria derrubado pelo piso do livro e a troca
    viraria buraco.
    """
    leituras = [("c", .95), ("O", .9), ("s", .95), ("a", .95)]
    trocas, candidatas = _podar("cosa", leituras,
                                {1: [("O", .9), ("o", .08), ("Q", .01)]})
    assert trocas == {1: ("o", pytest.approx(.98))}
    assert candidatas.pedidos == [1], "só o box que não cabe consulta a rede"


def test_o_s_lido_maiusculo_fica_porque_a_tabela_mistura_fontes():
    """
    **O limite medido, e o teste afirma isso de propósito.** A caixa alta do
    `S` sobe 1,32 alturas de x no Darcy Lima e 1,67 no Attacking Manual — é a
    fonte —, e a tabela de todos os livros junta as duas: desvio de 0,15, e o
    `s` lido `S` fica a 2,8 desvios, abaixo do veto. A tolerância única pegava
    esse caso e quebrava o `l` de ascendente curto (F112 no ROADMAP). Quem
    fizer a tabela por livro muda este teste.
    """
    leituras = [("c", .95), ("a", .95), ("S", .9), ("a", .95)]
    trocas, _c = _podar("casa", leituras, {2: [("S", .9), ("s", .08)]})
    assert trocas == {}


def test_a_maiuscula_de_verdade_fica():
    leituras = [("S", .9), ("a", .95), ("n", .95), ("t", .95), ("o", .95)]
    trocas, candidatas = _podar("Santo", leituras, {})
    assert trocas == {}
    assert candidatas.pedidos == []


def test_so_troca_dentro_do_grupo_de_mesmo_desenho():
    """
    Solta, a poda trocava `)` por `J` quando a caixa estava baixa: a candidata
    que cabia era outro desenho. Fora de grupo a leitura nem é examinada.
    """
    leituras = [("a", .95), ("s", .9), ("a", .95), ("s", .95), ("a", .95)]
    trocas, _c = _podar("aSasa", leituras,
                        {1: [("s", .9), ("J", .05), ("S", .04)]})
    assert trocas == {1: ("S", pytest.approx(.94))}
    trocas, candidatas = _podar("asasa", [("a", .95), (")", .9), ("a", .95),
                                          ("s", .95), ("a", .95)],
                                {1: [(")", .9), ("J", .05)]})
    assert trocas == {} and candidatas.pedidos == []


def test_sem_substituta_que_caiba_a_leitura_fica():
    leituras = [("a", .95), ("S", .9), ("a", .95), ("s", .95), ("a", .95)]
    trocas, _c = _podar("asasa", leituras, {1: [("S", .9), ("5", .05)]})
    assert trocas == {}


def test_o_i_lido_como_l_volta_a_ser_i():
    """
    O `l` tem ascendente; a haste que para na altura de x é `i`. O corpo do
    `i` é a haste (o pingo destacado fica de fora), e ela para um pouco abaixo
    da altura que a linha vota — as redondas (`o`, `e`, `s`) a puxam para cima
    com o excesso delas. É nessa folga que os 23 `l`→`i` medidos caíram; com
    a haste exatamente na altura votada, o `l` (desvio 0,18) ainda cabe.
    """
    CORPO["i_baixo"] = (0.93, 0.0)
    try:
        img, caixas = _linha([("n", 0), ("i_baixo", 0), ("n", 0), ("e", 0)])
    finally:
        del CORPO["i_baixo"]
    recortes = _recortes(img, caixas)
    candidatas = _Candidatas(recortes, {1: [("l", .9), ("I", .05), ("i", .03)]})
    trocas = gl.podar(caixas, recortes,
                      [("n", .95), ("l", .9), ("n", .95), ("e", .95)],
                      candidatas, tabela=TABELA)
    assert trocas == {1: ("i", pytest.approx(.98))}


def test_o_zero_so_vira_o_dentro_de_palavra():
    """
    `C0nsult0ria` sai `Consultoria`; o algarismo de texto, que tem o corpo na
    altura de x, **não** vira letra em `10.` — sem esta trava, `1.e4` sairia
    `i.e4` num livro de algarismos de texto.
    """
    leituras = [("c", .95), ("0", .9), ("n", .95), ("s", .95)]
    trocas, _c = _podar("cons", leituras, {1: [("0", .9), ("o", .06)]})
    assert trocas == {1: ("o", pytest.approx(.96))}

    img, caixas = _linha([("1", 0), ("o", 0), (".", 0), ("e", 12), ("a", 0),
                          ("n", 0)])
    recortes = _recortes(img, caixas)
    leituras = [("1", .95), ("0", .9), (".", .95), ("e", .95), ("a", .95),
                ("n", .95)]
    candidatas = _Candidatas(recortes, {1: [("0", .9), ("o", .06)]})
    trocas = gl.podar(caixas, recortes, leituras, candidatas, tabela=TABELA,
                      limiar_de_espaco=8)
    assert trocas == {}, "o `0` entre algarismos é algarismo, mesmo baixo"


def test_entre_algarismos_o_corpo_de_caixa_alta_e_zero():
    """`1o.` com o `o` na altura de caixa alta: `O` e `0` cabem, e o `1` decide."""
    img, caixas = _linha([("1", 0), ("0", 0), (".", 0), ("a", 12), ("n", 0),
                          ("e", 0), ("s", 0)])
    recortes = _recortes(img, caixas)
    leituras = [("1", .95), ("o", .9), (".", .95), ("a", .95), ("n", .95),
                ("e", .95), ("s", .95)]
    candidatas = _Candidatas(recortes, {1: [("o", .9), ("O", .05), ("0", .04)]})
    trocas = gl.podar(caixas, recortes, leituras, candidatas, tabela=TABELA,
                      limiar_de_espaco=8)
    assert trocas == {1: ("0", pytest.approx(.99))}


def test_a_virgula_e_o_apostrofo_sao_a_mesma_marca_em_alturas_diferentes():
    leituras = [("o", .95), ("n", .95), ("e", .95), (",", .9), ("s", .95)]
    trocas, _c = _podar("one's", leituras, {3: [(",", .9), ("'", .08)]})
    assert trocas == {3: ("'", pytest.approx(.98))}


def test_o_ponto_alto_nao_vira_apostrofo():
    """
    O ponto na altura do pingo costuma ser o pingo de um `i` partido (a família
    A da F109): trocá-lo por `'` não conserta nada, e os dois não são grupo.
    """
    leituras = [("o", .95), ("n", .95), ("e", .95), (".", .9), ("s", .95)]
    trocas, _c = _podar("one's", leituras, {3: [(".", .9), ("'", .08)]})
    assert trocas == {}


def test_a_leitura_fraca_que_so_ela_cabe_e_confirmada():
    """
    O `o` repartido entre `o`, `0` e `O` que nenhum alcançava 0,5 (F107): a
    linha diz que só o `o` cabe, e ele sai com a massa do grupo em vez de cair
    pelo piso de confiança.
    """
    leituras = [("c", .95), ("o", .45), ("s", .95), ("a", .95)]
    trocas, _c = _podar("cosa", leituras,
                        {1: [("o", .45), ("0", .35), ("O", .15)]},
                        limiar_de_confirmacao=0.5)
    assert trocas == {1: ("o", pytest.approx(.95))}
    trocas, candidatas = _podar("cosa", leituras,
                                {1: [("o", .45), ("0", .35), ("O", .15)]})
    assert trocas == {} and candidatas.pedidos == [], \
        "sem o limiar, a leitura que cabe nem é examinada"


def test_sem_tabela_ou_sem_linha_nada_muda():
    leituras = [("c", .95), ("a", .95), ("S", .9), ("a", .95)]
    trocas, candidatas = _podar("casa", leituras, {2: [("s", .9)]}, tabela={})
    assert trocas == {} and candidatas.pedidos == []
    trocas, _c = _podar("csa", leituras[1:], {1: [("s", .9)]})
    assert trocas == {}


# ----------------------------------------------------------------------
# No livro
# ----------------------------------------------------------------------

def _ler(leituras):
    it = iter(leituras)
    return lambda _recorte: next(it)


def test_o_livro_poda_a_linha_antes_de_montar_o_texto(monkeypatch):
    """
    `_texto_da_linha` classifica a linha inteira, poda, e só então monta: o
    coletor e o piso de confiança recebem a leitura podada.
    """
    monkeypatch.setattr(gl, "carregar_tabela", lambda *a, **k: TABELA)
    img, caixas = _linha([(c, 0) for c in "cosa"])
    coletados = []
    candidatas = lambda _recorte, _k: [("O", .9), ("o", .08)]
    texto, fracos, pesos, _lac, cx = livro._texto_da_linha(
        img, caixas, _ler([("c", .95), ("O", .9), ("s", .95), ("a", .95)]),
        0.5, coletor=lambda r, c, conf, p: coletados.append(c),
        candidatas=candidatas)
    assert texto == "cosa"
    assert coletados == list("cosa")
    assert len(pesos) == len(texto)


def test_sem_candidatas_o_livro_le_como_antes(monkeypatch):
    monkeypatch.setattr(gl, "carregar_tabela", lambda *a, **k: TABELA)
    img, caixas = _linha([(c, 0) for c in "cosa"])
    texto, *_ = livro._texto_da_linha(
        img, caixas, _ler([("c", .95), ("O", .9), ("s", .95), ("a", .95)]), 0.5)
    assert texto == "cOsa"


def test_o_piso_de_confianca_nao_apaga_a_troca(monkeypatch):
    """A troca leva a massa do grupo, e passa pelo piso que a substituta sozinha não passaria."""
    monkeypatch.setattr(gl, "carregar_tabela", lambda *a, **k: TABELA)
    img, caixas = _linha([(c, 0) for c in "cosa"])
    texto, fracos, *_ = livro._texto_da_linha(
        img, caixas, _ler([("c", .95), ("O", .6), ("s", .95), ("a", .95)]),
        0.5, candidatas=lambda _r, _k: [("O", .6), ("o", .01)])
    assert texto == "cosa" and fracos == 0


def test_extrair_liga_a_poda_so_quando_pedido():
    import inspect
    for funcao in (livro.extrair, livro.extrair_pagina):
        parametro = inspect.signature(funcao).parameters["candidatas"]
        assert parametro.default is None


def test_a_exportacao_pela_janela_liga_a_poda(monkeypatch, tmp_path):
    """
    A opção não vale nada se parar antes da extração: a exportação de livro
    passa o top-k da rede, e o `livro.extrair` o recebe.
    """
    from tests.test_f26_livro import _App, _pdf_de_uma_pagina

    recebido = {}

    def falsa(input_pdf, classificar, **kw):
        recebido.update(kw)
        return []

    monkeypatch.setattr(livro, "extrair", falsa)
    entrada = str(tmp_path / "livro.pdf")
    _pdf_de_uma_pagina(entrada)
    with _App(entrada, str(tmp_path / "a.epub")) as app:
        app.rodar()
        assert not app.erros, app.erros
        assert recebido["candidatas"] is app.win.learning_service.candidatas


def test_o_documento_editorial_passa_a_poda_ao_leitor():
    from core.editorial_legacy import OpcoesDeLeitura

    def candidatas(recorte, k):
        return []

    assert OpcoesDeLeitura(candidatas=candidatas).kwargs()["candidatas"] is candidatas
    assert OpcoesDeLeitura().kwargs()["candidatas"] is None


# ----------------------------------------------------------------------
# A tabela gravada
# ----------------------------------------------------------------------

def test_a_tabela_gravada_mede_o_que_a_tipografia_diz():
    """
    A de `core/dados`, gerada por `medir_geometria.py --gravar`: a minúscula de
    altura de x tem o topo em 1, a maiúscula e o algarismo acima de 1,3, a
    vírgula desce abaixo da base e o apóstrofo mora no alto.
    """
    tabela = gl.carregar_tabela()
    assert tabela, "a tabela não está em core/dados"
    for c in "acemnorsuvwxz":
        assert tabela[c].topo == pytest.approx(1.0, abs=0.05), c
    for c in "SOCW0":
        assert tabela[c].topo > 1.3, c
    assert tabela[","].base < -0.1
    assert tabela["'"].base > 0.8
    assert tabela["p"].base < -0.3
    assert tabela["i"].topo == pytest.approx(1.0, abs=0.05), \
        "o corpo do `i` é a haste, sem o pingo"
    # A maiúscula rara (`U`, `X`, `Z`) não tem ocorrências para ter medida, e
    # classe sem medida não tem opinião: nem é podada, nem substitui.
    for membro in "cCoO0sSvVwWpP9gq,'.il1I":
        assert membro in tabela, f"sem medida de {membro!r}"


def test_a_tabela_vai_e_volta_pelo_json(tmp_path):
    caminho = tmp_path / "t.json"
    caminho.write_text(json.dumps(gl.dados_da_tabela(TABELA, nota="x")),
                       encoding="utf-8")
    assert gl.carregar_tabela(str(caminho)) == {
        c: gl.Classe(round(e.topo, 4), round(e.desvio_topo, 4),
                     round(e.base, 4), round(e.desvio_base, 4), e.n)
        for c, e in TABELA.items()}
    assert gl.carregar_tabela(str(tmp_path / "nao-existe.json")) == {}


def test_estimar_tabela_recupera_a_geometria_desenhada():
    img, caixas = _linha([(c, 0) for c in "casaSp,"])
    glifos = [gl.medir(r, b) for r, b in zip(_recortes(img, caixas), caixas)]
    tabela = gl.estimar_tabela([list(zip(glifos, "casaSp,"))] * 8, minimo=8)
    assert tabela["s"].topo == pytest.approx(1.0)
    assert tabela["S"].topo == pytest.approx(1.42, abs=0.05)
    assert tabela["p"].base == pytest.approx(-0.45, abs=0.05)
    assert tabela[","].base == pytest.approx(-0.25, abs=0.05)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
