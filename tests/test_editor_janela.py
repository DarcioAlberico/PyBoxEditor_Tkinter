"""
Testes de `ui/editor/janela.py` (ED-02; SPEC_EDITOR §7, §13.3, §14): a `JanelaDoEditor`
operada por comando numa raiz `withdraw`n — abrir o EPUB de hoje em texto e alternar
de modo sem mudar o canônico (AC-ED02-4), ficar em código com o XHTML mal-formado e
dizer linha e coluna (AC-5), a guarda ao fechar com resposta injetável, também pelo
`WM_DELETE_WINDOW` do `parent` (AC-6), o subprocesso `appy.py --editor` sem torch,
easyocr, cv2 nem numpy (AC-7), as duas camadas de erro com a janela viva (AC-8), o
layout que persiste (AC-9), abrir/salvar em Mensagens (AC-10), `novo_de_modelo`
(AC-11), o `AnelDeFoco` (AC-12) — e, num teste `gui` à parte (`deiconify` +
`focus_force`), os acordes da AC-3 e a ordem lógica dos painéis.

Rodar sem pytest:      python tests/test_editor_janela.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
from tkinter import ttk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from conftest import raiz_tk
from config.settings import Settings
from core.editor import epub, modelo as m, xhtml
from core.editor.projeto import Rascunho
from ui.editor import barra as barra_mod
from ui.editor.codigo import EditorDeCodigo
from ui.editor.janela import ORDEM_DOS_PAINEIS, JanelaDoEditor
from ui.editor.texto_rico import TextoRico

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EPUB = {"pasta": None, "caminho": None}


def _epub_de_hoje():
    """O EPUB de hoje, gerado uma vez por sessão; cada teste trabalha numa cópia."""
    if _EPUB["caminho"] is None:
        _EPUB["pasta"] = tempfile.mkdtemp(prefix="pbe-ed02-")
        _EPUB["caminho"] = editor_livros.epub_de_hoje(_EPUB["pasta"], "png")
    return _EPUB["caminho"]


class _Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def avancar(self, s):
        self.t += s


class _Caixas:
    """As respostas injetadas e o registro do que a janela pediu."""

    def __init__(self, janela):
        self.chamadas = []
        self.pergunta_resposta = True
        self.texto_resposta = ""
        self.inteiro_resposta = 1
        self.escolha_resposta = 0
        self.formulario_resposta = None
        c = janela.caixas
        c.entrada = lambda mensagem, *a, **k: self.chamadas.append(("entrada", mensagem))
        c.falha = lambda mensagem, detalhe: self.chamadas.append(("falha", mensagem, detalhe))
        c.informar = lambda mensagem, *a, **k: self.chamadas.append(("informar", mensagem))
        c.pergunta = lambda mensagem, *a, **k: (self.chamadas.append(("pergunta", mensagem)), self.pergunta_resposta)[1]
        c.pedir_texto = lambda *a, **k: self.texto_resposta
        c.pedir_inteiro = lambda *a, **k: self.inteiro_resposta
        c.escolher = lambda *a, **k: self.escolha_resposta
        c.formulario = lambda *a, **k: self.formulario_resposta
        c.texto = lambda titulo, conteudo, *a, **k: self.chamadas.append(("texto", titulo, conteudo))
        c.conclusao = lambda titulo, linhas, caminho, **k: self.chamadas.append(("conclusao", titulo, list(linhas), caminho))
        c.abrir = lambda *a, **k: ""
        c.salvar_como = lambda *a, **k: ""

    def entradas(self):
        return [c[1] for c in self.chamadas if c[0] == "entrada"]

    def falhas(self):
        return [c for c in self.chamadas if c[0] == "falha"]


class _Janela:
    def __init__(self, abrir=True, settings=None, pasta=None):
        self.abrir_epub = abrir
        self.settings = settings
        self.pasta = pasta

    def __enter__(self):
        self.raiz = raiz_tk()
        if self.raiz is None:
            pytest.skip("sem display")
        self.pasta = self.pasta or tempfile.mkdtemp(prefix="pbe-janela-")
        self.settings = self.settings or Settings(os.path.join(self.pasta, "settings.json"))
        self.relogio = _Relogio()
        self.j = JanelaDoEditor(self.raiz, settings=self.settings, relogio=self.relogio)
        self.j.withdraw()
        self.caixas = _Caixas(self.j)
        self.epub = None
        if self.abrir_epub:
            self.epub = os.path.join(self.pasta, "livro.epub")
            shutil.copy(_epub_de_hoje(), self.epub)
            self.j.executar("abrir", self.epub)
        return self

    def __exit__(self, *a):
        try:
            if self.j.winfo_exists():
                self.caixas.pergunta_resposta = False
                self.j.fechar()
            self.raiz.destroy()
        except Exception:
            pass

    def canonico(self, arquivo):
        livro = self.j.projeto.livro
        return xhtml.canonico(xhtml.escrever(livro.capitulo(arquivo), pasta_de_imagens=epub.pasta_de_imagens(livro)))


# ----------------------------------------------------------------------
# AC-ED02-4, AC-ED02-5: os modos
# ----------------------------------------------------------------------

def test_ac4_abre_o_epub_em_texto_e_alternar_modo_ida_e_volta_nao_muda_o_canonico():
    with _Janela() as t:
        j = t.j
        aba = j.aba_ativa()
        assert aba is not None and aba.modo == "texto" and isinstance(aba.widget, TextoRico)
        assert aba.arquivo == j.projeto.livro.capitulos[0].arquivo
        assert [a.arquivo for a in j.abas.abas] == [aba.arquivo]
        assert len(aba.widget.texto.window_names()) >= 2               # os diagramas, como ObjetoGenerico
        assert j.campos["modo"].cget("text") == "MODO TEXTO" and j.campos["capitulo"].cget("text") == "cap 1/2"
        antes = t.canonico(aba.arquivo)
        assert j.executar("alternar_modo") == "codigo"
        assert isinstance(aba.widget, EditorDeCodigo) and j.campos["modo"].cget("text") == "MODO CÓDIGO"
        assert j.projeto.livro.capitulo(aba.arquivo).texto_cru is not None
        assert "[código]" in j.abas.tab(aba.frame, "text")
        assert j.executar("alternar_modo") == "texto"
        assert isinstance(aba.widget, TextoRico) and j.projeto.livro.capitulo(aba.arquivo).texto_cru is None
        assert t.canonico(aba.arquivo) == antes
        assert j.mensagens.contem("Modo código") and j.mensagens.contem("Modo texto")
        assert not j._sujo()
        # modo_texto / modo_codigo são idempotentes
        assert j.executar("modo_texto") == "texto" and j.executar("modo_codigo") == "codigo"
        assert j.executar("modo_codigo") == "codigo"


@pytest.mark.parametrize("estrago, trecho", [
    ("<b>", "mismatched tag"),
    ('<span epub:type="noteref">x</span>', "unbound prefix"),
])
def test_ac5_xhtml_mal_formado_fica_em_codigo_com_linha_e_coluna_e_o_cursor_na_linha(estrago, trecho):
    with _Janela() as t:
        j = t.j
        aba = j.aba_ativa()
        j.executar("alternar_modo")
        editor = aba.widget
        # sem xmlns:epub, o prefixo não declarado é erro de bem-formado
        texto = editor.texto_todo().replace(' xmlns:epub="http://www.idpf.org/2007/ops"', "")
        editor.carregar(texto)
        linha = next(k for k, conteudo in enumerate(texto.split("\n"), start=1) if "<p" in conteudo)
        editor.texto.insert(f"{linha}.0", estrago)
        editor.ir_para(1)
        assert j.executar("alternar_modo") == "codigo"
        assert isinstance(aba.widget, EditorDeCodigo)
        assert len(j.validacao) == 1
        resultado = j.validacao.itens[0]
        assert resultado.arquivo == aba.arquivo and resultado.onde.startswith("linha ") and "col" in resultado.onde
        assert trecho in resultado.mensagem.lower() or trecho in resultado.mensagem
        assert "linha" in j.campos["aviso"].cget("text")
        assert j.mensagens.contem("linha ") and j.mensagens.contem(aba.nome)
        assert editor.posicao[0] == resultado.dados["linha"]
        assert j.inferior.select() == str(j.validacao)
        # salvar também recusa, antes de tocar o disco
        mtime = os.path.getmtime(t.epub)
        j.executar("salvar")
        assert t.caixas.entradas() and "não foi salvo" in t.caixas.entradas()[-1]
        assert os.path.getmtime(t.epub) == mtime
        # consertado, volta ao texto
        editor.carregar(editor.texto_todo().replace(estrago, ""))
        assert j.executar("alternar_modo") == "texto" and len(j.validacao) == 0


# ----------------------------------------------------------------------
# AC-ED02-6: a guarda ao fechar
# ----------------------------------------------------------------------

def test_ac6_guarda_ao_fechar_com_resposta_injetavel_tambem_pelo_wm_delete_window_do_parent():
    with _Janela() as t:
        j = t.j
        texto = j.aba_ativa().widget
        texto.ir_para(texto.ordem[1], 0)
        texto.inserir("mudança ")
        assert j._sujo() and j.title().startswith("• ")
        # cancelar: fica aberta
        t.caixas.pergunta_resposta = None
        assert j.fechar() is False and j.winfo_exists()
        assert t.caixas.chamadas[-1][0] == "pergunta"
        # pelo parent: a guarda roda antes do protocolo anterior, e o rascunho é forçado
        fechados = []
        t.raiz.protocol("WM_DELETE_WINDOW", lambda: fechados.append("parent"))
        j._instalar_guarda_no_parent()                      # o parent trocou o protocolo depois: reinstala
        t.raiz.tk.eval(t.raiz.protocol("WM_DELETE_WINDOW"))
        assert fechados == [] and j.winfo_exists()
        assert os.path.isfile(t.epub + ".autosave.json")
        # não salvar: fecha, descarta o rascunho e segue para o protocolo anterior do parent
        t.caixas.pergunta_resposta = False
        t.raiz.tk.eval(t.raiz.protocol("WM_DELETE_WINDOW"))
        assert fechados == ["parent"] and not j.winfo_exists()
        assert not os.path.isfile(t.epub + ".autosave.json")
        assert t.raiz.winfo_exists()
    with _Janela() as t:
        j = t.j
        j.aba_ativa().widget.inserir("x")
        t.caixas.pergunta_resposta = True                   # salvar: grava e fecha
        assert j.fechar() is True and not j.winfo_exists()
        livro, _rel = epub.ler(t.epub)
        assert m.texto_de(livro.capitulos[0].blocos[0]).startswith("x")


# ----------------------------------------------------------------------
# AC-ED02-7: o subprocesso
# ----------------------------------------------------------------------

def test_ac7_o_subprocesso_do_editor_nao_carrega_torch_easyocr_cv2_nem_numpy():
    caminho = _epub_de_hoje()
    ambiente = dict(os.environ, PYBOXEDITOR_SETTINGS=os.path.join(_EPUB["pasta"], "settings-subprocesso.json"))
    saida = subprocess.run([sys.executable, "appy.py", "--editor", caminho, "--fechar-apos", "1",
                            "--diagnostico-modulos"], capture_output=True, text=True, cwd=RAIZ, timeout=180,
                           env=ambiente)
    assert saida.returncode == 0, saida.stderr
    linha = next(li for li in saida.stdout.splitlines() if li.startswith("modulos pesados carregados:"))
    for pesado in ("torch", "easyocr", "cv2", "numpy", "ui.main_window"):
        assert f"'{pesado}'" not in linha, linha


# ----------------------------------------------------------------------
# AC-ED02-8: as duas camadas de erro
# ----------------------------------------------------------------------

def test_ac8_valueerror_vira_caixa_de_entrada_e_o_resto_caixa_de_falha_com_a_janela_viva():
    with _Janela(abrir=False) as t:
        j = t.j
        j.executar("salvar")                                   # sem livro: erro de entrada, com o que fazer
        assert t.caixas.entradas() == ["Nenhum livro aberto: abra um livro (Ctrl+O) ou crie um novo (Ctrl+N)."]
        assert j.ultimo_erro[0] == "entrada" and j.mensagens.contem("Nenhum livro aberto")
        j.comandos["quebrado"] = lambda: (_ for _ in ()).throw(RuntimeError("estourou"))
        j.executar("quebrado")
        falha = t.caixas.falhas()[-1]
        assert "RuntimeError: estourou" in falha[1] and "Traceback" in falha[2]
        assert j.ultimo_erro[0] == "falha" and j.winfo_exists()
        assert "Defeito do programa" in j.campos["aviso"].cget("text")
        assert j.executar("comando_que_nao_existe") is None and "chega na" in j.campos["aviso"].cget("text")
        # um comando de fase seguinte com item de menu diz a fase
        j.executar("imprimir")
        assert "ED-12" in j.campos["aviso"].cget("text")


# ----------------------------------------------------------------------
# AC-ED02-9, AC-ED02-10, AC-ED02-11, AC-ED02-12
# ----------------------------------------------------------------------

def test_ac9_o_layout_persiste_entre_janelas_na_mesma_preferencia():
    pasta = tempfile.mkdtemp(prefix="pbe-layout-")
    settings = Settings(os.path.join(pasta, "settings.json"))
    with _Janela(abrir=False, settings=settings, pasta=pasta) as t:
        j = t.j
        assert all(p.visivel for p in j.paineis.values())
        j.mostrar_painel("navegador", False)
        j.mostrar_painel("xadrez", False)
        j.mostrar_barra("xadrez", False)
        assert not j.paineis["navegador"].visivel and str(j.quadro_navegador) not in j.esquerda.panes()
        assert not j.variaveis["navegador"].get()
        layout = j.layout()
        assert layout["paineis"]["navegador"] is False and layout["paineis"]["sumario"] is True
        assert layout["barras"] == {"formatacao": True, "xadrez": False}
        t.caixas.pergunta_resposta = False
        j.fechar()
    assert Settings(os.path.join(pasta, "settings.json")).get("editor")["layout"]["paineis"]["navegador"] is False
    with _Janela(abrir=False, settings=Settings(os.path.join(pasta, "settings.json")), pasta=pasta) as t:
        j = t.j
        assert not j.paineis["navegador"].visivel and not j.paineis["xadrez"].visivel
        assert j.paineis["sumario"].visivel and j.paineis["propriedades"].visivel
        assert not j.variaveis["barra_de_xadrez"].get() and not j.barra_de_xadrez.winfo_manager()
        # esconder todos os da direita some com a lateral; mostrar um a traz de volta
        j.mostrar_painel("propriedades", False)
        assert str(j.direita) not in j.paned.panes()
        j.mostrar_painel("xadrez", True)
        assert str(j.direita) in j.paned.panes() and str(j.quadro_xadrez) in j.direita.panes()
        # o caderno de baixo é um painel só ("Busca e mensagens")
        j.mostrar_painel("busca", False)
        assert str(j.inferior) not in j.centro.panes() and not j.paineis["mensagens"].visivel
        j.mostrar_painel("mensagens", True)
        assert str(j.inferior) in j.centro.panes()


def test_ac10_abrir_e_salvar_geram_info_em_mensagens_e_salvar_limpa_o_sujo_e_alimenta_os_recentes():
    with _Janela() as t:
        j = t.j
        assert j.mensagens.contem("Aberto: ") and j.mensagens.contem("2 capítulos")
        assert j.recentes.lista() == [os.path.abspath(t.epub)]
        assert j.campos["estado"].cget("text") == "sem alterações"
        texto = j.aba_ativa().widget
        texto.ir_para(texto.ordem[1], 0)
        texto.inserir("Novo ")
        assert j._sujo() and j.campos["estado"].cget("text") == "• alterado"
        relatorio = j.executar("salvar")
        assert relatorio.formato == "epub" and not j._sujo() and not texto.sujo
        assert j.mensagens.contem("Salvo: ") and j.campos["estado"].cget("text").startswith("salvo ")
        assert not j.title().startswith("•")
        livro, _rel = epub.ler(t.epub)
        assert m.texto_de(livro.capitulos[0].blocos[1]).startswith("Novo ")
        # salvar como: muda o caminho do projeto e os recentes
        outro = os.path.join(t.pasta, "copia.epub")
        j.executar("salvar_como", outro)
        assert j.projeto.caminho == outro and j.recentes.lista()[0] == os.path.abspath(outro)
        assert j.title().startswith("copia.epub")
        j.executar("fechar_livro")
        assert j.projeto is None and len(j.abas) == 0 and j.title() == "Editor de livro"


def test_ac11_novo_de_modelo_poe_o_idioma_nos_metadados_e_nas_preferencias():
    with _Janela(abrir=False) as t:
        j = t.j
        projeto = j.executar("novo_de_modelo", "Título", "Autor", "pt")
        assert projeto.livro.metadados.idioma == "pt" and projeto.livro.metadados.titulo == "Título"
        assert projeto.livro.metadados.autores[0].nome == "Autor"
        assert t.settings.get("editor")["idioma_ortografia"] == "pt"
        assert j.aba_ativa() is not None and j.aba_ativa().modo == "texto"
        assert j.mensagens.contem("Livro novo a partir de modelo")
        j.executar("novo_de_modelo", "Outro", "", "xx1")
        assert "idioma inválido" in t.caixas.entradas()[-1]
        # pelo formulário
        t.caixas.formulario_resposta = {"titulo": "Pelo formulário", "autor": "", "idioma": "en"}
        projeto = j.executar("novo_de_modelo")
        assert projeto.livro.metadados.idioma == "en" and t.settings.get("editor")["idioma_ortografia"] == "en"
        # metadados (mínimo da ED-02)
        j.executar("metadados", "Renomeado", "Alguém", "pt-BR")
        md = j.projeto.livro.metadados
        assert (md.titulo, md.autores[0].nome, md.idioma) == ("Renomeado", "Alguém", "pt-BR") and j._sujo()


def test_ac12_o_anel_de_foco_marca_o_ttk_button_no_focusin_e_some_no_focusout():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        anel = barra_mod.AnelDeFoco(raiz, lambda pai: ttk.Button(pai, text="OK"))
        anel.pack()
        assert isinstance(anel.widget, ttk.Button) and int(anel.cget("highlightthickness")) == 0
        anel.widget.event_generate("<FocusIn>")
        assert int(anel.cget("highlightthickness")) == 2
        anel.widget.event_generate("<FocusOut>")
        assert int(anel.cget("highlightthickness")) == 0
    finally:
        raiz.destroy()


# ----------------------------------------------------------------------
# Projeto: pontos de verificação, reverter, rascunho, recentes
# ----------------------------------------------------------------------

def test_pontos_de_verificacao_criar_comparar_restaurar_e_reverter():
    with _Janela() as t:
        j = t.j
        ponto = j.executar("checkpoint_criar", "antes")
        assert os.path.isfile(ponto.caminho) and j.mensagens.contem("Ponto de verificação")
        texto = j.aba_ativa().widget
        texto.ir_para(texto.ordem[1], 0)
        texto.inserir("MUDOU ")
        diferencas = j.executar("checkpoint_comparar", ponto)
        # o capítulo mudou; o OPF também, pelo `dcterms:modified` de cada gravação
        assert {d.estado for d in diferencas} == {"alterado"} and any("MUDOU" in d.diff for d in diferencas)
        assert len(j.resultados) == len(diferencas) and t.caixas.chamadas[-1][0] == "texto"
        j.executar("checkpoint_restaurar", ponto)
        texto = j.aba_ativa().widget
        assert "MUDOU" not in m.texto_de(texto.sincronizar().blocos[1]) and j._sujo()
        # reverter: volta ao disco e limpa o sujo
        texto.ir_para(texto.ordem[1], 0)
        texto.inserir("DE NOVO ")
        t.caixas.pergunta_resposta = True
        j.executar("reverter")
        texto = j.aba_ativa().widget
        assert "DE NOVO" not in m.texto_de(texto.sincronizar().blocos[1]) and not j._sujo()
        # sem pontos, comparar é erro de entrada
        shutil.rmtree(j.projeto.pasta_de_checkpoints())
        j.executar("checkpoint_comparar")
        assert "não há pontos" in t.caixas.entradas()[-1]


def test_o_rascunho_grava_pelo_tique_com_o_relogio_injetado_e_e_oferecido_ao_reabrir():
    with _Janela() as t:
        j = t.j
        texto = j.aba_ativa().widget
        texto.ir_para(texto.ordem[1], 0)
        texto.inserir("rascunho ")
        assert j._tique() is False                             # ainda não passou o intervalo
        t.relogio.avancar(61)
        assert j._tique() is True
        rascunho = t.epub + ".autosave.json"
        assert os.path.isfile(rascunho) and j.mensagens.contem("Rascunho gravado")
        assert Rascunho.ler(rascunho)["livro"]["capitulos"][0]["blocos"][1]["trechos"][0]["texto"].startswith("rascunho ")
        t.relogio.avancar(61)
        assert j._tique() is False                             # nada mudou desde então
        pasta, caminho = t.pasta, t.epub
        j.destroy()                                            # "o processo caiu": sem guarda, o rascunho fica
    assert os.path.isfile(rascunho)
    with _Janela(abrir=False, pasta=pasta) as t:
        t.caixas.pergunta_resposta = True                      # "restaurar o rascunho?" → sim
        t.j.executar("abrir", caminho)
        assert t.caixas.chamadas[-1][0] == "pergunta" and "rascunho" in t.caixas.chamadas[-1][1]
        assert t.j.projeto.sujo and m.texto_de(t.j.projeto.livro.capitulos[0].blocos[1]).startswith("rascunho ")
        assert os.path.isfile(rascunho)                        # fica até a gravação seguinte
        t.caixas.pergunta_resposta = False                     # descartar ao fechar
        t.j.executar("fechar_livro")
        assert not os.path.isfile(rascunho)                    # quem descartou escolheu descartar


# ----------------------------------------------------------------------
# Abas, navegação, código
# ----------------------------------------------------------------------

def test_abas_capitulo_vizinho_fechar_aba_recurso_css_e_sumario():
    with _Janela() as t:
        j = t.j
        livro = j.projeto.livro
        aba2 = j.executar("capitulo_seguinte")
        assert aba2.arquivo == livro.capitulos[1].arquivo and j.campos["capitulo"].cget("text") == "cap 2/2"
        assert j.executar("capitulo_seguinte") is None and "último" in j.campos["aviso"].cget("text")
        assert j.executar("capitulo_anterior").arquivo == livro.capitulos[0].arquivo
        assert len(j.abas) == 2
        j.executar("fechar_aba")
        assert len(j.abas) == 1 and j.aba_ativa().arquivo == aba2.arquivo
        # a folha de estilo abre em código e volta para `Recurso.texto_cru` ao salvar
        folha = livro.folhas[0]
        aba_css = j.abrir_arquivo(folha)
        assert aba_css.tipo == "recurso" and aba_css.modo == "codigo" and aba_css.widget.linguagem == "css"
        aba_css.widget.texto.insert("end", "\np.novo { color: red; }\n")
        j.executar("salvar")
        assert livro.recurso(folha).texto_cru is not None and "p.novo" in livro.recurso(folha).texto_cru
        relido, _rel = epub.ler(t.epub)
        assert "p.novo" in epub.dados_de(relido, relido.recurso(folha)).decode("utf-8")
        # nav em leitura
        aba_nav = j.abrir_arquivo(livro.nav)
        assert aba_nav.somente_leitura and str(aba_nav.widget.texto.cget("state")) == "disabled"
        j.executar("negrito")
        assert "só para leitura" in t.caixas.entradas()[-1]
        # o OPF abre só para leitura (ED-08); uma imagem avisa
        aba_opf = j.abrir_arquivo(livro.opf)
        assert aba_opf.somente_leitura and "<package" in aba_opf.widget.texto_todo()
        with pytest.raises(ValueError):
            j.abrir_arquivo(next(c for c, r in livro.recursos.items() if r.tipo_mime.startswith("image/")))
        # navegador e sumário
        assert j.navegador.get_children() == ("grupo:Texto", "grupo:Estilos", "grupo:Imagens", "grupo:Fontes", "grupo:Outros")
        assert set(j.navegador.get_children("grupo:Texto")) == {c.arquivo for c in livro.capitulos}
        j.navegador.focus(livro.capitulos[0].arquivo)
        assert j._abrir_do_navegador().arquivo == livro.capitulos[0].arquivo
        entradas = j.arvore_do_sumario.get_children()
        assert entradas and j._destinos["s0"] == livro.sumario[0].destino
        j.arvore_do_sumario.focus("s0")
        aba = j._ir_pelo_sumario()
        assert aba.arquivo == livro.sumario[0].destino.partition("#")[0]


def test_dividir_capitulo_no_codigo_ir_para_linha_inserir_link_ancora_e_imagem():
    with _Janela() as t:
        j = t.j
        livro = j.projeto.livro
        aba = j.aba_ativa()
        # no texto, os comandos do código dizem que são do código (ir para linha é do código; ED-06)
        j.executar("ir_para", "linha", 3)
        assert "modo código" in t.caixas.entradas()[-1]
        j.executar("alternar_modo")
        editor = aba.widget
        assert j.executar("ir_para", "linha", 3) == 3 and editor.posicao[0] == 3
        j.caixas.ir_para = lambda *a, **k: ("linha", 2)
        assert j.executar("ir_para") == 2
        # dividir no <h2>: a segunda metade vira capítulo novo, logo depois
        segunda = editor.texto.search("<h2", "1.0")
        assert segunda
        editor.texto.mark_set("insert", f"{segunda} linestart")
        novo = j.executar("dividir_capitulo")
        assert novo and livro.capitulos[1].arquivo == novo and livro.capitulos[1].texto_cru
        assert j.aba_ativa().arquivo == novo and j._sujo()
        assert xhtml.bem_formado(livro.capitulos[0].texto_cru) is None
        assert xhtml.bem_formado(livro.capitulos[1].texto_cru) is None
        assert novo in j.navegador.get_children("grupo:Texto")
        # link, âncora e imagem no capítulo novo
        editor = j.aba_ativa().widget
        alvo = editor.texto.search("</h2>", "1.0")
        assert alvo
        editor.texto.mark_set("insert", alvo)
        j.executar("inserir_link", "../Text/x.xhtml#a", "rótulo")
        assert '<a href="../Text/x.xhtml#a">rótulo</a>' in editor.texto_todo()
        j.executar("inserir_ancora", "1 inválido")
        assert "id inválido" in t.caixas.entradas()[-1]
        j.executar("inserir_ancora", "minha-ancora")
        assert 'id="minha-ancora"' in editor.texto_todo()
        imagens = [c for c, r in livro.recursos.items() if r.tipo_mime.startswith("image/")]
        j.executar("inserir_imagem", imagens[0], "alt da figura")
        assert 'alt="alt da figura"' in editor.texto_todo()
        assert xhtml.bem_formado(editor.texto_todo()) is None
        # bem-formado, consertar e reformatar pela janela
        assert j.executar("bem_formado") is None and "bem-formado" in j.campos["aviso"].cget("text")
        editor.texto.insert("insert", "<i>")
        erro = j.executar("bem_formado")
        assert erro is not None and len(j.validacao) == 1
        j.executar("consertar")
        assert j.executar("bem_formado") is None
        assert j.executar("reformatar") is None


def test_comandos_de_formatacao_contagem_zoom_e_a_barra_de_status_pela_janela():
    with _Janela() as t:
        j = t.j
        texto = j.aba_ativa().widget
        p1 = texto.ordem[1]
        texto.selecionar(0, 5, p1)
        j.executar("negrito")
        assert texto.sincronizar().blocos[1].trechos[0].negrito
        j.executar("estilo_titulo2")
        assert isinstance(texto.sincronizar().blocos[1], m.Titulo) and texto.sincronizar().blocos[1].nivel == 2
        j.executar("estilo_corpo")
        assert isinstance(texto.sincronizar().blocos[1], m.Paragrafo) and not isinstance(texto.sincronizar().blocos[1], m.Titulo)
        j.executar("entrelinha_15")
        assert texto.sincronizar().blocos[1].entrelinha == 1.5
        j.executar("realce_amarelo")
        assert texto.sincronizar().blocos[1].trechos[0].fundo == "#ffff00"
        j.executar("realce_nenhum")
        assert texto.sincronizar().blocos[1].trechos[0].fundo == ""
        j.executar("recuar")
        assert texto.sincronizar().blocos[1].recuo_esquerda_em == 2.0
        j.executar("diminuir_recuo")
        assert texto.sincronizar().blocos[1].recuo_esquerda_em is None
        j.executar("maiusculas")
        assert m.texto_de(texto.sincronizar().blocos[1])[:5].isupper()
        assert j.executar("zoom_mais") > 1.0 and j.executar("zoom_zero") == 1.0
        j.variaveis["invisiveis"].set(True)
        j.executar("invisiveis")
        assert texto._invisiveis
        j.variaveis["quebra_automatica"].set(False)
        j.executar("quebra_automatica")
        assert str(texto.texto.cget("wrap")) == "none"
        contagem = j.executar("contagem")
        assert contagem["capitulos"] == 2 and contagem["livro"] >= contagem["capitulo"] > 0
        assert t.caixas.chamadas[-1][0] == "informar" and "palavras" in j.campos["palavras"].cget("text")
        # pincel: copia, depois aplica
        texto.ir_para(p1, 0)
        assert j.executar("pincel") is False and "Pincel carregado" in j.campos["aviso"].cget("text")
        texto.selecionar(0, 3, texto.ordem[0])
        assert j.executar("pincel") is True
        # parágrafo e fonte pelas caixas
        j.caixas.paragrafo = lambda atual: {"alinhamento": "centro"}
        j.executar("paragrafo")
        assert texto.sincronizar().blocos[0].alinhamento == "centro"
        j.caixas.fonte = lambda atual: {"italico": True}
        texto.selecionar(0, 3, texto.ordem[0])
        j.executar("fonte")
        assert texto.sincronizar().blocos[0].trechos[0].italico
        # o status acompanha o cursor
        texto.ir_para(p1, 2)
        assert j.campos["posicao"].cget("text") == "bloco 2/6, car 3"
        # ajuda
        j.executar("atalhos")
        assert t.caixas.chamadas[-1][0] == "texto" and "Ctrl+Shift+S" in t.caixas.chamadas[-1][2]
        j.executar("dialeto")
        assert "cabecalho-diagrama" in t.caixas.chamadas[-1][2]


def test_exportar_epub_escreve_uma_copia_e_chama_a_caixa_de_conclusao():
    with _Janela() as t:
        j = t.j
        destino = os.path.join(t.pasta, "exportado.epub")
        assert j.executar("exportar", "epub", destino) == destino
        assert os.path.isfile(destino) and j.projeto.caminho == t.epub
        conclusao = t.caixas.chamadas[-1]
        assert conclusao[0] == "conclusao" and conclusao[3] == destino
        assert any("Capítulos: 2" in li for li in conclusao[2])
        assert j.projeto.livro.zip_de_origem == t.epub
        j.executar("exportar", "docx", destino)
        assert "ED-12" in t.caixas.entradas()[-1]
        j.executar("exportar", "zzz", destino)
        assert "formato desconhecido" in t.caixas.entradas()[-1]


# ----------------------------------------------------------------------
# gui: os acordes (AC-ED02-3) e o foco (AC-ED02-9, AC-ED02-12)
# ----------------------------------------------------------------------

def _janela_gui():
    t = _Janela(abrir=False)
    return t


ACORDES = ["<Control-d>", "<Control-h>", "<Control-i>", "<Control-k>", "<Control-o>", "<Control-t>",
           "<Control-space>", "<Control-Shift-space>", "<Control-slash>", "<Control-a>", "<Control-Tab>",
           "<Control-Next>", "<Control-Prior>", "<Shift-Insert>", "<Insert>", "<Control-BackSpace>",
           "<Control-Delete>"]
ESPERADOS = {
    "texto": {"<Control-d>": "fonte", "<Control-h>": "substituir", "<Control-i>": "italico", "<Control-k>": None,
              "<Control-o>": "abrir", "<Control-t>": "sumario_editar", "<Control-space>": "limpar_caractere",
              "<Control-Shift-space>": "espaco_inseparavel", "<Control-slash>": None, "<Control-a>": "selecionar_tudo",
              "<Control-Tab>": None, "<Control-Next>": "capitulo_seguinte", "<Control-Prior>": "capitulo_anterior",
              "<Shift-Insert>": "colar", "<Insert>": None, "<Control-BackSpace>": "apagar_palavra_anterior",
              "<Control-Delete>": "apagar_palavra_seguinte"},
    "codigo": {"<Control-d>": None, "<Control-h>": "substituir", "<Control-i>": "italico", "<Control-k>": "inserir_link",
               "<Control-o>": "abrir", "<Control-t>": "sumario_editar", "<Control-space>": "autocompletar",
               "<Control-Shift-space>": None, "<Control-slash>": "comentar", "<Control-a>": "selecionar_tudo",
               "<Control-Tab>": None, "<Control-Next>": "capitulo_seguinte", "<Control-Prior>": "capitulo_anterior",
               "<Shift-Insert>": "colar", "<Insert>": None, "<Control-BackSpace>": "apagar_palavra_anterior",
               "<Control-Delete>": "apagar_palavra_seguinte"},
}


@pytest.mark.gui
def test_gui_ac3_os_acordes_nao_mexem_no_texto_e_chamam_o_espiao_do_comando():
    with _Janela(abrir=False) as t:
        j = t.j
        j.executar("novo_de_modelo", "Acordes", "", "pt")
        j.deiconify()
        j.focus_force()
        j.update()
        aba = j.aba_ativa()
        for modo in ("texto", "codigo"):
            if modo == "codigo":
                j.executar("alternar_modo")
            widget = aba.widget
            tk_text = widget.texto
            if modo == "texto":
                widget.carregar_blocos([m.Paragrafo(trechos=[m.Trecho(texto="abc")])])
            else:
                widget.carregar("abc")
            tk_text.mark_set("insert", "1.1")
            base = tk_text.get("1.0", "end")                  # "abc\n" no código; o texto rico fecha o bloco com \n
            assert base.startswith("abc\n")
            for seq in ACORDES:
                chamados = []
                esperado = ESPERADOS[modo][seq]
                if esperado:
                    j.comandos[esperado] = lambda c=esperado: chamados.append(c)
                    j.modos_do_comando.pop(esperado, None)
                tk_text.focus_force()
                j.update()
                tk_text.event_generate(seq)
                j.update()
                assert tk_text.get("1.0", "end") == base, (modo, seq, tk_text.get("1.0", "end"))
                assert tk_text.index("insert") == "1.1", (modo, seq)
                if esperado:
                    assert chamados == [esperado], (modo, seq, chamados)
        j.withdraw()


@pytest.mark.gui
def test_gui_ac9_esconder_o_painel_focado_devolve_o_foco_e_ac12_painel_seguinte_percorre_a_ordem():
    with _Janela() as t:
        j = t.j
        j.deiconify()
        j.focus_force()
        j.update()
        j.paineis["navegador"].foco()
        j.update()
        assert j._painel_com_foco() == "navegador"
        j.mostrar_painel("navegador", False)
        j.update()
        assert j._painel_com_foco() == "editor" and j.focus_get() is j.aba_ativa().widget.texto
        j.mostrar_painel("navegador", True)
        j.update()
        percorridos = []
        j.paineis["navegador"].foco()
        j.update()
        for _ in range(len(ORDEM_DOS_PAINEIS)):
            percorridos.append(j.executar("painel_seguinte"))
            j.update()
        assert percorridos == list(ORDEM_DOS_PAINEIS[1:]) + [ORDEM_DOS_PAINEIS[0]]
        assert j.executar("painel_anterior") == ORDEM_DOS_PAINEIS[-1]
        j.executar("foco_no_editor")
        j.update()
        assert j._painel_com_foco() == "editor"
        j.withdraw()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
