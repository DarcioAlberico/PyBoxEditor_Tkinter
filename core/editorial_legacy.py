"""O leitor de livro medido (`core.livro.extrair`) atrás da fachada editorial.

A `EditorialPipeline` nasceu com um reconhecedor próprio de linha que, numa
página digitalizada, não lê nada: sem camada de texto e sem adapters de
linha, `Phase3Processor` trata a página inteira como uma linha vazia, e o
documento sai com um bloco `unresolved` sem aviso. Medido na p. 30 do
Aagaard, em 2026-09-18: 1 bloco, 0 caracteres, 100% de CER — enquanto
"Exportar Livro", que usa `livro.extrair` com a fusão por palavra entre a
cadeia própria e o Tesseract, sai a 2,4%.

Este módulo é a ponte: monta o `legacy_extractor` que `EditorialPipeline`
aceita, com **os mesmos leitores** da exportação de livro — o classificador
de glifos com o idioma preso, o Tesseract de página e de faixa (ou o modelo
de linha, quando passa no portão de produção) — e traduz o token de
cancelamento da fachada para o `progress_callback` de `livro.extrair`. O
resultado é o IR de sempre (`EditorialDocument`), só que cheio; e a lista de
`PaginaExtraida` fica guardada em `ultimas_paginas` para o EPUB/DOCX
históricos, que ainda são os escritores que embutem fonte de símbolos e
redesenham diagramas.
"""

from __future__ import annotations

import copy
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Mapping, Optional, Sequence

import chess
import numpy as np

from core import livro, render_diagrama
from core.diagrama import Casa, Leitura
from core.editorial_adapters import pagina_editorial_para_extraida


@dataclass
class OpcoesDeLeitura:
    """O que a exportação de livro pergunta ao usuário, num objeto só.

    Os padrões são os de `livro.extrair`; `diagramas`, `coordenadas`,
    `fonte`, `moldura`, `cantos` e `probabilidade` têm o significado de lá.
    `modelo_de_linha` liga o CRNN próprio como leitor de faixa — e só vale se
    `linha_trainer.modelo_utilizavel` disser que ele passa no portão.
    """

    idioma: str = "en"
    fusao: str = "palavra"
    diagramas: str = "render"
    coordenadas: Any = False
    fonte: Optional[str] = None
    moldura: Any = None
    cantos: Optional[str] = None
    lex: Any = None
    probabilidade: Optional[Callable] = None
    coletor: Optional[Callable] = None
    modelo_de_linha: bool = False
    dpi: int = 300
    extras: dict = field(default_factory=dict)

    def kwargs(self) -> dict:
        """Os argumentos nomeados de `livro.extrair`, sem os `None`."""
        saida = {"idioma_ocr": self.idioma, "fusao": self.fusao,
                 "diagramas": self.diagramas, "coordenadas": self.coordenadas,
                 "lex": self.lex, "probabilidade": self.probabilidade,
                 "coletor": self.coletor, "dpi": self.dpi}
        if self.fonte is not None:
            saida["fonte"] = self.fonte
        if self.moldura is not None:
            saida["moldura"] = self.moldura
        if self.cantos is not None:
            saida["cantos"] = self.cantos
        saida.update(self.extras)
        return saida


