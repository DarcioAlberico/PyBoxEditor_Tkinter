import datetime
import json
import os
import queue
import threading
from typing import Dict, List, Optional, Set

from core.box_model import BoxEntry


SIDECAR_SUFIXO = ".pyboxsession.json"
SCHEMA = 1

#: Em que dpi um rascunho **sem** o campo `dpi` foi gravado.
#:
#: O sidecar guarda coordenadas em pixels da renderização, e até a mudança de
#: `DPI_PADRAO` para 300 existiu um único valor possível: 200. Rascunho antigo
#: não diz em que escala está justamente porque não havia escolha, e assumir
#: 200 é o que reposiciona os boxes dele no lugar certo. Sem isto a mudança de
#: dpi devolveria todo rascunho anterior com os boxes a dois terços da posição,
#: em silêncio — e o autosave é restaurado sem o usuário escolher nada.
DPI_LEGADO = 200


def caminho_sidecar(documento: str) -> str:
    """Arquivo de rascunho ao lado do documento."""
    return os.path.splitext(documento)[0] + SIDECAR_SUFIXO


class _GravadorAssincrono:
    """
    Grava o rascunho numa thread própria, fora do BackgroundTask.

    Autosave não é uma operação do usuário: não tem progresso, não é cancelável
    e não pode disputar a vaga única de tarefa em primeiro plano com o OCR ou
    com o carregamento de página.

    A fila tem tamanho 1 e o pedido novo descarta o antigo — só interessa o
    estado mais recente. A escrita é atômica (arquivo temporário + os.replace):
    travar no meio de um autosave não pode deixar um rascunho corrompido, que
    é justamente o cenário para o qual ele existe.
    """

    def __init__(self):
        self._fila = queue.Queue(maxsize=1)
        self._thread = None
        self._erro = None

    def agendar(self, caminho: str, payload: dict):
        try:
            self._fila.put_nowait((caminho, payload))
        except queue.Full:
            try:
                self._fila.get_nowait()          # descarta o desatualizado
            except queue.Empty:
                pass
            try:
                self._fila.put_nowait((caminho, payload))
            except queue.Full:
                return

        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._rodar, daemon=True)
            self._thread.start()

    def _rodar(self):
        while True:
            try:
                caminho, payload = self._fila.get(timeout=0.5)
            except queue.Empty:
                return
            try:
                tmp = caminho + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False)
                os.replace(tmp, caminho)
                self._erro = None
            except Exception as e:      # noqa: BLE001 — consultado pela UI
                self._erro = e

    @property
    def ultimo_erro(self):
        return self._erro


