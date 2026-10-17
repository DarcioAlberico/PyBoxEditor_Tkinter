"""
A camada de texto dos livros e newsletters da Quality Chess (o Odds & Ends, 2012).

O leitor da camada (`core/pdf_nativo.py`) foi medido no Dvoretsky: uma coluna
alinhada à esquerda, figurinas na `SemFig`, diagramas na Merida. As newsletters
da Quality Chess são outra tipografia, e cada teste aqui é um defeito que a
exportação delas mostrou:

- as figurinas na codificação "SP" do ChessBase (`¤` é o cavalo) saíam cruas;
- a calha de 14 pt entre as duas colunas (1,3 corpo) juntava as duas linhas
  da mesma altura numa só;
- o título centrado em cima das colunas saía no meio delas;
- a linha principal em negrito e o comentário em redondo viravam um parágrafo;
- o cabeçalho corrente em dois pedaços (`Games` · `7`) ficava no texto;
- o diagrama sem legenda saía com as brancas a jogar por convenção, quando o
  lance de antes dele diz de quem é a vez;
- a frase que a paginação parte virava dois parágrafos;
- a fonte de diagrama "TT" do ChessBase não tinha mapa.

Os PDFs de prova são montados com o PyMuPDF, em Helvetica.
"""

import fitz
import pytest

from core import lado_a_jogar, pdf_nativo
from core.pagina import Figura, PaginaExtraida, Paragrafo

CORPO = 11.0

#: Palavras para encher linhas de coluna sem pontuação de fim no meio.
PALAVRAS = ("white keeps a small edge because the knight on d5 is strong and the "
            "black bishop has no good square left on the long diagonal").split()


def _linhas_de_coluna(n, largura, fonte="helv"):
    """`n` linhas que enchem `largura` pontos, sem ponto final."""
    linhas, atual, k = [], [], 0
    while len(linhas) < n:
        palavra = PALAVRAS[k % len(PALAVRAS)]
        k += 1
        tentativa = " ".join(atual + [palavra])
        if fitz.get_text_length(tentativa, fontname=fonte, fontsize=CORPO) > largura:
            linhas.append(" ".join(atual))
            atual = [palavra]
        else:
            atual.append(palavra)
    return linhas


def _duas_colunas(caminho, *, titulo="", cabecalho=None):
    """Duas colunas de 12 linhas, calha de 14 pt, as linhas na mesma altura; a
    da direita em maiúsculas, para se saber de que coluna é cada palavra."""
    doc = fitz.open()
    p = doc.new_page(width=480, height=680)
    if cabecalho:
        texto, folio = cabecalho
        largura = fitz.get_text_length(texto, fontname="helv", fontsize=CORPO)
        p.insert_text((240 - largura / 2, 40), texto, fontname="helv", fontsize=CORPO)
        p.insert_text((430, 40), folio, fontname="helv", fontsize=CORPO)
    y = 90.0
    if titulo:
        largura = fitz.get_text_length(titulo, fontname="hebo", fontsize=26)
        p.insert_text((240 - largura / 2, y), titulo, fontname="hebo", fontsize=26)
        y += 40
    esquerda = _linhas_de_coluna(12, 190)
    direita = [linha.upper() for linha in _linhas_de_coluna(12, 150)]
    for i in range(12):
        p.insert_text((40, y + i * 14), esquerda[i], fontname="helv", fontsize=CORPO)
        p.insert_text((244, y + i * 14), direita[i], fontname="helv", fontsize=CORPO)
    doc.save(caminho)
    doc.close()
    return str(caminho), esquerda, direita


# ----------------------------------------------------------------------
# Figurinas SP
# ----------------------------------------------------------------------

def test_a_codificacao_sp_do_chessbase():
    """A chave da Quality Chess, conferida glifo a glifo no Odds & Ends."""
    mapa = pdf_nativo.mapa_de_figurina("NWIXHN+SPTimeFig-Roman")
    assert "".join(mapa.get(c, c) for c in "¢£¦¥¤²³µ©÷„…™") == "♔♕♖♗♘⩲⩱∓⯹∞⇄Δ□"
    assert pdf_nativo.mapa_de_figurina("SPAriesFig-Bold")["¤"] == "♘"
    assert pdf_nativo.mapa_de_figurina("FigurineCB TimeSP,Bold")["¥"] == "♗"


def test_a_figurinecb_nao_troca_letra_por_peca():
    """No PDF que o ChessBase imprime, o texto corrido inteiro está na
    FigurineCB: o `B` de `Black` é letra."""
    mapa = pdf_nativo.mapa_de_figurina("FigurineCB TimeSP")
    assert "B" not in mapa and "K" not in mapa


