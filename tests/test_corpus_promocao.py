from __future__ import annotations

import json
import hashlib

import pytest

from core.corpus_promocao import promover_revisoes, validar_revisoes_com_candidatos
from core.ocr_corpus import CorpusDocument, CorpusManifest
from scripts import promover_corpus


def _manifesto() -> CorpusManifest:
    return CorpusManifest(
        name="corpus-teste",
        documents=[CorpusDocument(
            id="livro-a", title="Livro A", language="en",
            source_kind="pdf_scan", source="livro.pdf", split="test", pages=[]
        )],
    )


def _revisao(**campos):
    return {
        "id": "livro-a-p010",
        "documento": "livro-a",
        "page_index": 10,
        "reference": "referencias/livro-a-p010.txt",
        "familias": ["tabela", "prosa"],
        "principal": "tabela",
        "status": "reviewed",
        "revisor": "ana",
        "revisado_em": "2026-09-26T12:00:00+00:00",
        **campos,
    }


def _candidato(tmp_path, **campos):
    fonte = tmp_path / "livro.pdf"
    fonte.write_bytes(b"pdf original")
    sha256 = hashlib.sha256(fonte.read_bytes()).hexdigest()
    return {
        "id": "livro-a-p010",
        "documento": "livro-a",
        "page_index": 10,
        "status": "unreviewed",
        "source_pdf": str(fonte),
        "source_pdf_sha256": sha256,
        **campos,
    }


def test_validacao_de_revisao_exige_candidato_e_pdf_integro(tmp_path):
    candidato = _candidato(tmp_path)
    revisao = _revisao(
        candidate_id=candidato["id"],
        source_pdf_sha256=candidato["source_pdf_sha256"],
    )

    resultado = validar_revisoes_com_candidatos(
        [revisao], [candidato], base_dir=tmp_path)

    assert resultado == {
        "candidates": 1,
        "reviewed": 1,
        "candidate_ids": ["livro-a-p010"],
        "source_pdf_sha256": [candidato["source_pdf_sha256"]],
    }


def test_validacao_recusa_revisao_sem_candidato_ou_fonte_alterada(tmp_path):
    candidato = _candidato(tmp_path)
    revisao = _revisao(candidate_id=candidato["id"])

    with pytest.raises(ValueError, match="source_pdf_sha256"):
        validar_revisoes_com_candidatos([revisao], [candidato], base_dir=tmp_path)

    candidato["source_pdf_sha256"] = "0" * 64
    revisao["source_pdf_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash"):
        validar_revisoes_com_candidatos([revisao], [candidato], base_dir=tmp_path)

    with pytest.raises(ValueError, match="candidato"):
        validar_revisoes_com_candidatos(
            [_revisao(candidate_id="livro-a-p999", source_pdf_sha256="0" * 64)],
            [candidato], base_dir=tmp_path)


def test_promocao_exige_revisao_e_adiciona_pagina_sem_mutar_manifesto(tmp_path):
    (tmp_path / "referencias").mkdir()
    (tmp_path / "referencias" / "livro-a-p010.txt").write_text(
        "texto conferido", encoding="utf-8")
    manifesto = _manifesto()

    promovido = promover_revisoes(manifesto, [_revisao()], base_dir=tmp_path)

    assert manifesto.documents[0].pages == []
    pagina = promovido.documents[0].pages[0]
    assert pagina.id == "livro-a-p010"
    assert pagina.reference == "referencias/livro-a-p010.txt"
    assert pagina.metadata == {
        "annotation_status": "reviewed",
        "familias": ["tabela", "prosa"],
        "principal": "tabela",
        "candidate_id": "livro-a-p010",
        "reviewer": "ana",
        "reviewed_at": "2026-09-26T12:00:00+00:00",
    }
    assert promovido.corpus_sha256 == ""


def test_promocao_recusa_estado_ou_referencia_invalidos(tmp_path):
    with pytest.raises(ValueError, match="reviewed"):
        promover_revisoes(
            _manifesto(), [_revisao(status="unreviewed")], base_dir=tmp_path)
    with pytest.raises(FileNotFoundError, match="referência"):
        promover_revisoes(_manifesto(), [_revisao()], base_dir=tmp_path)
    with pytest.raises(ValueError, match="revisor"):
        promover_revisoes(
            _manifesto(), [_revisao(revisor="")], base_dir=tmp_path)


def test_promocao_recusa_id_duplicado_e_paginas_fora_do_livro(tmp_path):
    ref = tmp_path / "referencias"
    ref.mkdir()
    (ref / "livro-a-p010.txt").write_text("texto", encoding="utf-8")
    manifesto = _manifesto()

    with pytest.raises(ValueError, match="duplicad"):
        promover_revisoes(manifesto, [_revisao(), _revisao()], base_dir=tmp_path)
    with pytest.raises(ValueError, match="documento"):
        promover_revisoes(
            manifesto, [_revisao(documento="livro-inexistente")], base_dir=tmp_path)


def test_comando_promove_em_arquivo_novo_e_recalcula_manifesto(tmp_path):
    (tmp_path / "referencias").mkdir()
    (tmp_path / "referencias" / "livro-a-p010.txt").write_text(
        "texto conferido", encoding="utf-8")
    origem = tmp_path / "origem.json"
    revisoes = tmp_path / "revisoes.json"
    saida = tmp_path / "promovido.json"
    origem.write_text(json.dumps(_manifesto().to_dict()), encoding="utf-8")
    revisoes.write_text(json.dumps({"revisoes": [_revisao()]}), encoding="utf-8")

    assert promover_corpus.main([
        "--manifesto", str(origem), "--revisoes", str(revisoes),
        "--revisor", "ana", "--output", str(saida),
    ]) == 0
    dados = json.loads(saida.read_text(encoding="utf-8"))
    assert dados["documents"][0]["pages"][0]["metadata"]["annotation_status"] == "reviewed"
    assert dados["corpus_sha256"]
    assert origem.read_text(encoding="utf-8") != saida.read_text(encoding="utf-8")


def test_comando_promove_com_proveniencia_de_candidatos(tmp_path):
    (tmp_path / "referencias").mkdir()
    (tmp_path / "referencias" / "livro-a-p010.txt").write_text(
        "texto conferido", encoding="utf-8")
    origem = tmp_path / "origem.json"
    revisoes = tmp_path / "revisoes.json"
    candidatos = tmp_path / "candidatos.json"
    saida = tmp_path / "promovido.json"
    origem.write_text(json.dumps(_manifesto().to_dict()), encoding="utf-8")
    candidato = _candidato(tmp_path)
    revisao = _revisao(
        candidate_id=candidato["id"],
        source_pdf_sha256=candidato["source_pdf_sha256"],
    )
    revisoes.write_text(json.dumps({"revisoes": [revisao]}), encoding="utf-8")
    candidatos.write_text(json.dumps({"candidatos": [candidato]}), encoding="utf-8")

    assert promover_corpus.main([
        "--manifesto", str(origem), "--revisoes", str(revisoes),
        "--candidatos", str(candidatos), "--revisor", "ana",
        "--output", str(saida),
    ]) == 0
    dados = json.loads(saida.read_text(encoding="utf-8"))
    assert dados["metadata"]["promotion_provenance"]["reviewed"] == 1
    assert dados["metadata"]["promotion_provenance"]["candidate_ids"] == [
        "livro-a-p010"]
    pagina = dados["documents"][0]["pages"][0]
    assert pagina["metadata"]["candidate_id"] == "livro-a-p010"
    assert pagina["metadata"]["source_pdf_sha256"] == candidato["source_pdf_sha256"]
