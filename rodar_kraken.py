"""
Roda o Kraken nas faixas exportadas e escreve `<chave>.krk.txt` ao lado.

    python rodar_kraken.py faixas krk_modelo/catmus-print-fondue-tiny-2024-01-31.mlmodel

**Pela API, e não pelo CLI.** O `kraken -I '*.png'` quebra no Windows: ele
expande o glob internamente e os arquivos expandidos voltam para o parser do
click como se fossem subcomandos (`Error: No such command '001a....png'`). A API
não passa por ali.

**Sem segmentação**, que é o `-s` do CLI: a faixa já é uma linha, e é o mesmo
motivo pelo qual o EasyOCR aqui é chamado por `recognize` e não por `readtext`.
A caixa declarada é a imagem inteira.

Escreve também `tempo.txt` com os segundos da corrida, porque a ponte do
`medir_linha.py` não mede tempo de motor que roda fora.
"""

import glob
import os
import sys
import time

from PIL import Image

from kraken import rpred
from kraken.containers import BBoxLine, Segmentation
from kraken.lib import models


def main():
    pasta = sys.argv[1]
    caminho_modelo = sys.argv[2]

    modelo = models.load_any(caminho_modelo)
    arquivos = sorted(glob.glob(os.path.join(pasta, "*.png")))
    print(f"{len(arquivos)} faixa(s), modelo {os.path.basename(caminho_modelo)}")

    t0 = time.perf_counter()
    for i, caminho in enumerate(arquivos, 1):
        im = Image.open(caminho)
        seg = Segmentation(
            type="bbox",
            imagename=caminho,
            text_direction="horizontal-lr",
            script_detection=False,
            lines=[BBoxLine(id="1", bbox=(0, 0, im.width, im.height))],
        )
        texto = "".join(str(r) for r in rpred.rpred(modelo, im, seg))
        with open(caminho[: -len(".png")] + ".krk.txt", "w", encoding="utf-8") as f:
            f.write(texto)
        if i % 100 == 0:
            print(f"  {i}/{len(arquivos)}", flush=True)

    segundos = time.perf_counter() - t0
    with open(os.path.join(pasta, "tempo.txt"), "w", encoding="utf-8") as f:
        f.write(f"{segundos:.1f}\n")
    print(f"{segundos:.1f} s para {len(arquivos)} faixa(s) — "
          f"{1000 * segundos / max(1, len(arquivos)):.1f} ms/linha")


if __name__ == "__main__":
    main()
