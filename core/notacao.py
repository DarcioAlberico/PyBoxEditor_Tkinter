"""
Validação da notação de xadrez contra as regras do jogo.

A ideia veio do DocuVision-AI, mas o uso aqui é outro: eles pontuam qual bloco
da página é a notação; nós usamos a legalidade para **decidir entre leituras**.
Numa posição típica existem ~30 lances legais, contra centenas de cadeias que o
OCR poderia produzir — a legalidade descarta a maioria esmagadora das leituras
erradas sem treinar nada.

**Não copiar o `fix_chess_moves` deles**, que é o oposto disto:

    text = re.sub(r"2d3", "Bd3", text)      # remendo decorado para um corpus

Duas coisas foram medidas antes de escrever este módulo, e as duas mudaram o
desenho:

1. **A tabela de exemplos do ROADMAP estava errada.** Ela dizia que, após
   `1.e4 e5 2.Nf3 Nc6`, a legalidade separaria `Bb4`/`Bh4` e `Nf3`/`Nf8`. Nessa
   posição os dois lados de todos os pares são ilegais — `Nf3` porque o cavalo
   já está em f3. O princípio vale; os exemplos é que não tinham sido rodados.

2. **Espaço não dá para inferir só pela lacuna.** Nesta fonte os algarismos têm
   avanço tabular: a lacuna mediana depois de '1' é 10 px, contra 1–2 px depois
   de letras. Qualquer limiar que preserve os espaços de verdade parte "15" em
   "1 5", e qualquer limiar que preserve "15" cola "c4 c5" em "c4c5". Medido na
   página real (1.404 boxes):

       limiar        dígitos partidos    palavras coladas
       0,5x largura        71                   0
       0,8x largura        38                   vários
       1,2x largura        23                   muitos

   Daí a remontagem do §`_remontar_numeros`: um limiar normal para tudo, e uma
   segunda passada que só junta palavras **inteiramente numéricas**.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import chess

from core.box_model import BoxEntry
from core.services.box_service import BoxService


# Figurina -> letra. O livro usa um conjunto só para os dois lados (ver F1.1),
# então o glifo não diz a cor: quem diz é a paridade do número do lance, que o
# tabuleiro acompanha de graça.
FIGURINAS = {
    "♔": "K", "♕": "Q", "♖": "R", "♗": "B", "♘": "N",
    "♚": "K", "♛": "Q", "♜": "R", "♝": "B", "♞": "N",
}

# Símbolos de anotação que aparecem colados no lance e não fazem parte dele.
SUFIXOS = "!?+#±∓□■△▼∞²³=-–—,;:.)("

# Sem âncora `^`: `Pattern.match(texto, pos)` já ancora na posição, mas um `^`
# no padrão continua exigindo o começo da string e faz o casamento posicional
# falhar sempre — era o que impedia "Rb725.Rd2" de ser partido em "Rb7" + "25.".
RE_NUMERO = re.compile(r"(\d{1,3})\.(\.\.)?")

# Fatia da largura mediana de caractere acima da qual a lacuna vira espaço.
LIMIAR_ESPACO = 0.5
# Na remontagem de números, lacuna máxima (em larguras medianas) que ainda junta.
LIMIAR_NUMERO = 1.4


@dataclass
class Simbolo:
    """Um caractere lido, amarrado ao box de onde veio."""
    char: str
    indice: int          # posição no vetor original de boxes
    confianca: float = 0.0
    fonte: str = ""


@dataclass
class Palavra:
    simbolos: List[Simbolo]

    @property
    def texto(self) -> str:
        return "".join(s.char for s in self.simbolos)

    def __len__(self):
        return len(self.simbolos)


@dataclass
class Correcao:
    indice_box: int
    de: str
    para: str
    lance_lido: str
    lance_correto: str

    def __str__(self):
        return (f"box {self.indice_box}: {self.de!r} -> {self.para!r} "
                f"({self.lance_lido} -> {self.lance_correto})")


@dataclass
class LanceLido:
    texto: str
    simbolos: List[Simbolo]
    numero: Optional[int]
    brancas: bool
    situacao: str                     # legal | corrigido | ambiguo | perdido
    correto: Optional[str] = None
    candidatos: List[str] = field(default_factory=list)


@dataclass
class Analise:
    lances: List[LanceLido] = field(default_factory=list)
    correcoes: List[Correcao] = field(default_factory=list)
    partidas: int = 0
    dessincronizou: int = 0

    def contar(self, situacao: str) -> int:
        return sum(1 for l in self.lances if l.situacao == situacao)

    def resumo(self) -> str:
        if not self.lances:
            return "Nenhuma notação de xadrez encontrada na página."
        partes = [f"{len(self.lances)} lances lidos em {self.partidas} sequência(s)",
                  f"{self.contar('legal')} já legais",
                  f"{self.contar('corrigido')} corrigidos pela legalidade",
                  f"{self.contar('ambiguo')} ambíguos (mais de um lance legal casa)",
                  f"{self.contar('perdido')} sem solução"]
        return "; ".join(partes)


# ----------------------------------------------------------------------
# Dos boxes ao texto
# ----------------------------------------------------------------------

def _linhas_de_boxes(boxes: Sequence[BoxEntry]) -> List[List[Simbolo]]:
    """Agrupa em linhas de texto, na ordem de leitura, preservando os índices."""
    if not boxes:
        return []

    # sort_boxes_reading_order devolve os MESMOS objetos reordenados (inclusive
    # tratando páginas em duas colunas, F1.6), então dá para recuperar o índice
    # original por identidade em vez de reimplementar a ordenação aqui.
    posicao = {id(b): i for i, b in enumerate(boxes)}
    ordenados = BoxService.sort_boxes_reading_order(list(boxes))

    linhas: List[List[BoxEntry]] = []
    atual: List[BoxEntry] = []
    for b in ordenados:
        if not atual:
            atual = [b]
            continue
        fundo = sum(i.y2 for i in atual) / len(atual)
        if (b.y1 + b.y2) / 2 <= fundo + (b.y2 - b.y1) * 0.2:
            atual.append(b)
        else:
            linhas.append(atual)
            atual = [b]
    if atual:
        linhas.append(atual)

    return [[Simbolo(FIGURINAS.get(b.char, b.char), posicao[id(b)],
                     getattr(b, "confidence", 0.0), getattr(b, "source", ""))
             for b in linha]
            for linha in linhas]


def _largura_mediana(boxes: Sequence[BoxEntry]) -> float:
    larguras = sorted(b.x2 - b.x1 for b in boxes if b.char)
    if not larguras:
        return 1.0
    return float(larguras[len(larguras) // 2]) or 1.0


def _palavras_da_linha(linha: List[Simbolo], boxes: Sequence[BoxEntry],
                       largura: float) -> List[Palavra]:
    """
    Quebra a linha em palavras pela lacuna horizontal.

    Boxes sem caractere não viram símbolo, mas **ocupam espaço**: a lacuna entre
    dois vizinhos é a maior das lacunas do caminho, não a distância direta. Sem
    isso, esvaziar um box (que é como a correção remove um glifo fantasma)
    abriria um espaço no meio da palavra — "Nf6" viraria "N f6".
    """
    if not linha:
        return []
    palavras: List[Palavra] = []
    atual: List[Simbolo] = []
    lacuna = 0.0
    anterior: Optional[Simbolo] = None

    for s in linha:
        if anterior is not None:
            lacuna = max(lacuna,
                         boxes[s.indice].x1 - boxes[anterior.indice].x2)
        anterior = s
        if not s.char:
            continue
        if not atual:
            atual = [s]
        elif lacuna > LIMIAR_ESPACO * largura:
            palavras.append(Palavra(atual))
            atual = [s]
        else:
            atual.append(s)
        lacuna = 0.0

    if atual:
        palavras.append(Palavra(atual))
    return palavras


def _remontar_numeros(palavras: List[Palavra], boxes: Sequence[BoxEntry],
                      largura: float) -> List[Palavra]:
    """
    Junta palavras que a lacuna partiu **dentro de um número**.

    Só age quando a palavra da esquerda é toda de algarismos e a da direita
    começa por algarismo ou ponto: é exatamente o caso medido (avanço tabular
    dos dígitos) e não encosta em prosa. "20 1 0" vira "2010", "1 5.Rxe6" vira
    "15.Rxe6", e "Game 85" continua "Game 85" porque "Game" não é numérica.
    """
    if not palavras:
        return []
    saida = [palavras[0]]
    for p in palavras[1:]:
        esquerda = saida[-1].texto
        direita = p.texto
        lacuna = boxes[p.simbolos[0].indice].x1 - boxes[saida[-1].simbolos[-1].indice].x2
        if (esquerda.isdigit() and direita[:1].isdigit() or
                esquerda.isdigit() and direita[:1] == "."):
            if lacuna <= LIMIAR_NUMERO * largura:
                saida[-1] = Palavra(saida[-1].simbolos + p.simbolos)
                continue
        saida.append(p)
    return saida


def palavras_da_pagina(boxes: Sequence[BoxEntry]) -> List[List[Palavra]]:
    """Palavras por linha, na ordem de leitura."""
    largura = _largura_mediana(boxes)
    return [_remontar_numeros(_palavras_da_linha(linha, boxes, largura),
                              boxes, largura)
            for linha in _linhas_de_boxes(boxes)]


def texto_da_pagina(boxes: Sequence[BoxEntry]) -> str:
    return "\n".join(" ".join(p.texto for p in linha)
                     for linha in palavras_da_pagina(boxes))


# ----------------------------------------------------------------------
# Da palavra aos lances
# ----------------------------------------------------------------------

@dataclass
class Pedaco:
    """Um trecho de palavra já classificado."""
    tipo: str                # numero | lance | outro
    texto: str
    simbolos: List[Simbolo]
    numero: Optional[int] = None
    reticencias: bool = False


RE_CASA = re.compile(r"[a-h][1-8]")


# O SAN mais longo em uso é "exd8=Q+", com 7. Um pouco de folga cobre o lixo do
# OCR sem deixar palavra de prosa passar.
TAMANHO_MAXIMO_LANCE = 8
# Primeiro caractere possível de um lance: peça, coluna ou roque.
INICIAIS = set("KQRBNabcdefgh0O")


def parece_lance(texto: str) -> bool:
    """
    Peneira barata: tem cara de lance?

    Exige uma casa (`[a-h][1-8]`) ou um roque, mais tamanho e inicial
    plausíveis. É o que separa "N□f6", que é um lance sujo de OCR, de
    "counterplay", que é prosa — sem isso, toda palavra de texto corrido viraria
    um lance ilegal e derrubaria o tabuleiro.

    O tamanho e a inicial não são enfeite: "Antakya2010" tem "a2" dentro e
    passaria só pela casa.
    """
    limpo = texto.strip(SUFIXOS)
    if not limpo or len(limpo) > TAMANHO_MAXIMO_LANCE:
        return False
    if limpo.upper().replace("0", "O") in ("O-O", "O-O-O"):
        return True
    return limpo[0] in INICIAIS and bool(RE_CASA.search(limpo))


def _fatiar(palavra: Palavra) -> List[Pedaco]:
    """
    Divide a palavra em números de lance e candidatos a lance.

    Não usa expressão regular para reconhecer o lance. A primeira versão casava
    a forma exata do SAN (`[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8]...`) e quebrava no
    primeiro caractere errado: com o `□` que o classificador insere em "N□f6" o
    padrão não casa nada, o lance some e o tabuleiro se perde no primeiro lance
    da página — medido. Como todo lance vai ser confrontado com os lances legais
    de qualquer modo, o pedaço vai inteiro e é a legalidade que decide.
    """
    pedacos: List[Pedaco] = []
    texto = palavra.texto
    i = 0

    def emitir(tipo, ini, fim, **kw):
        pedacos.append(Pedaco(tipo, texto[ini:fim], palavra.simbolos[ini:fim], **kw))

    while i < len(texto):
        m = RE_NUMERO.match(texto, i)
        if m:
            emitir("numero", i, m.end(), numero=int(m.group(1)),
                   reticencias=bool(m.group(2)))
            i = m.end()
            continue

        # Onde termina este pedaço: no próximo número de lance embutido. Um
        # espaço perdido cola "Rb7" e "25.Rd2" numa palavra só; o corte válido é
        # o primeiro que deixa um lance plausível à esquerda — cortar em "725."
        # deixaria "Rb", que não é lance nenhum.
        fim = len(texto)
        for pos in range(i + 1, len(texto)):
            if RE_NUMERO.match(texto, pos) and parece_lance(texto[i:pos]):
                fim = pos
                break

        pedaco = texto[i:fim]
        nucleo = pedaco.strip(SUFIXOS)
        if nucleo and parece_lance(nucleo):
            ini_nucleo = i + pedaco.index(nucleo)
            if ini_nucleo > i:
                emitir("outro", i, ini_nucleo)
            emitir("lance", ini_nucleo, ini_nucleo + len(nucleo))
            if ini_nucleo + len(nucleo) < fim:
                emitir("outro", ini_nucleo + len(nucleo), fim)
        else:
            emitir("outro", i, fim)
        i = fim

    return pedacos


# ----------------------------------------------------------------------
# Custo de trocar uma leitura por outra
# ----------------------------------------------------------------------

def custo_da_troca(lido: str, candidato: str,
                   confiancas: Sequence[float]) -> float:
    """
    Quanto "custa" aceitar que `lido` era, na verdade, `candidato`.

    Distância de edição ponderada. Substituir um caractere custa a confiança que
    o modelo tinha nele — é a dependência da F3.2: sem confiança gravada, todo
    caractere pesaria igual e a correção seria chute. Inserir custa pouco (0,45):
    na página real o erro dominante é caractere **perdido** — "Bxe5" lido "Be5",
    "Qxf4" lido "Qx4".
    """
    CUSTO_INSERIR = 0.45
    CUSTO_REMOVER = 0.8

    n, m = len(lido), len(candidato)
    conf = list(confiancas) + [0.5] * max(0, n - len(confiancas))

    # linha 0: inserir todo o candidato
    anterior = [j * CUSTO_INSERIR for j in range(m + 1)]
    for i in range(1, n + 1):
        # Caractere sem confiança conhecida (veio de .box, F3.2) pesa meio.
        peso = conf[i - 1] if conf[i - 1] > 0 else 0.5
        atual = [anterior[0] + CUSTO_REMOVER]
        for j in range(1, m + 1):
            troca = anterior[j - 1] + (0.0 if lido[i - 1] == candidato[j - 1]
                                       else peso)
            atual.append(min(troca,
                             anterior[j] + CUSTO_REMOVER,
                             atual[j - 1] + CUSTO_INSERIR))
        anterior = atual
    return anterior[m]


# ----------------------------------------------------------------------
# Análise
# ----------------------------------------------------------------------

# Acima disto a "correção" já não é leitura ruim, é outro lance.
CUSTO_MAXIMO = 1.6
# O melhor candidato precisa ganhar do segundo por esta folga.
FOLGA_MINIMA = 0.35


def _melhor_lance_legal(board: chess.Board, lido: str,
                        confiancas: Sequence[float]) -> Tuple[Optional[str], List[str], float]:
    """(melhor, empatados, custo) entre os lances legais da posição."""
    pontuados = []
    for movimento in board.legal_moves:
        san = board.san(movimento)
        limpo = san.rstrip("+#")
        pontuados.append((min(custo_da_troca(lido, san, confiancas),
                              custo_da_troca(lido, limpo, confiancas)), san))
    if not pontuados:
        return None, [], float("inf")
    pontuados.sort()
    melhor_custo, melhor = pontuados[0]
    empatados = [s for c, s in pontuados if c <= melhor_custo + 1e-9]
    return melhor, empatados, melhor_custo


def _numero_da_vez(board: chess.Board) -> Tuple[int, bool]:
    return board.fullmove_number, board.turn == chess.WHITE


def analisar(boxes: Sequence[BoxEntry]) -> Analise:
    """
    Lê a notação da página e confronta cada lance com as regras.

    Quando um lance não é legal, procura entre os lances legais da posição o que
    melhor explica a leitura. Só aceita se um único candidato ganhar com folga —
    a legalidade **estreita** o conjunto, nem sempre decide (`Nbd2` e `Nfd2`
    podem ser ambos legais).

    Quando não dá para decidir, o tabuleiro é abandonado até o próximo número de
    lance conhecido. Continuar com uma posição errada produziria correções
    confiantes e falsas, que é pior que não corrigir.

    **Variantes.** Metade do texto destes livros são alternativas ao lance
    jogado — "12.Re1 Qa5 12...Ra6; 12...Ra7; 12...Nb6 13.Qc2". Lidas em
    sequência, todas menos a primeira seriam ilegais, e o corretor produziria
    lixo. Cada lance jogado guarda a posição de antes; um número de lance que já
    passou rebobina para lá. A busca é **de trás para frente**, o que faz a
    variante aninhada rebobinar para dentro da variante, e não para a linha
    principal.
    """
    analise = Analise()
    board: Optional[chess.Board] = None
    certo = False
    # Posições possíveis para o próximo lance. Vazia = usar `board`.
    pendentes: List[chess.Board] = []
    # (numero, brancas, posição ANTES do lance), na ordem em que apareceram.
    historico: List[Tuple[int, bool, chess.Board]] = []
    pilha: List[Tuple[Optional[chess.Board], bool]] = []   # parênteses

    for linha in palavras_da_pagina(boxes):
        for palavra in linha:
            for pedaco in _fatiar(palavra):
                if pedaco.tipo == "outro":
                    if pedaco.texto == "(":
                        pilha.append((board.copy() if board else None, certo))
                    elif pedaco.texto == ")" and pilha:
                        board, certo = pilha.pop()
                        pendentes = []
                    continue

                if pedaco.tipo == "numero":
                    if pedaco.numero == 1 and not pedaco.reticencias:
                        board, certo, pendentes = chess.Board(), True, []
                        historico.clear()
                        analise.partidas += 1
                        continue
                    pendentes = _posicoes_possiveis(
                        board, historico,
                        (pedaco.numero, not pedaco.reticencias))
                    if not pendentes:
                        board, certo = None, False
                    continue

                base = pendentes or ([board] if board is not None else [])
                pendentes = []
                if not base:
                    continue

                lido = pedaco.texto
                confs = [s.confianca for s in pedaco.simbolos]

                # Uma posição em que o lance já é legal decide entre as
                # candidatas: é o desempate mais barato que existe, e o único
                # que não depende de heurística de fonte.
                viaveis = [(b, b.parse_san(lido)) for b in base
                           if _tenta(b, lido) is not None]
                if viaveis:
                    board, movimento = viaveis[0]
                    if len(base) > 1:
                        # Só volta a ser certo se uma única candidata explicou.
                        certo = len(viaveis) == 1
                    analise.lances.append(
                        LanceLido(lido, pedaco.simbolos, None,
                                  board.turn == chess.WHITE, "legal"))
                    historico.append((*_numero_da_vez(board), board.copy()))
                    board.push(movimento)
                    continue

                # Nenhuma candidata aceita a leitura: pode ser erro de OCR.
                # Com mais de uma candidata não dá para saber de qual posição
                # partir, então nada é corrigido — só reportado.
                if len(base) > 1:
                    certo = False
                board = base[0]
                brancas = board.turn == chess.WHITE

                melhor, empatados, custo = _melhor_lance_legal(board, lido, confs)
                segundo = float("inf")
                if melhor is not None:
                    custos = sorted(
                        min(custo_da_troca(lido, board.san(m), confs),
                            custo_da_troca(lido, board.san(m).rstrip("+#"), confs))
                        for m in board.legal_moves)
                    segundo = custos[1] if len(custos) > 1 else float("inf")

                decidiu = (melhor is not None and len(empatados) == 1
                           and len(base) == 1 and certo
                           and custo <= CUSTO_MAXIMO
                           and segundo - custo >= FOLGA_MINIMA)

                if decidiu:
                    analise.lances.append(
                        LanceLido(lido, pedaco.simbolos, None, brancas,
                                  "corrigido", melhor, empatados))
                    analise.correcoes.extend(
                        _diferencas(pedaco.simbolos, lido, melhor.rstrip("+#")))
                    historico.append((*_numero_da_vez(board), board.copy()))
                    board.push_san(melhor)
                else:
                    situacao = ("ambiguo" if len(empatados) > 1 or not certo
                                else "perdido")
                    analise.lances.append(
                        LanceLido(lido, pedaco.simbolos, None, brancas,
                                  situacao, melhor, empatados[:4]))
                    analise.dessincronizou += 1
                    board, certo = None, False

    return analise


def _tenta(board: chess.Board, san: str):
    try:
        return board.parse_san(san)
    except (chess.IllegalMoveError, chess.InvalidMoveError,
            chess.AmbiguousMoveError):
        return None


def _posicoes_possiveis(board: Optional[chess.Board],
                        historico: List[Tuple[int, bool, chess.Board]],
                        alvo: Tuple[int, bool]) -> List[chess.Board]:
    """
    Onde o lance `alvo` pode estar sendo jogado.

    Um número que já passou é variante: rebobina. Mas o mesmo número aparece
    várias vezes ("12...Ra6; 12...Ra7; 12...Nb6"), e depois da variante o texto
    volta para a principal sem marcar — de fora, "13." tanto continua a variante
    quanto retoma a linha principal. Em vez de adivinhar, devolve todas as
    posições plausíveis e deixa o lance seguinte desempatar.

    Posições idênticas contam uma vez só: as três rebobinagens de "12..." dão o
    mesmo tabuleiro, e tratá-las como três candidatas fabricaria uma ambiguidade
    que não existe.
    """
    candidatas: List[chess.Board] = []
    vistas = set()

    def junta(b: chess.Board):
        chave = b.board_fen() + str(b.turn) + str(b.fullmove_number)
        if chave not in vistas:
            vistas.add(chave)
            candidatas.append(b)

    if board is not None and _numero_da_vez(board) == alvo:
        junta(board.copy())
    for n, brancas, anterior in reversed(historico):
        if (n, brancas) == alvo:
            junta(anterior.copy())
    return candidatas


def _alinhar(lido: str, correto: str) -> List[Tuple[Optional[int], str]]:
    """
    Alinhamento simples entre a leitura e o lance correto.

    Devolve [(posição em `lido` ou None, caractere esperado)]. `None` marca um
    caractere que **falta** na leitura, e esse é o caso que não vira edição:
    não existe box para ele. Um box sobrando, ao contrário, vira edição — é o
    caso do glifo partido em dois, em que o segundo pedaço é lido como um
    caractere fantasma.
    """
    n, m = len(lido), len(correto)
    # DP de distância de edição com custos iguais, só para achar o alinhamento.
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j - 1] + (lido[i - 1] != correto[j - 1]),
                          d[i - 1][j] + 1, d[i][j - 1] + 1)

    passos: List[Tuple[Optional[int], str]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (lido[i - 1] != correto[j - 1]):
            passos.append((i - 1, correto[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            passos.append((i - 1, ""))       # box sobrando: esvaziar
            i -= 1
        else:
            passos.append((None, correto[j - 1]))   # caractere sem box
            j -= 1
    passos.reverse()
    return passos


def _diferencas(simbolos: List[Simbolo], lido: str,
                correto: str) -> List[Correcao]:
    """
    Correções de caractere, só onde dá para apontar o box.

    Um caractere que **falta** na leitura não tem box: a imagem não tem o glifo,
    e inventar um box vazio seria pior que mostrar a sugestão e deixar o usuário
    decidir. Um box **sobrando** tem solução: o caractere vai a vazio, que é
    como o projeto representa "box sem caractere" (o `~` do formato .box). Foi o
    caso medido na página real, em que o 'N' em negrito era partido em dois e o
    segundo pedaço virava '□'.
    """
    return [Correcao(simbolos[pos].indice, lido[pos], esperado, lido, correto)
            for pos, esperado in _alinhar(lido, correto)
            if pos is not None and lido[pos] != esperado]


def aplicar(boxes: List[BoxEntry], correcoes: Sequence[Correcao]) -> int:
    """Escreve as correções nos boxes. Devolve quantas foram aplicadas."""
    aplicadas = 0
    for c in correcoes:
        if 0 <= c.indice_box < len(boxes) and boxes[c.indice_box].char == c.de:
            boxes[c.indice_box].char = c.para
            boxes[c.indice_box].confidence = 1.0
            boxes[c.indice_box].source = "xadrez"
            aplicadas += 1
    return aplicadas
