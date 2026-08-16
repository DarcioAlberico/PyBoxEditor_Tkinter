"""
F23 — o instrumento da cadeia, e a afirmação de que ele depende.

`medir_cadeia.py` consulta cada modelo **uma vez por recorte** e reexecuta só o
roteamento a cada ponto da varredura. Isso é o que torna a tabela viável — o
EasyOCR custa ~16 ms por caractere, e uma varredura de seis limiares pagaria a
leitura inteira seis vezes —, mas só vale se a memorização não mudar resposta
nenhuma. É essa a propriedade testada aqui.

O resto do arquivo é composição: o `fallback_chain` e o `ler_pagina` chamados
são os de produção, e quem os cobre são `test_f16_easyocr.py` e
`test_f17_leitura_de_linha.py`.
"""

import numpy as np

import medir_cadeia as mc
from core.services.ocr_service import OCRService


class _ModeloFalso:
    """Conta as consultas e devolve resposta dependente do recorte."""

    def __init__(self):
        self.chamadas = 0

    def predict(self, crop):
        self.chamadas += 1
        return chr(ord("a") + int(crop[0, 0]) % 26), float(crop[0, 0]) / 255.0


class _ReaderFalso:
    """O mesmo contrato de `test_f16_easyocr`, contando chamadas."""

    def __init__(self, texto="x", conf=0.42):
        self.texto, self.conf = texto, conf
        self.chamadas = 0

    def recognize(self, img, horizontal_list=None, free_list=None, detail=1):
        self.chamadas += 1
        return [([[0, 0]], self.texto, self.conf)]


def _crop(tom=200, h=12, w=10):
    return np.full((h, w), tom, dtype=np.uint8)


# ----------------------------------------------------------------------
# 1. A memória do modelo
# ----------------------------------------------------------------------

def test_memo_consulta_uma_vez_por_recorte():
    modelo = _ModeloFalso()
    memo = mc._Memo(modelo)
    crop = _crop()

    primeira = memo.predict(crop)
    for _ in range(9):
        assert memo.predict(crop) == primeira
    assert modelo.chamadas == 1


def test_memo_nao_confunde_recortes_diferentes():
    """
    A chave são os bytes da imagem. Dois boxes distintos nunca dão o mesmo
    recorte, e um recorte igual dá — legitimamente — a mesma resposta.
    """
    modelo = _ModeloFalso()
    memo = mc._Memo(modelo)

    a = memo.predict(_crop(tom=100))
    b = memo.predict(_crop(tom=200))
    assert a != b
    assert modelo.chamadas == 2


def test_memo_devolve_o_que_o_modelo_devolveria():
    """A memorização é transparente, ou a medição mede outra coisa."""
    modelo = _ModeloFalso()
    crop = _crop(tom=137)
    esperado = _ModeloFalso().predict(crop)
    assert mc._Memo(modelo).predict(crop) == esperado


def test_a_confianca_combinada_e_o_minimo_das_duas():
    """
    `min(absoluta, margem)` — a terceira forma que a F24 mediu, e que perde.

    O envelope não consulta o k-NN de novo: as duas metades já foram calculadas
    no aquecimento, e é isso que torna a varredura das duas confianças possível
    no mesmo processo — que é como elas ficam na mesma base.
    """
    class _Learner:
        def __init__(self):
            self.consultas = 0

        def predict(self, crop):
            self.consultas += 1
            return "a", 0.80

        def margem_de_confianca(self, crop):
            self.consultas += 1
            return 0.25

    alvo = _Learner()
    memo = mc._Memo(alvo)
    combinado = mc._MemoCombinado(memo)
    crop = _crop()

    assert combinado.predict(crop) == ("a", 0.25)
    combinado.predict(crop)
    combinado.predict(crop)
    assert alvo.consultas == 2      # um `predict` e uma `margem`, e só


def test_memo_responde_ao_loaded_do_fallback_chain():
    """
    O `fallback_chain` pergunta `predictor.loaded` antes de consultar a rede.
    Um envelope sem esse atributo desligaria o elo neural em silêncio, e a
    tabela sairia do caminho híbrido com o nome do neural.
    """
    assert mc._Memo(_ModeloFalso()).loaded is True


# ----------------------------------------------------------------------
# 2. A memória do EasyOCR, que é substituição de `classmethod`
# ----------------------------------------------------------------------

def test_servico_memorizado_le_o_recorte_uma_vez():
    svc = mc.ServicoMemorizado()
    reader = _ReaderFalso("e", 0.9)
    crop = _crop()

    primeira = svc.fallback_chain(crop, reader=reader)
    assert svc.fallback_chain(crop, reader=reader) == primeira
    assert svc.fallback_chain(crop, reader=reader) == primeira
    assert reader.chamadas == 1


