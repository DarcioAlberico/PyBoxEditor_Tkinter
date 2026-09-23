"""
O custo do caminho novo (item 7 da revisão de 2026-09-18).

Quatro defeitos de custo, todos invisíveis numa página e caros num livro: o
`sha256` da origem era recalculado a cada acesso — uma vez por página, lendo o
arquivo inteiro —, `evidences()` segurava o raster de todas as páginas ao mesmo
tempo, `process()` rasterizava o documento **de novo** só para pôr a inspeção no
metadata, e o cache não guardava nada (sem pasta) nem sabia com que pesos o
resultado tinha sido feito.

Medido em 2026-09-22, oito páginas de um PDF de 7,5 MB pela fachada:

    antes:  5,9 s · pico 268 MB · 18 leituras integrais do PDF
    depois: 2,8 s · pico 110 MB ·  1 leitura

Os testes aqui prendem o **comportamento** que produz esses números; a medida
está no `docs/REVISAO_MODOS_OCR.md` (4.10).
"""

from __future__ import annotations

import types

import fitz
import numpy as np
import pytest

from config import paths
from core.editorial_pipeline import (DocumentSource, EditorialPipeline,
                                     PageEvidence, PageInspection,
                                     ProcessOptions, SourcePage)
from core.ocr_result import PageResult, RegionResult
from core.ocr_runtime import BatchProcessor, CancellationToken, RuntimeConfig


def _pdf(tmp_path, paginas: int = 3):
    tmp_path.mkdir(parents=True, exist_ok=True)
    caminho = tmp_path / "livro.pdf"
    documento = fitz.open()
    for numero in range(paginas):
        pagina = documento.new_page(width=200, height=120)
        pagina.insert_text((20, 40), f"página {numero}")
    documento.save(caminho)
    documento.close()
    return caminho


def _fonte_de_memoria(paginas: int = 3) -> DocumentSource:
    return DocumentSource.from_pages(
        [SourcePage(page_index=i, raster=np.zeros((8, 8), dtype=np.uint8),
                    text_layer=f"linha {i}") for i in range(paginas)],
        source_id="memoria")


# ----------------------------------------------------------------------
# O sha256 da origem
# ----------------------------------------------------------------------

def test_o_sha256_da_origem_e_calculado_uma_vez(tmp_path, monkeypatch):
    fonte = DocumentSource.from_path(_pdf(tmp_path))
    contas = {"n": 0}
    original = DocumentSource._calcular_sha256

    def contando(self):
        contas["n"] += 1
        return original(self)

    monkeypatch.setattr(DocumentSource, "_calcular_sha256", contando)
    assert fonte.sha256 == fonte.sha256 == fonte.sha256
    assert contas["n"] == 1, "a origem foi re-hasheada"


def test_o_sha256_continua_identificando_o_conteudo(tmp_path):
    um, outro = _pdf(tmp_path / "a", 2), _pdf(tmp_path / "b", 3)
    (tmp_path / "copia.pdf").write_bytes(um.read_bytes())
    assert DocumentSource.from_path(um).sha256 == \
        DocumentSource.from_path(tmp_path / "copia.pdf").sha256
    assert DocumentSource.from_path(um).sha256 != \
        DocumentSource.from_path(outro).sha256


# ----------------------------------------------------------------------
# As evidências em fluxo
# ----------------------------------------------------------------------

def test_as_evidencias_saem_uma_a_uma(tmp_path):
    fonte = DocumentSource.from_path(_pdf(tmp_path, 3))
    evidencias = fonte.evidences(ProcessOptions(dpi=72))
    assert isinstance(evidencias, types.GeneratorType)
    primeira = next(evidencias)
    assert primeira.page_index == 0
    assert [item.page_index for item in evidencias] == [1, 2]


