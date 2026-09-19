"""
Testes de `core/editor/xhtml.py` (ED-00; SPEC_EDITOR §6.5): os cinco contratos de ida e
volta, as entidades HTML, as ilhas byte a byte, os erros com linha e coluna, o EPUB que
o projeto escreve hoje (R5) e o inverso das linhas do diagrama.

O que os testes de propriedade medem é a **idempotência** de `escrever ∘ ler` sobre
capítulos gerados (`tests/editor_gerador.py`), e não uma lista de casos escolhidos à
mão: uma fronteira esquecida entre trechos, uma classe que o leitor não devolve, um
atributo escrito em ordem diferente — tudo isso aparece num dos 200 capítulos.

Rodar sem pytest:      python tests/test_editor_xhtml.py
"""

import os
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_gerador as gerador
from core.editor import dialeto, modelo as m, xhtml

FEN = "r1bqk2r/pp2bppp/2n1pn2/3p4/3P4/2N1PN2/PP2BPPP/R1BQK2R w - - 0 1"
POSICAO = FEN.split()[0]
DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados", "editor")

CABECA = ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
          '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
          '<head><title>t</title></head><body>\n')
PE = "\n</body></html>\n"


def _doc(corpo: str) -> str:
    return CABECA + corpo + PE


# ----------------------------------------------------------------------
# R2 e R1 por propriedade (AC-ED00-1, AC-ED00-2)
# ----------------------------------------------------------------------

def test_r2_ler_escrever_devolve_o_mesmo_capitulo_em_200_gerados():
    for semente in range(1, 201):
        cap = gerador.capitulo(semente)
        saida = xhtml.escrever(cap)
        assert xhtml.bem_formado(saida) is None, semente
        cap2 = xhtml.ler(saida, cap.arquivo)
        assert m.igual(cap, cap2), f"semente {semente}"
        assert cap2.avisos == [], f"semente {semente}: {cap2.avisos}"


def test_r1_escrever_ler_e_idempotente_em_50_gerados():
    for semente in range(300, 350):
        cap = gerador.capitulo(semente)
        x = xhtml.escrever(cap)
        assert xhtml.canonico(x, cap.arquivo) == x, f"semente {semente}"
        assert xhtml.canonico(xhtml.escrever(xhtml.ler(x, cap.arquivo)), cap.arquivo) == xhtml.canonico(x, cap.arquivo)


def test_r1_canonico_normaliza_entidades_e_ids_gerados_sem_referencia():
    a = _doc('<p id="b-0123abcd">a&nbsp;b</p>')
    b = _doc("<p>a&#160;b</p>")
    c = _doc("<p>a\u00a0b</p>")
    assert xhtml.canonico(a) == xhtml.canonico(b) == xhtml.canonico(c)
    assert 'id="b-0123abcd"' not in xhtml.canonico(a)
    referenciado = _doc('<p id="b-0123abcd">a</p><p><a href="#b-0123abcd">x</a></p>')
    assert 'id="b-0123abcd"' in xhtml.canonico(referenciado)


# ----------------------------------------------------------------------
# R3: ilhas, entidades, comentários (AC-ED00-3)
# ----------------------------------------------------------------------

ILHAS = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 4"><rect width="4" height="4"/>x&#160;y</svg>',
    '<div style="columns: 2"><p>duas colunas</p></div>',
    "<table><tr><td><table><tr><td>aninhada</td></tr></table></td></tr></table>",
    "<!-- um comentário com &amp; e <b> -->",
    "<?pi dados?>",
    '<p>com <cite lang="de">Kasparov</cite> inline, <br/>quebra e <img src="a.png" alt="a>b"/> dentro</p>',
)


def test_r3_ilhas_comentarios_e_pi_atravessam_byte_a_byte():
    cap = xhtml.ler(_doc("\n".join(ILHAS)), "Text/c.xhtml")
    tipos = [type(b).__name__ for b in cap.blocos]
    assert tipos[:5] == ["IlhaBruta"] * 5 and tipos[5] == "Paragrafo"
    for esperado, bloco in zip(ILHAS[:5], cap.blocos[:5]):
        assert bloco.xhtml == esperado
    saida = xhtml.escrever(cap)
    for esperado in ILHAS[:5]:
        assert esperado in saida
    p = cap.blocos[5]
    ilhas_inline = [t.ilha for t in p.trechos if t.ilha]
    assert ilhas_inline == ['<cite lang="de">Kasparov</cite>', '<img src="a.png" alt="a>b"/>']
    assert any(t.quebra_antes for t in p.trechos)
    assert m.igual(cap, xhtml.ler(saida, "Text/c.xhtml"))


