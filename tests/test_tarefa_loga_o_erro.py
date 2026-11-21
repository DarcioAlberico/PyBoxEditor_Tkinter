"""O erro de uma tarefa vai ao log com o traceback (RG-12, R-14).

O `runner` de `BackgroundTask` punha a exceção na fila, e a janela a mostrava numa caixa de
uma linha: o traceback nunca chegava ao `pyboxeditor.log`, e quem depura ficava sem saber
de onde ela veio. O conserto no `runner` cobre as ~25 tarefas da janela e as dos diálogos.
"""

import logging
import time

import pytest

from conftest import raiz_tk
from core.services.task_service import BackgroundTask


def _funcao_que_quebra(handle):
    raise ZeroDivisionError("divisão no meio da leitura")


def test_a_tarefa_que_levanta_deixa_o_traceback_no_log(caplog):
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    erros = []
    tarefa = BackgroundTask(raiz, poll_ms=5)
    try:
        with caplog.at_level(logging.ERROR):
            assert tarefa.start(_funcao_que_quebra, on_error=erros.append)
            limite = time.time() + 10
            while not erros and time.time() < limite:
                raiz.update()
                time.sleep(0.01)
        assert erros and isinstance(erros[0], ZeroDivisionError), "a janela deixou de receber o erro"
        registros = [r for r in caplog.records if r.levelno >= logging.ERROR and r.exc_info]
        assert registros, "o erro da tarefa não foi ao log com o traceback"
        assert "_funcao_que_quebra" in caplog.text, "o traceback não diz de onde o erro veio"
    finally:
        tarefa.shutdown()
        raiz.destroy()


def test_o_cancelamento_nao_vira_erro_no_log(caplog):
    from core.services.task_service import Cancelled

    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    cancelados = []

    def cancela(handle):
        raise Cancelled()

    tarefa = BackgroundTask(raiz, poll_ms=5)
    try:
        with caplog.at_level(logging.ERROR):
            tarefa.start(cancela, on_cancel=lambda *a: cancelados.append(1))
            limite = time.time() + 10
            while not cancelados and time.time() < limite:
                raiz.update()
                time.sleep(0.01)
        assert cancelados and not [r for r in caplog.records if r.levelno >= logging.ERROR]
    finally:
        tarefa.shutdown()
        raiz.destroy()
