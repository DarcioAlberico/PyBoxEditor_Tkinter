"""
Testes da ED-15: `core/editor/limpar_importado.py` (a marcação do Calibre e do
*immersive-translate* reescrita no dialeto, sem perder texto) e, na janela, as vistas
Texto · Código · Dividido, o "Limpar marcação importada…" e o aviso ao abrir um capítulo
cheio de ilhas.

Rodar sem pytest:      python tests/test_editor_limpar_importado.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import limpar_importado as li
from core.editor import modelo as m
from core.editor import xhtml

CSS = """/* folha do Calibre */
.calibre { display: block }
.calibre1 { display: block; text-align: justify; margin: 0 0 0 12pt }
.calibre2 { font-weight: bold }
span.calibre3, .outra { font-style: italic; font-family: serif }
.calibre4 { font-variant: small-caps; text-decoration: underline }
.calibre5 { vertical-align: super; font-size: 0.7em }
"""

IMPORTADO = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title>
<link href="../Styles/s.css" rel="stylesheet" type="text/css"/></head>
<body class="calibre"><div class="calibre">
<p class="calibre1" data-imt_insert_failed="1"><a id="filepos12"></a><a id="alvo"></a>46.<span class="calibre2">R</span>xf5 <span class="notranslate immersive-translate-target-translation-theme-none"><span class="calibre3">texto</span> traduzido</span></p>
<p style="text-indent: 12pt; text-align: center">c<font color="red" face="x">z</font><span class="calibre5">2</span></p>
<p><span class="calibre4">Karpov</span> e <span id="solto">Kasparov</span></p>
<div class="calibre">solto <b>b</b></div>
</div></body></html>
"""


def _texto_visivel(documento: str) -> str:
    corpo = documento[documento.index("<body"):]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", corpo)).strip()


def test_regras_calibre_le_classe_solta_com_elemento_e_em_lista():
    regras = li.regras_calibre([CSS])
    assert regras["calibre2"] == {"font-weight": "bold"}
    assert regras["calibre3"]["font-style"] == "italic"
    assert "outra" not in regras
    assert regras["calibre1"]["text-align"] == "justify"


def test_a_marcacao_importada_vira_dialeto_sem_perder_texto():
    assert li.contar_ilhas(IMPORTADO) > 0
    novo, rel = li.limpar(IMPORTADO, [CSS], ids_usados={"alvo"})
    assert _texto_visivel(novo) == _texto_visivel(IMPORTADO)          # nenhum caractere de texto some
    assert li.contar_ilhas(novo) == 0
    assert '<p id="alvo" style="text-align: justify">46.' in novo      # a âncora do link virou o id do bloco
    assert "data-imt" not in novo and "immersive" not in novo and "notranslate" not in novo
    assert "calibre" not in novo and "<div" not in novo and "<font" not in novo
    assert "filepos12" not in novo                                      # a âncora sem uso sai
    assert 'id="solto"' not in novo
    assert "<strong>R</strong>" in novo and "<em>texto</em> traduzido" in novo
    assert '<span class="versalete"><u>Karpov</u></span>' in novo
    assert "<sup>2</sup>" in novo and '<span style="color: red">z</span>' in novo
    assert '<p style="text-align: center">' in novo
    assert "<p>solto <b>b</b></p>" in novo
    # o que não tem lugar no dialeto é contado, não escondido
    assert rel.descartadas["margin"] == 1 and rel.descartadas["text-indent"] == 1
    assert rel.trocas["classe calibre convertida"] >= 5 and rel.trocas["âncora sem uso removida"] == 1
    # e o leitor lê: negrito, itálico e versalete como trechos
    cap = xhtml.ler(novo, "Text/c.xhtml")
    trechos = [t for b in cap.blocos for t in getattr(b, "trechos", [])]
    assert any(t.negrito and t.texto == "R" for t in trechos)
    assert any(t.italico and t.texto == "texto" for t in trechos)
    assert any(t.versalete and t.sublinhado and t.texto == "Karpov" for t in trechos)


