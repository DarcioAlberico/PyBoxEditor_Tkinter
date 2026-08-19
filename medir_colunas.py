"""
Mede a detecção de calha — a régua da F61, e a projeção da F70.

**Por que existe.** A régua da F1.6 (`calha >= 3 × largura mediana de caractere`)
nunca foi medida contra livro nenhum, e o efeito disso só aparece no arquivo
exportado: no Kasparov ela acha a calha em algumas páginas e não em outras, e no
Nunn não acha em nenhuma. Página lida como coluna única sai com a linha da
esquerda intercalada com a da direita — que é a queixa que abriu a fase.

**E a F61 não fechou a queixa, porque o limiar não era o defeito** (F70). A
projeção era um OR, e uma letra do cabeçalho corrente — que é centralizado, isto
é, em cima da calha — apagava a calha da página inteira. Daí as três colunas de
régua: `F1.6` é o limiar de 3,0, `F61` é o limiar medido ainda com o OR, e
`hoje` é a projeção que conta linhas.

Este script é o que reproduz a tabela do ROADMAP. Sobre as páginas rotuladas
(verdade de segmentação) e, com `--pdf`, sobre uma amostra de páginas de um PDF
com a segmentação de produção.

    python medir_colunas.py                     # as páginas rotuladas
    python medir_colunas.py --pdf Nunn          # amostra de um PDF pelo nome
    python medir_colunas.py --calha 0.8 1.5 3   # varre a régua

As duas colunas que importam:

    calha   o maior vão da projeção em x, em larguras medianas de caractere.
            É a grandeza que a régua compara.
    saltos  quantas vezes a ordem de leitura pula de uma coluna para a outra.
            Numa página de duas colunas lida direito, é **1**. Era 16.
"""

import argparse
import contextlib
import glob
import os
import sys

import numpy as np
from PIL import Image

from core.avaliacao_pagina import carregar_box
from core.calibracao_de_pagina import paginas_rotuladas
from core.leitura_de_linha import quebrar_em_linhas
from core.services.box_service import BoxService

#: Não tolerar linha nenhuma na calha é a projeção por OR de antes da F70.
SEM_TOLERANCIA = 10 ** 9

#: A régua de antes da F61, para a coluna "antes" da tabela. O `0` de coluna
#: mínima desliga a fusão de faixa estreita, que também é da F61 — sem isso a
#: coluna "antes" não seria o comportamento de antes.
REGUA_DA_F16 = (3.0, 0.02, 0.0, SEM_TOLERANCIA)

#: A régua da F61: a calha medida, mas ainda com a projeção por OR. É a coluna
#: contra a qual a F70 se compara — o que ela mudou não foi limiar nenhum.
REGUA_DA_F61 = (0.8, 0.01, 0.10, SEM_TOLERANCIA)

DPI = 300


@contextlib.contextmanager
def _regua(em_caracteres, piso, coluna_minima, linhas_para_tolerar):
    """
    Troca a régua da `detectar_colunas` pela duração do bloco.

    Mexer nos atributos da classe, e não copiar a função para cá: foi cópia
    divergente que deixou a F1.5 medir uma coisa e a aplicação fazer outra
    (ver `medir_paginas.segmentar`). O que se mede aqui é o código de produção
    com outra constante.

    **`LINHAS_PARA_TOLERAR` entrou na régua na F70**, e tinha de entrar: sem
    ela a coluna "antes" passaria a ser medida com a projeção por linhas, que é
    justamente o que mudou, e a tabela compararia limiar com limiar quando a
    diferença está na projeção.
    """
    antes = (BoxService.CALHA_EM_CARACTERES, BoxService.CALHA_DA_PAGINA,
             BoxService.COLUNA_MINIMA, BoxService.LINHAS_PARA_TOLERAR)
    (BoxService.CALHA_EM_CARACTERES, BoxService.CALHA_DA_PAGINA,
     BoxService.COLUNA_MINIMA, BoxService.LINHAS_PARA_TOLERAR) = (
        em_caracteres, piso, coluna_minima, linhas_para_tolerar)
    try:
        yield
    finally:
        (BoxService.CALHA_EM_CARACTERES, BoxService.CALHA_DA_PAGINA,
         BoxService.COLUNA_MINIMA, BoxService.LINHAS_PARA_TOLERAR) = antes