class ExtratorDeLivro:
    """`legacy_extractor` para `EditorialPipeline`, com os leitores de produção.

    `extrator(caminho, options, token)` devolve a lista de `PaginaExtraida`
    das páginas pedidas em `options.page_indices` (todas, se `None`), lendo
    com `livro.extrair`. `ultimas_paginas` guarda a última lista lida.
    """

    def __init__(self, learning_service: Any, ocr_service: Any,
                 opcoes: OpcoesDeLeitura | None = None):
        self.learning_service = learning_service
        self.ocr_service = ocr_service
        self.opcoes = opcoes or OpcoesDeLeitura()
        self.ultimas_paginas: List[Any] = []
        self.leitor_de_faixa = "tesseract"

    def _leitores(self):
        """`(classificar, ler_pagina, ler_faixa)` — os mesmos da exportação."""
        idioma = self.opcoes.idioma
        if not self.learning_service.load_predictor():
            raise RuntimeError(self.learning_service.motivo_do_modelo())
        classificar = self.learning_service.leitor_de_texto(idioma)
        servico = self.ocr_service

        def ler_pagina(imagem):
            return servico.tesseract_pagina_detalhada_conf(imagem, idioma)

        ler_faixa = None
        if self.opcoes.modelo_de_linha:
            from config.paths import caminhos_modelo_linha
            from core.linha_trainer import modelo_utilizavel
            modelo, meta = caminhos_modelo_linha()
            utilizavel, _motivo = modelo_utilizavel(meta, modelo)
            if utilizavel:
                self.leitor_de_faixa = "modelo_de_linha"

                def ler_faixa(faixa, _m=str(modelo), _j=str(meta)):
                    return servico.linha_treinada_conf(faixa, _m, _j)
        if ler_faixa is None:
            self.leitor_de_faixa = "tesseract"

            def ler_faixa(faixa):
                return servico.tesseract_faixa_detalhada_conf(faixa, idioma)
        return classificar, ler_pagina, ler_faixa

    def __call__(self, caminho: str | Path, options: Any = None,
                 token: Any = None) -> Sequence[Any]:
        classificar, ler_pagina, ler_faixa = self._leitores()
        paginas = None
        if options is not None and getattr(options, "page_indices", None) is not None:
            paginas = [int(i) for i in options.page_indices]
        dpi = int(getattr(options, "dpi", None) or self.opcoes.dpi)

        def progresso(atual, total):
            if token is not None:
                token.raise_if_cancelled()

        kwargs = self.opcoes.kwargs()
        kwargs["dpi"] = dpi
        self.ultimas_paginas = list(livro.extrair(
            str(caminho), classificar, paginas=paginas,
            ler_pagina=ler_pagina, ler_faixa=ler_faixa,
            progress_callback=progresso, **kwargs))
        return self.ultimas_paginas


def pipeline_de_producao(learning_service: Any, ocr_service: Any,
                         opcoes: OpcoesDeLeitura | None = None):
    """`(pipeline, extrator)`: a `EditorialPipeline` com o leitor medido dentro."""
    from core.editorial_pipeline import EditorialPipeline

    extrator = ExtratorDeLivro(learning_service, ocr_service, opcoes)
    return EditorialPipeline(legacy_extractor=extrator), extrator


# ----------------------------------------------------------------------
# O que a fila de revisão precisa do leitor: a página, o diagrama, a volta
# ----------------------------------------------------------------------

#: Quantas páginas rasterizadas ficam na memória do provedor. A revisão anda
#: por página; quatro cobrem o vai-e-volta entre vizinhas sem guardar um
#: livro de 300 páginas a 300 dpi (8 MB cada).
PAGINAS_EM_MEMORIA = 4


class ProvedorDePaginas:
    """A imagem de cada página do documento, na escala em que ela foi lida.

    O IR guarda as caixas em pixels da imagem que `livro.extrair` leu — a
    página rasterizada a `pagina.dpi` em cinza —, e não a imagem: um livro
    inteiro não cabe no JSON. Quem quer o recorte de uma linha rasteriza a
    página de novo, pelo mesmo caminho (`livro._pagina_cinza`), e as caixas
    caem no lugar. A origem vem de `documento.metadata["source_path"]`.
    """

    def __init__(self, documento: Any, *, caminho: str | Path | None = None):
        self.documento = documento
        origem = caminho or documento.metadata.get("source_path")
        self.caminho = Path(origem) if origem else None
        self._memoria: "OrderedDict[int, np.ndarray]" = OrderedDict()
        self._doc = None

    def dpi_da_pagina(self, page_index: int) -> int:
        for page in self.documento.pages:
            if page.page_index == page_index:
                return int(page.metadata.get("dpi") or 0)
        return 0

    def _abrir(self):
        if self._doc is None:
            import fitz
            self._doc = fitz.open(str(self.caminho))
        return self._doc

    def imagem(self, page_index: int) -> Optional[np.ndarray]:
        """A página em cinza (`uint8`, altura × largura), ou `None` quando
        não há origem, ou a página não está nela."""
        if page_index in self._memoria:
            self._memoria.move_to_end(page_index)
            return self._memoria[page_index]
        if self.caminho is None or not self.caminho.exists():
            return None
        try:
            # A imagem solta (PNG, JPG) passa pelo `fitz` como o PDF: é como
            # `livro.extrair` a abre, e é o que deixa as caixas na escala.
            doc = self._abrir()
            if not 0 <= page_index < len(doc):
                return None
            dpi = self.dpi_da_pagina(page_index) or 300
            imagem = livro._pagina_cinza(doc[page_index], dpi)
        except Exception:  # noqa: BLE001 — sem imagem a fila mostra só texto
            return None
        self._memoria[page_index] = imagem
        while len(self._memoria) > PAGINAS_EM_MEMORIA:
            self._memoria.popitem(last=False)
        return imagem

    __call__ = imagem

    def fechar(self) -> None:
        if self._doc is not None:
            try:
                self._doc.close()
            finally:
                self._doc = None
        self._memoria.clear()


