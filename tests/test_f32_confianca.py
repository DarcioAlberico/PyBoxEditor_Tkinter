"""
Testes da F3.2 — confiança visível.

O `fallback_chain` sempre calculou a confiança de cada reconhecimento, e o
código a descartava (`char, source, _ = ...`). Sem ela, revisar uma página de
2.000 caracteres é reler tudo.

Rodar sem pytest:      python tests/test_f32_confianca.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import raiz_tk

import numpy as np
import tkinter as tk
from tkinter import messagebox
from PIL import Image

from core.box_model import BoxEntry
from core.services.ocr_service import OCRService
from ui import confidence as cf


# ----------------------------------------------------------------------
# Escala de cores
# ----------------------------------------------------------------------

def test_escala_de_cores():
    def box(char, conf, fonte):
        return BoxEntry(char, 0, 0, 5, 5, confidence=conf, source=fonte)

    assert cf.cor_do_box(box("e", 0.99, "neural")) == cf.COR_ALTA
    assert cf.cor_do_box(box("e", 0.90, "neural")) == cf.COR_ALTA
    assert cf.cor_do_box(box("e", 0.89, "neural")) == cf.COR_MEDIA
    assert cf.cor_do_box(box("e", 0.70, "neural")) == cf.COR_MEDIA
    assert cf.cor_do_box(box("e", 0.69, "neural")) == cf.COR_BAIXA
    assert cf.cor_do_box(box("", 0.99, "neural")) == cf.COR_VAZIO


def test_sem_info_nao_e_confianca_baixa():
    """
    Um box carregado de .box não traz confiança (o formato do Tesseract não
    guarda isso). Pintá-lo de vermelho diria 'confira este' quando o certo é
    'não sei' — e encheria a tela de falso alarme ao abrir um arquivo salvo.
    """
    carregado = BoxEntry("e", 0, 0, 5, 5)          # confidence=0.0, source=""

    assert cf.cor_do_box(carregado) == cf.COR_SEM_INFO
    assert cf.cor_do_box(carregado) != cf.COR_BAIXA
    assert cf.precisa_revisao(carregado) is False, \
        "sem informação não deve entrar na fila de revisão"


def test_precisa_revisao():
    assert cf.precisa_revisao(BoxEntry("", 0, 0, 5, 5)) is True
    assert cf.precisa_revisao(
        BoxEntry("e", 0, 0, 5, 5, confidence=0.5, source="neural")) is True
    assert cf.precisa_revisao(
        BoxEntry("e", 0, 0, 5, 5, confidence=0.95, source="neural")) is False


def test_rotulo_curto():
    assert cf.rotulo(BoxEntry("e", 0, 0, 5, 5, confidence=0.987, source="neural")) == " 99%"
    assert cf.rotulo(BoxEntry("e", 0, 0, 5, 5)) == "   ?"
    assert cf.rotulo(BoxEntry("", 0, 0, 5, 5)) == "   -"


# ----------------------------------------------------------------------
# A confiança do EasyOCR deixa de ser jogada fora
# ----------------------------------------------------------------------

def test_easyocr_devolve_confianca_real():
    """Era: fallback_chain devolvia 0.0 fixo para tudo que viesse do EasyOCR."""
    svc = OCRService()

    # readtext(detail=1) devolve (bbox, texto, confiança)
    falso = [([[0, 0], [9, 0], [9, 9], [0, 9]], "e", 0.87)]
    char, conf = svc._primeiro_char_easyocr(falso)

    assert char == "e"
    assert abs(conf - 0.87) < 1e-6, "a confiança do EasyOCR foi descartada"

    assert svc._primeiro_char_easyocr([]) == ("", 0.0)
    assert svc._primeiro_char_easyocr(
        [([[0, 0]], "   ", 0.9)]) == ("", 0.0)


def test_fallback_chain_propaga_confianca():
    """Cada elo da cadeia tem que devolver a confiança de quem respondeu."""
    class _Pred:
        loaded = True
        def __init__(self, c): self.c = c
        def predict(self, crop): return ("N", self.c)

    class _Learner:
        def __init__(self, c): self.c = c
        def predict(self, crop): return ("R", self.c)
        # A cadeia consulta o k-NN por `predict_e_margem` desde a F44: uma busca
        # só para as duas escalas.
        def predict_e_margem(self, crop): return ("R", self.c, 0.5)

    class _Reader:
        def recognize(self, img, horizontal_list=None, free_list=None, detail=1):
            return [([[0, 0]], "x", 0.42)]

    svc = OCRService()
    crop = np.full((10, 10), 255, dtype=np.uint8)

    # neural responde
    assert svc.fallback_chain(crop, predictor=_Pred(0.97), learner=_Learner(0.99),
                              reader=_Reader()) == ("N", "neural", 0.97)

    # neural abaixo do limiar -> learner responde
    assert svc.fallback_chain(crop, predictor=_Pred(0.10), learner=_Learner(0.99),
                              reader=_Reader()) == ("R", "learner", 0.99)

    # ambos abaixo -> easyocr, com a confiança dele (era 0.0 fixo)
    char, fonte, conf = svc.fallback_chain(
        crop, predictor=_Pred(0.10), learner=_Learner(0.10), reader=_Reader())
    assert (char, fonte) == ("x", "easyocr")
    assert abs(conf - 0.42) < 1e-6


# ----------------------------------------------------------------------
# Integração com o editor
# ----------------------------------------------------------------------

class _App:
    def __enter__(self):
        from ui.main_window import MainWindow
        self._info, self._erro = messagebox.showinfo, messagebox.showerror
        messagebox.showinfo = lambda *a, **k: None
        messagebox.showerror = lambda *a, **k: None
        self.root = raiz_tk()
        self.win = MainWindow(self.root)
        self.win.image = Image.new("L", (200, 100), color=255)
        return self

    def __exit__(self, *a):
        messagebox.showinfo, messagebox.showerror = self._info, self._erro
        try:
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass


def test_correcao_do_usuario_zera_a_suspeita():
    """
    O ponto que faz a escala funcionar: corrigir um box tem que tirá-lo do
    vermelho. Se a cor não convergisse, a revisão não teria fim visível.
    """
    with _App() as app:
        w = app.win
        w.boxes = [BoxEntry("c", 0, 0, 10, 10, confidence=0.31, source="easyocr")]
        w.selected_index = 0
        assert cf.cor_do_box(w.boxes[0]) == cf.COR_BAIXA
        assert cf.precisa_revisao(w.boxes[0]) is True

        w.char_entry.delete(0, "end")
        w.char_entry.insert(0, "e")
        w.apply_char()

        b = w.boxes[0]
        assert b.char == "e"
        assert b.source == "manual"
        assert b.confidence == 1.0
        assert cf.cor_do_box(b) == cf.COR_ALTA
        assert cf.precisa_revisao(b) is False


def test_apagar_caractere_volta_para_pendente():
    with _App() as app:
        w = app.win
        w.boxes = [BoxEntry("e", 0, 0, 10, 10, confidence=1.0, source="manual")]
        w.selected_index = 0

        w.char_entry.delete(0, "end")
        w.apply_char()

        assert w.boxes[0].source == "", "box vazio não tem origem"
        assert cf.cor_do_box(w.boxes[0]) == cf.COR_VAZIO
        assert cf.precisa_revisao(w.boxes[0]) is True


def test_lista_lateral_colore_e_mostra_confianca():
    with _App() as app:
        w = app.win
        w.boxes = [
            BoxEntry("a", 0, 0, 9, 9, confidence=0.95, source="neural"),
            BoxEntry("b", 10, 0, 19, 9, confidence=0.40, source="easyocr"),
            BoxEntry("", 20, 0, 29, 9),
        ]
        w.update_sidebar()

        assert w.listbox.size() == 3
        assert "95%" in w.listbox.get(0)
        assert "40%" in w.listbox.get(1)

        assert w.listbox.itemcget(0, "foreground") == cf.COR_ALTA
        assert w.listbox.itemcget(1, "foreground") == cf.COR_BAIXA
        assert w.listbox.itemcget(2, "foreground") == cf.COR_VAZIO


def test_contador_de_pendentes():
    with _App() as app:
        w = app.win
        w.boxes = [
            BoxEntry("a", 0, 0, 9, 9, confidence=0.95, source="neural"),
            BoxEntry("b", 10, 0, 19, 9, confidence=0.40, source="easyocr"),
            BoxEntry("", 20, 0, 29, 9),
        ]
        w.update_sidebar()
        assert "2 de 3 a revisar" in w.lbl_revisao.cget("text")

        for b in w.boxes:
            b.char, b.confidence, b.source = "x", 1.0, "manual"
        w.update_sidebar()
        assert "nada pendente" in w.lbl_revisao.cget("text")


def test_box_carregado_de_arquivo_fica_sem_info():
    """Salvar e recarregar perde a confiança — o .box do Tesseract não a guarda.
    O comportamento correto é 'não avaliado', não 'suspeito'."""
    with tempfile.TemporaryDirectory() as tmp:
        with _App() as app:
            w = app.win
            w.boxes = [BoxEntry("e", 1, 1, 9, 9, confidence=0.99, source="neural")]
            destino = os.path.join(tmp, "p.box")
            w._save_box_to_path(destino)

            w._load_box_from_path(destino)
            b = w.boxes[0]

            assert b.char == "e"
            assert b.source == "" and b.confidence == 0.0
            assert cf.cor_do_box(b) == cf.COR_SEM_INFO


def test_box_novo_nasce_vazio():
    """Era criado com char '?', que parecia um caractere reconhecido."""
    from ui.canvas_view import CanvasView

    with _App() as app:
        w = app.win
        c = w.canvas
        c.drag_mode = "new"
        c.new_box_start = (10, 10)
        c.new_box_end = (40, 40)

        class E:
            x = y = 0
        c.on_left_release(E())

        assert len(w.boxes) == 1
        assert w.boxes[0].char == ""
        assert cf.cor_do_box(w.boxes[0]) == cf.COR_VAZIO


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
