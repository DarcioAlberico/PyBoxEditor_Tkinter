"""A tarefa não aplica resultado sobre boxes que mudaram (RG-12, R-15).

- "Preencher boxes" casava resultado e box por posição: apagar um box durante a leitura
  deslocava o caractere de todos os seguintes.
- A detecção de boxes substituía a página inteira, inclusive o que se editou no meio.
- "Salvar todas" lia as listas vivas na thread e marcava salva a página editada durante a
  gravação.

A edição não é travada (o Ctrl+S foi feito para deixar editar enquanto grava): o resultado
é que respeita o que mudou.
"""

import os
import tempfile
import threading

from PIL import Image

from core.box_model import BoxEntry
from tests.test_trabalho_fora_da_interface import _App, _segurar


def _pagina(app, tmp, boxes):
    imagem = os.path.join(tmp, "pagina.png")
    Image.new("L", (200, 80), 255).save(imagem)
    app.win.open_image(imagem)
    app.win.boxes.extend(boxes)
    app.win._commit_change()


def test_apagar_um_box_durante_preencher_nao_desloca_os_outros():
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        win = app.win
        _pagina(app, tmp, [BoxEntry("", 10, 10, 20, 30), BoxEntry("", 30, 10, 40, 30), BoxEntry("", 50, 10, 60, 30)])
        primeiro, segundo, terceiro = win.boxes
        liberar = threading.Event()
        letras = iter("abc")

        def preparar(h):
            liberar.wait(10)
            return lambda justo, com_faixa: (next(letras), "teste", 0.9)

        win._preencher_boxes("Preencher", preparar, lambda fontes, n: f"{n} lidos")
        assert win.task.is_running()
        win.boxes.remove(primeiro)                 # apagou o primeiro enquanto lia
        win._commit_change()
        liberar.set()
        app.aguardar()
        assert [b.char for b in win.boxes] == ["b", "c"], "o caractere de cada box se deslocou"
        assert win.boxes[0] is segundo and win.boxes[1] is terceiro


def test_editar_durante_a_deteccao_faz_ela_nao_aplicar_e_avisar():
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        win = app.win
        _pagina(app, tmp, [BoxEntry("a", 1, 1, 5, 5)])
        novos = [BoxEntry("", 10, 10, 20, 30)]
        liberar, _ = _segurar(win.box_service, "generate_boxes_opencv", lambda *a, **k: list(novos))
        win._arbitro_de_corte = lambda: None
        continuou = []
        win.generate_boxes_opencv(ao_concluir=lambda: continuou.append(1))
        win.boxes.append(BoxEntry("z", 50, 10, 60, 30))     # editou durante a detecção
        win._commit_change()
        liberar.set()
        app.aguardar()
        assert [b.char for b in win.boxes] == ["a", "z"], "a detecção apagou a edição feita no meio"
        assert not continuou
        assert any("mudou" in c[2] for c in app.caixas), "a detecção descartada não avisou"


def test_a_deteccao_sem_edicao_no_meio_aplica():
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        win = app.win
        _pagina(app, tmp, [BoxEntry("a", 1, 1, 5, 5)])
        liberar, _ = _segurar(win.box_service, "generate_boxes_opencv",
                              lambda *a, **k: [BoxEntry("", 10, 10, 20, 30)])
        win._arbitro_de_corte = lambda: None
        win.generate_boxes_opencv()
        liberar.set()
        app.aguardar()
        assert [(b.x1, b.x2) for b in win.boxes] == [(10, 20)]


def test_editar_durante_salvar_todas_deixa_a_pagina_suja():
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        win = app.win
        _pagina(app, tmp, [BoxEntry("a", 10, 10, 20, 30)])
        escrever = win._write_box_pair
        liberar = threading.Event()

        def gravar_devagar(path, image, boxes):
            liberar.wait(10)
            return escrever(path, image, boxes)

        win._write_box_pair = gravar_devagar
        win.save_all_pages()
        assert win.task.is_running()
        win.boxes[0].char = "z"                    # editou enquanto gravava
        win._commit_change()
        liberar.set()
        app.aguardar()
        with open(os.path.join(tmp, "pagina.box"), encoding="utf-8") as box:
            assert box.read().startswith("a "), "gravou a edição feita depois de mandar salvar"
        assert win.session.is_dirty(), "a página editada no meio saiu como salva"
