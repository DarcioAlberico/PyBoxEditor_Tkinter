"""Janela para revisar amostras de linhas já salvas no dataset."""

from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

from core.linha_review import corrigir, descartar, ler_manifesto


class DialogoRevisaoLinhas(tk.Toplevel):
    def __init__(self, parent, pasta="training_data_linhas"):
        super().__init__(parent.parent)
        self.app, self.pasta = parent, Path(pasta)
        self.amostras, self.pos = ler_manifesto(self.pasta), 0
        self.imagem_tk = None
        self.title("Revisão do dataset de linhas")
        self.geometry("900x600")
        self.transient(parent.parent)
        self._montar()
        self._mostrar()
        self.grab_set()

    def _montar(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.info = tk.Label(self, anchor="w")
        self.info.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        corpo = tk.Frame(self)
        corpo.grid(row=1, column=0, sticky="nsew", padx=10)
        corpo.columnconfigure(0, weight=1)
        corpo.rowconfigure(0, weight=1)
        self.preview = tk.Label(corpo, bg="#202124")
        self.preview.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.texto = tk.Text(corpo, height=8, width=32, wrap="word")
        self.texto.grid(row=0, column=1, sticky="nsew")
        botoes = tk.Frame(self, pady=8)
        botoes.grid(row=2, column=0, sticky="ew", padx=10)
        tk.Button(botoes, text="Anterior", command=self._anterior).pack(side="left")
        tk.Button(botoes, text="Salvar correção", command=self._salvar).pack(side="left", padx=8)
        tk.Button(botoes, text="Descartar", command=self._descartar).pack(side="left")
        tk.Button(botoes, text="Próxima", command=self._proxima).pack(side="left", padx=8)
        tk.Button(botoes, text="Fechar", command=self.destroy).pack(side="right")
        self.texto.bind("<Control-Return>", lambda _event: self._salvar())

    def _mostrar(self):
        if not self.amostras:
            self.info.config(text="Nenhuma amostra no dataset.")
            self.preview.config(image="")
            self.texto.delete("1.0", "end")
            return
        item = self.amostras[self.pos]
        caminho = self.pasta / item.caminho
        with Image.open(caminho) as original:
            imagem = original.convert("RGB")
            escala = min(680 / max(1, imagem.width), 420 / max(1, imagem.height), 1.0)
            imagem = imagem.resize((max(1, round(imagem.width * escala)),
                                    max(1, round(imagem.height * escala))), Image.Resampling.LANCZOS)
            self.imagem_tk = ImageTk.PhotoImage(imagem)
        self.preview.config(image=self.imagem_tk)
        self.info.config(text=f"Amostra {self.pos + 1} de {len(self.amostras)} — {item.caminho}")
        self.texto.delete("1.0", "end")
        self.texto.insert("1.0", item.texto)

    def _salvar(self):
        if not self.amostras:
            return
        texto = self.texto.get("1.0", "end-1c").strip()
        try:
            corrigir(self.pasta, self.amostras[self.pos].caminho, texto)
        except (ValueError, FileNotFoundError) as erro:
            messagebox.showerror("Correção", str(erro), parent=self)
            return
        self.amostras = ler_manifesto(self.pasta)
        self._proxima()

    def _descartar(self):
        if not self.amostras:
            return
        descartar(self.pasta, self.amostras[self.pos].caminho, "revisao_visual")
        self.amostras = ler_manifesto(self.pasta)
        self.pos = min(self.pos, max(0, len(self.amostras) - 1))
        self._mostrar()

    def _proxima(self):
        if self.amostras:
            self.pos = min(self.pos + 1, len(self.amostras) - 1)
            self._mostrar()

    def _anterior(self):
        if self.amostras:
            self.pos = max(0, self.pos - 1)
            self._mostrar()
