from __future__ import annotations

from pathlib import Path

from PIL import Image

from core.chess_symbols import CHESS_ANNOTATION_CHARACTERS
from core.linha_sintetica import gerar_caracteres_faltantes


def test_catalogo_contem_simbolos_de_avaliacao():
    assert {"±", "∓", "∞", "⩲", "⩱", "⯹", "⇆", "⨁"} <= CHESS_ANNOTATION_CHARACTERS


def test_gera_exemplos_de_classes_ausentes_idempotentes(tmp_path: Path):
    primeira = gerar_caracteres_faltantes({"±", "†", "E"}, tmp_path)
    segunda = gerar_caracteres_faltantes({"±", "†", "E"}, tmp_path)
    assert [texto for _caminho, texto in primeira] == [texto for _caminho, texto in segunda]
    assert all(caminho.exists() for caminho, _texto in primeira)
    with Image.open(primeira[0][0]) as imagem:
        assert imagem.width >= 2 and imagem.height >= 2
