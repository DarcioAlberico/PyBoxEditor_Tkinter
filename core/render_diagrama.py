"""
O diagrama redesenhado a partir do FEN, com fonte de xadrez (F58).

**Por que redesenhar em vez de recortar.** Até aqui o `livro` exportava o
diagrama recortando a imagem do scan: fiel, e feio — hachura de meio-tom,
moldura torta, tinta do papel. Como a F7.x já lê a posição, o diagrama pode
nascer limpo, no tamanho que o formato pedir, com coordenadas ou sem.

**O preço disso é que o render mente bem.** O recorte, quando o OCR erra, sai
com a peça que o livro imprimiu; o render sai com a peça que o modelo achou —
desenhada com a mesma nitidez das outras 63 casas, sem nada que denuncie o erro.
A F8.4 mediu 92,49% de tabuleiro inteiro certo em 346 tabuleiros de livros fora
do treino: **um em treze**. É por isso que o porteiro da F58 existe, e é ele, e
não este módulo, que decide entre desenhar e recortar. Aqui só se desenha.

## Como a fonte funciona, e como isso foi apurado

Uma fonte de diagrama mapeia caractere → *casa inteira*: a peça e o fundo da
casa saem no mesmo glifo, e por isso cada peça tem duas letras — uma para casa
clara, outra para escura. A página 3 do `fonts/SkakNew.pdf` imprime a posição
inicial na própria fonte, e é dali que o mapa saiu:

    8rmblkans   7opopopop   60Z0Z0Z0Z   2POPOPOPO   1SNAQJBMR

Maiúscula é branca, minúscula é preta, `0` é casa clara vazia e `Z` é escura
vazia. Sobram quatro combinações que a posição inicial não mostra (dama preta em
casa clara, rei preto em escura, e as duas brancas correspondentes), e elas se
fecham por eliminação: `q j` e `L K`.

**A geometria dos glifos confirma o mapa sem depender da leitura do PDF.** Medido
no `hmtx` e no contorno de cada glifo: as 12 letras de casa clara desenham só a
peça (`B` vai de x=127 a 873), e as 12 de casa escura pintam o quadrado inteiro
(`A` vai de -8 a 1008). Os dois grupos batem, letra por letra, com o que a
posição inicial diz. E as duas redes da F7.4/F7.5 fecham o círculo: renderizar um
FEN com este mapa e reler o desenho com elas devolve o mesmo FEN.

**O `-8` não é defeito, é o que evita a costura.** Os glifos de casa escura
transbordam 8 milésimos de em para cada lado, então o quadrado vizinho é coberto
antes que sobre linha branca entre as filas. Quem desenha tem de respeitar isso:
avanço de 1 em exato, sem espaçamento entre letras e sem entrelinha — `em` é
1000, `ascent` é 1000 e `descent` é 0, ou seja **a casa é o quadrado do em, com
a linha de base no pé dela**.

## Por que PyMuPDF, e sem dependência nova

O `fitz` já está aqui, abre a fonte pelo caminho — como `ui/fontes.py` e o PDF
pesquisável já fazem — e rasteriza. A checagem de cobertura de glifo é
obrigatória e não decorativa: a §4.2 da SPEC registra o modo de falha em que uma
fonte errada troca todo símbolo por `·` **sem levantar erro**. Aqui isso sairia
como um tabuleiro de 64 casas vazias, plausível à distância.

A fonte é LPPL 1.2+ (© 2004–2009 Ulrich Dirr), o que permite redistribuí-la —
é o que abre a porta para o modo de fonte embutida da F59. O PNG não depende
disso: quem abre o arquivo não precisa da fonte.
"""

import io
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import fitz
from PIL import Image

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CAMINHO_MAPAS = os.path.join(_RAIZ, "core", "dados", "fontes_de_diagrama.json")

#: A que está no repositório, e por isso a única que a suíte consegue exercitar.
FONTE_PADRAO = "SkakNew-Diagram"

#: Lado do desenho, em pixels.
#:
#: **É o DOCX que manda no número, e ele é barato.** O EPUB escala a figura pela
#: CSS e se contenta com pouco; o DOCX a fixa em 9 cm, e aí o lado em pixels
#: *é* a resolução de impressão. Medido no mesmo diagrama, com a moldura junto:
#:
#:     lado    arquivo   dpi a 9 cm no DOCX
#:     256 px    5,1 KB      72
#:     350 px    6,8 KB      99   ← o que o recorte a 150 dpi produzia
#:     528 px   11,2 KB     149
#:     700 px   14,4 KB     198
#:
#: O recorte que isto substitui pesava ~85 KB a 700 px e cerca de um quarto
#: disso a 350 (`livro.DPI_FIGURA`). **O desenho a 528 px custa metade do
#: recorte a 350** — sai com 149 dpi impressos onde o recorte dava 99, e ainda
#: assim encolhe o arquivo. Não há troca a fazer aqui, e por isso o padrão não
#: é o mínimo.
LADO_PADRAO = 528

