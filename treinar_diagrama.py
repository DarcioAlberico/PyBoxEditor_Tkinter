"""
Constrói os modelos que leem os diagramas (F7.1, F8.3, F7.4, F7.5).

    python treinar_diagrama.py
    python treinar_diagrama.py --conferir      # só a conferência da base
    python treinar_diagrama.py --rapido        # sem medir (uma rede em vez de duas)

**São dois modelos, de duas bases**, e a separação foi medida:

    training_data_diagrama/  ->  diagrama_modelo.pth   qual peça é (F7.4)
    training_data_ocupacao/  ->  ocupacao_modelo.pth   há peça?    (F7.5)

As amostras são **resíduos** — a casa menos o fundo estimado daquele diagrama —,
gravadas deslocadas de 128 para poderem ser olhadas como imagem. Ver
`core/diagrama.py` para o porquê do resíduo.

**Era um banco de vizinhos, e virou uma rede na F7.4.** O argumento contra a
rede estava escrito aqui — "são poucas centenas de amostras de dois livros, e
uma rede treinada nisso decoraria" — e a medição o desmentiu: deixando um livro
inteiro de fora do treino, o banco de vizinhos faz 86,9% e a rede 98,0%. A
vantagem **cresce** no teste difícil, que é o contrário do que a decoreba
produziria.

Demora ~40 s em CPU, contra os ~2 s do banco de vizinhos, e a maior parte disso
é a segunda rede — a que mede. Com `--rapido` cai pela metade e o relatório diz
que não mediu.

**A implementação mora em `core/treino_diagrama.py`**, e não aqui: desde a F8.3
o programa também treina de dentro (Ferramentas → "Treinar modelo de
diagramas..."), e duas implementações do mesmo treino é a família de defeito
que a F5.2 documenta.
"""

import argparse
import sys

from core import treino_diagrama


def main(argv=None):
    p = argparse.ArgumentParser(description="Treina o modelo de diagramas.")
    # Vários caminhos desde a F8.4: a base conferida à mão e a importada do
    # corpus moram separadas. Sem `--pasta`, entram as que existirem.
    p.add_argument("--pasta", nargs="+", default=None)
    # As duas bases andam juntas aqui e separadas no `treinar`: apontar uma sem
    # a outra desliga a segunda, para um teste com base própria não regravar o
    # modelo de verdade. Da linha de comando, quem aponta uma quase sempre quer
    # as duas, então o padrão as mantém emparelhadas.
    p.add_argument("--pasta-ocupacao", dest="pasta_ocupacao",
                   default=treino_diagrama.PASTA_OCUPACAO)
    p.add_argument("--conferir", action="store_true",
                   help="só confere a base, sem treinar")
    p.add_argument("--rapido", action="store_true",
                   help="pula a medição (treina uma rede em vez de duas)")
    args = p.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    if args.conferir:
        problemas = treino_diagrama.conferir(args.pasta)
        for problema in problemas:
            print(problema)
        if not problemas:
            print("base sem problemas")
        return 1 if any(p.grave for p in problemas) else 0

    pastas = treino_diagrama._pastas(args.pasta)
    print("amostras de peça em: " + ", ".join(pastas), flush=True)
    relatorio = treino_diagrama.treinar(args.pasta, medir=not args.rapido,
                                        progresso=lambda m: print(m, flush=True),
                                        pasta_ocupacao=args.pasta_ocupacao)
    if not relatorio.total:
        print("nenhuma amostra em " + ", ".join(p + "/" for p in pastas))
        return 1

    print(relatorio.texto())
    return 0


if __name__ == "__main__":
    sys.exit(main())
