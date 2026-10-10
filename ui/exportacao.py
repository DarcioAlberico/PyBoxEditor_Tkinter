"""
O fluxo de exportar da janela principal, num lugar só (item 6 da análise de 2026-10-06).

Até aqui os oito métodos — exportar o livro (EPUB/DOCX), processar e escrever o documento
editorial, revisar a fila e regravar o documento revisado, o PDF pesquisável e o PGN —
moravam em `ui/main_window.py`, entre os de boxes, treino e navegação: 644 das 5.700
linhas da janela. Aqui eles são a `Exportacao`, que a janela cria no `__init__`
(`self.exportacao = Exportacao(self)`) e para a qual delega, método a método, com o mesmo
nome: `janela.exportar_livro_action()` continua existindo, para o menu, os atalhos e os
testes; o corpo é o daqui.

A janela continua dona do estado (`session`, `boxes`, `documento_editorial`,
`exportacao_editorial`), dos serviços (`ocr_service`, `learning_service`), das caixas
injetáveis (`DIALOGO_DE_EXPORTACAO`, `DIALOGO_DE_CONCLUSAO`, `DIALOGO_DIAGRAMA`) e de
`_run_task`, que leva o trabalho para fora da thread do Tk: por isso os métodos falam com
ela por `self.janela`, e quem troca um método da janela num teste (`win._escrever_documento_editorial = …`)
continua sendo ouvido, porque as chamadas internas passam pelo delegado. É o padrão do
editor de livros (`ui/editor/operacoes.py`, `conversoes.py`), e é o que os próximos fluxos
da janela — boxes e OCR, treino, navegação — devem seguir (PD-22).
"""
from __future__ import annotations

import collections
import os
from pathlib import Path
from tkinter import filedialog, messagebox

import numpy as np

from config.paths import caminhos_modelo_linha
from core import coleta, exportar, livro, pdf_nativo
from core.editorial_legacy import OpcoesDeLeitura, pipeline_de_producao
from core.editorial_pipeline import DocumentSource, ExportOptions, ProcessOptions
from core.linha_trainer import modelo_utilizavel
from ui.dialogo_de_exportacao import FORMATOS_DE_LIVRO, FORMATOS_EDITORIAIS


