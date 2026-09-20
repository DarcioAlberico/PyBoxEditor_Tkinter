"""
Testes de `core/editor/epub.py` (ED-01; SPEC_EDITOR §10.1, DEC-01, DEC-08): a ida e
volta do EPUB de hoje sem perda (AC-ED01-1), um EPUB de fora com tudo que não é
dialeto sobrevivendo (AC-ED01-2), o `mimetype` e o UTF-8 sem BOM (AC-ED01-3), a
recusa do XHTML mal-formado sem tocar o arquivo (AC-ED01-4), a gravação atômica
(AC-ED01-7), o livro novo, os `pybox:*`, o PNG reutilizado e o `epubcheck`.

Rodar sem pytest:      python tests/test_editor_epub.py
"""

import hashlib
import os
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros as livros
from core.editor import epub, modelo as m, xhtml
from core.editor.xhtml import ErroDeXhtml


def _sha(caminho):
    with open(caminho, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _entradas(caminho):
    with zipfile.ZipFile(caminho) as z:
        return {n: z.read(n) for n in z.namelist()}


def _epubcheck_limpo(caminho):
    resultado = epub.epubcheck(caminho)
    if resultado is None:
        pytest.skip("epubcheck não instalado")
    passou, saida = resultado
    assert passou, saida


# ----------------------------------------------------------------------
# AC-ED01-1: o EPUB de hoje, ida e volta
# ----------------------------------------------------------------------

@pytest.mark.parametrize("modo", ["png", "fonte"])
def test_ac1_o_epub_de_hoje_volta_com_os_mesmos_capitulos_recursos_e_nomes(tmp_path, modo):
    original = livros.epub_de_hoje(str(tmp_path), modo)
    livro, relatorio = epub.ler(original)
    assert relatorio.formato == "epub" and relatorio.capitulos == 2 and not relatorio.avisos
    assert livro.opf == "OEBPS/content.opf" and livro.nav == "nav.xhtml" and livro.ncx == ""
    assert [c.arquivo for c in livro.capitulos] == ["pagina-0001.xhtml", "pagina-0002.xhtml"]
    assert livro.metadados.titulo == "Livro de hoje" and livro.metadados.autores[0].nome == "Autora"
    assert livro.metadados.idioma == "en" and livro.metadados.identificador.startswith("urn:uuid:")
    assert livro.folhas == ["estilo.css"] and livro.capitulos[0].folhas == ["estilo.css"]

    regravado = str(tmp_path / f"regravado-{modo}.epub")
    relatorio2 = epub.escrever(livro, regravado)
    assert not relatorio2.avisos, relatorio2.avisos
    antes, depois = _entradas(original), _entradas(regravado)
    assert set(antes) == set(depois)                      # os nomes de entrada, OPF e nav no lugar
    regenerados = {"META-INF/container.xml", "OEBPS/content.opf", "OEBPS/nav.xhtml",
                   "OEBPS/pagina-0001.xhtml", "OEBPS/pagina-0002.xhtml"}
    for nome in antes:
        if nome not in regenerados:
            assert antes[nome] == depois[nome], nome            # recursos byte a byte
    relido, _ = epub.ler(regravado)
    for c1, c2 in zip(livro.capitulos, relido.capitulos):
        assert m.igual(c1, c2), c1.arquivo
    assert relido.metadados.titulo == livro.metadados.titulo
    assert relido.metadados.identificador == livro.metadados.identificador
    assert [p.nome for p in relido.metadados.autores] == ["Autora"]
    assert epub.validar_estrutura(regravado) == []
    _epubcheck_limpo(regravado)


def test_o_png_do_diagrama_de_hoje_e_reutilizado_e_so_o_diagrama_mudado_e_redesenhado(tmp_path):
    original = livros.epub_de_hoje(str(tmp_path), "png")
    livro, _ = epub.ler(original)
    diagramas = [b for c in livro.capitulos for b in c.blocos if isinstance(b, m.Diagrama)]
    assert len(diagramas) == 3
    assert [d.imagem for d in diagramas] == ["imagens/fig-0001-1.png", "imagens/fig-0001-2.png",
                                             "imagens/fig-0002-1.png"]
    assert all(d.imagem_chave and d.estado == "revisar" for d in diagramas)
    regravado = str(tmp_path / "r1.epub")
    epub.escrever(livro, regravado)
    assert not [n for n in _entradas(regravado) if "diag-" in n]      # nada foi redesenhado
    # Confirmar a orientação muda a chave: só esse diagrama ganha um PNG novo, na pasta do livro.
    diagramas[1].orientacao = "preta"
    regravado2 = str(tmp_path / "r2.epub")
    relatorio = epub.escrever(livro, regravado2)
    novos = [n for n in _entradas(regravado2) if "diag-" in n]
    assert len(novos) == 1 and novos[0].startswith("OEBPS/imagens/diag-"), novos
    assert not relatorio.avisos
    relido, _ = epub.ler(regravado2)
    d = [b for b in relido.capitulos[0].blocos if isinstance(b, m.Diagrama)][1]
    assert d.orientacao == "preta" and d.imagem == "" and d.modo == "png"
    xhtml_texto = _entradas(regravado2)["OEBPS/pagina-0001.xhtml"].decode("utf-8")
    assert 'style="width: ' in xhtml_texto          # a largura em pontos, como no EPUB de hoje


# ----------------------------------------------------------------------
# AC-ED01-2: um EPUB de fora
# ----------------------------------------------------------------------

def test_ac2_o_epub_de_fora_abre_e_o_que_nao_e_dialeto_sobrevive(tmp_path):
    caminho = livros.epub_de_fora(str(tmp_path))
    livro, relatorio = epub.ler(caminho)
    assert livro.opf == "OEBPS/content.opf" and livro.ncx == "toc.ncx"
    assert [c.arquivo for c in livro.capitulos] == ["Text/capa.xhtml", "Text/cap 1.xhtml", "Text/cap2.xhtml",
                                                    "Text/notas.xhtml"]
    assert [c.linear for c in livro.capitulos] == [False, True, True, False]
    capa, cap1, cap2, notas = livro.capitulos
    assert notas.notas and notas.notas[0].id == "n1"
    assert cap1.folhas == ["Styles/a.css", "Styles/b.css"] and cap2.folhas == ["Styles/b.css", "Styles/a.css"]
    assert cap1.blocos[0].id == "title" and cap2.blocos[0].id == "title"       # o mesmo id em dois capítulos
    assert m.texto_de(cap1.blocos[0]) == "Capítulo\u00a0um"
    ilhas = [b for b in cap1.blocos if isinstance(b, m.IlhaBruta)]
    assert len(ilhas) == 1 and ilhas[0].xhtml == ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
                                                  '<text x="1" y="1">a&#160;b</text></svg>')
    trechos = cap1.blocos[1].trechos
    assert any(t.ilha.startswith("<cite>") for t in trechos) and any(t.negrito for t in trechos)
    assert any(t.link == "Text/cap2.xhtml#title" for t in trechos)
    assert any(t.link == "Text/cap 1.xhtml#title" for t in cap2.blocos[1].trechos)      # `%20` decodificado
    figura = [b for b in cap1.blocos if isinstance(b, m.Figura)][0]
    assert figura.recurso == "Images/fig.png"
    assert set(livro.recursos) >= {"Styles/a.css", "Styles/b.css", "Images/fig.png", "Images/capa.png",
                                   "sobra.txt", "../META-INF/com.apple.ibooks.display-options.xml"}
    assert livro.recursos["sobra.txt"].no_manifesto is False
    assert livro.recursos["../META-INF/com.apple.ibooks.display-options.xml"].no_manifesto is False
    assert livro.recursos["Images/capa.png"].propriedades == ""      # `cover-image` vem de `capa`
    assert livro.metadados.capa == "Images/capa.png"
    md = livro.metadados
    assert md.titulo == "Livro de Fora" and md.ids["titulo"] == "title"
    assert md.identificador == "urn:uuid:11111111-2222-3333-4444-555555555555" and md.ids["identificador"] == "BookId"
    assert md.idioma == "pt-BR" and md.editora == "Editora X" and md.data == "2020-01-02"
    assert md.descricao == "Uma descrição & tal." and md.direitos == "© 2020" and md.assuntos == ["Xadrez"]
    assert md.autores == [m.Pessoa(nome="Ana Silva", papel="aut", file_as="Silva, Ana", id="creator01")]
    assert md.colaboradores == [m.Pessoa(nome="Bruno Costa", papel="edt", id="ed1")]
    assert md.colecao == ("Série Y", 3) and md.ids["colecao"] == "c01"
    assert md.fonte_impressa == "urn:isbn:9780000000000" and md.modificado == "2020-01-02T03:04:05Z"
    assert md.prefixos == {"calibre": "https://calibre-ebook.com"}
    extras = {(el, at) for el, at, _v in md.extras}
    assert ("dc:identifier", 'id="isbn"') in extras
    assert ("dc:title", 'id="sub"') in extras
    assert ("meta", 'refines="#title" property="title-type"') in extras
    assert ("meta", 'refines="#creator01" property="display-seq"') in extras
    assert ("meta", 'refines="#c01" property="collection-type"') in extras
    assert ("meta", 'property="calibre:series"') in extras
    assert ("meta", 'name="calibre:series_index" content="3"') in extras
    assert not [e for e in md.extras if "schema:" in e[1] or "role" in e[1] or "file-as" in e[1]]
    assert [e.rotulo for e in livro.sumario] == ["Capítulo um", "Capítulo dois"]        # do NCX, sem nav
    assert livro.sumario[0].destino == "Text/cap 1.xhtml#title"
    assert ("cover", "Text/capa.xhtml") in livro.marcos and ("bodymatter", "Text/cap 1.xhtml") in livro.marcos
    assert any("sobra.txt" in a for a in relatorio.avisos)
    assert livro.nav == "nav.xhtml"                                       # será criado ao salvar

    regravado = str(tmp_path / "de-fora-regravado.epub")
    relatorio2 = epub.escrever(livro, regravado)
    assert not [a for a in relatorio2.avisos if "prefixo" in a], relatorio2.avisos
    entradas = _entradas(regravado)
    assert "OEBPS/nav.xhtml" in entradas and "OEBPS/toc.ncx" in entradas
    assert entradas["OEBPS/Styles/a.css"] == livros.CSS_A_DE_FORA.encode("utf-8")      # o `@media`, byte a byte
    assert entradas["OEBPS/sobra.txt"] == b"esquecido"
    assert entradas["META-INF/com.apple.ibooks.display-options.xml"] == livros.DISPLAY_OPTIONS_DE_FORA.encode("utf-8")
    assert '<aside epub:type="footnote" role="doc-footnote" id="n1">' in entradas["OEBPS/Text/notas.xhtml"].decode("utf-8")
    cap1_texto = entradas["OEBPS/Text/cap 1.xhtml"].decode("utf-8")
    assert "a&#160;b" in cap1_texto and "&nbsp;" not in cap1_texto and "<cite>uma citação</cite>" in cap1_texto
    assert 'href="cap2.xhtml#title"' in cap1_texto
    assert '<a epub:type="noteref" href="notas.xhtml#n1">1</a>' in cap1_texto      # ilha: nota noutro arquivo
    assert 'href="cap%201.xhtml#title"' in entradas["OEBPS/Text/cap2.xhtml"].decode("utf-8")
    opf = entradas["OEBPS/content.opf"].decode("utf-8")
    assert 'unique-identifier="BookId"' in opf and '<dc:identifier id="BookId">' in opf
    assert '<dc:title id="title">Livro de Fora</dc:title>' in opf
    assert '<meta refines="#title" property="title-type">main</meta>' in opf
    assert '<dc:identifier id="isbn">urn:isbn:9780000000000</dc:identifier>' in opf
    assert '<dc:creator id="creator01">Ana Silva</dc:creator>' in opf
    assert '<meta refines="#creator01" property="file-as">Silva, Ana</meta>' in opf
    assert '<dc:contributor id="ed1">Bruno Costa</dc:contributor>' in opf
    assert '<meta refines="#ed1" property="role" scheme="marc:relators">edt</meta>' in opf
    assert '<meta property="belongs-to-collection" id="c01">Série Y</meta>' in opf
    assert '<meta refines="#c01" property="group-position">3</meta>' in opf
    assert 'prefix="' in opf and "calibre: https://calibre-ebook.com" in opf
    assert '<meta property="calibre:series">Série Y</meta>' in opf
    assert opf.count("schema:accessMode") >= 1 and "displayTransformability" not in opf
    assert 'href="Text/cap%201.xhtml"' in opf and 'properties="cover-image"' in opf
    assert '<meta name="cover" content="' in opf and 'linear="no"' in opf and '<spine toc="ncx">' in opf
    assert '<reference type="cover"' in opf
    assert 'href="Text/cap%201.xhtml#title"' in entradas["OEBPS/nav.xhtml"].decode("utf-8")
    relido, _ = epub.ler(regravado)
    assert [c.arquivo for c in relido.capitulos] == [c.arquivo for c in livro.capitulos]
    assert [c.linear for c in relido.capitulos] == [False, True, True, False]
    for c1, c2 in zip(livro.capitulos, relido.capitulos):
        assert m.igual(c1, c2), c1.arquivo
    assert relido.metadados.extras == md.extras and relido.metadados.ids == md.ids
    assert relido.metadados.autores == md.autores and relido.metadados.colecao == md.colecao
    assert epub.validar_estrutura(regravado) == []
    _epubcheck_limpo(regravado)


