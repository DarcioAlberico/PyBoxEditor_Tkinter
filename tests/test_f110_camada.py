"""
F110 — o livro que já trazia o texto: a camada do PDF lida como texto.

`core/pdf_nativo.py` decide por página se a camada de texto é a do livro
(`avaliar_pagina`) e, quando é, tira dela o texto e os diagramas
(`extrair_pagina`) — sem OCR. Os testes montam PDFs nascidos digitais com o
próprio PyMuPDF: prosa em Helvetica, a figurina na `SkakNew-Figurine` e o
tabuleiro na `ChessMerida-Diagram` do projeto, uma casa por glifo, como o
Dvoretsky de 2025 compõe o dele. Os do fim rodam sobre os PDFs de `PDF/`
quando eles estão na máquina.
"""

import glob
import os

import fitz
import pytest

from core import livro, pdf_nativo, render_diagrama
from core.editorial_adapters import (pagina_editorial_para_extraida,
                                     pagina_extraida_para_pagina)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MERIDA = os.path.join(RAIZ, "fonts", "ChessMerida-Diagram.ttf")
FIGURINA = os.path.join(RAIZ, "fonts", "SkakNew-Figurine.otf")

#: Rei branco em b5, peões brancos em a4 e c4, rei preto em b7, peão preto em
#: b6 — o diagrama 1-7 do Dvoretsky.
FEN = "8/1k6/1p6/1K6/P1P5/8/8/8"

CASA = 20.0


# ----------------------------------------------------------------------
# PDFs de prova
# ----------------------------------------------------------------------

def _centro(pagina, texto, x_centro, y, corpo=10, fonte="helv"):
    largura = fitz.get_text_length(texto, fontname=fonte, fontsize=corpo)
    pagina.insert_text((x_centro - largura / 2, y), texto, fontname=fonte,
                       fontsize=corpo)


def _tabuleiro(pagina, fen=FEN, x0=220.0, y0=200.0, rotulos=True,
               orientacao="branca", legenda=("1-7", "B"), cabecalho=""):
    """Um diagrama composto em fonte, casa a casa, como o livro nascido digital."""
    linhas = render_diagrama.linhas(fen, render_diagrama.carregar("ChessMerida-Diagram"),
                                    orientacao)
    for i, linha in enumerate(linhas):
        pagina.insert_text((x0, y0 + (i + 1) * CASA), linha, fontfile=MERIDA,
                           fontname="merida", fontsize=CASA)
    if rotulos:
        filas, colunas = "87654321", "abcdefgh"
        if orientacao == "preta":
            filas, colunas = filas[::-1], colunas[::-1]
        for i, fila in enumerate(filas):
            pagina.insert_text((x0 - 12, y0 + i * CASA + 14), fila, fontname="helv",
                               fontsize=8)
        for j, coluna in enumerate(colunas):
            pagina.insert_text((x0 + j * CASA + 8, y0 + 8 * CASA + 11), coluna,
                               fontname="helv", fontsize=8)
    centro = x0 + 4 * CASA
    if cabecalho:
        _centro(pagina, cabecalho, centro, y0 - 10, fonte="hebo")
    for k, texto in enumerate(legenda):
        _centro(pagina, texto, centro, y0 + 8 * CASA + 32 + k * 12)


def _prosa(pagina, x, y, linhas, recuo=10.0, passo=12.0, corpo=10, fonte="helv"):
    """Um parágrafo: a primeira linha recuada, as outras na margem."""
    for i, texto in enumerate(linhas):
        pagina.insert_text((x + (recuo if i == 0 else 0), y + i * passo), texto,
                           fontname=fonte, fontsize=corpo)
    return y + len(linhas) * passo


def _lance(pagina, x, y, antes, peca, depois, corpo=10):
    """`antes` + figurina (na fonte de figurina) + `depois`, na mesma linha."""
    pagina.insert_text((x, y), antes, fontname="helv", fontsize=corpo)
    x += fitz.get_text_length(antes, fontname="helv", fontsize=corpo)
    pagina.insert_text((x, y), peca, fontfile=FIGURINA, fontname="fig", fontsize=corpo)
    x += fitz.Font(fontfile=FIGURINA).text_length(peca, fontsize=corpo)
    pagina.insert_text((x, y), depois, fontname="helv", fontsize=corpo)


def _livro_digital(caminho, paginas=1, **tabuleiro):
    """Páginas com título, prosa, um lance com figurina e o diagrama."""
    doc = fitz.open()
    for _ in range(paginas):
        p = doc.new_page(width=600, height=800)
        p.insert_text((200, 60), "Chapter 1 Pawn Endgames", fontname="hebo",
                      fontsize=16)
        y = _prosa(p, 60, 100, ["White has the opposition, but it is not enough",
                                "to win, and the whole ending turns on that."])
        _lance(p, 70, y + 4, "1...", "K", "c7! is the only move.")
        _tabuleiro(p, **tabuleiro)
        _prosa(p, 60, 500, ["Since 2.c5 would be useless, the king starts an",
                            "outflanking maneuver. Black replies by getting",
                            "the horizontal opposition."])
    doc.save(caminho)
    doc.close()
    return str(caminho)


