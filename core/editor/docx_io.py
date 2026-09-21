"""
O livro do editor em DOCX: `escrever(livro, caminho, opcoes) -> RelatorioDeConversao`
(ED-09; SPEC_EDITOR §6.2, §6.3, §10.3, §10.7, §10.8, DEC-12).

## O que sai, e de onde

Cada bloco do modelo (§5) vira o que a §10.3 manda: parágrafo com o estilo nomeado da
§6.3 (nomes do Word — `Heading 1`, `Caption`, `Quote`, `footnote text` —, para o
Word reconhecer os seus e não duplicar), lista pelo `numbering.xml` (um `abstractNum`
por lista, com `w:lvlText` e `w:ind` por nível e `startOverride`), tabela `Table Grid`
com `tblHeader` e legenda `Caption` com `SEQ`, figura e diagrama em imagem por
`add_picture` com o texto alternativo no `docPr/@descr`, diagrama em fonte na tabela
1×1 de `exportar._caixa_do_diagrama` (com a fonte embutida por
`_embutir_fontes_no_docx`), nota de rodapé e de fim **reais** (as sete costuras:
`footnotes.xml`/`endnotes.xml` com as separadoras `-1` e `0`, `w:footnotePr` em
`settings.xml`, o `Override` do `[Content_Types].xml`, o relacionamento, os estilos e o
`w:footnoteReference` no corpo), referência cruzada por `REF _Ref<n> \\h` com o marcador
só em torno de "Tabela n", sumário pré-renderizado num `w:sdt` (`TOC \\o "1-3"`, uma
entrada por título com `w:hyperlink` para `_Toc<n>` e `PAGEREF`) mais `w:updateFields`
para o Word refazer os números ao abrir, cabeçalhos par e ímpar
(`w:evenAndOddHeaders`: par = título do livro, ímpar = `STYLEREF "Heading 1"`), rodapé
`PAGE`, página e margens de `Livro.pagina` com `w:mirrorMargins`, e `w:autoHyphenation`
quando o formato de página pede.

## O que fica no relatório, e não em silêncio

O DOCX não tem onde guardar `classe` livre, `epub:type`, `origem` nem CSS fora da
mínima (§10.7): tudo isso sai do modelo sem aviso, porque não muda o que se lê. O que
muda vira aviso no `RelatorioDeConversao`: a ilha (fora do dialeto), que sai como
texto no estilo `Ilha`; o diagrama em fonte com coordenadas numa fonte sem moldura em
glifo, que **cai para PNG** — no Word não há como alinhar rótulo de outra fonte sobre
as casas; o SVG, que é rasterizado; a nota que aponta para um id que não existe; a
imagem que não está no livro.

## Por que tudo é importado dentro de `escrever`

`python-docx` é dependência opcional (DEC-07): sem ela, `escrever` levanta
`RuntimeError` com a instrução de instalação (AC-ED09-3), e o resto do editor abre
sem ela. `core.exportar` e `core.render_diagrama` trazem `fitz` e `PIL`; ficam atrás
da mesma porta. As páginas do zip que o `python-docx` não expõe (notas, campos,
marcadores, sombreado, idioma, numeração) são escritas no XML dele, na ordem que o
esquema exige — a ordem errada é o que faz o Word dizer "arquivo corrompido".
"""

from __future__ import annotations

import html
import io
import os
import posixpath
import re
import tempfile
from typing import Any, Sequence

from core.editor import dialeto, epub, modelo, xhtml
from core.editor.conversao import Cronometro, OpcoesDeConversao, RelatorioDeConversao
from core.editor.modelo import (Bloco, Capitulo, Citacao, Diagrama, Figura, IlhaBruta, Lista, Livro,
                                MarcaDePagina, Nota, Paragrafo, QuebraDePagina, Separador, Tabela, Titulo, Trecho)
from core.editor.xhtml import ErroDeXhtml
from core.estilo_do_livro import PISO_DO_SIMBOLO, corpo_valido

INSTRUCAO_DE_INSTALACAO = ("python-docx não está instalado — instale com:\n"
                           "    .venv/Scripts/python.exe -m pip install python-docx")
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT_FOOTNOTES = "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"
CT_ENDNOTES = "application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml"
#: A ordem dos filhos de `CT_Settings` (ECMA-376 §17.15.1.78) — os que este módulo toca e os vizinhos.
ORDEM_DOS_SETTINGS = (
    "writeProtection", "view", "zoom", "removePersonalInformation", "removeDateAndTime",
    "doNotDisplayPageBoundaries", "displayBackgroundShape", "printPostScriptOverText",
    "printFractionalCharacterWidth", "printFormsData", "embedTrueTypeFonts", "embedSystemFonts",
    "saveSubsetFonts", "saveFormsData", "mirrorMargins", "alignBordersAndEdges", "bordersDoNotSurroundHeader",
    "bordersDoNotSurroundFooter", "gutterAtTop", "hideSpellingErrors", "hideGrammaticalErrors",
    "activeWritingStyle", "proofState", "formsDesign", "attachedTemplate", "linkStyles", "stylePaneFormatFilter",
    "stylePaneSortMethod", "documentType", "mailMerge", "revisionView", "trackRevisions", "doNotTrackMoves",
    "doNotTrackFormatting", "documentProtection", "autoFormatOverride", "styleLockTheme", "styleLockQFSet",
    "defaultTabStop", "autoHyphenation", "consecutiveHyphenLimit", "hyphenationZone", "doNotHyphenateCaps",
    "showEnvelope", "summaryLength", "clickAndTypeStyle", "defaultTableStyle", "evenAndOddHeaders",
    "bookFoldRevPrinting", "bookFoldPrinting", "bookFoldPrintingSheets", "drawingGridHorizontalSpacing",
    "drawingGridVerticalSpacing", "displayHorizontalDrawingGridEvery", "displayVerticalDrawingGridEvery",
    "doNotUseMarginsForDrawingGridOrigin", "drawingGridHorizontalOrigin", "drawingGridVerticalOrigin",
    "doNotShadeFormData", "noPunctuationKerning", "characterSpacingControl", "printTwoOnOne", "strictFirstAndLastChars",
    "noLineBreaksAfter", "noLineBreaksBefore", "savePreviewPicture", "doNotValidateAgainstSchema",
    "saveInvalidXml", "ignoreMixedContent", "alwaysShowPlaceholderText", "doNotDemarcateInvalidXml",
    "saveXmlDataOnly", "useXSLTWhenSaving", "saveThroughXslt", "showXMLTags", "alwaysMergeEmptyNamespace",
    "updateFields", "hdrShapeDefaults", "footnotePr", "endnotePr", "compat", "docVars", "rsids", "mathPr",
    "attachedSchema", "themeFontLang", "clrSchemeMapping", "doNotIncludeSubdocsInStats",
    "doNotAutoCompressPictures", "forceUpgrade", "captions", "readModeInkLockDown", "smartTagType",
    "schemaLibrary", "shapeDefaults", "doNotEmbedSmartTags", "decimalSymbol", "listSeparator",
)
#: marcador do modelo → (w:numFmt, w:lvlText com `%n`, fonte do glifo)
MARCADORES = {
    "disco": ("bullet", "", "Symbol"),
    "circulo": ("bullet", "o", "Courier New"),
    "quadrado": ("bullet", "", "Wingdings"),
    "decimal": ("decimal", "%n.", None),
    "alfa": ("lowerLetter", "%n)", None),
    "romano": ("lowerRoman", "%n.", None),
}
MARCADOR_SEM_ORDEM = ("disco", "circulo", "quadrado")
#: Estilos de parágrafo que este módulo cria (nome do Word → como se define).
ESTILOS_DE_CARACTERE = {
    "Lance": {"noProof": True}, "NAG": {"noProof": True}, "Figurina": {"simbolos": True},
    "Simbolo": {"simbolos": True}, "Versalete": {"smallCaps": True}, "Jogador": {"bold": True},
    "Abertura": {"italic": True}, "Comentario (caractere)": {"italic": True},
    "Ilha": {"shd": "EEEEEE", "cor": "555555"},
    "Hyperlink": {"cor": "0563C1", "underline": True, "builtin": True},
    "footnote reference": {"vertAlign": "superscript", "styleId": "FootnoteReference", "builtin": True},
    "endnote reference": {"vertAlign": "superscript", "styleId": "EndnoteReference", "builtin": True},
}
ESTILO_DE_CARACTERE_DO_PAPEL = {"lance": "Lance", "nag": "NAG", "figurina": "Figurina",
                                "comentario": "Comentario (caractere)", "jogador": "Jogador", "abertura": "Abertura"}
