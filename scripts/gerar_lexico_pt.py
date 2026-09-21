"""
Gera `assets/lexico/pt.hunspell.gz` — o léxico do português para a ortografia do editor
de livros (ED-06b; SPEC_EDITOR §8.13) — a partir de um dicionário Hunspell
(`pt_BR.dic` + `pt_BR.aff`).

## De onde vem

O dicionário é o VERO (Verificador Ortográfico do LibreOffice/OpenOffice.org, de
Raimundo Santos Moura e colaboradores, LGPL 2.1), que vem instalado com o TeXstudio, o
LibreOffice e o Firefox; a licença está em `assets/lexico/LICENCAS.txt`. O `.dic` traz
307 mil raízes com **flags** (`cavalo/D`), e o `.aff` diz o que cada flag faz — 25 mil
regras de sufixo e 150 de prefixo.

## Por que não uma lista chã como a do inglês

A expansão completa (o `unmunch`, que `expandir` faz) dá **10 milhões** de formas — 2,7
milhões sem as ênclises (`amá-lo-ia`), 1,8 milhão sem diminutivos e superlativos —, 27 MB
comprimidos e meio minuto para carregar. O pacote guarda as raízes com as flags e as
regras (1,3 MB) e `core/afixos.py` consulta ao contrário, da palavra para a raiz. O
arquivo é texto UTF-8: as linhas `SFX`/`PFX` do `.aff`, uma linha `---`, as entradas do
`.dic` — o `.aff` diz a sua codificação (`SET ISO8859-1`), e é daí que se converte.
`expandir` fica aqui para o teste conferir que o verificador reconhece cada forma que a
expansão produz (`tests/test_lexico_pt.py`).

Uso:  python scripts/gerar_lexico_pt.py [caminho/pt_BR.dic] [--saida assets/lexico/pt.hunspell.gz]
"""

from __future__ import annotations

import argparse
import gzip
import os
import re
import sys
from dataclasses import dataclass, field

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA_PADRAO = os.path.join(RAIZ, "assets", "lexico", "pt.hunspell.gz")
CANDIDATOS = (
    r"C:\Program Files\texstudio\dictionaries\pt_BR.dic",
    r"C:\Program Files\LibreOffice\share\extensions\dict-pt-BR\pt_BR.dic",
    "/usr/share/hunspell/pt_BR.dic",
)


@dataclass
class Regra:
    strip: str
    add: str
    condicao: re.Pattern | None
    continuacao: str = ""            # flags do `add/flags`


@dataclass
class Afixo:
    flag: str
    cruzado: bool
    regras: list[Regra] = field(default_factory=list)


def _condicao(texto: str, sufixo: bool) -> re.Pattern | None:
    if texto == ".":
        return None
    padrao = texto.replace("\\", "\\\\")
    return re.compile((padrao + "$") if sufixo else ("^" + padrao))


def codificacao_do_aff(caminho: str) -> str:
    with open(caminho, "rb") as f:
        for linha in f:
            if linha.startswith(b"SET "):
                return linha.split()[1].decode("ascii")
    return "ISO-8859-1"


def ler_aff(caminho: str) -> tuple[dict[str, Afixo], dict[str, Afixo], str]:
    """`(sufixos, prefixos, codificação)` do `.aff`."""
    codificacao = codificacao_do_aff(caminho)
    sufixos: dict[str, Afixo] = {}
    prefixos: dict[str, Afixo] = {}
    with open(caminho, encoding=codificacao, errors="replace") as f:
        for linha in f:
            partes = linha.rstrip("\r\n").split()
            if len(partes) < 4 or partes[0] not in ("SFX", "PFX"):
                continue
            alvo = sufixos if partes[0] == "SFX" else prefixos
            flag = partes[1]
            if flag not in alvo:
                # A linha de cabeçalho: `SFX D Y 16` (cruzado, quantas regras).
                alvo[flag] = Afixo(flag, partes[2] == "Y")
                if len(partes) == 4 and partes[3].isdigit():
                    continue
            if len(partes) < 5:
                continue
            strip = "" if partes[2] == "0" else partes[2]
            add, _, continuacao = partes[3].partition("/")
            add = "" if add == "0" else add
            alvo[flag].regras.append(Regra(strip, add, _condicao(partes[4], partes[0] == "SFX"), continuacao))
    return sufixos, prefixos, codificacao


