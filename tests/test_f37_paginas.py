"""
Testes da F3.7 — persistência de boxes por página e aviso de trabalho não salvo.

O defeito original: `_load_pdf_page` fazia `self.boxes = []` sem aviso nenhum.
Virar a página do PDF apagava tudo que havia sido digitado, em silêncio.

Rodar sem pytest:      python tests/test_f37_paginas.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
import tkinter as tk
from tkinter import messagebox
from PIL import Image

from core.box_model import BoxEntry
from core.services.document_service import DocumentSession


# ----------------------------------------------------------------------
# Apoio
# ----------------------------------------------------------------------

def _pdf_de_teste(caminho, paginas=3):
    doc = fitz.open()
    for i in range(paginas):
        pg = doc.new_page()
        pg.insert_text((60, 80), f"Pagina {i + 1} ABC", fontsize=18)
    doc.save(caminho)
    doc.close()
    return caminho


class _App:
    """MainWindow com os diálogos neutralizados (bloqueiam em teste)."""

    def __init__(self, descartar=True):
        from ui.main_window import MainWindow
        self.perguntas = []
        self._descartar = descartar

        self._info, self._erro, self._sim = (
            messagebox.showinfo, messagebox.showerror, messagebox.askyesno)
        messagebox.showinfo = lambda t, m, **k: None
        messagebox.showerror = lambda t, m, **k: None
        messagebox.askyesno = self._askyesno

        self.root = tk.Tk()
        self.root.withdraw()
        self.win = MainWindow(self.root)

    def _askyesno(self, titulo, msg, **k):
        self.perguntas.append((titulo, msg))
        return self._descartar

    def __enter__(self):
        return self

    def __exit__(self, *a):
        messagebox.showinfo, messagebox.showerror, messagebox.askyesno = (
            self._info, self._erro, self._sim)
        try:
            self.root.destroy()
        except tk.TclError:
            pass


# ----------------------------------------------------------------------
# DocumentSession — unidade
# ----------------------------------------------------------------------

def test_sessao_guarda_boxes_por_pagina():
    s = DocumentSession("/tmp/livro.pdf", num_pages=10, is_pdf=True)

    s.store(0, [BoxEntry("a", 0, 0, 5, 5)])
    s.store(4, [BoxEntry("b", 0, 0, 5, 5), BoxEntry("c", 6, 0, 9, 5)])

    assert [b.char for b in s.boxes_for(0)] == ["a"]
    assert [b.char for b in s.boxes_for(4)] == ["b", "c"]
    assert s.boxes_for(7) == []              # não visitada
    assert s.pages_with_boxes() == [0, 4]
    assert s.total_boxes() == 3


def test_sessao_rastreia_paginas_sujas():
    s = DocumentSession("/tmp/livro.pdf", num_pages=5, is_pdf=True)
    assert not s.is_dirty()

    s.store(1, [BoxEntry("a", 0, 0, 5, 5)])
    s.mark_dirty(1)
    assert s.is_dirty() and s.dirty_pages() == [1]

    s.store(2, [BoxEntry("b", 0, 0, 5, 5)])
    s.mark_dirty(2)
    assert s.dirty_pages() == [1, 2]

    s.mark_saved(1)
    assert s.dirty_pages() == [2]

    s.mark_saved()
    assert not s.is_dirty()


def test_page_stem():
    pdf = DocumentSession(os.path.join("dir", "livro.pdf"), num_pages=200, is_pdf=True)
    assert pdf.page_stem(0).endswith("livro_pg001")
    assert pdf.page_stem(10).endswith("livro_pg011")

    img = DocumentSession(os.path.join("dir", "foto.png"), is_pdf=False)
    assert img.page_stem(0).endswith("foto")


# ----------------------------------------------------------------------
# O bug original: virar a página apagava tudo
# ----------------------------------------------------------------------

def test_virar_pagina_preserva_boxes():
    """Era: `self.boxes = []` em _load_pdf_page descartava o trabalho."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=3)

        with _App() as app:
            w = app.win
            w.open_pdf(pdf)
            assert w.current_pdf_page == 0

            w.boxes.append(BoxEntry("X", 10, 10, 20, 20))
            w._commit_change()

            w.next_page()                                   # <- apagava aqui
            assert w.current_pdf_page == 1
            assert w.boxes == [], "página nova deve começar vazia"

            w.boxes.append(BoxEntry("Y", 30, 30, 40, 40))
            w._commit_change()

            w.prev_page()
            assert w.current_pdf_page == 0
            assert [b.char for b in w.boxes] == ["X"], "o trabalho da página 1 sumiu"

            w.next_page()
            assert [b.char for b in w.boxes] == ["Y"], "o trabalho da página 2 sumiu"


