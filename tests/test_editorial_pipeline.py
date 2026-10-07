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
from core.ocr_result import OCRHypothesis, PageResult, RegionResult
from core.ocr_runtime import CancellationToken
from core.ocr_phase4 import DiagramProcessor, Phase4Processor
from core.ocr_phase3 import Phase3Processor


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

    # `evidences` é gerador desde 2026-09-22 (item 7): quem quer a lista pede.
    evidencias = list(fonte.evidences(ProcessOptions(dpi=240)))

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


def test_fachada_monta_ensemble_de_engines_com_fusao_auditavel():
    class Service:
        def tesseract_linha_conf(self, image, language):
            return "texto tesseract", .72

        def easyocr_linha_conf(self, image, languages, gpu):
            return "texto easy", .78

        def paddleocr_linha_conf(self, image, language, gpu):
            return "texto paddle", .74

    fonte = DocumentSource.from_pages([
        SourcePage(0, raster=np.zeros((60, 240), dtype=np.uint8),
                   text_layer="texto original")
    ], source_id="ensemble")

    documento = EditorialPipeline.from_ocr_service(
        Service(), language="en", languages=("en",), trained_line=False
    ).process(fonte, ProcessOptions(use_cache=False))

    resultado = documento.pages[0].observations["page_result"]
    assert resultado["metadata"]["recognizers"] == ["engine_registry"]
    fontes = {item["source"] for item in resultado["lines"][0]["metadata"]["fusion"]["hypotheses"]}
    assert {"pdf_text", "tesseract", "easyocr", "paddleocr"} <= fontes


def test_ensemble_segmenta_scan_em_linhas_antes_de_consultar_os_engines():
    import cv2

    chamadas = []

    class Service:
        def _linha(self, image):
            chamadas.append(tuple(image.shape[:2]))
            return "linha reconhecida", .8

        def tesseract_linha_conf(self, image, language):
            return self._linha(image)

        def easyocr_linha_conf(self, image, languages, gpu):
            return self._linha(image)

        def paddleocr_linha_conf(self, image, language, gpu):
            return self._linha(image)

    raster = np.zeros((300, 500), dtype=np.uint8)
    for y in (50, 120, 205):
        cv2.rectangle(raster, (30, y), (470, y + 8), 255, -1)
    fonte = DocumentSource.from_pages([
        SourcePage(0, raster=raster),
    ], source_id="ensemble-lines")

    documento = EditorialPipeline.from_ocr_service(
        Service(), trained_line=False
    ).process(fonte, ProcessOptions(use_cache=False))

    linhas = documento.pages[0].observations["page_result"]["lines"]
    assert len(linhas) >= 3
    assert len(chamadas) >= 9
    assert all(0 < altura < raster.shape[0] for altura, _largura in chamadas)


def test_tabela_da_evidencia_chega_ao_ir_e_ao_exportador(tmp_path):
    fonte = DocumentSource.from_pages([
        SourcePage(
            0, raster=np.zeros((120, 240), dtype=np.uint8),
            text_blocks=({
                "type": "table", "bbox": [20, 20, 220, 90],
                "rows": [["Jogador", "Pontos"], ["A", "3"], ["B", "1"]],
            },),
        )
    ], source_id="tabela-editorial")
    pipeline = EditorialPipeline(recognizer=Phase4Processor(
        diagram_processor=DiagramProcessor(detector=lambda image, **kwargs: []),
    ))

    documento = pipeline.process(fonte, ProcessOptions(use_cache=False))

    tabela = next(bloco for bloco in documento.pages[0].blocks
                  if bloco.kind == "table")
    assert tabela.decision.value == {
        "rows": [["Jogador", "Pontos"], ["A", "3"], ["B", "1"]]
    }
    assert documento.pages[0].observations["routing"][0]["primary"] == "special"
    inspeccao = EditorialPipeline().inspect(fonte)
    assert any(region["type"] == "table"
               for region in inspeccao.pages[0].layout["regions"])
    relatorio = pipeline.export(
        documento, tmp_path / "tabela.html", ExportOptions(format="html")
    )
    assert relatorio.files == (str(tmp_path / "tabela.html"),)
    assert "<table" in (tmp_path / "tabela.html").read_text(encoding="utf-8")


