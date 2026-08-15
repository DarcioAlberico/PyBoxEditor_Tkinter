"""
F7.2 — o k-NN deixa de custar 21 s por página.

O elo do meio da cadeia (rede -> k-NN -> EasyOCR) **se paga**: medido nas 9
páginas rotuladas, a rede fica abaixo de 0,8 em 3,5% dos caracteres, e nesses
366 casos difíceis a cadeia com o k-NN acerta 88,5% contra 72,4% da rede
sozinha. O que custava caro era a implementação.

O risco desta fase é o de toda otimização: **acelerar mudando a resposta**. Se o
vizinho escolhido deixar de ser o mesmo, o ganho é falso e ninguém percebe — a
saída continua parecendo plausível. Por isso o teste central compara a resposta
nova com um laço ingênuo escrito aqui dentro, que é a implementação anterior.

Rodar sem pytest:      python tests/test_f72_knn.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pytest

from core.learner import (LADO, NOME_DO_CACHE, CharacterLearner, char_to_folder,
                          folder_to_char)


def _amostra(valor, ruido=0):
    img = np.full((LADO, LADO), valor, np.uint8)
    if ruido:
        img[0, 0] = min(255, valor + ruido)
    return img


def _base(tmp_path, amostras):
    """Monta uma base de treino: {caractere: [imagens]}."""
    raiz = tmp_path / "base"
    for char, imagens in amostras.items():
        pasta = raiz / char_to_folder(char)
        pasta.mkdir(parents=True, exist_ok=True)
        for i, img in enumerate(imagens):
            cv2.imwrite(str(pasta / f"{i}.png"), img)
    return str(raiz)


def _vizinho_ingenuo(learner, consulta):
    """A implementação anterior: um laço, uma norma por referência."""
    alvo = cv2.resize(consulta, (LADO, LADO)).astype(np.float32).ravel()
    melhor, menor = "?", float("inf")
    for char, linha in zip(learner._chars, learner._X):
        d = float(np.linalg.norm(alvo - linha))
        if d < menor:
            menor, melhor = d, char
    return melhor, menor


# ----------------------------------------------------------------------
# A busca não pode mudar
# ----------------------------------------------------------------------

def test_a_busca_e_a_mesma_do_laco(tmp_path):
    """
    A conta de matriz da F7.2 devolve o mesmo vizinho que o laço ingênuo.

    Media o `predict` até a F24, quando a decisão passou a ser voto entre k e a
    confiança passou a ser margem. **A propriedade em teste é a mesma** — a
    busca não mudou —, e quem a expõe agora é `vizinhos`.
    """
    caminho = _base(tmp_path, {
        "a": [_amostra(10), _amostra(20), _amostra(30)],
        "b": [_amostra(120), _amostra(130)],
        "c": [_amostra(240), _amostra(250)],
    })
    L = CharacterLearner(caminho, usar_cache=False)
    for valor in (0, 15, 25, 100, 125, 200, 245, 255):
        consulta = _amostra(valor)
        assert L.vizinhos(consulta, k=1)[0] == pytest.approx(
            _vizinho_ingenuo(L, consulta), abs=1e-6), f"valor {valor}"


def test_predict_responde_o_que_respondia_antes_da_f24(tmp_path):
    """
    A F24 trocou `predict` por voto e margem, mediu, e desfez. Este teste é o
    que garante que o desfazer foi completo — inclusive a confiança, que o
    teste da busca não cobre.

    A referência é o corpo anterior reescrito aqui, contra as mesmas matrizes.
    Conferido também nos 4.280 recortes de quatro páginas reais: zero
    divergências.
    """
    caminho = _base(tmp_path, {
        "a": [_amostra(10), _amostra(20)], "b": [_amostra(120)],
        "c": [_amostra(240), _amostra(250)],
    })
    L = CharacterLearner(caminho, usar_cache=False)

    def antes_da_f24(consulta, threshold=2000.0):
        char, distancia = _vizinho_ingenuo(L, consulta)
        conf = (max(0.0, 1.0 - distancia / threshold)
                if distancia < threshold else 0.0)
        return char, conf

    for valor in (0, 15, 25, 100, 125, 200, 245, 255):
        consulta = _amostra(valor)
        assert L.predict(consulta) == pytest.approx(
            antes_da_f24(consulta), abs=1e-6), f"valor {valor}"


def test_vizinhos_saem_em_ordem_e_no_numero_pedido(tmp_path):
    caminho = _base(tmp_path, {"a": [_amostra(10), _amostra(30)],
                               "b": [_amostra(120)], "c": [_amostra(240)]})
    L = CharacterLearner(caminho, usar_cache=False)
    perto = L.vizinhos(_amostra(20), k=3)
    assert len(perto) == 3
    assert [c for c, _d in perto] == ["a", "a", "b"]
    assert [d for _c, d in perto] == sorted(d for _c, d in perto)


def test_vizinhos_de_base_vazia(tmp_path):
    L = CharacterLearner(str(tmp_path / "vazia"), usar_cache=False)
    assert L.vizinhos(_amostra(50)) == []


# ----------------------------------------------------------------------
# F24 — o voto entre os k
# ----------------------------------------------------------------------

def test_a_confianca_de_producao_cai_com_a_distancia(tmp_path):
    """
    O que a cadeia roteia por: distância absoluta ao vizinho mais próximo.

    Sobreviveu à F24, que mediu a alternativa e a devolveu — ver
    `test_a_margem_mede_ambiguidade_e_a_producao_mede_novidade`.
    """
    caminho = _base(tmp_path, {"a": [_amostra(100)]})
    L = CharacterLearner(caminho, usar_cache=False)
    _, perto = L.predict(_amostra(100))
    _, longe = L.predict(_amostra(160))
    assert perto == 1.0
    assert 0.0 < longe < perto


def test_o_voto_escolhe_a_maioria_e_nao_o_mais_proximo(tmp_path):
    """
    Uma referência solitária mais perto que o grupo certo.

    É o caso que motivou medir o voto, e o `voto` de fato o resolve. Não
    entrou porque **no conjunto** ele custa: 96,10% com k=1 contra 95,90% com
    k=5 (ver `K_VIZINHOS`). Um caso construído não é uma distribuição.
    """
    caminho = _base(tmp_path, {
        "o": [_amostra(100)],
        "0": [_amostra(104), _amostra(106), _amostra(108), _amostra(110)],
    })
    L = CharacterLearner(caminho, usar_cache=False)
    consulta = _amostra(101)

    assert L.vizinhos(consulta, k=1)[0][0] == "o"
    assert L.voto(consulta, k=5) == "0"
    assert L.predict(consulta)[0] == "o"        # produção segue o mais próximo


def test_o_voto_desempata_pelo_mais_proximo(tmp_path):
    caminho = _base(tmp_path, {"a": [_amostra(100)], "b": [_amostra(140)]})
    L = CharacterLearner(caminho, usar_cache=False)
    assert L.voto(_amostra(110), k=2) == "a"
    assert L.voto(_amostra(130), k=2) == "b"


def test_voto_de_base_vazia(tmp_path):
    L = CharacterLearner(str(tmp_path / "vazia"), usar_cache=False)
    assert L.voto(_amostra(50)) == "?"


# ----------------------------------------------------------------------
# F24 — a margem, que também não entrou
# ----------------------------------------------------------------------

def test_a_margem_e_invariante_de_escala(tmp_path):
    """
    A razão entre distâncias não se move quando todas as distâncias dobram.

    É a propriedade que motivou medi-la: `1 - distância/2000` mede peso de
    tinta junto com qualidade, e rebaixa o glifo de traço grosso por engordar.
    As duas bases aqui têm a mesma geometria relativa e o mesmo número sai.
    """
    # O alvo a 1/5 do caminho entre as duas classes, com vão de 80 numa base e
    # de 160 na outra.
    perto = _base(tmp_path / "perto", {"a": [_amostra(100)],
                                       "b": [_amostra(180)]})
    longe = _base(tmp_path / "longe", {"a": [_amostra(20)],
                                       "b": [_amostra(180)]})
    A = CharacterLearner(perto, usar_cache=False)
    B = CharacterLearner(longe, usar_cache=False)
    assert A.margem_de_confianca(_amostra(116)) == pytest.approx(0.75, abs=1e-6)
    assert B.margem_de_confianca(_amostra(52)) == pytest.approx(0.75, abs=1e-6)

    # E a de produção **não** é invariante: é o defeito que a margem corrigia.
    assert A.predict(_amostra(116))[1] != pytest.approx(
        B.predict(_amostra(52))[1], abs=1e-6)


def test_a_margem_mede_ambiguidade_e_a_producao_mede_novidade(tmp_path):
    """
    O achado da F24, no menor caso que o mostra.

    Um recorte que a base nunca viu, longe de tudo, mas muito mais perto de uma
    classe que da outra: **margem alta, confiança de produção baixa**. Quem
    roteia quer a segunda leitura — o elo seguinte da cadeia existe justamente
    para o box que esta base não conhece.
    """
    # Distância 1.920 até 'a' e 3.840 até 'b': o dobro, então a margem dá 0,50 —
    # e 1.920 é longe o bastante para a confiança de produção dar 0,04.
    caminho = _base(tmp_path, {"a": [_amostra(10)], "b": [_amostra(190)]})
    L = CharacterLearner(caminho, usar_cache=False)
    desconhecido = _amostra(70)

    assert L.margem_de_confianca(desconhecido) == pytest.approx(0.50, abs=1e-6)
    assert L.predict(desconhecido)[1] == pytest.approx(0.04, abs=1e-6)


def test_copia_exata_da_base_da_confianca_cheia(tmp_path):
    caminho = _base(tmp_path, {"a": [_amostra(100)], "b": [_amostra(200)]})
    L = CharacterLearner(caminho, usar_cache=False)
    assert L.predict(_amostra(100)) == ("a", 1.0)
    assert L.margem_de_confianca(_amostra(100)) == 1.0


def test_classe_unica_na_base_nao_tem_do_que_duvidar(tmp_path):
    """Sem outra classe não há margem a medir, e fingir dúvida seria pior."""
    caminho = _base(tmp_path, {"a": [_amostra(100)]})
    L = CharacterLearner(caminho, usar_cache=False)
    assert L.margem_de_confianca(_amostra(160)) == 1.0


def test_duas_classes_a_mesma_distancia_zeram_a_margem(tmp_path):
    """
    O empate perfeito é o caso em que a margem tem de dizer "não sei".

    **Não dá para montá-lo com a mesma imagem sob dois rótulos** — a dedup por
    bytes da F7.2 guarda só uma das duas, e as 16 contradições da base real
    (`0`/`o`, `1`/`l`, `V`/`v`) já chegam ao k-NN com um lado só. Aqui o empate
    é geométrico: o alvo no meio exato do caminho entre as duas classes.
    """
    caminho = _base(tmp_path, {"a": [_amostra(100)], "b": [_amostra(140)]})
    L = CharacterLearner(caminho, usar_cache=False)
    assert L.margem_de_confianca(_amostra(120)) == 0.0


def test_a_margem_cai_quando_a_outra_classe_se_aproxima(tmp_path):
    caminho = _base(tmp_path, {"a": [_amostra(100)], "b": [_amostra(200)]})
    L = CharacterLearner(caminho, usar_cache=False)
    folgada = L.margem_de_confianca(_amostra(105))
    apertada = L.margem_de_confianca(_amostra(145))
    assert folgada > apertada > 0.0


def test_margem_de_base_vazia(tmp_path):
    L = CharacterLearner(str(tmp_path / "vazia"), usar_cache=False)
    assert L.margem_de_confianca(_amostra(50)) == 0.0


def test_aprender_uma_classe_nova_entra_no_indice(tmp_path):
    """
    `_ids` é o que torna a margem vetorizada, e ele cresce em `learn`. Fora de
    sincronia, a máscara apontaria para a classe errada — em silêncio.
    """
    caminho = _base(tmp_path, {"a": [_amostra(100)]})
    L = CharacterLearner(caminho, usar_cache=False)
    assert L.margem_de_confianca(_amostra(200)) == 1.0     # classe única

    L.learn(_amostra(200), "z")
    assert L.predict(_amostra(200))[0] == "z"
    assert L.margem_de_confianca(_amostra(200)) == 1.0     # cópia exata de 'z'
    assert len(L._ids) == L.total
    assert L._classes[L._ids[-1]] == "z"


def test_base_vazia_devolve_interrogacao(tmp_path):
    L = CharacterLearner(str(tmp_path / "vazia"), usar_cache=False)
    assert L.predict(_amostra(50)) == ("?", 0.0)


def test_recorte_colorido_e_aceito(tmp_path):
    caminho = _base(tmp_path, {"a": [_amostra(100)]})
    L = CharacterLearner(caminho, usar_cache=False)
    colorido = np.full((20, 20, 3), 100, np.uint8)
    assert L.predict(colorido)[0] == "a"


def test_recorte_de_outro_tamanho_e_redimensionado(tmp_path):
    caminho = _base(tmp_path, {"a": [_amostra(100)]})
    L = CharacterLearner(caminho, usar_cache=False)
    assert L.predict(np.full((7, 60), 100, np.uint8))[0] == "a"


# ----------------------------------------------------------------------
# F37 — as candidatas por classe
# ----------------------------------------------------------------------

def test_candidatas_sao_classes_e_vizinhos_sao_amostras(tmp_path):
    """
    A distinção que fez a F37 precisar de método novo, no menor caso que a
    mostra: uma classe com muitas amostras vizinhas afoga as outras.

    `vizinhos(k=3)` devolve três amostras de `a`, e não há o que desempatar.
    `candidatas(n=3)` devolve `a`, `b`, `c` — a melhor de cada. É a mesma razão
    pela qual o voto da F24 mediu pior: com a dedup, o vizinho mais próximo é
    quase o mesmo PNG.
    """
    caminho = _base(tmp_path, {"a": [_amostra(100), _amostra(101),
                                     _amostra(102)],
                               "b": [_amostra(140)],
                               "c": [_amostra(180)]})
    L = CharacterLearner(caminho, usar_cache=False)

    assert [c for c, _d in L.vizinhos(_amostra(100), k=3)] == ["a", "a", "a"]
    assert [c for c, _p in L.candidatas(_amostra(100), n=3)] == ["a", "b", "c"]


def test_a_primeira_candidata_e_o_que_predict_responde(tmp_path):
    """A ordem é a da distância, invertida pela confiança — e a mesma escala."""
    caminho = _base(tmp_path, {"a": [_amostra(100)], "b": [_amostra(180)]})
    L = CharacterLearner(caminho, usar_cache=False)

    alvo = _amostra(110)
    char, conf = L.predict(alvo)
    assert L.candidatas(alvo, n=2)[0] == (char, pytest.approx(conf))


def test_candidatas_nao_repete_classe(tmp_path):
    """Pedir mais classes do que existem devolve as que existem, sem repetir."""
    caminho = _base(tmp_path, {"a": [_amostra(100)] * 4, "b": [_amostra(180)]})
    L = CharacterLearner(caminho, usar_cache=False)

    chars = [c for c, _p in L.candidatas(_amostra(100), n=9)]
    assert chars == ["a", "b"]


def test_candidatas_em_base_vazia(tmp_path):
    L = CharacterLearner(str(tmp_path / "vazia"), usar_cache=False)
    assert L.candidatas(_amostra(100)) == []


# ----------------------------------------------------------------------
# A duplicata some, e some sem mudar nada
# ----------------------------------------------------------------------

def test_amostras_identicas_viram_uma(tmp_path):
    """86% da base real era repetição byte a byte; comparar sete vezes é o mesmo."""
    caminho = _base(tmp_path, {"a": [_amostra(100)] * 7, "b": [_amostra(200)]})
    L = CharacterLearner(caminho, usar_cache=False)
    assert L.total == 2


def test_a_duplicata_nao_muda_o_vizinho(tmp_path):
    com = _base(tmp_path / "com", {"a": [_amostra(100)] * 5, "b": [_amostra(200)]})
    sem = _base(tmp_path / "sem", {"a": [_amostra(100)], "b": [_amostra(200)]})
    A = CharacterLearner(com, usar_cache=False)
    B = CharacterLearner(sem, usar_cache=False)
    for valor in (0, 90, 110, 150, 190, 255):
        assert A.predict(_amostra(valor)) == B.predict(_amostra(valor))


def test_amostras_quase_iguais_ficam_as_duas(tmp_path):
    """A remoção é byte a byte; um pixel de diferença é outra amostra."""
    caminho = _base(tmp_path, {"a": [_amostra(100), _amostra(100, ruido=5)]})
    assert CharacterLearner(caminho, usar_cache=False).total == 2


# ----------------------------------------------------------------------
# Aprender
# ----------------------------------------------------------------------

def test_aprender_vale_na_hora(tmp_path):
    caminho = _base(tmp_path, {"a": [_amostra(10)]})
    L = CharacterLearner(caminho, usar_cache=False)
    assert L.predict(_amostra(200))[0] == "a"
    L.learn(_amostra(200), "z")
    assert L.predict(_amostra(200))[0] == "z"
    assert L.total == 2


def test_aprender_grava_no_disco(tmp_path):
    caminho = _base(tmp_path, {"a": [_amostra(10)]})
    CharacterLearner(caminho, usar_cache=False).learn(_amostra(200), "z")
    pasta = os.path.join(caminho, char_to_folder("z"))
    assert os.path.isdir(pasta) and os.listdir(pasta)


def test_ligadura_deixa_de_ser_descartada(tmp_path):
    """
    A guarda era `len(char) != 1`, e um box marcado 'fi' sumia calado — apesar
    de `char_to_folder` ter um ramo `ligature_*` para exatamente isso.
    """
    caminho = _base(tmp_path, {"a": [_amostra(10)]})
    L = CharacterLearner(caminho, usar_cache=False)
    L.learn(_amostra(200), "fi")
    assert L.predict(_amostra(200))[0] == "fi"
    assert os.path.isdir(os.path.join(caminho, "ligature_fi"))


def test_ligadura_sobrevive_a_recarga(tmp_path):
    caminho = _base(tmp_path, {"a": [_amostra(10)]})
    CharacterLearner(caminho, usar_cache=False).learn(_amostra(200), "fi")
    assert CharacterLearner(caminho, usar_cache=False).predict(
        _amostra(200))[0] == "fi"


def test_caractere_vazio_nao_e_aprendido(tmp_path):
    caminho = _base(tmp_path, {"a": [_amostra(10)]})
    L = CharacterLearner(caminho, usar_cache=False)
    L.learn(_amostra(200), "")
    assert L.total == 1


def test_aprender_o_que_ja_existe_nao_incha_a_matriz(tmp_path):
    caminho = _base(tmp_path, {"a": [_amostra(10)]})
    L = CharacterLearner(caminho, usar_cache=False)
    for _ in range(5):
        L.learn(_amostra(10), "a")
    assert L.total == 1


# ----------------------------------------------------------------------
# O cache
# ----------------------------------------------------------------------

def test_cache_e_gravado_e_reusado(tmp_path):
    caminho = _base(tmp_path, {"a": [_amostra(10)], "b": [_amostra(200)]})
    primeiro = CharacterLearner(caminho)
    assert os.path.isfile(os.path.join(caminho, NOME_DO_CACHE))

    segundo = CharacterLearner(caminho)
    assert segundo.total == primeiro.total
    assert segundo._chars == primeiro._chars
    assert np.array_equal(segundo._X, primeiro._X)


def test_cache_velho_e_refeito(tmp_path):
    """Uma amostra nova muda a contagem da pasta, e o cache deixa de valer."""
    caminho = _base(tmp_path, {"a": [_amostra(10)]})
    CharacterLearner(caminho)

    pasta = os.path.join(caminho, char_to_folder("b"))
    os.makedirs(pasta, exist_ok=True)
    cv2.imwrite(os.path.join(pasta, "novo.png"), _amostra(200))

    L = CharacterLearner(caminho)
    assert L.total == 2
    assert L.predict(_amostra(200))[0] == "b"


def test_cache_corrompido_nao_derruba_o_programa(tmp_path):
    caminho = _base(tmp_path, {"a": [_amostra(10)]})
    CharacterLearner(caminho)
    with open(os.path.join(caminho, NOME_DO_CACHE), "wb") as f:
        f.write(b"isto nao e um npz")

    L = CharacterLearner(caminho)
    assert L.total == 1 and L.predict(_amostra(10))[0] == "a"


def test_cache_desligado_nao_cria_arquivo(tmp_path):
    caminho = _base(tmp_path, {"a": [_amostra(10)]})
    CharacterLearner(caminho, usar_cache=False)
    assert not os.path.isfile(os.path.join(caminho, NOME_DO_CACHE))


def test_salvar_cache_depois_de_aprender(tmp_path):
    caminho = _base(tmp_path, {"a": [_amostra(10)]})
    L = CharacterLearner(caminho)
    L.learn(_amostra(200), "z")
    L.salvar_cache()

    outro = CharacterLearner(caminho)
    assert outro.total == 2
    assert outro.predict(_amostra(200))[0] == "z"


def test_o_cache_nao_entra_como_referencia(tmp_path):
    """Ele mora dentro da base; ler `.learner_cache.npz` como classe seria ruim."""
    caminho = _base(tmp_path, {"a": [_amostra(10)]})
    CharacterLearner(caminho)
    assert CharacterLearner(caminho).total == 1


def test_o_servico_grava_o_cache_apos_o_lote(tmp_path):
    from PIL import Image
    from core.box_model import BoxEntry
    from core.services.learning_service import LearningService

    caminho = _base(tmp_path, {"a": [_amostra(10)]})
    svc = LearningService(data_dir=caminho)
    imagem = Image.fromarray(np.full((40, 40), 200, np.uint8))
    n = svc.learn_from_boxes(imagem, [BoxEntry("z", 0, 0, 20, 20)])

    assert n == 1
    assert CharacterLearner(caminho).total == 2


# ----------------------------------------------------------------------
# O que já valia continua valendo
# ----------------------------------------------------------------------

@pytest.mark.parametrize("char", list("aZ0") + ["fi", "f7", "-g", "+-", "♞", "?", "."])
def test_ida_e_volta_do_nome_de_pasta(char):
    assert folder_to_char(char_to_folder(char)) == char


def test_pasta_desconhecida_nao_vira_referencia_silenciosa(tmp_path):
    """`folder_to_char` estrito é o que impediu 127 amostras de treinar '?'."""
    from core.learner import NomeDePastaInvalido
    with pytest.raises(NomeDePastaInvalido):
        folder_to_char("sym_nao_numerico", strict=True)


def test_base_inexistente_nao_quebra(tmp_path):
    L = CharacterLearner(str(tmp_path / "nao_existe"), usar_cache=False)
    assert L.total == 0


# ----------------------------------------------------------------------
# O defeito de dados que apareceu no caminho
# ----------------------------------------------------------------------

def test_denuncia_a_mesma_imagem_com_dois_rotulos(tmp_path):
    """Na base real são 16 — `1`/`l`, `V`/`v`, `0`/`o`. Ver dataset_check."""
    from core.dataset_check import rotulos_contraditorios

    caminho = _base(tmp_path, {"o": [_amostra(100)], "0": [_amostra(100)],
                               "a": [_amostra(200)]})
    problemas = rotulos_contraditorios(caminho)
    assert len(problemas) == 1
    assert problemas[0].tipo == "rotulo_contraditorio"
    assert "0/o" in problemas[0].detalhe


def test_rotulo_contraditorio_e_aviso_e_nao_erro(tmp_path):
    """
    Nenhum treino melhora removendo um dos lados: os dois rótulos estão certos
    para alguma ocorrência daquele desenho. Quem escolhe é o contexto (F1.7).
    """
    from core.dataset_check import rotulos_contraditorios

    caminho = _base(tmp_path, {"o": [_amostra(100)], "0": [_amostra(100)]})
    assert not rotulos_contraditorios(caminho)[0].grave


def test_base_sem_contradicao_nao_acusa(tmp_path):
    from core.dataset_check import rotulos_contraditorios

    caminho = _base(tmp_path, {"a": [_amostra(10)], "b": [_amostra(200)]})
    assert rotulos_contraditorios(caminho) == []


def test_a_varredura_cara_fica_fora_do_caminho_rapido(tmp_path):
    """`validar_dados` desliga a leitura dos PNGs de propósito; 151k custam 18 s."""
    from core.dataset_check import validar_dataset

    caminho = _base(tmp_path, {"o": [_amostra(100)] * 12,
                               "0": [_amostra(100)] * 12})
    rapido = validar_dataset(caminho, checar_pngs=False)
    completo = validar_dataset(caminho, checar_pngs=True)
    assert not any(p.tipo == "rotulo_contraditorio" for p in rapido)
    assert any(p.tipo == "rotulo_contraditorio" for p in completo)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
