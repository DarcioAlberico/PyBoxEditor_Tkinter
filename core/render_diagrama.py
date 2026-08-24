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
from PIL import Image, ImageChops

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

#: Os três feitios de moldura (F97).
#:
#: **É escolha de quem exporta, e por isso são três e não dois.** O tabuleiro da
#: fonte não traz moldura nenhuma — a `skak` desenha o filete por fora, no
#: LaTeX, e aqui é o mesmo —, então o que se decide aqui é o que se desenha em
#: volta: nada, um filete, ou o par de filetes concêntricos com que os livros de
#: xadrez emolduram o diagrama.
MOLDURAS = ("sem", "simples", "dupla")
MOLDURA_PADRAO = "simples"

#: Espessura do filete simples, em casas.
ESPESSURA_MOLDURA = 0.04

#: A moldura dupla, de fora para dentro: filete grosso, vão, filete fino — em
#: casas, como a de cima.
#:
#: **A ordem importa e é a do livro impresso**: o traço pesado fica por fora e o
#: leve encosta no tabuleiro. Invertida, a moldura parece uma sombra.
MOLDURA_DUPLA = (0.045, 0.030, 0.020)

#: A quina da moldura: viva ou redonda (F101).
#:
#: **É um eixo à parte da moldura, e não dois feitios a mais.** "Sem moldura
#: arredondada" não quer dizer nada, e pôr cinco respostas onde há três e um
#: sim-ou-não faria o usuário procurar a combinação em vez de escolhê-la.
CANTOS = ("reto", "arredondado")
CANTO_PADRAO = "reto"

#: O raio da quina redonda, em casas, quando ela é desenhada com a caneta.
#:
#: Sai do desenho da Chess Merida, que é quem tem a quina redonda em glifo: a
#: caixa do canto simples dela mede 135 das 2048 unidades do em, e a do duplo,
#: 409. Copiar o número faz o mesmo diagrama ter a mesma quina saindo da fonte
#: ou da caneta — que é o que impede a escolha de significar duas coisas.
RAIO_DO_CANTO = {"simples": 0.066, "dupla": 0.200}

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
    #: `{"simples"|"dupla": {peça da moldura: caractere}}`, quando a fonte
    #: desenha a moldura com glifo (F99).
    #:
    #: **Nem toda fonte de diagrama tem isto, e é o que a torna interessante.**
    #: A SkakNew-Diagram não tem glifo de borda nenhum — a `skak` desenha o
    #: filete por fora, no LaTeX. A Chess Merida tem os oito pedaços da moldura
    #: *e* mais dezesseis que trazem o filete com o rótulo da fila ou da coluna
    #: desenhado ao lado. São esses dezesseis que permitem escrever um diagrama
    #: com coordenada **inteiro em texto**, sem uma segunda fonte para os
    #: rótulos — que é o que o EPUB fazia com um `<i>` dentro de um `<span>`, e
    #: o que o DOCX não conseguia fazer de jeito nenhum.
    molduras: Dict[str, Dict[str, str]] = field(default_factory=dict)

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

    def moldura_em_glifo(self, moldura: str,
                         cantos: str = CANTO_PADRAO) -> Optional[Dict[str, str]]:
        """
        Os caracteres desta moldura, ou `None` se a fonte não os tem.

        `cantos="arredondado"` troca os quatro cantos pelos de quina redonda —
        **quando a fonte os traz**. Não trazendo, devolve os de quina viva em
        vez de devolver `None`: a alternativa seria mandar o diagrama inteiro
        para o caminho da caneta e perder as coordenadas em glifo, que é muito
        mais do que o usuário pediu ao marcar uma caixinha.
        """
        pecas = self.molduras.get(moldura)
        if pecas is None or cantos != "arredondado":
            return pecas
        return dict(pecas, **pecas.get("cantos_arredondados", {}))


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
    molduras = {m: dict(pecas) for m, pecas in bruto.get("molduras", {}).items()
                if m in MOLDURAS}
    fonte = Fonte(nome=nome, arquivo=caminho, em=int(bruto.get("em", 1000)),
                  casas=casas, licenca=bruto.get("licenca", ""),
                  molduras=molduras)

    # A moldura em glifo entra na **mesma** conferência das casas, e não numa
    # mais frouxa: um mapa que prometesse `0xC0` numa fonte que não o desenha
    # daria um diagrama com a coluna dos rótulos em branco — plausível à
    # distância, que é a definição do modo de falha da §4.2.
    exigidos = set(casas) | {c for pecas in molduras.values()
                             for valor in pecas.values()
                             for c in (valor.values() if isinstance(valor, dict)
                                       else valor)}
    faltando = sem_glifo(caminho, sorted(exigidos))
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