def _pagina_de_imagem(caminho, texto_invisivel=False):
    """A digitalização: a página é uma imagem, com ou sem OCR invisível por cima."""
    fonte = fitz.open()
    p = fonte.new_page(width=300, height=200)
    p.insert_text((30, 60), "Uma linha de prosa que foi digitalizada.", fontsize=10)
    pix = p.get_pixmap(dpi=100)
    doc = fitz.open()
    q = doc.new_page(width=300, height=200)
    q.insert_image(q.rect, pixmap=pix)
    if texto_invisivel:
        q.insert_text((30, 60), "Uma linha de prosa que foi digitalizada.",
                      fontsize=10, render_mode=3)
    doc.save(caminho)
    doc.close()
    fonte.close()
    return str(caminho)


def _figuras(pagina):
    return [b for b in pagina.blocos if isinstance(b, livro.Figura)]


def _paragrafos(pagina):
    return [b for b in pagina.blocos if isinstance(b, livro.Paragrafo)]


# ----------------------------------------------------------------------
# A régua
# ----------------------------------------------------------------------

def test_a_regua_aceita_a_camada_tipografica(tmp_path):
    pdf = _livro_digital(tmp_path / "d.pdf")
    [veredito] = pdf_nativo.avaliar(pdf)
    assert veredito.aceita, veredito.motivo
    assert veredito.leitura == pdf_nativo.LEITURA_CAMADA
    assert veredito.caracteres > 100


def test_a_regua_recusa_o_ocr_invisivel_sobre_a_imagem(tmp_path):
    """É a camada do Paper Capture e do ABBYY — e a do nosso PDF pesquisável."""
    [veredito] = pdf_nativo.avaliar(_pagina_de_imagem(tmp_path / "s.pdf", True))
    assert not veredito.aceita
    assert "invisível" in veredito.motivo


def test_a_regua_recusa_a_pagina_sem_texto(tmp_path):
    [veredito] = pdf_nativo.avaliar(_pagina_de_imagem(tmp_path / "s.pdf"))
    assert not veredito.aceita and not veredito.tem_texto
    assert "sem camada" in veredito.motivo


def test_a_regua_recusa_texto_visivel_sobre_a_pagina_inteira_de_imagem(tmp_path):
    caminho = _pagina_de_imagem(tmp_path / "s.pdf")
    doc = fitz.open(caminho)
    doc[0].insert_text((30, 150), "Texto por cima da digitalização inteira.", fontsize=10)
    doc.saveIncr()
    doc.close()
    [veredito] = pdf_nativo.avaliar(caminho)
    assert not veredito.aceita
    assert "digitalização" in veredito.motivo


def test_a_regua_recusa_o_pdf_carimbado_por_ocr(tmp_path):
    caminho = _livro_digital(tmp_path / "d.pdf")
    doc = fitz.open(caminho)
    doc.set_metadata({"producer": "Adobe Acrobat 10.1 Paper Capture Plug-in with ClearScan"})
    doc.saveIncr()
    doc.close()
    [veredito] = pdf_nativo.avaliar(caminho)
    assert not veredito.aceita
    assert "paper capture" in veredito.motivo


def test_a_regua_recusa_a_pagina_girada(tmp_path):
    caminho = _livro_digital(tmp_path / "d.pdf")
    doc = fitz.open(caminho)
    doc[0].set_rotation(90)
    doc.saveIncr()
    doc.close()
    [veredito] = pdf_nativo.avaliar(caminho)
    assert not veredito.aceita and "girada" in veredito.motivo


def test_a_regua_recusa_o_diagrama_numa_fonte_de_xadrez_sem_mapa(tmp_path):
    """Com a fonte desconhecida, as casas virariam texto (`l+*+` na frase): a
    página vai ao OCR, que lê o tabuleiro pela imagem."""
    caminho = _livro_digital(tmp_path / "d.pdf", legenda=())
    doc = fitz.open(caminho)
    pagina = doc[0]
    for i in range(8):
        pagina.insert_text((40, 600 + i * 18), "ABCDEFGH",
                           fontfile=os.path.join(RAIZ, "fonts", "IS-TT-01.TTF"),
                           fontname="isch", fontsize=18)
    doc.saveIncr()
    doc.close()
    [veredito] = pdf_nativo.avaliar(caminho)
    assert not veredito.aceita
    assert "fonte de xadrez sem mapa" in veredito.motivo and "ISChess" in veredito.motivo


def test_as_fontes_do_ocr_de_fabrica_sao_reconhecidas_pelo_nome():
    """O ClearScan dá nomes como `Fd350139`; o Tesseract, `GlyphLessFont`."""
    assert pdf_nativo.fonte_de_ocr("Fd350139")
    assert pdf_nativo.fonte_de_ocr("ABCDEF+Fd543593")
    assert pdf_nativo.fonte_de_ocr("GlyphLessFont")
    assert not pdf_nativo.fonte_de_ocr("TimesNewRomanPSMT")
    assert not pdf_nativo.fonte_de_ocr("Fdisplay")
    assert pdf_nativo.produtor_de_ocr("ABBYY FineReader PDF 15") == "finereader"
    assert pdf_nativo.produtor_de_ocr("PDFill PDF Editor 15.0") is None


