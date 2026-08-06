"""
Mede quanto do erro de OCR um dicionário de palavras teria como alcançar (F9.1).

Esta é a **primeira** medição da F9, e a ordem não é arbitrária: o item diz que ela
pode encerrar a fase. Um dicionário só age sobre palavra de prosa — a notação é
domínio da legalidade (F1.7), e pontuação não está dentro de palavra nenhuma. Se a
fatia de erro que cai em palavra for magra, não há léxico que pague, e o custo de
descobrir isso é uma contagem.

É o método da F1.8, que supôs milhares de boxes de lixo e mediu **um**.

    python medir_lexico.py                # todas as páginas rotuladas
    python medir_lexico.py --exemplos 12  # mostra amostras de cada categoria

As categorias, e por que cada uma é o que é:

    lance            o pedaço foi tipado `lance` — quem decide é a legalidade
    numero           número de jogada
    fora-do-nucleo   o erro está na pontuação das pontas ("counterplay," -> a vírgula)
    nucleo-nao-e-palavra   o que devia estar ali não é palavra ("2010", "d4")
    palavra-de-1     núcleo de uma letra só — está no dicionário de qualquer jeito
    PALAVRA          alcançável: erro dentro de palavra de duas letras ou mais

`PALAVRA` é o teto, não a promessa. Duas deduções ficam fora do alcance desta
medição e estão registradas no ROADMAP: a palavra cuja leitura errada é **outra
palavra real** (o léxico não tem o que sinalizar) e a palavra que um dicionário
genérico não tem (nome próprio — é a F9.2). A segunda é parcialmente medida aqui
pela divisão minúscula/Capitalizada.

`risco-de-lance` é o contrário: pedaço tipado `outro` cuja verdade **é** um lance.
Ali o léxico atacaria notação, que é o que o contrato 1 da SPEC §5.8 proíbe. Se
esse número for grande, a fronteira `parece_lance` não basta como peneira.
"""

import argparse
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from PIL import Image

from core import lexico, notacao
from core.avaliacao_pagina import carregar_box, comparar, normalizar
from medir_paginas import MIN_ROTULADOS, paginas_rotuladas, segmentar


CATEGORIAS = ("lance", "numero", "fora-do-nucleo", "nucleo-nao-e-palavra",
              "palavra-de-1", "PALAVRA")

# O console do Windows é cp1252 e não tem os glifos de xadrez: imprimir '♖' cru
# derruba a medição no fim, depois de todo o trabalho. É a mesma armadilha que a
# SPEC §5.2 registra para o `cv2.imwrite` em caminho não-ASCII.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def nucleo(texto: str) -> tuple:
    """
    (núcleo, início) — o que iria a uma consulta de dicionário.

    Tira o que não é letra das **pontas**, não do meio: "p1ay" tem de sobrar
    inteiro, porque o `1` no meio é justamente o erro que se quer alcançar.
    """
    i, j = 0, len(texto)
    while i < j and not texto[i].isalpha():
        i += 1
    while j > i and not texto[j - 1].isalpha():
        j -= 1
    return texto[i:j], i


def pedacos_da_pagina(boxes):
    """[Pedaco] de toda a página, no caminho de produção.

    `_fatiar` é privado e é usado de propósito: é o mesmo código que a F1.7 roda,
    e uma cópia divergente foi o que deixou a F1.5 medir uma coisa e a aplicação
    fazer outra.
    """
    saida = []
    for linha in notacao.palavras_da_pagina(boxes):
        for palavra in linha:
            saida.extend(notacao._fatiar(palavra))
    return saida