def rotulos(orientacao: str) -> Tuple[List[str], List[str]]:
    """
    (letras das colunas, números das filas) na ordem em que se imprimem.

    Pública desde a F95: o EPUB em modo de fonte embutida escreve os
    rótulos em texto, e escrevia `a`–`h` fixo. Num diagrama impresso do
    lado das pretas as oito linhas já vêm giradas, e o rótulo fixo
    chamaria `h8` de `a1` sem nada denunciar. Um lugar só para os dois
    usos, que é a disciplina da F5.2.
    """
    colunas = list("abcdefgh")
    filas = [str(n) for n in range(8, 0, -1)]
    if orientacao == "preta":
        colunas.reverse()
        filas.reverse()
    return colunas, filas


#: Quanto de branco fica em volta do desenho em grade, em casas.
#:
#: A grade tem 10 casas de lado, mas a tinta não chega às bordas dela: o filete
#: de cima mora no pé da casa de cima, e o rótulo da fila ocupa pouco mais da
#: metade da casa da esquerda. Sem recortar, o diagrama sairia com quase uma
#: casa de branco em cima e à direita e nada embaixo — o desenho ficaria torto
#: dentro da própria figura. Recorta-se pela tinta, e esta é a folga que sobra.
SANGRIA_DA_GRADE = 0.07


def normalizar_cantos(valor) -> str:
    """`"reto"` ou `"arredondado"`, e nada mais — erro de digitação dói aqui."""
    if valor in CANTOS:
        return valor
    raise ValueError(f"cantos inválidos: {valor!r} (use um de {CANTOS})")


def grade(fen: str, fonte: Optional[Fonte] = None, orientacao: str = "branca",
          moldura: str = MOLDURA_PADRAO,
          cantos: str = CANTO_PADRAO) -> Optional[List[str]]:
    """
    As dez linhas de dez caracteres que desenham o tabuleiro **emoldurado e
    rotulado** — ou `None` se esta fonte não sabe (F99).

    O quadro é o do livro impresso:

        canto  topo  topo … topo  canto
        fila8  ┃ as oito casas ┃  direita
        …
        fila1  ┃ as oito casas ┃  direita
        canto  col.a … col.h    canto

    **O rótulo vem junto do filete, e não é escolha desta função**: na Chess
    Merida o glifo `0xC0` *é* a borda esquerda com um `1` desenhado ao lado.
    Daí a consequência que atravessa o resto do projeto: não há como pedir
    coordenada sem moldura por este caminho, e `moldura="sem"` devolve `None`.

    **Devolver `None` é a resposta certa, e não uma falha.** A SkakNew-Diagram
    não tem glifo de borda nenhum, e o desenho dela continua saindo com o filete
    da caneta e o rótulo em fonte de texto, que é o que sempre fez.

    A orientação sai dos mesmos `rotulos` que o resto usa, e por isso o
    diagrama impresso do lado das pretas ganha `h` na primeira coluna e `1` na
    primeira fila, sem que este código precise saber disso.
    """
    fonte = fonte or carregar()
    moldura = normalizar_moldura(moldura)
    pecas = fonte.moldura_em_glifo(moldura, normalizar_cantos(cantos))
    if pecas is None:
        return None

    corpo = linhas(fen, fonte, orientacao)
    colunas, filas = rotulos(orientacao)

    saida = [pecas["canto_ne"] + pecas["topo"] * 8 + pecas["canto_no"]]
    for rotulo, linha in zip(filas, corpo):
        saida.append(pecas["filas"][int(rotulo) - 1] + linha + pecas["direita"])
    saida.append(pecas["canto_se"]
                 + "".join(pecas["colunas"][ord(c) - ord("a")] for c in colunas)
                 + pecas["canto_so"])
    return saida


