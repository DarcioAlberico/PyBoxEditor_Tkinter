"""
O fluxo de reconhecer da janela principal, num lugar só (PD-22).

Até aqui os 42 métodos — gerar os boxes, detectar e reconhecer pelos quatro modos,
preencher os boxes existentes por caractere ou por linha, o léxico e o idioma da
sessão, aplicar aos semelhantes, dividir e excluir box, ler os diagramas, validar a
notação e as ações sobre o PDF (substituir glifos, corrigir o mapeamento, o OCR do
PDF) — moravam em `ui/main_window.py`, entre os de documento e treino: 1.394 das
5.105 linhas da janela, mais os limiares da cadeia com a medição de cada um. Aqui
eles são o `Reconhecimento`, que a janela cria no `__init__`
(`self.reconhecimento = Reconhecimento(self)`) e para o qual delega, método a método,
com o mesmo nome: `janela.generate_and_fill_neural()` continua existindo, para o menu,
os atalhos e os testes; o corpo é o daqui.

A janela continua dona do estado (`boxes`, `session`, `image`, `selected_index`), dos
serviços (`ocr_service`, `learning_service`, `box_service`), dos diálogos injetáveis e
de `_run_task`, que leva o trabalho para fora da thread do Tk: os métodos falam com
ela por `self.janela`, e quem troca um método da janela num teste continua sendo
ouvido, porque as chamadas internas passam pelo delegado. É o padrão de
`ui/exportacao.py` (item 6 da análise de 2026-10-06).

Os limiares da cadeia (`NEURAL_THRESHOLD`, as travas da linha, o k-NN do híbrido)
vieram junto, com a medição que justifica cada número; `ui.main_window` os reexporta
para quem os importava de lá (`scripts/medidas/medir_cadeia.py`, os testes).
"""
from __future__ import annotations

import os
from dataclasses import replace
from tkinter import filedialog, messagebox
import numpy as np
from PIL import Image
from core import coleta, leitura_de_linha, lexico, livro, proporcao, vertical
from core.chess_pdf_processor import analisar_substituicao
from core.mapa_glifos import caminhos_do_relatorio as caminhos_do_mapa
from core.mapa_glifos import corrigir_mapeamento
from core.relatorio_pdf import caminhos_do_relatorio
from core.searchable_pdf import contar_paginas_com_texto, gerar_pdf_pesquisavel
from core.box_model import SEM_MARGEM
from core.services.box_service import faixas_de_linha
from config.paths import caminhos_modelo_linha
from core.linha_trainer import modelo_utilizavel
from core.services.ocr_service import COMO_INSTALAR_TESSERACT, TesseractSemResposta


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

#: As fontes da âncora que a trava da linha **não** protege (F116).
#:
#: A trava existe para a linha não passar por cima da rede (F20) e do k-NN
#: (F21), e compara `cf >= trava` sem olhar quem respondeu. Só que o último elo
#: da cadeia, o `easyocr`, tem confiança **plana**: a F48 mediu mediana 0,97 no
#: erro e no acerto, e é por isso que ele entra inteiro na fila de revisão
#: (`FONTES_SEMPRE_REVISADAS`). Plana e alta, ela passava pela trava sempre — e
#: o elo que acerta 29% (neural) e 44% (híbrido) no que lhe sobra ficava
#: protegido da linha, que é o melhor conserto que ele tem.
#:
#: Medido nas 10 páginas rotuladas, 10.508 caracteres, contra a produção do
#: mesmo processo (`medir_cadeia.py --sem-trava-para`):
#:
#:     caminho    trava    sem isenção   isentando   trocas novas   conserto / quebra
#:     neural      0,70        97,32%      97,37%              8            6 / 0
#:     híbrido     0,30        97,43%      97,58%             37           17 / 1
#:
#: Nos boxes que o EasyOCR respondeu: 35 dos 38 (neural) e 165 dos 165
#: (híbrido) estavam travados; o acerto neles sobe de 28,95% para 44,74% e de
#: 44,24% para 53,94%. A trava do resto não muda de lugar com a isenção ligada
#: — o híbrido continua melhor em 0,30, e o neural fica no platô da F25.
#:
#: **Só o `easyocr`.** O `learner` e o `neural` têm confiança que ordena (F51:
#: separação 0,795 e 0,634), e é neles que a trava faz o que a F20 mediu.
FONTES_SEM_TRAVA = frozenset({"easyocr"})

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
#: Reproduzir: `python scripts/medidas/medir_cadeia.py --neural --rede 0.4 0.6 0.7 0.8 0.9`.
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
#: `python scripts/medidas/medir_cadeia.py --neural --learner 0.0 0.15 0.2 0.3 0.5 0.7 0.9`.
LEARNER_THRESHOLD_NEURAL = 0.30