def _aplicar_sufixos(palavra: str, flags: str, sufixos: dict[str, Afixo], nivel: int = 0) -> list[tuple[str, bool]]:
    """`(forma, veio de regra cruzada)` para cada sufixo aplicável."""
    saida: list[tuple[str, bool]] = []
    for flag in flags:
        afixo = sufixos.get(flag)
        if afixo is None:
            continue
        for regra in afixo.regras:
            if regra.condicao is not None and not regra.condicao.search(palavra):
                continue
            if regra.strip and not palavra.endswith(regra.strip):
                continue
            forma = (palavra[:-len(regra.strip)] if regra.strip else palavra) + regra.add
            saida.append((forma, afixo.cruzado))
            if regra.continuacao and nivel < 1:
                saida.extend(_aplicar_sufixos(forma, regra.continuacao, sufixos, nivel + 1))
    return saida


def _aplicar_prefixos(palavra: str, flags: str, prefixos: dict[str, Afixo]) -> list[tuple[str, bool]]:
    saida: list[tuple[str, bool]] = []
    for flag in flags:
        afixo = prefixos.get(flag)
        if afixo is None:
            continue
        for regra in afixo.regras:
            if regra.condicao is not None and not regra.condicao.search(palavra):
                continue
            if regra.strip and not palavra.startswith(regra.strip):
                continue
            forma = regra.add + (palavra[len(regra.strip):] if regra.strip else palavra)
            saida.append((forma, afixo.cruzado))
    return saida


def expandir(raiz: str, flags: str, sufixos: dict[str, Afixo], prefixos: dict[str, Afixo]) -> set[str]:
    """A raiz, as sufixadas, as prefixadas e — só entre regras cruzadas — as prefixadas das sufixadas."""
    formas = {raiz}
    sufixadas = _aplicar_sufixos(raiz, flags, sufixos)
    formas.update(f for f, _c in sufixadas)
    formas.update(f for f, _c in _aplicar_prefixos(raiz, flags, prefixos))
    flags_cruzadas = "".join(f for f in flags if f in prefixos and prefixos[f].cruzado)
    if flags_cruzadas:
        for forma_s, cruzada_s in sufixadas:
            if cruzada_s:
                formas.update(f for f, _c in _aplicar_prefixos(forma_s, flags_cruzadas, prefixos))
    return formas


def ler_dic(caminho: str, codificacao: str):
    with open(caminho, encoding=codificacao, errors="replace") as f:
        primeira = True
        for linha in f:
            linha = linha.rstrip("\r\n")
            if primeira:
                primeira = False
                if linha.strip().isdigit():
                    continue
            if not linha or linha.startswith("#") or linha.startswith("\t"):
                continue
            raiz, _, flags = linha.partition("/")
            raiz = raiz.split("\t")[0].strip()
            if raiz:
                yield raiz, flags.split("\t")[0].strip()


def empacotar(dic: str, saida: str) -> tuple[int, int]:
    """O pacote `.hunspell.gz`; devolve `(regras, raízes)`."""
    aff = os.path.splitext(dic)[0] + ".aff"
    codificacao = codificacao_do_aff(aff)
    regras = 0
    raizes = 0
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    with gzip.open(saida, "wt", encoding="utf-8", newline="\n") as f:
        with open(aff, encoding=codificacao, errors="replace") as origem:
            for linha in origem:
                if linha.startswith(("SFX", "PFX")):
                    f.write(linha.rstrip("\r\n") + "\n")
                    regras += 1
        f.write("---\n")
        for raiz, flags in ler_dic(dic, codificacao):
            f.write(f"{raiz}/{flags}\n" if flags else f"{raiz}\n")
            raizes += 1
    return regras, raizes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("dic", nargs="?", help="o pt_BR.dic (o .aff fica ao lado)")
    parser.add_argument("--saida", default=SAIDA_PADRAO)
    args = parser.parse_args(argv)
    dic = args.dic or next((c for c in CANDIDATOS if os.path.exists(c)), None)
    if not dic or not os.path.exists(dic):
        print("dicionário Hunspell não encontrado; passe o caminho do pt_BR.dic", file=sys.stderr)
        return 2
    regras, raizes = empacotar(dic, args.saida)
    print(f"{raizes} raízes e {regras} linhas de regra em {args.saida} ({os.path.getsize(args.saida) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
