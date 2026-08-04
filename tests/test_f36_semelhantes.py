"""
F3.6 — corrigiu um `e`, corrige os 300 iguais.

O risco desta fase é o inverso do da F3.3: lá, um erro de mapeamento fazia o
usuário editar UM box errado; aqui, um critério frouxo estraga TREZENTOS de uma
vez, em boxes que ele nunca olhou, e ainda os marca como revisados.

Por isso os testes cobram três coisas, não uma:
  - o critério casa o que é igual e recusa o que não é;
  - o modelo do lote é o box que o usuário corrigiu, não o que a seleção
    avançou por cima depois (F3.1 avança sozinho);
  - 300 boxes alterados são UM Ctrl+Z, não trezentos.

Rodar sem pytest:      python tests/test_f36_semelhantes.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import raiz_tk

import tkinter as tk
from tkinter import messagebox

import numpy as np
import pytest
from PIL import Image, ImageDraw

from core import semelhanca
from core.box_model import BoxEntry


# ----------------------------------------------------------------------
# Página sintética: os mesmos glifos desenhados em posições diferentes
# ----------------------------------------------------------------------

LADO_GLIFO = 20


def _desenhar(draw, x, y, forma):
    """Formas bem distintas, para o critério não ficar no limite do ruído."""
    x2, y2 = x + LADO_GLIFO - 4, y + LADO_GLIFO - 4
    if forma == "quadrado":
        draw.rectangle([x, y, x2, y2], outline=0, width=3)
    elif forma == "cheio":
        draw.rectangle([x, y, x2, y2], fill=0)
    elif forma == "barra":
        draw.rectangle([x, y, x2, y + 4], fill=0)
    elif forma == "x":
        draw.line([x, y, x2, y2], fill=0, width=3)
        draw.line([x, y2, x2, y], fill=0, width=3)


def pagina(formas):
    """(imagem, boxes) com um glifo por forma, lado a lado."""
    img = Image.new("L", (LADO_GLIFO * len(formas) + 20, 40), color=255)
    draw = ImageDraw.Draw(img)
    boxes = []
    for i, forma in enumerate(formas):
        x, y = 10 + i * LADO_GLIFO, 10
        _desenhar(draw, x, y, forma)
        boxes.append(BoxEntry("", x, y, x + LADO_GLIFO - 4, y + LADO_GLIFO - 4))
    return img, boxes


# ----------------------------------------------------------------------
# core.semelhanca — o critério
# ----------------------------------------------------------------------

def test_acha_os_iguais():
    img, boxes = pagina(["quadrado", "cheio", "quadrado", "quadrado"])
    achados = semelhanca.encontrar_semelhantes(img, boxes, 0)
    assert [i for i, _ in achados] == [2, 3]


def test_nao_traz_o_diferente():
    img, boxes = pagina(["quadrado", "cheio", "x", "barra"])
    achados = semelhanca.encontrar_semelhantes(img, boxes, 0)
    assert achados == []


def test_o_proprio_box_fica_de_fora():
    img, boxes = pagina(["quadrado", "quadrado"])
    achados = semelhanca.encontrar_semelhantes(img, boxes, 0)
    assert 0 not in [i for i, _ in achados]


def test_sai_ordenado_por_distancia():
    """O duvidoso tem que ficar no fim — é onde o olho do revisor deve parar."""
    img, boxes = pagina(["quadrado"] * 5)
    achados = semelhanca.encontrar_semelhantes(img, boxes, 0, limiar=1.0)
    distancias = [d for _, d in achados]
    assert distancias == sorted(distancias)


def test_limiar_mais_apertado_traz_menos():
    img, boxes = pagina(["quadrado", "cheio", "x", "barra", "quadrado"])
    largo = semelhanca.encontrar_semelhantes(img, boxes, 0, limiar=1.0)
    apertado = semelhanca.encontrar_semelhantes(img, boxes, 0, limiar=0.05)
    assert len(apertado) <= len(largo)


def test_rigor_tem_os_tres_niveis_em_ordem():
    assert (semelhanca.RIGOR["estrito"] < semelhanca.RIGOR["normal"]
            < semelhanca.RIGOR["amplo"])
    assert semelhanca.LIMIAR_PADRAO == semelhanca.RIGOR["normal"]


def test_indice_fora_da_faixa_nao_explode():
    img, boxes = pagina(["quadrado"])
    assert semelhanca.encontrar_semelhantes(img, boxes, 9) == []
    assert semelhanca.encontrar_semelhantes(img, boxes, -1) == []


def test_box_degenerado_e_ignorado():
    img, boxes = pagina(["quadrado", "quadrado"])
    boxes.append(BoxEntry("", 5, 5, 5, 5))
    achados = semelhanca.encontrar_semelhantes(img, boxes, 0, limiar=1.0)
    assert 2 not in [i for i, _ in achados]


def test_box_fora_da_imagem_e_ignorado():
    img, boxes = pagina(["quadrado"])
    boxes.append(BoxEntry("", 9000, 9000, 9020, 9020))
    assert semelhanca.encontrar_semelhantes(img, boxes, 0, limiar=1.0) == []


# ----------------------------------------------------------------------
# O filtro de leitura
# ----------------------------------------------------------------------

def test_filtro_de_leitura_so_traz_quem_ainda_esta_lido_assim():
    img, boxes = pagina(["quadrado"] * 4)
    boxes[1].char = "c"
    boxes[2].char = "c"
    boxes[3].char = "x"
    achados = semelhanca.encontrar_semelhantes(img, boxes, 0, leitura="c")
    assert [i for i, _ in achados] == [1, 2]


def test_sem_filtro_de_leitura_traz_todos_os_parecidos():
    img, boxes = pagina(["quadrado"] * 4)
    boxes[1].char, boxes[2].char, boxes[3].char = "c", "c", "x"
    achados = semelhanca.encontrar_semelhantes(img, boxes, 0, leitura=None)
    assert [i for i, _ in achados] == [1, 2, 3]


def test_leitura_vazia_acha_os_boxes_sem_caractere():
    """Corrigir um box vazio e espalhar para os outros vazios é caso legítimo."""
    img, boxes = pagina(["quadrado"] * 3)
    boxes[1].char = ""
    boxes[2].char = "z"
    achados = semelhanca.encontrar_semelhantes(img, boxes, 0, leitura="")
    assert [i for i, _ in achados] == [1]


# ----------------------------------------------------------------------
# Geometria: proporção e altura entram por fora do descritor
# ----------------------------------------------------------------------

def test_proporcao_diferente_nao_casa():
    """Depois do redimensionamento um `.` e um `O` preenchem o mesmo quadrado."""
    img = Image.new("L", (200, 60), color=255)
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 30, 30], fill=0)     # quadrado
    draw.rectangle([50, 10, 110, 30], fill=0)    # o triplo de largo
    boxes = [BoxEntry("", 10, 10, 30, 30), BoxEntry("", 50, 10, 110, 30)]
    assert semelhanca.encontrar_semelhantes(img, boxes, 0, limiar=1.0) == []


def test_altura_muito_diferente_nao_casa():
    img = Image.new("L", (200, 120), color=255)
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 30, 30], fill=0)
    draw.rectangle([50, 10, 110, 70], fill=0)    # mesma proporção, 3x a altura
    boxes = [BoxEntry("", 10, 10, 30, 30), BoxEntry("", 50, 10, 110, 70)]
    assert semelhanca.encontrar_semelhantes(img, boxes, 0, limiar=1.0) == []


def test_descritor_nao_depende_do_tamanho_do_recorte():
    """Mesmo glifo em dois corpos de fonte tem o mesmo descritor."""
    pequeno = np.zeros((20, 20), dtype=np.uint8)
    grande = np.zeros((60, 60), dtype=np.uint8)
    d1 = semelhanca.descritor(pequeno)
    d2 = semelhanca.descritor(grande)
    assert semelhanca.distancia(d1, d2) < 0.01


def test_descritor_de_recorte_vazio_e_none():
    assert semelhanca.descritor(np.empty((0, 0), dtype=np.uint8)) is None
    assert semelhanca.descritor(None) is None


def test_distancia_de_iguais_e_zero():
    d = semelhanca.descritor(np.full((10, 10), 128, dtype=np.uint8))
    assert semelhanca.distancia(d, d) == pytest.approx(0.0)


def test_distancia_do_branco_ao_preto_e_um():
    branco = semelhanca.descritor(np.full((10, 10), 255, dtype=np.uint8))
    preto = semelhanca.descritor(np.zeros((10, 10), dtype=np.uint8))
    assert semelhanca.distancia(branco, preto) == pytest.approx(1.0, abs=0.01)


def test_aceita_imagem_colorida():
    colorida = np.zeros((30, 30, 3), dtype=np.uint8)
    boxes = [BoxEntry("", 0, 0, 10, 10), BoxEntry("", 15, 15, 25, 25)]
    achados = semelhanca.encontrar_semelhantes(colorida, boxes, 0)
    assert [i for i, _ in achados] == [1]


# ----------------------------------------------------------------------
# Integração com a janela
# ----------------------------------------------------------------------

class _DialogoFalso:
    """Dublê do diálogo: devolve o que o teste mandar, sem abrir janela."""

    devolver = None
    ultima_chamada = None

    def __init__(self, parent, imagem, boxes, indice, char_novo,
                 leitura=None, rigor="normal"):
        _DialogoFalso.ultima_chamada = dict(
            indice=indice, char_novo=char_novo, leitura=leitura, boxes=boxes,
            imagem=imagem)
        self._boxes = boxes
        self._indice = indice
        self._leitura = leitura

    def mostrar(self):
        if _DialogoFalso.devolver == "todos":
            return [i for i, _ in semelhanca.encontrar_semelhantes(
                _DialogoFalso.ultima_chamada["imagem"], self._boxes,
                self._indice, leitura=self._leitura)]
        return _DialogoFalso.devolver


class _App:
    def __enter__(self):
        from ui.main_window import MainWindow
        self._info, self._erro = messagebox.showinfo, messagebox.showerror
        messagebox.showinfo = lambda *a, **k: None
        messagebox.showerror = lambda *a, **k: None
        self.root = raiz_tk()
        self.win = MainWindow(self.root)
        self.win.DIALOGO_SEMELHANTES = _DialogoFalso
        _DialogoFalso.devolver = None
        _DialogoFalso.ultima_chamada = None
        return self

    def __exit__(self, *a):
        messagebox.showinfo, messagebox.showerror = self._info, self._erro
        try:
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass


def _montar(win, formas, chars):
    img, boxes = pagina(formas)
    for b, c in zip(boxes, chars):
        b.char = c
        b.confidence = 0.4
        b.source = "neural"
    win.image = img
    win.boxes = boxes
    win.selected_index = 0
    win.history.snapshot(win.boxes, 0)
    win.update_sidebar()
    return boxes


def test_lote_grava_o_caractere_nos_escolhidos():
    with _App() as app:
        w = app.win
        _montar(w, ["quadrado"] * 4, ["c", "c", "c", "c"])
        assert w.aplicar_em_lote([1, 2, 3], "e") == 3
        assert [b.char for b in w.boxes] == ["c", "e", "e", "e"]


def test_lote_marca_origem_propria():
    """Marcar como 'manual' apagaria o rastro de que o box veio de um lote."""
    with _App() as app:
        w = app.win
        _montar(w, ["quadrado"] * 3, ["c", "c", "c"])
        w.aplicar_em_lote([1, 2], "e")
        assert [b.source for b in w.boxes[1:]] == ["lote", "lote"]
        assert all(b.confidence == 1.0 for b in w.boxes[1:])


def test_box_de_lote_sai_da_fila_de_revisao():
    from ui import confidence as conf_ui

    with _App() as app:
        w = app.win
        _montar(w, ["quadrado"] * 2, ["c", "c"])
        assert conf_ui.precisa_revisao(w.boxes[1])
        w.aplicar_em_lote([1], "e")
        assert not conf_ui.precisa_revisao(w.boxes[1])


def test_box_de_lote_aparece_no_filtro_de_origem():
    with _App() as app:
        w = app.win
        _montar(w, ["quadrado"] * 2, ["c", "c"])
        w.aplicar_em_lote([1], "e")
        assert "lote" in list(w.combo_origem["values"])


def test_lote_inteiro_e_um_unico_desfazer():
    """300 boxes alterados, um Ctrl+Z. É o que torna o lote reversível."""
    with _App() as app:
        w = app.win
        _montar(w, ["quadrado"] * 6, list("cccccc"))
        antes = len(w.history._history)

        w.aplicar_em_lote([1, 2, 3, 4, 5], "e")
        assert len(w.history._history) == antes + 1
        assert [b.char for b in w.boxes] == ["c", "e", "e", "e", "e", "e"]

        w._perform_undo()
        assert [b.char for b in w.boxes] == list("cccccc")


def test_lote_sem_mudanca_nao_gera_desfazer():
    with _App() as app:
        w = app.win
        _montar(w, ["quadrado"] * 3, ["e", "e", "e"])
        antes = len(w.history._history)
        assert w.aplicar_em_lote([1, 2], "e") == 0
        assert len(w.history._history) == antes


def test_lote_ignora_indice_invalido():
    with _App() as app:
        w = app.win
        _montar(w, ["quadrado"] * 2, ["c", "c"])
        assert w.aplicar_em_lote([1, 99, -3], "e") == 1


def test_lote_marca_a_pagina_como_nao_salva():
    with _App() as app:
        w = app.win
        _montar(w, ["quadrado"] * 2, ["c", "c"])
        w.aplicar_em_lote([1], "e")
        assert w.session is None or w.session.is_dirty()


# ----------------------------------------------------------------------
# Qual box é o modelo — o ponto em que isto poderia dar muito errado
# ----------------------------------------------------------------------

def test_modelo_e_o_box_corrigido_mesmo_com_a_selecao_ja_adiantada():
    """
    F3.1 avança sozinho depois de gravar. Se o lote usasse a seleção, ele
    espalharia o caractere do box SEGUINTE — que o usuário nem olhou.
    """
    with _App() as app:
        w = app.win
        _montar(w, ["quadrado", "x", "quadrado"], ["c", "z", "c"])

        w.select_box(0)
        w.char_entry.delete(0, "end")
        w.char_entry.insert(0, "e")
        w.apply_char_and_next()

        assert w.selected_index != 0, "a seleção deveria ter avançado"
        indice, char, leitura = w.referencia_do_lote()
        assert (indice, char, leitura) == (0, "e", "c")


def test_sem_correcao_o_modelo_e_a_selecao_e_nao_ha_filtro_de_leitura():
    with _App() as app:
        w = app.win
        _montar(w, ["quadrado"] * 3, ["a", "b", "c"])
        w.select_box(2)
        assert w.referencia_do_lote() == (2, "c", None)


class _Tecla:
    """Evento de tecla mínimo — o `event_generate` não entrega `char`."""

    def __init__(self, char):
        self.char = char


def test_correcao_pelo_modo_digitacao_tambem_vira_modelo():
    with _App() as app:
        w = app.win
        _montar(w, ["quadrado", "x"], ["c", "z"])
        w.alternar_modo_digitacao(True)
        w.select_box(0)
        w._on_tecla_digitacao(_Tecla("e"))

        indice, char, leitura = w.referencia_do_lote()
        assert (indice, char, leitura) == (0, "e", "c")


def test_desfazer_invalida_a_correcao_guardada():
    """O undo troca a lista por cópias; casar por índice pegaria outro box."""
    with _App() as app:
        w = app.win
        _montar(w, ["quadrado"] * 3, ["c", "c", "c"])
        w.select_box(0)
        w.char_entry.delete(0, "end")
        w.char_entry.insert(0, "e")
        w.apply_char()
        w._perform_undo()

        referencia = w.referencia_do_lote()
        assert referencia is None or referencia[2] is None


def test_referencia_sem_box_nenhum_e_none():
    with _App() as app:
        w = app.win
        w.boxes = []
        w.selected_index = -1
        assert w.referencia_do_lote() is None


# ----------------------------------------------------------------------
# O comando completo, com o diálogo dublado
# ----------------------------------------------------------------------

def test_comando_completo_corrige_os_semelhantes():
    with _App() as app:
        w = app.win
        _montar(w, ["quadrado", "x", "quadrado", "quadrado"], ["c", "z", "c", "c"])

        w.select_box(0)
        w.char_entry.delete(0, "end")
        w.char_entry.insert(0, "e")
        w.apply_char_and_next()

        _DialogoFalso.devolver = "todos"
        w.aplicar_aos_semelhantes()

        assert [b.char for b in w.boxes] == ["e", "z", "e", "e"]


def test_o_dialogo_recebe_modelo_leitura_e_alvo():
    with _App() as app:
        w = app.win
        _montar(w, ["quadrado"] * 3, ["c", "c", "c"])
        w.select_box(0)
        w.char_entry.delete(0, "end")
        w.char_entry.insert(0, "e")
        w.apply_char_and_next()

        _DialogoFalso.devolver = []
        w.aplicar_aos_semelhantes()

        chamada = _DialogoFalso.ultima_chamada
        assert chamada["indice"] == 0
        assert chamada["char_novo"] == "e"
        assert chamada["leitura"] == "c"


def test_cancelar_o_dialogo_nao_muda_nada():
    with _App() as app:
        w = app.win
        _montar(w, ["quadrado"] * 3, ["c", "c", "c"])
        antes = [b.char for b in w.boxes]
        historico = len(w.history._history)

        _DialogoFalso.devolver = None
        w.aplicar_aos_semelhantes()

        assert [b.char for b in w.boxes] == antes
        assert len(w.history._history) == historico


def test_lote_sem_caractere_no_modelo_avisa_e_nao_abre_dialogo():
    with _App() as app:
        w = app.win
        _montar(w, ["quadrado"] * 3, ["", "", ""])
        w.select_box(0)
        w.aplicar_aos_semelhantes()
        assert _DialogoFalso.ultima_chamada is None


def test_sem_imagem_o_comando_nao_faz_nada():
    with _App() as app:
        w = app.win
        w.image = None
        w.boxes = [BoxEntry("a", 0, 0, 5, 5)]
        w.aplicar_aos_semelhantes()
        assert _DialogoFalso.ultima_chamada is None


# ----------------------------------------------------------------------
# O diálogo de pré-visualização
# ----------------------------------------------------------------------

class _Dialogo:
    """Abre o diálogo de verdade, sem esperar por usuário."""

    def __init__(self, formas, chars=None, leitura=None, char_novo="e"):
        from ui.dialogo_semelhantes import DialogoSemelhantes

        self.img, self.boxes = pagina(formas)
        for b, c in zip(self.boxes, chars or []):
            b.char = c
        self.root = raiz_tk()
        self.dlg = DialogoSemelhantes(self.root, self.img, self.boxes, 0,
                                      char_novo, leitura)

    def __enter__(self):
        self.dlg.construir()
        return self.dlg

    def __exit__(self, *a):
        try:
            self.dlg._fechar()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


def test_dialogo_abre_com_todos_marcados():
    with _Dialogo(["quadrado"] * 4) as dlg:
        assert [i for i, _ in dlg.achados] == [1, 2, 3]
        assert all(dlg.marcados.values())


def test_dialogo_devolve_os_marcados():
    with _Dialogo(["quadrado"] * 4) as dlg:
        dlg._confirmar()
        assert dlg.resultado == [1, 2, 3]


def test_clicar_desmarca_e_o_box_sai_do_lote():
    with _Dialogo(["quadrado"] * 4) as dlg:
        dlg._alternar(2)
        dlg._confirmar()
        assert dlg.resultado == [1, 3]


def test_botao_direito_desmarca_da_posicao_ate_o_fim():
    """Com a fila ordenada por distância, é o gesto que corta o duvidoso."""
    with _Dialogo(["quadrado"] * 6) as dlg:
        dlg._cortar_cauda(2)
        dlg._confirmar()
        assert dlg.resultado == [i for i, _ in dlg.achados[:2]]


def test_desmarcar_todos_desabilita_o_aplicar():
    with _Dialogo(["quadrado"] * 4) as dlg:
        dlg._marcar_todos(False)
        assert str(dlg.btn_aplicar.cget("state")) == "disabled"
        dlg._marcar_todos(True)
        assert str(dlg.btn_aplicar.cget("state")) == "normal"


def test_cancelar_devolve_none_e_nao_lista_vazia():
    """None é 'desisti', [] é 'desmarquei tudo' — a janela reage diferente."""
    with _Dialogo(["quadrado"] * 3) as dlg:
        dlg._cancelar()
        assert dlg.resultado is None


def test_rigor_mais_estrito_encolhe_a_lista():
    with _Dialogo(["quadrado", "cheio", "x", "quadrado", "barra"]) as dlg:
        dlg.var_rigor.set("amplo")
        dlg._buscar()
        amplo = len(dlg.achados)
        dlg.var_rigor.set("estrito")
        dlg._buscar()
        assert len(dlg.achados) <= amplo


def test_titulo_mostra_o_caractere_e_a_leitura():
    with _Dialogo(["quadrado"] * 3, chars=["e", "c", "c"], leitura="c") as dlg:
        texto = dlg.lbl_titulo.cget("text")
        assert "e" in texto and "c" in texto


def test_contador_acompanha_a_marcacao():
    with _Dialogo(["quadrado"] * 5) as dlg:
        assert "(4)" in dlg.btn_aplicar.cget("text")
        dlg._alternar(dlg.achados[0][0])
        assert "(3)" in dlg.btn_aplicar.cget("text")


def test_dialogo_sem_semelhante_nenhum_nao_quebra():
    with _Dialogo(["quadrado", "cheio", "x"]) as dlg:
        assert dlg.achados == []
        assert str(dlg.btn_aplicar.cget("state")) == "disabled"
        dlg._confirmar()
        assert dlg.resultado == []


def test_comando_tem_atalho_proprio():
    with _App() as app:
        w = app.win
        assert "<Control-Key-e>" in w.parent.bind()


def test_atalho_do_lote_nao_colide_com_os_ja_existentes():
    """Ctrl+D divide, Ctrl+B grava rascunho, Ctrl+F busca, Ctrl+S salva."""
    with _App() as app:
        ligadas = list(app.win.parent.bind())
        assert len(ligadas) == len(set(ligadas))
        for atalho in ("<Control-Key-d>", "<Control-Key-b>", "<Control-Key-f>",
                       "<Control-Key-s>", "<Control-Key-z>"):
            assert atalho in ligadas


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
