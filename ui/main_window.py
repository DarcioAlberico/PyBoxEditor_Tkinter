import os
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import replace
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image

from core import (coleta, exportar, formato_box, leitura_de_linha, lexico,
                  livro, nags, vertical)
from core.chess_pdf_processor import (CHESS_UNICODE, analisar_substituicao,
                                      substitute_chess_glyphs)
from core.mapa_glifos import caminhos_do_relatorio as caminhos_do_mapa
from core.mapa_glifos import corrigir_mapeamento
from core.relatorio_pdf import caminhos_do_relatorio
from core.searchable_pdf import contar_paginas_com_texto, gerar_pdf_pesquisavel
from core.box_model import SEM_MARGEM, BoxEntry
from core.services.box_service import BoxService, faixas_de_linha
from core.services.ocr_service import OCRService
from core.services.pdf_service import DPI_PADRAO, PDFService
from core.services.learning_service import LearningService
from core.services.history_service import HistoryManager
from core.services.document_service import DocumentSession, _GravadorAssincrono
from core.services.task_service import BackgroundTask

from ui.canvas_view import CanvasView
from ui.dialogo_diagrama import DialogoDiagrama
from ui.dialogo_semelhantes import DialogoSemelhantes
from ui.status_bar import StatusBar
from ui import confidence as conf_ui
from ui import fontes


#: Confiança da cadeia acima da qual a leitura por linha **não** encosta no box.
#:
#: A trava da F18, e sem ela a linha estraga mais do que conserta — em qualquer
#: um dos dois caminhos. **O valor certo depende de quão forte é a âncora**, e
#: por isso são dois. Medido em 2.278 caracteres, **com o modelo calibrado**
#: (T = 2,1916; ver F22 e a nota de temperatura no fim):
#:
#:     trava        com a rede    híbrido (k-NN)
#:     sem linha        97,37%           94,82%
#:     0,60             97,45%           95,17%
#:     0,70             97,45%           95,22%
#:     0,80             97,45%           95,22%
#:     0,85             97,28%           95,26%
#:     0,95             97,15%           95,08%
#:     sempre           90,34%           90,25%
#:
#: **A âncora mais fraca é onde a linha rende.** No caminho com a rede o ganho é
#: pequeno por construção — ela responde 96,7% dos boxes e sobra pouco onde a
#: linha tem o que dizer, e o resultado é +0,08 ponto (3 boxes). No híbrido, sem
#: rede, o ganho é cinco vezes maior: +0,44 ponto, 42 boxes.
#:
#: Em nenhum dos dois "sempre" serve: seria pôr o EasyOCR (89,5%) por cima de
#: quem já lia melhor, e custa 7,0 e 4,6 pontos respectivamente.
#:
#: **Sobre a temperatura, porque estes números dependem dela.** A calibração da
#: F1.9 (`calibrar_modelo.py --gravar`) desloca a escala de confiança inteira, e
#: recalibrar obriga a remedir isto. Foi feito: em T = 1 o corte era um ponto
#: (0,70, com 0,85 neutro); em T = 2,19 virou um **platô de 0,60 a 0,80**, e
#: 0,85 passou a fazer mal ao caminho com a rede. O 0,70 ficou porque é o meio
#: do platô, e não porque era o valor de antes.
#:
#: **Remedido na F25**, contra o treino de 14/08 e a calibração T = 2,1682, em
#: 10.484 caracteres — e este sobreviveu inteiro, ao contrário do
#: `NEURAL_THRESHOLD`:
#:
#:     trava       acerto   trocados
#:     sem linha   97,37%          0
#:     0,60        97,41%         15
#:     0,70        97,43%         19
#:     0,80        97,31%         42
#:     sempre      89,74%        888
CONF_MAXIMA_PARA_A_LINHA = 0.70

#: Confiança mínima para o k-NN responder sozinho, no caminho híbrido (F23).
#:
#: Era 0,85, e o 0,85 nunca tinha sido medido: veio de ser o mesmo número da
#: trava da linha, que por sua vez era 0,85 por ser o `learner_threshold`. Os
#: dois se justificavam um pelo outro e nenhum dos dois pela página.
#:
#: `medir_cadeia.py` põe o k-NN e o EasyOCR **no mesmo box**, separados por
#: faixa de confiança do k-NN. Medido em 10.481 caracteres de 10 páginas:
#:
#:     confiança do k-NN   boxes    k-NN   EasyOCR
#:     0,00 – 0,50           395   51,9%     47,6%
#:     0,50 – 0,70           839   98,6%     62,7%
#:     0,70 – 0,80           808   97,8%     65,7%
#:     0,80 – 0,85           218   99,1%     85,8%
#:     0,85 – 0,90           216   98,6%     87,0%
#:     0,95 – 0,99         2.006   97,5%     79,1%
#:     0,99 – 1,00         5.972   99,7%     74,6%
#:
#: **O k-NN ganha em toda faixa, e nas de 0,50 a 0,85 ele vai a 98%** — acima da
#: própria faixa 0,95–0,99. A confiança `1 - distância/2000` mal ordena
#: qualidade no meio da escala, e o corte em 0,85 mandava 21,6% dos boxes para o
#: pior dos dois classificadores.
#:
#: **A fórmula foi trocada por margem e a troca foi desfeita (F24)** — 97,32%
#: contra 97,62%. Ela ordena melhor, e é justamente por isso que perde: o que o
#: roteamento pergunta não é "o vencedor está à frente?" e sim "esta base já viu
#: algo assim?". Antes de mexer aqui de novo, ver a F24 no ROADMAP.
#:
#: A varredura, com a trava acompanhando:
#:
#:     limiar   10 páginas   as 2 limpas
#:     0,00         97,53%        95,73%
#:     0,30         97,62%        95,68%
#:     0,50         97,36%        95,45%
#:     0,70         95,53%        92,65%
#:     0,85         93,72%        87,68%
#:     0,95         94,11%        88,51%
#:
#: **0,30 e não 0,00.** De 0,00 a 0,50 o resultado é platô; o que decide a borda
#: é a faixa mais baixa, onde nas páginas limpas o k-NN faz 46,7% contra 48,9% —
#: cara ou coroa, e a única em que ele não ganha. O 0,30 o mantém fora dela.
#:
#: **"As 2 limpas" é a coluna que vale para livro novo.** `training_data` foi
#: colhida das próprias páginas rotuladas, e onde o k-NN responde acima de 0,99
#: ele está consultando a própria cópia, não generalizando — em duas páginas
#: isso é 97% e 95% dos boxes. As duas menos contaminadas (9,5% e 27,1%) sobem
#: **8,00 pontos** com esta mudança, contra 3,90 do conjunto: o ganho não era
#: vazamento, e cresce justamente onde a base não ajuda.
#:
#: **Remedido na F46, com a base em 86.897 referências contra as 73.900 da F24,
#: e o 0,30 fica.** A varredura fina:
#:
#:     limiar   âncora   com a linha   corte em distância
#:     0,10     97,57%        97,57%                1.800
#:     0,20     97,67%        97,67%                1.600
#:     0,30     97,61%        97,64%                1.400
#:     0,40     97,38%        97,55%                1.200
#:     0,50     97,01%        97,37%                1.000
#:
#: O pico volta a cair em 0,20, como na F24, e **isso não é confirmação
#: independente**: as páginas são as mesmas, só a base de referência cresceu, e
#: os boxes que separam 0,20 de 0,30 são em grande parte os mesmos boxes.
#:
#: O que decide é a tabela por distância (F35), que a F24 não tinha. Entre 1.400
#: e 1.600 de corte entra uma faixa de **34 boxes** em que o k-NN faz 58,8%
#: contra 47,1% do EasyOCR — 4 caracteres, com erro padrão de ~3 boxes. É onde a
#: curva sobe e é o único ponto em disputa, e o vencedor dele não está
#: estabelecido. Já a queda de 0,10 é sólida: o corte em 1.800 engole a faixa de
#: 1.700–2.000, em que o k-NN faz 24,4% contra 56,1%.
LEARNER_THRESHOLD_HIBRIDO = 0.30

#: A trava da linha no caminho híbrido, **e ela é o mesmo número de propósito**.
#:
#: A razão é mecânica, e não coincidência numérica: a trava existe para a linha
#: agir exatamente nos boxes em que o k-NN se recusou a responder, e quem define
#: essa recusa é o limiar acima. Amarrados aqui para que mover um mova o outro —
#: separá-los foi medido e é o pior dos mundos. Com o limiar em 0,30 e a trava
#: deixada em 0,85, nas duas páginas limpas:
#:
#:     trava       acerto   trocados
#:     sem linha   95,68%          0
#:     0,30        95,68%          3
#:     0,60        95,22%         22
#:     0,70        93,57%         65
#:     0,85        91,54%        112
#:     sempre      88,01%        209
#:
#: São **7 consertos contra 97 quebras**, saldo de −90 caracteres: o EasyOCR por
#: linha (89,5%) passando por cima de um k-NN que agora lê a 95,7%. É a lei da
#: F21 — a linha rende na proporção inversa da força da âncora — vista do outro
#: lado, e é por isso que fortalecer a âncora **tira** trabalho da linha em vez
#: de somar com ele.
CONF_MAXIMA_PARA_A_LINHA_HIBRIDO = LEARNER_THRESHOLD_HIBRIDO

#: Confiança mínima para a rede responder sozinha, sem passar ao k-NN.
#:
#: **Este número é por modelo, e já se moveu duas vezes.** Era 0,8; a F22 mediu
#: contra a calibração daquele treino e baixou para 0,7; a F25 remediu contra o
#: treino de 14/08 (210 classes, T = 2,1682) e devolveu para 0,8. Não é
#: indecisão: é a propriedade do limiar. Ele compara confiança, e a escala da
#: confiança é do conjunto de pesos — o próximo treino invalida esta tabela em
#: silêncio, como invalidou as duas anteriores.
#:
#: Medido em 10.484 caracteres das 10 páginas rotuladas (F25):
#:
#:     limiar   acerto    rede /  k-NN / OCR
#:     0,40     97,32%   10.405 /    5 /  26
#:     0,60     97,43%   10.368 /   32 /  63
#:     0,70     97,43%   10.325 /   54 /  86
#:     0,80     97,52%   10.168 /  168 / 125
#:     0,90     97,10%    9.904 /  293 / 245
#:
#: **0,80 é pico, e não meio de platô** — cai dos dois lados. São 9 caracteres
#: de vantagem sobre 0,70, pouco por si só; o que decide é que a composição
#: aponta no mesmo sentido. A 0,80 o k-NN vê 168 boxes em vez de 54, e é para
#: isso que ele está na cadeia: nos casos difíceis ele acerta 88,5% contra 72,4%
#: da rede sozinha (ver `CharacterLearner`). A 0,40 a segunda opinião some quase
#: inteira e o acerto cai junto.
#:
#: Reproduzir: `python medir_cadeia.py --neural --rede 0.4 0.6 0.7 0.8 0.9`.
NEURAL_THRESHOLD = 0.80

