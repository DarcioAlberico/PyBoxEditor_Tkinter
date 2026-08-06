"""
Testes da F4.4 — a lista lateral deixa de ser refeita a cada tecla.

Era `delete(0,"end")` mais N `insert()` a **cada** `update_sidebar`, e
`select_box` chama isso a cada seleção: com 2.000 boxes, cada seta pressionada
refazia 2.000 linhas.

O que destrava é notar que **navegar não muda o conteúdo da lista**, só qual
linha está marcada. Guardando o que foi desenhado dá para comparar e não fazer
nada. Os testes medem isso contando as operações que chegam ao Listbox, com um
dublê no lugar dele — contar operações é estável, enquanto cronometrar numa
máquina compartilhada não é.

Rodar sem pytest:      python tests/test_f44_sidebar.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.box_model import BoxEntry
from ui import confidence as conf_ui


class ListboxDublê:
    """Conta o que a lista lateral manda fazer."""

    def __init__(self):
        self.itens = []
        self.deletes = 0
        self.inserts = 0
        self.itemconfigs = 0

    def delete(self, inicio, fim=None):
        self.deletes += 1
        if fim == "end":
            self.itens = []
        else:
            del self.itens[inicio]

    def insert(self, onde, texto):
        self.inserts += 1
        if onde == "end":
            self.itens.append(texto)
        else:
            self.itens.insert(onde, texto)

    def itemconfig(self, linha, **kw):
        self.itemconfigs += 1

    def selection_clear(self, *a):
        pass

    def select_set(self, linha):
        pass

    def see(self, linha):
        pass

    def zerar(self):
        self.deletes = self.inserts = self.itemconfigs = 0

    @property
    def operacoes(self):
        return self.deletes + self.inserts + self.itemconfigs


class JanelaFalsa:
    """
    Só o que `update_sidebar` toca.

    Chamar o método real na classe (`MainWindow.update_sidebar(self, ...)`) sem
    construir a janela inteira: subir o Tk de verdade traria menu, canvas e
    threads para um teste que é sobre contagem de operações de lista.
    """

    def __init__(self, boxes):
        self.boxes = boxes
        self.listbox = ListboxDublê()
        self.selected_index = -1
        self._visiveis = []
        self.filtro = None
        # Fora do dicionário (F9). Vazio por padrão: sem lista instalada o
        # `lexico.carregar` devolve léxico vazio e nada é sinalizado, que é o
        # contrato 6 da SPEC §5.8.
        self.suspeitos = set()

    # --- colaboradores que update_sidebar chama ---
    def _atualizar_origens(self):
        pass

    def _atualizar_contadores(self):
        pass

    def boxes_visiveis(self):
        if self.filtro is None:
            return list(range(len(self.boxes)))
        return [i for i in range(len(self.boxes)) if self.filtro(self.boxes[i])]

    def linha_do_box(self, indice):
        if indice in self._visiveis:
            return self._visiveis.index(indice)
        return None

    def boxes_suspeitos(self):
        return self.suspeitos

    # --- os métodos reais sob teste ---
    def _linha_da_lista(self, i, suspeitos=()):
        from ui.main_window import MainWindow
        return MainWindow._linha_da_lista(self, i, suspeitos)

    def update_sidebar(self):
        from ui.main_window import MainWindow
        return MainWindow.update_sidebar(self)


def _janela(n=2000):
    boxes = [BoxEntry(chr(97 + i % 26), i, i * 2, i + 15, i * 2 + 20)
             for i in range(n)]
    for b in boxes:
        b.confidence = 0.95
        b.source = "neural"
    return JanelaFalsa(boxes)


# ----------------------------------------------------------------------
# O ganho que a fase existe para dar
# ----------------------------------------------------------------------

def test_primeira_montagem_desenha_tudo():
    j = _janela(2000)
    j.update_sidebar()
    assert len(j.listbox.itens) == 2000
    assert j.listbox.inserts == 2000


def test_navegar_nao_refaz_a_lista():
    """
    O defeito: cada seta refazia 2.000 linhas. Trocar a seleção não muda o
    conteúdo, então o custo tem de ser ZERO operação de lista.
    """
    j = _janela(2000)
    j.update_sidebar()
    j.listbox.zerar()

    for i in range(10):          # dez setas
        j.selected_index = i
        j.update_sidebar()

    assert j.listbox.operacoes == 0, \
        f"navegar custou {j.listbox.operacoes} operações de lista"
    assert len(j.listbox.itens) == 2000, "a lista foi corrompida"


def test_editar_um_caractere_toca_so_uma_linha():
    j = _janela(2000)
    j.update_sidebar()
    j.listbox.zerar()

    j.boxes[500].char = "Z"
    j.update_sidebar()

    assert j.listbox.deletes == 1 and j.listbox.inserts == 1, \
        f"{j.listbox.deletes} deletes e {j.listbox.inserts} inserts para 1 edição"
    assert "'Z'" in j.listbox.itens[500]
    assert len(j.listbox.itens) == 2000


def test_mudanca_de_confianca_tambem_atualiza():
    """A cor e o rótulo saem da confiança; mudar ela tem de repintar a linha."""
    j = _janela(50)
    j.update_sidebar()
    j.listbox.zerar()

    j.boxes[7].confidence = 0.10
    j.update_sidebar()

    assert j.listbox.inserts == 1
    assert conf_ui.rotulo(j.boxes[7]) in j.listbox.itens[7]


def test_lista_continua_correta_apos_muitas_edicoes():
    j = _janela(200)
    j.update_sidebar()
    for i in range(0, 200, 7):
        j.boxes[i].char = "#"
        j.update_sidebar()

    esperado = [j._linha_da_lista(i)[0] for i in range(200)]
    assert j.listbox.itens == esperado


# ----------------------------------------------------------------------
# Quando o tamanho muda, refazer é o certo
# ----------------------------------------------------------------------

def test_box_novo_refaz_a_lista():
    j = _janela(100)
    j.update_sidebar()
    j.listbox.zerar()

    j.boxes.append(BoxEntry("x", 1, 1, 10, 10))
    j.update_sidebar()

    assert len(j.listbox.itens) == 101
    assert j.listbox.deletes == 1, "não refez de uma vez"


def test_filtro_que_corta_refaz_a_lista():
    j = _janela(100)
    j.update_sidebar()
    j.listbox.zerar()

    j.filtro = lambda b: b.char in "abc"
    j.update_sidebar()

    assert len(j.listbox.itens) < 100
    esperado = [j._linha_da_lista(i)[0] for i in j._visiveis]
    assert j.listbox.itens == esperado


def test_filtro_nao_confunde_linha_com_indice_de_box():
    """Com filtro, a linha 0 da lista não é o box 0 — o texto traz o índice real."""
    j = _janela(100)
    j.filtro = lambda b: b.char == "d"
    j.update_sidebar()

    assert j.listbox.itens, "o filtro não deixou nada"
    # A primeira coluna é a marca do léxico (F9); o índice vem depois dela.
    assert j.listbox.itens[0].lstrip("* ").startswith(f"{j._visiveis[0]:04d}")


def test_marca_do_lexico_e_uma_coluna_e_nao_a_cor():
    """
    Fora do dicionário aparece como coluna à esquerda, e a cor não muda.

    A cor é a confiança do caractere e o léxico é a palavra — dois eixos que a
    SPEC §5.8 mantém separados de propósito, porque o erro que só o dicionário
    pega é justamente o que veio com confiança alta. Se a marca virasse cor, ela
    apagaria o dado que já estava lá.
    """
    j = _janela(6)
    j.suspeitos = {2, 3}
    j.update_sidebar()

    marcados = [t[0] for t in j.listbox.itens]
    assert marcados == [" ", " ", "*", "*", " ", " "]
    # Todas com confiança 0,95: a cor continua a mesma nas seis.
    cores = {j._linha_da_lista(i, j.suspeitos)[1] for i in range(6)}
    assert cores == {conf_ui.COR_ALTA}


def test_linhas_continuam_alinhadas_com_e_sem_marca():
    """A coluna é fixa: sem isso a lista fica em zigue-zague ao rolar."""
    j = _janela(4)
    j.suspeitos = {1}
    j.update_sidebar()
    assert len({len(t) for t in j.listbox.itens}) == 1


def test_lista_vazia_nao_explode():
    j = _janela(0)
    j.update_sidebar()
    assert j.listbox.itens == []
    j.update_sidebar()


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
