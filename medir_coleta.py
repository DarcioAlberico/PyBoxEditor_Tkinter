"""
Mede a **precisão da pasta de revisão** — o que "Criar Recortes para Revisão" produz.

A pergunta não é a acurácia do modelo, que já tem régua (`medir_paginas.py`). É
outra, e é a que decide se a revisão vale a tarde de quem a faz:

    dos arquivos que caíram em `revisao_ocr/lower_o/`, quantos são um `o`?

Três respostas possíveis para cada arquivo, e as três importam por motivos
diferentes:

    certo     o box cerca um caractere e o modelo o leu certo — é contraste,
              é o que faz o intruso saltar aos olhos na grade de miniaturas
    errado    o box cerca um caractere e o modelo errou — é o material de
              treino que a fase existe para colher
    espúrio   **não há caractere nenhum ali**: respingo, pedaço de régua,
              metade de glifo partido. O modelo foi obrigado a responder e
              respondeu. Este é o veneno: na miniatura ele é indistinguível
              de um acerto, e é promovido junto com os outros.

A régua do "espúrio" são as páginas rotuladas à mão (as mesmas de
`medir_paginas.py` e da calibração): box gerado que não emparelha com nenhum
rotulado é box que não cerca caractere.

    python medir_coleta.py                 # a tabela completa
    python medir_coleta.py --varrer        # a varredura dos limiares da porta
    python medir_coleta.py --so page-0020  # só estas páginas

Reproduz a tabela da F93 no ROADMAP.
"""

import argparse
import os
import sys
from collections import Counter

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import coleta
from core.avaliacao_pagina import carregar_box, comparar, normalizar
from core.calibracao_de_pagina import MIN_ROTULADOS, paginas_rotuladas
from core.services.box_service import BoxService


# ----------------------------------------------------------------------
# Colher: um registro por box gerado, com o veredito da régua rotulada
# ----------------------------------------------------------------------

class Recorte:
    """Um box gerado, o que o modelo disse dele, e o que ele era."""

    __slots__ = ("imagem", "palpite", "conf", "pagina", "verdade")

    def __init__(self, imagem, palpite, conf, pagina, verdade):
        self.imagem = imagem
        self.palpite = palpite
        self.conf = conf
        self.pagina = pagina
        #: o caractere rotulado à mão, ou `None` quando não há caractere ali
        self.verdade = verdade

    @property
    def espurio(self) -> bool:
        return self.verdade is None

    @property
    def certo(self) -> bool:
        return (self.verdade is not None
                and normalizar(self.palpite) == normalizar(self.verdade))


def colher(predictor, raiz=".", so=None, caminho="pagina"):
    """
    `[Recorte]` de todas as páginas rotuladas, na ordem das páginas.

    `caminho` escolhe **como os boxes nascem**, e a escolha muda a resposta:

    - `pagina` é o que o botão faz. `livro.caixas_e_diagramas` já tirou os
      respingos e o miolo dos diagramas antes de chamar o classificador, e o
      recorte sai pelo `vertical.recorte_de_pe`, com o endireitamento e o
      positivo do negativo.
    - `cru` é `generate_boxes_opencv` na página inteira, que é como
      `medir_paginas.py` e a calibração medem. Fica aqui para comparação: a
      diferença entre as duas colunas **é** o quanto a exclusão de diagrama já
      limpa a pilha, e medir na errada foi o primeiro erro desta fase.
    """
    from core import livro, vertical

    recortes = []
    for numero, (imagem, caminho_box) in enumerate(paginas_rotuladas(raiz)):
        nome = os.path.basename(imagem)
        if so and not any(s in nome for s in so):
            continue
        img = Image.open(imagem).convert("L")
        rotulados = carregar_box(caminho_box, img.size[1])
        if len(rotulados) < MIN_ROTULADOS:
            continue

        arr = np.array(img)
        if caminho == "pagina":
            boxes, _t, _e, _r, _c = livro.caixas_e_diagramas(
                arr, lambda r: predictor.predict(r) if r.size else ("", 0.0))
            crus = [vertical.recorte_de_pe(arr, b) for b in boxes]
        else:
            boxes = BoxService.generate_boxes_opencv(img, separar_colados=True)
            crus = [arr[b.y1:b.y2, b.x1:b.x2] for b in boxes]
        if not boxes:
            continue

        lidos = [predictor.predict(c) if c.size else ("", 0.0) for c in crus]
        for b, (char, _) in zip(boxes, lidos):
            b.char = char

        de_box = {}
        for i, j in comparar(boxes, rotulados).pares:
            de_box[i] = rotulados[j].char

        for i, cru in enumerate(crus):
            char, conf = lidos[i]
            if not char:
                continue
            recortes.append(Recorte(cru, char, conf, numero, de_box.get(i)))
        print(f"  {nome}: {len(boxes)} boxes, "
              f"{len(boxes) - len(de_box)} sem caractere rotulado")
    return recortes


