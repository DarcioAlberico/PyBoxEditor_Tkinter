"""A fila de suspeitas ligada à janela principal (2026-09-19).

Três ligações que só a janela principal tem: a imagem da página vem de um
`ProvedorDePaginas` sobre a origem do documento; o diagrama abre no
`DIALOGO_DIAGRAMA` (a costura de teste da F3.6) ao lado do recorte, com a
posição do IR dentro; e "Exportar com as correções" regrava o arquivo da
exportação — o EPUB/DOCX pelas `PaginaExtraida` com a revisão aplicada, os
formatos do IR pelo documento revisado. O FEN revisado **volta** para a
exportação por esse caminho, que é o que o item 2 da lista pediu.
"""

import time
from tkinter import messagebox

import pytest
from PIL import Image

from conftest import raiz_tk
from core.editorial_adapters import paginas_extraidas_para_documento
from core.editorial_pipeline import EditorialPipeline
from ui.dialogo_de_exportacao import OpcoesDeExportacao
from tests.test_fila_de_suspeitas import _pagina, _pdf


class _App:
    def __enter__(self):
        from ui.main_window import MainWindow
        self._info, self._erro, self._sim = (messagebox.showinfo, messagebox.showerror,
                                             messagebox.askyesno)
        self.avisos = []
        messagebox.showinfo = lambda t="", m="", *a, **k: self.avisos.append(m)
        messagebox.showerror = lambda t="", m="", *a, **k: self.avisos.append(m)
        messagebox.askyesno = lambda *a, **k: True
        self.root = raiz_tk()
        if self.root is None:
            pytest.skip("sem display")
        self.win = MainWindow(self.root)
        self.win.image = Image.new("L", (400, 100), color=255)
        # A caixa de conclusão (ED-11) é modal: o dublê põe o relatório em `avisos`.
        self.win.DIALOGO_DE_CONCLUSAO = _conclusao_fixa(self.avisos)
        return self

    def __exit__(self, *a):
        messagebox.showinfo, messagebox.showerror, messagebox.askyesno = (
            self._info, self._erro, self._sim)
        try:
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass


def _conclusao_fixa(avisos):
    class _Caixa:
        def __init__(self, parent, titulo, linhas, caminho, **kw):
            self.texto = "\n".join(list(linhas) + [f"Arquivo salvo em:\n{caminho}"])
            self.abrir_no_editor = kw.get("abrir_no_editor")

        def mostrar(self):
            avisos.append(self.texto)

    return _Caixa


class _Extrator:
    def __init__(self, paginas):
        self.ultimas_paginas = paginas
        self.leitor_de_faixa = "tesseract"


class _Janela:
    """O dublê da janela de revisão: guarda o que a ação lhe passou."""

    instancias = []

    def __init__(self, parent, session, **kw):
        self.session = session
        self.kw = kw
        _Janela.instancias.append(self)

    def bind(self, *a, **k):
        pass

    def mostrar(self):
        return self


def _preparar(app, tmp_path, formato="epub"):
    pdf = _pdf(tmp_path / "livro.pdf", paginas=1)
    paginas = [_pagina(0)]
    paginas[0].dpi = 144
    documento = paginas_extraidas_para_documento(paginas, document_id="livro")
    documento.metadata["source_path"] = str(pdf)
    documento.metadata["review_journal_path"] = str(tmp_path / "saida.review.jsonl")
    app.win.documento_editorial = documento
    app.win.exportacao_editorial = {
        "pipeline": EditorialPipeline(), "extrator": _Extrator(paginas),
        "opcoes": OpcoesDeExportacao(saida=str(tmp_path / f"saida.{formato}"),
                                     formato=formato, diagramas="render"),
        "origem": str(pdf)}
    return documento, paginas


def test_sem_documento_a_revisao_avisa():
    with _App() as app:
        app.win.revisar_documento_editorial_action()
        assert app.avisos and "Processe um documento" in app.avisos[0]