class Exportacao:
    """As ações de exportar da janela principal; `janela` é a `MainWindow`."""

    def __init__(self, janela):
        self.janela = janela

    def gerar_pdf_pesquisavel_action(self):
        """PDF pesquisável: mantém a página como está e só acrescenta o texto."""
        self.janela._acao_ocr_pdf(
            modo="searchable",
            titulo="PDF pesquisável",
            titulo_saida="Salvar PDF pesquisável como...",
        )

    def _preparar_exportacao(self, entrada, formatos, titulo):
        """
        Tudo que a caixa de exportação precisa saber antes de abrir, e a caixa.

        Devolve `(opcoes, idioma_detectado, motor_disponivel)`, com `opcoes`
        `None` quando o usuário cancelou. As sondagens — número de páginas,
        idioma pela camada de texto, Tesseract, portão do modelo de linha —
        acontecem aqui, antes, para a caixa mostrar o estado de cada coisa ao
        lado da escolha em vez de perguntar depois.
        """
        e_pdf = entrada.lower().endswith(".pdf")
        total = 1
        if e_pdf:
            import fitz
            try:
                documento = fitz.open(entrada)
                total = len(documento)
                documento.close()
            except Exception as erro:  # noqa: BLE001 — PDF que não abre
                messagebox.showerror(
                    titulo, f"Não foi possível ler o número de páginas do PDF:\n{erro}")
                return None, None, True

        def sondar():
            # Fora da thread da interface (PD-02): só lê o arquivo e o
            # executável, e nenhuma das três abre caixa.
            idioma, camada = None, None
            if e_pdf:
                idioma, _detectado = self.janela._idioma_do_livro(entrada, perguntar=False)
                # A régua da camada de texto numa amostra do livro (F110): a
                # caixa diz quantas páginas sairiam do próprio arquivo antes de ler.
                try:
                    camada = pdf_nativo.amostrar(entrada)
                except Exception:  # noqa: BLE001 — a sondagem que falha não barra a exportação
                    camada = None
            return idioma, camada, self.janela.ocr_service.tesseract_disponivel(idioma or "en")

        idioma_detectado, camada, (disponivel, motivo) = self.janela._esperar_sem_travar(
            "Examinando o arquivo", sondar)
        modelo_path, meta_path = caminhos_modelo_linha()
        opcoes = self.janela.DIALOGO_DE_EXPORTACAO(
            self.janela.parent, entrada=entrada, total_paginas=total, formatos=formatos,
            configuracoes=self.janela._configuracoes, idioma_detectado=idioma_detectado,
            motor_de_prosa=(disponivel, motivo),
            modelo_de_linha=modelo_utilizavel(meta_path, modelo_path),
            titulo=titulo, camada=camada).mostrar()
        if opcoes is not None and opcoes.idioma != (idioma_detectado or "en"):
            # A sondagem é por pacote de idioma (`eng`/`por`): quem trocou o
            # idioma na caixa é sondado de novo, senão o "disponível" do inglês
            # valeria para um português sem `por.traineddata`.
            disponivel, _motivo = self.janela._esperar_sem_travar(
                "Sondando o Tesseract",
                lambda: self.janela.ocr_service.tesseract_disponivel(opcoes.idioma))
        return opcoes, idioma_detectado, disponivel

    def processar_documento_editorial_action(self):
        """Lê um PDF ou imagem com o leitor de produção e grava o documento
        editorial — ou uma saída derivada dele.

        **É o mesmo leitor da exportação de livro** (`livro.extrair`: cadeia
        própria + Tesseract, fusão por palavra), atrás da fachada
        `EditorialPipeline` por `core.editorial_legacy`. A fachada sozinha, com
        o reconhecedor próprio de linha, não lê página digitalizada: medido na
        p. 30 do Aagaard em 2026-09-18, saía um bloco vazio e sem aviso, contra
        2,4% de CER pelo leitor de produção.

        JSON, HTML, TXT e PDF pesquisável saem do IR; EPUB e DOCX saem do
        escritor de produção (`exportar.exportar`), que é o que embute a fonte
        de símbolos e redesenha os diagramas — pela mesma fachada, sobre as
        páginas lidas (PD-21). A caixa é a mesma da exportação de livro
        (`DialogoDeExportacao`), com mais formatos.
        """
        if self.janela._busy("O processamento editorial"):
            return
        origem = self.janela._perguntar_entrada(
            "Selecionar PDF ou imagem",
            [("PDF e imagens", "*.pdf *.png *.jpg *.jpeg *.tif *.tiff"),
             ("Todos os arquivos", "*.*")])
        if not origem:
            return
        self.janela._avisar_do_modelo()
        opcoes, _idioma_detectado, motor_disponivel = self.janela._preparar_exportacao(
            origem, FORMATOS_EDITORIAIS, "Exportar documento editorial")
        if opcoes is None:
            return
        formato, paginas, idioma = opcoes.formato, opcoes.paginas, opcoes.idioma
        formatos = {ext for ext, _rotulo in FORMATOS_EDITORIAIS}
        if formato not in formatos:
            messagebox.showerror(
                "Documento editorial",
                f"Extensão não reconhecida: {formato!r}.\n"
                f"Use uma de: {', '.join('.' + f for f in sorted(formatos))}.")
            return
        if not motor_disponivel and not self.janela._confirmar_motor_de_prosa(idioma):
            return
        coletor = (coleta.Coletor(origem=os.path.basename(origem),
                                  max_por_classe=opcoes.teto)
                   if opcoes.coletar else None)
        opcoes_de_leitura = OpcoesDeLeitura(
            idioma=idioma, lex=self.janela.lexico_da_sessao(),
            diagramas=opcoes.diagramas, coordenadas=opcoes.coordenadas,
            fonte=opcoes.fonte, moldura=opcoes.moldura, cantos=opcoes.cantos,
            probabilidade=(self.janela.learning_service.probabilidade_de
                           if opcoes.reparar else None),
            # A caixa pela geometria da linha (F112): o top-k da rede, que a
            # poda consulta quando a leitura não cabe no corpo da linha.
            candidatas=self.janela.learning_service.candidatas,
            coletor=coletor, modelo_de_linha=opcoes.modelo_de_linha,
            usar_ensemble=opcoes.usar_ensemble,
            minimo_consenso=opcoes.minimo_consenso,
            camada=opcoes.camada)

        def trabalho(handle):
            # O adapter converte o cancelamento da UI para o token público do
            # pipeline; o worker continua sem tocar em widgets.
            class Token:
                @property
                def cancelled(self):
                    return handle.cancelled

                def raise_if_cancelled(self):
                    if self.cancelled:
                        from core.ocr_runtime import OCRCancelled
                        raise OCRCancelled("processamento editorial cancelado")

            handle.log("Carregando modelo neural...")
            pipeline, extrator = pipeline_de_producao(
                self.janela.learning_service, self.janela.ocr_service, opcoes_de_leitura,
                progresso=lambda atual, total: handle.progress(
                    atual, total, f"página {atual}/{total}"))
            source = DocumentSource.from_path(origem)
            options = ProcessOptions(
                language=idioma, use_cache=False,
                page_indices=tuple(paginas) if paginas is not None else None)
            documento = pipeline.process(source, options, Token())
            handle.raise_if_cancelled()
            handle.log("Escrevendo o arquivo...")
            arquivos = self.janela._escrever_documento_editorial(
                pipeline, documento, extrator.ultimas_paginas, opcoes, origem)
            if coletor is not None:
                coletor.gravar_indice()
            return arquivos, documento, extrator, pipeline

        def concluir(resultado):
            arquivos, documento, extrator, pipeline = resultado
            documento.metadata["review_journal_path"] = str(
                Path(arquivos[0]).with_suffix(".review.jsonl"))
            self.janela.documento_editorial = documento
            # O que a revisão precisa para **voltar** ao arquivo: o leitor
            # com as páginas lidas (o EPUB/DOCX sai delas), a fachada (os
            # formatos do IR) e as opções com que se exportou.
            self.janela.exportacao_editorial = {"pipeline": pipeline, "extrator": extrator,
                                         "opcoes": opcoes, "origem": origem}
            avisos = sum(len(page.warnings) for page in documento.pages)
            blocos = sum(len(page.blocks) for page in documento.pages)
            caracteres = sum(p.caracteres for p in extrator.ultimas_paginas)
            sem_motor = sum(1 for p in extrator.ultimas_paginas
                            if p.motor_indisponivel)
            linhas = [f"Arquivo salvo em:\n{arquivos[0]}", "",
                      f"Páginas: {len(documento.pages)}",
                      f"Blocos: {blocos}",
                      f"Caracteres lidos: {caracteres}",
                      f"Leitor de faixa: {extrator.leitor_de_faixa}",
                      f"Idioma: {idioma}"]
            da_camada = pdf_nativo.contar_leituras(
                extrator.ultimas_paginas)[pdf_nativo.LEITURA_CAMADA]
            if da_camada:
                # F110: a página da camada não tem as duas leituras por linha
                # que enchem a fila — ela sai de fora da revisão, e isso é dito.
                linhas.append(f"Páginas lidas da camada do PDF: {da_camada} — "
                              "sem OCR, fora da coleta e da fila de revisão.")
            if coletor is not None:
                linhas += ["", f"Para revisão: {coletor.resumo()}",
                           f"em {os.path.abspath(coletor.pasta)}"]
            if sem_motor:
                linhas.append(f"ATENÇÃO: o motor de prosa faltou em {sem_motor} "
                              f"página(s) — elas saíram só com a cadeia própria.")
            if avisos:
                linhas.append(f"Avisos nas páginas: {avisos}.")
            from core.editorial_review import build_review_queue
            suspeitos = len(build_review_queue(documento).items)
            linhas.append(f"Blocos na fila de revisão: {suspeitos}"
                          + (" — Revisar → Revisar documento editorial mostra cada "
                             "um com o recorte, as duas leituras e o motivo."
                             if suspeitos else "."))
            # A caixa termina com "Abrir no editor" (ED-11, SPEC_EDITOR §7.2): o livro
            # montado do documento, com a proveniência de cada bloco e a ponte ligada.
            self.janela.DIALOGO_DE_CONCLUSAO(
                self.janela.parent, "Documento editorial concluído", linhas, arquivos[0],
                abrir_no_editor=self.janela._abridor_do_editor(documento)).mostrar()

        # Barra determinada, com a página: girando sem número, a barra não
        # distinguia um livro de 525 páginas sendo lido de uma página presa (F119).
        self.janela._run_task("Processamento editorial", trabalho, concluir)

    def _escrever_documento_editorial(self, pipeline, documento, paginas, opcoes,
                                      origem: str):
        """Grava o documento editorial em `opcoes.saida`, no formato pedido.

        Um caminho só, a fachada (PD-21): EPUB e DOCX saem do escritor de
        produção (`exportar.exportar`) sobre as `PaginaExtraida` da leitura —
        `paginas`, cruas —, com a revisão do documento aplicada pela própria
        fachada e as opções da caixa (fonte do diagrama, corpo, moldura); os
        outros formatos saem do IR. É o mesmo caminho da primeira gravação e da
        regravação depois da revisão — o que muda entre as duas é o documento.
        Roda fora da thread da interface.
        """
        from core.editorial_legacy import OpcoesDeFigura

        saida, formato, idioma = opcoes.saida, opcoes.formato, opcoes.idioma
        e_pdf = origem.lower().endswith(".pdf")
        titulo, autor = (livro.titulo_e_autor(origem) if e_pdf
                         else (os.path.splitext(os.path.basename(origem))[0], ""))
        return pipeline.export(documento, saida, ExportOptions(
            format=formato, paginas=paginas,
            figura=OpcoesDeFigura(fonte=opcoes.fonte, moldura=opcoes.moldura,
                                  cantos=opcoes.cantos),
            escritor={"titulo": titulo, "autor": autor,
                      "diagramas": opcoes.diagramas_no_arquivo, "corpo_pt": opcoes.corpo_pt,
                      "moldura": opcoes.moldura, "cantos": opcoes.cantos,
                      "idioma": idioma})).files

    def revisar_documento_editorial_action(self):
        """Abre a fila de suspeitas do último documento processado.

        A janela recebe três coisas que só a janela principal tem: a imagem
        de cada página (`ProvedorDePaginas`, que rasteriza a origem na
        escala em que ela foi lida), o diálogo 8×8 para o diagrama
        (`DIALOGO_DIAGRAMA`, aberto ao lado do recorte impresso) e a
        regravação do arquivo com as correções — o FEN revisado **volta**
        para a exportação por aqui.
        """
        documento = getattr(self.janela, "documento_editorial", None)
        if documento is None:
            messagebox.showinfo(
                "Revisão editorial",
                "Processe um documento editorial primeiro para abrir a fila de revisão.",
            )
            return
        from core.editorial_legacy import ProvedorDePaginas, leitura_de_fen
        from core.editorial_review import ReviewJournal, ReviewSession
        from ui.dialogo_revisao_editorial import DialogoRevisaoEditorial
        journal = ReviewJournal(documento.metadata.get("review_journal_path"))
        try:
            sessao = ReviewSession.from_journal(documento, journal)
        except (ValueError, KeyError):
            # O diário no mesmo caminho é de outra exportação (outro
            # documento, outros blocos): não se aplica, e não se apaga.
            sessao = ReviewSession(documento, journal=journal)
        provedor = ProvedorDePaginas(documento)

        def abrir_diagrama(item, imagem):
            valor = item.value if isinstance(item.value, dict) else {}
            # O lado a jogar só é levado ao diálogo quando foi **lido** — da
            # legenda da página ou de uma revisão anterior. Assumido, ele fica
            # de fora, e o diálogo mostra o aviso da convenção em vez de exibir
            # "brancas" marcado como se alguém tivesse respondido.
            origem_do_lado = str(valor.get("side_to_move_source") or "assumed")
            leitura = leitura_de_fen(
                str(valor.get("fen") or ""), item.bbox,
                orientacao=str(valor.get("orientation") or "branca"),
                lado_a_jogar=(str(valor.get("side_to_move") or "")
                              if origem_do_lado != "assumed" else None))
            if imagem is None:
                imagem = np.full((8, 8), 255, dtype=np.uint8)
            return self.janela.DIALOGO_DIAGRAMA(
                self.janela.parent, imagem, [leitura],
                origem=f"{documento.document_id} p{item.page_index + 1}").mostrar()

        ao_exportar = (self.janela._exportar_documento_revisado
                       if getattr(self.janela, "exportacao_editorial", None) else None)
        # Duas verdades, uma resposta (SPEC_EDITOR DEC-10): com o livro aberto no editor
        # de livros, a fila não regrava o arquivo — quem exporta é o editor.
        aviso = ("o livro está no editor; exporte por ele"
                 if ao_exportar is not None and self.janela._editor_sobre(documento) else "")
        janela = DialogoRevisaoEditorial(
            self.janela, sessao, imagem_da_pagina=provedor.imagem,
            abrir_diagrama=abrir_diagrama, ao_exportar=ao_exportar, aviso_da_exportacao=aviso)
        janela.bind("<Destroy>", lambda e: provedor.fechar() if e.widget is janela else None)
        janela.mostrar()

    def _exportar_documento_revisado(self, documento):
        """Regrava o último arquivo exportado com as decisões da revisão.

        O documento revisado substitui o da sessão; a fachada aplica as
        decisões a cópias das páginas do leitor (`aplicar_revisao`: texto,
        filas, FEN redesenhado, bloco rejeitado fora, o diagrama não conferido
        carimbado — PD-21) e o arquivo sai pelo mesmo caminho da primeira vez,
        no mesmo lugar — depois de perguntar, porque sobrescreve.
        """
        contexto = getattr(self.janela, "exportacao_editorial", None)
        if not contexto:
            messagebox.showinfo("Revisão editorial",
                                "Este documento não veio de uma exportação desta sessão.")
            return
        if self.janela._busy("A exportação"):
            return
        opcoes, origem = contexto["opcoes"], contexto["origem"]
        if not messagebox.askyesno(
                "Exportar com as correções",
                f"Gravar de novo, com as correções da revisão, em:\n{opcoes.saida}\n\n"
                "O arquivo atual será substituído."):
            return
        self.janela.documento_editorial = documento
        pipeline, extrator = contexto["pipeline"], contexto["extrator"]

        def trabalho(handle):
            # A revisão é aplicada pela fachada, sobre cópias das páginas do
            # leitor (PD-21): as originais ficam como estão para a próxima.
            handle.log("Escrevendo o arquivo com as correções...")
            return self.janela._escrever_documento_editorial(
                pipeline, documento, extrator.ultimas_paginas, opcoes, origem)

        def concluir(arquivos):
            eventos = len(documento.review_events)
            self.janela.DIALOGO_DE_CONCLUSAO(
                self.janela.parent, "Exportação concluída",
                [f"Eventos de revisão aplicados: {eventos}"], arquivos[0],
                abrir_no_editor=self.janela._abridor_do_editor(documento)).mostrar()

        self.janela._run_task("Exportação revisada", trabalho, concluir, indeterminado=True)

    def exportar_livro_action(self):
        """
        Lê o PDF e escreve um EPUB ou DOCX.

        **A digitalização é lida como imagem**, porque nela a camada de texto
        vem de um OCR de fábrica que erra a notação inteira — medido na página
        11 do Yusupov, `'•. hb7 2.hb7 l2Jd7 3.ha8 Wlxa8'` onde o nosso OCR lê
        `'1...♗xb7 2.♗xb7 ♘d7 3.♗xa8 ♕xa8'`. **A página nascida digital é
        lida da camada** (F110, `core/pdf_nativo.py`), com a opção ligada na
        caixa: texto, figurinas e diagramas saem do próprio arquivo, exatos e
        sem OCR. Quem decide página a página é a régua
        (`pdf_nativo.avaliar_pagina`), e o relatório do fim conta os dois
        caminhos.

        **Uma caixa só** (`DialogoDeExportacao`, 2026-09-18) no lugar das
        catorze perguntas encadeadas de antes: formato, destino, páginas,
        idioma, motor, reparo de colagem, modelo de linha, coleta, diagramas —
        com o que se escolheu da última vez já preenchido. O que cada escolha
        significa e custa está explicado na caixa, ao lado dela; o que ela
        devolve é um `OpcoesDeExportacao`, e é dele que tudo abaixo sai.
        """
        if self.janela._busy("A exportação"):
            return
        self.janela._avisar_do_modelo()

        input_pdf = self.janela._perguntar_entrada(
            "Selecionar PDF", [("Arquivos PDF", "*.pdf")])
        if not input_pdf:
            return

        opcoes, idioma_detectado, motor_disponivel = self.janela._preparar_exportacao(
            input_pdf, FORMATOS_DE_LIVRO, "Exportar livro")
        if opcoes is None:
            return
        saida, formato, paginas = opcoes.saida, opcoes.formato, opcoes.paginas
        if formato not in exportar.FORMATOS:
            messagebox.showerror(
                "Exportar livro",
                f"Extensão não reconhecida: {formato!r}.\n"
                f"Use .epub ou .docx.")
            return
        idioma = opcoes.idioma
        detectado = idioma_detectado == idioma
        desenhar = opcoes.diagramas == "render"
        embutir = opcoes.embutir_fonte
        coordenadas = opcoes.coordenadas
        fonte_do_diagrama, moldura, cantos, corpo_pt = (
            opcoes.fonte, opcoes.moldura, opcoes.cantos, opcoes.corpo_pt)
        coletar, teto, reparar = opcoes.coletar, opcoes.teto, opcoes.reparar
        modelo_linha = opcoes.modelo_de_linha

        # **O motor de prosa é sondado antes, e não descoberto no relatório**:
        # sem o Tesseract a página inteira sai só com a cadeia própria — na
        # p. 30 do Aagaard isso é 27% de CER na prosa contra 1,3% com a fusão
        # (ROADMAP_OCR). A caixa já mostrou o estado; aqui é a última palavra.
        if not motor_disponivel and not self.janela._confirmar_motor_de_prosa(idioma):
            return

        def trabalho(h):
            h.log("Carregando modelo neural...")
            if not self.janela.learning_service.load_predictor():
                raise RuntimeError(self.janela.learning_service.motivo_do_modelo())

            coletor = coleta.Coletor(
                origem=os.path.basename(input_pdf),
                max_por_classe=teto) if coletar else None

            def progresso(atual, total):
                h.raise_if_cancelled()
                h.progress(atual, total, f"página {atual}/{total}")

            def probabilidade(recorte, char):
                # O reparo de colagem é o laço mais longo da página, e o
                # cancelamento só era visto entre páginas (F119).
                h.raise_if_cancelled()
                return self.janela.learning_service.probabilidade_de(recorte, char)

            from core.editorial_legacy import ExtratorDeLivro, OpcoesDeLeitura
            leitura = OpcoesDeLeitura(
                idioma=idioma, fusao="palavra",
                diagramas="render" if desenhar else "recorte",
                coordenadas=coordenadas, fonte=fonte_do_diagrama,
                moldura=moldura, cantos=cantos, lex=self.janela.lexico_da_sessao(),
                probabilidade=(probabilidade if reparar else None),
                candidatas=self.janela.learning_service.candidatas,
                coletor=coletor, modelo_de_linha=modelo_linha,
                usar_ensemble=opcoes.usar_ensemble,
                minimo_consenso=opcoes.minimo_consenso,
                dpi=300, camada=opcoes.camada)
            classificar, ler_pagina, ler_faixa = ExtratorDeLivro(
                self.janela.learning_service, self.janela.ocr_service, leitura)._leitores()

            paginas_extraidas = livro.extrair(input_pdf,
                                    classificar,
                                    paginas=paginas,
                                    coletor=coletor,
                                    ler_pagina=ler_pagina,
                                    ler_faixa=ler_faixa,
                                    idioma_ocr=idioma,
                                    lex=self.janela.lexico_da_sessao(),
                                    # A prova visual do reparo de colagem (F69):
                                    # é ela que autoriza trocar `Dmamic` por
                                    # `Dynamic`. Sem ela o reparo não roda, e é
                                    # assim que o "não" da pergunta o desliga.
                                    probabilidade=(probabilidade if reparar
                                                   else None),
                                    # A caixa pela geometria da linha (F112).
                                    candidatas=self.janela.learning_service.candidatas,
                                    diagramas="render" if desenhar else "recorte",
                                    coordenadas=coordenadas,
                                    moldura=moldura, cantos=cantos,
                                    fonte=fonte_do_diagrama,
                                    progress_callback=progresso,
                                    camada=opcoes.camada)
            h.log("Escrevendo o arquivo...")
            titulo, autor = livro.titulo_e_autor(input_pdf)
            exportar.exportar(paginas_extraidas, saida, formato=formato,
                              titulo=titulo, autor=autor,
                              diagramas="fonte" if embutir else "png",
                              corpo_pt=corpo_pt, moldura=moldura,
                              cantos=cantos, idioma=idioma)
            if coletor is not None:
                coletor.gravar_indice()
            return paginas_extraidas, coletor

        def concluir(resultado):
            paginas, coletor = resultado
            figuras = sum(1 for p in paginas for b in p.blocos
                          if isinstance(b, livro.Figura) and b.origem != "faixa")
            faixas = sum(1 for p in paginas for b in p.blocos
                         if isinstance(b, livro.Figura) and b.origem == "faixa")
            de_imagem = sum(1 for p in paginas if p.pagina_de_imagem)
            diagramas = sum(p.diagramas for p in paginas)
            desenhados = sum(p.diagramas_desenhados for p in paginas)
            linhas = [
                f"Páginas: {len(paginas)}",
                f"Caracteres lidos: {sum(p.caracteres for p in paginas)}",
                f"Figuras: {figuras}",
            ]
            if faixas:
                linhas.append(f"Cabeçalhos de diagrama recuperados: {faixas}")
            varias = sum(1 for p in paginas if p.colunas > 1)
            if varias:
                # É o único jeito de conferir a F61 sem abrir o arquivo: numa
                # página lida como uma coluna só, as duas se misturam.
                linhas.append(f"Páginas lidas em mais de uma coluna: "
                              f"{varias} de {len(paginas)}")
            # **De onde veio cada página tem de aparecer** (F110): a da camada
            # do PDF não tem box nem confiança por glifo, e por isso não
            # alimenta a coleta nem a fila de revisão — a base de treino não
            # pode encolher sem ninguém ver.
            leituras = pdf_nativo.contar_leituras(paginas)
            if leituras[pdf_nativo.LEITURA_CAMADA]:
                linhas.append(
                    f"Páginas lidas da camada do PDF: "
                    f"{leituras[pdf_nativo.LEITURA_CAMADA]} de {len(paginas)} — "
                    "texto e diagramas do próprio arquivo, sem OCR; elas não "
                    "entram na coleta nem na fila de revisão.")
            if desenhar and diagramas:
                # Quem caiu para o recorte é o que o usuário precisa saber para
                # conferir: são as páginas em que a leitura não convenceu.
                linhas.append(f"Diagramas redesenhados: {desenhados} de {diagramas}")
                recortados = [
                    f"  página {p.numero + 1}: {b.aviso}"
                    for p in paginas for b in p.blocos
                    if isinstance(b, livro.Figura) and b.aviso
                    and b.origem != "render"]
                # O desenho com ressalva é o da camada sem coordenada impressa:
                # a posição é exata, a orientação é suposta.
                ressalvas = [
                    f"  página {p.numero + 1}: {b.aviso}"
                    for p in paginas for b in p.blocos
                    if isinstance(b, livro.Figura) and b.aviso
                    and b.origem == "render"]
                if ressalvas:
                    linhas.append(f"Desenhados com ressalva ({len(ressalvas)}):")
                    linhas += ressalvas[:6]
                    if len(ressalvas) > 6:
                        linhas.append(f"  ... e mais {len(ressalvas) - 6}")
                if recortados:
                    linhas.append(f"Caíram para o recorte do scan "
                                  f"({len(recortados)}):")
                    linhas += recortados[:12]
                    if len(recortados) > 12:
                        linhas.append(f"  ... e mais {len(recortados) - 12}")
            # **O dicionário reescreveu texto, e isso tem de aparecer** (F115).
            # A F66 recusou ligar o reparo de colagem chamando-o de "reescrever
            # o texto em silêncio"; o silêncio era metade da objeção, e é esta
            # linha que a desfaz — quem exporta vê quantas palavras mudaram e
            # pode conferi-las.
            reparos = sum(p.reparos for p in paginas)
            cortes = sum(p.cortes for p in paginas)
            if reparos or cortes:
                linhas.append(f"Reparos do dicionário: {reparos} palavra(s) "
                              f"corrigida(s) pelo desenho, {cortes} colada(s) "
                              f"partida(s).")
            # **O que saiu da prosa tem de ser dito** (F109), pela mesma razão
            # do reparo: quem exporta precisa poder conferir que o que foi
            # retirado era cabeçalho de página, e não a primeira linha de um
            # capítulo que se repetia.
            retirados = collections.Counter()
            for p in paginas:
                retirados.update(p.cabecalhos)
            if retirados:
                exemplos = ", ".join(f"'{t}' ({n}×)"
                                     for t, n in retirados.most_common(3))
                linhas.append(f"Cabeçalhos e rodapés de página retirados: "
                              f"{sum(retirados.values())} — {exemplos}")
            nome = {"en": "inglês", "pt": "português"}.get(idioma, idioma)
            linhas.append(f"Idioma: {nome} "
                          + ("(pela camada de texto do PDF)" if detectado
                             else "(informado)"))
            # O sumário e o que ficou mudo no arquivo (F111).
            capitulos = exportar.capitulos(paginas)
            if capitulos:
                linhas.append(f"Capítulos no sumário: {len(capitulos)} — "
                              + "; ".join(t for _a, _b, t in capitulos[:4]))
            mudos = exportar.simbolos_sem_fonte(
                "".join(p.texto for p in paginas))
            if mudos:
                linhas.append(f"Símbolos que nenhuma fonte do arquivo desenha: "
                              f"{' '.join(mudos)}")
            if de_imagem:
                linhas.append(f"{de_imagem} página(s) eram imagem e saíram inteiras.")
            # **Quem leu cada linha tem de aparecer**, pela mesma razão do
            # reparo: a prosa que veio do Tesseract é a que se confere de outro
            # jeito. O lance fica sempre com a cadeia própria, mesmo na linha
            # fundida — é o roteamento por palavra de `livro.extrair_pagina`.
            fontes = collections.Counter(r["fonte"] for p in paginas
                                         for r in p.roteamento if r["texto"])
            if fontes:
                fundidas = fontes.get("fusao", 0) + fontes.get("line", 0)
                linhas.append(f"Linhas lidas: {fontes.get('glyph', 0)} só pela "
                              f"cadeia própria, {fundidas} com a prosa do "
                              f"Tesseract e os lances da cadeia.")
            # **A página em que o motor faltou tem de aparecer**: até aqui a
            # falha do Tesseract devolvia `[]` e a página saía "normal" — só
            # com a cadeia própria, 20 vezes pior na prosa, sem uma linha de
            # aviso. Quem exporta precisa saber quais páginas conferir.
            sem_motor = [p for p in paginas if p.motor_indisponivel]
            if sem_motor:
                motivos = collections.Counter(p.motor_indisponivel
                                              for p in sem_motor)
                motivo, _n = motivos.most_common(1)[0]
                numeros = ", ".join(str(p.numero + 1) for p in sem_motor[:8])
                if len(sem_motor) > 8:
                    numeros += f" e mais {len(sem_motor) - 8}"
                linhas.append(f"ATENÇÃO: o motor de prosa falhou em "
                              f"{len(sem_motor)} página(s) — {numeros} — que "
                              f"saíram só com a cadeia própria. Motivo: "
                              f"{motivo}")
            if coletor is not None:
                linhas += ["", f"Para revisão: {coletor.resumo()}",
                           f"em {os.path.abspath(coletor.pasta)}"]
            da_camada = leituras[pdf_nativo.LEITURA_CAMADA]
            if paginas and da_camada == len(paginas):
                linhas += ["", "O texto e os diagramas vieram da camada do PDF — "
                           "nenhuma página passou pelo OCR."]
            elif not da_camada:
                linhas += ["", "O texto veio do nosso OCR — "
                           + ("a régua não reconheceu camada tipográfica neste PDF."
                              if opcoes.ler_camada else
                              "a leitura da camada do PDF estava desligada.")]
            # A caixa termina com o arquivo aberto — no leitor, na pasta ou, se
            # for EPUB, no editor de livros (ED-02, SPEC_EDITOR §7.2).
            self.janela.DIALOGO_DE_CONCLUSAO(
                self.janela.parent, "Livro exportado", linhas, saida,
                abrir_no_editor=(self.janela.abrir_editor_de_livro
                                 if formato == "epub" else None)).mostrar()

        self.janela._run_task("Exportar livro", trabalho, concluir)

    def exportar_pgn(self):
        """
        Grava a notação reconhecida como `.pgn`.

        Roda na thread da UI pelo mesmo motivo de `validar_notacao`: o custo é a
        análise, que são dezenas de milissegundos numa página cheia.
        """
        from core import pgn

        if not self.janela.boxes:
            messagebox.showinfo("Exportar PGN", "Nenhum box na página.")
            return

        texto, relatorio = pgn.exportar(
            self.janela.boxes,
            pgn.cabecalhos_do_documento(
                self.janela.session.path if self.janela.session else self.janela.image_path,
                self.janela.current_pdf_page if self.janela.session
                and self.janela.session.is_pdf else None))

        if not texto.strip():
            messagebox.showinfo(
                "Exportar PGN",
                "Nenhuma partida completa foi reconhecida nesta página.\n\n"
                + relatorio.resumo()
                + "\n\nA leitura começa num '1.' — sem o começo da partida não "
                  "há posição de onde partir.")
            return

        pasta, nome = self.janela._destino_sugerido(".pgn", "partida")

        caminho = filedialog.asksaveasfilename(
            defaultextension=".pgn", initialdir=pasta or None, initialfile=nome,
            filetypes=[("Arquivos PGN", "*.pgn"), ("Todos", "*.*")])
        if not caminho:
            return

        try:
            # O PGN é ASCII por especificação, mas comentário e cabeçalho aqui
            # podem trazer acento do nome do arquivo. UTF-8 é o que os programas
            # de xadrez atuais leem.
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(texto)
        except OSError as e:
            messagebox.showerror("Erro", f"Não foi possível gravar o PGN:\n{e}")
            return

        messagebox.showinfo(
            "Exportar PGN",
            f"Gravado em {os.path.basename(caminho)}.\n\n{relatorio.resumo()}")
        self.janela.status.set(f"PGN exportado: {relatorio.lances} lances em "
                        f"{len(relatorio.partidas)} partida(s).")
