"""
Testes da F3.3 — filtros e navegação por pendências.

Uma página de livro tem ~2.000 caracteres. Sem filtro, revisar é reler tudo.
Com filtro, é conferir só os duvidosos.

O risco desta fase: a lista deixa de mapear 1:1 com `self.boxes`. Se o
mapeamento linha→índice falhar, clicar numa linha seleciona o box errado — e
o usuário edita o caractere errado sem perceber.

Rodar sem pytest:      python tests/test_f33_filtros.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from tkinter import messagebox
from PIL import Image

from core.box_model import BoxEntry


class _App:
    def __enter__(self):
        from ui.main_window import MainWindow
        self._info, self._erro = messagebox.showinfo, messagebox.showerror
        messagebox.showinfo = lambda *a, **k: None
        messagebox.showerror = lambda *a, **k: None
        self.root = tk.Tk()
        self.root.withdraw()
        self.win = MainWindow(self.root)
        self.win.image = Image.new("L", (400, 100), color=255)
        return self

    def __exit__(self, *a):
        messagebox.showinfo, messagebox.showerror = self._info, self._erro
        try:
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass


def _pagina(win):
    """Seis boxes cobrindo todos os estados relevantes."""
    win.boxes = [
        BoxEntry("a", 0, 0, 9, 9, confidence=0.99, source="neural"),    # 0 ok
        BoxEntry("b", 10, 0, 19, 9, confidence=0.40, source="easyocr"),  # 1 pendente
        BoxEntry("", 20, 0, 29, 9),                                      # 2 vazio
        BoxEntry("c", 30, 0, 39, 9, confidence=0.95, source="neural"),   # 3 ok
        BoxEntry("a", 40, 0, 49, 9, confidence=0.55, source="learner"),  # 4 pendente
        BoxEntry("d", 50, 0, 59, 9),                                     # 5 sem info
    ]
    win.selected_index = 0
    win.update_sidebar()


# ----------------------------------------------------------------------
# Filtragem
# ----------------------------------------------------------------------

def test_sem_filtro_mostra_tudo():
    with _App() as app:
        w = app.win
        _pagina(w)
        assert w.boxes_visiveis() == [0, 1, 2, 3, 4, 5]
        assert w.listbox.size() == 6
        assert "mostrando todos os 6" in w.lbl_filtro.cget("text")


def test_filtro_so_pendentes():
    with _App() as app:
        w = app.win
        _pagina(w)
        w.var_so_pendentes.set(True)
        w.on_boxes_changed_view()

        # 1 e 4 têm confiança baixa; 2 está vazio. O 5 é "sem info", que não
        # é pendência (ver F3.2).
        assert w.boxes_visiveis() == [1, 2, 4]
        assert w.listbox.size() == 3
        assert "mostrando 3 de 6" in w.lbl_filtro.cget("text")


def test_filtro_so_vazios():
    with _App() as app:
        w = app.win
        _pagina(w)
        w.var_so_vazios.set(True)
        w.on_boxes_changed_view()
        assert w.boxes_visiveis() == [2]


def test_busca_por_caractere_e_conjunto():
    """Digitar 'a' acha os 'a'; digitar 'ac' acha 'a' e 'c'."""
    with _App() as app:
        w = app.win
        _pagina(w)

        w.var_busca.set("a")
        assert w.boxes_visiveis() == [0, 4]

        w.var_busca.set("ac")
        assert w.boxes_visiveis() == [0, 3, 4]

        w.var_busca.set("z")
        assert w.boxes_visiveis() == []


def test_busca_diferencia_maiuscula():
    """O OCR distingue 'A' de 'a' (upper_A / lower_a); a busca também."""
    with _App() as app:
        w = app.win
        w.boxes = [
            BoxEntry("A", 0, 0, 9, 9, confidence=0.9, source="neural"),
            BoxEntry("a", 10, 0, 19, 9, confidence=0.9, source="neural"),
        ]
        w.update_sidebar()

        w.var_busca.set("A")
        assert w.boxes_visiveis() == [0]
        w.var_busca.set("a")
        assert w.boxes_visiveis() == [1]


def test_filtro_por_origem():
    with _App() as app:
        w = app.win
        _pagina(w)
        w.var_origem.set("neural")
        w.on_boxes_changed_view()
        assert w.boxes_visiveis() == [0, 3]

        w.var_origem.set(w.ORIGEM_VAZIA)
        w.on_boxes_changed_view()
        assert w.boxes_visiveis() == [2, 5], "boxes sem origem definida"


def test_filtros_combinam():
    with _App() as app:
        w = app.win
        _pagina(w)
        w.var_so_pendentes.set(True)
        w.var_busca.set("a")
        w.on_boxes_changed_view()
        # dos pendentes (1, 2, 4), só o 4 tem caractere 'a'
        assert w.boxes_visiveis() == [4]


def test_limpar_filtros():
    with _App() as app:
        w = app.win
        _pagina(w)
        w.var_so_pendentes.set(True)
        w.var_busca.set("a")
        w.var_origem.set("neural")
        w.on_boxes_changed_view()

        w.limpar_filtros()
        assert w.boxes_visiveis() == [0, 1, 2, 3, 4, 5]
        assert w.var_busca.get() == ""


def test_combo_de_origem_reflete_a_pagina():
    with _App() as app:
        w = app.win
        _pagina(w)
        valores = list(w.combo_origem["values"])
        assert valores[0] == w.ORIGEM_TODAS
        assert set(valores[1:]) == {"neural", "easyocr", "learner", w.ORIGEM_VAZIA}


# ----------------------------------------------------------------------
# O risco desta fase: linha da lista != índice do box
# ----------------------------------------------------------------------

def test_clicar_na_lista_filtrada_seleciona_o_box_certo():
    """Se o mapeamento falhar, o usuário edita o caractere errado sem notar."""
    with _App() as app:
        w = app.win
        _pagina(w)
        w.var_so_pendentes.set(True)
        w.on_boxes_changed_view()
        assert w._visiveis == [1, 2, 4]

        # clicar na terceira linha da lista = box 4, não box 2
        w.listbox.selection_clear(0, "end")
        w.listbox.selection_set(2)
        w.on_sidebar_select(None)

        assert w.selected_index == 4, "a linha da lista foi confundida com o índice"
        assert w.boxes[w.selected_index].char == "a"


def test_selecao_sincroniza_com_a_linha_certa():
    with _App() as app:
        w = app.win
        _pagina(w)
        w.var_so_pendentes.set(True)
        w.on_boxes_changed_view()

        w.select_box(4)
        assert w.linha_do_box(4) == 2
        assert w.listbox.curselection() == (2,)


def test_box_fora_do_filtro_nao_tem_linha():
    with _App() as app:
        w = app.win
        _pagina(w)
        w.var_so_vazios.set(True)
        w.on_boxes_changed_view()
        assert w.linha_do_box(0) is None
        assert w.linha_do_box(2) == 0


# ----------------------------------------------------------------------
# Navegação
# ----------------------------------------------------------------------

def test_setas_andam_dentro_do_filtro():
    with _App() as app:
        w = app.win
        _pagina(w)
        w.var_so_pendentes.set(True)
        w.on_boxes_changed_view()
        w.select_box(1)

        w._on_key_down(None)
        assert w.selected_index == 2, "deveria pular do 1 para o 2 (visíveis)"
        w._on_key_down(None)
        assert w.selected_index == 4, "deveria pular o 3, que está filtrado"
        w._on_key_down(None)
        assert w.selected_index == 4, "não passa do fim da lista"

        w._on_key_up(None)
        assert w.selected_index == 2


def test_f3_pula_para_o_proximo_pendente():
    """O que troca 'reler 2.000' por 'conferir os duvidosos'."""
    with _App() as app:
        w = app.win
        _pagina(w)
        w.select_box(0)

        w.proximo_pendente(1)
        assert w.selected_index == 1
        w.proximo_pendente(1)
        assert w.selected_index == 2
        w.proximo_pendente(1)
        assert w.selected_index == 4

        # dá a volta ao chegar na ponta
        w.proximo_pendente(1)
        assert w.selected_index == 1


def test_shift_f3_volta():
    with _App() as app:
        w = app.win
        _pagina(w)
        w.select_box(4)
        w.proximo_pendente(-1)
        assert w.selected_index == 2
        w.proximo_pendente(-1)
        assert w.selected_index == 1


def test_f3_sem_pendencias_avisa():
    with _App() as app:
        w = app.win
        w.boxes = [BoxEntry("a", 0, 0, 9, 9, confidence=1.0, source="manual")]
        w.update_sidebar()
        w.select_box(0)

        w.proximo_pendente(1)
        assert "Nada pendente" in w.status.lbl.cget("text")


def test_corrigir_com_filtro_ativo_segue_para_o_proximo():
    """
    Com "só pendentes", corrigir um box o tira da lista. A lista encolhe, e a
    mesma posição já é o próximo pendente — o cursor não pode pular um.
    """
    with _App() as app:
        w = app.win
        _pagina(w)
        w.var_so_pendentes.set(True)
        w.on_boxes_changed_view()
        assert w._visiveis == [1, 2, 4]

        w.select_box(1)
        w.char_entry.delete(0, "end")
        w.char_entry.insert(0, "B")
        w.apply_char_and_next()

        assert w.boxes[1].char == "B"
        assert w._visiveis == [2, 4], "o box corrigido devia sair do filtro"
        assert w.selected_index == 2, "pulou o próximo pendente"


def test_corrigir_sem_filtro_segue_em_ordem():
    with _App() as app:
        w = app.win
        _pagina(w)
        w.select_box(1)
        w.char_entry.delete(0, "end")
        w.char_entry.insert(0, "B")
        w.apply_char_and_next()

        assert w.selected_index == 2


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