def test_limpar_e_idempotente_e_sem_ids_as_ancoras_ficam():
    novo, _ = li.limpar(IMPORTADO, [CSS], ids_usados={"alvo"})
    de_novo, rel = li.limpar(novo, [CSS], ids_usados={"alvo"})
    assert de_novo == novo and not rel.trocas
    sem_ids, _ = li.limpar(IMPORTADO, [CSS])
    assert "filepos12" in sem_ids and 'id="solto"' in sem_ids


def test_o_que_ja_e_dialeto_nao_muda():
    livro_nosso = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml">'
                   '<head><title>t</title></head><body>\n'
                   '<figure class="diagrama" data-fen="8/8/8/8/8/8/8/K6k w - - 0 1" data-lado="w">'
                   '<img src="../Images/d.png" alt="x"/></figure>\n'
                   '<p class="primeira" data-origem-pagina="3">Um <span class="sim fig">♘</span>f3</p>\n'
                   '</body></html>\n')
    novo, rel = li.limpar(livro_nosso, [CSS], ids_usados=set())
    assert novo == livro_nosso and not rel.trocas


def test_imagem_sozinha_vira_figura_e_o_p_diagrama_do_calibre_nao_e_o_nosso():
    importado = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml">'
                 '<head><title>t</title></head><body class="calibre">\n'
                 '<p class="diagrama"><img src="d1.png" alt="Diagrama" class="calibre1"/></p>\n'
                 '<div class="diagram"> <img src="d2.png" alt="Diagrama"/> </div>\n'
                 '<p>1.e4 <img class="inlineimg" src="n.png" alt=""/>f3</p>\n'
                 '</body></html>\n')
    novo, rel = li.limpar(importado, [CSS], ids_usados=set())
    assert '<figure><img src="d1.png" alt="Diagrama"/></figure>' in novo
    assert '<figure> <img src="d2.png" alt="Diagrama"/> </figure>' in novo
    assert rel.trocas["imagem sozinha vira figure"] == 2
    cap = xhtml.ler(novo, "c.xhtml")
    assert [type(b).__name__ for b in cap.blocos][:2] == ["Figura", "Figura"]
    # a figurina desenhada como imagem no meio do lance fica: não há texto a pôr no lugar
    assert '<img class="inlineimg" src="n.png" alt=""/>' in novo and li.contar_ilhas(novo) == 1


def test_o_style_do_tradutor_no_head_sai_e_o_do_livro_fica():
    importado = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml"><head>\n'
                 '<title>t</title>\n<style type="text/css">p.x { color: red }</style>\n'
                 '<style type="text/css">:root { --immersive-translate-theme-underline: 1px; }</style>\n'
                 '</head><body><p class="notranslate">a</p></body></html>\n')
    novo, rel = li.limpar(importado, [], ids_usados=set())
    assert "immersive-translate" not in novo and "p.x { color: red }" in novo
    assert rel.trocas["<style> de ferramenta removido"] == 1
    xhtml.ler(novo, "c.xhtml")                                         # continua bem-formado


def test_ids_usados_vem_dos_href():
    assert li.ids_usados(['<a href="c2.xhtml#n1">x</a>', "<a href='#topo'>y</a>", '<a href="c3.xhtml">z</a>']) \
        == {"n1", "topo"}


# ----------------------------------------------------------------------
# Na janela
# ----------------------------------------------------------------------

def _importar_no_primeiro_capitulo(j):
    from ui.editor.janela import _copiar_capitulo

    livro = j.projeto.livro
    livro.recursos["Styles/s.css"] = m.Recurso(caminho="Styles/s.css", tipo_mime="text/css", dados=CSS.encode())
    cap = livro.capitulos[0]
    _copiar_capitulo(xhtml.ler(IMPORTADO, cap.arquivo), cap)
    cap.folhas = ["Styles/s.css"]
    aba = j.abas.por_arquivo(cap.arquivo)
    if aba is not None:
        j._recarregar_aba(aba)
    return cap