# ----------------------------------------------------------------------
# Colunas, título e cabeçalho
# ----------------------------------------------------------------------

def test_a_calha_estreita_nao_junta_as_duas_colunas(tmp_path):
    caminho, esquerda, direita = _duas_colunas(tmp_path / "c.pdf")
    [pagina] = pdf_nativo.extrair(caminho).paginas
    textos = [b.texto for b in pagina.blocos if isinstance(b, Paragrafo)]
    assert pagina.colunas == 2
    # Nenhum parágrafo mistura as duas colunas (a da direita está em
    # maiúsculas), e a coluna da esquerda vem inteira antes da da direita.
    juntos = " ".join(textos)
    assert " ".join(esquerda) in juntos and " ".join(direita) in juntos
    assert juntos.index(esquerda[-1]) < juntos.index(direita[0])
    assert not any(t != t.upper() and t != t.lower() for t in textos)


def test_o_titulo_que_atravessa_as_colunas_vem_antes_delas(tmp_path):
    caminho, esquerda, _direita = _duas_colunas(tmp_path / "t.pdf", titulo="Games")
    [pagina] = pdf_nativo.extrair(caminho).paginas
    textos = [b.texto for b in pagina.blocos if isinstance(b, Paragrafo)]
    assert textos[0] == "Games"


def test_o_cabecalho_em_dois_pedacos_sai_com_o_numero(tmp_path):
    """`Games` no meio e `7` no canto: uma página só, sem repetição."""
    caminho, esquerda, _direita = _duas_colunas(tmp_path / "h.pdf", cabecalho=("Games", "7"))
    [pagina] = pdf_nativo.extrair(caminho).paginas
    textos = [b.texto for b in pagina.blocos if isinstance(b, Paragrafo)]
    assert "Games" not in textos and "7" not in textos
    assert sorted(pagina.cabecalhos) == ["7", "Games"]


def test_a_troca_de_peso_abre_paragrafo(tmp_path):
    """A linha principal em negrito e o comentário em redondo, sem recuo."""
    doc = fitz.open()
    p = doc.new_page(width=480, height=680)
    p.insert_text((40, 100), "15.fxe5 Bxg2 16.Kxg2 Qe2+ 17.Nf2 Nxe4", fontname="helv",
                  fontsize=CORPO)
    p.insert_text((40, 114), "18.Qd4! would have won a piece.", fontname="helv", fontsize=CORPO)
    p.insert_text((40, 128), "15...Qxh3 16.Nf2 Qh5 17.fxe5 Bxe5 18.d4", fontname="hebo",
                  fontsize=CORPO)
    for i, texto in enumerate(["The rest of the game is a long story and it is",
                               "told in the next paragraph of the newsletter."]):
        p.insert_text((40, 160 + i * 14), texto, fontname="helv", fontsize=CORPO)
    caminho = tmp_path / "peso.pdf"
    doc.save(caminho)
    doc.close()
    [pagina] = pdf_nativo.extrair(str(caminho)).paginas
    textos = [b.texto for b in pagina.blocos if isinstance(b, Paragrafo)]
    assert "15...Qxh3 16.Nf2 Qh5 17.fxe5 Bxe5 18.d4" in textos
    assert any(t.endswith("would have won a piece.") for t in textos)


# ----------------------------------------------------------------------
# O lado a jogar pelo lance
# ----------------------------------------------------------------------

#: A posição depois de 10.♘xc4 (e também depois de 8...♕h5 9.♘xc4 ♘bd5 10.e4 ♘b6).
FEN_SREEVES = "r1b1kb1r/pp2pppp/1np2n2/7q/2N1P3/6P1/PPQP1PBP/R1B1NRK1 w - - 0 1"
#: Depois de 13.♕b3 0–0–0.
FEN_DO_ROQUE = "2kr1b1r/pp2pppp/2p2n2/7q/4P1b1/1Q3NP1/PP1P1PBP/R1B2RK1 w - - 0 1"


@pytest.mark.parametrize("texto, fen, esperado", [
    ("9.e4 ♕h5 10.♘xc4", FEN_SREEVES, "b"),
    ("8...♕h5 9.♘xc4 ♘bd5 10.e4 ♘b6", FEN_SREEVES, "w"),
    ("11.♘f3 ♘xc4 12.♕xc4 ♗g4 12...e6!? 13.♕b3 0–0–0", FEN_DO_ROQUE, "w"),
    ("Sreeves lost faith in the recommendation of 13.♕b3, as the best move,",
     FEN_DO_ROQUE, "b"),
    ("23.Nxd8, when he is ready to take on b6", "1k1N1r2/8/8/8/8/8/8/6K1 w - - 0 1", "b"),
    # O lance não confere com o tabuleiro: não se diz nada.
    ("10.♘xd4", FEN_SREEVES, None),
    ("A position without any move.", FEN_SREEVES, None),
])
def test_o_lado_pelo_ultimo_lance_conferido_no_tabuleiro(texto, fen, esperado):
    assert lado_a_jogar.pelo_lance(texto, fen) == esperado


