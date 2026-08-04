"""
Testes da F1.5 — pré-processamento e separação de glifos colados.

Duas coisas nesta fase:

1. O threshold fixo em 180 estava replicado por três módulos. Funciona numa
   página limpa e falha em scan com iluminação irregular.
2. Em notação figurina os contornos se tocam: `findContours` devolvia "♞e5"
   como um box só, e o classificador lia um caractere errado. Era a origem de
   todos os erros de figurina observados na página real (achado da F1.1).

Rodar sem pytest:      python tests/test_f15_preprocess.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from PIL import Image

from core import preprocess
from core.box_model import BoxEntry
from core.services.box_service import BoxService


def _pagina(largura=400, altura=200, gradiente=False):
    """Página branca com algumas letras pretas."""
    img = np.full((altura, largura), 245, np.uint8)
    for i in range(6):
        cv2.putText(img, "A", (20 + i * 55, 120), cv2.FONT_HERSHEY_SIMPLEX,
                    1.6, 20, 3)
    if gradiente:
        # sombra de encadernação: um lado bem mais escuro que o outro
        rampa = np.linspace(1.0, 0.35, largura).astype(np.float32)
        img = (img.astype(np.float32) * rampa[None, :]).astype(np.uint8)
    return img


def _glifos(larguras, altura=30, vao=5):
    """
    Faixa binária com blocos de tinta separados por `vao` colunas vazias.

    Reproduz o caso real: os glifos NÃO se sobrepõem — eles se encostam num
    ponto (serifa, anti-aliasing), o suficiente para findContours devolver um
    contorno só, mas o perfil de tinta continua tendo vale entre eles. Blocos
    sólidos grudados, sem vale nenhum, não existem em texto e não podem ser
    separados por projeção.
    """
    total = sum(larguras) + vao * (len(larguras) - 1)
    img = np.zeros((altura, total), np.uint8)
    x = 0
    for i, lg in enumerate(larguras):
        img[4:altura - 4, x:x + lg] = 255
        x += lg + (vao if i < len(larguras) - 1 else 0)
    return img


# ----------------------------------------------------------------------
# Binarização
# ----------------------------------------------------------------------

def test_binarize_deixa_tinta_em_branco():
    """findContours espera tinta = 255, fundo = 0."""
    for metodo in ("otsu", "adaptive", "fixed"):
        th = preprocess.binarize(_pagina(), metodo)
        assert th.dtype == np.uint8
        assert set(np.unique(th)) <= {0, 255}
        assert 0 < (th > 0).mean() < 0.5, f"{metodo}: proporção de tinta implausível"


def test_metodo_invalido():
    try:
        preprocess.binarize(_pagina(), "xpto")
    except ValueError as e:
        assert "método" in str(e)
    else:
        raise AssertionError("aceitou método inválido")


def test_tinta_plausivel_reconhece_pagina_limpa():
    th = preprocess.binarize(_pagina(), "otsu")
    assert preprocess.tinta_plausivel(th) is True
    assert 0.0 < preprocess.fracao_de_tinta(th) < 0.35


def test_tinta_implausivel_em_pagina_com_sombra():
    """
    O critério que a primeira versão errava: com sombra de encadernação o
    histograma É bimodal (metade escura vs metade clara), mas o Otsu devolve
    quase metade da página como tinta.
    """
    com_sombra = _pagina(gradiente=True)
    import cv2 as _cv
    _, otsu = _cv.threshold(_cv.cvtColor(_cv.cvtColor(com_sombra, _cv.COLOR_GRAY2RGB),
                                         _cv.COLOR_RGB2GRAY),
                            0, 255, _cv.THRESH_BINARY_INV + _cv.THRESH_OTSU)
    assert preprocess.fracao_de_tinta(otsu) > 0.35
    assert preprocess.tinta_plausivel(otsu) is False


def test_auto_escolhe_adaptativo_em_iluminacao_irregular():
    """
    É o caso que o limiar fixo perdia: com sombra de encadernação, o lado
    escuro da página inteiro cai abaixo de 180 e vira uma mancha de tinta.
    """
    com_sombra = _pagina(gradiente=True)

    fixo = preprocess.binarize(com_sombra, "fixed", fixed_threshold=180)
    auto = preprocess.binarize(com_sombra, "auto")

    assert (fixo > 0).mean() > 0.5, "o cenário do teste não reproduz o problema"
    assert (auto > 0).mean() < 0.3, "auto não lidou com a iluminação irregular"


def test_binarize_aceita_rgb():
    rgb = cv2.cvtColor(_pagina(), cv2.COLOR_GRAY2RGB)
    assert preprocess.binarize(rgb, "otsu").ndim == 2


# ----------------------------------------------------------------------
# Deskew
# ----------------------------------------------------------------------

def test_deskew_corrige_inclinacao():
    reta = _pagina()
    h, w = reta.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 5.0, 1.0)
    torta = cv2.warpAffine(reta, M, (w, h), borderMode=cv2.BORDER_REPLICATE)

    _, angulo = preprocess.deskew(torta)
    assert abs(angulo) > 1.0, "não detectou a inclinação"
    assert angulo * 5.0 < 0 or abs(angulo - 5.0) < 3.0, \
        f"corrigiu no sentido errado (ângulo {angulo})"


def test_deskew_nao_mexe_em_pagina_reta():
    _, angulo = preprocess.deskew(_pagina())
    assert abs(angulo) < 1.0


def test_deskew_ignora_inclinacao_absurda():
    """Ângulo grande demais é sinal de que a medida pegou outra coisa."""
    _, angulo = preprocess.deskew(_pagina(), max_angle=0.5)
    assert angulo == 0.0


def test_deskew_com_imagem_quase_vazia():
    vazia = np.full((50, 50), 255, np.uint8)
    img, angulo = preprocess.deskew(vazia)
    assert angulo == 0.0 and img.shape == vazia.shape


# ----------------------------------------------------------------------
# Denoise e DPI
# ----------------------------------------------------------------------

def test_denoise_tira_sujeira_e_preserva_caractere():
    th = preprocess.binarize(_pagina(), "otsu")
    sujo = th.copy()
    for x in range(10, 390, 40):
        sujo[10, x] = 255          # partículas de 1 pixel

    limpo = preprocess.denoise(sujo)
    assert (limpo > 0).sum() < (sujo > 0).sum(), "não removeu nada"
    assert (limpo > 0).sum() >= (th > 0).sum() * 0.98, "comeu parte dos caracteres"


def test_normalize_dpi():
    img = _pagina(400, 200)
    assert preprocess.normalize_dpi(img, 150, 300).shape == (400, 800)
    assert preprocess.normalize_dpi(img, 300, 300).shape == (200, 400)
    assert preprocess.normalize_dpi(img, 0, 300).shape == (200, 400)


def test_pipeline_completo():
    binaria, angulo = preprocess.preparar_pagina(_pagina())
    assert binaria.ndim == 2
    assert set(np.unique(binaria)) <= {0, 255}
    assert abs(angulo) < 1.0


# ----------------------------------------------------------------------
# Separação de glifos colados
# ----------------------------------------------------------------------

def test_separa_glifos_encostados():
    """Três glifos que o findContours devolveu como um box só."""
    img = _glifos([20, 20, 20], vao=5)          # 20+5+20+5+20 = 70
    box = [BoxEntry("", 0, 0, 70, 30)]
    # mediana precisa vir de uma página com caracteres normais
    contexto = [BoxEntry("", i * 25, 40, i * 25 + 20, 70) for i in range(10)]

    saida = BoxService.dividir_glifos_colados(box + contexto, _preenche(img, 80, 90))
    largos = [b for b in saida if b.y1 == 0]
    assert len(largos) == 3, f"esperava 3 pedaços, veio {[(b.x1, b.x2) for b in largos]}"


def _preenche(faixa, alt, larg):
    """Coloca a faixa num canvas maior, para os índices dos boxes baterem."""
    canvas = np.zeros((max(alt, faixa.shape[0]), max(larg, faixa.shape[1])), np.uint8)
    canvas[:faixa.shape[0], :faixa.shape[1]] = faixa
    return canvas


def test_nao_corta_glifo_largo_com_vales_internos():
    """
    A coroa da dama tem vales fundos entre as pontas. Cortar por profundidade
    a partiria; o critério é a LARGURA do vale.

    Medido na página real (mediana 19px): ♞e5 tem vale de 10 colunas e ♛ tem
    vale de 0 — separáveis com folga.
    """
    # "coroa": blocos altos separados por fendas de 1 coluna, sobre uma base
    coroa = np.zeros((30, 36), np.uint8)
    for x in range(0, 36, 6):
        coroa[2:20, x:x + 5] = 255
    coroa[20:28, :] = 255                      # base sólida

    box = [BoxEntry("", 0, 0, 36, 30)]
    contexto = [BoxEntry("", i * 25, 40, i * 25 + 18, 70) for i in range(10)]

    saida = BoxService.dividir_glifos_colados(box + contexto, _preenche(coroa, 80, 80))
    largos = [b for b in saida if b.y1 == 0]
    assert len(largos) == 1, f"partiu um glifo único em {len(largos)} pedaços"


def test_nao_corta_box_de_largura_normal():
    boxes = [BoxEntry("", i * 25, 0, i * 25 + 18, 30) for i in range(10)]
    img = np.zeros((40, 300), np.uint8)
    for b in boxes:
        img[4:26, b.x1:b.x2] = 255
    assert len(BoxService.dividir_glifos_colados(boxes, img)) == len(boxes)


def test_sem_imagem_nao_faz_nada():
    boxes = [BoxEntry("", 0, 0, 100, 30)]
    assert BoxService.dividir_glifos_colados(boxes, None) == boxes
    assert BoxService.dividir_glifos_colados([], np.zeros((10, 10), np.uint8)) == []


def test_pedacos_nao_saem_finos_demais():
    """Um corte perto da borda deixaria um caco inútil."""
    img = _glifos([20, 20, 20], vao=5)
    box = [BoxEntry("", 0, 0, 70, 30)]
    contexto = [BoxEntry("", i * 25, 40, i * 25 + 20, 70) for i in range(10)]

    saida = BoxService.dividir_glifos_colados(box + contexto, _preenche(img, 80, 90))
    for b in (b for b in saida if b.y1 == 0):
        assert (b.x2 - b.x1) >= 6, f"pedaço de {b.x2-b.x1}px é fino demais"


# ----------------------------------------------------------------------
# Página real
# ----------------------------------------------------------------------

def test_pagina_real_separa_sem_cortes_falsos():
    """
    Medido em 8 páginas reais: boxes largos 660 → 427 (35% resolvidos), e
    ZERO pedaços estreitos novos — nenhum corte falso.
    """
    import glob

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cand = glob.glob(os.path.join(raiz, "ilovepdf_pages-to-jpg", "*0021.jpg"))
    if not cand:
        return

    img = cv2.imread(cand[0], cv2.IMREAD_GRAYSCALE)
    if img is None:
        return
    h, w = img.shape
    rec = Image.fromarray(img[int(h * 0.20):int(h * 0.80), int(w * 0.05):int(w * 0.95)])

    antes = BoxService.generate_boxes_opencv(rec, method="auto", separar_colados=False)
    depois = BoxService.generate_boxes_opencv(rec, method="auto", separar_colados=True)

    larg = sorted(b.x2 - b.x1 for b in antes)
    med = larg[len(larg) // 2] or 1

    largos_antes = sum(1 for b in antes if (b.x2 - b.x1) > med * 1.6)
    largos_depois = sum(1 for b in depois if (b.x2 - b.x1) > med * 1.6)
    assert largos_depois < largos_antes, "não separou nada na página real"

    finos_antes = sum(1 for b in antes if (b.x2 - b.x1) < med * 0.25)
    finos_depois = sum(1 for b in depois if (b.x2 - b.x1) < med * 0.25)
    assert finos_depois <= finos_antes, \
        f"o corte criou {finos_depois - finos_antes} pedaços estreitos"


def test_comportamento_antigo_continua_disponivel():
    """`method='fixed'` reproduz o que havia antes da F1.5, para comparação."""
    img = Image.fromarray(_pagina())
    assert BoxService.generate_boxes_opencv(img, method="fixed", threshold=180)


# ----------------------------------------------------------------------
# Execução direta
# ----------------------------------------------------------------------

def _main():
    testes = [(n, o) for n, o in sorted(globals().items())
              if n.startswith("test_") and callable(o)]
    falhas = []
    for nome, fn in testes:
        try:
            fn()
            print(f"  PASS  {nome}")
        except Exception as e:
            falhas.append(nome)
            print(f"  FALHA {nome}\n          {type(e).__name__}: {e}")
    print(f"\n{len(testes) - len(falhas)}/{len(testes)} testes passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(_main())
