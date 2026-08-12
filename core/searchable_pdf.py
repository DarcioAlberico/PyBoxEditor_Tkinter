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

from core import vertical
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
# notação, e exatamente as figurinas que o modelo aprendeu.
#
# Decidir se um ♘ reconhecido é peça branca ou preta é **visualmente
# impossível**: depende da paridade do número do lance. Isso é trabalho da
# F1.7 (validação com python-chess), não do reconhecimento de imagem.
PECAS = set(CHESS_UNICODE[:5])   # ♔♕♖♗♘


def tem_peca(char: str) -> bool:
    """
    A leitura deste box contém figurina? **Contém, não é.**

    A diferença passou a existir com as classes de ligadura da SPEC §5.2 item 6:
    o modelo emite `♗x`, porque numa captura de bispo o glifo e o `x` se tocam e
    `findContours` devolve os dois num box só. Com o teste antigo (`char in
    PECAS`) esse box não era peça, e o modo "replace" **pulava calado** justamente
    a captura de bispo — que não é caso raro em livro de xadrez.
    """
    return any(c in PECAS for c in char)


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


def _origem_do_texto(angulo: int, x1: float, y1: float,
                     x2: float, y2: float) -> fitz.Point:
    """
    Onde a linha de base começa, para cada ângulo (F8.1).

    O `rotate` do PyMuPDF usa a mesma convenção que o `angulo` do box, e isso
    foi conferido e não suposto: com `rotate=90` o texto extraído volta com
    direção (0,-1) — sobe na página —, e com 270 volta com (0,1). O que muda é
    o ponto de partida, porque o texto cresce a partir dele: a 90° ele sobe da
    base e o corpo da letra fica à esquerda; a 270° desce do topo, à direita.
    """
    if angulo % 360 == 90:
        return fitz.Point(x2, y2)
    if angulo % 360 == 270:
        return fitz.Point(x1, y1)
    return fitz.Point(x1, y2)


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