@pytest.mark.parametrize("texto, seguinte, esperado", [
    ("9.e4 ♕h5 10.♘xc4", "10...♗h3?!", "b"),
    ("8...♕h5 9.♘xc4 ♘bd5 10.e4 ♘b6", "11.♘d3", "w"),
    # O exemplo seguinte recomeça a numeração: o lance de antes não é dele.
    ("9.e4 ♕h5 10.♘xc4", "White to move wins: 1.a5! ♔g7", None),
    ("9.e4 ♕h5 10.♘xc4", "11.♘e3", None),
    ("9.e4 ♕h5 10.♘xc4", "A comment without moves.", None),
])
def test_o_texto_depois_do_diagrama_tem_de_continuar(texto, seguinte, esperado):
    assert lado_a_jogar.pelo_lance(texto, FEN_SREEVES, seguinte) == esperado


def _figura(fen):
    return Figura(png=b"", largura=1, altura=1, fen=fen, origem="recorte")


def test_a_passada_de_livro_usa_o_lance_da_pagina_anterior():
    """O diagrama que abre a página mostra a posição do fim da anterior; o
    parágrafo de variante mais perto não confere, e o anterior a ele sim."""
    antes = PaginaExtraida(numero=5, blocos=[
        Paragrafo("11.♘f3 ♘xc4 12.♕xc4 ♗g4 13.♕b3 0–0–0"),
        Paragrafo("13.♕a4 ♔b8 14.♕c2"),
    ])
    figura = _figura(FEN_DO_ROQUE)
    depois = PaginaExtraida(numero=6, blocos=[figura, Paragrafo("14.♖e1?!")])
    assert pdf_nativo.lados_pelos_lances([antes, depois]) == 1
    assert figura.fen.split()[1] == "w" and figura.lado_origem == "lance"


def test_a_figura_com_lado_lido_nao_muda():
    figura = _figura(FEN_SREEVES)
    figura.lado_origem = "legenda"
    pagina = PaginaExtraida(numero=1, blocos=[Paragrafo("9.e4 ♕h5 10.♘xc4"), figura,
                                              Paragrafo("10...♗h3?!")])
    assert pdf_nativo.lados_pelos_lances([pagina]) == 0
    assert figura.fen == FEN_SREEVES


# ----------------------------------------------------------------------
# O parágrafo que a paginação partiu
# ----------------------------------------------------------------------

def test_a_frase_partida_entre_paginas_volta_a_ser_uma():
    a = PaginaExtraida(numero=7, blocos=[Paragrafo("a game by Dutch GM Reinderman, who clearly",
                                                   negrito=[(12, 17)])])
    b = PaginaExtraida(numero=8, blocos=[Paragrafo("has read the GM Repertoire books.",
                                                   negrito=[(0, 3)]),
                                         Paragrafo("1.c4 e5")])
    assert pdf_nativo.juntar_entre_paginas([a, b]) == 1
    [junto] = a.blocos
    assert junto.texto == ("a game by Dutch GM Reinderman, who clearly "
                           "has read the GM Repertoire books.")
    assert junto.negrito == [(12, 17), (43, 46)]
    assert [p.texto for p in b.blocos] == ["1.c4 e5"]


@pytest.mark.parametrize("fim, comeco", [
    ("The game ended in a draw.", "after that he left"),
    ("who clearly", "Black resigned."),
    ("a well-", "known idea"),
])
def test_nao_junta_o_que_nao_e_continuacao(fim, comeco):
    a = PaginaExtraida(numero=1, blocos=[Paragrafo(fim)])
    b = PaginaExtraida(numero=2, blocos=[Paragrafo(comeco)])
    assert pdf_nativo.juntar_entre_paginas([a, b]) == 0


# ----------------------------------------------------------------------
# A fonte de diagrama TT do ChessBase
# ----------------------------------------------------------------------

def _glifo(c, coluna, fila, largura=18.0, altura=19.5, zero=False):
    x0 = 100 + coluna * largura
    y0 = 200 + fila * altura
    return pdf_nativo._Glifo(c, x0, y0, x0 if zero else x0 + largura, y0 + 18,
                             y0 + 14, 18.0, "DiagramTTFritz", False, (0, fila))


