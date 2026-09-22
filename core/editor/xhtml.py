"""
XHTML ↔ modelo: `ler`, `escrever`, `canonico`, `bem_formado` (ED-00; SPEC_EDITOR §6).

## Por que um parser `expat` próprio, e não `xml.etree`

Três coisas que o `ElementTree` não dá e o contrato de ida e volta exige:

1. **Entidades HTML.** Um EPUB do Sigil, do Calibre ou do Word está cheio de
   `&nbsp;` e `&mdash;`, que o XML não conhece. O `expat` só as resolve com
   `SetParamEntityParsing(ALWAYS)` **antes** de `UseForeignDTD(True)` e um
   `ExternalEntityRefHandler` que injeta as entidades de `html.entities.html5`
   ignorando o `systemId` — medido: sem o primeiro, o handler nunca é chamado e
   a entidade some em silêncio (o oposto do princípio 2 da spec). Um documento
   `standalone="yes"` faz o `expat` recusar a DTD estrangeira; a declaração é
   retirada antes de analisar, porque `escrever` a regenera de qualquer jeito.
2. **Ilhas byte a byte.** O que está fora do dialeto (DEC-02) tem de voltar ao
   arquivo como estava. `CurrentByteIndex` dá o `<` de cada elemento no início e,
   no fim, o começo de `</x>` (a fatia vai até o `>` seguinte) — ou, num elemento
   vazio como `<br/>`, o byte **depois** do `/>`. Fatia-se o texto-fonte em bytes
   UTF-8, nunca em caracteres.
3. **Namespaces.** Com `namespace_separator=" "`, um `epub:type` sem
   `xmlns:epub` é erro de análise (o `epubcheck` também recusa); sem isso "Salvar"
   passaria e o leitor reprovaria.

Uma exceção ao byte a byte, e é o EPUB 3 quem a impõe: referência nomeada dentro
de ilha sai **numérica** (`&nbsp;` → `&#160;`), porque o formato não aceita a
nomeada (`epubcheck` `RSC-016`).

## O que `canonico` é

`escrever(ler(texto))`, e nada mais esperto: a forma canônica é a que o escritor
produz. É por isso que R1 (`canonico(escrever(ler(x))) == canonico(x)`) é a
idempotência de `escrever ∘ ler`, e é ela que os testes de propriedade medem.
"""

from __future__ import annotations

import html.entities
import posixpath
import re
from urllib.parse import quote, unquote
from dataclasses import dataclass, field
from typing import Any, Sequence
from xml.parsers import expat
from xml.sax.saxutils import escape

from core import lado_a_jogar
from core.editor import dialeto, modelo
from core.editor.modelo import (Bloco, Capitulo, Celula, Citacao, Diagrama, Figura, IlhaBruta,
                                ItemDeLista, Lista, MarcaDePagina, Nota, Paragrafo,
                                QuebraDePagina, Separador, Tabela, Titulo, Trecho)

NS_XHTML = dialeto.NS_XHTML
NS_EPUB = dialeto.NS_EPUB
NS_XML = dialeto.NS_XML

#: O que `quote` deixa como está num `href`: a barra e os caracteres que uma URL relativa admite.
SEGUROS_NA_URL = "/@!$&'()*+,;=:-._~"

#: Prefixos que `escrever` sabe declarar quando aparecem numa ilha.
PREFIXOS_CONHECIDOS = {
    "epub": NS_EPUB,
    "xlink": "http://www.w3.org/1999/xlink",
    "m": "http://www.w3.org/1998/Math/MathML",
    "mml": "http://www.w3.org/1998/Math/MathML",
    "ibooks": "http://vocabulary.itunes.apple.com/rdf/ibooks/vocabulary-extensions-1.0/",
}

#: As entidades do HTML5 como DTD interna, sem as cinco que o XML já tem.
_DTD_DAS_ENTIDADES = "".join(
    f'<!ENTITY {nome[:-1]} "{"".join(f"&#{ord(c)};" for c in valor)}">\n'
    for nome, valor in html.entities.html5.items()
    if nome.endswith(";") and nome[:-1] not in ("lt", "gt", "amp", "quot", "apos")
).encode("ascii")

_RE_ENTIDADE_NOMEADA = re.compile(r"&([A-Za-z][A-Za-z0-9]*);")
_RE_DECLARACAO = re.compile(rb"^(\xef\xbb\xbf)?\s*<\?xml[^>]*\?>")
_RE_STANDALONE = re.compile(rb"\s+standalone\s*=\s*([\"'])yes\1")
_RE_ENCODING = re.compile(rb"encoding\s*=\s*[\"']([A-Za-z0-9._-]+)[\"']")
_RE_PAGINA = re.compile(r"^pg-(\d+)$")

ELEMENTOS_INLINE = frozenset({"a", "span", "strong", "em", "b", "i", "u", "s", "strike", "del",
                              "ins", "sup", "sub", "code", "br"})
ESTILOS_INLINE_SIMPLES = {"strong": "negrito", "em": "italico", "u": "sublinhado",
                          "s": "tachado", "code": "codigo"}


class ErroDeXhtml(ValueError):
    """XML mal-formado, prefixo não declarado ou entidade desconhecida — com linha e coluna."""

    def __init__(self, linha: int, coluna: int, mensagem: str):
        super().__init__(f"linha {linha}, coluna {coluna}: {mensagem}")
        self.linha = linha
        self.coluna = coluna
        self.mensagem = mensagem


# ----------------------------------------------------------------------
# A árvore intermediária
# ----------------------------------------------------------------------

@dataclass
class No:
    nome: str                       # "p", "epub:switch", "{uri}x"
    attrs: dict[str, str]
    filhos: list[Any] = field(default_factory=list)
    inicio: int = 0                 # byte do "<"
    fim: int = 0                    # byte depois do ">" que fecha o elemento
    linha: int = 0

    def elementos(self) -> list["No"]:
        return [f for f in self.filhos if isinstance(f, No)]

    def texto(self) -> str:
        return "".join(f.texto if isinstance(f, Texto) else (f.texto() if isinstance(f, No) else "")
                       for f in self.filhos)

    @property
    def classes(self) -> list[str]:
        return self.attrs.get("class", "").split()

    def so_espaco(self) -> bool:
        return all(isinstance(f, Texto) and not f.texto.strip() for f in self.filhos)


@dataclass
class Texto:
    texto: str


@dataclass
class Comentario:
    texto: str
    inicio: int = 0
    fim: int = 0


@dataclass
class PI:
    alvo: str
    dados: str
    inicio: int = 0
    fim: int = 0


@dataclass
class Documento:
    raiz: No
    fonte: bytes
    codificacao: str
    namespaces: dict[str, str]

    def fatia(self, inicio: int, fim: int) -> str:
        return self.fonte[inicio:fim].decode(self.codificacao, errors="replace")

    def cru(self, no: No | Comentario | PI) -> str:
        return self.fatia(no.inicio, no.fim)


