"""
Os índices de jogadores, partidas e aberturas (ED-12; SPEC_EDITOR §11.9).

## O que entra e como se ordena

O índice de **jogadores** lista os trechos `papel="jogador"` pela `Trecho.chave`
("Wely, Loek van", e não "Loek van Wely" — é a chave que ordena, sem acento e sem caixa);
o de **aberturas**, os `papel="abertura"` pela chave (o código ECO); o de **partidas**,
cada segmento com lances (§11.3), na ordem do livro, como "n. Brancas – Pretas". Cada
ocorrência vira um link ao título (ou diagrama) mais próximo **antes** dela, com o
número da partida em que está — e o alvo ganha `id_persistente`, porque o link precisa
do `id` no XHTML.

## A página

Um capítulo `semantica="index"` (`<body epub:type="index">`; o HTML exportado leva
`role="doc-index"` pelo mapa da ED-10), um parágrafo `p.indice` por entrada, refeito no
lugar quando já existe (pelo arquivo `Text/indice-<tipo>.xhtml`) e no fim do livro
quando não.
"""

from __future__ import annotations

import posixpath
import unicodedata
from dataclasses import dataclass, field
from typing import Sequence

from core.editor import modelo, pgn_io, xadrez
from core.editor.modelo import Bloco, Capitulo, Diagrama, Livro, Paragrafo, Titulo, Trecho

TIPOS = ("jogadores", "partidas", "aberturas")
TITULOS = {"pt": {"jogadores": "Índice de jogadores", "partidas": "Índice de partidas",
                  "aberturas": "Índice de aberturas"},
           "en": {"jogadores": "Index of players", "partidas": "Index of games", "aberturas": "Index of openings"}}
VAZIO = {"pt": "(nada marcado no livro)", "en": "(nothing marked in the book)"}


@dataclass
class Ocorrencia:
    arquivo: str            # o capítulo
    alvo_id: str            # o id do título/diagrama mais próximo (persistente)
    partida: int | None     # o número da partida no livro, quando a ocorrência está numa
    texto: str = ""


@dataclass
class Entrada:
    chave: str
    ocorrencias: list[Ocorrencia] = field(default_factory=list)


def _ordem(chave: str) -> str:
    """A chave sem acentos e sem caixa, para ordenar "Wely, Loek van" entre W e não entre L."""
    plana = unicodedata.normalize("NFKD", chave)
    return "".join(c for c in plana if not unicodedata.combining(c)).casefold()


def _partidas(livro: Livro) -> dict[str, list[tuple[int, int, int]]]:
    """Por capítulo, `(início, fim, número da partida no livro)` de cada segmento com lances."""
    saida: dict[str, list[tuple[int, int, int]]] = {}
    n = 0
    for cap in livro.capitulos:
        blocos = list(cap.blocos)
        faixas: list[tuple[int, int, int]] = []
        for seg in xadrez.segmentos(blocos):
            if not pgn_io.tem_lance(blocos[seg.inicio:seg.fim]):
                continue
            n += 1
            faixas.append((seg.inicio, seg.fim, n))
        saida[cap.arquivo] = faixas
    return saida


def _numero_da_partida(faixas: Sequence[tuple[int, int, int]], i: int) -> int | None:
    for inicio, fim, n in faixas:
        if inicio <= i < fim:
            return n
    return None


def _alvo(blocos: Sequence[Bloco], i: int) -> Bloco:
    """O título ou diagrama mais próximo antes (ou o próprio bloco); o id vira persistente."""
    for k in range(i, -1, -1):
        if isinstance(blocos[k], (Titulo, Diagrama)):
            blocos[k].id_persistente = True
            return blocos[k]
    blocos[i].id_persistente = True
    return blocos[i]


def _entradas_de_papel(livro: Livro, papel: str) -> list[Entrada]:
    faixas = _partidas(livro)
    por_chave: dict[str, Entrada] = {}
    for cap in livro.capitulos:
        blocos = list(cap.blocos)
        for i, bloco in enumerate(blocos):
            for t in modelo._todos_os_trechos(bloco):
                if t.papel != papel or not (t.chave or t.texto.strip()):
                    continue
                chave = t.chave or (xadrez.chave_de_jogador(t.texto) if papel == "jogador" else t.texto.strip())
                alvo = _alvo(blocos, i)
                entrada = por_chave.setdefault(chave, Entrada(chave))
                ocorrencia = Ocorrencia(cap.arquivo, alvo.id, _numero_da_partida(faixas.get(cap.arquivo, ()), i),
                                        t.texto.strip())
                if not any(o.alvo_id == ocorrencia.alvo_id and o.arquivo == ocorrencia.arquivo
                           for o in entrada.ocorrencias):
                    entrada.ocorrencias.append(ocorrencia)
    return [por_chave[c] for c in sorted(por_chave, key=_ordem)]


