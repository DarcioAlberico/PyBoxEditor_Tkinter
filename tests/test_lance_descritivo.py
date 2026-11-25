"""O lance em notação descritiva que o motor leu com letra no lugar da fila.

O *Xadrez Básico* (D'Agostini) está todo em notação descritiva portuguesa, e o
Tesseract lê a fila como letra: `TIBD; 2. TIC+, RIT` por `T1BD; 2. T1C+, R1T`.
Medido numa amostra de 50 páginas (1 em 12): 66 trocas, 64 consertos e as duas
impossíveis (`PIC`, `PITR`: o peão nunca vai à primeira fila), que a régua do
peão tirou. No *A Estratégia no Xadrez* e no *Xadrez Vitorioso*, nada.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import livro  # noqa: E402


@pytest.mark.parametrize("lance", [
    "P4R", "C3BR", "TD1D", "B5CR", "D4T+", "P4BD", "R1R", "TR1R", "T1BD",
    "R1C!", "P5D!", "C5CD", "P4TR", "B1BD",
])
def test_o_lance_descritivo_integro(lance):
    assert livro.RE_LANCE_DESCRITIVO.fullmatch(lance)


@pytest.mark.parametrize("token", [
    "BxC", "PxP", "P1C", "P1TR", "DIA", "RIR", "BRANCAS", "P4", "4R", "B8",
])
def test_o_que_nao_e_lance_descritivo(token):
    assert not livro.RE_LANCE_DESCRITIVO.fullmatch(token)


@pytest.mark.parametrize("linha, esperada", [
    ("TIBD; 2. TIC+, RIT; 3.", "T1BD; 2. T1C+, R1T; 3."),
    ("A) 6. BSCR (em vez de 6. B2R).", "A) 6. B5CR (em vez de 6. B2R)."),
    ("B) 4. DAT+ (em vez de 4. P3R) constitui", "B) 4. D4T+ (em vez de 4. P3R) constitui"),
    ("9. PABD R7C! ] g", "9. P4BD R7C! ] g"),
    ("()O; 15. TDID; e as", "()O; 15. TD1D; e as"),
    ("BxP+, RxB; 8. DSD+, RIR; 9.", "BxP+, RxB; 8. D5D+, R1R; 9."),
    # Lance que já é lance, e captura, ficam.
    ("1. P4R P4R 2. C3BR C3BD", "1. P4R P4R 2. C3BR C3BD"),
    ("4. RxP R2B", "4. RxP R2B"),
    # O peão nunca vai à primeira fila: `PIC` não é `P1C`.
    ("3. PIC PITR", "3. PIC PITR"),
])
def test_a_fila_lida_como_letra_volta_a_ser_algarismo(linha, esperada):
    assert livro._corrigir_lances_descritivos(linha) == esperada


@pytest.mark.parametrize("linha", [
    "CAPÍTULO III DIA DAD RIR",
    "O RIR das BRANCAS",
])
def test_sem_lance_na_linha_nada_muda(linha):
    """Sem número de lance nem lance íntegro, um `DAD` ou `RIR` é palavra."""
    assert livro._corrigir_lances_descritivos(linha) == linha


def test_so_em_portugues():
    linha = "TIBD; 2. TIC+, RIT; 3."
    assert livro._corrigir_prosa_contextual(linha, "pt", fuzzy=False) == "T1BD; 2. T1C+, R1T; 3."
    assert livro._corrigir_prosa_contextual(linha, "en", fuzzy=False) == linha
