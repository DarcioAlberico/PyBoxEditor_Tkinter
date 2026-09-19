"""
Desfazer e refazer do editor, por capítulo e por bloco (SPEC_EDITOR DEC-04).

**Por que não o desfazer do `tk.Text`.** Ele desfaz texto, mas `tag_add`,
`tag_remove`, imagens e janelas embutidas ficam fora da pilha dele — um negrito
aplicado não se desfaz, um diagrama apagado não volta. E ele mora no widget, que só
existe para o capítulo desenhado (DEC-11): uma substituição em todo o livro toca
capítulos que ninguém desenhou.

Aqui cada ponto guarda **os blocos afetados, antes e depois**, como modelo — é a
lição de `core/services/history_service.py` (snapshot barato do que mudou, sem
`deepcopy` do documento). A digitação contínua no mesmo bloco é coalescida num
ponto só (a janela de 700 ms é a do Word), e o relógio é injetável para o teste não
esperar.

Nasce na ED-00 porque a ED-01 (`Projeto`) e a ED-03 (`TextoRico`), que correm na
mesma onda, o consomem.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence


@dataclass
class Ponto:
    """O que mudou: os blocos (ou notas) com estes ids, antes e depois."""

    capitulo: str
    ids: tuple[str, ...]
    antes: list[Any]
    depois: list[Any]
    instante: float
    rotulo: str = ""
    #: id -> posicao na lista (blocos ou notas) no momento do "antes"; e o que permite
    #: reinserir um bloco apagado no lugar certo, e nao no fim.
    indices: dict[str, int] = field(default_factory=dict)


@dataclass
class _Pilhas:
    desfazer: list[Ponto] = field(default_factory=list)
    refazer: list[Ponto] = field(default_factory=list)


class Historico:
    """Uma pilha de desfazer/refazer por capítulo (a chave é `Capitulo.arquivo`)."""

    def __init__(self, limite: int = 200, coalescencia_s: float = 0.7,
                 relogio: Callable[[], float] = time.monotonic):
        self.limite = int(limite)
        self.coalescencia_s = float(coalescencia_s)
        self.relogio = relogio
        self._pilhas: dict[str, _Pilhas] = {}

    def _de(self, capitulo: str) -> _Pilhas:
        return self._pilhas.setdefault(capitulo, _Pilhas())

    def ponto(self, capitulo: str, ids: Sequence[str], antes: Sequence[Any], depois: Sequence[Any],
              *, coalescer: bool = False, rotulo: str = "",
              indices: dict[str, int] | None = None) -> Ponto:
        """
        Registra uma mudança. Com `coalescer`, um ponto sobre os **mesmos ids** dentro
        da janela de coalescência funde-se ao anterior (fica o `antes` mais antigo e o
        `depois` mais novo) — é a digitação. Qualquer ponto novo apaga a pilha de refazer.
        """
        pilhas = self._de(capitulo)
        agora = self.relogio()
        ids = tuple(ids)
        ultimo = pilhas.desfazer[-1] if pilhas.desfazer else None
        if (coalescer and ultimo is not None and ultimo.ids == ids
                and agora - ultimo.instante <= self.coalescencia_s):
            ultimo.depois = [copy.deepcopy(b) for b in depois]
            ultimo.instante = agora
            pilhas.refazer.clear()
            return ultimo
        ponto = Ponto(capitulo, ids, [copy.deepcopy(b) for b in antes],
                      [copy.deepcopy(b) for b in depois], agora, rotulo, dict(indices or {}))
        pilhas.desfazer.append(ponto)
        del pilhas.desfazer[:-self.limite]
        pilhas.refazer.clear()
        return ponto

    def desfazer(self, capitulo: str) -> Ponto | None:
        """O ponto a reverter (quem aplica `antes` ao modelo é quem chama), ou `None`."""
        pilhas = self._de(capitulo)
        if not pilhas.desfazer:
            return None
        ponto = pilhas.desfazer.pop()
        pilhas.refazer.append(ponto)
        return ponto

    def refazer(self, capitulo: str) -> Ponto | None:
        pilhas = self._de(capitulo)
        if not pilhas.refazer:
            return None
        ponto = pilhas.refazer.pop()
        pilhas.desfazer.append(ponto)
        return ponto

    def pode_desfazer(self, capitulo: str) -> bool:
        return bool(self._de(capitulo).desfazer)

    def pode_refazer(self, capitulo: str) -> bool:
        return bool(self._de(capitulo).refazer)

    def limpar(self, capitulo: str | None = None) -> None:
        if capitulo is None:
            self._pilhas.clear()
        else:
            self._pilhas.pop(capitulo, None)

    def capitulos_com_historico(self) -> list[str]:
        return [c for c, p in self._pilhas.items() if p.desfazer or p.refazer]


def aplicar(capitulo: Any, ponto: Ponto, sentido: str = "antes") -> list[str]:
    """
    Põe no capítulo os blocos de `ponto.antes` (desfazer) ou `ponto.depois` (refazer),
    pelo id: bloco que existe é trocado no lugar; bloco que não existe mais volta ao
    fim (ou na posição do vizinho anterior, quando ela é conhecida); bloco que só
    existe do outro lado é removido. Devolve os ids tocados. Vale para notas também.
    """
    alvo = ponto.antes if sentido == "antes" else ponto.depois
    outro = ponto.depois if sentido == "antes" else ponto.antes
    por_id = {getattr(b, "id"): b for b in alvo}
    ids_do_outro = {getattr(b, "id") for b in outro}
    tocados: list[str] = []
    for lista in (capitulo.blocos, capitulo.notas):
        posicoes = {getattr(b, "id"): i for i, b in enumerate(lista)}
        # Remove o que só existia do outro lado.
        for bloco_id in list(posicoes):
            if bloco_id in ids_do_outro and bloco_id not in por_id:
                del lista[posicoes[bloco_id]]
                posicoes = {getattr(b, "id"): i for i, b in enumerate(lista)}
                tocados.append(bloco_id)
        # Troca ou reinsere o que está no lado escolhido.
        anterior = None
        for bloco in alvo:
            bloco_id = getattr(bloco, "id")
            e_nota = type(bloco).__name__ == "Nota"
            if (lista is capitulo.notas) != e_nota:
                continue
            copia = copy.deepcopy(bloco)
            if bloco_id in posicoes:
                lista[posicoes[bloco_id]] = copia
            else:
                if bloco_id in ponto.indices:
                    indice = min(ponto.indices[bloco_id], len(lista))
                elif anterior in posicoes:
                    indice = posicoes[anterior] + 1
                else:
                    indice = len(lista)
                lista.insert(indice, copia)
                posicoes = {getattr(b, "id"): i for i, b in enumerate(lista)}
            tocados.append(bloco_id)
            anterior = bloco_id
    return tocados
