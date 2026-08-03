import fitz  # PyMuPDF
import os
from typing import Tuple

# Keywords to detect chess fonts
CHESS_FONT_KEYWORDS = [
    "chess", "merida", "diagram", "figurine", "skak", "cburnett", "alpha", "leipzig"
]

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


def process_span(page: fitz.Page, span: dict, mapping_profile: dict, base_font: str = "helv"):
    """
    Substitutes chess glyphs in a single span with Unicode text.
    """
    font_name = span.get("font", "")
    if not is_chess_font(font_name):
        return  # Not a chess font, do nothing

    original_text = span.get("text", "")
    bbox = fitz.Rect(span["bbox"])
    
    # Map the text
    new_text = "".join(mapping_profile.get(char, char) for char in original_text)
    
    # 1. Erase the original text by drawing a white rectangle over the bounding box
    # We use white assuming white background. Ideally, we should detect background color,
    # but for most PDFs white is safe.
    page.draw_rect(bbox, color=(1, 1, 1), fill=(1, 1, 1))
    
    # 2. Insert the new Unicode text
    # We use a standard font that supports Unicode chess symbols (e.g., helv or a specific embedded font if added)
    # The font size might need tweaking since Unicode symbols can be wider/narrower than the glyphs.
    page.insert_textbox(
        rect=bbox,
        buffer=new_text,
        fontname=base_font,
        fontsize=span["size"],
        align=0  # Left align. 1 is center.
    )


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

    # Optional: Insert a Unicode-capable font if standard fonts fail.
    # For now, we rely on standard fallback (PyMuPDF's built-in fonts might not support all 
    # Unicode chess symbols on all systems, but we'll try 'helv' first, or try to insert a base one).

    for page_num, page in enumerate(doc):
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
                        process_span(page, span, mapping_profile, base_font="helv")
                        replaced_spans_count += 1

    try:
        doc.save(output_pdf)
        doc.close()
    except Exception as e:
        raise Exception(f"Erro ao salvar PDF: {e}")

    return total_pages, replaced_spans_count
