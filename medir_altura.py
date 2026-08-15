"""
A altura relativa à linha separa os pares que a F14 nomeou — e mesmo assim não
melhora a leitura. Este script produz as duas tabelas da F19.

    python medir_altura.py             # separação (d') e a varredura, na rede
    python medir_altura.py --knn       # a mesma varredura, no k-NN (F37)
    python medir_altura.py --separacao # só a separação, não carrega classificador

**A separação não precisa de classificador**; a varredura precisa, porque a
pergunta dela é se desempatar as candidatas de alguém melhora o resultado — e
esse alguém pode ser a rede (F19) ou o k-NN (F37), que são âncoras de força
diferente e por isso têm orçamentos de erro diferentes.

A verdade são os `.box` rotulados: eles têm o caractere **e** a coordenada real.
A base de treino não serve para isto — são 32x32 já normalizados, e a altura foi
descartada na gravação. É a mesma razão pela qual a entrada não pôde ir para
dentro da rede (ver `core/altura_relativa.py`).
"""

import argparse
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from PIL import Image

from core import altura_relativa as ar
from core import leitura_de_linha as ldl
from core import vertical
from core.avaliacao_pagina import normalizar
from core.calibracao_de_pagina import MIN_ROTULADOS, paginas_rotuladas
from core.formato_box import ler as ler_box
from core.services.box_service import BoxService

#: Pares que a F14 lista, mais os homóglifos que ela mediu.
PARES = [("c", "C"), ("o", "O"), ("o", "0"), ("s", "S"), ("x", "X"),
         ("p", "P"), ("w", "W"), ("v", "V"), ("z", "Z"), ("u", "U"),
         ("l", "1"), ("i", "1"), ("g", "9"), ("y", "Y"), ("k", "K")]

MIN_AMOSTRAS = 8


def _console_em_utf8():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def linhas_rotuladas(img_path, box_path, minimo=3):
    """
    `(imagem da página, [linhas com pelo menos `minimo` boxes])`.

    Devolve `(pagina, [])` para a página que não passa em `MIN_ROTULADOS` — o
    corte é o mesmo de `medir_paginas.py` e de `medir_cadeia.py`, e a F41 o
    trouxe para cá. Sem ele este arquivo media um conjunto de páginas só dele.
    """
    pagina = np.array(Image.open(img_path).convert("L"))
    boxes = [b for b in ler_box(box_path, pagina.shape[0])
             if b.char and b.x2 > b.x1 and b.y2 > b.y1]
    if len(boxes) < MIN_ROTULADOS:
        return pagina, []
    boxes = BoxService.sort_boxes_reading_order(boxes)
    return pagina, [L for L in ldl.quebrar_em_linhas(boxes) if len(L) >= minimo]


def _dprime(a, b):
    """Distância entre as médias em desvios-padrão combinados."""
    x, y = np.array(a), np.array(b)
    s = np.sqrt((x.var() + y.var()) / 2) or 1e-9
    return abs(x.mean() - y.mean()) / s


def medir_separacao():
    """A tabela de d': o topo separa, a altura não."""
    por_char = defaultdict(lambda: ([], [], []))
    for img_path, box_path in paginas_rotuladas():
        _pag, linhas = linhas_rotuladas(img_path, box_path)
        for linha in linhas:
            topo = min(b.y1 for b in linha)
            h = max(b.y2 for b in linha) - topo
            if h <= 0:
                continue
            for b in linha:
                t, ba, al = por_char[b.char]
                t.append((b.y1 - topo) / h)
                ba.append((b.y2 - topo) / h)
                al.append((b.y2 - b.y1) / h)

    print(f"{'par':>7s} {'n':>10s} {'d(topo)':>8s} {'d(base)':>8s} {'d(alt)':>8s}")
    fortes = 0
    for baixa, alta in PARES:
        a, b = por_char.get(baixa), por_char.get(alta)
        if not a or not b or len(a[0]) < MIN_AMOSTRAS or len(b[0]) < MIN_AMOSTRAS:
            n_a = len(a[0]) if a else 0
            n_b = len(b[0]) if b else 0
            print(f"{baixa}/{alta:>5s} {n_a:5d}/{n_b:<4d}   (poucas amostras)")
            continue
        ds = [_dprime(a[i], b[i]) for i in range(3)]
        marca = "  <<<" if max(ds) >= 2.0 else ""
        fortes += max(ds) >= 2.0
        print(f"{baixa}/{alta:>5s} {len(a[0]):5d}/{len(b[0]):<4d} "
              f"{ds[0]:8.2f} {ds[1]:8.2f} {ds[2]:8.2f}{marca}")
    print(f"\npares com separação forte (d' >= 2,0): {fortes}")
    print("O topo ganha em toda linha: todo glifo se apoia na mesma base, então")
    print("a base não distingue nada; o que muda é até onde o glifo sobe.")


