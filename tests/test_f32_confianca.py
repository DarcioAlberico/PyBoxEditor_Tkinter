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
            BoxEntry("b", 10, 0, 19, 9, confidence=0.40, source="easyocr_so"),
            BoxEntry("", 20, 0, 29, 9),
            # Régua plana: sem número, e vermelho apesar do 0,99 (F53).
            BoxEntry("d", 30, 0, 39, 9, confidence=0.99, source="easyocr"),
        ]
        w.update_sidebar()

        assert w.listbox.size() == 4
        assert "95%" in w.listbox.get(0)
        assert "40%" in w.listbox.get(1)
        assert "!" in w.listbox.get(3) and "99%" not in w.listbox.get(3)

        assert w.listbox.itemcget(0, "foreground") == cf.COR_ALTA
        assert w.listbox.itemcget(1, "foreground") == cf.COR_BAIXA
        assert w.listbox.itemcget(2, "foreground") == cf.COR_VAZIO
        assert w.listbox.itemcget(3, "foreground") == cf.COR_BAIXA


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


def test_box_de_arquivo_de_fora_fica_sem_info():
    """
    Um `.box` que não veio daqui não traz confiança, e "não avaliado" é a
    verdade sobre ele — pintá-lo de vermelho diria "confira este" quando o
    certo é "não sei".

    **Este teste já cobriu o caso errado.** Ele round-trippava pelo próprio
    programa e exigia que a confiança se perdesse, o que fazia da perda um
    contrato em vez de um defeito — ver `test_a_ida_e_volta_preserva_a_revisao`
    logo abaixo e a F49. O arquivo de fora é escrito à mão aqui, que é o que
    ele sempre quis dizer.
    """
    with tempfile.TemporaryDirectory() as tmp:
        destino = os.path.join(tmp, "p.box")
        with open(destino, "w", encoding="utf-8") as f:
            f.write("e 1 1 9 9 0\n")     # seis campos, como o Tesseract grava
        with _App() as app:
            w = app.win
            w._load_box_from_path(destino)
            b = w.boxes[0]

            assert b.char == "e"
            assert b.source == "" and b.confidence == 0.0
            assert cf.cor_do_box(b) == cf.COR_SEM_INFO


def test_a_ida_e_volta_preserva_a_revisao():
    """
    O arquivo que **este** programa gravou volta sabendo o que ele mediu (F49).

    Antes, salvar e reabrir zerava a fila: a página inteira voltava azul e a
    revisão respondia "nada pendente" com tudo por conferir.
    """
    with tempfile.TemporaryDirectory() as tmp:
        with _App() as app:
            w = app.win
            w.boxes = [BoxEntry("e", 1, 1, 9, 9, confidence=0.99, source="neural"),
                       BoxEntry("o", 11, 1, 19, 9, confidence=0.20, source="learner")]
            pendentes = sum(1 for b in w.boxes if cf.precisa_revisao(b))
            destino = os.path.join(tmp, "p.box")
            w._save_box_to_path(destino)

            w._load_box_from_path(destino)
            assert [b.source for b in w.boxes] == ["neural", "learner"]
            assert sum(1 for b in w.boxes if cf.precisa_revisao(b)) == pendentes == 1
            assert cf.cor_do_box(w.boxes[0]) == cf.COR_ALTA


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


# ----------------------------------------------------------------------
# F48 — o que o EasyOCR respondeu entra sempre
# ----------------------------------------------------------------------

def test_easyocr_entra_na_fila_com_confianca_alta():
    """
    A régua do CRNN é plana onde importa: naqueles boxes a mediana de confiança
    é 0,9708 **no erro e no acerto** (F43). Medido, a regra antiga deixava 53
    de 92 erros escaparem ali (F48).
    """
    alto = BoxEntry("e", 1, 1, 9, 9, confidence=0.99, source="easyocr")
    assert cf.precisa_revisao(alto) is True


def test_as_outras_fontes_continuam_no_corte():
    """A mudança é só para quem tem régua plana, e não desconfiança geral."""
    assert cf.precisa_revisao(
        BoxEntry("e", 1, 1, 9, 9, confidence=0.99, source="neural")) is False
    assert cf.precisa_revisao(
        BoxEntry("e", 1, 1, 9, 9, confidence=0.99, source="learner")) is False
    assert cf.precisa_revisao(
        BoxEntry("e", 1, 1, 9, 9, confidence=0.50, source="neural")) is True