# ----------------------------------------------------------------------
# O diagrama composto em fonte
# ----------------------------------------------------------------------

def test_o_diagrama_em_fonte_vira_o_fen_exato(tmp_path):
    pagina = pdf_nativo.extrair(_livro_digital(tmp_path / "d.pdf")).paginas[0]
    [figura] = _figuras(pagina)
    assert figura.fen == f"{FEN} b - - 0 1", "posição ou lado errados"
    assert figura.origem == "render" and figura.png
    assert figura.lado_a_jogar == "b" and figura.lado_origem == "legenda"
    assert figura.orientacao == "branca" and figura.aviso is None
    assert pagina.diagramas == pagina.diagramas_desenhados == 1
    # A caixa do tabuleiro está em pixels a 300 dpi, como a do OCR.
    x0, y0, x1, y1 = figura.caixa
    assert abs(x0 - 220 * 300 / 72) < 3 and abs((x1 - x0) - 160 * 300 / 72) < 5


def test_a_legenda_sai_depois_da_figura_e_os_rotulos_saem_do_texto(tmp_path):
    pagina = pdf_nativo.extrair(_livro_digital(tmp_path / "d.pdf")).paginas[0]
    indice = next(i for i, b in enumerate(pagina.blocos) if isinstance(b, livro.Figura))
    legenda = pagina.blocos[indice + 1]
    assert isinstance(legenda, livro.Paragrafo) and legenda.texto == "1-7 B"
    assert not legenda.titulo and legenda.topo is None
    texto = pagina.texto
    for rotulo in (" a b c ", "8 7 6"):
        assert rotulo not in texto, f"rótulo de casa no texto: {texto!r}"


def test_o_lado_nao_se_le_da_letra_em_outro_idioma(tmp_path):
    """Em português o `B` seria das brancas: a regra do inglês não vale lá."""
    pdf = _livro_digital(tmp_path / "d.pdf")
    [figura] = _figuras(pdf_nativo.extrair(pdf, idioma="pt").paginas[0])
    assert figura.lado_a_jogar is None and figura.lado_origem == "convencao"
    assert figura.fen.split()[1] == "w"


def test_o_lado_da_frase_na_legenda(tmp_path):
    pdf = _livro_digital(tmp_path / "d.pdf", legenda=("Black to play",))
    [figura] = _figuras(pdf_nativo.extrair(pdf).paginas[0])
    assert figura.lado_a_jogar == "b"


def test_o_diagrama_do_lado_das_pretas_e_girado_pelos_rotulos(tmp_path):
    pdf = _livro_digital(tmp_path / "d.pdf", orientacao="preta", legenda=("1-8", "W"))
    [figura] = _figuras(pdf_nativo.extrair(pdf).paginas[0])
    assert figura.orientacao == "preta"
    assert figura.fen == f"{FEN} w - - 0 1", "o FEN é o da posição, não o do desenho"


def test_sem_coordenadas_a_orientacao_e_suposta_e_dita(tmp_path):
    pdf = _livro_digital(tmp_path / "d.pdf", rotulos=False)
    [figura] = _figuras(pdf_nativo.extrair(pdf).paginas[0])
    assert figura.orientacao == "branca"
    assert figura.aviso and "orientação não confirmada" in figura.aviso


def test_o_cabecalho_centrado_acima_do_diagrama_e_titulo(tmp_path):
    pdf = _livro_digital(tmp_path / "d.pdf", cabecalho="H. Neustadtl 1890")
    pagina = pdf_nativo.extrair(pdf).paginas[0]
    indice = next(i for i, b in enumerate(pagina.blocos) if isinstance(b, livro.Figura))
    cabecalho = pagina.blocos[indice - 1]
    assert isinstance(cabecalho, livro.Paragrafo) and cabecalho.titulo
    assert cabecalho.texto == "H. Neustadtl 1890"


def test_o_glifo_de_diagrama_solto_so_fica_no_texto_se_for_peca(tmp_path):
    """A casa vazia solta sairia `+` na frase; a peça solta é figurina."""
    doc = fitz.open()
    p = doc.new_page(width=400, height=300)
    x = 50.0
    for texto, arquivo in (("A stray glyph ", None), ("+", MERIDA),
                           (" and the move ", None), ("k", MERIDA), ("c3 follows.", None)):
        if arquivo:
            p.insert_text((x, 100), texto, fontfile=arquivo, fontname="merida", fontsize=10)
            x += fitz.Font(fontfile=arquivo).text_length(texto, fontsize=10)
        else:
            p.insert_text((x, 100), texto, fontname="helv", fontsize=10)
            x += fitz.get_text_length(texto, fontname="helv", fontsize=10)
    caminho = tmp_path / "solto.pdf"
    doc.save(caminho)
    doc.close()
    [pagina] = pdf_nativo.extrair(str(caminho)).paginas
    assert "+" not in pagina.texto
    assert "the move ♔c3 follows." in pagina.texto


