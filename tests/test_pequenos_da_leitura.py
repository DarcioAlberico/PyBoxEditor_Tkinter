"""Os pequenos da leitura (RG-16, R-25), um teste por item.

- `amostrar` cortava a amostra depois do passo: o livro de 41 a 79 páginas nunca tinha o fim.
- O Tesseract de um caractere descartava a leitura de confiança 0 e partia o acento decomposto.
- O cache dos nomes de glifo não via o PDF regravado no mesmo caminho.
- `render_diagrama.esquecer` deixava a largura da grade da fonte anterior.
- A página fora do livro levantava no meio da leitura, e a negativa lia do fim.
- A tabela da geometria ilegível virava "sem poda" calada, e o vazio ficava no cache.
"""

import json
import logging
import os
import unicodedata

import fitz
import pytest
from PIL import Image

from core import geometria_da_linha, livro, pdf_nativo, render_diagrama
from core import log as log_do_core
from core.services.ocr_service import OCRService
from tests.test_f110_camada import _livro_digital

pytesseract = pytest.importorskip("pytesseract")


def _pdf(caminho, paginas):
    with fitz.open() as doc:
        for n in range(paginas):
            doc.new_page(width=60, height=60).insert_text((5, 20), f"p{n}")
        doc.save(caminho)
    return str(caminho)


@pytest.mark.parametrize("total", [1, 39, 40, 41, 60, 79, 80, 81, 119, 400])
def test_a_amostra_vai_ate_o_fim_do_livro_e_cabe(tmp_path, monkeypatch, total):
    vistas = []
    monkeypatch.setattr(pdf_nativo, "avaliar_pagina", lambda page, *, numero, produtor: (
        vistas.append(numero), pdf_nativo.Veredito(numero, True, ""))[1])
    aceitas, amostradas = pdf_nativo.amostrar(_pdf(tmp_path / "l.pdf", total))
    assert aceitas == amostradas == len(vistas) <= 40
    # O fim entra: depois da última amostrada sobra menos que um passo.
    passo = vistas[1] - vistas[0] if len(vistas) > 1 else 1
    assert total - vistas[-1] <= passo


def _um_caractere(monkeypatch, textos, confs):
    monkeypatch.setattr(pytesseract, "image_to_data", lambda *a, **k: {"text": textos, "conf": confs})
    return OCRService().tesseract_ocr_conf(Image.new("L", (20, 20), 255))


def test_a_confianca_zero_e_leitura_e_o_menos_um_nao(monkeypatch):
    assert _um_caractere(monkeypatch, ["a"], [0]) == ("a", 0.0)
    assert _um_caractere(monkeypatch, ["a"], [-1]) == ("", 0.0)
    assert _um_caractere(monkeypatch, ["a", "b"], [0, 40]) == ("b", 0.4)
    assert _um_caractere(monkeypatch, ["a"], ["lixo"]) == ("", 0.0)


def test_o_caractere_decomposto_nao_se_parte(monkeypatch):
    decomposto = unicodedata.normalize("NFD", "é")
    assert len(decomposto) == 2
    assert _um_caractere(monkeypatch, [decomposto + "x"], [90]) == ("é", 0.9)
    assert _um_caractere(monkeypatch, ["ab"], [90]) == ("a", 0.9)


def test_o_pdf_regravado_no_mesmo_caminho_e_outro(tmp_path, monkeypatch):
    class Doc:
        name = str(tmp_path / "l.pdf")

        def __init__(self, ordem):
            self.ordem = ordem

        def __len__(self):
            return 3

        def extract_font(self, xref):
            return ("f", "ttf", "", self.ordem)

    import fontTools.ttLib
    monkeypatch.setattr(fontTools.ttLib, "TTFont", lambda dados, lazy: type(
        "F", (), {"getGlyphOrder": lambda self: dados.read().decode().split()})())
    monkeypatch.setattr(pdf_nativo, "_nomes_de_glifo", {})
    caminho = tmp_path / "l.pdf"
    caminho.write_bytes(b"um")
    os.utime(caminho, ns=(10**18, 10**18))
    assert pdf_nativo._nomes_da_fonte(Doc(b"a b"), 7) == ["a", "b"]
    assert pdf_nativo._nomes_da_fonte(Doc(b"c d"), 7) == ["a", "b"], "o cache não serviu"
    os.utime(caminho, ns=(2 * 10**18, 2 * 10**18))
    assert pdf_nativo._nomes_da_fonte(Doc(b"c d"), 7) == ["c", "d"]


def test_esquecer_solta_a_largura_da_grade():
    render_diagrama._LARGURA_DA_GRADE[("Fonte", "simples", "reto")] = 99.0
    render_diagrama.esquecer()
    assert not render_diagrama._LARGURA_DA_GRADE


@pytest.mark.parametrize("pedidas", [[0, 3], [-1], [0, 99]])
def test_a_pagina_fora_do_livro_levanta_antes_da_primeira(tmp_path, monkeypatch, pedidas):
    lidas = []
    monkeypatch.setattr(livro, "extrair_pagina", lambda *a, **k: lidas.append(1))
    caminho = _pdf(tmp_path / "l.pdf", 3)
    with pytest.raises(ValueError, match="fora do livro"):
        livro.extrair(caminho, lambda r, ref=None: ("a", 1.0), paginas=pedidas)
    with pytest.raises(ValueError, match="fora do livro"):
        pdf_nativo.extrair(caminho, pedidas)
    assert not lidas


def test_as_paginas_pedidas_ficam_na_ordem(tmp_path):
    assert pdf_nativo.paginas_pedidas(5, (4, 0, 2)) == [4, 0, 2]
    assert pdf_nativo.paginas_pedidas(3, None) == [0, 1, 2]
    [pagina] = pdf_nativo.extrair(_livro_digital(tmp_path / "d.pdf", paginas=3), [2]).paginas
    assert pagina.numero == 2


def test_a_tabela_ilegivel_fala_e_nao_fica_no_cache(tmp_path, caplog):
    caminho = tmp_path / "t.json"
    caminho.write_text("{ quebrado", encoding="utf-8")
    log_do_core.esquecer()
    with caplog.at_level(logging.WARNING):
        assert geometria_da_linha.carregar_tabela(str(caminho)) == {}
        assert geometria_da_linha.carregar_tabela(str(caminho)) == {}
    assert len([r for r in caplog.records if "geometria" in r.getMessage()]) == 1
    caminho.write_text(json.dumps({"classes": {"a": [1, 0.1, 0, 0.1, 9]}}), encoding="utf-8")
    assert "a" in geometria_da_linha.carregar_tabela(str(caminho))


def test_a_tabela_que_nao_existe_e_silencio(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        assert geometria_da_linha.carregar_tabela(str(tmp_path / "nao.json")) == {}
    assert not caplog.records