def test_o_easyocr_como_leitor_nao_entra_na_regra():
    """
    A regra da F48 foi medida onde o EasyOCR é **último recurso** — 57% de erro,
    o que sobra depois de a rede e o k-NN recusarem. Por isso a fonte do leitor
    tem nome próprio (F53).

    **O que sustenta a isenção é a régua, e não o acerto** (F55). A F53 escreveu
    "89,5%", que é o número da leitura por linha (F17); a ação por caractere,
    que grava a mesma fonte, acerta 73,2%. O que decide é a separação: 0,776
    aqui contra 0,582 no último recurso — e 0,634 na rede, que ninguém propõe
    marcar inteira.
    """
    leitor = BoxEntry("e", 1, 1, 9, 9, confidence=0.99, source="easyocr_so")
    assert cf.precisa_revisao(leitor) is False
    assert cf.cor_do_box(leitor) == cf.COR_ALTA
    assert cf.rotulo(leitor) == " 99%"


def test_a_cor_e_a_fila_nao_discordam():
    """
    O que a F44 levantou como pergunta e a F48 tornou realidade: um box do
    EasyOCR com 0,99 saía **verde** e entrava na fila. O usuário navegava
    pendentes e via verde.
    """
    b = BoxEntry("e", 1, 1, 9, 9, confidence=0.99, source="easyocr")
    assert cf.precisa_revisao(b) is True
    assert cf.cor_do_box(b) == cf.COR_BAIXA
    assert cf.rotulo(b) == "   !", "o 99% mentiria ao lado do vermelho"


def test_o_manual_nao_e_arrastado_junto():
    """`manual` é autoridade do usuário — mandá-lo revisar seria circular."""
    assert cf.precisa_revisao(
        BoxEntry("e", 1, 1, 9, 9, confidence=1.0, source="manual")) is False


# ----------------------------------------------------------------------
# F55 — o nome da fonte do leitor, que nada prendia
# ----------------------------------------------------------------------

def _esperar(raiz, condicao, voltas=300):
    """A ação roda fora da thread da UI; o resultado chega num `update`."""
    for _ in range(voltas):
        raiz.update()
        if condicao():
            return True
    return False


def test_as_duas_acoes_de_leitor_gravam_easyocr_so(monkeypatch):
    """
    A F53 separou `easyocr_so` de `easyocr` para a regra da F48 valer só onde
    foi medida — e **nada prendia o nome**. Escrever `"easyocr"` de volta numa
    das duas ações põe a página inteira em vermelho e na fila, calado, e é uma
    linha de diferença.

    São duas ações e não uma, que é o que a F55 achou: «OCR (EasyOCR)» lê
    caractere a caractere e «OCR (EasyOCR por linha)» usa a mesma leitura como
    âncora. As duas gravam a mesma fonte para os boxes que só o caractere
    decidiu, e é por isso que as duas precisam estar neste teste.
    """
    with _App() as app:
        w = app.win

        # Por caractere: a fonte sai da própria ação.
        w.boxes = [BoxEntry("", 0, 10, 9, 30), BoxEntry("", 10, 10, 19, 30)]
        monkeypatch.setattr(w.ocr_service, "easyocr_ocr_conf",
                            lambda crop, *a, **k: ("x", 0.99))
        w.auto_fill_characters_easyocr()
        assert _esperar(app.root, lambda: all(b.char for b in w.boxes)), \
            "a ação por caractere não chegou aos boxes"
        assert {b.source for b in w.boxes} == {"easyocr_so"}

        # Por linha: onde a linha **confirma**, a fonte é a da âncora — e a
        # âncora daquela ação é o mesmo EasyOCR por caractere.
        w.boxes = [BoxEntry("", 0, 10, 9, 30), BoxEntry("", 10, 10, 19, 30)]
        monkeypatch.setattr(w.ocr_service, "easyocr_linha_conf",
                            lambda faixa, *a, **k: ("xx", 0.9))
        w.auto_fill_characters_linha()
        assert _esperar(app.root, lambda: all(b.char for b in w.boxes)), \
            "a ação por linha não chegou aos boxes"
        assert {b.source for b in w.boxes} == {"easyocr_so"}, \
            "quem a linha confirmou fica com a fonte de quem leu"
