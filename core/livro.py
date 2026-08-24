"""
Extração do livro a partir da imagem da página (F2.6).

**Por que existe.** Todo o resto desta pasta trabalha *sobre* o PDF: o
`chess_pdf_processor` reescreve spans, o `mapa_glifos` conserta a tabela de
caracteres, o `searchable_pdf` acrescenta uma camada. Os três dependem do que o
PDF já traz, e nestes livros o que ele traz é ruim — a camada de texto vem de um
OCR de fábrica que erra a notação inteira e se perde nas tarjas de nome. Medido
na página 11 do Yusupov, a mesma linha:

    camada do PDF   '•. hb7 2.hb7 l2Jd7 3.ha8 Wlxa8 4.c!LJ£3;!;'
    nosso OCR       '1...♗xb7 2.♗xb7 ♘d7 3.♗xa8 ♕xa8 4.♘f3²'

e na tarja, `G.Levenfish - B.G0lden0v` contra `G.Levenfish - B.Goldenov` do PDF,
que ali acerta — mas em `L.Shamkovich` o PDF dá `L.Sham зv ..:_`.

Daí este módulo **ignorar a camada de texto por completo** e ler a página como
imagem, do mesmo jeito que a UI lê. O que sai daqui não é PDF: é uma sequência
de parágrafos e figuras, que o `exportar` transforma em EPUB ou DOCX.

**Os três filtros abaixo são o que separa livro de lixo**, e cada um está aqui
porque a medição mostrou o estrago que a falta dele faz.

**O diagrama deixou de ser recorte na F58.** Ele agora é redesenhado a partir do
FEN que a `diagrama.ler` extrai, com fonte de xadrez — mas só quando o porteiro
(`diagrama.confiavel`) deixa. O recorte não saiu de cena: é para onde cai quem
não passa, e é o que este módulo exportava sozinho até aqui.

**A coluna virou primeira classe na F61.** A ordem de leitura respeita colunas
desde a F1.6, mas ordem não é parágrafo: sem saber onde a coluna acaba, o último
parágrafo da esquerda saía colado no primeiro da direita, e a margem que abre
parágrafo — mediana das esquerdas — não era margem de coluna nenhuma. As três
coisas que aqui dependem da coluna são o corte de parágrafo, a margem do recuo e
o lugar da figura.
"""

import io
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple, Union


import fitz
import numpy as np
from PIL import Image

from core import diagrama, notacao, render_diagrama, vertical
from core.box_model import BoxEntry
from core.leitura_de_linha import quebrar_em_linhas
from core.services.box_service import BoxService


#: Quanto o retângulo do tabuleiro cresce antes de excluir o que está dentro
#: dele, em alturas de caractere.
#:
#: **Os rótulos das casas ficam de fora do tabuleiro.** O `diagrama.localizar`
#: devolve a borda do tabuleiro, e as letras `a`–`h` embaixo e os números `8`–`1`
#: ao lado moram fora dela. Sem margem eles entram no texto como linhas de um
#: caractere — medido na página 10 do Yusupov, oito linhas contendo só "8", "7",
#: "6"...
MARGEM_DIAGRAMA = 1.4

#: Área mínima de um contorno para ele ser caractere, em escalas de caractere
#: ao quadrado.
#:
#: A régua decorativa do cabeçalho destes livros é meio-tom, e o que sobra dela
#: depois do `remover_textura` são centenas de contornos de 3×7 e 3×2 px numa
#: página cujo caractere tem 44. Eles não somem por confiança — o modelo lê um
#: respingo como `:` ou `-` com folga.
#:
#: **É área, e não altura, porque altura derruba o ponto final.** A primeira
#: versão cortava por altura a 0,30 da escala e o livro saía sem pontuação
#: nenhuma: `5.♔xf2` virava `5♔d2`, `G.Levenfish` virava `G Levenfish`. Medido
#: nas páginas 10 e 11 do Yusupov, com a área normalizada pela escala:
#:
#:     respingo da régua    0,0021 – 0,0031
#:     ponto final          0,0129 – 0,0514
#:     hífen e travessão    0,0073 – 0,0882
#:     letra minúscula      0,1570 – 0,3315
#:
#: O limiar fica no vão entre a primeira faixa e a segunda, com folga dos dois
#: lados: ~1,6× acima do maior respingo e ~1,5× abaixo do menor traço legítimo.
MIN_AREA_GLIFO = 0.005

#: Quantos respingos numa célula de grade fazem dela ornamento, e o tamanho da
#: célula em escalas de caractere.
#:
#: **Descartar o respingo um a um não basta**, e é o que a medição mostrou: o
#: cabeçalho destes livros traz um leque de meio-tom e um filete pontilhado, e
#: os fragmentos maiores dele passam do limiar de área e entram no texto como
#: `⩲ w + ⩱`, `;♖ : □`, `= = : = : =`. Nem confiança os tira: a 0,97 eles
#: continuam lá e a prosa já perde letra ("Combinations involving bishops" sai
#: `Cmbinatin invlving bihp`, porque `o` e `s` classificam abaixo disso).
#:
#: O que os denuncia é a **companhia**: onde o leque está, há dezenas de marcas
#: pequenas demais para serem caractere no espaço de duas linhas. Texto de
#: verdade quase não gera respingo — medido, a página 11 inteira gera zero.
RESPINGOS_DE_ORNAMENTO = 4
CELULA_DE_ORNAMENTO = 2.0

#: Abaixo disto o caractere não entra no texto.
#:
#: É o piso que o `gerar_pdf_pesquisavel` também tem e a UI nunca passava. Aqui
#: ele importa mais: numa camada invisível de PDF um palpite ruim é ruído de
#: busca, num livro exportado ele é uma letra errada no meio da palavra.
CONF_MINIMA = 0.5

#: Vão entre dois caracteres que vira espaço, em larguras medianas de caractere
#: **da linha** — não da página, que mistura corpo 9 com corpo 12.
#:
#: O número mora em `diagrama` desde a F95, porque o título do diagrama usa a
#: mesma régua e aquele módulo não pode importar este. Uma definição só.
VAO_DE_ESPACO = diagrama.VAO_DE_ESPACO

#: Recuo que abre parágrafo, e salto vertical que abre parágrafo, ambos em
#: alturas de linha.
RECUO_DE_PARAGRAFO = 0.8
SALTO_DE_PARAGRAFO = 0.6


@dataclass
class Paragrafo:
    texto: str
    titulo: bool = False


