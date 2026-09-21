"""
DOCX → modelo: `ler(caminho) -> (Livro, RelatorioDeConversao)` (ED-09b; SPEC_EDITOR
§10.4, §6.2 coluna DOCX, §10.7, DEC-06). `docx_io.ler` é este `ler`.

## Sem `python-docx`

O `python-docx` não expõe nota, marcador, campo, sombreado, idioma nem numeração — é
XML que se lê de qualquer jeito. Lê-se então o pacote com o `zipfile` e o
`xml.etree` da biblioteca padrão: `word/document.xml`, `styles.xml`, `numbering.xml`,
`footnotes.xml`, `endnotes.xml`, `settings.xml`, os `.rels` (imagens e hiperlinks),
`word/media/*` e `docProps/core.xml`. A leitura não depende do extra `[docx]`
(DEC-07), e um DOCX de fora abre onde a escrita precisaria do Word.

## O que vira o quê

O estilo de parágrafo dá o bloco (nome do Word, com a cadeia `basedOn` resolvida):
`Heading n` → `Titulo`; `Primeira`, `Notacao`, `Comentario`, `Destaque`, `Epigrafe`,
`Assinatura`, `Cabecalho de diagrama` → o estilo homônimo; `Quote` → `Citacao`; `List
Paragraph` com `numPr` → `Lista` (aninhada pelo `ilvl`, `startOverride` → `inicio`);
`Caption` → a legenda da tabela que vem depois ("Tabela n: …") ou da figura/diagrama
que veio antes; estilo desconhecido → `corpo`, com aviso uma vez por estilo. O run dá o
trecho (§6.2): `b`, `i`, `u`, `strike`, `smallCaps`, `vertAlign`, `sz` (meio ponto),
`color`, `shd` (fundo exato) e `highlight`, `lang`, `rFonts` (a fonte de símbolos →
`familia="simbolos"`; uma fonte de diagrama → a família; a monoespaçada → `codigo`), e
o estilo de caractere dá o `papel` (`Lance`, `NAG`, `Figurina`, `Jogador`, `Abertura`,
`Comentario (caractere)`), o `versalete` e o `simbolos`. O texto no estilo `Ilha` volta
como texto, com aviso — a ilha original não está no DOCX.

Marcador `pg-n` no começo do parágrafo → `MarcaDePagina`; no meio → `Trecho.pagina`.
`w:br type="page"` → `QuebraDePagina`. Parágrafo vazio com borda inferior →
`Separador`. `w:drawing` → `Figura` (`descr` = alt) ou, quando o `descr` é um FEN,
`Diagrama(modo="png", lado="")`. A tabela 1×1 com `tblCaption="Diagrama"` (ou oito
parágrafos numa fonte de diagrama, no corpo) → `Diagrama` por `fen_de_linhas`, com o
FEN do `tblDescription` quando há, e `lado=""` — o DOCX não diz quem joga (DEC-06).
Notas de rodapé e de fim pelo `footnoteReference`/`endnoteReference`. Hiperlink com
`r:id` → link externo; com `w:anchor` → o bloco do marcador; `REF _Ref<n>` → `Trecho.ref`
com o tipo do alvo. O `w:sdt` do sumário é pulado (o sumário é regenerado dos títulos).
Caixa de texto, comentário, controle de alterações e cabeçalho/rodapé: texto preservado
onde há texto, e um aviso por tipo (§10.7).
"""

from __future__ import annotations

import os
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field, replace
from typing import Any, Sequence

from core.editor import epub, livro_ops, modelo, sumario
from core.editor.conversao import Cronometro, RelatorioDeConversao
from core.editor.modelo import (Bloco, Capitulo, Celula, Citacao, Diagrama, Figura, FormatoDePagina, ItemDeLista,
                                Lista, Livro, MarcaDePagina, Metadados, Nota, Paragrafo, Pessoa, QuebraDePagina,
                                Recurso, Separador, Tabela, Titulo, Trecho)

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "v": "urn:schemas-microsoft-com:vml",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
}
W = "{%s}" % NS["w"]
R = "{%s}" % NS["r"]
A = "{%s}" % NS["a"]
WP = "{%s}" % NS["wp"]
#: O corpo do texto do DOCX (`exportar.CORPO_DO_TEXTO_PT`), para converter pontos em `em`.
CORPO_DO_TEXTO_PT = 11.0
#: Nome do estilo de parágrafo (minúsculas) → estilo do modelo.
ESTILOS_DE_PARAGRAFO = {
    "normal": "corpo", "body text": "corpo", "primeira": "primeira", "notacao": "notacao",
    "comentario": "comentario", "caption": "legenda", "quote": "citacao", "intense quote": "citacao",
    "block text": "citacao", "destaque": "destaque", "epigrafe": "epigrafe", "assinatura": "assinatura",
    "cabecalho de diagrama": "cabecalho-diagrama", "list paragraph": "corpo", "footnote text": "nota",
    "endnote text": "nota", "no spacing": "corpo",
}
#: Estilos de parágrafo que não são conteúdo do livro (o sumário e o cabeçalho dele).
ESTILOS_IGNORADOS = {"toc heading", "toc 1", "toc 2", "toc 3", "toc 4", "toc 5", "toc 6", "toc 7", "toc 8", "toc 9",
                     "table of figures", "header", "footer"}
#: Nome do estilo de caractere (minúsculas) → o que ele diz do trecho.
ESTILOS_DE_CARACTERE = {
    "lance": {"papel": "lance"}, "nag": {"papel": "nag"}, "figurina": {"papel": "figurina"},
    "comentario (caractere)": {"papel": "comentario"}, "jogador": {"papel": "jogador"},
    "abertura": {"papel": "abertura"}, "simbolo": {"familia": "simbolos"}, "versalete": {"versalete": True},
    "ilha": {"ilha": True}, "hyperlink": {}, "footnote reference": {}, "endnote reference": {},
    "html code": {"codigo": True}, "code": {"codigo": True}, "strong": {"negrito": True},
    "emphasis": {"italico": True}, "subtle emphasis": {"italico": True},
    "intense emphasis": {"italico": True, "negrito": True},
}
#: As 16 cores do `w:highlight`.
CORES_DE_REALCE = {
    "yellow": "#ffff00", "green": "#00ff00", "cyan": "#00ffff", "magenta": "#ff00ff", "blue": "#0000ff",
    "red": "#ff0000", "darkBlue": "#000080", "darkCyan": "#008080", "darkGreen": "#008000",
    "darkMagenta": "#800080", "darkRed": "#800000", "darkYellow": "#808000", "darkGray": "#808080",
    "lightGray": "#c0c0c0", "black": "#000000", "white": "#ffffff",
}
FONTES_MONOESPACADAS = {"consolas", "courier new", "courier", "lucida console", "cascadia mono", "cascadia code"}
FONTES_DE_SIMBOLOS = {"simbolos de xadrez", "noto sans symbols2", "segoe ui symbol", "dejavu sans"}
NUMFMT = {"decimal": "decimal", "lowerLetter": "alfa", "upperLetter": "alfa", "lowerRoman": "romano",
          "upperRoman": "romano", "bullet": ""}
ROTULOS = {"tabela": "Tabela", "figura": "Figura", "diagrama": "Diagrama"}
_RE_LEGENDA = re.compile(r"^(Tabela|Figura|Diagrama|Table|Figure|Diagram)\s+(\d+)\s*(?::\s*(.*))?$", re.S)
_RE_REF = re.compile(r"^\s*REF\s+(\S+)")
_RE_SEQ = re.compile(r"^\s*SEQ\s+(\S+)")
_RE_PAGINA = re.compile(r"^pg-(\d+)$")
_RE_FONTE_DE_DIAGRAMA = re.compile(r"-Diagram$", re.IGNORECASE)


def _w(tag: str) -> str:
    return W + tag


def _twips_em(valor: str | None) -> float | None:
    if valor is None:
        return None
    try:
        return round(int(valor) / 20.0 / CORPO_DO_TEXTO_PT, 4)
    except ValueError:
        return None


