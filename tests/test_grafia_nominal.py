"""Nenhum teste confere a grafia do código (`inspect.getsource`): teste mede comportamento.

A RG-01b (R-39) congelou numa lista nominal os 19 testes que liam a fonte de uma função,
os do falso vermelho quando se edita com a suíte rodando (o `getsource` fatia o arquivo
novo pelas linhas do módulo velho). A PD-26 converteu os 19 — espião, `monkeypatch` ou,
nas regras sobre um arquivo inteiro, a leitura do arquivo do disco — e a lista zerou. Este
teste fica para ela não voltar a crescer."""

import ast
from pathlib import Path

TESTES = Path(__file__).resolve().parent


def _achados():
    achados = {}
    for caminho in sorted(TESTES.glob("*.py")):
        for funcao in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
            if not isinstance(funcao, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            chamadas = sum(1 for no in ast.walk(funcao) if isinstance(no, ast.Call)
                           and ast.unparse(no.func).split(".")[-1] in ("getsource", "getsourcelines"))
            if chamadas:
                achados[caminho.name, funcao.name] = chamadas
    return achados


def test_nenhum_teste_le_a_fonte_de_uma_funcao():
    assert _achados() == {}, ("teste que confere a grafia do código: troque por um espião ou "
                              "`monkeypatch` sobre o que a função faz")