class DocumentSession:
    """
    Um documento aberto — imagem única ou PDF de N páginas.

    Existe para resolver uma perda silenciosa de trabalho: antes, virar a página
    do PDF fazia `self.boxes = []` sem aviso, e tudo que havia sido digitado na
    página anterior simplesmente sumia.

    A sessão guarda os boxes de todas as páginas visitadas e registra quais têm
    alterações ainda não gravadas em disco.

    Nota sobre referências: `boxes_for()` devolve a própria lista guardada, e
    `store()` guarda a lista recebida sem copiar. Isso é proposital — a
    MainWindow muta `self.boxes` no lugar o tempo todo, e copiar a cada tecla
    numa página de 2.000 caracteres seria caro. O contrato é que todo ponto que
    reatribui `self.boxes` chame `store()` em seguida.
    """

    def __init__(self, path: str, num_pages: int = 1, is_pdf: bool = False,
                 dpi: int = 0):
        self.path = path
        self.num_pages = max(1, num_pages)
        self.is_pdf = is_pdf
        # Em que escala estão as coordenadas desta sessão. A sessão não escolhe
        # o dpi — quem renderiza escolhe —, ela só registra qual foi, para o
        # rascunho poder ser relido depois que esse valor mudar. Zero quer dizer
        # "não informado", e aí nada é reescalado.
        self.dpi = int(dpi or 0)

        self._pages: Dict[int, List[BoxEntry]] = {}
        self._dirty: Set[int] = set()

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    def boxes_for(self, page: int) -> List[BoxEntry]:
        """Boxes da página (lista vazia própria, se ainda não visitada)."""
        return self._pages.setdefault(page, [])

    def has_boxes(self, page: int) -> bool:
        return bool(self._pages.get(page))

    def pages_with_boxes(self) -> List[int]:
        return sorted(p for p, boxes in self._pages.items() if boxes)

    def dirty_pages(self) -> List[int]:
        """Páginas com alterações não salvas (e que ainda têm algo a salvar)."""
        return sorted(p for p in self._dirty if self._pages.get(p))

    def is_dirty(self) -> bool:
        return bool(self.dirty_pages())

    def total_boxes(self) -> int:
        return sum(len(b) for b in self._pages.values())

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------

    def store(self, page: int, boxes: List[BoxEntry]) -> None:
        """Associa a lista de boxes à página. Não mexe no estado 'sujo'."""
        self._pages[page] = boxes

    def mark_dirty(self, page: int) -> None:
        self._dirty.add(page)

    def mark_saved(self, page: Optional[int] = None) -> None:
        """Marca uma página como gravada — ou todas, se page for None."""
        if page is None:
            self._dirty.clear()
        else:
            self._dirty.discard(page)

    # ------------------------------------------------------------------
    # Nomes de arquivo
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Rascunho automático (autosave)
    # ------------------------------------------------------------------

    def sidecar(self) -> str:
        return caminho_sidecar(self.path)

    def montar_payload(self) -> dict:
        """
        Snapshot serializável do estado. Roda na thread da UI, porque precisa
        de uma visão consistente dos boxes.

        Guarda cada box como tupla, não como dict: medido em 40 mil boxes, a
        conversão cai de 98 ms para 23 ms e o arquivo de 3,9 MB para 1,7 MB.
        O `.box` do Tesseract não tem onde guardar confiança e origem; aqui
        tem, então o rascunho preserva o que a F3.2 calculou.
        """
        paginas = {}
        for pagina, boxes in self._pages.items():
            if boxes:
                paginas[str(pagina)] = [
                    (b.char, b.x1, b.y1, b.x2, b.y2, round(b.confidence, 4),
                     b.source, getattr(b, "angulo", 0))
                    for b in boxes
                ]
        return {
            "schema": SCHEMA,
            "documento": os.path.basename(self.path),
            "gravado_em": datetime.datetime.now().isoformat(timespec="seconds"),
            "is_pdf": self.is_pdf,
            "num_pages": self.num_pages,
            # A escala em que estas coordenadas foram feitas. Campo novo, e o
            # `schema` continua 1 de propósito: subi-lo faria `ler_autosave`
            # recusar todo rascunho anterior, que é a perda de trabalho que o
            # autosave existe para evitar. O ausente é tratado por `DPI_LEGADO`.
            "dpi": self.dpi,
            "sujas": self.dirty_pages(),
            "paginas": paginas,
        }

    def autosave(self, gravador: _GravadorAssincrono) -> Optional[str]:
        """Agenda a gravação do rascunho. Devolve o caminho, ou None se não há
        o que gravar."""
        if not self.pages_with_boxes():
            return None
        destino = self.sidecar()
        gravador.agendar(destino, self.montar_payload())
        return destino

    def remover_autosave(self):
        """Apaga o rascunho. Chamado quando o trabalho foi gravado de verdade,
        ou quando o usuário decidiu descartá-lo."""
        try:
            os.remove(self.sidecar())
        except OSError:
            pass

    def fator_de_escala(self, payload: dict) -> float:
        """
        Quanto reescalar as coordenadas de um rascunho gravado noutro dpi.

        Devolve 1.0 quando não há o que fazer — sessão sem dpi informado, ou
        rascunho da mesma escala.
        """
        if not self.dpi:
            return 1.0
        try:
            gravado = int(payload.get("dpi") or DPI_LEGADO)
        except (TypeError, ValueError):
            gravado = DPI_LEGADO
        if gravado <= 0 or gravado == self.dpi:
            return 1.0
        return self.dpi / gravado

    def aplicar_payload(self, payload: dict) -> int:
        """Restaura páginas e marcações a partir de um rascunho. Devolve
        quantas páginas foram recuperadas.

        **Reescala se o rascunho é de outro dpi.** As coordenadas são pixels da
        renderização, e o `DPI_PADRAO` mudou de 200 para 300: sem isto o
        trabalho de antes voltaria com cada box a dois terços da posição.
        """
        f = self.fator_de_escala(payload)
        paginas = payload.get("paginas", {}) or {}
        for chave, itens in paginas.items():
            try:
                indice = int(chave)
            except (TypeError, ValueError):
                continue
            boxes = []
            for it in itens:
                try:
                    char, x1, y1, x2, y2 = it[0], int(it[1]), int(it[2]), int(it[3]), int(it[4])
                    conf = float(it[5]) if len(it) > 5 else 0.0
                    origem = it[6] if len(it) > 6 else ""
                    # Rascunho gravado antes da F8.1 não tem o oitavo campo, e
                    # a ausência dele quer dizer exatamente ângulo zero.
                    angulo = int(it[7]) if len(it) > 7 else 0
                except (TypeError, ValueError, IndexError):
                    continue
                if f != 1.0:
                    x1, y1 = int(round(x1 * f)), int(round(y1 * f))
                    x2, y2 = int(round(x2 * f)), int(round(y2 * f))
                boxes.append(BoxEntry(char, x1, y1, x2, y2,
                                      confidence=conf, source=origem or "",
                                      angulo=angulo if angulo in (0, 90, 180, 270) else 0))
            if boxes:
                self._pages[indice] = boxes

        for p in payload.get("sujas", []) or []:
            try:
                self._dirty.add(int(p))
            except (TypeError, ValueError):
                continue
        return len(paginas)

    @staticmethod
    def ler_autosave(documento: str) -> Optional[dict]:
        """
        Lê o rascunho de um documento, se houver e se for utilizável.

        Devolve None em vez de levantar: um rascunho ilegível não pode impedir
        o usuário de abrir o arquivo.
        """
        caminho = caminho_sidecar(documento)
        if not os.path.isfile(caminho):
            return None
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
            return None
        if not payload.get("paginas"):
            return None
        return payload

    def page_stem(self, page: int) -> str:
        """
        Caminho-base (sem extensão) dos arquivos daquela página.

        Um .box/.png por página, seguindo a convenção que o projeto já usa em
        Box/ (ex.: 'AAGAARD - Practical Chess Defence_pg11.box'). Manter um
        arquivo por página preserva a compatibilidade com o formato .box do
        Tesseract, que espera uma imagem por arquivo de boxes.
        """
        base = os.path.splitext(self.path)[0]
        if not self.is_pdf:
            return base
        return f"{base}_pg{page + 1:03d}"
