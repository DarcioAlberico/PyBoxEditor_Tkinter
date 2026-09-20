"""
O modelo do livro que a janela de edição edita (ED-00).

É a forma que o modo texto desenha e devolve, a que o DOCX consome e a que o
rascunho automático grava — o XHTML do EPUB é a *outra* forma do mesmo capítulo
(`core/editor/xhtml.py` faz a ida e a volta; SPEC_EDITOR DEC-01).

**Por que tudo é `kw_only`.** A base `Bloco` tem campos com valor padrão (`id`,
`classe`, `origem`) e as filhas têm campos obrigatórios (`Paragrafo.trechos`,
`Diagrama.fen`); sem `kw_only=True` o `dataclass` recusa a definição — "non-default
argument follows default argument". A consequência é que todo bloco se constrói por
nome de campo, inclusive em `de_dict`.

**Por que os padrões são literais.** `Diagrama.fonte` e `corpo_pt` copiam
`render_diagrama.FONTE_PADRAO` e `estilo_do_livro.CORPO_PADRAO_PT` como números e
strings, e não os importam: `render_diagrama` traz `fitz` e `PIL`, e este módulo
precisa abrir num processo sem nada disso (DEC-07). Um teste confere que as cópias
não divergiram.

**O que é único e onde.** `Bloco.id` e `Nota.id` são únicos **por capítulo**, que é a
regra do XHTML — um EPUB do Calibre tem `id="title"` em todo capítulo, e exigir
unicidade por livro faria o livro não abrir (INV-01). `id_novo()` sorteia oito hex,
único no livro na prática.
"""

from __future__ import annotations

import base64
import copy
import re
import secrets
import types
import typing
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Mapping, Sequence

# ----------------------------------------------------------------------
# Constantes copiadas (ver o cabeçalho) e vocabulários fechados
# ----------------------------------------------------------------------

#: Cópias de `core/estilo_do_livro.py` e `core/render_diagrama.py`; conferidas por
#: `tests/test_editor_modelo.py`.
CORPO_PADRAO_PT = 16.0
FONTE_PADRAO = "SkakNew-Diagram"
MOLDURA_PADRAO = "simples"
CANTO_PADRAO = "reto"

POSICOES = ("", "sobre", "sub")
PAPEIS = ("", "lance", "nag", "figurina", "comentario", "jogador", "abertura")
REFERENCIAS = ("", "diagrama", "figura", "tabela", "titulo")
ALINHAMENTOS = ("", "esquerda", "centro", "direita", "justificado")
ALINHAMENTOS_DE_FIGURA = ("esq", "centro", "dir")
MARCADORES = ("", "disco", "circulo", "quadrado", "decimal", "alfa", "romano")
ORIENTACOES = ("branca", "preta")
LADOS = ("", "w", "b")
INDICADORES = ("", "marca", "legenda")
MODOS_DE_DIAGRAMA = ("png", "fonte")
ESTADOS_DE_DIAGRAMA = ("ok", "revisar")
TIPOS_DE_NOTA = ("rodape", "fim")

#: Os estilos de parágrafo do dialeto (§6.3). `titulo1`…`titulo6` são o `Titulo`.
ESTILOS_DE_PARAGRAFO = ("corpo", "primeira", "notacao", "comentario", "legenda", "nota",
                        "cabecalho-diagrama", "epigrafe", "assinatura", "destaque", "citacao")

_RE_ID_GERADO = re.compile(r"^b-[0-9a-f]{8}$")


def id_novo() -> str:
    """Um id de bloco: `b-` e oito hexadecimais. Ver o cabeçalho sobre unicidade."""
    return "b-" + secrets.token_hex(4)


def id_gerado(valor: str) -> bool:
    """Este id tem a forma dos que `id_novo` produz? (é o que `canonico` ignora)"""
    return bool(_RE_ID_GERADO.match(valor or ""))


def fen_valido(fen: str) -> bool:
    """
    O FEN é sintaticamente válido para o `python-chess`?

    Só a sintaxe: a legalidade da posição é aviso, não erro (invariante 7 do
    `CONTEXT.md` — legalidade filtra candidatos, não inventa peça). O `chess` é
    importado aqui dentro para o módulo continuar leve de importar.
    """
    if not isinstance(fen, str) or not fen.strip():
        return False
    import chess
    try:
        chess.Board(fen)
    except ValueError:
        return False
    return True


def fen_completo(posicao: str, lado: str = "") -> str:
    """
    Um FEN de seis campos a partir da posição (campo 1) e do lado.

    O lado desconhecido (`""`) sai como `w` no FEN, porque o `python-chess` exige
    um; quem sabe que ele é desconhecido é `Diagrama.lado`, não o FEN (DEC-06).
    """
    campos = posicao.split()
    if len(campos) >= 6:
        if lado:
            campos[1] = lado
        return " ".join(campos[:6])
    return f"{campos[0]} {lado or 'w'} - - 0 1"


def _um_de(valor: str, opcoes: Sequence[str], nome: str) -> str:
    valor = "" if valor is None else str(valor)
    if valor not in opcoes:
        raise ValueError(f"{nome} inválido: {valor!r} (use um de {opcoes})")
    return valor


# ----------------------------------------------------------------------
# Trechos
# ----------------------------------------------------------------------

@dataclass(kw_only=True)
class Trecho:
    """Uma corrida de texto com o mesmo formato — ou uma ilha inline (§5)."""

    texto: str = ""
    negrito: bool = False
    italico: bool = False
    sublinhado: bool = False
    tachado: bool = False
    versalete: bool = False
    posicao: str = ""
    familia: str = ""
    corpo_pt: float | None = None
    cor: str = ""
    fundo: str = ""
    classe: str = ""
    lang: str = ""
    titulo: str = ""
    link: str = ""
    ref: str = ""
    nota: str = ""
    papel: str = ""
    nag: int | None = None
    chave: str = ""
    codigo: bool = False
    quebra_antes: bool = False
    pagina: int | None = None
    ilha: str = ""

    def __post_init__(self) -> None:
        self.texto = str(self.texto)
        self.posicao = _um_de(self.posicao, POSICOES, "posicao")
        self.papel = _um_de(self.papel, PAPEIS, "papel")
        self.ref = _um_de(self.ref, REFERENCIAS, "ref")
        if self.corpo_pt is not None:
            self.corpo_pt = float(self.corpo_pt)
            if self.corpo_pt <= 0:
                raise ValueError(f"corpo inválido: {self.corpo_pt!r}")
        if self.nag is not None:
            self.nag = int(self.nag)
        if self.pagina is not None:
            self.pagina = int(self.pagina)
        if self.ilha and self.texto:
            raise ValueError("uma ilha inline não tem texto próprio")

    @property
    def vazio(self) -> bool:
        """Não carrega texto nem nada que valha sozinho (quebra, página, ilha, nota)."""
        return not (self.texto or self.quebra_antes or self.pagina is not None
                    or self.ilha or self.nota)

    def formato(self) -> dict[str, Any]:
        """Tudo menos o texto — o que decide se dois trechos vizinhos se fundem."""
        dados = para_dict(self)
        dados.pop("texto")
        dados.pop("tipo", None)
        return dados


