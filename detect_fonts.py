import fitz

def basic_text_check(pdf_path):
    doc = fitz.open(pdf_path)
    text = doc[10].get_text() # Try page 10
    print(f"Texto extraido (Pagina 10, {len(text)} caracteres):")
    print(text[:200])
    
    images = doc[10].get_images()
    print(f"Imagens na pagina 10: {len(images)}")
    
if __name__ == "__main__":
    pdf = r"C:/Users/WagnerEscorcio/Documents/Chessbase/PDF/01_Yusupov,_Artur_Build_up_Your_Chess_1_The_Fundamentals teste.pdf"
    basic_text_check(pdf)
