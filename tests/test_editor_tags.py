"""
Testes de `ui/editor/tags.py` (ED-03; DEC-03): os nomes das tags, o estilo de tela, a
cascata da CSS mínima sobre os estilos, a fonte derivada (uma `tkfont.Font` por
combinação, em cache) e a configuração das tags num `tk.Text`.

Rodar sem pytest:      python tests/test_editor_tags.py
"""

import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from conftest import raiz_tk
from core.editor import css_minima
from ui.editor import tags as T


def test_nomes_valores_e_familias_de_tags():
    assert T.nome("link:", "Text/cap 1.xhtml#x") == "link:Text/cap%201.xhtml#x"
    assert T.valor("link:Text/cap%201.xhtml#x") == "Text/cap 1.xhtml#x" and T.prefixo("link:x") == "link:"
    assert T.valor("b") == "" and T.prefixo("b") == "b"
    assert T.e_de_caractere("b") and T.e_de_caractere("cor:#ff0000") and not T.e_de_caractere("p:corpo")
    assert T.e_de_paragrafo("p:titulo2") and T.e_de_paragrafo("manter") and not T.e_de_paragrafo("b")
    assert T.e_de_tela("fonte:Georgia:12:b") and T.e_de_tela("protegido") and not T.e_de_tela("b")
    assert T.e_quebra("qs") and T.e_quebra("qi:2") and not T.e_quebra("quebra")


def test_a_cascata_do_estilo_de_paragrafo_com_e_sem_folha():
    estilos = T.Estilos(T.EstiloDeTela(familia="Georgia", corpo_pt=12.0))
    corpo = estilos.de_paragrafo("corpo")
    assert corpo["familia"] == "Georgia" and corpo["corpo_pt"] == 12.0 and not corpo["negrito"]
    titulo = estilos.de_paragrafo("titulo1")
    assert titulo["negrito"] and titulo["corpo_pt"] == 24.0                     # 2em, como o navegador
    assert estilos.de_paragrafo("comentario")["italico"] and estilos.de_paragrafo("legenda")["alinhamento"] == "centro"
    folha = css_minima.ler("p.comentario { font-style: italic; color: #444 }\nh1 { font-size: 1.5em; font-weight: normal }\n"
                           "p { text-indent: 1.2em; margin-top: 0.5em }\nspan.lance { color: #004488; font-weight: bold }\n"
                           ".versalete { font-variant: small-caps }")
    estilos = T.Estilos(T.EstiloDeTela(corpo_pt=12.0), folha)
    comentario = estilos.de_paragrafo("comentario")
    assert comentario["italico"] and comentario["cor"] == "#444444"
    assert comentario["recuo_primeira_em"] == 1.2 and comentario["antes_em"] == 0.5
    titulo = estilos.de_paragrafo("titulo1")
    assert titulo["corpo_pt"] == 18.0 and not titulo["negrito"]                   # a folha vence o padrão
    lance = estilos.de_caractere("lance")
    assert lance["cor"] == "#004488" and lance["negrito"]
    assert estilos.de_caractere("", ["versalete"])["versalete"]
    assert estilos.de_caractere("comentario")["italico"]                          # sem folha para ele: o padrão


def test_a_fonte_derivada_e_o_cache():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        estilos = T.Estilos(T.EstiloDeTela(familia="Georgia", corpo_pt=12.0, familia_mono="Consolas"))
        nome, atributos = T.fonte_derivada(estilos, "corpo", ())
        assert nome == "fonte:Georgia:12:" and atributos["corpo"] == 12 and not atributos["negrito"]
        nome, atributos = T.fonte_derivada(estilos, "corpo", ("b", "i"))
        assert nome == "fonte:Georgia:12:bi" and atributos["negrito"] and atributos["italico"]
        nome, _ = T.fonte_derivada(estilos, "titulo2", ("i",))
        assert nome == "fonte:Georgia:18:bi"                                        # negrito do estilo + itálico próprio
        nome, atributos = T.fonte_derivada(estilos, "corpo", ("sobre", "fam:Arial", "corpo:10"))
        assert nome == "fonte:Arial:10:o" and atributos["variante"] == "sobre"
        nome, _ = T.fonte_derivada(estilos, "corpo", ("code",))
        assert nome == "fonte:Consolas:12:"
        nome, _ = T.fonte_derivada(estilos, "corpo", ("fam:simbolos",))
        assert nome == "fonte:Georgia:12:"                                          # `simbolos` é a família da tela
        estilos.tela.zoom = 1.5
        assert T.fonte_derivada(estilos, "corpo", ())[0] == "fonte:Georgia:18:"     # o zoom só mexe na tela
        fontes = T.Fontes(raiz)
        a = fontes.fonte("Georgia", 12, True, False, "")
        b = fontes.fonte("Georgia", 12, True, False, "")
        c = fontes.fonte("Georgia", 12, False, False, "vers")
        assert a is b and c is not a and len(fontes) == 2
        assert c.cget("size") == 10                                                 # versalete: 0,85 do corpo
    finally:
        raiz.destroy()


def test_configurar_as_tags_num_text_e_o_realce_escuro_com_texto_branco():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        texto = tk.Text(raiz)
        estilos = T.Estilos(T.EstiloDeTela(corpo_pt=12.0), css_minima.ler("p.comentario { color: #444 }"))
        fontes = T.Fontes(raiz)
        T.configurar(texto, estilos, fontes)
        assert str(texto.tag_cget("u", "underline")) in ("1", "True") and texto.tag_cget("orto", "underlinefg") == "#c00000"
        T.configurar_paragrafo(texto, "p:comentario", estilos, fontes)
        assert texto.tag_cget("p:comentario", "foreground") == "#444444"
        T.configurar_paragrafo(texto, "al:centro", estilos, fontes)
        assert texto.tag_cget("al:centro", "justify") == "center"
        T.configurar_paragrafo(texto, "li:2", estilos, fontes)
        assert int(texto.tag_cget("li:2", "lmargin1")) > int(texto.tag_cget("li:2", "lmargin1")) - 1
        T.configurar_caractere(texto, "fundo:#000080", estilos, fontes)
        assert texto.tag_cget("fundo:#000080", "foreground") == "#ffffff"            # §8.2: realce escuro
        T.configurar_caractere(texto, "fundo:#ffff00", estilos, fontes)
        assert texto.tag_cget("fundo:#ffff00", "foreground") == ""
        T.configurar_caractere(texto, "link:x.xhtml", estilos, fontes)
        assert texto.tag_cget("link:x.xhtml", "foreground") == estilos.tela.cor_do_link
        nome, atributos = T.fonte_derivada(estilos, "corpo", ("sub",))
        T.configurar_fonte(texto, nome, atributos, fontes, estilos)
        assert int(texto.tag_cget(nome, "offset")) < 0
    finally:
        raiz.destroy()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
