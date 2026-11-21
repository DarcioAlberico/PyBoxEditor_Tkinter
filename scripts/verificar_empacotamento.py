"""Verifica os recursos que o bundle desktop e o wheel têm de levar.

Este comando é deliberadamente barato e não importa Tk, Torch ou PyMuPDF.
Serve para CI e para dar uma mensagem útil antes de iniciar o PyInstaller.

`RECURSOS_OBRIGATORIOS` é a lista única (RG-02a, R-41 da revisão geral 2): o bundle
confere a árvore (`verificar_raiz`) e o wheel confere o zip (`verificar_wheel`), pela regra
de `nome_no_wheel` — o que mora num pacote vai com o mesmo caminho, o que vai como
`data-files` (fontes, peças) vai para `<dist>.data/data/share/PyBoxEditor/`. Antes, a CI
conferia três arquivos escritos à mão, e o wheel saía sem fontes, peças e perfis.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


RECURSOS_OBRIGATORIOS = (
    Path("appy.py"),
    Path("assets/fonts/SimbolosDeXadrez.ttf"),
    Path("assets/lexico/en.txt.gz"),
    Path("core/dados/fontes_de_diagrama.json"),
    Path("pieces/wK.png"),
    Path("fonts/SkakNew-Diagram.otf"),
    Path("fonts/ChessMerida-Diagram.ttf"),
    Path("config/profiles/10_figurina_unica.json"),
    Path("config/profiles/20_duas_caixas.json"),
)

#: O que vai como `data-files` (o `setup.py`), e não dentro de um pacote.
_PASTAS_DE_DADOS = ("fonts", "pieces")

#: O que o bundle leva e o wheel não: o ponto de entrada fica fora dos pacotes.
_SO_NO_BUNDLE = (Path("appy.py"),)


def verificar_raiz(raiz: str | Path) -> list[Path]:
    """Devolve os recursos ausentes, sem alterar a árvore do projeto."""
    base = Path(raiz).resolve()
    return [caminho for caminho in RECURSOS_OBRIGATORIOS
            if not (base / caminho).is_file()]


def nome_no_wheel(caminho: str | Path, dist: str) -> str:
    """O nome, dentro do wheel `dist` (ex. `pyboxeditor-0.1.0`), do recurso `caminho` da árvore."""
    relativo = Path(caminho).as_posix()
    if relativo.split("/", 1)[0] in _PASTAS_DE_DADOS:
        return f"{dist}.data/data/share/PyBoxEditor/{relativo}"
    return relativo


def verificar_wheel(wheel: str | Path) -> list[str]:
    """Os nomes que faltam no wheel, pela mesma lista e pela regra de `nome_no_wheel`."""
    wheel = Path(wheel)
    nome, versao = wheel.name.split("-")[:2]
    dist = f"{nome}-{versao}"
    with zipfile.ZipFile(wheel) as arquivo:
        nomes = set(arquivo.namelist())
    esperados = [nome_no_wheel(c, dist) for c in RECURSOS_OBRIGATORIOS if c not in _SO_NO_BUNDLE]
    return [n for n in esperados if n not in nomes]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raiz", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="raiz do projeto (padrão: diretório pai de scripts)")
    parser.add_argument("--wheel", type=Path, help="confere este wheel em vez da árvore")
    args = parser.parse_args(argv)

    if args.wheel:
        faltam = verificar_wheel(args.wheel)
        if faltam:
            print(f"Recursos ausentes no wheel {args.wheel.name}:", file=sys.stderr)
            for nome in faltam:
                print(f"  - {nome}", file=sys.stderr)
            return 1
        print(f"Wheel completo: {args.wheel.name}")
        return 0

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
