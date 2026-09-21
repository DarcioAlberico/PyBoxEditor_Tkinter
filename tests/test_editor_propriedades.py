"""
Testes do painel Propriedades (ED-04; SPEC_EDITOR §8.3, §8.6–§8.9, AC-ED04-8): o painel
só grava em "Aplicar" e o foco é visível nos widgets novos; o parágrafo (estilo,
alinhamento, recuos, âncora, classe), a figura, a tabela, a marca de página, a ilha, a
referência de nota (tipo) e o link (destino em vermelho quando não existe, e no
relatório de Resultados ao seguir — AC-4); `Alt+Enter` mostra o painel e o foca; o
painel acompanha a aba e a célula de tabela ativa.

Rodar sem pytest:      python tests/test_editor_propriedades.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from conftest import raiz_tk
from core.editor import modelo as m
from editor_ambiente import Janela, Widget, p
from ui.editor.barra import AnelDeFoco
from ui.editor.propriedades import COR_DE_ERRO, PainelDePropriedades


class _Painel:
    """Um painel ligado a um `TextoRico` solto."""

    def __init__(self, blocos, notas=None):
        self.t = Widget(blocos, notas)
        self.w = self.t.w
        self.acoes = []
        self.painel = PainelDePropriedades(self.t.raiz, self.w, ao_acao=lambda n, a: self.acoes.append((n, a["tipo"])),
                                           verificar_destino=lambda href: not href.endswith("nao-existe"))
        self.painel.pack(fill="both", expand=True)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.t.__exit__(*a)


# ----------------------------------------------------------------------
# AC-ED04-8
# ----------------------------------------------------------------------

def test_ac8_o_painel_so_grava_em_aplicar_e_o_foco_e_visivel():
    with _Painel([p("um parágrafo"), p("outro")]) as t:
        w, painel = t.w, t.painel
        w.ir_para(t.t.cap.blocos[0].id, 3)
        alvo = painel.atualizar()
        assert alvo["tipo"] == "paragrafo" and painel.titulo.cget("text") == "Parágrafo"
        assert set(painel.variaveis) >= {"estilo", "alinhamento", "recuo_esquerda_em", "id", "classe",
                                         "manter_com_proximo"}
        painel.definir("alinhamento", "centro")
        painel.definir("recuo_esquerda_em", "1,5")
        painel.definir("estilo", "destaque")
        painel.definir("id", "âncora-um")
        painel.definir("classe", "x y")
        painel.definir("manter_com_proximo", True)
        antes = t.t.blocos()[0]
        assert antes.alinhamento == "" and antes.estilo == "corpo" and not antes.id_persistente   # nada gravado
        assert painel.aplicar() is True
        depois = t.t.blocos()[0]
        assert depois.alinhamento == "centro" and depois.recuo_esquerda_em == 1.5 and depois.estilo == "destaque"
        assert depois.id == "âncora-um" and depois.id_persistente and depois.classe == "x y"
        assert depois.manter_com_proximo is True and m.texto_de(depois) == "um parágrafo"
        assert painel.alvo["id"] == "âncora-um" and painel.variaveis["estilo"].get() == "destaque"
        # Um desfazer só para o "Aplicar" inteiro.
        assert w.desfazer()
        volta = t.t.blocos()[0]
        assert volta.alinhamento == "" and volta.estilo == "corpo" and not volta.id_persistente and volta.classe == ""
        # Valor inválido é erro de entrada; o modelo não muda.
        w.ir_para(t.t.blocos()[0].id, 0)
        painel.atualizar(forcar=True)
        painel.definir("entrelinha", "muito")
        with pytest.raises(ValueError):
            painel.aplicar()
        assert t.t.blocos()[0].entrelinha is None
        # Foco visível: o botão Aplicar num anel de foco; os campos com a moldura do ttk.
        assert isinstance(painel.anel_aplicar, AnelDeFoco)
        painel.anel_aplicar._entrou()
        assert int(painel.anel_aplicar.cget("highlightthickness")) == 2
        painel.foco()
        assert "disabled" not in painel.botao_aplicar.state()


def test_o_painel_acompanha_o_cursor_e_so_remonta_quando_o_alvo_muda():
    figura = m.Figura(recurso="Images/x.png", alt="x", largura_pt=50)
    with _Painel([p("texto"), figura]) as t:
        w, painel = t.w, t.painel
        w.ir_para(t.t.cap.blocos[0].id, 0)
        painel.atualizar()
        painel.definir("classe", "pendente")
        w.ir_para(t.t.cap.blocos[0].id, 3)                   # mesmo alvo: os campos ficam como estavam
        painel.atualizar()
        assert painel.variaveis["classe"].get() == "pendente"
        w.selecionar_objeto(figura.id)
        alvo = painel.atualizar()
        assert alvo["tipo"] == "figura" and painel.variaveis["largura_pt"].get() == "50"
        assert painel.titulo.cget("text") == "Figura" and "classe" in painel.variaveis
        painel.definir("largura_pt", "")
        painel.definir("legenda", "A figura")
        painel.definir("alinhamento", "dir")
        assert painel.aplicar()
        fig = t.t.blocos()[1]
        assert fig.largura_pt is None and [tr.texto for tr in fig.legenda] == ["A figura"] and fig.alinhamento == "dir"
        assert "A figura" in w.widget_do_objeto(figura.id).winfo_children()[-1].cget("text")


def test_tabela_marca_de_pagina_ilha_e_nota_pelo_painel():
    tabela = m.Tabela(filas=[[m.Celula(blocos=[p("a")]), m.Celula(blocos=[p("b")])]])
    marca = m.MarcaDePagina(pagina=12)
    ilha = m.IlhaBruta(xhtml='<svg xmlns="http://www.w3.org/2000/svg"/>', elemento="svg")
    ref = m.Paragrafo(trechos=[m.Trecho(texto="n"), m.Trecho(nota="n1")])
    with _Painel([tabela, marca, ilha, ref], notas=[m.Nota(id="n1", blocos=[p("a nota", estilo="nota")])]) as t:
        w, painel = t.w, t.painel
        w.selecionar_objeto(tabela.id)
        alvo = painel.atualizar()
        assert alvo["tipo"] == "tabela" and painel.botao_acao is not None
        painel.definir("legenda", "Resultados")
        painel.definir("numero", "3")
        painel.definir("largura_pct", "80")
        painel.definir("primeira_fila_cabecalho", True)
        assert painel.aplicar()
        tab = t.t.blocos()[0]
        assert tab.numero == 3 and tab.largura_pct == 80 and tab.primeira_fila_cabecalho
        assert [tr.texto for tr in tab.legenda] == ["Resultados"] and all(c.cabecalho for c in tab.filas[0])
        assert "Tabela 3" in w.widget_do_objeto(tabela.id).legenda.cget("text")
        painel.acao("entrar_na_tabela")
        assert t.acoes[-1] == ("entrar_na_tabela", "tabela")
        # A marca de página: a página muda e o id (pg-n) acompanha; desfazer traz a antiga.
        w.selecionar_objeto(marca.id)
        assert painel.atualizar()["tipo"] == "marca"
        painel.definir("pagina", "13")
        assert painel.aplicar()
        nova = t.t.blocos()[1]
        assert isinstance(nova, m.MarcaDePagina) and nova.pagina == 13 and nova.id == "pg-13"
        assert w.widget_do_objeto("pg-13").texto == "— página 13 —"
        assert w.desfazer() and t.t.blocos()[1].id == "pg-12"
        # A ilha: o XHTML editado no painel; o que virou dialeto vira bloco do dialeto.
        w.selecionar_objeto(ilha.id)
        assert painel.atualizar()["tipo"] == "ilha" and "xhtml" in painel.caixas_de_texto
        painel.definir("xhtml", "<p>agora texto</p>")
        assert painel.aplicar()
        assert isinstance(t.t.blocos()[2], m.Paragrafo) and m.texto_de(t.t.blocos()[2]) == "agora texto"
        # A referência de nota: o tipo muda para fim.
        w.ir_para(ref.id, 1)
        alvo = painel.atualizar()
        assert alvo["tipo"] == "nota" and painel.variaveis["tipo"].get() == "rodape"
        painel.definir("tipo", "fim")
        assert painel.aplicar() and t.t.notas()[0].tipo == "fim"
        painel.acao("ir_para_nota")
        assert t.acoes[-1] == ("ir_para_nota", "nota")


# ----------------------------------------------------------------------
# AC-ED04-4 (o painel e o relatório)
# ----------------------------------------------------------------------

def test_ac4_link_inexistente_fica_vermelho_no_painel_e_seguir_o_poe_no_relatorio():
    with _Painel([m.Paragrafo(trechos=[m.Trecho(texto="ver "), m.Trecho(texto="alvo", link="x.xhtml#nao-existe"),
                                       m.Trecho(texto=" e "), m.Trecho(texto="ok", link="x.xhtml#alvo")])]) as t:
        w, painel = t.w, t.painel
        w.ir_para(t.t.cap.blocos[0].id, 5)
        alvo = painel.atualizar()
        assert alvo["tipo"] == "link" and painel.variaveis["href"].get() == "x.xhtml#nao-existe"
        assert str(painel.entradas["href"].cget("foreground")) == COR_DE_ERRO
        assert "não existe" in painel.aviso.cget("text")
        painel.definir("href", "x.xhtml#alvo")                # digitar um destino que existe limpa o vermelho
        assert str(painel.entradas["href"].cget("foreground")) == ""
        painel.definir("titulo", "dica")
        assert painel.aplicar()
        trecho = t.t.blocos()[0].trechos[1]
        assert trecho.link == "x.xhtml#alvo" and trecho.titulo == "dica" and trecho.texto == "alvo"
        painel.definir("href", "")
        with pytest.raises(ValueError):
            painel.aplicar()
    with Janela() as t:
        j, texto = t.j, t.texto
        paragrafo = t.bloco(lambda b: isinstance(b, m.Paragrafo) and any(tr.link == "cap2.xhtml#alvo"
                                                                          for tr in b.trechos))
        desloc = t.deslocamento_do_link(paragrafo, "cap2.xhtml#alvo")
        texto.ir_para(paragrafo.id, desloc + 1)
        texto.selecionar(desloc, desloc + 7)
        texto.aplicar(link="cap2.xhtml#nao-existe")
        texto.ir_para(paragrafo.id, desloc + 1)
        painel = j.painel_de_propriedades
        alvo = painel.atualizar(forcar=True)
        assert alvo["tipo"] == "link" and str(painel.entradas["href"].cget("foreground")) == COR_DE_ERRO
        assert j.executar("seguir_link") is None
        assert "não existe" in t.caixas.entradas()[-1] and not t.caixas.falhas()
        assert j.resultados.itens and j.resultados.itens[0].mensagem == "destino inexistente: cap2.xhtml#nao-existe"
        assert j.resultados.itens[0].dados["bloco"] == paragrafo.id
        assert j.aba_ativa().arquivo == "cap1.xhtml"
        # Um destino que existe: sem vermelho, e `destino_existe` sabe de âncora e de nota.
        assert j.destino_existe("cap2.xhtml#alvo") and j.destino_existe("cap2.xhtml")
        assert j.destino_existe("#n1") and not j.destino_existe("cap9.xhtml") and not j.destino_existe("#zzz")
        assert j.destino_existe("https://example.org/")


def test_alt_enter_mostra_o_painel_e_o_foca_e_o_painel_segue_a_celula_ativa():
    with Janela() as t:
        j, texto = t.j, t.texto
        j.mostrar_painel("propriedades", False)
        assert not j.paineis["propriedades"].visivel
        figura = t.bloco(lambda b: isinstance(b, m.Figura))
        texto.selecionar_objeto(figura.id)
        alvo = j.executar("propriedades_do_objeto")
        assert alvo["tipo"] == "figura" and j.paineis["propriedades"].visivel
        assert j.menus.estado("propriedades_do_objeto") == "normal"
        # O cursor num parágrafo: o painel segue (o `<<CursorMoveu>>` chama `atualizar`).
        paragrafo = t.bloco(lambda b: isinstance(b, m.Paragrafo) and not isinstance(b, m.Titulo))
        texto.ir_para(paragrafo.id, 0)
        painel = j.painel_de_propriedades
        assert painel.atualizar()["tipo"] == "paragrafo" and painel.alvo["id"] == paragrafo.id
        # Trocar de aba troca o alvo do painel.
        j.abrir_capitulo("cap2.xhtml")
        assert painel.texto_rico is j.aba_ativa().widget
        assert painel.atualizar(forcar=True)["tipo"] == "paragrafo"


def test_o_painel_sem_editor_diz_que_nao_ha_nada_e_nao_quebra():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        painel = PainelDePropriedades(raiz, None)
        assert painel.atualizar()["tipo"] == "" and painel.aplicar() is False
        assert "disabled" in painel.botao_aplicar.state()
    finally:
        raiz.destroy()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
