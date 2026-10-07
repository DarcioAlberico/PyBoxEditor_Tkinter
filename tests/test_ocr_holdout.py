import json
import hashlib
from pathlib import Path

import pytest

from core.ocr_corpus import CorpusDocument, CorpusManifest, CorpusPage, salvar_manifesto
from core.ocr_holdout import carregar_selecao, selecionar_holdout
from scripts import preparar_fase7


def _manifesto(tmp_path: Path, *, split="holdout", synthetic=False,
               annotation_status="reviewed") -> Path:
    (tmp_path / "book.pdf").write_bytes(b"pdf")
    (tmp_path / "page.png").write_bytes(b"image")
    (tmp_path / "reference.txt").write_text("texto revisado\n", encoding="utf-8")
    manifesto = CorpusManifest(
        name="holdout-real",
        documents=[CorpusDocument(
            id="book-a", title="Book A", language="pt", source_kind="pdf_scan",
            source="book.pdf", split=split,
            pages=[CorpusPage(
                id="book-a-p001", page_index=1, image="page.png",
                reference="reference.txt",
                metadata={
                    "synthetic": synthetic,
                    "annotation_status": annotation_status,
                },
            )],
        )],
    )
    caminho = tmp_path / "corpus.json"
    salvar_manifesto(manifesto, caminho, base_dir=tmp_path)
    return caminho


def test_selecionar_holdout_exige_pagina_real_revisada_e_preserva_hash(tmp_path):
    caminho = _manifesto(tmp_path)

    selecao = selecionar_holdout(caminho)

    assert selecao.corpus_sha256
    assert selecao.document_ids == ("book-a",)
    assert selecao.pages[0].page_id == "book-a-p001"
    assert selecao.pages[0].reference == tmp_path / "reference.txt"


def test_selecionar_holdout_rejeita_documento_sem_split_holdout(tmp_path):
    caminho = _manifesto(tmp_path, split="test")

    with pytest.raises(ValueError, match="holdout"):
        selecionar_holdout(caminho)


def test_selecionar_holdout_rejeita_pagina_sintetica(tmp_path):
    caminho = _manifesto(tmp_path, synthetic=True)

    with pytest.raises(ValueError, match="sint.tica"):
        selecionar_holdout(caminho)


def test_selecionar_holdout_rejeita_revisao_ausente(tmp_path):
    caminho = _manifesto(tmp_path, annotation_status="unreviewed")

    with pytest.raises(ValueError, match="revis"):
        selecionar_holdout(caminho)


def test_selecao_pode_ser_materializada_com_proveniencia(tmp_path):
    caminho = _manifesto(tmp_path)
    selecao = selecionar_holdout(caminho)

    saida = selecao.salvar(tmp_path / "holdout.selection.json")

    dados = json.loads(saida.read_text(encoding="utf-8"))
    assert dados["schema"] == "pyboxeditor.ocr-holdout/v1"
    assert dados["corpus_sha256"] == selecao.corpus_sha256
    assert dados["pages"][0]["page_id"] == "book-a-p001"


def test_carregar_selecao_revalida_o_corpus_de_origem(tmp_path):
    manifesto = _manifesto(tmp_path)
    selecao = selecionar_holdout(manifesto)
    caminho = selecao.salvar(tmp_path / "holdout.selection.json")

    carregada = carregar_selecao(caminho)

    assert carregada.corpus_sha256 == selecao.corpus_sha256
    caminho.write_text(
        caminho.read_text(encoding="utf-8").replace(
            selecao.corpus_sha256, "0" * 64
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="desatualizada"):
        carregar_selecao(caminho)


def test_comando_fase7_holdout_grava_selecao_auditavel(tmp_path):
    manifesto = _manifesto(tmp_path)
    saida = tmp_path / "holdout.selection.json"

    assert preparar_fase7.main([
        "holdout", str(manifesto), "--output", str(saida)
    ]) == 0

    assert json.loads(saida.read_text(encoding="utf-8"))["pages"]


def _dataset_de_linhas_proveniente(tmp_path: Path, selecao, *, corpus_sha256=None):
    dataset = tmp_path / "holdout-linhas"
    (dataset / "images").mkdir(parents=True)
    imagem = dataset / "images" / "linha_00001.png"
    from PIL import Image
    Image.new("L", (80, 24), 255).save(imagem)
    (dataset / "rec_gt.txt").write_text(
        "images/linha_00001.png\ttexto revisado\n", encoding="utf-8")
    pagina = selecao.pages[0]
    fonte = pagina.image.read_bytes()
    (dataset / "provenance.json").write_text(json.dumps({
        "schema": "pyboxeditor.ocr-line-holdout/v1",
        "corpus_sha256": corpus_sha256 or selecao.corpus_sha256,
        "lines": [{
            "image": "images/linha_00001.png",
            "document_id": pagina.document_id,
            "page_id": pagina.page_id,
            "page_index": pagina.page_index,
            "source_image_sha256": hashlib.sha256(fonte).hexdigest(),
            "bbox": [0, 0, 80, 24],
        }],
    }, ensure_ascii=False), encoding="utf-8")
    return dataset


def test_holdout_de_linhas_exige_proveniencia_por_imagem(tmp_path):
    manifesto = _manifesto(tmp_path)
    selecao = selecionar_holdout(manifesto)
    dataset = _dataset_de_linhas_proveniente(tmp_path, selecao)

    from core.ocr_holdout import validar_proveniencia_de_linhas
    resultado = validar_proveniencia_de_linhas(dataset, selecao)

    assert resultado["schema"] == "pyboxeditor.ocr-line-holdout/v1"
    assert resultado["lines"] == 1
    assert resultado["page_ids"] == ["book-a-p001"]


def test_holdout_de_linhas_rejeita_hash_do_corpus_desatualizado(tmp_path):
    manifesto = _manifesto(tmp_path)
    selecao = selecionar_holdout(manifesto)
    dataset = _dataset_de_linhas_proveniente(tmp_path, selecao,
                                              corpus_sha256="0" * 64)

    from core.ocr_holdout import validar_proveniencia_de_linhas
    with pytest.raises(ValueError, match="corpus"):
        validar_proveniencia_de_linhas(dataset, selecao)


def test_comando_de_holdout_valida_dataset_de_linhas(tmp_path, capsys):
    manifesto = _manifesto(tmp_path)
    selecao = selecionar_holdout(manifesto)
    dataset = _dataset_de_linhas_proveniente(tmp_path, selecao)

    from scripts import validar_holdout_corpus
    assert validar_holdout_corpus.main([
        str(manifesto), "--dataset-linhas", str(dataset)
    ]) == 0

    assert "line_dataset_sha256" in capsys.readouterr().out
