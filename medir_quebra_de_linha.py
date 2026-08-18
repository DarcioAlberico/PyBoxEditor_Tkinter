"""
Mede a quebra de linha — a régua da F63.

**Por que existe.** `quebrar_em_linhas` cortava onde a caixa nova descia em
relação à **caixa anterior sozinha**. Um apóstrofo é uma caixa curta plantada no
alto: o fundo dele fica na altura de x, e qualquer letra depois dele tem o
centro abaixo disso. A linha se parte no meio, e no livro exportado a prosa sai
picada — `following fresh` / `high-` / `quality encounter` em três parágrafos.

Duas medidas, e elas puxam para lados opostos:

    corte no meio   corte que não é `voltou`, isto é, que não coincide com o
                    fim de linha de verdade (a leitura voltando para a
                    esquerda). É o defeito, e tem de cair.
    linha alta      linha cujo conjunto de caixas cobre mais de `--alto`
                    alturas medianas. É o risco do conserto — régua frouxa
                    demais funde duas linhas numa —, e não pode subir.

    python medir_quebra_de_linha.py                       # antes e hoje
    python medir_quebra_de_linha.py --curto 0 0.5 0.65 0.8  # varre a régua
    python medir_quebra_de_linha.py --bandas              # a tabela da F64

`--bandas` mede um degrau antes: a **banda** de linha que o `_linhas` forma, e
quantas delas são feitas só de caixa curta. Banda só de aspas é o apóstrofo
abrindo linha sozinho, e é o que faz `White's` sair `' White s`.

A coluna "antes" é a régua da F61 **reescrita aqui**, e não um valor da de hoje:
a mudança tem duas partes — a base sai da linha em vez da caixa anterior, e
caixa curta não fixa base — e nenhum ponto do parâmetro reproduz as duas. É a
mesma solução que o modo `global` do `medir_paginas.py`: linha de base
histórica, mantida no instrumento para a tabela poder ser refeita.
"""

import argparse
import os
import sys

from PIL import Image

from core import leitura_de_linha as ldl
from core.avaliacao_pagina import carregar_box
from core.calibracao_de_pagina import paginas_rotuladas
from core.services.box_service import BoxService

#: Quantas alturas medianas uma linha pode cobrir antes de ser suspeita de ter
#: fundido duas. Uma linha de texto normal cobre pouco mais de uma — o que
#: passa disso é ascendente de uma somado a descendente da outra.
ALTO_PADRAO = 1.8


def quebrar_como_na_f61(boxes):
    """
    A régua de antes da F63: descer é contra a **caixa anterior**.

    Cópia declarada, e não parâmetro: é a linha de base histórica da tabela, do
    mesmo jeito que o modo `global` do `medir_paginas.py`. Ninguém deve chamá-la
    em produção — quem faz isso é `leitura_de_linha.quebrar_em_linhas`.
    """
    linhas, atual = [], []
    for b in boxes:
        if atual:
            ant = atual[-1]
            desceu = (b.y1 + b.y2) / 2 > ant.y2
            voltou = b.x1 < ant.x1 - (ant.y2 - ant.y1)
            girado = getattr(b, "angulo", 0) or getattr(ant, "angulo", 0)
            subiu = not girado and b.y2 < min(a.y1 for a in atual)
            if desceu or voltou or subiu:
                linhas.append(atual)
                atual = []
        atual.append(b)
    if atual:
        linhas.append(atual)
    return linhas


def bandas_como_na_f16(boxes):
    """
    A banda de antes da F64: o fundo médio sai de **todas** as caixas da banda.

    Cópia declarada, como a `quebrar_como_na_f61`. Ninguém deve chamá-la em
    produção — quem faz isso é `BoxService._linhas`.
    """
    grupos, atual = [], []
    for b in sorted(boxes, key=lambda b: b.y1):
        if not atual:
            atual = [b]
            continue
        fundo = sum(i.y2 for i in atual) / len(atual)
        if (b.y1 + b.y2) / 2 <= fundo + (b.y2 - b.y1) * 0.2:
            atual.append(b)
        else:
            grupos.append(atual)
            atual = [b]
    if atual:
        grupos.append(atual)
    return grupos


