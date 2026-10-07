"""
O modelo da página lida: `Paragrafo`, `Figura`, `Tabela`, `Bloco` e `PaginaExtraida`.

É o intermediário entre quem lê e quem escreve. Quem lê — `core/livro.py` da imagem,
`core/pdf_nativo.py` da camada de texto do PDF — devolve uma lista de `PaginaExtraida`;
quem escreve — `core/exportar.py`, `core/editorial_adapters.py` (a ida ao documento
editorial e a volta), `core/editor/importar_ir.py` — só precisa deste módulo. Até
2026-10-06 as classes moravam dentro de `livro.py`, e `pdf_nativo` importava o leitor
inteiro para ter o tipo de retorno: era metade do ciclo `livro` ↔ `pdf_nativo` (item 6
da análise geral). `livro.Paragrafo`, `livro.PaginaExtraida` e os outros nomes continuam
valendo: `livro.py` os re-exporta, e são o mesmo objeto.
"""
from __future__ import annotations

from array import array
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union


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
    #: Os trechos em itálico, do mesmo jeito (PD-06). Hoje só a camada de texto
    #: do PDF os preenche (`pdf_nativo`, pela bandeira e pelo nome da fonte):
    #: no OCR não há régua de inclinação medida, e marcar sem régua seria
    #: inventar ênfase.
    italico: List[Tuple[int, int]] = field(default_factory=list)
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
    #: As casas que o livro marcou no diagrama (`"c6"`), quando se sabe (F110):
    #: o `x` das casas-chave do Dvoretsky, que a fonte de diagrama compõe como
    #: glifo. Saem no desenho como anel (`render_diagrama.desenhar(marcas=)`),
    #: e é daqui que quem redesenha a figura as tira — sem isto, redesenhar
    #: para pôr o indicador de lado apagaria a marca.
    marcas: List[str] = field(default_factory=list)


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

    **A célula de duas linhas leva o `\n` entre elas** (PD-03): `W: Win (1 ♖e1!)`
    e `B: Draw (1...♖a2!)` são duas linhas no papel, e numa tabela de frases
    independentes juntá-las com espaço faria de duas uma. O EPUB escreve
    `<br/>`, o DOCX uma quebra de linha no run, e o texto corrido da página
    (`PaginaExtraida.texto`) volta ao espaço — é dele que saem o alfabeto dos
    símbolos e a régua do corpus, e para os dois a quebra não diz nada.
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
    #: Por onde a página foi lida (F110): `"imagem"` é o OCR deste módulo, e
    #: `"camada"` é o texto que o próprio PDF traz (`core/pdf_nativo.py`). A
    #: página da camada não tem box nem confiança por glifo, e por isso não
    #: alimenta a coleta nem a fila de revisão — o relatório da exportação
    #: conta quantas vieram de cada caminho, para isso não acontecer calado.
    leitura: str = "imagem"

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
                partes.extend(" ".join(c.replace("\n", " ") for c in fila)
                              for fila in b.linhas)
        return "\n\n".join(partes)
