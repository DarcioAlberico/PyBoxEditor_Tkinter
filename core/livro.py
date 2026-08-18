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
"""

import io
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple, Union


import fitz
import numpy as np
from PIL import Image

from core import diagrama, render_diagrama, vertical
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
VAO_DE_ESPACO = 0.35

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


Bloco = Union[Paragrafo, Figura]


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

    @property
    def texto(self) -> str:
        return "\n\n".join(b.texto for b in self.blocos if isinstance(b, Paragrafo))


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

    @property
    def topo(self) -> int:
        return self.exclusao[1]


def caixas_e_diagramas(img: np.ndarray, classificar: Callable
                       ) -> Tuple[List[BoxEntry], List["Diagrama"], int, int]:
    """
    (caixas de texto em ordem de leitura, diagramas, escala, respingos).

    O tabuleiro sai do `boxes_antes_do_descarte`, que é o estágio em que ele
    ainda existe como caixa. Refazer essas etapas aqui fora foi tentado e não
    funciona: falta uma delas e o `localizar` acha 6 tabuleiros onde há 2,
    levando o texto da página junto.
    """
    pil = Image.fromarray(img)
    antes, _th, escala, _cinza = BoxService.boxes_antes_do_descarte(
        pil, max_contornos=BoxService.MAX_CONTORNOS_DE_TEXTO)
    escala = escala or 1
    if not antes:
        # Página que é imagem, não texto. Sai inteira como figura: ler caractere
        # dela custaria minutos e devolveria ruído.
        return [], [], escala, 0

    diagramas = [Diagrama(exclusao=_com_margem(r, escala * MARGEM_DIAGRAMA,
                                               img.shape),
                          tabuleiro=r)
                 for r in diagrama.localizar(antes, escala=escala)]
    rects = [d.exclusao for d in diagramas]

    boxes = BoxService.generate_boxes_opencv(pil, arbitro=classificar)
    boxes = [b for b in boxes if not any(_dentro(b, r) for r in rects)]

    minima = MIN_AREA_GLIFO * escala * escala
    grandes, respingos = [], []
    for b in boxes:
        (grandes if (b.x2 - b.x1) * (b.y2 - b.y1) >= minima else respingos).append(b)

    ornamento = _celulas_de_ornamento(respingos, escala)
    grandes = [b for b in grandes
               if _celula(b, escala) not in ornamento]

    return (BoxService.sort_boxes_reading_order(grandes), diagramas, escala,
            len(respingos))


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
        partes.append(char or "")
    return "".join(partes).strip(), fracos


def _agrupar_em_paragrafos(linhas: List[Tuple[int, int, int, str]]) -> List[Paragrafo]:
    """
    (topo, esquerda, altura, texto) → parágrafos.

    Abre parágrafo no recuo da primeira linha e no salto vertical. As duas
    regras juntas porque nenhuma sozinha cobre este livro: a prosa usa recuo, e
    a notação em negrito entre parágrafos usa espaço em branco.
    """
    if not linhas:
        return []

    esquerdas = sorted(e for _t, e, _a, _x in linhas)
    margem = esquerdas[len(esquerdas) // 2]
    alturas = sorted(a for _t, _e, a, _x in linhas)
    altura = alturas[len(alturas) // 2] or 1

    paragrafos: List[Paragrafo] = []
    atual: List[str] = []
    anterior = None
    for topo, esq, _alt, texto in linhas:
        recuou = esq > margem + altura * RECUO_DE_PARAGRAFO
        saltou = anterior is not None and topo - anterior > altura * (1 + SALTO_DE_PARAGRAFO)
        if atual and (recuou or saltou):
            paragrafos.append(Paragrafo(" ".join(atual)))
            atual = []
        atual.append(texto)
        anterior = topo
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
                    tons: int = TONS_DA_FIGURA) -> Tuple[bytes, int, int]:
    corte = Image.fromarray(img[rect[1]:rect[3], rect[0]:rect[2]])
    if dpi_figura and dpi_figura < dpi:
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


#: Os dois modos de pôr um diagrama no livro.
#:
#: **`render` é o padrão porque a medição da F58 o autorizou**, e não porque é
#: mais bonito: o porteiro deixa escapar 2 leituras erradas em 346 (1 em 173,
#: contra 1 em 14 sem ele), e o que ele barra cai para o recorte — que é
#: exatamente o que este módulo exportava antes.
MODOS_DE_DIAGRAMA = ("render", "recorte")


def _figura_do_diagrama(img: np.ndarray, d: Diagrama, *, dpi: int,
                        dpi_figura: int, modo: str, coordenadas: bool,
                        fonte: str, lado: int) -> Figura:
    """
    Um tabuleiro da página vira figura: desenhado, se merecer; recortado, se não.

    **A leitura entra pelo `tabuleiro` e o recorte sai pela `exclusao`**, e a
    troca dos dois é o defeito que a `Diagrama` existe para tornar impossível.

    Quando não há coordenadas a pedir, o recorte também sai justo: o desenho e o
    recorte convivem no mesmo livro, e um com rótulo e outro sem seria a única
    diferença visível entre uma página em que o modelo se saiu bem e outra em
    que não.
    """
    aviso = None
    if modo == "render":
        try:
            leitura = diagrama.ler(img, d.tabuleiro)
            passa, aviso = diagrama.confiavel(leitura)
            if passa:
                fen = leitura.fen()
                png, larg, alt = render_diagrama.desenhar(
                    fen, fonte=fonte, lado_px=lado, coordenadas=coordenadas)
                return Figura(png, larg, alt, fen=fen, origem="render",
                              linhas=render_diagrama.linhas(
                                  fen, render_diagrama.carregar(fonte)),
                              fonte=fonte, coordenadas=coordenadas)
        except (diagrama.ModeloAusente, render_diagrama.FonteDesconhecida,
                render_diagrama.FonteIncompleta) as erro:
            # Falta de modelo ou de fonte não pode derrubar a exportação de um
            # livro de 264 páginas: cai para o recorte e diz por quê, uma vez
            # por diagrama, onde quem lê o relatório vai ver.
            aviso = f"não deu para desenhar: {erro}"

    rect = d.exclusao if coordenadas else d.tabuleiro
    png, larg, alt = _png_do_recorte(img, rect, dpi, dpi_figura)
    return Figura(png, larg, alt, origem="recorte", aviso=aviso)


def extrair_pagina(page: fitz.Page, classificar: Callable, *, numero: int = 0,
                   dpi: int = 300, conf_minima: float = CONF_MINIMA,
                   dpi_figura: int = DPI_FIGURA,
                   coletor: Optional[Callable] = None,
                   diagramas: str = "render", coordenadas: bool = False,
                   fonte: str = render_diagrama.FONTE_PADRAO,
                   lado_do_diagrama: int = render_diagrama.LADO_PADRAO
                   ) -> PaginaExtraida:
    """
    Uma página do PDF vira parágrafos e figuras, lendo só a imagem.

    As figuras entram na ordem pela altura em que o diagrama está na página, e
    não todas no fim: um diagrama que fica no meio da coluna tem texto antes e
    depois dele, e jogá-lo para o fim desmancha a leitura.

    `coordenadas` é **falso por padrão** nos dois modos. O livro impresso traz
    `a`–`h` e `8`–`1` para quem vai falar da posição em voz alta; num arquivo
    que se lê no tablet elas ocupam espaço e não dizem nada que o tabuleiro já
    não diga.
    """
    if diagramas not in MODOS_DE_DIAGRAMA:
        raise ValueError(f"modo de diagrama inválido: {diagramas!r} "
                         f"(use um de {MODOS_DE_DIAGRAMA})")

    img = _pagina_cinza(page, dpi)
    boxes, tabuleiros, _escala, respingos = caixas_e_diagramas(img, classificar)

    if not boxes and not tabuleiros:
        # Página de imagem: entra inteira, como está.
        png, larg, alt = _png_do_recorte(
            img, (0, 0, img.shape[1], img.shape[0]), dpi, dpi_figura)
        return PaginaExtraida(numero=numero,
                              blocos=[Figura(png, larg, alt, origem="pagina")],
                              pagina_de_imagem=True)

    medidas: List[Tuple[int, int, int, str]] = []
    fracos = 0
    for linha in quebrar_em_linhas(boxes):
        texto, n = _texto_da_linha(img, linha, classificar, conf_minima,
                                   coletor, numero)
        fracos += n
        if texto:
            medidas.append((min(b.y1 for b in linha), min(b.x1 for b in linha),
                            int(np.median([b.y2 - b.y1 for b in linha])), texto))

    resultado = PaginaExtraida(numero=numero, diagramas=len(tabuleiros),
                               respingos_descartados=respingos,
                               descartados_por_confianca=fracos)

    def figura(d: Diagrama) -> Figura:
        return _figura_do_diagrama(img, d, dpi=dpi, dpi_figura=dpi_figura,
                                   modo=diagramas, coordenadas=coordenadas,
                                   fonte=fonte, lado=lado_do_diagrama)

    # Intercalar texto e figura pela posição vertical.
    figuras = sorted(tabuleiros, key=lambda d: d.topo)
    i = 0
    corrente: List[Tuple[int, int, int, str]] = []
    for medida in medidas:
        while i < len(figuras) and figuras[i].topo < medida[0]:
            resultado.blocos.extend(_agrupar_em_paragrafos(corrente))
            corrente = []
            resultado.blocos.append(figura(figuras[i]))
            i += 1
        corrente.append(medida)
    resultado.blocos.extend(_agrupar_em_paragrafos(corrente))
    for d in figuras[i:]:
        resultado.blocos.append(figura(d))

    resultado.caracteres = sum(len(b.texto) for b in resultado.blocos
                               if isinstance(b, Paragrafo))
    resultado.diagramas_desenhados = sum(
        1 for b in resultado.blocos
        if isinstance(b, Figura) and b.origem == "render")
    return resultado


def extrair(input_pdf: str, classificar: Callable, *, dpi: int = 300,
            paginas: Optional[Sequence[int]] = None,
            conf_minima: float = CONF_MINIMA, dpi_figura: int = DPI_FIGURA,
            coletor: Optional[Callable] = None,
            diagramas: str = "render", coordenadas: bool = False,
            fonte: str = render_diagrama.FONTE_PADRAO,
            lado_do_diagrama: int = render_diagrama.LADO_PADRAO,
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
                                        lado_do_diagrama=lado_do_diagrama))
        if progress_callback:
            progress_callback(len(numeros), len(numeros))
        return saida
    finally:
        doc.close()
