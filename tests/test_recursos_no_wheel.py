"""O que se distribui leva o que o programa abre (RG-02a, R-41 da revisão geral 2).

O wheel construído do `HEAD` não levava as fontes de diagrama, as peças nem os perfis:
instalado, `render_diagrama.carregar` levantava `FonteIncompleta`, o tabuleiro ficava sem
as figuras e `perfis.carregar_todos()` devolvia `[]` — sem que a CI visse, porque ela
conferia três arquivos à mão. E as fontes e as peças eram achadas por `__file__`, que num
wheel aponta o `site-packages`, onde os `data-files` não estão.

Os perfis vão como package-data de `config`; as fontes do `fontes_de_diagrama.json`, as
licenças delas e as peças vão como `data-files` em `share/PyBoxEditor`, e
`config.paths.recurso()` as procura no projeto e depois lá. `RECURSOS_OBRIGATORIOS` é a
lista que o bundle e o wheel têm de levar, com a regra de como um caminho da árvore vira
o nome dentro do wheel.
"""

import importlib
import runpy
import shutil
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

from config import paths
from scripts import verificar_empacotamento as ve

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def instalado(tmp_path, monkeypatch):
    """O projeto sem os recursos (o `site-packages`) e um `share` com eles."""
    vazio = tmp_path / "site-packages"
    vazio.mkdir()
    prefixo = tmp_path / "prefixo"
    share = prefixo / "share" / "PyBoxEditor"
    share.mkdir(parents=True)
    monkeypatch.setattr(paths, "projeto_dir", lambda: vazio)
    monkeypatch.setattr(sys, "prefix", str(prefixo))
    return share


def test_o_recurso_vem_do_projeto_e_senao_do_share(instalado):
    (instalado / "fonts").mkdir()
    (instalado / "fonts" / "x.otf").write_bytes(b"fonte")
    assert paths.recurso("fonts/x.otf") == instalado / "fonts" / "x.otf"
    assert paths.recurso("fonts/nao_existe.otf") == paths.projeto_dir() / "fonts" / "nao_existe.otf"


def test_a_fonte_de_diagrama_abre_do_share(instalado):
    from core import render_diagrama as rd

    (instalado / "fonts").mkdir()
    for nome in ("SkakNew-Diagram.otf", "ChessMerida-Diagram.ttf"):
        shutil.copy(RAIZ / "fonts" / nome, instalado / "fonts" / nome)
    rd.esquecer()
    try:
        fonte = rd.carregar(rd.FONTE_PADRAO)
        assert Path(fonte.arquivo).parent == instalado / "fonts"
    finally:
        rd.esquecer()

    from core.editor import fontes
    assert Path(fontes.arquivo_da_fonte_de_diagrama("SkakNew-Diagram")).parent == instalado / "fonts"


def test_as_pecas_abrem_do_share(instalado):
    from ui import pecas

    shutil.copytree(RAIZ / "pieces", instalado / "pieces")
    try:
        importlib.reload(pecas)
        assert Path(pecas.PASTA) == instalado / "pieces"
        assert pecas.faltando() == []
    finally:
        sys.modules.pop("ui.pecas", None)
        importlib.import_module("ui.pecas")


def test_o_wheel_leva_fontes_licencas_e_pecas():
    setup = runpy.run_path(str(RAIZ / "setup.py"), run_name="sem_setup")
    destinos = dict(setup["arquivos_de_dados"](RAIZ))
    fontes = {Path(f).name for f in destinos["share/PyBoxEditor/fonts"]}
    assert {"SkakNew-Diagram.otf", "ChessMerida-Diagram.ttf", "SkakNew.pdf", "LEEME__D.TXT"} <= fontes
    pecas = {Path(f).name for f in destinos["share/PyBoxEditor/pieces"]}
    assert pecas == {f"{cor}{p}.png" for cor in "wb" for p in "KQRBNP"}


def test_os_perfis_vao_como_dado_do_pacote_config():
    pyproject = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    assert "profiles/*.json" in pyproject["tool"]["setuptools"]["package-data"]["config"]


def test_a_lista_obrigatoria_cobre_fontes_pecas_e_perfis():
    nomes = {str(c).replace("\\", "/") for c in ve.RECURSOS_OBRIGATORIOS}
    assert {"fonts/SkakNew-Diagram.otf", "fonts/ChessMerida-Diagram.ttf",
            "pieces/wK.png", "config/profiles/10_figurina_unica.json"} <= nomes


def test_a_regra_da_arvore_para_o_wheel():
    assert ve.nome_no_wheel("core/dados/x.json", "pyboxeditor-0.1.0") == "core/dados/x.json"
    assert ve.nome_no_wheel("config/profiles/a.json", "pyboxeditor-0.1.0") == "config/profiles/a.json"
    assert ve.nome_no_wheel("fonts/a.otf", "pyboxeditor-0.1.0") == \
        "pyboxeditor-0.1.0.data/data/share/PyBoxEditor/fonts/a.otf"
    assert ve.nome_no_wheel("pieces/wK.png", "pyboxeditor-0.1.0") == \
        "pyboxeditor-0.1.0.data/data/share/PyBoxEditor/pieces/wK.png"


def test_o_verificador_do_wheel_aponta_o_que_falta(tmp_path):
    wheel = tmp_path / "pyboxeditor-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as z:
        z.writestr("core/dados/fontes_de_diagrama.json", "{}")
    faltam = ve.verificar_wheel(wheel)
    assert "pyboxeditor-0.1.0.data/data/share/PyBoxEditor/fonts/SkakNew-Diagram.otf" in faltam
    assert "config/profiles/10_figurina_unica.json" in faltam
    assert "core/dados/fontes_de_diagrama.json" not in faltam


def test_o_spec_leva_os_perfis():
    spec = (RAIZ / "pyboxeditor.spec").read_text(encoding="utf-8")
    assert '_data("config/profiles")' in spec
