"""
Do diagrama impresso para uma posição de xadrez (F7.1).

## Onde os diagramas já estavam

Não foi preciso procurá-los. A F1.8 descarta contornos grandes demais para
serem caractere, e o tabuleiro sai como **um** contorno só — ele tem moldura
fechada e `findContours` roda com `RETR_EXTERNAL`, então as 64 casas e as peças
são contornos filhos e não são devolvidos. Nas 9 páginas rotuladas isso rende 25
diagramas, quadrados de ~480x479 px. `localizar` só recolhe o que a F1.8 já
jogava fora.

## A grade

Dividir o recorte por 8 basta, e isso foi verificado, não suposto: o padrão de
cores do tabuleiro é conhecido de antemão — a casa (linha+coluna) par é clara —
e nos 25 diagramas o padrão observado bate com o esperado. Uma grade deslocada
quebraria esse xadrez imediatamente.

## Vazia ou ocupada — a decisão que vem antes de tudo

Era um limiar de Otsu sobre a "força" do resíduo, por diagrama e por cor de
casa. **Era o gargalo da leitura, e por seis anos não havia número que o
dissesse** — os 94,5% da F7.1 misturavam esta decisão com a identificação da
peça, e a F7.4 melhorou só a segunda.

A F7.5 transcreveu à mão as 1.600 casas dos 25 diagramas rotulados
(`tests/dados/ocupacao_diagramas.txt`) e mediu:

| decisão | omissões | falsos+ | acerto |
|---|---:|---:|---:|
| Otsu (F7.1) | 86 | 38 | 92,25% |
| melhor limiar possível, com o gabarito na mão | — | — | 98,25% |
| rede dedicada | 6 | 5 | **99,31%** |

A linha do meio é a que mandou trocar de abordagem em vez de afinar a que havia.
Ver `ocupadas`.

## O fundo, e por que a leitura é do resíduo

A casa pode ser clara ou escura, e **escura tem dois desenhos diferentes** nestes
livros: cinza chapado num, hachura diagonal no outro. Medir tom absoluto não
serve — a moda de uma casa hachurada é branca, e os quatro diagramas hachurados
saíam com "zero casas escuras".

O que resolve: para cada diagrama e cada cor de casa, o fundo é a **mediana
pixel a pixel** das 32 casas daquela cor. As vazias são maioria, então a mediana
*é* a casa vazia — chapada ou hachurada, tanto faz. A peça é o que sobra
(`casa - fundo`), e é sobre esse resíduo que tudo mais trabalha. O modelo é
refeito uma segunda vez usando só as casas julgadas vazias, porque a primeira
mediana inclui ~40% de peças.

## A classificação

Uma rede convolucional pequena sobre o resíduo (`core.neural_model.RedeDiagrama`),
treinada nas amostras rotuladas de `training_data_diagrama/`. Ver
`core/treino_diagrama.py`.

**Era HOG + PCA para 32 dimensões + voto dos 3 vizinhos mais próximos, e a troca
foi medida (F7.4).** Deixando um livro inteiro de fora do treino — que é a
pergunta que o programa faz na prática, "abro um PDF novo, ele lê?":

| protocolo | k-NN (antes) | rede |
|---|---:|---:|
| leave-one-out solto | 93,5% | — |
| 5 folds agrupados por diagrama | 93,8% | 98,8% |
| **um livro inteiro de fora** | **86,9%** | **98,0%** |

A vantagem da rede **cresce** no teste difícil, que é o contrário do que se veria
se fosse sobreajuste. E o gargalo não era o PCA: com 256 componentes, ou sem PCA
nenhuma sobre o HOG cru e um vizinho só, o melhor que o k-NN faz num livro novo
é 89,2%. O que ele errava eram as peças de desenho detalhado — dama 80,8%,
cavalo 83,7% —, exatamente o que uma silhueta de gradientes borra.

**Duas correções que pareciam óbvias e pioraram**, medidas na época do k-NN
contra 128 casas transcritas à mão:

| variante | acerto por casa |
|---|---:|
| resíduo + HOG | **94,5%** |
| \\+ canal de sinal para a cor da peça | 90,6% |
| detecção por energia de borda | 93,0% |

A primeira parecia certa: o HOG usa orientação módulo 180 e magnitude absoluta,
logo descarta o sinal, e torre branca virava torre preta. Dar-lhe o sinal por
fora **subiu** os erros de cor de 3 para 5. A segunda também: peça branca em casa
clara quase some no resíduo (é branca por dentro, traço fino em volta) e a borda
a acha — mas troca 3 omissões por 4 falsos positivos.

A segunda apontava para o limite da F7.4 — **a rede das peças só decide qual
peça é, não se a casa está ocupada** —, e é justamente o que a F7.5 foi
atacar. As omissões que ela descreve saíram de 86 para 6.

## A legalidade arbitra, como na F1.7

Uma posição de xadrez real tem exatamente um rei de cada cor, no máximo oito
peões por lado, nenhum peão na 1a ou 8a fila e no máximo dezesseis peças por
cor. São restrições sobre a posição **inteira**, mais fortes que as da F1.7 —
que valiam para um lance de cada vez.

`_arbitrar` troca a leitura da casa que custa menos: a de menor diferença entre a
pontuação da leitura atual e a da leitura que resolve o problema. Medido, leva de
17 para 23 os 25 diagramas cuja posição é possível.

## O que este módulo NÃO entrega

**Continua sendo um rascunho para conferir.** As duas redes cobrem as duas
perguntas de dentro do tabuleiro — 99,3% de ocupação e 98,0% de identidade, cada
uma medida em diagramas que ficaram fora do treino —, mas a localização do
tabuleiro na página erra por conta própria, e um livro novo traz fonte nova de
peças. A interface tem de mostrar assim, do mesmo jeito que a F3.6 mostra o lote
antes de aplicar.

Passar nas provas de legalidade **não é prova de estar certo**: elas contam
peças, não reconhecem bispo lido como peão. Por isso o número que vale é o de
casas transcritas à mão, e não os 25/25.

Lado a jogar, roque e en passant **não estão no diagrama** e não são deduzíveis
dele. `fen()` assume brancas a jogar, sem roque e sem en passant, e diz isso.

## Onde os diagramas **não** estavam (F95)

A premissa do topo — "o tabuleiro sai como um contorno só" — vale enquanto ele
for contorno **externo**. Ele deixa de ser quando o livro o imprime dentro de
outra coisa: a página 199 do Yusupov põe os dois diagramas do capítulo num
painel sombreado que atravessa a coluna inteira, e com `RETR_EXTERNAL` o painel
é o contorno e os tabuleiros são filhos dele. Não há o que descartar, então não
há o que `localizar` recolha: **2 diagramas impressos, 0 achados**, e o comando
respondia "nenhum diagrama encontrado" com o mesmo texto de sempre.

A segunda passada (`_aninhados`) refaz os contornos com `RETR_LIST`, que
devolve os de dentro também, e peneira com duas provas independentes:

    preenchimento  área do contorno / área da caixa >= 0,90
    xadrez         as casas pares são mais claras que as ímpares

Medido em 21 páginas de 5 livros: recupera os 2 da página 199 e **não inventa
nenhum** nas outras 20. Custa de 0,01 a 0,10 s por página. As duas provas fazem
falta juntas: os contornos-escada de dentro do próprio tabuleiro passam no
xadrez (42,3 no melhor deles, contra 30,9 do tabuleiro inteiro) e reprovam no
preenchimento por larga margem — 0,20 a 0,43 contra 0,96.

## O que está impresso em volta (F95)

O tabuleiro não é a única tinta do diagrama, e o que sobra tem dois nomes:

- **os rótulos** `a`–`h` e `8`–`1`, quando o livro os imprime. Ver `ler_rotulos`;
- **o título**, que num livro fica acima (`➤ Ex. 22-4 ◀ ★★ ▼`, no Yusupov) e
  noutro abaixo (`144`, no Nunn). Ver `ler_titulo`.

Os dois existem porque o arquivo exportado precisa **escolher**, e até aqui não
tinha com o que: `livro.extrair` recebia `coordenadas=True|False` para o livro
inteiro, sem saber o que o livro trazia. Com `ler_rotulos` a escolha passa a
poder ser "como está impresso".

E os rótulos respondem uma pergunta que nada mais respondia: **para que lado o
tabuleiro está virado**. `ler` sempre supôs brancas embaixo; um diagrama
impresso do lado das pretas saía com o FEN girado 180°, plausível e errado.
"""

import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import chess
import cv2
import numpy as np

from core.box_model import BoxEntry


#: Lado do recorte normalizado de uma casa.
LADO = 48

#: Proporção máxima entre largura e altura para um contorno ser tabuleiro.
#: Medido: os 25 diagramas ficam entre 1,000 e 1,008.
TOLERANCIA_QUADRADO = 1.12

#: Menor lado aceito, em múltiplos da altura mediana de caractere da página.
#: Os diagramas medidos têm ~480 px contra ~19 px de caractere, isto é, 25x.
MINIMO_EM_CARACTERES = 6.0

#: Lado da entrada da rede. Menor que `LADO` de propósito: a amostra é gravada
#: em 48 px para poder ser olhada, e a rede lê 32 — foi o tamanho medido.
LADO_REDE = 32

#: Quanto da casa forma o anel de fundo que `pontuacao_de_tabuleiro` mede (F95).
#:
#: **É anel, e não a casa inteira, porque a peça mora no meio.** Um tabuleiro
#: cheio tem peça em quase metade das casas, e a tinta delas some com a
#: diferença entre casa clara e escura — que é justamente o que se quer medir.
#: A moldura da casa é fundo em toda casa, ocupada ou não.
ANEL_DA_CASA = 0.2

#: Abaixo disto o recorte não é tabuleiro (F95).
#:
#: A pontuação é a diferença de tinta entre as 32 casas ímpares e as 32 pares,
#: em níveis de cinza. Medida em 49 tabuleiros de 5 livros e em 5 recortes de
#: texto do mesmo tamanho:
#:
#:     origem                          menor   maior
#:     tabuleiro, hachurado (Nunn)      19,7    38,3
#:     tabuleiro, hachurado (Dvorets.)  20,2    22,8
#:     tabuleiro, chapado (Yusupov)     36,0    46,2
#:     tabuleiro, chapado (Aagaard)     32,9    44,2
#:     tabuleiro, chapado (Darcy)       92,2   124,3
#:     **recorte de texto**            **-1,1**  **3,1**
#:
#: O vão entre 3,1 e 19,7 é de seis vezes, e o corte fica no meio dele em
#: escala logarítmica. Não é um limiar afinado: é um vão.
PISO_DO_XADREZ = 12.0

