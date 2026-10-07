"""
A paleta e os estilos da janela principal e dos diálogos dela, num lugar só.

É o item 9 da `docs/REVISAO_MODOS_OCR.md`. As cores estavam soltas em nove
arquivos, e o mesmo papel tinha tons diferentes: o texto de erro era `#B71C1C`
na caixa de exportação, `#b00020` na revisão editorial e `#9b2226` na
rotulagem; o verde de "pronto", três tons em três diálogos. Aqui cada cor tem
um nome que diz **para que serve**, e quem desenha pede pelo nome.

As cores do reconhecimento — a escala de confiança, o léxico, a seleção — são
contrato: a tela, a lista e os testes as usam pelos nomes de `ui.confidence`,
que apontam para cá com os mesmos valores. O editor de livros (`ui/editor/`)
tem a folha dele e fica de fora.

Os estilos ttk com nome (`Erro.TLabel`, `Alerta.TLabel`, `Ok.TLabel`,
`Andamento.TLabel`, `Secundario.TLabel`) são configurados por `aplicar`, que
é idempotente: o `appy.main` chama ao abrir, e cada diálogo que os usa chama ao
nascer — um diálogo aberto num teste, sem o `appy`, sai com as mesmas cores.
"""

from tkinter import ttk

# ----------------------------------------------------------------------
# O reconhecimento (ui.confidence, ui.canvas_view)
# ----------------------------------------------------------------------

CONFIANCA_ALTA = "#2E9B4F"       # verde
CONFIANCA_MEDIA = "#FB8C00"      # laranja
CONFIANCA_BAIXA = "#E53935"      # vermelho
SEM_CARACTERE = "#9E9E9E"        # cinza — o box vazio
SEM_AVALIACAO = "#3F7FBF"        # azul — lido de um .box, sem confiança
SELECAO = "#FFD400"              # amarelo — a seleção e o modo digitação
FORA_DO_DICIONARIO = "#8E24AA"   # roxo — o sublinhado do léxico (F9)
TOPO_DO_GIRADO = "#8E24AA"       # roxo — o lado que é o topo do glifo girado (F8.1)

# ----------------------------------------------------------------------
# Texto que diz um estado
# ----------------------------------------------------------------------

TEXTO_ERRO = "#B71C1C"           # o que falhou ou barra a ação
TEXTO_ALERTA = "#8A5A00"         # o que pede atenção, sem barrar
TEXTO_OK = "#2E7D32"             # o que está pronto
TEXTO_ANDAMENTO = "#1769AA"      # o que está acontecendo agora
TEXTO_SECUNDARIO = "#4D4D4D"     # a explicação ao lado do controle

# ----------------------------------------------------------------------
# Fundos e bordas
# ----------------------------------------------------------------------

FUNDO_DO_RECORTE = "#202124"     # a pré-visualização da linha recortada
FUNDO_DA_ETIQUETA = "#FFFFE0"    # a etiqueta do caractere sob o box selecionado
FUNDO_MARCADO = "#E8F5E9"        # a miniatura que entra no lote
BORDA_DESMARCADA = "#BDBDBD"     # a miniatura que ficou de fora

# ----------------------------------------------------------------------
# O tabuleiro do diálogo 8×8 (ui.dialogo_diagrama)
# ----------------------------------------------------------------------

CASA_ARBITRADA = CONFIANCA_BAIXA   # a legalidade mexeu nesta casa
CASA_EM_DUVIDA = CONFIANCA_MEDIA
CASA_CORRIGIDA = TEXTO_OK          # a mão do usuário mexeu nesta casa (F8.2)
CASA_SELECIONADA = "#1E88E5"

#: Os estilos ttk que `aplicar` define, e a cor de cada um.
ESTILOS_DE_TEXTO = {
    "Erro.TLabel": TEXTO_ERRO,
    "Alerta.TLabel": TEXTO_ALERTA,
    "Ok.TLabel": TEXTO_OK,
    "Andamento.TLabel": TEXTO_ANDAMENTO,
    "Secundario.TLabel": TEXTO_SECUNDARIO,
}


def aplicar(widget) -> ttk.Style:
    """Os estilos ttk com nome, no interpretador de `widget` (idempotente)."""
    estilo = ttk.Style(widget)
    for nome, cor in ESTILOS_DE_TEXTO.items():
        estilo.configure(nome, foreground=cor)
    return estilo
