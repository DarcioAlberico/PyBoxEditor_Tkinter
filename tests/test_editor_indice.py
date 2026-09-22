"""
Testes de `core/editor/indice.py` (ED-12; SPEC_EDITOR §11.9, AC-ED12-3): o índice de
jogadores ordena pela `chave` ("Kasparov, Garry" antes de "Wely, Loek van", e não pelo
texto "Loek van Wely"; "Ávila" entre os A), com links ao título mais próximo e o número da
partida; a página é `epub:type="index"` no EPUB e `role="doc-index"` no HTML; os índices
de partidas e de aberturas; refeito no lugar.

Rodar sem pytest:      .venv/Scripts/python.exe tests/test_editor_indice.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import html_io, indice, modelo as m, xhtml


def p(texto, **kw):
    return m.Paragrafo(trechos=[m.Trecho(texto=texto)], **kw)


def _livro():
    livro = editor_livros.livro_completo()
    cap = livro.capitulos[0]
    cap.blocos = [
        m.Titulo(trechos=[m.Trecho(texto="Capítulo um")], nivel=1),
        m.Titulo(trechos=[m.Trecho(texto="Loek van Wely", papel="jogador", chave="Wely, Loek van"), m.Trecho(texto=" – "),
                          m.Trecho(texto="Garry Kasparov", papel="jogador", chave="Kasparov, Garry"),
                          m.Trecho(texto=" ("), m.Trecho(texto="C42", papel="abertura", chave="C42"),
                          m.Trecho(texto=")")], nivel=2),
        p("1.e4 e5 2.Nf3 Nf6", estilo="notacao"),
        m.Titulo(trechos=[m.Trecho(texto="Karpov", papel="jogador", chave="Karpov, Anatoly"), m.Trecho(texto=" – "),
                          m.Trecho(texto="Kasparov", papel="jogador", chave="Kasparov, Garry")], nivel=2),
        p("1.d4 Nf6 2.c4", estilo="notacao"),
        m.Paragrafo(trechos=[m.Trecho(texto="Fora de partida, cita "),
                             m.Trecho(texto="Ávila", papel="jogador", chave="Ávila, Pedro")]),
    ]
    cap2 = livro.capitulos[1]
    cap2.blocos.insert(1, m.Paragrafo(trechos=[m.Trecho(texto="Sem chave: "),
                                                 m.Trecho(texto="Judit Polgar", papel="jogador")]))
    return livro


def test_ac3_o_indice_de_jogadores_ordena_pela_chave_com_links_e_numero_da_partida(tmp_path):
    livro = _livro()
    n = len(livro.capitulos)
    cap = indice.gerar(livro, "jogadores")
    assert cap in livro.capitulos and len(livro.capitulos) == n + 1 and cap.semantica == "index"
    assert cap.arquivo == "indice-jogadores.xhtml" and cap.titulo == "Índice de jogadores"
    assert m.texto_de(cap.blocos[0]) == "Índice de jogadores" and isinstance(cap.blocos[0], m.Titulo)
    entradas = [m.texto_de(b) for b in cap.blocos[1:]]
    assert entradas == ["Ávila, Pedro  2", "Karpov, Anatoly  2", "Kasparov, Garry  1, 2", "Polgar, Judit  ·",
                        "Wely, Loek van  1"]                                  # pela chave, sem acento e sem caixa
    assert all(b.classe == "indice" for b in cap.blocos[1:])
    # os links vão ao título mais próximo, no capítulo certo, com o alvo persistente
    kasparov = cap.blocos[3]
    links = [t.link for t in kasparov.trechos if t.link]
    alvos = [livro.capitulos[0].blocos[1], livro.capitulos[0].blocos[3]]
    assert links == [f"cap1.xhtml#{alvos[0].id}", f"cap1.xhtml#{alvos[1].id}"] and all(a.id_persistente for a in alvos)
    polgar = cap.blocos[4]
    assert [t.link for t in polgar.trechos if t.link] == ["cap2.xhtml#" + livro.capitulos[1].blocos[0].id]
    assert kasparov.trechos[0].negrito and kasparov.trechos[0].texto == "Kasparov, Garry"
    # o XHTML da página e o HTML exportado
    x = xhtml.escrever(cap)
    assert '<body epub:type="index">' in x and f'href="cap1.xhtml#{alvos[0].id}"' in x
    html_io.escrever_unico(livro, str(tmp_path / "livro.html"))
    h = open(tmp_path / "livro.html", encoding="utf-8").read()
    assert 'role="doc-index"' in h
    # refeito no lugar: o mesmo capítulo, sem outro igual
    livro.capitulos[0].blocos.append(m.Paragrafo(trechos=[m.Trecho(texto="Zukertort", papel="jogador",
                                                                   chave="Zukertort, Johannes")]))
    cap2 = indice.gerar(livro, "jogadores", idioma="en")
    assert cap2 is cap and len(livro.capitulos) == n + 1 and cap2.titulo == "Index of players"
    assert m.texto_de(cap2.blocos[-1]).startswith("Zukertort, Johannes")
    # o EPUB volta com a semântica
    from core.editor import epub

    epub.escrever(livro, str(tmp_path / "i.epub"))
    relido, _r = epub.ler(str(tmp_path / "i.epub"))
    assert relido.capitulos[-1].semantica == "index" and m.texto_de(relido.capitulos[-1].blocos[1]).startswith("Ávila")


def test_os_indices_de_partidas_e_de_aberturas_e_o_livro_sem_marcas():
    livro = _livro()
    partidas = indice.gerar(livro, "partidas")
    assert [m.texto_de(b) for b in partidas.blocos[1:]] == ["1. Loek van Wely – Garry Kasparov  1",
                                                            "2. Karpov – Kasparov  2"]
    assert not partidas.blocos[1].trechos[0].negrito
    aberturas = indice.gerar(livro, "aberturas")
    assert [m.texto_de(b) for b in aberturas.blocos[1:]] == ["C42  1"]
    assert [c.arquivo for c in livro.capitulos[-3:]] == ["cap2.xhtml", "indice-partidas.xhtml",
                                                          "indice-aberturas.xhtml"]
    with pytest.raises(ValueError):
        indice.gerar(livro, "cidades")
    vazio = m.Livro(metadados=m.Metadados(titulo="Vazio"),
                    capitulos=[m.Capitulo(arquivo="Text/a.xhtml", blocos=[p("Prosa sem marcas.")])])
    cap = indice.gerar(vazio, "jogadores")
    assert cap.arquivo == "Text/indice-jogadores.xhtml" and m.texto_de(cap.blocos[1]) == "(nada marcado no livro)"
    assert [e.chave for e in indice.entradas(livro, "aberturas")] == ["C42"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
