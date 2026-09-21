"""
Testes de `ui/editor/previa.py` e da prévia na janela (ED-08; SPEC_EDITOR DEC-05, §9.6):
`Previa(atraso_ms=0)` + `update()` mostra o `<p>`; um XHTML mal-formado mantém a prévia
anterior; `ir_ao_bloco(linha)`; `abrir_alvo` real troca de aba (AC-ED08-7); `F12` liga e
desliga a prévia ao lado do código, que segue o cursor e devolve a linha ao clique.

Rodar sem pytest:      python tests/test_editor_previa.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from conftest import raiz_tk
from core.editor import modelo as m
from editor_ambiente import Janela
from ui.editor.previa import Previa

XHTML = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml">\n<head>\n'
         "<title>t</title>\n</head>\n<body>\n<h1>Título</h1>\n<p>Primeiro parágrafo.</p>\n"
         "<p>Segundo <strong>forte</strong>.</p>\n</body>\n</html>\n")


def test_ac7_a_previa_mostra_o_p_mantem_a_anterior_no_mal_formado_e_vai_ao_bloco():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        cliques = []
        previa = Previa(raiz, atraso_ms=0, ao_clicar=cliques.append)
        previa.pack(fill="both", expand=True)
        previa.atualizar(XHTML, "c.xhtml")
        raiz.update()
        textos = [m.texto_de(b) for b in previa.texto_rico.sincronizar().blocos]
        assert textos == ["Título", "Primeiro parágrafo.", "Segundo forte."]
        assert str(previa.texto_rico.texto.cget("state")) == "disabled" and previa.erro is None
        # mal-formado: fica a anterior, com o erro no rodapé
        previa.atualizar(XHTML.replace("</p>\n</body>", "\n</body>"), "c.xhtml")
        raiz.update()
        assert previa.erro is not None and "mal-formado" in previa.rodape.cget("text")
        assert [m.texto_de(b) for b in previa.texto_rico.sincronizar().blocos] == textos
        # de volta ao bom, o rodapé limpa; `ir_ao_bloco` pela linha da fonte
        previa.atualizar(XHTML, "c.xhtml")
        raiz.update()
        assert previa.rodape.cget("text") == ""
        blocos = previa.capitulo.blocos
        assert [b.linha_fonte for b in blocos] == [7, 8, 9]
        assert previa.ir_ao_bloco(8) == blocos[1].id and previa.texto_rico.bloco_atual() == blocos[1].id
        assert previa.ir_ao_bloco(100) == blocos[2].id and previa.ir_ao_bloco(1) == blocos[0].id
        # o clique devolve a linha da fonte do bloco clicado
        previa.texto_rico.ir_para(blocos[2].id, 2)
        assert previa.linha_do_indice("insert") == 9
        # com atraso, a última chamada é a que vale
        previa.atraso_ms = 50
        previa.atualizar(XHTML.replace("Primeiro", "Um"), "c.xhtml")
        previa.atualizar(XHTML.replace("Primeiro", "Dois"), "c.xhtml")
        raiz.after(150, raiz.quit)
        raiz.mainloop()
        assert [m.texto_de(b) for b in previa.texto_rico.sincronizar().blocos][1] == "Dois parágrafo."
    finally:
        raiz.destroy()


def test_f12_liga_a_previa_ao_lado_do_codigo_e_ela_segue_o_cursor():
    with Janela() as t:
        j = t.j
        j.executar("previa")
        assert "modo código" in t.caixas.entradas()[-1]
        j.executar("alternar_modo")
        aba = j.aba_ativa()
        j._gravar_preferencia("previa_ms", 0)
        previa = j.executar("previa")
        assert previa is not None and aba.dados["previa"] is previa and previa.capitulo is not None
        assert previa.winfo_manager() == "pack" and j.menus.estado("previa") == "normal"
        # o cursor no código leva a prévia ao bloco; uma edição redesenha
        editor = aba.widget
        linha_do_titulo = int(editor.texto.search("<h1", "1.0").split(".")[0])
        editor.ir_para(linha_do_titulo)
        j.update()
        assert previa.texto_rico.bloco_atual() == previa.bloco_da_linha(linha_do_titulo)
        editor.texto.insert(f"{linha_do_titulo}.0", "<p>Inserido pela prévia.</p>\n")
        j.update()
        assert any(m.texto_de(b) == "Inserido pela prévia." for b in previa.capitulo.blocos)
        # o clique na prévia leva o código à linha
        previa.ao_clicar(linha_do_titulo + 1)
        assert editor.posicao[0] == linha_do_titulo + 1
        assert j.executar("previa") is None and "previa" not in aba.dados


def test_ac7_abrir_alvo_real_troca_de_aba_e_vai_ao_id_ou_a_regra():
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        livro.recursos["Styles/estilo.css"] = m.Recurso(caminho="Styles/estilo.css", tipo_mime="text/css",
                                                        dados=b"p { a: b }\n.lance { c: d }\n")
        livro.capitulos[0].folhas = ["Styles/estilo.css"]
        j.executar("alternar_modo")
        editor = j.aba_ativa().widget
        indice = editor.texto.search('href="cap2.xhtml#alvo"', "1.0")
        assert indice
        editor.texto.mark_set("insert", f"{indice}+8c")
        j.executar("ir_ao_alvo")
        aba = j.aba_ativa()
        assert aba.arquivo == "cap2.xhtml" and aba.modo == "codigo"
        assert 'id="alvo"' in aba.widget.texto.get("insert linestart", "insert lineend")
        j.executar("voltar")
        assert j.aba_ativa().arquivo == "cap2.xhtml"          # o voltar é dentro da aba do código
        j.abrir_capitulo("cap1.xhtml", modo="codigo")
        editor = j.aba_ativa().widget
        indice = editor.texto.search('class="lance"', "1.0")
        assert indice
        editor.texto.mark_set("insert", f"{indice}+8c")
        j.executar("ir_ao_alvo")
        aba = j.aba_ativa()
        assert aba.arquivo == "Styles/estilo.css" and ".lance" in aba.widget.texto.get("insert linestart",
                                                                                     "insert lineend")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
