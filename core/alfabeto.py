"""
O alfabeto de cada livro (F109 §1): que letras o modelo pode responder aqui.

O modelo tem 314 classes, e todas competem em todo recorte de todo livro. Num
livro em inglês saem 17 letras acentuadas distintas em 1.112 ocorrências —
`Š` 185 vezes, `É` 404, `ê` 409 — e nenhuma é legítima: são classes que o livro
não usa e que ganham no softmax da classe certa por um pixel de serifa.

**Isto não pede modelo novo nem treino.** O veto geométrico da F106 já tem a
forma "filtre as candidatas e escolha entre as que sobram", e a máscara entra
no mesmo lugar, com o mesmo formato (`LearningService.ler_texto`). O custo é um
teste de pertinência por leitura que falhe — a leitura que passa não paga nada.

**O que se mascara é a letra latina fora do alfabeto do idioma, e só ela.**
Dígito, pontuação, figurina e símbolo de análise (`Δ`, `±`, `□`) passam sempre:
não são de idioma nenhum. E o `Δ` é o motivo de a régua não ser `isalpha()`,
que o chama de letra — a régua é "letra latina fora do ASCII", que é o que as
classes acentuadas do modelo são.

Sem idioma (`None`) a máscara não tem opinião, que é o comportamento de antes:
quem lê uma página solta na tela não sabe de que livro ela é.
"""

import unicodedata
from typing import Iterable, List, Optional, Tuple

#: As letras que cada idioma escreve **além** do latim básico.
#:
#: O inglês não escreve nenhuma — `café` e `naïve` são raros demais para pagar
#: 1.112 leituras erradas num livro só. O português é o do próprio projeto
#: (dois dos oito livros do corpus), com o `ü` do `lingüiça` de antes de 2009,
#: que os livros mais velhos ainda trazem.
ACENTUADAS = {
    "en": "",
    "pt": "áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ",
}


def _latina_estendida(c: str) -> bool:
    """Letra latina fora do ASCII — o que uma máscara de idioma julga."""
    return (ord(c) > 127 and c.isalpha()
            and unicodedata.name(c, "").startswith("LATIN "))


def permitido(char: str, idioma: Optional[str]) -> bool:
    """
    O idioma escreve esta classe?

    `True` sem idioma, para idioma que este módulo não conhece, e para toda
    classe sem letra latina estendida — a máscara só tem opinião sobre a
    letra acentuada, e não ter opinião é responder que sim. A classe de
    ligadura (`ça`, `çã`) é julgada letra a letra, que é como ela sai no texto.
    """
    if not idioma or idioma not in ACENTUADAS:
        return True
    proprias = ACENTUADAS[idioma]
    return all(not _latina_estendida(c) or c in proprias for c in char)


def filtrar(candidatas: Iterable[Tuple[str, float]],
            idioma: Optional[str]) -> List[Tuple[str, float]]:
    """As candidatas que o idioma admite, na ordem em que vieram."""
    return [(c, p) for c, p in candidatas if permitido(c, idioma)]
