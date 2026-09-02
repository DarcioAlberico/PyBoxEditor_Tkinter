"""
A faixa do diagrama come prosa, e as duas réguas óbvias não a separam (F115).

`livro._na_faixa` recolhe para o cabeçalho do diagrama toda caixa cujo **pé**
caia dentro de `MARGEM_DIAGRAMA` alturas de caractere acima da borda do
tabuleiro e que apenas **se sobreponha** a ele na horizontal. Num livro de
coluna única toda linha de prosa se sobrepõe, e a linha que passar perto demais
do tabuleiro sai do parágrafo: vira `<h2>` no EPUB e `Heading 2` no DOCX, ou —
se um caractere dela sair fraco — vira um PNG que ninguém pesquisa.

    python medir_faixa.py
    python medir_faixa.py --livro Darcy --paginas 120
    python medir_faixa.py --livro Darcy --mostrar

## O que ele mede

Para cada linha que a faixa recolhe, se ela **parece cabeçalho de diagrama**; e,
para as duas réguas candidatas, quanta prosa cada uma salvaria e quantos
cabeçalhos perderia. As três colunas juntas são o que decide, e foi assim que as
duas réguas foram recusadas na F115:

    régua                                     salva      perde
    cabe no retângulo de exclusão             5 de 19        2
    a linha continua fora da faixa           25 de 25       55

## A pergunta tem de ser "isto parece cabeçalho", e não "isto é prosa"

**É o erro que a primeira versão desta medição cometeu, e ele custou uma
conclusão errada.** Perguntar "há palavra de dicionário de quatro letras nesta
linha?" é cego duas vezes: o léxico do projeto é inglês, e o livro onde o
defeito acontece é em português (`Darcy Lima · A Estratégia`); e notação não tem
palavra de dicionário, que é o caso do EPUB do Kasparov, onde 111 dos 122 `<h2>`
são lance. Com aquela régua a varredura devolveu **zero em 240 páginas**; com
esta, o defeito aparece na primeira página que o tem.

O cabeçalho destes livros é `Diagram 12-1 △`, `➤ Ex. 22-1 ◀ ★★ ▼` ou `437` — e o
OCR o entrega mastigado (`Diagrram6 1`, `Di 235`, `I]iagram 2f3`), então o padrão
é frouxo de propósito. Errar para o lado de "é cabeçalho" **subestima** o defeito,
que é o lado seguro para um número que serve de acusação.
"""

import argparse
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fitz
from PIL import Image

from core import livro
from core.leitura_de_linha import quebrar_em_linhas
from core.services.box_service import BoxService
from core.services.learning_service import LearningService

RAIZ = "PDF"

#: Páginas sorteadas por livro. A semente é fixa para a tabela ser refeita.
POR_LIVRO = 60
SEMENTE = 11

#: A figurina denuncia notação, e notação nunca é cabeçalho de diagrama.
FIGURINA = re.compile(r"[♔♕♖♗♘♙♚♛♜♝♞♟]")

#: Abaixo disto a linha é fragmento de um ou dois glifos, e não prosa perdida.
CURTA = 2

#: O cabeçalho: dígito, pontuação, seta, estrela, e no máximo uma palavra —
#: `Diagram`, `Ex.`, ou o que o OCR fez delas.
CABECALHO = re.compile(r"^[\s\d.\-–—()\[\]△▽▼▲★☆◀▶➤⮞⮜■□○●+±∓=?!lI|]*"
                       r"(?:[DdIi][\w\[\]]*|[Ee]x\w*\.?|[A-Z])?"
                       r"[\s\d.\-–—()\[\]△▽▼▲★☆◀▶➤⮞⮜■□○●+±∓=?!lI|]*"
                       r"(?:\(\w+\))?"
                       r"[\s\d.\-–—()\[\]△▽▼▲★☆◀▶➤⮞⮜■□○●+±∓=?!lI|]*$")


def _console_em_utf8():
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            try:
                fluxo.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass


def pdfs(marca=None):
    """
    `(nome, caminho)` dos PDF de `PDF/`, um por pasta.

    A comparação é por pedaço do nome porque **o nome no disco vem em NFD** —
    acento decomposto —, e um caminho escrito à mão em NFC não casa com ele.
    """
    if not os.path.isdir(RAIZ):
        return
    for pasta in sorted(os.listdir(RAIZ)):
        if marca and marca.lower() not in pasta.lower():
            continue
        cheio = os.path.join(RAIZ, pasta)
        if not os.path.isdir(cheio):
            continue
        for f in sorted(os.listdir(cheio)):
            if (f.lower().endswith(".pdf") and "_teste" not in f
                    and "mapeamento" not in f):
                yield pasta[:30], os.path.join(cheio, f)
                break


