"""
A família de layout de uma página lida — o eixo em que o corpus tem de crescer.

As quatro páginas de referência de 2026-09-15 não foram escolhidas ao acaso:
uma é prosa com diagramas (Aagaard 30), uma é tabela (Nunn 237), uma é de duas
colunas com cabeçalho em negativo (Yusupov 34) e uma é painel sobre trama
(Yusupov 47). Cada uma quebrou o leitor de um jeito diferente, e é por isso que
o item 6 da revisão de 2026-09-18 pede trinta páginas **por livro e por família
de layout**, e não trinta páginas quaisquer: trinta páginas de prosa mediriam
uma coisa só, com três casas decimais.

Este módulo diz a que família uma página pertence. Ele não abre PDF nem lê
imagem: recebe a `PaginaExtraida` que `livro.extrair` já produziu — que é onde
as colunas, os diagramas, as tabelas e o domínio de cada linha já foram
decididos — e lê os sinais dali.

**Uma página pertence a mais de uma família, e isso é o ponto.** A p. 30 do
Aagaard é prosa *e* notação *e* diagrama; contá-la só como "diagrama" esconderia
que ela é a única página de prosa longa do corpus. Por isso `familias` devolve um
conjunto e `principal` devolve uma só — a mais rara, que é a que faz a página
valer a transcrição.
"""

from __future__ import annotations

import collections
from typing import Any, Iterable, Mapping, Sequence

#: As famílias, da mais rara para a mais comum. A ordem **é** a regra de
#: desempate de `principal`: uma página de tabela com prosa em volta entra no
#: corpus pela tabela, porque prosa já há em toda página.
FAMILIAS = ("imagem", "tabela", "trama", "negativo", "duas_colunas",
            "diagramas", "notacao", "prosa")

#: Acima desta fração de linhas de lance, a página é de notação — é o perfil de
#: uma página de solução ou de análise, onde a prosa é legenda do lance e não o
#: contrário. Medido nas quatro de referência: 0,92 na p. 237 do Nunn (tabela de
#: finais), 0,29 na p. 30 do Aagaard (prosa com lances no meio).
FRACAO_DE_NOTACAO = 0.5

#: Quantos contornos fazem uma página de trama (F96). É o mesmo teto que faz o
#: `extrair_diagramas` trocar de caminho: acima disto a página não é texto com
#: figura, é uma fotografia meio-tom que o binarizador transforma em dezenas de
#: milhares de caixas.
CONTORNOS_DE_TRAMA = 20_000


def _blocos_por_tipo(pagina: Any) -> collections.Counter:
    return collections.Counter(type(bloco).__name__
                               for bloco in getattr(pagina, "blocos", []) or [])


#: O que o rótulo humano do manifesto (`metadata.difficulty`) declara.
#:
#: Duas famílias não estão na `PaginaExtraida` e não vão estar: a trama é uma
#: propriedade da **imagem** (a p. 47 do Yusupov é um painel meio-tom que o
#: binarizador transforma em 85.903 contornos), e o negativo é do **desenho** do
#: cabeçalho (branco sobre preto, que `core/negativo.py` endireita box a box).
#: Quem as conhece é quem olhou a página, e é por isso que elas vêm do
#: manifesto, que é onde o rótulo humano mora.
FAMILIA_DA_DIFICULDADE = {
    "table": "tabela", "two_columns": "duas_colunas",
    "halftone_panel": "trama", "negative_header": "negativo",
    "full_page_image": "imagem",
}


def familias(pagina: Any, *, contornos: int | None = None,
             declaradas: Iterable[str] = ()) -> set[str]:
    """As famílias a que esta página pertence.

    `contornos` é o número de caixas que a página gerou **antes** do descarte,
    quando quem chama o tem (`BoxService.boxes_antes_do_descarte`): é o único
    sinal de trama que não exige reabrir a imagem. `declaradas` são as famílias
    que o manifesto afirma — o rótulo de quem olhou a página, que é de onde a
    trama e o negativo vêm quando ninguém contou os contornos.
    """
    achadas: set[str] = {familia for familia in declaradas if familia in FAMILIAS}
    if getattr(pagina, "pagina_de_imagem", False):
        return achadas | {"imagem"}
    tipos = _blocos_por_tipo(pagina)
    if tipos.get("Tabela"):
        achadas.add("tabela")
    if int(getattr(pagina, "diagramas", 0) or 0):
        achadas.add("diagramas")
    if int(getattr(pagina, "colunas", 1) or 1) >= 2:
        achadas.add("duas_colunas")
    if contornos is not None and contornos >= CONTORNOS_DE_TRAMA:
        achadas.add("trama")
    roteamento = list(getattr(pagina, "roteamento", []) or [])
    if roteamento:
        de_lance = sum(1 for registro in roteamento
                       if str(registro.get("dominio")) in ("notation", "mixed"))
        if de_lance / len(roteamento) >= FRACAO_DE_NOTACAO:
            achadas.add("notacao")
    if tipos.get("Paragrafo"):
        achadas.add("prosa")
    return achadas or {"prosa"}


def principal(pagina: Any, *, contornos: int | None = None,
              declaradas: Iterable[str] = ()) -> str:
    """A família **mais rara** desta página — a que justifica transcrevê-la."""
    achadas = familias(pagina, contornos=contornos, declaradas=declaradas)
    return next(familia for familia in FAMILIAS if familia in achadas)


def cobertura(paginas: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Quantas páginas do corpus cobrem cada família.

    Recebe o que o relatório da rodada guarda — dicionários com `familias` —,
    e não as páginas lidas, porque a cobertura se pergunta sobre o corpus
    inteiro, inclusive o de rodadas passadas.
    """
    contagem = {familia: 0 for familia in FAMILIAS}
    for pagina in paginas:
        for familia in pagina.get("familias") or ():
            if familia in contagem:
                contagem[familia] += 1
    return contagem


def faltando(paginas: Iterable[Mapping[str, Any]], *, minimo: int = 3) -> list[str]:
    """As famílias com menos de `minimo` páginas — o que o corpus ainda não mede.

    Três é o piso do item 6, e não é número redondo: com uma página, um defeito
    de layout e um defeito de leitura são indistinguíveis; com duas, o empate
    não se desfaz.
    """
    contagem = cobertura(paginas)
    return [familia for familia in FAMILIAS if contagem[familia] < minimo]


def por_livro(paginas: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """A cobertura de famílias, livro a livro."""
    saida: dict[str, dict[str, int]] = {}
    for pagina in paginas:
        documento = str(pagina.get("documento") or "?")
        alvo = saida.setdefault(documento, {familia: 0 for familia in FAMILIAS})
        for familia in pagina.get("familias") or ():
            if familia in alvo:
                alvo[familia] += 1
    return saida


def resumo(paginas: Sequence[Mapping[str, Any]], *, minimo: int = 3) -> dict[str, Any]:
    """O bloco de cobertura que o relatório da rodada publica."""
    return {"paginas": len(paginas), "cobertura": cobertura(paginas),
            "faltando": faltando(paginas, minimo=minimo),
            "por_livro": por_livro(paginas), "minimo_por_familia": minimo}
