"""
O que o leitor da página de imagem (`core/livro.py`) e o da camada do PDF
(`core/pdf_nativo.py`) têm em comum e nenhum dos dois pode tomar do outro (PD-22).

Até aqui o `pdf_nativo` importava o `livro` inteiro para três funções de
cabeçalho — a assinatura de uma linha, se ela é candidata a cabeçalho, o lance
limpo de uma palavra — e o `livro` importava o `pdf_nativo` para ler a camada:
um ciclo. As três moram aqui, com o `notacao` de que precisam; `core/pagina.py`
tem as constantes e o `_coluna_de`, que não precisam de nada. O `livro` as
reexporta com o nome de sempre, para quem já as tomava de lá.
"""
from __future__ import annotations

import re

from core import notacao
from core.pagina import PALAVRAS_DE_CABECALHO


def _assinatura(texto: str) -> str:
    """
    O que fica de um cabeçalho quando se tira o que muda de página para página.

    O número sai — `Chapter 3 · 37` e `Chapter 3 · 38` são o mesmo cabeçalho —
    e a pontuação vira espaço. O número de página sozinho vira a assinatura
    vazia, que é a de todo número de página.
    """
    baixo = re.sub(r"\d+", "", texto.lower())
    return " ".join(re.sub(r"[^\w\s]", " ", baixo).split())

def _candidato_a_cabecalho(linha: str) -> bool:
    """
    Uma linha curta, com letra ou número, e sem lance: a régua que a
    repetição ainda confirma.

    A letra ou o número é o que separa o número de página do `=` que o
    filete decorativo vira quando é lido: os dois têm a assinatura vazia, e
    sem isto o filete sairia como rodapé. Ele não é cabeçalho, é ruído, e
    ruído tem outro dono.
    """
    palavras = linha.split()
    if not 0 < len(palavras) <= PALAVRAS_DE_CABECALHO:
        return False
    if not any(c.isalnum() for c in linha):
        return False
    # O parêntese é o outro dono: `(see page 43)` no alto de três páginas é
    # remissão, e cabeçalho de página nunca vem entre parênteses.
    if linha.startswith("(") and linha.endswith(")"):
        return False
    return not any(notacao.parece_lance(_lance_limpo(w)) for w in palavras)

def _lance_limpo(palavra: str) -> str:
    """
    `20...♗d3!` como `parece_lance` o entende: sem o número do lance, com a
    figurina em letra e o travessão do roque em hífen. Ele lê `Bd3!`, e não
    o que o livro imprime — é a mesma tradução que `notacao.Simbolo` faz.
    """
    sem_numero = re.sub(r"^\d+\.(\.\.)?", "", palavra)
    return "".join(notacao.FIGURINAS.get(c, "-" if c in "–—" else c)
                   for c in sem_numero)