def test_o_cabecalho_do_diagrama_de_baixo_nao_vira_legenda_do_de_cima(tmp_path):
    """Dois diagramas empilhados: o nome centrado entre os dois é do de baixo."""
    doc = fitz.open()
    p = doc.new_page(width=600, height=800)
    _tabuleiro(p, y0=100, legenda=("1-1", "W"))
    _tabuleiro(p, y0=330, legenda=("1-2", "B"), cabecalho="H. Someone 1900")
    caminho = tmp_path / "empilhados.pdf"
    doc.save(caminho)
    doc.close()
    [pagina] = pdf_nativo.extrair(str(caminho)).paginas
    textos = [(b.texto, b.titulo) if isinstance(b, livro.Paragrafo) else "F"
              for b in pagina.blocos]
    assert textos == ["F", ("1-1 W", False), ("H. Someone 1900", True), "F",
                      ("1-2 B", False)]


def test_o_numero_de_pagina_nao_vira_legenda(tmp_path):
    """`37` no pé, debaixo do último diagrama, e `38` no alto da seguinte: os
    dois são fólio — nem legenda desta página, nem religados da outra."""
    doc = fitz.open()
    p = doc.new_page(width=600, height=800)
    _prosa(p, 60, 100, ["Some prose above the diagram, as the book prints it.",
                        "It goes on for another line of prose here."])
    _tabuleiro(p, y0=560, legenda=())
    _centro(p, "37", 300, 775)
    q = doc.new_page(width=600, height=800)
    _centro(q, "38", 300, 40)
    _prosa(q, 60, 110, ["The analysis continues on this page, and it goes on",
                        "for a while."])
    caminho = tmp_path / "folios.pdf"
    doc.save(caminho)
    doc.close()
    primeira, segunda = pdf_nativo.extrair(str(caminho)).paginas
    assert isinstance(primeira.blocos[-1], livro.Figura), "o fólio virou legenda"
    assert primeira.cabecalhos == ["37"] and segunda.cabecalhos == ["38"]
    assert segunda.texto.startswith("The analysis continues")


def test_o_recorte_pedido_sai_do_pdf_com_o_fen(tmp_path):
    pdf = _livro_digital(tmp_path / "d.pdf")
    [figura] = _figuras(pdf_nativo.extrair(pdf, diagramas="recorte").paginas[0])
    assert figura.origem == "recorte" and figura.aviso is None
    assert figura.fen == f"{FEN} b - - 0 1"


def test_a_paridade_das_casas_recusa_um_mapa_errado():
    """Um glifo de casa escura numa casa clara: a grade não é tabuleiro."""
    mapa = pdf_nativo.mapa_de_diagrama("Chess-Merida")
    glifos = []
    for linha in range(8):
        for coluna in range(8):
            clara = (linha + coluna) % 2 == 0
            c = "*" if clara else "+"
            if (linha, coluna) == (0, 0):
                c = "+"            # a8 é clara, e o glifo diz escura
            glifos.append(pdf_nativo._Glifo(c, coluna * 20.0, linha * 20.0,
                                            coluna * 20.0 + 20, linha * 20.0 + 20,
                                            linha * 20.0 + 20, 20.0, "Chess-Merida",
                                            False, (0, linha)))
    assert pdf_nativo._grade(glifos, mapa) is None
    glifos[0].c = "*"
    assert pdf_nativo._grade(glifos, mapa) is not None


def test_o_teclado_da_merida_le_as_duas_casas_vazias_e_as_marcas():
    mapa = pdf_nativo.mapa_de_diagrama("ABCDEF+Chess-Merida")
    assert mapa.casas["*"] == (None, "clara") and mapa.casas[" "] == (None, "clara")
    assert mapa.casas["+"] == (None, "escura")
    assert mapa.casas["l"] == ("k", "clara") and mapa.casas["O"] == ("p", "escura")
    assert mapa.marcas == {"x": "clara", "X": "escura", ".": "clara", ":": "escura"}
    assert pdf_nativo.mapa_de_diagrama("TimesNewRomanPSMT") is None
    # A fonte Symbol traz o teclado na área privada.
    assert pdf_nativo._sem_simbolo(chr(0xF02B)) == "+"


# ----------------------------------------------------------------------
# O texto
# ----------------------------------------------------------------------

def test_a_figurina_da_fonte_de_figurina_vira_unicode(tmp_path):
    pagina = pdf_nativo.extrair(_livro_digital(tmp_path / "d.pdf")).paginas[0]
    assert "1...♔c7! is the only move." in pagina.texto


def test_a_codificacao_chessbase_da_semfig():
    """A chave de símbolos do Dvoretsky (p. 788), no ponto de código da barra."""
    mapa = pdf_nativo.mapa_de_figurina("SemFigNormal")
    assert "".join(mapa.get(c, c) for c in "K§²³µ™…„±∞") == "♔♙⩲⩱∓□Δ⇄±∞"
    assert pdf_nativo.mapa_de_figurina("SkakNew-Figurine")["N"] == "♘"
    assert pdf_nativo.mapa_de_figurina("Helvetica") is None


def test_o_titulo_de_corpo_maior_e_capitulo(tmp_path):
    pagina = pdf_nativo.extrair(_livro_digital(tmp_path / "d.pdf")).paginas[0]
    titulo = pagina.blocos[0]
    assert isinstance(titulo, livro.Paragrafo) and titulo.titulo and titulo.nivel == 1
    assert titulo.texto == "Chapter 1 Pawn Endgames"


