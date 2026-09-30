"""
A foto e a gravura do livro ClearScan saem como figura, e não como texto lido.

O retrato de Morphy da p. 76 do Yusupov (*Chess Evolution 1*) era lido como
treze parágrafos de símbolos (`= ⯹ ⩲ ♖ ♕`), e nas pp. 148 e 206 a foto engolia a
página, que saía vazia. `livro._gravuras_do_pdf` acha a gravura pelo objeto de
imagem do PDF e pela tinta dele; `livro._sem_gravuras` a tira da página que se
lê; `livro._moldura_da_gravura` tira a moldura do quadro oval da legenda.

Os testes montam os casos com o PyMuPDF e numpy; os do fim rodam sobre o
Yusupov e o *Attacking Manual* quando eles estão em `PDF/`.
"""

import glob
import os

import fitz
import numpy as np
import pytest

from core import lexico, livro
from core.box_model import BoxEntry

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pixmap(largura, altura, desenho):
    arr = np.full((altura, largura), 255, np.uint8)
    desenho(arr)
    return fitz.Pixmap(fitz.csGRAY, largura, altura, arr.tobytes(), False)


def _foto(arr):
    """A retícula escura de uma foto: quase toda tinta, uma massa só, com um
    rosto claro no meio."""
    arr[:, :] = 40
    arr[60:180, 70:170] = 200


def _faixa(arr):
    """A faixa de cabeçalho: cinza, larga e baixa, com letra branca."""
    arr[:, :] = 90
    for k in range(10):
        arr[20:44, 40 + 60 * k:70 + 60 * k] = 255


def _texto(arr):
    """Um quadro de legenda: letra espalhada em fundo branco."""
    for linha in range(4):
        for k in range(12):
            arr[20 + 40 * linha:40 + 40 * linha, 15 + 25 * k:30 + 25 * k] = 0


def _pagina(*imagens, texto=False):
    doc = fitz.open()
    p = doc.new_page(width=465, height=680)
    if texto:
        for y in range(40, 200, 14):
            p.insert_text((40, y), "The quick brown fox jumps over the lazy dog again.", fontsize=10)
    for rect, pix in imagens:
        p.insert_image(fitz.Rect(*rect), pixmap=pix)
    doc = fitz.open("pdf", doc.tobytes())
    return doc, doc[0]


def _lida(page):
    return livro._pagina_cinza(page, 300)


def test_a_foto_da_pagina_sem_tipografia_e_gravura():
    _doc, page = _pagina(((80, 90, 370, 470), _pixmap(240, 240, _foto)))
    [g] = livro._gravuras_do_pdf(page, _lida(page))
    esperado = tuple(int(v * 300 / 72) for v in (80, 90, 370, 470))
    assert all(abs(a - b) <= 6 for a, b in zip(g.caixa, esperado)), g.caixa


def test_a_faixa_e_o_quadro_de_texto_nao_sao_gravura():
    """A faixa `A.Yusupov – M.Chandler` passa na tinta e cai na proporção; o
    quadro da legenda cai na tinta."""
    _doc, page = _pagina(((40, 300, 400, 330), _pixmap(660, 60, _faixa)),
                         ((100, 400, 400, 520), _pixmap(320, 170, _texto)))
    assert livro._gravuras_do_pdf(page, _lida(page)) == []


def test_na_pagina_tipografica_quem_responde_e_a_outra_porta():
    """Com camada de texto de verdade, a imagem é figura por `_imagens_do_pdf`;
    aqui não se repete."""
    _doc, page = _pagina(((80, 250, 370, 600), _pixmap(240, 240, _foto)), texto=True)
    assert livro._gravuras_do_pdf(page, _lida(page)) == []


def test_o_fundo_do_tamanho_da_pagina_nao_fecha_a_porta():
    """O *Attacking Manual*: o ClearScan guarda o scan atrás da página, e a foto
    do capítulo por cima. O fundo não é a digitalização em tiras."""
    fundo = _pixmap(200, 290, lambda a: None)
    _doc, page = _pagina(((0, 0, 465, 680), fundo), ((10, 10, 455, 360), _pixmap(240, 200, _foto)))
    [g] = livro._gravuras_do_pdf(page, _lida(page))
    assert g.caixa[1] < 100 and g.caixa[3] < 1600


def test_a_gravura_sai_da_pagina_que_se_le():
    img = np.zeros((100, 100), np.uint8)
    limpa = livro._sem_gravuras(img, [livro._ImagemDoPdf((10, 20, 50, 60))])
    assert limpa[30, 30] == 255 and limpa[5, 5] == 0
    assert img[30, 30] == 0, "a página original não pode mudar: a figura sai dela"


def test_a_moldura_do_oval_sai_e_a_legenda_fica():
    lex = lexico.Lexico(palavras={"author", "relaxed", "mood"})
    g = livro._ImagemDoPdf((0, 0, 100, 60), objeto=(0, 0, 100, 100))
    linha = [BoxEntry("n", 10, 70, 20, 80), BoxEntry("r", 30, 70, 40, 80)]
    assert livro._moldura_da_gravura(linha, "n r n=n= ⇄", [g], lex)
    assert not livro._moldura_da_gravura(linha, "The author in relaxed mood", [g], lex)
    fora = [BoxEntry("n", 10, 170, 20, 180)]
    assert not livro._moldura_da_gravura(fora, "n r n=n= ⇄", [g], lex)


# ----------------------------------------------------------------------
# Os livros, quando estão na máquina
# ----------------------------------------------------------------------

def _pdf(padrao):
    # `PDF_DO_CORPUS` aponta a pasta de outra árvore (o worktree não tem `PDF/`).
    pasta = os.environ.get("PDF_DO_CORPUS") or os.path.join(RAIZ, "PDF")
    achados = sorted(glob.glob(os.path.join(pasta, padrao)))
    if not achados:
        pytest.skip(f"PDF do corpus ausente: {padrao}")
    return achados[0]


def test_yusupov_o_retrato_de_morphy_e_gravura_e_a_faixa_nao():
    with fitz.open(_pdf("*Yusupov*Evolution 1*editable/*editable.pdf")) as doc:
        [morphy] = livro._gravuras_do_pdf(doc[75], _lida(doc[75]))
        assert livro._gravuras_do_pdf(doc[33], _lida(doc[33])) == []
    assert morphy.caixa[2] - morphy.caixa[0] > 1000


def test_attacking_manual_a_foto_do_capitulo_e_gravura():
    with fitz.open(_pdf("Jacob Aagaard*/*.pdf")) as doc:
        assert len(livro._gravuras_do_pdf(doc[27], _lida(doc[27]))) == 1
