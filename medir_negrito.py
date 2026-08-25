"""
Mede a régua do negrito — a da F105.

**O gabarito é o próprio PDF, e existe um livro só que o tem.** O Dvoretsky foi
composto em Times de verdade e a camada de texto dele nomeia a fonte de cada
span: `TimesNewRomanPS-BoldMT` contra `TimesNewRomanPSMT`. Nos outros livros
desta pasta a camada veio de um OCR de fábrica que reembutiu as fontes com nomes
gerados (`Fd350139`), e ali não há como saber qual era o peso — por isso o
instrumento não os varre.

O que ele mede é a **régua**, e não a extração: os recortes saem das caixas de
caractere que o próprio PDF declara, e não da segmentação. É de propósito. A
pergunta desta fase é "espessura separa peso?", e misturá-la com "a segmentação
achou o glifo?" responderia as duas ao mesmo tempo e nenhuma direito.

    python medir_negrito.py                  # a régua, unidade e referência
    python medir_negrito.py --limiar         # varredura fina do limiar
    python medir_negrito.py --palavra        # acerto por tamanho de palavra
    python medir_negrito.py --glifo          # a régua num caractere sozinho
    python medir_negrito.py --fontes         # a razão negrito÷redondo por família
    python medir_negrito.py --paginas 60     # quantas páginas amostrar

`--fontes` não usa livro nenhum: desenha o alfabeto nas famílias instaladas, nos
dois pesos, e mede a razão entre eles. É a prova de que o limiar não é um número
do Times — e é onde se vê que ele encolhe no corpo miúdo.

**As decisões saem todas de `core.negrito`**, e nenhuma é recopiada aqui: a
alternativa histórica (a referência pela mediana, que a fase descartou) está
declarada como tal em `referencia_pela_mediana`, do mesmo jeito que o
`quebrar_como_na_f61` do `medir_quebra_de_linha.py`.
"""

import argparse
import collections
import glob
import os
import random
import sys

import numpy as np

from core import negrito

#: O único livro desta pasta cuja camada de texto nomeia as fontes.
LIVRO = "Dvoretsky"

#: Páginas amostradas por padrão, e a semente que as escolhe.
PAGINAS = 40
SEMENTE = 7

#: O dpi da leitura. O mesmo do `livro.extrair`, e não é detalhe: a espessura
#: relativa cresce com o corpo em pixels — ver a tabela do `--fontes`.
DPI = 300

#: As famílias do Windows que o `--fontes` varre, em (redondo, negrito).
FAMILIAS = (("Times", "times.ttf", "timesbd.ttf"),
            ("Georgia", "georgia.ttf", "georgiab.ttf"),
            ("Bookman", "BOOKOS.TTF", "BOOKOSB.TTF"),
            ("Arial", "arial.ttf", "arialbd.ttf"),
            ("Cambria", "cambria.ttc", "cambriab.ttf"),
            ("Constantia", "constan.ttf", "constanb.ttf"),
            ("Palatino", "pala.ttf", "palab.ttf"),
            ("Garamond", "GARA.TTF", "GARABD.TTF"),
            ("Sitka", "Sitka.ttc", "SitkaB.ttc"),
            ("Calibri", "calibri.ttf", "calibrib.ttf"))

#: Os corpos em pixels do `--fontes`: 30 px são ~7 pt a 300 dpi (nota de rodapé),
#: 44 px o corpo de texto destes livros, 60 px um subtítulo.
CORPOS = (30, 44, 60)


def referencia_pela_mediana(amostras):
    """
    A referência que a F105 descartou: a mediana em vez do quantil baixo.

    Cópia declarada, e não parâmetro. Ela supõe que a maior parte das aparições
    de cada caractere está no peso redondo, e num livro de xadrez isso é falso
    para os dígitos — a notação é negrito. Ninguém deve chamá-la em produção;
    quem responde lá é `negrito.referencia`.
    """
    return {ch: float(np.median(v)) for ch, v in amostras.items() if v}


def caminho_do_livro(raiz):
    achados = [p for p in glob.glob(os.path.join(raiz, "PDF", "*", "*.pdf"))
               if LIVRO.lower() in os.path.basename(p).lower()]
    return achados[0] if achados else None


