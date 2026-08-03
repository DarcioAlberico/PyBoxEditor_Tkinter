import tkinter as tk


class StatusBar(tk.Label):
    def __init__(self, parent):
        super().__init__(parent, anchor="w", relief="sunken", bd=1)
        self.set("Pronto.")

    def set(self, text: str):
        self.config(text=text)
