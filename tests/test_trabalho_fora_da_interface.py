"""
O trabalho pesado da janela principal roda numa tarefa (item 9 da
`docs/REVISAO_MODOS_OCR.md`, §3.5).

Seis handlers faziam o trabalho na thread do Tk, com a janela congelada e sem
"Cancelar": gerar os boxes, ler os diagramas, validar e avaliar a base de
linhas, o Ctrl+S (que codifica o PNG da página) e a busca dos semelhantes. Os
cinco da janela passam por `_run_task`; o sexto roda numa thread do próprio
diálogo (`tests/test_f36_semelhantes.py`). Os testes olham as duas pontas: o
handler volta sem ter feito o trabalho, e a tarefa, ao terminar, aplica o
resultado na thread da interface.
"""

import os
from pathlib import Path
import tempfile
import threading
import time
from tkinter import filedialog, messagebox
from types import SimpleNamespace

import pytest
from PIL import Image

from conftest import raiz_tk
from core.box_model import BoxEntry


def _dataset_de_linhas(caminho: Path, nome: str):
    (caminho / "images").mkdir(parents=True)
    Image.new("L", (80, 24), 255).save(caminho / "images" / nome)
    (caminho / "rec_gt.txt").write_text(
        f"images/{nome}\ttexto conferido\n", encoding="utf-8")


def test_a_ui_exige_datasets_de_avaliacao_independentes_e_validos(tmp_path):
    from ui.main_window import _validar_dataset_adicional_linhas

    treino = tmp_path / "treino"
    holdout = tmp_path / "holdout"
    calibracao = tmp_path / "calibracao"
    _dataset_de_linhas(treino, "treino.png")
    _dataset_de_linhas(holdout, "holdout.png")
    _dataset_de_linhas(calibracao, "calibracao.png")

    assert _validar_dataset_adicional_linhas(
        holdout, treino, nome="holdout") == holdout.resolve()
    assert _validar_dataset_adicional_linhas(
        calibracao, treino, nome="calibração", outros=(holdout,)) == calibracao.resolve()

    with pytest.raises(ValueError, match="independente"):
        _validar_dataset_adicional_linhas(treino, treino, nome="holdout")
    with pytest.raises(ValueError, match="diferente"):
        _validar_dataset_adicional_linhas(
            holdout, treino, nome="calibração", outros=(holdout,))


