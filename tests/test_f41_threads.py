"""
Testes da F4.1 — trabalho pesado fora da thread da interface.

Antes, todo processamento longo rodava na thread do Tkinter com
`parent.update()` no meio do laço: a janela era marcada como "Não Responde",
não havia como cancelar, e o `update()` reentrante podia reentrar num handler
no meio da mutação da lista de boxes.

Rodar sem pytest:      python tests/test_f41_threads.py
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk

from core.services.task_service import BackgroundTask, Cancelled


# ----------------------------------------------------------------------
# Apoio
# ----------------------------------------------------------------------

class _Raiz:
    def __enter__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.task = BackgroundTask(self.root, poll_ms=10)
        return self

    def __exit__(self, *a):
        try:
            self.task.shutdown()
            self.root.update()
        except Exception:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def bombear(self, ate, limite=30.0):
        """Roda o laço do Tk até `ate()` ou estourar o tempo. Conta os ciclos."""
        ciclos = 0
        fim = time.time() + limite
        while not ate() and time.time() < fim:
            self.root.update()
            ciclos += 1
            time.sleep(0.005)
        self.root.update()
        return ciclos


# ----------------------------------------------------------------------
# O ponto central: a UI não fica bloqueada
# ----------------------------------------------------------------------

def test_start_devolve_o_controle_na_hora():
    """O critério da F4.1: nenhuma operação bloqueia a UI.

    Um trabalho de ~0,6 s tem que devolver o controle em milissegundos.
    """
    with _Raiz() as r:
        pronto = {}

        t0 = time.perf_counter()
        r.task.start(lambda h: time.sleep(0.6) or "fim",
                     on_done=lambda res: pronto.update(res=res))
        decorrido = (time.perf_counter() - t0) * 1000

        assert decorrido < 100, f"start() bloqueou por {decorrido:.0f} ms"

        ciclos = r.bombear(lambda: "res" in pronto)
        assert pronto["res"] == "fim"
        assert ciclos > 10, (
            f"a UI só rodou {ciclos} ciclos durante o trabalho — sinal de bloqueio")


def test_trabalho_roda_em_outra_thread():
    with _Raiz() as r:
        capturado = {}
        principal = threading.get_ident()

        r.task.start(lambda h: threading.get_ident(),
                     on_done=lambda tid: capturado.update(tid=tid))
        r.bombear(lambda: "tid" in capturado)

        assert capturado["tid"] != principal, "o trabalho rodou na thread da UI"


def test_callbacks_rodam_na_thread_da_ui():
    """Só a thread da UI pode tocar em widget — os callbacks precisam voltar
    para ela."""
    with _Raiz() as r:
        threads = {"progresso": [], "done": None}
        principal = threading.get_ident()

        def trabalho(h):
            for i in range(3):
                h.progress(i + 1, 3)
                time.sleep(0.02)
            return "ok"

        r.task.start(
            trabalho,
            on_progress=lambda a, t, m="": threads["progresso"].append(threading.get_ident()),
            on_done=lambda _: threads.update(done=threading.get_ident()),
        )
        r.bombear(lambda: threads["done"] is not None)

        assert threads["done"] == principal
        assert threads["progresso"], "nenhum progresso chegou"
        assert all(t == principal for t in threads["progresso"])


# ----------------------------------------------------------------------
# Cancelamento
# ----------------------------------------------------------------------

def test_cancelamento_cooperativo_devolve_parcial():
    """Laços que consultam h.cancelled devolvem o que já processaram."""
    with _Raiz() as r:
        saida = {}

        def trabalho(h):
            feitos = []
            for i in range(1000):
                if h.cancelled:
                    break
                feitos.append(i)
                time.sleep(0.002)
            return feitos

        r.task.start(trabalho, on_done=lambda res: saida.update(res=res))
        r.bombear(lambda: False, limite=0.15)      # deixa progredir um pouco
        r.task.cancel()
        r.bombear(lambda: "res" in saida)

        assert 0 < len(saida["res"]) < 1000, \
            f"esperava resultado parcial, veio {len(saida['res'])}"


def test_raise_if_cancelled_aborta():
    """Operações cujo parcial não serve (conversão de PDF) abortam de vez."""
    with _Raiz() as r:
        estado = {}

        def trabalho(h):
            for _ in range(1000):
                h.raise_if_cancelled()
                time.sleep(0.002)
            return "nunca chega aqui"

        r.task.start(trabalho,
                     on_done=lambda res: estado.update(fim="done"),
                     on_cancel=lambda: estado.update(fim="cancel"))
        r.bombear(lambda: False, limite=0.15)
        r.task.cancel()
        r.bombear(lambda: "fim" in estado)

        assert estado["fim"] == "cancel"


# ----------------------------------------------------------------------
# Erros e concorrência
# ----------------------------------------------------------------------

def test_erro_vai_para_on_error():
    """A exceção não pode morrer na thread — tem que chegar à UI."""
    with _Raiz() as r:
        capturado = {}

        def trabalho(h):
            raise ValueError("falha proposital")

        r.task.start(trabalho,
                     on_done=lambda _: capturado.update(erro="NAO DEVERIA"),
                     on_error=lambda e: capturado.update(erro=e))
        r.bombear(lambda: "erro" in capturado)

        assert isinstance(capturado["erro"], ValueError)
        assert "falha proposital" in str(capturado["erro"])


def test_uma_tarefa_por_vez():
    with _Raiz() as r:
        pronto = {}
        assert r.task.start(lambda h: time.sleep(0.3) or 1,
                            on_done=lambda _: pronto.update(ok=True)) is True
        assert r.task.start(lambda h: 2) is False, "aceitou duas tarefas ao mesmo tempo"
        r.bombear(lambda: "ok" in pronto)


def test_is_running_so_cai_apos_entregar():
    """
    Bug encontrado ao escrever estes testes: is_running() consultava
    thread.is_alive(), que vira False no instante em que a thread enfileira o
    resultado — antes de on_done rodar. Nessa janela dava para disparar outra
    tarefa por cima de um estado ainda não aplicado.
    """
    with _Raiz() as r:
        estado = {}

        def on_done(_):
            # Ainda dentro da entrega: é o momento em que o estado é aplicado.
            estado["rodando_durante_entrega"] = r.task.is_running()
            estado["entregue"] = True

        # O trabalho precisa demorar o bastante para o _pump inicial (que roda
        # dentro de start()) encontrar a fila vazia e agendar o próximo ciclo.
        r.task.start(lambda h: time.sleep(0.1) or "x", on_done=on_done)

        # Espera a thread morrer sem deixar o Tk processar a fila.
        r.task._thread.join(timeout=5)
        estado["rodando_com_thread_morta"] = r.task.is_running()

        r.bombear(lambda: "entregue" in estado)

        assert estado["rodando_com_thread_morta"] is True, \
            "is_running() caiu antes de o resultado ser aplicado"
        assert estado["entregue"] is True


# ----------------------------------------------------------------------
# Barra de status
# ----------------------------------------------------------------------

def test_status_bar_mostra_e_esconde_progresso():
    from ui.status_bar import StatusBar

    root = tk.Tk()
    root.withdraw()
    try:
        sb = StatusBar(root)
        sb.pack()
        root.update()

        # winfo_ismapped() não serve aqui: a raiz está withdraw(), então nada
        # é mapeado. winfo_manager() diz se o widget está sob o pack.
        assert sb.progress.winfo_manager() == ""
        assert sb.btn_cancel.winfo_manager() == ""

        sb.start_task("Trabalhando")
        root.update()
        assert sb.progress.winfo_manager() == "pack", "a barra de progresso não apareceu"
        assert sb.btn_cancel.winfo_manager() == "pack", "o botão cancelar não apareceu"

        sb.set_progress(5, 10, "metade")
        root.update()
        assert abs(float(sb.progress.cget("value")) - 50.0) < 0.01
        assert "metade" in sb.lbl.cget("text")

        sb.end_task("Pronto.")
        root.update()
        assert sb.progress.winfo_manager() == ""
        assert sb.lbl.cget("text") == "Pronto."
    finally:
        root.destroy()


def test_cancelar_pela_barra_de_status():
    from ui.status_bar import StatusBar

    root = tk.Tk()
    root.withdraw()
    try:
        chamou = {}
        sb = StatusBar(root, on_cancel=lambda: chamou.update(sim=True))
        sb.pack()
        sb.start_task("Trabalhando")
        root.update()

        sb.btn_cancel.invoke()
        assert chamou.get("sim") is True
        assert str(sb.btn_cancel.cget("state")) == "disabled", \
            "o botão deveria travar para não cancelar duas vezes"

        sb.reset_cancel_button()
        assert str(sb.btn_cancel.cget("state")) == "normal"
    finally:
        root.destroy()


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
