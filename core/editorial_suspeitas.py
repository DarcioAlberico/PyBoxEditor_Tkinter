"""O que faz de uma linha lida uma **suspeita** — e como dizer isso a alguém.

A fila de revisão editorial (`core.editorial_review`) só existe se tiver o
que pôr dentro. O leitor medido (`core.livro`) devolve cada linha com um
registro de roteamento — a âncora da cadeia própria, a linha do motor, quem
escreveu o texto final e as contas da fusão — mas nenhum "está errado": a
fusão por palavra decide e segue. Até 2026-09-19 o adapter do IR marcava todo
bloco como `automatic` com confiança 1,0, e a fila de um livro inteiro saía
vazia; ao lado dela, a fila da fachada nova punha o livro **inteiro** dentro.

Este módulo é a régua entre as duas: lê o registro de uma linha e devolve os
motivos pelos quais ela merece um olhar humano, **em código e em frase**. O
código é o que a fila ordena e o dataset de correções guarda; a frase é o
que o revisor lê — `low_confidence` não diz nada a quem está com o livro na
mão, e "o motor de prosa não confirmou esta linha" diz.

As regras são lexicais e geométricas, como as de `livro.py`, e vieram de
olhar os resíduos das quatro páginas de referência de 2026-09-18 (ver
`docs/REVISAO_MODOS_OCR.md`, §4.1): o `25♖xc7!` sem o ponto, o `26...g16`,
o `57..♖xc4?`, o `w♖g1`, os dois `*` que a cadeia derrubou, o `a6` onde o
motor leu `gxh5`, o `1` solto no fim da linha em que o livro imprime `1–0`.
Cada uma existe por um desses. O que elas **não** pegam — e não há regra
barata que pegue — é o erro confiante da cadeia num lance bem formado:
`⩲` por `±`, `♕c1` por `♕e1`. Isso é a OCR-14, e é treino, não fila.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping, Sequence

from core import notacao

#: A confiança de uma linha que nenhuma regra apontou e que o motor não mediu
#: (a linha só de lances, que a cadeia lê sozinha).
CONFIANCA_SEM_MEDIDA = 0.9

#: Quanto cada motivo pesa: é o que ordena a fila entre linhas suspeitas e o
#: que a confiança da linha desconta. A ordem segue a spec (§9): o que muda o
#: lance vem antes do que muda a palavra, e o que muda a palavra vem antes do
#: sinal estranho.
PESOS = {
    "fen_invalid": 0.95,
    "line_lost": 0.90,
    "diagram_uncertain": 0.80,
    "notation_conflict": 0.65,
    "malformed_move": 0.60,
    "malformed_move_number": 0.60,
    "orientation_missing": 0.50,
    "engine_disagreed": 0.50,
    "motor_indisponivel": 0.50,
    "result_incomplete": 0.45,
    "dropped_in_notation": 0.40,
    "low_confidence": 0.40,
    "engine_missing": 0.35,
    "stray_mark": 0.30,
    "engine_garbage": 0.25,
}

#: Os motivos em linguagem humana — os desta régua e os que chegam de outros
#: lugares (a Fase 4 dos diagramas, a própria sessão de revisão). Quem não
#: está aqui aparece pelo código, que é melhor que nada e pior que tudo.
MOTIVOS = {
    "line_lost": "a linha ficou vazia: a cadeia derrubou {descartados} caractere(s) por confiança",
    "notation_conflict": "o motor leu o lance «{motor}» onde a cadeia leu «{ancora}»",
    "malformed_move": "«{token}» tem figurina mas não tem forma de lance",
    "malformed_move_number": "«{token}» começa como número de lance mas não é lance",
    "engine_disagreed": "o motor de prosa não confirmou a linha (semelhança {semelhanca:.0%}); "
                        "a prosa ficou com a cadeia própria",
    "result_incomplete": "«{token}» solto no fim da linha de lances: resultado incompleto?",
    "dropped_in_notation": "a cadeia derrubou {descartados} caractere(s) nesta linha de lances "
                           "e o motor não repôs",
    "engine_missing": "o motor de prosa não devolveu esta linha; a prosa ficou com a cadeia própria",
    "engine_garbage": "«{token}» traz um sinal que não é de prosa",
    "stray_mark": "a linha é só um sinal: «{token}»",
    "motor_indisponivel": "o motor de prosa faltou nesta página; ela saiu só com a cadeia própria",
    "diagram_uncertain": "o modelo não confiou na leitura do diagrama e a figura saiu recortada",
    "orientation_missing": "não há coordenadas impressas que digam o lado do tabuleiro",
    "side_to_move_convention": "o lado a jogar é convenção (brancas), não leitura",
    "fen_invalid": "a posição lida não é legal",
    "low_confidence": "a confiança da leitura ficou abaixo do piso",
    "layout_ambiguous": "a ordem de leitura desta região é ambígua",
    "manual_review": "marcado para revisão manual",
    "unresolved": "sem leitura: precisa de decisão humana",
    "page_result_region": "região lida pelo pipeline de página",
    "page_result_text": "texto da página sem regiões",
    "legacy_adapter": "lido pelo leitor de livro (cadeia própria + motor de prosa)",
    "accepted": "aceito pelo revisor",
    "human_correction": "corrigido pelo revisor",
    "rejected": "rejeitado pelo revisor",
    "deferred": "adiado pelo revisor",
    "batch": "aceito em lote",
    "undo": "desfeito",
}

#: Códigos que dizem de onde a leitura veio, e não que ela está em dúvida.
#: Ficam fora da frase da fila — o revisor quer saber o que conferir, não a
#: genealogia do bloco.
PROCEDENCIA = frozenset({"legacy_adapter", "page_result_region", "page_result_text"})

_FIGURINAS = notacao.GLIFOS_DE_XADREZ
#: A célula da tabela do Nunn: `B♖h2`, `W♔d1` — cor, peça e casa, sem número
#: de lance. Não é SAN, e é a única forma com figurina fora do SAN que estes
#: livros imprimem; `w♖g1` (minúscula) não é ela, e é um dos resíduos.
_RE_PECA_NA_CASA = re.compile(
    r"^[WB]?[" + "".join(sorted(_FIGURINAS)) + r"][a-h][1-8]$")
#: O começo de um número de lance: `26.`, `26...`, `(26...`.
_RE_COMECA_COMO_NUMERO = re.compile(r"^\(?\d{1,3}\.{1,3}(?=\S)")
#: O que sobra de um lance depois do número e da peça: `xh5`, `e4`, `g5+`.
#: É por isto que se compara o lance do motor com o da cadeia — o motor lê a
#: figurina como `B`, `H`, `W`, e a letra da peça não vale nada nele.
_RE_CAUDA = re.compile(r"x?[a-h][1-8](?:=[A-Z])?[+#]?")
#: O lance que vale como leitura do motor: SAN inteiro, com a origem — peça
#: em letra (`Nf3`, `Rxe5`) ou peão (`e4`, `gxh5`). `RE_LANCE_ESTRITO` aceita
#: `xe7` (tudo opcional antes da casa), que no motor é a figurina caída, e
#: não um lance.
_RE_LANCE_DO_MOTOR = re.compile(
    r"^(?:\d{1,3}\.(?:\.\.)?)?"
    r"(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h](?:x[a-h])?[1-8])"
    r"(?:=[QRBN])?[+#]?[!?]{0,2}$")
#: Abaixo disto a linha do motor não serve de contraprova de lance: o
#: `26...e6` que ele lê a 0,4 onde a cadeia lê `26...g6` é ruído dele.
CONFIANCA_MINIMA_PARA_CONTRAPROVA = 0.6
_SINAIS_ESTRANHOS = frozenset("[]{}|\\§")
#: O que pode vir depois do lance, colado: xeque, anotação e a avaliação —
#: `+–`, `–+`, `±`, `∞` —, com o traço em qualquer das três formas que a
#: impressão e o motor usam. `RE_LANCE_ESTRITO` só admite um sinal de
#: avaliação depois do `!?`, e o Chess Evolution imprime `3.♕h4+–` e
#: `6.♘e5†+–` em toda solução: sem isto, a fila era a página inteira.
_RE_SUFIXO_DE_AVALIACAO = re.compile(r"[+\-–—±∓⩱⩲=∞!?#□■△▼]+$")
#: O `’s` que o motor escreve como `,s`: `opponent,s`.
_RE_APOSTROFO_TROCADO = re.compile(r"^[A-Za-z]+,s$")
#: A aspa curva que abre e não fecha: o Tesseract escreve `‘` onde há um
#: cisco na margem (`‘The`, p. 30 do Aagaard), e a prosa destes livros
#: fecha a aspa que abre.
_ASPAS = {"‘": "’", "“": "”"}
_RESULTADO_PARTIDO = frozenset({"1", "0", "½", "1-", "0-", "½-", "1–", "0–", "½–"})


@dataclass(frozen=True)
class Motivo:
    codigo: str
    frase: str

    @property
    def peso(self) -> float:
        return PESOS.get(self.codigo, 0.3)


def descrever(codigo: str, **valores: Any) -> str:
    """A frase de um código; sem modelo para ele, o próprio código."""
    modelo = MOTIVOS.get(codigo)
    if modelo is None:
        return codigo
    try:
        return modelo.format(**valores)
    except (KeyError, IndexError, ValueError):
        # Sem os valores o modelo pede, a frase sai com o buraco à mostra —
        # melhor que uma exceção no meio da fila.
        return re.sub(r"\{[^}]*\}", "…", modelo)


def descrever_codigos(codigos: Iterable[str]) -> list[str]:
    """As frases de uma lista de códigos, sem repetição e sem a procedência."""
    frases: list[str] = []
    for codigo in codigos:
        if codigo in PROCEDENCIA:
            continue
        frase = descrever(codigo)
        if frase not in frases:
            frases.append(frase)
    return frases


def _nucleo(token: str) -> str:
    return token.strip(notacao._PONTUACAO_DE_BORDA)


def _tem_figurina(texto: str) -> bool:
    return any(c in _FIGURINAS for c in texto)


def _lance_bem_formado(nucleo: str) -> bool:
    """A forma que um token com figurina pode ter: SAN com figurina no lugar
    da peça, a peça na casa da tabela, ou uma figurina sozinha (a prosa que
    fala da peça: "the ♘ is strong")."""
    if not nucleo:
        return True
    if len(nucleo) == 1 and nucleo in _FIGURINAS:
        return True
    if notacao.RE_SINAL_DE_AVALIACAO.match(nucleo):
        return True
    # `♔h6/h8/♖d2` — alternativas com barra, como o Nunn imprime na tabela.
    partes = [p for p in nucleo.split("/") if p]
    if len(partes) > 1:
        return all(not _tem_figurina(p) or _lance_bem_formado(p) for p in partes)
    if notacao.RE_LANCE_ESTRITO.match(nucleo) or _RE_PECA_NA_CASA.match(nucleo):
        return True
    sem_sufixo = _RE_SUFIXO_DE_AVALIACAO.sub("", nucleo)
    return bool(sem_sufixo != nucleo and sem_sufixo
                and notacao.RE_LANCE_ESTRITO.match(sem_sufixo))


def _e_lance_com_avaliacao(nucleo: str) -> bool:
    """`5.e7++–`: lance sem figurina com a avaliação colada."""
    sem_sufixo = _RE_SUFIXO_DE_AVALIACAO.sub("", nucleo)
    return bool(sem_sufixo and notacao.e_token_de_notacao(sem_sufixo))


def _cauda(nucleo: str) -> str | None:
    achado = _RE_CAUDA.search(nucleo)
    return achado.group(0) if achado else None


def _lances_do_motor(linha_ocr: str) -> list[str]:
    """Os tokens do motor que são SAN bem formado — o motor não escreve
    figurina, então o que ele lê como lance é peão, ou peça em letra."""
    lances = []
    for token in str(linha_ocr or "").split():
        nucleo = _nucleo(token)
        if nucleo and _RE_LANCE_DO_MOTOR.match(nucleo):
            lances.append(nucleo)
    return lances


def _motivos_dos_tokens(texto: str, dominio: str) -> list[Motivo]:
    motivos: list[Motivo] = []
    tokens = str(texto or "").split()
    for token in tokens:
        nucleo = _nucleo(token)
        if not nucleo:
            continue
        if _tem_figurina(nucleo):
            if not _lance_bem_formado(nucleo):
                motivos.append(Motivo("malformed_move",
                                      descrever("malformed_move", token=token)))
            continue
        if (_RE_COMECA_COMO_NUMERO.match(nucleo) and not notacao.e_token_de_notacao(token)
                and not _e_lance_com_avaliacao(nucleo)):
            motivos.append(Motivo("malformed_move_number",
                                  descrever("malformed_move_number", token=token)))
            continue
        if ((any(c in _SINAIS_ESTRANHOS for c in nucleo) and any(c.isalpha() for c in nucleo))
                or _RE_APOSTROFO_TROCADO.match(nucleo)):
            motivos.append(Motivo("engine_garbage",
                                  descrever("engine_garbage", token=token)))
        elif token[:1] in _ASPAS and _ASPAS[token[0]] not in texto and "'" not in texto:
            motivos.append(Motivo("engine_garbage",
                                  descrever("engine_garbage", token=token)))
    if dominio == "notation" and tokens and tokens[-1] in _RESULTADO_PARTIDO:
        motivos.append(Motivo("result_incomplete",
                              descrever("result_incomplete", token=tokens[-1])))
    # A figurina sozinha no **fim** de uma linha com lances: a casa dela
    # caiu (`3.♖e8+ ♘d8 4.♘e5 ♕`, p. 34 do Yusupov). No meio da prosa a
    # figurina solta é a peça de que se fala; no fim da linha de lances, não.
    if (dominio in ("notation", "mixed") and len(tokens) > 1
            and len(_nucleo(tokens[-1])) == 1 and _nucleo(tokens[-1]) in _FIGURINAS):
        motivos.append(Motivo("malformed_move",
                              descrever("malformed_move", token=tokens[-1])))
    # A linha que é um sinal só (`:`, `/`, `-`): o cisco da trama que a
    # cadeia leu como pontuação (p. 47 do Yusupov, o painel sobre meio-tom).
    if len(tokens) == 1 and len(tokens[0]) <= 2 and not any(c.isalnum() for c in tokens[0]) \
            and not _tem_figurina(tokens[0]) and not notacao.e_token_de_notacao(tokens[0]):
        motivos.append(Motivo("stray_mark", descrever("stray_mark", token=tokens[0])))
    return motivos


def _conflito_de_lance(texto: str, linha_ocr: str) -> Motivo | None:
    """O motor leu um lance bem formado cuja cauda (`xh5`) não está em lance
    nenhum da linha final: `a6` na cadeia, `gxh5` no motor. A peça não entra
    na comparação — o motor a lê como letra qualquer —, e por isso `58.Bxd4`
    do motor contra `58.♖xd4` da cadeia não é conflito."""
    lidos = _lances_do_motor(linha_ocr)
    if not lidos:
        return None
    caudas = set()
    for token in str(texto or "").split():
        nucleo = _nucleo(token)
        if nucleo and notacao.e_token_de_notacao(nucleo):
            for parte in nucleo.split("/"):
                cauda = _cauda(parte)
                if cauda:
                    caudas.add(cauda)
    candidatos = [_nucleo(t) for t in str(texto or "").split()
                  if notacao.e_token_de_notacao(_nucleo(t)) and _cauda(_nucleo(t))]
    for lance in lidos:
        cauda = _cauda(lance)
        if cauda and cauda not in caudas:
            # O lance da cadeia mais parecido é o que fica na frase: qual
            # está no mesmo lugar não dá para saber sem as caixas. O lance
            # de peão do motor procura primeiro um lance de peão da cadeia —
            # a peça o motor lê como letra, e `gxh5` não é `♕g5+`.
            de_peao = re.sub(r"^\d{1,3}\.{1,3}", "", lance)[:1] not in "KQRBN"
            proximos = ([c for c in candidatos if not _tem_figurina(c)]
                        if de_peao else candidatos) or candidatos
            ancora = max(proximos, default="?",
                         key=lambda c: SequenceMatcher(None, c, lance).ratio())
            return Motivo("notation_conflict",
                          descrever("notation_conflict", motor=lance, ancora=ancora))
    return None


def motivos_da_linha(registro: Mapping[str, Any]) -> list[Motivo]:
    """Os motivos de suspeita de uma linha, pelo registro de roteamento dela.

    Vazio é a linha que não tem o que conferir por regra — o que não quer
    dizer certa: quer dizer que a régua não viu nada. O fragmento que o
    detector descartou de propósito (`fragmento`) nunca é suspeita.
    """
    if registro.get("fragmento"):
        return []
    texto = str(registro.get("texto") or "")
    ancora = str(registro.get("ancora") or "")
    linha_ocr = str(registro.get("linha_ocr") or "")
    dominio = str(registro.get("dominio") or "unknown")
    fonte = str(registro.get("fonte") or "glyph")
    primario = str(registro.get("primario") or "")
    descartados = int(registro.get("descartados") or 0)
    preenchidas = int(registro.get("lacunas_preenchidas") or 0)
    semelhanca = registro.get("semelhanca")

    if not texto.strip():
        if descartados > 0 or ancora.strip():
            frase = descrever("line_lost", descartados=descartados)
            if linha_ocr.strip():
                frase += f"; o motor leu «{linha_ocr.strip()}»"
            return [Motivo("line_lost", frase)]
        return []

    motivos: list[Motivo] = []
    if primario == "line" and fonte == "glyph":
        if linha_ocr.strip():
            motivos.append(Motivo("engine_disagreed", descrever(
                "engine_disagreed",
                semelhanca=float(semelhanca) if semelhanca is not None else 0.0)))
        else:
            motivos.append(Motivo("engine_missing", descrever("engine_missing")))
    if dominio == "notation" and descartados > preenchidas:
        motivos.append(Motivo("dropped_in_notation", descrever(
            "dropped_in_notation", descartados=descartados - preenchidas)))
    motivos.extend(_motivos_dos_tokens(texto, dominio))
    if float(registro.get("confianca_ocr") or 0.0) >= CONFIANCA_MINIMA_PARA_CONTRAPROVA:
        conflito = _conflito_de_lance(texto, linha_ocr)
        if conflito is not None:
            motivos.append(conflito)
    return motivos


def confianca_da_linha(registro: Mapping[str, Any],
                       motivos: Sequence[Motivo] | None = None) -> float:
    """A confiança de uma linha, para a fila ordenar — não para decidir.

    Sem motivo, é a semelhança entre a âncora e o motor (as duas leituras
    concordam tanto quanto isto) ou `CONFIANCA_SEM_MEDIDA` na linha que só
    a cadeia leu. Com motivo, o maior peso desconta, e cada motivo a mais
    tira um pouco: é evidência para priorizar (`CONTEXT.md`, invariante 5).
    """
    if motivos is None:
        motivos = motivos_da_linha(registro)
    semelhanca = registro.get("semelhanca")
    base = (float(semelhanca) if semelhanca is not None
            and str(registro.get("fonte")) != "glyph" else CONFIANCA_SEM_MEDIDA)
    base = max(0.0, min(1.0, base))
    if not motivos:
        return base
    desconto = max(m.peso for m in motivos) + 0.1 * (len(motivos) - 1)
    return round(max(0.0, min(base, 1.0 - desconto)), 4)
