"""
O dicionário é cego a caixa, e quanto custaria abrir o olho dele (F108).

`Lexico.conhece` baixa os dois lados antes de comparar, então `biShop`,
`preSSure` e `tHe` são todos **conhecidos**. Para o dicionário um erro de caixa
não é erro: ele não sinaliza, a fila de revisão não enfileira, e o reparo da F66
não tem contra o que casar. Medido nos dois livros exportados, é o que passa:

    livro                palavras   maiúscula interna   aceitas assim mesmo
    Seirawan (pt)          69.129        13.089                4.583
    Yusupov (en)           42.684           764                  513

E contamina a régua: `medir_confusao_no_livro` usa o mesmo `conhece`, então a
tabela dos seis livros do ROADMAP **não enxerga erro de caixa** — que é a
família que a F107 mediu como 84% dos erros de leitura.

    python medir_caixa.py
    python medir_caixa.py --livro "Nunn"

## O que se propõe, e o que ele de fato é

Não é "guardar a forma do dicionário": as listas deste projeto são todas
minúsculas, então a forma atestada não existe para se guardar. O que existe é o
**padrão**. Três padrões são legítimos em qualquer língua de alfabeto latino —
`bishop`, `Bishop`, `BISHOP` —, e `biShop` não é nenhum deles. A regra é
tipográfica, e o dicionário só entra para dizer que aquilo é prosa e não lance.

**A correção é baixar a maiúscula interna, e nada mais.** Ela não escolhe entre
candidatas nem consulta distância de edição: onde a regra dispara, só existe uma
saída. Isso a põe na mesma família do veto da F106 — ela recusa o impossível, e
não opina sobre o duvidoso.

## O gabarito

As 25 páginas com `.box` rotulado à mão. **As caixas são as do gabarito**, então
a segmentação está certa por construção e o que varia é só a leitura de cada
recorte — que é como se isola a pergunta de caixa da de corte. As palavras saem
pela mesma régua de espaço da produção (`diagrama.limiar_de_espaco`).

**O hífen parte a palavra antes da regra**, e não é detalhe: `Kasparov-Karpov`
tem maiúscula interna e está certo. O `núcleo` do léxico só tira das pontas, de
propósito (`p1ay` precisa sobrar inteiro), então quem parta tem de ser esta
regra.

Reproduz a F108 no ROADMAP.
"""

import argparse
import os
import sys
from collections import Counter
from typing import List, Optional, Sequence, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2

from core import diagrama, formato_box, lexico, vertical
from core.lexico import caixa_estranha as anomala
from core.lexico import com_a_caixa_arrumada as corrigir
from core.lexico import pode_baixar
from core.box_model import BoxEntry
from core.leitura_de_linha import quebrar_em_linhas
from core.services.learning_service import LearningService
from medir_tamanho import _ler_cinza, livro_de, paginas_com_box


#: A marca de origem que o `.box` grava para a caixa que uma pessoa confirmou.
#: As outras (`neural`, `knn`, `easyocr`) são palpite gravado, e não gabarito.
ORIGEM_DE_MAO = "manual"


def _console_em_utf8():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


# ----------------------------------------------------------------------
# As palavras de uma página rotulada, lidas pelos dois lados
# ----------------------------------------------------------------------

def palavras_da_pagina(img, boxes: Sequence[BoxEntry], ler
                       ) -> List[Tuple[str, str, bool]]:
    """
    [(verdade, lido, só de mão)] por palavra, com as caixas do gabarito.

    **O terceiro campo existe porque o gabarito não é todo gabarito.** O `.box`
    guarda a origem de cada caixa, e nas páginas rotuladas convivem `manual` —
    a que uma pessoa digitou ou confirmou — e `neural`, que é o palpite do
    modelo gravado e nunca corrigido. Medindo contra as duas juntas, um erro de
    caixa que o modelo cometeu **e** gravou aparece como verdade: foi assim que
    `defeSa` saiu ao mesmo tempo como conserto (numa página) e como estrago
    (noutra). Só as de mão respondem à pergunta.
    """
    saida = []
    for linha in quebrar_em_linhas(list(boxes)):
        limiar = diagrama.limiar_de_espaco(linha)
        verdade, lido, mao = [], [], True
        for i, b in enumerate(linha):
            if i and b.x1 - linha[i - 1].x2 > limiar:
                if verdade:
                    saida.append(("".join(verdade), "".join(lido), mao))
                verdade, lido, mao = [], [], True
            recorte = vertical.recorte_de_pe(img, b)
            if recorte.size == 0:
                continue
            verdade.append(b.char)
            lido.append(ler(recorte)[0])
            mao = mao and b.source == ORIGEM_DE_MAO
        if verdade:
            saida.append(("".join(verdade), "".join(lido), mao))
    return saida


