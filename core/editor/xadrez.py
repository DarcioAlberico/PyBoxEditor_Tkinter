"""
Xadrez sobre o modelo: os lances da notação, a partida que eles formam, a posição
em qualquer ponto, a validação, figurinas ↔ letras, os NAGs, jogadores e aberturas,
legendas e fontes (ED-05; SPEC_EDITOR §11.3–§11.7, DEC-06).

## Só a notação participa

Um parágrafo `corpo` com "after Nf3 the bishop…" não é linha de jogo; só os
parágrafos `notacao` e `comentario` e os trechos `papel="lance"` entram na leitura
(§11.3). É o que impede a prosa de derrubar o tabuleiro — e o que faz "Marcar lances"
ser útil: o que ele marca passa a contar.

## Tokens, segmentos, árvore de variantes

`tokens()` separa o **número do lance** (`23.`, `23…`, `23...`) do lance (`Nf3`,
`♘f3`, `O-O`, `e8=Q+`), porque `notacao.parece_lance("1.e4")` é falso e porque o `…`
diz de que lado é o lance seguinte. Uma **partida** (`segmentos()`) começa num
`Titulo`, num número `1.` de brancas ou num `Diagrama` cujo FEN difere da posição
corrente — nesse caso a linha **re-sincroniza** no diagrama e avisa "diagrama n não
bate com a linha" (é o erro de OCR mais comum). `posicao_apos()` percorre o segmento
que contém o cursor com uma pilha de variantes (`(`/`)` e `[`/`]` — cada variante parte
da posição **anterior** ao lance que a abre) e devolve a posição da linha em que o
cursor está, o lado proposto e o primeiro lance ilegal, que interrompe.

## A sugestão de lance ilegal não passa por `core.notacao`

`validar()` sugere o lance legal mais parecido com a mesma conta de
`notacao._melhor_lance_legal` (`custo_da_troca`, uma distância de edição em que inserir
custa 0,45 e trocar custa a confiança do caractere) — copiada aqui, e não importada,
porque `core.notacao` traz `box_service` e o `cv2` (DEC-07), e a validação é um comando
do editor que tem de rodar num processo sem OCR. Um teste de paridade confere as duas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from core import nags
from core.editor import dialeto, modelo
from core.editor.modelo import Bloco, Capitulo, Diagrama, Livro, Paragrafo, Titulo, Trecho
from core.estilo_do_livro import PISO_DO_SIMBOLO

#: Figurina → letra inglesa; os dois lados usam as mesmas figurinas (a cor vem do lance).
FIGURINAS = {"♔": "K", "♕": "Q", "♖": "R", "♗": "B", "♘": "N",
             "♚": "K", "♛": "Q", "♜": "R", "♝": "B", "♞": "N"}
FIGURINA_DA_LETRA = {"K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘"}
#: As letras das peças por idioma (a inicial de `KQRBN` em cada língua).
LETRAS = {"en": "KQRBN", "pt": "RDTBC", "es": "RDTAC", "fr": "RDTFC", "de": "KDTLS", "it": "RDTAC"}
#: Estilos de parágrafo em que a notação mora.
ESTILOS_DE_NOTACAO = ("notacao", "comentario")
_PECAS = "KQRBN" + "".join(FIGURINAS)
_NUMERO = r"(?P<numero>\d{1,3})(?P<pontos>\.\.\.|…|\.)"


def _lance(nome: str) -> str:
    """O padrão de um lance SAN (letra ou figurina, roque, promoção, xeque), num grupo chamado `nome`."""
    return (r"(?P<" + nome + r">(?:[" + _PECAS + r"][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x?[a-h]?[1-8](?:=?[" + _PECAS
            + r"])?|[Oo0]-[Oo0](?:-[Oo0])?)[+#]?)")


_SUFIXO = r"(?P<sufixo>[!?]{1,2}|[±∓⩱⩲=∞□⨀⇄⌓△▼]|\+-|-\+)?"
_RE_TOKEN = re.compile(
    r"(?P<abre>[(\[])|(?P<fecha>[)\]])|" + _NUMERO + r"(?:\s*" + _lance("lance_do_numero") + r")?|"
    + _lance("lance") + _SUFIXO
    + r"|(?P<resultado>1-0|0-1|½-½|1/2-1/2|\*)|(?P<nag>[!?]{1,2}|[±∓⩱⩲=∞□⨀⇄⌓△▼⯹]|\+-|-\+)(?![\w])")
_RE_LANCE_INTEIRO = re.compile(r"^" + _lance("lance") + r"$")
_RE_LETRA_DE_PECA = re.compile(r"^([" + _PECAS + r"])")
_RE_PROMOCAO = re.compile(r"=([" + _PECAS + r"])")
_RE_CABECALHO = re.compile(r"^\s*(?P<a>[^–—-]{2,60}?)\s+[–—-]\s+(?P<b>[^–—-]{2,60}?)\s*(?:\(|\[|,|$)")
#: Sobrenome → nome completo, para "Kasparov – Karpov" virar a chave de índice "Kasparov, Garry".
JOGADORES_CONHECIDOS = {
    "Steinitz": "Wilhelm", "Lasker": "Emanuel", "Capablanca": "José Raúl", "Alekhine": "Alexander",
    "Euwe": "Max", "Botvinnik": "Mikhail", "Smyslov": "Vasily", "Tal": "Mikhail", "Petrosian": "Tigran",
    "Spassky": "Boris", "Fischer": "Robert James", "Karpov": "Anatoly", "Kasparov": "Garry",
    "Kramnik": "Vladimir", "Anand": "Viswanathan", "Carlsen": "Magnus", "Topalov": "Veselin",
    "Caruana": "Fabiano", "Nakamura": "Hikaru", "Aronian": "Levon", "Ivanchuk": "Vassily", "Shirov": "Alexei",
    "Polgar": "Judit", "Yusupov": "Artur", "Dvoretsky": "Mark", "Nunn": "John", "Aagaard": "Jacob",
    "Nepomniachtchi": "Ian", "Ding": "Liren", "Gukesh": "Dommaraju", "Mecking": "Henrique",
}
#: Os sinais que também são outra coisa: não se marcam sozinhos como NAG.
NAGS_AMBIGUOS = frozenset({"=", "∞", "+", "#"})


# ----------------------------------------------------------------------
# Tokens
# ----------------------------------------------------------------------

@dataclass
class Token:
    tipo: str            # "numero" | "lance" | "abre" | "fecha" | "nag" | "resultado"
    texto: str
    inicio: int
    fim: int
    numero: int | None = None
    lado: str = ""       # do número: "w" (`23.`) ou "b" (`23…`); do lance, o que o número disse


def tokens(texto: str) -> list[Token]:
    """Os tokens de notação de um texto, na ordem, com o deslocamento de cada um."""
    saida: list[Token] = []
    for m in _RE_TOKEN.finditer(texto):
        if m.group("abre"):
            saida.append(Token("abre", m.group("abre"), m.start(), m.end()))
        elif m.group("fecha"):
            saida.append(Token("fecha", m.group("fecha"), m.start(), m.end()))
        elif m.group("numero"):
            lado = "b" if m.group("pontos") in ("...", "…") else "w"
            fim_do_numero = m.start("pontos") + len(m.group("pontos"))
            saida.append(Token("numero", texto[m.start():fim_do_numero], m.start(), fim_do_numero,
                               int(m.group("numero")), lado))
            if m.group("lance_do_numero"):
                saida.append(Token("lance", m.group("lance_do_numero"), m.start("lance_do_numero"),
                                   m.end("lance_do_numero"), int(m.group("numero")), lado))
        elif m.group("lance"):
            lance = Token("lance", m.group("lance"), m.start("lance"), m.end("lance"))
            saida.append(lance)
            if m.group("sufixo"):
                saida.append(Token("nag", m.group("sufixo"), m.start("sufixo"), m.end("sufixo")))
        elif m.group("resultado"):
            saida.append(Token("resultado", m.group("resultado"), m.start(), m.end()))
        elif m.group("nag"):
            saida.append(Token("nag", m.group("nag"), m.start(), m.end()))
    return saida


def lance_em_san(texto: str) -> str:
    """`♘f3` → `Nf3`, `0-0` → `O-O`, `e8=♕+` → `e8=Q+` — o que o `python-chess` lê."""
    saida = "".join(FIGURINAS.get(c, c) for c in texto)
    saida = re.sub(r"^[0o]-[0o](-[0o])?", lambda m: m.group(0).upper().replace("0", "O"), saida)
    return saida


# ----------------------------------------------------------------------
# Segmentos e a posição
# ----------------------------------------------------------------------

@dataclass
class Segmento:
    """Uma partida: os índices dos blocos que ela ocupa e o FEN de onde começa."""

    inicio: int
    fim: int                       # exclusivo
    fen_inicial: str = ""          # "" = posição inicial
    diagrama_id: str = ""
    aviso: str = ""                # "diagrama n não bate com a linha" quando ele re-sincronizou uma linha


def e_notacao(bloco: Bloco) -> bool:
    """O bloco é uma linha de jogo: parágrafo de notação, ou com trechos `lance` marcados."""
    if not isinstance(bloco, Paragrafo) or isinstance(bloco, Titulo):
        return False
    return bloco.estilo in ESTILOS_DE_NOTACAO or any(t.papel == "lance" for t in bloco.trechos)


def _texto_de_notacao(bloco: Paragrafo) -> str:
    """O texto do parágrafo, com o que não é lance apagado em branco quando só os trechos `lance` contam."""
    if bloco.estilo in ESTILOS_DE_NOTACAO:
        return modelo.texto_de(bloco)
    partes: list[str] = []
    for t in bloco.trechos:
        texto = t.texto if t.papel == "lance" else " " * len(t.texto)
        partes.append(("\n" if t.quebra_antes else "") + texto)
    return "".join(partes)


def segmentos(blocos: Sequence[Bloco]) -> list[Segmento]:
    """
    As partidas de um capítulo (§11.3): uma começa num `Titulo`, num `1.` das brancas
    depois de já haver lances, ou num `Diagrama` cujo FEN não bate com a linha (aí a
    linha re-sincroniza a partir dele).
    """
    saida: list[Segmento] = []
    atual: Segmento | None = None
    board = _novo_board("")
    houve_lance = False

    def abrir(i: int, fen: str = "", diagrama_id: str = "", aviso: str = "") -> None:
        nonlocal atual, board, houve_lance
        if atual is not None:
            atual.fim = i
            if atual.fim > atual.inicio:
                saida.append(atual)
        atual = Segmento(inicio=i, fim=i, fen_inicial=fen, diagrama_id=diagrama_id, aviso=aviso)
        board = _novo_board(fen)
        houve_lance = False

    for i, bloco in enumerate(blocos):
        if isinstance(bloco, Titulo):
            abrir(i)
            continue
        if isinstance(bloco, Diagrama):
            posicao = _posicao_do_fen(bloco.fen)
            if atual is None or posicao != board.board_fen():
                aviso = ""
                if atual is not None and houve_lance:
                    rotulo = f"diagrama {bloco.numero}" if bloco.numero is not None else f"diagrama {bloco.id}"
                    aviso = f"{rotulo} não bate com a linha; a linha continua dele"
                abrir(i, bloco.fen, bloco.id, aviso)
            continue
        if not e_notacao(bloco):
            continue
        if atual is None:
            abrir(i)
        for token in tokens(_texto_de_notacao(bloco)):
            if token.tipo == "numero" and token.numero == 1 and token.lado == "w" and houve_lance:
                abrir(i)
            elif token.tipo == "lance":
                houve_lance = True
                board, _ok = _jogar(board, token.texto)
    if atual is not None:
        atual.fim = len(blocos)
        if atual.fim > atual.inicio:
            saida.append(atual)
    return saida


def _novo_board(fen: str):
    import chess

    if not fen:
        return chess.Board()
    try:
        return chess.Board(fen if len(fen.split()) >= 2 else fen + " w - - 0 1")
    except ValueError:
        return chess.Board()


def _posicao_do_fen(fen: str) -> str:
    return fen.split()[0] if fen else ""


def _jogar(board: Any, lance: str) -> tuple[Any, bool]:
    """Tenta o lance na cópia; `(board novo, deu)` — o board original não muda."""
    try:
        movimento = board.parse_san(lance_em_san(lance).rstrip("!?"))
    except ValueError:
        return board, False
    novo = board.copy()
    novo.push(movimento)
    return novo, True


@dataclass
class Posicao:
    """O que `posicao_apos` devolve; desempacota em `(board, lado, erro)`."""

    board: Any
    lado: str
    erro: str | None
    avisos: list[str] = field(default_factory=list)
    numero: int = 1

    def __iter__(self):
        yield self.board
        yield self.lado
        yield self.erro

    @property
    def fen(self) -> str:
        return self.board.fen()


def posicao_apos(blocos: Sequence[Bloco], ate: tuple[int, int]) -> Posicao:
    """
    A posição da linha que contém o cursor `ate = (índice do bloco, deslocamento)`
    (§11.3): percorre o segmento do cursor com a pilha de variantes e para no cursor
    (ou no primeiro lance ilegal, que vira `erro`). O `lado` é quem joga na posição.
    """
    i_alvo, desloc_alvo = ate
    segmento = next((s for s in segmentos(blocos) if s.inicio <= i_alvo < s.fim), None)
    if segmento is None:
        return Posicao(_novo_board(""), "w", None, ["o cursor não está numa linha de jogo"])
    board = _novo_board(segmento.fen_inicial)
    pilha: list[Any] = []                   # a posição anterior ao lance que abriu cada variante
    anterior = board                        # a posição antes do último lance jogado
    avisos: list[str] = [segmento.aviso] if segmento.aviso else []
    erro: str | None = None
    for i in range(segmento.inicio, min(segmento.fim, i_alvo + 1)):
        bloco = blocos[i]
        if isinstance(bloco, Diagrama):
            if i != segmento.inicio and _posicao_do_fen(bloco.fen) != board.board_fen():
                rotulo = f"diagrama {bloco.numero}" if bloco.numero is not None else f"diagrama {bloco.id}"
                avisos.append(f"{rotulo} não bate com a linha; a linha continua dele")
                board = _novo_board(bloco.fen)
            continue
        if not e_notacao(bloco):
            continue
        for token in tokens(_texto_de_notacao(bloco)):
            if i == i_alvo and token.inicio >= desloc_alvo:
                break
            if token.tipo == "abre":
                pilha.append(board)
                board = anterior
            elif token.tipo == "fecha":
                if pilha:
                    board = pilha.pop()
                    anterior = board
            elif token.tipo == "lance":
                novo, deu = _jogar(board, token.texto)
                if not deu:
                    erro = token.texto
                    return Posicao(board, "w" if board.turn else "b", erro, avisos, board.fullmove_number)
                anterior, board = board, novo
        if erro:
            break
    return Posicao(board, "w" if board.turn else "b", erro, avisos, board.fullmove_number)


# ----------------------------------------------------------------------
# Validação
# ----------------------------------------------------------------------

@dataclass
class Problema:
    i_bloco: int
    bloco_id: str
    inicio: int
    fim: int
    texto: str
    sugestao: str
    mensagem: str


CUSTO_INSERIR = 0.45
CUSTO_REMOVER = 0.8


def custo_da_troca(lido: str, candidato: str, confiancas: Sequence[float]) -> float:
    """Cópia de `notacao.custo_da_troca` (ver o cabeçalho): a distância de edição ponderada."""
    n, m = len(lido), len(candidato)
    conf = list(confiancas) + [0.5] * max(0, n - len(confiancas))
    anterior = [j * CUSTO_INSERIR for j in range(m + 1)]
    for i in range(1, n + 1):
        peso = conf[i - 1] if conf[i - 1] > 0 else 0.5
        atual = [anterior[0] + CUSTO_REMOVER]
        for j in range(1, m + 1):
            troca = anterior[j - 1] + (0.0 if lido[i - 1] == candidato[j - 1] else peso)
            atual.append(min(troca, anterior[j] + CUSTO_REMOVER, atual[j - 1] + CUSTO_INSERIR))
        anterior = atual
    return anterior[m]


def melhor_lance_legal(board: Any, lido: str, confiancas: Sequence[float] | None = None) -> tuple:
    """Cópia de `notacao._melhor_lance_legal`: `(melhor, empatados, custo)` entre os lances legais."""
    confiancas = list(confiancas) if confiancas is not None else [1.0] * len(lido)
    pontuados = []
    for movimento in board.legal_moves:
        san = board.san(movimento)
        limpo = san.rstrip("+#")
        pontuados.append((min(custo_da_troca(lido, san, confiancas), custo_da_troca(lido, limpo, confiancas)), san))
    if not pontuados:
        return None, [], float("inf")
    pontuados.sort()
    melhor_custo, melhor = pontuados[0]
    empatados = [s for c, s in pontuados if c <= melhor_custo + 1e-9]
    if len(empatados) > 1:
        # O desempate que a leitura do OCR não precisa e o texto digitado precisa: entre
        # `Bb5` e `Ba6` para um `Bb6`, fica o que compartilha o prefixo mais longo com o lido.
        def prefixo(candidato: str) -> int:
            n = 0
            for a, b in zip(lido, candidato):
                if a != b:
                    break
                n += 1
            return n

        maior = max(prefixo(c) for c in empatados)
        com_prefixo = [c for c in empatados if prefixo(c) == maior]
        if len(com_prefixo) == 1:
            return com_prefixo[0], com_prefixo, melhor_custo
    return melhor, empatados, melhor_custo


def validar(blocos: Sequence[Bloco]) -> list[Problema]:
    """
    Todos os lances de todas as linhas de todos os segmentos (§11.4), com a sugestão do
    lance legal mais parecido. Não corrige nada: devolve a lista para o painel e as
    marcas no texto.
    """
    problemas: list[Problema] = []
    for segmento in segmentos(blocos):
        board = _novo_board(segmento.fen_inicial)
        pilha: list[Any] = []
        anterior = board
        # depois de um erro a linha continua com o lance sugerido (quando há um só) para
        # não marcar todo lance seguinte como ilegal por arrasto
        for i in range(segmento.inicio, segmento.fim):
            bloco = blocos[i]
            if isinstance(bloco, Diagrama):
                if i != segmento.inicio and _posicao_do_fen(bloco.fen) != board.board_fen():
                    board = _novo_board(bloco.fen)
                    anterior = board
                continue
            if not e_notacao(bloco):
                continue
            for token in tokens(_texto_de_notacao(bloco)):
                if token.tipo == "abre":
                    pilha.append(board)
                    board = anterior
                elif token.tipo == "fecha":
                    if pilha:
                        board = pilha.pop()
                        anterior = board
                elif token.tipo == "lance":
                    novo, deu = _jogar(board, token.texto)
                    if deu:
                        anterior, board = board, novo
                        continue
                    lido = lance_em_san(token.texto).rstrip("+#!?")
                    melhor, empatados, custo = melhor_lance_legal(board, lido)
                    sugestao = melhor if melhor and len(empatados) == 1 and custo <= 1.6 else ""
                    mensagem = f"{token.texto} não é legal aqui" + (f"; talvez {sugestao}" if sugestao else "")
                    problemas.append(Problema(i, bloco.id, token.inicio, token.fim, token.texto, sugestao, mensagem))
                    if sugestao:
                        anterior, board = board, _jogar(board, sugestao)[0]
    return problemas


# ----------------------------------------------------------------------
# Figurinas e letras
# ----------------------------------------------------------------------

def _trocar_pecas(lance: str, de: dict[str, str]) -> str:
    return "".join(de.get(c, c) for c in lance)


def para_letras(texto: str, de: str = "figurinas", idioma: str = "en") -> str:
    """
    Os lances de `texto` com as peças em letras do `idioma` (`en` KQRBN, `pt` RDTBC…);
    `de` diz o que o texto usa hoje: `"figurinas"` ou um idioma. Só toca nos tokens de
    lance — a prosa fica.
    """
    letras = LETRAS.get(idioma, LETRAS["en"])
    if de == "figurinas":
        mapa = {fig: letras["KQRBN".index(letra)] for fig, letra in FIGURINAS.items()}
    else:
        origem = LETRAS.get(de, LETRAS["en"])
        mapa = {origem[k]: letras[k] for k in range(5)}
    return _sobre_os_lances(texto, lambda lance: _trocar_pecas(lance, mapa), origem_em_letras=de != "figurinas",
                            letras_de_origem=LETRAS.get(de, LETRAS["en"]) if de != "figurinas" else "")


def para_figurinas(texto: str, de: str = "en") -> str:
    """O inverso: as letras do idioma `de` viram figurinas brancas (a leitura aceita as pretas)."""
    origem = LETRAS.get(de, LETRAS["en"])
    mapa = {origem[k]: FIGURINA_DA_LETRA["KQRBN"[k]] for k in range(5)}
    return _sobre_os_lances(texto, lambda lance: _trocar_pecas(lance, mapa), origem_em_letras=True,
                            letras_de_origem=origem)


def _sobre_os_lances(texto: str, funcao, origem_em_letras: bool, letras_de_origem: str) -> str:
    """Aplica `funcao` a cada token de lance; num idioma com peças fora de KQRBN, os tokens são achados com elas."""
    if origem_em_letras and letras_de_origem and letras_de_origem != "KQRBN":
        traduzido = _para_en(texto, letras_de_origem)
        posicoes = [(t.inicio, t.fim) for t in tokens(traduzido) if t.tipo == "lance"]
    else:
        posicoes = [(t.inicio, t.fim) for t in tokens(texto) if t.tipo == "lance"]
    partes: list[str] = []
    pos = 0
    for ini, fim in posicoes:
        partes.append(texto[pos:ini])
        partes.append(funcao(texto[ini:fim]))
        pos = fim
    partes.append(texto[pos:])
    return "".join(partes)


def _para_en(texto: str, letras: str) -> str:
    """As iniciais de peça de outro idioma como se fossem inglesas, para `tokens` as achar (mesmo comprimento)."""
    mapa = {letras[k]: "KQRBN"[k] for k in range(5)}
    saida = []
    for m in re.finditer(r"\S+|\s+", texto):
        palavra = m.group(0)
        if palavra.strip():
            candidato = "".join(mapa.get(c, c) for c in palavra)
            if candidato != palavra and any(t.tipo == "lance" for t in tokens(candidato)):
                palavra = candidato
        saida.append(palavra)
    return "".join(saida)


def figurina_ao_digitar(paragrafo: Paragrafo, deslocamento: int, idioma: str = "en") -> bool:
    """
    Ao fechar um token que parece lance em `notacao`/`comentario` (§11.5): a letra da
    peça vira figurina no token que termina em `deslocamento`. `False` em `corpo` ou
    quando não há o que trocar.
    """
    if paragrafo.estilo not in ESTILOS_DE_NOTACAO:
        return False
    texto = modelo.texto_de(paragrafo)
    letras = LETRAS.get(idioma, LETRAS["en"])
    alvo = next((t for t in tokens(_para_en(texto[:deslocamento], letras)) if t.tipo == "lance"
                 and t.fim == deslocamento), None)
    if alvo is None:
        return False
    original = texto[alvo.inicio:alvo.fim]
    novo = para_figurinas(original, idioma)
    if novo == original:
        return False
    _substituir_no_paragrafo(paragrafo, alvo.inicio, alvo.fim, novo)
    return True


def _substituir_no_paragrafo(paragrafo: Paragrafo, ini: int, fim: int, novo: str) -> None:
    """Troca o texto entre `ini` e `fim` (posições do bloco) mantendo o formato do trecho."""
    pos = 0
    for trecho in paragrafo.trechos:
        comprimento = len(trecho.texto) + (1 if trecho.quebra_antes else 0)
        inicio_do_texto = pos + (1 if trecho.quebra_antes else 0)
        if inicio_do_texto <= ini and fim <= inicio_do_texto + len(trecho.texto):
            a, b = ini - inicio_do_texto, fim - inicio_do_texto
            trecho.texto = trecho.texto[:a] + novo + trecho.texto[b:]
            return
        pos += comprimento
    # atravessa trechos: aplica no texto inteiro e reparte pelo primeiro
    modelo.aplicar_formato(paragrafo, ini, fim)
    pos = 0
    for k, trecho in enumerate(paragrafo.trechos):
        inicio_do_texto = pos + (1 if trecho.quebra_antes else 0)
        if inicio_do_texto == ini:
            trecho.texto = novo
            fim_k = k
            while fim_k + 1 < len(paragrafo.trechos) and pos + len(trecho.texto) < fim:
                paragrafo.trechos.pop(fim_k + 1)
                fim_k += 1
            return
        pos += len(trecho.texto) + (1 if trecho.quebra_antes else 0)


# ----------------------------------------------------------------------
# Marcar lances, NAGs, jogador e abertura
# ----------------------------------------------------------------------

def marcar_lances(blocos: Sequence[Bloco]) -> int:
    """`papel="lance"` em todo token de lance dos parágrafos de notação; devolve quantos."""
    n = 0
    for bloco in blocos:
        if not isinstance(bloco, Paragrafo) or isinstance(bloco, Titulo) or bloco.estilo not in ESTILOS_DE_NOTACAO:
            continue
        texto = modelo.texto_de(bloco)
        for token in reversed(tokens(texto)):
            if token.tipo != "lance":
                continue
            modelo.aplicar_formato(bloco, token.inicio, token.fim, papel="lance")
            n += 1
    return n


def _codigo_do_simbolo() -> dict[str, int]:
    """símbolo → código do NAG, só para os unívocos (o `POR_CODIGO` invertido, §11.6)."""
    contagem: dict[str, list[int]] = {}
    for nag in nags.TABELA:
        if nag.simbolo:
            contagem.setdefault(nag.simbolo, []).append(nag.codigo)
    return {s: codigos[0] for s, codigos in contagem.items() if len(codigos) == 1 and s not in NAGS_AMBIGUOS}


def marcar_nags(blocos: Sequence[Bloco]) -> tuple[int, list[str]]:
    """
    `papel="nag"` + `nag` no que veio digitado (ou do OCR) quando o símbolo é unívoco;
    devolve `(quantos, os ambíguos encontrados)` — `=` e `∞` ficam para o usuário.
    """
    codigos = _codigo_do_simbolo()
    n = 0
    ambiguos: list[str] = []
    for bloco in blocos:
        if not isinstance(bloco, Paragrafo) or isinstance(bloco, Titulo) or bloco.estilo not in ESTILOS_DE_NOTACAO:
            continue
        texto = modelo.texto_de(bloco)
        for token in reversed(tokens(texto)):
            if token.tipo != "nag":
                continue
            if token.texto in NAGS_AMBIGUOS or token.texto not in codigos:
                if token.texto not in ambiguos:
                    ambiguos.append(token.texto)
                continue
            modelo.aplicar_formato(bloco, token.inicio, token.fim, papel="nag", nag=codigos[token.texto])
            n += 1
    return n, ambiguos


@dataclass
class Sugestao:
    i_bloco: int
    inicio: int
    fim: int
    texto: str
    papel: str            # "jogador" | "abertura"
    chave: str


def chave_de_jogador(nome: str, conhecidos: dict[str, str] | None = None) -> str:
    """"Garry Kasparov" → "Kasparov, Garry"; "Kasparov" → "Kasparov, Garry" quando se sabe o nome; senão o sobrenome."""
    nome = nome.strip()
    if "," in nome:
        return nome
    partes = nome.split()
    if len(partes) >= 2:
        return f"{partes[-1]}, {' '.join(partes[:-1])}"
    tabela = dict(JOGADORES_CONHECIDOS)
    tabela.update(conhecidos or {})
    if nome in tabela:
        return f"{nome}, {tabela[nome]}"
    return nome


def sugerir_jogadores_e_aberturas(blocos: Sequence[Bloco]) -> list[Sugestao]:
    """
    Os cabeçalhos "Nome – Nome" (título ou `cabecalho-diagrama`) viram sugestões de
    `papel="jogador"` com a chave de índice; um "[B90]" ou "(C42)" no mesmo cabeçalho vira
    `abertura` com o ECO. Nomes já marcados no capítulo ensinam a chave dos iguais.
    """
    conhecidos: dict[str, str] = {}
    for bloco in blocos:
        for t in modelo._todos_os_trechos(bloco):
            if t.papel == "jogador" and t.chave and "," in t.chave:
                sobrenome, _, nome = t.chave.partition(",")
                conhecidos[sobrenome.strip()] = nome.strip()
    saida: list[Sugestao] = []
    for i, bloco in enumerate(blocos):
        if not isinstance(bloco, Paragrafo):
            continue
        if not (isinstance(bloco, Titulo) or bloco.estilo in ("cabecalho-diagrama", "legenda")):
            continue
        texto = modelo.texto_de(bloco)
        m = _RE_CABECALHO.match(texto)
        if m:
            for grupo in ("a", "b"):
                nome = m.group(grupo).strip()
                if not nome or nome[0].islower() or any(c.isdigit() for c in nome):
                    continue
                saida.append(Sugestao(i, m.start(grupo), m.start(grupo) + len(nome), nome, "jogador",
                                      chave_de_jogador(nome, conhecidos)))
        for eco in re.finditer(r"(?<![A-Za-z])([A-E]\d\d)(?![0-9])", texto):
            saida.append(Sugestao(i, eco.start(1), eco.end(1), eco.group(1), "abertura", eco.group(1)))
    return saida


def marcar_jogador_abertura(blocos: Sequence[Bloco], sugestoes: Iterable[Sugestao] | None = None) -> int:
    """Aplica as sugestões (todas, por padrão): `papel` e `chave` nos trechos; devolve quantas."""
    escolhidas = list(sugestoes) if sugestoes is not None else sugerir_jogadores_e_aberturas(blocos)
    n = 0
    for s in sorted(escolhidas, key=lambda x: (x.i_bloco, -x.inicio)):
        bloco = blocos[s.i_bloco]
        if not isinstance(bloco, Paragrafo):
            continue
        modelo.aplicar_formato(bloco, s.inicio, s.fim, papel=s.papel, chave=s.chave)
        n += 1
    return n


# ----------------------------------------------------------------------
# Legendas, referências, fontes
# ----------------------------------------------------------------------

alt_de = dialeto.alt_de

LEGENDA_DE_LADO = {"pt": {"w": "Brancas jogam", "b": "Pretas jogam"},
                   "en": {"w": "White to move", "b": "Black to move"}}


def legenda_de_lado(d: Diagrama, idioma: str = "pt") -> str:
    """"Brancas jogam"/"Pretas jogam" quando o lado é conhecido; vazio quando não (DEC-06)."""
    return LEGENDA_DE_LADO.get(idioma.split("-")[0].lower(), LEGENDA_DE_LADO["pt"]).get(d.lado, "")


def cabecalho_em_legenda(cap: Capitulo, i: int) -> Diagrama | None:
    """
    O `h2` (ou o parágrafo `cabecalho-diagrama`) em `i` vira a legenda do diagrama que
    vem depois dele — o cabeçalho da F67 —, e sai do capítulo. `None` se não há diagrama
    logo depois (só marcas de página e parágrafos vazios entre os dois).
    """
    if not 0 <= i < len(cap.blocos):
        return None
    cabecalho = cap.blocos[i]
    if not isinstance(cabecalho, Paragrafo):
        return None
    if not (isinstance(cabecalho, Titulo) or cabecalho.estilo in ("cabecalho-diagrama", "legenda")):
        return None
    for k in range(i + 1, len(cap.blocos)):
        bloco = cap.blocos[k]
        if isinstance(bloco, Diagrama):
            trechos = [Trecho(**{c: v for c, v in modelo.para_dict(t).items() if c != "tipo"})
                       for t in cabecalho.trechos if not t.nota]
            for t in trechos:
                t.quebra_antes = False
            bloco.legenda = (bloco.legenda + [Trecho(texto=" ")] if bloco.legenda else []) + trechos
            del cap.blocos[i]
            return bloco
        if isinstance(bloco, modelo.MarcaDePagina) or (isinstance(bloco, Paragrafo)
                                                      and not modelo.texto_de(bloco).strip()):
            continue
        return None
    return None


def texto_da_referencia(bloco: Bloco) -> str:
    """"Diagrama 12", "Figura 3", "Tabela 1" ou o texto do título — o que `Trecho.ref` mostra."""
    if isinstance(bloco, Titulo):
        return modelo.texto_de(bloco)
    for tipo, classe in (("diagrama", Diagrama), ("figura", modelo.Figura), ("tabela", modelo.Tabela)):
        if isinstance(bloco, classe):
            numero = getattr(bloco, "numero", None)
            return f"{modelo.ROTULOS_DE_OBJETO[tipo]} {numero if numero is not None else '?'}"
    return ""


def tipo_de_referencia(bloco: Bloco) -> str:
    if isinstance(bloco, Titulo):
        return "titulo"
    if isinstance(bloco, Diagrama):
        return "diagrama"
    if isinstance(bloco, modelo.Figura):
        return "figura"
    if isinstance(bloco, modelo.Tabela):
        return "tabela"
    return ""


def alvos_de_referencia(livro: Livro) -> list[tuple[str, str, str, str]]:
    """`(arquivo, id, tipo, rótulo)` de todo diagrama, figura, tabela e título do livro."""
    saida = []
    for cap in livro.capitulos:
        for bloco in modelo.blocos_do_capitulo(cap):
            tipo = tipo_de_referencia(bloco)
            if tipo:
                saida.append((cap.arquivo, bloco.id, tipo, texto_da_referencia(bloco)))
    return saida


def fonte_do_livro(livro: Livro, fonte: str) -> int:
    """Troca a fonte de diagrama de **todos** os diagramas (e dos trechos naquela família); devolve quantos."""
    n = 0
    for cap in livro.capitulos:
        for bloco in modelo.blocos_do_capitulo(cap):
            if isinstance(bloco, Diagrama) and bloco.fonte != fonte:
                bloco.fonte = fonte
                n += 1
        for t in modelo.trechos_do_capitulo(cap):
            if t.familia and t.familia != "simbolos" and t.familia != fonte and (
                    t.familia.endswith("-Diagram")):
                t.familia = fonte
                n += 1
    return n


def fonte_dos_simbolos_do_livro(livro: Livro, familia: str = "simbolos") -> int:
    """
    Põe (ou tira, com `familia=""`) a família `simbolos` em todo trecho que tem um
    caractere acima de `PISO_DO_SIMBOLO` — as figurinas e os sinais que a fonte do texto
    não desenha. Devolve quantos trechos mudaram.
    """
    n = 0
    for cap in livro.capitulos:
        for bloco in modelo.blocos_do_capitulo(cap):
            if not isinstance(bloco, Paragrafo):
                continue
            texto = modelo.texto_de(bloco)
            corridas = [(m.start(), m.end()) for m in re.finditer(r"[^\x00-῿]+", texto)]
            for ini, fim in reversed(corridas):
                if not any(ord(c) >= PISO_DO_SIMBOLO for c in texto[ini:fim]):
                    continue
                antes = [t.familia for t in bloco.trechos]
                modelo.aplicar_formato(bloco, ini, fim, familia=familia)
                if [t.familia for t in bloco.trechos] != antes:
                    n += 1
    return n


def diagrama_dos_lances(blocos: Sequence[Bloco], ate: tuple[int, int], **campos: Any) -> tuple[Diagrama, Posicao]:
    """Um `Diagrama` com a posição da linha do cursor e o lado **proposto** (`lado` fica gravado, §11.3)."""
    posicao = posicao_apos(blocos, ate)
    fen = posicao.board.fen()
    return Diagrama(fen=fen, lado=posicao.lado, **campos), posicao


__all__ = ["Token", "tokens", "lance_em_san", "Segmento", "segmentos", "Posicao", "posicao_apos", "Problema",
           "validar", "melhor_lance_legal", "custo_da_troca", "para_letras", "para_figurinas", "e_notacao",
           "figurina_ao_digitar", "marcar_lances", "marcar_nags", "Sugestao", "sugerir_jogadores_e_aberturas",
           "marcar_jogador_abertura", "chave_de_jogador", "alt_de", "legenda_de_lado", "cabecalho_em_legenda",
           "texto_da_referencia", "tipo_de_referencia", "alvos_de_referencia", "fonte_do_livro",
           "fonte_dos_simbolos_do_livro", "diagrama_dos_lances", "FIGURINAS", "LETRAS", "JOGADORES_CONHECIDOS",
           "NAGS_AMBIGUOS", "ESTILOS_DE_NOTACAO"]
