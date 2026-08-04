"""
Testes da F1.6 — ordem de leitura com colunas.

O algoritmo antigo agrupava tudo por linha, ignorando colunas: numa página de
duas colunas ele lia a linha 1 da esquerda, a linha 1 da direita, a linha 2 da
esquerda... Numa página real do Kasparov isso fazia a partida saltar do lance
19 para o 43 e voltar para o 20.

Rodar sem pytest:      python tests/test_f16_colunas.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.box_model import BoxEntry
from core.services.box_service import BoxService


def _linha(x_ini, y, n, larg=18, alt=20, passo=22, rotulo=""):
    """n boxes numa linha horizontal, opcionalmente rotulados."""
    return [BoxEntry(f"{rotulo}{i}" if rotulo else "",
                     x_ini + i * passo, y, x_ini + i * passo + larg, y + alt)
            for i in range(n)]


def _colunas_de(seq, colunas):
    def qual(b):
        cx = (b.x1 + b.x2) / 2
        for i, (a, z) in enumerate(colunas):
            if a <= cx <= z:
                return i
        return -1
    return [qual(b) for b in seq]


def _saltos(seq, colunas):
    lados = _colunas_de(seq, colunas)
    return sum(1 for i in range(1, len(lados)) if lados[i] != lados[i - 1])


# ----------------------------------------------------------------------
# Detecção de colunas
# ----------------------------------------------------------------------

def test_pagina_de_coluna_unica():
    boxes = []
    for y in (0, 30, 60):
        boxes += _linha(0, y, 20)
    assert len(BoxService.detectar_colunas(boxes)) == 1


def test_duas_colunas():
    boxes = []
    for y in (0, 30, 60):
        boxes += _linha(0, y, 15) + _linha(600, y, 15)
    colunas = BoxService.detectar_colunas(boxes)
    assert len(colunas) == 2, f"detectou {colunas}"
    assert colunas[0][1] < 600 <= colunas[1][0] + 1


def test_calha_fora_do_centro():
    """
    A abordagem do DocuVision procura a calha entre 42% e 58% da largura.
    Colunas assimétricas — comuns quando há nota lateral — escapam disso.
    """
    boxes = []
    for y in (0, 30, 60):
        boxes += _linha(0, y, 8) + _linha(400, y, 25)
    colunas = BoxService.detectar_colunas(boxes)
    assert len(colunas) == 2, f"calha assimétrica não detectada: {colunas}"


def test_tres_colunas():
    boxes = []
    for y in (0, 30, 60):
        boxes += _linha(0, y, 8) + _linha(400, y, 8) + _linha(800, y, 8)
    assert len(BoxService.detectar_colunas(boxes)) == 3


def test_espaco_entre_palavras_nao_vira_coluna():
    """O limiar é relativo à largura de caractere, não absoluto."""
    boxes = _linha(0, 0, 6) + _linha(160, 0, 6) + _linha(320, 0, 6)
    boxes += _linha(0, 30, 6) + _linha(160, 30, 6) + _linha(320, 30, 6)
    assert len(BoxService.detectar_colunas(boxes)) == 1, \
        "espaço entre palavras foi confundido com calha"


def test_sem_boxes():
    assert BoxService.detectar_colunas([]) == []
    assert BoxService.sort_boxes_reading_order([]) == []


# ----------------------------------------------------------------------
# Ordem de leitura
# ----------------------------------------------------------------------

def test_coluna_unica_mantem_ordem_de_linha():
    boxes = _linha(0, 30, 3, rotulo="b") + _linha(0, 0, 3, rotulo="a")
    saida = BoxService.sort_boxes_reading_order(boxes)
    assert [b.char for b in saida] == ["a0", "a1", "a2", "b0", "b1", "b2"]


def test_duas_colunas_nao_intercalam():
    """O defeito original: a leitura pulava de uma coluna para a outra a cada
    linha."""
    boxes = []
    for y in (0, 30, 60):
        boxes += _linha(0, y, 10) + _linha(600, y, 10)
    colunas = BoxService.detectar_colunas(boxes)

    saida = BoxService.sort_boxes_reading_order(boxes)
    assert _saltos(saida, colunas) == 1, "ainda intercala as colunas"

    lados = _colunas_de(saida, colunas)
    assert lados[0] == 0 and lados[-1] == 1, "começou pela coluna errada"


def test_ordem_dentro_da_coluna():
    esq = _linha(0, 0, 3, rotulo="E") + _linha(0, 30, 3, rotulo="e")
    dir_ = _linha(600, 0, 3, rotulo="D") + _linha(600, 30, 3, rotulo="d")
    saida = BoxService.sort_boxes_reading_order(esq + dir_)
    assert [b.char for b in saida] == [
        "E0", "E1", "E2", "e0", "e1", "e2",
        "D0", "D1", "D2", "d0", "d1", "d2",
    ]


def test_tres_colunas_em_ordem():
    boxes = []
    for y in (0, 30):
        boxes += (_linha(0, y, 6) + _linha(400, y, 6) + _linha(800, y, 6))
    colunas = BoxService.detectar_colunas(boxes)
    saida = BoxService.sort_boxes_reading_order(boxes)
    assert _saltos(saida, colunas) == 2
    assert _colunas_de(saida, colunas)[0] == 0


# ----------------------------------------------------------------------
# Elemento que atravessa a calha
# ----------------------------------------------------------------------

def test_titulo_largo_separa_as_faixas():
    """
    Um título ou diagrama que cruza a calha não pertence a coluna nenhuma.
    Serve de separador: o que está acima é lido coluna a coluna, depois vem
    ele, depois o que está abaixo.
    """
    acima = _linha(0, 0, 8, rotulo="A") + _linha(600, 0, 8, rotulo="B")
    titulo = [BoxEntry("TITULO", 100, 60, 900, 90)]
    abaixo = _linha(0, 120, 8, rotulo="C") + _linha(600, 120, 8, rotulo="D")

    saida = BoxService.sort_boxes_reading_order(acima + titulo + abaixo)
    chars = [b.char for b in saida]

    pos_titulo = chars.index("TITULO")
    antes, depois = set(chars[:pos_titulo]), set(chars[pos_titulo + 1:])

    assert {"A0", "B0"} <= antes, "conteúdo de cima veio depois do título"
    assert {"C0", "D0"} <= depois, "conteúdo de baixo veio antes do título"
    assert chars.index("A0") < chars.index("B0"), "faixa de cima intercalou"
    assert chars.index("C0") < chars.index("D0"), "faixa de baixo intercalou"


def test_nenhum_box_se_perde():
    """Reordenar não pode somer com box nem duplicar."""
    boxes = []
    for y in (0, 30, 60):
        boxes += _linha(0, y, 7) + _linha(600, y, 7)
    boxes.append(BoxEntry("larga", 100, 100, 900, 130))

    saida = BoxService.sort_boxes_reading_order(boxes)
    assert len(saida) == len(boxes)
    assert {id(b) for b in saida} == {id(b) for b in boxes}


def test_boxes_iguais_nao_se_confundem():
    """Dois boxes com as mesmas coordenadas são objetos distintos; a ordenação
    usa identidade, não igualdade."""
    a = BoxEntry("", 0, 0, 18, 20)
    b = BoxEntry("", 0, 0, 18, 20)
    saida = BoxService.sort_boxes_reading_order([a, b])
    assert len(saida) == 2


# ----------------------------------------------------------------------
# Página real
# ----------------------------------------------------------------------

def test_pagina_real_do_livro():
    """Medido: 9 saltos entre colunas antes, 1 depois."""
    import glob
    import cv2

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidatos = glob.glob(os.path.join(raiz, "ilovepdf_pages-to-jpg", "*0021.jpg"))
    if not candidatos:
        return          # scans não distribuídos com o código

    img = cv2.imread(candidatos[0], cv2.IMREAD_GRAYSCALE)
    if img is None:
        return
    h, w = img.shape
    rec = img[int(h * 0.44):int(h * 0.60), int(w * 0.06):int(w * 0.94)]

    _, th = cv2.threshold(rec, 180, 255, cv2.THRESH_BINARY_INV)
    cont, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    brutos = []
    for c in cont:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw >= 2 and bh >= 2:
            brutos.append(BoxEntry("", x, y, x + bw, y + bh))
    brutos.sort(key=lambda b: (b.y1, b.x1))
    boxes = BoxService.merge_vertical_boxes(brutos)

    colunas = BoxService.detectar_colunas(boxes)
    assert len(colunas) == 2, f"a página é de 2 colunas, detectou {len(colunas)}"

    saida = BoxService.sort_boxes_reading_order(boxes)
    assert _saltos(saida, colunas) == 1, "voltou a intercalar as colunas"
    assert len(saida) == len(boxes)


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