def linhas_da_pagina(page, dpi=DPI):
    """
    As linhas da página como `(texto, espessuras, verdade)`.

    `verdade` é, caractere a caractere, o que o PDF declara: `True` onde o span
    é `…-BoldMT`. O texto sai com um espaço onde a produção poria um — vão maior
    que uma fração da largura mediana, a mesma regra do `_texto_da_linha` —, e
    não onde a camada de texto diz: um corte diferente mediria outra coisa.
    """
    import fitz

    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height,
                                                             pix.width)
    escala = dpi / 72.0
    saida = []
    for bloco in page.get_text("rawdict")["blocks"]:
        for linha in bloco.get("lines", []):
            medidos = []
            for span in linha["spans"]:
                # A fonte de xadrez fica de fora: ela tem um peso só, e o glifo
                # dela não é letra de nenhuma família.
                if "Chess" in span["font"]:
                    continue
                forte = "Bold" in span["font"]
                for c in span["chars"]:
                    if not c["c"].strip():
                        continue
                    x1, y1, x2, y2 = [v * escala for v in c["bbox"]]
                    recorte = img[max(0, int(y1)):int(np.ceil(y2)),
                                  max(0, int(x1)):int(np.ceil(x2))]
                    medidos.append((c["c"], forte, negrito.espessura(recorte),
                                    x1, x2))
            montada = _montar_linha(medidos)
            if montada is not None:
                saida.append(montada)
    return saida


def _montar_linha(medidos):
    """Os caracteres medidos viram (texto, espessuras, verdade) de uma linha."""
    if not medidos:
        return None
    vao = 0.35 * float(np.median([m[4] - m[3] for m in medidos]))
    texto, pesos, verdade, anterior = [], [], [], None
    for m in medidos:
        if anterior is not None and m[3] - anterior[4] > vao:
            texto.append(" ")
            pesos.append(None)
            verdade.append(False)
        texto.append(m[0])
        pesos.append(m[2])
        verdade.append(m[1])
        anterior = m
    return "".join(texto), pesos, verdade


def palavras_de(linhas):
    """As palavras destas linhas, como (verdade, glifos medidos)."""
    saida = []
    for texto, pesos, verdade in linhas:
        for inicio, fim in negrito._palavras(texto):
            glifos = [(ch, e) for ch, e in zip(texto[inicio:fim],
                                               pesos[inicio:fim])
                      if e is not None]
            if glifos:
                saida.append((np.mean(verdade[inicio:fim]) > 0.5, glifos))
    return saida


def colher(caminho, quantas, dpi=DPI):
    """{número da página: linhas dela}, de uma amostra fixa do livro."""
    import fitz

    doc = fitz.open(caminho)
    try:
        random.seed(SEMENTE)
        alvo = sorted(random.sample(range(40, min(doc.page_count, 780)),
                                    min(quantas, doc.page_count - 40)))
        return {n: linhas_da_pagina(doc[n], dpi) for n in alvo}
    finally:
        doc.close()


def pesar(palavras, ref):
    """(verdade, peso relativo) de cada palavra que dá para pesar."""
    return [(forte, negrito.relativo(glifos, ref), len(glifos))
            for forte, glifos in palavras]


def amostras_de(palavras):
    amostras = collections.defaultdict(list)
    for _forte, glifos in palavras:
        for ch, e in glifos:
            amostras[ch].append(e)
    return amostras


def acerto(pesados, normal, limiar=negrito.LIMIAR, minimo=1):
    """(acerto, alarme falso) desta régua sobre estas palavras."""
    certos, falsos = [], []
    for forte, peso, glifos in pesados:
        if peso is None:
            continue
        marcada = glifos >= minimo and negrito.e_negrito(peso, normal, limiar)
        (certos if forte else falsos).append(marcada)
    return (float(np.mean(certos)) if certos else 0.0,
            float(np.mean(falsos)) if falsos else 0.0,
            len(falsos), len(certos))


def tabela_das_reguas(por_pagina):
    """
    A tabela que escolheu a referência: página × livro, mediana × quantil.

    Mede no regime de produção — palavra curta demais não decide —, que é o que
    torna as quatro linhas comparáveis entre si e com o resto da fase.
    """
    do_livro = palavras_de([l for desta in por_pagina.values() for l in desta])
    print("\n## A referência de cada caractere\n")
    print("| referência | acerta | falso |")
    print("|---|---:|---:|")
    for rotulo, ref_de, todo_o_livro in (
            ("mediana da página", referencia_pela_mediana, False),
            ("quantil da página", negrito.referencia, False),
            ("mediana do livro", referencia_pela_mediana, True),
            ("**quantil do livro** (hoje)", negrito.referencia, True)):
        if todo_o_livro:
            pesados = pesar(do_livro, ref_de(amostras_de(do_livro)))
        else:
            pesados = []
            for linhas in por_pagina.values():
                desta = palavras_de(linhas)
                pesados.extend(pesar(desta, ref_de(amostras_de(desta))))
        pega, falso, _n, _b = acerto(pesados, normal_de(pesados),
                                     minimo=negrito.MINIMO_DE_GLIFOS)
        print(f"| {rotulo} | {pega:.1%} | {falso:.2%} |")