#: Tons com que o PNG é gravado. Mesma conta da `livro.TONS_DA_FIGURA`: isto é
#: desenho de linha, e 256 tons pagam por gradiente que não existe.
TONS = 4

#: Espessura da moldura, em casas. O tabuleiro da fonte não traz moldura — a
#: `skak` desenha o filete por fora, no LaTeX, e aqui é o mesmo.
ESPESSURA_MOLDURA = 0.04

#: Espaço do rótulo e corpo dele, em casas.
GUTTER_ROTULO = 0.72
CORPO_ROTULO = 0.46

#: A fonte dos rótulos **não é a do diagrama**: medido no `cmap` da
#: SkakNew-Diagram, ela tem 46 codepoints e entre eles não há `a`–`h` nem `7` e
#: `8` — as letras `a b j k l m n o p q r s` e os dígitos `0`–`6` desenham casas,
#: não texto. Rótulo sai em fonte de texto, e a `helv` do PyMuPDF basta.
FONTE_DO_ROTULO = "helv"


class FonteDesconhecida(KeyError):
    """Não há mapa para essa fonte em `fontes_de_diagrama.json`."""


class FonteIncompleta(RuntimeError):
    """O arquivo da fonte não desenha algum caractere que o mapa promete."""


@dataclass
class Fonte:
    """O mapa de uma fonte de diagrama, já pronto para desenhar."""

    nome: str
    arquivo: str
    em: int = 1000
    #: caractere → (símbolo FEN ou None, "clara"|"escura")
    casas: Dict[str, Tuple[Optional[str], str]] = field(default_factory=dict)
    licenca: str = ""

    @property
    def por_casa(self) -> Dict[Tuple[Optional[str], str], str]:
        """(símbolo, cor da casa) → caractere. É o sentido que desenha."""
        return {v: k for k, v in self.casas.items()}

    def caractere(self, simbolo: Optional[str], cor: str) -> str:
        try:
            return self.por_casa[(simbolo, cor)]
        except KeyError:
            raise FonteIncompleta(
                f"{self.nome} não tem casa {cor} para {simbolo!r}") from None


_cache: Dict[str, Fonte] = {}


def _mapas() -> dict:
    with open(CAMINHO_MAPAS, encoding="utf-8") as f:
        return json.load(f)["fontes"]


def fontes() -> List[str]:
    """As fontes com mapa, na ordem do arquivo."""
    return list(_mapas())


def carregar(nome: str = FONTE_PADRAO) -> Fonte:
    """
    O mapa da fonte, com o arquivo dela conferido.

    A conferência é a da SPEC §4.2 e não é formalidade: fonte que não desenha o
    que o mapa promete não falha na hora de escrever — ela devolve um tabuleiro
    de casas em branco, que passa por diagrama até alguém olhar de perto.
    """
    if nome in _cache:
        return _cache[nome]

    mapas = _mapas()
    if nome not in mapas:
        raise FonteDesconhecida(
            f"sem mapa para {nome!r} (há: {', '.join(mapas) or 'nenhuma'})")
    bruto = mapas[nome]

    caminho = bruto["arquivo"]
    if not os.path.isabs(caminho):
        caminho = os.path.join(_RAIZ, caminho)
    if not os.path.exists(caminho):
        raise FonteIncompleta(f"arquivo da fonte não encontrado: {caminho}")

    casas = {ch: (par[0], par[1]) for ch, par in bruto["casas"].items()}
    fonte = Fonte(nome=nome, arquivo=caminho, em=int(bruto.get("em", 1000)),
                  casas=casas, licenca=bruto.get("licenca", ""))

    faltando = sem_glifo(caminho, casas)
    if faltando:
        raise FonteIncompleta(
            f"{nome} não desenha {''.join(faltando)!r} — o mapa não vale para "
            f"este arquivo ({caminho})")

    _cache[nome] = fonte
    return fonte


def sem_glifo(caminho: str, caracteres: Sequence[str]) -> List[str]:
    """Quais destes caracteres o arquivo da fonte não desenha."""
    f = fitz.Font(fontfile=caminho)
    return [c for c in caracteres if not f.has_glyph(ord(c))]


def esquecer() -> None:
    """Descarta o cache — a suíte troca o JSON debaixo dele."""
    _cache.clear()


# ----------------------------------------------------------------------
# FEN → as oito linhas de texto
# ----------------------------------------------------------------------

def _casas_do_fen(fen: str) -> List[List[Optional[str]]]:
    """8×8 de símbolos, linha 0 = 8ª fila, como a `diagrama.Casa`."""
    filas = fen.split()[0].split("/")
    if len(filas) != 8:
        raise ValueError(f"FEN com {len(filas)} filas: {fen!r}")
    tabuleiro = []
    for fila in filas:
        linha: List[Optional[str]] = []
        for ch in fila:
            if ch.isdigit():
                linha.extend([None] * int(ch))
            else:
                linha.append(ch)
        if len(linha) != 8:
            raise ValueError(f"fila com {len(linha)} casas em {fen!r}")
        tabuleiro.append(linha)
    return tabuleiro