#: Confiança mínima para o k-NN responder sozinho **no caminho com a rede**, e
#: no PDF pesquisável, que usa a mesma cadeia.
#:
#: Era o literal `0.9` escrito dentro das duas ações, em duas cópias, e **sem
#: tabela** — a última situação da F23 ainda de pé quando a F39 olhou. O irmão
#: dele no híbrido era `0.85` pela mesma razão (ninguém tinha medido), a F23
#: mediu e ele caiu para 0,30. Aqui a varredura deu o mesmo veredito.
#:
#: Medido em 10.504 caracteres das 10 páginas rotuladas, com a trava da linha
#: presa em 0,70, que é onde produção a deixa (F39):
#:
#:     limiar   âncora   com a linha
#:     0,00     97,46%        97,51%
#:     0,15     97,47%        97,51%
#:     0,20     97,48%        97,51%
#:     0,30     97,44%        97,50%
#:     0,50     97,42%        97,48%
#:     0,70     97,32%        97,43%
#:     0,90     97,03%        97,13%   <- era este
#:
#: **De 0,00 a 0,30 é platô** — um caractere separa as seis linhas —, e o 0,90
#: custava 0,38 ponto, 40 caracteres. A composição diz o mecanismo: em 0,90 o
#: k-NN respondia 165 boxes acertando 96,4% e 163 caíam no EasyOCR, que acerta
#: **46,0%**. Baixar o limiar move box do pior classificador para o melhor.
#:
#: **Dentro do platô o número sai do mecanismo, e não do empate.** A confiança é
#: `1 - d/2000`, então o corte em distância é `2000·(1-t)`; e a tabela por
#: distância (F35) diz que o k-NN só perde do EasyOCR acima de ~1.700. Em 0,30 o
#: corte cai em 1.400, dentro da região em que ele ganha; em 0,00 cai em 2.000, e
#: aí ele também leva a faixa de 1.700–2.000, onde perde de 24,4% a 56,1%. Hoje
#: isso são ~40 boxes e não move o total — numa base pior, move.
#:
#: Que dê no mesmo número do híbrido é consequência, **não é a razão**. A F23
#: desmontou exatamente o raciocínio inverso: lá os dois limiares se
#: justificavam um pelo outro e nenhum pela página.
#:
#: Reproduzir:
#: `python medir_cadeia.py --neural --learner 0.0 0.15 0.2 0.3 0.5 0.7 0.9`.
LEARNER_THRESHOLD_NEURAL = 0.30


# Símbolos do "Key to symbols used" destes livros, por família. O agrupamento é o
# da própria página do livro, e serve para achar o botão: numa fileira única de 23
# o olho procura, em quatro grupos ele vai direto.
#
# **Todos foram conferidos contra a fonte, e não é zelo excessivo.** `Segoe UI
# Symbol` desenha os 23; `MS Gothic`, que é a candidata seguinte em
# `chess_pdf_processor.CHESS_FONT_CANDIDATES`, não tem `⩲`, `⩱`, `⌓` — nem o `⨀`
# que já estava aqui antes. Glifo ausente vira caixa vazia sem aviso, que é o
# defeito do `·` da SPEC §4.2.
NAGS_POR_FAMILIA = [
    ("Avaliação", [
        ("⩲", "Brancas ligeiramente melhor"), ("⩱", "Negras ligeiramente melhor"),
        ("±", "Brancas melhor"), ("∓", "Negras melhor"),
        ("+-", "Brancas vencem"), ("-+", "Negras vencem"),
        ("=", "Igualdade"), ("∞", "Posição incerta"),
    ]),
    ("Lance", [
        ("!", "Boa jogada"), ("!!", "Excelente"), ("?", "Erro"), ("??", "Erro grave"),
        ("!?", "Interessante"), ("?!", "Duvidoso"),
        ("□", "Lance único"), ("#", "Mate"),
    ]),
    ("Ideia", [
        # `⯹` é o U+2BF9, um igual sobre um infinito — o desenho impresso, que a
        # "Key to symbols used" destes livros põe logo acima do `∞` sozinho de
        # *unclear*. Escreveu-se `≡` aqui enquanto nenhuma das 559 famílias de
        # `C:\Windows\Fonts` o desenhava; quem o desenha é a `NotoSansSymbols2`
        # empacotada em `assets/fonts/`, que `ui.fontes` registra no processo
        # para o Tk alcançar. Trocá-lo de novo é mexer numa linha desta tabela.
        ("⯹", "Com compensação"), ("⇄", "Com contrajogo"),
        ("⌓", "Melhor é"), ("Δ", "Com ideia de"), ("⨀", "Zugzwang"),
    ]),
    ("Lado", [
        ("△", "Brancas jogam"), ("▼", "Negras jogam"),
    ]),
]

#: A lista achatada, que é o que o menu de contexto e os testes consomem.
NAGS = [par for _, familia in NAGS_POR_FAMILIA for par in familia]

# As figurinas de peça, ao lado dos NAGs e pela mesma razão que eles existem:
# são caracteres que o teclado não tem e que aparecem em quase toda linha de
# notação. Sem o botão, escrever um `♗` é procurar o codepoint.
#
# **São 5, e não 12**, e a razão é a mesma de `searchable_pdf.PECAS`, medida no
# material real: peão não ganha letra em notação algébrica (`e4`, nunca com
# figurina), e estes livros usam **um** conjunto de figurinas para os dois lados
# — na linha "17...♞e5 18.♛c2 ♞a6 19.♞c4" o lance 17... é das pretas e o 19. das
# brancas, e os dois cavalos usam o mesmo glifo. São exatamente as 5 classes que
# o modelo aprendeu (`sym_9812` a `sym_9816` na base de treino).
#
# Os codepoints saem de `CHESS_UNICODE` em vez de serem redigitados aqui: é a
# mesma tabela que `resolve_chess_font` valida contra as fontes do disco, e uma
# segunda cópia poderia divergir dela sem ninguém notar.
PECAS_RAPIDAS = ("Peças", list(zip(
    CHESS_UNICODE[:5], ("Rei", "Dama", "Torre", "Bispo", "Cavalo"))))


