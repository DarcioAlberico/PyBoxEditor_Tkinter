"""Coordenação do documento aberto, independente da camada visual."""

from __future__ import annotations

from typing import Callable, List, Optional

from core.box_model import BoxEntry
from core.services.document_service import DocumentSession, _GravadorAssincrono
from core.services.history_service import HistoryManager


class DocumentController:
    """Fachada do estado mutável de uma sessão de edição.

    A janela ainda pode renderizar e editar a lista retornada por
    :attr:`boxes`, mas a posse da sessão, do histórico e da página atual fica
    concentrada aqui. Isso reduz o acoplamento dos handlers de Tkinter e torna
    undo/redo e troca de página testáveis sem criar uma janela.
    """

    def __init__(
        self,
        autosave_writer: Optional[_GravadorAssincrono] = None,
        max_history: int = 50,
        on_autosave: Optional[Callable[[], None]] = None,
    ):
        self.session: Optional[DocumentSession] = None
        self.page = 0
        self.boxes: List[BoxEntry] = []
        self.selected_index = -1
        self.history = HistoryManager(max_history=max_history)
        self.autosave_writer = autosave_writer
        self.on_autosave = on_autosave

    def open(self, path: str, num_pages: int = 1, is_pdf: bool = False, dpi: int = 0):
        self.session = DocumentSession(path, num_pages=num_pages, is_pdf=is_pdf, dpi=dpi)
        self.page = 0
        self.boxes = self.session.boxes_for(0)
        self.selected_index = -1
        self.history.reset()
        return self.session

    def close(self):
        self.session = None
        self.page = 0
        self.boxes = []
        self.selected_index = -1
        self.history.reset()

    def load_page(self, page: int) -> List[BoxEntry]:
        if self.session is None:
            raise RuntimeError("não há documento aberto")
        if not 0 <= page < self.session.num_pages:
            raise IndexError(f"página fora do intervalo: {page}")
        self.store_current()
        self.page = page
        self.boxes = self.session.boxes_for(page)
        self.selected_index = -1
        self.history.reset()
        return self.boxes

    def store_current(self):
        if self.session is not None:
            self.session.store(self.page, self.boxes)

    def autosave(self):
        """Agenda o snapshot da sessão no gravador configurado."""
        if self.session is None or self.autosave_writer is None:
            return None
        return self.session.autosave(self.autosave_writer)

    def commit(self):
        """Registra uma mutação e agenda autosave quando necessário."""
        self.history.snapshot(self.boxes, self.selected_index)
        if self.session is None:
            return
        self.session.store(self.page, self.boxes)
        self.session.mark_dirty(self.page)
        if self.on_autosave is not None:
            self.on_autosave()

    def undo(self) -> bool:
        boxes, selected = self.history.undo()
        if boxes is None:
            return False
        self.boxes = boxes
        self.selected_index = selected if selected is not None else -1
        self.store_current()
        return True

    def redo(self) -> bool:
        boxes, selected = self.history.redo()
        if boxes is None:
            return False
        self.boxes = boxes
        self.selected_index = selected if selected is not None else -1
        self.store_current()
        return True

    @property
    def can_undo(self) -> bool:
        return self.history.can_undo()

    @property
    def can_redo(self) -> bool:
        return self.history.can_redo()
