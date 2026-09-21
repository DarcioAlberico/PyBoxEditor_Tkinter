"""
Testes da grade de tabela do modo texto (ED-04; SPEC_EDITOR §8.6, AC-ED04-2): a tabela
3×3 preenchida por `proxima_celula()`, `Tab` na última célula que cria uma fila, inserir
fila, cabeçalho, excluir coluna (e a tabela continua retangular), `sair()` que devolve
o cursor ao texto de fora, `entrar()` que vai à primeira célula, `colspan` que vira ilha,
20×20 que carrega como grade (o tempo está em `scripts/medir_editor.py`) e 21×20 que não
(caixa), o desfazer sobre a tabela inteira, notas e negrito dentro de células, as setas
nas bordas e o `Esc` — e, num teste `gui`, o foco de verdade.

Rodar sem pytest:      python tests/test_editor_tabela.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import modelo as m, xhtml
from editor_ambiente import Janela, Widget, p
from ui.editor import objetos
from ui.editor.tabela import LIMITE, GradeDeTabela


def _tabela(filas, colunas, cabecalho=False):
    return m.Tabela(filas=[[m.Celula(blocos=[p(f"c{f}{c}")], cabecalho=bool(cabecalho and f == 0))
                            for c in range(colunas)] for f in range(filas)],
                    primeira_fila_cabecalho=cabecalho)


def _textos(tabela):
    return [[" ".join(m.texto_de(b) for b in c.blocos) for c in fila] for fila in tabela.filas]


# ----------------------------------------------------------------------
# AC-ED04-2
# ----------------------------------------------------------------------

def test_ac2_tabela_3x3_por_proxima_celula_fila_cabecalho_excluir_coluna_sair_e_entrar():
    with Widget([p("antes"), p("depois")]) as t:
        w = t.w
        w.ir_para(t.cap.blocos[0].id, 5)
        tabela = m.Tabela(filas=[[m.Celula(blocos=[]) for _ in range(3)] for _ in range(3)])
        w.inserir_objeto(tabela)
        grade = w.widget_do_objeto(tabela.id)
        assert isinstance(grade, GradeDeTabela) and grade.texto == "Tabela: 3×3"
        celula = grade.entrar()
        assert grade.celula_atual() == (0, 0) and celula is grade.celulas[0][0]
        for k in range(9):
            grade.celula(*grade.celula_atual()).inserir(f"c{k}")
            if k < 8:
                grade.proxima_celula()
        assert grade.celula_atual() == (2, 2)
        modelo = t.blocos()[1]
        assert isinstance(modelo, m.Tabela) and _textos(modelo) == [["c0", "c1", "c2"], ["c3", "c4", "c5"],
                                                                     ["c6", "c7", "c8"]]
        # `Tab` na última célula cria uma fila e vai à primeira célula dela.
        grade.proxima_celula()
        assert grade.celula_atual() == (3, 0) and len(t.blocos()[1].filas) == 4
        # Inserir fila acima da atual; a primeira fila vira cabeçalho (<th> em toda célula dela).
        grade.entrar(1, 1)
        grade.inserir_fila(depois=False)
        assert _textos(t.blocos()[1])[1] == ["", "", ""] and len(t.blocos()[1].filas) == 5
        grade.alternar_cabecalho()
        modelo = t.blocos()[1]
        assert modelo.primeira_fila_cabecalho and all(c.cabecalho for c in modelo.filas[0])
        assert not any(c.cabecalho for c in modelo.filas[1])
        escrito = xhtml.escrever(w.sincronizar())
        assert "<thead>" in escrito and escrito.count("<th>") == 3
        # Excluir a coluna do meio: continua retangular (INV-04).
        grade.entrar(0, 1)
        grade.excluir_coluna()
        modelo = t.blocos()[1]
        assert modelo.colunas == 2 and {len(f) for f in modelo.filas} == {2}
        assert _textos(modelo)[0] == ["c0", "c2"] and _textos(modelo)[2] == ["c3", "c5"]
        assert m.igual(w.sincronizar(reler=True).blocos[1], modelo)
        # `sair()` devolve o cursor ao texto de fora, sobre a tabela; `entrar()` vai à primeira célula.
        grade.sair(0)
        assert w.objeto_no_cursor() is not None and w.objeto_no_cursor().id == tabela.id
        grade.sair(-1)
        assert w.bloco_atual() == t.cap.blocos[0].id and w.posicao() == (t.cap.blocos[0].id, 5)
        grade.sair(1)
        assert w.bloco_atual() == t.cap.blocos[1].id
        assert grade.entrar() is grade.celulas[0][0] and grade.celula_atual() == (0, 0)
        # Excluir a última fila e a última coluna é recusado (para tirá-las, apaga-se a tabela).
        pequena = m.Tabela(filas=[[m.Celula(blocos=[p("x")])]])
        w.ir_para(t.cap.blocos[1].id, 0)
        w.inserir_objeto(pequena)
        g2 = w.widget_do_objeto(pequena.id)
        with pytest.raises(ValueError):
            g2.excluir_fila()
        with pytest.raises(ValueError):
            g2.excluir_coluna()


def test_ac2_colspan_vira_ilha_20x20_carrega_como_grade_e_21x20_como_caixa():
    xhtml_com_colspan = ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head><body>'
                         '<table><tr><td colspan="2">a</td></tr><tr><td>b</td><td>c</td></tr></table>'
                         "</body></html>")
    cap = xhtml.ler(xhtml_com_colspan, "Text/c.xhtml")
    assert isinstance(cap.blocos[0], m.IlhaBruta) and cap.blocos[0].elemento == "table"
    with Widget(cap.blocos) as t:
        assert isinstance(t.w.widget_do_objeto(cap.blocos[0].id), objetos.ObjetoDeIlha)
        assert xhtml.escrever(t.w.sincronizar()).count('colspan="2"') == 1
    grande = _tabela(20, 20)
    maior = _tabela(21, 20)
    with Widget([p("a"), grande, maior, p("b")]) as t:
        w = t.w
        assert isinstance(w.widget_do_objeto(grande.id), GradeDeTabela)
        assert isinstance(w.widget_do_objeto(maior.id), objetos.ObjetoGenerico)
        assert len(w.widget_do_objeto(grande.id).celulas) == 20 and LIMITE == 400
        volta = w.sincronizar(reler=True)
        assert m.igual(volta, t.cap)
        celula = w.widget_do_objeto(grande.id).entrar(19, 19)
        celula.inserir("!")
        assert _textos(t.blocos()[1])[19][19] == "c1919!"


def test_editar_uma_celula_e_um_ponto_sobre_a_tabela_inteira_e_a_digitacao_coalesce():
    tabela = _tabela(2, 2)
    with Widget([p("a"), tabela, p("b")]) as t:
        w = t.w
        grade = w.widget_do_objeto(tabela.id)
        celula = grade.entrar(0, 0)
        assert not w.pode_desfazer
        celula.inserir("x")
        celula.inserir("y")
        assert w.pode_desfazer and _textos(t.blocos()[1])[0][0] == "c00xy"
        grade.inserir_fila()                                   # estrutura: ponto próprio
        assert len(t.blocos()[1].filas) == 3
        assert w.desfazer() and len(t.blocos()[1].filas) == 2 and _textos(t.blocos()[1])[0][0] == "c00xy"
        assert w.desfazer() and _textos(t.blocos()[1])[0][0] == "c00"
        assert not w.pode_desfazer
        assert w.refazer() and _textos(t.blocos()[1])[0][0] == "c00xy"
        # Depois de desfazer, a grade nasce de novo do modelo e continua editável.
        grade = w.widget_do_objeto(tabela.id)
        assert isinstance(grade, GradeDeTabela)
        celula = grade.entrar(1, 1)
        celula.desfazer()                                     # o desfazer da célula é o do texto de fora
        assert _textos(t.blocos()[1])[0][0] == "c00"


def test_negrito_nota_e_link_dentro_da_celula_e_uma_celula_nao_recebe_tabela():
    tabela = _tabela(1, 2)
    with Widget([p("fora"), tabela]) as t:
        w = t.w
        grade = w.widget_do_objeto(tabela.id)
        celula = grade.entrar(0, 0)
        celula.selecionar(0, 3)
        celula.alternar("negrito")
        assert t.blocos()[1].filas[0][0].blocos[0].trechos[0].negrito is True
        celula.ir_para(celula.bloco_atual(), 3)
        nota = celula.inserir_nota("rodape")
        assert w.em_nota() == nota and w.ids_das_notas() == [nota]
        w.inserir("nota da célula")
        assert w.voltar_da_nota()
        cap = w.sincronizar()
        assert [tr.nota for tr in cap.blocos[1].filas[0][0].blocos[0].trechos if tr.nota] == [nota]
        assert m.texto_de(cap.notas[0]) == "nota da célula"
        escrito = xhtml.escrever(cap)
        assert escrito.count(f'href="#{nota}"') == 1 and f'id="{nota}"' in escrito
        with pytest.raises(ValueError):
            celula.inserir_objeto(_tabela(1, 1))
        with pytest.raises(ValueError):
            celula.inserir_quebra_de_pagina()
        # Apagar a referência na célula apaga a nota do capítulo.
        celula.ir_para(celula.bloco_atual(), 3)
        assert celula.backspace() is False and celula.selecao() is not None
        assert celula.backspace() is True
        assert w.sincronizar().notas == [] and w.ids_das_notas() == []
        assert w.desfazer() and w.ids_das_notas() == [nota]


def test_setas_nas_bordas_tab_e_esc_pelos_handlers_da_celula():
    tabela = _tabela(2, 2)
    with Widget([p("a"), tabela, p("b")]) as t:
        w = t.w
        grade = w.widget_do_objeto(tabela.id)
        celula = grade.entrar(0, 0)
        assert celula.ligacoes["<Tab>"](None) == "break" and grade.celula_atual() == (0, 1)
        celula = grade.celula(0, 1)
        assert celula.ligacoes["<Shift-Tab>"](None) == "break" and grade.celula_atual() == (0, 0)
        celula = grade.celula(0, 0)
        celula.texto.mark_set("insert", "1.0")
        assert celula.ligacoes["<Up>"](None) == "break"                    # primeira fila: sai para o bloco anterior
        assert w.bloco_atual() == t.cap.blocos[0].id
        celula = grade.entrar(1, 0)
        assert celula.ligacoes["<Down>"](None) == "break" and w.bloco_atual() == t.cap.blocos[2].id
        celula = grade.entrar(0, 0)
        assert celula.ligacoes["<Down>"](None) == "break" and grade.celula_atual() == (1, 0)
        celula = grade.entrar(0, 1)
        celula.texto.mark_set("insert", "1.0")
        assert celula.ligacoes["<Left>"](None) == "break" and grade.celula_atual() == (0, 0)
        celula = grade.celula(0, 0)
        celula.ir_para_o_fim()
        assert celula.ligacoes["<Right>"](None) == "break" and grade.celula_atual() == (0, 1)
        celula = grade.celula(0, 1)
        celula.texto.mark_set("insert", "1.1")
        assert celula.ligacoes["<Left>"](None) is None                    # no meio: a seta é do Text
        assert celula.ligacoes["<Escape>"](None) == "break" and w.objeto_no_cursor().id == tabela.id
        assert celula.ligacoes["<MouseWheel>"](type("E", (), {"delta": 120})()) == "break"
        assert w.ligacoes["<Escape>"](None) is None                        # fora da célula, Esc é da janela


@pytest.mark.gui
def test_gui_sair_devolve_o_foco_de_verdade_ao_texto_de_fora_e_o_foco_e_visivel():
    tabela = _tabela(2, 2)
    with Widget([p("a"), tabela, p("b")]) as t:
        t.raiz.deiconify()
        t.raiz.focus_force()
        t.raiz.update()
        w = t.w
        grade = w.widget_do_objeto(tabela.id)
        celula = grade.entrar(0, 1)
        t.raiz.update()
        assert t.raiz.focus_get() is celula.texto and grade.celula_com_foco() == (0, 1)
        assert int(celula.texto.cget("highlightthickness")) >= 1
        grade.sair(0)
        t.raiz.update()
        assert t.raiz.focus_get() is w.texto and w.ativo() is w


def test_inserir_tabela_pela_janela_com_formulario_e_o_submenu_tabela():
    with Janela() as t:
        j, texto = t.j, t.texto
        t.caixas.tabela_resposta = (2, 3, True)
        texto.ir_para(texto.ordem_do_capitulo[1], 0)
        tid = j.executar("inserir_tabela")
        tabela = t.bloco(lambda b: b.id == tid)
        assert len(tabela.filas) == 2 and tabela.colunas == 3 and tabela.primeira_fila_cabecalho
        grade = texto.widget_do_objeto(tid)
        assert grade.celula_atual() == (0, 0)
        j.executar("tabela_coluna_direita")
        j.executar("tabela_fila_abaixo")
        tabela = t.bloco(lambda b: b.id == tid)
        assert len(tabela.filas) == 3 and tabela.colunas == 4
        assert j.menus.estado("tabela_excluir") == "normal" and j.menus.estado("inserir_tabela") == "normal"
        j.executar("tabela_excluir")
        assert not any(b.id == tid for b in texto.sincronizar().blocos)
        assert texto.desfazer() and t.bloco(lambda b: b.id == tid).colunas == 4
        # Fora de uma tabela, o submenu diz o que fazer (erro de entrada, janela viva).
        texto.ir_para(texto.ordem_do_capitulo[0], 0)
        assert j.executar("tabela_excluir_fila") is None and "tabela" in t.caixas.entradas()[-1]
        assert not t.caixas.falhas()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
