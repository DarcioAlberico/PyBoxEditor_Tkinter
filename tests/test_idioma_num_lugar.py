"""O idioma num lugar só (RG-16b, R-23): `alfabeto.idioma_normalizado`, e os remendos da
prosa inglesa só no inglês."""

import os
import re

import pytest

from core import alfabeto, livro, pdf_nativo
from core.lexico import Lexico
from core.services.ocr_service import OCRService


@pytest.mark.parametrize("escrito, chave", [
    ("pt", "pt"), ("pt-BR", "pt"), ("pt_BR", "pt"), ("PT", "pt"), ("por", "pt"), (" pt ", "pt"),
    ("en", "en"), ("en-US", "en"), ("eng", "en"), ("es", "es"), ("", None), (None, None),
])
def test_a_chave_do_idioma(escrito, chave):
    assert alfabeto.idioma_normalizado(escrito) == chave


@pytest.mark.parametrize("escrito", ["pt", "pt-BR", "pt_BR", "por"])
def test_o_portugues_e_o_mesmo_em_toda_parte(escrito):
    assert alfabeto.permitido("ç", escrito) and not alfabeto.permitido("Š", escrito)
    assert OCRService._idioma_tesseract(escrito) == "por"
    assert livro._corrigir_prosa_contextual("TIBD; 2. TIC+, RIT; 3.", escrito, fuzzy=False) \
        == "T1BD; 2. T1C+, R1T; 3."


@pytest.mark.parametrize("escrito", ["en", "en-US", "eng"])
def test_o_ingles_tambem(escrito):
    assert not alfabeto.permitido("ç", escrito)
    assert OCRService._idioma_tesseract(escrito) == "eng"
    assert livro._corrigir_prosa_contextual("Blackhasto play arc", escrito, fuzzy=False) \
        == "Black has to play are"


def test_o_idioma_que_o_projeto_nao_conhece_passa_como_veio():
    assert OCRService._idioma_tesseract("deu") == "deu"
    assert alfabeto.permitido("ß", "de")


@pytest.mark.parametrize("linha", ["tu andas bem", "o arc de triunfo", "a zame", "chen Ping"])
def test_o_portugues_nao_recebe_remendo_do_ingles(linha):
    assert livro._corrigir_prosa_contextual(linha, "pt", fuzzy=False) == linha
    assert livro._corrigir_frases_de_prosa(linha, "pt-BR") == linha


def test_o_ingles_continua_recebendo():
    assert livro._corrigir_frases_de_prosa("andas it was") == "and as it was"


def test_o_paragrafo_recebe_o_idioma():
    def linha(texto):
        return livro.Linha(topo=10, esquerda=10, altura=20, texto=texto)

    assert livro._paragrafo_de([linha("tu andas bem")], idioma="pt").texto == "tu andas bem"
    assert livro._paragrafo_de([linha("so andas it")]).texto == "so and as it"
    [p] = livro._agrupar_em_paragrafos([linha("tu andas bem")], idioma="pt_BR")
    assert p.texto == "tu andas bem"


def test_o_idioma_da_leitura_chega_ao_paragrafo(tmp_path, monkeypatch):
    from tests.test_passadas_de_livro import _pdf

    vistos = set()
    original = livro._paragrafo_de

    def espia(linhas, lex=None, altura=None, idioma="en"):
        vistos.add(idioma)
        return original(linhas, lex, altura, idioma)

    monkeypatch.setattr(livro, "_paragrafo_de", espia)
    livro.extrair(_pdf(tmp_path / "l.pdf", 1), lambda r, ref=None: ("a", 0.99), dpi=150,
                  idioma_ocr="pt", lex=Lexico(palavras={"a"}))
    assert vistos == {"pt"}


def test_ninguem_corta_o_idioma_por_conta_propria():
    """O `startswith("pt")` e o corte de dois caracteres não voltam."""
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for modulo in ("core/livro.py", "core/pdf_nativo.py", "core/alfabeto.py",
                   "core/services/ocr_service.py"):
        with open(os.path.join(raiz, modulo), encoding="utf-8") as f:
            fonte = f.read()
        assert not re.search(r"idioma[^\n]*\.startswith\(\"pt\"|idioma[^\n]*\.lower\(\)\[:2\]", fonte), modulo


def test_a_legenda_da_camada_le_o_idioma_com_regiao():
    assert pdf_nativo.idioma_normalizado("pt-BR") == "pt"
