"""A janela da fila de suspeitas (2026-09-19; `docs/REVISAO_MODOS_OCR.md`, §5.2).

O estado é da `ReviewSession` (`tests/test_fila_de_suspeitas.py`); aqui se
fixa o que a janela faz com ele: lista os itens com tipo e motivo em
português, mostra as linhas do bloco com as duas leituras e o recorte da
página, troca uma linha pela leitura do motor, aceita semelhantes depois de
mostrar a amostra, abre o diagrama e devolve o FEN ao documento, desfaz em
pilha, exporta pelo callback de quem a abriu — e não aceita o bloco quando o
`a` foi digitado no campo de texto.

A janela é construída sem `mostrar()` (`grab_set` numa janela escondida) e
operada pelos widgets, como um usuário faria.
"""

import numpy as np
import pytest

from conftest import raiz_tk
from core import livro
from core.editorial_adapters import paginas_extraidas_para_documento
from core.editorial_review import ReviewSession
from ui.dialogo_revisao_editorial import (DialogoRevisaoEditorial, _recortar,
                                          _texto_do_valor, _valor_do_texto)
from tests.test_fila_de_suspeitas import _pagina


class _Janela:
    def __init__(self, paginas=None, **kw):
        self.raiz = raiz_tk()
        if self.raiz is None:
            pytest.skip("sem display")
        documento = paginas_extraidas_para_documento(paginas or [_pagina()], document_id="livro")
        self.sessao = ReviewSession(documento)
        self.imagens = []
        argumentos = dict(imagem_da_pagina=self._imagem)
        argumentos.update(kw)
        self.janela = DialogoRevisaoEditorial(self.raiz, self.sessao, **argumentos)
        self.janela.withdraw()
        self.janela.update_idletasks()

    def _imagem(self, indice):
        self.imagens.append(indice)
        return np.full((1600, 1200), 255, dtype=np.uint8)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        try:
            self.janela.destroy()
            self.raiz.destroy()
        except Exception:
            pass

    def linhas_da_fila(self):
        return [self.janela.tree.item(i)["values"] for i in self.janela.tree.get_children()]

    def selecionar(self, target_id):
        self.janela.tree.selection_set(target_id)
        self.janela._show_selected()


def test_a_fila_lista_tipo_pagina_e_motivo_em_portugues():
    with _Janela() as j:
        valores = j.linhas_da_fila()
        assert [v[0] for v in valores] == ["diagrama", "tabela", "parágrafo"]
        assert valores[0][1] == 30 and valores[0][3] == "sem solução"
        assert valores[2][4] == "«25♖xc7!» tem figurina mas não tem forma de lance"
        assert j.janela.var_contagem.get() == "3 de 3 pendente(s)"


def test_selecionar_mostra_as_linhas_o_recorte_e_as_duas_leituras():
    with _Janela() as j:
        j.selecionar("block-livro-p0030-b0000")
        assert "parágrafo · página 30" in j.janela.summary.cget("text")
        assert "tem figurina" in j.janela.lbl_motivos.cget("text")
        linhas = j.janela.tree_linhas.get_children()
        assert len(linhas) == 2
        assert "suspeita" in j.janela.tree_linhas.item(linhas[0])["tags"]
        # A primeira linha suspeita já vem selecionada, com as duas leituras.
        assert j.janela.tree_linhas.selection() == (linhas[0],)
        j.janela._show_line()
        assert j.janela.lbl_ancora.cget("text").startswith("25♖xc7! A1nazing]y")
        assert j.janela.lbl_motor.cget("text").startswith("25.8xc7! Amazingly")
        assert "disabled" not in j.janela.btn_motor.state()
        assert j.janela.lbl_recorte.cget("image") != "" and set(j.imagens) == {29}
        assert j.janela.detail.get("1.0", "end-1c").startswith("25♖xc7!")


