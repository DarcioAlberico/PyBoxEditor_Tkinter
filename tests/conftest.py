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

Mora aqui também a guarda da **base de ocupação de verdade** — ver
`_a_suite_nao_escreve_na_base_de_ocupacao`. É guarda de sessão inteira, e por
isso não cabe num arquivo de teste.
"""

import os
import sys
import tkinter as tk

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import diagrama, treino_diagrama


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


# ----------------------------------------------------------------------
# A base de ocupação de verdade não é rascunho de teste
# ----------------------------------------------------------------------

def amostras_da_ocupacao():
    """
    `{classe: {nomes de arquivo}}` da base de ocupação de verdade.

    Nomes, e não contagem: um teste que gravasse uma amostra e apagasse outra
    fecharia a conta e passaria batido. Conteúdo não entra — regravar o mesmo
    nome com outra imagem exige a mesma procedência e a mesma casa, que é o que
    `treino_diagrama._nome_de_arquivo` garante ser difícil de fazer sem querer.
    """
    saida = {}
    for simbolo in (diagrama.VAZIA, diagrama.OCUPADA):
        pasta = treino_diagrama._pasta_da_classe(
            treino_diagrama.PASTA_OCUPACAO, simbolo)
        if os.path.isdir(pasta):
            saida[simbolo] = {n for n in os.listdir(pasta)
                              if n.endswith(".png")}
    return saida


#: Como a base estava quando a sessão começou — lido na importação do conftest,
#: que o pytest faz antes de coletar o primeiro teste.
_OCUPACAO_NO_INICIO = amostras_da_ocupacao()


def mexeu_na_ocupacao():
    """`(gravados, apagados)` na base de verdade desde o início da sessão."""
    agora = amostras_da_ocupacao()
    gravados, apagados = [], []
    for simbolo in sorted(set(agora) | set(_OCUPACAO_NO_INICIO)):
        antes = _OCUPACAO_NO_INICIO.get(simbolo, set())
        depois = agora.get(simbolo, set())
        gravados += [f"{simbolo}/{n}" for n in sorted(depois - antes)]
        apagados += [f"{simbolo}/{n}" for n in sorted(antes - depois)]
    return gravados, apagados


@pytest.fixture(scope="session", autouse=True)
def _a_suite_nao_escreve_na_base_de_ocupacao():
    """
    A base tem de terminar a sessão como começou.

    **Não é zelo: aconteceu.** Um teste de diálogo que esquecia de apontar
    `PASTA_OCUPACAO` para uma pasta temporária gravava 64 casas sintéticas na
    base de verdade a cada execução — e nada acusava, porque amostra a mais não
    quebra treino nenhum, só envenena o modelo devagar. É o defeito da F1.4 na
    forma que a F7.5 podia criá-lo.

    **A guarda é de sessão, e não um teste, por causa da ordem.** O pytest roda
    os arquivos em ordem alfabética, e quem mais mexe na base —
    `test_f83_treino_diagrama.py` — vem depois do `test_f75_ocupacao.py`. Um
    teste no meio da fila só cobriria a parte da suíte que já passou.

    O que ela **não** trava é o tamanho da base: ele cresce de propósito, a cada
    diagrama que o usuário confere (F8.3). Era o que a versão anterior fazia, e
    reprovava por trabalho bem feito.
    """
    yield
    gravados, apagados = mexeu_na_ocupacao()
    assert not (gravados or apagados), (
        "a suíte mexeu na base de ocupação de verdade — algum teste esqueceu de "
        "apontar PASTA_OCUPACAO para uma pasta temporária.\n"
        f"  gravados: {gravados}\n  apagados: {apagados}")
