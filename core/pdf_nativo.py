"""
O texto e os diagramas que o PDF já traz, lidos do próprio arquivo (F110).

**Por que existe.** `core/livro.py` lê toda página como imagem, e diz por quê
na letra: nos livros digitalizados deste corpus a camada de texto é o OCR de
fábrica do Acrobat, que erra a notação inteira (`•. hb7 2.hb7 l2Jd7` onde o
livro imprime `1...♗xb7 2.♗xb7 ♘d7`). Isso vale para as digitalizações, e só
para elas. O Dvoretsky de 2025 é outra coisa: um PDF nascido digital, com Times
New Roman de verdade no texto, as figurinas numa fonte própria (`SemFigNormal`,
em que o `K` *é* o rei) e **cada diagrama composto em Chess-Merida, uma casa
por glifo** — `*` é a casa clara vazia, `+` a escura, `l` o rei preto em casa
clara. Lido como imagem, ele custa segundos por página e perde letra e peça;
lido daqui, o livro inteiro sai em segundos, com o texto que o autor escreveu e
o FEN exato de cada diagrama — não há o que reconhecer, só o que decodificar.

**A régua decide por página** (`avaliar_pagina`), e o erro dela é assimétrico
de propósito: recusar uma página boa custa o OCR de sempre, que é o que o
projeto já fazia; aceitar uma ruim põe no livro o lixo que o `livro.py` existe
para evitar. Por isso ela não julga a *qualidade* do texto — o ClearScan
escreve prosa quase limpa e notação ilegível, e uma régua de dicionário o
aprovaria —, e sim o que o OCR de fábrica deixa no arquivo: texto invisível por
cima da imagem, fonte sintetizada pelo ClearScan (`Fd350139`), glifo sem
Unicode, produtor que é programa de OCR, página girada, texto sobre a imagem da
página inteira.

**O que sai daqui é o mesmo intermediário do OCR** — `livro.PaginaExtraida`,
com `Paragrafo` e `Figura` —, e por isso o EPUB e o DOCX (`exportar.py`), o
documento editorial e o editor não mudam uma linha. O diagrama sai `render`,
desenhado do FEN como o que o porteiro da F58 aprova; o texto sai com as
figurinas em Unicode, o negrito da fonte e o título pelo corpo da letra — que é
o capítulo que a F111 deixou para cá, porque aqui ele é exato.

**O que se perde, dito em voz alta** (F110): a procedência por caractere. A
página lida daqui não tem box, não tem confiança por glifo, não alimenta a
coleta de treino e não enfileira linha na fila de revisão.
`PaginaExtraida.leitura` diz `"camada"`, e o relatório da exportação conta
quantas páginas vieram de cada caminho.
"""

from __future__ import annotations

import collections
import io
import os
import re
import statistics
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import fitz
from PIL import Image

from core import lado_a_jogar as lado_jogar
from core import lexico, livro, render_diagrama
from core.box_model import BoxEntry


# ----------------------------------------------------------------------
# O vocabulário
# ----------------------------------------------------------------------

#: `PaginaExtraida.leitura` da página que veio daqui, e da que veio do OCR.
LEITURA_CAMADA = "camada"
LEITURA_IMAGEM = "imagem"

#: Os três valores de `livro.extrair(camada=...)`.
#:
#: `"nunca"` é o padrão da API, e não é timidez: os instrumentos que medem o
#: OCR (`ab_ocr_livro.py`, `rodada_do_corpus.py`) chamam `livro.extrair`, e uma
#: página que passasse a vir da camada mudaria o número deles sem mudar o
#: leitor. Quem quer o livro — a exportação, o documento editorial — pede
#: `"auto"`. `"sempre"` é a mão do usuário sobre a régua: lê da camada toda
#: página que tem texto, inclusive o OCR de fábrica que a régua recusaria.
MODOS = ("nunca", "auto", "sempre")

#: As bandeiras da extração: o espaço entra como caractere (é ele que separa
#: palavra em livro composto), o que está fora da página não entra, e a
#: ligadura sai desfeita — `ﬁ` vira `fi`, que é o que o dicionário conhece.
FLAGS_DO_TEXTO = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP

#: Menos que isto de caracteres visíveis e a página não tem camada de texto —
#: é a capa, a página em branco, a página que é só foto. Ela vai para o OCR,
#: que sabe fazer dela uma figura (`livro.extrair_pagina`, página de imagem).
CARACTERES_MINIMOS = 10

#: A fração de caracteres com cara de OCR de fábrica que a régua tolera.
#:
#: **Não é zero porque o livro nascido digital também tem o seu resíduo**, e
#: o que decide não é o resíduo. Medido: o Yusupov do ClearScan tem 27
#: caracteres invisíveis em 1.750 (1,5%) e *todos os outros* numa fonte `Fd`; o
#: Dvoretsky tem zero dos dois. Dois por cento separa os dois mundos com folga
#: dos dois lados.
LIMITE_DE_OCR = 0.02

#: Abaixo deste corpo, em pontos, o glifo é resíduo de composição e não texto.
#:
#: Medido no Dvoretsky: cada casa do diagrama vem acompanhada de um espaço de
#: **0,7 pt** em Chess-Merida (81.472 deles no livro), que não desenha nada e
#: dobraria a contagem de casas.
TAMANHO_MINIMO = 2.0

#: A fração da área da página que uma imagem precisa cobrir para a página ser
#: uma digitalização com texto por cima.
COBERTURA_DE_DIGITALIZACAO = 0.85

#: Fração do texto que pode estar fora da horizontal antes de a régua recusar.
#: O texto girado é do `core/vertical.py`, que lê a imagem.
LIMITE_DE_GIRADOS = 0.2


# ----------------------------------------------------------------------
# As fontes, pelo nome
# ----------------------------------------------------------------------

_SUBCONJUNTO = re.compile(r"^[A-Z]{6}\+")


def _chave(nome: str) -> str:
    """O nome da fonte sem subconjunto e sem pontuação: `ABCDEF+Chess-Merida` → `chessmerida`."""
    return re.sub(r"[^0-9a-z]", "", _SUBCONJUNTO.sub("", str(nome or "")).lower())


#: As fontes que o ClearScan do Acrobat sintetiza a partir do glifo
#: digitalizado — `Fd350139`, `Fd543593`. Os três livros "editáveis" do corpus
#: as têm, e o Unicode delas é o que o OCR do Acrobat achou.
_CLEARSCAN = re.compile(r"^fd\d+$")

#: Fontes que só existem numa camada de OCR: a invisível do Acrobat, a do
#: Tesseract (`GlyphLessFont`).
FONTES_DE_OCR = frozenset({"hiddenhorzocr", "hiddenvertocr", "glyphlessfont"})

#: Programas cujo carimbo em `producer`/`creator` diz que o texto do PDF saiu
#: de um reconhecimento. O Paper Capture é o do ClearScan e o da camada
#: invisível do Acrobat.
PRODUTORES_DE_OCR = ("paper capture", "clearscan", "finereader", "abbyy",
                     "tesseract", "ocrmypdf", "omnipage", "readiris")


def fonte_de_ocr(nome: str) -> bool:
    """A fonte é das que um OCR de fábrica escreve?"""
    chave = _chave(nome)
    return bool(_CLEARSCAN.match(chave)) or chave in FONTES_DE_OCR


def produtor_de_ocr(carimbo: str) -> Optional[str]:
    """O programa de OCR que o carimbo do PDF denuncia, ou `None`."""
    baixo = str(carimbo or "").lower()
    for nome in PRODUTORES_DE_OCR:
        if nome in baixo:
            return nome
    return None


def produtor(doc: fitz.Document) -> str:
    """`producer` e `creator` do PDF, juntos — os dois carimbam o OCR."""
    meta = doc.metadata or {}
    return " ".join(p for p in (meta.get("producer"), meta.get("creator")) if p)


# ----------------------------------------------------------------------
# A figurina do texto corrido
# ----------------------------------------------------------------------

#: A codificação das figurinas do ChessBase, **medida na chave de símbolos do
#: próprio Dvoretsky** (p. 788, "Signs and Symbols", que imprime cada símbolo
#: na `SemFigNormal` ao lado do que ele quer dizer) e no uso: `R+§ vs R+§` é
#: "torre e peão contra torre e peão", e o `…` da `SemFig` abre `(… 3...cxb6)`,
#: que é "com a ideia de" — as reticências dos lances vêm em Times.
#:
#: **O ponto de código de chegada é o da barra rápida** (`core/nags.py`), e não
#: o da Wikipedia: `Δ` e não `∆`, `⇄` e não `⇆`. É a mesma regra que impede duas
#: classes ensinando o mesmo símbolo ao modelo.
#:
#: O `+–`/`–+` fica com o travessão: é o que o livro imprime e o que o leitor
#: de imagem escreve (`livro._TRACOS_DO_MOTOR`). Caractere da fonte que não está
#: aqui passa como veio — ele é o que o PDF diz, e inventar tradução seria pior.
FIGURINAS_CHESSBASE = {
    "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "§": "♙",
    "²": "⩲", "³": "⩱", "µ": "∓", "™": "□", "…": "Δ", "„": "⇄",
}

#: A fonte de figurina genérica: só as maiúsculas são peça (F2.3, o `Bb5` que
#: virava `♗♝5`). É o que o perfil `10_figurina_unica` faz com as figurinas.
FIGURINAS_SIMPLES = {"K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙"}

#: `(trecho do nome da fonte, mapa)` — o primeiro que casa ganha.
#:
#: **Não são os perfis de `config/profiles`, e é de propósito.** Aqueles servem
#: para reescrever o PDF, depois de `chess_pdf_processor.is_chess_font` já ter
#: decidido que o span é de xadrez; os padrões deles são largos (`alpha`,
#: `diagram`), e aplicados ao texto corrido de um livro qualquer trocariam o
#: `b` de uma fonte chamada `AlphaSans` por bispo preto. Aqui a lista é curta e
#: cada linha foi vista num PDF.
FONTES_DE_FIGURINA: Tuple[Tuple[str, Dict[str, str]], ...] = (
    ("semfig", FIGURINAS_CHESSBASE),
    ("figurine", FIGURINAS_SIMPLES),
)

#: Os caracteres de texto que querem dizer outra coisa num livro de xadrez.
#:
#: O Dvoretsky compõe o zugzwang com o `ʘ` (U+0298, o clique bilabial do
#: alfabeto fonético) — a chave de símbolos dele diz "ʘ zugzwang" —, e o
#: símbolo da barra rápida é o `⨀`. Nenhum livro de xadrez usa o clique como
#: letra.
EQUIVALENTES = {"ʘ": "⨀"}

#: A figurina de cada peça, pela letra do FEN — a figurina do texto corrido é
#: uma só para os dois lados (F1.1).
_FIGURINA_DA_LETRA = {"K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙"}


def mapa_de_figurina(nome_da_fonte: str) -> Optional[Dict[str, str]]:
    """O mapa de uma fonte de figurina do texto corrido, ou `None`."""
    chave = _chave(nome_da_fonte)
    for trecho, mapa in FONTES_DE_FIGURINA:
        if trecho in chave:
            return mapa
    return None


def _sem_simbolo(caractere: str) -> str:
    """
    O caractere de uma fonte de símbolos, sem o deslocamento da área privada.

    A `MERIFONT.TTF` original só tem `cmap` Symbol (3,0), com os glifos em
    U+F020–U+F0FF (`fontes_de_diagrama.json`); um PDF composto com ela pode
    trazer a casa `+` como U+F02B. Tirar o `0xF000` devolve o teclado do mapa.
    """
    codigo = ord(caractere)
    if 0xF020 <= codigo <= 0xF0FF:
        return chr(codigo - 0xF000)
    return caractere


# ----------------------------------------------------------------------
# A fonte de diagrama
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class MapaDeDiagrama:
    """
    O que cada glifo de uma fonte de diagrama quer dizer, para **ler**.

    Sai do mesmo `fontes_de_diagrama.json` que o `render_diagrama` usa para
    desenhar, e acrescenta o que só a leitura precisa: a outra forma da casa
    vazia, as marcas e o rótulo que a moldura traz desenhado.
    """

    nome: str
    #: caractere → (letra do FEN ou None, "clara" | "escura")
    casas: Dict[str, Tuple[Optional[str], str]]
    #: caractere → cor da casa **marcada** (vazia, com um sinal por cima)
    marcas: Dict[str, str] = field(default_factory=dict)
    #: os caracteres que são pedaço de moldura
    moldura: frozenset = frozenset()
    #: caractere de moldura que traz o rótulo da fila → a fila (1..8)
    filas: Dict[str, int] = field(default_factory=dict)
    #: caractere de moldura que traz o rótulo da coluna → a coluna (0 = a)
    colunas: Dict[str, int] = field(default_factory=dict)

    def de_casa(self, caractere: str) -> bool:
        return caractere in self.casas or caractere in self.marcas

    def cor(self, caractere: str) -> str:
        if caractere in self.casas:
            return self.casas[caractere][1]
        return self.marcas[caractere]