def medir_bandas(boxes, bandas_de):
    """(bandas, bandas feitas só de caixa curta)."""
    alturas = sorted(b.y2 - b.y1 for b in boxes)
    curto = (alturas[len(alturas) // 2] or 1) * ldl.CAIXA_CURTA
    bandas = bandas_de(boxes)
    orfas = [B for B in bandas if all((b.y2 - b.y1) < curto for b in B)]
    return bandas, orfas


def medir(boxes, alto, quebrar=None):
    """(linhas, cortes no meio, linhas altas)."""
    ordenados = BoxService.sort_boxes_reading_order(list(boxes))
    linhas = (quebrar or ldl.quebrar_em_linhas)(ordenados)

    alturas = sorted(b.y2 - b.y1 for b in ordenados)
    mediana = alturas[len(alturas) // 2] or 1

    # O corte "no meio" é o que nenhuma das duas regras legítimas explica: a
    # leitura não voltou para a esquerda (fim de linha) e não subiu para a
    # coluna vizinha. Sem tirar a troca de coluna, toda página de duas colunas
    # entraria na conta com um corte que está certo.
    #
    # **A troca de coluna é medida com a folga da F65**, e não por "subiu um
    # pixel": o apóstrofo sobe 0,14 altura mediana e a coluna vizinha sobe 66.
    # Sem a folga aqui, o corte que a F65 conserta era contado como legítimo e
    # a tabela não via o defeito.
    no_meio = 0
    for anterior, seguinte in zip(linhas, linhas[1:]):
        ant, b = anterior[-1], seguinte[0]
        voltou = b.x1 < ant.x1 - (ant.y2 - ant.y1)
        subiu = (b.y2 < min(a.y1 for a in anterior)
                 - mediana * ldl.FOLGA_DE_COLUNA)
        if not voltou and not subiu:
            no_meio += 1

    altas = sum(1 for L in linhas
                if max(b.y2 for b in L) - min(b.y1 for b in L) > mediana * alto)
    return len(linhas), no_meio, altas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--curto", type=float, nargs="*", default=None,
                    help="varre CAIXA_CURTA (0 reproduz o de antes da F63)")
    ap.add_argument("--alto", type=float, default=ALTO_PADRAO,
                    help="quantas alturas medianas fazem uma linha suspeita")
    ap.add_argument("--bandas", action="store_true",
                    help="mede a banda do `_linhas` em vez da linha (F64)")
    args = ap.parse_args()

    # (rótulo, CAIXA_CURTA, função de quebra) — `None` quer dizer a de produção.
    if args.curto is not None:
        reguas = [(f"{c:g}", c, None) for c in args.curto]
    else:
        reguas = [("antes", ldl.CAIXA_CURTA, quebrar_como_na_f61),
                  ("hoje", ldl.CAIXA_CURTA, None)]
    raiz = os.path.dirname(os.path.abspath(__file__))

    paginas = []
    for imagem, caminho in paginas_rotuladas(raiz):
        with Image.open(imagem) as img:
            altura = img.height
        boxes = carregar_box(caminho, altura)
        if len(boxes) >= 50:
            paginas.append((os.path.basename(imagem)[-14:], boxes))

    if not paginas:
        print("Nenhuma página rotulada — as digitalizações não estão no repo.")
        return

    if args.bandas:
        print(f"{'página':16s} | {'antes':>6s} bandas órfãs | {'hoje':>6s} bandas órfãs")
        totais = {"antes": [0, 0], "hoje": [0, 0]}
        for nome, boxes in paginas:
            texto = f"{nome:16s}"
            for rotulo, bandas_de in (("antes", bandas_como_na_f16),
                                      ("hoje", BoxService._linhas)):
                bandas, orfas = medir_bandas(boxes, bandas_de)
                totais[rotulo][0] += len(bandas)
                totais[rotulo][1] += len(orfas)
                texto += (f" | {'':6s}{len(bandas):6d} {len(orfas):5d}"
                          + (f" {[''.join(b.char for b in B) for B in orfas]}"
                             if orfas else ""))
            print(texto)
        print()
        for rotulo in ("antes", "hoje"):
            bandas, orfas = totais[rotulo]
            print(f"{rotulo:>6s}: bandas={bandas:5d}  só de caixa curta={orfas:3d}")
        return

    cabecalho = f"{'página':16s}"
    for rotulo, _c, _q in reguas:
        cabecalho += f" | {rotulo:>6s} linhas meio altas"
    print(cabecalho)

    totais = {r[0]: [0, 0, 0] for r in reguas}
    for nome, boxes in paginas:
        texto = f"{nome:16s}"
        for rotulo, curto, quebrar in reguas:
            antes = ldl.CAIXA_CURTA
            ldl.CAIXA_CURTA = curto
            try:
                n, meio, altas = medir(boxes, args.alto, quebrar)
            finally:
                ldl.CAIXA_CURTA = antes
            for i, v in enumerate((n, meio, altas)):
                totais[rotulo][i] += v
            texto += f" | {'':6s}{n:4d} {meio:4d} {altas:5d}"
        print(texto)

    print()
    for rotulo, _c, _q in reguas:
        n, meio, altas = totais[rotulo]
        print(f"{rotulo:>6s}: linhas={n:5d}  cortes no meio={meio:4d} "
              f"({meio / max(1, n):.0%})  linhas altas={altas:3d}")


if __name__ == "__main__":
    sys.exit(main())
