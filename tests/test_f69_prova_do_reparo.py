"""
F69 — a prova visual do reparo de colagem.

O par que estes testes usam é `hamer`, e ele foi escolhido por reproduzir em
duas palavras reais a armadilha que a F66 mediu e não conseguiu passar:

    hater     casa **sem esconder caractere nenhum** — e está errado
    hammer    casa escondendo um — e é o que está impresso

A F66 decidia por comprimento (Occam da geometria) e entregava `hater` toda vez.
O que separa os dois não é o dicionário nem a largura do box: é o que está
desenhado ali. Estes testes travam as duas metades disso — o léxico perguntando,
e o `BoxService` respondendo — e a costura entre elas.

O modelo não entra: `provar` é injetado, como o `arbitro` da F1.5b. Teste que
precisa de rede treinada não roda em máquina limpa, e a F27 já pagou por isso.
"""

import numpy as np
import pytest

from core import lexico
from core.box_model import BoxEntry
from core.neural_trainer import NeuralPredictor
from core.services.box_service import BoxService


#: Pequeno e explícito de propósito: quem lê o teste precisa saber **quais**
#: candidatos existem, e com a lista de 73 mil palavras isso é invisível.
PROSA = {"hater", "hammer", "few", "flow", "the", "of", "and", "player",
         "wandering"}


@pytest.fixture
def lex():
    return lexico.Lexico(palavras=set(PROSA))


def _simbolos(texto):
    """Pares (caractere, índice de box) — um box por caractere."""
    return [(c, i) for i, c in enumerate(texto)]


def _provar_de(tabela):
    """Um `provar` de mentira: a nota de cada trecho vem da tabela, por letra."""
    def provar(caixas, letras):
        return tabela.get(letras, 0.0)
    return provar


# ------------------------------------------------------- o léxico decidindo

def test_sem_prova_o_comprimento_decide_e_erra(lex):
    """
    O caminho da F66, intacto. Existe para a F69 não poder ser confundida com
    um conserto do que havia: sem `provar`, `reparar` continua devolvendo
    `hater` — que é o defeito, e continua sendo o comportamento sem prova.
    """
    r = lexico.reparar(_simbolos("hamer"), {2}, lex)
    assert r is not None and r.corrigida == "hater"
    assert (r.nota, r.vantagem) == (0.0, 0.0)   # sem prova não se inventa número


def test_a_prova_vira_o_resultado(lex):
    """O papel diz `mm`, e o comprimento deixa de decidir."""
    provar = _provar_de({"mm": 0.90, "t": 0.10})
    r = lexico.reparar(_simbolos("hamer"), {2}, lex, provar)
    assert r is not None and r.corrigida == "hammer"


def test_a_nota_e_a_vantagem_ficam_no_reparo(lex):
    """
    São o que o relatório mostra para dizer **por que** a palavra foi trocada.
    Sem eles a fase não tem tabela, e a régua não teria como ser escolhida.
    """
    provar = _provar_de({"mm": 0.90, "t": 0.10})
    r = lexico.reparar(_simbolos("hamer"), {2}, lex, provar)
    assert r.nota == pytest.approx(0.90)
    assert r.vantagem == pytest.approx(0.80)


def test_candidato_unico_tem_vantagem_igual_a_nota(lex):
    """Sem segundo colocado, a vantagem é a nota inteira — e não indefinida."""
    provar = _provar_de({"l": 0.80})
    r = lexico.reparar(_simbolos("fow"), {1}, lex, provar)
    assert r is None or r.vantagem == pytest.approx(r.nota)


def test_nota_abaixo_da_regua_recusa_a_troca(lex):
    """
    O que a `NOTA_MINIMA` compra. `hammer` ganha de `hater` na comparação e
    ainda assim não entra: ganhar do outro candidato não é o mesmo que o papel
    sustentar a palavra, e quem reescreve texto em silêncio precisa das duas.
    """
    provar = _provar_de({"mm": 0.30, "t": 0.05})
    assert lexico.reparar(_simbolos("hamer"), {2}, lex, provar) is None


