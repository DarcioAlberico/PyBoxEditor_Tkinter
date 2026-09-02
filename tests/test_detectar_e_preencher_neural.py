"""
«Detectar e Preencher (Neural)» — os quatro defeitos que a revisão da ação achou.

1. Sem modelo, a ação seguia sem a rede e sem avisar: `aviso_do_modelo` cala
   quando a carga **falha**, e a cadeia pula o elo com `loaded=False`. Sobrava o
   k-NN em 0,30 com a trava da linha em 0,70 — a combinação que a tabela de
   `CONF_MAXIMA_PARA_A_LINHA_HIBRIDO` mediu como a pior.
2. Os boxes eram regenerados **antes** do `_busy`: com uma tarefa rodando, o
   usuário perdia a lista da página e depois lia que a ação não podia começar.
3. `altura_de_referencia(self.boxes)` era lida da thread de trabalho.
4. Um recorte que o OCR não lia derrubava a página inteira: o cancelamento
   aplicava o parcial, o erro não aplicava nada.
"""

import inspect
import os
import sys

import numpy as np
import pytest

from core import leitura_de_linha as ldl
from core.box_model import BoxEntry


def _boxes(chars, y1=10, y2=30, largura=8):
    return [BoxEntry(c, i * largura, y1, i * largura + largura - 1, y2)
            for i, c in enumerate(chars)]


def _janela():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from conftest import raiz_tk
    from ui.main_window import MainWindow

    raiz = raiz_tk()
    if raiz is None:
        return None, None
    return raiz, MainWindow(raiz)


# ----------------------------------------------------------------------
# 4. `ler_pagina` segura a página quando um recorte falha
# ----------------------------------------------------------------------

def _pagina():
    return np.full((60, 80), 200, dtype=np.uint8)


def test_sem_ao_falhar_a_excecao_sobe_como_antes():
    """O contrato de `medir_cadeia.py` e dos testes da F17 não muda."""
    def ler_caractere(b):
        raise ValueError("recorte degenerado")

    with pytest.raises(ValueError):
        ldl.ler_pagina(_pagina(), [_boxes("ab")],
                       ler_faixa=lambda t: ("ab", 0.9),
                       ler_caractere=ler_caractere)


def test_o_box_que_falhou_sai_vazio_e_o_resto_da_linha_e_lido():
    falhas = []

    def ler_caractere(b):
        if b.char == "b":
            raise ValueError("recorte degenerado")
        return (b.char, 0.9, "neural")

    saida = ldl.ler_pagina(_pagina(), [_boxes("abc")],
                           ler_faixa=lambda t: ("", 0.0),
                           ler_caractere=ler_caractere,
                           ao_falhar=lambda b, e: falhas.append((b.char, e)))

    assert [(c, f) for _b, c, _cf, f in saida] == [
        ("a", "neural"), ("", "vazio"), ("c", "neural")]
    assert len(falhas) == 1 and falhas[0][0] == "b"
    assert isinstance(falhas[0][1], ValueError)


def test_a_faixa_que_falhou_deixa_a_linha_com_a_ancora():
    falhas = []

    def ler_faixa(tira):
        raise RuntimeError("EasyOCR caiu")

    saida = ldl.ler_pagina(_pagina(), [_boxes("ab"), _boxes("cd", y1=35, y2=55)],
                           ler_faixa=ler_faixa,
                           ler_caractere=lambda b: (b.char, 0.5, "neural"),
                           ao_falhar=lambda b, e: falhas.append(e))

    assert "".join(c for _b, c, _cf, _f in saida) == "abcd"
    assert {f for _b, _c, _cf, f in saida} == {"neural"}
    assert len(falhas) == 2, "uma falha por linha, e a página inteira saiu"


def test_a_linha_que_a_faixa_leu_bem_nao_e_afetada_pela_que_falhou():
    def ler_faixa(tira):
        # A tira da segunda linha fica mais embaixo na página.
        if tira.shape[0] > 40:
            raise RuntimeError("EasyOCR caiu")
        return ("ab", 0.9)

    saida = ldl.ler_pagina(_pagina(), [_boxes("a0"), _boxes("cd", y1=5, y2=58)],
                           ler_faixa=ler_faixa,
                           ler_caractere=lambda b: (b.char, 0.5, "neural"),
                           ao_falhar=lambda b, e: None)
    assert "".join(c for _b, c, _cf, _f in saida) == "abcd"


# ----------------------------------------------------------------------
# 1 e 2 — a janela, sem modelo e com tarefa em andamento
# ----------------------------------------------------------------------

def _silenciar(monkeypatch):
    from tkinter import messagebox

    erros, infos, avisos = [], [], []
    monkeypatch.setattr(messagebox, "showerror", lambda t, m, **k: erros.append(m))
    monkeypatch.setattr(messagebox, "showinfo", lambda t, m, **k: infos.append(m))
    monkeypatch.setattr(messagebox, "showwarning", lambda t, m, **k: avisos.append(m))
    return erros, infos, avisos