def test_a_fonte_de_memoria_so_monta_a_pagina_pedida():
    fonte = _fonte_de_memoria(3)
    contas = {"n": 0}
    original = DocumentSource._evidence_from_memory

    def contando(self, page, options):
        contas["n"] += 1
        return original(self, page, options)

    DocumentSource._evidence_from_memory = contando
    try:
        gerador = fonte.evidences(ProcessOptions())
        assert contas["n"] == 0, "montou antes de alguém pedir"
        next(gerador)
        assert contas["n"] == 1, "montou mais de uma página para entregar uma"
    finally:
        DocumentSource._evidence_from_memory = original


def test_a_validacao_da_origem_continua_no_lugar_da_chamada(tmp_path):
    """Gerador adia o trabalho, não o erro: quem chama espera o erro onde chamou."""
    with pytest.raises(FileNotFoundError):
        DocumentSource.from_path(tmp_path / "nao-existe.pdf").evidences(ProcessOptions())
    with pytest.raises(ValueError):
        DocumentSource("x", None, "memory", (), "", "und", None).evidences(ProcessOptions())
    de_memoria = DocumentSource("m", None, "memory",
                                (SourcePage(page_index=0, text_layer="a"),),
                                "", "und", (7,))
    with pytest.raises(IndexError):
        de_memoria.evidences(ProcessOptions())


def test_a_evidencia_sem_raster_guarda_as_medidas():
    evidencia = PageEvidence(document_id="d", page_index=0, source_kind="pdf_raster",
                             raster=np.zeros((120, 200), dtype=np.uint8),
                             raster_hash="h", text_layer="texto")
    leve = evidencia.sem_raster()
    assert leve.raster is None
    assert (leve.width, leve.height) == (200, 120)
    assert leve.text_layer == "texto" and leve.raster_hash == "h"
    assert leve.sem_raster() is leve


# ----------------------------------------------------------------------
# A inspeção derivada
# ----------------------------------------------------------------------

def test_a_inspecao_sai_do_que_a_pagina_ja_apurou():
    page = PageResult("page-0003", metadata={
        "page_index": 3, "source_kind": "pdf_text", "dpi": 300,
        "image_hash": "abc", "text_layer": "quatro",
        "layout": {"columns": 2, "warnings": ["coluna estreita"]},
        "layout_routing": [{"region_id": "r0", "primary": "line"}],
        "routing": [{"region_id": "r9", "primary": "glyph"}],
    })
    inspecao = PageInspection.da_pagina(page)
    assert (inspecao.page_index, inspecao.dpi, inspecao.raster_hash) == (3, 300, "abc")
    assert inspecao.text_characters == len("quatro")
    assert inspecao.routing == ({"region_id": "r0", "primary": "line"},), \
        "a inspeção publica o roteamento do layout, não o do resultado"
    assert inspecao.warnings == ("coluna estreita",)


def test_process_nao_rasteriza_o_documento_uma_segunda_vez(tmp_path):
    """
    A inspeção do metadata custava uma passada inteira pelo documento. Agora ela
    é derivada, e `process` não chama `inspect` nenhuma vez.
    """
    def processador(evidence, options, token):
        return PageResult(f"page-{evidence.page_index:04d}",
                          regions=[RegionResult("r0", "body", 0, .9, (0, 0, 8, 8),
                                                text="texto")])

    pipeline = EditorialPipeline(page_processor=processador)
    chamadas = {"n": 0}
    original = EditorialPipeline.inspect
    pipeline.inspect = lambda *a, **k: (chamadas.__setitem__("n", chamadas["n"] + 1)
                                        or original(pipeline, *a, **k))

    documento = pipeline.process(_fonte_de_memoria(3),
                                 ProcessOptions(use_cache=False))
    assert chamadas["n"] == 0, "process voltou a inspecionar a origem"
    inspecao = documento.metadata["inspection"]
    assert [pagina["page_index"] for pagina in inspecao["pages"]] == [0, 1, 2]
    assert inspecao["source_sha256"] == documento.source_sha256


# ----------------------------------------------------------------------
# O cache
# ----------------------------------------------------------------------

