import json

import pytest

from core.ocr_benchmark import (
    agregar,
    distancia_edicao,
    executar_manifesto,
    medir_boxes,
    medir_pagina,
    normalizar_texto,
    tokenizar,
)


def test_normalizacao_preserva_conteudo_e_normaliza_unicode():
    assert normalizar_texto("  Café\r\n  com   chá ") == "Café\ncom chá"
    assert normalizar_texto("AbC", ignorar_maiusculas=True) == "abc"


def test_tokenizacao_separa_pontuacao():
    assert tokenizar("Olá, mundo!") == ["Olá", ",", "mundo", "!"]


@pytest.mark.parametrize(("a", "b", "esperado"), [
    ("", "", 0), ("abc", "abc", 0), ("abc", "axc", 1),
    ("kitten", "sitting", 3), (["a", "b"], ["a"], 1),
])
def test_distancia_edicao(a, b, esperado):
    assert distancia_edicao(a, b) == esperado


def test_medir_pagina_calcula_cer_wer_linhas_paragrafos_e_layout():
    ref = {
        "text": "Casa azul.",
        "lines": ["Casa azul."],
        "paragraphs": ["Casa azul."],
        "regions": [{"type": "body"}],
    }
    pred = {
        "text": "Casa aznl.",
        "lines": ["Casa aznl."],
        "paragraphs": ["Casa aznl."],
        "regions": [{"type": "body"}],
    }
    resultado = medir_pagina("p1", ref, pred)
    assert resultado.text.erros == 1
    assert resultado.text.total == len("Casa azul.")
    assert resultado.words.erros == 1
    assert resultado.lines.erros == 1
    assert resultado.paragraphs.acuracia_exata == 0.0
    assert resultado.layout.tipos_corretos == 1


def test_medir_boxes_diferencia_perdidos_espurios_e_caractere():
    ref = [
        {"char": "A", "x1": 0, "y1": 0, "x2": 10, "y2": 10},
        {"char": "B", "x1": 12, "y1": 0, "x2": 22, "y2": 10},
    ]
    pred = [
        {"char": "A", "x1": 1, "y1": 1, "x2": 9, "y2": 9},
        {"char": "X", "x1": 12, "y1": 1, "x2": 21, "y2": 9},
        {"char": "?", "x1": 50, "y1": 50, "x2": 60, "y2": 60},
    ]
    resultado = medir_boxes(ref, pred)
    assert (resultado.referencia, resultado.predicao) == (2, 3)
    assert (resultado.casados, resultado.certos) == (2, 1)
    assert resultado.espurios == 1
    assert resultado.perdidos == 0


def test_agregar_usa_totais_micro_e_nao_media_de_percentuais():
    primeiro = medir_pagina("1", {"text": "a"}, {"text": "b"})
    segundo = medir_pagina("2", {"text": "abcdefghij"}, {"text": "abcdefghij"})
    resultado = agregar([primeiro, segundo])
    assert resultado.text.erros == 1
    assert resultado.text.total == 11
    assert resultado.text.cer == pytest.approx(1 / 11)


def test_executar_manifesto_resolve_caminhos_relativos(tmp_path):
    (tmp_path / "ref.json").write_text(json.dumps({"text": "abc"}), encoding="utf-8")
    (tmp_path / "pred.json").write_text(json.dumps({"text": "abd"}), encoding="utf-8")
    manifesto = tmp_path / "manifest.json"
    manifesto.write_text(json.dumps({"pages": [{"id": "p1", "reference": "ref.json",
                                                  "prediction": "pred.json"}]}),
                         encoding="utf-8")
    resultado = executar_manifesto(manifesto)
    assert resultado.pages == 1
    assert resultado.text.erros == 1
