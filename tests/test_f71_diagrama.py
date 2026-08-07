"""
F7.1 — do diagrama impresso para uma posição.

O risco desta fase é o mesmo da F6.1, e maior: **uma posição errada que parece
certa.** Um FEN abre em qualquer programa de xadrez e vira fato; ninguém confere
64 casas. Medido, a leitura acerta 94,5% das casas — isto é, ~3,5 casas erradas
por diagrama. Então a maior parte destes testes é sobre o módulo **admitir** o
que não sabe: avisar do que não está no diagrama, marcar o que a legalidade
mexeu, e dizer quando a posição continua impossível.

Rodar sem pytest:      python tests/test_f71_diagrama.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess
import numpy as np
import pytest

from core import diagrama
from core.box_model import BoxEntry
from core.diagrama import Casa, Leitura

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ----------------------------------------------------------------------
# Achar o diagrama na página
# ----------------------------------------------------------------------

def _pagina_de_texto(n=60):
    """Boxes de caractere: ~19 px, como nas páginas medidas."""
    return [BoxEntry("a", (i % 20) * 22, (i // 20) * 30,
                     (i % 20) * 22 + 14, (i // 20) * 30 + 19) for i in range(n)]


def test_acha_o_tabuleiro():
    boxes = _pagina_de_texto()
    boxes.append(BoxEntry("", 100, 200, 580, 679))          # 480x479
    assert diagrama.localizar(boxes) == [(100, 200, 580, 679)]


def test_travessao_nao_e_tabuleiro():
    """Ele também é descartado por tamanho, e não é quadrado."""
    boxes = _pagina_de_texto()
    boxes.append(BoxEntry("", 10, 10, 500, 30))
    assert diagrama.localizar(boxes) == []


def test_coluna_alta_e_estreita_nao_e_tabuleiro():
    boxes = _pagina_de_texto()
    boxes.append(BoxEntry("", 10, 10, 40, 500))
    assert diagrama.localizar(boxes) == []


def test_caractere_grande_nao_e_tabuleiro():
    """Quadrado mas pequeno: uma capitular não é diagrama."""
    boxes = _pagina_de_texto()
    boxes.append(BoxEntry("W", 10, 10, 60, 60))
    assert diagrama.localizar(boxes) == []


def test_dois_diagramas_saem_em_ordem_de_leitura():
    boxes = _pagina_de_texto()
    boxes.append(BoxEntry("", 100, 700, 580, 1179))
    boxes.append(BoxEntry("", 100, 100, 580, 579))
    assert [c[1] for c in diagrama.localizar(boxes)] == [100, 700]


def test_pagina_sem_boxes():
    assert diagrama.localizar([]) == []


def test_quase_quadrado_passa():
    """Os 25 medidos vão de 1,000 a 1,008 de proporção; a folga cobre o scan."""
    boxes = _pagina_de_texto()
    boxes.append(BoxEntry("", 0, 0, 480, 479))
    assert len(diagrama.localizar(boxes)) == 1


# ----------------------------------------------------------------------
# Leitura: a estrutura e o que ela promete
# ----------------------------------------------------------------------

def _leitura(pares, avisos=None):
    casas = {(r, c): Casa(r, c, s) for (r, c), s in pares.items()}
    todas = [casas.get((r, c)) or Casa(r, c, None)
             for r in range(8) for c in range(8)]
    return Leitura(caixa=(0, 0, 8, 8), casas=todas, avisos=avisos or [])


def test_nome_da_casa():
    assert Casa(0, 0, None).nome == "a8"
    assert Casa(7, 7, None).nome == "h1"
    assert Casa(6, 4, None).nome == "e2"


def test_tabuleiro_e_fen():
    L = _leitura({(0, 4): "k", (7, 4): "K", (6, 0): "P"})
    assert L.tabuleiro().piece_at(chess.E8) == chess.Piece.from_symbol("k")
    assert L.fen().startswith("4k3/8/8/8/8/8/P7/4K3")


def test_fen_declara_a_convencao():
    """O diagrama não diz de quem é a vez; o FEN precisa dizer algo."""
    L = _leitura({(0, 4): "k", (7, 4): "K"})
    assert L.fen().endswith(" w - - 0 1")


def test_o_aviso_da_convencao_e_obrigatorio():
    """Sem ele, a convenção passa por leitura."""
    im = np.full((160, 160), 250, np.uint8)
    L = diagrama.ler(im)
    assert any("não estão no diagrama" in a for a in L.avisos)


def test_ocupadas_ignora_as_vazias():
    L = _leitura({(0, 4): "k", (7, 4): "K"})
    assert len(L.casas) == 64
    assert len(L.ocupadas) == 2


# ----------------------------------------------------------------------
# As provas de contagem
# ----------------------------------------------------------------------

def test_posicao_com_dois_reis_e_plausivel():
    assert _leitura({(0, 4): "k", (7, 4): "K"}).plausivel


@pytest.mark.parametrize("pecas,motivo", [
    ({(0, 4): "k"}, "falta o rei branco"),
    ({(7, 4): "K"}, "falta o rei preto"),
    ({(0, 4): "k", (7, 4): "K", (7, 0): "K"}, "dois reis brancos"),
])
def test_contagem_de_reis(pecas, motivo):
    assert not _leitura(pecas).plausivel, motivo


def test_nove_peoes_e_impossivel():
    pecas = {(0, 4): "k", (7, 4): "K"}
    for i in range(9):
        pecas[(5, i % 8)] = "P" if i < 8 else "P"
    pecas.update({(5, i): "P" for i in range(8)})
    pecas[(4, 0)] = "P"
    assert not _leitura(pecas).plausivel


def test_peao_na_primeira_fila_e_impossivel():
    assert not _leitura({(0, 4): "k", (7, 4): "K", (7, 0): "P"}).plausivel


def test_peao_na_oitava_fila_e_impossivel():
    assert not _leitura({(0, 4): "k", (7, 4): "K", (0, 0): "p"}).plausivel


def test_dezessete_pecas_de_uma_cor_e_impossivel():
    pecas = {(0, 4): "k", (7, 4): "K"}
    pecas.update({(4, c): "R" for c in range(8)})
    pecas.update({(5, c): "R" for c in range(8)})
    assert not _leitura(pecas).plausivel


# ----------------------------------------------------------------------
# A legalidade arbitrando
# ----------------------------------------------------------------------

def _pontos(leituras):
    """Matriz de pontuação em que cada casa prefere o símbolo pedido."""
    P = np.full((len(leituras), len(diagrama.SIMBOLOS)), 0.1, np.float32)
    for i, s in enumerate(leituras):
        P[i, diagrama.SIMBOLOS.index(s)] = 1.0
    return P


def test_sem_rei_branco_a_legalidade_inventa_um():
    casas = [(0, 4), (7, 4), (5, 3)]
    lidos, mexidas = diagrama._arbitrar(_pontos(["k", "Q", "P"]), casas)
    assert lidos.count("K") == 1
    assert any(mexidas)


def test_dois_reis_pretos_viram_um():
    casas = [(0, 4), (0, 0), (7, 4)]
    lidos, _ = diagrama._arbitrar(_pontos(["k", "k", "K"]), casas)
    assert lidos.count("k") == 1


def test_peao_na_ultima_fila_e_trocado():
    casas = [(0, 0), (0, 4), (7, 4)]
    lidos, mexidas = diagrama._arbitrar(_pontos(["P", "k", "K"]), casas)
    assert lidos[0] != "P"
    assert mexidas[0]


def test_a_troca_mais_barata_e_a_escolhida():
    """Duas casas poderiam virar rei; ganha a que resiste menos."""
    casas = [(0, 4), (4, 4), (4, 0)]
    P = np.full((3, len(diagrama.SIMBOLOS)), 0.05, np.float32)
    P[0, diagrama.SIMBOLOS.index("k")] = 1.0
    P[1, diagrama.SIMBOLOS.index("Q")] = 0.9      # convicta
    P[1, diagrama.SIMBOLOS.index("K")] = 0.85
    P[2, diagrama.SIMBOLOS.index("R")] = 0.95     # convicta, e longe de rei
    P[2, diagrama.SIMBOLOS.index("K")] = 0.10
    lidos, _ = diagrama._arbitrar(P, casas)
    assert lidos[1] == "K", "a casa hesitante devia ter virado rei"
    assert lidos[2] == "R"


def test_posicao_ja_legal_nao_e_mexida():
    casas = [(0, 4), (7, 4), (5, 3)]
    lidos, mexidas = diagrama._arbitrar(_pontos(["k", "K", "P"]), casas)
    assert lidos == ["k", "K", "P"]
    assert not any(mexidas)


def test_arbitrar_termina_mesmo_no_caso_ruim():
    """Sem teto de voltas, uma posição irreparável giraria para sempre."""
    casas = [(0, c) for c in range(8)]
    lidos, _ = diagrama._arbitrar(_pontos(["P"] * 8), casas)
    assert len(lidos) == 8


# ----------------------------------------------------------------------
# Leitura de imagem
# ----------------------------------------------------------------------

def _tabuleiro_sintetico(pecas=(), lado=320):
    """
    Tabuleiro 8x8 desenhado: casas claras e escuras, peça = disco preto.

    Não serve para testar QUAL peça é — serve para a grade, o modelo de fundo e
    a separação vazia/ocupada, que são a parte do módulo que não depende do
    banco de amostras.
    """
    import cv2
    im = np.full((lado, lado), 250, np.uint8)
    passo = lado // 8
    for r in range(8):
        for c in range(8):
            if (r + c) % 2:
                im[r*passo:(r+1)*passo, c*passo:(c+1)*passo] = 170
    for r, c in pecas:
        cv2.circle(im, (c*passo + passo//2, r*passo + passo//2), passo//3, 0, -1)
    return im


def test_tabuleiro_vazio_nao_acha_peca():
    L = diagrama.ler(_tabuleiro_sintetico())
    assert L.ocupadas == []
    assert "nenhuma peça encontrada" in " ".join(L.avisos)


def test_acha_as_peca_onde_elas_estao():
    postas = {(0, 0), (3, 4), (7, 7), (5, 2)}
    L = diagrama.ler(_tabuleiro_sintetico(postas))
    achadas = {(c.linha, c.coluna) for c in L.ocupadas}
    assert achadas == postas


def test_a_grade_nao_desloca_com_tamanho_diferente():
    postas = {(1, 1), (6, 6)}
    for lado in (256, 320, 480):
        L = diagrama.ler(_tabuleiro_sintetico(postas, lado))
        assert {(c.linha, c.coluna) for c in L.ocupadas} == postas


def test_recorte_minusculo_avisa_em_vez_de_quebrar():
    L = diagrama.ler(np.full((8, 8), 200, np.uint8))
    assert L.avisos and "pequeno" in L.avisos[0]


def test_imagem_colorida_e_aceita():
    im = np.stack([_tabuleiro_sintetico({(2, 2)})] * 3, axis=-1)
    assert len(diagrama.ler(im).ocupadas) == 1


def test_todas_as_64_casas_saem_na_leitura():
    L = diagrama.ler(_tabuleiro_sintetico({(0, 0)}))
    assert len({(c.linha, c.coluna) for c in L.casas}) == 64


# ----------------------------------------------------------------------
# Página real (os diagramas versionados em Box/)
# ----------------------------------------------------------------------

def _paginas_com_diagrama():
    import glob
    import cv2
    from core import preprocess
    from core.services.box_service import BoxService

    saida = []
    for p in sorted(glob.glob(os.path.join(RAIZ, "Box", "*.png"))):
        arr = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
        if arr is None:
            continue
        th = preprocess.binarize(arr, "auto")
        cont, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        brutos = []
        for c in cont:
            x, y, w, h = cv2.boundingRect(c)
            if w >= 2 and h >= 2:
                brutos.append(BoxEntry("", x, y, x + w, y + h))
        brutos.sort(key=lambda b: (b.y1, b.x1))
        pais = BoxService.merge_vertical_boxes(brutos)
        caixas = diagrama.localizar(pais)
        if caixas:
            saida.append((p, arr, caixas))
    return saida


def test_acha_diagrama_em_pagina_de_verdade():
    paginas = _paginas_com_diagrama()
    if not paginas:
        pytest.skip("nenhuma página com diagrama em Box/")
    assert sum(len(c) for _, _, c in paginas) >= 1


def test_diagrama_de_verdade_tem_contagem_possivel():
    """
    Sem rótulo, a prova é a contagem: um tabuleiro de livro nunca tem 40 peças.
    Um erro grosseiro de grade ou de limiar estoura isto na hora.
    """
    paginas = _paginas_com_diagrama()
    if not paginas:
        pytest.skip("nenhuma página com diagrama em Box/")
    for caminho, arr, caixas in paginas:
        for caixa in caixas:
            L = diagrama.ler(arr, caixa)
            assert 2 <= len(L.ocupadas) <= 32, f"{caminho} {caixa}: {L.resumo()}"


def test_fen_de_pagina_real_e_aceito_pelo_python_chess():
    paginas = _paginas_com_diagrama()
    if not paginas:
        pytest.skip("nenhuma página com diagrama em Box/")
    for _, arr, caixas in paginas:
        for caixa in caixas:
            chess.Board(diagrama.ler(arr, caixa).fen())    # levanta se inválido


def test_ler_pagina_encadeia_localizar_e_ler():
    paginas = _paginas_com_diagrama()
    if not paginas:
        pytest.skip("nenhuma página com diagrama em Box/")
    caminho, arr, caixas = paginas[0]
    import cv2
    from core import preprocess
    from core.services.box_service import BoxService
    th = preprocess.binarize(arr, "auto")
    cont, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    brutos = []
    for c in cont:
        x, y, w, h = cv2.boundingRect(c)
        if w >= 2 and h >= 2:
            brutos.append(BoxEntry("", x, y, x + w, y + h))
    brutos.sort(key=lambda b: (b.y1, b.x1))
    leituras = diagrama.ler_pagina(arr, BoxService.merge_vertical_boxes(brutos))
    assert len(leituras) == len(caixas)


# ----------------------------------------------------------------------
# O modelo embarcado
# ----------------------------------------------------------------------

def test_o_modelo_existe_e_cobre_as_doze_pecas():
    if not os.path.isfile(diagrama.CAMINHO_MODELO):
        pytest.skip("modelo não construído (rode treinar_diagrama.py)")
    import torch
    d = torch.load(diagrama.CAMINHO_MODELO, map_location="cpu", weights_only=True)
    assert set(d["simbolos"]) == set("PNBRQKpnbrqk")
    # A última camada tem de ter uma saída por símbolo declarado: se as duas
    # listas se descasarem, a leitura troca as peças sem erro nenhum aparecer.
    assert d["pesos"]["fc.weight"].shape[0] == len(d["simbolos"])


def test_o_modelo_embarcado_cabe_no_repositorio():
    """
    O `.gitignore` manda `*.pth` para fora, e este tem exceção nominal (F7.4).

    A exceção só se justifica enquanto o arquivo for pequeno: é ele que faz um
    clone novo ler diagramas sem baixar nada. O banco de vizinhos que ele
    substituiu tinha 231 KB.
    """
    if not os.path.isfile(diagrama.CAMINHO_MODELO):
        pytest.skip("modelo não construído (rode treinar_diagrama.py)")
    assert os.path.getsize(diagrama.CAMINHO_MODELO) < 300_000


def test_o_modelo_embarcado_le_uma_peca():
    """Carrega, roda e devolve 12 colunas — o funil inteiro, sem página."""
    if not os.path.isfile(diagrama.CAMINHO_MODELO):
        pytest.skip("modelo não construído (rode treinar_diagrama.py)")
    residuo = np.zeros((diagrama.LADO, diagrama.LADO), np.float32)
    residuo[12:36, 16:32] = 90
    pontos = diagrama._pontuar([residuo])
    assert pontos.shape == (1, 12)
    # Probabilidades, não votos: é o que `ler` divide para achar a confiança.
    assert 0.99 < float(pontos.sum()) < 1.01


def test_modelo_ausente_levanta_erro_com_a_receita():
    guardado, diagrama._modelo = diagrama._modelo, None
    caminho, diagrama.CAMINHO_MODELO = diagrama.CAMINHO_MODELO, "nao_existe.pth"
    try:
        with pytest.raises(diagrama.ModeloAusente, match="treinar_diagrama"):
            diagrama._carregar_modelo()
    finally:
        diagrama.CAMINHO_MODELO, diagrama._modelo = caminho, guardado


# ----------------------------------------------------------------------
# O comando da janela e o diálogo
# ----------------------------------------------------------------------

class _App:
    def __enter__(self):
        from tkinter import messagebox
        from PIL import Image
        from conftest import raiz_tk
        from ui.main_window import MainWindow

        self._salvos = (messagebox.showinfo, messagebox.showerror)
        self.avisos = []
        messagebox.showinfo = lambda t, m=None, **k: self.avisos.append(m or t)
        messagebox.showerror = lambda t, m=None, **k: self.avisos.append(m or t)
        self.root = raiz_tk()
        self.win = MainWindow(self.root)
        self.win.image = Image.fromarray(_tabuleiro_sintetico({(0, 4), (7, 4)}))
        self.mostrados = []
        app = self

        class _DialogoFalso:
            def __init__(self, parent, imagem, leituras, origem=""):
                app.mostrados.append(leituras)
                app.origem = origem

            def mostrar(self):
                return app.devolver

        self.devolver = None
        self.win.DIALOGO_DIAGRAMA = _DialogoFalso
        return self

    def __exit__(self, *a):
        from tkinter import messagebox
        messagebox.showinfo, messagebox.showerror = self._salvos
        try:
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass


def _boxes_com_tabuleiro(lado=320):
    boxes = _pagina_de_texto()
    boxes.append(BoxEntry("", 0, 0, lado, lado))
    return boxes


def _pagina_com_diagrama(lado=240, pecas=((0, 4), (7, 4), (3, 3))):
    """
    Uma página como a que a interface vê: texto miúdo e um tabuleiro com
    moldura fechada.

    **Estes três testes usavam `win.boxes = _boxes_com_tabuleiro()`, e era por
    isso que passavam com o comando quebrado** (corrigido na F8.3). Aquela
    lista tinha o box do tabuleiro dentro; a lista que a interface realmente
    produz, não — `generate_boxes_opencv` descarta o contorno grande antes de
    devolver. O teste montava uma entrada que o caminho de produção nunca
    produz, e o comando respondia "nenhum diagrama encontrado" em toda página
    real sem que nada acusasse.
    """
    import cv2

    img = np.full((900, 700), 255, np.uint8)
    for i in range(80):
        x, y = 20 + (i % 20) * 30, 30 + (i // 20) * 26
        cv2.rectangle(img, (x, y), (x + 12, y + 17), 0, -1)

    x0, y0, passo = 120, 200, lado // 8
    for r in range(8):
        for c in range(8):
            if (r + c) % 2:
                img[y0 + r * passo:y0 + (r + 1) * passo,
                    x0 + c * passo:x0 + (c + 1) * passo] = 170
    cv2.rectangle(img, (x0, y0), (x0 + lado, y0 + lado), 0, 3)
    for r, c in pecas:
        cv2.circle(img, (x0 + c * passo + passo // 2,
                         y0 + r * passo + passo // 2), passo // 3, 0, -1)
    return img


def test_comando_abre_o_dialogo_com_as_leituras():
    from PIL import Image

    with _App() as app:
        app.win.image = Image.fromarray(_pagina_com_diagrama())
        app.win.extrair_diagramas()
        assert len(app.mostrados) == 1
        assert len(app.mostrados[0]) == 1


def test_o_comando_nao_depende_dos_boxes_da_pagina():
    """
    O diagrama é procurado na imagem, e não na lista de caracteres.

    Era o defeito: a lista de caracteres é justamente de onde o tabuleiro foi
    tirado.
    """
    from PIL import Image

    with _App() as app:
        app.win.image = Image.fromarray(_pagina_com_diagrama())
        app.win.boxes = []
        app.win.extrair_diagramas()
        assert len(app.mostrados) == 1


def test_pagina_sem_diagrama_avisa():
    from PIL import Image

    with _App() as app:
        app.win.image = Image.fromarray(np.full((400, 400), 255, np.uint8))
        app.win.extrair_diagramas()
        assert any("Nenhum diagrama" in a for a in app.avisos)
        assert app.mostrados == []


def test_comando_sem_imagem_avisa():
    with _App() as app:
        app.win.image = None
        app.win.boxes = _boxes_com_tabuleiro()
        app.win.extrair_diagramas()
        assert app.mostrados == []


def test_pagina_sem_diagrama_explica_o_criterio():
    with _App() as app:
        app.win.boxes = _pagina_de_texto()
        app.win.extrair_diagramas()
        assert any("Nenhum diagrama" in a for a in app.avisos)


def test_fen_escolhido_vai_para_a_area_de_transferencia():
    from PIL import Image

    with _App() as app:
        app.win.image = Image.fromarray(_pagina_com_diagrama())
        app.devolver = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"
        app.win.extrair_diagramas()
        assert app.win.parent.clipboard_get() == app.devolver


def test_comando_esta_no_menu():
    with _App() as app:
        barra = app.win.parent.nametowidget(app.win.parent.cget("menu"))
        for i in range(barra.index("end") + 1):
            if (barra.type(i) == "cascade"
                    and barra.entrycget(i, "label") == "Ferramentas"):
                menu = barra.nametowidget(barra.entrycget(i, "menu"))
                rotulos = [menu.entrycget(j, "label")
                           for j in range(menu.index("end") + 1)
                           if menu.type(j) == "command"]
                assert "Ler posição dos diagramas..." in rotulos
                return
        raise AssertionError("menu Ferramentas não existe")


def test_dialogo_desenha_as_duas_visoes():
    """O recorte impresso e a leitura, lado a lado — é o que torna a conferência viável."""
    from PIL import Image
    from conftest import raiz_tk
    from ui.dialogo_diagrama import DialogoDiagrama

    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        arr = _tabuleiro_sintetico({(0, 4), (7, 4), (3, 3)})
        leitura = diagrama.ler(arr)
        dlg = DialogoDiagrama(raiz, Image.fromarray(arr), [leitura])
        dlg.construir()
        assert dlg.var_fen.get() == leitura.fen()
        assert dlg.canvas.find_all(), "o tabuleiro lido não foi desenhado"
        assert dlg._fotos, "o recorte impresso não foi mostrado"
        dlg._confirmar()
        assert dlg.resultado == leitura.fen()
    finally:
        try:
            raiz.destroy()
        except Exception:
            pass


def test_dialogo_navega_entre_diagramas():
    from PIL import Image
    from conftest import raiz_tk
    from ui.dialogo_diagrama import DialogoDiagrama

    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        arr = _tabuleiro_sintetico({(0, 4), (7, 4)})
        leituras = [diagrama.ler(arr), diagrama.ler(arr)]
        dlg = DialogoDiagrama(raiz, Image.fromarray(arr), leituras)
        dlg.construir()
        assert "1 de 2" in dlg.lbl_titulo.cget("text")
        dlg._ir(1)
        assert "2 de 2" in dlg.lbl_titulo.cget("text")
        dlg._ir(1)
        assert "1 de 2" in dlg.lbl_titulo.cget("text"), "devia dar a volta"
    finally:
        try:
            raiz.destroy()
        except Exception:
            pass


def test_dialogo_fechado_sem_escolher_devolve_none():
    from PIL import Image
    from conftest import raiz_tk
    from ui.dialogo_diagrama import DialogoDiagrama

    raiz = raiz_tk()
    if raiz is None:
        pytest.skip("sem display")
    try:
        arr = _tabuleiro_sintetico({(0, 4), (7, 4)})
        dlg = DialogoDiagrama(raiz, Image.fromarray(arr), [diagrama.ler(arr)])
        dlg.construir()
        dlg._fechar()
        assert dlg.resultado is None
    finally:
        try:
            raiz.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