@dataclass
class Figura:
    """
    Um diagrama no livro exportado — redesenhado, ou recortado da página.

    `origem` diz qual dos dois, e não é enfeite: um diagrama redesenhado afirma
    uma posição que o nosso modelo leu, e o `aviso` guarda por que os outros não
    passaram no porteiro (F58). Sem esses dois campos, o relatório do fim da
    exportação não teria como dizer em que páginas o livro preferiu o scan.
    """
    png: bytes
    largura: int
    altura: int
    #: A posição, quando ela foi lida e mereceu confiança. É o que vira o texto
    #: alternativo da figura nos dois formatos.
    fen: Optional[str] = None
    origem: str = "recorte"          # "render" | "recorte" | "pagina"
    aviso: Optional[str] = None
    #: As oito linhas que desenham a mesma posição **na fonte de xadrez**, para
    #: o modo de fonte embutida da F59.
    #:
    #: Vêm **junto** do PNG, e não no lugar dele: são 72 bytes por figura, e é o
    #: que permite escolher o modo na hora de *escrever o arquivo* em vez de na
    #: hora de ler o PDF. A extração custa minutos; a escrita, segundos — e
    #: quem quer o mesmo livro nos dois modos não paga o OCR duas vezes.
    linhas: Optional[List[str]] = None
    fonte: Optional[str] = None
    coordenadas: bool = False
    #: Para que lado o tabuleiro foi desenhado (F95). É "preta" quando o livro
    #: imprimiu o diagrama do lado das pretas e os rótulos disseram isso — e aí
    #: as `linhas` já vêm giradas, e quem escreve o rótulo em texto tem de girar
    #: junto, ou o `a1` do desenho ficaria rotulado `h8`.
    orientacao: str = "branca"
    #: A largura desta figura **medida em casas do tabuleiro** (F97).
    #:
    #: É o que faz o corpo em pontos valer também para a imagem. Quem escreve o
    #: arquivo sabe quantos pontos o usuário quer por casa; o que ele não sabe é
    #: quanto da imagem é tabuleiro — um desenho com moldura e coordenadas tem
    #: quase nove casas de largura, e um recorte justo tem oito. Multiplicar
    #: este número pelo corpo dá a largura da figura na página, e é assim que o
    #: diagrama desenhado e o recortado saem do **mesmo tamanho** no mesmo livro.
    #:
    #: `None` é a figura que não tem tabuleiro por dentro — a página inteira que
    #: virou imagem —, e essa continua saindo pela largura fixa de antes.
    casas_de_largura: Optional[float] = None


@dataclass
class Tabela:
    """
    Uma tabela do livro — as células, linha a linha (F72).

    **Existe porque ler na ordem certa não era ler como tabela.** A F71 tirou a
    tabela de dentro da moldura que a engolia, e ela passou a sair como texto
    corrido: as células na ordem certa, mas sem nada que dissesse onde uma
    acabava e a outra começava. No livro de finais do Nunn a tabela *é* o
    conteúdo — `W: Win (1 ♖e1!)` na casa de `B♖h2` × `W♔d1` é a informação —, e
    um parágrafo por linha com as colunas separadas por espaço não a preserva.

    `linhas[i][j]` é o texto da célula, e a matriz é retangular: célula vazia é
    string vazia. Quem exporta decide o que fazer com a primeira linha.
    """
    linhas: List[List[str]]


Bloco = Union[Paragrafo, Figura, Tabela]


@dataclass
class PaginaExtraida:
    numero: int
    blocos: List[Bloco] = field(default_factory=list)
    caracteres: int = 0
    descartados_por_confianca: int = 0
    respingos_descartados: int = 0
    diagramas: int = 0
    #: Quantos dos `diagramas` saíram redesenhados. O resto caiu para o recorte,
    #: e cada `Figura` diz por quê.
    diagramas_desenhados: int = 0
    #: A página tinha contorno demais para ser texto e saiu inteira como figura.
    pagina_de_imagem: bool = False
    #: Quantas colunas a página tinha (F61). É o que o relatório do fim da
    #: exportação conta para quem quer saber se o livro de duas colunas foi
    #: lido como duas colunas — a queixa que abriu a fase não tinha como ser
    #: conferida sem este número.
    colunas: int = 1

    @property
    def texto(self) -> str:
        """
        Todo o texto da página, parágrafos **e** células (F72).

        A tabela entra porque quem chama isto pergunta o que está escrito na
        página: é daqui que sai o alfabeto para escolher a fonte dos símbolos, e
        deixar a tabela de fora fazia a figurina dentro da célula sair sem a
        fonte que a desenha — medido no EPUB da página 236, `♖` nu na célula e
        `<span class="sim">♔</span>` no parágrafo da mesma página.
        """
        partes = []
        for b in self.blocos:
            if isinstance(b, Paragrafo):
                partes.append(b.texto)
            elif isinstance(b, Tabela):
                partes.extend(" ".join(fila) for fila in b.linhas)
        return "\n\n".join(partes)


# ----------------------------------------------------------------------
# Página → caixas de texto, já sem diagrama nem respingo
# ----------------------------------------------------------------------

def _pagina_cinza(page: fitz.Page, dpi: int) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def _com_margem(rect, margem: float, forma) -> Tuple[int, int, int, int]:
    altura, largura = forma[:2]
    x1, y1, x2, y2 = rect
    m = int(round(margem))
    return (max(0, x1 - m), max(0, y1 - m),
            min(largura, x2 + m), min(altura, y2 + m))


def _dentro(b: BoxEntry, rect) -> bool:
    return rect[0] <= b.x1 and b.x2 <= rect[2] and rect[1] <= b.y1 and b.y2 <= rect[3]


@dataclass
class Diagrama:
    """
    Os dois retângulos de um tabuleiro na página, que **não são o mesmo**.

    `exclusao` é a borda mais a margem, e é o que não pode virar texto: sem ela
    os rótulos `a`–`h` entram como linhas de um caractere. `tabuleiro` é a borda
    que o `diagrama.localizar` devolveu, e é o que a leitura exige — o
    `_casas_do_recorte` divide o recorte em 8×8 **iguais**, e a F8.4 mediu que
    moldura de 2% desloca toda casa.

    Eram um retângulo só até a F58, e a confusão não aparecia porque o único uso
    do recorte era virar figura. Ler o tabuleiro pela `exclusao` daria 64 casas
    deslocadas — e um FEN errado sem nada que denunciasse.
    """

    exclusao: Tuple[int, int, int, int]
    tabuleiro: Tuple[int, int, int, int]
    #: O que está impresso **acima** da borda, quando há algo (F60).
    #:
    #: Nestes livros é o cabeçalho do exercício — `➤ Ex. 22-1 ◀ ★★ ▼` —, e o ▼ é
    #: a única coisa na página que diz de quem é o lance. Fica dentro da margem
    #: de exclusão, então não vira texto; e com o diagrama redesenhado deixou de
    #: virar figura. É `None` no diagrama que não tem nada em cima, que é o caso
    #: do diagrama no meio da prosa.
    faixa: Optional[Tuple[int, int, int, int]] = None
    #: As caixas que compõem a faixa, para ela poder virar **texto** (F67) em
    #: vez de imagem. São as mesmas que a margem excluiu; guardá-las custa uma
    #: lista por diagrama e é o que separa um cabeçalho pesquisável de um
    #: retrato dele.
    caixas_da_faixa: List[BoxEntry] = field(default_factory=list)
    #: As coordenadas que o livro imprimiu em volta **deste** tabuleiro (F95).
    #:
    #: É o que faz `coordenadas="auto"` existir: até aqui a exportação recebia
    #: um booleano para o livro inteiro e não tinha como saber o que o livro
    #: trazia. Traz também a orientação, que é a única coisa no diagrama capaz
    #: de dizer se ele foi impresso do lado das pretas.
    rotulos: diagrama.Rotulos = field(default_factory=diagrama.Rotulos)
    #: A legenda impressa **abaixo** da borda, quando há (F95).
    #:
    #: A `faixa` cobre o que está acima, e por seis fases foi o único lado que
    #: alguém olhou. No Nunn a legenda é o número do diagrama e fica embaixo —
    #: `437`, com a avaliação da posição do outro lado da mesma linha —, e ela
    #: some do livro exportado pelo mesmo motivo que o cabeçalho sumia antes da
    #: F60: a margem a exclui do texto, e a figura é só o tabuleiro.
    legenda: diagrama.Titulo = field(default_factory=diagrama.Titulo)

    @property
    def topo(self) -> int:
        return self.exclusao[1]


