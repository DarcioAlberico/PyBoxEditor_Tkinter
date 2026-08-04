"""
Testes da F1.3 — split de validação, early stopping e relatório.

O defeito: a acurácia exibida era calculada sobre as próprias amostras de treino,
já aumentadas, e o "melhor modelo" era escolhido pela *training loss* — critério
que seleciona exatamente o ponto de maior overfitting. Quanto mais o modelo
decorava, melhor ele parecia.

Três invariantes de regressão:

1. **O checkpoint é pela perda de validação.** Um modelo que melhora no treino e
   piora na validação não pode sobrescrever o gravado.
2. **Classe pequena demais não é dividida, e isso aparece.** Uma acurácia de
   validação que ignora 24 das 103 classes em silêncio seria o mesmo defeito de
   novo, com outra roupa.
3. **A avaliação não usa augmentation.** É imagem limpa que chega na predição, e
   medir sobre imagem sorteada tornaria o número irreprodutível.

Rodar sem pytest:      python tests/test_f13_validacao.py
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import torch
from PIL import Image

from core.avaliacao import (MIN_PARA_DIVIDIR, Avaliacao, avaliar,
                            dividir_estratificado, pares_confusos,
                            piores_classes, salvar_amostras_erradas)
from core.neural_model import SimpleCNN
from core.neural_trainer import CharDataset, NeuralTrainer


def _base(raiz, conteudo):
    """{pasta: (qtd, região preenchida)} — desenhos distinguíveis por classe."""
    for pasta, (n, regiao) in conteudo.items():
        d = os.path.join(raiz, pasta)
        os.makedirs(d, exist_ok=True)
        for i in range(n):
            img = np.full((32, 32), 255, dtype=np.uint8)
            img[regiao] = 0
            Image.fromarray(img).save(os.path.join(d, f"{i:04d}.png"))
    return raiz


QUADRADO = (slice(8, 24), slice(8, 24))
BARRA = (slice(4, 28), slice(12, 20))
FAIXA = (slice(10, 22), slice(4, 28))


# ----------------------------------------------------------------------
# Split estratificado
# ----------------------------------------------------------------------

def test_split_respeita_as_proporcoes():
    labels = [0] * 1000 + [1] * 500
    d = dividir_estratificado(labels, 2)
    assert len(d.validacao) == 225      # 15% de 1000 + 15% de 500
    assert len(d.teste) == 75           # 5%
    assert len(d.treino) == 1200
    assert len(d.treino) + len(d.validacao) + len(d.teste) == 1500


def test_split_e_estratificado_e_nao_global():
    """
    Numa base de 25.075:1, um sorteio global deixaria classes inteiras fora da
    validação por acaso. A proporção é aplicada dentro de cada classe.
    """
    labels = [0] * 2000 + [1] * 10
    d = dividir_estratificado(labels, 2)
    y = np.array(labels)
    assert (y[d.validacao] == 1).sum() >= 1
    assert (y[d.teste] == 1).sum() >= 0
    assert (y[d.treino] == 1).sum() >= 1


def test_classe_pequena_vai_inteira_para_o_treino():
    """Tirar 15% de uma classe de 3 deixa o treino com 2 para medir mal 1."""
    labels = [0] * 500 + [1] * 3
    d = dividir_estratificado(labels, 2)
    y = np.array(labels)
    assert (y[d.treino] == 1).sum() == 3
    assert (y[d.validacao] == 1).sum() == 0
    assert d.sem_validacao == [1]


def test_split_nao_esvazia_o_treino_de_nenhuma_classe():
    for n in range(MIN_PARA_DIVIDIR, 40):
        labels = [0] * 500 + [1] * n
        d = dividir_estratificado(labels, 2)
        y = np.array(labels)
        assert (y[d.treino] == 1).sum() >= 1, f"n={n} zerou o treino da classe"


def test_split_e_reprodutivel():
    labels = [0] * 300 + [1] * 120 + [2] * 40
    a = dividir_estratificado(labels, 3, semente=7)
    b = dividir_estratificado(labels, 3, semente=7)
    c = dividir_estratificado(labels, 3, semente=8)
    assert np.array_equal(a.validacao, b.validacao)
    assert not np.array_equal(a.validacao, c.validacao)


def test_split_nao_repete_indice_entre_conjuntos():
    labels = [0] * 300 + [1] * 120 + [2] * 7
    d = dividir_estratificado(labels, 3)
    todos = np.concatenate([d.treino, d.validacao, d.teste])
    assert len(set(todos.tolist())) == len(todos) == len(labels)


# ----------------------------------------------------------------------
# Avaliação
# ----------------------------------------------------------------------

def _modelo_e_dados(n_por_classe=20):
    with tempfile.TemporaryDirectory() as tmp:
        pass
    dados = np.zeros((2 * n_por_classe, 32, 32), dtype=np.uint8)
    dados[:] = 255
    dados[:n_por_classe][:, 8:24, 8:24] = 0
    dados[n_por_classe:][:, 4:28, 12:20] = 0
    labels = [0] * n_por_classe + [1] * n_por_classe
    return SimpleCNN(2), dados, labels


def test_avaliacao_conta_acertos_por_classe():
    torch.manual_seed(0)
    model, dados, labels = _modelo_e_dados()
    av = avaliar(model, dados, labels, np.arange(len(labels)), 2)
    assert av.totais.tolist() == [20, 20]
    assert av.acertos.sum() == av.matriz.trace()
    assert 0.0 <= av.acuracia <= 100.0
    assert len(av.erros) == int(av.totais.sum() - av.acertos.sum())


def test_avaliacao_nao_usa_augmentation():
    """Duas chamadas seguidas têm que dar exatamente o mesmo número."""
    torch.manual_seed(0)
    model, dados, labels = _modelo_e_dados()
    idx = np.arange(len(labels))
    a = avaliar(model, dados, labels, idx, 2)
    b = avaliar(model, dados, labels, idx, 2)
    assert a.acuracia == b.acuracia and a.perda == b.perda


def test_avaliacao_devolve_o_modelo_ao_modo_anterior():
    """Avaliar no meio do treino não pode deixar o dropout desligado."""
    model, dados, labels = _modelo_e_dados()
    model.train()
    avaliar(model, dados, labels, np.arange(len(labels)), 2)
    assert model.training
    model.eval()
    avaliar(model, dados, labels, np.arange(len(labels)), 2)
    assert not model.training


def test_conjunto_vazio_nao_quebra():
    model, dados, labels = _modelo_e_dados()
    av = avaliar(model, dados, labels, np.array([], dtype=np.int64), 2)
    assert np.isnan(av.acuracia)


def test_recall_macro_difere_da_acuracia_em_base_desbalanceada():
    """É a diferença que a F1.2 mediu; aqui só se trava que são coisas distintas."""
    av = Avaliacao(perda=0.0, acuracia=0.0, recall_macro=0.0,
                   acertos=np.array([100, 0]), totais=np.array([100, 10]),
                   matriz=np.array([[100, 0], [10, 0]]), erros=[])
    r = av.recall_por_classe()
    assert r.tolist() == [100.0, 0.0]
    assert av.classes_zeradas() == 1


def test_piores_classes_vem_ordenado():
    av = Avaliacao(0.0, 0.0, 0.0,
                   acertos=np.array([10, 5, 9]), totais=np.array([10, 10, 10]),
                   matriz=np.eye(3, dtype=np.int64), erros=[])
    piores = piores_classes(av, {0: "a", 1: "b", 2: "c"}, quantas=3)
    assert [p[0] for p in piores] == ["b", "c", "a"]


def test_pares_confusos_ignora_a_diagonal():
    m = np.array([[90, 10, 0], [3, 95, 2], [0, 0, 100]], dtype=np.int64)
    av = Avaliacao(0.0, 0.0, 0.0, np.array([90, 95, 100]),
                   np.array([100, 100, 100]), m, [])
    pares = pares_confusos(av, {0: "a", 1: "b", 2: "c"})
    assert pares[0] == ("a", "b", 10)
    assert all(e != p for e, p, _ in pares)


def test_amostras_erradas_vao_para_disco():
    with tempfile.TemporaryDirectory() as tmp:
        dados = np.full((4, 32, 32), 255, dtype=np.uint8)
        av = Avaliacao(0.0, 0.0, 0.0, np.array([0, 0]), np.array([2, 2]),
                       np.zeros((2, 2), dtype=np.int64),
                       erros=[(0, 0, 1), (1, 0, 1), (2, 1, 0)])
        n = salvar_amostras_erradas(tmp, dados, av, {0: "a", 1: "b"})
        assert n == 3
        assert os.path.isdir(os.path.join(tmp, "lower_a_virou_lower_b"))
        assert os.path.isdir(os.path.join(tmp, "lower_b_virou_lower_a"))


def test_amostras_erradas_tem_teto():
    with tempfile.TemporaryDirectory() as tmp:
        dados = np.full((500, 32, 32), 255, dtype=np.uint8)
        av = Avaliacao(0.0, 0.0, 0.0, np.array([0, 0]), np.array([500, 0]),
                       np.zeros((2, 2), dtype=np.int64),
                       erros=[(i, 0, 1) for i in range(500)])
        assert salvar_amostras_erradas(tmp, dados, av, {0: "a", 1: "b"},
                                       maximo=25) == 25


# ----------------------------------------------------------------------
# Treino: checkpoint, early stopping e relatório
# ----------------------------------------------------------------------

def test_treino_grava_relatorio_com_numeros_de_validacao():
    with tempfile.TemporaryDirectory() as tmp:
        dados = _base(os.path.join(tmp, "d"),
                      {"lower_a": (120, QUADRADO), "lower_b": (80, BARRA)})
        msgs = []
        assert NeuralTrainer(dados, os.path.join(tmp, "m.pth"),
                             os.path.join(tmp, "m.json")).train(
            epochs=2, callback=msgs.append)

        rel = os.path.join(tmp, "relatorio_treino.txt")
        assert os.path.exists(rel)
        texto = open(rel, encoding="utf-8").read()
        for esperado in ["VALIDAÇÃO", "recall macro", "PIORES CLASSES",
                         "CONFUSÕES MAIS FREQUENTES", "POR EPOCH"]:
            assert esperado in texto, esperado

        dados_json = json.load(open(os.path.join(tmp, "relatorio_treino.json"),
                                    encoding="utf-8"))
        assert dados_json["divisao"]["validacao"] > 0
        assert len(dados_json["historico"]) == 2
        assert any("val acc" in m for m in msgs), msgs


def test_relatorio_nomeia_as_classes_sem_validacao():
    """Não dá para deixar isso implícito: são classes fora de todo número."""
    with tempfile.TemporaryDirectory() as tmp:
        dados = _base(os.path.join(tmp, "d"),
                      {"lower_a": (120, QUADRADO), "lower_b": (80, BARRA),
                       "upper_Q": (2, FAIXA)})
        msgs = []
        NeuralTrainer(dados, os.path.join(tmp, "m.pth"),
                      os.path.join(tmp, "m.json")).train(epochs=1,
                                                         callback=msgs.append)
        texto = open(os.path.join(tmp, "relatorio_treino.txt"),
                     encoding="utf-8").read()
        assert "Classes SEM validação (1)" in texto
        assert "'Q'" in texto
        assert any("pequenas demais para dividir" in m for m in msgs), msgs


def test_checkpoint_e_pela_perda_de_validacao():
    """
    O critério antigo era a perda de TREINO, que só cai. Com ele, a última
    epoch era sempre a "melhor" — o ponto de maior overfitting.
    """
    with tempfile.TemporaryDirectory() as tmp:
        dados = _base(os.path.join(tmp, "d"),
                      {"lower_a": (120, QUADRADO), "lower_b": (80, BARRA)})
        NeuralTrainer(dados, os.path.join(tmp, "m.pth"),
                      os.path.join(tmp, "m.json")).train(epochs=4)
        d = json.load(open(os.path.join(tmp, "relatorio_treino.json"),
                           encoding="utf-8"))
        hist = d["historico"]
        melhor = min(hist, key=lambda h: h["perda_val"])["epoch"]
        texto = open(os.path.join(tmp, "relatorio_treino.txt"),
                     encoding="utf-8").read()
        assert f"Melhor epoch: {melhor} de" in texto

        # E a perda de treino não é o critério: se fosse, a melhor seria a última.
        melhor_por_treino = min(hist, key=lambda h: h["perda_treino"])["epoch"]
        if melhor_por_treino != melhor:
            assert f"Melhor epoch: {melhor_por_treino} de" not in texto


def test_modelo_gravado_e_o_da_melhor_epoch():
    with tempfile.TemporaryDirectory() as tmp:
        dados = _base(os.path.join(tmp, "d"),
                      {"lower_a": (120, QUADRADO), "lower_b": (80, BARRA)})
        mp = os.path.join(tmp, "m.pth")
        NeuralTrainer(dados, mp, os.path.join(tmp, "m.json")).train(epochs=3)

        ds = CharDataset(dados, augment=False)
        rotulos = np.asarray(ds.labels)
        div = dividir_estratificado(rotulos, 2)
        model = SimpleCNN(2)
        model.load_state_dict(torch.load(mp, map_location="cpu"))
        av = avaliar(model, ds.data, rotulos, div.validacao, 2)

        d = json.load(open(os.path.join(tmp, "relatorio_treino.json"),
                           encoding="utf-8"))
        assert abs(av.acuracia - d["validacao"]["acuracia"]) < 1e-6
        assert abs(av.perda - d["validacao"]["perda"]) < 1e-4


def test_early_stopping_para_antes_do_fim():
    """Paciência 1 numa base trivial: para assim que a validação não melhora."""
    with tempfile.TemporaryDirectory() as tmp:
        dados = _base(os.path.join(tmp, "d"),
                      {"lower_a": (120, QUADRADO), "lower_b": (80, BARRA)})
        msgs = []
        NeuralTrainer(dados, os.path.join(tmp, "m.pth"),
                      os.path.join(tmp, "m.json")).train(
            epochs=30, callback=msgs.append, paciencia=1)
        d = json.load(open(os.path.join(tmp, "relatorio_treino.json"),
                           encoding="utf-8"))
        assert len(d["historico"]) < 30
        assert any("Early stopping" in m for m in msgs), msgs


def test_conjunto_de_teste_nao_entra_no_treino_nem_na_validacao():
    with tempfile.TemporaryDirectory() as tmp:
        dados = _base(os.path.join(tmp, "d"),
                      {"lower_a": (200, QUADRADO), "lower_b": (200, BARRA)})
        NeuralTrainer(dados, os.path.join(tmp, "m.pth"),
                      os.path.join(tmp, "m.json")).train(epochs=1)
        d = json.load(open(os.path.join(tmp, "relatorio_treino.json"),
                           encoding="utf-8"))
        assert d["divisao"]["teste"] == 20
        assert "teste" in d
        texto = open(os.path.join(tmp, "relatorio_treino.txt"),
                     encoding="utf-8").read()
        assert "não usado em nenhuma decisão do treino" in texto


def test_base_sem_validacao_possivel_avisa_e_treina():
    """
    Base recém-começada, toda classe com poucas amostras. Treinar ainda tem que
    funcionar — mas o usuário precisa saber que voltou ao critério ruim.
    """
    with tempfile.TemporaryDirectory() as tmp:
        dados = _base(os.path.join(tmp, "d"),
                      {"lower_a": (3, QUADRADO), "lower_b": (3, BARRA)})
        msgs = []
        assert NeuralTrainer(dados, os.path.join(tmp, "m.pth"),
                             os.path.join(tmp, "m.json")).train(
            epochs=1, callback=msgs.append)
        assert os.path.exists(os.path.join(tmp, "m.pth"))
        assert any("base pequena demais" in m.lower() for m in msgs), msgs
        assert not os.path.exists(os.path.join(tmp, "relatorio_treino.txt"))


def test_cancelar_mantem_a_melhor_epoch_gravada():
    with tempfile.TemporaryDirectory() as tmp:
        dados = _base(os.path.join(tmp, "d"),
                      {"lower_a": (120, QUADRADO), "lower_b": (80, BARRA)})
        estado = {"epochs": 0}

        def parar():
            estado["epochs"] += 1
            return estado["epochs"] > 2      # deixa duas epochs rodarem

        msgs = []
        assert NeuralTrainer(dados, os.path.join(tmp, "m.pth"),
                             os.path.join(tmp, "m.json")).train(
            epochs=20, callback=msgs.append, should_stop=parar)
        assert os.path.exists(os.path.join(tmp, "m.pth"))
        assert any("interrompido" in m for m in msgs), msgs
        d = json.load(open(os.path.join(tmp, "relatorio_treino.json"),
                           encoding="utf-8"))
        assert len(d["historico"]) == 2


def test_cancelar_antes_da_primeira_epoch_nao_grava_modelo():
    with tempfile.TemporaryDirectory() as tmp:
        dados = _base(os.path.join(tmp, "d"),
                      {"lower_a": (30, QUADRADO), "lower_b": (30, BARRA)})
        mp = os.path.join(tmp, "m.pth")
        ok = NeuralTrainer(dados, mp, os.path.join(tmp, "m.json")).train(
            epochs=5, should_stop=lambda: True)
        assert ok is False
        assert not os.path.exists(mp)


def test_pesos_do_sampler_usam_so_o_conjunto_de_treino():
    """
    Contar a base inteira para pesar o sorteio contaria amostras que o modelo
    não vai ver — e o peso de uma classe rara ficaria menor do que deveria.
    """
    with tempfile.TemporaryDirectory() as tmp:
        raiz = _base(os.path.join(tmp, "d"),
                     {"lower_a": (100, QUADRADO), "lower_b": (20, BARRA)})
        ds = CharDataset(raiz, augment=False)
        rotulos = np.asarray(ds.labels)
        div = dividir_estratificado(rotulos, 2)
        from core.neural_trainer import contar_por_classe
        no_treino = contar_por_classe(rotulos[div.treino], 2)
        assert no_treino.sum() == len(div.treino)
        assert list(no_treino) != list(ds.contagens)


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
