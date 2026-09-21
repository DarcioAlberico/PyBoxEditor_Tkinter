"""
Testes de `core/editor/consertar.py` (ED-07; SPEC_EDITOR §9 "Mend / Reformat"): o
XHTML mal-formado volta bem-formado com um aviso por coisa mudada (AC-ED07-2), o que já
está bem-formado não muda, a caixa das letras sobrevive (`viewBox`), e o
`reformatar_css` é idempotente e preserva os comentários (AC-ED07-3).

Rodar sem pytest:      python tests/test_editor_consertar.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.editor import consertar, xhtml


def test_consertar_fecha_o_aberto_e_avisa_cada_coisa():
    texto = ("<html><body><p>aberto<br>x & y <b>neg <i>it</b> fim</p>\n"
             '<img src=a.png alt="x" class=a class=b><!-- a -- b --></body></html>')
    saida, avisos = consertar.consertar(texto)
    assert xhtml.bem_formado(saida) is None
    assert saida == ('<html xmlns="http://www.w3.org/1999/xhtml"><body><p>aberto<br/>x &amp; y <b>neg <i>it</i></b> fim</p>\n'
                     '<img src="a.png" alt="x" class="a"/><!-- a - - b --></body></html>')
    texto_dos_avisos = "\n".join(avisos)
    assert "linha 1: <br> fechado com />" in texto_dos_avisos
    assert "<i> fechado antes de </b>" in texto_dos_avisos
    assert "linha 2: atributo repetido class descartado" in texto_dos_avisos
    assert "'--' dentro de coment" in texto_dos_avisos and "<html> sem xmlns" in texto_dos_avisos
    assert len(avisos) == 6


def test_o_bem_formado_volta_intacto_e_sem_aviso():
    texto = '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>ok &amp; &nbsp; <br/></p></body></html>'
    assert consertar.consertar(texto) == (texto, [])
    assert consertar.consertar("﻿" + texto) == (texto, [])


def test_fragmento_e_embrulhado_e_o_prefixo_epub_declarado():
    saida, avisos = consertar.consertar('<p>fragmento <span epub:type="noteref">n</span></p>')
    assert xhtml.bem_formado(saida) is None
    assert saida.startswith('<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">')
    assert "<body>\n<p>fragmento" in saida and avisos == ["sem <html>: o texto foi embrulhado em html/body"]
    saida, avisos = consertar.consertar('<html xmlns="http://www.w3.org/1999/xhtml"><body><span epub:type="x">a</span></body></html>')
    assert 'xmlns:epub="http://www.idpf.org/2007/ops"' in saida and any("prefixo epub" in a for a in avisos)
    assert xhtml.bem_formado(saida) is None


def test_a_caixa_das_letras_e_o_fechamento_orfao():
    saida, avisos = consertar.consertar('<html><body><svg viewBox="0 0 1 1"><rect width="1"/></svg></p></body></html>')
    assert 'viewBox="0 0 1 1"' in saida and '<rect width="1"/>' in saida
    assert any("</p> sem abertura" in a for a in avisos) and xhtml.bem_formado(saida) is None
    # o fechamento opcional do HTML5 (ED-10): `<p>um<p>dois` são dois parágrafos, não um dentro do outro
    saida, avisos = consertar.consertar("<html><body><p>um<p>dois")
    assert saida.endswith("<p>um</p><p>dois</p></body></html>") and xhtml.bem_formado(saida) is None
    assert sum("fechado no fim" in a for a in avisos) == 3 and any("fechamento opcional" in a for a in avisos)
    saida, _avisos = consertar.consertar("<html><body><ul><li>a<li>b</ul><table><tr><td>1<td>2<tr><td>3</table>")
    assert ("<ul><li>a</li><li>b</li></ul><table><tr><td>1</td><td>2</td></tr><tr><td>3</td></tr></table>" in saida
            and xhtml.bem_formado(saida) is None)


def test_reformatar_css_e_idempotente_e_guarda_os_comentarios():
    css = ("/* topo */\np{color:red;margin:0}\n@media print{ p>span.x{margin:0} /* dentro */ }\n"
           "@font-face{font-family:'A';src:url(a.otf)}\nh1 , h2{ color : #fff /* linha */ ; }\n")
    saida = consertar.reformatar_css(css)
    assert saida == ("/* topo */\np {\n  color: red;\n  margin: 0;\n}\n\n@media print {\n  p>span.x {\n    margin: 0;\n  }\n"
                     "  /* dentro */\n}\n\n@font-face {\n  font-family: 'A';\n  src: url(a.otf);\n}\n\n"
                     "h1 , h2 {\n  color: #fff /* linha */;\n}\n")
    assert consertar.reformatar_css(saida) == saida
    assert consertar.reformatar_css("") == "" and consertar.reformatar_css("\r\n") == ""
    assert consertar.reformatar_css('.q { content: "}" }') == '.q {\n  content: "}";\n}\n'


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
