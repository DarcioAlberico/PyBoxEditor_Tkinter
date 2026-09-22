"""
A família de layout e a rodada do corpus (item 6 da revisão de 2026-09-18).

As quatro páginas de referência medem quatro layouts diferentes, e é esse o
eixo em que o corpus tem de crescer: trinta páginas de prosa mediriam uma coisa
só, com três casas decimais. `core/familias_de_pagina.py` diz a que família uma
página lida pertence, e `scripts/rodada_do_corpus.py` mede o corpus inteiro,
pondera o total, compara com a rodada anterior e diz o que ainda não é medido.

Os testes são de mesa: páginas de mentira, sem PDF e sem modelo.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from core import familias_de_pagina as fam  # noqa: E402
from core.livro import Figura, PaginaExtraida, Paragrafo, Tabela  # noqa: E402


def _pagina(**campos) -> PaginaExtraida:
    campos.setdefault("blocos", [Paragrafo("um parágrafo de prosa")])
    return PaginaExtraida(numero=campos.pop("numero", 0), **campos)


def _linhas(notacao: int, prosa: int) -> list[dict]:
    return ([{"dominio": "notation"}] * notacao) + ([{"dominio": "prose"}] * prosa)


# ----------------------------------------------------------------------
# A família
# ----------------------------------------------------------------------

def test_a_pagina_de_prosa_e_so_prosa():
    assert fam.familias(_pagina()) == {"prosa"}
    assert fam.principal(_pagina()) == "prosa"


def test_a_tabela_ganha_da_prosa_em_volta():
    """Prosa há em toda página; tabela, em quatro de um livro inteiro."""
    pagina = _pagina(blocos=[Paragrafo("texto"), Tabela([["W: Win", "B: Draw"]])])
    assert fam.familias(pagina) == {"tabela", "prosa"}
    assert fam.principal(pagina) == "tabela"


def test_a_pagina_de_imagem_nao_e_mais_nada():
    pagina = _pagina(blocos=[Figura(b"", 10, 10, origem="pagina")],
                     pagina_de_imagem=True)
    assert fam.familias(pagina) == {"imagem"}


def test_as_duas_colunas_e_os_diagramas_saem_da_leitura():
    pagina = _pagina(colunas=2, diagramas=2)
    assert fam.familias(pagina) == {"duas_colunas", "diagramas", "prosa"}
    assert fam.principal(pagina) == "duas_colunas"


def test_a_pagina_e_de_notacao_quando_metade_das_linhas_e_lance():
    assert "notacao" in fam.familias(_pagina(roteamento=_linhas(5, 5)))
    assert "notacao" not in fam.familias(_pagina(roteamento=_linhas(2, 8)))


def test_a_trama_e_o_negativo_vem_do_rotulo_humano_ou_dos_contornos():
    """
    Nenhum dos dois está na `PaginaExtraida`: a trama é da imagem e o negativo
    é do desenho do cabeçalho. Quem os conhece é quem olhou a página.
    """
    assert "trama" in fam.familias(_pagina(), contornos=85_903)
    assert "trama" not in fam.familias(_pagina(), contornos=1_200)
    assert fam.principal(_pagina(colunas=2), declaradas=["negativo"]) == "negativo"
    assert fam.FAMILIA_DA_DIFICULDADE["halftone_panel"] == "trama"


def test_a_cobertura_diz_o_que_o_corpus_ainda_nao_mede():
    paginas = [
        {"documento": "aagaard", "familias": ["notacao", "prosa"]},
        {"documento": "nunn", "familias": ["tabela", "notacao", "prosa"]},
        {"documento": "yusupov", "familias": ["duas_colunas", "prosa"]},
        {"documento": "yusupov", "familias": ["trama", "prosa", "diagramas"]},
    ]
    resumo = fam.resumo(paginas)
    assert resumo["cobertura"]["prosa"] == 4 and resumo["cobertura"]["tabela"] == 1
    assert resumo["faltando"] == ["imagem", "tabela", "trama", "negativo",
                                  "duas_colunas", "diagramas", "notacao"]
    assert resumo["por_livro"]["yusupov"]["prosa"] == 2
    assert fam.faltando(paginas, minimo=1) == ["imagem", "negativo"]


# ----------------------------------------------------------------------
# A rodada
# ----------------------------------------------------------------------

def test_o_total_do_corpus_e_ponderado_pelo_tamanho_da_pagina():
    """
    A média das páginas faria uma de doze tokens pesar como uma de trezentos —
    e o número que se cita é o do livro, não o da página.
    """
    import rodada_do_corpus

    paginas = [
        {"metricas": {"total": {"caracteres": 1000, "erros_de_caractere": 10,
                                "tokens": 200, "erros": 4}}},
        {"metricas": {"total": {"caracteres": 10, "erros_de_caractere": 5,
                                "tokens": 2, "erros": 1}}},
    ]
    totais = rodada_do_corpus._totais(paginas)
    assert round(totais["total"]["cer"], 6) == round(15 / 1010, 6)
    assert round(totais["total"]["wer"], 6) == round(5 / 202, 6)
    # A média simples daria 26%: o que a ponderação evita.
    assert totais["total"]["cer"] < 0.02


def test_a_pagina_sem_metrica_nao_entra_na_conta():
    import rodada_do_corpus

    totais = rodada_do_corpus._totais([{"metricas": None}, {"erro": "PDF ausente"}])
    assert totais["total"]["cer"] == 0.0 and totais["total"]["wer"] == 0.0


def test_o_manifesto_vira_paginas_com_caminhos_resolvidos(tmp_path):
    import rodada_do_corpus

    (tmp_path / "ref").mkdir()
    (tmp_path / "ref" / "p030.txt").write_text("texto", encoding="utf-8")
    manifesto = tmp_path / "corpus.json"
    manifesto.write_text(json.dumps({
        "schema": "pyboxeditor.ocr-corpus/v1",
        "documents": [{
            "id": "aagaard", "title": "Calculation", "language": "en",
            "source": "../livro.pdf",
            "pages": [
                {"id": "aagaard-p030", "page_index": 30,
                 "reference": "ref/p030.txt",
                 "metadata": {"difficulty": "halftone_panel"}},
                {"id": "aagaard-p031", "page_index": 31, "reference": None},
            ]}]}), encoding="utf-8")

    paginas = rodada_do_corpus.paginas_do_manifesto(manifesto)
    assert [pagina["id"] for pagina in paginas] == ["aagaard-p030"], \
        "a página sem referência não entra na rodada"
    assert paginas[0]["referencia"] == (tmp_path / "ref" / "p030.txt").resolve()
    assert paginas[0]["pdf"] == (tmp_path.parent / "livro.pdf").resolve()
    assert paginas[0]["declaradas"] == ["trama"]


def test_a_rodada_anterior_e_o_ponto_de_comparacao(tmp_path):
    import rodada_do_corpus

    (tmp_path / "2026-09-20-1000.json").write_text(json.dumps({
        "paginas": [{"id": "p1", "metricas": {"total": {"cer": 0.0137}}}]}),
        encoding="utf-8")
    (tmp_path / "2026-09-21-1000.json").write_text(json.dumps({
        "paginas": [{"id": "p1", "metricas": {"total": {"cer": 0.0120}}},
                    {"id": "p2", "metricas": None}]}), encoding="utf-8")

    ultima = rodada_do_corpus._ultima_rodada(tmp_path)
    assert rodada_do_corpus._cer_por_pagina(ultima) == {"p1": 0.0120}
    assert rodada_do_corpus._cer_por_pagina(None) == {}
    assert rodada_do_corpus._ultima_rodada(tmp_path / "vazio") is None


def test_o_portao_derruba_a_rodada_quando_uma_pagina_piora():
    """
    Mudança em `core/livro.py` se mede aqui antes de ser commitada. A tolerância
    existe porque o leitor tem ruído de arredondamento, não para perdoar
    regressão: 0,1 ponto percentual num corpus de 1,6% é um oitavo do total.
    """
    import rodada_do_corpus

    medidas = [
        {"id": "p1", "metricas": {"total": {"cer": 0.0150}}},   # piorou 0,13 pp
        {"id": "p2", "metricas": {"total": {"cer": 0.0185}}},   # melhorou
        {"id": "p3", "metricas": {"total": {"cer": 0.0075}}},   # página nova
        {"id": "p4", "metricas": None},                         # sem PDF
    ]
    antes = {"p1": 0.0137, "p2": 0.0187, "p4": 0.0100}
    assert rodada_do_corpus.pioras(medidas, antes, 0.001) == [
        "p1: 1.37% → 1.50%"]
    assert rodada_do_corpus.pioras(medidas, antes, 0.002) == [], \
        "dentro da tolerância não é piora"
    assert rodada_do_corpus.pioras(medidas, {}, 0.001) == [], \
        "sem rodada anterior não há o que comparar"
