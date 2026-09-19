"""O motor de OCR opcional que falta **não** é uma página sem texto.

Até 2026-09-18 o Tesseract ausente devolvia `[]` de dentro de
`OCRService._linhas_do_tesseract`, e a página saía só com a cadeia própria —
bit a bit igual a uma página em branco, sem aviso em lugar nenhum. Os testes
aqui fixam o contrato novo: o serviço levanta `MotorIndisponivel`, o
`livro.extrair_pagina` segue lendo mas registra a falha em
`PaginaExtraida.motor_indisponivel`, e o leitor de faixa é desligado na
primeira indisponibilidade (uma chamada de processo por linha, todas iguais).
"""

import sys

import fitz
import numpy as np
import pytest

from core import livro
from core.services.ocr_service import COMO_INSTALAR_TESSERACT, MotorIndisponivel, OCRService


def _pagina(linhas=("Uma linha de prosa comum.", "E outra linha, igual.")):
    doc = fitz.open()
    p = doc.new_page(width=300, height=200)
    for i, linha in enumerate(linhas):
        p.insert_text((30, 40 + i * 16), linha, fontsize=10)
    return doc


def _classificador(char="a", confianca=0.99):
    return lambda recorte: (char, confianca)


# ----------------------------------------------------------------------
# O serviço
# ----------------------------------------------------------------------

def test_executavel_ausente_sobe_como_motor_indisponivel(monkeypatch):
    pytesseract = pytest.importorskip("pytesseract")

    def sem_executavel(*a, **k):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "image_to_data", sem_executavel)
    servico = OCRService()
    with pytest.raises(MotorIndisponivel) as erro:
        servico._linhas_do_tesseract(np.full((20, 80), 255, dtype=np.uint8), "en", 7)
    assert erro.value.motor == "Tesseract"
    assert "não foi encontrado" in erro.value.motivo
    assert COMO_INSTALAR_TESSERACT in str(erro.value)


def test_idioma_nao_instalado_sobe_como_motor_indisponivel(monkeypatch):
    pytesseract = pytest.importorskip("pytesseract")

    def sem_idioma(*a, **k):
        raise pytesseract.TesseractError(1, "Error opening data file por.traineddata")

    monkeypatch.setattr(pytesseract, "image_to_data", sem_idioma)
    with pytest.raises(MotorIndisponivel) as erro:
        OCRService().tesseract_pagina_detalhada_conf(
            np.full((20, 80), 255, dtype=np.uint8), "pt")
    assert "por.traineddata" in erro.value.motivo


def test_outra_excecao_nao_e_traduzida_nem_engolida(monkeypatch):
    pytesseract = pytest.importorskip("pytesseract")

    def defeito(*a, **k):
        raise ZeroDivisionError("defeito de verdade")

    monkeypatch.setattr(pytesseract, "image_to_data", defeito)
    with pytest.raises(ZeroDivisionError):
        OCRService()._linhas_do_tesseract(np.full((20, 80), 255, dtype=np.uint8), "en", 3)


def test_sondagem_diz_o_motivo_sem_executavel(monkeypatch):
    pytesseract = pytest.importorskip("pytesseract")

    def sem_executavel(*a, **k):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "get_tesseract_version", sem_executavel)
    disponivel, motivo = OCRService().tesseract_disponivel("en")
    assert disponivel is False
    assert "não foi encontrado" in motivo


# ----------------------------------------------------------------------
# A página: segue, mas sabe
# ----------------------------------------------------------------------

def test_a_pagina_registra_o_motor_que_faltou_e_segue_lendo():
    doc = _pagina()
    try:
        def ler_pagina(img):
            raise MotorIndisponivel("Tesseract", "o executável não foi encontrado")

        p = livro.extrair_pagina(doc[0], _classificador(), dpi=150,
                                 ler_pagina=ler_pagina)
    finally:
        doc.close()
    assert p.caracteres > 0, "a página tem de sair, só com a cadeia própria"
    assert "página: Tesseract indisponível" in p.motor_indisponivel
    assert all(r["fonte"] == "glyph" for r in p.roteamento if r["texto"])


def test_sem_motor_pedido_a_pagina_nao_reclama_de_nada():
    doc = _pagina()
    try:
        p = livro.extrair_pagina(doc[0], _classificador(), dpi=150)
    finally:
        doc.close()
    assert p.motor_indisponivel == ""


def test_o_leitor_de_faixa_desliga_na_primeira_indisponibilidade():
    """Uma chamada de processo por linha, todas iguais: depois da primeira
    `MotorIndisponivel` a faixa não é mais pedida — e a página registra."""
    chamadas = []

    def ler_faixa(faixa):
        chamadas.append(1)
        raise MotorIndisponivel("Tesseract", "o executável não foi encontrado")

    doc = _pagina(("Uma linha de prosa comum.", "E outra linha, igual.",
                   "E a terceira, por via das dúvidas."))
    try:
        p = livro.extrair_pagina(doc[0], _classificador(), dpi=150,
                                 ler_pagina=lambda img: [], ler_faixa=ler_faixa)
    finally:
        doc.close()
    assert len(chamadas) == 1
    assert "faixa: o executável não foi encontrado" in p.motor_indisponivel


def test_a_falha_isolada_da_faixa_nao_desliga_o_leitor():
    """Um recorte que o motor não engoliu é uma falha; três seguidas são um
    defeito. A isolada fica registrada e a linha seguinte ainda paga o motor."""
    contagem = {"n": 0}

    def ler_faixa(faixa):
        contagem["n"] += 1
        if contagem["n"] == 1:
            raise ValueError("recorte estranho")
        return []

    doc = _pagina(("Uma linha de prosa comum.", "E outra linha, igual.",
                   "E a terceira, por via das dúvidas."))
    try:
        p = livro.extrair_pagina(doc[0], _classificador(), dpi=150,
                                 ler_pagina=lambda img: [], ler_faixa=ler_faixa)
    finally:
        doc.close()
    assert contagem["n"] >= 2, "a segunda linha ainda pediu a faixa"
    assert "faixa: ValueError: recorte estranho" in p.motor_indisponivel


def test_a_pagina_extraida_sabe_a_largura_e_o_dpi():
    """É o que converte `Paragrafo.topo`/`pe` em pontos do PDF fora daqui."""
    doc = _pagina()
    try:
        p = livro.extrair_pagina(doc[0], _classificador(), dpi=150)
    finally:
        doc.close()
    assert p.dpi == 150
    assert p.largura == round(300 * 150 / 72)
    assert p.altura == round(200 * 150 / 72)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
