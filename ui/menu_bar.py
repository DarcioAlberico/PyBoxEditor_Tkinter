import tkinter as tk
from tkinter import filedialog, messagebox
from core.tesseract_utils import set_tesseract_path, test_tesseract


class MenuBar(tk.Menu):
    def __init__(self, parent, controller, settings):
        super().__init__(parent)
        self.parent = parent
        self.controller = controller
        self.settings = settings

        menu_file = tk.Menu(self, tearoff=False)
        menu_tools = tk.Menu(self, tearoff=False)

        self.add_cascade(label="Arquivo", menu=menu_file)
        self.add_cascade(label="Ferramentas", menu=menu_tools)

        # Arquivo
        menu_file.add_command(label="Abrir imagem...", command=self.controller.open_image)
        menu_file.add_command(label="Salvar .box", command=self.controller.save_box)
        menu_file.add_command(label="Carregar .box", command=self.controller.load_box_dialog)
        menu_file.add_separator()
        menu_file.add_command(label="Sair", command=self.parent.quit)

        # Ferramentas
        menu_tools.add_command(
            label="Gerar boxes (OpenCV)", command=self.controller.generate_autobox
        )
        menu_tools.add_command(
            label="Substituir Glifos de Xadrez em PDF (Texto)...", command=self.controller.substitute_chess_glyphs_action
        )
        menu_tools.add_command(
            label="Substituir Glifos em PDF Escaneado (Neural)...", command=self.controller.substitute_glyphs_neural_action
        )
        menu_tools.add_separator()
        menu_tools.add_command(
            label="Selecionar Tesseract OCR...", command=self.select_tesseract
        )

    def select_tesseract(self):
        path = filedialog.askopenfilename(
            title="Selecionar tesseract.exe",
            filetypes=[("Executável", "*.exe"), ("Todos os arquivos", "*.*")]
        )
        if not path:
            return

        if not test_tesseract(path):
            messagebox.showerror("Erro", "Falha ao executar tesseract.exe selecionado.")
            return

        set_tesseract_path(self.settings, path)
        messagebox.showinfo("Tesseract", "Tesseract configurado com sucesso.")
