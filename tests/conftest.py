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
`_a_suite_nao_escreve_na_base_de_ocupacao` — e a do **cache do OCR**, que desde
2026-09-22 tem pasta padrão na área do usuário. As duas são de sessão inteira,
e por isso não cabem num arquivo de teste. A da **pasta de dados** —
`_reapontar_a_pasta_de_dados` — vale para a sessão inteira pelo mesmo motivo, e
roda antes de todas: na importação deste arquivo.
"""

import atexit
import os
import shutil
import sys
import tempfile
import time
import tkinter as tk

import pytest


# ----------------------------------------------------------------------
# A pasta de dados de quem roda a suíte não é rascunho de teste
# ----------------------------------------------------------------------

#: As variáveis de onde `config.paths.data_dir()` tira a pasta de dados: no
#: Windows `LOCALAPPDATA` e, sem ela, `APPDATA`; fora dele `XDG_DATA_HOME`.
VARIAVEIS_DA_PASTA_DE_DADOS = ("LOCALAPPDATA", "APPDATA", "XDG_DATA_HOME")

#: Como elas estavam antes da suíte — é por elas que se acha a pasta de verdade
#: (`test_pasta_de_dados_da_suite.py`).
AMBIENTE_ORIGINAL = {nome: os.environ.get(nome) for nome in VARIAVEIS_DA_PASTA_DE_DADOS}

#: A pasta que a suíte usa no lugar dela; some no fim do processo.
PASTA_DE_DADOS_DA_SUITE = os.path.realpath(tempfile.mkdtemp(prefix="pyboxeditor-dados-da-suite-"))


def _reapontar_a_pasta_de_dados():
    """
    O `settings.json`, o `crash_log.txt` e os `rascunhos/` da suíte ficam numa pasta
    temporária, e não na de quem a roda.

    **Não é zelo: aconteceu.** Em 2026-09-22 o `settings.json` de verdade tinha seis
    `editor.recentes`, todos `...\\pytest-of-...\\test_ac6_abrir_no_editor_apos_0\\
    saida.epub` ou `editado.epub`, com `editor.diretorios` na mesma pasta de teste e
    `editor.idioma_ortografia` trocado para `"und"` — a língua da ortografia do
    usuário virou a do livro sintético. O `test_ac6_…` do `test_editor_ponte.py`
    abre a `JanelaDoEditor` sem `settings=`, e ela cai no `Settings()` padrão, que é
    `config.paths.settings_path()`. Numa suíte rastreada, foi o único teste a gravar
    ali; o próximo que esquecer o `settings=` já nasce coberto.

    **Na importação, e não numa fixture de sessão** como a do cache do OCR: a
    fixture só roda antes do primeiro teste, depois da coleta — e a coleta importa
    todos os módulos de teste, e este arquivo importa `core` logo abaixo. Um módulo
    que calculasse a pasta ao ser importado guardaria a de verdade. Hoje nenhum
    calcula (`data_dir()` relê o ambiente a cada chamada, e o `Settings()` padrão só
    é aberto quando se pede); daqui em diante isso deixa de depender de nenhum
    calcular.

    **Pelo ambiente, e não trocando `data_dir`:** os testes que sobem o `appy.py
    --editor` num subprocesso herdam o ambiente, e o `crash_log.txt` e os
    `rascunhos/` deles caem na mesma pasta; o `PYBOXEDITOR_SETTINGS` que eles
    passam só cobre o `settings.json`. As três variáveis, e não só `LOCALAPPDATA`:
    `APPDATA` é o que `data_dir()` usa quando `LOCALAPPDATA` falta, e
    `XDG_DATA_HOME` é o de fora do Windows — e o de um teste que finja outra
    plataforma trocando `sys.platform`.

    Nada que a suíte precisa sai dessas variáveis: os pesos (`custom_model.pth`,
    `text_line_model.*`, `core/dados/*.pth`) vêm de `projeto_dir()` (e do cwd), o
    Tesseract do `PATH` ou de `C:\\Program Files`, e o Pillow procura fonte em
    `WINDIR` — e a suíte inteira passa com as três reapontadas.
    """
    for nome in VARIAVEIS_DA_PASTA_DE_DADOS:
        pasta = os.path.join(PASTA_DE_DADOS_DA_SUITE, nome)
        os.makedirs(pasta, exist_ok=True)
        os.environ[nome] = pasta
    atexit.register(shutil.rmtree, PASTA_DE_DADOS_DA_SUITE, ignore_errors=True)


_reapontar_a_pasta_de_dados()

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


def esperar_ate(janela, condicao, prazo=10.0, passo=0.01):
    """
    Bombeia o laço do Tk até `condicao()` valer ou `prazo` segundos passarem.

    É a espera por uma ação que roda em thread (`BackgroundTask`, o `_run_task`
    da janela): o resultado só chega ao widget quando o `after` drena a fila, e
    fora do `mainloop` é o `update()` que o faz andar. Contar voltas de
    `update()` não serve de prazo — a volta não cede a vez à thread, e na suíte
    inteira, com a máquina dividida, 200 voltas acabam antes de ela terminar:
    `test_f17_leitura_de_linha` caiu assim em 2026-10-10 e passou sozinho. Um
    teste que só falha acompanhado é pior que um que nunca passa.

    Devolve se a condição valeu dentro do prazo; a asserção fica com quem chama,
    que sabe dizer o que não chegou.
    """
    fim = time.monotonic() + prazo
    while True:
        janela.update()
        if condicao():
            return True
        if time.monotonic() >= fim:
            return False
        time.sleep(passo)


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
def _o_cache_do_ocr_fica_fora_do_appdata(tmp_path_factory):
    """
    O cache por página da fachada não escreve na pasta do usuário.

    Desde 2026-09-22 (item 7 da revisão de 2026-09-18) `use_cache=True` sem
    `cache_dir` guarda em `config.paths.cache_ocr_dir()`, que no Windows é
    `%LOCALAPPDATA%/PyBoxEditor/cache/ocr` — e o padrão de `ProcessOptions` é
    justamente esse. Sem esta guarda, rodar a suíte encheria a pasta de quem a
    roda e, pior, faria um teste servir resultado gravado por outro.

    É a mesma decisão da guarda da base de ocupação, aqui embaixo: pasta de
    verdade não é lugar de teste.
    """
    os.environ["PYBOXEDITOR_CACHE_DIR"] = str(
        tmp_path_factory.mktemp("cache-ocr-da-suite"))
    yield
    os.environ.pop("PYBOXEDITOR_CACHE_DIR", None)


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
    try:
        from core import calibracao_de_pagina
    except ModuleNotFoundError as erro:
        # O núcleo sem ML continua testável sem instalar Torch. Os testes que
        # precisam dele importam a dependência explicitamente e falham/ são
        # selecionados pelo ambiente completo de desenvolvimento.
        if erro.name != "torch":
            raise
        return

    monkeypatch.setattr(calibracao_de_pagina, "paginas_rotuladas",
                        lambda *a, **k: [])
