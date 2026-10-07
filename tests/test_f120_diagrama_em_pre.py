"""
Testes da F120 — o diagrama em fonte saía com sete casas por fila.

Na Chess Merida a casa clara vazia é o **espaço**, e toda fila do tabuleiro começa
ou termina numa casa clara. Com um `<p>` por fila, o espaço da ponta era o primeiro
a sumir: o "Mend and Prettify" do Sigil apara o começo e o fim de cada parágrafo, e o
leitor que não aplica o `white-space: pre` da folha junta o espaço da borda como junta
o de qualquer parágrafo. O tabuleiro aparecia 7×8, sem erro nenhum — foi como o
usuário o viu, no *The Russian Endgame Handbook*. As filas agora moram num `<pre>` só,
que ninguém apara e que já é pré-formatado sem folha; o editor lê as duas formas,
e a folha de um livro de antes ganha as regras do `pre` quando ele é gravado.

O que prende o defeito é o **desenho**, e não só a marcação: o `fitz.Story` (o mesmo
motor do PDF do editor) desenha a página com a folha e a fonte do EPUB, e as filas
são contadas no que ele desenhou.

Rodar sem pytest:      python tests/test_f120_diagrama_em_pre.py
"""

import os
import re
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import exportar, livro
from core import render_diagrama as rd
from core.editor import dialeto, epub, fontes, modelo as m, pdf_io, xhtml
from core.editor.conversao import OpcoesDeConversao

MERIDA = "ChessMerida-Diagram"
SKAK = "SkakNew-Diagram"

#: O diagrama que o usuário mandou (2026-09-23): a p. 368 do Rabinovich, que saiu
#: `<p>T + +l+</p>` depois de passar pelo Sigil.
FEN = "1r4k1/8/5PK1/8/8/8/R7/8 w - - 0 1"

CABECA = ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
          '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head><body>\n')
PE = "\n</body></html>\n"


def _figura(nome=MERIDA, orientacao="branca", coordenadas=False, emoldurada=False):
    png, largura, altura = rd.desenhar(FEN, fonte=nome, lado_px=96)
    fonte = rd.carregar(nome)
    linhas = (rd.grade(FEN, fonte, orientacao, "simples", "reto") if emoldurada
              else rd.linhas(FEN, fonte, orientacao))
    return livro.Figura(png, largura, altura, fen=FEN, origem="render", linhas=linhas, fonte=nome,
                        coordenadas=coordenadas, orientacao=orientacao, linhas_emolduradas=emoldurada)


def _epub(*figuras, pasta=None, **kw):
    caminho = os.path.join(pasta or tempfile.mkdtemp(), "livro.epub")
    exportar.para_epub([livro.PaginaExtraida(numero=0, blocos=[livro.Paragrafo("Prosa."), *figuras])],
                       caminho, diagramas="fonte", **kw)
    return caminho


def _ler(caminho):
    with zipfile.ZipFile(caminho) as z:
        return {n: z.read(n) for n in z.namelist()}


def _pagina_e_folha(caminho):
    entradas = _ler(caminho)
    return entradas["OEBPS/pagina-0001.xhtml"].decode("utf-8"), entradas["OEBPS/estilo.css"].decode("utf-8")


def _aparar_como_o_sigil(texto: str) -> str:
    """
    O que o "Mend and Prettify" do Sigil faz com um bloco de texto e que aqui importa:
    tira o espaço do começo e do fim de cada `<p>` — e deixa o `<pre>` como está. A
    indentação e as linhas em branco que ele põe entre os blocos não mudam casa.
    """
    return re.sub(r"(<p\b[^>]*>)\s*(.*?)\s*(</p>)", r"\1\2\3", texto, flags=re.S)


REGUA = '<span class="colunas">'


def _como_antes_da_f120(texto: str) -> str:
    """A marcação de antes: um `<p>` por fila, a régua das letras num `p.colunas`."""
    def paragrafo(fila: str) -> str:
        if fila.startswith(REGUA):
            return f'<p class="colunas">{fila[len(REGUA):-len("</span>")]}</p>'
        return f"<p>{fila}</p>"

    def paragrafos(achado):
        return "\n".join(paragrafo(fila) for fila in achado.group(1).split("\n"))
    return re.sub(r"<pre>(.*?)</pre>", paragrafos, texto, flags=re.S)


def _folha_de_antes(folha: str) -> str:
    """A folha de antes: as regras das filas só para o `p`."""
    return re.sub(r"(div\.diagrama(?:\.[\w-]+)?) pre, \1 p \{", r"\1 p {", folha)