#: `(trecho do nome da fonte no PDF, mapa em fontes_de_diagrama.json)`.
#:
#: A Chess-Merida do Dvoretsky é a de Armando Marroquin, com o teclado do
#: `fonts/LEEME__D.TXT`: a casa clara vazia é "[espacio] ó `*`" e a escura é
#: `+`. O livro usa o `*`; o mapa de desenho só tem o espaço, porque desenha
#: com ele — e é por isso que a leitura acrescenta o `*` (`_CASAS_A_MAIS`).
FONTES_DE_DIAGRAMA: Tuple[Tuple[str, str], ...] = (
    ("merida", "ChessMerida-Diagram"),
    ("merifont", "ChessMerida-Diagram"),
    ("skaknewdiagram", "SkakNew-Diagram"),
)

#: A casa vazia que o mapa de desenho não tem, porque escolheu a outra forma.
_CASAS_A_MAIS = {"ChessMerida-Diagram": {"*": (None, "clara")}}

#: As marcas do teclado da Chess Merida (`LEEME__D.TXT`: "(x), (X), (.) y (:)
#: contienen símbolos auxiliares"). Minúscula — ou o ponto — na casa clara,
#: maiúscula — ou os dois-pontos — na escura, como as peças. O Dvoretsky usa o
#: `x` e o `X` nas casas-chave da p. 18.
_MARCAS = {"ChessMerida-Diagram": {"x": "clara", "X": "escura",
                                   ".": "clara", ":": "escura"}}

_mapas: Dict[str, Optional[MapaDeDiagrama]] = {}


def _mapa_de_leitura(nome: str) -> MapaDeDiagrama:
    base = render_diagrama.mapa_da_fonte(nome)
    casas = dict(base.casas)
    casas.update(_CASAS_A_MAIS.get(nome, {}))
    moldura: set = set()
    filas: Dict[str, int] = {}
    colunas: Dict[str, int] = {}
    for pecas in base.molduras.values():
        for chave, valor in pecas.items():
            if chave == "filas":
                filas.update({c: i + 1 for i, c in enumerate(valor)})
            elif chave == "colunas":
                colunas.update({c: i for i, c in enumerate(valor)})
            if isinstance(valor, dict):
                moldura.update(valor.values())
            else:
                moldura.update(valor)
    return MapaDeDiagrama(nome, casas, dict(_MARCAS.get(nome, {})),
                          frozenset(moldura), filas, colunas)


def mapa_de_diagrama(nome_da_fonte: str) -> Optional[MapaDeDiagrama]:
    """O mapa de leitura de uma fonte de diagrama do PDF, ou `None`."""
    chave = _chave(nome_da_fonte)
    if chave in _mapas:
        return _mapas[chave]
    mapa = None
    for trecho, nome in FONTES_DE_DIAGRAMA:
        if trecho in chave:
            try:
                mapa = _mapa_de_leitura(nome)
            except (render_diagrama.FonteDesconhecida, KeyError, OSError, ValueError):
                mapa = None
            break
    _mapas[chave] = mapa
    return mapa


def _de_xadrez(nome_da_fonte: str) -> bool:
    return (mapa_de_figurina(nome_da_fonte) is not None
            or mapa_de_diagrama(nome_da_fonte) is not None)


#: Trechos de nome que denunciam fonte de xadrez — a lista de
#: `chess_pdf_processor.CHESS_FONT_KEYWORDS` sem o `alpha` e o `leipzig`
#: soltos, que casariam com uma `AlphaSans` de texto corrido. Aqui o nome só
#: serve para **recusar** (`GLIFOS_DE_FONTE_SEM_MAPA`), e recusar por engano
#: custa o OCR de sempre, e não o livro.
PALAVRAS_DE_FONTE_DE_XADREZ = ("chess", "merida", "diagram", "figurin", "skak",
                               "cburnett", "chessalpha", "fritz")

#: Glifos numa fonte de xadrez sem mapa a partir dos quais a página vai ao OCR.
#:
#: Um tabuleiro são 64: com a fonte desconhecida, as casas virariam texto —
#: `l+*+` no meio da frase —, e o OCR lê o tabuleiro pela imagem. Abaixo disto
#: são figurinas soltas, que passam como a letra que o PDF diz.
GLIFOS_DE_FONTE_SEM_MAPA = 16


def _fonte_de_xadrez_sem_mapa(nome_da_fonte: str) -> bool:
    chave = _chave(nome_da_fonte)
    return (any(p in chave for p in PALAVRAS_DE_FONTE_DE_XADREZ)
            and not _de_xadrez(nome_da_fonte))


# ----------------------------------------------------------------------
# A régua: esta camada merece ser lida?
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class Veredito:
    """O que a régua decidiu sobre uma página, e por quê."""

    numero: int
    aceita: bool
    motivo: str
    #: Caracteres visíveis que não são espaço.
    caracteres: int = 0
    #: As fontes da página, da que mais escreve para a que menos.
    fontes: Tuple[str, ...] = ()

    @property
    def tem_texto(self) -> bool:
        return self.caracteres >= CARACTERES_MINIMOS

    @property
    def leitura(self) -> str:
        return LEITURA_CAMADA if self.aceita else LEITURA_IMAGEM


_ESPACOS = frozenset({9, 10, 13, 32, 0xA0})


def avaliar_pagina(page: fitz.Page, *, numero: Optional[int] = None,
                   produtor: str = "") -> Veredito:
    """
    A camada desta página é o texto que o livro imprimiu?

    Lê o `get_texttrace`, que é o único lugar em que o PyMuPDF diz se o texto
    está **visível**: a camada de OCR do Paper Capture e do ABBYY é texto de
    verdade no arquivo, com posição e fonte, e só o modo de renderização 3
    (invisível) a separa do texto impresso. Medido nos livros de `PDF/`: o
    Darcy Lima e a amostra do ABBYY têm todos os caracteres invisíveis; os três
    ClearScan (Yusupov, Nunn, Aagaard), quase todos em fontes `Fd`; o
    Dvoretsky, nenhum dos dois.
    """
    numero = page.number if numero is None else numero
    total = invisiveis = de_ocr = sem_unicode = girados = 0
    por_fonte: "collections.Counter[str]" = collections.Counter()
    sem_mapa: "collections.Counter[str]" = collections.Counter()
    for traco in page.get_texttrace():
        nome = str(traco.get("font") or "")
        caracteres = traco.get("chars") or ()
        uteis = sum(1 for item in caracteres if item[0] not in _ESPACOS)
        if not uteis:
            continue
        total += uteis
        por_fonte[nome] += uteis
        if traco.get("type") == 3 or float(traco.get("opacity", 1.0) or 0.0) <= 0.0:
            invisiveis += uteis
        if fonte_de_ocr(nome):
            de_ocr += uteis
        if _fonte_de_xadrez_sem_mapa(nome):
            sem_mapa[nome] += uteis
        direcao = traco.get("dir") or (1.0, 0.0)
        if abs(float(direcao[1])) > 0.1:
            girados += uteis
        if not _de_xadrez(nome):
            sem_unicode += sum(1 for item in caracteres
                               if item[0] == 0xFFFD or 0xE000 <= item[0] <= 0xF8FF)
    fontes = tuple(nome for nome, _n in por_fonte.most_common())

    def recusa(motivo: str) -> Veredito:
        return Veredito(numero, False, motivo, total, fontes)

    if page.rotation % 360:
        return recusa(f"página girada ({page.rotation}°)")
    if total < CARACTERES_MINIMOS:
        return recusa("sem camada de texto")
    if invisiveis > LIMITE_DE_OCR * total:
        return recusa(f"texto invisível sobre a imagem ({invisiveis} de {total} "
                      "caracteres): é camada de OCR")
    if de_ocr > LIMITE_DE_OCR * total:
        return recusa(f"fonte sintetizada pelo OCR ({de_ocr} de {total} caracteres "
                      "em fontes como Fd…): é o texto que o ClearScan achou")
    if sem_unicode > LIMITE_DE_OCR * total:
        return recusa(f"glifos sem Unicode ({sem_unicode} de {total}): a fonte "
                      "não diz que letra desenha")
    desconhecida = next((nome for nome, n in sem_mapa.most_common()
                         if n >= GLIFOS_DE_FONTE_SEM_MAPA), None)
    if desconhecida:
        return recusa(f"fonte de xadrez sem mapa ({desconhecida}): o diagrama "
                      "dela não se decodifica, e vai à imagem")
    programa = produtor_de_ocr(produtor)
    if programa:
        return recusa(f"o PDF foi carimbado por um programa de OCR ({programa})")
    if girados > LIMITE_DE_GIRADOS * total:
        return recusa(f"texto fora da horizontal ({girados} de {total})")
    area = abs(page.rect) or 1.0
    for info in page.get_image_info():
        caixa = fitz.Rect(info.get("bbox") or (0, 0, 0, 0)) & page.rect
        if abs(caixa) >= COBERTURA_DE_DIGITALIZACAO * area:
            return recusa("texto sobre a imagem da página inteira: é digitalização")
    return Veredito(numero, True, "camada tipográfica", total, fontes)


def avaliar(caminho: str, paginas: Optional[Sequence[int]] = None) -> List[Veredito]:
    """O veredito de cada página pedida (todas, sem `paginas`)."""
    with fitz.open(caminho) as doc:
        carimbo = produtor(doc)
        numeros = range(len(doc)) if paginas is None else paginas
        return [avaliar_pagina(doc[n], numero=n, produtor=carimbo) for n in numeros]


