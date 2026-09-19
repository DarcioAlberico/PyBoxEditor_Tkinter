"""
O dialeto XHTML+CSS que o editor entende (SPEC_EDITOR §6) — como dados.

Aqui moram as tabelas: que elemento e que classe cada bloco e cada atributo de
trecho viram no XHTML, quais atributos o leitor conhece e preserva (o resto
transforma o elemento numa ilha bruta, DEC-02), os sinônimos aceitos ao ler, a
ordem canônica de aninhamento dos elementos inline, os estilos nomeados com a
regra CSS e o estilo do DOCX de cada um, e a folha padrão do livro novo.

**Por que tabelas, e não `if` espalhados.** `xhtml.ler` e `xhtml.escrever` têm de
concordar exatamente — é o contrato de ida e volta da §6.5 —, e dois conjuntos de
`if` divergem com o tempo. Um mapa só, lido nos dois sentidos, não diverge.

Nada aqui importa Tkinter, PyMuPDF ou numpy (DEC-07): a CSS do diagrama vem de
`core/estilo_do_livro.py`, que é só texto.
"""

from __future__ import annotations

import hashlib
import posixpath
from typing import Any, Mapping

from core.estilo_do_livro import (CSS, CSS_DO_DIAGRAMA, MOLDURA_NA_CSS, RAIO_NA_CSS,
                                  classe_da_fonte)
from core.editor import modelo
from core.editor.modelo import Diagrama, Origem

NS_XHTML = "http://www.w3.org/1999/xhtml"
NS_EPUB = "http://www.idpf.org/2007/ops"
NS_XML = "http://www.w3.org/XML/1998/namespace"

# ----------------------------------------------------------------------
# Atributos e sinônimos
# ----------------------------------------------------------------------

#: O que o leitor conhece em qualquer elemento do dialeto e preserva em `extras`
#: (DEC-02). `id` e `class` têm tratamento próprio; os outros passam intactos.
ATRIBUTOS_CONHECIDOS = frozenset({
    "id", "class", "lang", "xml:lang", "title", "dir", "epub:type", "role", "aria-label",
})

#: Os `data-*` da origem editorial (DEC-10) e da suspeita, em qualquer bloco. O prefixo
#: `origem-` é o que os distingue da `data-pagina` da marca de página impressa.
ATRIBUTOS_DE_ORIGEM = ("data-origem-pagina", "data-origem-bloco", "data-origem-caixa",
                       "data-origem-fundidas", "data-suspeito")

#: Os `data-*` do diagrama (§6.1), na ordem em que são escritos.
ATRIBUTOS_DE_DIAGRAMA = (
    "data-fen", "data-lado", "data-orientacao", "data-coordenadas", "data-indicador",
    "data-marcas", "data-setas", "data-fonte", "data-moldura", "data-cantos", "data-corpo",
    "data-modo", "data-numero", "data-recorte", "data-estado", "data-aviso",
)

#: Elementos inline lidos como sinônimo e escritos na forma canônica.
SINONIMOS_INLINE = {"b": "strong", "i": "em", "strike": "s", "del": "s", "ins": "u"}

#: De fora para dentro: é a ordem em que `escrever` aninha e que `canonico` impõe.
ORDEM_DE_ANINHAMENTO = ("a", "span", "strong", "em", "u", "s", "sup", "sub", "code")

#: As classes do `<span>` de um trecho, na ordem canônica.
ORDEM_DE_CLASSES = ("sim", "lance", "nag", "fig", "com", "jogador", "abertura", "versalete")

#: `papel` do trecho ↔ classe do `<span>`.
CLASSE_DO_PAPEL = {"lance": "lance", "nag": "nag", "figurina": "fig", "comentario": "com",
                   "jogador": "jogador", "abertura": "abertura"}
PAPEL_DA_CLASSE = {v: k for k, v in CLASSE_DO_PAPEL.items()}

