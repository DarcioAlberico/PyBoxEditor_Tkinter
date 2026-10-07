from __future__ import annotations

import json
import importlib.util
from pathlib import Path

import pytest

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
    load_split_manifest,
    split_corpus,
)
_PREPARAR_FASE7 = Path(__file__).resolve().parents[1] / "scripts" / "preparar_fase7.py"
_SPEC = importlib.util.spec_from_file_location("pyboxeditor_preparar_fase7", _PREPARAR_FASE7)
preparar_fase7 = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(preparar_fase7)


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


def test_ocr14_so_entra_na_fase7_depois_de_confirmacao_explicita():
    entrada = {
        "arquivo": "revisao_ocr14/⩲/aagaard_p030_l002b004.png",
        "esperado": "⩲",
        "lido": "±",
        "confianca": 1.0,
        "dominio": "notation",
        "especie": "troca",
        "token_esperado": "g3⩲",
        "token_lido": "g3±",
        "caixa": [10, 20, 30, 40],
        "pagina": 30,
        "linha": 2,
        "indice_do_box": 4,
        "rotulo_confirmado": True,
        "rotulo": "⩲",
        "revisor": "editor",
    }

    dataset = CorrectionDataset.from_ocr14([entrada], name="ocr14-reviewed")

    assert len(dataset.records) == 1
    record = dataset.records[0]
    assert record.before == "±"
    assert record.after == "⩲"
    assert record.domain == "notation"
    assert record.kind == "glyph"
    assert record.editor == "editor"
    assert record.synthetic is False
    assert record.metadata["source"] == "ocr14"
    assert record.metadata["especie"] == "troca"
    assert record.metadata["caixa"] == [10, 20, 30, 40]


def test_split_ocr14_exige_proveniencia_verificada(tmp_path):
    entrada = {
        "arquivo": "revisao_ocr14/y/recorte.png",
        "lido": "x", "dominio": "notation",
        "rotulo_confirmado": True, "rotulo": "y",
    }
    dataset = CorrectionDataset.from_ocr14([entrada], name="ocr14-reviewed")
    caminho = dataset.save(tmp_path / "ocr14.json")

    with pytest.raises(ValueError, match="proven"):
        preparar_fase7.main([
            "split", str(caminho), "-o", str(tmp_path / "split.json")
        ])


def test_split_ocr14_exige_hash_dos_recortes(tmp_path):
    entrada = {
        "arquivo": "revisao_ocr14/y/recorte.png",
        "lido": "x", "dominio": "notation",
        "rotulo_confirmado": True, "rotulo": "y",
    }
    dataset = CorrectionDataset.from_ocr14([entrada], name="ocr14-reviewed")
    dataset.metadata["review_provenance"] = {"verified": True}
    caminho = dataset.save(tmp_path / "ocr14-sem-hash.json")

    with pytest.raises(ValueError, match="hash dos recortes"):
        preparar_fase7.main([
            "split", str(caminho), "-o", str(tmp_path / "split.json")
        ])


def test_ocr14_nao_pode_promover_quarentena_sem_rotulo_confirmado():
    entrada = {
        "arquivo": "revisao_ocr14/⩲/recorte.png",
        "esperado": "⩲",
        "lido": "±",
        "dominio": "notation",
        "rotulo_confirmado": False,
    }

    with pytest.raises(ValueError, match="confirmação humana"):
        CorrectionDataset.from_ocr14([entrada], name="ocr14-unreviewed")


def test_ocr14_recusa_o_mesmo_recorte_duas_vezes():
    entrada = {
        "arquivo": "revisao_ocr14/y/recorte.png",
        "lido": "x", "dominio": "notation",
        "rotulo_confirmado": True, "rotulo": "y",
    }

    with pytest.raises(ValueError, match="recorte OCR-14 duplicado"):
        CorrectionDataset.from_ocr14([entrada, dict(entrada)], name="duplicado")


def test_ocr14_dataset_recusa_rotulo_com_multiplos_glifos():
    entrada = {
        "arquivo": "revisao_ocr14/y/recorte.png",
        "lido": "x", "dominio": "notation",
        "rotulo_confirmado": True, "rotulo": "xy",
    }

    with pytest.raises(ValueError, match="um único glifo"):
        CorrectionDataset.from_ocr14([entrada], name="rotulo-invalido")


def test_ocr14_importacao_estrita_recusa_relatorio_sem_recortes():
    with pytest.raises(ValueError, match="não contém recortes confirmados"):
        CorrectionDataset.from_ocr14([], exigir_registros=True)


def test_ocr14_modo_estrito_confere_arquivo_e_guarda_hash(tmp_path):
    arquivo = tmp_path / "revisao_ocr14" / "y" / "recorte.png"
    arquivo.parent.mkdir(parents=True)
    arquivo.write_bytes(b"recorte conferido")
    entrada = {
        "arquivo": "revisao_ocr14/y/recorte.png",
        "lido": "x", "dominio": "notation",
        "rotulo_confirmado": True, "rotulo": "y",
    }

    dataset = CorrectionDataset.from_ocr14(
        [entrada], name="ocr14-estrito", base_dir=tmp_path,
        exigir_arquivos=True)

    assert len(dataset.records[0].metadata["arquivo_sha256"]) == 64


