"""
O menu Exibir e o canvas que rola (item 9 da `docs/REVISAO_MODOS_OCR.md`).

O canvas abria em 100% no canto de cima — um quarto de uma página de livro a
300 dpi — e a roda dava zoom, então não havia como descer a página sem arrastar
com o botão direito. Agora o documento abre ajustado à janela, a roda rola
(Shift+roda para o lado), o zoom é Ctrl+roda no cursor ou Ctrl+= / Ctrl+-, e
Ctrl+0 / Ctrl+1 ajustam e voltam a 100%. As teclas soltas `+ − 0 F` da revisão
ficaram com Ctrl: no modo digitação toda tecla imprimível vai para o box.

Os testes de canvas usam o controlador falso da F4.3; os da janela, a janela de
verdade, retraída.
"""

import os
import tempfile
from types import SimpleNamespace

import pytest
from PIL import Image

from conftest import raiz_tk
from core.box_model import BoxEntry

#: Uma página de livro a 300 dpi (A4).
PAGINA = (2480, 3508)


class _Controlador:
    def __init__(self, largura, altura, boxes=()):
        self.image = Image.new("L", (largura, altura), 255)
        self.boxes = list(boxes)
        self.selected_index = -1
        self.redesenhos = 0

    def update_canvas(self):
        self.redesenhos += 1

    def boxes_suspeitos(self):
        return set()


def _canvas(largura=400, altura=300, pagina=PAGINA, boxes=()):
    """O canvas com a view fixada em `largura`×`altura`: a janela de teste é
    retraída, e retraída ela não tem tamanho — `viewport()` cairia no padrão
    de 800×600, e o teste mediria outra coisa."""
    from ui.canvas_view import CanvasView

    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    controlador = _Controlador(*pagina, boxes=boxes)
    canvas = CanvasView(raiz, controlador)
    canvas.pack()
    canvas.tamanho_da_view = [largura, altura]
    canvas.viewport = lambda: tuple(canvas.tamanho_da_view)
    return raiz, canvas, controlador


def _roda(canvas, cliques, x=200, y=150):
    """O evento de um clique da roda como cada sistema o entrega."""
    if canvas.tk.call("tk", "windowingsystem") == "x11":
        return SimpleNamespace(num=4 if cliques > 0 else 5, delta=0, x=x, y=y)
    return SimpleNamespace(num=None, delta=120 * cliques, x=x, y=y)


def test_ajustar_a_janela_mostra_a_pagina_inteira_e_centrada():
    raiz, canvas, _ = _canvas()
    try:
        canvas.ajustar_a_janela()
        largura, altura = PAGINA[0] * canvas.zoom, PAGINA[1] * canvas.zoom
        assert largura <= 400 and altura <= 300
        assert altura > 0.95 * 300          # ocupa a janela, com a folga só
        assert canvas.offset_x == pytest.approx((400 - largura) / 2)
        assert canvas.ajustado is True
    finally:
        raiz.destroy()


def test_a_roda_rola_e_nao_da_zoom():
    raiz, canvas, _ = _canvas()
    try:
        canvas.tamanho_real()
        canvas.offset_x = canvas.offset_y = 0.0
        canvas.on_wheel(_roda(canvas, -1))             # roda para baixo: desce
        assert canvas.zoom == 1.0
        assert canvas.offset_y == pytest.approx(-0.1 * 300)
        canvas.on_wheel_shift(_roda(canvas, -1))       # Shift: para o lado
        assert canvas.offset_x == pytest.approx(-0.1 * 400)
    finally:
        raiz.destroy()


def test_ctrl_roda_da_zoom_com_o_ponto_do_cursor_parado():
    raiz, canvas, _ = _canvas()
    try:
        canvas.tamanho_real()
        antes = canvas.canvas_to_img(120, 80)
        assert canvas.on_wheel_ctrl(_roda(canvas, 1, x=120, y=80)) == "break"
        assert canvas.zoom == pytest.approx(canvas.PASSO_DE_ZOOM)
        assert canvas.canvas_to_img(120, 80) == pytest.approx(antes)
        assert canvas.ajustado is False
    finally:
        raiz.destroy()


def test_rolar_nao_tira_a_pagina_da_tela():
    raiz, canvas, _ = _canvas()
    try:
        canvas.tamanho_real()
        for _ in range(200):
            canvas.rolar(dy=-1.0)                      # para cima, muito
        assert canvas.offset_y == canvas.MARGEM_VISIVEL
        for _ in range(200):
            canvas.rolar(dy=1.0)                       # para baixo, muito
        assert canvas.offset_y == 300 - PAGINA[1] - canvas.MARGEM_VISIVEL
    finally:
        raiz.destroy()


