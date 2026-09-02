"""
A troca do tamanho da lista de palavras: alarme falso contra erro escondido (F9.1).

    python medir_troca.py                          # as listas de assets/lexico
    python medir_troca.py --lista a.txt b.txt.gz   # compara listas quaisquer

`medir_lexico.py --lista` mede o alarme falso sobre a **verdade** rotulada, e por
isso não vê a outra metade: lista maior cala mais alarme falso *e* esconde mais
erro, porque a leitura errada cai dentro dela — `glans` está na lista, então `plans`
lido `glans` passa batido. Esta medição roda o OCR de verdade e classifica cada
palavra de prosa lida:

    lido == verdade, fora da lista   alarme falso
    lido != verdade, fora da lista   ERRO PEGO
    lido != verdade, na lista        ERRO ESCONDIDO

O par (recall, alarme falso) é o que decide o tamanho da lista, e a medida 3 do
ROADMAP é a saída deste arquivo.

**A comparação é sensível a caixa** (F109 §6). Era `.lower()` dos dois lados, e
com isso `alSo` lido por `also` entrava no denominador **como acerto** — e como a
lista conhece `also`, o erro que ela escondia nem era contado. A coluna `caixa`
diz quantos dos escondidos são só de caixa: são os que a lista nunca poderia
pegar, porque ela não tem caixa, e que a F108 pega por outro caminho.

**Pedaço com box sem par não é medível**, e ignorar isso inverteu o resultado na
primeira rodada. A verdade é remontada dos pares de `comparar`; um box gerado sem par
contribui string vazia e a verdade sai truncada, então saíam como "erro escondido"
coisas como `difficult` lido onde a verdade seria `diffcult` e `King` onde seria `ng`
— casos em que o OCR acertou e quem perdeu letra foi a verdade remontada. É a
terceira vez na fase que a propriedade medida não era a que interessava; as outras
duas estão na F1.5 e na medida 1.
"""

import argparse
import os
import sys
from collections import Counter

import numpy as np
from PIL import Image

from core import lexico
from core.avaliacao_pagina import carregar_box, comparar, normalizar
from medir_lexico import nucleo, pedacos_da_pagina
from medir_paginas import MIN_ROTULADOS, paginas_rotuladas, segmentar
from core.services.learning_service import LearningService

# O console do Windows é cp1252 e não tem os glifos de xadrez — a mesma armadilha
# que `medir_lexico.py` registra.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def _padrao():
    """As duas listas empacotadas, e a do idioma sozinha para comparar."""
    idioma = lexico.CAMINHO_PADRAO
    nomes = lexico.CAMINHO_NOMES
    saida = {}
    if os.path.exists(idioma):
        saida["idioma"] = lexico._ler(idioma)
    if os.path.exists(nomes) and "idioma" in saida:
        saida["idioma+nomes"] = saida["idioma"] | lexico._ler(nomes)
    return saida


def medir(listas, exemplos=18):
    svc = LearningService()
    if not svc.load_predictor():
        print("sem modelo treinado — esta medição precisa dele")
        return 1
    predizer = svc._predictor.predict

    conta = {n: Counter() for n in listas}
    escondidos = {n: [] for n in listas}
    total = nao_medivel = com_erro = 0

    for imagem, caminho_box in paginas_rotuladas():
        img = Image.open(imagem).convert("L")
        rotulados = carregar_box(caminho_box, img.size[1])
        if len(rotulados) < MIN_ROTULADOS:
            continue
        arr = np.array(img)

        # O modo de hoje: separador com árbitro (F1.5b).
        _, filhos = segmentar(img, "arbitrado", arbitro=predizer)
        for b in filhos:
            b.char, b.confidence = predizer(arr[b.y1:b.y2, b.x1:b.x2])

        r = comparar(filhos, rotulados)
        verdade = {i: rotulados[j].char for i, j in r.pares}

        for pedaco in pedacos_da_pagina(filhos):
            if pedaco.tipo != "outro":
                continue
            indices = [s.indice for s in pedaco.simbolos]
            if any(verdade.get(i) is None for i in indices):
                nao_medivel += 1
                continue
            vd = "".join(verdade[i] for i in indices)
            lido, _ = nucleo(pedaco.texto)
            certo, _ = nucleo(vd)
            # A mesma população de `medir_lexico.palavras_verdadeiras`: palavra de
            # prosa de duas letras para cima cuja verdade é palavra. Sem isso, "d4"
            # mal lido entraria como erro que o léxico deveria pegar, e ele não é
            # palavra de idioma nenhum.
            if len(certo) < 2 or not certo.isalpha() or len(lido) < 2:
                continue
            total += 1
            errada = normalizar(lido) != normalizar(certo)
            so_caixa = (errada and normalizar(lido).lower()
                        == normalizar(certo).lower())
            com_erro += errada
            for nome, lista in listas.items():
                conhece = lido.lower() in lista
                if errada and conhece:
                    conta[nome]["escondido"] += 1
                    conta[nome]["caixa"] += so_caixa
                    if len(escondidos[nome]) < exemplos:
                        escondidos[nome].append(f"{lido!r}<-{certo!r}")
                elif errada:
                    conta[nome]["pego"] += 1
                elif not conhece:
                    conta[nome]["alarme"] += 1

    if not total:
        print("nenhuma palavra de prosa medível")
        return 1

    print(f"\n=========== {total} palavras de prosa lidas, "
          f"{com_erro} com erro de OCR ===========")
    print(f"({nao_medivel} pedaços fora da conta por terem box sem par)\n")
    print(f"{'lista':<16} {'palavras':>9} {'pego':>6} {'escond':>7} "
          f"{'caixa':>6} {'recall':>8} {'alarme':>8} {'precisão':>9}")
    for nome, c in conta.items():
        pego, esc, alarme = c["pego"], c["escondido"], c["alarme"]
        rec = 100.0 * pego / (pego + esc) if pego + esc else 0.0
        print(f"{nome:<16} {len(listas[nome]):>9} {pego:>6} {esc:>7} "
              f"{c['caixa']:>6} "
              f"{rec:>7.1f}% {100.0*alarme/total:>7.1f}% "
              f"{100.0*pego/(pego+alarme) if pego+alarme else 0:>8.1f}%")

    for nome, ex in escondidos.items():
        if ex:
            print(f"\n--- escondidos por {nome} (lido<-verdade) ---")
            print("  " + "; ".join(ex))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lista", nargs="*", default=None,
                    help="listas a comparar; sem isto, as de assets/lexico")
    ap.add_argument("--exemplos", type=int, default=18)
    args = ap.parse_args()

    if args.lista:
        listas = {os.path.basename(c): lexico._ler(c) for c in args.lista}
    else:
        listas = _padrao()
    if not listas:
        print(f"nenhuma lista — rode `python importar_lexico.py` primeiro")
        return 1
    return medir(listas, args.exemplos)


if __name__ == "__main__":
    sys.exit(main())
