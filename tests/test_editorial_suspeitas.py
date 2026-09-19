"""A régua das suspeitas (2026-09-19; `docs/REVISAO_MODOS_OCR.md`, §4.5).

O que faz de uma linha lida uma suspeita, fixado sobre os registros reais
de roteamento das quatro páginas de referência de 2026-09-18 (encurtados):
os resíduos de 4.1 viram motivo, em código e em frase, e o que está certo —
a avaliação colada ao lance, a peça na casa da tabela, a figurina solta na
prosa, a linha do motor fraca — não vira. No fim, o que o leitor passou a
guardar para a fila existir: o registro de cada linha no parágrafo e a
caixa de cada linha no registro.
"""

import fitz
import pytest

from core import livro
from core.editorial_suspeitas import (MOTIVOS, confianca_da_linha, descrever,
                                      descrever_codigos, motivos_da_linha)


# ----------------------------------------------------------------------
# Os registros reais, encurtados
# ----------------------------------------------------------------------

def _registro(texto, ancora="", linha_ocr="", *, dominio="mixed", fonte="fusao",
              primario="line", semelhanca=0.9, confianca_ocr=0.85, descartados=0,
              caixa=(10, 20, 300, 40), **extras):
    return {"linha": 0, "dominio": dominio, "primario": primario,
            "motivo": f"region_type={'notation' if dominio == 'notation' else 'body'}",
            "fonte": fonte, "ancora": ancora or texto, "linha_ocr": linha_ocr,
            "confianca_ocr": confianca_ocr, "semelhanca": semelhanca,
            "descartados": descartados, "caixa": list(caixa), "texto": texto, **extras}


def _codigos(registro):
    return [m.codigo for m in motivos_da_linha(registro)]


@pytest.mark.parametrize("texto, linha_ocr, esperado", [
    # p. 30, linha 1: o ponto do número de lance que a cadeia não viu.
    ("25♖xc7! Amazingly Gashimov missed his chance", "25.8xc7! Amazingly Gashimov missed his chance",
     "malformed_move"),
    # p. 30, linha 9: dois pontos onde o livro imprime três.
    ("In reply to 57..♖xc4? White could have taken", "In reply to 57...8xe4? White could have taken",
     "malformed_move"),
    # p. 30, linha 20: `g16` não é casa; é `gxh6` lido torto.
    ("a simple move: 26.h6! ♖f6 26...g16 27.♘c5", "a simple move: 26.h6! BFf6 26...¢xh6 27.He5",
     "malformed_move_number"),
    # p. 237: a minúscula no `W♖g1` da legenda da tabela.
    ("In all cases w♖g1, ♙c3 and B♔h7: W=White to play", "In all cases es Web ¢ &c3 and B&h7",
     "malformed_move"),
    # p. 237: `1..♖b2?` com um ponto a menos.
    ("W3a) 1..♖b2? (1...♖f2? 2 ♖e8! is", "W3a) 1...b2? (1...2f2? 2 He8! is", "malformed_move"),
    # p. 30, linha 5: o `]` que veio do motor dentro de uma palavra.
    ("9. El] Debs — Valhondo Morales, Gibraltar 2012", "9. El] Debs — Valhondo Morales, Gibraltar 2012",
     "engine_garbage"),
])
def test_os_residuos_das_paginas_de_referencia_viram_motivo(texto, linha_ocr, esperado):
    registro = _registro(texto, linha_ocr=linha_ocr)
    assert esperado in _codigos(registro)


def test_o_lance_de_peao_que_o_motor_leu_diferente_e_conflito():
    # p. 30, linha 4: a cadeia leu `a6` onde está impresso `gxh5`.
    registro = _registro("a6 28.♕g5+ Black is mated.", linha_ocr="gxh5 28.4954 Black is mated.",
                         confianca_ocr=0.77)
    motivos = motivos_da_linha(registro)
    assert [m.codigo for m in motivos] == ["notation_conflict"]
    assert "«gxh5»" in motivos[0].frase and "«a6»" in motivos[0].frase


def test_o_motor_fraco_nao_serve_de_contraprova():
    # p. 30, linha 23: o motor lê `26...e6` a 0,4 onde a cadeia lê `26...g6`, e
    # o livro imprime `g6`.
    registro = _registro("26...g6 27.♖g7+ ♔h8 28.♕a7 is just mate.",
                         linha_ocr="26...e6 27.Eg7t Hh8 28.Wa7 is just mate.", confianca_ocr=0.4)
    assert _codigos(registro) == []


