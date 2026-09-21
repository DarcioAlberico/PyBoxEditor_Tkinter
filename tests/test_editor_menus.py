"""
Testes de `ui/editor/menus.py` (ED-02; SPEC_EDITOR §7.3): todo item da §7.3 existe
com `underline` fora das letras de peça, os mnemônicos dos menus são os da spec, o
comando repetido é `alias_de`, o item desabilitado escreve a fase na barra de status
ao `<<MenuSelect>>` (AC-ED02-2) e — pela janela — cada acorde da §7.4 tem item de
menu que chega ao comando trocado por um espião (AC-ED02-1).

Rodar sem pytest:      python tests/test_editor_menus.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from conftest import raiz_tk
from config.settings import Settings
from ui.editor import atalhos, menus
from ui.editor.janela import JanelaDoEditor


class _Janela:
    def __enter__(self):
        self.raiz = raiz_tk()
        if self.raiz is None:
            pytest.skip("sem display")
        self.pasta = tempfile.mkdtemp(prefix="pbe-menus-")
        self.j = JanelaDoEditor(self.raiz, settings=Settings(os.path.join(self.pasta, "s.json")))
        self.j.withdraw()
        return self

    def __exit__(self, *a):
        try:
            self.j.caixas.pergunta = lambda *a, **k: False
            self.j.fechar()
            self.raiz.destroy()
        except Exception:
            pass


def test_a_tabela_da_secao_7_3_passa_na_verificacao_e_os_mnemonicos_sao_os_da_spec():
    assert menus.verificar() == []
    assert menus.MNEMONICOS_DOS_MENUS == {"Arquivo": "A", "Editar": "E", "Exibir": "x", "Inserir": "I",
                                          "Formatar": "F", "Xadrez": "z", "Ferramentas": "m", "Livro": "L",
                                          "Ajuda": "u"}
    for letra in menus.MNEMONICOS_DOS_MENUS.values():
        assert letra not in menus.LETRAS_PROIBIDAS
    rotulos = {rotulo for rotulo, _itens in menus.MENUS}
    assert rotulos == {"Arquivo", "Editar", "Exibir", "Inserir", "Formatar", "Xadrez", "Ferramentas", "Livro", "Ajuda"}
    # os itens que a §7.3 nomeia, por amostra, com a fase
    por_comando = {i.comando: i for i in menus.todos_os_itens() if i.comando and not i.alias_de}
    assert por_comando["novo_de_modelo"].fase == "ED-02"
    assert por_comando["localizar"].fase == "ED-06" and por_comando["previa"].fase == "ED-08"
    assert por_comando["imprimir"].fase == "ED-12" and por_comando["preferencias"].fase == "ED-13"
    assert por_comando["marcas_e_setas"].fase == "ED-05b" and por_comando["tipografia"].fase == "ED-06b"
    # repetidos são alias_de
    lares = {}
    for item in menus.todos_os_itens():
        if not item.comando:
            continue
        if item.comando in lares:
            assert item.alias_de or lares[item.comando].alias_de, item.rotulo
        lares.setdefault(item.comando, item)
    aliases = {i.rotulo for i in menus.todos_os_itens() if i.alias_de}
    assert {"Diagrama…", "Capítulo novo", "Propriedades do diagrama…"} <= aliases


def test_todo_item_tem_underline_fora_das_letras_de_peca_e_o_acelerador_da_tabela():
    with _Janela() as t:
        m = t.j.menus
        assert m.barra.index("end") == 8
        for i in range(9):
            rotulo = m.barra.entrycget(i, "label")
            sub = int(m.barra.entrycget(i, "underline"))
            assert rotulo[sub].lower() == menus.MNEMONICOS_DOS_MENUS[rotulo].lower()
        vistos = 0
        for (menu, indice), nome in m.mapa.items():
            tipo = menu.type(indice)
            if tipo == "separator":
                continue
            rotulo = menu.entrycget(indice, "label")
            sub = int(menu.entrycget(indice, "underline"))
            assert sub >= 0, rotulo
            assert rotulo[sub] not in menus.LETRAS_PROIBIDAS, rotulo
            if tipo in ("command", "checkbutton") and nome in [i.comando for i in menus.todos_os_itens()]:
                assert menu.entrycget(indice, "accelerator") == menus.acelerador_no_modo(nome, "texto"), rotulo
            vistos += 1
        assert vistos >= len(menus.todos_os_itens())


def test_ac_ed02_1_todo_acorde_chega_ao_comando_pelo_item_de_menu_trocado_por_espiao():
    with _Janela() as t:
        j = t.j
        for a in atalhos.TABELA:
            if a.tipo != "comando":
                continue
            for modo in a.modos:
                chamados = []
                j.comandos[a.comando] = lambda c=a.comando: chamados.append(c)
                j.modos_do_comando.pop(a.comando, None)
                j.modo_atual = lambda m=modo: m
                j.menus.atualizar(modo)
                assert j.menus.estado(a.comando) == "normal", (a.atalho, modo)
                j.menus.invocar(a.comando)
                assert chamados == [a.comando], (a.atalho, modo)


def test_ac_ed02_2_item_desabilitado_escreve_a_fase_na_barra_de_status_ao_percorrer():
    with _Janela() as t:
        j = t.j
        m = j.menus
        assert m.estado("localizar") == "disabled" and m.estado("novo") == "normal"
        menu, indice, item = m.itens["localizar"][0]
        # o Tk não ativa entrada desabilitada: a que está sob o mouse vem do `y` do evento
        m._ao_percorrer(type("E", (), {"widget": menu, "y": menu.yposition(indice) + 1})())
        assert "ED-06" in j.campos["aviso"].cget("text")
        # um item de outro modo diz o modo; um comando registrado só para um modo diz a fase do outro
        menu, indice, item = m.itens["fonte"][0]
        assert item.modos == ("texto",)
        assert m.motivo(item, "codigo") == "Fonte…: só no modo texto"
        menu, indice, item = m.itens["inserir_link"][0]
        assert m.motivo(item, "texto") == "Link…: no modo texto chega na ED-04"
        assert m.estado("inserir_link") == "disabled"
        j.modo_atual = lambda: "codigo"
        m.atualizar("codigo")
        assert m.estado("inserir_link") == "normal" and m.estado("fonte") == "disabled"
        # o item habilitado ecoa o rótulo e o atalho
        menu, indice, item = m.itens["salvar"][0]
        menu.activate(indice)
        m._ao_percorrer(type("E", (), {"widget": menu})())
        assert j.campos["aviso"].cget("text") == "Salvar  (Ctrl+S)"


def test_o_menu_de_contexto_vem_da_tabela_e_os_submenus_dinamicos_se_preenchem():
    with _Janela() as t:
        j = t.j
        contexto = j.menus.contexto("texto")
        rotulos = [contexto.entrycget(i, "label") for i in range(contexto.index("end") + 1)
                   if contexto.type(i) == "command"]
        assert rotulos[:3] == ["Desfazer", "Refazer", "Recortar"] and "Propriedades do objeto…" in rotulos
        contexto = j.menus.contexto("codigo")
        rotulos = [contexto.entrycget(i, "label") for i in range(contexto.index("end") + 1)
                   if contexto.type(i) == "command"]
        assert "Comentar/descomentar" in rotulos and "Ir ao alvo do link" in rotulos
        assert j.menu_de_contexto() is not None                 # janela escondida: monta e não posta
        # recentes e clipes: os postcommand
        menu_recentes = j.menus.itens["Abrir recente"][0][0].nametowidget(
            j.menus.itens["Abrir recente"][0][0].entrycget(j.menus.itens["Abrir recente"][0][1], "menu"))
        j.menus._preencher_dinamico(menu_recentes, "recentes")
        assert menu_recentes.entrycget(0, "label") == "(vazio)"
        menu_clipes = j.menus.itens["Clipe"][0][0].nametowidget(
            j.menus.itens["Clipe"][0][0].entrycget(j.menus.itens["Clipe"][0][1], "menu"))
        j.menus._preencher_dinamico(menu_clipes, "clipes")
        assert menu_clipes.index("end") + 1 == len(j.clipes) > 0
        with pytest.raises(KeyError):
            j.menus.invocar("comando_inexistente")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
