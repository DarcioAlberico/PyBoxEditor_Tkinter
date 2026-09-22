"""Revisão de OCR por linha, com coleta de dados para treino de texto."""

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import numpy as np
from PIL import Image, ImageTk

from core import nags
from core.chess_symbols import (CHESS_ANNOTATION_CHARACTERS,
                                VANTAGEM_LIGEIRA_BRANCAS,
                                VANTAGEM_LIGEIRA_PRETAS)
from core.leitura_de_linha import linhas_da_pagina
from core import vertical
from config.paths import caminhos_modelo_linha
from core.linha_trainer import modelo_utilizavel
from ui import fontes


def _simbolos_da_paleta() -> tuple[str, ...]:
    """Retorna todos os rótulos digitáveis da tabela de NAGs e do catálogo.

    Alguns NAGs são compostos (``!!``, ``⩲`` e ``RR``) e devem ser inseridos
    como uma unidade; os caracteres do catálogo entram individualmente para
    permitir correção de uma posição dentro da linha.
    """
    resultado: list[str] = []
    vistos: set[str] = set()

    def adicionar(valor: str) -> None:
        valor = str(valor)
        if valor and valor not in vistos:
            vistos.add(valor)
            resultado.append(valor)

    for nag in nags.TABELA:
        adicionar(nag.simbolo)
    # Mantém o par no início mesmo que a tabela de NAGs seja reorganizada.
    for simbolo in (VANTAGEM_LIGEIRA_BRANCAS, VANTAGEM_LIGEIRA_PRETAS):
        adicionar(simbolo)
    for simbolo in "♔♕♖♗♘♙♚♛♜♝♞♟" + "⌖△▽" + "≡⇄":
        adicionar(simbolo)
    for simbolo in sorted(CHESS_ANNOTATION_CHARACTERS):
        adicionar(simbolo)
    # Caracteres de texto que já eram úteis no editor de linhas.
    for simbolo in "éçãõáóúàâêôü+-=()[]/.":
        adicionar(simbolo)
    return tuple(resultado)