class _Analisador:
    """Constrói a árvore com os deslocamentos em bytes; levanta `ErroDeXhtml`."""

    def __init__(self, dados: bytes):
        self.dados = dados
        self.pilha: list[No] = []
        self.raiz: No | None = None
        self.namespaces: dict[str, str] = {}
        self.prefixos: dict[str, str] = {NS_XHTML: "", NS_EPUB: "epub", NS_XML: "xml"}
        p = expat.ParserCreate(namespace_separator=" ")
        self.p = p
        p.buffer_text = True
        p.ordered_attributes = True
        p.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_ALWAYS)
        p.UseForeignDTD(True)
        p.ExternalEntityRefHandler = self._dtd
        p.SkippedEntityHandler = self._entidade_desconhecida
        p.StartNamespaceDeclHandler = self._namespace
        p.StartElementHandler = self._inicio
        p.EndElementHandler = self._fim
        p.CharacterDataHandler = self._texto
        p.CommentHandler = self._comentario
        p.ProcessingInstructionHandler = self._pi

    # -- handlers ---------------------------------------------------------

    def _dtd(self, context, base, sysid, pubid) -> int:
        externo = self.p.ExternalEntityParserCreate(context)
        externo.Parse(_DTD_DAS_ENTIDADES, True)
        return 1

    def _entidade_desconhecida(self, nome: str, e_parametro: bool) -> None:
        raise ErroDeXhtml(self.p.CurrentLineNumber, self.p.CurrentColumnNumber + 1,
                          f"entidade desconhecida: &{nome};")

    def _namespace(self, prefixo: str | None, uri: str) -> None:
        if prefixo:
            self.namespaces[prefixo] = uri
            self.prefixos.setdefault(uri, prefixo)

    def _nome(self, qualificado: str) -> str:
        uri, _, local = qualificado.rpartition(" ")
        if not uri:
            return local
        prefixo = self.prefixos.get(uri)
        if prefixo is None:
            return "{%s}%s" % (uri, local)
        return f"{prefixo}:{local}" if prefixo else local

    def _inicio(self, nome: str, atributos: list) -> None:
        attrs = {self._nome(atributos[i]): atributos[i + 1] for i in range(0, len(atributos), 2)}
        no = No(self._nome(nome), attrs, inicio=self.p.CurrentByteIndex, linha=self.p.CurrentLineNumber)
        if self.pilha:
            self.pilha[-1].filhos.append(no)
        else:
            self.raiz = no
        self.pilha.append(no)

    def _fim(self, nome: str) -> None:
        no = self.pilha.pop()
        indice = self.p.CurrentByteIndex
        # Num elemento vazio (`<img …/>`) o índice já aponta depois do `/>` — e o que vem
        # a seguir pode ser o `</p>` do pai. Só a própria tag de abertura diz se era vazio.
        if self.dados[indice:indice + 2] == b"</" and not self._tag_vazia(no.inicio):
            fecha = self.dados.find(b">", indice)
            no.fim = fecha + 1 if fecha >= 0 else len(self.dados)
        else:
            no.fim = indice

    def _tag_vazia(self, inicio: int) -> bool:
        """A tag de abertura em `inicio` termina em `/>`? (as aspas dos atributos são respeitadas)."""
        dados = self.dados
        aspas = b""
        i = inicio + 1
        n = len(dados)
        while i < n:
            c = dados[i:i + 1]
            if aspas:
                if c == aspas:
                    aspas = b""
            elif c in (b'"', b"'"):
                aspas = c
            elif c == b">":
                return dados[i - 1:i] == b"/"
            i += 1
        return False

    def _texto(self, texto: str) -> None:
        if not self.pilha:
            return
        filhos = self.pilha[-1].filhos
        if filhos and isinstance(filhos[-1], Texto):
            filhos[-1].texto += texto
        else:
            filhos.append(Texto(texto))

    def _comentario(self, texto: str) -> None:
        inicio = self.p.CurrentByteIndex
        fim = self.dados.find(b"-->", inicio)
        no = Comentario(texto, inicio, fim + 3 if fim >= 0 else inicio)
        if self.pilha:
            self.pilha[-1].filhos.append(no)

    def _pi(self, alvo: str, dados: str) -> None:
        inicio = self.p.CurrentByteIndex
        fim = self.dados.find(b"?>", inicio)
        no = PI(alvo, dados, inicio, fim + 2 if fim >= 0 else inicio)
        if self.pilha:
            self.pilha[-1].filhos.append(no)

    # -- execução ---------------------------------------------------------

    def executar(self) -> No:
        try:
            self.p.Parse(self.dados, True)
        except expat.ExpatError as erro:
            raise ErroDeXhtml(erro.lineno, erro.offset + 1, expat.errors.messages.get(erro.code, str(erro))
                              if hasattr(expat, "errors") else str(erro)) from None
        if self.raiz is None:
            raise ErroDeXhtml(1, 1, "documento sem elemento raiz")
        return self.raiz


def _preparar(texto: str | bytes) -> tuple[bytes, str]:
    """Os bytes que o `expat` recebe, e a codificação para decodificar as fatias."""
    dados = texto.encode("utf-8") if isinstance(texto, str) else bytes(texto)
    codificacao = "utf-8"
    cabeca = _RE_DECLARACAO.match(dados)
    if cabeca:
        declarado = _RE_ENCODING.search(cabeca.group(0))
        if declarado:
            codificacao = declarado.group(1).decode("ascii")
        # `standalone="yes"` faz o expat recusar as entidades da DTD estrangeira.
        sem_standalone = _RE_STANDALONE.sub(b"", cabeca.group(0))
        dados = sem_standalone + dados[cabeca.end():]
    return dados, codificacao


def analisar(texto: str | bytes) -> Documento:
    """A árvore de um documento (ou fragmento embrulhado) com as fatias em bytes."""
    dados, codificacao = _preparar(texto)
    analisador = _Analisador(dados)
    raiz = analisador.executar()
    return Documento(raiz, dados, codificacao, dict(analisador.namespaces))


def bem_formado(texto: str | bytes) -> ErroDeXhtml | None:
    """`None` se o XML é bem-formado com todo prefixo declarado; senão o erro, com linha e coluna."""
    try:
        analisar(texto)
    except ErroDeXhtml as erro:
        return erro
    return None


# ----------------------------------------------------------------------
# Leitura: árvore → modelo
# ----------------------------------------------------------------------