#: Quanto da caixa o contorno precisa encher para ser candidato a tabuleiro
#: numa página em que ele não é contorno externo (F95).
#:
#: Um tabuleiro com moldura fechada é um borrão cheio: o contorno é o filete de
#: fora, e ele encerra as 64 casas. Os contornos-escada que as casas escuras
#: formam por dentro encerram um quinto disto. Medido nos dois diagramas da
#: página 199 do Yusupov: 0,96 nos dois tabuleiros, 0,20 a 0,43 nos dez
#: contornos internos que também são grandes e quase quadrados.
PISO_DO_PREENCHIMENTO = 0.9

#: Quanto duas caixas precisam se sobrepor para serem o mesmo tabuleiro.
SOBREPOSICAO_DE_REPETIDO = 0.5

#: Faixa em volta do tabuleiro onde moram rótulo e título, em alturas de
#: caractere. É a mesma margem que `livro.MARGEM_DIAGRAMA` exclui do texto, e
#: **tem de ser a mesma**: o que o livro exclui do texto por ser do diagrama é
#: exatamente o que aqui se procura como sendo do diagrama.
FAIXA_EM_CARACTERES = 1.4

#: Quantas das 8 raias precisam ter marca para a banda ser rótulo de casa (F95).
#:
#: Medido em 20 tabuleiros de 5 livros, contando raias ocupadas por banda:
#:
#:     livro                     esquerda  abaixo   tem rótulo?
#:     Yusupov (Chess Evolution)     8        8      sim
#:     Dvoretsky                     8        8      sim
#:     Nunn                          0        0      não
#:     Aagaard                     0–4      0–0      não
#:     Darcy Lima                  0–3      0–2      não
#:
#: Os dois grupos não encostam: quem tem rótulo tem as 8 raias, quem não tem
#: chega a 4. O 7 deixa passar uma raia comida pelo recorte sem abrir a porta
#: para a prosa que corre ao lado do tabuleiro.
RAIAS_DE_ROTULO = 7

_DADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")

CAMINHO_MODELO = os.path.join(_DADOS, "diagrama_modelo.pth")

#: A rede que decide vazia/ocupada (F7.5). **Separada da das peças, e a medição
#: é que separou**: as duas perguntas juntas numa rede de 13 classes fazem 97,8%
#: de ocupação, contra 99,3% da rede dedicada — três vezes mais erro. As bases
#: também são diferentes na origem: ocupação vem de tabuleiro inteiro
#: transcrito, identidade vem do fluxo de correção da F8.3.
CAMINHO_OCUPACAO = os.path.join(_DADOS, "ocupacao_modelo.pth")

_modelo = None
_modelo_ocupacao = None


class ModeloAusente(RuntimeError):
    """O modelo das peças não foi encontrado. Rode `treinar_diagrama.py`."""


# ----------------------------------------------------------------------
# Estruturas
# ----------------------------------------------------------------------

@dataclass
class Casa:
    """Uma casa lida. `linha` 0 é a 8a fila; `coluna` 0 é a coluna 'a'."""

    linha: int
    coluna: int
    simbolo: Optional[str]           # None = vazia; senão 'PNBRQKpnbrqk'
    confianca: float = 0.0
    arbitrada: bool = False          # a legalidade mudou esta leitura
    corrigida: bool = False          # a mão do usuário mudou esta leitura (F8.2)
    #: Quanto a rede da ocupação (F7.5) se convenceu de que esta casa tem — ou
    #: não tem — peça. Vai de 0,5 (moeda) a 1,0, e existe **em toda casa**,
    #: inclusive na vazia, ao contrário da `confianca`, que só a peça tem. É o
    #: sinal que o porteiro da F58 usa para desconfiar de um tabuleiro inteiro.
    confianca_ocupacao: float = 0.0

    @property
    def nome(self) -> str:
        return f"{'abcdefgh'[self.coluna]}{8 - self.linha}"


@dataclass
class Rotulos:
    """
    As letras `a`–`h` e os números `8`–`1` impressos em volta do tabuleiro (F95).

    **Existe para o arquivo exportado poder escolher.** O `livro.extrair`
    recebia `coordenadas=True|False` para o livro inteiro e não tinha como
    saber o que o livro trazia; com isto a escolha passa a poder ser "como está
    impresso", que é o padrão desde a F95.

    `lados` diz onde há rótulo, e não é redundante com `presentes`: um livro
    imprime `a`–`h` só embaixo, outro em cima e embaixo, e quem recorta a
    página precisa saber de que lado sobra tinta.

    `colunas` e `filas` são o que os rótulos **dizem**, quando houve
    classificador para lê-los. É de onde sai a `orientacao` — e é a única coisa
    no diagrama que a diz.
    """

    lados: Tuple[str, ...] = ()
    colunas: str = ""
    filas: str = ""
    #: "branca" (brancas embaixo), "preta", ou None quando os rótulos não
    #: bastaram para decidir. Nunca é chute: ver `_orientacao_dos_rotulos`.
    orientacao: Optional[str] = None

    @property
    def presentes(self) -> bool:
        return bool(self.lados)

    def resumo(self) -> str:
        if not self.presentes:
            return "sem coordenadas impressas"
        onde = ", ".join(self.lados)
        lado = {"branca": ", brancas embaixo",
                "preta": ", **pretas embaixo**"}.get(self.orientacao, "")
        return f"coordenadas impressas ({onde}){lado}"


@dataclass
class Titulo:
    """
    O que está impresso encostado no tabuleiro, acima ou abaixo dele (F95).

    **Não é sempre acima.** O Yusupov põe `➤ Ex. 22-4 ◀ ★★ ▼` em cima; o Nunn
    põe o número do diagrama (`144`) embaixo, à esquerda, com a avaliação da
    posição do outro lado. Um leitor que só olhasse para cima perderia o
    segundo, que é justamente o que se procura num livro de finais.

    `texto` vazio com `caixa` preenchida quer dizer "há tinta ali, e não deu
    para lê-la" — o chamador ainda pode recortá-la como imagem, que é o que a
    F60 fazia com a faixa.
    """

    texto: str = ""
    caixa: Optional[Tuple[int, int, int, int]] = None
    #: "acima" ou "abaixo". Vazio quando não há título.
    lado: str = ""
    #: As caixas que o título consumiu, para quem chama poder tirá-las do texto
    #: da página. Sem isto o mesmo `437` sairia duas vezes no livro exportado:
    #: uma como legenda da figura e outra como parágrafo solto.
    caixas: List[BoxEntry] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.texto or self.caixa)


@dataclass
class Leitura:
    """O que se conseguiu ler de um diagrama."""

    caixa: Tuple[int, int, int, int]         # x1, y1, x2, y2 na página
    casas: List[Casa] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)
    #: O que o livro imprimiu em volta (F95). Vêm de `ler_pagina`, e ficam
    #: vazios em quem chama `ler` com um recorte solto — ali não há "em volta".
    rotulos: Rotulos = field(default_factory=Rotulos)
    titulo: Titulo = field(default_factory=Titulo)
    #: Para que lado o diagrama foi impresso. As casas já vêm **giradas para o
    #: lado das brancas** quando isto é "preta": o FEN é sempre o da posição, e
    #: este campo é o de como ela estava desenhada. Quem redesenha o diagrama
    #: passa isto a `render_diagrama.desenhar(orientacao=...)` e o livro sai
    #: como o livro era.
    orientacao: str = "branca"

    @property
    def ocupadas(self) -> List[Casa]:
        return [c for c in self.casas if c.simbolo]

    @property
    def arbitradas(self) -> int:
        return sum(1 for c in self.casas if c.arbitrada)

    def tabuleiro(self) -> chess.Board:
        board = chess.Board(None)
        for c in self.ocupadas:
            board.set_piece_at(chess.square(c.coluna, 7 - c.linha),
                               chess.Piece.from_symbol(c.simbolo))
        return board

    def fen(self) -> str:
        """
        FEN completo, com o que o diagrama não tem preenchido por convenção.

        Lado a jogar, roque e en passant não estão desenhados no tabuleiro. Sai
        "brancas a jogar, sem roque, sem en passant" — e `avisos` diz isso, para
        ninguém tomar a convenção por leitura.
        """
        return f"{self.tabuleiro().board_fen()} w - - 0 1"

    @property
    def plausivel(self) -> bool:
        """A posição passa nas provas de contagem. Não quer dizer 'certa'."""
        return _plausivel([c.simbolo for c in self.ocupadas],
                          [(c.linha, c.coluna) for c in self.ocupadas])

    def resumo(self) -> str:
        partes = [f"{len(self.ocupadas)} peças"]
        if self.arbitradas:
            partes.append(f"{self.arbitradas} corrigida(s) pela legalidade")
        if not self.plausivel:
            partes.append("posição impossível — confira")
        return ", ".join(partes)


# ----------------------------------------------------------------------
# O recorte parece um tabuleiro?
# ----------------------------------------------------------------------

