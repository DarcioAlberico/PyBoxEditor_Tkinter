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
from difflib import SequenceMatcher
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


_LEGENDAS_DE_TURNO = (
    ("White to play", "white to play"),
    ("Black to play", "black to play"),
    ("White to move", "white to move"),
    ("Black to move", "black to move"),
    ("White to play and win", "white to play and win"),
    ("Black to play and win", "black to play and win"),
)


def normalizar_legenda(texto: Optional[str]) -> str:
    """Recupera uma legenda curta quando o OCR a deformou severamente.

    A correção só considera as frases de vez conhecidas e exige margem entre
    a melhor e a segunda candidata. Não é aplicada a prosa: uma legenda
    vizinha ao diagrama pode alimentar o FEN e, por isso, merece uma regra
    pequena e explícita em vez do corretor lexical geral.
    """
    original = str(texto or "").strip()
    if not original or ler(original):
        return original
    dobrado = dobrar(original)
    compacto = dobrado.replace(" ", "")
    if len(compacto) < 5 or len(compacto) > 28:
        return original
    candidatos = []
    for exibicao, chave in _LEGENDAS_DE_TURNO:
        similaridade = SequenceMatcher(None, compacto, chave.replace(" ", "")).ratio()
        candidatos.append((similaridade, exibicao))
    candidatos.sort(reverse=True)
    melhor, nome = candidatos[0]
    segunda = candidatos[1][0]
    if melhor >= 0.74 and melhor - segunda >= 0.08:
        return nome
    return original


def ler_varios(*textos: Optional[str]) -> LadoLido:
    """
    O lado dito por um dos textos em volta do diagrama — o de cima e o de baixo.

    Lidos em separado, e não emendados num só: `dobrar` apaga a pontuação, e um
    "as brancas" que termina o cabeçalho colado a um "jogam" que abre a legenda
    inventaria uma frase que a página não tem. Dois textos que discordam são
    `ambigua`, pela mesma razão que dois lados na mesma legenda o são.
    """
    lidos = [item for item in (
        ler(normalizar_legenda(texto)) for texto in textos if texto
    ) if item]
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


# ----------------------------------------------------------------------
# O lado pelo último lance do texto
# ----------------------------------------------------------------------

_LETRA_DA_FIGURINA = {"♔": "K", "♕": "Q", "♖": "R", "♗": "B", "♘": "N",
                      "♚": "K", "♛": "Q", "♜": "R", "♝": "B", "♞": "N"}
_PECAS_DO_LANCE = "KQRBN" + "".join(_LETRA_DA_FIGURINA)
_ROQUE = r"[0O][-–—][0O](?:[-–—][0O])?"
# A promoção só existe no lance de peão que chega à fila 1 ou 8: o `N` de
# novidade colado ao lance (`16...d5N`) não é cavalo.
_SAN = (rf"(?:{_ROQUE}|(?:[a-h][x:]?)?[a-h][18]=?[QRBN♕♖♗♘]"
        rf"|[{_PECAS_DO_LANCE}]?[a-h]?[1-8]?[x:]?[a-h][1-8])")

#: `10.e4 ♘b6`, `23.♘xd8,`, `16...♘e8!?N`: o número, o lance e, depois do das
#: brancas, o das pretas quando vem colado. O que segue o lance sem espaço
#: (`!?`, `†`, `⩲`, a vírgula) é anotação.
_LANCE_NUMERADO = re.compile(
    rf"(?<![\w.])(\d{{1,3}})\s?(\.\s?\.\.\.|\.\.\.|…|\.)\s?({_SAN})\S*"
    rf"(?:\s+({_SAN})(?![\w.])\S*)?")

#: Onde ficam o rei e a torre depois de cada roque, por cor.
_DEPOIS_DO_ROQUE = {
    ("w", False): {"g1": "K", "f1": "R"}, ("w", True): {"c1": "K", "d1": "R"},
    ("b", False): {"g8": "k", "f8": "r"}, ("b", True): {"c8": "k", "d8": "r"},
}


