"""Ida e volta sem perda silenciosa: os atributos de dentro dos blocos (RG-10, R-26).

O leitor aceitava e descartava `id` e `class` de `li`, `tr`, `td`, `th`, os do `img` da
figura, os do `body` e do `html`, e o `media` do `<link>`: `<li id="fn1">` voltava `<li>`, e o
link `#fn1` quebrava. Agora eles vão para os `extras` do elemento e voltam na gravação.
"""

import zipfile

from core.editor import epub, sumario, xhtml
from core.editor.modelo import EntradaDeSumario, Recurso

_XHTML = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="pt" xml:lang="pt" dir="ltr" data-versao="2">
<head>
<title>Atributos</title>
<link rel="stylesheet" type="text/css" href="../Styles/estilo.css" media="screen"/>
</head>
<body class="capitulo par" dir="ltr" lang="pt" id="corpo">
<h1>Atributos</h1>
<ol>
  <li id="fn1" class="nota" lang="en" dir="ltr">Primeira nota.</li>
  <li>Segunda.</li>
</ol>
<table>
  <tbody>
    <tr id="linha-1" class="par"><td id="c11" class="num" lang="en">1</td><td>2</td></tr>
    <tr><th class="cab" dir="rtl">3</th><td>4</td></tr>
  </tbody>
</table>
<figure><img src="../Images/a.png" alt="Uma imagem" id="img-a" class="foto" title="Legenda do title"/></figure>
<p>Veja a <a href="#fn1">nota 1</a>.</p>
</body>
</html>
"""


def _ida_e_volta():
    cap = xhtml.ler(_XHTML, "Text/c.xhtml")
    texto = xhtml.escrever(cap)
    return cap, texto, xhtml.ler(texto, "Text/c.xhtml")


def test_li_tr_td_th_img_body_html_e_link_voltam_com_os_atributos():
    cap, texto, volta = _ida_e_volta()
    # `id`, `class`, `lang` e `dir` são do dialeto: a lista e a tabela continuam editáveis,
    # e não viram ilha (que voltaria byte a byte, mas sem deixar editar).
    assert [type(b).__name__ for b in cap.blocos] == ["Titulo", "Lista", "Tabela", "Figura", "Paragrafo"]
    for trecho in ('<li id="fn1" class="nota" lang="en" dir="ltr">', '<tr id="linha-1" class="par">',
                   '<td id="c11" class="num" lang="en">', '<th class="cab" dir="rtl">',
                   'id="img-a"', 'class="foto"', 'title="Legenda do title"',
                   'class="capitulo par"', 'id="corpo"', 'data-versao="2"', 'media="screen"'):
        assert trecho in texto, f"perdeu {trecho}"
    assert 'dir="ltr"' in texto.split("<head>")[0], "o dir do <html> se perdeu"
    # E a segunda volta é igual à primeira: nada se acumula nem se perde.
    assert xhtml.escrever(volta) == texto


def test_o_link_para_o_id_do_li_nao_quebra(tmp_path):
    livro = epub.novo_livro("Notas")
    cap = xhtml.ler(_XHTML, "Text/c.xhtml")
    cap.folhas = list(livro.folhas)
    livro.capitulos = [cap]
    livro.recursos["Images/a.png"] = Recurso(caminho="Images/a.png", tipo_mime="image/png", dados=b"\x89PNG")
    livro.marcos = []
    assert [type(b).__name__ for b in cap.blocos][1:3] == ["Lista", "Tabela"]
    livro.sumario = [EntradaDeSumario(rotulo="Nota", destino="Text/c.xhtml#fn1"),
                     EntradaDeSumario(rotulo="Célula", destino="Text/c.xhtml#c11"),
                     EntradaDeSumario(rotulo="Imagem", destino="Text/c.xhtml#img-a")]
    assert sumario.destinos_quebrados(livro) == [], "os ids dos extras não entraram no índice de âncoras"
    caminho = str(tmp_path / "a.epub")
    epub.escrever(livro, caminho)
    with zipfile.ZipFile(caminho) as z:
        gravado = z.read("OEBPS/Text/c.xhtml").decode("utf-8")
    assert '<li id="fn1"' in gravado and 'href="#fn1"' in gravado
    lido, _ = epub.ler(caminho)
    assert [e.destino for e in lido.sumario] == ["Text/c.xhtml#fn1", "Text/c.xhtml#c11", "Text/c.xhtml#img-a"]


def test_o_atributo_desconhecido_ainda_manda_o_elemento_para_ilha():
    cap = xhtml.ler(_XHTML.replace('<li id="fn1"', '<li data-x="1" id="fn1"'), "Text/c.xhtml")
    assert any(type(b).__name__ == "IlhaBruta" and b.elemento == "ol" for b in cap.blocos)


def test_o_rascunho_antigo_sem_extras_abre():
    from core.editor import modelo

    cap = xhtml.ler(_XHTML, "Text/c.xhtml")
    dados = modelo.para_dict(cap)

    def sem(d):
        if isinstance(d, dict):
            return {k: sem(v) for k, v in d.items()
                    if k not in ("extras_da_imagem", "extras_das_filas", "extras_do_corpo", "extras_da_raiz",
                                 "midia_das_folhas") and not (k == "extras" and d.get("tipo") in
                                                              ("ItemDeLista", "Celula"))}
        if isinstance(d, list):
            return [sem(v) for v in d]
        return d

    velho = modelo.de_dict(sem(dados))
    assert xhtml.escrever(velho).startswith("<?xml")
