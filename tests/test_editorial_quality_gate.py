from __future__ import annotations

import json

from core.editorial_model import (
    Decision,
    EditorialBlock,
    EditorialDocument,
    EditorialPage,
    Evidence,
    SourceRef,
)
from core.editorial_quality_gate import validar_documento
from scripts.validar_documento_editorial import main


FEN = "8/1k6/1p6/1K6/P1P5/8/8/8 w - - 0 1"


def _documento(*, fen: str = FEN, ordem: tuple[int, ...] = (0, 1),
               sequencia: str = "1. e4 e5 2. Nf3 Nc6") -> EditorialDocument:
    pages = []
    for page_index, block_orders in enumerate((ordem, (0,))):
        source = SourceRef("book", page_index, (0, 0, 100, 100),
                           f"hash-{page_index}", "raster")
        evidence = Evidence(f"ev-{page_index}", source, confidence=0.99)
        blocks = []
        for block_order in block_orders:
            if page_index == 0 and block_order == 0:
                kind, value = "chess_sequence", sequencia
            else:
                kind, value = "diagram", {"fen": fen}
            blocks.append(EditorialBlock(
                f"block-{page_index}-{block_order}", kind, block_order,
                [source], Decision(value, [evidence.id], "automatic")))
        pages.append(EditorialPage(
            f"book-p{page_index:04d}", page_index, [source], blocks, [evidence]))
    return EditorialDocument("book", "Livro", "pt", pages,
                             pipeline_version="test", source_sha256="source")


def test_gate_valida_ordem_fen_tabela_e_sequencia():
    resultado = validar_documento(_documento())

    assert resultado.valid is True
    assert resultado.errors == ()
    assert resultado.metrics["pages"] == 2
    assert resultado.metrics["diagrams"] == 2
    assert resultado.metrics["sequences"] == 1


def test_gate_rejeita_fen_invalido_e_ordem_de_bloco():
    resultado = validar_documento(_documento(fen="fen invalido", ordem=(1, 0)))

    assert resultado.valid is False
    assert any("FEN" in erro for erro in resultado.errors)
    assert any("ordem" in erro for erro in resultado.errors)


def test_gate_cli_grava_relatorio_e_retorna_falha(tmp_path):
    caminho = tmp_path / "documento.json"
    saida = tmp_path / "gate.json"
    caminho.write_text(json.dumps(_documento(fen="fen invalido").to_dict()),
                       encoding="utf-8")

    assert main([str(caminho), "-o", str(saida)]) == 1
    relatorio = json.loads(saida.read_text(encoding="utf-8"))
    assert relatorio["valid"] is False
    assert relatorio["schema"] == "pyboxeditor.editorial-quality/v1"


def test_gate_pode_exigir_decisoes_resolvidas():
    documento = _documento()
    documento.pages[0].blocks[0].decision.status = "unresolved"

    resultado = validar_documento(documento, exigir_resolvido=True)

    assert resultado.valid is False
    assert any("unresolved" in erro for erro in resultado.errors)


def test_gate_exigir_resolvido_recusa_bloco_marcado_para_revisao():
    documento = _documento()
    documento.pages[0].blocks[0].metadata["review_required"] = True
    documento.pages[0].blocks[0].warnings.append("engine indisponível")

    resultado = validar_documento(documento, exigir_resolvido=True)

    assert resultado.valid is False
    assert resultado.metrics["review_required"] == 1
    assert any("revisão" in erro for erro in resultado.errors)


def test_gate_nao_confunde_warning_informativo_com_pendencia():
    documento = _documento()
    documento.pages[0].blocks[0].warnings.append("lado a jogar assumido")

    resultado = validar_documento(documento, exigir_resolvido=True)

    assert resultado.valid is True
    assert resultado.metrics["review_required"] == 0