def _ler_boxes(img, boxes, reconhecer, ler_linha, conf_linha_maxima, resumo):
    """
    `(box, char, confiança)` para cada box, já com a leitura por linha aplicada.

    Sem `ler_linha` é o laço de antes: um box, uma chamada de `reconhecer`, na
    ordem em que os boxes vieram.

    Com ele, os boxes são agrupados em linhas e cada linha ganha uma segunda
    opinião — mas a troca só acontece nos boxes em que a cadeia ficou abaixo de
    `conf_linha_maxima`. O porquê do corte está em `gerar_pdf_pesquisavel`.
    """
    from core import leitura_de_linha as ldl

    def do_box(b):
        # De pé para classificar (F8.1): o modelo aprendeu glifo em pé, e o
        # mesmo recorte deitado desce de 94,2% para 8,4%.
        recorte = vertical.recorte_de_pe(img, b)
        if recorte.size == 0:
            return None
        char, conf = reconhecer(recorte)
        return (b, char, conf)

    if ler_linha is None:
        return [r for r in (do_box(b) for b in boxes) if r is not None]

    saida = []
    for linha in ldl.linhas_da_pagina(boxes):
        lidos = [r for r in (do_box(b) for b in linha) if r is not None]
        if not lidos:
            continue

        texto = ""
        if ldl.em_bloco([b for b, _c, _f in lidos]):
            faixa = ldl.faixa_da_linha(img, [b for b, _c, _f in lidos])
            if faixa is not None:
                texto = ler_linha(faixa)[0].replace(" ", "")

        if not texto:
            saida.extend(lidos)
            continue

        da_linha = ldl.distribuir([c for _b, c, _f in lidos], texto)
        for (b, char, conf), sugerido in zip(lidos, da_linha):
            if conf < conf_linha_maxima and sugerido and sugerido != char:
                resumo["corrigidos_pela_linha"] += 1
                saida.append((b, sugerido, conf))
            else:
                saida.append((b, char, conf))
    return saida


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
    ler_linha: Optional[Callable[[np.ndarray], Tuple[str, float]]] = None,
    conf_linha_maxima: float = 0.70,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """
    Escreve `output_pdf` a partir de `input_pdf`, preservando o original.

    reconhecer(crop) -> (char, confiança). Recebe o recorte em escala de cinza.

    modo:
      searchable — só a camada de texto invisível (padrão)
      replace    — desenha as peças de xadrez reconhecidas por cima do original
      both       — as duas coisas

    `ler_linha(faixa) -> (texto, confiança)` liga a leitura por linha da F17, e
    **só manda onde a cadeia está fraca** — abaixo de `conf_linha_maxima`.

    Essa restrição não é cautela, é o que a medição pede. Aqui o `reconhecer` é
    a cadeia inteira, e nela a rede responde 98,9% dos boxes com 97,6% de
    acerto: o EasyOCR, que é onde a F17 rende, é consultado em **0,7%**. Medido
    em 2.278 caracteres com a cadeia carregada:

        a linha manda quando        acerto
        nunca                       97,50%
        confiança < 0,70            97,54%
        confiança < 0,90            97,50%
        confiança < 0,99            97,32%
        sempre                      90,21%

    O melhor caso é **um caractere em 2.278**, e mandar sempre custa 7,3 pontos
    — seria trocar a rede a 97,6% pelo EasyOCR a 89,5%. Os 16,6 pontos da F17
    foram medidos contra o EasyOCR **sozinho**; aqui ele não é o leitor, é o
    último recurso. O corte de 0,70 é o melhor da tabela, e é o mesmo que a F14
    apontou como o melhor negócio da triagem por confiança.

    Sem `ler_linha` nada disso roda e o caminho é byte a byte o de antes.

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
        "corrigidos_pela_linha": 0,
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

            for b, char, conf in _ler_boxes(img, boxes, reconhecer, ler_linha,
                                            conf_linha_maxima, resumo):
                if not char or conf < conf_minima:
                    continue
                # Todos os caracteres, e não só `char[0]`: uma classe de
                # ligadura escreve dois glifos, e conferir o primeiro deixaria o
                # segundo virar retângulo vazio no PDF — o defeito do `·` da
                # SPEC §4.2, que aparece só quando o arquivo já está pronto.
                if not all(fonte.has_glyph(ord(c)) for c in char):
                    resumo["sem_glifo"] += 1
                    continue

                resumo["reconhecidos"] += 1
                if conf < 0.7:
                    resumo["baixa_confianca"] += 1

                x1, y1 = b.x1 * escala, b.y1 * escala
                x2, y2 = b.x2 * escala, b.y2 * escala
                angulo = getattr(b, "angulo", 0) % 360
                # Num box girado o texto corre na altura da caixa, e o corpo da
                # letra é que ocupa a largura.
                if angulo in (90, 270):
                    corpo = _corpo_que_preenche(fonte, char, y2 - y1, x2 - x1)
                else:
                    corpo = _corpo_que_preenche(fonte, char, x2 - x1, y2 - y1)
                origem = _origem_do_texto(angulo, x1, y1, x2, y2)

                if modo in ("searchable", "both"):
                    # render_mode=3 = invisível: o texto existe para busca e
                    # cópia, mas não aparece nem cobre o original. O texto
                    # girado entra girado: assim a seleção no leitor cai sobre
                    # o caractere certo e a ordem de cópia é a de leitura.
                    page.insert_text(
                        origem, char, fontname=FONTE_OCR, fontsize=corpo,
                        render_mode=3, rotate=angulo,
                    )

                if (modo in ("replace", "both")
                        and tem_peca(char) and conf >= conf_minima_pecas):
                    # Desenha na própria página, sem rasterizar: cobre o glifo
                    # original e escreve o símbolo Unicode por cima.
                    page.draw_rect(fitz.Rect(x1, y1, x2, y2),
                                   color=(1, 1, 1), fill=(1, 1, 1))
                    page.insert_text(
                        origem, char, fontname=FONTE_PECAS, fontsize=corpo,
                        rotate=angulo,
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
