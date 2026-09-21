"""
O livro no disco: ler e escrever EPUB preservando a disposição (ED-01; SPEC_EDITOR
§10.1, DEC-01, DEC-08).

## O que "preservar a disposição" quer dizer

Um EPUB aberto aqui volta ao disco **com os mesmos nomes de entrada**: o OPF onde
estava (`OEBPS/content.opf` no livro de hoje, `OEBPS/package.opf` no do Sigil), o
`nav.xhtml` e o `toc.ncx` no lugar, cada capítulo e cada recurso com o `href` tal como
lido. O que é regenerado — OPF, nav, NCX, o XHTML dos capítulos que passaram pelo
modelo — é regenerado **no mesmo caminho**; o que não é dialeto (uma folha de estilo,
uma fonte, um `META-INF/encryption.xml`, um arquivo esquecido fora do manifesto)
volta byte a byte. É o contrário de "importar e exportar": o livro continua sendo
o mesmo arquivo, editado por dentro.

## O que o modelo interpreta, e o que só carrega

Do OPF, o modelo entende identificador, título, idioma, pessoas (com `role` e
`file-as`, em `refines` do EPUB 3 ou em `opf:role` do EPUB 2), editora, data,
descrição, assuntos, direitos, fonte impressa, coleção, capa, `dcterms:modified` e
os `pybox:*` que ele mesmo escreve. **Tudo o mais fica em `Metadados.extras` na
letra** — um `title-type`, um `calibre:series`, um `<link rel="record">` — e volta
depois do que o escritor gera. Para os `refines` desses extras continuarem apontando
para alguma coisa, os `id` dos elementos interpretados são guardados
(`Metadados.ids`, `Pessoa.id`) e reescritos iguais.

Os metadados de acessibilidade (`schema:*`) e o `ibooks:specified-fonts` **não** são
carregados: são calculados do conteúdo a cada gravação (§10.1), e carregar os velhos
faria o livro declarar o que já não tem.

## Recursos sob demanda

Um EPUB de 300 páginas com 400 imagens não precisa vir inteiro para a memória para
se editar um parágrafo. `Recurso.dados` fica `None` até alguém pedir
(`dados_de`), e `Livro.zip_de_origem` diz de onde ler. Ao gravar, o que ainda não
foi lido é copiado do zip antigo para o novo — mesmo quando os dois são o mesmo
caminho, porque a escrita é num arquivo temporário ao lado e só o `os.replace`
final troca um pelo outro (é o que garante que uma gravação interrompida deixa o
original intacto).

## Diagramas em imagem

Um `Diagrama` em modo `png` cujo PNG já está no livro com outro nome (o
`fig-0001-1.png` do EPUB de hoje) **reutiliza o PNG** enquanto os parâmetros do
desenho não mudarem (`Diagrama.imagem`, `imagem_chave`); só o diagrama alterado,
ou o novo, é desenhado por `render_diagrama.desenhar` — uma vez por chave, com
cache. Redesenhar todos a cada gravação custaria segundos e trocaria em silêncio a
orientação dos que o EPUB de hoje não registra (DEC-06).
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import tempfile
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from typing import Iterable
from urllib.parse import quote, unquote
from xml.sax.saxutils import escape

from core.editor import css_minima, dialeto, fontes, modelo, sumario, xhtml
from core.editor.conversao import Cronometro, RelatorioDeConversao
from core.editor.modelo import (Capitulo, Diagrama, Figura, FormatoDePagina, Livro, Metadados,
                                OrigemDoLivro, Pessoa, Recurso, Titulo, Trecho)
from core.editor.xhtml import ErroDeXhtml

NS_OPF = "http://www.idpf.org/2007/opf"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_XML = "http://www.w3.org/XML/1998/namespace"
NS_CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"

MIME_EPUB = "application/epub+zip"
MIME_XHTML = "application/xhtml+xml"
MIME_NCX = "application/x-dtbncx+xml"
MIME_CSS = "text/css"
MIME_PNG = "image/png"

#: Extensão → tipo de mídia, para os recursos que chegam sem manifesto (e para `novo_livro`).
TIPOS_MIME = {
    ".xhtml": MIME_XHTML, ".html": MIME_XHTML, ".htm": MIME_XHTML, ".css": MIME_CSS,
    ".png": MIME_PNG, ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".svg": "image/svg+xml", ".webp": "image/webp", ".otf": "font/otf", ".ttf": "font/ttf",
    ".woff": "font/woff", ".woff2": "font/woff2", ".ncx": MIME_NCX, ".js": "application/javascript",
    ".mp3": "audio/mpeg", ".mp4": "video/mp4", ".json": "application/json", ".xml": "application/xml",
    ".smil": "application/smil+xml", ".pls": "application/pls+xml", ".txt": "text/plain",
}
#: Os tipos de fonte, com os nomes antigos que um EPUB 3.0 ainda usa.
TIPOS_DE_FONTE = {"font/otf", "font/ttf", "font/woff", "font/woff2", "application/vnd.ms-opentype",
                  "application/font-sfnt", "application/x-font-ttf", "application/x-font-otf",
                  "application/font-woff", "application/font-woff2"}

#: Prefixos que o EPUB 3.3 reserva: usá-los sem declarar é certo, declará-los é aviso.
PREFIXOS_RESERVADOS = {"a11y", "dcterms", "marc", "media", "onix", "rendition", "schema", "xsd"}
URI_IBOOKS = "http://vocabulary.itunes.apple.com/rdf/ibooks/vocabulary-extensions-1.0/"
URI_PYBOX = "urn:pyboxeditor:vocabulario"
PREFIXO_PYBOX = "pybox"

#: `epub:type` do marco → `type` do `<guide>` do EPUB 2 (só os que o guide conhece).
GUIDE_DO_MARCO = {
    "cover": "cover", "toc": "toc", "bodymatter": "text", "titlepage": "title-page",
    "preface": "preface", "index": "index", "glossary": "glossary", "bibliography": "bibliography",
    "copyright-page": "copyright-page", "dedication": "dedication", "acknowledgments": "acknowledgements",
    "loi": "loi", "lot": "lot", "endnotes": "notes", "colophon": "colophon", "foreword": "foreword",
}
MARCO_DO_GUIDE = {v: k for k, v in GUIDE_DO_MARCO.items()}

#: Um `Titulo` que é só "Página 12" não é navegação estrutural (§10.1, ED-10).
_RE_TITULO_DE_PAGINA = re.compile(r"^\s*p[áa]g(?:ina)?\.?\s*\d+\s*$", re.IGNORECASE)

#: As propriedades do EPUB 2 que viram `Pessoa`.
_RE_PREFIXO = re.compile(r"([A-Za-z_][\w.-]*):\s*(\S+)")
_RE_PROPRIEDADE_COM_PREFIXO = re.compile(r'(?:property|scheme)="([A-Za-z_][\w.-]*):')
_RE_ENTIDADE_NOMEADA = re.compile(rb"&[A-Za-z][A-Za-z0-9]*;")
_RE_ENTIDADE_DO_XML = re.compile(rb"&(?:lt|gt|amp|quot|apos);")


class ErroDeEpub(ValueError):
    """O arquivo não é um EPUB que dê para abrir (sem container, sem OPF, zip corrompido)."""


# ----------------------------------------------------------------------
# Utilidades de caminho e de XML
# ----------------------------------------------------------------------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _ns(tag: str) -> str:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


def _attr(valor: str) -> str:
    return escape(str(valor), {'"': "&quot;"})


def nome_no_zip(livro: Livro, href: str) -> str:
    """O nome da entrada no zip de um `href` relativo ao OPF do livro."""
    pasta = posixpath.dirname(livro.opf)
    return posixpath.normpath(posixpath.join(pasta, href)) if pasta else posixpath.normpath(href)


def href_de(livro: Livro, nome: str) -> str:
    """O inverso: a entrada do zip como `href` relativo ao OPF."""
    pasta = posixpath.dirname(livro.opf)
    return posixpath.relpath(nome, pasta) if pasta else nome


def tipo_mime_de(caminho: str) -> str:
    return TIPOS_MIME.get(posixpath.splitext(caminho)[1].lower(), "application/octet-stream")


def _agora() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _e_fonte(recurso: Recurso) -> bool:
    return recurso.tipo_mime in TIPOS_DE_FONTE or recurso.tipo_mime.startswith("font/")


def fontes_embutidas(livro: Livro) -> list[str]:
    """Os hrefs das fontes que o livro carrega (o que o relatório mostra)."""
    return [c for c, r in livro.recursos.items() if _e_fonte(r) and r.no_manifesto]


def pasta_de_imagens(livro: Livro) -> str:
    """
    Onde os PNG dos diagramas ficam: a pasta dos `diag-*.png` que o livro já tem; senão a
    da primeira imagem; senão `Images` (o livro novo). O EPUB de hoje usa `imagens/`.
    """
    for caminho in livro.recursos:
        if posixpath.basename(caminho).startswith("diag-") and caminho.endswith(".png"):
            return posixpath.dirname(caminho) or "."
    for caminho, recurso in livro.recursos.items():
        if recurso.tipo_mime.startswith("image/") and recurso.no_manifesto:
            return posixpath.dirname(caminho) or "."
    return "Images"


def dados_de(livro: Livro, recurso: Recurso) -> bytes:
    """
    Os bytes do recurso: os que ele tem; o `texto_cru` codificado; ou, lidos agora do
    `zip_de_origem` e guardados nele. `FileNotFoundError` quando não há de onde ler.
    """
    if recurso.texto_cru is not None:
        return recurso.texto_cru.lstrip("\ufeff").encode("utf-8")
    if recurso.dados is not None:
        return recurso.dados
    if not livro.zip_de_origem:
        raise FileNotFoundError(f"recurso {recurso.caminho} sem dados e sem zip de origem")
    nome = nome_no_zip(livro, recurso.caminho)
    try:
        with zipfile.ZipFile(livro.zip_de_origem) as z:
            recurso.dados = z.read(nome)
    except (OSError, KeyError, zipfile.BadZipFile) as erro:
        raise FileNotFoundError(f"recurso {recurso.caminho} não está em {livro.zip_de_origem}: {erro}") from None
    return recurso.dados


def descarregar(livro: Livro) -> int:
    """
    Solta da memória os recursos que já estão no `zip_de_origem` — o que se faz depois
    de gravar, porque a gravação carrega todos para copiá-los, e um rascunho de 60 s
    não deve levar 400 imagens em base64. Devolve quantos soltou.
    """
    if not livro.zip_de_origem:
        return 0
    try:
        with zipfile.ZipFile(livro.zip_de_origem) as z:
            nomes = set(z.namelist())
    except (OSError, zipfile.BadZipFile):
        return 0
    soltos = 0
    for recurso in livro.recursos.values():
        no_zip = nome_no_zip(livro, recurso.caminho) in nomes
        if recurso.dados is not None and recurso.texto_cru is None and no_zip:
            recurso.dados = None
            soltos += 1
    return soltos


# ----------------------------------------------------------------------
# Leitura
# ----------------------------------------------------------------------

def _opf_do_container(z: zipfile.ZipFile, nomes: list[str], relatorio: RelatorioDeConversao) -> str:
    if "META-INF/container.xml" in nomes:
        try:
            raiz = ET.fromstring(z.read("META-INF/container.xml"))
        except ET.ParseError as erro:
            raise ErroDeEpub(f"META-INF/container.xml mal-formado: {erro}") from None
        for el in raiz.iter():
            if _local(el.tag) == "rootfile" and el.get("full-path"):
                caminho = unquote(el.get("full-path"))
                if caminho in nomes:
                    return caminho
                raise ErroDeEpub(f"o container aponta para {caminho}, que não está no zip")
        raise ErroDeEpub("META-INF/container.xml sem rootfile")
    candidatos = [n for n in nomes if n.lower().endswith(".opf")]
    if not candidatos:
        raise ErroDeEpub("não é um EPUB: sem META-INF/container.xml e sem OPF")
    relatorio.aviso("sem META-INF/container.xml; o OPF foi achado pelo nome")
    return candidatos[0]


class _LeitorDeOpf:
    """Lê o `<package>` inteiro: metadados, manifesto, espinha, guide."""

    def __init__(self, texto: bytes, opf: str, relatorio: RelatorioDeConversao):
        try:
            self.raiz = ET.fromstring(texto)
        except ET.ParseError as erro:
            raise ErroDeEpub(f"{opf} mal-formado: {erro}") from None
        self.opf = opf
        self.relatorio = relatorio
        self.versao = self.raiz.get("version", "3.0")
        self.unico = self.raiz.get("unique-identifier", "")
        self.prefixos = dict(_RE_PREFIXO.findall(self.raiz.get("prefix", "")))
        self.itens: dict[str, tuple[str, str, str]] = {}      # id -> (href, mime, propriedades)
        self.espinha: list[tuple[str, bool]] = []              # (id, linear)
        self.toc_da_espinha = ""
        self.guia: list[tuple[str, str]] = []                  # (type, href)
        self.capa_id = ""
        self.origem = OrigemDoLivro()
        self.pagina: FormatoDePagina | None = None
        for filho in self.raiz:
            nome = _local(filho.tag)
            if nome == "metadata":
                self.metadados = self._metadados(filho)
            elif nome == "manifest":
                self._manifesto(filho)
            elif nome == "spine":
                self.toc_da_espinha = filho.get("toc", "")
                for ref in filho:
                    if _local(ref.tag) == "itemref" and ref.get("idref"):
                        self.espinha.append((ref.get("idref"), ref.get("linear", "yes") != "no"))
            elif nome == "guide":
                for ref in filho:
                    if _local(ref.tag) == "reference" and ref.get("href"):
                        self.guia.append((ref.get("type", ""), unquote(ref.get("href").split("#")[0])))
        if not hasattr(self, "metadados"):
            self.metadados = Metadados(titulo="")
            relatorio.aviso("OPF sem <metadata>")

    # -- manifesto --------------------------------------------------------

    def _manifesto(self, manifesto: ET.Element) -> None:
        for item in manifesto:
            if _local(item.tag) != "item" or not item.get("href"):
                continue
            id_ = item.get("id", "") or f"item-{len(self.itens) + 1}"
            self.itens[id_] = (unquote(item.get("href")), item.get("media-type", ""), item.get("properties", ""))

    # -- metadados --------------------------------------------------------

    def _atributos_verbatim(self, el: ET.Element, ignorar: Iterable[str] = ()) -> str:
        partes = []
        for chave, valor in el.attrib.items():
            nome = _nome_do_atributo(chave)
            if nome in ignorar:
                continue
            partes.append(f'{nome}="{_attr(valor)}"')
        return " ".join(partes)

    def _metadados(self, md: ET.Element) -> Metadados:
        """
        Dois passes: os elementos, na ordem; depois os `<meta refines>` que nenhum
        elemento interpretado consumiu (um `title-type`, um `display-seq`), verbatim.
        Um `refines` pode vir **antes** do elemento que refina, e é por isso que ele
        não é decidido no primeiro passe.
        """
        m = Metadados(titulo="", idioma="")        # sem `dc:language` é "und", não o "en" do padrão
        elementos = list(md)
        refina: dict[str, list[ET.Element]] = {}
        for el in elementos:
            alvo = el.get("refines", "")
            if _local(el.tag) == "meta" and alvo.startswith("#"):
                refina.setdefault(alvo[1:], []).append(el)
        consumidos: set[int] = set()

        def refines_de(el: ET.Element, propriedade: str) -> str:
            for r in refina.get(el.get("id", ""), []):
                if r.get("property") == propriedade:
                    consumidos.add(id(r))
                    return (r.text or "").strip()
            return ""

        def pessoa(el: ET.Element, papel_padrao: str) -> Pessoa:
            papel = refines_de(el, "role") or el.get(f"{{{NS_OPF}}}role", "") or papel_padrao
            file_as = refines_de(el, "file-as") or el.get(f"{{{NS_OPF}}}file-as", "")
            return Pessoa(nome=(el.text or "").strip() or "?", papel=papel, file_as=file_as, id=el.get("id", ""))

        def guardar_id(chave: str, el: ET.Element) -> None:
            if el.get("id"):
                m.ids[chave] = el.get("id")

        # O identificador principal é o que `unique-identifier` aponta; sem ele, o primeiro.
        identificadores = [el for el in elementos if _ns(el.tag) == NS_DC and _local(el.tag) == "identifier"]
        principal = next((el for el in identificadores if self.unico and el.get("id") == self.unico),
                         identificadores[0] if identificadores else None)
        vistos: set[str] = set()
        simples = {"title": "titulo", "language": "idioma", "publisher": "editora", "date": "data",
                   "description": "descricao", "rights": "direitos", "source": "fonte_impressa"}
        for el in elementos:
            if id(el) in consumidos or (el.get("refines", "").startswith("#") and _local(el.tag) == "meta"):
                continue
            nome, ns = _local(el.tag), _ns(el.tag)
            texto = (el.text or "").strip()
            if ns == NS_DC:
                if nome == "identifier" and el is principal:
                    m.identificador = texto
                    guardar_id("identificador", el)
                elif nome in simples and simples[nome] not in vistos:
                    campo = simples[nome]
                    vistos.add(campo)
                    setattr(m, campo, texto)
                    guardar_id(campo, el)
                    if nome == "source":
                        refines_de(el, "source-of")
                elif nome == "creator":
                    m.autores.append(pessoa(el, "aut"))
                elif nome == "contributor":
                    m.colaboradores.append(pessoa(el, "ctb"))
                elif nome == "subject":
                    m.assuntos.append(texto)
                    guardar_id(f"assunto-{len(m.assuntos)}", el)
                else:
                    m.extras.append((f"dc:{nome}", self._atributos_verbatim(el), texto))
                continue
            if nome == "meta":
                propriedade = el.get("property", "")
                if propriedade == "dcterms:modified":
                    m.modificado = texto
                elif propriedade == "belongs-to-collection" and m.colecao is None:
                    posicao = refines_de(el, "group-position")
                    try:
                        m.colecao = (texto, int(float(posicao)) if posicao else 0)
                    except ValueError:
                        m.colecao = (texto, 0)
                    guardar_id("colecao", el)
                elif propriedade.startswith("schema:access") or propriedade in ("ibooks:specified-fonts",
                                                                                 "pageBreakSource"):
                    continue      # calculados a cada gravação (§10.1)
                elif propriedade.startswith(PREFIXO_PYBOX + ":"):
                    self._pybox(propriedade[len(PREFIXO_PYBOX) + 1:], texto)
                elif el.get("name") == "cover":
                    self.capa_id = el.get("content", "")
                else:
                    m.extras.append(("meta", self._atributos_verbatim(el), texto))
                continue
            m.extras.append((nome, self._atributos_verbatim(el), texto))
        for el in elementos:
            if _local(el.tag) == "meta" and el.get("refines", "").startswith("#") and id(el) not in consumidos:
                m.extras.append(("meta", self._atributos_verbatim(el), (el.text or "").strip()))
        m.prefixos = {p: u for p, u in self.prefixos.items()
                      if p not in PREFIXOS_RESERVADOS and p not in ("ibooks", PREFIXO_PYBOX)}
        return m

    def _pybox(self, chave: str, valor: str) -> None:
        if chave in ("documento_editorial", "pdf", "diario"):
            setattr(self.origem, chave, valor)
        elif chave == "pagina":
            try:
                self.pagina = modelo.de_dict(dict(json.loads(valor), tipo="FormatoDePagina"))
            except (ValueError, TypeError) as erro:
                self.relatorio.aviso(f"pybox:pagina ilegível, ignorado: {erro}")


def _nome_do_atributo(chave: str) -> str:
    if chave.startswith("{"):
        uri, local = chave[1:].split("}", 1)
        if uri == NS_XML:
            return f"xml:{local}"
        if uri == NS_OPF:
            return f"opf:{local}"
        return local
    return chave


def ler(caminho: str) -> tuple[Livro, RelatorioDeConversao]:
    """
    Abre um EPUB — qualquer um, 2 ou 3, do Sigil, do Calibre ou do `exportar.para_epub`
    — preservando a disposição. Capítulo que não é XHTML bem-formado abre em
    `texto_cru` (modo código) com aviso, e não derruba o livro.
    """
    caminho = os.fspath(caminho)
    relatorio = RelatorioDeConversao(formato="epub", arquivos=[caminho])
    with Cronometro(relatorio):
        try:
            z = zipfile.ZipFile(caminho)
        except (OSError, zipfile.BadZipFile) as erro:
            raise ErroDeEpub(f"não deu para abrir {caminho}: {erro}") from None
        with z:
            livro = _ler_do_zip(z, caminho, relatorio)
    relatorio.contar(livro)
    relatorio.fontes_embutidas = fontes_embutidas(livro)
    return livro, relatorio


def _ler_do_zip(z: zipfile.ZipFile, caminho: str, relatorio: RelatorioDeConversao) -> Livro:
    nomes = z.namelist()
    if "mimetype" not in nomes:
        relatorio.aviso("sem entrada mimetype")
    elif z.read("mimetype").strip() != MIME_EPUB.encode("ascii"):
        relatorio.aviso("mimetype não é application/epub+zip")
    opf = _opf_do_container(z, nomes, relatorio)
    leitor = _LeitorDeOpf(z.read(opf), opf, relatorio)
    livro = Livro(metadados=leitor.metadados, opf=opf, origem=leitor.origem, zip_de_origem=caminho)
    if leitor.pagina is not None:
        livro.pagina = leitor.pagina
    pasta = posixpath.dirname(opf)

    # O nav e o NCX, pelo manifesto.
    nav_id = next((i for i, (_h, _m, props) in leitor.itens.items() if "nav" in props.split()), "")
    ncx_id = leitor.toc_da_espinha if leitor.toc_da_espinha in leitor.itens else \
        next((i for i, (_h, mime, _p) in leitor.itens.items() if mime == MIME_NCX), "")
    livro.nav = leitor.itens[nav_id][0] if nav_id else ""
    livro.ncx = leitor.itens[ncx_id][0] if ncx_id else ""

    # A espinha vira capítulos; o resto do manifesto, recursos.
    na_espinha: set[str] = set()
    for i, (id_, linear) in enumerate(leitor.espinha):
        if id_ not in leitor.itens:
            relatorio.aviso(f"espinha aponta para id inexistente: {id_}")
            continue
        href, mime, _props = leitor.itens[id_]
        if id_ == nav_id:
            livro.nav_na_espinha = len(livro.capitulos)
            na_espinha.add(id_)
            continue
        if mime != MIME_XHTML and not href.lower().endswith((".xhtml", ".html", ".htm")):
            relatorio.aviso(f"espinha com item que não é XHTML, deixado como recurso: {href}")
            continue
        nome = nome_no_zip(livro, href)
        if nome not in nomes:
            relatorio.aviso(f"capítulo do manifesto ausente no zip: {href}")
            continue
        dados = z.read(nome)
        try:
            cap = xhtml.ler(dados, href)
        except ErroDeXhtml as erro:
            texto = dados.decode("utf-8", errors="replace").lstrip("\ufeff")
            cap = Capitulo(arquivo=href, texto_cru=texto, avisos=[f"XHTML mal-formado: {erro}"])
            relatorio.aviso(f"{href}: XHTML mal-formado ({erro}); aberto em modo código")
        cap.linear = linear
        livro.capitulos.append(cap)
        na_espinha.add(id_)
    for id_, (href, mime, props) in leitor.itens.items():
        if id_ in na_espinha or id_ == nav_id or id_ == ncx_id:
            continue
        if nome_no_zip(livro, href) not in nomes:
            relatorio.aviso(f"recurso do manifesto ausente no zip: {href}")
            continue
        propriedades = " ".join(p for p in props.split() if p != "cover-image")
        livro.recursos[href] = Recurso(caminho=href, tipo_mime=mime or tipo_mime_de(href),
                                       propriedades=propriedades)
        if "cover-image" in props.split():
            livro.metadados.capa = href
    if not livro.metadados.capa and leitor.capa_id in leitor.itens:
        livro.metadados.capa = leitor.itens[leitor.capa_id][0]
    livro.folhas = [c for c, r in livro.recursos.items() if r.tipo_mime == MIME_CSS]

    # O que está no zip sem estar no manifesto viaja junto (META-INF/*, sobras).
    conhecidos = {opf, "mimetype", "META-INF/container.xml"}
    conhecidos |= {nome_no_zip(livro, h) for h, _m, _p in leitor.itens.values()}
    for nome in nomes:
        if nome in conhecidos or nome.endswith("/"):
            continue
        href = href_de(livro, nome)
        livro.recursos[href] = Recurso(caminho=href, tipo_mime=tipo_mime_de(nome), no_manifesto=False)
        if not nome.startswith("META-INF/"):
            relatorio.aviso(f"arquivo fora do manifesto, mantido onde está: {nome}")

    # Sumário e marcos: do nav; sem nav, do NCX e do guide.
    if livro.nav and nome_no_zip(livro, livro.nav) in nomes:
        try:
            livro.sumario, livro.marcos, _paginas = sumario.ler_nav(z.read(nome_no_zip(livro, livro.nav)), livro.nav)
        except ErroDeXhtml as erro:
            relatorio.aviso(f"{livro.nav} mal-formado ({erro}); sumário refeito dos títulos")
    elif livro.nav:
        relatorio.aviso(f"nav ausente no zip: {livro.nav}")
        livro.nav = ""
    if not livro.sumario and livro.ncx and nome_no_zip(livro, livro.ncx) in nomes:
        try:
            livro.sumario = sumario.ler_ncx(z.read(nome_no_zip(livro, livro.ncx)), livro.ncx)
        except ErroDeXhtml as erro:
            relatorio.aviso(f"{livro.ncx} mal-formado ({erro})")
    if not livro.nav:
        livro.nav = _nome_livre(livro, "nav.xhtml")
        if leitor.versao.startswith("2"):
            relatorio.aviso("EPUB 2: o nav.xhtml será criado ao salvar")
    if not livro.marcos and leitor.guia:
        for tipo, href in leitor.guia:
            if tipo in MARCO_DO_GUIDE:
                destino = posixpath.normpath(posixpath.join(pasta, href)) if pasta else href
                livro.marcos.append((MARCO_DO_GUIDE[tipo], href_de(livro, destino)))
    if not livro.sumario:
        livro.sumario = sumario.gerar_dos_titulos(livro)
    return livro


def _nome_livre(livro: Livro, nome: str) -> str:
    """`nome`, ou `nome-1`, `nome-2`… — o primeiro que não colide com capítulo ou recurso."""
    usados = {c.arquivo for c in livro.capitulos} | set(livro.recursos) | {livro.ncx}
    if nome not in usados:
        return nome
    raiz, ext = posixpath.splitext(nome)
    n = 1
    while f"{raiz}-{n}{ext}" in usados:
        n += 1
    return f"{raiz}-{n}{ext}"


# ----------------------------------------------------------------------
# Escrita
# ----------------------------------------------------------------------

#: chave do diagrama → (png, largura, altura); o mesmo diagrama não é desenhado duas vezes.
_CACHE_DE_PNG: dict[str, tuple[bytes, int, int]] = {}
_LIMITE_DO_CACHE = 512


def png_do_diagrama(d: Diagrama) -> tuple[bytes, int, int]:
    """O PNG deste diagrama, por `render_diagrama.desenhar`, com cache por chave."""
    from core import render_diagrama

    chave = dialeto.chave_do_diagrama(d)
    if chave not in _CACHE_DE_PNG:
        if len(_CACHE_DE_PNG) >= _LIMITE_DO_CACHE:
            _CACHE_DE_PNG.clear()
        _CACHE_DE_PNG[chave] = render_diagrama.desenhar(
            d.fen, fonte=d.fonte, lado_px=render_diagrama.LADO_PADRAO, coordenadas=d.coordenadas,
            moldura=d.moldura, cantos=d.cantos, orientacao=d.orientacao,
            lado_a_jogar=d.lado if d.lado_indicador == "marca" and d.lado in ("w", "b") else None,
            marcas=list(d.marcas), setas=list(d.setas))
    return _CACHE_DE_PNG[chave]


def _id_de_manifesto(href: str, usados: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]", "_", posixpath.basename(href)) or "item"
    if not re.match(r"[A-Za-z_]", base):
        base = "x" + base
    nome, n = base, 1
    while nome in usados:
        n += 1
        nome = f"{base}-{n}"
    usados.add(nome)
    return nome


def _propriedades_do_xhtml(texto: str, lidas: str = "") -> str:
    props = [p for p in lidas.split() if p not in ("svg", "mathml", "scripted", "remote-resources", "nav")]
    if "<svg" in texto:
        props.append("svg")
    if "<math" in texto:
        props.append("mathml")
    if "<script" in texto:
        props.append("scripted")
    if re.search(r'\b(?:src|poster)="https?://', texto) or re.search(r'<link[^>]+href="https?://', texto):
        props.append("remote-resources")
    return " ".join(dict.fromkeys(props))


class _Escritor:
    def __init__(self, livro: Livro, caminho: str, relatorio: RelatorioDeConversao):
        self.livro = livro
        self.caminho = caminho
        self.relatorio = relatorio
        self.entradas: list[tuple[str, bytes]] = []
        self.manifesto: list[tuple[str, str, str, str]] = []     # (id, href, mime, propriedades)
        self.ids: set[str] = set()
        self.pasta_de_imagens = pasta_de_imagens(livro)

    # -- verificação antes de tocar o disco ---------------------------------

    def verificar(self) -> None:
        livro = self.livro
        for aviso in livro.validar():
            self.relatorio.aviso(aviso)
        for cap in livro.capitulos:
            if cap.texto_cru is not None:
                erro = xhtml.bem_formado(cap.texto_cru)
                if erro is not None:
                    raise ErroDeXhtml(erro.linha, erro.coluna, f"{cap.arquivo}: {erro.mensagem}")
        for recurso in livro.recursos.values():
            if recurso.texto_cru is not None and recurso.tipo_mime == MIME_CSS:
                problema = problema_da_css(recurso.texto_cru)
                if problema:
                    self.relatorio.aviso(f"{recurso.caminho}: CSS com problema ({problema}); gravada assim mesmo")
        quebrados = sumario.destinos_quebrados(livro)
        if quebrados:
            livro.sumario = _sem_destinos(livro.sumario, set(quebrados))
            for destino in quebrados:
                self.relatorio.aviso(f"entrada do sumário sem destino, retirada: {destino}")
        arquivos = {c.arquivo for c in livro.capitulos}
        marcos = []
        for tipo, destino in livro.marcos:
            if destino.split("#")[0] in arquivos:
                marcos.append((tipo, destino))
            else:
                self.relatorio.aviso(f"marco {tipo} sem destino, retirado: {destino}")
        livro.marcos = marcos
        if not livro.sumario:
            livro.sumario = sumario.gerar_dos_titulos(livro)
        if not livro.metadados.identificador:
            livro.metadados.identificador = f"urn:uuid:{uuid.uuid4()}"

    # -- montagem -------------------------------------------------------------

    def montar(self, sem_dados: bool = False) -> None:
        """As entradas do zip; com `sem_dados`, só o manifesto (o OPF para ler, ED-08), sem abrir recurso."""
        livro = self.livro
        self.entradas.append(("META-INF/container.xml", _container(livro.opf).encode("utf-8")))
        if not sem_dados:
            self._embutir_fontes()
        capitulos: list[tuple[Capitulo, str]] = []
        for cap in livro.capitulos:
            if cap.texto_cru is not None:
                texto = cap.texto_cru.lstrip("\ufeff")
            else:
                texto = xhtml.escrever(cap, pasta_de_imagens=self.pasta_de_imagens)
                if not sem_dados:
                    self._desenhar_diagramas(cap)
            capitulos.append((cap, texto))
        # Nav, NCX e capítulos vão antes dos recursos no zip: é a ordem em que um leitor os pede.
        nav = livro.nav or _nome_livre(livro, "nav.xhtml")
        livro.nav = nav
        self._item(nav, MIME_XHTML, "nav", sumario.escrever_nav(livro).encode("utf-8"))
        if livro.ncx:
            self._item(livro.ncx, MIME_NCX, "", sumario.escrever_ncx(livro).encode("utf-8"), id_="ncx")
        for cap, texto in capitulos:
            self._item(cap.arquivo, MIME_XHTML, _propriedades_do_xhtml(texto), texto.encode("utf-8"))
        for href, recurso in livro.recursos.items():
            if sem_dados:
                dados = b""
            else:
                try:
                    dados = dados_de(livro, recurso)
                except FileNotFoundError as erro:
                    self.relatorio.aviso(f"recurso deixado de fora: {erro}")
                    continue
            if not recurso.no_manifesto:
                self.entradas.append((nome_no_zip(livro, href), dados))
                continue
            props = recurso.propriedades
            if href == livro.metadados.capa:
                props = " ".join(dict.fromkeys(props.split() + ["cover-image"]))
            self._item(href, recurso.tipo_mime or tipo_mime_de(href), props, dados)
        self.entradas.insert(1, (livro.opf, self._opf().encode("utf-8")))

    def _item(self, href: str, mime: str, props: str, dados: bytes, id_: str = "") -> None:
        if id_ and id_ not in self.ids:
            self.ids.add(id_)
        else:
            id_ = _id_de_manifesto(href, self.ids)
        self.manifesto.append((id_, href, mime, props))
        self.entradas.append((nome_no_zip(self.livro, href), dados))

    def _embutir_fontes(self) -> None:
        """As fontes de diagrama e de símbolos que o livro usa entram como recurso, com o `@font-face` (ED-10)."""
        livro = self.livro

        def ler(recurso: Recurso) -> str:
            return dados_de(livro, recurso).decode("utf-8", errors="replace").lstrip("\ufeff")

        try:
            novas, avisos = fontes.embutir(livro, ler_recurso=ler)
        except Exception as erro:      # noqa: BLE001 — uma fonte que não se lê não derruba a gravação
            novas, avisos = [], [f"fontes não embutidas ({erro})"]
        for aviso in avisos:
            self.relatorio.aviso(aviso)
        for href in novas:
            self.relatorio.aviso(f"fonte embutida: {href}")

    def _desenhar_diagramas(self, cap: Capitulo) -> None:
        """Os PNG dos diagramas em imagem que ninguém desenhou ainda viram recursos do livro."""
        for bloco in modelo.blocos_do_capitulo(cap):
            if not isinstance(bloco, Diagrama) or bloco.modo != "png":
                continue
            href = xhtml.imagem_do_diagrama(bloco, self.pasta_de_imagens)
            if href in self.livro.recursos:
                continue
            try:
                png, _largura, _altura = png_do_diagrama(bloco)
            except Exception as erro:      # noqa: BLE001 — fonte ausente não derruba a gravação
                self.relatorio.aviso(f"{cap.arquivo}: diagrama {bloco.id} não desenhado ({erro})")
                continue
            self.livro.recursos[href] = Recurso(caminho=href, tipo_mime=MIME_PNG, dados=png)

    # -- OPF --------------------------------------------------------------------

    def _opf(self) -> str:
        livro = self.livro
        m = livro.metadados
        ids_por_href = {href: id_ for id_, href, _m, _p in self.manifesto}
        prefixos: dict[str, str] = {}
        tem_fonte = any(mime in TIPOS_DE_FONTE or mime.startswith("font/") for _i, _h, mime, _p in self.manifesto)
        if tem_fonte:
            prefixos["ibooks"] = URI_IBOOKS
        pybox = self._pybox()
        if pybox:
            prefixos[PREFIXO_PYBOX] = URI_PYBOX
        for prefixo, uri in m.prefixos.items():
            if prefixo not in PREFIXOS_RESERVADOS:
                prefixos.setdefault(prefixo, uri)
        for _el, atributos, _v in m.extras:
            for prefixo in _RE_PROPRIEDADE_COM_PREFIXO.findall(atributos):
                if prefixo not in PREFIXOS_RESERVADOS and prefixo not in prefixos:
                    self.relatorio.aviso(f"prefixo {prefixo}: usado nos metadados sem declaração")
        usa_opf = any("opf:" in atributos for _e, atributos, _v in m.extras)
        id_unico = m.ids.get("identificador") or "pub-id"
        cabeca = (f'<package xmlns="{NS_OPF}" version="3.0" unique-identifier="{_attr(id_unico)}"'
                  + (f' xml:lang="{_attr(m.idioma)}"' if m.idioma else "")
                  + (' xmlns:opf="' + NS_OPF + '"' if usa_opf else "")
                  + (' prefix="' + " ".join(f"{p}: {u}" for p, u in prefixos.items()) + '"' if prefixos else "")
                  + ">")
        linhas = ['<?xml version="1.0" encoding="utf-8"?>', cabeca,
                  f'<metadata xmlns:dc="{NS_DC}">']
        linhas.extend(self._metadata(tem_fonte, pybox, ids_por_href))
        linhas.append("</metadata>")
        linhas.append("<manifest>")
        for id_, href, mime, props in self.manifesto:
            linhas.append(f'<item id="{_attr(id_)}" href="{_attr(quote(href, safe="/@!$&()*+,;=:-._~"))}" '
                          f'media-type="{_attr(mime)}"' + (f' properties="{_attr(props)}"' if props else "") + "/>")
        linhas.append("</manifest>")
        linhas.append('<spine toc="ncx">' if livro.ncx else "<spine>")
        itemrefs = [(cap.arquivo, cap.linear) for cap in livro.capitulos]
        if livro.nav_na_espinha is not None:
            itemrefs.insert(min(livro.nav_na_espinha, len(itemrefs)), (livro.nav, False))
        for href, linear in itemrefs:
            linhas.append(f'<itemref idref="{_attr(ids_por_href[href])}"' + ("" if linear else ' linear="no"') + "/>")
        linhas.append("</spine>")
        if livro.ncx and livro.marcos:
            linhas.append("<guide>")
            for tipo, destino in livro.marcos:
                if tipo in GUIDE_DO_MARCO:
                    linhas.append(f'<reference type="{GUIDE_DO_MARCO[tipo]}" '
                                  f'title="{_attr(sumario.ROTULOS_DOS_MARCOS.get(tipo, tipo))}" '
                                  f'href="{_attr(quote(destino, safe="/#@!$&()*+,;=:-._~"))}"/>')
            linhas.append("</guide>")
        linhas.append("</package>")
        return "\n".join(linhas) + "\n"

    def _pybox(self) -> list[tuple[str, str]]:
        livro = self.livro
        saida = [(chave, getattr(livro.origem, chave)) for chave in ("documento_editorial", "pdf", "diario")
                 if getattr(livro.origem, chave)]
        if modelo.para_dict(livro.pagina) != modelo.para_dict(FormatoDePagina()):
            dados = modelo.para_dict(livro.pagina)
            dados.pop("tipo", None)
            saida.append(("pagina", json.dumps(dados, ensure_ascii=False, sort_keys=True)))
        return saida

    def _metadata(self, tem_fonte: bool, pybox: list[tuple[str, str]], ids_por_href: dict[str, str]) -> list[str]:
        livro = self.livro
        m = livro.metadados
        saida: list[str] = []

        def dc(nome: str, texto: str, id_: str = "", extra: str = "") -> None:
            abre = f"<dc:{nome}" + (f' id="{_attr(id_)}"' if id_ else "") + extra
            saida.append(f"{abre}>{escape(texto)}</dc:{nome}>")

        def meta(propriedade: str, texto: str, refines: str = "", scheme: str = "", id_: str = "") -> None:
            saida.append("<meta" + (f' refines="#{_attr(refines)}"' if refines else "") + f' property="{propriedade}"'
                         + (f' scheme="{scheme}"' if scheme else "") + (f' id="{_attr(id_)}"' if id_ else "")
                         + f">{escape(texto)}</meta>")

        dc("identifier", m.identificador, m.ids.get("identificador") or "pub-id")
        dc("title", m.titulo or "Sem título", m.ids.get("titulo", ""))
        dc("language", m.idioma or "und", m.ids.get("idioma", ""))
        for i, pessoa in enumerate(m.autores, start=1):
            id_ = pessoa.id or f"creator-{i}"
            dc("creator", pessoa.nome, id_)
            meta("role", pessoa.papel or "aut", refines=id_, scheme="marc:relators")
            if pessoa.file_as:
                meta("file-as", pessoa.file_as, refines=id_)
        for i, pessoa in enumerate(m.colaboradores, start=1):
            id_ = pessoa.id or f"contributor-{i}"
            dc("contributor", pessoa.nome, id_)
            meta("role", pessoa.papel or "ctb", refines=id_, scheme="marc:relators")
            if pessoa.file_as:
                meta("file-as", pessoa.file_as, refines=id_)
        if m.editora:
            dc("publisher", m.editora, m.ids.get("editora", ""))
        if m.data:
            dc("date", m.data, m.ids.get("data", ""))
        if m.descricao:
            dc("description", m.descricao, m.ids.get("descricao", ""))
        for i, assunto in enumerate(m.assuntos, start=1):
            dc("subject", assunto, m.ids.get(f"assunto-{i}", ""))
        if m.direitos:
            dc("rights", m.direitos, m.ids.get("direitos", ""))
        marcas = sumario.marcas_de_pagina(livro)
        if m.fonte_impressa:
            id_ = m.ids.get("fonte_impressa") or "src-1"
            dc("source", m.fonte_impressa, id_)
            if marcas:
                meta("pageBreakSource", m.fonte_impressa)
        m.modificado = _agora()
        meta("dcterms:modified", m.modificado)
        if m.colecao is not None:
            nome, posicao = m.colecao
            id_ = m.ids.get("colecao") or "colecao-1"
            meta("belongs-to-collection", nome, id_=id_)
            if posicao:
                meta("group-position", str(posicao), refines=id_)
        if m.capa and m.capa in ids_por_href:
            saida.append(f'<meta name="cover" content="{_attr(ids_por_href[m.capa])}"/>')
        saida.extend(self._acessibilidade(marcas))
        if tem_fonte:
            meta("ibooks:specified-fonts", "true")
        for chave, valor in pybox:
            meta(f"{PREFIXO_PYBOX}:{chave}", valor)
        for elemento, atributos, texto in m.extras:
            abre = f"<{elemento}" + (" " + atributos if atributos else "")
            if texto:
                saida.append(f"{abre}>{escape(texto)}</{elemento}>")
            else:
                saida.append(f"{abre}/>")
        return saida

    def _acessibilidade(self, marcas: list) -> list[str]:
        """§10.1: o que o livro **tem**, calculado agora, e nem mais nem menos."""
        livro = self.livro
        imagens = 0
        sem_alt = 0
        diagramas = 0
        titulos = False
        for cap in livro.capitulos:
            for bloco in modelo.blocos_do_capitulo(cap):
                if isinstance(bloco, Figura):
                    imagens += 1
                    if not bloco.alt:
                        sem_alt += 1
                elif isinstance(bloco, Diagrama):
                    diagramas += 1
                    if bloco.modo == "png":
                        imagens += 1
                elif isinstance(bloco, Titulo) and not _RE_TITULO_DE_PAGINA.match(modelo.texto_de(bloco)):
                    titulos = True      # "Página 12" não é navegação estrutural
        if livro.metadados.capa:
            imagens += 1
        saida = ['<meta property="schema:accessMode">textual</meta>']
        if imagens:
            saida.append('<meta property="schema:accessMode">visual</meta>')
        if not sem_alt:
            saida.append('<meta property="schema:accessModeSufficient">textual</meta>')
        recursos = []
        if imagens and not sem_alt:
            recursos.append("alternativeText")
        if titulos:
            recursos.append("structuralNavigation")
        recursos.append("readingOrder")
        if livro.sumario:
            recursos.append("tableOfContents")
        if marcas:
            recursos += ["pageBreakMarkers", "printPageNumbers"]
        saida += [f'<meta property="schema:accessibilityFeature">{r}</meta>' for r in recursos]
        saida.append('<meta property="schema:accessibilityHazard">none</meta>')
        resumo = "Livro em texto corrido, editado no PyBoxEditor."
        if diagramas:
            resumo += " Os diagramas de xadrez trazem a posição descrita em texto alternativo."
        if marcas:
            resumo += " As páginas do impresso estão marcadas."
        saida.append(f'<meta property="schema:accessibilitySummary">{escape(resumo)}</meta>')
        return saida

    # -- gravação -------------------------------------------------------------------

    def gravar(self) -> None:
        caminho = self.caminho
        pasta = os.path.dirname(os.path.abspath(caminho)) or "."
        os.makedirs(pasta, exist_ok=True)
        fd, temporario = tempfile.mkstemp(prefix=".epub-", suffix=".tmp", dir=pasta)
        os.close(fd)
        try:
            with zipfile.ZipFile(temporario, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr(zipfile.ZipInfo("mimetype"), MIME_EPUB, compress_type=zipfile.ZIP_STORED)
                vistos: set[str] = set()
                for nome, dados in self.entradas:
                    if nome in vistos:
                        self.relatorio.aviso(f"entrada repetida no zip, a segunda ficou de fora: {nome}")
                        continue
                    vistos.add(nome)
                    z.writestr(nome, dados)
            with zipfile.ZipFile(temporario) as z:
                if z.testzip() is not None:
                    raise zipfile.BadZipFile("EPUB temporário com entrada inválida")
            os.replace(temporario, caminho)
        except BaseException:
            try:
                os.unlink(temporario)
            except OSError:
                pass
            raise


def problema_da_css(texto: str) -> str:
    """
    O que se consegue apontar numa folha sem um parser de CSS de verdade: chave que
    não fecha (ou que fecha demais), comentário aberto, e o que `css_minima.ler`
    recusar. `""` quando nada salta aos olhos — CSS não é XML, e o leitor tolera muito.
    """
    sem_comentarios = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    if "/*" in sem_comentarios:
        return "comentário sem fechar"
    sem_strings = re.sub(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'", "", sem_comentarios)
    abre, fecha = sem_strings.count("{"), sem_strings.count("}")
    if abre != fecha:
        return f"{abre} chaves abertas e {fecha} fechadas"
    try:
        css_minima.ler(texto)
    except Exception as erro:      # noqa: BLE001 — o que o leitor recusar é o problema
        return str(erro)
    return ""


def _sem_destinos(entradas, quebrados: set[str]):
    saida = []
    for e in entradas:
        if e.destino in quebrados:
            continue
        e.filhos = _sem_destinos(e.filhos, quebrados)
        saida.append(e)
    return saida


def _container(opf: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            f'<container version="1.0" xmlns="{NS_CONTAINER}">\n'
            "  <rootfiles>\n"
            f'    <rootfile full-path="{_attr(quote(opf, safe="/"))}" media-type="application/oebps-package+xml"/>\n'
            "  </rootfiles>\n"
            "</container>\n")


def texto_do_opf(livro: Livro) -> str:
    """O OPF como o escritor o gravaria agora — para a aba só de leitura do navegador (ED-08)."""
    import copy

    escritor = _Escritor(copy.deepcopy(livro), "", RelatorioDeConversao(formato="epub"))
    escritor.montar(sem_dados=True)
    return escritor._opf()


def escrever(livro: Livro, caminho: str, *, ncx: bool | None = None) -> RelatorioDeConversao:
    """
    Grava o livro como EPUB 3 no `caminho`, atomicamente. `ncx=True` acrescenta o
    `toc.ncx` de compatibilidade (`False` o tira; `None` deixa como o livro está).

    Recusa, **antes de tocar o disco**, um capítulo em `texto_cru` mal-formado
    (`ErroDeXhtml` com o arquivo, a linha e a coluna) e um modelo que viola as
    invariantes (`ValueError`); uma CSS com problema é aviso e grava.
    """
    caminho = os.fspath(caminho)
    if ncx is True and not livro.ncx:
        livro.ncx = _nome_livre(livro, "toc.ncx")
    elif ncx is False:
        livro.ncx = ""
    relatorio = RelatorioDeConversao(formato="epub", arquivos=[caminho])
    with Cronometro(relatorio):
        escritor = _Escritor(livro, caminho, relatorio)
        escritor.verificar()
        escritor.montar()
        escritor.gravar()
    livro.zip_de_origem = caminho
    relatorio.contar(livro)
    relatorio.fontes_embutidas = fontes_embutidas(livro)
    return relatorio


# ----------------------------------------------------------------------
# Livro novo e validação estrutural
# ----------------------------------------------------------------------

def novo_livro(titulo: str = "Livro novo", autor: str = "", idioma: str = "pt", *, ncx: bool = True) -> Livro:
    """
    Um livro de um capítulo na disposição `OEBPS/package.opf` + `Text/Styles/Images/Fonts`
    (§10.1), com a folha padrão de `dialeto.css_padrao` e o identificador sorteado.
    """
    folha = "Styles/estilo.css"
    capitulo = "Text/cap-0001.xhtml"
    metadados = Metadados(titulo=titulo, idioma=idioma or "und", identificador=f"urn:uuid:{uuid.uuid4()}",
                          autores=[Pessoa(nome=autor)] if autor.strip() else [])
    cap = Capitulo(arquivo=capitulo, folhas=[folha],
                   blocos=[Titulo(trechos=[Trecho(texto=titulo)], nivel=1)])
    livro = Livro(metadados=metadados, capitulos=[cap], folhas=[folha],
                  recursos={folha: Recurso(caminho=folha, tipo_mime=MIME_CSS,
                                           dados=dialeto.css_padrao().encode("utf-8"))},
                  marcos=[("bodymatter", capitulo)], opf="OEBPS/package.opf", nav="nav.xhtml",
                  ncx="toc.ncx" if ncx else "")
    livro.sumario = sumario.gerar_dos_titulos(livro)
    return livro


def validar_estrutura(caminho: str) -> list[str]:
    """
    O que o `epubcheck` pegaria de estrutura, sem Java: `mimetype` primeiro e sem
    compressão, container, OPF, manifesto contra o zip, espinha contra o manifesto,
    nav, XHTML bem-formado e sem BOM. Lista vazia é "nada a apontar".
    """
    problemas: list[str] = []
    try:
        z = zipfile.ZipFile(caminho)
    except (OSError, zipfile.BadZipFile) as erro:
        return [f"não abre como zip: {erro}"]
    with z:
        infos = z.infolist()
        nomes = [i.filename for i in infos]
        if not infos or infos[0].filename != "mimetype":
            problemas.append("mimetype não é a primeira entrada")
        elif infos[0].compress_type != zipfile.ZIP_STORED:
            problemas.append("mimetype comprimido")
        elif z.read("mimetype") != MIME_EPUB.encode("ascii"):
            problemas.append("mimetype com conteúdo errado")
        if "META-INF/container.xml" not in nomes:
            problemas.append("sem META-INF/container.xml")
            return problemas
        relatorio = RelatorioDeConversao(formato="epub")
        try:
            opf = _opf_do_container(z, nomes, relatorio)
            leitor = _LeitorDeOpf(z.read(opf), opf, relatorio)
        except ErroDeEpub as erro:
            return problemas + [str(erro)]
        pasta = posixpath.dirname(opf)
        if leitor.unico and leitor.unico != leitor.metadados.ids.get("identificador"):
            problemas.append(f"unique-identifier {leitor.unico} não aponta para um dc:identifier")
        if not leitor.metadados.identificador:
            problemas.append("sem dc:identifier")
        if not leitor.metadados.titulo:
            problemas.append("sem dc:title")
        if leitor.metadados.idioma in ("", "und"):
            problemas.append("sem dc:language")
        if not leitor.metadados.modificado:
            problemas.append("sem dcterms:modified")
        tem_nav = False
        capas = 0
        hrefs_vistos: set[str] = set()
        for id_, (href, mime, props) in leitor.itens.items():
            nome = posixpath.normpath(posixpath.join(pasta, href)) if pasta else href
            if href in hrefs_vistos:
                problemas.append(f"manifesto com href repetido: {href}")
            hrefs_vistos.add(href)
            if nome not in nomes:
                problemas.append(f"manifesto aponta para arquivo ausente: {href}")
                continue
            if "nav" in props.split():
                tem_nav = True
                if mime != MIME_XHTML:
                    problemas.append(f"{href}: o nav não é XHTML")
                else:
                    texto_do_nav = z.read(nome).decode("utf-8", errors="replace")
                    if 'epub:type="toc"' not in texto_do_nav and "epub:type='toc'" not in texto_do_nav:
                        problemas.append(f"{href}: nav sem <nav epub:type=\"toc\">")
            if "cover-image" in props.split():
                capas += 1
            if mime == MIME_XHTML:
                dados = z.read(nome)
                if dados.startswith(b"\xef\xbb\xbf"):
                    problemas.append(f"{href}: BOM no início")
                erro = xhtml.bem_formado(dados)
                if erro is not None:
                    problemas.append(f"{href}: {erro}")
                elif _RE_ENTIDADE_NOMEADA.search(_RE_ENTIDADE_DO_XML.sub(b"", dados)):
                    problemas.append(f"{href}: entidade nomeada (o EPUB 3 só aceita as cinco do XML)")
            elif mime == MIME_CSS:
                problema = problema_da_css(z.read(nome).decode("utf-8", errors="replace"))
                if problema:
                    problemas.append(f"{href}: CSS com problema ({problema})")
        if not tem_nav:
            problemas.append("sem item com properties=\"nav\"")
        if capas > 1:
            problemas.append(f"{capas} itens com properties=\"cover-image\" (só pode haver um)")
        vistos_na_espinha: set[str] = set()
        for id_, _linear in leitor.espinha:
            if id_ not in leitor.itens:
                problemas.append(f"espinha aponta para id inexistente: {id_}")
                continue
            if id_ in vistos_na_espinha:
                problemas.append(f"espinha repete o item {id_}")
            vistos_na_espinha.add(id_)
            href, mime, _props = leitor.itens[id_]
            if mime not in (MIME_XHTML, "image/svg+xml"):
                problemas.append(f"espinha com item que não é XHTML: {href} ({mime})")
        if not leitor.espinha:
            problemas.append("espinha vazia")
        if leitor.toc_da_espinha and leitor.toc_da_espinha not in leitor.itens:
            problemas.append(f"spine toc aponta para id inexistente: {leitor.toc_da_espinha}")
        # Um arquivo fora do manifesto (`sobra.txt`) é aviso no epubcheck, não erro: fica para o leitor.
    return problemas


def epubcheck(caminho: str, timeout: float = 300) -> tuple[bool, str] | None:
    """
    Roda o `epubcheck` se houver um (`epubcheck` no PATH ou `python -m epubcheck`,
    que precisa de Java); `None` quando não há. Devolve `(passou, saída)`.
    """
    import shutil
    import subprocess
    import sys

    comando: list[str] | None = None
    exe = shutil.which("epubcheck")
    if exe:
        comando = [exe]
    else:
        try:
            import epubcheck as _modulo  # noqa: F401
            comando = [sys.executable, "-m", "epubcheck"]
        except ImportError:
            return None
    try:
        saida = subprocess.run(comando + [os.fspath(caminho)], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as erro:
        return False, str(erro)
    return saida.returncode == 0, (saida.stdout or "") + (saida.stderr or "")

