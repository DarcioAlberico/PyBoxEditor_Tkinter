"""
F19 — a altura relativa à linha: mede, separa, e mesmo assim não melhora.

O módulo não é chamado por produção nenhuma; ele serve `medir_altura.py`. Estes
testes existem para que a medição continue reproduzível e para travar as duas
regras de segurança que a tornam interpretável — quem a tipografia não
classifica nunca é trocado, e box girado não é medido.
"""

import pytest

from core import altura_relativa as ar
from core.box_model import BoxEntry


def _box(y1, y2, x1=0, x2=8):
    return BoxEntry("?", x1, y1, x2, y2)


# ----------------------------------------------------------------------
# A classe tipográfica
# ----------------------------------------------------------------------

def test_x_height_e_descendente_tem_topo_em_x():
    """O descendente desce, mas o topo dele é o de x — e o topo é o que decide."""
    for c in "acemnorsuvwxz":
        assert ar.classe_do_char(c) == "x", c
    for c in "gpqy":
        assert ar.classe_do_char(c) == "x", c


def test_maiuscula_digito_e_ascendente_sobem():
    for c in "ABCZ0159":
        assert ar.classe_do_char(c) == "alto", c
    for c in "bdfhklt":
        assert ar.classe_do_char(c) == "alto", c


def test_o_pingo_poe_o_i_e_o_j_no_alto():
    """Medido: o topo do `i` é o do `1` (d' = 0,01). É o pingo que sobe."""
    assert ar.classe_do_char("i") == "alto"
    assert ar.classe_do_char("j") == "alto"


def test_quem_a_tipografia_nao_classifica_fica_de_fora():
    """Figurina, ligadura, pontuação e símbolo não têm classe de topo."""
    for c in ("♗", "fi", ".", "+", "", "±"):
        assert ar.classe_do_char(c) is None, repr(c)


# ----------------------------------------------------------------------
# A medida
# ----------------------------------------------------------------------

def test_o_topo_relativo_e_fracao_da_faixa():
    assert ar.topo_relativo(_box(30, 50), 20, 40) == pytest.approx(0.25)


def test_faixa_de_altura_zero_nao_mede():
    assert ar.topo_relativo(_box(10, 20), 10, 0) is None


def test_minuscula_mede_x_e_maiuscula_mede_alto():
    # x-height fica em 0,30 da faixa; caixa alta, em 0,08 (medido)
    assert ar.classe_medida(_box(30, 60), 0, 100) == "x"
    assert ar.classe_medida(_box(8, 60), 0, 100) == "alto"


def test_perto_do_corte_nao_opina():
    """
    A faixa é `max(y2) - min(y1)` dos boxes da linha, então uma linha sem
    descendente encolhe a faixa e desloca todas as frações juntas. Perto do
    corte essa deriva vale mais que o sinal.
    """
    perto = int(ar.CORTE * 100)
    assert ar.classe_medida(_box(perto, 60), 0, 100) is None


def test_box_girado_nao_e_medido():
    """Para texto vertical (F8.1) a faixa da linha é horizontal."""
    b = _box(30, 60)
    b.angulo = 90
    assert ar.classe_medida(b, 0, 100) is None


def test_faixas_por_linha():
    linhas = [[_box(10, 30), _box(14, 34)], [_box(60, 80)]]
    assert ar.faixas_por_linha(linhas) == [(10, 24), (60, 20)]


def test_faixa_de_linha_vazia():
    assert ar.faixas_por_linha([[]]) == [(0, 0)]


# ----------------------------------------------------------------------
# A desambiguação
# ----------------------------------------------------------------------

def test_troca_a_vencedora_que_nao_cabe_na_altura():
    """`C` medido em x-height, com `c` entre as candidatas."""
    assert ar.desambiguar([("C", 0.6), ("c", 0.3)], "x") == ("c", 0.3)


def test_nao_mexe_quando_a_vencedora_ja_cabe():
    assert ar.desambiguar([("c", 0.6), ("C", 0.3)], "x") is None


def test_nao_mexe_sem_medida():
    assert ar.desambiguar([("C", 0.6), ("c", 0.3)], None) is None


def test_nao_mexe_sem_candidata_que_caiba():
    assert ar.desambiguar([("C", 0.6), ("K", 0.3)], "x") is None


def test_a_cauda_da_distribuicao_nao_decide():
    """
    A rede é peaked — a F14 mediu 0,9994 num acerto. Sem a margem, uma classe
    que ela deu 0,001 decidiria a leitura, e isso é ruído, não segunda opinião.
    """
    assert ar.desambiguar([("C", 0.99), ("c", 0.001)], "x", margem=0.02) is None
    assert ar.desambiguar([("C", 0.99), ("c", 0.001)], "x",
                          margem=0.0005) == ("c", 0.001)


def test_a_figurina_nunca_e_trocada():
    """Metade da segurança do módulo: sem classe de topo, não entra na troca."""
    assert ar.desambiguar([("♗", 0.9), ("B", 0.05)], "x") is None
    assert ar.desambiguar([("C", 0.9), ("♗", 0.5)], "x") is None


def test_sem_candidatas():
    assert ar.desambiguar([], "x") is None
