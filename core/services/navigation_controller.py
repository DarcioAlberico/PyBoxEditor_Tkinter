"""Estado de navegação de um documento, sem dependência de Tkinter."""

from dataclasses import dataclass


@dataclass
class NavigationController:
    """Mantém a página atual e centraliza os limites de navegação."""

    page_count: int = 0
    current_page: int = 0

    def reset(self, page_count: int) -> int:
        self.page_count = max(0, int(page_count))
        self.current_page = 0 if self.page_count else -1
        return self.current_page

    def target(self, page: int) -> int:
        if not self.page_count:
            raise IndexError("não há páginas no documento")
        page = int(page)
        if not 0 <= page < self.page_count:
            raise IndexError(f"página fora do intervalo: {page}")
        return page

    def go_to(self, page: int) -> int:
        self.current_page = self.target(page)
        return self.current_page

    def previous(self) -> int:
        return self.go_to(self.current_page - 1)

    def next(self) -> int:
        return self.go_to(self.current_page + 1)

    @property
    def can_previous(self) -> bool:
        return self.page_count > 0 and self.current_page > 0

    @property
    def can_next(self) -> bool:
        return self.page_count > 0 and self.current_page < self.page_count - 1

