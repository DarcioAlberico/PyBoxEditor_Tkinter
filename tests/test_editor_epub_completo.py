"""
Testes do EPUB completo (ED-10; SPEC_EDITOR §10.1): as fontes usadas copiadas com o
`@font-face` relativo à folha e o `ibooks:specified-fonts`; os metadados de
acessibilidade calculados do que o livro tem (`accessMode visual` só com imagem,
`accessModeSufficient textual` ausente com figura sem `alt`, `pageBreakMarkers` junto
da `page-list`, `structuralNavigation` ausente num livro só de "Página N"); o
`validar_estrutura` completo; e o `epubcheck` limpo (`slow`) — AC-ED10-1.

Rodar sem pytest:      python tests/test_editor_epub_completo.py
"""

import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros as livros
from core.editor import epub, fontes, modelo as m
from core.editor.conversao import RelatorioDeConversao

FEN = livros.FEN


def _entradas(caminho):
    with zipfile.ZipFile(caminho) as z:
        return {n: z.read(n) for n in z.namelist()}


def _livro_com_fonte_e_simbolo():
    livro = epub.novo_livro("Fontes", "Autora", "pt")
    cap = livro.capitulos[0]
    cap.blocos.append(m.Paragrafo(trechos=[m.Trecho(texto="Avaliação "), m.Trecho(texto="⩲", familia="simbolos")]))
    cap.blocos.append(m.Diagrama(fen=FEN, modo="fonte"))
    return livro


def test_ac1_diagrama_em_fonte_e_simbolo_embutem_duas_fontes_com_font_face_relativo(tmp_path):
    livro = _livro_com_fonte_e_simbolo()
    caminho = str(tmp_path / "fontes.epub")
    relatorio = epub.escrever(livro, caminho)
    assert relatorio.fontes_embutidas == ["Fonts/SkakNew-Diagram.otf", "Fonts/SimbolosDeXadrez.ttf"]
    entradas = _entradas(caminho)
    assert "OEBPS/Fonts/SkakNew-Diagram.otf" in entradas and "OEBPS/Fonts/SimbolosDeXadrez.ttf" in entradas
    assert entradas["OEBPS/Fonts/SkakNew-Diagram.otf"] == open(fontes.arquivo_da_fonte_de_diagrama("SkakNew-Diagram"),
                                                               "rb").read()
    css = entradas["OEBPS/Styles/estilo.css"].decode("utf-8")
    assert fontes.MARCA_DAS_FONTES in css and fontes.FIM_DAS_FONTES in css
    assert '@font-face { font-family: "SkakNew-Diagram";' in css and 'src: url("../Fonts/SkakNew-Diagram.otf")' in css
    assert 'div.diagrama.fonte-SkakNew-Diagram p { font-family: "SkakNew-Diagram", monospace; }' in css
    assert '@font-face { font-family: "Simbolos de Xadrez";' in css and 'url("../Fonts/SimbolosDeXadrez.ttf")' in css
    assert 'span.sim { font-family: "Simbolos de Xadrez", serif; }' in css
    opf = entradas["OEBPS/package.opf"].decode("utf-8")
    assert '<meta property="ibooks:specified-fonts">true</meta>' in opf and "ibooks: http://vocabulary.itunes" in opf
    assert 'href="Fonts/SkakNew-Diagram.otf" media-type="font/otf"' in opf
    assert 'href="Fonts/SimbolosDeXadrez.ttf" media-type="font/ttf"' in opf
    assert epub.validar_estrutura(caminho) == []
    # regravado: as fontes não entram duas vezes, o bloco é regenerado (não duplicado)
    relido, _r = epub.ler(caminho)
    caminho2 = str(tmp_path / "fontes-2.epub")
    epub.escrever(relido, caminho2)
    css2 = _entradas(caminho2)["OEBPS/Styles/estilo.css"].decode("utf-8")
    assert css2.count("@font-face") == 2 and css2.count(fontes.MARCA_DAS_FONTES) == 1
    assert sorted(n for n in _entradas(caminho2) if "/Fonts/" in n) == ["OEBPS/Fonts/SimbolosDeXadrez.ttf",
                                                                        "OEBPS/Fonts/SkakNew-Diagram.otf"]
    # sem símbolo nem diagrama em fonte, nada é embutido e o bloco sai da folha
    relido.capitulos[0].blocos = [b for b in relido.capitulos[0].blocos if not isinstance(b, m.Diagrama)]
    for t in m.trechos_do_capitulo(relido.capitulos[0]):
        if t.familia == "simbolos":
            t.texto, t.familia = "=", ""
    del relido.recursos["Fonts/SkakNew-Diagram.otf"], relido.recursos["Fonts/SimbolosDeXadrez.ttf"]
    caminho3 = str(tmp_path / "fontes-3.epub")
    relatorio3 = epub.escrever(relido, caminho3)
    assert relatorio3.fontes_embutidas == []
    css3 = _entradas(caminho3)["OEBPS/Styles/estilo.css"].decode("utf-8")
    assert "@font-face" not in css3 and fontes.MARCA_DAS_FONTES not in css3
    assert "ibooks" not in _entradas(caminho3)["OEBPS/package.opf"].decode("utf-8")


