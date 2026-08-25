"""
Testes da F104 — a confusão de caracteres medida sem gabarito.

O instrumento tem três peças que erram em silêncio, e são elas que estão presas
aqui:

    o prior      sem ele, distância de edição escolhe `quiche` para `quicHy`
                 com a mesma facilidade com que escolhe `quickly`
    a caixa      alinhado em minúsculo, `BIack` contra `Black` vira `l → i`, e
                 é `l → I` — outra troca, outro defeito a procurar
    a peneira    `hxg` é `hxg5` sem o algarismo; sem tirá-lo, a matriz sai
                 dominada por notação, que é o que a SPEC §5.8 proíbe

O relatório inteiro não se testa: ele é texto para olho humano. O que se testa é
a conta que ele imprime.

Rodar sem pytest:      python tests/test_f104_confusao_no_livro.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import medir_confusao_no_livro as mcl
from core import lexico


def _lexico(*palavras):
    return lexico.Lexico(palavras=set(palavras))


# ----------------------------------------------------------------------
# Distância e alinhamento
# ----------------------------------------------------------------------

def test_a_distancia_desiste_acima_do_teto():
    assert mcl.levenshtein("two", "rwo") == 1
    assert mcl.levenshtein("anyway", "anryay") == 2
    assert mcl.levenshtein("two", "elephant", teto=2) > 2
    # Desistir é o que a torna barata: comprimento distante nem entra na conta.
    assert mcl.levenshtein("ab", "abcdefgh", teto=2) > 2


def test_deletes_e_a_vizinhanca_de_uma_supressao():
    assert mcl.deletes("abc") == {"bc", "ac", "ab"}


def test_a_troca_de_duas_letras_por_uma_conta_como_uma_so():
    """
    `quickly` lido `quicHy` é o par `kl` virando `H`, e não duas trocas
    independentes. Perder isso mandaria procurar dois defeitos onde há um.
    """
    assert mcl.trocas("quickly", "quicHy") == [("kl", "H")]
    assert mcl.trocas("two", "rwo") == [("t", "r")]
    assert mcl.trocas("zugzwang", "zugwang") == [("z", "")]
    assert mcl.trocas("after", "afiter") == [("", "i")]
    assert mcl.trocas("igual", "igual") == []


def test_a_vizinhanca_acha_a_uma_e_a_duas_edicoes():
    v = mcl.Vizinhanca({"two", "twice", "between", "anyway", "elephant"})
    assert ("two" in [p for _d, p in v.perto("rwo")])
    assert (2, "anyway") in v.perto("anryay")
    assert not [p for _d, p in v.perto("elephant") if p == "two"]


def test_a_vizinhanca_ignora_o_que_nao_e_palavra():
    v = mcl.Vizinhanca({"two", "hx", "a", "x" * 40})
    assert v.vocabulario == ["two"], "entrou curta demais, longa demais ou não-letra"


# ----------------------------------------------------------------------
# A peneira
# ----------------------------------------------------------------------

def test_a_notacao_sem_o_algarismo_sai_da_conta():
    """
    São 19% do que fica fora do dicionário no Aagaard. Dentro, a matriz
    passaria a medir notação — e dicionário não decide sobre lance (SPEC §5.8).
    """
    for truncada in ("hxg", "fxe", "axb", "cxd", "guf", "guh"):
        assert mcl.e_notacao_truncada(truncada), truncada
    for palavra in ("the", "two", "between", "endgame", "hnd", "xtu"):
        assert not mcl.e_notacao_truncada(palavra), palavra


def test_a_peneira_do_parece_lance_seria_larga_demais():
    """
    **A versão elegante estava errada, e o teste guarda o número.** Perguntar
    `parece_lance(nucleo + algarismo)` aceita `endgame1`, `fine1` e `ed1`, e
    esconderia erros de leitura no balde dos lances — no livro, `dgame` com 140
    ocorrências, que é `endgame`.
    """
    from core import notacao

    for palavra in ("endgame", "dgame", "fine", "beeause"):
        assert any(notacao.parece_lance(palavra + d) for d in "12345678"), (
            f"{palavra}: a peneira antiga deixou de ser larga — reveja o "
            f"cabeçalho do e_notacao_truncada")
        assert not mcl.e_notacao_truncada(palavra)


def test_o_pedaco_de_palavra_nao_vira_confusao_de_caractere():
    """
    `dgame` é `endgame` sem duas letras — segmentação, e não glifo trocado. Na
    matriz daria `nada → d` com o peso de 140 leituras, apontando um defeito que
    não existe.
    """
    prior = {"endgame": 500, "game": 40, "exchange": 60, "first": 68}
    assert mcl.e_pedaco_de_palavra("dgame", prior) == "endgame"
    # Uma letra só é leitura errada, e é o que se quer medir.
    assert not mcl.e_pedaco_de_palavra("exchang", prior)
    # Só entre as palavras que o livro usa.
    assert not mcl.e_pedaco_de_palavra("dgame", {"game": 40})
    # **Vale a partir de três letras**: `rst` é `first` sem a ligadura `fi`, e
    # com quatro de mínimo ele escapava para a matriz como `u → r` — 53 leituras
    # de uma troca que não existe, porque `ust` está no dicionário e fica a uma
    # edição enquanto `first` fica a duas.
    assert mcl.e_pedaco_de_palavra("rst", prior) == "first"
    assert not mcl.e_pedaco_de_palavra("st", prior)


def test_a_flexao_que_falta_no_dicionario_nao_e_erro_de_leitura():
    lx = _lexico("increment", "trivial", "exchang")
    assert mcl.e_flexao_ausente("increments", lx)
    assert mcl.e_flexao_ausente("trivially", lx)
    # `Exchang` é `Exchange` sem o `e` — leitura errada, e não flexão.
    assert not mcl.e_flexao_ausente("exchange", lx)


def test_o_espaco_perdido_se_reconhece_pela_partição():
    lx = _lexico("of", "the", "you", "if")
    assert mcl.parte_em_conhecidas("ofthe", lx) == ("of", "the")
    assert mcl.parte_em_conhecidas("ifyou", lx) == ("if", "you")
    assert mcl.parte_em_conhecidas("ofxthe", lx) is None


def test_contar_separa_prosa_de_notacao_e_monta_o_prior():
    lx = _lexico("two", "pawn")
    conhecidas, fora, prior = mcl.contar(
        ["two", "pawn,", "Nf3", "exd5", "rwo", "12", "of", "pawn"], lx)
    assert conhecidas == 3 and prior == {"two": 1, "pawn": 2}
    assert fora == {"rwo": 1}, "lance, número ou palavra curta entrou na conta"


# ----------------------------------------------------------------------
# A medição
# ----------------------------------------------------------------------

def test_o_prior_desempata_e_e_por_isso_que_ele_existe():
    """
    **O teste da fase.** `quickiy` está a uma edição de `quickie` e de
    `quickly`; quem decide é qual das duas este livro usa. Sem prior a escolha é
    o acaso da ordem alfabética.
    """
    lx = _lexico("quickie", "quickly")
    v = mcl.Vizinhanca(lx.palavras)

    _cat, confusao, atribuidas, _ind = mcl.medir(
        {"quickiy": 3}, {"quickly": 40}, lx, v)
    assert atribuidas == [(3, "quickiy", "quickly")]
    assert confusao == {("l", "i"): 3}

    _cat, _conf, atribuidas, _ind = mcl.medir(
        {"quickiy": 3}, {"quickie": 40}, lx, v)
    assert atribuidas == [(3, "quickiy", "quickie")]


def test_a_distancia_manda_mais_que_o_prior():
    """
    E é de propósito: `quicHy` está a **uma** edição de `quiche` e a duas de
    `quickly`, e frequência não compra distância. É o limite honesto do método,
    e é por isso que o relatório imprime a fatia indecisa.
    """
    lx = _lexico("quiche", "quickly")
    v = mcl.Vizinhanca(lx.palavras)
    _cat, _conf, atribuidas, _ind = mcl.medir(
        {"quicHy": 3}, {"quickly": 900, "quiche": 9}, lx, v)
    assert atribuidas == [(3, "quicHy", "quiche")]


def test_o_prior_de_uma_aparicao_nao_e_evidencia():
    """
    Sem piso, `hrst` — que é `first` sem a ligadura `fi` — foi atribuído a
    `horst`, palavra que o livro usa **uma** vez, e a matriz ganhou oito
    leituras de `f → h` que não existem.
    """
    lx = _lexico("horst", "hoist", "first")
    v = mcl.Vizinhanca(lx.palavras)
    categorias, confusao, atribuidas, _ind = mcl.medir(
        {"hrst": 8}, {"horst": mcl.PRIOR_MINIMO - 1}, lx, v)
    assert not atribuidas and not confusao
    assert categorias["sem prior para decidir"] == 8

    _cat, _conf, atribuidas, _ind = mcl.medir(
        {"hrst": 8}, {"horst": mcl.PRIOR_MINIMO}, lx, v)
    assert atribuidas == [(8, "hrst", "horst")]


def test_sem_prior_nenhum_a_forma_fica_indecisa_em_vez_de_chutada():
    """
    Chutar poria ruído na matriz. No Aagaard são 231 ocorrências — entre elas
    `quickiy`, cujas 88 leituras de `quickly` saíram **todas** erradas, e por
    isso a palavra certa não está no prior.
    """
    lx = _lexico("quiche", "quickly")
    v = mcl.Vizinhanca(lx.palavras)
    categorias, confusao, atribuidas, indecisas = mcl.medir(
        {"quickiy": 5}, {}, lx, v)
    assert not atribuidas and not confusao
    assert categorias["sem prior para decidir"] == 5
    assert indecisas[0][:2] == (5, "quickiy")


def test_a_caixa_original_sobrevive_ao_alinhamento():
    """`BIack` contra `Black` é `l → I` maiúsculo, e não `l → i`."""
    lx = _lexico("black")
    v = mcl.Vizinhanca(lx.palavras)
    _cat, confusao, atribuidas, _ind = mcl.medir(
        {"BIack": 7}, {"black": 100}, lx, v)
    assert atribuidas == [(7, "BIack", "Black")]
    assert confusao == {("l", "I"): 7}


def test_a_contagem_e_por_ocorrencia_e_nao_por_forma():
    """
    Uma troca que aparece em 247 leituras da mesma palavra pesa 247, e não 1.
    É o que faz `t → r` responder por 22,9% do livro com seis palavras.
    """
    lx = _lexico("two", "between")
    v = mcl.Vizinhanca(lx.palavras)
    _cat, confusao, _atr, _ind = mcl.medir(
        {"rwo": 247, "berween": 49}, {"two": 70, "between": 17}, lx, v)
    assert confusao == {("t", "r"): 296}


def test_o_que_nao_tem_candidato_nao_vira_confusao():
    lx = _lexico("elephant")
    v = mcl.Vizinhanca(lx.palavras)
    categorias, confusao, atribuidas, _ind = mcl.medir({"xyzqw": 4}, {}, lx, v)
    assert not confusao and not atribuidas
    assert categorias["sem candidato"] == 4


def test_o_idioma_errado_e_recusado_em_vez_de_medido(capsys):
    """
    **Contra o livro do idioma errado o método não falha, ele produz.** Sem a
    guarda, um livro em português contra o léxico inglês sai com uma matriz
    inteira, com números convincentes, medindo a diferença entre dois idiomas.
    """
    lx = _lexico("the", "two", "pawn")
    v = mcl.Vizinhanca(lx.palavras)
    fora = {f"palavra{i}": 3 for i in range(20)}
    saida = mcl.relatar(2, fora, *mcl.medir(fora, {}, lx, v))
    assert saida == 1, "mediu um livro que o dicionário não cobre"
    assert "idioma" in capsys.readouterr().out

    # E o livro do idioma certo passa: 3% a 5% fora do dicionário, medido.
    assert mcl.relatar(1000, {"rwo": 5}, *mcl.medir(
        {"rwo": 5}, {"two": 90}, lx, v)) == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
