"""
Matriz de confusão **na página real**, e não no split de validação.

A F13 fechou dizendo que o maior alvo restante deixou de ser segmentação: sobram
~348 caracteres lidos errado com o box certo. Este script diz quais são.

    python medir_confusao.py              # tabela resumida
    python medir_confusao.py --matriz     # a matriz inteira, classe a classe

**Por que não serve a matriz do treino.** `core.avaliacao` já produz uma, e ela
mede outra coisa: recorte já segmentado, limpo, da mesma base em que o modelo
treinou. Ali o número é 99,8%. Na página o mesmo modelo dá ~96%, e a diferença é
o assunto — recorte que veio do `findContours` com a sujeira que a página tem.

**A conta separa o que é confusão do que é impossível.** Um rótulo cuja classe o
modelo não tem não é erro de leitura: é classe que falta, e nenhuma matriz de
confusão o conserta. Misturar os dois inflaria o alvo e mandaria procurar no
lugar errado — foi o que a F13 encontrou do outro lado, com os 231 que eram 153.
"""

import argparse
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from PIL import Image

from core.avaliacao_pagina import carregar_box, comparar, normalizar
from medir_paginas import MIN_ROTULADOS, paginas_rotuladas, segmentar


#: Os cortes da curva de triagem da F1.9. A pergunta aqui é a mesma: destes
#: erros, quantos a confiança já denuncia?
CORTES = (0.500, 0.700, 0.900, 0.990, 0.999)


def _console_em_utf8():
    """
    O console do Windows é cp1252, e este relatório é feito de `♗`, `◼`, `⩱`.

    Sem isto o script morre de `UnicodeEncodeError` no meio da tabela — e morre
    justamente nas classes de figurina, que são as que interessam.
    """
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


#: Formas que o papel imprime praticamente iguais e só o tamanho ou o contexto
#: distingue. Cada grupo é uma classe de equivalência de **desenho**, não de
#: significado: um `0` e um `o` da mesma fonte diferem em altura, não em traço.
HOMOGLIFOS = [
    set("0oO"), set("1ilI|"), set("9gq"), set("5sS"), set("2zZ"),
    set("8B"), set(".,·"), set("'`’"), set(":;"), set("-–—_"),
]

#: Pontuação, para separar "o modelo trocou dois sinais" de "trocou duas
#: letras". São erros de custo diferente no texto final.
PONTUACAO = set(".,;:!?'\"()[]-–—/½")


def familia_do_erro(esperado: str, lido: str) -> str:
    """
    Em que família este par cai. A ordem dos testes é a da especificidade.

    O agrupamento é o produto desta medição: 313 pares soltos não dizem o que
    fazer, cinco famílias dizem. Cada uma pede um remédio diferente — ligadura
    disparada é classe nova que passou a competir, caixa e homóglifo são o
    mesmo desenho em tamanhos diferentes, e resto é o que sobra para olhar um
    a um.
    """
    if len(lido) > len(esperado) and esperado and esperado[0] in lido:
        return "ligadura disparada"
    if len(lido) > 1 or len(esperado) > 1:
        return "ligadura (outra)"
    if esperado.lower() == lido.lower():
        return "caixa alta/baixa"
    if any({esperado, lido} <= g for g in HOMOGLIFOS):
        return "homóglifo"
    if esperado in PONTUACAO and lido in PONTUACAO:
        return "pontuação"
    return "resto"


def _classes_do_modelo(meta_path):
    """As formas normalizadas que o modelo consegue emitir."""
    import json
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    return {normalizar(c) for c in meta["idx_to_char"].values()}


