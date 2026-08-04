"""
Geração de PDF pesquisável a partir de páginas escaneadas.

Substitui `neural_pdf_processor.process_scanned_pdf`, que rasterizava o
documento: convertia cada página em imagem RGB, desenhava por cima e salvava
tudo como PDF de imagens. O resultado perdia todo o texto selecionável — até o
que já estava perfeito no original —, a busca parava de funcionar no arquivo
inteiro e o tamanho explodia. Para uma ferramenta de OCR, era a lacuna
estrutural mais séria do projeto.

Aqui a página original **nunca é rasterizada**. O reconhecimento entra como uma
camada de texto invisível (`render_mode=3`) posicionada sobre cada caractere: o
PDF fica visualmente idêntico e passa a ser pesquisável e copiável.
"""

import os
from typing import Callable, Optional, Tuple

import fitz
import numpy as np
from PIL import Image

from core.chess_pdf_processor import CHESS_UNICODE, resolve_chess_font
from core.services.box_service import BoxService


MODOS = ("searchable", "replace", "both")

FONTE_OCR = "pyboxocr"
FONTE_PECAS = "pyboxchess"

# Peças que o modo "replace" desenha por cima do original.
#
# São 5, não 12. Duas razões, ambas do domínio e verificadas no material real:
#
#   1. Peão não tem letra em notação algébrica — um lance de peão escreve-se
#      "e4", nunca com figurina. U+2659 e U+265F são inalcançáveis.
#   2. O livro usa UM conjunto de figurinas para os dois lados. Na linha real
#      "17...♞e5 18.♛c2 ♞a6 19.♞c4", o lance 17... é das pretas e o 19. das
#      brancas, e os dois cavalos usam o mesmo glifo. Os codepoints "pretos"
#      não existem como desenho próprio.
#
# Sobram exatamente K, Q, R, B, N — as únicas peças que ganham letra na
# notação, e exatamente as classes que o modelo aprendeu.
#
# Decidir se um ♘ reconhecido é peça branca ou preta é **visualmente
# impossível**: depende da paridade do número do lance. Isso é trabalho da
# F1.7 (validação com python-chess), não do reconhecimento de imagem.
PECAS = set(CHESS_UNICODE[:5])   # ♔♕♖♗♘


def _pagina_tem_texto(page: fitz.Page, minimo: int = 12) -> bool:
    """
    Heurística de página digital.

    Escrever a camada de OCR sobre uma página que já tem texto duplicaria o
    conteúdo: a busca passaria a devolver cada trecho duas vezes.
    """
    try:
        return len(page.get_text("text").strip()) >= minimo
    except Exception:
        return False


def _pagina_para_numpy(page: fitz.Page, dpi: int) -> np.ndarray:
    """Renderiza a página em escala de cinza, sem tocar no conteúdo dela."""
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def _corpo_que_preenche(font: fitz.Font, texto: str,
                        larg_alvo: float, alt_alvo: float) -> float:
    """
    Corpo de fonte que faz o texto ocupar a largura do box.

    Importa para o retângulo de seleção cair sobre o caractere certo quando o
    usuário arrasta o mouse no leitor de PDF.
    """
    corpo = max(alt_alvo, 1.0)
    larg = font.text_length(texto, fontsize=corpo)
    if larg > 0 and larg_alvo > 0:
        corpo *= larg_alvo / larg
    return max(1.0, min(corpo, alt_alvo * 3.0))


