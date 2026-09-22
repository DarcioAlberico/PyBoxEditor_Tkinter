"""
Testes da ponte na janela (ED-11; SPEC_EDITOR §7.2, §10.6.5, DEC-09, DEC-10): "Importar ▸
JSON editorial…" e "Abrir…" com `.json` montam o livro com a ponte ligada; o bloco suspeito
tem a tag `suspeito` e o `!` na calha, e o painel Propriedades mostra a origem, os motivos
e as leituras, com "Marcar como revisto" (AC-ED11-5); salvar grava os eventos no diário e
o relatório diz que o negrito não viaja; o EPUB salvo religa o documento ao reabrir; na
janela principal, "Abrir no editor" depois de exportar monta o livro das páginas, a fila
fica com "Exportar com as correções" desabilitado e o aviso, e a caixa de conclusão da
exportação revisada oferece o editor (AC-ED11-6).

Rodar sem pytest:      .venv/Scripts/python.exe tests/test_editor_ponte.py
"""

import json
import os
import sys
import time
from tkinter import messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from conftest import raiz_tk
from core.editor import modelo as m
from core.editor.projeto import Projeto
from editor_ambiente import Janela
from test_editor_importar_ir import documento_sintetico


def _json(tmp_path, nome="doc.json", document_id="doc"):
    doc = documento_sintetico(document_id)
    doc.metadata["review_journal_path"] = str(tmp_path / "saida.review.jsonl")
    caminho = str(tmp_path / nome)
    doc.save_json(caminho)
    return caminho, doc


def _bloco_por_origem(texto, bloco_id):
    return next(b for b in texto.sincronizar().blocos if b.origem is not None and b.origem.bloco_id == bloco_id)


# ----------------------------------------------------------------------
# AC-ED11-5: o suspeito na tela e no painel
# ----------------------------------------------------------------------

def test_ac5_importar_json_liga_a_ponte_e_marca_os_suspeitos(tmp_path):
    caminho, doc = _json(tmp_path)
    with Janela(abrir=False) as t:
        j = t.j
        projeto = j.executar("importar_json", caminho)
        assert isinstance(projeto, Projeto) and projeto.caminho is None and projeto.sujo
        assert projeto.documento_editorial.document_id == "doc" and projeto.diario == str(tmp_path / "saida.review.jsonl")
        assert projeto.livro.origem.documento_editorial == os.path.abspath(caminho)
        assert len(projeto.livro.capitulos) == 2 and j.aba_ativa().arquivo == "Text/cap-0001.xhtml"
        texto = t.texto
        suspeitos = texto.suspeitos()
        assert len(suspeitos) == 2
        for bloco_id in suspeitos:
            assert texto.calha.icone_de(bloco_id) == "suspeito"
        par = _bloco_por_origem(texto, "block-doc-p0002-b0003")
        ini, fim = texto.indice_de(par.id, 0), texto.indice_de(par.id, len("Suspeito por motor."))
        assert "suspeito" in texto.texto.tag_names(ini) and "suspeito" in texto.texto.tag_names(f"{fim}-1c")
        assert texto.texto.tag_cget("suspeito", "background") == "#fff3a0"
        # o painel Propriedades: origem, motivos, leituras e o botão
        texto.ir_para(par.id, 3)
        j.painel_de_propriedades.atualizar(forcar=True)
        rotulos = [w.cget("text") for w in j.painel_de_propriedades.corpo.winfo_children()
                   if isinstance(w, __import__("tkinter").ttk.Label)]
        assert "Origem:" in rotulos and any("página 2, bloco block-doc-p0002-b0003" in r for r in rotulos)
        assert "Suspeito:" in rotulos and any("o motor de prosa faltou" in r for r in rotulos)
        leituras = j.painel_de_propriedades.caixa_de_leituras.get("1.0", "end").strip().splitlines()
        assert leituras[0] == "Suspeito por motor." and any("âncora da cadeia própria: Suspeito p0r m0tor." in li
                                                            for li in leituras)
        assert any("linha do motor de prosa" in li for li in leituras) and any("motivos:" in li for li in leituras)
        assert j.painel_de_propriedades.botao_acao.cget("text") == "Marcar como revisto"
        assert j.descrever_suspeita(par) == (["o motor de prosa faltou"], leituras)
        # "Marcar como revisto": o data-suspeito sai, a tag e o ! também; desfazer traz de volta
        j.painel_de_propriedades.acao("limpar_suspeita")
        par = texto.modelo_de(par.id)
        assert "data-suspeito" not in par.extras and texto.calha.icone_de(par.id) is None
        assert "suspeito" not in texto.texto.tag_names(texto.indice_de(par.id, 0))
        assert texto.suspeitos() == [_bloco_por_origem(texto, "block-doc-p0002-b0000").id]
        assert j.executar("desfazer")
        assert texto.modelo_de(par.id).extras.get("data-suspeito") == "motor_indisponivel"
        assert texto.calha.icone_de(par.id) == "suspeito"
        # a figura suspeita (sem posição) tem o aviso como título e os códigos como motivo sem documento
        fig = _bloco_por_origem(texto, "block-doc-p0002-b0000")
        assert isinstance(fig, m.Figura) and fig.extras["title"] == "ocupação a 0,71"
        motivos, leituras_fig = j.descrever_suspeita(fig)
        assert motivos == ["o porteiro não confiou no tabuleiro: ocupação a 0,71"] and leituras_fig == []
        # o bloco sem origem no painel não mostra origem
        texto.ir_para(texto.ordem[1], 0)
        j.painel_de_propriedades.atualizar(forcar=True)
        rotulos = [w.cget("text") for w in j.painel_de_propriedades.corpo.winfo_children()
                   if isinstance(w, __import__("tkinter").ttk.Label)]
        assert "Origem:" in rotulos and "Suspeito:" not in rotulos           # o título tem origem, mas não é suspeito
        # o que não é JSON editorial
        (tmp_path / "x.json").write_text('{"a": 1}', encoding="utf-8")
        j.executar("importar_json", str(tmp_path / "x.json"))
        assert "não é um documento editorial" in t.caixas.entradas()[-1]