class Reconhecimento:
    """O fluxo de reconhecimento da janela principal; `janela` é a `MainWindow`."""

    def __init__(self, janela):
        self.janela = janela

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
        if self.janela._modelo_conferido:
            return
        # Marcado **antes** de saber se há ressalva, e não só quando há. Com a
        # marca só no caminho do aviso, um modelo em ordem fazia `load_predictor`
        # rodar na thread da UI a cada ação — e a primeira carga custa ~2 s de
        # janela congelada. Uma conferência por sessão é o que se quer nos dois
        # casos.
        self.janela._modelo_conferido = True
        aviso = self.janela.learning_service.aviso_do_modelo()
        if aviso:
            messagebox.showwarning("Modelo neural", aviso)

    def _confirmar_motor_de_prosa(self, idioma: str) -> bool:
        """Sonda o Tesseract para `idioma` antes de uma leitura de livro.

        Devolve `True` para seguir. Com o motor em ordem não pergunta nada;
        sem ele, diz o motivo e o custo — a prosa fica só com a cadeia própria —
        e deixa o usuário escolher entre seguir assim e desistir para instalar.
        É a versão pré-tarefa do `PaginaExtraida.motor_indisponivel`: o
        relatório do fim conta o que **já** aconteceu; esta caixa deixa
        escolher **antes** que aconteça.
        """
        disponivel, motivo = self.janela._esperar_sem_travar(
            "Sondando o Tesseract",
            lambda: self.janela.ocr_service.tesseract_disponivel(idioma))
        if disponivel:
            return True
        return messagebox.askyesno(
            "Tesseract indisponível",
            f"O Tesseract não vai rodar: {motivo}.\n\n"
            "Sem ele a prosa fica só com a cadeia própria — que lê o lance "
            "bem e a prosa mal (na página de referência, 27% de erro por "
            "caractere contra 1% com os dois juntos).\n\n"
            "Seguir assim mesmo?\n\n"
            f"Não: cancelar. {COMO_INSTALAR_TESSERACT}",
            default=messagebox.NO)

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
        if not self.janela.learning_service.load_predictor():
            return None
        return self.janela.learning_service.predict_neural

    def generate_boxes_opencv(self, ao_concluir=None):
        """
        Regera os boxes da página numa tarefa (item 9 da revisão de 2026-09-18).

        Era síncrono, na thread da interface: a segmentação de uma página de
        livro a 300 dpi leva segundos — e a primeira vez ainda carrega o modelo
        que arbitra os cortes —, com a janela congelada e sem "Cancelar".
        `ao_concluir()` é a continuação dos "Detectar e reconhecer": roda na
        thread da interface com os boxes novos já na tela, e só se a página
        tiver algum.
        """
        if self.janela.image is None:
            messagebox.showinfo("Aviso", "Carregue uma imagem primeiro.")
            return
        imagem = self.janela.image

        def trabalho(h):
            h.log("Segmentando a página...")
            boxes = self.janela.box_service.generate_boxes_opencv(
                imagem, arbitro=self.janela._arbitro_de_corte())
            # A segmentação não se interrompe no meio; o "Cancelar" descarta
            # o resultado, e os boxes da página ficam como estavam.
            h.raise_if_cancelled()
            return boxes

        def aplicar(boxes):
            self.janela.boxes = boxes
            self.janela._commit_change()
            self.janela.update_canvas()
            self.janela.update_sidebar()
            if ao_concluir is not None and self.janela.boxes:
                ao_concluir()

        self.janela._run_task("Gerar boxes", trabalho, aplicar, indeterminado=True)

    def substitute_chess_glyphs_action(self):
        if self.janela._busy("A conversão"):
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
                messagebox.showwarning(titulo, f"{corpo}\n\n{self.janela._saida_do_beco(rel)}")
            else:
                messagebox.showinfo(titulo, corpo)

        self.janela._run_task("Simular substituição" if simular else "Substituir glifos",
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

    def substitute_glyphs_neural_action(self):
        """Substitui as peças reconhecidas E deixa o PDF pesquisável."""
        self.janela._acao_ocr_pdf(
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
        if self.janela._busy("A correção"):
            return
        self.janela._avisar_do_modelo()

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
            if not self.janela.learning_service.load_predictor():
                raise RuntimeError(self.janela.learning_service.motivo_do_modelo())

            # Só a rede, sem a cadeia de fallback: aqui a pergunta é "que peça é
            # este desenho", e o EasyOCR — que aceita o que vier — só diluiria a
            # votação com palpites de letra.
            def classificar(recorte):
                return self.janela.learning_service.predict_neural(recorte)

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

        self.janela._run_task("Corrigir mapeamento", trabalho, concluir)

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
                "com o livro inteiro, sem teto.\n\n"
                "Havendo teto, o que fica é sorteado sobre o livro inteiro, e "
                "não são os primeiros que aparecerem: senão a classe inteira "
                "sairia das primeiras páginas.",
                initialvalue=digitado)
            if digitado is None:
                return self.janela.CANCELADO
            try:
                return coleta.teto_de_texto(digitado)
            except ValueError as erro:
                messagebox.showwarning(
                    "Teto por classe",
                    f"{erro}\n\nDigite um número, ou deixe o campo em branco "
                    "para não ter teto.")

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
        self.janela.parent.config(cursor="watch")
        self.janela.status.set("Verificando quais páginas já têm texto...")
        self.janela.parent.update_idletasks()
        try:
            com_texto, total = contar_paginas_com_texto(input_pdf)
        except Exception:
            # Arquivo ilegível: quem reporta é a tarefa, com o diálogo de erro
            # de sempre. Aqui só não dá para perguntar nada.
            return True
        finally:
            self.janela.parent.config(cursor="")
            self.janela.status.set("Pronto.")

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
        if self.janela._busy("A conversão"):
            return
        self.janela._avisar_do_modelo()

        input_pdf = filedialog.askopenfilename(
            title="Selecionar PDF Escaneado",
            filetypes=[("Arquivos PDF", "*.pdf")]
        )
        if not input_pdf:
            return

        pular = self.janela._perguntar_sobre_paginas_com_texto(input_pdf)
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
            self.janela.learning_service.load_predictor()
            h.log("Carregando base de referência...")
            learner = self.janela.learning_service._get_learner()
            predictor = self.janela.learning_service._predictor

            def reconhecer(recorte):
                char, _fonte, conf = self.janela.ocr_service.fallback_chain(
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
                ler_linha=self.janela.ocr_service.easyocr_linha_conf,
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

        self.janela._run_task(titulo, trabalho, concluir)

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
        pagina = np.array(self.janela.image)
        faixas = faixas_de_linha(self.janela.boxes)

        pares = []
        for b, (topo, base) in zip(self.janela.boxes, faixas):
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
        if self.janela.image is None or not self.janela.boxes:
            messagebox.showinfo("Aviso", "Não há boxes para preencher.")
            return
        if self.janela._busy(titulo):
            return

        recortes = self.janela._recortes_dos_boxes()
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
            for b, (char, fonte, conf) in zip(self.janela.boxes, resultados):
                b.char = char
                b.source = fonte if char else ""
                b.confidence = conf
                fontes[fonte] = fontes.get(fonte, 0) + 1

            self.janela._commit_change()
            self.janela.update_sidebar()
            self.janela.update_canvas()

            texto = resumo(fontes, len(resultados))
            if saida["cancelado"]:
                texto += f"\n\nCancelado: {len(resultados)} de {total} boxes processados."
                self.janela.status.set(f"{titulo}: cancelado ({len(resultados)}/{total}).")
            messagebox.showinfo(titulo, texto)

        self.janela._run_task(titulo, trabalho, aplicar)

    def auto_fill_characters(self):
        whitelist = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,!?+-=()#:/\'\""

        # O disjuntor da janela (PD-01), o mesmo do `livro.extrair` (F124): um
        # box sem resposta no prazo fica vazio e a leitura segue; depois de
        # `BOXES_SEM_RESPOSTA_ATE_DESISTIR` seguidos o executável é dado como
        # preso, e o resto dos boxes não o consulta — antes, o primeiro prazo
        # vencido derrubava a tarefa e jogava fora o que já estava lido.
        estado = {"seguidas": 0, "sem_resposta": 0, "desligado": False}

        def preparar(h):
            def classificar(justo, _com_faixa):
                if estado["desligado"]:
                    return ("", "vazio", 0.0)
                try:
                    ch, c = self.janela.ocr_service.tesseract_ocr_conf(
                        Image.fromarray(justo), whitelist)
                except TesseractSemResposta:
                    estado["sem_resposta"] += 1
                    estado["seguidas"] += 1
                    if estado["seguidas"] >= self.janela.BOXES_SEM_RESPOSTA_ATE_DESISTIR:
                        estado["desligado"] = True
                    return ("", "vazio", 0.0)
                estado["seguidas"] = 0
                return (ch, "tesseract" if ch else "vazio", c)
            return classificar

        def resumo(fontes, n):
            texto = f"Processados: {n} boxes."
            if estado["sem_resposta"]:
                texto += (f"\n\nO Tesseract não respondeu no prazo em "
                          f"{estado['sem_resposta']} box(es)")
                if estado["desligado"]:
                    texto += (", e foi desligado para o resto da página: o "
                              "executável parece preso. Os boxes que ele não "
                              "leu ficaram vazios.")
                else:
                    texto += "; esses ficaram vazios."
            return texto

        self.janela._preencher_boxes("OCR (Tesseract)", preparar, resumo)

    def auto_fill_characters_easyocr(self):
        from core.avaliacao_pagina import normalizar

        def preparar(h):
            # O k-NN é consultado em cada box que o EasyOCR leu (PD-13): é a
            # concordância dos dois que diz se a leitura vai à fila. A base
            # carrega aqui, na thread da tarefa, e não na da interface.
            h.log("Carregando a base do k-NN...")
            knn = self.janela.learning_service.predict_learner

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
                ch, c = self.janela.ocr_service.easyocr_ocr_conf(
                    justo, contexto=com_faixa)
                if not ch:
                    return (ch, "vazio", c)
                lido_pelo_knn, _conf_knn = knn(justo)
                if normalizar(lido_pelo_knn) != normalizar(ch):
                    return (ch, self.janela.FONTE_EASYOCR_DISCORDA, c)
                return (ch, "easyocr_so", c)
            return classificar

        def resumo(fontes, n):
            preenchidos = (fontes.get("easyocr_so", 0)
                           + fontes.get(self.janela.FONTE_EASYOCR_DISCORDA, 0))
            texto = (f"Processados: {n} boxes.\n"
                     f"Caracteres preenchidos: {preenchidos}")
            if fontes.get(self.janela.FONTE_EASYOCR_DISCORDA):
                texto += (f"\nO k-NN discordou em "
                          f"{fontes[self.janela.FONTE_EASYOCR_DISCORDA]}: esses vão "
                          f"para a revisão.")
            return texto

        self.janela._preencher_boxes("OCR (EasyOCR)", preparar, resumo)

    def generate_and_fill_easyocr(self):
        # `_busy` antes de gerar — ver o comentário sobre `generate_and_fill_linha`.
        if self.janela._busy("OCR (EasyOCR)"):
            return
        self.janela.generate_boxes_opencv(ao_concluir=self.janela.auto_fill_characters_easyocr)

    def auto_fill_characters_paddleocr(self):
        """Preenche os boxes atuais com o reconhecedor opcional PaddleOCR."""
        def preparar(h):
            def classificar(justo, _com_faixa):
                ch, c = self.janela.ocr_service.paddleocr_ocr_conf(justo)
                return (ch, "paddleocr" if ch else "vazio", c)
            return classificar

        self.janela._preencher_boxes(
            "OCR (PaddleOCR)", preparar,
            lambda fontes, n: (f"Processados: {n} boxes.\n"
                               f"Caracteres preenchidos: "
                               f"{fontes.get('paddleocr', 0)}"),
        )

    def auto_fill_characters_linha(self, languages=("en",), ao_concluir=None):
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
                justo, contexto = self.janela._recortes_do_box(pagina, b, faixas)
                ch, cf = self.janela.ocr_service.easyocr_ocr_conf(
                    justo, languages=languages, contexto=contexto)
                # Ver `auto_fill_characters_easyocr`: aqui ele é o leitor.
                return ch, cf, "easyocr_so"
            return ler_caractere

        self.janela._preencher_por_linha(
            "OCR (EasyOCR por linha)", preparar,
            lambda fontes: (
                f"Decididos pela linha: {fontes.get('easyocr_linha', 0)}\n"
                f"Só pelo caractere: {fontes.get('easyocr_so', 0)}"),
            languages=languages,
            ao_concluir=ao_concluir,
        )

    def auto_fill_characters_linha_treinada(self):
        """Aplica o CRNN/CTC treinado às linhas e distribui o texto nos boxes."""
        if self.janela.image is None or not self.janela.boxes:
            messagebox.showinfo("OCR treinado", "Não há boxes para preencher.")
            return
        if self.janela._busy("OCR treinado"):
            return
        modelo, meta = caminhos_modelo_linha()
        if not (modelo.exists() and meta.exists()):
            messagebox.showinfo("OCR treinado", "Treine o modelo sequencial primeiro.")
            return
        # O modelo que não passa no portão de produção ainda pode ser
        # aplicado — é aqui que se olha o que ele lê —, mas quem aplica sabe
        # o que está aplicando, e o texto vai para os boxes com a fonte
        # `linha_treinada`, que o filtro de origem separa.
        utilizavel, motivo = modelo_utilizavel(meta, modelo)
        if not utilizavel and not messagebox.askyesno(
                "OCR treinado abaixo do limite",
                f"{motivo[0].upper()}{motivo[1:]}.\n\n"
                "Aplicar assim mesmo, sobrescrevendo o texto dos boxes desta "
                "página com a leitura dele?\n\nNão: cancelar.",
                default=messagebox.NO):
            return

        linhas = leitura_de_linha.linhas_da_pagina(self.janela.boxes)
        recortes = []
        for linha in linhas:
            x1, y1 = min(b.x1 for b in linha), min(b.y1 for b in linha)
            x2, y2 = max(b.x2 for b in linha), max(b.y2 for b in linha)
            recortes.append(np.array(self.janela.image.crop((x1 - 10, y1 - 10, x2 + 10, y2 + 10))))

        def trabalho(h):
            resultados = []
            for pos, recorte in enumerate(recortes):
                texto, confiancas = self.janela.ocr_service.linha_treinada_detalhada(
                    recorte, modelo, meta)
                resultados.append((texto.replace(" ", ""), confiancas))
                h.progress(pos + 1, len(recortes), f"linha {pos + 1}/{len(recortes)}")
            return resultados

        def concluir(resultados):
            alterados = 0
            for linha, (texto, confiancas) in zip(linhas, resultados):
                sugeridos = leitura_de_linha.distribuir([""] * len(linha), texto)
                for indice, (box, char) in enumerate(zip(linha, sugeridos)):
                    if char:
                        box.char = char
                        box.confidence = (confiancas[indice]
                                          if indice < len(confiancas) else 0.0)
                        box.source = "linha_treinada"
                        alterados += 1
            self.janela._commit_change()
            self.janela.update_sidebar()
            self.janela.update_canvas()
            messagebox.showinfo("OCR treinado", f"{alterados} boxes preenchidos.")

        self.janela._run_task("OCR treinado por linha", trabalho, concluir)

    def _recortes_do_box(self, pagina, b, faixas):
        """`(justo, com a faixa da linha)` — ver `_recortes_dos_boxes`."""
        justo = vertical.recorte_de_pe(pagina, b)
        topo, base = faixas[id(b)]
        if (topo, base) == (b.y1, b.y2):
            return justo, justo
        return justo, vertical.recorte_de_pe(
            pagina, replace(b, y1=topo, y2=base))

    def _preencher_por_linha(self, titulo, preparar, resumo,
                             conf_maxima_para_trocar=None,
                             exigir_confianca_linha=False,
                             confianca_linha_minima=None,
                             confianca_ancora_maxima=None,
                             ao_concluir=None, languages=("en",),
                             poda=None):
        """
        Como `_preencher_boxes`, mas o laço é por **linha** e não por box.

        `preparar(h, pagina, faixas)` devolve
        `ler_caractere(box) -> (char, confiança, fonte)`, que é a âncora do
        alinhamento. `conf_maxima_para_trocar` é a trava da F18 — ver
        `leitura_de_linha.ler_pagina`.

        `poda(pagina)` monta o `podar` de `ler_pagina` — a geometria da linha
        corrigindo a âncora antes de a linha ser lida (F123). É chamada na
        thread de trabalho, **depois** de `preparar`, porque é ali que o modelo
        de quem ela pede as candidatas acabou de ser carregado.

        Cancelar devolve o parcial por linha: o que já foi lido é aplicado, e o
        resto dos boxes fica **como estava** em vez de ser esvaziado.
        """
        if self.janela.image is None or not self.janela.boxes:
            messagebox.showinfo("Aviso", "Não há boxes para preencher.")
            return
        if self.janela._busy(titulo):
            return

        # Cópia na thread da UI, pela razão de `_recortes_dos_boxes`.
        pagina = np.array(self.janela.image)
        linhas = leitura_de_linha.linhas_da_pagina(self.janela.boxes)
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

        # Um recorte que o OCR não consegue ler não pode custar a página: o
        # cancelamento aplica o parcial, e um erro solto no meio do laço não
        # aplicava nada do que já estava lido. O box fica vazio, e o diálogo
        # de fim diz quantos foram e qual foi o primeiro erro.
        falhas = []

        def trabalho(h):
            ler_caractere = preparar(h, pagina, faixas, margens)
            lidos = leitura_de_linha.ler_pagina(
                pagina, linhas,
                ler_faixa=lambda faixa: self.janela.ocr_service.easyocr_linha_conf(
                    faixa, languages=languages),
                ler_caractere=ler_caractere,
                podar=None if poda is None else poda(pagina),
                # **Sem `deslocam`, e a F36 mediu que tem de ser.** A linha com
                # figurina parece a que mais precisa de filtro e é a que menos:
                # o `_alinhar` absorve o deslocamento, e filtrar joga fora as
                # correções do resto da linha. Ver `leitura_de_linha.em_bloco`.
                conf_maxima_para_trocar=conf_maxima_para_trocar,
                # A trava não segura o box que o EasyOCR respondeu (F116): a
                # confiança dele é plana, e a linha acerta mais que ele ali.
                fontes_sem_trava=FONTES_SEM_TRAVA,
                exigir_confianca_linha=exigir_confianca_linha,
                confianca_linha_minima=confianca_linha_minima,
                confianca_ancora_maxima=confianca_ancora_maxima,
                cancelado=lambda: h.cancelled,
                progresso=lambda i, n: h.progress(i, n, f"linha {i}/{n}"),
                ao_falhar=lambda b, e: falhas.append(f"{type(e).__name__}: {e}"),
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

            self.janela._commit_change()
            self.janela.update_sidebar()
            self.janela.update_canvas()

            feitos = len(saida["lidos"])
            texto = f"Linhas: {len(linhas)}\n" + resumo(fontes)
            if saida["cancelado"]:
                texto += (f"\n\nCancelado: {feitos} de {total} boxes "
                          f"processados; o resto ficou como estava.")
                self.janela.status.set(f"{titulo}: cancelado ({feitos}/{total}).")
            if falhas:
                texto += (f"\n\n{len(falhas)} leitura(s) falharam e o box "
                          f"ficou vazio. Primeiro erro:\n{falhas[0]}")
                messagebox.showwarning(titulo, texto)
            else:
                messagebox.showinfo(titulo, texto)
            if ao_concluir:
                ao_concluir()

        self.janela._run_task(titulo, trabalho, aplicar)

    def generate_and_fill_linha(self):
        if self.janela._busy("OCR (EasyOCR por linha)"):
            return
        self.janela.generate_boxes_opencv(ao_concluir=self.janela.auto_fill_characters_linha)

    def generate_and_fill_combined(self):
        if self.janela._busy("Detectar e preencher (Híbrido)"):
            return

        def preencher():
            # O denominador do veto geométrico (F106), tirado da página inteira
            # uma vez só — é o que separa o ponto do quadrado. Aqui, e não
            # dentro de `preparar`: aquele roda na thread de trabalho, e
            # `self.janela.boxes` é da UI.
            referencia = proporcao.altura_de_referencia(self.janela.boxes)
            # E o idioma do livro (F117), pela mesma razão: ele pode perguntar.
            idioma = self.janela.idioma_da_sessao()

            def preparar(h, pagina, faixas, margens):
                h.log("Carregando base de referência...")
                learner = self.janela.learning_service._get_learner()

                def ler_caractere(b):
                    justo, contexto = self.janela._recortes_do_box(pagina, b, faixas)
                    # `neural_threshold` não é usado — esta ação não carrega a
                    # rede —, mas fica igual ao outro para o dia em que alguém
                    # passar um predictor por aqui e esperar o mesmo roteamento.
                    leitura = self.janela.ocr_service.fallback_chain_detalhado(
                        justo, learner=learner, contexto=contexto,
                        neural_threshold=LEARNER_THRESHOLD_HIBRIDO,
                        learner_threshold=LEARNER_THRESHOLD_HIBRIDO,
                        altura_de_referencia=referencia,
                        idioma=idioma,
                    )
                    if leitura.fonte not in ("learner", "easyocr"):
                        return ("", 0.0, "vazio")
                    margens[id(b)] = leitura.margem
                    return (leitura.char, leitura.confianca, leitura.fonte)
                return ler_caractere

            self.janela._preencher_por_linha(
                "Detectar e preencher (Híbrido)", preparar,
                lambda fontes: (f"Encontrados via Base: {fontes.get('learner', 0)}\n"
                                f"Encontrados via OCR: {fontes.get('easyocr', 0)}\n"
                                f"Corrigidos pela linha: "
                                f"{fontes.get('easyocr_linha', 0)}"
                                + self.janela._frase_do_idioma(idioma)),
                conf_maxima_para_trocar=CONF_MAXIMA_PARA_A_LINHA_HIBRIDO,
            )

        self.janela.generate_boxes_opencv(ao_concluir=preencher)

    @staticmethod
    def _frase_do_idioma(idioma):
        """A linha do diálogo que diz que máscara de alfabeto valeu (F117)."""
        if idioma is None:
            return "\nMáscara de alfabeto: desligada (página sem livro)"
        nome = {"en": "inglês", "pt": "português"}.get(idioma, idioma)
        return f"\nMáscara de alfabeto: {nome}"

    def generate_and_fill_neural(self):
        titulo = "Detectar e preencher (Neural)"
        if self.janela._busy(titulo):
            return
        # Antes do trabalho, não depois: este é o caminho em que a confiança da
        # rede vira `b.confidence`, e é ela que decide a cor do box e o filtro
        # "só pendentes". Saber que a escala não está calibrada muda como o
        # usuário lê o resultado que está prestes a gerar.
        self.janela._avisar_do_modelo()
        # **Sem modelo, a ação para aqui — e não segue sem a rede.** O
        # `aviso_do_modelo` só fala de modelo que carregou; quando a carga
        # falha ele cala, e a cadeia, vendo `loaded=False`, pulava a rede em
        # silêncio. O que sobrava era o k-NN em 0,30 com a trava da linha em
        # 0,70: a combinação que a tabela de `CONF_MAXIMA_PARA_A_LINHA_HIBRIDO`
        # mediu como a pior (93,57% contra 95,68%), com o diálogo de fim
        # dizendo só "Neural: 0". Quem quer ler sem a rede tem o «Híbrido».
        if not self.janela.learning_service.load_predictor():
            messagebox.showerror(titulo, self.janela.learning_service.motivo_do_modelo())
            return

        def preencher():
            # Na thread da UI, pela razão dita em `generate_and_fill_combined`.
            referencia = proporcao.altura_de_referencia(self.janela.boxes)
            idioma = self.janela.idioma_da_sessao()

            def preparar(h, pagina, faixas, margens):
                h.log("Carregando modelo neural...")
                if not self.janela.learning_service.load_predictor():
                    raise RuntimeError(self.janela.learning_service.motivo_do_modelo())
                h.log("Carregando base de referência...")
                learner = self.janela.learning_service._get_learner()
                predictor = self.janela.learning_service._predictor

                def ler_caractere(b):
                    justo, contexto = self.janela._recortes_do_box(pagina, b, faixas)
                    leitura = self.janela.ocr_service.fallback_chain_detalhado(
                        justo, predictor=predictor, learner=learner,
                        contexto=contexto,
                        neural_threshold=NEURAL_THRESHOLD,
                        learner_threshold=LEARNER_THRESHOLD_NEURAL,
                        altura_de_referencia=referencia,
                        idioma=idioma,
                    )
                    margens[id(b)] = leitura.margem
                    return (leitura.char, leitura.confianca, leitura.fonte)
                return ler_caractere

            def poda(pagina):
                # A caixa pela geometria da linha (F112), que o caminho do livro
                # já tinha (F123). As candidatas são as da rede, que `preparar`
                # acabou de carregar; só o que a rede leu é trocado.
                from core import geometria_da_linha
                return geometria_da_linha.poda_da_ancora(
                    pagina, self.janela.learning_service.candidatas)

            self.janela._preencher_por_linha(
                titulo, preparar,
                lambda fontes: (f"Neural: {fontes.get('neural', 0)}\n"
                                f"Referência: {fontes.get('learner', 0)}\n"
                                f"EasyOCR: {fontes.get('easyocr', 0)}\n"
                                f"Corrigidos pela linha: "
                                f"{fontes.get('easyocr_linha', 0)}\n"
                                f"Corrigidos pela geometria: "
                                f"{fontes.get('geometria', 0)}"
                                + self.janela._frase_do_idioma(idioma)),
                conf_maxima_para_trocar=CONF_MAXIMA_PARA_A_LINHA,
                poda=poda,
            )

        self.janela.generate_boxes_opencv(ao_concluir=preencher)

    def lexico_da_sessao(self):
        """
        O léxico desta sessão: a lista geral mais a deste livro (F9.2).

        Carregado uma vez por documento, não uma vez por processo — a lista do
        usuário é por livro, e mantê-la de um documento para o outro daria ao
        Kasparov o vocabulário do Yusupov, que é o contrário do motivo da F9.2.
        `_esquecer_lexico` é quem invalida, na abertura.
        """
        if self.janela._lexico is None:
            self.janela._lexico = lexico.carregar(
                caminho_usuario=self.janela._caminho_do_lexico())
        return self.janela._lexico

    def _caminho_do_lexico(self):
        """Onde fica a lista deste livro, ou None sem documento aberto."""
        if self.janela.session is None:
            return None
        return lexico.caminho_do_usuario(self.janela.session.path, self.janela.session.is_pdf)

    def _esquecer_lexico(self):
        """Força a recarga do léxico e das suspeitas — chamada ao abrir."""
        self.janela._lexico = None
        self.janela._cache_suspeitas = (None, [])
        # O idioma é do livro, como o léxico: o próximo documento pergunta de
        # novo. `None` aqui quer dizer "ainda não conferido", e não "sem idioma".
        self.janela._idioma = None

    @staticmethod
    def _idioma_do_livro(caminho_pdf, perguntar=True):
        """
        `(idioma, detectado)` de um PDF (F109).

        A camada de texto responde em 72% das páginas do corpus; onde não há
        camada — a digitalização de verdade — é o usuário quem diz, porque a
        máscara errada apagaria o `ç` do livro inteiro. Um lugar só para a
        exportação e para a tela, para as duas perguntarem a mesma coisa.

        Com `perguntar=False` não abre caixa nenhuma: devolve `(None, False)`
        quando a camada não diz — é o que a caixa de exportação usa para
        preencher o idioma e deixar o usuário escolher ali, e não numa
        pergunta à parte.
        """
        idioma = livro.idioma_do_pdf(caminho_pdf)
        if idioma is not None:
            return idioma, True
        if not perguntar:
            return None, False
        return ("pt" if messagebox.askyesno(
            "Idioma do livro",
            "O livro é em português?\n\n"
            "O PDF não tem camada de texto que diga o idioma, e ele "
            "decide que letras o OCR pode responder: num livro em inglês "
            "a letra acentuada é sempre erro de leitura, e deixa de "
            "competir com a certa.\n\n"
            "Não: o livro é tratado como inglês.") else "en"), False

    def idioma_da_sessao(self):
        """
        O idioma do documento aberto, ou `None` — que desliga a máscara.

        Conferido **uma vez por documento**, na primeira ação que o pede, e não
        na abertura: quem abre um PDF para arrastar boxes não precisa responder
        sobre idioma. A pergunta, quando há, é a mesma da exportação.

        Uma imagem solta fica sem idioma, e é a regra de `core.alfabeto`: quem
        lê uma página avulsa não sabe de que livro ela é, e a máscara sem
        opinião é a cadeia de antes — nunca a máscara errada.
        """
        if self.janela._idioma is None:
            idioma = None
            if self.janela.session is not None and self.janela.session.is_pdf:
                idioma, _detectado = self.janela._idioma_do_livro(self.janela.session.path)
            # Guardado como tupla para distinguir "conferido: nenhum" de "ainda
            # não conferido", que é o `None` cru.
            self.janela._idioma = (idioma,)
        return self.janela._idioma[0]

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
        return self.janela.aprender_palavras_das_paginas(
            [self.janela.boxes if boxes is None else boxes])

    def aprender_palavras_das_paginas(self, paginas):
        """
        O mesmo, para várias páginas de uma vez, gravando o arquivo uma só vez.

        Existe por causa do "Salvar todas as páginas": chamar a versão de uma
        página em laço reescreveria a lista inteira a cada página gravada, e a
        lista é a verdade do arquivo — quem edita à mão entre uma página e outra
        não deve ver o programa desfazendo a edição N vezes.
        """
        lex = self.janela.lexico_da_sessao()
        caminho = self.janela._caminho_do_lexico()
        if not lex.sinaliza or not caminho:
            return []
        novas = []
        for boxes in paginas:
            # Sem `caminho`: só mexe no léxico em memória. A gravação é uma só,
            # depois do laço.
            novas.extend(lexico.aprender_da_pagina(boxes, lex))
        if novas:
            lexico.salvar_do_usuario(caminho, lex.do_usuario)
            self.janela._cache_suspeitas = (None, [])
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
        uc = self.janela._ultima_correcao
        if uc is not None:
            _, box, anterior, novo = uc
            for i, b in enumerate(self.janela.boxes):
                if b is box and b.char == novo and novo:
                    return i, novo, anterior

        if 0 <= self.janela.selected_index < len(self.janela.boxes):
            b = self.janela.boxes[self.janela.selected_index]
            return self.janela.selected_index, b.char, None
        return None

    def aplicar_aos_semelhantes(self):
        if self.janela.image is None or not self.janela.boxes:
            return
        if self.janela._busy("A aplicação em lote"):
            return

        referencia = self.janela.referencia_do_lote()
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

        escolhidos = self.janela.DIALOGO_SEMELHANTES(
            self.janela.parent, self.janela.image, self.janela.boxes, indice, alvo, leitura).mostrar()
        if escolhidos is None:
            self.janela.status.set("Lote cancelado.")
            return
        if not escolhidos:
            self.janela.status.set("Nenhum box semelhante marcado.")
            return

        n = self.janela.aplicar_em_lote(escolhidos, alvo)
        self.janela.status.set(f"{n} box(es) marcados como “{alvo}” em lote. "
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
            if not (0 <= i < len(self.janela.boxes)):
                continue
            b = self.janela.boxes[i]
            if b.char == char:
                continue
            b.char = char
            b.confidence = 1.0
            b.source = self.janela.ORIGEM_LOTE
            mudados += 1

        if mudados:
            self.janela._commit_change()
            self.janela.update_sidebar()
            self.janela.update_canvas()
        return mudados

    def ocr_selected_box(self):
        if (self.janela.image is None or self.janela.selected_index < 0
                or self.janela.selected_index >= len(self.janela.boxes)):
            return

        b = self.janela.boxes[self.janela.selected_index]
        # Pelo funil, e não por `self.janela.image.crop`: o Tesseract quer o glifo de
        # pé (F8.1) e escuro sobre claro (F10), como qualquer classificador.
        crop = Image.fromarray(vertical.recorte_de_pe(np.array(self.janela.image), b))
        try:
            ch = self.janela.ocr_service.tesseract_ocr(crop)
        except Exception as erro:  # noqa: BLE001 — ação síncrona, fora de _run_task
            # O serviço deixou de devolver "" quando o Tesseract falta: aqui,
            # no botão, o motivo é dito na hora, com o que fazer.
            messagebox.showerror("OCR (box)", str(erro))
            return

        if not ch:
            messagebox.showinfo("OCR", "Nenhum caractere reconhecido.")
            return

        self.janela.char_entry.delete(0, "end")
        self.janela.char_entry.insert(0, ch)

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
        if self.janela.selected_index < 0 or self.janela.selected_index >= len(self.janela.boxes):
            return

        b = self.janela.boxes[self.janela.selected_index]
        pagina = np.array(self.janela.image) if self.janela.image is not None else None
        b1, b2 = self.janela.box_service.split_box(b, pagina)

        self.janela.boxes.pop(self.janela.selected_index)
        self.janela.boxes.insert(self.janela.selected_index, b2)
        self.janela.boxes.insert(self.janela.selected_index, b1)
        self.janela._commit_change()

        self.janela.select_box(self.janela.selected_index)
        if not self.janela.modo_digitacao:
            self.janela.char_entry.focus_set()
            self.janela.char_entry.select_range(0, "end")

    def delete_selected_box(self):
        if self.janela.selected_index < 0 or self.janela.selected_index >= len(self.janela.boxes):
            return
        self.janela.boxes.pop(self.janela.selected_index)
        if self.janela.selected_index >= len(self.janela.boxes):
            self.janela.selected_index = len(self.janela.boxes) - 1
        self.janela._commit_change()
        self.janela.update_sidebar()
        self.janela.update_canvas()

    def extrair_diagramas(self):
        """
        Lê a posição dos diagramas da página (F7.1, corrigida na F8.3).

        **Os boxes da página não servem para achar o diagrama, e isso era um
        defeito calado.** O tabuleiro é o contorno grande e quadrado que a F1.8
        descarta — e `generate_boxes_opencv` descarta antes de devolver. Passar
        `self.janela.boxes` para `localizar` é pedir que ela ache entre os contornos
        justamente aquele que já não está lá: medido em 6 páginas reais com
        diagrama, 0 encontrados contra 2 ou 3 por página. O comando respondia
        sempre "nenhum diagrama encontrado", e o texto ainda culpava a borda da
        página.

        A geração aqui é própria e sem descarte. Custa uma passada de contornos
        (0,36 s numa página de 1.605 boxes) e não mexe em `self.janela.boxes`, que
        continua sendo a lista de caracteres da página.

        **Duas páginas de livro têm custo de ordens diferentes** (F96), e desde
        ela o comando tem dois caminhos em vez de um:

        | página | contornos | caminho | custo |
        |---|---:|---|---:|
        | comum | ~2.000 | `localizar`, com os contornos | ~1 s |
        | de trama | 85.903 | detector da F96, sem contorno | 0,76 s |

        Quem decide é o `MAX_CONTORNOS_DE_TEXTO`, e a decisão é **por caminho,
        não por desistência**: acima do teto o estágio de caracteres devolve
        lista vazia, e `ler_pagina` procura o tabuleiro pelo desenho dele. Sem
        isso a página de trama custava 63 s só no merge — e, antes da F96, 250 s.

        **O modelo de texto entra junto desde a F95**, e não é para ler o
        tabuleiro: é para ler o que está impresso em volta dele — o título e as
        coordenadas das casas. Sem ele o comando ainda acha os diagramas e
        ainda diz se há coordenadas (a prova disso é geométrica), mas o título
        fica sem texto e a orientação, sem resposta. Por isso a falta do modelo
        aqui **não** é erro: o comando segue sem ele.
        """
        from core import diagrama as diag

        if self.janela.image is None:
            messagebox.showinfo("Diagramas", "Abra uma imagem ou PDF primeiro.")
            return
        imagem = self.janela.image
        com_o_modelo = []

        # A leitura roda numa tarefa desde o item 9 da revisão de 2026-09-18:
        # carregar a rede, segmentar e passar cada casa pelas duas CNNs levava
        # de um a três segundos com a janela congelada. O diálogo abre depois,
        # na thread da interface.
        def trabalho(h):
            h.log("Carregando o modelo...")
            classificar = None
            if self.janela.learning_service.load_predictor():
                classificar = self.janela.learning_service.predict_neural
                com_o_modelo.append(True)
            h.log("Procurando os diagramas...")
            # **O estágio pedido passou a ser o que `localizar` espera** (F96).
            # Este comando chamava `generate_boxes_opencv(descartar_nao_texto=
            # False)`, que não para aí: segue para `dividir_linhas_coladas`
            # medindo perfil de tinta dentro dos blocos grandes que o descarte
            # teria tirado — o custo que o docstring do `boxes_antes_do_descarte`
            # documenta desde a F26, e que ninguém tinha vindo cobrar aqui.
            #
            # **E com teto**, que é o que faz a página de trama responder. Sem
            # ele a 96 do Yusupov leva 63 s só no merge; com ele ela chega ao
            # `ler_pagina` sem caixa nenhuma, e lá o detector da F96 acha o
            # diagrama em 0,76 s. O teto não perde a página: troca o caminho.
            contornos, _th, _escala, _cinza = (
                self.janela.box_service.boxes_antes_do_descarte(
                    imagem, max_contornos=self.janela.box_service.MAX_CONTORNOS_DE_TEXTO))
            h.raise_if_cancelled()
            leituras = diag.ler_pagina(imagem, contornos, classificar)
            h.raise_if_cancelled()
            return leituras

        def falhou(exc):
            if isinstance(exc, diag.ModeloAusente):
                messagebox.showerror("Diagramas", str(exc))
                return True
            return False

        def mostrar(leituras):
            if com_o_modelo:
                # O título do diagrama é texto lido pela rede, e texto lido pela
                # rede leva o aviso do modelo junto (F26) — a mesma regra dos
                # outros caminhos, que a F95 fez este comando passar a ter.
                self.janela._avisar_do_modelo()
            if not leituras:
                messagebox.showinfo(
                    "Diagramas",
                    "Nenhum diagrama encontrado nesta página.\n\n"
                    "O tabuleiro é reconhecido por ser um desenho grande, quadrado "
                    "e em xadrez — inclusive quando está impresso dentro de um "
                    "painel. Um diagrama cortado na borda da página não casa.")
                return
            fen = self.janela.DIALOGO_DIAGRAMA(self.janela.parent, imagem, leituras,
                                        origem=self.janela._origem_da_pagina()).mostrar()
            if fen:
                self.janela.parent.clipboard_clear()
                self.janela.parent.clipboard_append(fen)
                self.janela.status.set(f"FEN copiado: {fen}")
            else:
                self.janela.status.set(f"{len(leituras)} diagrama(s) lidos.")

        self.janela._run_task("Ler posição dos diagramas", trabalho, mostrar,
                       indeterminado=True, ao_falhar=falhou)

    def _origem_da_pagina(self) -> str:
        """
        Nome que identifica a página atual, para a procedência da amostra (F8.3).

        Sai do mesmo lugar que o `.box` da página usa, quando há sessão; senão,
        do nome do arquivo aberto.
        """
        if self.janela.session is not None:
            return os.path.basename(self.janela.session.page_stem(self.janela.current_pdf_page))
        if self.janela.image_path:
            return os.path.splitext(os.path.basename(self.janela.image_path))[0]
        return ""

    def validar_notacao(self):
        """
        Confronta a notação da página com as regras do xadrez (F1.7).

        Roda direto na thread da UI: medido em 37 ms para 1.487 boxes, bem
        dentro do critério de 100 ms da F4.1. Passar pelo BackgroundTask custaria
        mais em cerimônia do que economiza.
        """
        from core import notacao

        if not self.janela.boxes:
            messagebox.showinfo("Validar notação",
                                "Nenhum box na página.")
            return

        analise = notacao.analisar(self.janela.boxes)
        if not analise.lances:
            messagebox.showinfo(
                "Validar notação",
                "Nenhuma sequência de lances foi reconhecida nesta página.\n\n"
                "A leitura começa num '1.' — sem o começo da partida não há "
                "posição de onde partir.")
            return

        linhas = [analise.resumo(), ""]
        duvidosos = [lance for lance in analise.lances
                     if lance.situacao != "legal"]
        if duvidosos:
            linhas.append("Lances que não fecham com a posição:")
            for lance in duvidosos[:14]:
                alvo = f" -> {lance.correto}" if lance.correto else ""
                linhas.append(f"  {lance.texto}{alvo}   ({lance.situacao})")
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
            n = notacao.aplicar(self.janela.boxes, analise.correcoes)
            self.janela.on_boxes_changed()
            messagebox.showinfo("Validar notação",
                                f"{n} caractere(s) corrigido(s). "
                                "Ctrl+Z desfaz.")
