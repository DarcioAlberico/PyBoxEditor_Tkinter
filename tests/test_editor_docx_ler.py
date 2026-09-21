"""
Testes de `core/editor/docx_leitura.py` — `docx_io.ler` (ED-09b; SPEC_EDITOR §10.4, §6.2):
`ler(escrever(livro))` devolve o texto por bloco, os atributos da §6.2 (menos `classe`),
o `papel` pelo estilo, o `fundo` exato, o `corpo_pt` a meio ponto e as marcas de página
(AC-ED09b-1); o FEN igual no diagrama em fonte (tabela 1×1) e em PNG (`descr`), com
`lado=""` (AC-ED09b-2, AC-009); um DOCX de fora com caixa de texto e comentário volta com
o texto preservado e dois avisos, e três `Heading 1` viram três capítulos (AC-ED09b-3).
A leitura não precisa do `python-docx`; a escrita dos fixtures, sim.

Rodar sem pytest:      python tests/test_editor_docx_ler.py
"""

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import docx_io, docx_leitura, epub, modelo as m
from core.editor.conversao import OpcoesDeConversao

FEN = editor_livros.FEN


def _ida_e_volta(tmp_path, **opcoes):
    pytest.importorskip("docx")
    livro = editor_livros.livro_completo()
    caminho = str(tmp_path / "livro.docx")
    docx_io.escrever(livro, caminho, OpcoesDeConversao(**opcoes))
    relido, relatorio = docx_io.ler(caminho)
    return livro, relido, relatorio


# ----------------------------------------------------------------------
# AC-ED09b-1
# ----------------------------------------------------------------------