#: As propriedades de `style` que o dialeto escreve num `<span>`, nesta ordem.
PROPRIEDADES_DE_TRECHO = ("font-family", "font-size", "color", "background-color")

#: As propriedades de `style` de um parágrafo com formatação direta, nesta ordem.
PROPRIEDADES_DE_PARAGRAFO = (
    "text-align", "text-indent", "margin-left", "margin-right", "margin-top",
    "margin-bottom", "line-height", "page-break-after", "page-break-inside",
)

#: `text-align` ↔ `Paragrafo.alinhamento`.
ALINHAMENTO_CSS = {"esquerda": "left", "centro": "center", "direita": "right",
                   "justificado": "justify"}
ALINHAMENTO_DO_CSS = {v: k for k, v in ALINHAMENTO_CSS.items()}

#: `list-style-type` ↔ `Lista.marcador`.
MARCADOR_CSS = {"disco": "disc", "circulo": "circle", "quadrado": "square",
                "decimal": "decimal", "alfa": "lower-alpha", "romano": "lower-roman"}
MARCADOR_DO_CSS = {v: k for k, v in MARCADOR_CSS.items()}
MARCADOR_DO_CSS.update({"lower-latin": "alfa", "upper-alpha": "alfa", "upper-roman": "romano"})

#: Classe da `<figure>` ↔ `Figura.alinhamento`.
CLASSES_DE_FIGURA = {"esq": "esq", "centro": "centro", "dir": "dir"}

# ----------------------------------------------------------------------
# Estilos nomeados (§6.3)
# ----------------------------------------------------------------------

#: nome → (elemento, classe, estilo no DOCX). `titulo1`…`titulo6` são o `Titulo`;
#: `citacao` é o `<p>` dentro de `<blockquote>`; `nota` é o `<p>` da nota.
ESTILOS_DE_PARAGRAFO: dict[str, tuple[str, str, str]] = {
    "corpo": ("p", "", "Normal"),
    "primeira": ("p", "primeira", "Primeira"),
    "titulo1": ("h1", "", "Heading 1"),
    "titulo2": ("h2", "", "Heading 2"),
    "titulo3": ("h3", "", "Heading 3"),
    "titulo4": ("h4", "", "Heading 4"),
    "titulo5": ("h5", "", "Heading 5"),
    "titulo6": ("h6", "", "Heading 6"),
    "notacao": ("p", "notacao", "Notacao"),
    "comentario": ("p", "comentario", "Comentario"),
    "legenda": ("p", "legenda", "Caption"),
    "citacao": ("p", "", "Quote"),
    "nota": ("p", "", "footnote text"),
    "destaque": ("p", "destaque", "Destaque"),
    "epigrafe": ("p", "epigrafe", "Epigrafe"),
    "assinatura": ("p", "assinatura", "Assinatura"),
    "cabecalho-diagrama": ("p", "cabecalho-diagrama", "Cabecalho de diagrama"),
}

#: classe do `<p>` → estilo (o que o leitor reconhece).
ESTILO_DA_CLASSE = {classe: nome for nome, (el, classe, _docx) in ESTILOS_DE_PARAGRAFO.items()
                    if el == "p" and classe}

#: Estilos de caractere: nome → (classe do span ou atributo, estilo no DOCX).
ESTILOS_DE_CARACTERE = {
    "Lance": ("lance", "Lance"), "NAG": ("nag", "NAG"), "Figurina": ("fig", "Figurina"),
    "Simbolo": ("sim", "Simbolo"), "Versalete": ("versalete", "Versalete"),
    "Jogador": ("jogador", "Jogador"), "Abertura": ("abertura", "Abertura"),
}