# ----------------------------------------------------------------------
# AC-ED01-3, AC-ED01-4, AC-ED01-7
# ----------------------------------------------------------------------

def test_ac3_mimetype_primeiro_e_sem_compressao_e_xhtml_utf8_sem_bom(tmp_path):
    caminho = str(tmp_path / "novo.epub")
    livro = epub.novo_livro("Título com acento", "Autor", "pt")
    livro.capitulos[0].blocos.append(m.Paragrafo(trechos=[m.Trecho(texto="Ação ♕ e «aspas».")]))
    epub.escrever(livro, caminho)
    with zipfile.ZipFile(caminho) as z:
        infos = z.infolist()
        assert infos[0].filename == "mimetype" and infos[0].compress_type == zipfile.ZIP_STORED
        assert z.read("mimetype") == b"application/epub+zip"
        for nome in z.namelist():
            if nome.endswith((".xhtml", ".opf", ".ncx", ".css", ".xml")):
                dados = z.read(nome)
                assert not dados.startswith(b"\xef\xbb\xbf"), nome
                dados.decode("utf-8")
        assert "Ação ♕ e «aspas»." in z.read("OEBPS/Text/cap-0001.xhtml").decode("utf-8")
    with open(caminho, "rb") as f:
        assert f.read(64).find(b"mimetypeapplication/epub+zip") == 30
    assert epub.validar_estrutura(caminho) == []