def test_abrir_com_json_e_o_caminho_do_abrir(tmp_path):
    caminho, _doc = _json(tmp_path)
    with Janela(abrir=False) as t:
        j = t.j
        projeto = j.executar("abrir", caminho)
        assert projeto is j.projeto and projeto.documento_editorial is not None
        t.caixas.pergunta_resposta = False                                     # descartar o sujo e abrir de novo
        assert j.executar("abrir_documento_editorial", projeto.documento_editorial, "") is not None
        assert j.projeto is not projeto and j.projeto.documento_editorial is projeto.documento_editorial


# ----------------------------------------------------------------------
# Salvar: os eventos, o relatório, o EPUB que religa
# ----------------------------------------------------------------------

def test_salvar_grava_os_eventos_e_o_epub_religa_o_documento(tmp_path):
    caminho, doc = _json(tmp_path)
    diario = str(tmp_path / "saida.review.jsonl")
    with Janela(abrir=False) as t:
        j = t.j
        j.executar("importar_json", caminho)
        texto = t.texto
        par = _bloco_por_origem(texto, "block-doc-p0001-b0001")
        texto.selecionar(0, len("Texto"), par.id)
        texto.apagar_selecao()
        texto.inserir("Trecho")                                              # edita um bloco com negrito
        texto.ir_para(par.id, 0)
        fim = _bloco_por_origem(texto, "block-doc-p0002-b0002")
        texto.selecionar_bloco() if False else None
        texto.ir_para(fim.id, 0)
        texto.selecionar(0, len("coisa estranha"), fim.id)
        texto.apagar_selecao()
        texto.inserir("outra coisa")
        destino = str(tmp_path / "livro.epub")
        relatorio = j.executar("salvar_como", destino)
        ponte = j.projeto.ponte
        assert ponte is not None and ponte.eventos == 2 and ponte.editados == 2 and ponte.diario == diario
        assert any("não viaja" in a for a in relatorio.avisos) and relatorio.metadados["ponte"]["eventos"] == 2
        assert "ponte: 2 evento(s)" in j.campos["aviso"].cget("text")
        eventos = [json.loads(li) for li in open(diario, encoding="utf-8").read().splitlines() if li.strip()]
        assert [(e["target_id"], e["after"]) for e in eventos] == [("block-doc-p0001-b0001", "Trecho com negrito no meio."),
                                                                   ("block-doc-p0002-b0002", "outra coisa")]
        assert j.projeto.documento_editorial.review_events and j.projeto.livro.origem.diario == diario
        assert not j.projeto.sujo
        # salvar de novo sem mudar: nenhum evento a mais
        j.executar("salvar")
        assert j.projeto.ponte.eventos == 0 and len(open(diario, encoding="utf-8").read().splitlines()) == 2
        # editar de volta e salvar: o segundo evento, com before = after do primeiro
        par = texto.modelo_de(par.id)
        texto.selecionar(0, len("Trecho"), par.id)
        texto.apagar_selecao()
        texto.inserir("Texto")
        j.executar("salvar")
        eventos = [json.loads(li) for li in open(diario, encoding="utf-8").read().splitlines() if li.strip()]
        assert len(eventos) == 3 and eventos[-1]["before"] == "Trecho com negrito no meio."
        assert eventos[-1]["after"] == "Texto com negrito no meio."
    # o EPUB salvo aponta para o JSON: reabrir religa a ponte e o diário continua o mesmo
    projeto = Projeto.abrir(destino)
    assert projeto.documento_editorial is not None and projeto.documento_editorial.document_id == "doc"
    assert projeto.diario == diario and projeto.livro.origem.documento_editorial == os.path.abspath(caminho)
    # a suspeita e a origem sobreviveram ao EPUB
    cap = projeto.livro.capitulos[0]
    assert any(b.extras.get("data-suspeito") == "motor_indisponivel" for b in cap.blocos)
    # sem o JSON no lugar, a ponte fica desligada sem erro
    os.remove(caminho)
    projeto2 = Projeto.abrir(destino)
    assert projeto2.documento_editorial is None and projeto2.salvar_como(str(tmp_path / "solto.epub")).capitulos == 2


