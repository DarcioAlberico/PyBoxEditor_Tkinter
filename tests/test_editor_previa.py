"""
Testes de `ui/editor/previa.py` e da prévia na janela (ED-08; SPEC_EDITOR DEC-05, §9.6):
`Previa(atraso_ms=0)` desenha o capítulo pelo `fitz.Story` (ED-14); um XHTML mal-formado
mantém a prévia anterior; `ir_ao_bloco(linha)` contorna o bloco; `abrir_alvo` real troca de
aba (AC-ED08-7); `F12` liga e desliga a prévia numa divisória ao lado do código, que segue o
cursor e devolve a linha ao clique.

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


def test_ac7_a_previa_desenha_mantem_a_anterior_no_mal_formado_e_vai_ao_bloco():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        raiz.geometry("600x500")
        cliques = []
        previa = Previa(raiz, atraso_ms=0, ao_clicar=cliques.append,
                        folhas=[("Styles/e.css", "h1 { font-size: 2em; } p { text-indent: 1em; }")])
        previa.pack(fill="both", expand=True)
        raiz.update()
        previa.atualizar(XHTML, "Text/c.xhtml")
        raiz.update()
        assert previa.pronta and previa.erro is None and previa.rodape.cget("text") == ""
        assert [linha for linha, _p, _r in previa.desenho.posicoes] == [7, 8, 9]
        # a fatia é da largura do painel (a raiz do teste fica escondida: vale o `width` pedido) e virou imagem
        if previa.canvas.winfo_ismapped():
            assert abs(previa.desenho.largura_pt * previa.px_por_pt() - previa.canvas.winfo_width()) < 3
        assert previa.canvas.find_withtag("fatia")
        anterior = previa.desenho
        # mal-formado: fica a anterior, com o erro no rodapé
        previa.atualizar(XHTML.replace("</p>\n</body>", "\n</body>"), "Text/c.xhtml")
        raiz.update()
        assert previa.erro is not None and "mal-formado" in previa.rodape.cget("text")
        assert previa.desenho is anterior
        # de volta ao bom, o rodapé limpa; `ir_ao_bloco` pela linha da fonte, com contorno
        previa.atualizar(XHTML, "Text/c.xhtml")
        raiz.update()
        assert previa.rodape.cget("text") == ""
        assert previa.ir_ao_bloco(8) == 8 and previa.canvas.find_withtag("bloco")
        assert previa.ir_ao_bloco(100) == 9 and previa.ir_ao_bloco(1) == 7
        # o clique devolve a linha da fonte do bloco clicado
        _linha, _pagina, (x0, y0, x1, y1) = previa.desenho.posicao_da_linha(9)
        escala = previa.px_por_pt()
        assert previa.linha_em((x0 + x1) / 2 * escala, (y0 + y1) / 2 * escala) == 9
        # com atraso, a última chamada é a que vale
        previa.atraso_ms = 50
        previa.atualizar(XHTML.replace("Primeiro", "Um"), "Text/c.xhtml")
        previa.atualizar(XHTML.replace("Primeiro", "Dois"), "Text/c.xhtml")
        raiz.after(200, raiz.quit)
        raiz.mainloop()
        assert "Dois" in previa._texto
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
        j.update()
        assert previa is not None and aba.dados["previa"] is previa and previa.pronta
        assert j.menus.estado("previa") == "normal"
        # código e prévia repartem a largura numa divisória (antes a prévia ficava com ~30 px)
        divisao = aba.dados["divisao"]
        editor = aba.widget
        assert divisao.winfo_manager() == "pack" and len(divisao.panes()) == 2
        if divisao.winfo_width() > 100:
            assert 0.3 < divisao.sash_coord(0)[0] / divisao.winfo_width() < 0.7
        # o cursor no código leva a prévia ao bloco; uma edição redesenha
        linha_do_titulo = int(editor.texto.search("<h1", "1.0").split(".")[0])
        editor.ir_para(linha_do_titulo)
        j.update()
        assert previa.linha_marcada == linha_do_titulo and previa.canvas.find_withtag("bloco")
        antes = len(previa.desenho.posicoes)
        editor.texto.insert(f"{linha_do_titulo}.0", "<p>Inserido pela prévia.</p>\n")
        j.update()
        assert len(previa.desenho.posicoes) == antes + 1
        # o clique na prévia leva o código à linha
        previa.ao_clicar(linha_do_titulo + 1)
        assert editor.posicao[0] == linha_do_titulo + 1
        assert j.executar("previa") is None and "previa" not in aba.dados and "divisao" not in aba.dados
        assert editor.winfo_manager() == "pack"
        # ligada de novo e trocando de modo, a prévia sai com a divisória
        j.executar("previa")
        j.executar("alternar_modo")
        assert j.aba_ativa().modo == "texto" and "previa" not in aba.dados and "divisao" not in aba.dados


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
