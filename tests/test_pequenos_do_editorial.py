"""Os pequenos do editorial (RG-17, R-36), um teste por item que muda comportamento.

- `header`, `footer` e `caption` voltavam do IR como parágrafo comum, e o cabeçalho entrava no
  corpo do livro.
- A imagem da página engolia a falha sem log e não conferia se o PDF em disco é o que se leu.
- O processamento por página casava resultado e página pelo índice.
- Havia duas `ExportOptions`, com `paginas` de contratos opostos, e duas `_faixas`.
"""

import logging
import zipfile

import fitz
import pytest

from core import editorial_export, editorial_legacy, editorial_pipeline, exportar, livro
from core.editorial_adapters import (pagina_editorial_para_extraida, paginas_extraidas_para_documento)
from core.editorial_export import EditorialExporter, ExportOptions
from core.editorial_legacy import ProvedorDePaginas, aplicar_revisao
from core.editorial_model import Decision, EditorialBlock, EditorialDocument, EditorialPage, SourceRef
from core.editorial_pipeline import (DocumentSource, EditorialPipeline, ProcessOptions, SourcePage)
from core.ocr_result import PageResult, RegionResult


# ----------------------------------------------------------------------
# O tipo volta
# ----------------------------------------------------------------------

def _documento_com_papeis():
    """Um IR que não veio do leitor: cabeçalho, legenda, prosa e rodapé."""
    ref = SourceRef("l", 0)
    tipos = (("header", "CABECALHO CORRENTE"), ("paragraph", "Prosa do livro."),
             ("caption", "Legenda do diagrama"), ("footer", "RODAPE 37"))
    blocos = [EditorialBlock(f"b{i}", tipo, i, [ref], Decision(texto, [], "automatic"))
              for i, (tipo, texto) in enumerate(tipos)]
    return EditorialDocument("l", "Livro", "pt", [EditorialPage("p1", 0, [ref], blocos, [])])


def test_o_tipo_volta_e_vai_de_novo():
    pagina = pagina_editorial_para_extraida(_documento_com_papeis().pages[0])
    assert [b.papel for b in pagina.blocos] == ["header", "", "caption", "footer"]
    de_novo = paginas_extraidas_para_documento([pagina], document_id="l")
    assert [b.kind for b in de_novo.pages[0].blocks] == ["header", "paragraph", "caption", "footer"]


def test_o_cabecalho_e_o_rodape_ficam_fora_do_corpo(tmp_path):
    docx = pytest.importorskip("docx")
    documento = _documento_com_papeis()
    for formato in ("epub", "docx"):
        relatorio = EditorialExporter().export(documento, tmp_path / f"l.{formato}",
                                               ExportOptions(format=formato))
        assert any("2 cabeçalho(s) e rodapé(s)" in a for a in relatorio.warnings)
    with zipfile.ZipFile(tmp_path / "l.epub") as z:
        xhtml = z.read("OEBPS/pagina-0001.xhtml").decode("utf-8")
    paragrafos = docx.Document(str(tmp_path / "l.docx")).paragraphs
    for texto in (xhtml, " ".join(p.text for p in paragrafos)):
        assert "CABECALHO" not in texto and "RODAPE" not in texto
        assert "Prosa do livro." in texto and "Legenda do diagrama" in texto
    [legenda] = [p for p in paragrafos if p.text == "Legenda do diagrama"]
    assert legenda.style.name == "Caption"