def test_ac1_ler_escrever_devolve_texto_atributos_papel_fundo_corpo_e_marcas(tmp_path):
    livro, relido, relatorio = _ida_e_volta(tmp_path, modo_de_diagrama="png")
    assert relatorio.formato == "docx" and relatorio.capitulos == 2
    assert [c.arquivo for c in relido.capitulos] == ["Text/cap-0001.xhtml", "Text/cap-0002.xhtml"]
    assert relido.metadados.titulo == "Livro completo" and relido.metadados.idioma == "pt-BR"
    assert [p.nome for p in relido.metadados.autores] == ["Autora"]
    for antes, depois in zip(livro.capitulos, relido.capitulos):
        assert len(antes.blocos) == len(depois.blocos), antes.arquivo
        for a, b in zip(antes.blocos, depois.blocos):
            if isinstance(a, m.IlhaBruta):
                assert isinstance(b, m.Paragrafo) and m.texto_de(b) == "SVG solto"     # a ilha voltou como texto
                continue
            assert type(a) is type(b), (m.texto_de(a), m.texto_de(b))
            if isinstance(a, m.Paragrafo) and not any(t.ilha for t in a.trechos):
                assert m.texto_de(a) == m.texto_de(b), m.texto_de(a)
                assert a.estilo == b.estilo and (not isinstance(a, m.Titulo) or a.nivel == b.nivel)
    cap = relido.capitulos[0]
    # os atributos da §6.2, trecho a trecho (a `classe` não tem lugar no DOCX)
    trechos = cap.blocos[2].trechos
    por_texto = {t.texto.strip(): t for t in trechos}
    assert por_texto["neg"].negrito and por_texto["ita"].italico and por_texto["sub"].sublinhado
    assert por_texto["tach"].tachado and por_texto["Versalete"].versalete
    assert por_texto["x"].posicao == "sobre" and por_texto["2"].posicao == "sub"
    assert por_texto["♕"].familia == "simbolos"
    assert por_texto["arial"].familia == "Arial" and por_texto["arial"].corpo_pt == 9.0
    assert por_texto["arial"].cor == "#ff0000"
    assert por_texto["escuro"].fundo == "#003366" and por_texto["escuro"].cor == ""       # o fundo exato
    assert por_texto["amarelo"].fundo == "#ffff00" and por_texto["english"].lang == "en"
    assert por_texto["23.Nf3"].papel == "lance" and por_texto["!?"].papel == "nag"       # o papel pelo estilo
    assert por_texto["♘"].papel == "figurina" and por_texto["(comentário)"].papel == "comentario"
    assert por_texto["Carlsen"].papel == "jogador" and por_texto["Siciliana"].papel == "abertura"
    assert por_texto["cod"].codigo and por_texto["nova linha"].quebra_antes
    # o corpo a meio ponto
    assert all(t.corpo_pt is None or t.corpo_pt * 2 == int(t.corpo_pt * 2) for t in m.trechos_do_capitulo(cap))
    # a formatação direta do parágrafo
    formatado = next(b for b in cap.blocos if m.texto_de(b) == "Formatado.")
    assert (formatado.alinhamento, formatado.recuo_primeira_em, formatado.recuo_esquerda_em,
            formatado.recuo_direita_em) == ("direita", 0.0, 1.5, 0.5)
    assert (formatado.antes_em, formatado.depois_em, formatado.entrelinha) == (1.0, 0.5, 1.5)
    assert formatado.manter_com_proximo and formatado.manter_linhas
    # as marcas de página de volta (o marcador `pg-n` do começo do parágrafo e o do meio)
    assert [b.pagina for b in cap.blocos if isinstance(b, m.MarcaDePagina)] == list(range(11, 23))
    assert any(t.pagina == 7 and t.texto == "aqui" for t in m.trechos_do_capitulo(cap))
    assert any(isinstance(b, m.QuebraDePagina) for b in cap.blocos) and any(isinstance(b, m.Separador)
                                                                            for b in cap.blocos)
    # listas, tabela, figura, citação, notas, links e referências
    listas = [b for b in cap.blocos if isinstance(b, m.Lista)]
    assert (listas[0].ordenada, listas[0].marcador) == (False, "disco") and listas[0].itens[1].filhos is not None
    assert [m.texto_de(p) for p in listas[0].itens[1].paragrafos] == ["item b", "continuação de b"]
    assert (listas[1].ordenada, listas[1].inicio, listas[1].marcador) == (True, 3, "alfa")
    assert listas[2].marcador == "romano"
    tabela = next(b for b in cap.blocos if isinstance(b, m.Tabela))
    assert tabela.numero == 1 and [t.texto for t in tabela.legenda] == ["Resultados"]
    assert tabela.primeira_fila_cabecalho and tabela.largura_pct == 80
    assert [[m.texto_de(c.blocos[0]) for c in f] for f in tabela.filas] == [["Jogador", "Pontos"], ["A", "1"],
                                                                            ["B", "½"]]
    assert tabela.filas[0][1].alinhamento == "direita" and tabela.filas[0][0].cabecalho
    figuras = [b for b in cap.blocos if isinstance(b, m.Figura)]
    assert figuras[0].alt == "Uma foto" and figuras[0].numero == 1 and [t.texto for t in figuras[0].legenda] == ["A foto"]
    assert figuras[0].largura_pt == 120.0 and relido.recursos[figuras[0].recurso].dados[:8] == b"\x89PNG\r\n\x1a\n"
    assert figuras[1].alt == "Um desenho"                                # o SVG rasterizado volta como PNG
    citacao = next(b for b in cap.blocos if isinstance(b, m.Citacao))
    assert [m.texto_de(p) for p in citacao.blocos] == ["Citação um.", "Citação dois."]
    assert [n.tipo for n in cap.notas] == ["rodape", "fim"] and [len(n.blocos) for n in cap.notas] == [1, 2]
    assert m.texto_de(cap.notas[0].blocos[0]) == "Nota de rodapé com link."
    assert any(t.link == "https://example.org/n" for t in cap.notas[0].blocos[0].trechos)
    assert [t.nota for t in m.trechos_do_capitulo(cap) if t.nota] == [n.id for n in cap.notas]
    links = {t.texto: t for t in m.trechos_do_capitulo(cap) if t.link}
    assert links["externo"].link == "https://example.org/x"
    assert links["interno"].link.startswith("Text/cap-0002.xhtml#") and relido.capitulos[1].bloco(
        links["interno"].link.split("#")[1]) is not None
    assert links["Tabela 1"].ref == "tabela" and links["Tabela 1"].link == "#" + tabela.id
    assert links["Figura 1"].ref == "figura" and links["Figura 1"].link == "#" + figuras[0].id
    assert links["Diagrama 1"].ref == "diagrama" and links["Capítulo um"].ref == "titulo"
    assert links["Capítulo um"].link == "#" + cap.blocos[0].id and cap.blocos[0].id_persistente
    # o formato de página
    assert (relido.pagina.largura_mm, relido.pagina.altura_mm) == (140.0, 210.0)
    assert relido.pagina.margens_mm == (15.0, 12.0, 18.0, 20.0) and relido.pagina.espelhadas and relido.pagina.hifenizar
    assert [e.rotulo for e in relido.sumario] == ["Capítulo um", "Capítulo dois"]
    # e o livro relido grava um EPUB válido
    destino = str(tmp_path / "docx.epub")
    epub.escrever(relido, destino)
    assert epub.validar_estrutura(destino) == []