def test_r3_a_entidade_nomeada_da_ilha_sai_numerica_e_o_epub3_a_aceita():
    cap = xhtml.ler(_doc("<svg><text>a&nbsp;b&mdash;c</text></svg>"), "Text/c.xhtml")
    assert cap.blocos[0].xhtml == "<svg><text>a&#160;b&#8212;c</text></svg>"
    saida = xhtml.escrever(cap)
    assert "&nbsp;" not in saida and "&#160;" in saida
    ET.fromstring(saida.encode("utf-8"))      # o XML puro aceita o que sai


def test_entidades_html_no_texto_sao_decodificadas_com_e_sem_doctype():
    com = xhtml.ler(_doc("<p>a&nbsp;b&mdash;c&#160;d</p>"))
    sem = xhtml.ler(_doc("<p>a&nbsp;b</p>").replace("<!DOCTYPE html>\n", ""))
    xhtml11 = xhtml.ler(_doc("<p>a&nbsp;b</p>").replace(
        "<!DOCTYPE html>", '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
                           '"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'))
    assert m.texto_de(com.blocos[0]) == "a\u00a0b\u2014c\u00a0d"
    assert m.texto_de(sem.blocos[0]) == m.texto_de(xhtml11.blocos[0]) == "a\u00a0b"


def test_standalone_yes_e_lido_e_a_declaracao_e_regenerada():
    doc = _doc("<p>a&nbsp;b</p>").replace('encoding="utf-8"?>', 'encoding="utf-8" standalone="yes"?>')
    cap = xhtml.ler(doc)
    assert m.texto_de(cap.blocos[0]) == "a\u00a0b"
    assert "standalone" not in xhtml.escrever(cap)


# ----------------------------------------------------------------------
# INV-06: erros com linha e coluna (AC-ED00-5)
# ----------------------------------------------------------------------

def test_tag_aberta_da_erro_com_linha_e_coluna():
    erro = xhtml.bem_formado(_doc("<p>aberto"))
    # O expat acusa onde o desencontro aparece: no `</body>` da linha seguinte.
    assert isinstance(erro, xhtml.ErroDeXhtml) and erro.linha in (4, 5) and erro.coluna > 0
    with pytest.raises(xhtml.ErroDeXhtml):
        xhtml.ler(_doc("<p>aberto"))


def test_prefixo_nao_declarado_e_erro():
    doc = _doc('<p epub:type="x">a</p>').replace(' xmlns:epub="http://www.idpf.org/2007/ops"', "")
    erro = xhtml.bem_formado(doc)
    assert erro is not None and "prefix" in erro.mensagem.lower()


def test_entidade_desconhecida_e_erro_e_nao_silencio():
    erro = xhtml.bem_formado(_doc("<p>a&naoexiste;b</p>"))
    assert erro is not None and "naoexiste" in erro.mensagem


def test_escrever_de_capitulo_gerado_passa_no_xml_puro():
    for semente in (1, 2, 3):
        ET.fromstring(xhtml.escrever(gerador.capitulo(semente)).encode("utf-8"))


# ----------------------------------------------------------------------
# R5: o EPUB que o projeto escreve hoje (AC-ED00-4)
# ----------------------------------------------------------------------

def _figura(fonte_nome, coordenadas, orientacao, texto=True, emoldurada=False):
    from core import livro, render_diagrama as rd
    png, largura, altura = rd.desenhar(FEN, lado_px=96)
    if not texto:
        return livro.Figura(png, largura, altura, origem="recorte")
    fonte = rd.carregar(fonte_nome)
    linhas = (rd.grade(FEN, fonte, orientacao, "simples", "reto") if emoldurada
              else rd.linhas(FEN, fonte, orientacao))
    return livro.Figura(png, largura, altura, fen=FEN, origem="render", linhas=linhas,
                        fonte=fonte.nome, coordenadas=coordenadas, orientacao=orientacao,
                        linhas_emolduradas=emoldurada)


