"""
Mede a altura de referência do veto de tamanho (F106) e a exceção do pontilhado (F121).

O veto de tamanho separa o `.` do `■` pelo maior lado do recorte contra
`proporcao.altura_de_referencia`. Até a F121 ela era a mediana da altura dos
boxes da página, sempre; num sumário de pontilhado os pontos são a maioria, a
mediana vira a altura de um ponto, e o ponto é vetado como grande demais. Este
script responde às três perguntas que decidem se a exceção pode entrar:

    onde ela muda   em que páginas a referência nova difere da mediana — e em
                    nenhuma página comum ela pode diferir, porque é sobre a
                    mediana que o envelope de `TAMANHO` foi medido
    o par           o `.` e o `■` rotulados, em múltiplos da referência, antes e
                    depois: o vão entre os dois tem de continuar aberto
    a leitura       nas páginas em que ela muda, o que `ler_texto` passa a ler

    python medir_referencia.py                    # as páginas com .box
    python medir_referencia.py --gerados          # com os boxes que a janela gera
    python medir_referencia.py --primeiras 18     # as 18 primeiras de cada PDF
    python medir_referencia.py --pdf LIVRO.pdf --paginas 3 4 8

**A leitura só roda onde a referência mudou**, e não por economia: `ler_texto` é
determinístico no recorte, na referência e no idioma, então página com a mesma
referência lê igual até o último caractere. Contar as duas seria medir a mesma
coisa duas vezes.

**`--gerados` é a população da janela.** O «Detectar e Preencher» tira a
referência dos boxes que `generate_boxes_opencv` acabou de gerar, e não do
gabarito; os dois dão a mesma referência em todas as páginas rotuladas, e o
modo existe para dizer isso medindo. As razões do par continuam sendo as dos
boxes rotulados, que são os que têm rótulo.

**`--primeiras` e `--pdf` renderizam como a janela** (`pdf_service`, 300 dpi, em
cinza) e segmentam como ela, com a rede de árbitro. Ali não há rótulo: a coluna
que diz alguma coisa é a das trocas de leitura.

Reproduz a F121 no ROADMAP.
"""

import argparse
import collections
import os
import sys

import numpy as np
from PIL import Image

from core import proporcao
from core.avaliacao_pagina import carregar_box
from core.calibracao_de_pagina import paginas_rotuladas
from core.services.box_service import BoxService
from core.services.learning_service import LearningService
from medir_tamanho import paginas_com_box

#: Os dois lados do par que o veto de tamanho separa.
PAR = (".", "■")


