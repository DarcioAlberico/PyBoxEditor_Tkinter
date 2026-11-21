"""Salvar o `.box` não regrava a imagem de origem (RG-05, R-52; invariante 1 do `CONTEXT.md`).

`_write_box_pair` gravava `<destino>.png` com a imagem em memória, que `open_image` guarda
convertida para cinza; e o destino sugerido do `.box` é o nome da imagem aberta. Abrir
`pagina.png` e salvar com o nome padrão gravava `pagina.png` por cima do scan original —
o RGB a 600 dpi voltava em cinza e sem dpi —, sem pergunta, no Ctrl+S e no "Salvar todas".
O "mesmo arquivo" é o do sistema de arquivos: aberto `Pagina.PNG`, o par `Pagina.png` é o
mesmo arquivo no Windows.
"""

import os
import tempfile
from tkinter import filedialog

from PIL import Image

from core.box_model import BoxEntry
from tests.test_trabalho_fora_da_interface import _App


def _scan(caminho):
    Image.new("RGB", (200, 80), (250, 240, 220)).save(caminho, dpi=(600, 600))
    with open(caminho, "rb") as f:
        return f.read()


def _abrir_com_um_box(win, caminho):
    win.open_image(caminho)
    win.boxes.append(BoxEntry("a", 10, 10, 20, 30))
    win._commit_change()


def test_o_ctrl_s_com_o_nome_sugerido_nao_toca_no_scan(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        imagem = os.path.join(tmp, "pagina.png")
        original = _scan(imagem)
        _abrir_com_um_box(app.win, imagem)
        pasta, nome = app.win._destino_sugerido(".box", "boxes")
        monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **k: os.path.join(pasta, nome))
        app.win.save_box_file()
        app.aguardar()
        with open(imagem, "rb") as f:
            assert f.read() == original, "o scan original foi regravado"
        assert os.path.exists(os.path.join(tmp, "pagina.box"))
        assert "mantida" in app.caixas[-1][2]


def test_salvar_todas_numa_sessao_de_imagem_nao_toca_no_scan():
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        imagem = os.path.join(tmp, "pagina.png")
        original = _scan(imagem)
        _abrir_com_um_box(app.win, imagem)
        app.win.save_all_pages()
        app.aguardar()
        with open(imagem, "rb") as f:
            assert f.read() == original
        assert os.path.exists(os.path.join(tmp, "pagina.box"))


def test_a_origem_com_outra_caixa_no_nome_e_o_mesmo_arquivo(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        imagem = os.path.join(tmp, "Pagina.PNG")
        original = _scan(imagem)
        _abrir_com_um_box(app.win, imagem)
        monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **k: os.path.join(tmp, "Pagina.box"))
        app.win.save_box_file()
        app.aguardar()
        with open(imagem, "rb") as f:
            assert f.read() == original


def test_com_outro_nome_o_par_sai_inteiro(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        imagem = os.path.join(tmp, "pagina.png")
        _scan(imagem)
        _abrir_com_um_box(app.win, imagem)
        monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **k: os.path.join(tmp, "outro.box"))
        app.win.save_box_file()
        app.aguardar()
        assert os.path.exists(os.path.join(tmp, "outro.box"))
        assert Image.open(os.path.join(tmp, "outro.png")).size == (200, 80)
