"""Os pequenos da janela principal (RG-13, R-19), um teste por item.

- Ctrl+Z/Ctrl+Y não mudavam o "suja": desfazer até o estado salvo deixava a página suja.
- "Aprender com a página" ensinava o léxico antes de a gravação das amostras dar certo.
- O lote convertia o livro inteiro para a memória antes de começar, e a imagem ilegível
  sumia sem ser contada.
- O relator de exceções do Tk gravava no log a cada exceção de `<B1-Motion>`: um registro
  por pixel arrastado.
"""

import logging
import os
import tempfile

from tkinter import filedialog, messagebox

from PIL import Image

from core.box_model import BoxEntry
from tests.test_trabalho_fora_da_interface import _App


def _pagina(app, tmp):
    imagem = os.path.join(tmp, "pagina.png")
    Image.new("L", (200, 80), 255).save(imagem)
    app.win.open_image(imagem)
    return imagem


def test_desfazer_ate_o_estado_salvo_deixa_a_pagina_limpa():
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        win = app.win
        _pagina(app, tmp)
        assert not win.session.is_dirty()
        win.boxes.append(BoxEntry("a", 10, 10, 20, 30))
        win._commit_change()
        assert win.session.is_dirty()
        win._perform_undo()
        assert not win.session.is_dirty(), "desfazer até o estado aberto deixou a página suja"
        win._perform_redo()
        assert win.session.is_dirty(), "refazer a mudança não sujou a página"


def test_o_lexico_so_aprende_depois_de_gravar(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        win = app.win
        _pagina(app, tmp)
        win.boxes.append(BoxEntry("a", 10, 10, 20, 30))
        win._commit_change()
        aprendidas = []
        monkeypatch.setattr(win, "aprender_palavras_da_pagina", lambda *a, **k: aprendidas.append(1) or [])
        monkeypatch.setattr(win, "aprender_palavras_das_paginas", lambda *a, **k: aprendidas.append(1) or [])
        monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)

        def quebra(*a, **k):
            raise OSError("disco cheio")

        monkeypatch.setattr(win.learning_service, "learn_from_boxes", quebra)
        win.treino.learn_from_current_page()
        app.aguardar()
        assert not aprendidas, "o léxico aprendeu a página cuja gravação falhou"


def test_o_lote_vai_pagina_a_pagina_e_conta_a_ilegivel(monkeypatch, caplog):
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        win = app.win
        boa = os.path.join(tmp, "boa.png")
        Image.new("L", (40, 40), 255).save(boa)
        outra = os.path.join(tmp, "outra.png")
        Image.new("L", (40, 40), 255).save(outra)
        ruim = os.path.join(tmp, "ruim.png")
        open(ruim, "w", encoding="utf-8").write("não é imagem")
        monkeypatch.setattr(win.learning_service, "load_predictor", lambda: True)
        monkeypatch.setattr(win, "_avisar_do_modelo", lambda: None)
        monkeypatch.setattr(filedialog, "askopenfilenames", lambda **k: [boa, ruim, outra])
        monkeypatch.setattr(filedialog, "askdirectory", lambda **k: tmp)
        lotes = []
        monkeypatch.setattr(win.learning_service, "batch_extract_and_classify",
                            lambda imagens, saida, progress_callback=None: (lotes.append(len(list(imagens))), 3)[1])
        with caplog.at_level(logging.WARNING):
            win.treino.run_general_neural_training()
            app.aguardar()
        assert lotes == [1, 1], "o lote juntou as páginas na memória antes de começar"
        assert "1 imagem(ns) ilegível(is)" in app.caixas[-1][2], app.caixas[-1][2]
        assert any("ruim.png" in r.getMessage() for r in caplog.records)


def test_o_relator_grava_um_registro_por_excecao_repetida(caplog, monkeypatch):
    import appy

    monkeypatch.setattr(appy, "_gravar_no_log", lambda texto: "log")
    monkeypatch.setattr(messagebox, "showerror", lambda *a, **k: None)
    raiz = type("Raiz", (), {})()
    appy._instalar_relator_de_callbacks(raiz)
    erro = ValueError("coordenada fora da imagem")
    with caplog.at_level(logging.ERROR):
        for _ in range(30):                                    # um arrasto: a mesma exceção a cada pixel
            raiz.report_callback_exception(ValueError, erro, None)
    registros = [r for r in caplog.records if "callback do Tk" in r.getMessage()]
    assert len(registros) == 1, f"{len(registros)} registros de um arrasto só"


def test_o_pdf_do_lote_sai_uma_pagina_por_vez(tmp_path):
    import types

    import fitz

    from core.services.pdf_service import PDFService

    pdf = tmp_path / "livro.pdf"
    with fitz.open() as doc:
        for _ in range(3):
            doc.new_page(width=100, height=100)
        doc.save(pdf)
    paginas = PDFService.iterar_paginas(str(pdf), dpi=72)
    assert isinstance(paginas, types.GeneratorType)
    lidas = list(paginas)
    inteiras = PDFService.convert_pdf_to_images(str(pdf), dpi=72)
    assert [p.size for p in lidas] == [p.size for p in inteiras]
    assert [p.mode for p in lidas] == [p.mode for p in inteiras]