# ----------------------------------------------------------------------
# Blocos
# ----------------------------------------------------------------------

@dataclass(kw_only=True)
class Origem:
    """De onde o bloco veio no documento editorial (DEC-10)."""

    page_id: str
    bloco_id: str
    pagina: int
    caixa: tuple[int, int, int, int] | None = None
    fundidas: list["Origem"] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not str(self.page_id).strip() or not str(self.bloco_id).strip():
            raise ValueError("origem precisa de page_id e bloco_id")
        self.pagina = int(self.pagina)
        if self.caixa is not None:
            caixa = tuple(int(v) for v in self.caixa)
            if len(caixa) != 4:
                raise ValueError("caixa da origem precisa de quatro coordenadas")
            self.caixa = caixa  # type: ignore[assignment]


@dataclass(kw_only=True)
class Bloco:
    """Base de todo bloco; nunca instanciada diretamente."""

    id: str = field(default_factory=id_novo)
    id_persistente: bool = False
    classe: str = ""
    extras: dict[str, str] = field(default_factory=dict)
    origem: Origem | None = None
    linha_fonte: int | None = None

    def __post_init__(self) -> None:
        if type(self) is Bloco:
            raise TypeError("Bloco é abstrato; use uma das classes concretas")
        self.id = str(self.id).strip()
        if not self.id:
            raise ValueError("bloco sem id")
        self.extras = {str(k): str(v) for k, v in (self.extras or {}).items()}
        if self.origem is not None:
            self.id_persistente = True


@dataclass(kw_only=True)
class Paragrafo(Bloco):
    trechos: list[Trecho]
    estilo: str = "corpo"
    alinhamento: str = ""
    recuo_primeira_em: float | None = None
    recuo_esquerda_em: float | None = None
    recuo_direita_em: float | None = None
    antes_em: float | None = None
    depois_em: float | None = None
    entrelinha: float | None = None
    manter_com_proximo: bool = False
    manter_linhas: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        self.trechos = list(self.trechos)
        self.estilo = str(self.estilo or "corpo")
        self.alinhamento = _um_de(self.alinhamento, ALINHAMENTOS, "alinhamento")

    @property
    def texto(self) -> str:
        return texto_de(self)


@dataclass(kw_only=True)
class Titulo(Paragrafo):
    nivel: int = 1

    def __post_init__(self) -> None:
        super().__post_init__()
        self.nivel = int(self.nivel)
        if not 1 <= self.nivel <= 6:
            raise ValueError(f"nível de título inválido: {self.nivel}")
        # É a âncora do sumário: o `id` de um título sempre vai para o arquivo.
        self.id_persistente = True
        self.estilo = f"titulo{self.nivel}"


@dataclass(kw_only=True)
class ItemDeLista:
    paragrafos: list[Paragrafo]
    filhos: "Lista | None" = None

    def __post_init__(self) -> None:
        self.paragrafos = list(self.paragrafos)


@dataclass(kw_only=True)
class Lista(Bloco):
    ordenada: bool
    itens: list[ItemDeLista]
    inicio: int = 1
    marcador: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        self.ordenada = bool(self.ordenada)
        self.itens = list(self.itens)
        self.inicio = int(self.inicio)
        self.marcador = _um_de(self.marcador, MARCADORES, "marcador")


@dataclass(kw_only=True)
class Celula:
    blocos: list[Paragrafo]
    cabecalho: bool = False
    alinhamento: str = ""

    def __post_init__(self) -> None:
        self.blocos = list(self.blocos)
        self.alinhamento = _um_de(self.alinhamento, ALINHAMENTOS, "alinhamento")


@dataclass(kw_only=True)
class Tabela(Bloco):
    filas: list[list[Celula]]
    primeira_fila_cabecalho: bool = False
    legenda: list[Trecho] = field(default_factory=list)
    numero: int | None = None
    largura_pct: int | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        self.filas = [list(fila) for fila in self.filas]
        larguras = {len(fila) for fila in self.filas}
        if len(larguras) > 1:
            raise ValueError(f"tabela {self.id} não é retangular: filas com {sorted(larguras)} células")
        if self.largura_pct is not None:
            self.largura_pct = int(self.largura_pct)
        # A primeira fila de cabeçalho e as células `<th>` dela são a mesma coisa dita
        # de dois jeitos; normalizar aqui é o que deixa a ida e volta fechar.
        if self.filas and self.filas[0]:
            if self.primeira_fila_cabecalho:
                for celula in self.filas[0]:
                    celula.cabecalho = True
            elif all(celula.cabecalho for celula in self.filas[0]):
                self.primeira_fila_cabecalho = True

    @property
    def colunas(self) -> int:
        return len(self.filas[0]) if self.filas else 0


@dataclass(kw_only=True)
class Figura(Bloco):
    recurso: str
    alt: str = ""
    legenda: list[Trecho] = field(default_factory=list)
    numero: int | None = None
    largura_pt: float | None = None
    alinhamento: str = "centro"

    def __post_init__(self) -> None:
        super().__post_init__()
        self.recurso = str(self.recurso).strip()
        if not self.recurso:
            raise ValueError(f"figura {self.id} sem recurso")
        self.alinhamento = _um_de(self.alinhamento, ALINHAMENTOS_DE_FIGURA, "alinhamento")


