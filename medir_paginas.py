"""
Mede a segmentação + classificação contra as páginas rotuladas à mão.

Reproduz a tabela da F1.5 no ROADMAP. Existe porque a validação original da F1.5
usava um proxy — "boxes largos resolvidos, zero pedaços estreitos novos" — que
não distingue cortar uma colagem de partir um glifo ao meio, e por isso deixou
passar o defeito que a F1.7 encontrou.

    python medir_paginas.py                # todas as páginas rotuladas
    python medir_paginas.py --sem-modelo   # só segmentação, não carrega a rede

Os modos comparados:

    off       separar_colados=False
    global    escala do limiar pela mediana da PÁGINA (comportamento pré-correção)
    local     escala pela mediana da LINHA, com piso na global (F1.7)
    arbitrado o classificador confirma cada corte (F1.5b) — o de hoje

O modo `arbitrado` precisa do modelo; com `--sem-modelo` ele não roda.
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


def segmentar(imagem, modo, arbitro=None, margem=None, fator=None):
    """
    (boxes antes do corte, boxes depois) para o modo pedido.

    `fator` é o `fator_largo` de `dividir_glifos_colados` — a largura, em
    larguras de referência da linha, acima da qual um box vira candidato a
    corte. Existe como parâmetro por causa da F13: os colados que sobram são
    caractere fino grudado em largo (`.R`, `,h`, `il`), e num par desses a
    largura do box mal se mexe. Varrer o fator é o que diz se baixar a
    candidatura alcança esses casos ou só fabrica candidato.
    """
    arr = np.array(imagem)
    th = preprocess.binarize(arr, "auto")
    # Espelha `generate_boxes_opencv` também aqui: a trama sai antes de medir.
    th = preprocess.remover_textura(arr, th)
    escala = preprocess.escala_de_texto(th)
    contornos, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    brutos = []
    for c in contornos:
        x, y, w, h = cv2.boundingRect(c)
        if w >= 2 and h >= 2:
            brutos.append(BoxEntry("", x, y, x + w, y + h))
    brutos.sort(key=lambda b: (b.y1, b.x1))
    # espelha `generate_boxes_opencv`: o diagrama sai DEPOIS do merge (F1.8)
    pais = BoxService.descartar_blocos_nao_texto(
        BoxService.merge_vertical_boxes(brutos), escala=escala)
    # Fora do `if`, e antes dele: o corte de linha (F12) não é um dos modos —
    # é parte do pipeline em todos eles. Os modos comparam o separador de
    # **glifo**, e deixá-lo só num deles compararia duas coisas de uma vez.
    pais = BoxService.dividir_linhas_coladas(pais, th, escala)

    if modo == "off":
        return pais, BoxService.sort_boxes_reading_order(list(pais))

    if modo in ("local", "arbitrado"):
        # O código de verdade, não uma cópia dele: foi uma cópia divergente
        # que deixou a F1.5 medir uma coisa e a aplicação fazer outra.
        extra = {} if fator is None else {"fator_largo": fator}
        filhos = BoxService.dividir_glifos_colados(
            pais, th,
            arbitro=(arbitro if modo == "arbitrado" else None),
            imagem_cinza=arr, margem=margem, **extra)
        return pais, BoxService.sort_boxes_reading_order(filhos)

    # 'global': a escala pré-F1.7, mantida só como linha de base histórica.
    larguras = sorted(b.x2 - b.x1 for b in pais)
    m = larguras[len(larguras) // 2] or 1

    filhos = []
    for b in pais:
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
    ap.add_argument("--margens", type=float, nargs="*", default=None,
                    help="varre margens do árbitro (F1.5b) em vez dos modos")
    ap.add_argument("--fatores", type=float, nargs="*", default=None,
                    help="varre o fator_largo da candidatura (F13)")
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

    if args.margens is not None and predizer is None:
        print("a varredura de margens precisa do modelo")
        return 1

    if args.fatores is not None and predizer is None:
        print("a varredura de fatores precisa do modelo")
        return 1

    if args.fatores is not None:
        # Só o fator muda; o árbitro fica no valor de produção, senão a tabela
        # compararia duas coisas de uma vez.
        execucoes = [(f"fator {f:.2f}", None, f) for f in args.fatores]
    elif args.margens is not None:
        # Cada margem vira um "modo" próprio, para a tabela sair comparável.
        execucoes = ([("off", None, None), ("local", None, None)]
                     + [(f"arb {m:+.2f}", m, None) for m in args.margens])
    else:
        execucoes = [("off", None, None), ("global", None, None),
                     ("local", None, None)]
        if predizer is not None:
            execucoes.append(("arbitrado", None, None))

    modos = [nome for nome, _, _ in execucoes]
    total = {m: dict(certos=0, gerados=0, rotulados=0, espurios=0,
                     bons=0, falsos=0) for m in modos}

    for imagem, caminho_box in paginas:
        img = Image.open(imagem).convert("L")
        rotulados = carregar_box(caminho_box, img.size[1])
        if len(rotulados) < MIN_ROTULADOS:
            continue
        arr = np.array(img)
        print(f"\n=== {os.path.basename(imagem)}  ({len(rotulados)} rotulados)")

        for modo, margem, fator in execucoes:
            base = modo
            if modo.startswith("arb ") or modo.startswith("fator "):
                base = "arbitrado"
            pais, filhos = segmentar(img, base, arbitro=predizer,
                                     margem=margem, fator=fator)
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
            print(f"  {modo:<10} {medida}  cortes bons {c['cortes_legitimos']:>3} "
                  f"falsos {c['cortes_falsos']:>3}")

    print("\n\n=========== TOTAL ===========")
    cabecalho = f"{'modo':<10}"
    if predizer:
        cabecalho += f"{'recall':>8} {'precisão':>9} {'F1':>6}"
    print(cabecalho + f" {'espúrios':>9} {'cortes bons':>12} {'cortes falsos':>14}")

    for modo in modos:
        t = total[modo]
        linha = f"{modo:<10}"
        if predizer and t["rotulados"]:
            rec = 100.0 * t["certos"] / t["rotulados"]
            pre = 100.0 * t["certos"] / t["gerados"]
            f1 = 2 * rec * pre / (rec + pre) if rec + pre else 0.0
            linha += f" {rec:>6.1f}% {pre:>7.1f}% {f1:>6.1f}"
        print(linha + f" {t['espurios']:>9} {t['bons']:>12} {t['falsos']:>14}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
