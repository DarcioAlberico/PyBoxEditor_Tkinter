"""
Uma raiz Tk para a suíte inteira, em vez de uma por teste.

**Por que isto existe.** Cada `tk.Tk()` faz o Tcl reler os arquivos de tema do
ttk do disco. Com 136 raízes por execução são milhares de aberturas de arquivo,
e no Windows uma delas de vez em quando falha — o erro que aparece é
`TclError: ... ttk::LoadThemes ... This probably means that tk wasn't installed
properly`, num teste diferente a cada vez. Medido antes desta mudança: 2 de 3
execuções da suíte tinham pelo menos uma falha assim, sempre espúria.

Não era vazamento: a contagem fechava em 136 criadas e 136 destruídas. Era o
volume de criações.

**Como usar.** `raiz_tk()` devolve um `Toplevel` da raiz compartilhada, que
serve de `parent` para a `MainWindow` — ela usa `protocol`, `config(menu=...)`,
`bind` e `focus_get`, e um `Toplevel` atende a todos. Destruir esse `Toplevel`
no fim do teste é o equivalente ao antigo `root.destroy()`.

O isolamento entre testes continua o mesmo em tudo que importa: cada um tem sua
janela, seus widgets e seus bindings. O que passa a ser compartilhado é o
interpretador Tcl, que nenhum teste modifica.
"""

import tkinter as tk

import pytest


_raiz = None


def _raiz_da_sessao():
    global _raiz
    if _raiz is None or not _raiz.winfo_exists():
        _raiz = tk.Tk()
        _raiz.withdraw()
    return _raiz


def raiz_tk():
    """
    Uma janela nova sobre a raiz compartilhada, pronta para servir de `parent`.

    Devolve `None` quando não há display — os testes de UI já sabem se pular
    nesse caso.
    """
    try:
        janela = tk.Toplevel(_raiz_da_sessao())
    except tk.TclError:
        return None
    janela.withdraw()
    return janela


@pytest.fixture(scope="session", autouse=True)
def _fecha_a_raiz_no_fim():
    yield
    global _raiz
    if _raiz is not None:
        try:
            _raiz.destroy()
        except tk.TclError:
            pass
        _raiz = None
