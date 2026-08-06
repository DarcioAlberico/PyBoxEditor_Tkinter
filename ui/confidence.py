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


def precisa_revisao(box) -> bool:
    """Verdadeiro para o que o revisor deveria olhar: vazio ou confiança baixa."""
    if not box.char:
        return True
    if not box.source:
        return False          # não avaliado não é o mesmo que suspeito
    return box.confidence < LIMIAR_ALTO


def rotulo(box) -> str:
    """Coluna curta de confiança para a lista lateral (4 caracteres)."""
    if not box.char:
        return "   -"
    if not box.source:
        return "   ?"
    return f"{box.confidence * 100:3.0f}%"