def normalizar_moldura(valor) -> str:
    """
    O nome da moldura, aceitando os booleanos de antes da F97.

    `True` e `False` continuam valendo porque foi assim que a `desenhar` nasceu
    e é assim que a suíte ainda a chama; **qualquer outra coisa levanta erro**,
    e não vira verdadeiro em silêncio. É a mesma disciplina que o `livro` aplica
    ao `coordenadas` desde a F95: um `"Dupla"` com maiúscula sairia como moldura
    simples no livro inteiro sem nada denunciar.
    """
    if valor is True:
        return "simples"
    if valor is False:
        return "sem"
    if valor in MOLDURAS:
        return valor
    raise ValueError(f"moldura inválida: {valor!r} (use um de {MOLDURAS})")


def filetes(moldura: str, casa: float) -> Tuple[List[Tuple[float, float]], float]:
    """
    `([(recuo do caminho, espessura)], margem total)` dos filetes, em pixels.

    O `recuo` é medido do lado do tabuleiro **para fora**, e é o centro do
    traço: um filete de espessura `e` cujo caminho passa a `e/2` do tabuleiro
    ocupa exatamente a faixa de `0` a `e` fora dele, sem invadir uma casa. É por
    isso que a margem da página é a soma, e não a metade dela.
    """
    if moldura == "sem":
        return [], 0.0
    if moldura == "simples":
        e = casa * ESPESSURA_MOLDURA
        return [(e / 2.0, e)], e
    externo, vao, interno = (casa * f for f in MOLDURA_DUPLA)
    return ([(interno / 2.0, interno),
             (interno + vao + externo / 2.0, externo)],
            interno + vao + externo)


def lado_efetivo(lado_px: int) -> int:
    """
    O lado que o desenho vai mesmo ter: múltiplo de 8, e nunca zero.

    Pública desde a F97 porque quem escreve o arquivo precisa dela para saber
    **quantas casas de largura a figura tem** — é o que converte o corpo em
    pontos, que é escolha do usuário, na largura da imagem no DOCX e no EPUB.
    """
    return max(8, int(round(lado_px / 8.0)) * 8)


