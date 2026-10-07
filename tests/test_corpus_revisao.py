from __future__ import annotations

import json

import pytest

from core.corpus_revisao import preparar_fila_revisao
from scripts import preparar_revisao_corpus


def _plano():
    return {
        "schema": "pyboxeditor.ocr-corpus-plan/v1",
        "rodada": "rodada.json",
        "candidatos": ["candidatos.json"],
        "plan": {
            "selecionados": [{
                "id": "livro-a-p010",
                "documento": "livro-a",
                "page_index": 10,
                "familias": ["tabela", "prosa"],
                "principal": "tabela",
                "status": "unreviewed",
                "source_pdf": "livro.pdf",
                "source_pdf_sha256": "a" * 64,
                "artifacts": {
                    "draft": "rascunhos/livro-a-p010.txt",
                    "routing": "roteamento/livro-a-p010.json",
                },
            }],
        },
    }


def test_fila_de_revisao_preserva_proveniencia_sem_virar_referencia():
    fila = preparar_fila_revisao(_plano())

    assert fila["schema"] == "pyboxeditor.ocr-corpus-review/v1"
    assert fila["items"][0] == {
        "candidate_id": "livro-a-p010",
        "documento": "livro-a",
        "page_index": 10,
        "source_pdf": "livro.pdf",
        "source_pdf_sha256": "a" * 64,
        "draft": "rascunhos/livro-a-p010.txt",
        "routing": "roteamento/livro-a-p010.json",
        "familias_sugeridas": ["tabela", "prosa"],
        "principal_sugerida": "tabela",
        "status": "pending_review",
    }
    assert "reference" not in fila["items"][0]
    assert "holdout" not in fila["items"][0]


def test_fila_recusa_candidato_que_já_contem_referencia():
    plano = _plano()
    plano["plan"]["selecionados"][0]["reference"] = "ref.txt"

    with pytest.raises(ValueError, match="reference"):
        preparar_fila_revisao(plano)


def test_comando_grava_fila_separada_do_manifesto(tmp_path):
    entrada = tmp_path / "plano.json"
    saida = tmp_path / "fila.json"
    entrada.write_text(json.dumps(_plano()), encoding="utf-8")

    assert preparar_revisao_corpus.main([
        "--plano", str(entrada), "--output", str(saida),
    ]) == 0

    dados = json.loads(saida.read_text(encoding="utf-8"))
    assert dados["schema"] == "pyboxeditor.ocr-corpus-review/v1"
    assert dados["source_plan"] == str(entrada)
    assert dados["items"][0]["status"] == "pending_review"
