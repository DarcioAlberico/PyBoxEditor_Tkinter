"""
PD-13 (`docs/ROADMAP_PENDENCIAS.md`) — a régua da F57 em produção.

Na ação «OCR (EasyOCR)» o k-NN é consultado no mesmo recorte, e a leitura que
ele não confirma sai com a fonte `easyocr_discorda`, que vai sempre à fila. A
confiança do box continua sendo a do EasyOCR. Nas 12 páginas rotuladas: 2.928
dos 2.977 erros pegos, contra 2.079 com a régua de antes (`medir_cadeia.py
--regua`).
"""

import os
import sys

import pytest

from core.box_model import BoxEntry
from ui import confidence


def test_a_fonte_que_discorda_vai_sempre_a_fila():
    box = BoxEntry("a", 0, 0, 10, 10)
    box.source, box.confidence = "easyocr_discorda", 0.99
    assert confidence.precisa_revisao(box)
    assert confidence.cor_do_box(box) == confidence.COR_BAIXA
    assert confidence.rotulo(box).strip() == "!"


def test_a_que_concorda_segue_a_confianca():
    box = BoxEntry("a", 0, 0, 10, 10)
    box.source, box.confidence = "easyocr_so", 0.99
    assert not confidence.precisa_revisao(box)
    box.confidence = 0.10
    assert confidence.precisa_revisao(box)


def _janela():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from conftest import raiz_tk
    from ui.main_window import MainWindow

    raiz = raiz_tk()
    if raiz is None:
        return None, None
    return raiz, MainWindow(raiz)


def test_a_acao_consulta_o_knn_e_marca_a_discordancia(monkeypatch):
    from conftest import esperar_ate
    from tkinter import messagebox
    from PIL import Image

    raiz, win = _janela()
    if win is None:
        pytest.skip("sem display")
    try:
        infos = []
        monkeypatch.setattr(messagebox, "showinfo", lambda t, m, **k: infos.append(m))
        win.image = Image.new("L", (120, 40), color=200)
        win.boxes = [BoxEntry("", 5 + 20 * i, 5, 20 + 20 * i, 30) for i in range(3)]
        leituras = [("a", 0.95), ("b", 0.40), ("", 0.0)]
        knn = [("a", 0.9), ("h", 0.9)]
        monkeypatch.setattr(win.ocr_service, "easyocr_ocr_conf",
                            lambda justo, contexto=None: leituras.pop(0))
        monkeypatch.setattr(win.learning_service, "predict_learner",
                            lambda justo: knn.pop(0))
        win.auto_fill_characters_easyocr()
        esperar_ate(raiz, lambda: infos)
        assert [(b.char, b.source) for b in win.boxes] == [
            ("a", "easyocr_so"), ("b", "easyocr_discorda"), ("", "")]
        assert win.boxes[1].confidence == 0.40, "a confiança é a do EasyOCR"
        assert knn == [], "o k-NN não é consultado no box vazio"
        assert infos and "discordou em 1" in infos[0]
    finally:
        try:
            win.task.shutdown()
            raiz.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
