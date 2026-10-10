"""As caixas de verdade do editor (`ui/editor/dialogos.py`), construídas sem `mostrar()`.

A medição de cobertura de 2026-10-06 (item 7 da análise geral) achou o módulo em 26%: a
suíte inteira troca as caixas por falsas (`editor_ambiente.Caixas`) para nunca esperar um
clique, e as reais — o formulário, a lista, o texto longo, a falha, o parágrafo, as caixas
de marcar, os marcos — nunca abriam. Elas foram feitas para isto: `construir()` monta o
`Toplevel` sem `wait_window`, os widgets ficam em atributos, e `confirmar()` lê e fecha. A
fachada `Caixas` é testada com o `messagebox` e o `filedialog` trocados: o que se confere
é o que ela passa a eles e o que devolve.
"""
import tkinter as tk

import pytest

from conftest import raiz_tk
from ui.editor import dialogos as d


@pytest.fixture
def raiz():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    yield raiz
    try:
        raiz.destroy()
    except tk.TclError:
        pass


def test_o_formulario_devolve_os_campos_editados_e_cancelar_devolve_nada(raiz):
    caixa = d.DialogoDeFormulario(raiz, "Metadados", [("titulo", "Título:", "Antes"), ("idioma", "Idioma:", "pt")],
                                  opcoes={"idioma": ["pt", "en"]}, texto="Preencha o livro.")
    top = caixa.construir()
    assert caixa.construir() is top, "construir de novo não abre outra janela"
    assert isinstance(caixa.entradas["idioma"], d.ttk.Combobox)
    caixa._foco_inicial()
    caixa.variaveis["titulo"].set("Depois")
    assert caixa.confirmar() == {"titulo": "Depois", "idioma": "pt"}
    assert caixa.top is None

    outra = d.DialogoDeFormulario(raiz, "Metadados", [("titulo", "Título:", "x")])
    outra.construir()
    outra.cancelar()
    assert outra.resultado is None and outra.top is None


def test_a_lista_comeca_no_primeiro_e_devolve_o_indice_escolhido(raiz):
    caixa = d.DialogoDeLista(raiz, "Capítulos", "Qual?", ["um", "dois", "três"], ok="Ir")
    caixa.construir()
    caixa._foco_inicial()
    assert caixa._ler() == 0
    caixa.escolher(2)
    assert caixa.confirmar() == 2

    vazia = d.DialogoDeLista(raiz, "Nada", "Qual?", [])
    vazia.construir()
    assert vazia.confirmar() is None


def test_o_texto_longo_e_so_de_leitura_e_fechar_confirma(raiz):
    caixa = d.DialogoDeTexto(raiz, "Atalhos", "Ctrl+S salva\nCtrl+Q sai", monoespaco=True)
    caixa.construir()
    caixa._foco_inicial()
    assert caixa.caixa.get("1.0", "end-1c") == "Ctrl+S salva\nCtrl+Q sai"
    assert str(caixa.caixa.cget("state")) == "disabled"
    caixa.copiar()
    assert caixa.confirmar() is True

    prosa = d.DialogoDeTexto(raiz, "Dialeto", "texto corrido", monoespaco=False)
    prosa.construir()
    assert str(prosa.caixa.cget("wrap")) == "word"
    prosa.cancelar()


def test_a_falha_dobra_os_detalhes_e_copia_mensagem_e_traceback(raiz):
    caixa = d.DialogoDeFalha(raiz, "a exportação caiu", "Traceback (most recent call last):\n  ZeroDivisionError")
    caixa.construir()
    caixa._foco_inicial()
    assert not caixa.detalhes_abertos and not caixa.caixa.winfo_manager()
    assert caixa.alternar_detalhes() is True
    assert caixa.caixa.winfo_manager() == "grid"
    assert caixa.alternar_detalhes() is False
    assert caixa.copiar() == "a exportação caiu\n\nTraceback (most recent call last):\n  ZeroDivisionError"
    assert caixa.confirmar() is True


def test_o_paragrafo_devolve_so_o_que_mudou_e_recusa_numero_torto(raiz):
    caixa = d.DialogoDeParagrafo(raiz, {"alinhamento": "", "recuo_primeira_em": 1.5})
    caixa.construir()
    caixa._foco_inicial()
    assert caixa.variaveis["recuo_primeira_em"].get() == "1.5"
    caixa.variaveis["alinhamento"].set("centro")
    caixa.variaveis["antes_em"].set("0,5")
    assert caixa.confirmar() == {"alinhamento": "centro", "antes_em": 0.5}

    torta = d.DialogoDeParagrafo(raiz)
    torta.construir()
    torta.variaveis["depois_em"].set("muito")
    with pytest.raises(ValueError, match="depois_em"):
        torta.confirmar()
    torta.cancelar()
    assert d._numero(None) == "" and d._numero(2) == "2" and d._numero("1.50") == "1.5"


