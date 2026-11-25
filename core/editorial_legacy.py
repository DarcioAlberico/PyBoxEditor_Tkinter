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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, List, Mapping, Optional, Sequence

import chess
import numpy as np

from core import lado_a_jogar as lado_jogar
from core import livro, render_diagrama
from core.diagrama import Casa, Leitura
from core.editorial_adapters import blocos_de_volta, montar_pagina_extraida
from core.editorial_export import (faixas_do_estilo, lado_revisado, orientacao_revisada, posicao_do_fen,
                                   posicao_revisada, revisao_pendente)
from core.log import logger

log = logger(__name__)


@dataclass
class OpcoesDeLeitura:
    """O que a exportação de livro pergunta ao usuário, num objeto só.

    Os padrões são os de `livro.extrair`; `diagramas`, `coordenadas`,
    `fonte`, `moldura`, `cantos`, `probabilidade`, `candidatas` e `camada` têm
    o significado de lá. `modelo_de_linha` liga o CRNN próprio como leitor de
    faixa — e só vale se `linha_trainer.modelo_utilizavel` disser que ele
    passa no portão.

    `camada` fica `"nunca"` aqui pelo mesmo motivo que lá: quem mede o leitor
    (`scripts/fila_de_suspeitas.py`) não pode passar a medir outra coisa sem
    pedir. A janela pede `"auto"` (F110).
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
    candidatas: Optional[Callable] = None
    coletor: Optional[Callable] = None
    modelo_de_linha: bool = False
    usar_ensemble: bool = False
    minimo_consenso: int = 2
    dpi: int = 300
    camada: str = "nunca"
    extras: dict = field(default_factory=dict)

    def kwargs(self) -> dict:
        """Os argumentos nomeados de `livro.extrair`, sem os `None`."""
        saida = {"idioma_ocr": self.idioma, "fusao": self.fusao,
                 "diagramas": self.diagramas, "coordenadas": self.coordenadas,
                 "lex": self.lex, "probabilidade": self.probabilidade,
                 "candidatas": self.candidatas,
                 "coletor": self.coletor, "dpi": self.dpi,
                 "camada": self.camada}
        if self.fonte is not None:
            saida["fonte"] = self.fonte
        if self.moldura is not None:
            saida["moldura"] = self.moldura
        if self.cantos is not None:
            saida["cantos"] = self.cantos
        saida.update(self.extras)
        return saida


def leitor_de_faixa_com_ensemble(leitor_principal: Callable,
                                 servico: Any, idioma: str, *,
                                 modelo_de_linha: bool = False,
                                 minimo_consenso: int = 2,
                                 motor_principal: str = "tesseract") -> Callable:
    """Envolve o leitor principal com o consenso comum a todos os fluxos.

    Com apenas uma engine disponível, preserva o leitor principal. Quando o
    consenso diverge do leitor principal, mantém a leitura já medida e marca
    a faixa para revisão; só usa o consenso quando ele é compatível.

    **A evidência viaja no quinto campo do próprio registro** (RG-14, R-21), que é
    o que `livro._registro_da_faixa` lê. Ela ia por um atributo da função
    (`last_result`), que os invólucros da leitura não repassam: a divergência nunca
    chegava à fila. Viaja a que tem o que conferir — engine que faltou, leituras que
    não concordam — e a do consenso aceito; a faixa que o principal não leu leva a
    dela num registro sem texto.

    `motor_principal` é o nome do adapter que o leitor principal já é: a leitura dele
    entra no ensemble como está, e o motor não é chamado duas vezes pela mesma faixa.
    """
    from core.ocr_engines import CallableAdapter, EnsembleLineReader, OCRServiceAdapters

    registro = OCRServiceAdapters.registry(
        servico, languages=(idioma,), language=idioma,
        trained_line=modelo_de_linha)
    ensemble = EnsembleLineReader(registro, minimum_support=minimo_consenso)
    lida = {"texto": "", "confianca": 0.0}
    registro.adapters = [
        CallableAdapter(a.name, lambda _imagem: (lida["texto"], lida["confianca"]),
                        metadata=a.metadata) if a.name == motor_principal else a
        for a in registro.adapters]

    def ler_faixa(faixa):
        principal = [tuple(r) for r in leitor_principal(faixa) or []]
        com_texto = [r for r in principal if len(r) >= 3 and str(r[0] or "").strip()]
        # A linha mais larga, que é a que `livro._registro_da_faixa` fica.
        escolhida = max(com_texto, key=lambda r: r[2][2] - r[2][0], default=None)
        lida["texto"] = str(escolhida[0]).strip() if escolhida else ""
        lida["confianca"] = float(escolhida[1] or 0.0) if escolhida else 0.0
        consenso = ensemble(faixa)
        resultado = ensemble.last_result
        diverge = bool(consenso and principal
                       and str(principal[0][0]).strip().casefold()
                       != str(consenso[0][0]).strip().casefold())
        if diverge:
            resultado = replace(
                resultado, review_required=True,
                reason_codes=(*resultado.reason_codes, "primary_disagreement"))
        elif consenso:
            return consenso
        if resultado.errors or (len(resultado.hypotheses) >= 2 and resultado.review_required):
            return _com_evidencia(principal, resultado.to_dict())
        return principal

    return ler_faixa


def _com_evidencia(registros: Sequence[tuple], evidencia: dict) -> list[tuple]:
    """Cada registro com a evidência do ensemble no quinto campo; sem registro nenhum, um
    sem texto, só para ela."""
    if not registros:
        return [("", 0.0, (0, 0, 0, 0), (), evidencia)]
    return [(*r[:3], r[3] if len(r) > 3 else (), evidencia) for r in registros]


class ExtratorDeLivro:
    """`legacy_extractor` para `EditorialPipeline`, com os leitores de produção.

    `extrator(caminho, options, token)` devolve a lista de `PaginaExtraida`
    das páginas pedidas em `options.page_indices` (todas, se `None`), lendo
    com `livro.extrair`. `ultimas_paginas` guarda a última lista lida.

    `progresso(atual, total)` é chamado antes de cada página e no fim, na
    thread de quem lê — é o que a janela põe na barra de status. A fachada não
    tem canal de progresso, e sem ele a ação "Documento editorial" passava o
    livro inteiro com a barra girando e "Carregando modelo neural..." escrito:
    não havia como distinguir quarenta minutos de leitura de uma página presa.
    """

    def __init__(self, learning_service: Any, ocr_service: Any,
                 opcoes: OpcoesDeLeitura | None = None,
                 progresso: Optional[Callable[[int, int], None]] = None):
        self.learning_service = learning_service
        self.ocr_service = ocr_service
        self.opcoes = opcoes or OpcoesDeLeitura()
        self.progresso = progresso
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
        if self.opcoes.usar_ensemble:
            ler_faixa = leitor_de_faixa_com_ensemble(
                ler_faixa, servico, idioma,
                modelo_de_linha=self.opcoes.modelo_de_linha,
                minimo_consenso=self.opcoes.minimo_consenso,
                motor_principal=("trained_line" if self.leitor_de_faixa == "modelo_de_linha"
                                 else "tesseract"))
                # Discordância não escolhe uma fonte silenciosamente. Quando
                # há apenas uma engine disponível, preservamos o leitor
                # principal já medido; com duas fontes conflitantes, a cadeia
                # própria permanece como evidência segura.
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
            if self.progresso is not None:
                self.progresso(atual, total)

        kwargs = self.opcoes.kwargs()
        kwargs["dpi"] = dpi
        provar = kwargs.get("probabilidade")
        if provar is not None and token is not None:
            # **O reparo de colagem é o laço mais longo de uma página**, e o
            # token só era consultado entre páginas: com a prova visual ligada,
            # o "Cancelar" esperava a página acabar — e uma página do sumário
            # do Rabinovich passou mais de uma hora nele (F119). A prova é a pergunta
            # que o reparo repete, então é nela que o cancelamento entra.
            def probabilidade(recorte, char, _provar=provar):
                token.raise_if_cancelled()
                return _provar(recorte, char)
            kwargs["probabilidade"] = probabilidade
        self.ultimas_paginas = list(livro.extrair(
            str(caminho), classificar, paginas=paginas,
            ler_pagina=ler_pagina, ler_faixa=ler_faixa,
            progress_callback=progresso, **kwargs))
        return self.ultimas_paginas


def pipeline_de_producao(learning_service: Any, ocr_service: Any,
                         opcoes: OpcoesDeLeitura | None = None,
                         progresso: Optional[Callable[[int, int], None]] = None):
    """`(pipeline, extrator)`: a `EditorialPipeline` com o leitor medido dentro.
    `progresso` é o do `ExtratorDeLivro`."""
    from core.editorial_pipeline import EditorialPipeline

    extrator = ExtratorDeLivro(learning_service, ocr_service, opcoes,
                               progresso=progresso)
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
    caem no lugar. A origem vem de `documento.metadata["source_path"]`, e tem de ser o
    arquivo que se leu: com outro PDF no mesmo caminho, o recorte mostrado seria de outro
    livro (`source_sha256`, a identidade da RG-07 — RG-17, R-36).
    """

    def __init__(self, documento: Any, *, caminho: str | Path | None = None):
        self.documento = documento
        origem = caminho or documento.metadata.get("source_path")
        self.caminho = Path(origem) if origem else None
        self._memoria: "OrderedDict[int, np.ndarray]" = OrderedDict()
        self._doc = None
        self._origem_confere: Optional[bool] = None

    def _confere(self) -> bool:
        """O arquivo no caminho é o que se leu? Pergunta-se uma vez; sem `source_sha256` no
        documento, ou com outro arquivo dado à mão, não há o que conferir."""
        if self._origem_confere is None:
            esperado = str(getattr(self.documento, "source_sha256", "") or "")
            self._origem_confere = True
            if esperado:
                from core.editorial_pipeline import DocumentSource
                achado = DocumentSource.from_path(self.caminho).sha256
                self._origem_confere = achado == esperado
                if not self._origem_confere:
                    log.warning("%s não é o arquivo que se leu (o conteúdo mudou): a revisão "
                                "segue sem a imagem da página.", self.caminho)
        return self._origem_confere

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
            if not self._confere():
                return None
            # A imagem solta (PNG, JPG) passa pelo `fitz` como o PDF: é como
            # `livro.extrair` a abre, e é o que deixa as caixas na escala.
            doc = self._abrir()
            if not 0 <= page_index < len(doc):
                return None
            dpi = self.dpi_da_pagina(page_index) or 300
            imagem = livro._pagina_cinza(doc[page_index], dpi)
        except Exception as erro:  # noqa: BLE001 — sem imagem a fila mostra só texto
            log.warning("a imagem da página %d não saiu de %s (%s: %s); a revisão mostra só o texto.",
                        page_index + 1, self.caminho, type(erro).__name__, erro)
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
            cantos=opcoes.cantos, orientacao=orientacao,
            # Como o leitor desenha: o indicador só do lado que se sabe, e as casas que o
            # livro marcou. Sem os dois, redesenhar os apagava (RG-17, R-34).
            lado_a_jogar=figura.lado_a_jogar, marcas=figura.marcas)
        objeto = render_diagrama.carregar(opcoes.fonte)
        linhas, emolduradas = render_diagrama.linhas_do_diagrama(
            fen, objeto, orientacao, opcoes.moldura, opcoes.cantos, bool(figura.coordenadas))
    except (render_diagrama.FonteDesconhecida, render_diagrama.FonteIncompleta,
            ValueError) as erro:
        nova.aviso = f"FEN revisado, mas não deu para redesenhar: {erro}"
        return nova
    nova.png, nova.largura, nova.altura = png, largura, altura
    nova.linhas = linhas
    nova.linhas_emolduradas = emolduradas
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
    são alteradas: o que sai são cópias, na ordem do documento (`page_index`).

    **Página que não está em `paginas` volta do próprio documento**
    (`pagina_editorial_para_extraida`), e é o que permite exportar o EPUB ou o
    DOCX de um IR gravado noutra sessão: antes, sem a lista de páginas do
    leitor ao lado, a exportação revisada não tinha de onde sair.

    **E cada diagrama sai sabendo se ainda espera revisão** (PD-21):
    `Figura.revisao_pendente` recebe, na cópia, o estado do bloco
    (`editorial_export.revisao_pendente`), e é o que o escritor de produção
    carimba no `alt`, na `figcaption` e na legenda do DOCX. Nos dois ramos —
    as páginas do leitor e as de volta do IR — o mesmo estado chega ao arquivo.
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
            # do bloco **já é** o revisado; o que falta é redesenhar o diagrama
            # cujo FEN a revisão trocou — o diálogo da fila grava o valor
            # inteiro, com o FEN novo e o desenho velho — e o que chegou sem
            # desenho (a Fase 4, o valor só com o FEN). O que ninguém tocou
            # fica com o desenho que tinha: redesenhar tudo no tamanho padrão
            # trocava o livro e custava 30 desenhos por 30 páginas (PD-21).
            blocos = []
            for block, bloco in blocos_de_volta(page, estado_da_revisao=True):
                if bloco is None:
                    continue
                if isinstance(bloco, livro.Figura) and _desenho_velho(block, bloco):
                    bloco = _redesenhar(bloco, bloco.fen, opcoes)
                blocos.append(bloco)
            destino = montar_pagina_extraida(page, blocos)
            saida[int(page.page_index)] = destino
            ordem_das_paginas.append(int(page.page_index))
            continue
        remover: List[int] = []
        for block in page.blocks:
            ordem = _ordem_do_bloco(block.id)
            if ordem is None or not 0 <= ordem < len(destino.blocos):
                continue
            legado = destino.blocos[ordem]
            if isinstance(legado, livro.Figura) and block.kind == "diagram":
                # O estado da revisão vai na cópia, nunca na página do leitor
                # (PD-21): é o que o escritor carimba no `alt` e na legenda. O
                # diagrama que nada acusa fica como o leitor o deixou — o mesmo
                # objeto, sem estado —, porque `None` e `False` escrevem o mesmo.
                pendente = revisao_pendente(block)
                if bool(legado.revisao_pendente) != pendente:
                    legado = copy.copy(legado)
                    legado.revisao_pendente = pendente
                    destino.blocos[ordem] = legado
            status = block.decision.status
            if status == "rejected":
                remover.append(ordem)
                continue
            if status != "reviewed":
                continue
            destino.blocos[ordem] = _bloco_revisado(destino.blocos[ordem], block, opcoes)
        for ordem in sorted(set(remover), reverse=True):
            del destino.blocos[ordem]
    # A ordem do documento, e não a de quem leu: `extrair(paginas=[5, 2])` sai 2 e 5 em
    # todos os formatos (RG-17, R-32).
    return [saida[numero] for numero in sorted(ordem_das_paginas)]


