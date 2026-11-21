"""Diálogo que dispara tarefa religa em todo desfecho (RG-13, R-16).

- A rotulagem: o pré-OCR não tinha `ao_falhar` nem `ao_cancelar` (o botão ficava preso em
  "Lendo linhas…"), fechar no meio não cancelava e o `concluir` tocava widget destruído, e
  a troca de página recusada deixava `_pagina_rodando` presa.
- A revisão editorial é modal (`grab_set`): o Cancelar da barra de status da janela fica
  atrás dela, e a exportação que ela dispara não tinha como ser cancelada.
- A caixa de conclusão não fechava se a ação levantava.
"""

import pytest
from PIL import Image

from conftest import raiz_tk
from core.box_model import BoxEntry


class _Tarefa:
    def __init__(self):
        self.rodando = False
        self.cancelada = False

    def is_running(self):
        return self.rodando

    def cancel(self):
        self.cancelada = True


class _App:
    """O que a rotulagem pede da janela; `_run_task` guarda os callbacks para o teste."""

    def __init__(self, raiz, aceitar=True):
        self.parent = raiz
        self.image = Image.new("L", (200, 80), 255)
        self.boxes = [BoxEntry("a", 10, 10, 20, 30), BoxEntry("b", 22, 10, 30, 30)]
        self.current_pdf_page = 0
        self.pdf_service = type("PDF", (), {"is_loaded": lambda self: False})()
        self.task = _Tarefa()
        self.aceitar = aceitar
        self.chamadas = []

    def _run_task(self, titulo, trabalho, concluir, ao_cancelar=None, indeterminado=False, ao_falhar=None):
        self.chamadas.append({"concluir": concluir, "ao_falhar": ao_falhar, "ao_cancelar": ao_cancelar})
        if self.aceitar:
            self.task.rodando = True
        return self.aceitar


def _dialogo(raiz, **k):
    from ui.dialogo_rotulagem import DialogoRotulagem

    app = _App(raiz, **k)
    dialogo = DialogoRotulagem(app)
    dialogo.withdraw()
    dialogo._linhas = [list(app.boxes)]
    dialogo._pos = 0
    return app, dialogo


@pytest.fixture
def raiz():
    r = raiz_tk()
    if r is None:
        pytest.skip("sem display")
    yield r
    r.destroy()


@pytest.mark.parametrize("desfecho", ["falha", "cancelamento", "recusa"])
def test_o_pre_ocr_religa_em_todo_desfecho(raiz, desfecho):
    app, dialogo = _dialogo(raiz, aceitar=desfecho != "recusa")
    dialogo._pre_ocr()
    if desfecho == "falha":
        assert app.chamadas[-1]["ao_falhar"] is not None, "o pré-OCR não tem ao_falhar"
        app.task.rodando = False
        app.chamadas[-1]["ao_falhar"](RuntimeError("o motor caiu"))
    elif desfecho == "cancelamento":
        assert app.chamadas[-1]["ao_cancelar"] is not None, "o pré-OCR não tem ao_cancelar"
        app.task.rodando = False
        app.chamadas[-1]["ao_cancelar"]()
    assert not dialogo._ocr_rodando and str(dialogo.btn_ocr.cget("state")) == "normal"
    assert dialogo.btn_ocr.cget("text") == "Executar", "o botão ficou preso em 'Lendo linhas…'"
    dialogo.destroy()


def test_fechar_no_meio_cancela_e_o_concluir_nao_toca_o_que_morreu(raiz, monkeypatch):
    from tkinter import messagebox

    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: False)
    app, dialogo = _dialogo(raiz)
    dialogo._pre_ocr()
    concluir = app.chamadas[-1]["concluir"]
    dialogo._fechar()
    assert app.task.cancelada, "fechar o diálogo no meio não cancelou a tarefa"
    concluir([("texto", 0.9)])                    # chega depois do fechamento: não levanta


def test_a_troca_de_pagina_recusada_solta_a_bandeira(raiz):
    app, dialogo = _dialogo(raiz)
    app._load_pdf_page = lambda *a, **k: None       # a janela recusou (outra coisa rodando)
    app._total = 3
    dialogo._total_paginas = lambda: 3
    dialogo._resolver_pendente = lambda: True
    dialogo._salvar_dataset = lambda: None
    dialogo._trocar_pagina(1)
    assert not dialogo._pagina_rodando, "a página recusada deixou a navegação presa"
    dialogo.destroy()


def test_a_revisao_modal_tem_o_proprio_cancelar(raiz):
    from core.editorial_model import Decision, EditorialBlock, EditorialDocument, EditorialPage, SourceRef
    from core.editorial_review import ReviewSession
    from ui.dialogo_revisao_editorial import DialogoRevisaoEditorial

    ref = SourceRef("doc", 0)
    bloco = EditorialBlock(id="b0", kind="paragraph", order=0, source_refs=[ref],
                           decision=Decision("texto", [], "unresolved", ["legacy_adapter"]))
    sessao = ReviewSession(EditorialDocument("doc", "Doc", "pt", [EditorialPage("p1", 0, [ref], [bloco], [])]))
    tarefa = _Tarefa()
    tarefa.rodando = True
    dialogo = DialogoRevisaoEditorial(raiz, sessao, ao_exportar=lambda doc: None,
                                      ao_cancelar_tarefa=tarefa.cancel, tarefa_rodando=tarefa.is_running)
    dialogo.withdraw()
    assert "Cancelar operação" in dialogo.botoes, "a revisão modal não tem como cancelar a tarefa"
    dialogo.botoes["Cancelar operação"].invoke()
    assert tarefa.cancelada
    tarefa.cancelada = False
    dialogo._fechar()                               # fechar no meio cancela também
    assert tarefa.cancelada


def test_a_conclusao_fecha_mesmo_quando_a_acao_levanta(raiz, tmp_path):
    from ui.dialogo_de_conclusao import DialogoDeConclusao

    def quebra(caminho):
        raise OSError("o arquivo sumiu")

    caixa = DialogoDeConclusao(raiz, "Livro exportado", [], str(tmp_path / "x.epub"), acoes=[("Quebra", quebra)])
    caixa.construir().withdraw()
    with pytest.raises(OSError):
        caixa.invocar("Quebra")
    assert caixa.top is None, "a caixa ficou aberta (com grab) depois da ação que levantou"
