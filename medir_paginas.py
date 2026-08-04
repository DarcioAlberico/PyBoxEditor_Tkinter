"""
Mede a segmentação + classificação contra as páginas rotuladas à mão.

Reproduz a tabela da F1.5 no ROADMAP. Existe porque a validação original da F1.5
usava um proxy — "boxes largos resolvidos, zero pedaços estreitos novos" — que
não distingue cortar uma colagem de partir um glifo ao meio, e por isso deixou
passar o defeito que a F1.7 encontrou.

    python medir_paginas.py                # todas as páginas rotuladas
    python medir_paginas.py --sem-modelo   # só segmentação, não carrega a rede

Os modos comparados:

    off      separar_colados=False
    global   escala do limiar pela mediana da PÁGINA (comportamento pré-correção)
    local    escala pela mediana da LINHA, com piso na global (o de hoje)
"""

import argparse
import glob
import os
import sys

import cv2
import numpy as np
from PIL import Image

from core import preprocess
from core.avaliacao_pagina import carregar_box, classificar_cortes, comparar
from core.box_model import BoxEntry
from core.services.box_service import BoxService


PASTAS_DE_IMAGEM = ("ilovepdf_pages-to-jpg", "Box")
MIN_ROTULADOS = 50


def paginas_rotuladas():
    """[(imagem, .box)] — a imagem pode estar na pasta do .box ou na do PDF."""
    achados = []
    for pasta in PASTAS_DE_IMAGEM:
        for cx in sorted(glob.glob(os.path.join(pasta, "*.box"))):
            nome = os.path.splitext(os.path.basename(cx))[0]
            for onde in (os.path.dirname(cx),) + PASTAS_DE_IMAGEM:
                imagem = next(
                    (p for p in (os.path.join(onde, nome + e)
                                 for e in (".jpg", ".png", ".jpeg"))
                     if os.path.exists(p)), None)
                if imagem:
                    achados.append((imagem, cx))
                    break
    return achados


def segmentar(imagem, modo):
    """(boxes antes do corte, boxes depois) para o modo pedido."""
    th = preprocess.binarize(np.array(imagem), "auto")
    contornos, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    brutos = []
    for c in contornos:
        x, y, w, h = cv2.boundingRect(c)
        if w >= 2 and h >= 2:
            brutos.append(BoxEntry("", x, y, x + w, y + h))
    brutos.sort(key=lambda b: (b.y1, b.x1))
    # espelha `generate_boxes_opencv`: o diagrama sai DEPOIS do merge (F1.8)
    pais = BoxService.descartar_blocos_nao_texto(
        BoxService.merge_vertical_boxes(brutos))

    if modo == "off":
        return pais, BoxService.sort_boxes_reading_order(list(pais))

    if modo == "local":
        referencia = BoxService._largura_de_referencia(pais)
    else:
        larguras = sorted(b.x2 - b.x1 for b in pais)
        m = larguras[len(larguras) // 2] or 1
        referencia = {id(b): m for b in pais}

    filhos = []
    for b in pais:
        m = referencia[id(b)]
        if (b.x2 - b.x1) <= m * 1.6:
            filhos.append(b)
            continue
        cortes = BoxService._cortes_do_perfil(
            th[b.y1:b.y2, b.x1:b.x2], 0.30,
            max(3, int(m * 0.25)), max(3, int(m * 0.40)))
        if not cortes:
            filhos.append(b)
            continue
        limites = [0] + cortes + [b.x2 - b.x1]
        for ini, fim in zip(limites, limites[1:]):
            filhos.append(BoxEntry(b.char, b.x1 + ini, b.y1, b.x1 + fim, b.y2))

    return pais, BoxService.sort_boxes_reading_order(filhos)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-modelo", action="store_true",
                    help="só conta cortes bons e falsos; não carrega a rede")
    args = ap.parse_args()

    predizer = None
    if not args.sem_modelo:
        from core.services.learning_service import LearningService
        svc = LearningService()
        if not svc.load_predictor():
            print("sem modelo treinado — rodando como --sem-modelo\n")
        else:
            predizer = svc._predictor.predict

    paginas = paginas_rotuladas()
    if not paginas:
        print("nenhuma página rotulada encontrada")
        return 1

    modos = ("off", "global", "local")
    total = {m: dict(certos=0, gerados=0, rotulados=0, espurios=0,
                     bons=0, falsos=0) for m in modos}

    for imagem, caminho_box in paginas:
        img = Image.open(imagem).convert("L")
        rotulados = carregar_box(caminho_box, img.size[1])
        if len(rotulados) < MIN_ROTULADOS:
            continue
        arr = np.array(img)
        print(f"\n=== {os.path.basename(imagem)}  ({len(rotulados)} rotulados)")

        for modo in modos:
            pais, filhos = segmentar(img, modo)
            if predizer:
                for b in filhos:
                    b.char, b.confidence = predizer(arr[b.y1:b.y2, b.x1:b.x2])
            r = comparar(filhos, rotulados)
            c = classificar_cortes(pais, filhos, rotulados)

            t = total[modo]
            t["certos"] += r.certos
            t["gerados"] += r.gerados
            t["rotulados"] += r.rotulados
            t["espurios"] += r.espurios
            t["bons"] += c["cortes_legitimos"]
            t["falsos"] += c["cortes_falsos"]

            medida = str(r) if predizer else f"boxes {r.gerados:>5}"
            print(f"  {modo:<7} {medida}  cortes bons {c['cortes_legitimos']:>3} "
                  f"falsos {c['cortes_falsos']:>3}")

    print("\n\n=========== TOTAL ===========")
    cabecalho = f"{'modo':<8}"
    if predizer:
        cabecalho += f"{'recall':>8} {'precisão':>9} {'F1':>6}"
    print(cabecalho + f" {'espúrios':>9} {'cortes bons':>12} {'cortes falsos':>14}")

    for modo in modos:
        t = total[modo]
        linha = f"{modo:<8}"
        if predizer and t["rotulados"]:
            rec = 100.0 * t["certos"] / t["rotulados"]
            pre = 100.0 * t["certos"] / t["gerados"]
            f1 = 2 * rec * pre / (rec + pre) if rec + pre else 0.0
            linha += f" {rec:>6.1f}% {pre:>7.1f}% {f1:>6.1f}"
        print(linha + f" {t['espurios']:>9} {t['bons']:>12} {t['falsos']:>14}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
