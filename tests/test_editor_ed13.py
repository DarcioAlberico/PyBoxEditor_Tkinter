"""
Testes da ED-13 na janela (SPEC_EDITOR §7.6, §7.3 "Ajuda", §8.11): o `CF_HTML` injetado com
`<b>`, `<i>`, `<h2>` e `<img data:>` cola como negrito, itálico, título e figura
(AC-ED13-2); a preferência de corpo persiste em `Settings.get("editor")` e a próxima janela
abre com ela (AC-ED13-3); o cabeçalho do `CF_HTML` é lido pelos deslocamentos em bytes e
pelos comentários; "Preferências…" valida e aplica na hora; "Ajuda…" abre o texto.

Rodar sem pytest:      .venv/Scripts/python.exe tests/test_editor_ed13.py
"""

import base64
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from core.editor import area_de_transferencia as area_mod, modelo as m
from editor_ambiente import Janela
from ui.editor.janela import JanelaDoEditor
from ui.editor.preferencias import TEXTO_DE_AJUDA


def _png():
    from PIL import Image

    b = io.BytesIO()
    Image.new("RGB", (12, 9), (200, 30, 30)).save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode("ascii")


def _cf_html(fragmento: str) -> bytes:
    """Um payload `CF_HTML` como o Windows monta: cabeçalho com deslocamentos em bytes."""
    corpo = f"<html><body><!--StartFragment-->{fragmento}<!--EndFragment--></body></html>"
    cabecalho_modelo = ("Version:0.9\r\nStartHTML:{:08d}\r\nEndHTML:{:08d}\r\nStartFragment:{:08d}\r\n"
                        "EndFragment:{:08d}\r\n")
    tamanho = len(cabecalho_modelo.format(0, 0, 0, 0).encode("utf-8"))
    corpo_bytes = corpo.encode("utf-8")
    inicio = tamanho + corpo_bytes.index(b"<!--StartFragment-->") + len(b"<!--StartFragment-->")
    fim = tamanho + corpo_bytes.index(b"<!--EndFragment-->")
    cabecalho = cabecalho_modelo.format(tamanho, tamanho + len(corpo_bytes), inicio, fim)
    return cabecalho.encode("utf-8") + corpo_bytes


FRAGMENTO = ('<h2>Título colado</h2><p>Com <b>negrito</b> e <i>itálico</i>, ç e ♕.</p>'
             '<p><img src="data:image/png;base64,{png}" alt="Figura colada"/></p>')


def test_o_fragmento_cf_html_e_lido_pelos_deslocamentos_e_pelos_comentarios():
    fragmento = FRAGMENTO.format(png=_png())
    assert area_mod.fragmento_cf_html(_cf_html(fragmento)) == fragmento
    # só os comentários (sem deslocamentos); só o HTML; nada
    assert area_mod.fragmento_cf_html(f"<html><body><!--StartFragment-->{fragmento}<!--EndFragment--></body>") == fragmento
    assert area_mod.fragmento_cf_html("Version:0.9\r\n<p>solto</p>") == "<p>solto</p>"
    assert area_mod.fragmento_cf_html(b"") == "" and area_mod.fragmento_cf_html("texto sem tag") == ""
    # deslocamentos errados caem nos comentários
    quebrado = _cf_html(fragmento).replace(b"StartFragment:", b"StartFragment:9")
    assert area_mod.fragmento_cf_html(quebrado) == fragmento


