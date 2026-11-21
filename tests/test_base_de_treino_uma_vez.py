"""A base de treino reflete o que o usuário promoveu, uma vez só (RG-05b, R-53).

- `salvar_cache` gravava a impressão digital do disco no momento de gravar: promovidos
  recortes por outro `CharacterLearner` (o da `coleta.promover`, que nunca salvava o
  cache), o learner vivo, que não os viu, gravava um cache "em dia" sem eles — e a sessão
  seguinte o carregava sem as amostras.
- Promover a mesma pasta duas vezes (a janela promove com `apagar=False`) duplicava as
  amostras no disco: o k-NN deduplica na leitura, o treino da rede não.
"""

import os

import cv2
import numpy as np

from core import coleta
from core.learner import CharacterLearner, char_to_folder


def _glifo(semente, forma=(20, 14)):
    gerador = np.random.default_rng(semente)
    return gerador.integers(0, 256, size=forma, dtype=np.uint8)


def _quarentena(pasta, char, sementes):
    destino = os.path.join(pasta, char_to_folder(char))
    os.makedirs(destino, exist_ok=True)
    for s in sementes:
        assert cv2.imwrite(os.path.join(destino, f"r{s}.png"), _glifo(s))
    return pasta


def _base(tmp_path):
    base = str(tmp_path / "base")
    vivo = CharacterLearner(data_dir=base)
    vivo.learn(_glifo(1), "a")
    vivo.learn(_glifo(2), "a")
    vivo.salvar_cache()
    return base


def test_o_cache_de_quem_nao_viu_a_promocao_nao_esconde_as_amostras(tmp_path):
    base = _base(tmp_path)
    vivo = CharacterLearner(data_dir=base)                   # a janela, aberta antes
    quarentena = _quarentena(str(tmp_path / "q"), "b", [10, 11, 12])
    coleta.promover(quarentena, data_dir=base)              # outro learner promove

    vivo.learn(_glifo(20), "c")                              # "Aprender com a página"
    vivo.salvar_cache()

    seguinte = CharacterLearner(data_dir=base)
    assert "b" in seguinte._classes, "a sessão seguinte não conhece as amostras promovidas"
    assert "c" in seguinte._classes


def test_a_promocao_pelo_learner_vivo_salva_o_cache_em_dia(tmp_path, monkeypatch):
    base = _base(tmp_path)
    vivo = CharacterLearner(data_dir=base)
    quarentena = _quarentena(str(tmp_path / "q"), "b", [10, 11, 12])
    coleta.promover(quarentena, learner=vivo)
    assert "b" in vivo._classes

    def sem_disco(self):
        raise AssertionError("a base foi relida do disco")

    monkeypatch.setattr(CharacterLearner, "_ler_do_disco", sem_disco)
    seguinte = CharacterLearner(data_dir=base)
    assert "b" in seguinte._classes and seguinte.total == vivo.total


def test_aprender_e_reabrir_carrega_do_cache(tmp_path, monkeypatch):
    base = _base(tmp_path)
    vivo = CharacterLearner(data_dir=base)
    vivo.learn(_glifo(30), "d")
    vivo.learn(_glifo(31), "d")
    vivo.salvar_cache()

    def sem_disco(self):
        raise AssertionError("a base foi relida do disco")

    monkeypatch.setattr(CharacterLearner, "_ler_do_disco", sem_disco)
    seguinte = CharacterLearner(data_dir=base)
    assert seguinte._chars.count("d") == 2


def test_promover_duas_vezes_nao_duplica_a_base(tmp_path):
    base = _base(tmp_path)
    quarentena = _quarentena(str(tmp_path / "q"), "b", [10, 11, 12])
    primeira = coleta.promover(quarentena, data_dir=base)
    segunda = coleta.promover(quarentena, data_dir=base)
    pasta_b = os.path.join(base, char_to_folder("b"))
    assert len([f for f in os.listdir(pasta_b) if f.endswith(".png")]) == 3, \
        "a segunda promoção duplicou as amostras no disco"
    assert (primeira.aprendidos, primeira.repetidos) == (3, 0)
    assert (segunda.aprendidos, segunda.repetidos) == (0, 3)

    # O mesmo desenho em outro tamanho é outra amostra (F107: o tamanho separa `s` de `S`).
    destino = os.path.join(quarentena, char_to_folder("b"))
    assert cv2.imwrite(os.path.join(destino, "maior.png"), cv2.resize(_glifo(10), (28, 40)))
    terceira = coleta.promover(quarentena, data_dir=base)
    assert (terceira.aprendidos, terceira.repetidos) == (1, 3)
