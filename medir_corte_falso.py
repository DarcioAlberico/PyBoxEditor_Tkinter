"""
Quanto custa um corte falso na revisão (F31).

    python medir_corte_falso.py                      # as margens 0,00 e 0,30
    python medir_corte_falso.py --margens 0.0 0.15 0.30

A F30 terminou dizendo que o F1 da página não decide mais a margem do árbitro:
ele é plano de 0,05 a 0,30, e o que sustenta o 0,30 é a **assimetria entre os
três modos de errar**, que o F1 não sabe expressar. Ele conta um box espúrio e
um glifo partido como o mesmo desvio de 1; para quem revisa, não são.

A moeda desta medição é outra: **erro que chega ao texto final sem ninguém
ver**. Um box a mais é caro se o revisor tem de achá-lo, e barato se ele salta.

## As duas redes que a página já tem

1. **`ui.confidence.precisa_revisao`** (F3.2) — box vazio ou de confiança baixa
   entra na fila. É a rede principal, e é cega para o erro confiante: a F14
   mediu que a confiança mediana de um erro é alta.
2. **O léxico** (F9) — palavra de prosa fora do dicionário acende, *independente
   da confiança*. Existe exatamente para o que a primeira não vê, e é a rede
   que um corte falso deveria acionar: `m` partido vira `rn`, e `rn` dentro de
   uma palavra costuma quebrá-la.

Um corte falso que escapa das duas é o caso caro — e é o número que a F30 disse
que faltava.

## O que este arquivo não mede

Não mede quanto **tempo** custa consertar um box, que é a outra metade da
palavra "custo". Isso é medida com gente, não com script. Aqui o custo é
contado em erros invisíveis, que é o que decide entre duas margens sem precisar
cronometrar ninguém.
"""

import argparse
import os
import sys
from collections import Counter

import numpy as np
from PIL import Image

from core import lexico
from core.avaliacao_pagina import (carregar_box, comparar, normalizar,
                                   pais_por_categoria)
from core.services.learning_service import LearningService
from medir_paginas import MIN_ROTULADOS, paginas_rotuladas, segmentar
from ui import confidence as conf_ui


def _console_em_utf8():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


class _BoxFalso:
    """O mínimo que `ui.confidence` olha, para não copiar a regra da revisão."""

    __slots__ = ("char", "source", "confidence")

    def __init__(self, b):
        self.char = b.char
        self.source = "neural" if b.char else ""
        self.confidence = b.confidence


def filhos_de(pai, filhos):
    """
    Os pedaços em que `pai` foi cortado.

    Pelo centro dentro do pai, e não por igualdade de coordenada: o corte
    reparte a largura, então cada filho fica **dentro** do pai e nenhum coincide
    com ele.
    """
    return [b for b in filhos
            if pai.x1 <= (b.x1 + b.x2) / 2 <= pai.x2
            and pai.y1 <= (b.y1 + b.y2) / 2 <= pai.y2]


#: Os quatro destinos possíveis de um caractere rotulado, do melhor ao pior.
#:
#: `sem_box` não é "invisível": a falta deixa buraco no texto, e buraco se vê
#: lendo. `errado_invisivel` é o único que chega ao fim parecendo certo.
ESTADOS = ("certo", "errado_visivel", "errado_invisivel", "sem_box")


def estado_por_rotulo(img, caminho_box, predizer, margem, lex):
    """
    `{índice do rotulado: estado}` — o destino de cada caractere da verdade.

    É a metade do ganho que a F31 deixou aberta. Ela contou o custo de uma
    margem agressiva em erro invisível, e o ganho em "caractere certo" — duas
    moedas que não se somam. Aqui os dois lados são contados na mesma.

    O índice é o do rotulado, que **não muda com a margem** — é a mesma verdade
    lida do mesmo `.box`. É o que permite acompanhar o mesmo caractere de uma
    margem para a outra.
    """
    rotulados = carregar_box(caminho_box, img.size[1])
    if len(rotulados) < MIN_ROTULADOS:
        return None

    arr = np.array(img)
    _pais, filhos = segmentar(img, "arbitrado", arbitro=predizer, margem=margem)
    for b in filhos:
        b.char, b.confidence = predizer(arr[b.y1:b.y2, b.x1:b.x2])

    suspeitos = set()
    if not lex.vazio:
        for s in lexico.suspeitas_da_pagina(filhos, lex):
            suspeitos.update(s.indices)

    estado = {j: "sem_box" for j in range(len(rotulados))}
    for i, j in comparar(filhos, rotulados).pares:
        b = filhos[i]
        if normalizar(b.char) == normalizar(rotulados[j].char):
            estado[j] = "certo"
        elif conf_ui.precisa_revisao(_BoxFalso(b)) or i in suspeitos:
            estado[j] = "errado_visivel"
        else:
            estado[j] = "errado_invisivel"
    return estado


