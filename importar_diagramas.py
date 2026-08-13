"""
Importa um corpus de tabuleiros rotulados por FEN para a base de amostras (F8.4).

O corpus veio de outro projeto de OCR de diagramas: um PNG por tabuleiro, já
recortado na borda, mais um `labels.csv` com o FEN de cada um. Aqui ele vira
resíduo por casa — o formato que `core/treino_diagrama.py` grava e lê.

    python importar_diagramas.py --conferir
    python importar_diagramas.py --limite 1200
    python importar_diagramas.py                      # tudo

## A base do corpus é separada da nossa, e de propósito

Nossa base é conferida à mão, tem 1.649 amostras e **viaja no repositório**. A do
corpus tem 51 mil e é material derivado de livro com copyright, como os scans que
o `.gitignore` já manda para fora. Misturá-las apagaria a única pergunta que
interessa quando o número muda: veio da amostra que o revisor sustentou ou do
lote importado? É a mesma separação que o léxico faz entre `palavras` e
`do_usuario` (F9.2).

`treinar(pastas=[...])` lê as duas juntas.

## Só as peças, e o motivo está medido

O corpus traz 51.589 peças e 168.507 casas vazias. As vazias **não** entram: a
rede de ocupação já acerta 99,8% neste mesmo corpus (medido antes de importar
nada), enquanto a de identidade cai para 76,7%. Importar 168 mil amostras para a
pergunta que já está resolvida custaria toda a memória do treino e não moveria o
número que está errado.

## O tabuleiro que a ocupação desmente não entra

O rótulo do corpus é FEN, e parte dele veio de leitura automática revisada. A
rede de ocupação é o conferidor disponível e é **independente** do que se quer
aprender: ela diz se há peça, não qual. Onde ela discorda do FEN em muitas casas,
ou o recorte está torto ou o rótulo está errado — e amostra torta rotulada com
segurança é o defeito da F1.4, que não avisa que está errada.
"""

import argparse
import collections
import csv
import hashlib
import os
import sys

import numpy as np
from PIL import Image

from core import diagrama as diag
from core import treino_diagrama as treino

#: Onde o corpus foi despejado.
PASTA_CORPUS = "Diagramas-outro-projeto"

#: Onde as amostras importadas moram. Fora do git, como os scans. O nome mora
#: no `treino_diagrama` porque é ele quem precisa achar a pasta sozinho.
DESTINO_PADRAO = treino.PASTA_CORPUS

#: Quantas casas a ocupação pode discordar do FEN antes de o tabuleiro ser
#: recusado. Medido no corpus: a rede erra 0,2% das casas, ou ~0,13 por
#: tabuleiro, então 3 é folga larga para o ruído e ainda pega o recorte torto,
#: onde a discordância vai a dezenas.
MAX_DISCORDANCIA = 3


def casas_do_fen(fen: str) -> dict:
    """`{(linha, coluna): símbolo ou None}` — linha 0 é a 8a fila, como `Casa`."""
    tabuleiro = {}
    for linha, fila in enumerate(fen.split()[0].split("/")):
        coluna = 0
        for ch in fila:
            if ch.isdigit():
                for _ in range(int(ch)):
                    tabuleiro[(linha, coluna)] = None
                    coluna += 1
            else:
                tabuleiro[(linha, coluna)] = ch
                coluna += 1
    return tabuleiro


def nome_da_casa(linha: int, coluna: int) -> str:
    return f"{'abcdefgh'[coluna]}{8 - linha}"


