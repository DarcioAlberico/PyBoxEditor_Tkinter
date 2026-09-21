"""
Testes de `core/editor/docx_io.py` (ED-09; SPEC_EDITOR §10.3): o livro sintético
completo (`editor_livros.livro_completo`) escrito em DOCX e lido de volta **no XML do
zip** — estilos e runs da §6.2/§6.3, lista alfabética a partir de 3, legendas com `SEQ`
e `_Ref`, `descr` da figura e do diagrama, o diagrama em fonte na tabela 1×1 e a queda
para PNG com aviso, notas de rodapé e de fim reais, quebra de página só onde há
`QuebraDePagina`, hiperlinks, `REF`, sumário com `PAGEREF`, rodapé `PAGE`, cabeçalhos
par e ímpar, página e margens, hifenização (AC-ED09-1); as costuras do pacote
(AC-ED09-2); `RuntimeError` sem `python-docx` (AC-ED09-3); e o golden de
`tests/dados/editor/docx_golden/` — regravado com `python tests/test_editor_docx.py
--gravar-golden` quando a saída muda de propósito.

Rodar sem pytest:      python tests/test_editor_docx.py
"""

import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import docx_io
from core.editor import modelo as m
from core.editor.conversao import OpcoesDeConversao

PASTA_DO_GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados", "editor", "docx_golden")
PARTES_DO_GOLDEN = ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml", "word/numbering.xml")
pytest.importorskip("docx")


def _escrever(tmp_path, livro=None, **opcoes):
    livro = livro or editor_livros.livro_completo()
    caminho = str(tmp_path / "livro.docx")
    relatorio = docx_io.escrever(livro, caminho, OpcoesDeConversao(**opcoes))
    return caminho, relatorio


def _partes(caminho):
    with zipfile.ZipFile(caminho) as z:
        return {nome: z.read(nome).decode("utf-8") for nome in z.namelist() if nome.endswith((".xml", ".rels"))}


def _conta(padrao, texto):
    return len(re.findall(padrao, texto))


# ----------------------------------------------------------------------
# AC-ED09-1
# ----------------------------------------------------------------------