def pontuacao_de_tabuleiro(recorte) -> float:
    """
    Quanto o recorte parece um tabuleiro, em níveis de cinza (F95).

    A diferença média de tinta entre as 32 casas ímpares e as 32 pares, medida
    **no anel de fundo de cada casa** — ver `ANEL_DA_CASA`. Um tabuleiro dá de
    19 a 124; um recorte de texto do mesmo tamanho dá de -1 a 3.

    **Serve a duas perguntas que pareciam uma.** A primeira é "isto é um
    tabuleiro?", e é o que peneira os candidatos de `_aninhados`. A segunda é
    "a grade está no lugar?": a conta é a mesma, porque uma grade deslocada
    mistura casa clara com escura e a diferença desaba — é a prova que o
    docstring do topo diz ter sido feita nos 25 diagramas rotulados, aqui
    escrita como função em vez de como afirmação.

    Não usa a rede, e isso é de propósito: quem chama é a **localização**, que
    roda antes de haver leitura, e num modelo ausente ela tem de continuar
    funcionando.

    Mede tom, e não binarização, porque a casa escura destes livros tem dois
    desenhos — cinza chapado num, hachura diagonal noutro. Binarizada, a
    hachurada fica branca na moda e o xadrez some; o tom médio do anel a
    distingue nos dois casos.
    """
    arr = np.asarray(recorte)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    h, w = arr.shape[:2]
    if h < 32 or w < 32:
        return 0.0

    tinta = np.zeros((8, 8), np.float32)
    for r in range(8):
        for c in range(8):
            casa = arr[int(r * h / 8):int((r + 1) * h / 8),
                       int(c * w / 8):int((c + 1) * w / 8)]
            if casa.size == 0:
                return 0.0
            m = max(1, int(round(casa.shape[0] * ANEL_DA_CASA)))
            n = max(1, int(round(casa.shape[1] * ANEL_DA_CASA)))
            anel = np.concatenate([casa[:m].ravel(), casa[-m:].ravel(),
                                   casa[:, :n].ravel(), casa[:, -n:].ravel()])
            tinta[r, c] = 255.0 - float(anel.mean())

    paridade = np.fromfunction(lambda r, c: (r + c) % 2, (8, 8)).astype(int)
    return float(tinta[paridade == 1].mean() - tinta[paridade == 0].mean())


# ----------------------------------------------------------------------
# Achar o diagrama na página
# ----------------------------------------------------------------------

def _sobrepoe(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]
              ) -> float:
    """Interseção sobre união de duas caixas."""
    lx = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    ly = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = lx * ly
    uniao = ((a[2] - a[0]) * (a[3] - a[1])
             + (b[2] - b[0]) * (b[3] - b[1]) - inter)
    return inter / max(1, uniao)


def _quadrado_grande(l: int, a: int, minimo: float) -> bool:
    """As duas provas de forma que um tabuleiro tem de passar."""
    l, a = max(1, l), max(1, a)
    return l >= minimo and a >= minimo and max(l / a, a / l) <= TOLERANCIA_QUADRADO


def _aninhados(imagem, binaria, minimo: float,
               achados: Sequence[Tuple[int, int, int, int]]
               ) -> List[Tuple[int, int, int, int]]:
    """
    Os tabuleiros que **não** são contorno externo da página (F95).

    O caso é o do diagrama impresso dentro de um painel: com `RETR_EXTERNAL` o
    painel é o contorno e o tabuleiro é filho dele, então ele nunca chega à
    lista de boxes e `localizar` não tem o que recolher. `RETR_LIST` devolve os
    de dentro também — e junto com eles os contornos-escada que as casas
    escuras formam, que também são grandes e quase quadrados.

    Quem os separa são as duas provas independentes: o preenchimento
    (`PISO_DO_PREENCHIMENTO`) e o xadrez (`PISO_DO_XADREZ`). Ver o docstring do
    módulo para os números.

    Roda **depois** da passada normal e só acrescenta: um tabuleiro que já
    apareceu como contorno externo continua vindo de lá, com o retângulo de lá.
    """
    if binaria is None or imagem is None:
        return []

    contornos, _h = cv2.findContours(binaria, cv2.RETR_LIST,
                                     cv2.CHAIN_APPROX_SIMPLE)
    arr = np.asarray(imagem)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

    novos: List[Tuple[int, int, int, int]] = []
    for contorno in contornos:
        x, y, l, a = cv2.boundingRect(contorno)
        if not _quadrado_grande(l, a, minimo):
            continue
        if cv2.contourArea(contorno) < PISO_DO_PREENCHIMENTO * l * a:
            continue
        caixa = (x, y, x + l, y + a)
        if any(_sobrepoe(caixa, outra) > SOBREPOSICAO_DE_REPETIDO
               for outra in list(achados) + novos):
            continue
        if pontuacao_de_tabuleiro(arr[y:y + a, x:x + l]) < PISO_DO_XADREZ:
            continue
        novos.append(caixa)
    return novos


def ordem_de_leitura(caixas: Sequence[Tuple[int, int, int, int]]
                     ) -> List[Tuple[int, int, int, int]]:
    """
    Os diagramas na ordem em que se leem: coluna a coluna, de cima para baixo.

    **Era `sort(key=(y1, x1))`, e isso é errado duas vezes.**

    A primeira é que um pixel troca a fila inteira. Medido na página 221 do
    Yusupov, que tem seis diagramas em duas colunas: o da direita começa em
    y=358 e o da esquerda em y=359, então a lista saía com o da direita antes.
    Quem via "Diagrama 1 de 6" via o `Ex. 22-4`.

    A segunda é que, mesmo estável, ordenar por fila não é a ordem de leitura de
    uma página de duas colunas — é a mesma armadilha que a F61 documenta para o
    texto. Conferido nos rótulos que a F95 passou a ler, nas duas páginas de
    seis diagramas que o material tem: no Yusupov eles se chamam `Ex. 22-1` a
    `Ex. 22-6` e no Aagaard `①` a `⑥`, e nos dois a numeração desce a coluna da
    esquerda antes de começar a da direita. Por fila sairia 1, 4, 2, 5, 3, 6.

    Coluna a coluna cobre também o caso de uma fila só: dois diagramas lado a
    lado são duas colunas de um, e saem da esquerda para a direita como sairiam
    por fila. Não há layout que peça a outra ordem.

    Duas caixas são da mesma coluna quando se sobrepõem na horizontal em mais da
    metade da largura da menor. É a régua da leitura de linha da F17 deitada, e
    pelo mesmo motivo: alinhamento de impressão não é alinhamento exato.
    """
    restantes = sorted(caixas, key=lambda c: (c[0], c[1]))
    saida: List[Tuple[int, int, int, int]] = []
    while restantes:
        primeira = restantes[0]
        coluna, sobram = [], []
        for c in restantes:
            largura = min(primeira[2] - primeira[0], c[2] - c[0])
            juntos = min(primeira[2], c[2]) - max(primeira[0], c[0])
            (coluna if juntos * 2 > largura else sobram).append(c)
        saida.extend(sorted(coluna, key=lambda c: c[1]))
        restantes = sobram
    return saida