def _digest(pasta: str, arquivo: str):
    """Resumo do conteúdo da imagem, ou None se ela não existir."""
    caminho = os.path.join(pasta, "samples", arquivo)
    if not os.path.exists(caminho):
        return None
    with open(caminho, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _sem_repetidos(pasta: str, linhas):
    """
    Uma linha por imagem. Devolve `(linhas, motivos dos descartes)`.

    **O corpus tem a mesma imagem sob nomes diferentes**: 3.439 linhas para 3.264
    imagens distintas, 164 delas repetidas. Duas razões para não deixar passar:

    - **O gêmeo fura a separação por diagrama.** `grupo_da_amostra` agrupa pela
      marca da procedência, e dois nomes diferentes são dois grupos: as mesmas
      casas poderiam cair uma no treino e outra no teste, que é exatamente o que
      a F7.4 mediu inflando o número.
    - **Onde os FENs discordam, nenhum dos dois se sustenta.** Aconteceu uma vez
      no corpus, com o `c2` de uma posição lido como bispo numa linha e peão na
      outra — e é peão. A ocupação não pega esse caso: as duas dizem "ocupada".
      Rótulo contraditório é o defeito da F1.4, e `conferir` o classifica como
      erro **grave**; deixá-lo entrar treinaria o alarme a ser ignorado.

    Quando os rótulos concordam fica a primeira; quando discordam **saem todas**,
    porque não há como saber qual está certa.
    """
    por_conteudo = collections.OrderedDict()
    for linha in linhas:
        digest = _digest(pasta, linha[0])
        if digest is not None:
            por_conteudo.setdefault(digest, []).append(linha)

    saida, descartes = [], []
    for grupo in por_conteudo.values():
        posicoes = {l[1].split()[0] for l in grupo}
        if len(posicoes) > 1:
            descartes += [(l[0], "mesma imagem com FEN conflitante")
                          for l in grupo]
            continue
        saida.append(grupo[0])
        descartes += [(l[0], "imagem repetida") for l in grupo[1:]]
    return saida, descartes


def carregar_indice(pasta: str):
    """[(arquivo, fen, split)] do corpus, sem os tabuleiros em quarentena."""
    caminho = os.path.join(pasta, "data", "labels.csv")
    splits = {}
    cs = os.path.join(pasta, "data", "splits.csv")
    if os.path.exists(cs):
        with open(cs, encoding="utf-8") as f:
            splits = {r["filename"]: r["split"] for r in csv.DictReader(f)}

    quarentena = set()
    cq = os.path.join(pasta, "data", "quarantine.csv")
    if os.path.exists(cq):
        with open(cq, encoding="utf-8") as f:
            quarentena = {r["filename"] for r in csv.DictReader(f)}

    with open(caminho, encoding="utf-8") as f:
        return [(r["filename"], r["fen"], splits.get(r["filename"], "train"))
                for r in csv.DictReader(f)
                if r["filename"] not in quarentena and r["fen"].strip()]


def residuos_do_tabuleiro(caminho: str):
    """(resíduo por casa, ocupada por casa) de um PNG de tabuleiro."""
    arr = np.array(Image.open(caminho).convert("L"))
    return diag.residuos(arr)


def importar(pasta_corpus: str = PASTA_CORPUS, destino: str = DESTINO_PADRAO,
             limite: int = 0, incluir_teste: bool = False,
             conferir_so: bool = False, progresso=print) -> dict:
    """
    Grava as amostras de peça do corpus. Devolve o resumo.

    `limite` é o teto **por classe**, e o corte não é o começo da lista: os
    tabuleiros são percorridos intercalados por dia de captura, que é o proxy de
    livro disponível. Cortar em ordem daria mil peões de um livro só, que é o
    contrário do que falta — o corpus vale pelas fontes que a nossa base não tem.
    """
    indice = carregar_indice(pasta_corpus)

    # O que o `medir_diagramas.py` vai medir, lido do índice **inteiro** e por
    # conteúdo. Antes da deduplicação de propósito: ela colapsaria a cópia de
    # teste na de treino, e a imagem entraria pelo lado errado justamente no
    # caso que isto existe para impedir. O corpus de hoje não tem nenhum, mas
    # medição com vazamento não avisa que está inflada.
    de_teste = set()
    if not incluir_teste:
        de_teste = {_digest(pasta_corpus, t[0])
                    for t in indice if t[2] == "test"} - {None}

    indice, recusados = _sem_repetidos(pasta_corpus, indice)
    if not incluir_teste:
        recusados += [(t[0], "imagem também no split de teste") for t in indice
                      if _digest(pasta_corpus, t[0]) in de_teste]
        indice = [t for t in indice
                  if _digest(pasta_corpus, t[0]) not in de_teste]

    por_dia = collections.OrderedDict()
    for item in indice:
        por_dia.setdefault(item[0][6:14], []).append(item)
    intercalado = [t for grupo in zip(*_igualar(list(por_dia.values())))
                   for t in grupo if t is not None]

    conta = collections.Counter()
    gravados = 0
    lidos = 0

    for arquivo, fen, _split in intercalado:
        if limite and all(conta[s] >= limite for s in diag.SIMBOLOS):
            break
        caminho = os.path.join(pasta_corpus, "samples", arquivo)
        if not os.path.exists(caminho):
            continue

        verdade = casas_do_fen(fen)
        residuo, ocupada = residuos_do_tabuleiro(caminho)
        if not residuo:
            recusados.append((arquivo, "recorte pequeno demais"))
            continue

        discorda = sum(1 for k in residuo
                       if bool(ocupada.get(k)) != bool(verdade.get(k)))
        if discorda > MAX_DISCORDANCIA:
            recusados.append((arquivo, f"ocupação discorda em {discorda} casas"))
            continue

        lidos += 1
        origem = os.path.splitext(arquivo)[0]
        for (linha, coluna), simbolo in sorted(verdade.items()):
            if not simbolo or (limite and conta[simbolo] >= limite):
                continue
            conta[simbolo] += 1
            if conferir_so:
                continue
            if treino.gravar(residuo[(linha, coluna)], simbolo, origem,
                             nome_da_casa(linha, coluna), destino):
                gravados += 1
        if lidos % 200 == 0:
            progresso(f"  {lidos} tabuleiros, {sum(conta.values())} peças...")

    return {"tabuleiros": lidos, "amostras": sum(conta.values()),
            "gravados": gravados, "por_classe": dict(conta),
            "recusados": recusados, "candidatos": len(intercalado)}


def _igualar(grupos):
    """Grupos do mesmo comprimento, completados com None — para intercalar."""
    maior = max((len(g) for g in grupos), default=0)
    return [g + [None] * (maior - len(g)) for g in grupos]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--corpus", default=PASTA_CORPUS)
    p.add_argument("--destino", default=DESTINO_PADRAO)
    p.add_argument("--limite", type=int, default=0,
                   help="teto de amostras por classe (0 = sem teto)")
    p.add_argument("--incluir-teste", action="store_true",
                   help="importa também o split de teste do outro projeto")
    p.add_argument("--conferir", action="store_true",
                   help="conta sem gravar nada")
    args = p.parse_args(argv)

    if not os.path.isdir(os.path.join(args.corpus, "samples")):
        print(f"corpus não encontrado em {args.corpus}", file=sys.stderr)
        return 1

    print(f"lendo {args.corpus}...")
    r = importar(args.corpus, args.destino, args.limite, args.incluir_teste,
                 args.conferir)

    print(f"\n{r['tabuleiros']} tabuleiros aceitos de {r['candidatos']} "
          f"candidatos, {r['amostras']} peças")
    print("  " + "  ".join(f"{s}:{r['por_classe'].get(s, 0)}"
                           for s in "PNBRQKpnbrqk"))
    if r["recusados"]:
        motivos = collections.Counter(m.split(" em ")[0] for _, m in r["recusados"])
        print(f"  {len(r['recusados'])} tabuleiros recusados: {dict(motivos)}")
        for arquivo, motivo in r["recusados"][:5]:
            print(f"    {arquivo}: {motivo}")
    if args.conferir:
        print("\n--conferir: nada foi gravado.")
    else:
        print(f"\n{r['gravados']} PNGs em {args.destino}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
