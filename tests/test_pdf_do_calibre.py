"""
O PDF que o calibre faz de um ePub de xadrez — o Khenkin de 2012.

`1000 Checkmate Combinations` chega como PDF nascido digital (CharisSIL de
verdade, nada invisível, nenhum carimbo de OCR), e a régua da F110 o aceitava
inteiro. Três coisas dele não estão onde a camada as procura:

  - **a figurina é imagem** no meio da frase, e a camada lia `1 … xd4!` onde o
    livro imprime `1 … ♘xd4!`. A régua recusa a página (`_imagens_na_linha`);
  - **a ligadura não tem Unicode** (o ToUnicode do calibre não a mapeia), e a
    camada lia `battle�eld`. O nome do glifo na fonte embutida diz a letra
    (`f_i`), e o que o nome não disser recusa a página;
  - **a moldura do diagrama sai partida** na binária do OCR (a imagem
    reamostrada tem uma linha cinza nas divisas das filas), e o tabuleiro
    virava parágrafo. `diagrama._de_moldura_partida` o acha pelas faixas.

E dois que apareciam junto: a linha de prosa colada em cima do tabuleiro
perdia as letras que descem (`j gy` virava o título do diagrama), e a imagem
com quatro recortes de canto de tabuleiro (p. 21), que não é diagrama, virava
seis parágrafos de figurinas soltas — agora sai como figura
(`livro._imagens_do_pdf`), só onde a camada é tipografia. A imagem do PDF que
o detector da F96 reconhece como tabuleiro vira diagrama (`livro.
_tabuleiros_das_imagens`) — o terceiro da p. 60, de moldura partida em toda
divisa, que nenhuma outra pista achava.

Os testes montam os casos com o PyMuPDF e com numpy; os do fim rodam sobre o
PDF do Khenkin quando ele está na máquina (`KHENKIN_PDF`, ou uma pasta
`Khenkin*` em `PDF/` ou em `../HTML_to_EPUB/`).
"""

import glob
import io
import os
import re

import cv2
import fitz
import numpy as np
import pytest

from core import deteccao_de_tabuleiro as det
from core import diagrama as diag
from core import livro, pdf_nativo
from core.box_model import BoxEntry

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ----------------------------------------------------------------------
# A ligadura sem Unicode
# ----------------------------------------------------------------------

@pytest.mark.parametrize("nome,texto", [
    ("f_i", "fi"), ("f_i.SlantItalic", "fi"), ("f_f_l", "ffl"), ("f_f", "ff"),
    ("fi", "fi"), ("uniFB01", "fi"), ("uni00660069", "fi"), ("A", "A"),
])
def test_o_nome_do_glifo_diz_a_letra(nome, texto):
    pytest.importorskip("fontTools")
    assert pdf_nativo.texto_do_nome_de_glifo(nome) == texto


@pytest.mark.parametrize("nome", ["glyph00633", ".notdef", "", "f_foo", "xyz"])
def test_o_nome_que_nao_diz_nada_nao_vira_meia_palavra(nome):
    assert pdf_nativo.texto_do_nome_de_glifo(nome) is None


