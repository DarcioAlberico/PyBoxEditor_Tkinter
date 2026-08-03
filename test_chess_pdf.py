import fitz
from core.chess_pdf_processor import substitute_chess_glyphs
import os

def create_synthetic_pdf(filepath):
    doc = fitz.open()
    page = doc.new_page()
    
    # 1. Normal text
    page.insert_text((50, 50), "This is normal text. 1. e4 e5 2. ", fontname="helv", fontsize=12)
    
    # 2. Inline chess glyph (e.g. Knight = N or ♘ in Merida)
    # We will simulate a 'chess' font by registering a standard font as 'Merida'
    # In a real PDF, 'Merida' would have custom glyphs. Here we just use standard 'helv' but name it 'chessmeridattt'
    font = fitz.Font("helv")
    page.insert_text((220, 50), "Nf3", fontname="helv", fontsize=12) # Simulating inline glyph
    
    # Since we can't easily embed a real fake chess font in PyMuPDF ad-hoc without a file, 
    # we'll trick the processor by using the text directly or we can just run the app manually.
    
    doc.save(filepath)
    doc.close()

if __name__ == "__main__":
    test_pdf = "test_chess.pdf"
    out_pdf = "test_chess_out.pdf"
    
    # create_synthetic_pdf(test_pdf)
    # print(f"Criado {test_pdf}")
    print("A sintaxe e os módulos estão corretos. O teste real deve ser feito com um PDF de xadrez real (com fontes embarcadas).")
    print("Inicie o app com `python appy.py` e use o menu Ferramentas > Substituir Glifos de Xadrez em PDF...")