def test_ensemble_consulta_os_engines_no_nivel_special_da_tabela():
    chamadas = []

    class Service:
        def tesseract_ocr_conf(self, image):
            chamadas.append("tesseract")
            return "tesseract", .80

        def easyocr_ocr_conf(self, image, languages, gpu):
            chamadas.append("easyocr")
            return "easyocr", .82

        def paddleocr_ocr_conf(self, image, language, gpu):
            chamadas.append("paddleocr")
            return "paddleocr", .81

    fonte = DocumentSource.from_pages([SourcePage(
        0, raster=np.zeros((120, 240), dtype=np.uint8),
        text_blocks=({
            "type": "table", "bbox": [20, 20, 220, 90],
            "rows": [["A", "B"], ["C", "D"]],
        },),
    )], source_id="tabela-ensemble")
    processor = Phase3Processor.from_ocr_service(Service(), trained_line=False)
    documento = EditorialPipeline(recognizer=Phase4Processor(
        text_processor=processor,
        diagram_processor=DiagramProcessor(detector=lambda image, **kwargs: []),
    )).process(fonte, ProcessOptions(use_cache=False))

    assert len(chamadas) == 12
    assert set(chamadas) == {"tesseract", "easyocr", "paddleocr"}
    resultado = documento.pages[0].observations["page_result"]
    assert resultado["metadata"]["routing"][0]["primary"] == "special"


def test_ensemble_preserva_ordem_coluna_a_coluna_no_scan():
    import cv2

    from core.ocr_phase3 import CallableRecognizer
    raster = np.zeros((260, 600), dtype=np.uint8)
    for x1, x2 in ((30, 250), (350, 570)):
        for y in (30, 80, 130):
            cv2.rectangle(raster, (x1, y), (x2, y + 8), 255, -1)

    def ler(_image, context):
        return [OCRHypothesis(
            f"x{context.bbox[0]}-y{context.bbox[1]}", .9, "layout-test",
            bbox=context.bbox,
        )]

    fonte = DocumentSource.from_pages([
        SourcePage(0, raster=raster),
    ], source_id="duas-colunas-editorial")
    pipeline = EditorialPipeline(recognizer=Phase4Processor(
        text_processor=Phase3Processor(line_recognizers=[
            CallableRecognizer("layout-test", ler),
        ]),
        diagram_processor=DiagramProcessor(detector=lambda image, **kwargs: []),
    ))

    documento = pipeline.process(fonte, ProcessOptions(use_cache=False))
    linhas = documento.pages[0].observations["page_result"]["lines"]

    x = [line["bbox"][0] for line in linhas]
    y = [line["bbox"][1] for line in linhas]
    assert x[:3] == [x[0]] * 3 and x[3:] == [x[3]] * 3 and x[0] < x[3]
    assert y == [y[0], y[1], y[2], y[0], y[1], y[2]]


def test_camada_textual_reordena_blocos_intercalados_por_coluna():
    def bloco(texto, x, y):
        bbox = [x, y, x + 180, y + 18]
        return {"bbox": bbox, "lines": [{
            "bbox": bbox, "spans": [{"text": texto, "size": 10}],
        }]}

    fonte = DocumentSource.from_pages([SourcePage(
        0, raster=np.zeros((220, 600), dtype=np.uint8),
        text_blocks=(
            bloco("L1", 30, 20), bloco("R1", 390, 20),
            bloco("L2", 30, 60), bloco("R2", 390, 60),
            bloco("L3", 30, 100), bloco("R3", 390, 100),
        ),
    )], source_id="duas-colunas-camada")
    pipeline = EditorialPipeline(recognizer=Phase4Processor(
        text_processor=Phase3Processor(),
        diagram_processor=DiagramProcessor(detector=lambda image, **kwargs: []),
    ))

    documento = pipeline.process(fonte, ProcessOptions(use_cache=False))
    linhas = documento.pages[0].observations["page_result"]["lines"]

    assert [line["text"] for line in linhas] == ["L1", "L2", "L3", "R1", "R2", "R3"]
    assert [block.decision.value for block in documento.pages[0].blocks] == [
        "L1", "L2", "L3", "R1", "R2", "R3",
    ]
    inspeccao = EditorialPipeline().inspect(fonte)
    assert [region["text"] for region in inspeccao.pages[0].layout["regions"]] == [
        "L1", "L2", "L3", "R1", "R2", "R3",
    ]


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
    evidencias = list(source.evidences(ProcessOptions(dpi=72)))

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


def test_poda_do_cache_tambem_se_aplica_ao_leitor_de_producao(tmp_path):
    from core.livro import PaginaExtraida, Paragrafo
    import os

    caminho = tmp_path / "livro.pdf"
    pdf = fitz.open()
    pdf.new_page()
    pdf.save(caminho)
    pdf.close()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    antigo = cache_dir / "resultado-antigo.json"
    antigo.write_text("{}", encoding="utf-8")
    os.utime(antigo, (100.0, 100.0))

    def legado(path, options, cancellation):
        return [PaginaExtraida(0, blocos=[Paragrafo("texto legado")])]

    documento = EditorialPipeline(legacy_extractor=legado).process(
        DocumentSource.from_path(caminho),
        ProcessOptions(cache_dir=cache_dir, cache_prune_max_age_seconds=100),
    )

    assert not antigo.exists()
    assert documento.metadata["cache_prune"]["removed"] == 1