def entradas(livro: Livro, tipo: str) -> list[Entrada]:
    """As entradas do índice `tipo`, ordenadas (jogadores e aberturas pela chave; partidas pela ordem do livro)."""
    if tipo == "jogadores":
        return _entradas_de_papel(livro, "jogador")
    if tipo == "aberturas":
        return _entradas_de_papel(livro, "abertura")
    if tipo != "partidas":
        raise ValueError(f"índice desconhecido: {tipo!r} (há: {', '.join(TIPOS)})")
    saida: list[Entrada] = []
    faixas = _partidas(livro)
    for cap in livro.capitulos:
        blocos = list(cap.blocos)
        for inicio, _fim, n in faixas.get(cap.arquivo, ()):
            white, black = pgn_io.cabecalho_proximo(blocos, inicio)
            alvo = _alvo(blocos, inicio)
            saida.append(Entrada(f"{n}. {white} – {black}", [Ocorrencia(cap.arquivo, alvo.id, n, "")]))
    return saida


def _link(arquivo_do_indice: str, ocorrencia: Ocorrencia) -> str:
    if posixpath.dirname(arquivo_do_indice) == posixpath.dirname(ocorrencia.arquivo):
        return f"{posixpath.basename(ocorrencia.arquivo)}#{ocorrencia.alvo_id}"
    return f"{ocorrencia.arquivo}#{ocorrencia.alvo_id}"


def gerar(livro: Livro, tipo: str = "jogadores", idioma: str = "pt") -> Capitulo:
    """
    A página do índice `tipo` (§11.9): `semantica="index"`, um `p.indice` por entrada com a chave
    e os links (o número da partida, ou `·` fora de partida). Refeita no lugar quando já existe;
    senão entra no fim do livro. Devolve o capítulo.
    """
    if tipo not in TIPOS:
        raise ValueError(f"índice desconhecido: {tipo!r} (há: {', '.join(TIPOS)})")
    idioma = idioma.split("-")[0].lower()
    idioma = idioma if idioma in TITULOS else "pt"
    vizinho = livro.capitulos[-1] if livro.capitulos else None
    pasta = posixpath.dirname(vizinho.arquivo) if vizinho is not None else "Text"
    arquivo = posixpath.join(pasta, f"indice-{tipo}.xhtml") if pasta else f"indice-{tipo}.xhtml"
    lista = entradas(livro, tipo)
    blocos: list[Bloco] = [Titulo(trechos=[Trecho(texto=TITULOS[idioma][tipo])], nivel=1)]
    if not lista:
        blocos.append(Paragrafo(trechos=[Trecho(texto=VAZIO[idioma])]))
    for entrada in lista:
        trechos = [Trecho(texto=entrada.chave, negrito=(tipo != "partidas"))]
        for k, oc in enumerate(entrada.ocorrencias):
            rotulo = str(oc.partida) if oc.partida is not None else "·"
            trechos.append(Trecho(texto="  " if k == 0 else ", "))
            trechos.append(Trecho(texto=rotulo, link=_link(arquivo, oc)))
        blocos.append(Paragrafo(trechos=trechos, classe="indice"))
    existente = next((c for c in livro.capitulos if c.arquivo == arquivo), None)
    if existente is not None:
        existente.blocos = blocos
        existente.semantica = "index"
        existente.titulo = TITULOS[idioma][tipo]
        return existente
    cap = Capitulo(arquivo=arquivo, titulo=TITULOS[idioma][tipo], blocos=blocos, semantica="index",
                   folhas=list(vizinho.folhas) if vizinho is not None else list(livro.folhas[:1]),
                   idioma=vizinho.idioma if vizinho is not None else "")
    livro.capitulos.append(cap)
    return cap


__all__ = ["gerar", "entradas", "Entrada", "Ocorrencia", "TIPOS", "TITULOS"]
