"""
Testes da F4.3 e F4.6 — navegação sem sobressalto e guard de atalho.

**F4.3.** `select_box` chamava `zoom_to_box` em *toda* seleção, com margem 10,0 e
zoom mínimo forçado de 1,5×. Navegar com as setas re-enquadrava a imagem a cada
tecla: dava para ver o caractere e não dava para ver a palavra. Agora a seleção
usa `garantir_visivel`, que rola o mínimo e **não mexe no zoom**; enquadrar virou
comando explícito (F4 ou duplo-clique).

**F4.6.** Havia dois guards de foco no mesmo arquivo — o de `_on_tecla_digitacao`,
completo, e o do Ctrl+D, que testava só `tk.Entry`. O roadmap dizia que o buraco
era `ttk.Entry`; medindo, `ttk.Entry` e `ttk.Spinbox` **herdam** de `tk.Entry` e
já estavam cobertos. Quem faltava era `tk.Text`, `tk.Spinbox` e `ttk.Combobox`.

Os testes de canvas usam um controlador falso: `CanvasView` só precisa de
`image`, `boxes`, `selected_index` e `update_canvas`, e assim não é preciso subir
a janela inteira.

Rodar sem pytest:      python tests/test_f43_navegacao.py
"""

import pytest
import os
import sys
import tkinter as tk
import tkinter.ttk as ttk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import raiz_tk

from core.box_model import BoxEntry


def _tem_display():
    try:
        raiz = raiz_tk()
        raiz.destroy()
        return True
    except Exception:
        return False


TEM_DISPLAY = _tem_display()


class ControladorFalso:
    """O mínimo que o CanvasView consome."""

    def __init__(self, boxes, largura=2000, altura=2000):
        from PIL import Image
        self.image = Image.new("L", (largura, altura), 255)
        self.boxes = boxes
        self.selected_index = -1
        self.redesenhos = 0

    def update_canvas(self):
        self.redesenhos += 1

    def select_box(self, i):
        self.selected_index = i


def _canvas(boxes, largura=400, altura=300):
    from ui.canvas_view import CanvasView

    raiz = raiz_tk()
    ctrl = ControladorFalso(boxes)
    cv = CanvasView(raiz, ctrl)
    cv.pack()
    # winfo_width() só vale depois de o Tk calcular a geometria; sem isto a
    # função cai no fallback 800x600 e o teste mede outra coisa.
    cv.config(width=largura, height=altura)
    raiz.update_idletasks()
    return raiz, cv, ctrl


# ----------------------------------------------------------------------
# F4.3 — garantir_visivel
# ----------------------------------------------------------------------

def test_nao_mexe_no_zoom():
    """O ponto da fase: rolar não é re-enquadrar."""
    if not TEM_DISPLAY:
        pytest.skip("sem display para o Tk")
    boxes = [BoxEntry("", 10, 10, 30, 40), BoxEntry("", 1500, 1500, 1520, 1530)]
    raiz, cv, _ = _canvas(boxes)
    try:
        cv.zoom = 2.5
        cv.garantir_visivel(1)
        assert cv.zoom == 2.5, f"o zoom mudou para {cv.zoom}"
    finally:
        raiz.destroy()


def test_box_ja_visivel_nao_rola():
    """Rolar sem necessidade é o próprio defeito que a fase veio corrigir."""
    if not TEM_DISPLAY:
        pytest.skip("sem display para o Tk")
    boxes = [BoxEntry("", 100, 100, 120, 130)]
    raiz, cv, ctrl = _canvas(boxes)
    try:
        cv.zoom = 1.0
        cv.offset_x = cv.offset_y = 0.0
        antes = (cv.offset_x, cv.offset_y, ctrl.redesenhos)
        cv.garantir_visivel(0)
        assert (cv.offset_x, cv.offset_y, ctrl.redesenhos) == antes
    finally:
        raiz.destroy()


def test_rola_o_suficiente_para_o_box_aparecer():
    if not TEM_DISPLAY:
        pytest.skip("sem display para o Tk")
    boxes = [BoxEntry("", 1500, 1500, 1520, 1530)]
    raiz, cv, _ = _canvas(boxes, largura=400, altura=300)
    try:
        cv.zoom = 1.0
        cv.offset_x = cv.offset_y = 0.0
        cv.garantir_visivel(0)

        b = boxes[0]
        x1 = b.x1 * cv.zoom + cv.offset_x
        x2 = b.x2 * cv.zoom + cv.offset_x
        y1 = b.y1 * cv.zoom + cv.offset_y
        y2 = b.y2 * cv.zoom + cv.offset_y
        vw, vh = cv.viewport()
        assert 0 <= x1 and x2 <= vw, f"fora em x: {x1}..{x2} (view {vw})"
        assert 0 <= y1 and y2 <= vh, f"fora em y: {y1}..{y2} (view {vh})"
    finally:
        raiz.destroy()


