"""A fachada editorial com o leitor de produção dentro, e o que sai dela.

`EditorialPipeline()` sozinha, numa página digitalizada, devolve um bloco
vazio: sem camada de texto e sem adapters de linha, `Phase3Processor` trata a
página inteira como uma linha sem texto (medido na p. 30 do Aagaard em
2026-09-18: 1 bloco `unresolved`, 0 caracteres, nenhum aviso). Estes testes
fixam a ponte de `core.editorial_legacy`: o mesmo `livro.extrair` da exportação
de livro, o IR cheio, a caixa por parágrafo, a largura/dpi da página, o aviso
do motor que faltou, e o PDF pesquisável escrito **invisível** e na escala
certa.
"""

import json
import sys

import fitz
import pytest

from core import livro
from core.editorial_adapters import pagina_extraida_para_pagina
from core.editorial_legacy import ExtratorDeLivro, OpcoesDeLeitura, pipeline_de_producao
from core.editorial_pipeline import DocumentSource, EditorialPipeline, ExportOptions, ProcessOptions
from core.editorial_review import _decision_requires_review
from core.editorial_model import Decision, EditorialBlock, SourceRef


class _Aprendizado:
    """O `LearningService` do teste: carrega sempre, lê sempre a mesma letra."""

    def load_predictor(self):
        return True

    def motivo_do_modelo(self):
        return ""

    def leitor_de_texto(self, idioma):
        self.idioma = idioma
        return lambda recorte, referencia=None: ("a", 0.99)


class _OCR:
    """O `OCRService` do teste: o Tesseract da página não devolve nada."""

    def __init__(self):
        self.idiomas = []

    def tesseract_pagina_detalhada_conf(self, imagem, idioma):
        self.idiomas.append(idioma)
        return []

    def tesseract_faixa_detalhada_conf(self, faixa, idioma):
        return []


def _pdf(caminho, linhas=("Uma linha de prosa comum.", "E outra linha, igual."),
         paginas=1):
    doc = fitz.open()
    for _ in range(paginas):
        p = doc.new_page(width=300, height=200)
        for i, linha in enumerate(linhas):
            p.insert_text((30, 40 + i * 16), linha, fontsize=10)
    doc.save(caminho)
    doc.close()
    return caminho


# ----------------------------------------------------------------------
# A ponte
# ----------------------------------------------------------------------

def test_a_fachada_com_o_leitor_de_producao_le_a_pagina(tmp_path):
    pdf = _pdf(tmp_path / "livro.pdf")
    ocr = _OCR()
    pipeline, extrator = pipeline_de_producao(
        _Aprendizado(), ocr, OpcoesDeLeitura(idioma="pt", diagramas="recorte"))
    documento = pipeline.process(DocumentSource.from_path(pdf),
                                 ProcessOptions(language="pt", use_cache=False, dpi=150))

    assert documento.language == "pt"
    assert documento.metadata["engine"] == "livro.extrair"
    pagina = documento.pages[0]
    kinds = [b.kind for b in pagina.blocks]
    assert "paragraph" in kinds
    assert extrator.ultimas_paginas and extrator.ultimas_paginas[0].caracteres > 0
    # O idioma chegou aos dois leitores.
    assert ocr.idiomas == ["pt"]
    # A caixa do parágrafo e as medidas da página vieram junto.
    paragrafo = next(b for b in pagina.blocks if b.kind == "paragraph")
    x1, y1, x2, y2 = paragrafo.source_refs[0].bbox
    assert x1 == 0 and x2 == pagina.metadata["image_width"] and y2 > y1
    assert pagina.metadata["dpi"] == 150


