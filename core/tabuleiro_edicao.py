"""
O tabuleiro que se edita (F8.2).

## Por que editar não é enfeite

A F7.1 lê a posição do diagrama e acerta **94,5% das casas** — cerca de três e
meia erradas em 64. Ela já concluiu que isso é um rascunho para conferir, e o
diálogo mostra o recorte impresso ao lado da leitura exatamente por isso. Mas
conferir sem poder corrigir devolve o trabalho inteiro para fora do programa:
quem vê um bispo lido como peão copia um FEN errado ou desiste.

## O estado mora aqui, e não no diálogo

Pelo mesmo motivo que a leitura mora em `core/diagrama.py`: o que tem regra
precisa de teste, e teste de widget não é teste de regra. O diálogo desenha e
despacha cliques; quem sabe o que é uma posição, o que é um desfazer e o que é
um roque possível é este módulo.

## A legalidade, agora que alguém pode responder

A F7.1 arbitra a leitura por contagem — um rei de cada cor, oito peões, dezesseis
peças. Aqui a checagem é a do `python-chess` inteira (`Board.status()`), porque
duas coisas que a leitura não tinha como saber passam a ter dono:

- **Lado a jogar.** Sem ele não dá para dizer que a posição é impossível por o
  rei de quem *não* joga estar em xeque. Com ele, dá.
- **Roque.** Só é oferecido o que a posição comporta — rei em e1 e torre em h1
  para o `K`, e assim por diante. Marcar um roque impossível e ver o FEN sair
  com `-` seria pior que não oferecer.

**O que o usuário informou não vira leitura.** O aviso da F7.1 dizia que o FEN
assume brancas a jogar, sem roque; quando o lado ou o roque são informados, o
aviso passa a dizer que vieram de quem editou. En passant continua fora: não
está no diagrama e não é dedutível dele.
"""

from typing import List, Optional, Sequence, Tuple

import chess

from core import diagrama as diag


#: Ordem da paleta: brancas, depois pretas. É a ordem em que a notação as
#: escreve, e a mesma de `diagrama.SIMBOLOS` reagrupada por cor.
SIMBOLOS = tuple("KQRBNP") + tuple("kqrbnp")

#: Casas que cada direito de roque exige, no xadrez padrão.
_ROQUE = {
    "K": (chess.E1, chess.H1, "K", "R"),
    "Q": (chess.E1, chess.A1, "K", "R"),
    "k": (chess.E8, chess.H8, "k", "r"),
    "q": (chess.E8, chess.A8, "k", "r"),
}

#: O que cada bandeira de `Board.status()` quer dizer, em português. As de
#: variante (`RACE_*`) ficam de fora: não há como chegar a elas por aqui.
_PROBLEMAS = [
    (chess.STATUS_EMPTY, "o tabuleiro está vazio"),
    (chess.STATUS_NO_WHITE_KING, "não há rei branco"),
    (chess.STATUS_NO_BLACK_KING, "não há rei preto"),
    (chess.STATUS_TOO_MANY_KINGS, "há mais de um rei de alguma cor"),
    (chess.STATUS_TOO_MANY_WHITE_PAWNS, "mais de oito peões brancos"),
    (chess.STATUS_TOO_MANY_BLACK_PAWNS, "mais de oito peões pretos"),
    (chess.STATUS_PAWNS_ON_BACKRANK, "há peão na 1ª ou na 8ª fila"),
    (chess.STATUS_TOO_MANY_WHITE_PIECES, "mais de dezesseis peças brancas"),
    (chess.STATUS_TOO_MANY_BLACK_PIECES, "mais de dezesseis peças pretas"),
    (chess.STATUS_BAD_CASTLING_RIGHTS, "o roque marcado não é possível aqui"),
    (chess.STATUS_INVALID_EP_SQUARE, "a casa de en passant não é possível"),
    (chess.STATUS_OPPOSITE_CHECK,
     "o rei de quem NÃO está a jogar está em xeque"),
    (chess.STATUS_TOO_MANY_CHECKERS, "peças demais dando xeque ao mesmo tempo"),
    (chess.STATUS_IMPOSSIBLE_CHECK, "este xeque não teria como acontecer"),
]

AVISO_CONVENCAO = (
    "Lado a jogar, roque e en passant não estão no diagrama; o FEN assume "
    "brancas a jogar, sem roque.")