def _fonte_com_ligadura(nome_da_ligadura: str) -> bytes:
    """Uma TrueType mínima: as letras de `battlefield` e a ligadura `fi`."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    letras = "batlefid"
    nomes = [".notdef", "space"] + list(letras) + [nome_da_ligadura]
    mapa = {32: "space", 0xFB01: nome_da_ligadura}
    mapa.update({ord(c): c for c in letras})
    glifos = {}
    for nome in nomes:
        pen = TTGlyphPen(None)
        if nome not in (".notdef", "space"):
            pen.moveTo((50, 0))
            pen.lineTo((50, 700))
            pen.lineTo((550, 700))
            pen.lineTo((550, 0))
            pen.closePath()
        glifos[nome] = pen.glyph()
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(nomes)
    fb.setupCharacterMap(mapa)
    fb.setupGlyf(glifos)
    fb.setupHorizontalMetrics({n: (600, 50) for n in nomes})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Prova", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost(keepGlyphNames=True)
    saida = io.BytesIO()
    fb.save(saida)
    return saida.getvalue()


def _pdf_sem_unicode_na_ligadura(caminho, nome_da_ligadura="f_i"):
    """A prosa com a ligadura `fi`, e o ToUnicode sem a linha dela — o que o
    calibre escreveu no Khenkin. Duas ligaduras em ~500 caracteres: abaixo do
    `LIMITE_DE_OCR`, como as 3 em 772 da p. 20 dele."""
    doc = fitz.open()
    p = doc.new_page(width=600, height=400)
    p.insert_font(fontname="prova", fontbuffer=_fonte_com_ligadura(nome_da_ligadura))
    p.insert_text((20, 40), "battle\ufb01eld tabled battle\ufb01eld", fontname="prova",
                  fontsize=10)
    for i in range(12):
        p.insert_text((20, 60 + 16 * i), "tabled battle tabled battle tabled battle",
                      fontname="prova", fontsize=10)
    doc = fitz.open("pdf", doc.tobytes())
    for xref in range(1, doc.xref_length()):
        tipo, valor = doc.xref_get_key(xref, "ToUnicode")
        if tipo != "xref":
            continue
        alvo = int(valor.split()[0])
        cmap = doc.xref_stream(alvo).decode("latin-1")
        linhas = [l for l in cmap.splitlines() if not re.search(r"<[fF][bB]01>", l)]
        cmap = "\n".join(linhas)
        cmap = re.sub(r"(\d+) beginbfchar", lambda m: f"{int(m.group(1)) - 1} beginbfchar",
                      cmap)
        doc.update_stream(alvo, cmap.encode("latin-1"))
    doc.save(caminho)
    doc.close()
    return str(caminho)


def test_a_ligadura_sem_unicode_se_le_pelo_nome_do_glifo(tmp_path):
    pytest.importorskip("fontTools")
    pdf = _pdf_sem_unicode_na_ligadura(tmp_path / "l.pdf")
    with fitz.open(pdf) as doc:
        assert "\ufffd" in "".join(chr(c[0]) for t in doc[0].get_texttrace()
                                   for c in t["chars"]), "o PDF de prova não perdeu o Unicode"
    [veredito] = pdf_nativo.avaliar(pdf)
    assert veredito.aceita, veredito.motivo
    [pagina] = pdf_nativo.extrair(pdf).paginas
    assert "battlefield" in pagina.texto
    assert "\ufffd" not in pagina.texto


def test_a_ligadura_que_o_nome_nao_diz_manda_a_pagina_ao_ocr(tmp_path):
    """Abaixo do `LIMITE_DE_OCR` de 2% a página passava com `battle�eld`; a
    letra que nem o nome diz agora a manda ao OCR."""
    pytest.importorskip("fontTools")
    pdf = _pdf_sem_unicode_na_ligadura(tmp_path / "l.pdf", "xyz")
    [veredito] = pdf_nativo.avaliar(pdf)
    assert not veredito.aceita
    assert "sem Unicode" in veredito.motivo


# ----------------------------------------------------------------------
# A figurina em imagem
# ----------------------------------------------------------------------

def _figurina_png(lado=18) -> bytes:
    pix = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, lado, lado), False)
    pix.clear_with(255)
    pix.set_rect(fitz.IRect(4, 4, lado - 4, lado - 2), (0,))
    return pix.tobytes("png")


def _pagina_com_lance(caminho, *, figurina_na_linha: bool, figura_grande: bool = False):
    doc = fitz.open()
    p = doc.new_page(width=600, height=800)
    for i in range(6):
        p.insert_text((60, 100 + 16 * i), "White played the only move, and the game soon "
                      "ended in a draw.", fontname="helv", fontsize=12)
    p.insert_text((60, 220), "1 ...", fontname="helv", fontsize=12)
    x = 60 + fitz.get_text_length("1 ... ", fontname="helv", fontsize=12)
    if figurina_na_linha:
        p.insert_image(fitz.Rect(x, 208, x + 13.5, 222), stream=_figurina_png())
    p.insert_text((x + 14, 220), "xd4! (this exchange opens the c-file)", fontname="helv",
                  fontsize=12)
    if figura_grande:
        grande = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 214, 214), False)
        grande.clear_with(200)
        p.insert_image(fitz.Rect(220, 300, 380, 460), pixmap=grande)
    doc.save(caminho)
    doc.close()
    return str(caminho)


def test_a_figurina_em_imagem_na_linha_manda_a_pagina_ao_ocr(tmp_path):
    [veredito] = pdf_nativo.avaliar(_pagina_com_lance(tmp_path / "f.pdf",
                                                      figurina_na_linha=True))
    assert not veredito.aceita
    assert "figurina em imagem" in veredito.motivo


def test_a_figura_grande_fora_da_linha_nao_e_figurina(tmp_path):
    """O diagrama em imagem, a foto do autor: a página continua da camada."""
    [veredito] = pdf_nativo.avaliar(_pagina_com_lance(tmp_path / "f.pdf",
                                                      figurina_na_linha=False,
                                                      figura_grande=True))
    assert veredito.aceita, veredito.motivo


# ----------------------------------------------------------------------
# A moldura partida
# ----------------------------------------------------------------------

LADO, MOLDURA, CASA_ESCURA = 480, 4, 150


def _pagina_com_moldura_partida():
    """Um tabuleiro com a moldura aberta em cinza 158 nas divisas de três filas,
    como a imagem reamostrada do Khenkin, e as faixas que a binária deixa dele."""
    pg = np.full((1400, 1100), 255, np.uint8)
    x0, y0 = 300, 400
    casa = (LADO - 2 * MOLDURA) // 8
    for linha in range(8):
        for coluna in range(8):
            if (linha + coluna) % 2:
                y, x = y0 + MOLDURA + linha * casa, x0 + MOLDURA + coluna * casa
                pg[y:y + casa, x:x + casa] = CASA_ESCURA
    cv2.rectangle(pg, (x0, y0), (x0 + LADO - 1, y0 + LADO - 1), 0, MOLDURA)
    cortes = [y0 + MOLDURA + k * casa for k in (3, 5, 6)]
    for y in cortes:
        pg[y - 1:y + 2, x0:x0 + MOLDURA + 1] = 158
        pg[y - 1:y + 2, x0 + LADO - MOLDURA - 1:x0 + LADO] = 158
    topos = [y0] + cortes
    fundos = cortes + [y0 + LADO]
    faixas = [BoxEntry("?", x0, a, x0 + LADO, b) for a, b in zip(topos, fundos)]
    return pg, faixas, (x0, y0, x0 + LADO, y0 + LADO)


def test_o_tabuleiro_de_moldura_partida_e_achado_pelas_faixas():
    pg, faixas, caixa = _pagina_com_moldura_partida()
    [achado] = diag.localizar(faixas, faixas, escala=30, imagem=pg)
    assert all(abs(a - b) <= 6 for a, b in zip(achado, caixa)), achado


def test_sem_faixa_o_detector_nao_roda(monkeypatch):
    """A porta é estreita como a da F96: sem pedaço de moldura no descarte, quem
    responde é o `localizar` de sempre."""
    pg, _faixas, _caixa = _pagina_com_moldura_partida()
    chamadas = []
    monkeypatch.setattr(det, "localizar", lambda *a, **k: chamadas.append(a) or [])
    filete = BoxEntry("-", 100, 100, 900, 104)        # o traço também é descartado
    assert diag.localizar([filete], [filete], escala=30, imagem=pg) == []
    assert chamadas == []


def test_o_tabuleiro_longe_das_faixas_nao_entra():
    """O detector acha o tabuleiro; a faixa está em outro lugar — não é ele que partiu."""
    pg, _faixas, _caixa = _pagina_com_moldura_partida()
    longe = BoxEntry("?", 100, 1000, 700, 1150)
    assert diag.localizar([longe], [longe], escala=30, imagem=pg) == []


# ----------------------------------------------------------------------
# A linha de prosa colada em cima do tabuleiro
# ----------------------------------------------------------------------

def _letra(c, x, y1, y2):
    return BoxEntry(c, x, y1, x + 20, y2)


def test_a_letra_que_desce_na_faixa_volta_para_a_prosa():
    """`Nedeljkovic`: o `j` desce na margem do tabuleiro; o `e` e o `l` não."""
    e, l, i = _letra("e", 100, 470, 500), _letra("l", 122, 460, 500), _letra("i", 166, 460, 500)
    j = _letra("j", 144, 460, 515)
    comidas = [[j]]
    texto = [e, l, i]
    livro._devolver_a_linha_de_prosa(comidas, {id(j)}, texto, escala=30, minima=10)
    assert comidas == [[]]
    assert j in texto


def test_o_cabecalho_inteiro_na_faixa_fica_no_diagrama():
    """`Diagram 1-5` do Yusupov: o pé de toda letra cai na margem, e a linha é da faixa."""
    linha = [_letra(c, 100 + 22 * k, 470, 505) for k, c in enumerate("Diagram")]
    prosa_de_cima = [_letra("x", 100 + 22 * k, 380, 410) for k in range(7)]
    comidas = [list(linha)]
    texto = list(prosa_de_cima)
    livro._devolver_a_linha_de_prosa(comidas, {id(b) for b in linha}, texto,
                                     escala=30, minima=10)
    assert comidas == [linha]


# ----------------------------------------------------------------------
# A imagem do PDF que não é tabuleiro
# ----------------------------------------------------------------------

#: A página de prova tem 600x800 pt; lida a 300 dpi, 2500x3333 px.
FORMA = (int(800 * 300 / 72), int(600 * 300 / 72))


def _pagina_com_imagens(*retangulos, texto=True):
    """Prosa em Helvetica no alto e no pé da página (a camada tipográfica), e
    as imagens pedidas."""
    doc = fitz.open()
    p = doc.new_page(width=600, height=800)
    if texto:
        for y in (40, 56, 72, 740, 756, 772):
            p.insert_text((40, y), "Mating situations in which the rook delivers a "
                          "linear blow can also arise on the files.", fontsize=10)
    pix = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 60, 60), False)
    pix.clear_with(180)
    for r in retangulos:
        p.insert_image(fitz.Rect(*r), pixmap=pix)
    doc = fitz.open("pdf", doc.tobytes())
    return doc, doc[0]


def _em_pixels(*r):
    return tuple(int(v * 300 / 72) for v in r)


def _letras_fora(n=200):
    """Caixas de letra espalhadas fora da imagem, como a prosa da página."""
    return [BoxEntry("a", 100 + (k % 40) * 50, 100 + (k // 40) * 60,
                     130 + (k % 40) * 50, 140 + (k // 40) * 60) for k in range(n)]


def test_a_imagem_do_meio_da_pagina_sai_como_figura():
    """Os quatro recortes da p. 21 do Khenkin: nem tabuleiro, nem texto."""
    _doc, pagina = _pagina_com_imagens((200, 300, 400, 500))
    dentro = [BoxEntry("♖", *_em_pixels(250, 350, 262, 364))]
    [imagem] = livro._imagens_do_pdf(pagina, FORMA, _letras_fora() + dentro, [])
    assert all(abs(a - b) <= 1 for a, b in zip(imagem.caixa, _em_pixels(200, 300, 400, 500)))
    assert livro._centro_dentro(dentro[0], imagem.caixa)


def test_sem_tipografia_a_imagem_e_resto_do_scan():
    """ClearScan ou digitalização: a camada não é tipografia, e a imagem do meio
    da página (a faixa de cabeçalho do Yusupov) continua sendo lida como texto."""
    _doc, pagina = _pagina_com_imagens((200, 300, 400, 500), texto=False)
    assert livro._imagens_do_pdf(pagina, FORMA, _letras_fora(), []) == []


def test_a_digitalizacao_nao_vira_figura():
    """A página inteira em imagem — e a digitalização em quatro tiras."""
    _doc, inteira = _pagina_com_imagens((0, 0, 600, 800))
    assert livro._imagens_do_pdf(inteira, FORMA, _letras_fora(), []) == []
    _doc, tiras = _pagina_com_imagens(*[(0, 200 * k, 600, 200 * (k + 1)) for k in range(4)])
    assert livro._imagens_do_pdf(tiras, FORMA, _letras_fora(), []) == []


def test_a_imagem_com_a_maior_parte_das_letras_e_a_pagina():
    """A digitalização que não cobre a página (margem larga): as letras estão dentro dela."""
    _doc, pagina = _pagina_com_imagens((20, 20, 580, 600))
    letras = [BoxEntry("a", *_em_pixels(40 + (k % 20) * 25, 40 + (k // 20) * 30,
                                        52 + (k % 20) * 25, 52 + (k // 20) * 30))
              for k in range(300)]
    assert livro._imagens_do_pdf(pagina, FORMA, letras + _letras_fora(20), []) == []


def test_a_figurina_em_imagem_e_o_diagrama_em_imagem_ficam_de_fora():
    _doc, pagina = _pagina_com_imagens((100, 100, 113.5, 114), (200, 300, 360, 460))
    tabuleiro = _em_pixels(203, 303, 357, 457)
    d = livro.Diagrama(exclusao=tabuleiro, tabuleiro=tabuleiro)
    assert livro._imagens_do_pdf(pagina, FORMA, _letras_fora(), [d]) == []


# ----------------------------------------------------------------------
# O Khenkin, quando ele está na máquina
# ----------------------------------------------------------------------

def _khenkin():
    candidatos = [os.environ.get("KHENKIN_PDF", "")]
    for base in (os.path.join(RAIZ, "PDF"), os.path.join(os.path.dirname(RAIZ), "HTML_to_EPUB")):
        candidatos += sorted(glob.glob(os.path.join(base, "Khenkin*", "*.pdf")))
    for caminho in candidatos:
        if caminho and os.path.isfile(caminho):
            return caminho
    pytest.skip("o PDF do Khenkin não está na máquina")


def test_khenkin_as_paginas_de_figurina_em_imagem_vao_ao_ocr():
    vereditos = pdf_nativo.avaliar(_khenkin(), [19, 20])
    assert [v.aceita for v in vereditos] == [False, False]
    assert all("figurina em imagem" in v.motivo for v in vereditos)


def test_khenkin_os_tres_tabuleiros_da_pagina_20_sao_achados():
    from PIL import Image
    from core.services.box_service import BoxService

    with fitz.open(_khenkin()) as doc:
        pix = doc[19].get_pixmap(dpi=300, colorspace=fitz.csGRAY, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy()
    binaria = BoxService.binaria_para_segmentacao(
        img, max_contornos=BoxService.MAX_CONTORNOS_DE_TEXTO)
    antes, th, escala, _c = BoxService.boxes_antes_do_descarte(
        Image.fromarray(img), max_contornos=BoxService.MAX_CONTORNOS_DE_TEXTO,
        binaria_inicial=binaria)
    assert len(diag.localizar(antes, escala=escala, imagem=img, binaria=th)) == 3


def test_khenkin_os_recortes_da_pagina_21_saem_como_uma_figura():
    """Antes: seis parágrafos de figurinas soltas entre as duas prosas."""
    with fitz.open(_khenkin()) as doc:
        pagina = livro.extrair_pagina(doc[20], lambda *a, **k: ("a", 0.99), numero=20)
    figuras = [b for b in pagina.blocos
               if isinstance(b, livro.Figura) and b.origem == "pagina"]
    assert len(figuras) == 1
    antes = pagina.blocos[pagina.blocos.index(figuras[0]) - 1]
    assert isinstance(antes, livro.Paragrafo) and len(antes.texto) > 100


def test_a_imagem_do_pdf_que_e_tabuleiro_vira_diagrama():
    """A p. 60 do Khenkin: a moldura partida em toda divisa não deixa pista no
    descarte, e é a imagem do PDF que diz onde procurar."""
    pg, _faixas, caixa = _pagina_com_moldura_partida()
    tabuleiro = livro._ImagemDoPdf((caixa[0] - 10, caixa[1] - 10, caixa[2] + 10, caixa[3] + 10))
    texto = livro._ImagemDoPdf((100, 1000, 700, 1150))
    ficam, achados = livro._tabuleiros_das_imagens(pg, [tabuleiro, texto], 30,
                                                   lambda *a, **k: ("a", 0.99))
    assert ficam == [texto]
    [d] = achados
    assert all(abs(a - b) <= 6 for a, b in zip(d.tabuleiro, caixa)), d.tabuleiro


def test_khenkin_o_terceiro_tabuleiro_da_pagina_60_e_diagrama():
    with fitz.open(_khenkin()) as doc:
        pagina = livro.extrair_pagina(doc[59], lambda *a, **k: ("a", 0.99), numero=59)
    assert pagina.diagramas == 3
    assert [b.origem for b in pagina.blocos
            if isinstance(b, livro.Figura)].count("pagina") == 1