# ----------------------------------------------------------------------
# Simular a coleta sem tocar em disco
# ----------------------------------------------------------------------

def simular(recortes, limiar, filtrar, deduplicar, teto=None,
            semente=coleta.SEMENTE_PADRAO):
    """
    O que a pasta teria, com estas chaves. Devolve (ficaram, contadores).

    Espelha `Coletor.__call__` na ordem exata — confiança, porta, dedução,
    teto — e é o único jeito honesto de comparar: um `Coletor` de verdade
    gravaria 250 mil PNG por linha da tabela.
    """
    import random

    from core.learner import char_to_folder

    sorteio = random.Random(semente)
    reserva, candidatos, impressoes = {}, Counter(), {}
    contas = Counter()

    for r in recortes:
        if limiar is not None and r.conf >= limiar:
            continue
        imagem = coleta._cinza(r.imagem)
        if imagem is None:
            continue
        if filtrar:
            motivo = coleta.motivo_de_recusa(imagem)
            if motivo:
                contas["recusado:" + motivo] += 1
                contas["recusado_espurio" if r.espurio
                       else "recusado_caractere"] += 1
                continue
        classe = char_to_folder(r.palpite)
        if deduplicar:
            chave = coleta._impressao(imagem)
            vistas = impressoes.setdefault(classe, set())
            if chave in vistas:
                contas["repetido"] += 1
                continue
            vistas.add(chave)

        lista = reserva.setdefault(classe, [])
        candidatos[classe] += 1
        if teto is None or len(lista) < teto:
            lista.append(r)
            continue
        j = sorteio.randrange(candidatos[classe])
        if j < teto:
            lista[j] = r
        else:
            contas["além do teto"] += 1

    ficaram = [r for lista in reserva.values() for r in lista]
    return ficaram, contas


def perfil(ficaram):
    """(certos, errados, espúrios) da pasta."""
    espurios = sum(1 for r in ficaram if r.espurio)
    certos = sum(1 for r in ficaram if r.certo)
    return certos, len(ficaram) - certos - espurios, espurios


def linha(titulo, ficaram, contas, largura=34):
    n = len(ficaram)
    certos, errados, espurios = perfil(ficaram)
    pct = (lambda x: f"{100.0 * x / n:5.1f}%") if n else (lambda x: "    —")
    extra = []
    if contas.get("repetido"):
        extra.append(f"{contas['repetido']} repetidos")
    if contas.get("recusado_espurio") or contas.get("recusado_caractere"):
        extra.append(f"porta: {contas.get('recusado_espurio', 0)} espúrios "
                     f"e {contas.get('recusado_caractere', 0)} caracteres fora")
    if contas.get("além do teto"):
        extra.append(f"{contas['além do teto']} além do teto")
    print(f"| {titulo:<{largura}} | {n:>6} | {pct(certos)} | {pct(errados)} | "
          f"{pct(espurios)} | {'; '.join(extra)}")


def cabecalho(largura=34):
    print(f"| {'modo':<{largura}} | {'na pasta':>6} | certos | errados | "
          f"espúrios | observações")
    print(f"|{'-' * (largura + 2)}|{'-' * 8}|{'-' * 8}|{'-' * 9}|"
          f"{'-' * 10}|{'-' * 20}")


# ----------------------------------------------------------------------
# A varredura da porta
# ----------------------------------------------------------------------

