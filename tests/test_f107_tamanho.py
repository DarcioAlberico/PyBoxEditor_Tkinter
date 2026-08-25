"""
F107 — o tamanho que se perdia na gravação, e a régua do espaço que media errado.

Duas correções sem parentesco de código e com o mesmo parentesco de defeito:
uma régua comparando contra a referência errada.

  - `learn` gravava a amostra já em 32x32, e com isso a base inteira crescia
    sem a única coisa que separa `s` de `S`. O `resize` pertence à leitura, e
    ela já o fazia — a gravação era o único ponto do projeto em que a informação
    se **perdia**.
  - o espaço saía de `vão > 0,35 x largura de tinta`, e largura de tinta muda
    com o alfabeto sem que o espacejamento mude junto. Algarismo tabular é o
    caso que quebra, e `2011` saía `20 1 1`.

O primeiro teste de cada bloco é o motivo de a fase existir; os outros travam o
que faz a correção ser segura.

Rodar sem pytest:      python tests/test_f107_tamanho.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pytest

from core import diagrama, livro
from core.box_model import BoxEntry
from core.learner import LADO, CharacterLearner


def _glifo(alt, larg, valor=0):
    """Um retângulo de tinta de tamanho escolhido, sobre fundo branco."""
    img = np.full((alt, larg), 255, np.uint8)
    img[1:-1, 1:-1] = valor
    return img


def _box(x1, x2, y1=0, y2=20, char="?"):
    return BoxEntry(char, x1, y1, x2, y2)


def _linha(pares, y1=0, y2=20):
    """A linha de caixas a partir de [(x1, x2), ...]."""
    return [_box(a, b, y1, y2) for a, b in pares]


# ----------------------------------------------------------------------
# O tamanho da amostra gravada
# ----------------------------------------------------------------------

def test_a_amostra_e_gravada_no_tamanho_do_recorte():
    """
    É a razão de existir da metade `learn` da fase.

    Enquanto isto falhar, cada amostra nova entra na base sem a proporção e sem
    o tamanho, e nenhum treino futuro pode aprender o que separa `s` de `S`.
    """
    with tempfile.TemporaryDirectory() as tmp:
        ln = CharacterLearner(data_dir=tmp, usar_cache=False)
        ln.learn(_glifo(27, 17), "s")

        arquivos = [os.path.join(r, a) for r, _d, arqs in os.walk(tmp)
                    for a in arqs if a.endswith(".png")]
        assert len(arquivos) == 1
        assert cv2.imread(arquivos[0], cv2.IMREAD_GRAYSCALE).shape == (27, 17)


def test_o_esticao_continua_na_matriz_do_knn():
    """
    O disco muda, a matriz não.

    A matriz do k-NN é de linhas de `LADO x LADO` e o cache guarda esse
    tamanho — gravar o recorte cru **na matriz** quebraria a busca inteira. A
    separação é a correção: `resize` na leitura, tamanho no disco.
    """
    with tempfile.TemporaryDirectory() as tmp:
        ln = CharacterLearner(data_dir=tmp, usar_cache=False)
        ln.learn(_glifo(27, 17), "s")
        ln.learn(_glifo(9, 40), "-")
        assert ln._X.shape == (2, LADO * LADO)


def test_o_recorte_e_uma_fatia_da_pagina_e_grava_assim_mesmo():
    """
    `recorte_de_pe` devolve `img[y1:y2, x1:x2]`, que não é contíguo.

    Enquanto o que se gravava era o `resize`, isto não podia aparecer — o
    `resize` devolve array novo. Passando o recorte direto, o `cv2.imwrite`
    recusa o layout, e a amostra se perderia com um `IOError` no meio da
    revisão.
    """
    pagina = np.full((100, 100), 255, np.uint8)
    pagina[10:37, 20:37] = 0
    fatia = pagina[10:37, 20:37]
    assert not fatia.flags["C_CONTIGUOUS"]

    with tempfile.TemporaryDirectory() as tmp:
        ln = CharacterLearner(data_dir=tmp, usar_cache=False)
        ln.learn(fatia, "s")
        assert ln.total == 1


def test_o_caminho_da_ui_grava_com_tamanho():
    """
    Ponta a ponta pelo caminho que o usuário usa de fato.

    `learn_from_boxes` é o que a janela chama ao aprender uma página, e é ele
    que passa o recorte por `vertical.recorte_de_pe` — a fatia não-contígua.
    Testar só o `learn` deixaria de fora justamente a junta em que a mudança
    podia quebrar.
    """
    from PIL import Image

    from core.services.learning_service import LearningService

    pagina = np.full((80, 120), 255, np.uint8)
    caixas = [BoxEntry("s", 10, 20, 27, 47), BoxEntry("S", 40, 12, 63, 47)]
    for b in caixas:
        pagina[b.y1 + 1:b.y2 - 1, b.x1 + 1:b.x2 - 1] = 0

    with tempfile.TemporaryDirectory() as tmp:
        svc = LearningService(data_dir=tmp)
        assert svc.learn_from_boxes(Image.fromarray(pagina), caixas) == 2

        formas = sorted(cv2.imread(os.path.join(r, a),
                                   cv2.IMREAD_GRAYSCALE).shape
                        for r, _d, arqs in os.walk(tmp)
                        for a in arqs if a.endswith(".png"))
        # 27x17 e 35x23 — o `s` e o `S` chegam ao disco de tamanhos diferentes,
        # que é a única coisa que os separa.
        assert formas == [(27, 17), (35, 23)]


def test_a_base_de_tamanhos_variados_carrega():
    """
    O que a leitura já fazia, e por isso a correção coube numa linha.

    `_ler_do_disco` redimensiona o que não estiver em 32x32 — a base misturada,
    com o que foi gravado antes e depois desta fase, monta a mesma matriz.
    """
    with tempfile.TemporaryDirectory() as tmp:
        ln = CharacterLearner(data_dir=tmp, usar_cache=False)
        ln.learn(_glifo(27, 17), "s")
        ln.learn(cv2.resize(_glifo(31, 19), (LADO, LADO)), "s")

        outro = CharacterLearner(data_dir=tmp, usar_cache=False)
        assert outro.total == 2
        assert outro._X.shape[1] == LADO * LADO


# ----------------------------------------------------------------------
# A régua do espaço
# ----------------------------------------------------------------------

def test_o_algarismo_tabular_nao_vira_espaco():
    """
    É a razão de existir da metade `limiar_de_espaco` da fase.

    Quatro algarismos de `2011`: tinta estreita (7 px) e vão largo (5 px),
    porque o espacejamento é do avanço e não da tinta. Contra a largura, 5 é
    0,71 dela — muito acima de 0,35, e a régua velha punha três espaços dentro
    do ano. Contra o vão típico da linha, 5 **é** o vão típico.
    """
    ano = _linha([(0, 7), (12, 19), (24, 31), (36, 43)])
    limiar = diagrama.limiar_de_espaco(ano)
    vaos = [b.x1 - a.x2 for a, b in zip(ano, ano[1:])]
    assert all(v <= limiar for v in vaos)
    # E a régua velha punha espaço em todos eles — é o que a fase corrige.
    largura = float(np.median([b.width for b in ano]))
    assert all(v > largura * diagrama.VAO_DE_ESPACO for v in vaos)


def test_o_espaco_de_verdade_continua_espaco():
    """A régua nova não compra o silêncio recusando toda separação."""
    # "ab cd": vão de 2 px dentro da palavra, de 20 px entre elas.
    palavras = _linha([(0, 10), (12, 22), (42, 52), (54, 64)])
    limiar = diagrama.limiar_de_espaco(palavras)
    vaos = [b.x1 - a.x2 for a, b in zip(palavras, palavras[1:])]
    assert vaos == [2, 20, 2]
    assert [v > limiar for v in vaos] == [False, True, False]


def test_a_linha_de_uma_palavra_so_nao_ganha_espaco():
    """
    O piso é o que impede a régua de inventar separação onde não há nenhuma.

    Numa linha sem espaço, o vão típico é o vão entre letras, e `2,0 x` ele
    ainda é pequeno: sem piso, a folga um pouco maior de um par qualquer viraria
    palavra nova. O defeito seria simétrico ao que a régua velha tem com
    algarismo, e trocar um pelo outro não seria conserto.
    """
    palavra = _linha([(0, 10), (12, 22), (24, 34), (37, 47), (49, 59)])
    limiar = diagrama.limiar_de_espaco(palavra)
    vaos = [b.x1 - a.x2 for a, b in zip(palavra, palavra[1:])]
    assert max(vaos) == 3            # um par um pouco mais folgado
    assert all(v <= limiar for v in vaos)


def test_a_linha_de_glifos_colados_cai_no_piso():
    """
    Vão típico zero ou negativo é linha colada, e ali a referência relativa não
    existe. Quem responde é o piso — e não `0 x qualquer coisa`, que faria toda
    folga de um pixel virar espaço.
    """
    colados = _linha([(0, 10), (10, 20), (20, 30), (30, 40)])
    limiar = diagrama.limiar_de_espaco(colados)
    assert limiar == pytest.approx(10 * diagrama.PISO_DO_VAO)
    assert limiar > 0


def test_uma_caixa_so_nao_tem_vao_para_medir():
    """Sem par não há vão, e a régua devolve o que nunca dispara."""
    assert diagrama.limiar_de_espaco([]) == float("inf")
    assert diagrama.limiar_de_espaco(_linha([(0, 10)])) == float("inf")


def test_a_faixa_curta_nao_perde_o_espaco_para_a_propria_mediana():
    """
    Com um vão só, esse vão **é** a mediana, e `2,0 x` ele nunca é alcançado.

    Numa faixa de duas marcas separadas por espaço — o cabeçalho curto de
    diagrama —, a parte relativa apagaria a separação: o único vão viraria a
    referência de si mesmo. Abaixo de `VAOS_PARA_A_MEDIANA` quem responde é o
    piso, e ali o espaço volta a aparecer.
    """
    faixa = _linha([(0, 10), (40, 50)])
    assert diagrama.limiar_de_espaco(faixa) == pytest.approx(
        10 * diagrama.PISO_DO_VAO)
    assert faixa[1].x1 - faixa[0].x2 > diagrama.limiar_de_espaco(faixa)


def test_a_parte_relativa_so_vale_onde_foi_medida():
    """
    O `medir_vao` pulou linha com menos de 4 caixas, então os pares que
    escolheram as duas constantes são todos de 3 vãos ou mais. A régua respeita
    o mesmo limite em vez de extrapolar para onde ninguém mediu.
    """
    colados = [(0, 10), (10, 20), (20, 30), (30, 40)]
    curta = diagrama.limiar_de_espaco(_linha(colados[:3]))     # 2 vãos
    longa = diagrama.limiar_de_espaco(_linha(colados))          # 3 vãos
    piso = 10 * diagrama.PISO_DO_VAO
    assert curta == pytest.approx(piso)
    assert longa == pytest.approx(piso)   # aqui a mediana é 0, e o piso ganha


def test_a_regra_do_instrumento_e_a_de_producao():
    """
    A trava contra as duas divergirem — é o arranjo que a F5.2 fixou.

    `medir_vao.regra_nova` repete a conta em vez de importá-la, porque precisa
    avaliar pares já medidos sem as caixas à mão. O preço disso é este teste:
    as duas respondem igual sobre a mesma linha, ou uma delas mudou sozinha.
    """
    import medir_vao

    for pares in ([(0, 7), (12, 19), (24, 31), (36, 43)],
                  [(0, 10), (12, 22), (42, 52), (54, 64)],
                  [(0, 10), (10, 20), (20, 30), (30, 40)]):
        linha = _linha(pares)
        limiar = diagrama.limiar_de_espaco(linha)
        largura = float(np.median([b.width for b in linha]))
        tipico = max(float(np.median([b.x1 - a.x2
                                      for a, b in zip(linha, linha[1:])])), 0.0)
        for a, b in zip(linha, linha[1:]):
            vao = b.x1 - a.x2
            assert (vao > limiar) == medir_vao.regra_nova(
                vao, largura, 0.0, tipico)


def test_o_livro_le_a_linha_com_a_regua_nova():
    """
    Ponta a ponta: a régua trocada aparece no texto que o livro exporta.

    Sem isto, `limiar_de_espaco` podia estar certa e `_texto_da_linha` continuar
    chamando a conta velha — que é exatamente o defeito que a F5.2 nomeou.
    """
    img = np.full((40, 60), 255, np.uint8)
    ano = _linha([(0, 7), (12, 19), (24, 31), (36, 43)], y1=5, y2=25)
    for b in ano:
        img[b.y1 + 1:b.y2 - 1, b.x1 + 1:b.x2 - 1] = 0

    texto, _fracos, _pesos = livro._texto_da_linha(
        img, ano, lambda r: ("2", 0.99), conf_minima=0.5)
    assert texto == "2222"        # sem espaço nenhum dentro do ano


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