def _console_em_utf8():
    """O mesmo de `medir_proporcao.py`: sem isto, o `■` derruba o script no cp1252."""
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def mediana_da_pagina(boxes):
    """A referência de antes da F121: a mediana da altura, sempre."""
    alturas = sorted(b.y2 - b.y1 for b in boxes if b.y2 > b.y1)
    return float(alturas[len(alturas) // 2]) if alturas else None


def paginas_com_gabarito(raiz):
    """`[(imagem, .box)]` — as de `paginas_com_box` e as de `paginas_rotuladas`."""
    achadas = {os.path.normpath(box): img for img, box in paginas_com_box(raiz)}
    for img, box in paginas_rotuladas(raiz):
        achadas.setdefault(os.path.normpath(box), img)
    return sorted((img, box) for box, img in achadas.items())


def paginas_de_pdf(pdfs, numeros=None, primeiras=None):
    """`[(nome, imagem)]`, renderizadas como a janela abre uma página de PDF."""
    import fitz
    from core.services.pdf_service import DPI_PADRAO, _para_pil

    for pdf in pdfs:
        with fitz.open(pdf) as doc:
            quais = numeros or range(1, min(primeiras, len(doc)) + 1)
            for n in quais:
                yield (f"{os.path.basename(pdf)} p. {n}",
                       _para_pil(doc[n - 1], DPI_PADRAO, cinza=True))


def pdfs_do_corpus(raiz):
    """Um PDF por livro da pasta `PDF/` — sem as cópias de teste e de mapeamento."""
    achados = []
    for pasta, _d, arquivos in os.walk(os.path.join(raiz, "PDF")):
        for a in arquivos:
            if (a.lower().endswith(".pdf") and "Convertidos" not in pasta
                    and "mapeamento" not in a and "teste" not in a):
                achados.append(os.path.join(pasta, a))
    return sorted(achados)


def ler(servico, arr, boxes, referencia, idioma):
    return [servico.ler_texto(arr[b.y1:b.y2, b.x1:b.x2], referencia,
                              idioma=idioma)[0] for b in boxes]


def comparar_leituras(servico, arr, boxes, antes, depois, idioma, rotulados):
    """As leituras que mudam de uma referência para a outra, contra o rótulo se há."""
    velhas = ler(servico, arr, boxes, antes, idioma)
    novas = ler(servico, arr, boxes, depois, idioma)
    conta = collections.Counter()
    trocas = collections.Counter()
    for b, v, n in zip(boxes, velhas, novas):
        rotulo = b.char if rotulados else None
        if rotulo is not None:
            conta["rotulados"] += 1
            conta["certo_antes"] += v == rotulo
            conta["certo_depois"] += n == rotulo
        if v == n:
            continue
        conta["mexidas"] += 1
        if rotulo is not None:
            conta["consertou"] += n == rotulo
            conta["quebrou"] += v == rotulo
        trocas[(rotulo, v, n)] += 1
    return conta, trocas


def _linha_de_trocas(conta, trocas, quantas=6):
    partes = [f"{conta['mexidas']} leituras mudam"]
    if conta["rotulados"]:
        partes.append(f"consertou {conta['consertou']}, quebrou {conta['quebrou']}; "
                      f"acerto {conta['certo_antes'] / conta['rotulados']:.2%} -> "
                      f"{conta['certo_depois'] / conta['rotulados']:.2%}")
    linhas = ["      " + " · ".join(partes)]
    # As que quebraram saem todas, e não só as mais comuns: são elas que decidem.
    comuns = trocas.most_common(quantas)
    quebras = [(t, q) for t, q in trocas.items()
               if t[0] is not None and t[0] == t[1] and (t, q) not in comuns]
    for (rotulo, v, n), q in comuns + quebras:
        de = f"{rotulo!r} lido " if rotulo is not None else ""
        marca = "  QUEBROU" if rotulo is not None and v == rotulo else ""
        linhas.append(f"      {q:6d}x  {de}{v!r} -> {n!r}{marca}")
    return "\n".join(linhas)


def _par_na_pagina(rotulados, antes, depois):
    """A faixa do `.` e do `■` rotulados desta página, em múltiplos das duas referências."""
    partes = []
    for c in PAR:
        lados = [max(b.x2 - b.x1, b.y2 - b.y1) for b in rotulados if b.char == c]
        if lados:
            partes.append(f"{c!r} {min(lados) / antes:.2f}–{max(lados) / antes:.2f} -> "
                          f"{min(lados) / depois:.2f}–{max(lados) / depois:.2f}")
    return "      " + " · ".join(partes) if partes else None


def _faixa(valores):
    if not valores:
        return "—"
    v = np.array(valores)
    return (f"n={len(v):>4}  mín {v.min():.2f}  p10 {np.percentile(v, 10):.2f}  "
            f"mediana {np.median(v):.2f}  p90 {np.percentile(v, 90):.2f}  "
            f"máx {v.max():.2f}")


def medir_rotuladas(args, servico):
    arbitro = servico.predict_neural if args.gerados else None
    razoes = {(c, lado): [] for c in PAR for lado in ("antes", "depois")}
    total = mudaram = 0
    for img_p, box_p in paginas_com_gabarito(args.raiz):
        img = Image.open(img_p).convert("L")
        rotulados = [b for b in carregar_box(box_p, img.size[1])
                     if b.x2 > b.x1 and b.y2 > b.y1]
        if len(rotulados) < 20:
            continue
        base = (BoxService.generate_boxes_opencv(img, arbitro=arbitro)
                if args.gerados else rotulados)
        antes, depois = mediana_da_pagina(base), proporcao.altura_de_referencia(base)
        total += 1
        for b in rotulados:
            if b.char in PAR:
                lado = max(b.x2 - b.x1, b.y2 - b.y1)
                razoes[(b.char, "antes")].append(lado / antes)
                razoes[(b.char, "depois")].append(lado / depois)
        if antes == depois:
            continue
        mudaram += 1
        print(f"  {os.path.basename(box_p)}: {len(base)} boxes, "
              f"referência {antes:.0f} -> {depois:.0f}")
        par = _par_na_pagina(rotulados, antes, depois)
        if par:
            print(par)
        conta, trocas = comparar_leituras(servico, np.array(img), rotulados,
                                          antes, depois, args.idioma, True)
        print(_linha_de_trocas(conta, trocas))
    print(f"\n{total} páginas com gabarito; a referência muda em {mudaram}\n")
    print("maior lado ÷ referência, nos boxes rotulados do par "
          "(o corte de `TAMANHO` é 0,7):")
    corte = proporcao.TAMANHO["."][1]
    for c in PAR:
        for lado in ("antes", "depois"):
            valores = razoes[(c, lado)]
            errados = (sum(v > corte for v in valores) if c == "."
                       else sum(v < corte for v in valores))
            print(f"  {c!r} {lado:<6}  {_faixa(valores)}   "
                  f"do lado errado do corte: {errados}")


def medir_pdf(args, servico, pdfs):
    total = mudaram = 0
    for nome, img in paginas_de_pdf(pdfs, args.paginas, args.primeiras):
        boxes = BoxService.generate_boxes_opencv(img, arbitro=servico.predict_neural)
        if not boxes:
            continue
        antes, depois = mediana_da_pagina(boxes), proporcao.altura_de_referencia(boxes)
        total += 1
        if antes == depois:
            continue
        mudaram += 1
        print(f"  {nome}: {len(boxes)} boxes, referência {antes:.0f} -> {depois:.0f}",
              flush=True)
        conta, trocas = comparar_leituras(servico, np.array(img), boxes,
                                          antes, depois, args.idioma, False)
        print(_linha_de_trocas(conta, trocas), flush=True)
    print(f"\n{total} páginas; a referência muda em {mudaram}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--gerados", action="store_true",
                    help="a referência dos boxes que a janela gera, e não do gabarito")
    ap.add_argument("--pdf", nargs="+", help="PDFs a percorrer pela janela")
    ap.add_argument("--paginas", type=int, nargs="+",
                    help="com --pdf: as páginas (contadas de 1)")
    ap.add_argument("--primeiras", type=int,
                    help="as N primeiras páginas de cada PDF de PDF/ (ou de --pdf)")
    ap.add_argument("--idioma", default=None,
                    help="a máscara de alfabeto de `ler_texto` (en, pt); sem ela, desligada")
    ap.add_argument("--raiz", default=".")
    args = ap.parse_args(argv)
    _console_em_utf8()

    servico = LearningService()
    if not servico.load_predictor():
        print(servico.motivo_do_modelo())
        return 1

    if args.pdf or args.primeiras:
        pdfs = args.pdf or pdfs_do_corpus(args.raiz)
        if not args.paginas and not args.primeiras:
            ap.error("--pdf pede --paginas ou --primeiras")
        medir_pdf(args, servico, pdfs)
    else:
        medir_rotuladas(args, servico)
    return 0


if __name__ == "__main__":
    sys.exit(main())
