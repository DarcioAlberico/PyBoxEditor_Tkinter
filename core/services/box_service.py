import itertools

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
        boxes, th, escala, img_cv = BoxService.boxes_antes_do_descarte(
            image, threshold=threshold, method=method, arbitro=arbitro)
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

    #: Acima disto a página não é de texto, e não vale medi-la.
    #:
    #: **O custo é do `merge_vertical_boxes`.** Medido nas páginas do Yusupov a
    #: 300 dpi: a 11, de texto, dá 2.131 contornos e o merge leva 0,4 s; a 8,
    #: que é quase toda imagem, dá **78.558** e o mesmo merge levava **160 s** —
    #: 37× mais contorno, 400× mais tempo. O limiar fica uma ordem de grandeza
    #: acima da página de texto mais carregada.
    #:
    #: **A premissa da primeira linha é falsa, e a F96 tem o contraexemplo.** A
    #: página 96 do mesmo livro dá **85.903** contornos e é uma página de texto
    #: comum: duas colunas de prosa, um diagrama e um painel de sumário. Quem
    #: produz os contornos é a trama do painel, não a ausência de texto. Ou
    #: seja, quem passa este teto perde a página inteira — o texto e o diagrama
    #: junto —, e é por isso que ele continua sendo `None` por omissão.
    #:
    #: O índice espacial da F96 tirou 4× do merge e **não** resolve isto: a
    #: página 96 saiu de 250,81 s para 62,77 s, que ainda não é tempo de tela.
    #: Quem responde nela em 0,76 s, e achando o diagrama, é
    #: `core.deteccao_de_tabuleiro` — ver o que a F96 deixou em aberto.
    MAX_CONTORNOS_DE_TEXTO = 20000

    @staticmethod
    def boxes_antes_do_descarte(image: Image.Image, threshold: int = 180,
                                method: str = "auto", arbitro=None,
                                max_contornos: Optional[int] = None
                                ) -> Tuple[List[BoxEntry], np.ndarray, int, np.ndarray]:
        """
        As caixas no estágio anterior ao descarte da F1.8, com `th`, escala e a
        imagem em cinza. É o estágio que o `diagrama.localizar` espera.

        **Existe porque não havia como pedir esse estágio.** O `localizar`
        procura o contorno grande e quase quadrado do tabuleiro, e o descarte é
        justamente quem o joga fora — então quem quer achar diagrama precisa
        das caixas de antes. As duas saídas que havia para isso não servem:

        - `generate_boxes_opencv(descartar_nao_texto=False)` **não para aqui**:
          segue para `dividir_linhas_coladas`, que passa a medir perfil de
          tinta dentro dos blocos grandes que o descarte teria tirado. Medido
          na página 8 do Yusupov, **158 segundos** contra 1,4 do caminho
          normal. É o que a leitura de diagramas da UI faz hoje
          (`main_window.py`), e é o mesmo custo.
        - refazer as etapas por fora, como um chamador tentou, dá 6 tabuleiros
          onde há 2 assim que uma delas falta — e o texto da página some junto
          com os retângulos falsos.

        Devolver `th` e `escala` junto não é conveniência: são o mesmo `th`
        **depois** da inversão das tarjas (F10) e a mesma escala que o resto do
        pipeline usa, e recalculá-los por fora daria outros valores.

        `max_contornos` devolve a lista **vazia** quando a página tem contorno
        demais para ser texto — ver `MAX_CONTORNOS_DE_TEXTO`. Não é limite de
        segurança inventado: é o que separa uma página de livro de uma página
        que é uma fotografia, e sem ele a segunda custa três minutos para
        devolver lixo. O padrão é `None`, sem limite, para não mudar o que os
        chamadores de hoje recebem.
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

        if max_contornos is not None and len(boxes) > max_contornos:
            return [], th, escala, img_cv

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
        return BoxService.merge_vertical_boxes(boxes), th, escala, img_cv

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
    #:
    #: **Era 0,30, decidido pelo F1 da página; é 0,00 desde a F33, decidido pelo
    #: que sobra errado no texto final.** A F30 mediu que o F1 é plano de 0,05 a
    #: 0,30 e não decide mais nada; a F31 e a F32 trocaram a moeda para "erro que
    #: atravessa a fila de revisão e o léxico". Contra a de produção, em 10
    #: páginas e 10.613 caracteres rotulados:
    #:
    #:     margem  saldo do texto  saldo invisível  ganha em  cortes falsos
    #:     0,00           +47            +4          7 de 10        16
    #:     0,05           +33            +7          6 de 10        11
    #:     0,10           +22            +6          6 de 10         8
    #:     0,15           +14            +6          5 de 10         5
    #:     0,30             0             0             —            2
    #:
    #: "Saldo do texto" é caractere rotulado que passou a sair certo menos o que
    #: deixou de sair. "Saldo invisível" soma os dois lados **sem sobrepô-los** —
    #: somar as duas colunas de erro invisível foi o defeito da F31, porque os
    #: pedaços de um corte falso que não casam com rótulo *são* boxes espúrios.
    #:
    #: O 0,00 ganha em toda coluna e **não perde em página nenhuma** (a única
    #: regressão de caractere em 10 páginas está numa que ganha 4).
    #:
    #: **O risco que este número carrega, e que a medida não cobre:** ele sobe os
    #: cortes falsos de 2 para 16, e 7 dos 16 saem de **uma** digitalização ruim.
    #: Fora destas dez páginas, um livro pior escaneado paga mais caro — e cada
    #: corte falso custa ~0,8 erro que ninguém vê (F31). Se aparecer livro assim,
    #: é aqui que se mexe, e `medir_corte_falso.py` é quem diz quanto.
    MARGEM_ARBITRO = 0.00

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

    #: Quanto a prova visual desloca o corte para cada lado da repartição igual,
    #: em frações da largura de uma letra, e de quanto em quanto.
    #:
    #: **A repartição igual sozinha erraria por construção**: as letras que
    #: colam não têm a mesma largura — `y`+`n`, `w`+`n`, `v`+`i` —, e cortar no
    #: meio parte a maior. Um vale do perfil resolveria, mas de cada quatro
    #: colagens uma não tem vale nenhum (F66): em negrito e itálico os traços se
    #: soldam, e é justamente onde a prova precisa falar.
    #:
    #: Varrer ±40% de uma letra em passos de 20% custa 5 posições por junta e
    #: cobre de `il` a `wn` sem depender do perfil.
    DESLOCAMENTO_DE_PROVA = 0.4
    PASSO_DE_PROVA = 0.2

    @staticmethod
    def provar_letras(imagem_cinza: np.ndarray, box: BoxEntry, letras: str,
                      probabilidade) -> float:
        """
        Quanto o desenho deste box sustenta **estas** letras, de 0 a 1 (F69).

        É a pergunta invertida do árbitro. O `_cortes_endossados` pergunta "vale
        a pena cortar aqui?" e deixa o modelo escolher o que leu; aqui o
        dicionário já disse o que deveria estar escrito, e o que falta é saber
        se o papel concorda. `probabilidade(recorte, char) -> float` é quem
        responde, injetado como o `arbitro` é — este módulo não conhece o modelo.

        **A nota é a do pedaço mais fraco**, e não a média, pela mesma razão que
        o `_cortes_endossados` usa a menor: `dynamic` só está ali se o `y` e o
        `n` estiverem os dois, e uma média deixaria um `y` convincente pagar por
        um `n` que não existe.

        **O corte é o melhor entre os que se experimenta**, porque a partição
        certa não se conhece: parte-se da repartição igual e varre-se em volta
        (`DESLOCAMENTO_DE_PROVA`). Uma letra só dispensa corte, e é o caso do
        box largo que escondia uma ligadura inteira.

        **A varredura repete pedaço, e o pedaço é que custa.** Com três letras
        são 25 partições e 75 perguntas, mas só 35 pedaços distintos: a primeira
        letra tem 5 recortes possíveis, e cada um deles reaparece nas 5
        partições que só diferem da segunda junta em diante. Guardar a resposta
        por `(início, fim, letra)` não muda nota nenhuma — o modelo é
        determinístico — e é o que faz a fase caber em minutos.
        """
        largura = box.x2 - box.x1
        if not letras or largura <= 0:
            return 0.0

        def recorte_de(ini, fim):
            pedaco = imagem_cinza[box.y1:box.y2, box.x1 + ini:box.x1 + fim]
            if pedaco.size and getattr(box, "negativo", False):
                return negativo.positivar(pedaco)
            return pedaco

        visto = {}

        def pontuar(ini, fim, c):
            chave = (ini, fim, c)
            if chave not in visto:
                pedaco = recorte_de(ini, fim)
                visto[chave] = (0.0 if pedaco.size == 0
                                else float(probabilidade(pedaco, c)))
            return visto[chave]

        def nota(limites):
            menor = 1.0
            for (ini, fim), c in zip(zip(limites, limites[1:]), letras):
                menor = min(menor, pontuar(ini, fim, c))
                if menor == 0.0:
                    return 0.0
            return menor

        if len(letras) == 1:
            return nota([0, largura])

        # Cada junta desliza em volta da repartição igual, independente das
        # outras: com três letras, a primeira pode estar larga e a segunda
        # estreita, e uma varredura única não alcançaria as duas.
        letra = largura / len(letras)
        passos = []
        d = -BoxService.DESLOCAMENTO_DE_PROVA
        while d <= BoxService.DESLOCAMENTO_DE_PROVA + 1e-9:
            passos.append(d)
            d += BoxService.PASSO_DE_PROVA

        melhor = 0.0
        for combinacao in itertools.product(passos, repeat=len(letras) - 1):
            limites = [0]
            for i, desloc in enumerate(combinacao, start=1):
                corte = int(round(letra * (i + desloc)))
                # Cada pedaço precisa sobrar com alguma coisa dentro.
                limites.append(min(largura - 1, max(limites[-1] + 1, corte)))
            limites.append(largura)
            melhor = max(melhor, nota(limites))
            if melhor == 1.0:
                break
        return melhor

    @staticmethod
    def prova_de_reparo(imagem_cinza: np.ndarray, boxes: List[BoxEntry],
                        probabilidade):
        """
        O `provar` que o `lexico.reparar` consome (F69), pronto para injetar.

        O léxico raciocina em índices de box e em letras; a prova mora na
        imagem. Esta função é a única costura entre os dois, e existe para que
        `core.lexico` continue sem saber o que é um pixel — como
        `generate_boxes_opencv` não sabe o que é um modelo, e recebe o
        `arbitro`.

        A assinatura devolvida é `(caixas, letras) -> nota`, onde `caixas` são
        índices em `boxes`, na ordem em que a palavra os atravessa.

        **Um trecho mascarado pode cair sobre mais de um box**, quando duas
        colagens se encostam, e aí não se sabe quantas letras couberam em cada
        um: reparte-se o pedaço do candidato entre eles de todos os modos com
        pelo menos uma letra por box, e vale o melhor. A nota da repartição é a
        do box mais fraco, pelo mesmo motivo que a de `provar_letras` é a da
        letra mais fraca — a palavra só está ali se **todos** os pedaços
        estiverem.

        **Menos letras que boxes é impossível**, e sai 0,0: cada caractere
        mascarado veio de um box largo, então o candidato traz pelo menos uma
        letra por box. Chegar aqui seria máscara e boxes discordando, e a
        resposta segura é não autorizar a troca.

        A memória é o que torna a fase pagável: os candidatos de uma mesma
        palavra caem todos sobre os mesmos boxes, e muitos repetem as letras do
        trecho (`dynamic` e `dynamics` perguntam o mesmo `yn`). Sem ela cada
        candidato repagaria a varredura inteira de `provar_letras`.
        """
        memoria = {}

        def provar(caixas, letras: str) -> float:
            caixas = tuple(caixas)
            if not letras or not caixas or len(letras) < len(caixas):
                return 0.0
            chave = (caixas, letras)
            if chave in memoria:
                return memoria[chave]

            if len(caixas) == 1:
                nota = BoxService.provar_letras(imagem_cinza, boxes[caixas[0]],
                                                letras, probabilidade)
            else:
                nota = 0.0
                for cortes in itertools.combinations(range(1, len(letras)),
                                                     len(caixas) - 1):
                    limites = (0,) + cortes + (len(letras),)
                    menor = 1.0
                    for (ini, fim), i in zip(zip(limites, limites[1:]), caixas):
                        menor = min(menor, BoxService.provar_letras(
                            imagem_cinza, boxes[i], letras[ini:fim],
                            probabilidade))
                        if menor == 0.0:
                            break
                    nota = max(nota, menor)
                    if nota == 1.0:
                        break

            memoria[chave] = nota
            return nota

        return provar

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

    #: Largura mínima de uma calha, em larguras medianas de caractere.
    #:
    #: **Eram 3,0 até a F61, e é por isso que o livro de duas colunas saía
    #: embaralhado.** A régua nunca foi medida: 3,0 é largo demais para a calha
    #: que estes livros usam de verdade. Medido em 33 páginas de 6 livros, com a
    #: segmentação de produção e o vão da projeção em larguras medianas:
    #:
    #:     calha de verdade   Nunn        1,00 – 1,18   (17–20 px)
    #:                        Kasparov    2,58 – 3,31   (49–58 px)
    #:                        Yusupov     2,59 – 2,94   (44–46 px)
    #:     vão que não é      Aagaard AM  0,06 – 0,12   (1–2 px)   ← ver abaixo
    #:                        Yusupov     0,17 – 0,75
    #:
    #: **A linha do Aagaard não vale, e a F70 mostrou por quê.** O `Attacking
    #: Manual` é de **duas** colunas, e o que se mediu ali foi a calha dele
    #: apagada pelo cabeçalho corrente — não um vão inocente. Ele entrou na
    #: medição como controle de coluna única e não era um; o controle de
    #: verdade é o Darcy Lima. Pelo mesmo motivo, os 1,00–1,18 do Nunn são o
    #: resto que o cabeçalho deixou, e não a calha: ela tem ~3,3 (56 px). Com a
    #: projeção por linhas da F70 a régua deixa de depender desses números —
    #: mas 0,8 continua sendo o limiar, porque baixá-lo nunca foi o remédio.
    #:
    #: A 3,0, o Nunn nunca é detectado e o Kasparov é detectado **em algumas
    #: páginas e não em outras** — que é exatamente a queixa: o texto da coluna
    #: da esquerda se mistura com o da direita "em muitos trechos". O limiar cai
    #: para 0,8: 1,25× abaixo da menor calha medida e 6,7× acima do maior vão
    #: que não é calha. O espaço entre palavras não chega perto porque a
    #: projeção é da **página inteira** — para sobreviver a ela, toda linha
    #: teria de ter espaço no mesmo x.
    CALHA_EM_CARACTERES = 0.8

    #: O piso da calha em frações da largura do texto, para a página cuja
    #: largura mediana de caractere não vale nada.
    #:
    #: Existe desde a F1.6 (a 0,02) e continua existindo pelo mesmo motivo que
    #: `escala_de_texto`: numa página com trama a mediana simples desaba para 2
    #: px, e `0,8 × 2` deixaria qualquer respiro virar coluna. Medido na página
    #: 66 do Chess Evolution 1 — trama de scan na margem, mediana 2 px, calha de
    #: verdade com 34 px —, 1% da largura do texto dá 18 px: barra o respingo e
    #: deixa passar a calha. A 2% barrava também a do Nunn.
    CALHA_DA_PAGINA = 0.01

    #: Largura mínima de uma coluna, em frações da largura do texto.
    #:
    #: **É o que separa duas colunas de uma tabela de duas casas.** Sem ele, o
    #: sumário do Practical Chess Defence — número do capítulo, título, número
    #: da página — vira três colunas, e o livro exportado sai com dez números,
    #: dez títulos e dez páginas em vez de dez linhas. Medido, a "coluna" de
    #: número de capítulo tem 2% da largura do texto e a de número de página 4%,
    #: contra 48% de cada coluna de verdade no Kasparov e 45% da mais estreita
    #: no Chess Evolution 1. O limiar fica no vão: 2,5× acima do maior falso e
    #: 4,5× abaixo da menor coluna de verdade.
    COLUNA_MINIMA = 0.10

    #: Quantas linhas de texto podem cruzar a calha sem que ela deixe de existir.
    #:
    #: **Uma letra do cabeçalho apagava a calha da página inteira** (F70). A
    #: projeção era um OR — `ocupado[x]` valia para qualquer box —, e o cabeçalho
    #: corrente centralizado pousa justamente em cima da calha. Medido no Nunn,
    #: um único box de 25×27 px em y≈105 derruba a calha de 31 px para 7, e a
    #: página sai com as duas colunas intercaladas: é a queixa da F61 na sua
    #: última forma, e explica por que o defeito era errático — a variável é onde
    #: a letra do cabeçalho calha de cair.
    #:
    #: **A calha de verdade do Nunn tem ~56 px (3,3 larguras medianas)**, e não
    #: os 14–20 que a régua via. O que a F61 mediu foi o resto que o cabeçalho
    #: deixou, e é por isso que `CALHA_EM_CARACTERES` precisou descer tanto.
    #:
    #: Tolerar **uma** linha, medido nas 456 páginas de prosa de 4 livros:
    #:
    #:     Nunn (2 colunas)           298 → 316 de 352 páginas
    #:     Aagaard (2 colunas)          3 →  28 de 30
    #:     Yusupov Complete (2 col)    23 →  26 de 35
    #:     Darcy Lima (1 coluna)        0 →   0 de 39   ← o controle
    #:
    #: Duas linhas não acrescentam nada no Nunn e começam a partir o Yusupov
    #: (32 de 35), então o ponto é uma.
    LINHAS_NA_CALHA = 1

    #: A partir de quantas linhas a página pode desprezar uma delas na calha.
    #:
    #: **Uma linha de cinco é 20% da página, e aí a tolerância inventa calha.**
    #: Medido no recorte de página real do `test_f16_colunas` — cinco linhas,
    #: duas colunas —, tolerar uma abre uma terceira faixa onde a contagem
    #: mínima é 1: o vão entre duas palavras que calham de se alinhar em cinco
    #: linhas seguidas. Na página inteira isso não acontece, porque nenhum x
    #: central sobrevive a quarenta linhas de texto justificado.
    #:
    #: O limiar fica no vão entre o falso e o verdadeiro: 2,4× acima do recorte
    #: de 5 linhas e 1,25× abaixo da **menor** página de prosa medida — 15
    #: linhas no Nunn, contra 23 no Aagaard e 30 no Darcy Lima. Abaixo dele vale
    #: a régua de antes, nenhuma linha tolerada, que é o lado seguro do erro.
    LINHAS_PARA_TOLERAR = 12

    @staticmethod
    def _linhas_por_x(linhas: List[List[BoxEntry]], x_min: int,
                      largura: int) -> np.ndarray:
        """
        Quantas linhas de texto cobrem cada x.

        **O que marca é a união dos boxes da linha, e não a caixa que a
        envolve.** Numa página de duas colunas a banda da `_linhas` recolhe a
        linha da esquerda e a da direita juntas, porque estão na mesma altura;
        envolvê-las numa caixa só encheria a calha, que é exatamente o vão que
        se quer enxergar vazio.
        """
        conta = np.zeros(largura + 2, dtype=np.int32)
        for linha in linhas:
            desta = np.zeros(largura + 2, dtype=bool)
            for b in linha:
                desta[max(0, b.x1 - x_min):max(0, b.x2 - x_min) + 1] = True
            conta += desta
        return conta

    @staticmethod
    def detectar_colunas(boxes: List[BoxEntry],
                         calha_minima: int = None) -> List[Tuple[int, int]]:
        """
        Faixas horizontais de coluna, em ordem de leitura.

        Projeta a ocupação dos boxes no eixo X e procura vãos verticais sem
        conteúdo nenhum. Usa os boxes, não os pixels: o vão que interessa é
        onde não há *caractere*, e assim funciona igual para página escaneada
        e para imagem já limpa.

        **A projeção conta linhas, e não boxes** (F70). Como OR, ela dava a
        calha por inexistente assim que **um** caractere caía dentro dela — e o
        cabeçalho corrente centralizado cai. Contando linhas, o cabeçalho é uma
        só e passa por `LINHAS_NA_CALHA`, enquanto o miolo de uma página de
        coluna única é coberto por todas as quarenta: o espaço entre palavras do
        texto justificado cai num x diferente a cada linha, e nenhum x central
        sobrevive à conta.

        O limiar é relativo à largura mediana de caractere — uma calha de
        verdade é muito mais larga que o espaço entre palavras. Fixar a busca
        numa faixa central (como faz o DocuVision, 42%–58% da largura) só acha
        duas colunas simétricas; aqui a calha pode estar em qualquer posição, e
        podem ser mais de duas.

        **Achar o vão não basta: a faixa que ele deixa tem de ser uma coluna**
        (F61). O vão entre o título e o número da página de um sumário é largo,
        e tratá-lo como calha faz o livro sair com os títulos todos juntos e os
        números todos juntos. Quem passa é a faixa larga o bastante para ter
        texto dentro; a estreita se funde à vizinha — nenhum box se perde.
        """
        if not boxes:
            return []

        x_min = min(b.x1 for b in boxes)
        x_max = max(b.x2 for b in boxes)
        largura = x_max - x_min
        if largura <= 1:
            return [(x_min, x_max)]

        linhas = BoxService._linhas(boxes)
        tolerado = (BoxService.LINHAS_NA_CALHA
                    if len(linhas) >= BoxService.LINHAS_PARA_TOLERAR else 0)
        livre = BoxService._linhas_por_x(linhas, x_min, largura) <= tolerado

        if calha_minima is None:
            larguras = sorted(b.x2 - b.x1 for b in boxes)
            mediana = larguras[len(larguras) // 2] or 1
            calha_minima = max(int(mediana * BoxService.CALHA_EM_CARACTERES),
                               int(largura * BoxService.CALHA_DA_PAGINA), 4)

        cortes = []
        inicio = None
        for i, vago in enumerate(livre):
            if vago:
                if inicio is None:
                    inicio = i
            else:
                # **O vão que encosta na margem esquerda não é calha.** Com o OR
                # ele não tinha como existir — algum box começa em `x_min` por
                # definição —, mas a tolerância o cria na página em que só o
                # cabeçalho alcança a margem. Abrir faixa ali deixaria os boxes
                # dele fora de toda coluna, e o `_por_colunas` os despeja no fim
                # da página.
                if (inicio is not None and inicio > 0
                        and i - inicio >= calha_minima):
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

        faixas = [f for f in faixas if f[1] > f[0]] or [(x_min, x_max)]
        return BoxService._fundir_faixas_estreitas(faixas, largura)

    @staticmethod
    def _fundir_faixas_estreitas(faixas: List[Tuple[int, int]],
                                 largura: int) -> List[Tuple[int, int]]:
        """
        Funde na vizinha toda faixa estreita demais para ser coluna.

        Funde, e não descarta: a faixa é o critério de quem entra em qual
        coluna, e uma faixa a menos seria um punhado de boxes lidos no fim da
        página, fora de ordem. Some pela calha **mais estreita** das duas ao
        redor, que é a que menos afirma separação.
        """
        minima = largura * BoxService.COLUNA_MINIMA
        faixas = list(faixas)
        while len(faixas) > 1:
            i = min(range(len(faixas)), key=lambda j: faixas[j][1] - faixas[j][0])
            if faixas[i][1] - faixas[i][0] >= minima:
                break
            esquerda = faixas[i][0] - faixas[i - 1][1] if i else None
            direita = (faixas[i + 1][0] - faixas[i][1]
                       if i + 1 < len(faixas) else None)
            if direita is None or (esquerda is not None and esquerda <= direita):
                faixas[i - 1:i + 1] = [(faixas[i - 1][0], faixas[i][1])]
            else:
                faixas[i:i + 2] = [(faixas[i][0], faixas[i + 1][1])]
        return faixas

    @staticmethod
    def _linhas(boxes: List[BoxEntry]) -> List[List[BoxEntry]]:
        """
        Agrupa em linhas de texto por sobreposição vertical, de cima para baixo.

        Um box entra na linha corrente se o seu centro vertical não passa do
        fundo médio da linha (com folga de 20% da própria altura); senão abre
        uma linha nova. Dentro da linha a ordem é a de entrada — quem precisa
        delas ordenadas usa `_agrupar_em_linhas`.

        **O fundo médio sai só das caixas altas** (F64). O apóstrofo mora na
        altura de ascendente e a ordenação é por `y1`, então ele chega antes da
        letra que ele segue e **abre a banda sozinho** — com o fundo da banda
        cravado na altura de x, nenhuma letra da linha consegue entrar. Medido
        nas 10 páginas rotuladas, 7 bandas feitas só de caixa curta, todas aspas
        ou apóstrofo, e no livro exportado isso é `White's` saindo `' White s`.

        Enquanto a banda só tiver caixa curta ela não tem fundo, e a próxima
        caixa entra sem discussão — que é o certo: uma aspa não estabelece
        linha de base, e a letra que vem depois dela é da linha dela.
        """
        if not boxes:
            return []

        # Tardio de propósito: `leitura_de_linha` importa `notacao`, que importa
        # este módulo. Em tempo de execução tudo já está carregado, e a régua da
        # caixa curta tem de ser **uma** — foi cópia divergente que deixou a
        # F1.5 medir uma coisa e a aplicação fazer outra.
        from core.leitura_de_linha import CAIXA_CURTA

        alturas = sorted(b.y2 - b.y1 for b in boxes)
        curto = (alturas[len(alturas) // 2] or 1) * CAIXA_CURTA

        grupos: List[List[BoxEntry]] = []
        atual: List[BoxEntry] = []
        altos: List[int] = []           # os fundos do que já é letra na banda

        for b in sorted(boxes, key=lambda b: b.y1):
            if atual and altos:
                fundo = sum(altos) / len(altos)
                if (b.y1 + b.y2) / 2 > fundo + (b.y2 - b.y1) * 0.2:
                    grupos.append(atual)
                    atual, altos = [], []
            atual.append(b)
            if (b.y2 - b.y1) >= curto:
                altos.append(b.y2)

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
        """
        Coluna a coluna; dentro de cada uma, linha a linha.

        **Quem cai dentro da calha fica com a faixa mais próxima** (F70), e não
        no fim da página. Antes sobrava: o box que não coubesse em faixa nenhuma
        era despejado depois de tudo, e isso era inofensivo enquanto a calha
        tinha 20 px e nada cabia lá dentro. Com a calha de verdade — 56 px no
        Nunn — quem mora ali é o caractere central do cabeçalho corrente, o
        mesmo que apagava a calha, e ele passava a sair depois da página
        inteira. É a regra que o `livro._coluna_de` já usava para decidir de
        quem a figura é vizinha.
        """
        def da_coluna(b: BoxEntry) -> int:
            cx = (b.x1 + b.x2) / 2
            for i, (x1, x2) in enumerate(colunas):
                if x1 <= cx <= x2:
                    return i
            return min(range(len(colunas)),
                       key=lambda i: min(abs(cx - colunas[i][0]),
                                         abs(cx - colunas[i][1])))

        saida = []
        for i in range(len(colunas)):
            desta = [b for b in boxes if da_coluna(b) == i]
            if desta:
                saida.extend(BoxService._agrupar_em_linhas(desta))
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

    #: Folga vertical máxima para colar um pedaço curto num glifo **alto** —
    #: o pingo do 'i' e do 'j', o ponto do '?' e do '!', o acento. Em alturas
    #: medianas de box.
    #:
    #: Medido nas 11 páginas rotuladas, a folga do diacrítico de verdade é bem
    #: menor que 0,30: 'i' (386 casos) vai a 0,23, '?' e '!' a 0,23, 'j' a 0,25,
    #: '±' a 0,17. Do outro lado do vale, a pontuação da **linha de cima** colada
    #: num glifo alto começa em 0,55 (',' e 'P') e vai a 0,79. Nada da população
    #: medida cai entre 0,25 e 0,55.
    FOLGA_DE_DIACRITICO = 0.30

    #: A mesma folga quando os **dois** pedaços são curtos: ':' e ';', que são
    #: dois pontos separados por meia altura de x e por isso precisam de mais
    #: espaço que um pingo. Medido, ':' fica em 0,45 e ';' em 0,43.
    #:
    #: São duas folgas e não uma porque a maior delas, aplicada ao par
    #: curto+alto, é justamente o que deixa o ponto da linha de cima entrar.
    FOLGA_DE_PONTUACAO = 0.50

    @staticmethod
    def _grade_de_caixas(boxes: List[BoxEntry], celula: int) -> dict:
        """Índice espacial das caixas: célula quadrada -> índices que a tocam (F96).

        Uma caixa entra em todas as células que o seu retângulo cruza, e não só
        na do canto: o tabuleiro e a tarja cruzam dezenas delas, e indexá-los
        por um ponto só os faria sumir da busca de quase todo vizinho.
        """
        grade: dict = {}
        for k, b in enumerate(boxes):
            for cx in range(b.x1 // celula, b.x2 // celula + 1):
                for cy in range(b.y1 // celula, b.y2 // celula + 1):
                    grade.setdefault((cx, cy), []).append(k)
        return grade

    @staticmethod
    def _vizinhos_na_grade(grade: dict, celula: int, i: int, usados: set,
                           x1: int, y1: int, x2: int, y2: int) -> List[int]:
        """Os índices maiores que `i` cujas caixas tocam o retângulo, **em ordem**.

        A ordem é a de índice, e não é detalhe de implementação: o merge fica
        com o *primeiro* candidato que passa nas duas provas, então devolver
        outra ordem trocaria qual caixa cresce e qual é absorvida.

        A limpeza de `usados` acontece aqui, na célula visitada. Sem ela, uma
        região densa pagaria de novo, a cada busca, por caixas já consumidas —
        que é metade do custo que esta fase foi tirar.
        """
        achados = set()
        for cx in range(x1 // celula, x2 // celula + 1):
            for cy in range(y1 // celula, y2 // celula + 1):
                chave = (cx, cy)
                lista = grade.get(chave)
                if not lista:
                    continue
                vivos = [k for k in lista if k not in usados]
                if len(vivos) != len(lista):
                    grade[chave] = vivos
                achados.update(k for k in vivos if k > i)
        return sorted(achados)

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

        **A folga depende de quem está sendo colado** (F3.11). A régua única de
        antes — `max(10, min(30, mediana * 0,8))` — media 0,8 alturas medianas
        nas páginas medidas, e o ponto final da linha de cima está a 0,55–0,79
        de um glifo alto da linha de baixo: cabia inteiro dentro dela. Como o
        laço refaz a busca com a caixa já crescida, o primeiro ponto engolido
        abria caminho para os vizinhos, e um '...' entrava com os três.
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
        MIN_HORIZ_OVERLAP_RATIO = 0.3

        # **O que tirava minutos de uma página aqui (F96).** O laço de dentro
        # varria a página inteira para cada caixa, e **cada fusão o reiniciava**.
        # Medido no Yusupov a 300 dpi, a mesma página antes e depois do índice:
        #
        #     página   caixas   saída     antes    depois
        #        198   11.457   3.745    9,70 s    1,96 s
        #        134   38.964   2.749   95,74 s   21,75 s
        #         96   85.903   2.252  250,81 s   62,77 s
        #
        # A terceira coluna é o que explica as outras duas: 38.964 caixas viram
        # 2.749, isto é, ~36 mil fusões, cada uma seguida de uma varredura nova
        # do começo. Não é o `n²` da varredura só; é o `n²` vezes as fusões.
        #
        # **E não fica linear**: a página que cresce absorve milhares de caixas,
        # e o retângulo de busca cresce com ela. O que o índice tira é o custo
        # de olhar a página inteira; o que sobra é o custo de olhar a mancha,
        # que numa página de trama é grande. Ver o que a F96 deixou em aberto.
        #
        # **As duas condições de merge são locais**, e é isso que o índice usa:
        # nenhum critério aceita distância vertical acima de `folga_maxima`, e a
        # prova horizontal exige sobreposição em `x` — logo o candidato tem de
        # tocar o retângulo `(x1, y1) .. (x2, y2 + folga_maxima)` da caixa que
        # está crescendo. `_vizinhos_na_grade` devolve exatamente quem toca
        # esse retângulo, **em ordem de índice**, que é a ordem em que o laço de
        # antes os encontraria. Mesma escolha, mesma saída — o que muda é não
        # olhar as outras 85 mil.
        #
        # **`ordenada` não é suposição, e o índice depende dela.** Numa lista
        # ordenada por `y1`, toda caixa de índice maior começa em `y1` maior ou
        # igual, e o retângulo acima é um limite de verdade. Quem vem de
        # `boxes_antes_do_descarte` chega ordenado — conferido nas páginas 10,
        # 40, 96 e 198 do Yusupov, zero pares fora de ordem —, mas
        # `vertical.fundir_pingos` chama isto com as coordenadas transpostas, e
        # ali `y1` é o `x1` de origem. Quando a lista não chega ordenada, o laço
        # é exatamente o de antes: o índice sai de cena, e com ele qualquer
        # risco de mudar resultado. `tests/test_f311_merge.py` prende os dois
        # caminhos contra uma transcrição do laço original.
        ordenada = all(boxes[k].y1 <= boxes[k + 1].y1
                       for k in range(len(boxes) - 1))
        folga_maxima = max(2.0, median_h * max(BoxService.FOLGA_DE_DIACRITICO,
                                               BoxService.FOLGA_DE_PONTUACAO))
        celula = max(16, int(median_h))
        grade = BoxService._grade_de_caixas(boxes, celula) if ordenada else None

        merged_boxes = []
        used_indices = set()

        for i in range(len(boxes)):
            if i in used_indices:
                continue

            b1 = boxes[i]
            # `moldura` viaja junto com `negativo`, e pelo mesmo motivo: o merge
            # constrói uma caixa nova, e o que não for copiado aqui se perde
            # calado. Medido na página 236 do Nunn, os 277 boxes lidos de dentro
            # da tabela chegavam marcados e saíam daqui sem marca nenhuma (F72).
            current_merged = BoxEntry(
                b1.char, b1.x1, b1.y1, b1.x2, b1.y2,
                negativo=getattr(b1, "negativo", False),
                moldura=getattr(b1, "moldura", False),
            )
            used_indices.add(i)

            merged_something = True
            while merged_something:
                merged_something = False

                # **O índice só vale enquanto a busca for pequena.** Uma caixa
                # do tamanho da página — a tarja do `negativo`, a moldura de
                # uma tabela — faz o retângulo cobrir tudo, e aí percorrer as
                # células custa mais que percorrer as caixas: medido, 3.000
                # caixas mais **uma** do tamanho da página iam de 0,03 s para
                # 10,52 s. Quando as células passam de quantas caixas ainda
                # restam, a varredura direta é a barata, e é ela que roda.
                limite_y = current_merged.y2 + int(folga_maxima) + 1
                celulas = ((current_merged.x2 // celula
                            - current_merged.x1 // celula + 1)
                           * (limite_y // celula
                              - current_merged.y1 // celula + 1))

                if grade is not None and celulas <= len(boxes) - i:
                    candidatos = BoxService._vizinhos_na_grade(
                        grade, celula, i, used_indices,
                        current_merged.x1, current_merged.y1,
                        current_merged.x2, limite_y)
                else:
                    candidatos = range(i + 1, len(boxes))

                for j in candidatos:
                    if j in used_indices:
                        continue

                    b2 = boxes[j]

                    # Numa lista ordenada por `y1` — e os candidatos da grade
                    # também saem em ordem de índice —, a primeira caixa longe
                    # demais garante que o resto está mais longe ainda.
                    if ordenada and b2.y1 - current_merged.y2 > folga_maxima:
                        break
                    dist_vert = b2.y1 - current_merged.y2

                    h1 = current_merged.y2 - current_merged.y1
                    h2 = b2.y2 - b2.y1

                    is_tall_1 = h1 > SHORT_THRESH
                    is_tall_2 = h2 > SHORT_THRESH

                    if is_tall_1 and is_tall_2:
                        max_vert_dist = 2
                    elif is_tall_1 or is_tall_2:
                        # curto + alto: diacrítico. É o par que o ponto da linha
                        # de cima imita, e por isso o mais apertado dos três.
                        max_vert_dist = median_h * BoxService.FOLGA_DE_DIACRITICO
                    else:
                        max_vert_dist = median_h * BoxService.FOLGA_DE_PONTUACAO

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
                        # Basta um dos dois ter vindo de dentro da moldura: o
                        # pingo e o corpo do 'i' são o mesmo caractere, e a
                        # caixa fundida está onde os dois estavam.
                        current_merged.moldura = (current_merged.moldura
                                                  or getattr(b2, "moldura", False))

                        used_indices.add(j)
                        merged_something = True
                        break

            merged_boxes.append(current_merged)

        return merged_boxes

    #: O corte manual procura o vale só no miolo do box: perto da borda todo
    #: perfil de tinta desce, e cortar ali devolve uma lasca em vez de um
    #: caractere. É a fração descartada de **cada** ponta. Medido nos 5.747
    #: pares descritos em `split_box`, tem platô entre 0,10 e 0,20 (0,3% de eixo
    #: errado) e piora a partir de 0,25 (0,6%).
    MARGEM_DO_CORTE = 0.15

    #: Fundura mínima para o vale mandar no lugar da geometria. A população
    #: medida é **insensível** a este número — de 0,00 a 0,50 o resultado não
    #: muda —, porque par de caracteres vizinhos sempre tem vale de verdade. Ele
    #: existe para o caso que a medição não tem: o box sem vale nenhum (um glifo
    #: só, um box vazio), onde a resposta certa é "não sei, corte no meio".
    MIN_FUNDURA_DO_VALE = 0.25

    @staticmethod
    def _vale_mais_fundo(perfil: np.ndarray, margem: float):
        """
        `(posição, fundura)` do vale interno mais nítido de um perfil de tinta.

        **A fundura é medida contra o menor dos dois picos que ladeiam o vale**,
        e é isso que distingue um vale de uma descida. Num box com 'ba' o perfil
        por linha *cai* na faixa do ascendente do 'b' — pouca tinta lá em cima,
        muita embaixo, onde estão as duas letras. Comparado com o pico geral
        aquilo pontua como vale fundo; comparado com o pico *de cima*, que é o
        próprio ascendente, pontua zero, que é o que ele é.

        Devolve `None` quando não há vale interno — perfil curto demais, sem
        tinta, ou monotônico.
        """
        perfil = np.asarray(perfil, dtype=float)
        n = len(perfil)
        if n < 3:
            return None

        ini = max(1, int(round(n * margem)))
        fim = n - ini
        if fim <= ini:
            return None

        # Pico acumulado de cada lado: `pico_esq[i]` é o máximo de tudo até `i`,
        # `pico_dir[i]` o de tudo a partir de `i`. Com eles o vale largo sai de
        # graça — o flanco de uma posição no meio do vão ainda é o pico da letra.
        pico_esq = np.maximum.accumulate(perfil)
        pico_dir = np.maximum.accumulate(perfil[::-1])[::-1]

        pos = np.arange(ini, fim)
        flanco = np.minimum(pico_esq[pos - 1], pico_dir[pos + 1])
        fundura = np.where(flanco > 0, 1.0 - perfil[pos] / np.maximum(flanco, 1e-9), 0.0)

        melhor = float(fundura.max())
        if melhor <= 0:
            return None
        # Empate resolve pelo mais central: num vão de várias colunas todas
        # empatam em zero de tinta, e o meio do vão é o corte que o olho espera.
        centro = (n - 1) / 2.0
        escolhida = min(pos[fundura >= melhor - 1e-9], key=lambda p: abs(p - centro))
        return int(escolhida), melhor

    @staticmethod
    def split_box(box: BoxEntry, imagem_cinza: np.ndarray = None) -> List[BoxEntry]:
        """
        Divide um box em dois, **no vão entre os glifos**. Char vazio nos dois.

        **A regra antiga era a proporção do box, e ela erra o eixo em 9,3% dos
        casos.** "Mais largo que alto corta em X, senão em Y, sempre no meio":
        num box com 'it', 'is', 'ba' ou 'll' — letra alta ao lado de letra baixa
        — a caixa sai mais alta que larga, e o Ctrl+D devolvia as duas metades
        *uma embaixo da outra*. Era o defeito relatado, e ele tem nome: as letras
        estreitas e altas do inglês corrido.

        **O que decide agora é onde a tinta abre.** Perfil de tinta nos dois
        eixos, vale mais nítido de cada um (`_vale_mais_fundo`), e ganha o eixo
        com o vale mais fundo. Sem imagem, ou sem vale em eixo nenhum, vale a
        regra antiga — que é a resposta honesta para um box onde não há vão.

        **Medido nas 9 páginas rotuladas**, unindo cada par de caracteres
        vizinhos da verdade rotulada num box só — que é exatamente o box que o
        usuário manda dividir. 5.747 pares lado a lado e 57 empilhados; "corte
        bom" é cair a menos de 10% do lado do box da fronteira verdadeira:

            regra        lado a lado (n=5.747)      empilhados (n=57)
                         eixo errado  corte bom   eixo errado  corte bom
            geometria       9,3%        61,6%        0,0%       94,7%
            vale de tinta   0,3%        98,6%        0,0%       94,7%

        **A coluna dos empilhados é a que prova que não houve troca de um erro
        por outro.** O eixo Y continua sendo escolhido onde ele é o certo — o
        vale por linha existe de verdade ali —, com o mesmo acerto de antes.

        O que sobra de erro é o pingo do 'i' sobre o braço do 'w': em 'wi' e 'vi'
        há um vale horizontal real embaixo do pingo, e ele ganha do vertical.
        Quinze casos em 5.747.

        A binarização é a do **recorte**, com Otsu, e não a da página: sai igual
        (15 erros contra 17) e poupa binarizar a folha inteira a cada Ctrl+D.

        As metades herdam o ângulo (F8.1) e a polaridade (F10): quem parte um
        box de rótulo vertical — ou de tarja preta — em dois quer dois pedaços
        do mesmo rótulo, não dois boxes normais.
        """
        x1, y1, x2, y2 = box.x1, box.y1, box.x2, box.y2
        angulo = getattr(box, "angulo", 0)
        neg = getattr(box, "negativo", False)

        def em_x(corte):
            return [BoxEntry("", x1, y1, corte, y2, angulo=angulo, negativo=neg),
                    BoxEntry("", corte, y1, x2, y2, angulo=angulo, negativo=neg)]

        def em_y(corte):
            return [BoxEntry("", x1, y1, x2, corte, angulo=angulo, negativo=neg),
                    BoxEntry("", x1, corte, x2, y2, angulo=angulo, negativo=neg)]

        tinta = BoxService._tinta_do_box(box, imagem_cinza)
        if tinta is not None:
            margem = BoxService.MARGEM_DO_CORTE
            vx = BoxService._vale_mais_fundo(tinta.sum(axis=0), margem)
            vy = BoxService._vale_mais_fundo(tinta.sum(axis=1), margem)
            fx = vx[1] if vx else 0.0
            fy = vy[1] if vy else 0.0
            if max(fx, fy) >= BoxService.MIN_FUNDURA_DO_VALE:
                return em_x(x1 + vx[0]) if fx >= fy else em_y(y1 + vy[0])

        # Sem imagem ou sem vão: o meio geométrico, como sempre foi.
        if (x2 - x1) > (y2 - y1):
            return em_x((x1 + x2) // 2)
        return em_y((y1 + y2) // 2)

    @staticmethod
    def _tinta_do_box(box: BoxEntry, imagem_cinza: np.ndarray):
        """Máscara booleana da tinta dentro do box, ou `None` se não der."""
        if imagem_cinza is None:
            return None
        recorte = imagem_cinza[max(0, box.y1):box.y2, max(0, box.x1):box.x2]
        if recorte.size == 0 or min(recorte.shape[:2]) < 3:
            return None
        if getattr(box, "negativo", False):
            # Tarja preta (F10): sem positivar, o perfil mediria o fundo e o
            # vale cairia no meio da letra em vez de no vão entre duas.
            recorte = negativo.positivar(recorte)
        # Otsu e não "auto": recorte de caractere é bimodal por construção, e o
        # `auto` cairia no adaptativo — que numa área do tamanho de duas letras
        # não tem vizinhança suficiente para estimar fundo nenhum.
        return preprocess.binarize(recorte, "otsu") > 0

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


# ----------------------------------------------------------------------
# A faixa vertical da linha (F14 — a caixa alta que a normalização apaga)
# ----------------------------------------------------------------------

#: Quanto dois boxes precisam se sobrepor em y, em frações da menor altura,
#: para contarem como da mesma linha.
SOBREPOSICAO_DE_LINHA = 0.5

#: Altura máxima de um box, em medianas da página, para ele entrar na faixa.
#: Um diagrama ou uma capitular esticaria a faixa até engolir a linha inteira.
ALTURA_MAXIMA_DE_LINHA = 2.5


def faixas_de_linha(boxes):
    """
    `(topo, base)` da linha de cada box, na ordem de `boxes`.

    Existe para o último elo da cadeia de OCR. O recorte justo de um box é
    normalizado em altura antes de chegar ao classificador, e isso apaga a
    única coisa que separa `c` de `C` — o tamanho. Esticado até a faixa da
    linha, o glifo mantém a altura relativa e a caixa volta a ser legível;
    medido, 66,9% para 74,2% de acerto no EasyOCR.

    **É vizinhança de um salto, não fecho transitivo.** Cada box olha quem se
    sobrepõe a ele em y, e para. Encadear levaria uma faixa a atravessar a
    página por uma corrente de sobreposições parciais.

    **Box girado fica com a própria caixa.** Para texto vertical (F8.1) a faixa
    da linha é horizontal, e `recorte_de_pe` ainda vai girar o recorte; misturar
    as duas voltas aqui trocaria um ganho medido por um caso não medido. O box
    girado devolve `(y1, y2)` dele mesmo e segue como estava.
    """
    if not boxes:
        return []

    alturas = sorted(b.y2 - b.y1 for b in boxes)
    mediana = alturas[len(alturas) // 2] or 1
    teto = mediana * ALTURA_MAXIMA_DE_LINHA
    plausiveis = [b for b in boxes if (b.y2 - b.y1) <= teto
                  and not getattr(b, "angulo", 0)]

    saida = []
    for b in boxes:
        if getattr(b, "angulo", 0):
            saida.append((b.y1, b.y2))
            continue

        topo, base = b.y1, b.y2
        altura_b = max(b.y2 - b.y1, 1)
        for outro in plausiveis:
            cobertura = min(b.y2, outro.y2) - max(b.y1, outro.y1)
            if cobertura <= 0:
                continue
            menor = min(altura_b, max(outro.y2 - outro.y1, 1))
            if cobertura >= menor * SOBREPOSICAO_DE_LINHA:
                topo = min(topo, outro.y1)
                base = max(base, outro.y2)
        saida.append((topo, base))
    return saida
