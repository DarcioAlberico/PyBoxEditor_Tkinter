"""O rascunho não some antes da hora (RG-05, R-04).

- "Descartar" ao abrir outro arquivo apagava o rascunho antes do seletor: cancelar o
  seletor (ou um PDF que não abre) deixava o trabalho na tela e nenhum rascunho dele.
- A falha do gravador do rascunho só passava pela barra de status, sobrescrita logo; a de
  `remover_autosave` ia ao log em DEBUG, e o rascunho velho voltava como "recuperar".
- A página da qual se apagaram todos os boxes não contava como suja nem entrava no
  rascunho: "Nada para salvar", o `.box` antigo ficava, e o rascunho velho voltava a
  oferecer os boxes apagados.
- No editor, o `OSError` do rascunho ao fechar pela janela principal impedia o
  fechamento; e o rascunho era oferecido só com a hora, mesmo mais velho que o EPUB.
"""

import logging
import os
import tempfile
import time

from tkinter import filedialog, messagebox

from PIL import Image

from core import formato_box
from core.box_model import BoxEntry
from core.services import document_service
from core.services.document_service import DocumentSession, _GravadorAssincrono
from tests.test_trabalho_fora_da_interface import _App


def _imagem(caminho):
    Image.new("L", (120, 60), 255).save(caminho)
    return caminho


def _sessao_suja_com_rascunho(app, caminho):
    app.win.open_image(caminho)
    app.win.boxes.append(BoxEntry("a", 10, 10, 20, 30))
    app.win._commit_change()
    rascunho = app.win.session.sidecar()
    with open(rascunho, "w", encoding="utf-8") as f:
        f.write("{}")
    return rascunho


def test_cancelar_o_seletor_depois_de_descartar_mantem_o_rascunho(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        rascunho = _sessao_suja_com_rascunho(app, _imagem(os.path.join(tmp, "a.png")))
        monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)        # "Descartar"
        monkeypatch.setattr(app.win, "_perguntar_entrada", lambda *a, **k: "")   # cancela o seletor
        app.win.open_image()
        assert os.path.exists(rascunho), "o rascunho sumiu sem outro arquivo aberto"
        app.win.open_pdf(os.path.join(tmp, "nao_existe.pdf"))                    # o PDF não abre
        assert os.path.exists(rascunho), "o rascunho sumiu com um PDF que não abriu"

        app.win.open_image(_imagem(os.path.join(tmp, "b.png")))                 # agora abre
        assert not os.path.exists(rascunho), "o descarte escolhido não aconteceu"


