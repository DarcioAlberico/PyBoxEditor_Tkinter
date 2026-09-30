"""
F124 — o Tesseract ganha prazo, e o livro desiste do executável que não volta.

A F119 deixou registrado que o Tesseract era chamado sem prazo: nenhuma página
travou nele, mas um executável que não volta prende a exportação do mesmo jeito
que o reparo de colagem prendia — e sem nada que o denuncie. Agora cada chamada
tem prazo (`PRAZO_DA_PAGINA_S`, `PRAZO_DA_FAIXA_S`, `PRAZO_DO_CARACTERE_S`), o
processo que passa dele sobe como `TesseractSemResposta`, a página segue com a
cadeia própria e registra, e `livro.extrair` desliga o motor para o resto do
livro depois de `PAGINAS_SEM_RESPOSTA_ATE_DESISTIR` páginas seguidas sem resposta.

Rodar sem pytest:      python tests/test_f124_prazo_do_tesseract.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz
import numpy as np
import pytest
from PIL import Image

from core import livro
from core.services import ocr_service
from core.services.ocr_service import (MotorIndisponivel, OCRService,
                                       TesseractSemResposta)

pytesseract = pytest.importorskip("pytesseract")


def _vazio():
    return {k: [] for k in ("level", "page_num", "block_num", "par_num",
                            "line_num", "word_num", "left", "top", "width",
                            "height", "conf", "text")}


def _estourou(*a, **k):
    # O que o pytesseract levanta depois de matar o processo (timeout_manager).
    raise RuntimeError("Tesseract process timeout")


# ----------------------------------------------------------------------
# O serviço: cada chamada tem prazo, e o estouro tem nome
# ----------------------------------------------------------------------

def test_cada_chamada_pede_o_prazo_do_seu_tamanho(monkeypatch):
    prazos = []

    def image_to_data(*a, timeout=None, **k):
        prazos.append(timeout)
        return _vazio()

    monkeypatch.setattr(pytesseract, "image_to_data", image_to_data)
    servico = OCRService()
    branco = np.full((40, 120), 255, np.uint8)
    servico._linhas_do_tesseract(branco, "en", 3)
    servico._linhas_do_tesseract(branco, "en", 7)
    servico.tesseract_ocr_conf(Image.fromarray(branco))
    assert prazos == [ocr_service.PRAZO_DA_PAGINA_S, ocr_service.PRAZO_DA_FAIXA_S,
                      ocr_service.PRAZO_DO_CARACTERE_S]
    assert (ocr_service.PRAZO_DO_CARACTERE_S < ocr_service.PRAZO_DA_FAIXA_S
            < ocr_service.PRAZO_DA_PAGINA_S)


@pytest.mark.parametrize("psm, prazo", [(3, ocr_service.PRAZO_DA_PAGINA_S),
                                        (7, ocr_service.PRAZO_DA_FAIXA_S)])
def test_o_processo_que_passou_do_prazo_sobe_com_nome_e_prazo(monkeypatch, psm, prazo):
    monkeypatch.setattr(pytesseract, "image_to_data", _estourou)
    with pytest.raises(TesseractSemResposta) as erro:
        OCRService()._linhas_do_tesseract(np.full((40, 120), 255, np.uint8), "en", psm)
    assert erro.value.prazo == prazo
    assert f"não respondeu em {prazo} s" in str(erro.value)
    assert not isinstance(erro.value, MotorIndisponivel), \
        "o executável existe: é a imagem que ele não fechou"


def test_o_caractere_isolado_tambem_tem_prazo(monkeypatch):
    monkeypatch.setattr(pytesseract, "image_to_data", _estourou)
    with pytest.raises(TesseractSemResposta):
        OCRService().tesseract_ocr_conf(Image.new("L", (20, 20), 255))


def test_outro_runtime_error_nao_vira_prazo(monkeypatch):
    def outro(*a, **k):
        raise RuntimeError("defeito de verdade")

    monkeypatch.setattr(pytesseract, "image_to_data", outro)
    with pytest.raises(RuntimeError) as erro:
        OCRService()._linhas_do_tesseract(np.full((40, 120), 255, np.uint8), "en", 3)
    assert type(erro.value) is RuntimeError


# ----------------------------------------------------------------------
# A página segue, e o livro desiste
# ----------------------------------------------------------------------

def _documento(paginas=1, linhas=("Uma linha de prosa comum.", "E outra linha, igual.")):
    doc = fitz.open()
    for _ in range(paginas):
        p = doc.new_page(width=300, height=200)
        for i, linha in enumerate(linhas):
            p.insert_text((30, 40 + i * 16), linha, fontsize=10)
    return doc


def _classificador(recorte):
    return ("a", 0.99)


def test_a_pagina_sem_resposta_sai_com_a_cadeia_e_registra():
    doc = _documento()
    try:
        def ler_pagina(img):
            raise TesseractSemResposta(ocr_service.PRAZO_DA_PAGINA_S)

        p = livro.extrair_pagina(doc[0], _classificador, dpi=150,
                                 ler_pagina=ler_pagina)
    finally:
        doc.close()
    assert p.caracteres > 0, "a página tem de sair, só com a cadeia própria"
    assert "página: o Tesseract não respondeu em 180 s" in p.motor_indisponivel


def _livro(tmp_path, paginas):
    caminho = tmp_path / "livro.pdf"
    doc = _documento(paginas)
    doc.save(str(caminho))
    doc.close()
    return str(caminho)


def test_duas_paginas_seguidas_sem_resposta_desligam_o_motor_para_o_livro(tmp_path):
    """
    O executável que não volta: sem o disjuntor, cada página pagaria o prazo da
    página e o de três faixas até o fim do livro. Com ele, a terceira página
    nem chama o motor — e diz por quê.
    """
    chamadas = {"pagina": 0, "faixa": 0}

    def ler_pagina(img):
        chamadas["pagina"] += 1
        raise TesseractSemResposta(ocr_service.PRAZO_DA_PAGINA_S)

    def ler_faixa(faixa):
        chamadas["faixa"] += 1
        return []

    paginas = livro.extrair(_livro(tmp_path, 4), _classificador, dpi=150,
                            ler_pagina=ler_pagina, ler_faixa=ler_faixa)
    assert chamadas["pagina"] == livro.PAGINAS_SEM_RESPOSTA_ATE_DESISTIR == 2
    faixas_antes = chamadas["faixa"]
    assert faixas_antes > 0, "nas duas primeiras a faixa ainda foi pedida"
    assert all(p.caracteres > 0 for p in paginas)
    assert "desligado para o resto do livro" not in paginas[0].motor_indisponivel
    for p in paginas[2:]:
        assert "Tesseract indisponível" in p.motor_indisponivel
        assert "em 2 páginas seguidas; desligado para o resto do livro" in p.motor_indisponivel


def test_a_pagina_que_responde_zera_a_conta(tmp_path):
    """A página que o Tesseract não fecha é uma página; o livro não desiste
    dele enquanto as outras respondem."""
    chamadas = []

    def ler_pagina(img):
        chamadas.append(1)
        if len(chamadas) % 2:
            raise TesseractSemResposta(ocr_service.PRAZO_DA_PAGINA_S)
        return []

    paginas = livro.extrair(_livro(tmp_path, 4), _classificador, dpi=150,
                            ler_pagina=ler_pagina)
    assert len(chamadas) == 4
    assert not any("desligado" in p.motor_indisponivel for p in paginas)


def test_a_indisponibilidade_nao_conta_como_falta_de_resposta(tmp_path):
    """O executável ausente já tem o seu caminho (`MotorIndisponivel`): cada
    página registra, e o disjuntor não o transforma em outra coisa."""
    def ler_pagina(img):
        raise MotorIndisponivel("Tesseract", "o executável não foi encontrado")

    paginas = livro.extrair(_livro(tmp_path, 3), _classificador, dpi=150,
                            ler_pagina=ler_pagina)
    assert all("o executável não foi encontrado" in p.motor_indisponivel
               for p in paginas)
    assert not any("desligado" in p.motor_indisponivel for p in paginas)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