def _epub_de_hoje(modo):
    from core import exportar, livro
    paginas = [
        livro.PaginaExtraida(numero=0, blocos=[
            livro.Paragrafo("Capítulo um", titulo=True, nivel=1),
            livro.Paragrafo("Prosa com negrito e ♕ figurina.", negrito=[(10, 17)]),
            _figura("SkakNew-Diagram", True, "branca"),
            _figura("SkakNew-Diagram", True, "preta"),
            _figura("SkakNew-Diagram", False, "preta"),
            livro.Paragrafo("Depois", titulo=True, nivel=2),
            livro.Tabela([["a", "b"], ["c", "d"]]),
        ]),
        livro.PaginaExtraida(numero=1, blocos=[
            livro.Paragrafo("Página dois."),
            _figura("ChessMerida-Diagram", True, "preta", emoldurada=True),
            _figura("SkakNew-Diagram", False, "branca", texto=False),
        ]),
    ]
    caminho = os.path.join(tempfile.mkdtemp(), f"livro-{modo}.epub")
    exportar.para_epub(paginas, caminho, diagramas=modo)
    with zipfile.ZipFile(caminho) as z:
        return {n[len("OEBPS/"):]: z.read(n) for n in z.namelist()
                if n.endswith(".xhtml") and "nav" not in n}


@pytest.mark.parametrize("modo", ["png", "fonte"])
def test_r5_o_epub_de_hoje_abre_sem_ilha_e_com_os_diagramas_de_volta(modo):
    paginas = _epub_de_hoje(modo)
    cap1 = xhtml.ler(paginas["pagina-0001.xhtml"], "pagina-0001.xhtml")
    cap2 = xhtml.ler(paginas["pagina-0002.xhtml"], "pagina-0002.xhtml")
    for cap in (cap1, cap2):
        assert not any(isinstance(b, m.IlhaBruta) for b in cap.blocos), cap.avisos
        assert not any(t.ilha for t in m.trechos_do_capitulo(cap))
        assert m.igual(cap, xhtml.ler(xhtml.escrever(cap), cap.arquivo))
    diagramas = [b for b in cap1.blocos if isinstance(b, m.Diagrama)]
    assert len(diagramas) == 3 and all(d.posicao == POSICAO for d in diagramas)
    assert [type(b).__name__ for b in cap1.blocos] == ["Titulo", "Paragrafo", "Diagrama", "Diagrama",
                                                      "Diagrama", "Titulo", "Tabela"]
    negrito = [t for t in cap1.blocos[1].trechos if t.negrito]
    assert negrito and negrito[0].texto == "negrito"
    if modo == "png":
        # O FEN vem do `alt`; a orientação não foi registrada — é o que "revisar" diz.
        assert all(d.estado == "revisar" and d.lado == "" and d.modo == "png" for d in diagramas)
    else:
        # O FEN vem do `title`, e a orientação é a que reproduz as linhas: tudo "ok".
        assert [d.orientacao for d in diagramas] == ["branca", "preta", "preta"]
        assert [d.coordenadas for d in diagramas] == [True, True, False]
        assert all(d.estado == "ok" and d.modo == "fonte" for d in diagramas)
    recorte = [b for b in cap2.blocos if isinstance(b, m.Figura)]
    assert len(recorte) == 1 and recorte[0].alt == "Diagrama"
    if modo == "fonte":
        merida = [b for b in cap2.blocos if isinstance(b, m.Diagrama)][0]
        assert merida.fonte == "ChessMerida-Diagram" and merida.orientacao == "preta" and merida.estado == "ok"


def test_um_div_de_fora_sem_titulo_e_sem_rotulo_fica_para_revisar():
    from core import render_diagrama as rd
    fonte = rd.mapa_da_fonte("SkakNew-Diagram")
    linhas = rd.linhas(FEN, fonte, "preta")
    div = ('<div class="diagrama caixa fonte-SkakNew-Diagram" role="img">\n'
           + "\n".join(f"<p>{linha}</p>" for linha in linhas) + "\n</div>")
    cap = xhtml.ler(_doc(div))
    d = cap.blocos[0]
    assert isinstance(d, m.Diagrama) and d.estado == "revisar" and d.aviso
    # Sem rótulo, as linhas giradas decodificam para a posição girada — e é por isso
    # que o estado é "revisar", e não um chute silencioso.
    assert d.posicao != POSICAO
    com_rotulo = ('<div class="diagrama caixa fonte-SkakNew-Diagram" role="img">\n'
                  + "\n".join(f'<p><span class="rot"><i>{i + 1}</i></span>{linha}</p>' for i, linha in enumerate(linhas))
                  + '\n<p class="colunas"><span class="rot"></span></p>\n</div>')
    d2 = xhtml.ler(_doc(com_rotulo)).blocos[0]
    assert d2.estado == "ok" and d2.orientacao == "preta" and d2.posicao == POSICAO


