"""
Mede o que a F8.1 custa e o que ela rende, com o código de produção.

    python medir_vertical.py             # tudo
    python medir_vertical.py --rapido    # sem a varredura de todas as páginas

Quatro medições, e cada uma responde a uma pergunta que a fase precisava
responder antes de existir:

  1. classificador  — quanto se perde lendo um glifo deitado (a razão da fase)
  2. arbitragem     — o classificador sabe dizer em que ângulo a linha está?
  3. falso positivo — quantas pilhas de página normal ele aceita por engano?
  4. ponta a ponta  — uma linha real colada girada volta a ser lida?

As digitalizações não estão no repositório (material com direitos autorais).
Num clone limpo este script mede o que encontrar, e diz o que não encontrou.
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

from core import vertical
from core.avaliacao_pagina import carregar_box
from core.neural_trainer import NeuralPredictor
from core.services.box_service import BoxService
from medir_paginas import MIN_ROTULADOS, paginas_rotuladas

#: Ângulos simulados na medição de arbitragem. Inclui 180 de propósito: a
#: pergunta é se o classificador *saberia* separá-lo, não se ele acontece.
ANGULOS_SIMULADOS = (0, 90, 180, 270)


def _girar(recorte, graus):
    """Aplica o giro do texto impresso (o inverso de `endireitar`)."""
    return vertical.endireitar(recorte, -graus % 360)


def _paginas():
    achadas = []
    for imagem, caixa in paginas_rotuladas():
        img = Image.open(imagem).convert("L")
        boxes = [b for b in carregar_box(caixa, img.height)
                 if len(b.char) == 1 and b.char.strip()]
        if len(boxes) >= MIN_ROTULADOS:
            achadas.append((os.path.basename(imagem), img, boxes))
    return achadas


# ----------------------------------------------------------------------
# 1. O que custa ler deitado
# ----------------------------------------------------------------------

def medir_classificador(paginas, predizer):
    print("\n=== 1. o mesmo recorte, de pé e deitado ===")
    de_pe = girado = volta = total = 0
    iguais = 0

    for nome, img, boxes in paginas:
        arr = np.asarray(img)
        for b in boxes:
            recorte = arr[b.y1:b.y2, b.x1:b.x2]
            if recorte.size == 0 or min(recorte.shape[:2]) < 3:
                continue
            total += 1
            a = predizer(recorte)[0]
            deitado = predizer(_girar(recorte, 90))[0]
            ida_e_volta = predizer(vertical.endireitar(
                _girar(recorte, 90), 90))[0]
            de_pe += a == b.char
            girado += deitado == b.char
            volta += ida_e_volta == b.char
            iguais += a == ida_e_volta

    if not total:
        print("  sem páginas rotuladas")
        return
    print(f"  {total} caracteres rotulados em {len(paginas)} páginas")
    print(f"  de pé          {de_pe:6d}  {100.0 * de_pe / total:6.2f}%")
    print(f"  girado 90°     {girado:6d}  {100.0 * girado / total:6.2f}%")
    print(f"  girado e desgirado {volta:2d}  {100.0 * volta / total:6.2f}%")
    print(f"  respostas idênticas depois da ida e volta: "
          f"{100.0 * iguais / total:.2f}%  (giro de 90° é transposição)")


# ----------------------------------------------------------------------
# 2. O classificador sabe o ângulo?
# ----------------------------------------------------------------------

def medir_arbitragem(paginas, predizer):
    print("\n=== 2. o argmax da confiança média acerta o ângulo? ===")
    certos = {a: 0 for a in ANGULOS_SIMULADOS}
    totais = {a: 0 for a in ANGULOS_SIMULADOS}
    folgas = []

    for nome, img, boxes in paginas:
        arr = np.asarray(img)
        for linha in BoxService._linhas(sorted(boxes, key=lambda b: (b.y1, b.x1))):
            recortes = [arr[b.y1:b.y2, b.x1:b.x2] for b in linha]
            recortes = [r for r in recortes
                        if r.size and min(r.shape[:2]) >= 3]
            if len(recortes) < vertical.MIN_ITENS:
                continue
            for impresso in ANGULOS_SIMULADOS:
                deitados = [_girar(r, impresso) for r in recortes]
                medias = {a: float(np.mean(
                    [predizer(vertical.endireitar(d, a))[1] for d in deitados]))
                    for a in ANGULOS_SIMULADOS}
                escolhido = max(medias, key=medias.get)
                certos[impresso] += escolhido == impresso
                totais[impresso] += 1
                folgas.append(medias[impresso]
                              - max(v for k, v in medias.items() if k != impresso))

    if not sum(totais.values()):
        print("  sem linhas suficientes")
        return
    for a in ANGULOS_SIMULADOS:
        if totais[a]:
            print(f"  impresso a {a:3d}°: {certos[a]}/{totais[a]} = "
                  f"{100.0 * certos[a] / totais[a]:5.1f}%")
    print(f"  folga do certo sobre o melhor concorrente: "
          f"mediana {np.median(folgas):+.3f}")


# ----------------------------------------------------------------------
# 3. Falso positivo em página normal
# ----------------------------------------------------------------------

def medir_falsos(predizer, limite=None):
    import glob

    import cv2

    from core import preprocess
    from core.box_model import BoxEntry

    print("\n=== 3. pilhas propostas e aceitas em página sem texto vertical ===")
    arquivos = sorted(glob.glob(os.path.join("ilovepdf_pages-to-jpg", "*.jpg")))
    if limite:
        arquivos = arquivos[::max(1, len(arquivos) // limite)]
    if not arquivos:
        print("  sem páginas digitalizadas neste clone")
        return

    candidatas = aceitas = 0
    por_tamanho = {}
    for caminho in arquivos:
        img = cv2.imread(caminho, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        th = preprocess.binarize(img, "auto")
        contornos, _ = cv2.findContours(th, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        boxes = [BoxEntry("", x, y, x + w, y + h)
                 for x, y, w, h in map(cv2.boundingRect, contornos)
                 if w >= 2 and h >= 2]
        for cadeia in vertical.candidatos(boxes):
            candidatas += 1
            angulo, _ = vertical.decidir_angulo(img, cadeia, predizer)
            por_tamanho.setdefault(len(cadeia), [0, 0])
            por_tamanho[len(cadeia)][0] += 1
            if angulo:
                aceitas += 1
                por_tamanho[len(cadeia)][1] += 1

    print(f"  {len(arquivos)} páginas")
    print(f"  candidatas propostas pela geometria: {candidatas} "
          f"({candidatas / len(arquivos):.2f} por página)")
    print(f"  aceitas pelo classificador (falso positivo): {aceitas}")
    for n in sorted(por_tamanho):
        prop, aceite = por_tamanho[n]
        print(f"     {n} caixas: {prop} propostas, {aceite} aceitas")


# ----------------------------------------------------------------------
# 4. Ponta a ponta
# ----------------------------------------------------------------------

def _colar_girada(img, boxes, angulo=90):
    """Cola uma linha real da própria página, girada, numa faixa vazia."""
    linhas = [l for l in BoxService._linhas(sorted(boxes, key=lambda b: (b.y1, b.x1)))
              if 12 <= len(l) <= 22]
    if not linhas:
        return None
    linha = sorted(linhas[len(linhas) // 2], key=lambda b: b.x1)
    esperado = "".join(b.char for b in linha)

    arr = np.asarray(img)
    x1 = max(0, min(b.x1 for b in linha) - 3)
    y1 = max(0, min(b.y1 for b in linha) - 5)
    x2 = max(b.x2 for b in linha) + 3
    y2 = max(b.y2 for b in linha) + 5
    girada = Image.fromarray(_girar(arr[y1:y2, x1:x2], angulo))

    colunas = (arr < 128).sum(axis=0)
    destino = None
    for x in range(arr.shape[1] - girada.width - 2, 0, -1):
        if colunas[x:x + girada.width].max() == 0:
            destino = x
            break
    if destino is None:
        return None

    pagina = img.copy()
    topo = max(0, (arr.shape[0] - girada.height) // 2)
    pagina.paste(girada, (destino, topo))
    regiao = (destino, topo, destino + girada.width, topo + girada.height)
    return pagina, regiao, esperado


def _ler_regiao(pagina, regiao, predizer):
    boxes = BoxService.generate_boxes_opencv(pagina, arbitro=predizer)
    arr = np.asarray(pagina)
    dentro = [b for b in boxes
              if b.x1 >= regiao[0] - 4 and b.x2 <= regiao[2] + 4
              and b.y1 >= regiao[1] - 4 and b.y2 <= regiao[3] + 4]
    lido = "".join(predizer(vertical.recorte_de_pe(arr, b))[0] for b in dentro)
    return lido, len(dentro)


def _acertos(lido, esperado):
    """Caracteres em comum, na ordem — distância de edição por programação."""
    anterior = [0] * (len(esperado) + 1)
    for c in lido:
        atual = [0]
        for j, e in enumerate(esperado):
            atual.append(max(anterior[j] + (c == e), anterior[j + 1], atual[j]))
        anterior = atual
    return anterior[-1]


def medir_ponta_a_ponta(paginas, predizer):
    print("\n=== 4. uma linha real colada girada volta a ser lida? ===")
    if not paginas:
        print("  sem páginas rotuladas")
        return

    for nome, img, boxes in paginas[:3]:
        colada = _colar_girada(img, boxes)
        if colada is None:
            continue
        pagina, regiao, esperado = colada

        sem_fase = vertical.MIN_ITENS
        vertical.MIN_ITENS = 10 ** 6          # desliga só esta fase
        try:
            antes, n_antes = _ler_regiao(pagina, regiao, predizer)
        finally:
            vertical.MIN_ITENS = sem_fase
        depois, n_depois = _ler_regiao(pagina, regiao, predizer)

        print(f"  {nome[:44]}")
        print(f"     esperado ({len(esperado)} caracteres): {esperado!r}")
        print(f"     antes  — {n_antes:2d} boxes, {_acertos(antes, esperado)} "
              f"caracteres certos: {antes!r}")
        print(f"     depois — {n_depois:2d} boxes, {_acertos(depois, esperado)} "
              f"caracteres certos: {depois!r}")


def main():
    # O que sai daqui inclui o que o modelo leu, e ele lê figurina de xadrez.
    # No console do Windows (cp1252) isso derruba o print no meio da medição.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rapido", action="store_true",
                   help="amostra as páginas em vez de varrer todas")
    args = p.parse_args()

    predictor = NeuralPredictor()
    if not predictor.load():
        print(f"modelo neural não carregou: {predictor.erro or 'ausente'}")
        return 1

    paginas = _paginas()
    if not paginas:
        print("nenhuma página rotulada encontrada — as digitalizações não "
              "estão no repositório.")

    medir_classificador(paginas, predictor.predict)
    medir_arbitragem(paginas, predictor.predict)
    medir_falsos(predictor.predict, limite=40 if args.rapido else None)
    medir_ponta_a_ponta(paginas, predictor.predict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