def test_o_recuo_abre_paragrafo_e_as_linhas_se_juntam(tmp_path):
    pagina = pdf_nativo.extrair(_livro_digital(tmp_path / "d.pdf")).paginas[0]
    textos = [p.texto for p in _paragrafos(pagina)]
    assert ("White has the opposition, but it is not enough to win, and the whole "
            "ending turns on that.") in textos
    ultimo = next(p for p in _paragrafos(pagina) if p.texto.startswith("Since"))
    segunda = len("Since 2.c5 would be useless, the king starts an ")
    assert ultimo.inicios == [0, segunda, ultimo.texto.index("the horizontal")]
    assert ultimo.topo is not None and ultimo.pe > ultimo.topo
    assert ultimo.registros == [] and ultimo.pesos is None


def _pagina_de_texto(caminho, blocos):
    """`blocos` = [(x, y, texto, fonte, corpo)] — uma linha cada."""
    doc = fitz.open()
    p = doc.new_page(width=400, height=600)
    for x, y, texto, fonte, corpo in blocos:
        p.insert_text((x, y), texto, fontname=fonte, fontsize=corpo)
    doc.save(caminho)
    doc.close()
    return str(caminho)


def test_o_hifen_do_fim_da_linha_fica_sem_dicionario(tmp_path):
    """`f-`+`file` é hífen de verdade: juntar sem ele daria `ffile`."""
    pdf = _pagina_de_texto(tmp_path / "h.pdf", [
        (50, 100, "The rook stands on the open f-", "helv", 10),
        (40, 112, "file, and the king walks to the queenside.", "helv", 10)])
    [pagina] = pdf_nativo.extrair(pdf).paginas
    assert "open f-file, and" in pagina.texto


def test_o_hifen_de_quebra_sai_com_o_dicionario(tmp_path):
    from core.lexico import Lexico

    pdf = _pagina_de_texto(tmp_path / "h.pdf", [
        (50, 100, "The king starts an outflank-", "helv", 10),
        (40, 112, "ing maneuver towards the pawn on the wing.", "helv", 10)])
    lex = Lexico(palavras={"outflanking"})
    [pagina] = pdf_nativo.extrair(pdf, lex=lex).paginas
    assert "an outflanking maneuver" in pagina.texto


def test_o_hifen_brando_junta_sem_espaco():
    """O U+00AD no fim da linha é quebra por definição: some, e sem espaço.

    Montado nas linhas, e não num PDF: a Helvetica de base do PyMuPDF escreve o
    U+00AD pela codificação WinAnsi, e a extração o devolve como `-` comum —
    que é o caso do teste acima, e não este."""
    brando = chr(0xAD)
    primeira = "The king starts an outflank" + brando
    segunda = "ing maneuver, with a mid" + brando + "word break."
    linhas = [pdf_nativo._Linha([], primeira, [True] * len(primeira)),
              pdf_nativo._Linha([], segunda, [False] * len(segunda))]
    texto, negrito, inicios = pdf_nativo._juntar(linhas, None)
    assert texto == "The king starts an outflanking maneuver, with a midword break."
    assert len(negrito) == len(texto)
    assert inicios == [0, texto.index("ing maneuver")]
    assert negrito[texto.index("outflank")] and not negrito[texto.index("ing maneuver")]


def test_o_negrito_da_fonte_vira_trecho(tmp_path):
    fim = 50 + fitz.get_text_length("Key squares", fontname="hebo", fontsize=10)
    pdf = _pagina_de_texto(tmp_path / "n.pdf", [
        (50, 100, "Key squares", "hebo", 10),
        (fim, 100, " are what we call those squares.", "helv", 10)])
    [pagina] = pdf_nativo.extrair(pdf).paginas
    [paragrafo] = _paragrafos(pagina)
    assert paragrafo.negrito == [(0, len("Key squares"))]


def test_a_figurina_herda_o_negrito_do_lance(tmp_path):
    """`1...♔c7!` em negrito com o rei numa fonte de figurina sem negrito: o
    lance inteiro é um trecho só, e não `1...` + `c7!` com o rei de fora."""
    doc = fitz.open()
    p = doc.new_page(width=400, height=300)
    x = 50.0
    for texto, fonte, arquivo in (("1...", "hebo", None), ("K", "fig", FIGURINA),
                                  ("c7! 2.", "hebo", None), ("K", "fig", FIGURINA),
                                  ("a6", "hebo", None)):
        if arquivo:
            p.insert_text((x, 100), texto, fontfile=arquivo, fontname=fonte, fontsize=10)
            x += fitz.Font(fontfile=arquivo).text_length(texto, fontsize=10)
        else:
            p.insert_text((x, 100), texto, fontname=fonte, fontsize=10)
            x += fitz.get_text_length(texto, fontname=fonte, fontsize=10)
    p.insert_text((50, 130), "and the plain text of the analysis follows here.",
                  fontname="helv", fontsize=10)
    caminho = tmp_path / "b.pdf"
    doc.save(caminho)
    doc.close()
    [pagina] = pdf_nativo.extrair(str(caminho)).paginas
    lance = next(p for p in _paragrafos(pagina) if p.texto.startswith("1..."))
    assert lance.texto.startswith("1...♔c7! 2.♔a6")
    assert lance.negrito[0] == (0, len("1...♔c7! 2.♔a6"))


