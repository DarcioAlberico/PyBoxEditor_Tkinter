from __future__ import annotations

import json

import pytest

from core.ocr14_revisao import revisar_relatorio
from core.ocr_phase7 import CorrectionDataset
from scripts.preparar_fase7 import _entradas_ocr14
from scripts.revisar_ocr14 import main


def _relatorio():
    return {
        "pdf": "livro.pdf",
        "paginas": {
            "30": {
                "recortes": [
                    {
                        "arquivo": "revisao_ocr14/a/um.png",
                        "esperado": "a",
                        "lido": "o",
                        "dominio": "notation",
                        "rotulo_confirmado": False,
                    },
                    {
                        "arquivo": "revisao_ocr14/b/dois.png",
                        "esperado": "b",
                        "lido": "d",
                        "dominio": "notation",
                        "rotulo_confirmado": False,
                    },
                ]
            }
        },
    }


def test_revisao_ocr14_confirma_rotulos_e_preserva_proveniencia():
    resultado = revisar_relatorio(
        _relatorio(),
        {"revisao_ocr14/a/um.png": "a", "revisao_ocr14/b/dois.png": "b"},
        revisor="editor",
        revisado_em="2026-09-26T12:00:00+00:00",
    )

    assert resultado["schema"] == "pyboxeditor.ocr14-review/v1"
    assert resultado["pdf"] == "livro.pdf"
    assert resultado["status"] == "reviewed"
    assert resultado["pending"] == []
    assert [item["rotulo"] for item in resultado["entradas"]] == ["a", "b"]
    assert all(item["rotulo_confirmado"] is True for item in resultado["entradas"])
    assert all(item["revisor"] == "editor" for item in resultado["entradas"])
    assert all(item["revisado_em"] == "2026-09-26T12:00:00+00:00"
               for item in resultado["entradas"])


def test_revisao_ocr14_exige_todos_os_recortes_e_rejeita_arquivo_desconhecido():
    with pytest.raises(ValueError, match="sem revisao"):
        revisar_relatorio(_relatorio(), {"revisao_ocr14/a/um.png": "a"})

    with pytest.raises(ValueError, match="nao pertence"):
        revisar_relatorio(
            _relatorio(),
            {"revisao_ocr14/a/um.png": "a", "fora.png": "x"},
        )


def test_cli_ocr14_produz_artefato_consumivel_pela_fase7(tmp_path):
    from scripts import preparar_fase7

    base = tmp_path / "revisao_ocr14"
    (base / "a").mkdir(parents=True)
    (base / "b").mkdir(parents=True)
    (base / "a" / "um.png").write_bytes(b"um")
    (base / "b" / "dois.png").write_bytes(b"dois")
    relatorio = tmp_path / "relatorio.json"
    rotulos = tmp_path / "rotulos.json"
    saida = tmp_path / "revisado.json"
    relatorio.write_text(json.dumps(_relatorio()), encoding="utf-8")
    rotulos.write_text(json.dumps({
        "revisao_ocr14/a/um.png": "a",
        "revisao_ocr14/b/dois.png": "b",
    }), encoding="utf-8")

    assert main([str(relatorio), str(rotulos), "-o", str(saida),
                 "--revisor", "editor"]) == 0
    revisado = json.loads(saida.read_text(encoding="utf-8"))
    dataset_saida = tmp_path / "dataset-promovido.json"
    assert preparar_fase7.main([
        "ocr14", str(saida), "-o", str(dataset_saida),
        "--base-dir", str(tmp_path), "--exigir-arquivos",
        "--exigir-proveniencia",
    ]) == 0
    promovido = CorrectionDataset.load(dataset_saida)
    assert promovido.metadata["review_provenance"]["verified"] is True
    assert preparar_fase7.main([
        "split", str(dataset_saida), "-o", str(tmp_path / "split.json")
    ]) == 0
    dataset = CorrectionDataset.from_ocr14(
        _entradas_ocr14(revisado), base_dir=tmp_path,
        exigir_arquivos=True, exigir_registros=True)

    assert revisado["status"] == "reviewed"
    assert len(dataset.records) == 2
    assert all(record.metadata["arquivo_sha256"] for record in dataset.records)


def test_fase7_recusa_relatorio_ocr14_com_revisao_pendente(tmp_path):
    from scripts import preparar_fase7

    parcial = revisar_relatorio(
        _relatorio(), {"revisao_ocr14/a/um.png": "a"},
        exigir_todos=False)

    assert parcial["status"] == "pending_review"
    relatorio = tmp_path / "parcial.json"
    relatorio.write_text(json.dumps(parcial), encoding="utf-8")
    with pytest.raises(ValueError, match="revisado por completo"):
        preparar_fase7.main([
            "ocr14", str(relatorio), "-o", str(tmp_path / "dataset.json")
        ])


def test_fase7_portao_de_proveniencia_rejeita_quarentena_alterada(tmp_path):
    from scripts import preparar_fase7

    original = tmp_path / "relatorio.json"
    rotulos = tmp_path / "rotulos.json"
    revisado = tmp_path / "revisado.json"
    original.write_text(json.dumps(_relatorio()), encoding="utf-8")
    rotulos.write_text(json.dumps({
        "revisao_ocr14/a/um.png": "a",
        "revisao_ocr14/b/dois.png": "b",
    }), encoding="utf-8")
    assert main([str(original), str(rotulos), "-o", str(revisado)]) == 0

    (tmp_path / "revisao_ocr14" / "a").mkdir(parents=True)
    (tmp_path / "revisao_ocr14" / "b").mkdir(parents=True)
    (tmp_path / "revisao_ocr14" / "a" / "um.png").write_bytes(b"um")
    (tmp_path / "revisao_ocr14" / "b" / "dois.png").write_bytes(b"dois")

    original.write_text(json.dumps(_relatorio() | {"alterado": True}),
                        encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        preparar_fase7.main([
            "ocr14", str(revisado), "-o", str(tmp_path / "dataset.json"),
            "--base-dir", str(tmp_path), "--exigir-arquivos",
            "--exigir-proveniencia",
        ])
