"""
Importa a lista de palavras do ABBYY FineReader para `assets/lexico/` (F9.1).

    python importar_lexico.py                       # de "Lista de Palavras/"
    python importar_lexico.py --origem <pasta>
    python importar_lexico.py --texto               # sem gzip, para inspecionar

Produz dois arquivos, e a divisão não é arrumação — é o desenho da SPEC §5.8:

    assets/lexico/en.txt.gz       73.447  vocabulário do idioma
    assets/lexico/nomes.txt.gz   237.018  nome próprio

**A caixa da entrada original é o que separa as duas**, e é a única separação
confiável que estes arquivos oferecem. O ABBYY guarda cada palavra comum nas duas
caixas (`build` e `Build`) e o nome próprio só na Capitalizada (`Andretti`), então
"aparece em minúscula" é vocabulário e "só Capitalizada" é nome. A primeira
tentativa separou por subtração — a lista de jogadores tirada do dicionário — e o
alarme falso saltou de 8,8% para 62,7%: `MegaDatabase(Jogadores)` tem time e
torneio (`Aachen Hoern U20`), então subtraí-la levava inglês junto.

**Das seis listas da pasta, só uma é lida.** `Chess-Dic-68 with MegaDatabePlayers`
contém 99,8% dos tokens de `MegaDatabase(Jogadores palavras unicas)` — o nome do
arquivo não mentia — e acrescentar as outras cinco às 310.465 palavras dele rendeu
0,1 ponto de alarme falso e custou 5,7 de recall. Ficam de fora por medida, não por
esquecimento.

**Entrada com ponto não é tokenizada, e isso também é medido.** Metade do arquivo é
inicial colada ao sobrenome (`m.lois`, `P.Puustinenasi`). Partir no ponto para
colher `lois` acrescenta 198 mil palavras, baixa o alarme falso de 5,8% para 4,8% e
derruba o recall de 53,8% para 49,1% — a troca ruim, porque o produto da fase é
triagem. Só entra o que já é palavra inteira.

O arquivo é **UTF-16 LE com BOM** e começa com uma linha `DICTIONARY_PROPERTIES=`,
que é do formato do ABBYY e não é palavra.
"""

import argparse
import gzip
import os
import sys
from collections import Counter

sys.stdout.reconfigure(errors="replace")

ORIGEM_PADRAO = "Lista de Palavras"
ARQUIVO = "Chess-Dic-68 with MegaDatabePlayers.txt"
DESTINO = os.path.join("assets", "lexico")

# Menor palavra que entra. É o `MIN_PARTE` do `core.lexico`, e pelo mesmo motivo:
# com 1 letra, "a"+"way" tornaria qualquer palavra partível.
MIN_LETRAS = 2


def ler_abbyy(caminho):
    """(minúsculas, só-Capitalizadas) — as duas listas, pela caixa da entrada.

    Descarta o que não é palavra inteira: entrada com ponto, dígito, espaço ou
    apóstrofo. São 523.566 das 834.031 linhas, e a maior parte é inicial colada a
    sobrenome — ver o cabeçalho deste arquivo para a medida que as manda embora.
    """
    minusculas, capitalizadas = set(), set()
    descartadas = Counter()
    with open(caminho, encoding="utf-16", errors="replace") as f:
        for linha in f:
            s = linha.strip()
            if not s or s.startswith("DICTIONARY_PROPERTIES"):
                continue
            if len(s) < MIN_LETRAS:
                descartadas["curta"] += 1
            elif not s.isalpha():
                descartadas["nao-e-palavra"] += 1
            elif s.islower():
                minusculas.add(s)
            else:
                capitalizadas.add(s.lower())
    return minusculas, capitalizadas - minusculas, descartadas


def gravar(caminho, palavras, comprimir):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    conteudo = "\n".join(sorted(palavras)) + "\n"
    if comprimir:
        # `mtime=0` para o arquivo sair byte a byte igual em duas execuções: com o
        # relógio dentro do gzip, cada importação viraria um diff de 900 KB.
        with gzip.GzipFile(caminho, "wb", compresslevel=9, mtime=0) as f:
            f.write(conteudo.encode("utf-8"))
    else:
        with open(caminho, "w", encoding="utf-8", newline="\n") as f:
            f.write(conteudo)
    return os.path.getsize(caminho)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--origem", default=ORIGEM_PADRAO,
                    help=f"pasta com {ARQUIVO!r}")
    ap.add_argument("--destino", default=DESTINO)
    ap.add_argument("--texto", action="store_true",
                    help="grava .txt em vez de .txt.gz")
    args = ap.parse_args()

    origem = os.path.join(args.origem, ARQUIVO)
    if not os.path.exists(origem):
        print(f"não achei {origem!r}")
        return 1

    idioma, nomes, descartadas = ler_abbyy(origem)
    ext = ".txt" if args.texto else ".txt.gz"
    total = 0
    for nome, palavras in (("en", idioma), ("nomes", nomes)):
        caminho = os.path.join(args.destino, nome + ext)
        n = gravar(caminho, palavras, not args.texto)
        total += n
        print(f"{caminho:<32} {len(palavras):>7} palavras  {n/1e6:>5.2f} MB")

    print(f"{'':<32} {len(idioma) + len(nomes):>7} palavras  {total/1e6:>5.2f} MB")
    print("\ndescartadas (não são palavra inteira):")
    for k, v in descartadas.most_common():
        print(f"  {k:<16} {v:>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