ROTULOS = {"tabela": "Tabela", "figura": "Figura", "diagrama": "Diagrama"}
FONTE_MONOESPACADA = "Consolas"
#: A caixa do diagrama em fonte é `corpo × colunas` mais isto: com a largura exata, o Word 16
#: (16.0.14334) dobra o oitavo glifo para a linha seguinte — medido com 0,5 pt (dobra) e 1 pt (não).
FOLGA_DA_CAIXA_PT = 1.5
_RE_TAG = re.compile(r"<[^>]*>")
_RE_NOME_DE_MARCADOR = re.compile(r"[^A-Za-z0-9_]")


# ----------------------------------------------------------------------
# A porta
# ----------------------------------------------------------------------

def _importar_docx() -> Any:
    try:
        import docx
    except ImportError as erro:
        raise RuntimeError(INSTRUCAO_DE_INSTALACAO) from erro
    return docx


def escrever(livro: Livro, caminho: str, opcoes: OpcoesDeConversao | None = None) -> RelatorioDeConversao:
    """
    Escreve `livro` em `caminho` (.docx) com as `opcoes` (`modo_de_diagrama`, `notas`,
    `sumario`, `idioma`; a hifenização e a página vêm de `Livro.pagina`). Devolve o
    relatório com as contagens do que **saiu** e os avisos (§10.8). A gravação é num
    temporário ao lado, trocado por `os.replace` só no fim — uma falha não destrói um
    DOCX que já existia.
    """
    opcoes = opcoes or OpcoesDeConversao()
    caminho = os.fspath(caminho)
    relatorio = RelatorioDeConversao("docx", arquivos=[caminho])
    with Cronometro(relatorio):
        docx = _importar_docx()
        escritor = _Escritor(livro, opcoes, relatorio, docx)
        escritor.montar()
        escritor.gravar(caminho)
    return relatorio


# ----------------------------------------------------------------------
# XML miúdo
# ----------------------------------------------------------------------

def _qn(tag: str) -> str:
    from docx.oxml.ns import qn

    return qn(tag)


def _el(tag: str, **atributos: str) -> Any:
    from docx.oxml import OxmlElement

    elemento = OxmlElement(tag)
    for chave, valor in atributos.items():
        elemento.set(_qn(chave), str(valor))
    return elemento


def _por_na_ordem(pai: Any, filho: Any, ordem: Sequence[str]) -> None:
    """Insere `filho` em `pai` respeitando `ordem` (nomes locais): antes do primeiro que vem depois dele."""
    nome = filho.tag.split("}")[-1]
    posicao = ordem.index(nome) if nome in ordem else len(ordem)
    for existente in list(pai):
        local = existente.tag.split("}")[-1]
        if local in ordem and ordem.index(local) > posicao:
            existente.addprevious(filho)
            return
    pai.append(filho)


def _style_id(nome: str) -> str:
    """`w:styleId` só com letras e dígitos: "Comentario (caractere)" → `ComentarioCaractere`."""
    partes = re.split(r"[^A-Za-z0-9]+", nome)
    return "".join(p[:1].upper() + p[1:] for p in partes if p) or "Estilo"


def _texto_da_ilha(xhtml_cru: str) -> str:
    return html.unescape(_RE_TAG.sub("", xhtml_cru)).strip()


def _nome_de_marcador(base: str, limite: int = 40) -> str:
    nome = _RE_NOME_DE_MARCADOR.sub("_", base)
    if not nome or not (nome[0].isalpha() or nome[0] == "_"):
        nome = "b_" + nome
    return nome[:limite]


def _escuro(cor_hex: str) -> bool:
    """Luminância abaixo da metade: o texto sobre ela sai branco (§10.3 "realce")."""
    cor = cor_hex.lstrip("#")
    if len(cor) == 3:
        cor = "".join(c * 2 for c in cor)
    try:
        r, g, b = int(cor[0:2], 16), int(cor[2:4], 16), int(cor[4:6], 16)
    except ValueError:
        return False
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0 < 0.5


def _hex(cor: str) -> str | None:
    cor = cor.strip().lstrip("#")
    if len(cor) == 3:
        cor = "".join(c * 2 for c in cor)
    if re.fullmatch(r"[0-9A-Fa-f]{6}", cor):
        return cor.upper()
    return None


# ----------------------------------------------------------------------
# O escritor
# ----------------------------------------------------------------------

