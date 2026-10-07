"""
PD-06 (`docs/ROADMAP_PENDENCIAS.md`) — o itálico da camada de texto chega ao arquivo.

A F111 contou **0 runs em itálico em 36.442**: o `Paragrafo` tinha `negrito` e
nada mais. Onde o PDF declara o estilo — a bandeira `TEXT_FONT_ITALIC` do
MuPDF, ou o nome da fonte (`TimesNewRomanPS-ItalicMT`, `Helvetica-Oblique`,
`MinionPro-It`) —, a camada de texto (F110) o lê como lê o negrito, e ele sai
`<em>` no EPUB, `run.italic` no DOCX, `italic_spans` no IR e itálico no editor.
Medido nos PDFs do corpus: 4,4% dos glifos do Dvoretsky e 2,0% do Darcy Lima;
os outros não têm fonte que o diga.

No OCR o itálico continua vazio: não há régua de inclinação medida, e marcar
sem régua seria inventar ênfase.
"""

import sys
import zipfile

import fitz
import pytest

from core import exportar, livro, pdf_nativo
from core.livro import PaginaExtraida, Paragrafo

INCLINADO = "variation"
FRASE = ["The ", INCLINADO, " is the whole point of the ending."]


def _pdf_com_italico(caminho, inclinada="heit", reta="helv"):
    """Uma linha de prosa com uma palavra em itálico no meio, e mais uma para
    o parágrafo não ser curto como título."""
    doc = fitz.open()
    p = doc.new_page(width=400, height=600)
    x = 50.0
    for k, pedaco in enumerate(FRASE):
        fonte = inclinada if k == 1 else reta
        p.insert_text((x, 100), pedaco, fontname=fonte, fontsize=10)
        x += fitz.get_text_length(pedaco, fontname=fonte, fontsize=10)
    p.insert_text((40, 112), "And the king walks to the queenside at once.",
                  fontname=reta, fontsize=10)
    doc.save(str(caminho))
    doc.close()
    return str(caminho)


def _paragrafo(pdf):
    [pagina] = pdf_nativo.extrair(pdf).paginas
    [paragrafo] = [b for b in pagina.blocos if isinstance(b, Paragrafo)]
    return pagina, paragrafo


@pytest.mark.parametrize("nome, flags, esperado", [
    ("TimesNewRomanPS-ItalicMT", 0, True),
    ("ABCDEF+TimesNewRomanPS-BoldItalicMT", 0, True),
    ("Helvetica-Oblique", 0, True),
    ("MinionPro-It", 0, True),
    ("MinionPro-BoldIt", 0, True),
    ("Times-Roman", 2, True),
    ("TimesNewRomanPS-BoldMT", 16, False),
    ("Helvetica", 0, False),
    ("Arial-Italicless", 0, True),   # o nome diz "italic"; é o que se tem
    ("SkakNew-Figurine", 0, False),
])
def test_o_italico_pela_bandeira_ou_pelo_nome(nome, flags, esperado):
    assert pdf_nativo._e_italico(nome, flags) is esperado


def test_a_palavra_em_italico_vira_trecho(tmp_path):
    _pagina, paragrafo = _paragrafo(_pdf_com_italico(tmp_path / "i.pdf"))
    inicio = paragrafo.texto.index(INCLINADO)
    assert paragrafo.italico == [(inicio, inicio + len(INCLINADO))]
    assert paragrafo.negrito == []


def test_negrito_e_italico_juntos(tmp_path):
    _pagina, paragrafo = _paragrafo(
        _pdf_com_italico(tmp_path / "bi.pdf", inclinada="hebi"))
    inicio = paragrafo.texto.index(INCLINADO)
    trecho = (inicio, inicio + len(INCLINADO))
    assert paragrafo.italico == [trecho] and paragrafo.negrito == [trecho]


def test_o_epub_escreve_em(tmp_path):
    pagina, _paragrafo_ = _paragrafo(_pdf_com_italico(tmp_path / "i.pdf"))
    destino = str(tmp_path / "i.epub")
    exportar.para_epub([pagina], destino, titulo="Teste")
    with zipfile.ZipFile(destino) as z:
        alvo = [n for n in z.namelist() if n.startswith("OEBPS/pagina")][0]
        xhtml = z.read(alvo).decode("utf-8")
    assert f"The <em>{INCLINADO}</em> is" in xhtml


def test_negrito_italico_no_epub_e_strong_em():
    paragrafo = Paragrafo("um dois tres", negrito=[(0, 7)], italico=[(3, 12)])
    xhtml = exportar._marcado(paragrafo, "")
    assert xhtml == ("<strong>um </strong><strong><em>dois</em></strong>"
                     "<em> tres</em>")


def test_sem_italico_o_corte_e_o_de_sempre():
    """O arquivo de quem não tem itálico sai byte a byte como saía."""
    texto, negrito = "abc def ghi", [(4, 7), (0, 3)]
    assert exportar.trechos_com_estilo(texto, negrito) == [
        (t, forte, False) for t, forte in exportar.trechos(texto, negrito)]


def test_o_docx_escreve_run_italico(tmp_path):
    pytest.importorskip("docx")
    pagina, _p = _paragrafo(_pdf_com_italico(tmp_path / "i.pdf"))
    destino = str(tmp_path / "i.docx")
    exportar.para_docx([pagina], destino, titulo="Teste")
    from docx import Document
    runs = [r for p in Document(destino).paragraphs for r in p.runs]
    inclinados = [r.text for r in runs if r.italic]
    assert inclinados == [INCLINADO]
    assert not any(r.italic is False for r in runs), \
        "o run redondo não fala de itálico (`None`), como o negrito"


def test_o_ir_e_o_editor_levam_o_italico(tmp_path):
    from core.editor.importar_ir import de_paginas
    from core.editor.modelo import Paragrafo as ParagrafoDoEditor
    from core.editorial_adapters import (pagina_editorial_para_extraida,
                                         pagina_extraida_para_pagina)
    from core.editorial_export import ExportOptions, _block_html

    pagina, paragrafo = _paragrafo(_pdf_com_italico(tmp_path / "i.pdf"))
    editorial = pagina_extraida_para_pagina(pagina, document_id="d")
    [bloco] = [b for b in editorial.blocks if b.kind == "paragraph"]
    assert bloco.style["italic_spans"] == [list(t) for t in paragrafo.italico]
    assert f"<em>{INCLINADO}</em>" in _block_html(bloco, ExportOptions())
    assert pagina_editorial_para_extraida(editorial).blocos[0].italico == paragrafo.italico

    livro_do_editor, _relatorio = de_paginas([pagina])
    trechos = [t for c in livro_do_editor.capitulos for b in c.blocos
               if isinstance(b, ParagrafoDoEditor) for t in b.trechos]
    assert [t.texto for t in trechos if t.italico] == [INCLINADO]


def test_o_ir_de_quem_nao_tem_italico_nao_muda():
    from core.editorial_adapters import pagina_extraida_para_pagina

    pagina = PaginaExtraida(numero=0, blocos=[Paragrafo("prosa comum", negrito=[(0, 5)])])
    [bloco] = pagina_extraida_para_pagina(pagina, document_id="d").blocks
    assert "italic_spans" not in bloco.style


def test_o_corte_de_cabecalho_anda_com_o_italico():
    p = Paragrafo("CABEÇALHO texto em italico", italico=[(19, 26)], inicios=[0, 10])
    livro._cortar(p, 0, 10)
    assert p.texto == "texto em italico"
    assert p.texto[p.italico[0][0]:p.italico[0][1]] == "italico"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