def classificar_erros(gerados, rotulados):
    """
    Onde cai cada caractere errado da página.

    Devolve (contagem por categoria, exemplos, extras). A verdade vem do
    emparelhamento de `comparar`; box espúrio não tem verdade e entra à parte,
    porque ele é editável (contrato 3 da §5.8) mas não é "caractere errado".
    """
    r = comparar(gerados, rotulados)
    verdade = {i: rotulados[j].char for i, j in r.pares}
    errados = {i for i, j in r.pares
               if normalizar(gerados[i].char) != normalizar(rotulados[j].char)}

    # Ligadura certa que o emparelhamento conta como erro.
    #
    # `comparar` casa um box gerado com **um** rotulado. Um box que cobre "e4"
    # colado casa com o 'e', então ler "e4" — que é a leitura certa e é a razão
    # das classes da SPEC §5.2 item 6 existirem — sai como erro *e* deixa o '4'
    # como perdido. O metro pune a classe que acerta.
    ligadura_certa = set()
    for i in errados:
        lido_n = normalizar(gerados[i].char)
        if len(lido_n) < 2:
            continue
        g = gerados[i]
        dentro = [b for b in rotulados
                  if g.x1 <= (b.x1 + b.x2) / 2 <= g.x2
                  and g.y1 <= (b.y1 + b.y2) / 2 <= g.y2]
        dentro.sort(key=lambda b: b.x1)
        if len(dentro) >= 2 and "".join(normalizar(b.char) for b in dentro) == lido_n:
            ligadura_certa.add(i)

    conta = Counter()
    caixa = Counter()          # PALAVRA: minúscula vs Capitalizada
    exemplos = defaultdict(list)
    extras = Counter(espurios_em_palavra=0, risco_de_lance=0)

    for pedaco in pedacos_da_pagina(gerados):
        indices = [s.indice for s in pedaco.simbolos]
        lido = pedaco.texto
        # A verdade do pedaço: box espúrio não contribui caractere nenhum.
        partes = [verdade.get(i) for i in indices]
        vd = "".join(p for p in partes if p)

        # Onde cada box começa dentro de `vd`. **O núcleo é recortado da verdade,
        # não do lido**, e isso levou uma medição errada para descobrir: com o
        # recorte pelo lido, "Mov6" (verdade "Move") e "3awn" (verdade "Pawn")
        # caíam em `fora-do-nucleo`, porque o caractere errado virou dígito e
        # deixou de ser borda alfabética. São os erros mais alcançáveis que
        # existem, e a medida os estava jogando fora.
        inicio, corr = [], 0
        for p in partes:
            inicio.append(corr)
            corr += len(p) if p else 0

        nuc_v, ini_v = nucleo(vd)
        fim_v = ini_v + len(nuc_v)
        e_palavra = len(nuc_v) >= 2 and nuc_v.isalpha()

        def no_nucleo(k):
            return partes[k] is not None and ini_v <= inicio[k] < fim_v

        # Box espúrio dentro de palavra: o léxico pode esvaziá-lo. Ele não tem
        # verdade, então a posição de referência é a do vizinho anterior.
        if pedaco.tipo == "outro" and e_palavra:
            extras["espurios_em_palavra"] += sum(
                1 for k, i in enumerate(indices)
                if partes[k] is None and ini_v <= inicio[k] <= fim_v)

        # Fronteira vazando: tipado prosa, mas a verdade é um lance.
        if pedaco.tipo == "outro" and nuc_v and notacao.parece_lance(vd):
            extras["risco_de_lance"] += 1
            exemplos["risco-de-lance"].append(f"{lido!r} -> {vd!r}")

        for k, i in enumerate(indices):
            if i not in errados:
                continue
            # Ligadura predita onde a verdade tem um caractere só (e o inverso):
            # é o custo das 16 classes novas da SPEC §5.2 item 6, que ninguém
            # havia contado — cada erro desses injeta ou come um caractere.
            if len(gerados[i].char) > len(verdade[i]):
                extras["ligadura_a_mais"] += 1
            elif len(gerados[i].char) < len(verdade[i]):
                extras["ligadura_a_menos"] += 1

            if pedaco.tipo in ("lance", "numero"):
                cat = pedaco.tipo
            elif len(nuc_v) == 1:
                cat = "palavra-de-1"
            elif not e_palavra:
                cat = "nucleo-nao-e-palavra"
            elif not no_nucleo(k):
                cat = "fora-do-nucleo"
            else:
                cat = "PALAVRA"
                caixa["Capitalizada" if nuc_v[0].isupper() else "minúscula"] += 1

            conta[cat] += 1
            if len(exemplos[cat]) < 40:
                # Normalizado porque é assim que a comparação decide: a figurina
                # e a letra do lance são a mesma leitura (F1.1).
                exemplos[cat].append(
                    f"{normalizar(gerados[i].char)!r}<-{normalizar(verdade[i])!r}"
                    f" em {lido!r}" + (f" (verdade {vd!r})" if vd != lido else ""))

    # Erros que o emparelhamento não vê como par.
    extras["perdidos"] = r.perdidos
    extras["espurios"] = r.espurios
    extras["errados"] = len(errados)
    extras["rotulados"] = r.rotulados
    extras["ligadura_certa"] = len(ligadura_certa)
    extras["verdade_ilegivel"] = sum(1 for i in errados if verdade[i] == "?")
    return conta, caixa, exemplos, extras


