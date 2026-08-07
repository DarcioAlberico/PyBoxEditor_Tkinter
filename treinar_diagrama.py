"""
Constrói o modelo que lê as peças dos diagramas (F7.1, F8.3, F7.4).

    python treinar_diagrama.py
    python treinar_diagrama.py --conferir      # só a conferência da base
    python treinar_diagrama.py --rapido        # sem medir (uma rede em vez de duas)

Lê as amostras rotuladas de `training_data_diagrama/` e grava
`core/dados/diagrama_modelo.pth`. As amostras são **resíduos** — a casa menos o
fundo estimado daquele diagrama —, gravadas deslocadas de 128 para poderem ser
olhadas como imagem. Ver `core/diagrama.py` para o porquê do resíduo.

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
    p.add_argument("--pasta", default=treino_diagrama.PASTA_PADRAO)
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

    relatorio = treino_diagrama.treinar(args.pasta, medir=not args.rapido,
                                        progresso=lambda m: print(m, flush=True))
    if not relatorio.total:
        print(f"nenhuma amostra em {args.pasta}/")
        return 1

    print(relatorio.texto())
    return 0


if __name__ == "__main__":
    sys.exit(main())