def test_a_fonte_de_simbolos_e_escolhida_pela_cobertura_e_o_epub_de_hoje_nao_a_declara_de_novo(tmp_path):
    familia, arquivo, cobertos = fontes.fonte_dos_simbolos("a ⩲ b ♙ ± c")
    assert familia == "Simbolos de Xadrez" and arquivo.endswith("SimbolosDeXadrez.ttf") and cobertos == "♙⩲"
    assert fontes.fonte_dos_simbolos("só letras e ±") is None
    assert fontes.familia_do_arquivo(arquivo) == "Simbolos de Xadrez"
    assert fontes.familia_do_arquivo(os.path.join(os.path.dirname(__file__), "editor_livros.py")) is None
    pontos = fontes.caracteres_dos_dados(open(arquivo, "rb").read())
    assert ord("⩲") in pontos and ord("♙") in pontos and ord("a") not in pontos
    # o EPUB de hoje em `fonte` já traz a SkakNew e a Simbolos declaradas em `estilo.css`: nada se repete
    caminho = livros.epub_de_hoje(str(tmp_path), "fonte")
    livro, _r = epub.ler(caminho)
    assert fontes.fontes_de_diagrama_usadas(livro) == ["SkakNew-Diagram", "ChessMerida-Diagram"]
    assert "SkakNew-Diagram" in fontes.familias_declaradas(livro, lambda r: epub.dados_de(livro, r).decode("utf-8"))
    assert fontes.pasta_de_fontes(livro) == "fonts"
    regravado = str(tmp_path / "hoje-regravado.epub")
    epub.escrever(livro, regravado)
    entradas = _entradas(regravado)
    css = entradas["OEBPS/estilo.css"].decode("utf-8")
    assert css.count('font-family: "SkakNew-Diagram"') == 2         # o @font-face e a regra, os de hoje
    assert fontes.MARCA_DAS_FONTES not in css
    assert sorted(n for n in entradas if n.startswith("OEBPS/fonts/")) == [
        "OEBPS/fonts/ChessMerida-Diagram.ttf", "OEBPS/fonts/SimbolosDeXadrez.ttf", "OEBPS/fonts/SkakNew-Diagram.otf"]
    assert not [n for n in entradas if "/Fonts/" in n]          # nada entrou numa segunda pasta


def test_ac1_os_metadados_de_acessibilidade_sao_calculados_do_que_o_livro_tem(tmp_path):
    # só texto: textual, sem visual, com structuralNavigation (há título de verdade)
    livro = epub.novo_livro("A11y", "", "pt")
    caminho = str(tmp_path / "a.epub")
    epub.escrever(livro, caminho)
    opf = _entradas(caminho)["OEBPS/package.opf"].decode("utf-8")
    assert '<meta property="schema:accessMode">textual</meta>' in opf
    assert '<meta property="schema:accessMode">visual</meta>' not in opf
    assert '<meta property="schema:accessModeSufficient">textual</meta>' in opf
    assert ">structuralNavigation<" in opf and ">pageBreakMarkers<" not in opf
    assert 'property="pageBreakSource"' not in opf
    # com figura sem alt e marcas de página: visual presente, sufficient ausente, page-list e pageBreakMarkers
    livro.recursos["Images/x.png"] = m.Recurso(caminho="Images/x.png", tipo_mime="image/png", dados=livros.PNG_MINIMO)
    cap = livro.capitulos[0]
    cap.blocos += [m.Figura(recurso="Images/x.png", alt=""), m.MarcaDePagina(pagina=3),
                   m.Paragrafo(trechos=[m.Trecho(texto="Página três.")])]
    livro.metadados.fonte_impressa = "urn:isbn:9780000000000"
    caminho2 = str(tmp_path / "b.epub")
    epub.escrever(livro, caminho2)
    entradas = _entradas(caminho2)
    opf = entradas["OEBPS/package.opf"].decode("utf-8")
    assert '<meta property="schema:accessMode">visual</meta>' in opf
    assert "schema:accessModeSufficient" not in opf and ">alternativeText<" not in opf
    assert ">pageBreakMarkers<" in opf and ">printPageNumbers<" in opf
    assert '<meta property="pageBreakSource">urn:isbn:9780000000000</meta>' in opf
    nav = entradas["OEBPS/nav.xhtml"].decode("utf-8")
    assert 'epub:type="page-list"' in nav and ">3</a>" in nav
    # um livro só de "Página N": sem structuralNavigation
    paginas = m.Livro(metadados=m.Metadados(titulo="Scan", idioma="pt", identificador="urn:uuid:scan"))
    for n in (1, 2):
        paginas.capitulos.append(m.Capitulo(arquivo=f"pagina-{n:04d}.xhtml", blocos=[
            m.Titulo(trechos=[m.Trecho(texto=f"Página {n}")], nivel=1),
            m.Paragrafo(trechos=[m.Trecho(texto="texto")])]))
    caminho3 = str(tmp_path / "c.epub")
    epub.escrever(paginas, caminho3)
    opf = _entradas(caminho3)["OEBPS/package.opf"].decode("utf-8")
    assert ">structuralNavigation<" not in opf and ">readingOrder<" in opf and ">tableOfContents<" in opf
    assert "accessibilityHazard\">none" in opf and "accessibilitySummary" in opf
    assert epub.validar_estrutura(caminho3) == []


