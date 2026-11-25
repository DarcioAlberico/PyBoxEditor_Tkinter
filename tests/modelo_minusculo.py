"""
Um treino de verdade, minúsculo, para os testes olharem o metadado que o
`NeuralTrainer.train` grava em vez de lerem a fonte dele (PD-26, R-39).

Duas classes de vinte quadrados pretos, uma época, sem calibração nem relatório:
uns segundos na CPU. Antes do treino, o metadado no destino é o de um "modelo
anterior" calibrado (`TEMPERATURA_ANTERIOR`), para o teste poder ver que o treino
não a herda.

Não é arquivo de teste (não começa por `test_`): o pytest não o coleta.
"""

from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

TEMPERATURA_ANTERIOR = 1.7


def treinar(pasta):
    """`(caminho_do_modelo, caminho_do_metadado)` de um treino minúsculo em `pasta`."""
    from core.neural_trainer import NeuralTrainer

    dados = os.path.join(pasta, "base")
    for classe, deslocamento in (("lower_a", 4), ("lower_b", 12)):
        os.makedirs(os.path.join(dados, classe))
        for i in range(20):
            img = np.full((32, 32), 255, dtype=np.uint8)
            img[deslocamento:deslocamento + 14, 8:24] = 0
            Image.fromarray(img).save(os.path.join(dados, classe, f"{i:04d}.png"))
    modelo, meta = os.path.join(pasta, "m.pth"), os.path.join(pasta, "m.json")
    with open(meta, "w", encoding="utf-8") as f:
        json.dump({"temperatura": TEMPERATURA_ANTERIOR}, f)
    assert NeuralTrainer(dados, modelo, meta).train(epochs=1, calibrar=False, relatorio=False)
    return modelo, meta


def ler_meta(caminho):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)