def test_rola_o_minimo_e_nao_centraliza():
    """
    Centralizar a cada seleção é o salto que incomodava. Um box logo abaixo da
    borda deve subir só o necessário, ficando perto da borda — não no meio.
    """
    if not TEM_DISPLAY:
        pytest.skip("sem display para o Tk")
    caixa = BoxEntry("", 50, 0, 70, 0)
    raiz, cv, _ = _canvas([caixa], largura=400, altura=300)
    try:
        cv.zoom = 1.0
        cv.offset_x = cv.offset_y = 0.0

        # Logo ABAIXO da borda de baixo — a posição é relativa à view efetiva,
        # que com a janela retraída é o recuo de `viewport()`, não o 300 pedido.
        _, vh = cv.viewport()
        caixa.y1, caixa.y2 = vh + 10, vh + 40

        cv.garantir_visivel(0)

        centro_do_box = (caixa.y1 + caixa.y2) / 2 + cv.offset_y
        assert centro_do_box > vh * 0.6, \
            f"centralizou em vez de rolar o mínimo (centro {centro_do_box} de {vh})"
    finally:
        raiz.destroy()


def test_box_maior_que_a_janela_e_centralizado():
    """Encostar numa borda deixaria a outra ponta fora de qualquer jeito."""
    if not TEM_DISPLAY:
        pytest.skip("sem display para o Tk")
    raiz, cv, _ = _canvas([BoxEntry("", 0, 0, 900, 900)], largura=400, altura=300)
    try:
        cv.zoom = 1.0
        cv.offset_x = cv.offset_y = 0.0
        cv.garantir_visivel(0)
        centro = 450 + cv.offset_x
        assert abs(centro - cv.viewport()[0] / 2) < 2
    finally:
        raiz.destroy()


def test_indice_invalido_nao_explode():
    if not TEM_DISPLAY:
        pytest.skip("sem display para o Tk")
    raiz, cv, _ = _canvas([BoxEntry("", 0, 0, 10, 10)])
    try:
        cv.garantir_visivel(-1)
        cv.garantir_visivel(99)
    finally:
        raiz.destroy()


def test_sem_imagem_nao_explode():
    if not TEM_DISPLAY:
        pytest.skip("sem display para o Tk")
    raiz, cv, ctrl = _canvas([BoxEntry("", 0, 0, 10, 10)])
    try:
        ctrl.image = None
        cv.garantir_visivel(0)
    finally:
        raiz.destroy()


class _Gravador:
    """Grava cada método chamado nele, com os argumentos: `(nome, args)`."""

    def __init__(self):
        self.chamadas = []

    def __getattr__(self, nome):
        if nome.startswith("__"):
            raise AttributeError(nome)
        return lambda *a, **k: self.chamadas.append((nome, a))


def test_selecao_nao_chama_mais_o_zoom():
    """
    Guarda contra o `zoom_to_box` voltar para dentro de `select_box`: a seleção
    pede ao canvas só que o box fique visível, e o enquadramento fica como estava.
    """
    from types import SimpleNamespace

    from ui.main_window import MainWindow

    canvas, campo = _Gravador(), _Gravador()
    janela = SimpleNamespace(boxes=[BoxEntry("a", 0, 0, 10, 10), BoxEntry("b", 20, 0, 30, 10)],
                             selected_index=-1, char_entry=campo, canvas=canvas,
                             update_sidebar=lambda: None, update_canvas=lambda: None)
    MainWindow.select_box(janela, 1)
    assert janela.selected_index == 1
    assert ("insert", (0, "b")) in campo.chamadas
    assert canvas.chamadas == [("garantir_visivel", (1,))], \
        "o zoom automático voltou para a seleção — ver F4.3"


def test_zoom_continua_disponivel_sob_comando():
    """O duplo-clique ainda enquadra o box selecionado: o zoom saiu da seleção, não do app."""
    from types import SimpleNamespace

    from ui.canvas_view import CanvasView

    pedidos = []
    falso = SimpleNamespace(
        controller=SimpleNamespace(image=object(), selected_index=3),
        zoom_to_box=pedidos.append,
    )
    assert CanvasView.on_double_click(falso, None) == "break"
    assert pedidos == [3]

    falso.controller.selected_index = -1
    CanvasView.on_double_click(falso, None)
    assert pedidos == [3], "sem box selecionado, o duplo-clique não enquadra nada"


