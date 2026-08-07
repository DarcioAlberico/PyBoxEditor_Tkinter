"""
Mede a detecção de texto em negativo (F10) num PDF inteiro.

    python medir_negativo.py "caminho/livro.pdf"            # o livro todo
    python medir_negativo.py "caminho/livro.pdf" 30 45      # só um intervalo
    python medir_negativo.py --imagens ilovepdf_pages-to-jpg

Responde três perguntas, e cada uma tem um jeito de estar errada:

1. **Quantas tarjas aparecem e quantas são aceitas.** Faixa recusada é texto
   que continua perdido; faixa aceita que não é tarja é lixo novo na página.
2. **O que o classificador lê dentro delas.** É a única prova de que a
   segmentação serviu para alguma coisa — contar boxes não distingue vinte
   caixas nas letras de vinte caixas no meio do fundo preto.

   Num PDF com camada de texto, cada tarja sai com o `[n/m]` da comparação
   contra ela. **Isso é referência, não verdade**: a camada do *Chess
   Evolution 1* traz `Boibochan` onde o impresso diz Bolbochan e `Stefnit`
   onde diz Steinitz. Serve para achar tarja que saiu vazia ou embaralhada;
   não serve para publicar percentual. Os 89,4% da F10.1 no ROADMAP saíram de
   seis tarjas conferidas à mão contra a imagem.
3. **Quanto custa por página.** O detector roda em toda geração de boxes,
   inclusive nas páginas que não têm tarja nenhuma.

Sem `--sem-modelo` ele carrega a rede; sem rede, mede só 1 e 3.
"""

import argparse
import difflib
import glob
import os
import sys
import time

import cv2
import numpy as np
from PIL import Image

from core import negativo, preprocess, vertical
from core.box_model import BoxEntry
from core.services.box_service import BoxService


DPI = 300


def paginas_do_pdf(caminho, ini, fim, dpi=DPI):
    import fitz

    doc = fitz.open(caminho)
    fim = len(doc) if fim is None else min(fim, len(doc))
    for i in range(ini, fim):
        pagina = doc[i]
        pix = pagina.get_pixmap(dpi=dpi)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.h, pix.w, pix.n)
        cinza = (cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
                 if pix.n >= 3 else arr[:, :, 0])
        yield f"pág {i}", cinza, pagina
    doc.close()


def paginas_da_pasta(pasta, ini, fim):
    arquivos = sorted(glob.glob(os.path.join(pasta, "*.jpg"))
                      + glob.glob(os.path.join(pasta, "*.png")))
    for caminho in arquivos[ini:fim]:
        yield os.path.basename(caminho), np.array(
            Image.open(caminho).convert("L")), None


def verdade_da_faixa(pagina, faixa, dpi=DPI):
    """
    O texto que o PDF diz haver dentro da faixa, ou "" se não houver camada.

    Só serve em PDF com texto — é o caso dos livros "editable", e é a única
    verdade disponível sem rotular tarja a mão. Num scan puro não há o que
    comparar, e a medida cai para "quantos boxes saíram".
    """
    if pagina is None:
        return ""
    import fitz

    escala = 72.0 / dpi
    ret = fitz.Rect(faixa.x1 * escala, faixa.y1 * escala,
                    faixa.x2 * escala, faixa.y2 * escala)
    return " ".join(pagina.get_textbox(ret).split())


def normalizar(texto):
    """Tira o que a comparação não deve cobrar: espaço e tipo de travessão."""
    for traco in "–—−":
        texto = texto.replace(traco, "-")
    return "".join(texto.split())


