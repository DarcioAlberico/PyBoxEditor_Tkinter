"""
Testes de `ui/editor/dump.py` (ED-03; DEC-03): `dump_para_blocos` sem Tk — a lista do
`dump` é montada à mão — e `indice_de` (AC-ED03-9).

Rodar sem pytest:      python tests/test_editor_dump.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.editor import modelo as m
from ui.editor import dump


def _itens(*eventos):
    """`("mark", "bloco:x", "1.0")`, `("on", "b", "1.0")`, `("txt", "abc", "1.0")`… em tuplas do `dump`."""
    saida = []
    for chave, valor, indice in eventos:
        saida.append({"on": "tagon", "off": "tagoff", "txt": "text", "win": "window"}.get(chave, chave))
        saida[-1] = (saida[-1], valor, indice)
    return saida


def test_paragrafo_com_marcadores_e_tags_independentes():
    itens = _itens(("mark", "bloco:p1", "1.0"), ("on", "p:corpo", "1.0"), ("on", "al:centro", "1.0"),
                   ("txt", "Um ", "1.0"), ("on", "b", "1.3"), ("on", "link:Text/x.xhtml#a", "1.3"),
                   ("txt", "dois", "1.3"), ("off", "b", "1.7"), ("off", "link:Text/x.xhtml#a", "1.7"),
                   ("txt", " três", "1.7"), ("txt", "\n", "1.11"), ("off", "p:corpo", "2.0"),
                   ("off", "al:centro", "2.0"))
    blocos, notas = dump.dump_para_blocos(itens, {}, {})
    assert notas == [] and len(blocos) == 1
    p = blocos[0]
    assert isinstance(p, m.Paragrafo) and p.id == "p1" and p.estilo == "corpo" and p.alinhamento == "centro"
    assert [(t.texto, t.negrito, t.link) for t in p.trechos] == [("Um ", False, ""), ("dois", True, "Text/x.xhtml#a"),
                                                                 (" três", False, "")]


def test_titulo_quebra_suave_nota_pagina_e_o_que_e_so_de_tela():
    itens = _itens(("mark", "bloco:t", "1.0"), ("on", "p:titulo2", "1.0"), ("on", "fonte:Georgia:18:b", "1.0"),
                   ("txt", "Título", "1.0"), ("on", "qs", "1.6"), ("on", "quebra", "1.6"), ("on", "protegido", "1.6"),
                   ("txt", "\n", "1.6"), ("off", "qs", "2.0"), ("off", "quebra", "2.0"), ("off", "protegido", "2.0"),
                   ("txt", "continua", "2.0"), ("on", "nota:n1", "2.8"), ("on", "protegido", "2.8"), ("txt", "¹", "2.8"),
                   ("off", "nota:n1", "2.9"), ("off", "protegido", "2.9"),
                   ("on", "pagina:12", "2.9"), ("on", "protegido", "2.9"), ("txt", "⁞", "2.9"),
                   ("off", "pagina:12", "2.10"), ("off", "protegido", "2.10"),
                   ("on", "invisivel", "2.10"), ("on", "protegido", "2.10"), ("txt", "¶", "2.10"),
                   ("off", "invisivel", "2.11"), ("off", "protegido", "2.11"), ("txt", " fim\n", "2.11"))
    anteriores = {"t": m.Titulo(trechos=[], nivel=2, id="t", classe="capitulo", extras={"epub:type": "chapter"}),
                  "n1": m.Nota(id="n1", blocos=[m.Paragrafo(trechos=[m.Trecho(texto="nota")])])}
    blocos, notas = dump.dump_para_blocos(itens, {}, anteriores)
    t = blocos[0]
    assert isinstance(t, m.Titulo) and t.nivel == 2 and t.classe == "capitulo" and t.extras == {"epub:type": "chapter"}
    assert [(x.texto, x.quebra_antes, x.nota, x.pagina) for x in t.trechos] == [
        ("Título", False, "", None), ("continua", True, "", None), ("", False, "n1", None), (" fim", False, "", 12)]
    assert [n.id for n in notas] == ["n1"]


def test_lista_aninhada_citacao_e_objeto_pelo_registro():
    diagrama = m.Diagrama(fen="8/8/8/8/8/8/8/8 w - - 0 1", id="d1")
    itens = _itens(
        ("mark", "bloco:l", "1.0"), ("on", "p:corpo", "1.0"), ("on", "lista:o", "1.0"), ("on", "ini:3", "1.0"),
        ("on", "li:1", "1.0"), ("on", "marcador", "1.0"), ("on", "protegido", "1.0"), ("txt", "3. ", "1.0"),
        ("off", "marcador", "1.3"), ("off", "protegido", "1.3"), ("txt", "um", "1.3"),
        ("on", "qi:2", "1.5"), ("on", "quebra", "1.5"), ("on", "protegido", "1.5"), ("txt", "\n", "1.5"),
        ("off", "qi:2", "2.0"), ("off", "quebra", "2.0"), ("off", "protegido", "2.0"), ("off", "li:1", "2.0"),
        ("on", "li:2", "2.0"), ("on", "sub:n|quadrado|1", "2.0"), ("on", "marcador", "2.0"), ("on", "protegido", "2.0"),
        ("txt", "◦ ", "2.0"), ("off", "marcador", "2.2"), ("off", "protegido", "2.2"), ("txt", "filho", "2.2"),
        ("off", "li:2", "2.7"), ("off", "sub:n|quadrado|1", "2.7"), ("txt", "\n", "2.7"),
        ("off", "lista:o", "3.0"), ("off", "ini:3", "3.0"),
        ("mark", "bloco:c", "3.0"), ("on", "p:citacao", "3.0"), ("on", "cit", "3.0"), ("txt", "um", "3.0"),
        ("on", "qp", "3.2"), ("on", "quebra", "3.2"), ("on", "protegido", "3.2"), ("txt", "\n", "3.2"),
        ("off", "qp", "4.0"), ("off", "quebra", "4.0"), ("off", "protegido", "4.0"), ("txt", "dois\n", "4.0"),
        ("off", "p:citacao", "5.0"), ("off", "cit", "5.0"),
        ("mark", "bloco:d1", "5.0"), ("on", "objeto", "5.0"), ("on", "protegido", "5.0"), ("win", ".t.obj", "5.0"),
        ("off", "objeto", "5.1"), ("off", "protegido", "5.1"), ("txt", "\n", "5.1"),
    )
    blocos, _ = dump.dump_para_blocos(itens, {".t.obj": diagrama}, {"d1": diagrama})
    assert [type(b).__name__ for b in blocos] == ["Lista", "Citacao", "Diagrama"]
    lista = blocos[0]
    assert lista.ordenada and lista.inicio == 3 and len(lista.itens) == 1
    assert m.texto_de(lista.itens[0].paragrafos[0]) == "um"
    filhos = lista.itens[0].filhos
    assert filhos is not None and not filhos.ordenada and filhos.marcador == "quadrado"
    assert m.texto_de(filhos.itens[0].paragrafos[0]) == "filho"
    citacao = blocos[1]
    assert [m.texto_de(p) for p in citacao.blocos] == ["um", "dois"] and citacao.blocos[0].estilo == "citacao"
    assert blocos[2] is diagrama


def test_marcas_coincidentes_e_bloco_apagado():
    itens = _itens(("mark", "bloco:velho", "1.0"), ("mark", "bloco:novo", "1.0"), ("on", "p:corpo", "1.0"),
                   ("txt", "texto\n", "1.0"))
    blocos, _ = dump.dump_para_blocos(itens, {}, {})
    assert [b.id for b in blocos] == ["novo"]                          # a mais nova sobrevive


def test_ac9_indice_de_pula_o_que_e_so_de_tela():
    itens = _itens(("mark", "bloco:p", "3.0"), ("on", "marcador", "3.0"), ("on", "protegido", "3.0"),
                   ("txt", "1. ", "3.0"), ("off", "marcador", "3.3"), ("off", "protegido", "3.3"),
                   ("txt", "ab", "3.3"), ("on", "invisivel", "3.5"), ("on", "protegido", "3.5"), ("txt", "¶", "3.5"),
                   ("off", "invisivel", "3.6"), ("off", "protegido", "3.6"), ("txt", "cd", "3.6"),
                   ("on", "qs", "3.8"), ("on", "quebra", "3.8"), ("on", "protegido", "3.8"), ("txt", "\n", "3.8"),
                   ("off", "qs", "4.0"), ("off", "quebra", "4.0"), ("off", "protegido", "4.0"), ("txt", "efgh\n", "4.0"))
    assert dump.indice_de(itens, "p", 0) == "3.3"                       # o marcador não conta
    assert dump.indice_de(itens, "p", 2) == "3.6"                       # o ¶ invisível não conta
    assert dump.indice_de(itens, "p", 4) == "3.8"                       # a quebra suave conta um
    assert dump.indice_de(itens, "p", 5) == "4.0"                       # o 6º caractere do modelo
    assert dump.indice_de(itens, "p", 9) == "4.4"
    assert dump.indice_de(itens, "outro", 0) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
