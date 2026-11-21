"""O caminho que vem de fora não sai da raiz dele: a decisão única (RG-04, R-05; invariante 18).

Revisão geral 2. Um EPUB, um DOCX ou um HTML de terceiro traz nomes de arquivo escritos por
quem fez o livro, e o programa os usava como caminho no disco: a pasta HTML de um EPUB com a
entrada `../../ESCAPOU.txt` gravou fora da pasta escolhida; um EPUB legítimo com o OPF em
`OEBPS/opf/` e os capítulos em `../Text/` também escapava; a leitura do zip regravava
entradas `..` e absolutas no EPUB salvo.

`e_relativo_seguro(relativo)` diz se um caminho relativo (com `/` ou `\\`) fica dentro da raiz
de quem o resolve: recusa o absoluto (`/x`, `\\x`), a letra de unidade (`C:x`, `C:/x`), o UNC
(`//servidor`, `\\\\servidor`) e o que, normalizado, sobe acima da raiz (`../x`, `a/../../x`).
`caminho_seguro(raiz, relativo)` devolve o caminho no disco ou levanta `CaminhoInseguro`.
"""

from __future__ import annotations

import os
import posixpath
import re
from pathlib import Path

_UNIDADE = re.compile(r"^[A-Za-z]:")


class CaminhoInseguro(ValueError):
    """O caminho sairia da raiz em que devia ser resolvido."""


def e_relativo_seguro(relativo: str) -> bool:
    """`relativo`, resolvido em qualquer raiz, fica dentro dela?"""
    if not relativo:
        return False
    texto = relativo.replace("\\", "/")
    if texto.startswith("/") or _UNIDADE.match(texto):
        return False
    normal = posixpath.normpath(texto)
    return normal != ".." and not normal.startswith("../")


def caminho_seguro(raiz: str | os.PathLike, relativo: str) -> Path:
    """O caminho de `relativo` dentro de `raiz`; `CaminhoInseguro` se ele sairia dela."""
    if not e_relativo_seguro(relativo):
        raise CaminhoInseguro(f"caminho fora da raiz: {relativo!r}")
    base = Path(raiz)
    destino = base.joinpath(*posixpath.normpath(relativo.replace("\\", "/")).split("/"))
    if os.path.commonpath([os.path.abspath(base), os.path.abspath(destino)]) != os.path.abspath(base):
        raise CaminhoInseguro(f"caminho fora da raiz: {relativo!r}")
    return destino
