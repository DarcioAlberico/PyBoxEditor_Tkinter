"""
O realce de sintaxe do modo código: tokenizador por regex com estados, **estado por
linha**, e os dois temas (ED-07; SPEC_EDITOR §9.2, §13.2).

## Por que estado por linha, e não um regex sobre o documento inteiro

Um `<!--` na linha 10 muda a cor de tudo até o `-->`, esteja ele na linha 11 ou na
200. Realçar o documento inteiro a cada tecla num arquivo de 200 KB custaria mais do
que a tecla; realçar só a linha alterada erraria o comentário. O meio-termo é o dos
editores de código de verdade: cada linha guarda o **estado em que começa** (fora
de tag, dentro de tag, dentro de aspas, dentro de comentário, dentro de `<style>`…),
e uma edição re-tokeniza da linha alterada para a frente **até o estado no começo de
uma linha voltar a ser o que já era** — abrir um comentário propaga até o fim;
fechá-lo de novo propaga até onde tinha propagado; trocar uma letra num parágrafo
para em uma linha. As tags do `tk.Text` só são aplicadas à faixa visível.

O estado é uma tupla pequena e hashável, comparada por `==`; é o que torna a
convergência barata. Nada aqui importa Tk: o tokenizador é puro, e o teste de
desempenho (`slow`) mede só ele.

## Os temas

Dois, claro e escuro, com contraste ≥ 4,5:1 entre cada cor de token e o fundo
(WCAG 2.2 AA, medido por `contraste`, que é a fórmula da recomendação); a linha
atual e o casamento de tags são fundos, e o texto sobre eles continua passando.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

# ----------------------------------------------------------------------
# Estados
# ----------------------------------------------------------------------

#: O estado é `(modo, extra)`. Nos modos de XML `extra` é o nome da tag aberta (só
#: importa para `<style>` e `<script>`); nos de CSS é a profundidade de blocos.
INICIAL_XHTML = ("texto", "")
INICIAL_CSS = ("css_fora", 0)

#: Tipos de token que o tema pinta (o que não está aqui fica na cor do texto).
TIPOS = ("tag", "atributo", "valor", "entidade", "comentario", "pi", "doctype", "cdata",
         "seletor", "propriedade", "arroba", "pontuacao", "script")

#: At-rules cujo bloco contém **regras** (e não declarações): `@media { p { … } }`.
_ARROBAS_COM_REGRAS = {"media", "supports", "document", "keyframes", "layer", "container"}

_RE_TEXTO = re.compile(r"[<&]")
_RE_ENTIDADE = re.compile(r"&(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]*);")
_RE_NOME_DE_TAG = re.compile(r"</?[A-Za-z_:][\w:.-]*")
_RE_ATRIBUTO = re.compile(r"[^\s=/>\"']+")
_RE_ESPACO = re.compile(r"\s+")
_RE_CSS_PROPRIEDADE = re.compile(r"[-\w]+")


class Tokenizador:
    """`tokenizar_linha(linha, estado) → (tokens, estado_seguinte)`; tokens são `(inicio, fim, tipo)`."""

    def __init__(self, linguagem: str = "xhtml"):
        if linguagem not in ("xhtml", "css"):
            raise ValueError(f"linguagem desconhecida: {linguagem!r}")
        self.linguagem = linguagem

    @property
    def inicial(self) -> tuple:
        return INICIAL_XHTML if self.linguagem == "xhtml" else INICIAL_CSS

    def tokenizar_linha(self, linha: str, estado: tuple) -> tuple[list[tuple[int, int, str]], tuple]:
        tokens: list[tuple[int, int, str]] = []
        i, n = 0, len(linha)
        modo, extra = estado
        while i < n:
            if modo == "texto":
                m = _RE_TEXTO.search(linha, i)
                if m is None:
                    break
                i = m.start()
                if linha[i] == "&":
                    e = _RE_ENTIDADE.match(linha, i)
                    if e:
                        tokens.append((i, e.end(), "entidade"))
                        i = e.end()
                    else:
                        i += 1
                    continue
                if linha.startswith("<!--", i):
                    modo, extra = "comentario", ""
                    inicio = i
                    i += 4
                    fim = linha.find("-->", i)
                    if fim < 0:
                        tokens.append((inicio, n, "comentario"))
                        i = n
                    else:
                        tokens.append((inicio, fim + 3, "comentario"))
                        i = fim + 3
                        modo = "texto"
                    continue
                if linha.startswith("<![CDATA[", i):
                    modo, extra = "cdata", ""
                    inicio = i
                    i += 9
                    fim = linha.find("]]>", i)
                    if fim < 0:
                        tokens.append((inicio, n, "cdata"))
                        i = n
                    else:
                        tokens.append((inicio, fim + 3, "cdata"))
                        i = fim + 3
                        modo = "texto"
                    continue
                if linha.startswith("<?", i):
                    modo, extra = "pi", ""
                    inicio = i
                    i += 2
                    fim = linha.find("?>", i)
                    if fim < 0:
                        tokens.append((inicio, n, "pi"))
                        i = n
                    else:
                        tokens.append((inicio, fim + 2, "pi"))
                        i = fim + 2
                        modo = "texto"
                    continue
                if linha.startswith("<!", i):
                    modo, extra = "doctype", ""
                    inicio = i
                    fim = linha.find(">", i)
                    if fim < 0:
                        tokens.append((inicio, n, "doctype"))
                        i = n
                    else:
                        tokens.append((inicio, fim + 1, "doctype"))
                        i = fim + 1
                        modo = "texto"
                    continue
                t = _RE_NOME_DE_TAG.match(linha, i)
                if t:
                    tokens.append((i, t.end(), "tag"))
                    nome = t.group(0).lstrip("</").lower()
                    modo, extra = "tag", ("/" if t.group(0).startswith("</") else "") + nome
                    i = t.end()
                else:
                    tokens.append((i, i + 1, "tag"))
                    i += 1
                continue
            if modo == "tag":
                c = linha[i]
                if c.isspace():
                    i = _RE_ESPACO.match(linha, i).end()
                    continue
                if linha.startswith("/>", i):
                    tokens.append((i, i + 2, "tag"))
                    i += 2
                    modo, extra = "texto", ""
                    continue
                if c == ">":
                    tokens.append((i, i + 1, "tag"))
                    i += 1
                    if extra == "style":
                        modo, extra = "css_fora", 0
                    elif extra == "script":
                        modo, extra = "script", ""
                    else:
                        modo, extra = "texto", ""
                    continue
                if c == "=":
                    tokens.append((i, i + 1, "pontuacao"))
                    i += 1
                    continue
                if c in "\"'":
                    inicio = i
                    fim = linha.find(c, i + 1)
                    if fim < 0:
                        tokens.append((inicio, n, "valor"))
                        i = n
                        modo = "aspas" if c == '"' else "apostrofo"
                    else:
                        tokens.append((inicio, fim + 1, "valor"))
                        i = fim + 1
                    continue
                a = _RE_ATRIBUTO.match(linha, i)
                if a:
                    tokens.append((i, a.end(), "atributo"))
                    i = a.end()
                else:
                    i += 1
                continue
            if modo in ("aspas", "apostrofo"):
                aspa = '"' if modo == "aspas" else "'"
                fim = linha.find(aspa, i)
                if fim < 0:
                    tokens.append((i, n, "valor"))
                    i = n
                else:
                    tokens.append((i, fim + 1, "valor"))
                    i = fim + 1
                    modo = "tag"
                continue
            if modo in ("comentario", "cdata", "pi", "doctype"):
                fecho = {"comentario": "-->", "cdata": "]]>", "pi": "?>", "doctype": ">"}[modo]
                fim = linha.find(fecho, i)
                if fim < 0:
                    tokens.append((i, n, modo))
                    i = n
                else:
                    tokens.append((i, fim + len(fecho), modo))
                    i = fim + len(fecho)
                    modo, extra = "texto", ""
                continue
            if modo == "script":
                fim = linha.lower().find("</script", i)
                if fim < 0:
                    tokens.append((i, n, "script"))
                    i = n
                else:
                    if fim > i:
                        tokens.append((i, fim, "script"))
                    i = fim
                    modo, extra = "texto", ""
                continue
            # CSS (solto ou dentro de <style>)
            i, modo, extra = self._css(linha, i, modo, extra, tokens)
        return tokens, (modo, extra)

    def _css(self, linha: str, i: int, modo: str, prof: int, tokens: list) -> tuple[int, str, int]:
        n = len(linha)
        no_xhtml = self.linguagem == "xhtml"
        while i < n:
            if modo in ("css_comentario_fora", "css_comentario_dentro"):
                fim = linha.find("*/", i)
                if fim < 0:
                    tokens.append((i, n, "comentario"))
                    return n, modo, prof
                tokens.append((i, fim + 2, "comentario"))
                i = fim + 2
                modo = "css_fora" if modo == "css_comentario_fora" else "css_dentro"
                continue
            if no_xhtml and linha.lower().startswith("</style", i):
                return i, "texto", ""
            c = linha[i]
            if c.isspace():
                i = _RE_ESPACO.match(linha, i).end()
                continue
            if linha.startswith("/*", i):
                fim = linha.find("*/", i + 2)
                if fim < 0:
                    tokens.append((i, n, "comentario"))
                    return n, "css_comentario_fora" if modo == "css_fora" else "css_comentario_dentro", prof
                tokens.append((i, fim + 2, "comentario"))
                i = fim + 2
                continue
            if modo == "css_fora":
                if c == "{":
                    tokens.append((i, i + 1, "pontuacao"))
                    cabeca = _cabeca_do_bloco(linha, i)
                    if cabeca.startswith("@") and cabeca[1:].split(None, 1)[0].lower() in _ARROBAS_COM_REGRAS:
                        modo = "css_fora"
                    else:
                        modo = "css_dentro"
                    prof += 1
                    i += 1
                    continue
                if c == "}":
                    tokens.append((i, i + 1, "pontuacao"))
                    prof = max(0, prof - 1)
                    i += 1
                    continue
                if c == ";":
                    tokens.append((i, i + 1, "pontuacao"))
                    i += 1
                    continue
                if c == "@":
                    fim = _fim_do_seletor(linha, i)
                    tokens.append((i, fim, "arroba"))
                    i = fim
                    continue
                fim = _fim_do_seletor(linha, i)
                if fim > i:
                    tokens.append((i, fim, "seletor"))
                    i = fim
                else:
                    i += 1
                continue
            # css_dentro: declarações
            if c == "}":
                tokens.append((i, i + 1, "pontuacao"))
                prof = max(0, prof - 1)
                modo = "css_fora"
                i += 1
                continue
            if c == "{":
                tokens.append((i, i + 1, "pontuacao"))
                prof += 1
                i += 1
                continue
            if c in ";:":
                tokens.append((i, i + 1, "pontuacao"))
                i += 1
                if c == ":":
                    fim = _fim_do_valor(linha, i)
                    if fim > i:
                        tokens.append((i, fim, "valor"))
                    i = fim
                continue
            p = _RE_CSS_PROPRIEDADE.match(linha, i)
            if p:
                tokens.append((i, p.end(), "propriedade"))
                i = p.end()
            else:
                i += 1
        return i, modo, prof


def _cabeca_do_bloco(linha: str, i: int) -> str:
    """O texto antes do `{` na posição `i` (até o `;`, `}` ou `{` anterior), sem espaços."""
    j = i - 1
    while j >= 0 and linha[j] not in "{};" and not linha.startswith("*/", j - 1):
        j -= 1
    return linha[j + 1:i].strip()


def _fim_do_seletor(linha: str, i: int) -> int:
    n = len(linha)
    j = i
    while j < n and linha[j] not in "{};" and not linha.startswith("/*", j):
        j += 1
    while j > i and linha[j - 1].isspace():
        j -= 1
    return j


def _fim_do_valor(linha: str, i: int) -> int:
    """O valor de uma declaração: até `;` ou `}`, respeitando aspas e parênteses."""
    n = len(linha)
    j = i
    aspa = ""
    parenteses = 0
    while j < n:
        c = linha[j]
        if aspa:
            if c == aspa:
                aspa = ""
        elif c in "\"'":
            aspa = c
        elif c == "(":
            parenteses += 1
        elif c == ")":
            parenteses = max(0, parenteses - 1)
        elif c in ";}" and parenteses == 0:
            break
        elif linha.startswith("/*", j):
            break
        j += 1
    while j > i and linha[j - 1].isspace():
        j -= 1
    return j


# ----------------------------------------------------------------------
# O motor incremental
# ----------------------------------------------------------------------

class Realce:
    """
    Guarda o estado em que cada linha começa e re-tokeniza o mínimo. `linhas` é sempre
    a lista de linhas **atual** do documento (quem chama a mantém).
    """

    def __init__(self, linguagem: str = "xhtml"):
        self.tokenizador = Tokenizador(linguagem)
        #: `estados[i]` é o estado no começo da linha `i`; tem `len(linhas) + 1` entradas.
        self.estados: list[tuple] = [self.tokenizador.inicial]

    def carregar(self, linhas: Sequence[str]) -> None:
        estado = self.tokenizador.inicial
        estados = [estado]
        for linha in linhas:
            _tokens, estado = self.tokenizador.tokenizar_linha(linha, estado)
            estados.append(estado)
        self.estados = estados

    def editar(self, de: int, removidas: int, inseridas: int) -> None:
        """
        Ajusta a lista de estados a uma edição que trocou `removidas` linhas a partir
        de `de` por `inseridas` linhas — antes de `reprocessar`.
        """
        de = max(0, min(de, len(self.estados) - 1))
        if removidas > inseridas:
            del self.estados[de + 1 + inseridas: de + 1 + removidas]
        elif inseridas > removidas:
            enchimento = [self.estados[min(de + 1, len(self.estados) - 1)]] * (inseridas - removidas)
            self.estados[de + 1 + removidas: de + 1 + removidas] = enchimento

    def reprocessar(self, linhas: Sequence[str], de: int) -> tuple[int, int]:
        """
        Re-tokeniza de `de` até o estado no começo de uma linha convergir (ou até o fim).
        Devolve `(de, ate)`: as linhas `[de, ate)` são as que precisam de tags novas.
        """
        n = len(linhas)
        if len(self.estados) != n + 1:
            self.carregar(linhas)
            return 0, n
        de = max(0, min(de, n))
        estado = self.estados[de]
        i = de
        while i < n:
            _tokens, estado = self.tokenizador.tokenizar_linha(linhas[i], estado)
            i += 1
            if self.estados[i] == estado and i > de + 1:
                # A linha seguinte começa como começava: daqui para a frente nada muda.
                return de, i
            self.estados[i] = estado
        return de, n

    def tokens(self, linhas: Sequence[str], i: int) -> list[tuple[int, int, str]]:
        """Os tokens da linha `i` (0-based), com o estado guardado."""
        if i < 0 or i >= len(linhas) or i >= len(self.estados):
            return []
        tokens, _ = self.tokenizador.tokenizar_linha(linhas[i], self.estados[i])
        return tokens

    def faixa(self, linhas: Sequence[str], de: int, ate: int) -> Iterable[tuple[int, list[tuple[int, int, str]]]]:
        """`(i, tokens)` para as linhas `[de, ate)` — a faixa visível."""
        for i in range(max(0, de), min(ate, len(linhas))):
            yield i, self.tokens(linhas, i)

    def estado_no_inicio(self, i: int) -> tuple:
        return self.estados[min(max(i, 0), len(self.estados) - 1)]


# ----------------------------------------------------------------------
# Temas
# ----------------------------------------------------------------------

TEMAS: dict[str, dict[str, str]] = {
    "claro": {
        "fundo": "#ffffff", "texto": "#1f1f1f", "cursor": "#000000",
        "tag": "#0d47a1", "atributo": "#6a1b9a", "valor": "#1b5e20", "entidade": "#8d2900",
        "comentario": "#5f6368", "pi": "#5f6368", "doctype": "#5f6368", "cdata": "#5f6368",
        "seletor": "#0d47a1", "propriedade": "#6a1b9a", "arroba": "#8d2900", "pontuacao": "#1f1f1f",
        "script": "#3e2723",
        "linha_atual": "#f3f6fb", "casamento": "#d0e2ff", "selecao": "#b8d4ff", "selecao_texto": "#000000",
        "erro": "#ffd6d6", "calha_fundo": "#f0f0f0", "calha_texto": "#5f6368", "calha_atual": "#1f1f1f",
    },
    "escuro": {
        "fundo": "#1e1e1e", "texto": "#e6e6e6", "cursor": "#ffffff",
        "tag": "#7fb4ff", "atributo": "#d7a8ff", "valor": "#a6d38b", "entidade": "#ffb38a",
        "comentario": "#9aa0a6", "pi": "#9aa0a6", "doctype": "#9aa0a6", "cdata": "#9aa0a6",
        "seletor": "#7fb4ff", "propriedade": "#d7a8ff", "arroba": "#ffb38a", "pontuacao": "#e6e6e6",
        "script": "#e0c9a6",
        "linha_atual": "#2a2d2e", "casamento": "#12304d", "selecao": "#3a5f8a", "selecao_texto": "#ffffff",
        "erro": "#5a2626", "calha_fundo": "#252526", "calha_texto": "#9aa0a6", "calha_atual": "#e6e6e6",
    },
}


def _luminancia(cor: str) -> float:
    cor = cor.lstrip("#")
    r, g, b = (int(cor[i:i + 2], 16) / 255.0 for i in (0, 2, 4))

    def canal(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def contraste(a: str, b: str) -> float:
    """A razão de contraste WCAG entre duas cores `#rrggbb` (≥ 4,5:1 é o AA para texto)."""
    la, lb = _luminancia(a), _luminancia(b)
    claro, escuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (escuro + 0.05)


def tema(nome: str) -> dict[str, str]:
    if nome not in TEMAS:
        raise ValueError(f"tema desconhecido: {nome!r} (há: {', '.join(TEMAS)})")
    return dict(TEMAS[nome])


def tipos_pintados() -> tuple[str, ...]:
    return TIPOS