def medir_pagina(img, caminho_box, predizer, margem, lex):
    """As contas de uma página, para uma margem."""
    rotulados = carregar_box(caminho_box, img.size[1])
    if len(rotulados) < MIN_ROTULADOS:
        return None

    arr = np.array(img)
    pais, filhos = segmentar(img, "arbitrado", arbitro=predizer, margem=margem)
    for b in filhos:
        b.char, b.confidence = predizer(arr[b.y1:b.y2, b.x1:b.x2])

    categorias = pais_por_categoria(pais, filhos, rotulados)
    r = comparar(filhos, rotulados)
    verdade = {i: rotulados[j].char for i, j in r.pares}
    indice = {id(b): i for i, b in enumerate(filhos)}

    # As suspeitas do léxico são por índice de box na página inteira.
    suspeitos = set()
    if not lex.vazio:
        for s in lexico.suspeitas_da_pagina(filhos, lex):
            suspeitos.update(s.indices)

    conta = Counter()
    conta["cortes_falsos"] = len(categorias["cortes_falsos"])
    conta["espurios"] = r.espurios

    for pai in categorias["cortes_falsos"]:
        pedacos = filhos_de(pai, filhos)
        conta["pedacos_de_corte_falso"] += len(pedacos)
        for b in pedacos:
            i = indice[id(b)]
            errado = normalizar(b.char) != normalizar(verdade.get(i, "\x00"))
            if not errado:
                conta["pedaco_certo_por_sorte"] += 1
                continue
            na_fila = conf_ui.precisa_revisao(_BoxFalso(b))
            no_lexico = i in suspeitos
            conta["pedaco_errado"] += 1
            if na_fila:
                conta["pego_pela_confianca"] += 1
            elif no_lexico:
                conta["pego_so_pelo_lexico"] += 1
            else:
                conta["invisivel"] += 1

    # O mesmo para o box espúrio, que é o outro custo que a margem compra.
    pareados = {i for i, _j in r.pares}
    for i, b in enumerate(filhos):
        if i in pareados:
            continue
        if conf_ui.precisa_revisao(_BoxFalso(b)):
            conta["espurio_na_fila"] += 1
        elif i in suspeitos:
            conta["espurio_so_pelo_lexico"] += 1
        else:
            conta["espurio_invisivel"] += 1
    return conta


