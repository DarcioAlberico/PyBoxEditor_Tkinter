from __future__ import annotations

import json

import fitz
import numpy as np

from core.editorial_model import EditorialDocument
from core.editorial_pipeline import (
    DocumentSource,
    EditorialPipeline,
    ExportOptions,
    ProcessOptions,
    SourcePage,
)
from core.ocr_result import PageResult, RegionResult
from core.ocr_runtime import CancellationToken


def _page(page_id: str, text: str = "1. e4") -> PageResult:
    region = RegionResult(
        id=f"region-{page_id}", type="notation", order=0, confidence=0.91,
        bbox=(10, 20, 150, 45), text=text,
    )
    return PageResult(
        page_id=page_id, text=text, confidence=0.91, regions=[region],
        metadata={"engine": "fake"},
    )


def test_source_de_memoria_produz_evidencia_reprodutivel():
    fonte = DocumentSource.from_pages([
        SourcePage(2, raster=np.zeros((10, 20), dtype=np.uint8), text_layer="1. e4")
    ], source_id="livro-teste")

    evidencias = fonte.evidences(ProcessOptions(dpi=240))

    assert len(evidencias) == 1
    assert evidencias[0].page_index == 2
    assert evidencias[0].source_kind == "memory"
    assert len(evidencias[0].raster_hash) == 64
    assert evidencias[0].text_layer == "1. e4"
    assert fonte.sha256 == fonte.sha256


def test_inspect_expone_layout_e_roteamento_sem_executar_engine():
    fonte = DocumentSource.from_pages([
        SourcePage(0, text_layer="1. e4 e5\n2. Nf3", raster=np.zeros((80, 240), np.uint8))
    ], source_id="inspecao")
    pipeline = EditorialPipeline()

    relatorio = pipeline.inspect(fonte)

    assert relatorio.source_id == "inspecao"
    assert relatorio.pages[0].text_characters > 0
    assert relatorio.pages[0].source_kind == "memory"
    assert isinstance(relatorio.pages[0].layout, dict)


def test_process_e_adapta_page_result_para_documento_editorial():
    fonte = DocumentSource.from_pages([
        SourcePage(0, text_layer="ignored"), SourcePage(1, text_layer="ignored")
    ], source_id="processado", title="Livro de teste", language="pt")
    chamadas = []

    def leitor(evidence, options, token):
        token.raise_if_cancelled()
        chamadas.append((evidence.page_index, options.language))
        return _page(f"page-{evidence.page_index}", f"texto {evidence.page_index}")

    documento = EditorialPipeline(page_processor=leitor).process(
        fonte, ProcessOptions(language="pt", use_cache=False)
    )

    assert isinstance(documento, EditorialDocument)
    assert [page.page_index for page in documento.pages] == [0, 1]
    assert chamadas == [(0, "pt"), (1, "pt")]
    assert documento.source_sha256 == fonte.sha256
    assert documento.metadata["phase"] == 4
    assert documento.pages[0].observations["routing"][0]["primary"] == "glyph"
    assert documento.pages[0].source_refs[0].image_hash


def test_process_nativo_preserva_camada_textual_sem_callback():
    fonte = DocumentSource.from_pages([
        SourcePage(0, text_layer="1. e4 e5\n2. Nf3", metadata={"dpi": 144})
    ], source_id="nativo")

    documento = EditorialPipeline().process(
        fonte, ProcessOptions(use_cache=False, engine="native")
    )

    pagina = documento.pages[0]
    assert pagina.blocks
    assert "1. e4 e5" in str(pagina.blocks[0].decision.value)
    assert pagina.observations["source_kind"] == "memory"
    assert pagina.observations["routing"]


def test_exportar_json_e_html_usam_o_mesmo_documento(tmp_path):
    fonte = DocumentSource.from_pages([SourcePage(0, text_layer="Um texto")], source_id="export")
    documento = EditorialPipeline().process(fonte, ProcessOptions(use_cache=False))
    pipeline = EditorialPipeline()

    json_report = pipeline.export(
        documento, tmp_path / "livro.json", ExportOptions(format="json")
    )
    html_report = pipeline.export(
        documento, tmp_path / "livro.html", ExportOptions(format="html")
    )

    assert json_report.files == (str(tmp_path / "livro.json"),)
    assert html_report.files == (str(tmp_path / "livro.html"),)
    assert json.loads((tmp_path / "livro.json").read_text(encoding="utf-8"))["schema"]
    assert "Um texto" in (tmp_path / "livro.html").read_text(encoding="utf-8")


def test_source_pdf_preserva_texto_raster_e_selecao_de_pagina(tmp_path):
    caminho = tmp_path / "livro.pdf"
    pdf = fitz.open()
    for texto in ("primeira página", "segunda página"):
        pagina = pdf.new_page(width=200, height=120)
        pagina.insert_text((20, 40), texto)
    pdf.save(caminho)
    pdf.close()

    source = DocumentSource.from_path(caminho, page_indices=[1])
    evidencias = source.evidences(ProcessOptions(dpi=72))

    assert [item.page_index for item in evidencias] == [1]
    assert evidencias[0].source_kind == "pdf_text"
    assert "segunda" in evidencias[0].text_layer
    assert evidencias[0].raster.shape[:2] == (120, 200)


def test_adapter_legado_e_cancelamento_mantem_documento_auditavel(tmp_path):
    from core.livro import PaginaExtraida, Paragrafo

    caminho = tmp_path / "livro.pdf"
    pdf = fitz.open()
    pdf.new_page()
    pdf.save(caminho)
    pdf.close()
    token = CancellationToken()

    def legado(path, options, cancellation):
        assert path == caminho
        cancellation.raise_if_cancelled()
        return [PaginaExtraida(0, blocos=[Paragrafo("texto legado")])]

    documento = EditorialPipeline(legacy_extractor=legado).process(
        DocumentSource.from_path(caminho),
        ProcessOptions(use_cache=False), token,
    )

    assert documento.metadata["adapter"] == "legacy_extractor"
    assert documento.pages[0].blocks[0].decision.value == "texto legado"
