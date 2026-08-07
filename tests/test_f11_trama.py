"""
F11 — texto sobre trama de meio-tom.

O painel chapado do "Scoring", no fim de cada capítulo do Yusupov, escaneia como
uma nuvem de pontos, e o estrago é em dois tempos:

1. A trama envenena a régua: 95,8% dos 6.765 contornos da página 18 medem 6x6 px
   ou menos, a mediana das alturas cai para 2, e `descartar_blocos_nao_texto`
   passa a jogar fora tudo acima de 8 px — o texto.
2. A trama solda: os pontos encostam nas letras, o painel sai como **um**
   contorno de 1049x390 e o que estava escrito ali não chega a existir.

Metade destes testes é sobre não estragar o que já funcionava: o diagrama tem de
continuar sendo um box descartado (F1.8), a pontuação escura tem de sobreviver à
limpeza, e a página sem trama tem de sair byte a byte igual.

Rodar sem pytest:      python tests/test_f11_trama.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pytest
from PIL import Image

from core import preprocess, trama
from core.box_model import BoxEntry
from core.services.box_service import BoxService


ESCALA = 30          # altura de caractere das montagens


def _pagina(largura=900, altura=600):
    return np.full((altura, largura), 245, np.uint8)


def _texto(img, texto, x, y, escala=1.0, cor=15):
    cv2.putText(img, texto, (x, y), cv2.FONT_HERSHEY_SIMPLEX, escala, cor, 2)


def _linhas_de_texto(img, quantas=6):
    """Texto normal, que é de onde sai a escala da página."""
    for k in range(quantas):
        _texto(img, "ABCDEFGH", 40, 60 + k * 50)
    return img


def _trama(img, x, y, w, h, passo=3, tom=150):
    """Trama solta: pontos claros e separados, que não se tocam."""
    img[y:y + h:passo, x:x + w:passo] = tom
    return img


def _trama_soldada(img, x, y, w, h, densidade=0.45, tom=120, semente=0):
    """
    Trama que **solda**: acima de ~41% de densidade os pontos se encadeiam.

    É o limiar de percolação de sítios numa grade quadrada com vizinhança 8, e é
    o que separa esta montagem da de cima — com pontos regulares e separados
    cada um vira um componente solto, e o defeito da fase (o painel inteiro
    virando um contorno só) não aparece.
    """
    ruido = np.random.RandomState(semente).random_sample((h, w)) < densidade
    regiao = img[y:y + h, x:x + w]
    regiao[ruido] = tom
    return img


def _pagina_com_painel():
    """
    Página com texto normal e um painel de trama com texto dentro.

    O painel é **largo** (3:1), como o do livro — é o que o distingue de um
    tabuleiro — e a trama é densa o bastante para soldar.
    """
    img = _linhas_de_texto(_pagina(1000, 800))
    _trama_soldada(img, 100, 400, 750, 250)
    _texto(img, "PONTOS", 150, 480, 1.0)
    _texto(img, "MAXIMO 22", 150, 560, 1.0)
    return img


# ----------------------------------------------------------------------
# A régua
# ----------------------------------------------------------------------

def test_escala_de_texto_ignora_a_nuvem_de_pontos():
    """
    A mediana simples desaba; a ponderada por tinta não.

    O ponto de trama tem ~4 px de tinta e uma letra tem ~200 — é a massa que
    faz a diferença, e é por isso que a ponderação funciona.
    """
    img = _pagina()
    _linhas_de_texto(img)
    th_limpo = preprocess.binarize(img, "auto")
    escala_limpa = preprocess.escala_de_texto(th_limpo)

    com_pontos = _trama(img.copy(), 300, 300, 500, 250, passo=4, tom=120)
    th = preprocess.binarize(com_pontos, "auto")

    alturas = sorted(cv2.boundingRect(c)[3] for c in cv2.findContours(
        th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0])
    mediana = alturas[len(alturas) // 2]

    assert mediana <= 4, "a montagem não reproduz o envenenamento da mediana"
    assert preprocess.escala_de_texto(th) >= escala_limpa * 0.5
    assert preprocess.escala_de_texto(th) >= 15


def test_escala_de_texto_de_pagina_vazia():
    assert preprocess.escala_de_texto(np.zeros((10, 10), np.uint8)) == 0


def test_o_descarte_com_escala_salva_o_texto():
    """
    O defeito que apagava o painel: com a mediana envenenada, o limite do
    descarte fica em 8 px e os caracteres não passam.
    """
    letras = [BoxEntry("", i * 40, 0, i * 40 + 30, 30) for i in range(10)]
    pontos = [BoxEntry("", i * 3, 100, i * 3 + 2, 102) for i in range(200)]
    boxes = letras + pontos

    sem_escala = BoxService.descartar_blocos_nao_texto(boxes)
    com_escala = BoxService.descartar_blocos_nao_texto(boxes, escala=30)

    assert not any(b in sem_escala for b in letras), \
        "a montagem não reproduz o defeito"
    assert all(b in com_escala for b in letras)


# ----------------------------------------------------------------------
# A limpeza da trama solta
# ----------------------------------------------------------------------

def test_remover_textura_apaga_ponto_claro_e_pequeno():
    img = _linhas_de_texto(_pagina())
    com_pontos = _trama(img.copy(), 300, 300, 500, 250, passo=4, tom=120)

    th = preprocess.binarize(com_pontos, "auto")
    limpo = preprocess.remover_textura(com_pontos, th)

    assert (limpo > 0).sum() < (th > 0).sum() * 0.9


def test_remover_textura_poupa_pontuacao_escura():
    """
    Ponto final é pequeno como um ponto de trama — e **escuro**, que é o que o
    salva. Apagar por tamanho sozinho comeria a pontuação da página inteira.
    """
    img = _linhas_de_texto(_pagina())
    for k in range(6):                       # pontos finais, escuros
        cv2.circle(img, (300, 60 + k * 50), 3, 15, -1)

    th = preprocess.binarize(img, "auto")
    limpo = preprocess.remover_textura(img, th)

    assert (limpo > 0).sum() == (th > 0).sum(), "apagou tinta escura"


def test_pagina_sem_trama_sai_intacta():
    img = _linhas_de_texto(_pagina())
    th = preprocess.binarize(img, "auto")
    assert (preprocess.remover_textura(img, th) == th).all()


# ----------------------------------------------------------------------
# O bloco soldado
# ----------------------------------------------------------------------

def test_o_painel_vira_um_bloco_soldado():
    """A premissa da fase: sem ela, não há o que consertar."""
    img = _pagina_com_painel()
    th = preprocess.remover_textura(img, preprocess.binarize(img, "auto"))
    cont, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    grandes = [cv2.boundingRect(c) for c in cont
               if cv2.boundingRect(c)[2] > 400 and cv2.boundingRect(c)[3] > 150]
    assert grandes, "o painel não saiu soldado num bloco só"


def test_o_texto_do_painel_vira_boxes():
    img = _pagina_com_painel()
    boxes = BoxService.generate_boxes_opencv(Image.fromarray(img))

    dentro = [b for b in boxes
              if 100 <= b.x1 and b.x2 <= 850 and 400 <= b.y1 and b.y2 <= 650]
    assert len(dentro) >= 6, f"o texto do painel continua perdido ({len(dentro)})"
    assert all(b.height <= ESCALA * 3 for b in dentro)


def test_bloco_quadrado_nao_e_lido():
    """
    A peneira que protege o diagrama, e ela é do domínio: tabuleiro é quadrado.

    Medido nas páginas 30 e 31 do Yusupov, os seis diagramas dão proporção 1,00
    a 1,01; o painel de pontuação dá 2,69. Ler dentro de um tabuleiro daria uma
    caixa por peça — o contrário do que a F1.8 mediu e fixou.
    """
    quadrado = BoxEntry("", 0, 0, 20 * ESCALA, 20 * ESCALA)
    largo = BoxEntry("", 0, 0, 20 * ESCALA, 8 * ESCALA)

    assert trama.candidatos([quadrado], ESCALA) == []
    assert trama.candidatos([largo], ESCALA) == [largo]


def test_bloco_pequeno_nao_e_candidato():
    palavra = BoxEntry("", 0, 0, 6 * ESCALA, 2 * ESCALA)
    assert trama.candidatos([palavra], ESCALA) == []


def test_sem_escala_nao_ha_candidato():
    """Sem régua não há como dizer o que é grande — e não agir é o certo."""
    assert trama.candidatos([BoxEntry("", 0, 0, 600, 200)], 0) == []


def test_bloco_sem_texto_dentro_fica_como_estava():
    """Sombra, filete e moldura também são blocos largos."""
    img = _pagina(600, 300)
    img[100:200, 50:550] = 30              # barra chapada, sem nada dentro
    th = preprocess.binarize(img, "auto")
    bloco = BoxEntry("", 50, 100, 550, 200)

    novas, lidos = trama.aplicar(img, [bloco], ESCALA)
    assert lidos == []
    assert novas == [bloco]


def test_a_lista_volta_ordenada():
    """A mesma porta da F10: fora de ordem, o merge atravessa a página."""
    img = _pagina_com_painel()
    th = preprocess.remover_textura(img, preprocess.binarize(img, "auto"))
    escala = preprocess.escala_de_texto(th)
    cont, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in cont:
        x, y, w, h = cv2.boundingRect(c)
        if w >= 2 and h >= 2:
            boxes.append(BoxEntry("", x, y, x + w, y + h))
    boxes.sort(key=lambda b: (b.y1, b.x1))

    novas, lidos = trama.aplicar(img, boxes, escala)
    assert lidos, "a montagem não produziu bloco legível"
    chaves = [(b.y1, b.x1) for b in novas]
    assert chaves == sorted(chaves)


# ----------------------------------------------------------------------
# A página real
# ----------------------------------------------------------------------

def _pagina_do_yusupov(indice=17, dpi=300):
    """A página 18 impressa (índice 17), ou None se o PDF não está aqui."""
    import glob

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    achados = glob.glob(os.path.join(raiz, "PDF", "*Yusupov*", "*.pdf"))
    if not achados:
        return None
    try:
        import fitz
    except ImportError:
        return None

    doc = fitz.open(achados[0])
    if indice >= len(doc):
        doc.close()
        return None
    pix = doc[indice].get_pixmap(dpi=dpi)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    doc.close()
    return (cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
            if pix.n >= 3 else arr[:, :, 0].copy())


def test_o_quadro_de_pontuacao_da_pagina_18():
    """
    A página que motivou a fase: 6.765 contornos, 95,8% deles de 6x6 ou menos.

    Antes, o painel inteiro saía sem um box; o teste cobra que o texto de dentro
    dele exista.
    """
    cinza = _pagina_do_yusupov()
    if cinza is None:
        pytest.skip("o PDF do Yusupov não está distribuído com o código")

    th = preprocess.binarize(cinza, "auto")
    assert preprocess.escala_de_texto(th) >= 20, "a régua desabou"

    boxes = BoxService.generate_boxes_opencv(Image.fromarray(cinza))
    # o painel ocupa aproximadamente esta faixa da página, a 300 dpi
    dentro = [b for b in boxes
              if 460 <= b.x1 and b.x2 <= 1510 and 440 <= b.y1 and b.y2 <= 840
              and b.height >= 15]
    assert len(dentro) >= 30, \
        f"o texto do quadro de pontuação continua perdido ({len(dentro)} boxes)"


def test_o_diagrama_continua_sendo_um_bloco_descartado():
    """A invariante da F1.8, cobrada na página real com diagramas."""
    cinza = _pagina_do_yusupov(30)
    if cinza is None:
        pytest.skip("o PDF do Yusupov não está distribuído com o código")

    th = preprocess.remover_textura(cinza, preprocess.binarize(cinza, "auto"))
    escala = preprocess.escala_de_texto(th)
    cont, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in cont:
        x, y, w, h = cv2.boundingRect(c)
        if w >= 2 and h >= 2:
            boxes.append(BoxEntry("", x, y, x + w, y + h))

    quadrados = [b for b in boxes
                 if b.width >= escala * 4 and b.height >= escala * 4
                 and 0.9 <= b.width / b.height <= 1.1]
    assert quadrados, "a página 31 deveria ter diagrama"
    assert trama.candidatos(boxes, escala) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
