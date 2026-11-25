"""O corretor de prosa lembra o que respondeu por palavra e idioma (RG-16b, R-24): a busca
aproximada percorre 100 mil palavras, e a prosa repete as mesmas."""

import pytest

from core import livro

pytest.importorskip("rapidfuzz")
pytest.importorskip("wordfreq")


@pytest.fixture
def contadas(monkeypatch):
    monkeypatch.setattr(livro, "_APROXIMACOES", {})
    chamadas = []
    original = livro._aproximar_sem_memoria

    def contar(palavra, idioma, vocabulario):
        chamadas.append((palavra, idioma))
        return original(palavra, idioma, vocabulario)

    monkeypatch.setattr(livro, "_aproximar_sem_memoria", contar)
    return chamadas


def test_a_palavra_repetida_se_pergunta_uma_vez(contadas):
    linha = "the quecn takes the quecn and the quecn wins"
    primeira = livro._corrigir_prosa_contextual(linha)
    segunda = livro._corrigir_prosa_contextual(linha)
    assert primeira == segunda
    assert len(contadas) == len(set(contadas))
    assert [p for p, _i in contadas].count("quecn") == 1


def test_o_idioma_separa_as_respostas(contadas):
    for idioma in ("en", "pt", "en", "pt"):
        livro._corrigir_prosa_contextual("jogada", idioma)
    assert contadas == [("jogada", "en"), ("jogada", "pt")]


def test_a_lembrada_e_a_mesma_da_busca():
    """Palavras da prosa de verdade e as deformadas delas, com memória e sem."""
    from wordfreq import top_n_list

    vocabulario = top_n_list("en", 100000)
    palavras = [p for p in top_n_list("en", 400) if len(p) >= 4 and p.isalpha()][:60]
    palavras += [p[:-1] + "c" for p in palavras]
    assert ([livro._aproximar(p, "en", vocabulario) for p in palavras * 2]
            == [livro._aproximar_sem_memoria(p, "en", vocabulario) for p in palavras] * 2)


def test_o_vocabulario_trocado_comeca_outra_memoria(contadas):
    assert livro._aproximar("quecn", "en", ["queen"]) == "queen"
    assert livro._aproximar("quecn", "en", ["rook"]) == "quecn"
    assert livro._aproximar("quecn", "en", ["queen"]) == "queen"
    assert len(contadas) == 3


def test_o_teto(contadas, monkeypatch):
    monkeypatch.setattr(livro, "TETO_DE_APROXIMACOES", 2)
    vocabulario = ["queen"]
    for palavra in ("aaa", "bbb", "ccc", "ddd"):
        livro._aproximar(palavra, "en", vocabulario)
    assert len(livro._APROXIMACOES["en"][1]) <= 2
