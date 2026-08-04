"""
Testes da F3.4 — rascunho automático e recuperação.

A F3.7 protegeu contra fechar sem salvar, mas um travamento ainda perdia tudo
— e o `crash_log.txt` na raiz do projeto existe por um motivo.

Rodar sem pytest:      python tests/test_f34_autosave.py
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from tkinter import messagebox
from PIL import Image

from core.box_model import BoxEntry
from core.services.document_service import (
    DocumentSession, _GravadorAssincrono, caminho_sidecar)
from ui import confidence as cf


def _esperar_arquivo(caminho, limite=5.0):
    """O gravador é assíncrono: aguarda o arquivo aparecer."""
    fim = time.time() + limite
    while time.time() < fim:
        if os.path.isfile(caminho) and os.path.getsize(caminho) > 0:
            return True
        time.sleep(0.02)
    return False


class _App:
    def __init__(self, responder=True):
        self.responder = responder
        self.perguntas = []

    def __enter__(self):
        from ui.main_window import MainWindow
        self._info, self._erro, self._sim = (
            messagebox.showinfo, messagebox.showerror, messagebox.askyesno)
        messagebox.showinfo = lambda *a, **k: None
        messagebox.showerror = lambda *a, **k: None
        messagebox.askyesno = self._askyesno
        self.root = tk.Tk()
        self.root.withdraw()
        self.win = MainWindow(self.root)
        return self

    def _askyesno(self, titulo, msg, **k):
        self.perguntas.append((titulo, msg))
        return self.responder

    def __exit__(self, *a):
        messagebox.showinfo, messagebox.showerror, messagebox.askyesno = (
            self._info, self._erro, self._sim)
        try:
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass


# ----------------------------------------------------------------------
# Formato do rascunho
# ----------------------------------------------------------------------

def test_payload_guarda_confianca_e_origem():
    """
    O `.box` do Tesseract não tem onde guardar confiança — recarregar perdia o
    trabalho da F3.2. O rascunho guarda.
    """
    s = DocumentSession(os.path.join("dir", "livro.pdf"), num_pages=5, is_pdf=True)
    s.store(2, [BoxEntry("e", 1, 2, 3, 4, confidence=0.87, source="neural")])
    s.mark_dirty(2)

    p = s.montar_payload()
    assert p["schema"] == 1 and p["is_pdf"] is True
    assert p["sujas"] == [2]

    item = p["paginas"]["2"][0]
    assert item[0] == "e"
    assert item[5] == 0.87
    assert item[6] == "neural"


def test_ida_e_volta_do_payload():
    origem = DocumentSession("/tmp/livro.pdf", num_pages=9, is_pdf=True)
    origem.store(0, [BoxEntry("a", 0, 0, 5, 5, confidence=0.9, source="neural")])
    origem.store(4, [BoxEntry("b", 6, 0, 9, 5, confidence=0.3, source="easyocr"),
                     BoxEntry("", 10, 0, 14, 5)])
    origem.mark_dirty(0)
    origem.mark_dirty(4)

    destino = DocumentSession("/tmp/livro.pdf", num_pages=9, is_pdf=True)
    destino.aplicar_payload(origem.montar_payload())

    assert destino.pages_with_boxes() == [0, 4]
    assert destino.dirty_pages() == [0, 4]
    b = destino.boxes_for(4)[0]
    assert (b.char, b.confidence, b.source) == ("b", 0.3, "easyocr")
    assert destino.boxes_for(4)[1].char == ""


def test_rascunho_ilegivel_nao_derruba_a_abertura():
    """Um rascunho corrompido não pode impedir o usuário de abrir o arquivo."""
    with tempfile.TemporaryDirectory() as tmp:
        doc = os.path.join(tmp, "livro.pdf")
        with open(caminho_sidecar(doc), "w", encoding="utf-8") as f:
            f.write("{ isto nao e json valido")
        assert DocumentSession.ler_autosave(doc) is None

        with open(caminho_sidecar(doc), "w", encoding="utf-8") as f:
            json.dump({"schema": 999, "paginas": {"0": []}}, f)
        assert DocumentSession.ler_autosave(doc) is None, "schema desconhecido"


# ----------------------------------------------------------------------
# Gravação assíncrona e atômica
# ----------------------------------------------------------------------

def test_gravacao_assincrona():
    with tempfile.TemporaryDirectory() as tmp:
        doc = os.path.join(tmp, "livro.pdf")
        s = DocumentSession(doc, num_pages=3, is_pdf=True)
        s.store(1, [BoxEntry("x", 0, 0, 5, 5, confidence=0.5, source="easyocr")])

        g = _GravadorAssincrono()
        destino = s.autosave(g)
        assert destino == caminho_sidecar(doc)
        assert _esperar_arquivo(destino), "o rascunho não foi gravado"

        lido = DocumentSession.ler_autosave(doc)
        assert lido["paginas"]["1"][0][0] == "x"
        assert g.ultimo_erro is None


def test_nao_grava_sessao_vazia():
    with tempfile.TemporaryDirectory() as tmp:
        s = DocumentSession(os.path.join(tmp, "livro.pdf"), num_pages=3, is_pdf=True)
        assert s.autosave(_GravadorAssincrono()) is None
        assert not os.path.exists(s.sidecar())


def test_escrita_atomica_nao_deixa_temporario():
    with tempfile.TemporaryDirectory() as tmp:
        doc = os.path.join(tmp, "livro.pdf")
        s = DocumentSession(doc, num_pages=2, is_pdf=True)
        s.store(0, [BoxEntry("a", 0, 0, 5, 5)])

        g = _GravadorAssincrono()
        destino = s.autosave(g)
        assert _esperar_arquivo(destino)
        time.sleep(0.1)

        assert not os.path.exists(destino + ".tmp"), \
            "sobrou o arquivo temporário da escrita atômica"


def test_pedidos_seguidos_sao_coalescidos():
    """A fila tem tamanho 1: só interessa o estado mais recente."""
    with tempfile.TemporaryDirectory() as tmp:
        doc = os.path.join(tmp, "livro.pdf")
        s = DocumentSession(doc, num_pages=2, is_pdf=True)
        g = _GravadorAssincrono()

        for n in range(30):
            s.store(0, [BoxEntry(str(n % 10), 0, 0, 5, 5)])
            s.autosave(g)

        assert _esperar_arquivo(caminho_sidecar(doc))
        time.sleep(0.3)
        lido = DocumentSession.ler_autosave(doc)
        assert lido is not None and lido["paginas"]["0"], "o rascunho final saiu vazio"


# ----------------------------------------------------------------------
# Integração: o cenário que motiva a fase
# ----------------------------------------------------------------------

def test_autosave_dispara_a_cada_n_mudancas():
    with tempfile.TemporaryDirectory() as tmp:
        img = os.path.join(tmp, "pagina.png")
        Image.new("L", (200, 60), color=255).save(img)

        with _App() as app:
            w = app.win
            w.open_image(img)
            w.boxes.extend(BoxEntry("", i * 10, 0, i * 10 + 9, 9) for i in range(40))

            for i in range(w.AUTOSAVE_A_CADA - 1):
                w.boxes[i].char = "x"
                w._commit_change()
            assert not os.path.exists(w.session.sidecar()), "gravou cedo demais"

            w.boxes[30].char = "y"
            w._commit_change()          # completa o intervalo
            assert _esperar_arquivo(w.session.sidecar()), "não gravou no intervalo"


def test_recupera_trabalho_apos_travamento():
    """
    Simula o travamento: a sessão grava o rascunho e a janela morre sem salvar.
    Ao reabrir o mesmo arquivo, o trabalho tem que voltar — com confiança.
    """
    with tempfile.TemporaryDirectory() as tmp:
        img = os.path.join(tmp, "pagina.png")
        Image.new("L", (200, 60), color=255).save(img)

        # --- sessão 1: trabalha e "trava" ---
        with _App() as app:
            w = app.win
            w.open_image(img)
            w.boxes.append(BoxEntry("Q", 5, 5, 15, 15,
                                    confidence=0.42, source="easyocr"))
            w._commit_change()
            w.salvar_rascunho_agora()
            assert _esperar_arquivo(w.session.sidecar())
            # nada de salvar .box: é exatamente o que um travamento deixaria

        # --- sessão 2: reabre e aceita recuperar ---
        with _App(responder=True) as app:
            w = app.win
            w.open_image(img)

            assert any("Recuperar" in t for t, _ in app.perguntas), \
                "não ofereceu recuperação"
            assert len(w.boxes) == 1, "o trabalho não voltou"
            b = w.boxes[0]
            assert b.char == "Q"
            assert b.source == "easyocr" and abs(b.confidence - 0.42) < 1e-6, \
                "a confiança não sobreviveu ao rascunho"


def test_recusar_recuperacao_descarta_o_rascunho():
    with tempfile.TemporaryDirectory() as tmp:
        img = os.path.join(tmp, "pagina.png")
        Image.new("L", (200, 60), color=255).save(img)

        with _App() as app:
            w = app.win
            w.open_image(img)
            w.boxes.append(BoxEntry("Q", 5, 5, 15, 15))
            w._commit_change()
            w.salvar_rascunho_agora()
            sidecar = w.session.sidecar()
            assert _esperar_arquivo(sidecar)

        with _App(responder=False) as app:
            w = app.win
            w.open_image(img)
            assert w.boxes == [], "recuperou mesmo com recusa"
            assert not os.path.exists(sidecar), \
                "o rascunho recusado deveria sumir, para não perguntar de novo"


def test_salvar_de_verdade_some_com_o_rascunho():
    with tempfile.TemporaryDirectory() as tmp:
        img = os.path.join(tmp, "pagina.png")
        Image.new("L", (200, 60), color=255).save(img)

        with _App() as app:
            w = app.win
            w.open_image(img)
            w.boxes.append(BoxEntry("a", 1, 1, 9, 9))
            w._commit_change()
            w.salvar_rascunho_agora()
            sidecar = w.session.sidecar()
            assert _esperar_arquivo(sidecar)

            w._save_box_to_path(os.path.join(tmp, "pagina.box"))

            assert not w.session.is_dirty()
            assert not os.path.exists(sidecar), \
                "trabalho salvo de verdade não precisa de rascunho"


def test_descartar_alteracoes_some_com_o_rascunho():
    """Quem aceitou perder não pode ver o trabalho ressuscitar na próxima
    abertura."""
    with tempfile.TemporaryDirectory() as tmp:
        img1 = os.path.join(tmp, "a.png")
        img2 = os.path.join(tmp, "b.png")
        Image.new("L", (200, 60), color=255).save(img1)
        Image.new("L", (200, 60), color=255).save(img2)

        with _App(responder=True) as app:
            w = app.win
            w.open_image(img1)
            w.boxes.append(BoxEntry("a", 1, 1, 9, 9))
            w._commit_change()
            w.salvar_rascunho_agora()
            sidecar = w.session.sidecar()
            assert _esperar_arquivo(sidecar)

            w.open_image(img2)          # pergunta e o teste responde "sim"

            assert not os.path.exists(sidecar)


def test_rascunho_recuperado_nao_e_sobrescrito_pelo_box():
    """O rascunho é mais recente que o .box em disco."""
    with tempfile.TemporaryDirectory() as tmp:
        img = os.path.join(tmp, "pagina.png")
        Image.new("L", (200, 60), color=255).save(img)

        with _App() as app:
            w = app.win
            w.open_image(img)
            w.boxes.append(BoxEntry("v", 1, 1, 9, 9))
            w._commit_change()
            w._save_box_to_path(os.path.join(tmp, "pagina.box"))   # .box com 'v'

            w.boxes.append(BoxEntry("n", 20, 1, 29, 9))            # trabalho novo
            w._commit_change()
            w.salvar_rascunho_agora()
            assert _esperar_arquivo(w.session.sidecar())

        with _App(responder=True) as app:
            w = app.win
            w.open_image(img)
            assert [b.char for b in w.boxes] == ["v", "n"], \
                "o .box em disco sobrescreveu o rascunho recuperado"


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