def cor_da_casa(linha: int, coluna: int) -> str:
    """a8 é clara, e a partir dela alterna. Espelhar o tabuleiro não muda isto."""
    return "clara" if (linha + coluna) % 2 == 0 else "escura"


def linhas(fen: str, fonte: Optional[Fonte] = None,
           orientacao: str = "branca") -> List[str]:
    """
    As oito linhas de texto que, nessa fonte, desenham a posição.

    Girar o tabuleiro inverte fila e coluna ao mesmo tempo, e a soma dos dois
    índices conserva a paridade — a casa continua da cor que ela é.
    """
    fonte = fonte or carregar()
    tabuleiro = _casas_do_fen(fen)
    saida = []
    for i, fila in enumerate(tabuleiro):
        texto = "".join(fonte.caractere(simbolo, cor_da_casa(i, j))
                        for j, simbolo in enumerate(fila))
        saida.append(texto)
    if orientacao == "preta":
        saida = [linha[::-1] for linha in reversed(saida)]
    elif orientacao != "branca":
        raise ValueError(f"orientação inválida: {orientacao!r}")
    return saida


# ----------------------------------------------------------------------
# As oito linhas → PNG
# ----------------------------------------------------------------------

def _rotulos(orientacao: str) -> Tuple[List[str], List[str]]:
    colunas = list("abcdefgh")
    filas = [str(n) for n in range(8, 0, -1)]
    if orientacao == "preta":
        colunas.reverse()
        filas.reverse()
    return colunas, filas


def desenhar(fen: str, *, fonte: str = FONTE_PADRAO, lado_px: int = LADO_PADRAO,
             coordenadas: bool = False, moldura: bool = True,
             orientacao: str = "branca", tons: int = TONS
             ) -> Tuple[bytes, int, int]:
    """
    (PNG, largura, altura) do diagrama.

    `coordenadas` é **falso por padrão**: o livro imprime `a`–`h` e `8`–`1` para
    quem vai falar da posição em voz alta, e num arquivo que se lê no tablet
    elas só ocupam espaço. Quem quiser, pede.

    O lado é arredondado para múltiplo de 8, e não é preciosismo: quem relê o
    desenho — a suíte, o porteiro, o `diagrama.ler` — divide a imagem em 8×8
    **iguais**, e um pixel de resto desloca toda casa da última fila.
    """
    f = carregar(fonte)
    texto = linhas(fen, f, orientacao)

    lado = max(8, int(round(lado_px / 8.0)) * 8)
    casa = lado / 8.0
    espessura = casa * ESPESSURA_MOLDURA if moldura else 0.0

    gutter_esq = casa * GUTTER_ROTULO if coordenadas else 0.0
    gutter_baixo = casa * GUTTER_ROTULO if coordenadas else 0.0
    margem = espessura  # o filete mora fora do tabuleiro, e precisa caber

    largura = gutter_esq + lado + 2 * margem
    altura = lado + gutter_baixo + 2 * margem
    x0, y0 = gutter_esq + margem, margem

    doc = fitz.open()
    pagina = doc.new_page(width=largura, height=altura)
    try:
        for i, linha in enumerate(texto):
            pagina.insert_text((x0, y0 + (i + 1) * casa), linha, fontsize=casa,
                               fontname="diag", fontfile=f.arquivo)

        if moldura:
            meio = espessura / 2.0
            pagina.draw_rect(
                fitz.Rect(x0 - meio, y0 - meio, x0 + lado + meio, y0 + lado + meio),
                width=espessura, color=(0, 0, 0))

        if coordenadas:
            corpo = casa * CORPO_ROTULO
            colunas, filas = _rotulos(orientacao)
            for i, rotulo in enumerate(filas):
                largura_texto = fitz.get_text_length(rotulo, FONTE_DO_ROTULO, corpo)
                pagina.insert_text(
                    (x0 - espessura - casa * 0.28 - largura_texto,
                     y0 + i * casa + casa / 2 + corpo * 0.35),
                    rotulo, fontsize=corpo, fontname=FONTE_DO_ROTULO)
            for j, rotulo in enumerate(colunas):
                largura_texto = fitz.get_text_length(rotulo, FONTE_DO_ROTULO, corpo)
                pagina.insert_text(
                    (x0 + j * casa + (casa - largura_texto) / 2,
                     y0 + lado + espessura + casa * 0.28 + corpo * 0.7),
                    rotulo, fontsize=corpo, fontname=FONTE_DO_ROTULO)

        pix = pagina.get_pixmap(colorspace=fitz.csGRAY, alpha=False)
        imagem = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()

    if tons and tons < 256:
        imagem = imagem.quantize(colors=tons)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), pix.width, pix.height
