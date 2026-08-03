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
from core.services.task_service import BackgroundTask

from ui.canvas_view import CanvasView
from ui.status_bar import StatusBar


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

        # Trabalho pesado roda em thread separada; a UI só lê a fila.
        self.task = BackgroundTask(self)

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
        if self.task.is_running():
            if not messagebox.askyesno(
                "Operação em andamento",
                "Há uma operação rodando. Cancelar e fechar mesmo assim?",
                icon="warning",
            ):
                return
            self.task.cancel()
        if self._confirm_discard():
            self.task.shutdown()
            self.parent.destroy()

    # -------------------------------------------------------
    # Trabalho pesado fora da thread da UI
    # -------------------------------------------------------

    def _busy(self, acao="Esta operação") -> bool:
        """True (e avisa) se já houver uma tarefa rodando."""
        if self.task.is_running():
            messagebox.showinfo(
                "Aguarde",
                f"{acao} não pode começar agora: já há uma operação em andamento.\n"
                "Use 'Cancelar' na barra de status para interrompê-la."
            )
            return True
        return False

    def _run_task(self, titulo, trabalho, ao_concluir,
                  ao_cancelar=None, indeterminado=False):
        """
        Executa `trabalho(handle)` numa thread, com progresso e cancelamento.

        `trabalho` roda FORA da thread da UI e não pode tocar em widget algum —
        ela calcula e devolve dados. Quem mexe na tela é `ao_concluir`, chamado
        de volta na thread da interface.
        """
        self.status.reset_cancel_button()
        self.status.start_task(f"{titulo}...", indeterminado=indeterminado)

        def progresso(atual, total, mensagem=""):
            self.status.set_progress(atual, total, f"{titulo}: {mensagem}" if mensagem else "")

        def encerrar(texto):
            self.status.end_task(texto)
            self.status.reset_cancel_button()
            self.parent.config(cursor="")
            # Reabilita a navegação em qualquer desfecho — inclusive erro e
            # cancelamento, senão os botões ficariam travados.
            self._update_nav_controls()

        def concluir(resultado):
            encerrar(f"{titulo}: concluído.")
            ao_concluir(resultado)

        def cancelado():
            encerrar(f"{titulo}: cancelado.")
            if ao_cancelar:
                ao_cancelar()

        def falhou(exc):
            encerrar(f"{titulo}: erro.")
            messagebox.showerror(titulo, f"{type(exc).__name__}: {exc}")

        self.parent.config(cursor="watch")
        self.task.start(
            trabalho,
            on_progress=progresso,
            on_done=concluir,
            on_error=falhou,
            on_cancel=cancelado,
            on_log=self.status.set,
        )

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
        self.rowconfigure(4, weight=0)

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

        # Barra de status: mensagem + progresso + cancelar
        self.status = StatusBar(self, on_cancel=self.task.cancel)
        self.status.grid(row=4, column=0, columnspan=2, sticky="ew")

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
        if self._busy("Abrir imagem"):
            return
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
        # pdf_service é lido pela thread de trabalho; trocar o PDF por baixo
        # dela corromperia o resultado.
        if self._busy("Abrir PDF"):
            return
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
        """
        Troca de página. A renderização vai para a thread de trabalho: medido em
        ~950 ms num PDF sintético simples, e um scan de livro a 300 dpi é bem
        pior. Como virar a página é a operação mais frequente do app, fazer isso
        na thread da UI travava a janela a cada clique.
        """
        if self.task.is_running():
            return  # navegação não abre diálogo; os botões já ficam desativados

        # Arquivar o trabalho da página que sai é rápido e acontece já, antes de
        # qualquer coisa poder dar errado.
        if arquivar_atual and self.session is not None:
            self.session.store(self.current_pdf_page, self.boxes)

        self.btn_prev_page.config(state="disabled")
        self.btn_next_page.config(state="disabled")

        def trabalho(h):
            h.log(f"Renderizando página {page_index + 1}...")
            img = self.pdf_service.load_page(page_index)
            if img is None:
                raise ValueError("Nenhuma imagem retornada para a página.")
            return img

        def aplicar(page_img):
            self.image = page_img
            self.image_path = (f"{os.path.basename(self.pdf_service.pdf_path)} "
                               f"[Pág {page_index + 1}]")
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

        self._run_task(f"Página {page_index + 1}", trabalho, aplicar,
                       indeterminado=True)

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
        if self._busy("A conversão"):
            return

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

        def trabalho(h):
            def progresso(pagina, total):
                # O PDF só é gravado no fim, então cancelar aqui não deixa
                # arquivo pela metade.
                h.raise_if_cancelled()
                h.progress(pagina + 1, total, f"página {pagina + 1}/{total}")

            return substitute_chess_glyphs(input_pdf, output_pdf,
                                           progress_callback=progresso)

        def concluir(resultado):
            total_pages, replaced = resultado
            messagebox.showinfo(
                "Concluído",
                f"Conversão finalizada!\nPáginas processadas: {total_pages}\n"
                f"Substituições realizadas: {replaced}\n\nArquivo salvo em:\n{output_pdf}"
            )

        self._run_task("Substituir glifos", trabalho, concluir)

    def substitute_glyphs_neural_action(self):
        if self._busy("A conversão"):
            return

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

        def trabalho(h):
            def progresso(pagina, total):
                h.raise_if_cancelled()
                h.progress(pagina + 1, total, f"página {pagina + 1}/{total}")

            return process_scanned_pdf(
                input_pdf=input_pdf,
                output_pdf=output_pdf,
                model_path="custom_model.pth",
                meta_path="model_meta.json",
                progress_callback=progresso,
            )

        def concluir(resultado):
            total_pages, replaced = resultado
            messagebox.showinfo(
                "Concluído Neural",
                f"Conversão finalizada!\nPáginas escaneadas: {total_pages}\n"
                f"Peças reconhecidas/substituídas: {replaced}\n\n"
                f"Arquivo salvo em:\n{output_pdf}"
            )

        self._run_task("OCR neural do PDF", trabalho, concluir)

    # -------------------------------------------------------
    # OCR automático para todos os boxes
    # -------------------------------------------------------

    def _recortes_dos_boxes(self):
        """
        Recorta todos os boxes para numpy ANTES de entregar à thread.

        A PIL.Image da página é compartilhada com o redraw do canvas; deixar a
        thread de trabalho recortando dela enquanto o usuário faz pan/zoom seria
        dois acessos concorrentes ao mesmo objeto. Os recortes de caractere são
        pequenos, então o custo é baixo.
        """
        return [np.array(self.image.crop((b.x1, b.y1, b.x2, b.y2)))
                for b in self.boxes]

    def _preencher_boxes(self, titulo, preparar, resumo):
        """
        Preenche os caracteres de todos os boxes fora da thread da UI.

        `preparar(h)` roda na thread e devolve `classificar(crop) -> (char, fonte)`;
        é lá que a carga pesada acontece (o learner lê 127 mil imagens de
        referência, o predictor carrega o modelo).

        Cancelar devolve o resultado parcial: o que já foi reconhecido é aplicado
        em vez de descartado.
        """
        if self.image is None or not self.boxes:
            messagebox.showinfo("Aviso", "Não há boxes para preencher.")
            return
        if self._busy(titulo):
            return

        recortes = self._recortes_dos_boxes()
        total = len(recortes)

        def trabalho(h):
            classificar = preparar(h)
            resultados = []
            cancelado = False
            for i, crop in enumerate(recortes):
                if h.cancelled:
                    cancelado = True
                    break
                resultados.append(classificar(crop))
                if i % 5 == 0 or i == total - 1:
                    h.progress(i + 1, total, f"{i + 1}/{total}")
            return {"resultados": resultados, "cancelado": cancelado}

        def aplicar(saida):
            resultados = saida["resultados"]
            fontes = {}
            for b, (char, fonte) in zip(self.boxes, resultados):
                b.char = char
                fontes[fonte] = fontes.get(fonte, 0) + 1

            self._commit_change()
            self.update_sidebar()
            self.update_canvas()

            texto = resumo(fontes, len(resultados))
            if saida["cancelado"]:
                texto += f"\n\nCancelado: {len(resultados)} de {total} boxes processados."
                self.status.set(f"{titulo}: cancelado ({len(resultados)}/{total}).")
            messagebox.showinfo(titulo, texto)

        self._run_task(titulo, trabalho, aplicar)

    def auto_fill_characters(self):
        whitelist = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,!?+-=()#:/\'\""

        def preparar(h):
            def classificar(crop):
                ch = self.ocr_service.tesseract_ocr(Image.fromarray(crop), whitelist)
                return (ch, "tesseract")
            return classificar

        self._preencher_boxes(
            "OCR (Tesseract)", preparar,
            lambda fontes, n: f"Processados: {n} boxes.",
        )

    def auto_fill_characters_easyocr(self):
        def preparar(h):
            def classificar(crop):
                ch = self.ocr_service.easyocr_ocr(crop)
                return (ch, "easyocr" if ch else "vazio")
            return classificar

        self._preencher_boxes(
            "OCR (EasyOCR)", preparar,
            lambda fontes, n: (f"Processados: {n} boxes.\n"
                               f"Caracteres preenchidos: {fontes.get('easyocr', 0)}"),
        )

    def generate_and_fill_easyocr(self):
        self.generate_boxes_opencv()
        if self.boxes:
            self.auto_fill_characters_easyocr()

    def generate_and_fill_combined(self):
        self.generate_boxes_opencv()
        if not self.boxes:
            return

        def preparar(h):
            h.log("Carregando base de referência...")
            learner = self.learning_service._get_learner()

            def classificar(crop):
                char, fonte, _ = self.ocr_service.fallback_chain(
                    crop, learner=learner,
                    neural_threshold=0.85, learner_threshold=0.85,
                )
                return (char if fonte in ("learner", "easyocr") else "", fonte)
            return classificar

        self._preencher_boxes(
            "Detectar e preencher (Híbrido)", preparar,
            lambda fontes, n: (f"Total: {n}\n"
                               f"Encontrados via Base: {fontes.get('learner', 0)}\n"
                               f"Encontrados via OCR: {fontes.get('easyocr', 0)}"),
        )

    def generate_and_fill_neural(self):
        self.generate_boxes_opencv()
        if not self.boxes:
            return

        def preparar(h):
            h.log("Carregando modelo neural...")
            self.learning_service.load_predictor()
            h.log("Carregando base de referência...")
            learner = self.learning_service._get_learner()
            predictor = self.learning_service._predictor

            def classificar(crop):
                char, fonte, _ = self.ocr_service.fallback_chain(
                    crop, predictor=predictor, learner=learner,
                    neural_threshold=0.8, learner_threshold=0.9,
                )
                return (char, fonte)
            return classificar

        self._preencher_boxes(
            "Detectar e preencher (Neural)", preparar,
            lambda fontes, n: (f"Neural: {fontes.get('neural', 0)}\n"
                               f"Referência: {fontes.get('learner', 0)}\n"
                               f"EasyOCR: {fontes.get('easyocr', 0)}"),
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
        if self._busy("O salvamento"):
            return

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

        # A imagem da página atual é compartilhada com o canvas: copiar antes
        # de entregar à thread evita que worker e redraw leiam o mesmo objeto.
        img_atual = self.image.copy() if self.image is not None else None
        pagina_atual = self.current_pdf_page
        sessao = self.session

        def trabalho(h):
            salvos, falhas = [], []
            for n, page in enumerate(paginas):
                h.raise_if_cancelled()
                h.progress(n + 1, len(paginas), f"página {page + 1}")

                if page == pagina_atual:
                    img = img_atual
                elif sessao.is_pdf:
                    img = self.pdf_service.load_page(page)
                else:
                    img = img_atual

                if img is None:
                    falhas.append(f"pág {page + 1}: não foi possível renderizar")
                    continue

                destino = sessao.page_stem(page) + ".box"
                erro = self._write_box_pair(destino, img, sessao.boxes_for(page))
                if erro:
                    falhas.append(f"pág {page + 1}: {erro}")
                else:
                    salvos.append((page, destino))
            return salvos, falhas

        def concluir(resultado):
            salvos, falhas = resultado
            for page, _ in salvos:
                sessao.mark_saved(page)
            self._update_nav_controls()
            self._update_title()
            self._relatar_salvamento([d for _, d in salvos], falhas)

        self._run_task("Salvar todas as páginas", trabalho, concluir)

    def _relatar_salvamento(self, salvos, falhas):
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
        if self._busy("O aprendizado"):
            return

        if self.image is None or not self.boxes:
            messagebox.showinfo("Aviso", "Nada para aprender na página atual.")
            return

        if not messagebox.askyesno(
            "Confirmar Aprendizado",
            f"Deseja adicionar {len(self.boxes)} caracteres desta página à base de conhecimento?\n"
            "Certifique-se de que os caracteres estão CORRETOS antes de prosseguir."
        ):
            return

        imagem = self.image.copy()
        boxes = [b.copy() for b in self.boxes]

        def trabalho(h):
            h.progress(0, len(boxes), "gravando amostras")
            return self.learning_service.learn_from_boxes(imagem, boxes)

        def concluir(count):
            messagebox.showinfo(
                "Sucesso", f"Aprendizado concluído.\n{count} novos modelos adicionados.")

        self._run_task("Aprender com a página", trabalho, concluir, indeterminado=True)

    # -------------------------------------------------------
    # Neural Network
    # -------------------------------------------------------

    def train_neural_network(self):
        if self._busy("O treino"):
            return

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

        def trabalho(h):
            # should_stop é consultado a cada época: cancelar mantém salvo o
            # melhor modelo obtido até ali.
            return self.learning_service.train_neural(
                epochs=epochs,
                callback=h.log,
                should_stop=lambda: h.cancelled,
            )

        def concluir(sucesso):
            if sucesso:
                messagebox.showinfo(
                    "Sucesso",
                    "Treinamento concluído!\nAgora você pode usar 'Detectar e Preencher (Neural)'."
                )
            else:
                messagebox.showerror("Erro", "Falha no treinamento.")

        self._run_task("Treinar rede neural", trabalho, concluir, indeterminado=True)

    # -------------------------------------------------------
    # Treinamento Geral (Batch) & Importacao
    # -------------------------------------------------------

    def run_general_neural_training(self):
        if self._busy("O processamento em lote"):
            return

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

        def trabalho(h):
            images = []
            for n, fpath in enumerate(filepaths):
                h.raise_if_cancelled()
                ext = os.path.splitext(fpath)[1].lower()
                h.progress(n + 1, len(filepaths), f"lendo {os.path.basename(fpath)}")

                if ext == ".pdf":
                    try:
                        pages = self.pdf_service.convert_pdf_to_images(fpath, dpi=200)
                    except Exception as e:
                        if "poppler" in str(e).lower():
                            raise RuntimeError(
                                "Para ler PDF é preciso o POPPLER instalado e no PATH.\n"
                                "Baixe em: https://github.com/oschwartz10612/poppler-windows/releases/"
                            ) from e
                        raise
                    for i, page in enumerate(pages):
                        images.append((f"{os.path.basename(fpath)}_pg{i+1}", page))
                else:
                    try:
                        images.append((os.path.basename(fpath),
                                       Image.open(fpath).convert("L")))
                    except Exception:
                        continue

            def progresso(nome, atual, total):
                h.raise_if_cancelled()
                h.progress(atual, total, f"{atual}/{total} — {nome}")

            return self.learning_service.batch_extract_and_classify(
                images, output_dir, progress_callback=progresso
            )

        def concluir(total_crops):
            messagebox.showinfo(
                "Concluído",
                f"Processamento finalizado!\n{total_crops} caracteres extraídos em:\n{output_dir}"
            )

        self._run_task("Processamento em lote", trabalho, concluir)

    def import_character_images(self):
        if self._busy("A importação"):
            return

        src_dir = filedialog.askdirectory(title="Selecione a pasta de ORIGEM")
        if not src_dir:
            return

        def trabalho(h):
            h.log("Copiando imagens...")
            return self.learning_service.import_character_images(src_dir)

        def concluir(count):
            messagebox.showinfo(
                "Sucesso",
                f"Importação concluída.\n{count} imagens importadas para training_data."
            )

        self._run_task("Importar imagens", trabalho, concluir, indeterminado=True)