#: As regras CSS dos estilos, na folha padrão do livro novo.
CSS_DOS_ESTILOS = """\
p.notacao { text-indent: 0; }
p.comentario { font-style: italic; }
p.legenda, figcaption, caption { font-size: 0.9em; text-align: center; text-indent: 0; margin: 0.4em 0 1em; }
p.destaque { border: 1px solid #999; background-color: #f4f4f4; padding: 0.6em 0.8em; text-indent: 0; }
p.epigrafe { font-style: italic; text-align: right; text-indent: 0; }
p.assinatura { text-align: right; text-indent: 0; }
p.cabecalho-diagrama { font-weight: bold; text-align: center; text-indent: 0; }
blockquote { margin: 1em 2em; }
blockquote p { text-indent: 0; }
.versalete { font-variant: small-caps; }
span.lance { white-space: nowrap; }
hr.quebra { border: 0; page-break-after: always; }
figure.diagrama { margin: 1.2em 0; text-align: center; page-break-inside: avoid; }
figure.esq { text-align: left; }
figure.dir { text-align: right; }
aside[role="doc-footnote"], section[role="doc-endnotes"] { font-size: 0.9em; margin-top: 2em;
  border-top: 1px solid #ccc; }
a[role="doc-noteref"] { text-decoration: none; }
"""


def css_padrao(corpo_pt: float = modelo.CORPO_PADRAO_PT, moldura: str = modelo.MOLDURA_PADRAO,
               cantos: str = modelo.CANTO_PADRAO) -> str:
    """
    A folha do livro novo: a CSS de sempre, o molde do diagrama **preenchido** e as
    regras dos estilos. Só `CSS_DO_DIAGRAMA` é molde (`%(corpo)s`, `%(moldura)s`);
    a `CSS` base tem `margin: 0 6%` e não pode passar por `%`.
    """
    if moldura not in MOLDURA_NA_CSS:
        raise ValueError(f"moldura inválida: {moldura!r}")
    regra = MOLDURA_NA_CSS[moldura] + (RAIO_NA_CSS[moldura] if cantos == "arredondado" else "")
    diagrama = CSS_DO_DIAGRAMA % {"corpo": f"{float(corpo_pt):g}", "moldura": regra}
    return CSS + diagrama + CSS_DOS_ESTILOS


# ----------------------------------------------------------------------
# Diagrama ↔ atributos
# ----------------------------------------------------------------------

def atributos_de_diagrama(d: Diagrama) -> dict[str, str]:
    """Os `data-*` da `<figure class="diagrama">`, na ordem da §6.1; só os não vazios."""
    valores = {
        "data-fen": d.fen,
        "data-lado": d.lado,
        "data-orientacao": d.orientacao,
        "data-coordenadas": "1" if d.coordenadas else "",
        "data-indicador": d.lado_indicador,
        "data-marcas": " ".join(d.marcas),
        "data-setas": " ".join(a + b for a, b in d.setas),
        "data-fonte": d.fonte,
        "data-moldura": d.moldura,
        "data-cantos": d.cantos,
        "data-corpo": f"{d.corpo_pt:g}",
        "data-modo": d.modo,
        "data-numero": "" if d.numero is None else str(d.numero),
        "data-recorte": d.recorte,
        "data-estado": d.estado if d.estado != "ok" else "",
        "data-aviso": d.aviso,
    }
    return {chave: valores[chave] for chave in ATRIBUTOS_DE_DIAGRAMA if valores[chave]}