# ----------------------------------------------------------------------
# F4.6 — guard de foco
# ----------------------------------------------------------------------

def test_guard_cobre_os_widgets_que_consomem_tecla():
    """
    O roadmap dizia que o buraco era `ttk.Entry`. Medindo, `ttk.Entry` e
    `ttk.Spinbox` herdam de `tk.Entry` e já estavam cobertos; quem faltava era
    `tk.Text`, `tk.Spinbox` e `ttk.Combobox`.
    """
    from ui.main_window import MainWindow

    campos = MainWindow.CAMPOS_DE_TEXTO
    for classe in (tk.Entry, tk.Text, tk.Spinbox, ttk.Entry, ttk.Combobox):
        assert issubclass(classe, campos), f"{classe.__name__} ficou de fora"

    # herdam de tk.Entry, então entram pelo guard sem precisar ser listadas
    assert issubclass(ttk.Entry, tk.Entry)
    assert issubclass(ttk.Spinbox, tk.Entry)
    # os que NÃO herdam, e por isso precisavam ser listados
    assert not issubclass(tk.Text, tk.Entry)
    assert not issubclass(tk.Spinbox, tk.Entry)


def test_ha_um_guard_so():
    """
    Havia dois guards no arquivo, um completo e o outro não. Guard duplicado é
    guard que sai de sincronia — foi como o do Ctrl+D ficou para trás.

    Os três atalhos perguntam ao mesmo `_foco_em_campo_de_texto`: com ele dizendo
    "campo", nenhum age; dizendo "não", os três agem — também com um `Entry` no
    foco, que um `isinstance` próprio de qualquer um deles calaria.
    """
    from types import SimpleNamespace

    from ui.main_window import MainWindow

    entry = tk.Entry.__new__(tk.Entry)          # sem Tk: ao guard só o tipo importa
    for em_campo in (True, False):
        feitos = []
        janela = SimpleNamespace(
            parent=SimpleNamespace(focus_get=lambda: entry),
            _foco_em_campo_de_texto=lambda v=em_campo: v,
            split_selected_box=lambda: feitos.append("dividir"),
            selected_index=0, canvas=SimpleNamespace(zoom_to_box=lambda i: feitos.append("zoom")),
            modo_digitacao=True, _mover_selecao=lambda passo: feitos.append("digitar"),
            _status_digitacao=lambda: None)
        espaco = SimpleNamespace(char=" ")
        MainWindow._on_key_split_safe(janela, espaco)
        MainWindow._on_key_zoom(janela, espaco)
        MainWindow._on_tecla_digitacao(janela, espaco)
        assert feitos == ([] if em_campo else ["dividir", "zoom", "digitar"]), em_campo


def test_guard_sobrevive_a_focus_get_sem_foco():
    """
    `focus_get()` levanta KeyError quando o foco está noutra aplicação. Sem
    tratamento, o atalho morreria com exceção em vez de simplesmente disparar.
    """
    from types import SimpleNamespace

    from ui.main_window import MainWindow

    def sem_foco():
        raise KeyError("o foco está noutra aplicação")

    janela = SimpleNamespace(parent=SimpleNamespace(focus_get=sem_foco),
                             CAMPOS_DE_TEXTO=MainWindow.CAMPOS_DE_TEXTO)
    assert MainWindow._foco_em_campo_de_texto(janela) is False
    janela.parent.focus_get = lambda: tk.Text.__new__(tk.Text)
    assert MainWindow._foco_em_campo_de_texto(janela) is True


def test_f4_esta_ligado_ao_zoom():
    """F4 enquadra o box selecionado (F4.3), ligado na janela inteira."""
    from ui.main_window import MainWindow

    class _Ligacoes:
        def __init__(self):
            self.ligadas = {}

        def bind(self, sequencia, handler):
            self.ligadas[sequencia] = handler

    class _Janela:
        """Cada atributo que a janela não tem é o nome dele: o handler se reconhece."""

        def __init__(self):
            self.parent, self.char_entry = _Ligacoes(), _Ligacoes()

        def __getattr__(self, nome):
            return f"handler {nome}"

    janela = _Janela()
    MainWindow._bind_keys(janela)
    assert janela.parent.ligadas["<F4>"] == "handler _on_key_zoom"


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
    if not TEM_DISPLAY:
        print("(sem display: os testes de canvas foram pulados)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(_main())
