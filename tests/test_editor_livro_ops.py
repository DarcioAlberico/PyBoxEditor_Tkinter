"""
Testes de `core/editor/livro_ops.py` (ED-01; SPEC_EDITOR §5.2, §9.5): renomear (com
tudo que aponta reescrito), renumerar, excluir devolvendo quem apontava, anexar com
colisão (AC-ED01-9); dividir com as notas indo cada uma para o seu lado, juntar
devolvendo o original, juntar por título as páginas do impresso, dividir nos
marcadores (AC-ED01-10); e o resto: mover, ordenar, folhas, cópia, ilhas e CSS que
seguem o arquivo renomeado.

Rodar sem pytest:      python tests/test_editor_livro_ops.py
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros as livros
from core.editor import epub, livro_ops as ops, modelo as m, sumario, xhtml


def _links(livro):
    return sorted(t.link for c in livro.capitulos for t in m.trechos_do_capitulo(c) if t.link)


def _destinos(livro):
    return [e.destino for e in sumario._todos(livro.sumario)]


# ----------------------------------------------------------------------
# AC-ED01-9: renomear, renumerar, excluir, anexar
# ----------------------------------------------------------------------

def test_renomear_reescreve_links_sumario_marcos_manifesto_folhas_ilhas_e_css():
    livro = livros.livro_de_teste()
    n = ops.renomear(livro, "Text/cap-0002.xhtml", "Text/dois.xhtml")
    assert n == 3                        # dois links e uma entrada do sumário
    assert [c.arquivo for c in livro.capitulos] == ["Text/cap-0001.xhtml", "Text/dois.xhtml", "Text/cap-0003.xhtml"]
    assert "Text/dois.xhtml#alvo" in _links(livro) and "Text/dois.xhtml#meio" in _links(livro)
    assert "Text/cap-0002.xhtml#alvo" not in _links(livro)
    assert "#alvo" in _links(livro)                                   # o link interno continua nu
    assert any(d.startswith("Text/dois.xhtml#") for d in _destinos(livro))
    assert not any("cap-0002" in d for d in _destinos(livro))
    with pytest.raises(ValueError):
        ops.renomear(livro, "Text/cap-0001.xhtml", "Text/dois.xhtml")     # já existe
    with pytest.raises(KeyError):
        ops.renomear(livro, "Text/nada.xhtml", "Text/x.xhtml")

    # Recurso: a folha muda de nome e de pasta, e quem a usa segue junto — inclusive o `url()` dela.
    ops.renomear(livro, "Styles/estilo.css", "css/livro.css")
    assert "css/livro.css" in livro.recursos and "Styles/estilo.css" not in livro.recursos
    assert livro.folhas == ["css/livro.css"] and all(c.folhas == ["css/livro.css"] for c in livro.capitulos)
    assert livro.recursos["css/livro.css"].dados == b"h1 { background: url(../Images/fig.png); }\n"
    ops.renomear(livro, "Images/fig.png", "Media/figura.png")
    assert livro.recursos["css/livro.css"].dados == b"h1 { background: url(../Media/figura.png); }\n"
    figura = [b for b in livro.capitulos[1].blocos if isinstance(b, m.Figura)][0]
    assert figura.recurso == "Media/figura.png"
    ilha = [b for b in livro.capitulos[2].blocos if isinstance(b, m.IlhaBruta)][0]
    assert ilha.xhtml == '<svg xmlns="http://www.w3.org/2000/svg"><image href="../Media/figura.png"/></svg>'
    assert ("bodymatter", "Text/cap-0001.xhtml") in livro.marcos
    assert livro.validar() == []


def test_o_capitulo_que_muda_de_pasta_leva_os_caminhos_relativos_das_ilhas_e_do_texto_cru():
    livro = livros.livro_de_teste()
    livro.capitulos[2].texto_cru = xhtml.escrever(livro.capitulos[2])
    assert '<image href="../Images/fig.png"/>' in livro.capitulos[2].texto_cru
    ops.renomear(livro, "Text/cap-0003.xhtml", "tres.xhtml")             # sobe uma pasta
    cru = livro.capitulos[2].texto_cru
    assert '<image href="Images/fig.png"/>' in cru and 'href="Styles/estilo.css"' in cru
    assert 'href="Text/cap-0002.xhtml#meio"' in cru
    lido = xhtml.ler(cru, "tres.xhtml")
    assert lido.folhas == ["Styles/estilo.css"] and lido.blocos[1].trechos[0].link == "Text/cap-0002.xhtml#meio"


def test_renomear_varios_renumera_tres_de_uma_vez_sem_colidir():
    livro = livros.livro_de_teste()
    ops.mover(livro, "Text/cap-0003.xhtml", 0)          # a ordem da espinha manda na numeração
    mapa = ops.renomear_varios(livro, "cap-%03d")
    assert mapa == {"Text/cap-0003.xhtml": "Text/cap-001.xhtml", "Text/cap-0001.xhtml": "Text/cap-002.xhtml",
                    "Text/cap-0002.xhtml": "Text/cap-003.xhtml"}
    assert [c.arquivo for c in livro.capitulos] == ["Text/cap-001.xhtml", "Text/cap-002.xhtml", "Text/cap-003.xhtml"]
    assert "Text/cap-003.xhtml#alvo" in _links(livro) and "Text/cap-002.xhtml#t1" in _links(livro)
    assert livro.marcos == [("bodymatter", "Text/cap-002.xhtml")]
    # Renumerar de novo com o mesmo padrão é a identidade (o `cap-001 → cap-001` não é troca).
    assert ops.renomear_varios(livro, "cap-%03d") == {}
    # Um padrão que gera nome de recurso existente é recusado.
    livro.recursos["Text/x-001.xhtml"] = m.Recurso(caminho="Text/x-001.xhtml", tipo_mime="text/plain", dados=b"")
    with pytest.raises(ValueError):
        ops.renomear_varios(livro, "x-%03d")
    with pytest.raises(ValueError):
        ops.renomear_varios(livro, "sem-numero")


def test_excluir_devolve_quem_apontava_e_limpa_sumario_marcos_e_folhas():
    livro = livros.livro_de_teste()
    livro.sumario = [e for e in livro.sumario if not e.destino.startswith("Text/cap-0002.xhtml")]
    assert ops.excluir(livro, "Text/cap-0002.xhtml") == ["Text/cap-0001.xhtml#x", "Text/cap-0003.xhtml#y"]
    assert [c.arquivo for c in livro.capitulos] == ["Text/cap-0001.xhtml", "Text/cap-0003.xhtml"]
    assert "Text/cap-0002.xhtml#alvo" in _links(livro)                 # o link fica (INV-02): vira aviso
    assert any("inexistente" in a for a in livro.validar())

    livro = livros.livro_de_teste()
    quem = ops.excluir(livro, "Text/cap-0001.xhtml")
    assert quem == ["Text/cap-0002.xhtml#d", "sumário: Um", "marco: bodymatter"]
    assert livro.marcos == [] and [e.rotulo for e in livro.sumario] == ["Dois", "Três"]

    livro = livros.livro_de_teste()
    quem = ops.excluir(livro, "Styles/estilo.css")
    assert quem == ["Text/cap-0001.xhtml", "Text/cap-0002.xhtml", "Text/cap-0003.xhtml"]
    assert livro.folhas == [] and all(c.folhas == [] for c in livro.capitulos)
    assert "Styles/estilo.css" not in livro.recursos
    with pytest.raises(KeyError):
        ops.excluir(livro, "nada")


def test_anexar_renomeia_colisoes_reescreve_os_links_do_anexado_e_compartilha_recurso_igual():
    livro = livros.livro_de_teste()
    outro = livros.livro_de_teste()
    outro.recursos["Styles/estilo.css"].dados = b"p { color: blue }"          # difere: precisa de outro nome
    outro.capitulos[1].blocos[1].trechos[0].texto = "do outro"
    novos = ops.anexar(livro, outro)
    assert novos == ["Text/cap-0001-1.xhtml", "Text/cap-0002-1.xhtml", "Text/cap-0003-1.xhtml"]
    assert len(livro.capitulos) == 6 and len(livro.recursos) == 3
    assert "Styles/estilo-1.css" in livro.recursos and "Images/fig.png" in livro.recursos      # a figura, igual, é uma só
    anexado = livro.capitulo("Text/cap-0001-1.xhtml")
    assert anexado.folhas == ["Styles/estilo-1.css"]
    assert anexado.blocos[1].trechos[1].link == "Text/cap-0002-1.xhtml#alvo"
    assert livro.capitulo("Text/cap-0003-1.xhtml").blocos[1].trechos[0].link == "Text/cap-0002-1.xhtml#meio"
    assert livro.capitulos[0].blocos[1].trechos[1].link == "Text/cap-0002.xhtml#alvo"       # o meu não mudou
    assert [e.rotulo for e in livro.sumario] == ["Um", "Dois", "Três", "Um", "Dois", "Três"]
    assert livro.validar() == []
    assert len(outro.capitulos) == 3 and outro.capitulos[0].arquivo == "Text/cap-0001.xhtml"   # `outro` intacto


# ----------------------------------------------------------------------
# AC-ED01-10: dividir, juntar, juntar por título, dividir nos marcadores
# ----------------------------------------------------------------------

def test_dividir_leva_cada_nota_para_o_seu_lado_e_reescreve_sumario_e_links():
    livro = livros.livro_de_teste()
    original = copy.deepcopy(livro)
    livro.sumario[1].filhos.append(m.EntradaDeSumario(rotulo="Alvo", destino="Text/cap-0002.xhtml#alvo"))
    livro.marcos.append(("bodymatter", "Text/cap-0002.xhtml#alvo"))
    novo = ops.dividir(livro, "Text/cap-0002.xhtml", 3)          # antes da figura
    assert novo == "Text/cap-0002-1.xhtml"
    assert [c.arquivo for c in livro.capitulos] == ["Text/cap-0001.xhtml", "Text/cap-0002.xhtml", novo,
                                                    "Text/cap-0003.xhtml"]
    primeiro, segundo = livro.capitulos[1], livro.capitulos[2]
    assert [b.id for b in primeiro.blocos] == ["t2", "a", "meio"] and [b.id for b in segundo.blocos] == ["fig", "alvo", "d"]
    assert [n.id for n in primeiro.notas] == ["n1"] and [n.id for n in segundo.notas] == ["n2"]
    assert primeiro.folhas == segundo.folhas == ["Styles/estilo.css"]
    assert primeiro.blocos[2].trechos[1].link == "Text/cap-0002-1.xhtml#alvo"         # o `#alvo` nu cruzou a fronteira
    assert livro.capitulos[0].blocos[1].trechos[1].link == "Text/cap-0002-1.xhtml#alvo"
    assert livro.capitulos[3].blocos[1].trechos[0].link == "Text/cap-0002.xhtml#meio"    # ficou onde estava
    assert segundo.blocos[2].trechos[2].link == "Text/cap-0001.xhtml#t1"
    assert "Text/cap-0002-1.xhtml#alvo" in _destinos(livro) and ("bodymatter", "Text/cap-0002-1.xhtml#alvo") in livro.marcos
    assert livro.validar() == []
    with pytest.raises(ValueError):
        ops.dividir(livro, "Text/cap-0002.xhtml", 0)

    # Juntar devolve o original: ids preservados, notas de volta, links e sumário como antes.
    assert ops.juntar(livro, novo) == "Text/cap-0002.xhtml"
    livro.sumario[1].filhos.pop()
    livro.marcos.pop()
    assert [c.arquivo for c in livro.capitulos] == [c.arquivo for c in original.capitulos]
    for c1, c2 in zip(livro.capitulos, original.capitulos):
        assert m.igual(c1, c2), c1.arquivo
    assert _links(livro) == _links(original) and _destinos(livro) == _destinos(original)
    with pytest.raises(ValueError):
        ops.juntar(livro, "Text/cap-0001.xhtml")


def test_juntar_troca_ids_que_colidem_e_reescreve_quem_apontava_para_eles():
    livro = livros.livro_de_teste()
    # O capítulo 3 ganha um bloco "meio", como o 2 já tem; alguém aponta para ele.
    livro.capitulos[2].blocos.append(m.Paragrafo(trechos=[m.Trecho(texto="meio do três")], id="meio",
                                                 id_persistente=True))
    livro.capitulos[0].blocos.append(m.Paragrafo(trechos=[m.Trecho(texto="l", link="Text/cap-0003.xhtml#meio")]))
    livro.capitulos[0].blocos.append(m.Paragrafo(trechos=[m.Trecho(texto="l", link="Text/cap-0003.xhtml")]))
    ops.juntar(livro, "Text/cap-0003.xhtml")
    juntado = livro.capitulos[1]
    ids = [b.id for b in juntado.blocos]
    assert len(ids) == len(set(ids)) and ids.count("meio") == 1
    novo_id = ids[-1]
    assert novo_id != "meio" and livro.capitulos[0].blocos[-2].trechos[0].link == f"Text/cap-0002.xhtml#{novo_id}"
    assert livro.capitulos[0].blocos[-1].trechos[0].link == "Text/cap-0002.xhtml"
    assert m.texto_de(juntado.blocos[-1]) == "meio do três"
    assert livro.capitulos[0].blocos[1].trechos[1].link == "Text/cap-0002.xhtml#alvo"
    assert livro.validar() == []


def test_juntar_por_titulo_das_12_paginas_do_impresso_faz_3_capitulos_com_12_marcas():
    capitulos = []
    for n in range(1, 13):
        blocos = []
        if n in (1, 5, 9):
            blocos.append(m.Titulo(trechos=[m.Trecho(texto=f"Capítulo {n}")], nivel=1))
        blocos.append(m.Paragrafo(trechos=[m.Trecho(texto=f"prosa da página {n}")]))
        capitulos.append(m.Capitulo(arquivo=f"pagina-{n:04d}.xhtml", titulo=f"Página {n}", blocos=blocos))
    livro = m.Livro(metadados=m.Metadados(titulo="T"), capitulos=capitulos, opf="OEBPS/content.opf")
    livro.sumario = sumario.gerar_dos_titulos(livro)
    cabecas = ops.juntar_por_titulo(livro, 1)
    assert cabecas == ["pagina-0001.xhtml", "pagina-0005.xhtml", "pagina-0009.xhtml"]
    assert [c.arquivo for c in livro.capitulos] == cabecas
    marcas = [b for c in livro.capitulos for b in c.blocos if isinstance(b, m.MarcaDePagina)]
    assert [b.pagina for b in marcas] == list(range(1, 13))
    assert sumario.marcas_de_pagina(livro) == [(n, f"{c}#pg-{n}") for c, n in
                                               zip(["pagina-0001.xhtml"] * 4 + ["pagina-0005.xhtml"] * 4
                                                   + ["pagina-0009.xhtml"] * 4, range(1, 13))]
    assert [c.titulo for c in livro.capitulos] == ["", "", ""]                  # "Página N" saiu
    assert [c.titulo_efetivo for c in livro.capitulos] == ["Capítulo 1", "Capítulo 5", "Capítulo 9"]
    assert [b.pagina for b in livro.capitulos[0].blocos if isinstance(b, m.MarcaDePagina)] == [1, 2, 3, 4]
    assert isinstance(livro.capitulos[0].blocos[1], m.Titulo)
    assert _destinos(livro) == [f"{c}#{livro.capitulo(c).blocos[1].id}" for c in cabecas]
    assert livro.validar() == []
    # Uma página com o título no meio parte ali, e não no começo da página.
    livro2 = m.Livro(metadados=m.Metadados(titulo="T"), capitulos=[
        m.Capitulo(arquivo="pagina-0001.xhtml", blocos=[m.Paragrafo(trechos=[m.Trecho(texto="fim do anterior")]),
                                                        m.Titulo(trechos=[m.Trecho(texto="Novo")], nivel=1),
                                                        m.Paragrafo(trechos=[m.Trecho(texto="começo")])]),
        m.Capitulo(arquivo="pagina-0002.xhtml", blocos=[m.Paragrafo(trechos=[m.Trecho(texto="segue")])]),
    ])
    assert ops.juntar_por_titulo(livro2, 1) == ["pagina-0001.xhtml", "pagina-0001-1.xhtml"]
    assert [type(b).__name__ for b in livro2.capitulos[1].blocos] == ["Titulo", "Paragrafo", "MarcaDePagina", "Paragrafo"]
    assert [type(b).__name__ for b in livro2.capitulos[0].blocos] == ["MarcaDePagina", "Paragrafo"]


def test_dividir_nos_marcadores_parte_em_tres_e_os_marcadores_somem():
    livro = livros.livro_de_teste()
    cap = livro.capitulos[1]
    cap.blocos.insert(2, m.Separador(classe="divisao"))
    cap.blocos.insert(5, m.Separador(classe="divisao"))
    cap.blocos.append(m.Separador(classe="outra"))
    hrefs = ops.dividir_nos_marcadores(livro, "Text/cap-0002.xhtml")
    assert hrefs == ["Text/cap-0002.xhtml", "Text/cap-0002-1.xhtml", "Text/cap-0002-2.xhtml"]
    partes = [livro.capitulo(h) for h in hrefs]
    assert [[b.id for b in p.blocos if not isinstance(b, m.Separador)] for p in partes] == [
        ["t2", "a"], ["meio", "fig"], ["alvo", "d"]]
    assert not any(isinstance(b, m.Separador) and "divisao" in b.classe for p in partes for b in p.blocos)
    assert isinstance(partes[2].blocos[-1], m.Separador)                       # o `hr` comum fica
    assert [n.id for n in partes[0].notas] == ["n1"] and [n.id for n in partes[2].notas] == ["n2"]
    assert livro.capitulos[0].blocos[1].trechos[1].link == "Text/cap-0002-2.xhtml#alvo"
    assert livro.validar() == []


def test_dividir_por_titulo_no_livro_reescreve_o_sumario():
    livro = livros.livro_de_teste()
    cap = livro.capitulos[1]
    cap.blocos.insert(3, m.Titulo(trechos=[m.Trecho(texto="Dois e meio")], nivel=1, id="t25"))
    livro.sumario = sumario.gerar_dos_titulos(livro)
    assert ops.dividir_por_titulo(livro, "Text/cap-0002.xhtml", 1) == ["Text/cap-0002.xhtml", "Text/cap-0002-1.xhtml"]
    assert [e.destino for e in livro.sumario] == ["Text/cap-0001.xhtml#t1", "Text/cap-0002.xhtml#t2",
                                                  "Text/cap-0002-1.xhtml#t25", "Text/cap-0003.xhtml#t3"]
    assert livro.validar() == []


# ----------------------------------------------------------------------
# O resto: mover, ordenar, folhas, cópia, capítulo em modo código
# ----------------------------------------------------------------------

def test_mover_ordenar_vincular_folhas_e_adicionar_copia():
    livro = livros.livro_de_teste()
    ops.mover(livro, "Text/cap-0001.xhtml", 2)
    assert [c.arquivo for c in livro.capitulos] == ["Text/cap-0002.xhtml", "Text/cap-0003.xhtml", "Text/cap-0001.xhtml"]
    ops.ordenar(livro, ["Text/cap-0001.xhtml", "Text/cap-0002.xhtml", "Text/cap-0003.xhtml"])
    assert [c.arquivo for c in livro.capitulos] == ["Text/cap-0001.xhtml", "Text/cap-0002.xhtml", "Text/cap-0003.xhtml"]
    with pytest.raises(ValueError):
        ops.ordenar(livro, ["Text/cap-0001.xhtml"])
    livro.recursos["Styles/extra.css"] = m.Recurso(caminho="Styles/extra.css", tipo_mime="text/css", dados=b"")
    assert ops.vincular_folhas(livro, ["Text/cap-0001.xhtml"], ["Styles/extra.css"], substituir=False) == 1
    assert livro.capitulos[0].folhas == ["Styles/estilo.css", "Styles/extra.css"]
    assert ops.vincular_folhas(livro, None, ["Styles/extra.css"]) == 3
    assert all(c.folhas == ["Styles/extra.css"] for c in livro.capitulos)
    with pytest.raises(ValueError):
        ops.vincular_folhas(livro, None, ["Styles/nao-existe.css"])
    assert ops.adicionar_copia(livro, "Text/cap-0002.xhtml") == "Text/cap-0002-1.xhtml"
    assert livro.capitulos[2].arquivo == "Text/cap-0002-1.xhtml" and m.igual(livro.capitulos[2].blocos, livro.capitulos[1].blocos)
    assert ops.adicionar_copia(livro, "Images/fig.png") == "Images/fig-1.png"
    assert livro.recursos["Images/fig-1.png"].dados == livros.PNG_MINIMO
    assert livro.validar() == []


def test_dividir_um_capitulo_em_modo_codigo_converte_antes_e_recusa_o_mal_formado():
    livro = livros.livro_de_teste()
    cap = livro.capitulos[1]
    cap.texto_cru = xhtml.escrever(cap)
    novo = ops.dividir(livro, "Text/cap-0002.xhtml", 3)
    assert livro.capitulos[1].texto_cru is None and livro.capitulo(novo).texto_cru is None
    assert [b.id for b in livro.capitulos[1].blocos] == ["t2", "a", "meio"]
    livro.capitulos[1].texto_cru = "<p>aberto"
    with pytest.raises(xhtml.ErroDeXhtml):
        ops.juntar(livro, novo)


def test_as_operacoes_sobrevivem_a_gravacao(tmp_path):
    livro = livros.livro_de_teste()
    ops.renomear(livro, "Text/cap-0002.xhtml", "Text/dois.xhtml")
    ops.dividir(livro, "Text/dois.xhtml", 3)
    caminho = str(tmp_path / "ops.epub")
    relatorio = epub.escrever(livro, caminho)
    assert not relatorio.avisos, relatorio.avisos
    relido, _ = epub.ler(caminho)
    assert [c.arquivo for c in relido.capitulos] == ["Text/cap-0001.xhtml", "Text/dois.xhtml", "Text/dois-1.xhtml",
                                                     "Text/cap-0003.xhtml"]
    assert "Text/dois-1.xhtml#alvo" in _links(relido) and epub.validar_estrutura(caminho) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
