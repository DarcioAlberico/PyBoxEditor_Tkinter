"""
Escala visual de confiança.

O `fallback_chain` sempre calculou a confiança de cada reconhecimento e o
código a jogava fora (`char, source, _ = ...`). É o dado mais útil que existe
para revisar OCR: com ele, revisar uma página de 2.000 caracteres deixa de ser
"reler tudo" e vira "conferir os 80 vermelhos".

Um estado que merece atenção: **sem informação** não é o mesmo que confiança
baixa. Um box carregado de um `.box` não traz confiança nenhuma (o formato do
Tesseract não guarda isso), e pintá-lo de vermelho diria "confira este" quando
o correto é "não sei". Por isso ele tem cor própria.
"""

LIMIAR_ALTO = 0.90
LIMIAR_MEDIO = 0.70

COR_VAZIO = "#9E9E9E"      # cinza  — box sem caractere
COR_SEM_INFO = "#3F7FBF"   # azul   — não avaliado
COR_BAIXA = "#E53935"      # vermelho
COR_MEDIA = "#FB8C00"      # laranja
COR_ALTA = "#2E9B4F"       # verde

COR_SELECAO = "#FFD400"    # amarelo — marcação de seleção

# Fora do dicionário (F9). **Não é um degrau da escala acima, e por isso é um
# sublinhado e não a cor do contorno**: o sinal do léxico é independente da
# confiança — a F1.9 mediu que 1,000 é a confiança mediana de um erro, e é
# justamente esse que o dicionário pega. Pintar o box roubaria a informação que já
# estava lá para mostrar outra.
COR_LEXICO = "#8E24AA"     # roxo

LEGENDA = [
    (COR_ALTA, f"≥{int(LIMIAR_ALTO * 100)}%"),
    (COR_MEDIA, f"≥{int(LIMIAR_MEDIO * 100)}%"),
    (COR_BAIXA, "baixa"),
    (COR_SEM_INFO, "s/ info"),
    (COR_VAZIO, "vazio"),
]

# Legenda própria, porque o eixo é outro: a escala acima é do caractere, esta é
# da palavra.
LEGENDA_LEXICO = (COR_LEXICO, "fora do dicionário")


def cor_do_box(box) -> str:
    """Cor do contorno conforme o quanto o caractere precisa de revisão."""
    if not box.char:
        return COR_VAZIO
    if not box.source:
        return COR_SEM_INFO
    if box.source in FONTES_SEMPRE_REVISADAS:
        # **A cor segue a fila, e não a confiança** (F53). Sem isto um box do
        # EasyOCR com 0,99 saía verde e mesmo assim entrava na fila: o usuário
        # navegava pendentes e via verde. Não é contradição a resolver
        # escolhendo um dos dois — é que naquele elo o número **não quer dizer
        # nada**, e a cor não pode fingir que quer.
        return COR_BAIXA
    if box.confidence >= LIMIAR_ALTO:
        return COR_ALTA
    if box.confidence >= LIMIAR_MEDIO:
        return COR_MEDIA
    return COR_BAIXA


#: Abaixo disto a leitura do k-NN iria para a revisão — e **está suspenso**.
#:
#: A F44 trocou o corte da fila por este, com uma tabela que dizia que ele
#: dominava a confiança nos dois eixos. A tabela estava errada por dois defeitos
#: do instrumento, achados na F47:
#:
#: - ela aplicava a margem do k-NN a **todo** box, e produção só a aplica onde a
#:   fonte é `learner`. Os boxes do EasyOCR entravam ordenados por um número de
#:   um classificador que o roteamento tinha recusado, e é justamente ali que os
#:   erros se concentram — 46% de acerto;
#: - e comparava cinco cortes de margem contra **um** ponto da confiança, o 0,90
#:   daqui de baixo. Duas réguas só se comparam a recall igual ou a custo igual.
#:
#: Com a régua certa não há domínio, e o corte que foi embarcado **pega menos
#: erro que o que ele substituiu**: 88 contra 123, em 10.504 boxes com 246 erros.
#:
#: **A F47 fechou a medição, e a resposta é ficar na confiança.** Varridas as
#: duas réguas, as curvas se cruzam:
#:
#:     à toa    conf pega   margem pega
#:       ~180          65            69
#:     ~1.050          91           112
#:     ~2.270         123           125     <- o ponto de operação de hoje
#:     ~4.200         195           176
#:
#: A margem ganha no meio (uns 20% a mais de erro a custo igual), **empata onde
#: o programa opera** e perde na cauda. Empate não paga troca. O que mudaria
#: isso é escolher outro ponto de operação: com orçamento para mil boxes em vez
#: de dois mil, a margem entrega 112 erros onde a confiança entrega 91 — e aí a
#: régua muda junto com a política, não antes dela.
#:
#: O campo `BoxEntry.margem` continua sendo preenchido, e isso é de propósito:
#: ele não custa consulta nenhuma (`predict_e_margem` faz a busca uma vez só) e
#: é o que a F47 precisa ter na mão para decidir com as duas curvas na mesma
#: tabela. O que está suspenso é **usá-lo para cortar**, não medi-lo.
LIMIAR_DE_MARGEM = 0.50