def _epub_de_antes(origem: str, destino: str) -> str:
    """O mesmo livro como o exportador o escrevia antes da F120."""
    with zipfile.ZipFile(origem) as z, zipfile.ZipFile(destino, "w") as novo:
        for info in z.infolist():
            dados = z.read(info)
            if info.filename.endswith(".xhtml"):
                dados = _como_antes_da_f120(dados.decode("utf-8")).encode("utf-8")
            elif info.filename.endswith(".css"):
                dados = _folha_de_antes(dados.decode("utf-8")).encode("utf-8")
            novo.writestr(info, dados)
    return destino


def _filas_desenhadas(doc, fonte="Merida"):
    """`[(texto, largura em casas)]` das linhas desenhadas na fonte, de cima para baixo."""
    filas = {}
    for pagina in doc:
        for bloco in pagina.get_text("rawdict")["blocks"]:
            for linha in bloco.get("lines", []):
                for span in linha["spans"]:
                    if fonte in span["font"]:
                        for c in span["chars"]:
                            filas.setdefault((pagina.number, round(c["origin"][1], 1)), []).append((c, span["size"]))
    saida = []
    for _chave, chars in sorted(filas.items()):
        chars.sort(key=lambda par: par[0]["origin"][0])
        largura = max(c["bbox"][2] for c, _ in chars) - min(c["bbox"][0] for c, _ in chars)
        saida.append(("".join(c["c"] for c, _ in chars), round(largura / chars[0][1], 2)))
    return saida


def _desenhar(corpo: str, folha: str, entradas: dict, tmp_path) -> list:
    """O corpo da página desenhado pelo `fitz.Story` com a folha e as fontes do EPUB."""
    fitz = pytest.importorskip("fitz")
    arquivo = fitz.Archive()
    for nome, dados in entradas.items():
        if nome.startswith("OEBPS/fonts/"):
            arquivo.add(dados, nome[len("OEBPS/"):])
    story = fitz.Story(html=f"<html><body>{corpo}</body></html>", user_css=folha, archive=arquivo)
    caminho = str(tmp_path / f"desenho-{len(os.listdir(tmp_path))}.pdf")
    escritor = fitz.DocumentWriter(caminho)
    mais = True
    while mais:
        dispositivo = escritor.begin_page(fitz.paper_rect("a4"))
        mais, _ = story.place(fitz.Rect(36, 36, 559, 806))
        story.draw(dispositivo)
        escritor.end_page()
    escritor.close()
    doc = fitz.open(caminho)
    try:
        return _filas_desenhadas(doc)
    finally:
        doc.close()


def _corpo(pagina: str) -> str:
    return pagina[pagina.index("<body>") + len("<body>"):pagina.index("</body>")]


# ----------------------------------------------------------------------
# O arquivo que o exportador escreve
# ----------------------------------------------------------------------

def test_as_filas_saem_num_pre_com_oito_casas_cada():
    pagina, _folha = _pagina_e_folha(_epub(_figura()))
    ET.fromstring(pagina.encode("utf-8"))
    div = re.search(r'<div class="diagrama[^"]*"[^>]*>(.*?)</div>', pagina, re.S).group(1)
    assert not re.search(r"<p\b", div), "o tabuleiro voltou a ser um <p> por fila"
    filas = re.search(r"<pre>(.*?)</pre>", div, re.S).group(1).split("\n")
    assert filas == rd.linhas(FEN, rd.carregar(MERIDA))
    # a oitava começa numa casa clara vazia, e a sétima termina numa: eram as que o Sigil comia
    assert filas[0] == " T + +l+" and filas[1] == "+ + + + "


def test_aparado_como_o_sigil_o_tabuleiro_continua_oito_por_oito(tmp_path):
    """
    O defeito, desenhado: na forma de antes, aparada, sete das oito filas perdem a casa
    da ponta (só `r+ + + +`, que começa numa peça e termina numa casa escura, escapa —
    como no diagrama que o usuário mandou); na de hoje nenhuma perde.
    """
    caminho = _epub(_figura(), _figura(orientacao="preta"))
    entradas = _ler(caminho)
    pagina, folha = _pagina_e_folha(caminho)
    esperadas = rd.linhas(FEN, rd.carregar(MERIDA)) + rd.linhas(FEN, rd.carregar(MERIDA), "preta")

    for corpo in (_corpo(pagina), _aparar_como_o_sigil(_corpo(pagina))):
        desenhadas = _desenhar(corpo, folha, entradas, tmp_path)
        assert [texto for texto, _ in desenhadas] == esperadas
        assert {largura for _, largura in desenhadas} == {8.0}

    de_antes = _aparar_como_o_sigil(_como_antes_da_f120(_corpo(pagina)))
    desenhadas = _desenhar(de_antes, _folha_de_antes(folha), entradas, tmp_path)
    assert [largura for _, largura in desenhadas[:8]] == [7.0] * 6 + [8.0, 7.0]