def test_a_regua_e_parametro_e_a_medicao_pode_varre_la(lex):
    """`medir_reparo.py --nota` depende disto, e a régua saiu de uma varredura."""
    provar = _provar_de({"mm": 0.30, "t": 0.05})
    r = lexico.reparar(_simbolos("hamer"), {2}, lex, provar, nota_minima=0.2)
    assert r is not None and r.corrigida == "hammer"


def test_a_nota_do_candidato_e_a_do_trecho_mais_fraco(lex):
    """
    Dois trechos mascarados, um convincente e outro não: `namer` -> `hater`
    pede `h` e `t`. A média daria 0,60 e passaria pela régua de 0,5; a menor dá
    0,20 e não passa. A palavra só está ali se **todos** os pedaços estiverem.
    """
    provar = _provar_de({"h": 1.00, "t": 0.20})
    assert lexico.reparar(_simbolos("namer"), {0, 2}, lex, provar) is None

    r = lexico.reparar(_simbolos("namer"), {0, 2}, lex, provar, nota_minima=0.1)
    assert r is not None and r.nota == pytest.approx(0.20)


def test_nucleo_de_duas_letras_nao_se_repara(lex):
    """
    `MIN_PARA_REPARAR`. `♗f1` lido `Bf` é o pior reparo proposto que a F69 mediu:
    fora da máscara quase não sobra âncora, e o que sai é adivinhação. Sinalizar
    continua valendo — quem faz isso é `suspeitas_da_pagina`, com `MIN_PARTE`.
    """
    provar = _provar_de({"ew": 1.0, "e": 1.0, "f": 1.0, "o": 1.0})
    assert lexico.reparar(_simbolos("Bf"), {1}, lex, provar) is None


def test_tres_letras_se_reparam(lex):
    """
    O outro lado da régua, e a razão de ela ser 3 e não 4: `fow` -> `few` está
    certo e tira nota alta na prova. Régua que custa acerto sem comprar recusa
    não fica de pé.
    """
    provar = _provar_de({"e": 0.95})
    r = lexico.reparar(_simbolos("fow"), {1}, lex, provar)
    assert r is not None and r.corrigida == "few"


def test_sem_box_largo_a_prova_nem_e_consultada(lex):
    """Sem colagem não há o que reparar, e o modelo não é pago à toa."""
    def provar(caixas, letras):
        raise AssertionError("a prova não devia ser consultada")

    assert lexico.reparar(_simbolos("hamer"), set(), lex, provar) is None


def test_palavra_conhecida_nao_chega_a_prova(lex):
    """`player` está no dicionário: não é palavra estragada, e sai antes."""
    def provar(caixas, letras):
        raise AssertionError("a prova não devia ser consultada")

    assert lexico.reparar(_simbolos("player"), {2}, lex, provar) is None


def test_reparos_da_pagina_repassa_a_prova(lex):
    """
    A prova precisa atravessar a função que a produção chama, e não só a
    interna: foi passando por cima de `reparos_da_pagina` que a F69 ficou
    montada e desligada.
    """
    boxes = [BoxEntry(c, i * 11, 0, i * 11 + 10, 20, confidence=1.0)
             for i, c in enumerate("hamer")]
    provar = _provar_de({"mm": 0.90, "t": 0.10})
    (r,) = lexico.reparos_da_pagina(boxes, {2}, lex, provar)
    assert r.corrigida == "hammer"


# ------------------------------------------------------ a caixa da inicial

def test_a_mascara_na_inicial_nao_come_a_maiuscula(lex):
    """
    `Whndering` -> `Wandering`, e não `wandering`. O dicionário é todo
    minúsculo, e enquanto a máscara começa depois da inicial isso não aparece —
    `_remontar` só troca o pedaço estragado. Quando ela **pega** a inicial, a
    letra vem do dicionário e a maiúscula ia junto.
    """
    provar = _provar_de({"Wa": 0.90, "wa": 0.10})
    r = lexico.reparar(_simbolos("Whndering"), {0, 1}, lex, provar)
    assert r is not None and r.corrigida == "Wandering"


