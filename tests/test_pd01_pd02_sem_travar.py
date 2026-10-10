"""
PD-01 e PD-02 (`docs/ROADMAP_PENDENCIAS.md`) — nada trava a thread da interface.

- PD-01: a sondagem do Tesseract (`--version`, `--list-langs`) tem prazo, e a
  ação «OCR (Tesseract)» da janela tem o disjuntor que o `livro.extrair` já
  tinha (F124).
- PD-02: as sondagens que a caixa de exportação precisa antes de abrir rodam
  numa thread enquanto a janela processa eventos. A outra metade da PD-02,
  a prova por programação dinâmica, está em `test_pd02_prova_dinamica.py`.
"""

import os
import sys
import time

import pytest

from core.box_model import BoxEntry
from core.services import ocr_service
from core.services.ocr_service import OCRService, TesseractSemResposta


# ----------------------------------------------------------------------
# PD-01 — a sondagem com prazo
# ----------------------------------------------------------------------

def test_o_executavel_que_nao_volta_e_morto_no_prazo():
    inicio = time.monotonic()
    with pytest.raises(TesseractSemResposta) as erro:
        ocr_service._sondar([sys.executable, "-c", "import time; time.sleep(30)"],
                            prazo=0.5)
    assert erro.value.prazo == 0.5
    assert time.monotonic() - inicio < 10


def test_o_executavel_que_responde_devolve_codigo_e_saida():
    codigo, saida = ocr_service._sondar(
        [sys.executable, "-c", "print('tesseract v5.5.0.20241111')"], prazo=30)
    assert codigo == 0
    assert ocr_service._versao_da_saida(saida) == "5.5.0.20241111"


def test_a_versao_e_os_idiomas_saem_da_saida_do_executavel():
    assert ocr_service._versao_da_saida("tesseract 4.1.1\n leptonica-1.79") == "4.1.1"
    assert ocr_service._versao_da_saida("") is None
    saida = ('List of available languages in "C:\\tessdata/" (3):\n'
             "eng\nosd\npor\nchi_sim\n")
    assert ocr_service._idiomas_da_saida(saida) == {"eng", "osd", "por", "chi_sim"}


def test_a_sondagem_sem_resposta_e_indisponivel_com_o_motivo(monkeypatch):
    pytest.importorskip("pytesseract")

    def preso(argumentos, prazo=ocr_service.PRAZO_DA_SONDAGEM_S):
        raise TesseractSemResposta(prazo)

    monkeypatch.setattr(ocr_service, "_sondar", preso)
    disponivel, motivo = OCRService().tesseract_disponivel("en")
    assert disponivel is False
    assert "não respondeu" in motivo and "--version" in motivo


def test_a_lista_de_idiomas_sem_resposta_tambem_e_indisponivel(monkeypatch):
    pytest.importorskip("pytesseract")

    def so_a_versao(argumentos, prazo=ocr_service.PRAZO_DA_SONDAGEM_S):
        if "--version" in argumentos:
            return 0, "tesseract 5.3.0\n"
        raise TesseractSemResposta(prazo)

    monkeypatch.setattr(ocr_service, "_sondar", so_a_versao)
    disponivel, motivo = OCRService().tesseract_disponivel("en")
    assert disponivel is False and "--list-langs" in motivo


def test_o_idioma_que_falta_continua_sendo_dito(monkeypatch):
    pytest.importorskip("pytesseract")

    def executavel(argumentos, prazo=ocr_service.PRAZO_DA_SONDAGEM_S):
        if "--version" in argumentos:
            return 0, "tesseract v5.5.0.20241111\n"
        return 0, 'List of available languages in "x" (2):\neng\nosd\n'

    monkeypatch.setattr(ocr_service, "_sondar", executavel)
    assert OCRService().tesseract_disponivel("en") == (True, "5.5.0.20241111")
    disponivel, motivo = OCRService().tesseract_disponivel("pt")
    assert disponivel is False and "'por'" in motivo


# ----------------------------------------------------------------------
# A janela
# ----------------------------------------------------------------------

def _janela():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from conftest import raiz_tk
    from ui.main_window import MainWindow

    raiz = raiz_tk()
    if raiz is None:
        return None, None
    return raiz, MainWindow(raiz)