class DialogoRotulagem(tk.Toplevel):
    """Pré-OCR e revisão de uma frase por vez."""

    def __init__(self, parent):
        super().__init__(parent.parent)
        self.app = parent
        self.title("Rotulagem de linhas — treino OCR")
        self.geometry("1020x700")
        self.minsize(820, 560)
        self.transient(parent.parent)
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self._linhas = linhas_da_pagina(self.app.boxes)
        self._pos = 0
        self._pagina_rodando = False
        self._geracao_rodando = False
        self._ocr = {}
        self._confirmadas = set()
        self._descartadas = set()
        self._salvas = set()
        self._linha_tk = None
        self._ocr_rodando = False
        self._texto_original = ""
        self._montar()
        self._mostrar()
        self.grab_set()
        self.focus_force()
        self.after_idle(self._garantir_boxes)

    def _montar(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        topo = tk.Frame(self, padx=12, pady=8)
        topo.grid(row=0, column=0, sticky="ew")
        topo.columnconfigure(1, weight=1)
        self.lbl_progresso = tk.Label(topo, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_progresso.grid(row=0, column=0, sticky="w")
        tk.Label(topo, text="Revise a frase inteira; confirme ou corrija.",
                 fg="gray30").grid(row=0, column=1, sticky="e")
        pagina = tk.Frame(topo)
        pagina.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.btn_pagina_anterior = tk.Button(
            pagina, text="‹ Página", command=lambda: self._trocar_pagina(-1))
        self.btn_pagina_anterior.pack(side="left")
        self.lbl_pagina = tk.Label(pagina, text="", width=18)
        self.lbl_pagina.pack(side="left", padx=6)
        self.btn_pagina_proxima = tk.Button(
            pagina, text="Página ›", command=lambda: self._trocar_pagina(1))
        self.btn_pagina_proxima.pack(side="left")
        tk.Label(pagina, text="Ir para:").pack(side="left", padx=(14, 2))
        self.entry_pagina = tk.Entry(pagina, width=6, justify="center")
        self.entry_pagina.pack(side="left")
        self.entry_pagina.bind("<Return>", lambda _e: self._ir_para_pagina())
        tk.Button(pagina, text="Ir", command=self._ir_para_pagina).pack(
            side="left", padx=2)

        centro = tk.Frame(self, padx=12)
        centro.grid(row=1, column=0, sticky="nsew")
        centro.columnconfigure(0, weight=1)
        centro.rowconfigure(1, weight=1)
        self.line_preview = tk.Label(centro, bg="#202124", relief="sunken", bd=1)
        self.line_preview.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.lbl_linha = tk.Label(centro, text="", anchor="w", fg="gray30")
        self.lbl_linha.grid(row=0, column=0, sticky="sw", padx=5, pady=(0, 6))
        self.preview = tk.Label(centro, bg="#202124", relief="sunken", bd=1)
        self.preview.grid(row=1, column=0, sticky="nsew", padx=(0, 12))

        painel = tk.Frame(centro, width=300)
        painel.grid(row=0, column=1, rowspan=2, sticky="ns")
        ocr = tk.LabelFrame(painel, text="Pré-OCR da página", padx=5, pady=5)
        ocr.pack(fill="x", pady=(0, 10))
        linha_ocr = tk.Frame(ocr)
        linha_ocr.pack(fill="x")
        tk.Label(linha_ocr, text="Motor:").pack(side="left")
        self._modelo_path, self._meta_path = caminhos_modelo_linha()
        # O modelo treinado só é o padrão se passa no portão de produção — o
        # mesmo de `linha_trainer.modelo_utilizavel` que a exportação e o
        # botão de preenchimento consultam. Existir no disco não basta: o de
        # 2026-09-17 existia, e errava 96% dos caracteres na validação.
        modelo_pronto, motivo_modelo = modelo_utilizavel(self._meta_path,
                                                          self._modelo_path)
        self.var_motor = tk.StringVar(
            value="Modelo treinado" if modelo_pronto else "EasyOCR")
        ttk.Combobox(linha_ocr, textvariable=self.var_motor,
                     values=("Modelo treinado", "EasyOCR", "PaddleOCR", "Tesseract"),
                     state="readonly", width=15).pack(
                         side="left", padx=4)
        if not modelo_pronto and (self._modelo_path.exists() and self._meta_path.exists()):
            tk.Label(ocr, text=f"Modelo treinado fora do padrão: {motivo_modelo}.",
                     fg="gray30", wraplength=380, justify="left").pack(fill="x", pady=(4, 0))
        tk.Label(linha_ocr, text="idioma:").pack(side="left")
        self.var_idioma = tk.StringVar(value="en + pt")
        ttk.Combobox(linha_ocr, textvariable=self.var_idioma,
                     values=("en", "pt", "en + pt"), state="readonly", width=8).pack(
                         side="left")
        self.btn_ocr = tk.Button(ocr, text="Executar", command=self._pre_ocr)
        self.btn_ocr.pack(fill="x", pady=(5, 0))

        tk.Label(painel, text="Transcrição corrigida:").pack(anchor="w")
        self.texto = tk.Text(painel, height=5, width=32, wrap="word",
                             font=("Segoe UI", 12))
        self.texto.pack(fill="x", pady=(3, 8))
        self.texto.bind("<Control-Return>", lambda e: self._confirmar())
        self.lbl_atual = tk.Label(painel, text="", justify="left", anchor="w")
        self.lbl_atual.pack(fill="x", pady=(0, 8))
        self.lbl_status = tk.Label(painel, text="", fg="#1769aa", wraplength=280,
                                   justify="left")
        self.lbl_status.pack(fill="x", pady=(0, 8))
        tk.Button(painel, text="Aceitar / salvar linha  (Ctrl+Enter)",
                  command=self._confirmar).pack(fill="x", pady=2)
        tk.Button(painel, text="Descartar linha (sujeira do PDF)",
                  command=self._descartar).pack(fill="x", pady=2)
        tk.Button(painel, text="← Anterior", command=self._anterior).pack(
            side="left", fill="x", expand=True, pady=2)
        tk.Button(painel, text="Próxima →", command=self._proxima).pack(
            side="left", fill="x", expand=True, pady=2)

        paleta = tk.LabelFrame(painel, text="Glifos e símbolos", padx=3, pady=3)
        paleta.pack(fill="x", pady=(12, 0))
        paleta.columnconfigure(0, weight=1)
        area = tk.Frame(paleta)
        area.grid(row=0, column=0, sticky="ew")
        area.columnconfigure(0, weight=1)
        canvas = tk.Canvas(area, height=176, width=260, highlightthickness=0)
        barra = ttk.Scrollbar(area, orient="vertical", command=canvas.yview)
        barra_x = ttk.Scrollbar(area, orient="horizontal", command=canvas.xview)
        conteudo = tk.Frame(canvas)
        janela = canvas.create_window((0, 0), window=conteudo, anchor="nw")
        canvas.configure(xscrollcommand=barra_x.set, yscrollcommand=barra.set)
        canvas.grid(row=0, column=0, sticky="ew")
        barra.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")
        conteudo.bind("<Configure>",
                      lambda _evento: canvas.configure(scrollregion=canvas.bbox("all")))

        def ajustar_largura(evento):
            # O frame precisa conservar a largura solicitada pela grade; se
            # for forçado sempre à largura visível, os botões da direita ficam
            # fora do scrollregion e parecem desaparecer.
            largura = max(evento.width, conteudo.winfo_reqwidth())
            canvas.itemconfigure(janela, width=largura)
            canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", ajustar_largura)
        canvas.bind("<MouseWheel>",
                    lambda evento: canvas.yview_scroll(-int(evento.delta / 120), "units"))
        canvas.bind("<Shift-MouseWheel>",
                    lambda evento: canvas.xview_scroll(-int(evento.delta / 120), "units"))
        base_fonte = ("Segoe UI Symbol", 10, "normal")
        for pos, simbolo in enumerate(_simbolos_da_paleta()):
            tk.Button(conteudo, text=simbolo,
                      width=max(2, min(5, len(simbolo) + 1)),
                      font=fontes.fonte_do_rotulo(simbolo, base_fonte),
                      command=lambda s=simbolo: self._inserir(s)).grid(
                          row=pos // 10, column=pos % 10, padx=1, pady=1, sticky="ew")

        rodape = tk.Frame(self, padx=12, pady=8)
        rodape.grid(row=2, column=0, sticky="ew")
        tk.Label(rodape, text="Confirmações viram dataset de treino de linhas.",
                 fg="gray35").pack(side="left")
        tk.Button(rodape, text="Salvar dataset", command=self._salvar_dataset).pack(
            side="right", padx=4)
        tk.Button(rodape, text="Fechar", command=self._fechar).pack(side="right")
        self.bind("<Escape>", lambda e: self._fechar())
        self.bind("<Control-s>", lambda e: self._salvar_dataset())
        self.bind("<Control-S>", lambda e: self._salvar_dataset())
        # As setas navegam entre linhas — **fora do campo de texto**. Com o
        # foco no campo (que `_mostrar` põe lá), a seta move o cursor e só;
        # sem esta guarda a binding do Toplevel rodava depois da do `Text` e
        # trocava de linha no meio da digitação, jogando fora o que estava
        # escrito. Para navegar de dentro do campo: Ctrl+Seta.
        self.bind("<Right>", lambda e: None if self._foco_no_texto() else self._proxima())
        self.bind("<Left>", lambda e: None if self._foco_no_texto() else self._anterior())
        self.bind("<Control-Right>", lambda e: self._proxima())
        self.bind("<Control-Left>", lambda e: self._anterior())
        self.bind("<Control-Prior>", lambda e: self._trocar_pagina(-1))
        self.bind("<Control-Next>", lambda e: self._trocar_pagina(1))

    def _idiomas(self):
        valor = self.var_idioma.get()
        return ("en", "pt") if valor == "en + pt" else (valor,)

    def _caixa_linha(self, linha):
        imagem = self.app.image
        return (max(0, min(b.x1 for b in linha) - 10),
                max(0, min(b.y1 for b in linha) - 10),
                min(imagem.width, max(b.x2 for b in linha) + 10),
                min(imagem.height, max(b.y2 for b in linha) + 10))

    def _mostrar(self):
        if not self._linhas:
            self.lbl_progresso.config(text="Nenhuma linha encontrada")
            self.texto.delete("1.0", "end")
            self.lbl_atual.config(text="Boxes ainda não gerados para esta página.")
            self._atualizar_navegacao()
            return
        linha = self._linhas[self._pos]
        recorte = self.app.image.crop(self._caixa_linha(linha)).convert("RGB")
        escala = min(900 / max(1, recorte.width), 160 / max(1, recorte.height))
        faixa = recorte.resize((max(1, int(recorte.width * escala)),
                                max(1, int(recorte.height * escala))),
                               Image.Resampling.NEAREST)
        self._linha_tk = ImageTk.PhotoImage(faixa)
        self.line_preview.config(image=self._linha_tk)
        self.preview.config(image=self._linha_tk)
        texto = self._ocr.get(self._pos, "")
        self.texto.delete("1.0", "end")
        texto_exibido = texto or "".join(b.char for b in linha)
        self.texto.insert("1.0", texto_exibido)
        self._texto_original = texto_exibido
        self.lbl_progresso.config(text=f"Linha {self._pos + 1} de {len(self._linhas)}")
        self.lbl_linha.config(text="Linha inteira — corrija a transcrição abaixo")
        self.lbl_atual.config(text=f"{len(linha)} glifo(s) | confiança: "
                                f"{self._ocr.get((self._pos, 'conf'), '—')}")
        if self._pos in self._confirmadas:
            self.lbl_status.config(text="Linha já confirmada nesta sessão.", fg="#267326")
        elif self._pos in self._descartadas:
            self.lbl_status.config(text="Linha descartada nesta sessão.", fg="#9b2226")
        self.texto.focus_set()

    def _total_paginas(self):
        if self.app.pdf_service.is_loaded():
            return self.app.pdf_service.num_pages
        return 1

    def _atualizar_navegacao(self):
        total = self._total_paginas()
        atual = self.app.current_pdf_page + 1
        self.lbl_pagina.config(text=f"Página {atual}/{total}")
        estado = "disabled" if self._pagina_rodando or self._geracao_rodando else "normal"
        self.btn_pagina_anterior.config(
            state=(estado if atual > 1 else "disabled"))
        self.btn_pagina_proxima.config(
            state=(estado if atual < total else "disabled"))
        self.entry_pagina.config(state=estado)

    def _garantir_boxes(self):
        if self._linhas:
            self._atualizar_navegacao()
            return
        self._gerar_boxes()

    def _gerar_boxes(self):
        if self._geracao_rodando or self.app.image is None:
            return
        self._geracao_rodando = True
        self.btn_ocr.config(state="disabled")
        self.lbl_status.config(text="Gerando boxes automaticamente...", fg="#1769aa")
        imagem = self.app.image.copy()

        def trabalho(h):
            h.log("Gerando boxes da página...")
            return self.app.box_service.generate_boxes_opencv(
                imagem, arbitro=self.app._arbitro_de_corte())

        def concluir(boxes):
            self.app.boxes = boxes
            self.app._commit_change()
            self.app.update_canvas()
            self.app.update_sidebar()
            self._linhas = linhas_da_pagina(self.app.boxes)
            self._pos = 0
            self._geracao_rodando = False
            self.btn_ocr.config(state="normal")
            self.lbl_status.config(
                text="Boxes gerados. Iniciando o pré-OCR automaticamente...")
            self._mostrar()
            # O callback ainda está encerrando a tarefa do gerador; agendar o
            # OCR para o próximo ciclo evita iniciar duas tarefas simultâneas.
            self.after_idle(self._pre_ocr)

        def falhar(_erro):
            self._geracao_rodando = False
            self.btn_ocr.config(state="normal")
            self.lbl_status.config(
                text="Não foi possível gerar os boxes desta página.",
                fg="#9b2226")
            self._atualizar_navegacao()
            return False

        self.app._run_task("Gerando boxes para rotulagem", trabalho, concluir,
                           ao_falhar=falhar, ao_cancelar=falhar)

    def _trocar_pagina(self, deslocamento):
        if self._pagina_rodando or self._geracao_rodando or self.app.task.is_running():
            return
        if not self._resolver_pendente():
            return
        # Confirmadas e ainda não gravadas não podem desaparecer ao trocar de
        # página. O manifesto é atualizado aqui, sem exigir um clique extra.
        self._salvar_dataset()
        destino = self.app.current_pdf_page + deslocamento
        if not 0 <= destino < self._total_paginas():
            return
        self._pagina_rodando = True
        self._limpar_pagina()
        self.app._load_pdf_page(
            destino, ao_concluir=self._pagina_carregada,
            ao_falhar=lambda _erro: self._pagina_com_erro(),
            ao_cancelar=self._pagina_com_erro)

    def _ir_para_pagina(self):
        try:
            destino = int(self.entry_pagina.get()) - 1
        except ValueError:
            self.lbl_status.config(text="Informe um número de página válido.", fg="#9b2226")
            return
        if 0 <= destino < self._total_paginas():
            if destino != self.app.current_pdf_page:
                self._trocar_pagina(destino - self.app.current_pdf_page)
        else:
            self.lbl_status.config(text="Página fora do intervalo do documento.", fg="#9b2226")

    def _resolver_pendente(self):
        if (not self._linhas or self._pos in self._confirmadas
                or self._pos in self._descartadas):
            return True
        atual = self.texto.get("1.0", "end-1c").strip()
        if not atual or atual == self._texto_original.strip():
            return True
        resposta = messagebox.askyesnocancel(
            "Correção pendente",
            "A linha atual foi alterada.\n\n"
            "Sim: confirmar e salvar a correção na sessão.\n"
            "Não: trocar de página e perder esta alteração.\n"
            "Cancelar: continuar nesta linha.",
            parent=self)
        if resposta is None:
            return False
        if resposta:
            self._confirmar()
        return True

    def _limpar_pagina(self):
        self._linhas = []
        self._pos = 0
        self._ocr = {}
        self._confirmadas = set()
        self._descartadas = set()
        self._salvas = set()
        self._mostrar()

    def _pagina_carregada(self):
        self._pagina_rodando = False
        self._linhas = linhas_da_pagina(self.app.boxes)
        self._pos = 0
        self._ocr = {}
        self._confirmadas = set()
        self._descartadas = set()
        self._salvas = set()
        self._mostrar()
        if not self._linhas:
            self._gerar_boxes()

    def _pagina_com_erro(self):
        self._pagina_rodando = False
        self.lbl_status.config(text="Não foi possível carregar esta página.",
                               fg="#9b2226")
        self._atualizar_navegacao()

    def _pre_ocr(self):
        if self._ocr_rodando or not self._linhas:
            return
        if self.app.task.is_running():
            messagebox.showinfo("Pré-OCR", "Já existe uma operação em andamento.", parent=self)
            return
        self._ocr_rodando = True
        self.btn_ocr.config(state="disabled", text="Lendo linhas...")
        recortes = [np.array(self.app.image.crop(self._caixa_linha(linha)))
                    for linha in self._linhas]
        motor, idiomas = self.var_motor.get(), self._idiomas()

        def trabalho(h):
            saida = []
            for pos, recorte in enumerate(recortes):
                if motor == "Tesseract":
                    texto, conf = self.app.ocr_service.tesseract_linha_conf(
                        recorte, idioma=idiomas[0])
                elif motor == "Modelo treinado":
                    texto, conf = self.app.ocr_service.linha_treinada_conf(
                        recorte, str(self._modelo_path), str(self._meta_path))
                    # Um CRNN/CTC mal treinado pode colapsar uma frase inteira
                    # em um único token, ainda que reporte confiança alta. A
                    # quantidade de boxes é uma verificação geométrica
                    # independente e permite recuperar a linha pelo modelo de
                    # glifos já treinado, que é muito mais confiável nesse caso.
                    linha = self._linhas[pos]
                    minimo = max(2, len(linha) // 2)
                    if len(texto.replace(" ", "")) < minimo:
                        recuperado = self._ler_por_glifos(linha)
                        if recuperado[0]:
                            texto, conf = recuperado
                elif motor == "PaddleOCR":
                    texto, conf = self.app.ocr_service.paddleocr_linha_conf(
                        recorte, language=idiomas[0])
                else:
                    texto, conf = self.app.ocr_service.easyocr_linha_conf(
                        recorte, languages=idiomas)
                saida.append((texto, conf))
                h.progress(pos + 1, len(recortes), f"linha {pos + 1}/{len(recortes)}")
            return saida

        def concluir(saida):
            for pos, (texto, conf) in enumerate(saida):
                self._ocr[pos] = texto
                self._ocr[(pos, "conf")] = f"{conf:.0%}"
            self._ocr_rodando = False
            self.btn_ocr.config(state="normal", text="Executar")
            self._mostrar()

        self.app._run_task("Pré-OCR das linhas", trabalho, concluir)

    def _ler_por_glifos(self, linha):
        """Reconstrói uma linha usando o reconhecedor neural por caractere.

        É um fallback deliberado para checkpoints de linha que colapsaram a
        saída CTC. Os recortes continuam sendo os boxes originais da página,
        portanto símbolos de xadrez não passam pelo alfabeto do EasyOCR.
        """
        try:
            if not self.app.learning_service.load_predictor():
                return "", 0.0
            imagem = np.asarray(self.app.image)
            chars, confiancas = [], []
            for box in linha:
                char, conf = self.app.learning_service.ler_texto(
                    vertical.recorte_de_pe(imagem, box), referencia=None,
                    idioma="en")
                chars.append(char or "")
                confiancas.append(float(conf))
            texto = self._inserir_espacos(linha, chars)
            return texto, sum(confiancas) / max(1, len(confiancas))
        except Exception:
            return "", 0.0

    @staticmethod
    def _inserir_espacos(linha, chars):
        """Insere espaços inferindo as separações pela geometria dos boxes."""
        if not chars:
            return ""
        lacunas = [max(0, linha[i + 1].x1 - linha[i].x2)
                   for i in range(len(linha) - 1)]
        positivas = sorted(valor for valor in lacunas if valor > 0)
        mediana = positivas[len(positivas) // 2] if positivas else 0
        limite = max(3, mediana * 1.8)
        sem_espaco_antes = set(".,;:!?)]}›")
        sem_espaco_depois = set("([{‹")
        resultado = []
        for indice, char in enumerate(chars):
            if indice and lacunas[indice - 1] > limite:
                anterior = chars[indice - 1]
                # O ponto do número do lance liga-se à peça: 27.♕d4.
                ponto_numero = anterior == "." and any(
                    c.isdigit() for c in chars[max(0, indice - 3):indice - 1])
                if (not ponto_numero and char not in sem_espaco_antes
                        and anterior not in sem_espaco_depois):
                    resultado.append(" ")
            resultado.append(char)
        return "".join(resultado)

    def _inserir(self, simbolo):
        self.texto.insert("insert", simbolo)
        self.texto.focus_set()

    def _confirmar(self):
        if not self._linhas:
            return
        texto = self.texto.get("1.0", "end-1c").strip()
        if not texto:
            messagebox.showinfo("Linha", "Digite uma transcrição antes de confirmar.", parent=self)
            return
        self._ocr[self._pos] = texto
        self._confirmadas.add(self._pos)
        self._descartadas.discard(self._pos)
        self.lbl_status.config(text="Linha confirmada. Salve o dataset ao terminar.")
        self._proxima()

    def _descartar(self):
        if self._linhas:
            self._descartadas.add(self._pos)
            self._confirmadas.discard(self._pos)
            self.lbl_status.config(text="Linha marcada como sujeira do PDF.")
            self._proxima()

    def _foco_no_texto(self) -> bool:
        try:
            return self.focus_get() is self.texto
        except KeyError:
            return False

    def _guardar_edicao(self) -> None:
        """O que está digitado fica com a linha ao sair dela, confirmado ou
        não: `_mostrar` reescreve o campo a partir de `self._ocr`, e sem isto
        a edição não confirmada sumia a cada troca de linha."""
        if not self._linhas:
            return
        atual = self.texto.get("1.0", "end-1c").strip()
        if atual and atual != self._texto_original.strip():
            self._ocr[self._pos] = atual

    def _proxima(self):
        if self._linhas and self._pos < len(self._linhas) - 1:
            self._guardar_edicao()
            self._pos += 1
            self._mostrar()

    def _anterior(self):
        if self._linhas and self._pos > 0:
            self._guardar_edicao()
            self._pos -= 1
            self._mostrar()

    def _salvar_dataset(self):
        indices = sorted(self._confirmadas - self._salvas)
        if not indices:
            self.lbl_status.config(text="Nenhuma linha confirmada nova para salvar.")
            return
        pasta = Path("training_data_linhas")
        imagens = pasta / "images"
        imagens.mkdir(parents=True, exist_ok=True)
        from core.linha_review import adicionar_ou_corrigir
        for pos in indices:
            nome = f"pagina_{self.app.current_pdf_page + 1:04d}_linha_{pos + 1:05d}.png"
            self.app.image.crop(self._caixa_linha(self._linhas[pos])).save(imagens / nome)
            texto = self._ocr.get(pos, "").replace("\n", " ").strip()
            adicionar_ou_corrigir(pasta, f"images/{nome}", texto)
        self._salvas.update(indices)
        self.lbl_status.config(text=f"{len(indices)} linha(s) salva(s) em training_data_linhas/.")

    def _fechar(self):
        pendentes = self._confirmadas - self._salvas
        if pendentes and messagebox.askyesno(
                "Dataset de treino", f"Há {len(pendentes)} linha(s) não salva(s).\n\n"
                "Salvar antes de fechar?", parent=self):
            self._salvar_dataset()
        self.grab_release()
        self.destroy()
