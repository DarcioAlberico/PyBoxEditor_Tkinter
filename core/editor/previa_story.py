"""
O desenho da prévia (ED-14; docs/ANALISE_JANELA_EDITOR.md §4.1): o XHTML da aba, com a CSS
do capítulo, as fontes e as imagens do livro, posto num `fitz.Story` — o mesmo motor do
PDF paginado da ED-12 — e devolvido como páginas de largura fixa, empilhadas sem folga
pela tela (rolagem contínua, como a do Sigil).

## A linha da fonte

Antes de desenhar, uma **cópia** do texto ganha `id="__l<linha>"` na tag de abertura de
cada elemento de bloco que ainda não tem `id`; o que já tem `id` fica como está e entra no
mapa pelo próprio `id`. `Story.element_positions` devolve o retângulo de cada um, por
página, e isso dá o mapa `linha → (página, retângulo)` que a prévia usa nos dois sentidos:
o cursor do código rola até o bloco, e o clique devolve a linha. O texto salvo não muda.

## Os recursos

`src` do capítulo e `url()` das folhas são reescritos para o caminho relativo ao OPF, que é
o nome no `fitz.Archive`; os bytes vêm de `recursos(href)` e ficam em cache no `Montador`
(uma prévia aberta redesenha a cada tecla, e as 600 imagens de um livro não são relidas).
Com o `livro`, as fontes de diagrama e de símbolos e os PNG de diagrama que o livro ainda
não tem entram como no PDF (`pdf_io._Montador`), para a prévia e o PDF desenharem igual.

Sem Tk: devolve `Desenho` (o PDF em memória, o tamanho das páginas e o mapa). A tela é de
`ui/editor/previa.py`.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

#: Elementos que marcam linha: os de bloco do dialeto e os de fora que o livro importado traz.
ELEMENTOS_DE_BLOCO = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "figure", "div", "li", "blockquote",
                      "table", "tr", "pre", "hr", "ul", "ol", "dl", "dt", "dd", "section", "aside",
                      "header", "footer", "figcaption", "img", "caption")
#: Margem da página da prévia, em pt, e a altura de cada fatia da rolagem contínua.
MARGEM_PT = 12.0
ALTURA_DA_FATIA_PT = 720.0
PREFIXO = "__l"

_RE_ABERTURA = re.compile(r"<(" + "|".join(ELEMENTOS_DE_BLOCO) + r")(?=[\s/>])([^>]*)>", re.I)
_RE_ID = re.compile(r"""\sid\s*=\s*(["'])(.*?)\1""", re.S)
_RE_SRC = re.compile(r"""(\s(?:src|xlink:href)\s*=\s*)(["'])([^"']*)\2""")
_RE_URL = re.compile(r"url\((['\"]?)([^)'\"]+)\1\)")
_RE_LINK = re.compile(r"<link\b[^>]*>", re.I)


@dataclass
class Desenho:
    """O capítulo desenhado: o PDF em memória, a largura das fatias e as posições."""

    pdf: bytes
    largura_pt: float
    altura_pt: float
    paginas: int
    #: `(linha, página, (x0, y0, x1, y1))` na ordem do documento — a linha é a da fonte.
    posicoes: list[tuple[int, int, tuple[float, float, float, float]]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def linha_em(self, pagina: int, x: float, y: float) -> int | None:
        """A linha do bloco mais interno sob `(x, y)` da página; senão a do último bloco acima."""
        dentro = [(r, linha) for linha, p, r in self.posicoes if p == pagina and r[0] <= x <= r[2] and r[1] <= y <= r[3]]
        if dentro:
            # O mais interno é o de menor área (um <p> dentro de um <div>); no empate, o que
            # vem depois — o filho, que abre depois do pai.
            melhor = None
            for r, linha in dentro:
                area = (r[2] - r[0]) * (r[3] - r[1])
                if melhor is None or area <= melhor[0]:
                    melhor = (area, linha)
            return melhor[1]
        acima = [linha for linha, p, r in self.posicoes if p < pagina or (p == pagina and r[1] <= y)]
        return acima[-1] if acima else (self.posicoes[0][0] if self.posicoes else None)

    def posicao_da_linha(self, linha: int) -> tuple[int, int, tuple[float, float, float, float]] | None:
        """O bloco de linha maior ≤ `linha` (o primeiro, se nenhum): `(linha, página, retângulo)`."""
        if not self.posicoes:
            return None
        abaixo = [item for item in self.posicoes if item[0] <= linha]
        if not abaixo:
            return min(self.posicoes, key=lambda item: item[0])
        alvo = max(item[0] for item in abaixo)
        # A primeira fatia do bloco (um bloco que passa de uma fatia à outra aparece nas duas).
        return next(item for item in self.posicoes if item[0] == alvo)


def marcar_linhas(texto: str) -> tuple[str, dict[str, int]]:
    """
    A cópia do texto com `id="__l<linha>"` em cada elemento de bloco sem `id`, e o mapa
    `id → linha` (os `id` que já existiam também entram, com a linha da sua tag).
    """
    ids: dict[str, int] = {}
    partes: list[str] = []
    ultimo = 0
    linha = 1
    pos_linha = 0
    for achado in _RE_ABERTURA.finditer(texto):
        linha += texto.count("\n", pos_linha, achado.start())
        pos_linha = achado.start()
        atributos = achado.group(2)
        existente = _RE_ID.search(atributos)
        if existente:
            ids.setdefault(existente.group(2), linha)
            continue
        novo = f"{PREFIXO}{linha}"
        if novo in ids:
            novo = f"{PREFIXO}{linha}_{achado.start()}"
        ids[novo] = linha
        fim_do_nome = achado.start() + 1 + len(achado.group(1))
        partes.append(texto[ultimo:fim_do_nome])
        partes.append(f' id="{novo}"')
        ultimo = fim_do_nome
    partes.append(texto[ultimo:])
    return "".join(partes), ids


def resolver(pasta: str, valor: str) -> str:
    """Um caminho relativo ao capítulo/folha → relativo ao OPF (o nome no arquivo)."""
    if not valor or "://" in valor or valor.startswith(("#", "data:", "mailto:")):
        return valor
    return posixpath.normpath(posixpath.join(pasta, valor)) if pasta else posixpath.normpath(valor)


class Montador:
    """
    Guarda o que não muda entre dois redesenhos da mesma aba: os bytes dos recursos e as
    regras de fonte do livro. `recursos(href)` devolve os bytes de um recurso (relativo ao
    OPF) ou `None`.
    """

    def __init__(self, recursos: Callable[[str], bytes | None] | None = None, livro: Any = None):
        self.recursos = recursos
        self.livro = livro
        self.dados: dict[str, bytes] = {}
        self._faltando: set[str] = set()
        self._regras_de_fonte: str | None = None
        self._pdf_io: Any = None
        self.avisos: list[str] = []

    # -- recursos ----------------------------------------------------------------------

    def _buscar(self, caminho: str) -> None:
        if not caminho or caminho in self.dados or caminho in self._faltando or "://" in caminho \
                or caminho.startswith(("#", "data:")):
            return
        dados = None
        if self.recursos is not None:
            try:
                dados = self.recursos(caminho)
            except Exception:      # noqa: BLE001 — um recurso ilegível não derruba a prévia
                dados = None
        if dados is None:
            self._faltando.add(caminho)
        else:
            self.dados[caminho] = dados

    def _montador_do_pdf(self) -> Any:
        """O `_Montador` do PDF, que sabe as fontes de diagrama e desenha os PNG que faltam."""
        if self.livro is None:
            return None
        if self._pdf_io is None:
            from core.editor import pdf_io
            from core.editor.conversao import OpcoesDeConversao, RelatorioDeConversao

            self._pdf_io = pdf_io._Montador(self.livro, OpcoesDeConversao(), RelatorioDeConversao(formato="pdf"))
            self._pdf_io.dados = self.dados      # um cache só
        return self._pdf_io

    def regras_de_fonte(self) -> str:
        if self._regras_de_fonte is None:
            montador = self._montador_do_pdf()
            regras = ""
            if montador is not None:
                try:
                    # As fontes do livro primeiro, para `_fonte_no_arquivo` achá-las pelo nome.
                    for caminho, recurso in self.livro.recursos.items():
                        if "font" in (recurso.tipo_mime or "") or caminho.lower().endswith((".ttf", ".otf", ".woff")):
                            self._buscar(caminho)
                    regras = montador._fontes()
                    self.avisos.extend(montador.relatorio.avisos if hasattr(montador.relatorio, "avisos") else ())
                except Exception as erro:      # noqa: BLE001
                    self.avisos.append(f"fontes do livro fora da prévia: {erro}")
            self._regras_de_fonte = regras
        return self._regras_de_fonte

    def diagramas(self, texto: str, arquivo: str) -> None:
        """Os PNG dos diagramas do capítulo que o livro ainda não tem, desenhados uma vez."""
        montador = self._montador_do_pdf()
        if montador is None or "data-fen" not in texto:
            return
        try:
            from core.editor import xhtml

            cap = xhtml.ler(texto, arquivo)
            montador._diagramas([cap])
        except Exception as erro:      # noqa: BLE001
            self.avisos.append(f"diagramas fora da prévia: {erro}")

    # -- CSS e HTML --------------------------------------------------------------------

    def css(self, folhas: Iterable[tuple[str, str]]) -> str:
        """As folhas `(href relativo ao OPF, texto)` com os `url()` resolvidos, mais as regras de fonte."""
        partes: list[str] = []
        for href, texto in folhas:
            pasta = posixpath.dirname(href)

            def trocar(m: re.Match, pasta: str = pasta) -> str:
                caminho = resolver(pasta, m.group(2))
                self._buscar(caminho)
                return f"url({caminho})"

            partes.append(_RE_URL.sub(trocar, texto))
        if self.livro is not None:
            try:
                from core.editor import fontes

                partes.append(fontes.regras_para_o_pre("\n".join(partes)))
            except Exception:      # noqa: BLE001
                pass
        partes.append(self.regras_de_fonte())
        partes.append("figure { margin: 0.6em auto; text-align: center; }\n"
                      "figure img, img { max-width: 100%; }\n"
                      "figcaption { font-size: 0.85em; text-align: center; }\n")
        return "\n".join(partes)

    def html(self, texto: str, arquivo: str) -> tuple[str, dict[str, int]]:
        """O texto com as linhas marcadas, os `src` resolvidos e os `<link>` fora (a CSS vai à parte)."""
        marcado, ids = marcar_linhas(texto)
        pasta = posixpath.dirname(arquivo)

        def trocar(m: re.Match) -> str:
            caminho = resolver(pasta, m.group(3))
            self._buscar(caminho)
            return f"{m.group(1)}{m.group(2)}{caminho}{m.group(2)}"

        marcado = _RE_SRC.sub(trocar, marcado)
        marcado = _RE_LINK.sub("", marcado)
        # O `Story` lê HTML: a declaração XML e o DOCTYPE ficam de fora.
        marcado = re.sub(r"^\s*<\?xml[^>]*\?>", "", marcado)
        marcado = re.sub(r"<!DOCTYPE[^>]*>", "", marcado, count=1, flags=re.I)
        marcado = marcado.replace("epub:type=", "data-epub-type=")
        return marcado, ids


def desenhar(texto: str, arquivo: str = "", folhas: Iterable[tuple[str, str]] = (),
             largura_pt: float = 420.0, montador: Montador | None = None, corpo_pt: float = 11.0) -> Desenho:
    """
    Desenha o XHTML `texto` do capítulo `arquivo` em fatias de `largura_pt` × `ALTURA_DA_FATIA_PT`.
    Levanta o erro do MuPDF quando o `Story` recusa o HTML; a prévia mantém o desenho anterior.
    """
    import fitz

    montador = montador or Montador()
    montador.diagramas(texto, arquivo)
    html, ids = montador.html(texto, arquivo)
    css = montador.css(folhas)
    arquivo_fitz = fitz.Archive()
    for nome, dados in montador.dados.items():
        arquivo_fitz.add(dados, nome)
    story = fitz.Story(html=html, user_css=css, em=float(corpo_pt), archive=arquivo_fitz)
    largura_pt = max(120.0, float(largura_pt))
    mediabox = fitz.Rect(0, 0, largura_pt, ALTURA_DA_FATIA_PT)
    rect = mediabox + (MARGEM_PT, MARGEM_PT * 0.5, -MARGEM_PT, -MARGEM_PT * 0.5)
    buffer = __import__("io").BytesIO()
    writer = fitz.DocumentWriter(buffer)
    vistos: list[tuple[int, int, tuple[float, float, float, float]]] = []

    def posicao(p: Any) -> None:
        pagina = int(getattr(p, "pagina", 0))
        if not p.id or not (p.open_close & 1):
            return
        linha = ids.get(p.id)
        if linha is None and p.id.startswith(PREFIXO):
            try:
                linha = int(p.id[len(PREFIXO):].split("_")[0])
            except ValueError:
                linha = None
        if linha is not None:
            vistos.append((linha, pagina, tuple(float(v) for v in p.rect)))

    n = 0
    while True:
        dev = writer.begin_page(mediabox)
        mais, _preenchido = story.place(rect)
        story.element_positions(posicao, {"pagina": n})
        story.draw(dev)
        writer.end_page()
        n += 1
        if not mais or n > 2000:
            break
    writer.close()
    return Desenho(pdf=buffer.getvalue(), largura_pt=largura_pt, altura_pt=ALTURA_DA_FATIA_PT, paginas=n,
                   posicoes=vistos, avisos=list(montador.avisos))


__all__ = ["Desenho", "Montador", "desenhar", "marcar_linhas", "resolver", "ELEMENTOS_DE_BLOCO",
           "ALTURA_DA_FATIA_PT", "MARGEM_PT"]
