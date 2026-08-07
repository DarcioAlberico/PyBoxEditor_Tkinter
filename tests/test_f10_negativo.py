"""
F10 — texto impresso em negativo (branco sobre tarja preta ou colorida).

O risco desta fase tem os mesmos dois lados da F8.1, e a proporção entre eles é
diferente.

**Não ler.** A tarja com o nome dos jogadores vira um borrão de tinta na
binarização, `findContours` com RETR_EXTERNAL devolve um box só e os caracteres
de dentro não chegam a existir. Medido na página 33 do Yusupov, antes desta
fase: 6 tarjas, 6 boxes, zero caracteres.

**Inventar box onde não há texto.** Faixa cheia também é foto, logotipo e barra
de rodapé. Aceitar uma delas troca um box espúrio por dezenas. Por isso metade
destes testes é sobre **não** aceitar: retângulo sólido sem texto, bloco de
ruído, caractere gordo, e a faixa que não tem borda cheia.

O terceiro risco é o que a medição pegou e nenhum teste anteciparia: as caixas
novas voltando fora de ordem fazem `merge_vertical_boxes` colar a página
inteira — 1.889 boxes viraram 27. `test_a_lista_volta_ordenada` é o que guarda
essa porta.

Rodar sem pytest:      python tests/test_f10_negativo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pytest
from PIL import Image

from core import formato_box, negativo, preprocess, vertical
from core.box_model import BoxEntry
from core.services.box_service import BoxService


# ----------------------------------------------------------------------
# Apoio: uma página com tarja
# ----------------------------------------------------------------------

def _tarja(largura=460, altura=60, texto="ABCDEF", fundo=0, tinta=255,
           tira=False):
    """
    Uma tarja: retângulo de `fundo` com `texto` claro dentro.

    Com `tira`, põe em cima a tira decorativa hachurada do Yusupov — é ela que
    fundia meia linha num componente só antes da apara.
    """
    img = np.full((altura, largura), fundo, np.uint8)
    cv2.putText(img, texto, (20, altura - 15), cv2.FONT_HERSHEY_SIMPLEX,
                1.2, int(tinta), 3)
    if tira:
        # Hachura: ~1/3 de pixel claro em TODA linha. É o perfil medido na tira
        # do Yusupov — 0,54–0,74 de tinta por linha, contra ~1,00 da tarja.
        # Alternar linha cheia com linha hachurada não serviria: a apara para
        # na primeira linha cheia, e é isso que ela tem de fazer.
        pontos = np.random.RandomState(0).rand(14, largura) < 0.35
        faixa = np.full((14, largura), fundo, np.uint8)
        faixa[pontos] = tinta
        img = np.vstack([faixa, img])
    return img


def _pagina_com_tarja(**kw):
    """Página branca com uma linha de texto normal e uma tarja embaixo."""
    img = np.full((300, 500), 245, np.uint8)
    for i in range(6):
        cv2.putText(img, "A", (20 + i * 55, 80), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, 20, 2)
    tarja = _tarja(**kw)
    img[150:150 + tarja.shape[0], 20:20 + tarja.shape[1]] = tarja
    return img


def _pagina_sem_tarja():
    img = np.full((300, 500), 245, np.uint8)
    for linha in range(3):
        for i in range(8):
            cv2.putText(img, "AB", (20 + i * 55, 80 + linha * 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, 20, 2)
    return img


def _brutos(th):
    """Os boxes de RETR_EXTERNAL, como `generate_boxes_opencv` os faz."""
    contornos, _ = cv2.findContours(th, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in contornos:
        x, y, w, h = cv2.boundingRect(c)
        if w >= 2 and h >= 2:
            boxes.append(BoxEntry("", x, y, x + w, y + h))
    boxes.sort(key=lambda b: (b.y1, b.x1))
    return boxes


def _rodar(cinza):
    """(boxes, th, faixas) da fase inteira sobre uma página em cinza."""
    th = preprocess.binarize(cinza, "auto")
    return negativo.aplicar(cinza, th, _brutos(th))


# ----------------------------------------------------------------------
# Positivar
# ----------------------------------------------------------------------

def test_positivar_troca_a_polaridade():
    recorte = np.array([[0, 255], [40, 200]], np.uint8)
    assert negativo.positivar(recorte).tolist() == [[255, 0], [215, 55]]


def test_positivar_ida_e_volta():
    recorte = np.random.randint(0, 256, (8, 8), dtype=np.uint8)
    assert (negativo.positivar(negativo.positivar(recorte)) == recorte).all()


def test_recorte_de_pe_positiva_o_box_marcado():
    """
    O funil da F8.1 é o mesmo desta fase: quem classifica pede o glifo como o
    modelo o viu no treino.
    """
    pagina = np.zeros((20, 20), np.uint8)
    pagina[5:15, 5:15] = 255

    normal = vertical.recorte_de_pe(pagina, BoxEntry("", 5, 5, 15, 15))
    marcado = vertical.recorte_de_pe(
        pagina, BoxEntry("", 5, 5, 15, 15, negativo=True))

    assert normal.mean() == 255
    assert marcado.mean() == 0


def test_recorte_de_pe_compoe_negativo_com_angulo():
    """As duas voltas no mesmo funil, e o ângulo depois da polaridade."""
    pagina = np.zeros((10, 10), np.uint8)
    pagina[0, :] = 255                       # linha clara no topo

    recorte = vertical.recorte_de_pe(
        pagina, BoxEntry("", 0, 0, 10, 10, angulo=90, negativo=True))

    assert recorte.shape == (10, 10)
    # positivado, a linha do topo vira escura; girado 90°, ela vai para a
    # coluna da direita
    assert (recorte[:, -1] == 0).all()
    assert (recorte[:, 0] == 255).all()


# ----------------------------------------------------------------------
# A geometria propõe
# ----------------------------------------------------------------------

def test_a_tarja_e_candidata():
    cinza = _pagina_com_tarja()
    th = preprocess.binarize(cinza, "auto")
    assert len(negativo.candidatos(th, _brutos(th))) == 1


def test_caractere_normal_nao_e_candidato():
    """Um 'A' é estreito e vazado; nenhum deles pode virar faixa."""
    cinza = _pagina_sem_tarja()
    th = preprocess.binarize(cinza, "auto")
    assert negativo.candidatos(th, _brutos(th)) == []


def test_a_apara_tira_a_tira_decorativa():
    """
    O retângulo cheio se acha pelas bordas.

    Sem a apara, a tira hachurada encosta no topo das letras e funde meia linha
    num componente só — medido, 88 componentes numa tarja de 20 caracteres.
    """
    cinza = _pagina_com_tarja(tira=True)
    th = preprocess.binarize(cinza, "auto")
    candidato = negativo.candidatos(th, _brutos(th))[0]
    faixa = negativo.faixa_solida(th, candidato)

    assert faixa is not None
    # a tira tem 14 linhas e fica em cima; a faixa começa depois dela
    assert faixa.y1 >= candidato.y1 + 10
    assert faixa.height >= 40


def test_a_decoracao_escura_nao_vira_box():
    """
    A rede que pega o que a apara deixou passar.

    A tira aqui é **escura**: as linhas dela passam de `SOLIDO`, então a apara
    para na primeira e a decoração entra no recorte. Medido, três das 438
    tarjas do Yusupov são assim, e elas devolviam 119, 112 e 22 boxes para
    nomes de ~20 caracteres — o excedente é hachura, e ela entra no meio do
    texto na ordem de leitura.
    """
    tarja = _tarja()
    tira = np.zeros((16, tarja.shape[1]), np.uint8)
    tira[3::6, 5::17] = 255          # respingos claros esparsos: ~1% da tira
    tarja = np.vstack([tira, tarja])

    img = _pagina_sem_tarja()
    img[150:150 + tarja.shape[0], 20:20 + tarja.shape[1]] = tarja

    boxes, _th, faixas = _rodar(img)
    assert len(faixas) == 1

    marcados = [b for b in boxes if b.negativo]
    assert len(marcados) >= 6, "as letras sumiram junto com a decoração"
    # a tira tem 16 linhas e fica no topo da faixa; nada de lá pode virar box
    limite = faixas[0].y1 + 16
    assert all(b.y2 > limite for b in marcados), \
        "respingo da tira decorativa virou box"


def test_tarja_de_duas_linhas_mantem_as_duas():
    """
    O filtro de linha mede a faixa do texto inteira, não uma linha só.

    A tarja de duas linhas existe no material — *"Section 2 – The Typical /
    Volga Structure"*, no Kasparov, 715x112 com letras de ~35 px. A proporção
    aqui é a de lá, e não por acaso: `ALTURA_GLIFO` mede o glifo contra a
    altura da **faixa**, então a tarja de duas linhas passa raspando e a de
    três não passa (ver o cabeçalho de `core/negativo.py`).
    """
    tarja = np.zeros((112, 460), np.uint8)
    cv2.putText(tarja, "ABCDEF", (20, 48), cv2.FONT_HERSHEY_SIMPLEX, 1.55, 255, 3)
    cv2.putText(tarja, "GHIJKL", (20, 106), cv2.FONT_HERSHEY_SIMPLEX, 1.55, 255, 3)

    # A página é maior que a das outras montagens de propósito: uma tarja de
    # duas linhas ocupando um terço da folha faz o Otsu devolver 37% de tinta,
    # o "auto" cai no adaptativo (`preprocess.tinta_plausivel`) e o fundo da
    # tarja deixa de ser tinta. Página de livro não tem essa proporção.
    img = np.full((700, 620), 245, np.uint8)
    for linha in range(6):
        for i in range(9):
            cv2.putText(img, "AB", (20 + i * 62, 60 + linha * 44),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, 20, 2)
    img[450:562, 20:480] = tarja

    boxes, _th, faixas = _rodar(img)
    assert len(faixas) == 1

    marcados = [b for b in boxes if b.negativo]
    meio = faixas[0].y1 + faixas[0].height / 2
    assert any(b.y2 <= meio for b in marcados), "a primeira linha sumiu"
    assert any(b.y1 >= meio for b in marcados), "a segunda linha sumiu"


def test_faixa_sem_borda_cheia_volta_inteira():
    """
    Sem linha cheia, a apara devolve a faixa como está — e quem julga é o
    conteúdo.

    Aparar não pode ser condição de aceite: medido na página 264 do Kasparov,
    a tarja *"6...♘bd7"* é cinza-clara, a binarização marca 60%–87% dela e
    nenhuma linha chega a `SOLIDO`. Exigir moldura cheia recusava uma tarja
    legível de nove caracteres.
    """
    ruido = (np.random.RandomState(0).rand(60, 400) < 0.5).astype(np.uint8) * 255
    caixa = BoxEntry("", 0, 0, 400, 60)
    faixa = negativo.faixa_solida(ruido, caixa)

    assert faixa is not None
    assert (faixa.x1, faixa.y1, faixa.x2, faixa.y2) == (0, 0, 400, 60)


def test_bloco_de_ruido_e_recusado_pelo_conteudo():
    """A recusa mora no teste de conteúdo, não no da moldura."""
    img = np.full((300, 500), 245, np.uint8)
    ruido = np.random.RandomState(0).rand(60, 460) < 0.5
    bloco = np.zeros((60, 460), np.uint8)
    bloco[ruido] = 255
    img[150:210, 20:480] = bloco

    _boxes, _th, faixas = _rodar(img)
    assert faixas == []


# ----------------------------------------------------------------------
# O conteúdo dispõe
# ----------------------------------------------------------------------

def test_a_tarja_vira_caracteres():
    cinza = _pagina_com_tarja(texto="ABCDEF")
    boxes, _th, faixas = _rodar(cinza)

    assert len(faixas) == 1
    marcados = [b for b in boxes if b.negativo]
    assert len(marcados) >= 6, "os caracteres da tarja não saíram"
    assert all(faixas[0].x1 <= b.x1 and b.x2 <= faixas[0].x2 for b in marcados)


def test_a_tarja_sai_da_lista():
    """O box do borrão é substituído, não somado."""
    cinza = _pagina_com_tarja()
    th = preprocess.binarize(cinza, "auto")
    candidato = negativo.candidatos(th, _brutos(th))[0]

    boxes, _th, _faixas = negativo.aplicar(cinza, th, _brutos(th))
    largos = [b for b in boxes if b.width >= candidato.width]
    assert largos == [], "a tarja continua na lista como um box só"


def test_retangulo_solido_sem_texto_e_recusado():
    """Sem nada claro dentro, não há o que ler — e o box fica como estava."""
    img = np.full((300, 500), 245, np.uint8)
    img[150:210, 20:480] = 0

    boxes, _th, faixas = _rodar(img)
    assert faixas == []
    assert not any(b.negativo for b in boxes)


def test_faixa_com_dois_respingos_e_recusada():
    """Dois pontos claros não são uma linha de texto."""
    img = np.full((300, 500), 245, np.uint8)
    img[150:210, 20:480] = 0
    img[170:190, 100:120] = 255
    img[170:190, 300:320] = 255

    _boxes, _th, faixas = _rodar(img)
    assert faixas == []


def test_pagina_normal_nao_ganha_marca():
    """A porta que protege quem já estava certo."""
    cinza = _pagina_sem_tarja()
    boxes, th, faixas = _rodar(cinza)

    assert faixas == []
    assert not any(b.negativo for b in boxes)
    assert (th == preprocess.binarize(cinza, "auto")).all(), \
        "a binarização foi mexida sem faixa nenhuma aceita"


def test_a_tarja_colorida_tambem_conta():
    """
    Preto não é requisito; contraste é.

    A página chega em tom de cinza — uma tarja azul-escura ou vermelha vira um
    retângulo cinza-escuro, e é isso que o detector vê.
    """
    cinza = _pagina_com_tarja(fundo=70, tinta=250)
    _boxes, _th, faixas = _rodar(cinza)
    assert len(faixas) == 1


# ----------------------------------------------------------------------
# O que a fase entrega para o resto do pipeline
# ----------------------------------------------------------------------

def test_o_th_volta_com_a_faixa_invertida():
    """
    `dividir_glifos_colados` corta pelo perfil de tinta. Sem inverter a faixa
    no `th`, o vale entre duas letras da tarja é um pico.
    """
    cinza = _pagina_com_tarja()
    _boxes, th, faixas = _rodar(cinza)

    faixa = faixas[0]
    dentro = th[faixa.y1:faixa.y2, faixa.x1:faixa.x2]
    assert (dentro > 0).mean() < 0.4, "a faixa continua sendo um bloco de tinta"


def test_a_lista_volta_ordenada():
    """
    A regressão que a medição pegou: `merge_vertical_boxes` mede a distância
    vertical como `b2.y1 - b1.y2` e aceita valor negativo. Fora de ordem, uma
    letra da tarja casa com um box do outro lado da página e a caixa resultante
    absorve tudo que cruza a sua coluna — 1.889 boxes viraram 27.
    """
    cinza = _pagina_com_tarja()
    boxes, _th, _faixas = _rodar(cinza)

    chaves = [(b.y1, b.x1) for b in boxes]
    assert chaves == sorted(chaves)


def test_o_merge_nao_come_a_pagina():
    """A mesma propriedade, cobrada onde ela quebrou."""
    cinza = _pagina_com_tarja()
    boxes, _th, _faixas = _rodar(cinza)
    depois = BoxService.merge_vertical_boxes(boxes)

    assert len(depois) >= len(boxes) * 0.5, \
        f"o merge colapsou a página: {len(boxes)} -> {len(depois)}"


def test_geracao_completa_le_a_tarja():
    """A fase dentro do `generate_boxes_opencv`, que é quem a UI chama."""
    cinza = _pagina_com_tarja(texto="ABCDEF")
    boxes = BoxService.generate_boxes_opencv(Image.fromarray(cinza))

    marcados = [b for b in boxes if b.negativo]
    assert len(marcados) >= 6
    assert all(b.width < 100 for b in marcados), \
        "saiu um box do tamanho da tarja, não dos caracteres"


# ----------------------------------------------------------------------
# A marca sobrevive ao caminho todo
# ----------------------------------------------------------------------

def test_o_box_guarda_a_polaridade_no_disco():
    original = BoxEntry("A", 10, 20, 30, 40, negativo=True)
    texto = formato_box.escrever_texto([original], 1000)
    voltou = formato_box.ler_texto(texto, 1000)

    assert len(voltou) == 1
    assert voltou[0].negativo is True
    assert voltou[0].char == "A"


def test_polaridade_e_angulo_juntos_no_disco():
    original = BoxEntry("A", 10, 20, 30, 40, angulo=270, negativo=True)
    voltou = formato_box.ler_texto(
        formato_box.escrever_texto([original], 1000), 1000)[0]

    assert (voltou.angulo, voltou.negativo) == (270, True)


def test_box_normal_grava_o_arquivo_de_antes():
    """
    Byte a byte igual: a extensão só aparece quando é preciso.
    """
    linha = formato_box.formatar_linha(BoxEntry("A", 10, 20, 30, 40), 1000)
    assert linha == "A 10 960 30 980 0"


def test_o_oitavo_campo_obriga_o_setimo():
    """Sem o `0` do ângulo, o `1` da polaridade cairia na posição errada."""
    linha = formato_box.formatar_linha(
        BoxEntry("A", 10, 20, 30, 40, negativo=True), 1000)
    assert linha == "A 10 960 30 980 0 0 1"


def test_arquivo_de_terceiro_com_oitavo_campo_estranho_nao_derruba_o_box():
    voltou = formato_box.ler_texto("A 10 960 30 980 0 0 xpto", 1000)
    assert len(voltou) == 1
    assert voltou[0].negativo is False


def test_as_metades_herdam_a_polaridade():
    partes = BoxService.split_box(BoxEntry("", 0, 0, 40, 10, negativo=True))
    assert all(p.negativo for p in partes)


def test_o_clamp_preserva_a_polaridade():
    preso = BoxService.clamp_box(
        BoxEntry("A", -5, 0, 40, 10, negativo=True), 30, 30)
    assert preso.negativo is True


def test_o_estado_do_historico_carrega_a_polaridade():
    original = BoxEntry("A", 1, 2, 3, 4, 0.5, "neural", 90, True)
    assert BoxEntry.from_state(original.as_state()) == original


def test_estado_antigo_de_oito_campos_continua_carregando():
    """O `.pyboxsession.json` gravado antes da F10 tem oito campos."""
    antigo = ("A", 1, 2, 3, 4, 0.5, "neural", 90)
    assert BoxEntry.from_state(antigo).negativo is False


# ----------------------------------------------------------------------
# A página real
# ----------------------------------------------------------------------

def _pagina_do_yusupov(indice=33, dpi=300):
    """A página real, ou None quando o PDF não está na máquina."""
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    import glob

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
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.h, pix.w, pix.n)
    doc.close()
    return (cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
            if pix.n >= 3 else arr[:, :, 0].copy())


def test_a_pagina_real_tem_seis_tarjas_e_elas_viram_texto():
    """
    A página 33 do *Chess Evolution 1*: seis exercícios, seis tarjas.

    Antes desta fase eram 6 boxes de 663x55 e zero caracteres.
    """
    cinza = _pagina_do_yusupov()
    if cinza is None:
        pytest.skip("o PDF do Yusupov não está distribuído com o código")

    boxes, _th, faixas = _rodar(cinza)
    assert len(faixas) == 6, f"eram 6 tarjas, achou {len(faixas)}"

    marcados = [b for b in boxes if b.negativo]
    assert len(marcados) > 100, \
        f"6 nomes de jogador dão bem mais que {len(marcados)} caracteres"
    # nenhum deles pode ter o tamanho da tarja
    assert max(b.width for b in marcados) < 200


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