class _Leitor:
    def __init__(self, doc: Documento, arquivo: str):
        self.doc = doc
        self.arquivo = arquivo
        self.pasta = posixpath.dirname(arquivo)
        self.avisos: list[str] = []
        self.ids_referenciados: set[str] = set()

    # -- utilidades -------------------------------------------------------

    def _href(self, valor: str) -> str:
        """
        `href` relativo ao capítulo → relativo ao OPF (a convenção do modelo), e sem a
        codificação de URL: `cap%201.xhtml` é o arquivo `cap 1.xhtml` do zip (ED-01).
        """
        if not valor or "://" in valor or valor.startswith(("#", "mailto:", "data:")):
            return valor
        caminho, _, ancora = valor.partition("#")
        caminho = unquote(caminho)
        if self.pasta:
            caminho = posixpath.normpath(posixpath.join(self.pasta, caminho))
        return caminho + ("#" + ancora if ancora else "")

    def _ilha(self, no: No | Comentario | PI) -> IlhaBruta:
        elemento = no.nome if isinstance(no, No) else ("!--" if isinstance(no, Comentario) else "?" + no.alvo)
        # A referência nomeada vira numérica já aqui: o EPUB 3 não a aceita, e um
        # modelo que a guardasse divergiria do arquivo a cada gravação (DEC-07).
        return IlhaBruta(xhtml=_entidades_numericas(self.doc.cru(no)), elemento=elemento,
                         linha_fonte=no.linha if isinstance(no, No) else None)

    def _atributos(self, no: No, permitidos: Sequence[str] = ()) -> tuple[dict[str, str], bool]:
        """`(extras, ok)`: os atributos conhecidos preservados; `ok` falso se há desconhecido."""
        extras: dict[str, str] = {}
        for chave, valor in no.attrs.items():
            if chave in ("id", "class") or chave in permitidos or chave in dialeto.ATRIBUTOS_DE_ORIGEM:
                continue
            if chave in dialeto.ATRIBUTOS_CONHECIDOS:
                extras[chave] = valor
                continue
            return extras, False
        return extras, True

    def _base(self, no: No, extras: dict[str, str]) -> dict[str, Any]:
        """Os campos de `Bloco` a partir dos atributos."""
        base: dict[str, Any] = {"extras": extras, "linha_fonte": no.linha}
        if "id" in no.attrs:
            base["id"] = no.attrs["id"]
            base["id_persistente"] = not modelo.id_gerado(no.attrs["id"])
        origem = dialeto.origem_de_atributos(no.attrs)
        if origem is not None:
            base["origem"] = origem
        if no.attrs.get("data-suspeito"):
            extras["data-suspeito"] = no.attrs["data-suspeito"]
        return base

    def _estilo_direto(self, valor: str) -> dict[str, str] | None:
        """As declarações de um `style`, ou `None` se alguma não é do dialeto."""
        declaracoes: dict[str, str] = {}
        for parte in valor.split(";"):
            if not parte.strip():
                continue
            nome, _, dado = parte.partition(":")
            nome, dado = nome.strip().lower(), dado.strip()
            if not dado:
                return None
            declaracoes[nome] = dado
        return declaracoes

    # -- documento --------------------------------------------------------

    def capitulo(self) -> Capitulo:
        raiz = self.doc.raiz
        if raiz.nome != "html":
            raise ErroDeXhtml(raiz.linha, 1, f"o elemento raiz é <{raiz.nome}>, não <html>")
        cap = Capitulo(arquivo=self.arquivo or "capitulo.xhtml")
        cap.idioma = raiz.attrs.get("xml:lang") or raiz.attrs.get("lang") or ""
        cap.namespaces = {p: u for p, u in self.doc.namespaces.items()
                          if u not in (NS_XHTML, NS_EPUB) and PREFIXOS_CONHECIDOS.get(p) != u}
        cabeca = next((e for e in raiz.elementos() if e.nome == "head"), None)
        corpo = next((e for e in raiz.elementos() if e.nome == "body"), None)
        if cabeca is not None:
            self._cabeca(cabeca, cap)
        if corpo is None:
            raise ErroDeXhtml(raiz.linha, 1, "documento sem <body>")
        cap.semantica = corpo.attrs.get("epub:type", "")
        self._corpo(corpo, cap)
        self._marcar_referenciados(cap)
        titulo = cap.titulo
        cap.titulo = ""
        if titulo != cap.titulo_efetivo:
            cap.titulo = titulo      # só um <title> que não é o que se deduziria é próprio
        cap.avisos.extend(self.avisos)
        return cap

    def _cabeca(self, cabeca: No, cap: Capitulo) -> None:
        extra: list[str] = []
        for filho in cabeca.filhos:
            if isinstance(filho, Texto):
                continue
            if isinstance(filho, No) and filho.nome == "title":
                cap.titulo = filho.texto().strip()
            elif (isinstance(filho, No) and filho.nome == "link"
                  and filho.attrs.get("rel", "").lower() == "stylesheet" and filho.attrs.get("href")):
                cap.folhas.append(self._href(filho.attrs["href"]))
            else:
                extra.append(self.doc.cru(filho))
        cap.cabeca_extra = "\n".join(extra)

    def _corpo(self, corpo: No, cap: Capitulo) -> None:
        for filho in corpo.filhos:
            if isinstance(filho, Texto):
                if filho.texto.strip():
                    cap.blocos.append(Paragrafo(trechos=[Trecho(texto=filho.texto.strip())]))
                    self.avisos.append("texto solto no <body> virou parágrafo")
                continue
            if isinstance(filho, (Comentario, PI)):
                cap.blocos.append(self._ilha(filho))
                continue
            nota = self._nota(filho)
            if nota is not None:
                cap.notas.extend(nota)
                continue
            cap.blocos.append(self.bloco(filho))

    def _marcar_referenciados(self, cap: Capitulo) -> None:
        """Um id gerado que algum link ou nota aponta passa a ser persistente."""
        for trecho in modelo.trechos_do_capitulo(cap):
            if trecho.nota:
                self.ids_referenciados.add(trecho.nota)
            if trecho.link.startswith("#"):
                self.ids_referenciados.add(trecho.link[1:])
            elif trecho.link:
                arquivo, _, anc = trecho.link.partition("#")
                if anc and arquivo == cap.arquivo:
                    self.ids_referenciados.add(anc)
        for bloco in modelo.blocos_do_capitulo(cap):
            if bloco.id in self.ids_referenciados:
                bloco.id_persistente = True

    # -- notas ------------------------------------------------------------

    def _nota(self, no: No) -> list[Nota] | None:
        tipo = no.attrs.get("epub:type", "")
        if no.nome == "aside" and "footnote" in tipo.split():
            blocos = self._paragrafos_de(no, "nota")
            if blocos is None:
                return None
            return [Nota(id=no.attrs.get("id", modelo.id_novo()), tipo="rodape", blocos=blocos)]
        if no.nome == "section" and "endnotes" in tipo.split():
            notas: list[Nota] = []
            for lista in no.elementos():
                if lista.nome != "ol":
                    return None
                for item in lista.elementos():
                    if item.nome != "li" or "endnote" not in item.attrs.get("epub:type", "").split():
                        return None
                    blocos = self._paragrafos_de(item, "nota")
                    if blocos is None:
                        return None
                    notas.append(Nota(id=item.attrs.get("id", modelo.id_novo()), tipo="fim", blocos=blocos))
            return notas
        return None

    def _paragrafos_de(self, no: No, estilo: str = "corpo") -> list[Paragrafo] | None:
        """
        Os `<p>` de um contêiner — ou o conteúdo inline como um parágrafo só; `None` se
        há outra coisa. `estilo` é o do contêiner (`citacao`, `nota`), que o `<p>` de
        dentro não declara em classe.
        """
        elementos = no.elementos()
        if elementos and all(e.nome == "p" for e in elementos):
            if any(isinstance(f, Texto) and f.texto.strip() for f in no.filhos):
                return None
            saida = []
            for e in elementos:
                bloco = self.bloco(e)
                if not isinstance(bloco, Paragrafo):
                    return None
                if bloco.estilo == "corpo":
                    bloco.estilo = estilo
                saida.append(bloco)
            return saida
        if all(isinstance(f, Texto) or (isinstance(f, No) and f.nome in ELEMENTOS_INLINE) for f in no.filhos):
            return [Paragrafo(trechos=self.trechos(no), estilo=estilo)]
        return None

    # -- blocos -----------------------------------------------------------

    def bloco(self, no: No) -> Bloco:
        nome = no.nome
        if nome == "p" or re.fullmatch(r"h[1-6]", nome):
            return self._paragrafo(no)
        if nome in ("ol", "ul"):
            return self._lista(no)
        if nome == "table":
            return self._tabela(no)
        if nome == "figure":
            return self._figura(no)
        if nome == "div" and "diagrama" in no.classes:
            return self._diagrama_de_div(no, {}, {})
        if nome == "blockquote":
            return self._citacao(no)
        if nome == "hr":
            return self._hr(no)
        return self._ilha(no)

    def _paragrafo(self, no: No) -> Bloco:
        extras, ok = self._atributos(no, ("style",))
        if not ok:
            return self._ilha(no)
        campos = self._base(no, extras)
        classes = no.classes
        estilo = "corpo"
        restantes = []
        for classe in classes:
            if no.nome == "p" and classe in dialeto.ESTILO_DA_CLASSE and estilo == "corpo":
                estilo = dialeto.ESTILO_DA_CLASSE[classe]
            else:
                restantes.append(classe)
        campos["classe"] = " ".join(restantes)
        if "style" in no.attrs:
            direto = self._estilo_direto(no.attrs["style"])
            if direto is None or not self._formatacao_de_paragrafo(direto, campos):
                return self._ilha(no)
        trechos = self.trechos(no)
        if no.nome == "p":
            return Paragrafo(trechos=trechos, estilo=estilo, **campos)
        return Titulo(trechos=trechos, nivel=int(no.nome[1]), **campos)

    def _formatacao_de_paragrafo(self, direto: dict[str, str], campos: dict[str, Any]) -> bool:
        """Traduz as propriedades da §6.1 para os campos do parágrafo; falso se há outra."""
        for nome, valor in direto.items():
            if nome == "text-align" and valor in dialeto.ALINHAMENTO_DO_CSS:
                campos["alinhamento"] = dialeto.ALINHAMENTO_DO_CSS[valor]
            elif nome in ("text-indent", "margin-left", "margin-right", "margin-top", "margin-bottom"):
                numero = _em(valor)
                if numero is None:
                    return False
                campos[{"text-indent": "recuo_primeira_em", "margin-left": "recuo_esquerda_em",
                        "margin-right": "recuo_direita_em", "margin-top": "antes_em",
                        "margin-bottom": "depois_em"}[nome]] = numero
            elif nome == "line-height":
                try:
                    campos["entrelinha"] = float(valor)
                except ValueError:
                    return False
            elif nome == "page-break-after" and valor == "avoid":
                campos["manter_com_proximo"] = True
            elif nome == "page-break-inside" and valor == "avoid":
                campos["manter_linhas"] = True
            else:
                return False
        return True

    def _lista(self, no: No) -> Bloco:
        extras, ok = self._atributos(no, ("start", "style"))
        if not ok:
            return self._ilha(no)
        campos = self._base(no, extras)
        campos["classe"] = " ".join(no.classes)
        marcador = ""
        if "style" in no.attrs:
            direto = self._estilo_direto(no.attrs["style"])
            if direto is None or set(direto) - {"list-style-type"}:
                return self._ilha(no)
            marcador = dialeto.MARCADOR_DO_CSS.get(direto.get("list-style-type", ""), "")
            if direto.get("list-style-type") and not marcador:
                return self._ilha(no)
        itens: list[ItemDeLista] = []
        for filho in no.filhos:
            if isinstance(filho, Texto) and not filho.texto.strip():
                continue
            if not isinstance(filho, No) or filho.nome != "li":
                return self._ilha(no)
            item = self._item(filho)
            if item is None:
                return self._ilha(no)
            itens.append(item)
        try:
            inicio = int(no.attrs.get("start", "1"))
        except ValueError:
            return self._ilha(no)
        return Lista(ordenada=no.nome == "ol", itens=itens, inicio=inicio, marcador=marcador, **campos)

    def _item(self, li: No) -> ItemDeLista | None:
        if li.attrs and set(li.attrs) - {"id", "class"}:
            return None
        elementos = li.elementos()
        filhos_de_bloco = [e for e in elementos if e.nome in ("p", "ol", "ul")]
        if not elementos or len(filhos_de_bloco) != len(elementos):
            if all(isinstance(f, Texto) or (isinstance(f, No) and f.nome in ELEMENTOS_INLINE) for f in li.filhos):
                return ItemDeLista(paragrafos=[Paragrafo(trechos=self.trechos(li))])
            return None
        if any(isinstance(f, Texto) and f.texto.strip() for f in li.filhos):
            return None
        paragrafos: list[Paragrafo] = []
        filhos: Lista | None = None
        for e in elementos:
            if e.nome == "p":
                if filhos is not None:
                    return None
                bloco = self.bloco(e)
                if not isinstance(bloco, Paragrafo):
                    return None
                paragrafos.append(bloco)
            else:
                if filhos is not None:
                    return None
                sub = self._lista(e)
                if not isinstance(sub, Lista):
                    return None
                filhos = sub
        if not paragrafos:
            paragrafos = [Paragrafo(trechos=[])]
        return ItemDeLista(paragrafos=paragrafos, filhos=filhos)

    def _tabela(self, no: No) -> Bloco:
        extras, ok = self._atributos(no, ("style", "data-numero"))
        if not ok:
            return self._ilha(no)
        campos = self._base(no, extras)
        campos["classe"] = " ".join(no.classes)
        largura = None
        if "style" in no.attrs:
            direto = self._estilo_direto(no.attrs["style"])
            if direto is None or set(direto) - {"width"}:
                return self._ilha(no)
            largura = _pct(direto.get("width", ""))
            if direto.get("width") and largura is None:
                return self._ilha(no)
        legenda: list[Trecho] = []
        filas: list[list[Celula]] = []
        cabecalho = False
        for filho in no.filhos:
            if isinstance(filho, Texto) and not filho.texto.strip():
                continue
            if not isinstance(filho, No):
                return self._ilha(no)
            if filho.nome == "caption":
                legenda = self.trechos(filho)
            elif filho.nome in ("thead", "tbody", "tfoot"):
                for tr in filho.filhos:
                    if isinstance(tr, Texto) and not tr.texto.strip():
                        continue
                    if not isinstance(tr, No) or tr.nome != "tr":
                        return self._ilha(no)
                    fila = self._fila(tr)
                    if fila is None:
                        return self._ilha(no)
                    if filho.nome == "thead" and not filas:
                        cabecalho = True
                    filas.append(fila)
            elif filho.nome == "tr":
                fila = self._fila(filho)
                if fila is None:
                    return self._ilha(no)
                filas.append(fila)
            else:
                return self._ilha(no)
        if not filas or len({len(f) for f in filas}) != 1:
            return self._ilha(no)
        numero = no.attrs.get("data-numero", "")
        return Tabela(filas=filas, primeira_fila_cabecalho=cabecalho or all(c.cabecalho for c in filas[0]),
                      legenda=legenda, numero=int(numero) if numero.isdigit() else None,
                      largura_pct=largura, **campos)

    def _fila(self, tr: No) -> list[Celula] | None:
        if set(tr.attrs) - {"id", "class"}:
            return None
        celulas: list[Celula] = []
        for filho in tr.filhos:
            if isinstance(filho, Texto) and not filho.texto.strip():
                continue
            if not isinstance(filho, No) or filho.nome not in ("td", "th"):
                return None
            if set(filho.attrs) - {"id", "class", "style"}:
                return None
            alinhamento = ""
            if "style" in filho.attrs:
                direto = self._estilo_direto(filho.attrs["style"])
                if direto is None or set(direto) - {"text-align"}:
                    return None
                alinhamento = dialeto.ALINHAMENTO_DO_CSS.get(direto.get("text-align", ""), "")
            blocos = [] if not filho.filhos else self._paragrafos_de(filho)
            if blocos is None:
                return None
            celulas.append(Celula(blocos=blocos, cabecalho=filho.nome == "th", alinhamento=alinhamento))
        return celulas

    def _figura(self, no: No) -> Bloco:
        extras, ok = self._atributos(no, ("style", "data-numero") + dialeto.ATRIBUTOS_DE_DIAGRAMA)
        if not ok:
            return self._ilha(no)
        campos = self._base(no, extras)
        elementos = no.elementos()
        if any(isinstance(f, Texto) and f.texto.strip() for f in no.filhos):
            return self._ilha(no)
        legenda_no = next((e for e in elementos if e.nome == "figcaption"), None)
        legenda = self.trechos(legenda_no) if legenda_no is not None else []
        conteudo = [e for e in elementos if e.nome != "figcaption"]
        if len(conteudo) != 1:
            return self._ilha(no)
        miolo = conteudo[0]
        numero = no.attrs.get("data-numero", "")
        campos["classe"] = " ".join(c for c in no.classes if c not in ("diagrama",) + tuple(dialeto.CLASSES_DE_FIGURA))
        if "data-fen" in no.attrs:
            if extras.get("title") == no.attrs["data-fen"]:
                extras.pop("title")      # é o `title` que `escrever` põe, não um do usuário
            try:
                d = dialeto.diagrama_de_atributos(no.attrs, legenda=legenda, **campos)
            except ValueError as erro:
                self.avisos.append(f"diagrama com atributos inválidos virou ilha: {erro}")
                return self._ilha(no)
            alt = miolo.attrs.get("alt", "") if miolo.nome == "img" else miolo.attrs.get("aria-label", "")
            d.alt = "" if alt in ("", d.fen, alt_de(d), alt_de(d, "en")) else alt
            if miolo.nome == "img":
                self._imagem_do_diagrama(d, miolo.attrs.get("src", ""))
            return d
        if miolo.nome == "div" and "diagrama" in miolo.classes:
            return self._diagrama_de_div(miolo, campos, {"legenda": legenda})
        if miolo.nome != "img":
            return self._ilha(no)
        if set(miolo.attrs) - {"src", "alt", "style", "title", "id", "class"}:
            return self._ilha(no)
        alt = miolo.attrs.get("alt", "")
        fen_do_alt, lado_do_alt = lado_a_jogar.do_alt(alt)
        if modelo.fen_valido(fen_do_alt):
            # O EPUB de hoje escreve o FEN no `alt` (`exportar._alternativo`): é um
            # diagrama, e a orientação não foi registrada (DEC-06). O lado a jogar
            # passou a ir junto desde o item 3 da revisão de 2026-09-18, com a
            # procedência — e `do_alt` só o devolve quando ele foi **lido**: o que
            # o escritor declarou convenção não pode voltar como leitura.
            d = Diagrama(fen=fen_do_alt, lado=lado_do_alt, estado="revisar",
                         aviso="orientação não registrada",
                         legenda=legenda, numero=int(numero) if numero.isdigit() else None, **campos)
            self._imagem_do_diagrama(d, miolo.attrs.get("src", ""))
            return d
        largura = None
        if "style" in miolo.attrs:
            direto = self._estilo_direto(miolo.attrs["style"])
            if direto is None or set(direto) - {"width"}:
                return self._ilha(no)
            largura = _pt(direto.get("width", ""))
        alinhamento = next((c for c in no.classes if c in dialeto.CLASSES_DE_FIGURA), "centro")
        if not alt:
            self.avisos.append(f"figura {miolo.attrs.get('src', '?')} sem alt")
        return Figura(recurso=self._href(miolo.attrs.get("src", "")) or "?", alt=alt, legenda=legenda,
                      numero=int(numero) if numero.isdigit() else None, largura_pt=largura,
                      alinhamento=alinhamento, **campos)

    def _imagem_do_diagrama(self, d: Diagrama, src: str) -> None:
        """
        Guarda em `d.imagem` o PNG que já desenha este diagrama, quando o nome dele não é
        o canônico `diag-<chave>.png` — é o `fig-0001-1.png` do EPUB de hoje. Com o nome
        canônico não há o que guardar: o escritor o regenera igual.
        """
        href = self._href(src)
        if not href or "://" in href or href.startswith("data:"):
            return
        chave = dialeto.chave_do_diagrama(d)
        if posixpath.basename(href) == posixpath.basename(dialeto.nome_do_png(d)):
            return
        d.imagem, d.imagem_chave = href, chave

    def _diagrama_de_div(self, div: No, campos: dict[str, Any], resto: dict[str, Any]) -> Bloco:
        try:
            return diagrama_de_div(div, **campos, **resto)
        except (ValueError, KeyError) as erro:
            self.avisos.append(f"diagrama em texto que não deu para ler virou ilha: {erro}")
            return self._ilha(div)

    def _citacao(self, no: No) -> Bloco:
        extras, ok = self._atributos(no)
        if not ok:
            return self._ilha(no)
        blocos = self._paragrafos_de(no, "citacao")
        if blocos is None:
            return self._ilha(no)
        campos = self._base(no, extras)
        campos["classe"] = " ".join(no.classes)
        return Citacao(blocos=blocos, **campos)

    def _hr(self, no: No) -> Bloco:
        extras, ok = self._atributos(no, ("style", "data-pagina"))
        if not ok:
            return self._ilha(no)
        campos = self._base(no, extras)
        classes = no.classes
        if "pagina" in classes:
            pagina = no.attrs.get("data-pagina") or no.attrs.get("aria-label") or ""
            if not pagina.isdigit():
                casamento = _RE_PAGINA.match(no.attrs.get("id", ""))
                if not casamento:
                    return self._ilha(no)
                pagina = casamento.group(1)
            campos["extras"] = {k: v for k, v in extras.items() if k not in ("epub:type", "role", "aria-label")}
            campos["classe"] = " ".join(c for c in classes if c != "pagina")
            return MarcaDePagina(pagina=int(pagina), **campos)
        if "style" in no.attrs and "page-break" not in no.attrs["style"]:
            return self._ilha(no)
        if "quebra" in classes or "page-break" in no.attrs.get("style", ""):
            campos["classe"] = " ".join(c for c in classes if c != "quebra")
            return QuebraDePagina(**campos)
        campos["classe"] = " ".join(classes)
        return Separador(**campos)

    # -- trechos ----------------------------------------------------------

    def trechos(self, no: No) -> list[Trecho]:
        saida: list[Trecho] = []
        pendente: dict[str, Any] = {"quebra_antes": False, "pagina": None}
        self._inline(no, Trecho(), saida, pendente)
        if pendente["quebra_antes"] or pendente["pagina"] is not None:
            saida.append(Trecho(quebra_antes=pendente["quebra_antes"], pagina=pendente["pagina"]))
        return modelo.trechos_normalizados(saida)

    def _inline(self, no: No, estado: Trecho, saida: list[Trecho], pendente: dict[str, Any]) -> None:
        for filho in no.filhos:
            if isinstance(filho, Texto):
                trecho = _copia(estado)
                trecho.texto = filho.texto
                self._aplicar_pendente(trecho, pendente)
                saida.append(trecho)
            elif isinstance(filho, (Comentario, PI)):
                saida.append(self._ilha_inline(self.doc.cru(filho), estado, pendente))
            elif filho.nome == "br" and not filho.attrs:
                if pendente["quebra_antes"]:
                    saida.append(Trecho(quebra_antes=True))
                pendente["quebra_antes"] = True
            else:
                novo = self._estado_de(filho, estado)
                if novo is None:
                    saida.append(self._ilha_inline(self.doc.cru(filho), estado, pendente))
                    continue
                if novo == "nota":
                    trecho = _copia(estado)
                    trecho.nota = filho.attrs.get("href", "").lstrip("#")
                    self._aplicar_pendente(trecho, pendente)
                    saida.append(trecho)
                    continue
                if novo == "pagina":
                    pagina = filho.attrs.get("aria-label") or _RE_PAGINA.sub(r"\1", filho.attrs.get("id", ""))
                    if not pagina.isdigit():
                        saida.append(self._ilha_inline(self.doc.cru(filho), estado, pendente))
                        continue
                    pendente["pagina"] = int(pagina)
                    continue
                self._inline(filho, novo, saida, pendente)

    def _aplicar_pendente(self, trecho: Trecho, pendente: dict[str, Any]) -> None:
        trecho.quebra_antes = pendente["quebra_antes"]
        trecho.pagina = pendente["pagina"]
        pendente["quebra_antes"] = False
        pendente["pagina"] = None

    def _ilha_inline(self, cru: str, estado: Trecho, pendente: dict[str, Any]) -> Trecho:
        trecho = Trecho(ilha=_entidades_numericas(cru))
        self._aplicar_pendente(trecho, pendente)
        return trecho

    def _estado_de(self, no: No, estado: Trecho) -> Trecho | str | None:
        """O estado dentro deste elemento inline; `"nota"`/`"pagina"` para os marcos; `None` = ilha."""
        nome = dialeto.SINONIMOS_INLINE.get(no.nome, no.nome)
        novo = _copia(estado)
        attrs = dict(no.attrs)
        # `lang`, `xml:lang` e `title` valem em qualquer inline; o resto depende do elemento.
        if "xml:lang" in attrs or "lang" in attrs:
            novo.lang = attrs.pop("xml:lang", None) or attrs.pop("lang", "")
            attrs.pop("lang", None)
        if "title" in attrs:
            novo.titulo = attrs.pop("title")
        if nome in ESTILOS_INLINE_SIMPLES:
            if attrs:
                return None
            setattr(novo, ESTILOS_INLINE_SIMPLES[nome], True)
            return novo
        if nome in ("sup", "sub"):
            if attrs:
                return None
            novo.posicao = "sobre" if nome == "sup" else "sub"
            return novo
        if nome == "a":
            tipo = attrs.pop("epub:type", "")
            attrs.pop("role", None)
            if "noteref" in tipo.split():
                # Só a nota do próprio capítulo é `Trecho.nota`; a referência a uma nota
                # noutro arquivo (o Calibre as junta num só) fica ilha, byte a byte (DEC-02).
                return "nota" if attrs.get("href", "").startswith("#") else None
            href = attrs.pop("href", None)
            if href is None or tipo:
                return None
            classes = attrs.pop("class", "").split()
            ref = attrs.pop("data-ref", "")
            if "ref" in classes:
                classes.remove("ref")
            if attrs or classes or (ref and ref not in modelo.REFERENCIAS):
                return None
            novo.link = self._href(href)
            novo.ref = ref
            return novo
        if nome == "span":
            tipo = attrs.pop("epub:type", "")
            if "pagebreak" in tipo.split():
                return "pagina" if not no.filhos or no.so_espaco() else None
            if tipo:
                return None
            attrs.pop("role", None)
            classes = attrs.pop("class", "").split()
            restantes: list[str] = []
            for classe in classes:
                if classe == "sim":
                    novo.familia = "simbolos"
                elif classe == "versalete":
                    novo.versalete = True
                elif classe in dialeto.PAPEL_DA_CLASSE:
                    novo.papel = dialeto.PAPEL_DA_CLASSE[classe]
                elif classe.startswith("fonte-"):
                    novo.familia = classe[len("fonte-"):]
                else:
                    restantes.append(classe)
            novo.classe = " ".join(restantes)
            if "data-nag" in attrs:
                valor = attrs.pop("data-nag")
                if not valor.isdigit():
                    return None
                novo.nag = int(valor)
            for chave in ("data-chave", "data-eco"):
                if chave in attrs:
                    novo.chave = attrs.pop(chave)
            if "style" in attrs:
                direto = self._estilo_direto(attrs.pop("style"))
                if direto is None or not _formatacao_de_trecho(direto, novo):
                    return None
            if attrs:
                return None
            return novo
        return None


