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

#: Onde mora a base de verdade, resolvido na importação do conftest — antes de
#: qualquer teste apontar `PASTA_OCUPACAO` para uma pasta temporária.
_BASE_DE_OCUPACAO = os.path.abspath(treino_diagrama.PASTA_OCUPACAO)

#: O que a suíte tentou gravar lá. Ver `gravacoes_indevidas`.
_INDEVIDAS = []


def gravacoes_indevidas():
    """As gravações que **esta sessão** tentou fazer na base de verdade."""
    return list(_INDEVIDAS)


@pytest.fixture(scope="session", autouse=True)
def _a_suite_nao_escreve_na_base_de_ocupacao():
    """
    Nenhum teste grava na base de ocupação de verdade — e se tentar, não grava.

    **Não é zelo: aconteceu.** Um teste de diálogo que esquecia de apontar
    `PASTA_OCUPACAO` para uma pasta temporária gravava 64 casas sintéticas na
    base de verdade a cada execução — e nada acusava, porque amostra a mais não
    quebra treino nenhum, só envenena o modelo devagar. É o defeito da F1.4 na
    forma que a F7.5 podia criá-lo.

    **Vigia o processo, não a pasta**, e a diferença não é sutil. A primeira
    versão desta guarda fotografava a base no início da sessão e comparava no
    fim; reprovou na primeira execução em que o usuário estava **usando o app
    enquanto os testes rodavam** — dois diagramas conferidos, 128 casas
    gravadas, e a guarda apontando para trabalho legítimo feito noutro
    processo. Comparar pasta não distingue quem escreveu.

    Aqui `treino_diagrama.gravar` é embrulhado durante a sessão: se o destino
    resolvido for a base de verdade, a gravação é **recusada** e anotada. Só
    passa por esse caminho quem esqueceu de redirecionar a pasta, então recusar
    não atrapalha teste correto nenhum — e protege o dado em vez de só relatar
    o estrago depois de feito.

    **A guarda é de sessão, e não um teste, por causa da ordem.** O pytest roda
    os arquivos em ordem alfabética, e quem mais mexe na base —
    `test_f83_treino_diagrama.py` — vem depois do `test_f75_ocupacao.py`. Um
    teste no meio da fila só cobriria a parte da suíte que já passou.

    O que ela **não** trava é o tamanho da base: ele cresce de propósito, a cada
    diagrama que o usuário confere (F8.3).
    """
    original = treino_diagrama.gravar

    def vigiado(residuo, simbolo, origem="", casa="", pasta=None):
        alvo = treino_diagrama.PASTA_PADRAO if pasta is None else pasta
        if os.path.abspath(alvo) == _BASE_DE_OCUPACAO:
            _INDEVIDAS.append(f"{simbolo!r} de origem={origem!r} casa={casa!r}")
            return None
        return original(residuo, simbolo, origem, casa, pasta)

    treino_diagrama.gravar = vigiado
    try:
        yield
    finally:
        treino_diagrama.gravar = original

    assert not _INDEVIDAS, (
        "a suíte tentou gravar na base de ocupação de verdade — algum teste "
        "esqueceu de apontar PASTA_OCUPACAO para uma pasta temporária "
        "(a gravação foi recusada, a base está intacta):\n  "
        + "\n  ".join(_INDEVIDAS))


@pytest.fixture(autouse=True)
def _sem_paginas_rotuladas(monkeypatch):
    """
    Nenhum teste enxerga as páginas rotuladas do diretório de trabalho.

    A F27 fez o treino calibrar sozinho no fim, e a calibração procura `.box`
    em `Box/` e `ilovepdf_pages-to-jpg/` — que existem na máquina de quem
    desenvolve e não num clone limpo. Sem esta trava, onze testes de treino
    passavam a colher logits das dez páginas reais: **103 s a mais na suíte**, e
    um resultado que dependia de arquivos fora do repositório.

    O caminho não é desligado, é esvaziado: `_calibrar` roda, não acha página e
    relata — que é exatamente o estado de quem nunca rotulou uma. Quem quiser o
    outro lado devolve `paginas_rotuladas` no próprio teste.
    """
    from core import calibracao_de_pagina

    monkeypatch.setattr(calibracao_de_pagina, "paginas_rotuladas",
                        lambda *a, **k: [])
