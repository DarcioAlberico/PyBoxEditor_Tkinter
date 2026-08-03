import os
from typing import List, Tuple, Optional
from PIL import Image


class PDFService:
    """
    Serviço puro para carregamento e navegação de PDFs.
    """

    def __init__(self):
        self.pdf_bytes: Optional[bytes] = None
        self.pdf_path: Optional[str] = None
        self.num_pages: int = 0

    def load_pdf(self, path: str) -> Tuple[int, str]:
        """
        Carrega um PDF do disco.
        Retorna (num_pages, error_message). Se error_message for vazio, sucesso.
        """
        import pdf2image

        if not os.path.exists(path):
            return 0, f"Arquivo não encontrado: {path}"

        try:
            with open(path, "rb") as f:
                self.pdf_bytes = f.read()

            info = pdf2image.pdfinfo_from_bytes(self.pdf_bytes)
            self.num_pages = info["Pages"]
            self.pdf_path = path
            return self.num_pages, ""
        except Exception as e:
            self.pdf_bytes = None
            self.pdf_path = None
            self.num_pages = 0
            return 0, f"Erro ao abrir PDF:\n{e}\n\nVerifique se o Poppler está instalado."

    def load_page(self, page_index: int) -> Optional[Image.Image]:
        """
        Carrega uma página específica do PDF previamente carregado.
        Retorna PIL.Image em grayscale (mode 'L') ou None.
        """
        import pdf2image

        if self.pdf_bytes is None:
            return None

        try:
            pages = pdf2image.convert_from_bytes(
                self.pdf_bytes,
                first_page=page_index + 1,
                last_page=page_index + 1,
            )
            if not pages:
                return None
            return pages[0].convert("L")
        except Exception:
            return None

    def is_loaded(self) -> bool:
        return self.pdf_bytes is not None and self.num_pages > 0

    def close(self):
        self.pdf_bytes = None
        self.pdf_path = None
        self.num_pages = 0

    @staticmethod
    def convert_pdf_to_images(path: str, dpi: int = 200) -> List[Image.Image]:
        """
        Converte todo um PDF em uma lista de imagens PIL.
        Útil para processamento em lote.
        """
        import pdf2image

        with open(path, "rb") as f:
            pdf_bytes = f.read()
        return pdf2image.convert_from_bytes(pdf_bytes, dpi=dpi)
