"""
Testes das operações de livro na janela (ED-08; SPEC_EDITOR §9.5, §9 tabela): adicionar
arquivo e cópia, nova folha, novo capítulo, excluir com "quem apontava" em Resultados,
vincular folhas grava `Capitulo.folhas`, folhas do livro, ordenar por nome (AC-ED08-1);
"Abrir com…" exporta, lança e traz o arquivo de volta quando muda; um clipe no modo
texto vira o modelo do fragmento e `ui/fontes.registrar_arquivo` põe a fonte do EPUB em
`tkfont.families()` (AC-ED08-9); e o AC-ED02-7 repetido (os módulos pesados ficam fora).

Rodar sem pytest:      python tests/test_editor_livro_ops_ui.py
"""

import os
import subprocess
import sys
import time
from tkinter import font as tkfont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import livro_ops, modelo as m
from core.editor.clipes import Clipe
from editor_ambiente import Janela

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_ac1_adicionar_arquivo_copia_nova_folha_novo_capitulo_e_excluir(tmp_path):
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        # adicionar: uma imagem, um CSS e um XHTML
        png = tmp_path / "nova.png"
        png.write_bytes(editor_livros._png_40x30())
        assert j.executar("adicionar_arquivo", str(png)) == "Images/nova.png"
        css = tmp_path / "extra.css"
        css.write_text("p { color: red }", encoding="utf-8")
        href_css = j.executar("adicionar_arquivo", str(css))
        assert href_css.endswith("extra.css") and livro.recursos[href_css].texto_cru == "p { color: red }"
        xhtml = tmp_path / "solto.xhtml"
        xhtml.write_text('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>s</title></head><body><p>s</p>'
                         "</body></html>", encoding="utf-8")
        href_x = j.executar("adicionar_arquivo", str(xhtml))
        assert livro.capitulo(href_x) is not None and livro.capitulos[-1].arquivo == href_x
        assert j.navegador.exists(href_x) and j.painel_navegador.selecionado() == href_x and j.projeto.sujo
        j.executar("adicionar_arquivo", str(tmp_path / "nada.txt"))
        assert "não existe" in t.caixas.entradas()[-1]
        # cópia do capítulo ativo (o navegador está no XHTML solto)
        copia = j.executar("adicionar_copia")
        assert copia != href_x and livro.capitulo(copia) is not None
        # nova folha: a primeira vira a padrão, com a CSS do dialeto; a segunda, vazia
        livro.folhas = []
        folha = j.executar("nova_folha", "tema")
        assert folha.endswith("tema.css") and livro.folhas == [folha] and "figure.diagrama" in livro.recursos[
            folha].texto_cru
        assert j.aba_ativa().arquivo == folha and j.painel_de_estilos.folha_padrao == livro.recursos[folha].texto_cru
        outra = j.executar("nova_folha", "outra.css")
        assert livro.recursos[outra].texto_cru == "" and livro.folhas == [folha, outra]
        # novo capítulo depois do alvo, com as folhas do vizinho
        j.painel_navegador.selecionar("cap1.xhtml")
        novo = j.executar("novo_capitulo", "Extra")
        assert livro.capitulos[1].arquivo == novo and livro.capitulo(novo).titulo_efetivo == "Extra"
        assert j.aba_ativa().arquivo == novo and j.aba_ativa().modo == "texto"
        # excluir: quem apontava vai a Resultados; o nav não se exclui; a aba fecha
        t.caixas.pergunta_resposta = True
        j.abrir_capitulo("cap2.xhtml")
        j.painel_navegador.selecionar("cap2.xhtml")
        apontavam = j.executar("excluir")
        assert livro.capitulo("cap2.xhtml") is None and j.abas.por_arquivo("cap2.xhtml") is None
        assert any(a.startswith("cap1.xhtml#") for a in apontavam) and "sumário" in " ".join(apontavam)
        assert len(j.resultados) == len(apontavam) and j.resultados.itens[0].mensagem.endswith("cap2.xhtml")
        j.executar("excluir", livro.nav)
        assert "regenerado" in t.caixas.entradas()[-1]
        t.caixas.pergunta_resposta = False
        assert j.executar("excluir", "Images/nova.png") == [] and "Images/nova.png" in livro.recursos


def test_ac1_vincular_folhas_grava_capitulo_folhas_e_folhas_do_livro_escolhe_a_padrao():
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        j.executar("vincular_folhas")
        assert "não tem folha" in t.caixas.entradas()[-1]
        a = livro_ops.nova_folha(livro, "Styles/a.css", "p { a: 1 }", padrao=True)
        b = livro_ops.nova_folha(livro, "Styles/b.css", "p { b: 2 }")
        j.atualizar_navegador()
        # pela caixa: marca só a `b` para o cap1 (o alvo do navegador)
        j.painel_navegador.selecionar("cap1.xhtml")
        j.caixas.marcar_varios = lambda titulo, rotulo, opcoes, marcadas=(), ok="OK": [opcoes.index(b)]
        assert j.executar("vincular_folhas") == 1 and livro.capitulo("cap1.xhtml").folhas == [b]
        # por argumento: as duas em todos
        assert j.executar("vincular_folhas", [a, b], "todos") == 2
        assert all(c.folhas == [a, b] for c in livro.capitulos) and j.projeto.sujo
        # a aba de texto do cap1 foi recarregada com as folhas novas
        assert j.abas.por_arquivo("cap1.xhtml").widget.estilos is not None
        # as folhas do livro: a primeira marcada é a padrão
        j.caixas.marcar_varios = lambda titulo, rotulo, opcoes, marcadas=(), ok="OK": [opcoes.index(b),
                                                                                        opcoes.index(a)]
        assert j.executar("folhas_de_estilo") == [b, a] and livro.folhas == [b, a]
        assert j.painel_de_estilos.folha_padrao == "p { b: 2 }"
        with pytest.raises(ValueError):
            j.operacoes.folhas_de_estilo(["nada.css"])