def main():
    _console_em_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--matriz", action="store_true",
                    help="lista todas as classes, não só as piores")
    ap.add_argument("--minimo", type=int, default=5,
                    help="classes com menos aparições que isto ficam de fora "
                         "da tabela de recall (padrão 5)")
    args = ap.parse_args()

    from core.services.learning_service import LearningService
    svc = LearningService()
    if not svc.load_predictor():
        print("sem modelo treinado:", svc.motivo_do_modelo())
        return 1
    predizer = svc._predictor.predict
    do_modelo = _classes_do_modelo(svc.meta_path)

    paginas = paginas_rotuladas()
    if not paginas:
        print("nenhuma página rotulada encontrada")
        return 1

    confusoes = Counter()          # (esperado, lido) -> quantas
    fora_do_modelo = Counter()     # esperado -> quantas
    total_por_classe = Counter()
    acertos_por_classe = Counter()
    conf_dos_erros = []
    conf_dos_acertos = []
    casados = 0

    for imagem, caminho_box in paginas:
        img = Image.open(imagem).convert("L")
        rotulados = carregar_box(caminho_box, img.size[1])
        if len(rotulados) < MIN_ROTULADOS:
            continue
        arr = np.array(img)

        _, filhos = segmentar(img, "arbitrado", arbitro=predizer)
        for b in filhos:
            b.char, b.confidence = predizer(arr[b.y1:b.y2, b.x1:b.x2])

        pares = comparar(filhos, rotulados).pares
        certos_pag = 0
        for i, j in pares:
            esperado = normalizar(rotulados[j].char)
            lido = normalizar(filhos[i].char)
            total_por_classe[esperado] += 1
            casados += 1
            if esperado == lido:
                acertos_por_classe[esperado] += 1
                conf_dos_acertos.append(filhos[i].confidence)
                certos_pag += 1
            elif esperado not in do_modelo:
                fora_do_modelo[esperado] += 1
                conf_dos_erros.append(filhos[i].confidence)
            else:
                confusoes[(esperado, lido)] += 1
                conf_dos_erros.append(filhos[i].confidence)

        print(f"  {os.path.basename(imagem)[-28:]:<30} "
              f"{len(pares):>5} casados   "
              f"{100.0 * certos_pag / max(1, len(pares)):>5.1f}% certos")

    errados = sum(confusoes.values()) + sum(fora_do_modelo.values())
    print(f"\n=========== {casados} boxes casados com um rótulo ===========")
    print(f"  lidos certo .............. {casados - errados}  "
          f"({100.0 * (casados - errados) / max(1, casados):.2f}%)")
    print(f"  lidos errado ............. {errados}")
    print(f"    confusão (a classe existe) ....... {sum(confusoes.values())}")
    print(f"    classe que o modelo não tem ...... {sum(fora_do_modelo.values())}")

    if fora_do_modelo:
        print("\nClasses que faltam ao modelo (nenhuma matriz conserta):")
        for c, n in fora_do_modelo.most_common(15):
            print(f"  {c!r:<10} {n:>4}")

    print("\nEm que famílias os erros caem:")
    familias = defaultdict(Counter)
    for (e, l), n in confusoes.items():
        familias[familia_do_erro(e, l)][(e, l)] += n
    ordenadas = sorted(familias.items(), key=lambda kv: -sum(kv[1].values()))
    for nome, pares in ordenadas:
        n = sum(pares.values())
        exemplos = "  ".join(f"{e}->{l}x{q}" for (e, l), q in
                             pares.most_common(4))
        print(f"  {nome:<26} {n:>4}  ({100.0 * n / max(1, sum(confusoes.values())):>4.1f}%)  "
              f"{exemplos}")

    print("\nOs pares que mais se comem (esperado -> lido):")
    for (e, l), n in confusoes.most_common(30):
        print(f"  {e!r:>8} -> {l!r:<10} {n:>4}  [{familia_do_erro(e, l)}]")

    print(f"\nRecall por classe na página (classes com {args.minimo}+ aparições):")
    linhas = []
    for c, tot in total_por_classe.items():
        if tot < args.minimo:
            continue
        ok = acertos_por_classe[c]
        linhas.append((100.0 * ok / tot, c, ok, tot))
    linhas.sort()
    mostrar = linhas if args.matriz else linhas[:25]
    for rec, c, ok, tot in mostrar:
        comeu = [f"{l!r}x{n}" for (e, l), n in confusoes.most_common()
                 if e == c][:3]
        print(f"  {c!r:>8} {rec:>6.1f}%  {ok:>4}/{tot:<5} "
              f"{'  '.join(comeu)}")
    if not args.matriz and len(linhas) > 25:
        print(f"  ... e mais {len(linhas) - 25} classes (use --matriz)")

    print("\nA confiança denuncia estes erros? (curva de triagem da F1.9)")
    erros = np.array(conf_dos_erros) if conf_dos_erros else np.zeros(0)
    acs = np.array(conf_dos_acertos) if conf_dos_acertos else np.zeros(0)
    print(f"  {'corte':>8} {'erros abaixo':>14} {'acertos abaixo':>16} "
          f"{'erros que escapam':>19}")
    for corte in CORTES:
        pegos = int((erros < corte).sum())
        falso_alarme = int((acs < corte).sum())
        print(f"  {corte:>8.3f} {pegos:>13} "
              f"{falso_alarme:>16} {len(erros) - pegos:>19}")
    if len(erros):
        print(f"\n  confiança mediana de um erro  {float(np.median(erros)):.4f}")
        print(f"  confiança mediana de um acerto {float(np.median(acs)):.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