def test_o_teclado_tt_le_a_peca_sobre_o_fundo_escuro():
    """Fila de cima `r+-+-trk+` (o fundo `t` sob a torre de f8) e as outras
    vazias; a entrelinha de 19,5 pt com casas de 18."""
    mapa = pdf_nativo.mapa_de_diagrama("DiagramTTFritz")
    glifos = []
    oitava = ["r", "+", "-", "+", "-", ("t", "r"), "k", "+"]
    for coluna, casa in enumerate(oitava):
        if isinstance(casa, tuple):
            glifos.append(_glifo(casa[0], coluna, 0, zero=True))
            glifos.append(_glifo(casa[1], coluna, 0))
        else:
            glifos.append(_glifo(casa, coluna, 0))
    for fila in range(1, 8):
        for coluna in range(8):
            glifos.append(_glifo("-" if (fila + coluna) % 2 == 0 else "+", coluna, fila))
    tabuleiro = pdf_nativo._grade(glifos, mapa)
    assert tabuleiro is not None
    assert tabuleiro.impresso[0] == ["r", None, None, None, None, "r", "k", None]


def test_o_teclado_tt_recusa_a_paridade_errada():
    """O rei preto sem o fundo numa casa escura: o mapa não confere."""
    mapa = pdf_nativo.mapa_de_diagrama("DiagramTTFritz")
    glifos = [_glifo("-" if (f + c) % 2 == 0 else "+", c, f) for f in range(8) for c in range(8)]
    glifos[1] = _glifo("k", 1, 0)
    assert pdf_nativo._grade(glifos, mapa) is None


def test_o_sinal_da_fonte_tt_no_texto_continua_texto():
    """O `+-` da avaliação composto na DiagramTTFritz não vira peça nem some."""
    g = _glifo("+", 0, 0)
    assert pdf_nativo._solto_e_texto(g)
    assert pdf_nativo._caractere(g) == "+"
    assert pdf_nativo._caractere(_glifo("l", 0, 0)) == "l"


# ----------------------------------------------------------------------
# Os achados da revisão de código
# ----------------------------------------------------------------------

def test_o_n_de_novidade_nao_e_promocao():
    fen = "4k3/8/8/3p4/8/8/8/4K3 w - - 0 1"
    assert lado_a_jogar.pelo_lance("16...d5N", fen, "17.e4") == "w"
    assert lado_a_jogar.pelo_lance("16. ...d5", fen, "17.e4") == "w"
    assert lado_a_jogar.pelo_lance("40.b8=Q", "1Q2k3/8/8/8/8/8/8/4K3 w - - 0 1") == "b"


def test_fen_vazio_nao_quebra():
    assert lado_a_jogar.pelo_lance("10.♘xc4", "   ") is None


def test_pagina_que_falha_vai_ao_ocr_e_o_livro_continua(tmp_path, monkeypatch):
    caminho, _esquerda, _direita = _duas_colunas(tmp_path / "f.pdf")
    original = pdf_nativo.extrair_pagina

    def quebra(page, **kw):
        raise IndexError("defeito de teste")

    monkeypatch.setattr(pdf_nativo, "extrair_pagina", quebra)
    extracao = pdf_nativo.extrair(caminho)
    assert extracao.paginas == []
    [veredito] = extracao.vereditos
    assert not veredito.aceita and "falhou" in veredito.motivo
    monkeypatch.setattr(pdf_nativo, "extrair_pagina", original)


def test_o_fundo_casa_com_a_peca_mesmo_um_pouco_deslocado():
    mapa = pdf_nativo.mapa_de_diagrama("DiagramTTFritz")
    fundo = _glifo("w", 2, 0, zero=True)
    peca = _glifo("q", 2, 0)
    peca.x0 += 0.3
    [junto] = pdf_nativo._juntar_fundos([fundo, peca], mapa)
    assert junto.c == "wq"


def test_juntar_com_espaco_a_esquerda_desloca_as_marcas_certo():
    a = PaginaExtraida(numero=1, blocos=[Paragrafo("who clearly")])
    b = PaginaExtraida(numero=2, blocos=[Paragrafo("  has read", negrito=[(2, 5)])])
    assert pdf_nativo.juntar_entre_paginas([a, b]) == 1
    [junto] = a.blocos
    assert junto.texto == "who clearly has read"
    a0, z0 = junto.negrito[0]
    assert junto.texto[a0:z0] == "has"


def test_figurinecb_sem_sp_nao_e_sp():
    assert pdf_nativo.mapa_de_figurina("FigurineCB Times") is pdf_nativo.FIGURINAS_SIMPLES
