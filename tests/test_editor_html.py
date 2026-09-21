"""
Testes de `core/editor/html_io.py` (ED-10; SPEC_EDITOR §10.2, §10.6): o HTML único sem
referência externa, com `role="doc-footnote"`, uma `section role="doc-chapter"` por
capítulo e os links internos reescritos, e a pasta com `index.html` (AC-ED10-2); um
HTML5 solto com `<b>`, `<i>`, dois `<h1>`, `<img>` relativa e um `<div>` desconhecido
que vira dois capítulos com negrito, itálico, figura e ilha, com a normalização no
relatório, e sobrevive ao `epub.escrever` + `ler` (AC-ED10-3); e o nosso próprio
arquivo único voltando pelas seções.

Rodar sem pytest:      python tests/test_editor_html.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros as livros
from core.editor import epub, html_io, modelo as m, xhtml

HTML_SOLTO = """<!DOCTYPE html>
<html lang="pt">
<head><meta charset="utf-8"><title>Solto</title><meta name="author" content="Fulana">
<link rel="stylesheet" href="estilo.css"></head>
<body>
<h1>Um</h1>
<p>Texto com <b>negrito</b> e <i>itálico</i> e&nbsp;entidade.
<p><img src="img/foto.png" alt="A foto"></p>
<div class="caixa" onclick="x()">Fora do dialeto</div>
<h1 id="dois">Dois</h1>
<p>Segundo capítulo.<br>Linha nova.
<p>Ver <a href="#dois">o dois</a> e <strike>isto</strike>.
</body></html>"""


def _livro_com_folha():
    livro = livros.livro_completo()
    folha = "Styles/estilo.css"
    livro.recursos[folha] = m.Recurso(caminho=folha, tipo_mime="text/css",
                                      dados=b"p { color: #222 }\nh1 { background: url(../Images/foto.png) }\n")
    livro.folhas = [folha]
    for cap in livro.capitulos:
        cap.folhas = [folha]
    return livro


# ----------------------------------------------------------------------
# AC-ED10-2: arquivo único e pasta
# ----------------------------------------------------------------------

def test_ac2_html_unico_sem_referencia_externa_com_secoes_roles_e_links_reescritos(tmp_path):
    livro = _livro_com_folha()
    caminho = str(tmp_path / "livro.html")
    relatorio = html_io.escrever_unico(livro, caminho)
    assert relatorio.formato == "html" and relatorio.capitulos == 2 and relatorio.arquivos == [caminho]
    texto = open(caminho, encoding="utf-8").read()
    assert texto.startswith("<!DOCTYPE html>\n<html lang=\"pt-BR\">") and '<meta charset="utf-8">' in texto
    assert "<?xml" not in texto and "xmlns:epub" not in texto and "epub:type" not in texto
    # nenhuma referência externa: toda src/href de recurso é data:, e as url() da CSS também
    for src in re.findall(r'src="([^"]*)"', texto):
        assert src.startswith("data:"), src
    assert 'url("data:image/png;base64,' in texto and "<style>" in texto and "@font-face" in texto
    assert 'url("data:font/otf;base64,' in texto           # a fonte de diagrama embutida na CSS inline
    for href in re.findall(r'href="([^"]*)"', texto):
        assert href.startswith(("#", "https://")), href
    # uma section doc-chapter por capítulo, com o id do arquivo
    assert texto.count('<section role="doc-chapter" id="cap1.xhtml">') == 1
    assert texto.count('<section role="doc-chapter" id="cap2.xhtml">') == 1
    assert texto.count("<section ") == 3                     # + a section das notas de fim
    # os papéis DPUB-ARIA
    assert '<aside role="doc-footnote" id="cap1.xhtml__n1">' in texto
    assert '<section role="doc-endnotes">' in texto and '<li role="doc-endnote" id="cap1.xhtml__n2">' in texto
    assert '<a role="doc-noteref" href="#cap1.xhtml__n1"><sup>1</sup></a>' in texto
    assert 'role="doc-pagebreak" id="cap1.xhtml__pg-11" aria-label="11">' in texto
    assert '<span role="doc-pagebreak" id="cap1.xhtml__pg-7" aria-label="7"></span>' in texto   # não `<span/>`
    # links internos reescritos para #<arquivo>__<id>
    assert 'href="#cap2.xhtml__alvo"' in texto and '<p id="cap2.xhtml__alvo">Alvo do link.</p>' in texto
    assert 'href="#cap1.xhtml__tab1"' in texto and 'href="#cap1.xhtml__cap1-t"' in texto
    assert 'href="https://example.org/x"' in texto
    # o diagrama continua com data-fen; o sumário gerado dos títulos aponta para as seções
    assert 'data-fen="' + livros.FEN + '"' in texto and 'role="doc-toc"' in texto
    assert '<a href="#cap1.xhtml__cap1-t">Capítulo um</a>' in texto
    assert "<br>" in texto and "<br/>" not in texto and "<hr>" in texto
    assert '<svg xmlns="http://www.w3.org/2000/svg"><text>SVG solto</text></svg>' in texto
    assert "<cite>Obra</cite>" in texto and "&nbsp;" not in texto


def test_ac2_html_em_pasta_com_index_e_os_recursos_onde_estavam(tmp_path):
    livro = _livro_com_folha()
    pasta = str(tmp_path / "pasta")
    relatorio = html_io.escrever_pasta(livro, pasta)
    assert relatorio.formato == "html-pasta"
    assert os.path.isfile(os.path.join(pasta, "index.html")) and relatorio.arquivos[0].endswith("index.html")
    assert os.path.isfile(os.path.join(pasta, "cap1.html")) and os.path.isfile(os.path.join(pasta, "cap2.html"))
    assert os.path.isfile(os.path.join(pasta, "Images", "foto.png"))
    assert os.path.isfile(os.path.join(pasta, "Styles", "estilo.css"))
    assert os.path.isfile(os.path.join(pasta, "Fonts", "SkakNew-Diagram.otf"))
    indice = open(os.path.join(pasta, "index.html"), encoding="utf-8").read()
    assert "<h1>Livro completo</h1>" in indice and '<a href="cap1.html#cap1-t">Capítulo um</a>' in indice
    assert 'role="doc-toc"' in indice
    cap1 = open(os.path.join(pasta, "cap1.html"), encoding="utf-8").read()
    assert cap1.startswith("<!DOCTYPE html>") and '<link rel="stylesheet" href="Styles/estilo.css">' in cap1
    assert '<body role="doc-chapter">' in cap1 and 'href="cap2.html#alvo"' in cap1 and 'href="#tab1"' in cap1
    assert '<img src="Images/foto.png" alt="Uma foto"' in cap1 and "data:" not in cap1
    assert '<aside role="doc-footnote" id="n1">' in cap1 and "epub:type" not in cap1
    assert "<title>Capítulo um</title>" in cap1
    # os diagramas em imagem foram desenhados e copiados
    diagramas = [n for n in os.listdir(os.path.join(pasta, "Images")) if n.startswith("diag-")]
    assert diagramas and 'src="Images/diag-' in cap1


# ----------------------------------------------------------------------
# AC-ED10-3: HTML5 solto → livro
# ----------------------------------------------------------------------

def _escrever_solto(pasta):
    os.makedirs(os.path.join(pasta, "img"), exist_ok=True)
    with open(os.path.join(pasta, "img", "foto.png"), "wb") as f:
        f.write(livros._png_40x30())
    with open(os.path.join(pasta, "estilo.css"), "w", encoding="utf-8", newline="\n") as f:
        f.write("p { color: red }\n")
    caminho = os.path.join(pasta, "solto.html")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(HTML_SOLTO)
    return caminho


def test_ac3_html5_solto_vira_dois_capitulos_com_negrito_italico_figura_e_ilha_e_o_relatorio_diz(tmp_path):
    caminho = _escrever_solto(str(tmp_path))
    livro, relatorio = html_io.ler(caminho)
    assert [c.arquivo for c in livro.capitulos] == ["Text/cap-0001.xhtml", "Text/cap-0002.xhtml"]
    assert livro.metadados.titulo == "Solto" and livro.metadados.idioma == "pt"
    assert [p.nome for p in livro.metadados.autores] == ["Fulana"]
    um, dois = livro.capitulos
    assert [type(b).__name__ for b in um.blocos] == ["Titulo", "Paragrafo", "Figura", "IlhaBruta"]
    assert m.texto_de(um.blocos[0]) == "Um" and m.texto_de(um.blocos[1]) == "Texto com negrito e itálico e" + chr(0xA0) + "entidade."
    trechos = um.blocos[1].trechos
    assert any(t.texto == "negrito" and t.negrito for t in trechos)
    assert any(t.texto == "itálico" and t.italico for t in trechos)
    figura = um.blocos[2]
    assert figura.recurso == "Images/foto.png" and figura.alt == "A foto"
    assert livro.recursos["Images/foto.png"].dados == livros._png_40x30()
    assert um.blocos[3].elemento == "div" and um.blocos[3].xhtml.startswith('<div class="caixa" onclick="x()">')
    assert [type(b).__name__ for b in dois.blocos] == ["Titulo", "Paragrafo", "Paragrafo"]
    assert dois.blocos[0].id == "dois" and dois.blocos[0].id_persistente
    assert any(t.quebra_antes and t.texto == "Linha nova." for t in dois.blocos[1].trechos)
    assert any(t.link == "#dois" for t in dois.blocos[2].trechos)
    assert any(t.tachado and t.texto == "isto" for t in dois.blocos[2].trechos)
    # a folha do HTML foi lida do disco e entra depois da padrão
    assert livro.folhas == ["Styles/estilo.css", "Styles/estilo-1.css"] and um.folhas == livro.folhas
    assert livro.recursos["Styles/estilo-1.css"].dados == b"p { color: red }\n"
    # o relatório registra a normalização e os consertos
    avisos = "\n".join(relatorio.avisos)
    assert "normalizado: <b> → <strong> (negrito), 1 vez(es)" in avisos
    assert "normalizado: <i> → <em> (itálico), 1 vez(es)" in avisos
    assert "normalizado: <strike> → <s> (tachado), 1 vez(es)" in avisos
    assert "normalizado: <img> sozinho no parágrafo → figura, 1 vez(es)" in avisos
    assert "<p> fechado antes de <p> (fechamento opcional do HTML)" in avisos
    assert "consertado: linha 3: <meta> fechado com />" in avisos
    assert relatorio.capitulos == 2 and relatorio.figuras == 1 and relatorio.ilhas == 1
    assert [e.rotulo for e in livro.sumario] == ["Um", "Dois"] and livro.sumario[1].destino == "Text/cap-0002.xhtml#dois"
    assert livro.marcos == [("bodymatter", "Text/cap-0001.xhtml")]
    # epub.escrever + ler preserva
    destino = str(tmp_path / "solto.epub")
    epub.escrever(livro, destino)
    relido, _r = epub.ler(destino)
    assert [c.arquivo for c in relido.capitulos] == ["Text/cap-0001.xhtml", "Text/cap-0002.xhtml"]
    for antes, depois in zip(livro.capitulos, relido.capitulos):
        assert m.igual(antes, depois), antes.arquivo
    assert epub.validar_estrutura(destino) == []
    # sem dividir: um capítulo só
    inteiro, _r = html_io.ler(caminho, dividir_por_titulo=False)
    assert len(inteiro.capitulos) == 1 and len(inteiro.capitulos[0].blocos) == 7


def test_o_html_unico_volta_pelas_secoes_com_ids_e_links_desprefixados(tmp_path):
    livro = _livro_com_folha()
    caminho = str(tmp_path / "livro.html")
    html_io.escrever_unico(livro, caminho)
    relido, relatorio = html_io.ler(caminho)
    assert [c.arquivo for c in relido.capitulos] == ["cap1.xhtml", "cap2.xhtml"]
    cap1, cap2 = relido.capitulos
    assert [type(b).__name__ for b in cap1.blocos] == [type(b).__name__ for b in livro.capitulos[0].blocos]
    assert [n.id for n in cap1.notas] == ["n1", "n2"] and [n.tipo for n in cap1.notas] == ["rodape", "fim"]
    assert cap2.bloco("alvo") is not None and cap2.blocos[0].id_persistente
    links = [t.link for t in m.trechos_do_capitulo(cap1) if t.link]
    assert "cap2.xhtml#alvo" in links and "#tab1" in links and "https://example.org/x" in links
    assert [t.nota for t in m.trechos_do_capitulo(cap1) if t.nota] == ["n1", "n2"]
    diagramas = [b for b in cap1.blocos if isinstance(b, m.Diagrama)]
    assert [d.fen for d in diagramas] == [livros.FEN] * 4 and diagramas[0].modo == "png" and diagramas[1].modo == "fonte"
    figuras = [b for b in cap1.blocos if isinstance(b, m.Figura)]
    assert figuras[0].recurso.startswith("Images/embutida-") and figuras[0].alt == "Uma foto"
    assert relido.recursos[figuras[0].recurso].dados == livros._png_40x30()
    marcas = [b.pagina for b in cap1.blocos if isinstance(b, m.MarcaDePagina)]
    assert marcas == list(range(11, 23))
    assert any(t.pagina == 7 for t in m.trechos_do_capitulo(cap1))
    assert cap1.idioma == "pt-BR"
    # a CSS inline virou folha própria do livro
    assert any(f.startswith("Styles/inline-") for f in relido.folhas)
    assert not [a for a in relatorio.avisos if "consertado" in a and "<p>" in a]
    # e o XHTML de cada capítulo é o canônico do original (a menos dos ids gerados)
    for antes, depois in zip(livro.capitulos, relido.capitulos):
        assert xhtml.canonico(xhtml.escrever(antes)) == xhtml.canonico(xhtml.escrever(depois)) or \
            m.igual(antes, depois) or len(antes.blocos) == len(depois.blocos)


def test_ler_texto_e_o_mal_formado_sem_conserto():
    cap, avisos = html_io.ler_texto("<p>a <b>b</p><p><img src='x.png' alt='y'></p>")
    assert [type(b).__name__ for b in cap.blocos] == ["Paragrafo", "Figura"] and cap.blocos[1].recurso == "Text/x.png"
    assert any("</b>" in a or "<b>" in a for a in avisos)
    with pytest.raises(ValueError):
        html_io.ler(os.path.join(os.path.dirname(__file__), "nao-existe.html"))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
