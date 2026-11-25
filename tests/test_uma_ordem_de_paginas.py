"""Uma ordem de páginas para os seis formatos (RG-17, R-32; invariante 10).

O HTML, o TXT e o PDF ordenavam por `page_index`; EPUB, DOCX e JSON seguiam a lista que
chegava. Agora quem ordena é o `EditorialDocument`, na construção, `aplicar_revisao` devolve
as páginas nessa ordem, e nenhum exportador reordena.
"""

import inspect
import json
import zipfile

import fitz
import pytest

from core import editorial_export, livro
from core.editorial_adapters import (documento_para_paginas_extraidas,
                                     paginas_extraidas_para_documento)
from core.editorial_export import EditorialExporter, ExportOptions
from core.editorial_legacy import aplicar_revisao
from core.editorial_model import EditorialDocument
from core.editorial_pipeline import EditorialPipeline
from core.editorial_pipeline import ExportOptions as OpcoesDaFachada

MARCAS = ["PAGINA-DOIS", "PAGINA-CINCO", "PAGINA-NOVE"]


def _paginas():
    """As páginas 9, 2 e 5, como `livro.extrair(paginas=[8, 1, 4])` as devolve."""
    return [livro.PaginaExtraida(numero=n, blocos=[livro.Paragrafo(f"Texto da {marca}.")],
                                 largura=1000, altura=1400, dpi=200)
            for n, marca in ((8, MARCAS[2]), (1, MARCAS[0]), (4, MARCAS[1]))]


def _documento():
    return paginas_extraidas_para_documento(_paginas(), document_id="livro", title="Livro",
                                            language="pt")


def _texto(caminho, formato):
    if formato in ("html", "txt"):
        return caminho.read_text(encoding="utf-8")
    if formato == "json":
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return " ".join(json.dumps(p, ensure_ascii=False) for p in dados["pages"])
    if formato == "epub":
        with zipfile.ZipFile(caminho) as z:
            opf = z.read("OEBPS/content.opf").decode("utf-8")
            hrefs = dict((item.split('id="')[1].split('"')[0], item.split('href="')[1].split('"')[0])
                         for item in opf.split("<item ")[1:] if 'id="' in item)
            ordem = [i.split('"')[0] for i in opf.split('<itemref idref="')[1:]]
            return " ".join(z.read("OEBPS/" + hrefs[i]).decode("utf-8") for i in ordem)
    if formato == "docx":
        docx = pytest.importorskip("docx")
        return " ".join(p.text for p in docx.Document(str(caminho)).paragraphs)
    with fitz.open(caminho) as pdf:
        return " ".join(pagina.get_text() for pagina in pdf)


def _ordem(texto):
    posicoes = [texto.find(marca) for marca in MARCAS]
    assert min(posicoes) >= 0, texto[:400]
    return sorted(MARCAS, key=texto.find)


@pytest.mark.parametrize("formato", ["epub", "docx", "html", "txt", "pdf", "json"])
@pytest.mark.parametrize("com_leitura", [True, False])
def test_os_seis_formatos_na_mesma_ordem(tmp_path, formato, com_leitura):
    class Extrator:
        ultimas_paginas = _paginas() if com_leitura else []

    destino = tmp_path / f"livro.{formato}"
    origem = tmp_path / "origem.pdf"                # dez páginas, para o PDF ter a nona
    with fitz.open() as pdf:
        for _ in range(10):
            pdf.new_page()
        pdf.save(origem)
    documento = _documento()
    documento.metadata["source_path"] = str(origem)
    EditorialPipeline(legacy_extractor=Extrator()).export(
        documento, destino, OpcoesDaFachada(format=formato, escritor={"titulo": "Livro"}))
    assert _ordem(_texto(destino, formato)) == MARCAS


@pytest.mark.parametrize("formato", ["epub", "docx", "html", "txt"])
def test_o_exportador_sozinho_tambem(tmp_path, formato):
    destino = tmp_path / f"livro.{formato}"
    EditorialExporter().export(_documento(), destino, ExportOptions(format=formato))
    assert _ordem(_texto(destino, formato)) == MARCAS


def test_o_documento_ordena_na_construcao_e_na_leitura(tmp_path):
    documento = _documento()
    assert [p.page_index for p in documento.pages] == [1, 4, 8]
    dados = documento.to_dict()
    dados["pages"].reverse()                        # um JSON gravado antes da RG-17
    assert [p.page_index for p in EditorialDocument.from_dict(dados).pages] == [1, 4, 8]


def test_aplicar_revisao_devolve_na_ordem_do_documento():
    assert [p.numero for p in aplicar_revisao(_paginas(), _documento())] == [1, 4, 8]
    assert [p.numero for p in aplicar_revisao(_paginas()[:1], _documento())] == [1, 4, 8]
    assert [p.numero for p in documento_para_paginas_extraidas(_documento())] == [1, 4, 8]


def test_paginas_de_mesmo_indice_ficam_na_ordem_em_que_chegaram():
    primeira, segunda = _documento().pages[:2]
    segunda.page_index = primeira.page_index
    documento = EditorialDocument("livro", "", "pt", [segunda, primeira])
    assert [p.page_id for p in documento.pages] == [segunda.page_id, primeira.page_id]


def test_nenhum_exportador_reordena_as_paginas():
    fonte = inspect.getsource(editorial_export)
    assert "item.page_index" not in fonte and "sorted(document.pages" not in fonte