def test_ac1_o_livro_sintetico_completo_sai_com_tudo_da_secao_10_3(tmp_path):
    caminho, relatorio = _escrever(tmp_path, modo_de_diagrama="fonte")
    partes = _partes(caminho)
    doc = partes["word/document.xml"]
    estilos = partes["word/styles.xml"]

    # estilos de parágrafo (§6.3), com os nomes do Word, e `w:lang` em todos
    for nome in ("Primeira", "Notacao", "Comentario", "Destaque", "Epigrafe", "Assinatura", "CabecalhoDeDiagrama",
                 "Caption", "Quote", "Heading1", "Heading6", "ListParagraph", "TOC1", "TOC3", "TOCHeading"):
        assert f'w:pStyle w:val="{nome}"' in doc, nome
    for nome in ("footnote text", "endnote text", "footnote reference", "endnote reference", "toc 1", "toc 6",
                 "Hyperlink", "Lance", "NAG", "Figurina", "Simbolo", "Versalete", "Jogador", "Abertura", "Ilha"):
        assert f'<w:name w:val="{nome}"/>' in estilos, nome
    # os nomes internos do Word nascem sem `customStyle` (senão o Word cria "…1" ao lado do dele)
    for style_id in ("FootnoteText", "EndnoteText", "FootnoteReference", "EndnoteReference", "TOC1", "Hyperlink"):
        assert re.search(rf'<w:style w:type="\w+" w:styleId="{style_id}">', estilos), style_id
    assert _conta(r'<w:noProof/>', estilos) >= 3                      # Notacao, Lance, NAG
    assert _conta(r'<w:lang w:val="pt-BR"/>', estilos) > 30

    # runs (§6.2)
    for tag in ("<w:b/>", "<w:i/>", '<w:u w:val="single"/>', "<w:strike/>", "<w:smallCaps/>",
                '<w:vertAlign w:val="superscript"/>', '<w:vertAlign w:val="subscript"/>',
                '<w:rFonts w:ascii="Arial"', '<w:sz w:val="18"/>', '<w:color w:val="FF0000"/>',
                '<w:shd w:val="clear" w:color="auto" w:fill="003366"/>', '<w:fill="FFFF00"/>'.replace("<w:", "w:"),
                '<w:lang w:val="en"/>', '<w:rStyle w:val="Lance"/>', '<w:rStyle w:val="NAG"/>',
                '<w:rStyle w:val="Figurina"/>', '<w:rStyle w:val="ComentarioCaractere"/>',
                '<w:rStyle w:val="Jogador"/>', '<w:rStyle w:val="Abertura"/>', '<w:rFonts w:ascii="Consolas"',
                '<w:br/>', '<w:rStyle w:val="Ilha"/>', '<w:rStyle w:val="Hyperlink"/>'):
        assert tag in doc, tag
    # fundo escuro → texto branco; o símbolo na fonte de recurso
    assert re.search(r'<w:color w:val="FFFFFF"/>.*?<w:shd [^>]*w:fill="003366"/>', doc, re.S) or \
        re.search(r'<w:shd [^>]*w:fill="003366"/>.*?<w:color w:val="FFFFFF"/>', doc, re.S)
    assert 'w:ascii="Simbolos de Xadrez"' in doc

    # listas: numeração própria, alfabética começando em 3, romana
    numbering = partes["word/numbering.xml"]
    assert _conta("<w:numPr>", doc) == 6
    assert '<w:startOverride w:val="3"/>' in numbering
    assert '<w:numFmt w:val="lowerLetter"/>' in numbering and '<w:numFmt w:val="lowerRoman"/>' in numbering
    assert '<w:numFmt w:val="bullet"/>' in numbering and _conta(r'<w:ind w:left="\d+" w:hanging="\d+"/>', numbering) >= 27

    # tabela com cabeçalho, largura e legenda `SEQ Tabela` com o marcador `_Ref`
    assert "<w:tblHeader/>" in doc and '<w:tblW w:type="pct" w:w="4000"/>' in doc
    assert re.search(r'<w:bookmarkStart w:id="\d+" w:name="_Ref1"/>.*?Tabela .*?SEQ Tabela .*?<w:bookmarkEnd', doc, re.S)
    assert _conta(r'SEQ (Tabela|Figura|Diagrama) \\\* ARABIC', doc) == 3

    # figura com `descr`; SVG rasterizado; diagrama em imagem com `descr` = FEN
    assert 'descr="Uma foto"' in doc and 'descr="Um desenho"' in doc
    assert f'descr="{editor_livros.FEN}"' in doc
    assert any("rasterizado" in a for a in relatorio.avisos)
    # diagrama em fonte na tabela 1×1 (a Merida com coordenadas em glifo: dez colunas); a SkakNew com
    # coordenadas cai para PNG com aviso
    assert _conta(r'<w:tblCaption w:val="Diagrama"/>', doc) == 3
    assert _conta(rf'<w:tblDescription w:val="{re.escape(editor_livros.FEN)}"/>', doc) == 3
    assert 'w:ascii="ChessMerida-Diagram"' in doc and 'w:ascii="SkakNew-Diagram"' in doc
    assert any("dia-skak-coord" in a and "coordenadas" in a for a in relatorio.avisos)
    assert relatorio.diagramas_fonte == 3 and relatorio.diagramas_png == 1
    assert set(relatorio.fontes_embutidas) == {"ChessMerida-Diagram", "SkakNew-Diagram", "Simbolos de Xadrez"}
    with zipfile.ZipFile(caminho) as z:
        assert len([n for n in z.namelist() if n.startswith("word/fonts/")]) == 3

    # notas de rodapé e de fim reais
    assert _conta("<w:footnoteReference ", doc) == 1 and _conta("<w:endnoteReference ", doc) == 1
    notas = partes["word/footnotes.xml"]
    assert "Nota de rodapé com" in notas and "<w:footnoteRef/>" in notas and 'w:anchor' not in notas
    assert "<w:hyperlink r:id=" in notas and "hyperlink" in partes["word/_rels/footnotes.xml.rels"]
    fim = partes["word/endnotes.xml"]
    assert "Nota de fim." in fim and "Segundo parágrafo." in fim and "<w:endnoteRef/>" in fim
    assert 'w:pStyle w:val="FootnoteText"' in notas and 'w:pStyle w:val="EndnoteText"' in fim

    # quebra de página só onde há `QuebraDePagina`; as 12 marcas + a do trecho viram marcadores sem quebra
    assert _conta(r'<w:br w:type="page"/>', doc) == 1
    assert _conta(r'<w:bookmarkStart w:id="\d+" w:name="pg-\d+"/>', doc) == 13
    assert 'w:name="pg-7"' in doc and 'w:name="pg-22"' in doc
    assert '<w:pageBreakBefore/>' in estilos                            # o capítulo abre página pelo estilo

    # hiperlinks (externo e interno), `REF _Ref`, sumário com uma entrada e um `PAGEREF` por título (níveis 1–3)
    assert '<w:hyperlink r:id="rId' in doc and '<w:hyperlink w:anchor="bm_1_alvo"' in doc
    assert 'w:name="bm_1_alvo"' in doc
    assert _conta(r'REF _Ref\d \\h', doc) == 4
    assert _conta(r'<w:sdt>', doc) == 1 and 'TOC \\o "1-3" \\h \\z \\u' in doc
    assert _conta(r'PAGEREF _Toc\d+ \\h', doc) == 6 and _conta(r'<w:hyperlink w:anchor="_Toc\d+"', doc) == 6
    assert _conta(r'w:name="_Toc\d+"', doc) == 10
    assert doc.index("<w:sdt>") < doc.index("Capítulo um")

    # rodapé `PAGE`; cabeçalhos par (título) e ímpar (`STYLEREF 1`); página e margens de `Livro.pagina`
    rodapes = [partes[n] for n in partes if re.match(r"word/footer\d+\.xml", n)]
    assert len(rodapes) == 2 and all("> PAGE <" in r or " PAGE " in r for r in rodapes)
    cabecalhos = {n: partes[n] for n in partes if re.match(r"word/header\d+\.xml", n)}
    assert any("STYLEREF 1" in c for c in cabecalhos.values()) and any("Livro completo" in c for c in cabecalhos.values())
    sect = re.search(r"<w:sectPr.*?</w:sectPr>", doc, re.S).group(0)
    assert 'w:type="even"' in sect and 'w:type="default"' in sect
    assert re.search(r'<w:pgSz w:w="793[78]" w:h="11906"/>', sect)           # 140 × 210 mm (twips arredondados)
    assert re.search(r'<w:pgMar w:top="850" w:right="680" w:bottom="1020" w:left="1134"', sect)
    settings = partes["word/settings.xml"]
    assert '<w:autoHyphenation w:val="true"/>' in settings and "<w:mirrorMargins/>" in settings

    # o relatório
    assert relatorio.formato == "docx" and relatorio.arquivos == [caminho] and relatorio.capitulos == 2
    assert relatorio.notas == 2 and relatorio.ilhas == 2 and relatorio.figuras == 2 and relatorio.tempo_s > 0
    assert sum("Ilha" in a for a in relatorio.avisos) == 2