def varrer(recortes, limiar=None, predictor=None):
    """
    O custo e o benefício de cada régua da porta, uma de cada vez.

    Cada régua é medida **sozinha e varrida**, contra a coleta sem porta
    nenhuma: é o que a F47 cobrou e a F44 não fez — comparar uma régua nova
    contra a antiga inteira, e não contra um ponto dela.

    `limiar` restringe à pilha que aquele modo produz. A pergunta não é a mesma
    nas duas: em "todos" os espúrios são 6,6% e em "só os duvidosos" são a
    maioria, e uma régua pode servir a uma e não à outra.
    """
    if limiar is not None:
        recortes = [r for r in recortes if r.conf < limiar]
    imagens = [(coleta._cinza(r.imagem), r) for r in recortes]
    imagens = [(i, r) for i, r in imagens if i is not None]
    espurios = sum(1 for _, r in imagens if r.espurio)
    print(f"\n{len(imagens)} recortes, dos quais {espurios} não cercam "
          f"caractere nenhum ({100.0 * espurios / max(1, len(imagens)):.1f}%)\n")

    def tabela(titulo, reguas, corta):
        print(f"### {titulo}\n")
        print("| corte | espúrios pegos | caracteres perdidos | troca |")
        print("|---|---:|---:|---:|")
        for v in reguas:
            pegos = sum(1 for i, r in imagens if r.espurio and corta(i, r, v))
            perdidos = sum(1 for i, r in imagens
                           if not r.espurio and corta(i, r, v))
            troca = f"{pegos / perdidos:.1f}x" if perdidos else "—"
            print(f"| {v} | {pegos} ({100.0 * pegos / max(1, espurios):.1f}%) "
                  f"| {perdidos} | {troca} |")
        print()

    def lado(i):
        return min(i.shape[:2])

    def area(i):
        return int(i.shape[0]) * int(i.shape[1])

    def proporcao(i):
        """Quanto o recorte é mais comprido que largo, ou o contrário."""
        h, w = i.shape[:2]
        return max(h / max(1, w), w / max(1, h))

    tabela("Lado mínimo", [2, 3, 4, 5, 6, 8, 10],
           lambda i, r, v: lado(i) < v)
    tabela("Área mínima", [16, 36, 64, 100, 200, 400],
           lambda i, r, v: area(i) < v)
    tabela("Contraste mínimo", [10, 20, 25, 40, 60],
           lambda i, r, v: (int(i.max()) - int(i.min())) < v)
    tabela("Piso de tinta", [0.005, 0.02, 0.05, 0.10, 0.20],
           lambda i, r, v: coleta.fracao_de_tinta(i) < v)
    tabela("Teto de tinta", [0.98, 0.90, 0.80, 0.70, 0.60],
           lambda i, r, v: coleta.fracao_de_tinta(i) > v)
    tabela("Proporção máxima (comprido demais)", [10, 6, 4, 3, 2.5],
           lambda i, r, v: proporcao(i) > v)
    tabela("Confiança mínima", [0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90],
           lambda i, r, v: r.conf < v)

    if predictor is not None:
        margens = {id(r): predictor.margem_de_confianca(i) for i, r in imagens}
        tabela("Margem mínima (1 - p2/p1)", [0.05, 0.10, 0.20, 0.40, 0.60, 0.90],
               lambda i, r, v: margens[id(r)] < v)

    def faixa(nome, de):
        v = np.array([de(i, r) for i, r in imagens], dtype=float)
        marca = np.array([r.espurio for _, r in imagens])
        if not marca.any() or marca.all():
            return
        print(f"{nome}: caractere mediana {np.median(v[~marca]):.4f} "
              f"(p05 {np.percentile(v[~marca], 5):.4f}, "
              f"p95 {np.percentile(v[~marca], 95):.4f}), "
              f"espúrio mediana {np.median(v[marca]):.4f}")

    faixa("lado", lambda i, r: lado(i))
    faixa("área", lambda i, r: area(i))
    faixa("contraste", lambda i, r: int(i.max()) - int(i.min()))
    faixa("tinta", lambda i, r: coleta.fracao_de_tinta(i))
    faixa("proporção", lambda i, r: proporcao(i))
    faixa("confiança", lambda i, r: r.conf)


# ----------------------------------------------------------------------

def espalhamento(ficaram, classes_de_interesse, de_classe):
    """
    Mediana de páginas distintas **por classe** entre as classes que encheram.

    Contar páginas distintas na pasta inteira não mede nada: com 200 classes e
    10 páginas, qualquer amostra toca as 10. O viés do teto é **dentro** da
    classe — 30 `e` do primeiro-a-chegar saem todos da página 1 —, e é por
    classe que ele tem de ser contado.
    """
    por_classe = {}
    for r in ficaram:
        c = de_classe(r)
        if c in classes_de_interesse:
            por_classe.setdefault(c, set()).add(r.pagina)
    if not por_classe:
        return 0.0, 0
    valores = sorted(len(v) for v in por_classe.values())
    return float(np.median(valores)), min(valores)


