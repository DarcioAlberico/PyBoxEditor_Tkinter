import fitz  # PyMuPDF
import os
from typing import Tuple

# Keywords to detect chess fonts
CHESS_FONT_KEYWORDS = [
    "chess", "merida", "diagram", "figurine", "skak", "cburnett", "alpha", "leipzig"
]

# Os 12 símbolos Unicode de peças (U+2654..U+265F).
CHESS_UNICODE = "\u2654\u2655\u2656\u2657\u2658\u2659\u265A\u265B\u265C\u265D\u265E\u265F"

# Fontes candidatas, em ordem de preferência.
# ATENÇÃO: a maioria das fontes comuns NÃO tem estes glifos. Verificado neste
# sistema: Arial, Segoe UI, Times e Calibri falham nas 12 peças; apenas
# Segoe UI Symbol e MS Gothic cobrem. Por isso resolve_chess_font() valida a
# cobertura de verdade em vez de só checar se o arquivo existe.
CHESS_FONT_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "assets", "fonts", "DejaVuSans.ttf"),   # empacotada (preferencial)
    r"C:\Windows\Fonts\seguisym.ttf",                    # Segoe UI Symbol
    r"C:\Windows\Fonts\msgothic.ttc",                    # MS Gothic
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


class ChessFontError(RuntimeError):
    """Nenhuma fonte disponível consegue desenhar as peças de xadrez."""


def missing_glyphs(font_path: str, chars: str = CHESS_UNICODE) -> list:
    """Retorna os caracteres que a fonte NÃO consegue desenhar."""
    font = fitz.Font(fontfile=font_path)
    # has_glyph devolve o id do glifo; 0 significa ausente.
    return [c for c in chars if not font.has_glyph(ord(c))]


def resolve_chess_font(chars: str = CHESS_UNICODE) -> str:
    """
    Primeira fonte candidata que cobre TODOS os caracteres pedidos.

    Levanta ChessFontError se nenhuma servir. Falhar alto aqui é proposital:
    a alternativa é o PyMuPDF trocar cada peça por '·' sem avisar, e o usuário
    só descobrir ao abrir o PDF já convertido.
    """
    tentativas = []
    for path in CHESS_FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            falta = missing_glyphs(path, chars)
        except Exception as e:
            tentativas.append(f"  {path}: erro ao ler ({e})")
            continue
        if not falta:
            return path
        tentativas.append(f"  {path}: não cobre {''.join(falta)}")

    detalhe = "\n".join(tentativas) if tentativas else "  (nenhuma candidata encontrada no disco)"
    raise ChessFontError(
        "Nenhuma fonte disponível desenha os símbolos de xadrez.\n"
        f"Fontes testadas:\n{detalhe}\n\n"
        "Solução: coloque DejaVuSans.ttf em assets/fonts/ "
        "(https://dejavu-fonts.github.io/)."
    )

# Default profile for mapping chess pseudo-ASCII to Unicode
# This is a generic fallback that attempts to cover the most common mappings.
DEFAULT_MAPPING_PROFILE = {
    # Merida / standard
    "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
    "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
    " ": " ", ".": "·", "-": " ",
    # Sometimes they use A-F or other mappings, we can expand this profile if needed.
}


def is_chess_font(font_name: str) -> bool:
    """Check if the font name contains typical chess font keywords."""
    font_lower = font_name.lower()
    return any(kw in font_lower for kw in CHESS_FONT_KEYWORDS)


def is_diagram_span(span: dict) -> bool:
    """
    Check if a span is likely part of a diagram.
    For inline substitution, we want to IGNORE these spans.
    A diagram span usually has:
    - Only a few characters but it's part of a very dense block, OR
    - It's very wide/tall, OR
    - It contains repetitive structures (though this is harder to check on a single span level).
    
    A simpler heuristic contextually:
     diagrams usually consist of many lines of chess fonts in a single block.
    """
    # This function is a placeholder; diagram detection is better done at the block level.
    # We will implement diagram detection at the block level in the main function.
    return False


def is_block_a_diagram(block: dict) -> bool:
    """
    Detect if a text block is likely a chess diagram (8x8 grid).
    Heuristic: A diagram is usually a block with multiple lines (often ~8 or more)
    where almost all text uses a chess font.
    """
    if "lines" not in block:
        return False
        
    line_count = len(block["lines"])
    if line_count < 4:  # Too few lines to be a full diagram
        return False
        
    chess_span_count = 0
    total_span_count = 0
    
    for line in block["lines"]:
        for span in line["spans"]:
            total_span_count += 1
            if is_chess_font(span["font"]):
                chess_span_count += 1
                
    # If a high percentage of spans in this large block are chess fonts, it's a diagram.
    return total_span_count > 0 and (chess_span_count / total_span_count) > 0.7