def normal_de(pesados):
    """O peso redondo destas palavras — só as que decidem por si o compõem."""
    return negrito.escala([p for _f, p, n in pesados if p is not None
                           and n >= negrito.MINIMO_DE_GLIFOS])


def tabela_do_limiar(pesados, normal):
    print("\n## O limiar\n")
    print("| limiar | acerta | falso |")
    print("|---|---:|---:|")
    # O de produção entra na varredura, e não se espera que a grade caia nele.
    grade = sorted(set(np.round(np.arange(1.00, 1.31, 0.02), 2))
                   | {negrito.LIMIAR})
    for limiar in grade:
        pega, falso, _n, _b = acerto(pesados, normal, limiar=limiar,
                                     minimo=negrito.MINIMO_DE_GLIFOS)
        marca = " ← hoje" if limiar == negrito.LIMIAR else ""
        print(f"| {limiar:.2f}{marca} | {pega:.1%} | {falso:.2%} |")

    firmes = [(f, p) for f, p, n in pesados
              if p is not None and n >= negrito.MINIMO_DE_GLIFOS]
    redondas = np.array([p / normal for f, p in firmes if not f])
    fortes = np.array([p / normal for f, p in firmes if f])
    print("\nAs duas populações, em pesos redondos:\n")
    print(f"    redonda   p90={np.percentile(redondas, 90):.3f} "
          f"p99={np.percentile(redondas, 99):.3f} "
          f"p99,9={np.percentile(redondas, 99.9):.3f}")
    print(f"    negrito   p01={np.percentile(fortes, 1):.3f} "
          f"p05={np.percentile(fortes, 5):.3f} "
          f"mediana={np.median(fortes):.3f}")


def tabela_das_palavras(pesados, normal):
    print("\n## Por tamanho de palavra, antes da regra da vizinhança\n")
    print("| glifos medidos | palavras | acerta | falso |")
    print("|---|---:|---:|---:|")
    for rotulo, cabe in (("1", lambda n: n == 1), ("2", lambda n: n == 2),
                         ("3 ou mais", lambda n: n >= 3),
                         ("**todas**", lambda n: True)):
        sub = [(f, p, n) for f, p, n in pesados if cabe(n)]
        pega, falso, redondas, fortes = acerto(sub, normal)
        print(f"| {rotulo} | {redondas + fortes} | {pega:.1%} | {falso:.2%} |")


def tabela_dos_glifos(palavras, ref, normal):
    """
    Glifo a glifo — a tabela que decidiu que a unidade é a palavra.

    A régua aplicada a um caractere sozinho, e a quebra por classe: é aqui que
    se vê que a pontuação não tem medida que preste, e que a mediana da palavra
    é o que passa por cima disso.
    """
    print("\n## Glifo a glifo, e por classe de caractere\n")
    print("| classe | glifos em negrito | pegos |")
    print("|---|---:|---:|")
    classes = {"dígito": str.isdigit, "letra": str.isalpha}
    contas = collections.defaultdict(lambda: [0, 0])
    certos, falsos = [], []
    for forte, glifos in palavras:
        for ch, e in glifos:
            peso = negrito.relativo([(ch, e)], ref)
            if peso is None:
                continue
            marcado = negrito.e_negrito(peso, normal)
            (certos if forte else falsos).append(marcado)
            if not forte:
                continue
            nome = next((k for k, cabe in classes.items() if cabe(ch)), "sinal")
            contas[nome][0] += 1
            contas[nome][1] += marcado
    for nome in ("dígito", "letra", "sinal"):
        total, pegos = contas[nome]
        if total:
            print(f"| {nome} | {total} | {pegos / total:.1%} |")
    print(f"| **todos** | {len(certos)} | {np.mean(certos):.1%} | ")
    print(f"\nalarme falso glifo a glifo: {np.mean(falsos):.2%}")


def tabela_da_producao(por_pagina):
    """
    A régua de produção inteira, ponta a ponta: `negrito.marcar` no gabarito.

    Cada linha do PDF vira um `Paragrafo` com as espessuras medidas, e o que se
    compara é o que o livro exportado traria contra o que o PDF declara. É a
    única tabela que inclui a regra da vizinhança — as outras medem peças.
    """
    from core.livro import PaginaExtraida, Paragrafo

    paginas, verdades = [], []
    for numero, linhas in sorted(por_pagina.items()):
        blocos = []
        for texto, pesos, verdade in linhas:
            blocos.append(Paragrafo(texto, pesos=negrito.vetor(pesos)))
            verdades.append(verdade)
        paginas.append(PaginaExtraida(numero=numero, blocos=blocos))

    negrito.marcar(paginas)

    certos, falsos = [], []
    i = 0
    for pagina in paginas:
        for bloco in pagina.blocos:
            marcado = [False] * len(bloco.texto)
            for inicio, fim in bloco.negrito:
                for k in range(inicio, fim):
                    marcado[k] = True
            verdade = verdades[i]
            i += 1
            for inicio, fim in negrito._palavras(bloco.texto):
                forte = np.mean(verdade[inicio:fim]) > 0.5
                saiu = any(marcado[inicio:fim])
                (certos if forte else falsos).append(saiu)
    print("\n## A régua de produção, ponta a ponta\n")
    print("| palavras | acerta | falso |")
    print("|---|---:|---:|")
    print(f"| {len(certos) + len(falsos)} | {np.mean(certos):.1%} | "
          f"{np.mean(falsos):.2%} |")


