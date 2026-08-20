"""
Testes da F1.4b — a correção automática da base de treino.

A F1.4 aprendeu a **acusar**: "'ç' está em formato antigo; o código atual
gravaria em 'sym_231', partindo a classe em duas". E parava aí. Quem lia o
diálogo tinha de abrir o Explorer, renomear pastas e arrastar PNG de uma para
outra — com o treino recusado até terminar. Na base real eram 4 erros e 126
amostras.

Aqui o mesmo diálogo passa a oferecer o conserto, e o "sim" do usuário é a
única coisa que ele precisa fazer.

Rodar sem pytest:      python tests/test_f14b_correcao_automatica.py
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import raiz_tk

import numpy as np
import tkinter as tk
from tkinter import messagebox

from core.dataset_check import Problema as _Problema
from core.dataset_check import validar_dataset
from core.services.learning_service import DatasetInvalido, LearningService


# ----------------------------------------------------------------------
# Apoio
# ----------------------------------------------------------------------

def _base_quebrada(pasta):
    """
    A base real do dia em que isto foi escrito, em miniatura.

    'ligature_ça' e 'ç' são de formato antigo, e 'ç' ainda colide com
    'sym_231' — os mesmos 4 erros que o diálogo mostrava.
    """
    from PIL import Image
    conteudo = {"ligature_ça": 6, "ç": 5, "sym_231": 7, "upper_A": 12}
    for k, (classe, n) in enumerate(conteudo.items()):
        d = os.path.join(pasta, classe)
        os.makedirs(d, exist_ok=True)
        img = np.full((32, 32), 255, dtype=np.uint8)
        img[8:24, 8:24] = 0
        img[2:6, 2 + k * 4:6 + k * 4] = 0
        for i in range(n):
            Image.fromarray(img).save(os.path.join(d, f"p{i:04d}_c050_{k}{i}.png"))
    return pasta


def _graves(pasta):
    return [p for p in validar_dataset(pasta, checar_pngs=False) if p.grave]


class _App:
    """
    Uma MainWindow de teste sobre uma base quebrada, com os diálogos dublados.

    `resposta` é o que o usuário responde ao "corrigir?" — os dois lados
    importam: quem aceita tem a base consertada, quem recusa tem a base
    intocada.
    """

    def __init__(self, resposta=True):
        from ui.main_window import MainWindow

        self.perguntas = []
        self.erros = []
        self.avisos = []
        self.resposta = resposta
        self.treinos = []

        self._info, self._erro, self._sim = (
            messagebox.showinfo, messagebox.showerror, messagebox.askyesno)
        messagebox.showinfo = lambda t, m="", **k: self.avisos.append((t, m))
        messagebox.showerror = lambda t, m="", **k: self.erros.append((t, m))
        messagebox.askyesno = self._askyesno

        self._tmp = tempfile.TemporaryDirectory()
        self.base = _base_quebrada(self._tmp.name)

        self.root = raiz_tk()
        self.win = MainWindow(self.root)
        self.win.learning_service = LearningService(
            data_dir=self.base,
            model_path=os.path.join(self.base, "modelo.pth"),
            meta_path=os.path.join(self.base, "meta.json"))
        # Treinar de verdade levaria minutos e não é o que está sob teste: o
        # que importa é a recusa da base, que vem da validação de verdade.
        self.win.learning_service.train_neural = self._train_neural

    def _train_neural(self, epochs=20, callback=None, should_stop=None, **k):
        self.treinos.append(epochs)
        graves = [p for p in self.win.learning_service.validar_dados() if p.grave]
        if graves:
            raise DatasetInvalido(graves)
        return True

    def _askyesno(self, titulo, msg="", **k):
        self.perguntas.append((titulo, msg))
        return self.resposta

    def aguardar(self, limite=60.0):
        """
        Bombeia o Tk até não haver mais tarefa — inclusive as encadeadas.

        A correção dispara o treino de dentro do `ao_concluir`, ainda na thread
        da UI: quando este laço volta a olhar, a tarefa seguinte já começou.
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
        self._tmp.cleanup()


def _sem_display():
    janela = raiz_tk()
    if janela is None:
        return True
    janela.destroy()
    return False


# ----------------------------------------------------------------------
# O caminho do treino
# ----------------------------------------------------------------------

