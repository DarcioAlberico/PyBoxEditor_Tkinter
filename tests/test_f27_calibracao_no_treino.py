"""
F27 — o treino calibra sozinho no fim.

A F26 pôs o aviso de "este modelo está sem calibração", e fechou dizendo que o
aviso é o remédio barato: enquanto der para terminar um treino e sair sem
calibrar, a situação da F25 volta a acontecer — só que avisada. Esta fase fecha
o buraco.

O que decidiu foi o custo, que ninguém tinha medido: **20 s** nas dez páginas
rotuladas (8,6 s colhendo logits, 11,6 s ajustando a temperatura), contra os
minutos de um treino.

O que estes testes guardam é o contrato, e não o número: que a temperatura sai
de 1,0 quando dá, que **o treino nunca cai** quando não dá, e que o metadado
sobrevive inteiro à regravação — ele carrega os dois SHA-256 da F7.3, e
remontá-lo de fora é o caminho para dessincronizá-los em silêncio.

Rodar sem pytest:      python tests/test_f27_calibracao_no_treino.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

from core import calibracao_de_pagina as cal
from core.neural_trainer import NeuralTrainer


def _base(tmp_path, classes=("a", "b", "c"), por_classe=12):
    """Uma base de treino mínima: pastas de classe com PNGs de tom distinto."""
    import cv2

    raiz = tmp_path / "dados"
    for i, c in enumerate(classes):
        pasta = raiz / f"lower_{c}"
        pasta.mkdir(parents=True, exist_ok=True)
        tom = 20 + i * 80
        for n in range(por_classe):
            img = np.full((32, 32), tom, np.uint8)
            img[n % 32, n % 32] = 255          # cada amostra distinta
            cv2.imwrite(str(pasta / f"{n}.png"), img)
    return str(raiz)


def _treinar(tmp_path, **kw):
    dados = _base(tmp_path)
    mp = str(tmp_path / "m.pth")
    jp = str(tmp_path / "m.json")
    msgs = []
    ok = NeuralTrainer(dados, mp, jp).train(epochs=1, callback=msgs.append, **kw)
    return ok, jp, msgs


def _meta(caminho):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------------
# Sem página rotulada — o estado de quem nunca rotulou uma
# ----------------------------------------------------------------------

def test_sem_pagina_rotulada_o_treino_termina_e_avisa(tmp_path):
    """
    Não é erro: é o estado normal de uma instalação nova. O modelo tem de ficar
    gravado e utilizável, com a temperatura neutra e a ressalva da F26 acesa.
    """
    ok, jp, msgs = _treinar(tmp_path)          # o conftest esvazia as páginas
    assert ok
    assert _meta(jp)["temperatura"] == 1.0
    assert any("Sem calibração" in m for m in msgs)


def test_o_aviso_diz_o_que_fazer(tmp_path):
    _ok, _jp, msgs = _treinar(tmp_path)
    juntas = "\n".join(msgs)
    assert "calibrar_modelo.py --gravar" in juntas
    assert "rotule uma página" in juntas


# ----------------------------------------------------------------------
# Com página rotulada — o caminho que a fase abriu
# ----------------------------------------------------------------------

def test_com_paginas_o_treino_grava_a_temperatura(tmp_path, monkeypatch):
    """
    O ponto da fase. `ajustar` é substituído porque colher logits de página
    real é o que custa 8,6 s; o que este teste guarda é que o treino **usa** o
    resultado e o grava.
    """
    monkeypatch.setattr(cal, "ajustar",
                        lambda *a, **k: (2.1682, 10, 10549))
    ok, jp, msgs = _treinar(tmp_path)

    assert ok
    assert _meta(jp)["temperatura"] == pytest.approx(2.1682)
    assert any("T = 2.1682" in m for m in msgs)
    assert any("10549 caracteres" in m for m in msgs)


def test_a_regravacao_preserva_o_resto_do_metadado(tmp_path, monkeypatch):
    """
    O metadado carrega `modelo_sha256` e `classes_sha256`, que amarram o par de
    arquivos (F7.3). Remontá-lo de fora para trocar um campo é como se perde
    essa amarração sem ninguém notar.
    """
    monkeypatch.setattr(cal, "ajustar", lambda *a, **k: (2.0, 3, 300))
    _ok, jp, _msgs = _treinar(tmp_path)

    meta = _meta(jp)
    for campo in ("schema_version", "label_map", "idx_to_char", "num_classes",
                  "modelo_sha256", "classes_sha256", "treinado_em"):
        assert campo in meta, campo
    assert meta["num_classes"] == 3
    assert len(meta["modelo_sha256"]) == 64


def test_gravar_temperatura_nao_mexe_em_mais_nada(tmp_path):
    """A mesma garantia, no nível do arquivo."""
    caminho = str(tmp_path / "meta.json")
    original = {"schema_version": 2, "num_classes": 7, "temperatura": 1.0,
                "idx_to_char": {"0": "♗"}, "modelo_sha256": "f" * 64}
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(original, f, ensure_ascii=False)

    cal.gravar_temperatura(caminho, 2.5)

    depois = _meta(caminho)
    assert depois["temperatura"] == 2.5
    assert depois["idx_to_char"] == {"0": "♗"}      # inclusive o não-ASCII
    assert {k: v for k, v in depois.items() if k != "temperatura"} == \
           {k: v for k, v in original.items() if k != "temperatura"}


# ----------------------------------------------------------------------
# A calibração nunca derruba o treino
# ----------------------------------------------------------------------

def test_falha_na_calibracao_nao_perde_o_modelo(tmp_path, monkeypatch):
    """
    O modelo já está gravado quando a calibração roda. Uma exceção aqui não
    pode transformar um treino de minutos em nada — o que se perde é a
    calibração, e o aviso da F26 passa a acender por conta disso.
    """
    def explodir(*a, **k):
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(cal, "ajustar", explodir)
    ok, jp, msgs = _treinar(tmp_path)

    assert ok
    assert os.path.exists(jp)
    assert _meta(jp)["temperatura"] == 1.0
    assert any("disco cheio" in m for m in msgs)
    assert any("está gravado e vale" in m for m in msgs)


def test_calibrar_desligado_nem_tenta(tmp_path, monkeypatch):
    """
    `calibrar=False` existe para quem mede o laço de treino e não quer o custo
    — é o que a suíte usava antes de o `conftest` esvaziar as páginas.
    """
    chamou = []
    monkeypatch.setattr(cal, "ajustar",
                        lambda *a, **k: chamou.append(1) or (2.0, 1, 1))
    ok, jp, msgs = _treinar(tmp_path, calibrar=False)

    assert ok and not chamou
    assert _meta(jp)["temperatura"] == 1.0
    assert not any("Calibrando" in m for m in msgs)


# ----------------------------------------------------------------------
# O serviço solta o preditor velho
# ----------------------------------------------------------------------

def test_treinar_solta_o_preditor_anterior(tmp_path, monkeypatch):
    """
    `load_predictor` devolve `True` sem reler quando já há um carregado. Sem
    soltar o antigo, a sessão seguiria usando os pesos velhos depois do treino
    — e a ressalva da F26 seria a do arquivo que acabou de ser substituído.
    """
    from core.services.learning_service import LearningService

    dados = _base(tmp_path)
    svc = LearningService(data_dir=dados,
                          model_path=str(tmp_path / "m.pth"),
                          meta_path=str(tmp_path / "m.json"))
    svc._predictor = object()          # um preditor "carregado" de antes

    assert svc.train_neural(epochs=1, validar=False)
    assert svc._predictor is None


# ----------------------------------------------------------------------
# A borda do intervalo, que é onde o ajuste diz "não sei"
# ----------------------------------------------------------------------

def test_temperatura_na_borda_e_recusada(tmp_path, monkeypatch):
    """
    Automatizar a calibração tirou o humano que via as tabelas e julgava. O que
    ele pegaria a olho é o ajuste que para na borda: não é temperatura medida, é
    o fim da régua, e acontece quando o modelo não sabe ler aquelas páginas.

    Gravá-la seria pior que não calibrar — T no teto esmaga toda a confiança e
    nada mais passaria pelo `NEURAL_THRESHOLD`.
    """
    monkeypatch.setattr(cal, "ajustar",
                        lambda *a, **k: (cal.LIMITES[1], 10, 2224))
    ok, jp, msgs = _treinar(tmp_path)

    assert ok
    assert _meta(jp)["temperatura"] == 1.0
    assert any("parou na borda" in m for m in msgs)


def test_a_borda_de_baixo_tambem(tmp_path, monkeypatch):
    monkeypatch.setattr(cal, "ajustar",
                        lambda *a, **k: (cal.LIMITES[0], 10, 2224))
    _ok, jp, msgs = _treinar(tmp_path)
    assert _meta(jp)["temperatura"] == 1.0
    assert any("parou na borda" in m for m in msgs)


def test_no_limite_reconhece_as_duas_pontas_e_o_meio():
    assert cal.no_limite(cal.LIMITES[0])
    assert cal.no_limite(cal.LIMITES[1])
    assert not cal.no_limite(2.1682)
    assert not cal.no_limite(1.0)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
