"""
Testes dos objetos do modo texto (ED-04; SPEC_EDITOR §8.7–§8.10, §7.4): a figura de um
PNG em `Images/` com o alt vazio avisado e a largura por "Aplicar", que sobrevive a
salvar e reabrir (AC-ED04-1); as notas de rodapé e de fim — renumerar ao apagar, o
`aside` com o id e a `section` de notas de fim no XHTML, e o `sincronizar()` que devolve
blocos **e** notas editadas na faixa (AC-3); as ilhas de bloco e inline byte a byte, com
`apagar_selecao()` e desfazer (AC-5); dividir e juntar pela janela por `livro_ops`
(AC-6); as quebras, a marca de página e `juntar_paragrafos` através dela (AC-7, parte);
os desenhos de cada objeto e o mini-editor da ilha; a ação principal do `Enter`.

Rodar sem pytest:      python tests/test_editor_objetos.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from conftest import raiz_tk
from core.editor import epub, livro_ops, modelo as m, xhtml
from editor_ambiente import Janela, Widget, p
from ui.editor import objetos
from ui.editor.tabela import GradeDeTabela


def _png(caminho, largura=40, altura=30):
    from PIL import Image

    Image.new("RGB", (largura, altura), (200, 30, 30)).save(caminho)
    return caminho


# ----------------------------------------------------------------------
# AC-ED04-1: a figura
# ----------------------------------------------------------------------

def test_ac1_png_de_tmp_vira_figura_em_images_com_alt_avisado_largura_por_aplicar_e_salvar_reabrir_mantem(tmp_path):
    png = _png(str(tmp_path / "quadrado.png"))
    with Janela() as t:
        j, texto = t.j, t.texto
        texto.ir_para(texto.ordem_do_capitulo[1], 0)
        href = j.executar("inserir_imagem", png, "")
        assert href == "Images/quadrado.png" and href in j.projeto.livro.recursos
        assert j.projeto.livro.recursos[href].tipo_mime == "image/png"
        assert "sem alt" in j.campos["aviso"].cget("text")
        figura = t.bloco(lambda b: isinstance(b, m.Figura) and b.recurso == href)
        assert figura.alt == "" and figura.largura_pt is None
        janela = texto.widget_do_objeto(figura.id)
        assert isinstance(janela, objetos.ObjetoDeFigura) and janela.imagem is not None
        assert janela.imagem.width() == 40 and janela.imagem.height() == 30
        # A largura por "Aplicar": antes de aplicar, o modelo não muda (AC-8).
        texto.selecionar_objeto(figura.id)
        painel = j.painel_de_propriedades
        alvo = painel.atualizar(forcar=True)
        assert alvo["tipo"] == "figura" and "Sem alt" in painel.aviso.cget("text")
        painel.definir("largura_pt", "120")
        painel.definir("alt", "um quadrado vermelho")
        assert t.bloco(lambda b: b.id == figura.id).largura_pt is None
        assert painel.aplicar() is True
        depois = t.bloco(lambda b: b.id == figura.id)
        assert depois.largura_pt == 120.0 and depois.alt == "um quadrado vermelho"
        assert painel.aviso.cget("text") == ""                          # o alt preenchido cala o aviso
        assert texto.desfazer() and t.bloco(lambda b: b.id == figura.id).largura_pt is None
        assert texto.refazer() and t.bloco(lambda b: b.id == figura.id).largura_pt == 120.0
        # Salvar e reabrir mantém a figura, a largura e o recurso.
        salvo = os.path.join(t.pasta, "salvo.epub")
        j.executar("salvar_como", salvo)
        livro, _ = epub.ler(salvo)
        cap = livro.capitulos[0]
        cap = xhtml.ler(cap.texto_cru, cap.arquivo) if cap.texto_cru is not None else cap
        fig = next(b for b in cap.blocos if isinstance(b, m.Figura) and b.recurso == href)
        assert fig.largura_pt == 120.0 and fig.alt == "um quadrado vermelho"
        assert epub.dados_de(livro, livro.recursos[href]) == open(png, "rb").read()


def test_a_figura_sem_imagem_legivel_vira_caixa_com_o_nome_e_o_svg_tambem():
    figura = m.Figura(recurso="Images/desenho.svg", alt="um desenho", largura_pt=80)
    with Widget([p("a"), figura, p("b")], recursos=lambda href: b"<svg/>") as t:
        janela = t.w.widget_do_objeto(figura.id)
        assert isinstance(janela, objetos.ObjetoDeFigura) and janela.imagem is None
        assert "desenho.svg" in janela.texto and "um desenho" in janela.texto
        assert m.igual(t.w.sincronizar(reler=True), t.cap)


# ----------------------------------------------------------------------
# AC-ED04-3: notas
# ----------------------------------------------------------------------

def test_ac3_duas_notas_apagar_a_primeira_renumera_e_o_xhtml_tem_aside_com_o_id_e_a_section_de_fim():
    with Widget([p("um dois"), p("tres quatro")]) as t:
        w = t.w
        b0, b1 = t.cap.blocos[0].id, t.cap.blocos[1].id
        w.ir_para(b0, 2)
        n1 = w.inserir_nota("rodape")
        assert w.em_nota() == n1 and w.bloco_atual() != b0          # o cursor foi para a nota
        w.inserir("primeira nota")
        assert w.voltar_da_nota() and w.posicao() == (b0, 2)
        w.ir_para(b1, 4)
        n2 = w.inserir_nota("rodape")
        w.inserir("segunda nota")
        w.voltar_da_nota()
        cap = w.sincronizar()
        assert [(n.id, n.tipo, m.texto_de(n)) for n in cap.notas] == [(n1, "rodape", "primeira nota"),
                                                                       (n2, "rodape", "segunda nota")]
        assert [tr.nota for b in cap.blocos for tr in b.trechos if tr.nota] == [n1, n2]
        assert w.texto.get("1.0", "end-1c") == "um¹ dois\ntres² quatro\n\n¹ primeira nota\n² segunda nota\n"
        # Apagar a primeira: a segunda vira ¹ na referência e na faixa; o XHTML tem o aside com o id.
        assert w.apagar_nota(n1)
        cap = w.sincronizar()
        assert [n.id for n in cap.notas] == [n2]
        assert w.texto.get("1.0", "end-1c") == "um dois\ntres¹ quatro\n\n¹ segunda nota\n"
        escrito = xhtml.escrever(cap)
        assert f'<aside epub:type="footnote" role="doc-footnote" id="{n2}">' in escrito
        assert f'href="#{n2}"><sup>1</sup></a>' in escrito
        # Desfazer traz a nota e a referência de volta, num ponto só.
        assert w.desfazer()
        cap = w.sincronizar()
        assert [n.id for n in cap.notas] == [n1, n2] and "um¹ dois" in w.texto.get("1.0", "2.0")
        # Uma nota de fim sai em section[epub:type=endnotes] > ol > li[epub:type=endnote].
        w.ir_para(b1, 0)
        n3 = w.inserir_nota("fim")
        w.inserir("nota de fim")
        cap = w.sincronizar()
        assert [n.tipo for n in cap.notas] == ["rodape", "rodape", "fim"]
        escrito = xhtml.escrever(cap)
        assert '<section epub:type="endnotes" role="doc-endnotes">' in escrito
        assert f'<li epub:type="endnote" id="{n3}">' in escrito and "<ol>" in escrito
        volta = xhtml.ler(escrito, cap.arquivo)
        assert m.igual(volta, cap)


def test_ac3_sincronizar_devolve_blocos_e_notas_editadas_na_faixa_e_desfaz_a_nota_inteira():
    notas = [m.Nota(id="n1", tipo="rodape", blocos=[p("nota um", estilo="nota")]),
             m.Nota(id="n2", tipo="fim", blocos=[p("nota dois", estilo="nota"), p("continua", estilo="nota")])]
    ref = m.Paragrafo(trechos=[m.Trecho(texto="a"), m.Trecho(nota="n1"), m.Trecho(texto="b"), m.Trecho(nota="n2")])
    with Widget([ref, p("c")], notas=notas) as t:
        w = t.w
        assert m.igual(w.sincronizar(reler=True), t.cap)                   # ida e volta com a faixa
        assert w.ids_das_notas() == ["n1", "n2"] and len(w.ordem) == 2 + 1 + 3   # blocos + marco + parágrafos
        # Editar na faixa: o texto da nota muda no modelo; o ponto de desfazer é sobre a nota.
        w.ir_para_nota("n1")
        assert w.em_nota() == "n1"
        w.inserir("X")
        cap = w.sincronizar()
        assert m.texto_de(cap.notas[0]) == "Xnota um" and m.texto_de(cap.blocos[0]) == "ab"
        assert w.pode_desfazer and w.desfazer()
        assert m.texto_de(w.sincronizar().notas[0]) == "nota um"
        # Enter dentro da nota abre um parágrafo na mesma nota; BackSpace no começo dele junta de volta.
        w.ir_para_nota("n2")
        w.ir_para(w.bloco_atual(), 4)
        assert w.enter()
        cap = w.sincronizar()
        assert [m.texto_de(b) for b in cap.notas[1].blocos] == ["nota", " dois", "continua"]
        assert w.backspace()
        assert [m.texto_de(b) for b in w.sincronizar().notas[1].blocos] == ["nota dois", "continua"]
        # Uma nota não recebe objeto de bloco nem outra nota; Esc volta à referência.
        with pytest.raises(ValueError):
            w.inserir_objeto(m.Separador())
        with pytest.raises(ValueError):
            w.inserir_nota("rodape")
        assert w.voltar_da_nota() and w.em_nota() is None and w.bloco_atual() == ref.id
        # Rodapé ↔ fim reordena a faixa e renumera.
        assert w.mudar_tipo_da_nota("n1", "fim")
        assert [(n.id, n.tipo) for n in w.sincronizar().notas] == [("n2", "fim"), ("n1", "fim")] or \
            [(n.id, n.tipo) for n in w.sincronizar().notas] == [("n1", "fim"), ("n2", "fim")]
        assert w.desfazer() and [(n.id, n.tipo) for n in w.sincronizar().notas] == [("n1", "rodape"), ("n2", "fim")]


def test_apagar_a_referencia_pela_selecao_leva_a_nota_e_selecionar_tudo_para_antes_da_faixa():
    with Widget([p("abc")]) as t:
        w = t.w
        w.ir_para(t.cap.blocos[0].id, 1)
        n = w.inserir_nota("rodape")
        w.inserir("texto")
        w.voltar_da_nota()
        w.selecionar_tudo()
        ini, fim = w.selecao()
        assert w.texto.compare(fim, "<=", w._inicio_de("faixa:notas"))      # Ctrl+A não pega as notas
        # BackSpace depois da referência seleciona-a; o segundo apaga — e a nota vai junto.
        w.ir_para(t.cap.blocos[0].id, 1)                     # o 1 do modelo pula a referencia: fica logo depois dela
        assert w.backspace() is False and w.selecao() is not None
        assert w.backspace() is True
        cap = w.sincronizar()
        assert cap.notas == [] and m.texto_de(cap.blocos[0]) == "abc" and "faixa:notas" not in w.ordem
        assert w.desfazer() and [x.id for x in w.sincronizar().notas] == [n]


# ----------------------------------------------------------------------
# AC-ED04-5: ilhas
# ----------------------------------------------------------------------

def test_ac5_ilha_svg_e_ilha_inline_cite_atravessam_carregar_editar_ao_redor_e_sincronizar_byte_a_byte():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'
    ilha = m.IlhaBruta(xhtml=svg, elemento="svg")
    cite = m.Paragrafo(trechos=[m.Trecho(texto="ver "), m.Trecho(ilha="<cite lang=\"la\">Opus</cite>"),
                                m.Trecho(texto=" ali")])
    with Widget([p("antes"), ilha, cite, p("depois")]) as t:
        w = t.w
        assert isinstance(w.widget_do_objeto(ilha.id), objetos.ObjetoDeIlha)
        nome = w.ilha_inline_no_cursor() or next(n for n in w.registro.nomes()
                                                if isinstance(w.registro.objeto_registrado(n), m.Trecho))
        assert isinstance(w.registro.widget_de(nome), objetos.ObjetoDeIlhaInline)
        assert w.registro.widget_de(nome).texto == "⟨cite⟩"
        # Editar ao redor: texto antes da ilha de bloco e dos dois lados da inline.
        w.ir_para(t.cap.blocos[0].id, 5)
        w.inserir(" e mais")
        w.inserir("X", w.texto.index(nome))                  # antes da ilha (o deslocamento 4 do modelo cai depois)
        w.ir_para(cite.id, 5)
        w.inserir("Y")
        cap = w.sincronizar(reler=True)
        assert cap.blocos[1].xhtml == svg and cap.blocos[1].elemento == "svg"
        assert [tr.ilha or tr.texto for tr in cap.blocos[2].trechos] == ["ver X", '<cite lang="la">Opus</cite>',
                                                                          "Y ali"]
        assert xhtml.escrever(cap).count(svg) == 1
        # `apagar_selecao()` apaga a ilha de bloco (selecionada) e a inline (na seleção), com desfazer.
        w.selecionar_objeto(ilha.id)
        assert w.apagar_selecao()
        assert [type(b).__name__ for b in t.blocos()] == ["Paragrafo", "Paragrafo", "Paragrafo"]
        w.ir_para(cite.id, 3)
        w.selecionar(3, 6)
        assert w.apagar_selecao()
        assert [tr.ilha for tr in t.blocos()[1].trechos] == [""] and m.texto_de(t.blocos()[1]) == "ver ali"
        assert w.desfazer() and [tr.ilha for tr in t.blocos()[1].trechos if tr.ilha] == ['<cite lang="la">Opus</cite>']
        assert w.desfazer() and isinstance(t.blocos()[1], m.IlhaBruta) and t.blocos()[1].xhtml == svg


def test_o_mini_editor_da_ilha_so_aceita_fragmento_legivel_e_substituir_ilha_volta_ao_dialeto_quando_cabe():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        editor = objetos.EditorDeIlha(raiz, "<svg xmlns=\"http://www.w3.org/2000/svg\"/>")
        editor.construir()
        editor.definir_texto("<svg><rect")
        assert editor.confirmar() is None and editor.erro and editor.top is not None   # fica aberto
        editor.definir_texto("<p>agora é parágrafo</p>")
        assert editor.confirmar() == "<p>agora é parágrafo</p>" and editor.top is None
        editor2 = objetos.EditorDeIlha(raiz, "x")
        editor2.construir()
        editor2.definir_texto("   ")
        assert editor2.confirmar() is None and "vazia" in editor2.erro
    finally:
        raiz.destroy()
    ilha = m.IlhaBruta(xhtml='<svg xmlns="http://www.w3.org/2000/svg"/>', elemento="svg")
    with Widget([p("a"), ilha, p("b")]) as t:
        w = t.w
        ids = w.substituir_ilha(ilha.id, "<p>um</p><p>dois</p>")
        assert [m.texto_de(b) for b in t.blocos()] == ["a", "um", "dois", "b"] and ids[0] == ilha.id
        assert w.desfazer() and isinstance(t.blocos()[1], m.IlhaBruta)
        w.substituir_ilha(ilha.id, '<div class="x"><span>y</span></div>')
        assert isinstance(t.blocos()[1], m.IlhaBruta) and t.blocos()[1].elemento == "div"
        with pytest.raises(ValueError):
            w.substituir_ilha(ilha.id, "<p>")


# ----------------------------------------------------------------------
# AC-ED04-6: dividir e juntar pela janela
# ----------------------------------------------------------------------

def test_ac6_dividir_e_juntar_pela_janela_chamam_livro_ops_e_recarregam_abas_e_sumario(monkeypatch):
    chamadas = []
    original_dividir, original_juntar = livro_ops.dividir, livro_ops.juntar
    monkeypatch.setattr(livro_ops, "dividir",
                        lambda livro, href, i, novo=None: (chamadas.append(("dividir", href, i)),
                                                           original_dividir(livro, href, i, novo))[1])
    monkeypatch.setattr(livro_ops, "juntar",
                        lambda livro, href: (chamadas.append(("juntar", href)), original_juntar(livro, href))[1])
    with Janela() as t:
        j, texto = t.j, t.texto
        ordem = texto.ordem_do_capitulo
        texto.ir_para(ordem[5], 0)
        novo = j.executar("dividir_capitulo")
        assert novo == "cap1-1.xhtml" and chamadas == [("dividir", "cap1.xhtml", 5)]
        assert [c.arquivo for c in j.projeto.livro.capitulos] == ["cap1.xhtml", "cap1-1.xhtml", "cap2.xhtml"]
        assert j.aba_ativa().arquivo == novo and [a.arquivo for a in j.abas.abas] == ["cap1.xhtml", novo]
        primeira = j.abas.por_arquivo("cap1.xhtml").widget
        assert len(primeira.ordem_do_capitulo) == 5 and len(primeira.ids_das_notas()) == 2
        assert len(t.texto.ids_das_notas()) == 0                           # as notas ficaram com as referencias
        assert j.navegador.exists("cap1-1.xhtml")
        sumario = [j.arvore_do_sumario.item(i, "text") for i in j.arvore_do_sumario.get_children()]
        assert sumario and j._destinos["s0"].startswith("cap1.xhtml")
        # No meio de um parágrafo, o parágrafo é partido no cursor antes de dividir.
        texto = t.texto
        alvo = next(i for i in texto.ordem_do_capitulo if isinstance(texto.modelo_de(i), m.Paragrafo)
                    and len(m.texto_de(texto.modelo_de(i))) > 6)
        texto.ir_para(alvo, 3)
        novo2 = j.executar("dividir_capitulo")
        assert novo2 == "cap1-1-1.xhtml" and chamadas[-1] == ("dividir", "cap1-1.xhtml", 1)
        assert m.texto_de(j.projeto.livro.capitulos[2].blocos[0]) == m.texto_de(t.texto.sincronizar().blocos[0])
        assert len(m.texto_de(j.projeto.livro.capitulos[1].blocos[-1])) == 3       # a cabeca ficou no de cima
        # Juntar com o anterior: a aba do que entrou fecha, o alvo recarrega, o sumario tambem.
        alvo = j.executar("juntar_com_anterior")
        assert alvo == "cap1-1.xhtml" and chamadas[-1] == ("juntar", "cap1-1-1.xhtml")
        assert [c.arquivo for c in j.projeto.livro.capitulos] == ["cap1.xhtml", "cap1-1.xhtml", "cap2.xhtml"]
        assert j.aba_ativa().arquivo == alvo and "cap1-1-1.xhtml" not in [a.arquivo for a in j.abas.abas]
        assert j.projeto.sujo and not j.navegador.exists("cap1-1-1.xhtml")
        j.executar("juntar_com_anterior")
        assert [c.arquivo for c in j.projeto.livro.capitulos] == ["cap1.xhtml", "cap2.xhtml"]
        assert j.aba_ativa().arquivo == "cap1.xhtml" and len(t.texto.ids_das_notas()) == 2
        # O primeiro capítulo não tem anterior: erro de entrada, janela viva.
        assert j.executar("juntar_com_anterior") is None and "anterior" in t.caixas.entradas()[-1]


# ----------------------------------------------------------------------
# AC-ED04-7 (parte): quebras e marca de página
# ----------------------------------------------------------------------

def test_ac7_quebra_suave_quebra_de_pagina_e_marca_de_pagina_que_junta_atraves():
    with Widget([p("um dois"), p("tres")]) as t:
        w = t.w
        b0 = t.cap.blocos[0].id
        w.ir_para(b0, 3)
        assert w.inserir_quebra_suave()
        assert [tr.quebra_antes for tr in t.blocos()[0].trechos] == [False, True]
        assert m.texto_de(t.blocos()[0]) == "um \ndois"
        w.ir_para(b0, 2)
        quebra = w.inserir_quebra_de_pagina()
        blocos = t.blocos()
        assert [type(b).__name__ for b in blocos] == ["Paragrafo", "QuebraDePagina", "Paragrafo", "Paragrafo"]
        assert [m.texto_de(b) for b in blocos] == ["um", "", " \ndois", "tres"]
        assert w.widget_do_objeto(quebra).texto == "— quebra de página —"
        assert w.desfazer() and [m.texto_de(b) for b in t.blocos()] == ["um \ndois", "tres"]   # um ponto só
        sep = w.inserir_separador()                        # o cursor esta no comeco do bloco: entra antes dele
        assert isinstance(t.blocos()[0], m.Separador) and w.widget_do_objeto(sep) is not None
        assert [m.texto_de(b) for b in t.blocos()[1:]] == ["um \ndois", "tres"]
    marca = m.MarcaDePagina(pagina=27)
    with Widget([p("antes da"), marca, p("página"), p("fim")]) as t:
        w = t.w
        assert w.widget_do_objeto(marca.id).texto == "— página 27 —"
        w.ir_para(t.cap.blocos[2].id, 0)
        assert w.backspace()
        blocos = t.blocos()
        assert [type(b).__name__ for b in blocos] == ["Paragrafo", "Paragrafo"]
        assert [(tr.texto, tr.pagina) for tr in blocos[0].trechos] == [("antes da", None), ("página", 27)]
        assert w.posicao() == (t.cap.blocos[0].id, 8)
        assert w.desfazer() and [type(b).__name__ for b in t.blocos()] == ["Paragrafo", "MarcaDePagina", "Paragrafo",
                                                                            "Paragrafo"]
        assert m.igual(t.blocos()[1], marca)
        # A marca de página inline é desenhada e volta.
        assert m.igual(w.sincronizar(reler=True), t.cap)


# ----------------------------------------------------------------------
# Desenhos, ação principal, links
# ----------------------------------------------------------------------

def test_os_desenhos_de_cada_objeto_sao_focaveis_e_descrevem_o_objeto():
    tabela = m.Tabela(filas=[[m.Celula(blocos=[p("x")])]])
    grande = m.Tabela(filas=[[m.Celula(blocos=[]) for _ in range(21)] for _ in range(20)])
    blocos = [m.Figura(recurso="Images/nada.png", alt="figura"), m.IlhaBruta(xhtml="<x/>", elemento="x"),
              m.QuebraDePagina(), m.MarcaDePagina(pagina=3), m.Separador(), tabela, grande,
              m.Diagrama(fen="8/8/8/8/8/8/8/8 w - - 0 1"), p("fim")]
    with Widget(blocos) as t:
        w = t.w
        tipos = [type(w.widget_do_objeto(b.id)).__name__ for b in blocos[:-1]]
        assert tipos == ["ObjetoDeFigura", "ObjetoDeIlha", "ObjetoDeQuebra", "ObjetoDeMarcaDePagina",
                         "ObjetoDeSeparador", "GradeDeTabela", "ObjetoGenerico", "ObjetoDeDiagrama"]   # ED-05
        for b in blocos[:-1]:
            janela = w.widget_do_objeto(b.id)
            if isinstance(janela, GradeDeTabela):
                continue
            assert int(janela.rotulo.cget("takefocus")) == 1 and int(janela.rotulo.cget("highlightthickness")) == 2
            assert janela.dica() or isinstance(janela, objetos.ObjetoGenerico)
        assert "420" in w.widget_do_objeto(grande.id).texto or "20×21" in w.widget_do_objeto(grande.id).texto
        assert m.igual(w.sincronizar(reler=True), t.cap)
        with pytest.raises(ValueError):
            w.inserir_objeto(m.Tabela(filas=[[m.Celula(blocos=[]) for _ in range(21)] for _ in range(20)]))


def test_enter_sobre_o_objeto_faz_a_acao_principal_e_depois_dele_abre_paragrafo():
    with Janela() as t:
        j, texto = t.j, t.texto
        tabela = t.bloco(lambda b: isinstance(b, m.Tabela))
        texto.texto.mark_set("insert", texto._inicio_de(tabela.id))
        assert texto.enter() is True
        grade = texto.widget_do_objeto(tabela.id)
        assert grade.celula_atual() == (0, 0)
        # Sobre a ilha: o mini-editor (a caixa injetada devolve o XHTML novo).
        ilha = t.bloco(lambda b: isinstance(b, m.IlhaBruta))
        t.caixas.ilha_resposta = "<p>virou parágrafo</p>"
        texto.selecionar_objeto(ilha.id)
        assert texto.enter() is True and t.caixas.chamadas[-1][0] == "ilha"
        assert m.texto_de(t.bloco(lambda b: b.id == ilha.id)) == "virou parágrafo"
        # Depois de um objeto (no \n dele), Enter abre um parágrafo a seguir.
        figura = t.bloco(lambda b: isinstance(b, m.Figura))
        texto.texto.mark_set("insert", f"{texto._inicio_de(figura.id)}+1c")
        n = len(texto.ordem_do_capitulo)
        assert texto.enter() and len(texto.ordem_do_capitulo) == n + 1
        i = texto.ordem_do_capitulo.index(figura.id)
        assert isinstance(texto.modelo_de(texto.ordem_do_capitulo[i + 1]), m.Paragrafo)
        # Sobre uma referência de nota, Enter vai à nota; Esc (o comando) volta.
        paragrafo = t.bloco(lambda b: isinstance(b, m.Paragrafo) and any(tr.nota for tr in b.trechos))
        desloc = sum(len(tr.texto) for tr in paragrafo.trechos[:next(k for k, tr in enumerate(paragrafo.trechos)
                                                                          if tr.nota)])
        texto.ir_para(paragrafo.id, desloc)
        assert texto.enter() and texto.em_nota() == "n1"
        j.executar("escape")
        assert texto.em_nota() is None and texto.bloco_atual() == paragrafo.id
        # Sobre o diagrama, Enter abre o editor de posição (ED-05): a caixa injetada devolve o diagrama novo.
        diagrama = t.bloco(lambda b: isinstance(b, m.Diagrama))
        texto.selecionar_objeto(diagrama.id)
        t.caixas.diagrama_resposta = m.Diagrama(fen="8/8/8/8/8/8/8/K6k w - - 0 1", lado="w")
        assert j.acao_principal(diagrama) == "diagrama" and t.caixas.chamadas[-1][0] == "diagrama"
        assert t.bloco(lambda b: b.id == diagrama.id).fen == "8/8/8/8/8/8/8/K6k w - - 0 1"


def test_inserir_link_ancora_e_seguir_link_no_texto_e_o_link_externo_vai_ao_navegador():
    abertos = []
    with Janela() as t:
        j, texto = t.j, t.texto
        j.abrir_url = abertos.append
        primeiro = next(i for i in texto.ordem_do_capitulo
                        if isinstance(texto.modelo_de(i), m.Paragrafo) and not isinstance(texto.modelo_de(i), m.Titulo))
        texto.ir_para(primeiro, 0)
        texto.selecionar(0, 8)
        j.executar("inserir_link", "https://example.org/", None)
        bloco = t.bloco(lambda b: b.id == primeiro)
        assert bloco.trechos[0].link == "https://example.org/" and len(bloco.trechos[0].texto) == 8
        texto.ir_para(primeiro, 2)
        assert j.executar("seguir_link") == "https://example.org/" and abertos == ["https://example.org/"]
        # Sem seleção, o rótulo entra já com o link; a âncora dá id persistente ao bloco.
        texto.ir_para(primeiro, 8)
        j.executar("inserir_link", "cap2.xhtml#alvo", " (ver)")
        bloco = t.bloco(lambda b: b.id == primeiro)
        assert [(tr.texto, tr.link) for tr in bloco.trechos][:2] == [(bloco.trechos[0].texto, "https://example.org/"),
                                                                     (" (ver)", "cap2.xhtml#alvo")]
        assert j.executar("inserir_ancora", "meu-alvo") == "meu-alvo"
        assert texto.bloco_atual() == "meu-alvo" and t.bloco(lambda b: b.id == "meu-alvo").id_persistente
        assert j.destino_existe("cap1.xhtml#meu-alvo") and j.destino_existe("#meu-alvo")
        with pytest.raises(ValueError):
            texto.definir_id(texto.bloco_atual(), "cap1-t")                # já existe (INV-01)
        # Seguir o link interno troca de aba e leva ao bloco.
        texto.ir_para("meu-alvo", 10)
        assert texto.link_no_cursor() == "cap2.xhtml#alvo"
        j.executar("seguir_link")
        assert j.aba_ativa().arquivo == "cap2.xhtml" and j.aba_ativa().widget.bloco_atual() == "alvo"
        assert t.caixas.entradas() == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
