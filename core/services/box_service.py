import cv2
import numpy as np
from typing import List, Tuple
from PIL import Image

from core.box_model import BoxEntry


class BoxService:
    """
    Serviço puro (sem UI) para geração, ordenação, merge e manipulação de boxes.
    """

    @staticmethod
    def generate_boxes_opencv(image: Image.Image, threshold: int = 180) -> List[BoxEntry]:
        """
        Gera boxes automaticamente a partir de uma imagem PIL (grayscale).
        """
        img_cv = np.array(image)
        _, th = cv2.threshold(img_cv, threshold, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        boxes = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if w < 2 or h < 2:
                continue
            boxes.append(BoxEntry("", x, y, x + w, y + h))

        boxes.sort(key=lambda b: (b.y1, b.x1))
        boxes = BoxService.merge_vertical_boxes(boxes)
        boxes = BoxService.sort_boxes_reading_order(boxes)
        return boxes

    @staticmethod
    def detectar_colunas(boxes: List[BoxEntry],
                         calha_minima: int = None) -> List[Tuple[int, int]]:
        """
        Faixas horizontais de coluna, em ordem de leitura.

        Projeta a ocupação dos boxes no eixo X e procura vãos verticais sem
        conteúdo nenhum. Usa os boxes, não os pixels: o vão que interessa é
        onde não há *caractere*, e assim funciona igual para página escaneada
        e para imagem já limpa.

        O limiar é relativo à largura mediana de caractere — uma calha de
        verdade é muito mais larga que o espaço entre palavras. Fixar a busca
        numa faixa central (como faz o DocuVision, 42%–58% da largura) só acha
        duas colunas simétricas; aqui a calha pode estar em qualquer posição, e
        podem ser mais de duas.
        """
        if not boxes:
            return []

        x_min = min(b.x1 for b in boxes)
        x_max = max(b.x2 for b in boxes)
        largura = x_max - x_min
        if largura <= 1:
            return [(x_min, x_max)]

        ocupado = np.zeros(largura + 2, dtype=bool)
        for b in boxes:
            ocupado[max(0, b.x1 - x_min):max(0, b.x2 - x_min) + 1] = True

        if calha_minima is None:
            larguras = sorted(b.x2 - b.x1 for b in boxes)
            mediana = larguras[len(larguras) // 2] or 1
            calha_minima = max(int(mediana * 3), int(largura * 0.02), 4)

        cortes = []
        inicio = None
        for i, cheio in enumerate(ocupado):
            if not cheio:
                if inicio is None:
                    inicio = i
            else:
                if inicio is not None and i - inicio >= calha_minima:
                    cortes.append((inicio, i))
                inicio = None

        if not cortes:
            return [(x_min, x_max)]

        faixas = []
        anterior = 0
        for ini, fim in cortes:
            if ini > anterior:
                faixas.append((x_min + anterior, x_min + ini - 1))
            anterior = fim
        if anterior <= largura:
            faixas.append((x_min + anterior, x_max))

        return [f for f in faixas if f[1] > f[0]] or [(x_min, x_max)]

    @staticmethod
    def _agrupar_em_linhas(boxes: List[BoxEntry]) -> List[BoxEntry]:
        """
        Ordena por linha de texto: agrupa por sobreposição vertical, linhas de
        cima para baixo, itens da esquerda para a direita dentro da linha.
        """
        if not boxes:
            return []

        boxes_sorted_y = sorted(boxes, key=lambda b: b.y1)

        lines = []
        current_line = []

        for b in boxes_sorted_y:
            y_center = (b.y1 + b.y2) / 2

            if not current_line:
                current_line.append(b)
            else:
                avg_bottom = sum(item.y2 for item in current_line) / len(current_line)
                if y_center <= avg_bottom + (b.y2 - b.y1) * 0.2:
                    current_line.append(b)
                else:
                    lines.append(current_line)
                    current_line = [b]

        if current_line:
            lines.append(current_line)

        final_boxes = []
        for line in lines:
            final_boxes.extend(sorted(line, key=lambda b: b.x1))

        return final_boxes

    @staticmethod
    def _por_colunas(boxes: List[BoxEntry],
                     colunas: List[Tuple[int, int]]) -> List[BoxEntry]:
        """Coluna a coluna; dentro de cada uma, linha a linha."""
        saida = []
        restantes = list(boxes)
        for x1, x2 in colunas:
            desta = [b for b in restantes if x1 <= (b.x1 + b.x2) / 2 <= x2]
            if desta:
                pegos = set(id(b) for b in desta)
                restantes = [b for b in restantes if id(b) not in pegos]
                saida.extend(BoxService._agrupar_em_linhas(desta))
        # o que não caiu em coluna nenhuma vai no fim, em ordem de linha
        saida.extend(BoxService._agrupar_em_linhas(restantes))
        return saida

    @staticmethod
    def sort_boxes_reading_order(boxes: List[BoxEntry]) -> List[BoxEntry]:
        """
        Ordena boxes como um humano leria.

        Antes, agrupava tudo por linha ignorando colunas: numa página de duas
        colunas o resultado intercalava as duas (linha 1 da esquerda, linha 1
        da direita, linha 2 da esquerda...), embaralhando o texto. Medido numa
        página real do Kasparov: 9 saltos entre colunas onde o correto é 1.

        Elementos que atravessam a calha — título, diagrama largo — não podem
        ser jogados numa coluna. Servem de separador horizontal: o que está
        acima deles é lido coluna a coluna, depois vem o elemento, depois o que
        está abaixo.
        """
        if not boxes:
            return []

        colunas = BoxService.detectar_colunas(boxes)
        if len(colunas) <= 1:
            return BoxService._agrupar_em_linhas(boxes)

        def bandas_cobertas(b):
            return sum(1 for x1, x2 in colunas if b.x1 <= x2 and b.x2 >= x1)

        transversais = sorted((b for b in boxes if bandas_cobertas(b) > 1),
                              key=lambda b: b.y1)
        ids_transversais = set(id(b) for b in transversais)
        restantes = [b for b in boxes if id(b) not in ids_transversais]

        if not transversais:
            return BoxService._por_colunas(restantes, colunas)

        saida = []
        for t in transversais:
            acima = [b for b in restantes if b.y2 <= t.y1]
            if acima:
                ids = set(id(b) for b in acima)
                restantes = [b for b in restantes if id(b) not in ids]
                saida.extend(BoxService._por_colunas(acima, colunas))
            saida.append(t)

        saida.extend(BoxService._por_colunas(restantes, colunas))
        return saida

    @staticmethod
    def merge_vertical_boxes(boxes: List[BoxEntry]) -> List[BoxEntry]:
        """
        Mescla boxes verticalmente alinhados e próximos (ex: pingo do 'i', ':', ';').
        """
        if not boxes:
            return []

        heights = [b.y2 - b.y1 for b in boxes]
        if not heights:
            return boxes

        median_h = sorted(heights)[len(heights) // 2]
        if median_h < 10:
            median_h = 10

        SHORT_THRESH = median_h * 0.6
        DEFAULT_MAX_VERT = max(10, min(30, median_h * 0.8))
        MIN_HORIZ_OVERLAP_RATIO = 0.3

        merged_boxes = []
        used_indices = set()

        for i in range(len(boxes)):
            if i in used_indices:
                continue

            b1 = boxes[i]
            current_merged = BoxEntry(
                b1.char, b1.x1, b1.y1, b1.x2, b1.y2
            )
            used_indices.add(i)

            merged_something = True
            while merged_something:
                merged_something = False

                for j in range(i + 1, len(boxes)):
                    if j in used_indices:
                        continue

                    b2 = boxes[j]
                    dist_vert = b2.y1 - current_merged.y2

                    h1 = current_merged.y2 - current_merged.y1
                    h2 = b2.y2 - b2.y1

                    is_tall_1 = h1 > SHORT_THRESH
                    is_tall_2 = h2 > SHORT_THRESH

                    if is_tall_1 and is_tall_2:
                        max_vert_dist = 2
                    else:
                        max_vert_dist = DEFAULT_MAX_VERT

                    if dist_vert > max_vert_dist:
                        continue

                    ox1 = max(current_merged.x1, b2.x1)
                    ox2 = min(current_merged.x2, b2.x2)
                    overlap = max(0, ox2 - ox1)

                    width1 = current_merged.x2 - current_merged.x1
                    width2 = b2.x2 - b2.x1
                    min_width = min(width1, width2)

                    if min_width <= 0:
                        continue

                    if (overlap / min_width) > MIN_HORIZ_OVERLAP_RATIO:
                        new_x1 = min(current_merged.x1, b2.x1)
                        new_y1 = min(current_merged.y1, b2.y1)
                        new_x2 = max(current_merged.x2, b2.x2)
                        new_y2 = max(current_merged.y2, b2.y2)

                        current_merged.x1 = new_x1
                        current_merged.y1 = new_y1
                        current_merged.x2 = new_x2
                        current_merged.y2 = new_y2

                        used_indices.add(j)
                        merged_something = True
                        break

            merged_boxes.append(current_merged)

        return merged_boxes

    @staticmethod
    def split_box(box: BoxEntry) -> List[BoxEntry]:
        """
        Divide um box ao meio. Se for mais largo que alto, divide em X.
        Caso contrário, divide em Y. Retorna 2 boxes com char vazio.
        """
        x1, y1, x2, y2 = box.x1, box.y1, box.x2, box.y2

        if (x2 - x1) > (y2 - y1):
            mx = (x1 + x2) // 2
            return [
                BoxEntry("", x1, y1, mx, y2),
                BoxEntry("", mx, y1, x2, y2),
            ]
        else:
            my = (y1 + y2) // 2
            return [
                BoxEntry("", x1, y1, x2, my),
                BoxEntry("", x1, my, x2, y2),
            ]

    @staticmethod
    def clamp_box(box: BoxEntry, max_w: int, max_h: int) -> BoxEntry:
        """Garante que as coordenadas do box fiquem dentro dos limites da imagem."""
        return BoxEntry(
            char=box.char,
            x1=max(0, box.x1),
            y1=max(0, box.y1),
            x2=min(max_w, box.x2),
            y2=min(max_h, box.y2),
        )
