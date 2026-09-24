"""
F119 — a prova do reparo repagava o modelo a cada candidato.

`prova_de_reparo` guardava a nota do trecho inteiro, e `provar_letras` guardava a
do recorte só dentro de uma chamada. Os candidatos de uma palavra perguntam as
mesmas letras aos mesmos recortes, e cada um pagava o modelo de novo: no sumário
do Rabinovich (p. 4), o `Matewith` de "Mate with the queen" tem 22.852
candidatos, e a exportação passou mais de uma hora na página. Com a memória do recorte
na página inteira, a nota não muda — o modelo é determinístico — e a pergunta
repetida não volta a ele.

O `probabilidade` é injetado, como na F69: estes testes não precisam de rede.
"""

import numpy as np

from core.box_model import BoxEntry
from core.services.box_service import BoxService


def _pagina():
    """Dois boxes de mesma largura e desenho diferente: o da esquerda claro,
    o da direita escuro — para a nota depender do box, e não só do recorte."""
    pagina = np.full((20, 80), 255, np.uint8)
    pagina[:, 50:80] = 40
    return pagina


def _probabilidade(perguntas):
    def probabilidade(recorte, char):
        perguntas.append(char)
        # Depende do conteúdo e da letra, para que uma memória com a chave
        # errada (sem o box, sem a posição) devolvesse a nota de outro recorte.
        return float(recorte.mean()) / 255.0 * (0.9 if char in "yn" else 0.6)
    return probabilidade


def test_a_letra_repetida_no_mesmo_recorte_nao_volta_ao_modelo():
    perguntas = []
    provar = BoxService.prova_de_reparo(_pagina(), [BoxEntry("m", 0, 0, 30, 20)],
                                        _probabilidade(perguntas))
    provar([0], "yn")
    ys = perguntas.count("y")
    assert ys > 0
    # Outro candidato, com o mesmo `y` nos mesmos recortes: só o `o` é novo.
    provar([0], "yo")
    assert perguntas.count("y") == ys
    assert perguntas.count("o") > 0


def test_a_nota_e_a_mesma_com_e_sem_a_memoria_da_pagina():
    """A memória é por box: dois boxes de mesma largura e desenho diferente
    têm as notas deles, e a de cada um é a que `provar_letras` daria sozinho."""
    pagina = _pagina()
    boxes = [BoxEntry("m", 0, 0, 30, 20), BoxEntry("m", 50, 0, 80, 20)]
    provar = BoxService.prova_de_reparo(pagina, boxes, _probabilidade([]))
    for letras in ("yn", "yo", "rn", "y"):
        for i, box in enumerate(boxes):
            sozinho = BoxService.provar_letras(pagina, box, letras,
                                               _probabilidade([]))
            assert provar([i], letras) == sozinho, (letras, i)
    # E a repartição entre dois boxes também sai igual à conta sem memória.
    esperado = max(
        min(BoxService.provar_letras(pagina, boxes[0], "yn"[:k], _probabilidade([])),
            BoxService.provar_letras(pagina, boxes[1], "yn"[k:], _probabilidade([])))
        for k in (1,))
    assert provar([0, 1], "yn") == esperado


def _preditor(tmp_path):
    """Um `NeuralPredictor` carregado, com pesos aleatórios de cinco classes —
    o par de mentira do `test_f73_modelo`."""
    import json

    import torch

    from core.neural_model import SimpleCNN
    from core.neural_trainer import (SCHEMA_META, NeuralPredictor,
                                     impressao_das_classes, impressao_do_modelo)

    idx = {str(i): c for i, c in enumerate("abcde")}
    pth, meta = tmp_path / "m.pth", tmp_path / "m.json"
    torch.save(SimpleCNN(len(idx)).state_dict(), str(pth))
    meta.write_text(json.dumps({
        "schema_version": SCHEMA_META,
        "label_map": {c: i for i, c in enumerate("abcde")},
        "idx_to_char": idx, "num_classes": len(idx), "temperatura": 2.0,
        "modelo_sha256": impressao_do_modelo(str(pth)),
        "classes_sha256": impressao_das_classes(idx)}), encoding="utf-8")
    p = NeuralPredictor(str(pth), str(meta))
    assert p.load()
    return p


def test_o_vetor_do_recorte_serve_a_todas_as_letras(tmp_path):
    """A prova pergunta ao mesmo recorte por uma letra de cada vez, e o softmax
    já traz todas: uma passada da rede por recorte, e não uma por pergunta."""
    p = _preditor(tmp_path)
    passadas = []
    modelo = p.model
    p.model = lambda tensor: passadas.append(1) or modelo(tensor)
    recorte = np.arange(20 * 12, dtype=np.uint8).reshape(20, 12)

    notas = {c: p.probabilidade_de(recorte, c) for c in "abcde"}
    assert len(passadas) == 1
    assert abs(sum(notas.values()) - 1.0) < 1e-5
    # Outro recorte (e fatiado, como os de `provar_letras`) é outra passada; o
    # mesmo recorte de novo, nenhuma.
    p.probabilidade_de(recorte[:, :6], "a")
    p.probabilidade_de(recorte, "c")
    assert len(passadas) == 2
    # E a nota guardada é a de uma passada sem memória.
    p._recortes = {}
    assert p.probabilidade_de(recorte, "c") == notas["c"]


def test_carregar_de_novo_esvazia_a_memoria(tmp_path):
    """Os pesos e a temperatura vêm do `load`: um vetor guardado antes dele é de
    outro modelo."""
    p = _preditor(tmp_path)
    p.probabilidade_de(np.full((20, 12), 128, np.uint8), "a")
    assert p._recortes
    assert p.load()
    assert not p._recortes


def test_sem_a_memoria_da_pagina_provar_letras_e_o_de_antes():
    """Quem chama `provar_letras` direto — os testes da F69, o `medir_reparo` —
    continua com a memória só da chamada."""
    perguntas = []
    box = BoxEntry("m", 0, 0, 30, 20)
    BoxService.provar_letras(_pagina(), box, "yn", _probabilidade(perguntas))
    uma = len(perguntas)
    BoxService.provar_letras(_pagina(), box, "yn", _probabilidade(perguntas))
    assert len(perguntas) == 2 * uma