def _cor(valor: str | None) -> str:
    if not valor or valor.lower() == "auto":
        return ""
    valor = valor.strip().lstrip("#")
    return "#" + valor.lower() if re.fullmatch(r"[0-9A-Fa-f]{6}", valor) else ""


def _ligado(el: ET.Element | None) -> bool:
    """`<w:b/>`, `<w:b w:val="1"/>`, `<w:b w:val="true"/>` ligam; `w:val="0"`/`"false"` desligam."""
    if el is None:
        return False
    return el.get(_w("val"), "true").lower() not in ("0", "false", "off")


def _prop(pai: ET.Element | None, nome: str) -> bool:
    """A propriedade booleana `<w:nome>` de um `rPr`/`pPr`, ligada ou não."""
    if pai is None:
        return False
    return _ligado(pai.find(_w(nome))) if pai.find(_w(nome)) is not None else False


def _fen(descr: str) -> str:
    """O FEN completo de uma descrição que passa em `fen_valido` (só a posição, ou os seis campos)."""
    return descr.strip() if len(descr.split()) >= 6 else modelo.fen_completo(descr.strip())


# ----------------------------------------------------------------------
# O pacote
# ----------------------------------------------------------------------

@dataclass
class _Estilo:
    id: str
    nome: str
    tipo: str
    base: str = ""
    outline: int | None = None
    rpr: ET.Element | None = None


@dataclass
class _Nivel:
    ordenada: bool
    marcador: str
    inicio: int


@dataclass
class _Contexto:
    """O estado de um parágrafo enquanto os runs são lidos."""

    trechos: list[Trecho] = field(default_factory=list)
    marcas_no_inicio: list[int] = field(default_factory=list)
    pagina_pendente: int | None = None
    quebra_pendente: bool = False
    quebra_de_pagina: bool = False
    marcadores: list[str] = field(default_factory=list)
    imagens: list[tuple[str, str, float | None]] = field(default_factory=list)   # (rId, descr, largura_pt)
    campo: list[str] | None = None            # a instrução do campo aberto
    resultado_de_campo: bool = False
    ref_pendente: tuple[str, str] | None = None   # (marcador alvo, texto em cache)

    def texto(self) -> str:
        return "".join(t.texto for t in self.trechos)


class _Pacote:
    def __init__(self, caminho: str, relatorio: RelatorioDeConversao):
        self.relatorio = relatorio
        try:
            with zipfile.ZipFile(caminho) as z:
                self.partes = {n: z.read(n) for n in z.namelist()}
        except (OSError, zipfile.BadZipFile) as erro:
            raise ValueError(f"não deu para abrir {caminho} como DOCX: {erro}") from None
        if "word/document.xml" not in self.partes:
            raise ValueError(f"{os.path.basename(caminho)} não é um DOCX (sem word/document.xml)")
        self.documento = ET.fromstring(self.partes["word/document.xml"])
        self.estilos = self._estilos()
        self.numeracao = self._numeracao()
        self.rels = self._rels("word/_rels/document.xml.rels")
        self.rels_das_notas = {"rodape": self._rels("word/_rels/footnotes.xml.rels"),
                               "fim": self._rels("word/_rels/endnotes.xml.rels")}
        self.notas = {"rodape": self._notas("word/footnotes.xml", "footnote"),
                      "fim": self._notas("word/endnotes.xml", "endnote")}

    def _xml(self, nome: str) -> ET.Element | None:
        if nome not in self.partes:
            return None
        try:
            return ET.fromstring(self.partes[nome])
        except ET.ParseError as erro:
            self.relatorio.aviso(f"{nome} mal-formado, ignorado ({erro})")
            return None

    def _estilos(self) -> dict[str, _Estilo]:
        raiz = self._xml("word/styles.xml")
        saida: dict[str, _Estilo] = {}
        if raiz is None:
            return saida
        for el in raiz.findall(_w("style")):
            id_ = el.get(_w("styleId"), "")
            nome_el = el.find(_w("name"))
            nome = (nome_el.get(_w("val"), "") if nome_el is not None else id_).strip().lower()
            base_el = el.find(_w("basedOn"))
            ppr = el.find(_w("pPr"))
            outline = None
            if ppr is not None and ppr.find(_w("outlineLvl")) is not None:
                try:
                    outline = int(ppr.find(_w("outlineLvl")).get(_w("val"), "0"))
                except ValueError:
                    outline = None
            saida[id_] = _Estilo(id_, nome, el.get(_w("type"), "paragraph"),
                                 base_el.get(_w("val"), "") if base_el is not None else "", outline, el.find(_w("rPr")))
        return saida

    def nome_do_estilo(self, style_id: str, conhecidos: dict[str, Any]) -> tuple[str, str]:
        """`(nome resolvido pela cadeia basedOn até um conhecido, nome próprio)`; vazio se não há."""
        proprio = self.estilos[style_id].nome if style_id in self.estilos else ""
        atual, vistos = style_id, set()
        while atual and atual in self.estilos and atual not in vistos:
            vistos.add(atual)
            estilo = self.estilos[atual]
            conhecido = estilo.nome in conhecidos or estilo.nome in ESTILOS_IGNORADOS
            if conhecido or re.fullmatch(r"heading \d", estilo.nome):
                return estilo.nome, proprio
            atual = estilo.base
        return "", proprio

    def nivel_do_titulo(self, style_id: str) -> int | None:
        atual, vistos = style_id, set()
        while atual and atual in self.estilos and atual not in vistos:
            vistos.add(atual)
            estilo = self.estilos[atual]
            m = re.fullmatch(r"heading (\d)", estilo.nome)
            if m:
                return int(m.group(1))
            if estilo.nome == "title":
                return 1
            if estilo.outline is not None and estilo.tipo == "paragraph":
                return estilo.outline + 1
            atual = estilo.base
        return None

    def _numeracao(self) -> dict[str, dict[int, _Nivel]]:
        raiz = self._xml("word/numbering.xml")
        saida: dict[str, dict[int, _Nivel]] = {}
        if raiz is None:
            return saida
        abstratos: dict[str, dict[int, _Nivel]] = {}
        for abstrato in raiz.findall(_w("abstractNum")):
            niveis: dict[int, _Nivel] = {}
            for lvl in abstrato.findall(_w("lvl")):
                try:
                    ilvl = int(lvl.get(_w("ilvl"), "0"))
                except ValueError:
                    continue
                fmt_el, start_el = lvl.find(_w("numFmt")), lvl.find(_w("start"))
                fmt = fmt_el.get(_w("val"), "decimal") if fmt_el is not None else "decimal"
                inicio_val = start_el.get(_w("val"), "1") if start_el is not None else "1"
                inicio = int(inicio_val) if inicio_val.isdigit() else 1
                marcador = NUMFMT.get(fmt, "")
                ordenada = fmt != "bullet" and fmt != "none"
                if fmt == "bullet":
                    texto_el = lvl.find(_w("lvlText"))
                    texto = texto_el.get(_w("val"), "") if texto_el is not None else ""
                    marcador = {"o": "circulo", "": "quadrado", "": "disco", "•": "disco", "▪": "quadrado",
                                "": ""}.get(texto, "")
                niveis[ilvl] = _Nivel(ordenada, marcador, inicio)
            abstratos[abstrato.get(_w("abstractNumId"), "")] = niveis
        for num in raiz.findall(_w("num")):
            ref = num.find(_w("abstractNumId"))
            niveis = {k: _Nivel(v.ordenada, v.marcador, v.inicio)
                      for k, v in abstratos.get(ref.get(_w("val"), "") if ref is not None else "", {}).items()}
            for sobre in num.findall(_w("lvlOverride")):
                try:
                    ilvl = int(sobre.get(_w("ilvl"), "0"))
                except ValueError:
                    continue
                start = sobre.find(_w("startOverride"))
                if start is not None and ilvl in niveis and start.get(_w("val"), "").isdigit():
                    niveis[ilvl].inicio = int(start.get(_w("val")))
            saida[num.get(_w("numId"), "")] = niveis
        return saida

    def _rels(self, nome: str) -> dict[str, tuple[str, str, bool]]:
        raiz = self._xml(nome)
        saida: dict[str, tuple[str, str, bool]] = {}
        if raiz is None:
            return saida
        for rel in raiz:
            saida[rel.get("Id", "")] = (rel.get("Target", ""), rel.get("Type", ""),
                                        rel.get("TargetMode", "") == "External")
        return saida

    def _notas(self, nome: str, tag: str) -> dict[str, ET.Element]:
        raiz = self._xml(nome)
        if raiz is None:
            return {}
        return {el.get(_w("id"), ""): el for el in raiz.findall(_w(tag))
                if el.get(_w("type"), "") not in ("separator", "continuationSeparator")}

    def midia(self, rid: str, rels: dict[str, tuple[str, str, bool]] | None = None) -> tuple[str, bytes] | None:
        """`(nome do arquivo, bytes)` da imagem de um `r:embed`; `None` se não está no pacote."""
        rels = rels if rels is not None else self.rels
        alvo = rels.get(rid)
        if alvo is None or alvo[2]:
            return None
        caminho = posixpath.normpath(posixpath.join("word", alvo[0])) if not alvo[0].startswith("/") else alvo[0][1:]
        dados = self.partes.get(caminho)
        if dados is None:
            return None
        return posixpath.basename(caminho), dados

    def metadados(self) -> Metadados:
        raiz = self._xml("docProps/core.xml")
        md = Metadados(titulo="", idioma="")

        def texto(tag: str) -> str:
            if raiz is None:
                return ""
            el = raiz.find(tag, NS)
            return (el.text or "").strip() if el is not None else ""

        md.titulo = texto("dc:title")
        autor = texto("dc:creator")
        if autor:
            md.autores = [Pessoa(nome=a.strip()) for a in re.split(r"[;\n]", autor) if a.strip()]
        md.idioma = texto("dc:language")
        md.descricao = texto("dc:description")
        assuntos = texto("dc:subject") or texto("cp:keywords")
        if assuntos:
            md.assuntos = [a.strip() for a in re.split(r"[;,]", assuntos) if a.strip()]
        return md

    def pagina(self) -> FormatoDePagina:
        formato = FormatoDePagina()
        corpo = self.documento.find(_w("body"))
        sect = corpo.find(_w("sectPr")) if corpo is not None else None
        if sect is not None:
            tam = sect.find(_w("pgSz"))
            if tam is not None and tam.get(_w("w"), "").isdigit() and tam.get(_w("h"), "").isdigit():
                formato.largura_mm = round(int(tam.get(_w("w"))) / 20 * 25.4 / 72, 1)
                formato.altura_mm = round(int(tam.get(_w("h"))) / 20 * 25.4 / 72, 1)
            mar = sect.find(_w("pgMar"))
            if mar is not None:
                def mm(nome: str, padrao: float) -> float:
                    valor = mar.get(_w(nome), "")
                    return round(int(valor) / 20 * 25.4 / 72, 1) if valor.lstrip("-").isdigit() else padrao
                sup, ext, inf, int_ = formato.margens_mm
                formato.margens_mm = (mm("top", sup), mm("right", ext), mm("bottom", inf), mm("left", int_))
        settings = self._xml("word/settings.xml")
        if settings is not None:
            formato.espelhadas = settings.find(_w("mirrorMargins")) is not None
            formato.hifenizar = _ligado(settings.find(_w("autoHyphenation"))) if settings.find(
                _w("autoHyphenation")) is not None else False
        formato.numerar_paginas = any(n.startswith("word/footer") for n in self.partes)
        return formato


