from typing import List, Optional, Sequence, Tuple

from core.box_model import BoxEntry


class HistoryManager:
    """
    Undo/redo por snapshot do estado inteiro.

    **O snapshot guarda tuplas, não `BoxEntry`, e isso é a diferença entre o
    modo digitação ser usável ou não.** Toda mutação passa por
    `MainWindow._commit_change`, que tira um snapshot — no modo digitação da
    F3.1 isso é uma vez por tecla. Com `copy.deepcopy` de uma lista de
    dataclasses, medido numa página de 2.000 boxes:

        copy.deepcopy(boxes)                     15,79 ms
        [copy.copy(b) for b in boxes]             3,33 ms
        [b.copy() for b in boxes]  (replace)      3,72 ms
        [BoxEntry(b.char, b.x1, ...) ...]         0,57 ms
        [b.as_state() for b in boxes]             0,19 ms   <- o de hoje
        reconstruir de tuplas (custo do undo)     0,55 ms

    O `deepcopy` fazia trabalho para um caso que não existe aqui: os campos do
    `BoxEntry` são todos imutáveis (str, int, float), então não há grafo de
    objetos a percorrer nem ciclo a memoizar. Trocar por tupla é 84x.

    **A F3.4 previa "snapshot incremental em vez de cópia integral", e a medição
    diz para não fazer isso.** Guardar só o que mudou custaria uma comparação de
    listas (0,16 ms) mais a cópia dos alterados — ou seja, 0,17 ms contra os
    0,19 ms da cópia integral. Nada, em troca de um delta com estado próprio,
    que precisa acertar inserção e remoção (dividir e excluir box) e é onde
    esse tipo de código erra. A cópia integral ficou.

    O `DocumentSession.montar_payload` chegou à mesma conclusão antes, pelo
    mesmo caminho e para o rascunho em disco. A diferença é que lá a confiança é
    arredondada para 4 casas, para o arquivo encolher; aqui não pode haver
    arredondamento nenhum — o undo tem de devolver o estado idêntico.
    """

    def __init__(self, max_history: int = 50):
        self._history: List[dict] = []
        self._index: int = -1
        self._max_history = max_history

    # ------------------------------------------------------------------

    @staticmethod
    def _guardar(boxes: Sequence[BoxEntry]) -> List[tuple]:
        return [b.as_state() for b in boxes]

    @staticmethod
    def _restaurar(estado: Sequence[tuple]) -> List[BoxEntry]:
        # Instâncias novas a cada restauração: quem chama muta a lista no
        # lugar, e devolver as mesmas apagaria o histórico por baixo.
        return [BoxEntry.from_state(t) for t in estado]

    # ------------------------------------------------------------------

    def snapshot(self, boxes: Sequence[BoxEntry], selected_index: int = -1):
        """
        Salva o estado atual. Descarta o futuro, se havia (undo seguido de
        mutação).
        """
        if self._index < len(self._history) - 1:
            self._history = self._history[:self._index + 1]

        self._history.append({
            "boxes": self._guardar(boxes),
            "selected_index": selected_index,
        })

        if len(self._history) > self._max_history:
            self._history.pop(0)
        else:
            self._index += 1

    def undo(self) -> Tuple[Optional[List[BoxEntry]], Optional[int]]:
        """(boxes, selected_index), ou (None, None) se não há o que desfazer."""
        if self._index <= 0:
            return None, None

        self._index -= 1
        estado = self._history[self._index]
        return self._restaurar(estado["boxes"]), estado["selected_index"]

    def redo(self) -> Tuple[Optional[List[BoxEntry]], Optional[int]]:
        """(boxes, selected_index), ou (None, None) se não há o que refazer."""
        if self._index >= len(self._history) - 1:
            return None, None

        self._index += 1
        estado = self._history[self._index]
        return self._restaurar(estado["boxes"]), estado["selected_index"]

    def can_undo(self) -> bool:
        return self._index > 0

    def can_redo(self) -> bool:
        return self._index < len(self._history) - 1

    def reset(self):
        """Limpa o histórico (ex.: ao abrir outra imagem)."""
        self._history = []
        self._index = -1