def test_abrir_com_exporta_lanca_e_traz_de_volta_o_que_mudou(tmp_path):
    with Janela() as t:
        j = t.j
        livro = j.projeto.livro
        lancados = []
        j.operacoes.lancador = lambda caminho, programa: lancados.append((caminho, programa))
        j.painel_navegador.selecionar("cap2.xhtml")
        caminho = j.executar("abrir_com", "meu-editor.exe")
        assert lancados == [(caminho, "meu-editor.exe")] and os.path.exists(caminho)
        assert caminho.endswith("cap2.xhtml") and t.settings.get("editor")["abrir_com"] == "meu-editor.exe"
        assert j.operacoes.verificar_vigiados() == []
        # o programa externo salva: o arquivo volta para o livro (em texto cru), a aba recarrega
        time.sleep(0.05)
        with open(caminho, "w", encoding="utf-8") as f:
            f.write('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>x</title></head><body>'
                    "<p>Editado fora.</p></body></html>")
        os.utime(caminho, None)
        assert j.operacoes.verificar_vigiados() == ["cap2.xhtml"]
        cap = livro.capitulo("cap2.xhtml")
        assert cap.texto_cru and "Editado fora." in cap.texto_cru and j.projeto.sujo
        aba = j.abrir_capitulo("cap2.xhtml")
        assert "Editado fora." in (aba.widget.texto_todo() if aba.modo == "codigo"
                                   else " ".join(m.texto_de(b) for b in aba.widget.sincronizar().blocos))
        # um recurso também
        caminho_css = j.executar("abrir_com", "", "Images/foto.png")
        assert lancados[-1] == (caminho_css, "") and os.path.getsize(caminho_css) > 0


def test_ac9_um_clipe_no_modo_texto_vira_o_modelo_e_a_fonte_do_epub_entra_no_tk(tmp_path):
    with Janela() as t:
        j = t.j
        texto = t.texto
        texto.ir_para(texto.ordem[1], 0)
        clipe = Clipe("Negrito", "<p><strong>\\0 forte</strong> e <em>suave</em></p>", "grupo")
        texto.selecionar(0, 8)                      # "Primeira"
        assert j.executar("aplicar_clipe", clipe).startswith("<p><strong>Primeira forte")
        blocos = texto.sincronizar().blocos
        assert m.texto_de(blocos[1]).startswith("Primeira forte e suave") and blocos[1].trechos[0].negrito
        assert blocos[1].trechos[2].italico
        # a barra de clipes também abre no texto
        assert j.executar("clipes") is not None and j.menus.estado("clipes") == "normal"
        # a fonte do EPUB (uma fonte de verdade como recurso) registrada no Tk pela família
        from ui import fontes

        caminho = os.path.join(RAIZ, "assets", "fonts", "SimbolosDeXadrez.ttf")
        if not os.path.exists(caminho):
            pytest.skip("fonte empacotada ausente")
        with open(caminho, "rb") as f:
            dados = f.read()
        j.projeto.livro.recursos["Fonts/x.ttf"] = m.Recurso(caminho="Fonts/x.ttf", tipo_mime="font/ttf", dados=dados)
        extraida = tmp_path / "x.ttf"
        extraida.write_bytes(dados)
        familia = fontes.registrar_arquivo(str(extraida))
        assert familia == "Simbolos de Xadrez" and familia in tkfont.families()
        assert fontes.registrar_arquivo(str(extraida)) == familia          # idempotente
        assert fontes.registrar_arquivo(os.path.join(RAIZ, "README.md")) is None


def test_ac7_repetido_o_subprocesso_do_editor_continua_sem_torch_easyocr_cv2_numpy_nem_fitz(tmp_path):
    caminho = os.path.join(str(tmp_path), "livro.epub")
    from core.editor import epub

    epub.escrever(editor_livros.livro_completo(), caminho)
    ambiente = dict(os.environ, PYBOXEDITOR_SETTINGS=os.path.join(str(tmp_path), "settings.json"))
    saida = subprocess.run([sys.executable, "appy.py", "--editor", caminho, "--fechar-apos", "1",
                            "--diagnostico-modulos"], capture_output=True, text=True, cwd=RAIZ, timeout=180,
                           env=ambiente)
    assert saida.returncode == 0, saida.stderr
    linha = next(li for li in saida.stdout.splitlines() if li.startswith("modulos pesados carregados:"))
    for pesado in ("torch", "easyocr", "cv2", "numpy", "fitz", "ui.main_window"):
        assert f"'{pesado}'" not in linha, linha


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