def palavras_verdadeiras(rotulados):
    """
    Os núcleos de palavra construídos sobre a VERDADE rotulada, não sobre o OCR.

    Serve para medir a lista de palavras sem envolver o modelo: toda palavra que
    está certa na página e **não** está na lista viraria alarme falso. É o piso de
    falso positivo da sinalização, e dá para medi-lo antes de escrever o léxico.
    """
    saida = []
    for pedaco in pedacos_da_pagina(rotulados):
        if pedaco.tipo != "outro":
            continue
        nuc, _ = nucleo(pedaco.texto)
        if len(nuc) >= 2 and nuc.isalpha():
            saida.append(nuc)
    return saida


def _parte_em_palavras(w, lista, min_parte=2):
    """`w` se decompõe em palavras de `lista`? ("ofthe" -> "of"+"the")

    Se decompõe, a palavra ausente não é lacuna de vocabulário: é **espaço
    perdido** na segmentação, e o culpado é o limiar de lacuna da `notacao`.

    **`lista` aqui é o vocabulário da própria página, e não a lista de 370 mil.**
    Contra a lista grande esta função mentia: `Benko` decompõe em `ben`+`ko` e
    `queenside` em `queen`+`side`, porque uma lista desse tamanho tem lixo de duas
    e três letras para todo lado — 60% das ausências vinham marcadas como espaço
    perdido, e não eram. Palavra que se parte em palavras **vistas nas mesmas
    páginas** é sinal forte; e errar para menos é o lado seguro.
    """
    n = len(w)
    alcanca = [False] * (n + 1)
    alcanca[0] = True
    for j in range(min_parte, n + 1):
        for i in range(0, j - min_parte + 1):
            if alcanca[i] and w[i:j] in lista:
                alcanca[j] = True
                break
    return alcanca[n] and n >= 4


def _e_pedaco(w, ordenada, ordenada_rev, min_len=4, folga=2):
    """`w` é começo ou fim de alguma palavra da lista, sem ser palavra?

    É a assinatura de palavra partida — pelo hífen de fim de linha ("em-" /
    "barrassment") ou por um box de ligadura que abriu lacuna no meio dela
    ("fi" + "ghting").

    `min_len` de 4 e `folga` de 2 existem pela mesma razão do aviso acima: com 3
    letras, `Elo` sai como prefixo de `elope` e `ofa` de `ofay`. Exigir que a
    palavra completa seja pelo menos duas letras maior corta a coincidência.
    """
    import bisect
    if len(w) < min_len:
        return None
    i = bisect.bisect_left(ordenada, w)
    if (i < len(ordenada) and ordenada[i].startswith(w)
            and len(ordenada[i]) >= len(w) + folga):
        return "prefixo-de-palavra"
    r = w[::-1]
    i = bisect.bisect_left(ordenada_rev, r)
    if (i < len(ordenada_rev) and ordenada_rev[i].startswith(r)
            and len(ordenada_rev[i]) >= len(r) + folga):
        return "sufixo-de-palavra"
    return None