def test_a_folha_da_ao_pre_a_fonte_o_corpo_e_o_white_space():
    _pagina, folha = _pagina_e_folha(_epub(_figura(), _figura(SKAK)))
    regra = re.search(r"div\.diagrama pre, div\.diagrama p \{([^}]*)\}", folha).group(1)
    for declaracao in ("white-space: pre", "line-height: 1 !important", "margin: 0", "letter-spacing: 0",
                       "font-size: 16pt"):
        assert declaracao in regra
    for nome in (MERIDA, SKAK):
        classe = exportar.classe_da_fonte(nome)
        assert (f'div.diagrama.{classe} pre, div.diagrama.{classe} p '
                f'{{ font-family: "{nome}", monospace; }}') in folha


def test_coordenada_em_span_e_moldura_em_glifo_tambem_saem_no_pre():
    pagina, _folha = _pagina_e_folha(_epub(_figura(SKAK, coordenadas=True),
                                           _figura(orientacao="preta", coordenadas=True, emoldurada=True)))
    skak, merida = re.findall(r"<pre>(.*?)</pre>", pagina, re.S)
    filas = skak.split("\n")
    assert len(filas) == 9 and all(f.startswith('<span class="rot"><i>') for f in filas[:8])
    assert filas[8].startswith('<span class="colunas"><span class="rot"></span><span class="col"><i>a</i>')
    assert merida.split("\n") == rd.grade(FEN, rd.carregar(MERIDA), "preta", "simples", "reto")


# ----------------------------------------------------------------------
# O editor
# ----------------------------------------------------------------------

def test_o_editor_le_o_pre_e_devolve_o_mesmo_pre():
    # Sem moldura, para as oito linhas nuas ficarem nuas: com moldura, a da fonte vem
    # desde a F122 (ver `test_f122_moldura_na_fonte.py`).
    caminho = _epub(_figura(), _figura(orientacao="preta"), _figura(SKAK, coordenadas=True),
                    _figura(orientacao="preta", coordenadas=True, emoldurada=True), moldura="sem")
    pagina, folha = _pagina_e_folha(caminho)
    assert pagina.count("<pre>") == 4
    caixa = dialeto.moldura_da_folha(folha)
    assert caixa == ("sem", "reto")
    cap = xhtml.ler(pagina.encode("utf-8"), "pagina-0001.xhtml", caixa)
    assert not any(isinstance(b, m.IlhaBruta) for b in cap.blocos), cap.avisos
    diagramas = [b for b in cap.blocos if isinstance(b, m.Diagrama)]
    assert [d.estado for d in diagramas] == ["ok"] * 4, [d.aviso for d in diagramas]
    assert [d.orientacao for d in diagramas] == ["branca", "preta", "branca", "preta"]
    assert [d.coordenadas for d in diagramas] == [False, False, True, True]
    assert all(d.fen == FEN for d in diagramas)
    saida = xhtml.escrever(cap)
    # O editor escreve o mesmo tabuleiro que o exportador (R5).
    assert re.findall(r"<pre>(.*?)</pre>", saida, re.S) == re.findall(r"<pre>(.*?)</pre>", pagina, re.S)
    assert m.igual(cap, xhtml.ler(saida, cap.arquivo))


@pytest.mark.parametrize("orientacao", ["branca", "preta"])
def test_o_livro_de_antes_aparado_pelo_sigil_volta_inteiro_pelo_editor(orientacao):
    """
    Um livro de antes da F120 que já passou pelo Sigil: sete casas na maioria das
    filas. O FEN do `title` manda na posição, a fila aparada ainda diz a orientação, e
    a gravação redesenha o tabuleiro inteiro, no `<pre>` — e, com a moldura simples da
    folha, dentro da moldura da própria fonte (F122).
    """
    pagina, _folha = _pagina_e_folha(_epub(_figura(orientacao=orientacao)))
    div = re.search(r"<div class=\"diagrama.*?</div>", pagina, re.S).group(0)
    aparado = _aparar_como_o_sigil(_como_antes_da_f120(div))
    assert re.search(r"<p>[^ <][^<]{6}</p>", aparado), "o crivo não aparou nada"
    cap = xhtml.ler(CABECA + aparado + PE)
    d = cap.blocos[0]
    assert isinstance(d, m.Diagrama) and d.estado == "ok", d.aviso
    assert d.orientacao == orientacao and d.fen == FEN
    filas = re.search(r"<pre>(.*?)</pre>", xhtml.escrever(cap), re.S).group(1).split("\n")
    merida = rd.carregar(MERIDA)
    assert filas == rd.grade(FEN, merida, orientacao, "simples", "reto", com_rotulos=False)
    assert [fila[1:9] for fila in filas[1:9]] == rd.linhas(FEN, merida, orientacao)