# ----------------------------------------------------------------------
# AC-ED11-6: a janela principal
# ----------------------------------------------------------------------

class _App:
    def __enter__(self):
        from ui.main_window import MainWindow

        self._info, self._erro, self._sim = messagebox.showinfo, messagebox.showerror, messagebox.askyesno
        self.avisos = []
        messagebox.showinfo = lambda t="", m="", *a, **k: self.avisos.append(m)
        messagebox.showerror = lambda t="", m="", *a, **k: self.avisos.append(m)
        messagebox.askyesno = lambda *a, **k: True
        self.root = raiz_tk()
        if self.root is None:
            pytest.skip("sem display")
        self.win = MainWindow(self.root)
        return self

    def __exit__(self, *a):
        messagebox.showinfo, messagebox.showerror, messagebox.askyesno = self._info, self._erro, self._sim
        try:
            if self.win.editor is not None and self.win.editor.winfo_exists():
                self.win.editor.destroy()
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass


class _Conclusao:
    """O dublê da caixa de conclusão: guarda as linhas e a ação "Abrir no editor" para o teste chamar."""

    instancias = []

    def __init__(self, parent, titulo, linhas, caminho, acoes=(), abrir_no_editor=None):
        self.titulo, self.linhas, self.caminho, self.abrir_no_editor = titulo, list(linhas), caminho, abrir_no_editor
        _Conclusao.instancias.append(self)

    def mostrar(self):
        return None


class _Fila:
    instancias = []

    def __init__(self, parent, session, **kw):
        self.session, self.kw = session, kw
        _Fila.instancias.append(self)

    def bind(self, *a, **k):
        pass

    def mostrar(self):
        return self


