from __future__ import annotations

import json

import pytest

from core.livro import PaginaExtraida, Paragrafo, Tabela
from core.corpus_candidatos import candidato_de_pagina
from scripts import descobrir_candidatos_corpus


def test_candidato_preserva_sinais_e_separa_rotulo_de_referencia():
    pagina = PaginaExtraida(
        numero=4,
        blocos=[Paragrafo("1. e4 e5"), Tabela([["W", "B"]])],
        diagramas=1,
        colunas=2,
        roteamento=[{"dominio": "notation"}, {"dominio": "notation"}],
    )

    candidato = candidato_de_pagina(
        "livro-a", 5, pagina, pdf="/dados/livro-a.pdf",
        declaradas=("negativo",),
    )

    assert candidato["id"] == "livro-a-p005"
    assert candidato["documento"] == "livro-a"
    assert candidato["page_index"] == 5
    assert candidato["familias"] == [
        "tabela", "negativo", "duas_colunas", "diagramas", "notacao",
        "prosa",
    ]
    assert candidato["principal"] == "tabela"
    assert candidato["status"] == "unreviewed"
    assert candidato["source_pdf"] == "/dados/livro-a.pdf"
    assert "source_pdf_sha256" not in candidato
    assert candidato["declared_families"] == ["negativo"]
    assert candidato["signals"] == {
        "pagina_de_imagem": False,
        "colunas": 2,
        "diagramas": 1,
        "leitura": "imagem",
        "roteamento": {"linhas": 2, "dominios": {"notation": 2}},
    }
    assert "reference" not in candidato
    assert "holdout" not in candidato


def test_candidato_de_pagina_rejeita_identidade_insegura():
    pagina = PaginaExtraida(numero=0)

    try:
        candidato_de_pagina("", 1, pagina)
    except ValueError as erro:
        assert "documento" in str(erro)
    else:
        raise AssertionError("documento vazio deveria ser rejeitado")


def test_comando_descobre_candidatos_sem_promover_referencia(tmp_path, monkeypatch):
    pdf = tmp_path / "livro.pdf"
    saida = tmp_path / "candidatos.json"
    pdf.write_bytes(b"pdf")

    pagina = PaginaExtraida(numero=0, blocos=[Paragrafo("texto")])

    monkeypatch.setattr(
        descobrir_candidatos_corpus,
        "_extrair_paginas",
        lambda **kwargs: [pagina],
    )

    assert descobrir_candidatos_corpus.main([
        str(pdf), "--documento", "livro-a", "--paginas", "1",
        "--output", str(saida),
    ]) == 0

    dados = json.loads(saida.read_text(encoding="utf-8"))
    assert dados["schema"] == "pyboxeditor.ocr-corpus-candidates/v1"
    assert dados["candidatos"][0]["status"] == "unreviewed"
    assert dados["source"]["page_index_base"] == 1
    assert len(dados["source"]["pdf_sha256"]) == 64
    assert dados["candidatos"][0]["source_pdf_sha256"] == dados["source"]["pdf_sha256"]
    assert "reference" not in dados["candidatos"][0]
    artefatos = dados["candidatos"][0]["artifacts"]
    assert artefatos["draft"] == "rascunhos/livro-a-p001.txt"
    assert artefatos["routing"] == "roteamento/livro-a-p001.json"
    assert (saida.parent / artefatos["draft"]).read_text(encoding="utf-8") == "texto\n"
    assert json.loads((saida.parent / artefatos["routing"]).read_text(
        encoding="utf-8")) == []


def test_comando_recusa_pagina_repetida(tmp_path):
    pdf = tmp_path / "livro.pdf"
    pdf.write_bytes(b"pdf")

    with pytest.raises(SystemExit, match="repetida"):
        descobrir_candidatos_corpus.main([
            str(pdf), "--documento", "livro-a", "--paginas", "1", "1",
            "--output", str(tmp_path / "candidatos.json"),
        ])