def test_sem_imagem_a_janela_diz_e_segue():
    with _Janela(imagem_da_pagina=None) as j:
        j.selecionar("block-livro-p0030-b0000")
        assert j.janela.lbl_recorte.cget("text") == "(sem imagem da página)"


def test_usar_o_motor_troca_a_linha_e_tira_o_bloco_da_fila():
    with _Janela() as j:
        j.selecionar("block-livro-p0030-b0000")
        j.janela._show_line()
        j.janela._usar_leitura("motor")
        assert "block-livro-p0030-b0000" not in j.janela.tree.get_children()
        bloco = next(b for p in j.sessao.document.pages for b in p.blocks
                     if b.id == "block-livro-p0030-b0000")
        assert bloco.decision.value.startswith("25.8xc7! Amazingly")
        assert j.janela.botoes["Desfazer"].cget("text") == "Desfazer (1) [Ctrl+Z]"
        j.janela._undo()
        assert "block-livro-p0030-b0000" in j.janela.tree.get_children()


def test_salvar_a_edicao_do_valor_registra_o_texto_digitado():
    with _Janela() as j:
        j.selecionar("block-livro-p0030-b0000")
        j.janela.detail.delete("1.0", "end")
        j.janela.detail.insert("1.0", "Texto corrigido à mão.")
        j.janela._edit()
        bloco = next(b for p in j.sessao.document.pages for b in p.blocks
                     if b.id == "block-livro-p0030-b0000")
        assert bloco.decision.value == "Texto corrigido à mão."
        assert bloco.decision.status == "reviewed"


def test_a_tecla_solta_nao_vale_com_o_foco_no_texto(monkeypatch):
    with _Janela() as j:
        j.selecionar("block-livro-p0030-b0000")
        monkeypatch.setattr(j.janela, "focus_get", lambda: j.janela.detail)
        j.janela._atalho(j.janela._accept)
        assert "block-livro-p0030-b0000" in j.janela.tree.get_children()
        monkeypatch.setattr(j.janela, "focus_get", lambda: j.janela.tree)
        j.janela._atalho(j.janela._accept)
        assert "block-livro-p0030-b0000" not in j.janela.tree.get_children()


def test_aceitar_semelhantes_mostra_a_amostra_e_desfaz_num_passo(monkeypatch):
    with _Janela([_pagina(1), _pagina(2)]) as j:
        perguntas = []
        monkeypatch.setattr(j.janela, "confirmar_lote",
                            lambda quantos, exemplos, item: perguntas.append((quantos, exemplos)) or True)
        j.selecionar("block-livro-p0002-b0000")
        j.janela._batch()
        assert perguntas[0][0] == 2 and "p. 2:" in perguntas[0][1] and "p. 3:" in perguntas[0][1]
        restantes = [v[0] for v in j.linhas_da_fila()]
        assert "parágrafo" not in restantes
        assert j.janela.botoes["Desfazer"].cget("text") == "Desfazer (1) [Ctrl+Z]"
        j.janela._undo()
        assert [v[0] for v in j.linhas_da_fila()].count("parágrafo") == 2


def test_o_diagrama_abre_pelo_callback_e_o_fen_volta_para_o_documento():
    chamadas = []

    def abrir(item, imagem):
        chamadas.append((item.target_id, None if imagem is None else imagem.shape))
        return "8/8/8/8/8/8/4k3/4K3 w - - 0 1"

    with _Janela(abrir_diagrama=abrir) as j:
        j.selecionar("block-livro-p0030-b0003")
        assert "disabled" not in j.janela.botoes["Diagrama"].state()
        j.janela._diagrama()
        assert chamadas == [("block-livro-p0030-b0003", (1600, 1200))]
        bloco = next(b for p in j.sessao.document.pages for b in p.blocks
                     if b.id == "block-livro-p0030-b0003")
        assert bloco.decision.value["fen"] == "8/8/8/8/8/8/4k3/4K3 w - - 0 1"
        assert bloco.decision.value["origin"] == "recorte"
        assert bloco.decision.status == "reviewed"
        assert "block-livro-p0030-b0003" not in j.janela.tree.get_children()


