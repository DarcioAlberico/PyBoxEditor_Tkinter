from __future__ import annotations

import json

import pytest

from core.corpus_planejamento import planejar_amostragem
from scripts import planejar_corpus


def test_planejamento_cobre_deficits_por_livro_com_selecao_deterministica():
    paginas = [
        {"id": "a-001", "documento": "a", "familias": ["prosa"]},
        {"id": "b-001", "documento": "b", "familias": ["prosa"]},
    ]
    candidatos = [
        {"id": "b-010", "documento": "b", "page_index": 10,
         "familias": ["imagem", "diagramas"]},
        {"id": "a-010", "documento": "a", "page_index": 10,
         "familias": ["tabela", "diagramas"]},
        {"id": "a-011", "documento": "a", "page_index": 11,
         "familias": ["negativo"]},
        {"id": "b-011", "documento": "b", "page_index": 11,
         "familias": ["negativo"]},
    ]

    plano = planejar_amostragem(paginas, candidatos, minimo=1)

    assert [item["id"] for item in plano["selecionados"]] == [
        "a-010", "b-010", "a-011", "b-011"]
    assert plano["faltando"] == {
        "a": ["imagem", "trama", "duas_colunas", "notacao"],
        "b": ["tabela", "trama", "duas_colunas", "notacao"],
    }
    assert all(item["status"] == "unreviewed" for item in plano["selecionados"])
    assert plano["necessidades_iniciais"]["a"] == [
        "imagem", "tabela", "trama", "negativo", "duas_colunas", "diagramas",
        "notacao"]


def test_planejamento_respeita_limite_e_recusa_candidato_sem_identidade():
    paginas = [{"id": "a-001", "documento": "a", "familias": ["prosa"]}]
    candidatos = [{"documento": "a", "familias": ["tabela"]}]

    with pytest.raises(ValueError, match="id"):
        planejar_amostragem(paginas, candidatos, minimo=1, limite=1)


def test_planejamento_recusa_candidato_que_ja_tem_referencia_ou_holdout():
    candidato = {
        "id": "a-010", "documento": "a", "familias": ["tabela"],
        "reference": "referencia/a-010.txt",
    }

    with pytest.raises(ValueError, match="reference"):
        planejar_amostragem([], [candidato], minimo=1)


def test_planejamento_recusa_mesma_pagina_com_id_diferente():
    paginas = [{"id": "a-001", "documento": "a", "page_index": 1,
                "familias": ["prosa"]}]
    candidato = {"id": "outro-id", "documento": "a", "page_index": 1,
                 "familias": ["tabela"]}

    with pytest.raises(ValueError, match="já presente"):
        planejar_amostragem(paginas, [candidato], minimo=1)


def test_planejamento_recusa_candidatos_repetidos_por_pagina():
    candidatos = [
        {"id": "a-010", "documento": "a", "page_index": 10,
         "familias": ["tabela"]},
        {"id": "a-010-alt", "documento": "a", "page_index": 10,
         "familias": ["negativo"]},
    ]

    with pytest.raises(ValueError, match="mesma página"):
        planejar_amostragem([], candidatos, minimo=1)


def test_comando_grava_plano_separado_do_manifesto_oficial(tmp_path):
    rodada = tmp_path / "rodada.json"
    candidatos = tmp_path / "candidatos.json"
    saida = tmp_path / "plano.json"
    rodada.write_text('{"paginas": [{"id": "a-001", "documento": "a", '
                       '"familias": ["prosa"]}]}', encoding="utf-8")
    candidatos.write_text('{"candidatos": [{"id": "a-010", "documento": "a", '
                           '"page_index": 10, "familias": ["tabela"]}]}',
                          encoding="utf-8")

    assert planejar_corpus.main([
        "--rodada", str(rodada), "--candidatos", str(candidatos),
        "-o", str(saida), "--minimo", "1",
    ]) == 0
    plano = json.loads(saida.read_text(encoding="utf-8"))
    assert plano["schema"] == "pyboxeditor.ocr-corpus-plan/v1"
    assert plano["candidatos"] == [str(candidatos)]
    assert plano["plan"]["selecionados"][0]["status"] == "unreviewed"


def test_comando_agrega_varias_filas_de_candidatos(tmp_path):
    rodada = tmp_path / "rodada.json"
    primeiro = tmp_path / "primeiro.json"
    segundo = tmp_path / "segundo.json"
    saida = tmp_path / "plano.json"
    rodada.write_text('{"paginas": [{"id": "a-001", "documento": "a", '
                       '"familias": ["prosa"]}]}', encoding="utf-8")
    primeiro.write_text('{"candidatos": [{"id": "a-010", "documento": "a", '
                         '"page_index": 10, "familias": ["tabela"]}]}',
                        encoding="utf-8")
    segundo.write_text('{"candidatos": [{"id": "a-011", "documento": "a", '
                        '"page_index": 11, "familias": ["negativo"]}]}',
                       encoding="utf-8")

    assert planejar_corpus.main([
        "--rodada", str(rodada), "--candidatos", str(primeiro), str(segundo),
        "-o", str(saida), "--minimo", "1",
    ]) == 0
    plano = json.loads(saida.read_text(encoding="utf-8"))
    assert plano["candidatos"] == [str(primeiro), str(segundo)]
    assert [item["id"] for item in plano["plan"]["selecionados"]] == [
        "a-010", "a-011"]