def test_o_inverso_das_linhas_em_50_fens_nas_duas_fontes():
    import random

    import chess
    from core import render_diagrama as rd
    r = random.Random(3)
    for _ in range(50):
        board = chess.Board()
        for _ in range(r.randint(0, 30)):
            lances = list(board.legal_moves)
            if not lances:
                break
            board.push(r.choice(lances))
        posicao = board.fen().split()[0]
        for nome in rd.fontes():
            fonte = rd.mapa_da_fonte(nome)
            assert rd.fen_de_linhas(rd.linhas(posicao, fonte), fonte) == (posicao, None)
            grade = rd.grade(posicao, fonte, "preta", "simples", "reto")
            if grade is not None:
                assert rd.fen_de_linhas(grade, fonte) == (posicao, "preta")
                assert rd.fen_de_linhas(rd.grade(posicao, fonte, "branca", "simples", "reto"), fonte) == (posicao, "branca")


# ----------------------------------------------------------------------
# O dialeto, caso a caso
# ----------------------------------------------------------------------

def test_hrefs_viram_relativos_ao_opf_e_voltam_relativos_ao_capitulo():
    doc = _doc('<p><a href="../Text/b.xhtml#x">b</a> <a href="https://e.org/?a=1&amp;b=2">e</a></p>'
               '<figure><img src="../Images/i.png" alt="i"/></figure>').replace(
        "<head><title>t</title></head>", '<head><title>t</title><link rel="stylesheet" type="text/css" href="../Styles/s.css"/></head>')
    cap = xhtml.ler(doc, "Text/a.xhtml")
    assert cap.folhas == ["Styles/s.css"]
    assert cap.blocos[0].trechos[0].link == "Text/b.xhtml#x"
    assert cap.blocos[0].trechos[2].link == "https://e.org/?a=1&b=2"
    assert cap.blocos[1].recurso == "Images/i.png"
    saida = xhtml.escrever(cap)
    assert 'href="../Styles/s.css"' in saida and 'href="b.xhtml#x"' in saida and 'src="../Images/i.png"' in saida


def test_o_titulo_so_e_proprio_quando_difere_do_deduzido():
    cap = xhtml.ler(_doc("<h1>Abertura</h1>").replace("<title>t</title>", "<title>Abertura</title>"))
    assert cap.titulo == "" and cap.titulo_efetivo == "Abertura"
    cap2 = xhtml.ler(_doc("<h1>Abertura</h1>").replace("<title>t</title>", "<title>Outro</title>"))
    assert cap2.titulo == "Outro"


def test_figura_sem_alt_avisa_e_nao_bloqueia():
    cap = xhtml.ler(_doc('<figure><img src="i.png" alt=""/></figure>'))
    assert isinstance(cap.blocos[0], m.Figura) and any("sem alt" in a for a in cap.avisos)


def test_notas_de_rodape_e_de_fim_e_a_referencia_regenerada():
    cap = xhtml.ler(_doc(
        '<p>a<a epub:type="noteref" role="doc-noteref" href="#n2"><sup>9</sup></a>'
        'b<a epub:type="noteref" role="doc-noteref" href="#n1"><sup>9</sup></a></p>'
        '<aside epub:type="footnote" role="doc-footnote" id="n1"><p>rodapé</p></aside>'
        '<section epub:type="endnotes" role="doc-endnotes"><ol><li epub:type="endnote" id="n2"><p>fim</p></li></ol></section>'))
    assert [(n.id, n.tipo, m.texto_de(n)) for n in cap.notas] == [("n1", "rodape", "rodapé"), ("n2", "fim", "fim")]
    assert [t.nota for t in cap.blocos[0].trechos if t.nota] == ["n2", "n1"]
    saida = xhtml.escrever(cap)
    assert 'href="#n1"><sup>1</sup>' in saida and 'href="#n2"><sup>2</sup>' in saida
    assert '<li epub:type="endnote" id="n2">' in saida and 'role="doc-footnote" id="n1"' in saida