def test_fechar_a_janela_com_descartar_apaga_o_rascunho(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        rascunho = _sessao_suja_com_rascunho(app, _imagem(os.path.join(tmp, "a.png")))
        monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
        monkeypatch.setattr(app.win, "gravar_estado_da_janela", lambda: None)
        app.win._on_close()
        assert not os.path.exists(rascunho)


def test_a_falha_do_gravador_vai_ao_log_e_ao_titulo(monkeypatch, caplog, tmp_path):
    import core.escrita_atomica as ea

    def falha(*a, **k):
        raise OSError(28, "Não há espaço no disco")

    monkeypatch.setattr(ea, "escrita_atomica", falha)
    gravador = _GravadorAssincrono()
    with caplog.at_level(logging.WARNING):
        gravador.agendar(str(tmp_path / "x.pyboxsession.json"), {"a": 1})
        gravador._thread.join(5)
    assert isinstance(gravador.ultimo_erro, OSError)
    assert any("rascunho" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)

    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        app.win.open_image(_imagem(os.path.join(tmp, "a.png")))
        app.win._gravador._erro = OSError(28, "Não há espaço no disco")
        app.win._update_title()
        assert "rascunho não gravado" in app.root.title()
        app.win._gravador._erro = None
        app.win._update_title()
        assert "rascunho" not in app.root.title()


def test_a_falha_de_remover_o_rascunho_vai_ao_log_em_warning(monkeypatch, caplog, tmp_path):
    sessao = DocumentSession(str(tmp_path / "a.png"), num_pages=1, is_pdf=False)
    with caplog.at_level(logging.DEBUG):
        sessao.remover_autosave()                       # não existe: nada a dizer
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    def preso(caminho):
        raise PermissionError(13, "Acesso negado", caminho)

    monkeypatch.setattr(document_service.os, "remove", preso)
    with caplog.at_level(logging.WARNING):
        sessao.remover_autosave()
    assert any(r.levelno == logging.WARNING and "rascunho" in r.getMessage() for r in caplog.records)


def test_a_pagina_esvaziada_conta_como_suja_e_salva_vazia(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp, _App() as app:
        imagem = _imagem(os.path.join(tmp, "pagina.png"))
        box = os.path.join(tmp, "pagina.box")
        formato_box.escrever(box, [BoxEntry("a", 10, 10, 20, 30)], 60)
        app.win.open_image(imagem)
        assert len(app.win.boxes) == 1
        app.win.boxes.clear()
        app.win._commit_change()
        assert app.win.session.is_dirty(), "a página esvaziada não conta como suja"
        assert app.win.session.montar_payload()["paginas"] == {"0": []}, \
            "a página esvaziada não entra no rascunho"

        monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **k: box)
        app.win.save_box_file()
        app.aguardar()
        assert not any(c[2] == "Nada para salvar." for c in app.caixas)
        assert formato_box.ler(box, 60) == [], "o .box antigo ficou"
        assert not app.win.session.is_dirty()


def test_o_rascunho_da_pagina_esvaziada_volta_vazio(tmp_path):
    sessao = DocumentSession(str(tmp_path / "livro.pdf"), num_pages=3, is_pdf=True)
    sessao.store(1, [BoxEntry("a", 0, 0, 5, 5)])
    sessao.store(1, [])
    sessao.mark_dirty(1)
    payload = sessao.montar_payload()
    outra = DocumentSession(str(tmp_path / "livro.pdf"), num_pages=3, is_pdf=True)
    outra.store(1, [BoxEntry("velho", 0, 0, 5, 5)])                  # o que veio do `.box`
    outra.aplicar_payload(payload)
    assert outra.boxes_for(1) == [] and outra.dirty_pages() == [1]


# ---------------------------------------------------------------------------
# O editor
# ---------------------------------------------------------------------------

def test_o_rascunho_que_nao_grava_nao_impede_fechar_o_editor(caplog):
    from tests.test_editor_janela import _Janela

    with _Janela() as t:
        j = t.j
        j.aba_ativa().widget.inserir("mudança ")
        fechados = []
        t.raiz.protocol("WM_DELETE_WINDOW", lambda: fechados.append("parent"))
        j._instalar_guarda_no_parent()

        def falha():
            raise OSError(28, "Não há espaço no disco")

        j.rascunho.gravar = falha
        t.caixas.pergunta_resposta = False                               # não salvar
        with caplog.at_level(logging.WARNING):
            t.raiz.tk.eval(t.raiz.protocol("WM_DELETE_WINDOW"))
        assert fechados == ["parent"] and not j.winfo_exists(), "o OSError do rascunho prendeu o editor"
        assert any("rascunho" in r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)


def test_o_rascunho_mais_velho_que_o_livro_e_oferecido_com_aviso():
    from tests.test_editor_janela import _Janela

    with _Janela() as t:
        j = t.j
        j.aba_ativa().widget.inserir("rascunho ")
        j.rascunho.gravar()
        rascunho = j.rascunho.ultimo_caminho
        pasta, caminho = t.pasta, t.epub
        j.destroy()
    agora = time.time()
    os.utime(rascunho, (agora - 600, agora - 600))
    os.utime(caminho, (agora, agora))                                     # editado por fora depois
    with _Janela(abrir=False, pasta=pasta) as t:
        t.caixas.pergunta_resposta = False
        t.j.executar("abrir", caminho)
        pergunta = [c for c in t.caixas.chamadas if c[0] == "pergunta"][-1][1]
        assert "mais novo" in pergunta, "o rascunho velho foi oferecido sem aviso"

    with _Janela() as t:                                                  # o rascunho recente: sem aviso
        t.j.aba_ativa().widget.inserir("x")
        t.j.rascunho.gravar()
        pasta, caminho = t.pasta, t.epub
        t.j.destroy()
    with _Janela(abrir=False, pasta=pasta) as t:
        t.caixas.pergunta_resposta = False
        t.j.executar("abrir", caminho)
        pergunta = [c for c in t.caixas.chamadas if c[0] == "pergunta"][-1][1]
        assert "mais novo" not in pergunta
