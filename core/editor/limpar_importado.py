"""
Limpar a marcação importada (ED-15; docs/ANALISE_JANELA_EDITOR.md §4.2): o XHTML que o
Calibre, o *immersive-translate* e outros conversores deixam num EPUB, reescrito no
dialeto do editor, para o modo texto deixar de mostrar tudo como ilha.

## O que muda

- **Atributos de ferramenta:** `data-*` que o dialeto não conhece (`data-imt_insert_failed`,
  …) saem; os do diagrama, da origem, da página e das notas ficam.
- **Classes de ferramenta:** `notranslate`, `immersive-translate-*` saem.
- **Classes `calibreN` viram estilo do dialeto** (decisão do usuário, 2026-09-30): a regra
  CSS da classe é lida da folha do livro e traduzida — negrito → `<strong>`, itálico →
  `<em>`, sublinhado → `<u>`, riscado → `<s>`, versalete → `span.versalete`, sobrescrito
  e subscrito → `<sup>`/`<sub>`; num bloco, `text-align` vira o alinhamento do parágrafo
  e negrito/itálico do bloco inteiro embrulham o conteúdo. O resto da regra (fonte,
  margens em pt, cores de fundo…) não tem lugar no dialeto: sai, e o relatório conta.
- **`style` direto:** fica só o que o dialeto lê (`PROPRIEDADES_DE_TRECHO`,
  `text-align`); o resto sai e é contado.
- **Embrulhos:** `span` e `font` sem atributo que sobre são desembrulhados; `div` que só
  embrulha blocos é desembrulhado, e o que embrulha texto vira `<p>`.
- **Imagem sozinha:** `<p>`/`<div>` que só têm uma `<img>` viram `<figure>` (o
  `p.diagrama > img` do Calibre é uma figura, não o diagrama do editor).
- **Âncoras:** com `ids_usados` (os alvos de `href` do livro), `<a id>` vazia e `id` de
  `span` que ninguém aponta saem; a âncora usada que abre um bloco passa a ser o `id` dele.
- **Nada de ferramenta, nada muda:** o texto volta byte a byte (as entidades inclusive).

O que fica como ilha é o que não tem tradução no dialeto — figurina desenhada como
`<img>` no meio do texto, por exemplo — e o relatório mostra a contagem antes/depois.

**Nunca apaga texto.** Um elemento de ferramenta é desembrulhado, não removido — o
*immersive-translate* põe a tradução num `span`, e é texto do livro.

Só `xhtml.analisar` (expat, da biblioteca padrão) — nada novo (DEC-07). Sem Tk.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from core.editor import dialeto, xhtml
from core.editor.xhtml import PI, Comentario, No, Texto

#: Os `data-*` que o dialeto lê e escreve: ficam.
DATA_DO_DIALETO = frozenset(dialeto.ATRIBUTOS_DE_ORIGEM) | frozenset(dialeto.ATRIBUTOS_DE_DIAGRAMA) | frozenset({
    "data-pagina", "data-chave", "data-eco", "data-nag", "data-ref", "data-epub-type",
})
_RE_CLASSE_DE_FERRAMENTA = re.compile(r"^(notranslate|immersive-translate(-.*)?|imt-.*)$")
_RE_CALIBRE = re.compile(r"^calibre\d*$")
_RE_ESTILO_DE_FERRAMENTA = re.compile(r"immersive-translate|\bimt-")
BLOCOS = frozenset({"p", "h1", "h2", "h3", "h4", "h5", "h6", "div", "li", "blockquote", "figure", "table",
                    "ul", "ol", "dl", "pre", "hr", "section", "aside", "header", "footer", "figcaption",
                    "tr", "td", "th", "thead", "tbody", "caption", "nav", "dt", "dd"})
VAZIOS = frozenset({"br", "hr", "img", "col", "area", "input", "meta", "link", "wbr", "source"})
#: Blocos cujo conteúdo é texto corrido (o negrito/itálico de bloco embrulha o conteúdo).
BLOCOS_DE_TEXTO = frozenset({"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "dt", "dd", "figcaption", "caption"})
ALINHAMENTOS = frozenset({"left", "center", "right", "justify"})

_RE_REGRA = re.compile(r"([^{}@;]+)\{([^{}]*)\}")
_RE_COMENTARIO_CSS = re.compile(r"/\*.*?\*/", re.S)
_RE_SELETOR_DE_CLASSE = re.compile(r"^\s*([a-zA-Z][\w-]*)?\.(calibre\d*)\s*$")


@dataclass
class Relatorio:
    """O que a limpeza fez: `trocas` e `descartadas` contam por tipo; `avisos` em frases."""

    trocas: Counter = field(default_factory=Counter)
    descartadas: Counter = field(default_factory=Counter)
    avisos: list[str] = field(default_factory=list)
    ilhas_antes: int = 0
    ilhas_depois: int = 0

    def somar(self, outro: "Relatorio") -> None:
        self.trocas.update(outro.trocas)
        self.descartadas.update(outro.descartadas)
        self.avisos.extend(outro.avisos)
        self.ilhas_antes += outro.ilhas_antes
        self.ilhas_depois += outro.ilhas_depois

    def linhas(self) -> list[str]:
        saida = [f"ilhas: {self.ilhas_antes} → {self.ilhas_depois}"]
        saida += [f"{nome}: {n}" for nome, n in sorted(self.trocas.items())]
        if self.descartadas:
            saida.append("descartado (sem lugar no dialeto): " +
                         ", ".join(f"{p} ({n})" for p, n in self.descartadas.most_common()))
        return saida + self.avisos


# ----------------------------------------------------------------------
# CSS
# ----------------------------------------------------------------------

def _declaracoes(texto: str) -> dict[str, str]:
    saida: dict[str, str] = {}
    for parte in texto.split(";"):
        nome, _, valor = parte.partition(":")
        nome, valor = nome.strip().lower(), valor.strip()
        if nome and valor:
            saida[nome] = valor.replace("!important", "").strip()
    return saida


def regras_calibre(folhas: Iterable[str]) -> dict[str, dict[str, str]]:
    """`classe → declarações` das regras `.calibreN` / `el.calibreN` das folhas (as seguintes somam)."""
    regras: dict[str, dict[str, str]] = {}
    for css in folhas:
        css = _RE_COMENTARIO_CSS.sub("", css or "")
        for seletores, corpo in _RE_REGRA.findall(css):
            declaracoes = _declaracoes(corpo)
            for seletor in seletores.split(","):
                achado = _RE_SELETOR_DE_CLASSE.match(seletor)
                if achado:
                    regras.setdefault(achado.group(2), {}).update(declaracoes)
    return regras


def _formato(decl: dict[str, str]) -> tuple[list[str], list[str], str, list[str]]:
    """`(embrulhos inline, classes, alinhamento, descartadas)` de um conjunto de declarações."""
    embrulhos: list[str] = []
    classes: list[str] = []
    alinhamento = ""
    descartadas: list[str] = []
    for nome, valor in decl.items():
        v = valor.lower()
        if nome == "font-weight":
            if v in ("bold", "bolder") or (v.isdigit() and int(v) >= 600):
                embrulhos.append("strong")
        elif nome == "font-style":
            if v in ("italic", "oblique"):
                embrulhos.append("em")
        elif nome in ("text-decoration", "text-decoration-line"):
            if "underline" in v:
                embrulhos.append("u")
            if "line-through" in v:
                embrulhos.append("s")
        elif nome == "font-variant":
            if "small-caps" in v:
                classes.append("versalete")
        elif nome == "vertical-align":
            if v in ("super", "sub"):
                embrulhos.append("sup" if v == "super" else "sub")
            elif v not in ("baseline",):
                descartadas.append(nome)
        elif nome == "text-align":
            if v in ALINHAMENTOS:
                alinhamento = v
        else:
            descartadas.append(nome)
    return embrulhos, classes, alinhamento, descartadas


# ----------------------------------------------------------------------
# A árvore
# ----------------------------------------------------------------------

def _escapar(texto: str) -> str:
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escapar_atributo(texto: str) -> str:
    return _escapar(texto).replace('"', "&quot;")


class _Limpador:
    def __init__(self, doc: xhtml.Documento, regras: dict[str, dict[str, str]], ids_usados: set[str] | None,
                 relatorio: Relatorio):
        self.doc = doc
        self.regras = regras
        self.ids_usados = ids_usados
        self.rel = relatorio

    # -- atributos ---------------------------------------------------------------

    def _limpar_atributos(self, no: No, bloco: bool) -> tuple[list[str], list[str], str]:
        """Tira o que é de ferramenta de `no.attrs`; devolve `(embrulhos, classes novas, alinhamento)`."""
        embrulhos: list[str] = []
        novas: list[str] = []
        alinhamento = ""
        for nome in list(no.attrs):
            if nome.startswith("data-") and nome not in DATA_DO_DIALETO:
                del no.attrs[nome]
                self.rel.trocas["atributo de ferramenta removido"] += 1
        classes = no.attrs.get("class", "").split()
        mantidas: list[str] = []
        for classe in classes:
            if _RE_CLASSE_DE_FERRAMENTA.match(classe):
                self.rel.trocas["classe de ferramenta removida"] += 1
            elif _RE_CALIBRE.match(classe):
                e, c, a, descartadas = _formato(self.regras.get(classe, {}))
                embrulhos += e
                novas += c
                alinhamento = a or alinhamento
                self.rel.descartadas.update(descartadas)
                self.rel.trocas["classe calibre convertida"] += 1
            else:
                mantidas.append(classe)
        style_antes = no.attrs.get("style")
        if "style" in no.attrs:
            e, c, a, descartadas = _formato(_declaracoes(no.attrs["style"]))
            # No `style` direto, as propriedades de trecho que o dialeto lê ficam como estão.
            ficam = {k: v for k, v in _declaracoes(no.attrs["style"]).items()
                     if k in dialeto.PROPRIEDADES_DE_TRECHO and not bloco}
            descartadas = [d for d in descartadas if d not in ficam]
            embrulhos += e
            novas += c
            alinhamento = a or alinhamento
            self.rel.descartadas.update(descartadas)
            if ficam:
                no.attrs["style"] = "; ".join(f"{k}: {v}" for k, v in ficam.items())
            else:
                del no.attrs["style"]
        if bloco and alinhamento:
            no.attrs["style"] = f"text-align: {alinhamento}"
        if style_antes is not None and no.attrs.get("style") != style_antes:
            self.rel.trocas["style direto convertido"] += 1
        if not bloco:
            mantidas += [c for c in novas if c not in mantidas]
        if mantidas:
            no.attrs["class"] = " ".join(mantidas)
        else:
            no.attrs.pop("class", None)
        return embrulhos, (novas if bloco else []), alinhamento

    # -- nós ----------------------------------------------------------------------

    def filhos(self, no: No) -> list:
        saida: list = []
        for filho in no.filhos:
            if isinstance(filho, No):
                saida.extend(self.no(filho))
            else:
                saida.append(filho)
        return saida

    def no(self, no: No) -> list:
        nome = no.nome
        if nome.startswith("{"):
            return [no]                      # elemento de namespace estranho: intacto
        if _intacto(no):
            return [no]                      # o que o dialeto já lê como bloco próprio
        bloco = nome in BLOCOS
        embrulhos, classes_de_bloco, _alinhamento = self._limpar_atributos(no, bloco)
        # Âncora vazia que ninguém aponta.
        if nome == "a" and self.ids_usados is not None and not no.filhos and set(no.attrs) <= {"id", "name"} \
                and no.attrs.get("id", no.attrs.get("name", "")) not in self.ids_usados:
            self.rel.trocas["âncora sem uso removida"] += 1
            return []
        if nome in ("span", "font") and "id" in no.attrs and self.ids_usados is not None \
                and no.attrs["id"] not in self.ids_usados:
            del no.attrs["id"]
            self.rel.trocas["id sem uso removido"] += 1
        if nome == "font":
            cor = no.attrs.pop("color", "")
            for atributo in ("face", "size"):
                if no.attrs.pop(atributo, None) is not None:
                    self.rel.descartadas[f"font {atributo}"] += 1
            if cor:
                no.attrs["style"] = "; ".join(filter(None, [no.attrs.get("style", ""), f"color: {cor}"]))
            no.nome = nome = "span"
            self.rel.trocas["font vira span"] += 1
        no.filhos = self.filhos(no)
        if bloco and nome in BLOCOS_DE_TEXTO and "id" not in no.attrs:
            self._subir_ancora(no)
        conteudo: list = no.filhos
        # Embrulhos de formato, de dentro para fora na ordem canônica do dialeto.
        ordem = [e for e in dialeto.ORDEM_DE_ANINHAMENTO if e in embrulhos]
        if bloco:
            if ordem and nome in BLOCOS_DE_TEXTO:
                no.filhos = self._embrulhar(conteudo, ordem)
            elif ordem:
                self.rel.descartadas["formato de bloco sem texto"] += 1
            if classes_de_bloco:
                self.rel.descartadas["versalete de bloco"] += len(classes_de_bloco)
        if nome in ("p", "div") and self._so_uma_imagem(no):
            no.nome = nome = "figure"
            no.attrs = {k: v for k, v in no.attrs.items() if k == "id"}
            self.rel.trocas["imagem sozinha vira figure"] += 1
            return [no]
        if nome == "span" and not no.attrs:
            self.rel.trocas["span desembrulhado"] += 1
            return self._embrulhar(conteudo, ordem) if ordem else list(conteudo)
        if nome == "div" and not no.attrs:
            if all(not isinstance(f, No) or f.nome in BLOCOS for f in conteudo) and \
                    all(not isinstance(f, Texto) or not f.texto.strip() for f in conteudo):
                self.rel.trocas["div desembrulhado"] += 1
                return list(conteudo)
            no.nome = "p"
            self.rel.trocas["div de texto vira p"] += 1
        if not bloco and ordem:
            return [self._copia(no, self._embrulhar(no.filhos, ordem))]
        return [no]

    @staticmethod
    def _so_uma_imagem(no: No) -> bool:
        """O bloco é só uma `<img>` (e espaço)? Aí ele é a figura dela."""
        imagens = [f for f in no.filhos if isinstance(f, No)]
        texto = "".join(f.texto for f in no.filhos if isinstance(f, Texto))
        return len(imagens) == 1 and imagens[0].nome == "img" and not texto.strip()

    def _subir_ancora(self, no: No) -> None:
        """`<p><a id="x"></a>…` → `<p id="x">…`: o link continua caindo ali, e a âncora não vira ilha."""
        for k, filho in enumerate(no.filhos):
            if isinstance(filho, Texto) and not filho.texto.strip():
                continue
            if isinstance(filho, No) and filho.nome == "a" and not filho.filhos and set(filho.attrs) == {"id"}:
                no.attrs = {"id": filho.attrs["id"], **no.attrs}
                del no.filhos[k]
                self.rel.trocas["âncora vira id do bloco"] += 1
            return

    @staticmethod
    def _copia(no: No, filhos: list) -> No:
        return No(no.nome, dict(no.attrs), filhos, no.inicio, no.fim, no.linha)

    def _embrulhar(self, conteudo: list, ordem: list[str]) -> list:
        """`conteudo` dentro de `ordem[0] > ordem[1] > …` (o primeiro é o de fora)."""
        if not ordem or not conteudo:
            return list(conteudo)
        for nome in reversed(ordem):
            conteudo = [No(nome, {}, list(conteudo))]
            self.rel.trocas[f"<{nome}> de estilo"] += 1
        return conteudo

    # -- escrever -------------------------------------------------------------------

    def escrever(self, itens: list) -> str:
        partes: list[str] = []
        for item in itens:
            if isinstance(item, Texto):
                partes.append(_escapar(item.texto))
            elif isinstance(item, (Comentario, PI)):
                partes.append(self.doc.cru(item))
            elif isinstance(item, No):
                if _intacto(item):
                    partes.append(self.doc.cru(item))
                    continue
                atributos = "".join(f' {k}="{_escapar_atributo(v)}"' for k, v in item.attrs.items())
                if not item.filhos and item.nome in VAZIOS:
                    partes.append(f"<{item.nome}{atributos}/>")
                else:
                    partes.append(f"<{item.nome}{atributos}>{self.escrever(item.filhos)}</{item.nome}>")
        return "".join(partes)


def _intacto(no: No) -> bool:
    """Elementos que passam intactos: namespace estranho, SVG, MathML e os diagramas do próprio editor."""
    if no.nome.startswith("{") or no.nome in ("svg", "math", "epub:switch"):
        return True
    return no.nome in ("figure", "div") and "diagrama" in no.attrs.get("class", "").split()


def _achar(no: No, nome: str) -> No | None:
    for filho in no.elementos():
        if filho.nome == nome:
            return filho
    return None


def limpar(texto: str, folhas: Iterable[str] = (), ids_usados: set[str] | None = None) -> tuple[str, Relatorio]:
    """
    O XHTML `texto` limpo, e o relatório. `folhas` são os textos CSS do capítulo (de onde vêm
    as regras `calibreN`); `ids_usados`, os alvos de link do livro (sem eles as âncoras ficam).
    Levanta `xhtml.ErroDeXhtml` se o texto não é bem-formado — consertar vem antes.
    """
    relatorio = Relatorio()
    doc = xhtml.analisar(texto)
    corpo = _achar(doc.raiz, "body")
    if corpo is None:
        return texto, relatorio
    limpador = _Limpador(doc, regras_calibre(folhas), ids_usados, relatorio)
    corpo.attrs = {k: v for k, v in corpo.attrs.items()}
    limpador._limpar_atributos(corpo, bloco=True)
    corpo.attrs.pop("style", None)
    miolo = limpador.escrever(limpador.filhos(corpo))
    # O `<style>` que o tradutor injeta no `<head>` (centenas de linhas de variáveis dele).
    cabeca = _achar(doc.raiz, "head")
    cortes = [(no.inicio, no.fim) for no in (cabeca.elementos() if cabeca is not None else ())
              if no.nome == "style" and _RE_ESTILO_DE_FERRAMENTA.search(no.texto())]
    if cortes:
        relatorio.trocas["<style> de ferramenta removido"] += len(cortes)
    if not relatorio.trocas:
        return texto, relatorio        # nada de ferramenta: o texto volta byte a byte (entidades inclusive)
    atributos = "".join(f' {k}="{_escapar_atributo(v)}"' for k, v in corpo.attrs.items())
    fonte = doc.fonte[:corpo.inicio]
    for inicio, fim in sorted(cortes, reverse=True):
        fim_da_linha = fim + 1 if fonte[fim:fim + 1] == b"\n" else fim
        fonte = fonte[:inicio] + fonte[fim_da_linha:]
    antes = fonte.decode(doc.codificacao, errors="replace")
    depois = doc.fatia(corpo.fim, len(doc.fonte))
    return f"{antes}<body{atributos}>{miolo}</body>{depois}", relatorio


def contar_ilhas(texto: str, arquivo: str = "") -> int:
    """Quantas ilhas (de bloco e de trecho) o leitor faz deste XHTML."""
    from core.editor import modelo

    cap = xhtml.ler(texto, arquivo)
    n = 0
    for bloco in modelo.blocos_do_capitulo(cap):
        if isinstance(bloco, modelo.IlhaBruta):
            n += 1
        for trecho in getattr(bloco, "trechos", ()) or ():
            if trecho.ilha:
                n += 1
    return n


_RE_HREF = re.compile(r"""\shref\s*=\s*["'][^"'#]*#([^"']+)["']""")


def ids_usados(textos: Iterable[str]) -> set[str]:
    """Os alvos (`#id`) dos `href` de todos os textos do livro."""
    usados: set[str] = set()
    for texto in textos:
        usados.update(_RE_HREF.findall(texto or ""))
    return usados


__all__ = ["Relatorio", "limpar", "regras_calibre", "contar_ilhas", "ids_usados", "DATA_DO_DIALETO"]