# ----------------------------------------------------------------------
# O leitor
# ----------------------------------------------------------------------

class _Leitor:
    def __init__(self, pacote: _Pacote, relatorio: RelatorioDeConversao):
        self.p = pacote
        self.relatorio = relatorio
        self.blocos: list[Bloco] = []
        self.notas: list[Nota] = []
        self.recursos: dict[str, Recurso] = {}
        self._imagens_por_rid: dict[str, str] = {}
        self._marcadores: dict[str, str] = {}          # nome do marcador → id do bloco
        self._marcador_pendente: list[str] = []         # marcadores num parágrafo que não vira bloco (legenda)
        self._marcas_pendentes: list[int] = []
        self._refs: list[tuple[Trecho, str]] = []      # (trecho com REF, marcador alvo)
        self._legenda_pendente: tuple[str, int, list[Trecho], list[str]] | None = None   # para a tabela seguinte
        self._itens: list[tuple[int, str, list[Paragrafo]]] = []      # (ilvl, numId, parágrafos) do bloco de lista
        self._citacao: list[Paragrafo] = []
        self._linhas_de_diagrama: list[tuple[str, str]] = []           # (texto, fonte) de parágrafos em fonte
        self._estilos_avisados: set[str] = set()
        self._avisos_unicos: set[str] = set()
        self._contadores = {"tabela": 0, "figura": 0, "diagrama": 0}
        self._em_nota = False
        self._rels_atuais = pacote.rels

    # -- avisos ---------------------------------------------------------------

    def _aviso_unico(self, texto: str) -> None:
        if texto not in self._avisos_unicos:
            self._avisos_unicos.add(texto)
            self.relatorio.aviso(texto)

    # -- fechamentos de grupos ------------------------------------------------

    def _fechar_lista(self) -> None:
        if not self._itens:
            return
        itens = self._itens
        self._itens = []
        self.blocos.append(self._montar_lista(itens, 0, itens[0][0])[0])

    def _montar_lista(self, itens: list[tuple[int, str, list[Paragrafo]]], inicio: int,
                      nivel: int) -> tuple[Lista, int]:
        num_id = itens[inicio][1]
        niveis = self.p.numeracao.get(num_id, {})
        nivel_def = niveis.get(nivel) or niveis.get(0) or _Nivel(False, "", 1)
        lista = Lista(ordenada=nivel_def.ordenada, itens=[], marcador=nivel_def.marcador,
                      inicio=nivel_def.inicio if nivel_def.ordenada else 1)
        i = inicio
        while i < len(itens):
            n, _num, paragrafos = itens[i]
            if n < nivel:
                break
            if n > nivel:
                filhos, i = self._montar_lista(itens, i, n)
                if lista.itens:
                    lista.itens[-1].filhos = filhos
                else:
                    lista.itens.append(ItemDeLista(paragrafos=[Paragrafo(trechos=[Trecho(texto="")])], filhos=filhos))
                continue
            lista.itens.append(ItemDeLista(paragrafos=paragrafos))
            i += 1
        return lista, i

    def _fechar_citacao(self) -> None:
        if self._citacao:
            self.blocos.append(Citacao(blocos=self._citacao))
            self._citacao = []

    def _fechar_diagrama_em_fonte(self) -> None:
        linhas = self._linhas_de_diagrama
        self._linhas_de_diagrama = []
        if not linhas:
            return
        if len(linhas) in (8, 10):
            diagrama = self._diagrama_das_linhas([t for t, _f in linhas], linhas[0][1], "")
            if diagrama is not None:
                self.blocos.append(diagrama)
                return
        for texto, fonte in linhas:      # não era um tabuleiro: os parágrafos voltam como texto naquela fonte
            self.blocos.append(Paragrafo(trechos=[Trecho(texto=texto, familia=fonte)]))

    def _fechar_tudo(self) -> None:
        self._fechar_lista()
        self._fechar_citacao()
        self._fechar_diagrama_em_fonte()

    def _fechar_exceto(self, *grupos: str) -> None:
        if "lista" not in grupos:
            self._fechar_lista()
        if "citacao" not in grupos:
            self._fechar_citacao()
        if "diagrama" not in grupos:
            self._fechar_diagrama_em_fonte()

    def _emitir(self, bloco: Bloco) -> None:
        """Um bloco novo recebe as marcas de página e os marcadores pendentes."""
        for pagina in self._marcas_pendentes:
            self.blocos.append(MarcaDePagina(pagina=pagina))
        self._marcas_pendentes = []
        for nome in self._marcador_pendente:
            self._marcadores[nome] = bloco.id
            bloco.id_persistente = True
        self._marcador_pendente = []
        self.blocos.append(bloco)

    # -- o corpo ----------------------------------------------------------------

    def corpo(self) -> None:
        raiz = self.p.documento.find(_w("body"))
        if raiz is None:
            raise ValueError("DOCX sem <w:body>")
        self._filhos(raiz)
        self._fechar_tudo()
        for pagina in self._marcas_pendentes:
            self.blocos.append(MarcaDePagina(pagina=pagina))
        self._marcas_pendentes = []
        self._resolver_marcadores()
        self._avisar_partes_ignoradas()

    def _filhos(self, pai: ET.Element) -> None:
        for el in pai:
            tag = el.tag
            if tag == _w("p"):
                self._paragrafo(el)
            elif tag == _w("tbl"):
                self._fechar_tudo()
                self._tabela(el)
            elif tag == _w("sdt"):
                if self._e_sumario(el):
                    continue
                conteudo = el.find(_w("sdtContent"))
                if conteudo is not None:
                    self._filhos(conteudo)
            elif tag == _w("bookmarkStart"):
                nome = el.get(_w("name"), "")
                m = _RE_PAGINA.match(nome)
                if m:
                    self._marcas_pendentes.append(int(m.group(1)))
                elif nome and not nome.startswith("_GoBack"):
                    self._marcador_pendente.append(nome)
            elif tag in (_w("sectPr"), _w("bookmarkEnd"), _w("proofErr")):
                continue
            elif tag.endswith("}AlternateContent"):
                self._alternate(el)
            else:
                self._aviso_unico(f"elemento {tag.split('}')[-1]} no corpo sem tradução, ignorado")

    def _e_sumario(self, sdt: ET.Element) -> bool:
        pr = sdt.find(_w("sdtPr"))
        if pr is None:
            return False
        galeria = pr.find(_w("docPartObj") + "/" + _w("docPartGallery"))
        return galeria is not None and galeria.get(_w("val"), "") == "Table of Contents"

    def _alternate(self, el: ET.Element) -> None:
        """`mc:AlternateContent` (caixa de texto, forma): o texto de dentro é preservado, com aviso."""
        textos: list[str] = []
        for p in el.iter(_w("p")):
            texto = "".join(t.text or "" for t in p.iter(_w("t")))
            if texto.strip():
                textos.append(texto)
        if textos:
            self._aviso_unico("caixa de texto: o texto foi preservado como parágrafo (§10.7)")
            for texto in textos:
                self._emitir(Paragrafo(trechos=[Trecho(texto=texto)]))

    # -- parágrafos ---------------------------------------------------------------

    def _ppr(self, p: ET.Element) -> ET.Element | None:
        return p.find(_w("pPr"))

    def _style_id(self, ppr: ET.Element | None) -> str:
        if ppr is None:
            return ""
        st = ppr.find(_w("pStyle"))
        return st.get(_w("val"), "") if st is not None else ""

    def _paragrafo(self, p: ET.Element) -> None:
        ctx = self._paragrafo_interno(p)
        if ctx is not None and ctx.quebra_de_pagina and (ctx.texto().strip() or ctx.imagens):
            # a quebra de página no fim de um parágrafo com texto: o parágrafo, e depois a quebra
            self._fechar_tudo()
            self.blocos.append(QuebraDePagina())

    def _paragrafo_interno(self, p: ET.Element) -> _Contexto | None:
        ppr = self._ppr(p)
        style_id = self._style_id(ppr)
        nome, proprio = self.p.nome_do_estilo(style_id, ESTILOS_DE_PARAGRAFO)
        nivel = self.p.nivel_do_titulo(style_id)
        if nivel is None and ppr is not None and ppr.find(_w("outlineLvl")) is not None:
            try:
                nivel = int(ppr.find(_w("outlineLvl")).get(_w("val"), "0")) + 1
            except ValueError:
                nivel = None
        if nome in ESTILOS_IGNORADOS:
            return None
        ctx = _Contexto()
        self._runs(p, ctx, self.p.rels)
        numpr = ppr.find(_w("numPr")) if ppr is not None else None
        texto = ctx.texto()
        vazio = not texto.strip() and not ctx.imagens and not any(t.nota for t in ctx.trechos)

        # 1. o que não é bloco de texto
        if ctx.quebra_de_pagina and vazio:
            self._fechar_tudo()
            self._marcas_e_marcadores(ctx)
            self._emitir(QuebraDePagina())
            return None
        if vazio and not ctx.imagens:
            self._marcas_e_marcadores(ctx)
            bordas = ppr.find(_w("pBdr")) if ppr is not None else None
            if bordas is not None and bordas.find(_w("bottom")) is not None:
                self._fechar_tudo()
                self._emitir(Separador())
            return None
        # 2. imagens: figura ou diagrama em PNG
        if ctx.imagens:
            self._fechar_tudo()
            self._marcas_e_marcadores(ctx)
            for rid, descr, largura in ctx.imagens:
                self._imagem(rid, descr, largura, ppr)
            if texto.strip():
                self._emitir(Paragrafo(trechos=ctx.trechos))
            return ctx
        # 3. diagrama em fonte no corpo: parágrafos inteiros numa fonte de diagrama
        fonte = self._fonte_de_diagrama_do_paragrafo(ctx)
        if fonte and (nivel is None):
            self._fechar_exceto("diagrama")
            self._marcas_e_marcadores(ctx)
            self._linhas_de_diagrama.append((texto, fonte))
            return ctx
        self._fechar_diagrama_em_fonte()
        # 4. legenda
        if nome == "caption":
            self._legenda(ctx, texto)
            return ctx
        # 5. título
        if nivel is not None:
            self._fechar_tudo()
            self._marcas_e_marcadores(ctx)
            bloco = Titulo(trechos=ctx.trechos, nivel=min(max(nivel, 1), 6))
            self._formato(bloco, ppr)
            self._emitir(bloco)
            return ctx
        # 6. item de lista
        if numpr is not None:
            ilvl_el, numid_el = numpr.find(_w("ilvl")), numpr.find(_w("numId"))
            ilvl_val = ilvl_el.get(_w("val"), "0") if ilvl_el is not None else "0"
            ilvl = int(ilvl_val) if ilvl_val.isdigit() else 0
            num_id = numid_el.get(_w("val"), "") if numid_el is not None else ""
            if num_id and num_id != "0":
                self._fechar_exceto("lista")
                self._marcas_e_marcadores(ctx)
                par = Paragrafo(trechos=ctx.trechos)
                self._formato(par, ppr, ignorar_recuo=True)
                if self._itens and self._itens[-1][1] != num_id:
                    self._fechar_lista()
                self._itens.append((ilvl, num_id, [par]))
                return ctx
        if nome == "list paragraph" and self._itens and ppr is not None and ppr.find(_w("ind")) is not None:
            # continuação de item (parágrafo recuado, sem numPr, logo depois de um item)
            par = Paragrafo(trechos=ctx.trechos)
            self._itens[-1][2].append(par)
            return ctx
        # 7. citação
        if ESTILOS_DE_PARAGRAFO.get(nome) == "citacao":
            self._fechar_exceto("citacao")
            self._marcas_e_marcadores(ctx)
            par = Paragrafo(trechos=ctx.trechos, estilo="citacao")
            self._formato(par, ppr)
            self._citacao.append(par)
            return ctx
        # 8. parágrafo comum (ou estilo desconhecido)
        self._fechar_tudo()
        self._marcas_e_marcadores(ctx)
        estilo = ESTILOS_DE_PARAGRAFO.get(nome, "corpo")
        if estilo == "nota" and not self._em_nota:
            estilo = "corpo"
        if not nome and style_id and style_id not in self._estilos_avisados:
            self._estilos_avisados.add(style_id)
            self.relatorio.aviso(f"estilo de parágrafo sem tradução: {proprio or style_id!r} (lido como corpo)")
        par = Paragrafo(trechos=ctx.trechos, estilo=estilo)
        self._formato(par, ppr)
        self._emitir(par)
        return ctx

    def _marcas_e_marcadores(self, ctx: _Contexto) -> None:
        self._marcas_pendentes.extend(ctx.marcas_no_inicio)
        self._marcador_pendente.extend(ctx.marcadores)

    def _fonte_de_diagrama_do_paragrafo(self, ctx: _Contexto) -> str:
        familias = {t.familia for t in ctx.trechos if t.texto}
        if len(familias) != 1:
            return ""
        familia = next(iter(familias))
        if familia and familia != "simbolos" and (_RE_FONTE_DE_DIAGRAMA.search(familia) or _e_fonte_do_mapa(familia)):
            return familia
        return ""

    def _formato(self, bloco: Paragrafo, ppr: ET.Element | None, ignorar_recuo: bool = False) -> None:
        if ppr is None:
            return
        jc = ppr.find(_w("jc"))
        if jc is not None:
            bloco.alinhamento = {"left": "esquerda", "start": "esquerda", "center": "centro", "right": "direita",
                                 "end": "direita", "both": "justificado", "distribute": "justificado"}.get(
                jc.get(_w("val"), ""), "")
        ind = ppr.find(_w("ind"))
        if ind is not None and not ignorar_recuo:
            primeira = _twips_em(ind.get(_w("firstLine")))
            pendurado = _twips_em(ind.get(_w("hanging")))
            if primeira is not None:
                bloco.recuo_primeira_em = primeira
            elif pendurado is not None:
                bloco.recuo_primeira_em = -pendurado
            esquerda = _twips_em(ind.get(_w("left")) or ind.get(_w("start")))
            direita = _twips_em(ind.get(_w("right")) or ind.get(_w("end")))
            if esquerda is not None:
                bloco.recuo_esquerda_em = esquerda
            if direita is not None:
                bloco.recuo_direita_em = direita
        spacing = ppr.find(_w("spacing"))
        if spacing is not None:
            antes, depois = _twips_em(spacing.get(_w("before"))), _twips_em(spacing.get(_w("after")))
            if antes is not None:
                bloco.antes_em = antes
            if depois is not None:
                bloco.depois_em = depois
            linha = spacing.get(_w("line"))
            if linha and linha.isdigit() and spacing.get(_w("lineRule"), "auto") == "auto":
                bloco.entrelinha = round(int(linha) / 240, 3)
        if _prop(ppr, "keepNext"):
            bloco.manter_com_proximo = True
        if _prop(ppr, "keepLines"):
            bloco.manter_linhas = True

    # -- runs ----------------------------------------------------------------------

    def _runs(self, p: ET.Element, ctx: _Contexto, rels: dict) -> None:
        for el in p:
            tag = el.tag
            if tag == _w("pPr"):
                continue
            if tag == _w("r"):
                self._run(el, ctx, rels)
            elif tag == _w("hyperlink"):
                self._hyperlink(el, ctx, rels)
            elif tag == _w("bookmarkStart"):
                self._bookmark(el, ctx)
            elif tag == _w("fldSimple"):
                instr = el.get(_w("instr"), "")
                ctx.campo = [instr]
                self._runs(el, ctx, rels)
                self._fechar_campo(ctx)
            elif tag in (_w("ins"), _w("moveTo"), _w("smartTag"), _w("sdt"), _w("customXml")):
                self._aviso_unico("controle de alterações: as inserções foram aceitas") if tag == _w("ins") else None
                conteudo = el.find(_w("sdtContent")) if tag == _w("sdt") else el
                if conteudo is not None:
                    self._runs(conteudo, ctx, rels)
            elif tag in (_w("del"), _w("moveFrom")):
                self._aviso_unico("controle de alterações: as exclusões foram descartadas")
            elif tag in (_w("commentRangeStart"), _w("commentRangeEnd")):
                self._aviso_unico("comentários ignorados (§10.7)")
            elif tag in (_w("bookmarkEnd"), _w("proofErr")):
                continue
            elif tag.endswith("}AlternateContent"):
                self._alternate_inline(el, ctx)
            else:
                self._aviso_unico(f"elemento {tag.split('}')[-1]} no parágrafo sem tradução, ignorado")

    def _alternate_inline(self, el: ET.Element, ctx: _Contexto) -> None:
        textos: list[str] = []
        for p in el.iter(_w("p")):
            texto = "".join(t.text or "" for t in p.iter(_w("t")))
            if texto.strip():
                textos.append(texto)
        if textos:
            self._aviso_unico("caixa de texto: o texto foi preservado como parágrafo (§10.7)")
            for texto in textos:
                ctx.trechos.append(Trecho(texto=texto, quebra_antes=bool(ctx.trechos)))

    def _bookmark(self, el: ET.Element, ctx: _Contexto) -> None:
        nome = el.get(_w("name"), "")
        m = _RE_PAGINA.match(nome)
        if m:
            if ctx.texto() or ctx.trechos:
                ctx.pagina_pendente = int(m.group(1))
            else:
                ctx.marcas_no_inicio.append(int(m.group(1)))
        elif nome and nome != "_GoBack":
            ctx.marcadores.append(nome)

    def _hyperlink(self, el: ET.Element, ctx: _Contexto, rels: dict) -> None:
        rid = el.get(R + "id")
        ancora = el.get(_w("anchor"), "")
        antes = len(ctx.trechos)
        self._runs(el, ctx, rels)
        link = ""
        if rid:
            alvo = rels.get(rid)
            if alvo is not None:
                link = alvo[0]
        elif ancora:
            link = "#marcador:" + ancora
        for t in ctx.trechos[antes:]:
            if link and not t.nota:
                t.link = link

    def _fechar_campo(self, ctx: _Contexto) -> None:
        ctx.campo = None
        ctx.resultado_de_campo = False
        ctx.ref_pendente = None

    def _run(self, r: ET.Element, ctx: _Contexto, rels: dict) -> None:
        rpr = r.find(_w("rPr"))
        for el in r:
            tag = el.tag
            if tag == _w("rPr"):
                continue
            if tag == _w("fldChar"):
                tipo = el.get(_w("fldCharType"), "")
                if tipo == "begin":
                    ctx.campo = []
                    ctx.resultado_de_campo = False
                elif tipo == "separate":
                    ctx.resultado_de_campo = True
                    instr = " ".join(ctx.campo or []).strip()
                    m = _RE_REF.match(instr)
                    ctx.ref_pendente = (m.group(1), "") if m else None
                elif tipo == "end":
                    self._fechar_campo(ctx)
                continue
            if tag == _w("instrText"):
                if ctx.campo is not None:
                    ctx.campo.append(el.text or "")
                continue
            if ctx.campo is not None and not ctx.resultado_de_campo:
                continue                                    # entre begin e separate só há instrução
            if tag == _w("t"):
                texto = el.text or ""
                if not texto:
                    continue
                if ctx.campo is not None:
                    instr = " ".join(ctx.campo).strip()
                    if _RE_SEQ.match(instr) or ctx.ref_pendente is not None:
                        pass                                # o resultado em cache de SEQ/REF vale como texto
                    elif re.match(r"^\s*(PAGE|PAGEREF|TOC|STYLEREF|NUMPAGES)\b", instr):
                        continue                            # números de página e sumário não são conteúdo
                trecho = self._trecho(texto, rpr, ctx)
                if ctx.ref_pendente is not None:
                    self._refs.append((trecho, ctx.ref_pendente[0]))
                ctx.trechos.append(trecho)
            elif tag == _w("tab"):
                ctx.trechos.append(self._trecho("\t", rpr, ctx))
            elif tag == _w("br"):
                if el.get(_w("type"), "") == "page":
                    ctx.quebra_de_pagina = True
                else:
                    ctx.quebra_pendente = True
            elif tag == _w("noBreakHyphen"):
                ctx.trechos.append(self._trecho("‑", rpr, ctx))
            elif tag == _w("softHyphen"):
                ctx.trechos.append(self._trecho("­", rpr, ctx))
            elif tag == _w("sym"):
                self._aviso_unico("símbolo de fonte (w:sym) lido pelo código do caractere")
                codigo = el.get(_w("char"), "")
                try:
                    ctx.trechos.append(self._trecho(chr(int(codigo, 16)), rpr, ctx))
                except ValueError:
                    pass
            elif tag in (_w("footnoteReference"), _w("endnoteReference")):
                tipo = "rodape" if tag == _w("footnoteReference") else "fim"
                nota_id = self._nota(tipo, el.get(_w("id"), ""))
                if nota_id:
                    trecho = Trecho(nota=nota_id)
                    self._pendentes_no_trecho(trecho, ctx)
                    ctx.trechos.append(trecho)
            elif tag == _w("drawing"):
                self._drawing(el, ctx)
            elif tag == _w("pict") or tag == _w("object"):
                self._pict(el, ctx)
            elif tag in (_w("lastRenderedPageBreak"), _w("footnoteRef"), _w("endnoteRef"), _w("separator"),
                         _w("continuationSeparator"), _w("cr"), _w("commentReference"), _w("annotationRef")):
                if tag == _w("cr"):
                    ctx.quebra_pendente = True
                if tag == _w("commentReference"):
                    self._aviso_unico("comentários ignorados (§10.7)")
                continue
            elif tag.endswith("}AlternateContent"):
                self._alternate_inline(el, ctx)

    def _pendentes_no_trecho(self, trecho: Trecho, ctx: _Contexto) -> None:
        if ctx.pagina_pendente is not None:
            trecho.pagina = ctx.pagina_pendente
            ctx.pagina_pendente = None
        if ctx.quebra_pendente:
            trecho.quebra_antes = True
            ctx.quebra_pendente = False

    def _trecho(self, texto: str, rpr: ET.Element | None, ctx: _Contexto) -> Trecho:
        trecho = Trecho(texto=texto)
        self._pendentes_no_trecho(trecho, ctx)
        if rpr is None:
            return trecho
        estilo_el = rpr.find(_w("rStyle"))
        if estilo_el is not None:
            nome, proprio = self.p.nome_do_estilo(estilo_el.get(_w("val"), ""), ESTILOS_DE_CARACTERE)
            definicao = ESTILOS_DE_CARACTERE.get(nome, {})
            if definicao.get("papel"):
                trecho.papel = definicao["papel"]
            if definicao.get("familia"):
                trecho.familia = definicao["familia"]
            if definicao.get("versalete"):
                trecho.versalete = True
            if definicao.get("codigo"):
                trecho.codigo = True
            if definicao.get("negrito"):
                trecho.negrito = True
            if definicao.get("italico"):
                trecho.italico = True
            if definicao.get("ilha"):
                self._aviso_unico("texto no estilo Ilha voltou como texto: a ilha original não está no DOCX")
            if not nome and proprio and proprio not in self._estilos_avisados:
                self._estilos_avisados.add(proprio)
                self.relatorio.aviso(f"estilo de caractere sem tradução: {proprio!r} (ignorado)")
        if _prop(rpr, "b"):
            trecho.negrito = True
        if _prop(rpr, "i"):
            trecho.italico = True
        u = rpr.find(_w("u"))
        if u is not None and u.get(_w("val"), "single") != "none":
            trecho.sublinhado = True
        if _prop(rpr, "strike") or _prop(rpr, "dstrike"):
            trecho.tachado = True
        if _prop(rpr, "smallCaps"):
            trecho.versalete = True
        va = rpr.find(_w("vertAlign"))
        if va is not None:
            trecho.posicao = {"superscript": "sobre", "subscript": "sub"}.get(va.get(_w("val"), ""), "")
        sz = rpr.find(_w("sz"))
        if sz is not None and sz.get(_w("val"), "").isdigit():
            trecho.corpo_pt = int(sz.get(_w("val"))) / 2.0
        cor = rpr.find(_w("color"))
        if cor is not None:
            trecho.cor = _cor(cor.get(_w("val")))
        shd = rpr.find(_w("shd"))
        if shd is not None:
            trecho.fundo = _cor(shd.get(_w("fill")))
        realce = rpr.find(_w("highlight"))
        if realce is not None and not trecho.fundo:
            trecho.fundo = CORES_DE_REALCE.get(realce.get(_w("val"), ""), "")
        if trecho.fundo and trecho.cor == "#ffffff":
            trecho.cor = ""             # o branco sobre fundo escuro é da escrita, não do trecho
        lang = rpr.find(_w("lang"))
        if lang is not None and lang.get(_w("val")):
            trecho.lang = lang.get(_w("val"))
        fontes = rpr.find(_w("rFonts"))
        if fontes is not None:
            familia = fontes.get(_w("ascii")) or fontes.get(_w("hAnsi")) or ""
            if familia:
                self._familia(trecho, familia)
        return trecho

    def _familia(self, trecho: Trecho, familia: str) -> None:
        baixa = familia.strip().lower()
        if baixa in FONTES_MONOESPACADAS:
            trecho.codigo = True
        elif baixa in FONTES_DE_SIMBOLOS:
            trecho.familia = "simbolos"
        elif _RE_FONTE_DE_DIAGRAMA.search(familia) or _e_fonte_do_mapa(familia):
            trecho.familia = familia
        elif baixa in ("symbol", "wingdings"):
            pass
        else:
            trecho.familia = familia.strip() if not trecho.familia else trecho.familia

    # -- notas ------------------------------------------------------------------

    def _nota(self, tipo: str, id_: str) -> str:
        el = self.p.notas[tipo].get(id_)
        if el is None:
            self._aviso_unico(f"referência a nota de {tipo} que não está no pacote (id {id_})")
            return ""
        leitor = _Leitor(self.p, self.relatorio)
        leitor._em_nota = True
        leitor._rels_atuais = self.p.rels_das_notas[tipo]
        leitor.recursos = self.recursos
        leitor._imagens_por_rid = self._imagens_por_rid
        for filho in el:
            if filho.tag == _w("p"):
                leitor._paragrafo_de_nota(filho, self.p.rels_das_notas[tipo])
        leitor._fechar_tudo()
        blocos = [b for b in leitor.blocos if isinstance(b, Paragrafo)]
        for b in blocos:
            b.estilo = "nota"
        nota = Nota(tipo=tipo, blocos=blocos or [Paragrafo(trechos=[Trecho(texto="")], estilo="nota")])
        self.notas.append(nota)
        return nota.id

    def _paragrafo_de_nota(self, p: ET.Element, rels: dict) -> None:
        ctx = _Contexto()
        self._runs(p, ctx, rels)
        # o primeiro run é o `footnoteRef` (o número) e um espaço: fora
        trechos = ctx.trechos
        while trechos and trechos[0].texto in (" ", "\t") and not trechos[0].nota:
            trechos.pop(0)
        if trechos and trechos[0].texto:
            trechos[0].texto = trechos[0].texto.lstrip(" \t") or trechos[0].texto
        if not any(t.texto.strip() or t.nota for t in trechos):
            return
        par = Paragrafo(trechos=trechos, estilo="nota")
        self.blocos.append(par)

    # -- legenda, imagens, tabelas, diagramas ------------------------------------------

    def _legenda(self, ctx: _Contexto, texto: str) -> None:
        m = _RE_LEGENDA.match(texto.strip())
        marcadores = list(ctx.marcadores)
        if not m:
            # uma legenda solta vira parágrafo no estilo legenda
            self._fechar_tudo()
            self._marcas_e_marcadores(ctx)
            par = Paragrafo(trechos=ctx.trechos, estilo="legenda")
            self._emitir(par)
            return
        tipo = {"tabela": "tabela", "table": "tabela", "figura": "figura", "figure": "figura",
                "diagrama": "diagrama", "diagram": "diagrama"}[m.group(1).lower()]
        numero = int(m.group(2))
        # os trechos da legenda: o que vem depois de ": "
        legenda = _depois_dos_dois_pontos(ctx.trechos)
        self._marcas_pendentes.extend(ctx.marcas_no_inicio)
        if tipo == "tabela":
            self._fechar_tudo()
            self._legenda_pendente = (tipo, numero, legenda, marcadores)
            return
        alvo = self._ultimo_objeto(tipo)
        if alvo is None:
            self._fechar_tudo()
            self._marcador_pendente.extend(marcadores)
            self._emitir(Paragrafo(trechos=ctx.trechos, estilo="legenda"))
            return
        alvo.numero = numero
        alvo.legenda = legenda
        for nome in marcadores:
            self._marcadores[nome] = alvo.id
            alvo.id_persistente = True

    def _ultimo_objeto(self, tipo: str) -> Any:
        classe = {"figura": Figura, "diagrama": Diagrama, "tabela": Tabela}[tipo]
        for bloco in reversed(self.blocos):
            if isinstance(bloco, classe):
                return bloco if bloco.legenda == [] and bloco.numero is None else None
            if isinstance(bloco, (Paragrafo, Lista, Citacao)):
                return None
        return None

    def _imagem(self, rid: str, descr: str, largura: float | None, ppr: ET.Element | None) -> None:
        if modelo.fen_valido(descr.strip()):
            self._contadores["diagrama"] += 1
            self._emitir(Diagrama(fen=_fen(descr), lado="", modo="png"))
            return
        midia = self.p.midia(rid, self._rels_atuais)
        if midia is None and self._rels_atuais is not self.p.rels:
            midia = self.p.midia(rid)
        if midia is None:
            self.relatorio.aviso(f"imagem {rid} não está no pacote; figura saiu sem imagem")
            self._emitir(Paragrafo(trechos=[Trecho(texto=f"[imagem ausente: {descr or rid}]")]))
            return
        href = self._imagens_por_rid.get(rid)
        if href is None:
            nome, dados = midia
            href = "Images/" + nome
            n = 1
            while href in self.recursos and self.recursos[href].dados != dados:
                n += 1
                raiz, ext = posixpath.splitext(nome)
                href = f"Images/{raiz}-{n}{ext}"
            self.recursos[href] = Recurso(caminho=href, tipo_mime=epub.tipo_mime_de(href), dados=dados)
            self._imagens_por_rid[rid] = href
        alinhamento = "centro"
        jc = ppr.find(_w("jc")) if ppr is not None else None
        if jc is not None:
            alinhamento = {"left": "esq", "start": "esq", "right": "dir", "end": "dir"}.get(jc.get(_w("val"), ""),
                                                                                              "centro")
        self._contadores["figura"] += 1
        self._emitir(Figura(recurso=href, alt=descr, largura_pt=largura, alinhamento=alinhamento))

    def _drawing(self, el: ET.Element, ctx: _Contexto) -> None:
        docpr = el.find(".//" + WP + "docPr")
        descr = docpr.get("descr", "") if docpr is not None else ""
        blip = el.find(".//" + A + "blip")
        rid = blip.get(R + "embed", "") if blip is not None else ""
        largura = None
        extent = el.find(".//" + WP + "extent")
        if extent is not None and extent.get("cx", "").isdigit():
            largura = round(int(extent.get("cx")) / 12700.0, 2)
        if rid:
            ctx.imagens.append((rid, descr, largura))
        elif el.find(".//" + WP + "txbxContent") is not None or el.find(".//" + _w("txbxContent")) is not None:
            self._alternate_inline(el, ctx)
        else:
            self._aviso_unico("desenho sem imagem (forma) ignorado (§10.7)")

    def _pict(self, el: ET.Element, ctx: _Contexto) -> None:
        imagedata = el.find(".//{%s}imagedata" % NS["v"])
        if imagedata is not None and imagedata.get(R + "id"):
            ctx.imagens.append((imagedata.get(R + "id"), imagedata.get("title", "") or "", None))
            return
        if el.find(".//" + _w("txbxContent")) is not None:
            self._alternate_inline(el, ctx)
            return
        self._aviso_unico("forma (VML) ignorada (§10.7)")

    def _tabela(self, tbl: ET.Element) -> None:
        tblpr = tbl.find(_w("tblPr"))
        filas_xml = tbl.findall(_w("tr"))
        legenda_pendente, self._legenda_pendente = self._legenda_pendente, None
        # o diagrama em fonte: uma célula, e a legenda "Diagrama"
        caption = tblpr.find(_w("tblCaption")) if tblpr is not None else None
        descricao = tblpr.find(_w("tblDescription")) if tblpr is not None else None
        if len(filas_xml) == 1 and len(filas_xml[0].findall(_w("tc"))) == 1:
            celula = filas_xml[0].find(_w("tc"))
            paragrafos = celula.findall(_w("p"))
            linhas: list[str] = []
            fonte = ""
            for p in paragrafos:
                ctx = _Contexto()
                self._runs(p, ctx, self.p.rels)
                linhas.append(ctx.texto())
                fonte = fonte or self._fonte_de_diagrama_do_paragrafo(ctx)
            e_diagrama = (caption is not None and caption.get(_w("val"), "") == "Diagrama") or bool(fonte)
            if e_diagrama and len(linhas) in (8, 10):
                descr = descricao.get(_w("val"), "") if descricao is not None else ""
                diagrama = self._diagrama_das_linhas(linhas, fonte or modelo.FONTE_PADRAO, descr)
                if diagrama is not None:
                    moldura = "simples"
                    tcpr = celula.find(_w("tcPr"))
                    bordas = tcpr.find(_w("tcBorders")) if tcpr is not None else None
                    if bordas is not None:
                        topo = bordas.find(_w("top"))
                        val = topo.get(_w("val"), "single") if topo is not None else "single"
                        moldura = {"nil": "sem", "none": "sem", "double": "dupla"}.get(val, "simples")
                    diagrama.moldura = moldura if len(linhas) == 8 else "simples"
                    self._marcas_e_marcadores_de_legenda(legenda_pendente)
                    self._emitir(diagrama)
                    return
        tabela = self._tabela_comum(tbl, filas_xml, tblpr)
        if legenda_pendente is not None:
            _tipo, numero, legenda, marcadores = legenda_pendente
            tabela.numero = numero
            tabela.legenda = legenda
            for nome in marcadores:
                self._marcadores[nome] = tabela.id
                tabela.id_persistente = True
        self._emitir(tabela)

    def _marcas_e_marcadores_de_legenda(self, legenda_pendente: Any) -> None:
        if legenda_pendente is not None:
            self._marcador_pendente.extend(legenda_pendente[3])

    def _diagrama_das_linhas(self, linhas: Sequence[str], fonte: str, descr: str) -> Diagrama | None:
        from core import render_diagrama

        linhas = [li.rstrip("\n") for li in linhas]
        try:
            posicao, orientacao = render_diagrama.fen_de_linhas(linhas, fonte)
        except (ValueError, render_diagrama.FonteDesconhecida, KeyError) as erro:
            self.relatorio.aviso(f"tabuleiro em texto na fonte {fonte} não decodificado ({erro}); ficou como texto")
            return None
        emolduradas = len(linhas) == 10
        estado, aviso = "ok", ""
        if modelo.fen_valido(descr.strip()):
            fen = _fen(descr)
            mapa = render_diagrama.mapa_da_fonte(fonte)
            miolo = [linha[1:9] for linha in linhas[1:9]] if emolduradas else list(linhas)
            reproduz = next((o for o in ("branca", "preta") if render_diagrama.linhas(fen, mapa, o) == miolo), None)
            if reproduz is not None:
                orientacao = reproduz
            elif orientacao is None:
                orientacao, estado, aviso = "branca", "revisar", "as linhas não batem com a descrição da tabela"
        else:
            if orientacao is None:
                orientacao, estado, aviso = "branca", "revisar", "orientação não registrada"
            fen = modelo.fen_completo(posicao)
        self._contadores["diagrama"] += 1
        return Diagrama(fen=fen, lado="", orientacao=orientacao, coordenadas=emolduradas, fonte=fonte, modo="fonte",
                        estado=estado, aviso=aviso)

    def _tabela_comum(self, tbl: ET.Element, filas_xml: list[ET.Element], tblpr: ET.Element | None) -> Tabela:
        filas: list[list[Celula]] = []
        cabecalho = False
        for i, tr in enumerate(filas_xml):
            trpr = tr.find(_w("trPr"))
            if i == 0 and trpr is not None and trpr.find(_w("tblHeader")) is not None:
                cabecalho = True
            fila: list[Celula] = []
            for tc in tr.findall(_w("tc")):
                blocos: list[Paragrafo] = []
                alinhamento = ""
                for p in tc.findall(_w("p")):
                    ctx = _Contexto()
                    self._runs(p, ctx, self.p.rels)
                    par = Paragrafo(trechos=ctx.trechos)
                    ppr = self._ppr(p)
                    self._formato(par, ppr, ignorar_recuo=True)
                    nome, _proprio = self.p.nome_do_estilo(self._style_id(ppr), ESTILOS_DE_PARAGRAFO)
                    par.estilo = ESTILOS_DE_PARAGRAFO.get(nome, "corpo")
                    if par.estilo == "nota":
                        par.estilo = "corpo"
                    if par.alinhamento and par.alinhamento != "esquerda":
                        alinhamento = alinhamento or par.alinhamento
                    par.alinhamento = ""
                    blocos.append(par)
                gridspan = tc.find(_w("tcPr") + "/" + _w("gridSpan"))
                celula_cab = cabecalho and i == 0
                if blocos and celula_cab and all(t.negrito for b in blocos for t in b.trechos if t.texto.strip()):
                    for b in blocos:
                        for t in b.trechos:
                            t.negrito = False
                fila.append(Celula(blocos=blocos, cabecalho=celula_cab, alinhamento=alinhamento))
                if gridspan is not None and gridspan.get(_w("val"), "1").isdigit():
                    for _ in range(int(gridspan.get(_w("val"))) - 1):
                        fila.append(Celula(blocos=[]))
                    self._aviso_unico("célula mesclada horizontalmente lida como células vazias ao lado")
            filas.append(fila)
        largura = max((len(f) for f in filas), default=0)
        for fila in filas:
            while len(fila) < largura:
                fila.append(Celula(blocos=[]))
        largura_pct = None
        tblw = tblpr.find(_w("tblW")) if tblpr is not None else None
        if tblw is not None and tblw.get(_w("type"), "") == "pct" and tblw.get(_w("w"), "").isdigit():
            largura_pct = int(round(int(tblw.get(_w("w"))) / 50.0))
        self._contadores["tabela"] += 1
        return Tabela(filas=filas, primeira_fila_cabecalho=cabecalho, largura_pct=largura_pct)

    # -- marcadores e referências --------------------------------------------------

    def _resolver_marcadores(self) -> None:
        """`#marcador:<nome>` → `#<id>`; `REF` → `ref` com o tipo do alvo; alvo ausente vira aviso."""
        por_id = {b.id: b for b in modelo.blocos_do_capitulo(Capitulo(arquivo="x.xhtml", blocos=self.blocos))}
        for trecho in [t for b in self.blocos for t in modelo._todos_os_trechos(b)] + \
                [t for n in self.notas for b in n.blocos for t in b.trechos]:
            if trecho.link.startswith("#marcador:"):
                nome = trecho.link[len("#marcador:"):]
                alvo = self._marcadores.get(nome)
                if alvo is None:
                    self._aviso_unico(f"hiperlink para o marcador {nome!r} sem alvo no documento; ficou como texto")
                    trecho.link = ""
                else:
                    trecho.link = "#" + alvo
        for trecho, nome in self._refs:
            alvo = self._marcadores.get(nome)
            if alvo is None:
                continue
            bloco = por_id.get(alvo)
            tipo = {Tabela: "tabela", Figura: "figura", Diagrama: "diagrama", Titulo: "titulo"}.get(type(bloco), "")
            if tipo:
                trecho.ref = tipo
                trecho.link = "#" + alvo
                bloco.id_persistente = True

    def _avisar_partes_ignoradas(self) -> None:
        if any(n.startswith("word/header") or n.startswith("word/footer") for n in self.p.partes):
            com_texto = False
            for nome, dados in self.p.partes.items():
                if nome.startswith(("word/header", "word/footer")) and b"<w:t" in dados:
                    com_texto = True
            if com_texto:
                self.relatorio.aviso("cabeçalho/rodapé ignorados (o livro os regenera; §10.7)")
        if "word/comments.xml" in self.p.partes:
            self._aviso_unico("comentários ignorados (§10.7)")


