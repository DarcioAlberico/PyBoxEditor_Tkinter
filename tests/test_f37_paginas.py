"""
Testes da F3.7 — persistência de boxes por página e aviso de trabalho não salvo.

O defeito original: `_load_pdf_page` fazia `self.boxes = []` sem aviso nenhum.
Virar a página do PDF apagava tudo que havia sido digitado, em silêncio.

Rodar sem pytest:      python tests/test_f37_paginas.py
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import raiz_tk

import fitz
import tkinter as tk
from tkinter import messagebox
from PIL import Image

from core.box_model import BoxEntry
from core.services.document_service import DocumentSession


# ----------------------------------------------------------------------
# Apoio
# ----------------------------------------------------------------------

def _pdf_de_teste(caminho, paginas=3):
    doc = fitz.open()
    for i in range(paginas):
        pg = doc.new_page()
        pg.insert_text((60, 80), f"Pagina {i + 1} ABC", fontsize=18)
    doc.save(caminho)
    doc.close()
    return caminho


class _App:
    """MainWindow com os diálogos neutralizados (bloqueiam em teste)."""

    def __init__(self, descartar=True):
        from ui.main_window import MainWindow
        self.perguntas = []
        self._descartar = descartar

        self._info, self._erro, self._sim = (
            messagebox.showinfo, messagebox.showerror, messagebox.askyesno)
        messagebox.showinfo = lambda t, m, **k: None
        messagebox.showerror = lambda t, m, **k: None
        messagebox.askyesno = self._askyesno

        self.root = raiz_tk()
        self.win = MainWindow(self.root)

    def _askyesno(self, titulo, msg, **k):
        self.perguntas.append((titulo, msg))
        return self._descartar

    def aguardar(self, limite=60.0):
        """
        Bombeia o laço do Tk até a tarefa de fundo terminar.

        Necessário desde a F4.1: renderizar página do PDF passou a rodar em
        thread (medido em ~950 ms), então open_pdf/next_page/prev_page voltam
        antes de a página estar carregada.
        """
        fim = time.time() + limite
        self.root.update()
        while self.win.task.is_running() and time.time() < fim:
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        assert not self.win.task.is_running(), "tarefa nao terminou no tempo"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        messagebox.showinfo, messagebox.showerror, messagebox.askyesno = (
            self._info, self._erro, self._sim)
        try:
            self.win.task.shutdown()
            self.win.status.end_task()
            self.root.update()
        except Exception:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass


# ----------------------------------------------------------------------
# DocumentSession — unidade
# ----------------------------------------------------------------------

def test_sessao_guarda_boxes_por_pagina():
    s = DocumentSession("/tmp/livro.pdf", num_pages=10, is_pdf=True)

    s.store(0, [BoxEntry("a", 0, 0, 5, 5)])
    s.store(4, [BoxEntry("b", 0, 0, 5, 5), BoxEntry("c", 6, 0, 9, 5)])

    assert [b.char for b in s.boxes_for(0)] == ["a"]
    assert [b.char for b in s.boxes_for(4)] == ["b", "c"]
    assert s.boxes_for(7) == []              # não visitada
    assert s.pages_with_boxes() == [0, 4]
    assert s.total_boxes() == 3


def test_sessao_rastreia_paginas_sujas():
    s = DocumentSession("/tmp/livro.pdf", num_pages=5, is_pdf=True)
    assert not s.is_dirty()

    s.store(1, [BoxEntry("a", 0, 0, 5, 5)])
    s.mark_dirty(1)
    assert s.is_dirty() and s.dirty_pages() == [1]

    s.store(2, [BoxEntry("b", 0, 0, 5, 5)])
    s.mark_dirty(2)
    assert s.dirty_pages() == [1, 2]

    s.mark_saved(1)
    assert s.dirty_pages() == [2]

    s.mark_saved()
    assert not s.is_dirty()


def test_page_stem():
    pdf = DocumentSession(os.path.join("dir", "livro.pdf"), num_pages=200, is_pdf=True)
    assert pdf.page_stem(0).endswith("livro_pg001")
    assert pdf.page_stem(10).endswith("livro_pg011")

    img = DocumentSession(os.path.join("dir", "foto.png"), is_pdf=False)
    assert img.page_stem(0).endswith("foto")


# ----------------------------------------------------------------------
# O bug original: virar a página apagava tudo
# ----------------------------------------------------------------------

def test_virar_pagina_preserva_boxes():
    """Era: `self.boxes = []` em _load_pdf_page descartava o trabalho."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=3)

        with _App() as app:
            w = app.win
            w.open_pdf(pdf)
            app.aguardar()
            assert w.current_pdf_page == 0

            w.boxes.append(BoxEntry("X", 10, 10, 20, 20))
            w._commit_change()

            w.next_page()                                   # <- apagava aqui
            app.aguardar()
            assert w.current_pdf_page == 1
            assert w.boxes == [], "página nova deve começar vazia"

            w.boxes.append(BoxEntry("Y", 30, 30, 40, 40))
            w._commit_change()

            w.prev_page()
            app.aguardar()
            assert w.current_pdf_page == 0
            assert [b.char for b in w.boxes] == ["X"], "o trabalho da página 1 sumiu"

            w.next_page()
            app.aguardar()
            assert [b.char for b in w.boxes] == ["Y"], "o trabalho da página 2 sumiu"


