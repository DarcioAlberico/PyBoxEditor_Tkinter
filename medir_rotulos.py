"""
Mede o comando "Ler posição dos diagramas" numa página inteira (F95).

O `medir_diagramas.py` mede o que acontece **depois** de o tabuleiro estar
recortado: ocupação, identidade, tabuleiro inteiro. Nada media o que vem antes —
achar o tabuleiro na página — e era ali que estava o defeito mais caro da fase:
o diagrama impresso dentro de um painel não era achado, e o comando respondia
"nenhum diagrama encontrado" sem que número nenhum contradissesse.

Este script mede as três coisas que a leitura de página faz:

    achar        quantos tabuleiros de quantos impressos
    rótulos      há coordenadas em volta? (a resposta que a exportação usa)
    título       o que está impresso encostado no tabuleiro

O gabarito é `tests/dados/paginas_com_diagrama.txt`, escrito à mão olhando as
páginas: uma linha por página, `livro | página | diagramas | coordenadas`. Não
sai da leitura — um gabarito que saísse do programa mediria o programa contra
ele mesmo.

    python medir_rotulos.py
    python medir_rotulos.py --sem-aninhados     # como era antes da F95
    python medir_rotulos.py --titulos           # imprime o que leu de cada um

As digitalizações e os PDFs não estão no repositório. Num clone limpo este
script diz o que não achou e sai — como o `medir_paginas.py` já faz.
"""

import argparse
import glob
import os
import sys
import time

import numpy as np

GABARITO = os.path.join("tests", "dados", "paginas_com_diagrama.txt")


def pdf_de(fragmento: str):
    """O PDF cujo caminho contém este pedaço de nome, ou None."""
    for caminho in sorted(glob.glob(os.path.join("PDF", "*", "*.pdf"))):
        if fragmento.lower() in caminho.lower() and "mapeamento" not in caminho:
            return caminho
    return None


def ler_gabarito(caminho: str):
    """[(fragmento do livro, página 1-based, quantos diagramas, coordenadas?)]."""
    linhas = []
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.split("#")[0].strip()
            if not linha:
                continue
            livro, pagina, quantos, coord = [c.strip()
                                             for c in linha.split("|")]
            linhas.append((livro, int(pagina), int(quantos),
                           None if coord == "-" else coord == "sim"))
    return linhas


class Contagem:
    def __init__(self):
        self.paginas = self.achados = self.esperados = 0
        self.faltando = self.sobrando = 0
        self.rotulos_certos = self.rotulos_medidos = 0
        self.titulos = self.titulos_lidos = 0
        self.custos = []

    def texto(self) -> str:
        mediana = (sorted(self.custos)[len(self.custos) // 2]
                   if self.custos else 0.0)
        return (
            f"{self.paginas} páginas\n"
            f"  achar     {self.achados} de {self.esperados} diagramas"
            f"   ({self.faltando} não achados, {self.sobrando} inventados)\n"
            f"  rótulos   {self.rotulos_certos} de {self.rotulos_medidos}"
            f" decisões 'há coordenadas?' certas\n"
            f"  título    {self.titulos} achados, {self.titulos_lidos} lidos"
            f" (dos {self.achados} diagramas)\n"
            f"  custo     mediana {mediana:.2f} s por página,"
            f" máximo {max(self.custos or [0]):.2f} s")


def medir(itens, *, aninhados=True, mostrar_titulos=False,
          progresso=None) -> Contagem:
    import fitz
    from PIL import Image

    from core import diagrama as diag
    from core.services.box_service import BoxService
    from core.services.learning_service import LearningService

    servico = LearningService()
    classificar = (servico.predict_neural if servico.load_predictor() else None)
    if classificar is None and progresso:
        progresso("  sem modelo de texto: título e orientação ficam de fora")

    contagem = Contagem()
    abertos = {}
    for fragmento, numero, quantos, tem_coordenadas in itens:
        if fragmento not in abertos:
            caminho = pdf_de(fragmento)
            if caminho is None:
                if progresso:
                    progresso(f"  {fragmento}: PDF não encontrado, pulando")
                abertos[fragmento] = None
            else:
                abertos[fragmento] = fitz.open(caminho)
        doc = abertos[fragmento]
        if doc is None or numero > doc.page_count:
            continue

        pix = doc[numero - 1].get_pixmap(dpi=300, colorspace=fitz.csGRAY,
                                         alpha=False)
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width)
        antes, binaria, escala, _cinza = BoxService.boxes_antes_do_descarte(
            Image.fromarray(img),
            max_contornos=BoxService.MAX_CONTORNOS_DE_TEXTO)

        comeco = time.time()
        caixas = diag.localizar(
            antes, escala=escala,
            imagem=img if aninhados else None,
            binaria=binaria if aninhados else None)
        contagem.custos.append(time.time() - comeco)

        contagem.paginas += 1
        contagem.esperados += quantos
        contagem.achados += len(caixas)
        contagem.faltando += max(0, quantos - len(caixas))
        contagem.sobrando += max(0, len(caixas) - quantos)

        for caixa in caixas:
            rotulos = diag.ler_rotulos(img, caixa, escala, classificar)
            if tem_coordenadas is not None:
                contagem.rotulos_medidos += 1
                contagem.rotulos_certos += rotulos.presentes == tem_coordenadas
            titulo = diag.ler_titulo(img, caixa, escala, classificar,
                                     boxes=antes, rotulos=rotulos)
            contagem.titulos += bool(titulo.caixa)
            contagem.titulos_lidos += bool(titulo.texto)
            if mostrar_titulos and progresso:
                progresso(f"    {fragmento} pg{numero} [{titulo.lado or '-':7s}]"
                          f" {titulo.texto!r}   {rotulos.resumo()}")

    for doc in abertos.values():
        if doc is not None:
            doc.close()
    return contagem


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--gabarito", default=GABARITO)
    p.add_argument("--sem-aninhados", action="store_true",
                   help="desliga a segunda passada: mede o estado anterior à F95")
    p.add_argument("--titulos", action="store_true",
                   help="imprime o título e os rótulos lidos de cada diagrama")
    args = p.parse_args(argv)

    if not os.path.exists(args.gabarito):
        print(f"gabarito não encontrado em {args.gabarito}", file=sys.stderr)
        return 1

    itens = ler_gabarito(args.gabarito)
    print(f"{len(itens)} páginas no gabarito"
          + (" (segunda passada desligada)" if args.sem_aninhados else ""))
    contagem = medir(itens, aninhados=not args.sem_aninhados,
                     mostrar_titulos=args.titulos, progresso=print)
    if not contagem.paginas:
        print("nenhuma página medida — os PDFs não estão neste clone",
              file=sys.stderr)
        return 1
    print("\n" + contagem.texto())
    return 0


if __name__ == "__main__":
    sys.exit(main())