def _copia(trecho: Trecho) -> Trecho:
    novo = Trecho(**{k: v for k, v in modelo.para_dict(trecho).items() if k != "tipo"})
    novo.texto = ""
    novo.ilha = ""
    novo.quebra_antes = False
    novo.pagina = None
    novo.nota = ""
    return novo


def _formatacao_de_trecho(direto: dict[str, str], trecho: Trecho) -> bool:
    for nome, valor in direto.items():
        if nome == "font-family":
            trecho.familia = valor.split(",")[0].strip().strip("\"'")
        elif nome == "font-size":
            pt = _pt(valor)
            if pt is None:
                return False
            trecho.corpo_pt = pt
        elif nome == "color":
            trecho.cor = valor
        elif nome == "background-color":
            trecho.fundo = valor
        else:
            return False
    return True


def _em(valor: str) -> float | None:
    valor = valor.strip().lower()
    if valor in ("0", "0em", "0pt", "0px"):
        return 0.0
    if valor.endswith("em"):
        try:
            return float(valor[:-2])
        except ValueError:
            return None
    return None


def _pt(valor: str) -> float | None:
    valor = valor.strip().lower()
    if valor.endswith("pt"):
        try:
            return float(valor[:-2])
        except ValueError:
            return None
    return None


def _pct(valor: str) -> int | None:
    valor = valor.strip()
    if valor.endswith("%") and valor[:-1].isdigit():
        return int(valor[:-1])
    return None