def test_a_prova_pergunta_pela_caixa_do_papel(lex):
    """
    O modelo tem `W` e `w` em classes separadas — são desenhos diferentes —, e
    perguntar por `w` sobre um `W` impresso é perguntar pela classe errada. Foi
    o que rebaixou `Whndering` à pior nota aceita da tabela da F69.
    """
    perguntas = []

    def provar(caixas, letras):
        perguntas.append(letras)
        return 0.9

    lexico.reparar(_simbolos("Whndering"), {0, 1}, lex, provar)
    assert perguntas and all(x[0] == "W" for x in perguntas)


def test_inicial_minuscula_continua_minuscula(lex):
    """A regra é preservar, não capitalizar: `fow` -> `few`, e não `Few`."""
    provar = _provar_de({"e": 0.95})
    r = lexico.reparar(_simbolos("fow"), {1}, lex, provar)
    assert r is not None and r.corrigida == "few"


def test_a_maiuscula_volta_tambem_sem_prova(lex):
    """
    O defeito é do remonte, não da prova: o caminho da F66 o tinha igual, e
    consertá-lo só no caminho novo deixaria os dois discordando.
    """
    r = lexico.reparar(_simbolos("Whndering"), {0, 1}, lex)
    assert r is not None and r.corrigida == "Wandering"


# --------------------------------------------- a rede respondendo a pergunta

def test_probabilidade_de_classe_desconhecida_e_zero():
    """
    Zero quer dizer "não posso afirmar isto", e é a resposta segura: quem chama
    usa o número para **autorizar** uma troca. Devolver a probabilidade da
    vencedora, ou levantar, mandaria o reparo adiante por engano.
    """
    p = NeuralPredictor.__new__(NeuralPredictor)
    p.loaded = True
    p.idx_to_char = {0: "a", 1: "b"}
    p._char_to_idx = None
    assert p.probabilidade_de(np.zeros((8, 8), np.uint8), "z") == 0.0


def test_probabilidade_sem_modelo_e_zero():
    p = NeuralPredictor.__new__(NeuralPredictor)
    p.loaded = False
    p.idx_to_char = {}
    p._char_to_idx = None
    assert p.probabilidade_de(np.zeros((8, 8), np.uint8), "a") == 0.0


# ------------------------------------------------ o box sustentando as letras

def _pagina(largura=60, altura=20, tom=200):
    return np.full((altura, largura), tom, np.uint8)


def _box(x1=0, x2=30, **kw):
    return BoxEntry("m", x1, 0, x2, 20, confidence=1.0, **kw)


def test_uma_letra_nao_corta_o_box():
    """
    O box largo que escondia uma ligadura inteira: o candidato diz que ali há
    **uma** letra, e cortar seria inventar junta onde não há.
    """
    vistos = []

    def probabilidade(recorte, char):
        vistos.append((recorte.shape[1], char))
        return 0.7

    nota = BoxService.provar_letras(_pagina(), _box(), "m", probabilidade)
    assert nota == pytest.approx(0.7)
    assert vistos == [(30, "m")]


def test_a_nota_do_box_e_a_da_letra_mais_fraca():
    """
    A mesma escolha do `_cortes_endossados`, e pelo mesmo motivo: basta um
    pedaço sem sentido para a palavra não estar ali. A média deixaria um `y`
    convincente pagar por um `n` que não existe.
    """
    def probabilidade(recorte, char):
        return {"y": 1.0, "n": 0.2}[char]

    nota = BoxService.provar_letras(_pagina(), _box(), "yn", probabilidade)
    assert nota == pytest.approx(0.2)


def test_o_corte_desigual_e_alcancado():
    """
    O que a repartição igual sozinha não acha. Aqui só a junta em 40% da largura
    responde — é a colagem `y`+`n`, em que a primeira letra é mais estreita —, e
    a varredura de `DESLOCAMENTO_DE_PROVA` existe para alcançá-la.
    """
    def probabilidade(recorte, char):
        largura = recorte.shape[1]
        if char == "y":
            return 1.0 if largura == 12 else 0.0
        return 1.0 if largura == 18 else 0.0

    nota = BoxService.provar_letras(_pagina(), _box(x2=30), "yn", probabilidade)
    assert nota == pytest.approx(1.0)


