"""
A altura relativa à linha separa os pares que a F14 nomeou — e mesmo assim não
melhora a leitura. Este script produz as duas tabelas da F19.

    python medir_altura.py             # separação (d') e a varredura
    python medir_altura.py --separacao # só a separação, não carrega a rede

**A separação não precisa da rede**; a varredura precisa, porque a pergunta
dela é se desempatar as candidatas do modelo melhora o resultado.

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
from core.formato_box import ler as ler_box
from core.services.box_service import BoxService

#: Pares que a F14 lista, mais os homóglifos que ela mediu.
PARES = [("c", "C"), ("o", "O"), ("o", "0"), ("s", "S"), ("x", "X"),
         ("p", "P"), ("w", "W"), ("v", "V"), ("z", "Z"), ("u", "U"),
         ("l", "1"), ("i", "1"), ("g", "9"), ("y", "Y"), ("k", "K")]

MIN_AMOSTRAS = 8
PASTAS = ("Box", "ilovepdf_pages-to-jpg")


def _console_em_utf8():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def paginas_rotuladas():
    for pasta in PASTAS:
        if not os.path.isdir(pasta):
            continue
        for f in sorted(os.listdir(pasta)):
            if not f.endswith(".box"):
                continue
            base = os.path.splitext(f)[0]
            for ext in (".png", ".jpg", ".jpeg"):
                img = os.path.join(pasta, base + ext)
                if os.path.exists(img):
                    yield img, os.path.join(pasta, f)
                    break


def linhas_rotuladas(img_path, box_path, minimo=3):
    """[(imagem da página, [boxes da linha])] das linhas com pelo menos `minimo`."""
    pagina = np.array(Image.open(img_path).convert("L"))
    boxes = [b for b in ler_box(box_path, pagina.shape[0])
             if b.char and b.x2 > b.x1 and b.y2 > b.y1]
    if not boxes:
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


def _amostras_com_topk(predictor):
    """[(verdade, y1, ângulo, top-k, geometria da linha)] de todas as páginas."""
    saida = []
    for img_path, box_path in paginas_rotuladas():
        pagina, linhas = linhas_rotuladas(img_path, box_path)
        for linha in linhas:
            geo = [(b.y1, b.y2) for b in linha]
            for b in linha:
                recorte = vertical.recorte_de_pe(pagina, b)
                if recorte.size == 0:
                    continue
                topk = predictor.predict_topk(recorte, k=5)
                if topk:
                    saida.append((normalizar(b.char), b.y1,
                                  getattr(b, "angulo", 0), topk, geo))
        print(f"  {os.path.basename(img_path)}", flush=True)
    return saida


def _referencia_faixa(geo):
    topo = min(y1 for y1, _ in geo)
    return topo, max(y2 for _, y2 in geo) - topo


def _referencia_mediana(geo):
    """Mediana de y1 (linha de x) e de y2 (linha de base) — menos ruidoso."""
    ys1 = sorted(y1 for y1, _ in geo)
    ys2 = sorted(y2 for _, y2 in geo)
    x_topo = ys1[len(ys1) // 2]
    return x_topo, max(ys2[len(ys2) // 2] - x_topo, 1)


def medir_varredura():
    """A varredura que fecha a questão: desempatar não melhora."""
    from core.services.learning_service import LearningService

    servico = LearningService()
    if not servico.load_predictor():
        print("O modelo neural não carregou; a varredura precisa dele.")
        return
    amostras = _amostras_com_topk(servico._predictor)

    n = len(amostras)
    base = sum(1 for v, _y, _a, tk, _g in amostras if normalizar(tk[0][0]) == v)
    print(f"\n=== {n} caracteres ===")
    print(f"rede como está hoje (argmax): {100 * base / n:.2f}%\n")

    referencias = (("faixa", _referencia_faixa, (0.17, 0.19, 0.21)),
                   ("mediana", _referencia_mediana, (-0.5, -0.3, -0.15, 0.0)))
    melhor, quantas = (base, None), 0
    for nome, referencia, cortes in referencias:
        for corte in cortes:
            for incerteza in (0.02, 0.05, 0.10):
                for margem in (1e-6, 1e-4, 1e-3):
                    quantas += 1
                    ok = _acerto(amostras, referencia, corte, incerteza, margem)
                    if ok > melhor[0]:
                        melhor = (ok, (nome, corte, incerteza, margem))

    print(f"combinações varridas: {quantas}")
    print(f"melhor: {100 * melhor[0] / n:.2f}% "
          f"({100 * (melhor[0] - base) / n:+.2f} pontos)")
    if melhor[1] is None:
        print("\nNENHUMA supera o argmax. Ver `core/altura_relativa.py`: o sinal")
        print("existe, mas uma base a 97% não tolera um canal lateral a 97% —")
        print("os falsos positivos sobre os acertos superam os consertos.")
    else:
        print(f"  config: {melhor[1]}")


def _acerto(amostras, referencia, corte, incerteza, margem):
    ok = 0
    for verdade, y1, angulo, topk, geo in amostras:
        ref, h = referencia(geo)
        t = (y1 - ref) / h if h > 0 else None
        medida = (None if (angulo or t is None or abs(t - corte) < incerteza)
                  else ("x" if t > corte else "alto"))
        troca = ar.desambiguar(topk, medida, margem)
        if normalizar(troca[0] if troca else topk[0][0]) == verdade:
            ok += 1
    return ok


def main():
    _console_em_utf8()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--separacao", action="store_true",
                   help="só a tabela de d'; não carrega a rede")
    args = p.parse_args()

    medir_separacao()
    if not args.separacao:
        print()
        medir_varredura()
    return 0


if __name__ == "__main__":
    sys.exit(main())