# ----------------------------------------------------------------------
# O diagrama em texto de hoje → `Diagrama`
# ----------------------------------------------------------------------

def diagrama_de_div(div: No, **campos: Any) -> Diagrama:
    """
    O `div.diagrama` nu de `exportar._diagrama_em_texto` (F59/F95/F99) → `Diagrama`.

    O de hoje traz o FEN em `title` e `aria-label` (`exportar._alternativo`): o FEN vem
    daí — com a ressalva do lado a jogar atrás, desde o item 3 da revisão de
    2026-09-18 —, e a orientação é a que **reproduz** as linhas lidas. Só um `div` de fora, sem
    `title` que seja FEN, passa pelas linhas (`render_diagrama.fen_de_linhas`), com a
    orientação dos `span.rot` (a primeira fila rotulada `1` é o lado das pretas) ou dos
    glifos de moldura; sem nenhum dos dois é `estado="revisar"` (DEC-06).
    """
    from core import render_diagrama

    fonte = next((c[len("fonte-"):] for c in div.classes if c.startswith("fonte-")), modelo.FONTE_PADRAO)
    titulo, lado_do_titulo = lado_a_jogar.do_alt(
        div.attrs.get("title", "") or div.attrs.get("aria-label", ""))
    linhas: list[str] = []
    rotulos: list[str] = []
    coordenadas = False
    for p in div.elementos():
        if p.nome != "p":
            raise ValueError(f"<{p.nome}> dentro do diagrama")
        if "colunas" in p.classes:
            coordenadas = True
            continue
        texto = ""
        for filho in p.filhos:
            if isinstance(filho, Texto):
                texto += filho.texto
            elif isinstance(filho, No) and filho.nome == "span" and "rot" in filho.classes:
                rotulos.append(filho.texto().strip())
                coordenadas = True
            elif isinstance(filho, No) and filho.nome == "span" and "col" in filho.classes:
                continue
            else:
                raise ValueError(f"<{getattr(filho, 'nome', '?')}> dentro da linha do diagrama")
        linhas.append(texto.strip("\n"))
    emolduradas = len(linhas) == 10
    estado, aviso = "ok", ""
    if modelo.fen_valido(titulo):
        fen = modelo.fen_completo(titulo)
        mapa = render_diagrama.mapa_da_fonte(fonte)
        miolo = [linha[1:9] for linha in linhas[1:9]] if emolduradas else linhas
        orientacao = next((o for o in ("branca", "preta")
                           if render_diagrama.linhas(fen, mapa, o) == miolo), None)
        if orientacao is None:
            orientacao, estado, aviso = "branca", "revisar", "as linhas não batem com o FEN do título"
    else:
        posicao, orientacao = render_diagrama.fen_de_linhas(linhas, fonte)
        if orientacao is None and rotulos:
            orientacao = "preta" if rotulos[0] == "1" else "branca"
            if orientacao == "preta":
                # As oito linhas vieram giradas: desgira-se agora que se sabe.
                filas = posicao.split("/")
                posicao = "/".join(_inverter_fila(f) for f in reversed(filas))
        if orientacao is None:
            orientacao, estado, aviso = "branca", "revisar", "orientação não registrada"
        fen = modelo.fen_completo(posicao)
    return Diagrama(fen=fen, lado=lado_do_titulo if modelo.fen_valido(titulo) else "",
                    orientacao=orientacao,
                    coordenadas=coordenadas or emolduradas, fonte=fonte, modo="fonte",
                    moldura="simples" if ("caixa" in div.classes or emolduradas) else "sem",
                    alt="" if modelo.fen_valido(titulo) else titulo, estado=estado, aviso=aviso, **campos)