def test_navegacao_arquiva_na_pagina_certa():
    """prev_page/next_page não podem mexer em current_pdf_page antes de
    _load_pdf_page — senão o trabalho é arquivado sob o índice errado."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=3)

        with _App() as app:
            w = app.win
            w.open_pdf(pdf)

            for esperado in ("P0", "P1", "P2"):
                w.boxes.append(BoxEntry(esperado, 1, 1, 9, 9))
                w._commit_change()
                if esperado != "P2":
                    w.next_page()

            for pagina, esperado in enumerate(("P0", "P1", "P2")):
                assert [b.char for b in w.session.boxes_for(pagina)] == [esperado], \
                    f"página {pagina} guardou o conteúdo errado"


# ----------------------------------------------------------------------
# Aviso de trabalho não salvo
# ----------------------------------------------------------------------

def test_titulo_marca_nao_salvo():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=2)

        with _App() as app:
            w = app.win
            w.open_pdf(pdf)
            assert "*" not in w.parent.title()

            w.boxes.append(BoxEntry("A", 1, 1, 9, 9))
            w._commit_change()
            assert w.parent.title().endswith("*"), "faltou o marcador de não salvo"
            assert "livro.pdf" in w.parent.title()


def test_avisa_antes_de_descartar():
    """Abrir outro documento com trabalho pendente precisa perguntar."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=2)
        img = os.path.join(tmp, "outra.png")
        Image.new("L", (50, 50), color=255).save(img)

        with _App(descartar=True) as app:
            w = app.win
            w.open_pdf(pdf)
            w.boxes.append(BoxEntry("A", 1, 1, 9, 9))
            w._commit_change()

            w.open_image(img)
            assert len(app.perguntas) == 1, "abriu outro arquivo sem avisar"
            assert "não salvas" in app.perguntas[0][1]


def test_recusar_descarte_cancela_abertura():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=2)
        img = os.path.join(tmp, "outra.png")
        Image.new("L", (50, 50), color=255).save(img)

        with _App(descartar=False) as app:
            w = app.win
            w.open_pdf(pdf)
            w.boxes.append(BoxEntry("A", 1, 1, 9, 9))
            w._commit_change()

            w.open_image(img)
            assert w.session.is_pdf, "dizer 'não' deveria manter o PDF aberto"
            assert [b.char for b in w.boxes] == ["A"], "o trabalho foi perdido"


# ----------------------------------------------------------------------
# Salvar todas as páginas
# ----------------------------------------------------------------------

def test_salvar_todas_as_paginas():
    """Contrapartida da persistência: o trabalho acumulado precisa ter como sair."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=3)

        with _App() as app:
            w = app.win
            w.open_pdf(pdf)

            w.boxes.append(BoxEntry("A", 10, 10, 20, 20))
            w._commit_change()
            w.next_page()
            w.next_page()                                   # pula a página 2
            w.boxes.append(BoxEntry("C", 10, 10, 20, 20))
            w._commit_change()

            assert w.session.dirty_pages() == [0, 2]
            w.save_all_pages()

            assert os.path.exists(os.path.join(tmp, "livro_pg001.box"))
            assert os.path.exists(os.path.join(tmp, "livro_pg001.png"))
            assert os.path.exists(os.path.join(tmp, "livro_pg003.box"))
            assert not os.path.exists(os.path.join(tmp, "livro_pg002.box")), \
                "página sem boxes não deve gerar arquivo"

            assert not w.session.is_dirty(), "salvar deveria limpar o estado sujo"
            assert "*" not in w.parent.title()

            conteudo = open(os.path.join(tmp, "livro_pg003.box"), encoding="utf-8").read()
            assert conteudo.startswith("C "), f"conteúdo inesperado: {conteudo!r}"


def test_salvar_pagina_atual_nao_limpa_as_outras():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=2)

        with _App() as app:
            w = app.win
            w.open_pdf(pdf)
            w.boxes.append(BoxEntry("A", 10, 10, 20, 20))
            w._commit_change()
            w.next_page()
            w.boxes.append(BoxEntry("B", 10, 10, 20, 20))
            w._commit_change()

            w._save_box_to_path(os.path.join(tmp, "so_a_pagina_2.box"))

            assert w.session.dirty_pages() == [0], \
                "salvar uma página não pode marcar as outras como salvas"
            assert w.parent.title().endswith("*")


# ----------------------------------------------------------------------
# Execução direta
# ----------------------------------------------------------------------

def _main():
    testes = [(n, o) for n, o in sorted(globals().items())
              if n.startswith("test_") and callable(o)]
    falhas = []
    for nome, fn in testes:
        try:
            fn()
            print(f"  PASS  {nome}")
        except Exception as e:
            falhas.append(nome)
            print(f"  FALHA {nome}\n          {type(e).__name__}: {e}")
    print(f"\n{len(testes) - len(falhas)}/{len(testes)} testes passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(_main())
