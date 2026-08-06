"""
F8.2 — o diagrama vira uma janela com tabuleiro editável.

O risco desta fase é o inverso do da F7.1. Lá era **uma posição errada que
parece certa**; aqui é **uma edição que se perde ou que apaga o que estava
certo**. Um FEN abre em qualquer programa de xadrez e vira fato, e agora ele
carrega também o que a mão do usuário mexeu — inclusive o lado a jogar e o
roque, que não estão no diagrama e passaram a poder ser informados.

Daí o peso destes testes cair em três coisas: a edição **não se perder** (ao
desfazer, ao trocar de diagrama e voltar), a edição **não acontecer sozinha**
(clicar seleciona, não apaga), e a legalidade acompanhar o que foi digitado.

Rodar sem pytest:      python tests/test_f82_tabuleiro.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

from core import diagrama
from core.diagrama import Casa, Leitura
from core.tabuleiro_edicao import AVISO_CONVENCAO, TabuleiroEdicao


# ----------------------------------------------------------------------
# Apoio
# ----------------------------------------------------------------------

def _leitura(pecas=None, caixa=(0, 0, 320, 320)) -> Leitura:
    """Uma leitura pronta: `pecas` é {(linha, coluna): simbolo}."""
    pecas = pecas or {}
    leitura = Leitura(caixa=caixa)
    leitura.casas = [Casa(r, c, pecas.get((r, c)), 0.9)
                     for r in range(8) for c in range(8)]
    return leitura


#: Posição legal mínima: rei branco em e1, rei preto em e8.
REIS = {(7, 4): "K", (0, 4): "k"}


def _tabuleiro_sintetico(pecas=(), lado=320):
    """Igual ao da F7.1: casas claras e escuras, peça = disco preto."""
    import cv2
    im = np.full((lado, lado), 250, np.uint8)
    passo = lado // 8
    for r in range(8):
        for c in range(8):
            if (r + c) % 2:
                im[r * passo:(r + 1) * passo, c * passo:(c + 1) * passo] = 170
    for r, c in pecas:
        cv2.circle(im, (c * passo + passo // 2, r * passo + passo // 2),
                   passo // 3, 0, -1)
    return im


def _dialogo(leituras=None):
    """(diálogo construído, raiz) ou pula o teste se não houver display."""
    from PIL import Image
    from conftest import raiz_tk
    from ui.dialogo_diagrama import DialogoDiagrama

    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    leituras = leituras or [_leitura(dict(REIS))]
    arr = _tabuleiro_sintetico()
    dlg = DialogoDiagrama(raiz, Image.fromarray(arr), leituras)
    dlg.construir()
    return dlg, raiz


class _Evento:
    """O mínimo de um evento Tk: onde clicou, o que digitou."""

    def __init__(self, x=0, y=0, char="", keysym="", state=0):
        self.x, self.y = x, y
        self.char, self.keysym, self.state = char, keysym, state


def _ponto(linha, coluna):
    from ui.dialogo_diagrama import LADO_CASA
    return (coluna * LADO_CASA + LADO_CASA // 2,
            linha * LADO_CASA + LADO_CASA // 2)


# ----------------------------------------------------------------------
# O tabuleiro nasce da leitura, sem levá-la junto
# ----------------------------------------------------------------------

def test_nasce_com_as_64_casas():
    t = TabuleiroEdicao(_leitura(dict(REIS)))
    assert len(t.casas) == 64
    assert t.casa(7, 4).simbolo == "K"
    assert t.casa(4, 4).simbolo is None


def test_nasce_vazio_sem_leitura():
    t = TabuleiroEdicao()
    assert len(t.casas) == 64
    assert t.ocupadas == []


def test_editar_nao_mexe_na_leitura_de_origem():
    """
    Fechar a janela sem confirmar não pode ter mudado nada.

    A leitura é o que o programa leu; a edição é o que o usuário quis. Deixar
    a segunda escrever na primeira faria a próxima abertura mostrar a correção
    como se fosse leitura — e a F7.1 inteira se apoia em mostrar o que foi
    lido ao lado do que está impresso.
    """
    leitura = _leitura(dict(REIS))
    t = TabuleiroEdicao(leitura)
    t.colocar(4, 4, "Q")
    assert leitura.casas[4 * 8 + 4].simbolo is None
    assert t.casa(4, 4).simbolo == "Q"


# ----------------------------------------------------------------------
# Editar uma casa
# ----------------------------------------------------------------------

def test_colocar_troca_a_peca():
    t = TabuleiroEdicao(_leitura({(3, 3): "P"}))
    assert t.colocar(3, 3, "B")
    assert t.casa(3, 3).simbolo == "B"


def test_a_casa_corrigida_vira_autoridade():
    """Como o box digitado da F3.2: confiança 1,0 e origem do usuário."""
    t = TabuleiroEdicao(_leitura({(3, 3): "P"}))
    t.casa(3, 3).confianca = 0.2
    t.colocar(3, 3, "B")
    assert t.casa(3, 3).corrigida
    assert t.casa(3, 3).confianca == 1.0


def test_corrigir_apaga_a_marca_da_legalidade():
    """
    O vermelho dizia "isto aqui eu troquei sozinho", e deixou de ser verdade.

    Manter as duas marcas faria a casa contar duas vezes no resumo e pintaria
    de vermelho o que o usuário acabou de escolher.
    """
    t = TabuleiroEdicao(_leitura({(3, 3): "P"}))
    t.casa(3, 3).arbitrada = True
    t.colocar(3, 3, "B")
    assert not t.casa(3, 3).arbitrada
    assert t.corrigidas == 1
    assert t.arbitradas == 0


def test_colocar_o_mesmo_nao_e_mudanca():
    t = TabuleiroEdicao(_leitura({(3, 3): "P"}))
    assert not t.colocar(3, 3, "P")
    assert not t.casa(3, 3).corrigida


def test_simbolo_invalido_e_recusado():
    t = TabuleiroEdicao(_leitura())
    assert not t.colocar(3, 3, "X")
    assert t.casa(3, 3).simbolo is None


def test_fora_do_tabuleiro_e_recusado():
    t = TabuleiroEdicao(_leitura())
    assert not t.colocar(8, 0, "P")
    assert not t.colocar(-1, 0, "P")
    assert t.casa(9, 9) is None


def test_limpar_esvazia():
    t = TabuleiroEdicao(_leitura({(3, 3): "P"}))
    assert t.limpar(3, 3)
    assert t.casa(3, 3).simbolo is None
    assert t.casa(3, 3).corrigida


def test_mover_leva_a_peca_e_esvazia_a_origem():
    t = TabuleiroEdicao(_leitura({(3, 3): "N"}))
    assert t.mover((3, 3), (5, 5))
    assert t.casa(3, 3).simbolo is None
    assert t.casa(5, 5).simbolo == "N"
    assert t.casa(3, 3).corrigida and t.casa(5, 5).corrigida


def test_mover_de_casa_vazia_nao_faz_nada():
    t = TabuleiroEdicao(_leitura({(3, 3): "N"}))
    assert not t.mover((0, 0), (5, 5))
    assert t.casa(5, 5).simbolo is None


def test_mover_para_casa_ocupada_substitui():
    t = TabuleiroEdicao(_leitura({(3, 3): "N", (5, 5): "p"}))
    t.mover((3, 3), (5, 5))
    assert t.casa(5, 5).simbolo == "N"


# ----------------------------------------------------------------------
# Desfazer
# ----------------------------------------------------------------------

def test_desfazer_devolve_a_peca_e_a_marca():
    t = TabuleiroEdicao(_leitura({(3, 3): "P"}))
    t.colocar(3, 3, "B")
    assert t.desfazer()
    assert t.casa(3, 3).simbolo == "P"
    assert not t.casa(3, 3).corrigida


def test_refazer_refaz():
    t = TabuleiroEdicao(_leitura({(3, 3): "P"}))
    t.colocar(3, 3, "B")
    t.desfazer()
    assert t.refazer()
    assert t.casa(3, 3).simbolo == "B"


def test_desfazer_no_comeco_nao_faz_nada():
    t = TabuleiroEdicao(_leitura({(3, 3): "P"}))
    assert not t.pode_desfazer
    assert not t.desfazer()


def test_editar_depois_de_desfazer_descarta_o_refazer():
    t = TabuleiroEdicao(_leitura({(3, 3): "P"}))
    t.colocar(3, 3, "B")
    t.desfazer()
    t.colocar(4, 4, "N")
    assert not t.pode_refazer


def test_desfazer_cobre_o_lado_e_o_roque():
    """O desfazer é do estado inteiro, não só das casas."""
    t = TabuleiroEdicao(_leitura(dict(REIS)))
    t.definir_lado("b")
    assert t.desfazer()
    assert t.lado == "w" and not t.lado_informado


def test_desfazer_de_um_movimento_e_um_so():
    t = TabuleiroEdicao(_leitura({(3, 3): "N"}))
    t.mover((3, 3), (5, 5))
    t.desfazer()
    assert t.casa(3, 3).simbolo == "N" and t.casa(5, 5).simbolo is None


# ----------------------------------------------------------------------
# O FEN, o lado e o roque
# ----------------------------------------------------------------------

def test_o_fen_acompanha_a_edicao():
    t = TabuleiroEdicao(_leitura(dict(REIS)))
    antes = t.fen()
    t.colocar(4, 4, "Q")
    assert t.fen() != antes
    assert t.fen().split()[0].count("Q") == 1


def test_o_fen_de_partida_e_o_da_leitura():
    """Sem edição, a janela não pode mudar o que a F7.1 entregava."""
    leitura = _leitura(dict(REIS))
    assert TabuleiroEdicao(leitura).fen() == leitura.fen()


def test_o_lado_a_jogar_entra_no_fen():
    t = TabuleiroEdicao(_leitura(dict(REIS)))
    assert t.fen().split()[1] == "w"
    t.definir_lado("b")
    assert t.fen().split()[1] == "b"


def test_lado_invalido_e_recusado():
    t = TabuleiroEdicao(_leitura(dict(REIS)))
    assert not t.definir_lado("x")
    assert t.lado == "w"


def test_roque_so_e_possivel_com_rei_e_torre_no_lugar():
    t = TabuleiroEdicao(_leitura(dict(REIS)))
    assert t.roques_possiveis() == ""
    t.colocar(7, 7, "R")
    assert t.roques_possiveis() == "K"
    t.colocar(7, 0, "R")
    assert set(t.roques_possiveis()) == {"K", "Q"}


def test_roque_impossivel_nao_entra():
    """
    Marcar e ver o FEN sair com '-' seria pior que não oferecer.

    O `python-chess` derruba o direito na hora de escrever; então quem filtra
    é este módulo, antes de guardar.
    """
    t = TabuleiroEdicao(_leitura(dict(REIS)))
    assert not t.definir_roque("KQkq")
    assert t.roque == ""
    assert t.fen().split()[2] == "-"


def test_alternar_roque_liga_e_desliga():
    t = TabuleiroEdicao(_leitura({**REIS, (7, 7): "R"}))
    assert t.alternar_roque("K")
    assert t.fen().split()[2] == "K"
    assert t.alternar_roque("K")
    assert t.fen().split()[2] == "-"


def test_tirar_a_torre_derruba_o_roque_do_fen():
    t = TabuleiroEdicao(_leitura({**REIS, (7, 7): "R"}))
    t.alternar_roque("K")
    t.limpar(7, 7)
    assert t.fen().split()[2] == "-"


# ----------------------------------------------------------------------
# A legalidade, agora que alguém pode responder
# ----------------------------------------------------------------------

def test_posicao_legal_nao_tem_problema():
    t = TabuleiroEdicao(_leitura(dict(REIS)))
    assert t.problemas() == []
    assert t.plausivel


def test_sem_rei_o_problema_e_dito():
    t = TabuleiroEdicao(_leitura({(0, 4): "k"}))
    assert any("rei branco" in p for p in t.problemas())


def test_peao_na_ultima_fila_e_dito():
    t = TabuleiroEdicao(_leitura({**REIS, (0, 0): "P"}))
    assert any("fila" in p for p in t.problemas())


def test_dois_reis_da_mesma_cor():
    t = TabuleiroEdicao(_leitura({**REIS, (4, 4): "K"}))
    assert any("rei" in p for p in t.problemas())


def test_xeque_do_lado_errado_so_aparece_com_o_lado_informado():
    """
    O que a F7.1 não tinha como saber, e esta fase passa a saber.

    Com a torre branca dando xeque ao rei preto e as brancas a jogar, a
    posição é impossível: as pretas teriam deixado o rei em xeque.
    """
    t = TabuleiroEdicao(_leitura({**REIS, (0, 0): "R"}))
    assert any("xeque" in p for p in t.problemas())
    t.definir_lado("b")
    assert not any("xeque" in p for p in t.problemas())


def test_plausivel_e_mais_exigente_que_o_da_leitura():
    """A contagem da F7.1 aprova; a checagem inteira não."""
    leitura = _leitura({**REIS, (0, 0): "R"})
    assert leitura.plausivel
    assert not TabuleiroEdicao(leitura).plausivel


# ----------------------------------------------------------------------
# O que o usuário informou não vira leitura
# ----------------------------------------------------------------------

def test_sem_informar_nada_o_aviso_e_o_da_convencao():
    t = TabuleiroEdicao(_leitura(dict(REIS)))
    assert AVISO_CONVENCAO in t.avisos()


def test_depois_de_informar_o_aviso_muda():
    t = TabuleiroEdicao(_leitura(dict(REIS)))
    t.definir_lado("b")
    aviso = " ".join(t.avisos())
    assert AVISO_CONVENCAO not in aviso
    assert "veio de quem editou" in aviso


def test_o_aviso_de_impossivel_aparece():
    t = TabuleiroEdicao(_leitura({(0, 4): "k"}))
    assert any("impossível" in a for a in t.avisos())


def test_o_resumo_conta_as_correcoes():
    t = TabuleiroEdicao(_leitura({**REIS, (3, 3): "P"}))
    t.colocar(3, 3, "B")
    assert "1 corrigida" in t.resumo()


def test_correcoes_traz_so_o_que_a_mao_mexeu():
    t = TabuleiroEdicao(_leitura({**REIS, (3, 3): "P", (4, 4): "n"}))
    t.colocar(3, 3, "B")
    assert [(c.linha, c.coluna) for c in t.correcoes()] == [(3, 3)]


# ----------------------------------------------------------------------
# O diálogo
# ----------------------------------------------------------------------

def test_clicar_seleciona_e_nao_apaga():
    """
    Um clique que já mexesse na casa faria da conferência um campo minado.

    É a mesma prudência da F2.3, que pergunta antes de reescrever o PDF: o
    caminho barato tem de ser o que não estraga.
    """
    dlg, raiz = _dialogo()
    try:
        x, y = _ponto(7, 4)
        dlg._no_clique(_Evento(x=x, y=y))
        assert dlg.selecionada == (7, 4)
        assert dlg.tabuleiro().casa(7, 4).simbolo == "K"
        assert dlg.tabuleiro().corrigidas == 0
    finally:
        raiz.destroy()


def test_a_tecla_escreve_na_casa_selecionada():
    dlg, raiz = _dialogo()
    try:
        dlg._no_clique(_Evento(*_ponto(4, 4)))
        dlg._na_tecla(_Evento(char="Q"))
        assert dlg.tabuleiro().casa(4, 4).simbolo == "Q"
        dlg._na_tecla(_Evento(char="q"))
        assert dlg.tabuleiro().casa(4, 4).simbolo == "q"
    finally:
        raiz.destroy()


def test_a_tecla_sem_casa_selecionada_nao_faz_nada():
    dlg, raiz = _dialogo()
    try:
        dlg._na_tecla(_Evento(char="Q"))
        assert dlg.tabuleiro().corrigidas == 0
    finally:
        raiz.destroy()


def test_delete_esvazia_a_casa():
    dlg, raiz = _dialogo()
    try:
        dlg._no_clique(_Evento(*_ponto(7, 4)))
        dlg._na_tecla(_Evento(keysym="Delete"))
        assert dlg.tabuleiro().casa(7, 4).simbolo is None
    finally:
        raiz.destroy()


def test_o_pincel_da_paleta_pinta_ao_clicar():
    dlg, raiz = _dialogo()
    try:
        dlg._escolher("N")
        dlg._no_clique(_Evento(*_ponto(2, 2)))
        assert dlg.tabuleiro().casa(2, 2).simbolo == "N"
    finally:
        raiz.destroy()


def test_escolher_a_mesma_peca_volta_ao_modo_seguro():
    dlg, raiz = _dialogo()
    try:
        dlg._escolher("N")
        dlg._escolher("N")
        assert dlg.pincel is None
        dlg._no_clique(_Evento(*_ponto(2, 2)))
        assert dlg.tabuleiro().casa(2, 2).simbolo is None
    finally:
        raiz.destroy()


def test_clicar_de_novo_com_o_pincel_alterna_a_casa():
    """
    Pedido: com a peça escolhida, clicar na mesma casa alterna peça/vazia.

    É o que faz a paleta bastar para os dois movimentos da conferência —
    trocar a peça errada e apagar a que não existe — sem trocar de ferramenta
    no meio.
    """
    dlg, raiz = _dialogo()
    try:
        dlg._escolher("n")
        dlg._no_clique(_Evento(*_ponto(2, 2)))
        assert dlg.tabuleiro().casa(2, 2).simbolo == "n"
        dlg._no_clique(_Evento(*_ponto(2, 2)))
        assert dlg.tabuleiro().casa(2, 2).simbolo is None
        dlg._no_clique(_Evento(*_ponto(2, 2)))
        assert dlg.tabuleiro().casa(2, 2).simbolo == "n"
    finally:
        raiz.destroy()


def test_alternar_so_vale_para_a_peca_escolhida():
    """Casa com OUTRA peça é substituída, e não esvaziada."""
    dlg, raiz = _dialogo()
    try:
        dlg._escolher("n")
        dlg._no_clique(_Evento(*_ponto(7, 4)))          # tinha o rei branco
        assert dlg.tabuleiro().casa(7, 4).simbolo == "n"
    finally:
        raiz.destroy()


def test_a_borracha_nao_alterna():
    """Alternar exigiria uma peça para pôr de volta, e a borracha não tem."""
    dlg, raiz = _dialogo()
    try:
        dlg._escolher("")
        dlg._no_clique(_Evento(*_ponto(7, 4)))
        dlg._no_clique(_Evento(*_ponto(7, 4)))
        assert dlg.tabuleiro().casa(7, 4).simbolo is None
    finally:
        raiz.destroy()


def test_alternar_entra_no_desfazer_como_dois_passos():
    dlg, raiz = _dialogo()
    try:
        dlg._escolher("q")
        dlg._no_clique(_Evento(*_ponto(2, 2)))
        dlg._no_clique(_Evento(*_ponto(2, 2)))
        dlg._desfazer()
        assert dlg.tabuleiro().casa(2, 2).simbolo == "q"
    finally:
        raiz.destroy()


# ----------------------------------------------------------------------
# As figuras do livro, no lugar dos glifos da fonte
# ----------------------------------------------------------------------

def test_a_pasta_de_pecas_esta_completa():
    """Doze arquivos, um por peça — o tabuleiro é tudo ou nada."""
    from ui import pecas

    assert pecas.faltando() == []


def test_o_tabuleiro_desenha_as_figuras():
    dlg, raiz = _dialogo()
    try:
        tipos = [dlg.canvas.type(i) for i in dlg.canvas.find_all()]
        assert tipos.count("image") == 2      # os dois reis da posição
        assert "text" not in tipos            # nenhum glifo sobrou
    finally:
        raiz.destroy()


def test_a_paleta_usa_as_figuras():
    dlg, raiz = _dialogo()
    try:
        assert str(dlg.botoes_paleta["K"].cget("image"))
    finally:
        raiz.destroy()


def test_sem_a_pasta_o_tabuleiro_volta_aos_glifos_e_avisa(tmp_path, monkeypatch):
    """
    Uma janela que some com as peças porque um arquivo mudou de lugar é pior
    que uma janela feia — e o aviso na legenda custa menos que um modal.
    """
    from ui import pecas
    from ui.dialogo_diagrama import SEM_FIGURAS

    monkeypatch.setattr(pecas, "PASTA", str(tmp_path / "vazio"))
    dlg, raiz = _dialogo()
    try:
        assert dlg.figuras == {}
        tipos = [dlg.canvas.type(i) for i in dlg.canvas.find_all()]
        assert tipos.count("text") == 2
        assert SEM_FIGURAS in dlg.lbl_avisos.cget("text")
    finally:
        raiz.destroy()


def test_arquivo_de_peca_ilegivel_derruba_o_conjunto_inteiro(tmp_path, monkeypatch):
    """Dez figuras e dois glifos no meio confunde mais que doze glifos."""
    from ui import pecas

    pasta = tmp_path / "pieces"
    pasta.mkdir()
    for nome in pecas.ARQUIVOS.values():
        (pasta / nome).write_bytes(b"isto nao e um png")
    monkeypatch.setattr(pecas, "PASTA", str(pasta))
    dlg, raiz = _dialogo()
    try:
        assert dlg.figuras == {}
    finally:
        raiz.destroy()


def test_a_borracha_da_paleta_esvazia():
    dlg, raiz = _dialogo()
    try:
        dlg._escolher("")
        dlg._no_clique(_Evento(*_ponto(7, 4)))
        assert dlg.tabuleiro().casa(7, 4).simbolo is None
    finally:
        raiz.destroy()


def test_botao_direito_esvazia():
    dlg, raiz = _dialogo()
    try:
        dlg._no_direito(_Evento(*_ponto(7, 4)))
        assert dlg.tabuleiro().casa(7, 4).simbolo is None
    finally:
        raiz.destroy()


def test_arrastar_move_a_peca():
    dlg, raiz = _dialogo()
    try:
        dlg._no_clique(_Evento(*_ponto(7, 4)))
        dlg._no_solta(_Evento(*_ponto(5, 4)))
        assert dlg.tabuleiro().casa(7, 4).simbolo is None
        assert dlg.tabuleiro().casa(5, 4).simbolo == "K"
    finally:
        raiz.destroy()


def test_soltar_na_mesma_casa_nao_move():
    dlg, raiz = _dialogo()
    try:
        dlg._no_clique(_Evento(*_ponto(7, 4)))
        dlg._no_solta(_Evento(*_ponto(7, 4)))
        assert dlg.tabuleiro().casa(7, 4).simbolo == "K"
    finally:
        raiz.destroy()


def test_o_fen_da_janela_acompanha_a_edicao():
    dlg, raiz = _dialogo()
    try:
        antes = dlg.var_fen.get()
        dlg._no_clique(_Evento(*_ponto(4, 4)))
        dlg._na_tecla(_Evento(char="Q"))
        assert dlg.var_fen.get() != antes
        dlg._confirmar()
        assert "Q" in dlg.resultado.split()[0]
    finally:
        raiz.destroy()


def test_a_correcao_sobrevive_a_troca_de_diagrama():
    """
    Trocar de diagrama e voltar não pode desfazer o trabalho.

    É o mesmo compromisso da F3.7, em que sair da página e voltar preserva os
    boxes: o que o usuário fez não se perde por navegar.
    """
    dlg, raiz = _dialogo([_leitura(dict(REIS)), _leitura(dict(REIS))])
    try:
        dlg._no_clique(_Evento(*_ponto(4, 4)))
        dlg._na_tecla(_Evento(char="Q"))
        dlg._ir(1)
        assert dlg.tabuleiro().casa(4, 4).simbolo is None
        dlg._ir(-1)
        assert dlg.tabuleiro().casa(4, 4).simbolo == "Q"
    finally:
        raiz.destroy()


def test_a_selecao_nao_atravessa_diagramas():
    dlg, raiz = _dialogo([_leitura(dict(REIS)), _leitura(dict(REIS))])
    try:
        dlg._no_clique(_Evento(*_ponto(4, 4)))
        dlg._ir(1)
        assert dlg.selecionada is None
    finally:
        raiz.destroy()


def test_desfazer_pelo_botao():
    dlg, raiz = _dialogo()
    try:
        dlg._no_clique(_Evento(*_ponto(4, 4)))
        dlg._na_tecla(_Evento(char="Q"))
        dlg._desfazer()
        assert dlg.tabuleiro().casa(4, 4).simbolo is None
        assert str(dlg.btn_desfazer.cget("state")) == "disabled"
    finally:
        raiz.destroy()


def test_a_legenda_explica_o_verde():
    dlg, raiz = _dialogo()
    try:
        dlg._no_clique(_Evento(*_ponto(4, 4)))
        dlg._na_tecla(_Evento(char="Q"))
        assert "verde" in dlg.lbl_avisos.cget("text")
    finally:
        raiz.destroy()


def test_o_roque_impossivel_fica_desabilitado():
    dlg, raiz = _dialogo()
    try:
        assert str(dlg.checks_roque["K"].cget("state")) == "disabled"
        dlg._no_clique(_Evento(*_ponto(7, 7)))
        dlg._na_tecla(_Evento(char="R"))
        assert str(dlg.checks_roque["K"].cget("state")) == "normal"
    finally:
        raiz.destroy()


def test_o_lado_a_jogar_da_janela_entra_no_fen():
    dlg, raiz = _dialogo()
    try:
        dlg.var_lado.set("b")
        dlg._mudar_lado()
        assert dlg.var_fen.get().split()[1] == "b"
    finally:
        raiz.destroy()


def test_ctrl_com_letra_nao_escreve_na_casa():
    """Ctrl+Z é desfazer; sem esta guarda ele também escreveria um 'z' preto."""
    dlg, raiz = _dialogo()
    try:
        dlg._no_clique(_Evento(*_ponto(4, 4)))
        dlg._na_tecla(_Evento(char="z", state=0x4))
        assert dlg.tabuleiro().casa(4, 4).simbolo is None
    finally:
        raiz.destroy()


# ----------------------------------------------------------------------
# O botão na janela principal
# ----------------------------------------------------------------------

def test_o_botao_de_diagramas_existe_e_chama_a_leitura():
    """
    Pedido explicitamente: o caminho não podia ser só o menu.

    Ler diagrama é ação de página, e Ferramentas guarda configuração — quem
    não sabia que existia não encontrava.

    O teste aperta o botão de verdade e confere onde ele chega, em vez de
    trocar `extrair_diagramas` por um dublê: o `command` é ligado ao método
    na construção, então trocar o atributo depois não trocaria nada — o botão
    seguiria chamando o original e o teste passaria sem provar coisa alguma.
    """
    import tkinter as tk
    from tkinter import messagebox
    from conftest import raiz_tk
    from ui.main_window import MainWindow

    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")

    # Sem isto o `invoke` abre um showinfo modal e a suíte trava esperando um
    # clique que não vem. É o cuidado que o `_App` da F3.6 já tomava.
    mostrados, original = [], messagebox.showinfo
    messagebox.showinfo = lambda titulo, texto, *a, **k: mostrados.append(
        (titulo, texto))
    win = None
    try:
        win = MainWindow(raiz)
        assert isinstance(win.btn_diagramas, tk.Button)
        win.btn_diagramas.invoke()
        assert mostrados and mostrados[0][0] == "Diagramas"
    finally:
        messagebox.showinfo = original
        # A thread de trabalho da janela não é daemon.
        if win is not None:
            try:
                win.task.shutdown()
            except Exception:
                pass
        raiz.destroy()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