@dataclass(kw_only=True)
class Diagrama(Bloco):
    fen: str
    lado: str = ""
    orientacao: str = "branca"
    coordenadas: bool = False
    lado_indicador: str = ""
    marcas: list[str] = field(default_factory=list)
    setas: list[tuple[str, str]] = field(default_factory=list)
    fonte: str = FONTE_PADRAO
    moldura: str = MOLDURA_PADRAO
    cantos: str = CANTO_PADRAO
    corpo_pt: float = CORPO_PADRAO_PT
    modo: str = "png"
    numero: int | None = None
    legenda: list[Trecho] = field(default_factory=list)
    alt: str = ""
    recorte: str = ""
    estado: str = "ok"
    aviso: str = ""
    #: A imagem já desenhada deste diagrama (href relativo ao OPF), quando ela não tem o
    #: nome canônico `diag-<chave>.png` — é o PNG do EPUB de hoje. `epub.escrever` a
    #: reutiliza enquanto `imagem_chave` for a `dialeto.chave_do_diagrama` corrente; mudou
    #: o diagrama, mudou a chave, e a imagem é redesenhada (ED-01).
    imagem: str = ""
    imagem_chave: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not fen_valido(self.fen):
            raise ValueError(f"diagrama {self.id} com FEN inválido: {self.fen!r}")
        self.lado = _um_de(self.lado, LADOS, "lado")
        self.orientacao = _um_de(self.orientacao, ORIENTACOES, "orientacao")
        self.lado_indicador = _um_de(self.lado_indicador, INDICADORES, "lado_indicador")
        self.modo = _um_de(self.modo, MODOS_DE_DIAGRAMA, "modo")
        self.estado = _um_de(self.estado, ESTADOS_DE_DIAGRAMA, "estado")
        self.marcas = [str(c) for c in self.marcas]
        self.setas = [(str(a), str(b)) for a, b in self.setas]
        self.corpo_pt = float(self.corpo_pt)

    @property
    def posicao(self) -> str:
        """Só o campo de posição do FEN — o que a fonte de diagrama desenha."""
        return self.fen.split()[0]


@dataclass(kw_only=True)
class Citacao(Bloco):
    blocos: list[Paragrafo]

    def __post_init__(self) -> None:
        super().__post_init__()
        self.blocos = list(self.blocos)


@dataclass(kw_only=True)
class Nota:
    """Uma nota de rodapé ou de fim; mora em `Capitulo.notas` e é apontada por `Trecho.nota`."""

    id: str = field(default_factory=id_novo)
    tipo: str = "rodape"
    blocos: list[Paragrafo] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.id = str(self.id).strip()
        if not self.id:
            raise ValueError("nota sem id")
        self.tipo = _um_de(self.tipo, TIPOS_DE_NOTA, "tipo")
        self.blocos = list(self.blocos)


@dataclass(kw_only=True)
class QuebraDePagina(Bloco):
    """A quebra pedida pelo usuário: quebra de verdade no DOCX e no PDF."""


@dataclass(kw_only=True)
class MarcaDePagina(Bloco):
    """A página do impresso: marcador para a `page-list` e para "ir para página"; não quebra."""

    pagina: int

    def __post_init__(self) -> None:
        super().__post_init__()
        self.pagina = int(self.pagina)
        # O `id` é a âncora da `page-list` (`pg-27`), e é ele que "ir para página"
        # e o leitor usam; só um id dado de fora prevalece sobre isso.
        if id_gerado(self.id):
            self.id = f"pg-{self.pagina}"
        self.id_persistente = True


@dataclass(kw_only=True)
class Separador(Bloco):
    """Um `<hr/>`."""


@dataclass(kw_only=True)
class IlhaBruta(Bloco):
    xhtml: str
    elemento: str

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.xhtml:
            raise ValueError(f"ilha {self.id} vazia")
        self.elemento = str(self.elemento or "?")


# ----------------------------------------------------------------------
# Capítulo, recursos, metadados, livro
# ----------------------------------------------------------------------

@dataclass(kw_only=True)
class Capitulo:
    arquivo: str
    titulo: str = ""
    blocos: list[Bloco] = field(default_factory=list)
    notas: list[Nota] = field(default_factory=list)
    folhas: list[str] = field(default_factory=list)
    idioma: str = ""
    semantica: str = ""
    cabeca_extra: str = ""
    texto_cru: str | None = None
    avisos: list[str] = field(default_factory=list)
    #: Prefixos de namespace declarados no `<html>` além de `epub` (uma ilha pode usá-los).
    namespaces: dict[str, str] = field(default_factory=dict)
    #: `linear="no"` na espinha do OPF é `False` (a capa e as notas de um EPUB de fora).
    linear: bool = True

    def __post_init__(self) -> None:
        self.arquivo = str(self.arquivo).strip()
        if not self.arquivo:
            raise ValueError("capítulo sem nome de arquivo")
        self.blocos = list(self.blocos)
        self.notas = list(self.notas)
        self.folhas = [str(f) for f in self.folhas]
        self.avisos = [str(a) for a in self.avisos]

    @property
    def titulo_efetivo(self) -> str:
        """O título do sumário: o dado, senão o primeiro `Titulo`, senão o arquivo."""
        if self.titulo:
            return self.titulo
        for bloco in self.blocos:
            if isinstance(bloco, Titulo):
                return texto_de(bloco)
        return self.arquivo.rsplit("/", 1)[-1]

    def bloco(self, id: str) -> Bloco | None:
        return next((b for b in self.blocos if b.id == id), None)

    def nota(self, id: str) -> Nota | None:
        return next((n for n in self.notas if n.id == id), None)

    def normalizar_notas(self) -> None:
        """As de rodapé primeiro, depois as de fim — é a ordem em que o XHTML as guarda."""
        self.notas = sorted(self.notas, key=lambda n: 0 if n.tipo == "rodape" else 1)


@dataclass(kw_only=True)
class Recurso:
    caminho: str
    tipo_mime: str
    dados: bytes | None = None
    texto_cru: str | None = None
    propriedades: str = ""
    #: `False` para o que estava no zip sem entrada no manifesto (`META-INF/encryption.xml`,
    #: um arquivo esquecido): é regravado onde estava, e não entra no OPF.
    no_manifesto: bool = True

    def __post_init__(self) -> None:
        self.caminho = str(self.caminho).strip()
        if not self.caminho:
            raise ValueError("recurso sem caminho")
        self.tipo_mime = str(self.tipo_mime)