def leitura_de_fen(fen: str, caixa: Sequence[int] | None, *,
                   orientacao: str = "branca",
                   lado_a_jogar: str | None = None) -> Leitura:
    """Uma `diagrama.Leitura` montada a partir de um FEN, para o
    `DialogoDiagrama` abrir a posição do IR ao lado do recorte da página.

    As casas saem com confiança 1,0 e sem arbitragem: o que se abre aqui é
    uma decisão já tomada (pelo modelo ou pelo revisor), e o diálogo mostra
    o que ela diz — quem discorda edita a casa, que aí vira `corrigida`.

    `lado_a_jogar` é o lado **lido** (da legenda ou de uma revisão anterior), e
    não o do FEN: o campo do FEN sai preenchido de todo jeito, e abrir o
    diálogo com "brancas" marcado por convenção é o que faz a convenção virar
    resposta. Sem ele, o diálogo mostra o aviso da convenção, como antes.
    """
    tabuleiro = chess.Board(None)
    campos = str(fen or "").split()
    if campos:
        try:
            tabuleiro.set_board_fen(campos[0])
        except ValueError:
            tabuleiro = chess.Board(None)
    casas = []
    for linha in range(8):
        for coluna in range(8):
            peca = tabuleiro.piece_at(chess.square(coluna, 7 - linha))
            casas.append(Casa(linha, coluna, peca.symbol() if peca else None,
                              confianca=1.0 if peca else 0.0))
    if caixa and len(caixa) == 4:
        x1, y1, x2, y2 = (int(v) for v in caixa)
    else:
        x1 = y1 = 0
        x2 = y2 = 8
    return Leitura(caixa=(x1, y1, x2, y2), casas=casas,
                   orientacao=orientacao or "branca",
                   lado_a_jogar=(lado_a_jogar if lado_a_jogar in ("w", "b")
                                 else None))


@dataclass
class OpcoesDeFigura:
    """Como redesenhar um diagrama cujo FEN o revisor mudou — os mesmos
    parâmetros de `livro.extrair`, para a figura nova sair igual às outras
    do livro."""

    fonte: str = render_diagrama.FONTE_PADRAO
    lado: int = render_diagrama.LADO_PADRAO
    moldura: Any = render_diagrama.MOLDURA_PADRAO
    cantos: str = render_diagrama.CANTO_PADRAO


def _redesenhar(figura: livro.Figura, fen: str, opcoes: OpcoesDeFigura) -> livro.Figura:
    """A `Figura` com a posição nova: PNG, linhas de fonte e origem `render`.

    Sem fonte de xadrez no ambiente a figura fica como estava, com o FEN
    trocado e o aviso dizendo por quê — o texto alternativo já sai certo,
    e o desenho é o que falta.
    """
    nova = copy.copy(figura)
    nova.fen = fen
    orientacao = figura.orientacao or "branca"
    try:
        png, largura, altura = render_diagrama.desenhar(
            fen, fonte=opcoes.fonte, lado_px=opcoes.lado,
            coordenadas=bool(figura.coordenadas), moldura=opcoes.moldura,
            cantos=opcoes.cantos, orientacao=orientacao)
        objeto = render_diagrama.carregar(opcoes.fonte)
        em_grade = (render_diagrama.grade(fen, objeto, orientacao,
                                          opcoes.moldura, opcoes.cantos)
                    if figura.coordenadas else None)
    except (render_diagrama.FonteDesconhecida, render_diagrama.FonteIncompleta,
            ValueError) as erro:
        nova.aviso = f"FEN revisado, mas não deu para redesenhar: {erro}"
        return nova
    nova.png, nova.largura, nova.altura = png, largura, altura
    nova.linhas = em_grade or render_diagrama.linhas(fen, objeto, orientacao)
    nova.linhas_emolduradas = em_grade is not None
    nova.fonte = opcoes.fonte
    nova.origem = "render"
    nova.aviso = None
    nova.casas_de_largura = largura * 8.0 / render_diagrama.lado_efetivo(opcoes.lado)
    return nova


