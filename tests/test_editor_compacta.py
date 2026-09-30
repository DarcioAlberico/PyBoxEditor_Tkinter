"""
Testes da ED-16 (a janela compacta): a barra de arquivo e a do modo dividem uma fileira
quando cabem e empilham numa janela estreita; o caderno de baixo nasce recolhido (também,
uma vez, sobre um layout gravado antes da ED-16) e abre sozinho no `Ctrl+F`, nos resultados
e na validação; os símbolos de vantagem dos botões ficam maiores.

Rodar sem pytest:      python tests/test_editor_compacta.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from config.settings import Settings
from editor_ambiente import Janela


def _mestre(barra):
    return str(barra.pack_info().get("in")) if barra.winfo_manager() == "pack" else ""


def test_a_fileira_junta_as_barras_quando_cabem_e_empilha_quando_nao():
    with Janela() as t:
        j = t.j
        # A largura vai como argumento: no Windows, uma janela escondida só aceita o primeiro `geometry`.
        j._empilhar_barras(1360)
        assert j._lado_a_lado is True
        assert _mestre(j.barra_de_arquivo) == str(j.fileira) == _mestre(j.barra_de_formatacao)
        # no código, a barra de código divide a fileira
        j.executar("alternar_modo")
        j._empilhar_barras(1360)
        assert _mestre(j.barra_de_codigo) == str(j.fileira) and not j.barra_de_formatacao.winfo_manager()
        j.executar("alternar_modo")
        # estreita: a do modo desce para a sua própria fileira
        j._empilhar_barras(640)
        assert j._lado_a_lado is False and _mestre(j.barra_de_formatacao) == str(j.barras)
        # com o painel Xadrez à vista, a barra de xadrez não repete a paleta (ED-16b); fechado, ela
        # volta, abaixo das duas
        assert not j.barra_de_xadrez.winfo_manager()
        j.mostrar_painel("xadrez", False)
        ordem = [str(w) for w in j.barras.pack_slaves()]
        assert ordem.index(str(j.fileira)) < ordem.index(str(j.barra_de_xadrez))
        j.mostrar_painel("xadrez", True)
        assert not j.barra_de_xadrez.winfo_manager()
        # sem a barra do modo, só a de arquivo na fileira
        j.mostrar_barra("formatacao", False)
        j._empilhar_barras(1360)
        assert not j.barra_de_formatacao.winfo_manager() and _mestre(j.barra_de_arquivo) == str(j.fileira)


def test_o_caderno_de_baixo_nasce_recolhido_e_abre_quando_precisa():
    with Janela() as t:
        j = t.j
        assert not j.paineis["busca"].visivel and str(j.inferior) not in j.centro.panes()
        j.executar("localizar")                                           # Ctrl+F
        assert j.paineis["busca"].visivel and j.inferior.select() == str(j.busca)
        j.mostrar_painel("busca", False)
        # resultados com itens abrem o caderno na aba deles; vazios, não
        from ui.editor.resultados import Resultado

        j.resultados.definir([], "nada")
        assert not j.paineis["busca"].visivel
        j.resultados.definir([Resultado("cap1.xhtml", "1", "achado")], "um")
        assert j.paineis["busca"].visivel and j.inferior.select() == str(j.resultados)
        j.mostrar_painel("busca", False)
        # o XHTML mal-formado abre a Validação
        j.executar("alternar_modo")
        j.aba_ativa().widget.texto.insert("end", "<p>aberto")
        j.executar("alternar_modo")
        assert j.paineis["busca"].visivel and j.inferior.select() == str(j.validacao)


def test_layout_antigo_recolhe_uma_vez_e_depois_vale_a_escolha():
    pasta = tempfile.mkdtemp(prefix="pbe-compacta-")
    caminho = os.path.join(pasta, "settings.json")
    settings = Settings(caminho)
    antigo = {"geometria": "", "paineis": {"busca": True, "resultados": True, "mensagens": True,
                                           "validacao": True, "navegador": True},
              "barras": {"formatacao": True, "xadrez": True}}
    settings.set("editor", {"layout": antigo})
    settings.save()
    from ui.editor.janela import VERSAO_DO_LAYOUT, JanelaDoEditor
    from conftest import raiz_tk

    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        j = JanelaDoEditor(raiz, settings=Settings(caminho))
        j.withdraw()
        assert not j.paineis["busca"].visivel                             # o layout de antes: recolhe
        j.mostrar_painel("busca", True)                                    # o usuário quer aberto
        assert j.layout()["versao"] == VERSAO_DO_LAYOUT
        j.caixas.pergunta = lambda *a, **k: False
        j.fechar()
        j = JanelaDoEditor(raiz, settings=Settings(caminho))
        j.withdraw()
        assert j.paineis["busca"].visivel                                  # e fica aberto
        j.caixas.pergunta = lambda *a, **k: False
        j.fechar()
    finally:
        raiz.destroy()


def test_simbolos_de_vantagem_maiores():
    from ui.editor.paleta import SIMBOLOS_MIUDOS, fonte_do_simbolo

    assert {"±", "∓", "⩲", "⩱"} == set(SIMBOLOS_MIUDOS)
    assert fonte_do_simbolo("⩲", 10) == ("Segoe UI Symbol", 13) and fonte_do_simbolo("!", 10)[1] == 10
    with Janela() as t:
        botao = t.j.barra_de_xadrez.simbolos.get("⩲")
        assert botao is not None and "13" in str(botao.cget("font"))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