# ----------------------------------------------------------------------
# AC-ED09b-2 (AC-009)
# ----------------------------------------------------------------------

def test_ac2_o_fen_volta_igual_em_fonte_e_em_png_com_lado_desconhecido(tmp_path):
    for modo in ("fonte", "png"):
        livro, relido, _r = _ida_e_volta(tmp_path, modo_de_diagrama=modo)
        antes = [b for b in livro.capitulos[0].blocos if isinstance(b, m.Diagrama)]
        depois = [b for b in relido.capitulos[0].blocos if isinstance(b, m.Diagrama)]
        assert len(depois) == len(antes) == 4
        assert [d.fen for d in depois] == [FEN] * 4 and all(d.lado == "" for d in depois)
        assert all(d.estado == "ok" for d in depois)
        if modo == "png":
            assert all(d.modo == "png" for d in depois)
        else:
            # a SkakNew com coordenadas caiu para PNG na escrita (aviso da ED-09); as outras são tabela 1×1
            assert [d.modo for d in depois] == ["fonte", "fonte", "png", "fonte"]
            assert depois[3].fonte == "ChessMerida-Diagram" and depois[3].orientacao == "preta"
            assert depois[3].coordenadas and depois[0].fonte == "SkakNew-Diagram"
        primeiro = depois[0]
        assert primeiro.numero == 1 and [t.texto for t in primeiro.legenda] == ["Posição"]


# ----------------------------------------------------------------------
# AC-ED09b-3: um DOCX de fora
# ----------------------------------------------------------------------

_CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
</Types>"""
_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
_DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.org/fora" TargetMode="External"/>
</Relationships>"""
_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="MeuTitulo"><w:name w:val="Meu Título"/><w:basedOn w:val="Heading1"/></w:style>
<w:style w:type="paragraph" w:styleId="Esquisito"><w:name w:val="Esquisito"/></w:style>
<w:style w:type="character" w:styleId="Strong"><w:name w:val="Strong"/></w:style>
</w:styles>"""
_COMMENTS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:comment w:id="0" w:author="Revisor"><w:p><w:r><w:t>Conferir.</w:t></w:r></w:p></w:comment>
</w:comments>"""
_DOC = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:v="urn:schemas-microsoft-com:vml"
 xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">
