"""Box fora da página não entra, e clique não é edição (RG-05b, R-54).

- O canvas não limitava o box à imagem: arrastado para fora, ele ficava com coordenadas
  negativas, o recorte saía vazio e o `cv2.resize` derrubava o "Aprender" no meio do lote.
- Pior: o box inteiro à esquerda (ou acima) da página não falhava — o fatiamento com
  índice negativo dá a volta, e o recorte saía com a tinta do outro lado da página,
  aprendida em silêncio com o rótulo do box.
- `clamp_box` perdia `margem` e `moldura`; `split_box` num box de 1 px dava um box de
  largura zero; e cada clique sem movimento fazia commit no histórico, sujando a página.
"""

import os
import tempfile

import numpy as np
from PIL import Image

from core import vertical
from core.box_model import BoxEntry
from core.services.box_service import BoxService
from core.services.learning_service import LearningService
from tests.test_trabalho_fora_da_interface import _App


def _pagina():
    """200x100, com tinta só na faixa da direita (x >= 180)."""
    arr = np.full((100, 200), 255, dtype=np.uint8)
    arr[:, 180:] = 0
    return arr


def test_o_box_inteiro_a_esquerda_da_pagina_nao_traz_tinta_do_outro_lado():
    recorte = vertical.recorte_de_pe(_pagina(), BoxEntry("a", -30, 10, -10, 40))
    assert recorte.size == 0, "o recorte deu a volta na página"


def test_o_box_que_sai_em_parte_e_cortado_na_borda():
    recorte = vertical.recorte_de_pe(_pagina(), BoxEntry("a", 190, -5, 230, 20))
    assert recorte.shape == (20, 10)


def test_o_aprendizado_pula_o_recorte_vazio_e_segue_o_lote(tmp_path):
    servico = LearningService(data_dir=str(tmp_path / "base"))
    pagina = Image.fromarray(_pagina())
    boxes = [BoxEntry("a", 182, 10, 195, 40),
             BoxEntry("b", -30, 10, -10, 40),            # inteiro fora, à esquerda
             BoxEntry("c", 250, 10, 270, 40),            # inteiro fora, à direita
             BoxEntry("d", 185, 50, 198, 90)]
    assert servico.learn_from_boxes(pagina, boxes) == 2
    assert servico.ultimos_pulados == 2
    pastas = sorted(os.listdir(tmp_path / "base"))
    assert not any(p.endswith("_b") or p.endswith("_c") for p in pastas), \
        "o box fora da página virou amostra"
    assert os.path.isfile(servico._get_learner().caminho_do_cache), "o cache do lote não foi salvo"


def test_clamp_box_preserva_todos_os_campos():
    box = BoxEntry("♘", -5, -2, 230, 120, confidence=0.4, source="ocr", angulo=90,
                   negativo=True, margem=0.6, moldura=True)
    preso = BoxService.clamp_box(box, 200, 100)
    assert (preso.x1, preso.y1, preso.x2, preso.y2) == (0, 0, 200, 100)
    assert preso.as_state()[5:] == box.as_state()[5:], "o clamp_box perdeu campos"


def test_split_box_de_um_pixel_devolve_o_box_inteiro():
    box = BoxEntry("i", 10, 10, 11, 30)
    assert BoxService.split_box(box, _pagina()) == [box]
    deitado = BoxEntry("i", 10, 10, 40, 11, angulo=90)          # ao longo da leitura, 1 px
    assert BoxService.split_box(deitado, _pagina()) == [deitado]
    partes = BoxService.split_box(BoxEntry("ab", 10, 10, 12, 30))
    assert [(p.x1, p.x2) for p in partes] == [(10, 11), (11, 12)]


class _Evento:
    def __init__(self, x, y):
        self.x, self.y = x, y


def _janela_com_um_box(app, tmp):
    caminho = os.path.join(tmp, "pagina.png")
    Image.fromarray(_pagina()).save(caminho)
    app.win.open_image(caminho)
    app.win.boxes.append(BoxEntry("a", 20, 20, 40, 50))
    app.win._commit_change()
    app.win.session.mark_saved()
    canvas = app.win.canvas
    canvas.zoom, canvas.offset_x, canvas.offset_y = 1.0, 0, 0
    app.win.select_box(-1)
    return canvas


def _arrastar(canvas, de, para):
    canvas.on_left_press(_Evento(*de))
    canvas.on_left_drag(_Evento(*para))
    canvas.on_left_release(_Evento(*para))


def test_mover_para_fora_para_na_borda_sem_mudar_o_tamanho():
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        canvas = _janela_com_um_box(app, tmp)
        _arrastar(canvas, (30, 30), (-100, -100))
        b = app.win.boxes[0]
        assert (b.x1, b.y1, b.x2, b.y2) == (0, 0, 20, 30)
        app.win.select_box(-1)
        _arrastar(canvas, (10, 10), (500, 500))
        b = app.win.boxes[0]
        assert (b.x1, b.y1, b.x2, b.y2) == (180, 70, 200, 100)


def test_redimensionar_e_box_novo_cortam_na_borda():
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        canvas = _janela_com_um_box(app, tmp)
        app.win.select_box(0)
        canvas.drag_mode = None
        # O canto de baixo à direita, levado para fora da página.
        canvas.on_left_press(_Evento(40, 50))
        assert canvas.drag_mode == "resize"
        canvas.on_left_drag(_Evento(400, 300))
        canvas.on_left_release(_Evento(400, 300))
        b = app.win.boxes[0]
        assert (b.x1, b.y1, b.x2, b.y2) == (20, 20, 200, 100)

        app.win.select_box(-1)
        app.win.boxes.clear()
        _arrastar(canvas, (150, 60), (260, 140))
        b = app.win.boxes[-1]
        assert (b.x1, b.y1, b.x2, b.y2) == (150, 60, 200, 100)


def test_clique_sem_movimento_nao_suja_a_pagina_nem_o_historico():
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        canvas = _janela_com_um_box(app, tmp)
        antes = len(app.win.history._history)
        for _ in range(3):
            app.win.select_box(-1)
            _arrastar(canvas, (30, 30), (30, 30))
        assert not app.win.session.is_dirty(), "o clique sujou a página"
        assert len(app.win.history._history) == antes, "o clique entrou no histórico"
