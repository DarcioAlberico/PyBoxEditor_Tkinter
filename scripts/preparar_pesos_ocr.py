"""Prepara os pesos opcionais de OCR para português e inglês.

Uso:
    python scripts/preparar_pesos_ocr.py
    python scripts/preparar_pesos_ocr.py --destino modelos/easyocr --gpu

O comando falha com uma mensagem acionável se o EasyOCR não estiver instalado.
Ele não executa OCR nem modifica o modelo treinado do projeto.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.services.ocr_service import OCRService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--destino", type=Path,
                        help="pasta para armazenar os modelos do EasyOCR")
    parser.add_argument("--idiomas", nargs="+", choices=("en", "pt"),
                        default=["en", "pt"],
                        help="idiomas a preparar (padrão: en pt)")
    parser.add_argument("--gpu", action="store_true",
                        help="inicializa o reader usando GPU")
    args = parser.parse_args()
    if args.destino:
        args.destino.mkdir(parents=True, exist_ok=True)
    try:
        OCRService().preparar_easyocr(tuple(args.idiomas), args.gpu,
                                      str(args.destino) if args.destino else None)
    except ModuleNotFoundError as erro:
        modulo = erro.name or "easyocr"
        print(f"Dependência ausente: {modulo}. Instale com: "
              "python -m pip install -e \".[ml]\"", file=sys.stderr)
        return 2
    except Exception as erro:
        print(f"Não foi possível preparar os pesos OCR: {erro}", file=sys.stderr)
        return 1
    local = str(args.destino) if args.destino else "cache padrão do EasyOCR"
    print(f"Pesos EasyOCR preparados: {', '.join(args.idiomas)} ({local})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
