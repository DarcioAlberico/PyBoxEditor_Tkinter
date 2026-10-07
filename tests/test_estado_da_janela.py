"""
A janela principal lembra onde estava (item 9 da `docs/REVISAO_MODOS_OCR.md`).

Nada persistia: a geometria voltava ao padrão, os filtros da lista voltavam
desligados, e o Ctrl+O abria sempre na pasta corrente — só a caixa de
exportação lembrava a pasta. Agora `gravar_estado_da_janela` (ao fechar) guarda
a geometria, se estava maximizada e os filtros na chave `janela` do
`settings.json`, `restaurar_estado_da_janela` (no `appy.main`) os devolve se a
geometria ainda cabe na tela, e abrir e exportar dividem a mesma pasta.
"""

import json
from tkinter import filedialog

import pytest
from PIL import Image

from config.settings import Settings
from conftest import raiz_tk


class _App:
    def __init__(self, settings):
        self.settings = settings

    def __enter__(self):
        from tkinter import messagebox

        from ui.main_window import MainWindow
        self._caixas = messagebox.showinfo, messagebox.showerror
        messagebox.showinfo = messagebox.showerror = lambda *a, **k: None
        self.root = raiz_tk()
        if self.root is None:
            pytest.skip("sem display")
        self.win = MainWindow(self.root)
        self.win._configuracoes_ = Settings(str(self.settings))
        return self

    def __exit__(self, *a):
        from tkinter import messagebox
        messagebox.showinfo, messagebox.showerror = self._caixas
        try:
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass


def _gravado(arquivo):
    return json.loads(arquivo.read_text(encoding="utf-8"))


def test_a_geometria_e_os_filtros_voltam_da_ultima_vez(tmp_path):
    arquivo = tmp_path / "settings.json"
    with _App(arquivo) as app:
        app.win.var_so_pendentes.set(True)
        app.win.var_so_fora_dicionario.set(True)
        app.win.parent.geometry = lambda *a: "900x600+10+20"
        app.win.gravar_estado_da_janela()
    estado = _gravado(arquivo)["janela"]
    assert estado == {"filtros": {"so_pendentes": True, "so_vazios": False,
                                  "so_fora_dicionario": True},
                      "maximizada": False, "geometria": "900x600+10+20"}

    with _App(arquivo) as app:
        aplicadas = []
        app.win.parent.geometry = lambda *a: aplicadas.extend(a)
        app.win.restaurar_estado_da_janela()
        assert app.win.var_so_pendentes.get() and app.win.var_so_fora_dicionario.get()
        assert not app.win.var_so_vazios.get()
        assert aplicadas == ["900x600+10+20"]


def test_a_geometria_que_nao_cabe_mais_na_tela_nao_volta(tmp_path):
    arquivo = tmp_path / "settings.json"
    arquivo.write_text(json.dumps({"janela": {"geometria": "9000x7000+0+0"}}),
                       encoding="utf-8")
    with _App(arquivo) as app:
        aplicadas = []
        app.win.parent.geometry = lambda *a: aplicadas.extend(a)
        app.win.restaurar_estado_da_janela()
        assert aplicadas == []
        assert not app.win._geometria_que_cabe("800x600+-3000+0")   # noutro monitor
        assert not app.win._geometria_que_cabe("lixo")


def test_maximizada_guarda_a_geometria_de_antes(tmp_path):
    """O botão de restaurar tem de devolver a janela ao tamanho de antes — e
    maximizada, `geometry()` diria o tamanho da tela."""
    arquivo = tmp_path / "settings.json"
    arquivo.write_text(json.dumps({"janela": {"geometria": "1000x640+30+10"}}),
                       encoding="utf-8")
    with _App(arquivo) as app:
        app.win._maximizada = lambda: True
        app.win.parent.geometry = lambda *a: "1360x728+0+0"
        app.win.gravar_estado_da_janela()
    estado = _gravado(arquivo)["janela"]
    assert estado["maximizada"] is True and estado["geometria"] == "1000x640+30+10"


def test_abrir_comeca_na_pasta_do_ultimo_documento(tmp_path, monkeypatch):
    arquivo = tmp_path / "settings.json"
    pasta = tmp_path / "livros"
    pasta.mkdir()
    imagem = pasta / "pagina.png"
    Image.new("L", (200, 80), 255).save(imagem)
    pedidos = []

    def escolher(**opcoes):
        pedidos.append(opcoes.get("initialdir"))
        return str(imagem)

    monkeypatch.setattr(filedialog, "askopenfilename", escolher)
    with _App(arquivo) as app:
        app.win.abrir_documento()
        assert app.win.image is not None
        app.win.open_image()
    assert pedidos == [None, str(pasta)]
    # e é a mesma pasta da caixa de exportação
    assert _gravado(arquivo)["ultimo_diretorio_de_entrada"] == str(pasta)


def test_o_appy_restaura_a_janela_ao_abrir():
    """É no `appy.main` que a janela de verdade nasce; o `__init__` não
    restaura, para a janela retraída dos testes não ser maximizada pelo
    `settings.json` de quem roda a suíte."""
    import inspect

    import appy
    assert "restaurar_estado_da_janela" in inspect.getsource(appy.main)