@dataclass(kw_only=True)
class EntradaDeSumario:
    rotulo: str
    destino: str
    filhos: list["EntradaDeSumario"] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rotulo = str(self.rotulo)
        self.destino = str(self.destino)
        self.filhos = list(self.filhos)


@dataclass(kw_only=True)
class Pessoa:
    nome: str
    papel: str = "aut"
    file_as: str = ""
    #: O `id` do `<dc:creator>` como lido; um `<meta refines="#id">` preservado em
    #: `Metadados.extras` precisa dele de volta.
    id: str = ""

    def __post_init__(self) -> None:
        self.nome = str(self.nome).strip()
        if not self.nome:
            raise ValueError("pessoa sem nome")


@dataclass(kw_only=True)
class Metadados:
    titulo: str
    autores: list[Pessoa] = field(default_factory=list)
    colaboradores: list[Pessoa] = field(default_factory=list)
    idioma: str = "en"
    identificador: str = ""
    editora: str = ""
    data: str = ""
    descricao: str = ""
    assuntos: list[str] = field(default_factory=list)
    direitos: str = ""
    colecao: tuple[str, int] | None = None
    capa: str = ""
    fonte_impressa: str = ""
    modificado: str = ""
    #: O que o modelo não interpreta, tal como estava no OPF: `(elemento, atributos, texto)`
    #: — `("meta", 'property="title-type" refines="#title"', "main")`, `("dc:type", "", "…")`.
    #: `epub.escrever` os devolve na letra, depois do que ele mesmo gera.
    extras: list[tuple[str, str, str]] = field(default_factory=list)
    #: `id` do OPF dos elementos interpretados (`"identificador"`, `"titulo"`, `"idioma"`,
    #: `"colecao"`, `"assunto-1"`…), para os `refines` dos extras não ficarem soltos.
    ids: dict[str, str] = field(default_factory=dict)
    #: O `prefix` do `<package>`, além dos reservados e dos que o escritor declara sozinho.
    prefixos: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.titulo = str(self.titulo)
        self.idioma = str(self.idioma or "und")
        if self.colecao is not None:
            nome, posicao = self.colecao
            self.colecao = (str(nome), int(posicao))
        self.extras = [(str(a), str(b), str(c)) for a, b, c in self.extras]
        self.ids = {str(k): str(v) for k, v in self.ids.items()}
        self.prefixos = {str(k): str(v) for k, v in self.prefixos.items()}


@dataclass(kw_only=True)
class FormatoDePagina:
    largura_mm: float = 156.0
    altura_mm: float = 234.0
    #: superior, externa, inferior, interna
    margens_mm: tuple[float, float, float, float] = (20.0, 18.0, 20.0, 22.0)
    espelhadas: bool = True
    cabecalho_par: str = "titulo"
    cabecalho_impar: str = "capitulo"
    numerar_paginas: bool = True
    #: `hyphens: auto` na folha padrão, `w:autoHyphenation` no DOCX, o mesmo no PDF.
    hifenizar: bool = False

    def __post_init__(self) -> None:
        self.margens_mm = tuple(float(m) for m in self.margens_mm)  # type: ignore[assignment]
        if len(self.margens_mm) != 4:
            raise ValueError("margens precisam de quatro valores")
        for nome in ("cabecalho_par", "cabecalho_impar"):
            _um_de(getattr(self, nome), ("", "titulo", "capitulo"), nome)


@dataclass(kw_only=True)
class OrigemDoLivro:
    documento_editorial: str = ""
    pdf: str = ""
    diario: str = ""


@dataclass(kw_only=True)
class Livro:
    metadados: Metadados
    capitulos: list[Capitulo] = field(default_factory=list)
    recursos: dict[str, Recurso] = field(default_factory=dict)
    folhas: list[str] = field(default_factory=list)
    sumario: list[EntradaDeSumario] = field(default_factory=list)
    marcos: list[tuple[str, str]] = field(default_factory=list)
    opf: str = "OEBPS/package.opf"
    nav: str = "nav.xhtml"
    ncx: str = ""
    pagina: FormatoDePagina = field(default_factory=FormatoDePagina)
    origem: OrigemDoLivro = field(default_factory=OrigemDoLivro)
    #: O EPUB de onde os `Recurso.dados is None` ainda vão ser lidos (`epub.dados_de`);
    #: `epub.escrever` o atualiza para o arquivo recém-gravado.
    zip_de_origem: str = ""
    #: Posição do `nav.xhtml` na espinha quando ele estava nela (o Sigil o põe), senão `None`.
    nav_na_espinha: int | None = None

    def __post_init__(self) -> None:
        self.capitulos = list(self.capitulos)
        self.recursos = dict(self.recursos)
        self.folhas = [str(f) for f in self.folhas]
        self.marcos = [(str(a), str(b)) for a, b in self.marcos]

    def capitulo(self, arquivo: str) -> Capitulo | None:
        return next((c for c in self.capitulos if c.arquivo == arquivo), None)

    def recurso(self, caminho: str) -> Recurso | None:
        return self.recursos.get(caminho)

    def validar(self) -> list[str]:
        """
        As invariantes da §5.1: levanta para o que é erro, devolve avisos para o resto.

        INV-01 (id único por capítulo), INV-03 (FEN) e INV-04 (tabela retangular)
        levantam `ValueError` citando o id; INV-02 (referência para o que não existe)
        vira aviso — apagar um link porque o alvo sumiu seria perder em silêncio.
        """
        avisos: list[str] = []
        arquivos = [c.arquivo for c in self.capitulos]
        if len(set(arquivos)) != len(arquivos):
            raise ValueError("dois capítulos com o mesmo arquivo")
        ids_por_capitulo: dict[str, set[str]] = {}
        for cap in self.capitulos:
            vistos: set[str] = set()
            for bloco in _todos_os_blocos(cap):
                if bloco.id in vistos:
                    raise ValueError(f"id duplicado no capítulo {cap.arquivo}: {bloco.id}")
                vistos.add(bloco.id)
                if isinstance(bloco, Diagrama) and not fen_valido(bloco.fen):
                    raise ValueError(f"diagrama {bloco.id} com FEN inválido: {bloco.fen!r}")
                if isinstance(bloco, Tabela):
                    larguras = {len(f) for f in bloco.filas}
                    if len(larguras) > 1:
                        raise ValueError(f"tabela {bloco.id} não é retangular")
            for nota in cap.notas:
                if nota.id in vistos:
                    raise ValueError(f"id duplicado no capítulo {cap.arquivo}: {nota.id}")
                vistos.add(nota.id)
            ids_por_capitulo[cap.arquivo] = vistos
        for cap in self.capitulos:
            for bloco in _todos_os_blocos(cap):
                for recurso in _recursos_de(bloco):
                    if recurso not in self.recursos:
                        avisos.append(f"{cap.arquivo}: bloco {bloco.id} aponta para recurso inexistente {recurso}")
                for trecho in _todos_os_trechos(bloco):
                    if trecho.nota and cap.nota(trecho.nota) is None:
                        avisos.append(f"{cap.arquivo}: bloco {bloco.id} referencia nota inexistente {trecho.nota}")
                    alvo = trecho.link
                    if alvo and not _e_externo(alvo):
                        arquivo, _, anc = alvo.partition("#")
                        arquivo = arquivo or cap.arquivo
                        if arquivo not in ids_por_capitulo:
                            avisos.append(f"{cap.arquivo}: link para capítulo inexistente {alvo}")
                        elif anc and anc not in ids_por_capitulo[arquivo] and not anc.startswith("pg-"):
                            avisos.append(f"{cap.arquivo}: link para âncora inexistente {alvo}")
            for folha in cap.folhas:
                if folha not in self.recursos:
                    avisos.append(f"{cap.arquivo}: folha de estilo inexistente {folha}")
        if self.metadados.capa and self.metadados.capa not in self.recursos:
            avisos.append(f"capa aponta para recurso inexistente {self.metadados.capa}")
        for folha in self.folhas:
            if folha not in self.recursos:
                avisos.append(f"folha de estilo do livro inexistente {folha}")
        return avisos


