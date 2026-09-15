"""Serviços de negócio para desacoplar a UI da lógica de OCR, ML e I/O."""
from .box_service import BoxService
from .ocr_service import OCRService, preprocess_for_easyocr
from .pdf_service import PDFService

__all__ = [
    "BoxService",
    "OCRService",
    "preprocess_for_easyocr",
    "PDFService",
    "LearningService",
]


def __getattr__(name):
    """Carrega o serviço de ML somente quando ele for realmente utilizado."""
    if name == "LearningService":
        from .learning_service import LearningService

        return LearningService
    raise AttributeError(name)
