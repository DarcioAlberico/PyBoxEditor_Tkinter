"""
Roda o PaddleOCR nas faixas exportadas e escreve `<chave>.pad.txt` ao lado.

    python rodar_paddle.py faixas PP-OCRv6_medium_rec

**Só o módulo de reconhecimento**, que é o `TextRecognition` — a faixa já é uma
linha, e rodar o detector de novo é o erro que a F17 mediu do lado do EasyOCR.

**O modelo é argumento porque a família tem três níveis**, e a SPEC §7.2 pontua
os três: `PP-OCRv6_medium_rec` (34,5 M, 93,20), `PP-OCRv6_small_rec` (7,7 M,
88,20) e `PP-OCRv6_tiny_rec` (1,5 M, 86,80). O RapidOCR desta mesma tabela roda o
**small**; medir o PaddleOCR sem dizer qual nível seria comparar duas coisas
diferentes com o mesmo nome.

Escreve `tempo.txt` com os segundos, porque a ponte do `medir_linha.py` não mede
tempo de motor que roda fora.
"""

import glob
import os
import sys
import time

from paddleocr import TextRecognition


def main():
    pasta = sys.argv[1]
    modelo = sys.argv[2] if len(sys.argv) > 2 else "PP-OCRv6_medium_rec"

    rec = TextRecognition(model_name=modelo)
    arquivos = sorted(glob.glob(os.path.join(pasta, "*.png")))
    print(f"{len(arquivos)} faixa(s), modelo {modelo}")

    t0 = time.perf_counter()
    escritas = 0
    for i in range(0, len(arquivos), 32):
        lote = arquivos[i:i + 32]
        for caminho, r in zip(lote, rec.predict(lote)):
            with open(caminho[: -len(".png")] + ".pad.txt", "w",
                      encoding="utf-8") as f:
                f.write(r.get("rec_text") or "")
            escritas += 1
        if escritas % 128 < 32:
            print(f"  {escritas}/{len(arquivos)}", flush=True)

    segundos = time.perf_counter() - t0
    with open(os.path.join(pasta, "tempo_paddle.txt"), "w", encoding="utf-8") as f:
        f.write(f"{segundos:.1f}\n")
    print(f"{segundos:.1f} s para {escritas} faixa(s) — "
          f"{1000 * segundos / max(1, escritas):.1f} ms/linha")


if __name__ == "__main__":
    main()
