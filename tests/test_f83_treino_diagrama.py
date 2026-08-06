"""
F8.3 — a correção do tabuleiro vira amostra, e o modelo retreina.

O risco desta fase é o da F1.4, e ele é o pior tipo: **estragar a base sem
sintoma**. Amostra errada não levanta exceção, não aparece na tela e não some
sozinha — ela vira modelo, e o modelo vira leitura errada meses depois. Foi
assim que 127 amostras rotuladas como '?' treinaram a classe errada por meses.

Daí a maior parte destes testes ser sobre o que **não** deve entrar na base:
casa que ninguém tocou sem o gesto explícito, casa esvaziada (que não tem classe
onde ser aprendida), e o mesmo desenho em duas classes depois de uma segunda
correção.

Rodar sem pytest:      python tests/test_f83_treino_diagrama.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
import pytest

from core import diagrama, treino_diagrama
from core.diagrama import LADO, Casa, Leitura
from core.tabuleiro_edicao import TabuleiroEdicao


# ----------------------------------------------------------------------
# Apoio
# ----------------------------------------------------------------------

def _residuo(valor=60, lado=LADO):
    """Um resíduo qualquer, com uma marca que o distingue dos outros."""
    r = np.zeros((lado, lado), np.float32)
    r[lado // 4:3 * lado // 4, lado // 4:3 * lado // 4] = valor
    return r


def _leitura(pecas=None, caixa=(0, 0, 320, 320)) -> Leitura:
    pecas = pecas or {}
    leitura = Leitura(caixa=caixa)
    leitura.casas = [Casa(r, c, pecas.get((r, c)), 0.9)
                     for r in range(8) for c in range(8)]
    return leitura


def _tabuleiro_sintetico(pecas=(), lado=320):
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


def _base(tmp_path, amostras):
    """
    Monta uma base: {simbolo: [resíduos]}. Devolve o caminho.

    A procedência muda com o símbolo de propósito. Na produção ela carrega
    página, diagrama e casa, então duas classes nunca compartilham nome —
    e `gravar` conta com isso para apagar o rótulo desmentido. Com a
    procedência repetida entre classes, cada classe apagaria a anterior (foi
    o que a primeira versão deste apoio fez, e os testes pegaram).
    """
    pasta = str(tmp_path / "diagramas")
    for simbolo, residuos in amostras.items():
        for i, r in enumerate(residuos):
            treino_diagrama.gravar(r, simbolo, origem=f"teste_{simbolo}_{i}",
                                   casa="a1", pasta=pasta)
    return pasta


def _familia(simbolo, n, semente):
    """`n` resíduos parecidos entre si e diferentes dos de outra família."""
    return [_residuo(semente) + np.random.RandomState(semente + i).normal(
        0, 1.0, (LADO, LADO)).astype(np.float32) for i in range(n)]


# ----------------------------------------------------------------------
# A amostra é o resíduo
# ----------------------------------------------------------------------

def test_gravar_e_carregar_devolve_o_residuo(tmp_path):
    """Ida e volta pelo disco: o que sai é o que entrou, dentro do arredondamento."""
    pasta = str(tmp_path / "d")
    r = _residuo(40)
    treino_diagrama.gravar(r, "B", origem="pag1", casa="c1", pasta=pasta)
    amostras = treino_diagrama.carregar_amostras(pasta)
    assert len(amostras) == 1
    simbolo, voltou, _ = amostras[0]
    assert simbolo == "B"
    assert np.abs(voltou - r).max() <= 1.0


def test_a_amostra_vai_para_a_pasta_da_cor(tmp_path):
    pasta = str(tmp_path / "d")
    treino_diagrama.gravar(_residuo(), "B", "p", "c1", pasta)
    treino_diagrama.gravar(_residuo(), "b", "p", "c8", pasta)
    assert os.path.isdir(os.path.join(pasta, "branca", "B"))
    assert os.path.isdir(os.path.join(pasta, "preta", "B"))


def test_simbolo_que_nao_e_peca_nao_grava(tmp_path):
    pasta = str(tmp_path / "d")
    assert treino_diagrama.gravar(_residuo(), "X", "p", "c1", pasta) is None
    assert treino_diagrama.carregar_amostras(pasta) == []


def test_o_nome_e_deterministico(tmp_path):
    """Conferir o mesmo diagrama duas vezes regrava, não duplica."""
    pasta = str(tmp_path / "d")
    treino_diagrama.gravar(_residuo(), "R", "pag1_d1", "h1", pasta)
    treino_diagrama.gravar(_residuo(30), "R", "pag1_d1", "h1", pasta)
    assert len(treino_diagrama.carregar_amostras(pasta)) == 1


def test_procedencias_diferentes_nao_colidem(tmp_path):
    """
    Duas páginas de nome parecido não podem apagar as amostras uma da outra.

    O nome é truncado para não ficar impossível, e é por isso que ele leva uma
    marca curta da procedência inteira.
    """
    pasta = str(tmp_path / "d")
    longo = "livro_muito_comprido_com_nome_que_nao_cabe_no_arquivo"
    treino_diagrama.gravar(_residuo(), "R", longo + "_pagina_0001", "h1", pasta)
    treino_diagrama.gravar(_residuo(), "R", longo + "_pagina_0002", "h1", pasta)
    assert len(treino_diagrama.carregar_amostras(pasta)) == 2


def test_corrigir_de_novo_nao_deixa_o_rotulo_antigo(tmp_path):
    """
    O defeito da F1.4, na forma em que esta fase poderia criá-lo.

    Casa corrigida para bispo e depois para cavalo: sem apagar a primeira, a
    mesma imagem ficaria rotulada das duas maneiras, e o treino aprenderia as
    duas.
    """
    pasta = str(tmp_path / "d")
    treino_diagrama.gravar(_residuo(), "B", "pag1_d1", "c1", pasta)
    treino_diagrama.gravar(_residuo(), "N", "pag1_d1", "c1", pasta)
    amostras = treino_diagrama.carregar_amostras(pasta)
    assert [s for s, _, _ in amostras] == ["N"]


# ----------------------------------------------------------------------
# Silêncio não é confirmação
# ----------------------------------------------------------------------

def _colheita(tmp_path, corrigir=None, tudo=False):
    pasta = str(tmp_path / "d")
    pecas = {(0, 4): "k", (7, 4): "K", (3, 3): "P"}
    imagem = _tabuleiro_sintetico(pecas.keys())
    leitura = _leitura(pecas)
    tabuleiro = TabuleiroEdicao(leitura)
    if corrigir:
        for (linha, coluna), simbolo in corrigir.items():
            tabuleiro.colocar(linha, coluna, simbolo)
    caminhos = treino_diagrama.colher(imagem, leitura, tabuleiro,
                                      origem="pag1", tudo=tudo, pasta=pasta)
    return pasta, caminhos


def test_sem_correcao_e_sem_conferir_nao_guarda_nada(tmp_path):
    """
    O centro desta fase: casa que ninguém tocou não vira amostra.

    Sem isso a base cresceria enviesada para o que o modelo já acerta — as
    casas que ele erra são exatamente as que o usuário mexe.
    """
    _, caminhos = _colheita(tmp_path)
    assert caminhos == []


def test_so_a_correcao_vira_amostra(tmp_path):
    pasta, caminhos = _colheita(tmp_path, corrigir={(3, 3): "B"})
    assert len(caminhos) == 1
    assert [s for s, _, _ in treino_diagrama.carregar_amostras(pasta)] == ["B"]


def test_conferir_o_diagrama_inteiro_guarda_as_ocupadas(tmp_path):
    pasta, caminhos = _colheita(tmp_path, tudo=True)
    assert len(caminhos) == 3
    assert sorted(s for s, _, _ in treino_diagrama.carregar_amostras(pasta)) == \
        ["K", "P", "k"]


def test_casa_esvaziada_nao_vira_amostra(tmp_path):
    """
    Não é esquecimento: o modelo tem 12 classes de peça e nenhuma de vazia.

    Quem decide vazia/ocupada é o limiar de Otsu da F7.1, antes do
    classificador. Corrigir um falso positivo conserta o FEN e não tem onde
    ser aprendido.
    """
    pasta, caminhos = _colheita(tmp_path, corrigir={(3, 3): None})
    assert caminhos == []


def test_a_amostra_colhida_e_o_residuo_e_nao_o_recorte(tmp_path):
    """
    Guardar a casa crua traria o papel do livro junto.

    O teste compara o que foi para o disco com o resíduo que o próprio
    `diagrama` calcula para aquela casa — tem de ser o mesmo.
    """
    pasta, caminhos = _colheita(tmp_path, corrigir={(3, 3): "B"})
    guardado = cv2.imread(caminhos[0], cv2.IMREAD_GRAYSCALE).astype(np.float32) - 128.0

    pecas = {(0, 4): "k", (7, 4): "K", (3, 3): "P"}
    residuos, _ = diagrama.residuos(_tabuleiro_sintetico(pecas.keys()),
                                    (0, 0, 320, 320))
    esperado = residuos[(3, 3)]
    assert np.abs(guardado - np.clip(esperado, -128, 127)).max() <= 1.5


# ----------------------------------------------------------------------
# Conferir a base
# ----------------------------------------------------------------------

def test_base_sadia_nao_acusa_nada_grave(tmp_path):
    pasta = _base(tmp_path, {s: _familia(s, 12, i * 7 + 3)
                             for i, s in enumerate("PNBRQKpnbrqk")})
    assert [p for p in treino_diagrama.conferir(pasta) if p.grave] == []


def test_imagem_igual_em_duas_classes_e_erro_grave(tmp_path):
    """
    Aqui é erro, e na base de caracteres era aviso — a diferença é de domínio.

    A F7.2 concluiu que '1' e 'l' podem virar o mesmo desenho e os dois
    rótulos estarem certos para ocorrências diferentes. Num diagrama não há
    esse contexto: um bispo é um bispo.
    """
    pasta = str(tmp_path / "d")
    r = _residuo(50)
    treino_diagrama.gravar(r, "B", "a", "c1", pasta)
    treino_diagrama.gravar(r, "N", "b", "c1", pasta)
    graves = [p for p in treino_diagrama.conferir(pasta) if p.grave]
    assert graves and graves[0].tipo == "rotulo_contraditorio"


def test_classe_magra_e_so_aviso(tmp_path):
    pasta = _base(tmp_path, {"B": _familia("B", 3, 5)})
    problemas = treino_diagrama.conferir(pasta)
    assert any(p.tipo == "classe_magra" for p in problemas)
    assert not any(p.grave for p in problemas)


def test_classe_vazia_e_so_aviso(tmp_path):
    pasta = _base(tmp_path, {"B": _familia("B", 12, 5)})
    assert any(p.tipo == "classe_vazia" for p in treino_diagrama.conferir(pasta))
    assert not any(p.grave for p in treino_diagrama.conferir(pasta))


def test_base_vazia_nao_quebra(tmp_path):
    assert treino_diagrama.carregar_amostras(str(tmp_path / "nada")) == []
    assert treino_diagrama.contagem(str(tmp_path / "nada")) == {
        s: 0 for s in diagrama.SIMBOLOS}


# ----------------------------------------------------------------------
# O treino
# ----------------------------------------------------------------------

def test_treinar_grava_o_modelo(tmp_path):
    pasta = _base(tmp_path, {s: _familia(s, 6, i * 11 + 2)
                             for i, s in enumerate("PNBRQK")})
    destino = str(tmp_path / "modelo.npz")
    relatorio = treino_diagrama.treinar(pasta, destino)
    assert os.path.isfile(destino)
    assert relatorio.total == 36
    assert relatorio.contagem["P"] == 6


def test_base_vazia_nao_grava_modelo(tmp_path):
    destino = str(tmp_path / "modelo.npz")
    relatorio = treino_diagrama.treinar(str(tmp_path / "nada"), destino)
    assert relatorio.total == 0
    assert not os.path.isfile(destino)


def test_o_modelo_treinado_e_lido_pelo_leitor(tmp_path):
    """O `.npz` novo tem de servir para `core/diagrama`, e não só para o treino."""
    pasta = _base(tmp_path, {s: _familia(s, 6, i * 11 + 2)
                             for i, s in enumerate("PNBRQK")})
    destino = str(tmp_path / "modelo.npz")
    treino_diagrama.treinar(pasta, destino)

    d = np.load(destino, allow_pickle=False)
    assert set(["media", "base", "amostras", "simbolos"]) <= set(d.files)
    assert d["amostras"].shape[0] == 36
    assert d["base"].shape[0] == treino_diagrama.COMPONENTES


def test_o_leave_one_out_separa_familias(tmp_path):
    """Famílias bem distintas têm de dar acerto alto; é o piso de sanidade."""
    pasta = _base(tmp_path, {s: _familia(s, 8, i * 40 + 10)
                             for i, s in enumerate("PNBR")})
    relatorio = treino_diagrama.treinar(pasta, str(tmp_path / "m.npz"))
    assert relatorio.acerto > 0.8
    assert set(relatorio.acerto_por_classe) == set("PNBR")


def test_o_relatorio_avisa_das_classes_magras(tmp_path):
    pasta = _base(tmp_path, {"P": _familia("P", 12, 3), "N": _familia("N", 4, 90)})
    relatorio = treino_diagrama.treinar(pasta, str(tmp_path / "m.npz"))
    assert "N" in relatorio.magras and "P" not in relatorio.magras
    assert "leave-one-out" in relatorio.texto()


def test_o_relatorio_avisa_que_uma_correcao_nao_vira_uma_casa(tmp_path):
    """
    Sem este aviso o usuário corrige, retreina, relê e conclui que não funciona.

    Medido numa página real: a amostra nova vira o vizinho mais próximo
    (0,990) e mesmo assim perde para dois vizinhos antigos (1,876), porque o
    voto soma os três. Com duas correções parecidas, vira.
    """
    pasta = _base(tmp_path, {s: _familia(s, 6, i * 11 + 2)
                             for i, s in enumerate("PNBR")})
    texto = treino_diagrama.treinar(pasta, str(tmp_path / "m.npz")).texto()
    assert "3 vizinhos" in texto and "duas viram" in texto


def test_o_relatorio_diz_que_o_numero_e_otimista(tmp_path):
    """
    O número não pode passar por promessa de acerto em livro novo.

    É a lição da F1.3: a acurácia que não diz em que dados foi medida vale
    zero, e a que engana é pior que a que falta.
    """
    pasta = _base(tmp_path, {s: _familia(s, 6, i * 11 + 2)
                             for i, s in enumerate("PNBR")})
    texto = treino_diagrama.treinar(pasta, str(tmp_path / "m.npz")).texto()
    assert "otimista" in texto


def test_a_avaliacao_usa_o_mesmo_voto_da_leitura(tmp_path):
    """
    Medir com outro critério mediria outro classificador.

    Duas amostras iguais de classes diferentes: o voto de 3 vizinhos não tem
    como acertar as duas, e o acerto tem de cair — se subisse, a avaliação
    estaria usando outra regra.
    """
    reduzido = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.0, 1.0]],
                        np.float32)
    acerto, _ = treino_diagrama.avaliar(reduzido, ["P", "P", "N", "N"])
    assert acerto == 1.0
    acerto_ruim, _ = treino_diagrama.avaliar(reduzido, ["P", "N", "P", "N"])
    assert acerto_ruim < 1.0


# ----------------------------------------------------------------------
# O modelo não se descasa da base (F7.3 aplicada aqui)
# ----------------------------------------------------------------------

def test_a_impressao_muda_quando_a_base_muda(tmp_path):
    pasta = _base(tmp_path, {"P": _familia("P", 4, 3)})
    antes = treino_diagrama.impressao(pasta)
    treino_diagrama.gravar(_residuo(70), "P", "nova", "d4", pasta)
    assert treino_diagrama.impressao(pasta) != antes


def test_o_modelo_guarda_a_impressao_da_base(tmp_path):
    pasta = _base(tmp_path, {s: _familia(s, 6, i * 11 + 2)
                             for i, s in enumerate("PNBR")})
    destino = str(tmp_path / "m.npz")
    treino_diagrama.treinar(pasta, destino)
    d = np.load(destino, allow_pickle=False)
    assert str(d["impressao"]) == treino_diagrama.impressao(pasta)
    assert str(d["treinado_em"])


def test_modelo_desatualizado_pega_a_amostra_nova(tmp_path, monkeypatch):
    """
    Acrescentar amostra e esquecer de treinar é indistinguível de ter treinado.

    É o defeito da F7.3 nesta base: nada levanta, e o programa segue lendo com
    o banco velho.
    """
    pasta = _base(tmp_path, {s: _familia(s, 6, i * 11 + 2)
                             for i, s in enumerate("PNBR")})
    destino = str(tmp_path / "m.npz")
    monkeypatch.setattr(diagrama, "CAMINHO_MODELO", destino)
    treino_diagrama.treinar(pasta, destino)
    assert not treino_diagrama.modelo_desatualizado(pasta)

    treino_diagrama.gravar(_residuo(80), "P", "nova", "d4", pasta)
    assert treino_diagrama.modelo_desatualizado(pasta)


def test_modelo_sem_impressao_nao_e_dado_como_desatualizado(tmp_path, monkeypatch):
    """Modelo anterior a esta fase carrega e não acusa nada — como na F7.3."""
    destino = str(tmp_path / "velho.npz")
    np.savez_compressed(destino, media=np.zeros(3, np.float32),
                        base=np.zeros((1, 3), np.float32),
                        amostras=np.zeros((1, 1), np.float32),
                        simbolos=np.array(["P"]))
    monkeypatch.setattr(diagrama, "CAMINHO_MODELO", destino)
    assert not treino_diagrama.modelo_desatualizado(str(tmp_path / "d"))


def test_treinar_faz_o_leitor_esquecer_o_modelo_em_memoria(tmp_path, monkeypatch):
    """
    Sem isto, treinar sem fechar o programa não mudaria nada, em silêncio.

    O `.npz` novo ficaria no disco e as leituras seguintes continuariam com o
    banco velho até alguém reiniciar.
    """
    pasta = _base(tmp_path, {s: _familia(s, 6, i * 11 + 2)
                             for i, s in enumerate("PNBR")})
    destino = str(tmp_path / "m.npz")
    monkeypatch.setattr(diagrama, "CAMINHO_MODELO", destino)
    diagrama._modelo = ("velho",)
    treino_diagrama.treinar(pasta, destino)
    assert diagrama._modelo is None


# ----------------------------------------------------------------------
# A janela: o gesto explícito
# ----------------------------------------------------------------------

def _dialogo(tmp_path, leituras=None):
    from PIL import Image
    from conftest import raiz_tk
    from ui.dialogo_diagrama import DialogoDiagrama

    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    pecas = {(0, 4): "k", (7, 4): "K", (3, 3): "P"}
    leituras = leituras or [_leitura(pecas)]
    arr = _tabuleiro_sintetico(pecas.keys())
    dlg = DialogoDiagrama(raiz, Image.fromarray(arr), leituras, origem="pag1")
    dlg.construir()
    return dlg, raiz


def test_o_botao_de_amostras_comeca_desligado(tmp_path):
    dlg, raiz = _dialogo(tmp_path)
    try:
        assert str(dlg.btn_amostras.cget("state")) == "disabled"
    finally:
        raiz.destroy()


def test_corrigir_liga_o_botao_de_amostras(tmp_path):
    from ui.dialogo_diagrama import LADO_CASA
    dlg, raiz = _dialogo(tmp_path)
    try:
        dlg._no_clique(type("E", (), {"x": 3 * LADO_CASA + 5,
                                      "y": 3 * LADO_CASA + 5})())
        dlg._na_tecla(type("E", (), {"char": "B", "keysym": "B", "state": 0})())
        assert str(dlg.btn_amostras.cget("state")) == "normal"
    finally:
        raiz.destroy()


def test_marcar_conferido_liga_o_botao_sem_correcao(tmp_path):
    dlg, raiz = _dialogo(tmp_path)
    try:
        dlg.var_conferido.set(True)
        dlg._desenhar()
        assert str(dlg.btn_amostras.cget("state")) == "normal"
    finally:
        raiz.destroy()


def test_guardar_pela_janela_grava_na_base(tmp_path, monkeypatch):
    pasta = str(tmp_path / "base")
    monkeypatch.setattr(treino_diagrama, "PASTA_PADRAO", pasta)
    dlg, raiz = _dialogo(tmp_path)
    try:
        dlg.var_conferido.set(True)
        dlg._guardar_amostras()
        assert dlg.guardadas[0] == 3
        assert len(treino_diagrama.carregar_amostras(pasta)) == 3
        assert "3 amostra" in dlg.lbl_amostras.cget("text")
    finally:
        raiz.destroy()


def test_a_procedencia_leva_pagina_diagrama_e_caixa(tmp_path):
    dlg, raiz = _dialogo(tmp_path)
    try:
        procedencia = dlg.procedencia()
        assert "pag1" in procedencia and "_d1_" in procedencia
        assert "0-0-320-320" in procedencia
    finally:
        raiz.destroy()


def test_conferido_nao_atravessa_diagramas(tmp_path):
    """O gesto vale para o diagrama que estava na tela, e não para o próximo."""
    pecas = {(0, 4): "k", (7, 4): "K"}
    dlg, raiz = _dialogo(tmp_path, [_leitura(pecas), _leitura(pecas)])
    try:
        dlg.var_conferido.set(True)
        dlg._ir(1)
        assert not dlg.var_conferido.get()
        assert str(dlg.btn_amostras.cget("state")) == "disabled"
    finally:
        raiz.destroy()


def test_falha_ao_gravar_nao_derruba_a_janela(tmp_path, monkeypatch):
    def explodir(*a, **k):
        raise OSError("disco cheio")

    monkeypatch.setattr(treino_diagrama, "colher", explodir)
    dlg, raiz = _dialogo(tmp_path)
    try:
        dlg.var_conferido.set(True)
        dlg._guardar_amostras()
        assert "não deu para guardar" in dlg.lbl_amostras.cget("text")
    finally:
        raiz.destroy()


# ----------------------------------------------------------------------
# O comando na janela principal
# ----------------------------------------------------------------------

def test_o_menu_tem_o_treino_de_diagramas():
    import tkinter as tk
    from tkinter import messagebox
    from conftest import raiz_tk
    from ui.main_window import MainWindow

    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    salvos = (messagebox.showinfo, messagebox.showerror)
    messagebox.showinfo = lambda *a, **k: None
    messagebox.showerror = lambda *a, **k: None
    win = None
    try:
        win = MainWindow(raiz)
        menubar = raiz.nametowidget(raiz.cget("menu"))
        for i in range(menubar.index("end") + 1):
            if menubar.type(i) != "cascade":
                continue
            sub = raiz.nametowidget(menubar.entrycget(i, "menu"))
            rotulos = [sub.entrycget(j, "label")
                       for j in range(sub.index("end") + 1)
                       if sub.type(j) == "command"]
            if "Ler posição dos diagramas..." in rotulos:
                assert "Treinar modelo de diagramas..." in rotulos
                return
        raise AssertionError("menu Ferramentas não encontrado")
    finally:
        messagebox.showinfo, messagebox.showerror = salvos
        if win is not None:
            try:
                win.task.shutdown()
            except Exception:
                pass
        raiz.destroy()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
