"""
Mede o reparo de colagem — a régua da F66.

**Por que existe.** O modelo lê bem: com o box certo, as 10 páginas rotuladas
saem a 98% e o cabeçalho `The Dynamic Benko Gambit` sai perfeito. O que estraga
o livro exportado é **colagem**: dois glifos que se encostam viram um box, e o
box vira um caractere só — `Dynamic` sai `Dmamic`, `manoeuvres` sai `manoeumes`.

Medido, são 96 boxes com 2+ caracteres dentro nas 10 páginas, em **74 pares
distintos** — cauda plana, sem punhado de ligaduras para acrescentar. E o
separador de colados já está no ótimo que o ROADMAP mediu (F1.5b).

O que sobra é o dicionário, que já sabe: das palavras estragadas, 10 em 11 não
existem no léxico, e as 11 certas existem todas. Este script mede se dá para
**consertar** em vez de só sinalizar, e a que preço.

    python medir_reparo.py                  # a tabela do ROADMAP
    python medir_reparo.py --suspeita 1.3 1.5 2.0    # varre a régua do box

As três colunas que importam:

    consertadas   o reparo trocou, e ficou igual ao rótulo
    estragadas    o reparo trocou, e ficou diferente do rótulo — o que não pode
    intocadas     o reparo desistiu (empate no dicionário, ou nada casou)
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

from core import lexico, vertical
from core.avaliacao_pagina import _centro_dentro, carregar_box
from core.calibracao_de_pagina import paginas_rotuladas
from core.services.box_service import BoxService
from core.services.learning_service import LearningService


def _verdade_das_palavras(rotulados):
    """{núcleo lido -> núcleo rotulado} não serve: a chave é a posição."""
    return rotulados


def medir(imagem, cx, lex, ls, limiar):
    """(consertadas, estragadas, intocadas, exemplos)."""
    with Image.open(imagem) as im:
        arr = np.array(im.convert("L"))
    rotulados = carregar_box(cx, arr.shape[0])
    if len(rotulados) < 50:
        return None

    gerados = BoxService.generate_boxes_opencv(Image.fromarray(arr),
                                               arbitro=ls.predict_neural)
    for g in gerados:
        recorte = vertical.recorte_de_pe(arr, g)
        g.char = ls.predict_neural(recorte)[0] if recorte.size else ""

    largos = lexico.boxes_largos(gerados, limiar)
    reparos = lexico.reparos_da_pagina(gerados, largos, lex)

    certo = errado = 0
    exemplos = []
    for r in reparos:
        # A verdade da palavra: os caracteres rotulados cujo centro cai **em
        # cada box** que a compõe, e não no retângulo que envolve todos.
        #
        # A primeira versão usava o retângulo, e ele mente nos dois sentidos: o
        # espaço entre dois boxes da mesma palavra recolhe caractere vizinho, e
        # box justo demais perde o rótulo do glifo alto. Medido, ela acusou
        # `example` e `tournament` — dois reparos **certos** — como estrago.
        dentro = []
        for i in r.indices:
            g = gerados[i]
            dentro += sorted((b for b in rotulados if _centro_dentro(b, g)),
                             key=lambda b: b.x1)
        alvo = lexico.nucleo("".join(b.char for b in dentro))[0]
        if alvo.lower() == r.corrigida.lower():
            certo += 1
            exemplos.append(f"  ✓ {r.palavra!r} -> {r.corrigida!r}")
        else:
            errado += 1
            exemplos.append(f"  ✗ {r.palavra!r} -> {r.corrigida!r} "
                            f"(era {alvo!r})")

    # As que continuaram fora do dicionário e tinham box suspeito: o reparo
    # olhou e desistiu. É o tamanho do que sobra para uma fase futura.
    intocadas = 0
    for simbolos in lexico._palavras_de_prosa(gerados):
        nuc, _ind = lexico.boxes_do_nucleo(simbolos)
        if len(nuc) < lexico.MIN_PARTE or lex.conhece(nuc):
            continue
        if any(i in largos for _c, i in simbolos):
            intocadas += 1
    intocadas -= certo + errado
    return certo, errado, max(0, intocadas), exemplos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suspeita", type=float, nargs="*", default=None,
                    help="varre SUSPEITA_DE_COLAGEM")
    ap.add_argument("--exemplos", action="store_true",
                    help="lista palavra a palavra")
    args = ap.parse_args()

    raiz = os.path.dirname(os.path.abspath(__file__))
    lex = lexico.carregar()
    if not lex.sinaliza:
        print("Sem dicionário instalado — o reparo não age, e não há o que medir.")
        return
    ls = LearningService()

    limiares = args.suspeita or [lexico.SUSPEITA_DE_COLAGEM]
    paginas = list(paginas_rotuladas(raiz))
    if not paginas:
        print("Nenhuma página rotulada — as digitalizações não estão no repo.")
        return

    for limiar in limiares:
        certo = errado = intocadas = 0
        exemplos = []
        for imagem, cx in paginas:
            r = medir(imagem, cx, lex, ls, limiar)
            if r is None:
                continue
            certo += r[0]
            errado += r[1]
            intocadas += r[2]
            exemplos += r[3]
        tocadas = certo + errado
        print(f"suspeita={limiar:<4g} consertadas={certo:3d}  estragadas={errado:3d}"
              f"  intocadas={intocadas:3d}"
              + (f"  (precisão {certo / tocadas:.0%})" if tocadas else ""))
        if args.exemplos:
            for e in exemplos:
                print(e)


if __name__ == "__main__":
    sys.exit(main())