def _e_externo(alvo: str) -> bool:
    return "://" in alvo or alvo.startswith(("mailto:", "tel:"))


# ----------------------------------------------------------------------
# Percursos
# ----------------------------------------------------------------------

def _todos_os_blocos(cap: Capitulo):
    """Todo bloco do capítulo, inclusive os aninhados (célula, item, citação, nota)."""
    def percorrer(blocos):
        for bloco in blocos:
            yield bloco
            if isinstance(bloco, Lista):
                for item in bloco.itens:
                    yield from percorrer(item.paragrafos)
                    if item.filhos is not None:
                        yield from percorrer([item.filhos])
            elif isinstance(bloco, Tabela):
                for fila in bloco.filas:
                    for celula in fila:
                        yield from percorrer(celula.blocos)
            elif isinstance(bloco, Citacao):
                yield from percorrer(bloco.blocos)
    yield from percorrer(cap.blocos)
    for nota in cap.notas:
        yield from percorrer(nota.blocos)


def blocos_do_capitulo(cap: Capitulo) -> list[Bloco]:
    """A lista achatada de `_todos_os_blocos`, para quem prefere lista."""
    return list(_todos_os_blocos(cap))


def _todos_os_trechos(bloco: Bloco):
    if isinstance(bloco, Paragrafo):
        yield from bloco.trechos
    elif isinstance(bloco, (Tabela, Figura, Diagrama)):
        yield from bloco.legenda


def trechos_do_capitulo(cap: Capitulo) -> list[Trecho]:
    saida: list[Trecho] = []
    for bloco in _todos_os_blocos(cap):
        saida.extend(_todos_os_trechos(bloco))
    return saida


def _recursos_de(bloco: Bloco) -> list[str]:
    if isinstance(bloco, Figura):
        return [bloco.recurso]
    if isinstance(bloco, Diagrama) and bloco.recorte:
        return [bloco.recorte]
    return []


# ----------------------------------------------------------------------
# Texto e trechos
# ----------------------------------------------------------------------

def texto_de(bloco: Any) -> str:
    """
    O texto do bloco, sem marcação — o que a busca, a contagem e a ponte com o
    documento editorial leem. A quebra suave é `\\n`; a ilha inline e a referência de
    nota não têm texto; o diagrama e a figura contribuem só com a legenda.
    """
    if isinstance(bloco, Paragrafo):
        return "".join(("\n" if t.quebra_antes else "") + t.texto for t in bloco.trechos)
    if isinstance(bloco, Lista):
        partes = []
        for item in bloco.itens:
            partes.extend(texto_de(p) for p in item.paragrafos)
            if item.filhos is not None:
                partes.append(texto_de(item.filhos))
        return "\n".join(p for p in partes if p)
    if isinstance(bloco, Tabela):
        return "\n".join("\t".join(" ".join(texto_de(p) for p in c.blocos) for c in fila)
                         for fila in bloco.filas)
    if isinstance(bloco, (Figura, Diagrama)):
        return "".join(t.texto for t in bloco.legenda)
    if isinstance(bloco, Citacao):
        return "\n".join(texto_de(p) for p in bloco.blocos)
    if isinstance(bloco, Nota):
        return "\n".join(texto_de(p) for p in bloco.blocos)
    return ""


def trechos_normalizados(trechos: Sequence[Trecho]) -> list[Trecho]:
    """
    Funde trechos vizinhos com o mesmo formato e descarta os que não carregam nada.

    É o que faz a ida e volta fechar (INV-05): `aplicar_formato` parte trechos para
    formatar um pedaço, e a leitura do XHTML produz um trecho por elemento; sem fundir,
    "ab" + "c" e "abc" seriam parágrafos diferentes com o mesmo XHTML.
    """
    saida: list[Trecho] = []
    for trecho in trechos:
        if trecho.vazio:
            continue
        if saida and _fundem(saida[-1], trecho):
            saida[-1].texto += trecho.texto
            continue
        saida.append(copy.copy(trecho))
    return saida


_CAMPOS_DE_FORMATO: tuple[str, ...] = ()


def _chave_de_formato(t: Trecho) -> tuple:
    """Os campos do trecho menos o texto, como tupla — `formato()` sem passar por `para_dict`."""
    global _CAMPOS_DE_FORMATO
    if not _CAMPOS_DE_FORMATO:
        _CAMPOS_DE_FORMATO = tuple(f.name for f in fields(Trecho) if f.name != "texto")
    return tuple(getattr(t, campo) for campo in _CAMPOS_DE_FORMATO)


