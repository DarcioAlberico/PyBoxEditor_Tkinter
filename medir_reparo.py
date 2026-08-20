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

**A prova visual é a F69**, e é ela que faz a fase pagar. Sem `--prova` o
dicionário decide sozinho e o empate no comprimento manda desistir — é a régua
que a F66 mediu e reprovou. Com `--prova`, o candidato é pontuado contra o
desenho do box (`BoxService.prova_de_reparo`) e o comprimento deixa de decidir:
`Dmamic` para de perder `dynamic` para `drazic`.

    python medir_reparo.py                  # a tabela da F66, sem prova
    python medir_reparo.py --prova          # a tabela da F69
    python medir_reparo.py --prova --nota 0 0.3 0.5 0.8   # varre a régua da prova
    python medir_reparo.py --suspeita 1.3 1.5 2.0         # varre a régua do box

As três colunas que importam:

    consertadas   o reparo trocou, e ficou igual ao rótulo
    estragadas    o reparo trocou, e ficou diferente do rótulo — o que não pode
    intocadas     o reparo desistiu (empate no dicionário, ou nada casou)

Com `--exemplos`, cada linha traz a nota da prova e a vantagem sobre o segundo
colocado — os dois números pelos quais a `NOTA_MINIMA` foi escolhida.

**O rótulo à mão não é a verdade aqui**, e a F69 registra por quê: em três das
sete páginas ele está incompleto, e reparo certo aparece como estrago. A coluna
`estragadas` desta tabela é teto, não conta — os 18 reparos da F69 foram
conferidos no impresso, um a um.
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


def medir(imagem, cx, lex, ls, limiar, prova=False,
          nota_minima=lexico.NOTA_MINIMA):
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
    # A prova pergunta ao **mesmo** modelo que leu a página, sobre a **mesma**
    # imagem em tom de cinza de que os boxes saíram: medir com outro recorte
    # mediria o recorte, e não a prova.
    provar = (BoxService.prova_de_reparo(arr, gerados, ls.probabilidade_de)
              if prova else None)
    reparos = lexico.reparos_da_pagina(gerados, largos, lex, provar,
                                       nota_minima)

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
        # Sem prova a nota sai 0,0 para todos, e a coluna não diria nada: some.
        marca = (f"  [nota {r.nota:.3f}  vantagem {r.vantagem:+.3f}]"
                 if prova else "")
        if alvo.lower() == r.corrigida.lower():
            certo += 1
            exemplos.append(f"  ✓ {r.palavra!r} -> {r.corrigida!r}{marca}")
        else:
            errado += 1
            exemplos.append(f"  ✗ {r.palavra!r} -> {r.corrigida!r} "
                            f"(era {alvo!r}){marca}")

    # As que continuaram fora do dicionário e tinham box suspeito: o reparo
    # olhou e desistiu. É o tamanho do que sobra para uma fase futura.
    intocadas = 0
    for simbolos in lexico._palavras_de_prosa(gerados):
        nuc, _ind = lexico.boxes_do_nucleo(simbolos)
        # `MIN_PARA_REPARAR`, e não `MIN_PARTE`: núcleo de duas letras não
        # é intocada, é população que o reparo nunca vê (F69). Contá-lo
        # aqui inflava o que sobra com o que já estava decidido.
        if len(nuc) < lexico.MIN_PARA_REPARAR or lex.conhece(nuc):
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
    ap.add_argument("--prova", action="store_true",
                    help="pontua o candidato contra o desenho do box (F69)")
    ap.add_argument("--nota", type=float, nargs="*", default=None,
                    help="varre NOTA_MINIMA; implica --prova")
    args = ap.parse_args()
    prova = args.prova or args.nota is not None

    raiz = os.path.dirname(os.path.abspath(__file__))
    lex = lexico.carregar()
    if not lex.sinaliza:
        print("Sem dicionário instalado — o reparo não age, e não há o que medir.")
        return
    ls = LearningService()

    limiares = args.suspeita or [lexico.SUSPEITA_DE_COLAGEM]
    notas = args.nota if args.nota else [lexico.NOTA_MINIMA]
    paginas = list(paginas_rotuladas(raiz))
    if not paginas:
        print("Nenhuma página rotulada — as digitalizações não estão no repo.")
        return
    # A prova precisa do modelo, e sem ele todo candidato tiraria 0,0: a tabela
    # sairia com zero reparo e pareceria medida, em vez de impedida.
    if prova and not ls.load_predictor():
        print("Sem modelo treinado — a prova visual não tem a quem perguntar.")
        return

    for limiar in limiares:
        for nota_minima in notas:
            certo = errado = intocadas = 0
            exemplos = []
            for imagem, cx in paginas:
                r = medir(imagem, cx, lex, ls, limiar, prova, nota_minima)
                if r is None:
                    continue
                certo += r[0]
                errado += r[1]
                intocadas += r[2]
                exemplos += r[3]
            tocadas = certo + errado
            regua = f" nota={nota_minima:<4g}" if prova else ""
            print(f"suspeita={limiar:<4g}{regua} consertadas={certo:3d}"
                  f"  estragadas={errado:3d}  intocadas={intocadas:3d}"
                  + (f"  (precisão {certo / tocadas:.0%})" if tocadas else ""))
            if args.exemplos:
                for e in exemplos:
                    print(e)


if __name__ == "__main__":
    sys.exit(main())
