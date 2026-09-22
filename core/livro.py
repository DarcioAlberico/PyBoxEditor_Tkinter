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
import re
from difflib import SequenceMatcher
from array import array
import collections
import os
from dataclasses import dataclass, field
from math import isnan, nan
from typing import Callable, List, Optional, Sequence, Tuple, Union


import fitz
import numpy as np
from PIL import Image

from core import (diagrama, lado_a_jogar as lado_jogar, lexico, negrito,
                  notacao, render_diagrama, vertical)
from core.box_model import BoxEntry
from core.leitura_de_linha import MARGEM as MARGEM_DA_FAIXA, quebrar_em_linhas
from core.ocr_result import RegionResult
from core.ocr_routing import OCRRouter
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

#: Vão entre dois caracteres que vira espaço.
#:
#: **A régua deixou de ser um número na F107** e passou a ser
#: `diagrama.limiar_de_espaco`, que mede contra o vão típico da linha em vez de
#: contra a largura de tinta. Este reexporte fica de pé para quem já o
#: importava; a constante que ele traz é a régua velha, e não a de produção.
#:
#: O número mora em `diagrama` desde a F95, porque o título do diagrama usa a
#: mesma régua e aquele módulo não pode importar este. Uma definição só.
VAO_DE_ESPACO = diagrama.VAO_DE_ESPACO

#: Recuo que abre parágrafo, e salto vertical que abre parágrafo, ambos em
#: alturas de linha.
#: O recuo que abre parágrafo, em **passos de linha** (F103).
RECUO_DE_PARAGRAFO = 0.8

#: O vão que abre parágrafo, em **passos de linha** além do passo (F103).
#:
#: **A unidade era a altura de glifo, e por isso a regra nunca funcionou.** A
#: `Linha.altura` é a mediana da altura dos glifos daquela linha, e numa fonte
#: de texto isso é a altura de x — sem ascendente nem descendente. O passo entre
#: linhas mede quase o triplo disso, então todo passo normal já parecia vão de
#: parágrafo. Medido em 40.828 transições do Aagaard, o salto sobre a altura de
#: glifo tem **mediana 2,62** e décimo percentil 1,86, contra o limite de 1,6:
#: 99,3% das linhas abriam parágrafo, e o livro exportado saía com um parágrafo
#: por linha impressa.
#:
#: Não era defeito daquele livro. Medido em seis, a mediana vai de 1,91 a 2,74,
#: e a fração acima do limite de 86% a 100%. Sobre o passo da coluna a mediana é
#: **1,00 nos seis**, que é o que se espera de uma medida normalizada por si
#: mesma, e a regra vira subconjunto estrito da de antes: no Aagaard inteiro ela
#: concorda em 8.515 quebras, deixa de fazer 31.164 e não inventa nenhuma.
SALTO_DE_PARAGRAFO = 0.6

#: Quantas alturas de glifo mede um passo de linha, quando não há passo medido.
#:
#: Só serve à coluna de uma linha só, que não tem vão nenhum para medir — e
#: onde, por definição, não há segunda linha para abrir parágrafo. É a mediana
#: das medianas dos seis livros (1,91 a 2,74), e está aqui para o cálculo nunca
#: dividir por zero, não para decidir coisa alguma.
PASSO_POR_ALTURA = 2.4


@dataclass
class Paragrafo:
    texto: str
    titulo: bool = False
    #: O nível do título, quando `titulo` (F111): 1 é capítulo, 2 é o
    #: cabeçalho de diagrama que a faixa marca desde a F67. Sai como `<h1>` e
    #: `Heading 1` num, `<h2>` e `Heading 2` no outro — e é o `<h1>` que faz o
    #: sumário do leitor ter capítulo em vez de 390 legendas.
    nivel: int = 2
    #: Os trechos `(início, fim)` do `texto` que estão impressos em negrito
    #: (F105). Fatias do próprio `texto`, e não texto marcado: quem lê o
    #: parágrafo para escolher a fonte dos símbolos, para o léxico ou para o
    #: PGN continua lendo o que estava escrito, sem marcação nenhuma no meio.
    negrito: List[Tuple[int, int]] = field(default_factory=list)
    #: A espessura do traço de cada caractere do `texto`, em alturas do glifo —
    #: `nan` no que não deu para medir, e no espaço entre palavras.
    #:
    #: É a matéria-prima do `negrito`, e não o resultado: quem decide é
    #: `negrito.marcar`, e ele precisa do livro inteiro para saber qual é o peso
    #: redondo de cada caractere. Fica guardado depois da decisão porque é o que
    #: permite remarcar — o `extrair_pagina` marca com uma página por
    #: referência, e o `extrair` remarca com todas.
    pesos: Optional[array] = None
    #: A lacuna antes de cada caractere do `texto`, em larguras medianas da
    #: linha — `nan` no que não deu para medir (F115).
    #:
    #: Está aqui pela mesma razão que `pesos`: quem decide onde faltou espaço é
    #: `partir_coladas`, e ele precisa do **livro inteiro** para saber quais
    #: palavras existem nele. Guardar a medida por parágrafo é o que permite
    #: adiar a decisão até haver livro.
    lacunas: Optional[array] = None
    #: Onde o parágrafo começa e acaba na página, em pixels da imagem lida
    #: (F109).
    #:
    #: É o que `retirar_cabecalhos` precisa para saber se um parágrafo está na
    #: margem de cima ou na de baixo — a ordem dos blocos não diz isso numa
    #: página de duas colunas, onde o rodapé centrado cai no meio da lista.
    #: `None` no parágrafo que não veio de linhas da página: a faixa do
    #: diagrama, a legenda, e os que os testes montam à mão.
    topo: Optional[int] = None
    pe: Optional[int] = None
    #: Onde cada linha impressa começa no `texto` (F109). A primeira é `0`.
    #:
    #: **O parágrafo não esquece a linha**, e é isto que permite tirar dele o
    #: cabeçalho de página que a régua do salto (F103) colou ao primeiro
    #: parágrafo — no Aagaard é o caso de quase toda página. Vazio no
    #: parágrafo montado à mão.
    inicios: List[int] = field(default_factory=list)
    #: O índice, em `PaginaExtraida.roteamento`, do registro de cada linha
    #: impressa — paralelo a `inicios`, e `-1` na linha que não veio da
    #: página. É o que liga o parágrafo às duas leituras de cada linha (a
    #: âncora da cadeia e a linha do motor): a fila de revisão mostra o
    #: recorte da linha e as alternativas dela por aqui, e sem isto o
    #: parágrafo já pronto não sabia mais de que linhas tinha saído.
    registros: List[int] = field(default_factory=list)

    @property
    def linhas_impressas(self) -> int:
        return len(self.inicios)


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
    #: As `linhas` já trazem a moldura e as coordenadas, em glifo da própria
    #: fonte de xadrez (F99) — são dez de dez, e não oito de oito.
    #:
    #: **É o que faz o diagrama com coordenada caber no modo de fonte.** Sem
    #: isto o rótulo tem de sair em fonte de texto, e aí o EPUB precisa de um
    #: `<i>` dentro de um `<span>` para alinhá-lo com a casa, e o DOCX precisa
    #: desistir e mandar a figura como imagem. Quem tem os glifos escreve as dez
    #: linhas e acabou — e quem escreve o arquivo não põe moldura por fora,
    #: porque ela já está dentro do texto.
    linhas_emolduradas: bool = False
    #: Onde o tabuleiro está na página lida — o `Diagrama.tabuleiro`, em
    #: pixels da imagem a `PaginaExtraida.dpi`. `None` na figura que não veio
    #: de um tabuleiro da página (a página inteira que virou imagem).
    #:
    #: É o que a fila de revisão precisa para abrir o diagrama **ao lado do
    #: recorte impresso**, na mesma escala, e não só ao lado do desenho que o
    #: modelo fez dele: conferir uma posição contra o desenho dela é conferir
    #: a leitura contra si mesma.
    caixa: Optional[Tuple[int, int, int, int]] = None
    #: De quem é a vez, e de onde isso veio (item 3 da revisão de 2026-09-18).
    #:
    #: O tabuleiro não desenha o lado a jogar, e o FEN exige o campo: por seis
    #: fases ele saiu `w` em silêncio. Quando a legenda ou o cabeçalho do
    #: diagrama dizem ("White to play", "as pretas jogam"), o lado é leitura, o
    #: FEN sai com ele e o desenho ganha o indicador; quando não dizem,
    #: `lado_origem` fica `convencao` e quem escreve o arquivo tem de carimbar
    #: isso no `alt` e na legenda, que é onde o leitor de tela e a busca vêem.
    lado_a_jogar: Optional[str] = None
    #: `"legenda"` ou `"convencao"`. Ver `lado_a_jogar`.
    lado_origem: str = "convencao"


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
    #: Quantas palavras o dicionário reescreveu nesta página (F115).
    #:
    #: **Existe porque a F66 recusou este reparo chamando-o de "reescrever o
    #: texto em silêncio".** O silêncio era metade da objeção, e é a metade que
    #: um número no relatório resolve: quem exporta vê quantas palavras trocaram
    #: e pode conferi-las. A outra metade — a precisão — foi a F69 que resolveu.
    reparos: int = 0
    #: Quantas palavras coladas foram partidas nesta página (F115). Preenchido
    #: pela passada `partir_coladas`, que é quem decide.
    cortes: int = 0
    #: A altura da imagem lida, em pixels. É a régua de `retirar_cabecalhos`:
    #: "na margem de cima" é uma fração disto, e não um número de pixels.
    altura: int = 0
    #: A largura da imagem lida, em pixels, e a resolução em que ela foi
    #: rasterizada. Com `altura`, é o que permite converter `Paragrafo.topo`/
    #: `pe` em coordenadas de página (pontos do PDF) fora daqui — a camada
    #: invisível do PDF pesquisável escala por `largura da página / largura`.
    largura: int = 0
    dpi: int = 0
    #: O texto de cada cabeçalho ou rodapé de página que saiu desta página
    #: (F109). Preenchido pela passada `retirar_cabecalhos`, que é quem
    #: decide — e guardado como texto, e não como número, para o relatório do
    #: fim da exportação poder dizer **o que** foi retirado.
    cabecalhos: List[str] = field(default_factory=list)
    #: Uma entrada por linha lida, com o domínio, o leitor principal que o
    #: `OCRRouter` escolheu, quem escreveu o texto e as duas leituras — a
    #: âncora da cadeia própria e a linha do motor contextual. É o registro
    #: que a OCR-11 pede ("registrar decisão de roteamento e motivo"), e é o
    #: que `scripts/ab_ocr_livro.py` lê para medir prosa e notação em separado.
    roteamento: List[dict] = field(default_factory=list)
    #: O motivo, quando o motor contextual (`ler_pagina`/`ler_faixa`) **falhou**
    #: nesta página — o Tesseract ausente, o pacote de idioma que não está
    #: instalado. A página sai só com a cadeia própria, como sempre saiu; o que
    #: muda é que isso deixa de ser invisível: até aqui a falha devolvia `[]`,
    #: e uma página sem Tesseract era bit a bit igual a uma página em branco.
    #: O relatório do fim da exportação conta quantas páginas ficaram assim.
    motor_indisponivel: str = ""

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
    # A mesma máscara limpa precisa alimentar as duas passadas. Sem isso a
    # primeira passava pelo limite de componentes, mas a geração real de texto
    # refazia a binarização original e voltava a analisar centenas de milhares
    # de partículas da trama.
    binaria_inicial = BoxService.binaria_para_segmentacao(
        img, max_contornos=BoxService.MAX_CONTORNOS_DE_TEXTO)
    antes, th, escala, _cinza = BoxService.boxes_antes_do_descarte(
        pil, max_contornos=BoxService.MAX_CONTORNOS_DE_TEXTO,
        binaria_inicial=binaria_inicial)
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
    todas = BoxService.generate_boxes_opencv(
        pil, arbitro=classificar, binaria=binaria_inicial)

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

    # **O rótulo que a margem não alcançou** (F109 §3). A exclusão pede a caixa
    # inteira dentro de 1,4 alturas de caractere, e a letra `a`–`h` impressa
    # a 1,2 alturas da borda tem o pé fora dela. Ela chegava ao texto como uma
    # linha de oito caracteres — `a b c d e f g h`, 146 parágrafos no Yusupov
    # exportado — e o `h` que sobrava colava na legenda da figura seguinte. Só
    # nos lados em que `ler_rotulos` achou rótulo, e pela régua dele.
    for d in diagramas:
        usadas = {id(b) for b in diagrama.caixas_dos_rotulos(
            d.tabuleiro, escala, d.rotulos, grandes)}
        if usadas:
            grandes = [b for b in grandes if id(b) not in usadas]

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


GLIFOS_DE_XADREZ = frozenset("♔♕♖♗♘♙♚♛♜♝♞♟")
_VOCABULARIO_OCR = {}
_ERROS_OCR_FREQUENTES = {
    # Confusões recorrentes desta fonte no Tesseract latino. São formas
    # improváveis em prosa inglesa e, ao contrário de um corretor genérico,
    # não alteram nomes próprios nem palavras já legítimas.
    "che": "the",
    "buc": "but",
    "wuld": "would",
    "poinc": "point",
    "beauciful": "beautiful",
    "alchough": "although",
    "acurate": "accurate",
    "afrer": "after",
    "ambitius": "ambitious",
    "payers": "players",
    "havc": "have",
    "afcr": "after",
    "chis": "this",
    "ic": "it",
    "rhe": "the",
    "arc": "are",
    "macerial": "material",
    "attempc": "attempt",
    "bese": "best",
    "whice": "white",
    "whie": "white",
    "whitc": "white",
    "chen": "then",
    "pointe": "point",
    "befence": "defence",
    "defcnce": "defence",
    "activatcs": "activates",
    "consolation": "consolation",
    "haper": "chapter",
}


# ----------------------------------------------------------------------
# Roteamento por domínio, palavra a palavra (OCR-11 e OCR-12 em produção)
# ----------------------------------------------------------------------
#
# A F114 mediu os dois leitores nas faixas destes livros: a cadeia própria
# acerta 97,6% dos boxes, e o melhor motor de linha, 88,4% — e a diferença é a
# figurina, que o modelo latino do Tesseract não tem e **omite**. Na prosa a
# conta inverte: `1n.ssed b.s cbance` contra `missed his chance`. Só que a
# linha destes livros é mista — `25.♖xc7! Amazingly Gashimov missed his
# chance` —, então a escolha não é por linha: é por palavra. O lance fica com
# a cadeia própria, que é a autoridade geométrica (um item por box); a palavra
# de prosa fica com o motor de linha, que tem contexto. Quem decide o que é
# lance é a forma do token da âncora — `notacao.e_token_de_notacao` —, e a
# decisão de cada linha fica registrada em `PaginaExtraida.roteamento`, que é
# o que `scripts/ab_ocr_livro.py` lê.

_e_token_de_notacao = notacao.e_token_de_notacao

#: O domínio de uma linha, pelo que a âncora tem dentro. Cada um vira um tipo
#: de região do `OCRRouter`, que é quem diz qual leitor é o principal: a linha
#: só de lances nem paga o motor contextual, e a de prosa (ou mista) o paga e
#: funde palavra a palavra.
TIPO_DE_REGIAO_POR_DOMINIO = {"notation": "notation", "prose": "body",
                              "mixed": "body", "unknown": "unknown"}


def _dominio_da_linha(texto: str) -> str:
    """`notation`, `prose`, `mixed` ou `unknown`, contando os tokens."""
    lances = palavras = 0
    for token in str(texto or "").split():
        if _e_token_de_notacao(token):
            lances += 1
        elif sum(c.isalpha() for c in token) >= 2:
            palavras += 1
    if lances and not palavras:
        return "notation"
    if palavras and not lances:
        return "prose"
    if lances and palavras:
        return "mixed"
    return "unknown"


#: Um número de lance partido do lance por um espaço falso: `1 .♘f6!`,
#: `1 ...♕xe2`, `1 1.♕g7`. O `1` em negrito do Chess Evolution 1 tem a tinta
#: estreita e o avanço largo, e o vão até o ponto (8–12 px) passa da régua
#: do espaço (6–8 px) — geometricamente é espaço; lexicalmente, um inteiro
#: solto seguido de ponto e lance (ou de dígitos, ponto e lance) só pode ser
#: número de lance. O ponto tem de ter algo depois: `2012 .` partido em
#: `201 2 .` com um respingo lido como ponto não é `2.`.
#:
#: O `l` e o `I` entram como dígito: a cadeia lê o `1` do Chess Evolution 1
#: como `l` (`l ...♘g4!`, `1 l .♘xf4+`), e um `l` solto na frente de
#: reticências e lance não é letra. Sai como `1`.
RE_NUMERO_PARTIDO = re.compile(r"(?<![^\s(])([0-9lI]{1,2}) (?=(?:[0-9lI]{1,2})?\.{1,3}[^.\s])")

#: O parêntese partido do número de lance por um espaço falso: `( 1...♔h6`,
#: `( 1 ♖e1!)`. Nas células da tabela do Nunn a régua do espaço é a de poucos
#: boxes, e o `(` sai solto cinco vezes na página; um `(` sozinho na frente de
#: um número de lance só pode ser o parêntese da variante.
RE_PARENTESE_PARTIDO = re.compile(r"(?<!\S)\( (?=[0-9lI]{1,3}[. ])")

#: A reticência do lance das pretas partida por um espaço: `1. ..♖d2`,
#: `1.. .♖h2`. Três pontos com um espaço no meio, logo depois de um dígito,
#: não são dois sinais de pontuação.
RE_RETICENCIA_PARTIDA = re.compile(r"(?<=[0-9lI ])(?:\. (?=\.\.)|\.\. (?=\.))")

#: O `!`/`?` partido do lance por um espaço: `♖e8 !`, `♖e1 !)`. O sinal de
#: anotação é do lance que o precede; solto, depois de casa, xeque ou
#: figurina, ele nunca é outra coisa.
RE_SINAL_PARTIDO = re.compile(r"(?<=[a-h1-8+#♔♕♖♗♘♙♚♛♜♝♞♟]) (?=[!?]{1,2}(?:[)\s]|$))")

#: O `l` (ou `I`) que é o `1` do lance das pretas: `(l...♖a2!)`, `l...e5`.
#: Sem letra antes e com a reticência **e um lance** depois — a figurina, ou
#: peça e casa —, não há leitura em que seja letra. O `I...` de um diálogo
#: em prosa não tem lance depois da reticência.
RE_L_QUE_E_UM = re.compile(
    r"(?<![A-Za-z])[lI](?=\.{3}(?:[♔♕♖♗♘♙♚♛♜♝♞♟]|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8]))")


