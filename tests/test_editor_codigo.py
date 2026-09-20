"""
Testes de `ui/editor/codigo.py` (ED-07; SPEC_EDITOR §9.1–§9.3, §13.2, §14): o
`EditorDeCodigo` operado **por comando** sobre uma raiz `withdraw`n — bem-formado e
consertar (AC-ED07-2), reformatar idempotente (AC-ED07-3), completar tag, sugerir
com as classes das folhas e envolver (AC-ED07-4), dividir no cursor (AC-ED07-6), ir
ao alvo com espião e voltar (AC-ED07-7), foco visível e temas (AC-ED07-8), inserir
link/id/imagem (AC-ED07-9), mais o desfazer próprio, o realce na tela, a calha, a
linha atual, o casamento, enter, tab, comentar, apagar palavra, zoom e as ligações
na bindtag.

Rodar sem pytest:      python tests/test_editor_codigo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from conftest import raiz_tk
from core.editor.clipes import Clipe
from core.editor.xhtml import ErroDeXhtml
from ui.editor import codigo, realce

DOC = ('<?xml version="1.0" encoding="utf-8"?>\n'
       '<html xmlns="http://www.w3.org/1999/xhtml">\n'
       "<head><title>T</title></head>\n"
       "<body>\n"
       '<p class="lance">Um <b>dois</b> tr&amp;s</p>\n'
       '<p>Segundo <a href="cap-0002.xhtml#x">link</a></p>\n'
       "</body>\n"
       "</html>\n")
FOLHAS = {"Styles/a.css": "p.lance { color: red }\n.lado { }\n.x { }\n", "Styles/b.css": ".outra { }\n"}


class _Editor:
    def __init__(self, linguagem="xhtml", **kw):
        self.raiz = raiz_tk()
        if self.raiz is None:
            pytest.skip("sem display")
        self.chamadas = []
        kw.setdefault("folhas", FOLHAS)
        kw.setdefault("abrir_alvo", lambda a, b: self.chamadas.append((a, b)))
        self.editor = codigo.EditorDeCodigo(self.raiz, linguagem, **kw)
        self.editor.pack(fill="both", expand=True)
        self.texto = self.editor.texto

    def __enter__(self):
        return self

    def __exit__(self, *a):
        try:
            self.raiz.destroy()
        except Exception:
            pass

    def linha(self, n):
        return self.texto.get(f"{n}.0", f"{n}.end")

    def tags(self, tipo):
        faixas = self.texto.tag_ranges(tipo)
        return [self.texto.get(a, b) for a, b in zip(faixas[::2], faixas[1::2])]


# ----------------------------------------------------------------------
# Carga, realce na tela, calha, linha atual, casamento
# ----------------------------------------------------------------------

def test_carregar_realca_marca_a_linha_atual_e_nao_fica_sujo():
    with _Editor() as e:
        e.editor.carregar(DOC)
        assert e.editor.texto_todo() == DOC and e.editor.sujo is False and e.editor.posicao == (1, 1)
        assert '"http://www.w3.org/1999/xhtml"' in e.tags("valor") and "&amp;" in e.tags("entidade")
        assert "<p" in e.tags("tag") and "class" in e.tags("atributo")
        assert e.tags("linha_atual") == [DOC.split("\n")[0] + "\n"]
        assert int(e.texto.cget("highlightthickness")) == 2 and str(e.texto.cget("undo")) == "0"
        assert codigo.BINDTAG in e.texto.bindtags() and e.texto.bindtags().index(codigo.BINDTAG) < e.texto.bindtags().index("Text")
        e.editor.ir_para(5, 3)
        assert e.editor.posicao == (5, 3) and e.tags("linha_atual") == [DOC.split("\n")[4] + "\n"]
        assert e.tags("casamento") == ['<p class="lance">', "</p>"]          # a tag sob o cursor e o seu par
        e.editor.ir_para(5, 24)
        assert e.tags("casamento") == ["<b>", "</b>"]
        e.texto.mark_set("insert", e.texto.search("</p>", "5.0") + "+2c")
        assert e.tags("casamento") == ['<p class="lance">', "</p>"]          # sobre o </p>: o par é o <p>
        e.editor.carregar("a (b [c] d) e")
        e.editor.ir_para(1, 4)
        assert e.tags("casamento") == ["(", ")"]
        e.editor.ir_para(1, 9)
        assert e.tags("casamento") == ["]", "["] or e.tags("casamento") == ["[", "]"]


def test_editar_re_realca_e_marca_sujo_e_o_comentario_propaga_na_tela():
    with _Editor() as e:
        e.editor.carregar(DOC)
        e.editor.ir_para(5, 1)
        e.texto.insert("insert", "<!-- ")
        assert e.editor.sujo is True
        e.editor.sincronizar(tudo=True)
        assert "</html>" not in e.tags("tag") and any("</html>" in t for t in e.tags("comentario"))
        e.texto.insert("5.end", " -->")
        e.editor.sincronizar(tudo=True)
        assert "</html>" in e.tags("tag")
        assert int(e.editor.calha.cget("width")) > 20


# ----------------------------------------------------------------------
# Desfazer próprio
# ----------------------------------------------------------------------

def test_desfazer_por_operacao_com_coalescencia_e_grupos(monkeypatch):
    agora = [1000.0]
    with _Editor(relogio=lambda: agora[0]) as e:
        e.editor.carregar("abc")
        assert not e.editor.pode_desfazer
        e.editor.ir_para(1, 4)
        for c in "def":                                  # digitação contínua: um ponto só
            e.texto.insert("insert", c)
            agora[0] += 0.1
        agora[0] += 5
        e.texto.insert("insert", "X")                    # fora da janela: outro ponto
        assert e.editor.texto_todo() == "abcdefX"
        assert e.editor.desfazer() and e.editor.texto_todo() == "abcdef"
        assert e.editor.desfazer() and e.editor.texto_todo() == "abc"
        assert not e.editor.desfazer()
        assert e.editor.refazer() and e.editor.texto_todo() == "abcdef"
        assert e.editor.refazer() and e.editor.texto_todo() == "abcdefX" and not e.editor.pode_refazer
        # Um comando composto (envolver) é um grupo: desfaz de uma vez, sem perder o miolo.
        e.texto.tag_add("sel", "1.0", "1.3")
        e.editor.envolver("strong")
        assert e.editor.texto_todo() == "<strong>abc</strong>defX"
        assert e.editor.desfazer() and e.editor.texto_todo() == "abcdefX"
        e.editor.carregar("x")
        assert not e.editor.pode_desfazer and not e.editor.sujo   # carregar zera o histórico


# ----------------------------------------------------------------------
# AC-ED07-2, 3: bem-formado, consertar, reformatar
# ----------------------------------------------------------------------

def test_ac2_bem_formado_da_linha_e_coluna_e_consertar_fecha_e_avisa():
    with _Editor() as e:
        e.editor.carregar("<html xmlns=\"http://www.w3.org/1999/xhtml\"><body>\n<p>aberto\n</body></html>")
        erro = e.editor.verificar_bem_formado()
        assert isinstance(erro, ErroDeXhtml) and erro.linha == 3 and erro.coluna >= 1
        assert e.editor.posicao[0] == 3 and e.tags("erro")           # a linha marcada, o cursor nela
        avisos = e.editor.consertar()
        assert avisos and any("<p>" in a for a in avisos)
        assert e.editor.verificar_bem_formado() is None and not e.tags("erro")
        assert "<p>aberto\n</p>" in e.editor.texto_todo()
        e.editor.carregar('<html xmlns="http://www.w3.org/1999/xhtml"><body><span epub:type="x">a</span></body></html>')
        erro = e.editor.verificar_bem_formado()
        assert erro is not None and "prefixo" in erro.mensagem.lower() or "prefix" in erro.mensagem.lower() or "epub" in erro.mensagem
        assert e.editor.consertar() and e.editor.verificar_bem_formado() is None
        assert 'xmlns:epub="http://www.idpf.org/2007/ops"' in e.editor.texto_todo()
        assert e.editor.consertar() == []                              # já está bem-formado: nada a fazer


def test_ac3_reformatar_e_o_canonico_idempotente_e_a_css_preserva_comentarios():
    with _Editor() as e:
        e.editor.carregar(DOC.replace("<b>dois</b>", "<i>dois</i>"))
        assert e.editor.reformatar() is None
        primeira = e.editor.texto_todo()
        assert "<em>dois</em>" in primeira                             # o sinônimo virou a forma canônica
        assert e.editor.reformatar() is None and e.editor.texto_todo() == primeira
        e.editor.carregar("<p>aberto")
        assert isinstance(e.editor.reformatar(), ErroDeXhtml)         # mal-formado: recusa, e o texto fica
        assert e.editor.texto_todo() == "<p>aberto"
    with _Editor("css") as e:
        e.editor.carregar("/* topo */\np{color:red;margin:0}\n@media print{p{margin:0} /* dentro */}\n")
        assert e.editor.reformatar() is None
        saida = e.editor.texto_todo()
        assert saida.startswith("/* topo */\np {\n  color: red;\n  margin: 0;\n}\n") and "/* dentro */" in saida
        assert e.editor.reformatar() is None and e.editor.texto_todo() == saida
        assert "p" in e.tags("seletor") and "color" in e.tags("propriedade")


# ----------------------------------------------------------------------
# AC-ED07-4: completar, sugerir, envolver
# ----------------------------------------------------------------------

def test_ac4_completar_tag_sugerir_classes_das_folhas_e_envolver():
    with _Editor() as e:
        e.editor.carregar(DOC)
        e.texto.mark_set("insert", e.texto.search("dois", "5.0") + "+4c")     # depois de "Um <b>dois"
        e.texto.insert("insert", "</")
        assert e.editor.completar_tag() == "b" and e.linha(5).startswith('<p class="lance">Um <b>dois</b>')
        e.texto.mark_set("insert", "5.end")
        e.texto.insert("insert", "</")
        assert e.editor.completar_tag() == "body"                        # o <p> já fechou: o aberto é o body
        assert e.editor.completar_tag() is None                          # sem `</` antes do cursor
        # `/` digitado depois de `<` completa sozinho (a ligação da tecla).
        e.editor.carregar("<p>x")
        e.texto.mark_set("insert", "end-1c")
        e.texto.insert("insert", "<")
        assert e.editor.ligacoes["<Key-slash>"](None) == "break" and e.editor.texto_todo() == "<p>x</p>"
        # Sugerir: classes das folhas dentro de class="…", com o prefixo digitado.
        e.editor.carregar('<p class="l')
        e.texto.mark_set("insert", "end-1c")
        assert e.editor.sugerir() == ["lado", "lance"] and e.editor._popup is not None
        assert e.editor.escolher_sugestao(1) == "lance" and e.editor.texto_todo() == '<p class="lance'
        assert e.editor._popup is None and e.editor.escolher_sugestao(0) is None
        e.editor.carregar('<p class="')
        e.texto.mark_set("insert", "end-1c")
        assert e.editor.sugerir() == ["lado", "lance", "outra", "x"]
        e.editor.fechar_sugestoes()
        # Tags: um candidato só entra direto, com o par e o cursor no meio.
        e.editor.carregar("<sp")
        e.texto.mark_set("insert", "end-1c")
        assert e.editor.sugerir() == ["span"] and e.editor.texto_todo() == "<span></span>" and e.editor.posicao == (1, 7)
        e.editor.carregar("<p ")
        e.texto.mark_set("insert", "end-1c")
        assert "class" in e.editor.sugerir() and "id" in e.editor.sugerir()
        e.editor.fechar_sugestoes()
        e.editor.carregar('<p epub:type="ch')
        e.texto.mark_set("insert", "end-1c")
        assert e.editor.sugerir() == ["chapter"] and e.editor.texto_todo() == '<p epub:type="chapter'
        # Envolver com e sem seleção.
        e.editor.carregar("abc")
        e.texto.tag_add("sel", "1.0", "1.3")
        e.editor.envolver("strong")
        assert e.editor.texto_todo() == "<strong>abc</strong>"
        e.editor.carregar("")
        e.editor.envolver("em")
        assert e.editor.texto_todo() == "<em></em>" and e.editor.posicao == (1, 5)
        e.editor.comandos["italico"]()
        assert e.editor.texto_todo() == "<em><em></em></em>"


# ----------------------------------------------------------------------
# AC-ED07-6, 7, 9: dividir, ir ao alvo, inserir
# ----------------------------------------------------------------------

def test_ac6_dividir_no_cursor_deixa_as_duas_metades_bem_formadas():
    from core.editor import xhtml
    with _Editor() as e:
        e.editor.carregar(DOC)
        e.editor.ir_para(6, 1)
        antes, depois = e.editor.dividir_no_cursor()
        assert xhtml.bem_formado(antes) is None and xhtml.bem_formado(depois) is None
        assert "Segundo" not in antes and "Segundo" in depois and "<title>T</title>" in depois
        # No meio de um <b> dentro do <p>: fecha e reabre os dois, sem o id.
        e.editor.carregar(DOC.replace('<p class="lance">', '<p class="lance" id="p1">'))
        e.texto.mark_set("insert", "5.32")
        antes, depois = e.editor.dividir_no_cursor()
        assert xhtml.bem_formado(antes) is None and xhtml.bem_formado(depois) is None
        assert antes.count("</b>") == 1 and antes.count("</p>") == 1
        assert '<p class="lance"><b>' in depois and 'id="p1"' not in depois
        e.editor.ir_para(2, 1)
        assert e.editor.dividir_no_cursor() is None                    # fora do body
        e.editor.carregar("<p>aberto")
        assert e.editor.dividir_no_cursor() is None                    # mal-formado
        # A tecla gera o evento virtual para a janela (que sabe o livro).
        recebidos = []
        e.texto.bind("<<DividirNoCursor>>", lambda ev: recebidos.append(1))
        assert e.editor.ligacoes["<Control-Return>"](None) == "break" and recebidos == [1]


def test_ac7_ir_ao_alvo_chama_o_espiao_com_arquivo_e_ancora_ou_folha_e_regra_e_voltar_retorna():
    with _Editor() as e:
        e.editor.carregar(DOC)
        i = e.texto.search("href", "1.0")
        e.texto.mark_set("insert", f"{i}+8c")
        assert e.editor.ir_ao_alvo() == ("cap-0002.xhtml", "x") and e.chamadas == [("cap-0002.xhtml", "x")]
        posicao = e.editor.posicao
        e.editor.ir_para(1, 1)
        assert e.editor.voltar() is True and e.editor.posicao == posicao
        assert e.editor.voltar() is False
        i = e.texto.search('class="lance"', "1.0")
        e.texto.mark_set("insert", f"{i}+3c")
        assert e.editor.ir_ao_alvo() == ("Styles/a.css", ".lance") and e.chamadas[-1] == ("Styles/a.css", ".lance")
        e.texto.mark_set("insert", "5.20")                             # texto comum: nada
        assert e.editor.ir_ao_alvo() is None
        e.editor.carregar('<a href="https://x.org/">x</a>')
        e.texto.mark_set("insert", "1.12")
        assert e.editor.ir_ao_alvo() is None                            # externo: não é alvo do livro


def test_ac9_inserir_link_id_e_imagem_deixam_o_xhtml_bem_formado():
    with _Editor() as e:
        e.editor.carregar(DOC)
        e.texto.mark_set("insert", "6.11")
        e.editor.inserir_link("cap-0002.xhtml#x", "ver")
        assert '<a href="cap-0002.xhtml#x">ver</a>' in e.linha(6)
        e.texto.mark_set("insert", "5.3")                               # dentro da tag de abertura do <p>
        e.editor.inserir_id("x")
        assert e.linha(5).startswith('<p id="x" class="lance">')
        e.texto.mark_set("insert", "6.end")
        e.editor.inserir_imagem("../Images/a.png", "alt")
        assert '<img src="../Images/a.png" alt="alt"/>' in e.linha(6)
        assert e.editor.verificar_bem_formado() is None
        e.texto.tag_add("sel", "6.3", "6.10")
        e.editor.inserir_id("y")
        assert '<span id="y">Segundo</span>' in e.linha(6) and e.editor.verificar_bem_formado() is None
        e.texto.tag_add("sel", "6.3", "6.7")
        e.editor.inserir_link("#x")                                     # sem rótulo: a seleção
        assert '<a href="#x"><spa' in e.linha(6) or '<a href="#x">' in e.linha(6)
        e.editor.carregar("")
        e.editor.inserir_link('a"b', "r<s")
        assert e.editor.texto_todo() == '<a href="a&quot;b">r&lt;s</a>'
        # Sem argumentos, o pedido vai para a janela.
        recebidos = []
        e.texto.bind("<<InserirLink>>", lambda ev: recebidos.append("link"))
        e.texto.bind("<<IrParaLinha>>", lambda ev: recebidos.append("linha"))
        e.editor.inserir_link()
        e.editor.ir_para_linha()
        assert recebidos == ["link", "linha"]
        e.editor.carregar("a\nb\nc")
        e.editor.ir_para_linha(3)
        assert e.editor.posicao == (3, 1)
        e.editor.ir_para_linha(99)
        assert e.editor.posicao == (3, 1)


# ----------------------------------------------------------------------
# Enter, tab, comentar, apagar palavra, zoom, tema, clipe, ligações
# ----------------------------------------------------------------------

def test_enter_mantem_o_recuo_e_abre_um_nivel_depois_da_tag_aberta():
    with _Editor() as e:
        e.editor.carregar("  <p>")
        e.texto.mark_set("insert", "end-1c")
        e.editor.enter()
        assert e.editor.texto_todo() == "  <p>\n    "
        e.editor.carregar("<p></p>")
        e.editor.ir_para(1, 4)
        e.editor.enter()
        assert e.editor.texto_todo() == "<p>\n  \n</p>" and e.editor.posicao == (2, 3)
        e.editor.carregar("  <br/>")
        e.texto.mark_set("insert", "end-1c")
        e.editor.enter()
        assert e.editor.texto_todo() == "  <br/>\n  "                   # tag vazia não abre nível
        e.editor.carregar("p {")
        e.texto.mark_set("insert", "end-1c")
        e.editor.enter()
        assert e.editor.texto_todo() == "p {\n  "
        e.editor.carregar("abc")
        e.editor.ir_para(1, 2)
        assert e.editor.ligacoes["<Return>"](None) == "break" and e.editor.texto_todo() == "a\nbc"


def test_tab_indenta_e_desindenta_e_comentar_alterna():
    with _Editor() as e:
        e.editor.carregar("a\nb\nc")
        e.editor.ir_para(1, 1)
        e.editor.indentar_ou_tab()
        assert e.editor.texto_todo() == "  a\nb\nc"
        e.texto.tag_add("sel", "2.0", "3.0")
        assert e.editor.indentar(1) == 1 and e.editor.texto_todo() == "  a\n  b\nc"
        e.texto.tag_add("sel", "1.0", "2.end")
        assert e.editor.indentar(-1) == 2 and e.editor.texto_todo() == "a\nb\nc"
        e.texto.tag_remove("sel", "1.0", "end")         # o indentar deixa a seleção; aqui é a linha atual
        e.editor.ir_para(2, 1)
        assert e.editor.comentar() is True and e.linha(2) == "<!-- b -->"
        e.texto.tag_remove("sel", "1.0", "end")
        assert e.editor.comentar() is False and e.linha(2) == "b"
        e.texto.tag_remove("sel", "1.0", "end")
        e.texto.tag_add("sel", "1.0", "2.end")
        assert e.editor.comentar() is True and e.editor.texto_todo() == "<!-- a\nb -->\nc"
    with _Editor("css") as e:
        e.editor.carregar("p { }")
        assert e.editor.comentar() is True and e.editor.texto_todo() == "/* p { } */"


def test_apagar_palavra_zoom_tema_e_clipe():
    with _Editor() as e:
        e.editor.carregar("abc def ghi")
        e.editor.ir_para(1, 8)
        assert e.editor.apagar_palavra(-1) == "def" and e.editor.texto_todo() == "abc  ghi"
        assert e.editor.apagar_palavra(1) == " " and e.editor.texto_todo() == "abc ghi"
        assert e.editor.apagar_palavra(1) == "ghi" and e.editor.apagar_palavra(1) == ""
        assert e.editor.zoom(2) == 13 and e.editor.corpo == 13 and e.editor.zoom_zero() == 11
        assert e.editor.zoom(-100) == codigo.CORPO_MINIMO
        e.editor.aplicar_tema("escuro")
        assert e.editor.tema["fundo"] == realce.TEMAS["escuro"]["fundo"]
        assert e.texto.cget("background") == realce.TEMAS["escuro"]["fundo"]
        e.editor.carregar("23.Rxe4")
        e.texto.tag_add("sel", "1.0", "1.7")
        assert e.editor.aplicar_clipe(Clipe(nome="L", texto='<span class="lance">\\1</span>')) == '<span class="lance">23.Rxe4</span>'
        e.editor.carregar("")
        e.editor.aplicar_clipe(Clipe(nome="N", texto="<strong>\\1</strong>"))
        assert e.editor.texto_todo() == "<strong></strong>" and e.editor.posicao == (1, 9)


def test_as_ligacoes_da_bindtag_devolvem_break_e_os_comandos_existem():
    with _Editor() as e:
        e.editor.carregar(DOC)
        obrigatorias = ["<Return>", "<Tab>", "<Key-slash>", "<Control-slash>", "<Control-Shift-I>", "<Control-space>",
                        "<Control-b>", "<Control-i>", "<Control-u>", "<Control-BackSpace>", "<Control-Delete>",
                        "<Control-KP_Add>", "<Control-KP_Subtract>", "<Control-Key-0>", "<<Undo>>", "<<Redo>>",
                        "<Alt-F7>", "<Alt-F8>", "<Control-Return>", "<Control-k>", "<Control-g>",
                        "<Control-Shift-J>", "<Escape>", "<Key-Insert>", "<<PasteSelection>>"]
        for sequencia in obrigatorias:
            assert sequencia in e.editor.ligacoes, sequencia
            assert e.texto.bind_class(codigo.BINDTAG, sequencia), sequencia
        e.editor.ir_para(5, 21)
        assert e.editor.ligacoes["<Control-b>"](None) == "break" and "<strong></strong>" in e.linha(5)
        assert e.editor.ligacoes["<<Undo>>"](None) == "break" and "<strong>" not in e.linha(5)
        assert e.editor.ligacoes["<Key-Insert>"](None) == "break"
        for nome in ("desfazer", "refazer", "comentar", "reformatar", "completar_tag", "sugerir", "negrito",
                     "italico", "sublinhado", "inserir_link", "inserir_id", "inserir_imagem", "ir_para_linha",
                     "bem_formado", "consertar", "dividir_no_cursor", "ir_ao_alvo", "voltar", "zoom_mais",
                     "zoom_menos", "zoom_zero", "apagar_palavra_anterior", "apagar_palavra_seguinte",
                     "selecionar_tudo", "indentar", "desindentar", "aplicar_clipe"):
            assert callable(e.editor.comandos[nome]), nome
        with pytest.raises(ValueError):
            codigo.EditorDeCodigo(e.raiz, "python")


def test_o_subprocesso_que_importa_o_modo_codigo_nao_traz_fitz_numpy_nem_cv2():
    import subprocess
    programa = ("import sys; import ui.editor.codigo, ui.editor.realce, ui.editor.clipes, core.editor.consertar, "
                "core.editor.clipes; print(sorted(m for m in ('fitz', 'numpy', 'cv2', 'PIL', 'docx') if m in sys.modules))")
    saida = subprocess.run([sys.executable, "-c", programa], capture_output=True, text=True,
                           cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), timeout=120)
    assert saida.returncode == 0, saida.stderr
    assert saida.stdout.strip() == "[]", saida.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