def test_a_peca_que_o_motor_le_como_letra_nao_e_conflito():
    # `58.Bxd4` do motor contra `58.♖xd4` da cadeia: a casa é a mesma.
    registro = _registro("with the point 58.♖xd4 ♕g3+", linha_ocr="with the point 58.Bxd4 Yg3+")
    assert _codigos(registro) == []


def test_a_celula_da_tabela_com_peca_na_casa_nao_e_suspeita():
    registro = _registro("B♖h2", dominio="notation", fonte="glyph", primario="glyph",
                         semelhanca=None, confianca_ocr=0.0, celula="t0c0l0")
    assert _codigos(registro) == []
    assert confianca_da_linha(registro) == pytest.approx(0.9)


def test_a_linha_que_a_cadeia_derrubou_inteira_e_a_pior_suspeita():
    # p. 237: os dois `*` da tabela, que a cadeia derrubou e o motor leu.
    registro = _registro("", ancora="", linha_ocr="*", dominio="unknown", fonte="glyph",
                         primario="line", semelhanca=0.0, confianca_ocr=0.92, descartados=1,
                         faixa=True, celula="t3c1l0")
    motivos = motivos_da_linha(registro)
    assert [m.codigo for m in motivos] == ["line_lost"]
    assert "o motor leu «*»" in motivos[0].frase
    assert confianca_da_linha(registro, motivos) <= 0.1


def test_o_resultado_partido_no_fim_da_linha_de_lances():
    # p. 30, linha 24: `1–0` de que só sobrou o `1`.
    registro = _registro("♖g8 31.♕a7 ♘e7 32.♗e4 fxe4 33.♖xe7 ♖xg2+ 34.♔xg2 e3+ 35.♔h3 1",
                         linha_ocr="Hg8 31.Ya7 De7 32.Re4 fxed 33.8xe7 Exg2t 34.Bxg2 3+ 35.2h3 1-0",
                         dominio="notation", fonte="glyph", primario="glyph", confianca_ocr=0.5,
                         descartados=1)
    assert set(_codigos(registro)) == {"dropped_in_notation", "result_incomplete"}


def test_a_prosa_que_ficou_com_a_cadeia_e_suspeita_e_diz_por_que():
    recusada = _registro("Wh1c was able o ui[1 the b]ack", linha_ocr="White was able to ruin the black",
                         fonte="glyph", semelhanca=0.4)
    motivos = motivos_da_linha(recusada)
    assert [m.codigo for m in motivos][0] == "engine_disagreed"
    assert "40%" in motivos[0].frase
    sem_motor = _registro("White won on move 68", linha_ocr="", fonte="glyph", semelhanca=None)
    assert "engine_missing" in _codigos(sem_motor)


def test_a_linha_limpa_o_fragmento_e_a_prosa_boa_nao_tem_motivo():
    assert _codigos(_registro("The unprotected knight on c6 is a target. 18.♗g3 ♕h6 19.g5!",
                              linha_ocr="The unprotected knight on G is a target. 18.223 Wh6 19.95!")) == []
    assert _codigos(_registro("", fragmento=True, descartados=3)) == []
    # `8.` de "8. Gashimov" é número, e não lance partido; `(D)` e `W3)` são prosa.
    assert _codigos(_registro("8. Gashimov — Navara, Wijk aan Zee 2012",
                              linha_ocr="8. Gashimov — Navara, Wijk aan Zee 2012")) == []
    assert _codigos(_registro("W3) 1 ♔d1 (D) and now:", linha_ocr="W3) 1 @di (D) and now:")) == []
    # A alternativa com barra da tabela do Nunn.
    assert _codigos(_registro("B: Draw (1...♔h6/h8/♖d2/e2)", linha_ocr="B: Draw (1...8h6/h8/Hd2/e2)",
                              dominio="notation", fonte="glyph", primario="glyph")) == []


