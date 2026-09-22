"""
Testes de `core/editor/pdf_io.py` (ED-12; SPEC_EDITOR §10.5, AC-ED12-1): o PDF do livro
completo tem ≥ 3 páginas no formato de `Livro.pagina`, texto pesquisável, o diagrama como
imagem, o número de página, cabeçalho par ≠ ímpar, o sumário do PDF (`get_toc`) com os
títulos, os metadados e um link interno que funciona (`get_links`); as margens espelhadas
alternam; o modo `fonte` embute as fontes de diagrama; os links entre capítulos caem na
página certa.

Rodar sem pytest:      .venv/Scripts/python.exe tests/test_editor_pdf.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import modelo as m, pdf_io
from core.editor.conversao import OpcoesDeConversao


def _livro():
    livro = editor_livros.livro_completo()
    livro.pagina = m.FormatoDePagina(largura_mm=148, altura_mm=210, margens_mm=(18, 15, 18, 22), espelhadas=True,
                                     cabecalho_par="titulo", cabecalho_impar="capitulo", numerar_paginas=True)
    return livro


def test_ac1_o_pdf_paginado_do_livro_completo(tmp_path):
    import fitz

    livro = _livro()
    caminho = str(tmp_path / "livro.pdf")
    rel = pdf_io.escrever(livro, caminho)
    assert rel.formato == "pdf" and rel.arquivos == [caminho] and rel.metadados["paginas"] >= 3
    assert rel.capitulos == 2 and rel.diagramas_png == 1 and rel.diagramas_fonte == 3 and rel.tempo_s > 0
    assert set(rel.fontes_embutidas) >= {"SkakNew-Diagram", "ChessMerida-Diagram"}
    doc = fitz.open(caminho)
    try:
        assert doc.page_count == rel.metadados["paginas"] >= 3
        # o papel é o de Livro.pagina
        assert abs(doc[0].rect.width - 148 * 72 / 25.4) < 0.5 and abs(doc[0].rect.height - 210 * 72 / 25.4) < 0.5
        # texto pesquisável
        assert doc[0].search_for("Primeira linha sem recuo") and "Capítulo um" in doc[0].get_text()
        # o diagrama em imagem e a figura
        assert sum(len(p.get_images()) for p in doc) >= 2
        # número de página em toda página; cabeçalho par (título do livro) ≠ ímpar (capítulo)
        for k, page in enumerate(doc):
            texto = page.get_text()
            assert str(k + 1) in texto
            if k % 2 == 1:
                assert "Livro completo" in texto                            # par: o título do livro
            else:
                assert "Capítulo" in texto                                  # ímpar: o capítulo corrente
        # o sumário do PDF tem os títulos, com os níveis sem salto
        toc = doc.get_toc()
        titulos = [t[1] for t in toc]
        assert titulos[0] == "Capítulo um" and "Capítulo dois" in titulos and "Título 2" in titulos
        assert toc[0][0] == 1 and all(toc[i][0] <= toc[i - 1][0] + 1 for i in range(1, len(toc)))
        pagina_do_dois = next(t[2] for t in toc if t[1] == "Capítulo dois")
        assert pagina_do_dois == doc.page_count                             # o capítulo dois começa em página nova
        # metadados e idioma
        assert doc.metadata["title"] == "Livro completo" and doc.metadata["author"] == "Autora"
        assert doc.metadata["creator"] == "PyBoxEditor" and doc.language == "pt"
        # um link interno funcional: o "Alvo do link" do capítulo dois
        links = [lk for p in doc for lk in p.get_links()]
        internos = [lk for lk in links if lk["kind"] == fitz.LINK_GOTO]
        externos = [lk for lk in links if lk["kind"] == fitz.LINK_URI]
        assert any(lk["page"] == pagina_do_dois - 1 for lk in internos)     # cai na página do capítulo dois
        assert any(lk["uri"] == "https://example.org/x" for lk in externos)
        assert any(lk["page"] == 0 for lk in internos) or len(internos) >= 2   # o link ao título do próprio capítulo
        # margens espelhadas: o texto da página ímpar começa mais à direita (margem interna à esquerda)
        x0_impar = min(b[0] for b in doc[0].get_text("blocks") if b[4].strip() and b[1] > 40)
        x0_par = min(b[0] for b in doc[1].get_text("blocks") if b[4].strip() and b[1] > 40)
        assert x0_impar - x0_par > 5 * 72 / 25.4
    finally:
        doc.close()


def test_o_modo_fonte_embute_a_fonte_e_a_pagina_sem_espelho_nem_numero(tmp_path):
    import fitz

    livro = _livro()
    livro.pagina = m.FormatoDePagina(largura_mm=120, altura_mm=180, margens_mm=(10, 10, 10, 10), espelhadas=False,
                                     cabecalho_par="", cabecalho_impar="", numerar_paginas=False)
    caminho = str(tmp_path / "fonte.pdf")
    rel = pdf_io.escrever(livro, caminho, OpcoesDeConversao(modo_de_diagrama="fonte"))
    doc = fitz.open(caminho)
    try:
        fontes = {f[3] for p in doc for f in p.get_fonts()}
        assert any("SkakNew" in f for f in fontes) and any("Merida" in f for f in fontes)
        assert "SkakNew-Diagram" in rel.fontes_embutidas
        # sem cabeçalho nem número: a primeira linha da página 2 é do texto
        assert not doc[1].get_text().strip().startswith(("Livro completo", "2"))
        x0 = [min(b[0] for b in doc[k].get_text("blocks") if b[4].strip()) for k in range(2)]
        assert abs(x0[0] - x0[1]) < 1                                        # sem espelho, a mesma margem
    finally:
        doc.close()


def test_um_livro_sem_folha_e_com_diagrama_que_nao_desenha_avisa_e_sai(tmp_path):
    import fitz

    livro = m.Livro(metadados=m.Metadados(titulo="Sem folha", idioma="en"), capitulos=[
        m.Capitulo(arquivo="Text/a.xhtml", blocos=[m.Titulo(trechos=[m.Trecho(texto="Only chapter")], nivel=1),
                                                    m.Paragrafo(trechos=[m.Trecho(texto="Body text.")]),
                                                    m.Diagrama(fen="8/8/8/8/8/8/8/K6k w - - 0 1", fonte="Inexistente")])])
    caminho = str(tmp_path / "solto.pdf")
    rel = pdf_io.escrever(livro, caminho)
    assert rel.metadados["paginas"] == 1 and any("não desenhado" in a or "sem arquivo" in a for a in rel.avisos)
    doc = fitz.open(caminho)
    try:
        assert "Body text." in doc[0].get_text() and doc.get_toc() == [[1, "Only chapter", 1]]
    finally:
        doc.close()
    assert pdf_io.chave_do_capitulo("Text/cap 1.xhtml") == "Text_cap_1_xhtml"
    assert abs(pdf_io.mm(25.4) - 72.0) < 1e-9


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