def test_ac4_capitulo_em_codigo_mal_formado_e_recusado_sem_tocar_o_arquivo(tmp_path):
    caminho = str(tmp_path / "livro.epub")
    livro = epub.novo_livro("L", "", "pt")
    epub.escrever(livro, caminho)
    antes = _sha(caminho)
    livro.capitulos.append(m.Capitulo(arquivo="Text/quebrado.xhtml", texto_cru="<p>aberto"))
    with pytest.raises(ErroDeXhtml) as erro:
        epub.escrever(livro, caminho)
    assert "Text/quebrado.xhtml" in str(erro.value) and erro.value.linha == 1
    assert _sha(caminho) == antes
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
    # CSS não é XML: aviso, e grava.
    livro.capitulos.pop()
    livro.recursos["Styles/estilo.css"].texto_cru = "p{"
    relatorio = epub.escrever(livro, caminho)
    assert any("Styles/estilo.css" in a for a in relatorio.avisos)
    assert _entradas(caminho)["OEBPS/Styles/estilo.css"] == b"p{"


def test_ac7_excecao_no_meio_da_gravacao_deixa_o_original_intacto(tmp_path, monkeypatch):
    caminho = str(tmp_path / "livro.epub")
    livro = epub.novo_livro("L", "", "pt")
    epub.escrever(livro, caminho)
    antes = _sha(caminho)
    monkeypatch.setattr(zipfile.ZipFile, "testzip", lambda self: "OEBPS/package.opf")
    with pytest.raises(zipfile.BadZipFile):
        epub.escrever(livro, caminho)
    assert _sha(caminho) == antes
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
    monkeypatch.undo()
    monkeypatch.setattr(epub.sumario, "escrever_nav", lambda *a, **k: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        epub.escrever(livro, caminho)
    assert _sha(caminho) == antes


# ----------------------------------------------------------------------
# Livro novo, pybox, sob demanda, validação
# ----------------------------------------------------------------------

def test_o_livro_novo_vai_e_volta_e_passa_no_epubcheck(tmp_path):
    livro = epub.novo_livro("Meu livro", "Eu", "pt")
    assert livro.opf == "OEBPS/package.opf" and livro.capitulos[0].arquivo == "Text/cap-0001.xhtml"
    assert livro.folhas == ["Styles/estilo.css"] and livro.ncx == "toc.ncx"
    livro.origem.documento_editorial = "C:/livros/x.json"
    livro.origem.pdf = "C:/livros/x.pdf"
    livro.pagina.hifenizar = True
    livro.pagina.largura_mm = 140.0
    caminho = str(tmp_path / "novo.epub")
    relatorio = epub.escrever(livro, caminho)
    assert relatorio.capitulos == 1 and not relatorio.avisos
    relido, _ = epub.ler(caminho)
    assert m.igual(relido.capitulos[0], livro.capitulos[0])
    assert relido.origem.documento_editorial == "C:/livros/x.json" and relido.origem.pdf == "C:/livros/x.pdf"
    assert relido.pagina.hifenizar is True and relido.pagina.largura_mm == 140.0
    assert relido.metadados.identificador == livro.metadados.identificador
    assert relido.sumario[0].destino.startswith("Text/cap-0001.xhtml#")
    assert relido.marcos == [("bodymatter", "Text/cap-0001.xhtml")]
    opf = _entradas(caminho)["OEBPS/package.opf"].decode("utf-8")
    assert "pybox: urn:pyboxeditor:vocabulario" in opf and '<meta property="pybox:pdf">' in opf
    assert epub.validar_estrutura(caminho) == []
    _epubcheck_limpo(caminho)


def test_recursos_sao_lidos_sob_demanda_e_soltos_depois_de_gravar(tmp_path):
    original = livros.epub_de_hoje(str(tmp_path), "png")
    livro, _ = epub.ler(original)
    recurso = livro.recursos["imagens/fig-0001-1.png"]
    assert recurso.dados is None and livro.zip_de_origem == original
    dados = epub.dados_de(livro, recurso)
    assert dados.startswith(b"\x89PNG") and recurso.dados is dados
    novo = str(tmp_path / "novo.epub")
    epub.escrever(livro, novo)
    assert livro.zip_de_origem == novo
    assert all(r.dados is not None for r in livro.recursos.values())
    assert epub.descarregar(livro) == len(livro.recursos)
    assert all(r.dados is None for r in livro.recursos.values())
    os.unlink(original)
    assert epub.dados_de(livro, recurso) == dados          # agora vem do novo
    livro.recursos["x.bin"] = m.Recurso(caminho="x.bin", tipo_mime="application/octet-stream")
    with pytest.raises(FileNotFoundError):
        epub.dados_de(livro, livro.recursos["x.bin"])


def test_validar_estrutura_aponta_o_que_esta_errado(tmp_path):
    caminho = str(tmp_path / "ruim.epub")
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="x.opf" media-type="application/oebps-package+xml"/>'
                   "</rootfiles></container>")
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("x.opf", '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="u">'
                   '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>T</dc:title></metadata>'
                   '<manifest><item id="c" href="c.xhtml" media-type="application/xhtml+xml"/></manifest>'
                   '<spine><itemref idref="c"/><itemref idref="z"/></spine></package>')
        z.writestr("c.xhtml", "\ufeff<html><p>aberto</html>")
    problemas = epub.validar_estrutura(caminho)
    texto = "\n".join(problemas)
    assert "mimetype não é a primeira" in texto and "dc:identifier" in texto and "dc:language" in texto
    assert "BOM" in texto and "c.xhtml: linha" in texto and "id inexistente: z" in texto and "nav" in texto
    with pytest.raises(epub.ErroDeEpub):
        epub.ler(str(tmp_path / "nao-existe.epub"))


