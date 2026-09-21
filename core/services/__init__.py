"""
Serviços de negócio para desacoplar a UI da lógica de OCR, ML e I/O.

Nenhum serviço é importado aqui no topo: `box_service`, `ocr_service` e
`pdf_service` trazem cv2, numpy e PyMuPDF, e um processo que só quer o
`TaskController` (o editor de livros, `appy.py --editor`, SPEC_EDITOR DEC-07)
pagava esses três só por importar `core.services.task_controller`. Os nomes do
pacote continuam existindo — carregados na primeira vez que alguém os pede.
"""

__all__ = [
    "BoxService",
    "OCRService",
    "preprocess_for_easyocr",
    "PDFService",
    "LearningService",
]

_ONDE = {
    "BoxService": ".box_service",
    "OCRService": ".ocr_service",
    "preprocess_for_easyocr": ".ocr_service",
    "PDFService": ".pdf_service",
    "LearningService": ".learning_service",
}


def __getattr__(name):
    """Carrega o serviço só quando ele for realmente utilizado."""
    modulo = _ONDE.get(name)
    if modulo is None:
        raise AttributeError(name)
    from importlib import import_module

    return getattr(import_module(modulo, __name__), name)