def test_treino_da_ui_encaminha_holdout_para_a_fachada(monkeypatch, tmp_path):
    from tkinter import simpledialog
    from ui import main_window
    from core import ocr_training

    treino = tmp_path / "treino"
    holdout = tmp_path / "holdout"
    _dataset_de_linhas(treino, "treino.png")
    _dataset_de_linhas(holdout, "holdout.png")

    janela = object.__new__(main_window.MainWindow)
    janela._busy = lambda *_args: False
    janela.status = SimpleNamespace(set=lambda *_args: None)
    janela.ocr_service = SimpleNamespace()
    chamada = {}

    def treinar(**kwargs):
        chamada.update(kwargs)
        return SimpleNamespace(production_eligible=False,
                               production_gate_reason="holdout ausente")

    monkeypatch.setattr(main_window, "pasta_de_linhas", lambda: treino)
    monkeypatch.setattr(main_window, "pasta_de_linhas_sinteticas",
                        lambda: tmp_path / "sem-sintetico")
    respostas = iter((True, False))
    monkeypatch.setattr(messagebox, "askyesno",
                        lambda *_args, **_kwargs: next(respostas))
    monkeypatch.setattr(filedialog, "askdirectory", lambda **_kwargs: str(holdout))
    monkeypatch.setattr(simpledialog, "askinteger", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(ocr_training, "treinar_pacote", treinar)

    def executar(_titulo, trabalho, _concluir, **_kwargs):
        class Handler:
            cancelled = False

            @staticmethod
            def log(_mensagem):
                pass

        trabalho(Handler())

    janela._run_task = executar
    janela.train_line_ocr()

    assert chamada["pasta"] == treino
    assert chamada["holdout"] == holdout.resolve()
    assert chamada["calibracao"] is None


class _App:
    def __enter__(self):
        from ui.main_window import MainWindow
        self.caixas = []
        self._originais = (messagebox.showinfo, messagebox.showerror,
                           messagebox.showwarning)
        messagebox.showinfo = lambda t, m, **k: self.caixas.append(("info", t, m))
        messagebox.showerror = lambda t, m, **k: self.caixas.append(("erro", t, m))
        messagebox.showwarning = lambda t, m, **k: self.caixas.append(("aviso", t, m))
        self.root = raiz_tk()
        if self.root is None:
            pytest.skip("sem display")
        self.win = MainWindow(self.root)
        return self

    def __exit__(self, *a):
        (messagebox.showinfo, messagebox.showerror,
         messagebox.showwarning) = self._originais
        try:
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass

    def aguardar(self, limite=30.0):
        fim = time.time() + limite
        self.root.update()
        while self.win.task.is_running() and time.time() < fim:
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        assert not self.win.task.is_running(), "a tarefa não terminou no tempo"


def _segurar(servico, metodo, resultado):
    """Troca `servico.metodo` por um que espera o sinal — para ver a janela
    responder enquanto o trabalho não acabou."""
    liberar = threading.Event()
    chamadas = []

    def lento(*a, **k):
        chamadas.append(threading.current_thread() is threading.main_thread())
        liberar.wait(10)
        return resultado(*a, **k) if callable(resultado) else resultado

    setattr(servico, metodo, lento)
    return liberar, chamadas


def test_gerar_boxes_roda_numa_tarefa_e_continua_pelo_ao_concluir():
    with _App() as app:
        win = app.win
        win.image = Image.new("L", (200, 80), 255)
        win.boxes = [BoxEntry("a", 1, 1, 5, 5)]
        novos = [BoxEntry("", 10, 10, 20, 30), BoxEntry("", 30, 10, 40, 30)]
        liberar, chamadas = _segurar(win.box_service, "generate_boxes_opencv",
                                     lambda *a, **k: list(novos))
        win._arbitro_de_corte = lambda: None
        continuou = []

        win.generate_boxes_opencv(ao_concluir=lambda: continuou.append(len(win.boxes)))
        assert win.task.is_running()
        assert [b.char for b in win.boxes] == ["a"], "trocou os boxes antes de gerar"
        liberar.set()
        app.aguardar()
        assert chamadas == [False], "a segmentação rodou na thread da interface"
        assert [(b.x1, b.x2) for b in win.boxes] == [(10, 20), (30, 40)]
        assert continuou == [2]


def test_cancelar_a_geracao_deixa_os_boxes_como_estavam():
    """A segmentação não se interrompe no meio; o "Cancelar" descarta o que
    ela devolveu, e nem a continuação roda."""
    with _App() as app:
        win = app.win
        win.image = Image.new("L", (200, 80), 255)
        win.boxes = [BoxEntry("a", 1, 1, 5, 5)]
        liberar, _ = _segurar(win.box_service, "generate_boxes_opencv",
                              lambda *a, **k: [BoxEntry("", 10, 10, 20, 30)])
        win._arbitro_de_corte = lambda: None
        continuou = []
        win.generate_boxes_opencv(ao_concluir=lambda: continuou.append(1))
        win.task.cancel()
        liberar.set()
        app.aguardar()
        assert [b.char for b in win.boxes] == ["a"] and continuou == []


def test_sem_boxes_novos_a_continuacao_nao_roda():
    with _App() as app:
        win = app.win
        win.image = Image.new("L", (200, 80), 255)
        win.box_service.generate_boxes_opencv = lambda *a, **k: []
        win._arbitro_de_corte = lambda: None
        continuou = []
        win.generate_boxes_opencv(ao_concluir=lambda: continuou.append(1))
        app.aguardar()
        assert continuou == [] and win.boxes == []


def test_ler_diagramas_roda_numa_tarefa_e_o_modelo_ausente_vira_caixa(monkeypatch):
    from core import diagrama

    with _App() as app:
        win = app.win
        win.image = Image.new("L", (200, 80), 255)
        monkeypatch.setattr(win.learning_service, "load_predictor", lambda: False)
        monkeypatch.setattr(win.box_service, "boxes_antes_do_descarte",
                            lambda *a, **k: ([], None, 1.0, None))
        threads = []

        def sem_modelo(*a, **k):
            threads.append(threading.current_thread() is threading.main_thread())
            raise diagrama.ModeloAusente("o modelo de diagramas não está instalado")

        monkeypatch.setattr(diagrama, "ler_pagina", sem_modelo)
        win.extrair_diagramas()
        app.aguardar()
        assert threads == [False]
        assert app.caixas == [("erro", "Diagramas",
                               "o modelo de diagramas não está instalado")]


def test_validar_e_avaliar_a_base_de_linhas_rodam_numa_tarefa(monkeypatch, tmp_path):
    from core import linha_trainer

    with _App() as app:
        win = app.win
        threads = []

        def validar(pasta=None):
            threads.append(threading.current_thread() is threading.main_thread())
            return {"linhas": 3, "caracteres": 5, "alfabeto": "abcde",
                    "vazias": [], "ilegiveis": [], "ausentes": [], "malformadas": []}

        monkeypatch.setattr(linha_trainer, "validar_dataset", validar)
        win.validar_dataset_linhas()
        app.aguardar()
        assert threads == [False]
        assert app.caixas[-1][:2] == ("info", "Dataset de linhas")
        assert "Linhas válidas no manifesto: 3" in app.caixas[-1][2]

        modelo, meta = tmp_path / "m.pth", tmp_path / "m.json"
        modelo.write_bytes(b"x")
        meta.write_text("{}", encoding="utf-8")
        monkeypatch.setattr("ui.main_window.caminhos_modelo_linha", lambda: (modelo, meta))

        def avaliar(destino=None, meta=None, pasta=None):
            threads.append(threading.current_thread() is threading.main_thread())
            return {"linhas": 2, "cer": 0.5, "wer": 1.0, "exatas": 0, "grupos": {}}

        monkeypatch.setattr(linha_trainer, "avaliar", avaliar)
        monkeypatch.setattr(linha_trainer, "salvar_avaliacao", lambda r, destino=None: None)
        win.avaliar_modelo_linhas()
        app.aguardar()
        assert threads == [False, False]
        assert app.caixas[-1][:2] == ("info", "Avaliação do OCR de linhas")
        assert "CER: 50.00%" in app.caixas[-1][2]


def test_o_ctrl_s_grava_numa_tarefa_o_que_havia_no_momento(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        win = app.win
        imagem = os.path.join(tmp, "pagina.png")
        Image.new("L", (200, 80), 255).save(imagem)
        win.open_image(imagem)
        win.boxes.extend([BoxEntry("a", 10, 10, 20, 30), BoxEntry("b", 30, 10, 40, 30)])
        win._commit_change()
        destino = os.path.join(tmp, "saida.box")
        monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **k: destino)

        escrever = win._write_box_pair
        liberar = threading.Event()
        threads = []

        def gravar_devagar(path, image, boxes):
            threads.append(threading.current_thread() is threading.main_thread())
            liberar.wait(10)
            return escrever(path, image, boxes)

        win._write_box_pair = gravar_devagar
        win.save_box_file()
        assert win.task.is_running() and not os.path.exists(destino)
        win.boxes[0].char = "z"                    # editou enquanto gravava
        win._commit_change()
        liberar.set()
        app.aguardar()

        assert threads == [False]
        with open(destino, encoding="utf-8") as box:
            assert box.read().startswith("a "), "gravou a edição feita depois do Ctrl+S"
        assert os.path.exists(os.path.join(tmp, "saida.png"))
        assert win.session.is_dirty(), "a edição do meio saiu como salva"
        assert "mudou enquanto era gravada" in app.caixas[-1][2]


def test_o_ctrl_s_sem_edicao_no_meio_deixa_a_pagina_salva(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        win = app.win
        imagem = os.path.join(tmp, "pagina.png")
        Image.new("L", (200, 80), 255).save(imagem)
        win.open_image(imagem)
        win.boxes.append(BoxEntry("a", 10, 10, 20, 30))
        win._commit_change()
        monkeypatch.setattr(filedialog, "asksaveasfilename",
                            lambda **k: os.path.join(tmp, "saida.box"))
        win.save_box_file()
        app.aguardar()
        assert not win.session.is_dirty()
        assert app.caixas[-1][1] == "Sucesso"
