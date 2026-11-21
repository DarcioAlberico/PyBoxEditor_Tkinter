"""Teste que não mede, pula: nenhum `test_*` sai por `return` antes de conferir algo.

Revisão geral 2, RG-01 (R-38 da `docs/SPEC_REVISAO_GERAL_2.md`). Um teste que, sem o
dado ou sem o display de que precisa, sai por `return` antes da primeira asserção aparece
como PASSED sem ter medido nada — na CI e numa exportação limpa do `HEAD`, onde os dados
fora do git não existem, isso é um verde falso. O certo é `pytest.skip` com o motivo, que
aparece no relatório como SKIPPED.

A regra, por AST, em toda função `test_*` de `tests/` (no módulo ou numa classe): um
`return` sem valor que vem antes da primeira asserção da função (`assert`, ou uma chamada
`pytest.raises`/`pytest.fail`/`pytest.skip` como marcador de que o teste já decidiu) e fora
de um `except` é recusado. Um `return` dentro de `except` é a saída deliberada de um teste
que já tentou (o de `test_f12_balanceamento.py`); um `return` depois de uma asserção é a
saída de sucesso (os de `test_f61_pgn.py`, `test_f71_diagrama.py`, `test_f83_treino_diagrama.py`,
que acham o item no menu e param).

A lista nominal `PERMITIDOS` (princípio 7 da spec) guarda o que a regra pegaria e que fica
de propósito, cada um com o motivo; começa vazia.
"""

from __future__ import annotations

import ast
from pathlib import Path

PASTA = Path(__file__).resolve().parent

#: `arquivo.py::teste` -> motivo. Vazia: nenhum `return` nu antes de asserção é aceito.
PERMITIDOS: dict[str, str] = {}

_DECIDE = {"raises", "fail", "skip", "xfail", "importorskip"}


def _linha_da_primeira_asserção(funcao: ast.AST) -> int | None:
    linhas = []
    for no in ast.walk(funcao):
        if isinstance(no, ast.Assert):
            linhas.append(no.lineno)
        elif (
            isinstance(no, ast.Call)
            and isinstance(no.func, ast.Attribute)
            and no.func.attr in _DECIDE
            and isinstance(no.func.value, ast.Name)
            and no.func.value.id == "pytest"
        ):
            linhas.append(no.lineno)
    return min(linhas) if linhas else None


def _returns_nus_fora_de_except(funcao: ast.AST):
    """Os `return` sem valor da função (não das funções aninhadas), fora de `except`."""

    def visitar(no, dentro_de_except):
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            if isinstance(filho, ast.Return) and filho.value is None and not dentro_de_except:
                yield filho
            yield from visitar(filho, dentro_de_except or isinstance(filho, ast.ExceptHandler))

    yield from visitar(funcao, False)


def _testes(arvore: ast.Module):
    for no in arvore.body:
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no.name.startswith("test_"):
            yield no
        elif isinstance(no, ast.ClassDef):
            for membro in no.body:
                if isinstance(membro, (ast.FunctionDef, ast.AsyncFunctionDef)) and membro.name.startswith(
                    "test_"
                ):
                    yield membro


def saidas_mudas() -> list[str]:
    """`arquivo.py:linha::teste` de cada `return` nu antes da primeira asserção."""
    achados = []
    for arquivo in sorted(PASTA.glob("test_*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for teste in _testes(arvore):
            primeira = _linha_da_primeira_asserção(teste)
            for ret in _returns_nus_fora_de_except(teste):
                if primeira is None or ret.lineno < primeira:
                    chave = f"{arquivo.name}::{teste.name}"
                    if chave not in PERMITIDOS:
                        achados.append(f"{arquivo.name}:{ret.lineno}::{teste.name}")
    return achados


def test_nenhum_teste_sai_por_return_antes_de_conferir():
    achados = saidas_mudas()
    assert not achados, (
        "teste que sai por `return` antes da primeira asserção passa sem medir; "
        "use pytest.skip com o motivo:\n" + "\n".join(achados)
    )


def test_a_regra_pega_o_return_mudo_e_deixa_os_legitimos():
    codigo = '''
def test_mudo():
    if falta():
        return
    assert 1

def test_skip():
    if falta():
        pytest.skip("sem dado")
    assert 1

def test_sucesso():
    for x in itens():
        if x:
            assert x
            return

def test_no_except():
    try:
        f()
    except ValueError:
        return
    assert 1

def test_aninhada():
    def ajuda():
        return
    assert ajuda() is None
'''
    arvore = ast.parse(codigo)
    pegos = []
    for teste in _testes(arvore):
        primeira = _linha_da_primeira_asserção(teste)
        for ret in _returns_nus_fora_de_except(teste):
            if primeira is None or ret.lineno < primeira:
                pegos.append(teste.name)
    assert pegos == ["test_mudo"]


def test_a_lista_de_permitidos_so_tem_testes_que_existem():
    nomes = set()
    for arquivo in PASTA.glob("test_*.py"):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        nomes |= {f"{arquivo.name}::{t.name}" for t in _testes(arvore)}
    assert set(PERMITIDOS) <= nomes, sorted(set(PERMITIDOS) - nomes)