def test_o_paragrafo_inteiro_em_negrito_nao_vira_escada_de_titulos(tmp_path):
    """A definição do Dvoretsky, em negrito itálico, com o primeiro verso
    recuado: a forma de título em cada linha, e é um parágrafo só."""
    pdf = _pagina_de_texto(tmp_path / "n.pdf", [
        (40, 80, "Before the box there is a line of plain text here.", "helv", 10),
        (50, 110, "Key Squares are what we call those", "hebo", 10),
        (40, 122, "squares whose occupation by the king", "hebo", 10),
        (40, 134, "assures victory, regardless of whose", "hebo", 10),
        (40, 146, "turn it is to move.", "hebo", 10)])
    [pagina] = pdf_nativo.extrair(pdf).paginas
    assert not any(p.titulo for p in _paragrafos(pagina))
    assert any(p.texto.startswith("Key Squares are what we call those squares whose")
               for p in _paragrafos(pagina))


def test_o_titulo_de_secao_em_duas_linhas_centradas_e_um_so(tmp_path):
    cheia = "Plain body text that fills the whole column width, as usual."
    corpo = [(40, 80 + 12 * i, cheia, "helv", 10) for i in range(3)]
    largura = fitz.get_text_length(cheia, fontname="helv", fontsize=10)
    titulo = [("The Rook Is in Front of the Pawn and", 140),
              ("the Pawn Is on the Seventh Rank", 152)]
    linhas = corpo + [
        (40 + (largura - fitz.get_text_length(t, fontname="hebo", fontsize=10)) / 2,
         y, t, "hebo", 10) for t, y in titulo]
    linhas += [(50, 180, "Now the body text of the new section starts here,", "helv", 10),
               (40, 192, "and it goes on for a while in the column.", "helv", 10)]
    pdf = _pagina_de_texto(tmp_path / "t.pdf", linhas)
    [pagina] = pdf_nativo.extrair(pdf).paginas
    titulos = [p.texto for p in _paragrafos(pagina) if p.titulo]
    assert titulos == ["The Rook Is in Front of the Pawn and the Pawn Is on the Seventh Rank"]


# ----------------------------------------------------------------------
# O livro inteiro
# ----------------------------------------------------------------------

def test_a_legenda_que_a_paginacao_separou_volta_ao_diagrama(tmp_path):
    """O `16-2`/`B` no alto da página seguinte é do último diagrama desta."""
    doc = fitz.open()
    p = doc.new_page(width=600, height=800)
    _prosa(p, 60, 100, ["Some text above the diagram, as the book prints it.",
                        "It goes on for another line of prose here."])
    _tabuleiro(p, y0=560, legenda=())
    q = doc.new_page(width=600, height=800)
    _centro(q, "16-2", 300, 60)
    _centro(q, "B", 300, 72)
    _prosa(q, 60, 110, ["The analysis of the diagram starts on this page, and it",
                        "continues for a while."])
    caminho = tmp_path / "p.pdf"
    doc.save(caminho)
    doc.close()

    extracao = pdf_nativo.extrair(str(caminho))
    primeira, segunda = extracao.paginas
    assert isinstance(primeira.blocos[-1], livro.Paragrafo)
    assert primeira.blocos[-1].texto == "16-2 B"
    [figura] = _figuras(primeira)
    assert figura.lado_a_jogar == "b" and figura.fen.split()[1] == "b"
    assert not segunda.texto.startswith("16-2")


def test_o_numero_de_pagina_solto_sai_e_o_ano_do_fim_do_paragrafo_fica(tmp_path):
    doc = fitz.open()
    for numero in (11, 12, 13):
        p = doc.new_page(width=400, height=600)
        _prosa(p, 40, 80, ["A paragraph of prose that fills a whole line of the",
                           "column and finishes in the year", "2019."])
        _centro(p, str(numero), 200, 570)
    caminho = tmp_path / "f.pdf"
    doc.save(caminho)
    doc.close()
    paginas = pdf_nativo.extrair(str(caminho)).paginas
    for pagina, numero in zip(paginas, (11, 12, 13)):
        assert pagina.cabecalhos == [str(numero)]
        assert pagina.texto.endswith("finishes in the year 2019.")


def test_o_cabecalho_corrente_solto_e_repetido_sai(tmp_path):
    doc = fitz.open()
    for _ in range(3):
        p = doc.new_page(width=400, height=600)
        _centro(p, "Pawn Endgames", 200, 40, corpo=8)
        _prosa(p, 40, 90, ["A paragraph of prose that fills a whole line of the",
                           "column."])
    caminho = tmp_path / "c.pdf"
    doc.save(caminho)
    doc.close()
    paginas = pdf_nativo.extrair(str(caminho)).paginas
    assert all(p.cabecalhos == ["Pawn Endgames"] for p in paginas)
    assert all("Pawn Endgames" not in p.texto for p in paginas)


