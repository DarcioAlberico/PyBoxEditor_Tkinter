"""
Execução de trabalho pesado fora da thread da interface.

Antes, todo processamento longo (OCR de página, treino, lote, conversão de PDF)
rodava na própria thread do Tkinter, com `parent.update()` no meio do laço:

  - o Windows marcava a janela como "Não Responde"
  - não havia como cancelar
  - `update()` reentrante processa a fila de eventos no meio do processamento,
    e pode reentrar num handler enquanto a lista de boxes está sendo mutada

Aqui o trabalho vai para uma thread e conversa com a UI por uma fila. A thread
da interface só lê a fila, periodicamente, via `widget.after()`.

Regra que não pode ser quebrada: **a função de trabalho nunca toca em widget**.
Tkinter não é thread-safe. Ela calcula e devolve dados; quem mexe na tela é o
callback `on_done`, que roda na thread da UI.
"""

import queue
import threading


class Cancelled(Exception):
    """Levantada por TaskHandle.raise_if_cancelled() quando o usuário cancela."""


class TaskHandle:
    """
    O que a função de trabalho recebe para se comunicar com a UI.

    Só isto é seguro de usar de dentro da thread: reportar progresso, registrar
    mensagens e consultar o cancelamento.
    """

    def __init__(self, fila: queue.Queue, evento_cancelar: threading.Event):
        self._fila = fila
        self._cancelar = evento_cancelar

    def progress(self, atual: int, total: int, mensagem: str = ""):
        self._fila.put(("progress", (atual, total, mensagem)))

    def log(self, mensagem: str):
        self._fila.put(("log", mensagem))

    @property
    def cancelled(self) -> bool:
        """Consulta sem interromper — para laços que querem devolver o parcial."""
        return self._cancelar.is_set()

    def raise_if_cancelled(self):
        """Aborta na hora — para operações cujo resultado parcial não serve."""
        if self._cancelar.is_set():
            raise Cancelled()


class BackgroundTask:
    """
    Roda `fn(handle)` numa thread e entrega os eventos na thread da UI.

    Uma instância executa uma tarefa por vez; start() devolve False se já houver
    outra em andamento.
    """

    def __init__(self, widget, poll_ms: int = 50):
        self._widget = widget
        self._poll_ms = poll_ms
        self._fila = None
        self._thread = None
        self._cancelar = None
        self._after_id = None
        self._ativo = False

    def is_running(self) -> bool:
        """
        Verdadeiro até o resultado ter sido *entregue*, não só até a thread
        morrer.

        Consultar `thread.is_alive()` seria cedo demais: a thread termina no
        instante em que enfileira o resultado, e o callback `on_done` só roda no
        próximo ciclo de `after`. Nessa janela, quem perguntasse "acabou?"
        receberia sim com o estado ainda por aplicar — e poderia disparar outra
        tarefa em cima.
        """
        return self._ativo

    def start(self, fn, on_progress=None, on_done=None,
              on_error=None, on_cancel=None, on_log=None) -> bool:
        if self.is_running():
            return False

        self._ativo = True
        self._fila = queue.Queue()
        self._cancelar = threading.Event()
        handle = TaskHandle(self._fila, self._cancelar)
        fila = self._fila

        def runner():
            try:
                resultado = fn(handle)
            except Cancelled:
                fila.put(("cancelled", None))
            except Exception as e:  # noqa: BLE001 — reportado à UI
                fila.put(("error", e))
            else:
                fila.put(("done", resultado))

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()
        self._pump(on_progress, on_done, on_error, on_cancel, on_log)
        return True

    def cancel(self):
        """Pedido cooperativo: a função de trabalho decide quando parar."""
        if self._cancelar is not None:
            self._cancelar.set()

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    def _pump(self, on_progress, on_done, on_error, on_cancel, on_log):
        """Drena a fila na thread da UI e reagenda a si mesmo."""
        encerrou = False
        try:
            while True:
                tipo, carga = self._fila.get_nowait()

                if tipo == "progress":
                    if on_progress:
                        on_progress(*carga)
                elif tipo == "log":
                    if on_log:
                        on_log(carga)
                elif tipo == "done":
                    encerrou = True
                    self._encerrar()
                    if on_done:
                        on_done(carga)
                    return
                elif tipo == "error":
                    encerrou = True
                    self._encerrar()
                    if on_error:
                        on_error(carga)
                    return
                elif tipo == "cancelled":
                    encerrou = True
                    self._encerrar()
                    if on_cancel:
                        on_cancel()
                    return
        except queue.Empty:
            pass
        finally:
            if not encerrou:
                try:
                    self._after_id = self._widget.after(
                        self._poll_ms,
                        lambda: self._pump(on_progress, on_done, on_error, on_cancel, on_log),
                    )
                except Exception:
                    # Janela destruída enquanto a tarefa rodava: nada a fazer.
                    self._after_id = None

    def _encerrar(self):
        self._ativo = False
        if self._after_id is not None:
            try:
                self._widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def shutdown(self):
        """
        Solta o agendamento pendente antes de destruir a janela.

        Sem isto, o `after` que ainda está na agenda dispara depois da janela ir
        embora e o Tk reclama de 'invalid command name'.
        """
        self.cancel()
        self._encerrar()
