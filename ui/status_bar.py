import tkinter as tk
from tkinter import ttk


class StatusBar(tk.Frame):
    """
    Barra de status com mensagem, progresso e botão de cancelar.

    Substitui dois improvisos: o progresso escrito no título da janela e as
    janelas Toplevel que cada operação longa criava por conta própria.

    (A versão anterior deste arquivo era um `tk.Label`, e por isso não servia:
    um Label não comporta um Progressbar dentro. Foi removida na F5.1 e
    reescrita aqui como Frame.)
    """

    def __init__(self, parent, on_cancel=None):
        super().__init__(parent, relief="sunken", bd=1)
        self._on_cancel = on_cancel

        self.lbl = tk.Label(self, anchor="w", padx=6)
        self.lbl.pack(side="left", fill="x", expand=True)

        self.btn_cancel = tk.Button(self, text="Cancelar", width=10,
                                    command=self._cancelar)
        self.progress = ttk.Progressbar(self, length=220, mode="determinate")

        self.set("Pronto.")

        # Um Progressbar em modo indeterminado se reagenda via `after`. Se a
        # janela for destruída no meio da animação, o callback pendente dispara
        # contra uma aplicação que já não existe e o Tk cospe um erro.
        self.bind("<Destroy>", self._ao_destruir)

    def _ao_destruir(self, _event=None):
        try:
            self.progress.stop()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------

    def set(self, texto: str):
        self.lbl.config(text=texto)

    def start_task(self, texto: str, indeterminado: bool = False):
        """Entra em modo 'ocupado': mostra progresso e o botão de cancelar."""
        self.set(texto)
        self.progress.pack(side="right", padx=6, pady=2)
        self.btn_cancel.pack(side="right", padx=6, pady=2)

        if indeterminado:
            self.progress.config(mode="indeterminate")
            self.progress.start(12)
        else:
            self.progress.config(mode="determinate", maximum=100, value=0)

    def set_progress(self, atual: int, total: int, mensagem: str = ""):
        if total > 0 and str(self.progress.cget("mode")) == "determinate":
            self.progress.config(value=(atual / total) * 100)
        if mensagem:
            self.set(mensagem)

    def end_task(self, texto: str = "Pronto."):
        try:
            self.progress.stop()
        except tk.TclError:
            pass
        self.progress.pack_forget()
        self.btn_cancel.pack_forget()
        self.set(texto)

    # ------------------------------------------------------------------

    def _cancelar(self):
        if self._on_cancel:
            self.btn_cancel.config(state="disabled", text="Cancelando")
            self._on_cancel()

    def reset_cancel_button(self):
        self.btn_cancel.config(state="normal", text="Cancelar")
