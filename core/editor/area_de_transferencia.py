"""
A área de transferência do editor (ED-04; SPEC_EDITOR §8.11).

## Por que isto mora em `core/`

Copiar e colar têm regra — o que vai para o sistema, quando uma colagem é interna,
como um texto de fora vira parágrafos, como um XHTML colado é consertado e lido —
e a regra é testável sem Tk. O acesso ao sistema (`clipboard_get`, `clipboard_append`,
`ImageGrab`) é **injetado** pelo widget: `AreaDeTransferencia(ler_sistema,
gravar_sistema, ler_imagem)`.

## O contrato

- `copiar(fragmento)` guarda o modelo copiado no buffer do processo e põe no sistema
  **só o texto plano**. Um programa de fora recebe texto; o editor recebe o modelo.
- `colar()` é **interna** quando o texto do sistema é idêntico ao do último copiar
  (o fragmento volta, em cópia); senão é texto do sistema; senão, sem texto, é a
  imagem do sistema (bytes de PNG), quando há quem a leia. `forcar_texto` é o
  `Ctrl+Shift+V`: sempre o texto plano.
- `blocos_do_texto(texto)`: texto de fora → um parágrafo por linha não vazia.
- `blocos_do_xhtml(texto)`: "Colar como XHTML" — `consertar` + `ler_fragmento`, com os
  avisos do conserto.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from core.editor import modelo
from core.editor.modelo import Bloco, Nota, Paragrafo, Trecho


@dataclass
class Fragmento:
    """O que uma seleção do modo texto contém, como modelo."""

    blocos: list[Bloco] = field(default_factory=list)
    #: `True` quando é um pedaço de um parágrafo só — cola no cursor, sem abrir bloco.
    inline: bool = False
    #: O texto plano equivalente (o que vai para o sistema).
    texto: str = ""
    #: As notas referenciadas pelos blocos (nascem de novo, com id novo, ao colar).
    notas: list[Nota] = field(default_factory=list)

    @property
    def vazio(self) -> bool:
        return not self.blocos and not self.texto

    def copia(self) -> "Fragmento":
        return Fragmento(blocos=copy.deepcopy(self.blocos), inline=self.inline, texto=self.texto,
                         notas=copy.deepcopy(self.notas))

    @property
    def trechos(self) -> list[Trecho]:
        """Os trechos de um fragmento inline (o primeiro bloco, que é um parágrafo)."""
        if self.blocos and isinstance(self.blocos[0], Paragrafo):
            return list(self.blocos[0].trechos)
        return []


@dataclass
class Colagem:
    """O que `colar()` devolve: `tipo` é `"interno"`, `"html"`, `"texto"` ou `"imagem"`."""

    tipo: str
    fragmento: Fragmento | None = None
    texto: str = ""
    imagem: bytes | None = None
    html: str = ""             # o fragmento do `CF_HTML` do sistema (ED-13), quando há


# ----------------------------------------------------------------------
# CF_HTML: o HTML que o navegador e o Word põem na área de transferência (ED-13)
# ----------------------------------------------------------------------

_RE_DESLOCAMENTO = re.compile(rb"^(StartFragment|EndFragment|StartHTML|EndHTML):\s*(-?\d+)", re.M)


def fragmento_cf_html(dados: bytes | str) -> str:
    """
    O fragmento HTML de um payload `CF_HTML` ("HTML Format" do Windows): o cabeçalho diz
    `StartFragment`/`EndFragment` em **bytes** (o payload é UTF-8); sem eles, valem os
    comentários `<!--StartFragment-->`/`<!--EndFragment-->`; sem nada, o que vem depois do
    cabeçalho. Devolve "" quando não há HTML.
    """
    if isinstance(dados, str):
        dados = dados.encode("utf-8", errors="replace")
    dados = dados.rstrip(b"\x00")
    if not dados.strip():
        return ""
    limites = {m.group(1).decode("ascii"): int(m.group(2)) for m in _RE_DESLOCAMENTO.finditer(dados[:2000])}
    inicio, fim = limites.get("StartFragment", -1), limites.get("EndFragment", -1)
    if 0 <= inicio < fim <= len(dados):
        return dados[inicio:fim].decode("utf-8", errors="replace").strip()
    texto = dados.decode("utf-8", errors="replace")
    a, b = texto.find("<!--StartFragment-->"), texto.find("<!--EndFragment-->")
    if a >= 0 and b > a:
        return texto[a + len("<!--StartFragment-->"):b].strip()
    inicio, fim = limites.get("StartHTML", -1), limites.get("EndHTML", -1)
    if 0 <= inicio < fim <= len(dados):
        return dados[inicio:fim].decode("utf-8", errors="replace").strip()
    posicao = texto.find("<")
    return texto[posicao:].strip() if posicao >= 0 else ""


def html_do_windows() -> str | None:
    """O fragmento `CF_HTML` da área de transferência do Windows, por `ctypes`; `None` fora dele ou sem HTML."""
    import sys

    if not sys.platform.startswith("win"):
        return None
    import ctypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    formato = user32.RegisterClipboardFormatW("HTML Format")
    if not formato or not user32.OpenClipboard(None):
        return None
    try:
        if not user32.IsClipboardFormatAvailable(formato):
            return None
        alca = user32.GetClipboardData(formato)
        if not alca:
            return None
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalSize.restype = ctypes.c_size_t
        ponteiro = kernel32.GlobalLock(ctypes.c_void_p(alca))
        if not ponteiro:
            return None
        try:
            dados = ctypes.string_at(ponteiro, kernel32.GlobalSize(ctypes.c_void_p(alca)))
        finally:
            kernel32.GlobalUnlock(ctypes.c_void_p(alca))
    finally:
        user32.CloseClipboard()
    fragmento = fragmento_cf_html(dados)
    return fragmento or None


def texto_plano(blocos: Sequence[Bloco]) -> str:
    """O texto plano de blocos copiados: um bloco por linha (o que o sistema recebe)."""
    return "\n".join(modelo.texto_de(b) for b in blocos)


def blocos_do_texto(texto: str) -> list[Paragrafo]:
    """Texto de fora → parágrafos: uma linha não vazia é um parágrafo; `\\r\\n` é `\\n`."""
    linhas = [li.rstrip() for li in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return [Paragrafo(trechos=[Trecho(texto=li)]) for li in linhas if li.strip()]


_RE_CORPO = re.compile(r"<body[^>]*>(.*)</body>", re.S)
#: Um elemento de bloco no HTML colado: sem nenhum, o fragmento é inline e vira um parágrafo só.
_RE_BLOCO_HTML = re.compile(r"<(p|h[1-6]|div|ul|ol|li|table|figure|blockquote|pre|hr|section|article|img|br)\b",
                            re.I)


def blocos_do_xhtml(texto: str, arquivo: str = "") -> tuple[list[Bloco], list[str]]:
    """
    "Colar como XHTML": conserta o que dá (`consertar`) e lê o fragmento; devolve os
    blocos e os avisos. `consertar` embrulha um fragmento em `html/body`: o que se lê é
    o miolo do `body` (`ler_fragmento`, que aceita só inline); um documento inteiro
    colado é lido como capítulo (`ler`) e dá os blocos dele.
    """
    from core.editor import consertar, xhtml

    consertado, avisos = consertar.consertar(texto)
    corpo = _RE_CORPO.search(consertado)
    try:
        if corpo is not None and "<html" in texto[:400].lower():
            blocos = list(xhtml.ler(consertado, arquivo).blocos)
        elif corpo is not None:
            blocos = xhtml.ler_fragmento(corpo.group(1).strip(), arquivo)
        else:
            blocos = xhtml.ler_fragmento(consertado.strip(), arquivo)
    except ValueError as erro:
        raise ValueError(f"o XHTML colado não pôde ser lido: {erro}") from erro
    return blocos, [a for a in avisos if not a.startswith("sem <html>")]


class AreaDeTransferencia:
    def __init__(self, ler_sistema: Callable[[], str], gravar_sistema: Callable[[str], Any],
                 ler_imagem: Callable[[], bytes | None] | None = None,
                 ler_html: Callable[[], str | None] | None = None):
        self.ler_sistema = ler_sistema
        self.gravar_sistema = gravar_sistema
        self.ler_imagem = ler_imagem
        self.ler_html = ler_html
        self._ultimo: Fragmento | None = None

    @property
    def ultimo(self) -> Fragmento | None:
        return self._ultimo

    def copiar(self, fragmento: Fragmento) -> str:
        """Guarda o fragmento e põe no sistema só o texto plano; devolve o texto."""
        if fragmento.vazio:
            return ""
        texto = fragmento.texto if fragmento.texto else texto_plano(fragmento.blocos)
        self._ultimo = Fragmento(blocos=copy.deepcopy(fragmento.blocos), inline=fragmento.inline, texto=texto,
                                 notas=copy.deepcopy(fragmento.notas))
        self.gravar_sistema(texto)
        return texto

    def _texto_do_sistema(self) -> str:
        try:
            texto = self.ler_sistema()
        except Exception:      # noqa: BLE001 — sem texto no sistema (o Tk levanta TclError)
            return ""
        return "" if texto is None else str(texto)

    def _html_do_sistema(self) -> str:
        if self.ler_html is None:
            return ""
        try:
            return self.ler_html() or ""
        except Exception:      # noqa: BLE001 — a área de transferência é de terceiros
            return ""

    def colar(self, forcar_texto: bool = False) -> Colagem | None:
        """
        Interna quando o texto do sistema é o do último copiar; senão o HTML do sistema
        (`CF_HTML`, com o texto plano ao lado); senão texto; senão imagem; senão `None`.
        """
        texto = self._texto_do_sistema()
        if forcar_texto:
            return Colagem("texto", texto=texto.replace("\r\n", "\n")) if texto else None
        if texto and self._ultimo is not None and texto.replace("\r\n", "\n") == self._ultimo.texto:
            return Colagem("interno", fragmento=self._ultimo.copia(), texto=self._ultimo.texto)
        html = self._html_do_sistema()
        if html:
            return Colagem("html", texto=texto.replace("\r\n", "\n"), html=html)
        if texto:
            return Colagem("texto", texto=texto.replace("\r\n", "\n"))
        if self.ler_imagem is not None:
            try:
                imagem = self.ler_imagem()
            except Exception:      # noqa: BLE001 — a leitura de imagem é de terceiros (ImageGrab)
                imagem = None
            if imagem:
                return Colagem("imagem", imagem=bytes(imagem))
        return None


def blocos_do_html(html: str, livro: Any = None, arquivo: str = "") -> tuple[list[Bloco], list[str]]:
    """
    O HTML colado do sistema (`CF_HTML`) → blocos do dialeto: `html_io.ler_texto` conserta e
    lê (`<b>`/`<i>` normalizados, `<h2>` título, `<p><img>` figura); com `livro`, as imagens
    `data:` viram recursos dele. Devolve `(blocos, avisos)`.
    """
    from core.editor import html_io
    from core.editor.conversao import RelatorioDeConversao

    if not _RE_BLOCO_HTML.search(html):
        html = f"<p>{html}</p>"                       # só inline: um parágrafo, e não um bloco por trecho
    if "<html" not in html[:400].lower():
        html = f"<html><body>{html}</body></html>"
    cap, avisos = html_io.ler_texto(html, arquivo or "Text/colado.xhtml")
    blocos = list(cap.blocos)
    if livro is not None:
        relatorio = RelatorioDeConversao(formato="html")
        html_io.embutir_imagens_data(livro, blocos, relatorio)
        avisos = list(avisos) + list(relatorio.avisos)
    return blocos, avisos


__all__ = ["AreaDeTransferencia", "Fragmento", "Colagem", "texto_plano", "blocos_do_texto", "blocos_do_xhtml",
           "blocos_do_html", "fragmento_cf_html", "html_do_windows"]