def test_a_extracao_diz_o_que_deixou_para_o_ocr(tmp_path):
    digital = _livro_digital(tmp_path / "d.pdf")
    scan = _pagina_de_imagem(tmp_path / "s.pdf", True)
    doc = fitz.open(digital)
    doc.insert_pdf(fitz.open(scan))
    misto = tmp_path / "m.pdf"
    doc.save(misto)
    doc.close()
    extracao = pdf_nativo.extrair(str(misto))
    assert [p.numero for p in extracao.paginas] == [0]
    assert [v.numero for v in extracao.recusadas] == [1]
    assert "1 de 2 página(s) lidas da camada" in extracao.resumo()
    # Forçar lê da camada o que tem texto — inclusive o OCR invisível.
    forcada = pdf_nativo.extrair(str(misto), forcar=True)
    assert [p.numero for p in forcada.paginas] == [0, 1]


def _classificar(_recorte, _referencia=None):
    return ("a", 0.99)


def test_o_livro_escolhe_o_caminho_por_pagina(tmp_path):
    digital = _livro_digital(tmp_path / "d.pdf")
    doc = fitz.open(digital)
    doc.insert_pdf(fitz.open(_pagina_de_imagem(tmp_path / "s.pdf")))
    misto = tmp_path / "m.pdf"
    doc.save(misto)
    doc.close()

    auto = livro.extrair(str(misto), _classificar, diagramas="recorte", camada="auto")
    assert [p.leitura for p in auto] == ["camada", "imagem"]
    assert pdf_nativo.contar_leituras(auto) == {"camada": 1, "imagem": 1}
    [figura] = _figuras(auto[0])
    assert figura.fen == f"{FEN} b - - 0 1"

    nunca = livro.extrair(str(misto), _classificar, diagramas="recorte")
    assert [p.leitura for p in nunca] == ["imagem", "imagem"], \
        "o padrão da API mudou: os instrumentos do OCR passariam a medir a camada"

    with pytest.raises(ValueError):
        livro.extrair(str(misto), _classificar, camada="talvez")


def test_a_pagina_da_camada_vai_e_volta_pelo_documento_editorial(tmp_path):
    pdf = _livro_digital(tmp_path / "d.pdf", legenda=("1-7", "B"))
    pagina = pdf_nativo.extrair(pdf).paginas[0]
    figura = _figuras(pagina)[0]
    figura.marcas = ["c6", "d6"]
    editorial = pagina_extraida_para_pagina(pagina, document_id="dv")
    assert editorial.observations["legacy_page"]["leitura"] == "camada"
    assert all(e.engine == "pdf_text" for e in editorial.evidence)
    assert all(b.decision.status == "automatic" for b in editorial.blocks), \
        "a página da camada não tem o que revisar"
    volta = pagina_editorial_para_extraida(editorial)
    assert volta.leitura == "camada"
    assert _figuras(volta)[0].marcas == ["c6", "d6"]
    assert _figuras(volta)[0].fen == figura.fen


def test_as_marcas_chegam_ao_diagrama_do_editor(tmp_path):
    from core.editor import importar_ir
    from core.editor.modelo import Diagrama

    pagina = pdf_nativo.extrair(_livro_digital(tmp_path / "d.pdf")).paginas[0]
    _figuras(pagina)[0].marcas = ["c6", "z9"]
    livro_do_editor, _relatorio = importar_ir.de_paginas([pagina], titulo="Prova")
    diagramas = [b for cap in livro_do_editor.capitulos for b in cap.blocos
                 if isinstance(b, Diagrama)]
    assert diagramas and diagramas[0].marcas == ["c6"]


# ----------------------------------------------------------------------
# A caixa de exportação
# ----------------------------------------------------------------------

def test_a_opcao_da_camada_vem_ligada_e_e_lembrada():
    from ui.dialogo_de_exportacao import OpcoesDeExportacao

    assert OpcoesDeExportacao().ler_camada is True
    assert OpcoesDeExportacao().camada == "auto"
    assert OpcoesDeExportacao(ler_camada=False).camada == "nunca"
    assert OpcoesDeExportacao.de_settings({"ler_camada": False}).ler_camada is False
    assert OpcoesDeExportacao.de_settings({"ler_camada": "sim"}).ler_camada is True
    assert "ler_camada" in OpcoesDeExportacao().para_settings()


def test_a_caixa_mostra_a_amostra_e_devolve_a_escolha(tmp_path):
    from conftest import raiz_tk
    from ui.dialogo_de_exportacao import DialogoDeExportacao

    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        for amostra, trecho in (((3, 40), "aceitou 3 de 40"),
                                ((0, 40), "Nenhuma das 40"), (None, "OCR de sempre")):
            caixa = DialogoDeExportacao(raiz, entrada=str(tmp_path / "livro.pdf"),
                                        total_paginas=40, camada=amostra)
            caixa._construir()
            assert trecho in caixa.lbl_camada.cget("text")
            opcoes, _erro = caixa._montar()
            assert opcoes.ler_camada is True
            caixa.var_camada.set(False)
            opcoes, _erro = caixa._montar()
            assert opcoes.ler_camada is False and opcoes.camada == "nunca"
            caixa.top.destroy()
    finally:
        raiz.destroy()