def test_navegacao_arquiva_na_pagina_certa():
    """prev_page/next_page não podem mexer em current_pdf_page antes de
    _load_pdf_page — senão o trabalho é arquivado sob o índice errado."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=3)

        with _App() as app:
            w = app.win
            w.open_pdf(pdf)
            app.aguardar()

            for esperado in ("P0", "P1", "P2"):
                w.boxes.append(BoxEntry(esperado, 1, 1, 9, 9))
                w._commit_change()
                if esperado != "P2":
                    w.next_page()
                    app.aguardar()
            app.aguardar()

            for pagina, esperado in enumerate(("P0", "P1", "P2")):
                assert [b.char for b in w.session.boxes_for(pagina)] == [esperado], \
                    f"página {pagina} guardou o conteúdo errado"


# ----------------------------------------------------------------------
# Aviso de trabalho não salvo
# ----------------------------------------------------------------------

def test_titulo_marca_nao_salvo():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=2)

        with _App() as app:
            w = app.win
            w.open_pdf(pdf)
            app.aguardar()
            assert "*" not in w.parent.title()

            w.boxes.append(BoxEntry("A", 1, 1, 9, 9))
            w._commit_change()
            assert w.parent.title().endswith("*"), "faltou o marcador de não salvo"
            assert "livro.pdf" in w.parent.title()


def test_avisa_antes_de_descartar():
    """Abrir outro documento com trabalho pendente precisa perguntar."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=2)
        img = os.path.join(tmp, "outra.png")
        Image.new("L", (50, 50), color=255).save(img)

        with _App(descartar=True) as app:
            w = app.win
            w.open_pdf(pdf)
            app.aguardar()
            w.boxes.append(BoxEntry("A", 1, 1, 9, 9))
            w._commit_change()

            w.open_image(img)
            assert len(app.perguntas) == 1, "abriu outro arquivo sem avisar"
            assert "não salvas" in app.perguntas[0][1]


def test_recusar_descarte_cancela_abertura():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=2)
        img = os.path.join(tmp, "outra.png")
        Image.new("L", (50, 50), color=255).save(img)

        with _App(descartar=False) as app:
            w = app.win
            w.open_pdf(pdf)
            app.aguardar()
            w.boxes.append(BoxEntry("A", 1, 1, 9, 9))
            w._commit_change()

            w.open_image(img)
            assert w.session.is_pdf, "dizer 'não' deveria manter o PDF aberto"
            assert [b.char for b in w.boxes] == ["A"], "o trabalho foi perdido"


# ----------------------------------------------------------------------
# Salvar todas as páginas
# ----------------------------------------------------------------------