def _inverter_fila(fila: str) -> str:
    casas: list[str] = []
    for ch in fila:
        casas.extend([""] * int(ch) if ch.isdigit() else [ch])
    saida, vazias = "", 0
    for casa in reversed(casas):
        if casa == "":
            vazias += 1
            continue
        if vazias:
            saida += str(vazias)
            vazias = 0
        saida += casa
    return saida + (str(vazias) if vazias else "")


# ----------------------------------------------------------------------
# Leitura pública
# ----------------------------------------------------------------------

def ler(texto: str | bytes, arquivo: str = "") -> Capitulo:
    """
    Um documento XHTML → `Capitulo`. `arquivo` é o href do capítulo relativo ao OPF
    (é o que torna os `href` de `<link>` e `<img>` relativos ao OPF, como o modelo pede).
    """
    doc = analisar(texto)
    return _Leitor(doc, arquivo).capitulo()


def ler_fragmento(texto: str, arquivo: str = "") -> list[Bloco]:
    """
    Um fragmento (blocos, ou só conteúdo inline) → blocos. É o que "Colar como XHTML"
    e os clipes usam; um fragmento só de inline vira um parágrafo.
    """
    embrulhado = (f'<div xmlns="{NS_XHTML}" xmlns:epub="{NS_EPUB}" '
                  f'xmlns:xlink="{PREFIXOS_CONHECIDOS["xlink"]}">{texto}</div>')
    doc = analisar(embrulhado)
    leitor = _Leitor(doc, arquivo)
    raiz = doc.raiz
    if all(isinstance(f, Texto) or (isinstance(f, No) and f.nome in ELEMENTOS_INLINE) for f in raiz.filhos):
        return [Paragrafo(trechos=leitor.trechos(raiz))]
    blocos: list[Bloco] = []
    for filho in raiz.filhos:
        if isinstance(filho, Texto):
            if filho.texto.strip():
                blocos.append(Paragrafo(trechos=[Trecho(texto=filho.texto.strip())]))
            continue
        if isinstance(filho, (Comentario, PI)):
            blocos.append(leitor._ilha(filho))
            continue
        blocos.append(leitor.bloco(filho))
    return blocos


# ----------------------------------------------------------------------
# Escrita: modelo → XHTML
# ----------------------------------------------------------------------

def _attr(valor: str) -> str:
    return escape(valor, {'"': "&quot;"})


def _atributos_para_texto(attrs: dict[str, str]) -> str:
    return "".join(f' {k}="{_attr(v)}"' for k, v in attrs.items() if v != "" or k in ("alt",))


def _entidades_numericas(cru: str) -> str:
    """Toda referência nomeada de uma ilha vira numérica — o EPUB 3 não aceita a nomeada."""
    def trocar(m: re.Match) -> str:
        nome = m.group(1)
        if nome in ("lt", "gt", "amp", "quot", "apos"):
            return m.group(0)
        valor = html.entities.html5.get(nome + ";")
        if valor is None:
            return m.group(0)
        return "".join(f"&#{ord(c)};" for c in valor)
    return _RE_ENTIDADE_NOMEADA.sub(trocar, cru)


