"""
Testes de `core/editor/validacao.py` e de "Validar EPUB" na janela (ED-08; SPEC_EDITOR §9
"Validate with epubcheck"): sem Java, uma mensagem (AC-ED08-8); com o `epubcheck` (o JSON
dele, canned ou de verdade — o de verdade é `slow`), os erros com arquivo e linha no
painel Validação, e a ativação leva à linha.

Rodar sem pytest:      python tests/test_editor_validacao.py
"""

import json
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import editor_livros
from core.editor import epub, validacao
from editor_ambiente import Janela

JSON_CANNED = {
    "checker": {"path": "x", "filename": "livro.epub", "checkerVersion": "5.3.0", "nFatal": 0, "nError": 1,
                "nWarning": 1, "nUsage": 0},
    "messages": [
        {"ID": "RSC-005", "severity": "ERROR", "message": "elemento body ainda não permitido",
         "suggestion": "", "locations": [{"path": "livro.epub/OEBPS/Text/cap2.xhtml", "line": 7, "column": 3}]},
        {"ID": "OPF-007", "severity": "WARNING", "message": "aviso do OPF", "suggestion": "",
         "locations": [{"path": "OEBPS/content.opf", "line": -1, "column": -1}]},
        {"ID": "ACC-013", "severity": "USAGE", "message": "uso", "suggestion": "", "locations": []},
    ],
}


def _epub(pasta, quebrado=False):
    livro = editor_livros.livro_completo()
    if quebrado:
        livro.capitulos[1].texto_cru = ('<html xmlns="http://www.w3.org/1999/xhtml"><body><p>sem head</p>'
                                        "</body></html>")
    caminho = os.path.join(pasta, "v.epub")
    epub.escrever(livro, caminho)
    return caminho, livro


def test_ac8_sem_java_a_mensagem_diz_o_que_falta_e_a_estrutura_e_conferida(tmp_path):
    caminho, _livro = _epub(str(tmp_path))
    r = validacao.validar(caminho, comando=[])
    assert r.sem_java and r.valido and r.mensagens == [] and "Java" in r.saida and "epubcheck" in r.resumo()
    # o JSON do epubcheck vira mensagens com href relativo ao OPF, linha e coluna; USAGE fica
    mensagens = validacao.mensagens_do_json(JSON_CANNED, "OEBPS/content.opf")
    assert [(m.codigo, m.gravidade, m.arquivo, m.linha, m.coluna) for m in mensagens] == [
        ("RSC-005", "ERROR", "Text/cap2.xhtml", 7, 3), ("OPF-007", "WARNING", "content.opf", 0, 0),
        ("ACC-013", "USAGE", "", 0, 0)]
    assert mensagens[0].onde == "linha 7, col 3" and mensagens[1].onde == ""
    assert str(mensagens[0]).startswith("ERROR(RSC-005) Text/cap2.xhtml linha 7, col 3:")


def test_com_o_epubcheck_simulado_os_erros_vem_com_arquivo_e_linha(tmp_path):
    caminho, _livro = _epub(str(tmp_path))

    def correr(comando, **kw):
        assert comando[-1] == caminho and "--json" in comando
        return SimpleNamespace(returncode=1, stdout=json.dumps(JSON_CANNED), stderr="")

    r = validacao.validar(caminho, "OEBPS/content.opf", comando=["epubcheck-de-mentira"], correr=correr)
    assert not r.sem_java and not r.valido and len(r.erros) == 1 and len(r.avisos) == 1 and r.versao == "5.3.0"
    assert r.resumo() == "epubcheck: 1 erro(s), 1 aviso(s)"
    # um epubcheck que não devolve JSON vira "não rodou"
    r2 = validacao.validar(caminho, comando=["x"], correr=lambda *a, **k: SimpleNamespace(returncode=2, stdout="",
                                                                                          stderr="Java not found"))
    assert r2.sem_java and "Java not found" in r2.saida


def test_na_janela_a_validacao_preenche_o_painel_e_ativar_vai_a_linha():
    with Janela() as t:
        j = t.j

        def correr(comando, **kw):
            dados = json.loads(json.dumps(JSON_CANNED))
            dados["messages"][0]["locations"][0]["path"] = "livro.epub/OEBPS/cap2.xhtml"
            dados["checker"]["filename"] = "validar.epub"
            dados["messages"][0]["locations"][0]["path"] = "validar.epub/OEBPS/cap2.xhtml"
            return SimpleNamespace(returncode=1, stdout=json.dumps(dados), stderr="")

        j.operacoes.comando_do_epubcheck = lambda: ["epubcheck-de-mentira"]
        j.operacoes.correr_epubcheck = correr
        resultado = j.executar("validar_epub")
        assert resultado is not None and not resultado.valido
        assert j.inferior.select() == str(j.validacao) and len(j.validacao) == 2
        item = j.validacao.itens[0]
        assert item.arquivo == "cap2.xhtml" and item.dados["linha"] == 7 and item.mensagem.startswith("✖ RSC-005")
        j.validacao.ativar(0)
        aba = j.aba_ativa()
        assert aba.arquivo == "cap2.xhtml" and aba.modo == "codigo" and aba.widget.posicao[0] == 7
        # sem Java: a mensagem entra no painel e no registro
        j.operacoes.comando_do_epubcheck = lambda: None
        resultado = j.executar("validar_epub")
        assert resultado.sem_java and any("Java" in r.mensagem for r in j.validacao.itens)
        assert j.mensagens.contem("Instale o Java")


@pytest.mark.slow
def test_com_java_de_verdade_o_epubcheck_acha_o_xhtml_sem_head(tmp_path):
    if validacao.comando_do_epubcheck() is None:
        pytest.skip("sem Java/epubcheck")
    caminho, livro = _epub(str(tmp_path), quebrado=True)
    r = validacao.validar(caminho, livro.opf)
    assert not r.sem_java and not r.valido
    erro = next(m for m in r.erros if m.arquivo == "cap2.xhtml")
    assert erro.linha >= 1 and erro.codigo.startswith("RSC")
    caminho_bom, livro_bom = _epub(str(tempfile.mkdtemp()))
    assert validacao.validar(caminho_bom, livro_bom.opf).valido


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
