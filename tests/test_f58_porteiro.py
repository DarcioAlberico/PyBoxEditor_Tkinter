"""
Testes do porteiro da F58 — quem decide entre desenhar e recortar.

O `diagrama.confiavel` é a única coisa entre uma leitura errada e um diagrama
bonito com a peça trocada no livro exportado. O que estes testes prendem é a
forma da régua, que a `medir_porteiro.py` mediu em 346 tabuleiros:

  - é a **menor** das confianças, não a média — 63 casas firmes não podem
    carregar a que ficou em moeda;
  - a confiança da **ocupação** conta junto com a da peça, porque a rede de
    ocupação é hoje a mais fraca das duas (F8.4: 99,38% contra 99,62%);
  - posição impossível é veto seco, sem consultar piso nenhum.

Nada aqui carrega modelo: as leituras são montadas à mão, que é o que permite
pôr uma casa exatamente no piso e outra logo abaixo dele.

Rodar sem pytest:      python tests/test_f58_porteiro.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import diagrama


def _leitura(pecas, *, ocupacao_vazia=1.0):
    """
    Uma `Leitura` de 64 casas com as peças que se pedir.

    `pecas` é `{(linha, coluna): (símbolo, confiança, confiança de ocupação)}`.
    As casas que sobram entram vazias e firmes, para que o teste que mexe numa
    casa esteja medindo aquela casa.
    """
    leitura = diagrama.Leitura(caixa=(0, 0, 64, 64))
    for r in range(8):
        for c in range(8):
            if (r, c) in pecas:
                simbolo, conf, conf_ocup = pecas[(r, c)]
                leitura.casas.append(
                    diagrama.Casa(r, c, simbolo, conf,
                                  confianca_ocupacao=conf_ocup))
            else:
                leitura.casas.append(
                    diagrama.Casa(r, c, None,
                                  confianca_ocupacao=ocupacao_vazia))
    return leitura


def _legal(conf=1.0, conf_ocup=1.0):
    """Dois reis e nada mais: a menor posição que passa na plausibilidade."""
    return {(0, 4): ("k", conf, conf_ocup), (7, 4): ("K", conf, conf_ocup)}


def test_a_leitura_firme_vira_desenho():
    passa, motivo = diagrama.confiavel(_leitura(_legal()))
    assert passa and motivo == ""


def test_a_casa_mais_fraca_barra_o_tabuleiro_inteiro():
    """
    É a decisão de desenho da fase: régua de mínimo, não de média. Com 63 casas
    a 100% e uma a 60%, uma média passaria a 99,4% — e o desenho sairia com a
    peça errada em algum lugar.
    """
    pecas = _legal()
    pecas[(3, 3)] = ("Q", 0.60, 1.0)
    passa, motivo = diagrama.confiavel(_leitura(pecas))
    assert not passa
    assert "60%" in motivo and "peça" in motivo


def test_a_confianca_da_ocupacao_conta_junto():
    """
    A casa não tem peça nenhuma, e mesmo assim decide: se a rede da F7.5 ficou
    em dúvida sobre haver peça ali, o tabuleiro pode estar com uma peça a mais
    ou a menos, e nenhuma confiança de identidade veria isso.
    """
    leitura = _leitura(_legal())
    leitura.casas[27].confianca_ocupacao = 0.55
    passa, motivo = diagrama.confiavel(leitura)
    assert not passa
    assert "haver peça" in motivo


def test_a_posicao_impossivel_e_veto_seco():
    """
    Não consulta piso: posição impossível é leitura errada por definição, então
    barrá-la nunca custa um tabuleiro certo. Aqui, dois reis brancos.
    """
    pecas = _legal()
    pecas[(0, 4)] = ("K", 1.0, 1.0)
    passa, motivo = diagrama.confiavel(_leitura(pecas), piso=0.0)
    assert not passa
    assert "impossível" in motivo


def test_sem_leitura_nao_ha_desenho():
    vazia = diagrama.Leitura(caixa=(0, 0, 0, 0))
    passa, motivo = diagrama.confiavel(vazia)
    assert not passa and motivo

    passa, motivo = diagrama.confiavel(_leitura({}), piso=0.0)
    assert not passa
    assert "nenhuma peça" in motivo


def test_o_piso_medido_e_o_padrao_e_da_para_afrouxar():
    """
    O 0,98 é o joelho da curva medida em 346 tabuleiros, e é o padrão; ele é
    parâmetro para quem quiser medir outro, não uma lei do módulo.
    """
    assert diagrama.PISO_DO_PORTEIRO == 0.98

    pecas = _legal(conf=0.90)
    assert not diagrama.confiavel(_leitura(pecas))[0]
    assert diagrama.confiavel(_leitura(pecas), piso=0.80)[0]


def test_o_piso_e_inclusivo_na_borda():
    """Casa exatamente no piso passa; um centésimo abaixo, não."""
    assert diagrama.confiavel(_leitura(_legal(conf=0.98)))[0]
    assert not diagrama.confiavel(_leitura(_legal(conf=0.97)))[0]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
