"""
O fluxo de treino da janela principal, num lugar só (PD-22).

Até aqui os 20 métodos — aprender com a página, verificar e corrigir a base, treinar
a rede de glifos e o OCR de linhas, validar e avaliar o dataset de linhas, os
relatórios, o modelo de diagramas, o treinamento geral, os recortes para revisão e a
promoção deles — moravam em `ui/main_window.py`: 799 das 5.105 linhas da janela, mais
o `_validar_dataset_adicional_linhas` que o treino de linhas usa. Aqui eles são o
`Treino`, que a janela cria no `__init__` (`self.treino = Treino(self)`) e para o qual
delega, método a método, com o mesmo nome: `janela.train_line_ocr()` continua
existindo, para o menu e os testes; o corpo é o daqui.

A janela continua dona do estado (`boxes`, `image_path`, `current_pdf_page`), dos
serviços (`learning_service`, `ocr_service`) e de `_run_task`, que leva o trabalho
para fora da thread do Tk: os métodos falam com ela por `self.janela`, e quem troca
um método da janela num teste continua sendo ouvido, porque as chamadas internas
passam pelo delegado. É o padrão de `ui/exportacao.py` (item 6 da análise de
2026-10-06).
"""
from __future__ import annotations

import os
from pathlib import Path
from tkinter import filedialog, messagebox
from PIL import Image
from core import coleta, livro
from config.paths import (caminhos_modelo_linha, modelo_de_lingua, pasta_de_linhas,
                          pasta_de_linhas_sinteticas, relatorio_de_linhas)
from core.services.pdf_service import DPI_PADRAO


def _validar_dataset_adicional_linhas(caminho, treino, *, nome, outros=()):
    """Valida um dataset escolhido na UI antes de iniciar o treinamento."""
    from core.linha_trainer import validar_dataset

    caminho = Path(caminho).resolve()
    treino = Path(treino).resolve()
    if caminho == treino:
        raise ValueError(f"o dataset de {nome} precisa ser independente do treino")
    if any(caminho == Path(outro).resolve() for outro in outros if outro is not None):
        raise ValueError(f"o dataset de {nome} precisa ser diferente dos demais datasets")
    if not (caminho / "rec_gt.txt").is_file():
        raise ValueError(f"o dataset de {nome} não contém rec_gt.txt")
    diagnostico = validar_dataset(caminho)
    problemas = (diagnostico.get("vazias", [])
                 + diagnostico.get("ilegiveis", [])
                 + diagnostico.get("ausentes", [])
                 + diagnostico.get("malformadas", []))
    if problemas:
        raise ValueError(
            f"o dataset de {nome} contém {len(problemas)} entrada(s) inválida(s)")
    return caminho


