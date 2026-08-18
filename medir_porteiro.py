"""
Quanto vale o porteiro que decide entre desenhar o diagrama e recortá-lo (F58).

A F58 troca o recorte do scan por um desenho feito a partir do FEN que o nosso
leitor extraiu. O ganho é óbvio; o risco é que **o render mente bem**: quando o
modelo erra uma casa, o desenho sai com a mesma nitidez nas outras 63 e nada
denuncia o erro. A F8.4 mediu 92,49% de tabuleiro inteiro certo em livros fora
do treino — um em treze.

Daí o porteiro: renderiza quem passa, recorta quem não passa. Este script mede
**que régua** e **que corte**, sobre os mesmos 346 tabuleiros do split `test` do
corpus da F8.4, que nunca entraram em treino nenhum.

As réguas candidatas não pedem modelo novo nem rótulo novo: são sinais que a
`diagrama.ler` já produz e descarta. Todas são "maior é mais confiável", para
que a regra seja sempre a mesma — barrar quem fica abaixo do corte.

    python medir_porteiro.py
    python medir_porteiro.py --quantos 100        # varredura rápida
    python medir_porteiro.py --regua "a menor das duas, zerada se implausível"

Duas colunas mandam na leitura da tabela:

    escapam   tabuleiros errados que o porteiro deixou virar desenho. É o custo
              que não se vê, e o que esta fase existe para reduzir
    perdidos  tabuleiros certos que ele mandou para o recorte. É o custo que se
              vê, e ele é pequeno: um recorte de scan, que é o que o livro já
              exportava antes desta fase
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import diagrama as diag
# A conta da separação é a da F51 e tem dono: `medir_cadeia`. Importá-la custa
# dois segundos de import e evita uma segunda definição da mesma coisa — que é
# como a F17 resolveu a duplicação da quebra em linhas.
from medir_cadeia import _separacao as separacao
from medir_diagramas import PASTA_CORPUS, casas_do_fen, tabuleiros_de_teste

#: Os cortes varridos. O fim da escala é varrido fino porque é onde a faixa útil
#: está: a rede é calibrada por temperatura (F2.7) e ainda assim mora perto de 1,
#: e entre 0,99 e 1,00 cabe mais decisão do que entre 0,50 e 0,99.
CORTES = (0.0, 0.50, 0.70, 0.80, 0.90, 0.95, 0.98, 0.99, 0.995, 0.998, 0.999,
          0.9995, 0.9999, 1.0)


def _console_em_utf8():
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


# ----------------------------------------------------------------------
# As réguas
# ----------------------------------------------------------------------

def sinais(leitura) -> dict:
    """
    Todas as réguas candidatas para uma leitura, no mesmo sentido.

    A confiança da peça só existe onde há peça; a da ocupação existe nas 64
    casas. Misturar as duas numa média esconderia a pior, que é justamente a
    que interessa — um tabuleiro só está certo se as 64 casas estiverem.
    """
    pecas = [c.confianca for c in leitura.casas if c.simbolo]
    ocupacao = [c.confianca_ocupacao for c in leitura.casas]

    pior_peca = min(pecas) if pecas else 0.0
    pior_ocupacao = min(ocupacao) if ocupacao else 0.0
    menor_das_duas = min(pior_peca, pior_ocupacao)
    plausivel = 1.0 if leitura.plausivel else 0.0
    intacta = 1.0 if not leitura.arbitradas else 0.0

    return {
        "confiança da peça, a pior casa": pior_peca,
        "confiança da ocupação, a pior casa": pior_ocupacao,
        "a menor das duas": menor_das_duas,
        "confiança da peça, a média": float(np.mean(pecas)) if pecas else 0.0,
        "posição plausível": plausivel,
        "nada foi arbitrado": intacta,
        "a menor das duas, zerada se implausível": menor_das_duas * plausivel,
        "a menor das duas, zerada se implausível ou arbitrada":
            menor_das_duas * plausivel * intacta,
    }


REGUAS = list(sinais(diag.Leitura(caixa=(0, 0, 0, 0))))


# ----------------------------------------------------------------------
# A passada
# ----------------------------------------------------------------------

def avaliar(itens, progresso=None) -> list:
    """[{régua: nota, ..., 'certo': bool}] — uma linha por tabuleiro."""
    linhas = []
    for n, (caminho, fen) in enumerate(itens):
        if progresso:
            progresso(n, len(itens))
        if not os.path.exists(caminho):
            continue
        arr = np.array(Image.open(caminho).convert("L"))
        verdade = casas_do_fen(fen)
        leitura = diag.ler(arr)
        certo = all(casa.simbolo == verdade.get((casa.linha, casa.coluna))
                    for casa in leitura.casas)
        # A decisão de produção vem do `diagrama.confiavel`, e não de uma cópia
        # da regra aqui dentro — é a trava da F52: instrumento que reimplementa
        # o que mede acaba medindo a si mesmo.
        passa, _motivo = diag.confiavel(leitura)
        linhas.append(dict(sinais(leitura), certo=certo, passa=passa))
    return linhas


def tabela_de_separacao(linhas) -> list:
    """[(régua, separação)] — a curva inteira num número, por régua."""
    saida = []
    for regua in REGUAS:
        errados = [linha[regua] for linha in linhas if not linha["certo"]]
        certos = [linha[regua] for linha in linhas if linha["certo"]]
        saida.append((regua, separacao(errados, certos)))
    return saida


def tabela_de_operacao(linhas, regua: str, cortes=CORTES) -> list:
    """
    [(corte, barrados, pegos, escapam, perdidos)] para uma régua.

    Barra quem fica **abaixo** do corte, então `corte=0.0` é não ter porteiro e
    `corte=1.0` é não confiar em nada.
    """
    errados = sum(1 for linha in linhas if not linha["certo"])
    saida = []
    for corte in cortes:
        barrados = pegos = 0
        for linha in linhas:
            if linha[regua] < corte:
                barrados += 1
                pegos += not linha["certo"]
        saida.append((corte, barrados, pegos, errados - pegos, barrados - pegos))
    return saida


# ----------------------------------------------------------------------

def main() -> int:
    _console_em_utf8()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--corpus", default=PASTA_CORPUS)
    ap.add_argument("--quantos", type=int, default=0, help="0 = todos")
    ap.add_argument("--regua", default=None,
                    help="a régua da tabela de operação (padrão: as três de maior separação)")
    ap.add_argument("--csv", default=None,
                    help="grava os sinais por tabuleiro, para reexaminar a escolha "
                         "sem repetir a passada")
    args = ap.parse_args()

    itens = tabuleiros_de_teste(args.corpus)
    if args.quantos:
        itens = itens[:args.quantos]
    print(f"{len(itens)} tabuleiros do split test de {args.corpus}\n")

    def progresso(n, total):
        if n and n % 25 == 0:
            print(f"  ... {n}/{total}", end="\r", flush=True)

    linhas = avaliar(itens, progresso)
    certos = sum(1 for linha in linhas if linha["certo"])
    errados = len(linhas) - certos
    print(f"sem porteiro: {certos / max(1, len(linhas)):.2%} de tabuleiro "
          f"inteiro certo — {errados} dos {len(linhas)} sairiam errados\n")

    if not errados:
        print("nenhum tabuleiro errado nesta amostra: não há o que separar")
        return 0

    print(f"{'régua':<52}{'separação':>11}")
    print("-" * 63)
    ordenadas = sorted(tabela_de_separacao(linhas), key=lambda p: -p[1])
    for regua, valor in ordenadas:
        print(f"{regua:<52}{valor:>11.4f}")
    print("\nseparação 0,50 é moeda: a régua não sabe quando o tabuleiro está "
          "errado")

    escolhidas = [args.regua] if args.regua else [r for r, _s in ordenadas[:3]]
    for regua in escolhidas:
        print(f"\ntabela de operação — {regua}")
        print(f"{'corte':>8}{'barrados':>10}{'pegos':>8}{'escapam':>9}"
              f"{'perdidos':>10}{'   dos certos':>14}")
        print("-" * 63)
        for corte, barrados, pegos, escapam, perdidos in tabela_de_operacao(
                linhas, regua):
            print(f"{corte:>8.4f}{barrados:>10}{pegos:>8}{escapam:>9}"
                  f"{perdidos:>10}{perdidos / max(1, certos):>13.1%}")
    print("\npegos + escapam = os tabuleiros errados; perdidos são os certos que "
          "\nforam para o recorte, que é o que o livro já exportava antes da F58")

    barrados = sum(1 for linha in linhas if not linha["passa"])
    pegos = sum(1 for linha in linhas if not linha["passa"] and not linha["certo"])
    print(f"\no porteiro de produção (`diagrama.confiavel`, piso "
          f"{diag.PISO_DO_PORTEIRO}) barra {barrados}: pega {pegos} dos "
          f"{errados} errados, deixa escapar {errados - pegos}, e manda "
          f"{barrados - pegos} certos para o recorte "
          f"({(barrados - pegos) / max(1, certos):.1%} deles)")

    if args.csv:
        import csv
        with open(args.csv, "w", encoding="utf-8", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=REGUAS + ["certo", "passa"])
            escritor.writeheader()
            escritor.writerows(linhas)
        print(f"\nsinais por tabuleiro: {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
