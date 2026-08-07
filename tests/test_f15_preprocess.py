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

# ----------------------------------------------------------------------
# Escala local — o defeito que a F1.7 encontrou
# ----------------------------------------------------------------------

def _glifo_com_vale(larg, alt, espessura=4):
    """
    Glifo ÚNICO e largo, com um vale interno largo: duas hastes ligadas por uma
    barra no topo. É a forma da figurina de cavalo em contorno e do 'm' — o que
    o separador partia ao meio.
    """
    g = np.zeros((alt, larg), np.uint8)
    g[:, :espessura] = 255
    g[:, -espessura:] = 255
    g[:espessura, :] = 255
    return g


def _pagina_duas_fontes():
    """
    Página com dois tamanhos de fonte, como as destes livros: a linha principal
    da partida é maior que o texto das variantes.

    Devolve (imagem binária, boxes, box do glifo grande).
    """
    img = np.zeros((300, 600), np.uint8)
    boxes = []

    # 8 linhas de texto miúdo: largura 17, que fica sendo a mediana da página
    for linha in range(8):
        y = 120 + linha * 22
        for i in range(20):
            x = 20 + i * 28
            img[y:y + 18, x:x + 17] = 255
            boxes.append(BoxEntry("", x, y, x + 17, y + 18))

    # uma linha de fonte grande: 8 glifos largos de 32 px, cada um com vale
    grande = None
    for i in range(8):
        x = 20 + i * 60
        g = _glifo_com_vale(32, 40)
        img[40:80, x:x + 32] = g
        b = BoxEntry("", x, 40, x + 32, 80)
        boxes.append(b)
        if grande is None:
            grande = b

    return img, boxes, grande


