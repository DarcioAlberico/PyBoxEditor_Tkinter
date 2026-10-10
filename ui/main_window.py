import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk


from core import (lexico, nags)
from core.chess_pdf_processor import (CHESS_UNICODE)
from core.services.box_service import BoxService
from config.settings import Settings
from core.services.ocr_service import (OCRService)
from core.services.pdf_service import PDFService
from core.services.learning_service import LearningService
from core.services.document_service import _GravadorAssincrono
from core.services.document_controller import DocumentController
from core.services.navigation_controller import NavigationController
from core.services.task_controller import TaskController

from ui.canvas_view import CanvasView
from ui.dialogo_de_conclusao import DialogoDeConclusao
from ui.dialogo_diagrama import DialogoDiagrama
from ui.dialogo_de_exportacao import (DialogoDeExportacao)
from ui.dialogo_do_diagrama import DialogoDoDiagrama
from ui.dialogo_semelhantes import DialogoSemelhantes
from ui.exportacao import Exportacao
from ui.menu_principal import MenuPrincipal
from ui.treino import Treino
from ui.documento import Documento
from ui.reconhecimento import Reconhecimento
# Os limiares da cadeia moram em `ui/reconhecimento.py` desde a PD-22, com a medição de
# cada um; continuam importáveis daqui para quem já os tomava daqui
# (`scripts/medidas/medir_cadeia.py`, os testes).
from ui.reconhecimento import CONF_MAXIMA_PARA_A_LINHA, CONF_MAXIMA_PARA_A_LINHA_HIBRIDO  # noqa: F401
from ui.reconhecimento import FONTES_SEM_TRAVA, LEARNER_THRESHOLD_HIBRIDO  # noqa: F401
from ui.reconhecimento import LEARNER_THRESHOLD_NEURAL, NEURAL_THRESHOLD  # noqa: F401
from ui.status_bar import StatusBar
from ui import confidence as conf_ui
from ui import fontes, tema


# Símbolos do "Key to symbols used" destes livros, por família. O agrupamento é o
# da própria página do livro, e serve para achar o botão: numa fileira única de 23
# o olho procura, em quatro grupos ele vai direto.
#
# **Todos foram conferidos contra a fonte, e não é zelo excessivo.** `Segoe UI
# Symbol` desenha os 23; `MS Gothic`, que é a candidata seguinte em
# `chess_pdf_processor.CHESS_FONT_CANDIDATES`, não tem `⩲`, `⩱`, `⌓` — nem o `⨀`
# que já estava aqui antes. Glifo ausente vira caixa vazia sem aviso, que é o
# defeito do `·` da SPEC §4.2.
# A tabela mora em `core/nags.py` desde a ED-05 (o editor de livros a usa sem esta
# janela); continua aqui com o mesmo nome para quem já a importava daqui.
from core.nags import NAGS, NAGS_POR_FAMILIA  # noqa: E402,F401

# As figurinas de peça, ao lado dos NAGs e pela mesma razão que eles existem:
# são caracteres que o teclado não tem e que aparecem em quase toda linha de
# notação. Sem o botão, escrever um `♗` é procurar o codepoint.
#
# **São 6, e não 12**, e a razão é a mesma de `searchable_pdf.PECAS`, medida no
# material real: estes livros usam **um** conjunto de figurinas para os dois
# lados — na linha "17...♞e5 18.♛c2 ♞a6 19.♞c4" o lance 17... é das pretas e o
# 19. das brancas, e os dois cavalos usam o mesmo glifo. São exatamente as 6
# classes que o modelo aprendeu (`sym_9812` a `sym_9817` na base de treino).
#
# O peão entrou depois dos outros cinco, e o botão faz mais falta nele que em
# qualquer um: ele aparece pouco — na prosa que nomeia material, `♖+♙b7 v ♖` —,
# e é justamente o glifo que ninguém tem na ponta da língua na hora de revisar.
#
# Os codepoints saem de `CHESS_UNICODE` em vez de serem redigitados aqui: é a
# mesma tabela que `resolve_chess_font` valida contra as fontes do disco, e uma
# segunda cópia poderia divergir dela sem ninguém notar.
PECAS_RAPIDAS = ("Peças", list(zip(
    CHESS_UNICODE[:6],
    ("Rei", "Dama", "Torre", "Bispo", "Cavalo", "Peão"))))


