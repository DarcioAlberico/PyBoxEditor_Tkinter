"""Verifica os pré-requisitos locais do bundle desktop.

Este comando é deliberadamente barato e não importa Tk, Torch ou PyMuPDF.
Serve para CI e para dar uma mensagem útil antes de iniciar o PyInstaller.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


RECURSOS_OBRIGATORIOS = (
    Path("appy.py"),
    Path("assets/fonts/SimbolosDeXadrez.ttf"),
    Path("assets/lexico/en.txt.gz"),
    Path("core/dados/fontes_de_diagrama.json"),
    Path("pieces/wK.png"),
)


def verificar_raiz(raiz: str | Path) -> list[Path]:
    """Devolve os recursos ausentes, sem alterar a árvore do projeto."""
    base = Path(raiz).resolve()
    return [caminho for caminho in RECURSOS_OBRIGATORIOS
            if not (base / caminho).is_file()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raiz", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="raiz do projeto (padrão: diretório pai de scripts)")
    args = parser.parse_args(argv)

    ausentes = verificar_raiz(args.raiz)
    if ausentes:
        print("Recursos necessários ausentes:", file=sys.stderr)
        for caminho in ausentes:
            print(f"  - {caminho}", file=sys.stderr)
        return 1

    print(f"Empacotamento pronto: {Path(args.raiz).resolve()}")
    print("Comando: python -m PyInstaller --noconfirm --clean pyboxeditor.spec")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
