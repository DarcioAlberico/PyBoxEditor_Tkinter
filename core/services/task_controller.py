"""Fachada da execução assíncrona usada pela camada visual."""

from core.services.task_service import BackgroundTask


class TaskController:
    """Coordena uma tarefa ativa sem expor sua implementação à janela."""

    def __init__(self, widget, poll_ms: int = 50):
        self._task = BackgroundTask(widget, poll_ms=poll_ms)

    def start(self, *args, **kwargs) -> bool:
        return self._task.start(*args, **kwargs)

    def is_running(self) -> bool:
        return self._task.is_running()

    def cancel(self):
        self._task.cancel()

    def shutdown(self):
        self._task.shutdown()