def _casas(fen: str) -> dict[str, str]:
    """`{casa: peça do FEN}` do campo das peças."""
    casas: dict[str, str] = {}
    campos = str(fen or "").split()
    fileiras = campos[0].split("/") if campos else []
    if len(fileiras) != 8:
        return casas
    for i, fileira in enumerate(fileiras):
        coluna = 0
        for c in fileira:
            if c.isdigit():
                coluna += int(c)
            else:
                if coluna < 8:
                    casas["abcdefgh"[coluna] + str(8 - i)] = c
                coluna += 1
    return casas


def _lance_confere(san: str, cor: str, casas: dict[str, str]) -> bool:
    """A peça que fez `san` está na casa de chegada do tabuleiro?"""
    if re.fullmatch(_ROQUE, san):
        longo = san.count(san[1]) >= 2
        esperado = _DEPOIS_DO_ROQUE[(cor, longo)]
        return all(casas.get(casa) == peca for casa, peca in esperado.items())
    destino = re.findall(r"[a-h][1-8]", san)[-1]
    promocao = re.search(r"=?([QRBN♕♖♗♘])$", san)
    if promocao:
        letra = _LETRA_DA_FIGURINA.get(promocao.group(1), promocao.group(1))
    else:
        letra = _LETRA_DA_FIGURINA.get(san[0], san[0]) if san[0] in _PECAS_DO_LANCE else "P"
    return casas.get(destino) == (letra if cor == "w" else letra.lower())


def tem_lance(texto: Optional[str]) -> bool:
    """O texto tem um lance numerado (`12.♕xc4`, `16...d3`)?"""
    return bool(_LANCE_NUMERADO.search(str(texto or "")))


def pelo_lance(texto: str, fen: str, seguinte: Optional[str] = None) -> Optional[str]:
    """
    O lado a jogar pelo último lance escrito antes do diagrama, **conferido nele**.

    O livro de partidas comentadas põe o diagrama depois do lance que leva à
    posição, e quase nunca diz de quem é a vez: `9.e4 ♕h5 10.♘xc4` em cima do
    tabuleiro são as pretas a jogar; `8...♕h5 9.♘xc4 ♘bd5 10.e4 ♘b6`, as
    brancas. Ler o lance não basta — o parágrafo antes do diagrama pode ser uma
    variante que não chega a ele —, e por isso a peça que fez o último lance
    tem de estar na casa de chegada (o rei e a torre, no roque). Não conferindo,
    ou sem lance no texto, sai `None` e o diagrama segue com a convenção
    declarada.

    **E o texto depois do diagrama tem de continuar dali**, quando `seguinte`
    é dado: depois de `10.♘xc4` o próximo lance numerado é `10...`, e depois
    de `10...♘b6`, `11.`. A peça na casa de chegada confere por coincidência
    — no Dvoretsky, um rei que voltou à casa de um exemplo anterior —, a
    numeração que continua não: o exemplo novo recomeça em `1.`.
    """
    achados = list(_LANCE_NUMERADO.finditer(str(texto or "")))
    casas = _casas(fen)
    if not achados or not casas:
        return None
    ultimo = achados[-1]
    numero = int(ultimo.group(1))
    reticencias = ultimo.group(2) != "."
    if reticencias or ultimo.group(4):
        san, cor = (ultimo.group(3) if reticencias else ultimo.group(4)), "b"
    else:
        san, cor = ultimo.group(3), "w"
    if not _lance_confere(san, cor, casas):
        return None
    lado = "w" if cor == "b" else "b"
    if seguinte is not None:
        proximo = _LANCE_NUMERADO.search(str(seguinte))
        if proximo is None:
            return None
        esperado = (numero, True) if lado == "b" else (numero + 1, False)
        if (int(proximo.group(1)), proximo.group(2) != ".") != esperado:
            return None
    return lado


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

#: A ressalva do diagrama cuja posição ninguém conferiu (PD-21), atrás do lado
#: a jogar no mesmo `alt` e na mesma legenda — `<FEN> — brancas a jogar
#: (assumido: a página não diz); não revisado`. Sai em todos os modos, inclusive
#: no limpo: a ressalva é para quem lê, e não para quem revisa (§4.6 da revisão
#: de 2026-09-18). `do_alt` não a lê: ela não muda o FEN nem o lado.
NAO_REVISADO = "não revisado"

_PROCEDENCIA = {
    "legenda": "da legenda", "legend": "da legenda",
    "legalidade": "inferido pela legalidade da posição",
    "lance": "pelo último lance do texto",
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