def test_a_fachada_sem_leitor_continua_vazia_numa_pagina_digitalizada(tmp_path):
    """O defeito que a ponte existe para contornar, fixado como está: sem
    reconhecedor a fachada não lê a página. Se um dia ela passar a ler, este
    teste avisa que a ponte pode ir embora."""
    pdf = _pdf(tmp_path / "livro.pdf")
    # A camada de texto do PDF é apagada rasterizando a página.
    origem = fitz.open(pdf)
    raster = fitz.open()
    pagina = raster.new_page(width=300, height=200)
    pagina.insert_image(pagina.rect, pixmap=origem[0].get_pixmap(dpi=150))
    scan = tmp_path / "scan.pdf"
    raster.save(scan)
    raster.close()
    origem.close()

    documento = EditorialPipeline().process(
        DocumentSource.from_path(scan), ProcessOptions(use_cache=False))
    textos = [str(b.decision.value) for b in documento.pages[0].blocks
              if isinstance(b.decision.value, str)]
    assert not any(t.strip() for t in textos)


def test_as_paginas_pedidas_e_o_cancelamento_chegam_ao_leitor(tmp_path):
    pdf = _pdf(tmp_path / "livro.pdf", paginas=3)
    extrator = ExtratorDeLivro(_Aprendizado(), _OCR(),
                               OpcoesDeLeitura(idioma="en", diagramas="recorte"))
    paginas = extrator(pdf, ProcessOptions(page_indices=(2,), dpi=150), None)
    assert [p.numero for p in paginas] == [2]

    class Cancelado:
        def raise_if_cancelled(self):
            from core.ocr_runtime import OCRCancelled
            raise OCRCancelled("cancelado")

    from core.services.task_service import Cancelled
    with pytest.raises(Cancelled):
        extrator(pdf, ProcessOptions(dpi=150), Cancelado())


def test_o_modelo_de_linha_so_entra_se_passa_no_portao(tmp_path, monkeypatch):
    import config.paths as paths
    pesos = tmp_path / "text_line_model.pth"
    pesos.write_bytes(b"x")
    meta = tmp_path / "text_line_model.json"
    meta.write_text(json.dumps({"historico": [{"perda_validacao": 1.0, "cer": 0.96}]}),
                    encoding="utf-8")
    monkeypatch.setattr(paths, "caminhos_modelo_linha", lambda: (pesos, meta))
    extrator = ExtratorDeLivro(_Aprendizado(), _OCR(),
                               OpcoesDeLeitura(modelo_de_linha=True, diagramas="recorte"))
    extrator(_pdf(tmp_path / "livro.pdf"), ProcessOptions(dpi=150), None)
    assert extrator.leitor_de_faixa == "tesseract"

    meta.write_text(json.dumps({"historico": [{"perda_validacao": 1.0, "cer": 0.05}]}),
                    encoding="utf-8")
    extrator = ExtratorDeLivro(_Aprendizado(), _OCR(),
                               OpcoesDeLeitura(modelo_de_linha=True, diagramas="recorte"))
    extrator._leitores()
    assert extrator.leitor_de_faixa == "modelo_de_linha"


# ----------------------------------------------------------------------
# O adapter: o aviso do motor vira aviso da página
# ----------------------------------------------------------------------

def test_o_motor_que_faltou_vira_aviso_da_pagina_no_ir():
    pagina = livro.PaginaExtraida(numero=3, blocos=[livro.Paragrafo("texto", topo=10, pe=30)],
                                  largura=200, altura=100, dpi=72,
                                  motor_indisponivel="página: Tesseract indisponível")
    editorial = pagina_extraida_para_pagina(pagina, document_id="doc")
    assert editorial.warnings == ["motor de prosa indisponível: página: Tesseract indisponível"]
    assert editorial.observations["legacy_page"]["motor_indisponivel"].startswith("página")
    assert editorial.blocks[0].source_refs[0].bbox == (0, 10, 200, 30)


def test_paragrafo_sem_medidas_fica_sem_caixa():
    pagina = livro.PaginaExtraida(numero=0, blocos=[livro.Paragrafo("texto")])
    editorial = pagina_extraida_para_pagina(pagina, document_id="doc")
    assert editorial.blocks[0].source_refs[0].bbox is None
    assert "image_width" not in editorial.metadata


