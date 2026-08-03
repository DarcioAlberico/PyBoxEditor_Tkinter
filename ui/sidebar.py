import tkinter as tk
from tkinter import ttk
from typing import List
from core.box_model import BoxEntry


class Sidebar(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        ttk.Label(self, text="Boxes", font=("Segoe UI", 10, "bold")).pack(anchor="w")

        self.listbox = tk.Listbox(self, height=25)
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        frm = ttk.LabelFrame(self, text="Editar Box")
        frm.pack(fill=tk.X, pady=5)

        ttk.Label(frm, text="Caractere:").pack(side=tk.LEFT)
        self.char_var = tk.StringVar()
        self.entry = ttk.Entry(frm, textvariable=self.char_var, width=6)
        self.entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(frm, text="Aplicar", command=self.apply_char).pack(side=tk.LEFT)

    def update_list(self, boxes: List[BoxEntry], selected_index: int):
        self.listbox.delete(0, tk.END)
        for i, b in enumerate(boxes):
            self.listbox.insert(
                tk.END, f"{i:04d}: '{b.char}' ({b.x1},{b.y1})-({b.x2},{b.y2})"
            )
        if 0 <= selected_index < len(boxes):
            self.listbox.selection_set(selected_index)
            self.listbox.see(selected_index)

    def on_select(self, event):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self.controller.select_box(idx)

    def apply_char(self):
        c = self.char_var.get().strip()
        if not c:
            c = "?"
        self.controller.apply_char(c)
