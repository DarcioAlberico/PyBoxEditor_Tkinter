"""
De quem é a vez — lido da legenda quando a página diz, e carimbado quando não.

Um tabuleiro desenhado não contém o lado a jogar: as 64 casas dizem onde estão
as peças e mais nada. O FEN, porém, **exige** o campo, e até aqui os dois
caminhos do programa o preenchiam com `w` em silêncio — `Leitura.fen`, a Fase 4
e o `TabuleiroEdicao` todos assumiam brancas. Um FEN abre em qualquer programa
de xadrez e vira fato; "brancas a jogar" por convenção é exatamente o tipo de
afirmação que ninguém confere e que muda a análise inteira de um final.

**A página costuma dizer, e em quatro palavras.** "White to play" está impresso
embaixo de metade dos diagramas do Nunn, "Black to move" embaixo da outra
metade; o Yusupov põe `➤ Ex. 22-4 ◀ ★★ ▼` em cima, e aquele `▼` é o NAG de
"negras jogam" — a única coisa naquela página que diz de quem é a vez. Quando
está escrito, isto lê; quando não está, quem chamar recebe `None` e tem de dizer
no `alt`, na legenda e na fila que o `w` do FEN é convenção, e não leitura.

**Duas cores na mesma legenda não decidem nada.** A página 237 do Nunn abre com
`W=White to play B=Black to play` — é a chave de uma tabela, não a vez de um
diagrama. Achar as duas e escolher a primeira seria pior que não achar: aqui
isso é `ambigua`, e o chamador segue com a convenção declarada.

O texto chega de OCR, então a comparação é feita sobre a forma dobrada: sem
acento, sem caixa, com os separadores todos virados em espaço e as figurinas
trocadas pela cor que elas são (`♔ to play` é `white to play`).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

#: Os dois valores que o campo do FEN aceita.
LADOS = ("w", "b")

#: O que se diz quando ninguém disse. Vai para o `alt`, para a legenda e para a
#: fila de suspeitas — é o que impede a convenção de passar por leitura.
AVISO_ASSUMIDO = ("o lado a jogar não está no diagrama nem na legenda; "
                  "o FEN assume brancas a jogar")

#: E quando a legenda disse, o mesmo aviso ao contrário: o lado é leitura, mas
#: de fora do tabuleiro, e o roque continua sendo convenção.
AVISO_DA_LEGENDA = ("o lado a jogar vem da legenda da página, e não do "
                    "tabuleiro; roque e en passant continuam por convenção")

_BRANCAS = "♔♕♖♗♘♙"
_PRETAS = "♚♛♜♝♞♟"

#: Os dois símbolos que **sozinhos** dizem de quem é a vez.
#:
#: São os da família "Lado" de `core/nags.py`, e no Yusupov são a única coisa na
#: página que o diz: o cabeçalho do exercício é `➤ Ex. 22-4 ◀ ★★ ▼`, e aquele
#: `▼` é "negras jogam". Ao contrário das frases, dispensam verbo — por isso são
#: procurados no texto cru, antes de `dobrar` os apagar como pontuação.
SIMBOLOS_DO_LADO = {"△": "w", "▼": "b"}

_COR = {
    "white": "w", "black": "b",
    "brancas": "w", "pretas": "b", "negras": "b",
    "blancas": "w", "weiss": "w", "schwarz": "b",
}

_PADROES = (
    # "White to move", "Black to play and win", "W=White to play"
    re.compile(r"\b(white|black|weiss|schwarz)\s+(?:is\s+)?to\s+(?:move|play)\b"),
    re.compile(r"\b(white|black)\s+(?:is\s+)?on\s+(?:the\s+)?move\b"),
    # "As brancas jogam", "pretas a jogar", "negras no lance"
    re.compile(r"\b(?:as\s+)?(brancas|pretas|negras)\s+"
               r"(?:jogam|movem|a\s+jogar|no\s+lance|para\s+jogar)\b"),
    re.compile(r"\bjogam\s+(?:as\s+)?(brancas|pretas|negras)\b"),
    re.compile(r"\bvez\s+d(?:as|e)\s+(brancas|pretas|negras)\b"),
    # "Juegan las blancas", "negras juegan"
    re.compile(r"\bjuegan\s+(?:las\s+)?(blancas|negras)\b"),
    re.compile(r"\b(blancas|negras)\s+juegan\b"),
)


@dataclass(frozen=True)
class LadoLido:
    """
    O lado a jogar que saiu de um texto, e de onde ele saiu.

    `origem` é `legenda` quando o texto disse, `ambigua` quando disse as duas
    coisas e `ausente` quando não disse nada. Só a primeira traz `lado`.
    """

    lado: Optional[str] = None
    origem: str = "ausente"
    trecho: str = ""

    def __bool__(self) -> bool:
        return self.lado is not None


def dobrar(texto: str) -> str:
    """
    A forma em que a comparação é feita: sem acento, sem caixa, sem figurina.

    O `NFKD` separa o acento da letra e o filtro tira a marca; as figurinas
    viram a cor que elas são, com espaço em volta, para `♔to play` — que é
    como sai um OCR sem o espaço fino — casar igual a `White to play`.
    """
    limpo = []
    for caractere in unicodedata.normalize("NFKD", str(texto or "")):
        if unicodedata.combining(caractere):
            continue
        if caractere in _BRANCAS:
            limpo.append(" white ")
        elif caractere in _PRETAS:
            limpo.append(" black ")
        elif caractere.isalnum():
            limpo.append(caractere)
        else:
            limpo.append(" ")
    return re.sub(r"\s+", " ", "".join(limpo)).strip().casefold()


def ler(texto: str) -> LadoLido:
    """O lado a jogar dito por uma legenda, ou `LadoLido()` quando não há."""
    cru = str(texto or "")
    # Os símbolos são procurados **antes** da dobra, que os apagaria junto com a
    # pontuação — e um cabeçalho que é só `▼` não tem outra coisa que o diga.
    achados: list[tuple[str, str]] = [
        (cor, simbolo) for simbolo, cor in SIMBOLOS_DO_LADO.items()
        if simbolo in cru]
    dobrado = dobrar(cru)
    for padrao in _PADROES:
        for encontro in padrao.finditer(dobrado):
            cor = _COR.get(encontro.group(1))
            if cor:
                achados.append((cor, encontro.group(0)))
    if not achados:
        return LadoLido()
    lados = {cor for cor, _trecho in achados}
    if len(lados) > 1:
        return LadoLido(None, "ambigua", "; ".join(t for _c, t in achados))
    cor, trecho = achados[0]
    return LadoLido(cor, "legenda", trecho)


def ler_varios(*textos: Optional[str]) -> LadoLido:
    """
    O lado dito por um dos textos em volta do diagrama — o de cima e o de baixo.

    Lidos em separado, e não emendados num só: `dobrar` apaga a pontuação, e um
    "as brancas" que termina o cabeçalho colado a um "jogam" que abre a legenda
    inventaria uma frase que a página não tem. Dois textos que discordam são
    `ambigua`, pela mesma razão que dois lados na mesma legenda o são.
    """
    lidos = [item for item in (ler(texto) for texto in textos if texto) if item]
    if not lidos:
        return LadoLido()
    lados = {item.lado for item in lidos}
    if len(lados) > 1:
        return LadoLido(None, "ambigua",
                        "; ".join(item.trecho for item in lidos))
    return lidos[0]


def com_lado(fen: str, lado: Optional[str]) -> str:
    """
    O mesmo FEN com o campo de quem joga trocado.

    Trocar o campo, e não remontar o FEN, é o que preserva roque e en passant de
    quem já os tinha. Um FEN só de peças ganha os campos que faltam; `lado`
    vazio ou desconhecido devolve o FEN como estava.
    """
    texto = str(fen or "").strip()
    if not texto or lado not in LADOS:
        return texto
    campos = texto.split()
    if len(campos) == 1:
        return f"{campos[0]} {lado} - - 0 1"
    campos[1] = lado
    return " ".join(campos)


def do_fen(fen: str) -> Optional[str]:
    """O lado que um FEN declara, ou `None` se ele não tem o campo."""
    campos = str(fen or "").split()
    return campos[1] if len(campos) > 1 and campos[1] in LADOS else None


#: O que separa o FEN da ressalva no texto alternativo da figura.
#:
#: O `alt` é lido de volta: o editor de livros reconstrói o diagrama do EPUB
#: exportado a partir dele (`core/editor/xhtml.py`). Por isso o FEN vem
#: **inteiro e na frente**, e a ressalva atrás de um separador que não aparece
#: dentro de um FEN.
SEPARADOR_DO_ALT = " — "

#: A palavra que abre toda procedência que **não** é leitura. É o contrato
#: entre quem escreve o `alt` e quem o lê de volta.
ASSUMIDO = "assumido"

_PROCEDENCIA = {
    "legenda": "da legenda", "legend": "da legenda",
    "usuario": "informado na revisão", "manual": "informado na revisão",
    "explicit": "informado na revisão", "explícito": "informado na revisão",
    "ambigua": f"{ASSUMIDO}: a legenda fala dos dois lados",
    "ambiguous": f"{ASSUMIDO}: a legenda fala dos dois lados",
}
_PROCEDENCIA_PADRAO = f"{ASSUMIDO}: a página não diz"


def marca(lado: Optional[str], origem: str) -> str:
    """
    A frase curta que vai para o `alt`, para a legenda e para a barra de status.

    Sempre diz **de onde** o lado veio: o leitor de tela e a busca do arquivo
    exportado são os dois lugares em que a convenção passaria por leitura se
    ninguém escrevesse nada.
    """
    nome = {"w": "brancas", "b": "pretas"}.get(lado or "", "brancas")
    return f"{nome} a jogar ({_PROCEDENCIA.get(origem, _PROCEDENCIA_PADRAO)})"


def do_alt(alt: str) -> tuple[str, str]:
    """
    O caminho de volta do `alt`: ``(FEN, lado lido)``.

    O segundo é vazio quando a ressalva diz que o lado foi assumido — quem lê o
    arquivo de volta não pode herdar como leitura um campo que o escritor
    declarou convenção. É o que mantém a DEC-06 valendo no round-trip.
    """
    texto = str(alt or "").strip()
    fen, _sep, ressalva = texto.partition(SEPARADOR_DO_ALT)
    fen = fen.strip()
    dentro = ressalva.partition("(")[2].strip()
    if not dentro or dentro.startswith(ASSUMIDO):
        return fen, ""
    return fen, do_fen(fen) or ""