def medir_pagina(cinza, predizer=None):
    """(faixas aceitas, boxes gerados dentro delas, leituras, ms)."""
    t0 = time.perf_counter()
    th = preprocess.binarize(cinza, "auto")
    contornos, _ = cv2.findContours(th, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    brutos = []
    for c in contornos:
        x, y, w, h = cv2.boundingRect(c)
        if w >= 2 and h >= 2:
            brutos.append(BoxEntry("", x, y, x + w, y + h))
    brutos.sort(key=lambda b: (b.y1, b.x1))

    propostas = len(negativo.candidatos(th, brutos))
    t1 = time.perf_counter()
    boxes, th, faixas = negativo.aplicar(cinza, th, brutos)
    custo = (time.perf_counter() - t1) * 1000

    # o caminho de verdade, e não uma cópia dele (a lição do medir_paginas.py)
    boxes = BoxService.merge_vertical_boxes(boxes)
    boxes = BoxService.descartar_blocos_nao_texto(boxes)
    boxes = BoxService.dividir_glifos_colados(
        boxes, th, arbitro=predizer, imagem_cinza=cinza)
    boxes = BoxService.sort_boxes_reading_order(boxes)

    leituras = []
    for faixa in faixas:
        dentro = [b for b in boxes
                  if b.negativo and faixa.x1 <= b.center()[0] <= faixa.x2
                  and faixa.y1 <= b.center()[1] <= faixa.y2]
        dentro.sort(key=lambda b: b.x1)
        texto = ""
        if predizer is not None:
            for b in dentro:
                char, _conf = predizer(vertical.recorte_de_pe(cinza, b))
                texto += char or "?"
        leituras.append((faixa, len(dentro), texto))

    return propostas, faixas, leituras, custo, (time.perf_counter() - t0) * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="?", help="PDF a medir")
    ap.add_argument("ini", nargs="?", type=int, default=0)
    ap.add_argument("fim", nargs="?", type=int, default=None)
    ap.add_argument("--imagens", help="pasta de .jpg/.png em vez de PDF")
    ap.add_argument("--sem-modelo", action="store_true")
    args = ap.parse_args()

    if not args.pdf and not args.imagens:
        ap.error("informe um PDF ou --imagens")

    predizer = None
    if not args.sem_modelo:
        from core.services.learning_service import LearningService

        svc = LearningService()
        if svc.load_predictor():
            predizer = svc._predictor.predict
        else:
            print("sem modelo treinado — medindo só a detecção\n")

    if args.imagens:
        fonte = paginas_da_pasta(args.imagens, args.ini, args.fim)
    else:
        fonte = paginas_do_pdf(args.pdf, args.ini, args.fim)

    n_pag = n_prop = n_faixa = n_box = n_recusada = 0
    certos = total_verdade = 0
    custo_total = custo_pagina = 0.0
    for nome, cinza, pagina in fonte:
        propostas, faixas, leituras, custo, total = medir_pagina(cinza, predizer)
        n_pag += 1
        n_prop += propostas
        n_faixa += len(faixas)
        n_recusada += propostas - len(faixas)
        custo_total += custo
        custo_pagina += total
        for faixa, quantos, texto in leituras:
            n_box += quantos
            verdade = normalizar(verdade_da_faixa(pagina, faixa))
            marca = ""
            if verdade and predizer is not None:
                casados = sum(
                    b.size for b in difflib.SequenceMatcher(
                        None, normalizar(texto), verdade).get_matching_blocks())
                certos += casados
                total_verdade += len(verdade)
                marca = f"  [{casados}/{len(verdade)}]  {verdade}"
            print(f"{nome:>12}  {faixa.width}x{faixa.height} em "
                  f"({faixa.x1},{faixa.y1})  {quantos:>3} boxes  "
                  f"{texto}{marca}")
        if propostas and not faixas:
            print(f"{nome:>12}  {propostas} faixa(s) recusada(s)")

    print(f"\n{n_pag} páginas: {n_prop} faixas propostas, {n_faixa} aceitas, "
          f"{n_recusada} recusadas, {n_box} boxes novos")
    if total_verdade:
        print(f"caracteres contra a camada de texto do PDF: "
              f"{certos}/{total_verdade} = "
              f"{100.0 * certos / total_verdade:.1f}%")
    if n_pag:
        print(f"custo do detector: {custo_total / n_pag:.1f} ms/página "
              f"(a página inteira leva {custo_pagina / n_pag:.0f} ms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