def test_servico_memorizado_responde_como_o_original():
    """
    `_ler_easyocr` é `classmethod` no serviço e vira método de instância aqui.
    Se a substituição não pegasse, a memória não teria efeito; se pegasse
    errado, a resposta mudaria. As duas falhas aparecem neste teste.
    """
    crop = _crop()
    esperado = OCRService().fallback_chain(crop, reader=_ReaderFalso("e", 0.9))
    obtido = mc.ServicoMemorizado().fallback_chain(
        crop, reader=_ReaderFalso("e", 0.9))
    assert obtido == esperado


def test_faixa_de_linha_memorizada_por_faixa():
    """A linha é lida uma vez por faixa, e faixas distintas não se misturam."""
    svc = mc.ServicoMemorizado()
    svc._readers[(("en",), False)] = _ReaderFalso("abc", 0.8)
    reader = svc._readers[(("en",), False)]

    a = svc.easyocr_linha_conf(_crop(tom=10, h=20, w=80))
    b = svc.easyocr_linha_conf(_crop(tom=10, h=20, w=80))
    c = svc.easyocr_linha_conf(_crop(tom=90, h=20, w=80))
    assert a == b == c            # o reader falso é constante
    assert reader.chamadas == 2   # mas foi consultado uma vez por faixa


# ----------------------------------------------------------------------
# 3. A conta do acerto
# ----------------------------------------------------------------------

def test_acerto_usa_os_equivalentes_da_avaliacao():
    """
    A mesma `normalizar` de `avaliacao_pagina`, senão este instrumento e o
    `medir_paginas.py` contariam populações diferentes de "certo".
    """
    registros = [("learner", 1.0, "a", "a", "p.png"),
                 ("learner", 1.0, "b", "c", "p.png")]
    assert mc.acerto(registros) == 50.0
    assert mc.acerto([]) == 0.0


def test_os_dois_limiares_do_hibrido_sao_o_mesmo_numero():
    """
    A F23 amarrou os dois: a trava existe para a linha agir onde o k-NN se
    recusou, e quem define a recusa é o limiar. Separá-los foi medido — 7
    consertos contra 97 quebras, −90 caracteres — e este teste é o que impede
    que a amarração se desfaça sem alguém decidir desfazê-la.
    """
    from ui.main_window import (CONF_MAXIMA_PARA_A_LINHA_HIBRIDO,
                                LEARNER_THRESHOLD_HIBRIDO)
    assert CONF_MAXIMA_PARA_A_LINHA_HIBRIDO == LEARNER_THRESHOLD_HIBRIDO


# ----------------------------------------------------------------------
# F52 — o instrumento não reimplementa a regra de produção
# ----------------------------------------------------------------------

def test_o_instrumento_nao_copia_a_regra_da_fila():
    """
    A trava do defeito que apareceu quatro vezes nesta série.

    `medir_cadeia.py` mede o que produção faz, e a única forma de continuar
    medindo isso quando produção muda é **chamar** a regra dela. Copiá-la —
    `conf < LIMIAR_ALTO` escrito à mão — funciona no dia em que se escreve e
    passa a mentir no dia seguinte, calado. Foi o que aconteceu na F43/F44 (a
    margem aplicada fora da fonte), e de novo na F48, quando
    `FONTES_SEMPRE_REVISADAS` entrou e a linha "hoje" das tabelas continuou
    medindo a regra anterior.

    `_BoxFalso` existe desde a F23 exatamente para isto: ele é o mínimo que
    `ui.confidence` olha num box, para o instrumento poder perguntar em vez de
    responder por conta própria.

    A trava é de **uso**, não de texto: comparar `LIMIAR_ALTO` num `if` é o que
    denuncia. Citá-lo dentro de uma f-string de rótulo é legítimo, e por isso a
    varredura olha comparações e não menções.
    """
    import ast
    import inspect

    import medir_cadeia

    arvore = ast.parse(inspect.getsource(medir_cadeia))
    ofensas = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Compare):
            continue
        for lado in [no.left] + list(no.comparators):
            if (isinstance(lado, ast.Attribute)
                    and lado.attr in ("LIMIAR_ALTO", "LIMIAR_MEDIO",
                                      "LIMIAR_DE_MARGEM")):
                ofensas.append((lado.attr, getattr(no, "lineno", "?")))

    assert not ofensas, (
        "o instrumento voltou a comparar contra um limiar de produção em vez de "
        f"chamar `precisa_revisao`: {ofensas}")