def test_capitulo_mal_formado_abre_em_modo_codigo_e_nao_derruba_o_livro(tmp_path):
    caminho = str(tmp_path / "quebrado.epub")
    livro = epub.novo_livro("L", "", "pt")
    epub.escrever(livro, caminho)
    with zipfile.ZipFile(caminho) as z:
        entradas = {n: z.read(n) for n in z.namelist()}
    entradas["OEBPS/Text/cap-0001.xhtml"] = b"<html><body><p>aberto</body></html>"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), entradas.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
        for nome, dados in entradas.items():
            z.writestr(nome, dados)
    relido, relatorio = epub.ler(caminho)
    cap = relido.capitulos[0]
    assert cap.texto_cru == "<html><body><p>aberto</body></html>" and cap.blocos == []
    assert any("mal-formado" in a for a in relatorio.avisos) and cap.avisos
    with pytest.raises(ErroDeXhtml):
        epub.escrever(relido, str(tmp_path / "x.epub"))


def test_importar_epub_livro_ops_e_projeto_nao_traz_fitz_numpy_cv2_pil_nem_tkinter():
    codigo = ("import sys; import core.editor.epub, core.editor.livro_ops, core.editor.projeto; "
              "print(sorted(m for m in ('fitz', 'numpy', 'cv2', 'PIL', 'tkinter', 'docx') if m in sys.modules))")
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                           cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), timeout=120)
    assert saida.returncode == 0, saida.stderr
    assert saida.stdout.strip() == "[]", saida.stdout


def test_o_xhtml_escrito_com_espaco_no_nome_codifica_o_href_e_o_leitor_decodifica():
    cap = m.Capitulo(arquivo="Text/cap 1.xhtml", blocos=[
        m.Paragrafo(trechos=[m.Trecho(texto="x", link="Text/cap 2.xhtml#a")]),
        m.Figura(recurso="Images/foto 1.png", alt="f")])
    texto = xhtml.escrever(cap)
    assert 'href="cap%202.xhtml#a"' in texto and 'src="../Images/foto%201.png"' in texto
    relido = xhtml.ler(texto, cap.arquivo)
    assert relido.blocos[0].trechos[0].link == "Text/cap 2.xhtml#a" and relido.blocos[1].recurso == "Images/foto 1.png"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
