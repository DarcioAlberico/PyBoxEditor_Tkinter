import tkinter as tk
from typing import Tuple
from PIL import ImageTk, Image

from core.box_model import BoxEntry
from ui.confidence import cor_do_box, COR_LEXICO, COR_SELECAO

#: Marca do lado que é o topo do glifo num box de texto girado (F8.1).
COR_GIRADO = "#8E24AA"


class CanvasView(tk.Canvas):
    """
    Canvas responsável por:
      - desenhar imagem + boxes
      - zoom com roda do mouse
      - pan com botão direito
      - selecionar box (clique)
      - mover box (arrastar dentro)
      - redimensionar box (arrastar cantos)
      - criar box novo (arrastar em área vazia)
    """

    HANDLE_SIZE = 6  # tamanho dos quadradinhos de resize

    def __init__(self, parent, controller):
        super().__init__(parent, bg="white", highlightthickness=0)
        self.controller = controller

        self.tk_image = None
        self.zoom = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0

        # estado de drag
        self.drag_mode = None  # None | "move" | "resize" | "new"
        self.drag_box_index = -1
        self.drag_corner = None  # "tl","tr","bl","br"
        self.drag_start_img = (0.0, 0.0)
        self.drag_orig_box = None

        # seleção de novo box
        self.new_box_start = None  # (x_img, y_img)
        self.new_box_end = None

        # pan
        self._pan_start = None  # (x_canvas, y_canvas, offset_x, offset_y)

        # ids desenhados
        self.new_box_rect_id = None

        # binds
        self.bind("<MouseWheel>", self.on_wheel)
        self.bind("<ButtonPress-3>", self.on_pan_start)
        self.bind("<B3-Motion>", self.on_pan_move)
        self.bind("<ButtonRelease-3>", self.on_right_release)

        self.bind("<ButtonPress-1>", self.on_left_press)
        self.bind("<B1-Motion>", self.on_left_drag)
        self.bind("<ButtonRelease-1>", self.on_left_release)
        # Zoom sob comando explícito (F4.3). O duplo-clique já seleciona pelo
        # <ButtonPress-1>, então aqui só falta enquadrar.
        self.bind("<Double-Button-1>", self.on_double_click)

    # -------------------------------------------------------
    # Conversão de coordenadas
    # -------------------------------------------------------

    def img_to_canvas(self, x: float, y: float) -> Tuple[float, float]:
        return x * self.zoom + self.offset_x, y * self.zoom + self.offset_y

    def canvas_to_img(self, x: float, y: float) -> Tuple[float, float]:
        return (x - self.offset_x) / self.zoom, (y - self.offset_y) / self.zoom

    # -------------------------------------------------------
    # Zoom / Pan
    # -------------------------------------------------------

    def on_wheel(self, event):
        if self.controller.image is None:
            return

        old_zoom = self.zoom
        if event.delta > 0:
            self.zoom *= 1.1
        else:
            self.zoom /= 1.1

        self.zoom = max(0.3, min(8.0, self.zoom))

        # zoom focado no cursor
        cx, cy = event.x, event.y
        rx = (cx - self.offset_x) / old_zoom
        ry = (cy - self.offset_y) / old_zoom
        self.offset_x = cx - rx * self.zoom
        self.offset_y = cy - ry * self.zoom

        self.controller.update_canvas()

    def on_pan_start(self, event):
        self._pan_start = (event.x, event.y, self.offset_x, self.offset_y)

    def on_pan_move(self, event):
        if self._pan_start is None:
            return
        sx, sy, ox, oy = self._pan_start
        dx = event.x - sx
        dy = event.y - sy
        self.offset_x = ox + dx
        self.offset_y = oy + dy
        self.controller.update_canvas()

    def on_right_release(self, event):
        if self._pan_start is None or self.controller.image is None:
            return
            
        sx, sy, _, _ = self._pan_start
        dx = abs(event.x - sx)
        dy = abs(event.y - sy)
        
        # If we didn't drag much, treat it as a right-click to show context menu
        if dx < 5 and dy < 5:
            # Check if we clicked inside a box to select it first
            img_x, img_y = self.canvas_to_img(event.x, event.y)
            boxes = self.controller.boxes
            
            for i, b in enumerate(boxes):
                if b.x1 <= img_x <= b.x2 and b.y1 <= img_y <= b.y2:
                    self.controller.select_box(i)
                    break
                    
            if self.controller.selected_index >= 0 and hasattr(self.controller, 'context_menu'):
                self.controller.context_menu.tk_popup(event.x_root, event.y_root)
                
        self._pan_start = None

    # Folga, em pixels de tela, entre o box e a borda da view. Sem ela o box
    # encosta no canto e o vizinho seguinte já entra cortado.
    MARGEM_VISIVEL = 40

    def viewport(self) -> Tuple[int, int]:
        """
        Tamanho útil da view, com o mesmo recuo que o resto do arquivo usa.

        `winfo_width()` devolve 1 enquanto o Tk ainda não calculou a geometria —
        antes do primeiro `update_idletasks`, ou com a janela retraída. Cair num
        tamanho plausível evita dividir por um pixel; ser um método só garante
        que enquadrar e rolar concordem sobre onde é a borda.
        """
        vw, vh = self.winfo_width(), self.winfo_height()
        return (vw if vw > 1 else 800), (vh if vh > 1 else 600)

    def on_double_click(self, event):
        """Duplo-clique enquadra o box sob o cursor (F4.3)."""
        if self.controller.image is None:
            return
        if self.controller.selected_index >= 0:
            self.zoom_to_box(self.controller.selected_index)
        return "break"

    def garantir_visivel(self, index, margem=None):
        """
        Rola o **mínimo necessário** para o box aparecer. Não mexe no zoom.

        É o que a seleção usa desde a F4.3. Antes ela chamava `zoom_to_box` a
        cada troca de box, então navegar com as setas re-enquadrava a imagem a
        cada tecla e o contexto da linha se perdia — dava para ver o caractere e
        não dava para ver a palavra. Zoom agora só sob comando explícito (F4 ou
        duplo-clique).

        Se o box já está na área visível, nada acontece: rolar sem necessidade é
        o próprio defeito que esta função veio corrigir.
        """
        if self.controller.image is None:
            return

        boxes = self.controller.boxes
        if index < 0 or index >= len(boxes):
            return

        margem = self.MARGEM_VISIVEL if margem is None else margem
        b = boxes[index]

        vw, vh = self.viewport()

        x1 = b.x1 * self.zoom + self.offset_x
        x2 = b.x2 * self.zoom + self.offset_x
        y1 = b.y1 * self.zoom + self.offset_y
        y2 = b.y2 * self.zoom + self.offset_y

        def deslocamento(inicio, fim, tamanho):
            # Box maior que a janela: encostar numa borda deixaria a outra ponta
            # fora de qualquer jeito, então centraliza.
            if (fim - inicio) > (tamanho - 2 * margem):
                return (tamanho / 2) - ((inicio + fim) / 2)
            if inicio < margem:
                return margem - inicio
            if fim > tamanho - margem:
                return (tamanho - margem) - fim
            return 0.0

        dx = deslocamento(x1, x2, vw)
        dy = deslocamento(y1, y2, vh)

        if dx or dy:
            self.offset_x += dx
            self.offset_y += dy
            self.controller.update_canvas()

    def zoom_to_box(self, index):
        """
        Zoom e centraliza no box de índice 'index'.

        Desde a F4.3 só é chamada sob comando explícito — F4 ou duplo-clique —,
        não a cada seleção. Quem só precisa que o box apareça usa
        `garantir_visivel`.
        """
        if self.controller.image is None:
            return
        
        boxes = self.controller.boxes
        if index < 0 or index >= len(boxes):
            return

        b = boxes[index]
        x1, y1 = b.x1, b.y1
        x2, y2 = b.x2, b.y2
        
        bw = x2 - x1
        bh = y2 - y1
        
        # Evita divisão por zero
        if bw < 1: bw = 1
        if bh < 1: bh = 1

        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2

        # Dimensões da view atual
        vw, vh = self.viewport()

        # Margem de contexto: queremos ver o caractere e um pouco em volta
        # Fator de zoom ideal: view / (box * margin_factor)
        # Aumentei para 6.0 para dar mais foco
        # Mas limitamos o zoom max em 8.0 la no on_wheel, entao ok.
        margin = 10.0 # Mais zoom no box
        
        zoom_w = vw / (bw * margin)
        zoom_h = vh / (bh * margin)
        
        target_zoom = min(zoom_w, zoom_h)
        
        # Limites de zoom
        # Min 1.5 para garantir que nao fique muito longe
        target_zoom = max(1.5, min(12.0, target_zoom))
        
        self.zoom = target_zoom
        
        # Calcula offsets para centralizar (cx, cy)
        self.offset_x = (vw / 2) - (cx * self.zoom)
        self.offset_y = (vh / 2) - (cy * self.zoom)

        self.controller.update_canvas()

    # -------------------------------------------------------
    # Mouse esquerdo: selecionar / mover / redimensionar / novo
    # -------------------------------------------------------

    def on_left_press(self, event):
        if self.controller.image is None:
            return

        self.focus_set()
        img_x, img_y = self.canvas_to_img(event.x, event.y)
        boxes = self.controller.boxes

        # 1) teste nos cantos do box selecionado (resize)
        hit_idx, corner = self._hit_test_handles(event.x, event.y, boxes)
        if hit_idx is not None:
            self.drag_mode = "resize"
            self.drag_box_index = hit_idx
            self.drag_corner = corner
            self.drag_start_img = (img_x, img_y)
            self.drag_orig_box = boxes[hit_idx].copy()
            self.controller.select_box(hit_idx)
            return

        # 2) clique dentro de algum box → mover
        for i, b in enumerate(boxes):
            if b.x1 <= img_x <= b.x2 and b.y1 <= img_y <= b.y2:
                self.drag_mode = "move"
                self.drag_box_index = i
                self.drag_start_img = (img_x, img_y)
                self.drag_orig_box = boxes[i].copy()
                self.controller.select_box(i)
                return

        # 3) área vazia → novo box
        # (o snapshot para undo é feito em on_boxes_changed, após concluir a criação)
        self.drag_mode = "new"
        self.new_box_start = (img_x, img_y)
        self.new_box_end = (img_x, img_y)

    def on_left_drag(self, event):
        if self.controller.image is None or self.drag_mode is None:
            return

        img_x, img_y = self.canvas_to_img(event.x, event.y)
        boxes = self.controller.boxes

        # mover box
        if self.drag_mode == "move" and self.drag_orig_box is not None:
            ob = self.drag_orig_box
            dx = img_x - self.drag_start_img[0]
            dy = img_y - self.drag_start_img[1]

            b = boxes[self.drag_box_index]
            b.x1 = int(ob.x1 + dx)
            b.y1 = int(ob.y1 + dy)
            b.x2 = int(ob.x2 + dx)
            b.y2 = int(ob.y2 + dy)
            self.controller.update_canvas()

        # redimensionar box
        elif self.drag_mode == "resize" and self.drag_orig_box is not None:
            ob = self.drag_orig_box
            dx = img_x - self.drag_start_img[0]
            dy = img_y - self.drag_start_img[1]
            x1, y1, x2, y2 = ob.x1, ob.y1, ob.x2, ob.y2

            c = self.drag_corner
            if c in ("tl", "bl"):  # esquerda
                x1 = int(ob.x1 + dx)
            if c in ("tr", "br"):  # direita
                x2 = int(ob.x2 + dx)
            if c in ("tl", "tr"):  # topo
                y1 = int(ob.y1 + dy)
            if c in ("bl", "br"):  # base
                y2 = int(ob.y2 + dy)

            # normaliza
            x1, x2 = sorted((x1, x2))
            y1, y2 = sorted((y1, y2))

            # tamanho mínimo
            if x2 - x1 < 3:
                x2 = x1 + 3
            if y2 - y1 < 3:
                y2 = y1 + 3

            b = boxes[self.drag_box_index]
            b.x1, b.y1, b.x2, b.y2 = x1, y1, x2, y2
            self.controller.update_canvas()

        # novo box
        elif self.drag_mode == "new":
            self.new_box_end = (img_x, img_y)
            self._draw_new_box_preview()

    def on_left_release(self, event):
        if self.controller.image is None:
            return

        # finalizar novo box
        if self.drag_mode == "new" and self.new_box_start and self.new_box_end:
            x1, y1 = self.new_box_start
            x2, y2 = self.new_box_end
            x1, x2 = sorted((int(x1), int(x2)))
            y1, y2 = sorted((int(y1), int(y2)))

            if x2 - x1 > 3 and y2 - y1 > 3:
                self.controller.boxes.append(BoxEntry("", x1, y1, x2, y2))
                self.controller.select_box(len(self.controller.boxes) - 1)
                self.controller.on_boxes_changed()

        if self.new_box_rect_id is not None:
            self.delete(self.new_box_rect_id)
            self.new_box_rect_id = None

        if self.drag_mode in ("move", "resize"):
            self.controller.on_boxes_changed()

        self.drag_mode = None
        self.drag_box_index = -1
        self.drag_corner = None
        self.drag_orig_box = None
        self.new_box_start = None
        self.new_box_end = None

    # -------------------------------------------------------
    # Hit-test nos handles do box selecionado
    # -------------------------------------------------------

    def _hit_test_handles(self, cx: int, cy: int, boxes):
        sel = self.controller.selected_index
        if sel < 0 or sel >= len(boxes):
            return (None, None)

        b = boxes[sel]
        hs = self.HANDLE_SIZE

        corners = {
            "tl": self.img_to_canvas(b.x1, b.y1),
            "tr": self.img_to_canvas(b.x2, b.y1),
            "bl": self.img_to_canvas(b.x1, b.y2),
            "br": self.img_to_canvas(b.x2, b.y2),
        }

        for name, (px, py) in corners.items():
            if abs(cx - px) <= hs and abs(cy - py) <= hs:
                return (sel, name)

        return (None, None)

    # -------------------------------------------------------
    # Desenho
    # -------------------------------------------------------

    def redraw(self):
        self.delete("all")

        img = self.controller.image
        if img is None:
            return

        # Canvas dimensions
        vw = self.winfo_width()
        vh = self.winfo_height()
        if vw <= 1:
            vw = 800
        if vh <= 1:
            vh = 600

        # --- OTIMIZAÇÃO DE ZOOM (Viewport Rendering) ---
        # 1. Calcular a região visível da imagem
        #    Top-Left visível (0,0 no canvas) -> Imagem
        x1_img, y1_img = self.canvas_to_img(0, 0)
        #    Bottom-Right visível (vw, vh no canvas) -> Imagem
        x2_img, y2_img = self.canvas_to_img(vw, vh)

        # 2. Clampar (limitar) aos limites da imagem
        #    Adicionamos uma margem de segurança (1px) para evitar arredondamentos
        ix1 = max(0, int(x1_img))
        iy1 = max(0, int(y1_img))
        ix2 = min(img.width, int(x2_img) + 2)
        iy2 = min(img.height, int(y2_img) + 2)

        # 3. Se a região visível for inválida ou vazia, não desenha nada
        if ix2 <= ix1 or iy2 <= iy1:
            # Imagem fora da tela
            pass
        else:
            # 4. Crop apenas da parte visível
            try:
                crop = img.crop((ix1, iy1, ix2, iy2))

                # 5. Redimensionar para o tamanho de tela correto
                #    Largura na tela = (largura da crop) * zoom
                display_w = int((ix2 - ix1) * self.zoom)
                display_h = int((iy2 - iy1) * self.zoom)

                if display_w > 0 and display_h > 0:
                    # Usa NEAREST se o zoom for muito grande para performance e "pixel art" feel,
                    # ou BILINEAR/BICUBIC para suavidade.
                    # Vamos usar um padrão razoável:
                    resample_method = Image.NEAREST if self.zoom >= 4.0 else Image.BILINEAR
                    
                    resized = crop.resize((display_w, display_h), resample_method)
                    self.tk_image = ImageTk.PhotoImage(resized)

                    # 6. Posicionar no canvas
                    #    A posição de desenho é onde o pixel (ix1, iy1) da imagem cairia no canvas
                    pos_x, pos_y = self.img_to_canvas(ix1, iy1)
                    
                    self.create_image(pos_x, pos_y, anchor="nw", image=self.tk_image)
            except Exception as e:
                print(f"Erro no redraw otimizado: {e}")

        # --- Desenho dos Boxes ---
        # (Otimização opcional: filtrar boxes fora da tela.
        #  Mas desenhar retângulos no Tkinter é rápido, o gargalo era o resize da imagem inteira.)
        
        sel = self.controller.selected_index
        hs = self.HANDLE_SIZE

        # Fora do dicionário (F9). Vem pronto do controller, que guarda o
        # resultado em cache: recalcular aqui custaria 9,5 ms por redraw, e o
        # redraw acontece a cada seta.
        suspeitos = self.controller.boxes_suspeitos()

        for i, b in enumerate(self.controller.boxes):
            # Pequena otimização: não desenhar se estiver muito fora
            # Mas vamos manter simples para garantir que não suam.
            
            x1, y1 = self.img_to_canvas(b.x1, b.y1)
            x2, y2 = self.img_to_canvas(b.x2, b.y2)

            # A cor carrega a confiança do reconhecimento; a seleção é marcada
            # pela espessura e pelos handles amarelos, para não esconder o dado.
            color = cor_do_box(b)
            width = 3 if i == sel else 2

            self.create_rectangle(
                x1, y1, x2, y2, outline=color, width=width,
                dash=(3, 3) if not b.char else None,
            )

            # Fora do dicionário: sublinhado, como o de um corretor ortográfico —
            # e **por baixo do box, não no lugar da cor dele**. São dois eixos
            # independentes (SPEC §5.8, contrato 5): o contorno diz o que o
            # classificador achou do caractere, o traço diz o que o dicionário
            # achou da palavra, e o caso que só o léxico pega é justamente o box
            # verde de confiança 1,000.
            if i in suspeitos:
                self.create_line(x1, y2 + 2, x2, y2 + 2,
                                 fill=COR_LEXICO, width=2)

            # Texto girado (F8.1): um traço no lado que é o TOPO do glifo. Sem
            # isto o box de um rótulo vertical é indistinguível de um box
            # normal, e a leitura dele — que sai de baixo para cima — pareceria
            # embaralhada sem motivo.
            angulo = getattr(b, "angulo", 0) % 360
            if angulo in (90, 270):
                lado = x1 if angulo == 90 else x2
                self.create_line(lado, y1, lado, y2,
                                 fill=COR_GIRADO, width=3)

            # --- FEATURES EXTRAS DE SELECAO ---
            if i == sel:
                # 1. Handles de resize
                for (px, py) in [
                    (x1, y1),
                    (x2, y1),
                    (x1, y2),
                    (x2, y2),
                ]:
                    self.create_rectangle(
                        px - hs, py - hs, px + hs, py + hs,
                        outline="black", fill=COR_SELECAO
                    )
                
                # 2. Box de preview do caractere abaixo
                char_text = b.char
                if not char_text: char_text = "?"
                
                # Posicao: abaixo do box, centralizado horizontalmente
                # Tamanho fixo ou baseado no texto? Fixo eh mais limpo.
                preview_w = 40
                preview_h = 25
                
                cx = (x1 + x2) / 2
                py_start = y2 + 5 # 5px de margem abaixo do box
                
                px1 = cx - preview_w/2
                py1 = py_start
                px2 = cx + preview_w/2
                py2 = py_start + preview_h
                
                # Fundo amarelo claro
                self.create_rectangle(
                    px1, py1, px2, py2,
                    fill="#FFFFE0", outline="black"
                )
                
                # Texto
                self.create_text(
                    cx, (py1 + py2)/2,
                    text=char_text,
                    fill="black",
                    font=("Arial", 12, "bold")
                )

        # preview do novo box
        self._draw_new_box_preview()

    def _draw_new_box_preview(self):
        if self.new_box_rect_id is not None:
            self.delete(self.new_box_rect_id)
            self.new_box_rect_id = None

        if not (self.drag_mode == "new" and self.new_box_start and self.new_box_end):
            return

        x1, y1 = self.img_to_canvas(*self.new_box_start)
        x2, y2 = self.img_to_canvas(*self.new_box_end)
        self.new_box_rect_id = self.create_rectangle(
            x1, y1, x2, y2, outline="green", dash=(4, 2)
        )
