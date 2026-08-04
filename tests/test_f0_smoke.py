"""
Testes de fumaça da fase F0 (desbloqueio).

Cada teste aqui reproduz um defeito real que impedia o uso do programa.
Se algum voltar a falhar, o bug correspondente reapareceu.

Rodar sem pytest:      python tests/test_f0_smoke.py
Rodar com pytest:      pytest tests/ -v
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import raiz_tk

import fitz
import numpy as np
from PIL import Image

from core.box_model import BoxEntry
from core.services.history_service import HistoryManager
from core.services.learning_service import LearningService
from core import chess_pdf_processor as cpp


# ----------------------------------------------------------------------
# F0.1 — BoxEntry é dataclass, não dicionário
# ----------------------------------------------------------------------

def test_box_entry_acesso_por_atributo():
    """Era: TypeError: 'BoxEntry' object is not subscriptable."""
    b = BoxEntry("a", 1, 2, 3, 4)

    assert (b.x1, b.y1, b.x2, b.y2) == (1, 2, 3, 4)
    assert b.width == 2 and b.height == 2

    for acesso in (lambda: b["x1"], lambda: b.get("x1")):
        try:
            acesso()
        except (TypeError, AttributeError):
            pass
        else:
            raise AssertionError("BoxEntry não deve aceitar acesso estilo dicionário")


def test_box_entry_copy():
    """Era: AttributeError: 'BoxEntry' object has no attribute 'copy'
    (quebrava mover e redimensionar box com o mouse)."""
    b = BoxEntry("a", 1, 2, 3, 4)
    c = b.copy()

    assert c == b and c is not b
    c.x1 = 99
    assert b.x1 == 1, "copy() deve ser independente do original"


def test_update_sidebar_com_boxes():
    """Era: o app morria ao renderizar a lista assim que existia 1 box."""
    import tkinter as tk
    from ui.main_window import MainWindow

    root = raiz_tk()
    try:
        win = MainWindow(root)
        win.image = Image.new("L", (200, 100), color=255)
        win.boxes = [BoxEntry("a", 1, 2, 3, 4), BoxEntry("", 5, 6, 7, 8)]

        win.update_sidebar()  # <- estourava aqui

        assert win.listbox.size() == 2
        assert "'a'" in win.listbox.get(0)
        assert "'?'" in win.listbox.get(1), "box vazio deve aparecer como '?'"
    finally:
        root.destroy()


def test_learn_from_boxes_aceita_boxentry():
    """Era: AttributeError em b.get("char") — quebrava 'Aprender com Página Atual'."""
    with tempfile.TemporaryDirectory() as tmp:
        svc = LearningService(data_dir=tmp)
        img = Image.new("L", (100, 50), color=255)
        boxes = [BoxEntry("a", 0, 0, 10, 10),
                 BoxEntry("", 10, 0, 20, 10),      # sem char: deve ser ignorado
                 BoxEntry("b", 20, 0, 30, 10)]

        assert svc.learn_from_boxes(img, boxes) == 2


def test_lote_extrai_e_classifica_sem_quebrar():
    """Era: AttributeError — 'Treinamento Geral Neural (Batch)' montava dicts
    e os passava a merge_vertical_boxes, que acessa atributos.

    Exercita batch_extract_and_classify de verdade (com um predictor de
    mentira, para não depender do modelo treinado)."""
    class _PredictorFalso:
        loaded = True
        def predict(self, crop_np):
            return ("a", 0.99)

    with tempfile.TemporaryDirectory() as tmp:
        svc = LearningService(data_dir=os.path.join(tmp, "train"))
        svc._predictor = _PredictorFalso()
        svc.load_predictor = lambda: True

        # duas manchas escuras lado a lado -> dois contornos, sem merge vertical
        arr = np.full((40, 60), 255, dtype=np.uint8)
        arr[10:25, 10:20] = 0
        arr[10:25, 30:40] = 0

        destino = os.path.join(tmp, "out")
        os.makedirs(destino)

        total = svc.batch_extract_and_classify(
            [("pagina_teste", Image.fromarray(arr))], destino
        )                                               # <- estourava aqui

        assert total == 2
        assert os.path.isdir(os.path.join(destino, "lower_a"))


# ----------------------------------------------------------------------
# F0.2 — substituição de glifos precisa escrever peças, não '·'
# ----------------------------------------------------------------------

def test_fonte_resolvida_cobre_as_12_pecas():
    """A fonte escolhida precisa desenhar U+2654..U+265F de verdade.
    Arial, Segoe UI, Times e Calibri passam no teste 'arquivo existe' e
    falham neste."""
    caminho = cpp.resolve_chess_font()

    assert os.path.exists(caminho)
    assert cpp.missing_glyphs(caminho) == []


def test_helv_falha_na_deteccao():
    """Guarda de sanidade: a fonte antiga (helv/Helvetica) NÃO cobre as peças.
    Se este teste falhar, missing_glyphs() parou de detectar o problema."""
    helv = fitz.Font("helv")
    ausentes = [c for c in cpp.CHESS_UNICODE if not helv.has_glyph(ord(c))]

    assert len(ausentes) == 12, "helv não deveria ter nenhuma das 12 peças"


def test_substituicao_ponta_a_ponta_gera_glifos_reais():
    """Era: o PDF de saída trazia '·' no lugar de cada peça, sem erro nenhum.

    Constrói um PDF, trata 'arial' como fonte de xadrez (o PyMuPDF reporta o
    nome interno da fonte, então não dá para forjar 'Merida'), converte, e
    confere que os símbolos saíram inteiros.
    """
    original = cpp.CHESS_FONT_KEYWORDS[:]
    tmpdir = tempfile.mkdtemp()
    entrada = os.path.join(tmpdir, "in.pdf")
    saida = os.path.join(tmpdir, "out.pdf")

    try:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_font(fontname="F0", fontfile=r"C:\Windows\Fonts\arial.ttf")
        page.insert_text((50, 100), "KQRBN", fontname="F0", fontsize=14)
        doc.save(entrada)
        doc.close()

        cpp.CHESS_FONT_KEYWORDS[:] = ["arial"]
        paginas, trocas = cpp.substitute_chess_glyphs(entrada, saida)

        assert paginas == 1 and trocas == 1

        texto = fitz.open(saida)[0].get_text()
        for peca in "\u2654\u2655\u2656\u2657\u2658":
            assert peca in texto, f"peça {peca} não chegou ao PDF de saída"
        assert "\u00b7" not in texto, "voltou a escrever '·' no lugar das peças"
    finally:
        cpp.CHESS_FONT_KEYWORDS[:] = original


# ----------------------------------------------------------------------
# F0.3 — undo/redo com padrão único de snapshot
# ----------------------------------------------------------------------

def test_undo_redo_no_fluxo_do_editor():
    """O teste que de fato guarda a F0.3.

    O HistoryManager sempre esteve correto; o defeito estava nos chamadores,
    que gravavam o snapshot ANTES de mudar os boxes. Assim o estado novo nunca
    entrava no histórico, e o redo devolvia o estado velho — a alteração
    sumia para sempre.
    """
    import tkinter as tk
    from ui.main_window import MainWindow

    root = raiz_tk()
    try:
        win = MainWindow(root)
        win.image = Image.new("L", (200, 100), color=255)
        win.boxes = [BoxEntry("A", 0, 0, 10, 10), BoxEntry("B", 20, 0, 30, 10)]
        win.selected_index = 0
        win.history.reset()
        win.history.snapshot(win.boxes, 0)

        win.delete_selected_box()
        assert [b.char for b in win.boxes] == ["B"]

        win._perform_undo()
        assert [b.char for b in win.boxes] == ["A", "B"], "undo não restaurou o box"

        win._perform_redo()
        assert [b.char for b in win.boxes] == ["B"], "redo perdeu a exclusão"
    finally:
        root.destroy()


def test_history_manager_ida_e_volta():
    """Unidade do HistoryManager, no padrão 'snapshot após a mutação'."""
    h = HistoryManager()
    boxes = [BoxEntry("A", 0, 0, 1, 1)]
    h.snapshot(boxes, 0)                        # estado inicial

    boxes = boxes + [BoxEntry("B", 0, 0, 1, 1)]
    h.snapshot(boxes, 1)                        # snapshot APÓS a mutação

    desfeito, _ = h.undo()
    assert [b.char for b in desfeito] == ["A"]

    refeito, _ = h.redo()
    assert [b.char for b in refeito] == ["A", "B"], "redo perdeu a alteração"


def test_undo_isola_snapshots():
    """Mutar os boxes depois do snapshot não pode alterar o histórico."""
    h = HistoryManager()
    boxes = [BoxEntry("A", 0, 0, 1, 1)]
    h.snapshot(boxes, 0)
    h.snapshot(boxes, 0)

    boxes[0].char = "MUDOU"

    desfeito, _ = h.undo()
    assert desfeito[0].char == "A", "o histórico guardou uma referência, não uma cópia"


# ----------------------------------------------------------------------
# Execução direta, sem pytest
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
            falhas.append((nome, e))
            print(f"  FALHA {nome}\n          {type(e).__name__}: {e}")

    print(f"\n{len(testes) - len(falhas)}/{len(testes)} testes passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(_main())