def test_a_acao_liga_a_pagina_o_diagrama_e_a_exportacao(tmp_path, monkeypatch):
    import ui.dialogo_revisao_editorial as modulo
    monkeypatch.setattr(modulo, "DialogoRevisaoEditorial", _Janela)
    _Janela.instancias.clear()
    with _App() as app:
        documento, _paginas = _preparar(app, tmp_path)

        aberturas = []

        class _Diagrama:
            def __init__(self, parent, imagem, leituras, origem=""):
                aberturas.append((imagem.shape, leituras[0].fen(), leituras[0].caixa, origem))

            def mostrar(self):
                return "8/8/8/8/8/8/4k3/4K3 w - - 0 1"

        app.win.DIALOGO_DIAGRAMA = _Diagrama
        app.win.revisar_documento_editorial_action()
        janela = _Janela.instancias[-1]
        assert janela.session.document.document_id == "livro"
        # A imagem vem da origem, na escala em que a página foi lida (144 dpi).
        assert janela.kw["imagem_da_pagina"](0).shape == (400, 600)
        assert janela.kw["imagem_da_pagina"](9) is None
        # O diagrama abre com a posição do IR e a caixa dele na página.
        item = janela.session.queue.filter(kind="diagram").items[0]
        fen = janela.kw["abrir_diagrama"](item, janela.kw["imagem_da_pagina"](0))
        assert fen == "8/8/8/8/8/8/4k3/4K3 w - - 0 1"
        assert aberturas == [((400, 600), "8/8/8/8/8/8/8/8 w - - 0 1", (500, 600, 900, 1000),
                              "livro p1")]
        assert janela.kw["ao_exportar"] == app.win._exportar_documento_revisado


def test_exportar_com_as_correcoes_regrava_o_arquivo_com_o_fen_revisado(tmp_path):
    with _App() as app:
        documento, paginas = _preparar(app, tmp_path, formato="epub")
        from core.editorial_review import ReviewSession
        sessao = ReviewSession(documento)
        sessao.edit("block-livro-p0001-b0003", {"fen": "8/8/8/8/8/8/4k3/4K3 w - - 0 1"})
        sessao.edit("block-livro-p0001-b0000", "Parágrafo revisado à mão.")
        sessao.reject("block-livro-p0001-b0002")

        escritos = []

        def escrever(pipeline, doc, paginas_escritas, opcoes, origem):
            escritos.append((doc, paginas_escritas, opcoes.formato))
            return (opcoes.saida,)

        app.win._escrever_documento_editorial = escrever
        app.win._exportar_documento_revisado(sessao.document)
        limite = time.time() + 10
        while (app.win.task.is_running() or not app.avisos) and time.time() < limite:
            app.root.update()
            time.sleep(0.01)
        assert escritos, "a exportação revisada não escreveu"
        doc, paginas_escritas, formato = escritos[0]
        assert doc is sessao.document and formato == "epub"
        blocos = paginas_escritas[0].blocos
        assert blocos[0].texto == "Parágrafo revisado à mão."
        assert [type(b).__name__ for b in blocos] == ["Paragrafo", "Paragrafo", "Figura", "Figura"]
        assert blocos[2].fen == "8/8/8/8/8/8/4k3/4K3 w - - 0 1" and blocos[2].origem == "render"
        # As páginas do leitor não foram mexidas: a próxima revisão parte delas.
        assert paginas[0].blocos[3].fen is None and len(paginas[0].blocos) == 5
        assert app.win.documento_editorial is sessao.document
        assert any("Eventos de revisão aplicados: 3" in aviso for aviso in app.avisos)


def test_sem_contexto_de_exportacao_a_regravacao_avisa(tmp_path):
    with _App() as app:
        documento, _ = _preparar(app, tmp_path)
        app.win.exportacao_editorial = None
        app.win._exportar_documento_revisado(documento)
        assert any("não veio de uma exportação" in aviso for aviso in app.avisos)


def test_o_diario_de_outro_documento_no_mesmo_caminho_nao_derruba_a_acao(tmp_path, monkeypatch):
    import ui.dialogo_revisao_editorial as modulo
    monkeypatch.setattr(modulo, "DialogoRevisaoEditorial", _Janela)
    _Janela.instancias.clear()
    with _App() as app:
        documento, _ = _preparar(app, tmp_path)
        outro = paginas_extraidas_para_documento([_pagina(0)], document_id="outro")
        from core.editorial_review import ReviewJournal, ReviewSession
        ReviewSession(outro, journal=ReviewJournal(documento.metadata["review_journal_path"])
                      ).accept("block-outro-p0001-b0002")
        app.win.revisar_documento_editorial_action()
        janela = _Janela.instancias[-1]
        assert janela.session.document.review_events == []

