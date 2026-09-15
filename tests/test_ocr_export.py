import json

import fitz
import pytest

from core.ocr_export import (
    ExportConfig,
    exportar_docx,
    exportar_json,
    exportar_pdf_pesquisavel,
    exportar_texto,
)
from core.ocr_result import PageResult, RegionResult, WordResult


def _pagina():
    return PageResult(
        "p1", text="Casa azul", metadata={"paragraphs": ["Casa azul"]},
        regions=[RegionResult("r1", "body", 0, 0.9, (0, 0, 100, 40))],
        words=[WordResult("w1", "Casa", 0.9, (20, 30, 80, 50), "l1", "fused")],
    )


def test_exporta_texto_e_json(tmp_path):
    pagina = _pagina()
    txt = exportar_texto([pagina], tmp_path / "out.txt")
    js = exportar_json([pagina], tmp_path / "out.json")
    assert txt.read_text(encoding="utf-8") == "Casa azul"
    assert '"pages"' in js.read_text(encoding="utf-8")


def test_json_pode_omitir_suspeitas_sem_mutar_pagina(tmp_path):
    pagina = _pagina()
    pagina.metadata["suspects"] = [{"id": "w1", "reason": "low_confidence"}]
    destino = exportar_json(
        [pagina], tmp_path / "sem-revisao.json",
        config=ExportConfig(incluir_suspeitas=False),
    )
    dados = json.loads(destino.read_text(encoding="utf-8"))
    assert "suspects" not in dados["pages"][0]["metadata"]
    assert "suspects" in pagina.metadata


def test_exporta_docx_com_dependencia_opcional(tmp_path):
    pytest.importorskip("docx")
    destino = exportar_docx([_pagina()], tmp_path / "out.docx", titulo="Teste")
    assert destino.exists() and destino.stat().st_size > 0


def test_pdf_pesquisavel_preserva_pagina_e_insere_texto(tmp_path):
    entrada = tmp_path / "in.pdf"
    saida = tmp_path / "out.pdf"
    doc = fitz.open()
    page = doc.new_page(width=200, height=100)
    page.insert_text((10, 30), "imagem original", fontsize=12)
    doc.save(entrada)
    doc.close()
    resumo = exportar_pdf_pesquisavel(
        entrada, saida, [_pagina()], config=ExportConfig(dpi=300))
    assert resumo["text_items"] == 1
    resultado = fitz.open(saida)
    texto = resultado[0].get_text()
    resultado.close()
    assert "imagem original" in texto
    assert "Casa" in texto


def test_config_rejeita_dpi_invalido():
    with pytest.raises(ValueError):
        ExportConfig(dpi=0)