def test_validar_estrutura_completo_aponta_o_que_o_epubcheck_apontaria(tmp_path):
    livro = epub.novo_livro("Estrutura", "", "pt")
    caminho = str(tmp_path / "ok.epub")
    epub.escrever(livro, caminho)
    assert epub.validar_estrutura(caminho) == []
    entradas = _entradas(caminho)
    opf = entradas["OEBPS/package.opf"].decode("utf-8")
    # href repetido no manifesto, item repetido na espinha, duas capas, entidade nomeada, CSS quebrada
    opf_ruim = opf.replace('<item id="ncx"', '<item id="dup" href="Text/cap-0001.xhtml" '
                           'media-type="application/xhtml+xml" properties="cover-image"/>'
                           '<item id="dup2" href="Styles/estilo.css" media-type="text/css" properties="cover-image"/>'
                           '<item id="ncx"')
    opf_ruim = opf_ruim.replace("</spine>", '<itemref idref="cap-0001.xhtml"/><itemref idref="dup2"/></spine>')
    xhtml_ruim = entradas["OEBPS/Text/cap-0001.xhtml"].replace(b"</h1>", b"&nbsp;</h1>")
    ruim = str(tmp_path / "ruim.epub")
    with zipfile.ZipFile(ruim, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), epub.MIME_EPUB, compress_type=zipfile.ZIP_STORED)
        for nome, dados in entradas.items():
            if nome == "mimetype":
                continue
            if nome == "OEBPS/package.opf":
                dados = opf_ruim.encode("utf-8")
            elif nome == "OEBPS/Text/cap-0001.xhtml":
                dados = xhtml_ruim
            elif nome == "OEBPS/Styles/estilo.css":
                dados = b"p { color: red "
            z.writestr(nome, dados)
    problemas = epub.validar_estrutura(ruim)
    texto = "\n".join(problemas)
    assert "manifesto com href repetido: Text/cap-0001.xhtml" in texto
    assert "espinha repete o item cap-0001.xhtml" in texto
    assert "2 itens com properties=\"cover-image\"" in texto
    assert "cap-0001.xhtml: entidade nomeada" in texto
    assert "espinha com item que não é XHTML: Styles/estilo.css" in texto
    assert "estilo.css: CSS com problema" in texto
    # nav sem toc e sem nav
    sem_nav = str(tmp_path / "sem-nav.epub")
    with zipfile.ZipFile(sem_nav, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), epub.MIME_EPUB, compress_type=zipfile.ZIP_STORED)
        for nome, dados in entradas.items():
            if nome == "mimetype":
                continue
            if nome == "OEBPS/nav.xhtml":
                dados = dados.replace(b'epub:type="toc"', b'epub:type="landmarks"')
            z.writestr(nome, dados)
    assert any("nav sem <nav epub:type=\"toc\">" in p for p in epub.validar_estrutura(sem_nav))


@pytest.mark.slow
def test_ac1_o_livro_com_fontes_e_marcas_passa_no_epubcheck(tmp_path):
    livro = _livro_com_fonte_e_simbolo()
    cap = livro.capitulos[0]
    cap.blocos += [m.MarcaDePagina(pagina=3), m.Paragrafo(trechos=[m.Trecho(texto="Página três.")])]
    livro.metadados.fonte_impressa = "urn:isbn:9780000000000"
    caminho = str(tmp_path / "fontes.epub")
    epub.escrever(livro, caminho)
    resultado = epub.epubcheck(caminho)
    if resultado is None:
        pytest.skip("epubcheck não instalado")
    passou, saida = resultado
    assert passou, saida


def test_relatorio_lista_as_fontes_embutidas():
    livro = _livro_com_fonte_e_simbolo()
    relatorio = RelatorioDeConversao(formato="epub")
    novas, avisos = fontes.embutir(livro)
    assert novas == ["Fonts/SkakNew-Diagram.otf", "Fonts/SimbolosDeXadrez.ttf"] and avisos == []
    relatorio.fontes_embutidas = epub.fontes_embutidas(livro)
    assert "Fontes embutidas: Fonts/SkakNew-Diagram.otf, Fonts/SimbolosDeXadrez.ttf" in relatorio.resumo()
    # de novo: nada entra, o bloco continua um só
    assert fontes.embutir(livro) == ([], [])
    css = livro.recursos["Styles/estilo.css"].dados.decode("utf-8")
    assert css.count(fontes.MARCA_DAS_FONTES) == 1 and css.count("@font-face") == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