def medir_deducao_em_pdf(caminho, paginas, predictor):
    """
    Quanto a dedução colapsa num PDF **digital** — o caso para que ela existe.

    Nas páginas rotuladas ela tira ~10%, e o número engana: elas são JPG de
    scan, em que o mesmo glifo nunca sai duas vezes com os mesmos pixels. Num
    PDF de texto renderizado a dpi fixo, sai — e é ali que a pasta enchia de
    cópias.
    """
    import fitz

    from core import livro

    doc = fitz.open(caminho)
    try:
        alvo = min(paginas, doc.page_count)
        print(f"\n## Dedução em {os.path.basename(caminho)} "
              f"({alvo} página(s))\n")
        cru = coleta.Coletor(pasta=os.devnull, limiar=None, deduplicar=False)
        # Não grava nada: o que interessa é a contagem, e o disco é o que
        # tornaria isto caro. `_gravar` devolve um caminho falso.
        for c in (cru,):
            c._gravar = lambda imagem, classe, conf, pag: "(memória)"
        deduzido = coleta.Coletor(pasta=os.devnull, limiar=None)
        deduzido._gravar = lambda imagem, classe, conf, pag: "(memória)"

        for n in range(alvo):
            for c in (cru, deduzido):
                livro.extrair_pagina(doc[n], predictor.predict, numero=n,
                                     conf_minima=0.0, coletor=c,
                                     diagramas="recorte")
        print("| coleta | na pasta | repetidos |")
        print("|---|---:|---:|")
        print(f"| sem dedução | {cru.total} | — |")
        corte = (100.0 * deduzido.ignorados_por_repeticao
                 / max(1, cru.total))
        print(f"| com dedução | {deduzido.total} | "
              f"{deduzido.ignorados_por_repeticao} ({corte:.1f}%) |")
    finally:
        doc.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--so", nargs="+", help="só páginas cujo nome contenha isto")
    ap.add_argument("--varrer", action="store_true",
                    help="a varredura dos limiares da porta")
    ap.add_argument("--limiar", type=float,
                    help="varrer só a pilha abaixo desta confiança")
    ap.add_argument("--caminho", choices=("pagina", "cru"), default="pagina",
                    help="como os boxes nascem; ver `colher`")
    ap.add_argument("--teto", type=int, default=30,
                    help="teto por classe usado na comparação do sorteio")
    ap.add_argument("--pdf", help="um PDF digital, para medir a dedução nele")
    ap.add_argument("--paginas", type=int, default=8,
                    help="quantas páginas do --pdf")
    args = ap.parse_args()

    from core.neural_trainer import NeuralPredictor

    predictor = NeuralPredictor()
    if not predictor.load():
        print("Modelo não carregou — esta medição precisa dele.")
        return 1

    print("Colhendo as páginas rotuladas...")
    recortes = colher(predictor, so=args.so, caminho=args.caminho)
    if not recortes:
        print("Nenhuma página rotulada encontrada.")
        return 1
    paginas = len({r.pagina for r in recortes})
    espurios = sum(1 for r in recortes if r.espurio)
    print(f"\n{len(recortes)} recortes em {paginas} páginas; "
          f"{espurios} não cercam caractere.\n")

    if args.varrer:
        varrer(recortes, limiar=args.limiar, predictor=predictor)
        return 0

    for nome, limiar in (("todos", None), ("só os duvidosos", 0.5)):
        print(f"\n## {nome}\n")
        cabecalho()
        for titulo, filtrar, dedup in (
                ("hoje (sem porta, sem dedução)", False, False),
                ("com a porta (medida, e desligada)", True, False),
                ("com a dedução (F93)", False, True)):
            ficaram, contas = simular(recortes, limiar, filtrar, dedup)
            linha(titulo, ficaram, contas)
        print()

    from core.learner import char_to_folder

    de_classe = lambda r: char_to_folder(r.palpite)
    base, _ = simular(recortes, None, False, True)
    candidatos = Counter(de_classe(r) for r in base)
    cheias = {c for c, n in candidatos.items() if n > args.teto}
    print(f"\n## O viés do teto (teto de {args.teto} por classe, modo 'todos')\n")
    print(f"{len(cheias)} classe(s) passam do teto, de {len(candidatos)}; "
          f"o livro tem {paginas} páginas.\n")
    print("| teto | na pasta | páginas por classe (mediana) | a pior classe |")
    print("|---|---:|---:|---:|")
    mediana, pior = espalhamento(base, cheias, de_classe)
    print(f"| sem teto | {len(base)} | {mediana:.0f} | {pior} |")

    # Primeiro-a-chegar: o comportamento anterior à F93, reconstruído aqui
    # porque o `Coletor` já não sabe fazê-lo.
    primeiros, contagem = [], Counter()
    for r in base:
        c = de_classe(r)
        if contagem[c] < args.teto:
            contagem[c] += 1
            primeiros.append(r)
    mediana, pior = espalhamento(primeiros, cheias, de_classe)
    print(f"| primeiro-a-chegar | {len(primeiros)} | {mediana:.0f} | {pior} |")

    sorteado, _ = simular(recortes, None, False, True, teto=args.teto)
    mediana, pior = espalhamento(sorteado, cheias, de_classe)
    print(f"| sorteado (F93) | {len(sorteado)} | {mediana:.0f} | {pior} |")

    if args.pdf:
        medir_deducao_em_pdf(args.pdf, args.paginas, predictor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