def test_ocr14_modo_estrito_recusa_arquivo_ausente_e_traversal(tmp_path):
    entrada = {
        "arquivo": "revisao_ocr14/y/ausente.png",
        "lido": "x", "dominio": "notation",
        "rotulo_confirmado": True, "rotulo": "y",
    }
    with pytest.raises(FileNotFoundError, match="recorte OCR-14 ausente"):
        CorrectionDataset.from_ocr14(
            [entrada], base_dir=tmp_path, exigir_arquivos=True)

    entrada["arquivo"] = "../fora.png"
    with pytest.raises(ValueError, match="fora do base_dir"):
        CorrectionDataset.from_ocr14(
            [entrada], base_dir=tmp_path, exigir_arquivos=True)


def test_comando_fase7_importa_relatorio_ocr14_revisado(tmp_path):
    relatorio = tmp_path / "ocr14.json"
    saida = tmp_path / "dataset.json"
    relatorio.write_text(json.dumps({"pdf": "livro.pdf", "paginas": {"30": {"recortes": [{
        "arquivo": "revisao_ocr14/y/recorte.png",
        "esperado": "y", "lido": "x", "dominio": "notation",
        "especie": "troca", "pagina": 30, "rotulo": "y",
        "rotulo_confirmado": True, "revisor": "editor",
    }]}}}, ensure_ascii=False), encoding="utf-8")

    assert preparar_fase7.main([
        "ocr14", str(relatorio), "-o", str(saida), "--nome", "ocr14-round",
    ]) == 0
    dataset = CorrectionDataset.load(saida)
    assert dataset.name == "ocr14-round"
    assert dataset.records[0].after == "y"
    assert dataset.records[0].document_id == "livro.pdf"


def test_comando_fase7_modo_estrito_confere_recorte(tmp_path):
    recorte = tmp_path / "revisao_ocr14" / "y" / "recorte.png"
    recorte.parent.mkdir(parents=True)
    recorte.write_bytes(b"recorte")
    relatorio = tmp_path / "ocr14.json"
    saida = tmp_path / "dataset.json"
    relatorio.write_text(json.dumps({"pdf": "livro.pdf", "paginas": {"30": {
        "recortes": [{
            "arquivo": "revisao_ocr14/y/recorte.png",
            "lido": "x", "dominio": "notation", "pagina": 30,
            "rotulo": "y", "rotulo_confirmado": True,
        }]}}}), encoding="utf-8")

    assert preparar_fase7.main([
        "ocr14", str(relatorio), "-o", str(saida),
        "--base-dir", str(tmp_path), "--exigir-arquivos",
    ]) == 0
    dataset = CorrectionDataset.load(saida)
    assert dataset.records[0].metadata["arquivo_sha256"]


def test_comando_fase7_modo_estrito_recusa_relatorio_vazio(tmp_path):
    relatorio = tmp_path / "ocr14-vazio.json"
    saida = tmp_path / "dataset.json"
    relatorio.write_text(json.dumps({"pdf": "livro.pdf", "paginas": {}}),
                         encoding="utf-8")

    with pytest.raises(ValueError, match="não contém recortes confirmados"):
        preparar_fase7.main([
            "ocr14", str(relatorio), "-o", str(saida), "--exigir-registros",
        ])


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


def test_manifesto_de_split_tem_schema_e_revalida_vazamento(tmp_path):
    registros = [
        CorpusItem("a", "doc-a", "book-a", "editor-a", "source-a",
                   "single-column", "body"),
        CorpusItem("h", "doc-h", "book-h", "editor-h", "source-h",
                   "two-column", "body", holdout=True),
    ]
    caminho = tmp_path / "split.json"
    caminho.write_text(json.dumps(
        split_corpus(registros, validation_fraction=0, test_fraction=0).to_dict(),
        ensure_ascii=False), encoding="utf-8")

    carregado = load_split_manifest(caminho)

    assert [item.id for item in carregado.train] == ["a"]
    assert [item.id for item in carregado.holdout] == ["h"]

    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados["holdout"][0]["book_id"] = "book-a"
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(ValueError, match="vazamento"):
        load_split_manifest(caminho)


def test_manifesto_de_split_recusa_id_duplicado_e_sintetico_no_treino(tmp_path):
    caminho = tmp_path / "split.json"
    dados = {
        "schema": "pyboxeditor.ocr-split/v1",
        "train": [{
            "id": "same", "document_id": "doc-t", "book_id": "book-t",
            "editor_id": "editor-t", "source_id": "source-t",
            "layout": "single-column", "domain": "body",
            "synthetic": True, "holdout": False, "payload": None,
        }],
        "validation": [], "test": [],
        "holdout": [{
            "id": "same", "document_id": "doc-h", "book_id": "book-h",
            "editor_id": "editor-h", "source_id": "source-h",
            "layout": "two-column", "domain": "body",
            "synthetic": False, "holdout": True, "payload": None,
        }],
        "synthetic": [],
    }
    caminho.write_text(json.dumps(dados), encoding="utf-8")

    with pytest.raises(ValueError, match="sint.tico|duplicado"):
        load_split_manifest(caminho)


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