def _amostras_com_topk(topk_de):
    """
    `([(verdade, y1, ângulo, top-k, geometria da linha)], páginas usadas)`.

    A contagem de páginas sai junto porque **duas rodadas só são comparáveis se
    o conjunto for o mesmo** — foi a lição que a F24 tirou de uma base que
    cresceu no meio da medição, e que a F41 teve de aprender de novo: este
    arquivo montava a sua própria lista de páginas rotuladas, e nada na saída
    dizia que era outra.
    """
    saida, usadas = [], 0
    for img_path, box_path in paginas_rotuladas():
        pagina, linhas = linhas_rotuladas(img_path, box_path)
        usadas += bool(linhas)
        for linha in linhas:
            geo = [(b.y1, b.y2) for b in linha]
            for b in linha:
                recorte = vertical.recorte_de_pe(pagina, b)
                if recorte.size == 0:
                    continue
                topk = topk_de(recorte)
                if topk:
                    saida.append((normalizar(b.char), b.y1,
                                  getattr(b, "angulo", 0), topk, geo))
        print(f"  {os.path.basename(img_path)}"
              f"{'' if linhas else '   (poucos rótulos, fora)'}", flush=True)
    return saida, usadas


def _referencia_faixa(geo):
    topo = min(y1 for y1, _ in geo)
    return topo, max(y2 for _, y2 in geo) - topo


