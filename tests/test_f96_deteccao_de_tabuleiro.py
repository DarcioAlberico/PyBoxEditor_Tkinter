"""
Testes da F96 — o tabuleiro achado sem passar pela segmentação de caracteres.

O detector de verdade só pode ser medido contra páginas impressas, e elas não
estão no repositório (`medir_rotulos.py --por-contorno` faz essa medição num
clone que tenha os PDFs). O que **estes** testes prendem é o que se pode
conferir sem material: as decisões que erram calado.

  - `ordenar_cantos` devolve os cantos na ordem prometida, inclusive com os
    pontos embaralhados e com o quadrilátero girado — errar aqui espelha o
    tabuleiro, e um tabuleiro espelhado lê como posição legal;
  - `endireitar` desentorta: um tabuleiro girado dentro de uma página sai
    quadrado e em registro, com as 64 casas no lugar;
  - a ordem de saída é **a de `diagrama.ordem_de_leitura`**, e não outra —
    é a prova de que a numeração da tela e a da exportação não podem divergir;
  - o detector acha os tabuleiros de uma página sintética e **não inventa** um
    onde só há texto.

Rodar sem pytest:      python tests/test_f96_deteccao_de_tabuleiro.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pytest

from core import deteccao_de_tabuleiro as det
from core import diagrama as diag

#: Tom da casa escura destes livros, medido: cinza chapado, não preto.
CASA_ESCURA = 150


def tabuleiro(lado: int = 480, moldura: int = 4) -> np.ndarray:
    """Um tabuleiro 8x8 chapado, com a moldura fechada que o detector procura."""
    img = np.full((lado, lado), 255, np.uint8)
    casa = (lado - 2 * moldura) // 8
    for linha in range(8):
        for coluna in range(8):
            if (linha + coluna) % 2:
                y, x = moldura + linha * casa, moldura + coluna * casa
                img[y:y + casa, x:x + casa] = CASA_ESCURA
    cv2.rectangle(img, (0, 0), (lado - 1, lado - 1), 0, moldura)
    return img


def pagina(*, com=(), lado=1200, altura=1600) -> np.ndarray:
    """Uma página branca com tabuleiros colados nas posições dadas."""
    pg = np.full((altura, lado), 255, np.uint8)
    for x, y in com:
        t = tabuleiro()
        pg[y:y + t.shape[0], x:x + t.shape[1]] = t
    return pg


def pagina_de_texto() -> np.ndarray:
    """Uma página só com linhas de texto — nada aqui é tabuleiro."""
    pg = np.full((1600, 1200), 255, np.uint8)
    for linha in range(30):
        y = 100 + linha * 45
        for palavra in range(9):
            x = 100 + palavra * 110
            pg[y:y + 22, x:x + 90] = 40
    return pg


# ----------------------------------------------------------------------
# Os cantos
# ----------------------------------------------------------------------

def test_ordena_cantos_embaralhados():
    canonico = np.array([[10, 20], [110, 20], [110, 120], [10, 120]], np.float32)
    for ordem in ([2, 0, 3, 1], [3, 2, 1, 0], [1, 3, 0, 2]):
        saida = det.ordenar_cantos(canonico[ordem])
        assert np.allclose(saida, canonico), f"embaralhado {ordem}"


def test_ordena_cantos_de_quadrilatero_girado():
    """Girado 10°, o canto de cima à esquerda continua sendo o de cima à esquerda."""
    centro = np.array([100.0, 100.0])
    base = np.array([[-50, -50], [50, -50], [50, 50], [-50, 50]], np.float32)
    a = np.deg2rad(10)
    giro = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]], np.float32)
    girado = (base @ giro.T) + centro

    saida = det.ordenar_cantos(girado[[2, 3, 0, 1]])
    assert np.allclose(saida, girado, atol=1e-4)


# ----------------------------------------------------------------------
# Endireitar
# ----------------------------------------------------------------------

def test_endireitar_devolve_quadrado_do_lado_pedido():
    quad = np.array([[10, 20], [200, 25], [195, 210], [15, 205]], np.float32)
    saida = det.endireitar(pagina(com=[(0, 0)]), quad, 320)
    assert saida.shape == (320, 320)


@pytest.mark.parametrize("giro, bbox_esperado", [(3.0, 64), (6.0, 46)])
def test_endireitar_poe_a_grade_em_registro(giro, bbox_esperado):
    """O teste que justifica a homografia — e diz **a partir de quando** ela paga.

    Um tabuleiro girado dentro da página é recortado das duas maneiras: pelo
    retângulo envolvente e pelos quatro cantos. Quem julga é o padrão de cores,
    que é conhecido de antemão — casa (linha+coluna) par é clara —, e o
    desalinhamento o quebra imediatamente.

    Os dois casos estão aqui porque o segundo sozinho esconderia o primeiro:
    **até 3° o bbox também acerta as 64**, e é honesto que o teste diga isso. A
    partir de 4° ele começa a cair (62, 57, 46 em 4°, 5° e 6°) e o recorte pelos
    cantos fica em 64 até 10°. Ver a tabela no docstring do módulo.
    """
    t = tabuleiro(480)
    pg = np.full((900, 900), 255, np.uint8)
    pg[200:680, 200:680] = t
    matriz = cv2.getRotationMatrix2D((450, 450), giro, 1.0)
    pg = cv2.warpAffine(pg, matriz, (900, 900), borderValue=255)

    cantos = np.array([[200, 200], [680, 200], [680, 680], [200, 680]], np.float32)
    girados = (np.hstack([cantos, np.ones((4, 1), np.float32)]) @ matriz.T).astype(np.float32)

    def xadrez_bate(recorte: np.ndarray) -> int:
        casa = recorte.shape[0] // 8
        certas = 0
        for linha in range(8):
            for coluna in range(8):
                y, x = linha * casa, coluna * casa
                miolo = recorte[y + casa // 4:y + 3 * casa // 4,
                                x + casa // 4:x + 3 * casa // 4]
                clara = float(np.mean(miolo)) > (255 + CASA_ESCURA) / 2
                certas += clara == ((linha + coluna) % 2 == 0)
        return certas

    x1, y1 = girados[:, 0].min(), girados[:, 1].min()
    x2, y2 = girados[:, 0].max(), girados[:, 1].max()
    pelo_bbox = cv2.resize(pg[int(y1):int(y2), int(x1):int(x2)], (800, 800))
    pelos_cantos = det.endireitar(pg, girados, 800)

    assert xadrez_bate(pelos_cantos) == 64
    assert xadrez_bate(pelo_bbox) == bbox_esperado


# ----------------------------------------------------------------------
# A ordem é a da casa
# ----------------------------------------------------------------------

def test_ordem_e_a_de_diagrama_ordem_de_leitura():
    """Duas colunas de dois: desce a da esquerda antes de começar a da direita."""
    posicoes = [(80, 100), (620, 100), (80, 700), (620, 700)]
    achados = det.detectar(pagina(com=posicoes, altura=1400))
    assert len(achados) == 4

    caixas = [t.caixa for t in achados]
    assert caixas == diag.ordem_de_leitura(caixas)
    # e a ordem que isso produz é coluna a coluna, não fila a fila
    assert [c[0] < 400 for c in caixas] == [True, True, False, False]


# ----------------------------------------------------------------------
# Achar, e não inventar
# ----------------------------------------------------------------------

def test_acha_os_tres_tabuleiros_da_pagina():
    achados = det.detectar(pagina(com=[(80, 100), (620, 100), (80, 700)], altura=1400))
    assert len(achados) == 3
    for t in achados:
        largura = t.caixa[2] - t.caixa[0]
        altura = t.caixa[3] - t.caixa[1]
        assert 460 <= largura <= 500 and 460 <= altura <= 500
        assert t.pontuacao > 0


def test_nao_inventa_tabuleiro_em_pagina_de_texto():
    assert det.detectar(pagina_de_texto()) == []


def test_a_peneira_da_f95_deixa_passar_o_tabuleiro():
    """`piso_do_xadrez` liga a prova da F95; ela não pode derrubar um tabuleiro."""
    com_peneira = det.detectar(pagina(com=[(80, 100), (620, 100)]),
                               piso_do_xadrez=diag.PISO_DO_XADREZ)
    assert len(com_peneira) == 2


def test_o_teto_corta_e_a_ordem_sobrevive():
    posicoes = [(80, 100), (620, 100), (80, 700), (620, 700)]
    achados = det.detectar(pagina(com=posicoes, altura=1400), maximo=2)
    assert len(achados) == 2
    caixas = [t.caixa for t in achados]
    assert caixas == diag.ordem_de_leitura(caixas)


def test_localizar_devolve_a_forma_que_diagrama_consome():
    """A porta de troca: mesma forma que `diagrama.localizar`, tupla a tupla."""
    caixas = det.localizar(pagina(com=[(80, 100), (620, 100)]))
    assert caixas == [t.caixa for t in det.detectar(pagina(com=[(80, 100), (620, 100)]))]
    for caixa in caixas:
        assert len(caixa) == 4
        assert all(isinstance(v, int) for v in caixa)


def test_pagina_em_rgb_e_em_cinza_dao_o_mesmo():
    """A página deste projeto vem em cinza; a do projeto de origem, em RGB."""
    cinza = pagina(com=[(80, 100), (620, 100)])
    rgb = np.dstack([cinza] * 3)
    assert det.localizar(cinza) == det.localizar(rgb)


def test_recorte_sai_no_lado_pedido():
    pg = pagina(com=[(80, 100)])
    achado = det.detectar(pg)[0]
    assert achado.recorte(pg).shape == (det.LADO_DO_RECORTE, det.LADO_DO_RECORTE)
    assert achado.recorte(pg, 320).shape == (320, 320)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