def _desenho_velho(block: Any, figura: livro.Figura) -> bool:
    """A figura que volta do IR traz um desenho que a revisão desmentiu? A mesma régua de
    `_figura_revisada`, com o "antes" que o IR guarda em `decision.original_value` (PD-21); e
    o diagrama que chegou sem as linhas da fonte (a Fase 4) se redesenha sempre."""
    if not figura.fen:
        return False
    if posicao_revisada(block):
        return True
    if figura.origem != "render":
        return False
    if not figura.linhas or orientacao_revisada(block):
        return True
    lado, original = lado_revisado(block), block.decision.original_value
    if not lado or not isinstance(original, Mapping):
        return False
    return (str(original.get("side_to_move_source") or "assumed") != "assumed"
            and str(original.get("side_to_move") or "") not in ("", lado))


def _ordem_do_bloco(block_id: str) -> Optional[int]:
    _prefixo, sep, fim = str(block_id).rpartition("-b")
    return int(fim) if sep and fim.isdigit() else None


def _bloco_revisado(legado: Any, block: Any, opcoes: OpcoesDeFigura) -> Any:
    valor = block.decision.value
    if isinstance(legado, livro.Paragrafo) and isinstance(valor, str):
        # O negrito e o itálico vêm do bloco, e não são zerados (pedido
        # registrado da ED-pré): o evento do editor de livros traz as faixas do
        # texto novo em `style`, e `apply_review` descarta as do texto velho —
        # então o que está em `block.style` é sempre do texto que está em
        # `value`. O parágrafo editado na fila, sem faixas, sai em redondo, como
        # saía.
        negrito = faixas_do_estilo(block, "bold_spans")
        italico = faixas_do_estilo(block, "italic_spans")
        texto_mudou = valor != legado.texto
        if (not texto_mudou and negrito == list(legado.negrito)
                and italico == list(getattr(legado, "italico", None) or [])):
            return legado
        novo = copy.copy(legado)
        if texto_mudou:
            novo.texto = valor
            # As medidas andam caractere a caractere com o texto; com o texto
            # trocado elas já não dizem nada dele.
            novo.pesos = novo.lacunas = None
            novo.inicios = []
            novo.registros = []
        novo.negrito = negrito
        novo.italico = italico
        return novo
    if isinstance(legado, livro.Tabela) and isinstance(valor, Mapping):
        filas = [[str(c) for c in fila] for fila in valor.get("rows", legado.linhas)]
        if filas == legado.linhas:
            return legado
        novo = copy.copy(legado)
        novo.linhas = filas
        return novo
    if isinstance(legado, livro.Figura) and isinstance(valor, Mapping):
        return _figura_revisada(legado, block, opcoes)
    return legado