#: Folga do recorte da faixa, em alturas de caractere.
#:
#: O `➤` e o `▼` do cabeçalho são desenhos, e o contorno deles às vezes sai um
#: pixel curto do que o olho vê. Meia altura de caractere em volta custa fundo
#: branco e evita ponta cortada.
FOLGA_DA_FAIXA = 0.5


def _na_faixa(b: BoxEntry, d: "Diagrama") -> bool:
    """
    A caixa está na altura da faixa deste diagrama e encosta nele.

    Vertical **dentro**, horizontal **sobreposta**: em cima do tabuleiro cabe
    uma linha só, e o que estiver nela é dela; ao lado do tabuleiro cabe a
    coluna vizinha inteira, e ali a continência é o que impede o texto do
    vizinho de ser confundido com rótulo de casa.

    **A altura é medida pelo pé da caixa, e não pelo topo**, e é o que fazia o
    cabeçalho sair pela metade. Medido na página 10 do Yusupov: a margem de
    exclusão começa em y=896, e o `D` de `Diagram` vai de 887 a 916 — a
    maiúscula sobe acima da margem, a minúscula não. Pelo topo, `Di` ficava de
    fora e a faixa saía `"agram -"`; pelo pé, a linha inteira é da faixa. Linha
    de prosa mais acima não entra: o pé dela fica antes do topo da margem.
    """
    return (d.exclusao[1] <= b.y2 <= d.tabuleiro[1]
            and b.x1 < d.exclusao[2] and b.x2 > d.exclusao[0])


def _faixa_acima(d: "Diagrama", caixas: Sequence[BoxEntry], escala: float
                 ) -> Optional[Tuple[int, int, int, int]]:
    """
    O retângulo do que está impresso acima da borda do tabuleiro, ou `None`.

    **A largura é a do tabuleiro, e a folga é só vertical.** As duas figuras
    saem escaladas para a mesma largura no arquivo, então largura diferente aqui
    vira cabeçalho transbordando o diagrama que ele encabeça — meia altura de
    caractere de cada lado já daria 16% a mais, medido na página 220. Na
    horizontal a faixa só cresce se a tinta passar da borda, o que nestes livros
    não acontece.
    """
    acima = [b for b in caixas if b.y2 <= d.tabuleiro[1]]
    if not acima:
        return None
    d.caixas_da_faixa = BoxService.sort_boxes_reading_order(acima)
    folga = int(round(escala * FOLGA_DA_FAIXA))
    return (max(d.exclusao[0], min(d.tabuleiro[0], min(b.x1 for b in acima))),
            max(d.exclusao[1], min(b.y1 for b in acima) - folga),
            min(d.exclusao[2], max(d.tabuleiro[2], max(b.x2 for b in acima))),
            min(d.tabuleiro[1], max(b.y2 for b in acima) + folga))


def caixas_e_diagramas(img: np.ndarray, classificar: Callable
                       ) -> Tuple[List[BoxEntry], List["Diagrama"], int, int,
                                  List[Tuple[int, int]]]:
    """
    (caixas de texto em ordem de leitura, diagramas, escala, respingos, colunas).

    O tabuleiro sai do `boxes_antes_do_descarte`, que é o estágio em que ele
    ainda existe como caixa. Refazer essas etapas aqui fora foi tentado e não
    funciona: falta uma delas e o `localizar` acha 6 tabuleiros onde há 2,
    levando o texto da página junto.

    **As colunas saem junto porque o `extrair_pagina` precisa delas** (F61). A
    ordem de leitura já as respeita desde a F1.6, mas ordem não basta: quem
    monta parágrafo tem de saber onde a coluna acaba, senão o último parágrafo
    da esquerda gruda no primeiro da direita — o salto vertical que abriria
    parágrafo é *negativo* ali, e nenhuma régua de salto pega isso.
    """
    pil = Image.fromarray(img)
    antes, th, escala, _cinza = BoxService.boxes_antes_do_descarte(
        pil, max_contornos=BoxService.MAX_CONTORNOS_DE_TEXTO)
    escala = escala or 1
    if not antes:
        # Página que é imagem, não texto. Sai inteira como figura: ler caractere
        # dela custaria minutos e devolveria ruído.
        return [], [], escala, 0, []

    # `imagem` e `binaria` abrem a segunda passada da F95, que acha o tabuleiro
    # impresso dentro de um painel — o `th` é o mesmo que já foi calculado aqui,
    # então não é custo novo.
    diagramas = [Diagrama(exclusao=_com_margem(r, escala * MARGEM_DIAGRAMA,
                                               img.shape),
                          tabuleiro=r,
                          rotulos=diagrama.ler_rotulos(img, r, escala,
                                                       classificar))
                 for r in diagrama.localizar(antes, escala=escala,
                                             imagem=img, binaria=th)]

    minima = MIN_AREA_GLIFO * escala * escala
    todas = BoxService.generate_boxes_opencv(pil, arbitro=classificar)

    # O que a margem come é justamente o que a F60 foi buscar: os rótulos das
    # casas, que não fazem falta, e o cabeçalho do exercício, que faz.
    comidas: List[List[BoxEntry]] = [[] for _ in diagramas]
    boxes = []
    for b in todas:
        if (b.x2 - b.x1) * (b.y2 - b.y1) < minima:
            boxes.append(b)          # respingo: separado logo abaixo
            continue
        dentro = [i for i, d in enumerate(diagramas) if _dentro(b, d.exclusao)]
        if not dentro:
            # **A faixa recolhe por sobreposição, e o miolo por continência.**
            # O cabeçalho `Diagram 1-5` é mais largo que o tabuleiro em alguns
            # livros, e exigir continência dele partia a linha ao meio: o `Di`
            # ia para o texto da página e o resto para a faixa, que saía
            # `"agram -"`. Medido na página 10 do Yusupov. Aqui basta a caixa
            # estar na altura da faixa e encostar no retângulo, que é o que
            # define "esta letra é do cabeçalho deste diagrama".
            dentro = [i for i, d in enumerate(diagramas)
                      if _na_faixa(b, d)]
        if dentro:
            comidas[dentro[0]].append(b)
            continue
        boxes.append(b)

    for d, caixas in zip(diagramas, comidas):
        d.faixa = _faixa_acima(d, caixas, escala)

    grandes, respingos = [], []
    for b in boxes:
        (grandes if (b.x2 - b.x1) * (b.y2 - b.y1) >= minima else respingos).append(b)

    ornamento = _celulas_de_ornamento(respingos, escala)
    grandes = [b for b in grandes
               if _celula(b, escala) not in ornamento]

    # **A legenda de baixo é procurada no texto da página, e não no que a
    # margem comeu** (F95). É a assimetria que a F60 não tinha por que notar: o
    # cabeçalho encosta na borda de cima e cabe inteiro na margem, mas a legenda
    # de baixo começa dentro dela e **acaba fora** — o `437` do Nunn nasce a
    # 1,29 escalas do tabuleiro e desce até 2,3, e a exclusão vai a 1,4. Ela
    # chega aqui como texto de página, e é preciso tirá-la de lá para não sair
    # duas vezes no livro.
    #
    # Depois do descarte do respingo, e não antes: um fragmento da régua
    # decorativa caído sob o tabuleiro entraria na legenda, e uma marca ilegível
    # derruba a legenda inteira (`_texto_das_marcas`).
    #
    # Só quem não tem faixa acima é procurado abaixo: nestes livros a legenda é
    # uma só, e o outro lado é o rótulo das casas.
    for d in diagramas:
        if d.faixa is not None:
            continue
        achado = diagrama.ler_titulo(img, d.tabuleiro, escala, classificar,
                                     boxes=grandes, rotulos=d.rotulos)
        # Acima é território da faixa, e ela já respondeu que não há nada.
        if achado.lado != "abaixo":
            continue
        d.legenda = achado
        usadas = {id(b) for b in achado.caixas}
        grandes = [b for b in grandes if id(b) not in usadas]

    # As colunas saem das mesmas caixas que a ordem de leitura ordena, e depois
    # do descarte do ornamento: a régua decorativa do cabeçalho atravessa a
    # calha, e mantê-la na conta apagaria a calha da página inteira.
    return (BoxService.sort_boxes_reading_order(grandes), diagramas, escala,
            len(respingos), BoxService.detectar_colunas(grandes))


