"""
As tags do `tk.Text` do modo texto: o que cada uma quer dizer, como se chamam, e a
**fonte derivada** que o Tk desenha (ED-03; SPEC_EDITOR DEC-03).

## Uma fonte por caractere

O Tk aceita uma única `-font` por caractere: quando duas tags com fonte se
sobrepõem, só a de maior prioridade vale — negrito **ou** itálico, nunca os dois. Por
isso o que é **do trecho** fica em tags-marcador **sem fonte** (`b`, `i`, `vers`,
`sobre`, `sub`, `fam:<nome>`, `corpo:<pt>`), e a fonte que se vê é uma tag
**derivada** — `fonte:<família>:<corpo>:<b><i><v|o|u>` — calculada do estilo do
parágrafo ⊕ CSS ⊕ marcadores, com um `tkfont.Font` por combinação em cache. O
`dump` descarta as derivadas: elas são tela, não modelo.

## Famílias de tags

- **Marcadores de caractere** (próprios do trecho, entram na fonte): `b`, `i`, `vers`,
  `sobre`, `sub`, `fam:…`, `corpo:…`.
- **Independentes** (o Tk desenha à parte): `u`, `s`, `cor:#…`, `fundo:#…`, `code`; e as
  que só carregam dado para o `dump`: `cls:…`, `lang:…`, `tit:…`, `link:…`, `ref:…`,
  `nota:…`, `papel:…`, `nag:…`, `chave:…`, `pagina:…`.
- **Quebras** (todas com `quebra`+`protegido`): `qs` (suave, `<br/>`), `qp` (parágrafo
  dentro de citação ou item), `qi:<nível>` (item de lista).
- **De parágrafo** (cobrem o bloco inteiro): `p:<estilo>`, `al:…`, `rec1:…`, `recE:…`,
  `recD:…`, `antes:…`, `depois:…`, `entre:…`, `manter`, `manterl`, `cit`, `li:<nível>`,
  e `dn:<id>|<tipo>` num parágrafo da faixa de notas (ED-04).
- **De tela** (nunca vão ao modelo): `protegido`, `marcador`, `invisivel`, `orto`,
  `notacao-ilegal`, `suspeito`, `sel-objeto`, `objeto`, `faixa`, `ncab:<id>` (o número
  da nota na faixa) e as `fonte:*`.

As tags fixas (`FIXAS`) são configuradas de uma vez em `configurar`; uma célula de
tabela pede `preguicoso=True` e as recebe sob demanda (`configurar_fixa`), porque
uma grade de 400 células não pode pagar 8.000 `tag configure` (ED-04).

Os valores vão no nome da tag depois dos dois-pontos; espaço vira `%20` porque o Tk
aceita, mas o olho não.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from tkinter import font as tkfont
from typing import Any, Iterable

from core.editor import dialeto

MARCADORES = ("b", "i", "vers", "sobre", "sub")
PREFIXOS_DE_MARCADOR = ("fam:", "corpo:")
INDEPENDENTES_VISUAIS = ("u", "s", "code")
PREFIXOS_INDEPENDENTES = ("cor:", "fundo:", "cls:", "lang:", "tit:", "link:", "ref:", "nota:", "papel:",
                          "nag:", "chave:", "pagina:")
QUEBRAS = ("qs", "qp")
PREFIXOS_DE_QUEBRA = ("qi:",)
PREFIXOS_DE_PARAGRAFO = ("p:", "al:", "rec1:", "recE:", "recD:", "antes:", "depois:", "entre:", "li:", "dn:")
PARAGRAFO_SIMPLES = ("manter", "manterl", "cit")
DE_TELA = ("protegido", "marcador", "invisivel", "orto", "notacao-ilegal", "suspeito", "sel-objeto", "objeto",
           "quebra", "faixa")

#: Os tamanhos e pesos que um navegador dá aos títulos, para quando a folha não diz.
TITULOS_PADRAO = {1: (2.0, True), 2: (1.5, True), 3: (1.17, True), 4: (1.0, True), 5: (0.83, True), 6: (0.67, True)}
#: Classes de caractere do dialeto que a tela pinta sem folha (o que `CSS_DOS_ESTILOS` diz).
PAPEIS_NA_TELA = {"comentario": {"italico": True}, "lance": {}, "nag": {}, "figurina": {}, "jogador": {},
                  "abertura": {}}

_RE_PT = re.compile(r"^\s*([0-9.]+)\s*(pt|px|em|%|rem)?\s*$")


def nome(prefixo: str, valor: Any) -> str:
    """`prefixo:valor` com o espaço escondido — um nome de tag legível e único."""
    return f"{prefixo}{str(valor).replace(' ', '%20')}"


def valor(tag: str) -> str:
    """O valor de uma tag `prefixo:valor` (o inverso de `nome`)."""
    return tag.split(":", 1)[1].replace("%20", " ") if ":" in tag else ""


def prefixo(tag: str) -> str:
    return tag.split(":", 1)[0] + ":" if ":" in tag else tag


def e_de_tela(tag: str) -> bool:
    return tag in DE_TELA or tag.startswith("fonte:") or tag == "sel"


def e_de_paragrafo(tag: str) -> bool:
    return tag in PARAGRAFO_SIMPLES or tag.startswith(PREFIXOS_DE_PARAGRAFO)


def e_de_caractere(tag: str) -> bool:
    return (tag in MARCADORES or tag in INDEPENDENTES_VISUAIS or tag.startswith(PREFIXOS_DE_MARCADOR)
            or tag.startswith(PREFIXOS_INDEPENDENTES))


def e_quebra(tag: str) -> bool:
    return tag in QUEBRAS or tag.startswith(PREFIXOS_DE_QUEBRA)


# ----------------------------------------------------------------------
# O estilo de tela
# ----------------------------------------------------------------------

@dataclass
class EstiloDeTela:
    """
    O que o modo texto usa para desenhar quando o livro não diz: a família e o corpo
    base, as cores, e um zoom que só mexe na tela. As folhas do capítulo (CSS mínima)
    entram por cima, em `Estilos`.
    """

    familia: str = "Georgia"
    corpo_pt: float = 12.0
    familia_mono: str = "Consolas"
    cor: str = "#1f1f1f"
    fundo: str = "#ffffff"
    cor_do_link: str = "#0645ad"
    cor_da_nota: str = "#7a3e00"
    fundo_protegido: str = "#eeeeee"
    zoom: float = 1.0
    largura_de_leitura: int = 0          # 0 = toda a janela; N = ~N caracteres, faixa cinza fora

    def corpo_na_tela(self, corpo_pt: float | None = None) -> int:
        base = self.corpo_pt if corpo_pt is None else float(corpo_pt)
        return max(4, int(round(base * self.zoom)))


def _em(valor_css: str, base: float) -> float | None:
    m = _RE_PT.match(valor_css or "")
    if not m:
        return None
    numero, unidade = float(m.group(1)), (m.group(2) or "pt")
    if unidade == "pt":
        return numero
    if unidade == "px":
        return numero * 0.75
    if unidade in ("em", "rem"):
        return numero * base
    if unidade == "%":
        return numero * base / 100.0
    return None


@dataclass
class Estilos:
    """
    A cascata que a tela lê: os estilos do dialeto (§6.3), os padrões dos títulos e as
    folhas do capítulo (`css_minima.Folha`, já em cascata). `de_paragrafo(nome)` dá o que
    o bloco inteiro recebe; `de_caractere(papel|classes)` dá o que um trecho acrescenta.
    """

    tela: EstiloDeTela = field(default_factory=EstiloDeTela)
    folha: Any = None                   # css_minima.Folha ou None

    def _css(self, elemento: str, classes: Iterable[str] = ()) -> dict[str, str]:
        if self.folha is None:
            return {}
        try:
            return self.folha.estilo_de(elemento, classes)
        except Exception:      # noqa: BLE001 — uma folha estranha não derruba a tela
            return {}

    def de_paragrafo(self, estilo: str) -> dict[str, Any]:
        """
        `familia`, `corpo_pt`, `negrito`, `italico`, `versalete`, `alinhamento`,
        `recuo_primeira_em`, `recuo_esquerda_em`, `recuo_direita_em`, `antes_em`,
        `depois_em`, `entrelinha`, `cor`, `fundo` — os que a folha ou o padrão fixam.
        """
        saida: dict[str, Any] = {"familia": self.tela.familia, "corpo_pt": self.tela.corpo_pt, "negrito": False,
                                 "italico": False, "versalete": False, "cor": self.tela.cor}
        elemento, classe, _docx = dialeto.ESTILOS_DE_PARAGRAFO.get(estilo, ("p", estilo, ""))
        if elemento.startswith("h") and elemento[1:].isdigit():
            fator, negrito = TITULOS_PADRAO[int(elemento[1:])]
            saida["corpo_pt"] = self.tela.corpo_pt * fator
            saida["negrito"] = negrito
        elif estilo == "comentario":
            saida["italico"] = True
        elif estilo in ("legenda",):
            saida["corpo_pt"] = self.tela.corpo_pt * 0.9
            saida["alinhamento"] = "centro"
        elif estilo == "cabecalho-diagrama":
            saida["negrito"] = True
            saida["alinhamento"] = "centro"
        elif estilo in ("epigrafe", "assinatura"):
            saida["alinhamento"] = "direita"
            saida["italico"] = estilo == "epigrafe"
        elif estilo == "notacao":
            saida["recuo_primeira_em"] = 0.0
        css = dict(self._css("p"))
        if elemento != "p":
            css.update(self._css(elemento))
        if classe:
            css.update(self._css("p", [classe]))
            css.update(self._css("", [classe]))
        _aplicar_css(saida, css, self.tela)
        return saida

    def de_caractere(self, papel: str = "", classes: Iterable[str] = ()) -> dict[str, Any]:
        """O que `span.<classe>` acrescenta ao trecho: negrito, itálico, versalete, cor, fundo, família, corpo."""
        saida: dict[str, Any] = {}
        todas = list(classes)
        if papel:
            saida.update(PAPEIS_NA_TELA.get(papel, {}))
            todas.append(dialeto.CLASSE_DO_PAPEL.get(papel, papel))
        css = {}
        for classe in todas:
            css.update(self._css("span", [classe]))
            css.update(self._css("", [classe]))
        _aplicar_css(saida, css, self.tela)
        return saida


def _aplicar_css(saida: dict[str, Any], css: dict[str, str], tela: EstiloDeTela) -> None:
    peso = css.get("font-weight", "")
    if peso:
        saida["negrito"] = peso in ("bold", "bolder") or (peso.isdigit() and int(peso) >= 600)
    estilo = css.get("font-style", "")
    if estilo:
        saida["italico"] = estilo in ("italic", "oblique")
    variante = css.get("font-variant", "")
    if variante:
        saida["versalete"] = "small-caps" in variante
    tamanho = css.get("font-size", "")
    if tamanho:
        pt = _em(tamanho, tela.corpo_pt)
        if pt:
            saida["corpo_pt"] = pt
    familia = css.get("font-family", "")
    if familia:
        saida["familia"] = familia.split(",")[0].strip().strip("\"'")
    cor = css.get("color", "")
    if cor and cor.startswith("#") and len(cor) in (4, 7):
        saida["cor"] = _cor_longa(cor)
    fundo = css.get("background-color", "") or css.get("background", "")
    if fundo and fundo.startswith("#") and len(fundo.split()[0]) in (4, 7):
        saida["fundo"] = _cor_longa(fundo.split()[0])
    alinhamento = css.get("text-align", "")
    if alinhamento in dialeto.ALINHAMENTO_DO_CSS:
        saida["alinhamento"] = dialeto.ALINHAMENTO_DO_CSS[alinhamento]
    recuo = css.get("text-indent", "")
    if recuo:
        em = _em(recuo, tela.corpo_pt)
        if em is not None:
            saida["recuo_primeira_em"] = em / tela.corpo_pt
    for chave, campo in (("margin-left", "recuo_esquerda_em"), ("margin-right", "recuo_direita_em"),
                         ("margin-top", "antes_em"), ("margin-bottom", "depois_em")):
        if css.get(chave):
            em = _em(css[chave], tela.corpo_pt)
            if em is not None:
                saida[campo] = em / tela.corpo_pt
    if css.get("line-height"):
        m = _RE_PT.match(css["line-height"])
        if m and not m.group(2):
            saida["entrelinha"] = float(m.group(1))
    decoracao = css.get("text-decoration", "")
    if "underline" in decoracao:
        saida["sublinhado"] = True
    if "line-through" in decoracao:
        saida["tachado"] = True


def _cor_longa(cor: str) -> str:
    if len(cor) == 4:
        return "#" + "".join(c * 2 for c in cor[1:])
    return cor


# ----------------------------------------------------------------------
# A fonte derivada
# ----------------------------------------------------------------------

class Fontes:
    """Um `tkfont.Font` por combinação (família, corpo na tela, negrito, itálico, variante), em cache."""

    def __init__(self, master: Any = None):
        self.master = master
        self._cache: dict[tuple, tkfont.Font] = {}

    def fonte(self, familia: str, corpo: int, negrito: bool = False, italico: bool = False,
              variante: str = "") -> tkfont.Font:
        corpo_real = corpo
        if variante in ("sobre", "sub"):
            corpo_real = max(4, int(round(corpo * 0.75)))
        elif variante == "vers":
            corpo_real = max(4, int(round(corpo * 0.85)))
        chave = (familia, corpo_real, negrito, italico)
        if chave not in self._cache:
            self._cache[chave] = tkfont.Font(root=self.master, family=familia, size=corpo_real,
                                             weight="bold" if negrito else "normal",
                                             slant="italic" if italico else "roman")
        return self._cache[chave]

    def __len__(self) -> int:
        return len(self._cache)


def nome_da_fonte(familia: str, corpo: int, negrito: bool, italico: bool, variante: str) -> str:
    """`fonte:<família>:<corpo>:<b><i><v|o|u>` — o nome da tag derivada."""
    sufixo = ("b" if negrito else "") + ("i" if italico else "")
    sufixo += {"vers": "v", "sobre": "o", "sub": "u"}.get(variante, "")
    return nome("fonte:", f"{familia}:{corpo}:{sufixo}")


def fonte_derivada(estilos: Estilos, estilo_do_paragrafo: str, tags: Iterable[str]) -> tuple[str, dict[str, Any]]:
    """
    O nome da tag `fonte:*` e os seus atributos para um caractere com estas `tags`
    (marcadores, `papel:`, `cls:`) num parágrafo deste estilo — a cascata da DEC-03.
    """
    tags = list(tags)
    base = estilos.de_paragrafo(estilo_do_paragrafo)
    papel = next((valor(t) for t in tags if t.startswith("papel:")), "")
    classes = [c for t in tags if t.startswith("cls:") for c in valor(t).split()]
    if papel or classes:
        base.update(estilos.de_caractere(papel, classes))
    familia = base.get("familia", estilos.tela.familia)
    corpo_pt = float(base.get("corpo_pt", estilos.tela.corpo_pt))
    negrito, italico = bool(base.get("negrito")), bool(base.get("italico"))
    variante = "vers" if base.get("versalete") else ""
    for t in tags:
        if t == "b":
            negrito = True
        elif t == "i":
            italico = True
        elif t == "vers":
            variante = "vers"
        elif t == "sobre":
            variante = "sobre"
        elif t == "sub":
            variante = "sub"
        elif t.startswith("fam:"):
            familia = valor(t)
        elif t.startswith("corpo:"):
            try:
                corpo_pt = float(valor(t))
            except ValueError:
                pass
        elif t == "code":
            familia = estilos.tela.familia_mono
    if familia == "simbolos":
        familia = estilos.tela.familia
    corpo = estilos.tela.corpo_na_tela(corpo_pt)
    return nome_da_fonte(familia, corpo, negrito, italico, variante), {
        "familia": familia, "corpo": corpo, "negrito": negrito, "italico": italico, "variante": variante,
        "cor": base.get("cor", estilos.tela.cor), "fundo": base.get("fundo", ""),
    }


# ----------------------------------------------------------------------
# Configuração das tags no widget
# ----------------------------------------------------------------------

def opcoes_das_fixas(estilos: Estilos, fontes: Fontes) -> dict[str, dict[str, Any]]:
    """As tags fixas do widget e as opções de cada uma: cores das independentes, das quebras e das de tela."""
    tela = estilos.tela
    return {
        "u": {"underline": True}, "s": {"overstrike": True},
        "code": {"font": fontes.fonte(tela.familia_mono, tela.corpo_na_tela())},
        "marcador": {"foreground": tela.cor}, "protegido": {}, "invisivel": {"foreground": "#8a8a8a"},
        "orto": {"underline": True, "underlinefg": "#c00000"},
        "notacao-ilegal": {"background": "#ffb060", "bgstipple": "gray50", "relief": "raised", "borderwidth": 1},
        "suspeito": {"background": "#fff3a0"}, "sel-objeto": {"background": "#b8d4ff"},
        "objeto": {}, "faixa": {"spacing1": _px(1.0, tela)},
        "cit": {"lmargin1": _px(2.0, tela), "lmargin2": _px(2.0, tela), "rmargin": _px(2.0, tela)},
        "manter": {}, "manterl": {}, "qs": {}, "qp": {}, "quebra": {},
    }


FIXAS = frozenset({"u", "s", "code", "marcador", "protegido", "invisivel", "orto", "notacao-ilegal", "suspeito",
                   "sel-objeto", "objeto", "faixa", "cit", "manter", "manterl", "qs", "qp", "quebra"})


def e_fixa(tag: str) -> bool:
    return tag in FIXAS


def configurar(texto: Any, estilos: Estilos, fontes: Fontes, preguicoso: bool = False) -> None:
    """
    As cores do widget e as tags fixas. Com `preguicoso` (as células de tabela, que são
    centenas), só as cores: cada tag fixa é configurada na primeira vez que entra
    (`configurar_fixa`), para a grade de 400 células não pagar 8.000 `tag configure`.
    """
    tela = estilos.tela
    texto.configure(background=tela.fundo, foreground=tela.cor, insertbackground=tela.cor)
    if not preguicoso:
        for tag, opcoes in opcoes_das_fixas(estilos, fontes).items():
            texto.tag_configure(tag, **opcoes)
    texto.tag_raise("sel")


def configurar_fixa(texto: Any, tag: str, estilos: Estilos, fontes: Fontes) -> None:
    """Uma tag fixa, sob demanda (o caminho preguiçoso das células)."""
    opcoes = opcoes_das_fixas(estilos, fontes).get(tag)
    if opcoes is not None:
        texto.tag_configure(tag, **opcoes)
        texto.tag_raise("sel")


def configurar_paragrafo(texto: Any, tag: str, estilos: Estilos, fontes: Fontes) -> None:
    """Configura uma tag de parágrafo (`p:corpo`, `al:centro`, `rec1:1.2`, `li:2`…) sob demanda."""
    tela = estilos.tela
    pref = prefixo(tag)
    if pref == "p:":
        estilo = estilos.de_paragrafo(valor(tag))
        opcoes: dict[str, Any] = {"foreground": estilo.get("cor", tela.cor)}
        if estilo.get("fundo"):
            opcoes["background"] = estilo["fundo"]
        if "alinhamento" in estilo:
            opcoes["justify"] = {"esquerda": "left", "centro": "center", "direita": "right",
                                 "justificado": "left"}.get(estilo["alinhamento"], "left")
        if "recuo_primeira_em" in estilo:
            opcoes["lmargin1"] = _px(estilo["recuo_primeira_em"] + estilo.get("recuo_esquerda_em", 0.0), tela)
        if "recuo_esquerda_em" in estilo:
            opcoes["lmargin2"] = _px(estilo["recuo_esquerda_em"], tela)
            opcoes.setdefault("lmargin1", _px(estilo["recuo_esquerda_em"], tela))
        if "recuo_direita_em" in estilo:
            opcoes["rmargin"] = _px(estilo["recuo_direita_em"], tela)
        if "antes_em" in estilo:
            opcoes["spacing1"] = _px(estilo["antes_em"], tela)
        if "depois_em" in estilo:
            opcoes["spacing3"] = _px(estilo["depois_em"], tela)
        texto.tag_configure(tag, **opcoes)
        texto.tag_lower(tag)
    elif pref == "al:":
        texto.tag_configure(tag, justify={"esquerda": "left", "centro": "center", "direita": "right",
                                          "justificado": "left"}.get(valor(tag), "left"))
    elif pref == "rec1:":
        texto.tag_configure(tag, lmargin1=_px(float(valor(tag)), tela))
    elif pref == "recE:":
        texto.tag_configure(tag, lmargin2=_px(float(valor(tag)), tela), lmargin1=_px(float(valor(tag)), tela))
    elif pref == "recD:":
        texto.tag_configure(tag, rmargin=_px(float(valor(tag)), tela))
    elif pref == "antes:":
        texto.tag_configure(tag, spacing1=_px(float(valor(tag)), tela))
    elif pref == "depois:":
        texto.tag_configure(tag, spacing3=_px(float(valor(tag)), tela))
    elif pref == "entre:":
        texto.tag_configure(tag, spacing2=max(0, int(round((float(valor(tag)) - 1.0) * tela.corpo_na_tela() * 1.2))))
    elif pref == "li:":
        nivel = int(valor(tag))
        texto.tag_configure(tag, lmargin1=_px(1.5 * nivel, tela), lmargin2=_px(1.5 * nivel + 1.2, tela))
    elif pref == "dn:":
        # Um paragrafo da faixa de notas (ED-04): recuado, com a margem que o numero ocupa.
        texto.tag_configure(tag, lmargin1=_px(0.5, tela), lmargin2=_px(2.0, tela))


def configurar_caractere(texto: Any, tag: str, estilos: Estilos, fontes: Fontes) -> None:
    """Configura uma tag independente com valor (`cor:`, `fundo:`, `link:`, `nota:`…) sob demanda."""
    tela = estilos.tela
    pref = prefixo(tag)
    if pref == "cor:":
        texto.tag_configure(tag, foreground=valor(tag))
    elif pref == "fundo:":
        cor = valor(tag)
        opcoes: dict[str, Any] = {"background": cor}
        if _luminancia(cor) < 0.18:
            opcoes["foreground"] = "#ffffff"       # realce escuro: texto branco (§8.2)
        texto.tag_configure(tag, **opcoes)
    elif pref == "link:":
        texto.tag_configure(tag, foreground=tela.cor_do_link, underline=True)
    elif pref == "nota:":
        texto.tag_configure(tag, foreground=tela.cor_da_nota, offset=_px(0.35, tela))
    elif pref == "ref:":
        texto.tag_configure(tag, foreground=tela.cor_do_link)
    elif pref == "papel:":
        estilo = estilos.de_caractere(valor(tag))
        opcoes = {}
        if estilo.get("cor"):
            opcoes["foreground"] = estilo["cor"]
        if estilo.get("fundo"):
            opcoes["background"] = estilo["fundo"]
        texto.tag_configure(tag, **opcoes)
    elif pref == "cls:":
        estilo = estilos.de_caractere("", valor(tag).split())
        opcoes = {}
        if estilo.get("cor"):
            opcoes["foreground"] = estilo["cor"]
        if estilo.get("fundo"):
            opcoes["background"] = estilo["fundo"]
        if estilo.get("sublinhado"):
            opcoes["underline"] = True
        texto.tag_configure(tag, **opcoes)
    elif pref == "pagina:":
        texto.tag_configure(tag, foreground="#8a8a8a")
    elif pref in ("lang:", "tit:", "nag:", "chave:"):
        texto.tag_configure(tag)


def configurar_fonte(texto: Any, tag: str, atributos: dict[str, Any], fontes: Fontes, estilos: Estilos) -> None:
    """Uma tag derivada `fonte:*`: a fonte do cache, e o deslocamento de sobre/subscrito."""
    fonte = fontes.fonte(atributos["familia"], atributos["corpo"], atributos["negrito"], atributos["italico"],
                         atributos["variante"])
    opcoes: dict[str, Any] = {"font": fonte}
    if atributos["variante"] == "sobre":
        opcoes["offset"] = max(1, int(round(atributos["corpo"] * 0.4)))
    elif atributos["variante"] == "sub":
        opcoes["offset"] = -max(1, int(round(atributos["corpo"] * 0.2)))
    else:
        opcoes["offset"] = 0
    texto.tag_configure(tag, **opcoes)
    texto.tag_raise(tag)
    for de_tela in ("sel", "sel-objeto", "suspeito", "notacao-ilegal", "orto"):
        try:
            texto.tag_raise(de_tela)
        except Exception:      # noqa: BLE001 — a tag pode não existir ainda
            pass


def _px(em: float, tela: EstiloDeTela) -> int:
    """`em` do corpo base → pixels de tela (1 pt ≈ 1,33 px a 96 dpi, vezes o zoom)."""
    return max(0, int(round(em * tela.corpo_na_tela() * 1.333)))


def _luminancia(cor: str) -> float:
    cor = cor.lstrip("#")
    if len(cor) == 3:
        cor = "".join(c * 2 for c in cor)
    try:
        r, g, b = (int(cor[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return 1.0

    def canal(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)

