import datetime
import json
import os
import queue
import threading
from dataclasses import replace
from typing import Dict, List, Optional, Set

from core.box_model import BoxEntry

import logging

from core.log import logger, uma_vez

log = logger(__name__)


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
                from core.escrita_atomica import escrita_atomica
                with escrita_atomica(caminho) as f:
                    json.dump(payload, f, ensure_ascii=False)
                self._erro = None
            except Exception as e:      # noqa: BLE001 — consultado pela UI
                # A barra de status, sobrescrita logo, não basta (RG-05, R-04): o log
                # guarda a primeira falha de cada rascunho, e o título da janela diz
                # enquanto ela durar.
                uma_vez(log, f"rascunho:{caminho}", logging.WARNING,
                        "o rascunho %s não foi gravado: %s", caminho, e)
                self._erro = e

    @property
    def ultimo_erro(self):
        return self._erro


def _estado_no_rascunho(b: BoxEntry) -> list:
    """O estado inteiro do box (`as_state`), com a confiança arredondada.

    Com oito campos, `negativo`, `margem` e `moldura` se perdiam na recuperação, e o
    `.box` salvo em seguida perdia o campo 8 (RG-05, R-55).
    """
    estado = list(b.as_state())
    estado[5] = round(b.confidence, 4)
    return estado


def _box_do_rascunho(it, f: float) -> Optional[BoxEntry]:
    """Um box do rascunho por `from_state`, reescalado por `f`; `None` se não se lê.

    `from_state` aceita o estado curto dos rascunhos antigos: o de antes da F8.1 não tem
    o oitavo campo (ângulo zero), o de antes da RG-05 não tem os três últimos, e os
    padrões deles são o que aquele box queria dizer. A escala vem depois.
    """
    try:
        if len(it) < 5:
            return None
        box = BoxEntry.from_state(list(it[:11]))
        x1, y1, x2, y2 = int(box.x1), int(box.y1), int(box.x2), int(box.y2)
        conf = float(box.confidence)
        angulo = int(box.angulo)
    except (TypeError, ValueError):
        return None
    if f != 1.0:
        x1, y1 = int(round(x1 * f)), int(round(y1 * f))
        x2, y2 = int(round(x2 * f)), int(round(y2 * f))
    return replace(box, x1=x1, y1=y1, x2=x2, y2=y2, confidence=conf,
                   source=box.source or "",
                   angulo=angulo if angulo in (0, 90, 180, 270) else 0)


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
        """Páginas com alterações não salvas — inclusive a que ficou sem boxes.

        A página esvaziada contava como limpa (RG-05, R-04): "Nada para salvar", o
        `.box` antigo ficava no disco e o rascunho velho voltava a oferecer os boxes
        apagados. Salvá-la grava o `.box` vazio.
        """
        return sorted(self._dirty)

    def pages_to_save(self) -> List[int]:
        """O que "Salvar todas" grava: as páginas com boxes e as esvaziadas."""
        return sorted(set(self.pages_with_boxes()) | self._dirty)

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
            if boxes or pagina in self._dirty:
                # A página esvaziada entra, vazia (RG-05, R-04).
                paginas[str(pagina)] = [_estado_no_rascunho(b) for b in boxes]
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
        if not self.pages_with_boxes() and not self._dirty:
            return None
        destino = self.sidecar()
        gravador.agendar(destino, self.montar_payload())
        return destino

    def remover_autosave(self):
        """Apaga o rascunho. Chamado quando o trabalho foi gravado de verdade,
        ou quando o usuário decidiu descartá-lo."""
        try:
            os.remove(self.sidecar())
        except FileNotFoundError:
            pass
        except OSError as erro:
            # O rascunho que fica volta como "recuperar trabalho" (RG-05, R-04).
            log.warning("o rascunho %s não foi apagado e pode ser oferecido de novo: %s",
                        self.sidecar(), erro)

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
        recuperadas = boxes_perdidos = 0
        paginas_perdidas: List[str] = []
        for chave, itens in paginas.items():
            try:
                indice = int(chave)
            except (TypeError, ValueError):
                paginas_perdidas.append(str(chave))
                continue
            boxes = []
            for it in itens or []:
                box = _box_do_rascunho(it, f)
                if box is not None:
                    boxes.append(box)
                else:
                    boxes_perdidos += 1
            # A lista vazia é a página que o usuário esvaziou (R-04): ela volta vazia,
            # e não com os boxes do `.box` antigo.
            if boxes or not itens:
                self._pages[indice] = boxes
                recuperadas += 1
            else:
                paginas_perdidas.append(str(chave))

        for p in payload.get("sujas", []) or []:
            try:
                self._dirty.add(int(p))
            except (TypeError, ValueError):
                log.warning("o rascunho marca como não salva uma página que não existe: %r", p)
        if paginas_perdidas or boxes_perdidos:
            # A página descartada contava como recuperada, e a barra de status dizia que o
            # trabalho tinha voltado (RG-18, R-37).
            log.warning("do rascunho ficaram de fora %d página(s) (%s) e %d box(es) que não se leem",
                        len(paginas_perdidas), ", ".join(paginas_perdidas[:5]) or "nenhuma",
                        boxes_perdidos)
        return recuperadas

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