def tabela_das_fontes(corpos=CORPOS):
    """A razão negrito ÷ redondo, caractere a caractere, por família."""
    import string

    from PIL import Image, ImageDraw, ImageFont

    alfabeto = string.ascii_letters + string.digits

    def espessuras(arquivo, corpo):
        try:
            fonte = ImageFont.truetype(os.path.join(
                os.environ.get("WINDIR", "C:/Windows"), "Fonts", arquivo), corpo)
        except OSError:
            return None
        saida = {}
        for ch in alfabeto:
            img = Image.new("L", (corpo * 3, corpo * 3), 255)
            ImageDraw.Draw(img).text((corpo, corpo // 2), ch, font=fonte, fill=0)
            arr = np.array(img)
            ys, xs = np.nonzero(255 - arr)
            if len(ys) < negrito.MINIMO_DE_TINTA:
                continue
            e = negrito.espessura(arr[ys.min():ys.max() + 1,
                                      xs.min():xs.max() + 1])
            if e is not None:
                saida[ch] = e
        return saida

    print("\n## A razão negrito ÷ redondo, por família\n")
    print("| família | " + " | ".join(f"{c} px" for c in corpos) + " |")
    print("|---|" + "---:|" * len(corpos))
    for nome, redondo, forte in FAMILIAS:
        celulas = []
        for corpo in corpos:
            r, f = espessuras(redondo, corpo), espessuras(forte, corpo)
            if not r or not f:
                celulas.append("—")
                continue
            razoes = [f[c] / r[c] for c in r if c in f and r[c] > 0]
            celulas.append(f"{np.median(razoes):.2f}" if razoes else "—")
        print(f"| {nome} | " + " | ".join(celulas) + " |")
    print(f"\nO limiar de produção é {negrito.LIMIAR:.2f}. A folga some no corpo "
          "miúdo, e é lá que esta régua erra.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paginas", type=int, default=PAGINAS,
                    help="quantas páginas amostrar do livro com gabarito")
    ap.add_argument("--limiar", action="store_true",
                    help="varredura fina do limiar")
    ap.add_argument("--glifo", action="store_true",
                    help="a régua aplicada a um caractere sozinho")
    ap.add_argument("--palavra", action="store_true",
                    help="acerto por número de glifos da palavra")
    ap.add_argument("--fontes", action="store_true",
                    help="a razão entre os dois pesos, família a família")
    args = ap.parse_args()

    if args.fontes:
        tabela_das_fontes()
        return

    raiz = os.path.dirname(os.path.abspath(__file__))
    caminho = caminho_do_livro(raiz)
    if caminho is None:
        print(f"'{LIVRO}' não está em PDF/ — é o único livro desta pasta cuja "
              "camada de texto nomeia as fontes, e sem ele não há gabarito.")
        print("O `--fontes` não depende dele e continua valendo.")
        return

    por_pagina = colher(caminho, args.paginas)
    palavras = palavras_de([l for desta in por_pagina.values() for l in desta])

    pesados = pesar(palavras, negrito.referencia(amostras_de(palavras)))
    normal = normal_de(pesados)
    fortes = sum(1 for f, _p, _n in pesados if f)
    print(f"# {os.path.basename(caminho)[:40]} — {len(por_pagina)} páginas, "
          f"{len(palavras)} palavras, {fortes / max(1, len(palavras)):.1%} "
          f"em negrito\n")
    print(f"peso redondo (escala) = {normal:.4f}")

    if args.limiar:
        tabela_do_limiar(pesados, normal)
    elif args.glifo:
        tabela_dos_glifos(palavras, negrito.referencia(amostras_de(palavras)),
                          normal)
    elif args.palavra:
        tabela_das_palavras(pesados, normal)
    else:
        tabela_das_reguas(por_pagina)
        tabela_das_palavras(pesados, normal)
        tabela_da_producao(por_pagina)


if __name__ == "__main__":
    sys.exit(main())