def _fundem(a: Trecho, b: Trecho) -> bool:
    # Uma ilha, uma quebra, uma marca de página ou uma nota são marcos do trecho
    # em que estão: o trecho seguinte não se cola a eles.
    if b.quebra_antes or b.pagina is not None or b.ilha or a.ilha or b.nota or a.nota:
        return False
    # Comparar tuplas, e não `formato()` (que passa por `para_dict`): a normalização
    # roda a cada leitura do widget, sobre milhares de trechos (ED-03, medido).
    return _chave_de_formato(a) == _chave_de_formato(b)


def _partir(trechos: Sequence[Trecho], posicao: int) -> list[Trecho]:
    """Os mesmos trechos com uma fronteira exatamente em `posicao` (do texto do bloco)."""
    saida: list[Trecho] = []
    andado = 0
    for trecho in trechos:
        comprimento = len(trecho.texto) + (1 if trecho.quebra_antes else 0)
        if andado < posicao < andado + comprimento:
            # `corte` é zero quando a fronteira cai logo depois da quebra suave: o
            # primeiro pedaço fica só com a quebra (não é vazio — carrega o `\n`).
            corte = posicao - andado - (1 if trecho.quebra_antes else 0)
            primeiro = copy.copy(trecho)
            primeiro.texto = trecho.texto[:corte]
            segundo = copy.copy(trecho)
            segundo.texto = trecho.texto[corte:]
            segundo.quebra_antes = False
            segundo.pagina = None
            saida.extend([primeiro, segundo])
        else:
            saida.append(trecho)
        andado += comprimento
    return saida


def _no_intervalo(trechos: Sequence[Trecho], ini: int, fim: int):
    """`(trecho, dentro)` para cada trecho, com `dentro` dizendo se ele cabe em [ini, fim)."""
    andado = 0
    for trecho in trechos:
        comprimento = len(trecho.texto) + (1 if trecho.quebra_antes else 0)
        dentro = comprimento > 0 and andado >= ini and andado + comprimento <= fim
        yield trecho, dentro
        andado += comprimento


ATRIBUTOS_DE_FORMATO = ("negrito", "italico", "sublinhado", "tachado", "versalete", "posicao",
                        "familia", "corpo_pt", "cor", "fundo", "classe", "lang", "titulo",
                        "papel", "nag", "chave", "codigo", "link", "ref")


def aplicar_formato(paragrafo: Paragrafo, ini: int, fim: int, **atributos: Any) -> Paragrafo:
    """Põe `atributos` nos trechos entre `ini` e `fim` (posições do texto do bloco)."""
    for nome in atributos:
        if nome not in ATRIBUTOS_DE_FORMATO:
            raise ValueError(f"atributo de formato desconhecido: {nome}")
    if ini > fim:
        ini, fim = fim, ini
    trechos = _partir(_partir(paragrafo.trechos, ini), fim)
    novos: list[Trecho] = []
    for trecho, dentro in _no_intervalo(trechos, ini, fim):
        if dentro and not trecho.ilha:
            trecho = copy.copy(trecho)
            for nome, valor in atributos.items():
                setattr(trecho, nome, valor)
            trecho.__post_init__()
        novos.append(trecho)
    paragrafo.trechos = trechos_normalizados(novos)
    return paragrafo


def limpar_formato(paragrafo: Paragrafo, ini: int, fim: int) -> Paragrafo:
    """Zera todo formato de caractere no intervalo — menos link, nota e referência."""
    limpo = {nome: getattr(Trecho(), nome) for nome in ATRIBUTOS_DE_FORMATO
             if nome not in ("link", "ref")}
    return aplicar_formato(paragrafo, ini, fim, **limpo)


def tem_formato(paragrafo: Paragrafo, ini: int, fim: int, nome: str) -> bool:
    """Todo o intervalo tem este atributo ligado? (a regra do "se todo tem, tira")"""
    trechos = _partir(_partir(paragrafo.trechos, ini), fim)
    dentro = [t for t, d in _no_intervalo(trechos, ini, fim) if d and not t.ilha and t.texto]
    return bool(dentro) and all(getattr(t, nome) for t in dentro)


def mudar_caixa(paragrafo: Paragrafo, ini: int, fim: int, modo: str) -> Paragrafo:
    """`maiusculas`, `minusculas`, `primeira` (de cada palavra) ou `alternar`."""
    if modo not in ("maiusculas", "minusculas", "primeira", "alternar"):
        raise ValueError(f"modo de caixa inválido: {modo!r}")
    trechos = _partir(_partir(paragrafo.trechos, ini), fim)
    novos: list[Trecho] = []
    for trecho, dentro in _no_intervalo(trechos, ini, fim):
        if dentro and not trecho.ilha:
            trecho = copy.copy(trecho)
            trecho.texto = _com_a_caixa(trecho.texto, modo)
        novos.append(trecho)
    paragrafo.trechos = trechos_normalizados(novos)
    return paragrafo


def _com_a_caixa(texto: str, modo: str) -> str:
    if modo == "maiusculas":
        return texto.upper()
    if modo == "minusculas":
        return texto.lower()
    if modo == "primeira":
        return re.sub(r"(^|(?<=\s))(\S)", lambda m: m.group(1) + m.group(2).upper(), texto.lower())
    return "".join(c.lower() if c.isupper() else c.upper() for c in texto)


def mudar_estilo(paragrafo: Paragrafo, nome: str) -> Paragrafo:
    if nome not in ESTILOS_DE_PARAGRAFO:
        raise ValueError(f"estilo desconhecido: {nome!r}")
    paragrafo.estilo = nome
    return paragrafo


def dividir_paragrafo(paragrafo: Paragrafo, posicao: int) -> tuple[Paragrafo, Paragrafo]:
    """O parágrafo partido em `posicao`; o segundo ganha id novo e o mesmo estilo."""
    trechos = _partir(paragrafo.trechos, posicao)
    antes: list[Trecho] = []
    depois: list[Trecho] = []
    andado = 0
    for trecho in trechos:
        comprimento = len(trecho.texto) + (1 if trecho.quebra_antes else 0)
        (antes if andado < posicao or comprimento == 0 and not depois else depois).append(trecho)
        andado += comprimento
    primeiro = copy.copy(paragrafo)
    primeiro.trechos = trechos_normalizados(antes)
    segundo = copy.copy(paragrafo)
    segundo.id = id_novo()
    segundo.id_persistente = False
    segundo.origem = None
    segundo.extras = dict(paragrafo.extras)
    segundo.trechos = trechos_normalizados(depois)
    if segundo.trechos and segundo.trechos[0].quebra_antes:
        segundo.trechos[0] = copy.copy(segundo.trechos[0])
        segundo.trechos[0].quebra_antes = False
    return primeiro, segundo


