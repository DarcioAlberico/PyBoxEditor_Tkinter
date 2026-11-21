"""As dependências que leem arquivo de terceiro têm teto, e o piso é o que a CI testa (RG-02a, R-08).

O PyMuPDF 2.x deixou a CI vermelha em 2026-11-06 (`insert_image` passou a manter a
proporção, `295f9c6`): sem teto, uma versão maior nova chega na máquina do usuário e muda
o que um PDF ou uma imagem de livro vira, sem aviso. O teto é o da maior versão que já foi
medida aqui: PyMuPDF < 3 (o 2.x passou na CI depois do conserto), Pillow < 13, python-docx
< 2 — e admite as versões que o AbbyChessCraft usa (PyMuPDF 1.26.6, Pillow 12.0.0,
python-docx 1.2.0). O `constraints.txt` fixa as versões das dependências declaradas para a
CI; o piso 3.11 é o que a matriz da CI roda (o 3.10 era declarado e nunca testado).
"""

import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

RAIZ = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))


def _requisitos():
    linhas = (RAIZ / "requirements.txt").read_text(encoding="utf-8").splitlines()
    reqs = [Requirement(linha.split("#")[0].strip()) for linha in linhas
            if linha.split("#")[0].strip()]
    for extra in PYPROJECT["project"]["optional-dependencies"].values():
        reqs += [Requirement(r) for r in extra]
    return reqs


def _nome(req):
    return re.sub(r"[-_.]+", "-", req.name).lower()


def test_quem_le_arquivo_de_terceiro_tem_teto():
    tetos = {"pymupdf": Version("3"), "pillow": Version("13"), "python-docx": Version("2")}
    vistos = set()
    for req in _requisitos():
        if _nome(req) in tetos:
            vistos.add(_nome(req))
            assert not req.specifier.contains(tetos[_nome(req)]), f"{req} sem teto"
            assert not req.specifier.contains(Version("99")), f"{req} sem teto"
    assert vistos == set(tetos)


def test_o_teto_admite_as_versoes_do_abbychesscraft():
    usadas = {"pymupdf": "1.26.6", "pillow": "12.0.0", "python-docx": "1.2.0"}
    for req in _requisitos():
        if _nome(req) in usadas:
            assert req.specifier.contains(usadas[_nome(req)]), f"{req} recusa {usadas[_nome(req)]}"


def test_o_piso_e_o_que_a_ci_testa():
    assert PYPROJECT["project"]["requires-python"] == ">=3.11,<3.14"
    assert PYPROJECT["tool"]["ruff"]["target-version"] == "py311"
    ci = (RAIZ / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'python-version: ["3.11", "3.12", "3.13"]' in ci


def test_as_restricoes_fixam_cada_dependencia_declarada_e_respeitam_os_tetos():
    restricoes = {}
    for linha in (RAIZ / "constraints.txt").read_text(encoding="utf-8").splitlines():
        linha = linha.split("#")[0].strip()
        if linha:
            req = Requirement(linha)
            assert str(req.specifier).startswith("=="), linha
            restricoes[_nome(req)] = Version(str(req.specifier)[2:])
    for req in _requisitos():
        assert _nome(req) in restricoes or _nome(req) in {"paddlepaddle", "paddleocr", "tkinterweb",
                                                           "pyinstaller"}, f"{req} sem versão fixada"
        if _nome(req) in restricoes:
            assert req.specifier.contains(restricoes[_nome(req)]), f"{req} recusa a fixada"


def test_o_script_de_calibracao_nao_desserializa_codigo():
    fonte = (RAIZ / "scripts" / "medidas" / "calibrar_modelo.py").read_text(encoding="utf-8")
    for chamada in re.findall(r"torch\.load\([^)]*\)", fonte):
        assert "weights_only=True" in chamada, chamada
