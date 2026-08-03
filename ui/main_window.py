import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image

from core.chess_pdf_processor import substitute_chess_glyphs
from core.neural_pdf_processor import process_scanned_pdf
from core.box_model import BoxEntry
from core.services.box_service import BoxService
from core.services.ocr_service import OCRService
from core.services.pdf_service import PDFService
from core.services.learning_service import LearningService
from core.services.history_service import HistoryManager
from core.services.document_service import DocumentSession

from ui.canvas_view import CanvasView


NAGS = [
    ("!", "Boa jogada"), ("!!", "Excelente"), ("?", "Erro"), ("??", "Erro grave"),
    ("!?", "Interessante"), ("?!", "Duvidoso"), ("=", "Igualdade"), ("±", "Brancas melhor"),
    ("∓", "Negras melhor"), ("+-", "Brancas vencem"), ("-+", "Negras vencem"),
    ("∞", "Posição incerta"), ("⨀", "Zugzwang"), ("□", "Lance único"), ("Δ", "Com ideia de")
]


class MainWindow(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        self.parent = parent
        self.image = None          # PIL.Image
        self.image_path = None
        self.boxes = []            # lista de BoxEntry da página atual
        self.selected_index = -1
        self.current_pdf_page = 0

        # Documento aberto: guarda os boxes de todas as páginas visitadas
        # e o que ainda não foi gravado em disco.
        self.session = None

        # Services
        self.box_service = BoxService()
        self.ocr_service = OCRService()
        self.pdf_service = PDFService()
        self.learning_service = LearningService()
        self.history = HistoryManager(max_history=50)

        self._build_layout()
        self._build_menu()
        self._bind_keys()

        # Fechar pela janela passa pela mesma confirmação do menu Sair.
        self.parent.protocol("WM_DELETE_WINDOW", self._on_close)
        self._update_title()

    # -------------------------------------------------------
    # Documento: estado sujo, título e confirmações
    # -------------------------------------------------------

    def _commit_change(self):
        """
        Registra uma mutação dos boxes: snapshot para undo + marca a página
        como não salva.

        Ponto único de entrada — todo lugar que altera self.boxes chama isto
        em vez de history.snapshot() direto.
        """
        self.history.snapshot(self.boxes, self.selected_index)
        if self.session is not None:
            self.session.store(self.current_pdf_page, self.boxes)
            self.session.mark_dirty(self.current_pdf_page)
        self._update_title()

    def _sync_session(self):
        """Reassocia self.boxes à página atual sem marcá-la como suja.
        Usado após undo/redo, que reatribuem a lista."""
        if self.session is not None:
            self.session.store(self.current_pdf_page, self.boxes)

    def _update_title(self):
        base = "PyBoxEditor"
        if self.session is not None:
            nome = os.path.basename(self.session.path)
            if self.session.is_pdf:
                base += f" — {nome} [Pág {self.current_pdf_page + 1}/{self.session.num_pages}]"
            else:
                base += f" — {nome}"
            if self.session.is_dirty():
                base += " *"
        self.parent.title(base)

    def _confirm_discard(self) -> bool:
        """True se pode prosseguir (nada pendente, ou o usuário aceitou perder)."""
        if self.session is None or not self.session.is_dirty():
            return True

        paginas = self.session.dirty_pages()
        if self.session.is_pdf:
            onde = f"{len(paginas)} página(s): " + ", ".join(str(p + 1) for p in paginas[:8])
            if len(paginas) > 8:
                onde += f" e mais {len(paginas) - 8}"
        else:
            onde = "esta imagem"

        return messagebox.askyesno(
            "Trabalho não salvo",
            f"Há alterações não salvas em {onde}.\n"
            f"Total na sessão: {self.session.total_boxes()} box(es).\n\n"
            "Use 'Salvar todas as páginas' para gravar tudo.\n\n"
            "Descartar as alterações e continuar?",
            icon="warning",
        )

    def _on_close(self):
        if self._confirm_discard():
            self.parent.destroy()

    # -------------------------------------------------------
    # Layout
    # -------------------------------------------------------

    def _build_layout(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)
        self.rowconfigure(2, weight=0)
        self.rowconfigure(3, weight=0)

        # Canvas principal
        self.canvas = CanvasView(self, controller=self)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # Sidebar de boxes (com scrollbar)
        sidebar = tk.Frame(self)
        sidebar.grid(row=0, column=1, sticky="ns")
        sidebar.rowconfigure(0, weight=1)
        sidebar.columnconfigure(0, weight=1)

        frame_list = tk.Frame(sidebar)
        frame_list.grid(row=0, column=0, sticky="ns")

        scrollbar = tk.Scrollbar(frame_list, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self.listbox = tk.Listbox(
            frame_list,
            width=32,
            yscrollcommand=scrollbar.set,
            font=("Consolas", 9)
        )
        self.listbox.pack(side="left", fill="y", expand=True)
        scrollbar.config(command=self.listbox.yview)

        self.listbox.bind("<<ListboxSelect>>", self.on_sidebar_select)
        self.listbox.bind("<Up>", self._on_key_up)
        self.listbox.bind("<Down>", self._on_key_down)

        # Editor de caractere + OCR
        editor = tk.Frame(self)
        editor.grid(row=1, column=0, columnspan=2, sticky="ew")
        editor.columnconfigure(1, weight=1)

        tk.Label(editor, text="Caractere:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        self.char_entry = tk.Entry(editor, width=5)
        self.char_entry.grid(row=0, column=1, sticky="w", padx=5, pady=3)
        self.char_entry.bind("<Return>", lambda e: self.apply_char_and_next())

        tk.Button(editor, text="Aplicar", command=self.apply_char).grid(row=0, column=2, padx=5)
        tk.Button(editor, text="Proximo >>", command=self.apply_char_and_next).grid(row=0, column=3, padx=5)
        self.btn_ocr_box = tk.Button(editor, text="OCR (box)", command=self.ocr_selected_box)
        self.btn_ocr_box.grid(row=0, column=4, padx=5)

        # NAGs Quick Access
        nag_frame = tk.Frame(self)
        nag_frame.grid(row=2, column=0, columnspan=2, sticky="ew")

        tk.Label(nag_frame, text="NAGs Rápidos:").pack(side="left", padx=5, pady=3)
        for nag_char, tooltip in NAGS:
            btn = tk.Button(nag_frame, text=nag_char, width=3,
                            command=lambda c=nag_char: self.apply_nag(c))
            btn.bind("<Enter>", lambda e, text=tooltip: self.show_nag_tooltip(text))
            btn.bind("<Leave>", lambda e: self.hide_nag_tooltip())
            btn.pack(side="left", padx=2, pady=3)

        self.lbl_tooltip = tk.Label(nag_frame, text="", fg="gray")
        self.lbl_tooltip.pack(side="left", padx=10)

        # Barra de Navegacao PDF
        self.nav_frame = tk.Frame(self)
        self.nav_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=5)
        self.nav_frame.columnconfigure(1, weight=1)

        self.btn_prev_page = tk.Button(self.nav_frame, text="<< Página Anterior", command=self.prev_page, state="disabled")
        self.btn_prev_page.pack(side="left", padx=10)

        self.lbl_page_info = tk.Label(self.nav_frame, text="Página: -/-")
        self.lbl_page_info.pack(side="left", padx=10)

        self.btn_next_page = tk.Button(self.nav_frame, text="Próxima Página >>", command=self.next_page, state="disabled")
        self.btn_next_page.pack(side="left", padx=10)

        self._build_context_menu()

    # -------------------------------------------------------
    # Menu
    # -------------------------------------------------------

    def _build_menu(self):
        menubar = tk.Menu(self.parent)
        self.parent.config(menu=menubar)

        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="Abrir imagem...", command=self.open_image)
        m_file.add_command(label="Abrir PDF...", command=self.open_pdf)
        m_file.add_command(label="Salvar .box (página atual)", accelerator="Ctrl+S",
                           command=self.save_box_file)
        m_file.add_command(label="Salvar todas as páginas...", accelerator="Ctrl+Shift+S",
                           command=self.save_all_pages)
        m_file.add_command(label="Carregar .box", command=self.load_box_file)
        m_file.add_separator()
        m_file.add_command(label="Sair", command=self._on_close)
        menubar.add_cascade(label="Arquivo", menu=m_file)

        m_tools = tk.Menu(menubar, tearoff=0)
        m_tools.add_command(label="Gerar boxes (OpenCV)", command=self.generate_boxes_opencv)
        m_tools.add_command(label="Preencher caracteres (OCR)", command=self.auto_fill_characters)
        m_tools.add_command(label="Preencher caracteres (EasyOCR)", command=self.auto_fill_characters_easyocr)
        m_tools.add_separator()
        m_tools.add_command(label="Detectar e Preencher (EasyOCR)", command=self.generate_and_fill_easyocr)
        m_tools.add_command(label="Detectar e Preencher (Híbrido/Ref)", command=self.generate_and_fill_combined)
        m_tools.add_command(label="Detectar e Preencher (Neural)", command=self.generate_and_fill_neural)
        m_tools.add_separator()
        m_tools.add_command(label="Aprender com Página Atual (Coletar)", command=self.learn_from_current_page)
        m_tools.add_command(label="Treinar Rede Neural", command=self.train_neural_network)
        m_tools.add_separator()
        m_tools.add_command(label="Treinamento Geral Neural (Batch)", command=self.run_general_neural_training)
        m_tools.add_command(label="Importar Imagens de Caracteres", command=self.import_character_images)
        m_tools.add_separator()
        m_tools.add_command(label="Dividir box selecionado", command=self.split_selected_box)
        m_tools.add_command(label="Excluir box selecionado", command=self.delete_selected_box)
        m_tools.add_separator()
        m_tools.add_command(label="Substituir Glifos de Xadrez em PDF (Texto)...", command=self.substitute_chess_glyphs_action)
        m_tools.add_command(label="Substituir Glifos em PDF Escaneado (Neural)...", command=self.substitute_glyphs_neural_action)
        menubar.add_cascade(label="Ferramentas", menu=m_tools)

    def _build_context_menu(self):
        self.context_menu = tk.Menu(self, tearoff=0)
        for nag_char, desc in NAGS:
            self.context_menu.add_command(
                label=f"{nag_char} ({desc})",
                command=lambda c=nag_char: self.apply_nag(c)
            )

        self.listbox.bind("<Button-3>", self.show_context_menu)

    def show_context_menu(self, event):
        if not self.boxes:
            return

        if event.widget == self.listbox:
            idx = self.listbox.nearest(event.y)
            if idx >= 0:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(idx)
                self.select_box(idx)

        self.context_menu.tk_popup(event.x_root, event.y_root)

    # -------------------------------------------------------
    # Keybindings
    # -------------------------------------------------------

    def _bind_keys(self):
        root = self.parent
        root.bind("<Up>", self._on_key_up)
        root.bind("<Down>", self._on_key_down)
        root.bind("<Delete>", self._on_key_delete)
        root.bind("<BackSpace>", self._on_key_delete)
        root.bind("d", self._on_key_split_safe)
        root.bind("D", self._on_key_split_safe)
        root.bind("<Control-s>", lambda e: (self.save_box_file(), "break")[1])
        root.bind("<Control-S>", lambda e: (self.save_all_pages(), "break")[1])
        root.bind("<Prior>", lambda e: (self.prev_page(), "break")[1])
        root.bind("<Next>", lambda e: (self.next_page(), "break")[1])
        root.bind("<Control-z>", self._on_key_undo)
        root.bind("<Control-y>", self._on_key_redo)
        root.bind("<Control-Z>", self._on_key_redo)  # Shift+Ctrl+Z fallback

    # -------------------------------------------------------
    # Imagem
    # -------------------------------------------------------

    def open_image(self, path=None):
        if not self._confirm_discard():
            return

        if path is None:
            path = filedialog.askopenfilename(
                filetypes=[("Imagens", "*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff")]
            )
        if not path:
            return

        try:
            img = Image.open(path)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir a imagem:\n{e}")
            return

        self.pdf_service.close()

        self.session = DocumentSession(path, num_pages=1, is_pdf=False)
        self.current_pdf_page = 0

        self.image = img.convert("L")
        self.image_path = path
        self.boxes = self.session.boxes_for(0)
        self.selected_index = -1

        self._update_nav_controls()

        # Zerar o histórico ao trocar de documento: sem isso, um undo logo após
        # abrir traria de volta os boxes da imagem anterior.
        self.history.reset()

        box_path = os.path.splitext(path)[0] + ".box"
        if os.path.exists(box_path):
            self._load_box_from_path(box_path, marcar_sujo=False)
        else:
            self.history.snapshot(self.boxes, self.selected_index)
            self.update_sidebar()
            self.update_canvas()

        self._update_title()

    def open_pdf(self, path=None):
        if not self._confirm_discard():
            return

        if path is None:
            path = filedialog.askopenfilename(
                filetypes=[("Arquivos PDF", "*.pdf")]
            )
        if not path:
            return

        num_pages, err = self.pdf_service.load_pdf(path)
        if err:
            messagebox.showerror("Erro PDF", err)
            return

        # A sessão nova precisa existir antes de carregar a página, e a página
        # atual não deve ser arquivada na sessão nova (ela é do documento antigo).
        self.session = DocumentSession(path, num_pages=num_pages, is_pdf=True)
        self.boxes = []
        self.current_pdf_page = 0
        self._load_pdf_page(0, arquivar_atual=False)

    def _load_pdf_page(self, page_index, arquivar_atual=True):
        self.parent.config(cursor="wait")
        self.parent.update()

        try:
            # Guardar o trabalho da página que está saindo ANTES de trocar.
            # Sem isto, virar a página descartava tudo que havia sido digitado.
            if arquivar_atual and self.session is not None:
                self.session.store(self.current_pdf_page, self.boxes)

            page_img = self.pdf_service.load_page(page_index)
            if page_img is None:
                raise ValueError("Nenhuma imagem retornada para a página.")

            self.image = page_img
            self.image_path = f"{os.path.basename(self.pdf_service.pdf_path)} [Pág {page_index+1}]"
            self.current_pdf_page = page_index

            # Restaura o que já havia sido feito nesta página (lista vazia se
            # for a primeira visita).
            self.boxes = (self.session.boxes_for(page_index)
                          if self.session is not None else [])
            self.selected_index = -1

            # O histórico é por página: um Ctrl+Z logo após virar a página não
            # deve despejar os boxes da página anterior sobre a atual.
            self.history.reset()
            self.history.snapshot(self.boxes, self.selected_index)

            self.update_sidebar()
            self.update_canvas()
            self._update_nav_controls()
            self._update_title()
        except Exception as e:
            messagebox.showerror("Erro Carregar Página", str(e))
        finally:
            self.parent.config(cursor="")

    def prev_page(self):
        # Não mexer em current_pdf_page aqui: _load_pdf_page usa o valor atual
        # para arquivar o trabalho da página que está saindo.
        if self.current_pdf_page > 0:
            self._load_pdf_page(self.current_pdf_page - 1)

    def next_page(self):
        if self.current_pdf_page < self.pdf_service.num_pages - 1:
            self._load_pdf_page(self.current_pdf_page + 1)

    def _update_nav_controls(self):
        if not self.pdf_service.is_loaded():
            if self.session is not None and self.session.has_boxes(0):
                self.lbl_page_info.config(text=f"{len(self.boxes)} boxes")
            else:
                self.lbl_page_info.config(text="Página: -/-")
            self.btn_prev_page.config(state="disabled")
            self.btn_next_page.config(state="disabled")
            return

        info = f"Página: {self.current_pdf_page + 1}/{self.pdf_service.num_pages}"
        if self.session is not None:
            com_boxes = self.session.pages_with_boxes()
            if com_boxes:
                info += (f"   |   {len(com_boxes)} pág. com boxes"
                         f", {self.session.total_boxes()} no total")
            sujas = self.session.dirty_pages()
            if sujas:
                info += f"   |   {len(sujas)} não salva(s)"
        self.lbl_page_info.config(text=info)
        self.btn_prev_page.config(
            state="normal" if self.current_pdf_page > 0 else "disabled"
        )
        self.btn_next_page.config(
            state="normal" if self.current_pdf_page < self.pdf_service.num_pages - 1 else "disabled"
        )

    # -------------------------------------------------------
    # OpenCV: gerar boxes automáticos
    # -------------------------------------------------------

    def generate_boxes_opencv(self):
        if self.image is None:
            messagebox.showinfo("Aviso", "Carregue uma imagem primeiro.")
            return

        self.boxes = self.box_service.generate_boxes_opencv(self.image)
        self._commit_change()
        self.update_canvas()
        self.update_sidebar()

    # -------------------------------------------------------
    # Ações de PDF (Xadrez)
    # -------------------------------------------------------

    def substitute_chess_glyphs_action(self):
        input_pdf = filedialog.askopenfilename(
            title="Selecionar PDF de Origem",
            filetypes=[("Arquivos PDF", "*.pdf")]
        )
        if not input_pdf:
            return

        output_pdf = filedialog.asksaveasfilename(
            title="Salvar PDF Convertido Como...",
            defaultextension=".pdf",
            filetypes=[("Arquivos PDF", "*.pdf")]
        )
        if not output_pdf:
            return

        try:
            total_pages, replaced = substitute_chess_glyphs(input_pdf, output_pdf)
            messagebox.showinfo(
                "Concluído",
                f"Conversão finalizada!\nPáginas processadas: {total_pages}\nSubstituições realizadas: {replaced}\n\nArquivo salvo em:\n{output_pdf}"
            )
        except Exception as e:
            messagebox.showerror("Erro", f"Erro na conversão:\n{str(e)}")

    def substitute_glyphs_neural_action(self):
        input_pdf = filedialog.askopenfilename(
            title="Selecionar PDF Escaneado",
            filetypes=[("Arquivos PDF", "*.pdf")]
        )
        if not input_pdf:
            return

        output_pdf = filedialog.asksaveasfilename(
            title="Salvar PDF Convertido Como...",
            defaultextension=".pdf",
            filetypes=[("Arquivos PDF", "*.pdf")]
        )
        if not output_pdf:
            return

        def update_progress(page, total):
            self.parent.title(f"PyBoxEditor - Processando Neural OCR: Pág {page+1} de {total}")
            self.parent.update()

        self.parent.config(cursor="wait")
        try:
            total_pages, replaced = process_scanned_pdf(
                input_pdf=input_pdf,
                output_pdf=output_pdf,
                model_path="custom_model.pth",
                meta_path="model_meta.json",
                progress_callback=update_progress
            )
            messagebox.showinfo(
                "Concluído Neural",
                f"Conversão finalizada!\nPáginas escaneadas: {total_pages}\nPeças reconhecidas/substituídas: {replaced}\n\nArquivo salvo em:\n{output_pdf}"
            )
        except Exception as e:
            messagebox.showerror("Erro Neural", f"Erro na conversão OCR:\n{str(e)}")
        finally:
            self._update_title()
            self.parent.config(cursor="")

    # -------------------------------------------------------
    # OCR automático para todos os boxes
    # -------------------------------------------------------

    def auto_fill_characters(self):
        if self.image is None or not self.boxes:
            messagebox.showinfo("Aviso", "Não há boxes para preencher.")
            return

        whitelist = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,!?+-=()#:/'\""

        for b in self.boxes:
            crop = self.image.crop((b.x1, b.y1, b.x2, b.y2))
            b.char = self.ocr_service.tesseract_ocr(crop, whitelist)

        self._commit_change()
        self.update_sidebar()
        self.update_canvas()

    def auto_fill_characters_easyocr(self):
        if self.image is None or not self.boxes:
            messagebox.showinfo("Aviso", "Não há boxes para preencher.")
            return

        self.parent.config(cursor="wait")
        self.parent.update()

        count = 0
        try:
            for i, b in enumerate(self.boxes):
                crop = self.image.crop((b.x1, b.y1, b.x2, b.y2))
                crop_np = np.array(crop)
                ch = self.ocr_service.easyocr_ocr(crop_np)
                if ch:
                    b.char = ch
                    count += 1
                else:
                    b.char = b.char

                if i % 5 == 0:
                    self.parent.title(f"PyBoxEditor - Processando OCR... ({i+1}/{len(self.boxes)})")
                    self.parent.update()
        except Exception as e:
            messagebox.showerror("Erro EasyOCR", str(e))
        finally:
            self._update_title()
            self.parent.config(cursor="")
            self._commit_change()
            self.update_sidebar()
            self.update_canvas()
            messagebox.showinfo("EasyOCR", f"Processamento concluído.\nCaracteres preenchidos: {count}")

    def generate_and_fill_easyocr(self):
        self.generate_boxes_opencv()
        if self.boxes:
            self.parent.update()
            self.auto_fill_characters_easyocr()

    def generate_and_fill_combined(self):
        self.generate_boxes_opencv()
        if not self.boxes:
            return

        self.parent.update()
        self.parent.config(cursor="wait")

        count_learned = 0
        count_ocr = 0
        total = len(self.boxes)

        try:
            for i, b in enumerate(self.boxes):
                crop = self.image.crop((b.x1, b.y1, b.x2, b.y2))
                crop_np = np.array(crop)

                char, source, _ = self.ocr_service.fallback_chain(
                    crop_np,
                    learner=self.learning_service._get_learner(),
                    neural_threshold=0.85,
                    learner_threshold=0.85,
                )

                if source == "learner":
                    b.char = char
                    count_learned += 1
                elif source == "easyocr":
                    b.char = char
                    count_ocr += 1
                else:
                    b.char = ""

                if i % 5 == 0:
                    self.parent.title(
                        f"Processando... ({i+1}/{total}) - Base: {count_learned} | OCR: {count_ocr}"
                    )
                    self.parent.update()
        except Exception as e:
            messagebox.showerror("Erro", str(e))
        finally:
            self._update_title()
            self.parent.config(cursor="")
            self._commit_change()
            self.update_sidebar()
            self.update_canvas()
            messagebox.showinfo(
                "Concluído",
                f"Total: {total}\nEncontrados via Base: {count_learned}\nEncontrados via OCR: {count_ocr}"
            )

    def generate_and_fill_neural(self):
        self.generate_boxes_opencv()
        if not self.boxes:
            return

        self.parent.config(cursor="wait")
        self.parent.update()

        count_neural = 0
        count_learner = 0
        count_ocr = 0

        try:
            self.learning_service.load_predictor()
            total = len(self.boxes)

            for i, b in enumerate(self.boxes):
                crop = self.image.crop((b.x1, b.y1, b.x2, b.y2))
                crop_np = np.array(crop)

                char, source, _ = self.ocr_service.fallback_chain(
                    crop_np,
                    predictor=self.learning_service._predictor,
                    learner=self.learning_service._get_learner(),
                    neural_threshold=0.8,
                    learner_threshold=0.9,
                )

                if source == "neural":
                    count_neural += 1
                elif source == "learner":
                    count_learner += 1
                elif source == "easyocr":
                    count_ocr += 1

                b.char = char

                if i % 5 == 0:
                    self.parent.title(
                        f"Processando... ({i+1}/{total}) - Neural: {count_neural} | Ref: {count_learner}"
                    )
                    self.parent.update()
        except Exception as e:
            messagebox.showerror("Erro", str(e))
        finally:
            self._update_title()
            self.parent.config(cursor="")
            self._commit_change()
            self.update_sidebar()
            self.update_canvas()
            messagebox.showinfo(
                "Concluído",
                f"Neural: {count_neural}\nReferencia: {count_learner}\nEasyOCR: {count_ocr}"
            )

    # -------------------------------------------------------
    # Sidebar / seleção
    # -------------------------------------------------------

    def update_sidebar(self):
        self.listbox.delete(0, "end")
        for i, b in enumerate(self.boxes):
            ch = b.char
            disp_ch = ch if ch else "?"
            line = f"{i:04d}: '{disp_ch}' @ ({b.x1},{b.y1})-({b.x2},{b.y2})"
            self.listbox.insert("end", line)

        if 0 <= self.selected_index < len(self.boxes):
            self.listbox.select_set(self.selected_index)
            self.listbox.see(self.selected_index)

    def update_canvas(self):
        self.canvas.redraw()

    def select_box(self, index):
        if index < 0 or index >= len(self.boxes):
            self.selected_index = -1
            self.char_entry.delete(0, "end")
        else:
            self.selected_index = index
            b = self.boxes[index]
            self.char_entry.delete(0, "end")
            self.char_entry.insert(0, b.char)
            self.canvas.zoom_to_box(index)

        self.update_sidebar()
        self.update_canvas()

    def on_sidebar_select(self, event):
        if not self.listbox.curselection():
            return
        idx = self.listbox.curselection()[0]
        self.select_box(idx)

    # -------------------------------------------------------
    # Mutação (undo/redo support)
    # -------------------------------------------------------

    def on_boxes_changed(self):
        """
        Chamado pelo CanvasView DEPOIS de concluir uma mutação (move, resize, novo box).

        Regra única do histórico: snapshot sempre APÓS a mutação. O estado inicial
        é gravado ao abrir o arquivo, então o estado anterior a qualquer operação já
        está no histórico e o undo tem para onde voltar. O padrão antigo gravava
        antes da mutação, e por isso o estado novo nunca entrava no histórico — o
        redo devolvia o estado velho e a alteração se perdia.
        """
        self._commit_change()
        self.update_sidebar()
        self.update_canvas()

    # -------------------------------------------------------
    # Editor de caractere / OCR de box único / NAGs
    # -------------------------------------------------------

    def show_nag_tooltip(self, text):
        self.lbl_tooltip.config(text=text)

    def hide_nag_tooltip(self):
        self.lbl_tooltip.config(text="")

    def apply_nag(self, symbol):
        if self.selected_index < 0 or self.selected_index >= len(self.boxes):
            return
        self.char_entry.delete(0, "end")
        self.char_entry.insert(0, symbol)
        self.apply_char_and_next()

    def apply_char(self):
        if self.selected_index < 0 or self.selected_index >= len(self.boxes):
            return
        ch = self.char_entry.get()
        if not ch:
            ch = ""
        self.boxes[self.selected_index].char = ch
        self._commit_change()
        self.update_sidebar()
        self.update_canvas()

    def apply_char_and_next(self):
        self.apply_char()
        if not self.boxes:
            return
        idx = min(len(self.boxes) - 1, self.selected_index + 1)
        self.select_box(idx)
        self.char_entry.focus_set()
        self.char_entry.select_range(0, "end")

    def ocr_selected_box(self):
        if self.image is None or self.selected_index < 0 or self.selected_index >= len(self.boxes):
            return

        b = self.boxes[self.selected_index]
        crop = self.image.crop((b.x1, b.y1, b.x2, b.y2))
        ch = self.ocr_service.tesseract_ocr(crop)

        if not ch:
            messagebox.showinfo("OCR", "Nenhum caractere reconhecido.")
            return

        self.char_entry.delete(0, "end")
        self.char_entry.insert(0, ch)

    # -------------------------------------------------------
    # Salvar / carregar .box
    # -------------------------------------------------------

    def save_box_file(self):
        if self.image is None or not self.boxes:
            messagebox.showinfo("Aviso", "Nada para salvar.")
            return

        if self.image_path:
            default = os.path.splitext(self.image_path)[0] + ".box"
        else:
            default = "boxes.box"

        path = filedialog.asksaveasfilename(
            defaultextension=".box",
            initialfile=os.path.basename(default),
            filetypes=[("Arquivos BOX", "*.box"), ("Todos", "*.*")]
        )
        if not path:
            return

        self._save_box_to_path(path)

    def load_box_file(self):
        if self.image is None:
            messagebox.showinfo("Aviso", "Carregue uma imagem primeiro.")
            return

        path = filedialog.askopenfilename(
            filetypes=[("Arquivos BOX", "*.box"), ("Todos", "*.*")]
        )
        if not path:
            return

        self._load_box_from_path(path)

    def save_all_pages(self):
        """
        Grava um par .box/.png por página que tenha boxes.

        Contrapartida necessária da persistência entre páginas: sem isto o
        usuário acumularia trabalho em várias páginas sem nenhuma forma de
        gravá-lo, o que seria pior que o comportamento antigo.
        """
        if self.session is None:
            messagebox.showinfo("Aviso", "Nenhum documento aberto.")
            return

        paginas = self.session.pages_with_boxes()
        if not paginas:
            messagebox.showinfo("Aviso", "Nenhuma página tem boxes para salvar.")
            return

        self.parent.config(cursor="wait")
        salvos, falhas = [], []
        try:
            for n, page in enumerate(paginas):
                self.parent.title(f"Salvando página {n + 1}/{len(paginas)}...")
                self.parent.update()

                if page == self.current_pdf_page:
                    img = self.image
                elif self.session.is_pdf:
                    img = self.pdf_service.load_page(page)
                else:
                    img = self.image

                if img is None:
                    falhas.append(f"pág {page + 1}: não foi possível renderizar")
                    continue

                destino = self.session.page_stem(page) + ".box"
                erro = self._write_box_pair(destino, img, self.session.boxes_for(page))
                if erro:
                    falhas.append(f"pág {page + 1}: {erro}")
                else:
                    self.session.mark_saved(page)
                    salvos.append(destino)
        finally:
            self.parent.config(cursor="")
            self._update_nav_controls()
            self._update_title()

        resumo = f"{len(salvos)} página(s) salva(s) em:\n{os.path.dirname(self.session.path)}"
        if falhas:
            messagebox.showerror("Salvo com erros", resumo + "\n\nFalhas:\n" + "\n".join(falhas))
        else:
            messagebox.showinfo("Sucesso", resumo)

    def _write_box_pair(self, path, image, boxes):
        """
        Escreve o par .box/.png. Devolve None em caso de sucesso, ou a mensagem
        de erro. Sem diálogos — quem chama decide como reportar.
        """
        H = image.height
        lines = []
        for b in boxes:
            ch = b.char
            save_ch = ch[0] if ch else "~"
            x1, y1, x2, y2 = b.x1, b.y1, b.x2, b.y2
            y1_t = H - y2
            y2_t = H - y1
            lines.append(f"{save_ch} {x1} {y1_t} {x2} {y2_t} 0")

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            image.save(os.path.splitext(path)[0] + ".png", format="PNG")
            return None
        except Exception as e:
            return str(e)

    def _save_box_to_path(self, path):
        erro = self._write_box_pair(path, self.image, self.boxes)
        if erro:
            messagebox.showerror("Erro", f"Não foi possível salvar os arquivos:\n{erro}")
            return

        if self.session is not None:
            self.session.mark_saved(self.current_pdf_page)
            self._update_nav_controls()
        self._update_title()

        img_path = os.path.splitext(path)[0] + ".png"
        aviso = ""
        if self.session is not None and self.session.is_dirty():
            pend = len(self.session.dirty_pages())
            aviso = (f"\n\nAtenção: ainda há {pend} outra(s) página(s) não salva(s)."
                     "\nUse 'Salvar todas as páginas' para gravar tudo.")

        messagebox.showinfo(
            "Sucesso",
            f"Salvo com sucesso:\n- {os.path.basename(path)}\n"
            f"- {os.path.basename(img_path)}{aviso}"
        )

    def _load_box_from_path(self, path, marcar_sujo=True):
        if self.image is None:
            return

        H = self.image.height
        boxes = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) < 6:
                        continue
                    ch = parts[0]
                    x1, y1_t, x2, y2_t = map(int, parts[1:5])
                    y1 = H - y2_t
                    y2 = H - y1_t
                    if ch == "~":
                        ch = ""
                    boxes.append(BoxEntry(ch, x1, y1, x2, y2))
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível carregar o .box:\n{e}")
            return

        boxes.sort(key=lambda b: (b.y1, b.x1))
        self.boxes = boxes
        self.selected_index = 0 if boxes else -1

        if marcar_sujo:
            self._commit_change()
        else:
            # Sidecar carregado junto com a imagem: o conteúdo já está em disco,
            # no lugar canônico. Marcar como sujo aqui faria a janela abrir com
            # '*' sem o usuário ter mexido em nada.
            self.history.snapshot(self.boxes, self.selected_index)
            self._sync_session()
            self._update_title()
        self.update_sidebar()
        self.update_canvas()

    # -------------------------------------------------------
    # Dividir / deletar box
    # -------------------------------------------------------

    def split_selected_box(self):
        if self.selected_index < 0 or self.selected_index >= len(self.boxes):
            return

        b = self.boxes[self.selected_index]
        b1, b2 = self.box_service.split_box(b)

        self.boxes.pop(self.selected_index)
        self.boxes.insert(self.selected_index, b2)
        self.boxes.insert(self.selected_index, b1)
        self._commit_change()

        self.select_box(self.selected_index)

    def delete_selected_box(self):
        if self.selected_index < 0 or self.selected_index >= len(self.boxes):
            return
        self.boxes.pop(self.selected_index)
        if self.selected_index >= len(self.boxes):
            self.selected_index = len(self.boxes) - 1
        self._commit_change()
        self.update_sidebar()
        self.update_canvas()

    # -------------------------------------------------------
    # Key handlers
    # -------------------------------------------------------

    def _on_key_up(self, event):
        if not self.boxes:
            return "break"
        idx = max(0, self.selected_index - 1)
        self.select_box(idx)
        return "break"

    def _on_key_down(self, event):
        if not self.boxes:
            return "break"
        idx = min(len(self.boxes) - 1, self.selected_index + 1)
        self.select_box(idx)
        return "break"

    def _on_key_delete(self, event):
        self.delete_selected_box()

    def _on_key_split_safe(self, event):
        focus_widget = self.parent.focus_get()
        if isinstance(focus_widget, tk.Entry):
            return
        self.split_selected_box()

    def _on_key_undo(self, event):
        self._perform_undo()
        return "break"

    def _on_key_redo(self, event):
        self._perform_redo()
        return "break"

    def _perform_undo(self):
        if not hasattr(self, 'history'):
            return
        boxes, sel = self.history.undo()
        if boxes is not None:
            self.boxes = boxes
            self.selected_index = sel
            self._sync_session()
            self.update_sidebar()
            self.update_canvas()

    def _perform_redo(self):
        if not hasattr(self, 'history'):
            return
        boxes, sel = self.history.redo()
        if boxes is not None:
            self.boxes = boxes
            self.selected_index = sel
            self._sync_session()
            self.update_sidebar()
            self.update_canvas()

    # -------------------------------------------------------
    # Interactive Learning
    # -------------------------------------------------------

    def learn_from_current_page(self):
        if self.image is None or not self.boxes:
            messagebox.showinfo("Aviso", "Nada para aprender na página atual.")
            return

        if not messagebox.askyesno(
            "Confirmar Aprendizado",
            f"Deseja adicionar {len(self.boxes)} caracteres desta página à base de conhecimento?\n"
            "Certifique-se de que os caracteres estão CORRETOS antes de prosseguir."
        ):
            return

        self.parent.config(cursor="wait")
        self.parent.update()

        try:
            count = self.learning_service.learn_from_boxes(self.image, self.boxes)
            messagebox.showinfo("Sucesso", f"Aprendizado concluído.\n{count} novos modelos adicionados.")
        except Exception as e:
            messagebox.showerror("Erro no Aprendizado", str(e))
        finally:
            self.parent.config(cursor="")

    # -------------------------------------------------------
    # Neural Network
    # -------------------------------------------------------

    def train_neural_network(self):
        if not self.learning_service.data_dir or not os.listdir(self.learning_service.data_dir):
            messagebox.showinfo(
                "Aviso",
                "Nenhum dado de treinamento encontrado.\nUse 'Aprender com Página Atual' primeiro."
            )
            return

        from tkinter import simpledialog
        epochs = simpledialog.askinteger(
            "Epochs",
            "Quantas epochs deseja treinar?\n(Mais epochs = mais preciso, porém mais lento)\n\nRecomendado: 15-30",
            initialvalue=15,
            minvalue=1,
            maxvalue=200
        )
        if epochs is None:
            return

        self.parent.config(cursor="wait")
        self.parent.update()

        try:
            top = tk.Toplevel(self.parent)
            top.title("Treinando...")
            top.geometry("400x120")
            lbl = tk.Label(top, text="Iniciando...", padx=20, pady=20)
            lbl.pack()
            top.update()

            def callback(msg):
                lbl.config(text=msg)
                top.update()
                print(msg)

            success = self.learning_service.train_neural(epochs=epochs, callback=callback)
            top.destroy()

            if success:
                messagebox.showinfo(
                    "Sucesso",
                    "Treinamento concluído!\nAgora você pode usar 'Detectar e Preencher (Neural)'."
                )
            else:
                messagebox.showerror("Erro", "Falha no treinamento.")
        except Exception as e:
            messagebox.showerror("Erro Fatal", str(e))
        finally:
            self.parent.config(cursor="")

    # -------------------------------------------------------
    # Treinamento Geral (Batch) & Importacao
    # -------------------------------------------------------

    def run_general_neural_training(self):
        if not self.learning_service.load_predictor():
            messagebox.showerror(
                "Erro",
                "Modelo neural não encontrado.\nTreine a rede primeiro ou verifique 'custom_model.pth'."
            )
            return

        filepaths = filedialog.askopenfilenames(
            title="Selecione as imagens ou PDF para processar",
            filetypes=[
                ("Todos Suportados", "*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff;*.pdf"),
                ("Imagens", "*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff"),
                ("PDF", "*.pdf")
            ]
        )
        if not filepaths:
            return

        output_dir = filedialog.askdirectory(title="Selecione a pasta de SAÍDA")
        if not output_dir:
            return

        self.parent.config(cursor="wait")
        self.parent.update()

        top = tk.Toplevel(self.parent)
        top.title("Processamento em Lote")
        top.geometry("400x150")
        lbl = tk.Label(top, text="Iniciando...", padx=20, pady=20)
        lbl.pack()
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(top, variable=progress_var, maximum=100, length=300)
        progress_bar.pack()
        top.update()

        try:
            images = []
            for fpath in filepaths:
                ext = os.path.splitext(fpath)[1].lower()
                if ext == ".pdf":
                    try:
                        lbl.config(text=f"Convertendo PDF: {os.path.basename(fpath)}...")
                        top.update()
                        pages = self.pdf_service.convert_pdf_to_images(fpath, dpi=200)
                        for i, page in enumerate(pages):
                            images.append((f"{os.path.basename(fpath)}_pg{i+1}", page))
                    except Exception as e:
                        err_str = str(e)
                        if "poppler" in err_str.lower():
                            messagebox.showerror(
                                "Erro Poppler",
                                "Para ler PDF, você precisa do POPPLER instalado e no PATH.\n"
                                "Baixe em: https://github.com/oschwartz10612/poppler-windows/releases/"
                            )
                            return
                        else:
                            messagebox.showerror("Erro PDF", f"Falha ao ler PDF: {e}")
                            continue
                else:
                    try:
                        img = Image.open(fpath).convert("L")
                        images.append((os.path.basename(fpath), img))
                    except Exception:
                        continue

            def progress_cb(name, current, total):
                lbl.config(text=f"Processando {current}/{total}...\n{name}")
                progress_var.set((current / total) * 100)
                top.update()

            total_crops = self.learning_service.batch_extract_and_classify(
                images, output_dir, progress_callback=progress_cb
            )
            top.destroy()
            messagebox.showinfo(
                "Concluído",
                f"Processamento finalizado!\n{total_crops} caracteres extraídos em:\n{output_dir}"
            )
        except Exception as e:
            top.destroy()
            messagebox.showerror("Erro", str(e))
        finally:
            self.parent.config(cursor="")

    def import_character_images(self):
        src_dir = filedialog.askdirectory(title="Selecione a pasta de ORIGEM")
        if not src_dir:
            return

        self.parent.config(cursor="wait")
        self.parent.update()

        try:
            count = self.learning_service.import_character_images(src_dir)
            messagebox.showinfo(
                "Sucesso",
                f"Importação concluída.\n{count} imagens importadas para training_data."
            )
        except Exception as e:
            messagebox.showerror("Erro", str(e))
        finally:
            self.parent.config(cursor="")