# ----------------------------------------------------------------------
# O PDF pesquisável do IR
# ----------------------------------------------------------------------

def test_o_pdf_pesquisavel_do_ir_e_invisivel_e_esta_na_escala(tmp_path):
    pdf = _pdf(tmp_path / "livro.pdf", linhas=("Gashimov missed his chance",))
    pipeline, _extrator = pipeline_de_producao(
        _Aprendizado(), _OCR(), OpcoesDeLeitura(diagramas="recorte"))
    documento = pipeline.process(DocumentSource.from_path(pdf),
                                 ProcessOptions(use_cache=False, dpi=150))
    # O texto lido pelo dublê é `aaaa...`; para a busca o bloco recebe a prosa.
    bloco = next(b for b in documento.pages[0].blocks if b.kind == "paragraph")
    bloco.decision.value = "Gashimov missed his chance"

    saida = tmp_path / "saida.pdf"
    relatorio = pipeline.export(documento, saida, ExportOptions(format="pdf"))
    assert relatorio.metadata["failed_items"] == 0
    assert relatorio.metadata["text_items"] >= 1

    original = fitz.open(pdf)
    novo = fitz.open(saida)
    try:
        # O PDF de teste tem o texto visível de fábrica; a camada acrescenta
        # uma ocorrência, e é a nova que tem de estar no lugar certo.
        antes = original[0].search_for("Gashimov")
        achados = novo[0].search_for("Gashimov")
        assert len(achados) == len(antes) + 1
        novos = [r for r in achados if all(abs(r.y0 - a.y0) > 0.5 for a in antes)]
        assert len(novos) == 1
        # Na faixa vertical do parágrafo, em pontos — não em pixels a 150 dpi.
        y1, y2 = bloco.source_refs[0].bbox[1], bloco.source_refs[0].bbox[3]
        assert y1 * 72 / 150 - 2 <= novos[0].y0 and novos[0].y1 <= y2 * 72 / 150 + 2
        # Invisível: a página renderizada não muda um pixel.
        assert (original[0].get_pixmap(dpi=50).samples
                == novo[0].get_pixmap(dpi=50).samples)
    finally:
        original.close()
        novo.close()


def test_pagina_fora_do_pdf_conta_como_falha_e_avisa(tmp_path):
    pdf = _pdf(tmp_path / "livro.pdf")
    pipeline, _extrator = pipeline_de_producao(
        _Aprendizado(), _OCR(), OpcoesDeLeitura(diagramas="recorte"))
    documento = pipeline.process(DocumentSource.from_path(pdf),
                                 ProcessOptions(use_cache=False, dpi=150))
    pagina = documento.pages[0]
    pagina.page_index = 7  # o PDF só tem a página 0
    relatorio = pipeline.export(documento, tmp_path / "saida.pdf", ExportOptions(format="pdf"))
    assert relatorio.metadata["failed_items"] == len(pagina.blocks)
    assert any("fora do PDF" in aviso for aviso in relatorio.warnings)


# ----------------------------------------------------------------------
# A fila: suspeita, e não "tudo que é automático"
# ----------------------------------------------------------------------

def _bloco(status="automatic", warnings=(), reason=(), metadata=None):
    return EditorialBlock(
        id="b", kind="paragraph", order=0,
        source_refs=[SourceRef("doc", 0)],
        decision=Decision("texto", ["e"], status, list(reason)),
        warnings=list(warnings), metadata=dict(metadata or {}))


def test_o_bloco_automatico_sem_sinal_nao_entra_na_fila():
    assert _decision_requires_review(_bloco()) is False


def test_o_que_tem_sinal_entra_na_fila():
    assert _decision_requires_review(_bloco("unresolved"))
    assert _decision_requires_review(_bloco(warnings=["motor de prosa indisponível"]))
    assert _decision_requires_review(_bloco(reason=["low_confidence"]))
    assert _decision_requires_review(_bloco(metadata={"review_required": True}))
    assert _decision_requires_review(_bloco("reviewed", warnings=["x"])) is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