def desenhar(fen: str, *, fonte: str = FONTE_PADRAO, lado_px: int = LADO_PADRAO,
             coordenadas: bool = False, moldura=MOLDURA_PADRAO,
             cantos: str = CANTO_PADRAO,
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

    `moldura` é `"sem"`, `"simples"` ou `"dupla"` desde a F97, e continua
    aceitando os booleanos de antes (ver `normalizar_moldura`).

    **Há dois desenhos aqui, e quem escolhe entre eles é a fonte** (F99). Pedida
    coordenada a uma fonte que tenha os glifos de borda com rótulo, o diagrama
    inteiro sai da fonte — moldura e `a`–`h` e `8`–`1` —, e o tamanho da figura
    passa a ser o do recorte na tinta. Pedida a uma que não tenha, sai como
    sempre saiu: filete de caneta e rótulo em fonte de texto. Sem coordenada os
    dois caminhos são o mesmo, e é o de sempre.
    """
    f = carregar(fonte)
    moldura = normalizar_moldura(moldura)
    cantos = normalizar_cantos(cantos)
    lado = lado_efetivo(lado_px)
    casa = lado / 8.0

    em_grade = grade(fen, f, orientacao, moldura, cantos) if coordenadas else None
    if em_grade is not None:
        imagem = _pintar_grade(em_grade, f, casa)
    else:
        imagem = _pintar_com_caneta(linhas(fen, f, orientacao), f, casa, lado,
                                    moldura, cantos, coordenadas, orientacao)

    if tons and tons < 256:
        imagem = imagem.quantize(colors=tons)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), imagem.width, imagem.height


def _pintar_grade(em_grade: Sequence[str], fonte: Fonte, casa: float) -> Image.Image:
    """
    As dez linhas da `grade`, pintadas e recortadas na tinta (F99).

    **Dez casas de lado, e nenhum cálculo de moldura.** O filete e o rótulo já
    estão dentro dos glifos, na posição em que o desenhista da fonte os pôs; o
    que este código faz é encostar as dez linhas uma na outra, como faz com as
    oito do tabuleiro nu.

    O recorte é o que impede o desenho de sair torto dentro da figura — ver
    `SANGRIA_DA_GRADE`. E ele é determinístico apesar de medir a tinta: a
    moldura fecha o desenho dos quatro lados, e as oito filas e as oito colunas
    saem em todo diagrama, então a caixa da tinta é sempre a mesma para uma dada
    fonte, moldura e escala — não depende de onde estão as peças.
    """
    lado_da_grade = casa * 10
    doc = fitz.open()
    pagina = doc.new_page(width=lado_da_grade, height=lado_da_grade)
    try:
        for i, linha in enumerate(em_grade):
            pagina.insert_text((0, (i + 1) * casa), linha, fontsize=casa,
                               fontname="diag", fontfile=fonte.arquivo)
        pix = pagina.get_pixmap(colorspace=fitz.csGRAY, alpha=False)
        imagem = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()

    tinta = ImageChops.invert(imagem).getbbox()
    if tinta is None:
        return imagem
    folga = max(1, int(round(casa * SANGRIA_DA_GRADE)))
    return imagem.crop((max(0, tinta[0] - folga), max(0, tinta[1] - folga),
                        min(imagem.width, tinta[2] + folga),
                        min(imagem.height, tinta[3] + folga)))


def _pintar_com_caneta(texto: Sequence[str], f: Fonte, casa: float, lado: int,
                       moldura: str, cantos: str, coordenadas: bool,
                       orientacao: str) -> Image.Image:
    """
    O tabuleiro com o filete desenhado e o rótulo em fonte de texto.

    É o desenho de sempre, e o único que a SkakNew-Diagram sabe fazer: ela tem
    46 codepoints e nenhum deles é `a`–`h`, `7` ou `8` — as letras que sobrariam
    para rótulo desenham casa.

    **A quina redonda é desenhada aqui também, e não só na fonte** (F101). Sem
    isso a caixinha dos cantos não faria nada no caminho mais usado de todos —
    o PNG sem coordenada, que é o padrão da exportação —, e uma opção que só
    funciona em certa combinação é pior que opção nenhuma. O raio é o mesmo que
    a Chess Merida desenha nos glifos dela, em casas.
    """
    # O filete mora fora do tabuleiro, e a margem da página é o que ele ocupa.
    tracos, margem = filetes(moldura, casa)

    gutter_esq = casa * GUTTER_ROTULO if coordenadas else 0.0
    gutter_baixo = casa * GUTTER_ROTULO if coordenadas else 0.0

    largura = gutter_esq + lado + 2 * margem
    altura = lado + gutter_baixo + 2 * margem
    x0, y0 = gutter_esq + margem, margem

    doc = fitz.open()
    pagina = doc.new_page(width=largura, height=altura)
    try:
        for i, linha in enumerate(texto):
            pagina.insert_text((x0, y0 + (i + 1) * casa), linha, fontsize=casa,
                               fontname="diag", fontfile=f.arquivo)

        # Concêntricos: o filete de dentro tem de curvar mais fechado que o de
        # fora, exatamente pela distância que os separa, ou os dois se cruzam na
        # quina. `radius` do PyMuPDF é fração do menor lado do retângulo.
        recuo_externo = max((recuo for recuo, _e in tracos), default=0.0)
        raio_externo = casa * RAIO_DO_CANTO.get(moldura, 0.0)
        for recuo, espessura in tracos:
            quadro = fitz.Rect(x0 - recuo, y0 - recuo,
                               x0 + lado + recuo, y0 + lado + recuo)
            raio = raio_externo - (recuo_externo - recuo)
            if cantos == "arredondado" and raio > 0:
                pagina.draw_rect(quadro, width=espessura, color=(0, 0, 0),
                                 radius=min(0.5, raio / quadro.width))
            else:
                pagina.draw_rect(quadro, width=espessura, color=(0, 0, 0))

        if coordenadas:
            corpo = casa * CORPO_ROTULO
            colunas, filas = rotulos(orientacao)
            for i, rotulo in enumerate(filas):
                largura_texto = fitz.get_text_length(rotulo, FONTE_DO_ROTULO, corpo)
                pagina.insert_text(
                    (x0 - margem - casa * 0.28 - largura_texto,
                     y0 + i * casa + casa / 2 + corpo * 0.35),
                    rotulo, fontsize=corpo, fontname=FONTE_DO_ROTULO)
            for j, rotulo in enumerate(colunas):
                largura_texto = fitz.get_text_length(rotulo, FONTE_DO_ROTULO, corpo)
                pagina.insert_text(
                    (x0 + j * casa + (casa - largura_texto) / 2,
                     y0 + lado + margem + casa * 0.28 + corpo * 0.7),
                    rotulo, fontsize=corpo, fontname=FONTE_DO_ROTULO)

        pix = pagina.get_pixmap(colorspace=fitz.csGRAY, alpha=False)
        return Image.frombytes("L", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()


#: Nome interno antigo, mantido para quem já importava.
_rotulos = rotulos
