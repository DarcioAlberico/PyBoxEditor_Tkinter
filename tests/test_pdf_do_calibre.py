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

E um quarto, que aparecia junto: a linha de prosa colada em cima do tabuleiro
perdia as letras que descem (`j gy` virava o título do diagrama).

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
    p.insert_text((20, 40), "battleﬁeld tabled battleﬁeld", fontname="prova",
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
        assert "�" in "".join(chr(c[0]) for t in doc[0].get_texttrace()
                                   for c in t["chars"]), "o PDF de prova não perdeu o Unicode"
    [veredito] = pdf_nativo.avaliar(pdf)
    assert veredito.aceita, veredito.motivo
    [pagina] = pdf_nativo.extrair(pdf).paginas
    assert "battlefield" in pagina.texto
    assert "�" not in pagina.texto


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