class _Escritor:
    def __init__(self, cap: Capitulo, pasta_de_imagens: str):
        self.cap = cap
        self.pasta_de_imagens = pasta_de_imagens
        self.pasta = posixpath.dirname(cap.arquivo)
        cap.normalizar_notas()
        self.numeros_de_nota = {n.id: i for i, n in enumerate(cap.notas, start=1)}
        self.usa_epub = bool(cap.semantica) or bool(cap.notas)
        self.ilhas: list[str] = []

    # -- utilidades -------------------------------------------------------

    def _href(self, valor: str) -> str:
        """`href` relativo ao OPF → relativo ao capítulo, codificado como URL (um espaço sai `%20`)."""
        if not valor or "://" in valor or valor.startswith(("#", "mailto:", "data:")):
            return valor
        caminho, _, ancora = valor.partition("#")
        if self.pasta:
            caminho = posixpath.relpath(caminho, self.pasta)
        return quote(caminho, safe=SEGUROS_NA_URL) + ("#" + ancora if ancora else "")

    def _ilha(self, cru: str) -> str:
        if "epub:" in cru:
            self.usa_epub = True
        self.ilhas.append(cru)
        return _entidades_numericas(cru)

    def _comuns(self, bloco: Bloco, classe_extra: str = "") -> dict[str, str]:
        attrs: dict[str, str] = {}
        if bloco.id_persistente:
            attrs["id"] = bloco.id
        classes = " ".join(c for c in (classe_extra, bloco.classe) if c)
        if classes:
            attrs["class"] = classes
        for chave in ("lang", "xml:lang", "title", "dir", "epub:type", "role", "aria-label"):
            if chave in bloco.extras:
                attrs[chave] = bloco.extras[chave]
                if chave == "epub:type":
                    self.usa_epub = True
        attrs.update(dialeto.atributos_de_origem(bloco.origem))
        if bloco.extras.get("data-suspeito"):
            attrs["data-suspeito"] = bloco.extras["data-suspeito"]
        return attrs

    # -- documento --------------------------------------------------------

    def documento(self) -> str:
        cap = self.cap
        corpo = "\n".join(self.bloco(b, 0) for b in cap.blocos)
        notas = self.notas()
        linhas_do_corpo = "\n".join(p for p in (corpo, notas) if p)
        cabeca = [f"<title>{escape(cap.titulo_efetivo)}</title>"]
        for folha in cap.folhas:
            cabeca.append(f'<link rel="stylesheet" type="text/css" href="{_attr(self._href(folha))}"/>')
        if cap.cabeca_extra:
            cabeca.append(self._ilha(cap.cabeca_extra))
        raiz = f'<html xmlns="{NS_XHTML}"'
        if self.usa_epub:
            raiz += f' xmlns:epub="{NS_EPUB}"'
        for prefixo, uri in cap.namespaces.items():
            if prefixo != "epub":
                raiz += f' xmlns:{prefixo}="{_attr(uri)}"'
        ilhas = "\n".join(self.ilhas) + "\n" + cap.cabeca_extra
        for prefixo, uri in PREFIXOS_CONHECIDOS.items():
            if prefixo != "epub" and prefixo not in cap.namespaces \
                    and re.search(rf"(?<![\w-]){re.escape(prefixo)}:[A-Za-z]", ilhas):
                raiz += f' xmlns:{prefixo}="{uri}"'
        if cap.idioma:
            raiz += f' lang="{_attr(cap.idioma)}" xml:lang="{_attr(cap.idioma)}"'
        raiz += ">"
        body = "<body" + (f' epub:type="{_attr(cap.semantica)}"' if cap.semantica else "") + ">"
        return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<!DOCTYPE html>\n"
                + raiz + "\n<head>\n" + "\n".join(cabeca) + "\n</head>\n" + body + "\n"
                + linhas_do_corpo + ("\n" if linhas_do_corpo else "") + "</body>\n</html>\n")

    def notas(self) -> str:
        partes: list[str] = []
        rodape = [n for n in self.cap.notas if n.tipo == "rodape"]
        fim = [n for n in self.cap.notas if n.tipo == "fim"]
        for nota in rodape:
            miolo = "\n".join(self.bloco(p, 1) for p in nota.blocos)
            partes.append(f'<aside epub:type="footnote" role="doc-footnote" id="{_attr(nota.id)}">\n'
                          f"{miolo}\n</aside>")
        if fim:
            itens = []
            for nota in fim:
                miolo = "\n".join(self.bloco(p, 2) for p in nota.blocos)
                itens.append(f'  <li epub:type="endnote" id="{_attr(nota.id)}">\n{miolo}\n  </li>')
            partes.append('<section epub:type="endnotes" role="doc-endnotes">\n<ol>\n'
                          + "\n".join(itens) + "\n</ol>\n</section>")
        if partes:
            self.usa_epub = True
        return "\n".join(partes)

    # -- blocos -----------------------------------------------------------

    def bloco(self, bloco: Bloco, nivel: int) -> str:
        recuo = "  " * nivel
        if isinstance(bloco, Titulo):
            return recuo + self._paragrafo(bloco, f"h{bloco.nivel}")
        if isinstance(bloco, Paragrafo):
            return recuo + self._paragrafo(bloco, "p")
        if isinstance(bloco, Lista):
            return self._lista(bloco, nivel)
        if isinstance(bloco, Tabela):
            return self._tabela(bloco, nivel)
        if isinstance(bloco, Diagrama):
            return recuo + self._diagrama(bloco)
        if isinstance(bloco, Figura):
            return recuo + self._figura(bloco)
        if isinstance(bloco, Citacao):
            miolo = "\n".join(self.bloco(p, nivel + 1) for p in bloco.blocos)
            return f"{recuo}<blockquote{_atributos_para_texto(self._comuns(bloco))}>\n{miolo}\n{recuo}</blockquote>"
        if isinstance(bloco, MarcaDePagina):
            attrs = self._comuns(bloco, "pagina")
            attrs.pop("id", None)
            attrs.update({"data-pagina": str(bloco.pagina), "epub:type": "pagebreak",
                          "role": "doc-pagebreak", "id": bloco.id, "aria-label": str(bloco.pagina)})
            self.usa_epub = True
            return f"{recuo}<hr{_atributos_para_texto(attrs)}/>"
        if isinstance(bloco, QuebraDePagina):
            attrs = self._comuns(bloco, "quebra")
            attrs["style"] = "page-break-after: always"
            return f"{recuo}<hr{_atributos_para_texto(attrs)}/>"
        if isinstance(bloco, Separador):
            return f"{recuo}<hr{_atributos_para_texto(self._comuns(bloco))}/>"
        if isinstance(bloco, IlhaBruta):
            return recuo + self._ilha(bloco.xhtml)
        raise TypeError(f"bloco desconhecido: {type(bloco).__name__}")

    def _paragrafo(self, p: Paragrafo, elemento: str) -> str:
        classe_do_estilo = ""
        if not isinstance(p, Titulo) and p.estilo in dialeto.ESTILOS_DE_PARAGRAFO:
            classe_do_estilo = dialeto.ESTILOS_DE_PARAGRAFO[p.estilo][1]
        elif not isinstance(p, Titulo) and p.estilo not in ("corpo", "citacao", "nota"):
            classe_do_estilo = p.estilo
        attrs = self._comuns(p, classe_do_estilo)
        estilo = self._estilo_do_paragrafo(p)
        if estilo:
            attrs["style"] = estilo
        return f"<{elemento}{_atributos_para_texto(attrs)}>{self.trechos(p.trechos)}</{elemento}>"

    def _estilo_do_paragrafo(self, p: Paragrafo) -> str:
        declaracoes: list[str] = []
        if p.alinhamento:
            declaracoes.append(f"text-align: {dialeto.ALINHAMENTO_CSS[p.alinhamento]}")
        for nome, valor in (("text-indent", p.recuo_primeira_em), ("margin-left", p.recuo_esquerda_em),
                            ("margin-right", p.recuo_direita_em), ("margin-top", p.antes_em),
                            ("margin-bottom", p.depois_em)):
            if valor is not None:
                declaracoes.append(f"{nome}: {valor:g}em" if valor else f"{nome}: 0")
        if p.entrelinha is not None:
            declaracoes.append(f"line-height: {p.entrelinha:g}")
        if p.manter_com_proximo:
            declaracoes.append("page-break-after: avoid")
        if p.manter_linhas:
            declaracoes.append("page-break-inside: avoid")
        return "; ".join(declaracoes)

    def _lista(self, lista: Lista, nivel: int) -> str:
        recuo = "  " * nivel
        attrs = self._comuns(lista)
        if lista.ordenada and lista.inicio != 1:
            attrs["start"] = str(lista.inicio)
        if lista.marcador:
            attrs["style"] = f"list-style-type: {dialeto.MARCADOR_CSS[lista.marcador]}"
        elemento = "ol" if lista.ordenada else "ul"
        itens = []
        for item in lista.itens:
            if len(item.paragrafos) == 1 and item.filhos is None and _paragrafo_simples(item.paragrafos[0]):
                itens.append(f"{recuo}  <li>{self.trechos(item.paragrafos[0].trechos)}</li>")
                continue
            partes = [self.bloco(p, nivel + 2) for p in item.paragrafos]
            if item.filhos is not None:
                partes.append(self._lista(item.filhos, nivel + 2))
            itens.append(f"{recuo}  <li>\n" + "\n".join(partes) + f"\n{recuo}  </li>")
        return f"{recuo}<{elemento}{_atributos_para_texto(attrs)}>\n" + "\n".join(itens) + f"\n{recuo}</{elemento}>"

    def _tabela(self, tabela: Tabela, nivel: int) -> str:
        recuo = "  " * nivel
        attrs = self._comuns(tabela)
        if tabela.largura_pct is not None:
            attrs["style"] = f"width: {tabela.largura_pct}%"
        if tabela.numero is not None:
            attrs["data-numero"] = str(tabela.numero)
        partes = [f"{recuo}<table{_atributos_para_texto(attrs)}>"]
        if tabela.legenda:
            partes.append(f"{recuo}  <caption>{self.trechos(tabela.legenda)}</caption>")
        filas = tabela.filas
        if tabela.primeira_fila_cabecalho and filas:
            partes.append(f"{recuo}  <thead>")
            partes.append(self._fila(filas[0], nivel + 2, True))
            partes.append(f"{recuo}  </thead>")
            filas = filas[1:]
        if filas:
            partes.append(f"{recuo}  <tbody>")
            partes.extend(self._fila(fila, nivel + 2, False) for fila in filas)
            partes.append(f"{recuo}  </tbody>")
        partes.append(f"{recuo}</table>")
        return "\n".join(partes)

    def _fila(self, fila: list[Celula], nivel: int, cabecalho: bool) -> str:
        recuo = "  " * nivel
        celulas = []
        for celula in fila:
            elemento = "th" if (celula.cabecalho or cabecalho) else "td"
            attrs = ""
            if celula.alinhamento:
                attrs = f' style="text-align: {dialeto.ALINHAMENTO_CSS[celula.alinhamento]}"'
            if len(celula.blocos) == 1 and _paragrafo_simples(celula.blocos[0]):
                celulas.append(f"{recuo}  <{elemento}{attrs}>{self.trechos(celula.blocos[0].trechos)}</{elemento}>")
            elif not celula.blocos:
                celulas.append(f"{recuo}  <{elemento}{attrs}></{elemento}>")
            else:
                miolo = "\n".join(self.bloco(p, nivel + 2) for p in celula.blocos)
                celulas.append(f"{recuo}  <{elemento}{attrs}>\n{miolo}\n{recuo}  </{elemento}>")
        return f"{recuo}<tr>\n" + "\n".join(celulas) + f"\n{recuo}</tr>"

    def _figura(self, figura: Figura) -> str:
        attrs = self._comuns(figura, figura.alinhamento if figura.alinhamento != "centro" else "")
        if figura.numero is not None:
            attrs["data-numero"] = str(figura.numero)
        img: dict[str, str] = {"src": self._href(figura.recurso), "alt": figura.alt}
        if figura.largura_pt is not None:
            img["style"] = f"width: {figura.largura_pt:g}pt"
        legenda = f"<figcaption>{self.trechos(figura.legenda)}</figcaption>" if figura.legenda else ""
        return f"<figure{_atributos_para_texto(attrs)}><img{_atributos_para_texto(img)}/>{legenda}</figure>"

    def _diagrama(self, d: Diagrama) -> str:
        attrs = self._comuns(d, "diagrama")
        attrs.update(dialeto.atributos_de_diagrama(d))
        attrs["title"] = d.fen
        alt = d.alt or alt_de(d)
        legenda = f"<figcaption>{self.trechos(d.legenda)}</figcaption>" if d.legenda else ""
        if d.modo == "fonte":
            miolo = self._diagrama_em_texto(d, alt)
            return f"<figure{_atributos_para_texto(attrs)}>\n{miolo}\n{legenda}</figure>"
        img = {"src": self._href(imagem_do_diagrama(d, self.pasta_de_imagens)), "alt": alt}
        largura = largura_do_png_pt(d)
        if largura is not None:
            # A largura vai no próprio `img`, como no EPUB de hoje (F97): o corpo por
            # casa é do diagrama, e quantas casas a figura tem depende da moldura e
            # das coordenadas.
            img["style"] = f"width: {largura:g}pt"
        return f"<figure{_atributos_para_texto(attrs)}><img{_atributos_para_texto(img)}/>{legenda}</figure>"

    def _diagrama_em_texto(self, d: Diagrama, alt: str) -> str:
        from core import render_diagrama

        fonte = render_diagrama.mapa_da_fonte(d.fonte)
        linhas = None
        emolduradas = False
        if d.coordenadas and d.moldura != "sem":
            linhas = render_diagrama.grade(d.fen, fonte, d.orientacao, d.moldura, d.cantos)
            emolduradas = linhas is not None
        if linhas is None:
            linhas = render_diagrama.linhas(d.fen, fonte, d.orientacao)
        return dialeto.div_do_diagrama(linhas, d.fonte, coordenadas=d.coordenadas, orientacao=d.orientacao,
                                       emolduradas=emolduradas, alt=alt, escapar=escape)

    # -- trechos ----------------------------------------------------------

    def trechos(self, trechos: Sequence[Trecho]) -> str:
        partes: list[str] = []
        for trecho in trechos:
            if trecho.pagina is not None:
                partes.append(f'<span epub:type="pagebreak" role="doc-pagebreak" id="pg-{trecho.pagina}" '
                              f'aria-label="{trecho.pagina}"/>')
                self.usa_epub = True
            if trecho.quebra_antes:
                partes.append("<br/>")
            if trecho.ilha:
                partes.append(self._ilha(trecho.ilha))
                continue
            if trecho.nota:
                numero = self.numeros_de_nota.get(trecho.nota, 0)
                partes.append(f'<a epub:type="noteref" role="doc-noteref" href="#{_attr(trecho.nota)}">'
                              f"<sup>{numero}</sup></a>")
                self.usa_epub = True
                continue
            if trecho.texto:
                partes.append(self._trecho(trecho))
        return "".join(partes)

    def _trecho(self, t: Trecho) -> str:
        texto = escape(t.texto)
        camadas: list[tuple[str, str]] = []   # (abertura, fechamento), de fora para dentro
        if t.link:
            attrs: dict[str, str] = {}
            if t.ref:
                attrs["class"] = "ref"
                attrs["data-ref"] = t.ref
            attrs["href"] = self._href(t.link)
            camadas.append((f"<a{_atributos_para_texto(attrs)}>", "</a>"))
        span = self._span(t)
        if span:
            camadas.append((f"<span{span}>", "</span>"))
        for atributo, elemento in (("negrito", "strong"), ("italico", "em"), ("sublinhado", "u"),
                                   ("tachado", "s")):
            if getattr(t, atributo):
                camadas.append((f"<{elemento}>", f"</{elemento}>"))
        if t.posicao:
            elemento = "sup" if t.posicao == "sobre" else "sub"
            camadas.append((f"<{elemento}>", f"</{elemento}>"))
        if t.codigo:
            camadas.append(("<code>", "</code>"))
        abre = "".join(a for a, _ in camadas)
        fecha = "".join(f for _, f in reversed(camadas))
        return abre + texto + fecha

    def _span(self, t: Trecho) -> str:
        classes: list[str] = []
        if t.familia == "simbolos":
            classes.append("sim")
        if t.papel in dialeto.CLASSE_DO_PAPEL:
            classes.append(dialeto.CLASSE_DO_PAPEL[t.papel])
        if t.versalete:
            classes.append("versalete")
        if t.familia and t.familia != "simbolos" and _e_fonte_de_diagrama(t.familia):
            classes.append(dialeto.classe_da_fonte(t.familia))
        if t.classe:
            classes.extend(t.classe.split())
        attrs: dict[str, str] = {}
        if classes:
            attrs["class"] = " ".join(classes)
        if t.papel == "nag" and t.nag is not None:
            attrs["data-nag"] = str(t.nag)
        if t.papel == "jogador" and t.chave:
            attrs["data-chave"] = t.chave
        if t.papel == "abertura" and t.chave:
            attrs["data-eco"] = t.chave
        if t.lang:
            attrs["lang"] = t.lang
            attrs["xml:lang"] = t.lang
        if t.titulo:
            attrs["title"] = t.titulo
        declaracoes: list[str] = []
        if t.familia and t.familia != "simbolos" and not _e_fonte_de_diagrama(t.familia):
            declaracoes.append(f'font-family: "{t.familia}"')
        if t.corpo_pt is not None:
            declaracoes.append(f"font-size: {t.corpo_pt:g}pt")
        if t.cor:
            declaracoes.append(f"color: {t.cor}")
        if t.fundo:
            declaracoes.append(f"background-color: {t.fundo}")
        if declaracoes:
            attrs["style"] = "; ".join(declaracoes)
        return _atributos_para_texto(attrs)


