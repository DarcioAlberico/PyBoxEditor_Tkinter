from types import SimpleNamespace

import pytest
from PIL import Image

from conftest import raiz_tk
from ui.dialogo_revisao_linhas import DialogoRevisaoLinhas
from ui.dialogo_rotulagem import _simbolos_da_paleta


def test_revisao_do_dataset_tem_paleta_e_insere_simbolo_no_texto(tmp_path):
    pasta = tmp_path / "training_data_linhas"
    imagens = pasta / "images"
    imagens.mkdir(parents=True)
    Image.new("L", (120, 32), 255).save(imagens / "linha.png")
    (pasta / "rec_gt.txt").write_text("images/linha.png\t1.e4\n", encoding="utf-8")

    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    raiz.deiconify()
    raiz.geometry("1200x800")
    dialogo = None
    try:
        dialogo = DialogoRevisaoLinhas(SimpleNamespace(parent=raiz), pasta=pasta)
        dialogo.update()
        dialogo.update_idletasks()
        simbolos = set(_simbolos_da_paleta())
        widgets = []

        def visitar(widget):
            widgets.append(widget)
            for filho in widget.winfo_children():
                visitar(filho)

        visitar(dialogo)
        botoes = [w for w in widgets if w.winfo_class() == "Button" and w.cget("text") in simbolos]
        assert len(botoes) == len(simbolos)
        botao = next(w for w in botoes if w.cget("text") == "♕")
        dialogo.texto.focus_set()
        dialogo.texto.mark_set("insert", "end-1c")
        botao.invoke()
        assert dialogo.texto.get("1.0", "end-1c").endswith("♕")
    finally:
        if dialogo is not None and dialogo.winfo_exists():
            dialogo.destroy()
        raiz.destroy()
