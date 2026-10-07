import tkinter as tk

import pytest

from core import nags
from core.chess_symbols import (CHESS_ANNOTATION_CHARACTERS,
                                VANTAGEM_LIGEIRA_BRANCAS,
                                VANTAGEM_LIGEIRA_PRETAS)
from ui.dialogo_rotulagem import DialogoRotulagem, _simbolos_da_paleta
from conftest import raiz_tk


def test_paleta_contem_todos_os_simbolos_da_tabela_nag():
    paleta = set(_simbolos_da_paleta())
    assert {nag.simbolo for nag in nags.TABELA if nag.simbolo} <= paleta


def test_paleta_contem_catalogo_de_caracteres_de_xadrez():
    assert CHESS_ANNOTATION_CHARACTERS <= set(_simbolos_da_paleta())


def test_paleta_contem_o_par_de_vantagem_ligeira():
    paleta = _simbolos_da_paleta()
    assert VANTAGEM_LIGEIRA_BRANCAS in paleta
    assert VANTAGEM_LIGEIRA_PRETAS in paleta


def test_paleta_nao_exibe_o_dois_sobrescrito():
    assert "²" not in _simbolos_da_paleta()


def test_paleta_de_rotulagem_mantem_todos_os_botoes_na_largura_e_rola_verticalmente():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    raiz.deiconify()
    raiz.geometry("1200x800")
    app = type("Aplicacao", (), {
        "parent": raiz,
        "boxes": [],
        "image": None,
        "current_pdf_page": 0,
        "pdf_service": type("PDF", (), {"is_loaded": lambda self: False})(),
    })()
    try:
        dialogo = DialogoRotulagem(app)
        dialogo.update()
        dialogo.update_idletasks()
        widgets = []

        def visitar(widget):
            widgets.append(widget)
            for filho in widget.winfo_children():
                visitar(filho)

        visitar(dialogo)
        simbolos = set(_simbolos_da_paleta())
        botoes = [w for w in widgets if isinstance(w, tk.Button) and w.cget("text") in simbolos]
        canvases = [w for w in widgets if isinstance(w, tk.Canvas)]
        assert len(botoes) == len(simbolos)
        assert len(canvases) == 1
        assert canvases[0].yview()[1] < 1.0, "a paleta precisa ter rolagem vertical"
        assert canvases[0].xview() == (0.0, 1.0), "nenhum símbolo deve ficar numa faixa horizontal escondida"
    finally:
        if "dialogo" in locals() and dialogo.winfo_exists():
            dialogo.destroy()
        raiz.destroy()