class MainWindow(tk.Frame):

    ORIGEM_TODAS = "(todas)"
    ORIGEM_VAZIA = "(sem)"

    # Quantas alterações entre gravações do rascunho. Baixo demais escreve à
    # toa; alto demais perde trabalho num travamento. 25 é ~meia linha de texto.
    AUTOSAVE_A_CADA = 25

    def __init__(self, parent):
        super().__init__(parent)

        self.parent = parent
        self.image = None          # PIL.Image
        self.image_path = None
        self.boxes = []            # lista de BoxEntry da página atual
        self.selected_index = -1
        self.current_pdf_page = 0

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
        # A ressalva do modelo já foi mostrada nesta sessão? Ver
        # `_avisar_do_modelo`: é sobre o arquivo, então uma vez basta.
        self._modelo_conferido = False

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

            self._mudancas_desde_autosave += 1
            if self._mudancas_desde_autosave >= self.AUTOSAVE_A_CADA:
                self._gravar_rascunho()
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

        descartar = messagebox.askyesno(
            "Trabalho não salvo",
            f"Há alterações não salvas em {onde}.\n"
            f"Total na sessão: {self.session.total_boxes()} box(es).\n\n"
            "Use 'Salvar todas as páginas' para gravar tudo.\n\n"
            "Descartar as alterações e continuar?",
            icon="warning",
        )
        if descartar:
            # O usuário aceitou perder: manter o rascunho o ressuscitaria na
            # próxima abertura, o que seria pior que a perda escolhida.
            self._descartar_rascunho()
        return descartar

    def _gravar_rascunho(self):
        """
        Agenda a gravação do rascunho e zera o contador.

        O snapshot é montado aqui (thread da UI) porque precisa de uma visão
        consistente dos boxes; o encode em JSON e a escrita vão para a thread
        do gravador. Medido em 40 mil boxes: 23 ms aqui contra 31 ms lá.
        """
        if self.session is None:
            return
        self._mudancas_desde_autosave = 0
        if self.session.autosave(self._gravador):
            erro = self._gravador.ultimo_erro
            if erro is not None:
                self.status.set(f"Falha ao gravar rascunho: {erro}")

    def _descartar_rascunho(self):
        """Some com o rascunho: ou o trabalho foi salvo de verdade, ou o
        usuário escolheu descartá-lo."""
        if self.session is not None:
            self.session.remover_autosave()
        self._mudancas_desde_autosave = 0

    def _tentar_recuperar(self):
        """
        Oferece o rascunho de um travamento anterior, se houver.

        Devolve True se algo foi recuperado.
        """
        if self.session is None:
            return False
        payload = DocumentSession.ler_autosave(self.session.path)
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
            self.session.remover_autosave()
            return False

        recuperadas = self.session.aplicar_payload(payload)
        self.status.set(f"Rascunho recuperado: {recuperadas} página(s).")
        return True

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

    def salvar_rascunho_agora(self):
        """Força a gravação do rascunho (menu / Ctrl+B)."""
        if self.session is None or not self.session.pages_with_boxes():
            self.status.set("Nada para gravar no rascunho.")
            return "break"
        self._gravar_rascunho()
        self.status.set(f"Rascunho gravado em {os.path.basename(self.session.sidecar())}.")
        return "break"

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

        self.lbl_filtro = tk.Label(filtros, text="", fg="gray20")
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
        tk.Button(editor, text="Proximo >>", command=self.apply_char_and_next).grid(row=0, column=3, padx=5)
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
                tk.Label(linha, text=titulo, fg="gray40").pack(side="left",
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
                self.lbl_tooltip = tk.Label(linha, text="", fg="gray")
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
            tk.Label(legenda, text=texto, fg="gray20").pack(side="left", padx=(0, 8))

        # O l\u00e9xico entra com um tra\u00e7o, n\u00e3o com um quadrado: no canvas ele \u00e9 um
        # sublinhado sob o box, e a legenda tem de parecer com o que se v\u00ea l\u00e1.
        cor_lex, texto_lex = conf_ui.LEGENDA_LEXICO
        tk.Label(legenda, text="\u2581", fg=cor_lex).pack(side="left")
        tk.Label(legenda, text=texto_lex, fg="gray20").pack(side="left")

        self.lbl_revisao = tk.Label(self.nav_frame, text="", fg="gray20")
        self.lbl_revisao.pack(side="left", padx=10)

        # Último a ser empacotado é o primeiro a ser cortado — e é o que menos
        # falta faz: quantas páginas têm boxes e quantas estão por salvar já
        # aparece no título da janela.
        self.lbl_sessao = tk.Label(self.nav_frame, text="", fg="gray30")
        self.lbl_sessao.pack(side="left", padx=6)

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
        m_file.add_command(label="Abrir...", accelerator="Ctrl+O",
                           command=self.abrir_documento)
        m_file.add_command(label="Abrir imagem...", command=self.open_image)
        m_file.add_command(label="Abrir PDF...", command=self.open_pdf)
        m_file.add_command(label="Salvar .box (página atual)", accelerator="Ctrl+S",
                           command=self.save_box_file)
        m_file.add_command(label="Salvar todas as páginas...", accelerator="Ctrl+Shift+S",
                           command=self.save_all_pages)
        m_file.add_command(label="Carregar .box", command=self.load_box_file)
        m_file.add_separator()
        m_file.add_command(label="Gravar rascunho agora", accelerator="Ctrl+B",
                           command=self.salvar_rascunho_agora)
        m_file.add_separator()
        m_file.add_command(label="Sair", command=self._on_close)
        menubar.add_cascade(label="Arquivo", menu=m_file)

        self._build_menu_notacao(menubar)

        m_tools = tk.Menu(menubar, tearoff=0)
        m_tools.add_command(label="Gerar boxes (OpenCV)", command=self.generate_boxes_opencv)
        m_tools.add_command(label="Preencher caracteres (OCR)", command=self.auto_fill_characters)
        m_tools.add_command(label="Preencher caracteres (EasyOCR)", command=self.auto_fill_characters_easyocr)
        m_tools.add_command(label="Preencher caracteres (EasyOCR por linha)",
                            command=self.auto_fill_characters_linha)
        m_tools.add_separator()
        m_tools.add_command(label="Detectar e Preencher (EasyOCR)", command=self.generate_and_fill_easyocr)
        m_tools.add_command(label="Detectar e Preencher (EasyOCR por linha)",
                            command=self.generate_and_fill_linha)
        m_tools.add_command(label="Detectar e Preencher (Híbrido/Ref)", command=self.generate_and_fill_combined)
        m_tools.add_command(label="Detectar e Preencher (Neural)", command=self.generate_and_fill_neural)
        m_tools.add_separator()
        m_tools.add_command(label="Aprender com Página Atual (Coletar)", command=self.learn_from_current_page)
        m_tools.add_command(label="Verificar base de treino...",
                            command=self.verificar_base_treino)
        m_tools.add_command(label="Treinar Rede Neural", command=self.train_neural_network)
        m_tools.add_command(label="Relatório do último treino...",
                            command=self.abrir_relatorio_treino)
        m_tools.add_separator()
        m_tools.add_command(label="Validar notação de xadrez...",
                            command=self.validar_notacao)
        m_tools.add_command(label="Exportar partidas em PGN...",
                            command=self.exportar_pgn)
        m_tools.add_command(label="Ler posição dos diagramas...",
                            command=self.extrair_diagramas)
        m_tools.add_command(label="Treinar modelo de diagramas...",
                            command=self.treinar_modelo_diagramas)
        m_tools.add_separator()
        m_tools.add_command(label="Treinamento Geral Neural (Batch)", command=self.run_general_neural_training)
        m_tools.add_command(label="Importar Imagens de Caracteres", command=self.import_character_images)
        m_tools.add_separator()
        m_tools.add_command(label="Aplicar a todos os semelhantes...",
                            accelerator="Ctrl+E",
                            command=self.aplicar_aos_semelhantes)
        m_tools.add_command(label="Dividir box selecionado", accelerator="Ctrl+D",
                            command=self.split_selected_box)
        m_tools.add_command(label="Excluir box selecionado", accelerator="Del",
                            command=self.delete_selected_box)
        m_tools.add_separator()
        m_tools.add_command(label="Substituir Glifos de Xadrez em PDF (Texto)...", command=self.substitute_chess_glyphs_action)
        m_tools.add_command(label="Gerar PDF Pesquisável (OCR)...",
                            command=self.gerar_pdf_pesquisavel_action)
        m_tools.add_command(label="Substituir Glifos em PDF Escaneado (Neural)...",
                            command=self.substitute_glyphs_neural_action)
        m_tools.add_command(label="Corrigir Mapeamento de Caracteres do PDF...",
                            command=self.corrigir_mapeamento_action)
        m_tools.add_command(label="Exportar Livro (EPUB/DOCX, só nosso OCR)...",
                            command=self.exportar_livro_action)
        m_tools.add_command(label="Criar Recortes para Revisão...",
                            command=self.criar_recortes_action)
        m_tools.add_command(label="Promover recortes revistos para a base...",
                            command=self.promover_revisao_action)
        menubar.add_cascade(label="Ferramentas", menu=m_tools)

    def _build_menu_notacao(self, menubar):
        """
        O menu **Notação**: a tabela completa de NAGs do padrão PGN.

        A barra rápida tem os 23 símbolos do "Key to symbols used" destes livros,
        que é o que se digita o dia inteiro. Este menu tem os 169 do padrão, que é
        outra coisa: serve para o símbolo que aparece uma vez em duzentas páginas e
        para saber que `$26` existe e chama-se "vantagem de espaço".

        **Em submenus por família, e não em coluna única.** Cento e sessenta e nove
        itens a ~20 px pedem 3.400 px de altura; o Tk não avisa que não cabe — ele
        quebra o menu em colunas lado a lado, e a lista deixa de ter ordem visível.
        Vinte e duas famílias cabem numa coluna de 440 px.

        **O item só fica clicável se houver o que escrever no box.** Duas razões
        para não haver, e o rótulo diz qual: `—` no lugar do símbolo é NAG que o
        padrão definiu sem forma impressa (`$24`, "leve vantagem de espaço" — 121
        dos 169 são assim); "(sem fonte)" é símbolo que existe mas que nenhuma
        fonte do disco desenha, medido em `nags.sem_glifo()`. Deixar o segundo caso
        clicável escreveria no box um caractere que vira retângulo vazio no PDF sem
        erro nenhum no caminho — o defeito do `·` da SPEC §4.2.
        """
        m_nag = tk.Menu(menubar, tearoff=0)

        # Uma medição só para as 169 entradas (17 ms), em vez de uma por item.
        ausentes = nags.sem_glifo()

        for titulo, familia in nags.FAMILIAS:
            sub = tk.Menu(m_nag, tearoff=0)
            for nag in familia:
                if nags.desenhavel(nag, ausentes):
                    sub.add_command(label=nags.rotulo(nag),
                                    command=lambda s=nag.simbolo: self.apply_nag(s))
                else:
                    sufixo = "   (sem fonte)" if nag.simbolo else ""
                    sub.add_command(label=nags.rotulo(nag) + sufixo,
                                    state="disabled")
            m_nag.add_cascade(label=titulo, menu=sub)

        menubar.add_cascade(label="Notação", menu=m_nag)

    def _build_context_menu(self):
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Aplicar a todos os semelhantes...",
                                      accelerator="Ctrl+E",
                                      command=self.aplicar_aos_semelhantes)
        self.context_menu.add_separator()
        for k, (_, familia) in enumerate(NAGS_POR_FAMILIA):
            if k:
                self.context_menu.add_separator()
            for nag_char, desc in familia:
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
            self.lbl_modo.config(text="  ⌨ DIGITAÇÃO  ", bg="#FFD400", fg="black")
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
        """Backspace volta um box no modo digitação; fora dele, exclui."""
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
        self._esquecer_lexico()
        self.current_pdf_page = 0
        self._mudancas_desde_autosave = 0
        recuperou = self._tentar_recuperar()

        self.image = img.convert("L")
        self.image_path = path
        self.boxes = self.session.boxes_for(0)
        self.selected_index = -1

        self._update_nav_controls()

        # Zerar o histórico ao trocar de documento: sem isso, um undo logo após
        # abrir traria de volta os boxes da imagem anterior.
        self.history.reset()

        box_path = os.path.splitext(path)[0] + ".box"
        if recuperou:
            # O rascunho é mais recente que o .box em disco; carregá-lo por
            # cima desfaria justamente o que se acabou de recuperar.
            self.history.snapshot(self.boxes, self.selected_index)
            self.update_sidebar()
            self.update_canvas()
        elif os.path.exists(box_path):
            self._load_box_from_path(box_path, marcar_sujo=False)
        else:
            self.history.snapshot(self.boxes, self.selected_index)
            self.update_sidebar()
            self.update_canvas()

        self._update_title()

    #: Extensões que `abrir_documento` reconhece como imagem de página.
    EXTENSOES_DE_IMAGEM = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")

    def abrir_documento(self, path=None):
        """
        Ctrl+O: um diálogo só, para PDF e imagem, decidido pela extensão.

        O menu tem duas entradas separadas porque o usuário às vezes quer
        filtrar a lista, mas um atalho que exigisse escolher o tipo antes de
        ver o arquivo seria pior que não ter atalho.
        """
        if path is None:
            imagens = " ".join("*" + e for e in self.EXTENSOES_DE_IMAGEM)
            path = filedialog.askopenfilename(
                filetypes=[("PDF e imagens", "*.pdf " + imagens),
                           ("Arquivos PDF", "*.pdf"),
                           ("Imagens", imagens),
                           ("Todos", "*.*")])
        if not path:
            return

        if os.path.splitext(path)[1].lower() == ".pdf":
            self.open_pdf(path)
        else:
            self.open_image(path)

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
        self.session = DocumentSession(path, num_pages=num_pages, is_pdf=True,
                                       dpi=DPI_PADRAO)
        self._esquecer_lexico()
        self.boxes = []
        self.current_pdf_page = 0
        self._mudancas_desde_autosave = 0
        self._tentar_recuperar()
        self._load_pdf_page(0, arquivar_atual=False)

    def _load_pdf_page(self, page_index, arquivar_atual=True):
        """
        Troca de página. A renderização vai para a thread de trabalho: medido em
        ~950 ms num PDF sintético simples, e um scan de livro a 300 dpi é bem
        pior. Como virar a página é a operação mais frequente do app, fazer isso
        na thread da UI travava a janela a cada clique.
        """
        if self.task.is_running():
            # Antes isto devolvia em silêncio, contando com os botões
            # desativados para explicar. Não explicam: pelo teclado (PgUp/PgDn)
            # ou pelo campo "ir para", o usuário aperta e **nada acontece** —
            # e a leitura natural é que virar a página está quebrado.
            self.status.set("Aguarde a operação em andamento para virar a página.")
            return

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

    def ir_para_pagina(self, numero=None):
        """
        Vai direto para a página `numero` (1 é a primeira).

        Sem argumento, lê o campo da barra de navegação. O número é o que o
        usuário vê no rótulo — 1 a N —, não o índice interno; trocar um pelo
        outro aqui levaria a página errada sem erro nenhum.
        """
        if not self.pdf_service.is_loaded():
            messagebox.showinfo("Ir para a página", "Nenhum PDF aberto.")
            return

        if numero is None:
            texto = self.entry_pagina.get().strip()
            if not texto:
                return
            try:
                numero = int(texto)
            except ValueError:
                messagebox.showinfo(
                    "Ir para a página",
                    f"{texto!r} não é um número de página.")
                return

        total = self.pdf_service.num_pages
        if not 1 <= numero <= total:
            messagebox.showinfo(
                "Ir para a página",
                f"Este PDF tem {total} página(s); {numero} está fora.")
            return

        if numero - 1 == self.current_pdf_page:
            self.status.set(f"Já está na página {numero}.")
            return

        self._load_pdf_page(numero - 1)

    def _update_nav_controls(self):
        if not self.pdf_service.is_loaded():
            if self.session is not None and self.session.has_boxes(0):
                self.lbl_page_info.config(text=f"{len(self.boxes)} boxes")
            else:
                self.lbl_page_info.config(text="Página: -/-")
            self.btn_prev_page.config(state="disabled")
            self.btn_next_page.config(state="disabled")
            self.entry_pagina.config(state="disabled")
            self.btn_ir.config(state="disabled")
            return

        self.lbl_page_info.config(
            text=f"Página: {self.current_pdf_page + 1}/{self.pdf_service.num_pages}")

        detalhe = []
        if self.session is not None:
            com_boxes = self.session.pages_with_boxes()
            if com_boxes:
                detalhe.append(f"{len(com_boxes)} pág. com boxes, "
                               f"{self.session.total_boxes()} no total")
            sujas = self.session.dirty_pages()
            if sujas:
                detalhe.append(f"{len(sujas)} não salva(s)")
        self.lbl_sessao.config(text="   |   ".join(detalhe))
        self.btn_prev_page.config(
            state="normal" if self.current_pdf_page > 0 else "disabled"
        )
        self.btn_next_page.config(
            state="normal" if self.current_pdf_page < self.pdf_service.num_pages - 1 else "disabled"
        )
        self.entry_pagina.config(state="normal")
        self.btn_ir.config(state="normal")

    # -------------------------------------------------------
    # OpenCV: gerar boxes automáticos
    # -------------------------------------------------------

    def _avisar_do_modelo(self):
        """
        Mostra a ressalva do modelo carregado, **uma vez por sessão**.

        Uma vez porque a ressalva é sobre o arquivo, não sobre a ação: repeti-la
        a cada preenchimento treinaria o usuário a fechá-la sem ler, que é o
        mesmo que não avisar — só que mais irritante. E é modal, e não barra de
        status, porque a única coisa que resolve é uma linha de comando que ele
        precisa ler inteira.

        Chamada da thread da UI. `load_predictor` dentro de `trabalho` roda em
        outra, e `messagebox` de lá é o caminho para uma janela que não fecha.
        """
        if self._modelo_conferido:
            return
        # Marcado **antes** de saber se há ressalva, e não só quando há. Com a
        # marca só no caminho do aviso, um modelo em ordem fazia `load_predictor`
        # rodar na thread da UI a cada ação — e a primeira carga custa ~2 s de
        # janela congelada. Uma conferência por sessão é o que se quer nos dois
        # casos.
        self._modelo_conferido = True
        aviso = self.learning_service.aviso_do_modelo()
        if aviso:
            messagebox.showwarning("Modelo neural", aviso)

    def _arbitro_de_corte(self):
        """
        O classificador que confirma cada corte de glifo colado (F1.5b).

        None quando não há modelo treinado. Não é degradação silenciosa: sem
        árbitro o `generate_boxes_opencv` simplesmente não separa, porque
        separar sem ele é a única configuração que a medição reprova (2,3
        pontos de F1 abaixo de não separar).

        **Este é o único caminho da rede que não chama `_avisar_do_modelo`, e é
        de propósito.** Aqui ela arbitra corte, não lê texto: roda em toda
        `generate_boxes_opencv`, inclusive nas ações híbrida e EasyOCR, onde a
        confiança dela não vira `b.confidence` nem roteia coisa alguma — e o
        recado da F26 fala de fila de revisão e de roteamento da cadeia. A
        margem da F1.5b *é* uma comparação de confiança, então a calibração
        provavelmente mexe na segmentação também; **provavelmente não está
        medido**, e avisar por causa disso seria afirmar o que não se sabe.
        """
        if not self.learning_service.load_predictor():
            return None
        return self.learning_service.predict_neural

    def generate_boxes_opencv(self):
        if self.image is None:
            messagebox.showinfo("Aviso", "Carregue uma imagem primeiro.")
            return

        self.boxes = self.box_service.generate_boxes_opencv(
            self.image, arbitro=self._arbitro_de_corte())
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

        # Simular primeiro é a pergunta certa a fazer antes de reescrever um PDF:
        # a conversão apaga o texto original com um retângulo branco e desenha
        # outro por cima, e depois de gravada não há como comparar com o que
        # havia. O padrão é 'sim' de propósito (F2.3).
        simular = messagebox.askyesnocancel(
            "Simular antes?",
            "Gerar apenas o relatório, sem gravar o PDF?\n\n"
            "Sim — simula e mostra o que seria substituído (nada é alterado).\n"
            "Não — converte de verdade e grava o PDF.\n\n"
            "A conversão reescreve o documento e não tem como ser desfeita."
        )
        if simular is None:
            return

        titulo_saida = ("Onde salvar o relatório da simulação..." if simular
                        else "Salvar PDF Convertido Como...")
        output_pdf = filedialog.asksaveasfilename(
            title=titulo_saida,
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

            return analisar_substituicao(input_pdf, output_pdf,
                                         progress_callback=progresso,
                                         dry_run=simular)

        def concluir(rel):
            cj, cc = caminhos_do_relatorio(output_pdf, rel.dry_run)
            destino = ("Nenhum PDF foi gravado." if rel.dry_run
                       else f"Arquivo salvo em:\n{output_pdf}")
            titulo = "Simulação concluída" if rel.dry_run else "Concluído"
            corpo = f"{rel.resumo()}\n\n{destino}\n\nRelatório:\n{cj}\n{cc}"

            # Zero substituições sai como aviso, não como conclusão. Este caminho
            # depende de reconhecer a fonte pelo nome, e nos três livros de
            # `PDF/` nenhuma das 39/28/41 fontes casa: os nomes vêm em subset
            # (`Fd350139`) e não há em que casar. O diálogo antigo dizia
            # "264 página(s), 0 substituição(ões); nenhum aviso" — que é o que
            # uma conversão perfeita também diria.
            if rel.alerta():
                messagebox.showwarning(titulo, f"{corpo}\n\n{self._saida_do_beco(rel)}")
            else:
                messagebox.showinfo(titulo, corpo)

        self._run_task("Simular substituição" if simular else "Substituir glifos",
                       trabalho, concluir)

    @staticmethod
    def _saida_do_beco(rel):
        """O que fazer diante de um relatório vazio. Depende de qual vazio é."""
        if rel.sem_camada_de_texto:
            return ("Este PDF não tem texto extraível — é uma digitalização. "
                    "Esta ferramenta trabalha sobre o texto do próprio PDF.\n"
                    "Use 'Substituir Glifos em PDF Escaneado (Neural)'.")
        return (
            "A detecção procura palavras-chave no nome da fonte (chess, merida, "
            "diagram...). Nomes como os deste documento costumam ser de subset, "
            "e o nome original não sobrevive neles.\n\n"
            "Se o livro é digitalizado, use 'Substituir Glifos em PDF Escaneado "
            "(Neural)'. Se é digital, acrescente o nome da fonte em "
            "'font_patterns' num perfil de config/profiles/ — a lista completa "
            "das fontes está no JSON do relatório.")

    def gerar_pdf_pesquisavel_action(self):
        """PDF pesquisável: mantém a página como está e só acrescenta o texto."""
        self._acao_ocr_pdf(
            modo="searchable",
            titulo="PDF pesquisável",
            titulo_saida="Salvar PDF pesquisável como...",
        )

    def substitute_glyphs_neural_action(self):
        """Substitui as peças reconhecidas E deixa o PDF pesquisável."""
        self._acao_ocr_pdf(
            modo="both",
            titulo="Substituir glifos + OCR",
            titulo_saida="Salvar PDF convertido como...",
        )

    def corrigir_mapeamento_action(self):
        """
        Conserta a tabela que diz qual caractere cada glifo representa.

        **Não desenha nem apaga nada na página.** É a operação certa para o
        livro cuja notação está correta na tela e sai `l2Jd7` ao copiar: nesses
        PDFs a fonte é Identity-H e o defeito está no `ToUnicode`, não no
        desenho. O PDF de saída renderiza pixel a pixel igual ao original —
        muda só o que a busca e a cópia enxergam.
        """
        if self._busy("A correção"):
            return
        self._avisar_do_modelo()

        input_pdf = filedialog.askopenfilename(
            title="Selecionar PDF",
            filetypes=[("Arquivos PDF", "*.pdf")]
        )
        if not input_pdf:
            return

        output_pdf = filedialog.asksaveasfilename(
            title="Salvar cópia corrigida como...",
            defaultextension=".pdf",
            filetypes=[("Arquivos PDF", "*.pdf")]
        )
        if not output_pdf:
            return

        def trabalho(h):
            h.log("Carregando modelo neural...")
            if not self.learning_service.load_predictor():
                raise RuntimeError(self.learning_service.motivo_do_modelo())

            # Só a rede, sem a cadeia de fallback: aqui a pergunta é "que peça é
            # este desenho", e o EasyOCR — que aceita o que vier — só diluiria a
            # votação com palpites de letra.
            def classificar(recorte):
                return self.learning_service.predict_neural(recorte)

            def progresso(atual, total):
                h.raise_if_cancelled()
                h.progress(atual, total, f"página {atual}/{total}")

            return corrigir_mapeamento(input_pdf, output_pdf,
                                       classificar=classificar,
                                       progress_callback=progresso)

        def concluir(rel):
            cj, cc = caminhos_do_mapa(output_pdf, rel.dry_run)
            corpo = (f"{rel.resumo()}\n\n"
                     f"A página não foi alterada: o PDF de saída renderiza igual "
                     f"ao original.\nO original não foi tocado.\n\n"
                     f"Arquivo salvo em:\n{output_pdf}\n\n"
                     f"Relatório:\n{cj}\n{cc}")
            if rel.avisos:
                corpo += "\n\n" + "\n".join(rel.avisos)

            if rel.aceitas:
                messagebox.showinfo("Mapeamento corrigido", corpo)
            else:
                messagebox.showwarning(
                    "Mapeamento corrigido", corpo + "\n\n"
                    "Nenhuma figurina foi identificada. Ou este PDF não tem o "
                    "defeito (a notação já copia certa), ou os glifos não se "
                    "parecem com o que o modelo aprendeu — o CSV mostra o que "
                    "foi examinado e por que cada candidata foi recusada.")

        self._run_task("Corrigir mapeamento", trabalho, concluir)

    #: Devolvido por `_perguntar_teto` quando o usuário desiste. **Não pode ser
    #: `None`**: aqui `None` já quer dizer "sem teto", que é a resposta oposta
    #: de "deixa para lá" — uma manda gravar tudo, a outra manda não rodar.
    CANCELADO = object()

    def _perguntar_teto(self):
        """
        Pergunta o teto por classe da coleta. Em branco é sem teto.

        **Campo de texto, e não `askinteger`.** O `askinteger` não tem como
        dizer "ilimitado": ele devolve `None` tanto para campo vazio quanto
        para o botão Cancelar, e mais um teto máximo no diálogo só trocaria um
        número fixo no código por outro na tela.

        Número inválido é perguntado de novo com o que foi digitado no campo,
        em vez de recusado com a ação inteira — o erro aqui é de dedo, e a
        alternativa é reabrir o PDF e a pasta para tentar outra vez.
        """
        from tkinter import simpledialog

        digitado = ""
        while True:
            digitado = simpledialog.askstring(
                "Teto por classe",
                "Quantos recortes gravar, no máximo, por cada classe?\n\n"
                "Deixe em branco para não ter teto: grava tudo o que aparecer.\n\n"
                "O teto existe porque uma classe ruim inunda a pasta e esconde "
                "as outras — revisar 4.000 recortes de 'o' não ensina mais que "
                "revisar algumas centenas. Para bater o olho numa grade de "
                "miniaturas, algumas centenas por classe; para engordar a base "
                "com o livro inteiro, sem teto.",
                initialvalue=digitado)
            if digitado is None:
                return self.CANCELADO
            try:
                return coleta.teto_de_texto(digitado)
            except ValueError as erro:
                messagebox.showwarning(
                    "Teto por classe",
                    f"{erro}\n\nDigite um número, ou deixe o campo em branco "
                    "para não ter teto.")

    def exportar_livro_action(self):
        """
        Lê o PDF **como imagem** e escreve um EPUB ou DOCX.

        É o único caminho que não usa a camada de texto do PDF. Nestes livros
        ela vem de um OCR de fábrica que erra a notação inteira — medido na
        página 11 do Yusupov, `'•. hb7 2.hb7 l2Jd7 3.ha8 Wlxa8'` onde o nosso
        OCR lê `'1...♗xb7 2.♗xb7 ♘d7 3.♗xa8 ♕xa8'`.
        """
        if self._busy("A exportação"):
            return
        self._avisar_do_modelo()

        input_pdf = filedialog.askopenfilename(
            title="Selecionar PDF",
            filetypes=[("Arquivos PDF", "*.pdf")]
        )
        if not input_pdf:
            return

        saida = filedialog.asksaveasfilename(
            title="Salvar livro como...",
            defaultextension=".epub",
            filetypes=[("Livro EPUB", "*.epub"), ("Documento Word", "*.docx")]
        )
        if not saida:
            return

        formato = os.path.splitext(saida)[1].lstrip(".").lower()
        if formato not in exportar.FORMATOS:
            messagebox.showerror(
                "Exportar livro",
                f"Extensão não reconhecida: {formato!r}.\n"
                f"Use .epub ou .docx.")
            return

        # O diagrama redesenhado é o padrão desde a F58, e o porteiro é quem
        # decide caso a caso — aqui só se pergunta se ele pode tentar. Quem
        # responde "não" leva o livro inteiro com o recorte do scan, que é o que
        # a F2.6 exportava.
        desenhar = messagebox.askyesno(
            "Redesenhar os diagramas?",
            "Redesenhar cada diagrama a partir da posição lida, com fonte de "
            "xadrez?\n\n"
            "O tabuleiro sai limpo, no lugar do recorte do scan. Onde a leitura "
            "não convencer, o diagrama cai sozinho para o recorte — medido em "
            "346 tabuleiros de livro, isso acontece em 9% deles.\n\n"
            "Não: todos os diagramas saem recortados da página, como antes.")

        # A fonte embutida (F59) só faz sentido sobre o desenho: recorte de scan
        # não vira letra. E é opção, não padrão — leitor que força a fonte do
        # usuário transforma o tabuleiro em `rmblkans`.
        embutir = desenhar and messagebox.askyesno(
            "Diagramas como texto, com a fonte embutida?",
            "Pôr o tabuleiro como texto de verdade, levando a fonte de xadrez "
            "dentro do arquivo?\n\n"
            "Ele passa a escalar sem perder nitidez e pesa quase nada. Em "
            "compensação, depende de o leitor respeitar a fonte embutida — "
            "quem trocar a fonte pela dele vê letras no lugar do tabuleiro.\n\n"
            "Não: o diagrama sai como imagem, que funciona em qualquer leitor.",
            default=messagebox.NO)

        coordenadas = messagebox.askyesno(
            "Coordenadas nos diagramas?",
            "Incluir as letras a–h e os números 1–8 em volta do tabuleiro?\n\n"
            "O livro impresso as traz para quem vai falar da posição em voz "
            "alta. Num arquivo que se lê na tela elas ocupam espaço e não dizem "
            "nada que o tabuleiro já não diga — por isso o padrão é sem.",
            default=messagebox.NO)

        # A extração já sabe onde o modelo é fraco: são os caracteres que ela
        # derruba por confiança. Guardá-los custa o disco de alguns milhares de
        # PNG pequenos e poupa caçá-los na tela um a um.
        coletar = messagebox.askyesno(
            "Guardar o que o modelo não soube ler?",
            "Guardar os recortes de baixa confiança numa pasta de revisão?\n\n"
            f"Eles vão para '{coleta.PASTA_PADRAO}/', separados pelo palpite do "
            "modelo — não para a base de treino. Confirmar é deixar o arquivo "
            "onde está, corrigir é movê-lo para outra pasta, descartar é "
            "apagá-lo.\n\n"
            "Depois, 'Promover recortes revistos' leva para a base o que sobrou.")

        teto = None
        if coletar:
            teto = self._perguntar_teto()
            if teto is self.CANCELADO:
                return

        def trabalho(h):
            h.log("Carregando modelo neural...")
            if not self.learning_service.load_predictor():
                raise RuntimeError(self.learning_service.motivo_do_modelo())

            coletor = coleta.Coletor(
                origem=os.path.basename(input_pdf),
                max_por_classe=teto) if coletar else None

            def progresso(atual, total):
                h.raise_if_cancelled()
                h.progress(atual, total, f"página {atual}/{total}")

            paginas = livro.extrair(input_pdf, self.learning_service.predict_neural,
                                    coletor=coletor,
                                    diagramas="render" if desenhar else "recorte",
                                    coordenadas=coordenadas,
                                    progress_callback=progresso)
            h.log("Escrevendo o arquivo...")
            exportar.exportar(paginas, saida, formato=formato,
                              titulo=os.path.splitext(os.path.basename(input_pdf))[0],
                              diagramas="fonte" if embutir else "png")
            if coletor is not None:
                coletor.gravar_indice()
            return paginas, coletor

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
            if desenhar and diagramas:
                # Quem caiu para o recorte é o que o usuário precisa saber para
                # conferir: são as páginas em que a leitura não convenceu.
                linhas.append(f"Diagramas redesenhados: {desenhados} de {diagramas}")
                recortados = [
                    f"  página {p.numero + 1}: {b.aviso}"
                    for p in paginas for b in p.blocos
                    if isinstance(b, livro.Figura) and b.aviso]
                if recortados:
                    linhas.append(f"Caíram para o recorte do scan "
                                  f"({len(recortados)}):")
                    linhas += recortados[:12]
                    if len(recortados) > 12:
                        linhas.append(f"  ... e mais {len(recortados) - 12}")
            if de_imagem:
                linhas.append(f"{de_imagem} página(s) eram imagem e saíram inteiras.")
            if coletor is not None:
                linhas += ["", f"Para revisão: {coletor.resumo()}",
                           f"em {os.path.abspath(coletor.pasta)}"]
            linhas += ["", "O texto veio só do nosso OCR — a camada de texto do "
                       "PDF foi ignorada.", f"Arquivo salvo em:\n{saida}"]
            messagebox.showinfo("Livro exportado", "\n".join(linhas))

        self._run_task("Exportar livro", trabalho, concluir)

    def criar_recortes_action(self):
        """
        Lê o PDF e grava os recortes de caractere separados por classe.

        Não escreve nada além dos PNG: nem PDF, nem livro. É o caminho para
        crescer a base de treino olhando — a pasta de uma classe fica cheia de
        acertos e o intruso salta aos olhos numa grade de miniaturas.

        **A pasta é escolhida, e o padrão nunca é `training_data`.** Amostra
        por conferir não pode ficar onde o treino varre.
        """
        if self._busy("A extração de recortes"):
            return
        self._avisar_do_modelo()

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

        teto = self._perguntar_teto()
        if teto is self.CANCELADO:
            return

        def trabalho(h):
            h.log("Carregando modelo neural...")
            if not self.learning_service.load_predictor():
                raise RuntimeError(self.learning_service.motivo_do_modelo())

            coletor = coleta.Coletor(
                pasta=pasta, origem=os.path.basename(input_pdf),
                max_por_classe=teto,
                limiar=None if todos else coleta.LIMIAR_PADRAO)

            def progresso(atual, total):
                h.raise_if_cancelled()
                h.progress(atual, total, f"página {atual}/{total}")

            livro.extrair(input_pdf, self.learning_service.predict_neural,
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
                    "Depois, 'Promover recortes revistos para a base'."]
            (messagebox.showinfo if coletor.total else messagebox.showwarning)(
                "Recortes para revisão", "\n".join(linhas))

        self._run_task("Criar recortes", trabalho, concluir)

    def promover_revisao_action(self):
        """
        Leva para a base de treino o que sobreviveu à revisão.

        O rótulo é o nome da pasta, então o que valeu foi o que você fez com o
        mouse: confirmar é deixar onde está, corrigir é mover, descartar é
        apagar. Pasta com nome que não é rótulo é recusada, não adivinhada.
        """
        if self._busy("A promoção"):
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
            return coleta.promover(pasta, data_dir=self.learning_service.data_dir)

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

        self._run_task("Promover recortes", trabalho, concluir)

    def _perguntar_sobre_paginas_com_texto(self, input_pdf):
        """
        True = pular as páginas que já têm texto, False = reprocessar, None = desistir.

        **É a pergunta que decide o resultado inteiro nestes livros.** Pular é o
        padrão certo para um scan limpo — escrever OCR sobre página que já tem
        texto duplica o conteúdo e a busca devolve tudo duas vezes. Mas as
        digitalizações deste projeto vêm com OCR de fábrica em quase toda
        página, e aí o padrão faz a conversão inteira não fazer nada: medido nos
        três livros de `PDF/`, 58/60, 57/60 e 53/60 páginas puladas. A opção
        existia em `gerar_pdf_pesquisavel` desde sempre e não chegava aqui.

        Só pergunta quando há o que perguntar: num scan puro a contagem dá zero
        e o padrão passa direto.
        """
        self.parent.config(cursor="watch")
        self.status.set("Verificando quais páginas já têm texto...")
        self.parent.update_idletasks()
        try:
            com_texto, total = contar_paginas_com_texto(input_pdf)
        except Exception:
            # Arquivo ilegível: quem reporta é a tarefa, com o diálogo de erro
            # de sempre. Aqui só não dá para perguntar nada.
            return True
        finally:
            self.parent.config(cursor="")
            self.status.set("Pronto.")

        if not com_texto:
            return True

        resposta = messagebox.askyesnocancel(
            "Páginas que já têm texto",
            f"{com_texto} de {total} página(s) já têm uma camada de texto.\n\n"
            "Sim — pular essas páginas (padrão): preserva o texto que já existe "
            "e processa só o resto.\n"
            "Não — reprocessar todas: para digitalização cujo OCR de fábrica é "
            "ruim, que é o caso dos livros deste projeto.\n\n"
            "Reprocessar acrescenta uma segunda camada de texto sobre a que já "
            "existe; a busca no PDF passa a encontrar as duas."
        )
        return resposta

    def _acao_ocr_pdf(self, modo, titulo, titulo_saida):
        if self._busy("A conversão"):
            return
        self._avisar_do_modelo()

        input_pdf = filedialog.askopenfilename(
            title="Selecionar PDF Escaneado",
            filetypes=[("Arquivos PDF", "*.pdf")]
        )
        if not input_pdf:
            return

        pular = self._perguntar_sobre_paginas_com_texto(input_pdf)
        if pular is None:
            return

        output_pdf = filedialog.asksaveasfilename(
            title=titulo_saida,
            defaultextension=".pdf",
            filetypes=[("Arquivos PDF", "*.pdf")]
        )
        if not output_pdf:
            return

        def trabalho(h):
            h.log("Carregando modelo neural...")
            self.learning_service.load_predictor()
            h.log("Carregando base de referência...")
            learner = self.learning_service._get_learner()
            predictor = self.learning_service._predictor

            def reconhecer(recorte):
                char, _fonte, conf = self.ocr_service.fallback_chain(
                    recorte, predictor=predictor, learner=learner,
                    neural_threshold=NEURAL_THRESHOLD,
                    learner_threshold=LEARNER_THRESHOLD_NEURAL,
                )
                return char, conf

            def progresso(pagina, total):
                h.raise_if_cancelled()
                h.progress(pagina + 1, total, f"página {pagina + 1}/{total}")

            return gerar_pdf_pesquisavel(
                input_pdf, output_pdf,
                reconhecer=reconhecer,
                modo=modo,
                pular_paginas_com_texto=pular,
                ler_linha=self.ocr_service.easyocr_linha_conf,
                progress_callback=progresso,
            )

        def concluir(resumo):
            linhas = [
                f"Páginas: {resumo['paginas']}"
                f"  (OCR em {resumo['paginas_ocr']}, "
                f"{resumo['paginas_puladas']} já tinham texto)",
                f"Caracteres reconhecidos: {resumo['reconhecidos']} de {resumo['boxes']}",
            ]
            if not resumo["paginas_ocr"] and resumo["paginas_puladas"]:
                linhas.append("")
                linhas.append(
                    "Nenhuma página foi processada: todas já tinham camada de "
                    "texto e foram puladas. Se essa camada é de um OCR ruim, "
                    "repita respondendo «Não» à pergunta sobre páginas que já "
                    "têm texto.")
            if resumo["pecas_substituidas"]:
                linhas.append(f"Peças substituídas: {resumo['pecas_substituidas']}")
            if resumo.get("simbolos_de_recurso"):
                linhas.append("Escritos com a fonte de recurso: "
                              f"{resumo['simbolos_de_recurso']}")
            if resumo["baixa_confianca"]:
                linhas.append(f"Baixa confiança: {resumo['baixa_confianca']}")
            if resumo["sem_glifo"]:
                linhas.append(f"Sem glifo na fonte: {resumo['sem_glifo']}")
            linhas.append("")
            linhas.append("O texto original do PDF foi preservado.")
            linhas.append(f"Arquivo salvo em:\n{output_pdf}")
            messagebox.showinfo(titulo, "\n".join(linhas))

        self._run_task(titulo, trabalho, concluir)

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

        Box de texto girado sai **de pé** (F8.1): o classificador foi treinado
        em glifo em pé, e o mesmo recorte deitado desce de 94,2% para 8,4%.

        `np.array` e não `np.asarray`: a segunda pode devolver vista sobre o
        buffer da própria PIL.Image, e aí os recortes voltariam a apontar para
        o objeto compartilhado — que é justamente o que este método existe
        para evitar. Uma cópia da página custa menos que milhares de recortes.

        Devolve `(justo, com_a_faixa_da_linha)` por box. O justo é o que a rede
        e o k-NN pedem — é nele que treinaram. O segundo é o mesmo box esticado
        até a linha, e serve ao EasyOCR, que sem ele não distingue `c` de `C`
        (ver `box_service.faixas_de_linha`). Sai pelo mesmo `recorte_de_pe`
        para herdar o giro e a positivação do negativo.
        """
        pagina = np.array(self.image)
        faixas = faixas_de_linha(self.boxes)

        pares = []
        for b, (topo, base) in zip(self.boxes, faixas):
            justo = vertical.recorte_de_pe(pagina, b)
            if (topo, base) == (b.y1, b.y2):
                pares.append((justo, justo))
            else:
                pares.append(
                    (justo,
                     vertical.recorte_de_pe(pagina, replace(b, y1=topo, y2=base))))
        return pares

    def _preencher_boxes(self, titulo, preparar, resumo):
        """
        Preenche os caracteres de todos os boxes fora da thread da UI.

        `preparar(h)` roda na thread e devolve
        `classificar(justo, com_faixa) -> (char, fonte, confiança)`; é lá que a
        carga pesada acontece (o learner lê 127 mil imagens de referência, o
        predictor carrega o modelo). Os dois recortes chegam porque cada elo
        quer um: ver `_recortes_dos_boxes`.

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
            for i, (justo, com_faixa) in enumerate(recortes):
                if h.cancelled:
                    cancelado = True
                    break
                resultados.append(classificar(justo, com_faixa))
                if i % 5 == 0 or i == total - 1:
                    h.progress(i + 1, total, f"{i + 1}/{total}")
            return {"resultados": resultados, "cancelado": cancelado}

        def aplicar(saida):
            resultados = saida["resultados"]
            fontes = {}
            for b, (char, fonte, conf) in zip(self.boxes, resultados):
                b.char = char
                b.source = fonte if char else ""
                b.confidence = conf
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
            def classificar(justo, _com_faixa):
                ch, c = self.ocr_service.tesseract_ocr_conf(
                    Image.fromarray(justo), whitelist)
                return (ch, "tesseract" if ch else "vazio", c)
            return classificar

        self._preencher_boxes(
            "OCR (Tesseract)", preparar,
            lambda fontes, n: f"Processados: {n} boxes.",
        )

    def auto_fill_characters_easyocr(self):
        def preparar(h):
            def classificar(justo, com_faixa):
                # `easyocr_so` e não `easyocr`: aqui ele é o **leitor**, e na
                # cadeia ele é o último recurso. Ver a F53 e
                # `FONTES_SEMPRE_REVISADAS` — a regra da F48 foi medida na
                # segunda população, em que 57% dos boxes estão errados.
                #
                # **Esta ação acerta 73,2%, e não os 89,5% que a F53 citou** —
                # aquele número é da leitura por linha (F17), que é a outra ação
                # a gravar esta mesma fonte. O que sustenta a isenção não é o
                # acerto e sim a régua: separação 0,776 (F55), contra os 0,582
                # que puseram `easyocr` na lista.
                ch, c = self.ocr_service.easyocr_ocr_conf(
                    justo, contexto=com_faixa)
                return (ch, "easyocr_so" if ch else "vazio", c)
            return classificar

        self._preencher_boxes(
            "OCR (EasyOCR)", preparar,
            lambda fontes, n: (f"Processados: {n} boxes.\n"
                               f"Caracteres preenchidos: "
                               f"{fontes.get('easyocr_so', 0)}"),
        )

    def generate_and_fill_easyocr(self):
        self.generate_boxes_opencv()
        if self.boxes:
            self.auto_fill_characters_easyocr()

    def auto_fill_characters_linha(self):
        """
        Lê a linha inteira, e não o caractere (F17).

        O `english_g2` é um CRNN treinado em palavra e linha; caractere a
        caractere ele fica sem o modelo de linguagem que separa `0` de `o` e `1`
        de `l`. Medido nas páginas rotuladas, 72,9% para 89,5% — e o ganho é
        todo nos pares que um glifo isolado não decide.

        O caro aqui não é a linha (1,5 ms por caractere), é a leitura por
        caractere que serve de âncora ao alinhamento. Ela é obrigatória: sem um
        item por box não há como distribuir a string pelos boxes.
        """
        def preparar(h, pagina, faixas, margens):
            # Sem k-NN nesta ação, então `margens` fica vazio e todo box sai
            # `SEM_MARGEM` — que é o certo: não há margem para falar dele.
            def ler_caractere(b):
                justo, contexto = self._recortes_do_box(pagina, b, faixas)
                ch, cf = self.ocr_service.easyocr_ocr_conf(
                    justo, contexto=contexto)
                # Ver `auto_fill_characters_easyocr`: aqui ele é o leitor.
                return ch, cf, "easyocr_so"
            return ler_caractere

        self._preencher_por_linha(
            "OCR (EasyOCR por linha)", preparar,
            lambda fontes: (
                f"Decididos pela linha: {fontes.get('easyocr_linha', 0)}\n"
                f"Só pelo caractere: {fontes.get('easyocr_so', 0)}"),
        )

    def _recortes_do_box(self, pagina, b, faixas):
        """`(justo, com a faixa da linha)` — ver `_recortes_dos_boxes`."""
        justo = vertical.recorte_de_pe(pagina, b)
        topo, base = faixas[id(b)]
        if (topo, base) == (b.y1, b.y2):
            return justo, justo
        return justo, vertical.recorte_de_pe(
            pagina, replace(b, y1=topo, y2=base))

    def _preencher_por_linha(self, titulo, preparar, resumo,
                             conf_maxima_para_trocar=None):
        """
        Como `_preencher_boxes`, mas o laço é por **linha** e não por box.

        `preparar(h, pagina, faixas)` devolve
        `ler_caractere(box) -> (char, confiança, fonte)`, que é a âncora do
        alinhamento. `conf_maxima_para_trocar` é a trava da F18 — ver
        `leitura_de_linha.ler_pagina`.

        Cancelar devolve o parcial por linha: o que já foi lido é aplicado, e o
        resto dos boxes fica **como estava** em vez de ser esvaziado.
        """
        if self.image is None or not self.boxes:
            messagebox.showinfo("Aviso", "Não há boxes para preencher.")
            return
        if self._busy(titulo):
            return

        # Cópia na thread da UI, pela razão de `_recortes_dos_boxes`.
        pagina = np.array(self.image)
        linhas = leitura_de_linha.linhas_da_pagina(self.boxes)
        faixas = {id(b): faixa
                  for uma in linhas
                  for b, faixa in zip(uma, faixas_de_linha(uma))}
        total = sum(len(uma) for uma in linhas)

        # **A margem viaja por fora do `ler_pagina`, e é de propósito** (F44). Ela
        # é do reconhecimento do caractere, não da leitura da linha, e enfiá-la
        # na tupla do `ler_pagina` mudaria o contrato de um módulo que o
        # `searchable_pdf` também usa. O `id(box)` como chave é o mesmo idioma
        # que o `faixas` aqui em cima já usa.
        margens = {}

        def trabalho(h):
            lidos = leitura_de_linha.ler_pagina(
                pagina, linhas,
                ler_faixa=self.ocr_service.easyocr_linha_conf,
                ler_caractere=preparar(h, pagina, faixas, margens),
                # **Sem `deslocam`, e a F36 mediu que tem de ser.** A linha com
                # figurina parece a que mais precisa de filtro e é a que menos:
                # o `_alinhar` absorve o deslocamento, e filtrar joga fora as
                # correções do resto da linha. Ver `leitura_de_linha.em_bloco`.
                conf_maxima_para_trocar=conf_maxima_para_trocar,
                cancelado=lambda: h.cancelled,
                progresso=lambda i, n: h.progress(i, n, f"linha {i}/{n}"),
            )
            return {"lidos": lidos, "cancelado": h.cancelled}

        def aplicar(saida):
            fontes = {}
            for b, char, conf, fonte in saida["lidos"]:
                b.char = char
                b.source = fonte if char else ""
                b.confidence = conf
                # Só onde a fonte sobreviveu: um box que a linha trocou passou a
                # ser leitura do EasyOCR, e a margem do k-NN não fala dele.
                b.margem = (margens.get(id(b), SEM_MARGEM)
                            if fonte == "learner" else SEM_MARGEM)
                fontes[fonte] = fontes.get(fonte, 0) + 1

            self._commit_change()
            self.update_sidebar()
            self.update_canvas()

            feitos = len(saida["lidos"])
            texto = f"Linhas: {len(linhas)}\n" + resumo(fontes)
            if saida["cancelado"]:
                texto += (f"\n\nCancelado: {feitos} de {total} boxes "
                          f"processados; o resto ficou como estava.")
                self.status.set(f"{titulo}: cancelado ({feitos}/{total}).")
            messagebox.showinfo(titulo, texto)

        self._run_task(titulo, trabalho, aplicar)

    def generate_and_fill_linha(self):
        self.generate_boxes_opencv()
        if self.boxes:
            self.auto_fill_characters_linha()

    def generate_and_fill_combined(self):
        self.generate_boxes_opencv()
        if not self.boxes:
            return

        def preparar(h, pagina, faixas, margens):
            h.log("Carregando base de referência...")
            learner = self.learning_service._get_learner()

            def ler_caractere(b):
                justo, contexto = self._recortes_do_box(pagina, b, faixas)
                # `neural_threshold` não é usado — esta ação não carrega a rede
                # —, mas fica igual ao outro para o dia em que alguém passar um
                # predictor por aqui e esperar o mesmo roteamento.
                leitura = self.ocr_service.fallback_chain_detalhado(
                    justo, learner=learner, contexto=contexto,
                    neural_threshold=LEARNER_THRESHOLD_HIBRIDO,
                    learner_threshold=LEARNER_THRESHOLD_HIBRIDO,
                )
                if leitura.fonte not in ("learner", "easyocr"):
                    return ("", 0.0, "vazio")
                margens[id(b)] = leitura.margem
                return (leitura.char, leitura.confianca, leitura.fonte)
            return ler_caractere

        self._preencher_por_linha(
            "Detectar e preencher (Híbrido)", preparar,
            lambda fontes: (f"Encontrados via Base: {fontes.get('learner', 0)}\n"
                            f"Encontrados via OCR: {fontes.get('easyocr', 0)}\n"
                            f"Corrigidos pela linha: "
                            f"{fontes.get('easyocr_linha', 0)}"),
            conf_maxima_para_trocar=CONF_MAXIMA_PARA_A_LINHA_HIBRIDO,
        )

    def generate_and_fill_neural(self):
        # Antes do trabalho, não depois: este é o caminho em que a confiança da
        # rede vira `b.confidence`, e é ela que decide a cor do box e o filtro
        # "só pendentes". Saber que a escala não está calibrada muda como o
        # usuário lê o resultado que está prestes a gerar.
        self._avisar_do_modelo()
        self.generate_boxes_opencv()
        if not self.boxes:
            return

        def preparar(h, pagina, faixas, margens):
            h.log("Carregando modelo neural...")
            self.learning_service.load_predictor()
            h.log("Carregando base de referência...")
            learner = self.learning_service._get_learner()
            predictor = self.learning_service._predictor

            def ler_caractere(b):
                justo, contexto = self._recortes_do_box(pagina, b, faixas)
                leitura = self.ocr_service.fallback_chain_detalhado(
                    justo, predictor=predictor, learner=learner,
                    contexto=contexto,
                    neural_threshold=NEURAL_THRESHOLD,
                    learner_threshold=LEARNER_THRESHOLD_NEURAL,
                )
                margens[id(b)] = leitura.margem
                return (leitura.char, leitura.confianca, leitura.fonte)
            return ler_caractere

        self._preencher_por_linha(
            "Detectar e preencher (Neural)", preparar,
            lambda fontes: (f"Neural: {fontes.get('neural', 0)}\n"
                            f"Referência: {fontes.get('learner', 0)}\n"
                            f"EasyOCR: {fontes.get('easyocr', 0)}\n"
                            f"Corrigidos pela linha: "
                            f"{fontes.get('easyocr_linha', 0)}"),
            conf_maxima_para_trocar=CONF_MAXIMA_PARA_A_LINHA,
        )

    # -------------------------------------------------------
    # Sidebar / seleção
    # -------------------------------------------------------

    # -------------------------------------------------------
    # Léxico (F9) — triagem por palavra, independente da confiança
    # -------------------------------------------------------

    def lexico_da_sessao(self):
        """
        O léxico desta sessão: a lista geral mais a deste livro (F9.2).

        Carregado uma vez por documento, não uma vez por processo — a lista do
        usuário é por livro, e mantê-la de um documento para o outro daria ao
        Kasparov o vocabulário do Yusupov, que é o contrário do motivo da F9.2.
        `_esquecer_lexico` é quem invalida, na abertura.
        """
        if self._lexico is None:
            self._lexico = lexico.carregar(
                caminho_usuario=self._caminho_do_lexico())
        return self._lexico

    def _caminho_do_lexico(self):
        """Onde fica a lista deste livro, ou None sem documento aberto."""
        if self.session is None:
            return None
        return lexico.caminho_do_usuario(self.session.path, self.session.is_pdf)

    def _esquecer_lexico(self):
        """Força a recarga do léxico e das suspeitas — chamada ao abrir."""
        self._lexico = None
        self._cache_suspeitas = (None, [])

    def aprender_palavras_da_pagina(self, boxes=None):
        """
        Põe no dicionário do livro as palavras que o usuário sustentou.

        Roda junto do "Aprender com Página Atual", e não num comando próprio: é
        a mesma confirmação, sobre a mesma página, e a F8.3 já estabeleceu que o
        que vira dado é o que o usuário sustenta explicitamente. Um segundo item
        de menu pediria que ele se lembrasse de dois.

        Roda **também ao salvar** (F9.3), que é o outro momento em que o usuário
        declara ter terminado com a página — e o mais frequente dos dois, porque
        salvar é obrigatório e "aprender" é opcional.
        """
        return self.aprender_palavras_das_paginas(
            [self.boxes if boxes is None else boxes])

    def aprender_palavras_das_paginas(self, paginas):
        """
        O mesmo, para várias páginas de uma vez, gravando o arquivo uma só vez.

        Existe por causa do "Salvar todas as páginas": chamar a versão de uma
        página em laço reescreveria a lista inteira a cada página gravada, e a
        lista é a verdade do arquivo — quem edita à mão entre uma página e outra
        não deve ver o programa desfazendo a edição N vezes.
        """
        lex = self.lexico_da_sessao()
        caminho = self._caminho_do_lexico()
        if not lex.sinaliza or not caminho:
            return []
        novas = []
        for boxes in paginas:
            # Sem `caminho`: só mexe no léxico em memória. A gravação é uma só,
            # depois do laço.
            novas.extend(lexico.aprender_da_pagina(boxes, lex))
        if novas:
            lexico.salvar_do_usuario(caminho, lex.do_usuario)
            self._cache_suspeitas = (None, [])
        return novas

    def _frase_do_dicionario(self, palavras):
        """A linha de relatório das palavras novas, ou string vazia."""
        if not palavras:
            return ""
        # Só as primeiras: uma página pode render dezenas, e o diálogo não é o
        # lugar de listar vocabulário — o arquivo é.
        amostra = ", ".join(palavras[:8])
        resto = f" (+{len(palavras) - 8})" if len(palavras) > 8 else ""
        return (f"\n\n{len(palavras)} palavra(s) nova(s) no dicionário deste "
                f"livro:\n{amostra}{resto}")

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

    def referencia_do_lote(self):
        """
        Qual box serve de modelo, e por qual leitura procurar. `(i, char, leitura)`.

        **A última correção tem preferência sobre a seleção, e isso não é
        detalhe.** Tanto o Enter quanto o modo digitação avançam sozinhos
        depois de gravar o caractere (F3.1), então quando o usuário pede o lote
        a seleção já saiu de cima do box que ele acabou de corrigir. Usar a
        seleção pegaria o box seguinte, que ele nem olhou.

        `leitura` é o caractere que os candidatos ainda mostram: o modelo já
        virou `e`, os outros 300 continuam em `c`. É o filtro que segura a
        precisão em 99,3% quando se afrouxa o limiar (ver `core.semelhanca`).
        Sem correção registrada, casa só pela imagem — não há "antes" que
        sirva de filtro.

        A identidade do objeto é o que valida a correção guardada, não o
        índice: dividir ou excluir um box desloca os índices, e o desfazer
        troca a lista inteira por cópias.
        """
        uc = self._ultima_correcao
        if uc is not None:
            _, box, anterior, novo = uc
            for i, b in enumerate(self.boxes):
                if b is box and b.char == novo and novo:
                    return i, novo, anterior

        if 0 <= self.selected_index < len(self.boxes):
            b = self.boxes[self.selected_index]
            return self.selected_index, b.char, None
        return None

    def aplicar_aos_semelhantes(self):
        if self.image is None or not self.boxes:
            return
        if self._busy("A aplicação em lote"):
            return

        referencia = self.referencia_do_lote()
        if referencia is None:
            messagebox.showinfo("Aplicar aos semelhantes",
                                "Selecione primeiro um box.")
            return

        indice, alvo, leitura = referencia
        if not alvo:
            messagebox.showinfo(
                "Aplicar aos semelhantes",
                "Escreva primeiro o caractere certo neste box; ele é o que "
                "será aplicado aos semelhantes.")
            return

        escolhidos = self.DIALOGO_SEMELHANTES(
            self.parent, self.image, self.boxes, indice, alvo, leitura).mostrar()
        if escolhidos is None:
            self.status.set("Lote cancelado.")
            return
        if not escolhidos:
            self.status.set("Nenhum box semelhante marcado.")
            return

        n = self.aplicar_em_lote(escolhidos, alvo)
        self.status.set(f"{n} box(es) marcados como “{alvo}” em lote. "
                        f"Ctrl+Z desfaz o lote inteiro.")

    def aplicar_em_lote(self, indices, char):
        """
        Grava `char` em todos os índices e devolve quantos mudaram.

        Um `_commit_change` só no fim: são 300 boxes, mas **um** Ctrl+Z. Um
        snapshot por box entupiria o histórico de 50 posições e deixaria o
        usuário sem como voltar ao estado anterior ao lote — que é exatamente
        o que ele vai querer quando o lote sair errado.
        """
        mudados = 0
        for i in indices:
            if not (0 <= i < len(self.boxes)):
                continue
            b = self.boxes[i]
            if b.char == char:
                continue
            b.char = char
            b.confidence = 1.0
            b.source = self.ORIGEM_LOTE
            mudados += 1

        if mudados:
            self._commit_change()
            self.update_sidebar()
            self.update_canvas()
        return mudados

    def ocr_selected_box(self):
        if self.image is None or self.selected_index < 0 or self.selected_index >= len(self.boxes):
            return

        b = self.boxes[self.selected_index]
        # Pelo funil, e não por `self.image.crop`: o Tesseract quer o glifo de
        # pé (F8.1) e escuro sobre claro (F10), como qualquer classificador.
        crop = Image.fromarray(vertical.recorte_de_pe(np.array(self.image), b))
        ch = self.ocr_service.tesseract_ocr(crop)

        if not ch:
            messagebox.showinfo("OCR", "Nenhum caractere reconhecido.")
            return

        self.char_entry.delete(0, "end")
        self.char_entry.insert(0, ch)

    # -------------------------------------------------------
    # Salvar / carregar .box
    # -------------------------------------------------------

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
        if self.session is not None:
            base = self.session.page_stem(self.current_pdf_page)
        elif self.image_path:
            base = os.path.splitext(self.image_path)[0]
        else:
            base = padrao
        return os.path.dirname(base), os.path.basename(base) + ext

    def save_box_file(self):
        if self.image is None or not self.boxes:
            messagebox.showinfo("Aviso", "Nada para salvar.")
            return

        pasta, nome = self._destino_sugerido(".box", "boxes")

        path = filedialog.asksaveasfilename(
            defaultextension=".box",
            initialdir=pasta or None,
            initialfile=nome,
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
            if not sessao.is_dirty():
                self._descartar_rascunho()
            self._update_nav_controls()
            self._update_title()
            # Aqui e não no `trabalho`: mexer no léxico e no cache de suspeitas
            # é estado da UI, e a thread não pode tocá-los. Só as páginas que
            # **gravaram** — quem falhou não terminou.
            palavras = self.aprender_palavras_das_paginas(
                [sessao.boxes_for(page) for page, _ in salvos])
            self._relatar_salvamento([d for _, d in salvos], falhas, palavras)
            if palavras:
                self.update_sidebar()
                self.update_canvas()

        self._run_task("Salvar todas as páginas", trabalho, concluir)

    def _relatar_salvamento(self, salvos, falhas, palavras=()):
        resumo = f"{len(salvos)} página(s) salva(s) em:\n{os.path.dirname(self.session.path)}"
        resumo += self._frase_do_dicionario(palavras)
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
        erro = self._write_box_pair(path, self.image, self.boxes)
        if erro:
            messagebox.showerror("Erro", f"Não foi possível salvar os arquivos:\n{erro}")
            return

        if self.session is not None:
            self.session.mark_saved(self.current_pdf_page)
            if not self.session.is_dirty():
                self._descartar_rascunho()
            self._update_nav_controls()
        self._update_title()

        # Depois de gravar, e não antes: se a escrita falhar, o usuário não
        # terminou com a página coisa nenhuma, e o dicionário não deve ter
        # aprendido nada dela.
        palavras = self.aprender_palavras_da_pagina()

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
            f"{self._frase_do_dicionario(palavras)}"
        )
        if palavras:
            # A palavra que entrou deixa de ser suspeita: a lista e o canvas
            # mostram isso agora, não na próxima vez que algo os redesenhar.
            self.update_sidebar()
            self.update_canvas()

    def _load_box_from_path(self, path, marcar_sujo=True):
        if self.image is None:
            return

        try:
            boxes = formato_box.ler(path, self.image.height)
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
        """
        Ctrl+D: parte o box selecionado em dois.

        A página vai junto porque o corte olha a tinta (ver `split_box`): sem
        ela sobra a regra da proporção, que devolve as metades uma embaixo da
        outra sempre que o box tem uma letra alta ao lado de uma baixa.

        **O foco vai para o campo do caractere** (F4.9). `split_box` devolve as
        duas metades **sem char nenhum**, então o passo seguinte a dividir é
        sempre digitar — e antes disso o revisor tinha de ir ao mouse buscar o
        campo, no meio de um fluxo que existe para não precisar dele.

        Isto mora na ação e não na binding: o Ctrl+D vem do canvas, da lista ou
        do menu "Dividir box selecionado", e as três rotas devem terminar com o
        cursor no mesmo lugar. No modo digitação o foco não se mexe, pela mesma
        razão do Tab — lá quem recebe as teclas é a janela, e roubá-lo
        desligaria o modo na prática.
        """
        if self.selected_index < 0 or self.selected_index >= len(self.boxes):
            return

        b = self.boxes[self.selected_index]
        pagina = np.array(self.image) if self.image is not None else None
        b1, b2 = self.box_service.split_box(b, pagina)

        self.boxes.pop(self.selected_index)
        self.boxes.insert(self.selected_index, b2)
        self.boxes.insert(self.selected_index, b1)
        self._commit_change()

        self.select_box(self.selected_index)
        if not self.modo_digitacao:
            self.char_entry.focus_set()
            self.char_entry.select_range(0, "end")

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

        # Fora da thread: mexe no léxico da sessão e no cache de suspeitas, que
        # são estado da UI. É rápido — a página inteira é uma passada de
        # `_fatiar` — e não tem por que disputar a vaga da tarefa de fundo.
        palavras = self.aprender_palavras_da_pagina()

        def trabalho(h):
            h.progress(0, len(boxes), "gravando amostras")
            return self.learning_service.learn_from_boxes(imagem, boxes)

        def concluir(count):
            aviso = f"Aprendizado concluído.\n{count} novos modelos adicionados."
            aviso += self._frase_do_dicionario(palavras)
            messagebox.showinfo("Sucesso", aviso)
            if palavras:
                self.update_sidebar()
                self.update_canvas()

        self._run_task("Aprender com a página", trabalho, concluir, indeterminado=True)

    # -------------------------------------------------------
    # Neural Network
    # -------------------------------------------------------

    def verificar_base_treino(self):
        """
        Diagnóstico completo da base, inclusive lendo cada PNG.

        Vale um item de menu próprio: o defeito que motivou isto (127 amostras
        treinando a classe errada) só era visível para quem fosse conferir os
        nomes das pastas à mão.
        """
        if self._busy("A verificação"):
            return

        def trabalho(h):
            h.log("Lendo a base de treino...")
            return self.learning_service.validar_dados(checar_pngs=True)

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

            mostrar = messagebox.showerror if graves else messagebox.showinfo
            mostrar("Base de treino", "\n".join(linhas))

        self._run_task("Verificar base de treino", trabalho, concluir,
                       indeterminado=True)

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

        def trabalho(h):
            # should_stop é consultado a cada época: cancelar mantém salvo o
            # melhor modelo obtido até ali.
            return self.learning_service.train_neural(
                epochs=epochs,
                callback=h.log,
                should_stop=lambda: h.cancelled,
            )

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
            self._modelo_conferido = False

            relatorio = self.learning_service.caminho_relatorio()
            if os.path.exists(relatorio):
                if messagebox.askyesno(
                    "Treinamento concluído",
                    "Treinamento concluído! Agora você pode usar "
                    "'Detectar e Preencher (Neural)'.\n\n"
                    "Deseja abrir o relatório de validação?"
                ):
                    self.abrir_relatorio_treino()
            else:
                messagebox.showinfo(
                    "Sucesso",
                    "Treinamento concluído!\nAgora você pode usar "
                    "'Detectar e Preencher (Neural)'."
                )
            self._avisar_do_modelo()

        self._run_task("Treinar rede neural", trabalho, concluir, indeterminado=True)

    #: Costura de teste, como a da F3.6.
    DIALOGO_DIAGRAMA = DialogoDiagrama

    def extrair_diagramas(self):
        """
        Lê a posição dos diagramas da página (F7.1, corrigida na F8.3).

        **Os boxes da página não servem para achar o diagrama, e isso era um
        defeito calado.** O tabuleiro é o contorno grande e quadrado que a F1.8
        descarta — e `generate_boxes_opencv` descarta antes de devolver. Passar
        `self.boxes` para `localizar` é pedir que ela ache entre os contornos
        justamente aquele que já não está lá: medido em 6 páginas reais com
        diagrama, 0 encontrados contra 2 ou 3 por página. O comando respondia
        sempre "nenhum diagrama encontrado", e o texto ainda culpava a borda da
        página.

        A geração aqui é própria e sem descarte. Custa uma passada de contornos
        (0,36 s numa página de 1.605 boxes) e não mexe em `self.boxes`, que
        continua sendo a lista de caracteres da página.
        """
        from core import diagrama as diag

        if self.image is None:
            messagebox.showinfo("Diagramas", "Abra uma imagem ou PDF primeiro.")
            return

        try:
            # `separar_colados=False`: cortar glifo colado não muda onde o
            # tabuleiro está, e aqui só se procura o tabuleiro.
            contornos = self.box_service.generate_boxes_opencv(
                self.image, descartar_nao_texto=False, separar_colados=False)
            leituras = diag.ler_pagina(self.image, contornos)
        except diag.ModeloAusente as e:
            messagebox.showerror("Diagramas", str(e))
            return

        if not leituras:
            messagebox.showinfo(
                "Diagramas",
                "Nenhum diagrama encontrado nesta página.\n\n"
                "O tabuleiro é reconhecido por ser um contorno grande e "
                "quadrado; um diagrama cortado na borda da página não casa.")
            return

        fen = self.DIALOGO_DIAGRAMA(self.parent, self.image, leituras,
                                    origem=self._origem_da_pagina()).mostrar()
        if fen:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(fen)
            self.status.set(f"FEN copiado: {fen}")
        else:
            self.status.set(f"{len(leituras)} diagrama(s) lidos.")

    def _origem_da_pagina(self) -> str:
        """
        Nome que identifica a página atual, para a procedência da amostra (F8.3).

        Sai do mesmo lugar que o `.box` da página usa, quando há sessão; senão,
        do nome do arquivo aberto.
        """
        if self.session is not None:
            return os.path.basename(self.session.page_stem(self.current_pdf_page))
        if self.image_path:
            return os.path.splitext(os.path.basename(self.image_path))[0]
        return ""

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
            self.status.set(
                f"Modelo de diagramas: {relatorio.total} amostras, {medido}.")

        self._run_task("Treinar modelo de diagramas", trabalho, concluir,
                       indeterminado=True)

    def exportar_pgn(self):
        """
        Grava a notação reconhecida como `.pgn`.

        Roda na thread da UI pelo mesmo motivo de `validar_notacao`: o custo é a
        análise, que são dezenas de milissegundos numa página cheia.
        """
        from core import pgn

        if not self.boxes:
            messagebox.showinfo("Exportar PGN", "Nenhum box na página.")
            return

        texto, relatorio = pgn.exportar(
            self.boxes,
            pgn.cabecalhos_do_documento(
                self.session.path if self.session else self.image_path,
                self.current_pdf_page if self.session
                and self.session.is_pdf else None))

        if not texto.strip():
            messagebox.showinfo(
                "Exportar PGN",
                "Nenhuma partida completa foi reconhecida nesta página.\n\n"
                + relatorio.resumo()
                + "\n\nA leitura começa num '1.' — sem o começo da partida não "
                  "há posição de onde partir.")
            return

        pasta, nome = self._destino_sugerido(".pgn", "partida")

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
        self.status.set(f"PGN exportado: {relatorio.lances} lances em "
                        f"{len(relatorio.partidas)} partida(s).")

    def validar_notacao(self):
        """
        Confronta a notação da página com as regras do xadrez (F1.7).

        Roda direto na thread da UI: medido em 37 ms para 1.487 boxes, bem
        dentro do critério de 100 ms da F4.1. Passar pelo BackgroundTask custaria
        mais em cerimônia do que economiza.
        """
        from core import notacao

        if not self.boxes:
            messagebox.showinfo("Validar notação",
                                "Nenhum box na página.")
            return

        analise = notacao.analisar(self.boxes)
        if not analise.lances:
            messagebox.showinfo(
                "Validar notação",
                "Nenhuma sequência de lances foi reconhecida nesta página.\n\n"
                "A leitura começa num '1.' — sem o começo da partida não há "
                "posição de onde partir.")
            return

        linhas = [analise.resumo(), ""]
        duvidosos = [l for l in analise.lances if l.situacao != "legal"]
        if duvidosos:
            linhas.append("Lances que não fecham com a posição:")
            for l in duvidosos[:14]:
                alvo = f" -> {l.correto}" if l.correto else ""
                linhas.append(f"  {l.texto}{alvo}   ({l.situacao})")
            if len(duvidosos) > 14:
                linhas.append(f"  ... e mais {len(duvidosos) - 14}")
            linhas.append("")

        if not analise.correcoes:
            linhas.append("Nenhuma correção automática a aplicar.")
            messagebox.showinfo("Validar notação", "\n".join(linhas))
            return

        linhas.append(f"{len(analise.correcoes)} correção(ões) de caractere:")
        for c in analise.correcoes[:14]:
            de, para = c.de, c.para or "(vazio)"
            linhas.append(f"  {c.lance_lido} -> {c.lance_correto}: "
                          f"{de!r} vira {para}")
        if len(analise.correcoes) > 14:
            linhas.append(f"  ... e mais {len(analise.correcoes) - 14}")
        linhas.append("")
        linhas.append("Aplicar?")

        if messagebox.askyesno("Validar notação", "\n".join(linhas)):
            n = notacao.aplicar(self.boxes, analise.correcoes)
            self.on_boxes_changed()
            messagebox.showinfo("Validar notação",
                                f"{n} caractere(s) corrigido(s). "
                                "Ctrl+Z desfaz.")

    def abrir_relatorio_treino(self):
        """Abre o relatório do último treino no aplicativo padrão do sistema."""
        caminho = self.learning_service.caminho_relatorio()
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

    # -------------------------------------------------------
    # Treinamento Geral (Batch) & Importacao
    # -------------------------------------------------------

    def run_general_neural_training(self):
        if self._busy("O processamento em lote"):
            return

        if not self.learning_service.load_predictor():
            # O motivo, e não "não encontrado": um par .pth/.json trocado
            # mandaria o usuário procurar um arquivo que está lá (F7.3).
            messagebox.showerror("Modelo neural",
                                 self.learning_service.motivo_do_modelo())
            return

        # Depois da carga, e não antes: aqui ela já roda na thread da UI, então
        # a conferência não acrescenta espera nenhuma.
        self._avisar_do_modelo()

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
                    pages = self.pdf_service.convert_pdf_to_images(
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
