"""Os documentos citam arquivos que existem (RG-19, R-44)."""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
CITADO = re.compile(r"`((?:core|ui|config)/[\w/]+\.py)`")


@pytest.mark.parametrize("documento", ["CLAUDE.md", "README.md", "docs/ARCHITECTURE.md"])
def test_todo_caminho_citado_existe(documento):
    citados = set(CITADO.findall((RAIZ / documento).read_text(encoding="utf-8")))
    assert citados, f"{documento} não cita nenhum módulo: a expressão deixou de casar?"
    assert not sorted(c for c in citados if not (RAIZ / c).is_file())


def test_o_docstring_da_fachada_aponta_a_biblioteca():
    from core import editorial_pipeline

    for caminho in re.findall(r"`(core/[\w/]+\.py)`", editorial_pipeline.__doc__):
        assert (RAIZ / caminho).is_file(), caminho


@pytest.mark.parametrize("nome", ["TaskService", "DocumentService", "HistoryService"])
def test_os_nomes_de_classe_sao_os_reais(nome):
    for documento in ("CLAUDE.md", "README.md", "docs/ARCHITECTURE.md"):
        assert nome not in (RAIZ / documento).read_text(encoding="utf-8"), documento