# ----------------------------------------------------------------------
# AC-ED09-2, AC-ED09-3
# ----------------------------------------------------------------------

def test_ac2_as_costuras_do_pacote_content_types_footnotes_settings_e_rels(tmp_path):
    caminho, _rel = _escrever(tmp_path)
    partes = _partes(caminho)
    tipos = partes["[Content_Types].xml"]
    assert ('<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.footnotes+xml"/>') in tipos
    assert ('<Override PartName="/word/endnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.endnotes+xml"/>') in tipos
    assert 'Extension="odttf"' in tipos
    for nome, ids in (("word/footnotes.xml", ("-1", "0", "1")), ("word/endnotes.xml", ("-1", "0", "1"))):
        xml = partes[nome]
        assert re.findall(r'w:id="(-?\d+)"', xml) == list(ids), nome
        assert 'w:type="separator" w:id="-1"' in xml and 'w:type="continuationSeparator" w:id="0"' in xml
        assert "<w:separator/>" in xml and "<w:continuationSeparator/>" in xml
    settings = partes["word/settings.xml"]
    assert '<w:footnotePr><w:footnote w:id="-1"/><w:footnote w:id="0"/></w:footnotePr>' in settings
    assert '<w:endnotePr><w:endnote w:id="-1"/><w:endnote w:id="0"/></w:endnotePr>' in settings
    assert "<w:evenAndOddHeaders/>" in settings and "<w:mirrorMargins/>" in settings
    assert '<w:updateFields w:val="true"/>' in settings
    ordem = re.findall(r"<w:(\w+)[ />]", settings)
    esperada = [t for t in docx_io.ORDEM_DOS_SETTINGS if t in ordem]
    assert [t for t in ordem if t in docx_io.ORDEM_DOS_SETTINGS] == esperada     # na ordem do esquema
    rels = partes["word/_rels/document.xml.rels"]
    for tipo in ("footnotes", "endnotes", "numbering", "header", "footer", "hyperlink", "image", "styles", "settings"):
        assert f"/relationships/{tipo}\"" in rels, tipo


