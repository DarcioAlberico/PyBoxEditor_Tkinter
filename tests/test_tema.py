"""
A paleta da janela principal mora em `ui/tema.py` (item 9 da
`docs/REVISAO_MODOS_OCR.md`).

As cores estavam soltas em nove arquivos, com o mesmo papel em tons diferentes
— o texto de erro era `#B71C1C`, `#b00020` e `#9b2226` conforme o diálogo.
Os testes prendem três coisas: a escala de confiança não mudou de valor (é
contrato da tela, da lista e dos testes da F3.2); os estilos ttk com nome
existem depois de `aplicar`; e nenhum módulo de `ui/` (fora do editor, que tem
a folha dele) voltou a escrever cor à mão.
"""

import re
from pathlib import Path

import pytest
from tkinter import ttk

from conftest import raiz_tk
from ui import confidence, tema

UI = Path(__file__).resolve().parents[1] / "ui"


def test_a_escala_de_confianca_continua_com_os_mesmos_valores():
    assert (confidence.COR_ALTA, confidence.COR_MEDIA, confidence.COR_BAIXA,
            confidence.COR_VAZIO, confidence.COR_SEM_INFO, confidence.COR_SELECAO,
            confidence.COR_LEXICO) == (
        "#2E9B4F", "#FB8C00", "#E53935", "#9E9E9E", "#3F7FBF", "#FFD400", "#8E24AA")


def test_os_estilos_com_nome_existem_depois_de_aplicar():
    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        tema.aplicar(raiz)
        estilo = ttk.Style(raiz)
        for nome, cor in tema.ESTILOS_DE_TEXTO.items():
            assert str(estilo.lookup(nome, "foreground")).lower() == cor.lower(), nome
    finally:
        raiz.destroy()


def test_nenhum_modulo_da_interface_escreve_cor_a_mao():
    """`#RRGGBB` ou `grayNN` fora de `ui/tema.py` é cor que escapou da paleta."""
    solta = re.compile(r"""["'](#[0-9A-Fa-f]{3,6}|gray\d*)["']""")
    achadas = [f"{arquivo.name}:{n}: {linha.strip()}"
               for arquivo in sorted(UI.glob("*.py")) if arquivo.name != "tema.py"
               for n, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1)
               if solta.search(linha) and not linha.lstrip().startswith("#")]
    assert not achadas, "\n".join(achadas)