def amostrar(caminho: str, paginas: int = 40) -> Tuple[int, int]:
    """
    `(aceitas, amostradas)`: a régua em páginas espalhadas pelo livro.

    É o que a caixa de exportação mostra antes de ler — a mesma amostra de
    `livro.idioma_do_pdf`, e pelo mesmo motivo: as primeiras páginas são capa
    e rosto, e não dizem como é o livro.
    """
    with fitz.open(caminho) as doc:
        total = len(doc)
        passo = max(1, total // max(1, paginas))
        numeros = list(range(0, total, passo))[:paginas]
        carimbo = produtor(doc)
        aceitas = sum(1 for n in numeros
                      if avaliar_pagina(doc[n], numero=n, produtor=carimbo).aceita)
    return aceitas, len(numeros)


# ----------------------------------------------------------------------
# Os glifos da página
# ----------------------------------------------------------------------

@dataclass(slots=True, eq=False)
class _Glifo:
    c: str
    x0: float
    y0: float
    x1: float
    y1: float
    base: float
    tamanho: float
    fonte: str
    negrito: bool
    #: `(bloco, linha)` do MuPDF: a linha que ele montou, antes de qualquer
    #: regra nossa.
    linha: Tuple[int, int]

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


_NEGRITO_NO_NOME = ("bold", "black", "heavy", "semibold", "demi")


def _e_negrito(nome: str, flags: int) -> bool:
    """O span é negrito pela bandeira ou pelo nome — a `TimesNewRomanPS-BoldMT`
    do Dvoretsky não liga a bandeira 16, e o nome é o que o compositor escolheu."""
    chave = _chave(nome)
    return bool(flags & 16) or any(p in chave for p in _NEGRITO_NO_NOME)


def _glifos(page: fitz.Page) -> List[_Glifo]:
    """Todo glifo horizontal e de corpo legível da página, na ordem do MuPDF."""
    saida: List[_Glifo] = []
    bruto = page.get_text("rawdict", flags=FLAGS_DO_TEXTO)
    for b, bloco in enumerate(bruto.get("blocks", ())):
        if bloco.get("type", 0) != 0:
            continue
        for k, linha in enumerate(bloco.get("lines", ())):
            direcao = linha.get("dir") or (1.0, 0.0)
            if abs(float(direcao[1])) > 0.1:
                continue
            for span in linha.get("spans", ()):
                tamanho = float(span.get("size") or 0.0)
                if tamanho < TAMANHO_MINIMO:
                    continue
                fonte = str(span.get("font") or "")
                xadrez = _de_xadrez(fonte)
                negrito = _e_negrito(fonte, int(span.get("flags") or 0))
                for ch in span.get("chars", ()):
                    c = ch.get("c") or ""
                    if not c:
                        continue
                    if xadrez:
                        c = _sem_simbolo(c)
                    x0, y0, x1, y1 = (float(v) for v in ch["bbox"])
                    origem = ch.get("origin") or (x0, y1)
                    saida.append(_Glifo(c, x0, y0, x1, y1, float(origem[1]),
                                        tamanho, fonte, negrito, (b, k)))
    return saida


# ----------------------------------------------------------------------
# Os tabuleiros compostos em fonte
# ----------------------------------------------------------------------

@dataclass(eq=False)
class _Tabuleiro:
    """Um diagrama composto em fonte, já decodificado — como impresso."""

    caixa: Tuple[float, float, float, float]
    casa: float
    #: 8×8, linha 0 = a de cima **como impressa**; `None` é casa vazia.
    impresso: List[List[Optional[str]]]
    #: `(linha, coluna)` impressas das casas marcadas.
    marcas: List[Tuple[int, int]]
    fonte_pdf: str
    #: A orientação que a moldura em glifo disse, quando ela traz rótulo.
    orientacao_da_moldura: Optional[str] = None
    glifos: List[_Glifo] = field(default_factory=list)


#: A folga, em casas, com que um glifo encosta no vizinho do mesmo tabuleiro.
#:
#: Casas vizinhas distam exatamente uma casa, de centro a centro — na diagonal
#: também, porque a distância é por eixo. A folga de 0,2 é o que separa dois
#: diagramas lado a lado: com 1,5, dois tabuleiros a menos de meia casa um do
#: outro viravam um grupo de 128 glifos que não fecha 8×8, e os dois se perdiam.
VIZINHANCA = 1.2

#: Casas impressas que um tabuleiro precisa ter para valer como tal. A casa
#: clara vazia pode vir como espaço (é uma das duas formas do teclado da
#: Merida), e um PDF pode omitir o espaço; a escura nunca — são 32 por
#: tabuleiro, e com elas a grade inteira fica determinada.
CASAS_MINIMAS = 32


class _Conjuntos:
    """União-busca mínima para juntar glifos vizinhos em tabuleiros."""

    def __init__(self, n: int):
        self.pai = list(range(n))

    def raiz(self, i: int) -> int:
        while self.pai[i] != i:
            self.pai[i] = self.pai[self.pai[i]]
            i = self.pai[i]
        return i

    def unir(self, a: int, b: int) -> None:
        ra, rb = self.raiz(a), self.raiz(b)
        if ra != rb:
            self.pai[rb] = ra


def _componentes(glifos: Sequence[_Glifo], passo: float) -> List[List[_Glifo]]:
    """Os glifos agrupados por vizinhança — cada grupo é candidato a tabuleiro."""
    alcance = max(passo * VIZINHANCA, 1e-6)
    grade: Dict[Tuple[int, int], List[int]] = collections.defaultdict(list)
    for i, g in enumerate(glifos):
        grade[(int(g.cx // alcance), int(g.cy // alcance))].append(i)
    conjuntos = _Conjuntos(len(glifos))
    for (gx, gy), indices in grade.items():
        vizinhos = [j for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                    for j in grade.get((gx + dx, gy + dy), ())]
        for i in indices:
            gi = glifos[i]
            for j in vizinhos:
                if j > i:
                    gj = glifos[j]
                    if abs(gi.cx - gj.cx) <= alcance and abs(gi.cy - gj.cy) <= alcance:
                        conjuntos.unir(i, j)
    grupos: Dict[int, List[_Glifo]] = collections.defaultdict(list)
    for i, g in enumerate(glifos):
        grupos[conjuntos.raiz(i)].append(g)
    return list(grupos.values())


def _orientacao_dos_votos(votos: "collections.Counter[str]") -> Optional[str]:
    """Quatro rótulos concordando e nenhum contra — a régua de
    `diagrama._orientacao_dos_rotulos` para o scan."""
    if votos["branca"] >= 4 and not votos["preta"]:
        return "branca"
    if votos["preta"] >= 4 and not votos["branca"]:
        return "preta"
    return None


def _grade(grupo: Sequence[_Glifo], mapa: MapaDeDiagrama) -> Optional[_Tabuleiro]:
    """
    Um grupo de glifos vira tabuleiro — ou `None`, se não fecha 8×8.

    **A paridade das casas é a prova do mapa.** Cada glifo de casa diz a cor da
    casa em que está (a Merida tem uma letra para o rei em casa clara e outra
    para o rei em casa escura), e a casa tem a cor que a posição dela manda —
    a8 é clara, e girar o tabuleiro não muda isso. Um mapa errado, ou uma grade
    deslocada de uma casa, erra a cor de metade das 64; aqui uma só já recusa.
    É o que impede o decodificador de afirmar uma posição lida com o teclado de
    outra fonte.
    """
    casas = [g for g in grupo if mapa.de_casa(g.c)]
    if len(casas) < CASAS_MINIMAS:
        return None
    passo = statistics.median(g.x1 - g.x0 for g in casas)
    if passo <= 0:
        return None
    x0 = min(g.x0 for g in casas)
    y0 = min(g.y0 for g in casas)
    posicoes: Dict[Tuple[int, int], _Glifo] = {}
    for g in casas:
        coluna = round((g.x0 - x0) / passo)
        linha = round((g.y0 - y0) / passo)
        if not (0 <= coluna < 8 and 0 <= linha < 8):
            return None
        if (abs(g.x0 - x0 - coluna * passo) > 0.25 * passo
                or abs(g.y0 - y0 - linha * passo) > 0.25 * passo):
            return None
        if (linha, coluna) in posicoes:
            return None
        posicoes[(linha, coluna)] = g
    if max(c for _l, c in posicoes) != 7 or max(lin for lin, _c in posicoes) != 7:
        return None
    for (linha, coluna), g in posicoes.items():
        esperada = "clara" if (linha + coluna) % 2 == 0 else "escura"
        if mapa.cor(g.c) != esperada:
            return None

    impresso: List[List[Optional[str]]] = [[None] * 8 for _ in range(8)]
    marcas: List[Tuple[int, int]] = []
    for (linha, coluna), g in posicoes.items():
        if g.c in mapa.casas:
            impresso[linha][coluna] = mapa.casas[g.c][0]
        else:
            marcas.append((linha, coluna))

    votos: "collections.Counter[str]" = collections.Counter()
    for g in grupo:
        if g.c in mapa.filas:
            linha = round((g.y0 - y0) / passo)
            fila = mapa.filas[g.c]
            votos["branca" if fila == 8 - linha else
                  "preta" if fila == linha + 1 else "?"] += 1
        elif g.c in mapa.colunas:
            coluna = round((g.x0 - x0) / passo)
            letra = mapa.colunas[g.c]
            votos["branca" if letra == coluna else
                  "preta" if letra == 7 - coluna else "?"] += 1
    caixa = (x0, y0, max(g.x1 for g in casas), max(g.y1 for g in casas))
    return _Tabuleiro(caixa, (caixa[2] - caixa[0]) / 8.0, impresso, sorted(marcas),
                      grupo[0].fonte, _orientacao_dos_votos(votos), list(grupo))


def _tabuleiros(glifos: Sequence[_Glifo]
                ) -> Tuple[List[_Tabuleiro], List[List[_Glifo]], List[_Glifo]]:
    """
    Os tabuleiros compostos em fonte de diagrama, os pedaços que não fecham e
    o que sobra solto.

    Os pedaços são grupos de quatro ou mais glifos de diagrama que não formam
    8×8 — o meio-tabuleiro que alguns livros imprimem para mostrar um canto.
    Eles não viram texto (seriam `l+*+` no meio da frase) e não viram FEN (não
    há posição inteira): saem como figura recortada do próprio PDF. Os soltos
    são os grupos menores — a figurina que o livro compôs na fonte do
    diagrama, no meio da frase, e o resto; quem decide o que fazer com cada um
    é `extrair_pagina`.
    """
    por_fonte: Dict[Tuple[str, int], List[_Glifo]] = collections.defaultdict(list)
    for g in glifos:
        mapa = mapa_de_diagrama(g.fonte)
        if mapa is None or not (mapa.de_casa(g.c) or g.c in mapa.moldura):
            continue
        por_fonte[(mapa.nome, round(g.tamanho))].append(g)

    tabuleiros: List[_Tabuleiro] = []
    pedacos: List[List[_Glifo]] = []
    soltos: List[_Glifo] = []
    for grupo in por_fonte.values():
        mapa = mapa_de_diagrama(grupo[0].fonte)
        passo = statistics.median(g.x1 - g.x0 for g in grupo) or grupo[0].tamanho
        for componente in _componentes(grupo, passo):
            tabuleiro = _grade(componente, mapa)
            if tabuleiro is not None:
                tabuleiros.append(tabuleiro)
            elif len(componente) >= 4:
                pedacos.append(componente)
            else:
                soltos.extend(componente)
    return tabuleiros, pedacos, soltos


def _peca_solta(g: _Glifo) -> bool:
    """O glifo solto de fonte de diagrama que é peça — e por isso figurina."""
    mapa = mapa_de_diagrama(g.fonte)
    return mapa is not None and g.c in mapa.casas and mapa.casas[g.c][0] is not None


# ----------------------------------------------------------------------
# Rótulos das casas em fonte de texto
# ----------------------------------------------------------------------

_FILAS = "12345678"
_COLUNAS = "abcdefgh"

#: A distância, em casas, até onde o rótulo impresso pode estar da borda.
ALCANCE_DO_ROTULO = 1.6


def _rotulos(tabuleiro: _Tabuleiro, glifos: Sequence[_Glifo],
             linhas_do_mupdf: Dict[Tuple[int, int], List[_Glifo]]
             ) -> Tuple[List[_Glifo], Optional[str]]:
    """
    Os rótulos `a`–`h` e `8`–`1` em volta do tabuleiro, e a orientação que eles dizem.

    **Só vale rótulo o glifo cuja linha do MuPDF é só rótulo** — `8`, `a b c`.
    Sem isso o `a` de "a pawn", começando a linha logo abaixo do diagrama,
    seria rótulo de coluna e sumiria do texto.
    """
    x0, y0, x1, y1 = tabuleiro.caixa
    casa = tabuleiro.casa
    alcance = casa * ALCANCE_DO_ROTULO
    folga = casa * 0.3
    usados: List[_Glifo] = []
    votos: "collections.Counter[str]" = collections.Counter()
    for g in glifos:
        if g.c not in _FILAS and g.c not in _COLUNAS:
            continue
        companheiros = [o for o in linhas_do_mupdf.get(g.linha, ()) if not o.c.isspace()]
        if len(companheiros) > 8 or any(o.c not in _FILAS + _COLUNAS
                                        for o in companheiros):
            continue
        lateral = (y0 <= g.cy <= y1
                   and ((x0 - alcance <= g.x0 and g.x1 <= x0 + folga)
                        or (x1 - folga <= g.x0 and g.x1 <= x1 + alcance)))
        horizontal = (x0 <= g.cx <= x1
                      and ((y1 - folga <= g.y0 and g.y1 <= y1 + alcance)
                           or (y0 - alcance <= g.y0 and g.y1 <= y0 + folga)))
        if lateral and g.c in _FILAS:
            fila = int(g.c)
            impressa = min(7, max(0, int((g.cy - y0) / casa)))
            votos["branca" if fila == 8 - impressa else
                  "preta" if fila == impressa + 1 else "?"] += 1
            usados.append(g)
        elif horizontal and g.c in _COLUNAS:
            coluna = min(7, max(0, int((g.cx - x0) / casa)))
            letra = _COLUNAS.index(g.c)
            votos["branca" if letra == coluna else
                  "preta" if letra == 7 - coluna else "?"] += 1
            usados.append(g)
    return usados, _orientacao_dos_votos(votos)


# ----------------------------------------------------------------------
# As linhas de texto
# ----------------------------------------------------------------------

@dataclass(eq=False)
class _Linha:
    glifos: List[_Glifo]
    texto: str = ""
    #: `negrito[i]` diz se o caractere `texto[i]` está impresso em negrito.
    negrito: List[bool] = field(default_factory=list)
    coluna: int = 0
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0
    base: float = 0.0
    tamanho: float = 0.0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def todo_negrito(self) -> bool:
        cheios = [n for c, n in zip(self.texto, self.negrito) if not c.isspace()]
        return bool(cheios) and all(cheios)


#: O vão entre dois glifos que vale espaço, em corpos da letra, quando o PDF
#: não pôs o espaço como caractere. O Dvoretsky põe; há compositor que não.
VAO_DE_ESPACO = 0.25

#: O vão, em corpos, a partir do qual dois pedaços na mesma altura não são a
#: mesma linha — é a calha entre duas colunas.
VAO_DE_COLUNA = 2.0


def _caractere(g: _Glifo) -> str:
    """O que o glifo quer dizer no texto corrido."""
    mapa = mapa_de_figurina(g.fonte)
    if mapa is not None:
        return mapa.get(g.c, g.c)
    diagrama = mapa_de_diagrama(g.fonte)
    if diagrama is not None and g.c in diagrama.casas:
        letra = diagrama.casas[g.c][0]
        return _FIGURINA_DA_LETRA.get((letra or "").upper(), g.c)
    return EQUIVALENTES.get(g.c, g.c)


def _montar(glifos: List[_Glifo]) -> _Linha:
    """
    Texto, negrito e medidas de uma linha, com o espaço que o vão pede.

    **A figurina não diz se o lance é negrito.** O Dvoretsky compõe `1...♔c7!`
    em Times negrito com o rei na `SemFigNormal` — a fonte de figurina tem os
    dois pesos, e o compositor nem sempre escolhe o certo —, e o lance saía
    `<strong>1...</strong>♔<strong>c7!</strong>`. O glifo de fonte de xadrez
    fica com o negrito dos vizinhos quando os dois concordam.
    """
    glifos = sorted(glifos, key=lambda o: o.x0)
    texto: List[str] = []
    negrito: List[bool] = []
    neutros: List[int] = []
    anterior: Optional[_Glifo] = None
    for g in glifos:
        if (anterior is not None and not g.c.isspace() and not anterior.c.isspace()
                and g.x0 - anterior.x1 > VAO_DE_ESPACO * max(g.tamanho, anterior.tamanho)
                and texto and texto[-1] != " "):
            texto.append(" ")
            negrito.append(anterior.negrito and g.negrito)
        pedaco = " " if g.c.isspace() else _caractere(g)
        xadrez = not g.c.isspace() and _de_xadrez(g.fonte)
        for c in pedaco:
            if c == " " and (not texto or texto[-1] == " "):
                continue
            if xadrez:
                neutros.append(len(texto))
            texto.append(c)
            negrito.append(g.negrito)
        anterior = g
    while texto and texto[-1] == " ":
        texto.pop()
        negrito.pop()
    de_xadrez = set(neutros)
    for i in neutros:
        if i >= len(texto):
            continue
        antes = next((negrito[k] for k in range(i - 1, -1, -1)
                      if k not in de_xadrez and not texto[k].isspace()), None)
        depois = next((negrito[k] for k in range(i + 1, len(texto))
                       if k not in de_xadrez and not texto[k].isspace()), None)
        if antes is not None and antes == depois:
            negrito[i] = antes
    cheios = [g for g in glifos if not g.c.isspace()] or glifos
    return _Linha(glifos, "".join(texto), negrito,
                  x0=min(g.x0 for g in cheios), y0=min(g.y0 for g in cheios),
                  x1=max(g.x1 for g in cheios), y1=max(g.y1 for g in cheios),
                  base=statistics.median(g.base for g in cheios),
                  tamanho=statistics.median(g.tamanho for g in cheios))


def _linhas(glifos: Sequence[_Glifo]) -> List[_Linha]:
    """
    Os glifos de texto em linhas, e cada linha com o seu texto.

    Parte da linha do MuPDF, que já junta o que está na mesma altura, e corrige
    os dois defeitos dela: a linha que atravessa a calha (dois pedaços longe
    demais para serem a mesma frase) e a mesma linha impressa partida em duas.
    """
    por_linha: Dict[Tuple[int, int], List[_Glifo]] = collections.defaultdict(list)
    for g in glifos:
        por_linha[g.linha].append(g)

    pedacos: List[_Linha] = []
    for membros in por_linha.values():
        membros.sort(key=lambda o: o.x0)
        atual = [membros[0]]
        for g in membros[1:]:
            if g.x0 - atual[-1].x1 > VAO_DE_COLUNA * max(g.tamanho, atual[-1].tamanho):
                pedacos.append(_montar(atual))
                atual = []
            atual.append(g)
        pedacos.append(_montar(atual))

    pedacos.sort(key=lambda p: (p.base, p.x0))
    juntos: List[_Linha] = []
    for pedaco in pedacos:
        for alvo in reversed(juntos[-6:]):
            corpo = max(pedaco.tamanho, alvo.tamanho)
            if (abs(pedaco.base - alvo.base) <= 0.35 * corpo
                    and 0 <= pedaco.x0 - alvo.x1 <= VAO_DE_COLUNA * corpo):
                indice = juntos.index(alvo)
                juntos[indice] = _montar(alvo.glifos + pedaco.glifos)
                break
        else:
            juntos.append(pedaco)
    return [linha for linha in juntos if linha.texto.strip()]


def _colunas(linhas: Sequence[_Linha], escala: float) -> List[Tuple[int, int]]:
    """
    As colunas da página, em pixels, pela mesma régua que o OCR usa.

    `BoxService.detectar_colunas` projeta as caixas de caractere e procura a
    calha; aqui as caixas vêm da camada em vez da segmentação, e a pergunta é a
    mesma. Uma régua só para os dois caminhos é o que faz a página de duas
    colunas sair em duas colunas pelos dois.
    """
    from core.services.box_service import BoxService

    caixas = []
    for linha in linhas:
        for g in linha.glifos:
            if g.c.isspace():
                continue
            x0, y0 = int(g.x0 * escala), int(g.y0 * escala)
            caixas.append(BoxEntry(g.c, x0, y0, max(x0 + 1, int(g.x1 * escala)),
                                   max(y0 + 1, int(g.y1 * escala))))
    if not caixas:
        return []
    return BoxService.detectar_colunas(caixas)


# ----------------------------------------------------------------------
# Parágrafos e títulos
# ----------------------------------------------------------------------

#: O recuo que abre parágrafo, em corpos da letra. O do Dvoretsky é 10,9 pt
#: num corpo de 14,6 (0,75); a régua fica na metade, longe do alinhamento
#: justificado, que não recua nada.
RECUO_DE_PARAGRAFO = 0.35

#: O salto que abre parágrafo, em passos de linha além do passo — o mesmo
#: número do OCR (`livro.SALTO_DE_PARAGRAFO`), porque é a mesma pergunta.
SALTO_DE_PARAGRAFO = livro.SALTO_DE_PARAGRAFO

#: Quanto o corpo de uma linha precisa passar o do texto para ela ser título
#: de capítulo. O Dvoretsky compõe o texto a 14,6 pt e os títulos a 18,9 (1,29).
TITULO_POR_CORPO = 1.2

#: O título de seção é negrito, curto e sem pontuação de frase no fim.
PALAVRAS_DE_TITULO = 10
_FIM_DE_FRASE = tuple(".,;:!?")

#: Os hífens de fim de linha — o mesmo conjunto que o léxico junta.
_HIFENS = lexico.HIFENS
#: O hífen brando (U+00AD), escrito por código: literal, ele some da tela.
_HIFEN_BRANDO = chr(0xAD)


@dataclass
class _Metricas:
    margem: Dict[int, float]
    #: Onde as linhas da coluna acabam — a mais comprida, que no texto
    #: alinhado só à esquerda (o Dvoretsky) é a borda da coluna.
    direita: Dict[int, float]
    passo: Dict[int, float]
    corpo: float
    #: O recuo de parágrafo da coluna, quando ela tem um: a moda dos recuos
    #: pequenos (10,9 pt no Dvoretsky).
    recuo: Dict[int, float] = field(default_factory=dict)


def _metricas(linhas: Sequence[_Linha]) -> _Metricas:
    """
    Margem, borda e passo de cada coluna, e o corpo do texto da página.

    A margem é a **moda** das esquerdas, e não a mediana: no Dvoretsky um
    quinto das linhas abre parágrafo com recuo, e numa coluna curta a mediana
    cairia no recuo. O corpo é o que escreve mais caracteres na página.
    """
    por_coluna: Dict[int, List[_Linha]] = collections.defaultdict(list)
    for linha in linhas:
        por_coluna[linha.coluna].append(linha)
    margem: Dict[int, float] = {}
    direita: Dict[int, float] = {}
    passo: Dict[int, float] = {}
    recuo: Dict[int, float] = {}
    for coluna, desta in por_coluna.items():
        esquerdas = collections.Counter(round(linha.x0) for linha in desta)
        maximo = max(esquerdas.values())
        margem[coluna] = float(min(x for x, n in esquerdas.items() if n == maximo))
        direita[coluna] = max(linha.x1 for linha in desta)
        bases = sorted(linha.base for linha in desta)
        corpo = statistics.median(linha.tamanho for linha in desta)
        saltos = [b - a for a, b in zip(bases, bases[1:])
                  if 0.5 * corpo < b - a < 2.5 * corpo]
        passo[coluna] = statistics.median(saltos) if saltos else 1.2 * corpo
        recuos = collections.Counter(
            round((linha.x0 - margem[coluna]) * 2) / 2 for linha in desta
            if RECUO_DE_PARAGRAFO * linha.tamanho < linha.x0 - margem[coluna]
            < 3 * linha.tamanho)
        if recuos:
            recuo[coluna] = recuos.most_common(1)[0][0]
    pesos: "collections.Counter[float]" = collections.Counter()
    for linha in linhas:
        pesos[round(linha.tamanho, 1)] += len(linha.texto)
    corpo = pesos.most_common(1)[0][0] if pesos else 10.0
    return _Metricas(margem, direita, passo, corpo, recuo)


def _abre_paragrafo(linha: _Linha, anterior: Optional[_Linha], m: _Metricas) -> bool:
    """
    Recuo, salto, troca de coluna ou de corpo — as regras do OCR, medidas aqui
    em pontos e sobre a linha que o arquivo diz, e não sobre a que a
    segmentação achou.
    """
    if anterior is None or linha.coluna != anterior.coluna:
        return True
    if linha.base <= anterior.base:
        return True
    if abs(linha.tamanho - anterior.tamanho) > 0.15 * m.corpo:
        return True
    passo = m.passo.get(linha.coluna, 1.2 * m.corpo)
    if linha.base - anterior.base > passo * (1 + SALTO_DE_PARAGRAFO):
        return True
    margem = m.margem.get(linha.coluna, linha.x0)
    return linha.x0 - margem > RECUO_DE_PARAGRAFO * linha.tamanho


def _forma_de_titulo(linha: _Linha, *, ultima: bool = True) -> bool:
    """
    Uma linha toda em negrito, curta, de letras e sem lance — e, se é a última
    do título, sem fim de frase.

    É o `The Rule of the Square`, o `Exercises` e o `Tragicomedies` do
    Dvoretsky. O `1...♔c7!` em negrito que abre a análise tem lance, e o `1-7`
    da legenda não tem letra — nenhum dos dois é título. Ter a forma não
    basta: ver `_secao`.
    """
    from core.notacao import e_token_de_notacao

    texto = linha.texto.strip()
    fim = texto.rstrip("”’\"')]» ")
    if not texto or not linha.todo_negrito or (ultima and fim.endswith(_FIM_DE_FRASE)):
        return False
    palavras = texto.split()
    if len(palavras) > PALAVRAS_DE_TITULO or sum(c.isalpha() for c in texto) < 2:
        return False
    return not any(e_token_de_notacao(p) for p in palavras)


def _centrada_na_coluna(linha: _Linha, m: _Metricas) -> bool:
    """
    Recuada dos dois lados, e pelo mesmo tanto — a linha de título.

    A folga é de um corpo, ou 8% da coluna. **E a linha que começa exatamente
    no recuo de parágrafo não é centrada**, por mais que acabe perto da borda:
    é a primeira linha de um parágrafo — no Dvoretsky, a de todo quadro em
    negrito itálico, que por isso saía título.
    """
    esquerda = m.margem.get(linha.coluna, linha.x0)
    direita = m.direita.get(linha.coluna, linha.x1)
    antes, depois = linha.x0 - esquerda, direita - linha.x1
    recuo = RECUO_DE_PARAGRAFO * linha.tamanho
    tipico = m.recuo.get(linha.coluna)
    if tipico is not None and abs(antes - tipico) <= 1.0:
        return False
    return (antes > recuo and depois > recuo
            and abs(antes - depois) <= max(0.08 * (direita - esquerda), linha.tamanho))


#: Linhas de um título de seção, no máximo.
LINHAS_DE_TITULO = 3


def _continua_titulo(grupo: Sequence[_Linha], linha: _Linha, m: _Metricas) -> bool:
    """
    A linha é a continuação de um título de seção em várias linhas?

    `The Rook Is in Front of the Pawn and` / `the Pawn Is on the Seventh Rank`
    é um título só: a segunda linha é centrada — e por isso "recuada", o que
    abriria parágrafo —, está no mesmo negrito, no mesmo corpo e no passo
    normal da coluna, sem o respiro que separa um título do que vem depois.
    """
    if len(grupo) >= LINHAS_DE_TITULO or not all(
            _forma_de_titulo(anterior, ultima=False) for anterior in grupo):
        return False
    ultima = grupo[-1]
    passo = m.passo.get(linha.coluna, 1.2 * m.corpo)
    return (linha.coluna == ultima.coluna
            and _forma_de_titulo(linha, ultima=False)
            and _centrada_na_coluna(linha, m)
            and abs(linha.tamanho - ultima.tamanho) < 0.5
            and 0 < linha.base - ultima.base <= 1.1 * passo)


def _secao(grupo: Sequence[_Linha], antes: Optional[_Linha], depois: Optional[_Linha],
           m: _Metricas) -> bool:
    """
    O título de seção: a forma de `_forma_de_titulo` **e** isolado na coluna.

    **A forma sozinha disparava em cascata.** O Dvoretsky compõe parágrafos
    inteiros em negrito itálico — a definição de "casas-chave" da p. 18, a
    frase que continua da página anterior —, e cada linha deles tem a forma de
    título: toda em negrito, curta, sem ponto no fim. Com a forma sozinha, o
    parágrafo saía como uma escada de `<h2>`, uma linha por degrau. O título de
    verdade está isolado — centrado na coluna, ou com um salto antes ou depois
    — e não é o começo de uma frase: a linha que o segue e começa em minúscula,
    sem abrir parágrafo, continua a frase que ele começou.
    """
    if len(grupo) > LINHAS_DE_TITULO or not all(
            _forma_de_titulo(linha, ultima=i == len(grupo) - 1)
            for i, linha in enumerate(grupo)):
        return False
    primeira, ultima = grupo[0], grupo[-1]
    if (depois is not None and depois.texto[:1].islower()
            and not _abre_paragrafo(depois, ultima, m)):
        return False
    centradas = [_centrada_na_coluna(linha, m) for linha in grupo]
    if len(grupo) > 1:
        # Título de várias linhas só existe com as de baixo centradas, que é
        # como `_continua_titulo` o monta — a primeira pode encher a coluna
        # (`The Rook Is in Front of the Pawn and`). Linhas em negrito que seguem
        # a primeira desde a margem são um parágrafo em negrito, e o Dvoretsky
        # tem dezenas: a primeira linha deles, com o recuo de parágrafo e o fim
        # perto da borda, passa por centrada.
        return all(centradas[1:])
    if centradas[0]:
        return True
    passo = m.passo.get(primeira.coluna, 1.2 * m.corpo) * (1 + SALTO_DE_PARAGRAFO)
    return ((antes is not None and antes.coluna == primeira.coluna
             and primeira.base - antes.base > passo)
            or (depois is not None and depois.coluna == ultima.coluna
                and depois.base - ultima.base > passo))


def _juntar(linhas: Sequence[_Linha], lex) -> Tuple[str, List[bool], List[int]]:
    """
    As linhas de um parágrafo num texto só, com o negrito e o começo de cada linha.

    **O hífen do fim da linha fica, a não ser que o dicionário diga que era
    quebra.** O Dvoretsky não hifeniza palavra: os 567 hífens de fim de linha
    dele são `f-`+`file`, `German-`+`English`, `diagram 1-`+`17` — hífen de
    verdade, e juntar sem ele daria `ffile`. Quem decide que um `outflank-`+
    `ing` era quebra é o mesmo `lexico.juntar_hifenizadas` do OCR; sem léxico o
    hífen fica, e a palavra continua inteira, sem espaço no meio. O hífen
    brando (U+00AD) é quebra por definição: some do texto, e o que ele fechava
    no fim da linha junta com a seguinte sem espaço.
    """
    juntas: set = set()
    if lex is not None and not lex.vazio:
        palavras = [linha.texto.split(" ") for linha in linhas]
        juntas = {juncao.linha for juncao in lexico.juntar_hifenizadas(palavras, lex)}

    texto = ""
    negrito: List[bool] = []
    inicios: List[int] = []
    branda = False
    for i, linha in enumerate(linhas):
        pedaco, marcas = linha.texto, list(linha.negrito)
        termina_branda = pedaco.endswith(_HIFEN_BRANDO)
        if _HIFEN_BRANDO in pedaco:
            mantidos = [(c, n) for c, n in zip(pedaco, marcas) if c != _HIFEN_BRANDO]
            pedaco = "".join(c for c, _n in mantidos)
            marcas = [n for _c, n in mantidos]
        if i:
            anterior = linhas[i - 1].texto
            if branda:
                pass
            elif i - 1 in juntas:
                corte = len(texto.rstrip(_HIFENS))
                texto, negrito = texto[:corte], negrito[:corte]
            elif not (anterior.endswith(tuple(_HIFENS)) and len(anterior) > 1
                      and anterior[-2].isalnum() and pedaco[:1].isalnum()):
                texto += " "
                negrito.append(bool(negrito and negrito[-1] and marcas and marcas[0]))
        inicios.append(len(texto))
        texto += pedaco
        negrito.extend(marcas)
        branda = termina_branda
    return texto, negrito, inicios


def _trechos_negritos(texto: str, negrito: Sequence[bool]) -> List[Tuple[int, int]]:
    """As fatias `(início, fim)` em negrito, sem espaço nas pontas."""
    trechos: List[Tuple[int, int]] = []
    inicio = None
    for i, (c, n) in enumerate(zip(texto, negrito)):
        if n and inicio is None and not c.isspace():
            inicio = i
        elif not n and inicio is not None:
            trechos.append((inicio, i))
            inicio = None
    if inicio is not None:
        trechos.append((inicio, len(texto)))
    saida = []
    for a, b in trechos:
        while b > a and texto[b - 1].isspace():
            b -= 1
        if b > a:
            saida.append((a, b))
    return saida


def _capitulo(grupo: Sequence[_Linha], m: _Metricas) -> bool:
    return statistics.median(linha.tamanho for linha in grupo) >= TITULO_POR_CORPO * m.corpo


def _paragrafos(linhas: Sequence[_Linha], m: _Metricas, escala: float, lex
                ) -> List["livro.Paragrafo"]:
    """
    Linhas → parágrafos, e o título de cada nível.

    Dois ajustes sobre o agrupamento: o título de seção isolado (`_secao`)
    fecha o parágrafo dele — a linha que vem depois não herda o `<h2>`, mesmo
    sem recuo —, e o título de capítulo em duas linhas centradas — `Chapter 1`
    / `Pawn Endgames` — volta a ser um só: a segunda linha abre parágrafo pelo
    recuo, e dois `<h1>` seguidos poriam dois capítulos no sumário onde o livro
    tem um.
    """
    grupos: List[List[_Linha]] = []
    antes_do_grupo: List[Optional[_Linha]] = []
    for k, linha in enumerate(linhas):
        anterior = linhas[k - 1] if k else None
        if grupos and _continua_titulo(grupos[-1], linha, m):
            grupos[-1].append(linha)
            continue
        abre = _abre_paragrafo(linha, anterior, m)
        if not abre and grupos and len(grupos[-1]) <= LINHAS_DE_TITULO:
            abre = _secao(grupos[-1], antes_do_grupo[-1], linha, m)
        if abre:
            grupos.append([])
            antes_do_grupo.append(anterior)
        grupos[-1].append(linha)

    fundidos: List[List[_Linha]] = []
    for grupo in grupos:
        if fundidos:
            ultimo = fundidos[-1]
            if (_capitulo(ultimo, m) and _capitulo(grupo, m)
                    and abs(ultimo[-1].tamanho - grupo[0].tamanho) < 0.5
                    and grupo[0].y0 - ultimo[-1].y1 <= grupo[0].tamanho):
                ultimo.extend(grupo)
                continue
        fundidos.append(list(grupo))

    saida = []
    for indice, grupo in enumerate(fundidos):
        texto, negrito, inicios = _juntar(grupo, lex)
        capitulo = _capitulo(grupo, m)
        antes = fundidos[indice - 1][-1] if indice else None
        depois = fundidos[indice + 1][0] if indice + 1 < len(fundidos) else None
        titulo = capitulo or _secao(grupo, antes, depois, m)
        saida.append(livro.Paragrafo(
            texto, titulo=titulo, nivel=1 if capitulo else 2,
            # Título não leva marca: o `<h1>`/`<h2>` já desenha negrito, e o
            # OCR também não marca título (`negrito.marcar`).
            negrito=[] if titulo else _trechos_negritos(texto, negrito),
            topo=int(min(linha.y0 for linha in grupo) * escala),
            pe=int(round(max(linha.y1 for linha in grupo) * escala)),
            inicios=inicios, registros=[]))
    return saida


# ----------------------------------------------------------------------
# Cabeçalho e legenda do diagrama
# ----------------------------------------------------------------------

#: O número do diagrama: `1-7`, `12-42`, `(9-220)`, `1-99*`, `Diagram 23`, `(23)`.
_NUMERO_DO_DIAGRAMA = re.compile(
    r"^(?:\(?(?:diagrama?\s+|diag\.\s*)\d{1,3}[a-z]?\)?"
    r"|\(?\d{1,3}[-–.]\d{1,4}[a-z]?\)?"
    r"|\(\d{1,3}[a-z]?\))\*?$", re.I)

#: O número sozinho — `23` embaixo do diagrama. **É também a cara de um número
#: de página**, e por isso não é legenda estrita: só vale colado ao tabuleiro
#: (`NUMERO_COLADO`), e nunca do outro lado da coluna nem na página seguinte,
#: onde o fólio do pé ou do alto seria levado para dentro da legenda.
_NUMERO_SOLTO = re.compile(r"^\d{1,3}[a-z]?\*?$")

#: Até onde, em casas abaixo do tabuleiro, o número sozinho é legenda — a
#: fila de letras `a`–`h` e mais um respiro.
NUMERO_COLADO = 1.5

#: O número do exercício que o Dvoretsky põe entre o do diagrama e a letra do
#: lado: `1/4` é o quarto exercício do capítulo 1.
_NUMERO_DO_EXERCICIO = re.compile(r"^\d{1,2}/\d{1,3}$")

#: A letra sozinha que diz de quem é a vez, por idioma — com o `?` do exercício.
#:
#: **Medido no Dvoretsky**: 315 diagramas trazem `W`, `W?`, `B` ou `B?` embaixo
#: do número, e em 315 de 315 o primeiro lance do texto que segue é o do lado
#: que a letra diz (`1.` depois de `W`, `1...` depois de `B`). Só o inglês: em
#: português o `B` seria das brancas, e a regra de um idioma aplicada ao outro
#: inverteria o lado de todo diagrama em silêncio.
MARCAS_DO_LADO = {"en": {"W": "w", "B": "b"}}

_MARCA_DO_LADO = re.compile(r"^([A-Z])\??$")

#: Onde o cabeçalho pode estar, em casas acima do tabuleiro, e a legenda,
#: abaixo. Medido no Dvoretsky, a linha centrada mais próxima acima de cada
#: tabuleiro está a 1,5 casa (76 de 113 amostrados) ou a 2,25–2,5 (22); o resto
#: se espalha de 3 casas para cima, e é texto de outra coisa. A legenda vem
#: depois da fila de letras `a`–`h`, e o livro põe o número a ~3,3 casas da
#: borda de baixo.
ALCANCE_DO_CABECALHO = 2.75
ALCANCE_DA_LEGENDA = 4.0

#: A legenda que não é número nem letra de lado ainda é legenda se for curta e
#: centrada sob o tabuleiro — `White to play`, `Kasparov – Karpov, 1985`.
CARACTERES_DE_LEGENDA = 40

#: Linhas de legenda, no máximo: `1-17` / `1/4` / `W?` / `Play` no Dvoretsky.
LINHAS_DE_LEGENDA = 4

#: A linha curta que, colada à anterior da legenda, ainda é legenda (`Play`).
CARACTERES_DE_COMPLEMENTO = 12


def _lado_da_marca(texto: str, idioma: str) -> Optional[str]:
    achado = _MARCA_DO_LADO.match(texto.strip())
    if not achado:
        return None
    return MARCAS_DO_LADO.get(idioma, {}).get(achado.group(1))


def legenda_estrita(texto: str, idioma: str = "en") -> bool:
    """O texto é o número do diagrama, o do exercício ou a letra de quem joga?"""
    texto = texto.strip()
    return (bool(_NUMERO_DO_DIAGRAMA.match(texto))
            or bool(_NUMERO_DO_EXERCICIO.match(texto))
            or _lado_da_marca(texto, idioma) is not None)


#: O quanto o centro de uma linha pode fugir do centro do tabuleiro, em
#: larguras dele, para ela ser o cabeçalho ou a legenda do diagrama. Medido no
#: Dvoretsky: 259 dos 261 cabeçalhos achados ficam a −0,04 ou −0,06 (o rótulo
#: das filas puxa o desenho para a esquerda); os dois de −0,16 e −0,20 eram a
#: última linha do parágrafo de cima.
DESVIO_DO_CENTRO = 0.1


def _centrada(linha: _Linha, caixa: Sequence[float]) -> bool:
    x0, _y0, x1, _y1 = caixa
    largura = x1 - x0
    return (linha.x1 - linha.x0 <= 0.95 * largura
            and abs(linha.cx - (x0 + x1) / 2) <= DESVIO_DO_CENTRO * largura)


def _lado_a_lado(a: _Tabuleiro, b: _Tabuleiro) -> bool:
    """Dois tabuleiros na mesma fileira da página — o par de diagramas."""
    return a is not b and min(a.caixa[3], b.caixa[3]) - max(a.caixa[1], b.caixa[1]) > a.casa


def _sob_outro(linha: _Linha, tabuleiro: _Tabuleiro,
               vizinhos: Sequence[_Tabuleiro]) -> bool:
    """A linha está alinhada com o vizinho da mesma fileira, e não com este."""
    x0, _y0, x1, _y1 = tabuleiro.caixa
    if x0 <= linha.cx <= x1:
        return False
    return any(v.caixa[0] <= linha.cx <= v.caixa[2] for v in vizinhos)


def _cabecalho(fluxo: Sequence[object], posicao: int, coluna: int,
               tabuleiro: _Tabuleiro, tomadas: set,
               vizinhos: Sequence[_Tabuleiro] = ()) -> List[_Linha]:
    """
    As linhas centradas logo acima do tabuleiro — o `H. Mattison 1918*`, o
    `Coull – Olarasu` —, até duas, coladas uma na outra.

    Saem como título do diagrama, como a faixa que o OCR lê acima do
    tabuleiro do Yusupov (`_faixa_em_texto`). O vizinho da mesma fileira e o
    cabeçalho dele ficam no caminho, e são pulados.
    """
    acima: List[_Linha] = []
    limite = tabuleiro.caixa[1]
    alcance = ALCANCE_DO_CABECALHO * tabuleiro.casa
    k = posicao - 1
    while k >= 0 and len(acima) < 2:
        anterior = fluxo[k]
        k -= 1
        if isinstance(anterior, tuple):
            if anterior[0] == "t" and any(v is anterior[2] for v in vizinhos):
                continue
            break
        if (not isinstance(anterior, _Linha) or anterior.coluna != coluna
                or id(anterior) in tomadas):
            break
        if _sob_outro(anterior, tabuleiro, vizinhos):
            continue
        distancia = limite - anterior.y1
        if not (-0.2 * tabuleiro.casa <= distancia <= alcance
                and _centrada(anterior, tabuleiro.caixa)):
            break
        acima.insert(0, anterior)
        limite = anterior.y0
        alcance = 0.8 * anterior.tamanho
    return acima


def _do_seguinte(linha: _Linha, seguintes: Sequence[_Tabuleiro]) -> bool:
    """A linha está na janela do cabeçalho de um tabuleiro de baixo, centrada nele."""
    return any(0 <= t.caixa[1] - linha.y1 <= ALCANCE_DO_CABECALHO * t.casa
               and _centrada(linha, t.caixa) for t in seguintes)


def _legenda(fluxo: Sequence[object], posicao: int, coluna: int,
             tabuleiro: _Tabuleiro, tomadas: set, idioma: str,
             vizinhos: Sequence[_Tabuleiro] = (),
             seguintes: Sequence[_Tabuleiro] = ()) -> List[_Linha]:
    """
    As linhas da legenda, embaixo do tabuleiro — até quatro.

    **Ela é procurada no fluxo de leitura, e não só na geometria**: no
    Dvoretsky o `1-8` fecha a coluna da esquerda e o `W?` abre a da direita. O
    número e a letra de lado valem em qualquer lugar da sequência; a legenda
    livre (`White to play`) só vale curta, centrada e perto. Com dois
    diagramas lado a lado (p. 782), as legendas dos dois se intercalam na
    ordem de leitura: a do vizinho — e o próprio vizinho — é pulada, e na mesma
    coluna só vale a linha que está debaixo **deste** tabuleiro.

    **Com dois diagramas empilhados, a linha do meio é de quem?** O número e a
    letra de lado vêm embaixo do tabuleiro, e são deste; o nome centrado
    (`H. Someone 1900`) vem em cima, e na janela de cabeçalho do de baixo
    (`seguintes`) ele é daquele — sem isto a legenda deste o engolia, e o de
    baixo ficava sem título.
    """
    embaixo: List[_Linha] = []
    x0, _y0, x1, fundo = tabuleiro.caixa
    folga = DESVIO_DO_CENTRO * (x1 - x0)
    k = posicao + 1
    while k < len(fluxo) and len(embaixo) < LINHAS_DE_LEGENDA:
        seguinte = fluxo[k]
        k += 1
        if isinstance(seguinte, tuple):
            if seguinte[0] == "t" and any(v is seguinte[2] for v in vizinhos):
                continue
            break
        if not isinstance(seguinte, _Linha):
            break
        if id(seguinte) in tomadas or (seguinte.coluna == coluna
                                       and _sob_outro(seguinte, tabuleiro, vizinhos)):
            continue
        texto = seguinte.texto.strip()
        mesma = seguinte.coluna == coluna
        perto = (mesma and seguinte.y0 >= fundo - 0.2 * tabuleiro.casa
                 and seguinte.y0 - fundo <= ALCANCE_DA_LEGENDA * tabuleiro.casa
                 and x0 - folga <= seguinte.cx <= x1 + folga)
        colada = (bool(embaixo) and seguinte.coluna == embaixo[-1].coluna
                  and 0 <= seguinte.y0 - embaixo[-1].y1 <= seguinte.tamanho)
        if _NUMERO_SOLTO.match(texto):
            if not ((perto and seguinte.y0 - fundo <= NUMERO_COLADO * tabuleiro.casa)
                    or colada):
                break
        elif legenda_estrita(texto, idioma):
            if not (perto or embaixo or not mesma):
                break
        elif _do_seguinte(seguinte, seguintes) or not (
                (perto and _centrada(seguinte, tabuleiro.caixa)
                 and len(texto) <= CARACTERES_DE_LEGENDA)
                or (colada and len(texto) <= CARACTERES_DE_COMPLEMENTO)):
            break
        embaixo.append(seguinte)
    return embaixo


def _lado(cabecalho: str, legendas: Sequence[str], idioma: str) -> Optional[str]:
    """
    De quem é a vez: a frase (`lado_a_jogar`) e a letra sozinha (`MARCAS_DO_LADO`).

    Os dois têm de concordar; discordando, ou a frase sendo ambígua, o lado
    fica por dizer — e o FEN o declara convenção, como no OCR.
    """
    lido = lado_jogar.ler_varios(cabecalho, " ".join(legendas))
    if lido.origem == "ambigua":
        return None
    marcas = {_lado_da_marca(texto, idioma) for texto in legendas} - {None}
    if len(marcas) > 1:
        return None
    if marcas:
        marca = marcas.pop()
        return marca if lido.lado in (None, marca) else None
    return lido.lado


# ----------------------------------------------------------------------
# As figuras
# ----------------------------------------------------------------------

def _png(pix: fitz.Pixmap, tons: int = livro.TONS_DA_FIGURA) -> Tuple[bytes, int, int]:
    modo = "L" if pix.n == 1 else "RGB"
    imagem = Image.frombytes(modo, (pix.width, pix.height), pix.samples)
    if tons and tons < 256:
        imagem = imagem.quantize(colors=tons)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), pix.width, pix.height


def _png_da_regiao(page: fitz.Page, caixa: Sequence[float], dpi: int) -> Tuple[bytes, int, int]:
    """A região da página desenhada do próprio PDF — vetor, e não digitalização."""
    retangulo = fitz.Rect(caixa) & page.rect
    return _png(page.get_pixmap(clip=retangulo, dpi=dpi, colorspace=fitz.csGRAY,
                                alpha=False))


def _posicao(impresso: Sequence[Sequence[Optional[str]]], orientacao: str) -> str:
    """O primeiro campo do FEN, a partir das casas **como impressas**."""
    filas = [list(fila) for fila in impresso]
    if orientacao == "preta":
        filas = [list(reversed(fila)) for fila in reversed(filas)]
    saida = []
    for fila in filas:
        texto, vazias = "", 0
        for simbolo in fila:
            if simbolo is None:
                vazias += 1
                continue
            if vazias:
                texto += str(vazias)
                vazias = 0
            texto += simbolo
        saida.append(texto + (str(vazias) if vazias else ""))
    return "/".join(saida)


def _nome_da_casa(linha: int, coluna: int, orientacao: str) -> str:
    if orientacao == "preta":
        return f"{_COLUNAS[7 - coluna]}{linha + 1}"
    return f"{_COLUNAS[coluna]}{8 - linha}"


@dataclass
class _Opcoes:
    dpi: int
    dpi_figura: int
    diagramas: str
    coordenadas: object
    fonte: str
    lado_do_diagrama: int
    moldura: object
    cantos: str
    idioma: str
    lex: object

    @property
    def escala(self) -> float:
        return self.dpi / 72.0

    def em_pixels(self, caixa: Sequence[float]) -> Tuple[int, ...]:
        return tuple(int(round(v * self.escala)) for v in caixa)


def _desenhada(fen: str, *, orientacao: str, lado: Optional[str], coordenadas: bool,
               marcas: Sequence[str], o: _Opcoes, caixa: Tuple[int, ...],
               aviso: Optional[str]) -> "livro.Figura":
    """A figura desenhada do FEN — as mesmas chamadas de `livro._figura_do_diagrama`."""
    png, largura, altura = render_diagrama.desenhar(
        fen, fonte=o.fonte, lado_px=o.lado_do_diagrama, coordenadas=coordenadas,
        moldura=o.moldura, cantos=o.cantos, orientacao=orientacao,
        lado_a_jogar=lado, marcas=marcas)
    objeto = render_diagrama.carregar(o.fonte)
    em_grade = (render_diagrama.grade(fen, objeto, orientacao, o.moldura, o.cantos)
                if coordenadas else None)
    return livro.Figura(
        png, largura, altura, fen=fen, origem="render", aviso=aviso,
        linhas=em_grade or render_diagrama.linhas(fen, objeto, orientacao),
        linhas_emolduradas=em_grade is not None, fonte=o.fonte,
        coordenadas=coordenadas, orientacao=orientacao,
        casas_de_largura=largura * 8.0 / render_diagrama.lado_efetivo(o.lado_do_diagrama),
        caixa=caixa, lado_a_jogar=lado,
        lado_origem="legenda" if lado else "convencao", marcas=list(marcas))


def _figura_do_tabuleiro(page: fitz.Page, tabuleiro: _Tabuleiro, *,
                         orientacao: Optional[str], rotulado: bool,
                         lado: Optional[str], o: _Opcoes) -> "livro.Figura":
    """
    O diagrama decodificado vira figura desenhada — pela mesma função do OCR.

    As marcas do livro (as casas-chave do `x`) entram como anel, que é a marca
    do editor (ED-05b). A orientação que nem os rótulos nem a moldura disseram
    vira aviso: o FEN supõe as brancas embaixo, e isso é convenção.
    """
    aviso = None
    if orientacao is None:
        orientacao = "branca"
        aviso = ("orientação não confirmada: o diagrama não imprime coordenadas, "
                 "e o FEN supõe as brancas embaixo")
    fen = f"{_posicao(tabuleiro.impresso, orientacao)} {lado or 'w'} - - 0 1"
    marcas = [_nome_da_casa(lin, col, orientacao) for lin, col in tabuleiro.marcas]
    quer = rotulado if o.coordenadas == livro.COMO_NO_LIVRO else bool(o.coordenadas)
    caixa = o.em_pixels(tabuleiro.caixa)
    if o.diagramas == "render":
        try:
            return _desenhada(fen, orientacao=orientacao, lado=lado, coordenadas=quer,
                              marcas=marcas, o=o, caixa=caixa, aviso=aviso)
        except (render_diagrama.FonteDesconhecida,
                render_diagrama.FonteIncompleta) as erro:
            aviso = f"não deu para desenhar: {erro}"
    # O recorte: pedido (`diagramas="recorte"`, que é escolha e não dúvida) ou
    # sem a fonte para desenhar. Ele sai do próprio PDF, em vetor, e o FEN vai
    # junto — aqui ele não é leitura de modelo, é o que o arquivo diz.
    margem = tabuleiro.casa * (ALCANCE_DO_ROTULO if quer else 0.1)
    x0, y0, x1, y1 = tabuleiro.caixa
    png, largura, altura = _png_da_regiao(
        page, (x0 - margem, y0 - margem, x1 + margem, y1 + margem), o.dpi_figura)
    return livro.Figura(png, largura, altura, fen=fen, origem="recorte",
                        aviso=aviso if o.diagramas == "render" else None,
                        coordenadas=quer, orientacao=orientacao,
                        casas_de_largura=8.0 * (x1 - x0 + 2 * margem) / (x1 - x0),
                        caixa=caixa, lado_a_jogar=lado,
                        lado_origem="legenda" if lado else "convencao",
                        marcas=marcas)


def _figura_de_pedaco(page: fitz.Page, glifos: Sequence[_Glifo], o: _Opcoes
                      ) -> "livro.Figura":
    caixa = (min(g.x0 for g in glifos), min(g.y0 for g in glifos),
             max(g.x1 for g in glifos), max(g.y1 for g in glifos))
    png, largura, altura = _png_da_regiao(page, caixa, o.dpi_figura)
    return livro.Figura(png, largura, altura, origem="recorte",
                        aviso="pedaço de tabuleiro em fonte de diagrama, sem as 64 casas",
                        caixa=o.em_pixels(caixa))


#: A menor imagem que entra no livro, em fração da área da página. Abaixo
#: disto é ornamento de composição (o filete, o marcador), e não figura.
AREA_MINIMA_DE_IMAGEM = 0.005


def _figura_da_imagem(page: fitz.Page, caixa: fitz.Rect, o: _Opcoes) -> "livro.Figura":
    """
    Uma imagem embutida numa página de camada.

    **O tabuleiro em imagem é lido como o OCR lê o dele**: localizado pela
    régua do xadrez (`deteccao_de_tabuleiro`), lido por `diagrama.ler` e
    desenhado só se o porteiro da F58 deixar. A diferença é que o recorte sai
    do PDF na resolução pedida, sem a digitalização no meio. A imagem que não é
    tabuleiro — a foto do autor, o logotipo — sai inteira, em cor, como a
    página de imagem do OCR.
    """
    import numpy as np

    pix = page.get_pixmap(clip=caixa, dpi=o.dpi, colorspace=fitz.csGRAY, alpha=False)
    cinza = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    try:
        from core import deteccao_de_tabuleiro, diagrama
    except ImportError:
        diagrama = None
    achados = (deteccao_de_tabuleiro.localizar(cinza, piso_do_xadrez=diagrama.PISO_DO_XADREZ)
               if diagrama is not None else [])
    if achados:
        tab = max(achados, key=lambda c: (c[2] - c[0]) * (c[3] - c[1]))
        leitura, passa, aviso = None, False, None
        if o.diagramas == "render":
            try:
                leitura = diagrama.ler(cinza, tab)
                passa, aviso = diagrama.confiavel(leitura)
            except (diagrama.ModeloAusente, ImportError) as erro:
                passa, aviso = False, f"sem o modelo de diagramas: {erro}"
        escala_da_imagem = o.dpi / 72.0
        na_pagina = (caixa.x0 + tab[0] / escala_da_imagem, caixa.y0 + tab[1] / escala_da_imagem,
                     caixa.x0 + tab[2] / escala_da_imagem, caixa.y0 + tab[3] / escala_da_imagem)
        if passa:
            try:
                return _desenhada(
                    leitura.fen(), orientacao="branca", lado=None,
                    coordenadas=bool(o.coordenadas is True), marcas=(), o=o,
                    caixa=o.em_pixels(na_pagina),
                    aviso=("orientação não confirmada: o tabuleiro é imagem, e os "
                           "rótulos dela não foram lidos"))
            except (render_diagrama.FonteDesconhecida,
                    render_diagrama.FonteIncompleta) as erro:
                aviso = f"não deu para desenhar: {erro}"
        png, largura, altura = _png(page.get_pixmap(
            clip=caixa, dpi=o.dpi_figura, colorspace=fitz.csGRAY, alpha=False))
        return livro.Figura(png, largura, altura, origem="recorte", aviso=aviso,
                            casas_de_largura=8.0 * caixa.width / max(
                                1e-6, na_pagina[2] - na_pagina[0]),
                            caixa=o.em_pixels(na_pagina))
    png, largura, altura = _png(page.get_pixmap(clip=caixa, dpi=o.dpi_figura,
                                                colorspace=fitz.csRGB, alpha=False),
                                tons=0)
    return livro.Figura(png, largura, altura, origem="pagina")


# ----------------------------------------------------------------------
# A página inteira
# ----------------------------------------------------------------------

def extrair_pagina(page: fitz.Page, *, numero: Optional[int] = None,
                   dpi: int = 300, dpi_figura: int = livro.DPI_FIGURA,
                   idioma: str = "en", lex=None, diagramas: str = "render",
                   coordenadas=False,
                   fonte: str = render_diagrama.FONTE_PADRAO,
                   lado_do_diagrama: int = render_diagrama.LADO_PADRAO,
                   moldura=render_diagrama.MOLDURA_PADRAO,
                   cantos: str = render_diagrama.CANTO_PADRAO
                   ) -> "livro.PaginaExtraida":
    """
    Uma página do PDF vira parágrafos e figuras, **lendo a camada**.

    As medidas saem em pixels a `dpi`, como as do OCR — `Paragrafo.topo`/`pe`,
    `Figura.caixa`, `PaginaExtraida.altura` —, e é isso que deixa o
    `retirar_cabecalhos`, a fila de revisão e o PDF pesquisável tratarem as
    duas páginas do mesmo jeito. Quem chama decide se a camada merece ser lida
    (`avaliar_pagina`); esta função lê o que houver.

    Os argumentos de diagrama são os de `livro.extrair_pagina`, e querem dizer o
    mesmo — `diagramas="recorte"` tira o tabuleiro do próprio PDF em vez de
    desenhá-lo, e o FEN vai junto; `idioma` decide a letra do lado a jogar
    (`MARCAS_DO_LADO`) e `lex` o hífen de fim de linha (`_juntar`).
    """
    if diagramas not in livro.MODOS_DE_DIAGRAMA:
        raise ValueError(f"modo de diagrama inválido: {diagramas!r} "
                         f"(use um de {livro.MODOS_DE_DIAGRAMA})")
    if coordenadas not in (True, False, livro.COMO_NO_LIVRO):
        raise ValueError(f"coordenadas inválidas: {coordenadas!r} "
                         f"(use True, False ou {livro.COMO_NO_LIVRO!r})")
    numero = page.number if numero is None else numero
    o = _Opcoes(dpi, dpi_figura, diagramas, coordenadas, fonte, lado_do_diagrama,
                moldura, cantos, (idioma or "en").lower()[:2], lex)

    glifos = _glifos(page)
    tabuleiros, pedacos, soltos = _tabuleiros(glifos)
    consumidos = {id(g) for t in tabuleiros for g in t.glifos}
    consumidos |= {id(g) for p in pedacos for g in p}
    # Do glifo de diagrama solto, só a peça fica no texto — é a figurina que o
    # livro compôs na fonte do diagrama. A casa vazia, a marca e o pedaço de
    # moldura soltos não dizem nada em prosa, e sairiam `*`, `+` ou `x` no meio
    # da frase.
    consumidos |= {id(g) for g in soltos if not _peca_solta(g)}
    restantes = [g for g in glifos if id(g) not in consumidos]

    # Os rótulos saem do texto, e dizem a orientação de cada tabuleiro.
    linhas_do_mupdf: Dict[Tuple[int, int], List[_Glifo]] = collections.defaultdict(list)
    for g in restantes:
        linhas_do_mupdf[g.linha].append(g)
    orientacoes: List[Optional[str]] = []
    rotulados: List[bool] = []
    for tabuleiro in tabuleiros:
        usados, pelos_rotulos = _rotulos(tabuleiro, restantes, linhas_do_mupdf)
        consumidos |= {id(g) for g in usados}
        orientacoes.append(tabuleiro.orientacao_da_moldura or pelos_rotulos)
        rotulados.append(bool(usados) or tabuleiro.orientacao_da_moldura is not None)
    linhas = _linhas([g for g in restantes if id(g) not in consumidos])

    area = abs(page.rect) or 1.0
    imagens = []
    for info in page.get_image_info():
        caixa = fitz.Rect(info.get("bbox") or (0, 0, 0, 0)) & page.rect
        if abs(caixa) >= AREA_MINIMA_DE_IMAGEM * area:
            imagens.append(caixa)

    colunas = _colunas(linhas, o.escala)
    for linha in linhas:
        linha.coluna = livro._coluna_de(linha.cx * o.escala, colunas)
    m = _metricas(linhas)

    # A ordem de leitura: coluna por coluna, de cima para baixo — a mesma do
    # OCR. O que não é linha entra pela coluna do centro dele.
    elementos: List[Tuple[int, float, int, object]] = []
    for linha in linhas:
        elementos.append((linha.coluna, linha.y0, 1, linha))

    def coluna_de(x0: float, x1: float) -> int:
        return livro._coluna_de((x0 + x1) / 2 * o.escala, colunas)

    for i, tabuleiro in enumerate(tabuleiros):
        x0, y0, x1, _y1 = tabuleiro.caixa
        elementos.append((coluna_de(x0, x1), y0, 0, ("t", i, tabuleiro)))
    for i, pedaco in enumerate(pedacos):
        elementos.append((coluna_de(min(g.x0 for g in pedaco), max(g.x1 for g in pedaco)),
                          min(g.y0 for g in pedaco), 0, ("p", i, None)))
    for i, caixa in enumerate(imagens):
        # A imagem entra pelo **meio** da altura, e não pelo topo: a foto do
        # autor ao lado do título da p. 12 começa um ponto abaixo da primeira
        # linha dele, e pelo topo partia o título em dois.
        elementos.append((coluna_de(caixa.x0, caixa.x1), (caixa.y0 + caixa.y1) / 2, 0,
                          ("i", i, None)))
    elementos.sort(key=lambda e: (e[0], e[1], e[2]))
    fluxo = [e[3] for e in elementos]

    # Primeiro, de cada tabuleiro, o cabeçalho de cima e a legenda de baixo —
    # antes de montar qualquer bloco, porque a legenda é quem diz o lado.
    cabecalhos: Dict[int, List[_Linha]] = {}
    legendas: Dict[int, List[_Linha]] = {}
    tomadas: set = set()
    for posicao, item in enumerate(fluxo):
        if isinstance(item, tuple) and item[0] == "t":
            i = item[1]
            coluna = elementos[posicao][0]
            vizinhos = [t for t in tabuleiros if _lado_a_lado(t, tabuleiros[i])]
            # Os de baixo, na mesma faixa horizontal: o cabeçalho deles não é
            # legenda deste (`_legenda`).
            x0, _y0, x1, fundo = tabuleiros[i].caixa
            seguintes = [t for t in tabuleiros if t is not tabuleiros[i]
                         and t.caixa[1] >= fundo
                         and min(x1, t.caixa[2]) - max(x0, t.caixa[0]) > 0]
            cabecalhos[i] = _cabecalho(fluxo, posicao, coluna, tabuleiros[i], tomadas,
                                       vizinhos)
            tomadas |= {id(linha) for linha in cabecalhos[i]}
            legendas[i] = _legenda(fluxo, posicao, coluna, tabuleiros[i], tomadas,
                                   o.idioma, vizinhos, seguintes)
            tomadas |= {id(linha) for linha in legendas[i]}

    blocos: List[object] = []
    corrente: List[_Linha] = []
    #: As imagens que esperam o parágrafo em curso acabar (ver abaixo).
    pendentes: List[livro.Figura] = []
    diagramas = 0

    def despejar() -> None:
        nonlocal corrente
        if corrente:
            blocos.extend(_paragrafos(corrente, m, o.escala, o.lex))
            corrente = []
        blocos.extend(pendentes)
        pendentes.clear()

    for item in fluxo:
        if isinstance(item, _Linha):
            if id(item) in tomadas:
                continue
            if pendentes and corrente and _abre_paragrafo(item, corrente[-1], m):
                despejar()
            corrente.append(item)
            continue
        tipo, i, _tabuleiro = item
        if tipo == "i":
            # **A imagem espera o parágrafo acabar**, e o tabuleiro não: a foto
            # que o livro põe ao lado do texto (a do autor, na p. 12) tem
            # linhas de um mesmo parágrafo acima e abaixo do meio dela, e entrar
            # ali o partia em dois. O tabuleiro ocupa a coluna — não há texto do
            # lado dele para esperar.
            figura = _figura_da_imagem(page, imagens[i], o)
            if figura.origem != "pagina":
                diagramas += 1
            pendentes.append(figura)
            if not corrente:
                despejar()
            continue
        despejar()
        if tipo == "t":
            diagramas += 1
            cabecalho = " ".join(linha.texto for linha in cabecalhos[i])
            legenda = " ".join(linha.texto for linha in legendas[i])
            if cabecalho:
                blocos.append(livro.Paragrafo(cabecalho, titulo=True))
            blocos.append(_figura_do_tabuleiro(
                page, tabuleiros[i], orientacao=orientacoes[i], rotulado=rotulados[i],
                lado=_lado(cabecalho, [linha.texto for linha in legendas[i]], o.idioma),
                o=o))
            if legenda:
                # Depois da figura, e sem ser título — é onde ela está impressa
                # e o que ela é, como a legenda do OCR (`livro.extrair_pagina`).
                blocos.append(livro.Paragrafo(legenda))
        else:
            diagramas += 1
            blocos.append(_figura_de_pedaco(page, pedacos[i], o))
    despejar()

    resultado = livro.PaginaExtraida(
        numero=numero, blocos=blocos, diagramas=diagramas,
        colunas=max(1, len(colunas)), altura=int(round(page.rect.height * o.escala)),
        largura=int(round(page.rect.width * o.escala)), dpi=int(dpi),
        leitura=LEITURA_CAMADA)
    resultado.caracteres = sum(
        len(b.texto) for b in blocos if isinstance(b, livro.Paragrafo))
    resultado.diagramas_desenhados = sum(
        1 for b in blocos if isinstance(b, livro.Figura) and b.origem == "render")
    return resultado


# ----------------------------------------------------------------------
# O livro
# ----------------------------------------------------------------------

def ligar_legendas(paginas: Sequence["livro.PaginaExtraida"], *, idioma: str = "en",
                   lado_do_diagrama: int = render_diagrama.LADO_PADRAO,
                   moldura=render_diagrama.MOLDURA_PADRAO,
                   cantos: str = render_diagrama.CANTO_PADRAO) -> int:
    """
    A legenda que a paginação mandou para a página seguinte volta ao diagrama dela.

    **Medido no Dvoretsky**: 25 dos 1.273 diagramas fecham a página, e o número
    e a letra de lado deles abrem a seguinte — o `16-2` e o `W?` no alto da
    p. 29 são do último diagrama da p. 28. Página a página esses diagramas
    saíam sem legenda e com o lado por convenção, e a legenda solta virava
    parágrafo no começo da página seguinte. É passada de livro pela mesma razão
    que o cabeçalho corrente é: numa página só, a legenda da outra não existe.

    **Tem de correr antes de `livro.retirar_cabecalhos`**: `16-2` e `W?` no alto
    de vinte e cinco páginas têm a forma e a repetição de um cabeçalho corrente
    (a assinatura de `16-2` é a mesma de um número de página), e sairiam do
    livro como tal. Levada para baixo da figura, a legenda não tem mais altura
    na página, e aquela régua não a vê.

    A legenda também pode partir no meio — o `1-135` fecha a página e o `B`
    abre a seguinte —, e aí o pedaço de cima completa a legenda que já está
    embaixo da figura; um segundo número de diagrama, não: ele é de outro.

    Só entre páginas da camada, seguidas, e só a sequência que **começa** pelo
    número do diagrama, pelo do exercício ou pela letra de lado. Devolve
    quantas legendas voltaram.
    """
    idioma = (idioma or "en").lower()[:2]
    religadas = 0
    for atual, seguinte in zip(paginas, paginas[1:]):
        if (getattr(atual, "leitura", "") != LEITURA_CAMADA
                or getattr(seguinte, "leitura", "") != LEITURA_CAMADA
                or seguinte.numero != atual.numero + 1 or not atual.blocos):
            continue
        existente: Optional[livro.Paragrafo] = None
        figura = atual.blocos[-1]
        if (isinstance(figura, livro.Paragrafo) and figura.topo is None
                and not figura.titulo and len(atual.blocos) >= 2):
            existente, figura = figura, atual.blocos[-2]
        if not (isinstance(figura, livro.Figura) and figura.fen
                and figura.origem in ("render", "recorte")):
            continue
        ja_numerada = existente is not None and any(
            _NUMERO_DO_DIAGRAMA.match(pedaco) for pedaco in existente.texto.split())
        levadas: List[livro.Paragrafo] = []
        for bloco in seguinte.blocos:
            if (not isinstance(bloco, livro.Paragrafo) or bloco.titulo
                    or len(levadas) >= LINHAS_DE_LEGENDA or len(bloco.inicios) > 1):
                break
            texto = bloco.texto.strip()
            if ja_numerada and _NUMERO_DO_DIAGRAMA.match(texto):
                break
            if not (legenda_estrita(texto, idioma)
                    or (levadas and len(texto) <= CARACTERES_DE_COMPLEMENTO)):
                break
            levadas.append(bloco)
        if not levadas or not legenda_estrita(levadas[0].texto, idioma):
            continue
        textos = [bloco.texto.strip() for bloco in levadas]
        seguinte.blocos = seguinte.blocos[len(levadas):]
        seguinte.caracteres -= sum(len(bloco.texto) for bloco in levadas)
        novos = " ".join(textos)
        if existente is not None:
            existente.texto = f"{existente.texto} {novos}"
            atual.caracteres += len(novos) + 1
            textos = existente.texto.split()
        else:
            atual.blocos.append(livro.Paragrafo(novos))
            atual.caracteres += len(novos)
        lado = _lado("", textos, idioma)
        if lado and lado != figura.lado_a_jogar:
            _trocar_lado(figura, lado, lado_do_diagrama, moldura, cantos)
        religadas += 1
    return religadas


#: O número de página: `37`, `- 12 -`, `xiv` — o romano só na forma de romano,
#: para `civil` ou `mild` soltos na margem não passarem por fólio.
_FOLIO = re.compile(
    r"^[\W_]*(?:\d{1,4}|(?=[ivxlcdm])m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})"
    r"(?:ix|iv|v?i{0,3}))[\W_]*$", re.I)


def retirar_mobilia(paginas: Sequence["livro.PaginaExtraida"]) -> "collections.Counter[str]":
    """
    O cabeçalho corrente e o número de página das páginas da **camada**.

    **É a mesma pergunta de `livro.retirar_cabecalhos`, com uma prova que só a
    camada dá.** Aquela régua olha a primeira e a última linha impressa de cada
    página e confirma pela repetição da assinatura sem dígitos — e a assinatura
    vazia é a de todo número de página, mas também a de `2019.`, de `1977` e de
    `1-17`. Medido no Dvoretsky, que não imprime cabeçalho nem número de página
    na camada: ela apagava 16 linhas de conteúdo, porque bastam três páginas
    terminando num ano para a assinatura vazia "se repetir". Aqui a linha só é
    candidata se estiver **solta**: um parágrafo de uma linha só, na margem, com
    um vão até o resto da página de pelo menos 0,8 da altura dela — e o `2019.`
    que fecha um parágrafo está colado nele. O número de página solto sai sem
    esperar repetição (é o que ele é); o texto solto sai quando se repete na
    mesma margem em `livro.PAGINAS_DE_CABECALHO` páginas.
    """
    candidatas = []
    vistos: "collections.Counter[Tuple[str, str]]" = collections.Counter()
    for pagina in paginas:
        if getattr(pagina, "leitura", "") != LEITURA_CAMADA or not pagina.altura:
            continue
        for margem, bloco in _soltos_na_margem(pagina):
            texto = bloco.texto.strip()
            chave = (margem, livro._assinatura(texto))
            vistos[chave] += 1
            candidatas.append((pagina, bloco, chave, texto))
    retirados: "collections.Counter[str]" = collections.Counter()
    for pagina, bloco, chave, texto in candidatas:
        if not (_FOLIO.match(texto) or (chave[1] and vistos[chave]
                                          >= livro.PAGINAS_DE_CABECALHO)):
            continue
        pagina.blocos = [b for b in pagina.blocos if b is not bloco]
        pagina.cabecalhos.append(texto)
        pagina.caracteres -= len(bloco.texto)
        retirados[texto] += 1
    return retirados


def _soltos_na_margem(pagina: "livro.PaginaExtraida"
                      ) -> List[Tuple[str, "livro.Paragrafo"]]:
    """O parágrafo de uma linha que abre (ou fecha) a página, solto do resto."""
    topos = []
    for bloco in pagina.blocos:
        if isinstance(bloco, livro.Paragrafo) and bloco.topo is not None:
            topos.append((bloco.topo, bloco.pe if bloco.pe is not None else bloco.topo, bloco))
        elif isinstance(bloco, livro.Figura) and bloco.caixa:
            topos.append((bloco.caixa[1], bloco.caixa[3], bloco))
    if len(topos) < 2:
        return []
    saida = []
    alto = min(topos, key=lambda t: t[0])
    baixo = max(topos, key=lambda t: t[1])
    for margem, (topo, pe, bloco) in (("alto", alto), ("baixo", baixo)):
        if not (isinstance(bloco, livro.Paragrafo) and not bloco.titulo
                and len(bloco.inicios) == 1
                and livro._candidato_a_cabecalho(bloco.texto.strip())):
            continue
        altura = max(1, pe - topo)
        if margem == "alto":
            na_margem = topo <= pagina.altura * livro.MARGEM_DE_PAGINA
            vao = min(t for t, _p, b in topos if b is not bloco) - pe
        else:
            na_margem = pe >= pagina.altura * (1 - livro.MARGEM_DE_PAGINA)
            vao = topo - max(p for _t, p, b in topos if b is not bloco)
        if na_margem and vao >= 0.8 * altura:
            saida.append((margem, bloco))
    return saida


def _trocar_lado(figura: "livro.Figura", lado: str, lado_do_diagrama: int,
                 moldura, cantos: str) -> None:
    """O lado que a legenda da página seguinte disse, no FEN e no desenho."""
    figura.fen = lado_jogar.com_lado(figura.fen, lado)
    figura.lado_a_jogar, figura.lado_origem = lado, "legenda"
    if figura.origem != "render":
        return
    try:
        png, largura, altura = render_diagrama.desenhar(
            figura.fen, fonte=figura.fonte or render_diagrama.FONTE_PADRAO,
            lado_px=lado_do_diagrama, coordenadas=figura.coordenadas, moldura=moldura,
            cantos=cantos, orientacao=figura.orientacao, lado_a_jogar=lado,
            marcas=figura.marcas)
    except (render_diagrama.FonteDesconhecida, render_diagrama.FonteIncompleta):
        # O desenho de antes fica, sem o indicador: o FEN já diz o lado, e a
        # figura que não se redesenha não pode derrubar o livro.
        return
    figura.png, figura.largura, figura.altura = png, largura, altura
    figura.casas_de_largura = largura * 8.0 / render_diagrama.lado_efetivo(lado_do_diagrama)


@dataclass
class Extracao:
    """O que `extrair` leu, e o que ele deixou para o OCR."""

    #: As páginas lidas da camada, na ordem pedida.
    paginas: List["livro.PaginaExtraida"]
    #: O veredito de cada página pedida, na mesma ordem.
    vereditos: List[Veredito]

    @property
    def recusadas(self) -> List[Veredito]:
        """As páginas que a régua mandou para o OCR — e por quê."""
        return [v for v in self.vereditos if not v.aceita]

    def resumo(self) -> str:
        motivos = collections.Counter(v.motivo.split(" (")[0] for v in self.recusadas)
        linhas = [f"{len(self.paginas)} de {len(self.vereditos)} página(s) lidas da camada"]
        linhas += [f"  {n} recusada(s): {motivo}" for motivo, n in motivos.most_common()]
        return "\n".join(linhas)


def extrair(caminho: str, paginas: Optional[Sequence[int]] = None, *,
            dpi: int = 300, dpi_figura: int = livro.DPI_FIGURA,
            idioma: Optional[str] = None, lex=None, diagramas: str = "render",
            coordenadas=False,
            fonte: str = render_diagrama.FONTE_PADRAO,
            lado_do_diagrama: int = render_diagrama.LADO_PADRAO,
            moldura=render_diagrama.MOLDURA_PADRAO,
            cantos: str = render_diagrama.CANTO_PADRAO,
            forcar: bool = False,
            progress_callback: Optional[Callable[[int, int], None]] = None
            ) -> Extracao:
    """
    O texto e os diagramas do PDF, **sem OCR**: as páginas que a régua aceita.

    É a porta de quem quer o livro nascido digital e não tem — ou não quer
    carregar — o modelo de glifos e o Tesseract. A página recusada não sai
    vazia e calada: ela fica em `Extracao.recusadas`, com o motivo, para quem
    chama mandá-la ao OCR (`livro.extrair(..., camada="auto")` faz as duas
    coisas de uma vez). `forcar=True` lê da camada toda página que tem texto,
    inclusive a que a régua recusou — é a mão do usuário sobre a régua.

    `idioma` `None` pergunta ao PDF (`livro.idioma_do_pdf`), e cai no inglês.
    """
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")
    if idioma is None:
        idioma = livro.idioma_do_pdf(caminho) or "en"
    lidas: List[livro.PaginaExtraida] = []
    vereditos: List[Veredito] = []
    with fitz.open(caminho) as doc:
        carimbo = produtor(doc)
        numeros = list(range(len(doc))) if paginas is None else list(paginas)
        for i, numero in enumerate(numeros):
            if progress_callback:
                progress_callback(i, len(numeros))
            page = doc[numero]
            veredito = avaliar_pagina(page, numero=numero, produtor=carimbo)
            vereditos.append(veredito)
            if veredito.aceita or (forcar and veredito.tem_texto):
                lidas.append(extrair_pagina(
                    page, numero=numero, dpi=dpi, dpi_figura=dpi_figura,
                    idioma=idioma, lex=lex, diagramas=diagramas,
                    coordenadas=coordenadas, fonte=fonte,
                    lado_do_diagrama=lado_do_diagrama, moldura=moldura,
                    cantos=cantos))
        if progress_callback:
            progress_callback(len(numeros), len(numeros))
    # As duas passadas do livro inteiro, nesta ordem (ver `ligar_legendas`): a
    # legenda que a paginação separou volta ao diagrama, e o cabeçalho corrente
    # e o número de página saem — a repetição na margem só existe com várias
    # páginas.
    ligar_legendas(lidas, idioma=idioma, lado_do_diagrama=lado_do_diagrama,
                   moldura=moldura, cantos=cantos)
    retirar_mobilia(lidas)
    return Extracao(lidas, vereditos)


def contar_leituras(paginas: Iterable["livro.PaginaExtraida"]) -> Dict[str, int]:
    """`{"camada": n, "imagem": m}` — quantas páginas vieram de cada caminho."""
    conta = collections.Counter(getattr(p, "leitura", LEITURA_IMAGEM) or LEITURA_IMAGEM
                                for p in paginas)
    return {LEITURA_CAMADA: conta.get(LEITURA_CAMADA, 0),
            LEITURA_IMAGEM: conta.get(LEITURA_IMAGEM, 0)}
