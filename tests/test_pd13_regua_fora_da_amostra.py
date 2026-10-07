"""
PD-13 (`docs/ROADMAP_PENDENCIAS.md`) — a régua da F57, medida fora da amostra.

A F57 achou que "concorda com o k-NN" separa os erros de `easyocr_so` muito
melhor que a confiança dele (0,978 contra 0,776), e deixou escrito o que
faltava para embarcar: o corte da candidata era escolhido na mesma amostra em
que era medido. `_regua_fora_da_amostra` ajusta o corte de cada página nas
outras, ao orçamento de hoje delas, e mede na página que ficou de fora.
"""

import sys

import pytest

import medir_cadeia as mc
from ui.confidence import LIMIAR_ALTO


def _reg(pagina, conf, char, verdade, chave):
    """O registro do instrumento: fonte, confiança, lido, verdade, página, chave."""
    return ("easyocr_so", conf, char, verdade, pagina, chave)


def _errou(reg):
    return mc.normalizar(reg[2]) != mc.normalizar(reg[3])


def _paginas(n_paginas=4):
    """Cada página com dois erros e dois acertos. A confiança de hoje erra a
    ordem — marca os dois acertos e deixa os erros passar —, e o orçamento de
    hoje é dois por página; a candidata põe os erros embaixo."""
    notados = []
    chave = 0
    for p in range(n_paginas):
        for errado in (True, True, False, False):
            chave += 1
            hoje = (LIMIAR_ALTO + 1.0) / 2 if errado else LIMIAR_ALTO / 2
            reg = _reg(f"p{p}", hoje, "a", "b" if errado else "a", chave)
            notados.append((reg, 0.1 if errado else 0.9))
    return notados


def test_a_regua_que_separa_pega_os_erros_da_pagina_que_nao_viu():
    notados = _paginas()
    fora = mc._regua_fora_da_amostra(notados, _errou)
    assert fora is not None
    marcados, pegos = fora
    # Ao custo de hoje (dois por página), os dois erros de cada página — e
    # hoje esse mesmo custo não pega nenhum.
    assert (marcados, pegos) == (8, 8)


def test_uma_pagina_so_nao_tem_fora_da_amostra():
    notados = [(r, n) for r, n in _paginas() if r[4] == "p0"]
    assert mc._regua_fora_da_amostra(notados, _errou) is None


def test_a_pagina_medida_nao_entra_no_corte():
    """Numa página a candidata inverte a ordem (acerto embaixo). O corte vem
    das outras, e ali ele marca os acertos dela — é o custo de medir honesto."""
    notados = _paginas(3)
    invertida = [(r, (0.9 if n == 0.1 else 0.1) if r[4] == "p2" else n)
                 for r, n in notados]
    marcados, pegos = mc._regua_fora_da_amostra(invertida, _errou)
    # Nas duas páginas boas o corte pega os dois erros; na invertida, o corte
    # das outras marca os dois acertos dela e deixa os erros passar.
    assert (marcados, pegos) == (6, 4)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