def test_ac3_sem_python_docx_o_erro_diz_como_instalar(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "docx", None)
    with pytest.raises(RuntimeError) as erro:
        docx_io.escrever(editor_livros.livro_completo(), str(tmp_path / "x.docx"))
    assert "pip install python-docx" in str(erro.value)
    assert not (tmp_path / "x.docx").exists()


# ----------------------------------------------------------------------
# Opções, capítulo em código, falhas anunciadas
# ----------------------------------------------------------------------

def test_o_modo_png_as_notas_no_fim_o_sumario_desligado_e_a_pagina_sem_numero(tmp_path):
    livro = editor_livros.livro_completo()
    livro.pagina.numerar_paginas = False
    livro.pagina.cabecalho_par = ""
    livro.pagina.espelhadas = False
    livro.pagina.hifenizar = False
    caminho, relatorio = _escrever(tmp_path, livro, modo_de_diagrama="png", notas="fim", sumario=False)
    partes = _partes(caminho)
    doc = partes["word/document.xml"]
    assert relatorio.diagramas_png == 4 and relatorio.diagramas_fonte == 0
    assert _conta(rf'descr="{re.escape(editor_livros.FEN)}"', doc) == 4 and "tblCaption" not in doc
    assert relatorio.fontes_embutidas == ["Simbolos de Xadrez"]
    assert "<w:sdt>" not in doc and "PAGEREF" not in doc
    assert _conta("<w:endnoteReference ", doc) == 2 and "footnoteReference" not in doc
    assert "word/footnotes.xml" not in partes and "footnotePr" not in partes["word/settings.xml"]
    assert not [n for n in partes if re.match(r"word/footer\d+\.xml", n)]
    assert "mirrorMargins" not in partes["word/settings.xml"] and "autoHyphenation" not in partes["word/settings.xml"]
    cabecalhos = [partes[n] for n in partes if re.match(r"word/header\d+\.xml", n)]
    assert any("STYLEREF 1" in c for c in cabecalhos)