def culpa_da_ausencia(faltando, lista, vocabulario):
    """De quem é cada palavra ausente: da lista, da segmentação ou do hífen."""
    ordenada = sorted(lista)
    ordenada_rev = sorted(w[::-1] for w in lista)
    conta, exemplos = Counter(), defaultdict(list)
    for w in faltando:
        b = w.lower()
        # O vocabulário da página, menos a própria palavra: senão "ofthe" se
        # explicaria por si mesma.
        vizinhas = vocabulario - {b}
        if _parte_em_palavras(b, vizinhas):
            cat = "espaco-perdido"
        else:
            cat = _e_pedaco(b, ordenada, ordenada_rev) or "vocabulario"
        conta[cat] += 1
        if len(exemplos[cat]) < 12:
            exemplos[cat].append(w)
    return conta, exemplos


def _lacunas(palavra, boxes, largura):
    """Lacuna entre cada par de caracteres vizinhos, em larguras medianas."""
    saida = []
    for k in range(len(palavra.simbolos) - 1):
        a = boxes[palavra.simbolos[k].indice]
        b = boxes[palavra.simbolos[k + 1].indice]
        saida.append((b.x1 - a.x2) / largura)
    return saida


def reparar_fronteiras(rotulados, lex):
    """
    Aplica os dois reparos do `core.lexico` sobre a verdade rotulada.

    Devolve (palavras finais, quantas junções de hífen, quantos cortes). Roda
    sobre a **verdade** de propósito: mede a fronteira de palavra sem o OCR no
    meio, então um número que melhora aqui melhorou por mérito do reparo.
    """
    largura = notacao._largura_mediana(rotulados) or 1.0

    # **A população é a mesma de `palavras_verdadeiras`: só pedaço tipado `outro`.**
    # A primeira versão iterava sobre todas as palavras, notação inclusive, e o
    # alarme falso "subiu" de 12,1% para 27,9% porque `Rxf2` e `Nf3` entraram como
    # palavra desconhecida. Não era o reparo piorando: era comparar duas
    # populações diferentes.
    linhas = []
    for linha in notacao.palavras_da_pagina(rotulados):
        pedacos = []
        for palavra in linha:
            pedacos.extend(p for p in notacao._fatiar(palavra)
                           if p.tipo == "outro")
        linhas.append(pedacos)

    textos = [[p.texto for p in linha] for linha in linhas]
    juncoes = lexico.juntar_hifenizadas(textos, lex)
    juntado = {(j.linha, j.palavra): j.texto for j in juncoes}
    # O pedaço da direita foi consumido pela junção e não conta duas vezes.
    consumido = {(j.linha + 1, 0) for j in juncoes}

    finais, cortes = [], 0
    for k, linha in enumerate(linhas):
        for i, p in enumerate(linha):
            if (k, i) in consumido:
                continue
            if (k, i) in juntado:
                finais.append(juntado[(k, i)])
                continue
            nuc, desloc = nucleo(p.texto)
            if len(nuc) < 2:
                continue
            lac = _lacunas(p, rotulados, largura)[desloc:desloc + len(nuc) - 1]
            corte = lexico.partir_colada(nuc, lac, lex)
            if corte:
                finais.extend([nuc[:corte], nuc[corte:]])
                cortes += 1
            else:
                finais.append(nuc)
    return finais, len(juncoes), cortes