class _Escritor:
    def __init__(self, livro: Livro, opcoes: OpcoesDeConversao, relatorio: RelatorioDeConversao, docx: Any):
        from docx import Document

        self.livro = livro
        self.opcoes = opcoes
        self.relatorio = relatorio
        self.docx = docx
        self.doc = Document()
        self.idioma = opcoes.idioma or livro.metadados.idioma or "pt"
        self._marcadores = 0
        self._toc: list[tuple[int, str, str]] = []
        self._refs: dict[str, str] = {}
        self._alvos: dict[str, str] = {}
        self._notas: dict[str, list[Any]] = {"rodape": [], "fim": []}
        self._partes_de_notas: dict[str, Any] = {}
        self._fontes: dict[str, str] = {}
        self._simbolos: tuple[str, str, str] | None = None
        self._numeros = {"tabela": 0, "figura": 0, "diagrama": 0}
        self._paginas_pendentes: list[int] = []
        self._marcador_pendente: list[str] = []
        self._num_ids: list[int] = []
        self._tem_campos = False
        self._contagem = {"png": 0, "fonte": 0}
        self._capitulo_atual: Capitulo | None = None
        self._indice_do_capitulo = 0
        self._chaves_dos_capitulos: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def montar(self) -> None:
        from core import exportar

        livro = self.livro
        capitulos = [self._capitulo_em_modelo(c) for c in livro.capitulos]
        capitulos = [c for c in capitulos if c is not None]
        self._chaves_dos_capitulos = {c.arquivo: k for k, c in enumerate(capitulos)}
        self._simbolos = self._fonte_dos_simbolos(capitulos)
        self._preparar_referencias(capitulos)
        md = livro.metadados
        autor = md.autores[0].nome if md.autores else ""
        exportar._propriedades_do_docx(self.doc, md.titulo, autor)
        self.doc.core_properties.language = self.idioma
        exportar._desenho_da_pagina(self.doc)
        self._estilos()
        self._pagina()
        self._cabecalhos()
        for capitulo in capitulos:
            self._capitulo(capitulo)
        self._fechar_paginas_pendentes()
        if self.opcoes.sumario and self._toc:
            self._sumario()
        self._notas_no_pacote()
        self._settings()
        self.relatorio.contar(livro)
        self.relatorio.diagramas_png = self._contagem["png"]
        self.relatorio.diagramas_fonte = self._contagem["fonte"]
        self.relatorio.fontes_embutidas = sorted(self._fontes)

    def gravar(self, caminho: str) -> None:
        from core import exportar

        pasta = os.path.dirname(os.path.abspath(caminho))
        os.makedirs(pasta, exist_ok=True)
        fd, temporario = tempfile.mkstemp(prefix=".docx-", suffix=".tmp", dir=pasta)
        os.close(fd)
        try:
            self.doc.save(temporario)
            if self._fontes:
                exportar._embutir_fontes_no_docx(temporario, dict(self._fontes))
            self.docx.Document(temporario)          # reabrir confere o pacote antes de publicá-lo
            os.replace(temporario, caminho)
        except Exception:
            try:
                os.unlink(temporario)
            except OSError:
                pass
            raise

    def _capitulo_em_modelo(self, cap: Capitulo) -> Capitulo | None:
        """Um capítulo em código (`texto_cru`) passa pelo `xhtml.ler`; mal-formado vira aviso."""
        if cap.texto_cru is None:
            return cap
        try:
            lido = xhtml.ler(cap.texto_cru, cap.arquivo)
        except ErroDeXhtml as erro:
            self.relatorio.aviso(f"{cap.arquivo}: XHTML mal-formado, capítulo não exportado ({erro})")
            return None
        lido.titulo = lido.titulo or cap.titulo
        return lido

    def _fonte_dos_simbolos(self, capitulos: Sequence[Capitulo]) -> tuple[str, str, str] | None:
        texto = "".join(t.texto for c in capitulos for t in modelo.trechos_do_capitulo(c)
                        if t.familia == "simbolos" or any(ord(ch) >= PISO_DO_SIMBOLO for ch in t.texto))
        if not texto:
            return None
        from core import exportar

        try:
            return exportar.fonte_dos_simbolos(texto)
        except Exception as erro:      # noqa: BLE001 — sem a fonte de recurso, o símbolo sai na fonte do texto
            self.relatorio.aviso(f"fonte de símbolos não embutida ({erro})")
            return None

    def _preparar_referencias(self, capitulos: Sequence[Capitulo]) -> None:
        """
        Os alvos de link e de `ref` do livro inteiro: é o que decide onde vai marcador. Só
        o que existe entra — um link para capítulo ou id que não há sai como texto, com aviso.
        """
        ids = {cap.arquivo: {b.id for b in modelo.blocos_do_capitulo(cap)} | {n.id for n in cap.notas}
               for cap in capitulos}
        n = 0
        for cap in capitulos:
            for trecho in modelo.trechos_do_capitulo(cap):
                if not trecho.link or "://" in trecho.link or trecho.link.startswith(("mailto:", "data:")):
                    continue
                arquivo, _, ancora = trecho.link.partition("#")
                arquivo = self._resolver(arquivo, cap.arquivo)
                if arquivo not in ids or (ancora and ancora not in ids[arquivo]):
                    continue
                chave = f"{arquivo}#{ancora}" if ancora else arquivo
                if trecho.ref:
                    if chave not in self._refs:
                        n += 1
                        self._refs[chave] = f"_Ref{n}"
                elif chave not in self._alvos:
                    indice = self._chaves_dos_capitulos.get(arquivo, 0)
                    self._alvos[chave] = _nome_de_marcador(f"bm_{indice}_{ancora or 'inicio'}")

    def _resolver(self, href: str, de_arquivo: str) -> str:
        if not href:
            return de_arquivo
        base = posixpath.dirname(de_arquivo)
        candidato = posixpath.normpath(posixpath.join(base, href)) if base else posixpath.normpath(href)
        if candidato in self._chaves_dos_capitulos:
            return candidato
        return href if href in self._chaves_dos_capitulos else candidato

    # ------------------------------------------------------------------
    # Estilos, página, cabeçalhos
    # ------------------------------------------------------------------

    def _estilos(self) -> None:
        from core import exportar
        from docx.enum.style import WD_STYLE_TYPE
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt, RGBColor

        estilos = self.doc.styles
        corpo = exportar.CORPO_DO_TEXTO_PT

        def paragrafo(nome: str, base: str = "Normal", style_id: str | None = None) -> Any:
            """
            Um estilo de parágrafo; `style_id` é dado quando o nome é um **nome interno do
            Word** ("footnote text", "toc 1") — e aí o estilo nasce `builtin`, sem
            `w:customStyle`, senão o Word o trata como estilo do usuário com nome reservado
            e cria "Texto de nota de rodapé1" ao lado do dele (medido no Word 16).
            """
            if nome in estilos:
                estilo = estilos[nome]
            else:
                estilo = estilos.add_style(nome, WD_STYLE_TYPE.PARAGRAPH, builtin=bool(style_id))
                estilo.base_style = estilos[base]
                estilo.quick_style = True
            if style_id:
                estilo.element.set(_qn("w:styleId"), style_id)
            return estilo

        for nome in ("Primeira", "Notacao", "Comentario", "Destaque", "Epigrafe", "Assinatura",
                     "Cabecalho de diagrama"):
            paragrafo(nome).element.set(_qn("w:styleId"), _style_id(nome))
        primeira = paragrafo("Primeira")
        primeira.paragraph_format.first_line_indent = Pt(0)
        notacao = paragrafo("Notacao")
        notacao.paragraph_format.first_line_indent = Pt(0)
        self._no_proof(notacao)
        comentario = paragrafo("Comentario")
        comentario.font.italic = True
        destaque = paragrafo("Destaque")
        destaque.paragraph_format.first_line_indent = Pt(0)
        destaque.paragraph_format.left_indent = Pt(corpo)
        destaque.paragraph_format.right_indent = Pt(corpo)
        self._borda_e_fundo(destaque, "F4F4F4")
        epigrafe = paragrafo("Epigrafe")
        epigrafe.font.italic = True
        epigrafe.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        epigrafe.paragraph_format.first_line_indent = Pt(0)
        assinatura = paragrafo("Assinatura")
        assinatura.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        assinatura.paragraph_format.first_line_indent = Pt(0)
        cabecalho = paragrafo("Cabecalho de diagrama")
        cabecalho.font.bold = True
        cabecalho.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cabecalho.paragraph_format.first_line_indent = Pt(0)
        cabecalho.paragraph_format.keep_with_next = True
        legenda = paragrafo("Caption")
        legenda.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        legenda.paragraph_format.first_line_indent = Pt(0)
        paragrafo("Quote").paragraph_format.first_line_indent = Pt(0)
        estilos["Normal"].paragraph_format.widow_control = True
        rodape = paragrafo("footnote text", style_id="FootnoteText")
        rodape.font.size = Pt(corpo - 2)
        rodape.paragraph_format.first_line_indent = Pt(0)
        rodape.paragraph_format.space_after = Pt(0)
        fim = paragrafo("endnote text", style_id="EndnoteText")
        fim.font.size = Pt(corpo - 2)
        fim.paragraph_format.first_line_indent = Pt(0)
        fim.paragraph_format.space_after = Pt(0)
        for nivel in range(1, 7):
            toc = paragrafo(f"toc {nivel}", style_id=f"TOC{nivel}")
            toc.paragraph_format.first_line_indent = Pt(0)
            toc.paragraph_format.left_indent = Pt(corpo * (nivel - 1))
            toc.paragraph_format.space_after = Pt(2)
        paragrafo("TOC Heading", "Heading 1", style_id="TOCHeading").paragraph_format.page_break_before = False
        titulo1 = estilos["Heading 1"]
        titulo1.paragraph_format.page_break_before = True
        for nivel in range(1, 7):
            estilos[f"Heading {nivel}"].paragraph_format.first_line_indent = Pt(0)

        for nome, definicao in ESTILOS_DE_CARACTERE.items():
            if nome in estilos:
                estilo = estilos[nome]
            else:
                estilo = estilos.add_style(nome, WD_STYLE_TYPE.CHARACTER, builtin=bool(definicao.get("builtin")))
            estilo.element.set(_qn("w:styleId"), definicao.get("styleId") or _style_id(nome))
            if definicao.get("noProof"):
                self._no_proof(estilo)
            if definicao.get("smallCaps"):
                estilo.font.small_caps = True
            if definicao.get("bold"):
                estilo.font.bold = True
            if definicao.get("italic"):
                estilo.font.italic = True
            if definicao.get("underline"):
                estilo.font.underline = True
            if definicao.get("cor"):
                estilo.font.color.rgb = RGBColor.from_string(definicao["cor"])
            if definicao.get("shd"):
                self._sombreado(estilo.element.get_or_add_rPr(), definicao["shd"])
            if definicao.get("vertAlign"):
                estilo.font.superscript = True
            if definicao.get("simbolos") and self._simbolos:
                self._familia_do_rpr(estilo.element.get_or_add_rPr(), self._simbolos[0])
        for estilo in list(estilos):
            if estilo.type in (WD_STYLE_TYPE.PARAGRAPH, WD_STYLE_TYPE.CHARACTER):
                exportar._idioma_do_estilo(estilo, self.idioma)

    def _no_proof(self, estilo: Any) -> None:
        rpr = estilo.element.get_or_add_rPr()
        if rpr.find(_qn("w:noProof")) is None:
            rpr.insert_element_before(_el("w:noProof"), "w:snapToGrid", "w:vanish", "w:webHidden", "w:color",
                                      "w:spacing", "w:w", "w:kern", "w:position", "w:sz", "w:szCs", "w:highlight",
                                      "w:u", "w:effect", "w:bdr", "w:shd", "w:fitText", "w:vertAlign", "w:rtl",
                                      "w:cs", "w:em", "w:lang", "w:eastAsianLayout", "w:specVanish", "w:oMath")

    def _sombreado(self, rpr: Any, cor: str) -> None:
        shd = _el("w:shd", **{"w:val": "clear", "w:color": "auto", "w:fill": cor})
        rpr.insert_element_before(shd, "w:fitText", "w:vertAlign", "w:rtl", "w:cs", "w:em", "w:lang",
                                  "w:eastAsianLayout", "w:specVanish", "w:oMath")

    def _borda_e_fundo(self, estilo: Any, fundo: str) -> None:
        ppr = estilo.element.get_or_add_pPr()
        bordas = _el("w:pBdr")
        for lado in ("top", "left", "bottom", "right"):
            bordas.append(_el(f"w:{lado}", **{"w:val": "single", "w:sz": "6", "w:space": "4", "w:color": "999999"}))
        ppr.insert_element_before(bordas, "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
                                  "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi",
                                  "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing",
                                  "w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection",
                                  "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle",
                                  "w:rPr", "w:sectPr", "w:pPrChange")
        shd = _el("w:shd", **{"w:val": "clear", "w:color": "auto", "w:fill": fundo})
        ppr.insert_element_before(shd, "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
                                  "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi",
                                  "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing",
                                  "w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection",
                                  "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle",
                                  "w:rPr", "w:sectPr", "w:pPrChange")

    def _familia_do_rpr(self, rpr: Any, familia: str) -> None:
        """Os quatro atributos do `w:rFonts`: sem `hAnsi`, o Word troca de fonte no primeiro não-ASCII."""
        fontes = rpr.get_or_add_rFonts()
        for atributo in ("ascii", "hAnsi", "cs", "eastAsia"):
            fontes.set(_qn(f"w:{atributo}"), familia)

    def _pagina(self) -> None:
        from docx.shared import Mm

        pagina = self.livro.pagina
        superior, externa, inferior, interna = pagina.margens_mm
        for secao in self.doc.sections:
            secao.page_width = Mm(pagina.largura_mm)
            secao.page_height = Mm(pagina.altura_mm)
            secao.top_margin = Mm(superior)
            secao.bottom_margin = Mm(inferior)
            secao.left_margin = Mm(interna)
            secao.right_margin = Mm(externa)

    def _cabecalhos(self) -> None:
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        pagina = self.livro.pagina
        titulo = self.livro.metadados.titulo
        secao = self.doc.sections[0]
        self.doc.settings.odd_and_even_pages_header_footer = True

        def escrever(cabecalho: Any, conteudo: str, alinhamento: Any) -> None:
            p = cabecalho.paragraphs[0]
            p.alignment = alinhamento
            if conteudo == "titulo":
                p.add_run(titulo)
            elif conteudo == "capitulo":
                # `STYLEREF 1` (o nível), e não `STYLEREF "Heading 1"`: o nome do estilo no campo é
                # o nome **local** — num Word em português, "Heading 1" dá "Erro! Use a guia…".
                self._campo(p._p, "STYLEREF 1 \\* MERGEFORMAT", titulo)
                self._tem_campos = True

        if pagina.cabecalho_impar:
            escrever(secao.header, pagina.cabecalho_impar, WD_ALIGN_PARAGRAPH.RIGHT)
        if pagina.cabecalho_par:
            escrever(secao.even_page_header, pagina.cabecalho_par, WD_ALIGN_PARAGRAPH.LEFT)
        if pagina.numerar_paginas:
            for rodape in (secao.footer, secao.even_page_footer):
                p = rodape.paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                self._campo(p._p, "PAGE", "1")
            self._tem_campos = True

    # ------------------------------------------------------------------
    # Capítulos e blocos
    # ------------------------------------------------------------------

    def _capitulo(self, cap: Capitulo) -> None:
        self._capitulo_atual = cap
        self._indice_do_capitulo = self._chaves_dos_capitulos[cap.arquivo]
        self._marcador_pendente = []
        if cap.arquivo in self._alvos:
            self._marcador_pendente.append(self._alvos[cap.arquivo])
        if not cap.blocos and not self._marcador_pendente:
            return
        for bloco in cap.blocos:
            self._bloco(bloco)
        if self._marcador_pendente or self._paginas_pendentes:
            p = self.doc.add_paragraph()
            self._abrir_paragrafo(p, None)

    def _bloco(self, bloco: Bloco, container: Any = None) -> None:
        chave = f"{self._capitulo_atual.arquivo}#{bloco.id}" if self._capitulo_atual else ""
        if chave in self._alvos:
            self._marcador_pendente.append(self._alvos[chave])
        if isinstance(bloco, Titulo):
            self._titulo(bloco, container)
        elif isinstance(bloco, Paragrafo):
            self._paragrafo(bloco, container=container)
        elif isinstance(bloco, Lista):
            self._lista(bloco, container)
        elif isinstance(bloco, Tabela):
            self._tabela(bloco, chave)
        elif isinstance(bloco, Figura):
            self._figura(bloco, chave)
        elif isinstance(bloco, Diagrama):
            self._diagrama(bloco, chave)
        elif isinstance(bloco, Citacao):
            for p in bloco.blocos:
                self._paragrafo(p, estilo="Quote", container=container)
        elif isinstance(bloco, QuebraDePagina):
            from docx.enum.text import WD_BREAK

            p = self.doc.add_paragraph()
            self._abrir_paragrafo(p, None)
            p.add_run().add_break(WD_BREAK.PAGE)
        elif isinstance(bloco, MarcaDePagina):
            self._paginas_pendentes.append(bloco.pagina)
        elif isinstance(bloco, Separador):
            p = self.doc.add_paragraph()
            self._abrir_paragrafo(p, None)
            ppr = p._p.get_or_add_pPr()
            bordas = _el("w:pBdr")
            bordas.append(_el("w:bottom", **{"w:val": "single", "w:sz": "6", "w:space": "1", "w:color": "auto"}))
            _por_na_ordem(ppr, bordas, ("pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl",
                                        "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs", "spacing", "ind", "jc",
                                        "rPr"))
        elif isinstance(bloco, IlhaBruta):
            p = self.doc.add_paragraph()
            self._abrir_paragrafo(p, None)
            run = p.add_run(_texto_da_ilha(bloco.xhtml))
            run.style = self.doc.styles["Ilha"]
            onde = self._capitulo_atual.arquivo if self._capitulo_atual else ""
            self.relatorio.aviso(f"{onde}: ilha <{bloco.elemento}> saiu como texto no estilo Ilha")
        else:
            self.relatorio.aviso(f"bloco {type(bloco).__name__} sem tradução para DOCX")

    def _abrir_paragrafo(self, p: Any, bloco: Paragrafo | None) -> None:
        """O que todo parágrafo recebe no começo: marcas de página e marcadores pendentes."""
        for pagina in self._paginas_pendentes:
            self._marcador_vazio(p._p, f"pg-{pagina}")
        self._paginas_pendentes = []
        for nome in self._marcador_pendente:
            self._marcador_vazio(p._p, nome)
        self._marcador_pendente = []

    def _fechar_paginas_pendentes(self) -> None:
        if self._paginas_pendentes:
            p = self.doc.add_paragraph()
            self._abrir_paragrafo(p, None)

    def _formato_de_paragrafo(self, p: Any, bloco: Paragrafo) -> None:
        from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
        from docx.shared import Pt

        from core import exportar

        corpo = exportar.CORPO_DO_TEXTO_PT
        formato = p.paragraph_format
        alinhamentos = {"esquerda": WD_ALIGN_PARAGRAPH.LEFT, "centro": WD_ALIGN_PARAGRAPH.CENTER,
                        "direita": WD_ALIGN_PARAGRAPH.RIGHT, "justificado": WD_ALIGN_PARAGRAPH.JUSTIFY}
        if bloco.alinhamento in alinhamentos:
            formato.alignment = alinhamentos[bloco.alinhamento]
        if bloco.recuo_primeira_em is not None:
            formato.first_line_indent = Pt(bloco.recuo_primeira_em * corpo)
        if bloco.recuo_esquerda_em is not None:
            formato.left_indent = Pt(bloco.recuo_esquerda_em * corpo)
        if bloco.recuo_direita_em is not None:
            formato.right_indent = Pt(bloco.recuo_direita_em * corpo)
        if bloco.antes_em is not None:
            formato.space_before = Pt(bloco.antes_em * corpo)
        if bloco.depois_em is not None:
            formato.space_after = Pt(bloco.depois_em * corpo)
        if bloco.entrelinha is not None:
            formato.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
            formato.line_spacing = float(bloco.entrelinha)
        if bloco.manter_com_proximo:
            formato.keep_with_next = True
        if bloco.manter_linhas:
            formato.keep_together = True

    def _paragrafo(self, bloco: Paragrafo, estilo: str | None = None, container: Any = None,
                   numeracao: tuple[int, int] | None = None) -> Any:
        dono = container if container is not None else self.doc
        p = dono.add_paragraph()
        nome = estilo or dialeto.ESTILOS_DE_PARAGRAFO.get(bloco.estilo, ("p", "", "Normal"))[2]
        if nome in self.doc.styles:
            p.style = self.doc.styles[nome]
        self._abrir_paragrafo(p, bloco)
        self._formato_de_paragrafo(p, bloco)
        if numeracao is not None:
            nivel, num_id = numeracao
            numpr = p._p.get_or_add_pPr().get_or_add_numPr()
            numpr.get_or_add_ilvl().val = nivel
            numpr.get_or_add_numId().val = num_id
        self._trechos(p, bloco.trechos)
        return p

    def _titulo(self, bloco: Titulo, container: Any = None) -> None:
        dono = container if container is not None else self.doc
        p = dono.add_paragraph()
        p.style = self.doc.styles[f"Heading {min(max(bloco.nivel, 1), 6)}"]
        self._abrir_paragrafo(p, bloco)
        self._formato_de_paragrafo(p, bloco)
        chave = f"{self._capitulo_atual.arquivo}#{bloco.id}" if self._capitulo_atual else ""
        nome_toc = f"_Toc{len(self._toc) + 1}"
        inicio, fim = self._marcador(nome_toc)
        p._p.append(inicio)
        self._trechos(p, bloco.trechos)
        p._p.append(fim)
        if chave in self._refs:
            i2, f2 = self._marcador(self._refs[chave])
            inicio.addnext(i2)
            fim.addprevious(f2)
        self._toc.append((bloco.nivel, modelo.texto_de(bloco), nome_toc))

    # -- listas -----------------------------------------------------------

    def _lista(self, lista: Lista, container: Any = None) -> None:
        num_id = self._numeracao(lista)
        self._itens(lista, 0, num_id, container)

    def _itens(self, lista: Lista, nivel: int, num_id: int, container: Any) -> None:
        from docx.shared import Pt

        from core import exportar

        for item in lista.itens:
            for k, p in enumerate(item.paragrafos):
                if k == 0:
                    self._paragrafo(p, estilo="List Paragraph", container=container, numeracao=(nivel, num_id))
                else:
                    par = self._paragrafo(p, estilo="List Paragraph", container=container)
                    par.paragraph_format.left_indent = Pt(exportar.CORPO_DO_TEXTO_PT * 2 * (nivel + 1))
            if item.filhos is not None:
                self._itens(item.filhos, min(nivel + 1, 8), num_id, container)

    def _niveis(self, lista: Lista) -> list[tuple[bool, str, int]]:
        """(ordenada, marcador, início) de cada nível, pela primeira sublista de cada profundidade."""
        niveis: list[tuple[bool, str, int]] = []

        def visitar(sub: Lista, profundidade: int) -> None:
            if profundidade >= len(niveis):
                niveis.append((sub.ordenada, sub.marcador, sub.inicio))
            for item in sub.itens:
                if item.filhos is not None:
                    visitar(item.filhos, profundidade + 1)

        visitar(lista, 0)
        return niveis

    def _numeracao(self, lista: Lista) -> int:
        """Um `abstractNum` (nove níveis) e um `num` para esta lista; `startOverride` por nível."""
        from core import exportar

        numbering = self.doc.part.numbering_part.element
        abstratos = [int(a.get(_qn("w:abstractNumId"))) for a in numbering.findall(_qn("w:abstractNum"))]
        nums = [int(n.get(_qn("w:numId"))) for n in numbering.findall(_qn("w:num"))]
        abstrato_id = max(abstratos + [99]) + 1
        num_id = max(nums + [0]) + 1
        niveis = self._niveis(lista)
        corpo = exportar.CORPO_DO_TEXTO_PT
        abstrato = _el("w:abstractNum", **{"w:abstractNumId": abstrato_id})
        abstrato.append(_el("w:multiLevelType", **{"w:val": "hybridMultilevel"}))
        for ilvl in range(9):
            if ilvl < len(niveis):
                ordenada, marcador, _inicio = niveis[ilvl]
            else:
                ordenada, marcador = niveis[0][0], ""
            if not marcador:
                marcador = "decimal" if ordenada else MARCADOR_SEM_ORDEM[ilvl % 3]
            formato, texto, fonte = MARCADORES.get(marcador, MARCADORES["decimal" if ordenada else "disco"])
            lvl = _el("w:lvl", **{"w:ilvl": ilvl})
            lvl.append(_el("w:start", **{"w:val": "1"}))
            lvl.append(_el("w:numFmt", **{"w:val": formato}))
            lvl.append(_el("w:lvlText", **{"w:val": texto.replace("%n", f"%{ilvl + 1}")}))
            lvl.append(_el("w:lvlJc", **{"w:val": "left"}))
            ppr = _el("w:pPr")
            recuo = int(round((corpo * 2 * (ilvl + 1)) * 20))
            ppr.append(_el("w:ind", **{"w:left": recuo, "w:hanging": int(round(corpo * 1.2 * 20))}))
            lvl.append(ppr)
            if fonte:
                rpr = _el("w:rPr")
                rpr.append(_el("w:rFonts", **{"w:ascii": fonte, "w:hAnsi": fonte, "w:hint": "default"}))
                lvl.append(rpr)
            abstrato.append(lvl)
        primeiro_num = numbering.find(_qn("w:num"))
        if primeiro_num is not None:
            primeiro_num.addprevious(abstrato)
        else:
            numbering.append(abstrato)
        num = _el("w:num", **{"w:numId": num_id})
        num.append(_el("w:abstractNumId", **{"w:val": abstrato_id}))
        for ilvl, (_ordenada, _marcador, inicio) in enumerate(niveis):
            if inicio != 1:
                sobre = _el("w:lvlOverride", **{"w:ilvl": ilvl})
                sobre.append(_el("w:startOverride", **{"w:val": inicio}))
                num.append(sobre)
        numbering.append(num)
        self._num_ids.append(num_id)
        return num_id

    # -- tabelas, figuras, diagramas ---------------------------------------

    def _legenda(self, tipo: str, bloco: Any, chave: str, antes: bool) -> Any:
        """"Tabela n: legenda" no estilo Caption, com `SEQ` e o marcador `_Ref<n>` em torno de "Tabela n"."""
        self._numeros[tipo] += 1
        numero = bloco.numero or self._numeros[tipo]
        rotulo = ROTULOS[tipo]
        p = self.doc.add_paragraph()
        p.style = self.doc.styles["Caption"]
        self._abrir_paragrafo(p, None)
        if antes:
            p.paragraph_format.keep_with_next = True
        inicio = fim = None
        if chave in self._refs:
            inicio, fim = self._marcador(self._refs[chave])
            p._p.append(inicio)
        p.add_run(rotulo + " ")
        self._campo(p._p, f"SEQ {rotulo} \\* ARABIC", str(numero))
        self._tem_campos = True
        if fim is not None:
            p._p.append(fim)
        if bloco.legenda:
            p.add_run(": ")
            self._trechos(p, bloco.legenda)
        return p

    def _separador_de_tabelas(self) -> None:
        """Duas tabelas coladas viram uma quando o Word abre o arquivo (ver `exportar.para_docx`)."""
        from docx.shared import Pt

        vao = self.doc.add_paragraph()
        vao.paragraph_format.space_before = Pt(0)
        vao.paragraph_format.space_after = Pt(0)
        vao.paragraph_format.line_spacing = Pt(1)
        vao.paragraph_format.first_line_indent = Pt(0)

    def _tabela(self, bloco: Tabela, chave: str) -> None:
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt

        self._legenda("tabela", bloco, chave, antes=True)
        filas, colunas = len(bloco.filas), bloco.colunas
        t = self.doc.add_table(rows=filas, cols=colunas)
        try:
            t.style = self.doc.styles["Table Grid"]
        except KeyError:
            pass
        if bloco.largura_pct:
            tblw = t._tbl.tblPr.find(_qn("w:tblW"))
            if tblw is not None:
                tblw.set(_qn("w:type"), "pct")
                tblw.set(_qn("w:w"), str(int(bloco.largura_pct) * 50))
        alinhamentos = {"esquerda": WD_ALIGN_PARAGRAPH.LEFT, "centro": WD_ALIGN_PARAGRAPH.CENTER,
                        "direita": WD_ALIGN_PARAGRAPH.RIGHT, "justificado": WD_ALIGN_PARAGRAPH.JUSTIFY}
        for i, (fila, celulas) in enumerate(zip(t.rows, bloco.filas)):
            if i == 0 and bloco.primeira_fila_cabecalho:
                fila._tr.get_or_add_trPr().append(_el("w:tblHeader"))
            for celula_docx, celula in zip(fila.cells, celulas):
                primeiro = True
                for p_modelo in celula.blocos:
                    p = celula_docx.paragraphs[0] if primeiro else celula_docx.add_paragraph()
                    primeiro = False
                    nome = dialeto.ESTILOS_DE_PARAGRAFO.get(p_modelo.estilo, ("p", "", "Normal"))[2]
                    if nome in self.doc.styles:
                        p.style = self.doc.styles[nome]
                    self._formato_de_paragrafo(p, p_modelo)
                    p.paragraph_format.first_line_indent = Pt(0)
                    if celula.alinhamento in alinhamentos:
                        p.alignment = alinhamentos[celula.alinhamento]
                    elif not p_modelo.alinhamento:
                        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    self._trechos(p, p_modelo.trechos, negrito=celula.cabecalho)
                if not celula.blocos:
                    celula_docx.paragraphs[0].paragraph_format.first_line_indent = Pt(0)
        self._separador_de_tabelas()

    def _bytes_do_recurso(self, caminho: str) -> bytes | None:
        recurso = self.livro.recurso(caminho)
        if recurso is None:
            return None
        try:
            return epub.dados_de(self.livro, recurso)
        except FileNotFoundError:
            return None

    def _rasterizar_svg(self, dados: bytes) -> bytes:
        import fitz

        documento = fitz.open(stream=dados, filetype="svg")
        try:
            pagina = documento[0]
            return pagina.get_pixmap(dpi=200, alpha=False).tobytes("png")
        finally:
            documento.close()

    def _imagem(self, dados: bytes, largura_pt: float | None, descricao: str, alinhamento: str) -> Any:
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt

        p = self.doc.add_paragraph()
        self._abrir_paragrafo(p, None)
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.keep_with_next = True
        run = p.add_run()
        largura = Pt(largura_pt) if largura_pt else None
        forma = run.add_picture(io.BytesIO(dados), width=largura)
        forma._inline.docPr.set("descr", descricao)
        p.alignment = {"esq": WD_ALIGN_PARAGRAPH.LEFT, "dir": WD_ALIGN_PARAGRAPH.RIGHT}.get(alinhamento,
                                                                                            WD_ALIGN_PARAGRAPH.CENTER)
        return forma

    def _figura(self, bloco: Figura, chave: str) -> None:
        dados = self._bytes_do_recurso(bloco.recurso)
        onde = self._capitulo_atual.arquivo if self._capitulo_atual else ""
        if dados is None:
            self.relatorio.aviso(f"{onde}: imagem {bloco.recurso} não está no livro; figura {bloco.id} saiu sem imagem")
            p = self.doc.add_paragraph(f"[imagem ausente: {bloco.recurso}]")
            self._abrir_paragrafo(p, None)
        else:
            e_svg = bloco.recurso.lower().endswith(".svg") or dados.lstrip()[:4] == b"<svg"
            if e_svg:
                try:
                    dados = self._rasterizar_svg(dados)
                    self.relatorio.aviso(f"{onde}: SVG {bloco.recurso} rasterizado para o DOCX")
                except Exception as erro:      # noqa: BLE001 — SVG que o fitz não lê sai como aviso, não como falha
                    self.relatorio.aviso(f"{onde}: SVG {bloco.recurso} não pôde ser rasterizado ({erro})")
                    p = self.doc.add_paragraph(f"[imagem SVG: {bloco.recurso}]")
                    self._abrir_paragrafo(p, None)
                    dados = None
            if dados is not None:
                descricao = bloco.alt or modelo.texto_de(bloco) or posixpath.basename(bloco.recurso)
                if not bloco.alt:
                    self.relatorio.aviso(f"{onde}: figura {bloco.recurso} sem texto alternativo")
                try:
                    self._imagem(dados, bloco.largura_pt, descricao, bloco.alinhamento)
                except Exception as erro:      # noqa: BLE001 — formato que o python-docx não abre
                    self.relatorio.aviso(f"{onde}: imagem {bloco.recurso} não entrou ({erro})")
        if bloco.legenda or bloco.numero is not None or chave in self._refs:
            self._legenda("figura", bloco, chave, antes=False)
        else:
            self._numeros["figura"] += 1

    def _png_do_diagrama(self, d: Diagrama) -> bytes | None:
        if d.imagem and d.imagem_chave == dialeto.chave_do_diagrama(d):
            dados = self._bytes_do_recurso(d.imagem)
            if dados is not None:
                return dados
        try:
            png, _largura, _altura = epub.png_do_diagrama(d)
        except Exception as erro:      # noqa: BLE001 — fonte ausente: aviso, e o diagrama sai em texto
            self.relatorio.aviso(f"diagrama {d.id} não desenhado ({erro})")
            return None
        return png

    def _diagrama(self, d: Diagrama, chave: str) -> None:
        onde = self._capitulo_atual.arquivo if self._capitulo_atual else ""
        modo = self.opcoes.modo_de_diagrama
        if modo == "fonte":
            if self._diagrama_em_fonte(d, onde):
                self._contagem["fonte"] += 1
                self._legenda_do_diagrama(d, chave)
                return
        png = self._png_do_diagrama(d)
        if png is None:
            p = self.doc.add_paragraph(f"[Diagrama: {d.fen}]")
            self._abrir_paragrafo(p, None)
        else:
            self._imagem(png, xhtml.largura_do_png_pt(d), d.fen, "centro")
            self._contagem["png"] += 1
        self._legenda_do_diagrama(d, chave)

    def _legenda_do_diagrama(self, d: Diagrama, chave: str) -> None:
        if d.legenda or d.numero is not None or chave in self._refs:
            self._legenda("diagrama", d, chave, antes=False)
        else:
            self._numeros["diagrama"] += 1

    def _diagrama_em_fonte(self, d: Diagrama, onde: str) -> bool:
        """A tabela 1×1 na fonte embutida; `False` quando tem de cair para PNG (com o motivo no relatório)."""
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt

        from core import exportar, render_diagrama

        try:
            fonte = render_diagrama.carregar(d.fonte)
        except (render_diagrama.FonteDesconhecida, render_diagrama.FonteIncompleta, OSError) as erro:
            self.relatorio.aviso(f"{onde}: diagrama {d.id} em imagem — fonte {d.fonte} indisponível ({erro})")
            return False
        linhas = None
        emolduradas = False
        if d.coordenadas:
            if d.moldura != "sem":
                linhas = render_diagrama.grade(d.fen, fonte, d.orientacao, d.moldura, d.cantos)
                emolduradas = linhas is not None
            if linhas is None:
                self.relatorio.aviso(f"{onde}: diagrama {d.id} em imagem — {d.fonte} não desenha coordenadas "
                                     "em glifo (no Word não há como alinhar rótulos de outra fonte sobre as casas)")
                return False
        if linhas is None:
            linhas = render_diagrama.linhas(d.fen, fonte, d.orientacao)
        corpo_pt = corpo_valido(d.corpo_pt)
        corpo = Pt(corpo_pt)
        colunas = max(len(linha) for linha in linhas)
        self._fechar_pendentes_num_paragrafo()
        caixa = exportar._caixa_do_diagrama(self.doc, "sem" if emolduradas else d.moldura,
                                            corpo_pt * colunas + FOLGA_DA_CAIXA_PT, d.fen)
        for i, linha in enumerate(linhas):
            p = caixa.paragraphs[0] if i == 0 else caixa.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.first_line_indent = Pt(0)
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = corpo
            run = p.add_run(linha)
            run.font.size = corpo
            self._familia_do_rpr(run._element.get_or_add_rPr(), d.fonte)
        self._fontes[d.fonte] = fonte.arquivo
        self._separador_de_tabelas()
        return True

    def _fechar_pendentes_num_paragrafo(self) -> None:
        """Antes de uma tabela: marca de página e marcador pendentes precisam de um parágrafo."""
        if self._paginas_pendentes or self._marcador_pendente:
            p = self.doc.add_paragraph()
            self._abrir_paragrafo(p, None)

    # ------------------------------------------------------------------
    # Trechos
    # ------------------------------------------------------------------

    def _trechos(self, p: Any, trechos: Sequence[Trecho], negrito: bool = False, em_nota: bool = False) -> None:
        for trecho in trechos:
            if trecho.pagina is not None:
                self._marcador_vazio(p._p, f"pg-{trecho.pagina}")
            if trecho.quebra_antes:
                from docx.enum.text import WD_BREAK

                p.add_run().add_break(WD_BREAK.LINE)
            if trecho.ilha:
                run = p.add_run(_texto_da_ilha(trecho.ilha))
                run.style = self.doc.styles["Ilha"]
                self.relatorio.aviso(f"{self._capitulo_atual.arquivo if self._capitulo_atual else ''}: ilha inline "
                                     f"saiu como texto no estilo Ilha")
                continue
            if trecho.nota:
                if em_nota:
                    self.relatorio.aviso("nota dentro de nota não tem tradução para DOCX; a referência saiu como texto")
                    p.add_run(trecho.texto or "")
                else:
                    self._referencia_de_nota(p, trecho.nota)
                continue
            if not trecho.texto:
                continue
            if trecho.ref and trecho.link:
                self._referencia_cruzada(p, trecho)
                continue
            if trecho.link:
                self._hiperlink(p, trecho, em_nota)
                continue
            self._run(p, trecho, negrito=negrito)

    def _run(self, p: Any, trecho: Trecho, negrito: bool = False, dentro: Any = None) -> Any:
        from docx.shared import Pt, RGBColor

        run = p.add_run(trecho.texto)
        if dentro is not None:
            dentro.append(run._element)
        if trecho.negrito or negrito:
            run.bold = True
        if trecho.italico:
            run.italic = True
        if trecho.sublinhado:
            run.underline = True
        if trecho.tachado:
            run.font.strike = True
        if trecho.versalete:
            run.font.small_caps = True
        if trecho.posicao == "sobre":
            run.font.superscript = True
        elif trecho.posicao == "sub":
            run.font.subscript = True
        if trecho.corpo_pt:
            run.font.size = Pt(trecho.corpo_pt)
        cor = _hex(trecho.cor) if trecho.cor else None
        fundo = _hex(trecho.fundo) if trecho.fundo else None
        if fundo:
            self._sombreado(run._element.get_or_add_rPr(), fundo)
            if cor is None and _escuro(fundo):
                cor = "FFFFFF"
        if cor:
            run.font.color.rgb = RGBColor.from_string(cor)
        if trecho.papel in ESTILO_DE_CARACTERE_DO_PAPEL:
            run.style = self.doc.styles[ESTILO_DE_CARACTERE_DO_PAPEL[trecho.papel]]
        if trecho.codigo:
            self._familia_do_rpr(run._element.get_or_add_rPr(), FONTE_MONOESPACADA)
        if trecho.familia:
            self._familia_do_run(run, trecho.familia)
        if trecho.lang:
            rpr = run._element.get_or_add_rPr()
            rpr.insert_element_before(_el("w:lang", **{"w:val": trecho.lang}), "w:eastAsianLayout", "w:specVanish",
                                      "w:oMath")
        return run

    def _familia_do_run(self, run: Any, familia: str) -> None:
        if familia == "simbolos":
            if self._simbolos:
                self._familia_do_rpr(run._element.get_or_add_rPr(), self._simbolos[0])
                self._fontes[self._simbolos[0]] = self._simbolos[1]
            return
        if xhtml._e_fonte_de_diagrama(familia):
            from core import render_diagrama

            try:
                fonte = render_diagrama.carregar(familia)
                self._fontes[familia] = fonte.arquivo
            except (render_diagrama.FonteDesconhecida, render_diagrama.FonteIncompleta, OSError) as erro:
                if familia not in self._avisadas():
                    self.relatorio.aviso(f"fonte de diagrama {familia} não embutida ({erro})")
        self._familia_do_rpr(run._element.get_or_add_rPr(), familia)

    def _avisadas(self) -> set[str]:
        if not hasattr(self, "_familias_avisadas"):
            self._familias_avisadas: set[str] = set()
        return self._familias_avisadas

    def _hiperlink(self, p: Any, trecho: Trecho, em_nota: bool) -> None:
        from docx.opc.constants import RELATIONSHIP_TYPE as RT

        externo = "://" in trecho.link or trecho.link.startswith(("mailto:", "data:"))
        hyperlink = _el("w:hyperlink")
        if externo:
            parte = self._partes_de_notas.get("atual") if em_nota else self.doc.part
            rid = parte.relate_to(trecho.link, RT.HYPERLINK, is_external=True)
            hyperlink.set(_qn("r:id"), rid)
        else:
            arquivo, _, ancora = trecho.link.partition("#")
            arquivo = self._resolver(arquivo, self._capitulo_atual.arquivo if self._capitulo_atual else "")
            chave = f"{arquivo}#{ancora}" if ancora else arquivo
            alvo = self._alvos.get(chave)
            if alvo is None:
                self.relatorio.aviso(f"link para {trecho.link!r} sem alvo no livro; saiu como texto")
                self._run(p, trecho)
                return
            hyperlink.set(_qn("w:anchor"), alvo)
        hyperlink.set(_qn("w:history"), "1")
        p._p.append(hyperlink)
        run = self._run(p, trecho, dentro=hyperlink)
        run.style = self.doc.styles["Hyperlink"]

    def _referencia_cruzada(self, p: Any, trecho: Trecho) -> None:
        arquivo, _, ancora = trecho.link.partition("#")
        arquivo = self._resolver(arquivo, self._capitulo_atual.arquivo if self._capitulo_atual else "")
        chave = f"{arquivo}#{ancora}" if ancora else arquivo
        nome = self._refs.get(chave)
        if nome is None:
            self._run(p, trecho)
            return
        self._campo(p._p, f"REF {nome} \\h", trecho.texto)
        self._tem_campos = True

    # -- notas ---------------------------------------------------------------

    def _tipo_da_nota(self, nota: Nota) -> str:
        return "fim" if (self.opcoes.notas == "fim" or nota.tipo == "fim") else "rodape"

    def _referencia_de_nota(self, p: Any, nota_id: str) -> None:
        cap = self._capitulo_atual
        nota = cap.nota(nota_id) if cap is not None else None
        if nota is None:
            self.relatorio.aviso(f"{cap.arquivo if cap else ''}: referência à nota {nota_id!r} sem nota; "
                                 "saiu como texto")
            p.add_run("[nota]")
            return
        tipo = self._tipo_da_nota(nota)
        parte = self._parte_de_notas(tipo)
        lista = self._notas[tipo]
        numero = len(lista) + 1
        elemento_nota = _el("w:footnote" if tipo == "rodape" else "w:endnote", **{"w:id": numero})
        estilo_texto = "footnote text" if tipo == "rodape" else "endnote text"
        estilo_ref = "footnote reference" if tipo == "rodape" else "endnote reference"
        self._partes_de_notas["atual"] = parte
        for k, bloco in enumerate(nota.blocos or [Paragrafo(trechos=[])]):
            par = self.doc.add_paragraph()
            par.style = self.doc.styles[estilo_texto]
            if k == 0:
                run = par.add_run()
                run.style = self.doc.styles[estilo_ref]
                run._element.append(_el("w:footnoteRef" if tipo == "rodape" else "w:endnoteRef"))
                par.add_run(" ")
            self._trechos(par, bloco.trechos, em_nota=True)
            elemento_nota.append(par._p)             # sai do corpo e entra na nota
        self._partes_de_notas.pop("atual", None)
        lista.append(elemento_nota)
        run = p.add_run()
        run.style = self.doc.styles[estilo_ref]
        run._element.append(_el("w:footnoteReference" if tipo == "rodape" else "w:endnoteReference",
                                **{"w:id": numero}))

    def _parte_de_notas(self, tipo: str) -> Any:
        if tipo in self._partes_de_notas:
            return self._partes_de_notas[tipo]
        from docx.opc.constants import RELATIONSHIP_TYPE as RT
        from docx.opc.packuri import PackURI
        from docx.opc.part import Part

        nome = "/word/footnotes.xml" if tipo == "rodape" else "/word/endnotes.xml"
        tipo_de_conteudo = CT_FOOTNOTES if tipo == "rodape" else CT_ENDNOTES
        parte = Part(PackURI(nome), tipo_de_conteudo, b"", self.doc.part.package)
        self.doc.part.relate_to(parte, RT.FOOTNOTES if tipo == "rodape" else RT.ENDNOTES)
        self._partes_de_notas[tipo] = parte
        return parte

    def _notas_no_pacote(self) -> None:
        """As partes `footnotes.xml`/`endnotes.xml` com as separadoras `-1` e `0` e as notas."""
        from lxml import etree

        for tipo, parte in list(self._partes_de_notas.items()):
            if tipo == "atual":
                continue
            raiz_tag = "w:footnotes" if tipo == "rodape" else "w:endnotes"
            nota_tag = "w:footnote" if tipo == "rodape" else "w:endnote"
            ref_tag = "w:footnoteRef" if tipo == "rodape" else "w:endnoteRef"
            raiz = _el(raiz_tag)
            for id_, separador in ((-1, "w:separator"), (0, "w:continuationSeparator")):
                nota = _el(nota_tag, **{"w:type": "separator" if id_ == -1 else "continuationSeparator", "w:id": id_})
                p = _el("w:p")
                ppr = _el("w:pPr")
                ppr.append(_el("w:spacing", **{"w:after": "0", "w:line": "240", "w:lineRule": "auto"}))
                p.append(ppr)
                r = _el("w:r")
                r.append(_el(separador))
                p.append(r)
                nota.append(p)
                raiz.append(nota)
            for elemento in self._notas[tipo]:
                raiz.append(elemento)
            assert ref_tag  # documentação: o `w:footnoteRef` já está no primeiro parágrafo de cada nota
            parte._blob = etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True)

    # -- sumário -------------------------------------------------------------

    def _sumario(self) -> None:
        """O `w:sdt` pré-renderizado, no começo do corpo: uma entrada por título com `PAGEREF`."""
        from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
        from docx.shared import Mm

        pagina = self.livro.pagina
        largura_util = Mm(pagina.largura_mm - pagina.margens_mm[1] - pagina.margens_mm[3])
        corpo = self.doc.element.body
        sdt = _el("w:sdt")
        sdtpr = _el("w:sdtPr")
        obj = _el("w:docPartObj")
        obj.append(_el("w:docPartGallery", **{"w:val": "Table of Contents"}))
        obj.append(_el("w:docPartUnique"))
        sdtpr.append(obj)
        sdt.append(sdtpr)
        conteudo = _el("w:sdtContent")
        sdt.append(conteudo)
        titulo = self.doc.add_paragraph("Sumário")
        titulo.style = self.doc.styles["TOC Heading"]
        conteudo.append(titulo._p)
        entradas = [(nivel, texto, nome) for nivel, texto, nome in self._toc if nivel <= 3]
        for k, (nivel, texto, nome) in enumerate(entradas):
            p = self.doc.add_paragraph()
            p.style = self.doc.styles[f"toc {nivel}"]
            p.paragraph_format.tab_stops.add_tab_stop(largura_util, WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            if k == 0:
                self._campo_abrir(p._p, 'TOC \\o "1-3" \\h \\z \\u')
            hyperlink = _el("w:hyperlink", **{"w:anchor": nome, "w:history": "1"})
            p._p.append(hyperlink)
            r = _el("w:r")
            t = _el("w:t")
            t.text = texto
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            r.append(t)
            hyperlink.append(r)
            tab = _el("w:r")
            tab.append(_el("w:tab"))
            hyperlink.append(tab)
            self._campo(hyperlink, f"PAGEREF {nome} \\h", str(self._indice_da_pagina(k)))
            if k == len(entradas) - 1:
                self._campo_fechar(p._p)
            conteudo.append(p._p)
        self._tem_campos = True
        corpo.insert(0, sdt)

    @staticmethod
    def _indice_da_pagina(k: int) -> int:
        return k + 1

    # -- campos e marcadores -------------------------------------------------

    def _campo_abrir(self, pai: Any, instrucao: str) -> None:
        r = _el("w:r")
        r.append(_el("w:fldChar", **{"w:fldCharType": "begin"}))
        pai.append(r)
        r = _el("w:r")
        instr = _el("w:instrText")
        instr.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        instr.text = f" {instrucao} "
        r.append(instr)
        pai.append(r)
        r = _el("w:r")
        r.append(_el("w:fldChar", **{"w:fldCharType": "separate"}))
        pai.append(r)

    def _campo_fechar(self, pai: Any) -> None:
        r = _el("w:r")
        r.append(_el("w:fldChar", **{"w:fldCharType": "end"}))
        pai.append(r)

    def _campo(self, pai: Any, instrucao: str, resultado: str) -> None:
        """Um campo completo — begin, instrText, separate, o resultado em cache, end."""
        self._campo_abrir(pai, instrucao)
        r = _el("w:r")
        t = _el("w:t")
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = resultado
        r.append(t)
        pai.append(r)
        self._campo_fechar(pai)

    def _marcador(self, nome: str) -> tuple[Any, Any]:
        self._marcadores += 1
        inicio = _el("w:bookmarkStart", **{"w:id": self._marcadores, "w:name": nome})
        fim = _el("w:bookmarkEnd", **{"w:id": self._marcadores})
        return inicio, fim

    def _marcador_vazio(self, p_element: Any, nome: str) -> None:
        inicio, fim = self._marcador(nome)
        p_element.append(inicio)
        p_element.append(fim)

    # -- settings --------------------------------------------------------------

    def _settings(self) -> None:
        settings = self.doc.settings.element
        pagina = self.livro.pagina
        if pagina.espelhadas and settings.find(_qn("w:mirrorMargins")) is None:
            _por_na_ordem(settings, _el("w:mirrorMargins"), ORDEM_DOS_SETTINGS)
        if pagina.hifenizar and settings.find(_qn("w:autoHyphenation")) is None:
            _por_na_ordem(settings, _el("w:autoHyphenation", **{"w:val": "true"}), ORDEM_DOS_SETTINGS)
        if self._tem_campos and settings.find(_qn("w:updateFields")) is None:
            _por_na_ordem(settings, _el("w:updateFields", **{"w:val": "true"}), ORDEM_DOS_SETTINGS)
        for tipo, tag, filho in (("rodape", "w:footnotePr", "w:footnote"), ("fim", "w:endnotePr", "w:endnote")):
            if tipo in self._partes_de_notas and settings.find(_qn(tag)) is None:
                pr = _el(tag)
                pr.append(_el(filho, **{"w:id": "-1"}))
                pr.append(_el(filho, **{"w:id": "0"}))
                _por_na_ordem(settings, pr, ORDEM_DOS_SETTINGS)


__all__ = ["escrever", "INSTRUCAO_DE_INSTALACAO", "MARCADORES", "ESTILOS_DE_CARACTERE", "ORDEM_DOS_SETTINGS"]