def _paragrafo_simples(p: Paragrafo) -> bool:
    """Um `<li>`/`<td>` pode levar o conteúdo inline direto quando o parágrafo não tem nada próprio."""
    return (type(p) is Paragrafo and p.estilo == "corpo" and not p.classe and not p.extras
            and not p.id_persistente and p.origem is None and not p.alinhamento
            and all(getattr(p, campo) is None for campo in ("recuo_primeira_em", "recuo_esquerda_em",
                                                            "recuo_direita_em", "antes_em", "depois_em",
                                                            "entrelinha"))
            and not p.manter_com_proximo and not p.manter_linhas)


_FONTES_DE_DIAGRAMA_CONHECIDAS = ("SkakNew-Diagram", "ChessMerida-Diagram")


def _e_fonte_de_diagrama(familia: str) -> bool:
    """Sem abrir o `fitz`: os nomes que o mapa de `render_diagrama` conhece hoje, mais o padrão."""
    return familia in _FONTES_DE_DIAGRAMA_CONHECIDAS or familia.endswith("-Diagram")


alt_de = dialeto.alt_de


def imagem_do_diagrama(d: Diagrama, pasta_de_imagens: str = "Images") -> str:
    """
    O href (relativo ao OPF) do PNG deste diagrama: a imagem já desenhada, enquanto
    ela reproduz a chave corrente; senão o nome canônico, que `epub.escrever` desenha.
    """
    if d.imagem and d.imagem_chave == dialeto.chave_do_diagrama(d):
        return d.imagem
    return dialeto.nome_do_png(d, pasta_de_imagens)


def largura_do_png_pt(d: Diagrama) -> float | None:
    """
    A largura do diagrama em imagem, em pontos: casas de largura × corpo por casa. O
    `render_diagrama` é importado aqui dentro (traz `fitz`), e uma fonte que ele não
    conhece não derruba a escrita — sai sem largura.
    """
    from core import render_diagrama

    try:
        casas = render_diagrama.largura_em_casas(d.fen, d.fonte, d.orientacao, d.moldura, d.cantos,
                                                 d.coordenadas,
                                                 indicador=d.lado_indicador == "marca" and d.lado in ("w", "b"))
    except (render_diagrama.FonteDesconhecida, render_diagrama.FonteIncompleta, OSError):
        return None
    return round(casas * d.corpo_pt, 2)


def escrever(cap: Capitulo, *, pasta_de_imagens: str = "Images") -> str:
    """
    O capítulo em XHTML canônico (§6). `pasta_de_imagens` é onde os PNG de diagrama
    ficam (relativa ao OPF); quem os grava é `epub.escrever`, pelo mesmo `nome_do_png`.
    """
    return _Escritor(cap, pasta_de_imagens).documento()


def escrever_fragmento(blocos: Sequence[Bloco], arquivo: str = "") -> str:
    """Só os blocos, sem `<html>`/`<body>` — para clipes e para a área de transferência."""
    cap = Capitulo(arquivo=arquivo or "fragmento.xhtml", blocos=list(blocos))
    escritor = _Escritor(cap, "Images")
    return "\n".join(escritor.bloco(b, 0) for b in blocos)


def canonico(texto: str | bytes, arquivo: str = "") -> str:
    """`escrever(ler(texto))` — a forma canônica é a que o escritor produz (ver o cabeçalho)."""
    return escrever(ler(texto, arquivo))