def test_salvar_todas_as_paginas():
    """Contrapartida da persistência: o trabalho acumulado precisa ter como sair."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=3)

        with _App() as app:
            w = app.win
            w.open_pdf(pdf)
            app.aguardar()

            w.boxes.append(BoxEntry("A", 10, 10, 20, 20))
            w._commit_change()
            w.next_page()
            app.aguardar()
            w.next_page()                                   # pula a página 2
            app.aguardar()
            w.boxes.append(BoxEntry("C", 10, 10, 20, 20))
            w._commit_change()

            assert w.session.dirty_pages() == [0, 2]
            w.save_all_pages()
            app.aguardar()

            assert os.path.exists(os.path.join(tmp, "livro_pg001.box"))
            assert os.path.exists(os.path.join(tmp, "livro_pg001.png"))
            assert os.path.exists(os.path.join(tmp, "livro_pg003.box"))
            assert not os.path.exists(os.path.join(tmp, "livro_pg002.box")), \
                "página sem boxes não deve gerar arquivo"

            assert not w.session.is_dirty(), "salvar deveria limpar o estado sujo"
            assert "*" not in w.parent.title()

            conteudo = open(os.path.join(tmp, "livro_pg003.box"), encoding="utf-8").read()
            assert conteudo.startswith("C "), f"conteúdo inesperado: {conteudo!r}"


def test_salvar_pagina_atual_nao_limpa_as_outras():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=2)

        with _App() as app:
            w = app.win
            w.open_pdf(pdf)
            app.aguardar()
            w.boxes.append(BoxEntry("A", 10, 10, 20, 20))
            w._commit_change()
            w.next_page()
            app.aguardar()
            w.boxes.append(BoxEntry("B", 10, 10, 20, 20))
            w._commit_change()

            w._save_box_to_path(os.path.join(tmp, "so_a_pagina_2.box"))

            assert w.session.dirty_pages() == [0], \
                "salvar uma página não pode marcar as outras como salvas"
            assert w.parent.title().endswith("*")


def test_o_dialogo_propoe_o_livro_e_a_pagina():
    """
    Era: o nome vinha de `image_path`, que num PDF é o rótulo `livro.pdf
    [Pág 11]`. O `splitext` disso devolve 'livro' — a página sumia e todas as
    páginas propunham `livro.box`, então salvar a segunda oferecia sobrescrever
    a primeira (e o `.png` do par junto).
    """
    from tkinter import filedialog

    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=12)
        salvo, visto = filedialog.asksaveasfilename, {}
        filedialog.asksaveasfilename = lambda **k: (visto.update(k), "")[1]
        try:
            with _App() as app:
                w = app.win
                w.open_pdf(pdf)
                app.aguardar()
                w.ir_para_pagina(11)
                app.aguardar()
                w.boxes.append(BoxEntry("A", 10, 10, 20, 20))
                w._commit_change()

                w.save_box_file()

                assert visto["initialfile"] == "livro_pg011.box", \
                    f"propôs {visto.get('initialfile')!r}"
                assert visto["initialdir"] == tmp, "abriu na pasta errada"

                # O mesmo destino que 'Salvar todas as páginas' gravaria: as
                # duas rotas não podem divergir de nome.
                assert (os.path.join(visto["initialdir"], visto["initialfile"])
                        == w.session.page_stem(w.current_pdf_page) + ".box")
        finally:
            filedialog.asksaveasfilename = salvo


# ----------------------------------------------------------------------
# Execução direta
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# Ir direto para uma página (F3.9)
# ----------------------------------------------------------------------

def test_ir_para_pagina_escolhida():
    """Num livro de 300 páginas, 'próxima' 107 vezes não é um caminho."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=12)
        with _App() as app:
            app.win.open_pdf(pdf)
            app.aguardar()

            app.win.ir_para_pagina(9)
            app.aguardar()
            assert app.win.current_pdf_page == 8, "devia estar na 9a página"
            assert "9/12" in app.win.lbl_page_info.cget("text")


def test_o_numero_digitado_e_o_que_o_usuario_ve():
    """1 é a primeira página. Trocar por índice levaria à página errada calado."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=5)
        with _App() as app:
            app.win.open_pdf(pdf)
            app.aguardar()

            app.win.entry_pagina.delete(0, "end")
            app.win.entry_pagina.insert(0, "3")
            app.win.ir_para_pagina()
            app.aguardar()
            assert app.win.current_pdf_page == 2


def test_pagina_fora_da_faixa_avisa_e_nao_navega():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=4)
        avisos = []
        with _App() as app:
            messagebox.showinfo = lambda t, m, **k: avisos.append(m)
            app.win.open_pdf(pdf)
            app.aguardar()

            for entrada in (0, 5, -1):
                app.win.ir_para_pagina(entrada)
                app.aguardar()
                assert app.win.current_pdf_page == 0
            assert len(avisos) == 3
            assert "4 página" in avisos[0]


def test_texto_que_nao_e_numero_avisa():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=3)
        avisos = []
        with _App() as app:
            messagebox.showinfo = lambda t, m, **k: avisos.append(m)
            app.win.open_pdf(pdf)
            app.aguardar()

            app.win.entry_pagina.delete(0, "end")
            app.win.entry_pagina.insert(0, "cento e oito")
            app.win.ir_para_pagina()
            assert avisos and "não é um número" in avisos[0]
            assert app.win.current_pdf_page == 0


def test_campo_vazio_nao_faz_nada():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=3)
        avisos = []
        with _App() as app:
            messagebox.showinfo = lambda t, m, **k: avisos.append(m)
            app.win.open_pdf(pdf)
            app.aguardar()
            app.win.entry_pagina.delete(0, "end")
            app.win.ir_para_pagina()
            assert avisos == []


def test_sem_pdf_o_campo_fica_desligado():
    with _App() as app:
        assert str(app.win.entry_pagina.cget("state")) == "disabled"
        assert str(app.win.btn_ir.cget("state")) == "disabled"


def test_o_campo_liga_ao_abrir_o_pdf():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=3)
        with _App() as app:
            app.win.open_pdf(pdf)
            app.aguardar()
            assert str(app.win.entry_pagina.cget("state")) == "normal"
            assert str(app.win.btn_ir.cget("state")) == "normal"


def test_ir_para_a_pagina_em_que_ja_esta_nao_recarrega():
    """Recarregar custa uma renderização e descartaria o histórico da página."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=3)
        with _App() as app:
            app.win.open_pdf(pdf)
            app.aguardar()
            app.win.boxes = [BoxEntry("z", 1, 1, 9, 9)]
            app.win.ir_para_pagina(1)
            app.aguardar()
            assert [b.char for b in app.win.boxes] == ["z"]