def test_o_box_falso_responde_o_que_a_regra_pergunta():
    """
    A trava acima só vale se `_BoxFalso` continuar servindo para a pergunta.
    Se `precisa_revisao` passar a olhar um campo que ele não tem, o instrumento
    quebra alto — e é o que se quer, em vez de divergir calado.
    """
    from ui import confidence as conf_ui

    import medir_cadeia

    # (fonte, confiança, lido, verdade, página, id)
    alto = medir_cadeia._BoxFalso(("neural", 0.99, "a", "a", "p", 1))
    baixo = medir_cadeia._BoxFalso(("neural", 0.10, "a", "a", "p", 2))
    ocr = medir_cadeia._BoxFalso(("easyocr", 0.99, "a", "a", "p", 3))

    assert conf_ui.precisa_revisao(alto) is False
    assert conf_ui.precisa_revisao(baixo) is True
    assert conf_ui.precisa_revisao(ocr) is True, "a regra da F48 tem de valer aqui"


# ----------------------------------------------------------------------
# F54 — a separação, e o que ela mede que um corte não mede
# ----------------------------------------------------------------------

def test_separacao_e_a_u_de_mann_whitney():
    """
    A definição da coluna que a F51 introduziu e a F54 usa para comparar réguas.

    Erro **abaixo** do acerto é a ordem certa, e é por isso que o teste da
    régua perfeita põe os erros com nota menor: a régua é de confiança, e
    confiança baixa é o que manda o box para a fila.
    """
    assert mc._separacao([0.1, 0.2], [0.8, 0.9]) == 1.0
    assert mc._separacao([0.8, 0.9], [0.1, 0.2]) == 0.0
    # Empate vale meio par, que é o que faz disto a U e não uma contagem
    # estrita: uma régua que dá a mesma nota a tudo é uma moeda, e não uma
    # régua perfeita nem uma invertida.
    assert mc._separacao([0.5, 0.5], [0.5, 0.5]) == 0.5
    assert mc._separacao([0.4, 0.6], [0.5, 0.5]) == 0.5

    # Um lado vazio é "não dá para perguntar", e não "não separa" — a fonte que
    # nunca errou nas páginas medidas não tem separação 0,00.
    import math

    assert math.isnan(mc._separacao([], [0.9]))
    assert math.isnan(mc._separacao([0.1], []))


def test_a_separacao_nao_muda_com_o_corte_nem_com_a_escala():
    """
    **É o teto de qualquer corte sobre aquela régua**, e é o que dá sentido à
    F54 existir depois da F47.

    A F47 comparou confiança e margem em quatro cortes e viu as curvas se
    cruzarem. Um corte é um ponto; a separação é a curva inteira, e ela não se
    move por reescala monótona da nota. Consequência prática: se a régua da rede
    separa 0,634, **nenhuma escolha de limiar** melhora isso — mexer no 0,90 anda
    sobre a mesma curva. Trocar de régua é outra coisa, e é a pergunta da F54.
    """
    erros, acertos = [0.10, 0.55, 0.91], [0.40, 0.80, 0.99]
    antes = mc._separacao(erros, acertos)

    for transformar in (lambda c: c ** 3,          # aperta o topo
                        lambda c: c ** (1 / 3),    # estica o topo
                        lambda c: 0.5 + c / 2):    # comprime a faixa inteira
        assert mc._separacao([transformar(c) for c in erros],
                             [transformar(c) for c in acertos]) == antes


def test_a_regua_alternativa_nao_empresta_a_margem_de_outro_elo(capsys):
    """
    A trava do defeito que a F47 achou embaixo da F43 e da F44.

    O aquecimento consulta o k-NN em **todos** os boxes, inclusive nos que o
    roteamento mandou ao EasyOCR — então o mapa de margens tem entrada para
    todo mundo. Julgar um box do EasyOCR pela ambiguidade de um classificador
    que foi recusado por estar longe de tudo é o que fez a margem parecer
    excelente por duas fases seguidas.
    """
    # (fonte, confiança, lido, verdade, página, id) — o EasyOCR erra e acerta,
    # então haveria os dois lados para a conta, se ela fosse feita.
    linhas = [("easyocr", 0.99, "a", "b", "p", 1),
              ("easyocr", 0.98, "c", "c", "p", 2),
              ("learner", 0.99, "d", "e", "p", 3),
              ("learner", 0.98, "f", "f", "p", 4)]
    margens = {1: 0.10, 2: 0.90, 3: 0.10, 4: 0.90}   # há margem para todos

    mc.tabela_regua_alternativa(linhas, margens)
    saida = capsys.readouterr().out

    easyocr = next(l for l in saida.splitlines() if l.startswith("easyocr"))
    assert "não produz margem" in easyocr, (
        "o instrumento voltou a julgar o EasyOCR pela margem do k-NN")
    assert "0.10" not in easyocr and "0.90" not in easyocr

    # E o `learner`, que produz a sua, é medido normalmente: a trava é sobre de
    # quem é a régua, e não sobre desligar a coluna.
    learner = next(l for l in saida.splitlines() if l.startswith("learner"))
    assert "1.000" in learner, "a margem do k-NN separa os seus próprios boxes"
