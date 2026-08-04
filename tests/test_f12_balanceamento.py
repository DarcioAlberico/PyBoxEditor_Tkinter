"""
Testes da F1.2 — desbalanceamento da base de treino.

A base real vai de 25.075 amostras (`lower_e`) a 1 (`upper_X`). Com sorteio
uniforme, as 10 classes mais comuns ocupam 79,6% de cada epoch, e medido com
holdout o recall macro fica em 88,7% contra 98,6% de acurácia global.

Dois invariantes aqui são de regressão, e valem mais que os números:

1. **O dataset guarda o original, não as cópias aumentadas.** A versão anterior
   materializava 8 variantes de cada amostra em float32 no construtor — 4,89 GB
   para a base real. Se alguém reintroduzir isso, o treino volta a não caber na
   memória e o sampler volta a sortear sempre as mesmas 9 imagens.

2. **Classe rara é reportada, não excluída.** A SPEC §5.3 propunha excluir
   classes abaixo de 10 amostras. Nesta base isso apagaria 'K', 'Q' e os
   símbolos de anotação de xadrez (± ∓ ∞ □ ■ △ ▼) — vocabulário do domínio.

Rodar sem pytest:      python tests/test_f12_balanceamento.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import torch
from PIL import Image

from core.neural_trainer import (MIN_AMOSTRAS_POR_CLASSE, CharDataset,
                                 NeuralTrainer, contar_por_classe,
                                 pesos_de_amostragem)


def _base(tmp, conteudo, desenho=None):
    """
    Base de treino de mentira: {pasta: qtd de PNGs}.

    Grava com PIL e não com cv2.imwrite — o OpenCV não escreve em caminho
    não-ASCII no Windows e devolve False sem levantar (ver F1.4).
    """
    for pasta, n in conteudo.items():
        d = os.path.join(tmp, pasta)
        os.makedirs(d, exist_ok=True)
        for i in range(n):
            img = (desenho(pasta, i) if desenho else
                   np.full((32, 32), 255, dtype=np.uint8))
            if desenho is None:
                img[8:24, 8:24] = 0
            Image.fromarray(img).save(os.path.join(d, f"{i:04d}.png"))
    return tmp


def _fracao_do_epoch(pesos, labels, num_classes):
    """Fatia de um epoch que cada classe ocupa, dados os pesos de sorteio."""
    p = np.asarray(pesos, dtype=np.float64)
    p = p / p.sum()
    labels = np.asarray(labels)
    return np.array([p[labels == k].sum() for k in range(num_classes)])


# ----------------------------------------------------------------------
# Pesos de amostragem
# ----------------------------------------------------------------------

def test_modo_nenhum_da_peso_igual():
    labels = [0] * 100 + [1] * 5
    cont = contar_por_classe(labels, 2)
    w = pesos_de_amostragem(cont, labels, modo="nenhum")
    assert len(set(np.round(w, 12))) == 1


def test_inverso_iguala_a_fatia_das_classes():
    """É o ponto do balanceamento: classe rara e classe comum pesam o mesmo."""
    labels = [0] * 1000 + [1] * 10
    cont = contar_por_classe(labels, 2)
    frac = _fracao_do_epoch(pesos_de_amostragem(cont, labels, modo="inverso", teto=0),
                            labels, 2)
    assert abs(frac[0] - 0.5) < 1e-9
    assert abs(frac[1] - 0.5) < 1e-9


def test_sqrt_fica_entre_nenhum_e_inverso():
    labels = [0] * 1000 + [1] * 10
    cont = contar_por_classe(labels, 2)
    raras = {m: _fracao_do_epoch(
        pesos_de_amostragem(cont, labels, modo=m, teto=0), labels, 2)[1]
        for m in ("nenhum", "sqrt", "inverso")}
    assert raras["nenhum"] < raras["sqrt"] < raras["inverso"]


def test_teto_limita_a_repeticao_por_amostra():
    """
    Sem teto, o peso inverso puro faz a única amostra de uma classe ser sorteada
    ~1200 vezes por epoch na base real: o modelo decora um PNG.
    """
    labels = [0] * 5000 + [1]
    cont = contar_por_classe(labels, 2)
    n = len(labels)

    sem = pesos_de_amostragem(cont, labels, modo="inverso", teto=0)
    rep_sem = sem[-1] / sem.sum() * n
    assert rep_sem > 1000, f"esperava repetição alta sem teto, veio {rep_sem:.0f}"

    com = pesos_de_amostragem(cont, labels, modo="inverso", teto=50)
    rep_com = com[-1] / com.sum() * n
    assert 49.0 <= rep_com <= 50.01, f"teto de 50 virou {rep_com:.1f}"


def test_teto_e_exato_e_nao_so_aproximado():
    """
    Cortar os pesos que estouram o teto reduz a soma e empurra os outros para
    cima. Uma passada só deixava o teto efetivo em 72 quando se pedia 50 — daí
    a iteração.
    """
    labels = [0] * 20000 + [1] * 3 + [2] * 2 + [3]
    cont = contar_por_classe(labels, 4)
    w = pesos_de_amostragem(cont, labels, modo="inverso", teto=25)
    rep = w / w.sum() * len(labels)
    assert rep.max() <= 25.0 + 1e-6, f"teto furado: {rep.max():.1f}"


def test_modo_desconhecido_levanta():
    try:
        pesos_de_amostragem([1], [0], modo="magico")
    except ValueError:
        return
    raise AssertionError("modo inválido deveria levantar ValueError")


def test_base_vazia_nao_quebra():
    assert len(pesos_de_amostragem(np.zeros(0), [], modo="sqrt")) == 0


# ----------------------------------------------------------------------
# CharDataset — augmentation sob demanda
# ----------------------------------------------------------------------

def test_dataset_tem_um_item_por_original():
    """Antes eram 9 (original + 8 cópias congeladas)."""
    with tempfile.TemporaryDirectory() as tmp:
        ds = CharDataset(_base(tmp, {"lower_a": 10, "lower_b": 4}), augment=True)
        assert len(ds) == 14


def test_dataset_guarda_uint8_e_nao_float_aumentado():
    """
    Regressão de memória. Em float32 com 8 cópias, cada amostra custa 36 KB;
    o original em uint8 custa 1 KB. Na base real: 4,7 GB contra 124 MB.
    """
    with tempfile.TemporaryDirectory() as tmp:
        ds = CharDataset(_base(tmp, {"lower_a": 50}), augment=True)
        assert ds.data.dtype == np.uint8
        assert ds.data.shape == (50, 32, 32)
        assert ds.data.nbytes == 50 * 1024


def test_item_sai_no_formato_que_a_rede_espera():
    with tempfile.TemporaryDirectory() as tmp:
        ds = CharDataset(_base(tmp, {"lower_a": 3}), augment=False)
        x, y = ds[0]
        assert isinstance(x, torch.Tensor) and x.shape == (1, 32, 32)
        assert x.dtype == torch.float32 and 0.0 <= float(x.min()) and float(x.max()) <= 1.0
        assert y == 0


def test_augmentation_varia_a_cada_leitura():
    """
    O que torna o sampler útil: sortear a mesma amostra 50 vezes tem que dar 50
    imagens diferentes, não a mesma cópia congelada.
    """
    with tempfile.TemporaryDirectory() as tmp:
        img = np.full((32, 32), 255, dtype=np.uint8)
        img[6:26, 12:20] = 0
        ds = CharDataset(_base(tmp, {"lower_a": 1}, lambda p, i: img.copy()),
                         augment=True)
        vistas = {ds[0][0].numpy().tobytes() for _ in range(30)}
        assert len(vistas) > 5, f"só {len(vistas)} variantes em 30 leituras"


def test_sem_augmentation_a_leitura_e_estavel():
    with tempfile.TemporaryDirectory() as tmp:
        ds = CharDataset(_base(tmp, {"lower_a": 1}), augment=False)
        assert ds[0][0].numpy().tobytes() == ds[0][0].numpy().tobytes()


def test_parte_dos_sorteios_devolve_a_amostra_limpa():
    """
    É imagem limpa que chega na hora de predizer. O desenho antigo tinha 1
    original para cada 8 cópias; augmentar 100% dos sorteios mudaria a
    distribuição de treino sem ninguém pedir.
    """
    with tempfile.TemporaryDirectory() as tmp:
        img = np.full((32, 32), 255, dtype=np.uint8)
        img[6:26, 12:20] = 0
        ds = CharDataset(_base(tmp, {"lower_a": 1}, lambda p, i: img.copy()),
                         augment=True)
        limpa = ds.data[0].astype(np.float32) / 255.0
        iguais = sum(np.array_equal(ds[0][0].numpy()[0], limpa) for _ in range(600))
        assert 30 < iguais < 130, f"{iguais}/600 limpas, esperado ~67"


def test_contagens_por_classe():
    with tempfile.TemporaryDirectory() as tmp:
        ds = CharDataset(_base(tmp, {"lower_a": 7, "lower_b": 2, "lower_c": 5}))
        assert list(ds.contagens) == [7, 2, 5]


def test_pasta_de_quarentena_nao_vira_classe():
    """`_quarentena` é onde o dataset_check põe PNG suspeito (F1.4)."""
    with tempfile.TemporaryDirectory() as tmp:
        _base(tmp, {"lower_a": 3, "_quarentena": 2})
        ds = CharDataset(tmp)
        assert list(ds.label_map) == ["lower_a"]
        assert len(ds) == 3


def test_pasta_vazia_nao_ocupa_indice_de_classe():
    """
    A `lower_ä` da base real ficou vazia porque o cv2.imwrite descartava as
    amostras em silêncio (F1.4), e ainda assim ocupava uma saída da rede.
    """
    with tempfile.TemporaryDirectory() as tmp:
        _base(tmp, {"lower_a": 5, "lower_c": 5})
        os.makedirs(os.path.join(tmp, "lower_b"))   # entre as duas, e vazia
        ds = CharDataset(tmp)
        assert ds.label_map == {"lower_a": 0, "lower_c": 1}
        assert ds.classes_vazias == ["lower_b"]
        assert list(ds.contagens) == [5, 5]


def test_le_amostra_em_caminho_nao_ascii():
    """cv2.imread devolve None em caminho não-ASCII no Windows, sem erro."""
    with tempfile.TemporaryDirectory() as tmp:
        pasta = os.path.join(tmp, "ação")
        os.makedirs(pasta)
        _base(pasta, {"lower_a": 4})
        assert len(CharDataset(pasta)) == 4


# ----------------------------------------------------------------------
# Classes raras: reportadas, não excluídas
# ----------------------------------------------------------------------

def test_classe_rara_e_reportada():
    with tempfile.TemporaryDirectory() as tmp:
        ds = CharDataset(_base(tmp, {"lower_a": 500, "upper_Q": 5}))
        raras = {c for _, c, _ in ds.classes_raras}
        assert raras == {"Q"}
        assert MIN_AMOSTRAS_POR_CLASSE == 10


def test_classe_rara_continua_no_treino():
    """
    A SPEC §5.3 propunha excluí-las. Nesta base as classes abaixo de 10
    amostras são 'K', 'Q' e ± ∓ ∞ □ ■ △ ▼ — o vocabulário do xadrez. Excluir
    significaria o modelo nunca poder produzir esses caracteres.
    """
    with tempfile.TemporaryDirectory() as tmp:
        ds = CharDataset(_base(tmp, {"lower_a": 500, "upper_Q": 5}))
        assert "upper_Q" in ds.label_map
        assert "Q" in ds.idx_to_char.values()
        assert int(ds.contagens[ds.label_map["upper_Q"]]) == 5
        assert len(ds) == 505


# ----------------------------------------------------------------------
# Integração com o treino
# ----------------------------------------------------------------------

def _sorteio_de_um_epoch(ds, modo, semente=7):
    from torch.utils.data import WeightedRandomSampler
    pesos = pesos_de_amostragem(ds.contagens, ds.labels, modo=modo)
    g = torch.Generator().manual_seed(semente)
    s = WeightedRandomSampler(torch.DoubleTensor(pesos), len(ds),
                              replacement=True, generator=g)
    return np.bincount([ds.labels[i] for i in s], minlength=len(ds.contagens))


def test_sampler_muda_a_fatia_de_cada_classe_no_epoch():
    with tempfile.TemporaryDirectory() as tmp:
        ds = CharDataset(_base(tmp, {"lower_a": 2000, "upper_Q": 20}))
        raro = ds.label_map["upper_Q"]

        antes = 20 / 2020
        depois = _sorteio_de_um_epoch(ds, "sqrt")[raro] / len(ds)
        assert depois > 5 * antes, f"{antes:.3%} -> {depois:.3%}"

        inverso = _sorteio_de_um_epoch(ds, "inverso")[raro] / len(ds)
        assert 0.4 < inverso < 0.6, f"inverso deveria dar ~50%, deu {inverso:.1%}"


def test_treino_roda_e_grava_modelo_e_meta():
    with tempfile.TemporaryDirectory() as tmp:
        dados = _base(os.path.join(tmp, "d"), {"lower_a": 30, "upper_Q": 6})
        mp = os.path.join(tmp, "m.pth")
        jp = os.path.join(tmp, "m.json")
        msgs = []
        ok = NeuralTrainer(dados, mp, jp).train(epochs=1, callback=msgs.append)
        assert ok and os.path.exists(mp) and os.path.exists(jp)
        assert any("balanceamento=sqrt" in m for m in msgs)
        assert any("menos de 10 amostras" in m for m in msgs)


def test_balanceamento_nenhum_reproduz_o_comportamento_antigo():
    """Continua sendo possível treinar sem compensação, para comparação."""
    with tempfile.TemporaryDirectory() as tmp:
        dados = _base(os.path.join(tmp, "d"), {"lower_a": 20, "lower_b": 20})
        msgs = []
        assert NeuralTrainer(dados, os.path.join(tmp, "m.pth"),
                             os.path.join(tmp, "m.json")).train(
            epochs=1, callback=msgs.append, balanceamento="nenhum")
        assert any("balanceamento=nenhum" in m for m in msgs)


def test_treino_relata_o_desbalanceamento():
    with tempfile.TemporaryDirectory() as tmp:
        dados = _base(os.path.join(tmp, "d"), {"lower_a": 40, "upper_Q": 2})
        msgs = []
        NeuralTrainer(dados, os.path.join(tmp, "m.pth"),
                      os.path.join(tmp, "m.json")).train(epochs=1,
                                                         callback=msgs.append)
        assert any("40:2" in m for m in msgs), msgs


def test_acuracia_de_treino_e_rotulada_como_tal():
    """
    Com o sampler o número cai, porque as classes raras deixaram de ser
    arredondamento — chamar isso de "Acc" faria parecer piora.

    A F1.3 passou a exibir acurácia de validação no caminho normal; este rótulo
    sobrevive só onde não há validação possível (toda classe pequena demais para
    dividir), que é justamente onde ele mais precisa ser honesto.
    """
    with tempfile.TemporaryDirectory() as tmp:
        dados = _base(os.path.join(tmp, "d"), {"lower_a": 3, "lower_b": 3})
        msgs = []
        NeuralTrainer(dados, os.path.join(tmp, "m.pth"),
                      os.path.join(tmp, "m.json")).train(epochs=1,
                                                         callback=msgs.append)
        assert any("Acc(treino)" in m for m in msgs), msgs


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