def process_span(page: fitz.Page, span: dict, mapping_profile: dict,
                 fontname: str, font: fitz.Font) -> bool:
    """
    Substitui os glifos de xadrez de um span por texto Unicode.

    'fontname' é o alias já registrado na página via page.insert_font(), e 'font'
    o objeto fitz.Font correspondente (usado para medir a largura do texto).
    Retorna True se algo foi escrito.
    """
    font_name = span.get("font", "")
    if not is_chess_font(font_name):
        return False  # Not a chess font, do nothing

    original_text = span.get("text", "")
    if not original_text:
        return False

    bbox = fitz.Rect(span["bbox"])

    # Map the text
    new_text = "".join(mapping_profile.get(char, char) for char in original_text)

    # 1. Erase the original text by drawing a white rectangle over the bounding box
    # We use white assuming white background. Ideally, we should detect background color,
    # but for most PDFs white is safe.
    page.draw_rect(bbox, color=(1, 1, 1), fill=(1, 1, 1))

    # 2. Ajustar o corpo da fonte para caber na largura original.
    #    Os símbolos Unicode costumam ser mais largos que os glifos da fonte de
    #    xadrez, e estourar o bbox empurraria a notação por cima do texto vizinho.
    size = span["size"]
    largura_alvo = bbox.width
    if largura_alvo > 0:
        limite = size * 0.6  # abaixo disso a leitura sofre; melhor deixar estourar
        while size > limite and font.text_length(new_text, fontsize=size) > largura_alvo:
            size -= 0.5

    # 3. Escrever na baseline do span original.
    #    insert_text (e não insert_textbox): o textbox reflui o conteúdo dentro do
    #    retângulo e desloca a notação inline; para um trecho curto como "♘f3" o
    #    que importa é manter o alinhamento com a linha de texto.
    origin = span.get("origin") or (bbox.x0, bbox.y1)

    page.insert_text(
        fitz.Point(origin),
        new_text,
        fontname=fontname,
        fontsize=size,
    )
    return True


def substitute_chess_glyphs(input_pdf: str, output_pdf: str, mapping_profile: dict = None, progress_callback=None) -> Tuple[int, int]:
    """
    Reads a PDF, finds inline chess glyphs, replaces them with Unicode, and saves the new PDF.
    Ignores 8x8 chess diagrams.
    
    Returns:
        tuple: (total_pages, replaced_spans_count)
    """
    if not os.path.exists(input_pdf):
        raise FileNotFoundError(f"Arquivo não encontrado: {input_pdf}")

    if mapping_profile is None:
        mapping_profile = DEFAULT_MAPPING_PROFILE

    try:
        doc = fitz.open(input_pdf)
    except Exception as e:
        raise Exception(f"Erro ao abrir PDF: {e}")

    total_pages = len(doc)
    replaced_spans_count = 0

    # Resolver a fonte ANTES de tocar no documento: se nenhuma fonte do sistema
    # desenhar as peças, é melhor abortar do que gerar um PDF com '·' no lugar
    # de cada símbolo. resolve_chess_font() levanta ChessFontError nesse caso.
    font_path = resolve_chess_font()
    font_obj = fitz.Font(fontfile=font_path)
    FONT_ALIAS = "chessuni"

    for page_num, page in enumerate(doc):
        # O alias precisa ser registrado em cada página que for usá-lo.
        page.insert_font(fontname=FONT_ALIAS, fontfile=font_path)

        # Notify progress
        if progress_callback:
            progress_callback(page_num, total_pages)

        # Extract text blocks with detailed layout info
        text_page = page.get_text("dict")
        if "blocks" not in text_page:
            continue

        blocks = text_page["blocks"]

        for block in blocks:
            # Skip image blocks
            if block.get("type", 0) != 0:
                continue
                
            # Nível 1: Filter out diagrams
            if is_block_a_diagram(block):
                continue
                
            # Nível 2: Process inline text
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if is_chess_font(span["font"]):
                        if process_span(page, span, mapping_profile,
                                        FONT_ALIAS, font_obj):
                            replaced_spans_count += 1

    try:
        doc.save(output_pdf)
        doc.close()
    except Exception as e:
        raise Exception(f"Erro ao salvar PDF: {e}")

    return total_pages, replaced_spans_count
