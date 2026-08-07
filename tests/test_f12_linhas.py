"""
F12 — o box que engoliu duas linhas.

É o defeito simétrico ao da F1.5b: lá dois glifos vizinhos se tocam na
horizontal e o contorno sai largo; aqui o descendente de uma linha ('y', 'g',
'p') encosta na linha de baixo e o contorno sai **alto**. Medido nas 10 páginas
rotuladas: 231 caracteres ficam sem box por estarem colados a um vizinho, e 71
boxes cobrem rótulos de duas linhas ao mesmo tempo.

O que estes testes guardam, além do corte em si, é a **lasca**: o pedaço curto
que sobra da linha vizinha. Emiti-la piora o resultado — cada caractere
recuperado custa 2,2 boxes espúrios, e o F1 cai de 94,48 para 93,95. Descartá-la
é o que faz a fase pagar.

Rodar sem pytest:      python tests/test_f12_linhas.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pytest
from PIL import Image

from core import preprocess
from core.box_model import BoxEntry
from core.services.box_service import BoxService


ESCALA = 30


def _faixa(alturas_de_tinta, largura=20, altura=100):
    """
    Recorte binário com tinta só nas faixas de linha pedidas.

    `alturas_de_tinta` são pares (início, fim) em pixels.
    """
    img = np.zeros((altura, largura), np.uint8)
    for ini, fim in alturas_de_tinta:
        img[ini:fim, :] = 255
    return img


def _pagina_com_duas_linhas_coladas():
    """
    Página onde um descendente encosta na linha de baixo.

    O 'g' da primeira linha e o 'h' da segunda ficam a 1 px um do outro, na
    mesma coluna: `findContours` os devolve num contorno só.
    """
    img = np.full((300, 500), 245, np.uint8)
    for k in range(6):
        cv2.putText(img, "ABC", (40 + k * 70, 80), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, 20, 2)
        cv2.putText(img, "DEF", (40 + k * 70, 150), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, 20, 2)
    # A ponte: uma coluna fina de tinta ligando as duas linhas. Vai só do fim
    # de uma até o começo da outra — atravessar o corpo da segunda encheria o
    # vale e não haveria onde cortar, que é o que uma primeira montagem fez.
    img[78:132, 300:302] = 20
    return img


# ----------------------------------------------------------------------
# O corte
# ----------------------------------------------------------------------

def test_box_de_duas_linhas_e_partido():
    bin_ = np.zeros((300, 100), np.uint8)
    bin_[100:130, 10:40] = 255          # linha de cima
    bin_[160:190, 10:40] = 255          # linha de baixo
    bin_[130:160, 22:26] = 255          # a ponte fina entre elas
    box = BoxEntry("", 10, 100, 40, 190)

    saida = BoxService.dividir_linhas_coladas([box], bin_, ESCALA)

    assert len(saida) == 2
    assert saida[0].y2 <= saida[1].y1
    assert all(b.height >= ESCALA for b in saida)


def test_caractere_normal_nao_e_tocado():
    bin_ = np.zeros((100, 60), np.uint8)
    bin_[10:40, 10:35] = 255
    box = BoxEntry("A", 10, 10, 35, 40)

    assert BoxService.dividir_linhas_coladas([box], bin_, ESCALA) == [box]


def test_bloco_nao_e_tocado():
    """Acima de 6 escalas é diagrama ou painel — assunto de outra fase."""
    bin_ = np.zeros((400, 400), np.uint8)
    bin_[10:390, 10:390] = 255
    box = BoxEntry("", 10, 10, 390, 390)

    assert BoxService.dividir_linhas_coladas([box], bin_, ESCALA) == [box]


def test_box_girado_nao_e_tocado():
    """Numa pilha vertical (F8.1) as linhas correm no outro eixo."""
    bin_ = np.zeros((300, 100), np.uint8)
    bin_[100:130, 10:40] = 255
    bin_[160:190, 10:40] = 255
    box = BoxEntry("", 10, 100, 40, 190, angulo=90)

    assert BoxService.dividir_linhas_coladas([box], bin_, ESCALA) == [box]


def test_sem_escala_nao_corta():
    bin_ = np.zeros((300, 100), np.uint8)
    box = BoxEntry("", 10, 100, 40, 190)
    assert BoxService.dividir_linhas_coladas([box], bin_, 0) == [box]


# ----------------------------------------------------------------------
# A lasca — a metade que faz a fase pagar
# ----------------------------------------------------------------------

def test_a_lasca_nao_vira_box():
    """
    Pedaço mais curto que um caractere não é caractere.

    Medido: emitir a lasca leva o F1 de 94,48 para 93,95, porque cada caractere
    recuperado custa 2,2 boxes espúrios.
    """
    bin_ = np.zeros((300, 100), np.uint8)
    bin_[100:145, 10:40] = 255          # caractere inteiro, 45 px
    bin_[150:170, 10:40] = 255          # lasca de 20 px, com escala 30
    bin_[145:150, 22:26] = 255          # o vale entre os dois
    box = BoxEntry("", 10, 100, 40, 170)

    saida = BoxService.dividir_linhas_coladas([box], bin_, ESCALA)

    assert len(saida) == 1, "a lasca virou box"
    assert saida[0].height >= ESCALA
    assert saida[0].y2 <= 150


def test_box_alto_sem_pedaco_utilizavel_fica_inteiro():
    """
    Quando nenhum pedaço tem tamanho de caractere, o box não era duas linhas —
    era outra coisa alta. Cortar ali seria trocar um box ruim por dois.
    """
    bin_ = np.zeros((200, 60), np.uint8)
    for ini in range(20, 80, 12):       # tinta em faixas finas
        bin_[ini:ini + 4, 10:50] = 255
    box = BoxEntry("", 10, 20, 50, 80)

    assert BoxService.dividir_linhas_coladas([box], bin_, ESCALA) == [box]


# ----------------------------------------------------------------------
# O que o corte tem de preservar
# ----------------------------------------------------------------------

def test_as_partes_herdam_a_polaridade():
    bin_ = np.zeros((300, 100), np.uint8)
    bin_[100:130, 10:40] = 255
    bin_[160:190, 10:40] = 255
    bin_[130:160, 22:26] = 255
    box = BoxEntry("", 10, 100, 40, 190, negativo=True)

    saida = BoxService.dividir_linhas_coladas([box], bin_, ESCALA)
    assert len(saida) == 2 and all(b.negativo for b in saida)


def test_as_partes_mantem_a_largura_do_original():
    """O corte é horizontal: o eixo x não se mexe."""
    bin_ = np.zeros((300, 100), np.uint8)
    bin_[100:130, 10:40] = 255
    bin_[160:190, 10:40] = 255
    bin_[130:160, 22:26] = 255
    box = BoxEntry("", 10, 100, 40, 190)

    for parte in BoxService.dividir_linhas_coladas([box], bin_, ESCALA):
        assert (parte.x1, parte.x2) == (box.x1, box.x2)


def test_cortar_de_novo_nao_muda_nada():
    """Idempotência: o que já foi partido não vira candidato outra vez."""
    bin_ = np.zeros((300, 100), np.uint8)
    bin_[100:130, 10:40] = 255
    bin_[160:190, 10:40] = 255
    bin_[130:160, 22:26] = 255

    uma = BoxService.dividir_linhas_coladas(
        [BoxEntry("", 10, 100, 40, 190)], bin_, ESCALA)
    duas = BoxService.dividir_linhas_coladas(uma, bin_, ESCALA)
    assert [b.as_state() for b in duas] == [b.as_state() for b in uma]


# ----------------------------------------------------------------------
# No pipeline
# ----------------------------------------------------------------------

def test_a_ponte_entre_linhas_deixa_de_engolir_a_linha():
    img = _pagina_com_duas_linhas_coladas()
    th = preprocess.binarize(img, "auto")
    escala = preprocess.escala_de_texto(th)

    cont, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    brutos = []
    for c in cont:
        x, y, w, h = cv2.boundingRect(c)
        if w >= 2 and h >= 2:
            brutos.append(BoxEntry("", x, y, x + w, y + h))

    altos_antes = [b for b in brutos if b.height > escala * 1.6]
    assert altos_antes, "a montagem não produziu box de duas linhas"

    depois = BoxService.dividir_linhas_coladas(brutos, th, escala)
    assert not [b for b in depois if b.height > escala * 1.6]


def test_geracao_completa_nao_deixa_box_de_duas_linhas():
    img = _pagina_com_duas_linhas_coladas()
    boxes = BoxService.generate_boxes_opencv(Image.fromarray(img))

    alturas = sorted(b.height for b in boxes)
    mediana = alturas[len(alturas) // 2]
    assert not [b for b in boxes if b.height > mediana * 2.5]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
