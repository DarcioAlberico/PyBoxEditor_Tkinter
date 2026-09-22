from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.ocr_corpus import (
    CorpusDocument,
    CorpusManifest,
    CorpusPage,
    executar_corpus,
    carregar_manifesto,
    dividir_documentos,
    salvar_manifesto,
)


def _arquivo(path: Path, content: str = "x") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path.as_posix()


def _manifest(tmp_path: Path, *, documents: int = 1) -> CorpusManifest:
    docs = []
    for index in range(documents):
        doc_id = f"book-{index}"
        _arquivo(tmp_path / "sources" / f"{doc_id}.pdf", "pdf")
        reference_path = tmp_path / "references" / doc_id / "p001.json"
        prediction_path = tmp_path / "predictions" / "current" / doc_id / "p001.json"
        image_path = tmp_path / "images" / doc_id / "p001.png"
        _arquivo(reference_path, json.dumps({"text": "texto correto"}))
        _arquivo(prediction_path, json.dumps({"text": "texto cor"}))
        _arquivo(image_path, "png")
        reference = reference_path.relative_to(tmp_path).as_posix()
        prediction = prediction_path.relative_to(tmp_path).as_posix()
        image = image_path.relative_to(tmp_path).as_posix()
        docs.append(CorpusDocument(
            id=doc_id,
            title=f"Livro {index}",
            language="pt",
            source_kind="pdf_scan",
            source=f"sources/{doc_id}.pdf",
            split="train" if index == 0 else "test",
            pages=[CorpusPage(
                id=f"{doc_id}-p001", page_index=0, image=image,
                reference=reference, predictions={"current": prediction},
                domains=("body",), metadata={"difficulty": "clean_body"},
            )],
        ))
    return CorpusManifest(name="books", documents=docs)


def test_manifesto_roundtrip_calcula_hash_e_preserva_metadados(tmp_path: Path):
    manifesto = _manifest(tmp_path)
    caminho = tmp_path / "corpus.json"

    salvar_manifesto(manifesto, caminho, base_dir=tmp_path)
    carregado = carregar_manifesto(caminho, validate_paths=True)

    assert carregado.schema == "pyboxeditor.ocr-corpus/v1"
    assert carregado.documents[0].pages[0].domains == ("body",)
    assert carregado.corpus_sha256
    assert carregado.digest(tmp_path) == carregado.corpus_sha256


def test_manifesto_rejeita_path_absoluto_e_documento_com_split_misto(tmp_path: Path):
    with pytest.raises(ValueError, match="relativo"):
        CorpusPage("p", 0, reference=str(tmp_path / "ref.json"))
    page = CorpusPage("p", 0, reference="ref.json")
    documento = CorpusDocument("book", "Livro", "en", "pdf", "book.pdf", "train", [page])
    manifesto = CorpusManifest("books", [documento])

    assert manifesto.validate() == []

    documento.pages.append(CorpusPage("p2", 1, reference="ref2.json"))
    documento.pages[1].metadata["split"] = "test"
    with pytest.raises(ValueError, match="split"):
        manifesto.validate()


def test_dividir_documentos_mantem_todas_as_paginas_no_mesmo_split(tmp_path: Path):
    manifesto = _manifest(tmp_path, documents=6)

    dividido = dividir_documentos(manifesto, validation_fraction=1 / 6,
                                   test_fraction=1 / 3, seed=7)

    assert {doc.split for doc in dividido.documents} == {"train", "validation", "test"}
    for documento in dividido.documents:
        assert {page.metadata.get("split", documento.split)
                for page in documento.pages} == {documento.split}


def test_executar_corpus_agrega_por_documento_e_engine(tmp_path: Path):
    manifesto = _manifest(tmp_path, documents=2)
    caminho = tmp_path / "corpus.json"
    salvar_manifesto(manifesto, caminho, base_dir=tmp_path)

    relatorio = executar_corpus(caminho, engine="current")

    assert relatorio.pages == 2
    assert relatorio.text is not None
    assert relatorio.metadata["engine"] == "current"
    assert relatorio.metadata["documents"] == ["book-0", "book-1"]
    assert {item.metadata["split"] for item in relatorio.page_results} == {"train", "test"}
