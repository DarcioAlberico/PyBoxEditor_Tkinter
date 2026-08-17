"""
A tabela completa de NAGs — os *Numeric Annotation Glyphs* do padrão PGN.

Fonte: <https://en.wikipedia.org/wiki/Portable_Game_Notation#Numeric_Annotation_Glyphs>,
que traz **duas listas**: a padrão (`$0`–`$139`, definida na especificação PGN) e a
não-padrão (`$140`–`$148`, `$220`–`$221`, `$238`–`$255`, convenções do ChessPad e do
Informator). As duas entram aqui, separadas por rótulo de família — quem edita um
livro do Informator precisa do `⌓` da segunda lista tanto quanto do `±` da primeira.

Os intervalos que a especificação reserva sem definir (`$149`–`$219`, `$222`–`$237`)
não aparecem: não há o que anotar com eles.

## Esta tabela não é a mesma que a `ui.main_window.NAGS_POR_FAMILIA`

Aquela é o "Key to symbols used" **destes livros**: 23 símbolos, quatro famílias, os
botões da barra rápida. Esta é o padrão inteiro, 169 entradas, e serve de referência
— a maioria delas nunca vai ser digitada.

Onde as duas se encontram, **o ponto de código é o da barra rápida**, e isso não é
detalhe de estilo. `Δ` (U+0394, que a barra usa) e `∆` (U+2206, que a Wikipedia
imprime em `$140`) têm o mesmo desenho e códigos diferentes; o mesmo vale para `⇄`
(U+21C4) contra `⇆` (U+21C6) do `$132`. Deixar os dois entrarem em `.box` diferentes
daria **duas classes ensinando o mesmo símbolo** ao modelo — o defeito que a F1.5b
já custou a desfazer. Cada divergência está comentada na linha em que acontece.

## Símbolo sem fonte é caixa vazia sem aviso

Seis símbolos desta lista — `⯹`, `⯺`, `⯻`, `⯼`, `⯽`, `⯾` (U+2BF9–U+2BFE, o bloco que
o Unicode 11 reservou para anotação de xadrez) — não são desenhados por **nenhuma**
fonte de uma instalação Windows típica. Medido: das 559 famílias de
`C:\\Windows\\Fonts` deste sistema, nenhuma os cobre; `Segoe UI Symbol` cobre os outros
36 e falha nesses seis; `MS Gothic` falha em 14. Escrever um deles num box produzia um
retângulo vazio no PDF final sem erro nenhum no caminho, que é o defeito do `·` da
SPEC §4.2.

**Cinco deles voltaram a ter desenho**, e não por decreto: a `NotoSansSymbols2` de
`chess_pdf_processor.FONTES_DE_SIMBOLO` cobre U+2BF0–U+2BFD, e `sem_glifo()` a
consulta junto com as outras. Sobra o `⯾` (U+2BFE), que está acima do fim do bloco
que ela desenha — o `$255` continua desligado, e é a medição que diz isso.

Por isso `sem_glifo()` **mede** em vez de decorar: a lista encolhe sozinha quando uma
fonte que os cubra entra em `assets/fonts/`, que foi exatamente o que aconteceu. Quem
monta o menu desliga o que ela devolver.
"""

import os
from dataclasses import dataclass
from typing import List, Optional, Sequence, Set, Tuple


@dataclass(frozen=True)
class Nag:
    """Uma entrada da tabela. `simbolo` vazio = o padrão não lhe deu forma impressa."""
    codigo: int
    simbolo: str
    descricao: str


def _lados(codigo: int, molde: str, simbolo: str = "",
           lado: Tuple[str, str] = ("Brancas", "Negras")) -> List[Nag]:
    """
    O par brancas/negras de um mesmo enunciado.

    De `$14` em diante o padrão é regular: **código par é das brancas, o ímpar
    seguinte é a mesma frase para as negras**, e só o par recebe símbolo impresso
    (`○` em `$26`, `↑` em `$36`, `→` em `$40`…). Escrever as 100 linhas simétricas
    uma a uma esconderia essa regularidade e convidaria a errar um código no meio.
    """
    return [Nag(codigo, simbolo, molde.format(lado[0])),
            Nag(codigo + 1, "", molde.format(lado[1]))]


# ----------------------------------------------------------------------
# A tabela, por família
# ----------------------------------------------------------------------
#
# O agrupamento é nosso — a Wikipedia lista os 169 em fila. Sem famílias, o menu
# seria uma coluna de 169 itens que não cabe em tela nenhuma; o Tk a quebraria em
# colunas sem aviso e achar o `⩲` viraria varredura.