def _fechar(raiz, win):
    try:
        win.task.shutdown()
        raiz.destroy()
    except Exception:
        pass


def _preencher_com_tesseract(monkeypatch, raiz, win, respostas):
    """Roda «OCR (Tesseract)» em cinco boxes, com o motor respondendo pela
    fila `respostas` (um par `(char, conf)` ou `None` para "sem resposta")."""
    from conftest import esperar_ate
    from tkinter import messagebox
    from PIL import Image

    infos = []
    monkeypatch.setattr(messagebox, "showinfo", lambda t, m, **k: infos.append(m))
    monkeypatch.setattr(messagebox, "showerror", lambda t, m, **k: infos.append(m))
    win.image = Image.new("L", (120, 40), color=200)
    win.boxes = [BoxEntry("", 5 + 20 * i, 5, 20 + 20 * i, 30) for i in range(5)]
    chamadas = []

    def tesseract(recorte, whitelist=None):
        chamadas.append(1)
        resposta = respostas.pop(0) if respostas else ("x", 0.9)
        if resposta is None:
            raise TesseractSemResposta(ocr_service.PRAZO_DO_CARACTERE_S)
        return resposta

    monkeypatch.setattr(win.ocr_service, "tesseract_ocr_conf", tesseract)
    win.auto_fill_characters()
    esperar_ate(raiz, lambda: infos)
    return infos, chamadas


def test_o_disjuntor_da_janela_desliga_o_tesseract_preso(monkeypatch):
    raiz, win = _janela()
    if win is None:
        pytest.skip("sem display")
    try:
        infos, chamadas = _preencher_com_tesseract(
            monkeypatch, raiz, win, [("a", 0.9), None, None, ("b", 0.9)])
        # Dois boxes seguidos sem resposta: o terceiro em diante não pergunta.
        assert len(chamadas) == 1 + win.BOXES_SEM_RESPOSTA_ATE_DESISTIR
        assert [b.char for b in win.boxes] == ["a", "", "", "", ""]
        assert infos and "desligado" in infos[0]
    finally:
        _fechar(raiz, win)


def test_um_prazo_vencido_so_esvazia_o_box_e_a_leitura_segue(monkeypatch):
    raiz, win = _janela()
    if win is None:
        pytest.skip("sem display")
    try:
        infos, chamadas = _preencher_com_tesseract(
            monkeypatch, raiz, win,
            [("a", 0.9), None, ("b", 0.9), None, ("c", 0.9)])
        assert len(chamadas) == 5
        assert [b.char for b in win.boxes] == ["a", "", "b", "", "c"]
        assert infos and "2 box(es)" in infos[0] and "desligado" not in infos[0]
    finally:
        _fechar(raiz, win)


def test_a_espera_da_sondagem_nao_para_a_janela(monkeypatch):
    from tkinter import messagebox

    raiz, win = _janela()
    if win is None:
        pytest.skip("sem display")
    try:
        avisos = []
        monkeypatch.setattr(messagebox, "showinfo", lambda t, m, **k: avisos.append(m))
        atendidos = []

        def durante():
            atendidos.append(time.monotonic())
            # Outra tarefa pedida no meio da sondagem é recusada, com o motivo.
            atendidos.append(win._busy("A exportação"))

        raiz.after(300, durante)

        def lenta():
            time.sleep(1.0)
            return "pronto"

        inicio = time.monotonic()
        assert win._esperar_sem_travar("Examinando o arquivo", lenta) == "pronto"
        assert atendidos, "a janela não atendeu evento nenhum durante a espera"
        assert atendidos[0] - inicio < 0.9
        assert atendidos[1] is True and "examinando o arquivo" in avisos[0]
        assert win._busy("Depois") is False
    finally:
        _fechar(raiz, win)


def test_a_falha_da_sondagem_sobe_na_thread_da_interface():
    raiz, win = _janela()
    if win is None:
        pytest.skip("sem display")
    try:
        def quebra():
            raise ValueError("defeito")

        with pytest.raises(ValueError):
            win._esperar_sem_travar("Examinando", quebra)
    finally:
        _fechar(raiz, win)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
