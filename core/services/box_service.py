import cv2
import numpy as np
from typing import List, Optional, Set, Tuple
from PIL import Image

from core import negativo, preprocess, trama, vertical
from core.box_model import BoxEntry


class BoxService:
    """
    Serviço puro (sem UI) para geração, ordenação, merge e manipulação de boxes.
    """

    @staticmethod
    def generate_boxes_opencv(image: Image.Image, threshold: int = 180,
                              method: str = "auto",
                              separar_colados="auto",
                              descartar_nao_texto: bool = True,
                              arbitro=None) -> List[BoxEntry]:
        """
        Gera boxes automaticamente a partir de uma imagem PIL (grayscale).

        `method` é passado a `preprocess.binarize`; "fixed" com `threshold`
        reproduz o comportamento anterior à F1.5.

        `arbitro` é o classificador que confirma cada corte de glifo colado
        (F1.5b), na forma `(recorte_cinza) -> (char, confiança)`.

        **`separar_colados` tem três valores, e o padrão não é `True` por um
        motivo medido.** Sem árbitro, o separador tira 2,3 pontos de F1 da
        página — corta 182 glifos bons para acertar 73 colagens. Com árbitro,
        devolve 0,3 acima de não separar. Deixar `True` como padrão seria
        deixar armada a única configuração que a medição reprova.

            "auto"  (padrão) separa só se houver árbitro
            True             separa mesmo sem árbitro (a configuração ruim,
                             mantida para reproduzir as medições da F1.5)
            False            nunca separa
        """
        img_cv = np.array(image)
        th = preprocess.binarize(img_cv, method, fixed_threshold=threshold)
        # A trama de meio-tom sai antes de qualquer coisa medir caractere: ela
        # é 95,8% dos contornos da página 18 do Yusupov e envenena toda régua
        # relativa do pipeline.
        th = preprocess.remover_textura(img_cv, th)
        escala = preprocess.escala_de_texto(th)

        contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        boxes = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if w < 2 or h < 2:
                continue
            boxes.append(BoxEntry("", x, y, x + w, y + h))

        boxes.sort(key=lambda b: (b.y1, b.x1))
        # Antes de tudo o que mede caractere: a tarja preta é um box só, e os
        # caracteres de dentro dela ainda não existem (F10). O `th` volta com
        # as tarjas invertidas, para o separador de colados ver o perfil de
        # tinta do texto e não o do fundo.
        boxes, th, _faixas = negativo.aplicar(img_cv, th, boxes)
        # E antes de o descarte jogar fora o bloco grande: dentro dele pode
        # haver uma linha de texto que a trama soldou ao fundo (F11).
        boxes, _blocos = trama.aplicar(img_cv, boxes, escala)
        # Antes do merge, e não depois: o merge vertical cola exatamente o que
        # numa pilha girada são letras vizinhas — medido, uma linha real de 17
        # caracteres saía como 7 caixas (F8.1). Quem sai daqui marcado fica
        # fora dele.
        boxes, _pilhas = vertical.aplicar(img_cv, boxes, arbitro)
        boxes = BoxService.merge_vertical_boxes(boxes)
        # Depois do merge, não antes: medido, o box do diagrama absorve os
        # respingos em volta dele (borda serrilhada, legenda encostada), e
        # descartá-lo depois leva esse lixo junto. Descartando antes, os
        # respingos sobram soltos — na página 0108, 11 boxes espúrios viram 29.
        if descartar_nao_texto:
            boxes = BoxService.descartar_blocos_nao_texto(boxes, escala=escala)
        # Antes do corte de glifo colado, e não depois: partir a linha primeiro
        # deixa cada metade com a largura certa para o separador da F1.5b medir.
        boxes = BoxService.dividir_linhas_coladas(boxes, th, escala)
        if separar_colados is True or (separar_colados == "auto"
                                       and arbitro is not None):
            # Depois do merge vertical: fundir o pingo do 'i' primeiro evita
            # que ele seja tratado como peça solta na hora de cortar.
            boxes = BoxService.dividir_glifos_colados(
                boxes, th, arbitro=arbitro, imagem_cinza=img_cv)
        boxes = BoxService.sort_boxes_reading_order(boxes)
        return boxes

    # Abaixo disto a linha tem amostra pequena demais para uma mediana confiável
    # (número de página, cabeçalho de uma palavra) e volta a usar a da página.
    MIN_BOXES_PARA_MEDIANA_LOCAL = 5

    # Múltiplo da altura mediana de caractere acima do qual um contorno deixa de
    # ser texto. Precisa valer nos DOIS eixos: um travessão é largo e legítimo.
    FATOR_NAO_TEXTO = 4.0
    # Com poucos boxes a mediana não é confiável (uma página que é só diagrama
    # teria "altura mediana de caractere" do tamanho do diagrama).
    MIN_BOXES_PARA_DESCARTE = 20

    @staticmethod
    def descartar_blocos_nao_texto(boxes: List[BoxEntry],
                                   fator: float = None,
                                   escala: int = None) -> List[BoxEntry]:
        """
        Remove contornos grandes demais para serem caractere — o diagrama.

        **`escala` é a altura de caractere da página, e omiti-la é perigoso numa
        página com trama.** Sem ela, a referência é a mediana das alturas dos
        próprios boxes; no painel de meio-tom da página 18 do Yusupov essa
        mediana é **2 px**, o limite vira 8, e o que esta função descarta deixa
        de ser o diagrama e passa a ser *o texto* — medido, o painel inteiro
        saiu sem um box. Quem tem a imagem passa `preprocess.escala_de_texto`,
        que pesa por tinta e não desaba (31–43 px nas mesmas páginas).

        **O problema aqui é menor do que o roadmap supunha, e isso foi medido.**
        A F1.8 previa que "em página escaneada o tabuleiro vira milhares de boxes
        de lixo". Não vira: `findContours` roda com `RETR_EXTERNAL` e o tabuleiro
        destes livros tem moldura fechada, então as 64 casas e as peças são
        contornos *filhos* e não são devolvidos. O tabuleiro inteiro sai como
        **um** box de 479x478. Medido em 8 páginas com diagrama: 1 box por
        tabuleiro, e a detecção de colunas da F1.6 não muda com ele nem sem ele.

        Por isso não há detecção de grade nem transformada de Hough aqui — seria
        maquinário para um problema que não existe neste formato. Um limiar de
        tamanho relativo resolve o que sobra, sem risco: medido nas 9 páginas
        rotuladas, 19 boxes caem e **nenhum** deles casava com caractere
        rotulado.

        O limiar é relativo à altura mediana de caractere, não absoluto. O
        pipeline de lote usava `w > 150 or h > 150`, que depende do DPI da
        digitalização: a 600 dpi corta letra legítima, a 150 dpi deixa o
        tabuleiro passar.
        """
        fator = BoxService.FATOR_NAO_TEXTO if fator is None else fator
        if len(boxes) < BoxService.MIN_BOXES_PARA_DESCARTE:
            return boxes

        if not escala:
            alturas = sorted(b.y2 - b.y1 for b in boxes)
            escala = alturas[len(alturas) // 2]
        limite = (escala or 1) * fator

        return [b for b in boxes
                if (b.y2 - b.y1) <= limite or (b.x2 - b.x1) <= limite]

    @staticmethod
    def _largura_de_referencia(boxes: List[BoxEntry]) -> dict:
        """
        Largura mediana de caractere **local a cada box**, indexada por `id`.

        A mediana da página inteira só serve quando a página tem um tamanho de
        fonte só. Nestes livros a linha principal da partida é maior que o texto
        de variantes: medido na página 0108, mediana de 21 px na linha principal
        contra 17 px nas variantes, com a mediana da página em 17. Com o limiar
        preso à mediana global, glifos grandes e legítimos passavam de
        `mediana * fator_largo` e viravam candidatos a corte — 147 dos 1.404
        caracteres rotulados, quase todos figurina (R, N, Q, B).

        **A referência local nunca fica abaixo da global**, e isso foi medido, não
        suposto. A mediana de uma linha não mede só o tamanho da fonte: mede
        também quais caracteres calharam de cair nela. Uma linha carregada de
        'i', 'l', '1' e pontuação tem mediana pequena sem ser fonte pequena, e
        baixar o limiar ali só fabrica candidato a corte. Medido nas 8 páginas
        rotuladas, a mediana da linha pura leva os cortes falsos de 221 para 182,
        mas *piora* a página 0020 (2 -> 9); tomando o máximo com a global, caem
        para 162 e a 0020 melhora (2 -> 1). O máximo também deixa a mudança
        segura por construção: o limiar só sobe, então nenhum corte que hoje não
        acontece passa a acontecer.

        Linha curta demais não tem mediana confiável e volta para a global.
        """
        larguras = sorted(b.x2 - b.x1 for b in boxes)
        global_ = larguras[len(larguras) // 2] or 1

        referencia = {}
        for linha in BoxService._linhas(boxes):
            local = global_
            if len(linha) >= BoxService.MIN_BOXES_PARA_MEDIANA_LOCAL:
                ls = sorted(b.x2 - b.x1 for b in linha)
                local = max(ls[len(ls) // 2], global_)
            for b in linha:
                referencia[id(b)] = local
        return referencia

    #: Quanto as partes precisam superar o inteiro para o corte valer (F1.5b).
    #: Ver `dividir_glifos_colados` para as tabelas que fixaram o valor.
    MARGEM_ARBITRO = 0.30

    @staticmethod
    def _cortes_endossados(imagem_cinza, box, cortes, arbitro, margem):
        """
        O classificador confirma o corte? Devolve os cortes, ou lista vazia.

        Compara a pontuação do box inteiro com a **menor** pontuação entre as
        partes. A menor, e não a média: basta um pedaço sem sentido para o
        corte ter sido estrago, e a média deixaria um pedaço bom encobrir o
        outro.

        Box em negativo é positivado antes de chegar ao árbitro (F10): aqui o
        recorte sai da página em tom de cinza, e branco sobre preto é o que o
        modelo lê pior — o árbitro recusaria todo corte de tarja pelo motivo
        errado.
        """
        def recorte_de(ini, fim):
            pedaco = imagem_cinza[box.y1:box.y2, box.x1 + ini:box.x1 + fim]
            if pedaco.size and getattr(box, "negativo", False):
                return negativo.positivar(pedaco)
            return pedaco

        largura = box.x2 - box.x1
        recorte = recorte_de(0, largura)
        if recorte.size == 0:
            return []
        _, p_inteiro = arbitro(recorte)

        limites = [0] + list(cortes) + [largura]
        menor = 1.0
        for ini, fim in zip(limites, limites[1:]):
            pedaco = recorte_de(ini, fim)
            if pedaco.size == 0:
                return []
            menor = min(menor, float(arbitro(pedaco)[1]))

        return list(cortes) if menor > float(p_inteiro) + margem else []

    @staticmethod
    def dividir_glifos_colados(boxes: List[BoxEntry], imagem_bin: np.ndarray,
                               fator_largo: float = 1.6,
                               razao_vale: float = 0.30,
                               arbitro=None, imagem_cinza: np.ndarray = None,
                               margem: float = None) -> List[BoxEntry]:
        """
        Separa boxes que contêm mais de um glifo encostado.

        Em notação figurina o espaçamento é apertado e os contornos se tocam:
        `findContours` com RETR_EXTERNAL devolve "♞e5" como um box só, que o
        classificador então lê como um caractere errado. Era a origem de todos
        os erros de figurina observados na página real.

        **O critério é a largura do vale, não a profundidade.** Medido (largura
        mediana de caractere = 19 px), contando colunas cuja tinta fica abaixo
        de 30% do pico:

            ♞e5  (3 glifos)  vale de 10 colunas, fundo a  8% do pico
            ♞a6  (3 glifos)  vale de 10 colunas, fundo a 10% do pico
            W    (1 glifo)   vale de  2 colunas, fundo a 25% do pico
            ♛    (1 glifo)   vale de  0 colunas, fundo a 41% do pico

        Cortar por profundidade partiria a coroa da dama, que tem vales
        internos fundos entre as pontas.

        **A escala é local à linha** (ver `_largura_de_referencia`). Com a
        mediana da página, uma página que mistura tamanhos de fonte transforma
        os glifos da linha maior em candidatos a corte.

        **Sozinho, o perfil de tinta não separa as duas populações, e isso está
        medido.** Nas páginas de notação *figurina* ele paga: as figurinas
        coladas têm vale largo e os vizinhos não. Onde a figurina aparece
        isolada entre texto normal, largura e profundidade do vale ficam
        indistinguíveis — na página 0108, vale de colagem com largura mediana de
        7 colunas e fundo a 13% do pico, contra 7 colunas e 10% para vales
        *internos* de glifo inteiro. Nas 9 páginas rotuladas o perfil propõe 73
        cortes bons contra 182 falsos: **precisão de 28,6%**.

        **`arbitro` é o que inverte esse sinal (F1.5b).** É o classificador,
        `(recorte_cinza) -> (char, confiança)`. A ideia: um `N` em negrito
        partido ao meio vira dois fragmentos sem sentido e o modelo os pontua
        baixo; um `♞e5` inteiro não é caractere nenhum, e as partes pontuam mais
        que o todo. Medido nos mesmos 255 candidatos:

            grupo (pelo rótulo)   inteiro   menor parte   partes > inteiro
            colagem   (n=73)       0,604       0,857           57,5%
            glifo inteiro (n=182)  1,000       0,481            6,6%

        E, variando a margem exigida:

            margem   colagens cortadas   glifos partidos   precisão do corte
            (sem árbitro)   73/73            182/182          28,6%
             0,00           42/73             12/182          77,8%
             0,10           33/73              6/182          84,6%
             0,30           23/73              2/182          92,0%

        **A margem é 0,30, e quem decidiu foi o F1 da página, não a precisão do
        corte.** As duas medidas discordariam: mais cortes bons (margem 0,0)
        parecia melhor pela contagem, mas o que chega ao texto diz outra coisa.
        Nas 9 páginas rotuladas, com o classificador lendo o resultado:

            modo         recall   precisão    F1
            desligado    94,1%     93,0%    93,5
            sem árbitro  94,0%     88,5%    91,2
            margem 0,00  94,7%     92,7%    93,7
            margem 0,30  94,5%     93,0%   *93,8*
            margem 0,50  94,3%     93,0%    93,6
            margem 1,00  94,1%     93,0%    93,5

        **O pico no meio é o que prova que o árbitro faz algo.** Se ele fosse
        só uma maneira lenta de cortar menos, o F1 subiria monotonicamente até
        o valor de "desligado" — e com margem 1,00 ele de fato converge para
        93,5, que é o desligado. O máximo em 0,30 é ganho de verdade.

        **O tamanho do ganho, dito sem enfeite: +0,3 de F1 sobre não separar.**
        O que mudou de fato foi o sinal — antes, manter o separador ligado
        custava 2,3 pontos. Continua sendo o caso que a segmentação por
        projeção é fraca para este material; o árbitro a torna inofensiva e
        levemente positiva, não a conserta.

        **Sem `arbitro` o comportamento é o antigo**, cortes falsos e tudo. O
        parâmetro é opcional porque `BoxService` não conhece o modelo, e quem
        chama é que sabe se há um carregado — mas por isso mesmo o padrão de
        `generate_boxes_opencv` é `separar_colados="auto"`, que não separa sem
        árbitro. A configuração reprovada não fica armada por omissão.
        """
        if not boxes or imagem_bin is None:
            return boxes
        if arbitro is not None and imagem_cinza is None:
            raise ValueError("o árbitro precisa da imagem em tom de cinza: "
                             "o modelo foi treinado nela, não no binarizado")
        margem = BoxService.MARGEM_ARBITRO if margem is None else margem

        referencia = BoxService._largura_de_referencia(boxes)

        saida = []
        for b in boxes:
            # Box girado não se corta aqui: o corte é por coluna de tinta, e
            # num glifo deitado a coluna atravessa o caractere no eixo errado
            # — cortaria um 'M' girado ao meio por parecer largo demais (F8.1).
            if getattr(b, "angulo", 0):
                saida.append(b)
                continue

            mediana = referencia[id(b)]
            if (b.x2 - b.x1) <= mediana * fator_largo:
                saida.append(b)
                continue

            cortes = BoxService._cortes_do_perfil(
                imagem_bin[b.y1:b.y2, b.x1:b.x2], razao_vale,
                max(3, int(mediana * 0.25)), max(3, int(mediana * 0.40)))

            if cortes and arbitro is not None:
                cortes = BoxService._cortes_endossados(
                    imagem_cinza, b, cortes, arbitro, margem)

            if not cortes:
                saida.append(b)
                continue

            limites = [0] + cortes + [b.x2 - b.x1]
            for ini, fim in zip(limites, limites[1:]):
                saida.append(BoxEntry(b.char, b.x1 + ini, b.y1, b.x1 + fim,
                                      b.y2, negativo=b.negativo))

        return saida

    #: Altura, em escalas de texto, acima da qual um box não é um caractere e
    #: sim duas linhas grudadas. Medido nas 10 páginas rotuladas: 109 boxes
    #: passam de 1,6 escalas, e o corte por vale de linha acha **todos** os 71
    #: que cobrem rótulos de duas linhas — nenhum escapa.
    ALTURA_DUAS_LINHAS = 1.6

    #: Teto: acima disto é bloco (diagrama, painel, moldura) e não é assunto
    #: deste corte. `descartar_blocos_nao_texto` usa 4,0 para o mesmo fim.
    ALTURA_MAXIMA_DE_CORTE = 6.0

    #: Pedaço menor que isto, em escalas, não vira box: é a **lasca** que sobra
    #: da linha vizinha, e é ela que decide se a fase paga. Medido nas 10
    #: páginas rotuladas, com o resto do pipeline igual:
    #:
    #:     lasca vira box       recall 94,96  precisão 92,96   F1 93,95   (pior)
    #:     descarta abaixo 0,8  recall 94,84  precisão 93,93   F1 94,38
    #:     descarta abaixo 0,9  recall 94,81  precisão 94,13   F1 94,47
    #:     descarta abaixo 1,0  recall 94,80  precisão 94,17   F1 94,48
    #:     descarta abaixo 1,2  recall 94,74  precisão 94,24   F1 94,49
    #:     sem cortar (antes)   recall 94,50  precisão 93,66   F1 94,08
    #:
    #: Emitir a lasca **piora** o F1: cada caractere recuperado custa 2,2 boxes
    #: espúrios. O valor é 1,0 por ficar no meio do platô 0,9–1,2 e por ser o que
    #: dá para dizer em voz alta: pedaço mais curto que um caractere não é
    #: caractere.
    PECA_MINIMA_DE_LINHA = 1.0

    @staticmethod
    def dividir_linhas_coladas(boxes: List[BoxEntry], imagem_bin: np.ndarray,
                               escala: int,
                               razao_vale: float = 0.30) -> List[BoxEntry]:
        """
        Parte o box que engoliu duas linhas de texto.

        **É o corte da F1.5b transposto**, e o defeito que ele ataca é o
        simétrico daquele: lá dois glifos vizinhos se tocam na horizontal e o
        contorno sai largo; aqui o descendente de uma linha ('y', 'g', 'p')
        encosta na linha de baixo e o contorno sai **alto**. Medido nas 10
        páginas rotuladas, 231 caracteres ficam sem box por estarem colados a um
        vizinho, e 71 boxes cobrem rótulos de duas linhas ao mesmo tempo.

        **Nem todos nascem no merge, e isso mudou o desenho.** Dos 131 boxes
        altos das páginas rotuladas, só 29 são criados por
        `merge_vertical_boxes`; os outros 102 já vêm assim do `findContours`,
        porque os glifos se tocam de verdade no papel. Proibir o merge não
        resolveria — é preciso cortar.

        O critério é o vale do perfil de tinta **por linha**, e a transposição
        é literal: `_cortes_do_perfil` já sabe achar vale numa direção, e
        passar o recorte transposto o faz olhar na outra. É a manobra de
        `vertical.fundir_pingos`.

        **Sem árbitro, ao contrário da F1.5b, e isso foi medido nas duas
        posições.** Lá o classificador é o que salva o corte, porque box largo é
        comum e o perfil sozinho acerta 28,6%. Aqui a geometria já é decisiva —
        um box 1,6 vez mais alto que um caractere é anômalo por construção, e
        são 109 em 10 páginas —, e submeter o corte ao árbitro **derruba** o
        ganho: F1 94,06 com ele contra 94,48 sem. O que ele recusa é justamente
        o corte certo, porque a lasca da linha vizinha pontua baixo.
        """
        if not boxes or imagem_bin is None or escala <= 0:
            return boxes

        piso = escala * BoxService.ALTURA_DUAS_LINHAS
        teto = escala * BoxService.ALTURA_MAXIMA_DE_CORTE
        vale_minimo = max(3, int(escala * 0.4))
        peca_minima = escala * BoxService.PECA_MINIMA_DE_LINHA

        saida = []
        for b in boxes:
            # Box girado fica de fora pelo mesmo motivo da F8.1: numa pilha
            # vertical as linhas correm no outro eixo.
            if getattr(b, "angulo", 0) or not (piso < b.height <= teto):
                saida.append(b)
                continue

            recorte = imagem_bin[b.y1:b.y2, b.x1:b.x2]
            cortes = BoxService._cortes_do_perfil(
                np.ascontiguousarray(recorte.T), razao_vale, 2, vale_minimo)
            if not cortes:
                saida.append(b)
                continue

            limites = [0] + list(cortes) + [b.height]
            pedacos = [(ini, fim) for ini, fim in zip(limites, limites[1:])
                       if fim - ini >= peca_minima]
            if not pedacos:
                # Nenhum pedaço tem tamanho de caractere: o box não era duas
                # linhas, era outra coisa alta. Fica como estava.
                saida.append(b)
                continue

            for ini, fim in pedacos:
                saida.append(BoxEntry(b.char, b.x1, b.y1 + ini, b.x2, b.y1 + fim,
                                      negativo=b.negativo))

        return saida

    @staticmethod
    def _cortes_do_perfil(recorte_bin: np.ndarray, razao_vale: float,
                          largura_min_vale: int, largura_min_peca: int) -> List[int]:
        """Posições de corte dentro de um box, a partir do perfil de tinta."""
        if recorte_bin.size == 0:
            return []

        perfil = (recorte_bin > 0).sum(axis=0)
        pico = int(perfil.max())
        if pico <= 0:
            return []

        limiar = max(1.0, pico * razao_vale)
        baixo = perfil <= limiar

        cortes = []
        inicio = None
        for i, e_baixo in enumerate(list(baixo) + [False]):
            if e_baixo:
                if inicio is None:
                    inicio = i
                continue
            if inicio is None:
                continue

            largura = i - inicio
            centro = (inicio + i) // 2
            # o vale precisa ser largo, interno, e deixar pedaços utilizáveis
            if (largura >= largura_min_vale
                    and centro - (cortes[-1] if cortes else 0) >= largura_min_peca
                    and len(perfil) - centro >= largura_min_peca):
                cortes.append(centro)
            inicio = None

        return cortes

    @staticmethod
    def detectar_colunas(boxes: List[BoxEntry],
                         calha_minima: int = None) -> List[Tuple[int, int]]:
        """
        Faixas horizontais de coluna, em ordem de leitura.

        Projeta a ocupação dos boxes no eixo X e procura vãos verticais sem
        conteúdo nenhum. Usa os boxes, não os pixels: o vão que interessa é
        onde não há *caractere*, e assim funciona igual para página escaneada
        e para imagem já limpa.

        O limiar é relativo à largura mediana de caractere — uma calha de
        verdade é muito mais larga que o espaço entre palavras. Fixar a busca
        numa faixa central (como faz o DocuVision, 42%–58% da largura) só acha
        duas colunas simétricas; aqui a calha pode estar em qualquer posição, e
        podem ser mais de duas.
        """
        if not boxes:
            return []

        x_min = min(b.x1 for b in boxes)
        x_max = max(b.x2 for b in boxes)
        largura = x_max - x_min
        if largura <= 1:
            return [(x_min, x_max)]

        ocupado = np.zeros(largura + 2, dtype=bool)
        for b in boxes:
            ocupado[max(0, b.x1 - x_min):max(0, b.x2 - x_min) + 1] = True

        if calha_minima is None:
            larguras = sorted(b.x2 - b.x1 for b in boxes)
            mediana = larguras[len(larguras) // 2] or 1
            calha_minima = max(int(mediana * 3), int(largura * 0.02), 4)

        cortes = []
        inicio = None
        for i, cheio in enumerate(ocupado):
            if not cheio:
                if inicio is None:
                    inicio = i
            else:
                if inicio is not None and i - inicio >= calha_minima:
                    cortes.append((inicio, i))
                inicio = None

        if not cortes:
            return [(x_min, x_max)]

        faixas = []
        anterior = 0
        for ini, fim in cortes:
            if ini > anterior:
                faixas.append((x_min + anterior, x_min + ini - 1))
            anterior = fim
        if anterior <= largura:
            faixas.append((x_min + anterior, x_max))

        return [f for f in faixas if f[1] > f[0]] or [(x_min, x_max)]

    @staticmethod
    def _linhas(boxes: List[BoxEntry]) -> List[List[BoxEntry]]:
        """
        Agrupa em linhas de texto por sobreposição vertical, de cima para baixo.

        Um box entra na linha corrente se o seu centro vertical não passa do
        fundo médio da linha (com folga de 20% da própria altura); senão abre
        uma linha nova. Dentro da linha a ordem é a de entrada — quem precisa
        delas ordenadas usa `_agrupar_em_linhas`.
        """
        if not boxes:
            return []

        grupos: List[List[BoxEntry]] = []
        atual: List[BoxEntry] = []

        for b in sorted(boxes, key=lambda b: b.y1):
            if not atual:
                atual = [b]
                continue

            fundo = sum(i.y2 for i in atual) / len(atual)
            if (b.y1 + b.y2) / 2 <= fundo + (b.y2 - b.y1) * 0.2:
                atual.append(b)
            else:
                grupos.append(atual)
                atual = [b]

        if atual:
            grupos.append(atual)

        return grupos

    @staticmethod
    def _agrupar_em_linhas(boxes: List[BoxEntry]) -> List[BoxEntry]:
        """
        Ordena por linha de texto: agrupa por sobreposição vertical, linhas de
        cima para baixo, itens da esquerda para a direita dentro da linha.
        """
        final_boxes = []
        for linha in BoxService._linhas(boxes):
            final_boxes.extend(sorted(linha, key=lambda b: b.x1))
        return final_boxes

    @staticmethod
    def _por_colunas(boxes: List[BoxEntry],
                     colunas: List[Tuple[int, int]]) -> List[BoxEntry]:
        """Coluna a coluna; dentro de cada uma, linha a linha."""
        saida = []
        restantes = list(boxes)
        for x1, x2 in colunas:
            desta = [b for b in restantes if x1 <= (b.x1 + b.x2) / 2 <= x2]
            if desta:
                pegos = set(id(b) for b in desta)
                restantes = [b for b in restantes if id(b) not in pegos]
                saida.extend(BoxService._agrupar_em_linhas(desta))
        # o que não caiu em coluna nenhuma vai no fim, em ordem de linha
        saida.extend(BoxService._agrupar_em_linhas(restantes))
        return saida

    @staticmethod
    def sort_boxes_reading_order(boxes: List[BoxEntry]) -> List[BoxEntry]:
        """
        Ordena boxes como um humano leria.

        Antes, agrupava tudo por linha ignorando colunas: numa página de duas
        colunas o resultado intercalava as duas (linha 1 da esquerda, linha 1
        da direita, linha 2 da esquerda...), embaralhando o texto. Medido numa
        página real do Kasparov: 9 saltos entre colunas onde o correto é 1.

        Elementos que atravessam a calha — título, diagrama largo — não podem
        ser jogados numa coluna. Servem de separador horizontal: o que está
        acima deles é lido coluna a coluna, depois vem o elemento, depois o que
        está abaixo.

        **Uma pilha de texto girado é um elemento só** (F8.1). Cada letra dela
        cai numa linha de texto diferente, e sem isto o rótulo ao lado do
        diagrama entra letra a letra no meio de seis linhas do parágrafo
        vizinho — foi o que a medição mostrou. A pilha entra na ordem pelo
        lugar da sua caixa, e por dentro segue o sentido do ângulo.
        """
        if not boxes:
            return []

        pilhas = vertical.runs(boxes)
        if pilhas:
            return BoxService._ordenar_com_pilhas(boxes, pilhas)

        colunas = BoxService.detectar_colunas(boxes)
        if len(colunas) <= 1:
            return BoxService._agrupar_em_linhas(boxes)

        def bandas_cobertas(b):
            return sum(1 for x1, x2 in colunas if b.x1 <= x2 and b.x2 >= x1)

        transversais = sorted((b for b in boxes if bandas_cobertas(b) > 1),
                              key=lambda b: b.y1)
        ids_transversais = set(id(b) for b in transversais)
        restantes = [b for b in boxes if id(b) not in ids_transversais]

        if not transversais:
            return BoxService._por_colunas(restantes, colunas)

        saida = []
        for t in transversais:
            acima = [b for b in restantes if b.y2 <= t.y1]
            if acima:
                ids = set(id(b) for b in acima)
                restantes = [b for b in restantes if id(b) not in ids]
                saida.extend(BoxService._por_colunas(acima, colunas))
            saida.append(t)

        saida.extend(BoxService._por_colunas(restantes, colunas))
        return saida

    @staticmethod
    def _ordenar_com_pilhas(boxes: List[BoxEntry],
                            pilhas: List[List[BoxEntry]]) -> List[BoxEntry]:
        """
        Ordena a página com cada pilha girada valendo por um elemento só.

        Troca a pilha por uma caixa que a representa, ordena a página com o
        algoritmo de sempre e depois desfaz a troca. Assim a pilha entra na
        ordem pelo lugar que ocupa na página — inclusive como elemento
        transversal, se ela cruzar a calha entre colunas — sem que a ordem
        precise saber que ela existe.
        """
        substitutos = {}
        restantes = list(boxes)
        for pilha in pilhas:
            ids = set(id(b) for b in pilha)
            restantes = [b for b in restantes if id(b) not in ids]
            marca = BoxEntry("", min(b.x1 for b in pilha),
                             min(b.y1 for b in pilha),
                             max(b.x2 for b in pilha),
                             max(b.y2 for b in pilha))
            substitutos[id(marca)] = pilha
            restantes.append(marca)

        saida = []
        for b in BoxService.sort_boxes_reading_order(restantes):
            saida.extend(substitutos.get(id(b), [b]))
        return saida

    @staticmethod
    def merge_vertical_boxes(boxes: List[BoxEntry]) -> List[BoxEntry]:
        """
        Mescla boxes verticalmente alinhados e próximos (ex: pingo do 'i', ':', ';').

        **Box de texto girado não entra** (F8.1). Numa pilha vertical as letras
        vizinhas são exatamente o que esta regra procura — alinhadas em x e
        encostadas em y —, e o merge as fundiria numa caixa só: medido, uma
        linha real de 17 caracteres colada girada saía como 7 boxes. O
        diacrítico de um glifo girado fica ao lado, não em cima, e quem o funde
        é `vertical.fundir_pingos`, no eixo certo.
        """
        if not boxes:
            return []

        girados = [b for b in boxes if getattr(b, "angulo", 0)]
        if girados:
            de_pe = [b for b in boxes if not getattr(b, "angulo", 0)]
            return BoxService.merge_vertical_boxes(de_pe) + girados

        heights = [b.y2 - b.y1 for b in boxes]
        if not heights:
            return boxes

        median_h = sorted(heights)[len(heights) // 2]
        if median_h < 10:
            median_h = 10

        SHORT_THRESH = median_h * 0.6
        DEFAULT_MAX_VERT = max(10, min(30, median_h * 0.8))
        MIN_HORIZ_OVERLAP_RATIO = 0.3

        merged_boxes = []
        used_indices = set()

        for i in range(len(boxes)):
            if i in used_indices:
                continue

            b1 = boxes[i]
            current_merged = BoxEntry(
                b1.char, b1.x1, b1.y1, b1.x2, b1.y2,
                negativo=getattr(b1, "negativo", False)
            )
            used_indices.add(i)

            merged_something = True
            while merged_something:
                merged_something = False

                for j in range(i + 1, len(boxes)):
                    if j in used_indices:
                        continue

                    b2 = boxes[j]
                    dist_vert = b2.y1 - current_merged.y2

                    h1 = current_merged.y2 - current_merged.y1
                    h2 = b2.y2 - b2.y1

                    is_tall_1 = h1 > SHORT_THRESH
                    is_tall_2 = h2 > SHORT_THRESH

                    if is_tall_1 and is_tall_2:
                        max_vert_dist = 2
                    else:
                        max_vert_dist = DEFAULT_MAX_VERT

                    if dist_vert > max_vert_dist:
                        continue

                    ox1 = max(current_merged.x1, b2.x1)
                    ox2 = min(current_merged.x2, b2.x2)
                    overlap = max(0, ox2 - ox1)

                    width1 = current_merged.x2 - current_merged.x1
                    width2 = b2.x2 - b2.x1
                    min_width = min(width1, width2)

                    if min_width <= 0:
                        continue

                    if (overlap / min_width) > MIN_HORIZ_OVERLAP_RATIO:
                        new_x1 = min(current_merged.x1, b2.x1)
                        new_y1 = min(current_merged.y1, b2.y1)
                        new_x2 = max(current_merged.x2, b2.x2)
                        new_y2 = max(current_merged.y2, b2.y2)

                        current_merged.x1 = new_x1
                        current_merged.y1 = new_y1
                        current_merged.x2 = new_x2
                        current_merged.y2 = new_y2

                        used_indices.add(j)
                        merged_something = True
                        break

            merged_boxes.append(current_merged)

        return merged_boxes

    @staticmethod
    def split_box(box: BoxEntry) -> List[BoxEntry]:
        """
        Divide um box ao meio. Se for mais largo que alto, divide em X.
        Caso contrário, divide em Y. Retorna 2 boxes com char vazio.

        As metades herdam o ângulo (F8.1) e a polaridade (F10): quem parte um
        box de rótulo vertical — ou de tarja preta — em dois quer dois pedaços
        do mesmo rótulo, não dois boxes normais.
        """
        x1, y1, x2, y2 = box.x1, box.y1, box.x2, box.y2
        angulo = getattr(box, "angulo", 0)
        neg = getattr(box, "negativo", False)

        if (x2 - x1) > (y2 - y1):
            mx = (x1 + x2) // 2
            return [
                BoxEntry("", x1, y1, mx, y2, angulo=angulo, negativo=neg),
                BoxEntry("", mx, y1, x2, y2, angulo=angulo, negativo=neg),
            ]
        else:
            my = (y1 + y2) // 2
            return [
                BoxEntry("", x1, y1, x2, my, angulo=angulo, negativo=neg),
                BoxEntry("", x1, my, x2, y2, angulo=angulo, negativo=neg),
            ]

    @staticmethod
    def clamp_box(box: BoxEntry, max_w: int, max_h: int) -> BoxEntry:
        """Garante que as coordenadas do box fiquem dentro dos limites da imagem."""
        return BoxEntry(
            char=box.char,
            x1=max(0, box.x1),
            y1=max(0, box.y1),
            x2=min(max_w, box.x2),
            y2=min(max_h, box.y2),
            confidence=box.confidence,
            source=box.source,
            angulo=getattr(box, "angulo", 0),
            negativo=getattr(box, "negativo", False),
        )