FAMILIAS: List[Tuple[str, List[Nag]]] = [
    ("Lance", [
        Nag(0, "", "Sem anotação"),
        # `!!`, `??`, `!?` e `?!` como dois caracteres, e não `‼` (U+203C), `⁇`
        # (U+2047), `⁉` (U+2049), `⁈` (U+2048), que é como a Wikipedia os imprime:
        # estes livros compõem dois glifos separados, e é isso que o detector de
        # boxes encontra na página. A barra rápida já usava a forma de dois.
        Nag(1, "!", "Boa jogada"),
        Nag(2, "?", "Erro"),
        Nag(3, "!!", "Excelente"),
        Nag(4, "??", "Erro grave"),
        Nag(5, "!?", "Interessante"),
        Nag(6, "?!", "Duvidoso"),
        Nag(7, "□", "Lance forçado (os outros perdem depressa)"),
        Nag(8, "", "Lance único (sem alternativa razoável)"),
        Nag(9, "", "Pior lance"),
    ]),
    ("Avaliação", [
        Nag(10, "=", "Igualdade"),
        Nag(11, "", "Chances iguais, posição tranquila"),
        Nag(12, "", "Chances iguais, posição ativa"),
        Nag(13, "∞", "Posição incerta"),
        Nag(14, "⩲", "Brancas ligeiramente melhor"),
        Nag(15, "⩱", "Negras ligeiramente melhor"),
        Nag(16, "±", "Brancas melhor"),
        Nag(17, "∓", "Negras melhor"),
        # `+-` e `-+` com hífen ASCII, como na barra rápida, e não com o sinal de
        # menos U+2212 da Wikipedia: o traço que estes livros imprimem é o mesmo
        # que o OCR já devolve em `Rxd8-+`.
        Nag(18, "+-", "Brancas vencem"),
        Nag(19, "-+", "Negras vencem"),
        Nag(20, "", "Brancas ganham (Negras deveriam abandonar)"),
        Nag(21, "", "Negras ganham (Brancas deveriam abandonar)"),
    ]),
    ("Zugzwang", _lados(22, "{} em zugzwang", "⨀")),
    ("Espaço", (
        _lados(24, "{} com leve vantagem de espaço")
        + _lados(26, "{} com vantagem de espaço", "○")
        + _lados(28, "{} com vantagem decisiva de espaço")
    )),
    ("Desenvolvimento", (
        _lados(30, "{} com leve vantagem de desenvolvimento")
        + _lados(32, "{} com vantagem de desenvolvimento", "⟳")
        + _lados(34, "{} com vantagem decisiva de desenvolvimento")
    )),
    ("Iniciativa e ataque", (
        _lados(36, "{} com a iniciativa", "↑")
        + _lados(38, "{} com iniciativa duradoura")
        + _lados(40, "{} com o ataque", "→")
    )),
    ("Compensação", (
        _lados(42, "{} com compensação insuficiente pelo material")
        # `⯹` (U+2BF9), que é o desenho impresso: um igual sobre um infinito, e é
        # assim que a p. 4 destes livros o imprime, logo acima do `∞` sozinho de
        # *unclear*. Escreveu-se `≡` aqui enquanto nenhuma fonte do disco o
        # desenhava; a `NotoSansSymbols2` de `FONTES_DE_SIMBOLO` desenha, então a
        # aproximação saiu. A barra rápida usa o mesmo ponto de código.
        + _lados(44, "{} com compensação pelo material", "⯹")
        + _lados(46, "{} com compensação mais que suficiente pelo material")
    )),
    ("Centro", (
        _lados(48, "{} com leve controle do centro")
        + _lados(50, "{} com controle do centro")
        + _lados(52, "{} com controle decisivo do centro")
    )),
    ("Flanco do rei", (
        _lados(54, "{} com leve controle do flanco do rei")
        + _lados(56, "{} com controle do flanco do rei")
        + _lados(58, "{} com controle decisivo do flanco do rei")
    )),
    ("Flanco da dama", (
        _lados(60, "{} com leve controle do flanco da dama")
        + _lados(62, "{} com controle do flanco da dama")
        + _lados(64, "{} com controle decisivo do flanco da dama")
    )),
    ("Primeira fileira", (
        _lados(66, "{} com a primeira fileira vulnerável")
        + _lados(68, "{} com a primeira fileira bem protegida")
    )),
    ("Rei", (
        _lados(70, "Rei {} mal protegido", lado=("das brancas", "das negras"))
        + _lados(72, "Rei {} bem protegido", lado=("das brancas", "das negras"))
        + _lados(74, "Rei {} mal colocado", lado=("das brancas", "das negras"))
        + _lados(76, "Rei {} bem colocado", lado=("das brancas", "das negras"))
    )),
    ("Estrutura de peões", (
        _lados(78, "Estrutura de peões {} muito fraca",
               lado=("das brancas", "das negras"))
        + _lados(80, "Estrutura de peões {} fraca",
                 lado=("das brancas", "das negras"))
        + _lados(82, "Estrutura de peões {} forte",
                 lado=("das brancas", "das negras"))
        + _lados(84, "Estrutura de peões {} muito forte",
                 lado=("das brancas", "das negras"))
    )),
    ("Colocação das peças", (
        _lados(86, "Cavalos {} mal colocados", lado=("das brancas", "das negras"))
        + _lados(88, "Cavalos {} bem colocados", lado=("das brancas", "das negras"))
        + _lados(90, "Bispos {} mal colocados", lado=("das brancas", "das negras"))
        + _lados(92, "Bispos {} bem colocados", lado=("das brancas", "das negras"))
        + _lados(94, "Torres {} mal colocadas", lado=("das brancas", "das negras"))
        + _lados(96, "Torres {} bem colocadas", lado=("das brancas", "das negras"))
        + _lados(98, "Dama {} mal colocada", lado=("das brancas", "das negras"))
        + _lados(100, "Dama {} bem colocada", lado=("das brancas", "das negras"))
        + _lados(102, "Peças {} mal coordenadas", lado=("das brancas", "das negras"))
        + _lados(104, "Peças {} bem coordenadas", lado=("das brancas", "das negras"))
    )),
    ("Abertura", (
        _lados(106, "{} jogaram a abertura muito mal")
        + _lados(108, "{} jogaram a abertura mal")
        + _lados(110, "{} jogaram a abertura bem")
        + _lados(112, "{} jogaram a abertura muito bem")
    )),
    ("Meio-jogo", (
        _lados(114, "{} jogaram o meio-jogo muito mal")
        + _lados(116, "{} jogaram o meio-jogo mal")
        + _lados(118, "{} jogaram o meio-jogo bem")
        + _lados(120, "{} jogaram o meio-jogo muito bem")
    )),
    ("Final", (
        _lados(122, "{} jogaram o final muito mal")
        + _lados(124, "{} jogaram o final mal")
        + _lados(126, "{} jogaram o final bem")
        + _lados(128, "{} jogaram o final muito bem")
    )),
    ("Contrajogo", (
        _lados(130, "{} com leve contrajogo")
        # `⇄` (U+21C4) da barra rápida, e não o `⇆` (U+21C6) da Wikipedia: mesmo
        # desenho espelhado, outro ponto de código.
        + _lados(132, "{} com contrajogo", "⇄")
        + _lados(134, "{} com contrajogo decisivo")
    )),
    ("Relógio", (
        _lados(136, "{} com pressão de tempo")
        + _lados(138, "{} em apuro de tempo (zeitnot)", "⨁")
    )),
    # Daqui para baixo é a lista não-padrão: o que o ChessPad e o Informator
    # acrescentaram por fora da especificação. São justamente as anotações que
    # aparecem impressas nestes livros.
    ("Comentário (não-padrão)", [
        # `Δ` (U+0394) da barra rápida, e não o `∆` (U+2206) da Wikipedia.
        Nag(140, "Δ", "Com a ideia de..."),
        Nag(141, "∇", "Contra..."),
        Nag(142, "⌓", "Melhor é..."),
        Nag(143, "<=", "Pior é..."),
        Nag(144, "==", "Equivale a..."),
        Nag(145, "RR", "Comentário editorial"),
        Nag(146, "N", "Novidade teórica"),
        Nag(147, "!!!", "Lance brilhante raríssimo"),
        Nag(148, "!??", "Objetivamente duvidoso, mas perigoso na prática"),
    ]),
    ("Diagrama (não-padrão)", [
        Nag(220, "⬒", "Diagrama"),
        Nag(221, "⬓", "Diagrama (do lado das negras)"),
    ]),
    ("Posicionais (não-padrão)", [
        # `$238` repete o `○` de `$26`; é assim na fonte, e não é engano de cópia.
        Nag(238, "○", "Vantagem de espaço"),
        Nag(239, "⇔", "Coluna"),
        Nag(240, "⇗", "Diagonal"),
        Nag(241, "⊞", "Centro"),
        Nag(242, "⟫", "Flanco do rei"),
        Nag(243, "⟪", "Flanco da dama"),
        Nag(244, "✕", "Ponto fraco"),
        Nag(245, "⊥", "Final"),
        # $246–$248 e $253 saem sem símbolo de propósito: a Wikipedia os imprime
        # com glifos da fonte "CA Chess", que não têm ponto de código Unicode.
        Nag(246, "", "Par de bispos"),
        Nag(247, "", "Bispos de cores opostas"),
        Nag(248, "", "Bispos da mesma cor"),
        # Os cinco de U+2BFA em diante. Ficaram desligados enquanto nenhuma fonte
        # do disco os desenhava; a `NotoSansSymbols2` cobre até U+2BFD, e o menu
        # os liberou sozinho — só o `⯾` do `$255` continua fora, porque está
        # acima desse fim. Quem responde é `sem_glifo()`, não este comentário.
        Nag(249, "⯺", "Peões ligados"),
        Nag(250, "⯻", "Peões isolados"),
        Nag(251, "⯼", "Peões dobrados"),
        Nag(252, "⯽", "Peão passado"),
        Nag(253, "", "Maioria de peões"),
        Nag(254, "∟", "Com"),
        Nag(255, "⯾", "Sem"),
    ]),
]

