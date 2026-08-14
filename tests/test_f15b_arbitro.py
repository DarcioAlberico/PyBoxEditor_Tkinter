"""
F1.5b — o classificador arbitra o corte de glifo colado.

O perfil de tinta acha candidatos com recall alto e precisão de 28,6%: nas 9
páginas rotuladas ele propõe 73 cortes bons contra 182 falsos, e por isso o
separador *custava* 2,3 pontos de F1 em vez de render. O árbitro é o
classificador dizendo se as partes fazem mais sentido que o todo.

O que estes testes protegem é sobretudo o **padrão**: `separar_colados="auto"`
não separa quando não há árbitro. Voltar isso para `True` rearmaria a única
configuração que a medição reprova, e nada na saída denunciaria — os boxes
continuariam saindo, só que partidos no lugar errado.

Rodar sem pytest:      python tests/test_f15b_arbitro.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest
from PIL import Image

from core.box_model import BoxEntry
from core.services.box_service import BoxService


ALTURA, LARGURA = 80, 90


def _faixa_colada(larguras=(20, 20, 20), vao=5, altura=30):
    """Blocos de tinta encostados, com vale entre eles — o caso do `♞e5`."""
    total = sum(larguras) + vao * (len(larguras) - 1)
    img = np.zeros((altura, total), np.uint8)
    x = 0
    for i, lg in enumerate(larguras):
        img[4:altura - 4, x:x + lg] = 255
        x += lg + (vao if i < len(larguras) - 1 else 0)
    canvas = np.zeros((ALTURA, LARGURA), np.uint8)
    canvas[:img.shape[0], :img.shape[1]] = img
    return canvas


def _cenario():
    """(boxes, binarizada) com um box largo cortável e contexto para a mediana."""
    largo = [BoxEntry("", 0, 0, 70, 30)]
    contexto = [BoxEntry("", i * 25, 40, i * 25 + 20, 70) for i in range(10)]
    return largo + contexto, _faixa_colada()


def _pedacos_do_largo(saida):
    return [b for b in saida if b.y1 == 0]


class _Arbitro:
    """Classificador de mentira, com pontuações ditadas pelo teste."""

    def __init__(self, inteiro, parte):
        self.inteiro, self.parte = inteiro, parte
        self.recortes = []

    def __call__(self, recorte):
        self.recortes.append(np.asarray(recorte))
        largura = np.asarray(recorte).shape[1]
        # o primeiro recorte que chega é sempre o box inteiro
        return "x", (self.inteiro if largura >= 70 else self.parte)


# ----------------------------------------------------------------------
# A decisão do árbitro
# ----------------------------------------------------------------------

def test_partes_melhores_que_o_todo_cortam():
    boxes, img = _cenario()
    arbitro = _Arbitro(inteiro=0.30, parte=0.95)
    saida = BoxService.dividir_glifos_colados(
        boxes, img, arbitro=arbitro, imagem_cinza=img, margem=0.30)
    assert len(_pedacos_do_largo(saida)) == 3


def test_partes_piores_que_o_todo_nao_cortam():
    """É o `N` em negrito: partido, vira dois fragmentos sem sentido."""
    boxes, img = _cenario()
    arbitro = _Arbitro(inteiro=0.99, parte=0.20)
    saida = BoxService.dividir_glifos_colados(
        boxes, img, arbitro=arbitro, imagem_cinza=img, margem=0.30)
    assert len(_pedacos_do_largo(saida)) == 1


def test_a_margem_e_exigida_de_verdade():
    """Empate não corta: a margem tem que ser superada, não igualada."""
    boxes, img = _cenario()
    saida = BoxService.dividir_glifos_colados(
        boxes, img, arbitro=_Arbitro(inteiro=0.50, parte=0.80),
        imagem_cinza=img, margem=0.30)
    assert len(_pedacos_do_largo(saida)) == 1

    saida = BoxService.dividir_glifos_colados(
        boxes, img, arbitro=_Arbitro(inteiro=0.50, parte=0.81),
        imagem_cinza=img, margem=0.30)
    assert len(_pedacos_do_largo(saida)) == 3


def test_margem_maior_corta_menos():
    boxes, img = _cenario()
    quantos = []
    for margem in (0.0, 0.3, 0.6):
        saida = BoxService.dividir_glifos_colados(
            boxes, img, arbitro=_Arbitro(inteiro=0.40, parte=0.85),
            imagem_cinza=img, margem=margem)
        quantos.append(len(_pedacos_do_largo(saida)))
    assert quantos == sorted(quantos, reverse=True)


def test_vale_a_menor_parte_e_nao_a_media():
    """
    Basta um pedaço sem sentido para o corte ter sido estrago. Com a média, um
    pedaço bom encobriria o outro.
    """
    class Desigual:
        def __init__(self):
            self.n = 0

        def __call__(self, recorte):
            largura = np.asarray(recorte).shape[1]
            if largura >= 70:
                return "x", 0.50
            self.n += 1
            # duas partes ótimas e uma péssima: média 0,67, menor 0,05
            return "x", 0.05 if self.n == 2 else 0.98

    boxes, img = _cenario()
    saida = BoxService.dividir_glifos_colados(
        boxes, img, arbitro=Desigual(), imagem_cinza=img, margem=0.0)
    assert len(_pedacos_do_largo(saida)) == 1


def test_margem_padrao_e_a_medida():
    """
    0,00 desde a F33, e **a régua mudou junto com o número**.

    O 0,30 era o pico de F1 da página. A F30 mediu que esse pico virou platô de
    0,05 a 0,30 — o F1 deixou de decidir —, e a F31/F32 trocaram a moeda para
    "erro que atravessa a fila de revisão e o léxico". Nela, contra a de
    produção: +47 de saldo de texto, melhor saldo de invisível das quatro
    candidatas, ganha em 7 das 10 páginas e não perde em nenhuma.

    Este teste existe para o valor não voltar por acidente. Para voltar de
    propósito há motivo registrado: o 0,00 sobe os cortes falsos de 2 para 16, e
    7 deles saem de uma digitalização ruim. Ver `MARGEM_ARBITRO` e
    `medir_corte_falso.py`.
    """
    assert BoxService.MARGEM_ARBITRO == 0.00


# ----------------------------------------------------------------------
# O que o árbitro recebe
# ----------------------------------------------------------------------

def test_arbitro_recebe_o_cinza_e_nao_o_binarizado():
    """O modelo foi treinado em tom de cinza; passar o binarizado o cegaria."""
    boxes, binaria = _cenario()
    cinza = np.full((ALTURA, LARGURA), 137, np.uint8)

    arbitro = _Arbitro(inteiro=0.9, parte=0.1)
    BoxService.dividir_glifos_colados(boxes, binaria, arbitro=arbitro,
                                      imagem_cinza=cinza)
    assert arbitro.recortes, "o árbitro nem foi chamado"
    assert all(np.all(r == 137) for r in arbitro.recortes)


def test_arbitro_sem_cinza_falha_alto():
    """
    Cair no binarizado em silêncio daria um árbitro que decide mal sem que
    nada na saída denuncie.
    """
    boxes, img = _cenario()
    with pytest.raises(ValueError, match="cinza"):
        BoxService.dividir_glifos_colados(boxes, img, arbitro=_Arbitro(0.9, 0.1))


def test_arbitro_so_e_consultado_para_quem_tem_corte_candidato():
    """Consultar o modelo em cada box da página custaria caro à toa."""
    boxes = [BoxEntry("", i * 25, 0, i * 25 + 18, 30) for i in range(10)]
    img = np.zeros((40, 300), np.uint8)
    for b in boxes:
        img[4:26, b.x1:b.x2] = 255

    arbitro = _Arbitro(inteiro=0.9, parte=0.1)
    BoxService.dividir_glifos_colados(boxes, img, arbitro=arbitro,
                                      imagem_cinza=img)
    assert arbitro.recortes == []


# ----------------------------------------------------------------------
# Sem árbitro: o comportamento antigo, preservado
# ----------------------------------------------------------------------

def test_sem_arbitro_corta_como_antes():
    boxes, img = _cenario()
    saida = BoxService.dividir_glifos_colados(boxes, img)
    assert len(_pedacos_do_largo(saida)) == 3


# ----------------------------------------------------------------------
# O padrão de generate_boxes_opencv — o ponto que mais importa
# ----------------------------------------------------------------------

def _pagina_com_colagem():
    """
    Imagem PIL cuja segmentação produz **um** box largo, cortável.

    Os três blocos precisam se tocar de verdade, senão o `findContours` já os
    devolve separados e não há nada para o separador fazer — foi assim que a
    primeira versão deste teste passou a medir outra coisa. A ponte de 2 px na
    base reproduz o caso real: encostam pela serifa, e o perfil de tinta
    continua tendo vale entre eles.
    """
    arr = np.full((ALTURA, LARGURA), 255, np.uint8)
    faixa = _faixa_colada()
    arr[faixa > 0] = 0
    arr[26:28, 0:70] = 0                       # a ponte
    for i in range(10):
        arr[40:70, i * 25:i * 25 + 20] = 0
    return Image.fromarray(arr)


def _tem_corte(img, **kwargs):
    boxes = BoxService.generate_boxes_opencv(img, descartar_nao_texto=False,
                                             **kwargs)
    return len([b for b in boxes if b.y1 < 35]) > 1


def test_auto_nao_separa_sem_arbitro():
    """O padrão não pode ser a configuração que a medição reprova."""
    assert not _tem_corte(_pagina_com_colagem())


def test_auto_separa_quando_ha_arbitro():
    img = _pagina_com_colagem()
    assert _tem_corte(img, arbitro=lambda r: ("x", 0.99 if
                                              np.asarray(r).shape[1] < 60 else 0.1))


def test_true_separa_mesmo_sem_arbitro():
    """Mantido para reproduzir as medições da F1.5, não como recomendação."""
    assert _tem_corte(_pagina_com_colagem(), separar_colados=True)


def test_false_nunca_separa():
    img = _pagina_com_colagem()
    assert not _tem_corte(img, separar_colados=False)
    assert not _tem_corte(img, separar_colados=False,
                          arbitro=lambda r: ("x", 0.99))


def test_padrao_do_parametro_e_auto():
    import inspect
    assinatura = inspect.signature(BoxService.generate_boxes_opencv)
    assert assinatura.parameters["separar_colados"].default == "auto"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