def test_o_trabalho_da_pagina_sobrevive_ao_salto():
    """Mesma garantia da F3.7, agora pelo caminho novo."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=6)
        with _App() as app:
            app.win.open_pdf(pdf)
            app.aguardar()
            app.win.boxes = [BoxEntry("Q", 5, 5, 15, 15)]
            app.win._commit_change()

            app.win.ir_para_pagina(5)
            app.aguardar()
            assert app.win.boxes == []

            app.win.ir_para_pagina(1)
            app.aguardar()
            assert [b.char for b in app.win.boxes] == ["Q"]


def test_atalho_ctrl_g_esta_ligado():
    with _App() as app:
        assert "<Control-Key-g>" in app.win.parent.bind()


def test_virar_pagina_com_tarefa_rodando_explica_em_vez_de_ignorar():
    """
    Antes devolvia em silêncio: pelo teclado ou pelo campo, o usuário apertava
    e nada acontecia — e a leitura natural é que virar a página quebrou.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=3)
        with _App() as app:
            app.win.open_pdf(pdf)
            app.aguardar()

            app.win.task.is_running = lambda: True
            try:
                app.win.ir_para_pagina(3)
                assert "Aguarde" in app.win.status.lbl.cget("text")
                assert app.win.current_pdf_page == 0
            finally:
                del app.win.task.is_running


# ----------------------------------------------------------------------
# O botão que sumia (F3.9)
# ----------------------------------------------------------------------

def test_a_janela_cabe_na_tela():
    """
    `geometry("1600x900")` fixo numa tela de 1360x768 punha o lado direito da
    janela fora do monitor — e é lá que ficava o botão de avançar página.
    """
    import appy

    with _App() as app:
        raiz = app.root
        largura, resto = appy._geometria_que_cabe(raiz).split("x")
        altura = resto.split("+")[0]
        assert int(largura) <= raiz.winfo_screenwidth()
        assert int(altura) <= raiz.winfo_screenheight()


def test_a_janela_nao_encolhe_a_ponto_de_sumir_controle():
    import appy

    assert appy.LARGURA_MINIMA >= 1024
    assert appy.ALTURA_MINIMA >= 640


def test_os_controles_de_pagina_ficam_juntos_e_primeiro():
    """
    A ordem de empacotamento é a ordem de sobrevivência: o Tk corta quem entrou
    por último. Os botões precisam estar no primeiro grupo.
    """
    with _App() as app:
        w = app.win
        grupo = w.btn_prev_page.master
        assert w.btn_next_page.master is grupo, "os dois botões no mesmo grupo"
        assert w.entry_pagina.master is grupo, "o campo 'ir para' junto deles"
        assert w.nav_frame.pack_slaves()[0] is grupo, "o grupo tem de vir primeiro"


def test_o_grupo_de_controles_cabe_numa_barra_estreita():
    with _App() as app:
        app.root.update()
        exigido = app.win.btn_prev_page.master.winfo_reqwidth()
        assert exigido < 500, f"os controles exigem {exigido} px, largo demais"


def test_o_rotulo_de_pagina_nao_cresce_com_o_uso():
    """
    Ele ficava entre os dois botões e chegava a 381 px — era o que empurrava o
    'Próxima' para fora. O detalhe da sessão foi para um rótulo próprio.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _pdf_de_teste(os.path.join(tmp, "livro.pdf"), paginas=8)
        with _App() as app:
            app.win.open_pdf(pdf)
            app.aguardar()

            curto = app.win.lbl_page_info.cget("text")
            for p in range(6):
                app.win.session.store(p, [BoxEntry("a", 0, 0, 5, 5)] * 200)
            app.win._update_nav_controls()

            assert app.win.lbl_page_info.cget("text") == curto
            assert "pág. com boxes" in app.win.lbl_sessao.cget("text")


def test_o_detalhe_da_sessao_e_o_ultimo_a_ser_cortado():
    with _App() as app:
        assert app.win.nav_frame.pack_slaves()[-1] is app.win.lbl_sessao


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
