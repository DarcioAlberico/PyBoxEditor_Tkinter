"""Os tetos de tamanho na leitura de um pacote zip de terceiro: DOCX e EPUB (RG-04, R-06).

Revisão geral 2. O `_Pacote` do DOCX lia o zip inteiro para a memória — um DOCX de 306 KB
com uma entrada de 300 MB de zeros levou o processo a 631 MB, e com alguns GB descomprimidos
o editor morria e levava o trabalho aberto — e o EPUB lia cada recurso sem olhar o tamanho.
Aqui se confere o `ZipInfo.file_size` declarado, por entrada e no total, **antes** de ler.

Os tetos são de livro, não de bomba: 256 MB por entrada (uma imagem de página a 600 dpi tem
dezenas de MB) e 1 GB no pacote inteiro.
"""

from __future__ import annotations

import zipfile

TETO_POR_ENTRADA = 256 << 20
TETO_TOTAL = 1024 << 20


class PacoteGrandeDemais(ValueError):
    """O pacote declara mais bytes descomprimidos do que um livro tem."""


def _mb(n: int) -> str:
    return f"{n / (1 << 20):.0f} MB"


def conferir(z: zipfile.ZipFile, arquivo: str = "") -> None:
    """Levanta `PacoteGrandeDemais` se uma entrada ou o total passam do teto."""
    de = f" em {arquivo}" if arquivo else ""
    total = 0
    for info in z.infolist():
        if info.file_size > TETO_POR_ENTRADA:
            raise PacoteGrandeDemais(
                f"a entrada {info.filename}{de} tem {_mb(info.file_size)} descomprimidos; "
                f"o teto é {_mb(TETO_POR_ENTRADA)} por entrada")
        total += info.file_size
    if total > TETO_TOTAL:
        raise PacoteGrandeDemais(
            f"o pacote{de} tem {_mb(total)} descomprimidos no total; o teto é {_mb(TETO_TOTAL)}")


def ler(z: zipfile.ZipFile, nome: str) -> bytes:
    """`z.read(nome)`, depois de conferir o tamanho declarado da entrada."""
    info = z.getinfo(nome)
    if info.file_size > TETO_POR_ENTRADA:
        raise PacoteGrandeDemais(
            f"a entrada {nome} tem {_mb(info.file_size)} descomprimidos; "
            f"o teto é {_mb(TETO_POR_ENTRADA)} por entrada")
    return z.read(nome)
