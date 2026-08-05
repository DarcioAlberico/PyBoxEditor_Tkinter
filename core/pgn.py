"""
Da página reconhecida para um `.pgn` que abre num programa de xadrez.

É o fim natural do que a F1.7 começou: `notacao.analisar` já percorre o texto
com um tabuleiro na mão, corrige o que a legalidade decide e sabe onde uma
partida começa. Faltava escrever o resultado num formato que sirva a alguém.

## O que sai, e o que não sai

**Sai a linha principal de cada partida.** Metade do texto destes livros são
variantes — "12.Re1 Qa5 12...Ra6; 12...Ra7; 12...Nb6 13.Qc2" — e elas ficam de
fora, contadas no relatório.

**A regra que separa variante de linha principal é o número da jogada.** Numa
variante o livro repete um número que já passou: o `12...` aparece quatro vezes
acima. Então um lance entra na linha principal só se a jogada dele vier
**depois** da última aceita. É a mesma informação que o tipógrafo usou para o
leitor humano entender que aquilo era um desvio.

Não tentei reconstruir as variantes aninhadas dentro do PGN, embora o formato
suporte. O `analisar` navega variante rebobinando o tabuleiro para uma posição
guardada, e essa estrutura não sobrevive na lista de lances — remontá-la seria
adivinhação, e uma variante colocada no ramo errado é pior que uma variante
ausente: ela parece certa.

## A validação não é opcional

Os lances aceitos foram jogados em tabuleiros que o `analisar` rebobinou várias
vezes. Nada garante que a sequência que sobra encadeie desde a posição inicial.
Por isso `montar` **replica a partida do zero** e corta no primeiro lance que
não couber, registrando onde parou. Um PGN que não carrega é pior que um PGN
curto: o usuário só descobre o problema no outro programa.
"""

import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import chess
import chess.pgn

from core import notacao
from core.box_model import BoxEntry


#: O que o PGN exige e a página não tem como saber.
DESCONHECIDO = "?"


@dataclass
class Partida:
    """Uma partida pronta para virar PGN."""

    lances: List[str] = field(default_factory=list)      # SAN, linha principal
    variantes: int = 0          # lances descartados por repetirem a jogada
    sem_solucao: int = 0        # lances que o OCR não resolveu
    parou_em: Optional[str] = None   # SAN que não encadeou, se houve
    desviou: bool = False       # a leitura seguiu por dentro de uma variante

    @property
    def jogadas(self) -> int:
        return (len(self.lances) + 1) // 2

    def __str__(self):
        partes = [f"{len(self.lances)} lances ({self.jogadas} jogadas)"]
        if self.variantes:
            partes.append(f"{self.variantes} de variante fora")
        if self.sem_solucao:
            partes.append(f"{self.sem_solucao} sem solução")
        if self.desviou:
            partes.append("cortada onde a leitura entrou numa variante")
        if self.parou_em:
            partes.append(f"interrompida em {self.parou_em}")
        return ", ".join(partes)


@dataclass
class Relatorio:
    partidas: List[Partida] = field(default_factory=list)

    @property
    def lances(self) -> int:
        return sum(len(p.lances) for p in self.partidas)

    @property
    def variantes(self) -> int:
        return sum(p.variantes for p in self.partidas)

    @property
    def sem_solucao(self) -> int:
        return sum(p.sem_solucao for p in self.partidas)

    @property
    def interrompidas(self) -> int:
        return sum(1 for p in self.partidas if p.parou_em)

    @property
    def desviadas(self) -> int:
        return sum(1 for p in self.partidas if p.desviou)

    def resumo(self) -> str:
        if not self.partidas:
            return "Nenhuma partida encontrada na página."
        linhas = [f"{len(self.partidas)} partida(s), {self.lances} lances na "
                  f"linha principal."]
        if self.variantes:
            linhas.append(f"{self.variantes} lance(s) de variante ficaram de "
                          f"fora — o PGN guarda só a linha principal.")
        if self.sem_solucao:
            linhas.append(f"{self.sem_solucao} lance(s) o OCR não resolveu; "
                          f"revise-os antes de exportar.")
        if self.desviadas:
            linhas.append(f"{self.desviadas} partida(s) foram cortadas onde a "
                          f"leitura entrou numa variante e não voltou. O que "
                          f"saiu está certo; só é mais curto que a página.")
        if self.interrompidas:
            linhas.append(f"{self.interrompidas} partida(s) foram cortadas "
                          f"onde a sequência deixou de encadear.")
        return "\n".join(linhas)


