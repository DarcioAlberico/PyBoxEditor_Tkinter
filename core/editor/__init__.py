"""O núcleo do editor de livros (ED-00 em diante): modelo, dialeto XHTML, CSS mínima.

Nada aqui importa Tkinter, PyMuPDF, numpy ou cv2 no topo — é o que deixa o
modelo testável sem display e o `appy.py --editor` abrir sem carregar o OCR
(SPEC_EDITOR DEC-07).
"""
