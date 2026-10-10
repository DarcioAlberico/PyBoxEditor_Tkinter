"""
Mede o leitor de diagramas contra tabuleiros que ele nunca viu treinando (F8.4).

O número que o `treinar_diagrama.py` imprime separa por **diagrama**, e o
relatório dele diz, desde a F7.4, que aquilo continua otimista: os diagramas de
teste vêm dos mesmos livros que os de treino, e livro novo traz outra fonte de
peças. Faltava material para medir isso — e é o que o corpus da F8.4 trouxe.

Este script mede no split `test` do corpus, que `importar_diagramas.py` deixa de
fora da importação de propósito. São livros e fontes que não entraram na base.

    python medir_diagramas.py
    python medir_diagramas.py --modelo /tmp/candidato.pth
    python medir_diagramas.py --quantos 100        # varredura rápida

As três perguntas saem separadas porque falham por motivos diferentes:

    ocupação    há peça nesta casa?     (a rede da F7.5)
    identidade  qual peça é?            (a rede da F7.4)
    tabuleiro   as 64 casas certas      o que o usuário vê

A identidade é medida **só onde as duas concordam que há peça**: misturá-la com
a ocupação daria um número que sobe quando a outra rede melhora, e o histórico do
projeto já mostrou o que um número assim esconde (F1.3).
"""

import argparse
import collections
import csv
import os
import sys

import numpy as np
from PIL import Image

from core import diagrama as diag

PASTA_CORPUS = "Diagramas-outro-projeto"


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


def tabuleiros_de_teste(pasta: str = PASTA_CORPUS):
    """[(caminho, fen)] do split que nunca entrou em treino nenhum."""
    with open(os.path.join(pasta, "data", "splits.csv"), encoding="utf-8") as f:
        teste = {r["filename"] for r in csv.DictReader(f) if r["split"] == "test"}
    with open(os.path.join(pasta, "data", "labels.csv"), encoding="utf-8") as f:
        return [(os.path.join(pasta, "samples", r["filename"]), r["fen"])
                for r in csv.DictReader(f)
                if r["filename"] in teste and r["fen"].strip()]


class Resultado:
    """O que uma passada apurou."""

    def __init__(self):
        self.casas = self.certas = 0
        self.ocup_ok = self.falso_pos = self.omissao = 0
        self.ident_ok = self.ident_total = 0
        self.tabuleiros = self.perfeitos = 0
        self.confusao = collections.Counter()

    @property
    def ocupacao(self):
        return self.ocup_ok / max(1, self.casas)

    @property
    def identidade(self):
        return self.ident_ok / max(1, self.ident_total)

    @property
    def inteiros(self):
        return self.perfeitos / max(1, self.tabuleiros)

    def texto(self):
        return (f"{self.tabuleiros} tabuleiros, {self.casas} casas\n"
                f"  ocupação (há peça?)     {self.ocupacao:7.2%}"
                f"   {self.falso_pos} falsos positivos, {self.omissao} omissões\n"
                f"  identidade (qual peça?) {self.identidade:7.2%}"
                f"   ({self.ident_total} casas com peça nas duas)\n"
                f"  tabuleiro inteiro certo {self.inteiros:7.2%}"
                f"   ({self.perfeitos} de {self.tabuleiros})")


def medir(itens, progresso=None) -> Resultado:
    r = Resultado()
    for n, (caminho, fen) in enumerate(itens):
        if not os.path.exists(caminho):
            continue
        arr = np.array(Image.open(caminho).convert("L"))
        verdade = casas_do_fen(fen)
        leitura = diag.ler(arr)
        r.tabuleiros += 1

        perfeito = True
        for casa in leitura.casas:
            v = verdade.get((casa.linha, casa.coluna))
            r.casas += 1
            if casa.simbolo == v:
                r.certas += 1
            else:
                perfeito = False
                r.confusao[(v or ".", casa.simbolo or ".")] += 1
            if bool(casa.simbolo) == bool(v):
                r.ocup_ok += 1
            elif casa.simbolo:
                r.falso_pos += 1
            else:
                r.omissao += 1
            if v and casa.simbolo:
                r.ident_total += 1
                r.ident_ok += casa.simbolo == v
        r.perfeitos += perfeito
        if progresso and (n + 1) % 100 == 0:
            progresso(f"  {n + 1} tabuleiros...")
    return r


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("--corpus", default=PASTA_CORPUS)
    p.add_argument("--modelo", help="usa este .pth em vez do modelo instalado")
    p.add_argument("--quantos", type=int, default=0,
                   help="mede só os N primeiros (varredura rápida)")
    args = p.parse_args(argv)

    if not os.path.isdir(os.path.join(args.corpus, "samples")):
        print(f"corpus não encontrado em {args.corpus}", file=sys.stderr)
        return 1

    if args.modelo:
        diag.CAMINHO_MODELO = args.modelo
        diag.esquecer_modelo()

    itens = tabuleiros_de_teste(args.corpus)
    if args.quantos:
        itens = itens[:args.quantos]

    print(f"modelo: {diag.CAMINHO_MODELO}")
    r = medir(itens, progresso=print)
    print("\n" + r.texto())
    print("\n  piores confusões (verdade -> lido):")
    for (v, l), n in r.confusao.most_common(10):
        print(f"    {v} -> {l}   {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