def test_box_em_negativo_e_positivado_antes_da_pergunta():
    """
    A volta da F10, no mesmo lugar em que o `_cortes_endossados` a faz. Sem ela
    o modelo leria branco sobre preto e recusaria toda troca dentro da tarja
    pelo motivo errado.
    """
    tons = []

    def probabilidade(recorte, char):
        tons.append(int(recorte[0, 0]))
        return 0.5

    BoxService.provar_letras(_pagina(tom=200), _box(negativo=True), "m",
                             probabilidade)
    assert tons == [55]                 # 255 - 200


def test_box_sem_pixel_nao_sustenta_nada():
    """Largura zero não é evidência fraca, é ausência de evidência."""
    def probabilidade(recorte, char):
        raise AssertionError("não há recorte para perguntar")

    assert BoxService.provar_letras(_pagina(), _box(x1=10, x2=10), "m",
                                    probabilidade) == 0.0


# ------------------------------------------------------------- a costura

def test_prova_de_reparo_entrega_a_assinatura_que_o_lexico_espera():
    """
    Índices de box entram, nota sai — e o `core.lexico` continua sem saber o que
    é um pixel. É o padrão do `arbitro` da F1.5b, e a razão de a costura ser uma
    função só.
    """
    boxes = [_box(0, 30), _box(31, 61)]

    def probabilidade(recorte, char):
        return 0.8 if char == "m" else 0.0

    provar = BoxService.prova_de_reparo(_pagina(largura=70), boxes,
                                        probabilidade)
    assert provar([0], "m") == pytest.approx(0.8)


def test_trecho_sobre_dois_boxes_reparte_as_letras():
    """
    Duas colagens encostadas: o candidato traz 3 letras e ninguém sabe quantas
    couberam em cada box. Só a repartição 1+2 responde, e é ela que a busca
    precisa alcançar.
    """
    boxes = [_box(0, 20), _box(21, 61)]
    # Cada box com o seu tom, que é como o recorte diz de onde veio.
    pagina = _pagina(largura=70, tom=100)
    pagina[:, 21:61] = 200

    def probabilidade(recorte, char):
        de_qual = 1 if recorte[0, 0] == 200 else 0
        return 1.0 if (char, de_qual) in {("a", 0), ("b", 1),
                                          ("c", 1)} else 0.0

    provar = BoxService.prova_de_reparo(pagina, boxes, probabilidade)
    # Só a repartição 1+2 acha; 2+1 põe o `b` no box errado e zera.
    assert provar([0, 1], "abc") == pytest.approx(1.0)


def test_menos_letras_que_boxes_nao_sustenta_nada():
    """
    Cada caractere mascarado veio de um box largo, então o candidato traz pelo
    menos uma letra por box. Chegar aqui é máscara e boxes discordando, e a
    resposta segura é recusar — não distribuir o que não há.
    """
    boxes = [_box(0, 30), _box(31, 61)]
    provar = BoxService.prova_de_reparo(_pagina(largura=70), boxes,
                                        lambda r, c: 1.0)
    assert provar([0, 1], "a") == 0.0


def test_a_mesma_pergunta_nao_se_paga_duas_vezes():
    """
    A memória é o que torna a fase pagável: os candidatos de uma palavra caem
    todos sobre os mesmos boxes, e `dynamic` e `dynamics` perguntam o mesmo
    `yn`. Sem ela cada candidato repagaria a varredura inteira.
    """
    contador = []

    def probabilidade(recorte, char):
        contador.append(char)
        return 0.5

    provar = BoxService.prova_de_reparo(_pagina(), [_box()], probabilidade)
    provar([0], "yn")
    quantas = len(contador)
    provar([0], "yn")
    assert len(contador) == quantas