def test_as_tres_vistas_e_o_botao_marcado():
    from editor_ambiente import Janela

    with Janela() as t:
        j = t.j
        j._gravar_preferencia("previa_ms", 0)
        barra = j.barra_de_arquivo
        assert set(barra.botoes) >= {"modo_texto", "modo_codigo", "modo_dividido"}
        assert "alternar_modo" not in barra.botoes
        assert j.operacoes.vista_atual() == "texto" and barra.vista.get() == "texto"
        assert j.executar("modo_dividido") == "dividido"
        aba = j.aba_ativa()
        assert aba.modo == "codigo" and aba.dados.get("previa") is not None and barra.vista.get() == "dividido"
        assert j.executar("modo_codigo") == "codigo" and aba.dados.get("previa") is None
        assert barra.vista.get() == "codigo"
        j.executar("previa")                                  # o F12 também marca a vista
        assert barra.vista.get() == "dividido"
        assert j.executar("modo_texto") == "texto" and barra.vista.get() == "texto"
        # o clique no botão da vista passa pelo mesmo caminho
        barra.botoes["modo_dividido"].invoke()
        assert j.operacoes.vista_atual() == "dividido" and barra.vista.get() == "dividido"
        # mal-formado não sai do código, e o botão volta à vista real
        editor = j.aba_ativa().widget
        editor.texto.insert("end", "<p>aberto")
        barra.botoes["modo_texto"].invoke()
        assert j.aba_ativa().modo == "codigo" and barra.vista.get() == "dividido"


def test_limpar_importado_no_capitulo_e_o_aviso_ao_abrir():
    from editor_ambiente import Janela

    with Janela() as t:
        j = t.j
        cap = _importar_no_primeiro_capitulo(j)
        j.abas.fechar(j.abas.por_arquivo(cap.arquivo))
        j.abrir_capitulo(cap.arquivo)
        # o aviso sai uma vez, com a saída
        assert cap.arquivo in j.operacoes._avisados
        assert "Limpar marcação importada" in j.campos["aviso"].cget("text")
        antes = li.contar_ilhas(xhtml.escrever(cap), cap.arquivo)
        assert antes > 0
        t.caixas.escolha_resposta = 0                         # "Capítulo atual"
        rel = j.executar("limpar_importado")
        assert rel is not None and rel.ilhas_antes == antes and rel.ilhas_depois == 0
        assert any(c[0] == "pergunta" and "Reescrever 1 capítulo" in c[1] for c in t.caixas.chamadas)
        assert not any(isinstance(b, m.IlhaBruta) for b in cap.blocos)
        assert "46.Rxf5 texto traduzido" in " ".join(m.texto_de(b) for b in cap.blocos)
        # a aba em texto foi redesenhada do capítulo limpo
        assert not any(isinstance(b, m.IlhaBruta) for b in t.texto.sincronizar().blocos)
        assert j.projeto.sujo
        # de novo: nada a limpar
        rel = j.operacoes.limpar_importado(escopo="capitulo", confirmar=False)
        assert rel.ilhas_antes == 0 and any(c[0] == "informar" for c in t.caixas.chamadas)


def test_limpar_importado_cancelado_nao_mexe():
    from editor_ambiente import Janela

    with Janela() as t:
        j = t.j
        cap = _importar_no_primeiro_capitulo(j)
        blocos = list(cap.blocos)
        t.caixas.pergunta_resposta = False
        assert j.operacoes.limpar_importado(escopo="livro") is None
        assert cap.blocos == blocos


def test_menu_e_atalho():
    from ui.editor import atalhos, menus

    comandos = {i.comando for i in menus.EXIBIR} | {i.comando for i in menus.FERRAMENTAS}
    assert {"modo_dividido", "limpar_importado"} <= comandos
    assert any(a.comando == "modo_dividido" and a.atalho == "Ctrl+F11" for a in atalhos.TABELA)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
