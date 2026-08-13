"""
F8.4 — o corpus de outro projeto vira amostra da nossa base.

O risco desta fase é o mesmo da F8.3 e o pior de todos: **estragar a base sem
sintoma**. Lá a defesa era "silêncio não é confirmação" — só entra a casa que a
mão tocou. Aqui não há mão nenhuma: são 45 mil amostras de rótulo alheio,
entrando de uma vez.

A defesa que sobra é a ocupação. Ela é a **outra** rede, independente do que se
quer aprender (diz se há peça, não qual), e acerta 99,8% neste mesmo corpus. Onde
ela discorda do FEN em muitas casas, ou o recorte pegou a legenda embaixo do
tabuleiro — o caso real que a fase encontrou — ou o rótulo está errado. Os dois
produzem amostra torta com rótulo confiante, que é o defeito da F1.4.

Rodar sem pytest:      python tests/test_f84_corpus.py
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pytest

import importar_diagramas as imp
from core import treino_diagrama


# ----------------------------------------------------------------------
# Apoio: um corpus de mentira, com a mesma forma do de verdade
# ----------------------------------------------------------------------

def _tabuleiro(pecas, lado=320):
    """Tabuleiro com casas alternadas e um disco onde houver peça."""
    im = np.full((lado, lado), 250, np.uint8)
    passo = lado // 8
    for r in range(8):
        for c in range(8):
            if (r + c) % 2:
                im[r * passo:(r + 1) * passo, c * passo:(c + 1) * passo] = 170
    for r, c in pecas:
        cv2.circle(im, (c * passo + passo // 2, r * passo + passo // 2),
                   passo // 3, 0, -1)
    return im


def _corpus(tmp_path, linhas, splits=None, quarentena=(), distinguir=True):
    """
    Monta a pasta do corpus. `linhas` é [(nome, fen, casas com peça)].

    A imagem é desenhada a partir das casas pedidas, e não do FEN, justamente
    para dar como montar o caso em que os dois discordam.

    `distinguir` carimba um pixel diferente em cada tabuleiro, no canto e a um
    tom do fundo, para que dois tabuleiros com as mesmas peças não saiam byte a
    byte iguais — o corpus de verdade é assim, e a deduplicação da F8.4
    engoliria o resto dos testes. Quem testa a repetição desliga isto.
    """
    raiz = tmp_path / "corpus"
    (raiz / "data").mkdir(parents=True)
    (raiz / "samples").mkdir()

    with open(raiz / "data" / "labels.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["filename", "fen"])
        for i, (nome, fen, pecas) in enumerate(linhas):
            w.writerow([nome, fen])
            im = _tabuleiro(pecas)
            if distinguir:
                im[0, 0] = 250 - i - 1
            cv2.imwrite(str(raiz / "samples" / nome), im)

    if splits:
        with open(raiz / "data" / "splits.csv", "w", newline="",
                  encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["filename", "split"])
            for nome, split in splits.items():
                w.writerow([nome, split])

    if quarentena:
        with open(raiz / "data" / "quarantine.csv", "w", newline="",
                  encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["filename", "fen", "motivo"])
            for nome in quarentena:
                w.writerow([nome, "", "teste"])
    return str(raiz)


#: Uma torre preta em a8 e uma branca em a1 — duas casas, dois símbolos.
FEN_DUAS = "r7/8/8/8/8/8/8/R7"
CASAS_DUAS = [(0, 0), (7, 0)]


# ----------------------------------------------------------------------
# O FEN vira casas
# ----------------------------------------------------------------------

def test_o_fen_vira_as_64_casas():
    casas = imp.casas_do_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1")
    assert len(casas) == 64
    assert sum(1 for v in casas.values() if v) == 32


def test_a_linha_zero_e_a_oitava_fila():
    """
    Mesma convenção do `Casa` do leitor: linha 0 em cima, coluna 0 no 'a'.

    Errar isto espelharia a base inteira sem levantar exceção — a torre preta
    entraria rotulada como branca e vice-versa.
    """
    casas = imp.casas_do_fen(FEN_DUAS)
    assert casas[(0, 0)] == "r", "a8 devia ser a torre preta"
    assert casas[(7, 0)] == "R", "a1 devia ser a torre branca"
    assert imp.nome_da_casa(0, 0) == "a8"
    assert imp.nome_da_casa(7, 7) == "h1"


def test_o_fen_com_lacunas_numericas():
    casas = imp.casas_do_fen("8/8/8/3q4/8/8/8/8")
    assert casas[(3, 3)] == "q"
    assert sum(1 for v in casas.values() if v) == 1


# ----------------------------------------------------------------------
# O que entra
# ----------------------------------------------------------------------

def test_importa_as_pecas_do_tabuleiro(tmp_path):
    corpus = _corpus(tmp_path, [("board_20260101_000001_000001.png",
                                 FEN_DUAS, CASAS_DUAS)])
    destino = str(tmp_path / "base")

    r = imp.importar(corpus, destino, progresso=lambda *a: None)

    assert r["tabuleiros"] == 1
    assert r["por_classe"] == {"r": 1, "R": 1}
    assert treino_diagrama.contagem(destino)["r"] == 1
    assert treino_diagrama.contagem(destino)["R"] == 1


def test_a_casa_vazia_nao_entra(tmp_path):
    """
    62 das 64 casas estão vazias, e nenhuma vira amostra.

    Não é esquecimento: a rede de ocupação já acerta 99,8% neste corpus, e a de
    identidade 76,4%. Importar 168 mil amostras para a pergunta resolvida
    custaria toda a memória do treino sem mover o número que está errado.
    """
    corpus = _corpus(tmp_path, [("board_20260101_000001_000001.png",
                                 FEN_DUAS, CASAS_DUAS)])
    destino = str(tmp_path / "base")
    imp.importar(corpus, destino, progresso=lambda *a: None)

    conta = treino_diagrama.contagem(destino)
    assert sum(conta.values()) == 2
    assert not os.path.isdir(os.path.join(destino, "vazia"))


def test_cada_tabuleiro_e_um_grupo_de_medicao(tmp_path):
    """
    `separar_por_diagrama` só é honesto se as amostras do mesmo tabuleiro
    ficarem do mesmo lado. O nome que `gravar` escreve carrega a marca da
    procedência, e é dela que `grupo_da_amostra` tira o grupo.
    """
    corpus = _corpus(tmp_path, [
        ("board_20260101_000001_000001.png", FEN_DUAS, CASAS_DUAS),
        ("board_20260101_000002_000002.png", FEN_DUAS, CASAS_DUAS)])
    destino = str(tmp_path / "base")
    imp.importar(corpus, destino, progresso=lambda *a: None)

    caminhos = [c for _, _, c in treino_diagrama.carregar_amostras(destino)]
    grupos = {treino_diagrama.grupo_da_amostra(c) for c in caminhos}
    assert len(caminhos) == 4
    assert len(grupos) == 2, "os dois tabuleiros viraram um grupo só"


# ----------------------------------------------------------------------
# O que não entra
# ----------------------------------------------------------------------

def test_o_tabuleiro_que_a_ocupacao_desmente_nao_entra(tmp_path):
    """
    O caso real da fase: o recorte de 800x800 às vezes pega a legenda de
    avaliação impressa abaixo do tabuleiro. A divisão 8x8 sai comprimida, toda
    casa fica deslocada — e o FEN continua dizendo com segurança o que há em
    cada uma.

    Aqui o desenho tem as peças em outro lugar que não o do FEN, que é a mesma
    discordância vista pela ocupação.
    """
    fen_cheio = "rrrrrrrr/rrrrrrrr/8/8/8/8/8/8"        # 16 peças em cima
    corpus = _corpus(tmp_path, [("board_20260101_000001_000001.png",
                                 fen_cheio, [(7, 0)])])   # e uma só, embaixo
    destino = str(tmp_path / "base")

    r = imp.importar(corpus, destino, progresso=lambda *a: None)

    assert r["tabuleiros"] == 0
    assert r["amostras"] == 0
    assert len(r["recusados"]) == 1
    assert "ocupação discorda" in r["recusados"][0][1]


def test_o_split_de_teste_fica_de_fora(tmp_path):
    """
    Sem isto não sobra material para medir. O `medir_diagramas.py` mede
    justamente neste split, e importá-lo transformaria a medição em memória —
    o defeito que a F1.3 registrou e a F7.4 mediu.
    """
    corpus = _corpus(
        tmp_path,
        [("board_20260101_000001_000001.png", FEN_DUAS, CASAS_DUAS),
         ("board_20260101_000002_000002.png", FEN_DUAS, CASAS_DUAS)],
        splits={"board_20260101_000001_000001.png": "train",
                "board_20260101_000002_000002.png": "test"})
    destino = str(tmp_path / "base")

    r = imp.importar(corpus, destino, progresso=lambda *a: None)
    assert r["tabuleiros"] == 1

    r2 = imp.importar(corpus, str(tmp_path / "b2"), incluir_teste=True,
                      progresso=lambda *a: None)
    assert r2["tabuleiros"] == 2


def test_a_imagem_que_esta_no_teste_nao_entra_pelo_treino(tmp_path):
    """
    O mesmo tabuleiro sob dois nomes, um em cada split, importaria a versão de
    treino e continuaria sendo medido pela de teste — vazamento que não avisa
    que está inflando o número. O corpus de hoje não tem nenhum caso; a garantia
    tem de vir da lógica e não disso.
    """
    corpus = _corpus(
        tmp_path,
        [("board_20260101_000001_000001.png", FEN_DUAS, CASAS_DUAS),
         ("board_20260101_000002_000002.png", FEN_DUAS, CASAS_DUAS)],
        splits={"board_20260101_000001_000001.png": "train",
                "board_20260101_000002_000002.png": "test"},
        distinguir=False)
    destino = str(tmp_path / "base")

    r = imp.importar(corpus, destino, progresso=lambda *a: None)
    assert r["tabuleiros"] == 0, "a imagem do split de teste entrou pelo treino"


def test_a_quarentena_do_outro_projeto_e_respeitada(tmp_path):
    """Eles já separaram as posições impossíveis; refazer o exame seria tolice."""
    corpus = _corpus(
        tmp_path,
        [("board_20260101_000001_000001.png", FEN_DUAS, CASAS_DUAS),
         ("board_20260101_000002_000002.png", FEN_DUAS, CASAS_DUAS)],
        quarentena=["board_20260101_000002_000002.png"])
    destino = str(tmp_path / "base")

    assert imp.importar(corpus, destino,
                        progresso=lambda *a: None)["tabuleiros"] == 1


def test_o_limite_por_classe_para_de_gravar(tmp_path):
    """
    O teto existe porque o corpus é desbalanceado — 11.928 peões brancos contra
    1.409 damas. Sem ele, importar "tudo" é importar peão.
    """
    corpus = _corpus(tmp_path, [
        (f"board_2026010{i}_00000{i}_00000{i}.png", FEN_DUAS, CASAS_DUAS)
        for i in range(1, 4)])
    destino = str(tmp_path / "base")

    r = imp.importar(corpus, destino, limite=2, progresso=lambda *a: None)
    assert r["por_classe"] == {"r": 2, "R": 2}


def test_a_imagem_repetida_entra_uma_vez_so(tmp_path):
    """
    O corpus tem a mesma imagem sob nomes diferentes: 3.439 linhas para 3.264
    imagens. O gêmeo não é só desperdício — `grupo_da_amostra` agrupa pela marca
    da procedência, e dois nomes são dois grupos, então as mesmas casas poderiam
    cair uma no treino e outra no teste. É o que a F7.4 mediu inflando o número.
    """
    corpus = _corpus(tmp_path, [
        ("board_20260101_000001_000001.png", FEN_DUAS, CASAS_DUAS),
        ("board_20260101_000002_000002.png", FEN_DUAS, CASAS_DUAS)],
        distinguir=False)
    destino = str(tmp_path / "base")

    r = imp.importar(corpus, destino, progresso=lambda *a: None)

    assert r["tabuleiros"] == 1, "a imagem repetida entrou duas vezes"
    assert [m for _, m in r["recusados"]] == ["imagem repetida"]


def test_a_imagem_repetida_com_rotulo_conflitante_sai_inteira(tmp_path):
    """
    Aconteceu uma vez no corpus real: a mesma imagem com `c2` rotulado bispo numa
    linha e peão na outra — e é peão. A ocupação não pega o caso, porque as duas
    dizem "ocupada"; quem pega é a contradição.

    **Saem as duas**, e não "fica a primeira": não há como saber qual está certa,
    e rótulo contraditório na base é o defeito da F1.4, que `conferir` classifica
    como erro grave.
    """
    outro_fen = "b7/8/8/8/8/8/8/R7"          # o mesmo desenho, outra peça em a8
    corpus = _corpus(tmp_path, [
        ("board_20260101_000001_000001.png", FEN_DUAS, CASAS_DUAS),
        ("board_20260101_000002_000002.png", outro_fen, CASAS_DUAS)],
        distinguir=False)
    destino = str(tmp_path / "base")

    r = imp.importar(corpus, destino, progresso=lambda *a: None)

    assert r["tabuleiros"] == 0
    assert {m for _, m in r["recusados"]} == {"mesma imagem com FEN conflitante"}
    assert not treino_diagrama.carregar_amostras(destino)


def test_imagens_diferentes_com_o_mesmo_fen_entram_as_duas(tmp_path):
    """
    A mesma posição impressa em dois livros é duas amostras legítimas — e são
    justamente as que ensinam a fonte nova. Deduplicar por FEN jogaria fora o
    que o corpus tem de mais valioso.
    """
    corpus = _corpus(tmp_path, [
        ("board_20260101_000001_000001.png", FEN_DUAS, CASAS_DUAS),
        ("board_20260101_000002_000002.png", FEN_DUAS, CASAS_DUAS)])
    destino = str(tmp_path / "base")

    r = imp.importar(corpus, destino, progresso=lambda *a: None)
    assert r["tabuleiros"] == 2, "deduplicou por FEN em vez de por imagem"
    assert not r["recusados"]


def test_conferir_nao_grava_nada(tmp_path):
    corpus = _corpus(tmp_path, [("board_20260101_000001_000001.png",
                                 FEN_DUAS, CASAS_DUAS)])
    destino = str(tmp_path / "base")

    r = imp.importar(corpus, destino, conferir_so=True,
                     progresso=lambda *a: None)
    assert r["amostras"] == 2 and r["gravados"] == 0
    assert not os.path.isdir(destino)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
