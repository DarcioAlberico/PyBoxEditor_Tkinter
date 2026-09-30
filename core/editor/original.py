"""
A página original do PDF ao lado do texto (ED-18; docs/ANALISE_JANELA_EDITOR.md §4.4) — a
parte sem Tk: onde o bloco está na página, qual é a próxima suspeita, e como trocar no
capítulo os blocos de uma página relida.

## A escala

`Origem.caixa` está em pixels da imagem que o leitor leu — a página rasterizada a `dpi`
(300 no leitor de produção; o documento editorial guarda o de cada página em
`page.metadata["dpi"]`). Em pontos do PDF é `px · 72 / dpi`; na tela, `pt · escala`.
`Origem.pagina` é o índice da página **no PDF** (0-based), mesmo quando só algumas foram
lidas.

## O bloco no modo código

No código não há `Bloco`: `origem_na_linha` acha a última tag de abertura com
`data-origem-*` que começa na linha do cursor ou antes dela — a mesma regra da prévia
("o bloco é o último que começa em ≤ linha").
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from core.editor import dialeto, modelo
from core.editor.modelo import Capitulo, Livro, MarcaDePagina, Origem

DPI_PADRAO = 300
_RE_TAG_COM_ORIGEM = re.compile(r"<[a-zA-Z][\w:-]*\b[^>]*\bdata-origem-bloco\s*=[^>]*>")
_RE_ATRIBUTO = re.compile(r"""([\w:-]+)\s*=\s*(["'])(.*?)\2""", re.S)


def pdf_do_livro(livro: Livro, documento: Any = None) -> str:
    """O PDF de onde o livro veio: o do livro (sobrevive ao EPUB), senão o do documento editorial."""
    caminho = getattr(getattr(livro, "origem", None), "pdf", "") or ""
    if not caminho and documento is not None:
        caminho = str(getattr(documento, "metadata", {}).get("source_path") or "")
    return caminho


def dpis_do_documento(documento: Any) -> dict[int, int]:
    """`índice da página → dpi` que o leitor usou (vazio sem documento)."""
    saida: dict[int, int] = {}
    for pagina in getattr(documento, "pages", ()) or ():
        dpi = int((getattr(pagina, "metadata", {}) or {}).get("dpi") or 0)
        if dpi:
            saida[int(pagina.page_index)] = dpi
    return saida


def caixa_em_pontos(caixa: Sequence[float], dpi: int = DPI_PADRAO) -> tuple[float, float, float, float]:
    """A caixa em pixels da leitura → em pontos do PDF."""
    fator = 72.0 / float(dpi or DPI_PADRAO)
    x0, y0, x1, y1 = (float(v) for v in caixa)
    return x0 * fator, y0 * fator, x1 * fator, y1 * fator


def origem_na_linha(texto: str, linha: int) -> Origem | None:
    """A origem do bloco do código na `linha` (1-based): a última tag com `data-origem-*` que começa em ≤ linha."""
    escolhida = None
    linha_da_tag = 1
    ultimo = 0
    for achado in _RE_TAG_COM_ORIGEM.finditer(texto):
        linha_da_tag += texto.count("\n", ultimo, achado.start())
        ultimo = achado.start()
        if linha_da_tag > linha:
            break
        escolhida = achado.group(0)
    if escolhida is None:
        return None
    attrs = {m.group(1): m.group(3) for m in _RE_ATRIBUTO.finditer(escolhida)}
    return dialeto.origem_de_atributos(attrs)


def blocos_com_origem(cap: Capitulo) -> list[Any]:
    return [b for b in modelo.blocos_do_capitulo(cap) if getattr(b, "origem", None) is not None]


def blocos_da_pagina(livro: Livro, pagina: int) -> list[tuple[str, Any]]:
    """`(arquivo do capítulo, bloco)` de todo bloco que veio da página `pagina` do PDF."""
    return [(cap.arquivo, b) for cap in livro.capitulos for b in blocos_com_origem(cap) if b.origem.pagina == pagina]


def bloco_no_ponto(livro: Livro, pagina: int, x: float, y: float, dpi: int = DPI_PADRAO) -> tuple[str, Any] | None:
    """O bloco cuja caixa (em pontos) contém `(x, y)` na página; o de menor área, se há mais de um."""
    melhor = None
    for arquivo, bloco in blocos_da_pagina(livro, pagina):
        if not bloco.origem.caixa:
            continue
        x0, y0, x1, y1 = caixa_em_pontos(bloco.origem.caixa, dpi)
        if x0 <= x <= x1 and y0 <= y <= y1:
            area = (x1 - x0) * (y1 - y0)
            if melhor is None or area < melhor[0]:
                melhor = (area, arquivo, bloco)
    return None if melhor is None else (melhor[1], melhor[2])


def suspeitos(livro: Livro) -> list[tuple[str, str]]:
    """`(arquivo, id do bloco)` de todo bloco suspeito, na ordem do livro."""
    return [(cap.arquivo, b.id) for cap in livro.capitulos for b in modelo.blocos_do_capitulo(cap)
            if getattr(b, "extras", {}).get("data-suspeito")]


def vizinha_suspeita(livro: Livro, arquivo: str, bloco_id: str | None, sentido: int = 1) -> tuple[str, str] | None:
    """A suspeita seguinte (`sentido=1`) ou anterior (`-1`) à posição dada, dando a volta no livro."""
    lista = suspeitos(livro)
    if not lista:
        return None
    ordem = {cap.arquivo: k for k, cap in enumerate(livro.capitulos)}
    posicoes: dict[tuple[str, str], int] = {}
    for cap in livro.capitulos:
        for k, b in enumerate(modelo.blocos_do_capitulo(cap)):
            posicoes[(cap.arquivo, b.id)] = k
    atual = (ordem.get(arquivo, 0), posicoes.get((arquivo, bloco_id or ""), -1 if sentido > 0 else 10 ** 9))

    def chave(item: tuple[str, str]) -> tuple[int, int]:
        return ordem.get(item[0], 0), posicoes.get(item, 0)

    if sentido > 0:
        depois = [s for s in lista if chave(s) > atual]
        return depois[0] if depois else lista[0]
    antes = [s for s in lista if chave(s) < atual]
    return antes[-1] if antes else lista[-1]


@dataclass
class Troca:
    """O que `trocar_pagina` fez: quantos blocos saíram e entraram, e em que capítulos."""

    saidos: int
    entrados: int
    capitulos: list[str]


def trocar_pagina(livro: Livro, pagina: int, novos: Iterable[Any]) -> Troca:
    """
    Tira do livro os blocos da página `pagina` (0-based) e põe `novos` no lugar do primeiro
    deles — o que "Reler do PDF" faz com a página relida. Os blocos sem origem (o que o
    usuário escreveu) e a `MarcaDePagina` ficam onde estão.
    """
    novos = [b for b in novos if not isinstance(b, MarcaDePagina)]
    saidos = 0
    capitulos: list[str] = []
    posto = False
    for cap in livro.capitulos:
        blocos: list[Any] = []
        mexeu = False
        for bloco in cap.blocos:
            origem = getattr(bloco, "origem", None)
            if origem is not None and origem.pagina == pagina and not isinstance(bloco, MarcaDePagina):
                saidos += 1
                mexeu = True
                if not posto:
                    blocos.extend(novos)
                    posto = True
                continue
            blocos.append(bloco)
        if mexeu:
            cap.blocos = blocos
            capitulos.append(cap.arquivo)
    if not posto and novos:
        # A página não tinha blocos com origem (apagados à mão): entram depois da marca dela.
        for cap in livro.capitulos:
            for k, bloco in enumerate(cap.blocos):
                if isinstance(bloco, MarcaDePagina) and bloco.pagina == pagina + 1:
                    cap.blocos[k + 1:k + 1] = novos
                    capitulos.append(cap.arquivo)
                    posto = True
                    break
            if posto:
                break
    if not posto and novos:
        raise ValueError(f"a página {pagina + 1} não está neste livro")
    return Troca(saidos, len(novos) if posto else 0, capitulos)


def existe(caminho: str) -> bool:
    return bool(caminho) and os.path.isfile(caminho)


__all__ = ["DPI_PADRAO", "pdf_do_livro", "dpis_do_documento", "caixa_em_pontos", "origem_na_linha",
           "blocos_com_origem", "blocos_da_pagina", "bloco_no_ponto", "suspeitos", "vizinha_suspeita",
           "Troca", "trocar_pagina", "existe"]