def _referencia_mediana(geo):
    """Mediana de y1 (linha de x) e de y2 (linha de base) — menos ruidoso."""
    ys1 = sorted(y1 for y1, _ in geo)
    ys2 = sorted(y2 for _, y2 in geo)
    x_topo = ys1[len(ys1) // 2]
    return x_topo, max(ys2[len(ys2) // 2] - x_topo, 1)


#: As margens de cada âncora, e elas **não** estão na mesma escala.
#:
#: A margem é o mínimo que a substituta precisa valer para ser considerada. Na
#: rede é probabilidade de softmax, e ela é peaked — a F14 mediu 0,9994 num
#: acerto, então a segunda candidata vem com ~0,0005 e qualquer margem "redonda"
#: fecha o filtro. Foi o erro de percurso da F19: a primeira varredura usou 0,02,
#: o desambiguador tocou **1 box em 2.257**, e "não mudou nada" passou por "não
#: tem sinal" quando era "o filtro estava fechado".
#:
#: No k-NN a escala é `1 - d/2000`, a mesma que roteia a cadeia, e ali os números
#: redondos querem dizer alguma coisa: 0,30 é o `LEARNER_THRESHOLD_HIBRIDO`, o
#: ponto em que a cadeia já confia no k-NN para responder sozinho.
MARGENS = {"rede": (1e-6, 1e-4, 1e-3),
           "knn": (0.0, 0.30, 0.50, 0.70)}


def _ancora(caminho):
    """`(nome, topk(recorte) -> [(char, peso)])` do classificador pedido."""
    from core.services.learning_service import LearningService

    servico = LearningService()
    if caminho == "knn":
        learner = servico._get_learner()
        if learner.total == 0:
            print("A base de referência está vazia.")
            return None
        print(f"k-NN com {learner.total} referências")
        return "k-NN (argmin)", lambda crop: learner.candidatas(crop, n=5)

    if not servico.load_predictor():
        print("O modelo neural não carregou; a varredura precisa dele.")
        return None
    return "rede (argmax)", lambda crop: servico._predictor.predict_topk(crop, k=5)


def medir_varredura(caminho="rede"):
    """A varredura: desempatar as candidatas com a geometria melhora?"""
    ancora = _ancora(caminho)
    if ancora is None:
        return
    rotulo, topk_de = ancora
    amostras, paginas = _amostras_com_topk(topk_de)
    if not amostras:
        print("nenhuma amostra")
        return

    n = len(amostras)
    base = sum(1 for v, _y, _a, tk, _g in amostras if normalizar(tk[0][0]) == v)
    print(f"\n=== {n} caracteres em {paginas} página(s), âncora {rotulo} ===")
    print(f"como está hoje: {100 * base / n:.2f}%\n")

    referencias = (("faixa", _referencia_faixa, (0.17, 0.19, 0.21)),
                   ("mediana", _referencia_mediana, (-0.5, -0.3, -0.15, 0.0)))

    # **A coluna `tocou` não é decoração.** Sem ela, "não melhorou" não distingue
    # "não há sinal" de "o filtro nunca disparou", que é o erro que a F19
    # registrou. Uma linha com `tocou = 0` não mediu nada.
    print(f"{'margem':>8} {'melhor':>8} {'delta':>7} {'tocou':>7} "
          f"{'consertos':>10} {'quebras':>8}  config")
    melhor_geral = (base, None)
    quantas = 0
    for margem in MARGENS[caminho]:
        linha_melhor = None
        for nome, referencia, cortes in referencias:
            for corte in cortes:
                for incerteza in (0.02, 0.05, 0.10):
                    quantas += 1
                    r = _avaliar(amostras, referencia, corte, incerteza, margem)
                    if linha_melhor is None or r[0] > linha_melhor[0][0]:
                        linha_melhor = (r, (nome, corte, incerteza))
                    if r[0] > melhor_geral[0]:
                        melhor_geral = (r[0], (nome, corte, incerteza, margem))
        (ok, tocou, consertos, quebras), cfg = linha_melhor
        print(f"{margem:>8} {100.0 * ok / n:>7.2f}% {100.0 * (ok - base) / n:>+6.2f} "
              f"{tocou:>7} {consertos:>10} {quebras:>8}  {cfg}")

    print(f"\ncombinações varridas: {quantas}")
    if melhor_geral[1] is None:
        print("NENHUMA supera a âncora. Ver `core/altura_relativa.py`: o sinal")
        print("existe, e o que decide é a aritmética da precisão — os falsos")
        print("positivos sobre os acertos superam os consertos.")
    else:
        print(f"melhor: {100 * melhor_geral[0] / n:.2f}% "
              f"({100 * (melhor_geral[0] - base) / n:+.2f} pontos), "
              f"config {melhor_geral[1]}")


def _avaliar(amostras, referencia, corte, incerteza, margem):
    """`(acertos, tocou, consertos, quebras)` desta combinação."""
    ok = tocou = consertos = quebras = 0
    for verdade, y1, angulo, topk, geo in amostras:
        ref, h = referencia(geo)
        t = (y1 - ref) / h if h > 0 else None
        medida = (None if (angulo or t is None or abs(t - corte) < incerteza)
                  else ("x" if t > corte else "alto"))
        troca = ar.desambiguar(topk, medida, margem)
        antes = normalizar(topk[0][0]) == verdade
        depois = normalizar(troca[0]) == verdade if troca else antes
        if troca:
            tocou += 1
            consertos += depois and not antes
            quebras += antes and not depois
        ok += depois
    return ok, tocou, consertos, quebras


def main():
    _console_em_utf8()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--separacao", action="store_true",
                   help="só a tabela de d'; não carrega classificador nenhum")
    p.add_argument("--knn", action="store_true",
                   help="desempata as candidatas do k-NN em vez das da rede "
                        "(F37); a separação é a mesma, ela não depende de "
                        "quem classifica")
    args = p.parse_args()

    medir_separacao()
    if not args.separacao:
        print()
        medir_varredura("knn" if args.knn else "rede")
    return 0


if __name__ == "__main__":
    sys.exit(main())
