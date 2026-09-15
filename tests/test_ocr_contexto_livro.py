"""Regressões do OCR contextual usado na exportação de livros."""

import sys

from core import livro
from core.box_model import BoxEntry


def test_a_linha_contextual_e_casada_por_interseccao_de_coordenadas():
    linha = [BoxEntry("", 100, 200, 112, 230),
             BoxEntry("", 114, 200, 128, 230)]
    registros = [("texto certo", 0.91, (98, 198, 130, 232)),
                 ("outra coluna", 0.99, (500, 198, 540, 232))]

    assert livro._casar_linha_ocr(linha, registros, set()) == (
        0, "texto certo", 0.91)


def test_linha_detalhada_do_tesseract_mantem_o_contrato_de_casamento():
    linha = [BoxEntry("", 100, 200, 112, 230)]
    registros = [("texto certo", 0.91, (98, 198, 130, 232),
                  (("texto", 0.91, (98, 198, 118, 232)),))]

    assert livro._casar_linha_ocr(linha, registros, set()) == (
        0, "texto certo", 0.91)


def test_fragmento_curto_coberto_por_linha_contextual_e_descartado():
    linha = [BoxEntry("", 100, 200, 112, 230)]
    registros = [("Solutions", 0.96, (98, 198, 180, 232))]

    assert livro._parece_fragmento_ocr(linha, "S0l", registros)
    assert not livro._parece_fragmento_ocr(linha, "the", registros)


def test_glifo_isolado_nao_contamina_a_prosa_contextual():
    peca = chr(0x2654)
    base = "31. " + peca + "aidy - Ivkov 19..." + chr(0x2656) + "f3"
    contextual = "31. Saidy - Ivkov 19...Rf3"

    resultado = livro._preservar_glifos_de_xadrez(base, contextual)

    assert "Saidy" in resultado
    assert peca not in resultado.split("Saidy", 1)[0]
    assert chr(0x2656) in resultado


def test_glifos_sao_mesclados_na_palavra_por_coordenada():
    peca = chr(0x2655)
    base = "White 31. " + peca + "h5t and Saidy"
    contextual = "White 31. Qh5t and Saidy"
    detalhes = (
        ("White", 0.99, (100, 20, 150, 40)),
        ("31.", 0.99, (155, 20, 180, 40)),
        ("Qh5t", 0.99, (185, 20, 230, 40)),
        ("and", 0.99, (235, 20, 265, 40)),
        ("Saidy", 0.99, (270, 20, 320, 40)),
    )

    resultado = livro._preservar_glifos_por_palavra(
        base, contextual, [(10, 188.0, peca)], detalhes)

    assert resultado == "White 31. " + peca + "h5t and Saidy"


def test_glifo_falso_em_nome_e_descartado_na_mescla_por_coordenada():
    peca = chr(0x2654)
    base = "31. " + peca + "aidy - Ivkov"
    contextual = "31. Saidy - Ivkov"
    detalhes = (
        ("31.", 0.99, (100, 20, 120, 40)),
        ("Saidy", 0.99, (125, 20, 175, 40)),
        ("-", 0.99, (180, 20, 188, 40)),
        ("Ivkov", 0.99, (195, 20, 240, 40)),
    )

    resultado = livro._preservar_glifos_por_palavra(
        base, contextual, [(140, 150.0, peca)], detalhes)

    assert resultado == contextual


def test_glifo_de_promocao_fica_depois_do_sinal_de_igual():
    peca = chr(0x2655)
    base = "41. fxg1=" + peca + "+"
    contextual = "41. fxg1=W+"
    detalhes = (("41.", 0.99, (100, 20, 120, 40)),
                ("fxg1=W+", 0.99, (125, 20, 205, 40)))

    resultado = livro._preservar_glifos_por_palavra(
        base, contextual, [(9, 180.0, peca)], detalhes)

    assert resultado == "41. fxg1=" + peca + "+"


def test_corretor_contextual_corrige_erros_frequentes_sem_mudar_nome():
    resultado = livro._corrigir_prosa_contextual(
        "the full poinc. A beauciful move, but wuld che queen")

    assert "full point" in resultado
    assert "beautiful move" in resultado
    assert "would the queen" in resultado
    assert livro._corrigir_prosa_contextual("Jianu Saidy") == "Jianu Saidy"


def test_corretor_contextual_corrige_maiusculas_e_erros_de_prosa_do_yusupov():
    resultado = livro._corrigir_prosa_contextual(
        "Whice exploits the outpost; chen earns one pointe."
    )

    assert resultado == "White exploits the outpost; then earns one point."


def test_trocas_diretas_nao_dependem_do_vocabulario_de_frequencia(monkeypatch):
    # Sem `wordfreq` a busca aproximada é desligada, mas a tabela desta fonte
    # continua valendo: era ela que devolvia a linha intocada quando o pacote
    # opcional faltava no interpretador.
    monkeypatch.setitem(livro._VOCABULARIO_OCR, "en", None)
    monkeypatch.setitem(sys.modules, "wordfreq", None)

    resultado = livro._corrigir_prosa_contextual(
        "Whice exploits che outpost; a nice movc")

    assert resultado == "White exploits the outpost; a nice movc"
    assert livro._VOCABULARIO_OCR["en"] == []
