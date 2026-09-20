"""
Consertar o XHTML que não está bem-formado, e reformatar CSS (ED-07; SPEC_EDITOR §9
"Mend / Reformat HTML / Reformat CSS").

## O que "consertar" faz, e o que não faz

O `expat` recusa `<p>aberto`, um `<br>` sem barra, um `&` solto, um `</b>` sem `<b>`.
Consertar é o que o Sigil chama de *Mend*: reler o texto com um leitor de HTML
tolerante (`html.parser`, da biblioteca padrão — DEC-07, nada novo) e reescrevê-lo
como XML bem-formado: tag vazia fechada com `/>`, elemento aberto fechado onde o pai
fecha (ou no fim), fechamento órfão descartado, `&` e `<` soltos escapados, `--`
dentro de comentário separado, atributo repetido reduzido ao primeiro. Cada coisa
que muda vira um aviso com a linha, porque consertar em silêncio é o que a spec
proíbe (princípio 2).

O que ele **não** faz: canonizar. O resultado é o texto do usuário, bem-formado;
`reformatar` (`xhtml.canonico`) é outro comando, e o usuário escolhe.

**Caixa das letras.** O `html.parser` devolve nome de tag e de atributo em
minúsculas; um `viewBox` de SVG embutido viraria `viewbox`, que o SVG não entende.
Por isso o texto original da tag de abertura (`get_starttag_text`) é relido aqui
com a caixa preservada, e só a comparação com a pilha é feita em minúsculas.

## Reformatar CSS

Uma regra por bloco, uma declaração por linha, dois espaços de recuo, um bloco de
`@media` recuado por dentro — e **os comentários no lugar**, porque num livro a
folha de estilo carrega anotações do editor que não podem sumir. Idempotente:
reformatar o reformatado devolve o mesmo texto.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from core.editor import xhtml

NS_XHTML = "http://www.w3.org/1999/xhtml"
NS_EPUB = "http://www.idpf.org/2007/ops"

#: Elementos vazios do HTML: sem `/>` o XML não os aceita.
VAZIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
          "source", "track", "wbr"}

_RE_ATRIBUTO = re.compile(r"""([^\s=/>"']+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s"'=<>`]+))?""")
_RE_NOME_DA_TAG = re.compile(r"<\s*([^\s/>]+)")
_RE_ENTIDADE = re.compile(r"&(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]*);")


def _escapar_texto(texto: str) -> str:
    """`&` que não é entidade e `<` viram referências; `>` pode ficar."""
    partes = []
    i = 0
    for m in _RE_ENTIDADE.finditer(texto):
        partes.append(texto[i:m.start()].replace("&", "&amp;").replace("<", "&lt;"))
        partes.append(m.group(0))
        i = m.end()
    partes.append(texto[i:].replace("&", "&amp;").replace("<", "&lt;"))
    return "".join(partes)


def _escapar_valor(valor: str) -> str:
    return _escapar_texto(valor).replace('"', "&quot;")


class _Consertador(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.saida: list[str] = []
        self.pilha: list[tuple[str, str]] = []      # (minúsculo, como escrito)
        self.avisos: list[str] = []
        self.usa_epub = False

    def _linha(self) -> int:
        return self.getpos()[0]

    # -- tags ----------------------------------------------------------------

    def _atributos(self, cru: str, attrs: list) -> str:
        nomes_vistos: set[str] = set()
        partes: list[str] = []
        fonte = cru[cru.find(" "):] if " " in cru else ""
        if not fonte:
            fonte = " ".join(f'{n}="{v or ""}"' for n, v in attrs)
        for m in _RE_ATRIBUTO.finditer(fonte.rstrip("/>")):
            nome, valor = m.group(1), m.group(2)
            if nome.lower() in nomes_vistos:
                self.avisos.append(f"linha {self._linha()}: atributo repetido {nome} descartado")
                continue
            nomes_vistos.add(nome.lower())
            if nome.startswith("epub:") or nome.startswith("xmlns:epub"):
                self.usa_epub = True
            if valor is None:
                valor = nome
            elif valor[:1] in "\"'":
                valor = valor[1:-1]
            partes.append(f' {nome}="{_escapar_valor(valor)}"')
        return "".join(partes)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        cru = self.get_starttag_text() or f"<{tag}>"
        m = _RE_NOME_DA_TAG.match(cru)
        nome = m.group(1) if m else tag
        atributos = self._atributos(cru, attrs)
        if tag in VAZIOS:
            self.saida.append(f"<{nome}{atributos}/>")
            if not cru.rstrip().endswith("/>"):
                self.avisos.append(f"linha {self._linha()}: <{nome}> fechado com />")
            return
        self.saida.append(f"<{nome}{atributos}>")
        self.pilha.append((tag, nome))

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        cru = self.get_starttag_text() or f"<{tag}/>"
        m = _RE_NOME_DA_TAG.match(cru)
        nome = m.group(1) if m else tag
        self.saida.append(f"<{nome}{self._atributos(cru, attrs)}/>")

    def handle_endtag(self, tag: str) -> None:
        if tag in VAZIOS:
            return
        abertos = [t for t, _n in self.pilha]
        if tag not in abertos:
            self.avisos.append(f"linha {self._linha()}: </{tag}> sem abertura, descartado")
            return
        while self.pilha:
            minusculo, nome = self.pilha.pop()
            self.saida.append(f"</{nome}>")
            if minusculo == tag:
                break
            self.avisos.append(f"linha {self._linha()}: <{nome}> fechado antes de </{tag}>")

    # -- o resto ---------------------------------------------------------------

    def handle_data(self, dados: str) -> None:
        self.saida.append(_escapar_texto(dados))

    def handle_entityref(self, nome: str) -> None:
        self.saida.append(f"&{nome};")

    def handle_charref(self, nome: str) -> None:
        self.saida.append(f"&#{nome};")

    def handle_comment(self, dados: str) -> None:
        if "--" in dados:
            self.avisos.append(f"linha {self._linha()}: '--' dentro de comentário separado")
            dados = dados.replace("--", "- -")
        self.saida.append(f"<!--{dados}-->")

    def handle_decl(self, decl: str) -> None:
        self.saida.append(f"<!{decl}>")

    def handle_pi(self, dados: str) -> None:
        self.saida.append(f"<?{dados}>")

    def unknown_decl(self, dados: str) -> None:
        if dados.startswith("CDATA["):
            self.saida.append(f"<![{dados}]]>")
        else:
            self.saida.append(f"<!{dados}>")

    def fechar_tudo(self) -> None:
        while self.pilha:
            _minusculo, nome = self.pilha.pop()
            self.saida.append(f"</{nome}>")
            self.avisos.append(f"<{nome}> não estava fechado; fechado no fim")


def consertar(texto: str) -> tuple[str, list[str]]:
    """
    O texto como XHTML bem-formado, e a lista do que mudou (com a linha). Um texto que
    já está bem-formado volta **inalterado**, sem aviso — consertar não é reformatar.
    """
    texto = texto.lstrip("\ufeff")
    if xhtml.bem_formado(texto) is None:
        return texto, []
    parser = _Consertador()
    parser.feed(texto)
    parser.close()
    parser.fechar_tudo()
    saida = "".join(parser.saida)
    avisos = parser.avisos
    tem_html = re.search(r"<html\b", saida, re.IGNORECASE) is not None
    if not tem_html:
        avisos.append("sem <html>: o texto foi embrulhado em html/body")
        saida = (f'<html xmlns="{NS_XHTML}"' + (f' xmlns:epub="{NS_EPUB}"' if parser.usa_epub else "")
                 + f">\n<head><title></title></head>\n<body>\n{saida}\n</body>\n</html>\n")
    else:
        m = re.search(r"<html\b([^>]*)>", saida)
        atributos = m.group(1) if m else ""
        extras = ""
        if "xmlns=" not in atributos:
            extras += f' xmlns="{NS_XHTML}"'
            avisos.append("<html> sem xmlns: declarado")
        if parser.usa_epub and "xmlns:epub" not in atributos:
            extras += f' xmlns:epub="{NS_EPUB}"'
            avisos.append("prefixo epub: usado sem declaração: declarado")
        if extras and m:
            saida = saida[:m.start()] + f"<html{extras}{atributos}>" + saida[m.end():]
    erro = xhtml.bem_formado(saida)
    if erro is not None:
        avisos.append(f"ainda não está bem-formado: {erro}")
    return saida, avisos


# ----------------------------------------------------------------------
# CSS
# ----------------------------------------------------------------------

_RE_CSS_TOKEN = re.compile(r"/\*.*?\*/|\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|[{};]|[^{};\"'/]+|/", re.S)


def reformatar_css(texto: str, recuo: str = "  ") -> str:
    """
    A folha com uma regra por bloco, uma declaração por linha e os comentários no
    lugar em que estavam (antes da regra, ou na linha da declaração).
    """
    texto = texto.lstrip("\ufeff").replace("\r\n", "\n")
    saida: list[str] = []
    nivel = 0
    cabeca: list[str] = []          # o texto acumulado antes de `{` ou `;`

    def nivelar() -> str:
        return recuo * nivel

    def descarregar_cabeca(terminador: str) -> None:
        conteudo = " ".join(" ".join(c.split()) for c in cabeca if c.strip())
        cabeca.clear()
        if not conteudo:
            return
        if terminador == "{":
            saida.append(f"{nivelar()}{conteudo} {{")
        elif terminador == ";" or (nivel > 0 and ":" in conteudo):
            # A última declaração do bloco, sem `;`, ganha o seu: é o que todo formatador faz.
            if ":" in conteudo and nivel > 0:
                propriedade, _, valor = conteudo.partition(":")
                saida.append(f"{nivelar()}{propriedade.strip()}: {valor.strip()};")
            else:
                saida.append(f"{nivelar()}{conteudo};")
        else:
            saida.append(f"{nivelar()}{conteudo}")

    for m in _RE_CSS_TOKEN.finditer(texto):
        token = m.group(0)
        if token.startswith("/*"):
            if cabeca and any(c.strip() for c in cabeca):
                cabeca.append(token)            # comentário no meio de uma declaração: vai junto
            else:
                saida.append(f"{nivelar()}{token}")
            continue
        if token == "{":
            descarregar_cabeca("{")
            nivel += 1
            continue
        if token == ";":
            descarregar_cabeca(";")
            continue
        if token == "}":
            descarregar_cabeca("")
            nivel = max(0, nivel - 1)
            saida.append(f"{nivelar()}}}")
            if nivel == 0:
                saida.append("")
            continue
        cabeca.append(token)
    descarregar_cabeca("")
    linhas = [linha.rstrip() for linha in saida]
    resultado = "\n".join(linhas).strip("\n")
    resultado = re.sub(r"\n{3,}", "\n\n", resultado)
    return resultado + "\n" if resultado else ""