def test_sem_callback_do_diagrama_o_botao_fica_desligado():
    with _Janela() as j:
        j.selecionar("block-livro-p0030-b0003")
        assert "disabled" in j.janela.botoes["Diagrama"].state()


def test_exportar_com_as_correcoes_entrega_o_documento_revisado():
    exportados = []
    with _Janela(ao_exportar=exportados.append) as j:
        j.selecionar("block-livro-p0030-b0002")
        j.janela._accept()
        j.janela._exportar()
        assert exportados[0] is j.sessao.document
        assert len(exportados[0].review_events) == 1
    with _Janela() as j:
        assert not hasattr(j.janela, "btn_exportar")


def test_os_filtros_por_pagina_tipo_e_teto():
    with _Janela([_pagina(1), _pagina(2)]) as j:
        assert len(j.linhas_da_fila()) == 6
        j.janela.var_pagina.set("2")
        j.janela._refresh()
        assert [v[1] for v in j.linhas_da_fila()] == [2, 2, 2]
        j.janela.var_tipo.set("table")
        j.janela._refresh()
        assert [v[0] for v in j.linhas_da_fila()] == ["tabela"]
        assert j.janela.var_contagem.get() == "1 de 6 pendente(s)"
        j.janela.var_pagina.set("todas")
        j.janela.var_tipo.set("todos")
        j.janela.var_limite.set("1")
        j.janela._refresh()
        assert [v[0] for v in j.linhas_da_fila()] == ["diagrama", "diagrama"]


def test_proximo_anda_pela_fila_e_da_a_volta():
    with _Janela() as j:
        ids = list(j.janela.tree.get_children())
        j.janela.tree.selection_set(ids[0])
        j.janela._next()
        assert j.janela.tree.selection() == (ids[1],)
        j.janela.tree.selection_set(ids[-1])
        j.janela._next()
        assert j.janela.tree.selection() == (ids[0],)


def test_o_recorte_cabe_na_tela_e_a_linha_e_ampliada():
    pagina = np.full((1000, 2000), 200, dtype=np.uint8)
    bloco = _recortar(pagina, (0, 100, 2000, 400))
    assert bloco.width <= 640 and bloco.height <= 260
    linha = _recortar(pagina, (100, 100, 300, 130), ampliar=2.5)
    assert linha.width == int((200 + 12) * 2.5)
    assert _recortar(pagina, None) is None and _recortar(None, (0, 0, 1, 1)) is None


def test_o_valor_vai_e_volta_do_texto_para_tabela_e_diagrama():
    from core.editorial_review import ReviewItem
    base = dict(document_id="d", page_id="p", page_index=0, original_value=None,
                status="automatic", confidence=1.0, severity=1)
    tabela = ReviewItem(target_id="t", kind="table", value={"rows": [["a", "b"], ["c", ""]]}, **base)
    assert _texto_do_valor(tabela) == "a | b\nc | "
    assert _valor_do_texto(tabela, "a | x\nc | d") == {"rows": [["a", "x"], ["c", "d"]]}
    diagrama = ReviewItem(target_id="g", kind="diagram", value={"fen": "8/8 w", "origin": "render"},
                          **base)
    assert _texto_do_valor(diagrama) == "8/8 w"
    assert _valor_do_texto(diagrama, " 4k3/8 b ") == {"fen": "4k3/8 b", "origin": "render"}


def test_a_janela_tambem_abre_com_o_documento_de_uma_figura_sem_caixa():
    pagina = livro.PaginaExtraida(numero=0, blocos=[
        livro.Figura(b"png", 8, 8, origem="recorte", aviso="sem tabuleiro")])
    with _Janela([pagina]) as j:
        j.selecionar("block-livro-p0001-b0000")
        assert j.janela.lbl_recorte.cget("text") == "(bloco sem caixa na página)"
