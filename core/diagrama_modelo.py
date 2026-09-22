"""
As estruturas do diagrama lido — `Casa`, `Rotulos`, `Titulo`, `Leitura` — sem `cv2`
(ED-05; SPEC_EDITOR DEC-07).

Saíram de `core/diagrama.py` **sem mudar de nome**: aquele módulo importa `cv2` e
`numpy` no topo, porque lê a página; estas classes são só dados (`dataclass`,
`python-chess`), e o editor de posição (`core/tabuleiro_edicao.py`,
`ui/editor/tabuleiro.py`) precisa delas num processo que não carrega o OCR.
`core.diagrama` as reimporta daqui, então `diagrama.Casa`, `diagrama.Leitura` etc.
continuam valendo para quem já os usava — inclusive `_plausivel`, a prova de
contagem que `Leitura.plausivel` chama.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import chess

from core.box_model import BoxEntry


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
    #: De quem é a vez, quando a legenda da página disse — `None` quando não
    #: disse, que é quando `fen()` cai na convenção e avisa.
    #:
    #: Não sai do tabuleiro: sai do `titulo`, pela peneira de
    #: `core/lado_a_jogar.py`. Quem a preenche é `ler_pagina`, que é quem tem o
    #: texto em volta; `ler` com um recorte solto nunca a tem.
    lado_a_jogar: Optional[str] = None

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

        **Menos o lado, quando a legenda o disse** (item 3 da revisão de
        2026-09-18): `Black to play` impresso embaixo do diagrama é leitura, não
        convenção, e o FEN termina em `b`. `avisos` muda junto — continua
        dizendo de onde veio cada campo que o tabuleiro não tem.
        """
        return f"{self.tabuleiro().board_fen()} {self.lado_a_jogar or 'w'} - - 0 1"

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