def test_na_pagina_ajustada_rolar_nao_a_tira_do_centro():
    raiz, canvas, controlador = _canvas()
    try:
        canvas.ajustar_a_janela()
        posicao, redesenhos = (canvas.offset_x, canvas.offset_y), controlador.redesenhos
        canvas.on_wheel(_roda(canvas, -3))
        assert (canvas.offset_x, canvas.offset_y) == posicao
        assert controlador.redesenhos == redesenhos    # nada mudou, nada redesenha
    finally:
        raiz.destroy()


def test_o_modo_ajustado_acompanha_a_janela_e_sai_com_o_zoom():
    raiz, canvas, _ = _canvas()
    try:
        canvas.ajustar_a_janela()
        pequeno = canvas.zoom
        canvas.tamanho_da_view = [800, 600]            # a janela cresceu
        canvas._ao_redimensionar()
        raiz.update()
        assert canvas.zoom == pytest.approx(2 * pequeno)

        canvas.aproximar(1)
        assert canvas.ajustado is False
        zoom = canvas.zoom
        canvas._ao_redimensionar()
        raiz.update()
        assert canvas.zoom == zoom                     # quem deu zoom escolheu
    finally:
        raiz.destroy()


def test_tamanho_real_e_o_zoom_tem_limites():
    raiz, canvas, _ = _canvas()
    try:
        canvas.tamanho_real()
        assert canvas.zoom == 1.0
        canvas.aproximar(-500)
        assert canvas.zoom == canvas.ZOOM_MINIMO
        canvas.aproximar(500)
        assert canvas.zoom == canvas.ZOOM_MAXIMO
    finally:
        raiz.destroy()


def test_selecionar_na_pagina_ajustada_nao_rola():
    """Com a página inteira à vista, `garantir_visivel` não tem o que fazer —
    e a margem dela, perto da borda, tiraria a página do centro."""
    raiz, canvas, controlador = _canvas(boxes=[BoxEntry("a", 2, 2, 30, 40)])
    try:
        canvas.ajustar_a_janela()
        posicao = (canvas.offset_x, canvas.offset_y)
        canvas.garantir_visivel(0)
        assert (canvas.offset_x, canvas.offset_y) == posicao
    finally:
        raiz.destroy()


# ----------------------------------------------------------------------
# A janela
# ----------------------------------------------------------------------

class _App:
    def __enter__(self):
        from tkinter import messagebox

        from ui.main_window import MainWindow
        self._caixas = messagebox.showinfo, messagebox.showerror
        messagebox.showinfo = messagebox.showerror = lambda *a, **k: None
        self.root = raiz_tk()
        if self.root is None:
            pytest.skip("sem display")
        self.win = MainWindow(self.root)
        return self

    def __exit__(self, *a):
        from tkinter import messagebox
        messagebox.showinfo, messagebox.showerror = self._caixas
        try:
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass


def _cascata(win, rotulo):
    barra = win.parent.nametowidget(win.parent.cget("menu"))
    for i in range(barra.index("end") + 1):
        if barra.type(i) == "cascade" and barra.entrycget(i, "label") == rotulo:
            return barra.nametowidget(barra.entrycget(i, "menu"))
    raise AssertionError(f"sem o menu {rotulo}")


def test_o_menu_exibir_tem_o_zoom_e_o_enquadrar():
    with _App() as app:
        exibir = _cascata(app.win, "Exibir")
        itens = {exibir.entrycget(i, "label"): exibir.entrycget(i, "accelerator")
                 for i in range(exibir.index("end") + 1) if exibir.type(i) == "command"}
        assert itens == {"Ajustar à janela": "Ctrl+0", "Tamanho real (100%)": "Ctrl+1",
                         "Aumentar o zoom": "Ctrl+=", "Diminuir o zoom": "Ctrl+-",
                         "Enquadrar box selecionado": "F4"}
        # e os atalhos estão ligados na raiz, com Ctrl — nenhum na tecla solta
        for sequencia in ("<Control-Key-0>", "<Control-Key-1>", "<Control-equal>",
                          "<Control-minus>"):
            assert app.win.parent.bind(sequencia), sequencia
        for solta in ("<Key-plus>", "<Key-minus>", "<Key-0>", "<Key-f>", "<Key-F>"):
            assert not app.win.parent.bind(solta), solta


def test_o_documento_novo_abre_ajustado_a_janela():
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        imagem = os.path.join(tmp, "pagina.png")
        Image.new("L", PAGINA, 255).save(imagem)
        app.win.canvas.tamanho_real()
        app.win.open_image(imagem)
        canvas = app.win.canvas
        assert canvas.ajustado is True
        largura, altura = canvas.viewport()
        assert PAGINA[0] * canvas.zoom <= largura and PAGINA[1] * canvas.zoom <= altura