def test_a_exportacao_pela_janela_le_a_camada_e_diz_no_relatorio(tmp_path):
    """A ação de menu inteira, com a opção ligada: o EPUB sai da camada, e a
    caixa do fim diz que nenhuma página passou pelo OCR."""
    import zipfile

    from tests.test_f26_livro import _App

    entrada = _livro_digital(tmp_path / "digital.pdf")
    saida = str(tmp_path / "digital.epub")
    with _App(entrada, saida, respostas={"Camada": True}) as app:
        recebido = {}
        original = app.win.DIALOGO_DE_EXPORTACAO.__init__

        def __init__(self, _parent, **kw):
            recebido.update(kw)
            original(self, _parent, **kw)

        app.win.DIALOGO_DE_EXPORTACAO.__init__ = __init__
        app.rodar()
        assert not app.erros, app.erros
        assert recebido["camada"] == (1, 1), "a caixa não recebeu a amostra da régua"
        relatorio = "\n".join(app.avisos)
        assert "Páginas lidas da camada do PDF: 1 de 1" in relatorio
        assert "nenhuma página passou pelo OCR" in relatorio
        with zipfile.ZipFile(saida) as z:
            paginas = [z.read(n).decode("utf-8") for n in z.namelist()
                       if n.startswith("OEBPS/pagina-")]
        assert any("♔" in p and FEN in p for p in paginas)


def test_a_amostra_da_regua(tmp_path):
    assert pdf_nativo.amostrar(_livro_digital(tmp_path / "d.pdf", paginas=3)) == (3, 3)
    assert pdf_nativo.amostrar(_pagina_de_imagem(tmp_path / "s.pdf", True)) == (0, 1)


# ----------------------------------------------------------------------
# Os livros de verdade, quando estão na máquina
# ----------------------------------------------------------------------

def _pdf_do_corpus(padrao):
    achados = sorted(glob.glob(os.path.join(RAIZ, "PDF", padrao)))
    if not achados:
        pytest.skip(f"PDF do corpus ausente: {padrao}")
    return achados[0]


@pytest.fixture(scope="module")
def dvoretsky():
    return _pdf_do_corpus("Dvoretsky*/*.pdf")


def test_dvoretsky_diagrama_1_7(dvoretsky):
    """p. 21 do livro: `8/1k6/1p6/1K6/P1P5` com as pretas a jogar (`B`)."""
    [pagina] = pdf_nativo.extrair(dvoretsky, [20], idioma="en").paginas
    [figura] = _figuras(pagina)
    assert figura.fen == "8/1k6/1p6/1K6/P1P5/8/8/8 b - - 0 1"
    assert "1...♔c7!" in pagina.texto and "5.♔c5⨀+–" in pagina.texto
    assert pagina.colunas == 2


def test_dvoretsky_a_legenda_que_passa_para_a_outra_coluna(dvoretsky):
    """p. 22: o `1-8` fecha a coluna da esquerda e o `W?` abre a da direita."""
    [pagina] = pdf_nativo.extrair(dvoretsky, [21], idioma="en").paginas
    primeira = _figuras(pagina)[0]
    indice = pagina.blocos.index(primeira)
    assert pagina.blocos[indice - 1].texto == "H. Neustadtl 1890"
    assert pagina.blocos[indice + 1].texto == "1-8 W?"
    assert primeira.fen == "8/8/8/4p1p1/8/5P2/6K1/3k4 w - - 0 1"


def test_dvoretsky_dois_diagramas_lado_a_lado(dvoretsky):
    """p. 783: cada legenda com o seu tabuleiro, e não as duas no segundo."""
    [pagina] = pdf_nativo.extrair(dvoretsky, [782], idioma="en").paginas
    legendas = [pagina.blocos[pagina.blocos.index(f) + 1].texto for f in _figuras(pagina)]
    assert legendas == ["15-117 15/41 W? Play", "16-127 B"]
    assert [f.lado_a_jogar for f in _figuras(pagina)] == ["w", "b"]


def test_dvoretsky_o_capitulo_e_o_titulo_de_secao(dvoretsky):
    paginas = pdf_nativo.extrair(dvoretsky, [16, 45], idioma="en").paginas
    titulos = [(b.nivel, b.texto) for p in paginas for b in _paragrafos(p) if b.titulo]
    assert (1, "Chapter 1 Pawn Endgames") in titulos
    assert (2, "The Rule of the Square") in titulos or any(
        "The Rule of the Square" in t for _n, t in titulos)


@pytest.mark.parametrize("padrao,pagina", [
    ("*Yusupov*Evolution*editable/*editable.pdf", 34),
    ("Nunn*/*.pdf", 237),
    ("Jacob*/*.pdf", 30),
    ("Darcy*/*.pdf", 30),
])
def test_a_regua_recusa_as_digitalizacoes_do_corpus(padrao, pagina):
    """As páginas de referência do A/B continuam indo ao OCR."""
    [veredito] = pdf_nativo.avaliar(_pdf_do_corpus(padrao), [pagina])
    assert not veredito.aceita, veredito