def _e_fonte_do_mapa(familia: str) -> bool:
    from core.editor import fontes

    return fontes.arquivo_da_fonte_de_diagrama(familia) is not None or familia in fontes._mapas()


def _depois_dos_dois_pontos(trechos: Sequence[Trecho]) -> list[Trecho]:
    """Os trechos de "Tabela 1: Resultados" depois do ": " — a legenda propriamente dita."""
    texto = "".join(t.texto for t in trechos)
    m = re.search(r":\s*", texto)
    if not m:
        return []
    corte = m.end()
    saida: list[Trecho] = []
    pos = 0
    for t in trechos:
        fim = pos + len(t.texto)
        if fim <= corte:
            pos = fim
            continue
        inicio = max(corte - pos, 0)
        saida.append(replace(t, texto=t.texto[inicio:], ref="", link=""))
        pos = fim
    return saida


# ----------------------------------------------------------------------
# A porta
# ----------------------------------------------------------------------

def ler(caminho: str, dividir_por_titulo: bool = True, nivel: int = 1) -> tuple[Livro, RelatorioDeConversao]:
    """Um DOCX → `Livro` (§10.4): um capítulo por `Heading 1` quando `dividir_por_titulo`. Ver o cabeçalho."""
    caminho = os.fspath(caminho)
    relatorio = RelatorioDeConversao(formato="docx", arquivos=[caminho])
    with Cronometro(relatorio):
        pacote = _Pacote(caminho, relatorio)
        leitor = _Leitor(pacote, relatorio)
        leitor.corpo()
        metadados = pacote.metadados()
        nome = os.path.splitext(os.path.basename(caminho))[0]
        primeiro_titulo = next((modelo.texto_de(b) for b in leitor.blocos if isinstance(b, Titulo) and b.nivel == 1),
                               "")
        metadados.titulo = metadados.titulo or primeiro_titulo or nome
        metadados.idioma = metadados.idioma or "und"
        livro = epub.novo_livro(metadados.titulo, metadados.autores[0].nome if metadados.autores else "",
                                metadados.idioma, ncx=True)
        metadados.identificador = livro.metadados.identificador
        livro.metadados = metadados
        padrao = livro.folhas[0]
        cap = Capitulo(arquivo="Text/cap-0001.xhtml", blocos=leitor.blocos, notas=leitor.notas, folhas=[padrao])
        cap.normalizar_notas()
        livro.capitulos = [cap]
        livro.recursos.update(leitor.recursos)
        livro.pagina = pacote.pagina()
        if dividir_por_titulo:
            livro_ops.dividir_por_titulo(livro, cap.arquivo, nivel)
            livro_ops.renomear_varios(livro, "cap-%04d")
        livro.sumario = sumario.gerar_dos_titulos(livro)
        livro.marcos = [("bodymatter", livro.capitulos[0].arquivo)]
    relatorio.contar(livro)
    return livro, relatorio


__all__ = ["ler", "ESTILOS_DE_PARAGRAFO", "ESTILOS_DE_CARACTERE", "CORES_DE_REALCE"]
