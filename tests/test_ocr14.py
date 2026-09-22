"""
O garimpo dos erros confiantes da cadeia (OCR-14, item 5 da revisão de 2026-09-18).

O módulo alinha o que a cadeia leu com a referência humana e devolve, por
divergência, o caractere esperado, o lido, a confiança e **a caixa do glifo na
página** — que é o que um treino dirigido precisa e o que não existia.

Os testes são de mesa: montam a leitura caractere a caractere, sem PDF, sem
modelo e sem torch.
"""

from __future__ import annotations

import pytest

from core import ocr14


def _lidos(texto: str, *, confianca: float = 1.0, linha: int = 0):
    """A leitura da cadeia, um caractere por box, com caixas em fila."""
    return [ocr14.CaractereLido(caractere, confianca if not caractere.isspace() else 0.0,
                                (k * 10, 0, k * 10 + 9, 20), k, linha)
            for k, caractere in enumerate(texto)]


def test_a_troca_confiante_sai_com_a_caixa_do_glifo():
    """O par que a OCR-14 existe para achar: `⩲` impresso, `±` lido."""
    erros = ocr14.minerar(_lidos("26.♗g3± and"), "26.♗g3⩲ and")
    assert len(erros) == 1
    erro = erros[0]
    assert (erro.esperado, erro.lido) == ("⩲", "±")
    assert erro.especie == "troca" and erro.confiante
    assert erro.dominio == "notation"
    assert erro.caixa == (60, 0, 69, 20) and erro.indice_do_box == 6
    assert erro.token_esperado == "26.♗g3⩲"


def test_o_buraco_e_a_invencao_sao_especies_proprias():
    """O que a cadeia comeu e o que ela pôs são material de treino diferente."""
    comeu = ocr14.minerar(_lidos("g6"), "gxh6")
    assert [(e.esperado, e.lido, e.especie) for e in comeu] == [
        ("x", "", "buraco"), ("h", "", "buraco")]

    pos = ocr14.minerar(_lidos("g16"), "g6")
    assert [(e.esperado, e.lido, e.especie) for e in pos] == [("", "1", "invencao")]
    assert pos[0].caixa == (10, 0, 19, 20), "a caixa é a do glifo inventado"


def test_a_leitura_certa_nao_gera_erro_nenhum():
    assert ocr14.minerar(_lidos("25.♖xc7! Amazingly"), "25.♖xc7! Amazingly") == []


def test_a_dobra_tipografica_nao_conta_como_erro():
    """O travessão impresso e o `†` do xeque são convenção, não leitura."""
    assert ocr14.minerar(_lidos("El Debs - Valhondo"), "El Debs – Valhondo") == []
    assert ocr14.minerar(_lidos("♗f6+"), "♗f6†") == []


def test_a_confianca_separa_o_residuo_do_que_a_fila_ja_alcanca():
    """
    Abaixo do piso o erro é dúvida, e a fila de suspeitas e a coleta de baixa
    confiança já o pegam desde a F2.7. A OCR-14 é o que passa **afirmado**.
    """
    hesitante = ocr14.minerar(_lidos("♗g3±", confianca=.4), "♗g3⩲")
    assert hesitante and not hesitante[0].confiante
    resumo = ocr14.Resumo(hesitante)
    assert resumo.confiantes == []
    assert ocr14.tabela_de_confusao(hesitante) == {}
    assert ocr14.tabela_de_confusao(hesitante, so_confiantes=False)[("±", "⩲")] == 1


def test_o_dominio_separa_o_lance_da_prosa():
    """
    A fusão por palavra dá a prosa ao motor e guarda o lance da cadeia, então o
    erro confiante da cadeia em prosa não chega ao livro — o do lance chega.
    """
    erros = ocr14.minerar(_lidos("Amazingly Gaslimov 25.♖xc8!"),
                          "Amazingly Gashimov 25.♖xc7!")
    resumo = ocr14.Resumo(erros)
    assert resumo.no_dominio("prose").confiantes[0].lido == "l"
    assert resumo.no_dominio("notation").confiantes[0].esperado == "7"
    assert len(resumo.no_dominio("todos").erros) == len(erros) == 2
    assert dict(resumo.por_dominio()) == {"prose": 1, "notation": 1}


def test_a_tabela_de_confusao_ordena_o_que_mais_dói():
    erros = []
    for _ in range(3):
        erros += ocr14.minerar(_lidos("♗g3±"), "♗g3⩲")
    erros += ocr14.minerar(_lidos("♕c1"), "♕e1")
    tabela = ocr14.tabela_de_confusao(erros)
    assert tabela.most_common(1) == [(("±", "⩲"), 3)]
    assert tabela[("c", "e")] == 1

    resumo = ocr14.Resumo(erros)
    assert resumo.classes_a_treinar() == [("⩲", 3)]
    assert resumo.classes_a_treinar(minimo=1) == [("⩲", 3), ("e", 1)]


def test_o_resumo_serializa_o_que_o_relatorio_publica():
    resumo = ocr14.Resumo(ocr14.minerar(_lidos("♗g3±"), "♗g3⩲"))
    dados = resumo.to_dict()
    assert dados["erros"] == dados["confiantes"] == 1
    assert dados["por_especie"] == {"troca": 1}
    assert dados["confusoes"] == [{"lido": "±", "esperado": "⩲", "vezes": 1}]


def test_a_linha_inteira_perdida_nao_estala_o_garimpo():
    """Página cuja cadeia não leu nada continua sendo mensurável."""
    erros = ocr14.minerar([], "25.♖xc7! Amazingly")
    assert len(erros) == len("25.♖xc7!") + len("Amazingly")
    assert all(erro.especie == "buraco" and erro.caixa is None for erro in erros)
    assert ocr14.Resumo(erros).confiantes == []


@pytest.mark.parametrize("caractere, dobrado", [
    ("–", "-"), ("†", "+"), ("’", "'"), ("a", "a"), ("…", "..."),
])
def test_a_dobra_por_caractere_e_a_do_ab(caractere, dobrado):
    assert ocr14.dobrar_caractere(caractere) == dobrado


def test_a_dobra_que_cresce_mantem_a_caixa_do_glifo_que_a_produziu():
    """`…` vira três pontos, e os três apontam para o box das reticências."""
    erros = ocr14.minerar(_lidos("a…"), "b...")
    assert [erro.especie for erro in erros] == ["troca"]
    assert erros[0].caixa == (0, 0, 9, 20)
