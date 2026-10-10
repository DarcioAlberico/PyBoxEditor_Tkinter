"""
O fluxo de documento da janela principal, num lugar só (PD-22).

Até aqui os 39 métodos — abrir imagem e PDF, carregar a página, navegar, o título e a
sessão, o rascunho e a recuperação, salvar e carregar o `.box`, o estado da janela,
o editor de livro e desfazer/refazer — moravam em `ui/main_window.py`: 771 das 5.105
linhas da janela. Aqui eles são o `Documento`, que a janela cria no `__init__`
(`self.documento = Documento(self)`) e para o qual delega, método a método, com o
mesmo nome: `janela.open_pdf()` continua existindo, para o menu, os atalhos e os
testes; o corpo é o daqui.

A janela continua dona do estado (`session`, `boxes`, `history`, `current_pdf_page`,
`image`), dos serviços (`pdf_service`, o controlador do documento e o da navegação)
e de `_run_task`: os métodos falam com ela por `self.janela`, e quem troca um método
da janela num teste continua sendo ouvido, porque as chamadas internas passam pelo
delegado. É o padrão de `ui/exportacao.py` (item 6 da análise de 2026-10-06).
"""
from __future__ import annotations

import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image
from core import formato_box
from core.services.pdf_service import DPI_PADRAO
from core.services.document_service import DocumentSession
from ui.dialogo_de_exportacao import CHAVE_DO_DIRETORIO_DE_ENTRADA