def main():
    _console_em_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--margens", type=float, nargs="*",
                    default=[0.0, 0.30],
                    help="margens do árbitro a comparar (F1.5b)")
    args = ap.parse_args()

    svc = LearningService()
    if not svc.load_predictor():
        print("sem modelo treinado:", svc.motivo_do_modelo())
        return 1
    predizer = svc._predictor.predict

    lex = lexico.carregar()
    if lex.vazio:
        print("AVISO: léxico vazio — a segunda rede não será medida.\n"
              "Rode `python importar_lexico.py` para tê-la.\n")

    paginas = paginas_rotuladas()
    if not paginas:
        print("nenhuma página rotulada encontrada")
        return 1

    totais, estados = {}, {}
    for margem in args.margens:
        print(f"\n=== margem {margem:.2f} ===", flush=True)
        soma, por_pagina = Counter(), {}
        for imagem, caminho_box in paginas:
            img = Image.open(imagem).convert("L")
            conta = medir_pagina(img, caminho_box, predizer, margem, lex)
            if conta is None:
                continue
            soma.update(conta)
            por_pagina[imagem] = estado_por_rotulo(img, caminho_box, predizer,
                                                   margem, lex)
            print(f"  {os.path.basename(imagem)[-28:]:<30}"
                  f"falsos {conta['cortes_falsos']:>3}   "
                  f"invisíveis {conta['invisivel']:>3}", flush=True)
        totais[margem] = soma
        estados[margem] = por_pagina

    print("\n\n=========== O CORTE FALSO ===========")
    print(f"{'margem':>8}{'cortes':>8}{'pedaços':>9}{'errados':>9}"
          f"{'na fila':>9}{'só léxico':>11}{'INVISÍVEIS':>12}")
    for margem, s in totais.items():
        print(f"{margem:>8.2f}{s['cortes_falsos']:>8}"
              f"{s['pedacos_de_corte_falso']:>9}{s['pedaco_errado']:>9}"
              f"{s['pego_pela_confianca']:>9}{s['pego_so_pelo_lexico']:>11}"
              f"{s['invisivel']:>12}")

    print("\n=========== O BOX ESPÚRIO ===========")
    print(f"{'margem':>8}{'espúrios':>10}{'na fila':>9}{'só léxico':>11}"
          f"{'INVISÍVEIS':>12}")
    for margem, s in totais.items():
        print(f"{margem:>8.2f}{s['espurios']:>10}{s['espurio_na_fila']:>9}"
              f"{s['espurio_so_pelo_lexico']:>11}"
              f"{s['espurio_invisivel']:>12}")

    if len(totais) == 2:
        a, b = list(totais)
        da = totais[b]["invisivel"] - totais[a]["invisivel"]
        de = totais[b]["espurio_invisivel"] - totais[a]["espurio_invisivel"]
        print(f"\nDe {a:.2f} para {b:.2f}: {da:+d} erro(s) invisível(is) de corte "
              f"falso, {de:+d} espúrio(s) invisível(is).")
        _tabela_de_transicao(estados[b], estados[a], b, a)
    return 0


def _tabela_de_transicao(de_estado, para_estado, de_margem, para_margem):
    """
    O que aconteceu com cada caractere rotulado ao trocar de margem.

    É a conta que fecha a F31: ela mediu o custo em erro invisível e o ganho em
    "caractere certo", que são moedas diferentes. Aqui os dois lados saem na
    mesma — o que se ganha é dito **de que estado veio**, e o que se perde, para
    qual foi.
    """
    troca = Counter()
    for imagem, antes in de_estado.items():
        depois = para_estado.get(imagem)
        if depois is None:
            continue
        for j, e_antes in antes.items():
            e_depois = depois.get(j)
            if e_depois is not None and e_antes != e_depois:
                troca[(e_antes, e_depois)] += 1

    print(f"\n=========== O QUE MUDA DE {de_margem:.2f} PARA "
          f"{para_margem:.2f} ===========")
    ganhos = [(a, n) for (a, d), n in troca.items() if d == "certo"]
    perdas = [(d, n) for (a, d), n in troca.items() if a == "certo"]

    print(f"\nGanhos — passaram a sair certos ({sum(n for _e, n in ganhos)}):")
    for estado in ESTADOS:
        n = sum(v for e, v in ganhos if e == estado)
        if n:
            print(f"  vinham de {estado:<18} {n:>4}")

    print(f"\nPerdas — deixaram de sair certos ({sum(n for _e, n in perdas)}):")
    for estado in ESTADOS:
        n = sum(v for e, v in perdas if e == estado)
        if n:
            print(f"  viraram   {estado:<18} {n:>4}")

    liquido_inv = (sum(v for e, v in perdas if e == "errado_invisivel")
                   - sum(v for e, v in ganhos if e == "errado_invisivel"))
    print(f"\nSaldo de erro invisível sobre caractere rotulado: {liquido_inv:+d}")
    print("(negativo é a favor de "
          f"{para_margem:.2f}; positivo, de {de_margem:.2f})")


if __name__ == "__main__":
    sys.exit(main())