def _coluna_de(x: float, colunas: Sequence[Tuple[int, int]]) -> int:
    """
    Em qual faixa de coluna cai um x, e nunca `None`.

    Quem cai na calha fica com a faixa mais próxima. É o caso do elemento que
    atravessa — um título largo, uma linha de notação que transborda —, e pô-lo
    numa coluna é melhor que abrir uma terceira: a ordem de leitura já resolveu
    onde ele entra, e a coluna aqui só decide de quem ele é vizinho na hora de
    virar parágrafo.
    """
    if not colunas:
        return 0
    for i, (a, z) in enumerate(colunas):
        if a <= x <= z:
            return i
    return min(range(len(colunas)),
               key=lambda i: min(abs(x - colunas[i][0]), abs(x - colunas[i][1])))


def _celula(b: BoxEntry, escala: float) -> Tuple[int, int]:
    lado = max(1.0, escala * CELULA_DE_ORNAMENTO)
    return (int(((b.x1 + b.x2) / 2) // lado), int(((b.y1 + b.y2) / 2) // lado))


def _celulas_de_ornamento(respingos: Sequence[BoxEntry], escala: float) -> set:
    """As células da página onde há respingo demais para ser texto."""
    conta: dict = {}
    for b in respingos:
        chave = _celula(b, escala)
        conta[chave] = conta.get(chave, 0) + 1
    return {c for c, n in conta.items() if n >= RESPINGOS_DE_ORNAMENTO}


# ----------------------------------------------------------------------
# Caixas → linhas → parágrafos
# ----------------------------------------------------------------------

# A quebra em linhas mora em `core.leitura_de_linha` (importada acima). Estava
# duplicada aqui, byte a byte, e o motivo era de versionamento e não de desenho:
# a F17 precisou dela num módulo versionado, e este ainda não estava — um commit
# não pode depender de arquivo que não existe em HEAD. Resolvida a favor de lá,
# que é onde a regra é usada pelos quatro caminhos de reconhecimento.


def _texto_da_linha(img: np.ndarray, linha: Sequence[BoxEntry],
                    classificar: Callable, conf_minima: float,
                    coletor: Optional[Callable] = None,
                    pagina: int = 0) -> Tuple[str, int]:
    """
    (texto, quantos caíram por confiança).

    O `coletor` recebe todo caractere classificado, com a confiança junto. É
    aqui que ele entra porque é aqui que os dois dados existem juntos, e a
    função não sabe nem precisa saber o que ele faz com eles — nem sequer se
    ele vai guardar aquele.
    """
    larguras = [b.x2 - b.x1 for b in linha]
    largura = float(np.median(larguras)) or 1.0
    partes, fracos = [], 0
    for i, b in enumerate(linha):
        recorte = vertical.recorte_de_pe(img, b)
        char, conf = classificar(recorte) if recorte.size else ("", 0.0)
        # O coletor recebe **tudo** que foi classificado, e ele é que decide o
        # que guardar. Filtrar aqui prendia a coleta ao piso de confiança, e há
        # revisão que quer o contrário: a pasta cheia de acertos com alguns
        # intrusos, que é como se acha erro batendo o olho.
        if char and coletor is not None:
            coletor(recorte, char, conf, pagina)
        if char and conf < conf_minima:
            char, fracos = "", fracos + 1
        if i and b.x1 - linha[i - 1].x2 > largura * VAO_DE_ESPACO:
            partes.append(" ")
        # **Depois do coletor, e antes do texto.** A base de treino guarda o
        # recorte sob a classe que o modelo emitiu — é ela que ensina o modelo —,
        # e o livro recebe o que a classe significa: o `✝` do xeque sai `+`, e
        # uma busca por `Nxe4+` passa a achar a página. Ver `notacao`.
        partes.append(notacao.normalizar_saida(char or ""))
    return "".join(partes).strip(), fracos


#: Quanto da faixa uma régua de tabela precisa atravessar para ser régua (F72).
#:
#: A moldura é o que dá a grade, e a grade é o que separa célula de célula. Não
#: dá para tirá-la dos boxes: o `trama.aplicar` troca o bloco pelo que há dentro
#: dele, e a moldura não sobrevive à troca — vai-se buscá-la na imagem, onde ela
#: continua desenhada.
#:
#: Medido na tabela da página 236 do Nunn, que tem 4 colunas: a 0,6 aparecem 4
#: divisórias verticais e falta uma (a tabela sairia com 3 colunas); a 0,5 e a
#: 0,4 aparecem as 5 certas; a 0,3 entra uma sexta que não existe, na borda de
#: uma coluna de texto. O limiar fica no meio do vão.
REGUA_DA_TABELA = 0.5

#: Quanto do lado a régua precisa atravessar. Ver `REGUA_DA_TABELA`.


def _faixas_de_tinta(perfil: np.ndarray, minimo: float) -> List[Tuple[int, int]]:
    """Os trechos contíguos em que o perfil passa do mínimo."""
    faixas, inicio = [], None
    for i, v in enumerate(perfil):
        if v >= minimo:
            if inicio is None:
                inicio = i
        elif inicio is not None:
            faixas.append((inicio, i - 1))
            inicio = None
    if inicio is not None:
        faixas.append((inicio, len(perfil) - 1))
    return faixas


#: Quanto a moldura pode invadir o retângulo do texto, em frações dele.
#:
#: **Não é margem de segurança inventada: um pedaço da moldura vira glifo.** O
#: `trama.glifos` lê o que há dentro do bloco, e um trecho de borda partido pelo
#: scan tem tamanho de caractere. Medido na página 236 do Nunn, o texto começa
#: em x=156 e a régua esquerda em x=159 — a moldura fica *dentro* do retângulo
#: do texto, e a régua que a fecha seria descartada por não vir antes dele.
TOLERANCIA_DA_MOLDURA = 0.02


def _cercam(reguas: Sequence[Tuple[int, int]], inicio: int, fim: int
            ) -> List[Tuple[int, int]]:
    """
    As réguas que fecham o texto entre `inicio` e `fim`, e as de dentro.

    **É o que dispensa uma folga arbitrária.** Sabe-se onde está o texto, não
    onde está a moldura — ela não sobrevive à troca do bloco pelo conteúdo
    (F71). Procurar "a régua a tantos pixels" erra assim que a célula tem mais
    respiro: medido, o texto começa a 7 px da régua na tabela do Nunn e a 130 px
    na montagem do `test_f72`. Procurar a **última antes** e a **primeira
    depois** não depende de distância nenhuma.
    """
    tol = max(2, int((fim - inicio) * TOLERANCIA_DA_MOLDURA))
    antes = [r for r in reguas if r[1] <= inicio + tol]
    depois = [r for r in reguas if r[0] >= fim - tol]
    if not antes or not depois:
        return []
    topo, base = antes[-1], depois[0]
    return [r for r in reguas if topo[0] <= r[0] and r[1] <= base[1]]


def _grade(img: np.ndarray, regiao: Tuple[int, int, int, int]
           ) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
    """
    As réguas da moldura: `(horizontais, verticais)`, em coordenadas da página.

    Cada eixo é projetado na **extensão inteira da página**, e não numa janela
    em volta do texto: a régua se acha por onde ela está, e o `_cercam` escolhe
    as que pertencem a esta moldura. O que passa por régua tem de atravessar
    metade da faixa, e linha de texto não atravessa.

    **As verticais são medidas só no miolo**, entre a primeira e a última
    horizontal. Medi-las na altura toda mistura a divisória da tabela com o vão
    entre as colunas do texto que vem antes e depois dela, e foi assim que a
    divisória mais fraca da página 236 se perdeu.
    """
    x1, y1, x2, y2 = regiao
    if x2 <= x1 or y2 <= y1:
        return [], []

    escuro = img < 128
    largura = escuro[:, x1:x2 + 1]
    horizontais = _cercam(
        _faixas_de_tinta(largura.sum(axis=1) / largura.shape[1],
                         REGUA_DA_TABELA), y1, y2)
    if len(horizontais) < 2:
        return [], []

    miolo = escuro[horizontais[0][1]:horizontais[-1][0] + 1, :]
    if miolo.size == 0:
        return [], []
    verticais = _cercam(
        _faixas_de_tinta(miolo.sum(axis=0) / miolo.shape[0],
                         REGUA_DA_TABELA), x1, x2)
    return horizontais, verticais


def _celulas(cortes: Sequence[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Os vãos **entre** réguas consecutivas — é onde mora o conteúdo."""
    return [(cortes[i][1] + 1, cortes[i + 1][0] - 1)
            for i in range(len(cortes) - 1)
            if cortes[i + 1][0] - cortes[i][1] > 2]


def _tabela_da_pagina(img: np.ndarray, boxes: Sequence[BoxEntry],
                      classificar: Callable, conf_minima: float,
                      coletor, numero: int):
    """
    `(Tabela, boxes consumidos, topo, fracos)` — ou `None`, se não há tabela.

    **A marca diz onde olhar, e a grade decide.** Os boxes vêm marcados de
    dentro de uma moldura (F71), mas moldura não é tabela: o painel de pontuação
    da F11 vem marcado igual e não tem grade nenhuma. Sem duas linhas e duas
    colunas de réguas, devolve `None` e o conteúdo segue o caminho de sempre —
    parágrafos, como saía antes desta fase.

    **Uma moldura por página.** Duas tabelas na mesma página entrariam no mesmo
    retângulo envolvente e sairiam como uma só, embaralhada; não há caso no
    material medido, e o preço de errar seria alto demais para adivinhar.
    """
    de_moldura = [b for b in boxes if getattr(b, "moldura", False)]
    if not de_moldura:
        return None

    regiao = (min(b.x1 for b in de_moldura), min(b.y1 for b in de_moldura),
              max(b.x2 for b in de_moldura), max(b.y2 for b in de_moldura))
    horizontais, verticais = _grade(img, regiao)
    filas, colunas = _celulas(horizontais), _celulas(verticais)
    if len(filas) < 2 or len(colunas) < 2:
        return None

    matriz: List[List[str]] = []
    usados: List[BoxEntry] = []
    fracos = 0
    for ya, yz in filas:
        fila: List[str] = []
        for xa, xz in colunas:
            dentro = [b for b in de_moldura
                      if ya <= (b.y1 + b.y2) / 2 <= yz
                      and xa <= (b.x1 + b.x2) / 2 <= xz]
            usados.extend(dentro)
            partes = []
            # **`_agrupar_em_linhas`, e não a ordem de leitura da página.**
            # Aquela procura colunas, e dentro de uma célula acha: duas linhas
            # curtas deixam um vão vertical que passa por calha, e a célula sai
            # lida coluna a coluna. Medido na página 236 do Nunn, a primeira
            # célula saía `w win ( 1 B Draw ( l ♖e 1` — as duas linhas
            # intercaladas. Célula se lê linha a linha, sempre.
            for sub in quebrar_em_linhas(
                    BoxService._agrupar_em_linhas(dentro)):
                texto, n = _texto_da_linha(img, sub, classificar, conf_minima,
                                           coletor, numero)
                fracos += n
                if texto:
                    partes.append(texto)
            fila.append(" ".join(partes))
        matriz.append(fila)

    if not any(c for fila in matriz for c in fila):
        return None
    return Tabela(matriz), usados, regiao[1], fracos


@dataclass
class Linha:
    """Uma linha de texto lida, com o lugar dela na página."""

    topo: int
    esquerda: int
    altura: int
    texto: str
    #: Em qual das faixas de `detectar_colunas` esta linha está. Zero na página
    #: de coluna única, que é o caso em que tudo isto some.
    coluna: int = 0


def _metricas_por_coluna(linhas: Sequence[Linha]) -> dict:
    """
    {coluna: (margem esquerda, altura de linha)}, medidas na página inteira.

    **A margem é por coluna, e sem isso a de duas colunas sai despedaçada**
    (F61). A mediana das esquerdas de uma página de duas colunas não é margem
    nenhuma: metade das linhas começa em 122 e metade em 893, e a mediana cai
    num dos dois. Com ela, ou a coluna da direita inteira parece recuada — cada
    linha vira um parágrafo — ou a da esquerda perde todos os recuos que tem.

    **E é da página, não do trecho.** Estas medidas são medianas, e a mediana
    de cinco linhas entre dois diagramas não diz onde fica a margem da coluna.
    """
    metricas = {}
    for coluna in {l.coluna for l in linhas}:
        desta = [l for l in linhas if l.coluna == coluna]
        esquerdas = sorted(l.esquerda for l in desta)
        alturas = sorted(l.altura for l in desta)
        metricas[coluna] = (esquerdas[len(esquerdas) // 2],
                            alturas[len(alturas) // 2] or 1)
    return metricas


def _agrupar_em_paragrafos(linhas: Sequence[Linha],
                           metricas: Optional[dict] = None) -> List[Paragrafo]:
    """
    Linhas → parágrafos.

    Abre parágrafo no recuo da primeira linha, no salto vertical e na troca de
    coluna. As três regras juntas porque nenhuma sozinha cobre este livro: a
    prosa usa recuo, a notação em negrito entre parágrafos usa espaço em branco,
    e nenhuma das duas vê o fim da coluna — lá o salto vertical é **negativo**,
    porque a leitura volta ao topo da página.

    `metricas` vem do `_metricas_por_coluna` da página inteira; sem ela, sai
    destas linhas mesmo, que é o que serve a quem chama com a página toda.
    """
    if not linhas:
        return []
    if metricas is None:
        metricas = _metricas_por_coluna(linhas)

    paragrafos: List[Paragrafo] = []
    atual: List[str] = []
    anterior: Optional[Linha] = None
    for linha in linhas:
        margem, altura = metricas.get(linha.coluna,
                                      (linha.esquerda, linha.altura or 1))
        trocou = anterior is not None and linha.coluna != anterior.coluna
        recuou = linha.esquerda > margem + altura * RECUO_DE_PARAGRAFO
        saltou = (anterior is not None and not trocou
                  and linha.topo - anterior.topo
                  > altura * (1 + SALTO_DE_PARAGRAFO))
        if atual and (recuou or saltou or trocou):
            paragrafos.append(Paragrafo(" ".join(atual)))
            atual = []
        atual.append(linha.texto)
        anterior = linha
    if atual:
        paragrafos.append(Paragrafo(" ".join(atual)))
    return paragrafos


# ----------------------------------------------------------------------
# A página inteira
# ----------------------------------------------------------------------

#: Resolução com que o diagrama entra no livro exportado.
#:
#: A página é lida a 300 dpi porque é disso que a segmentação precisa, mas o
#: tabuleiro não precisa entrar no arquivo nesse tamanho: a 300 dpi ele sai com
#: 700 px e ~85 KB, e um livro de 264 páginas passaria de **50 MB** só de
#: figura. A 150 dpi são 350 px — mais que suficiente para ler num tablet — e o
#: arquivo cai para cerca de um quarto.
DPI_FIGURA = 150

#: Tons com que a figura é gravada.
#:
#: Um tabuleiro é desenho de linha: traço preto, casa branca, casa hachurada.
#: Guardá-lo com 256 tons é pagar por gradiente que não existe. Medido nas 529
#: figuras do Chess Evolution 1 — 33,3 MB em 8 bits:
#:
#:     16 tons   ~55% do tamanho
#:      4 tons   ~25%, e visualmente indistinguível do original
#:      1 bit     ~8%, mas escurece a hachura das casas
#:
#: Quatro é onde a conta para de valer a pena: o passo seguinte estraga o que
#: se vê.
TONS_DA_FIGURA = 4


def _png_do_recorte(img: np.ndarray, rect, dpi: int = 300,
                    dpi_figura: int = DPI_FIGURA,
                    tons: int = TONS_DA_FIGURA,
                    largura_px: Optional[int] = None) -> Tuple[bytes, int, int]:
    """
    Um pedaço da página vira PNG. `largura_px` manda mais que o `dpi_figura`.

    Quem passa `largura_px` é a faixa do cabeçalho (F60), e o motivo é o EPUB:
    lá a imagem sai no tamanho natural dela, então uma faixa recortada a 150 dpi
    apareceria com pouco mais da metade da largura de um tabuleiro **desenhado**
    a 528 px, e o cabeçalho ficaria menor que o diagrama que ele encabeça.
    """
    corte = Image.fromarray(img[rect[1]:rect[3], rect[0]:rect[2]])
    if largura_px:
        fator = largura_px / max(1, corte.width)
        corte = corte.resize((max(1, int(round(corte.width * fator))),
                              max(1, int(round(corte.height * fator)))),
                             Image.LANCZOS)
    elif dpi_figura and dpi_figura < dpi:
        fator = dpi_figura / dpi
        corte = corte.resize((max(1, int(corte.width * fator)),
                              max(1, int(corte.height * fator))),
                             Image.LANCZOS)
    largura, altura = corte.width, corte.height
    if tons and tons < 256:
        corte = corte.quantize(colors=tons)
    buffer = io.BytesIO()
    corte.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), largura, altura


def _faixa_em_texto(img: np.ndarray, d: Diagrama, classificar: Callable,
                    conf_minima: float, coletor: Optional[Callable],
                    numero: int) -> Optional[Paragrafo]:
    """
    O cabeçalho do diagrama lido como texto, ou `None` se não deu para ler.

    **Uma letra fraca já manda a faixa de volta para a imagem**, e é mais
    severo que o resto do livro de propósito: na prosa, um caractere derrubado
    por confiança deixa um buraco no meio de uma frase que o leitor remonta
    sozinho; aqui a faixa inteira tem quatro ou cinco caracteres — `➤ Ex. 22-1
    ◀ ★★ ▼` —, e um buraco nela é o número do exercício, que é justamente o que
    alguém procuraria.

    Sai como `titulo` porque é isso que ela é: no EPUB vira `<h2>` e no DOCX,
    `Heading 2`. O leitor ganha um sumário navegável de graça.
    """
    if not d.caixas_da_faixa:
        return None
    partes = []
    for linha in quebrar_em_linhas(d.caixas_da_faixa):
        texto, fracos = _texto_da_linha(img, linha, classificar, conf_minima,
                                        coletor, numero)
        if fracos or not texto:
            return None
        partes.append(texto)
    if not partes:
        return None
    return Paragrafo(" ".join(partes), titulo=True)


#: Os dois modos de pôr um diagrama no livro.
#:
#: **`render` é o padrão porque a medição da F58 o autorizou**, e não porque é
#: mais bonito: o porteiro deixa escapar 2 leituras erradas em 346 (1 em 173,
#: contra 1 em 14 sem ele), e o que ele barra cai para o recorte — que é
#: exatamente o que este módulo exportava antes.
MODOS_DE_DIAGRAMA = ("render", "recorte")

#: O terceiro valor de `coordenadas`: as que o livro imprimiu (F95).
#:
#: Não é o padrão da API — quem chamava com `True` ou `False` continua tendo o
#: livro inteiro de um jeito só —, mas é o que a janela de exportação oferece
#: primeiro. Diagrama por diagrama, e não por livro: um mesmo volume imprime o
#: exercício com coordenadas e o diagrama no meio da prosa sem.
COMO_NO_LIVRO = "auto"


def _quer_coordenadas(escolha, d: Diagrama) -> bool:
    """
    Este diagrama sai com rótulo de casa?

    `escolha` é `True`, `False` ou `COMO_NO_LIVRO`. No terceiro caso quem
    responde é o que `diagrama.ler_rotulos` achou em volta **deste** tabuleiro.
    """
    if escolha == COMO_NO_LIVRO:
        return d.rotulos.presentes
    return bool(escolha)


def _figura_do_diagrama(img: np.ndarray, d: Diagrama, *, dpi: int,
                        dpi_figura: int, modo: str, coordenadas, fonte: str,
                        lado: int,
                        moldura=render_diagrama.MOLDURA_PADRAO) -> Figura:
    """
    Um tabuleiro da página vira figura: desenhado, se merecer; recortado, se não.

    **A leitura entra pelo `tabuleiro` e o recorte sai pela `exclusao`**, e a
    troca dos dois é o defeito que a `Diagrama` existe para tornar impossível.

    Quando não há coordenadas a pedir, o recorte também sai justo: o desenho e o
    recorte convivem no mesmo livro, e um com rótulo e outro sem seria a única
    diferença visível entre uma página em que o modelo se saiu bem e outra em
    que não.

    **`coordenadas` tem três valores desde a F95**, e o terceiro é
    `COMO_NO_LIVRO`: cada diagrama sai com o que o livro imprimiu em volta
    dele. Quem resolve é `_quer_coordenadas`, e ela responde por diagrama.

    **A orientação lida entra no desenho, e não no FEN** (F95). O FEN é sempre o
    da posição; se o livro imprimiu o diagrama do lado das pretas, é o desenho
    que se vira, para a página exportada continuar parecendo a página impressa.
    """
    aviso = None
    quer = _quer_coordenadas(coordenadas, d)
    if modo == "render":
        try:
            leitura = diagrama.ler(img, d.tabuleiro,
                                   orientacao=d.rotulos.orientacao or "branca")
            passa, aviso = diagrama.confiavel(leitura)
            if passa:
                fen = leitura.fen()
                png, larg, alt = render_diagrama.desenhar(
                    fen, fonte=fonte, lado_px=lado, coordenadas=quer,
                    moldura=moldura, orientacao=leitura.orientacao)
                return Figura(png, larg, alt, fen=fen, origem="render",
                              linhas=render_diagrama.linhas(
                                  fen, render_diagrama.carregar(fonte),
                                  leitura.orientacao),
                              fonte=fonte, coordenadas=quer,
                              orientacao=leitura.orientacao,
                              casas_de_largura=(
                                  larg * 8.0
                                  / render_diagrama.lado_efetivo(lado)))
        except (diagrama.ModeloAusente, render_diagrama.FonteDesconhecida,
                render_diagrama.FonteIncompleta) as erro:
            # Falta de modelo ou de fonte não pode derrubar a exportação de um
            # livro de 264 páginas: cai para o recorte e diz por quê, uma vez
            # por diagrama, onde quem lê o relatório vai ver.
            aviso = f"não deu para desenhar: {erro}"

    rect = d.exclusao if quer else d.tabuleiro
    png, larg, alt = _png_do_recorte(img, rect, dpi, dpi_figura)
    # O recorte também sabe medir-se em casas: o tabuleiro dele está na página,
    # e é o `d.tabuleiro`. Sem isto o desenho sairia no corpo pedido e o recorte
    # da página ao lado sairia noutro tamanho — no mesmo livro, na mesma página.
    na_pagina = max(1, d.tabuleiro[2] - d.tabuleiro[0])
    return Figura(png, larg, alt, origem="recorte", aviso=aviso,
                  coordenadas=quer,
                  casas_de_largura=8.0 * (rect[2] - rect[0]) / na_pagina)


def extrair_pagina(page: fitz.Page, classificar: Callable, *, numero: int = 0,
                   dpi: int = 300, conf_minima: float = CONF_MINIMA,
                   dpi_figura: int = DPI_FIGURA,
                   coletor: Optional[Callable] = None,
                   diagramas: str = "render", coordenadas=False,
                   fonte: str = render_diagrama.FONTE_PADRAO,
                   lado_do_diagrama: int = render_diagrama.LADO_PADRAO,
                   moldura=render_diagrama.MOLDURA_PADRAO
                   ) -> PaginaExtraida:
    """
    Uma página do PDF vira parágrafos e figuras, lendo só a imagem.

    As figuras entram na ordem pela altura em que o diagrama está na página, e
    não todas no fim: um diagrama que fica no meio da coluna tem texto antes e
    depois dele, e jogá-lo para o fim desmancha a leitura.

    **Numa página de duas colunas, "a altura" é dentro da coluna** (F61). O
    diagrama do alto da coluna da direita está *acima* de quase toda a coluna da
    esquerda, e intercalar pela altura na página o punha antes de um texto que
    se lê muito antes dele. Cada figura entra na coluna a que pertence, e a
    coluna que se deixa é despejada antes de a próxima começar.

    `coordenadas` tem três valores (F95): `True`, `False` e `COMO_NO_LIVRO`.
    O padrão continua sendo `False` — o livro impresso traz `a`–`h` e `8`–`1`
    para quem vai falar da posição em voz alta, e num arquivo que se lê no
    tablet elas ocupam espaço e não dizem nada que o tabuleiro já não diga.
    `COMO_NO_LIVRO` decide **por diagrama**, pelo que `diagrama.ler_rotulos`
    achou em volta de cada um; e um mesmo livro mistura os dois casos na mesma
    página.
    """
    if diagramas not in MODOS_DE_DIAGRAMA:
        raise ValueError(f"modo de diagrama inválido: {diagramas!r} "
                         f"(use um de {MODOS_DE_DIAGRAMA})")
    # Recusado, e não tratado como verdadeiro: `coordenadas` passou a aceitar
    # uma string (F95), e a partir daí um `"Auto"` com maiúscula ou um `"nao"`
    # seriam **verdadeiros** — o livro inteiro sairia rotulado, em silêncio, por
    # causa de um erro de digitação.
    if coordenadas not in (True, False, COMO_NO_LIVRO):
        raise ValueError(f"coordenadas inválidas: {coordenadas!r} "
                         f"(use True, False ou {COMO_NO_LIVRO!r})")

    img = _pagina_cinza(page, dpi)
    boxes, tabuleiros, _escala, respingos, colunas = caixas_e_diagramas(
        img, classificar)

    if not boxes and not tabuleiros:
        # Página de imagem: entra inteira, como está.
        png, larg, alt = _png_do_recorte(
            img, (0, 0, img.shape[1], img.shape[0]), dpi, dpi_figura)
        return PaginaExtraida(numero=numero,
                              blocos=[Figura(png, larg, alt, origem="pagina")],
                              pagina_de_imagem=True)

    fracos = 0
    # A tabela sai da página antes das linhas: as células dela não são linhas de
    # prosa, e deixá-las virar parágrafo é o defeito que a F72 fecha.
    achado = _tabela_da_pagina(img, boxes, classificar, conf_minima, coletor,
                               numero)
    tabela = topo_da_tabela = None
    if achado is not None:
        tabela, usados, topo_da_tabela, fracos = achado
        consumidos = {id(b) for b in usados}
        boxes = [b for b in boxes if id(b) not in consumidos]
        # As colunas **não** se recontam aqui, e chegou-se a isso medindo: as
        # células atravessam a página e apagam a calha, então recontá-las sem a
        # tabela parecia devolver as duas colunas de baixo. Nas 6 tabelas do
        # material a conta não muda em nenhuma — a página que tem tabela é de
        # coluna única também abaixo dela.

    medidas: List[Linha] = []
    for linha in quebrar_em_linhas(boxes):
        texto, n = _texto_da_linha(img, linha, classificar, conf_minima,
                                   coletor, numero)
        fracos += n
        if texto:
            medidas.append(Linha(
                topo=min(b.y1 for b in linha),
                esquerda=min(b.x1 for b in linha),
                altura=int(np.median([b.y2 - b.y1 for b in linha])),
                texto=texto,
                coluna=_coluna_de((min(b.x1 for b in linha)
                                   + max(b.x2 for b in linha)) / 2, colunas)))

    resultado = PaginaExtraida(numero=numero, diagramas=len(tabuleiros),
                               respingos_descartados=respingos,
                               descartados_por_confianca=fracos,
                               colunas=len(colunas))

    def figura(d: Diagrama) -> List[Bloco]:
        """
        A faixa do cabeçalho, quando ela não está no próprio recorte, e o
        diagrama.

        **A faixa é pulada num caso só**: recorte com coordenadas, em que a
        figura já sai pelo retângulo de exclusão e traz o cabeçalho dentro. Nos
        outros três — desenho com ou sem coordenadas, recorte justo — o
        tabuleiro sai sozinho, e sem esta figura o `➤ Ex. 22-1 ◀ ★★ ▼` some do
        livro: não vira texto, porque a margem o excluiu, e não vira imagem,
        porque a imagem passou a ser só o tabuleiro.

        **Ela sai como texto quando dá, e como imagem quando não dá** (F67). Foi
        imagem primeiro, e imagem não se pesquisa: o leitor que procura
        "Ex. 22-1" no arquivo exportado não acha a página do exercício. Como
        título, ela ainda ganha o `<h2>` do EPUB e o `Heading 2` do DOCX, que é
        por onde o sumário do leitor navega.
        """
        principal = _figura_do_diagrama(img, d, dpi=dpi, dpi_figura=dpi_figura,
                                        modo=diagramas, coordenadas=coordenadas,
                                        fonte=fonte, lado=lado_do_diagrama,
                                        moldura=moldura)
        # A legenda de baixo entra **depois** da figura, que é onde ela está
        # impressa (F95). Não é `titulo=True`: título embaixo da figura viraria
        # um `<h2>` no meio do texto seguinte, e o que ela é, é legenda.
        depois = ([Paragrafo(d.legenda.texto)]
                  if d.legenda.texto and not (principal.origem == "recorte"
                                              and principal.coordenadas)
                  else [])
        ja_esta_dentro = principal.origem == "recorte" and principal.coordenadas
        if d.faixa is None or ja_esta_dentro:
            return [principal] + depois

        cabecalho = _faixa_em_texto(img, d, classificar, conf_minima, coletor,
                                    numero)
        if cabecalho is not None:
            return [cabecalho, principal] + depois

        # A faixa entra na mesma escala do tabuleiro: o que na página media a
        # largura da borda tem de medir, no arquivo, a largura da figura.
        na_pagina = max(1, d.tabuleiro[2] - d.tabuleiro[0])
        alvo = int(round((d.faixa[2] - d.faixa[0]) * principal.largura / na_pagina))
        png, larg, alt = _png_do_recorte(img, d.faixa, dpi, dpi_figura,
                                         largura_px=alvo)
        # A escala da faixa é a do tabuleiro, e a medida em casas vai junto: a
        # faixa foi reamostrada para a largura da figura, então basta a regra de
        # três (F97). Sem isto o cabeçalho sairia na largura de antes e o
        # tabuleiro no corpo pedido — e o cabeçalho ficaria maior que o diagrama
        # que ele encabeça.
        em_casas = (principal.casas_de_largura * larg / max(1, principal.largura)
                    if principal.casas_de_largura else None)
        return [Figura(png, larg, alt, origem="faixa",
                       casas_de_largura=em_casas), principal] + depois

    # Intercalar texto e figura, coluna a coluna e por posição vertical.
    metricas = _metricas_por_coluna(medidas)
    # Por coluna e, dentro dela, por altura: é a ordem em que elas saem quando
    # não houver texto embaixo de que pendurá-las.
    pendentes = sorted(
        ((_coluna_de((d.tabuleiro[0] + d.tabuleiro[2]) / 2, colunas), d)
         for d in tabuleiros),
        key=lambda par: (par[0], par[1].topo))
    corrente: List[Linha] = []

    def despejar(coluna: int, ate: Optional[int] = None) -> None:
        """As figuras daquela coluna que já passaram — todas, se `ate` é None."""
        nonlocal corrente, pendentes
        restam = []
        for col, d in pendentes:
            if col != coluna or (ate is not None and d.topo >= ate):
                restam.append((col, d))
                continue
            resultado.blocos.extend(_agrupar_em_paragrafos(corrente, metricas))
            corrente = []
            resultado.blocos.extend(figura(d))
        pendentes = restam

    def soltar_tabela(ate: Optional[int] = None) -> None:
        """
        A tabela entra pela altura, como as figuras, e não no fim da página.

        Atravessa a largura toda, então não é de coluna nenhuma: o que a
        posiciona é só o topo dela contra o topo da linha corrente.
        """
        nonlocal corrente, tabela
        if tabela is None or (ate is not None and topo_da_tabela >= ate):
            return
        resultado.blocos.extend(_agrupar_em_paragrafos(corrente, metricas))
        corrente = []
        resultado.blocos.append(tabela)
        tabela = None

    coluna_anterior: Optional[int] = None
    for medida in medidas:
        if coluna_anterior is not None and medida.coluna != coluna_anterior:
            # O rodapé da coluna que se deixa entra antes do topo da próxima.
            despejar(coluna_anterior)
        despejar(medida.coluna, ate=medida.topo)
        soltar_tabela(ate=medida.topo)
        corrente.append(medida)
        coluna_anterior = medida.coluna
    resultado.blocos.extend(_agrupar_em_paragrafos(corrente, metricas))
    corrente = []
    soltar_tabela()
    for _col, d in pendentes:
        resultado.blocos.extend(figura(d))

    # As células contam como caractere da página: são texto lido, e é por este
    # número que o relatório do fim da exportação diz se a página rendeu (F72).
    resultado.caracteres = sum(
        len(b.texto) if isinstance(b, Paragrafo)
        else sum(len(c) for fila in b.linhas for c in fila)
        for b in resultado.blocos
        if isinstance(b, (Paragrafo, Tabela)))
    resultado.diagramas_desenhados = sum(
        1 for b in resultado.blocos
        if isinstance(b, Figura) and b.origem == "render")
    return resultado


def extrair(input_pdf: str, classificar: Callable, *, dpi: int = 300,
            paginas: Optional[Sequence[int]] = None,
            conf_minima: float = CONF_MINIMA, dpi_figura: int = DPI_FIGURA,
            coletor: Optional[Callable] = None,
            diagramas: str = "render", coordenadas=False,
            fonte: str = render_diagrama.FONTE_PADRAO,
            lado_do_diagrama: int = render_diagrama.LADO_PADRAO,
            moldura=render_diagrama.MOLDURA_PADRAO,
            progress_callback=None) -> List[PaginaExtraida]:
    """Lê o PDF inteiro (ou as páginas pedidas) como imagem."""
    import os
    if not os.path.exists(input_pdf):
        raise FileNotFoundError(f"Arquivo não encontrado: {input_pdf}")

    doc = fitz.open(input_pdf)
    try:
        numeros = list(range(len(doc))) if paginas is None else list(paginas)
        saida = []
        for i, numero in enumerate(numeros):
            if progress_callback:
                progress_callback(i, len(numeros))
            saida.append(extrair_pagina(doc[numero], classificar, numero=numero,
                                        dpi=dpi, conf_minima=conf_minima,
                                        dpi_figura=dpi_figura, coletor=coletor,
                                        diagramas=diagramas,
                                        coordenadas=coordenadas, fonte=fonte,
                                        lado_do_diagrama=lado_do_diagrama,
                                        moldura=moldura))
        if progress_callback:
            progress_callback(len(numeros), len(numeros))
        return saida
    finally:
        doc.close()
