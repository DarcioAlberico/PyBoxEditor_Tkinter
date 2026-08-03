import os
from typing import Dict, List, Optional, Set

from core.box_model import BoxEntry


class DocumentSession:
    """
    Um documento aberto — imagem única ou PDF de N páginas.

    Existe para resolver uma perda silenciosa de trabalho: antes, virar a página
    do PDF fazia `self.boxes = []` sem aviso, e tudo que havia sido digitado na
    página anterior simplesmente sumia.

    A sessão guarda os boxes de todas as páginas visitadas e registra quais têm
    alterações ainda não gravadas em disco.

    Nota sobre referências: `boxes_for()` devolve a própria lista guardada, e
    `store()` guarda a lista recebida sem copiar. Isso é proposital — a
    MainWindow muta `self.boxes` no lugar o tempo todo, e copiar a cada tecla
    numa página de 2.000 caracteres seria caro. O contrato é que todo ponto que
    reatribui `self.boxes` chame `store()` em seguida.
    """

    def __init__(self, path: str, num_pages: int = 1, is_pdf: bool = False):
        self.path = path
        self.num_pages = max(1, num_pages)
        self.is_pdf = is_pdf

        self._pages: Dict[int, List[BoxEntry]] = {}
        self._dirty: Set[int] = set()

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    def boxes_for(self, page: int) -> List[BoxEntry]:
        """Boxes da página (lista vazia própria, se ainda não visitada)."""
        return self._pages.setdefault(page, [])

    def has_boxes(self, page: int) -> bool:
        return bool(self._pages.get(page))

    def pages_with_boxes(self) -> List[int]:
        return sorted(p for p, boxes in self._pages.items() if boxes)

    def dirty_pages(self) -> List[int]:
        """Páginas com alterações não salvas (e que ainda têm algo a salvar)."""
        return sorted(p for p in self._dirty if self._pages.get(p))

    def is_dirty(self) -> bool:
        return bool(self.dirty_pages())

    def total_boxes(self) -> int:
        return sum(len(b) for b in self._pages.values())

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------

    def store(self, page: int, boxes: List[BoxEntry]) -> None:
        """Associa a lista de boxes à página. Não mexe no estado 'sujo'."""
        self._pages[page] = boxes

    def mark_dirty(self, page: int) -> None:
        self._dirty.add(page)

    def mark_saved(self, page: Optional[int] = None) -> None:
        """Marca uma página como gravada — ou todas, se page for None."""
        if page is None:
            self._dirty.clear()
        else:
            self._dirty.discard(page)

    # ------------------------------------------------------------------
    # Nomes de arquivo
    # ------------------------------------------------------------------

    def page_stem(self, page: int) -> str:
        """
        Caminho-base (sem extensão) dos arquivos daquela página.

        Um .box/.png por página, seguindo a convenção que o projeto já usa em
        Box/ (ex.: 'AAGAARD - Practical Chess Defence_pg11.box'). Manter um
        arquivo por página preserva a compatibilidade com o formato .box do
        Tesseract, que espera uma imagem por arquivo de boxes.
        """
        base = os.path.splitext(self.path)[0]
        if not self.is_pdf:
            return base
        return f"{base}_pg{page + 1:03d}"