def juntar_paragrafos(a: Paragrafo, b: Paragrafo, marca: MarcaDePagina | None = None) -> Paragrafo:
    """
    `a` seguido de `b`, num bloco só (o de `a`).

    Quando havia uma `MarcaDePagina` entre os dois, ela vira `Trecho.pagina` no
    primeiro trecho de `b` — a página do impresso não se perde por o parágrafo
    continuar na página seguinte (INV-10, §6.1).
    """
    juntado = copy.copy(a)
    trechos_b = [copy.copy(t) for t in b.trechos]
    if marca is not None:
        if trechos_b:
            trechos_b[0].pagina = marca.pagina
        else:
            trechos_b = [Trecho(pagina=marca.pagina)]
    juntado.trechos = trechos_normalizados(list(a.trechos) + trechos_b)
    if b.origem is not None:
        if juntado.origem is None:
            juntado.origem = b.origem
        else:
            juntado.origem = copy.copy(a.origem)
            juntado.origem.fundidas = list(a.origem.fundidas) + [b.origem]
    return juntado


# ----------------------------------------------------------------------
# Blocos e capítulos
# ----------------------------------------------------------------------

def inserir_bloco(cap: Capitulo, indice: int, bloco: Bloco) -> None:
    cap.blocos.insert(indice, bloco)


def mover_bloco(cap: Capitulo, de: int, para: int) -> None:
    bloco = cap.blocos.pop(de)
    cap.blocos.insert(para, bloco)


def converter(paragrafo: Paragrafo, para: str, nivel: int = 1) -> Paragrafo:
    """`Paragrafo` ↔ `Titulo`, preservando trechos, id e origem."""
    dados = para_dict(paragrafo)
    dados.pop("tipo")
    dados.pop("nivel", None)
    if para == "titulo":
        dados.pop("estilo", None)
        return de_dict(dict(dados, tipo="Titulo", nivel=nivel))
    if para == "paragrafo":
        dados["estilo"] = "corpo"
        return de_dict(dict(dados, tipo="Paragrafo"))
    raise ValueError(f"conversão desconhecida: {para!r}")


def _notas_referenciadas(blocos: Sequence[Bloco]) -> list[str]:
    ids: list[str] = []
    for bloco in blocos:
        for trecho in _todos_os_trechos(bloco):
            if trecho.nota and trecho.nota not in ids:
                ids.append(trecho.nota)
        if isinstance(bloco, Lista):
            for item in bloco.itens:
                ids.extend(n for n in _notas_referenciadas(item.paragrafos) if n not in ids)
        elif isinstance(bloco, Tabela):
            for fila in bloco.filas:
                for celula in fila:
                    ids.extend(n for n in _notas_referenciadas(celula.blocos) if n not in ids)
        elif isinstance(bloco, Citacao):
            ids.extend(n for n in _notas_referenciadas(bloco.blocos) if n not in ids)
    return ids


def dividir_capitulo(cap: Capitulo, indice: int, arquivo_novo: str) -> tuple[Capitulo, Capitulo]:
    """
    O capítulo partido antes do bloco `indice`; cada nota vai com a sua referência.

    Só o capítulo: quem reescreve espinha, sumário, marcos e links é
    `livro_ops.dividir` (ED-01), que chama isto.
    """
    if not 0 < indice < len(cap.blocos):
        raise ValueError(f"não dá para dividir em {indice} um capítulo de {len(cap.blocos)} blocos")
    primeiro = copy.copy(cap)
    primeiro.blocos = list(cap.blocos[:indice])
    segundo = copy.copy(cap)
    segundo.arquivo = arquivo_novo
    segundo.titulo = ""
    segundo.blocos = list(cap.blocos[indice:])
    segundo.texto_cru = None
    segundo.avisos = []
    ids_do_segundo = set(_notas_referenciadas(segundo.blocos))
    primeiro.notas = [n for n in cap.notas if n.id not in ids_do_segundo]
    segundo.notas = [n for n in cap.notas if n.id in ids_do_segundo]
    return primeiro, segundo


def juntar_capitulos(a: Capitulo, b: Capitulo) -> Capitulo:
    """`a` seguido de `b`; ids de `b` que colidem com os de `a` são trocados."""
    juntado = copy.copy(a)
    juntado.blocos = list(a.blocos)
    juntado.notas = list(a.notas)
    juntado.avisos = list(a.avisos) + list(b.avisos)
    juntado.folhas = list(a.folhas) + [f for f in b.folhas if f not in a.folhas]
    ids_de_a = {bl.id for bl in _todos_os_blocos(a)} | {n.id for n in a.notas}
    copia_b = copy.deepcopy(b)
    trocas: dict[str, str] = {}
    for bloco in _todos_os_blocos(copia_b):
        if bloco.id in ids_de_a:
            novo = id_novo()
            trocas[bloco.id] = novo
            bloco.id = novo
    for nota in copia_b.notas:
        if nota.id in ids_de_a:
            novo = id_novo()
            trocas[nota.id] = novo
            nota.id = novo
    if trocas:
        for trecho in trechos_do_capitulo(copia_b):
            if trecho.nota in trocas:
                trecho.nota = trocas[trecho.nota]
            if trecho.link.startswith("#") and trecho.link[1:] in trocas:
                trecho.link = "#" + trocas[trecho.link[1:]]
    juntado.blocos.extend(copia_b.blocos)
    juntado.notas.extend(copia_b.notas)
    return juntado


def dividir_por_titulo(cap: Capitulo, nivel: int, molde: str = "{base}-{n:04d}.xhtml") -> list[Capitulo]:
    """
    Um capítulo por `Titulo` de nível ≤ `nivel`; o que vem antes do primeiro fica com o
    nome original. É o que um DOCX de 300 páginas importado precisa (§9.5).
    """
    cortes = [i for i, b in enumerate(cap.blocos) if isinstance(b, Titulo) and b.nivel <= nivel and i > 0]
    if not cortes:
        return [cap]
    base = cap.arquivo.rsplit(".", 1)[0]
    restante = cap
    saida: list[Capitulo] = []
    deslocamento = 0
    for n, corte in enumerate(cortes, start=1):
        primeiro, restante = dividir_capitulo(restante, corte - deslocamento, molde.format(base=base, n=n))
        saida.append(primeiro)
        deslocamento = corte
    saida.append(restante)
    return saida