<w:body>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Primeiro</w:t></w:r></w:p>
<w:p><w:r><w:t xml:space="preserve">Texto com </w:t></w:r><w:r><w:rPr><w:b/><w:highlight w:val="yellow"/></w:rPr><w:t>negrito realçado</w:t></w:r>
<w:commentRangeStart w:id="0"/><w:r><w:t xml:space="preserve"> e comentado</w:t></w:r><w:commentRangeEnd w:id="0"/>
<w:r><w:commentReference w:id="0"/></w:r><w:r><w:t>.</w:t></w:r></w:p>
<w:p><w:r><w:pict><v:shape><v:textbox><w:txbxContent><w:p><w:r><w:t>Dentro da caixa de texto.</w:t></w:r></w:p></w:txbxContent></v:textbox></v:shape></w:pict></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="MeuTitulo"/></w:pPr><w:r><w:t>Segundo</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Esquisito"/></w:pPr><w:r><w:t>Estilo que o dialeto não conhece</w:t></w:r><w:ins w:id="5" w:author="x"><w:r><w:t xml:space="preserve"> inserido</w:t></w:r></w:ins><w:del w:id="6" w:author="x"><w:r><w:delText>apagado</w:delText></w:r></w:del><w:r><w:t>.</w:t></w:r></w:p>
<w:p><w:hyperlink r:id="rId3"><w:r><w:rPr><w:rStyle w:val="Strong"/></w:rPr><w:t>um link</w:t></w:r></w:hyperlink><w:r><w:tab/><w:t>depois da tabulação</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Terceiro</w:t></w:r></w:p>
<w:p><w:r><w:t>Fim.</w:t></w:r><w:r><w:br w:type="page"/></w:r></w:p>
<w:tbl><w:tblPr/><w:tr><w:tc><w:p><w:r><w:t>a</w:t></w:r></w:p></w:tc><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>b</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:p><w:r><w:t>c</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>d</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>e</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1417" w:right="1134" w:bottom="1417" w:left="1701"/></w:sectPr>
</w:body></w:document>"""


def _docx_de_fora(caminho):
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/document.xml", _DOC)
        z.writestr("word/styles.xml", _STYLES)
        z.writestr("word/comments.xml", _COMMENTS)
    return caminho


def test_ac3_docx_de_fora_caixa_de_texto_e_comentario_com_avisos_e_tres_headings_viram_tres_capitulos(tmp_path):
    caminho = _docx_de_fora(str(tmp_path / "fora.docx"))
    livro, relatorio = docx_io.ler(caminho)
    assert [c.arquivo for c in livro.capitulos] == ["Text/cap-0001.xhtml", "Text/cap-0002.xhtml", "Text/cap-0003.xhtml"]
    um, dois, tres = livro.capitulos
    assert [m.texto_de(b) for b in um.blocos] == ["Primeiro", "Texto com negrito realçado e comentado.",
                                                  "Dentro da caixa de texto."]
    assert isinstance(um.blocos[0], m.Titulo) and um.blocos[0].nivel == 1
    realcado = next(t for t in um.blocos[1].trechos if t.texto == "negrito realçado")
    assert realcado.negrito and realcado.fundo == "#ffff00"
    assert isinstance(dois.blocos[0], m.Titulo) and m.texto_de(dois.blocos[0]) == "Segundo"    # basedOn Heading 1
    assert m.texto_de(dois.blocos[1]) == "Estilo que o dialeto não conhece inserido." and dois.blocos[1].estilo == "corpo"
    assert m.texto_de(dois.blocos[2]) == "um link\tdepois da tabulação"
    assert dois.blocos[2].trechos[0].link == "https://example.org/fora" and dois.blocos[2].trechos[0].negrito
    assert [type(b).__name__ for b in tres.blocos] == ["Titulo", "Paragrafo", "QuebraDePagina", "Tabela"]
    tabela = tres.blocos[3]
    assert [[m.texto_de(c.blocos[0]) if c.blocos else "" for c in f] for f in tabela.filas] == [["a", "b", ""],
                                                                                              ["c", "d", "e"]]
    avisos = "\n".join(relatorio.avisos)
    assert "caixa de texto: o texto foi preservado" in avisos and "comentários ignorados" in avisos
    assert sum(1 for a in relatorio.avisos if "caixa de texto" in a) == 1
    assert sum(1 for a in relatorio.avisos if "comentários ignorados" in a) == 1
    assert "estilo de parágrafo sem tradução: 'esquisito'" in avisos
    assert "inserções foram aceitas" in avisos and "exclusões foram descartadas" in avisos
    assert "célula mesclada" in avisos
    assert livro.metadados.titulo == "Primeiro" and livro.pagina.largura_mm == 210.0 and livro.pagina.altura_mm == 297.0
    assert livro.pagina.margens_mm == (25.0, 20.0, 25.0, 30.0)
    sem_dividir, _r = docx_io.ler(caminho, dividir_por_titulo=False)
    assert len(sem_dividir.capitulos) == 1 and len(sem_dividir.capitulos[0].blocos) == 10
    with pytest.raises(ValueError):
        docx_io.ler(str(tmp_path / "nao-existe.docx"))
    with open(str(tmp_path / "vazio.docx"), "wb") as f:
        f.write(b"nada")
    with pytest.raises(ValueError):
        docx_io.ler(str(tmp_path / "vazio.docx"))


def test_a_leitura_nao_precisa_do_python_docx(tmp_path, monkeypatch):
    import builtins

    caminho = _docx_de_fora(str(tmp_path / "fora.docx"))
    real = builtins.__import__

    def sem_docx(nome, *a, **k):
        if nome == "docx" or nome.startswith("docx."):
            raise ImportError("sem python-docx")
        return real(nome, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sem_docx)
    livro, _r = docx_leitura.ler(caminho)
    assert len(livro.capitulos) == 3


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