def test_os_tres_pesos_sao_os_do_projeto():
    """A duplicação em `config.paths` é o preço de não importar `cv2` para saber
    onde os pesos estão — e este teste é o que impede a duplicação de divergir."""
    from core import diagrama
    from core.services.learning_service import LearningService

    from pathlib import Path

    pesos = paths.caminhos_dos_pesos()
    assert pesos["diagrama"] == Path(diagrama.CAMINHO_MODELO)
    assert pesos["ocupacao"] == Path(diagrama.CAMINHO_OCUPACAO)
    assert pesos["glifos"] == paths.projeto_dir() / LearningService().model_path
    assert pesos["diagrama"].exists() and pesos["ocupacao"].exists(), \
        "peso que não existe assina como ausente, e o cache não distingue dois ausentes"
    if not pesos["glifos"].exists():
        # Os dois de cima são versionados; este é treinado na máquina de quem
        # usa (`*.pth` no .gitignore), e um clone limpo não o tem.
        pytest.skip("custom_model.pth fica fora do git; sem ele não há o que conferir")


def test_a_pasta_do_cache_tem_padrao_fora_do_projeto(tmp_path, monkeypatch):
    assert ProcessOptions(use_cache=False).pasta_de_cache() is None
    assert ProcessOptions(cache_dir=tmp_path).pasta_de_cache() == tmp_path

    monkeypatch.setenv("PYBOXEDITOR_CACHE_DIR", str(tmp_path / "meu"))
    assert ProcessOptions().pasta_de_cache() == tmp_path / "meu" / "ocr"
    monkeypatch.delenv("PYBOXEDITOR_CACHE_DIR")
    assert ProcessOptions().pasta_de_cache() == paths.data_dir() / "cache" / "ocr"


def test_a_chave_do_cache_carrega_os_tres_pesos(tmp_path, monkeypatch):
    pesos = {nome: tmp_path / f"{nome}.pth" for nome in ("glifos", "diagrama", "ocupacao")}
    for caminho in pesos.values():
        caminho.write_bytes(b"peso")
    monkeypatch.setattr(paths, "caminhos_dos_pesos", lambda: pesos)

    chave = ProcessOptions().cache_key("v4")
    assert len(chave["pesos"]) == 3
    pesos["glifos"].write_bytes(b"peso treinado de novo")
    assert ProcessOptions().cache_key("v4") != chave, \
        "treinar o modelo tem de invalidar o resultado gravado"
    assert ProcessOptions(use_cache=False).cache_key("v4")["pesos"] == [], \
        "sem cache não se paga o sha256 dos pesos"


def test_o_cache_serve_a_segunda_leitura_e_nao_a_de_outro_modelo(tmp_path, monkeypatch):
    pesos = {"glifos": tmp_path / "g.pth"}
    pesos["glifos"].write_bytes(b"peso")
    monkeypatch.setattr(paths, "caminhos_dos_pesos", lambda: pesos)
    leituras = {"n": 0}

    def processador(evidence, options, token):
        leituras["n"] += 1
        return PageResult(f"page-{evidence.page_index:04d}")

    pipeline = EditorialPipeline(page_processor=processador)
    opcoes = ProcessOptions(cache_dir=tmp_path / "cache")
    pipeline.process(_fonte_de_memoria(2), opcoes)
    assert leituras["n"] == 2
    pipeline.process(_fonte_de_memoria(2), opcoes)
    assert leituras["n"] == 2, "a segunda leitura não veio do cache"

    pesos["glifos"].write_bytes(b"peso treinado de novo")
    pipeline.process(_fonte_de_memoria(2), opcoes)
    assert leituras["n"] == 4, "o cache serviu o resultado do modelo velho"


def test_o_lote_aceita_um_fluxo_de_paginas():
    def processador(item, token):
        return PageResult(f"page-{item:04d}")

    lote = BatchProcessor(processador, config=RuntimeConfig(use_cache=False))
    resultado = lote.process((i for i in range(3)), token=CancellationToken())
    assert [page.page_id for page in resultado.results] == [
        "page-0000", "page-0001", "page-0002"]
