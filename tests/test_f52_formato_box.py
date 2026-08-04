"""
F5.2 — o `.box` não pode perder dado calado.

Três defeitos: o escritor gravava `char[0]` (ligadura truncada), o `~` era
marcador de vazio sem escape (um `~` real voltava vazio), e um caractere espaço
deixava a linha com 5 campos e o leitor a descartava.

A propriedade que os testes cobram é ida e volta: `ler(escrever(x)) == x`.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import formato_box
from core.box_model import BoxEntry


ALTURA = 1000


def ida_e_volta(char):
    """Escreve um box com esse caractere e devolve o que voltou do disco."""
    original = BoxEntry(char, 10, 20, 30, 40)
    texto = formato_box.escrever_texto([original], ALTURA)
    voltou = formato_box.ler_texto(texto, ALTURA)
    assert len(voltou) == 1, f"a linha sumiu na volta: {texto!r}"
    return voltou[0]


# ---------------------------------------------------------------------------
# O defeito principal: truncar em char[0]
# ---------------------------------------------------------------------------

def test_ligadura_sobrevive_ao_disco():
    assert ida_e_volta("fi").char == "fi"


@pytest.mark.parametrize("char", ["fi", "fl", "ffi", "...", "!?", "1.", "+-"])
def test_sequencias_de_mais_de_um_caractere(char):
    assert ida_e_volta(char).char == char


def test_escritor_nao_trunca_no_primeiro_caractere():
    """O bug literal: `save_ch = ch[0] if ch else '~'`."""
    texto = formato_box.escrever_texto([BoxEntry("fi", 1, 2, 3, 4)], ALTURA)
    assert texto.split()[0] == "fi"


# ---------------------------------------------------------------------------
# O `~` real contra o `~` marcador
# ---------------------------------------------------------------------------

def test_til_digitado_nao_vira_vazio():
    assert ida_e_volta("~").char == "~"


def test_box_vazio_continua_vazio():
    assert ida_e_volta("").char == ""


def test_vazio_ainda_sai_como_til_no_arquivo():
    """Compatibilidade: quem lê o arquivo por fora espera o `~`."""
    texto = formato_box.escrever_texto([BoxEntry("", 1, 2, 3, 4)], ALTURA)
    assert texto.split()[0] == "~"


def test_til_e_vazio_nao_colidem_no_arquivo():
    boxes = [BoxEntry("~", 1, 2, 3, 4), BoxEntry("", 5, 6, 7, 8)]
    texto = formato_box.escrever_texto(boxes, ALTURA)
    primeiros = [linha.split()[0] for linha in texto.strip().splitlines()]
    assert primeiros[0] != primeiros[1]

    voltou = formato_box.ler_texto(texto, ALTURA)
    assert [b.char for b in voltou] == ["~", ""]


# ---------------------------------------------------------------------------
# Espaço e barra invertida — o que quebrava a linha
# ---------------------------------------------------------------------------

def test_espaco_nao_derruba_a_linha():
    assert ida_e_volta(" ").char == " "


def test_espaco_no_meio_de_uma_ligadura():
    assert ida_e_volta("a b").char == "a b"


def test_barra_invertida_sobrevive():
    assert ida_e_volta("\\").char == "\\"


def test_barra_seguida_de_s_nao_vira_espaco():
    """`\\s` é o escape do espaço; um `\\s` literal precisa escapar a barra."""
    assert ida_e_volta("\\s").char == "\\s"


def test_tabulacao_sobrevive():
    assert ida_e_volta("\t").char == "\t"


@pytest.mark.parametrize("char", ["~", " ", "\\", "\t", "\\~", "\\s", "~~"])
def test_linha_gravada_sempre_tem_seis_campos(char):
    texto = formato_box.escrever_texto([BoxEntry(char, 1, 2, 3, 4)], ALTURA)
    assert len(texto.strip().split()) == 6


# ---------------------------------------------------------------------------
# Figurinas e acentos — o alfabeto real do projeto
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("char", list("♔♕♖♗♘♙♚♛♜♝♞♟"))
def test_figurinas(char):
    assert ida_e_volta(char).char == char


@pytest.mark.parametrize("char", ["á", "ç", "±", "∓", "∞", "⨀", "□", "Δ"])
def test_acentos_e_simbolos(char):
    assert ida_e_volta(char).char == char


# ---------------------------------------------------------------------------
# Geometria: o y do arquivo é medido da base
# ---------------------------------------------------------------------------

def test_coordenadas_sobrevivem_a_ida_e_volta():
    original = BoxEntry("a", 11, 22, 33, 44)
    texto = formato_box.escrever_texto([original], ALTURA)
    voltou = formato_box.ler_texto(texto, ALTURA)[0]
    assert (voltou.x1, voltou.y1, voltou.x2, voltou.y2) == (11, 22, 33, 44)


def test_y_e_gravado_a_partir_da_base():
    texto = formato_box.escrever_texto([BoxEntry("a", 11, 22, 33, 44)], ALTURA)
    campos = texto.split()
    assert campos[2] == str(ALTURA - 44)
    assert campos[4] == str(ALTURA - 22)


def test_origem_superior_nao_inverte():
    boxes = formato_box.ler_texto("a 11 22 33 44 0\n", ALTURA,
                                  origem_inferior=False)
    assert (boxes[0].y1, boxes[0].y2) == (22, 44)


# ---------------------------------------------------------------------------
# Arquivos antigos continuam legíveis
# ---------------------------------------------------------------------------

def test_le_arquivo_do_tesseract_sem_escape():
    boxes = formato_box.ler_texto("C 445 1536 478 1571 0\n", 2000)
    assert boxes[0].char == "C"
    assert (boxes[0].x1, boxes[0].x2) == (445, 478)


def test_til_solto_de_arquivo_antigo_ainda_e_vazio():
    """Arquivo gravado antes da F5.2: `~` só podia significar vazio."""
    assert formato_box.ler_texto("~ 1 2 3 4 0\n", ALTURA)[0].char == ""


def test_linha_do_tesseract_com_espaco_literal_vira_box_de_espaco():
    """Cinco campos: o primeiro era um espaço. Antes a linha era descartada."""
    boxes = formato_box.ler_texto("  10 20 30 40 0\n", ALTURA)
    assert len(boxes) == 1
    assert boxes[0].char == " "
    assert (boxes[0].x1, boxes[0].x2) == (10, 30)


# ---------------------------------------------------------------------------
# Linhas que não são box
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("linha", ["", "   ", "lixo", "a b c", "a 1 2 3"])
def test_linha_invalida_e_ignorada(linha):
    assert formato_box.ler_texto(linha + "\n", ALTURA) == []


def test_coordenada_nao_numerica_e_ignorada():
    assert formato_box.ler_texto("a x y z w 0\n", ALTURA) == []


def test_linha_boa_no_meio_de_lixo_sobrevive():
    texto = "lixo\na 10 20 30 40 0\n\noutro lixo\n"
    boxes = formato_box.ler_texto(texto, ALTURA)
    assert [b.char for b in boxes] == ["a"]


def test_arquivo_sem_boxes_gera_texto_vazio():
    assert formato_box.escrever_texto([], ALTURA) == ""


# ---------------------------------------------------------------------------
# Disco de verdade
# ---------------------------------------------------------------------------

def test_ler_e_escrever_em_arquivo(tmp_path):
    caminho = str(tmp_path / "p.box")
    boxes = [BoxEntry("fi", 1, 2, 3, 4), BoxEntry("~", 5, 6, 7, 8),
             BoxEntry("", 9, 10, 11, 12), BoxEntry("♞", 13, 14, 15, 16)]
    formato_box.escrever(caminho, boxes, ALTURA)
    voltou = formato_box.ler(caminho, ALTURA)

    assert [b.char for b in voltou] == ["fi", "~", "", "♞"]
    assert [b.as_tuple()[1:] for b in voltou] == [b.as_tuple()[1:] for b in boxes]


def test_arquivo_e_utf8(tmp_path):
    caminho = str(tmp_path / "p.box")
    formato_box.escrever(caminho, [BoxEntry("♛", 1, 2, 3, 4)], ALTURA)
    with open(caminho, encoding="utf-8") as f:
        assert "♛" in f.read()


def test_numero_da_pagina_vai_para_o_arquivo():
    texto = formato_box.escrever_texto([BoxEntry("a", 1, 2, 3, 4)], ALTURA,
                                       pagina=7)
    assert texto.split()[5] == "7"


# ---------------------------------------------------------------------------
# O leitor da avaliação é o mesmo
# ---------------------------------------------------------------------------

def test_avaliacao_pagina_usa_o_mesmo_leitor(tmp_path):
    from core import avaliacao_pagina

    caminho = str(tmp_path / "p.box")
    formato_box.escrever(caminho, [BoxEntry("fi", 1, 2, 3, 4)], ALTURA)
    boxes = avaliacao_pagina.carregar_box(caminho, ALTURA)
    assert [b.char for b in boxes] == ["fi"]


def test_os_dois_leitores_concordam_nos_arquivos_do_projeto():
    """Havia dois leitores divergentes; agora é um só."""
    from core import avaliacao_pagina

    pasta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Box")
    arquivos = [f for f in os.listdir(pasta) if f.endswith(".box")] if os.path.isdir(pasta) else []
    if not arquivos:
        pytest.skip("nenhum .box no repositório")

    caminho = os.path.join(pasta, sorted(arquivos)[0])
    assert (formato_box.ler(caminho, 3000)
            == avaliacao_pagina.carregar_box(caminho, 3000))