class Treino:
    """O fluxo de treino da janela principal; `janela` é a `MainWindow`."""

    def __init__(self, janela):
        self.janela = janela

    def preparar_dataset_correcoes_action(self):
        """Materializa somente eventos editoriais confirmados para o treino."""
        documento = getattr(self.janela, "documento_editorial", None)
        if documento is None:
            messagebox.showinfo(
                "Dataset de correções",
                "Processe e revise um documento editorial antes de preparar o dataset.",
            )
            return
        destino = filedialog.asksaveasfilename(
            title="Salvar dataset versionado de correções",
            defaultextension=".json",
            filetypes=[("Dataset de correções", "*.json")],
        )
        if not destino:
            return
        from core.ocr_phase7 import CorrectionDataset
        dataset = CorrectionDataset.from_document(documento)
        dataset.save(destino)
        messagebox.showinfo(
            "Dataset de correções",
            f"{len(dataset.records)} correção(ões) salvas.\n\nChecksum: {dataset.digest()}",
        )

    def criar_recortes_action(self):
        """
        Lê o PDF e grava os recortes de caractere separados por classe.

        Não escreve nada além dos PNG: nem PDF, nem livro. É o caminho para
        crescer a base de treino olhando — a pasta de uma classe fica cheia de
        acertos e o intruso salta aos olhos numa grade de miniaturas.

        **A pasta é escolhida, e o padrão nunca é `training_data`.** Amostra
        por conferir não pode ficar onde o treino varre.
        """
        if self.janela._busy("A extração de recortes"):
            return
        self.janela._avisar_do_modelo()

        input_pdf = filedialog.askopenfilename(
            title="Selecionar PDF",
            filetypes=[("Arquivos PDF", "*.pdf")]
        )
        if not input_pdf:
            return

        pasta = filedialog.askdirectory(title="Onde gravar os recortes...")
        if not pasta:
            return

        # As duas revisões são diferentes e as duas servem; ver LIMIAR_PADRAO.
        todos = messagebox.askyesnocancel(
            "Quais recortes gravar?",
            "Sim — todos os caracteres.\n"
            "    A pasta de cada classe fica cheia de acertos, e o recorte que "
            "não pertence ali salta aos olhos. É o modo de revisar batendo o "
            "olho, e o que faz a base crescer.\n\n"
            "Não — só os que o modelo leu com dúvida.\n"
            "    Bem menos arquivo, e mostra onde o modelo é fraco. Mas a pasta "
            "fica sem contraste: se quase tudo ali está errado, não há com o "
            "que comparar.\n\n"
            "Em seguida você escolhe o teto por classe — em branco, sem teto.")
        if todos is None:
            return

        teto = self.janela._perguntar_teto()
        if teto is self.janela.CANCELADO:
            return

        def trabalho(h):
            h.log("Carregando modelo neural...")
            if not self.janela.learning_service.load_predictor():
                raise RuntimeError(self.janela.learning_service.motivo_do_modelo())

            coletor = coleta.Coletor(
                pasta=pasta, origem=os.path.basename(input_pdf),
                max_por_classe=teto,
                limiar=None if todos else coleta.LIMIAR_PADRAO,
                # A segunda candidata só é perguntada para o recorte que vai
                # ser gravado, e não para todo box da página: com a dedução na
                # frente, é uma inferência por arquivo em disco. Ver `detalhar`.
                detalhar=self.janela.learning_service.candidatas)

            def progresso(atual, total):
                h.raise_if_cancelled()
                h.progress(atual, total, f"página {atual}/{total}")

            livro.extrair(input_pdf, self.janela.learning_service.ler_texto,
                          coletor=coletor, progress_callback=progresso)
            coletor.gravar_indice()
            return coletor

        def concluir(coletor):
            linhas = [coletor.resumo(), "", f"Em: {os.path.abspath(coletor.pasta)}"]
            if coletor.total:
                linhas += [
                    "",
                    "Cada pasta é uma classe. Abra a pasta em miniaturas grandes "
                    "e procure o recorte que não pertence ali:",
                    "  • está certo — deixe onde está",
                    "  • está na classe errada — mova para a pasta certa",
                    "  • não é caractere — apague",
                    "",
                    "Ordene por Nome: o nome começa pela confiança, então a "
                    "fila sai com os mais duvidosos na frente.",
                    f"O {coleta.NOME_DO_INDICE} ao lado traz a segunda "
                    "candidata de cada recorte — é ela que diz para qual pasta "
                    "ele provavelmente devia ir.",
                    "",
                    "Depois, 'Promover recortes revistos para a base'."]
            (messagebox.showinfo if coletor.total else messagebox.showwarning)(
                "Recortes para revisão", "\n".join(linhas))

        self.janela._run_task("Criar recortes", trabalho, concluir)

    def promover_revisao_action(self):
        """
        Leva para a base de treino o que sobreviveu à revisão.

        O rótulo é o nome da pasta, então o que valeu foi o que você fez com o
        mouse: confirmar é deixar onde está, corrigir é mover, descartar é
        apagar. Pasta com nome que não é rótulo é recusada, não adivinhada.
        """
        if self.janela._busy("A promoção"):
            return

        pasta = filedialog.askdirectory(
            title="Pasta de revisão", initialdir=os.path.abspath(coleta.PASTA_PADRAO)
            if os.path.isdir(coleta.PASTA_PADRAO) else None)
        if not pasta:
            return

        quantos = sum(len([a for a in os.listdir(os.path.join(pasta, d))
                           if a.lower().endswith(".png")])
                      for d in os.listdir(pasta)
                      if os.path.isdir(os.path.join(pasta, d)))
        if not quantos:
            messagebox.showinfo("Promover recortes",
                                "Não há recorte nenhum nessa pasta.")
            return
        if not messagebox.askyesno(
                "Promover recortes",
                f"{quantos} recorte(s) vão entrar na base de treino, com o "
                f"rótulo da pasta em que estão.\n\n"
                "Confira antes: amostra com rótulo errado ensina o modelo "
                "errado, e sair dele depois dá trabalho."):
            return

        def trabalho(h):
            h.log("Lendo os recortes revistos...")
            return coleta.promover(pasta, data_dir=self.janela.learning_service.data_dir)

        def concluir(r):
            linhas = [f"{r.aprendidos} recorte(s) em {r.classes} classe(s) "
                      f"entraram na base."]
            if r.recusados:
                linhas += ["", "Pastas recusadas por não serem rótulo:",
                           "  " + ", ".join(r.recusados[:8])]
            if r.ilegiveis:
                linhas.append(f"{len(r.ilegiveis)} arquivo(s) ilegíveis.")
            linhas += ["", "Treine a rede para o modelo passar a usá-los."]
            messagebox.showinfo("Promover recortes", "\n".join(linhas))

        self.janela._run_task("Promover recortes", trabalho, concluir)

    def learn_from_current_page(self):
        if self.janela._busy("O aprendizado"):
            return

        if self.janela.image is None or not self.janela.boxes:
            messagebox.showinfo("Aviso", "Nada para aprender na página atual.")
            return

        if not messagebox.askyesno(
            "Confirmar Aprendizado",
            f"Deseja adicionar {len(self.janela.boxes)} caracteres desta página à base de conhecimento?\n"
            "Certifique-se de que os caracteres estão CORRETOS antes de prosseguir."
        ):
            return

        imagem = self.janela.image.copy()
        boxes = [b.copy() for b in self.janela.boxes]

        # Fora da thread: mexe no léxico da sessão e no cache de suspeitas, que
        # são estado da UI. É rápido — a página inteira é uma passada de
        # `_fatiar` — e não tem por que disputar a vaga da tarefa de fundo.
        palavras = self.janela.aprender_palavras_da_pagina()

        def trabalho(h):
            h.progress(0, len(boxes), "gravando amostras")
            return self.janela.learning_service.learn_from_boxes(imagem, boxes)

        def concluir(count):
            aviso = f"Aprendizado concluído.\n{count} novos modelos adicionados."
            aviso += self.janela._frase_do_dicionario(palavras)
            messagebox.showinfo("Sucesso", aviso)
            if palavras:
                self.janela.update_sidebar()
                self.janela.update_canvas()

        self.janela._run_task("Aprender com a página", trabalho, concluir, indeterminado=True)

    def verificar_base_treino(self):
        """
        Diagnóstico completo da base, inclusive lendo cada PNG.

        Vale um item de menu próprio: o defeito que motivou isto (127 amostras
        treinando a classe errada) só era visível para quem fosse conferir os
        nomes das pastas à mão.
        """
        if self.janela._busy("A verificação"):
            return

        def trabalho(h):
            h.log("Lendo a base de treino...")
            return self.janela.learning_service.validar_dados(checar_pngs=True)

        def concluir(problemas):
            graves = [p for p in problemas if p.grave]
            avisos = [p for p in problemas if not p.grave]
            if not problemas:
                messagebox.showinfo("Base de treino", "Nenhum problema encontrado.")
                return

            linhas = []
            if graves:
                linhas.append(f"{len(graves)} problema(s) que impedem o treino:")
                linhas += [f"  {p}" for p in graves[:15]]
                if len(graves) > 15:
                    linhas.append(f"  ... e mais {len(graves) - 15}")
            if avisos:
                if linhas:
                    linhas.append("")
                linhas.append(f"{len(avisos)} aviso(s) de classe com poucas amostras:")
                linhas += [f"  {p}" for p in avisos[:10]]
                if len(avisos) > 10:
                    linhas.append(f"  ... e mais {len(avisos) - 10}")

            if self.janela._corrigiveis(graves):
                linhas.append("")
                linhas.append(self.janela.EXPLICACAO_DA_CORRECAO)
                linhas.append("")
                linhas.append("Corrigir agora?")
                if messagebox.askyesno("Base de treino", "\n".join(linhas),
                                       icon="warning"):
                    self.janela.corrigir_base_treino(checar_pngs=True)
                return

            mostrar = messagebox.showerror if graves else messagebox.showinfo
            mostrar("Base de treino", "\n".join(linhas))

        self.janela._run_task("Verificar base de treino", trabalho, concluir,
                       indeterminado=True)

    @staticmethod
    def _corrigiveis(problemas):
        """Os problemas que a correção automática sabe resolver."""
        from core.dataset_check import TIPOS_CORRIGIVEIS
        return [p for p in problemas if p.tipo in TIPOS_CORRIGIVEIS]

    def corrigir_base_treino(self, checar_pngs=True, depois=None):
        """
        Sanea a base sozinho: renomeia, mescla, quarentena.

        Existe porque o diagnóstico parava no meio do caminho. Ele dizia que
        'ç' e 'sym_231' são a mesma classe partida em duas — e deixava o
        usuário juntar as duas pastas à mão, no Explorer, que é exatamente
        onde amostra se perde.

        `depois` encadeia o que motivou a correção (o treino, tipicamente).
        Roda no `ao_concluir`, ou seja na thread da UI e com a tarefa anterior
        já encerrada — é seguro disparar outra tarefa dali.
        """
        if self.janela._busy("A correção"):
            return

        def trabalho(h):
            h.log("Corrigindo a base de treino...")
            registro = self.janela.learning_service.sanear_dados(
                checar_pngs=checar_pngs, callback=h.log)
            # Revalidar em vez de confiar no registro: o que interessa é a base
            # ter ficado treinável, não a migração ter dito que fez algo.
            #
            # Pelo caminho rápido, mesmo quando a correção leu os PNGs: o que
            # não deu certo já está no registro como FALHOU, e reler os 571 mil
            # arquivos de novo custaria outra varredura completa para confirmar
            # o que a última passada da migração acabou de conferir.
            restantes = [p for p in self.janela.learning_service.validar_dados()
                         if p.grave]
            recusas = [r for r in registro
                       if r.startswith("FALHOU") or r.startswith("ATENÇÃO")]
            return registro, restantes, recusas

        def concluir(resultado):
            registro, restantes, recusas = resultado

            if restantes or recusas:
                linhas = [f"{len(registro)} correção(ões) aplicada(s), mas a "
                          "base ainda não está pronta para o treino:"]
                linhas += [f"  {p}" for p in restantes[:12]]
                if len(restantes) > 12:
                    linhas.append(f"  ... e mais {len(restantes) - 12}")
                linhas += [f"  {r}" for r in recusas[:6]]
                messagebox.showerror("Corrigir base de treino", "\n".join(linhas))
                return

            if not registro:
                messagebox.showinfo("Corrigir base de treino",
                                    "Nada a corrigir: a base já está sã.")
            else:
                linhas = [f"{len(registro)} correção(ões) aplicada(s):"]
                linhas += [f"  {r}" for r in registro[:15]]
                if len(registro) > 15:
                    linhas.append(f"  ... e mais {len(registro) - 15}")
                if depois is None:
                    messagebox.showinfo("Corrigir base de treino",
                                        "\n".join(linhas))
                else:
                    self.janela.status.set(f"Base corrigida: {len(registro)} ação(ões).")

            if depois is not None:
                depois()

        self.janela._run_task("Corrigir base de treino", trabalho, concluir,
                       indeterminado=True)

    def train_neural_network(self):
        if self.janela._busy("O treino"):
            return

        if not self.janela.learning_service.data_dir or not os.listdir(self.janela.learning_service.data_dir):
            messagebox.showinfo(
                "Aviso",
                "Nenhum dado de treinamento encontrado.\nUse 'Aprender com Página Atual' primeiro."
            )
            return

        from tkinter import simpledialog
        # "1 epoch = uma passada": antes o dataset materializava 8 cópias
        # aumentadas de cada amostra, então um epoch valia 9 passadas. Com a
        # augmentation sob demanda (F1.2) o epoch voltou ao significado usual —
        # e ficou ~9x mais rápido, o que muda o número que faz sentido pedir.
        epochs = simpledialog.askinteger(
            "Epochs",
            "Quantas epochs deseja treinar?\n(1 epoch = uma passada pela base)\n"
            "(Mais epochs = mais preciso, porém mais lento)\n\nRecomendado: 15-30",
            initialvalue=15,
            minvalue=1,
            maxvalue=200
        )
        if epochs is None:
            return

        self.janela._treinar_rede(epochs)

    def train_line_ocr(self):
        """Treina o reconhecedor CRNN/CTC com as linhas corrigidas."""
        if self.janela._busy("O treino sequencial"):
            return
        # A base, a sintética e o modelo saem de `config.paths`, e não do cwd:
        # aberto por atalho, o app rotulava numa pasta e treinava de outra.
        base = pasta_de_linhas()
        sinteticas = pasta_de_linhas_sinteticas()
        if not (base / "rec_gt.txt").exists():
            messagebox.showinfo(
                "Treino sequencial",
                "Nenhum dataset de linhas encontrado.\n"
                "Use a Janela de rotulagem e salve algumas linhas primeiro.",
            )
            return
        try:
            from core.linha_trainer import validar_dataset
            diagnostico = validar_dataset(base)
            if diagnostico.get("malformadas") or diagnostico.get("ausentes"):
                messagebox.showerror(
                    "Treino sequencial",
                    "O dataset possui entradas inválidas. Use 'Validar dataset de linhas'.")
                return
            self.janela.status.set(f"Dataset: {diagnostico['linhas']} linhas, "
                            f"{diagnostico['caracteres']} caracteres.")
        except Exception as exc:
            messagebox.showerror("Treino sequencial", str(exc))
            return
        dataset_treino = base
        dataset_validacao = None
        dataset_holdout = None
        dataset_calibracao = None
        if messagebox.askyesno(
                "Holdout real",
                "Selecionar um dataset real e independente para o holdout? Sim = promocao; Nao = treino experimental."):
            selecionado = filedialog.askdirectory(
                title="Selecione o dataset REAL de holdout",
                initialdir=str(base.parent))
            if not selecionado:
                return
            try:
                dataset_holdout = _validar_dataset_adicional_linhas(
                    selecionado, dataset_treino, nome="holdout",
                    outros=(dataset_validacao,))
            except (OSError, ValueError) as exc:
                messagebox.showerror("Holdout real", str(exc))
                return

            if messagebox.askyesno(
                    "Calibracao opcional",
                    "Selecionar tambem um dataset independente para calibrar a confianca? (opcional)"):
                selecionado = filedialog.askdirectory(
                    title="Selecione o dataset de calibracao",
                    initialdir=str(base.parent))
                if not selecionado:
                    return
                try:
                    dataset_calibracao = _validar_dataset_adicional_linhas(
                        selecionado, dataset_treino, nome="calibracao",
                        outros=(dataset_validacao, dataset_holdout))
                except (OSError, ValueError) as exc:
                    messagebox.showerror("Calibracao", str(exc))
                    return

        if (diagnostico.get("linhas", 0) < 500 and (sinteticas / "rec_gt.txt").exists()
                and messagebox.askyesno(
                    "Dataset sintético",
                    "Usar o dataset sintético para treino e as linhas reais como validação?\n\n"
                    "Recomendado quando há poucas linhas reais anotadas.")):
            dataset_treino = sinteticas
            dataset_validacao = base
        from tkinter import simpledialog
        epocas = simpledialog.askinteger(
            "Treino OCR sequencial",
            "Quantas epochs deseja treinar?\n\nRecomendado: 20-50",
            initialvalue=20, minvalue=1, maxvalue=500,
        )
        if epocas is None:
            return

        batch = simpledialog.askinteger(
            "Batch size", "Quantas linhas por lote?\n\nRecomendado: 4–8",
            initialvalue=8, minvalue=1, maxvalue=64)
        if batch is None:
            return
        paciencia = simpledialog.askinteger(
            "Paciência", "Epochs sem melhora antes de parar:",
            initialvalue=6, minvalue=1, maxvalue=50)
        if paciencia is None:
            return

        def trabalho(h):
            from core.ocr_training import treinar_pacote
            return treinar_pacote(pasta=dataset_treino, validacao=dataset_validacao,
                                  calibracao=dataset_calibracao,
                                  holdout=dataset_holdout,
                                  epocas=epocas, batch_size=batch, paciencia=paciencia,
                                  callback=h.log,
                                  should_stop=lambda: h.cancelled,
                                  service=self.janela.ocr_service)

        def concluir(sucesso):
            if sucesso:
                self.janela.ocr_service.recarregar_linha_treinada()
                modelo, meta = caminhos_modelo_linha()
                elegivel = bool(getattr(sucesso, "production_eligible", False))
                motivo_portao = str(
                    getattr(sucesso, "production_gate_reason", "") or "")
                uso = (
                    "O modelo passou pelo holdout e poderá ser usado na produção."
                    if elegivel else
                    "O modelo ficou fora da produção e não será usado automaticamente.\n"
                    f"Motivo do portão: {motivo_portao or 'holdout não aprovado'}.\n"
                    "Ele ainda pode ser aplicado manualmente para inspeção."
                )
                if not elegivel:
                    motivo_portao = motivo_portao or "holdout nao aprovado"
                    uso = ("Modelo experimental; nao sera usado automaticamente. "
                           f"Motivo do portao: {motivo_portao}. "
                           "Pode ser aplicado manualmente para inspecao.")
                    messagebox.showinfo(
                        "Treino OCR completo",
                        f"Treinamento concluído.\nPesos: {modelo}\n"
                        f"Metadados: {meta}\n\n{uso}")
                    return
                messagebox.showinfo(
                    "Treino OCR completo",
                    "Treinamento concluído.\n"
                    f"Pesos: {modelo}\n"
                    f"Metadados: {meta}\n"
                    f"Léxico: {getattr(sucesso, 'language_model', '') or modelo_de_lingua()}\n\n"
                    "O botão Executar usará o modelo treinado por linha.\n"
                    "Tesseract, EasyOCR e PaddleOCR continuam como engines "
                    "auxiliares/fallback.",
                )
            else:
                messagebox.showinfo("Treino sequencial", "Treinamento cancelado.")

        self.janela._run_task("Treino OCR sequencial", trabalho, concluir)

    def validar_dataset_linhas(self):
        """Mostra problemas e cobertura da base de linhas antes do treino.

        Numa tarefa (item 9 da revisão de 2026-09-18): a validação abre cada
        imagem da base, e com alguns milhares de linhas isso congelava a janela.
        """
        def trabalho(h):
            from core.linha_trainer import validar_dataset
            h.log("Conferindo as imagens da base de linhas...")
            return validar_dataset()

        def falhou(exc):
            messagebox.showerror("Dataset de linhas", str(exc))
            return True

        self.janela._run_task("Validar dataset de linhas", trabalho,
                       self.janela._mostrar_validacao_de_linhas, indeterminado=True,
                       ao_falhar=falhou)

    @staticmethod
    def _mostrar_validacao_de_linhas(resumo):
        problemas = (len(resumo["vazias"]) + len(resumo["ilegiveis"])
                     + len(resumo.get("ausentes", []))
                     + len(resumo.get("malformadas", [])))
        texto = (f"Linhas válidas no manifesto: {resumo['linhas']}\n"
                 f"Caracteres distintos: {resumo['caracteres']}\n"
                 f"Problemas: {problemas}\n\n"
                 f"Alfabeto: {resumo['alfabeto']}")
        if problemas:
            texto += "\n\nArquivos problemáticos:\n" + "\n".join(
                (resumo["vazias"] + resumo["ilegiveis"]
                 + resumo.get("ausentes", []) + resumo.get("malformadas", []))[:10])
            messagebox.showwarning("Dataset de linhas", texto)
        else:
            messagebox.showinfo("Dataset de linhas", texto)

    def avaliar_modelo_linhas(self):
        """Executa CER/WER no manifesto e mostra o resultado por página.

        Numa tarefa (item 9 da revisão de 2026-09-18): é a rede lendo a base
        inteira, linha a linha, e congelava a janela o tempo todo.
        """
        modelo, meta = caminhos_modelo_linha()
        if not (modelo.exists() and meta.exists()):
            messagebox.showinfo("Avaliação", "Treine o modelo sequencial primeiro.")
            return

        def trabalho(h):
            from core.linha_trainer import avaliar, salvar_avaliacao
            h.log("Lendo a base de linhas com o modelo...")
            resultado = avaliar(str(modelo), str(meta))
            salvar_avaliacao(resultado)
            return resultado

        def falhou(exc):
            messagebox.showerror("Avaliação do OCR", str(exc))
            return True

        self.janela._run_task("Avaliar modelo de linhas", trabalho,
                       self.janela._mostrar_avaliacao_de_linhas, indeterminado=True,
                       ao_falhar=falhou)

    @staticmethod
    def _mostrar_avaliacao_de_linhas(resultado):
        linhas = [
            f"Linhas avaliadas: {resultado['linhas']}",
            f"CER: {resultado['cer']:.2%}",
            f"WER: {resultado['wer']:.2%}",
            f"Linhas exatas: {resultado['exatas']}/{resultado['linhas']}",
        ]
        for grupo, item in sorted(resultado["grupos"].items()):
            linhas.append(f"{grupo}: CER {item['cer']:.2%}, "
                          f"WER {item['wer']:.2%}, "
                          f"exatas {item['exatas']}/{item['linhas']}")
        messagebox.showinfo("Avaliação do OCR de linhas", "\n".join(linhas))

    def abrir_revisao_dataset_linhas(self):
        if self.janela._busy("A revisão do dataset"):
            return
        if not (pasta_de_linhas() / "rec_gt.txt").exists():
            messagebox.showinfo("Revisão", "Ainda não existe dataset de linhas.")
            return
        from ui.dialogo_revisao_linhas import DialogoRevisaoLinhas
        DialogoRevisaoLinhas(self.janela)

    def abrir_relatorio_ocr_linhas(self):
        # O mesmo arquivo que `linha_trainer.treinar` grava — antes o do cwd,
        # que não era o do treino quando o app abria por atalho.
        caminho = str(relatorio_de_linhas())
        if not os.path.exists(caminho):
            messagebox.showinfo("Relatório", "Ainda não existe relatório de treino de linhas.")
            return
        try:
            os.startfile(caminho)
        except OSError as exc:
            messagebox.showerror("Relatório", f"Não foi possível abrir o relatório:\n{exc}")

    def _treinar_rede(self, epochs, ja_corrigiu=False):
        """
        A tarefa do treino, separada para poder ser refeita.

        `ja_corrigiu` corta a volta: se a base voltou a ser recusada logo
        depois de ter sido saneada, o problema não é do tipo que a correção
        automática resolve, e insistir seria um laço.
        """
        from core.services.learning_service import DatasetInvalido

        def trabalho(h):
            # should_stop é consultado a cada época: cancelar mantém salvo o
            # melhor modelo obtido até ali.
            return self.janela.learning_service.train_neural(
                epochs=epochs,
                callback=h.log,
                should_stop=lambda: h.cancelled,
            )

        def falhou(exc):
            """A base recusada vira uma pergunta com resposta, não um traceback."""
            if not isinstance(exc, DatasetInvalido) or ja_corrigiu:
                return False
            corrigiveis = self.janela._corrigiveis(exc.problemas)
            if not corrigiveis:
                return False

            linhas = [f"O treino não começou: {len(exc.problemas)} problema(s) "
                      "na base."]
            linhas += [f"  {p}" for p in exc.problemas[:10]]
            if len(exc.problemas) > 10:
                linhas.append(f"  ... e mais {len(exc.problemas) - 10}")
            linhas.append("")
            linhas.append(self.janela.EXPLICACAO_DA_CORRECAO)
            linhas.append("")
            linhas.append("Corrigir e treinar?")

            if messagebox.askyesno("Treinar rede neural", "\n".join(linhas),
                                   icon="warning"):
                # checar_pngs=False para casar com a validação que recusou o
                # treino: ela é a rápida, que não lê arquivo nenhum.
                self.janela.corrigir_base_treino(
                    checar_pngs=False,
                    depois=lambda: self.janela._treinar_rede(epochs, ja_corrigiu=True))
            return True

        def concluir(sucesso):
            if not sucesso:
                messagebox.showerror("Erro", "Falha no treinamento.")
                return

            # O relatório da F1.3 é o único lugar onde a qualidade do modelo
            # aparece medida sobre dados que ele não viu. Não adianta gravá-lo e
            # deixar o usuário sem saber que existe.
            # A ressalva agora é de outro arquivo: a que o usuário já fechou
            # era do modelo anterior. O treino calibra sozinho no fim (F27), e
            # quando ele consegue não há o que avisar — `_avisar_do_modelo` só
            # abre a boca se a temperatura ficou neutra, que é o caso de quem
            # não tem página rotulada. O log da tarefa já disse qual dos dois
            # aconteceu; isto é para quem não leu o log.
            self.janela._modelo_conferido = False

            relatorio = self.janela.learning_service.caminho_relatorio()
            if os.path.exists(relatorio):
                if messagebox.askyesno(
                    "Treinamento concluído",
                    "Treinamento concluído! Agora você pode usar "
                    "'Detectar e Preencher (Neural)'.\n\n"
                    "Deseja abrir o relatório de validação?"
                ):
                    self.janela.abrir_relatorio_treino()
            else:
                messagebox.showinfo(
                    "Sucesso",
                    "Treinamento concluído!\nAgora você pode usar "
                    "'Detectar e Preencher (Neural)'."
                )
            self.janela._avisar_do_modelo()

        self.janela._run_task("Treinar rede neural", trabalho, concluir,
                       indeterminado=True, ao_falhar=falhou)

    def treinar_modelo_diagramas(self):
        """
        Refaz o modelo das peças dos diagramas com as amostras de hoje (F8.3).

        Roda em thread, e desde a F7.4 isso deixou de ser precaução: eram 0,3 s
        para 357 amostras com o banco de vizinhos, e são ~40 s para treinar as
        duas redes — a que mede e a que fica. Daí o `progresso` chegar ao log da
        janela: quarenta segundos sem sinal de vida parecem travamento.
        """
        from core import treino_diagrama

        def trabalho(h):
            h.log("Lendo as amostras...")
            return treino_diagrama.treinar(progresso=h.log)

        def concluir(relatorio):
            if not relatorio.total:
                messagebox.showinfo(
                    "Treinar modelo de diagramas",
                    "Nenhuma amostra em training_data_diagrama/.\n\n"
                    "As amostras saem da janela de diagramas: corrija as casas "
                    "erradas e use 'Guardar amostras'.")
                return
            graves = [p for p in relatorio.problemas if p.grave]
            messagebox.showinfo(
                "Treinar modelo de diagramas",
                relatorio.texto()
                + ("\n\nCorrija os erros acima: eles vão para o modelo."
                   if graves else ""))
            medido = (f"{relatorio.acerto:.1%} em {relatorio.diagramas_de_teste} "
                      f"diagramas fora do treino" if relatorio.casas_de_teste
                      else "sem medição (base pequena demais para separar teste)")
            self.janela.status.set(
                f"Modelo de diagramas: {relatorio.total} amostras, {medido}.")

        self.janela._run_task("Treinar modelo de diagramas", trabalho, concluir,
                       indeterminado=True)

    def abrir_relatorio_treino(self):
        """Abre o relatório do último treino no aplicativo padrão do sistema."""
        caminho = self.janela.learning_service.caminho_relatorio()
        if not os.path.exists(caminho):
            messagebox.showinfo(
                "Relatório de treino",
                "Nenhum relatório encontrado.\n\n"
                "Ele é gravado ao final de 'Treinar Rede Neural', desde que a "
                "base seja grande o bastante para separar um conjunto de "
                "validação."
            )
            return
        try:
            os.startfile(caminho)   # noqa: S606 — Windows; é o app do usuário
        except (AttributeError, OSError) as e:
            messagebox.showinfo("Relatório de treino",
                                f"O relatório está em:\n{caminho}\n\n({e})")

    def run_general_neural_training(self):
        if self.janela._busy("O processamento em lote"):
            return

        if not self.janela.learning_service.load_predictor():
            # O motivo, e não "não encontrado": um par .pth/.json trocado
            # mandaria o usuário procurar um arquivo que está lá (F7.3).
            messagebox.showerror("Modelo neural",
                                 self.janela.learning_service.motivo_do_modelo())
            return

        # Depois da carga, e não antes: aqui ela já roda na thread da UI, então
        # a conferência não acrescenta espera nenhuma.
        self.janela._avisar_do_modelo()

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
                    # Sem tratamento especial de Poppler desde a F2.2: o PDF é
                    # renderizado pelo PyMuPDF, que não depende de binário
                    # externo. O que sobrar aqui é erro no arquivo, e a mensagem
                    # do próprio PyMuPDF diz mais que um texto genérico.
                    # O mesmo dpi de `load_page`, e não um 200 solto: este
                    # caminho alimenta o treino, e treinar numa escala e
                    # reconhecer noutra é descasar as duas.
                    pages = self.janela.pdf_service.convert_pdf_to_images(
                        fpath, dpi=DPI_PADRAO)
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

            return self.janela.learning_service.batch_extract_and_classify(
                images, output_dir, progress_callback=progresso
            )

        def concluir(total_crops):
            messagebox.showinfo(
                "Concluído",
                f"Processamento finalizado!\n{total_crops} caracteres extraídos em:\n{output_dir}"
            )

        self.janela._run_task("Processamento em lote", trabalho, concluir)

    def import_character_images(self):
        if self.janela._busy("A importação"):
            return

        src_dir = filedialog.askdirectory(title="Selecione a pasta de ORIGEM")
        if not src_dir:
            return

        def trabalho(h):
            h.log("Copiando imagens...")
            return self.janela.learning_service.import_character_images(src_dir)

        def concluir(count):
            messagebox.showinfo(
                "Sucesso",
                f"Importação concluída.\n{count} imagens importadas para training_data."
            )

        self.janela._run_task("Importar imagens", trabalho, concluir, indeterminado=True)
