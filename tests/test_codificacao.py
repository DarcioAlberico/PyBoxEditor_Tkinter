"""Todo arquivo de texto rastreado é UTF-8 sem BOM e sem mojibake (item 2 da análise de 2026-10-06).

A porta por onde o mojibake entrou duas vezes — uma ferramenta gravando em cp1252 o que
já era UTF-8 — fica fechada aqui: a suíte falha se um `Ã` seguido de `£` (o `ã` em dupla
codificação) voltar a algum arquivo, e diz em qual linha. O verificador é `scripts/conferir_codificacao.py`, que também corrige
(`--corrigir`); os testes de baixo provam que ele pega cada um dos três defeitos.
"""
from pathlib import Path

import pytest

from scripts.conferir_codificacao import (arquivos_de_texto, corrigir,
                                           desfazer_mojibake, problemas, relatorio)

RAIZ = Path(__file__).resolve().parents[1]

#: O `á` em dupla codificação, construído em vez de escrito: este arquivo também passa pelo
#: crivo que define, e o par literal o reprovaria.
A_ESTRAGADO = "á".encode("utf-8").decode("cp1252")


def test_todo_arquivo_de_texto_rastreado_e_utf8_sem_bom_e_sem_mojibake():
    caminhos = arquivos_de_texto(RAIZ)
    assert len(caminhos) > 100, "a lista de arquivos de texto veio vazia — o git ou a raiz mudaram?"
    achados = relatorio(caminhos, RAIZ)
    assert not achados, "\n" + "\n".join(achados)


def test_o_byte_fora_de_utf8_e_apontado_com_a_linha(tmp_path):
    arquivo = tmp_path / "cp1252.py"
    arquivo.write_bytes(b"# ok\n# p\xe1gina\n")
    assert problemas(arquivo) == ["linha 2: byte 0xe1 fora de UTF-8"]
    assert corrigir(arquivo) is False, "o que não é UTF-8 não se corrige às cegas"


def test_o_bom_e_apontado_e_sai_na_correcao(tmp_path):
    arquivo = tmp_path / "bom.py"
    arquivo.write_bytes(b"\xef\xbb\xbfimport os\n")
    assert problemas(arquivo) == ["começa com BOM"]
    assert corrigir(arquivo) is True
    assert arquivo.read_bytes() == b"import os\n"
    assert problemas(arquivo) == []


def test_o_mojibake_e_apontado_e_a_correcao_devolve_o_original(tmp_path):
    # Sem `”` (U+201D): o terceiro byte dele em UTF-8 é 0x9D, que o cp1252 não tem — é um
    # dos cinco bytes pelos quais o mojibake não passa, e o `decode` abaixo o recusaria.
    original = "A página não tem acentuação — só o travessão «assim».\n"
    estragado = original.encode("utf-8").decode("cp1252")
    assert estragado != original
    arquivo = tmp_path / "moji.md"
    arquivo.write_text(estragado, encoding="utf-8")
    [achado] = problemas(arquivo)
    assert achado.startswith(f"linha 1: mojibake {A_ESTRAGADO!r}")
    assert corrigir(arquivo) is True
    assert arquivo.read_text(encoding="utf-8") == original
    assert problemas(arquivo) == []


def test_a_linha_marcada_como_intencional_fica_fora_da_conferencia_e_da_correcao(tmp_path):
    arquivo = tmp_path / "relatorio.py"
    conteudo = (f'EXEMPLO = "p{A_ESTRAGADO}gina"  # mojibake intencional: o relatório detecta isto\n'
                f'OUTRO = "p{A_ESTRAGADO}gina"\n')
    arquivo.write_text(conteudo, encoding="utf-8")
    assert problemas(arquivo) == [f"linha 2: mojibake {A_ESTRAGADO!r}"]
    assert corrigir(arquivo) is True
    assert arquivo.read_text(encoding="utf-8") == conteudo.replace(
        f'OUTRO = "p{A_ESTRAGADO}gina"', 'OUTRO = "página"')


@pytest.mark.parametrize("texto", [
    "página, não, coração, três, ação — e “aspas”.",
    "A régua: ≤ 15%, ± 0,5; ⩲ e ♘f3.",
    "Ângulo e Âmbito em caixa alta; Ã sozinho.",
])
def test_o_texto_certo_passa_intacto(texto):
    assert desfazer_mojibake(texto) == texto
