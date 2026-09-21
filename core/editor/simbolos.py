"""
A caixa de símbolos e o código Unicode ↔ caractere (ED-06; SPEC_EDITOR §9 "Special
Characters", §7.3 Inserir).

As categorias são fixas e curtas — o que um livro de xadrez em português precisa à
mão: as figurinas (as pretas ficam aqui, a barra só tem as brancas, §7.1), os NAGs e
sinais de avaliação, a tipografia (aspas, travessões, reticências, os espaços e hifens
invisíveis), setas, matemática, letras acentuadas e o resto por **busca pelo nome**
Unicode (`unicodedata.name`): "BLACK CHESS" lista `♚♛♜♝♞♟` (AC-ED06-6). A busca varre
uma faixa fixa de códigos (`FAIXAS`), montada uma vez — os 65 mil do BMP levariam
segundos a cada tecla.

`Ctrl+Shift+X` é o `Alt+X` do Word: o hexadecimal antes do cursor vira o caractere
(`2A72` → `⩲`) e o caractere antes do cursor vira o seu código (`⩲` → `2A72`).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

#: `(rótulo, caracteres)` — as categorias da caixa, na ordem.
CATEGORIAS: tuple[tuple[str, str], ...] = (
    ("Figurinas", "♔♕♖♗♘♙♚♛♜♝♞♟"),
    ("Avaliação e NAGs", "!?‼⁇⁉⁈±∓⩲⩱=∞⯹□■△▼○●⟳↑↗⇆⇔⨀⊕⊖⩹⩺"),
    ("Tipografia", "“”‘’«»‹›„‚–—…·•§¶†‡°′″\u00a0\u2011\u00ad\u200b"),
    ("Setas", "←↑→↓↔↕↖↗↘↙⇐⇒⇔⇦⇨"),
    ("Matemática", "×÷±−≠≤≥≈≡∞√∑∏∫∂∆∇∈∉∪∩⊂⊃⊆⊇½⅓⅔¼¾⅛⅜⅝⅞"),
    ("Letras", "áàâãäåæçéèêëíìîïñóòôõöøœúùûüýÿßÁÀÂÃÄÅÆÇÉÈÊËÍÌÎÏÑÓÒÔÕÖØŒÚÙÛÜÝ"),
    ("Grego", "αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ"),
    ("Moedas e sinais", "€£¥¢©®™¤"),
)
#: Os nomes de tela dos caracteres que não se veem.
NOMES_DOS_INVISIVEIS = {"\u00a0": "espaço inseparável", "\u2011": "hífen inseparável", "\u00ad": "hífen opcional",
                        "\u200b": "espaço de largura zero", "\u2009": "espaço fino",
                        "\u202f": "espaço fino inseparável"}
#: As faixas de código que a busca por nome varre (o BMP inteiro custaria segundos por tecla).
FAIXAS = ((0x0020, 0x052F), (0x1E00, 0x1EFF), (0x2000, 0x2BFF), (0x2E00, 0x2E7F), (0xFB00, 0xFB4F),
          (0x1D400, 0x1D7FF), (0x1F000, 0x1F0FF), (0x1F300, 0x1F64F), (0x1F680, 0x1F6FF), (0x1F900, 0x1F9FF))
_RE_HEX = re.compile(r"(?:U\+|u\+|0x|0X)?([0-9A-Fa-f]{2,6})$")
_INDICE: list[tuple[str, str]] | None = None


@dataclass(frozen=True)
class Simbolo:
    caractere: str
    nome: str

    @property
    def codigo(self) -> str:
        return caractere_para_codigo(self.caractere)


def nome_de(caractere: str) -> str:
    if caractere in NOMES_DOS_INVISIVEIS:
        return NOMES_DOS_INVISIVEIS[caractere]
    try:
        return unicodedata.name(caractere).lower()
    except ValueError:
        return f"U+{ord(caractere):04X}"


def simbolos_da_categoria(rotulo: str) -> list[Simbolo]:
    for nome, caracteres in CATEGORIAS:
        if nome == rotulo:
            return [Simbolo(c, nome_de(c)) for c in caracteres]
    raise KeyError(rotulo)


def _indice() -> list[tuple[str, str]]:
    """`(caractere, NOME)` de toda a faixa, montado uma vez."""
    global _INDICE
    if _INDICE is None:
        saida: list[tuple[str, str]] = []
        for ini, fim in FAIXAS:
            for codigo in range(ini, fim + 1):
                c = chr(codigo)
                try:
                    saida.append((c, unicodedata.name(c)))
                except ValueError:
                    continue
        _INDICE = saida
    return _INDICE


def procurar(consulta: str, limite: int = 200) -> list[Simbolo]:
    """
    Os caracteres cujo nome Unicode contém todas as palavras da consulta ("BLACK CHESS"
    → `♚♛♜♝♞♟`), ou o caractere do código quando a consulta é um hexadecimal (`2A72`).
    """
    consulta = consulta.strip()
    if not consulta:
        return []
    codigo = codigo_para_caractere(consulta)
    saida: list[Simbolo] = []
    if codigo is not None:
        saida.append(Simbolo(codigo, nome_de(codigo)))
    palavras = consulta.upper().split()
    for c, nome in _indice():
        if all(p in nome for p in palavras):
            saida.append(Simbolo(c, nome.lower()))
            if len(saida) >= limite:
                break
    return saida


def codigo_para_caractere(codigo: str) -> str | None:
    """`"2A72"`, `"U+2A72"` ou `"0x2a72"` → `⩲`; `None` quando não é um código válido."""
    m = _RE_HEX.fullmatch(codigo.strip())
    if not m:
        return None
    valor = int(m.group(1), 16)
    if valor < 0x20 or valor > 0x10FFFF or 0xD800 <= valor <= 0xDFFF:
        return None
    return chr(valor)


def caractere_para_codigo(caractere: str) -> str:
    return f"{ord(caractere):04X}"


def alternar(antes_do_cursor: str) -> tuple[int, str] | None:
    """
    O `Ctrl+Shift+X`: dado o texto que precede o cursor, `(quantos caracteres apagar, o
    que pôr no lugar)`. Um hexadecimal no fim (`2A72`, `U+A0`) vira o caractere; senão o
    último caractere vira o seu código de quatro dígitos. `None` com o texto vazio.
    """
    if not antes_do_cursor:
        return None
    # Sem o prefixo `U+`, só de quatro a seis dígitos, começando em limite de palavra: o
    # Word converte `e4` em `ä` e `face` em um kanji, e num livro de xadrez `e4` é um lance.
    m = re.search(r"(?:U\+|u\+)([0-9A-Fa-f]{2,6})$|(?<![0-9A-Za-z])([0-9A-Fa-f]{4,6})$", antes_do_cursor)
    if m:
        digitos = m.group(1) or m.group(2)
        caractere = codigo_para_caractere(digitos)
        if caractere is not None:
            return len(m.group(0)), caractere
    ultimo = antes_do_cursor[-1]
    return 1, caractere_para_codigo(ultimo)


__all__ = ["CATEGORIAS", "NOMES_DOS_INVISIVEIS", "Simbolo", "nome_de", "simbolos_da_categoria", "procurar",
           "codigo_para_caractere", "caractere_para_codigo", "alternar"]