def test_a_fila_que_nao_bate_nem_aparada_continua_para_revisar():
    """Aparar a ponta é o único perdão: uma casa trocada no meio ainda é `revisar`."""
    pagina, _folha = _pagina_e_folha(_epub(_figura()))
    div = re.search(r"<div class=\"diagrama.*?</div>", pagina, re.S).group(0)
    trocado = div.replace(" T + +l+", " T + +k+")
    d = xhtml.ler(CABECA + trocado + PE).blocos[0]
    assert d.estado == "revisar" and d.aviso


def test_as_regras_do_pre_saem_das_do_p_e_so_quando_faltam():
    _pagina, folha = _pagina_e_folha(_epub(_figura()))
    assert fontes.regras_para_o_pre(folha) == ""
    antiga = _folha_de_antes(folha)
    base = re.search(r"div\.diagrama p \{([^}]*)\}", antiga).group(1)
    assert fontes.regras_para_o_pre(antiga) == (
        f"div.diagrama pre {{{base}}}\n"
        f'div.diagrama.fonte-{MERIDA} pre {{ font-family: "{MERIDA}", monospace; }}\n')
    # comentário não conta como regra, e o que mora num `@media` é da folha, não daqui
    assert fontes.regras_para_o_pre("/* div.diagrama pre */ div.diagrama p { margin: 0; }") == \
        "div.diagrama pre { margin: 0; }\n"
    assert fontes.regras_para_o_pre("@media print { div.diagrama p { margin: 0; } }") == ""


def test_o_editor_ensina_a_folha_de_antes_a_estilizar_o_pre(tmp_path):
    antigo = _epub_de_antes(_epub(_figura(), _figura(SKAK), pasta=str(tmp_path)), str(tmp_path / "antes.epub"))
    aberto, _r = epub.ler(antigo)
    assert [b.estado for c in aberto.capitulos for b in c.blocos if isinstance(b, m.Diagrama)] == ["ok", "ok"]
    regravado = str(tmp_path / "regravado.epub")
    epub.escrever(aberto, regravado)
    entradas = _ler(regravado)
    pagina = entradas["OEBPS/pagina-0001.xhtml"].decode("utf-8")
    folha = entradas["OEBPS/estilo.css"].decode("utf-8")
    assert pagina.count("<pre>") == 2 and not re.search(r"<p>[ +]", pagina)
    assert folha.startswith(_pagina_e_folha(antigo)[1]), "a folha de antes foi mexida"
    bloco = folha[folha.index(fontes.MARCA_DAS_FONTES):]
    assert re.search(r"div\.diagrama pre \{[^}]*font-size: 16pt;[^}]*white-space: pre;", bloco)
    for nome in (MERIDA, SKAK):
        assert f'div.diagrama.fonte-{nome} pre {{ font-family: "{nome}", monospace; }}' in bloco
    # desenhado com a folha regravada, o tabuleiro é 8×8 — dentro da moldura da fonte,
    # que é a simples que a folha de antes desenhava na CSS (F122)
    desenhadas = _desenhar(_corpo(pagina), folha, entradas, tmp_path)
    assert [texto for texto, _ in desenhadas] == rd.grade(FEN, rd.carregar(MERIDA), "branca", "simples",
                                                          "reto", com_rotulos=False)
    assert {largura for _, largura in desenhadas} == {10.0}
    # gravado de novo, o bloco é refeito igual, e não dobrado
    de_novo = str(tmp_path / "de-novo.epub")
    epub.escrever(epub.ler(regravado)[0], de_novo)
    assert _ler(de_novo)["OEBPS/estilo.css"].decode("utf-8") == folha


def test_o_pdf_do_editor_desenha_o_livro_de_antes_oito_por_oito(tmp_path):
    fitz = pytest.importorskip("fitz")
    antigo = _epub_de_antes(_epub(_figura(), pasta=str(tmp_path)), str(tmp_path / "antes.epub"))
    aberto, _r = epub.ler(antigo)
    caminho = str(tmp_path / "livro.pdf")
    pdf_io.escrever(aberto, caminho, OpcoesDeConversao(modo_de_diagrama="fonte"))
    doc = fitz.open(caminho)
    try:
        desenhadas = _filas_desenhadas(doc)
    finally:
        doc.close()
    # As oito filas de oito casas, dentro da moldura simples da fonte (F122).
    merida = rd.carregar(MERIDA)
    filas = [texto for texto, _ in desenhadas]
    assert filas == rd.grade(FEN, merida, "branca", "simples", "reto", com_rotulos=False)
    assert [fila[1:9] for fila in filas[1:9]] == rd.linhas(FEN, merida)
    assert {largura for _, largura in desenhadas} == {10.0}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