def medir_lista(caminho, reparar=False):
    """Cobertura de uma lista de palavras sobre as páginas rotuladas."""
    # `lexico._ler` e não `open`, senão as listas empacotadas em `.gz` não abrem
    # aqui — e medir a lista que o programa não usa é pior que não medir.
    lista = lexico._ler(caminho)
    print(f"{caminho}: {len(lista)} palavras\n")
    lex = lexico.Lexico(palavras=lista) if reparar else None

    todas, faltando = [], []
    rep_todas, rep_faltando, n_jun, n_cortes = [], [], 0, 0
    for imagem, caminho_box in paginas_rotuladas():
        img = Image.open(imagem)
        rotulados = carregar_box(caminho_box, img.size[1])
        if len(rotulados) < MIN_ROTULADOS:
            continue
        p = palavras_verdadeiras(rotulados)
        fora = [w for w in p if w.lower() not in lista]
        todas.extend(p)
        faltando.extend(fora)
        linha = (f"{os.path.basename(imagem)[-34:]:<36} palavras {len(p):>4}  "
                 f"fora da lista {len(fora):>3} "
                 f"({100.0*len(fora)/len(p) if p else 0:>4.1f}%)")

        if reparar:
            rp, j, c = reparar_fronteiras(rotulados, lex)
            # Só as de prosa, para comparar com a mesma base.
            rp = [w for w in rp if len(w) >= 2 and w.isalpha()]
            rf = [w for w in rp if w.lower() not in lista]
            rep_todas.extend(rp)
            rep_faltando.extend(rf)
            n_jun += j
            n_cortes += c
            linha += (f"  |  reparado {len(rf):>3} "
                      f"({100.0*len(rf)/len(rp) if rp else 0:>4.1f}%)")
        print(linha)

    if not todas:
        print("nenhuma palavra verdadeira encontrada")
        return 1

    unicas = Counter(w.lower() for w in todas)
    fora_unicas = Counter(w.lower() for w in faltando)
    cap = sum(1 for w in faltando if w[0].isupper())

    print(f"\n=========== TOTAL ===========")
    print(f"  palavras de prosa na verdade        {len(todas):>6}"
          f"  ({len(unicas)} distintas)")
    print(f"  fora da lista                       {len(faltando):>6}"
          f"  ({len(fora_unicas)} distintas)"
          f"  = {100.0*len(faltando)/len(todas):.1f}% de alarme falso")
    print(f"    das quais Capitalizadas           {cap:>6}"
          f"  ({100.0*cap/len(faltando) if faltando else 0:.1f}% do alarme)")

    if reparar and rep_todas:
        print(f"\n  --- com os reparos de fronteira do core.lexico ---")
        print(f"  junções de hífen aplicadas          {n_jun:>6}")
        print(f"  palavras coladas partidas           {n_cortes:>6}")
        print(f"  palavras de prosa                   {len(rep_todas):>6}")
        print(f"  fora da lista                       {len(rep_faltando):>6}"
              f"  = {100.0*len(rep_faltando)/len(rep_todas):.1f}% de alarme falso"
              f"  (era {100.0*len(faltando)/len(todas):.1f}%)")

    conta, exemplos = culpa_da_ausencia(faltando, lista, set(unicas))
    print(f"\nDe quem é a ausência, nas {len(faltando)} ocorrências:")
    for cat in ("espaco-perdido", "prefixo-de-palavra", "sufixo-de-palavra",
                "vocabulario"):
        if conta[cat]:
            print(f"  {cat:<20} {conta[cat]:>4} {100.0*conta[cat]/len(faltando):>6.1f}%"
                  f"   ex.: {', '.join(exemplos[cat][:6])}")

    print("\nAs que mais aparecem e a lista não tem:")
    for w, k in fora_unicas.most_common(15):
        print(f"  {k:>3}x  {w}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exemplos", type=int, default=0,
                    help="quantas amostras mostrar por categoria")
    ap.add_argument("--reparar", action="store_true",
                    help="aplica os reparos de fronteira e re-mede")
    ap.add_argument("--lista", default=None,
                    help="mede a cobertura de uma lista de palavras (sem modelo)")
    args = ap.parse_args()

    if args.lista:
        return medir_lista(args.lista, reparar=args.reparar)

    from core.services.learning_service import LearningService
    svc = LearningService()
    if not svc.load_predictor():
        print("sem modelo treinado — esta medição precisa dele")
        return 1
    predizer = svc._predictor.predict

    paginas = paginas_rotuladas()
    if not paginas:
        print("nenhuma página rotulada encontrada")
        return 1

    total, caixa_total = Counter(), Counter()
    extras_total = Counter()
    exemplos_total = defaultdict(list)

    for imagem, caminho_box in paginas:
        img = Image.open(imagem).convert("L")
        rotulados = carregar_box(caminho_box, img.size[1])
        if len(rotulados) < MIN_ROTULADOS:
            continue
        arr = np.array(img)

        # O modo de hoje: separador com árbitro (F1.5b).
        _, filhos = segmentar(img, "arbitrado", arbitro=predizer)
        for b in filhos:
            b.char, b.confidence = predizer(arr[b.y1:b.y2, b.x1:b.x2])

        conta, caixa, exemplos, extras = classificar_erros(filhos, rotulados)
        total += conta
        caixa_total += caixa
        extras_total += extras
        for k, v in exemplos.items():
            exemplos_total[k].extend(v)

        n = sum(conta.values())
        alc = 100.0 * conta["PALAVRA"] / n if n else 0.0
        print(f"{os.path.basename(imagem)[-34:]:<36} "
              f"errados {n:>4}  em palavra {conta['PALAVRA']:>4} ({alc:>4.1f}%)")

    n = sum(total.values())
    print(f"\n=========== TOTAL — {n} caracteres errados ===========")
    print(f"{'categoria':<24} {'n':>6} {'do erro':>9}")
    for cat in CATEGORIAS:
        print(f"{cat:<24} {total[cat]:>6} {100.0*total[cat]/n:>8.1f}%")

    print(f"\nDos {total['PALAVRA']} alcançáveis, por caixa da palavra verdadeira:")
    for k, v in caixa_total.most_common():
        print(f"  {k:<14} {v:>5} {100.0*v/total['PALAVRA']:>7.1f}%")

    print("\nOutras contas da mesma página:")
    print(f"  rotulados                        {extras_total['rotulados']:>6}")
    print(f"  caracteres perdidos (sem box)    {extras_total['perdidos']:>6}"
          "   — viram sugestão, não edição")
    print(f"  boxes espúrios                   {extras_total['espurios']:>6}")
    print(f"    dos quais dentro de palavra    {extras_total['espurios_em_palavra']:>6}"
          "   — o léxico pode esvaziá-los")
    print(f"  pedaços 'outro' que eram lance   {extras_total['risco_de_lance']:>6}"
          "   — onde a fronteira vazaria")
    print(f"\nClasses de ligadura (SPEC §5.2 item 6), dentro dos {n} erros acima:")
    print(f"  ligadura lida onde havia menos   {extras_total['ligadura_a_mais']:>6}"
          "   — injeta caractere no texto")
    print(f"  caractere lido onde havia mais   {extras_total['ligadura_a_menos']:>6}"
          "   — come caractere")
    print(f"  ligadura CERTA contada como erro {extras_total['ligadura_certa']:>6}"
          "   — o metro pune a classe que acerta")
    print(f"  verdade rotulada como '?'        {extras_total['verdade_ilegivel']:>6}"
          "   — nem o humano leu; não é erro do modelo")

    if args.exemplos:
        for cat in list(CATEGORIAS) + ["risco-de-lance"]:
            amostras = exemplos_total.get(cat, [])[:args.exemplos]
            if amostras:
                print(f"\n--- {cat} ---")
                for a in amostras:
                    print(f"  {a}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