def _colar_numero_de_lance(texto: str, pesos: List[Optional[float]],
                           lacunas: List[Optional[float]], caixas: List[int]):
    """Tira o espaço falso entre o número de lance e o lance, nos quatro
    vetores ao mesmo tempo — o espaço é um item deles, com box `-1`. Roda
    até estabilizar, porque `1 l .♘xf4+` cola em dois passos."""
    saida, pesos, lacunas, caixas = list(texto), list(pesos), list(lacunas), list(caixas)

    def tirar_espaco(posicao: int) -> None:
        if posicao < len(saida) and saida[posicao] == " ":
            del saida[posicao]
            for vetor in (pesos, lacunas, caixas):
                if posicao < len(vetor):
                    del vetor[posicao]

    # As colagens que sobravam nas células do Nunn, **antes** do número: o
    # parêntese solto na frente dele (`( 1...`), a reticência com espaço no
    # meio (`1 . ..♖d2`) e o sinal partido do lance (`♖e8 !`). Cada uma tira
    # um espaço, e os quatro vetores acompanham; o `l` que é `1` vem no fim.
    for regra in (RE_PARENTESE_PARTIDO, RE_RETICENCIA_PARTIDA, RE_SINAL_PARTIDO):
        atual = "".join(saida)
        for m in reversed(list(regra.finditer(atual))):
            tirar_espaco(m.end() - 1)

    for _passo in range(3):
        atual = "".join(saida)
        achados = [m for m in RE_NUMERO_PARTIDO.finditer(atual)
                   if len(m.group(1)) + len(re.match(r"[0-9lI]*", atual[m.end():]).group(0)) <= 3]
        if not achados:
            break
        for m in reversed(achados):
            posicao = m.end(1)
            if saida[posicao] != " ":
                continue
            tirar_espaco(posicao)
            for k in range(m.start(1), m.end(1)):
                if saida[k] in "lI":
                    saida[k] = "1"
    atual = "".join(saida)
    for m in RE_L_QUE_E_UM.finditer(atual):
        saida[m.start()] = "1"
    return "".join(saida), pesos, lacunas, caixas


#: O que separa a prosa colada ao lance, na frente do lance: o parêntese da
#: variante, o número de lance ou a figurina. `W:W1n(1♖d1!)` parte no `(`;
#: `Draw(1...♖h2!)` idem. É onde o token deixa de ser palavra e passa a ser
#: lance — e o pedaço da frente precisa ser palavra (duas letras, sem
#: figurina), senão não é prosa colada: `T♕` e `W♔d1` ficam inteiros.
RE_COMECO_DE_LANCE = re.compile(
    r"\((?=[0-9lI♔♕♖♗♘♙♚♛♜♝♞♟])|(?<![0-9])[0-9]{1,3}\.{1,3}(?=\S)|[♔♕♖♗♘♙♚♛♜♝♞♟]")

#: O lance que fica depois do corte, com o parêntese e o número opcionais: é
#: o que autoriza partir. `(1♖d1!)`, `(1...♖h2!)`, `♖e8!`, `1 ♖e1!)`.
RE_LANCE_DEPOIS_DO_CORTE = re.compile(
    r"^\(?(?:[0-9lI]{1,3}\.{0,3} ?)?"
    r"(?:[♔♕♖♗♘♙♚♛♜♝♞♟KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x?[a-h][1-8]|[a-h][1-8])")


def _partir_prosa_colada_ao_lance(texto: str, pesos: List[Optional[float]],
                                  lacunas: List[Optional[float]],
                                  caixas: List[int]):
    """Abre um espaço entre a prosa e o lance que a cadeia colou num token só.

    `W:W1n(1♖d1!)` e `Draw(1...♖h2!)` são um token para a cadeia porque a
    régua do espaço da célula é a de poucos boxes; e para a fusão o token com
    figurina é lance inteiro — ficava com a âncora, com o motor lendo `W:`
    `Win` `(1` a 0,9 no mesmo lugar. Partido em `W:W1n` + `(1♖d1!)`, a prosa
    vai para o motor e o lance fica, que é a regra de sempre.

    Só parte o token que **não** tem forma de lance inteiro, num ponto onde o
    que vem depois tem (`RE_LANCE_DEPOIS_DO_CORTE`) e o que vem antes é
    palavra: duas letras no mínimo, sem figurina. O espaço entra nos quatro
    vetores como os outros — `None` na medida, `-1` no box.
    """
    saida, pesos, lacunas, caixas = list(texto), list(pesos), list(lacunas), list(caixas)
    atual = "".join(saida)
    cortes = []
    for m in re.finditer(r"\S+", atual):
        token = m.group(0)
        if not any(c in GLIFOS_DE_XADREZ for c in token):
            continue
        nucleo = token.strip(notacao._PONTUACAO_DE_BORDA)
        if notacao.RE_LANCE_ESTRITO.match(nucleo):
            continue
        for inicio in RE_COMECO_DE_LANCE.finditer(token):
            k = inicio.start()
            cabeca, cauda = token[:k], token[k:]
            if (k == 0 or sum(c.isalpha() for c in cabeca) < 2
                    or any(c in GLIFOS_DE_XADREZ for c in cabeca)):
                continue
            if RE_LANCE_DEPOIS_DO_CORTE.match(cauda):
                cortes.append(m.start() + k)
                break
    for posicao in reversed(cortes):
        saida.insert(posicao, " ")
        pesos.insert(posicao, None)
        lacunas.insert(posicao, None)
        caixas.insert(posicao, -1)
    return "".join(saida), pesos, lacunas, caixas


def _semelhanca_de_linha(ancora: str, linha: str) -> float:
    """Quanto as duas leituras concordam, olhando só letras e dígitos.

    A figurina fica de fora porque o motor de linha não a tem; o espaço, porque
    a cadeia própria e o Tesseract o abrem em lugares diferentes. O que sobra é
    o que os dois leem, e é o suficiente para separar a mesma linha lida duas
    vezes (0,7–0,9) da linha errada (abaixo de 0,4).
    """
    def nucleo(texto: str) -> str:
        return "".join(c for c in str(texto or "").casefold() if c.isalnum())
    a, b = nucleo(ancora), nucleo(linha)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


#: Abaixo desta semelhança o registro do motor não é esta linha: é a vizinha,
#: ou o lixo da segunda passada sobre a trama, e a âncora fica como está.
SEMELHANCA_MINIMA_DA_LINHA = 0.5
#: Abaixo deste piso a linha inteira do motor não tem evidência suficiente
#: para sobrescrever a leitura que conserva os glifos (modo `linha`). É baixo
#: o bastante para aceitar linhas mistas, e recusa as dominadas por diagrama.
CONFIANCA_MINIMA_DA_LINHA = 0.45
#: O piso da palavra, no modo `palavra`. Medido na página 30 do Aagaard: a
#: palavra de prosa do Tesseract fica em 0,95 de mediana, e o lance que ele
#: lê sem a figurina (`27.Eg7t`, `Hh8`) fica em 0,0–0,4 — e é ele que puxa a
#: média da linha para baixo de `CONFIANCA_MINIMA_DA_LINHA` e escondia o
#: `is just mate` que estava certo no meio dos lances.
CONFIANCA_MINIMA_DA_PALAVRA = 0.5
#: Fração da palavra mais estreita que precisa coincidir, em x, para a
#: palavra do motor e o token da âncora serem a mesma coisa impressa.
SOBREPOSICAO_MINIMA_DE_PALAVRA = 0.5


def _sobreposicao(a1: float, a2: float, b1: float, b2: float) -> float:
    comum = min(a2, b2) - max(a1, b1)
    if comum <= 0:
        return 0.0
    return comum / max(1.0, min(a2 - a1, b2 - b1))


#: A palavra do motor que vale como leitura da faixa sobre trama. Medido no
#: painel do Chess Evolution 1 (p. 47), com a faixa limpa: a palavra impressa
#: sai a 0,94–0,96 (`Two`, `methods`, `How`, `force`) e o lixo da trama a
#: 0,00–0,39 (`ER`, `oe`, `SEE EE ER I ST`, `‘AURIS`). O `¥` da marca de
#: verificação fica no meio (0,62–0,75), e não tem letra.
CONFIANCA_DA_PALAVRA_NA_TRAMA = 0.8


def _motor_le_a_trama(detalhes) -> bool:
    """As palavras do motor a `CONFIANCA_DA_PALAVRA_NA_TRAMA` carregam a faixa?

    Metade das letras, ao menos, e duas no mínimo: `¥ Two methods Bee` tem
    10 letras confiantes em 13, e `SEE EE ER I ST` nenhuma.
    """
    confiantes = total = 0
    for detalhe in detalhes or ():
        if len(detalhe) < 2:
            continue
        letras = sum(c.isalpha() for c in str(detalhe[0] or ""))
        total += letras
        if float(detalhe[1] or 0.0) >= CONFIANCA_DA_PALAVRA_NA_TRAMA:
            confiantes += letras
    return confiantes >= 2 and confiantes * 2 >= total


def _compatibilidade_da_linha(ancora: str, texto_ocr: str, confianca_ocr: float,
                              detalhes, fusao: str, *,
                              trama: bool = False) -> Tuple[float, bool]:
    """`(semelhança, aceita?)` de um registro do motor para esta âncora.

    A fusão por palavra tem o piso de cada palavra e só pede a semelhança; a
    troca da linha inteira precisa do piso da linha, porque não tem outro.

    Com `trama`, o registro é o da faixa desta linha lida sobre meio-tom, e
    a semelhança deixa de decidir: a âncora sobre trama não é evidência de
    nada — a cadeia lê `T♕ eas` onde está impresso `Two methods` (0,35 de
    semelhança), e `🗸 H f0ee an` para `How to force an` (0,48). O que decide
    é o motor lendo a faixa limpa com confiança (`_motor_le_a_trama`). Só
    vale para a faixa, e nunca para o registro da passada de página: aquele
    pode ser a linha vizinha, e é a semelhança que o pega.
    """
    semelhanca = _semelhanca_de_linha(ancora, texto_ocr)
    por_palavra = fusao == "palavra" and bool(detalhes)
    tem_letra = any(char.isalpha() for char in texto_ocr)
    aceita = (tem_letra
              and semelhanca >= SEMELHANCA_MINIMA_DA_LINHA
              and (por_palavra or confianca_ocr >= CONFIANCA_MINIMA_DA_LINHA))
    if not aceita and trama and por_palavra and tem_letra:
        aceita = _motor_le_a_trama(detalhes)
    return semelhanca, aceita


#: A faixa da linha, para o motor, cresce até isto em larguras medianas de
#: box para cada lado, além dos boxes: onde a cadeia perdeu o fim da linha
#: — `Combining both meth`, os três boxes de `ods` derrubados na trama —, o
#: motor ainda vê o que está impresso. Três é o que uma sílaba mede; a coluna
#: vizinha fica a mais que isso.
FOLGA_DA_FAIXA_EM_LARGURAS = 3.0
#: A faixa está sobre trama quando os pontos — o componente com menos de
#: `BoxService.TRAMA_ALTURA_PX` nos dois eixos, o mesmo ponto que a página
#: tira da binária — são mais que isto vezes os outros componentes. Na faixa
#: do painel do Chess Evolution 1 são dezenas por letra (545 pontos para 15
#: letras). **Era relativo à altura mediana dos boxes** (um quarto dela), e
#: a linha feita de filetes da tabela do Nunn (p. 237) o desmentiu: o box
#: mediano é o filete de 177 px, um quarto é 44, e as letras da fila (30 px)
#: passavam por ponto — 97 de 102 —, e a fila inteira por trama. O ponto tem
#: tamanho físico, e é o da página: nas faixas do painel as duas réguas
#: contam quase o mesmo (545 e 557; 1.225 e 1.239).
TRAMA_NA_FAIXA = 3.0