def _figura_revisada(legado: livro.Figura, block: Any, opcoes: OpcoesDeFigura) -> livro.Figura:
    """
    A figura com o FEN, o lado a jogar e a orientação que o revisor deu (RG-17, R-34).

    **Só se redesenha o que o desenho passou a mentir**: a posição trocada, sempre; a
    orientação e o lado, só na figura que já é desenho — a orientação muda as casas de
    lugar, e o indicador desenhado é do lado de antes. O recorte do livro fica como o livro
    o imprimiu: trocar de quem é a vez não é motivo para jogá-lo fora.
    """
    valor = block.decision.value
    fen = str(valor.get("fen") or "") or (legado.fen or "")
    lado = lado_revisado(block)
    if fen and lado:
        fen = lado_jogar.com_lado(fen, lado)
    orientacao = str(valor.get("orientation") or "") or legado.orientacao
    virou = orientacao != legado.orientacao
    posicao_mudou = posicao_do_fen(fen) != posicao_do_fen(legado.fen)
    lado_mudou = bool(lado) and (lado, "usuario") != (legado.lado_a_jogar, legado.lado_origem)
    if not (virou or lado_mudou or posicao_mudou or fen != (legado.fen or "")):
        return legado
    nova = copy.copy(legado)
    nova.fen, nova.orientacao = fen or None, orientacao
    if lado_mudou:
        nova.lado_a_jogar, nova.lado_origem = lado, "usuario"
    indicador_velho = lado_mudou and legado.lado_a_jogar not in (None, lado)
    if fen and (posicao_mudou or (legado.origem == "render" and (virou or indicador_velho))):
        return _redesenhar(nova, fen, opcoes)
    return nova