def test_marcar_varios_devolve_os_indices_marcados(raiz):
    caixa = d.DialogoDeMarcarVarios(raiz, "Folhas", "Quais vincular?", ["a.css", "b.css", "c.css"], marcadas=(1,))
    caixa.construir()
    assert caixa._ler() == [1]
    caixa.marcar(0)
    assert caixa._ler() == [0, 1]
    caixa.marcar_todas(False)
    assert caixa._ler() == []
    caixa.marcar_todas(True)
    assert caixa.confirmar() == [0, 1, 2]


def test_os_marcos_se_definem_trocam_e_tiram_e_a_arvore_acompanha(raiz):
    caixa = d.DialogoDeMarcos(raiz, [("toc", "nav.xhtml")], [("toc", "Sumário"), ("cover", "Capa")],
                              ["nav.xhtml", "capa.xhtml"])
    caixa.construir()
    assert len(caixa.arvore.get_children()) == 1
    caixa.definir("cover", "capa.xhtml")
    caixa.definir("toc", "sumario.xhtml")
    assert caixa.marcos == [("cover", "capa.xhtml"), ("toc", "sumario.xhtml")]
    assert len(caixa.arvore.get_children()) == 2
    caixa.var_tipo.set("bodymatter")
    caixa.var_destino.set("cap1.xhtml")
    caixa._definir()
    assert ("bodymatter", "cap1.xhtml") in caixa.marcos
    assert caixa.tirar("toc") is True and caixa.tirar("toc") is False
    caixa.arvore.selection_set("0")
    caixa._tirar()
    assert caixa.marcos == [("bodymatter", "cap1.xhtml")]
    with pytest.raises(ValueError):
        caixa.definir("", "x")
    assert caixa.confirmar() == [("bodymatter", "cap1.xhtml")]


class _Fake:
    """Uma caixa falsa que anota o que recebeu e devolve o combinado."""

    instancias: list = []
    resposta = "ok"

    def __init__(self, *args, **kw):
        self.args, self.kw = args, kw
        _Fake.instancias.append(self)

    def mostrar(self):
        return _Fake.resposta


def test_a_fachada_passa_ao_messagebox_e_ao_filedialog_o_que_recebeu(raiz, monkeypatch):
    chamadas = []

    def anotar(nome, retorno):
        def funcao(*args, **kw):
            chamadas.append((nome, args, kw))
            return retorno
        return funcao

    monkeypatch.setattr(d.messagebox, "showwarning", anotar("showwarning", None))
    monkeypatch.setattr(d.messagebox, "showinfo", anotar("showinfo", None))
    monkeypatch.setattr(d.messagebox, "askyesnocancel", anotar("askyesnocancel", None))
    monkeypatch.setattr(d.messagebox, "askyesno", anotar("askyesno", 1))
    monkeypatch.setattr(d.filedialog, "askopenfilename", anotar("askopenfilename", ""))
    monkeypatch.setattr(d.filedialog, "asksaveasfilename", anotar("asksaveasfilename", "C:/x/livro.epub"))
    monkeypatch.setattr(d.filedialog, "askdirectory", anotar("askdirectory", ""))
    caixas = d.Caixas(raiz)

    caixas.entrada("falta o título")
    caixas.informar("gravado", titulo="Livro")
    assert caixas.pergunta("sair?") is None
    assert caixas.pergunta("sair?", cancelar=False) is True
    assert caixas.abrir() == ""
    assert caixas.salvar_como("pasta/antigo.docx", extensao=".docx") == "C:/x/livro.epub"
    assert caixas.escolher_pasta() == ""

    nomes = [c[0] for c in chamadas]
    assert nomes == ["showwarning", "showinfo", "askyesnocancel", "askyesno", "askopenfilename",
                     "asksaveasfilename", "askdirectory"]
    assert chamadas[0][1] == (d.TITULO, "falta o título") and chamadas[0][2]["parent"] is raiz
    assert chamadas[1][1] == ("Livro", "gravado")
    salvar = chamadas[5][2]
    assert salvar["defaultextension"] == ".docx" and salvar["initialfile"] == "antigo.docx"
    assert salvar["initialdir"] == "pasta"


def test_a_fachada_monta_as_caixas_proprias_com_os_argumentos_e_devolve_o_que_elas_mostram(raiz, monkeypatch):
    _Fake.instancias.clear()
    for nome in ("DialogoDeFormulario", "DialogoDeFalha"):
        monkeypatch.setattr(d, nome, _Fake)
    caixas = d.Caixas(raiz)

    _Fake.resposta = {"titulo": "x"}
    assert caixas.formulario("Metadados", [("titulo", "Título:", "")], {"a": ["b"]}, texto="t") == {"titulo": "x"}
    assert _Fake.instancias[-1].args == (raiz, "Metadados", [("titulo", "Título:", "")], {"a": ["b"]}, "t")

    _Fake.resposta = True
    caixas.falha("caiu", "detalhe")
    assert _Fake.instancias[-1].args == (raiz, "caiu", "detalhe")