def gerar_pdf_pesquisavel(
    input_pdf: str,
    output_pdf: str,
    *,
    reconhecer: Callable[[np.ndarray], Tuple[str, float]],
    dpi: int = 300,
    modo: str = "searchable",
    conf_minima: float = 0.0,
    conf_minima_pecas: float = 0.6,
    pular_paginas_com_texto: bool = True,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """
    Escreve `output_pdf` a partir de `input_pdf`, preservando o original.

    reconhecer(crop) -> (char, confiança). Recebe o recorte em escala de cinza.

    modo:
      searchable — só a camada de texto invisível (padrão)
      replace    — desenha as peças de xadrez reconhecidas por cima do original
      both       — as duas coisas

    Devolve um resumo do que foi feito.
    """
    if modo not in MODOS:
        raise ValueError(f"modo inválido: {modo!r} (use um de {MODOS})")
    if not os.path.exists(input_pdf):
        raise FileNotFoundError(f"Arquivo não encontrado: {input_pdf}")

    fonte_path = resolve_chess_font()
    fonte = fitz.Font(fontfile=fonte_path)

    doc = fitz.open(input_pdf)
    escala = 72.0 / dpi

    resumo = {
        "paginas": len(doc),
        "paginas_ocr": 0,
        "paginas_puladas": 0,
        "boxes": 0,
        "reconhecidos": 0,
        "baixa_confianca": 0,
        "pecas_substituidas": 0,
        "sem_glifo": 0,
    }

    try:
        for numero, page in enumerate(doc):
            if progress_callback:
                progress_callback(numero, len(doc))

            if pular_paginas_com_texto and _pagina_tem_texto(page):
                resumo["paginas_puladas"] += 1
                continue

            img = _pagina_para_numpy(page, dpi)
            # `reconhecer` já é o classificador desta execução — é ele que
            # arbitra os cortes de glifo colado (F1.5b), sem custo de carregar
            # nada a mais.
            boxes = BoxService.generate_boxes_opencv(Image.fromarray(img),
                                                     arbitro=reconhecer)
            if not boxes:
                continue

            resumo["paginas_ocr"] += 1
            resumo["boxes"] += len(boxes)

            page.insert_font(fontname=FONTE_OCR, fontfile=fonte_path)
            if modo in ("replace", "both"):
                page.insert_font(fontname=FONTE_PECAS, fontfile=fonte_path)

            for b in boxes:
                recorte = img[b.y1:b.y2, b.x1:b.x2]
                if recorte.size == 0:
                    continue

                char, conf = reconhecer(recorte)
                if not char or conf < conf_minima:
                    continue
                if not fonte.has_glyph(ord(char[0])):
                    resumo["sem_glifo"] += 1
                    continue

                resumo["reconhecidos"] += 1
                if conf < 0.7:
                    resumo["baixa_confianca"] += 1

                x1, y1 = b.x1 * escala, b.y1 * escala
                x2, y2 = b.x2 * escala, b.y2 * escala
                corpo = _corpo_que_preenche(fonte, char, x2 - x1, y2 - y1)

                if modo in ("searchable", "both"):
                    # render_mode=3 = invisível: o texto existe para busca e
                    # cópia, mas não aparece nem cobre o original.
                    page.insert_text(
                        fitz.Point(x1, y2), char,
                        fontname=FONTE_OCR, fontsize=corpo, render_mode=3,
                    )

                if (modo in ("replace", "both")
                        and char in PECAS and conf >= conf_minima_pecas):
                    # Desenha na própria página, sem rasterizar: cobre o glifo
                    # original e escreve o símbolo Unicode por cima.
                    page.draw_rect(fitz.Rect(x1, y1, x2, y2),
                                   color=(1, 1, 1), fill=(1, 1, 1))
                    page.insert_text(
                        fitz.Point(x1, y2), char,
                        fontname=FONTE_PECAS, fontsize=corpo,
                    )
                    resumo["pecas_substituidas"] += 1

        if progress_callback:
            progress_callback(len(doc), len(doc))

        # A fonte de símbolos tem 2,3 MB e seria embutida inteira. Reduzi-la aos
        # glifos usados leva o PDF de 1342 KB para 70 KB num teste de 200
        # inserções — e num livro inteiro a diferença se repete por arquivo.
        try:
            doc.subset_fonts()
        except Exception:
            pass    # sem subset o arquivo fica grande, mas continua correto

        doc.save(output_pdf, garbage=3, deflate=True)
    finally:
        doc.close()

    return resumo
