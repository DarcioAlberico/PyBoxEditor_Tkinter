"""
F115 — o caractere derrubado abria espaço, e o reparo não via a palavra inteira.

Dois defeitos do caminho do livro, e eles se somam no mesmo lugar: a palavra.

**O primeiro é o buraco.** `_texto_da_linha` derruba o caractere de confiança
baixa (`CONF_MINIMA`) e a régua do espaço não sabia disso — ela corria entre
caixas vizinhas e escrevia um espaço por vão que passasse do limiar. Um glifo
derrubado entre dois vãos largos passava por dois, e escrevia **dois** espaços:
`kni  ht` por `knight`. Medido, 1.232 no DOCX do Yusupov e 318 no EPUB do
Kasparov.

**O que este conserto não faz, e é preciso dizer:** ele não devolve `kniht`. Os
vãos em volta do buraco continuam sendo os vãos que a página tem, e quando eles
são largos de verdade — que é o caso da linha degradada onde o defeito aparece —
há separação ali. O que se conserta é escrever **uma** vez o espaço que existe,
em vez de duas. Suprimi-lo por inteiro colaria `White ✝ moves` em
`Whitemoves`, e o último teste desta seção é quem trava isso.

**O segundo é o lugar do reparo.** A F108 ligou `arrumar_caixa` na linha, e o
comentário dela dizia na letra que a palavra partida pelo hífen ficava de fora.
`lexico.juntar_hifenizadas` existe desde a F9.1, com teste e com medição — a
F104 mediu 490 junções no Nunn — e **não tinha chamador em produção**. Subir os
dois reparos para o parágrafo é o que os põe sobre a palavra que o livro
imprimiu, e não sobre o pedaço que coube na linha.

Os testes de alinhamento são os que travam a F105: o vetor de espessuras anda
caractere a caractere com o texto, e uma junção tira dois caracteres do meio
dele.

Rodar sem pytest:      python tests/test_f115_buraco_e_hifen.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

from core import lexico, livro
from core.box_model import BoxEntry


def _lex(*palavras):
    return lexico.Lexico(palavras=set(palavras))


def _linha_de(texto, vaos):
    """
    Uma imagem e as caixas de uma linha, com o vão pedido entre cada par.

    `vaos` tem um valor por par de vizinhas, em pixels. As caixas têm 20 px de
    largura, então `limiar_de_espaco` cai no piso de 9 px enquanto os vãos não
    tiverem mediana própria — que é o caso destas linhas curtas.
    """
    largura, altura = 20, 24
    x = 10
    boxes = []
    for i in range(len(texto)):
        if i:
            x += vaos[i - 1]
        boxes.append(BoxEntry("", x, 8, x + largura, 8 + altura))
        x += largura
    img = np.full((40, x + 20), 255, np.uint8)
    for b in boxes:
        img[b.y1 + 2:b.y2 - 2, b.x1 + 2:b.x2 - 2] = 0
    return img, boxes


def _ler(leituras):
    """Um classificador que devolve `(char, confiança)` em ordem."""
    it = iter(leituras)
    return lambda _recorte: next(it)


# ----------------------------------------------------------------------
# O buraco
# ----------------------------------------------------------------------

def test_o_caractere_derrubado_nao_escreve_dois_espacos():
    """
    Era: o vão corria entre caixas vizinhas, e a do meio não tinha saído.

    Com dois vãos largos em volta de um glifo derrubado, os dois passavam do
    limiar e os dois escreviam. Medido no EPUB do Kasparov, 318 parágrafos com
    espaço duplo.
    """
    img, boxes = _linha_de("abc", [30, 30])
    texto, fracos, pesos = livro._texto_da_linha(
        img, boxes, _ler([("a", 0.9), ("b", 0.2), ("c", 0.9)]), 0.5)
    assert fracos == 1, "o `b` tinha de cair por confiança"
    assert texto == "a c", f"saiu {texto!r} — o espaço saiu duas vezes"
    assert len(pesos) == len(texto)


def test_o_buraco_no_meio_da_palavra_deixa_de_dobrar_o_espaco():
    """
    `knight` com o `g` fraco, na linha degradada em que o defeito aparece: os
    vãos em volta do buraco passam do limiar dos dois lados.

    Era `kni  ht` e passa a `kni ht`. **Não vira `kniht`**, e o teste afirma
    isso de propósito — ver o cabeçalho do arquivo.
    """
    img, boxes = _linha_de("knight", [2, 2, 12, 12, 2])
    leituras = [(c, 0.9 if c != "g" else 0.2) for c in "knight"]
    texto, fracos, pesos = livro._texto_da_linha(
        img, boxes, _ler(leituras), 0.5)
    assert fracos == 1
    assert texto == "kni ht", f"saiu {texto!r}"
    assert len(pesos) == len(texto)


def test_o_buraco_de_vao_estreito_nao_parte_a_palavra():
    """O outro lado: onde a página não tem vão, o buraco não inventa um."""
    img, boxes = _linha_de("knight", [2, 2, 2, 2, 2])
    leituras = [(c, 0.9 if c != "g" else 0.2) for c in "knight"]
    texto, _fracos, _pesos = livro._texto_da_linha(
        img, boxes, _ler(leituras), 0.5)
    assert texto == "kniht"


def test_o_derrubado_entre_duas_palavras_continua_separando():
    """
    O outro lado da mesma régua, e é ele que impede o conserto de colar tudo:
    o glifo derrubado que **era** uma palavra continua abrindo um espaço — um
    só. Sem isto, `White ✝ moves` sairia `Whitemoves`.
    """
    img, boxes = _linha_de("A_B", [40, 40])
    texto, _f, _p = livro._texto_da_linha(
        img, boxes, _ler([("A", 0.9), ("+", 0.1), ("B", 0.9)]), 0.5)
    assert texto == "A B"


def test_a_linha_sem_nada_derrubado_sai_como_antes():
    """A trava de regressão: onde não há buraco, a régua não mudou."""
    img, boxes = _linha_de("abcd", [2, 40, 2])
    texto, fracos, pesos = livro._texto_da_linha(
        img, boxes, _ler([(c, 0.9) for c in "abcd"]), 0.5)
    assert (texto, fracos) == ("ab cd", 0)
    assert len(pesos) == len(texto)


def test_o_vetor_de_espessuras_acompanha_o_buraco():
    """
    O que a F105 exige: um peso por caractere do texto, e `nan` no espaço.

    O caractere que não saiu não deixa peso — se deixasse, o negrito do resto da
    linha andaria uma casa.
    """
    img, boxes = _linha_de("abc", [30, 30])
    texto, _f, pesos = livro._texto_da_linha(
        img, boxes, _ler([("a", 0.9), ("b", 0.2), ("c", 0.9)]), 0.5)
    assert len(pesos) == len(texto) == 3
    assert pesos[1] is None, "o espaço tem de vir sem medida"
    assert pesos[0] is not None and pesos[2] is not None


# ----------------------------------------------------------------------
# O hífen, e o lugar do reparo
# ----------------------------------------------------------------------

def _linhas(*textos):
    return [livro.Linha(topo=20 * i, esquerda=0, altura=10, texto=t,
                        pesos=[0.1 * (i + 1)] * len(t))
            for i, t in enumerate(textos)]


def test_o_hifen_de_fim_de_linha_remonta_a_palavra():
    """
    Era: `com-` e `promised` chegavam ao arquivo como duas palavras, com o
    hífen no meio. A F104 mediu 490 destas no Nunn.
    """
    p = livro._paragrafo_de(_linhas("uma coisa com-", "promised e o resto"),
                            _lex("compromised", "uma", "coisa", "resto"))
    assert p.texto == "uma coisa compromised e o resto"


def test_a_juncao_so_acontece_quando_ela_forma_palavra():
    """
    O critério é o dicionário e não o hífen — `Xue-` + `Fierro` tem hífen de
    verdade, é nome próprio, e não junta. É a regra que a F9.1 mediu.
    """
    p = livro._paragrafo_de(_linhas("jogou contra Xue-", "Fierro em 2011"),
                            _lex("jogou", "contra", "fierro"))
    assert p.texto == "jogou contra Xue- Fierro em 2011"


def test_a_juncao_mantem_o_vetor_alinhado():
    """
    **É a trava da F105.** A junção tira dois caracteres do texto — o hífen e o
    espaço que separava as linhas —, e os dois têm de sair do vetor junto. Sem
    isto, `negrito.marcar` pula o parágrafo inteiro em silêncio.
    """
    linhas = _linhas("com-", "promised")
    p = livro._paragrafo_de(linhas, _lex("compromised"))
    assert p.texto == "compromised"
    assert len(p.pesos) == len(p.texto)
    # Os três primeiros vieram da primeira linha, o resto da segunda.
    assert p.pesos[0] == pytest.approx(0.1)
    assert p.pesos[3] == pytest.approx(0.2)


def test_a_pontuacao_da_direita_sobrevive_a_juncao():
    """A vírgula depois da palavra é da palavra, e continua nela."""
    p = livro._paragrafo_de(_linhas("em-", "barrassment, disse"),
                            _lex("embarrassment", "disse"))
    assert p.texto == "embarrassment, disse"


def test_a_caixa_se_arruma_na_palavra_que_o_hifen_partiu():
    """
    O que o reparo por linha **não podia** alcançar, e é a razão de ele ter
    subido: nenhuma das duas metades é palavra, então o portão de `conhece` não
    abria em nenhuma das duas linhas. Juntas, a palavra existe e a caixa cai.
    """
    p = livro._paragrafo_de(_linhas("o bi-", "Shop preto"),
                            _lex("bishop", "preto"))
    assert p.texto == "o bishop preto"


def test_o_paragrafo_sem_lexico_sai_como_as_linhas_o_escreveram():
    """`lex=None` é o padrão, e com ele nada é reparado."""
    p = livro._paragrafo_de(_linhas("com-", "promised"))
    assert p.texto == "com- promised"
    assert len(p.pesos) == len(p.texto)


def test_o_lexico_desce_pelo_agrupador():
    """
    O caminho por onde o `extrair_pagina` o entrega. Sem este elo os reparos
    ficariam escritos e desligados, que é o defeito que esta fase conserta.
    """
    import inspect

    assert (inspect.signature(livro._agrupar_em_paragrafos)
            .parameters["lex"].default is None)
    linhas = _linhas("com-", "promised")
    (p,) = livro._agrupar_em_paragrafos(linhas, None, _lex("compromised"))
    assert p.texto == "compromised"


def test_a_correcao_de_caixa_continua_preservando_o_comprimento():
    """
    A conferência que o `_paragrafo_de` faz antes de aceitar o texto arrumado.
    Enquanto ela passar, o vetor de espessuras é o mesmo dos dois lados.
    """
    lex = _lex("bishop", "also")
    texto = "biShop alSo"
    assert len(lexico.arrumar_caixa(texto, lex)) == len(texto)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