def parece_cabecalho(texto: str) -> bool:
    """Esta linha é cabeçalho de diagrama? Ver o cabeçalho do módulo."""
    t = texto.strip()
    if len(t) <= CURTA:
        return True
    if FIGURINA.search(t):
        return False
    return bool(CABECALHO.match(t))


def linhas_da_faixa(img, tabuleiros, escala, ler):
    """`(diagrama, linha de caixas)` de tudo o que a faixa recolheu na página."""
    todas = BoxService.generate_boxes_opencv(Image.fromarray(img), arbitro=ler)
    minima = livro.MIN_AREA_GLIFO * escala * escala
    for d in tabuleiros:
        deste = [b for b in todas
                 if (b.x2 - b.x1) * (b.y2 - b.y1) >= minima
                 and not livro._dentro(b, d.exclusao)
                 and livro._na_faixa(b, d)]
        if not deste:
            continue
        for linha in quebrar_em_linhas(BoxService._agrupar_em_linhas(deste)):
            yield d, linha


def medir_livro(caminho, quantas, ler, mostrar=False):
    """`(recolhidas, prosa, salva_A, perde_A, salva_B, perde_B)`."""
    doc = fitz.open(caminho)
    try:
        random.seed(SEMENTE)
        alvos = sorted(random.sample(range(len(doc)),
                                     min(quantas, len(doc))))
        conta = [0] * 6
        for n in alvos:
            img = livro._pagina_cinza(doc[n], 300)
            try:
                fora, tabuleiros, escala, _r, _c = livro.caixas_e_diagramas(
                    img, ler)
            except Exception as erro:                        # noqa: BLE001
                print(f"  pg{n + 1}: {type(erro).__name__}: {erro}")
                continue
            if not tabuleiros:
                continue
            for d, linha in linhas_da_faixa(img, tabuleiros, escala, ler):
                texto, _f, _p = livro._texto_da_linha(img, linha, ler,
                                                      livro.CONF_MINIMA)
                e_cabecalho = parece_cabecalho(texto)
                # Régua A: a linha inteira cabe no retângulo de exclusão.
                cabe = (min(b.x1 for b in linha) >= d.exclusao[0]
                        and max(b.x2 for b in linha) <= d.exclusao[2])
                # Régua B: há texto de página na mesma altura desta linha, quer
                # dizer, a linha continua fora da faixa.
                topo, base = min(b.y1 for b in linha), max(b.y2 for b in linha)
                continua = any(topo <= (b.y1 + b.y2) / 2 <= base for b in fora)

                conta[0] += 1
                conta[1] += not e_cabecalho
                conta[2] += (not e_cabecalho) and not cabe
                conta[3] += e_cabecalho and not cabe
                conta[4] += (not e_cabecalho) and continua
                conta[5] += e_cabecalho and continua
                if mostrar:
                    print(f"  pg{n + 1:4d} "
                          f"{'CABEÇALHO' if e_cabecalho else 'PROSA    '} "
                          f"cabe={int(cabe)} continua={int(continua)} "
                          f"{texto[:56]!r}", flush=True)
        return conta
    finally:
        doc.close()


def main(argv=None) -> int:
    _console_em_utf8()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--livro", default=None,
                    help="pedaço do nome da pasta; sem isto, todos")
    ap.add_argument("--paginas", type=int, default=POR_LIVRO,
                    help=f"páginas sorteadas por livro (padrão {POR_LIVRO})")
    ap.add_argument("--mostrar", action="store_true",
                    help="uma linha por linha recolhida")
    args = ap.parse_args(argv)

    servico = LearningService()
    if not servico.load_predictor():
        raise SystemExit(f"sem modelo: {servico.motivo_do_modelo()}")
    ler = servico.ler_texto

    total = [0] * 6
    print(f"{'livro':32s} {'páginas':>7s} {'recolhidas':>11s} {'prosa':>7s}")
    for nome, caminho in pdfs(args.livro):
        if args.mostrar:
            print(f"\n===== {nome} =====")
        conta = medir_livro(caminho, args.paginas, ler, args.mostrar)
        print(f"{nome:32s} {args.paginas:7d} {conta[0]:11d} {conta[1]:7d}",
              flush=True)
        total = [a + b for a, b in zip(total, conta)]

    print(f"\n{'TOTAL':32s} {'':7s} {total[0]:11d} {total[1]:7d}")
    print("\nas duas réguas candidatas, e o que cada uma custa")
    print(f"{'régua':46s} {'salva':>7s} {'perde':>7s}")
    print(f"{'cabe no retângulo de exclusão':46s} {total[2]:7d} {total[3]:7d}")
    print(f"{'a linha continua fora da faixa':46s} {total[4]:7d} {total[5]:7d}")
    print("\n`perde` é cabeçalho legítimo que a régua devolveria para a prosa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