def _binaria_da_trama(miolo: np.ndarray):
    """`(binária, sobre trama?)` do miolo de uma faixa — Otsu, e a conta dos
    pontos contra os outros componentes (`TRAMA_NA_FAIXA`)."""
    import cv2

    if miolo.size == 0:
        return None, False
    _, binaria = cv2.threshold(miolo, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    total, _rotulos, medidas, _c = cv2.connectedComponentsWithStats(binaria, connectivity=8)
    if total <= 1:
        return binaria, False
    lado = BoxService.TRAMA_ALTURA_PX
    pontos = int(((medidas[1:, cv2.CC_STAT_HEIGHT] < lado)
                  & (medidas[1:, cv2.CC_STAT_WIDTH] < lado)).sum())
    outros = total - 1 - pontos
    return binaria, pontos >= TRAMA_NA_FAIXA * max(1, outros)


def _linha_sobre_trama(img: np.ndarray, linha: Sequence[BoxEntry]) -> bool:
    """A linha está impressa sobre meio-tom? A mesma conta da faixa que vai
    para o motor, na faixa dos boxes — é o que a fusão pergunta quando o
    registro veio da passada de página, e não da faixa."""
    if not linha:
        return False
    topo = max(0, min(b.y1 for b in linha))
    base = min(img.shape[0], max(b.y2 for b in linha))
    x1 = max(0, min(b.x1 for b in linha))
    x2 = min(img.shape[1], max(b.x2 for b in linha))
    if base <= topo or x2 <= x1:
        return False
    _binaria, trama = _binaria_da_trama(img[topo:base, x1:x2])
    return trama


def _limpar_faixa_de_trama(faixa: np.ndarray, linha: Sequence[BoxEntry]
                           ) -> Tuple[np.ndarray, bool]:
    """Otsu e abertura 2×2 no miolo da faixa, se ela está sobre trama; e se
    está — a fusão trata a linha sobre trama de outro jeito.

    O painel de conteúdo do capítulo (Chess Evolution 1, p. 47) é texto sobre
    meio-tom, e o Tesseract lê a faixa cinza como `v Combisnag bod: medi` a
    0,14. Binarizada e sem o ponto isolado, `¥ Combining both meth` a 0,83.
    A faixa limpa continua sendo texto para o motor; a que não tem trama
    fica como está, porque a abertura come a serifa fina.
    """
    import cv2

    m = MARGEM_DA_FAIXA
    binaria, trama = _binaria_da_trama(faixa[m:-m, m:-m])
    if not trama:
        return faixa, False
    tinta = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    limpa = faixa.copy()
    limpa[m:-m, m:-m] = 255 - tinta
    return limpa, True


#: Depois de quantas falhas seguidas do motor de faixa a página para de pedi-lo.
#: A indisponibilidade (executável, idioma) desliga na primeira, sem contar:
#: a segunda chamada falharia igual, e são uma por linha. A falha comum — um
#: recorte que o motor não engoliu — precisa se repetir: isolada, não desliga
#: nada, e três seguidas são um defeito que vai se repetir na linha seguinte.
FALHAS_DE_FAIXA_ATE_DESISTIR = 3


def _ler_faixa_registrando(ler_faixa: Callable, falhas: List[str]) -> Callable:
    """Embrulha `ler_faixa` para que a falha dele **fique registrada** em
    `falhas` em vez de sumir: o recorte que ele não leu devolve `[]` e a linha
    fica com a âncora, como antes — mas a página sabe que o motor faltou.
    A indisponibilidade (`MotorIndisponivel`) desliga o motor para o resto da
    página na primeira vez; a falha comum precisa se repetir
    `FALHAS_DE_FAIXA_ATE_DESISTIR` vezes seguidas."""
    from core.services.ocr_service import MotorIndisponivel

    estado = {"desligado": False, "seguidas": 0}

    def ler(faixa):
        if estado["desligado"]:
            return []
        try:
            registros = ler_faixa(faixa)
        except MotorIndisponivel as erro:
            estado["desligado"] = True
            falhas.append(f"faixa: {erro.motivo}")
            return []
        except Exception as erro:  # noqa: BLE001 — registrada, e a linha segue
            estado["seguidas"] += 1
            if estado["seguidas"] >= FALHAS_DE_FAIXA_ATE_DESISTIR:
                estado["desligado"] = True
            falhas.append(f"faixa: {type(erro).__name__}: {erro}")
            return []
        estado["seguidas"] = 0
        return registros
    return ler


def _registro_da_faixa(img: np.ndarray, linha: Sequence[BoxEntry],
                       ler_faixa: Callable):
    """Lê a faixa de uma linha só e devolve o registro em coordenadas da página.

    `ler_faixa(faixa)` devolve o mesmo formato de `ler_pagina`, mas com as
    caixas relativas à faixa: o deslocamento é o canto da faixa na página. A
    faixa é a de `faixa_da_linha` — os boxes com `MARGEM` em volta —, alargada
    por `FOLGA_DA_FAIXA_EM_LARGURAS` para os dois lados. Se o motor devolver
    mais de uma linha para a faixa, fica a mais larga.

    Devolve `(texto, confiança, palavras, sobre trama?)`: o quarto é se a
    faixa foi limpa de meio-tom antes de ir ao motor (`_limpar_faixa_de_trama`),
    que é o que autoriza a fusão a confiar no motor contra a âncora.
    """
    if not linha:
        return None
    negativa = any(getattr(b, "negativo", False) for b in linha)
    larguras = sorted(b.x2 - b.x1 for b in linha)
    # A tarja em negativo não ganha folga: os boxes da cadeia já a delimitam,
    # e a folga traria a sombra da borda dela, que invertida vira `| |`.
    folga = (0 if negativa
             else int(larguras[len(larguras) // 2] * FOLGA_DA_FAIXA_EM_LARGURAS))
    topo = max(0, min(b.y1 for b in linha))
    base = min(img.shape[0], max(b.y2 for b in linha))
    x1 = max(0, min(b.x1 for b in linha) - folga)
    x2 = min(img.shape[1], max(b.x2 for b in linha) + folga)
    if base <= topo or x2 <= x1:
        return None
    m = MARGEM_DA_FAIXA
    faixa = np.pad(img[topo:base, x1:x2], ((m, m), (m, m)), mode="constant",
                   constant_values=255)
    if negativa:
        # O cabeçalho em negativo — branco sobre preto — o motor lê mal como
        # está (`].Bolbochan` a 0,4, `W.Steinit`); invertido, é texto comum.
        # A cadeia própria já inverte o box; aqui se inverte o miolo da faixa,
        # e só ele: a margem em volta é branca, e invertida viraria uma
        # moldura preta em volta do texto.
        miolo = faixa[m:-m, m:-m]
        miolo[...] = 255 - miolo
        trama = False
    else:
        faixa, trama = _limpar_faixa_de_trama(faixa, linha)
    # A falha do motor não é tratada aqui: `extrair_pagina` embrulha o
    # `ler_faixa` em `_ler_faixa_registrando`, que a anota na página e devolve
    # `[]` — a linha fica com a âncora, e a página sabe por quê.
    registros = list(ler_faixa(faixa) or [])
    registros = [r for r in registros if len(r) >= 3 and str(r[0] or "").strip()]
    if not registros:
        return None
    registro = max(registros, key=lambda r: r[2][2] - r[2][0])
    dx = x1 - m
    dy = topo - m
    detalhes = tuple(
        (palavra, conf, (caixa[0] + dx, caixa[1] + dy, caixa[2] + dx, caixa[3] + dy))
        for palavra, conf, caixa in (d[:3] for d in (registro[3] if len(registro) > 3 else ()))
        if len(caixa) >= 4)
    return str(registro[0]).strip(), float(registro[1] or 0.0), detalhes, trama


#: O que pode entrar num lance vindo do motor de linha: letra de casa ou de
#: peça em SAN, dígito, captura, promoção, xeque, mate, anotação e avaliação.
#: Figurina não — o motor não a tem —, e letra fora disto é lixo dele.
_ALFABETO_DO_LANCE = frozenset("abcdefgh12345678xKQRBNO+#!?=-–—.")
#: O traço que o motor escreve vira o da cadeia — o `–` de `+–`, que é o que o
#: livro imprime; o Tesseract devolve `—` ou `-` conforme o humor.
_TRACOS_DO_MOTOR = {"—": "–", "-": "–"}


def _alinhar_lance(ancora: Sequence[str], palavra: str) -> Optional[List[str]]:
    """Alinha os itens da âncora de um lance à palavra do motor, e devolve o
    que o motor leu em cada lacuna.

    `ancora` é a lista de itens do token: um caractere por item, `"\\0"` na
    lacuna (o box que a cadeia derrubou) e a figurina como está. A figurina e
    a lacuna são curingas de um ou dois caracteres do motor — o Tesseract
    escreve a figurina como uma ou duas letras (`Wf` para ♕) e a lacuna pode
    ser uma ligadura (`ex`). Programação dinâmica: troca, inserção e remoção
    custam 2; a figurina casa de graça; a lacuna que recebe algo custa 1 e a
    vazia (o motor também não viu) custa 2 — assim, no empate, a letra do
    motor vai para a figurina, e não para a lacuna ao lado dela. Devolve
    `None` quando a palavra não é esta — mais de um quinto de edições fora
    das lacunas.
    """
    n, m = len(ancora), len(palavra)
    INF = 10 ** 6
    custo = [[INF] * (m + 1) for _ in range(n + 1)]
    origem: List[List[Optional[Tuple[int, int]]]] = [[None] * (m + 1) for _ in range(n + 1)]
    custo[0][0] = 0
    for j in range(1, m + 1):
        custo[0][j] = 2 * j
        origem[0][j] = (0, j - 1)
    for i in range(1, n + 1):
        item = ancora[i - 1]
        lacuna = item == "\0"
        curinga = lacuna or item in GLIFOS_DE_XADREZ
        consumo = 1 if lacuna else 0
        for j in range(0, m + 1):
            melhor, de = custo[i - 1][j] + 2, (i - 1, j)          # remoção
            if j and custo[i][j - 1] + 2 < melhor:                # inserção
                melhor, de = custo[i][j - 1] + 2, (i, j - 1)
            if j:
                troca = consumo if curinga else (0 if palavra[j - 1] == item else 2)
                if custo[i - 1][j - 1] + troca < melhor:
                    melhor, de = custo[i - 1][j - 1] + troca, (i - 1, j - 1)
            if curinga and j >= 2 and custo[i - 1][j - 2] + consumo < melhor:
                melhor, de = custo[i - 1][j - 2] + consumo, (i - 1, j - 2)
            custo[i][j] = melhor
            origem[i][j] = de
    edicoes_fora = 0
    lidas: List[str] = []
    i, j = n, m
    while i or j:
        pi, pj = origem[i][j]
        if pi == i - 1 and i:
            item = ancora[i - 1]
            trecho = palavra[pj:j]
            if item == "\0":
                lidas.append(trecho)
            elif item not in GLIFOS_DE_XADREZ and trecho != item:
                edicoes_fora += 1
        elif pi == i:
            edicoes_fora += 1
        i, j = pi, pj
    lidas.reverse()
    if edicoes_fora > max(1, len(ancora) // 5):
        return None
    return lidas


def _preencher_lacunas_do_lance(token: str, indices: Sequence[int],
                                linha: Sequence[BoxEntry], caixas_usadas: set,
                                palavra: str) -> Optional[str]:
    """O lance com os boxes derrubados preenchidos pelo motor de linha.

    A cadeia derruba o caractere abaixo de `CONF_MINIMA`, e no lance isso é
    sistemático em dois lugares medidos: o `–` de `+–` (0,40–0,44 no Chess
    Evolution 1) e a ligadura `ex` de `exf4` (0,43). O box derrubado é a
    evidência de que há um glifo ali; o que ele é, o motor de linha diz
    melhor que a cadeia hesitando — e só entra o que cabe no alfabeto do
    lance, e só se o lance inteiro continuar com forma de lance.
    """
    if not palavra or not indices:
        return None
    primeiro, ultimo = min(indices), max(indices)
    larguras = sorted(b.x2 - b.x1 for b in linha) or [1]
    encostado = larguras[len(larguras) // 2] * 0.6
    derrubados = [j for j in range(primeiro, ultimo + 1) if j not in caixas_usadas]
    # A lacuna encostada ao token, de um lado ou do outro, também é dele:
    # o `–` de `+–` vem depois do último caractere lido.
    for j in (primeiro - 1, ultimo + 1):
        if (0 <= j < len(linha) and j not in caixas_usadas
                and (linha[j].x1 - linha[j - 1].x2 if j > primeiro
                     else linha[j + 1].x1 - linha[j].x2) < encostado):
            derrubados.append(j)
    if not derrubados:
        return None
    itens: List[str] = []
    por_box = {}
    for posicao, indice in enumerate(indices):
        por_box.setdefault(indice, []).append(token[posicao])
    ordem = sorted(set(indices) | set(derrubados))
    for j in ordem:
        itens.extend(por_box.get(j, ["\0"]))
    lidas = _alinhar_lance(itens, palavra)
    if lidas is None or not any(lidas):
        return None
    if any(c not in _ALFABETO_DO_LANCE for lida in lidas for c in lida):
        return None
    saida: List[str] = []
    k = 0
    for item in itens:
        if item == "\0":
            saida.append("".join(_TRACOS_DO_MOTOR.get(c, c) for c in lidas[k]))
            k += 1
        else:
            saida.append(item)
    novo = "".join(saida)
    return novo if novo != token and _e_token_de_notacao(novo) else None


def _lance_sem_casa(token: str) -> bool:
    """O token que é lance só pela figurina: sem casa e sem número de lance.

    `T♕`, `ex♕fange`, `♕` — a figurina que a cadeia vê num ponto de trama.
    O lance de verdade tem casa (`♘e4`), ou é o número dele (`2.♘` com a
    casa derrubada, que `_preencher_lacunas_do_lance` completa).
    """
    return (any(c in GLIFOS_DE_XADREZ for c in token)
            and notacao.RE_CASA.search(token) is None
            and not token[:1].isdigit())


#: Onde o espaço do motor **não** entra num lance: entre a peça e a casa
#: (`♖d1`), entre a letra e o dígito da casa (`d1`), depois da captura
#: (`xd1`) e da promoção (`=♕`). O motor separa `(1` de `&d1!)` porque o
#: livro imprime `1 ♖d1!` com espaço; o que ele nunca separa, se separar, é
#: leitura errada dele, e o lance da âncora vale mais.
_NAO_PARTE_DEPOIS_DE = frozenset("KQRBNx=-–—" + "".join(sorted(GLIFOS_DE_XADREZ)))
#: E onde ele não entra pela pontuação: antes do ponto do número de lance, do
#: `!`/`?`, do xeque, do parêntese que fecha, da vírgula — e em volta do
#: traço, que é o do roque (`O-O`) e o do resultado (`1–0`, `½–½`): o motor
#: perde o traço fino com frequência e devolve duas palavras.
_PONTUACAO_QUE_COLA = frozenset(".!?)+#,;:…-–—")


def _espacos_do_motor(texto_token: str, caixas_do_token: Sequence[int],
                      linha: Sequence[BoxEntry],
                      palavras: Sequence[Tuple[float, float]]) -> str:
    """Repõe no lance o espaço que o motor viu e a cadeia não.

    O lance é da âncora, mas a régua do espaço da cadeia é a mediana da
    linha — numa célula de três boxes ela não diz nada, e `(1 ♖d1!)` sai
    `(1♖d1!)`. O motor tem as caixas das palavras dele: onde duas palavras
    do motor cobrem o mesmo token da âncora e o vão entre elas cai num vão
    entre dois boxes da âncora, ali havia espaço impresso. É evidência
    geométrica dos dois lados, e só ela: o token continua o da cadeia,
    caractere por caractere.
    """
    if " " in texto_token or len(caixas_do_token) != len(texto_token):
        return texto_token
    indices = [c for c in caixas_do_token if 0 <= c < len(linha)]
    if len(indices) < 2:
        return texto_token
    x1 = min(linha[i].x1 for i in indices)
    x2 = max(linha[i].x2 for i in indices)
    cobrem = sorted((px1, px2) for px1, px2 in palavras
                    if _sobreposicao(x1, x2, px1, px2) > 0
                    and min(x2, px2) - max(x1, px1) > 0)
    if len(cobrem) < 2:
        return texto_token
    vaos_do_motor = [(a[1], b[0]) for a, b in zip(cobrem, cobrem[1:])
                     if b[0] > a[1]]
    if not vaos_do_motor:
        return texto_token
    cortes = []
    for k in range(1, len(texto_token)):
        antes, depois = caixas_do_token[k - 1], caixas_do_token[k]
        if not (0 <= antes < len(linha) and 0 <= depois < len(linha)):
            continue
        if antes == depois:
            continue
        vao = (linha[antes].x2, linha[depois].x1)
        if vao[1] <= vao[0]:
            continue
        centro = (vao[0] + vao[1]) / 2.0
        if not any(inicio <= centro <= fim for inicio, fim in vaos_do_motor):
            continue
        anterior, atual = texto_token[k - 1], texto_token[k]
        if anterior in _NAO_PARTE_DEPOIS_DE or anterior in "(.,":
            continue
        # Espaço nunca vem antes de pontuação (`21 .♗xc6` não existe; o motor
        # leu `21 b` e o vão caiu antes do ponto), nem parte um número.
        if atual in _PONTUACAO_QUE_COLA or (anterior.isdigit() and atual.isdigit()):
            continue
        if anterior in "abcdefgh" and atual in "12345678":
            continue
        cortes.append(k)
    if not cortes:
        return texto_token
    partes = []
    ultimo = 0
    for k in cortes:
        partes.append(texto_token[ultimo:k])
        ultimo = k
    partes.append(texto_token[ultimo:])
    return " ".join(partes)


def _fundir_por_palavra(texto: str, caixas: Sequence[int],
                        linha: Sequence[BoxEntry], detalhes, *,
                        so_lacunas: bool = False,
                        trama: bool = False) -> Tuple[str, dict]:
    """Monta a linha token a token: lance da âncora, prosa do motor de linha.

    `texto` e `caixas` são os de `_texto_da_linha` — o caractere e o box de
    onde ele saiu —, e `detalhes` são as palavras do motor com as caixas delas,
    `(texto, confiança, (x1, y1, x2, y2))`. A caminhada é pela âncora, que é
    quem tem um item por box: cada token dela ou tem forma de lance e fica, ou
    é trocado pelas palavras do motor que ocupam o mesmo lugar em x. A palavra
    do motor que não coincide com token nenhum entra no lugar dela — é o
    caractere que a confiança derrubou, e que o motor ainda leu. Duas ficam
    de fora: a que está abaixo de `CONFIANCA_MINIMA_DA_PALAVRA`, que é o lance
    que o motor leu sem a figurina, e a que está fora da faixa vertical da
    linha, porque um registro do Tesseract às vezes traz duas linhas impressas
    dentro de uma.

    O lance fica com a âncora, mas **as lacunas dele são preenchidas pelo
    motor** (`_preencher_lacunas_do_lance`): o box derrubado pela confiança
    dentro do lance, ou encostado a ele, recebe o que o motor leu ali, se
    couber no alfabeto do lance. Para isso vale a palavra fraca do motor —
    o lance sem figurina sai dele a 0,3 —, que para a prosa fica de fora.
    Com `so_lacunas` é só isto que acontece: é o que a linha só de notação
    pede ao motor, e nada mais.

    Com `trama` a linha está sobre meio-tom, e **o lance sem casa vai para o
    motor como prosa** (`_lance_sem_casa`): a figurina ali é o que a cadeia
    fez de um ponto de trama — `T♕` para `Two`, `ex♕fange` para `exchange`
    —, e como lance ela ficava com a âncora e nunca passava pelo motor, que
    lê a faixa limpa a 0,7–0,96. O lance com casa continua sendo da âncora,
    trama ou não. Fora da trama nada muda: a figurina solta na prosa (`the
    ♘ is strong`) é da cadeia, que é a única que a escreve.

    Por fim, o token de lance ainda pode ganhar de volta **o espaço que só o
    motor viu** (`_espacos_do_motor`): a régua de espaço da cadeia é a
    mediana da linha, e numa célula de poucos boxes ela cola `(1 ♖d1!)` em
    `(1♖d1!)` — o motor tem as caixas das duas palavras e enxerga o vão que a
    régua não vê. Só onde o vão dele cai num vão entre boxes da âncora, e
    nunca antes de pontuação nem entre peça e casa.
    """
    y_topo = min(b.y1 for b in linha)
    y_base = max(b.y2 for b in linha)
    palavras = []
    todas = []
    fora_da_faixa = fracas = 0
    for detalhe in detalhes:
        if len(detalhe) < 3:
            continue
        palavra = str(detalhe[0] or "").strip()
        caixa = detalhe[2]
        if not palavra or len(caixa) < 4:
            continue
        x1, y1, x2, y2 = (float(v) for v in caixa[:4])
        if _sobreposicao(y_topo, y_base, y1, y2) < SOBREPOSICAO_MINIMA_DE_PALAVRA:
            fora_da_faixa += 1
            continue
        todas.append((x1, x2, palavra))
        if float(detalhe[1] or 0.0) < CONFIANCA_MINIMA_DA_PALAVRA:
            fracas += 1
            continue
        palavras.append((x1, x2, palavra))
    palavras.sort()
    todas.sort()
    if so_lacunas:
        palavras = []
    estatisticas = {"tokens_da_ancora": 0, "palavras_do_motor": 0,
                    "palavras_fora_da_faixa": fora_da_faixa,
                    "palavras_fracas": fracas, "lacunas_preenchidas": 0}
    if not todas:
        return texto, estatisticas

    caixas_usadas = {c for c in caixas if c >= 0}
    tokens = []
    for token in re.finditer(r"\S+", texto):
        ordem = [caixas[k] for k in range(token.start(), token.end())
                 if k < len(caixas) and 0 <= caixas[k] < len(linha)]
        if not ordem:
            continue
        x1 = min(linha[i].x1 for i in ordem)
        x2 = max(linha[i].x2 for i in ordem)
        sobrepostas = [j for j, (px1, px2, _p) in enumerate(palavras)
                       if _sobreposicao(x1, x2, px1, px2)
                       >= SOBREPOSICAO_MINIMA_DE_PALAVRA]
        texto_token = token.group(0)
        e_lance = _e_token_de_notacao(texto_token)
        if e_lance:
            vizinhas = "".join(p for px1, px2, p in todas
                               if _sobreposicao(x1, x2, px1, px2)
                               >= SOBREPOSICAO_MINIMA_DE_PALAVRA)
            preenchido = _preencher_lacunas_do_lance(
                texto_token, ordem, linha, caixas_usadas, vizinhas)
            if preenchido is not None:
                texto_token = preenchido
                estatisticas["lacunas_preenchidas"] += 1
            if not so_lacunas:
                espacado = _espacos_do_motor(
                    texto_token, [caixas[k] for k in range(token.start(), token.end())
                                  if k < len(caixas)],
                    linha, [(px1, px2) for px1, px2, _p in todas])
                if espacado != texto_token:
                    texto_token = espacado
                    estatisticas["espacos_do_motor"] = (
                        estatisticas.get("espacos_do_motor", 0) + 1)
            # Depois de preencher: o `♘xe` com o `4` derrubado ganha a casa
            # e continua lance. O que não ganhou, sobre trama, é prosa — e
            # só quando o motor leu alguma coisa ali; sem palavra do motor
            # a âncora é o que existe, de qualquer jeito.
            if trama and sobrepostas and _lance_sem_casa(texto_token):
                e_lance = False
                estatisticas["lances_sem_casa"] = (
                    estatisticas.get("lances_sem_casa", 0) + 1)
        tokens.append((x1, texto_token, sobrepostas, e_lance))

    itens = []
    consumida_por: dict = {}
    # A palavra do motor que toca um lance é do lance, antes de qualquer
    # prosa olhar para ela: o Tesseract às vezes cola os dois (`after:25.g4?`),
    # e usá-la na prosa escreveria o lance duas vezes.
    for _x1, _token, sobrepostas, e_lance in tokens:
        if e_lance:
            for j in sobrepostas:
                consumida_por.setdefault(j, "ancora")
    for x1, token, sobrepostas, e_lance in tokens:
        if e_lance:
            itens.append((x1, token))
            estatisticas["tokens_da_ancora"] += 1
            continue
        novas = [j for j in sobrepostas if j not in consumida_por]
        if novas:
            for j in novas:
                itens.append((palavras[j][0], palavras[j][2]))
                consumida_por[j] = "motor"
            estatisticas["palavras_do_motor"] += len(novas)
        elif not sobrepostas or all(consumida_por[j] == "ancora"
                                    for j in sobrepostas):
            # Sem palavra do motor neste lugar — ou a que havia foi para um
            # lance vizinho —, a âncora é o que existe.
            itens.append((x1, token))
            estatisticas["tokens_da_ancora"] += 1
        # Todas consumidas por um token de prosa anterior: é a segunda metade
        # de uma palavra que o motor leu inteira, e ela já saiu.
    for j, (px1, _px2, palavra) in enumerate(palavras):
        if j not in consumida_por:
            itens.append((px1, palavra))
            estatisticas["palavras_do_motor"] += 1
    itens.sort(key=lambda item: item[0])
    return " ".join(texto_item for _x, texto_item in itens), estatisticas


def _casar_linha_ocr(linha: Sequence[BoxEntry], registros, usados: set[int]):
    """Encontra a linha do OCR de página que cobre os mesmos boxes.

    O detector interno continua sendo a autoridade sobre a geometria. O OCR de
    contexto só fornece a palavra e, por isso, a associação exige interseção
    vertical e horizontal. Isso evita que uma linha da coluna vizinha seja
    aplicada silenciosamente, algo especialmente importante em livros de duas
    colunas.
    """
    if not linha:
        return None
    x1 = min(b.x1 for b in linha)
    y1 = min(b.y1 for b in linha)
    x2 = max(b.x2 for b in linha)
    y2 = max(b.y2 for b in linha)
    largura = max(1, x2 - x1)
    altura = max(1, y2 - y1)
    melhor = None
    melhor_pontuacao = -1.0
    for indice, registro in enumerate(registros):
        if indice in usados or len(registro) < 3:
            continue
        _texto, confianca, caixa = registro[:3]
        if len(caixa) < 4:
            continue
        rx1, ry1, rx2, ry2 = caixa[:4]
        ix = max(0, min(x2, rx2) - max(x1, rx1))
        iy = max(0, min(y2, ry2) - max(y1, ry1))
        if iy < 0.25 * altura or ix < 0.10 * largura:
            continue
        cobertura_x = ix / largura
        cobertura_y = iy / altura
        distancia = abs((rx1 + rx2) / 2 - (x1 + x2) / 2) / largura
        pontuacao = 2.0 * cobertura_y + cobertura_x - 0.15 * distancia
        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor = (indice, str(_texto or "").strip(), float(confianca or 0.0))
    return melhor


_PALAVRAS_CURTAS_OCR = frozenset(
    "a an and as at be by do for he if in is it no of on or so the to we".split()
)


def _parece_fragmento_ocr(linha: Sequence[BoxEntry], texto: str,
                          registros) -> bool:
    """Identifica sobra curta do detector interno coberta por uma linha OCR.

    Em fontes ornamentadas uma única linha como ``Solutions`` pode ser
    quebrada pelo detector de glifos em ``S0l``/``u``/``tl0ns``. O registro do
    Tesseract já cobre a faixa inteira, mas o contrato de uso único deixa as
    sobras no fallback neural. Palavras curtas reais e lances continuam
    protegidos por listas/réguas explícitas.
    """
    valor = str(texto or "").strip()
    if not valor or len(valor) > 5 or valor.casefold() in _PALAVRAS_CURTAS_OCR:
        return False
    if (any(char in GLIFOS_DE_XADREZ for char in valor)
            or re.search(r"[a-h][1-8]", valor, re.IGNORECASE)):
        return False
    return _casar_linha_ocr(linha, registros, set()) is not None


def _preservar_glifos_de_xadrez(texto_base: str, texto_contextual: str) -> str:
    """Põe os glifos reconhecidos pela rede especializada na prosa contextual.

    Tesseract é muito forte em letras, mas não possui as peças Unicode do
    livro no seu modelo latino: normalmente escreve ``Q``/``B``/``N`` no lugar
    delas. A posição relativa na linha é estável o bastante para substituir o
    caractere correspondente, sem trocar a frase inteira pelo OCR de glifo.
    """
    contextual = str(texto_contextual or "").strip()
    base = str(texto_base or "")
    # A CNN de glifos pode confundir uma letra maiúscula com uma peça quando
    # ela aparece isolada (por exemplo, ``♔idy`` para ``Saidy``). Só levamos a
    # peça para a prosa contextual quando o mesmo token tem a forma de uma
    # jogada: uma casa de xadrez, um número de lance ou uma promoção.
    pecas = []
    deslocamento = 0
    for token in re.findall(r"\S+", base):
        tem_casa = bool(re.search(r"[a-h][1-8]", token, re.IGNORECASE))
        tem_lance = bool(re.search(r"\d", token))
        if tem_casa or tem_lance:
            for indice, char in enumerate(token):
                if char in GLIFOS_DE_XADREZ:
                    pecas.append((deslocamento + indice, char))
        deslocamento += len(token)
    if not pecas or not contextual:
        return contextual
    posicoes = [indice for indice, char in enumerate(contextual) if not char.isspace()]
    if not posicoes:
        return contextual
    saida = list(contextual)
    total_base = max(1, len(base.replace(" ", "")) - 1)
    total_contexto = len(posicoes) - 1
    anteriores = set()
    for indice, char in pecas:
        alvo = round(indice * total_contexto / total_base)
        alvo = max(0, min(total_contexto, alvo))
        # Mantém a ordem mesmo quando duas peças caem no mesmo ponto devido a
        # uma leitura contextual mais curta.
        while alvo in anteriores and alvo < total_contexto:
            alvo += 1
        anteriores.add(alvo)
        saida[posicoes[alvo]] = char
    return "".join(saida)


def _preservar_glifos_por_palavra(
        texto_base: str, texto_contextual: str,
        glifos: Sequence[Tuple[int, float, str]], detalhes=()) -> str:
    """Mescla as peças internas na palavra contextual correspondente.

    A versão antiga distribuía todos os glifos pela linha inteira. Isso era
    frágil: uma diferença de uma palavra no Tesseract deslocava todas as
    peças seguintes para outra palavra. Aqui a coordenada horizontal do box
    especializado escolhe primeiro a palavra do OCR contextual e só então a
    posição relativa dentro dela.

    ``glifos`` contém posição no texto interno, centro X na página e caractere.
    ``detalhes`` é a sequência opcional de palavras do Tesseract, no formato
    ``(texto, confiança, (x1, y1, x2, y2))``. A coordenada escolhe a palavra e
    a posição dentro do box escolhe o caractere. Sem detalhes, conservamos o
    algoritmo antigo para manter compatibilidade com leitores externos.
    """
    if not detalhes:
        return _preservar_glifos_de_xadrez(texto_base, texto_contextual)
    contextual = str(texto_contextual or "").strip()
    if not contextual or not glifos:
        return contextual

    # Só peças dentro de tokens que têm evidência de nota ou lance entram na
    # mescla. Sem esta guarda, uma classificação isolada de uma letra comum
    # (por exemplo, o S de ``Saidy``) poderia virar uma peça Unicode.
    tokens_base = list(re.finditer(r"\S+", str(texto_base or "")))
    glifos_validos = []
    for posicao, centro_x, glifo in glifos:
        token = next((achado for achado in tokens_base
                      if achado.start() <= posicao < achado.end()), None)
        if token is None:
            continue
        palavra = token.group(0)
        if (re.search(r"[a-h][1-8]", palavra, re.IGNORECASE)
                or re.search(r"\d", palavra)):
            glifos_validos.append((float(centro_x), glifo, posicao))
    if not glifos_validos:
        return contextual

    palavras = []
    cursor = 0
    for detalhe in detalhes:
        if len(detalhe) < 3:
            continue
        palavra = str(detalhe[0] or "").strip()
        caixa = detalhe[2]
        if not palavra or len(caixa) < 4:
            continue
        inicio = contextual.find(palavra, cursor)
        if inicio < 0:
            # O Tesseract pode devolver uma palavra com pontuação diferente;
            # a ordem ainda é útil, então não força uma posição inexistente.
            inicio = cursor
        fim = min(len(contextual), inicio + len(palavra))
        palavras.append((inicio, fim, palavra, tuple(float(v) for v in caixa[:4])))
        cursor = fim
    if not palavras:
        return contextual

    saida = list(contextual)
    ocupados = set()
    for centro_x, glifo, posicao in glifos_validos:
        candidatos = []
        for indice, (inicio, fim, palavra, caixa) in enumerate(palavras):
            x1, _y1, x2, _y2 = caixa
            largura = max(1.0, x2 - x1)
            distancia = 0.0 if x1 <= centro_x <= x2 else min(
                abs(centro_x - x1), abs(centro_x - x2)) / largura
            # Uma peça não pode saltar para uma coluna muito distante. A
            # tolerância cobre pequenas diferenças entre os boxes internos e
            # o box de palavra do Tesseract, sem atravessar a coluna vizinha.
            if distancia <= 1.25:
                candidatos.append((distancia, indice, inicio, fim, palavra, caixa))
        if not candidatos:
            continue
        escolhido_candidato = min(candidatos)
        _distancia, indice, inicio, fim, palavra, caixa = escolhido_candidato
        # O detector interno às vezes não abre espaço entre ``35...`` e a
        # jogada seguinte, enquanto o Tesseract abre. Nessa fronteira o box da
        # peça pode ainda tocar o token puramente numérico; se há um token à
        # direita próximo, ele é a jogada correta e não o número do lance.
        if (re.fullmatch(r"\d+[.]*", palavra)
                and posicao > 0
                and str(texto_base)[posicao - 1] in ".0123456789"):
            a_direita = [item for item in candidatos if item[2] > inicio
                         and item[2] <= fim + 60]
            if a_direita:
                escolhido_candidato = min(
                    a_direita, key=lambda item: (item[2] - inicio, item[0]))
                _distancia, indice, inicio, fim, palavra, caixa = \
                    escolhido_candidato
        x1, _y1, x2, _y2 = caixa
        alvos = [i for i in range(inicio, fim)
                 if not contextual[i].isspace()]
        if not alvos:
            continue
        # A posição relativa no box da palavra escolhe o caractere. O índice
        # usa também pontuação: em ``37...@h8`` o ``@`` é a leitura contextual
        # da peça e, em ``35.Qh2``, a peça está depois de ``35.``. Usar apenas
        # letras/números deslocaria ambos os casos. ``floor`` modela as faixas
        # de cada caractere melhor que ``round`` para o pequeno box de uma peça
        # no início de ``Wh5t``.
        x1, _y1, x2, _y2 = caixa
        proporcao = max(0.0, min(0.999999,
                                 (centro_x - x1) / max(1.0, x2 - x1)))
        inicio_promocao = palavra.rfind("=")
        if inicio_promocao >= 0:
            depois_do_igual = [item for item in alvos
                               if item > inicio + inicio_promocao]
            alvo = depois_do_igual[0] if depois_do_igual else alvos[-1]
        else:
            alvo = alvos[int(proporcao * len(alvos))]
        # Duas caixas internas podem cair no mesmo caractere em uma palavra
        # curta (``Qh5+``). Procura a posição vizinha antes de desistir.
        ordem = sorted(alvos, key=lambda item: abs(item - alvo))
        escolhido = next((item for item in ordem if item not in ocupados), None)
        if escolhido is None:
            continue
        saida[escolhido] = glifo
        ocupados.add(escolhido)
    return "".join(saida)


def _corrigir_prosa_contextual(texto: str, idioma: str = "en", *,
                               fuzzy: bool = True) -> str:
    """Corrige erros tipográficos claros usando um vocabulário de frequência.

    Não é um corretor livre: só atua em palavras minúsculas, com pelo menos
    três letras, quando a alternativa comum tem similaridade alta e frequência
    muito maior. Assim nomes de jogadores, cabeçalhos e notação continuam
    sendo responsabilidade do OCR especializado.
    """
    if not texto:
        return texto
    # A trama da coluna de conteúdo faz o Tesseract devolver marcas de
    # verificação como ``¥``/replacement-character. Elas não são texto e não
    # podem contaminar a prosa depois que a linha contextual foi escolhida.
    texto = (str(texto).replace("\ufffd", "")
             .replace("\xa5", "")
             .replace("�", ""))
    if not re.search(r"\d", texto):
        # ``=`` e ``~`` soltos são resíduos da mesma textura; preservamos ``=``
        # quando a linha contém lances, onde ele pode ser promoção.
        texto = re.sub(r"(?<!\w)[=~|]+(?!\w)", " ", texto)
    texto = re.sub(r"\bof['’]a\b", "of a", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s+", " ", texto).strip()
    chave_idioma = "pt" if str(idioma or "en").lower().startswith("pt") else "en"
    # As trocas diretas são conhecimento desta fonte, não do vocabulário: elas
    # valem mesmo sem `wordfreq`/`rapidfuzz` instalados. Só a busca aproximada
    # depende dos dois, e sem eles ela é desligada em silêncio, como qualquer
    # outra melhoria opcional do caminho de livro.
    vocabulario = _VOCABULARIO_OCR.get(chave_idioma) if fuzzy else None
    if fuzzy and vocabulario is None:
        try:
            from wordfreq import top_n_list
            vocabulario = top_n_list(chave_idioma, 100000)
        except Exception:
            vocabulario = []
        _VOCABULARIO_OCR[chave_idioma] = vocabulario
    if vocabulario:
        try:
            from rapidfuzz import fuzz, process
            from wordfreq import zipf_frequency
        except Exception:
            vocabulario = []

    def corrigir(match: re.Match[str]) -> str:
        palavra = match.group(0)
        direta = _ERROS_OCR_FREQUENTES.get(palavra.casefold())
        if direta is not None:
            if palavra.isupper():
                return direta.upper()
            return direta.capitalize() if palavra[:1].isupper() else direta
        if (not vocabulario or len(palavra) < 3 or palavra.isupper()
                or palavra[:1].isupper() or not palavra.islower()):
            return palavra
        candidatos = process.extract(palavra, vocabulario, scorer=fuzz.ratio,
                                     limit=3, score_cutoff=74)
        if not candidatos:
            return palavra
        melhor, similaridade, _ = candidatos[0]
        if (melhor == palavra
                or similaridade < 74
                or zipf_frequency(melhor, chave_idioma) < 4.0
                or zipf_frequency(melhor, chave_idioma)
                <= zipf_frequency(palavra, chave_idioma) + 0.3):
            return palavra
        # Ambiguidade lexical: não escolhe entre duas palavras igualmente
        # próximas, pois isso seria pior que deixar a revisão sinalizar a forma.
        if (len(candidatos) > 1 and candidatos[1][1] == similaridade
                and zipf_frequency(candidatos[1][0], chave_idioma) >= 4.0):
            return palavra
        return melhor

    # O lance não passa pelo corretor. Ele corria sobre a linha inteira, e a
    # busca aproximada trocava `axb4` por `ab4` e `cxd5` por `cd5`: são três
    # letras, minúsculas, e `ab4` não está no vocabulário, mas `ab` está.
    return " ".join(token if _e_token_de_notacao(token)
                    else re.sub(r"[A-Za-zÀ-ÿ]+", corrigir, token)
                    for token in texto.split(" "))


def _transferir_medidas(texto_antigo: str, texto_novo: str,
                        pesos: Sequence[Optional[float]],
                        lacunas: Sequence[Optional[float]]):
    """Alinha negrito/lacunas ao texto que ganhou contexto de palavra."""
    novos_pesos: List[Optional[float]] = [None] * len(texto_novo)
    novas_lacunas: List[Optional[float]] = [None] * len(texto_novo)
    matcher = SequenceMatcher(None, texto_antigo, texto_novo, autojunk=False)
    for _tag, inicio_a, fim_a, inicio_n, fim_n in matcher.get_opcodes():
        if inicio_a >= fim_a or inicio_n >= fim_n:
            continue
        for indice_novo in range(inicio_n, fim_n):
            proporcao = (indice_novo - inicio_n) / max(1, fim_n - inicio_n)
            indice_antigo = min(fim_a - 1,
                                inicio_a + int(proporcao * (fim_a - inicio_a)))
            if indice_antigo < len(pesos):
                novos_pesos[indice_novo] = pesos[indice_antigo]
            if indice_antigo < len(lacunas):
                novas_lacunas[indice_novo] = lacunas[indice_antigo]
    return novos_pesos, novas_lacunas


def _texto_da_linha(img: np.ndarray, linha: Sequence[BoxEntry],
                    classificar: Callable, conf_minima: float,
                    coletor: Optional[Callable] = None,
                    pagina: int = 0,
                    marcador_glifo: Optional[Callable] = None,
                    marcador_confianca: Optional[Callable] = None
                    ) -> Tuple[str, int, List[Optional[float]],
                               List[Optional[float]], List[int]]:
    """
    (texto, caídos por confiança, espessura, lacuna e box de cada caractere).

    O `coletor` recebe todo caractere classificado, com a confiança junto. É
    aqui que ele entra porque é aqui que os dois dados existem juntos, e a
    função não sabe nem precisa saber o que ele faz com eles — nem sequer se
    ele vai guardar aquele.

    `marcador_confianca(indice_do_box, caractere, confiança)` recebe o mesmo
    que o coletor, box a box, **inclusive o derrubado**. É instrumento: foi
    por ele que se mediu, na página 30 do Aagaard, que a cadeia erra o lance
    com confiança (mediana 1,00 nos tokens errados) — o que descartou gatear
    uma segunda opinião pela confiança — e que o `?` e o `!` saíam como `.`
    mais um gancho derrubado a 0,2, que é o que levou à régua do pingo
    (`BoxService.FOLGA_DE_DIACRITICO`). Vai pelo índice do box, e não pela
    posição no texto, porque o texto ainda vai ser aparado e `caixas` é o que
    liga os dois.

    **A espessura sai daqui pelo mesmo motivo** (F105): é aqui que o recorte do
    glifo e o caractere que ele virou existem juntos, e a régua do negrito
    precisa dos dois — a espessura de um `.` só quer dizer alguma coisa
    comparada com a de outros `.`. A lista sai alinhada ao `texto`, caractere a
    caractere, com `None` no espaço entre palavras e no que não deu para medir.

    **O caractere derrubado por confiança não abre espaço** (F115). A régua do
    vão corria entre caixas vizinhas e não olhava se a do meio tinha produzido
    letra: um glifo derrubado entre dois vãos largos escrevia **dois** espaços,
    e um derrubado no meio da palavra partia a palavra em duas. Medido no
    Kasparov exportado, 298 parágrafos com espaço duplo; e `knight` com o `g`
    fraco saía `kni ht`, que são dois pedaços que o dicionário não conhece —
    contra `kniht`, que é uma palavra só e o reparo ainda pode alcançar.

    O vão continua sendo medido entre caixas vizinhas, que é onde ele existe;
    o que muda é **quando ele é escrito**. Enquanto nada sai, o espaço fica
    pendente, e sai uma vez só quando o próximo caractere sai. Isso mantém as
    duas leituras certas com uma régua só: o buraco no meio de `knight` não
    separa nada, e o `✝` derrubado entre duas palavras continua separando-as.

    **A lacuna sai daqui pelo mesmo motivo que a espessura** (F115): é o vão
    entre esta caixa e a anterior, em larguras medianas da linha, e é o que
    `lexico.partir_colada` precisa para achar onde faltou um espaço. Ela é
    `None` onde não dá para medir — no primeiro caractere, no espaço entre
    palavras, e depois de uma caixa que não produziu letra —, e `0,0` dentro de
    uma ligadura, onde não há vão porque as duas letras saem do mesmo box.

    **O normalizador não decide nada, e é bom que não decida.** As três
    condições de `partir_colada` comparam as lacunas de *dentro da mesma
    palavra* umas com as outras, então dividir todas pela mesma largura não muda
    resposta nenhuma. Ele está aqui para o número ser legível e comparável com o
    que a F9.1 mediu (0,18–0,50 no corte contra 0,00–0,27 fora dele), e é a
    mediana da linha pela mesma razão que a régua do espaço é (F107).

    **E o box de cada caractere, que é o que `lexico.reparar` chama de
    `simbolos`** (F115). O par `(caractere, índice do box)` é o contrato dele, e
    ele existe porque **um box não vale um caractere**: a ligadura traz dois, e o
    derrubado por confiança não traz nenhum. Só aqui essa conta é conhecida. O
    índice é dentro de `linha`, e quem quiser o da página converte — é o que o
    `extrair_pagina` faz, porque a régua do box largo é da página inteira.
    O espaço inserido não veio de box nenhum, e leva `-1`.
    """
    # A régua do espaço é do `diagrama` e é uma só (F107) — ver
    # `limiar_de_espaco`. Ela mede o vão contra o **vão típico desta linha**, e
    # não contra a largura de tinta: largura de tinta muda com o alfabeto sem
    # que o espacejamento mude junto, e era isso que partia `2011` em `20 1 1`.
    limiar = diagrama.limiar_de_espaco(linha)
    largura = float(np.median([b.x2 - b.x1 for b in linha])) if linha else 1.0
    largura = largura or 1.0
    partes, fracos = [], 0
    pesos: List[Optional[float]] = []
    lacunas: List[Optional[float]] = []
    caixas: List[int] = []
    pendente = False
    # Alguma caixa entre a última que escreveu e esta não escreveu nada: a
    # lacuna atravessa um buraco e deixa de ser a distância entre dois vizinhos.
    saltou = False
    for i, b in enumerate(linha):
        recorte = vertical.recorte_de_pe(img, b)
        char, conf = classificar(recorte) if recorte.size else ("", 0.0)
        # O coletor recebe **tudo** que foi classificado, e ele é que decide o
        # que guardar. Filtrar aqui prendia a coleta ao piso de confiança, e há
        # revisão que quer o contrário: a pasta cheia de acertos com alguns
        # intrusos, que é como se acha erro batendo o olho.
        if char and coletor is not None:
            coletor(recorte, char, conf, pagina)
        if marcador_confianca is not None:
            marcador_confianca(i, notacao.normalizar_saida(char or ""), conf)
        if char and conf < conf_minima:
            char, fracos = "", fracos + 1
        if i and b.x1 - linha[i - 1].x2 > limiar:
            pendente = True
        # **Depois do coletor, e antes do texto.** A base de treino guarda o
        # recorte sob a classe que o modelo emitiu — é ela que ensina o modelo —,
        # e o livro recebe o que a classe significa: o `✝` do xeque sai `+`, e
        # uma busca por `Nxe4+` passa a achar a página. Ver `notacao`.
        saida = notacao.normalizar_saida(char or "")
        if not saida:
            saltou = True
            continue
        if pendente:
            partes.append(" ")
            pesos.append(None)
            lacunas.append(None)
            caixas.append(-1)
            pendente = False
        vao = (None if i == 0 or saltou
               else (b.x1 - linha[i - 1].x2) / largura)
        if marcador_glifo is not None:
            inicio_saida = len("".join(partes))
            for deslocamento, simbolo in enumerate(saida):
                if simbolo in GLIFOS_DE_XADREZ:
                    marcador_glifo(inicio_saida + deslocamento,
                                   (b.x1 + b.x2) / 2.0, simbolo)
        partes.append(saida)
        # Um por caractere **do que saiu**, e não do que entrou: um sinônimo de
        # saída pode ter mais de um caractere. É o que mantém as listas
        # alinhadas ao texto.
        pesos.extend([negrito.espessura(recorte)] * len(saida))
        lacunas.extend([vao] + [0.0] * (len(saida) - 1))
        caixas.extend([i] * len(saida))
        saltou = False
    texto = "".join(partes)
    # O `strip` do texto tem de acontecer nos quatro, ou o alinhamento se perde
    # logo na primeira linha que comece com espaço.
    inicio = len(texto) - len(texto.lstrip())
    fim = len(texto.rstrip())
    return (texto[inicio:fim], fracos, pesos[inicio:fim],
            lacunas[inicio:fim], caixas[inicio:fim])


def _reparar_texto(texto: str, pesos: List[Optional[float]],
                   lacunas: List[Optional[float]], caixas: Sequence[int],
                   largos, lex, provar
                   ) -> Tuple[str, List[Optional[float]],
                              List[Optional[float]], int]:
    """
    A palavra que a colagem estragou, corrigida pelo dicionário (F115).

    **É o quarto e último reparo da lista da F109 §4.1, e o único que precisava
    de duas coisas que só existem aqui**: o box de cada caractere, para saber o
    que veio de um box largo demais para um glifo, e a imagem, para a prova
    visual poder olhar o papel.

    `lexico.reparar` apaga o que veio do box largo, ancora no resto e procura no
    dicionário uma palavra naquele molde: `Dmamic` vira `D` + máscara + `amic`,
    e só `dynamic` cabe. **A prova da F69 é obrigatória aqui**, e o `provar` é
    quem a traz: sem ela o reparo escolhe por comprimento, e a F66 mediu 62,5%
    de precisão — inaceitável para algo que reescreve o texto em silêncio. Com
    ela, a nota separa o que está desenhado no papel do que não está.

    **A palavra sem box largo nem chega a ser perguntada.** É o caso da imensa
    maioria, e pular antes de consultar o dicionário é o que faz o reparo caber
    num livro inteiro.

    O texto pode mudar de comprimento — `Dmamic` tem seis letras e `Dynamic`
    tem sete. Quando muda, a espessura e a lacuna do trecho saem: elas foram
    medidas sobre os glifos que estavam lá, e não sobre os que passaram a
    estar. Quando não muda, ficam — e o negrito da palavra reparada sobrevive.
    """
    trocas: List[Tuple[int, int, str]] = []
    for achado in re.finditer(r"\S+", texto):
        inicio, fim = achado.span()
        pedaco = achado.group(0)
        if notacao.parece_lance(pedaco):
            continue
        simbolos = [(texto[i], caixas[i]) for i in range(inicio, fim)]
        if not any(i in largos for _c, i in simbolos):
            continue
        reparo = lexico.reparar(simbolos, largos, lex, provar)
        if reparo is None:
            continue
        _nuc, desloc = lexico.nucleo(pedaco)
        trocas.append((inicio + desloc,
                       inicio + desloc + len(reparo.palavra),
                       reparo.corrigida))

    if not trocas:
        return texto, pesos, lacunas, 0

    partes: List[str] = []
    novos: List[Optional[float]] = []
    novas: List[Optional[float]] = []
    anterior = 0
    for inicio, fim, corrigida in trocas:
        partes.append(texto[anterior:inicio])
        novos.extend(pesos[anterior:inicio])
        novas.extend(lacunas[anterior:inicio])
        partes.append(corrigida)
        if len(corrigida) == fim - inicio:
            novos.extend(pesos[inicio:fim])
            novas.extend(lacunas[inicio:fim])
        else:
            novos.extend([None] * len(corrigida))
            novas.extend([None] * len(corrigida))
        anterior = fim
    partes.append(texto[anterior:])
    novos.extend(pesos[anterior:])
    novas.extend(lacunas[anterior:])
    return "".join(partes), novos, novas, len(trocas)


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


def _em_cima_da_regua(b: BoxEntry, horizontais: Sequence[Tuple[int, int]],
                      verticais: Sequence[Tuple[int, int]], tipica: float) -> bool:
    """O box que é um pedaço da régua da moldura, e não conteúdo da célula.

    A divisória vertical da tabela do Nunn (p. 237) sobrevive ao `trama.aplicar`
    em pedaços de 4–8 × 107–178 px, um por fila — 19 na página —, todos com
    o centro a 3 px da régua que `_grade` achou. Dentro da célula, um deles
    esticava a linha `W:Win(1 ♖e1!)` até a fila de baixo (y 427–583), e a
    linha casava o registro errado do motor e perdia a faixa; fora dela, os
    das bordas saíam depois da tabela como parágrafos `H l`, `u l u`, `ll`.
    O pedaço é mais alto que duas alturas de glifo e mais estreito que meia,
    e tem o centro a menos de meia altura da régua; o `l` e o `|` de verdade
    têm uma altura só. O mesmo, deitado, para a régua horizontal.
    """
    largura, altura = b.x2 - b.x1, b.y2 - b.y1
    cx, cy = (b.x1 + b.x2) / 2, (b.y1 + b.y2) / 2
    folga = tipica / 2
    if altura >= 2 * tipica and largura <= folga:
        return any(abs(cx - (r0 + r1) / 2) <= folga for r0, r1 in verticais)
    if largura >= 2 * tipica and altura <= folga:
        return any(abs(cy - (r0 + r1) / 2) <= folga for r0, r1 in horizontais)
    return False


def _tabela_da_pagina(img: np.ndarray, boxes: Sequence[BoxEntry],
                      classificar: Callable, conf_minima: float,
                      coletor, numero: int, leitor: Optional[Callable] = None):
    """
    `(Tabela, boxes consumidos, topo, fracos)` — ou `None`, se não há tabela.

    `leitor(linha, rotulo) -> (texto, derrubados)` lê cada linha de célula no
    lugar de `_texto_da_linha`: é o `ler_celula` de `extrair_pagina`, que
    passa a célula pelo motor como passa a linha de prosa. Sem ele a célula
    é só da cadeia, como era.

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

    # **O que está dentro do retângulo da tabela é da tabela**, marcado ou
    # não. A marca vem de `trama.glifos`, que só aceita componente com altura
    # de caractere (`ALTURA_GLIFO`): os dois pontos e as reticências das
    # células da página 236 do Nunn ficam abaixo dela, não recebem a marca e
    # sobravam na página — saíam depois da tabela como linhas de `: : :` e
    # `... ... ...`, e as células saíam `W Win (1 ♖e1!)` sem o `:` e sem o
    # `1...`. Uma moldura por página, então o retângulo é a régua.
    x1, y1, x2, y2 = regiao
    de_moldura = [b for b in boxes
                  if getattr(b, "moldura", False)
                  or (x1 <= (b.x1 + b.x2) / 2 <= x2
                      and y1 <= (b.y1 + b.y2) / 2 <= y2)]

    # **O box em cima da régua é a régua**, e a tabela o consome sem ler: nem
    # é conteúdo da célula, nem pode sobrar para virar linha da página.
    alturas = sorted(b.y2 - b.y1 for b in de_moldura)
    tipica = alturas[len(alturas) // 2]
    usados: List[BoxEntry] = [b for b in de_moldura
                              if _em_cima_da_regua(b, horizontais, verticais, tipica)]
    reguas = {id(b) for b in usados}
    de_moldura = [b for b in de_moldura if id(b) not in reguas]

    matriz: List[List[str]] = []
    fracos = 0
    for i, (ya, yz) in enumerate(filas):
        fila: List[str] = []
        for j, (xa, xz) in enumerate(colunas):
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
            for k, sub in enumerate(quebrar_em_linhas(
                    BoxService._agrupar_em_linhas(dentro))):
                # A célula não leva peso: a tabela sai como `Tabela`, e nem o
                # EPUB nem o DOCX marcam negrito dentro de célula (F105).
                if leitor is not None:
                    texto, n = leitor(sub, f"t{i}c{j}l{k}")
                else:
                    texto, n, _pesos, _lac, _cx = _texto_da_linha(
                        img, sub, classificar, conf_minima, coletor, numero)
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
    #: A espessura do traço de cada caractere do `texto` (F105), como sai do
    #: `_texto_da_linha`. `None` é a linha que veio de outro lugar que não a
    #: página — as dos testes, e as que se montam à mão.
    pesos: Optional[List[Optional[float]]] = None
    #: A lacuna antes de cada caractere do `texto`, em larguras medianas da
    #: linha (F115). É o que `lexico.partir_colada` precisa para achar onde
    #: faltou um espaço, e vem do mesmo lugar e pelo mesmo motivo que `pesos`:
    #: é aqui que o box e o caractere que ele virou existem lado a lado.
    lacunas: Optional[List[Optional[float]]] = None
    #: O domínio que `_dominio_da_linha` viu na âncora, e quem escreveu o
    #: `texto`: `glyph` (a cadeia própria), `fusao` (lance da âncora, prosa do
    #: motor) ou `line` (a linha do motor com as figurinas repostas). É o que o
    #: A/B separa para medir prosa e notação cada uma por si.
    dominio: str = "prose"
    fonte: str = "glyph"
    #: O índice do registro desta linha em `PaginaExtraida.roteamento`, para
    #: o parágrafo que ela vai formar guardar de onde veio (`Paragrafo.
    #: registros`). `None` na linha que não passou pelo roteador.
    registro: Optional[int] = None


def _metricas_por_coluna(linhas: Sequence[Linha]) -> dict:
    """
    {coluna: (margem esquerda, altura de glifo, passo de linha)}, da página.

    **A margem é por coluna, e sem isso a de duas colunas sai despedaçada**
    (F61). A mediana das esquerdas de uma página de duas colunas não é margem
    nenhuma: metade das linhas começa em 122 e metade em 893, e a mediana cai
    num dos dois. Com ela, ou a coluna da direita inteira parece recuada — cada
    linha vira um parágrafo — ou a da esquerda perde todos os recuos que tem.

    **O passo é por coluna pelo mesmo motivo, e é ele que decide** (F103). O vão
    entre uma linha e a seguinte só quer dizer alguma coisa comparado com o vão
    normal daquela coluna; comparado com a altura dos glifos, não quer dizer
    nada — ver `SALTO_DE_PARAGRAFO`.

    **E é da página, não do trecho.** Estas medidas são medianas, e a mediana
    de cinco linhas entre dois diagramas não diz onde fica a margem da coluna.

    O passo sai dos vãos entre linhas **ordenadas pelo topo**, e não pela ordem
    da lista: a mediana é robusta ao vão grande que um diagrama no meio da
    coluna abre, mas não a um vão negativo, que é o que a ordem de leitura
    produz na virada de coluna.
    """
    por_coluna = {}
    for linha in linhas:
        por_coluna.setdefault(linha.coluna, []).append(linha)

    metricas, vaos_da_pagina = {}, []
    for coluna, desta in por_coluna.items():
        esquerdas = sorted(linha.esquerda for linha in desta)
        alturas = sorted(linha.altura for linha in desta)
        topos = sorted(linha.topo for linha in desta)
        vaos = sorted(b - a for a, b in zip(topos, topos[1:]) if b > a)
        vaos_da_pagina.extend(vaos)
        metricas[coluna] = (esquerdas[len(esquerdas) // 2],
                            alturas[len(alturas) // 2] or 1,
                            vaos[len(vaos) // 2] if vaos else 0)

    # A coluna de uma linha só não tem vão para medir. Cai para o passo da
    # página, e na falta dele para a altura de glifo — onde, de todo modo, não
    # há segunda linha para abrir parágrafo.
    da_pagina = (vaos_da_pagina[len(vaos_da_pagina) // 2]
                 if vaos_da_pagina else 0)
    return {coluna: (margem, altura,
                     passo or da_pagina or max(1, int(altura * PASSO_POR_ALTURA)))
            for coluna, (margem, altura, passo) in metricas.items()}


def _juntar_no_hifen(textos: List[str], pesos: List[List[Optional[float]]],
                     lacunas: List[List[Optional[float]]],
                     lex: Optional["lexico.Lexico"]) -> List[bool]:
    """
    Remonta a palavra partida no fim da linha — texto e espessuras juntos (F115).

    Devolve um booleano por linha: `juntas[i]` verdadeiro quer dizer que a linha
    `i` continua na `i + 1` **sem espaço no meio**.

    **`lexico.juntar_hifenizadas` existe desde a F9.1, com teste e com medição,
    e não tinha um chamador em produção** — a F104 mediu que ela juntaria 490
    palavras no Nunn, e as 490 continuavam saindo partidas no arquivo. Ela
    *propõe* e não altera nada, e é este o lugar de aplicar: aqui as linhas do
    parágrafo já estão juntas, que é a única altura em que a palavra existe
    inteira. Por linha, como a F108 fazia com a caixa, o `com-` e o `promised`
    nunca se veem.

    A remontagem é a do léxico — o hífen sai, e o resto dos dois pedaços fica.
    A direita entra a partir do **núcleo**: pontuação abrindo a linha seguinte é
    borda, e não faz parte da palavra que se remonta.

    **O vetor de espessuras anda junto, e é por isso que esta função mexe nos
    dois** (F105). Cada caractere que sai do texto sai também do vetor, e o
    espaço que deixa de separar as duas linhas leva o `None` dele — senão a
    marcação de negrito do resto do parágrafo anda uma casa por junção.
    """
    juntas = [False] * len(textos)
    if lex is None or lex.vazio:
        return juntas
    for juncao in lexico.juntar_hifenizadas([t.split(" ") for t in textos],
                                            lex):
        k = juncao.linha
        sem_hifen = textos[k].rstrip(lexico.HIFENS)
        del pesos[k][len(sem_hifen):]
        del lacunas[k][len(sem_hifen):]
        textos[k] = sem_hifen
        _nuc, ini = lexico.nucleo(textos[k + 1].split(" ")[0])
        if ini:
            textos[k + 1] = textos[k + 1][ini:]
            del pesos[k + 1][:ini]
            del lacunas[k + 1][:ini]
        # A lacuna do primeiro caractere da linha de baixo já era `None` — não
        # há caixa anterior nela —, e continua sendo depois da junção: o vão
        # entre as duas metades da palavra atravessa uma quebra de linha e não
        # é distância nenhuma. É o que faz `_partir_coladas` recusar a palavra
        # remontada, que é o certo: ela acabou de ser afirmada pelo dicionário.
        juntas[k] = True
    return juntas


#: Quantas vezes a altura de glifo de uma linha tem de passar a da coluna para
#: ela ser título de capítulo (F111).
#:
#: A altura de uma `Linha` é a mediana das caixas dela; numa linha de prosa a
#: mediana é a minúscula, e num título em corpo maior é a maiúscula de um corpo
#: maior — o dobro, tipicamente. O 1,7 fica abaixo disso e acima do que uma
#: linha de notação alcança: ela é de dígito e figurina, que são altos, e mede
#: 1,3 a 1,5 alturas de minúscula. A régua de lance é a outra metade da
#: defesa.
TITULO_POR_ALTURA = 1.7

#: Fração da página, de cima para baixo, em que um título de capítulo começa.
#:
#: Medido no Yusupov: a régua da altura sozinha achava 60 "títulos", e metade
#: era o número de página em corpo grande ou a caixa de pontuação dos
#: exercícios ("If you scored less than 11 points…"), que é prosa em corpo
#: maior no pé da página. O capítulo abre no alto.
TOPO_DE_TITULO = 0.4

#: Letras entre os caracteres que não são espaço, no mínimo. O `gH♗` e o
#: `S .` que a altura pega são pedaço de diagrama e de ornamento, não título.
LETRAS_DE_TITULO = 0.7

#: A detecção de capítulo pela altura está **desligada**, e foi medida (F111).
#:
#: O sinal existe: no Yusupov o título tem 1,78 vezes o corpo, e a régua acha
#: as páginas certas — Contents, Preface, Exercises, Solutions, Scoring. Mas
#: o que ela devolve é o que o OCR lê num corpo de exibição, e isso é
#: `S()lut1.()ns` e `Sc0r1.n`: o `o` vira `()` e o `i` vira `1.`, que é a
#: família A da F109 em glifo grande. Com a régua de letras, sobram 20 títulos
#: em 264 páginas e metade é `fyu scred less` — a caixa de pontuação em corpo
#: maior. E no Aagaard o título de capítulo tem **1,27** vezes o corpo (`A
#: sneak preview`, pela camada de texto), abaixo de qualquer régua que não
#: inunde.
#:
#: A camada de texto do PDF traz os dois — o corpo em pontos e o texto limpo —
#: e por isso o capítulo é da F110, onde ele é exato e barato. Aqui fica o
#: mecanismo (`Paragrafo.nivel`, o `<h1>`, o sumário por capítulo) e a régua,
#: para `medir_prosa.py --capitulos` poder refazer a tabela.
DETECTAR_CAPITULOS = False


def _e_titulo(linhas: Sequence[Linha], altura_de_referencia: Optional[float]
              ) -> bool:
    """
    Uma linha só, alta contra a coluna, curta, de letras e sem lance (F111).

    A posição na página é a outra régua, e ela fica em `extrair_pagina`
    (`_confirmar_titulos`): aqui não se sabe a altura da página.
    """
    if len(linhas) != 1 or not altura_de_referencia:
        return False
    linha = linhas[0]
    if linha.altura < TITULO_POR_ALTURA * altura_de_referencia:
        return False
    cheio = linha.texto.replace(" ", "")
    letras = sum(c.isalpha() for c in cheio)
    if letras < 3 or letras < LETRAS_DE_TITULO * len(cheio):
        return False
    return _candidato_a_cabecalho(linha.texto)


def _confirmar_titulos(pagina: PaginaExtraida) -> None:
    """O título de capítulo abre no alto da página; o que a altura achou
    abaixo de `TOPO_DE_TITULO` volta a ser parágrafo."""
    if not pagina.altura:
        return
    for b in pagina.blocos:
        if (isinstance(b, Paragrafo) and b.titulo and b.nivel == 1
                and b.topo is not None
                and b.topo > pagina.altura * TOPO_DE_TITULO):
            b.titulo, b.nivel = False, 2


def _paragrafo_de(linhas: Sequence[Linha],
                  lex: Optional["lexico.Lexico"] = None,
                  altura_de_referencia: Optional[float] = None) -> Paragrafo:
    """
    As linhas de um parágrafo, juntas — texto e espessuras no mesmo passo.

    `altura_de_referencia` é a altura de glifo da coluna, e é o que decide se
    a linha é **título de capítulo** (F111): a que passa de
    `TITULO_POR_ALTURA` vezes ela sai com `titulo=True, nivel=1`.

    **O vetor de espessuras tem de ficar alinhado ao texto** (F105), e o espaço
    que junta duas linhas conta como caractere: sem o `nan` dele, a primeira
    quebra de linha do parágrafo deslocaria toda a medida do resto em um.

    **É aqui que o dicionário entra, e não na linha** (F115). A F108 o ligou em
    `extrair_pagina`, uma linha de cada vez, e ali metade das palavras que ele
    existe para consertar ainda não existe: a que o hífen partiu no fim da linha
    não está inteira em lado nenhum. Subir os reparos para o parágrafo é o que
    os põe sobre a palavra que o livro imprimiu, e não sobre o pedaço que coube
    na linha.

    **Dois dos três reparos correm aqui, e o terceiro não pode.** Juntar o hífen
    e arrumar a caixa decidem-se com a palavra na mão; partir o que está colado
    decide-se com o **livro** na mão, e por isso `partir_coladas` é uma passada
    à parte — ver lá. É a mesma separação que a F105 faz com o negrito: o que dá
    para medir na página mede-se aqui, e o que precisa de tudo espera.
    """
    textos = [linha.texto for linha in linhas]
    pesos = [list(linha.pesos) if linha.pesos is not None else [None] * len(linha.texto)
             for linha in linhas]
    lacunas = [list(linha.lacunas) if linha.lacunas is not None
               else [None] * len(linha.texto) for linha in linhas]
    juntas = _juntar_no_hifen(textos, pesos, lacunas, lex)

    partes: List[str] = []
    todos: List[Optional[float]] = []
    vaos: List[Optional[float]] = []
    inicios: List[int] = []
    for i, t in enumerate(textos):
        if i and not juntas[i - 1]:
            partes.append(" ")
            todos.append(None)
            vaos.append(None)
        inicios.append(len(todos))
        partes.append(t)
        todos.extend(pesos[i])
        vaos.extend(lacunas[i])
    texto = "".join(partes)

    if lex is not None:
        arrumado = lexico.arrumar_caixa(texto, lex)
        # **O contrato de `arrumar_caixa` é sair do mesmo comprimento**, e é
        # dele que o vetor de espessuras depende. Conferir custa a comparação
        # de dois inteiros e evita que uma mudança lá desligue o negrito daqui
        # em silêncio: `negrito.marcar` pula o parágrafo cujo vetor não bate
        # com o texto, e pular não deixa rastro nenhum.
        if len(arrumado) == len(texto):
            texto = arrumado

    capitulo = DETECTAR_CAPITULOS and _e_titulo(linhas, altura_de_referencia)
    return Paragrafo(texto, titulo=capitulo, nivel=1 if capitulo else 2,
                     pesos=negrito.vetor(todos),
                     lacunas=negrito.vetor(vaos),
                      topo=min(linha.topo for linha in linhas),
                      pe=max(linha.topo + linha.altura for linha in linhas),
                     inicios=inicios,
                     registros=[-1 if linha.registro is None else linha.registro
                                for linha in linhas])


#: Quantas vezes uma palavra precisa aparecer **sozinha** no material para
#: poder ser metade de um corte (F115).
#:
#: **Não é gosto: sem ele o reparo parte lixo em lixo.** `lexico.partir_colada`
#: exige que as duas metades estejam no dicionário, e o dicionário deste projeto
#: tem 310.465 palavras — nele existem `ng`, `fm`, `nt`, `er` e `feri`. Medido em
#: 200 páginas do Nunn e do Yusupov, o reparo solto dá 148 cortes e erra ~29:
#: `fering` vira `feri ng`, `fmnt` vira `fm nt`, `Bemer` vira `Bem er`. É o
#: mesmo perigo que `medir_lexico._parte_em_palavras` documenta — *"contra a
#: lista grande esta função mentia: `Benko` decompõe em `ben`+`ko`"* — e o
#: remédio é o dele: **o vocabulário do próprio material**.
#:
#: Exigir que as duas metades tenham sido vistas soltas duas vezes deixa 117 dos
#: 148 cortes e mata dois terços do erro. Uma vez só não separa: a metade
#: espúria costuma aparecer uma vez, dentro da própria palavra colada de outra
#: página.
VISTAS_PARA_CORTAR = 2


def vocabulario(paginas: Sequence["PaginaExtraida"],
                lex: "lexico.Lexico") -> dict:
    """
    {palavra: quantas vezes ela apareceu **sozinha**}, das páginas dadas.

    Só palavra que o dicionário conhece e que não é lance: é a lista de quem
    pode ser metade de um corte, e ela sai do próprio livro porque é a única
    fonte de frequência que este repositório tem (a mesma escolha que o
    `medir_confusao_no_livro` faz para o prior dele).
    """
    conta: dict = {}
    for pagina in paginas:
        for bloco in pagina.blocos:
            if not isinstance(bloco, Paragrafo):
                continue
            for pedaco in bloco.texto.split():
                if notacao.parece_lance(pedaco):
                    continue
                nuc, _i = lexico.nucleo(pedaco)
                if nuc and lex.conhece(nuc):
                    chave = nuc.lower()
                    conta[chave] = conta.get(chave, 0) + 1
    return conta


def _cortes_do_paragrafo(bloco: Paragrafo, lex: "lexico.Lexico",
                         visto: dict) -> List[int]:
    """Onde este parágrafo perdeu um espaço. Índices no `texto`, em ordem."""
    cortes: List[int] = []
    lacunas = bloco.lacunas
    if lacunas is None or len(lacunas) != len(bloco.texto):
        return cortes
    for achado in re.finditer(r"\S+", bloco.texto):
        pedaco = achado.group(0)
        if notacao.parece_lance(pedaco):
            continue
        nuc, desloc = lexico.nucleo(pedaco)
        if len(nuc) < 2 * lexico.MIN_PARTE:
            continue
        base = achado.start() + desloc
        fatia = [lacunas[i] for i in range(base + 1, base + len(nuc))]
        # Lacuna que não foi medida — caixa perdida por confiança no meio da
        # palavra, ou a junção que o hífen acabou de fazer. A terceira condição
        # de `partir_colada` compararia contra um número que ninguém mediu.
        if len(fatia) != len(nuc) - 1 or any(isnan(v) for v in fatia):
            continue
        corte = lexico.partir_colada(nuc, fatia, lex)
        if not corte:
            continue
        esquerda, direita = nuc[:corte].lower(), nuc[corte:].lower()
        if min(visto.get(esquerda, 0),
               visto.get(direita, 0)) < VISTAS_PARA_CORTAR:
            continue
        cortes.append(base + corte)
    return cortes


def partir_coladas(paginas: Sequence["PaginaExtraida"],
                   lex: Optional["lexico.Lexico"]) -> int:
    """
    Põe o espaço que a segmentação perdeu — `ofthe` vira `of the`. Devolve
    quantos (F115).

    **`lexico.partir_colada` é o terceiro dos reparos que a F109 §4.1 listou**,
    e o último a ganhar chamador em produção. Ele foi medido em 7 de 7 junções
    reais e traz três condições: a palavra não pode estar no dicionário, tem de
    partir em **duas** palavras que estão, e a lacuna no ponto de corte tem de
    ser a **maior de dentro da palavra**.

    **As três foram medidas sobre texto rotulado, e o OCR traz uma população que
    elas nunca viram.** Na verdade rotulada o único defeito é o espaço que
    faltou; na saída do modelo há `fering`, `fmnt` e `Wncura`, que também
    decompõem em duas palavras da lista. Daí o quarto portão desta função — o
    vocabulário do material —, e daí ela ser uma passada à parte: ele só existe
    depois de o livro inteiro estar lido. Ver `VISTAS_PARA_CORTAR`.

    **É o molde do `negrito.marcar`, e pela mesma razão** (F105): o
    `extrair_pagina` chama com a página que acabou de ler, que é o melhor que dá
    para fazer quando só há uma, e o `extrair` chama com todas — e é essa que
    vale. A operação é idempotente: o que já foi partido está no dicionário, e a
    primeira condição o recusa.
    """
    if lex is None or lex.vazio:
        return 0
    visto = vocabulario(paginas, lex)
    total = 0
    for pagina in paginas:
        for bloco in pagina.blocos:
            if not isinstance(bloco, Paragrafo):
                continue
            cortes = _cortes_do_paragrafo(bloco, lex, visto)
            if not cortes:
                continue
            partes, pesos, lacunas = [], [], []
            anterior = 0
            for corte in cortes:
                partes.append(bloco.texto[anterior:corte])
                pesos.extend(bloco.pesos[anterior:corte])
                lacunas.extend(bloco.lacunas[anterior:corte])
                # O espaço que entra não tem espessura nem lacuna medidas: ele
                # não estava na página, e é justamente essa a queixa.
                partes.append(" ")
                pesos.append(nan)
                lacunas.append(nan)
                anterior = corte
            partes.append(bloco.texto[anterior:])
            pesos.extend(bloco.pesos[anterior:])
            lacunas.extend(bloco.lacunas[anterior:])
            bloco.texto = "".join(partes)
            bloco.pesos = negrito.vetor(pesos)
            bloco.lacunas = negrito.vetor(lacunas)
            pagina.cortes += len(cortes)
            total += len(cortes)
    return total


#: Em quantas páginas o mesmo texto tem de aparecer na mesma margem para ser
#: cabeçalho ou rodapé (F109 §5).
#:
#: Três, e não uma fração do livro: o cabeçalho de capítulo muda a cada
#: capítulo, e um capítulo de dez páginas dá cinco ocorrências na página ímpar.
#: Uma fração de um livro de 2.612 páginas o deixaria passar inteiro.
PAGINAS_DE_CABECALHO = 3

#: Fração da altura da página que é margem — de cima ou de baixo. O parágrafo
#: que começa fora dela não é candidato, por mais que se repita.
MARGEM_DE_PAGINA = 0.12

#: Mais palavras que isto numa linha só não é cabeçalho, é prosa.
PALAVRAS_DE_CABECALHO = 8


def _assinatura(texto: str) -> str:
    """
    O que fica de um cabeçalho quando se tira o que muda de página para página.

    O número sai — `Chapter 3 · 37` e `Chapter 3 · 38` são o mesmo cabeçalho —
    e a pontuação vira espaço. O número de página sozinho vira a assinatura
    vazia, que é a de todo número de página.
    """
    baixo = re.sub(r"\d+", "", texto.lower())
    return " ".join(re.sub(r"[^\w\s]", " ", baixo).split())


def _candidato_a_cabecalho(linha: str) -> bool:
    """
    Uma linha curta, com letra ou número, e sem lance: a régua que a
    repetição ainda confirma.

    A letra ou o número é o que separa o número de página do `=` que o
    filete decorativo vira quando é lido: os dois têm a assinatura vazia, e
    sem isto o filete sairia como rodapé. Ele não é cabeçalho, é ruído, e
    ruído tem outro dono.
    """
    palavras = linha.split()
    if not 0 < len(palavras) <= PALAVRAS_DE_CABECALHO:
        return False
    if not any(c.isalnum() for c in linha):
        return False
    # O parêntese é o outro dono: `(see page 43)` no alto de três páginas é
    # remissão, e cabeçalho de página nunca vem entre parênteses.
    if linha.startswith("(") and linha.endswith(")"):
        return False
    return not any(notacao.parece_lance(_lance_limpo(w)) for w in palavras)


def _lance_limpo(palavra: str) -> str:
    """
    `20...♗d3!` como `parece_lance` o entende: sem o número do lance, com a
    figurina em letra e o travessão do roque em hífen. Ele lê `Bd3!`, e não
    o que o livro imprime — é a mesma tradução que `notacao.Simbolo` faz.
    """
    sem_numero = re.sub(r"^\d+\.(\.\.)?", "", palavra)
    return "".join(notacao.FIGURINAS.get(c, "-" if c in "–—" else c)
                   for c in sem_numero)


def _linha_da_margem(p: Paragrafo, margem: str) -> Tuple[int, int]:
    """
    `(início, fim)` no `texto` da linha impressa que encosta na margem —
    a primeira para `"alto"`, a última para `"baixo"`.

    O corte leva o espaço que a junta ao resto, para o parágrafo que sobra
    não começar nem acabar em espaço; e leva o **fim** do texto quando o
    parágrafo tem uma linha só.
    """
    if len(p.inicios) <= 1:
        return 0, len(p.texto)
    if margem == "alto":
        return 0, p.inicios[1]
    inicio = p.inicios[-1]
    if p.texto[inicio - 1:inicio] == " ":
        inicio -= 1
    return inicio, len(p.texto)


def _nas_margens(pagina: PaginaExtraida) -> List[Tuple[str, Paragrafo]]:
    """`[("alto", p), ("baixo", p)]` — o parágrafo de cada margem, se há."""
    paragrafos = [b for b in pagina.blocos
                  if isinstance(b, Paragrafo) and b.topo is not None
                  and b.inicios and not b.titulo]
    if not paragrafos or not pagina.altura:
        return []
    saida = []
    alto = min(paragrafos, key=lambda p: p.topo)
    if alto.topo <= pagina.altura * MARGEM_DE_PAGINA:
        saida.append(("alto", alto))
    baixo = max(paragrafos, key=lambda p: p.pe if p.pe is not None else p.topo)
    pe = baixo.pe if baixo.pe is not None else baixo.topo
    if (pe >= pagina.altura * (1 - MARGEM_DE_PAGINA)
            and not (baixo is alto and len(baixo.inicios) == 1)):
        saida.append(("baixo", baixo))
    return saida


def _cortar(p: Paragrafo, inicio: int, fim: int) -> None:
    """
    Tira `texto[inicio:fim]` do parágrafo, com os vetores no mesmo passo.

    Os vetores da F105 e da F115 andam caractere a caractere com o texto, e
    um corte fora de passo desligaria o negrito em silêncio — `negrito.marcar`
    pula o parágrafo cujo vetor não bate. `inicios` anda junto, e as fatias
    de negrito que o corte alcança saem: quem remarca com o livro inteiro as
    refaz.
    """
    p.texto = p.texto[:inicio] + p.texto[fim:]
    if p.pesos is not None:
        p.pesos = np.concatenate([p.pesos[:inicio], p.pesos[fim:]])
    if p.lacunas is not None:
        p.lacunas = np.concatenate([p.lacunas[:inicio], p.lacunas[fim:]])
    tamanho = fim - inicio
    # `registros` anda em paralelo a `inicios`: a linha que sai leva o
    # registro dela junto, senão o parágrafo apontaria para a linha errada.
    if len(p.registros) == len(p.inicios):
        p.registros = [r for i, r in zip(p.inicios, p.registros)
                       if not inicio <= i < fim]
    p.inicios = [i if i < inicio else i - tamanho
                 for i in p.inicios if not inicio <= i < fim]
    p.negrito = [(a if a < inicio else a - tamanho,
                  b if b <= inicio else b - tamanho)
                 for a, b in p.negrito if b <= inicio or a >= fim]


def retirar_cabecalhos(paginas: Sequence[PaginaExtraida]
                       ) -> "collections.Counter":
    """
    Tira o cabeçalho e o rodapé de página da prosa (F109 §5).

    **O sinal é o do livro inteiro, e por isso é uma passada à parte**, no molde
    de `partir_coladas`: o mesmo texto, na mesma margem, em página atrás de
    página. Numa página só o cabeçalho é uma linha curta como outra qualquer.

    A F104 mediu que ele é o maior contribuinte de erro de três dos seis
    livros — não porque seja mal lido, mas porque um erro nele se multiplica
    por centenas de páginas: `Attacking Manual - Volume 1` no alto de toda
    página par. E ele não é prosa: no arquivo exportado não há página, e um
    `Chapter 3` solto a cada trinta linhas é só ruído no meio do texto.

    **Olha a linha impressa, e não o parágrafo.** No Aagaard o cabeçalho
    está colado ao primeiro parágrafo em quase toda página — a régua do
    salto (F103) não o separa —, e uma passada por parágrafo tirava 12 em
    263 páginas. `Paragrafo.inicios` é o que permite achar a primeira linha
    dentro do parágrafo, e `_cortar` a tira com os vetores no mesmo passo.

    Quatro réguas, e a repetição sozinha não basta: a linha tem de estar na
    margem (`MARGEM_DE_PAGINA`), ser curta, ter letra ou número e não ter
    lance — a abertura `1.e4 c5 2.♘f3` que abre três páginas seguidas não é
    cabeçalho. Devolve `{texto: páginas}` do que saiu, e cada página guarda
    o dela em `cabecalhos`.
    """
    vistos: "collections.Counter" = collections.Counter()
    por_pagina = []
    for pagina in paginas:
        candidatos = []
        for margem, p in _nas_margens(pagina):
            inicio, fim = _linha_da_margem(p, margem)
            linha = p.texto[inicio:fim].strip()
            if _candidato_a_cabecalho(linha):
                chave = (margem, _assinatura(linha))
                vistos[chave] += 1
                candidatos.append((chave, p, margem, linha))
        por_pagina.append(candidatos)

    retirados: "collections.Counter" = collections.Counter()
    for pagina, candidatos in zip(paginas, por_pagina):
        for chave, p, margem, linha in candidatos:
            if vistos[chave] < PAGINAS_DE_CABECALHO:
                continue
            # A posição é refeita na hora do corte: o "alto" e o "baixo" do
            # mesmo parágrafo mudam o texto um do outro.
            inicio, fim = _linha_da_margem(p, margem)
            if p.texto[inicio:fim].strip() != linha:
                continue
            if len(p.inicios) <= 1:
                pagina.blocos = [b for b in pagina.blocos if b is not p]
            else:
                _cortar(p, inicio, fim)
            pagina.cabecalhos.append(linha)
            retirados[linha] += 1
    return retirados


def _agrupar_em_paragrafos(linhas: Sequence[Linha],
                           metricas: Optional[dict] = None,
                           lex: Optional["lexico.Lexico"] = None
                           ) -> List[Paragrafo]:
    """
    Linhas → parágrafos.

    Abre parágrafo no recuo da primeira linha, no salto vertical e na troca de
    coluna. As três regras juntas porque nenhuma sozinha cobre este livro: a
    prosa usa recuo, a notação em negrito entre parágrafos usa espaço em branco,
    e nenhuma das duas vê o fim da coluna — lá o salto vertical é **negativo**,
    porque a leitura volta ao topo da página.

    **As duas primeiras medem em passos de linha, e não em alturas de glifo**
    (F103). Era altura de glifo, e com isso o salto abria parágrafo em 99,3% das
    linhas de um livro de 898 páginas — cada linha impressa virava um parágrafo,
    em todos os livros que este projeto já exportou. O porquê está no
    `SALTO_DE_PARAGRAFO`.

    `metricas` vem do `_metricas_por_coluna` da página inteira; sem ela, sai
    destas linhas mesmo, que é o que serve a quem chama com a página toda.

    `lex` desce para o `_paragrafo_de`, que é onde os reparos do dicionário
    acontecem (F115). Sem ele o parágrafo sai como as linhas o escreveram.
    """
    if not linhas:
        return []
    if metricas is None:
        metricas = _metricas_por_coluna(linhas)

    def referencia(grupo: Sequence[Linha]) -> Optional[float]:
        """A altura de glifo da coluna destas linhas — a régua do título."""
        medida = metricas.get(grupo[0].coluna)
        return float(medida[1]) if medida else None

    paragrafos: List[Paragrafo] = []
    atual: List[Linha] = []
    anterior: Optional[Linha] = None
    for linha in linhas:
        altura_solta = linha.altura or 1
        margem, _altura, passo = metricas.get(
            linha.coluna,
            (linha.esquerda, altura_solta,
             max(1, int(altura_solta * PASSO_POR_ALTURA))))
        trocou = anterior is not None and linha.coluna != anterior.coluna
        recuou = linha.esquerda > margem + passo * RECUO_DE_PARAGRAFO
        saltou = (anterior is not None and not trocou
                  and linha.topo - anterior.topo
                  > passo * (1 + SALTO_DE_PARAGRAFO))
        if atual and (recuou or saltou or trocou):
            paragrafos.append(_paragrafo_de(atual, lex, referencia(atual)))
            atual = []
        atual.append(linha)
        anterior = linha
    if atual:
        paragrafos.append(_paragrafo_de(atual, lex, referencia(atual)))
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
        texto, fracos, _p, _l, _c = _texto_da_linha(img, linha, classificar,
                                                conf_minima, coletor, numero)
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

#: Como a leitura do motor contextual entra na linha. Ver `extrair_pagina`.
MODOS_DE_FUSAO = ("palavra", "linha")

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


def _leitura_estavel_do_diagrama(img: np.ndarray, d: Diagrama,
                                 leitura: "diagrama.Leitura"):
    """Recupera uma leitura boa que perdeu o porteiro por uma borda de scan.

    Em páginas com trama, a divisão de uma casa pode cair um ou dois pixels
    fora do tabuleiro e derrubar a confiança de uma única peça/casa vazia.
    Não basta baixar o porteiro: isso aceitaria tabuleiros errados. Aqui a
    leitura original precisa ser plausível, ficar próxima do corte e produzir
    exatamente o mesmo FEN em duas pequenas expansões da borda.
    """
    if not leitura.plausivel:
        return None

    pecas = [c.confianca for c in leitura.casas if c.simbolo]
    ocupacoes = [c.confianca_ocupacao for c in leitura.casas]
    if not pecas or min(min(pecas), min(ocupacoes)) < 0.85:
        return None

    x1, y1, x2, y2 = d.tabuleiro
    delta = max(1, min(4, int(round(min(x2 - x1, y2 - y1) * 0.004))))
    candidatos = [leitura]
    forma = img.shape[:2]
    for sinal in (-1, 1):
        margem = sinal * delta
        caixa = (max(0, x1 + margem), max(0, y1 + margem),
                 min(forma[1], x2 - margem), min(forma[0], y2 - margem))
        alternativa = diagrama.ler(
            img, caixa, orientacao=d.rotulos.orientacao or "branca")
        if alternativa.plausivel:
            candidatos.append(alternativa)

    mesmo_fen = [c for c in candidatos if c.fen() == leitura.fen()]
    if len(mesmo_fen) < 3:
        return None

    def firmeza(c):
        pecas = [p.confianca for p in c.casas if p.simbolo]
        return min(min(pecas, default=0.0),
                   min((p.confianca_ocupacao for p in c.casas), default=0.0))

    return max(mesmo_fen, key=firmeza)


def _figura_do_diagrama(img: np.ndarray, d: Diagrama, *, dpi: int,
                        dpi_figura: int, modo: str, coordenadas, fonte: str,
                        lado: int,
                        moldura=render_diagrama.MOLDURA_PADRAO,
                        cantos: str = render_diagrama.CANTO_PADRAO,
                        cabecalho: str = "") -> Figura:
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

    **O lado a jogar entra no FEN quando a legenda o disser** (item 3 da revisão
    de 2026-09-18). Até aqui o campo saía `w` para todo diagrama, e um FEN abre
    em qualquer programa de xadrez e vira fato: "brancas a jogar" por convenção
    é o tipo de afirmação que ninguém confere e que muda um final inteiro. O que
    está impresso embaixo (`d.legenda`) é lido por `core/lado_a_jogar.py`; o
    cabeçalho de cima é lido pela `figura`, depois, porque só ela tem o texto
    dele. Sem legenda nenhuma, fica a convenção — declarada em `lado_origem`,
    e daí no `alt` e na legenda do arquivo exportado.
    """
    aviso = None
    quer = _quer_coordenadas(coordenadas, d)
    lido = lado_jogar.ler_varios(cabecalho, d.legenda.texto)
    if modo == "render":
        try:
            leitura = diagrama.ler(img, d.tabuleiro,
                                   orientacao=d.rotulos.orientacao or "branca")
            passa, aviso = diagrama.confiavel(leitura)
            if not passa:
                # A borda da digitalização pode deslocar a divisão de uma casa
                # sem alterar a posição. Só aceita a recuperação se as duas
                # expansões repetirem a mesma posição legal.
                estavel = _leitura_estavel_do_diagrama(img, d, leitura)
                if estavel is not None:
                    leitura = estavel
                    passa, aviso = True, ""
            if passa:
                fen = lado_jogar.com_lado(leitura.fen(), lido.lado)
                png, larg, alt = render_diagrama.desenhar(
                    fen, fonte=fonte, lado_px=lado, coordenadas=quer,
                    moldura=moldura, cantos=cantos,
                    orientacao=leitura.orientacao,
                    # O indicador de quem joga só é desenhado quando o livro
                    # **sabe** o lado (ED-05, DEC-06) — e agora ele às vezes
                    # sabe: é o que a legenda disse.
                    lado_a_jogar=lido.lado)
                # As linhas de texto seguem o mesmo critério do desenho (F99):
                # havendo glifo de borda com rótulo, elas saem emolduradas; não
                # havendo, saem as oito de sempre. Decidir aqui, e não na hora
                # de escrever, é o que faz o EPUB e o DOCX concordarem sobre o
                # que a figura é.
                objeto = render_diagrama.carregar(fonte)
                em_grade = (render_diagrama.grade(
                    fen, objeto, leitura.orientacao, moldura, cantos)
                    if quer else None)
                return Figura(png, larg, alt, fen=fen, origem="render",
                              linhas=(em_grade or render_diagrama.linhas(
                                  fen, objeto, leitura.orientacao)),
                              linhas_emolduradas=em_grade is not None,
                              fonte=fonte, coordenadas=quer,
                              orientacao=leitura.orientacao,
                              casas_de_largura=(
                                  larg * 8.0
                                  / render_diagrama.lado_efetivo(lado)),
                              caixa=tuple(int(v) for v in d.tabuleiro),
                              lado_a_jogar=lido.lado,
                              lado_origem=("legenda" if lido else "convencao"))
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
                  casas_de_largura=8.0 * (rect[2] - rect[0]) / na_pagina,
                  caixa=tuple(int(v) for v in d.tabuleiro),
                  lado_a_jogar=lido.lado,
                  lado_origem=("legenda" if lido else "convencao"))


def _ler_linha(img: np.ndarray, linha: Sequence[BoxEntry], classificar: Callable,
               conf_minima: float, coletor, numero: int, *, rotulo, ordem: int,
               roteador: OCRRouter, registros_ocr, usados_ocr: set,
               ler_faixa: Optional[Callable], fusao: str, idioma_ocr: str):
    """Uma linha lida pela cadeia própria e, quando o roteador manda, pelo motor.

    É o corpo do laço de `extrair_pagina`, e saiu dele para a célula da
    tabela passar pelo mesmo caminho (`_tabela_da_pagina`, `leitor`): a
    cadeia lê `W:Win(1 ♖e1!)` e `W:W1n(1 ♖d1!)` nas células do Nunn, e o
    motor tem `W:`, `Win` e `(1` a 0,9 no mesmo lugar. Devolve `(texto,
    derrubados, pesos, lacunas, caixas, origem, domínio, registro)` — o
    registro é o do roteamento, sem o `texto` final, que quem chama ainda
    pode mudar (fragmento, correção direta, reparo de colagem).

    `rotulo` identifica a região no roteador (`l3` na página, `t1c2l0` na
    tabela — fila, coluna e linha da célula); `ordem` é a posição de leitura,
    e é o `linha` do registro.
    """
    glifos_linha: List[Tuple[int, float, str]] = []
    texto, n, pesos, vaos, caixas = _texto_da_linha(
        img, linha, classificar, conf_minima, coletor, numero,
        lambda posicao, centro_x, glifo: glifos_linha.append(
            (posicao, centro_x, glifo)))
    texto, pesos, vaos, caixas = _colar_numero_de_lance(texto, pesos, vaos, caixas)
    texto, pesos, vaos, caixas = _partir_prosa_colada_ao_lance(
        texto, pesos, vaos, caixas)
    ancora = texto
    # O roteador da OCR-11 decide pelo domínio da âncora: a linha só de
    # lances fica com a cadeia própria e nem paga o motor; a de prosa ou
    # mista vai para a fusão. A de domínio desconhecido só paga o motor
    # quando a âncora está fraca — perdeu caractere por confiança —, que é
    # a regra do `HybridOCRPipeline` para o mesmo caso.
    dominio = _dominio_da_linha(texto)
    decisao_bbox = (min(b.x1 for b in linha), min(b.y1 for b in linha),
                    max(b.x2 for b in linha), max(b.y2 for b in linha))
    decisao = roteador.decide(RegionResult(
        id=f"p{numero}-{rotulo}",
        type=TIPO_DE_REGIAO_POR_DOMINIO[dominio], order=ordem,
        confidence=1.0, bbox=decisao_bbox))
    quer_contexto = (decisao.primary == "line"
                     or (dominio == "unknown" and n > 0))
    # A linha só de lances não troca nada pelo motor, mas o box que a
    # cadeia derrubou dentro de um lance é preenchido pelo que o motor
    # leu ali (`_fundir_por_palavra(so_lacunas=True)`) — só quando há
    # box derrubado, e só com o registro que a página já tem.
    so_lacunas = (not quer_contexto and dominio == "notation" and n > 0
                  and fusao == "palavra")
    origem = "glyph"
    texto_ocr, confianca_ocr, semelhanca = "", 0.0, None
    detalhes_ocr: tuple = ()
    estatisticas: dict = {}
    compativel = trama = False
    # A linha em negativo não usa o registro da página: o motor leu a
    # faixa preta como estava, e o que saiu é fraco ou errado. Ela vai
    # direto para a faixa invertida, abaixo.
    negativa = any(getattr(b, "negativo", False) for b in linha)
    casamento = (_casar_linha_ocr(linha, registros_ocr, usados_ocr)
                 if registros_ocr and not negativa else None)
    if casamento is not None:
        indice_ocr, texto_ocr, confianca_ocr = casamento
        detalhes_ocr = (registros_ocr[indice_ocr][3]
                        if len(registros_ocr[indice_ocr]) > 3 else ())
        semelhanca, compativel = _compatibilidade_da_linha(
            texto, texto_ocr, confianca_ocr, detalhes_ocr, fusao)
        if (quer_contexto or so_lacunas) and compativel:
            # O registro só é consumido quando é aceito: o rejeitado pode
            # ser a linha de baixo — o Tesseract às vezes devolve duas
            # linhas impressas num registro só, e ele casa primeiro com a
            # de cima, que o recusa pela semelhança.
            usados_ocr.add(indice_ocr)
    if quer_contexto and not compativel and ler_faixa is not None:
        # A passada de página não devolveu esta linha (ou devolveu a
        # errada): o motor lê a faixa dela sozinha. Só aqui, e não em toda
        # linha, porque é uma chamada de processo por faixa.
        faixa = _registro_da_faixa(img, linha, ler_faixa)
        if faixa is not None:
            texto_ocr, confianca_ocr, detalhes_ocr, trama = faixa
            semelhanca, compativel = _compatibilidade_da_linha(
                texto, texto_ocr, confianca_ocr, detalhes_ocr, fusao,
                trama=trama)
            estatisticas["faixa"] = True
    elif (quer_contexto and compativel and fusao == "palavra"
            and any(_lance_sem_casa(t) for t in texto.split())):
        # O registro veio da passada de página, e a âncora tem a figurina
        # sem casa: se a linha está sobre trama, ela é um ponto — e é a
        # única coisa que a trama muda na fusão, então só se mede aqui.
        trama = _linha_sobre_trama(img, linha)
    if trama:
        estatisticas["trama"] = True
    if so_lacunas and compativel and detalhes_ocr:
        novo_texto, contas = _fundir_por_palavra(
            texto, caixas, linha, detalhes_ocr, so_lacunas=True)
        estatisticas.update(contas)
        if novo_texto and novo_texto != texto:
            pesos, vaos = _transferir_medidas(texto, novo_texto, pesos, vaos)
            texto = novo_texto
            origem = "lacunas"
    elif quer_contexto and compativel:
        if fusao == "palavra" and detalhes_ocr:
            novo_texto, contas = _fundir_por_palavra(
                texto, caixas, linha, detalhes_ocr, trama=trama)
            estatisticas.update(contas)
            origem = "fusao"
        else:
            # Sem as palavras do motor (um `ler_pagina` sem detalhes) só
            # dá para trocar a linha inteira.
            novo_texto = _preservar_glifos_por_palavra(
                texto, texto_ocr, glifos_linha, detalhes_ocr)
            origem = "line"
        if novo_texto:
            novo_texto = _corrigir_prosa_contextual(novo_texto, idioma_ocr)
            pesos, vaos = _transferir_medidas(texto, novo_texto,
                                               pesos, vaos)
            texto = novo_texto
        else:
            origem = "glyph"
    # A `caixa` é a da linha na página (pixels da imagem lida): é por ela
    # que a fila de revisão recorta a linha para mostrar ao lado das duas
    # leituras — o registro sem ela dizia o que foi lido, e não onde.
    registro = {"linha": ordem, "dominio": dominio,
                "primario": decisao.primary, "motivo": decisao.reason,
                "fonte": origem, "ancora": ancora, "linha_ocr": texto_ocr,
                "confianca_ocr": confianca_ocr, "semelhanca": semelhanca,
                "descartados": n, "caixa": [int(v) for v in decisao_bbox],
                **estatisticas}
    return texto, n, pesos, vaos, caixas, origem, dominio, registro


def extrair_pagina(page: fitz.Page, classificar: Callable, *, numero: int = 0,
                   dpi: int = 300, conf_minima: float = CONF_MINIMA,
                   dpi_figura: int = DPI_FIGURA,
                   coletor: Optional[Callable] = None,
                   ler_pagina: Optional[Callable] = None,
                   ler_faixa: Optional[Callable] = None,
                   idioma_ocr: str = "en",
                   fusao: str = "palavra",
                   diagramas: str = "render", coordenadas=False,
                   fonte: str = render_diagrama.FONTE_PADRAO,
                   lado_do_diagrama: int = render_diagrama.LADO_PADRAO,
                   moldura=render_diagrama.MOLDURA_PADRAO,
                   cantos: str = render_diagrama.CANTO_PADRAO,
                   lex: Optional["lexico.Lexico"] = None,
                   probabilidade: Optional[Callable] = None
                   ) -> PaginaExtraida:
    """
    Uma página do PDF vira parágrafos e figuras, lendo só a imagem.

    `ler_pagina(img)` é o motor contextual — o Tesseract de página inteira,
    uma chamada por página —, e `fusao` diz como a leitura dele entra na
    linha: `"palavra"` (o padrão) guarda o lance da âncora e toma a prosa do
    motor, token a token; `"linha"` é o modo anterior, em que a linha inteira
    do motor substituía a âncora e as figurinas eram repostas por coordenada.
    O segundo existe para o A/B medir o primeiro contra ele. Sem `ler_pagina`
    a página é lida só pela cadeia própria, que é o modo de antes dos dois.
    `ler_faixa(faixa)` é o fallback para a linha que a passada de página não
    devolveu: lê a faixa dela sozinha, e só dela.

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

    `probabilidade(recorte, char) -> float` liga o reparo de colagem da F66/F69
    (`_reparar_texto`). **Sem ele o reparo não acontece, e é de propósito:** a
    F66 mediu 62,5% de precisão quando o comprimento decide sozinho, e recusou
    ligar por isso. Quem autoriza a troca é a prova visual, e ela precisa
    perguntar ao modelo quanto ele dá a uma letra num pedaço de papel — que é
    uma pergunta que o `classificar` desta função não responde.
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
    if fusao not in MODOS_DE_FUSAO:
        raise ValueError(f"modo de fusão inválido: {fusao!r} "
                         f"(use um de {MODOS_DE_FUSAO})")

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

    # **A régua do box largo e a prova visual são da página inteira**, e por
    # isso saem daqui e não de dentro da linha: `_largura_de_referencia` mede a
    # largura de caractere linha a linha mas precisa da página para o piso, e a
    # prova indexa os boxes da página. Montadas uma vez por página, e não uma
    # vez por palavra — a memória do `prova_de_reparo` é o que torna a fase
    # pagável (F69).
    posicao = {id(b): i for i, b in enumerate(boxes)}
    largos, provar = set(), None
    if lex is not None and lex.sinaliza and probabilidade is not None:
        largos = lexico.boxes_largos(boxes)
        if largos:
            provar = BoxService.prova_de_reparo(img, boxes, probabilidade)

    # O Tesseract (ou outro motor contextual) é chamado uma vez por página,
    # nunca uma vez por caractere. O resultado traz coordenadas e fica restrito
    # à linha que realmente cobre os boxes internos.
    #
    # O OCR contextual é uma melhoria opcional: se o executável ou o idioma
    # não estiver instalado, a rede especializada continua produzindo o livro
    # normalmente. **Mas a falha fica registrada** (`falhas_do_motor`): até
    # aqui ela virava `[]` em silêncio, e a página sem motor era idêntica a
    # uma página em que o motor não leu nada. Depois da primeira
    # indisponibilidade a faixa deixa de ser pedida — o motor que não abriu
    # a página não vai abrir a faixa, e são uma chamada de processo por linha.
    falhas_do_motor: List[str] = []
    registros_ocr = []
    if ler_pagina is not None:
        try:
            registros_ocr = list(ler_pagina(img) or [])
        except Exception as erro:  # noqa: BLE001 — registrada, e a página segue
            falhas_do_motor.append(f"página: {erro}")
            registros_ocr = []
    if ler_faixa is not None:
        ler_faixa = _ler_faixa_registrando(ler_faixa, falhas_do_motor)
    usados_ocr: set[int] = set()

    fracos = reparos = 0
    roteador = OCRRouter()
    roteamento: List[dict] = []

    def ler_celula(sub: Sequence[BoxEntry], rotulo: str) -> Tuple[str, int]:
        """A linha de uma célula da tabela, pelo mesmo caminho da linha de
        prosa: cadeia, roteador e motor. Sem a régua de fragmento — a célula
        é curta por natureza (`W:`, `Draw`) — e sem o reparo de colagem, que
        é do texto corrido."""
        texto, n, _pesos, _vaos, _caixas, origem, dominio, registro = _ler_linha(
            img, sub, classificar, conf_minima, coletor, numero,
            rotulo=rotulo, ordem=len(roteamento), roteador=roteador,
            registros_ocr=registros_ocr, usados_ocr=usados_ocr,
            ler_faixa=ler_faixa, fusao=fusao, idioma_ocr=idioma_ocr)
        if origem == "glyph" and dominio != "notation":
            texto = _corrigir_prosa_contextual(texto, idioma_ocr, fuzzy=False)
        roteamento.append({**registro, "texto": texto, "celula": rotulo})
        return texto, n

    # A tabela sai da página antes das linhas: as células dela não são linhas de
    # prosa, e deixá-las virar parágrafo é o defeito que a F72 fecha. As
    # células passam pelo motor como as linhas (`ler_celula`), e consomem os
    # registros da página que são delas antes de qualquer linha olhar para
    # eles.
    achado = _tabela_da_pagina(img, boxes, classificar, conf_minima, coletor,
                               numero, leitor=ler_celula)
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
    for indice_linha, linha in enumerate(quebrar_em_linhas(boxes)):
        (texto, n, pesos, vaos, caixas, origem, dominio,
         registro) = _ler_linha(
            img, linha, classificar, conf_minima, coletor, numero,
            rotulo=f"l{indice_linha}", ordem=indice_linha, roteador=roteador,
            registros_ocr=registros_ocr, usados_ocr=usados_ocr,
            ler_faixa=ler_faixa, fusao=fusao, idioma_ocr=idioma_ocr)
        fracos += n
        if origem == "glyph":
            # A sobra curta do detector que o motor já cobriu inteira não vira
            # linha. E a linha que ficou com a cadeia própria recebe só as
            # trocas diretas — a de notação, nem essas: é o caminho de antes.
            if _parece_fragmento_ocr(linha, texto, registros_ocr):
                roteamento.append({**registro, "fragmento": True, "texto": ""})
                continue
            if dominio != "notation":
                texto = _corrigir_prosa_contextual(texto, idioma_ocr, fuzzy=False)
        if provar is not None and texto and origem == "glyph":
            # O índice do box passa a ser o da **página**, que é onde a régua do
            # box largo e a prova visual falam (`boxes_largos`,
            # `prova_de_reparo`); o `_texto_da_linha` só conhece a linha.
            texto, pesos, vaos, n_reparos = _reparar_texto(
                texto, pesos, vaos,
                [posicao[id(linha[c])] if c >= 0 else -1 for c in caixas],
                largos, lex, provar)
            reparos += n_reparos
        # **O dicionário deixou de entrar aqui, e subiu para o parágrafo**
        # (F115). A F108 o ligou nesta linha, e era o lugar certo enquanto o
        # único reparo era a caixa: a correção preserva o comprimento, e as
        # fatias de negrito da F105 continuavam apontando para o mesmo
        # caractere. O que a linha não tem é a palavra que o hífen partiu no fim
        # dela — o próprio comentário de lá dizia que ela ficava de fora —, e
        # `juntar_hifenizadas` precisa das duas metades ao mesmo tempo. Ver
        # `_paragrafo_de`, que faz os três reparos com os dois vetores ao lado,
        # um passo acima.
        roteamento.append({**registro, "texto": texto})
        if texto:
            medidas.append(Linha(
                topo=min(b.y1 for b in linha),
                esquerda=min(b.x1 for b in linha),
                altura=int(np.median([b.y2 - b.y1 for b in linha])),
                texto=texto,
                coluna=_coluna_de((min(b.x1 for b in linha)
                                   + max(b.x2 for b in linha)) / 2, colunas),
                pesos=pesos, lacunas=vaos, dominio=dominio, fonte=origem,
                registro=len(roteamento) - 1))

    resultado = PaginaExtraida(numero=numero, diagramas=len(tabuleiros),
                               respingos_descartados=respingos,
                               descartados_por_confianca=fracos,
                               colunas=len(colunas), reparos=reparos,
                               altura=int(img.shape[0]),
                               largura=int(img.shape[1]), dpi=int(dpi),
                               roteamento=roteamento,
                               motor_indisponivel="; ".join(falhas_do_motor))

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
        # O cabeçalho é lido **antes** do desenho, e não depois como na F67:
        # ele é um dos dois lugares em que o livro diz de quem é a vez, e o
        # indicador de lado faz parte do desenho (item 3 da revisão de
        # 2026-09-18). O preço é ler a faixa também no caso em que ela já sai
        # dentro do recorte — meia dúzia de caixas, e ali não há FEN nenhum
        # para o lado entrar.
        cabecalho = (_faixa_em_texto(img, d, classificar, conf_minima, coletor,
                                     numero)
                     if d.faixa is not None else None)
        principal = _figura_do_diagrama(img, d, dpi=dpi, dpi_figura=dpi_figura,
                                        modo=diagramas, coordenadas=coordenadas,
                                        fonte=fonte, lado=lado_do_diagrama,
                                        moldura=moldura, cantos=cantos,
                                        cabecalho=(cabecalho.texto if cabecalho
                                                   else ""))
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
            resultado.blocos.extend(_agrupar_em_paragrafos(corrente, metricas, lex))
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
        resultado.blocos.extend(_agrupar_em_paragrafos(corrente, metricas, lex))
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
    resultado.blocos.extend(_agrupar_em_paragrafos(corrente, metricas, lex))
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
    _confirmar_titulos(resultado)
    # **Antes do negrito, e não depois** (F115): o corte acrescenta um espaço no
    # meio do parágrafo, e é o negrito que tem de ver o texto final — ele mede
    # palavra a palavra, e uma palavra que se parte em duas passa a ser medida
    # como duas.
    partir_coladas([resultado], lex)
    # O negrito, com esta página por referência (F105). Quem lê o livro inteiro
    # remarca no fim, e acerta 6,5 pontos a mais — ver `negrito.marcar`.
    negrito.marcar([resultado])
    return resultado


#: Palavras que só um dos dois idiomas escreve, para `idioma_do_pdf`.
#:
#: Curtas e frequentes, e **nenhuma dos dois lados**: `a` e `as` são artigo em
#: português e palavra comum em inglês, e ficaram de fora por isso. Bastam
#: porque a pergunta é grosseira — o livro é de um idioma só, e o texto de
#: quarenta páginas responde por centenas de ocorrências.
PALAVRAS_DE_IDIOMA = {
    "en": frozenset("the and of to is with that this white black it on by "
                    "after not for".split()),
    "pt": frozenset("de que o e os com não para um uma das dos mais também "
                    "ou brancas pretas".split()),
}

#: Ocorrências abaixo das quais `idioma_do_pdf` não responde.
OCORRENCIAS_DE_IDIOMA = 50

#: Quantas vezes o idioma vencedor tem de bater o outro.
VANTAGEM_DE_IDIOMA = 3.0


def titulo_e_autor(caminho: str) -> Tuple[str, str]:
    """
    `(título, autor)` do livro, para o `dc:title`/`dc:creator` e o DOCX (F111).

    **Os metadados do PDF vêm primeiro, e quase nunca prestam**: dos oito
    livros do corpus, um traz os dois campos, um traz `cipun` como autor, e
    seis não trazem nada. O nome do arquivo é a segunda fonte, e nestes
    livros ele segue `Autor - Título`; quando não segue, o título é o nome e
    o autor fica vazio — vazio e não `python-docx`, que é o que o DOCX
    escrevia.
    """
    titulo = autor = ""
    try:
        doc = fitz.open(caminho)
        try:
            meta = doc.metadata or {}
        finally:
            doc.close()
        titulo = (meta.get("title") or "").strip()
        autor = (meta.get("author") or "").strip()
    except Exception:                                    # noqa: BLE001
        pass
    # Um autor sem espaço e sem maiúscula é o `cipun` do Nunn: não é nome.
    if autor and " " not in autor and autor.islower():
        autor = ""
    nome = os.path.splitext(os.path.basename(caminho))[0]
    if not titulo:
        antes, sep, depois = nome.partition(" - ")
        if sep and antes.strip() and depois.strip():
            titulo, autor = depois.strip(), autor or antes.strip()
        else:
            titulo = nome
    return titulo, autor


def idioma_do_pdf(caminho: str, paginas: int = 40) -> Optional[str]:
    """
    `"en"`, `"pt"`, ou `None` quando a camada de texto do PDF não diz (F109).

    **Lê a camada de texto, e não a imagem**, porque é barato e porque está lá
    em 72% das páginas do corpus (F110). Onde não está — o Seirawan e o
    Razuvaev, que são digitalizações de verdade — sai `None`, e quem chama
    pergunta ao usuário. Nunca chuta: o idioma liga a máscara de alfabeto
    (`core.alfabeto`), e a máscara errada apaga o `ç` de um livro inteiro.

    As páginas são espalhadas pelo livro, e não as primeiras: as primeiras são
    o frontispício e o sumário, que num livro traduzido ainda trazem o nome
    original.
    """
    doc = fitz.open(caminho)
    try:
        total = len(doc)
        passo = max(1, total // max(1, paginas))
        conta: "collections.Counter" = collections.Counter()
        for numero in range(0, total, passo):
            texto = doc[numero].get_text().lower()
            for palavra in re.findall(r"[a-záàâãéêíóôõúüç]+", texto):
                for idioma, lista in PALAVRAS_DE_IDIOMA.items():
                    if palavra in lista:
                        conta[idioma] += 1
    finally:
        doc.close()
    if sum(conta.values()) < OCORRENCIAS_DE_IDIOMA:
        return None
    # Um PDF escaneado pode não ter nenhuma palavra reconhecível. Ainda assim
    # a detecção precisa devolver ``None`` para que a UI pergunte o idioma,
    # em vez de tentar desempacotar uma lista curta e levantar IndexError.
    (primeiro, n1), (_segundo, n2) = (
        conta.most_common(2) + [("", 0), ("", 0)]
    )[:2]
    return primeiro if n1 >= VANTAGEM_DE_IDIOMA * max(1, n2) else None


def extrair(input_pdf: str, classificar: Callable, *, dpi: int = 300,
            paginas: Optional[Sequence[int]] = None,
            conf_minima: float = CONF_MINIMA, dpi_figura: int = DPI_FIGURA,
            coletor: Optional[Callable] = None,
            ler_pagina: Optional[Callable] = None,
            ler_faixa: Optional[Callable] = None,
            idioma_ocr: str = "en",
            fusao: str = "palavra",
            diagramas: str = "render", coordenadas=False,
            fonte: str = render_diagrama.FONTE_PADRAO,
            lado_do_diagrama: int = render_diagrama.LADO_PADRAO,
            moldura=render_diagrama.MOLDURA_PADRAO,
            cantos: str = render_diagrama.CANTO_PADRAO,
            lex: Optional["lexico.Lexico"] = None,
            probabilidade: Optional[Callable] = None,
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
                                        ler_pagina=ler_pagina,
                                        ler_faixa=ler_faixa,
                                        idioma_ocr=idioma_ocr,
                                        fusao=fusao,
                                        diagramas=diagramas,
                                        coordenadas=coordenadas, fonte=fonte,
                                        lado_do_diagrama=lado_do_diagrama,
                                        moldura=moldura, cantos=cantos,
                                        lex=lex,
                                        probabilidade=probabilidade))
        if progress_callback:
            progress_callback(len(numeros), len(numeros))
        # **O cabeçalho de página sai antes de tudo** (F109): ele não é prosa,
        # e o que vem depois — o vocabulário do livro, o negrito — mede-se
        # sobre a prosa. Só o livro inteiro o reconhece, e é por isso que ele
        # não sai no `extrair_pagina`.
        retirar_cabecalhos(saida)
        # **Repartido com o livro inteiro por vocabulário** (F115), pela mesma
        # razão que o negrito é remarcado logo abaixo: o portão que decide se
        # `of`+`positions` pode ser um corte é "estas duas palavras existem
        # neste livro", e numa página só quase nada existe duas vezes. Também é
        # idempotente — o que já foi partido está no dicionário, e a primeira
        # condição de `partir_colada` o recusa.
        partir_coladas(saida, lex)
        # **Remarcado com o livro inteiro por referência** (F105). Cada página
        # já saiu marcada contra si mesma, que é o melhor que dá para fazer
        # quando só há uma; com todas, o peso redondo de cada caractere é
        # estimado sobre muito mais texto, e a marcação passa de 90,2% para
        # 96,7% de acerto. A marcação é idempotente — esta é a que vale.
        negrito.marcar(saida)
        return saida
    finally:
        doc.close()