#: Fontes cuja confiança não diz nada, e que por isso entram na fila inteiras.
#:
#: **O EasyOCR está aqui porque a régua dele é plana** e porque o que sobra para
#: ele é ruim. Ele é o último elo: só vê o que a rede recusou e o k-NN recusou —
#: recorte-lixo, fragmento, glifo colado. Medido nesses boxes (F48):
#:
#:     regra                    marcados   pegos   à toa   escapam
#:     conf < 0,90 (antes)            63      39      24        53
#:     marcar todos (esta)           160      92      68         0
#:     o k-NN diverge do EasyOCR     139      90      49         2
#:
#: São **160 boxes com 92 erros** — 57% de erro, contra 2,3% da página inteira.
#: A régua antiga deixava 53 deles escaparem, e a razão está na F43: ali a
#: mediana de confiança é 0,9708 **no erro e no acerto**, então nenhum corte
#: separa nada.
#:
#: A linha do meio é a que entrou. A de baixo apara 19 alarmes à toa, e custa um
#: terceiro dado por box (o que o elo anterior respondeu) — não paga: 19 boxes
#: em 10.504, para perder 2 erros.
#:
#: Nas 3 páginas menos contaminadas a forma se repete: 26 erros em 44 boxes, a
#: régua antiga pegava 9 e deixava 17 escapar.
#:
#: **O custo é 68 boxes a mais na fila em 10 páginas** — sete por página.
#:
#: **Quem entra aqui entra por separação, e não por acerto** (F51, F54, F55). A
#: separação é a fração de pares (erro, acerto) que a régua daquela fonte põe na
#: ordem certa — 0,50 é moeda, e é o que torna qualquer corte inútil ali:
#:
#:     fonte           separação   população
#:     easyocr             0,582   último recurso da cadeia — **nesta lista**
#:     easyocr_so          0,776   o EasyOCR como leitor da página (F55)
#:     easyocr_linha       0,756   o que a linha trocou, na ação do leitor (F55)
#:     neural              0,634   96,6% da página no caminho neural (F51)
#:     learner             0,795   quase toda a página no híbrido (F51)
#:
#: A F53 manteve `easyocr_so` de fora citando "89,5% de acerto", que é o número
#: da **outra** ação a gravar essa fonte (F17, por linha; a por caractere acerta
#: 73,2%). A decisão estava certa e a justificativa não era: o que a sustenta é a
#: linha de cima — 0,776 é régua melhor que a da rede, que ninguém propõe marcar
#: inteira.
FONTES_SEMPRE_REVISADAS = frozenset({"easyocr"})


def precisa_revisao(box) -> bool:
    """
    Verdadeiro para o que o revisor deveria olhar: vazio ou confiança baixa.

    **A margem não decide aqui, e a F47 explica por quê** — ver
    `LIMIAR_DE_MARGEM`. A F44 a pôs no comando com uma medida furada e o efeito
    real foi achar menos erro; a regra voltou ao que era enquanto a comparação
    honesta não fica pronta.

    **Quem o EasyOCR respondeu entra sempre** — ver `FONTES_SEMPRE_REVISADAS`.
    Não é desconfiança do elo, é que a confiança dele não ordena nada: naqueles
    boxes a mediana é a mesma no erro e no acerto.
    """
    if not box.char:
        return True
    if not box.source:
        return False          # não avaliado não é o mesmo que suspeito
    if box.source in FONTES_SEMPRE_REVISADAS:
        return True
    return box.confidence < LIMIAR_ALTO


def rotulo(box) -> str:
    """
    Coluna curta de confiança para a lista lateral (4 caracteres).

    Fonte de régua plana não mostra número: escrever "99%" ao lado de um box
    vermelho e pendente seria contradizer duas vezes na mesma linha. O `!` diz
    o que é verdade ali — **há leitura, e o número dela não vale** —, que não é
    o mesmo que o `?` de "não avaliado" nem que uma porcentagem baixa.
    """
    if not box.char:
        return "   -"
    if not box.source:
        return "   ?"
    if box.source in FONTES_SEMPRE_REVISADAS:
        return "   !"
    return f"{box.confidence * 100:3.0f}%"
