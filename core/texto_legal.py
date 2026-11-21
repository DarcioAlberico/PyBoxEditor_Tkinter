"""O texto que um documento XML aceita: a decisão única dos escritores (RG-04, R-07).

Revisão geral 2. O XML 1.0 não aceita os caracteres de controle C0 (menos tabulação, nova
linha e retorno), os não caracteres U+FFFE e U+FFFF, nem um surrogate solto. O EPUB do OCR
gravava `"linha\\x0c fim"` e saía mal formado; o `python-docx` levantava `All strings must
be XML compatible` e a exportação inteira caía; o editor também gravava o capítulo mal
formado, e um `\\ud800` solto levantava `UnicodeEncodeError`. Esses caracteres não aparecem
na leitura do OCR medida; entram pela camada do PDF e pelo TXT, HTML e DOCX importados. A
defesa é aqui, na fronteira, e é chamada **onde o texto vira nó XML** — no documento já
serializado, no run, no trecho —, nunca antes do cálculo das faixas de negrito e itálico,
que são fatias do texto e ficariam deslocadas.

Precedente: o AbbyChessCraft filtra exatamente esse conjunto (`_FORA_DO_XML`, em
`abbychess/epub.py`); a função é pública como oferta a ele.
"""

from __future__ import annotations

import logging
import re

from core.log import logger, uma_vez

log = logger(__name__)

_FORA_DO_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿\ud800-\udfff]")


def texto_legal_em_xml(texto: str, origem: str = "") -> str:
    """`texto` sem o que o XML não aceita; a contagem vai ao log em WARNING, uma vez por `origem`."""
    limpo, tirados = _FORA_DO_XML.subn("", texto)
    if tirados:
        uma_vez(log, f"fora-do-xml:{origem}", logging.WARNING,
                "%d caractere(s) que o XML não aceita tirado(s) do texto%s",
                tirados, f" de {origem}" if origem else "")
    return limpo
