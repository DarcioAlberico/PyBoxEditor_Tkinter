"""
F3.8 — o snapshot deixa de custar uma tecla travada.

Toda mutação passa por `_commit_change`, que tira um snapshot. No modo digitação
da F3.1 isso é **uma vez por tecla**, e com `copy.deepcopy` de uma lista de
dataclasses custava 15,8 ms numa página de 2.000 boxes.

O risco de trocar a representação do histórico é perder campo na ida e volta —
confiança e origem não aparecem no canvas nem na lista como número exato, e um
undo que os zerasse passaria despercebido até o box reaparecer sem cor. Daí a
maioria destes testes ser sobre igualdade exata de estado.

Rodar sem pytest:      python tests/test_f38_historico.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.box_model import BoxEntry
from core.services.history_service import HistoryManager


def _pagina(n=5, prefixo="a"):
    return [BoxEntry(f"{prefixo}{i}", i * 10, 0, i * 10 + 8, 12,
                     confidence=0.1 * i, source="neural" if i % 2 else "")
            for i in range(n)]


def _estados(boxes):
    return [b.as_state() for b in boxes]


# ----------------------------------------------------------------------
# BoxEntry: as_state / from_state
# ----------------------------------------------------------------------

def test_as_state_leva_todos_os_campos():
    b = BoxEntry("fi", 1, 2, 3, 4, confidence=0.75, source="lote", angulo=90)
    assert b.as_state() == ("fi", 1, 2, 3, 4, 0.75, "lote", 90)


def test_from_state_desfaz_as_state():
    b = BoxEntry("♞", 5, 6, 7, 8, confidence=0.33, source="easyocr")
    assert BoxEntry.from_state(b.as_state()) == b


def test_as_state_nao_e_as_tuple():
    """`as_tuple` é para quem desenha; `as_state` é para guardar sem perder."""
    import dataclasses

    b = BoxEntry("a", 1, 2, 3, 4, confidence=0.9, source="manual")
    assert b.as_tuple() == ("a", 1, 2, 3, 4)
    # Um item por campo do dataclass, e não um número fixo: assim o teste
    # cobra o contrato ("não perde nada") de qualquer campo que apareça
    # depois — o `angulo` da F8.1 foi o primeiro a aparecer.
    assert len(b.as_state()) == len(dataclasses.fields(BoxEntry))


def test_from_state_devolve_objeto_novo():
    b = BoxEntry("a", 1, 2, 3, 4)
    outro = BoxEntry.from_state(b.as_state())
    outro.char = "z"
    assert b.char == "a"


# ----------------------------------------------------------------------
# Ida e volta: nada pode se perder
# ----------------------------------------------------------------------

def test_undo_devolve_o_estado_identico():
    h = HistoryManager()
    antes = _pagina()
    h.snapshot(antes, 2)

    depois = [b.copy() for b in antes]
    depois[1].char, depois[1].confidence, depois[1].source = "Z", 1.0, "lote"
    h.snapshot(depois, 1)

    voltou, sel = h.undo()
    assert _estados(voltou) == _estados(antes)
    assert sel == 2


def test_redo_devolve_o_estado_identico():
    h = HistoryManager()
    antes = _pagina()
    depois = _pagina(prefixo="b")
    h.snapshot(antes, 0)
    h.snapshot(depois, 4)

    h.undo()
    refeito, sel = h.redo()
    assert _estados(refeito) == _estados(depois)
    assert sel == 4


def test_confianca_e_origem_sobrevivem():
    """O canvas não mostra o número exato; um undo que o zerasse passaria."""
    h = HistoryManager()
    boxes = [BoxEntry("a", 0, 0, 5, 5, confidence=0.8765, source="neural")]
    h.snapshot(boxes, 0)
    h.snapshot([BoxEntry("b", 0, 0, 5, 5, confidence=1.0, source="manual")], 0)

    voltou, _ = h.undo()
    assert voltou[0].confidence == 0.8765
    assert voltou[0].source == "neural"


def test_box_vazio_e_ligadura_sobrevivem():
    h = HistoryManager()
    boxes = [BoxEntry("", 0, 0, 5, 5), BoxEntry("fi", 6, 0, 12, 5),
             BoxEntry("~", 13, 0, 18, 5)]
    h.snapshot(boxes, 0)
    h.snapshot([], 0)
    voltou, _ = h.undo()
    assert [b.char for b in voltou] == ["", "fi", "~"]


def test_lista_vazia_e_estado_valido():
    h = HistoryManager()
    h.snapshot([], -1)
    h.snapshot(_pagina(), 0)
    voltou, sel = h.undo()
    assert voltou == []
    assert sel == -1


# ----------------------------------------------------------------------
# Isolamento: mexer no resultado não pode contaminar o histórico
# ----------------------------------------------------------------------

def test_mutar_o_que_voltou_nao_contamina_o_historico():
    """`MainWindow` faz `self.boxes = <o que voltou>` e muta no lugar."""
    h = HistoryManager()
    h.snapshot(_pagina(), 0)
    h.snapshot(_pagina(prefixo="b"), 0)

    voltou, _ = h.undo()
    voltou[0].char = "ESTRAGADO"
    voltou.append(BoxEntry("x", 0, 0, 1, 1))

    h.redo()
    de_novo, _ = h.undo()
    assert de_novo[0].char == "a0"
    assert len(de_novo) == 5


def test_mutar_a_lista_depois_do_snapshot_nao_o_altera():
    h = HistoryManager()
    boxes = _pagina()
    h.snapshot(boxes, 0)

    boxes[0].char = "DEPOIS"
    boxes.pop()
    h.snapshot(boxes, 0)

    voltou, _ = h.undo()
    assert voltou[0].char == "a0"
    assert len(voltou) == 5


# ----------------------------------------------------------------------
# Navegação do histórico (o que já valia antes)
# ----------------------------------------------------------------------

def test_sem_o_que_desfazer():
    h = HistoryManager()
    assert h.undo() == (None, None)
    h.snapshot(_pagina(), 0)
    assert h.undo() == (None, None)
    assert not h.can_undo()


def test_sem_o_que_refazer():
    h = HistoryManager()
    h.snapshot(_pagina(), 0)
    assert h.redo() == (None, None)
    assert not h.can_redo()


def test_mutar_depois_de_desfazer_descarta_o_futuro():
    h = HistoryManager()
    for p in ("a", "b", "c"):
        h.snapshot(_pagina(prefixo=p), 0)

    h.undo()                       # volta para 'b'; 'c' vira futuro
    assert h.can_redo()
    h.snapshot(_pagina(prefixo="d"), 0)
    assert not h.can_redo(), "o 'c' deveria ter sido descartado"

    # desfazer a partir de 'd' leva a 'b', que era o estado de onde ele saiu
    voltou, _ = h.undo()
    assert voltou[0].char == "b0"


def test_teto_do_historico_descarta_o_mais_antigo():
    h = HistoryManager(max_history=3)
    for i in range(6):
        h.snapshot([BoxEntry(str(i), 0, 0, 5, 5)], 0)
    assert len(h._history) == 3

    chars = []
    while h.can_undo():
        voltou, _ = h.undo()
        chars.append(voltou[0].char)
    assert chars == ["4", "3"]


def test_reset_esvazia():
    h = HistoryManager()
    h.snapshot(_pagina(), 0)
    h.snapshot(_pagina(), 0)
    h.reset()
    assert not h.can_undo() and not h.can_redo()
    assert h._history == []


def test_ida_e_volta_repetida_converge():
    h = HistoryManager()
    a, b = _pagina(prefixo="a"), _pagina(prefixo="b")
    h.snapshot(a, 0)
    h.snapshot(b, 1)
    for _ in range(5):
        assert _estados(h.undo()[0]) == _estados(a)
        assert _estados(h.redo()[0]) == _estados(b)


# ----------------------------------------------------------------------
# O ponto do item: o custo
# ----------------------------------------------------------------------

def test_snapshot_nao_usa_deepcopy():
    """
    O `deepcopy` percorria grafo de objetos para um dataclass de campos todos
    imutáveis — 15,8 ms contra 0,19 ms, numa operação por tecla.

    Olha o módulo importado, e não o texto do arquivo: o próprio docstring da
    classe cita `copy.deepcopy` ao explicar a medição.
    """
    from core.services import history_service

    assert not hasattr(history_service, "copy"), \
        "o módulo voltou a importar `copy`"


def test_o_snapshot_guarda_tupla_e_nao_boxentry():
    h = HistoryManager()
    h.snapshot(_pagina(), 0)
    guardado = h._history[0]["boxes"]
    assert all(isinstance(t, tuple) for t in guardado)


def test_snapshot_de_pagina_grande_e_rapido():
    """
    Guarda de regressão, com folga grande sobre o medido (0,24 ms em 2.000
    boxes) para não virar teste instável em máquina ocupada. O que ele pega é
    a volta de uma cópia profunda, que custaria ~15 ms.
    """
    import time

    boxes = [BoxEntry("e", i, 0, i + 8, 12, confidence=0.9, source="neural")
             for i in range(2000)]
    h = HistoryManager()
    h.snapshot(boxes, 0)                      # aquece

    inicio = time.perf_counter()
    for _ in range(10):
        h.snapshot(boxes, 0)
    ms = (time.perf_counter() - inicio) / 10 * 1000
    assert ms < 5.0, f"snapshot custou {ms:.2f} ms por chamada"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
