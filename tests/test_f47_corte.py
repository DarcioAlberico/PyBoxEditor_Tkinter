"""
F4.7 — o Ctrl+D corta onde a tinta abre, e não onde a caixa é mais comprida.

O defeito relatado: um box com 'ba', 'it' ou 'll' — letra alta ao lado de letra
baixa — sai mais **alto** que largo, e a regra da proporção partia as duas
letras uma embaixo da outra. Medido nas 9 páginas rotuladas, unindo cada par de
caracteres vizinhos da verdade rotulada num box só (5.747 pares lado a lado),
a regra antiga erra o eixo em 534 deles — 9,3%.

Estes testes não repetem a medição: eles fixam o caso que ela encontrou. Cada
figura sintética é um par de glifos com a geometria que enganava a regra antiga,
e o que se afirma é o eixo e o lugar do corte.

Rodar sem pytest:      python tests/test_f47_corte.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core.box_model import BoxEntry
from core.services.box_service import BoxService


FUNDO, TINTA = 255, 0


def _pagina(*manchas, largura=40, altura=40):
    """Folha branca com retângulos de tinta. Cada mancha é (x1, y1, x2, y2)."""
    img = np.full((altura, largura), FUNDO, dtype=np.uint8)
    for x1, y1, x2, y2 in manchas:
        img[y1:y2, x1:x2] = TINTA
    return img


def _uniao(*manchas):
    return BoxEntry("", min(m[0] for m in manchas), min(m[1] for m in manchas),
                    max(m[2] for m in manchas), max(m[3] for m in manchas))


# ----------------------------------------------------------------------
# O caso relatado: 'ba'
# ----------------------------------------------------------------------

# 'b' é alto e estreito, 'a' é baixo. A união fica mais alta (20) que larga (12)
# — e é exatamente por isso que a regra da proporção a partia em Y.
BA = ((4, 4, 8, 24), (12, 14, 16, 24))


def test_ba_e_partido_ao_lado_e_nao_por_cima():
    a, b = BA
    partes = BoxService.split_box(_uniao(a, b), _pagina(a, b))

    assert len(partes) == 2
    # Corte em X: as metades dividem a largura e mantêm a altura inteira.
    assert partes[0].x2 == partes[1].x1, "o corte não foi vertical"
    assert partes[0].y1 == partes[1].y1 and partes[0].y2 == partes[1].y2


def test_o_corte_cai_no_vao_entre_as_letras():
    a, b = BA
    partes = BoxService.split_box(_uniao(a, b), _pagina(a, b))

    corte = partes[0].x2
    assert a[2] <= corte <= b[0], f"corte em x={corte}, fora do vão {a[2]}..{b[0]}"


def test_cada_metade_fica_com_uma_letra_inteira():
    """O que o revisor vai digitar em cada uma tem de estar lá dentro."""
    a, b = BA
    esq, dir_ = BoxService.split_box(_uniao(a, b), _pagina(a, b))

    assert esq.x1 <= a[0] and esq.x2 >= a[2]
    assert dir_.x1 <= b[0] and dir_.x2 >= b[2]


def test_a_regra_antiga_erraria_este_caso():
    """
    A prova de que a figura é a certa: sem imagem, o corte sai em Y.

    Se este teste começar a falhar, ou a regra de reserva mudou ou a figura
    deixou de reproduzir o defeito — e nos dois casos os testes acima passariam
    a não medir nada.
    """
    a, b = BA
    partes = BoxService.split_box(_uniao(a, b))
    assert partes[0].y2 == partes[1].y1, "a figura não engana mais a geometria"


# ----------------------------------------------------------------------
# O outro eixo continua funcionando
# ----------------------------------------------------------------------

# Empilhados: larga (20) e baixa (14). A proporção mandaria cortar em X.
PILHA = ((6, 4, 26, 10), (6, 14, 26, 20))


def test_glifos_empilhados_sao_partidos_por_cima():
    a, b = PILHA
    partes = BoxService.split_box(_uniao(a, b), _pagina(a, b))

    assert partes[0].y2 == partes[1].y1, "o corte não foi horizontal"
    assert partes[0].x1 == partes[1].x1 and partes[0].x2 == partes[1].x2
    assert a[3] <= partes[0].y2 <= b[1]


def test_pilha_tambem_engana_a_geometria_sozinha():
    a, b = PILHA
    partes = BoxService.split_box(_uniao(a, b))
    assert partes[0].x2 == partes[1].x1, "a figura não engana mais a geometria"


# ----------------------------------------------------------------------
# Sem tinta que ajude, vale a regra antiga
# ----------------------------------------------------------------------

def test_sem_imagem_o_corte_e_o_meio_geometrico():
    partes = BoxService.split_box(BoxEntry("", 0, 0, 40, 10))
    assert [p.as_tuple() for p in partes] == [("", 0, 0, 20, 10),
                                              ("", 20, 0, 40, 10)]


def test_glifo_solido_sem_vao_cai_no_meio():
    """Uma mancha só não tem vale: cortar no meio é a resposta honesta."""
    mancha = (10, 10, 30, 20)
    partes = BoxService.split_box(_uniao(mancha), _pagina(mancha))
    assert partes[0].x2 == partes[1].x1 == 20


def test_box_vazio_nao_explode():
    """Página em branco: sem tinta não há pico, e o corte volta à geometria."""
    partes = BoxService.split_box(BoxEntry("", 5, 5, 25, 15), _pagina())
    assert len(partes) == 2
    assert partes[0].x2 == partes[1].x1 == 15


def test_box_fino_demais_para_medir_nao_explode():
    partes = BoxService.split_box(BoxEntry("", 5, 5, 25, 6), _pagina())
    assert len(partes) == 2


def test_box_fora_da_imagem_nao_explode():
    partes = BoxService.split_box(BoxEntry("", 100, 100, 140, 110), _pagina())
    assert len(partes) == 2


# ----------------------------------------------------------------------
# O que as metades herdam (F8.1, F10)
# ----------------------------------------------------------------------

def test_as_metades_herdam_angulo_e_polaridade_com_imagem():
    a, b = BA
    box = _uniao(a, b)
    box.angulo, box.negativo = 90, True
    partes = BoxService.split_box(box, _pagina(a, b))
    assert all(p.angulo == 90 and p.negativo for p in partes)


def test_tarja_preta_e_positivada_antes_de_medir():
    """
    Em negativo a tinta é clara sobre fundo escuro (F10).

    Sem positivar, o perfil mediria o fundo: o vale cairia dentro de uma letra
    em vez de no vão entre as duas, e o corte sairia no lugar errado.
    """
    a, b = BA
    pagina = 255 - _pagina(a, b)          # a mesma figura, invertida
    box = _uniao(a, b)
    box.negativo = True

    partes = BoxService.split_box(box, pagina)
    assert partes[0].x2 == partes[1].x1
    assert a[2] <= partes[0].x2 <= b[0]


# ----------------------------------------------------------------------
# O vale, isolado
# ----------------------------------------------------------------------

def _vale(perfil, margem=0.0):
    return BoxService._vale_mais_fundo(np.array(perfil, dtype=float), margem)


def test_descida_monotona_nao_e_vale():
    """
    É o coração da correção.

    O perfil por linha de 'ba' *cai* na faixa do ascendente do 'b': pouca tinta
    em cima, muita embaixo. Medido contra o pico geral, aquilo parece um vale
    fundo; medido contra o pico de cima — que é o próprio ascendente — é zero.
    """
    assert _vale([1, 1, 1, 9, 9, 9]) is None


def test_vale_de_verdade_e_encontrado():
    pos, fundura = _vale([9, 9, 0, 9, 9])
    assert pos == 2
    assert fundura == 1.0


def test_vale_largo_corta_no_meio_do_vao():
    pos, _ = _vale([9, 9, 0, 0, 0, 9, 9])
    assert pos == 3


def test_a_fundura_e_medida_contra_o_menor_flanco():
    """Vale de 2 entre picos de 10 e 4: a queda que importa é a do 4."""
    _, fundura = _vale([10, 10, 2, 4, 4])
    assert abs(fundura - 0.5) < 1e-9


def test_perfil_curto_demais_nao_tem_vale_interno():
    assert _vale([9, 0]) is None
    assert _vale([]) is None


def test_perfil_sem_tinta_nao_tem_vale():
    assert _vale([0, 0, 0, 0]) is None


def test_a_margem_protege_as_pontas():
    """
    Perto da borda todo perfil desce, e cortar ali devolve uma lasca.

    Com margem, o vale da ponta é ignorado e vale o do miolo.
    """
    perfil = [9, 0, 9, 9, 9, 1, 9, 9, 9, 0, 9]
    assert _vale(perfil, 0.0)[0] == 1              # sem margem, ganha a ponta
    assert _vale(perfil, 0.20)[0] == 5             # com margem, o do miolo


# ----------------------------------------------------------------------
# O Ctrl+D chega ao campo do caractere
# ----------------------------------------------------------------------

class _App:
    """A janela real, como nos testes da F3.5."""

    def __enter__(self):
        from tkinter import messagebox
        from PIL import Image
        from conftest import raiz_tk
        from ui.main_window import MainWindow

        self._info, self._erro = messagebox.showinfo, messagebox.showerror
        messagebox.showinfo = lambda *a, **k: None
        messagebox.showerror = lambda *a, **k: None
        self.root = raiz_tk()
        self.win = MainWindow(self.root)
        # A mesma figura do 'ba', numa página que a janela possa medir.
        arr = _pagina(*BA, largura=60, altura=40)
        self.win.image = Image.fromarray(arr)
        self.win.boxes = [_uniao(*BA)]
        self.win.select_box(0)
        return self

    def __exit__(self, *a):
        from tkinter import messagebox
        messagebox.showinfo, messagebox.showerror = self._info, self._erro
        try:
            self.win.task.shutdown()
            self.root.destroy()
        except Exception:
            pass


def test_ctrl_d_no_campo_do_caractere_divide_o_box():
    """
    O box selecionado é o que está no campo: o atalho tem de valer ali.

    O guard de `_on_key_split_safe` cala o Ctrl+D em todo campo de texto, e para
    a busca e o número da página isso está certo. O campo do caractere é o
    oposto — ele *é* o box, e é onde a mão do revisor está.
    """
    with _App() as app:
        w = app.win
        w._on_key_split_no_campo(None)
        assert len(w.boxes) == 2
        assert w.boxes[0].x2 == w.boxes[1].x1, "dividiu no eixo errado"


def test_ctrl_d_esta_ligado_no_widget_e_nao_so_na_janela():
    """
    **O lugar da binding é o contrato, não um detalhe.**

    A tecla passa pelo widget, depois pela classe, depois pelo toplevel. A
    binding de classe do `Entry` trata `Control-d` apagando o caractere à
    direita do cursor: se só a janela tratasse o caso, o atalho dividiria o box
    **e** comeria o que estava escrito, porque a de classe já teria rodado.

    Ligada no widget e devolvendo "break" (o teste seguinte), as duas não
    rodam — é o que o Tk garante.
    """
    with _App() as app:
        ligadas = app.win.char_entry.bind()
        assert "<Control-Key-d>" in ligadas


def test_ctrl_d_no_campo_devolve_break():
    with _App() as app:
        assert app.win._on_key_split_no_campo(None) == "break"


def test_ctrl_d_no_campo_deixa_o_foco_pronto_para_digitar():
    """
    Dividir 'ba' e digitar 'b', Enter, 'a', Enter sem tirar a mão do teclado.

    Numa janela retirada da tela o Tk não atribui foco de verdade, então
    `focus_get()` não serve de asserção — a via é espiar a chamada, como já faz
    `test_f35_atalhos`.
    """
    with _App() as app:
        w = app.win
        pediu = []
        w.char_entry.focus_set = lambda: pediu.append(True)

        w._on_key_split_no_campo(None)
        assert pediu == [True]


def test_ctrl_d_continua_calado_na_busca():
    """
    Lá não há box por trás do campo — dividir seria dividir às cegas.

    O foco é fingido pelo mesmo motivo do teste acima: janela retirada da tela
    não recebe foco, e o guard pergunta por `focus_get`.
    """
    with _App() as app:
        w = app.win
        w.parent.focus_get = lambda: w.entry_busca

        w._on_key_split_safe(None)
        assert len(w.boxes) == 1


# ----------------------------------------------------------------------
# F4.9 — depois de dividir, o cursor já está no campo
# ----------------------------------------------------------------------

def test_ctrl_d_fora_do_campo_tambem_deixa_o_foco_pronto(monkeypatch):
    """
    O relato: dividir e ter de ir ao mouse buscar o campo para digitar a letra.

    Era só metade do caminho — o foco ia para o campo quando o Ctrl+D partia
    **de dentro** dele, e não quando partia do canvas ou da lista, que é onde a
    mão está depois de escolher o box.
    """
    with _App() as app:
        w = app.win
        w.parent.focus_get = lambda: w.canvas       # foco fora de campo de texto
        pediu = []
        monkeypatch.setattr(w.char_entry, "focus_set",
                            lambda: pediu.append(True))

        w._on_key_split_safe(None)

        assert len(w.boxes) == 2, "não dividiu"
        assert pediu == [True], "o foco não foi para o campo do caractere"


def test_dividir_pelo_menu_deixa_o_foco_pronto(monkeypatch):
    """
    'Dividir box selecionado' é a mesma ação, e termina no mesmo lugar.

    O foco mora em `split_selected_box` e não na binding justamente por isto:
    as três rotas do comando — canvas, campo e menu — têm de deixar o cursor
    pronto, e pendurá-lo na tecla deixaria o menu de fora.
    """
    with _App() as app:
        w = app.win
        pediu = []
        monkeypatch.setattr(w.char_entry, "focus_set",
                            lambda: pediu.append(True))

        w.split_selected_box()                      # o que o menu chama

        assert len(w.boxes) == 2
        assert pediu == [True]


def test_dividir_no_modo_digitacao_nao_rouba_o_foco(monkeypatch):
    """
    Mesma regra do Tab: lá quem recebe as teclas é a janela, e tirar o foco do
    canvas desligaria o modo na prática — o oposto do que o pedido queria.
    """
    with _App() as app:
        w = app.win
        w.alternar_modo_digitacao(True)
        pediu = []
        monkeypatch.setattr(w.char_entry, "focus_set",
                            lambda: pediu.append(True))

        w.split_selected_box()

        assert len(w.boxes) == 2, "no modo digitação o Ctrl+D deve dividir igual"
        assert pediu == []


def test_dividir_sem_box_selecionado_nao_mexe_no_foco(monkeypatch):
    """Sem box não há o que dividir nem o que digitar."""
    with _App() as app:
        w = app.win
        w.select_box(-1)
        pediu = []
        monkeypatch.setattr(w.char_entry, "focus_set",
                            lambda: pediu.append(True))

        w.split_selected_box()

        assert pediu == []


# ----------------------------------------------------------------------
# A seta na lista lateral
# ----------------------------------------------------------------------

def test_a_seta_aponta_o_box_selecionado():
    with _App() as app:
        w = app.win
        w.boxes = [BoxEntry(c, i * 10, 0, i * 10 + 8, 10)
                   for i, c in enumerate("abcde")]
        w.select_box(2)

        linhas = [w.listbox.get(i) for i in range(w.listbox.size())]
        assert [linha[0] for linha in linhas] == [
            " ", " ", w.SETA_SELECAO, " ", " "]


def test_a_seta_anda_junto_com_a_selecao():
    with _App() as app:
        w = app.win
        w.boxes = [BoxEntry(c, i * 10, 0, i * 10 + 8, 10)
                   for i, c in enumerate("abcde")]
        w.select_box(2)
        w.select_box(4)

        linhas = [w.listbox.get(i) for i in range(w.listbox.size())]
        assert linhas[2][0] == " ", "a seta velha ficou para trás"
        assert linhas[4][0] == w.SETA_SELECAO


def test_a_seta_e_uma_coluna_e_nao_empurra_o_resto_da_linha():
    """
    Coluna fixa: com e sem seta, o índice do box começa na mesma casa.

    Sem isso a lista dança para os lados a cada tecla de navegação.
    """
    with _App() as app:
        w = app.win
        w.boxes = [BoxEntry(c, i * 10, 0, i * 10 + 8, 10)
                   for i, c in enumerate("abcde")]
        w.select_box(1)

        indices = [w.listbox.get(i)[2:6] for i in range(w.listbox.size())]
        assert indices == ["0000", "0001", "0002", "0003", "0004"]


def test_a_seta_existe_na_fonte_da_lista():
    """
    `▶` (U+25B6) é o desenho óbvio e não existe na Consolas.

    O Tk não avisa: ele cai numa fonte de reserva, que não é monoespaçada, e a
    coluna sai do prumo. Este teste é a medição, não a suposição.
    """
    from PIL import Image as _Image, ImageDraw, ImageFont

    caminho = r"C:\Windows\Fonts\consola.ttf"
    if not os.path.exists(caminho):
        return                      # sem a fonte não há o que medir

    fonte = ImageFont.truetype(caminho, 20)

    def desenho(ch):
        im = _Image.new("L", (28, 32), 0)
        ImageDraw.Draw(im).text((2, 2), ch, font=fonte, fill=255)
        return im.tobytes()

    ausente = desenho("\ue123")     # área de uso privado: ninguém desenha
    from ui.main_window import MainWindow
    assert desenho(MainWindow.SETA_SELECAO) != ausente


# ----------------------------------------------------------------------
# Execução direta
# ----------------------------------------------------------------------

def _main():
    testes = [(n, o) for n, o in sorted(globals().items())
              if n.startswith("test_") and callable(o)]
    falhas = []
    for nome, fn in testes:
        try:
            fn()
            print(f"  PASS  {nome}")
        except Exception as e:
            falhas.append(nome)
            print(f"  FALHA {nome}\n          {type(e).__name__}: {e}")
    print(f"\n{len(testes) - len(falhas)}/{len(testes)} testes passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(_main())
