import copy
from typing import List, Dict, Any, Callable


class HistoryManager:
    """
    Gerenciador de Undo/Redo baseado em snapshots de estado.
    Ideal para estados pequenos (lista de boxes).
    """

    def __init__(self, max_history: int = 50):
        self._history: List[List[Dict[str, Any]]] = []
        self._index: int = -1
        self._max_history = max_history

    def snapshot(self, boxes: List[Dict[str, Any]], selected_index: int = -1):
        """
        Salva um snapshot do estado atual.
        Se houver estados "futuros" (após um undo), eles são descartados.
        """
        # Corta o histórico futuro se estivermos no meio
        if self._index < len(self._history) - 1:
            self._history = self._history[:self._index + 1]

        # Salva cópia profunda + índice selecionado
        state = {
            "boxes": copy.deepcopy(boxes),
            "selected_index": selected_index,
        }
        self._history.append(state)

        # Limita tamanho do histórico
        if len(self._history) > self._max_history:
            self._history.pop(0)
        else:
            self._index += 1

    def undo(self) -> tuple:
        """
        Desfaz a última ação. Retorna (boxes, selected_index) ou (None, None) se não houver o que desfazer.
        """
        if self._index <= 0:
            return None, None

        self._index -= 1
        state = self._history[self._index]
        return copy.deepcopy(state["boxes"]), state["selected_index"]

    def redo(self) -> tuple:
        """
        Refaz a ação desfeita. Retorna (boxes, selected_index) ou (None, None) se não houver o que refazer.
        """
        if self._index >= len(self._history) - 1:
            return None, None

        self._index += 1
        state = self._history[self._index]
        return copy.deepcopy(state["boxes"]), state["selected_index"]

    def can_undo(self) -> bool:
        return self._index > 0

    def can_redo(self) -> bool:
        return self._index < len(self._history) - 1

    def reset(self):
        """Limpa o histórico (ex: ao abrir nova imagem)."""
        self._history = []
        self._index = -1
