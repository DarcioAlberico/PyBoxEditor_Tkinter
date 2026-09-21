"""
Testes de `core/editor/busca.py` (ED-06; SPEC_EDITOR §8.12): o adaptador de trechos acha
o que o XHTML cru parte (AC-ED06-1); regex no livro inteiro com contagem por arquivo,
capítulos não abertos e um ponto de desfazer por capítulo (AC-ED06-2); "circular"; as
opções (maiúsculas, palavra inteira, mínimo, espaço casa o inseparável — AC-ED06-7); a
substituição que preserva o formato, a nota e a marca de página; e "ir para"
(AC-ED06-4, a parte pura).

Rodar sem pytest:      python tests/test_editor_busca.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import busca, modelo as m, xhtml
from core.editor.historico import Historico, aplicar
from core.editor.modelo import Capitulo, Livro, Metadados, Paragrafo, Trecho

NBSP = chr(0xA0)


def _p(*trechos, **kw):
    return Paragrafo(trechos=[t if isinstance(t, Trecho) else Trecho(texto=t) for t in trechos], **kw)


def _cap(*blocos, arquivo="c.xhtml", notas=()):
    return Capitulo(arquivo=arquivo, blocos=list(blocos), notas=list(notas))


def _pad(texto, **kw):
    return busca.compilar(busca.Opcoes(texto=texto, **kw))


# ----------------------------------------------------------------------
# AC-ED06-1: o adaptador de trechos
# ----------------------------------------------------------------------

def test_ac1_nimzowitsch_com_o_w_em_negrito_e_achado_no_adaptador_e_nao_no_cru():
    cap = _cap(_p("Nimzo", Trecho(texto="w", negrito=True), "itsch played 1.e4"))
    padrao = _pad("Nimzowitsch")
    achadas = busca.procurar_no_capitulo(cap, padrao)
    assert [(o.ini, o.fim, o.texto) for o in achadas] == [(0, 11, "Nimzowitsch")]
    assert achadas[0].alvo.caminho == ("bloco",) and achadas[0].alvo.deslocamento == 0
    cru = xhtml.escrever(cap)
    assert "<strong>w</strong>" in cru
    assert busca.procurar_no_cru(cru, padrao) == []
    # no cru, a busca acha o que está literalmente lá, com linha e coluna
    achada = busca.procurar_no_cru(cru, _pad("<strong>"))[0]
    assert achada.cru and achada.linha >= 1 and achada.coluna >= 1 and achada.onde.startswith("linha ")


def test_os_alvos_cobrem_lista_citacao_tabela_legenda_e_nota_com_o_deslocamento_certo():
    livro = editor_livros.livro_completo()
    cap = livro.capitulos[0]
    alvos = busca.alvos_do_capitulo(cap)
    caminhos = {a.caminho[0] for a in alvos}
    assert caminhos >= {"bloco", "lista", "citacao", "celula", "legenda", "nota"}
    lista = next(b for b in cap.blocos if isinstance(b, m.Lista))
    da_lista = [a for a in alvos if a.bloco_id == lista.id]
    # "item a" (6) + 1, "item b" (6) + 1, "continuação de b" (16) + 1, "sub b1"
    assert [(a.texto, a.deslocamento) for a in da_lista] == [("item a", 0), ("item b", 7), ("continuação de b", 14),
                                                             ("sub b1", 31)]
    assert all(a.deslocamento is None for a in alvos if a.caminho[0] in ("celula", "legenda"))
    nota = [a for a in alvos if a.caminho[0] == "nota" and a.caminho[1] == "n2"]
    assert [a.texto for a in nota] == ["Nota de fim.", "Segundo parágrafo."]
    assert nota[0].bloco_id == cap.nota("n2").blocos[0].id and nota[0].enderecavel
    # `paragrafo_do_alvo` devolve o parágrafo de cada um
    for alvo in alvos:
        p = busca.paragrafo_do_alvo(cap, alvo)
        if alvo.caminho[0] == "legenda":
            assert p is None
        else:
            assert isinstance(p, Paragrafo) and m.texto_de(p) == alvo.texto
    # a ocorrência numa célula diz a célula; numa nota, a nota
    assert busca.procurar_no_capitulo(cap, _pad("Pontos"))[0].onde == "tabela, célula 1,2"
    assert busca.procurar_no_capitulo(cap, _pad("Nota de fim"))[0].onde == "nota n2"
    assert busca.procurar_no_capitulo(cap, _pad("Resultados"))[0].onde == "legenda"


# ----------------------------------------------------------------------
# AC-ED06-2: regex no livro inteiro, contagem por arquivo, desfazer por capítulo, circular
# ----------------------------------------------------------------------

def _livro_de_tres():
    caps = [_cap(_p("O cavalo salta. O cavalo come."), _p("Cavalo de novo."), arquivo="a.xhtml"),
            _cap(_p("Sem nada aqui."), arquivo="b.xhtml"),
            _cap(_p("Um cavalo só, "), _p("e o bispo."), arquivo="c.xhtml")]
    caps[2].texto_cru = xhtml.escrever(caps[2])
    return Livro(metadados=Metadados(titulo="T"), capitulos=caps)


def test_ac2_regex_no_livro_inteiro_conta_por_arquivo_e_desfaz_um_capitulo_de_cada_vez():
    livro = _livro_de_tres()
    padrao = _pad(r"cav(alo)", regex=True)
    assert busca.contar_por_arquivo(livro, padrao) == {"a.xhtml": 3, "c.xhtml": 1}
    historico = Historico()
    opcoes = busca.Opcoes(texto=r"cav(alo)", substituto=r"CAV\1", regex=True)
    trocas = {c.arquivo: busca.substituir_tudo_no_capitulo(c, padrao, r"CAV\1", opcoes, historico)
              for c in livro.capitulos}
    assert trocas == {"a.xhtml": 3, "b.xhtml": 0, "c.xhtml": 1}
    assert [m.texto_de(b) for b in livro.capitulos[0].blocos] == ["O CAValo salta. O CAValo come.", "CAValo de novo."]
    assert "CAValo" in livro.capitulos[2].texto_cru          # o capítulo em texto cru também
    # um ponto por capítulo: desfazer o de `a` devolve os dois blocos e não toca o de `c`
    assert historico.capitulos_com_historico() == ["a.xhtml", "c.xhtml"]
    ponto = historico.desfazer("a.xhtml")
    assert ponto is not None and len(ponto.ids) == 2 and ponto.rotulo == "substituir todos"
    aplicar(livro.capitulos[0], ponto, "antes")
    assert [m.texto_de(b) for b in livro.capitulos[0].blocos] == ["O cavalo salta. O cavalo come.", "Cavalo de novo."]
    assert "CAValo" in livro.capitulos[2].texto_cru
    assert historico.desfazer("b.xhtml") is None


def test_circular_volta_ao_inicio_e_a_direcao_para_tras_usa_o_fim_da_ocorrencia():
    cap = _cap(_p("um dois um dois um"))
    ocorrencias = busca.procurar_no_capitulo(cap, _pad("um"))
    assert [o.ini for o in ocorrencias] == [0, 8, 16]
    assert busca.proxima(ocorrencias, (0, 3), 1) == (ocorrencias[1], False)
    assert busca.proxima(ocorrencias, (0, 17), 1, circular=True) == (ocorrencias[0], True)
    assert busca.proxima(ocorrencias, (0, 17), 1, circular=False) == (None, False)
    # para trás, a partir do começo de uma ocorrência selecionada, vem a anterior
    assert busca.proxima(ocorrencias, (0, 8), -1) == (ocorrencias[0], False)
    assert busca.proxima(ocorrencias, (0, 0), -1, circular=True) == (ocorrencias[2], True)
    assert busca.proxima([], (0, 0), 1) == (None, False)


# ----------------------------------------------------------------------
# As opções da caixa (AC-ED06-7: o espaço casa o inseparável)
# ----------------------------------------------------------------------

def test_as_opcoes_maiusculas_palavra_inteira_minimo_nbsp_e_o_regex_invalido():
    texto = f"Cavalo cavalos ca{NBSP}valo <b>x</b> <i>y</i>"
    cap = _cap(_p(texto))
    assert len(busca.procurar_no_capitulo(cap, _pad("cavalo"))) == 2
    assert len(busca.procurar_no_capitulo(cap, _pad("cavalo", maiusculas=True))) == 1
    assert len(busca.procurar_no_capitulo(cap, _pad("cavalo", palavra_inteira=True))) == 1
    # o espaço do padrão casa também o U+00A0 — e o inseparável do padrão casa o espaço
    assert len(busca.procurar_no_capitulo(cap, _pad("ca valo"))) == 1
    assert len(busca.procurar_no_capitulo(cap, _pad(f"ca{NBSP}valo"))) == 1
    assert len(busca.procurar_no_capitulo(cap, _pad("ca valo", espaco_casa_nbsp=False))) == 0
    assert [o.texto for o in busca.procurar_no_capitulo(cap, _pad("<.*>", regex=True))] == ["<b>x</b> <i>y</i>"]
    assert [o.texto for o in busca.procurar_no_capitulo(cap, _pad("<.*>", regex=True, minimo=True))] == [
        "<b>", "</b>", "<i>", "</i>"]
    with pytest.raises(ValueError, match="expressão regular inválida"):
        _pad("(", regex=True)
    with pytest.raises(ValueError, match="digite o que procurar"):
        _pad("")
    with pytest.raises(ValueError, match="escopo"):
        busca.Opcoes(texto="x", escopo="lua")


def test_dotall_atravessa_a_quebra_suave_e_o_casamento_vazio_nao_e_ocorrencia():
    cap = _cap(_p("linha um", Trecho(texto="linha dois", quebra_antes=True)))
    assert busca.procurar_no_capitulo(cap, _pad("um.linha", regex=True)) == []
    assert len(busca.procurar_no_capitulo(cap, _pad("um.linha", regex=True, dotall=True))) == 1
    assert busca.procurar_no_capitulo(cap, _pad("x*", regex=True)) == []


# ----------------------------------------------------------------------
# Substituir: formato, nota, marca de página, quebra, lista, célula, legenda
# ----------------------------------------------------------------------

def test_substituir_preserva_o_formato_do_primeiro_caractere_e_o_que_nao_tem_texto():
    p = _p("Ver ", Trecho(texto="Tabela", negrito=True, link="#tab1"), Trecho(texto=" 1", link="#tab1"),
           Trecho(nota="n1"), " fim ", Trecho(texto="aqui", pagina=7), ".")
    cap = _cap(p)
    o = busca.procurar_no_capitulo(cap, _pad("tabela 1"))[0]
    novo = busca.bloco_substituido(cap, o, "Quadro 2")
    trechos = [(t.texto, t.negrito, t.link, t.nota, t.pagina) for t in novo.trechos]
    assert trechos == [("Ver ", False, "", "", None), ("Quadro 2", True, "#tab1", "", None),
                       ("", False, "", "n1", None), (" fim ", False, "", "", None), ("aqui", False, "", "", 7),
                       (".", False, "", "", None)]
    # a marca de página sobrevive quando o próprio trecho marcado é trocado
    o2 = busca.procurar_no_capitulo(cap, _pad("aqui"))[0]
    novo2 = busca.bloco_substituido(cap, o2, "ali")
    assert [(t.texto, t.pagina) for t in novo2.trechos][-2:] == [("ali", 7), (".", None)]
    # o original não foi tocado
    assert m.texto_de(p) == "Ver Tabela 1 fim aqui."
    # um `\n` no substituto vira quebra suave
    novo3 = busca.substituir_no_paragrafo(_p("a b c"), 1, 2, "\n")
    assert m.texto_de(novo3) == "a\nb c" and novo3.trechos[1].quebra_antes


def test_substituir_dentro_de_lista_celula_legenda_e_nota_troca_so_o_pedaco_certo():
    livro = editor_livros.livro_completo()
    cap = livro.capitulos[0]
    # lista: o segundo parágrafo do item b
    o = busca.procurar_no_capitulo(cap, _pad("continuação de b"))[0]
    nova = busca.bloco_substituido(cap, o, "SEGUE")
    assert isinstance(nova, m.Lista) and nova.itens[1].paragrafos[1].texto == "SEGUE"
    assert cap.bloco(o.alvo.bloco_id).itens[1].paragrafos[1].texto == "continuação de b"
    # célula
    o = busca.procurar_no_capitulo(cap, _pad("Pontos"))[0]
    nova = busca.bloco_substituido(cap, o, "Score")
    assert isinstance(nova, m.Tabela) and nova.filas[0][1].blocos[0].texto == "Score"
    # legenda
    o = busca.procurar_no_capitulo(cap, _pad("A foto"))[0]
    nova = busca.bloco_substituido(cap, o, "Foto 1")
    assert isinstance(nova, m.Figura) and "".join(t.texto for t in nova.legenda) == "Foto 1"
    # nota: a nota inteira, com o parágrafo trocado
    o = busca.procurar_no_capitulo(cap, _pad("Segundo parágrafo"))[0]
    nota = busca.nota_substituida(cap, o, "Outro parágrafo")
    assert isinstance(nota, m.Nota) and nota.id == "n2" and nota.blocos[1].texto == "Outro parágrafo."
    # `substituir_tudo_no_capitulo` sobre o livro completo mexe em blocos e notas e registra os dois
    historico = Historico()
    opcoes = busca.Opcoes(texto="parágrafo", substituto="PARÁGRAFO")
    n = busca.substituir_tudo_no_capitulo(cap, busca.compilar(opcoes), "PARÁGRAFO", opcoes, historico)
    assert n >= 8
    ponto = historico.desfazer(cap.arquivo)
    assert ponto is not None and "n2" in ponto.ids
    assert cap.nota("n2").blocos[1].texto == "Segundo PARÁGRAFO."


def test_expandir_so_expande_com_regex_e_recusa_grupo_inexistente():
    cap = _cap(_p("abc"))
    o = busca.procurar_no_capitulo(cap, _pad("(b)", regex=True))[0]
    assert busca.expandir(o, r"[\1]", busca.Opcoes(texto="(b)", regex=True)) == "[b]"
    assert busca.expandir(o, r"[\1]", busca.Opcoes(texto="(b)")) == r"[\1]"
    with pytest.raises(ValueError, match="substituto"):
        busca.expandir(o, r"\2", busca.Opcoes(texto="(b)", regex=True))
    texto, n = busca.substituir_tudo_no_cru("a1 b2 c3", _pad(r"([a-z])(\d)", regex=True), r"\2\1",
                                            busca.Opcoes(texto="x", regex=True))
    assert (texto, n) == ("1a 2b 3c", 3)


# ----------------------------------------------------------------------
# AC-ED06-4 (a parte pura): ir para diagrama 7 / página 45 / bloco / capítulo
# ----------------------------------------------------------------------

def test_ac4_destino_de_diagrama_pagina_bloco_e_capitulo():
    livro = editor_livros.livro_completo()
    cap1 = livro.capitulos[0]
    diagramas = [b for b in m.blocos_do_capitulo(cap1) if isinstance(b, m.Diagrama)]
    assert busca.destino(livro, "diagrama", 2).bloco_id == diagramas[1].id
    assert busca.destino(livro, "diagrama", 7) is None
    assert busca.destino(livro, "figura", 1).bloco_id == "fig1"
    assert busca.destino(livro, "tabela", 1).endereco == "cap1.xhtml#tab1"
    marca = busca.destino(livro, "pagina", 15)
    assert marca is not None and marca.bloco_id == "pg-15"
    # a página 7 é um `Trecho.pagina` dentro de um parágrafo: o destino tem deslocamento
    inline = busca.destino(livro, "pagina", 7)
    assert inline is not None and inline.deslocamento == len("Página marcada ")
    assert busca.destino(livro, "pagina", 999) is None
    assert busca.destino(livro, "bloco", 2, "cap2.xhtml").bloco_id == "alvo"
    assert busca.destino(livro, "bloco", 99, "cap2.xhtml") is None
    assert busca.destino(livro, "capitulo", 2).arquivo == "cap2.xhtml" and busca.destino(livro, "capitulo", 3) is None
    with pytest.raises(ValueError):
        busca.destino(livro, "lua", 1)


def test_o_historico_das_buscas_guarda_vinte_sem_repetir():
    h = busca.Historico()
    for k in range(25):
        h.registrar(f"b{k}")
    assert len(h.itens) == 20 and h.itens[0] == "b24"
    h.registrar("b23")
    assert h.itens[:2] == ["b23", "b24"] and len(h.itens) == 20
    assert h.registrar("  ") == h.itens


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