class MainWindow(tk.Frame):

    ORIGEM_TODAS = "(todas)"
    ORIGEM_VAZIA = "(sem)"

    # Quantas alterações entre gravações do rascunho. Baixo demais escreve à
    # toa; alto demais perde trabalho num travamento. 25 é ~meia linha de texto.
    AUTOSAVE_A_CADA = 25

    @property
    def session(self):
        return self.document_controller.session

    @session.setter
    def session(self, value):
        self.document_controller.session = value

    @property
    def boxes(self):
        return self.document_controller.boxes

    @boxes.setter
    def boxes(self, value):
        self.document_controller.boxes = value

    @property
    def selected_index(self):
        return self.document_controller.selected_index

    @selected_index.setter
    def selected_index(self, value):
        self.document_controller.selected_index = value

    @property
    def current_pdf_page(self):
        return self.document_controller.page

    @current_pdf_page.setter
    def current_pdf_page(self, value):
        self.document_controller.page = int(value)
        if hasattr(self, "navigation") and self.navigation.page_count:
            self.navigation.current_page = int(value)

    @property
    def history(self):
        return self.document_controller.history

    def __init__(self, parent):
        # Os fluxos da janela, por composicao (item 6 da analise de 2026-10-06 e PD-22):
        # cada um e dono dos seus metodos, e a janela delega com o mesmo nome.
        self.documento = Documento(self)  # abrir, navegar, salvar, rascunho (ui/documento.py)
        self.reconhecimento = Reconhecimento(self)  # boxes, OCR, diagramas, PDF (ui/reconhecimento.py)
        self.treino = Treino(self)  # bases, modelos, relatorios (ui/treino.py)
        self.exportacao = Exportacao(self)  # livro, documento editorial, PGN (ui/exportacao.py)
        self.menu = MenuPrincipal(self)  # a barra, o Notação, o de contexto (ui/menu_principal.py)
        super().__init__(parent)

        self.parent = parent
        self.image = None          # PIL.Image
        self.image_path = None

        # Índices dos boxes visíveis na lista. Com filtro ativo a lista deixa
        # de mapear 1:1 com self.boxes, e toda seleção precisa passar por aqui.
        self._visiveis = []

        # Léxico (F9): carregado na primeira página que precisar dele, porque são
        # 310 mil palavras e 150 ms que nunca se pagam em quem só abre um .box.
        # `None` é "ainda não tentei" e distingue de `Lexico()` vazio, que é
        # "tentei e não achei arquivo" — sem isso a carga se repetiria a cada
        # página numa instalação sem `assets/lexico/`.
        self._lexico = None
        # (chave de conteúdo, suspeitas). A conta custa 9,5 ms numa página de
        # 1.589 boxes e `update_sidebar` roda a cada tecla do modo digitação —
        # é a mesma ordem do `deepcopy` que a F3.8 teve de tirar do caminho da
        # tecla. A chave custa 0,36 ms.
        self._cache_suspeitas = (None, [])
        # O idioma do documento, conferido na primeira ação que o pede (F117).
        # Ver `idioma_da_sessao`.
        self._idioma = None
        # A ressalva do modelo já foi mostrada nesta sessão? Ver
        # `_avisar_do_modelo`: é sobre o arquivo, então uma vez basta.
        self._modelo_conferido = False
        # As preferências persistidas (`config/settings.py`), abertas na
        # primeira ação que as pede — nunca na construção da janela, que os
        # testes fazem às dezenas.
        self._configuracoes_ = None

        # Modo digitação contínua: a tecla aplica e avança, sem Enter.
        self.modo_digitacao = False

        # Última correção manual, para a F3.6. Guarda a leitura ANTERIOR: o box
        # de referência já virou 'e', e é pelo 'c' que os outros 300 são
        # achados. (índice, leitura_anterior, caractere_novo)
        self._ultima_correcao = None

        # Rascunho automático: conta mutações desde a última gravação.
        self._gravador = _GravadorAssincrono()
        self._mudancas_desde_autosave = 0

        # Documento aberto: guarda os boxes de todas as páginas visitadas
        # e o que ainda não foi gravado em disco.
        self.document_controller = DocumentController(
            autosave_writer=self._gravador,
            max_history=50,
            on_autosave=self._autosave_threshold_reached,
        )
        self.navigation = NavigationController()

        # Services
        self.box_service = BoxService()
        self.ocr_service = OCRService()
        self.pdf_service = PDFService()
        self.learning_service = LearningService()

        # Trabalho pesado roda em thread separada; a UI só lê a fila.
        self.task = TaskController(self)

        # A janela de edição de livros (ED-02), quando aberta; ver `abrir_editor_de_livro`.
        self.editor = None

        self._build_layout()
        self._build_menu()
        self._bind_keys()

        # Fechar pela janela passa pela mesma confirmação do menu Sair.
        self.parent.protocol("WM_DELETE_WINDOW", self._on_close)
        self._update_title()


    # --- documento e navegação: o corpo está em ui/documento.py; aqui só os delegados ---
    def _autosave_threshold_reached(self):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._autosave_threshold_reached()

    def _commit_change(self):
        """Registra uma mutação dos boxes: snapshot para undo + marca a página.

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._commit_change()

    def _sync_session(self):
        """Reassocia self.boxes à página atual sem marcá-la como suja.

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._sync_session()

    def _update_title(self):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._update_title()

    def _confirm_discard(self):
        """True se pode prosseguir (nada pendente, ou o usuário aceitou perder).

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._confirm_discard()

    def _gravar_rascunho(self):
        """Agenda a gravação do rascunho e zera o contador — delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._gravar_rascunho()

    def _descartar_rascunho(self):
        """Some com o rascunho: ou o trabalho foi salvo de verdade, ou o.

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._descartar_rascunho()

    def _tentar_recuperar(self):
        """Oferece o rascunho de um travamento anterior, se houver — delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._tentar_recuperar()

    def _on_close(self):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._on_close()

    def salvar_rascunho_agora(self):
        """Força a gravação do rascunho (menu / Ctrl+B) — delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento.salvar_rascunho_agora()

    def open_image(self, path=None):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento.open_image(path)

    def abrir_documento(self, path=None):
        """Ctrl+O: um diálogo só, para PDF e imagem, decidido pela extensão.

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento.abrir_documento(path)

    def open_pdf(self, path=None):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento.open_pdf(path)

    def _load_pdf_page(self, page_index, arquivar_atual=True, ao_concluir=None, ao_falhar=None, ao_cancelar=None):
        """Troca de página. A renderização vai para a thread de trabalho: medido em.

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._load_pdf_page(page_index, arquivar_atual, ao_concluir, ao_falhar, ao_cancelar)

    def prev_page(self):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento.prev_page()

    def next_page(self):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento.next_page()

    def ir_para_pagina(self, numero=None):
        """Vai direto para a página `numero` (1 é a primeira) — delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento.ir_para_pagina(numero)

    def _update_nav_controls(self):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._update_nav_controls()

    def _perguntar_entrada(self, titulo, tipos):
        """O arquivo de entrada, começando na pasta da última vez — delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._perguntar_entrada(titulo, tipos)

    def _maximizada(self):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._maximizada()

    def _estado_da_janela(self, anterior=None):
        """O que `gravar_estado_da_janela` guarda. Maximizada, a geometria que.

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._estado_da_janela(anterior)

    def gravar_estado_da_janela(self):
        """Guarda a geometria e os filtros no `settings.json` (ao fechar).

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento.gravar_estado_da_janela()

    def _geometria_que_cabe(self, geometria):
        """A geometria gravada ainda cabe na tela de agora? Numa tela menor —.

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._geometria_que_cabe(geometria)

    def restaurar_estado_da_janela(self):
        """Devolve a geometria e os filtros da última vez (`appy.main`, ao abrir).

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento.restaurar_estado_da_janela()

    def _abridor_do_editor(self, documento):
        """O `abrir_no_editor` da caixa de conclusão: o arquivo exportado **e** o documento da sessão.

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._abridor_do_editor(documento)

    def _editor_sobre(self, documento):
        """O editor de livros está aberto sobre este documento (a ponte é dele; a fila não exporta).

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._editor_sobre(documento)

    def abrir_editor_de_livro(self, caminho=None, documento=None):
        """Arquivo → Editor de livro... (ED-02): a janela de edição, separada e sem.

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento.abrir_editor_de_livro(caminho, documento)

    def _destino_sugerido(self, ext, padrao):
        """Pasta e nome que o diálogo de salvar propõe para a página atual.

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._destino_sugerido(ext, padrao)

    def save_box_file(self):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento.save_box_file()

    def _salvar_box_em_tarefa(self, path):
        """O Ctrl+S grava numa tarefa (item 9 da revisão de 2026-09-18).

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._salvar_box_em_tarefa(path)

    def load_box_file(self):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento.load_box_file()

    def save_all_pages(self):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento.save_all_pages()

    def _relatar_salvamento(self, salvos, falhas, palavras=()):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._relatar_salvamento(salvos, falhas, palavras)

    def _write_box_pair(self, path, image, boxes):
        """Escreve o par .box/.png. Devolve None em caso de sucesso, ou a mensagem.

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._write_box_pair(path, image, boxes)

    def _save_box_to_path(self, path):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._save_box_to_path(path)

    def _depois_de_salvar(self, path, marcar_salva=True):
        """O que a janela faz com o par gravado: a página sai da lista das não.

        Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._depois_de_salvar(path, marcar_salva)

    def _load_box_from_path(self, path, marcar_sujo=True):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._load_box_from_path(path, marcar_sujo)

    def _perform_undo(self):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._perform_undo()

    def _perform_redo(self):
        """Delegado a `ui.documento.Documento` (PD-22)."""
        return self.documento._perform_redo()


    # -------------------------------------------------------
    # Trabalho pesado fora da thread da UI
    # -------------------------------------------------------

    #: Quanto uma sondagem pode levar antes de a janela passar a processar
    #: eventos enquanto espera (PD-02). Abaixo disso não há o que mostrar.
    ESPERA_SEM_EVENTOS_S = 0.2

    def _esperar_sem_travar(self, rotulo, funcao):
        """`funcao()` numa thread, e a thread da interface esperando por ela
        **sem parar de processar eventos** (PD-02).

        É para as sondagens curtas que abrem uma caixa — a régua da camada de
        texto (`pdf_nativo.amostrar`, 5,5 s no livro do Darcy Lima), o idioma
        do livro, o Tesseract —, que precisam do resultado **antes** de a
        caixa abrir e por isso não cabem no `_run_task`. O que a janela não
        pode é ficar sem responder: passados `ESPERA_SEM_EVENTOS_S`, ela
        redesenha e atende o mouse, com a barra de status dizendo o que
        espera. Nesse intervalo `_busy` recusa outra tarefa e fechar pede para
        aguardar. `funcao` não toca em widget; a exceção dela sobe aqui.
        """
        resultado = {}

        def alvo():
            try:
                resultado["valor"] = funcao()
            except BaseException as erro:  # noqa: BLE001 — relançada abaixo
                resultado["erro"] = erro

        linha = threading.Thread(target=alvo, daemon=True, name="sondagem")
        linha.start()
        linha.join(self.ESPERA_SEM_EVENTOS_S)
        if linha.is_alive():
            self._sondando = rotulo
            cursor = self.parent.cget("cursor")
            try:
                self.status.set(f"{rotulo}...")
                self.parent.config(cursor="watch")
                while linha.is_alive():
                    self.parent.update()
                    linha.join(0.03)
            finally:
                self._sondando = None
                try:
                    self.parent.config(cursor=cursor)
                    self.status.set("")
                except tk.TclError:
                    pass
        if "erro" in resultado:
            raise resultado["erro"]
        return resultado.get("valor")

    def _busy(self, acao="Esta operação") -> bool:
        """True (e avisa) se já houver uma tarefa rodando."""
        if getattr(self, "_sondando", None):
            messagebox.showinfo(
                "Aguarde",
                f"{acao} não pode começar agora: "
                f"{self._sondando[0].lower()}{self._sondando[1:]}.")
            return True
        if self.task.is_running():
            messagebox.showinfo(
                "Aguarde",
                f"{acao} não pode começar agora: já há uma operação em andamento.\n"
                "Use 'Cancelar' na barra de status para interrompê-la."
            )
            return True
        return False

    def _run_task(self, titulo, trabalho, ao_concluir,
                  ao_cancelar=None, indeterminado=False, ao_falhar=None):
        """
        Executa `trabalho(handle)` numa thread, com progresso e cancelamento.

        `trabalho` roda FORA da thread da UI e não pode tocar em widget algum —
        ela calcula e devolve dados. Quem mexe na tela é `ao_concluir`, chamado
        de volta na thread da interface.

        `ao_falhar(exc)` recebe a exceção antes do aviso genérico e devolve
        `True` quando já tratou o caso. É o que deixa uma falha *conhecida* —
        base de treino inválida, por exemplo — virar uma pergunta útil em vez
        de um "DatasetInvalido: ..." que o usuário não tem como responder.
        """
        # A guarda vale aqui, e não só em quem chama: o handler que esquecia o
        # `_busy` (o treino de diagramas esquecia) reiniciava a barra de status
        # com o título novo, e `task.start` devolvia `False` para ninguém — o
        # trabalho não rodava e a tela dizia que sim.
        if self._busy(titulo):
            return False
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
            if ao_falhar and ao_falhar(exc):
                return
            messagebox.showerror(titulo, f"{type(exc).__name__}: {exc}")

        self.parent.config(cursor="watch")
        iniciada = self.task.start(
            trabalho,
            on_progress=progresso,
            on_done=concluir,
            on_error=falhou,
            on_cancel=cancelado,
            on_log=self.status.set,
        )
        if not iniciada:
            encerrar(f"{titulo}: não iniciada — já há uma operação em andamento.")
        return iniciada

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

        sidebar.rowconfigure(0, weight=0)
        sidebar.rowconfigure(1, weight=1)

        # --- Filtros -------------------------------------------------
        self.var_busca = tk.StringVar()
        self.var_so_pendentes = tk.BooleanVar(value=False)
        self.var_so_vazios = tk.BooleanVar(value=False)
        self.var_so_fora_dicionario = tk.BooleanVar(value=False)
        self.var_origem = tk.StringVar(value=self.ORIGEM_TODAS)

        filtros = tk.LabelFrame(sidebar, text="Filtrar")
        filtros.grid(row=0, column=0, sticky="ew", padx=2, pady=2)

        linha1 = tk.Frame(filtros)
        linha1.pack(fill="x", padx=2, pady=1)
        tk.Label(linha1, text="Caractere:").pack(side="left")
        self.entry_busca = tk.Entry(linha1, textvariable=self.var_busca, width=8)
        self.entry_busca.pack(side="left", padx=3)
        tk.Button(linha1, text="Limpar", command=self.limpar_filtros,
                  padx=2).pack(side="left")

        tk.Checkbutton(filtros, text="só pendentes", variable=self.var_so_pendentes,
                       command=self.on_boxes_changed_view).pack(anchor="w", padx=2)
        tk.Checkbutton(filtros, text="só vazios", variable=self.var_so_vazios,
                       command=self.on_boxes_changed_view).pack(anchor="w", padx=2)
        self.chk_fora_dicionario = tk.Checkbutton(
            filtros, text="só fora do dicionário",
            variable=self.var_so_fora_dicionario,
            command=self.on_boxes_changed_view)
        self.chk_fora_dicionario.pack(anchor="w", padx=2)

        linha2 = tk.Frame(filtros)
        linha2.pack(fill="x", padx=2, pady=1)
        tk.Label(linha2, text="Origem:").pack(side="left")
        self.combo_origem = ttk.Combobox(linha2, textvariable=self.var_origem,
                                         width=12, state="readonly",
                                         values=[self.ORIGEM_TODAS])
        self.combo_origem.pack(side="left", padx=3)
        self.combo_origem.bind("<<ComboboxSelected>>",
                               lambda e: self.on_boxes_changed_view())

        self.lbl_filtro = tk.Label(filtros, text="", fg=tema.TEXTO_SECUNDARIO)
        self.lbl_filtro.pack(anchor="w", padx=2)

        # Filtrar a cada tecla: com 2.000 boxes o custo é irrelevante perto do
        # ganho de ver o resultado enquanto digita.
        self.var_busca.trace_add("write", lambda *a: self.on_boxes_changed_view())

        # --- Lista ---------------------------------------------------
        frame_list = tk.Frame(sidebar)
        frame_list.grid(row=1, column=0, sticky="ns")

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
        tk.Button(editor, text="Próximo >>", command=self.apply_char_and_next).grid(row=0, column=3, padx=5)
        self.btn_ocr_box = tk.Button(editor, text="OCR (box)", command=self.ocr_selected_box)
        self.btn_ocr_box.grid(row=0, column=4, padx=5)

        tk.Button(editor, text="Digitação (F2)",
                  command=self.alternar_modo_digitacao).grid(row=0, column=5, padx=5)

        # O caminho pelo menu continua existindo, mas ler diagrama é ação de
        # página, não de configuração: escondê-la em Ferramentas fazia dela um
        # recurso que só quem já sabia encontrava (F8.2).
        self.btn_diagramas = tk.Button(editor, text="Diagramas...",
                                       command=self.extrair_diagramas)
        self.btn_diagramas.grid(row=0, column=6, padx=5)

        # Indicador do modo: sem ele o usuário não sabe por que as teclas
        # mudaram de comportamento.
        self.lbl_modo = tk.Label(editor, text="", font=("Segoe UI", 9, "bold"))
        self.lbl_modo.grid(row=0, column=7, padx=8)

        # NAGs Quick Access
        nag_frame = tk.Frame(self)
        nag_frame.grid(row=2, column=0, columnspan=2, sticky="ew")

        # **Duas linhas, e não uma.** Os 23 símbolos em fila única pedem 1.076 px
        # e a janela mínima tem 1.024 (`appy.LARGURA_MINIMA`): com `side="left"`
        # o excesso é cortado à direita sem aviso, e sumiriam justamente os dois
        # últimos. É o mesmo defeito que o `appy._geometria_que_cabe` existe para
        # não repetir — lá o sintoma foi "o botão de próxima página não aparece".
        # As peças entram na segunda faixa, que é a curta: a primeira já leva 16
        # botões e é ela que define a largura mínima da janela.
        #
        # Só as figurinas passam pela conferência de fonte, e é onde ela importa:
        # os NAGs desta tabela foram conferidos um a um quando ela foi escrita,
        # mas peça é o caso em que a fonte falta de verdade — a maioria das
        # fontes comuns não desenha as 12, e é por isso que
        # `resolve_chess_font` existe. Botão que escreve um caractere que vira
        # retângulo vazio no PDF é o defeito do `·` da SPEC §4.2, e aqui ele fica
        # desligado em vez de mentir.
        sem_desenho = nags.sem_glifo([c for c, _ in PECAS_RAPIDAS[1]])

        # A fonte padrão do botão, escrita como tripla para servir de base à
        # escolha de família. Perguntar ao Tk em vez de fixar "Segoe UI 9" é o
        # que garante que os 22 botões que não trocam de família fiquem **byte a
        # byte** com a aparência de antes.
        padrao = tkfont.nametofont("TkDefaultFont")
        FONTE_BOTAO_NAG = (padrao.cget("family"), padrao.cget("size"),
                           padrao.cget("weight"))

        for faixa, familias in ((0, NAGS_POR_FAMILIA[:2]),
                                (1, NAGS_POR_FAMILIA[2:] + [PECAS_RAPIDAS])):
            linha = tk.Frame(nag_frame)
            linha.pack(fill="x")
            tk.Label(linha, text="NAGs Rápidos:" if not faixa else "").pack(
                side="left", padx=5, pady=1)
            for titulo, familia in familias:
                # Um rótulo separa as famílias. Sem ele, 23 botões iguais viram
                # uma parede: o agrupamento é o que faz achar o `!?` sem ler os
                # anteriores um a um.
                tk.Label(linha, text=titulo, fg=tema.TEXTO_SECUNDARIO).pack(side="left",
                                                               padx=(8, 2))
                for nag_char, tooltip in familia:
                    faltando = nag_char in sem_desenho
                    # O botão do `⯹` é o caso: o arquivo da fonte estar em
                    # `assets/fonts/` não basta para o Tk desenhá-lo, e sem esta
                    # escolha o botão sairia como retângulo vazio — habilitado,
                    # porque `sem_glifo` (que lê o arquivo) diz que há desenho.
                    # Os outros 22 não passam por aqui: `fonte_do_rotulo` só
                    # troca a família do que nenhuma fonte do sistema tem.
                    btn = tk.Button(
                        linha, text=nag_char, width=3,
                        font=fontes.fonte_do_rotulo(nag_char, FONTE_BOTAO_NAG),
                        state="disabled" if faltando else "normal",
                        command=lambda c=nag_char: self.apply_nag(c))
                    dica = f"{tooltip} (sem fonte)" if faltando else tooltip
                    btn.bind("<Enter>",
                             lambda e, text=dica: self.show_nag_tooltip(text))
                    btn.bind("<Leave>", lambda e: self.hide_nag_tooltip())
                    btn.pack(side="left", padx=1, pady=1)
            if faixa:
                self.lbl_tooltip = tk.Label(linha, text="", fg=tema.TEXTO_SECUNDARIO)
                self.lbl_tooltip.pack(side="left", padx=10)

        # Barra de Navegacao PDF
        self.nav_frame = tk.Frame(self)
        self.nav_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=5)
        self.nav_frame.columnconfigure(1, weight=1)

        # **A ordem de empacotamento é a ordem de sobrevivência.** Quando a
        # barra não cabe na janela, o Tk corta quem foi empacotado por último.
        # Antes, o rótulo de página ficava ENTRE os dois botões e crescia com o
        # uso — "Página: 108/120 | 14 pág. com boxes, 4200 no total | 14 não
        # salva(s)" mede 381 px — e empurrava o "Próxima Página >>" para fora.
        # O usuário via o botão de voltar e não via o de avançar.
        #
        # Agora os controles ficam juntos num grupo próprio, empacotado
        # primeiro: exigem ~330 px e nada que venha depois os espreme.
        controles = tk.Frame(self.nav_frame)
        controles.pack(side="left")

        self.btn_prev_page = tk.Button(controles, text="<< Anterior",
                                       command=self.prev_page, state="disabled")
        self.btn_prev_page.pack(side="left", padx=(10, 4))

        self.btn_next_page = tk.Button(controles, text="Próxima >>",
                                       command=self.next_page, state="disabled")
        self.btn_next_page.pack(side="left", padx=4)

        # Ir direto para uma página. Num livro de 300 páginas, chegar à 108 de
        # "próxima" em "próxima" são 107 renderizações e 107 esperas — o
        # caminho existia, mas não servia.
        tk.Label(controles, text="Ir para:").pack(side="left", padx=(12, 2))
        self.entry_pagina = tk.Entry(controles, width=5, state="disabled")
        self.entry_pagina.pack(side="left")
        self.entry_pagina.bind("<Return>", lambda e: self.ir_para_pagina())
        self.btn_ir = tk.Button(controles, text="Ir", state="disabled",
                                command=self.ir_para_pagina)
        self.btn_ir.pack(side="left", padx=(3, 10))

        # Curto de propósito: só "Página: 108/120". O detalhe da sessão foi para
        # um rótulo próprio, que pode ser cortado sem levar botão nenhum junto.
        self.lbl_page_info = tk.Label(self.nav_frame, text="Página: -/-")
        self.lbl_page_info.pack(side="left", padx=(6, 10))

        # Legenda da escala de confiança — sem ela as cores são adivinhação.
        legenda = tk.Frame(self.nav_frame)
        legenda.pack(side="left", padx=12)
        for cor, texto in conf_ui.LEGENDA:
            tk.Label(legenda, text="\u25a0", fg=cor).pack(side="left")
            tk.Label(legenda, text=texto, fg=tema.TEXTO_SECUNDARIO).pack(side="left", padx=(0, 8))

        # O l\u00e9xico entra com um tra\u00e7o, n\u00e3o com um quadrado: no canvas ele \u00e9 um
        # sublinhado sob o box, e a legenda tem de parecer com o que se v\u00ea l\u00e1.
        cor_lex, texto_lex = conf_ui.LEGENDA_LEXICO
        tk.Label(legenda, text="\u2581", fg=cor_lex).pack(side="left")
        tk.Label(legenda, text=texto_lex, fg=tema.TEXTO_SECUNDARIO).pack(side="left")

        self.lbl_revisao = tk.Label(self.nav_frame, text="", fg=tema.TEXTO_SECUNDARIO)
        self.lbl_revisao.pack(side="left", padx=10)

        # Último a ser empacotado é o primeiro a ser cortado — e é o que menos
        # falta faz: quantas páginas têm boxes e quantas estão por salvar já
        # aparece no título da janela.
        self.lbl_sessao = tk.Label(self.nav_frame, text="", fg=tema.TEXTO_SECUNDARIO)
        self.lbl_sessao.pack(side="left", padx=6)

        # Barra de status: mensagem + progresso + cancelar
        self.status = StatusBar(self, on_cancel=self.task.cancel)
        self.status.grid(row=4, column=0, columnspan=2, sticky="ew")

        self._build_context_menu()


    # --- menus: a tabela e o corpo estão em ui/menu_principal.py; aqui só os delegados ---
    def _build_menu(self):
        """A barra de menus, da tabela `BARRA` — delegado a `ui.menu_principal.MenuPrincipal` (PD-22)."""
        return self.menu.montar()

    def _build_context_menu(self):
        """O menu de contexto da lista — delegado a `ui.menu_principal.MenuPrincipal` (PD-22)."""
        return self.menu._build_context_menu()

    def show_context_menu(self, event):
        """Delegado a `ui.menu_principal.MenuPrincipal` (PD-22)."""
        return self.menu.show_context_menu(event)

    def mostrar_atalhos(self):
        """A lista de atalhos, num diálogo que dá para copiar — delegado a `ui.menu_principal.MenuPrincipal` (PD-22)."""
        return self.menu.mostrar_atalhos()

    def mostrar_sobre(self):
        """Delegado a `ui.menu_principal.MenuPrincipal` (PD-22)."""
        return self.menu.mostrar_sobre()

    def abrir_janela_rotulagem(self):
        """A rotulagem de glifos da página — delegado a `ui.menu_principal.MenuPrincipal` (PD-22)."""
        return self.menu.abrir_janela_rotulagem()


    # -------------------------------------------------------
    # Keybindings
    # -------------------------------------------------------

    def _bind_keys(self):
        root = self.parent
        root.bind("<Up>", self._on_key_up)
        root.bind("<Down>", self._on_key_down)
        root.bind("<Delete>", self._on_key_delete)
        root.bind("<BackSpace>", self._on_key_backspace)
        # Dividir saiu de 'd' para Ctrl+D: com o modo digitação, uma tecla nua
        # não pode disparar comando — 'd' precisa poder ser digitado. (O guard
        # antigo só testava tk.Entry e não cobria ttk.Entry nem Combobox.)
        root.bind("<Control-d>", self._on_key_split_safe)
        root.bind("<Control-D>", self._on_key_split_safe)
        # E no campo do caractere, que é a exceção do guard: ver
        # `_on_key_split_no_campo` para por que a binding é do widget.
        self.char_entry.bind("<Control-d>", self._on_key_split_no_campo)
        self.char_entry.bind("<Control-D>", self._on_key_split_no_campo)
        root.bind("<Control-b>", lambda e: self.salvar_rascunho_agora())
        root.bind("<Control-e>", lambda e: (self.aplicar_aos_semelhantes(),
                                            "break")[1])
        root.bind("<Control-E>", lambda e: (self.aplicar_aos_semelhantes(),
                                            "break")[1])
        root.bind("<F2>", lambda e: self.alternar_modo_digitacao())
        root.bind("<Escape>", self._on_key_escape)
        root.bind("<Key>", self._on_tecla_digitacao)
        root.bind("<Control-s>", lambda e: (self.save_box_file(), "break")[1])
        root.bind("<Control-S>", lambda e: (self.save_all_pages(), "break")[1])
        root.bind("<Prior>", lambda e: (self.prev_page(), "break")[1])
        root.bind("<Next>", lambda e: (self.next_page(), "break")[1])
        root.bind("<Control-g>", self._on_key_ir_para_pagina)
        root.bind("<Control-G>", self._on_key_ir_para_pagina)
        root.bind("<F4>", self._on_key_zoom)
        # O zoom do menu Exibir. `<Control-Key-1>`, e não `<Control-1>`, que é o
        # clique do botão 1 com Ctrl.
        for sequencia in ("<Control-equal>", "<Control-plus>", "<Control-KP_Add>"):
            root.bind(sequencia, lambda e: (self.canvas.aproximar(1), "break")[1])
        for sequencia in ("<Control-minus>", "<Control-KP_Subtract>"):
            root.bind(sequencia, lambda e: (self.canvas.aproximar(-1), "break")[1])
        root.bind("<Control-Key-0>", lambda e: (self.canvas.ajustar_a_janela(), "break")[1])
        root.bind("<Control-Key-1>", lambda e: (self.canvas.tamanho_real(), "break")[1])
        root.bind("<F3>", lambda e: self.proximo_pendente(1))
        root.bind("<Shift-F3>", lambda e: self.proximo_pendente(-1))
        root.bind("<Control-f>", lambda e: (self.entry_busca.focus_set(),
                                            self.entry_busca.select_range(0, "end"),
                                            "break")[2])
        root.bind("<Control-z>", self._on_key_undo)
        root.bind("<Control-y>", self._on_key_redo)
        root.bind("<Control-Z>", self._on_key_redo)  # Shift+Ctrl+Z fallback
        root.bind("<Control-o>", lambda e: (self.abrir_documento(), "break")[1])
        root.bind("<Control-O>", lambda e: (self.abrir_documento(), "break")[1])
        root.bind("<Tab>", lambda e: self._on_key_tab(1))
        root.bind("<Shift-Tab>", lambda e: self._on_key_tab(-1))
        # No X11 o Shift+Tab chega como ISO_Left_Tab, não como Shift-Tab.
        root.bind("<ISO_Left_Tab>", lambda e: self._on_key_tab(-1))

    # -------------------------------------------------------
    # Modo digitação contínua
    # -------------------------------------------------------

    AVISO_DIGITACAO = ("MODO DIGITAÇÃO — a tecla aplica e avança  |  "
                       "Espaço pula  |  Backspace volta  |  Esc sai")

    def alternar_modo_digitacao(self, ligar=None):
        """
        Liga/desliga a digitação contínua (F2).

        Fora dele, rotular um caractere custa duas teclas: o caractere e o
        Enter. Numa página de 2.000 caracteres isso são 2.000 teclas a mais.
        """
        novo = (not self.modo_digitacao) if ligar is None else bool(ligar)
        if novo == self.modo_digitacao:
            return "break"
        self.modo_digitacao = novo

        if novo:
            if not self.boxes:
                self.modo_digitacao = False
                self.status.set("Nada para digitar: a página não tem boxes.")
                return "break"
            if self.linha_do_box(self.selected_index) is None and self._visiveis:
                self.select_box(self._visiveis[0])
            # Tirar o foco do campo de texto é o que permite capturar as teclas
            # sem que o Entry as consuma antes.
            self.canvas.focus_set()
            self.lbl_modo.config(text="  ⌨ DIGITAÇÃO  ", bg=tema.SELECAO, fg="black")
            self._status_digitacao()
        else:
            self.lbl_modo.config(text="", bg=self.cget("bg"))
            self.char_entry.focus_set()
            self.status.set("Modo digitação desligado.")

        self.update_canvas()
        return "break"

    def _status_digitacao(self):
        pendentes = sum(1 for i in self._visiveis
                        if conf_ui.precisa_revisao(self.boxes[i]))
        pos = self.linha_do_box(self.selected_index)
        onde = f"{pos + 1}/{len(self._visiveis)}" if pos is not None else "-"
        self.status.set(f"{self.AVISO_DIGITACAO}   [{onde}, {pendentes} pendentes]")

    def _on_key_escape(self, event):
        if self.modo_digitacao:
            return self.alternar_modo_digitacao(False)
        return None

    def _on_key_backspace(self, event):
        """Backspace volta um box no modo digitação; fora dele, exclui.

        **Nunca com o foco num campo de texto**: ali o Backspace apaga uma
        letra, e é só isso que ele deve fazer. A binding da raiz roda depois
        da do `Entry`, e sem esta guarda apagar o caractere do campo
        "Caractere" (o destino do Tab e do Enter) apagava também o box.
        """
        if self._foco_em_campo_de_texto():
            return None
        if self.modo_digitacao:
            self._mover_selecao(-1)
            self._status_digitacao()
            return "break"
        return self._on_key_delete(event)

    def _on_tecla_digitacao(self, event):
        """
        Captura uma tecla imprimível e a aplica ao box selecionado.

        Teclas de controle (setas, F3, Ctrl+algo) têm event.char vazio ou não
        imprimível, então caem fora naturalmente e seguem para seus atalhos.
        """
        if not self.modo_digitacao:
            return None

        # Se o foco está num campo de texto (busca, caractere), quem manda é ele.
        if self._foco_em_campo_de_texto():
            return None

        ch = event.char
        if not ch or not ch.isprintable():
            return None

        if ch == " ":
            # Espaço avança sem alterar. Na revisão, a maioria dos caracteres
            # está certa: dá para passar por eles sem digitar nada.
            self._mover_selecao(1)
            self._status_digitacao()
            return "break"

        if self.selected_index < 0 or self.selected_index >= len(self.boxes):
            return "break"

        b = self.boxes[self.selected_index]
        anterior = b.char
        b.char = ch
        b.confidence = 1.0
        b.source = "manual"
        # É por aqui que passa a maior parte das correções (a F3.1 fez desta a
        # via principal), então é aqui que a F3.6 mais precisa da leitura
        # anterior — sem isto, Ctrl+E depois do modo digitação casaria só pela
        # imagem e perderia o filtro que segura a precisão.
        if anterior != ch:
            self._ultima_correcao = (self.selected_index, b, anterior, ch)
        self._commit_change()
        self._avancar_apos_edicao(self.selected_index)
        self._status_digitacao()
        return "break"

    # -------------------------------------------------------
    # Imagem
    # -------------------------------------------------------


    #: Extensões que `abrir_documento` reconhece como imagem de página.
    EXTENSOES_DE_IMAGEM = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")


    # --- reconhecimento: o corpo está em ui/reconhecimento.py; aqui só os delegados ---
    def _avisar_do_modelo(self):
        """Mostra a ressalva do modelo carregado, **uma vez por sessão**.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento._avisar_do_modelo()

    def _confirmar_motor_de_prosa(self, idioma: str):
        """Sonda o Tesseract para `idioma` antes de uma leitura de livro.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento._confirmar_motor_de_prosa(idioma)

    def _arbitro_de_corte(self):
        """O classificador que confirma cada corte de glifo colado (F1.5b).

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento._arbitro_de_corte()

    def generate_boxes_opencv(self, ao_concluir=None):
        """Regera os boxes da página numa tarefa (item 9 da revisão de 2026-09-18).

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.generate_boxes_opencv(ao_concluir)

    def substitute_chess_glyphs_action(self):
        """Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.substitute_chess_glyphs_action()

    @staticmethod
    def _saida_do_beco(rel):
        """O que fazer diante de um relatório vazio. Depende de qual vazio é.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return Reconhecimento._saida_do_beco(rel)

    def substitute_glyphs_neural_action(self):
        """Substitui as peças reconhecidas E deixa o PDF pesquisável.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.substitute_glyphs_neural_action()

    def corrigir_mapeamento_action(self):
        """Conserta a tabela que diz qual caractere cada glifo representa.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.corrigir_mapeamento_action()

    def _perguntar_teto(self):
        """Pergunta o teto por classe da coleta. Em branco é sem teto.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento._perguntar_teto()

    def _perguntar_sobre_paginas_com_texto(self, input_pdf):
        """True = pular as páginas que já têm texto, False = reprocessar, None = desistir.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento._perguntar_sobre_paginas_com_texto(input_pdf)

    def _acao_ocr_pdf(self, modo, titulo, titulo_saida):
        """Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento._acao_ocr_pdf(modo, titulo, titulo_saida)

    def _recortes_dos_boxes(self):
        """Recorta todos os boxes para numpy ANTES de entregar à thread.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento._recortes_dos_boxes()

    def _preencher_boxes(self, titulo, preparar, resumo):
        """Preenche os caracteres de todos os boxes fora da thread da UI.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento._preencher_boxes(titulo, preparar, resumo)

    def auto_fill_characters(self):
        """Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.auto_fill_characters()

    def auto_fill_characters_easyocr(self):
        """Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.auto_fill_characters_easyocr()

    def generate_and_fill_easyocr(self):
        """Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.generate_and_fill_easyocr()

    def auto_fill_characters_paddleocr(self):
        """Preenche os boxes atuais com o reconhecedor opcional PaddleOCR.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.auto_fill_characters_paddleocr()

    def auto_fill_characters_linha(self, languages=('en',), ao_concluir=None):
        """Lê a linha inteira, e não o caractere (F17) — delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.auto_fill_characters_linha(languages, ao_concluir)

    def auto_fill_characters_linha_treinada(self):
        """Aplica o CRNN/CTC treinado às linhas e distribui o texto nos boxes.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.auto_fill_characters_linha_treinada()

    def _recortes_do_box(self, pagina, b, faixas):
        """`(justo, com a faixa da linha)` — ver `_recortes_dos_boxes`.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento._recortes_do_box(pagina, b, faixas)

    def _preencher_por_linha(
            self, titulo, preparar, resumo, conf_maxima_para_trocar=None, exigir_confianca_linha=False,
            confianca_linha_minima=None, confianca_ancora_maxima=None, ao_concluir=None, languages=('en',),
            poda=None):
        """Como `_preencher_boxes`, mas o laço é por **linha** e não por box.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento._preencher_por_linha(
            titulo, preparar, resumo, conf_maxima_para_trocar, exigir_confianca_linha,
            confianca_linha_minima, confianca_ancora_maxima, ao_concluir, languages, poda)

    def generate_and_fill_linha(self):
        """Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.generate_and_fill_linha()

    def generate_and_fill_combined(self):
        """Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.generate_and_fill_combined()

    @staticmethod
    def _frase_do_idioma(idioma):
        """A linha do diálogo que diz que máscara de alfabeto valeu (F117).

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return Reconhecimento._frase_do_idioma(idioma)

    def generate_and_fill_neural(self):
        """Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.generate_and_fill_neural()

    def lexico_da_sessao(self):
        """O léxico desta sessão: a lista geral mais a deste livro (F9.2).

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.lexico_da_sessao()

    def _caminho_do_lexico(self):
        """Onde fica a lista deste livro, ou None sem documento aberto.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento._caminho_do_lexico()

    def _esquecer_lexico(self):
        """Força a recarga do léxico e das suspeitas — chamada ao abrir.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento._esquecer_lexico()

    @staticmethod
    def _idioma_do_livro(caminho_pdf, perguntar=True):
        """`(idioma, detectado)` de um PDF (F109) — delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return Reconhecimento._idioma_do_livro(caminho_pdf, perguntar)

    def idioma_da_sessao(self):
        """O idioma do documento aberto, ou `None` — que desliga a máscara.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.idioma_da_sessao()

    def aprender_palavras_da_pagina(self, boxes=None):
        """Põe no dicionário do livro as palavras que o usuário sustentou.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.aprender_palavras_da_pagina(boxes)

    def aprender_palavras_das_paginas(self, paginas):
        """O mesmo, para várias páginas de uma vez, gravando o arquivo uma só vez.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.aprender_palavras_das_paginas(paginas)

    def _frase_do_dicionario(self, palavras):
        """A linha de relatório das palavras novas, ou string vazia.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento._frase_do_dicionario(palavras)

    def referencia_do_lote(self):
        """Qual box serve de modelo, e por qual leitura procurar. `(i, char, leitura)`.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.referencia_do_lote()

    def aplicar_aos_semelhantes(self):
        """Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.aplicar_aos_semelhantes()

    def aplicar_em_lote(self, indices, char):
        """Grava `char` em todos os índices e devolve quantos mudaram.

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.aplicar_em_lote(indices, char)

    def ocr_selected_box(self):
        """Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.ocr_selected_box()

    def split_selected_box(self):
        """Ctrl+D: parte o box selecionado em dois — delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.split_selected_box()

    def delete_selected_box(self):
        """Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.delete_selected_box()

    def extrair_diagramas(self):
        """Lê a posição dos diagramas da página (F7.1, corrigida na F8.3).

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.extrair_diagramas()

    def _origem_da_pagina(self):
        """Nome que identifica a página atual, para a procedência da amostra (F8.3).

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento._origem_da_pagina()

    def validar_notacao(self):
        """Confronta a notação da página com as regras do xadrez (F1.7).

        Delegado a `ui.reconhecimento.Reconhecimento` (PD-22)."""
        return self.reconhecimento.validar_notacao()


    # --- exportação: o corpo está em ui/exportacao.py; aqui só os delegados ---
    def gerar_pdf_pesquisavel_action(self):
        """PDF pesquisável: mantém a página como está e só acrescenta o texto.

        Delegado a `ui.exportacao.Exportacao` (item 6 da análise de 2026-10-06).
        """
        return self.exportacao.gerar_pdf_pesquisavel_action()

    def _preparar_exportacao(self, entrada, formatos, titulo):
        """Tudo que a caixa de exportação precisa saber antes de abrir, e a caixa.

        Delegado a `ui.exportacao.Exportacao` (item 6 da análise de 2026-10-06).
        """
        return self.exportacao._preparar_exportacao(entrada, formatos, titulo)

    def processar_documento_editorial_action(self):
        """Lê um PDF ou imagem com o leitor de produção e grava o documento.

        Delegado a `ui.exportacao.Exportacao` (item 6 da análise de 2026-10-06).
        """
        return self.exportacao.processar_documento_editorial_action()

    def _escrever_documento_editorial(self, pipeline, documento, paginas, opcoes, origem: str):
        """Grava o documento editorial em `opcoes.saida`, no formato pedido.

        Delegado a `ui.exportacao.Exportacao` (item 6 da análise de 2026-10-06).
        """
        return self.exportacao._escrever_documento_editorial(pipeline, documento, paginas, opcoes, origem)

    def revisar_documento_editorial_action(self):
        """Abre a fila de suspeitas do último documento processado.

        Delegado a `ui.exportacao.Exportacao` (item 6 da análise de 2026-10-06).
        """
        return self.exportacao.revisar_documento_editorial_action()

    def _exportar_documento_revisado(self, documento):
        """Regrava o último arquivo exportado com as decisões da revisão.

        Delegado a `ui.exportacao.Exportacao` (item 6 da análise de 2026-10-06).
        """
        return self.exportacao._exportar_documento_revisado(documento)

    def exportar_livro_action(self):
        """Lê o PDF e escreve um EPUB ou DOCX.

        Delegado a `ui.exportacao.Exportacao` (item 6 da análise de 2026-10-06).
        """
        return self.exportacao.exportar_livro_action()

    def exportar_pgn(self):
        """Grava a notação reconhecida como `.pgn`.

        Delegado a `ui.exportacao.Exportacao` (item 6 da análise de 2026-10-06).
        """
        return self.exportacao.exportar_pgn()


    #: Devolvido por `_perguntar_teto` quando o usuário desiste. **Não pode ser
    #: `None`**: aqui `None` já quer dizer "sem teto", que é a resposta oposta
    #: de "deixa para lá" — uma manda gravar tudo, a outra manda não rodar.
    CANCELADO = object()


    #: Costura de teste, como a do `DIALOGO_DIAGRAMA`.
    DIALOGO_DO_DIAGRAMA = DialogoDoDiagrama
    #: A caixa única de exportação (2026-09-18); os testes põem um dublê que
    #: devolve um `OpcoesDeExportacao` pronto.
    DIALOGO_DE_EXPORTACAO = DialogoDeExportacao
    #: O disjuntor da ação «OCR (Tesseract)» (PD-01): boxes seguidos sem
    #: resposta no prazo até dar o executável por preso. O do livro é por
    #: página (`livro.PAGINAS_SEM_RESPOSTA_ATE_DESISTIR`), e o número é o mesmo.
    BOXES_SEM_RESPOSTA_ATE_DESISTIR = 2

    def _configuracoes(self):
        """O `Settings` da sessão, aberto na primeira vez que se pede."""
        if self._configuracoes_ is None:
            self._configuracoes_ = Settings()
        return self._configuracoes_


    #: O estado da janela que volta na próxima vez (item 9 da revisão de
    #: 2026-09-18): a geometria, se estava maximizada, e os filtros da lista.
    #: A pasta do último documento tem chave própria, a mesma da caixa de
    #: exportação (`CHAVE_DO_DIRETORIO_DE_ENTRADA`); a origem e a busca não
    #: voltam — a origem depende da página, e a busca é do momento.
    CHAVE_DA_JANELA = "janela"
    FILTROS_LEMBRADOS = ("so_pendentes", "so_vazios", "so_fora_dicionario")


    # --- treino e modelo: o corpo está em ui/treino.py; aqui só os delegados ---
    def preparar_dataset_correcoes_action(self):
        """Materializa somente eventos editoriais confirmados para o treino.

        Delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.preparar_dataset_correcoes_action()

    def criar_recortes_action(self):
        """Lê o PDF e grava os recortes de caractere separados por classe — delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.criar_recortes_action()

    def promover_revisao_action(self):
        """Leva para a base de treino o que sobreviveu à revisão — delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.promover_revisao_action()

    def learn_from_current_page(self):
        """Delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.learn_from_current_page()

    def verificar_base_treino(self):
        """Diagnóstico completo da base, inclusive lendo cada PNG — delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.verificar_base_treino()

    @staticmethod
    def _corrigiveis(problemas):
        """Os problemas que a correção automática sabe resolver — delegado a `ui.treino.Treino` (PD-22)."""
        return Treino._corrigiveis(problemas)

    def corrigir_base_treino(self, checar_pngs=True, depois=None):
        """Sanea a base sozinho: renomeia, mescla, quarentena — delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.corrigir_base_treino(checar_pngs, depois)

    def train_neural_network(self):
        """Delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.train_neural_network()

    def train_line_ocr(self):
        """Treina o reconhecedor CRNN/CTC com as linhas corrigidas — delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.train_line_ocr()

    def validar_dataset_linhas(self):
        """Mostra problemas e cobertura da base de linhas antes do treino — delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.validar_dataset_linhas()

    @staticmethod
    def _mostrar_validacao_de_linhas(resumo):
        """Delegado a `ui.treino.Treino` (PD-22)."""
        return Treino._mostrar_validacao_de_linhas(resumo)

    def avaliar_modelo_linhas(self):
        """Executa CER/WER no manifesto e mostra o resultado por página — delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.avaliar_modelo_linhas()

    @staticmethod
    def _mostrar_avaliacao_de_linhas(resultado):
        """Delegado a `ui.treino.Treino` (PD-22)."""
        return Treino._mostrar_avaliacao_de_linhas(resultado)

    def abrir_revisao_dataset_linhas(self):
        """Delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.abrir_revisao_dataset_linhas()

    def abrir_relatorio_ocr_linhas(self):
        """Delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.abrir_relatorio_ocr_linhas()

    def _treinar_rede(self, epochs, ja_corrigiu=False):
        """A tarefa do treino, separada para poder ser refeita — delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino._treinar_rede(epochs, ja_corrigiu)

    def treinar_modelo_diagramas(self):
        """Refaz o modelo das peças dos diagramas com as amostras de hoje (F8.3).

        Delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.treinar_modelo_diagramas()

    def abrir_relatorio_treino(self):
        """Abre o relatório do último treino no aplicativo padrão do sistema.

        Delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.abrir_relatorio_treino()

    def run_general_neural_training(self):
        """Delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.run_general_neural_training()

    def import_character_images(self):
        """Delegado a `ui.treino.Treino` (PD-22)."""
        return self.treino.import_character_images()

    #: A caixa do fim de "Exportar livro" (ED-02); o teste põe um dublê no lugar.
    DIALOGO_DE_CONCLUSAO = DialogoDeConclusao


    # -------------------------------------------------------
    # OCR automático para todos os boxes
    # -------------------------------------------------------


    #: A fonte da leitura do EasyOCR que o k-NN não confirmou (PD-13) — ver
    #: `ui.confidence.FONTES_SEMPRE_REVISADAS`.
    FONTE_EASYOCR_DISCORDA = "easyocr_discorda"


    # As quatro ações abaixo conferem `_busy` **antes** de gerar os boxes, e
    # não só dentro do preenchimento. Gerar substitui a lista da página; com
    # uma tarefa em andamento, o usuário perdia os boxes e em seguida lia que
    # a ação "não pode começar agora" — e a tarefa em curso ainda aplicava o
    # resultado dela por cima da lista nova.
    #
    # E o preenchimento é a **continuação** da geração (`ao_concluir`), desde
    # que ela virou tarefa (item 9 da revisão de 2026-09-18): as duas rodam
    # fora da thread da interface, uma depois da outra.


    # -------------------------------------------------------
    # Léxico (F9) — triagem por palavra, independente da confiança
    # -------------------------------------------------------


    def suspeitas(self):
        """
        As palavras de prosa que o dicionário não conhece, nesta página.

        **É triagem, não correção** — contrato 2 da SPEC §5.8. Palavra fora do
        dicionário é sinalizada e nunca aproximada da mais parecida: `Nimzowitsch`
        não está em lista alguma, e trocá-la entregaria prosa limpa e falsa.

        O que isto acrescenta ao filtro "só pendentes" é um sinal **independente da
        confiança**: a F1.9 mediu que 1,000 é a confiança mediana de um erro, e
        esses o `precisa_revisao` não vê. Medido em 10 páginas com o OCR real, o
        sinal pega 53,8% dos erros dentro de palavra de prosa, ao preço de acender
        em 5,8% das palavras certas (ROADMAP F9.1, medida 3).
        """
        if not self.boxes:
            return []
        lex = self.lexico_da_sessao()
        if lex.vazio:
            return []
        # Posição entra na chave junto do caractere: mover um box muda onde a
        # `notacao` corta as palavras, e com chave só de texto a suspeita ficaria
        # velha depois de um arraste.
        chave = tuple((b.char, b.x1, b.y1) for b in self.boxes)
        if self._cache_suspeitas[0] != chave:
            self._cache_suspeitas = (chave,
                                     lexico.suspeitas_da_pagina(self.boxes, lex))
        return self._cache_suspeitas[1]

    def boxes_suspeitos(self):
        """Índices de box cobertos por alguma suspeita — o que a UI marca."""
        return {i for s in self.suspeitas() for i in s.indices}

    def boxes_visiveis(self):
        """
        Índices dos boxes que passam pelo filtro ativo.

        A busca por caractere trata o texto digitado como um *conjunto*: "e"
        acha os 'e', e "aeiou" acha qualquer vogal. É mais útil que substring
        num editor onde cada box tem um caractere só. Diferencia maiúscula de
        minúscula, porque o OCR também diferencia.
        """
        termo = self.var_busca.get().strip()
        so_pendentes = self.var_so_pendentes.get()
        so_vazios = self.var_so_vazios.get()
        so_fora = self.var_so_fora_dicionario.get()
        origem = self.var_origem.get()
        suspeitos = self.boxes_suspeitos() if so_fora else ()

        visiveis = []
        for i, b in enumerate(self.boxes):
            if so_vazios and b.char:
                continue
            if so_pendentes and not conf_ui.precisa_revisao(b):
                continue
            if so_fora and i not in suspeitos:
                continue
            if origem != self.ORIGEM_TODAS and (b.source or self.ORIGEM_VAZIA) != origem:
                continue
            # Cuidado: `"" in "a"` é verdadeiro em Python, então sem o teste de
            # b.char todo box vazio passaria por qualquer busca de caractere.
            if termo and (not b.char or b.char not in termo):
                continue
            visiveis.append(i)
        return visiveis

    def limpar_filtros(self):
        self.var_so_pendentes.set(False)
        self.var_so_vazios.set(False)
        self.var_so_fora_dicionario.set(False)
        self.var_origem.set(self.ORIGEM_TODAS)
        self.var_busca.set("")          # o trace já redesenha a lista

    def on_boxes_changed_view(self):
        """Só o filtro mudou: redesenha lista e canvas, sem tocar no documento."""
        self.update_sidebar()
        self.update_canvas()

    def _atualizar_origens(self):
        """Mantém o combo com as origens que existem na página."""
        presentes = sorted({b.source or self.ORIGEM_VAZIA for b in self.boxes})
        valores = [self.ORIGEM_TODAS] + presentes
        if list(self.combo_origem["values"]) != valores:
            self.combo_origem["values"] = valores
        if self.var_origem.get() not in valores:
            self.var_origem.set(self.ORIGEM_TODAS)

    #: A seta do "você está aqui" na lista. `►` (U+25BA) e não `▶` (U+25B6),
    #: que é o desenho óbvio e **não existe na Consolas** — medido: o Tk cairia
    #: numa fonte de reserva não monoespaçada e a coluna sairia do prumo.
    SETA_SELECAO = "►"

    def _linha_da_lista(self, i, suspeitos=()):
        """(texto, cor) de um box na lista lateral.

        Três colunas fixas antes do índice, e a ordem é a da pergunta que cada
        uma responde: onde estou (a seta), a palavra está no dicionário (F9), e
        só então o box. Largura fixa mantém o resto da linha alinhado com as
        vizinhas — sem isso a lista fica em zigue-zague ao rolar.

        **A seta não é enfeite do realce do Listbox: é o que sobra dele.** O
        `tk.Listbox` nasce com `exportselection` ligado, então o realce da linha
        some assim que outro widget toma a seleção do sistema — e é o que
        acontece a cada `char_entry.select_range`, isto é, a cada Tab e a cada
        Enter do fluxo de revisão. Quem estava digitando ficava sem saber qual
        caractere estava editando.

        O léxico entra como coluna, e não como cor: a cor já é a confiança, e
        são dois eixos diferentes.
        """
        b = self.boxes[i]
        disp_ch = b.char if b.char else "?"
        seta = self.SETA_SELECAO if i == self.selected_index else " "
        marca = "*" if i in suspeitos else " "
        return (f"{seta}{marca}{i:04d} {conf_ui.rotulo(b)} '{disp_ch}' ({b.x1},{b.y1})",
                # A mesma escala do canvas, para o olho não ter que traduzir.
                conf_ui.cor_do_box(b))

    def update_sidebar(self):
        """
        Redesenha a lista lateral — só o que mudou (F4.4).

        Antes era `delete(0,"end")` mais N `insert()` a **cada** chamada, e
        `select_box` chama isto a cada seleção: com 2.000 boxes, cada seta
        pressionada refazia 2.000 linhas e a digitação engasgava.

        O ponto é que navegar quase não muda o conteúdo da lista. Guardando o
        que foi desenhado dá para comparar e reescrever só o que ficou
        diferente: quando o conteúdo muda de verdade (um caractere digitado, um
        filtro), são as linhas mudadas; quando o *tamanho* muda (box criado,
        excluído, filtro que corta), aí sim vale refazer tudo, que é raro e
        simples.

        **Andar de box custa duas linhas, e não zero como na F4.4 original.** É
        o preço da seta de seleção (`_linha_da_lista`): ela mora no texto da
        linha, então trocar a seleção reescreve a que perdeu a seta e a que
        ganhou. Duas linhas por tecla, não duas mil — o defeito que a F4.4
        existe para não deixar voltar continua fechado.
        """
        self._atualizar_origens()
        self._visiveis = self.boxes_visiveis()

        suspeitos = self.boxes_suspeitos()
        linhas = [self._linha_da_lista(i, suspeitos) for i in self._visiveis]
        anterior = getattr(self, "_linhas_desenhadas", None)

        if anterior is None or len(anterior) != len(linhas):
            self.listbox.delete(0, "end")
            for linha, (texto, cor) in enumerate(linhas):
                self.listbox.insert("end", texto)
                self.listbox.itemconfig(linha, foreground=cor)
        else:
            for linha, (novo, velho) in enumerate(zip(linhas, anterior)):
                if novo == velho:
                    continue
                # `delete` + `insert` na mesma posição: o Listbox do Tk não tem
                # como trocar o texto de uma linha no lugar.
                self.listbox.delete(linha)
                self.listbox.insert(linha, novo[0])
                self.listbox.itemconfig(linha, foreground=novo[1])

        self._linhas_desenhadas = linhas

        linha = self.linha_do_box(self.selected_index)
        if linha is not None:
            # A seleção do Listbox não sobrevive a um delete/insert da própria
            # linha, e no caminho rápido ela nem foi tocada — limpar antes deixa
            # os dois casos com o mesmo resultado.
            self.listbox.selection_clear(0, "end")
            self.listbox.select_set(linha)
            self.listbox.see(linha)

        self._atualizar_contadores()

    def linha_do_box(self, indice):
        """Linha da lista que mostra o box de índice `indice` (None se filtrado)."""
        try:
            return self._visiveis.index(indice)
        except ValueError:
            return None

    def _atualizar_contadores(self):
        """Quantos boxes ainda pedem revisão. É o que diz se a página acabou."""
        if not self.boxes:
            self.lbl_revisao.config(text="")
            self.lbl_filtro.config(text="")
            return
        total = len(self.boxes)
        mostrando = len(self._visiveis)
        texto = ("mostrando todos os %d" % total) if mostrando == total \
            else "mostrando %d de %d" % (mostrando, total)
        # Quantas palavras, não quantos boxes: o léxico decide por palavra, e
        # dizer "31 caracteres fora do dicionário" contaria as letras de dez
        # palavras e não bateria com nada que o revisor vê.
        n_suspeitas = len(self.suspeitas())
        if n_suspeitas:
            texto += "  ·  %d fora do dicionário" % n_suspeitas
        self.lbl_filtro.config(text=texto)

        pendentes = sum(1 for b in self.boxes if conf_ui.precisa_revisao(b))
        if pendentes:
            self.lbl_revisao.config(
                text=f"{pendentes} de {total} a revisar", fg=conf_ui.COR_BAIXA)
        else:
            self.lbl_revisao.config(text=f"{total} boxes, nada pendente",
                                    fg=conf_ui.COR_ALTA)

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
            # F4.3: rolar o mínimo, não re-enquadrar. Com zoom_to_box aqui,
            # navegar com as setas fazia a imagem saltar a cada tecla.
            self.canvas.garantir_visivel(index)

        self.update_sidebar()
        self.update_canvas()

    def on_sidebar_select(self, event):
        sel = self.listbox.curselection()
        if not sel:
            return
        linha = sel[0]
        if 0 <= linha < len(self._visiveis):
            # A linha da lista não é o índice do box quando há filtro ativo.
            self.select_box(self._visiveis[linha])

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

        b = self.boxes[self.selected_index]
        anterior = b.char
        b.char = ch
        # O usuário é autoridade: corrigir um box tem que tirá-lo do vermelho,
        # senão a cor nunca converge e a revisão não tem fim visível.
        b.confidence = 1.0
        b.source = "manual" if ch else ""
        if anterior != ch:
            self._ultima_correcao = (self.selected_index, b, anterior, ch)
        self._commit_change()
        self.update_sidebar()
        self.update_canvas()

    def _avancar_apos_edicao(self, anterior, linha_antes=None):
        """
        Vai para o próximo box após editar `anterior`.

        Com "só pendentes" ativo, corrigir o box o tira da lista: ela encolhe e
        a mesma posição já é o próximo pendente. Sem esse cuidado, o cursor
        pularia um item a cada correção.
        """
        if not self.boxes or not self._visiveis:
            return

        linha = self.linha_do_box(anterior)
        if linha is not None:
            proxima = linha + 1
        else:
            proxima = linha_antes if linha_antes is not None else 0

        proxima = max(0, min(len(self._visiveis) - 1, proxima))
        self.select_box(self._visiveis[proxima])

    def apply_char_and_next(self):
        anterior = self.selected_index
        linha_antes = self.linha_do_box(anterior)

        self.apply_char()          # aplica e refiltra a lista
        self._avancar_apos_edicao(anterior, linha_antes)

        if not self.modo_digitacao:
            # No modo digitação o foco fica no canvas, senão o Entry passaria a
            # consumir as teclas e o modo pararia de funcionar.
            self.char_entry.focus_set()
            self.char_entry.select_range(0, "end")

    # -------------------------------------------------------
    # F3.6 — aplicar a correção a todos os semelhantes
    # -------------------------------------------------------

    #: Origem própria para o que veio de um lote. Fica fora da fila de revisão
    #: (confiança 1,0) mas continua achável pelo filtro de origem — o critério
    #: erra ~1 em 145, e apagar o rastro de quais boxes vieram de lote tornaria
    #: esse resto impossível de reencontrar.
    ORIGEM_LOTE = "lote"

    #: Costura de teste: o diálogo é trocável por um dublê.
    DIALOGO_SEMELHANTES = DialogoSemelhantes


    # -------------------------------------------------------
    # Key handlers
    # -------------------------------------------------------

    def _mover_selecao(self, passo):
        """Anda pela lista *visível* — com filtro ativo, pular os escondidos
        seria confuso: o usuário navega o que está vendo."""
        vis = self._visiveis
        if not vis:
            return
        linha = self.linha_do_box(self.selected_index)
        if linha is None:
            linha = 0
        else:
            linha = max(0, min(len(vis) - 1, linha + passo))
        self.select_box(vis[linha])

    def proximo_pendente(self, direcao=1):
        """
        Pula para o próximo box que pede revisão, dentro do filtro ativo.

        É o que transforma "reler 2.000 caracteres" em "conferir os 80 duvidosos":
        os verdes são pulados. Dá a volta ao chegar na ponta.

        **Com o filtro do léxico ligado, quem manda é o léxico**, e sem isto o
        `F3` ficaria inútil justamente onde a fase serve para alguma coisa: uma
        palavra fora do dicionário costuma ser lida com confiança alta — 1,000 é
        a mediana de um erro, pela F1.9 —, então `precisa_revisao` não vê nenhuma
        e a lista filtrada responderia "nada pendente" com a tela cheia de
        sublinhados roxos.
        """
        if self.var_so_fora_dicionario.get():
            pendentes = list(self._visiveis)
        else:
            pendentes = [i for i in self._visiveis
                         if conf_ui.precisa_revisao(self.boxes[i])]
        if not pendentes:
            self.status.set("Nada pendente na lista atual.")
            return "break"

        atual = self.selected_index
        if direcao > 0:
            alvo = next((i for i in pendentes if i > atual), pendentes[0])
        else:
            anteriores = [i for i in pendentes if i < atual]
            alvo = anteriores[-1] if anteriores else pendentes[-1]

        self.select_box(alvo)
        self.status.set(f"Pendente {pendentes.index(alvo) + 1} de {len(pendentes)}.")
        if not self.modo_digitacao:
            self.char_entry.focus_set()
            self.char_entry.select_range(0, "end")
        return "break"

    def _on_key_up(self, event):
        if not self.boxes:
            return "break"
        self._mover_selecao(-1)
        return "break"

    def _on_key_down(self, event):
        if not self.boxes:
            return "break"
        self._mover_selecao(1)
        return "break"

    def _on_key_delete(self, event):
        # A mesma guarda do Backspace: Delete no campo de busca ou no de
        # página apaga um caractere, não o box selecionado.
        if self._foco_em_campo_de_texto():
            return None
        self.delete_selected_box()

    def _on_key_ir_para_pagina(self, event):
        """Ctrl+G põe o cursor no campo de página, pronto para digitar."""
        if str(self.entry_pagina.cget("state")) == "disabled":
            return "break"
        self.entry_pagina.focus_set()
        self.entry_pagina.select_range(0, "end")
        return "break"

    def _on_key_tab(self, passo):
        """
        Tab anda um box, Shift+Tab volta, e o foco fica pronto para digitar.

        Devolve "break" sempre: sem isso o Tk faria a travessia de foco padrão
        **além** de mover o box, e o foco sairia do editor no meio da revisão.
        Perder a travessia não custa nada aqui — a janela é um editor de canvas
        e lista, não um formulário, e o único campo que precisava de atalho
        próprio (a busca) já tem o Ctrl+F.

        Levar o foco ao campo do caractere é o que fecha o ciclo "Tab, digita,
        Tab": sem isso o Tab a partir da busca deixaria o usuário navegando
        boxes com as teclas caindo no filtro. No modo digitação o foco não se
        mexe — lá quem recebe as teclas é a janela, e roubá-lo desligaria o
        modo na prática.
        """
        if not self.boxes:
            return "break"
        self._mover_selecao(passo)
        if not self.modo_digitacao:
            self.char_entry.focus_set()
            self.char_entry.select_range(0, "end")
        return "break"

    # Widgets que consomem a tecla: enquanto um deles tem o foco, atalho de
    # janela não pode disparar. `ttk.Entry` e `ttk.Spinbox` herdam de `tk.Entry`
    # e já entram por ele; `tk.Text`, `tk.Spinbox` e `ttk.Combobox`, não — e era
    # essa a falha do guard antigo do Ctrl+D, que testava só `tk.Entry`.
    CAMPOS_DE_TEXTO = (tk.Entry, tk.Text, tk.Spinbox, ttk.Entry, ttk.Combobox)

    def _foco_em_campo_de_texto(self) -> bool:
        """Verdadeiro se quem tem o foco é um campo onde se digita."""
        try:
            foco = self.parent.focus_get()
        except KeyError:
            # focus_get() levanta quando o foco está num widget de outra
            # aplicação ou já destruído. Nesse caso não há campo nosso em foco.
            return False
        return isinstance(foco, self.CAMPOS_DE_TEXTO)

    def _on_key_split_safe(self, event):
        if self._foco_em_campo_de_texto():
            return
        self.split_selected_box()

    def _on_key_split_no_campo(self, event):
        """
        Ctrl+D com o foco no campo do caractere — o único que também divide.

        O guard acima cala o atalho em todo campo de texto, e para a busca e o
        número da página isso está certo: eles não têm box nenhum por trás. O
        campo do caractere é o oposto — ele *é* o box selecionado, e é onde o
        revisor está com as mãos quando descobre que a caixa tem duas letras.

        **Ligado no widget, e não na janela, porque a ordem das bindings do Tk
        importa aqui.** A tecla passa pelo widget, depois pela classe, depois
        pelo toplevel: se a janela tratasse o caso, a binding de classe do
        `Entry` já teria rodado antes — e nela `Control-d` apaga o caractere à
        direita do cursor. O `"break"` daqui é o que impede as duas.

        O foco fica onde estava, com a primeira metade selecionada e o campo
        vazio: dividir 'ba' e digitar 'b', Enter, 'a', Enter é o ciclo inteiro
        sem tirar a mão do teclado. Quem o põe ali é `split_selected_box`, desde
        a F4.9 — as outras rotas do comando precisavam do mesmo.
        """
        self.split_selected_box()
        return "break"

    def _on_key_zoom(self, event):
        """F4 enquadra o box selecionado (F4.3).

        Tecla de função, e não `Z` como o roadmap sugeria: com o modo digitação
        ligado (F3.1), uma letra solta é capturada por `_on_tecla_digitacao` e
        vira o caractere do box. F2 e F3 já são atalhos da janela pelo mesmo
        motivo.
        """
        if self._foco_em_campo_de_texto():
            return
        if self.selected_index >= 0:
            self.canvas.zoom_to_box(self.selected_index)
        return "break"

    def _on_key_undo(self, event):
        self._perform_undo()
        return "break"

    def _on_key_redo(self, event):
        self._perform_redo()
        return "break"


    # -------------------------------------------------------
    # Neural Network
    # -------------------------------------------------------


    #: O que a correção automática faz, na ordem em que faz — o texto que o
    #: usuário lê antes de autorizar mexer nas pastas dele.
    EXPLICACAO_DA_CORRECAO = (
        "A correção automática:\n"
        "  - renomeia a pasta de formato antigo para o nome atual;\n"
        "  - mescla-a na pasta certa quando as duas já existem (nenhuma "
        "amostra é perdida);\n"
        "  - remove pasta vazia, que ocupa índice de classe à toa;\n"
        "  - move para '_quarentena' o que não dá para identificar — PNG "
        "ilegível e pasta cujo nome não é caractere nenhum.\n"
        "\n"
        "Nenhuma amostra é apagada: o que sai do caminho do treino fica em "
        "'_quarentena', dentro da própria base."
    )


    #: Costura de teste, como a da F3.6.
    DIALOGO_DIAGRAMA = DialogoDiagrama