def maior_vao(boxes):
    """(maior vão da projeção em x, em px e em larguras medianas)."""
    x_min = min(b.x1 for b in boxes)
    largura = max(b.x2 for b in boxes) - x_min
    if largura <= 1:
        return 0, 0.0
    ocupado = np.zeros(largura + 2, dtype=bool)
    for b in boxes:
        ocupado[max(0, b.x1 - x_min):max(0, b.x2 - x_min) + 1] = True

    maior, inicio = 0, None
    for i, cheio in enumerate(ocupado):
        if not cheio:
            if inicio is None:
                inicio = i
        else:
            if inicio is not None and inicio > 0:
                maior = max(maior, i - inicio)
            inicio = None
    larguras = sorted(b.x2 - b.x1 for b in boxes)
    return maior, maior / (larguras[len(larguras) // 2] or 1)


def saltos_de_coluna(boxes, referencia):
    """
    Quantas vezes a leitura pula de uma coluna para a outra.

    **A `referencia` é fixa, e é o que torna a tabela comparável.** Contar os
    saltos contra as colunas que a própria régua achou dá zero para toda régua
    que não acha coluna nenhuma — a página intercalada sairia com nota cheia. As
    colunas de referência são as da régua de hoje, que é onde elas estão.

    Conta por **linha**, e não por box: a régua é "o texto da esquerda saiu
    inteiro antes do da direita", e um box perdido do outro lado da calha não é
    o defeito que se está medindo.
    """
    def qual(b):
        cx = (b.x1 + b.x2) / 2
        for i, (a, z) in enumerate(referencia):
            if a <= cx <= z:
                return i
        return -1

    linhas = quebrar_em_linhas(BoxService.sort_boxes_reading_order(list(boxes)))
    lados = [qual(max(linha, key=lambda b: b.x2 - b.x1)) for linha in linhas]
    return sum(1 for a, b in zip(lados, lados[1:]) if a != b), len(linhas)


def medir(nome, boxes, reguas):
    if len(boxes) < 50:
        return None
    px, relativo = maior_vao(boxes)
    saida = {"nome": nome, "vao": px, "relativo": relativo}
    referencia = BoxService.detectar_colunas(boxes)
    for rotulo, em_caracteres, piso, coluna_minima, tolerancia in reguas:
        with _regua(em_caracteres, piso, coluna_minima, tolerancia):
            colunas = BoxService.detectar_colunas(boxes)
            saltos, linhas = saltos_de_coluna(boxes, referencia)
        saida[rotulo] = (len(colunas), saltos, linhas)
    return saida


def _boxes_das_rotuladas(raiz):
    for imagem, caminho in paginas_rotuladas(raiz):
        with Image.open(imagem) as img:
            altura = img.height
        yield os.path.basename(imagem)[:44], carregar_box(caminho, altura)


def _boxes_do_pdf(padrao, raiz, quantas):
    import fitz

    achados = [p for p in glob.glob(os.path.join(raiz, "PDF", "**", "*.pdf"),
                                    recursive=True)
               if padrao.lower() in os.path.basename(p).lower()
               and "mapeamento" not in p]
    for caminho in achados:
        doc = fitz.open(caminho)
        try:
            passo = max(1, len(doc) // quantas)
            for n in range(0, len(doc), passo):
                pix = doc[n].get_pixmap(dpi=DPI, colorspace=fitz.csGRAY)
                arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width)
                yield (f"{os.path.basename(caminho)[:34]} p{n:04d}",
                       BoxService.generate_boxes_opencv(Image.fromarray(arr)))
        finally:
            doc.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="mede uma amostra deste PDF (por nome)")
    ap.add_argument("--paginas", type=int, default=8,
                    help="quantas páginas do PDF (padrão 8)")
    ap.add_argument("--calha", type=float, nargs="*", default=None,
                    help="varre a régua em larguras medianas de caractere")
    args = ap.parse_args()

    raiz = os.path.dirname(os.path.abspath(__file__))
    if args.calha:
        reguas = [(f"{c:g}×", c, BoxService.CALHA_DA_PAGINA,
                   BoxService.COLUNA_MINIMA, BoxService.LINHAS_PARA_TOLERAR)
                  for c in args.calha]
    else:
        reguas = [("F1.6",) + REGUA_DA_F16,
                  ("F61",) + REGUA_DA_F61,
                  ("hoje", BoxService.CALHA_EM_CARACTERES,
                   BoxService.CALHA_DA_PAGINA, BoxService.COLUNA_MINIMA,
                   BoxService.LINHAS_PARA_TOLERAR)]

    fonte = (_boxes_do_pdf(args.pdf, raiz, args.paginas) if args.pdf
             else _boxes_das_rotuladas(raiz))

    cabecalho = f"{'página':46s} {'calha':>6s} {'×lmed':>6s}"
    for regua in reguas:
        cabecalho += f" | {regua[0]:>5s} col saltos/linhas"
    print(cabecalho)

    linhas = []
    for nome, boxes in fonte:
        medida = medir(nome, boxes, reguas)
        if medida is None:
            continue
        linhas.append(medida)
        texto = (f"{medida['nome']:46s} {medida['vao']:6d} "
                 f"{medida['relativo']:6.2f}")
        for regua in reguas:
            col, saltos, n = medida[regua[0]]
            texto += f" | {col:8d} {saltos:6d}/{n:<5d}"
        print(texto)

    if not linhas:
        print("\nNenhuma página medida — as digitalizações não estão no repo.")
        return

    print()
    for regua in reguas:
        rotulo = regua[0]
        varias = sum(1 for m in linhas if m[rotulo][0] > 1)
        saltos = sum(m[rotulo][1] for m in linhas)
        print(f"{rotulo:>6s}: {varias} de {len(linhas)} páginas com mais de uma "
              f"coluna, {saltos} saltos no total")


if __name__ == "__main__":
    sys.exit(main())
