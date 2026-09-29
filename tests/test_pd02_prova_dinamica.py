"""
PD-02 (`docs/ROADMAP_PENDENCIAS.md`) — `provar_letras` por programação dinâmica.

A F119 registrou que a prova ainda enumerava `5^(n-1)` partições por candidato
(1,7 s de Python no `Matewith`). O corte de cada junta depende só do corte da
anterior e a nota é a do pedaço mais fraco — um caminho de gargalo —, então o
melhor até cada corte basta. A nota tem de ser **a mesma** da enumeração, até
o último bit, e é isso que estes testes cobram.
"""

import itertools
import random
import sys
import time

import numpy as np
import pytest

from core.box_model import BoxEntry
from core.services.box_service import BoxService


def _provar_por_enumeracao(imagem, box, letras, probabilidade):
    """A `provar_letras` de antes da PD-02, copiada: todas as partições."""
    largura = box.x2 - box.x1
    if not letras or largura <= 0:
        return 0.0

    def pontuar(ini, fim, c):
        pedaco = imagem[box.y1:box.y2, box.x1 + ini:box.x1 + fim]
        return 0.0 if pedaco.size == 0 else float(probabilidade(pedaco, c))

    def nota(limites):
        menor = 1.0
        for (ini, fim), c in zip(zip(limites, limites[1:]), letras):
            menor = min(menor, pontuar(ini, fim, c))
            if menor == 0.0:
                return 0.0
        return menor

    if len(letras) == 1:
        return nota([0, largura])
    letra = largura / len(letras)
    passos = []
    d = -BoxService.DESLOCAMENTO_DE_PROVA
    while d <= BoxService.DESLOCAMENTO_DE_PROVA + 1e-9:
        passos.append(d)
        d += BoxService.PASSO_DE_PROVA
    melhor = 0.0
    for combinacao in itertools.product(passos, repeat=len(letras) - 1):
        limites = [0]
        for i, desloc in enumerate(combinacao, start=1):
            corte = int(round(letra * (i + desloc)))
            limites.append(min(largura - 1, max(limites[-1] + 1, corte)))
        limites.append(largura)
        melhor = max(melhor, nota(limites))
        if melhor == 1.0:
            break
    return melhor


def _probabilidade_ao_acaso(semente):
    """Determinística no recorte e na letra, e com zeros — os zeros são o que
    exercita a poda dos caminhos mortos."""
    def probabilidade(recorte, char):
        h = hash((semente, recorte.shape, int(recorte.sum()), char))
        valor = (h % 1000) / 999.0
        return 0.0 if valor < 0.08 else valor
    return probabilidade


def test_a_nota_e_a_da_enumeracao_em_todas_as_formas():
    rnd = random.Random(29)
    for caso in range(400):
        largura = rnd.randint(3, 70)
        letras = "".join(rnd.choice("mnwyvi") for _ in range(rnd.randint(1, 6)))
        imagem = np.array([[rnd.randint(0, 255) for _ in range(largura + 4)]
                           for _ in range(12)], np.uint8)
        box = BoxEntry("m", 2, 1, 2 + largura, 11)
        probabilidade = _probabilidade_ao_acaso(caso)
        esperado = _provar_por_enumeracao(imagem, box, letras, probabilidade)
        obtido = BoxService.provar_letras(imagem, box, letras, probabilidade)
        assert obtido == esperado, (caso, largura, letras)


def test_oito_letras_nao_custam_as_78_mil_particoes():
    imagem = np.full((20, 200), 128, np.uint8)
    box = BoxEntry("m", 0, 0, 160, 20)
    perguntas = []

    def probabilidade(recorte, char):
        perguntas.append(char)
        return 0.5 + (recorte.shape[1] % 7) / 20.0

    inicio = time.monotonic()
    nota = BoxService.provar_letras(imagem, box, "Matewith", probabilidade)
    assert 0.0 < nota <= 1.0
    assert time.monotonic() - inicio < 0.5
    assert len(perguntas) < 400


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