class TabuleiroEdicao:
    """
    As 64 casas, o desfazer e o FEN de um diagrama sendo conferido.

    Nasce de uma `diagrama.Leitura` (ou vazio, sem ela) e **não a modifica**:
    trabalha sobre cópias das casas, para quem fechar a janela sem confirmar
    não levar edição nenhuma de volta para a leitura.
    """

    def __init__(self, leitura: Optional[diag.Leitura] = None):
        self.leitura = leitura
        origem = list(leitura.casas) if leitura is not None else []
        por_casa = {(c.linha, c.coluna): c for c in origem}
        self.casas: List[diag.Casa] = []
        for linha in range(8):
            for coluna in range(8):
                c = por_casa.get((linha, coluna))
                self.casas.append(diag.Casa(
                    linha, coluna,
                    c.simbolo if c else None,
                    c.confianca if c else 0.0,
                    c.arbitrada if c else False))

        self.lado = "w"
        self.roque = ""
        self.lado_informado = False
        self.roque_informado = False

        self._historico = [self._estado()]
        self._indice = 0

    # ------------------------------------------------------------------
    # Acesso
    # ------------------------------------------------------------------

    def casa(self, linha: int, coluna: int) -> Optional[diag.Casa]:
        if not (0 <= linha < 8 and 0 <= coluna < 8):
            return None
        return self.casas[linha * 8 + coluna]

    @property
    def ocupadas(self) -> List[diag.Casa]:
        return [c for c in self.casas if c.simbolo]

    @property
    def corrigidas(self) -> int:
        return sum(1 for c in self.casas if c.corrigida)

    @property
    def arbitradas(self) -> int:
        return sum(1 for c in self.casas if c.arbitrada and not c.corrigida)

    # ------------------------------------------------------------------
    # Editar
    # ------------------------------------------------------------------

    def colocar(self, linha: int, coluna: int,
                simbolo: Optional[str]) -> bool:
        """
        Põe (ou tira, com `simbolo=None`) uma peça. Devolve se algo mudou.

        A casa mexida à mão vira **autoridade**: confiança 1,0 e `corrigida`,
        do mesmo jeito que um box digitado vira `source="manual"` na F3.2. E
        deixa de contar como arbitrada — o vermelho da legalidade estava
        dizendo "isto aqui eu troquei sozinho", o que deixou de ser verdade.
        """
        alvo = self.casa(linha, coluna)
        if alvo is None:
            return False
        if simbolo is not None and simbolo not in SIMBOLOS:
            return False
        if alvo.simbolo == simbolo:
            return False

        alvo.simbolo = simbolo
        alvo.confianca = 1.0
        alvo.arbitrada = False
        alvo.corrigida = True
        self._registrar()
        return True

    def limpar(self, linha: int, coluna: int) -> bool:
        return self.colocar(linha, coluna, None)

    def mover(self, origem: Tuple[int, int], destino: Tuple[int, int]) -> bool:
        """Arrasta a peça de uma casa para outra; o destino é substituído."""
        de = self.casa(*origem)
        para = self.casa(*destino)
        if de is None or para is None or de is para or not de.simbolo:
            return False

        simbolo = de.simbolo
        for casa in (de, para):
            casa.confianca = 1.0
            casa.arbitrada = False
            casa.corrigida = True
        de.simbolo = None
        para.simbolo = simbolo
        self._registrar()
        return True

    def definir_lado(self, lado: str) -> bool:
        if lado not in ("w", "b") or lado == self.lado:
            return False
        self.lado = lado
        self.lado_informado = True
        self._registrar()
        return True

    def roques_possiveis(self) -> str:
        """
        Os direitos de roque que **esta posição** comporta.

        Oferecer o que a posição não comporta seria oferecer um FEN que sai
        diferente do que foi marcado: o `python-chess` derruba o direito na
        hora de escrever, e o usuário veria a caixa marcada e o `-` no FEN.
        """
        tabuleiro = self._tabuleiro_cru()
        possiveis = ""
        for letra, (casa_rei, casa_torre, rei, torre) in _ROQUE.items():
            peca_rei = tabuleiro.piece_at(casa_rei)
            peca_torre = tabuleiro.piece_at(casa_torre)
            if (peca_rei and peca_rei.symbol() == rei
                    and peca_torre and peca_torre.symbol() == torre):
                possiveis += letra
        return possiveis

    def definir_roque(self, direitos: str) -> bool:
        """Fixa os direitos de roque, limitados ao que a posição comporta."""
        possiveis = self.roques_possiveis()
        novo = "".join(l for l in "KQkq" if l in direitos and l in possiveis)
        if novo == self.roque:
            return False
        self.roque = novo
        self.roque_informado = True
        self._registrar()
        return True

    def alternar_roque(self, letra: str) -> bool:
        if letra not in "KQkq":
            return False
        atuais = set(self.roque)
        atuais.symmetric_difference_update({letra})
        return self.definir_roque("".join(sorted(atuais)))

    # ------------------------------------------------------------------
    # Desfazer
    # ------------------------------------------------------------------

    def _estado(self) -> tuple:
        return (tuple((c.simbolo, c.confianca, c.arbitrada, c.corrigida)
                      for c in self.casas),
                self.lado, self.roque, self.lado_informado, self.roque_informado)

    def _aplicar(self, estado: tuple) -> None:
        casas, lado, roque, lado_informado, roque_informado = estado
        for casa, (simbolo, confianca, arbitrada, corrigida) in zip(self.casas, casas):
            casa.simbolo = simbolo
            casa.confianca = confianca
            casa.arbitrada = arbitrada
            casa.corrigida = corrigida
        self.lado, self.roque = lado, roque
        self.lado_informado, self.roque_informado = lado_informado, roque_informado

    def _registrar(self) -> None:
        """
        Guarda o estado inteiro, e não o que mudou.

        São 64 tuplas curtas — a F3.8 mediu que a cópia rasa de 2.000 boxes
        custa 0,24 ms, e aqui é trinta vezes menos. Estado incremental teria
        estado próprio para errar, que é exatamente o que ela concluiu.
        """
        del self._historico[self._indice + 1:]
        self._historico.append(self._estado())
        self._indice = len(self._historico) - 1

    @property
    def pode_desfazer(self) -> bool:
        return self._indice > 0

    @property
    def pode_refazer(self) -> bool:
        return self._indice < len(self._historico) - 1

    def desfazer(self) -> bool:
        if not self.pode_desfazer:
            return False
        self._indice -= 1
        self._aplicar(self._historico[self._indice])
        return True

    def refazer(self) -> bool:
        if not self.pode_refazer:
            return False
        self._indice += 1
        self._aplicar(self._historico[self._indice])
        return True

    # ------------------------------------------------------------------
    # O que sai daqui
    # ------------------------------------------------------------------

    def _tabuleiro_cru(self) -> chess.Board:
        tabuleiro = chess.Board(None)
        for c in self.ocupadas:
            tabuleiro.set_piece_at(chess.square(c.coluna, 7 - c.linha),
                                   chess.Piece.from_symbol(c.simbolo))
        return tabuleiro

    def tabuleiro(self) -> chess.Board:
        tabuleiro = self._tabuleiro_cru()
        tabuleiro.turn = chess.WHITE if self.lado == "w" else chess.BLACK
        tabuleiro.set_castling_fen(self.roque or "-")
        return tabuleiro

    def fen(self) -> str:
        return self.tabuleiro().fen()

    def problemas(self) -> List[str]:
        """Tudo que impede esta posição de ser real, em português."""
        estado = self.tabuleiro().status()
        return [texto for bandeira, texto in _PROBLEMAS if estado & bandeira]

    @property
    def plausivel(self) -> bool:
        """
        A posição passa em toda a checagem do `python-chess`.

        É mais exigente que `Leitura.plausivel`, que só conta peças: aqui
        entram o xeque do lado errado e o roque impossível, que só passam a
        ser decidíveis depois de alguém dizer quem joga.
        """
        return not self.problemas()

    def avisos(self) -> List[str]:
        """O que o usuário precisa saber antes de levar este FEN embora."""
        saida = []
        if self.lado_informado or self.roque_informado:
            informado = []
            if self.lado_informado:
                informado.append("o lado a jogar")
            if self.roque_informado:
                informado.append("o roque")
            saida.append(
                f"{' e '.join(informado).capitalize()} não está no diagrama: "
                f"veio de quem editou. En passant sai sempre como '-'.")
        else:
            saida.append(AVISO_CONVENCAO)

        problemas = self.problemas()
        if problemas:
            saida.append("Posição impossível: " + "; ".join(problemas) + ".")
        return saida

    def resumo(self) -> str:
        partes = [f"{len(self.ocupadas)} peças"]
        if self.arbitradas:
            partes.append(f"{self.arbitradas} pela legalidade")
        if self.corrigidas:
            partes.append(f"{self.corrigidas} corrigida(s) à mão")
        if not self.plausivel:
            partes.append("posição impossível — confira")
        return ", ".join(partes)

    # ------------------------------------------------------------------
    # O que a F8.3 vai colher
    # ------------------------------------------------------------------

    def correcoes(self) -> List[diag.Casa]:
        """
        As casas mexidas à mão, que é o que uma amostra nova pode sair.

        Existe agora, e não na F8.3, porque é o dado que decide se a fase
        seguinte tem de onde começar: correção que morre na tela não vira
        treino nenhum.
        """
        return [c for c in self.casas if c.corrigida]
