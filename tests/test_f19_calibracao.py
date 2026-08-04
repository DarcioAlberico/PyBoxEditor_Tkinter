"""
Testes da F1.9 — calibração da confiança.

O que esta fase descobriu, e que os testes abaixo fixam:

1. **No split de validação não há o que calibrar** — ECE de 0,0003. A
   miscalibração só existe em página real. Calibrar no split, que era o proposto,
   daria T ≈ 1 e não mudaria nada.
2. **Calibrar não faz o filtro achar mais erro.** A temperatura preserva a ordem
   das confianças, então a AUROC entre certo e errado não muda. É a propriedade
   mais importante daqui, e a que impede de vender calibração como melhoria de
   triagem: `test_temperatura_nao_muda_o_poder_de_separacao`.

Rodar sem pytest:      python tests/test_f19_calibracao.py
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core import calibracao


def _logits_de_confianca(confiancas, acertou, num_classes=5, semente=7):
    """
    Logits sintéticos com a confiança pedida em cada amostra.

    Monta a classe 0 como vencedora com probabilidade `c` e espalha o resto; se
    `acertou` for falso, a máscara de aceitáveis aponta para outra classe.
    """
    rng = np.random.RandomState(semente)
    n = len(confiancas)
    logits = np.zeros((n, num_classes), dtype=np.float64)
    aceitaveis = np.zeros((n, num_classes), dtype=bool)

    for i, c in enumerate(confiancas):
        c = min(max(float(c), 1.0 / num_classes + 1e-6), 1 - 1e-9)
        resto = (1.0 - c) / (num_classes - 1)
        probs = np.full(num_classes, resto)
        probs[0] = c
        logits[i] = np.log(probs)
        aceitaveis[i, 0 if acertou[i] else 1] = True

    return logits, aceitaveis


# ----------------------------------------------------------------------
# ECE
# ----------------------------------------------------------------------

def test_ece_zero_quando_calibrado():
    """80% de confiança em 100 amostras com 80 acertos: desvio nenhum."""
    conf = np.full(100, 0.8)
    acertou = np.array([True] * 80 + [False] * 20)
    assert calibracao.ece(conf, acertou) < 1e-9


def test_ece_positivo_quando_superconfiante():
    conf = np.full(100, 1.0)
    acertou = np.array([True] * 80 + [False] * 20)
    assert abs(calibracao.ece(conf, acertou) - 0.2) < 1e-9


def test_ece_pesa_pela_quantidade_da_faixa():
    """
    Um desvio grande numa faixa quase vazia vale pouco.

    990 amostras a 0,9 com 90% de acerto (calibradas, contribuem zero) e 10
    amostras a 0,1 que acertam todas — 90 pontos de desvio em 1% da massa.
    """
    conf = np.concatenate([np.full(990, 0.9), np.full(10, 0.1)])
    acertou = np.concatenate([np.ones(891, bool), np.zeros(99, bool),
                              np.ones(10, bool)])
    assert calibracao.ece(conf, acertou) < 0.02


def test_ece_de_lista_vazia_nao_explode():
    assert np.isnan(calibracao.ece([], []))


# ----------------------------------------------------------------------
# AUROC e a invariância que decide o desenho da fase
# ----------------------------------------------------------------------

def test_auroc_separacao_perfeita_e_aleatoria():
    conf = np.array([0.1, 0.2, 0.8, 0.9])
    assert calibracao.auroc(conf, np.array([False, False, True, True])) == 1.0
    assert calibracao.auroc(conf, np.array([True, True, False, False])) == 0.0


def test_auroc_com_empates_usa_rank_medio():
    """Confiança toda igual não separa nada, e isso é 0,5 — não 0 nem 1."""
    conf = np.full(6, 0.9)
    acertou = np.array([True, True, True, False, False, False])
    assert abs(calibracao.auroc(conf, acertou) - 0.5) < 1e-9


def test_auroc_sem_erros_ou_sem_acertos_e_indefinida():
    assert np.isnan(calibracao.auroc([0.9, 0.8], [True, True]))
    assert np.isnan(calibracao.auroc([0.9, 0.8], [False, False]))


def test_temperatura_nao_muda_o_poder_de_separacao():
    """
    **A descoberta que muda o que esta fase pode prometer.**

    Reescalonar por temperatura mexe no valor da confiança, não na ordem entre
    as amostras. Como triagem é "olhe os N mais duvidosos", o que ela consome é
    a ordem — então calibrar não faz o filtro da F3.3 achar um erro a mais.
    Medido nas 8 páginas rotuladas, a AUROC vai de 0,845 (T=1) a 0,861 (T=4);
    o que muda de verdade é onde um limiar fixo cai.
    """
    rng = np.random.RandomState(11)
    logits = rng.normal(0, 4, size=(500, 12))
    aceitaveis = np.zeros((500, 12), dtype=bool)
    aceitaveis[np.arange(500), rng.randint(0, 12, 500)] = True

    base = calibracao.auroc(*calibracao.confianca_e_acerto(logits, aceitaveis, 1.0))
    for T in (0.5, 2.0, 4.0, 8.0):
        conf, ok = calibracao.confianca_e_acerto(logits, aceitaveis, T)
        assert abs(calibracao.auroc(conf, ok) - base) < 0.05, \
            f"a temperatura {T} mudou a separação — a premissa da fase caiu"


def test_temperatura_nao_muda_a_leitura():
    """Dividir os logits não muda quem vence, então nenhum caractere muda."""
    rng = np.random.RandomState(3)
    logits = rng.normal(0, 3, size=(200, 9))
    aceitaveis = np.zeros((200, 9), dtype=bool)
    aceitaveis[np.arange(200), 0] = True

    _, ok1 = calibracao.confianca_e_acerto(logits, aceitaveis, 1.0)
    for T in (0.6, 2.5, 7.0):
        _, ok = calibracao.confianca_e_acerto(logits, aceitaveis, T)
        assert (ok == ok1).all()


def test_temperatura_alta_baixa_a_confianca():
    rng = np.random.RandomState(5)
    logits = rng.normal(0, 5, size=(300, 7))
    aceitaveis = np.zeros((300, 7), dtype=bool)
    aceitaveis[np.arange(300), 0] = True

    c1, _ = calibracao.confianca_e_acerto(logits, aceitaveis, 1.0)
    c2, _ = calibracao.confianca_e_acerto(logits, aceitaveis, 3.0)
    assert c2.mean() < c1.mean()


# ----------------------------------------------------------------------
# Ajuste da temperatura
# ----------------------------------------------------------------------

def test_ajuste_corrige_superconfianca():
    """Modelo que diz 99% e acerta 80% precisa de temperatura acima de 1."""
    n = 600
    acertou = np.array([True] * int(n * 0.8) + [False] * (n - int(n * 0.8)))
    logits, aceitaveis = _logits_de_confianca(np.full(n, 0.99), acertou)

    T = calibracao.ajustar_temperatura(logits, aceitaveis)
    assert T > 1.0, f"não aumentou a temperatura (T={T})"

    antes = calibracao.ece(*calibracao.confianca_e_acerto(logits, aceitaveis, 1.0))
    depois = calibracao.ece(*calibracao.confianca_e_acerto(logits, aceitaveis, T))
    assert depois < antes


def test_ajuste_deixa_quieto_o_que_ja_esta_calibrado():
    n = 600
    acertou = np.array([True] * int(n * 0.8) + [False] * (n - int(n * 0.8)))
    logits, aceitaveis = _logits_de_confianca(np.full(n, 0.8), acertou)

    T = calibracao.ajustar_temperatura(logits, aceitaveis)
    assert 0.8 < T < 1.3, f"mexeu num modelo já calibrado (T={T})"


def test_criterio_invalido():
    logits = np.zeros((4, 3))
    aceitaveis = np.zeros((4, 3), dtype=bool)
    aceitaveis[:, 0] = True
    try:
        calibracao.ajustar_temperatura(logits, aceitaveis, criterio="xpto")
    except ValueError as e:
        assert "critério" in str(e)
    else:
        raise AssertionError("aceitou critério inválido")


def test_nll_soma_a_massa_das_classes_aceitaveis():
    """
    Duas classes aceitáveis valem a soma das probabilidades, não a maior.

    É o caso real: o livro imprime a figurina e quem rotulou escreveu a letra,
    então `N` e `♘` são os dois leitura correta de um mesmo desenho.
    """
    logits = np.log(np.array([[0.5, 0.3, 0.2]]))
    uma = np.array([[True, False, False]])
    duas = np.array([[True, True, False]])

    assert abs(calibracao.nll(logits, uma, 1.0) - (-np.log(0.5))) < 1e-9
    assert abs(calibracao.nll(logits, duas, 1.0) - (-np.log(0.8))) < 1e-9


# ----------------------------------------------------------------------
# Curva de triagem — a que responde onde pôr o limiar
# ----------------------------------------------------------------------

def test_curva_de_triagem_conta_certo():
    conf = np.array([0.4, 0.6, 0.95, 0.99])
    acertou = np.array([False, True, False, True])

    pontos = {p["corte"]: p for p in
              calibracao.curva_de_triagem(conf, acertou, cortes=(0.5, 0.97))}

    p = pontos[0.5]
    assert p["revisado_pct"] == 25.0            # só o 0,4
    assert p["erros_pegos_pct"] == 50.0         # 1 dos 2 erros
    assert p["erros_restantes"] == 1

    p = pontos[0.97]
    assert p["erros_pegos_pct"] == 100.0
    assert p["erros_restantes"] == 0


def test_curva_de_triagem_e_monotona():
    rng = np.random.RandomState(2)
    conf = rng.uniform(0, 1, 500)
    acertou = rng.uniform(0, 1, 500) < conf

    curva = calibracao.curva_de_triagem(conf, acertou)
    for a, b in zip(curva, curva[1:]):
        assert b["revisado_pct"] >= a["revisado_pct"]
        assert b["erros_pegos_pct"] >= a["erros_pegos_pct"]
        assert b["erros_restantes"] <= a["erros_restantes"]


# ----------------------------------------------------------------------
# O predictor lê a temperatura do metadado
# ----------------------------------------------------------------------

def _modelo_falso(pasta, temperatura=None, num_classes=3):
    import torch
    from core.neural_model import SimpleCNN

    caminho_modelo = os.path.join(pasta, "m.pth")
    caminho_meta = os.path.join(pasta, "m.json")
    torch.save(SimpleCNN(num_classes).state_dict(), caminho_modelo)

    meta = {"label_map": {"lower_a": 0, "lower_b": 1, "lower_c": 2},
            "idx_to_char": {"0": "a", "1": "b", "2": "c"},
            "num_classes": num_classes}
    if temperatura is not None:
        meta["temperatura"] = temperatura
    with open(caminho_meta, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return caminho_modelo, caminho_meta


def test_predictor_usa_temperatura_do_meta():
    from core.neural_trainer import NeuralPredictor

    with tempfile.TemporaryDirectory() as pasta:
        m, j = _modelo_falso(pasta, temperatura=2.5)
        p = NeuralPredictor(m, j)
        assert p.load()
        assert abs(p.temperatura - 2.5) < 1e-9


def test_predictor_sem_temperatura_fica_neutro():
    """Modelo gravado antes da F1.9 não tem o campo — 1,0 é o único padrão seguro."""
    from core.neural_trainer import NeuralPredictor

    with tempfile.TemporaryDirectory() as pasta:
        m, j = _modelo_falso(pasta, temperatura=None)
        p = NeuralPredictor(m, j)
        assert p.load()
        assert p.temperatura == 1.0


def test_predictor_ignora_temperatura_invalida():
    from core.neural_trainer import NeuralPredictor

    for ruim in ("abc", 0, -3, None):
        with tempfile.TemporaryDirectory() as pasta:
            m, j = _modelo_falso(pasta, temperatura=ruim)
            p = NeuralPredictor(m, j)
            assert p.load()
            assert p.temperatura == 1.0, f"aceitou temperatura {ruim!r}"


def test_temperatura_nao_muda_o_caractere_lido():
    """A leitura tem de ser a mesma; só a confiança muda."""
    from core.neural_trainer import NeuralPredictor

    rng = np.random.RandomState(1)
    amostras = [rng.randint(0, 256, (20, 20)).astype(np.uint8) for _ in range(25)]

    with tempfile.TemporaryDirectory() as pasta:
        m, j = _modelo_falso(pasta, temperatura=1.0)
        p = NeuralPredictor(m, j)
        assert p.load()

        neutro = [p.predict(a) for a in amostras]
        p.temperatura = 3.0
        quente = [p.predict(a) for a in amostras]

    assert [c for c, _ in neutro] == [c for c, _ in quente]
    assert all(q <= n + 1e-9 for (_, n), (_, q) in zip(neutro, quente))


def test_retreino_zera_a_temperatura_no_meta():
    """
    Uma temperatura é ajustada para UM conjunto de pesos.

    Herdar a do modelo anterior aplicaria uma correção medida sobre outra rede —
    pior que não calibrar. O `gravar_modelo` do treino grava 1,0 de propósito.
    """
    import inspect

    from core.neural_trainer import NeuralTrainer

    fonte = inspect.getsource(NeuralTrainer.train)
    assert '"temperatura": 1.0' in fonte, \
        "o treino deixou de zerar a temperatura ao gravar o metadado"


# ----------------------------------------------------------------------
# Execução direta
# ----------------------------------------------------------------------

def _main():
    testes = [(n, o) for n, o in sorted(globals().items())
              if n.startswith("test_") and callable(o)]
    falhas = []
    for nome, fn in testes:
        try:
            fn()
            print(f"  PASS  {nome}")
        except Exception as e:
            falhas.append(nome)
            print(f"  FALHA {nome}\n          {type(e).__name__}: {e}")
    print(f"\n{len(testes) - len(falhas)}/{len(testes)} testes passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(_main())