def localizar(boxes: Sequence[BoxEntry],
              descartados: Optional[Sequence[BoxEntry]] = None,
              escala: Optional[int] = None, *,
              imagem=None, binaria=None
              ) -> List[Tuple[int, int, int, int]]:
    """
    As caixas de diagrama, a partir dos contornos da página.

    `boxes` são os contornos antes do descarte da F1.8 e `descartados` o que ela
    tirou; passando só `boxes`, o descarte é refeito aqui. O diagrama é o que
    caiu por ser grande **e** é quase quadrado: um travessão também é descartado
    por largura, e não é tabuleiro.

    **`imagem` e `binaria` abrem a segunda passada** (F95), que acha o tabuleiro
    impresso dentro de um painel — aquele que nunca chega a `boxes` porque não é
    contorno externo. São a página em cinza e o `th` que `boxes_antes_do_descarte`
    devolve; sem eles, a busca é só a de antes. Ver `_aninhados`.

    **`escala` é a altura de caractere da página, e é o que dá o tamanho mínimo**
    (F7.6). Sem ela a referência é a mediana das alturas dos boxes — e numa
    página que é quase só diagrama essa mediana não mede o texto, mede o
    hachurado de dentro das casas. Medido na página 221 do Yusupov, que tem seis
    diagramas e quatro linhas de texto: a mediana das alturas é **5 px** contra
    30 na página anterior, o mínimo desaba de 114 px para 30, e seis caracteres
    soltos entram na conta como diagrama — o comando dizia 12.

    É a mesma armadilha que `descartar_blocos_nao_texto` documenta desde a F11,
    com a mesma saída: quem tem a imagem passa `preprocess.escala_de_texto`, que
    pesa por tinta e não desaba. `ler_pagina` passa.
    """
    from core.services.box_service import BoxService

    if descartados is None:
        ficam = {id(b) for b in BoxService.descartar_blocos_nao_texto(
            list(boxes), escala=escala)}
        descartados = [b for b in boxes if id(b) not in ficam]

    if not boxes:
        return []
    if not escala:
        alturas = sorted(b.height for b in boxes)
        escala = alturas[len(alturas) // 2]
    minimo = max(1, escala) * MINIMO_EM_CARACTERES

    saida = []
    for b in descartados:
        if not _quadrado_grande(b.width, b.height, minimo):
            continue
        saida.append((b.x1, b.y1, b.x2, b.y2))
    saida.extend(_aninhados(imagem, binaria, minimo, saida))
    return ordem_de_leitura(saida)


# ----------------------------------------------------------------------
# O que está impresso em volta: rótulos das casas e título (F95)
# ----------------------------------------------------------------------

#: Os quatro lados de um tabuleiro, na ordem em que se olha para eles.
LADOS = ("esquerda", "direita", "acima", "abaixo")

#: Altura aceita para uma marca ser caractere, em alturas de caractere.
#: Aberta dos dois lados: o `8` do rótulo é um algarismo de corpo cheio, e o
#: `➤` do cabeçalho do Yusupov é maior que a letra ao lado dele.
MARCA_MINIMA, MARCA_MAXIMA = 0.30, 1.8

#: Vão entre dois caracteres que vira espaço, em larguras medianas de caractere.
#:
#: **Saiu de produção na F107** — quem decide agora é `limiar_de_espaco`, logo
#: abaixo. Fica de pé porque `medir_vao.py` a usa como linha de base: sem ela o
#: instrumento não consegue mais medir a régua que substituiu.
#:
#: **Mora aqui e é usado pelo `livro`**, e não o contrário, porque `livro`
#: importa este módulo e este não importa aquele. Duas definições do mesmo
#: número é a família de defeito da F5.2: o dia em que uma muda, a mesma linha
#: sai espaçada de um jeito no título e de outro no parágrafo.
VAO_DE_ESPACO = 0.35

#: Quantas vezes o **vão típico da linha** o vão precisa ser para virar espaço,
#: e o piso disso em larguras medianas de tinta (F107).
#:
#: `VAO_DE_ESPACO` acima é a régua velha, e ela media contra a coisa errada:
#: comparava vão com **largura de tinta**, e a largura de tinta muda com o
#: alfabeto sem que o espacejamento mude junto. Algarismo é o caso que quebra —
#: ele vem com espacejamento tabular, e a caixa de tinta do `1` é um terço do
#: avanço dele, enquanto a mediana da linha é ditada pelas minúsculas da prosa.
#: Medido: o vão mediano entre dois algarismos vizinhos é 0,45, **já acima do
#: limiar de 0,35 antes de qualquer espaço existir**. É por isso que `2011` saía
#: `20 1 1`, e eram 1.965 números partidos no Yusupov exportado.
#:
#: O vão típico da linha responde à pergunta certa — "este vão é maior que os
#: que esta linha usa entre letras da mesma palavra?" — porque ele *é* o
#: espacejamento, e acompanha o alfabeto por construção.
#:
#: **O piso é o que impede a régua de inventar espaço na linha que não tem
#: nenhum.** Uma linha de uma palavra só, ou de lances colados, tem vão típico
#: pequeno, e sem piso qualquer folga de um pixel viraria separação — o defeito
#: seria simétrico ao que a régua velha tem com algarismo, e não adiantaria
#: trocar um pelo outro.
#:
#: Medidos em duas obras com camada de texto, 54.558 pares de caixas vizinhas
#: (`medir_vao.py`), onde a camada diz se os dois vizinhos são da mesma palavra:
#:
#:     régua                    Yusupov          Aagaard
#:                          a mais  a menos   a mais  a menos
#:     0,35 x largura        5,5%     7,9%     1,4%     2,6%
#:     2,0 x vão, piso 0,45  1,2%    10,9%     0,3%     4,0%
#:
#: Em contagem bruta, espaço a mais cai de 675 para 149 e de 426 para 84 —
#: **4,5x e 5,1x**. Espaço a menos sobe, de 235 para 322 e de 203 para 318.
#:
#: **Espaço a mais cai; espaço a menos sobe.** As duas contas ficam
#: separadas de propósito, porque não custam o mesmo: espaço a mais parte a
#: palavra e o dicionário a perde inteira, junto com a régua do léxico e a do
#: PGN que leem por palavra. Espaço a menos cola duas que continuam legíveis.
#:
#: A superfície é **plana** em volta: (2,0, 0,45), (2,25, 0,45), (2,5, 0,40) e
#: (2,5, 0,45) ficam a menos de 3% um do outro na soma dos dois livros. O par
#: escolhido é o melhor conjunto, e não uma quina — é o que faz não valer a pena
#: reajustá-lo por causa de um livro novo.
FATOR_DO_VAO = 2.0
PISO_DO_VAO = 0.45


#: Vãos de menos para a mediana deles querer dizer alguma coisa.
#:
#: **É o limite em que a medição vale**, e não um número de gosto. O
#: `medir_vao.py` pulou toda linha com menos de 4 caixas, então os 54.558 pares
#: que escolheram `FATOR_DO_VAO` e `PISO_DO_VAO` são todos de linha com 3 vãos
#: ou mais — aplicar a parte relativa abaixo disso seria usá-la fora do que foi
#: medido.
#:
#: E há um motivo antes desse: a mediana só estima o vão *dentro* da palavra
#: enquanto a maioria dos vãos for de dentro. Numa linha de prosa isso sobra
#: (medidos, 19,4% dos pares são separação). Numa faixa de duas marcas com um
#: espaço no meio, o único vão **é** o espaço — a mediana passa a ser ele, `2,0
#: x` ele nunca é alcançado, e o espaço sumiria. É o caso do cabeçalho curto de
#: diagrama, que é justamente onde um buraco custa o número do exercício.
#:
#: Abaixo do mínimo quem responde é o piso sozinho, que é a régua velha com a
#: constante corrigida.
VAOS_PARA_A_MEDIANA = 3


def limiar_de_espaco(emfila) -> float:
    """
    Acima deste vão, em pixels, os dois vizinhos estão em palavras diferentes.

    `emfila` são as caixas da linha **já ordenadas por x**, que é como os dois
    chamadores as têm. Uma definição só para os dois pelo mesmo motivo que a
    constante mora aqui e não no `livro`: o título do diagrama usa a mesma régua
    da prosa, e o dia em que houver duas a mesma linha sai espaçada de um jeito
    no título e de outro no parágrafo.

    Mediana de vão zero ou negativa é linha de glifos colados: ali a referência
    relativa não existe, e quem responde é o piso. Ver `FATOR_DO_VAO`. Com menos
    de `VAOS_PARA_A_MEDIANA` vãos, também — e ali é por não haver distribuição
    sobre a qual falar, não por ela ser estreita.
    """
    if len(emfila) < 2:
        return float("inf")
    largura = float(np.median([b.width for b in emfila])) or 1.0
    piso = largura * PISO_DO_VAO
    vaos = [b.x1 - a.x2 for a, b in zip(emfila, emfila[1:])]
    if len(vaos) < VAOS_PARA_A_MEDIANA:
        return piso
    return max(max(float(np.median(vaos)), 0.0) * FATOR_DO_VAO, piso)


def _cinza(imagem) -> np.ndarray:
    arr = np.asarray(imagem)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    return arr


def _banda(imagem, caixa: Tuple[int, int, int, int], escala: float, lado: str):
    """
    (recorte da banda, canto dela na página, eixo em que os rótulos se espalham).

    A banda é a faixa de `FAIXA_EM_CARACTERES` alturas de caractere colada ao
    lado pedido do tabuleiro — o mesmo território que `livro.MARGEM_DIAGRAMA`
    exclui do texto da página. `eixo` é 0 quando as marcas se espalham na
    horizontal (acima, abaixo) e 1 quando na vertical.
    """
    arr = _cinza(imagem)
    altura, largura = arr.shape[:2]
    x1, y1, x2, y2 = caixa
    faixa = max(1, int(round(escala * FAIXA_EM_CARACTERES)))

    if lado == "abaixo":
        recorte, canto, eixo = arr[y2:min(altura, y2 + faixa), x1:x2], (x1, y2), 0
    elif lado == "acima":
        topo = max(0, y1 - faixa)
        recorte, canto, eixo = arr[topo:y1, x1:x2], (x1, topo), 0
    elif lado == "esquerda":
        esq = max(0, x1 - faixa)
        recorte, canto, eixo = arr[y1:y2, esq:x1], (esq, y1), 1
    elif lado == "direita":
        recorte, canto, eixo = arr[y1:y2, x2:min(largura, x2 + faixa)], (x2, y1), 1
    else:
        raise ValueError(f"lado inválido: {lado!r} (use um de {LADOS})")

    return recorte, canto, eixo


#: Abaixo desta amplitude de tom a banda não tem tinta, tem papel.
#: Sem esta guarda o Otsu de `_marcas_da_banda` divide o ruído do scan ao meio e
#: devolve dezenas de marcas onde não há nada impresso.
AMPLITUDE_DE_TINTA = 40

#: Acima desta fração de tinta a banda não é margem, é o miolo de outra coisa —
#: uma tarja, o próprio tabuleiro num recorte torto. Marca ali não é rótulo.
TINTA_DE_MARGEM = 0.5


def _marcas_da_banda(faixa, escala: float) -> List[BoxEntry]:
    """
    As marcas do tamanho de um caractere que há na banda, **em coordenadas da
    página**.

    Sai na página, e não na banda, porque a banda corta letra alta: no Yusupov
    a margem começa em y=896 e o `D` de `Diagram` vai de 887 a 916. Medindo na
    banda, o recorte que vai ao classificador começa no 896 — e o `D` decapitado
    era lido como `U`. A marca é achada dentro da banda e recortada da página.
    """
    banda, canto, _eixo = faixa
    if banda.size == 0 or int(banda.max()) - int(banda.min()) < AMPLITUDE_DE_TINTA:
        return []
    _t, binaria = cv2.threshold(banda, 0, 255,
                                cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if binaria.mean() > 255 * TINTA_DE_MARGEM:
        return []

    ox, oy = canto
    quantas, _rotulos, medidas, _centros = cv2.connectedComponentsWithStats(
        binaria, 8)
    saida = []
    for i in range(1, quantas):
        x, y, l, a = medidas[i][:4]
        if not (MARCA_MINIMA * escala <= a <= MARCA_MAXIMA * escala):
            continue
        if not (0.10 * escala <= l <= MARCA_MAXIMA * escala):
            continue
        saida.append(BoxEntry("", int(ox + x), int(oy + y),
                              int(ox + x + l), int(oy + y + a)))
    return saida


def _por_raia(marcas: Sequence[BoxEntry], caixa: Tuple[int, int, int, int],
              eixo: int) -> Dict[int, BoxEntry]:
    """
    `{raia: a maior marca dela}` — a raia é a casa do tabuleiro a que a marca
    se alinha. Rótulo de casa tem uma marca por raia; prosa que passa ao lado
    não tem.

    As raias saem do **tabuleiro**, e não da banda: é com as casas que o rótulo
    se alinha, e uma banda cortada pela borda da página deslocaria todas.
    """
    x1, y1, x2, y2 = caixa
    inicio, comprimento = (x1, x2 - x1) if eixo == 0 else (y1, y2 - y1)
    saida: Dict[int, BoxEntry] = {}
    for m in marcas:
        meio = (m.x1 + m.x2) / 2 if eixo == 0 else (m.y1 + m.y2) / 2
        raia = int((meio - inicio) * 8 / max(1, comprimento))
        if not 0 <= raia < 8:
            continue
        atual = saida.get(raia)
        if atual is None or m.width * m.height > atual.width * atual.height:
            saida[raia] = m
    return saida


def _ler_marca(imagem, marca: BoxEntry, classificar: Optional[Callable],
               piso: float = 0.5) -> str:
    """Um caractere da página, ou '' se não houver classificador ou confiança."""
    if classificar is None:
        return ""
    arr = _cinza(imagem)
    recorte = arr[max(0, marca.y1):marca.y2, max(0, marca.x1):marca.x2]
    if not recorte.size:
        return ""
    char, conf = classificar(recorte)
    return char if char and char != "?" and conf >= piso else ""


#: As duas leituras possíveis de cada eixo de rótulos.
_COLUNAS = {"branca": "abcdefgh", "preta": "hgfedcba"}
_FILAS = {"branca": "87654321", "preta": "12345678"}

#: Quantos rótulos precisam bater, e por quanto o vencedor precisa ganhar, para
#: a orientação ser afirmada (F95).
#:
#: **A régua é conservadora de propósito.** Dizer "pretas embaixo" gira o FEN
#: 180°: acertar não muda nada num diagrama já certo, e errar estraga um que
#: estava certo. Medido nos rótulos lidos com o modelo de 105 classes:
#:
#:     livro       letras lidas   contra a-h   contra h-a
#:     Yusupov     'abcdefgh'          8            0
#:     Dvoretsky   'abCdefOh'          6            0
#:
#:     livro       números lidos  contra 8-1   contra 1-8
#:     Yusupov     '87654321'          8            0
#:     Dvoretsky   '37))43)1'          4            0
#:
#: O Dvoretsky é o caso difícil — os algarismos dele estão numa fonte que o
#: modelo não viu — e ainda assim a distância entre as duas hipóteses é de 4 a
#: 6. Um diagrama de fato invertido teria a distância no outro sentido.
ACERTOS_DE_ORIENTACAO = 4
VANTAGEM_DE_ORIENTACAO = 2


def _quanto_bate(lido: str, molde: str) -> int:
    return sum(1 for a, b in zip(lido, molde) if a and a.lower() == b)


def _orientacao_dos_rotulos(colunas: str, filas: str) -> Optional[str]:
    """
    Para que lado o tabuleiro está virado, ou None se os rótulos não bastam.

    **A paridade das casas não responde isto, e é o engano tentador.** Girar o
    tabuleiro 180° troca fila e coluna ao mesmo tempo, e a soma dos dois índices
    conserva a paridade — a casa de baixo à esquerda é escura nas duas
    orientações (`a1` numa, `h8` na outra). O único sinal impresso que distingue
    as duas é o rótulo, e por isso um diagrama sem coordenadas fica sem
    resposta: `None`, e `ler` segue supondo brancas embaixo, como sempre supôs.

    Os dois eixos são somados antes de decidir, e não votados um a um: um livro
    imprime só as letras, outro só os números, e exigir os dois perderia os dois
    casos.
    """
    pontos = {lado: _quanto_bate(colunas, _COLUNAS[lado])
                    + _quanto_bate(filas, _FILAS[lado])
              for lado in ("branca", "preta")}
    melhor, pior = sorted(pontos, key=lambda k: -pontos[k])
    if pontos[melhor] < ACERTOS_DE_ORIENTACAO:
        return None
    if pontos[melhor] - pontos[pior] < VANTAGEM_DE_ORIENTACAO:
        return None
    return melhor


def ler_rotulos(imagem, caixa: Tuple[int, int, int, int],
                escala: Optional[float] = None,
                classificar: Optional[Callable] = None) -> Rotulos:
    """
    As coordenadas `a`–`h` e `8`–`1` impressas em volta do tabuleiro (F95).

    **Achar que elas existem não precisa de classificador**, e é isso que faz a
    função servir à exportação: o que separa uma banda de rótulos de uma banda
    de prosa é a **geometria** — rótulo de casa tem uma marca por raia, e são
    oito raias. Medido em 20 tabuleiros de 5 livros, os que têm rótulo têm as 8
    raias e os que não têm chegam a 4 (ver `RAIAS_DE_ROTULO`).

    **Ler o que elas dizem precisa**, e é daí que sai a orientação. `classificar`
    é o mesmo contrato do resto do projeto: `(recorte_cinza) -> (char, conf)`.
    Sem ele, `colunas` e `filas` saem vazias e `orientacao` sai `None` — o que
    não é o mesmo que "brancas embaixo", e por isso não é escrito assim.

    `escala` é a altura de caractere da página. Omitida, sai do próprio
    tabuleiro: um oitavo do lado dele é a casa, e o rótulo é impresso menor que
    ela — a estimativa é grosseira e serve para quem só tem o recorte.
    """
    arr = _cinza(imagem)
    x1, y1, x2, y2 = caixa
    if min(x2 - x1, y2 - y1) < 32:
        return Rotulos()
    if not escala:
        # Um oitavo do lado é a casa; o rótulo cabe em meia casa. Não é a régua
        # da página, e por isso quem a tem deve passá-la.
        escala = (x2 - x1) / 8.0 * 0.5

    lados, por_lado = [], {}
    for lado in LADOS:
        faixa = _banda(arr, caixa, escala, lado)
        _recorte, _canto, eixo = faixa
        raias = _por_raia(_marcas_da_banda(faixa, escala), caixa, eixo)
        if len(raias) >= RAIAS_DE_ROTULO:
            lados.append(lado)
            por_lado[lado] = raias

    if not lados:
        return Rotulos()

    def texto(lado: str) -> str:
        raias = por_lado[lado]
        return "".join(_ler_marca(arr, raias[i], classificar)
                       if i in raias else "" for i in range(8))

    # Um livro imprime as letras só embaixo, outro em cima e embaixo; e há quem
    # imprima os números dos dois lados. Basta um de cada eixo, e o de baixo e o
    # da esquerda são os que todo livro que rotula traz.
    colunas = next((texto(l) for l in ("abaixo", "acima") if l in por_lado), "")
    filas = next((texto(l) for l in ("esquerda", "direita") if l in por_lado), "")
    return Rotulos(tuple(lados), colunas, filas,
                   _orientacao_dos_rotulos(colunas, filas))


def _caixas_da_banda(imagem, caixa, escala, lado, boxes) -> List[BoxEntry]:
    """
    As marcas da banda, em coordenadas da página, do jeito mais fiel que houver.

    Com a lista de caixas da página, são as caixas dela que caem na banda: já
    passaram pelo merge do pingo do `i` e pela volta da tarja em negativo. Sem
    ela, são os componentes conexos do recorte — que é o que sobra para quem
    chama com um diagrama solto na mão.

    **A peneira de altura não é a mesma nos dois casos, e não pode ser.** A
    caixa da página já passou pelo pipeline inteiro e é caractere por
    construção; peneirá-la por altura mínima tira o hífen de `Ex. 22-1`, que
    numa escala de 57 px tem 5 px de altura. O componente conexo cru não tem
    essa garantia — ali a peneira dos dois lados é o que separa letra de filete
    de moldura.
    """
    faixa = _banda(imagem, caixa, escala, lado)
    if boxes is None:
        return _marcas_da_banda(faixa, escala)

    banda, (ox, oy), _eixo = faixa
    alt, larg = banda.shape[:2]
    dentro = []
    for b in boxes:
        # **A borda que conta é a que olha para o tabuleiro**, e ela troca de
        # lado com a banda. Acima é o pé, e é o que a `livro._na_faixa`
        # documenta desde a F60: a maiúscula do cabeçalho sobe acima da banda e
        # a minúscula não, e medir pelo topo partia a linha ao meio (`Diagram`
        # saía `agram`). Abaixo é o topo, pela mesma razão espelhada — o
        # descendente do `y` desce abaixo da banda. Medido no Nunn, cuja legenda
        # `437` começa a 1,29 escalas do tabuleiro e acaba a 2,3: pelo pé, ela
        # não existia.
        borda = b.y2 if lado == "acima" else b.y1
        if not (oy <= borda <= oy + alt):
            continue
        if b.x2 <= ox or b.x1 >= ox + larg:
            continue
        if b.height > MARCA_MAXIMA * escala:
            continue
        dentro.append(b)
    return dentro


def caixas_dos_rotulos(caixa: Tuple[int, int, int, int], escala: float,
                       rotulos: Rotulos, boxes: Sequence[BoxEntry]
                       ) -> List[BoxEntry]:
    """
    As caixas da página que são rótulo de casa deste tabuleiro (F109 §3).

    **Existe porque a margem de exclusão pede continência, e o rótulo nem
    sempre cabe nela.** `livro.caixas_e_diagramas` tira do texto a caixa
    inteiramente dentro de `MARGEM_DIAGRAMA` (1,4 alturas de caractere); a
    letra `a`–`h` impressa a 1,2 alturas da borda tem o pé a 1,7, e escapa. No
    Yusupov exportado, 146 parágrafos eram só a fila `a b c d e f g h` — ou o
    pedaço dela que escapou —, e é dela que sai o `hDiagram`: o `h` que sobrou
    cola na legenda da figura seguinte.

    A régua é a de `ler_rotulos`, e por isso só vale nos lados em que ele
    **achou** rótulo: a caixa do tamanho de uma marca, contida na largura (ou
    na altura) do tabuleiro, e cuja borda voltada para ele cai na faixa de
    `FAIXA_EM_CARACTERES`. A continência no eixo do tabuleiro é o que separa
    o rótulo da prosa da coluna vizinha, que só se sobrepõe.
    """
    if not rotulos.presentes or not boxes:
        return []
    x1, y1, x2, y2 = caixa
    faixa = escala * FAIXA_EM_CARACTERES
    maxima = MARCA_MAXIMA * escala
    saida = []
    for b in boxes:
        if b.y2 - b.y1 > maxima or b.x2 - b.x1 > maxima:
            continue
        for lado in rotulos.lados:
            if lado == "abaixo":
                dentro = x1 <= b.x1 and b.x2 <= x2 and y2 <= b.y1 <= y2 + faixa
            elif lado == "acima":
                dentro = x1 <= b.x1 and b.x2 <= x2 and y1 - faixa <= b.y2 <= y1
            elif lado == "esquerda":
                dentro = y1 <= b.y1 and b.y2 <= y2 and x1 - faixa <= b.x2 <= x1
            else:
                dentro = y1 <= b.y1 and b.y2 <= y2 and x2 <= b.x1 <= x2 + faixa
            if dentro:
                saida.append(b)
                break
    return saida


def ler_titulo(imagem, caixa: Tuple[int, int, int, int],
               escala: Optional[float] = None,
               classificar: Optional[Callable] = None,
               boxes: Optional[Sequence[BoxEntry]] = None,
               rotulos: Optional[Rotulos] = None) -> Titulo:
    """
    O título do diagrama — o que está impresso encostado nele (F95).

    **Olha os dois lados, e a F60 só olhava um.** No Yusupov o título fica
    acima (`➤ Ex. 22-4 ◀ ★★ ▼`); no Nunn fica abaixo, e é o número do diagrama
    (`144`), com a avaliação da posição do outro lado da mesma linha. Quem só
    olhasse para cima perderia o segundo inteiro.

    Acima ganha quando há tinta nos dois: é ali que mora o título nos livros
    que têm os dois, e o de baixo naqueles é o rótulo das casas — que esta
    função já não olha, porque `rotulos` diz de que lados ele é.

    Devolve a caixa mesmo quando não lê o texto. É a diferença entre "não há
    título" e "há, e o modelo não deu conta": no segundo caso o exportador
    ainda pode recortá-lo como imagem, que é o que a F60 fazia.
    """
    arr = _cinza(imagem)
    x1, y1, x2, y2 = caixa
    if not escala:
        escala = (x2 - x1) / 8.0 * 0.5
    de_rotulo = set(rotulos.lados) if rotulos else set()

    for lado in ("acima", "abaixo"):
        if lado in de_rotulo:
            continue
        marcas = _caixas_da_banda(arr, caixa, escala, lado, boxes)
        if not marcas:
            continue
        return Titulo(_texto_das_marcas(arr, marcas, classificar),
                      (min(m.x1 for m in marcas), min(m.y1 for m in marcas),
                       max(m.x2 for m in marcas), max(m.y2 for m in marcas)),
                      lado, list(marcas))
    return Titulo()


def _texto_das_marcas(imagem, marcas: Sequence[BoxEntry],
                      classificar: Optional[Callable]) -> str:
    """
    As marcas da banda lidas da esquerda para a direita, com espaço no vão.

    Só um caractere fraco já derruba o título inteiro, e é mais severo que a
    prosa de propósito — é a regra que a `livro._faixa_em_texto` documenta
    desde a F67: a faixa tem quatro ou cinco caracteres, e um buraco nela é o
    número do exercício, que é justamente o que alguém procuraria.
    """
    from core import notacao

    if classificar is None or not marcas:
        return ""
    emfila = sorted(marcas, key=lambda m: m.x1)
    limiar = limiar_de_espaco(emfila)
    partes = []
    for i, m in enumerate(emfila):
        char = _ler_marca(imagem, m, classificar)
        if not char:
            return ""
        if i and m.x1 - emfila[i - 1].x2 > limiar:
            partes.append(" ")
        partes.append(notacao.normalizar_saida(char))
    return "".join(partes).strip()


# ----------------------------------------------------------------------
# Ler um diagrama
# ----------------------------------------------------------------------

def _casas_do_recorte(recorte: np.ndarray) -> dict:
    h, w = recorte.shape[:2]
    return {(r, c): cv2.resize(
                recorte[int(r * h / 8):int((r + 1) * h / 8),
                        int(c * w / 8):int((c + 1) * w / 8)],
                (LADO, LADO), interpolation=cv2.INTER_AREA).astype(np.float32)
            for r in range(8) for c in range(8)}


def _otsu(valores) -> float:
    v = np.asarray(valores, dtype=np.float32)
    if v.size < 2 or v.max() <= v.min():
        return float(v.max()) + 1.0
    n = ((v - v.min()) / (v.max() - v.min()) * 255).astype(np.uint8)
    t, _ = cv2.threshold(n, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return float(v.min() + t / 255.0 * (v.max() - v.min()))


def _residuos(quadros: dict) -> dict:
    """
    Resíduo por casa — o fundo é a mediana das casas da mesma cor.

    **O Otsu que sobrou aqui não decide nada sobre a leitura** (F7.5). Ele serve
    a uma pergunta interna e tolerante: quais casas usar para *reestimar o
    fundo*. A primeira mediana inclui ~40% de peças e enviesa o modelo; refazê-la
    com as casas de resíduo baixo limpa o fundo, e errar algumas nessa triagem
    quase não move uma mediana de 32 amostras.

    Quem decide vazia/ocupada é a rede, em `_ocupadas`. Era este mesmo Otsu, e
    era ele o gargalo: medido nas 1.600 casas transcritas do gabarito, 86
    omissões e 38 falsos positivos — 92,25%.
    """
    residuo = {}
    for paridade in (0, 1):
        chaves = [(r, c) for r in range(8) for c in range(8)
                  if (r + c) % 2 == paridade]
        pilha = np.stack([quadros[k] for k in chaves])
        fundo = np.median(pilha, axis=0)
        forca = {k: float(np.abs(quadros[k] - fundo).mean()) for k in chaves}

        vazias = [k for k in chaves if forca[k] <= _otsu(list(forca.values()))]
        if len(vazias) >= 4:
            fundo = np.median(np.stack([quadros[k] for k in vazias]), axis=0)

        for k in chaves:
            residuo[k] = quadros[k] - fundo
    return residuo


def residuos(imagem, caixa: Optional[Tuple[int, int, int, int]] = None
             ) -> Tuple[dict, dict]:
    """
    (resíduo por casa, ocupada?) de um diagrama — o que o modelo lê (F8.3).

    É a mesma conta que `ler` faz, exposta porque a amostra de treino tem de
    ser **o resíduo**, e não o recorte cru: guardar a casa como ela sai da
    página traria o fundo do livro junto, e o modelo aprenderia o papel.

    A ocupação sai da rede desde a F7.5, e por isso esta função passou a
    precisar do modelo. Quem chama já veio de uma leitura bem-sucedida.
    """
    arr = np.asarray(imagem)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    if caixa is None:
        caixa = (0, 0, arr.shape[1], arr.shape[0])
    x1, y1, x2, y2 = caixa
    recorte = arr[max(0, y1):y2, max(0, x1):x2]
    if recorte.size == 0 or min(recorte.shape[:2]) < 16:
        return {}, {}
    residuo = _residuos(_casas_do_recorte(recorte))
    return residuo, _ocupadas(residuo)


def confianca_de_ocupacao(residuo: dict) -> dict:
    """
    `{casa: quanto a rede se convenceu do que decidiu}`, de 0,5 a 1,0 (F58).

    É a probabilidade **da decisão tomada** — `p` onde ela disse "tem peça" e
    `1 - p` onde disse "vazia" —, e não a de "tem peça". As duas formas ordenam
    o mesmo conjunto de casas duvidosas, mas só esta responde à pergunta que o
    porteiro faz: *qual é a casa em que esta leitura menos se sustenta?* Com a
    probabilidade crua, uma casa vazia lida com 0,01 pareceria a mais frágil do
    tabuleiro, quando é a mais firme.

    Existe porque a `ocupadas` calculava este número e o jogava fora no `>= 0.5`
    — e a F8.4 mediu que a ocupação é hoje a mais fraca das duas redes (99,38%
    contra 99,62% da identidade). Porteiro que só olhasse a confiança da peça
    seria cego justamente para o erro mais comum.
    """
    return {k: max(p, 1.0 - p) for k, p in _probabilidade_de_peca(residuo).items()}


def _probabilidade_de_peca(residuo: dict) -> dict:
    """`{casa: probabilidade de ter peça}`, crua, como a rede da F7.5 a devolve."""
    import torch

    chaves = sorted(residuo)
    rede, coluna, temperatura = _carregar_ocupacao()
    with torch.no_grad():
        p = torch.softmax(rede(entrada_da_rede([residuo[k] for k in chaves]))
                          / temperatura, dim=1).numpy()
    return {k: float(p[i, coluna]) for i, k in enumerate(chaves)}


def ocupadas(residuo: dict) -> dict:
    """
    `{casa: há peça?}` — a decisão de ocupação, pela rede (F7.5).

    **Era um limiar de Otsu sobre a força do resíduo, e ele era o gargalo da
    leitura.** Medido nas 1.600 casas do gabarito transcrito à mão
    (`tests/dados/ocupacao_diagramas.txt`):

        decisão                     omissões  falsos+   acerto
        Otsu (F7.1)                    86       38      92,25%
        melhor limiar possível          —        —      98,25%
        rede dedicada                   6        5      99,31%

    A linha do meio é a que mandou trocar de abordagem em vez de afinar a que
    havia: o **oráculo** — o melhor limiar por diagrama e cor de casa, escolhido
    com o gabarito na mão — já ficava a 6 pontos do Otsu. A medida não era o
    problema; achar o corte sem rótulo era. Nenhuma regra sem supervisão
    (logaritmo, mediana + MAD, maior salto relativo, limiar fixo sobre medida
    adimensional) passou de 93,6%.

    Uma regressão logística sobre cinco medidas dessas chega a 97,8%. A rede
    sobre o resíduo chega a 99,3% — 11 casas erradas em 1.600, contra 124.
    """
    return {k: bool(p >= 0.5) for k, p in _probabilidade_de_peca(residuo).items()}


#: Nome interno antigo, mantido para quem já importava.
_ocupadas = ocupadas


def _carregar(caminho):
    """(rede, símbolos, temperatura) — o carregamento seguro, num lugar só."""
    if not os.path.isfile(caminho):
        raise ModeloAusente(
            f"{caminho} não existe. Rode `python treinar_diagrama.py`.")
    import torch
    from core.neural_model import RedeDiagrama

    # `weights_only=True` é o carregamento seguro: um `.pth` é um pickle, e sem
    # isso abrir um arquivo de terceiro executa o que estiver dentro.
    d = torch.load(caminho, map_location="cpu", weights_only=True)
    simbolos = tuple(str(s) for s in d["simbolos"])
    rede = RedeDiagrama(len(simbolos))
    rede.load_state_dict(d["pesos"])
    rede.eval()
    return rede, simbolos, float(d.get("temperatura", 1.0)) or 1.0


def _carregar_modelo():
    """(rede das peças, símbolos na ordem das saídas dela, temperatura)."""
    global _modelo
    if _modelo is None:
        _modelo = _carregar(CAMINHO_MODELO)
    return _modelo


def _carregar_ocupacao():
    """
    (rede da ocupação, coluna do 'tem peça', temperatura).

    A coluna sai do arquivo e não é fixada em 1: é a mesma disciplina do
    `simbolos` da rede das peças. Trocar a ordem das duas classes num treino
    futuro inverteria a leitura inteira sem erro nenhum aparecer.
    """
    global _modelo_ocupacao
    if _modelo_ocupacao is None:
        rede, simbolos, temperatura = _carregar(CAMINHO_OCUPACAO)
        if OCUPADA not in simbolos:
            raise ModeloAusente(
                f"{CAMINHO_OCUPACAO} não é um modelo de ocupação: as classes "
                f"dele são {simbolos!r}.")
        _modelo_ocupacao = (rede, simbolos.index(OCUPADA), temperatura)
    return _modelo_ocupacao


def esquecer_modelo() -> None:
    """
    Larga os modelos em memória, para a próxima leitura reler os arquivos (F8.3).

    Existe porque agora dá para treinar sem fechar o programa: sem isto, o
    treino gravaria um `.pth` novo e as leituras seguintes continuariam usando
    a rede velha, em silêncio, até alguém reiniciar.
    """
    global _modelo, _modelo_ocupacao
    _modelo = _modelo_ocupacao = None


def impressao_do_modelo() -> str:
    """A impressão da base com que o modelo foi treinado, ou '' se não a traz."""
    try:
        import torch
        d = torch.load(CAMINHO_MODELO, map_location="cpu", weights_only=True)
        return str(d.get("impressao", ""))
    except Exception:
        # Arquivo ausente, truncado, de outra versão do torch ou de outro
        # formato: para quem só quer a impressão, tudo isso é "não tem".
        # Quem precisa da rede chama `_carregar_modelo`, que levanta.
        return ""


def entrada_da_rede(residuos: Sequence[np.ndarray]):
    """
    Resíduos das casas -> lote `(n, 1, 32, 32)` para a rede.

    **Um lugar só, e isso importa** (F8.3). O treino já teve uma cópia da
    preparação da amostra; duas implementações da mesma conta é a família de
    defeito da F5.2 — o dia em que uma muda, o modelo passa a ser treinado num
    espaço e consultado noutro, sem erro nenhum aparecendo.

    A divisão por 128 e não uma normalização por casa: o resíduo **já** é
    centrado em zero por construção (casa menos fundo), e reescalar cada casa
    pelo próprio máximo apagaria o quanto de tinta ela tem — que é justamente o
    que separa peça cheia de peça vazada.
    """
    import torch

    lote = []
    for r in residuos:
        if r.shape[:2] != (LADO_REDE, LADO_REDE):
            r = cv2.resize(np.asarray(r, dtype=np.float32),
                           (LADO_REDE, LADO_REDE), interpolation=cv2.INTER_AREA)
        lote.append(np.asarray(r, dtype=np.float32) / 128.0)
    return torch.from_numpy(np.stack(lote)).unsqueeze(1)


SIMBOLOS = tuple("BKNPQRbknpqr")

#: O rótulo da casa vazia na base de amostras (F7.5). Não é peça, e por isso não
#: entra em `SIMBOLOS` — quem lê um símbolo espera algo que caiba num FEN.
VAZIA = "."

#: As classes da **base de amostras**, que são treze. Não é a saída de nenhuma
#: das duas redes — a das peças tem doze saídas, a da ocupação tem duas —, e a
#: distinção evita o defeito de ler coluna de rede com índice de pasta.
CLASSES = SIMBOLOS + (VAZIA,)

#: O outro rótulo da rede de ocupação: "tem peça, qualquer que seja". Não é
#: classe da base — nasce no treino, juntando as doze de peça numa só.
OCUPADA = "#"


def _pontuar(residuos: List[np.ndarray]) -> np.ndarray:
    """
    Matriz (casas x 12) com a probabilidade de cada peça.

    As colunas vêm do `simbolos` gravado no modelo, e não da ordem em que a rede
    devolve: um modelo treinado numa base sem dama saía com 11 saídas, e ler a
    coluna 4 como se fosse sempre 'Q' trocaria as peças em silêncio. Classe que
    o modelo não conhece fica em zero, que é o que ela vale.

    **A temperatura entra aqui, e é a F1.9 aplicada a esta base.** Ela divide os
    logitos antes do softmax: não muda nenhuma leitura — a ordem das classes é a
    mesma —, muda o número que a janela de diagramas mostra e usa para pintar de
    laranja o que ficou em dúvida. Sem ela a rede diria 99,9% em quase tudo,
    inclusive no que errou, e o laranja pararia de aparecer.
    """
    import torch

    rede, simbolos, temperatura = _carregar_modelo()
    with torch.no_grad():
        logitos = rede(entrada_da_rede(residuos)) / temperatura
        p = torch.softmax(logitos, dim=1).numpy()

    pontos = np.zeros((len(residuos), len(SIMBOLOS)), np.float32)
    for j, s in enumerate(simbolos):
        if s in SIMBOLOS:
            pontos[:, SIMBOLOS.index(s)] = p[:, j]
    return pontos


# ----------------------------------------------------------------------
# A legalidade arbitra
# ----------------------------------------------------------------------

def _plausivel(simbolos: Sequence[str], casas: Sequence[Tuple[int, int]]) -> bool:
    import collections
    c = collections.Counter(simbolos)
    if c["K"] != 1 or c["k"] != 1:
        return False
    if c["P"] > 8 or c["p"] > 8:
        return False
    if sum(c[s] for s in "PNBRQK") > 16 or sum(c[s] for s in "pnbrqk") > 16:
        return False
    return not any(s in "Pp" and casa[0] in (0, 7)
                   for s, casa in zip(simbolos, casas))


def _arbitrar(pontos: np.ndarray, casas: Sequence[Tuple[int, int]]
              ) -> Tuple[List[str], List[bool]]:
    """
    Ajusta a leitura até a posição parar de ser impossível.

    Sempre troca a casa **mais barata**: a de menor diferença entre a pontuação
    da leitura atual e a da leitura que resolve o problema. É o critério da F1.7
    — a regra estreita o conjunto, o custo decide qual.

    **Cada casa resolvida fica travada, e isso não é zelo.** A primeira versão
    fazia uma passada por restrição, repetindo até estabilizar, e desfazia a
    própria correção: sem rei branco, ela promovia a casa mais barata a `K`;
    na volta seguinte faltava o rei preto, e a mesma casa era outra vez a mais
    barata — agora para virar `k`, porque acabara de perder a pontuação
    original. Oscilava até o teto de voltas e devolvia a leitura inicial. Um
    teste de três casas pegou isso.
    """
    lidos = [SIMBOLOS[i] for i in pontos.argmax(1)]
    mexidas = [False] * len(lidos)
    travadas = set()

    # Em logaritmo, e não na probabilidade crua (F7.4). "Quanto custa trocar
    # esta casa" é uma razão entre evidências, não uma diferença: com a rede
    # confiante, `0,9999 - 0,0000001` empata com `0,999 - 0,001` em ponto
    # flutuante e o "mais barato" passaria a ser o primeiro índice da lista.
    # A diferença dos logaritmos separa os dois casos por uma ordem de grandeza.
    log_pontos = np.log(np.maximum(pontos, 1e-12))

    def custo(i: int, alvo: str) -> float:
        return float(log_pontos[i, SIMBOLOS.index(lidos[i])]
                     - log_pontos[i, SIMBOLOS.index(alvo)])

    def alternativa(i: int, proibidos) -> str:
        for j in np.argsort(pontos[i])[::-1]:
            if SIMBOLOS[j] not in proibidos:
                return SIMBOLOS[j]
        return lidos[i]

    def tirar_peoes_das_pontas():
        for i, s in enumerate(lidos):
            if s in "Pp" and casas[i][0] in (0, 7) and i not in travadas:
                lidos[i] = alternativa(i, "Pp")
                mexidas[i] = True

    tirar_peoes_das_pontas()

    for rei in ("K", "k"):
        outro = "k" if rei == "K" else "K"
        atuais = [i for i, s in enumerate(lidos) if s == rei]

        if len(atuais) == 1:
            travadas.add(atuais[0])
            continue

        if len(atuais) > 1:
            # o mais convincente fica; os outros viram a melhor leitura que não
            # seja rei daquela cor
            manter = max(atuais, key=lambda i: pontos[i, SIMBOLOS.index(rei)])
            for i in atuais:
                if i != manter:
                    lidos[i] = alternativa(i, {rei})
                    mexidas[i] = True
            travadas.add(manter)
            continue

        # nenhum: promove a casa mais barata que não esteja travada nem seja o
        # rei da outra cor — tirá-lo criaria o problema que se está resolvendo
        livres = [i for i in range(len(lidos))
                  if i not in travadas and lidos[i] != outro]
        if not livres:
            continue
        i = min(livres, key=lambda i: custo(i, rei))
        lidos[i] = rei
        mexidas[i] = True
        travadas.add(i)

    # a promoção a rei pode ter deixado um peão de volta numa ponta
    tirar_peoes_das_pontas()
    return lidos, mexidas


# ----------------------------------------------------------------------
# Entrada pública
# ----------------------------------------------------------------------

def ler(imagem, caixa: Optional[Tuple[int, int, int, int]] = None, *,
        orientacao: str = "branca") -> Leitura:
    """
    Lê um diagrama. `imagem` é a página (ou o recorte, com `caixa=None`).

    **`orientacao` é como o diagrama está impresso, não como o FEN sai** (F95).
    Com "preta" as 64 casas são giradas 180° depois de lidas, de modo que
    `Casa.linha` continue querendo dizer "fila 8" e o FEN continue sendo o da
    posição. Quem redesenha o diagrama tem o campo `Leitura.orientacao` para
    reproduzir o desenho do livro.

    Girar depois, e não antes, é o que mantém o árbitro (F1.7) intacto: ele
    proíbe peão nas duas pontas, e as duas pontas continuam sendo as duas
    pontas depois do giro.
    """
    if orientacao not in ("branca", "preta"):
        raise ValueError(f"orientação inválida: {orientacao!r}")
    arr = _cinza(imagem)
    if caixa is None:
        caixa = (0, 0, arr.shape[1], arr.shape[0])
    x1, y1, x2, y2 = caixa
    recorte = arr[max(0, y1):y2, max(0, x1):x2]

    leitura = Leitura(caixa=caixa, orientacao=orientacao)
    if recorte.size == 0 or min(recorte.shape[:2]) < 16:
        leitura.avisos.append("recorte pequeno demais para ser um tabuleiro")
        return leitura

    # O aviso da convenção entra antes de qualquer saída antecipada: `fen()`
    # sempre aplica a convenção, então ela nunca pode sair sem ser declarada.
    leitura.avisos.append(
        "Lado a jogar, roque e en passant não estão no diagrama; o FEN assume "
        "brancas a jogar, sem roque.")

    # Duas redes, em ordem: a da ocupação diz quais casas têm peça (F7.5), a das
    # peças diz qual é (F7.4). Era um limiar de Otsu no lugar da primeira.
    residuo = _residuos(_casas_do_recorte(recorte))
    # A rede da ocupação roda uma vez só: a decisão e a confiança dela saem da
    # mesma probabilidade, e chamar `ocupadas` e `confianca_de_ocupacao` em
    # seguida pagaria a rede duas vezes por tabuleiro.
    probabilidade = _probabilidade_de_peca(residuo)
    ocupada = {k: p >= 0.5 for k, p in probabilidade.items()}
    firmeza = {k: max(p, 1.0 - p) for k, p in probabilidade.items()}
    chaves = [k for k in sorted(residuo) if ocupada[k]]

    def virada(k):
        """A casa impressa em `k`, na fila e coluna que ela é de verdade."""
        return (7 - k[0], 7 - k[1]) if orientacao == "preta" else k

    def vazia(k) -> Casa:
        r, c = virada(k)
        return Casa(r, c, None, confianca_ocupacao=firmeza.get(k, 0.0))

    #: As 64 casas na ordem do tabuleiro, e não na da impressão: quem lê
    #: `leitura.casas[0]` espera a8, esteja o diagrama virado para que lado for.
    def montar(por_casa) -> List[Casa]:
        return sorted(por_casa.values(), key=lambda c: (c.linha, c.coluna))

    if not chaves:
        leitura.avisos.append("nenhuma peça encontrada")
        leitura.casas = montar({(r, c): vazia((r, c))
                                for r in range(8) for c in range(8)})
        return leitura

    pontos = _pontuar([residuo[k] for k in chaves])
    lidos, mexidas = _arbitrar(pontos, chaves)

    por_casa = {k: vazia(k) for k in residuo}
    for k, simbolo, mexida, linha_pontos in zip(chaves, lidos, mexidas, pontos):
        total = float(linha_pontos.sum()) or 1.0
        r, c = virada(k)
        por_casa[k] = Casa(r, c, simbolo,
                           float(linha_pontos[SIMBOLOS.index(simbolo)]) / total,
                           mexida, confianca_ocupacao=firmeza[k])

    leitura.casas = montar(por_casa)

    if orientacao == "preta":
        leitura.avisos.append(
            "O diagrama está impresso do lado das pretas; a posição foi girada "
            "para o FEN sair na convenção.")
    if leitura.arbitradas:
        leitura.avisos.append(
            f"{leitura.arbitradas} casa(s) foram trocadas para a posição deixar "
            f"de ser impossível.")
    if not leitura.plausivel:
        leitura.avisos.append(
            "A posição continua impossível (reis, peões ou contagem). A leitura "
            "está errada em algum lugar.")
    return leitura


#: O piso do porteiro da F58: abaixo disto o diagrama não vira desenho, vira
#: recorte do scan.
#:
#: **A régua é a menor das duas confianças** — a da peça na casa mais fraca e a
#: da ocupação na casa mais fraca —, e não a média de nenhuma delas. Um
#: tabuleiro só está certo se as 64 casas estiverem, e a média deixa 63 casas
#: firmes carregarem a que é moeda.
#:
#: Medido sobre os 346 tabuleiros do split `test` do corpus da F8.4, dos quais
#: 24 saem errados (93,06% de tabuleiro inteiro certo):
#:
#:     corte   barrados  pegos  escapam  certos perdidos
#:     0,00           0      0       24      0    (0,0%)  ← sem porteiro
#:     0,50          10     10       14      0    (0,0%)
#:     0,90          21     17        7      4    (1,2%)
#:     0,95          28     21        3      7    (2,2%)
#:     **0,98**      30     22        2      8    (2,5%)
#:     0,99          34     22        2     12    (3,7%)
#:     0,999         56     22        2     34   (10,6%)
#:
#: O 0,98 é onde a curva vira: pega 22 dos 24 por 2,5% dos certos, e daí para
#: cima o preço sobe sem que mais nenhum erro seja pego. **Um em treze vira um
#: em 173.**
#:
#: A separação da régua é 0,9806 (F51: fração de pares (errado, certo) que ela
#: ordena direito). A média da confiança da peça mede 0,9812 — empate dentro do
#: ruído de 24 tabuleiros —, mas ordena pior onde importa: a 0,50 ela não pega
#: um erro sequer, enquanto esta pega 10 **sem custar um certo**. São as casas
#: em que a rede jogou cara ou coroa, e a média as dilui.
#:
#: Os 2 que escapam escapam de tudo: as duas réguas só os pegam acima de 0,9995,
#: com 14% dos certos junto. São leituras erradas e confiantes, e nenhum sinal
#: que a `ler` produz hoje as distingue.
PISO_DO_PORTEIRO = 0.98


def confiavel(leitura: Leitura, *, piso: float = PISO_DO_PORTEIRO
              ) -> Tuple[bool, str]:
    """
    (esta leitura pode virar desenho?, por que não) — o porteiro da F58.

    **Existe porque o desenho mente bem.** Recortado do scan, o diagrama errado
    ao menos mostra o que o livro imprimiu; redesenhado a partir de uma leitura
    errada, ele sai com a mesma nitidez nas 64 casas e nada denuncia a peça
    trocada. Quem não passa aqui não é descartado — cai para o recorte, que é o
    que a F2.6 já exportava.

    A implausibilidade é veto seco, e não entra na conta do piso: posição
    impossível é leitura errada por definição, então barrá-la nunca custa um
    tabuleiro certo. Nos 346 do corpus ela não disparou uma vez — o árbitro
    (F1.7) conserta a posição antes —, e está aqui pelo caso que o corpus não
    tem: diagrama mal recortado, em que o árbitro não dá conta.
    """
    if not leitura.casas:
        return False, "não deu para ler o diagrama"

    # O tabuleiro vazio vem antes da plausibilidade porque ele também é
    # impossível — não tem rei nenhum —, e "não achei peça" diz o que houve,
    # enquanto "posição impossível" manda procurar um erro que não existe.
    pecas = [c.confianca for c in leitura.casas if c.simbolo]
    if not pecas:
        return False, "nenhuma peça encontrada no diagrama"

    if not leitura.plausivel:
        return False, "a posição lida é impossível"

    pior_peca = min(pecas)
    pior_ocupacao = min(c.confianca_ocupacao for c in leitura.casas)
    if min(pior_peca, pior_ocupacao) < piso:
        qual = ("a peça" if pior_peca <= pior_ocupacao else "haver peça")
        return False, (f"{qual} na casa mais fraca ficou em "
                       f"{min(pior_peca, pior_ocupacao):.0%}")
    return True, ""


def ler_pagina(imagem, boxes: Sequence[BoxEntry],
               classificar: Optional[Callable] = None) -> List[Leitura]:
    """
    Todos os diagramas de uma página, na ordem de leitura.

    Mede a escala de texto e a entrega a `localizar` (F7.6). É o passo que
    faltava: a mediana das alturas dos boxes, que `localizar` usava sozinha, não
    mede o texto numa página que é quase só diagrama — ver o docstring de lá.
    Custa uma binarização da página, e é o que separa 6 diagramas de 12.

    **A binarização que ela já pagava passou a ser usada duas vezes** (F95): ela
    mede a escala e abre a segunda passada de `localizar`, a que acha o
    tabuleiro impresso dentro de um painel. Não é custo novo — é o mesmo `th`.

    `classificar` é opcional e é o que separa "há coordenadas impressas" de "as
    coordenadas dizem isto". Sem ele, os rótulos ainda são **achados** (a prova
    é geométrica), o título sai só como retângulo e a orientação fica `None` —
    com ele, o título vira texto e a orientação é decidida.

    **`boxes` vazio não quer dizer página vazia** (F96). É a resposta de
    `boxes_antes_do_descarte` quando a página passa do `MAX_CONTORNOS_DE_TEXTO`,
    e a página que faz isso não é necessariamente uma fotografia: a 96 do
    Yusupov dá 85.903 contornos sendo prosa em duas colunas com um diagrama e um
    painel de sumário — quem os produz é a trama do painel. Sem teto, o merge
    dessa página custa 63 s; com teto, ela chega aqui sem caixa nenhuma.

    Nesse caso, e **só** nesse, quem acha o tabuleiro é `deteccao_de_tabuleiro`,
    que não passa por caractere nenhum e responde em 0,76 s. A porta é estreita
    de propósito: com `boxes` na mão, o `localizar` é melhor — 50 de 50 no
    gabarito da F95 contra 51 com um inventado do outro (ver F96). O detector
    entra onde o `localizar` não tem do que se alimentar, não no lugar dele.

    **E entra com a peneira da F95 armada**, que é o que separa o tabuleiro do
    retângulo grande qualquer. Sem ela, a página 134 do Yusupov ganha um
    "diagrama" de 1.521x1.571 px que é o cabeçalho do capítulo mais a prosa — e
    ainda sai pela borda de cima. Medido nas quatro páginas de trama do livro,
    `pontuacao_de_tabuleiro` sobre o recorte endireitado:

    | | menor | maior |
    |---|---:|---:|
    | os 7 tabuleiros de verdade | **40,89** | 55,28 |
    | os 2 retângulos inventados | 0,10 | **1,53** |

    O vão é de vinte e seis vezes, e o piso da F95 (12,0) cai no meio dele. O
    preço é conhecido e está na F96: onde o recorte do detector pega a moldura
    junto, como nos diagramas do Darcy Lima, a peneira derruba o diagrama bom.
    Numa página que chega aqui sem caixa nenhuma, porém, o outro prato da
    balança é vazio: sem o detector não há diagrama nenhum, e com ele sem
    peneira haveria um errado.
    """
    from core import preprocess

    arr = _cinza(imagem)
    binaria = preprocess.remover_textura(arr, preprocess.binarize(arr, "auto"))
    escala = preprocess.escala_de_texto(binaria)

    caixas = localizar(boxes, escala=escala, imagem=arr, binaria=binaria)
    if not caixas and not boxes:
        from core import deteccao_de_tabuleiro as det
        caixas = det.localizar(arr, piso_do_xadrez=PISO_DO_XADREZ)

    leituras = []
    for caixa in caixas:
        rotulos = ler_rotulos(arr, caixa, escala, classificar)
        leitura = ler(imagem, caixa,
                      orientacao=rotulos.orientacao or "branca")
        leitura.rotulos = rotulos
        leitura.titulo = ler_titulo(arr, caixa, escala, classificar,
                                    boxes=boxes, rotulos=rotulos)
        leituras.append(leitura)
    return leituras