def renumerar_notas(cap: Capitulo) -> list[tuple[str, int]]:
    """
    A ordem de exibição das notas: pela primeira referência no texto, e as órfãs no fim.

    Nada é gravado na nota — o número é só de exibição, por capítulo na tela e no
    XHTML, contínuo no DOCX (§8.8). A lista de notas do capítulo é reordenada.
    """
    ordem = _notas_referenciadas(cap.blocos)
    por_id = {n.id: n for n in cap.notas}
    novas = [por_id[i] for i in ordem if i in por_id]
    novas += [n for n in cap.notas if n.id not in ordem]
    cap.notas = novas
    cap.normalizar_notas()
    return [(n.id, i) for i, n in enumerate(cap.notas, start=1)]


ROTULOS_DE_OBJETO = {"diagrama": "Diagrama", "figura": "Figura", "tabela": "Tabela"}
_CLASSE_DE_OBJETO = {"diagrama": Diagrama, "figura": Figura, "tabela": Tabela}


def numerar_objetos(livro: Livro, tipo: str, por_capitulo: bool = False,
                    rotulo: str | None = None) -> dict[str, int]:
    """
    Numera diagramas, figuras ou tabelas em ordem de leitura e regenera o texto das
    referências cruzadas (`Trecho.ref == tipo`) — sem isso, inserir um diagrama
    desatualizaria toda referência do livro (§11.7).
    """
    classe = _CLASSE_DE_OBJETO[tipo]
    rotulo = rotulo or ROTULOS_DE_OBJETO[tipo]
    numeros: dict[str, int] = {}
    n = 0
    for cap in livro.capitulos:
        if por_capitulo:
            n = 0
        for bloco in _todos_os_blocos(cap):
            if isinstance(bloco, classe):
                n += 1
                bloco.numero = n
                bloco.id_persistente = True
                numeros[f"{cap.arquivo}#{bloco.id}"] = n
    for cap in livro.capitulos:
        for trecho in trechos_do_capitulo(cap):
            if trecho.ref != tipo:
                continue
            arquivo, _, anc = trecho.link.partition("#")
            chave = f"{arquivo or cap.arquivo}#{anc}"
            if chave in numeros:
                trecho.texto = f"{rotulo} {numeros[chave]}"
    return numeros


# ----------------------------------------------------------------------
# Serialização genérica e igualdade
# ----------------------------------------------------------------------

_TIPOS: dict[str, type] = {}


def _registrar_tipos() -> None:
    for nome, valor in list(globals().items()):
        if isinstance(valor, type) and is_dataclass(valor):
            _TIPOS[nome] = valor


def para_dict(obj: Any) -> Any:
    """
    Qualquer objeto do modelo em JSON puro. Dataclasses ganham `"tipo"`; `bytes`
    saem em base64 sob `"__bytes__"`; tuplas viram listas (o tipo anotado as
    devolve em `de_dict`).
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        dados: dict[str, Any] = {"tipo": type(obj).__name__}
        for campo in fields(obj):
            dados[campo.name] = para_dict(getattr(obj, campo.name))
        return dados
    if isinstance(obj, (list, tuple)):
        return [para_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): para_dict(v) for k, v in obj.items()}
    if isinstance(obj, bytes):
        return {"__bytes__": base64.b64encode(obj).decode("ascii")}
    return obj


def de_dict(dados: Any, tipo: Any = None) -> Any:
    """O inverso de `para_dict`, guiado pelo `"tipo"` gravado e pelas anotações."""
    if isinstance(dados, Mapping) and "__bytes__" in dados:
        return base64.b64decode(dados["__bytes__"])
    if isinstance(dados, Mapping) and "tipo" in dados and dados["tipo"] in _TIPOS:
        classe = _TIPOS[dados["tipo"]]
        dicas = typing.get_type_hints(classe)
        argumentos = {}
        for campo in fields(classe):
            if campo.name in dados:
                argumentos[campo.name] = de_dict(dados[campo.name], dicas.get(campo.name))
        return classe(**argumentos)
    origem = typing.get_origin(tipo)
    if origem in (types.UnionType, typing.Union):
        opcoes = [t for t in typing.get_args(tipo) if t is not type(None)]
        if dados is None:
            return None
        return de_dict(dados, opcoes[0] if len(opcoes) == 1 else None)
    if origem is tuple and isinstance(dados, list):
        argumentos_de_tipo = typing.get_args(tipo)
        if len(argumentos_de_tipo) == 2 and argumentos_de_tipo[1] is Ellipsis:
            return tuple(de_dict(v, argumentos_de_tipo[0]) for v in dados)
        return tuple(de_dict(v, t) for v, t in zip(dados, argumentos_de_tipo))
    if origem is list and isinstance(dados, list):
        (interno,) = typing.get_args(tipo) or (None,)
        return [de_dict(v, interno) for v in dados]
    if origem is dict and isinstance(dados, Mapping):
        _chave, valor = typing.get_args(tipo) or (None, None)
        return {k: de_dict(v, valor) for k, v in dados.items()}
    if isinstance(dados, list):
        return [de_dict(v) for v in dados]
    if isinstance(dados, Mapping):
        return {k: de_dict(v) for k, v in dados.items()}
    return dados


def _sem_ids_gerados(dados: Any) -> Any:
    """A forma de `para_dict` que `igual` compara: sem id gerado não persistente, sem linha."""
    if isinstance(dados, dict):
        limpo = {}
        for chave, valor in dados.items():
            if chave == "linha_fonte":
                continue
            if chave == "id" and not dados.get("id_persistente", True) and id_gerado(str(valor)):
                continue
            limpo[chave] = _sem_ids_gerados(valor)
        return limpo
    if isinstance(dados, list):
        return [_sem_ids_gerados(v) for v in dados]
    return dados


def igual(a: Any, b: Any) -> bool:
    """INV-05: iguais a menos de ids gerados não persistentes e de `linha_fonte`."""
    return _sem_ids_gerados(para_dict(a)) == _sem_ids_gerados(para_dict(b))


_registrar_tipos()