def aplicar_revisao(paginas: Sequence[livro.PaginaExtraida], documento: Any, *,
                    opcoes: OpcoesDeFigura | None = None) -> List[livro.PaginaExtraida]:
    """As `PaginaExtraida` com as decisões do revisor aplicadas — para o EPUB
    e o DOCX históricos, que ainda leem delas, saírem com o que a fila
    decidiu. É a volta do IR para o leitor, no que o leitor consome.

    O bloco `block-<page>-b<ordem>` é o `blocos[ordem]` da página de mesmo
    número: o texto revisado entra no parágrafo, as filas na tabela, o FEN
    na figura (redesenhada quando há fonte). O bloco **rejeitado** sai do
    livro. O que não foi tocado fica como o leitor deixou — inclusive as
    medidas de negrito e lacuna, que o texto novo já não acompanha e que
    por isso são esquecidas no parágrafo mexido. As páginas originais não
    são alteradas: o que sai são cópias.

    **Página que não está em `paginas` volta do próprio documento**
    (`pagina_editorial_para_extraida`), e é o que permite exportar o EPUB ou o
    DOCX de um IR gravado noutra sessão: antes, sem a lista de páginas do
    leitor ao lado, a exportação revisada não tinha de onde sair.
    """
    opcoes = opcoes or OpcoesDeFigura()
    por_numero = {int(p.numero): p for p in paginas}
    saida = {numero: copy.copy(p) for numero, p in por_numero.items()}
    for pagina in saida.values():
        pagina.blocos = list(pagina.blocos)
    ordem_das_paginas = [int(p.numero) for p in paginas]
    for page in documento.pages:
        destino = saida.get(int(page.page_index))
        if destino is None:
            # A página que o leitor desta sessão não leu — um IR gravado e
            # reaberto depois, ou uma exportação de páginas soltas — volta do
            # próprio documento (item 4 da revisão de 2026-09-18). Ali o valor
            # do bloco **já é** o revisado, então só falta redesenhar o
            # diagrama cujo FEN mudou, que é o que o laço abaixo não vê.
            destino = pagina_editorial_para_extraida(page)
            for i, bloco in enumerate(destino.blocos):
                if isinstance(bloco, livro.Figura) and bloco.origem == "render"                         and bloco.fen:
                    destino.blocos[i] = _redesenhar(bloco, bloco.fen, opcoes)
            saida[int(page.page_index)] = destino
            ordem_das_paginas.append(int(page.page_index))
            continue
        remover: List[int] = []
        for block in page.blocks:
            ordem = _ordem_do_bloco(block.id)
            if ordem is None or not 0 <= ordem < len(destino.blocos):
                continue
            status = block.decision.status
            if status == "rejected":
                remover.append(ordem)
                continue
            if status != "reviewed":
                continue
            destino.blocos[ordem] = _bloco_revisado(destino.blocos[ordem],
                                                    block.decision.value, opcoes)
        for ordem in sorted(set(remover), reverse=True):
            del destino.blocos[ordem]
    return [saida[numero] for numero in ordem_das_paginas]


def _ordem_do_bloco(block_id: str) -> Optional[int]:
    _prefixo, sep, fim = str(block_id).rpartition("-b")
    return int(fim) if sep and fim.isdigit() else None


def _bloco_revisado(legado: Any, valor: Any, opcoes: OpcoesDeFigura) -> Any:
    if isinstance(legado, livro.Paragrafo) and isinstance(valor, str):
        if valor == legado.texto:
            return legado
        novo = copy.copy(legado)
        novo.texto = valor
        # As medidas andam caractere a caractere com o texto; com o texto
        # trocado elas já não dizem nada dele.
        novo.pesos = novo.lacunas = None
        novo.negrito = []
        novo.inicios = []
        novo.registros = []
        return novo
    if isinstance(legado, livro.Tabela) and isinstance(valor, Mapping):
        filas = [[str(c) for c in fila] for fila in valor.get("rows", legado.linhas)]
        if filas == legado.linhas:
            return legado
        novo = copy.copy(legado)
        novo.linhas = filas
        return novo
    if isinstance(legado, livro.Figura) and isinstance(valor, Mapping):
        fen = str(valor.get("fen") or "")
        if fen and fen != (legado.fen or ""):
            return _redesenhar(legado, fen, opcoes)
        return legado
    return legado
