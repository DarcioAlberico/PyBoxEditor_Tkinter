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
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

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

    @property
    def nome(self) -> str:
        return f"{'abcdefgh'[self.coluna]}{8 - self.linha}"


@dataclass
class Leitura:
    """O que se conseguiu ler de um diagrama."""

    caixa: Tuple[int, int, int, int]         # x1, y1, x2, y2 na página
    casas: List[Casa] = field(default_factory=list)
    avisos: List[str] = field(default_factory=list)

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
# Achar o diagrama na página
# ----------------------------------------------------------------------

def localizar(boxes: Sequence[BoxEntry],
              descartados: Optional[Sequence[BoxEntry]] = None,
              escala: Optional[int] = None
              ) -> List[Tuple[int, int, int, int]]:
    """
    As caixas de diagrama, a partir dos contornos da página.

    `boxes` são os contornos antes do descarte da F1.8 e `descartados` o que ela
    tirou; passando só `boxes`, o descarte é refeito aqui. O diagrama é o que
    caiu por ser grande **e** é quase quadrado: um travessão também é descartado
    por largura, e não é tabuleiro.

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
        l, a = max(1, b.width), max(1, b.height)
        if l < minimo or a < minimo:
            continue
        if max(l / a, a / l) > TOLERANCIA_QUADRADO:
            continue
        saida.append((b.x1, b.y1, b.x2, b.y2))
    saida.sort(key=lambda c: (c[1], c[0]))
    return saida


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
    import torch

    chaves = sorted(residuo)
    rede, coluna, temperatura = _carregar_ocupacao()
    with torch.no_grad():
        p = torch.softmax(rede(entrada_da_rede([residuo[k] for k in chaves]))
                          / temperatura, dim=1).numpy()
    return {k: bool(p[i, coluna] >= 0.5) for i, k in enumerate(chaves)}


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

def ler(imagem, caixa: Optional[Tuple[int, int, int, int]] = None) -> Leitura:
    """Lê um diagrama. `imagem` é a página (ou o recorte, com `caixa=None`)."""
    arr = np.asarray(imagem)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    if caixa is None:
        caixa = (0, 0, arr.shape[1], arr.shape[0])
    x1, y1, x2, y2 = caixa
    recorte = arr[max(0, y1):y2, max(0, x1):x2]

    leitura = Leitura(caixa=caixa)
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
    ocupada = ocupadas(residuo)
    chaves = [k for k in sorted(residuo) if ocupada[k]]

    if not chaves:
        leitura.avisos.append("nenhuma peça encontrada")
        leitura.casas = [Casa(r, c, None) for r in range(8) for c in range(8)]
        return leitura

    pontos = _pontuar([residuo[k] for k in chaves])
    lidos, mexidas = _arbitrar(pontos, chaves)

    por_casa = {}
    for k, simbolo, mexida, linha_pontos in zip(chaves, lidos, mexidas, pontos):
        total = float(linha_pontos.sum()) or 1.0
        por_casa[k] = Casa(k[0], k[1], simbolo,
                           float(linha_pontos[SIMBOLOS.index(simbolo)]) / total,
                           mexida)

    leitura.casas = [por_casa.get((r, c)) or Casa(r, c, None)
                     for r in range(8) for c in range(8)]

    if leitura.arbitradas:
        leitura.avisos.append(
            f"{leitura.arbitradas} casa(s) foram trocadas para a posição deixar "
            f"de ser impossível.")
    if not leitura.plausivel:
        leitura.avisos.append(
            "A posição continua impossível (reis, peões ou contagem). A leitura "
            "está errada em algum lugar.")
    return leitura


def ler_pagina(imagem, boxes: Sequence[BoxEntry]) -> List[Leitura]:
    """
    Todos os diagramas de uma página, na ordem de leitura.

    Mede a escala de texto e a entrega a `localizar` (F7.6). É o passo que
    faltava: a mediana das alturas dos boxes, que `localizar` usava sozinha, não
    mede o texto numa página que é quase só diagrama — ver o docstring de lá.
    Custa uma binarização da página, e é o que separa 6 diagramas de 12.
    """
    from core import preprocess

    arr = np.asarray(imagem)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    escala = preprocess.escala_de_texto(
        preprocess.remover_textura(arr, preprocess.binarize(arr, "auto")))
    return [ler(imagem, caixa) for caixa in localizar(boxes, escala=escala)]
