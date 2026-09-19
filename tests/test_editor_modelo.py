"""
Testes do modelo do livro (ED-00; SPEC_EDITOR §5): invariantes, operações puras,
serialização e igualdade a menos de ids gerados.

Os padrões copiados (corpo, fonte, moldura, cantos) são conferidos contra os módulos
de onde vieram — é o preço de o modelo não importar `fitz` (DEC-07), e é a única
maneira de a cópia não divergir em silêncio.

Rodar sem pytest:      python tests/test_editor_modelo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.editor import modelo as m

FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _p(texto="abc", **kw):
    return m.Paragrafo(trechos=[m.Trecho(texto=texto)], **kw)


# ----------------------------------------------------------------------
# Os padrões copiados não divergiram (AC-ED00-8)
# ----------------------------------------------------------------------

def test_os_padroes_copiados_batem_com_a_origem():
    from core import estilo_do_livro, render_diagrama
    assert m.CORPO_PADRAO_PT == estilo_do_livro.CORPO_PADRAO_PT
    assert m.FONTE_PADRAO == render_diagrama.FONTE_PADRAO
    assert m.MOLDURA_PADRAO == render_diagrama.MOLDURA_PADRAO
    assert m.CANTO_PADRAO == render_diagrama.CANTO_PADRAO
    assert m.MODOS_DE_DIAGRAMA == estilo_do_livro.MODOS_DE_DIAGRAMA


# ----------------------------------------------------------------------
# Validação na construção (AC-ED00-7)
# ----------------------------------------------------------------------

def test_bloco_e_abstrato_e_as_filhas_se_constroem_por_nome():
    with pytest.raises(TypeError):
        m.Bloco()
    p = _p()
    assert m.id_gerado(p.id) and not p.id_persistente


def test_titulo_forca_id_persistente_e_estilo():
    t = m.Titulo(trechos=[m.Trecho(texto="Cap")], nivel=2)
    assert t.id_persistente and t.estilo == "titulo2"
    with pytest.raises(ValueError):
        m.Titulo(trechos=[], nivel=7)


def test_fen_invalido_e_recusado_na_construcao():
    with pytest.raises(ValueError, match="FEN"):
        m.Diagrama(fen="isto não é fen")
    assert m.fen_valido(FEN) and not m.fen_valido("") and not m.fen_valido("8/8/8 w")


def test_tabela_nao_retangular_e_recusada_e_o_cabecalho_se_normaliza():
    c = lambda cab=False: m.Celula(blocos=[_p()], cabecalho=cab)  # noqa: E731
    with pytest.raises(ValueError, match="retangular"):
        m.Tabela(filas=[[c(), c()], [c()]])
    t = m.Tabela(filas=[[c(True), c(True)], [c(), c()]])
    assert t.primeira_fila_cabecalho
    t2 = m.Tabela(filas=[[c(), c()]], primeira_fila_cabecalho=True)
    assert all(cel.cabecalho for cel in t2.filas[0])


def test_vocabularios_fechados_recusam_valor_estranho():
    with pytest.raises(ValueError):
        _p(alinhamento="meio")
    with pytest.raises(ValueError):
        m.Trecho(texto="x", papel="rei")
    with pytest.raises(ValueError):
        m.Trecho(texto="x", ilha="<b/>")     # ilha inline não tem texto próprio
    with pytest.raises(ValueError):
        m.Nota(tipo="margem")
    with pytest.raises(ValueError):
        m.Diagrama(fen=FEN, lado="branco")


def test_marca_de_pagina_ganha_o_id_da_page_list():
    marca = m.MarcaDePagina(pagina=27)
    assert marca.id == "pg-27" and marca.id_persistente
    assert m.MarcaDePagina(pagina=3, id="x").id == "x"


def test_validar_levanta_para_id_duplicado_no_capitulo_e_aceita_entre_capitulos():
    a = _p(id="x", id_persistente=True)
    b = _p(id="x", id_persistente=True)
    livro = m.Livro(metadados=m.Metadados(titulo="T"), capitulos=[
        m.Capitulo(arquivo="Text/a.xhtml", blocos=[a]),
        m.Capitulo(arquivo="Text/b.xhtml", blocos=[b]),
    ])
    assert livro.validar() == []
    livro.capitulos[0].blocos.append(m.Paragrafo(trechos=[], id="x"))
    with pytest.raises(ValueError, match="duplicado"):
        livro.validar()


def test_validar_avisa_para_recurso_e_link_inexistentes_sem_levantar():
    cap = m.Capitulo(arquivo="Text/a.xhtml", blocos=[
        m.Figura(recurso="Images/nao.png", alt="x"),
        m.Paragrafo(trechos=[m.Trecho(texto="ver", link="Text/b.xhtml#z"),
                             m.Trecho(texto="n", nota="n-9")]),
    ])
    livro = m.Livro(metadados=m.Metadados(titulo="T"), capitulos=[cap])
    avisos = livro.validar()
    assert any("Images/nao.png" in a for a in avisos)
    assert any("Text/b.xhtml#z" in a for a in avisos)
    assert any("n-9" in a for a in avisos)


# ----------------------------------------------------------------------
# Trechos e formato
# ----------------------------------------------------------------------

def test_aplicar_formato_parte_e_funde_trechos():
    p = _p("xabcx")
    m.aplicar_formato(p, 1, 4, negrito=True)
    assert [(t.texto, t.negrito) for t in p.trechos] == [("x", False), ("abc", True), ("x", False)]
    assert m.tem_formato(p, 1, 4, "negrito") and not m.tem_formato(p, 0, 5, "negrito")
    m.aplicar_formato(p, 0, 5, negrito=True)
    assert [(t.texto, t.negrito) for t in p.trechos] == [("xabcx", True)]
    m.aplicar_formato(p, 0, 5, negrito=False)
    assert len(p.trechos) == 1 and not p.trechos[0].negrito


def test_limpar_formato_mantem_link_e_nota():
    p = m.Paragrafo(trechos=[m.Trecho(texto="ab", negrito=True, cor="#f00", link="#x")])
    m.limpar_formato(p, 0, 2)
    t = p.trechos[0]
    assert not t.negrito and t.cor == "" and t.link == "#x"


def test_a_quebra_suave_conta_um_caractere_no_texto():
    p = m.Paragrafo(trechos=[m.Trecho(texto="ab"), m.Trecho(texto="cd", quebra_antes=True)])
    assert m.texto_de(p) == "ab\ncd"
    m.aplicar_formato(p, 3, 5, italico=True)
    assert [(t.texto, t.italico, t.quebra_antes) for t in p.trechos] == [
        ("ab", False, False), ("", False, True), ("cd", True, False)]


def test_mudar_caixa():
    p = _p("aBc dEf")
    m.mudar_caixa(p, 0, 7, "alternar")
    assert m.texto_de(p) == "AbC DeF"
    m.mudar_caixa(p, 0, 7, "primeira")
    assert m.texto_de(p) == "Abc Def"
    m.mudar_caixa(p, 0, 3, "maiusculas")
    assert m.texto_de(p) == "ABC Def"


def test_trechos_normalizados_descarta_vazios_e_funde_iguais():
    trechos = [m.Trecho(texto="a"), m.Trecho(texto=""), m.Trecho(texto="b"),
               m.Trecho(texto="c", negrito=True), m.Trecho(quebra_antes=True)]
    saida = m.trechos_normalizados(trechos)
    assert [(t.texto, t.negrito, t.quebra_antes) for t in saida] == [
        ("ab", False, False), ("c", True, False), ("", False, True)]


# ----------------------------------------------------------------------
# Parágrafos e capítulos
# ----------------------------------------------------------------------

def test_dividir_e_juntar_paragrafos():
    p = m.Paragrafo(trechos=[m.Trecho(texto="abc"), m.Trecho(texto="def", negrito=True)],
                    estilo="notacao", id="p1", id_persistente=True)
    a, b = m.dividir_paragrafo(p, 4)
    assert m.texto_de(a) == "abcd" and m.texto_de(b) == "ef"
    assert a.id == "p1" and m.id_gerado(b.id) and b.estilo == "notacao"
    juntado = m.juntar_paragrafos(a, b)
    assert m.texto_de(juntado) == "abcdef" and juntado.id == "p1"
    assert [(t.texto, t.negrito) for t in juntado.trechos] == [("abc", False), ("def", True)]


def test_juntar_atraves_de_marca_de_pagina_vira_trecho_com_pagina():
    a, b = _p("fim da página"), _p("começo da outra")
    juntado = m.juntar_paragrafos(a, b, m.MarcaDePagina(pagina=27))
    assert juntado.trechos[-1].pagina == 27
    assert m.texto_de(juntado) == "fim da páginacomeço da outra"


def test_juntar_guarda_a_origem_fundida():
    o1 = m.Origem(page_id="d-p0001", bloco_id="b1", pagina=0)
    o2 = m.Origem(page_id="d-p0001", bloco_id="b2", pagina=0)
    juntado = m.juntar_paragrafos(_p("a", origem=o1), _p("b", origem=o2))
    assert juntado.origem.bloco_id == "b1" and juntado.origem.fundidas[0].bloco_id == "b2"


def test_converter_paragrafo_em_titulo_e_de_volta():
    p = _p("Cap", classe="x")
    t = m.converter(p, "titulo", nivel=3)
    assert isinstance(t, m.Titulo) and t.nivel == 3 and t.id == p.id and t.classe == "x"
    p2 = m.converter(t, "paragrafo")
    assert type(p2) is m.Paragrafo and p2.estilo == "corpo"


def test_dividir_capitulo_leva_cada_nota_com_a_sua_referencia():
    n1, n2 = m.Nota(blocos=[_p("nota 1")]), m.Nota(blocos=[_p("nota 2")])
    cap = m.Capitulo(arquivo="Text/c.xhtml", blocos=[
        m.Paragrafo(trechos=[m.Trecho(texto="a"), m.Trecho(nota=n1.id)]),
        _p("meio"),
        m.Paragrafo(trechos=[m.Trecho(texto="b"), m.Trecho(nota=n2.id)]),
    ], notas=[n1, n2])
    a, b = m.dividir_capitulo(cap, 1, "Text/d.xhtml")
    assert [n.id for n in a.notas] == [n1.id] and [n.id for n in b.notas] == [n2.id]
    assert len(a.blocos) == 1 and len(b.blocos) == 2 and b.arquivo == "Text/d.xhtml"
    with pytest.raises(ValueError):
        m.dividir_capitulo(cap, 0, "x")
    juntado = m.juntar_capitulos(a, b)
    assert len(juntado.blocos) == 3 and {n.id for n in juntado.notas} == {n1.id, n2.id}


def test_juntar_capitulos_troca_ids_que_colidem_e_reescreve_as_referencias():
    nota = m.Nota(id="n", blocos=[_p("x")])
    a = m.Capitulo(arquivo="Text/a.xhtml", blocos=[_p("a", id="x", id_persistente=True)],
                   notas=[m.Nota(id="n", blocos=[_p("y")])])
    b = m.Capitulo(arquivo="Text/b.xhtml", blocos=[
        m.Paragrafo(trechos=[m.Trecho(texto="ver", link="#x"), m.Trecho(nota="n")], id="x")], notas=[nota])
    juntado = m.juntar_capitulos(a, b)
    ids = [bl.id for bl in juntado.blocos]
    assert ids[0] == "x" and ids[1] != "x"
    trechos = juntado.blocos[1].trechos
    assert trechos[0].link == "#" + ids[1] and trechos[1].nota == juntado.notas[1].id != "n"


def test_dividir_por_titulo():
    cap = m.Capitulo(arquivo="Text/livro.xhtml", blocos=[
        _p("prefácio"), m.Titulo(trechos=[m.Trecho(texto="Um")]), _p("a"),
        m.Titulo(trechos=[m.Trecho(texto="Dois")]), _p("b"),
        m.Titulo(trechos=[m.Trecho(texto="Seção")], nivel=2), _p("c"),
    ])
    partes = m.dividir_por_titulo(cap, 1)
    assert [c.arquivo for c in partes] == ["Text/livro.xhtml", "Text/livro-0001.xhtml", "Text/livro-0002.xhtml"]
    assert [len(c.blocos) for c in partes] == [1, 2, 4]
    assert partes[2].titulo_efetivo == "Dois"


def test_renumerar_notas_segue_a_ordem_das_referencias():
    n1, n2, n3 = (m.Nota(blocos=[_p(str(i))]) for i in range(3))
    cap = m.Capitulo(arquivo="Text/c.xhtml", blocos=[
        m.Paragrafo(trechos=[m.Trecho(nota=n2.id), m.Trecho(nota=n1.id)])], notas=[n1, n2, n3])
    assert m.renumerar_notas(cap) == [(n2.id, 1), (n1.id, 2), (n3.id, 3)]


def test_numerar_objetos_regenera_o_texto_das_referencias():
    d1, d2 = m.Diagrama(fen=FEN), m.Diagrama(fen=FEN)
    cap = m.Capitulo(arquivo="Text/c.xhtml", blocos=[
        d1, m.Paragrafo(trechos=[m.Trecho(texto="Diagrama 9", ref="diagrama", link="#" + d2.id)]), d2])
    livro = m.Livro(metadados=m.Metadados(titulo="T"), capitulos=[cap])
    numeros = m.numerar_objetos(livro, "diagrama")
    assert d1.numero == 1 and d2.numero == 2 and d2.id_persistente
    assert cap.blocos[1].trechos[0].texto == "Diagrama 2"
    assert numeros == {f"Text/c.xhtml#{d1.id}": 1, f"Text/c.xhtml#{d2.id}": 2}
    m.inserir_bloco(cap, 0, m.Diagrama(fen=FEN))
    m.numerar_objetos(livro, "diagrama")
    assert cap.blocos[2].trechos[0].texto == "Diagrama 3"


# ----------------------------------------------------------------------
# Serialização e igualdade
# ----------------------------------------------------------------------

def test_para_dict_e_de_dict_fecham_no_livro_inteiro():
    cap = m.Capitulo(arquivo="Text/c.xhtml", blocos=[
        m.Titulo(trechos=[m.Trecho(texto="T")]),
        m.Diagrama(fen=FEN, setas=[("e2", "e4")], marcas=["e4"], legenda=[m.Trecho(texto="L")]),
        m.Lista(ordenada=True, itens=[m.ItemDeLista(paragrafos=[_p("i")],
                                                    filhos=m.Lista(ordenada=False, itens=[m.ItemDeLista(paragrafos=[_p("j")])]))]),
        m.Tabela(filas=[[m.Celula(blocos=[_p("c")])]], legenda=[m.Trecho(texto="t")]),
        m.MarcaDePagina(pagina=4), m.QuebraDePagina(), m.Separador(),
        m.IlhaBruta(xhtml="<svg/>", elemento="svg"),
        m.Paragrafo(trechos=[m.Trecho(texto="o")],
                    origem=m.Origem(page_id="d-p0002", bloco_id="b", pagina=1, caixa=(1, 2, 3, 4))),
    ], notas=[m.Nota(blocos=[_p("n")], tipo="fim")])
    livro = m.Livro(metadados=m.Metadados(titulo="T", autores=[m.Pessoa(nome="A")], colecao=("S", 2)),
                    capitulos=[cap], recursos={"Images/x.png": m.Recurso(caminho="Images/x.png", tipo_mime="image/png", dados=b"\x89PNG")},
                    marcos=[("bodymatter", "Text/c.xhtml")])
    dados = m.para_dict(livro)
    copia = m.de_dict(dados)
    assert m.para_dict(copia) == dados
    assert copia.recursos["Images/x.png"].dados == b"\x89PNG"
    assert copia.metadados.colecao == ("S", 2)
    assert copia.capitulos[0].blocos[1].setas == [("e2", "e4")]
    assert copia.capitulos[0].blocos[-1].origem.caixa == (1, 2, 3, 4)


def test_igual_ignora_ids_gerados_nao_persistentes_e_linha_fonte():
    a = m.Capitulo(arquivo="c", blocos=[_p("x", linha_fonte=3)])
    b = m.Capitulo(arquivo="c", blocos=[_p("x", linha_fonte=9)])
    assert a.blocos[0].id != b.blocos[0].id and m.igual(a, b)
    c = m.Capitulo(arquivo="c", blocos=[_p("x", id="fixo", id_persistente=True)])
    assert not m.igual(a, c)
    d = m.Capitulo(arquivo="c", blocos=[_p("y")])
    assert not m.igual(a, d)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
