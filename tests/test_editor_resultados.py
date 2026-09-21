"""
Testes de `ui/editor/resultados.py` e `ui/editor/mensagens.py` (ED-02; SPEC_EDITOR
§7.1, §7.5, §13.4): a lista clicável genérica devolve o `Resultado` inteiro ao
callback, e o painel Mensagens ecoa o logger `pyboxeditor.editor` (INFO), também
de fora da thread da interface.

Rodar sem pytest:      python tests/test_editor_resultados.py
"""

import logging
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from conftest import raiz_tk
from ui.editor.mensagens import NOME_DO_LOGGER, PainelDeMensagens
from ui.editor.resultados import PainelDeResultados, Resultado


def test_o_painel_lista_ativa_e_devolve_o_resultado_inteiro_ao_callback():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        ativados = []
        painel = PainelDeResultados(raiz, ao_ativar=ativados.append, titulo="Busca")
        painel.pack()
        itens = [Resultado("Text/a.xhtml", "bloco 3", "achado", {"bloco": "b-1"}),
                 Resultado("Styles/x.css", "linha 40, col 3", "regra vazia", {"linha": 40, "coluna": 3}),
                 Resultado("Text/b.xhtml", "", "sem onde")]
        painel.definir(itens, "3 resultados")
        assert len(painel) == 3 and painel.rotulo.cget("text") == "3 resultados"
        assert painel.arvore.item("1", "values")[1] == "linha 40, col 3"
        assert painel.ativar(1) is itens[1] and ativados == [itens[1]]
        assert ativados[0].dados == {"linha": 40, "coluna": 3}
        painel.selecionar(2)
        assert painel.selecionado() is itens[2]
        assert painel.ativar() is itens[2] and ativados[-1] is itens[2]
        assert str(itens[0]) == "Text/a.xhtml (bloco 3): achado" and str(itens[2]) == "Text/b.xhtml: sem onde"
        painel.acrescentar(Resultado("c", "", "mais um"))
        assert len(painel) == 4
        painel.limpar()
        assert len(painel) == 0 and painel.selecionado() is None and painel.ativar() is None
        painel.foco()
        assert int(painel.arvore.cget("height")) >= 1
    finally:
        raiz.destroy()


def test_o_painel_de_mensagens_ecoa_o_logger_inclusive_de_outra_thread():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    log = logging.getLogger(NOME_DO_LOGGER)
    try:
        painel = PainelDeMensagens(raiz)
        painel.pack()
        painel.instalar(log)
        log.info("Aberto: %s", "livro.epub")
        log.warning("um aviso")
        log.debug("não aparece")
        assert painel.contem("Aberto: livro.epub") and painel.contem("um aviso")
        assert not painel.contem("não aparece")
        assert painel.linhas[0][0] == "INFO" and painel.linhas[1][0] == "WARNING"
        assert painel.texto.cget("state") == "disabled"
        # de outra thread, chega pelo `after`
        t = threading.Thread(target=lambda: log.info("de outra thread"))
        t.start()
        t.join()
        assert not painel.contem("de outra thread")             # ainda na fila
        limite = time.time() + 5
        while time.time() < limite and not painel.contem("de outra thread"):
            raiz.update()                                        # o `after` de 200 ms esvazia a fila
            time.sleep(0.02)
        assert painel.contem("de outra thread")
        painel.limpar()
        assert painel.linhas == [] and painel.texto.get("1.0", "end-1c") == ""
        painel.desinstalar(log)
        log.info("depois de desinstalar")
        assert not painel.contem("depois de desinstalar")
    finally:
        painel.desinstalar(log)
        raiz.destroy()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
