"""
O PGN do capítulo (ED-12; SPEC_EDITOR §11.8, §11.3).

## Uma partida por segmento

Os segmentos de `xadrez.segmentos` (§11.3: um começa num título, num `1.` de brancas
depois de já haver lances, ou num diagrama cujo FEN não bate com a linha) viram
partidas de `chess.pgn`: o STR completo — `Event` (o título do capítulo ou do livro),
`Site "?"`, `Date "????.??.??"`, `Round "?"`, `White`/`Black` do cabeçalho "Nome – Nome"
mais próximo (senão `?`), `Result` do último token de resultado (senão `*`) — e
`[SetUp "1"]` + `[FEN]` quando o segmento começa num diagrama.

## Os lances, as variantes, os comentários e os NAGs

Os tokens saem do mesmo `xadrez.tokens` da validação, com a mesma pilha de variantes
(`(`/`)`: a variante parte da posição **anterior** ao lance que a abre). O texto que
não é token — a prosa entre lances, os parágrafos `comentario` — vira comentário `{}`
do lance anterior. O NAG marcado (`Trecho.nag`) e o digitado unívoco saem como `$n`; o
ambíguo (`=`, `∞`…) sai como `{símbolo}` com aviso. Um lance ilegal encerra a partida
nele, com aviso: o PGN sai até onde a linha é jogável.
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from core.editor import modelo, xadrez
from core.editor.conversao import Cronometro, RelatorioDeConversao
from core.editor.modelo import Bloco, Capitulo, Diagrama, Livro, Paragrafo, Titulo, Trecho

RESULTADOS = {"1-0": "1-0", "0-1": "0-1", "½-½": "1/2-1/2", "1/2-1/2": "1/2-1/2", "*": "*"}


@dataclass
class Partida:
    """O que uma partida do capítulo tem antes de virar `chess.pgn.Game`."""

    cabecalhos: dict[str, str]
    fen_inicial: str = ""
    blocos: list[Bloco] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    lances: int = 0


def cabecalho_proximo(blocos: Sequence[Bloco], inicio: int) -> tuple[str, str]:
    """`(White, Black)` do "Nome – Nome" no título/cabeçalho mais próximo antes (ou no começo) do segmento."""
    for k in range(inicio, -1, -1):
        bloco = blocos[k]
        if isinstance(bloco, Paragrafo) and (isinstance(bloco, Titulo)
                                             or bloco.estilo in ("cabecalho-diagrama", "legenda")):
            m = xadrez._RE_CABECALHO.match(modelo.texto_de(bloco))
            if m:
                return m.group("a").strip(), m.group("b").strip()
            if isinstance(bloco, Titulo) and k < inicio:
                break
    return "?", "?"


def _evento(livro: Livro | None, cap: Capitulo) -> str:
    for bloco in cap.blocos:
        if isinstance(bloco, Titulo) and bloco.nivel == 1:
            return modelo.texto_de(bloco)
    if livro is not None and livro.metadados.titulo:
        return livro.metadados.titulo
    return cap.titulo or "?"


def _nag_de(trechos: Sequence[Trecho], inicio: int, fim: int) -> int | None:
    """O código do NAG marcado no trecho que cobre `[inicio, fim)` do texto do parágrafo, se há."""
    desloc = 0
    for t in trechos:
        desloc += 1 if t.quebra_antes else 0
        a, b = desloc, desloc + len(t.texto)
        if t.papel == "nag" and t.nag is not None and a <= inicio and fim <= b:
            return int(t.nag)
        desloc = b
    return None


def tem_lance(blocos: Sequence[Bloco]) -> bool:
    return any(isinstance(b, Paragrafo) and not isinstance(b, Titulo) and xadrez.e_notacao(b)
               and any(t.tipo == "lance" for t in xadrez.tokens(xadrez._texto_de_notacao(b))) for b in blocos)


class _Escritor:
    def __init__(self, livro: Livro | None, cap: Capitulo, relatorio: RelatorioDeConversao):
        self.livro = livro
        self.cap = cap
        self.relatorio = relatorio
        self.codigos = xadrez._codigo_do_simbolo()

    def partidas(self) -> list[Any]:
        import chess.pgn

        blocos = list(self.cap.blocos)
        saida = []
        k = 0
        for seg in xadrez.segmentos(blocos):
            if not tem_lance(blocos[seg.inicio:seg.fim]):
                continue                                             # um título sem partida não é partida
            k += 1
            game = chess.pgn.Game()
            white, black = cabecalho_proximo(blocos, seg.inicio)
            game.headers["Event"] = _evento(self.livro, self.cap)
            game.headers["Site"] = "?"
            game.headers["Date"] = "????.??.??"
            game.headers["Round"] = str(k)
            game.headers["White"] = white
            game.headers["Black"] = black
            game.headers["Result"] = "*"
            if seg.fen_inicial:
                import chess

                try:
                    game.setup(chess.Board(seg.fen_inicial if len(seg.fen_inicial.split()) >= 2
                                           else seg.fen_inicial + " w - - 0 1"))
                except ValueError:
                    self.relatorio.aviso(f"partida {k}: FEN inicial inválido ({seg.fen_inicial}); começa da inicial")
            if seg.aviso:
                self.relatorio.aviso(f"partida {k}: {seg.aviso}")
            resultado = self._lances(game, blocos[seg.inicio:seg.fim], k)
            game.headers["Result"] = resultado
            saida.append(game)
        return saida

    def _lances(self, game: Any, blocos: Sequence[Bloco], numero: int) -> str:
        node = game
        pilha: list[Any] = []
        resultado = "*"
        comentario: list[str] = []

        def fechar_comentario() -> None:
            texto = " ".join(" ".join(comentario).split())
            if texto.startswith("{") and texto.endswith("}"):
                texto = texto[1:-1].strip()                          # já veio entre chaves no impresso
            texto = texto.replace("{", "(").replace("}", ")")
            if texto:
                node.comment = (node.comment + " " + texto).strip() if node.comment else texto
            comentario.clear()

        for bloco in blocos:
            if isinstance(bloco, Diagrama):
                continue
            if not isinstance(bloco, Paragrafo):
                continue
            if isinstance(bloco, Titulo) or not xadrez.e_notacao(bloco):
                if bloco.estilo == "comentario" or (not isinstance(bloco, Titulo)
                                                    and bloco.estilo in xadrez.ESTILOS_DE_NOTACAO):
                    comentario.append(modelo.texto_de(bloco))
                continue
            texto = xadrez._texto_de_notacao(bloco)
            cursor = 0
            for token in xadrez.tokens(texto):
                prosa = texto[cursor:token.inicio].strip()
                if prosa and token.tipo != "numero":
                    comentario.append(prosa)
                elif prosa:
                    comentario.append(prosa)
                cursor = token.fim
                if token.tipo == "numero":
                    continue
                if token.tipo == "abre":
                    fechar_comentario()
                    pilha.append(node)
                    node = node.parent if node.parent is not None else node
                    continue
                if token.tipo == "fecha":
                    fechar_comentario()
                    if pilha:
                        node = pilha.pop()
                    continue
                if token.tipo == "resultado":
                    fechar_comentario()
                    resultado = RESULTADOS.get(token.texto, "*")
                    continue
                if token.tipo == "nag":
                    codigo = _nag_de(bloco.trechos, token.inicio, token.fim)
                    if codigo is None:
                        codigo = self.codigos.get(token.texto)
                    if codigo is None:
                        comentario.append(token.texto)
                        self.relatorio.aviso(f"partida {numero}: NAG sem código no padrão ({token.texto}) saiu como "
                                             f"comentário")
                    elif node is not game:
                        node.nags.add(codigo)
                    continue
                if token.tipo == "lance":
                    fechar_comentario()
                    board = node.board()
                    try:
                        movimento = board.parse_san(xadrez.lance_em_san(token.texto).rstrip("!?"))
                    except ValueError:
                        self.relatorio.aviso(f"partida {numero}: {token.texto} não é legal — a partida sai até ele")
                        prosa_final = texto[cursor:].strip()
                        if prosa_final:
                            comentario.append(prosa_final)
                        fechar_comentario()
                        return resultado
                    node = node.add_variation(movimento)
            resto = texto[cursor:].strip()
            if resto:
                comentario.append(resto)
        fechar_comentario()
        return resultado


def texto_do_capitulo(cap: Capitulo, livro: Livro | None = None,
                      relatorio: RelatorioDeConversao | None = None) -> str:
    """O PGN do capítulo como texto (uma partida por segmento); os avisos vão ao `relatorio`, se dado."""
    import chess.pgn

    relatorio = relatorio if relatorio is not None else RelatorioDeConversao(formato="pgn")
    partidas = _Escritor(livro, cap, relatorio).partidas()
    textos = [game.accept(chess.pgn.StringExporter(headers=True, variations=True, comments=True))
              for game in partidas]                                  # um exportador por partida: ele acumula
    relatorio.metadados["partidas"] = len(partidas)
    return "\n\n".join(textos) + ("\n" if textos else "")


def escrever(cap: Capitulo, caminho: str, livro: Livro | None = None) -> RelatorioDeConversao:
    """Exportar PGN do capítulo…: grava o PGN em `caminho` (UTF-8, `\\n`) e devolve o relatório (§10.8)."""
    caminho = os.fspath(caminho)
    relatorio = RelatorioDeConversao(formato="pgn", arquivos=[caminho])
    with Cronometro(relatorio):
        texto = texto_do_capitulo(cap, livro, relatorio)
        with io.open(caminho, "w", encoding="utf-8", newline="\n") as f:
            f.write(texto)
        relatorio.capitulos = 1
        relatorio.blocos = len(cap.blocos)
        relatorio.diagramas_png = sum(1 for b in cap.blocos if isinstance(b, Diagrama) and b.modo == "png")
        relatorio.diagramas_fonte = sum(1 for b in cap.blocos if isinstance(b, Diagrama) and b.modo == "fonte")
        relatorio.notas = len(cap.notas)
    return relatorio


def partidas_do_livro(livro: Livro) -> list[tuple[Capitulo, int, str, str]]:
    """`(capítulo, número da partida no livro, White, Black)` de todo segmento — é o que o índice de partidas lista."""
    saida: list[tuple[Capitulo, int, str, str]] = []
    n = 0
    for cap in livro.capitulos:
        blocos = list(cap.blocos)
        for seg in xadrez.segmentos(blocos):
            if not tem_lance(blocos[seg.inicio:seg.fim]):
                continue
            n += 1
            white, black = cabecalho_proximo(blocos, seg.inicio)
            saida.append((cap, n, white, black))
    return saida


_RE_TAG = re.compile(r'^\[(\w+)\s+"(.*)"\]$', re.M)


def tags(texto_pgn: str) -> list[dict[str, str]]:
    """Os cabeçalhos de cada partida de um texto PGN (o que os testes conferem sem o `chess.pgn`)."""
    saida: list[dict[str, str]] = []
    atual: dict[str, str] = {}
    for linha in texto_pgn.splitlines():
        m = _RE_TAG.match(linha)
        if m:
            atual[m.group(1)] = m.group(2)
        elif atual and linha.strip():
            saida.append(atual)
            atual = {}
    if atual:
        saida.append(atual)
    return saida


__all__ = ["escrever", "texto_do_capitulo", "partidas_do_livro", "tags", "cabecalho_proximo", "tem_lance", "Partida",
           "RESULTADOS"]
