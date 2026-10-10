"""
F123 — a poda da geometria da linha (F112) chega à janela.

A F112 pôs a poda de Baird no caminho do livro, onde a âncora é só a rede. As
ações «Detectar e Preencher» leem pela cadeia de `ocr_service` — rede, k-NN e
EasyOCR — e depois pela linha do EasyOCR, com a trava da F18; a poda precisa da
linha inteira para votar o corpo dela e por isso não cabe em `ler_caractere`,
que vê um box de cada vez. Ela entra em `leitura_de_linha.ler_pagina` como um
gancho que corrige a âncora da linha **antes** de a linha ser lida, e a troca
sai com fonte própria (`geometria`), que a fila de revisão vê.

As linhas destes testes são as desenhadas da F112 (`test_f112_geometria`), com
a tabela de lá: o teste diz o que a poda faz, e não o que a tabela gravada mediu.

Rodar sem pytest:      python tests/test_f123_poda_na_janela.py
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

from core import geometria_da_linha as gl
from core import leitura_de_linha as ldl
from core.box_model import BoxEntry
from tests.test_f112_geometria import TABELA, _linha


def _boxes(chars, y1=10, y2=30, largura=8):
    return [BoxEntry(c, i * largura, y1, i * largura + largura - 1, y2)
            for i, c in enumerate(chars)]


def _pagina():
    return np.full((60, 80), 200, dtype=np.uint8)


def _ancora(leituras):
    """`ler_caractere` que responde, box a box, a lista dada."""
    fila = list(leituras)
    return lambda _b: fila.pop(0)


# ----------------------------------------------------------------------
# O gancho de `ler_pagina`
# ----------------------------------------------------------------------

def test_a_poda_corrige_a_ancora_antes_da_linha():
    """
    `c0u` com o `0` lido pela rede a 0,95: a trava o protege da linha, e sem a
    poda ele fica. A poda o troca antes, a linha concorda com a âncora já
    corrigida, e a troca sai com a fonte da geometria.
    """
    leituras = [("c", .95, "neural"), ("0", .95, "neural"), ("u", .95, "neural")]
    sem = ldl.ler_pagina(_pagina(), [_boxes("c0u")],
                         ler_faixa=lambda t: ("cou", .9),
                         ler_caractere=_ancora(leituras),
                         conf_maxima_para_trocar=0.70)
    assert "".join(c for _b, c, _cf, _f in sem) == "c0u"

    vistas = []

    def podar(linha, ancora):
        vistas.append((len(linha), [c for c, _cf, _f in ancora]))
        return {1: ("o", .97, gl.FONTE)}

    com = ldl.ler_pagina(_pagina(), [_boxes("c0u")],
                         ler_faixa=lambda t: ("cou", .9),
                         ler_caractere=_ancora(leituras),
                         conf_maxima_para_trocar=0.70, podar=podar)
    assert "".join(c for _b, c, _cf, _f in com) == "cou"
    assert [f for _b, _c, _cf, f in com] == ["neural", gl.FONTE, "neural"]
    assert com[1][2] == pytest.approx(.97)
    assert vistas == [(3, ["c", "0", "u"])], "a linha inteira, uma vez"


def test_a_linha_e_alinhada_contra_a_ancora_podada():
    """
    A leitura da linha continua mandando onde a âncora é fraca — e o que ela
    compara é a âncora depois da poda: o box que a poda trocou e a linha
    confirma não vira `easyocr_linha`.
    """
    leituras = [("c", .95, "neural"), ("0", .95, "neural"), ("x", .30, "neural")]
    saida = ldl.ler_pagina(_pagina(), [_boxes("c0x")],
                           ler_faixa=lambda t: ("cou", .9),
                           ler_caractere=_ancora(leituras),
                           conf_maxima_para_trocar=0.70,
                           podar=lambda linha, ancora: {1: ("o", .97, gl.FONTE)})
    assert [(c, f) for _b, c, _cf, f in saida] == [
        ("c", "neural"), ("o", gl.FONTE), ("u", "easyocr_linha")]


def test_sem_poda_nada_muda():
    leituras = [("a", .95, "neural"), ("b", .95, "neural")]
    saida = ldl.ler_pagina(_pagina(), [_boxes("ab")],
                           ler_faixa=lambda t: ("", 0.0),
                           ler_caractere=_ancora(leituras), podar=None)
    assert [(c, f) for _b, c, _cf, f in saida] == [("a", "neural"), ("b", "neural")]


def test_o_erro_da_poda_deixa_a_ancora_quando_ha_ao_falhar():
    def podar(linha, ancora):
        raise ValueError("recorte degenerado")

    falhas = []
    leituras = [("a", .95, "neural"), ("b", .95, "neural")]
    saida = ldl.ler_pagina(_pagina(), [_boxes("ab")],
                           ler_faixa=lambda t: ("", 0.0),
                           ler_caractere=_ancora(leituras), podar=podar,
                           ao_falhar=lambda b, e: falhas.append(type(e).__name__))
    assert "".join(c for _b, c, _cf, _f in saida) == "ab"
    assert falhas == ["ValueError"]

    with pytest.raises(ValueError):
        ldl.ler_pagina(_pagina(), [_boxes("ab")],
                       ler_faixa=lambda t: ("", 0.0),
                       ler_caractere=_ancora(list(leituras)), podar=podar)


# ----------------------------------------------------------------------
# `poda_da_ancora`: a poda da F112 com a âncora da janela
# ----------------------------------------------------------------------

class _Rede:
    """O top-k da rede, e quantas vezes foi pedido."""

    def __init__(self, oferta):
        self.oferta = list(oferta)
        self.pedidos = 0

    def __call__(self, _recorte, k):
        self.pedidos += 1
        return self.oferta[:k]


def _gancho(glifos, rede, **kw):
    img, caixas = _linha([(g, 0) for g in glifos])
    return caixas, gl.poda_da_ancora(img, rede, tabela=TABELA, **kw)


def test_o_zero_da_rede_no_corpo_de_o_vira_o_com_fonte_propria():
    rede = _Rede([("0", .6), ("o", .35), ("O", .04)])
    caixas, podar = _gancho("cons", rede)
    ancora = [("c", .95, "neural"), ("0", .95, "neural"), ("n", .95, "neural"),
              ("s", .95, "neural")]
    assert podar(caixas, ancora) == {1: ("o", pytest.approx(.99), gl.FONTE)}
    assert rede.pedidos == 1, "só o box que não cabe consulta a rede"


def test_a_leitura_de_outro_elo_nao_e_trocada_nem_consulta_a_rede():
    """
    O k-NN e o EasyOCR respondem onde a rede não soube; trocar a resposta
    deles pelas candidatas da rede seria outro elo lendo, não a geometria
    podando. Eles votam o corpo da linha, e ficam como estão.
    """
    rede = _Rede([("0", .6), ("o", .35)])
    caixas, podar = _gancho("cons", rede)
    for fonte in ("learner", "easyocr"):
        ancora = [("c", .95, "neural"), ("0", .95, fonte), ("n", .95, "neural"),
                  ("s", .95, "neural")]
        assert podar(caixas, ancora) == {}
    assert rede.pedidos == 0


def test_na_janela_a_leitura_fraca_que_cabe_nao_e_confirmada():
    """
    No livro, o `o` fraco que é o único do grupo a caber sobe para a massa do
    grupo, porque o piso de confiança o apagaria do texto. Na janela ele não
    some: vai para a fila de revisão, e subir a confiança o esconderia de lá.
    """
    rede = _Rede([("o", .45), ("0", .3), ("O", .2)])
    img, caixas = _linha([(g, 0) for g in "cosa"])
    leituras = [("c", .95), ("o", .45), ("s", .95), ("a", .95)]
    no_livro = gl.podar(caixas, [img[b.y1:b.y2, b.x1:b.x2] for b in caixas],
                        leituras, rede, tabela=TABELA, limiar_de_confirmacao=.5)
    assert no_livro == {1: ("o", pytest.approx(.95))}

    podar = gl.poda_da_ancora(img, rede, tabela=TABELA)
    assert podar(caixas, [(c, cf, "neural") for c, cf in leituras]) == {}


def test_linha_curta_demais_nao_tem_corpo_e_nada_muda():
    rede = _Rede([("0", .6), ("o", .35)])
    caixas, podar = _gancho("co", rede)
    assert podar(caixas, [("c", .95, "neural"), ("0", .95, "neural")]) == {}


# ----------------------------------------------------------------------
# A janela
# ----------------------------------------------------------------------

def test_a_troca_da_geometria_entra_sempre_na_fila_de_revisao():
    """
    A confiança da troca é a massa do grupo, e a rede não separa os membros de
    um grupo: o número diz o desenho, não qual dos dois — régua plana, como a
    do EasyOCR (F48). A cor segue a fila, e a lista mostra `!`.
    """
    from ui import confidence as cf

    b = BoxEntry("o", 0, 0, 9, 9, confidence=0.99, source=gl.FONTE)
    assert cf.precisa_revisao(b) is True
    assert cf.cor_do_box(b) == cf.COR_BAIXA
    assert cf.rotulo(b).strip() == "!"
    assert cf.precisa_revisao(
        BoxEntry("o", 0, 0, 9, 9, confidence=0.99, source="neural")) is False


def test_so_a_acao_neural_passa_a_poda():
    """
    O «Híbrido» não carrega a rede para ler, e as candidatas da troca são dela.
    O neural a passa, com as candidatas pela porta do serviço, e o laço das
    duas ações a entrega a `ler_pagina` depois de `preparar` carregar o modelo.
    """
    from ui.main_window import MainWindow

    neural = inspect.getsource(MainWindow.generate_and_fill_neural)
    assert "poda_da_ancora(" in neural
    assert "self.learning_service.candidatas" in neural
    assert "poda=poda" in neural
    assert "Corrigidos pela geometria" in neural
    assert "poda" not in inspect.getsource(MainWindow.generate_and_fill_combined)

    laco = inspect.getsource(MainWindow._preencher_por_linha)
    montagem = "podar=None if poda is None else poda(pagina)"
    assert montagem in laco
    assert laco.index("= preparar(h, pagina, faixas, margens)") < laco.index(
        montagem), "a poda é montada depois de o modelo carregar"


def test_o_instrumento_mede_a_acao_por_omissao():
    """
    Toda tabela do `medir_cadeia.py` mede produção por omissão (F116): depois
    desta fase, o caminho neural dele poda como a ação poda, e o híbrido não.
    `None` explícito é a cadeia sem a poda — a ponta de `--geometria`.
    """
    from scripts.medidas import medir_cadeia as mc

    assert inspect.signature(mc.rodar).parameters["podar"].default is mc.DA_ACAO

    class _Cadeia:
        predictor = object()

    assert mc.poda_da_acao(_Cadeia(), "neural") is not None
    assert mc.poda_da_acao(_Cadeia(), "hibrido") is None
    _Cadeia.predictor = None
    assert mc.poda_da_acao(_Cadeia(), "neural") is None


def _janela():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from conftest import raiz_tk
    from ui.main_window import MainWindow

    raiz = raiz_tk()
    if raiz is None:
        return None, None
    return raiz, MainWindow(raiz)


def test_a_janela_aplica_a_troca_com_a_fonte_e_conta_no_dialogo(monkeypatch):
    from tkinter import messagebox
    from PIL import Image

    raiz, win = _janela()
    if win is None:
        pytest.skip("sem display")
    try:
        infos = []
        monkeypatch.setattr(messagebox, "showinfo", lambda t, m, **k: infos.append(m))
        monkeypatch.setattr(messagebox, "showwarning", lambda t, m, **k: infos.append(m))
        win.image = Image.new("L", (80, 60), color=200)
        win.boxes = _boxes("c0u")
        monkeypatch.setattr(win.ocr_service, "easyocr_linha_conf",
                            lambda faixa, *a, **k: ("", 0.0))

        paginas = []

        def preparar(h, pagina, faixas, margens):
            fila = [("c", .95, "neural"), ("0", .95, "neural"), ("u", .95, "neural")]
            return lambda _b: fila.pop(0)

        def poda(pagina):
            paginas.append(pagina.shape)
            return lambda linha, ancora: {1: ("o", .97, gl.FONTE)}

        win._preencher_por_linha(
            "teste", preparar,
            lambda fontes: f"Corrigidos pela geometria: {fontes.get(gl.FONTE, 0)}",
            conf_maxima_para_trocar=0.70, poda=poda)
        for _ in range(300):
            raiz.update()
            if infos:
                break

        assert "".join(b.char for b in win.boxes) == "cou"
        assert win.boxes[1].source == gl.FONTE
        assert paginas == [(60, 80)], "a poda recebe a página que foi lida"
        assert infos and "Corrigidos pela geometria: 1" in infos[0]
    finally:
        try:
            win.task.shutdown()
            raiz.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
