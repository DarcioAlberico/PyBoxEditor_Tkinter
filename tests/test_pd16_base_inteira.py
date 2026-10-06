"""
PD-16 (F1.3) — o treino na base inteira, na epoch que o treino com validação achou.

O treino com validação deixa 20% da base fora dos pesos para escolher a epoch e
parar cedo. `NeuralTrainer.train(base_inteira=True)` treina em 100% das
amostras por exatamente `epochs` epochs e grava a última; não escreve relatório,
porque a validação mediria amostras que o modelo viu.

Rodar sem pytest:      python tests/test_pd16_base_inteira.py
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image

from core.neural_trainer import NeuralTrainer


def _base(raiz):
    regioes = {"upper_A": (slice(8, 24), slice(8, 24)),
               "upper_B": (slice(4, 28), slice(12, 20)),
               "upper_C": (slice(10, 22), slice(4, 28))}
    for pasta, regiao in regioes.items():
        d = os.path.join(raiz, pasta)
        os.makedirs(d, exist_ok=True)
        for i in range(40):
            img = np.full((32, 32), 255, dtype=np.uint8)
            img[regiao] = 0
            Image.fromarray(img).save(os.path.join(d, f"{i:04d}.png"))
    return raiz


def test_treina_em_todas_as_amostras_e_grava_a_ultima_epoch():
    with tempfile.TemporaryDirectory() as tmp:
        dados = _base(os.path.join(tmp, "dados"))
        msgs = []
        assert NeuralTrainer(dados, os.path.join(tmp, "m.pth"),
                             os.path.join(tmp, "m.json")).train(
            epochs=3, base_inteira=True, calibrar=False, callback=msgs.append)
        assert any("Base inteira: 120 amostras" in m for m in msgs), msgs
        # Uma linha por epoch, sem parada cedo e sem validação.
        assert sum(m.startswith("Epoch ") for m in msgs) == 3
        assert not any("val loss" in m for m in msgs)
        assert not os.path.exists(os.path.join(tmp, "relatorio_treino.txt"))
        meta = json.load(open(os.path.join(tmp, "m.json"), encoding="utf-8"))
        assert meta["num_classes"] == 3 and meta["temperatura"] == 1.0


def test_sem_a_opcao_o_treino_continua_com_validacao():
    with tempfile.TemporaryDirectory() as tmp:
        dados = _base(os.path.join(tmp, "dados"))
        msgs = []
        NeuralTrainer(dados, os.path.join(tmp, "m.pth"),
                      os.path.join(tmp, "m.json")).train(
            epochs=1, calibrar=False, callback=msgs.append)
        assert any("val loss" in m for m in msgs)
        assert os.path.exists(os.path.join(tmp, "relatorio_treino.txt"))


if __name__ == "__main__":
    test_treina_em_todas_as_amostras_e_grava_a_ultima_epoch()
    test_sem_a_opcao_o_treino_continua_com_validacao()
    print("ok")