def diagrama_de_atributos(attrs: Mapping[str, str], **resto: Any) -> Diagrama:
    """O `Diagrama` de uma `<figure>` com `data-fen`; `resto` são os campos de `Bloco`."""
    setas_cru = attrs.get("data-setas", "").split()
    setas = [(s[:2], s[2:4]) for s in setas_cru if len(s) == 4]
    numero = attrs.get("data-numero", "")
    return Diagrama(
        fen=attrs["data-fen"],
        lado=attrs.get("data-lado", ""),
        orientacao=attrs.get("data-orientacao", "branca") or "branca",
        coordenadas=attrs.get("data-coordenadas", "") in ("1", "true", "sim"),
        lado_indicador=attrs.get("data-indicador", ""),
        marcas=attrs.get("data-marcas", "").split(),
        setas=setas,
        fonte=attrs.get("data-fonte", modelo.FONTE_PADRAO) or modelo.FONTE_PADRAO,
        moldura=attrs.get("data-moldura", modelo.MOLDURA_PADRAO) or modelo.MOLDURA_PADRAO,
        cantos=attrs.get("data-cantos", modelo.CANTO_PADRAO) or modelo.CANTO_PADRAO,
        corpo_pt=float(attrs.get("data-corpo", modelo.CORPO_PADRAO_PT) or modelo.CORPO_PADRAO_PT),
        modo=attrs.get("data-modo", "png") or "png",
        numero=int(numero) if numero else None,
        recorte=attrs.get("data-recorte", ""),
        estado=attrs.get("data-estado", "ok") or "ok",
        aviso=attrs.get("data-aviso", ""),
        **resto,
    )


def chave_do_diagrama(d: Diagrama) -> str:
    """O hash dos parâmetros que mudam o desenho (DEC-06): nomeia o PNG e o cache."""
    partes = [d.posicao, d.lado, d.orientacao, "c" if d.coordenadas else "", d.lado_indicador,
              " ".join(sorted(d.marcas)), " ".join(a + b for a, b in d.setas),
              d.fonte, d.moldura, d.cantos, f"{d.corpo_pt:g}"]
    return hashlib.sha1("|".join(partes).encode("utf-8")).hexdigest()[:12]


def nome_do_png(d: Diagrama, pasta: str = "Images") -> str:
    """`Images/diag-<hash>.png` — ou na pasta de imagens que o livro já usa."""
    return posixpath.join(pasta, f"diag-{chave_do_diagrama(d)}.png")


# ----------------------------------------------------------------------
# Origem ↔ atributos (DEC-10)
# ----------------------------------------------------------------------

def atributos_de_origem(origem: Origem | None) -> dict[str, str]:
    if origem is None:
        return {}
    attrs = {"data-origem-pagina": origem.page_id, "data-origem-bloco": origem.bloco_id}
    if origem.caixa:
        attrs["data-origem-caixa"] = ",".join(str(v) for v in origem.caixa)
    if origem.fundidas:
        attrs["data-origem-fundidas"] = " ".join(f"{o.page_id}|{o.bloco_id}" for o in origem.fundidas)
    return attrs


def origem_de_atributos(attrs: Mapping[str, str]) -> Origem | None:
    if "data-origem-bloco" not in attrs or "data-origem-pagina" not in attrs:
        return None
    caixa = None
    if attrs.get("data-origem-caixa"):
        partes = attrs["data-origem-caixa"].split(",")
        if len(partes) == 4:
            caixa = tuple(int(p) for p in partes)
    page_id = attrs["data-origem-pagina"]
    fundidas = []
    for item in attrs.get("data-origem-fundidas", "").split():
        pagina_id, _, bloco_id = item.partition("|")
        if pagina_id and bloco_id:
            fundidas.append(Origem(page_id=pagina_id, bloco_id=bloco_id, pagina=_indice_da_pagina(pagina_id)))
    return Origem(page_id=page_id, bloco_id=attrs["data-origem-bloco"], pagina=_indice_da_pagina(page_id),
                  caixa=caixa, fundidas=fundidas)


def _indice_da_pagina(page_id: str) -> int:
    """`"<doc>-p0001"` (o adaptador legado) → 0; sem o sufixo, 0."""
    _, _, sufixo = page_id.rpartition("-p")
    if sufixo.isdigit():
        return max(0, int(sufixo) - 1)
    return 0


# ----------------------------------------------------------------------
# O texto alternativo do diagrama
# ----------------------------------------------------------------------