def test_ac2_o_cf_html_injetado_cola_negrito_italico_titulo_e_figura():
    fragmento = FRAGMENTO.format(png=_png())
    with Janela() as t:
        j = t.j
        texto = t.texto
        t.sistema.texto = "Título colado\nCom negrito e itálico, ç e ♕."
        j.area.ler_html = lambda: area_mod.fragmento_cf_html(_cf_html(fragmento))
        texto.ir_para(texto.ordem[1], 0)
        antes = len(texto.ordem_do_capitulo)
        resultado = j.executar("colar")
        assert resultado.startswith("Título colado")
        blocos = texto.sincronizar().blocos
        assert len(texto.ordem_do_capitulo) >= antes + 3            # os três blocos (o parágrafo do cursor pode partir)
        titulo = next(b for b in blocos if isinstance(b, m.Titulo) and m.texto_de(b) == "Título colado")
        assert titulo.nivel == 2
        i = blocos.index(titulo)
        par, fig = blocos[i + 1], blocos[i + 2]
        assert [(tr.texto, tr.negrito, tr.italico) for tr in par.trechos] == [
            ("Com ", False, False), ("negrito", True, False), (" e ", False, False), ("itálico", False, True),
            (", ç e ♕.", False, False)]
        assert isinstance(fig, m.Figura) and fig.alt == "Figura colada" and fig.recurso.startswith("Images/embutida-")
        assert fig.recurso in j.projeto.livro.recursos and j.projeto.livro.recursos[fig.recurso].dados.startswith(b"\x89PNG")
        assert j.projeto.sujo and "Colado HTML: 3 bloco(s)" in j.campos["aviso"].cget("text")
        # um fragmento de uma linha entra inline no parágrafo do cursor
        j.area.ler_html = lambda: "<b>forte</b> e fraco"
        t.sistema.texto = "forte e fraco"
        texto.ir_para(texto.ordem[1], 0)
        antes = len(texto.ordem_do_capitulo)
        j.executar("colar")
        assert len(texto.ordem_do_capitulo) == antes                # inline: nenhum bloco a mais
        primeiro = next(b for b in texto.sincronizar().blocos if "forte e fraco" in m.texto_de(b))
        assert primeiro.trechos[0].texto == "forte" and primeiro.trechos[0].negrito and not primeiro.trechos[1].negrito
        # sem HTML, o colar de texto continua o mesmo; o colar sem formatação ignora o HTML
        j.area.ler_html = lambda: None
        t.sistema.texto = "só texto"
        assert j.executar("colar") == "só texto"
        j.area.ler_html = lambda: "<b>x</b>"
        t.sistema.texto = "x"
        assert j.executar("colar_sem_formatacao") == "x"
        # HTML quebrado cai no texto
        j.area.ler_html = lambda: "<p><b>aberto"
        t.sistema.texto = "aberto"
        assert j.executar("colar") in ("aberto", "(html)")
        # a leitura do Windows não derruba: sem HTML no sistema devolve None (ou o que houver)
        assert area_mod.html_do_windows() is None or isinstance(area_mod.html_do_windows(), str)


def test_ac3_a_preferencia_de_corpo_persiste_e_a_proxima_janela_abre_com_ela():
    with Janela() as t:
        j = t.j
        assert j._estilo_de_tela().corpo_pt == 12.0
        valores = {"familia": "Georgia", "corpo_pt": "15", "familia_mono": "Consolas", "zoom": "1", "largura_de_leitura": "0",
                   "tema_codigo": "escuro", "tabulacao": "4", "idioma_ortografia": "pt", "fonte_diagrama": "SkakNew-Diagram",
                   "modo_diagrama": "fonte", "indicador_de_lado": "legenda", "figurinas_ao_digitar": "não", "ncx": "não",
                   "notas": "fim", "intervalo_rascunho": "30"}
        gravado = j.executar("preferencias", valores)
        editor = t.settings.get("editor")
        assert editor["estilo_de_tela"]["corpo_pt"] == 15.0 and gravado["estilo_de_tela"]["corpo_pt"] == 15.0
        assert editor["tema_codigo"] == "escuro" and editor["tabulacao"] == 4 and editor["modo_diagrama"] == "fonte"
        assert editor["indicador_de_lado"] == "legenda" and editor["figurinas_ao_digitar"] is False
        assert editor["ncx"] is False and editor["notas"] == "fim" and editor["intervalo_rascunho"] == 30.0
        assert not j.variaveis["figurinas_ao_digitar"].get() and j.rascunho.intervalo_s == 30.0
        # aplicado na hora: o capítulo aberto redesenha com o corpo novo
        assert t.texto.tela.corpo_pt == 15.0
        # pela caixa de formulário, e cancelar
        t.caixas.formulario_resposta = {**valores, "corpo_pt": "13,5"}
        assert j.executar("preferencias")["estilo_de_tela"]["corpo_pt"] == 13.5
        t.caixas.formulario_resposta = None
        assert j.executar("preferencias") is None
        # validação
        j.executar("preferencias", {**valores, "corpo_pt": "abc"})
        assert "não é um número" in t.caixas.entradas()[-1]
        j.executar("preferencias", {**valores, "zoom": "9"})
        assert "entre 0.5 e 4" in t.caixas.entradas()[-1]
        j.executar("preferencias", {**valores, "tema_codigo": "roxo"})
        assert "não é uma das opções" in t.caixas.entradas()[-1]
        # a próxima janela, com o mesmo Settings, abre com o corpo gravado
        outra = JanelaDoEditor(t.raiz, settings=t.settings)
        try:
            outra.withdraw()
            assert outra._estilo_de_tela().corpo_pt == 13.5 and outra._tema_codigo == "escuro"
            assert outra._preferencia("indicador_de_lado") == "legenda"
        finally:
            outra.destroy()
        # a ajuda
        assert j.executar("ajuda") == TEXTO_DE_AJUDA and t.caixas.chamadas[-1][:2] == ("texto", "Ajuda")
        assert "F6" in TEXTO_DE_AJUDA and "Ctrl+Shift+D" in TEXTO_DE_AJUDA


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
