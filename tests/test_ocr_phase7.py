from __future__ import annotations

import json

from core.editorial_model import (
    Decision,
    EditorialBlock,
    EditorialDocument,
    EditorialPage,
    Evidence,
    SourceRef,
)
from core.editorial_review import ReviewSession
from core.ocr_phase7 import (
    ActiveSampler,
    CalibrationObservation,
    CorrectionDataset,
    CorpusItem,
    WeightManifest,
    calibrate_domains,
    evaluate_holdout,
    split_corpus,
)


def _document() -> EditorialDocument:
    ref = SourceRef("book", 0, (1, 2, 100, 40), "hash", "raster")
    evidence = Evidence("ev", ref, observed_text="texto", confidence=.45)
    block = EditorialBlock(
        "paragraph-1", "paragraph", 0, [ref],
        Decision("texto errado", ["ev"], "automatic", ["low_confidence"]),
        metadata={"domain": "body", "layout": "single-column"},
    )
    page = EditorialPage("book-p0001", 0, [ref], [block], [evidence])
    return EditorialDocument("book", "Livro", "pt", [page])


def test_correcoes_sao_coletadas_com_versao_e_roundtrip(tmp_path):
    session = ReviewSession(_document(), user="editor")
    session.edit("paragraph-1", "texto correto")
    dataset = CorrectionDataset.from_document(session.document, name="book-corrections")

    assert len(dataset.records) == 1
    assert dataset.records[0].before == "texto errado"
    assert dataset.records[0].after == "texto correto"
    assert dataset.records[0].domain == "body"

    path = dataset.save(tmp_path / "corrections.json")
    loaded = CorrectionDataset.load(path)
    assert loaded.version == dataset.version
    assert loaded.digest() == dataset.digest()
    assert json.loads(path.read_text(encoding="utf-8"))["checksum"]


def test_split_isola_holdout_real_sintetico_e_grupos_editoriais():
    records = [
        CorpusItem("a", "book-a", "book-a", "editor-a", "source-a", "two-column", "body"),
        CorpusItem("b", "book-b", "book-b", "editor-b", "source-b", "body", "body"),
        CorpusItem("c", "book-c", "book-c", "editor-c", "source-c", "diagram", "diagram"),
        CorpusItem("synthetic", "synthetic", "synthetic", "generated", "generated", "clean", "body", synthetic=True),
        CorpusItem("holdout", "holdout", "book-h", "editor-h", "source-h", "clean", "body", holdout=True),
    ]
    split = split_corpus(records, validation_fraction=.34, test_fraction=.34, seed=3)

    assert [item.id for item in split.synthetic] == ["synthetic"]
    assert [item.id for item in split.holdout] == ["holdout"]
    assert not set(item.id for item in split.synthetic) & set(item.id for item in split.train)
    groups = {}
    for name in ("train", "validation", "test"):
        for item in getattr(split, name):
            for key in (item.book_id, item.editor_id, item.source_id, item.layout):
                assert key not in groups or groups[key] == name
                groups[key] = name


def test_active_learning_combina_incerteza_e_impacto_com_ordem_reprodutivel():
    samples = ActiveSampler(seed=7).select([
        {"id": "confiante", "confidence": .98, "impact": 100, "domain": "diagram"},
        {"id": "incerto", "confidence": .25, "impact": 20, "domain": "body"},
        {"id": "critico", "confidence": .55, "impact": 100, "domain": "diagram"},
    ], 2)

    assert [sample.item_id for sample in samples] == ["critico", "incerto"]
    assert samples[0].score > samples[1].score


def test_gate_de_holdout_exige_melhoria_fora_do_corpus_de_correcoes():
    resultado = evaluate_holdout([True, False, True, True], [True, True, True, True],
                                 minimum_delta=.1)
    assert resultado.improved is True
    assert resultado.delta == .25
    assert evaluate_holdout([.9, .8], [.95, .85], higher_is_better=False).improved is False


def test_calibracao_por_dominio_produz_relatorio_de_confiabilidade():
    observations = [
        CalibrationObservation("body", .9, True),
        CalibrationObservation("body", .9, False),
        CalibrationObservation("body", .6, True),
        CalibrationObservation("diagram", .8, True),
        CalibrationObservation("diagram", .2, False),
    ]
    report = calibrate_domains(observations, bins=5)

    assert set(report.domains) == {"body", "diagram"}
    assert report.for_domain("body").samples == 3
    assert report.for_domain("body").after_ece <= report.for_domain("body").before_ece + .2
    assert report.reliability["diagram"]


def test_manifesto_de_peso_verifica_checksum_e_compatibilidade(tmp_path):
    weight = tmp_path / "model.pth"
    weight.write_bytes(b"weights-v1")
    manifest = WeightManifest.from_file(
        weight, model_id="line-crnn", schema="weights/v1",
        pipeline_version="editorial-pipeline/v4", config={"alphabet": "abc"},
    )
    path = manifest.save(tmp_path / "model.manifest.json")

    assert WeightManifest.load(path).verify(weight)
    assert WeightManifest.load(path).compatibility(
        schema="weights/v1", pipeline_version="editorial-pipeline/v4",
        config={"alphabet": "abc"},
    ).compatible
    weight.write_bytes(b"tampered")
    assert not WeightManifest.load(path).verify(weight)
    assert not WeightManifest.load(path).compatibility(
        schema="weights/v1", pipeline_version="other",
    ).compatible