NOMES_DAS_PECAS = {
    "pt": {"K": "Rei", "Q": "Dama", "R": "Torre", "B": "Bispo", "N": "Cavalo", "P": "Peão",
           "brancas": "Brancas", "pretas": "Pretas"},
    "en": {"K": "King", "Q": "Queen", "R": "Rook", "B": "Bishop", "N": "Knight", "P": "Pawn",
           "brancas": "White", "pretas": "Black"},
}


def alt_de(d: Diagrama, idioma: str = "pt") -> str:
    """
    O texto alternativo gerado: a lista de peças por cor ("Brancas: Rei g1, …"), e não
    o FEN cru — o FEN fica em `data-fen` e `title` (DEC-06). É o que um leitor de tela
    diz de útil sobre um diagrama. Nasce aqui, e não no `xadrez.py` da ED-05, porque
    `xhtml.escrever` e `epub.escrever` já precisam dele.
    """
    nomes = NOMES_DAS_PECAS.get(idioma, NOMES_DAS_PECAS["pt"])
    filas = d.posicao.split("/")
    por_cor: dict[str, list[str]] = {"brancas": [], "pretas": []}
    for i, fila in enumerate(filas):
        coluna = 0
        for ch in fila:
            if ch.isdigit():
                coluna += int(ch)
                continue
            casa = "abcdefgh"[coluna] + str(8 - i)
            por_cor["brancas" if ch.isupper() else "pretas"].append(f"{nomes[ch.upper()]} {casa}")
            coluna += 1
    partes = [f"{nomes[cor]}: {', '.join(pecas)}" for cor, pecas in por_cor.items() if pecas]
    return "; ".join(partes) or "Tabuleiro vazio"


# ----------------------------------------------------------------------
# O tabuleiro em texto, como `exportar._diagrama_em_texto` o escreve
# ----------------------------------------------------------------------

def div_do_diagrama(linhas: list[str], fonte: str, *, coordenadas: bool, orientacao: str,
                    emolduradas: bool, alt: str, escapar) -> str:
    """
    O `<div class="diagrama …">` de hoje (F59/F95/F99), byte a byte igual ao de
    `core/exportar.py`, para o EPUB continuar abrindo sem ilha (R5).

    `escapar` é a função de escape de texto de quem chama — este módulo não
    conhece o `xml.sax.saxutils` de propósito, para as duas escritas usarem a mesma.
    """
    familia = classe_da_fonte(fonte)
    alt_esc = escapar(alt, {'"': "&quot;"})
    if emolduradas:
        miolo = "\n".join(f"<p>{escapar(linha)}</p>" for linha in linhas)
        return (f'<div class="diagrama {familia}" title="{alt_esc}" '
                f'aria-label="{alt_esc}" role="img">\n{miolo}\n</div>')
    colunas, filas = _rotulos(orientacao)
    saida = []
    for i, linha in enumerate(linhas):
        linha = escapar(linha)
        if coordenadas:
            linha = f'<span class="rot"><i>{filas[i]}</i></span>{linha}'
        saida.append(f"<p>{linha}</p>")
    if coordenadas:
        cols = "".join(f'<span class="col"><i>{c}</i></span>' for c in colunas)
        saida.append(f'<p class="colunas"><span class="rot"></span>{cols}</p>')
    # `caixa` sai sempre neste caminho, como em `exportar._diagrama_em_texto`: a
    # moldura "sem" é a regra CSS vazia de `MOLDURA_NA_CSS`, não a ausência da classe.
    return (f'<div class="diagrama caixa {familia}" title="{alt_esc}" aria-label="{alt_esc}" role="img">\n'
            + "\n".join(saida) + "\n</div>")


def _rotulos(orientacao: str) -> tuple[list[str], list[str]]:
    """Cópia de `render_diagrama.rotulos`, para não importar `fitz` por causa de oito letras."""
    colunas = list("abcdefgh")
    filas = [str(n) for n in range(8, 0, -1)]
    if orientacao == "preta":
        colunas.reverse()
        filas.reverse()
    return colunas, filas