def test_sem_modelo_a_acao_neural_para_e_diz_por_que(monkeypatch):
    from PIL import Image

    raiz, win = _janela()
    if win is None:
        pytest.skip("sem display")
    try:
        erros, infos, _avisos = _silenciar(monkeypatch)
        win.image = Image.new("L", (200, 100), color=255)
        win.boxes = _boxes("abc")

        monkeypatch.setattr(win.learning_service, "load_predictor", lambda: False)
        monkeypatch.setattr(win.learning_service, "motivo_do_modelo",
                            lambda: "custom_model.pth não existe.\nTreine a rede primeiro.")
        gerados = []
        monkeypatch.setattr(win, "generate_boxes_opencv",
                            lambda: gerados.append(1))

        win.generate_and_fill_neural()

        assert gerados == [], "sem modelo, a página não pode ter sido regenerada"
        assert len(erros) == 1 and "custom_model.pth" in erros[0]
        assert "Treine" in erros[0], "o erro tem de dizer o que fazer"
        assert not win.task.is_running(), "nada foi para a thread"
        assert [b.char for b in win.boxes] == list("abc"), \
            "os boxes que havia ficaram como estavam"
    finally:
        try:
            win.task.shutdown()
            raiz.destroy()
        except Exception:
            pass


def test_o_trabalho_tambem_recusa_um_modelo_que_sumiu_no_caminho():
    """
    A conferência na thread da UI é a que o usuário vê; a de dentro de
    `preparar` é a rede de segurança para a carga que falha **depois** dela.
    Ambas têm de estar na fonte — o caminho sem rede não pode existir.
    """
    from ui.main_window import MainWindow

    fonte = inspect.getsource(MainWindow.generate_and_fill_neural)
    assert fonte.count("load_predictor()") >= 2
    assert "motivo_do_modelo()" in fonte
    assert "raise RuntimeError" in fonte


@pytest.mark.parametrize("acao", [
    "generate_and_fill_neural",
    "generate_and_fill_combined",
    "generate_and_fill_linha",
    "generate_and_fill_easyocr",
])
def test_com_tarefa_em_andamento_os_boxes_nao_sao_regenerados(monkeypatch, acao):
    from PIL import Image

    raiz, win = _janela()
    if win is None:
        pytest.skip("sem display")
    try:
        _erros, infos, _avisos = _silenciar(monkeypatch)
        win.image = Image.new("L", (200, 100), color=255)
        win.boxes = _boxes("abc")

        monkeypatch.setattr(win.task, "is_running", lambda: True)
        monkeypatch.setattr(win.learning_service, "load_predictor", lambda: True)
        monkeypatch.setattr(win.learning_service, "aviso_do_modelo", lambda: "")
        gerados = []
        monkeypatch.setattr(win, "generate_boxes_opencv",
                            lambda: gerados.append(1))

        getattr(win, acao)()

        assert gerados == [], f"{acao} regenerou os boxes com tarefa rodando"
        assert len(infos) == 1 and "já há uma operação" in infos[0]
        assert [b.char for b in win.boxes] == list("abc")
    finally:
        try:
            raiz.destroy()
        except Exception:
            pass


# ----------------------------------------------------------------------
# 3 — a referência é tirada na thread da UI
# ----------------------------------------------------------------------

@pytest.mark.parametrize("acao", ["generate_and_fill_neural",
                                  "generate_and_fill_combined"])
def test_a_altura_de_referencia_nao_e_lida_dentro_de_preparar(acao):
    """
    `preparar` roda na thread de trabalho, e `self.boxes` é da UI — o canvas
    continua editável durante a tarefa. A mesma razão pela qual `pagina` é
    copiada antes do `_run_task`.
    """
    import ast

    from ui.main_window import MainWindow

    fonte = inspect.getsource(getattr(MainWindow, acao))
    tree = ast.parse(fonte.lstrip() if not fonte.startswith("def") else fonte)
    metodo = tree.body[0]
    preparar = next(n for n in ast.walk(metodo)
                    if isinstance(n, ast.FunctionDef) and n.name == "preparar")
    dentro = {n.attr for n in ast.walk(preparar) if isinstance(n, ast.Attribute)}
    assert "altura_de_referencia" not in dentro
    assert "altura_de_referencia" in fonte, "a referência continua sendo passada"


# ----------------------------------------------------------------------
# 4 — a ação liga o `ao_falhar` e conta as falhas no diálogo
# ----------------------------------------------------------------------

def test_a_acao_por_linha_aplica_o_que_leu_mesmo_com_um_recorte_ruim(monkeypatch):
    from PIL import Image

    raiz, win = _janela()
    if win is None:
        pytest.skip("sem display")
    try:
        _erros, infos, avisos = _silenciar(monkeypatch)
        win.image = Image.new("L", (200, 100), color=255)
        win.boxes = _boxes("F0re", y1=10, y2=30)
        for b in win.boxes:
            b.char = ""

        monkeypatch.setattr(win.ocr_service, "easyocr_linha_conf",
                            lambda faixa, *a, **k: ("Fore", 0.9))

        chamadas = []

        def ocr(crop, *a, **k):
            chamadas.append(1)
            if len(chamadas) == 2:
                raise ValueError("recorte degenerado")
            return ("x", 0.4)
        monkeypatch.setattr(win.ocr_service, "easyocr_ocr_conf", ocr)

        win.auto_fill_characters_linha()
        for _ in range(200):
            raiz.update()
            if win.boxes[0].char:
                break

        assert "".join(b.char for b in win.boxes) == "Fore", \
            "a linha preencheu inclusive o box cuja âncora falhou"
        assert infos == [] and len(avisos) == 1
        assert "1 leitura(s) falharam" in avisos[0]
        assert "ValueError" in avisos[0]
    finally:
        try:
            win.task.shutdown()
            raiz.destroy()
        except Exception:
            pass