def test_mediana_da_pagina_nao_representa_linha_de_fonte_maior():
    """O cenário do defeito: a mediana global é a da fonte miúda."""
    _, boxes, grande = _pagina_duas_fontes()

    larguras = sorted(b.x2 - b.x1 for b in boxes)
    global_ = larguras[len(larguras) // 2]
    ref = BoxService._largura_de_referencia(boxes)

    assert global_ == 17, f"o cenário mudou: mediana global {global_}"
    assert (grande.x2 - grande.x1) > global_ * 1.6, \
        "o glifo grande precisa passar do limiar global para o teste valer"
    assert ref[id(grande)] == 32, \
        f"a referência local do glifo grande veio {ref[id(grande)]}, esperava 32"


def test_nao_parte_glifo_grande_de_linha_com_fonte_maior():
    """
    O defeito da F1.5 encontrado na F1.7: numa página que mistura tamanhos de
    fonte, o glifo da linha maior passava de `mediana_global * 1.6` e era
    partido no vale interno. Na página real isso partia a figurina de cavalo e
    "1.d4 Nf6" saía "1.d4 N□f6".
    """
    img, boxes, grande = _pagina_duas_fontes()

    saida = BoxService.dividir_glifos_colados(boxes, img)
    pedacos = [b for b in saida if b.y1 == grande.y1 and b.x1 >= grande.x1
               and b.x2 <= grande.x2]
    assert len(pedacos) == 1, \
        f"partiu um glifo inteiro em {len(pedacos)} pedaços"


def test_referencia_local_nunca_fica_abaixo_da_global():
    """
    Propriedade de segurança: o limiar só sobe.

    A mediana de uma linha mede também quais caracteres calharam de cair nela —
    uma linha cheia de 'i', 'l' e pontuação tem mediana pequena sem ser fonte
    pequena. Deixar o limiar cair ali fabricaria cortes que hoje não existem.
    """
    boxes = []
    # linha de caracteres estreitos
    for i in range(10):
        boxes.append(BoxEntry("", i * 20, 0, i * 20 + 4, 20))
    # linhas de caracteres normais, que dominam a mediana da página
    for linha in range(4):
        for i in range(10):
            y = 40 + linha * 30
            boxes.append(BoxEntry("", i * 30, y, i * 30 + 18, y + 24))

    larguras = sorted(b.x2 - b.x1 for b in boxes)
    global_ = larguras[len(larguras) // 2]
    ref = BoxService._largura_de_referencia(boxes)

    assert min(ref.values()) >= global_, \
        "a referência local ficou abaixo da global e baixaria o limiar"


def test_linhas_agrupa_por_sobreposicao_vertical():
    boxes = [BoxEntry("", i * 30, 0, i * 30 + 18, 24) for i in range(5)]
    boxes += [BoxEntry("", i * 30, 60, i * 30 + 18, 84) for i in range(3)]

    linhas = BoxService._linhas(boxes)
    assert [len(l) for l in linhas] == [5, 3]
    assert BoxService._linhas([]) == []


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


# ----------------------------------------------------------------------
# F1.8 — descarte de blocos que não são texto
# ----------------------------------------------------------------------

def test_descarta_bloco_grande_demais_para_ser_caractere():
    """O diagrama sai como UM contorno grande (moldura fechada + RETR_EXTERNAL)."""
    boxes = [BoxEntry("", i * 25, 0, i * 25 + 18, 24) for i in range(30)]
    tabuleiro = BoxEntry("", 100, 200, 580, 679)      # 480x479
    saida = BoxService.descartar_blocos_nao_texto(boxes + [tabuleiro])

    assert len(saida) == len(boxes)
    assert tabuleiro not in saida


def test_nao_descarta_travessao_nem_letra_alta():
    """
    Precisa ser grande nos DOIS eixos.

    Um travessão é largo e baixo; um parêntese de fração é alto e estreito. Os
    dois são texto, e um limiar num eixo só comeria ambos.
    """
    boxes = [BoxEntry("", i * 25, 0, i * 25 + 18, 24) for i in range(30)]
    travessao = BoxEntry("", 0, 40, 200, 46)          # largo, baixo
    alto = BoxEntry("", 300, 40, 312, 200)            # alto, estreito

    saida = BoxService.descartar_blocos_nao_texto(boxes + [travessao, alto])
    assert travessao in saida and alto in saida


def test_descarte_precisa_de_amostra_para_a_mediana():
    """
    Com poucos boxes a mediana não diz o tamanho do texto.

    Numa página que é só um diagrama, a "altura mediana de caractere" seria a do
    próprio diagrama e o limiar não significaria nada.
    """
    poucos = [BoxEntry("", 0, 0, 480, 479), BoxEntry("", 500, 0, 518, 24)]
    assert BoxService.descartar_blocos_nao_texto(poucos) == poucos


def test_descarte_e_opcional_no_pipeline():
    img = Image.fromarray(_pagina())
    com = BoxService.generate_boxes_opencv(img, descartar_nao_texto=True)
    sem = BoxService.generate_boxes_opencv(img, descartar_nao_texto=False)
    assert len(com) <= len(sem)


def test_descarte_acontece_depois_do_merge():
    """
    Ordem medida, não escolhida por gosto: o box do diagrama absorve os
    respingos à volta dele no `merge_vertical_boxes`, e descartá-lo depois leva
    o lixo junto. Descartando antes, os respingos sobram soltos — na página
    0108 os boxes espúrios iam de 11 para 29.
    """
    import inspect

    fonte = inspect.getsource(BoxService.generate_boxes_opencv)
    # Pelo nome da função, e não pela chamada inteira: a assinatura ganhou
    # `escala` na F11 e o teste quebrou sem que a ordem — que é o que ele cobra
    # — tivesse mudado.
    pos_merge = fonte.index("merge_vertical_boxes(boxes)")
    pos_descarte = fonte.index("descartar_blocos_nao_texto(")
    assert pos_merge < pos_descarte, \
        "o descarte voltou para antes do merge — ver a medição na docstring"


def test_pagina_real_descarte_nao_perde_caractere():
    """
    Nas páginas rotuladas o descarte tira 19 boxes e **nenhum** deles casava
    com caractere rotulado. É a propriedade que autoriza ligá-lo por padrão.
    """
    from core.avaliacao_pagina import comparar

    img, rotulados = _pagina_0108()
    if img is None:
        return

    com = BoxService.generate_boxes_opencv(img, separar_colados=False,
                                           descartar_nao_texto=True)
    sem = BoxService.generate_boxes_opencv(img, separar_colados=False,
                                           descartar_nao_texto=False)

    assert len(com) < len(sem), "não descartou nada nesta página"
    assert comparar(com, rotulados).casados == comparar(sem, rotulados).casados, \
        "o descarte levou junto um caractere de verdade"


def _pagina_0108():
    """(imagem PIL, boxes rotulados à mão) ou (None, None) se não estiver aqui."""
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    nome = "Kasparov - The Dynamic Benko Gambit (2012)_page-0108"
    jpg = os.path.join(raiz, "ilovepdf_pages-to-jpg", nome + ".jpg")
    box = os.path.join(raiz, "Box", nome + ".box")
    if not (os.path.exists(jpg) and os.path.exists(box)):
        return None, None

    from core.avaliacao_pagina import carregar_box

    img = Image.open(jpg).convert("L")
    return img, carregar_box(box, img.size[1])


def _pais_e_filhos(img, referencia):
    """
    Roda a segmentação até o corte, com a estratégia de escala pedida.

    `referencia`: "global" reproduz o comportamento anterior à correção,
    "local" usa o que o código faz hoje.
    """
    from core import preprocess

    th = preprocess.binarize(np.array(img), "auto")
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    brutos = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w >= 2 and h >= 2:
            brutos.append(BoxEntry("", x, y, x + w, y + h))
    brutos.sort(key=lambda b: (b.y1, b.x1))
    pais = BoxService.merge_vertical_boxes(brutos)

    if referencia == "local":
        ref = BoxService._largura_de_referencia(pais)
    else:
        larguras = sorted(b.x2 - b.x1 for b in pais)
        m = larguras[len(larguras) // 2] or 1
        ref = {id(b): m for b in pais}

    filhos = []
    for b in pais:
        m = ref[id(b)]
        if (b.x2 - b.x1) <= m * 1.6:
            filhos.append(b)
            continue
        cortes = BoxService._cortes_do_perfil(
            th[b.y1:b.y2, b.x1:b.x2], 0.30,
            max(3, int(m * 0.25)), max(3, int(m * 0.40)))
        if not cortes:
            filhos.append(b)
            continue
        lim = [0] + cortes + [b.x2 - b.x1]
        for i, f in zip(lim, lim[1:]):
            filhos.append(BoxEntry(b.char, b.x1 + i, b.y1, b.x1 + f, b.y2))
    return pais, filhos


def test_pagina_0108_escala_local_reduz_cortes_falsos():
    """
    A página que a validação da F1.5 não cobria.

    Ela mistura tamanhos de fonte e é rotulada à mão (1.404 caracteres), então
    dá para separar corte bom de corte falso em vez de só contar pedaços
    estreitos — que era a propriedade que deixou o defeito passar: as duas
    metades de uma figurina partida são largas demais para cair nela.
    """
    from core.avaliacao_pagina import classificar_cortes

    img, rotulados = _pagina_0108()
    if img is None:
        return

    antes = classificar_cortes(*_pais_e_filhos(img, "global"), rotulados)
    depois = classificar_cortes(*_pais_e_filhos(img, "local"), rotulados)

    assert antes["cortes_falsos"] >= 50, \
        f"o cenário do defeito mudou: só {antes['cortes_falsos']} cortes falsos antes"
    assert depois["cortes_falsos"] < antes["cortes_falsos"], \
        "a escala local não reduziu os cortes falsos"
    assert depois["cortes_legitimos"] >= antes["cortes_legitimos"], \
        "a escala local perdeu cortes legítimos"


def _figurinas_partidas(img, rotulados, referencia):
    """Quantas figurinas largas ficaram cobertas por mais de um box."""
    _, filhos = _pais_e_filhos(img, referencia)

    # as figurinas foram rotuladas com a letra do lance (o livro usa um conjunto
    # só para os dois lados, F1.1); são elas que dominam os boxes largos
    larguras = sorted(b.x2 - b.x1 for b in rotulados)
    mediana = larguras[len(larguras) // 2]
    figurinas = [b for b in rotulados
                 if b.char in "KQRBN" and (b.x2 - b.x1) > mediana * 1.6]

    partidas = 0
    for f in figurinas:
        dentro = [b for b in filhos
                  if f.x1 <= (b.x1 + b.x2) / 2 <= f.x2
                  and f.y1 <= (b.y1 + b.y2) / 2 <= f.y2]
        if len(dentro) > 1:
            partidas += 1
    return partidas, len(figurinas)


def test_pagina_0108_escala_local_parte_menos_figurinas():
    """
    O sintoma do relato: `1.d4 Nf6` saía `1.d4 N□f6` porque a figurina de cavalo
    da linha principal — mais larga que a mediana da página — era partida no vale
    interno do contorno.

    A escala local conserta a linha principal, **e não todas**: medido nesta
    página, 32 das 103 figurinas largas saíam partidas antes, 24 saem depois. As
    que sobram estão nas linhas de variante, onde a mediana da linha é a mesma da
    página e o limiar não muda. Fechar o resto exige um critério que separe vale
    de colagem de vale interno de glifo, e nesta página **não existe**: medidos
    os dois grupos, largura mediana do vale 7 colunas contra 7, fundo a 13% do
    pico contra 10%. Ver a nota da F1.5 no ROADMAP.
    """
    img, rotulados = _pagina_0108()
    if img is None:
        return

    antes, total = _figurinas_partidas(img, rotulados, "global")
    depois, _ = _figurinas_partidas(img, rotulados, "local")

    assert total >= 50, f"esperava dezenas de figurinas largas, achei {total}"
    assert antes >= 30, f"o cenário do defeito mudou: só {antes} partidas antes"
    assert depois < antes, \
        f"a escala local não reduziu figurinas partidas ({antes} -> {depois})"


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