class Documento:
    """O fluxo de documento da janela principal; `janela` é a `MainWindow`."""

    def __init__(self, janela):
        self.janela = janela

    def _autosave_threshold_reached(self):
        self.janela._mudancas_desde_autosave += 1
        if self.janela._mudancas_desde_autosave >= self.janela.AUTOSAVE_A_CADA:
            self.janela._gravar_rascunho()

    def _commit_change(self):
        """
        Registra uma mutação dos boxes: snapshot para undo + marca a página
        como não salva.

        Ponto único de entrada — todo lugar que altera self.janela.boxes chama isto
        em vez de history.snapshot() direto.
        """
        self.janela.document_controller.commit()
        self.janela._update_title()

    def _sync_session(self):
        """Reassocia self.janela.boxes à página atual sem marcá-la como suja.
        Usado após undo/redo, que reatribuem a lista."""
        self.janela.document_controller.store_current()

    def _update_title(self):
        base = "PyBoxEditor"
        if self.janela.session is not None:
            nome = os.path.basename(self.janela.session.path)
            if self.janela.session.is_pdf:
                base += f" — {nome} [Pág {self.janela.current_pdf_page + 1}/{self.janela.session.num_pages}]"
            else:
                base += f" — {nome}"
            if self.janela.session.is_dirty():
                base += " *"
        self.janela.parent.title(base)

    def _confirm_discard(self) -> bool:
        """True se pode prosseguir (nada pendente, ou o usuário aceitou perder)."""
        if self.janela.session is None or not self.janela.session.is_dirty():
            return True

        paginas = self.janela.session.dirty_pages()
        if self.janela.session.is_pdf:
            onde = f"{len(paginas)} página(s): " + ", ".join(str(p + 1) for p in paginas[:8])
            if len(paginas) > 8:
                onde += f" e mais {len(paginas) - 8}"
        else:
            onde = "esta imagem"

        descartar = messagebox.askyesno(
            "Trabalho não salvo",
            f"Há alterações não salvas em {onde}.\n"
            f"Total na sessão: {self.janela.session.total_boxes()} box(es).\n\n"
            "Use 'Salvar todas as páginas' para gravar tudo.\n\n"
            "Descartar as alterações e continuar?",
            icon="warning",
        )
        if descartar:
            # O usuário aceitou perder: manter o rascunho o ressuscitaria na
            # próxima abertura, o que seria pior que a perda escolhida.
            self.janela._descartar_rascunho()
        return descartar

    def _gravar_rascunho(self):
        """
        Agenda a gravação do rascunho e zera o contador.

        O snapshot é montado aqui (thread da UI) porque precisa de uma visão
        consistente dos boxes; o encode em JSON e a escrita vão para a thread
        do gravador. Medido em 40 mil boxes: 23 ms aqui contra 31 ms lá.
        """
        if self.janela.session is None:
            return
        self.janela._mudancas_desde_autosave = 0
        if self.janela.document_controller.autosave():
            erro = self.janela._gravador.ultimo_erro
            if erro is not None:
                self.janela.status.set(f"Falha ao gravar rascunho: {erro}")

    def _descartar_rascunho(self):
        """Some com o rascunho: ou o trabalho foi salvo de verdade, ou o
        usuário escolheu descartá-lo."""
        if self.janela.session is not None:
            self.janela.session.remover_autosave()
        self.janela._mudancas_desde_autosave = 0

    def _tentar_recuperar(self):
        """
        Oferece o rascunho de um travamento anterior, se houver.

        Devolve True se algo foi recuperado.
        """
        if self.janela.session is None:
            return False
        payload = DocumentSession.ler_autosave(self.janela.session.path)
        if payload is None:
            return False

        paginas = len(payload.get("paginas", {}))
        boxes = sum(len(v) for v in payload.get("paginas", {}).values())
        quando = payload.get("gravado_em", "?").replace("T", " ")

        if not messagebox.askyesno(
            "Recuperar trabalho",
            f"Há um rascunho não salvo deste documento, de {quando}:\n"
            f"{paginas} página(s), {boxes} box(es).\n\n"
            "Isso costuma sobrar de um fechamento inesperado.\n\n"
            "Recuperar esse trabalho?\n"
            "(Se recusar, o rascunho será descartado.)",
            icon="warning",
        ):
            self.janela.session.remover_autosave()
            return False

        recuperadas = self.janela.session.aplicar_payload(payload)
        self.janela.status.set(f"Rascunho recuperado: {recuperadas} página(s).")
        return True

    def _on_close(self):
        if getattr(self.janela, "_sondando", None):
            # A sondagem da caixa (PD-02) volta em segundos; fechar no meio
            # destruiria a janela embaixo do laço que a espera.
            self.janela.status.set(f"Aguarde: {self.janela._sondando.lower()}.")
            return
        if self.janela.task.is_running():
            if not messagebox.askyesno(
                "Operação em andamento",
                "Há uma operação rodando. Cancelar e fechar mesmo assim?",
                icon="warning",
            ):
                return
            self.janela.task.cancel()
        if self.janela._confirm_discard():
            self.janela.gravar_estado_da_janela()
            self.janela.task.shutdown()
            self.janela.parent.destroy()

    def salvar_rascunho_agora(self):
        """Força a gravação do rascunho (menu / Ctrl+B)."""
        if self.janela.session is None or not self.janela.session.pages_with_boxes():
            self.janela.status.set("Nada para gravar no rascunho.")
            return "break"
        self.janela._gravar_rascunho()
        self.janela.status.set(f"Rascunho gravado em {os.path.basename(self.janela.session.sidecar())}.")
        return "break"

    def open_image(self, path=None):
        if self.janela._busy("Abrir imagem"):
            return
        if not self.janela._confirm_discard():
            return

        if path is None:
            path = self.janela._perguntar_entrada(
                "Abrir imagem", [("Imagens", "*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff")])
        if not path:
            return

        try:
            img = Image.open(path)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir a imagem:\n{e}")
            return

        self.janela.pdf_service.close()

        self.janela.session = self.janela.document_controller.open(path, num_pages=1, is_pdf=False)
        self.janela.navigation.reset(1)
        self.janela._esquecer_lexico()
        self.janela.current_pdf_page = 0
        self.janela._mudancas_desde_autosave = 0
        recuperou = self.janela._tentar_recuperar()

        self.janela.image = img.convert("L")
        self.janela.image_path = path
        self.janela.boxes = self.janela.session.boxes_for(0)
        self.janela.selected_index = -1
        # O documento novo abre inteiro na janela, e não em 100% no canto.
        self.janela.canvas.ajustar_a_janela(redesenhar=False)

        self.janela._update_nav_controls()

        # Zerar o histórico ao trocar de documento: sem isso, um undo logo após
        # abrir traria de volta os boxes da imagem anterior.
        self.janela.history.reset()

        box_path = os.path.splitext(path)[0] + ".box"
        if recuperou:
            # O rascunho é mais recente que o .box em disco; carregá-lo por
            # cima desfaria justamente o que se acabou de recuperar.
            self.janela.history.snapshot(self.janela.boxes, self.janela.selected_index)
            self.janela.update_sidebar()
            self.janela.update_canvas()
        elif os.path.exists(box_path):
            self.janela._load_box_from_path(box_path, marcar_sujo=False)
        else:
            self.janela.history.snapshot(self.janela.boxes, self.janela.selected_index)
            self.janela.update_sidebar()
            self.janela.update_canvas()

        self.janela._update_title()

    def abrir_documento(self, path=None):
        """
        Ctrl+O: um diálogo só, para PDF e imagem, decidido pela extensão.

        O menu tem duas entradas separadas porque o usuário às vezes quer
        filtrar a lista, mas um atalho que exigisse escolher o tipo antes de
        ver o arquivo seria pior que não ter atalho.
        """
        if path is None:
            imagens = " ".join("*" + e for e in self.janela.EXTENSOES_DE_IMAGEM)
            path = self.janela._perguntar_entrada(
                "Abrir documento", [("PDF e imagens", "*.pdf " + imagens),
                                    ("Arquivos PDF", "*.pdf"),
                                    ("Imagens", imagens),
                                    ("Todos", "*.*")])
        if not path:
            return

        if os.path.splitext(path)[1].lower() == ".pdf":
            self.janela.open_pdf(path)
        else:
            self.janela.open_image(path)

    def open_pdf(self, path=None):
        # pdf_service é lido pela thread de trabalho; trocar o PDF por baixo
        # dela corromperia o resultado.
        if self.janela._busy("Abrir PDF"):
            return
        if not self.janela._confirm_discard():
            return

        if path is None:
            path = self.janela._perguntar_entrada("Abrir PDF", [("Arquivos PDF", "*.pdf")])
        if not path:
            return

        num_pages, err = self.janela.pdf_service.load_pdf(path)
        if err:
            messagebox.showerror("Erro PDF", err)
            return

        # A sessão nova precisa existir antes de carregar a página, e a página
        # atual não deve ser arquivada na sessão nova (ela é do documento antigo).
        self.janela.session = self.janela.document_controller.open(
            path, num_pages=num_pages, is_pdf=True, dpi=DPI_PADRAO
        )
        self.janela.navigation.reset(num_pages)
        self.janela._esquecer_lexico()
        self.janela.boxes = []
        self.janela.current_pdf_page = 0
        self.janela._mudancas_desde_autosave = 0
        self.janela._tentar_recuperar()
        # O documento novo abre com a página inteira na janela (o `aplicar` de
        # `_load_pdf_page` ajusta enquanto o modo valer).
        self.janela.canvas.ajustado = True
        self.janela._load_pdf_page(0, arquivar_atual=False)

    def _load_pdf_page(self, page_index, arquivar_atual=True, ao_concluir=None,
                       ao_falhar=None, ao_cancelar=None):
        """
        Troca de página. A renderização vai para a thread de trabalho: medido em
        ~950 ms num PDF sintético simples, e um scan de livro a 300 dpi é bem
        pior. Como virar a página é a operação mais frequente do app, fazer isso
        na thread da UI travava a janela a cada clique.
        """
        if self.janela.task.is_running():
            # Antes isto devolvia em silêncio, contando com os botões
            # desativados para explicar. Não explicam: pelo teclado (PgUp/PgDn)
            # ou pelo campo "ir para", o usuário aperta e **nada acontece** —
            # e a leitura natural é que virar a página está quebrado.
            self.janela.status.set("Aguarde a operação em andamento para virar a página.")
            return

        if self.janela.session is not None:
            try:
                self.janela.navigation.target(page_index)
            except IndexError:
                return

        # Arquivar o trabalho da página que sai é rápido e acontece já, antes de
        # qualquer coisa poder dar errado.
        if arquivar_atual and self.janela.session is not None:
            self.janela.session.store(self.janela.current_pdf_page, self.janela.boxes)

        self.janela.btn_prev_page.config(state="disabled")
        self.janela.btn_next_page.config(state="disabled")

        def trabalho(h):
            h.log(f"Renderizando página {page_index + 1}...")
            img = self.janela.pdf_service.load_page(page_index)
            if img is None:
                raise ValueError("Nenhuma imagem retornada para a página.")
            return img

        def aplicar(page_img):
            self.janela.image = page_img
            self.janela.image_path = (f"{os.path.basename(self.janela.pdf_service.pdf_path)} "
                               f"[Pág {page_index + 1}]")
            self.janela.current_pdf_page = page_index
            # Com a página ajustada à janela, a seguinte também chega ajustada;
            # quem deu zoom continua no mesmo zoom e no mesmo lugar.
            if self.janela.canvas.ajustado:
                self.janela.canvas.ajustar_a_janela(redesenhar=False)

            # Restaura o que já havia sido feito nesta página (lista vazia se
            # for a primeira visita).
            self.janela.boxes = (self.janela.session.boxes_for(page_index)
                          if self.janela.session is not None else [])
            self.janela.selected_index = -1
            self.janela.navigation.go_to(page_index)

            # O histórico é por página: um Ctrl+Z logo após virar a página não
            # deve despejar os boxes da página anterior sobre a atual.
            self.janela.history.reset()
            self.janela.history.snapshot(self.janela.boxes, self.janela.selected_index)

            self.janela.update_sidebar()
            self.janela.update_canvas()
            self.janela._update_nav_controls()
            self.janela._update_title()
            if ao_concluir:
                ao_concluir()

        self.janela._run_task(f"Página {page_index + 1}", trabalho, aplicar,
                       indeterminado=True, ao_falhar=ao_falhar,
                       ao_cancelar=ao_cancelar)

    def prev_page(self):
        # Não mexer em current_pdf_page aqui: _load_pdf_page usa o valor atual
        # para arquivar o trabalho da página que está saindo.
        if self.janela.navigation.can_previous:
            self.janela._load_pdf_page(self.janela.current_pdf_page - 1)

    def next_page(self):
        if self.janela.navigation.can_next:
            self.janela._load_pdf_page(self.janela.current_pdf_page + 1)

    def ir_para_pagina(self, numero=None):
        """
        Vai direto para a página `numero` (1 é a primeira).

        Sem argumento, lê o campo da barra de navegação. O número é o que o
        usuário vê no rótulo — 1 a N —, não o índice interno; trocar um pelo
        outro aqui levaria a página errada sem erro nenhum.
        """
        if not self.janela.pdf_service.is_loaded():
            messagebox.showinfo("Ir para a página", "Nenhum PDF aberto.")
            return

        if numero is None:
            texto = self.janela.entry_pagina.get().strip()
            if not texto:
                return
            try:
                numero = int(texto)
            except ValueError:
                messagebox.showinfo(
                    "Ir para a página",
                    f"{texto!r} não é um número de página.")
                return

        total = self.janela.pdf_service.num_pages
        if not 1 <= numero <= total:
            messagebox.showinfo(
                "Ir para a página",
                f"Este PDF tem {total} página(s); {numero} está fora.")
            return

        if numero - 1 == self.janela.current_pdf_page:
            self.janela.status.set(f"Já está na página {numero}.")
            return

        self.janela._load_pdf_page(numero - 1)

    def _update_nav_controls(self):
        if not self.janela.pdf_service.is_loaded():
            if self.janela.session is not None and self.janela.session.has_boxes(0):
                self.janela.lbl_page_info.config(text=f"{len(self.janela.boxes)} boxes")
            else:
                self.janela.lbl_page_info.config(text="Página: -/-")
            self.janela.btn_prev_page.config(state="disabled")
            self.janela.btn_next_page.config(state="disabled")
            self.janela.entry_pagina.config(state="disabled")
            self.janela.btn_ir.config(state="disabled")
            return

        self.janela.lbl_page_info.config(
            text=f"Página: {self.janela.current_pdf_page + 1}/{self.janela.pdf_service.num_pages}")

        detalhe = []
        if self.janela.session is not None:
            com_boxes = self.janela.session.pages_with_boxes()
            if com_boxes:
                detalhe.append(f"{len(com_boxes)} pág. com boxes, "
                               f"{self.janela.session.total_boxes()} no total")
            sujas = self.janela.session.dirty_pages()
            if sujas:
                detalhe.append(f"{len(sujas)} não salva(s)")
        self.janela.lbl_sessao.config(text="   |   ".join(detalhe))
        self.janela.btn_prev_page.config(
            state="normal" if self.janela.current_pdf_page > 0 else "disabled"
        )
        self.janela.btn_next_page.config(
            state="normal" if self.janela.current_pdf_page < self.janela.pdf_service.num_pages - 1 else "disabled"
        )
        self.janela.entry_pagina.config(state="normal")
        self.janela.btn_ir.config(state="normal")

    def _perguntar_entrada(self, titulo, tipos):
        """
        O arquivo de entrada, começando na pasta da última vez.

        Vale para abrir (Ctrl+O, Abrir imagem, Abrir PDF) e para exportar: é
        uma pasta só, a do último documento de trabalho — antes só a
        exportação lembrava, e o Ctrl+O abria sempre na pasta corrente.
        """
        try:
            pasta = self.janela._configuracoes().get(CHAVE_DO_DIRETORIO_DE_ENTRADA)
        except Exception:  # noqa: BLE001 — preferência que não abre não barra a ação
            pasta = None
        escolhido = filedialog.askopenfilename(
            title=titulo, filetypes=tipos,
            initialdir=pasta if pasta and os.path.isdir(pasta) else None)
        if escolhido:
            try:
                configuracoes = self.janela._configuracoes()
                configuracoes.set(CHAVE_DO_DIRETORIO_DE_ENTRADA,
                                  os.path.dirname(os.path.abspath(escolhido)))
                configuracoes.save()
            except Exception:  # noqa: BLE001
                pass
        return escolhido

    def _maximizada(self) -> bool:
        try:
            if self.janela.parent.tk.call("tk", "windowingsystem") == "win32":
                return self.janela.parent.state() == "zoomed"
            return bool(int(self.janela.parent.attributes("-zoomed")))
        except (tk.TclError, ValueError):
            return False

    def _estado_da_janela(self, anterior=None) -> dict:
        """O que `gravar_estado_da_janela` guarda. Maximizada, a geometria que
        vale é a de antes — a que o botão de restaurar deve devolver."""
        estado = {"filtros": {nome: bool(getattr(self.janela, f"var_{nome}").get())
                              for nome in self.janela.FILTROS_LEMBRADOS}}
        estado["maximizada"] = self.janela._maximizada()
        if estado["maximizada"]:
            if (anterior or {}).get("geometria"):
                estado["geometria"] = anterior["geometria"]
        else:
            estado["geometria"] = self.janela.parent.geometry()
        return estado

    def gravar_estado_da_janela(self):
        """Guarda a geometria e os filtros no `settings.json` (ao fechar)."""
        try:
            configuracoes = self.janela._configuracoes()
            anterior = configuracoes.get(self.janela.CHAVE_DA_JANELA)
            configuracoes.set(self.janela.CHAVE_DA_JANELA, self.janela._estado_da_janela(
                anterior if isinstance(anterior, dict) else None))
            configuracoes.save()
        except Exception:  # noqa: BLE001 — preferência que não grava não barra o fechamento
            pass

    def _geometria_que_cabe(self, geometria) -> bool:
        """A geometria gravada ainda cabe na tela de agora? Numa tela menor —
        o notebook depois do monitor grande —, ela abriria a janela com a
        borda fora do alcance, que é o defeito que `appy._geometria_que_cabe`
        existe para evitar."""
        achado = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", str(geometria or ""))
        if not achado:
            return False
        largura, altura, x, y = (int(valor) for valor in achado.groups())
        tela_l, tela_a = self.janela.parent.winfo_screenwidth(), self.janela.parent.winfo_screenheight()
        return (largura <= tela_l and altura <= tela_a
                and 0 <= x <= tela_l - 100 and 0 <= y <= tela_a - 100)

    def restaurar_estado_da_janela(self):
        """Devolve a geometria e os filtros da última vez (`appy.main`, ao abrir).

        Fora do `__init__` de propósito: a janela dos testes é retraída, e
        maximizá-la pelo `settings.json` de quem roda a suíte a poria na tela.
        """
        try:
            estado = self.janela._configuracoes().get(self.janela.CHAVE_DA_JANELA)
        except Exception:  # noqa: BLE001
            return
        if not isinstance(estado, dict):
            return
        filtros = estado.get("filtros") or {}
        for nome in self.janela.FILTROS_LEMBRADOS:
            getattr(self.janela, f"var_{nome}").set(bool(filtros.get(nome, False)))
        if self.janela._geometria_que_cabe(estado.get("geometria")):
            self.janela.parent.geometry(estado["geometria"])
        if estado.get("maximizada"):
            try:
                if self.janela.parent.tk.call("tk", "windowingsystem") == "win32":
                    self.janela.parent.state("zoomed")
                else:
                    self.janela.parent.attributes("-zoomed", True)
            except tk.TclError:
                pass

    def _abridor_do_editor(self, documento):
        """O `abrir_no_editor` da caixa de conclusão: o arquivo exportado **e** o documento da sessão."""
        return lambda caminho, d=documento: self.janela.abrir_editor_de_livro(caminho, documento=d)

    def _editor_sobre(self, documento) -> bool:
        """O editor de livros está aberto sobre este documento (a ponte é dele; a fila não exporta)."""
        editor = self.janela.editor
        try:
            if editor is None or not editor.winfo_exists():
                return False
        except Exception:      # noqa: BLE001 — janela já destruída
            return False
        projeto = getattr(editor, "projeto", None)
        aberto = getattr(projeto, "documento_editorial", None)
        return aberto is not None and documento is not None \
            and aberto.document_id == getattr(documento, "document_id", None)

    def abrir_editor_de_livro(self, caminho=None, documento=None):
        """
        Arquivo → Editor de livro... (ED-02): a janela de edição, separada e sem
        bloquear esta (SPEC_EDITOR DEC-09). Uma só por vez — chamada de novo, traz
        a que existe para a frente e, com `caminho`, abre o livro nela. Com
        `documento` (ED-11, §7.2), o livro é montado do `EditorialDocument` da
        sessão — com a proveniência de cada bloco e a ponte ligada — e `caminho` é
        o arquivo que a sessão exportou (um EPUB vira o caminho do projeto). O import
        fica aqui dentro para a janela principal não carregar o editor (nem o
        editor carregar o OCR) antes de alguém pedir.
        """
        from ui.editor.janela import JanelaDoEditor

        if self.janela.editor is not None and self.janela.editor.winfo_exists():
            self.janela.editor.deiconify()
            self.janela.editor.lift()
        else:
            self.janela.editor = JanelaDoEditor(self.janela.parent, task_controller=None)
        if documento is not None:
            self.janela.editor.executar("abrir_documento_editorial", documento, caminho or "")
        elif caminho:
            self.janela.editor.executar("abrir", caminho)
        return self.janela.editor

    def _destino_sugerido(self, ext, padrao):
        """
        Pasta e nome que o diálogo de salvar propõe para a página atual.

        Sai de `page_stem`, o mesmo lugar de onde 'Salvar todas as páginas' tira
        o destino: com um PDF aberto, o Ctrl+S propõe exatamente o arquivo que o
        salvamento em lote gravaria — `livro_pg011.box`, na pasta do PDF.

        O `.box` antes tirava o nome de `image_path`, que numa sessão de PDF é o
        rótulo da janela (`livro.pdf [Pág 11]`). O `splitext` disso devolve
        'livro' — a página se perdia, e **toda** página do livro propunha o mesmo
        nome: salvar a segunda oferecia sobrescrever a primeira, e o `.png` do
        par ia junto. O PGN já numerava, mas com outra grafia (`_pg11`), o que
        afastava o PGN do par `.box`/`.png` da mesma página na lista da pasta.
        """
        if self.janela.session is not None:
            base = self.janela.session.page_stem(self.janela.current_pdf_page)
        elif self.janela.image_path:
            base = os.path.splitext(self.janela.image_path)[0]
        else:
            base = padrao
        return os.path.dirname(base), os.path.basename(base) + ext

    def save_box_file(self):
        if self.janela.image is None or not self.janela.boxes:
            messagebox.showinfo("Aviso", "Nada para salvar.")
            return

        pasta, nome = self.janela._destino_sugerido(".box", "boxes")

        path = filedialog.asksaveasfilename(
            defaultextension=".box",
            initialdir=pasta or None,
            initialfile=nome,
            filetypes=[("Arquivos BOX", "*.box"), ("Todos", "*.*")]
        )
        if not path:
            return

        self.janela._salvar_box_em_tarefa(path)

    def _salvar_box_em_tarefa(self, path):
        """
        O Ctrl+S grava numa tarefa (item 9 da revisão de 2026-09-18).

        O par leva o PNG da página, e codificar uma página a 300 dpi congelava
        a janela a cada salvamento. Grava o que havia **no momento do Ctrl+S**
        — cópias da imagem e dos boxes —, e só dá a página por salva se ela não
        mudou enquanto gravava: a edição feita no meio não está no arquivo.
        """
        imagem = self.janela.image.copy()
        boxes = [b.copy() for b in self.janela.boxes]
        pagina = self.janela.current_pdf_page

        def trabalho(h):
            h.log(f"Gravando {os.path.basename(path)}...")
            erro = self.janela._write_box_pair(path, imagem, boxes)
            if erro:
                raise OSError(erro)
            return path

        def falhou(exc):
            messagebox.showerror("Erro", f"Não foi possível salvar os arquivos:\n{exc}")
            return True

        def concluir(_path):
            inteira = self.janela.current_pdf_page == pagina and self.janela.boxes == boxes
            self.janela._depois_de_salvar(path, marcar_salva=inteira)

        self.janela._run_task("Salvar .box", trabalho, concluir, indeterminado=True,
                       ao_falhar=falhou)

    def load_box_file(self):
        if self.janela.image is None:
            messagebox.showinfo("Aviso", "Carregue uma imagem primeiro.")
            return

        path = filedialog.askopenfilename(
            filetypes=[("Arquivos BOX", "*.box"), ("Todos", "*.*")]
        )
        if not path:
            return

        self.janela._load_box_from_path(path)

    def save_all_pages(self):
        if self.janela._busy("O salvamento"):
            return

        """
        Grava um par .box/.png por página que tenha boxes.

        Contrapartida necessária da persistência entre páginas: sem isto o
        usuário acumularia trabalho em várias páginas sem nenhuma forma de
        gravá-lo, o que seria pior que o comportamento antigo.
        """
        if self.janela.session is None:
            messagebox.showinfo("Aviso", "Nenhum documento aberto.")
            return

        paginas = self.janela.session.pages_with_boxes()
        if not paginas:
            messagebox.showinfo("Aviso", "Nenhuma página tem boxes para salvar.")
            return

        # A imagem da página atual é compartilhada com o canvas: copiar antes
        # de entregar à thread evita que worker e redraw leiam o mesmo objeto.
        img_atual = self.janela.image.copy() if self.janela.image is not None else None
        pagina_atual = self.janela.current_pdf_page
        sessao = self.janela.session

        def trabalho(h):
            salvos, falhas = [], []
            for n, page in enumerate(paginas):
                h.raise_if_cancelled()
                h.progress(n + 1, len(paginas), f"página {page + 1}")

                if page == pagina_atual:
                    img = img_atual
                elif sessao.is_pdf:
                    img = self.janela.pdf_service.load_page(page)
                else:
                    img = img_atual

                if img is None:
                    falhas.append(f"pág {page + 1}: não foi possível renderizar")
                    continue

                destino = sessao.page_stem(page) + ".box"
                erro = self.janela._write_box_pair(destino, img, sessao.boxes_for(page))
                if erro:
                    falhas.append(f"pág {page + 1}: {erro}")
                else:
                    salvos.append((page, destino))
            return salvos, falhas

        def concluir(resultado):
            salvos, falhas = resultado
            for page, _ in salvos:
                sessao.mark_saved(page)
            if not sessao.is_dirty():
                self.janela._descartar_rascunho()
            self.janela._update_nav_controls()
            self.janela._update_title()
            # Aqui e não no `trabalho`: mexer no léxico e no cache de suspeitas
            # é estado da UI, e a thread não pode tocá-los. Só as páginas que
            # **gravaram** — quem falhou não terminou.
            palavras = self.janela.aprender_palavras_das_paginas(
                [sessao.boxes_for(page) for page, _ in salvos])
            self.janela._relatar_salvamento([d for _, d in salvos], falhas, palavras)
            if palavras:
                self.janela.update_sidebar()
                self.janela.update_canvas()

        self.janela._run_task("Salvar todas as páginas", trabalho, concluir)

    def _relatar_salvamento(self, salvos, falhas, palavras=()):
        resumo = f"{len(salvos)} página(s) salva(s) em:\n{os.path.dirname(self.janela.session.path)}"
        resumo += self.janela._frase_do_dicionario(palavras)
        if falhas:
            messagebox.showerror("Salvo com erros", resumo + "\n\nFalhas:\n" + "\n".join(falhas))
        else:
            messagebox.showinfo("Sucesso", resumo)

    def _write_box_pair(self, path, image, boxes):
        """
        Escreve o par .box/.png. Devolve None em caso de sucesso, ou a mensagem
        de erro. Sem diálogos — quem chama decide como reportar.
        """
        try:
            formato_box.escrever(path, boxes, image.height)
            image.save(os.path.splitext(path)[0] + ".png", format="PNG")
            return None
        except Exception as e:
            return str(e)

    def _save_box_to_path(self, path):
        erro = self.janela._write_box_pair(path, self.janela.image, self.janela.boxes)
        if erro:
            messagebox.showerror("Erro", f"Não foi possível salvar os arquivos:\n{erro}")
            return
        self.janela._depois_de_salvar(path)

    def _depois_de_salvar(self, path, marcar_salva=True):
        """O que a janela faz com o par gravado: a página sai da lista das não
        salvas (se não mudou no meio — ver `_salvar_box_em_tarefa`), o
        dicionário aprende as palavras dela, e o aviso diz o que foi gravado."""
        if self.janela.session is not None:
            if marcar_salva:
                self.janela.session.mark_saved(self.janela.current_pdf_page)
            if not self.janela.session.is_dirty():
                self.janela._descartar_rascunho()
            self.janela._update_nav_controls()
        self.janela._update_title()

        # Depois de gravar, e não antes: se a escrita falhar, o usuário não
        # terminou com a página coisa nenhuma, e o dicionário não deve ter
        # aprendido nada dela.
        palavras = self.janela.aprender_palavras_da_pagina()

        img_path = os.path.splitext(path)[0] + ".png"
        aviso = ""
        if not marcar_salva:
            aviso = ("\n\nA página mudou enquanto era gravada: o arquivo tem o que "
                     "havia no Ctrl+S, e o que mudou depois ainda não está nele.")
        elif self.janela.session is not None and self.janela.session.is_dirty():
            pend = len(self.janela.session.dirty_pages())
            aviso = (f"\n\nAtenção: ainda há {pend} outra(s) página(s) não salva(s)."
                     "\nUse 'Salvar todas as páginas' para gravar tudo.")

        messagebox.showinfo(
            "Sucesso",
            f"Salvo com sucesso:\n- {os.path.basename(path)}\n"
            f"- {os.path.basename(img_path)}{aviso}"
            f"{self.janela._frase_do_dicionario(palavras)}"
        )
        if palavras:
            # A palavra que entrou deixa de ser suspeita: a lista e o canvas
            # mostram isso agora, não na próxima vez que algo os redesenhar.
            self.janela.update_sidebar()
            self.janela.update_canvas()

    def _load_box_from_path(self, path, marcar_sujo=True):
        if self.janela.image is None:
            return

        try:
            boxes = formato_box.ler(path, self.janela.image.height)
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível carregar o .box:\n{e}")
            return

        boxes.sort(key=lambda b: (b.y1, b.x1))
        self.janela.boxes = boxes
        self.janela.selected_index = 0 if boxes else -1

        if marcar_sujo:
            self.janela._commit_change()
        else:
            # Sidecar carregado junto com a imagem: o conteúdo já está em disco,
            # no lugar canônico. Marcar como sujo aqui faria a janela abrir com
            # '*' sem o usuário ter mexido em nada.
            self.janela.history.snapshot(self.janela.boxes, self.janela.selected_index)
            self.janela._sync_session()
            self.janela._update_title()
        self.janela.update_sidebar()
        self.janela.update_canvas()

    def _perform_undo(self):
        if not hasattr(self.janela, 'document_controller'):
            return
        if self.janela.document_controller.undo():
            self.janela.boxes = self.janela.document_controller.boxes
            self.janela.selected_index = self.janela.document_controller.selected_index
            self.janela.update_sidebar()
            self.janela.update_canvas()

    def _perform_redo(self):
        if not hasattr(self.janela, 'document_controller'):
            return
        if self.janela.document_controller.redo():
            self.janela.boxes = self.janela.document_controller.boxes
            self.janela.selected_index = self.janela.document_controller.selected_index
            self.janela.update_sidebar()
            self.janela.update_canvas()
