from core.services.task_controller import TaskController


class FakeTask:
    def __init__(self):
        self.calls = []

    def start(self, *args, **kwargs):
        self.calls.append(("start", args, kwargs))
        return True

    def is_running(self):
        return False

    def cancel(self):
        self.calls.append(("cancel",))

    def shutdown(self):
        self.calls.append(("shutdown",))


def test_controlador_expõe_ciclo_de_vida_da_tarefa():
    controller = TaskController.__new__(TaskController)
    controller._task = FakeTask()

    assert controller.start(lambda handle: None)
    assert not controller.is_running()
    controller.cancel()
    controller.shutdown()
    assert [call[0] for call in controller._task.calls] == [
        "start", "cancel", "shutdown"
    ]

