"""O log de `core` (item 5 da análise de 2026-10-06): um tronco, um arquivo, nenhum `print`.

`core/log.py` dá a convenção; estes testes a pinam: o nome de cada logger desce de
`pyboxeditor` (e o do editor, de `pyboxeditor.editor`, para o painel Mensagens ecoar), o
arquivo da pasta de dados recebe o que `core` avisa, `uma_vez` avisa uma vez, e nenhum
módulo de `core` fala pelo `print` nem abre um logger fora do tronco — era assim que o
silêncio da F119 nascia.
"""
import ast
import logging
import re
from pathlib import Path

import pytest

from core import log as log_mod
from core.log import configurar, desconfigurar, esquecer, logger, uma_vez

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _memoria_limpa():
    esquecer()
    yield
    esquecer()


def test_todo_logger_desce_de_pyboxeditor_e_o_do_editor_do_painel():
    assert logger("core.exportar").name == "pyboxeditor.core.exportar"
    assert logger("core.services.pdf_service").name == "pyboxeditor.core.services.pdf_service"
    assert logger("core.editor.fontes").name == "pyboxeditor.editor.core.fontes"
    assert logger("ui.editor.janela").name == "pyboxeditor.editor.ui.janela"
    assert logger("pyboxeditor.editor").name == "pyboxeditor.editor"
    from ui.editor.mensagens import NOME_DO_LOGGER
    assert logger("core.editor.epub").name.startswith(NOME_DO_LOGGER + "."), \
        "o que o núcleo do editor avisa tem de subir até o logger que o painel Mensagens escuta"


def test_configurar_pendura_um_arquivo_so_e_o_aviso_chega_nele(tmp_path):
    caminho = tmp_path / "log" / "pyboxeditor.log"
    try:
        assert configurar(caminho) == caminho
        assert configurar(caminho) == caminho, "chamar de novo não duplica"
        raiz = logging.getLogger(log_mod.RAIZ)
        meus = [h for h in raiz.handlers if getattr(h, "pyboxeditor_arquivo", None) == caminho]
        assert len(meus) == 1
        logger("core.teste_do_log").warning("a fonte %s não embutiu", "SkakNew")
        logger("core.editor.teste_do_log").info("o editor também cai no arquivo")
        for h in meus:
            h.flush()
        texto = caminho.read_text(encoding="utf-8")
        assert "WARNING pyboxeditor.core.teste_do_log: a fonte SkakNew não embutiu" in texto
        assert "INFO    pyboxeditor.editor.core.teste_do_log: o editor também cai no arquivo" in texto
    finally:
        desconfigurar(caminho)
    assert not [h for h in logging.getLogger(log_mod.RAIZ).handlers
                if getattr(h, "pyboxeditor_arquivo", None) == caminho]


def test_uma_vez_avisa_uma_vez_por_chave(caplog):
    log = logger("core.teste_uma_vez")
    with caplog.at_level(logging.WARNING, logger=log.name):
        assert uma_vez(log, "wordfreq", logging.WARNING, "sem wordfreq, a correção está desligada")
        assert not uma_vez(log, "wordfreq", logging.WARNING, "sem wordfreq, a correção está desligada")
        assert uma_vez(log, "rapidfuzz", logging.WARNING, "outra chave, outro aviso")
    assert [r.getMessage() for r in caplog.records] == [
        "sem wordfreq, a correção está desligada", "outra chave, outro aviso"]


def test_o_diagrama_que_nao_se_desenha_deixa_rastro(caplog):
    """O exemplo da classe: `imagem_do_diagrama` devolvia `"", "nenhuma"` em silêncio."""
    from core.editorial_export import imagem_do_diagrama
    from core.editorial_model import Decision, EditorialBlock

    bloco = EditorialBlock(
        id="b1", kind="diagram", order=0, source_refs=[],
        decision=Decision(value={"fen": "isto não é um FEN"}, evidence_ids=[], status="reviewed"),
    )
    with caplog.at_level(logging.WARNING, logger="pyboxeditor.core.editorial_export"):
        imagem, origem = imagem_do_diagrama(bloco)
    assert (imagem, origem) == ("", "nenhuma")
    assert any("b1" in r.getMessage() for r in caplog.records), \
        "a exportação sem a imagem do diagrama tem de dizer qual bloco e por quê"


def _modulos_de_core():
    for caminho in sorted(RAIZ.glob("core/**/*.py")):
        if "__pycache__" in caminho.parts:
            continue
        yield caminho


def test_nenhum_modulo_de_core_fala_pelo_print():
    """O `print` de `core` ia para um console que o aplicativo não tem; agora é `log`."""
    achados = []
    for caminho in _modulos_de_core():
        arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))
        guardados: set[int] = set()
        for no in ast.walk(arvore):
            if (isinstance(no, ast.If) and isinstance(no.test, ast.Compare)
                    and isinstance(no.test.left, ast.Name) and no.test.left.id == "__name__"):
                guardados.update(range(no.lineno, no.end_lineno + 1))
        for no in ast.walk(arvore):
            if (isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "print"
                    and no.lineno not in guardados):
                achados.append(f"{caminho.relative_to(RAIZ).as_posix()}:{no.lineno}")
    assert not achados, "\n".join(achados)


def test_nenhum_modulo_de_core_abre_logger_fora_do_tronco():
    """`logging.getLogger(...)` direto só com um nome `pyboxeditor…`; o resto usa `core.log.logger`."""
    padrao = re.compile(r"logging\.getLogger\(([^)]*)\)")
    achados = []
    for caminho in _modulos_de_core():
        if caminho.name == "log.py":
            continue
        for numero, linha in enumerate(caminho.read_text(encoding="utf-8").split("\n"), 1):
            m = padrao.search(linha)
            if m and "pyboxeditor" not in m.group(1) and "RAIZ" not in m.group(1):
                achados.append(f"{caminho.relative_to(RAIZ).as_posix()}:{numero}: {linha.strip()}")
    assert not achados, "\n".join(achados)