def test_ac6_abrir_no_editor_apos_exportar_monta_das_paginas_e_a_fila_fica_desabilitada(tmp_path, monkeypatch):
    import ui.dialogo_revisao_editorial as modulo

    monkeypatch.setattr(modulo, "DialogoRevisaoEditorial", _Fila)
    _Fila.instancias.clear()
    _Conclusao.instancias.clear()
    from core.editorial_pipeline import EditorialPipeline
    from ui.dialogo_de_exportacao import OpcoesDeExportacao
    from test_fila_de_suspeitas import _pagina, _pdf

    with _App() as app:
        pdf = _pdf(tmp_path / "livro.pdf", paginas=1)
        paginas = [_pagina(0)]
        paginas[0].dpi = 144
        from core.editorial_adapters import paginas_extraidas_para_documento

        documento = paginas_extraidas_para_documento(paginas, document_id="livro")
        documento.metadata["source_path"] = str(pdf)
        documento.metadata["review_journal_path"] = str(tmp_path / "saida.review.jsonl")
        saida = str(tmp_path / "saida.docx")
        app.win.documento_editorial = documento
        app.win.exportacao_editorial = {"pipeline": EditorialPipeline(), "extrator": type("E", (), {
            "ultimas_paginas": paginas, "leitor_de_faixa": "tesseract"})(),
            "opcoes": OpcoesDeExportacao(saida=saida, formato="docx", diagramas="render"), "origem": str(pdf)}
        app.win.DIALOGO_DE_CONCLUSAO = _Conclusao
        # a fila, antes do editor: exporta normalmente
        app.win.revisar_documento_editorial_action()
        assert _Fila.instancias[-1].kw["aviso_da_exportacao"] == ""
        assert _Fila.instancias[-1].kw["ao_exportar"] == app.win._exportar_documento_revisado
        # a exportação revisada termina na caixa de conclusão com "Abrir no editor"
        app.win._escrever_documento_editorial = lambda pipeline, doc, paginas_, opcoes, origem: (opcoes.saida,)
        app.win._exportar_documento_revisado(documento)
        limite = time.time() + 15
        while (app.win.task.is_running() or not _Conclusao.instancias) and time.time() < limite:
            app.root.update()
            time.sleep(0.01)
        caixa = _Conclusao.instancias[-1]
        assert caixa.titulo == "Exportação concluída" and caixa.caminho == saida and caixa.abrir_no_editor is not None
        assert caixa.linhas == ["Eventos de revisão aplicados: 0"]
        # "Abrir no editor" monta o livro das páginas (o DOCX não vira caminho do projeto)
        editor = caixa.abrir_no_editor(saida)
        assert editor is app.win.editor and editor.winfo_exists()
        projeto = editor.projeto
        assert projeto.caminho is None and projeto.documento_editorial is documento
        assert projeto.diario == str(tmp_path / "saida.review.jsonl")
        blocos = projeto.livro.capitulos[0].blocos
        assert [type(b).__name__ for b in blocos] == ["MarcaDePagina", "Paragrafo", "Paragrafo", "Tabela", "Figura",
                                                     "Diagrama"]
        assert blocos[1].origem.bloco_id == "block-livro-p0001-b0000" and blocos[1].extras.get("data-suspeito")
        assert blocos[5].lado == "" and blocos[5].posicao == "8/8/8/8/8/8/8/4K2k"
        # com o editor aberto sobre o documento, a fila não exporta: o botão fica desabilitado com o aviso
        app.win.revisar_documento_editorial_action()
        fila = _Fila.instancias[-1]
        assert fila.kw["aviso_da_exportacao"] == "o livro está no editor; exporte por ele"
        assert fila.kw["ao_exportar"] == app.win._exportar_documento_revisado
        # o negrito editado não viaja, e o relatório ao salvar o diz
        texto = editor.aba_ativa().widget
        par = blocos[1]
        texto.selecionar(0, len("25♖xc7!"), par.id)
        texto.alternar("negrito")
        texto.selecionar(0, 2, par.id)
        texto.apagar_selecao()
        texto.inserir("26")
        relatorio = editor.executar("salvar_como", str(tmp_path / "editado.epub"))
        assert editor.projeto.ponte.eventos == 1 and any("não viaja" in a for a in relatorio.avisos)
        eventos = [json.loads(li) for li in open(tmp_path / "saida.review.jsonl", encoding="utf-8").read().splitlines()]
        assert eventos[0]["after"].startswith("26♖xc7!") and "<" not in eventos[0]["after"]
        # um EPUB exportado vira o caminho do projeto
        editor.executar("fechar_livro")
        outro = app.win.abrir_editor_de_livro(str(tmp_path / "saida.epub"), documento=documento)
        assert outro is editor and editor.projeto.caminho == str(tmp_path / "saida.epub") and not editor.projeto.sujo
        # sem editor sobre o documento (outro documento), a fila volta a exportar
        editor.executar("fechar_livro")
        app.win.revisar_documento_editorial_action()
        assert _Fila.instancias[-1].kw["aviso_da_exportacao"] == ""


def test_a_fila_de_verdade_desabilita_o_botao_com_o_aviso(monkeypatch):
    import ui.dialogo_revisao_editorial as modulo
    from core.editorial_review import ReviewSession
    from ui.dialogo_revisao_editorial import DialogoRevisaoEditorial

    avisos = []
    monkeypatch.setattr(modulo.messagebox, "showinfo", lambda t="", m="", *a, **k: avisos.append(m))
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        sessao = ReviewSession(documento_sintetico())
        chamadas = []
        janela = DialogoRevisaoEditorial(raiz, sessao, ao_exportar=chamadas.append,
                                         aviso_da_exportacao="o livro está no editor; exporte por ele")
        assert janela.btn_exportar.instate(["disabled"]) and "exporte por ele" in janela.lbl_exportacao.cget("text")
        janela._exportar()
        assert chamadas == [] and avisos == ["o livro está no editor; exporte por ele"]
        janela.destroy()
        janela2 = DialogoRevisaoEditorial(raiz, sessao, ao_exportar=chamadas.append)
        assert not janela2.btn_exportar.instate(["disabled"]) and not hasattr(janela2, "lbl_exportacao")
        janela2._exportar()
        assert chamadas == [sessao.document]
        janela2.destroy()
    finally:
        raiz.destroy()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