def test_capitulo_em_codigo_e_convertido_e_o_mal_formado_vira_aviso(tmp_path):
    livro = editor_livros.livro_completo()
    cap2 = livro.capitulos[1]
    from core.editor import xhtml

    cap2.texto_cru = xhtml.escrever(cap2)
    cap2.blocos = []
    livro.capitulos.append(m.Capitulo(arquivo="cap3.xhtml", texto_cru="<html><body><p>aberto</body></html>"))
    caminho, relatorio = _escrever(tmp_path, livro)
    doc = _partes(caminho)["word/document.xml"]
    assert "Alvo do link." in doc and "Fora do sumário" in doc and "aberto" not in doc
    assert any("cap3.xhtml" in a and "mal-formado" in a for a in relatorio.avisos)


def test_imagem_ausente_nota_sem_alvo_e_link_sem_alvo_viram_avisos_e_texto(tmp_path):
    livro = m.Livro(metadados=m.Metadados(titulo="Faltas", idioma="pt"), capitulos=[m.Capitulo(
        arquivo="c.xhtml", blocos=[
            m.Figura(recurso="Images/nao-ha.png", alt="x", legenda=[m.Trecho(texto="Sem imagem")]),
            m.Paragrafo(trechos=[m.Trecho(texto="ver"), m.Trecho(nota="inexistente"),
                                 m.Trecho(texto="perdido", link="outro.xhtml#nada")]),
        ])])
    caminho, relatorio = _escrever(tmp_path, livro)
    doc = _partes(caminho)["word/document.xml"]
    assert "[imagem ausente: Images/nao-ha.png]" in doc and "[nota]" in doc and "perdido" in doc
    assert "<w:hyperlink" not in doc and "footnoteReference" not in doc
    assert sum("não está no livro" in a for a in relatorio.avisos) == 1
    assert sum("sem nota" in a for a in relatorio.avisos) == 1
    assert sum("sem alvo" in a for a in relatorio.avisos) == 1
    assert relatorio.figuras == 1 and relatorio.notas == 0


def test_a_gravacao_e_atomica_e_o_arquivo_reabre_no_python_docx(tmp_path):
    caminho, _rel = _escrever(tmp_path)
    from docx import Document

    documento = Document(caminho)
    assert documento.core_properties.title == "Livro completo" and documento.core_properties.author == "Autora"
    assert documento.core_properties.language == "pt-BR"
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]


# ----------------------------------------------------------------------
# O golden
# ----------------------------------------------------------------------

def _canonico(xml: str) -> str:
    from lxml import etree

    raiz = etree.fromstring(xml.encode("utf-8"))
    return etree.tostring(raiz, pretty_print=True, encoding="unicode")


def gravar_golden(caminho_do_docx: str) -> None:
    os.makedirs(PASTA_DO_GOLDEN, exist_ok=True)
    partes = _partes(caminho_do_docx)
    for parte in PARTES_DO_GOLDEN:
        with open(os.path.join(PASTA_DO_GOLDEN, os.path.basename(parte)), "w", encoding="utf-8", newline="\n") as f:
            f.write(_canonico(partes[parte]))


def test_o_golden_do_livro_completo_nao_mudou(tmp_path):
    caminho, _rel = _escrever(tmp_path, modo_de_diagrama="fonte")
    partes = _partes(caminho)
    for parte in PARTES_DO_GOLDEN:
        golden = os.path.join(PASTA_DO_GOLDEN, os.path.basename(parte))
        assert os.path.isfile(golden), f"golden ausente: {golden} (python tests/test_editor_docx.py --gravar-golden)"
        with open(golden, encoding="utf-8") as f:
            esperado = f.read()
        assert _canonico(partes[parte]) == esperado, f"{parte} mudou — se foi de propósito, regrave o golden"


if __name__ == "__main__":
    if "--gravar-golden" in sys.argv:
        import tempfile

        pasta = tempfile.mkdtemp(prefix="pbe-golden-")
        caminho = os.path.join(pasta, "livro.docx")
        docx_io.escrever(editor_livros.livro_completo(), caminho, OpcoesDeConversao(modo_de_diagrama="fonte"))
        gravar_golden(caminho)
        print("golden gravado em", PASTA_DO_GOLDEN)
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
