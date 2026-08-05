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

HOG sobre o resíduo, PCA para 32 dimensões, voto dos 3 vizinhos mais próximos
entre 361 amostras rotuladas à mão (`training_data_diagrama/`, construídas por
agrupamento e inspeção). Ver `treinar_diagrama.py`.

**Duas correções que pareciam óbvias e pioraram**, medidas contra 128 casas
transcritas à mão:

| variante | acerto por casa |
|---|---:|
| resíduo + HOG (o de hoje) | **94,5%** |
| \\+ canal de sinal para a cor da peça | 90,6% |
| detecção por energia de borda | 93,0% |

A primeira parecia certa: o HOG usa orientação módulo 180 e magnitude absoluta,
logo descarta o sinal, e torre branca virava torre preta. Dar-lhe o sinal por
fora **subiu** os erros de cor de 3 para 5. A segunda também: peça branca em casa
clara quase some no resíduo (é branca por dentro, traço fino em volta) e a borda
a acha — mas troca 3 omissões por 4 falsos positivos.

## A legalidade arbitra, como na F1.7

Uma posição de xadrez real tem exatamente um rei de cada cor, no máximo oito
peões por lado, nenhum peão na 1a ou 8a fila e no máximo dezesseis peças por
cor. São restrições sobre a posição **inteira**, mais fortes que as da F1.7 —
que valiam para um lance de cada vez.

`_arbitrar` troca a leitura da casa que custa menos: a de menor diferença entre a
pontuação da leitura atual e a da leitura que resolve o problema. Medido, leva de
17 para 23 os 25 diagramas cuja posição é possível.

## O que este módulo NÃO entrega

**94,5% por casa são ~3,5 casas erradas em 64.** Uma posição com três casas
erradas é uma posição errada. Isto é um **rascunho para conferir**, não um
extrator com autoridade — e a interface tem de mostrar assim, do mesmo jeito que
a F3.6 mostra o lote antes de aplicar.

Passar nas provas de legalidade **não é prova de estar certo**: elas contam
peças, não reconhecem bispo lido como peão. Por isso o número que vale é o das
128 casas transcritas à mão, e não os 23/25.

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

CAMINHO_MODELO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "dados", "diagrama_modelo.npz")

_HOG = cv2.HOGDescriptor((LADO, LADO), (12, 12), (6, 6), (6, 6), 9)
_modelo = None


class ModeloAusente(RuntimeError):
    """O banco de peças não foi encontrado. Rode `treinar_diagrama.py`."""


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
              descartados: Optional[Sequence[BoxEntry]] = None
              ) -> List[Tuple[int, int, int, int]]:
    """
    As caixas de diagrama, a partir dos contornos da página.

    `boxes` são os contornos antes do descarte da F1.8 e `descartados` o que ela
    tirou; passando só `boxes`, o descarte é refeito aqui. O diagrama é o que
    caiu por ser grande **e** é quase quadrado: um travessão também é descartado
    por largura, e não é tabuleiro.
    """
    from core.services.box_service import BoxService

    if descartados is None:
        ficam = {id(b) for b in BoxService.descartar_blocos_nao_texto(list(boxes))}
        descartados = [b for b in boxes if id(b) not in ficam]

    if not boxes:
        return []
    alturas = sorted(b.height for b in boxes)
    minimo = max(1, alturas[len(alturas) // 2]) * MINIMO_EM_CARACTERES

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


def _residuos(quadros: dict) -> Tuple[dict, dict]:
    """
    (resíduo por casa, ocupada?) — o fundo é a mediana das casas da mesma cor.

    O limiar entre vazia e ocupada é de Otsu **por diagrama e por cor de casa**.
    Um limiar global não serve: nos diagramas de casa hachurada o resíduo de uma
    casa vazia chega a 60, acima do resíduo de peça dos diagramas de casa
    chapada. Com o limiar local, a contagem de peças ficou entre 12 e 28 nos 25
    diagramas — nenhuma impossível.
    """
    residuo, ocupada = {}, {}
    for paridade in (0, 1):
        chaves = [(r, c) for r in range(8) for c in range(8)
                  if (r + c) % 2 == paridade]
        pilha = np.stack([quadros[k] for k in chaves])
        fundo = np.median(pilha, axis=0)
        forca = {k: float(np.abs(quadros[k] - fundo).mean()) for k in chaves}

        # Segunda passada: a mediana acima inclui ~40% de peças e enviesa o
        # fundo. Refazê-la só com as vazias limpa o modelo.
        vazias = [k for k in chaves if forca[k] <= _otsu(list(forca.values()))]
        if len(vazias) >= 4:
            fundo = np.median(np.stack([quadros[k] for k in vazias]), axis=0)
            forca = {k: float(np.abs(quadros[k] - fundo).mean()) for k in chaves}

        limiar = _otsu(list(forca.values()))
        for k in chaves:
            residuo[k] = quadros[k] - fundo
            ocupada[k] = forca[k] > limiar
    return residuo, ocupada


def _carregar_modelo():
    global _modelo
    if _modelo is None:
        if not os.path.isfile(CAMINHO_MODELO):
            raise ModeloAusente(
                f"{CAMINHO_MODELO} não existe. Rode `python treinar_diagrama.py`.")
        d = np.load(CAMINHO_MODELO, allow_pickle=False)
        _modelo = (d["media"], d["base"], d["amostras"],
                   [str(s) for s in d["simbolos"]])
    return _modelo


def _descritor(residuo: np.ndarray) -> np.ndarray:
    normal = cv2.normalize(residuo, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    v = _HOG.compute(normal).ravel()
    return v / (np.linalg.norm(v) + 1e-6)


SIMBOLOS = tuple("BKNPQRbknpqr")


def _pontuar(residuos: List[np.ndarray], vizinhos: int = 3) -> np.ndarray:
    """Matriz (casas x 12) com o voto dos `vizinhos` mais próximos."""
    media, base, amostras, rotulos = _carregar_modelo()
    X = np.stack([_descritor(r) for r in residuos])
    X = (X - media) @ base.T
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-6

    similaridade = X @ amostras.T
    pontos = np.zeros((len(residuos), len(SIMBOLOS)), np.float32)
    for i in range(len(residuos)):
        for j in np.argsort(similaridade[i])[::-1][:vizinhos]:
            pontos[i, SIMBOLOS.index(rotulos[j])] += max(0.0, float(similaridade[i, j]))
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

    def custo(i: int, alvo: str) -> float:
        return float(pontos[i, SIMBOLOS.index(lidos[i])]
                     - pontos[i, SIMBOLOS.index(alvo)])

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

    quadros = _casas_do_recorte(recorte)
    residuo, ocupada = _residuos(quadros)
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
    """Todos os diagramas de uma página, na ordem de leitura."""
    return [ler(imagem, caixa) for caixa in localizar(boxes)]