def test_a_pagina_do_leitor_nao_tem_papel_e_o_arquivo_nao_muda(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    pagina = livro.PaginaExtraida(0, [livro.Paragrafo("Um."), livro.Paragrafo("Dois.")])
    assert [b.papel for b in pagina.blocos] == ["", ""]
    exportar.para_epub([pagina], str(tmp_path / "a.epub"), titulo="L")
    with zipfile.ZipFile(tmp_path / "a.epub") as z:
        corpo = z.read("OEBPS/pagina-0001.xhtml").decode("utf-8")
    assert '<p class="primeira">Um.</p>\n<p>Dois.</p>' in corpo


# ----------------------------------------------------------------------
# A imagem da página
# ----------------------------------------------------------------------

def _pdf(caminho, texto="original"):
    with fitz.open() as doc:
        doc.new_page(width=200, height=200).insert_text((20, 50), texto)
        doc.save(caminho)
    return caminho


def _documento_de(pdf, sha=None):
    documento = paginas_extraidas_para_documento(
        [livro.PaginaExtraida(0, [livro.Paragrafo("x")], dpi=72)], document_id="l")
    documento.metadata["source_path"] = str(pdf)
    documento.source_sha256 = DocumentSource.from_path(pdf).sha256 if sha is None else sha
    return documento


def test_o_pdf_trocado_no_mesmo_caminho_nao_da_imagem(tmp_path, caplog):
    pdf = _pdf(tmp_path / "l.pdf")
    documento = _documento_de(pdf)
    provedor = ProvedorDePaginas(documento)
    assert provedor.imagem(0) is not None
    provedor.fechar()
    _pdf(pdf, "outro livro")
    with caplog.at_level(logging.WARNING):
        provedor = ProvedorDePaginas(documento)
        assert provedor.imagem(0) is None and provedor.imagem(0) is None
    assert len([r for r in caplog.records if "não é o arquivo que se leu" in r.getMessage()]) == 1


def test_sem_identidade_no_documento_a_imagem_sai(tmp_path):
    provedor = ProvedorDePaginas(_documento_de(_pdf(tmp_path / "l.pdf"), sha=""))
    assert provedor.imagem(0) is not None
    provedor.fechar()


def test_a_falha_da_imagem_fala(tmp_path, caplog):
    ruim = tmp_path / "l.pdf"
    ruim.write_bytes(b"isto nao e um pdf")
    with caplog.at_level(logging.WARNING):
        assert ProvedorDePaginas(_documento_de(ruim)).imagem(0) is None
    assert any("a imagem da página 1 não saiu" in r.getMessage() for r in caplog.records)


# ----------------------------------------------------------------------
# page_id
# ----------------------------------------------------------------------

def test_o_resultado_casa_com_a_pagina_pelo_id():
    fonte = DocumentSource.from_pages([SourcePage(i, text_layer="x") for i in range(4)],
                                      source_id="l", title="L")

    def leitor(evidence, options, token):
        if evidence.page_index == 2:
            raise ValueError("quebrou")
        return PageResult(f"meu-{evidence.page_index}", regions=[
            RegionResult("r", "body", 0, 1.0, (0, 0, 10, 10), text=f"texto {evidence.page_index}")])

    documento = EditorialPipeline(page_processor=leitor).process(
        fonte, ProcessOptions(use_cache=False, page_indices=(3, 0, 2)))
    assert [p.page_index for p in documento.pages] == [0, 2, 3]
    assert [b.decision.value for p in documento.pages for b in p.blocks] == ["texto 0", "texto 3"]
    quebrada = documento.pages[1]
    assert quebrada.page_id == "page-0002" and any("quebrou" in a for a in quebrada.warnings)
    assert [p.page_id for p in documento.pages] == ["meu-0", "page-0002", "meu-3"]


def test_a_pagina_do_cache_de_antes_casa_pelo_indice():
    assert editorial_pipeline._page_id_da_origem(
        PageResult("qualquer", metadata={"page_index": 7})) == "page-0007"


# ----------------------------------------------------------------------
# Uma só ExportOptions, uma só faixas
# ----------------------------------------------------------------------

def test_ha_uma_so_exportoptions_e_um_so_relatorio():
    assert editorial_pipeline.ExportOptions is editorial_export.ExportOptions
    assert editorial_pipeline.ExportReport is editorial_export.ExportReport
    assert editorial_pipeline.SUPPORTED_EXPORTS is editorial_export.EXPORT_FORMATS
    assert not hasattr(editorial_legacy, "_faixas") and not hasattr(editorial_export, "_faixas")
    assert editorial_legacy.faixas_do_estilo is editorial_export.faixas_do_estilo


def test_paginas_sao_paginas_revisadas(tmp_path):
    """O contrato: a fachada escreve o que recebe, sem aplicar a revisão de novo; sem
    páginas, aplica às da leitura."""
    from core.editorial_review import ReviewSession

    paginas = [livro.PaginaExtraida(0, [livro.Paragrafo("Cru."), livro.Paragrafo("Sai.")])]
    sessao = ReviewSession(paginas_extraidas_para_documento(paginas, document_id="l"))
    sessao.edit("block-l-p0001-b0000", "Revisado.")
    sessao.reject("block-l-p0001-b0001")

    class Extrator:
        ultimas_paginas = paginas

    def corpo(pipeline, nome, **kw):
        pipeline.export(sessao.document, tmp_path / nome,
                        ExportOptions(format="epub", escritor={"titulo": "L"}, **kw))
        with zipfile.ZipFile(tmp_path / nome) as z:
            return z.read("OEBPS/pagina-0001.xhtml").decode("utf-8")

    prontas = aplicar_revisao(paginas, sessao.document)
    for texto in (corpo(EditorialPipeline(), "a.epub", paginas=prontas),
                  corpo(EditorialPipeline(legacy_extractor=Extrator()), "b.epub"),
                  corpo(EditorialPipeline(), "c.epub")):
        assert "Revisado." in texto and "Sai." not in texto
    assert "Cru." in corpo(EditorialPipeline(), "d.epub", paginas=paginas)


def test_sem_opcoes_a_fachada_grava_json(tmp_path):
    documento = _documento_com_papeis()
    relatorio = EditorialPipeline().export(documento, tmp_path / "l.json")
    assert relatorio.format == "json"
    assert EditorialDocument.load_json(tmp_path / "l.json").document_id == "l"
