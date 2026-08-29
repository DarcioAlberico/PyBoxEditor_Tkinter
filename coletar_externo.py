"""
Junta as saídas de um motor de fora num `predicoes.json` para o
`medir_linha.py --predicoes`.

    python coletar_externo.py faixas predicoes.json .pred.txt   # Calamari
    python coletar_externo.py faixas krk.json       .krk.txt    # Kraken

A chave já é o nome do arquivo: o `--exportar` gravou cada faixa como
`<sha1 dos bytes>.png`, e os dois motores escrevem `<mesma chave><sufixo>` ao
lado.

**Os marcadores de direção saem.** O `python-bidi` do Calamari embrulha cada
linha em U+202A/U+202C (LTR embedding e pop), que não são texto da página e
contariam como dois caracteres a mais na distância de edição.

A confiança não vem por linha nos `.pred.txt`, então sai 0,0 — a tabela do
`medir_linha.py` não usa a confiança do motor em coluna nenhuma.
"""

import glob
import json
import os
import sys

MARCAS = dict.fromkeys(map(ord, "‪‫‬‭‮‎‏"))


def main():
    pasta = sys.argv[1] if len(sys.argv) > 1 else "faixas"
    saida = sys.argv[2] if len(sys.argv) > 2 else "predicoes.json"
    sufixo = sys.argv[3] if len(sys.argv) > 3 else ".pred.txt"

    pred = {}
    for caminho in glob.glob(os.path.join(pasta, "*" + sufixo)):
        chave = os.path.basename(caminho)[: -len(sufixo)]
        with open(caminho, encoding="utf-8") as f:
            texto = f.read().translate(MARCAS).strip()
        pred[chave] = [texto, 0.0]

    faixas = json.load(open(os.path.join(pasta, "faixas.json"), encoding="utf-8"))
    faltando = [c for c in faixas if c not in pred]

    with open(saida, "w", encoding="utf-8") as f:
        json.dump(pred, f, ensure_ascii=False)

    print(f"{len(pred)} predição(ões) para {len(faixas)} faixa(s) → {saida}")
    if faltando:
        print(f"{len(faltando)} sem predição: {faltando[:3]}")


if __name__ == "__main__":
    main()