@pytest.mark.parametrize("texto", [
    # Chess Evolution 1, p. 34: a avaliação colada ao lance, em toda solução.
    "2.♕xf4 ♕xf6 3.♕h4+–", "If 2...h6 then 3.♘xd7 hxg5 4.♘f6+–.", "3.♘xd7+-",
    "♔xd7 6.♘e5++—", "3...♕xf2 4.♘xc7+ ♔f8 5.e7++—", "2...c6 is met by 3.♖d3 ♕b8 4.♖f3!+–.",
    "(or 8.dxc5 ♕d5 9.f3 ♕xf3 10.c6 ♕xf4 11.♘xf4+–)", "21.♗xc6± and 26.♘g3⩲ are fine",
])
def test_a_avaliacao_colada_ao_lance_nao_e_lance_malformado(texto):
    assert _codigos(_registro(texto)) == []


@pytest.mark.parametrize("texto, dominio, esperado", [
    # p. 34: a figurina cuja casa caiu, no fim da linha de lances.
    ("3.♖e8+ ♘d8 4.♘e5 ♕", "mixed", "malformed_move"),
    # p. 34 e p. 47: o sinal que veio no lugar de uma letra, e o `’s` do motor.
    ("§.Tarrasch — S.Tartakower", "prose", "engine_garbage"),
    ("the typical mistake of simply chasing the opponent,s", "prose", "engine_garbage"),
    # p. 30: a aspa que abre e não fecha.
    ("wins for White. ‘The", "mixed", "engine_garbage"),
    # p. 47: o cisco da trama lido como pontuação, numa linha só dele.
    (":", "unknown", "stray_mark"),
    ("/", "unknown", "stray_mark"),
])
def test_os_residuos_do_yusupov_viram_motivo(texto, dominio, esperado):
    assert esperado in _codigos(_registro(texto, dominio=dominio))


def test_a_figurina_solta_na_prosa_e_a_aspa_fechada_nao_sao_motivo():
    assert _codigos(_registro("the ♘ is strong", dominio="prose")) == []
    assert _codigos(_registro("He said ‘no’ and left.", dominio="prose")) == []
    assert _codigos(_registro("(D)", dominio="prose")) == []


def test_todo_codigo_tem_frase_e_a_procedencia_fica_de_fora():
    for codigo in MOTIVOS:
        assert descrever(codigo, token="x", descartados=1, semelhanca=0.5, motor="a", ancora="b")
    assert descrever("codigo_novo") == "codigo_novo"
    assert descrever("malformed_move") == "«…» tem figurina mas não tem forma de lance"
    assert descrever_codigos(["legacy_adapter", "low_confidence", "low_confidence"]) == [
        "a confiança da leitura ficou abaixo do piso"]


def _pdf(caminho, paginas=2):
    doc = fitz.open()
    for i in range(paginas):
        p = doc.new_page(width=300, height=200)
        p.insert_text((30, 40), f"Página {i + 1}", fontsize=10)
    doc.save(caminho)
    doc.close()
    return caminho


# ----------------------------------------------------------------------
# O leitor: o registro tem a caixa, e o parágrafo lembra as linhas
# ----------------------------------------------------------------------

def test_o_leitor_liga_o_paragrafo_aos_registros_e_o_registro_a_caixa(tmp_path):
    pdf = _pdf(tmp_path / "livro.pdf", paginas=1)
    paginas = livro.extrair(str(pdf), lambda recorte, referencia=None: ("a", 0.99),
                            dpi=150, diagramas="recorte")
    pagina = paginas[0]
    paragrafos = [b for b in pagina.blocos if isinstance(b, livro.Paragrafo)]
    assert paragrafos and pagina.roteamento
    for paragrafo in paragrafos:
        assert len(paragrafo.registros) == len(paragrafo.inicios)
        for i in paragrafo.registros:
            registro = pagina.roteamento[i]
            x1, y1, x2, y2 = registro["caixa"]
            assert 0 <= x1 < x2 <= pagina.largura and 0 <= y1 < y2 <= pagina.altura
            # `pe` é topo + altura mediana; a caixa vai até o box mais fundo.
            assert paragrafo.topo <= y1 < paragrafo.pe


def test_cortar_o_paragrafo_leva_o_registro_da_linha_junto():
    paragrafo = livro.Paragrafo("cabeçalho da página e a primeira linha", topo=0, pe=40,
                                inicios=[0, 20], registros=[4, 5])
    livro._cortar(paragrafo, *livro._linha_da_margem(paragrafo, "alto"))
    assert paragrafo.texto == "e a primeira linha"
    assert paragrafo.inicios == [0] and paragrafo.registros == [5]
