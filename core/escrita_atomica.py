"""A escrita atômica do programa inteiro: o destino tem o conteúdo antigo inteiro ou o novo inteiro.

Revisão geral 2, RG-03 (R-01 da `docs/SPEC_REVISAO_GERAL_2.md`; invariante 17 do
`CONTEXT.md`). Cada gravador gravava do seu jeito, e três jeitos perdiam dado:

- **`.tmp` de nome fixo** (`settings.json.tmp`, `rascunho.tmp`): a janela principal e o
  `appy.py --editor` são processos diferentes e gravavam o mesmo temporário ao mesmo
  tempo, um por cima do outro;
- **direto no destino** (o `.box`, o TXT, o HTML, o PGN do editor): o `open("w")` zera o
  arquivo antes de escrever, e um erro na formatação ou um disco cheio deixava o `.box`
  vazio — medido, de 15 para 0 bytes;
- **`os.replace` sem `fsync`**: numa queda de energia o destino pode amanhecer vazio.

Aqui, em todas as formas, o temporário é único (`mkstemp` na mesma pasta, para o
`os.replace` ser uma troca de nome no mesmo disco), o conteúdo vai ao disco (`fsync`,
salvo `duravel=False` para cache descartável), o modo do destino é preservado (e o
arquivo novo sai `0o666 & ~umask`, não o 0600 do `mkstemp`), o `os.replace` tenta de novo
por um instante quando o Windows o recusa porque outro processo está lendo o destino, e
o temporário é apagado em qualquer falha. Texto sai em UTF-8 com LF.

Três formas, para os três jeitos de gravar que o código tem:

- `gravar_atomico(destino, conteudo)` — o conteúdo já está na mão (texto ou bytes);
- `with escrita_atomica(destino) as f:` — quem escreve em fluxo num arquivo aberto;
- `with caminho_temporario(destino) as tmp:` — quem passa um nome de arquivo a uma
  biblioteca que o abre sozinha (`torch.save`, `fitz.Document.save`, `docx.Document.save`,
  `Image.save`, `zipfile.ZipFile`).

O diário de revisão, que só acrescenta, não passa por aqui: ele tem a regra dele (R-09).
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import time
from pathlib import Path
from typing import Iterator, Union

from core.log import logger

log = logger(__name__)

Caminho = Union[str, "os.PathLike[str]"]

#: O umask do processo, lido uma vez: `os.umask` só se lê trocando-o, e trocar a cada
#: gravação não é seguro entre threads.
_UMASK = os.umask(0)
os.umask(_UMASK)

#: Quantas vezes o `os.replace` tenta de novo quando o Windows o recusa, e a pausa entre
#: elas: ~1 s ao todo, o bastante para outro processo terminar de ler o arquivo.
_TENTATIVAS = 20
_PAUSA = 0.05


def _modo_para(destino: Path) -> int:
    try:
        return destino.stat().st_mode & 0o7777
    except OSError:
        return 0o666 & ~_UMASK


def _trocar(temporario: str, destino: Path) -> None:
    for tentativa in range(_TENTATIVAS):
        try:
            os.replace(temporario, destino)
            return
        except PermissionError:
            if tentativa == _TENTATIVAS - 1:
                raise
            time.sleep(_PAUSA)


def _apagar(temporario: str) -> None:
    try:
        os.unlink(temporario)
    except FileNotFoundError:
        pass
    except OSError as erro:
        log.debug("escrita atômica: o temporário %s não foi apagado (%s)", temporario, erro)


def _para_o_disco(temporario: str) -> None:
    with open(temporario, "rb+") as f:
        os.fsync(f.fileno())


@contextlib.contextmanager
def caminho_temporario(destino: Caminho, *, duravel: bool = True) -> Iterator[str]:
    """Um caminho temporário ao lado de `destino`; publicado no fim do bloco, apagado na falha."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(prefix=f".{destino.name}.", suffix=".tmp", dir=destino.parent)
    os.close(fd)
    try:
        yield temporario
        if duravel:
            _para_o_disco(temporario)
        os.chmod(temporario, _modo_para(destino))
        _trocar(temporario, destino)
    except BaseException:
        _apagar(temporario)
        raise


@contextlib.contextmanager
def escrita_atomica(destino: Caminho, modo: str = "w", *, encoding: str = "utf-8",
                    duravel: bool = True) -> Iterator:
    """Um arquivo aberto (`"w"` texto com LF, ou `"wb"`) cujo conteúdo só vira `destino` no fim."""
    if modo not in ("w", "wb"):
        raise ValueError(f"modo de escrita atômica é 'w' ou 'wb', não {modo!r}")
    with caminho_temporario(destino, duravel=duravel) as temporario:
        if modo == "w":
            with open(temporario, "w", encoding=encoding, newline="\n") as f:
                yield f
        else:
            with open(temporario, "wb") as f:
                yield f


def gravar_atomico(destino: Caminho, conteudo: Union[str, bytes], *, encoding: str = "utf-8",
                   duravel: bool = True) -> Path:
    """Grava `conteudo` (texto em UTF-8 com LF, ou bytes) em `destino`, inteiro ou nada."""
    modo = "wb" if isinstance(conteudo, (bytes, bytearray)) else "w"
    with escrita_atomica(destino, modo, encoding=encoding, duravel=duravel) as f:
        f.write(conteudo)
    return Path(destino)