def test_treino_recusado_pergunta_em_vez_de_mostrar_traceback():
    """
    Antes, a recusa chegava como 'DatasetInvalido: ...' — nome de exceção e
    uma lista que o usuário não tinha como responder de dentro do app.
    """
    if _sem_display():
        return
    with _App(resposta=False) as app:
        app.win._treinar_rede(epochs=1)
        app.aguardar()

        assert len(app.perguntas) == 1, app.perguntas
        titulo, msg = app.perguntas[0]
        assert "quarentena" in msg, "a pergunta não diz o que vai acontecer"
        assert "amostra é perdida" in msg
        assert not any("DatasetInvalido" in m for _, m in app.erros), app.erros


def test_sim_corrige_a_base_e_treina_sozinho():
    """O ponto da fase: um clique entre o erro e o treino."""
    if _sem_display():
        return
    with _App(resposta=True) as app:
        antes = sum(len(os.listdir(os.path.join(app.base, d)))
                    for d in os.listdir(app.base))
        assert _graves(app.base)

        app.win._treinar_rede(epochs=7)
        app.aguardar()

        assert not _graves(app.base), "a base continuou recusada"
        assert app.treinos == [7, 7], "o treino não foi refeito depois da correção"
        assert os.path.isdir(os.path.join(app.base, "ligature_hex_00e70061"))
        assert not os.path.exists(os.path.join(app.base, "ç"))

        depois = sum(len(os.listdir(os.path.join(app.base, d)))
                     for d in os.listdir(app.base))
        assert depois == antes, "a correção perdeu amostra"


def test_nao_corrige_sem_o_usuario_mandar():
    """A base é dado do usuário: o pedido de treino não autoriza mexer nela."""
    if _sem_display():
        return
    with _App(resposta=False) as app:
        app.win._treinar_rede(epochs=1)
        app.aguardar()

        assert os.path.isdir(os.path.join(app.base, "ç")), "mexeu sem permissão"
        # Os dois nomes antigos e a colisão de 'ç' com 'sym_231', intactos.
        assert len(_graves(app.base)) == 3, [str(p) for p in _graves(app.base)]
        assert app.treinos == [1], "treinou com a base recusada"


def test_correcao_incompleta_nao_finge_que_deu_certo():
    """
    Se a base continua recusada, o treino não recomeça e o usuário fica
    sabendo — anunciar "corrigido!" e travar de novo é o pior dos dois mundos.
    """
    if _sem_display():
        return
    with _App(resposta=True) as app:
        app.win.learning_service.sanear_dados = lambda **k: ["nada feito"]

        app.win._treinar_rede(epochs=1)
        app.aguardar()

        assert len(app.perguntas) == 1, "perguntou de novo depois de corrigir"
        assert app.erros, "a correção fracassada passou calada"
        assert "ainda não está pronta" in app.erros[0][1]
        assert app.treinos == [1], "treinou com a base ainda recusada"


def test_recusa_depois_da_correcao_nao_vira_laco():
    """
    Base saneada e treino recusado assim mesmo: o problema não é dos que a
    correção resolve, e reperguntar seria um vaivém sem fim.
    """
    if _sem_display():
        return
    with _App(resposta=True) as app:
        def sempre_recusa(epochs=20, callback=None, should_stop=None, **k):
            app.treinos.append(epochs)
            raise DatasetInvalido(_graves(app.base) or [
                _Problema("nome_invalido", "outra_coisa", "problema teimoso")])

        app.win.learning_service.train_neural = sempre_recusa

        app.win._treinar_rede(epochs=1)
        app.aguardar()

        assert not _graves(app.base), "a correção não rodou"
        assert app.treinos == [1, 1], "o treino não foi refeito"
        assert len(app.perguntas) == 1, "perguntou de novo depois de corrigir"
        assert any("problema teimoso" in m for _, m in app.erros), app.erros


# ----------------------------------------------------------------------
# O caminho do diagnóstico
# ----------------------------------------------------------------------

def test_verificar_base_oferece_o_conserto():
    """O diálogo da verificação era um beco: listava os 4 erros e o botão OK."""
    if _sem_display():
        return
    with _App(resposta=True) as app:
        app.win.verificar_base_treino()
        app.aguardar()

        assert app.perguntas, "a verificação não ofereceu corrigir"
        assert "impedem o treino" in app.perguntas[0][1]
        assert not _graves(app.base)


def test_verificar_base_sa_nao_pergunta_nada():
    if _sem_display():
        return
    with _App(resposta=True) as app:
        app.win.learning_service.sanear_dados()
        app.perguntas.clear()

        app.win.verificar_base_treino()
        app.aguardar()

        assert not app.perguntas
        assert app.avisos, "nada foi dito ao usuário"


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
