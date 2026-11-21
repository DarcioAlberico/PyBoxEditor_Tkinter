"""O sumário não perde entradas válidas (RG-09, R-27).

`destinos_quebrados` só conhecia ids de bloco do modelo: o `<h2 id>` dentro de uma ilha e
o `<a id>` inline viravam "quebrados", e toda âncora de capítulo em modo código também; a
entrada sem `href` (um rótulo de seção) saía com a subárvore inteira; e, se todas caíam,
o sumário era trocado pelo gerado dos títulos sem aviso.
"""

import zipfile

from core.editor import epub, modelo as m, sumario, xhtml
from core.editor.modelo import EntradaDeSumario


def _livro():
    livro = epub.novo_livro("Âncoras")
    cap = livro.capitulos[0]
    cap.blocos.append(m.IlhaBruta(xhtml='<h2 id="secao-ilha" class="x" data-y="1">Na ilha</h2>', elemento="h2"))
    cap.blocos.append(m.Paragrafo(trechos=[m.Trecho(texto="Antes "), m.Trecho(ilha='<a id="ancora-inline"></a>'),
                                           m.Trecho(texto="depois.")]))
    arquivo = cap.arquivo
    livro.sumario = [
        EntradaDeSumario(rotulo="Na ilha", destino=f"{arquivo}#secao-ilha"),
        EntradaDeSumario(rotulo="Inline", destino=f"{arquivo}#ancora-inline"),
        EntradaDeSumario(rotulo="Parte sem link", destino="", filhos=[
            EntradaDeSumario(rotulo="Filho", destino=arquivo)]),
    ]
    return livro


def _nav(caminho):
    with zipfile.ZipFile(caminho) as z:
        nome = next(n for n in z.namelist() if n.endswith("nav.xhtml"))
        return z.read(nome).decode("utf-8")


def test_ilha_ancora_inline_e_rotulo_saem_no_nav(tmp_path):
    livro = _livro()
    assert sumario.destinos_quebrados(livro) == []
    caminho = str(tmp_path / "a.epub")
    relatorio = epub.escrever(livro, caminho)
    assert not any("retirada" in a for a in relatorio.avisos), relatorio.avisos
    nav = _nav(caminho)
    assert "#secao-ilha" in nav and "#ancora-inline" in nav
    assert "<span>Parte sem link</span>" in nav, "a entrada sem destino sumiu do nav"
    lido, _ = epub.ler(caminho)
    assert [e.rotulo for e in lido.sumario] == ["Na ilha", "Inline", "Parte sem link"]
    assert [f.rotulo for f in lido.sumario[2].filhos] == ["Filho"]


def test_capitulo_em_modo_codigo_mantem_as_suas_ancoras(tmp_path):
    livro = _livro()
    cap = livro.capitulos[0]
    cap.texto_cru = xhtml.escrever(cap).replace("<body>", '<body><div id="so-no-codigo"></div>', 1)
    livro.sumario.append(EntradaDeSumario(rotulo="Do código", destino=f"{cap.arquivo}#so-no-codigo"))
    assert sumario.destinos_quebrados(livro) == []
    nav = _nav(_gravar(livro, tmp_path))
    assert "#so-no-codigo" in nav and "#secao-ilha" in nav


def test_destino_quebrado_vira_rotulo_com_os_filhos_e_avisa(tmp_path):
    livro = _livro()
    arquivo = livro.capitulos[0].arquivo
    livro.sumario = [EntradaDeSumario(rotulo="Some", destino=f"{arquivo}#nao-existe", filhos=[
        EntradaDeSumario(rotulo="Fica", destino=arquivo)])]
    caminho = str(tmp_path / "b.epub")
    relatorio = epub.escrever(livro, caminho)
    assert any("nao-existe" in a and "rótulo" in a for a in relatorio.avisos)
    nav = _nav(caminho)
    assert "<span>Some</span>" in nav and ">Fica</a>" in nav, "a subárvore saiu com a entrada quebrada"


def test_regenerar_o_sumario_avisa(tmp_path):
    livro = _livro()
    livro.sumario = []
    relatorio = epub.escrever(livro, str(tmp_path / "c.epub"))
    assert any("gerado dos títulos" in a for a in relatorio.avisos), "o sumário foi regenerado sem aviso"


def test_o_ncx_leva_o_rotulo_pelo_primeiro_destino_dos_filhos(tmp_path):
    livro = _livro()
    caminho = str(tmp_path / "d.epub")
    epub.escrever(livro, caminho, ncx=True)
    with zipfile.ZipFile(caminho) as z:
        ncx = z.read(next(n for n in z.namelist() if n.endswith(".ncx"))).decode("utf-8")
    assert "Parte sem link" in ncx and 'src=""' not in ncx


def _gravar(livro, tmp_path):
    caminho = str(tmp_path / "x.epub")
    epub.escrever(livro, caminho)
    return caminho
