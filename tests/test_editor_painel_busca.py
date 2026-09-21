"""
Testes do painel Busca na janela (ED-06; SPEC_EDITOR §8.12, §9.4): `Ctrl+F` abre a caixa
com a seleção, `F3` percorre as ocorrências do capítulo e dá a volta, a ocorrência vira
seleção no texto rico (parágrafo, lista, nota, célula) e no código, "Substituir" troca a
selecionada preservando o formato e entra no desfazer, "Substituir todos" percorre o
livro — inclusive o capítulo que não está aberto, com um ponto de desfazer por capítulo
(AC-ED06-2) —, "Contar" e "Listar" (Resultados), os escopos "texto marcado" e "arquivos
marcados", e o regex com `\\1`.

Rodar sem pytest:      python tests/test_editor_painel_busca.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import busca, modelo as m
from editor_ambiente import Janela
from ui.editor.busca import PainelDeBusca
from ui.editor.tabela import GradeDeTabela


def _selecionado(widget):
    ativo = widget.ativo() if hasattr(widget, "ativo") else widget
    sel = ativo.selecao()
    return ativo.texto.get(*sel) if sel else None


def _textos(cap):
    return [m.texto_de(b) for b in cap.blocos]


# ----------------------------------------------------------------------
# A caixa e o percurso
# ----------------------------------------------------------------------

def test_ctrl_f_abre_a_caixa_com_a_selecao_e_f3_percorre_e_da_a_volta():
    with Janela() as t:
        j = t.j
        texto = t.texto
        texto.ir_para(texto.ordem[1], 0)
        texto.selecionar(0, 8)                      # "Primeira"
        j.executar("localizar")
        assert j.busca.var_texto.get() == "Primeira"
        assert j.inferior.select() == str(j.busca) and isinstance(j.busca, PainelDeBusca)
        # "Seleção" só entra na lista de escopos quando há seleção
        assert "Seleção" in j.busca.campo_escopo["values"]
        j.busca.definir(texto="página", escopo="capitulo", circular=True)
        cap = texto.sincronizar()
        esperadas = busca.procurar_no_capitulo(cap, busca.compilar(j.busca.opcoes()))
        assert len(esperadas) >= 13
        vistas = []
        for _ in esperadas:
            achada = j.executar("localizar_proximo")
            assert achada is not None
            vistas.append((achada.alvo.bloco_id, achada.ini, _selecionado(texto).lower()))
        assert [v[2] for v in vistas] == ["página"] * len(esperadas)
        assert [(v[0], v[1]) for v in vistas] == [(o.alvo.bloco_id, o.ini) for o in esperadas]
        assert j.campos["aviso"].cget("text").startswith(f"{len(esperadas)} de {len(esperadas)}")
        # a próxima dá a volta e avisa
        j.executar("localizar_proximo")
        assert "voltou ao início" in j.campos["aviso"].cget("text")
        # para trás, a partir da primeira, vai à última
        j.executar("localizar_anterior")
        assert _selecionado(texto).lower() == "página" and j.campos["aviso"].cget("text").startswith(
            f"{len(esperadas)} de")
        # sem circular, do fim para a frente não acha
        j.busca.definir(circular=False)
        assert j.executar("localizar_proximo") is None
        assert "não encontrado" in j.campos["aviso"].cget("text")
        # o histórico guarda a busca e vai para as preferências
        assert j.busca.historico.itens[0] == "página" and t.settings.get("editor")["buscas"][0] == "página"


def test_a_ocorrencia_vira_selecao_na_lista_na_nota_e_na_celula_e_no_codigo():
    with Janela() as t:
        j = t.j
        texto = t.texto
        j.busca.definir(texto="continuação de b")
        achada = j.executar("localizar_proximo")
        assert achada.alvo.caminho == ("lista", 2) and _selecionado(texto) == "continuação de b"
        j.busca.definir(texto="Segundo parágrafo")
        achada = j.executar("localizar_proximo")
        assert achada.alvo.caminho[0] == "nota" and _selecionado(texto) == "Segundo parágrafo"
        assert texto.em_nota() == "n2"
        j.busca.definir(texto="Pontos")
        achada = j.executar("localizar_proximo")
        assert achada.alvo.caminho == ("celula", 0, 1, 0)
        grade = texto.widget_do_objeto("tab1")
        assert isinstance(grade, GradeDeTabela) and grade.celula_atual() == (0, 1)
        assert _selecionado(grade.celula(0, 1)) == "Pontos"       # (o foco de verdade não existe sem tela)
        # a legenda de uma figura seleciona o objeto
        j.executar("escape")
        j.busca.definir(texto="A foto")
        achada = j.executar("localizar_proximo")
        assert achada.alvo.caminho == ("legenda",) and texto.objeto_no_cursor().id == "fig1"
        # no código, a ocorrência é linha e coluna, e a seleção é o texto cru
        j.executar("alternar_modo")
        editor = j.aba_ativa().widget
        j.busca.definir(texto="<h2")
        achada = j.executar("localizar_proximo")
        assert achada.cru and achada.linha > 1 and editor.texto.get("sel.first", "sel.last") == "<h2"
        assert editor.posicao[0] == achada.linha


# ----------------------------------------------------------------------
# Substituir
# ----------------------------------------------------------------------

def test_substituir_a_selecionada_preserva_o_formato_e_entra_no_desfazer():
    with Janela() as t:
        j = t.j
        texto = t.texto
        j.busca.definir(texto="Página marcada", substituto="Folha anotada")
        assert j.executar("localizar_proximo") is not None
        assert j.executar("substituir_atual") == "Folha anotada"
        bloco = texto.modelo_de(texto.bloco_atual())
        assert m.texto_de(bloco).startswith("Folha anotada aqui e uma ilha")
        # a marca de página e a ilha inline continuam no parágrafo
        assert any(tr.pagina == 7 for tr in bloco.trechos) and any(tr.ilha for tr in bloco.trechos)
        assert texto.sujo and j.projeto.historico.pode_desfazer("cap1.xhtml")
        assert j.executar("desfazer")
        assert m.texto_de(texto.modelo_de(texto.bloco_atual())).startswith("Página marcada aqui")
        # sem ocorrência selecionada, "Substituir" é erro de entrada
        texto.ir_para(texto.ordem[0], 0)
        j.executar("substituir_atual")
        assert "selecione uma ocorrência" in t.caixas.entradas()[-1]
        # "Substituir e localizar" troca e segue para a próxima
        j.busca.definir(texto="Texto da página", substituto="Texto da folha")
        j.executar("localizar_proximo")
        seguinte = j.executar("substituir_e_localizar")
        assert seguinte is not None and _selecionado(texto) == "Texto da página"
        cap = texto.sincronizar()
        assert sum("Texto da folha" in m.texto_de(b) for b in cap.blocos) == 1


def test_substituir_todos_no_livro_toca_o_capitulo_fechado_com_um_ponto_por_capitulo():
    with Janela() as t:
        j = t.j
        texto = t.texto
        assert j.abas.por_arquivo("cap2.xhtml") is None
        j.busca.definir(texto=r"(Fim|Texto da página) ?(\d*)", substituto=r"[\1 \2]", regex=True, escopo="livro",
                        maiusculas=True)
        contagem = j.executar("substituir_todos")
        assert contagem == {"cap1.xhtml": 12, "cap2.xhtml": 1}
        cap1 = texto.sincronizar()
        assert sum(m.texto_de(b).startswith("[Texto da página ") for b in cap1.blocos) == 12
        cap2 = j.projeto.livro.capitulo("cap2.xhtml")
        assert _textos(cap2)[-1] == "[Fim ]."
        assert j.projeto.sujo and j.abas.por_arquivo("cap2.xhtml") is None
        # Resultados lista a contagem por arquivo; o status resume
        assert [(r.arquivo, r.mensagem) for r in j.resultados.itens] == [("cap1.xhtml", "12 substituição(ões)"),
                                                                        ("cap2.xhtml", "1 substituição(ões)")]
        assert "13 substituição(ões) em 2 arquivo(s)" in j.campos["aviso"].cget("text")
        # o capítulo aberto: um desfazer só devolve as 12; o fechado: um ponto próprio no histórico
        assert j.executar("desfazer")
        cap1 = texto.sincronizar()
        assert sum(m.texto_de(b).startswith("Texto da página") for b in cap1.blocos) == 12
        ponto = j.projeto.historico.desfazer("cap2.xhtml")
        assert ponto is not None and ponto.rotulo == "substituir todos"
        from core.editor.historico import aplicar

        aplicar(cap2, ponto, "antes")
        assert _textos(cap2)[-1] == "Fim."


def test_substituir_todos_no_codigo_e_na_selecao():
    with Janela() as t:
        j = t.j
        j.executar("alternar_modo")
        editor = j.aba_ativa().widget
        j.busca.definir(texto="<p>Texto da página (\\d+)\\.</p>", substituto="<p>Pág. \\1</p>", regex=True,
                        escopo="capitulo")
        assert j.executar("substituir_todos") == {"cap1.xhtml": 12}
        assert editor.texto_todo().count("<p>Pág. ") == 12 and editor.sujo
        assert editor.desfazer() and editor.texto_todo().count("<p>Pág. ") == 0
        # na seleção: só a primeira linha selecionada
        ini = editor.texto.search("Texto da página 11", "1.0")
        assert ini
        editor.texto.tag_add("sel", f"{ini} linestart", f"{ini} lineend")
        j.busca.definir(escopo="selecao")
        assert j.executar("substituir_todos") == {"cap1.xhtml": 1}
        assert editor.texto_todo().count("<p>Pág. ") == 1


# ----------------------------------------------------------------------
# Contar, listar, escopos marcados
# ----------------------------------------------------------------------

def test_contar_e_listar_vao_ao_status_e_a_resultados_e_o_resultado_ativado_seleciona():
    with Janela() as t:
        j = t.j
        texto = t.texto
        j.busca.definir(texto="Capítulo", escopo="livro")
        contagem = j.executar("contar_ocorrencias")
        assert contagem == {"cap1.xhtml": 2, "cap2.xhtml": 1}
        assert any(c[0] == "informar" and "3 ocorrência(s)" in c[1] for c in t.caixas.chamadas)
        itens = j.executar("listar_ocorrencias")
        assert [(r.arquivo, r.dados["comprimento"]) for r in itens] == [("cap1.xhtml", 8)] * 2 + [("cap2.xhtml", 8)]
        assert len(j.resultados) == 3 and j.inferior.select() == str(j.resultados)
        # ativar o terceiro abre o cap2 e seleciona a ocorrência
        j.resultados.ativar(2)
        assert j.aba_ativa().arquivo == "cap2.xhtml" and _selecionado(j.aba_ativa().widget) == "Capítulo"
        # ativar o primeiro volta ao cap1, no bloco certo
        j.resultados.ativar(0)
        assert j.aba_ativa().arquivo == "cap1.xhtml" and _selecionado(texto) == "Capítulo"
        assert texto.bloco_atual() == "cap1-t"


def test_texto_marcado_e_arquivos_marcados_restringem_o_escopo():
    with Janela() as t:
        j = t.j
        texto = t.texto
        # sem marca, o escopo "texto marcado" é erro de entrada
        j.busca.definir(texto="página", escopo="marcado")
        j.executar("localizar_proximo")
        assert "não há texto marcado" in t.caixas.entradas()[-1]
        # marca os três primeiros "Texto da página"
        ids = [i for i in texto.ordem if m.texto_de(texto.modelo_de(i) or m.Paragrafo(trechos=[])).startswith(
            "Texto da página")]
        fim = len(m.texto_de(texto.modelo_de(ids[2])))
        texto.selecionar_indices(texto.indice_de(ids[0], 0), texto.indice_de(ids[2], fim))
        assert j.executar("marcar_texto") is True and j.busca.opcoes().escopo == "marcado"
        assert j.executar("contar_ocorrencias") == {"cap1.xhtml": 3}
        # a marca some sem seleção
        texto.texto.tag_remove("sel", "1.0", "end")
        assert j.executar("marcar_texto") is False
        # arquivos marcados: nenhum marcado é erro; marca o cap2 pelo navegador
        j.busca.definir(escopo="marcados")
        j.executar("contar_ocorrencias")
        assert "nenhum arquivo marcado" in t.caixas.entradas()[-1]
        assert j.executar("marcar_arquivo", "cap2.xhtml") is True and j.arquivos_marcados == {"cap2.xhtml"}
        assert j.navegador.item("cap2.xhtml", "text").startswith("✓ ")
        j.busca.definir(texto="Fim")
        assert j.executar("contar_ocorrencias") == {"cap2.xhtml": 1}
        assert j.executar("marcar_arquivo", "cap2.xhtml") is False and not j.arquivos_marcados
        # escopo "abas abertas": só o cap1 está aberto
        j.busca.definir(texto="Capítulo", escopo="abas")
        assert j.executar("contar_ocorrencias") == {"cap1.xhtml": 2}


def test_o_regex_invalido_e_a_caixa_vazia_sao_erros_de_entrada_e_o_menu_liga_os_comandos():
    with Janela() as t:
        j = t.j
        j.busca.definir(texto="(", regex=True)
        j.executar("localizar_proximo")
        assert "expressão regular inválida" in t.caixas.entradas()[-1]
        j.busca.definir(texto="")
        j.executar("localizar_proximo")
        assert "digite o que procurar" in t.caixas.entradas()[-1]
        for nome in ("localizar", "substituir", "localizar_proximo", "localizar_anterior", "substituir_e_localizar",
                     "substituir_todos", "contar_ocorrencias", "listar_ocorrencias", "marcar_texto",
                     "marcar_arquivo", "ir_para", "inserir_simbolo", "estatisticas", "ortografia", "dicionario"):
            assert j.menus.estado(nome) == "normal", nome
        assert j.menus.estado("codigo_unicode") == "normal"
        j.executar("alternar_modo")
        assert j.menus.estado("codigo_unicode") == "disabled" and j.menus.estado("localizar") == "normal"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