#: A tabela achatada, na ordem dos códigos.
TABELA: List[Nag] = [n for _, familia in FAMILIAS for n in familia]

#: Por código, para quem chega com um `$14` na mão (a exportação PGN, um dia).
POR_CODIGO = {n.codigo: n for n in TABELA}


def rotulo(nag: Nag) -> str:
    """
    O texto do item de menu: código, símbolo e enunciado.

    O código vai junto porque é a identidade do NAG — é `$14` que aparece dentro
    de um `.pgn`, não `⩲`. O travessão marca quem não tem forma impressa.
    """
    return f"${nag.codigo:<4} {nag.simbolo or '—':<4} {nag.descricao}"


# ----------------------------------------------------------------------
# Cobertura de fonte
# ----------------------------------------------------------------------

_cache_sem_glifo: Optional[Set[str]] = None


def sem_glifo(simbolos: Optional[Sequence[str]] = None) -> Set[str]:
    """
    Quais destes símbolos **nenhuma** fonte candidata do disco desenha.

    A pergunta é "alguma cobre?", e não "todas cobrem": a cadeia de
    `CHESS_FONT_CANDIDATES` é uma lista de tentativas, e `resolve_chess_font`
    escolhe a primeira que serve. Custa 17 ms para a tabela inteira, uma vez por
    processo — barato o bastante para rodar na montagem do menu e não decorar uma
    resposta que muda quando alguém instala uma fonte.

    Sem PyMuPDF não dá para responder, e aí devolve o conjunto vazio: melhor um
    menu inteiro habilitado do que um menu inteiro desligado por causa de uma
    dependência que só o PDF usa.
    """
    global _cache_sem_glifo
    if simbolos is None:
        if _cache_sem_glifo is not None:
            return _cache_sem_glifo
        alvo = sorted({c for n in TABELA for c in n.simbolo})
        _cache_sem_glifo = sem_glifo(alvo)
        return _cache_sem_glifo

    alvo = {c for s in simbolos for c in s}
    if not alvo:
        return set()

    try:
        from core.chess_pdf_processor import (CHESS_FONT_CANDIDATES,
                                              FONTES_DE_SIMBOLO,
                                              missing_glyphs)
    except Exception:
        return set()

    faltam = set(alvo)
    # As duas listas, porque a pergunta é "alguma desenha?" e a resposta pode
    # estar na fonte de recurso. Ela vem depois de propósito: quem escreve o PDF
    # consulta a principal primeiro, e esta ordem é a mesma.
    for caminho in list(CHESS_FONT_CANDIDATES) + list(FONTES_DE_SIMBOLO):
        if not faltam:
            break
        if not os.path.exists(caminho):
            continue
        try:
            faltam &= set(missing_glyphs(caminho, "".join(sorted(alvo))))
        except Exception:      # fonte ilegível não condena a tabela
            continue
    return faltam


def desenhavel(nag: Nag, ausentes: Optional[Set[str]] = None) -> bool:
    """Dá para escrever este NAG num box? Precisa de símbolo E de fonte."""
    if not nag.simbolo:
        return False
    if ausentes is None:
        ausentes = sem_glifo()
    return not any(c in ausentes for c in nag.simbolo)
