"""
De que são feitos os 231 caracteres colados na horizontal (F13).

A F12 fechou dizendo qual é o próximo alvo e quanto ele vale: nas 10 páginas
rotuladas faltam 231 caracteres porque o vizinho os engoliu — o dobro do que
aquela fase atacou. Este script responde a pergunta que vem antes de qualquer
corte: **de que eles são feitos?**

    python medir_colados.py                # com o modelo, pipeline de hoje
    python medir_colados.py --sem-modelo   # sem árbitro; mede a mesma coisa

A conta que interessa é a divisão entre os que o separador da F1.5b **olha** e
recusa e os que ele nem chega a olhar. O separador só considera box mais largo
que `fator_largo` (1,6) vezes a largura de referência da linha; abaixo disso o
box nem vira candidato, e nenhum ajuste de árbitro o alcança. São dois problemas
com o mesmo sintoma, e misturá-los faria varrer a margem do árbitro atrás de um
ganho que a maioria dos casos não pode dar.

Nada aqui altera arquivo nenhum: só lê as páginas rotuladas e conta.
"""

import argparse
import os
import sys
from collections import Counter

import numpy as np
from PIL import Image

from core.avaliacao_pagina import carregar_box, comparar, normalizar
from core.services.box_service import BoxService
from medir_paginas import MIN_ROTULADOS, paginas_rotuladas, segmentar


#: O mesmo de `dividir_glifos_colados`. Repetido aqui de propósito: se ele mudar
#: lá, esta medição tem de ser refeita, e um import silencioso esconderia isso.
FATOR_LARGO = 1.6


def _centro(b):
    return (b.x1 + b.x2) / 2, (b.y1 + b.y2) / 2


def _contem_centro(caixa, alvo):
    cx, cy = _centro(alvo)
    return caixa.x1 <= cx <= caixa.x2 and caixa.y1 <= cy <= caixa.y2


def _sobrepoe(a, b):
    return a.x1 < b.x2 and b.x1 < a.x2 and a.y1 < b.y2 and b.y1 < a.y2


def analisar_pagina(pais, filhos, rotulados):
    """
    Por que cada rótulo perdido se perdeu.

    `comparar` empareilha por centro do gerado dentro do rotulado; o que sobra
    são os perdidos. Para cada um a pergunta é qual box gerado o cobre:

      colado      um box cobre o centro dele **e** o de outro rótulo — o
                  caractere existe na página e divide caixa com o vizinho
      desalinhado um box o toca, mas nenhum centro cai dentro do outro
      sem box     nenhum box gerado encosta nele: sumiu na binarização
    """
    pares = comparar(filhos, rotulados).pares
    casados = {j for _, j in pares}

    referencia = BoxService._largura_de_referencia(pais)
    saida = {"colado": [], "desalinhado": [], "sem_box": []}

    for j, r in enumerate(rotulados):
        if j in casados:
            continue

        dono = next((f for f in filhos if _contem_centro(f, r)), None)
        if dono is None:
            vizinho = any(_sobrepoe(f, r) for f in filhos)
            saida["desalinhado" if vizinho else "sem_box"].append(r)
            continue

        # Quantos rótulos este box cobre? Dois ou mais = colagem de verdade.
        quantos = sum(1 for outro in rotulados if _contem_centro(dono, outro))
        if quantos < 2:
            saida["desalinhado"].append(r)
            continue

        # O separador da F1.5b decide a candidatura no PAI, antes de cortar.
        pai = next((p for p in pais if _contem_centro(p, r)), None)
        largura_ref = referencia.get(id(pai)) if pai is not None else None
        if pai is None or not largura_ref:
            largo, razao = False, 0.0
        else:
            razao = (pai.x2 - pai.x1) / largura_ref
            largo = razao > FATOR_LARGO

        companhia = sorted(
            (normalizar(o.char) for o in rotulados
             if _contem_centro(dono, o) and o is not r))
        saida["colado"].append({
            "char": normalizar(r.char), "com": companhia,
            "razao": razao, "candidato": largo, "n_no_box": quantos,
        })

    return saida


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-modelo", action="store_true",
                    help="não carrega a rede; o separador roda sem árbitro")
    args = ap.parse_args()

    predizer = None
    if not args.sem_modelo:
        from core.services.learning_service import LearningService
        svc = LearningService()
        if svc.load_predictor():
            predizer = svc._predictor.predict
        else:
            print("sem modelo treinado — rodando sem árbitro\n")

    paginas = paginas_rotuladas()
    if not paginas:
        print("nenhuma página rotulada encontrada")
        return 1

    modo = "arbitrado" if predizer else "local"
    total = {"colado": [], "desalinhado": [], "sem_box": []}
    rotulados_total = 0

    for imagem, caminho_box in paginas:
        img = Image.open(imagem).convert("L")
        rotulados = carregar_box(caminho_box, img.size[1])
        if len(rotulados) < MIN_ROTULADOS:
            continue
        arr = np.array(img)

        pais, filhos = segmentar(img, modo, arbitro=predizer)
        if predizer:
            for b in filhos:
                b.char, b.confidence = predizer(arr[b.y1:b.y2, b.x1:b.x2])

        parcial = analisar_pagina(pais, filhos, rotulados)
        rotulados_total += len(rotulados)
        for k in total:
            total[k] += parcial[k]

        print(f"  {os.path.basename(imagem)[-28:]:<30} "
              f"{len(rotulados):>5} rotulados   "
              f"colados {len(parcial['colado']):>3}   "
              f"desalinhados {len(parcial['desalinhado']):>3}   "
              f"sem box {len(parcial['sem_box']):>3}")

    colados = total["colado"]
    print(f"\n=========== {rotulados_total} caracteres rotulados ===========")
    print(f"  colados com o vizinho .... {len(colados)}")
    print(f"  box desalinhado .......... {len(total['desalinhado'])}")
    print(f"  sem box nenhum ........... {len(total['sem_box'])}")

    if not colados:
        return 0

    candidatos = [c for c in colados if c["candidato"]]
    print(f"\nO separador da F1.5b (fator_largo = {FATOR_LARGO}) olha quantos?")
    print(f"  vira candidato e é recusado ... {len(candidatos)}")
    print(f"  estreito demais para olhar .... {len(colados) - len(candidatos)}")

    print("\nLargura do box pai, em larguras de referência da linha:")
    faixas = [(0, 1.0), (1.0, 1.2), (1.2, 1.4), (1.4, 1.6),
              (1.6, 2.0), (2.0, 3.0), (3.0, 99)]
    for lo, hi in faixas:
        n = sum(1 for c in colados if lo <= c["razao"] < hi)
        marca = "  <- candidato" if lo >= FATOR_LARGO else ""
        print(f"  {lo:>4.1f} a {hi:>4.1f}   {n:>4}   "
              f"{'#' * min(60, n // 2)}{marca}")

    print("\nQuantos rótulos cabem no mesmo box:")
    for n, q in sorted(Counter(c["n_no_box"] for c in colados).items()):
        print(f"  {n} rótulos   {q:>4} caracteres perdidos")

    print("\nOs pares mais frequentes (caractere perdido + companhia):")
    pares = Counter(f"{c['char']}+{''.join(c['com'])}" for c in colados)
    for par, q in pares.most_common(20):
        print(f"  {par:<12} {q:>4}")

    print("\nSó dos estreitos demais (os que nenhum ajuste de árbitro alcança):")
    estreitos = Counter(f"{c['char']}+{''.join(c['com'])}"
                        for c in colados if not c["candidato"])
    for par, q in estreitos.most_common(15):
        print(f"  {par:<12} {q:>4}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
