"""
Testes de `ui/editor/tabuleiro.py` (ED-05; SPEC_EDITOR §11.2, §13.2): o teclado do
tabuleiro — `mover_selecao` × 4 + `por_peca("q", False)` põe a dama branca em e1,
`por_peca("q", True)` a preta, no idioma `pt` é `por_peca("d", False)`, `limpar_casa()`
esvazia, o anel de seleção é de dois tons nas duas paletas (AC-ED05-8); a cor da peça
vem de `event.state & 0x1` e nunca da caixa da letra; girar; `TabuleiroEdicao.de_fen`;
e o diálogo da F8.2 continua desenhando pelo widget.

Rodar sem pytest:      python tests/test_editor_tabuleiro.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from conftest import raiz_tk
from core.tabuleiro_edicao import TabuleiroEdicao
from ui.editor.tabuleiro import PALETAS, TabuleiroEditavel


class _Evento:
    def __init__(self, keysym="", char="", state=0, x=0, y=0):
        self.keysym, self.char, self.state, self.x, self.y = keysym, char, state, x, y


class _Widget:
    def __init__(self, fen="8/8/8/8/8/8/8/8 w - - 0 1", **kw):
        self.fen, self.kw = fen, kw

    def __enter__(self):
        self.raiz = raiz_tk()
        if self.raiz is None:
            pytest.skip("sem display")
        self.w = TabuleiroEditavel(self.raiz, TabuleiroEdicao.de_fen(self.fen), **self.kw)
        self.w.pack()
        self.raiz.update_idletasks()
        return self

    def __exit__(self, *a):
        try:
            self.raiz.destroy()
        except Exception:
            pass


def test_ac8_setas_e_letras_poem_a_dama_em_e1_branca_e_preta_e_em_portugues():
    with _Widget() as t:
        w = t.w
        w.selecionada = (7, 0)                                  # a1
        for _ in range(4):
            w.mover_selecao(0, 1)
        assert w.selecionada == (7, 4)                          # e1
        assert w.por_peca("q", False) and w.tabuleiro.casa(7, 4).simbolo == "Q"
        assert w.por_peca("q", True) and w.tabuleiro.casa(7, 4).simbolo == "q"
        assert w.limpar_casa() and w.tabuleiro.casa(7, 4).simbolo is None
        assert w.fen().split()[0] == "8/8/8/8/8/8/8/8"
    with _Widget(idioma="pt") as t:
        w = t.w
        w.selecionada = (7, 4)
        assert w.por_peca("d", False) and w.tabuleiro.casa(7, 4).simbolo == "Q"   # D de dama
        assert w.por_peca("c", True) and w.tabuleiro.casa(7, 4).simbolo == "n"    # C de cavalo, preto
        assert not w.por_peca("q", False)                                          # não é letra do mapa pt
        assert w.tabuleiro.casa(7, 4).simbolo == "n"


def test_a_cor_vem_do_shift_e_nao_da_caixa_da_letra_e_as_teclas_movem_e_apagam():
    with _Widget() as t:
        w = t.w
        w.selecionada = (4, 4)
        assert w._na_tecla(_Evento("k", "k")) == "break" and w.tabuleiro.casa(4, 4).simbolo == "K"     # minúscula, sem Shift: branca
        assert w._na_tecla(_Evento("K", "K", state=0x1)) == "break" and w.tabuleiro.casa(4, 4).simbolo == "k"  # Shift: preta
        assert w._na_tecla(_Evento("Right", "")) == "break" and w.selecionada == (4, 5)
        assert w._na_tecla(_Evento("Up", "")) == "break" and w.selecionada == (3, 5)
        assert w._na_tecla(_Evento("Down", "")) == "break" and w._na_tecla(_Evento("Left", "")) == "break"
        assert w.selecionada == (4, 4)
        assert w._na_tecla(_Evento("Delete", "")) == "break" and w.tabuleiro.casa(4, 4).simbolo is None
        assert w._na_tecla(_Evento("z", "z", state=0x4)) is None          # Ctrl: não é peça
        assert w._na_tecla(_Evento("Return", "")) is None                 # sobe para o diálogo
        assert w._na_tecla(_Evento("Tab", "")) is None
        # girar pelo F: a seleção continua na mesma casa do tabuleiro, desenhada do outro lado
        assert w._na_tecla(_Evento("f", "f")) == "break" and w.orientacao == "preta"
        w.mover_selecao(0, 1)
        assert w.selecionada == (4, 3)                                    # girado, a seta direita anda para a esquerda
        assert w.girar() == "branca"


def test_o_anel_de_selecao_tem_dois_tons_nas_duas_paletas():
    for alto in (False, True):
        with _Widget(alto_contraste=alto) as t:
            w = t.w
            w.selecionada = (0, 0)
            w.desenhar()
            fora = w.canvas.find_withtag("anel-fora")
            dentro = w.canvas.find_withtag("anel-dentro")
            assert len(fora) == 1 and len(dentro) == 1
            assert w.canvas.itemcget(fora[0], "outline") == "#ffffff" and w.canvas.itemcget(fora[0], "width") == "1.0"
            assert w.canvas.itemcget(dentro[0], "outline") == "#000000" and w.canvas.itemcget(dentro[0], "width") == "2.0"
            casas = [w.canvas.itemcget(i, "fill") for i in w.canvas.find_withtag("casa")]
            clara, escura = PALETAS["alto_contraste" if alto else "normal"]
            assert set(casas) == {clara, escura}
            assert int(w.canvas.cget("highlightthickness")) >= 2                  # foco visível (§13.2)


def test_de_fen_le_pecas_lado_e_roque_e_o_mouse_pinta_move_e_apaga():
    t = TabuleiroEdicao.de_fen("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
    assert t.fen() == "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    assert t.roque == "KQkq" and not t.lado_informado and t.plausivel
    t2 = TabuleiroEdicao.de_fen("8/8/8/8/8/8/8/K6k", "b")
    assert t2.lado == "b" and t2.lado_informado and t2.roque == ""
    with pytest.raises(ValueError):
        TabuleiroEdicao.de_fen("isto não é FEN")
    with _Widget("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1") as w_:
        w = w_.w
        lado = w.lado_casa
        w._no_clique(_Evento(x=4 * lado + 2, y=6 * lado + 2))               # e2
        assert w.selecionada == (6, 4)
        w._no_solta(_Evento(x=4 * lado + 2, y=4 * lado + 2))                # arrasta para e4
        assert w.tabuleiro.casa(4, 4).simbolo == "P" and w.tabuleiro.casa(6, 4).simbolo is None
        w.escolher("N")
        w._no_clique(_Evento(x=0 * lado + 2, y=4 * lado + 2))               # pinta um cavalo em a4
        assert w.tabuleiro.casa(4, 0).simbolo == "N"
        w._no_clique(_Evento(x=0 * lado + 2, y=4 * lado + 2))               # de novo: alterna para vazia
        assert w.tabuleiro.casa(4, 0).simbolo is None
        w.escolher("N")
        w._no_direito(_Evento(x=4 * lado + 2, y=4 * lado + 2))              # o botão direito apaga
        assert w.tabuleiro.casa(4, 4).simbolo is None
        assert not w.sem_figuras or len(w.canvas.find_withtag("peca")) == 30
        w.carregar_fen("8/8/8/8/8/8/8/K6k w - - 0 1")
        assert len(w.canvas.find_withtag("peca")) == 2
        w.espelhar()
        assert w.tabuleiro.casa(0, 0).simbolo == "k" and w.tabuleiro.casa(0, 7).simbolo == "K"


def test_o_dialogo_da_f82_desenha_pelo_widget_e_delega_o_que_era_seu():
    from PIL import Image
    from core.diagrama import Casa, Leitura
    from ui.dialogo_diagrama import DialogoDiagrama

    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        leitura = Leitura(caixa=(0, 0, 64, 64), casas=[Casa(7, 4, "K", 1.0), Casa(0, 4, "k", 1.0)])
        dlg = DialogoDiagrama(raiz, Image.new("L", (64, 64), 255), [leitura])
        dlg.construir()
        assert isinstance(dlg.editavel, TabuleiroEditavel) and dlg.canvas is dlg.editavel.canvas
        assert dlg.selecionada is None and dlg.pincel is None
        dlg.selecionada = (4, 4)
        assert dlg.editavel.selecionada == (4, 4)
        dlg._na_tecla(_Evento(char="Q"))
        assert dlg.tabuleiro().casa(4, 4).simbolo == "Q" and dlg.var_fen.get().split()[0].count("Q") == 1
        dlg._escolher("")
        assert dlg.pincel == "" and dlg.editavel.pincel == ""
        dlg._fechar()
    finally:
        raiz.destroy()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider", "-o", "addopts="]))