def main(argv=None) -> int:
    _console_em_utf8()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--livro", default=None,
                    help="mede só as obras cujo nome contenha isto")
    args = ap.parse_args(argv)

    lex = lexico.carregar()
    print(f"léxico: {len(lex)} palavras, idioma {lex.idioma}\n")

    svc = LearningService()
    if not svc.load_predictor():
        print("modelo neural não carregou:", svc.motivo_do_modelo())
        return 1

    #: (alvo, pega, conserta, estraga, alarme) por obra
    por_livro = {}
    exemplos_bons, exemplos_maus, alarmes = Counter(), Counter(), Counter()

    for img_p, box_p in paginas_com_box():
        obra = livro_de(box_p)
        if args.livro and args.livro.lower() not in obra.lower():
            continue
        img = _ler_cinza(img_p)
        if img is None:
            continue
        boxes = [b for b in formato_box.ler(box_p, img.shape[0]) if b.char]
        if not boxes:
            continue

        conta = por_livro.setdefault(obra, Counter())
        for verdade, lido, de_mao in palavras_da_pagina(img, boxes,
                                                        svc.ler_texto):
            if not de_mao:
                conta["palpite_gravado"] += 1
                continue
            nuc_v, _ = lexico.nucleo(verdade)
            nuc_l, _ = lexico.nucleo(lido)
            if len(nuc_l) < 3:
                continue
            conta["palavras"] += 1

            # O alvo: a palavra que só erra por caixa. É a população que a
            # regra existe para alcançar, e a única em que ela pode acertar.
            so_caixa = nuc_v != nuc_l and nuc_v.lower() == nuc_l.lower()
            if so_caixa:
                conta["alvo"] += 1

            if not anomala(nuc_l):
                continue
            # A regra acusa; `pode_baixar` diz se ela também corrige. O `I` só
            # acusa — ver `lexico.CAIXA_SO_ACUSADA`.
            arrumado = corrigir(nuc_l) if pode_baixar(nuc_l) else nuc_l

            # **O portão do dicionário funciona por causa da cegueira dele**, e
            # não apesar dela: `conhece('biShop')` é verdadeiro e
            # `conhece('tbitBl')` é falso, então baixar os dois lados separa
            # exatamente prosa de lixo. É o único uso em que a cegueira ajuda.
            passa = lex.conhece(nuc_l)
            for sufixo, vale in (("", True), ("_gate", passa)):
                if not vale:
                    continue
                conta["acusa" + sufixo] += 1
                if arrumado == nuc_v:
                    conta["conserta" + sufixo] += 1
                elif nuc_l == nuc_v:
                    # Estava certa e a regra a estragou: é o erro que não se
                    # pode cometer, e o que decide se a regra vale.
                    conta["estraga" + sufixo] += 1
                else:
                    # Errada antes e errada depois — a regra não a alcança, mas
                    # também não piorou. Acusar já a põe na fila de revisão.
                    conta["nem_la_nem_ca" + sufixo] += 1

            if arrumado == nuc_v:
                exemplos_bons[f"{nuc_l} -> {arrumado}"] += 1
            elif nuc_l == nuc_v:
                exemplos_maus[f"{nuc_l} -> {arrumado}"
                              f"{'  [o portão o barra]' if not passa else ''}"] += 1
            else:
                alarmes[f"{nuc_v} lido {nuc_l} -> {arrumado}"] += 1

    if not por_livro:
        print("nenhuma página rotulada encontrada")
        return 1

    print("a regra sozinha, e a regra com o portão do dicionário\n")
    print(f"{'obra':<34} {'palav.':>7} {'só caixa':>8}"
          f" | {'acusa':>6} {'conserta':>8} {'estraga':>7}"
          f" | {'acusa':>6} {'conserta':>8} {'estraga':>7}")
    total = Counter()
    for obra, c in sorted(por_livro.items()):
        if not c["palavras"]:
            continue
        total.update(c)
        print(f"{obra[:34]:<34} {c['palavras']:>7} {c['alvo']:>8}"
              f" | {c['acusa']:>6} {c['conserta']:>8} {c['estraga']:>7}"
              f" | {c['acusa_gate']:>6} {c['conserta_gate']:>8}"
              f" {c['estraga_gate']:>7}")
    print(f"{'TOTAL':<34} {total['palavras']:>7} {total['alvo']:>8}"
          f" | {total['acusa']:>6} {total['conserta']:>8} {total['estraga']:>7}"
          f" | {total['acusa_gate']:>6} {total['conserta_gate']:>8}"
          f" {total['estraga_gate']:>7}")

    alvo = max(1, total["alvo"])
    print(f"\n  alvo: {total['alvo']} palavras que erram **só** por caixa")
    print(f"  regra sozinha .... conserta {total['conserta']} "
          f"({total['conserta']/alvo:.0%}), estraga {total['estraga']}")
    print(f"  com o portão ..... conserta {total['conserta_gate']} "
          f"({total['conserta_gate']/alvo:.0%}), estraga "
          f"{total['estraga_gate']}")

    print("\nconsertos mais frequentes")
    for k, n in exemplos_bons.most_common(12):
        print(f"  {n:>4}x  {k}")
    if exemplos_maus:
        print("\nestragos — cada um é uma palavra certa que a regra derrubou")
        for k, n in exemplos_maus.most_common(12):
            print(f"  {n:>4}x  {k}")
    print("\nacusadas que continuam erradas (a regra as manda para a revisão)")
    for k, n in alarmes.most_common(8):
        print(f"  {n:>4}x  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
