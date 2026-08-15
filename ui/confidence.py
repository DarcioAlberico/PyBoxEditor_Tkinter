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
    if box.confidence >= LIMIAR_ALTO:
        return COR_ALTA
    if box.confidence >= LIMIAR_MEDIO:
        return COR_MEDIA
    return COR_BAIXA


#: Abaixo disto a leitura do k-NN vai para a revisão (F44).
#:
#: **Está numa escala diferente do `LIMIAR_ALTO`, e por isso tem nome próprio.**
#: Aquele corta confiança — distância absoluta, `1 - d/2000`. Este corta a
#: margem, a razão de Lowe, que pergunta outra coisa: não "isto se parece com
#: algo que eu já vi?" e sim "o vencedor estava claramente à frente?". Comparar
#: os dois números é comparar réguas.
#:
#: A F43 mediu por que são dois: **o roteamento gasta a primeira**. Quando o box
#: chega à fila, a pergunta da novidade já foi feita e respondida por quem
#: escolheu o classificador, e o que sobra por decidir é ambiguidade.
#:
#: Medido contra a regra que estava aqui, nas 10 páginas (246 erros) e nas 3
#: menos contaminadas (105 erros), que é a coluna que vale para livro novo:
#:
#:                          10 páginas              3 limpas
#:     regra              pegos    à toa        pegos    à toa
#:     conf < 0,90          123    2.266           53      918
#:     margem < 0,30        111      196           36       64
#:     margem < 0,50        141      501           55      189
#:     margem < 0,70        165    1.115           62      420
#:     margem < 0,90        178    2.331           72      951
#:
#: **0,50 domina a regra antiga nos dois eixos, nas duas amostras**: pega mais
#: erros (141 contra 123; 55 contra 53) abrindo quatro a cinco vezes menos
#: acerto à toa. As linhas de baixo também dominam, e a escolha entre elas é de
#: política — 0,90 acharia 55 erros a mais pelo mesmo trabalho de antes. O 0,50
#: é o ponto que melhora as duas colunas sem aumentar nenhuma.
#:
#: A vantagem **não** vem da contaminação, que era a suspeita óbvia: a distância
#: absoluta satura quando o vizinho é cópia da própria página, e as três limpas
#: são justamente onde ela não satura. O fator quase não se move entre as duas
#: colunas.
LIMIAR_DE_MARGEM = 0.50


def precisa_revisao(box) -> bool:
    """
    Verdadeiro para o que o revisor deveria olhar: vazio, ou duvidoso.

    "Duvidoso" mudou de definição na F44. Onde há **margem** — só o k-NN a
    produz —, é ela que decide, porque foi ela que mediu melhor como filtro. Nas
    outras fontes continua a confiança, que é o único número que existe.

    **A cor do box não segue esta regra**, e isso é deliberado: `cor_do_box` fica
    na confiança, que é o que a F25 mediu contra a calibração da rede e o que
    diz "o quanto esta leitura se parece com o que a base conhece". Um box pode
    sair verde e mesmo assim entrar na fila — quer dizer "parecidíssimo com algo
    que eu já vi, e quase igualmente parecido com outra coisa". São dois fatos
    diferentes sobre o mesmo box, e a F44 registra como pergunta aberta se
    mostrar os dois separados ajuda ou confunde quem revisa.
    """
    if not box.char:
        return True
    if not box.source:
        return False          # não avaliado não é o mesmo que suspeito
    if box.margem >= 0.0:
        return box.margem < LIMIAR_DE_MARGEM
    return box.confidence < LIMIAR_ALTO


def rotulo(box) -> str:
    """Coluna curta de confiança para a lista lateral (4 caracteres)."""
    if not box.char:
        return "   -"
    if not box.source:
        return "   ?"
    return f"{box.confidence * 100:3.0f}%"