def test_marca_de_pagina_e_quebra_de_pagina_sao_coisas_diferentes():
    cap = xhtml.ler(_doc('<hr class="pagina" data-pagina="27"/><hr class="quebra"/><hr/>'
                         '<p>a<span epub:type="pagebreak" role="doc-pagebreak" id="pg-28" aria-label="28"/>b</p>'))
    assert [type(b).__name__ for b in cap.blocos] == ["MarcaDePagina", "QuebraDePagina", "Separador", "Paragrafo"]
    assert cap.blocos[0].pagina == 27 and cap.blocos[0].id == "pg-27"
    assert [t.pagina for t in cap.blocos[3].trechos] == [None, 28]
    saida = xhtml.escrever(cap)
    assert 'epub:type="pagebreak" role="doc-pagebreak" id="pg-27" aria-label="27"' in saida
    assert 'class="quebra" style="page-break-after: always"' in saida
    assert 'id="pg-28" aria-label="28"/>b' in saida


def test_sinonimos_inline_viram_a_forma_canonica():
    cap = xhtml.ler(_doc("<p><b>n</b><i>i</i><strike>t</strike><ins>u</ins></p>"))
    t = cap.blocos[0].trechos
    assert (t[0].negrito, t[1].italico, t[2].tachado, t[3].sublinhado) == (True, True, True, True)
    assert "<strong>n</strong><em>i</em><u>u</u>" in xhtml.escrever(cap).replace("<s>t</s>", "")


def test_atributo_desconhecido_vira_ilha_e_conhecido_vai_para_extras():
    cap = xhtml.ler(_doc('<p onclick="x()">a</p><p lang="de" title="d" epub:type="bridgehead">b</p>'))
    assert isinstance(cap.blocos[0], m.IlhaBruta)
    assert cap.blocos[1].extras == {"lang": "de", "title": "d", "epub:type": "bridgehead"}


def test_origem_sai_como_data_origem_e_volta():
    p = m.Paragrafo(trechos=[m.Trecho(texto="x")],
                    origem=m.Origem(page_id="d-p0003", bloco_id="block-d-p0003-b0001", pagina=2, caixa=(1, 2, 3, 4)))
    cap = m.Capitulo(arquivo="Text/c.xhtml", blocos=[p, m.MarcaDePagina(pagina=3)])
    saida = xhtml.escrever(cap)
    assert 'data-origem-pagina="d-p0003"' in saida and 'data-origem-caixa="1,2,3,4"' in saida
    assert 'data-pagina="3"' in saida
    cap2 = xhtml.ler(saida, "Text/c.xhtml")
    assert cap2.blocos[0].origem.bloco_id == "block-d-p0003-b0001" and cap2.blocos[0].origem.pagina == 2
    assert cap2.blocos[1].pagina == 3 and cap2.blocos[1].origem is None


def test_alt_gerado_lista_as_pecas_e_nao_o_fen():
    d = m.Diagrama(fen="8/8/4k3/8/8/4K3/8/8 w - - 0 1")
    assert dialeto.alt_de(d) == "Brancas: Rei e3; Pretas: Rei e6"
    assert dialeto.alt_de(d, "en") == "White: King e3; Black: King e6"
    saida = xhtml.escrever(m.Capitulo(arquivo="Text/c.xhtml", blocos=[d]))
    assert 'alt="Brancas: Rei e3; Pretas: Rei e6"' in saida and 'title="8/8/4k3/8/8/4K3/8/8 w - - 0 1"' in saida


def test_fragmentos():
    blocos = xhtml.ler_fragmento("<p>a</p><p><b>b</b></p>")
    assert len(blocos) == 2 and blocos[1].trechos[0].negrito
    assert xhtml.ler_fragmento("só <em>inline</em>")[0].trechos[1].italico
    assert xhtml.escrever_fragmento(blocos) == "<p>a</p>\n<p><strong>b</strong></p>"


def test_o_xhtml_esperado_esta_no_golden():
    """Um capítulo fixo bate byte a byte com `tests/dados/editor/capitulo.xhtml`."""
    cap = gerador.capitulo(42)
    saida = xhtml.escrever(cap)
    caminho = os.path.join(DADOS, "capitulo.xhtml")
    if not os.path.exists(caminho):
        os.makedirs(DADOS, exist_ok=True)
        with open(caminho, "w", encoding="utf-8", newline="\n") as f:
            f.write(saida)
    with open(caminho, encoding="utf-8", newline="") as f:
        esperado = f.read().replace("\r\n", "\n")
    assert saida == esperado


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
