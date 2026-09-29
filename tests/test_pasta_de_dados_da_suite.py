"""
A suíte não grava na pasta de dados de quem a roda (`config.paths.data_dir()`).

Em 2026-09-22 o `settings.json` de verdade tinha seis `editor.recentes`, todos
`...\\pytest-of-...\\test_ac6_abrir_no_editor_apos_0\\saida.epub` ou `editado.epub`,
com `editor.diretorios` apontando para a mesma pasta de teste e
`editor.idioma_ortografia` trocado para `"und"`: o `test_ac6_…` do
`test_editor_ponte.py` abre a `JanelaDoEditor` sem `settings=`, e ela cai no
`Settings()` padrão. O conftest reaponta a pasta na importação
(`_reapontar_a_pasta_de_dados`); estes testes prendem o reapontamento no processo,
no fluxo do editor e num subprocesso.
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from config import paths
from conftest import AMBIENTE_ORIGINAL, PASTA_DE_DADOS_DA_SUITE, raiz_tk
from editor_ambiente import Caixas


def _dentro(caminho, pasta) -> bool:
    caminho, pasta = (os.path.normcase(os.path.realpath(c)) for c in (caminho, pasta))
    try:
        return os.path.commonpath([caminho, pasta]) == pasta
    except ValueError:      # unidades diferentes
        return False


@pytest.fixture
def pasta_de_verdade(monkeypatch):
    """A `data_dir()` de quem roda a suíte: a mesma conta, sobre o ambiente de antes do conftest."""
    with monkeypatch.context() as m:
        for nome, valor in AMBIENTE_ORIGINAL.items():
            if valor is None:
                m.delenv(nome, raising=False)
            else:
                m.setenv(nome, valor)
        return paths.data_dir()


def test_a_pasta_de_dados_da_suite_e_temporaria(pasta_de_verdade):
    from core.editor.projeto import pasta_de_rascunhos

    assert paths.data_dir() != pasta_de_verdade
    for caminho in (paths.data_dir(), paths.settings_path(), paths.crash_log_path(), pasta_de_rascunhos()):
        assert _dentro(caminho, PASTA_DE_DADOS_DA_SUITE), caminho


def test_abrir_um_livro_no_editor_grava_na_pasta_da_suite_e_nao_na_de_verdade(tmp_path, pasta_de_verdade):
    """
    O caminho do `test_ac6_…`, reduzido: a janela sem `settings=` abre um EPUB e grava
    `editor.recentes` e `editor.diretorios`.

    Do `settings.json` de verdade só se exige que não tenha recebido **este** livro, e não
    que continue byte a byte igual: quem roda a suíte pode estar usando o programa ao
    mesmo tempo (é o caso que o conftest registra para a base de ocupação), e uma
    gravação legítima dele não é defeito da suíte.
    """
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    from core.editor import epub
    from ui.editor.janela import JanelaDoEditor

    livro = str(tmp_path / "livro.epub")
    epub.escrever(editor_livros.livro_de_teste(), livro)
    da_suite = paths.settings_path()
    # sem o reapontamento, o fluxo abaixo seria o próprio defeito: o teste pára antes de gravar
    assert _dentro(da_suite, PASTA_DE_DADOS_DA_SUITE), da_suite
    antes = da_suite.read_bytes() if da_suite.is_file() else None
    try:
        janela = JanelaDoEditor(raiz)
        janela.withdraw()
        caixas = Caixas(janela)
        janela.executar("abrir", livro)
        assert not caixas.falhas()
        assert _dentro(janela.settings.path, PASTA_DE_DADOS_DA_SUITE)
        gravado = json.loads(da_suite.read_text(encoding="utf-8"))["editor"]
        assert gravado["recentes"][0] == os.path.abspath(livro)
        assert gravado["diretorios"]["abrir"] == os.path.dirname(os.path.abspath(livro))
        caixas.pergunta_resposta = False
        janela.fechar()
    finally:
        raiz.destroy()
        # os recentes deste teste não passam para os seguintes
        if antes is None:
            da_suite.unlink(missing_ok=True)
        else:
            da_suite.write_bytes(antes)
    de_verdade = pasta_de_verdade / "settings.json"
    texto = de_verdade.read_text(encoding="utf-8", errors="replace") if de_verdade.is_file() else ""
    assert json.dumps(str(tmp_path), ensure_ascii=False)[1:-1] not in texto


def test_um_subprocesso_herda_a_pasta_da_suite():
    """
    O reapontamento é pelo ambiente, e por isso vale para quem os testes sobem num
    subprocesso — o `appy.py --editor`, cujo `crash_log.txt` e cujos `rascunhos/` saem
    de `data_dir()`; o `PYBOXEDITOR_SETTINGS` que esses testes passam só cobre o
    `settings.json`.
    """
    saida = subprocess.run(
        [sys.executable, "-c", "from config.paths import data_dir; print(data_dir())"],
        cwd=str(paths.projeto_dir()), env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        capture_output=True, encoding="utf-8", timeout=120, check=True)
    assert _dentro(saida.stdout.strip(), PASTA_DE_DADOS_DA_SUITE), saida.stdout