def _e_avanco(numero: Optional[int], brancas: bool,
              ultimo: Optional[tuple]) -> bool:
    """A jogada vem depois da última aceita? É o que separa linha de variante."""
    if numero is None:
        return False
    if ultimo is None:
        return True
    # Brancas jogam antes das pretas dentro do mesmo número.
    return (numero, 0 if brancas else 1) > (ultimo[0], 0 if ultimo[1] else 1)


def montar(analise: notacao.Analise) -> Relatorio:
    """
    Agrupa os lances da análise em partidas com a linha principal validada.

    A validação replica cada partida do zero, num tabuleiro novo. Um lance que
    não couber corta a partida ali — o que sai é sempre carregável.
    """
    relatorio = Relatorio()
    por_partida: Dict[int, List[notacao.LanceLido]] = {}
    for lance in analise.lances:
        por_partida.setdefault(lance.partida, []).append(lance)

    for indice in sorted(por_partida):
        partida = Partida()
        board = chess.Board()
        ultimo = None

        for lance in por_partida[indice]:
            if lance.san is None:
                partida.sem_solucao += 1
                continue
            if not _e_avanco(lance.numero, lance.brancas, ultimo):
                partida.variantes += 1
                continue
            if partida.parou_em is not None or partida.desviou:
                # Já saiu do trilho: o resto não tem posição de onde partir.
                partida.variantes += 1
                continue

            # **O número diz que avançou; a posição diz de onde.** Quando o
            # texto traz uma variante, o analisador às vezes segue de dentro
            # dela, e os lances seguintes chegam aqui com número de linha
            # principal tendo saído de outro ramo. Aceitá-los produziria um PGN
            # que carrega e está errado — o pior resultado possível, porque
            # ninguém confere uma partida que abre.
            if lance.fen_antes is not None and lance.fen_antes != board.fen():
                partida.desviou = True
                partida.variantes += 1
                continue

            try:
                board.push_san(lance.san)
            except (chess.IllegalMoveError, chess.InvalidMoveError,
                    chess.AmbiguousMoveError):
                partida.parou_em = lance.san
                continue

            partida.lances.append(lance.san)
            ultimo = (lance.numero, lance.brancas)

        if partida.lances or partida.sem_solucao or partida.variantes:
            relatorio.partidas.append(partida)

    return relatorio


def _jogo(partida: Partida, cabecalhos: Optional[Dict[str, str]] = None
          ) -> chess.pgn.Game:
    jogo = chess.pgn.Game()
    for chave in ("Event", "Site", "Date", "Round", "White", "Black", "Result"):
        jogo.headers[chave] = DESCONHECIDO
    jogo.headers["Date"] = DESCONHECIDO * 4 + ".??.??"
    jogo.headers["Result"] = "*"
    if cabecalhos:
        jogo.headers.update({k: v for k, v in cabecalhos.items() if v})

    no = jogo
    board = chess.Board()
    for san in partida.lances:
        movimento = board.push_san(san)
        no = no.add_variation(movimento)

    if partida.parou_em:
        no.comment = (f"[reconhecimento interrompido: '{partida.parou_em}' não "
                      f"encadeia a partir daqui]")
    return jogo


def para_texto(relatorio: Relatorio,
               cabecalhos: Optional[Dict[str, str]] = None) -> str:
    """O conteúdo do `.pgn`. Partidas sem lance nenhum não entram."""
    blocos = []
    for i, partida in enumerate(relatorio.partidas, 1):
        if not partida.lances:
            continue
        cab = dict(cabecalhos or {})
        if len(relatorio.partidas) > 1:
            cab.setdefault("Round", str(i))
        blocos.append(str(_jogo(partida, cab)))
    return "\n\n".join(blocos) + ("\n" if blocos else "")


def exportar(boxes: Sequence[BoxEntry],
             cabecalhos: Optional[Dict[str, str]] = None):
    """`(texto_pgn, relatorio)` a partir dos boxes da página."""
    relatorio = montar(notacao.analisar(boxes))
    return para_texto(relatorio, cabecalhos), relatorio


def cabecalhos_do_documento(caminho: Optional[str],
                            pagina: Optional[int] = None) -> Dict[str, str]:
    """
    Cabeçalhos que dá para preencher com honestidade.

    O nome dos jogadores está na página, mas lê-lo é reconhecer prosa, não
    notação — e um `White` errado é pior que um `White` ausente, porque o
    programa de xadrez o mostra como fato. Fica o `Event` com a origem, que é
    verificável.
    """
    import os

    cab = {"Date": datetime.date.today().strftime("%Y.%m.%d")}
    if caminho:
        origem = os.path.basename(caminho)
        if pagina is not None:
            origem += f", pág. {pagina + 1}"
        cab["Event"] = origem
    return cab
