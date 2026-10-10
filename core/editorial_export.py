"""
A exportação do documento editorial: HTML, TXT, JSON e PDF pesquisável saem daqui,
do IR; EPUB e DOCX saem do escritor de produção (`core/exportar.py`) sobre as
páginas de volta do IR (PD-21, 2026-10-10).

Até a PD-21 este módulo era o terceiro escritor de EPUB e DOCX — um `content.xhtml`
só, as imagens em base64, sem a fonte dos símbolos nem o diagrama redesenhado —, e
o único a carimbar "não revisado" no diagrama. O carimbo passou à `Figura`
(`revisao_pendente`) e ao `exportar.py`; o que ficou aqui é o HTML semântico com os
modos e a auditoria, o TXT, o JSON e a camada de texto do PDF pesquisável.
"""

from __future__ import annotations

import base64
import html
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import fitz

from core.editorial_model import EditorialBlock, EditorialDocument

from core.log import logger

log = logger(__name__)


EXPORT_FORMATS = frozenset({"html", "epub", "docx", "pdf", "json", "txt"})
EXPORT_MODES = frozenset({"faithful", "clean", "hybrid"})


@dataclass(frozen=True)
class ExportOptions:
    format: str = "html"
    mode: str = "clean"
    include_diagnostics: bool = True
    include_review_report: bool = False
    source_pdf: str | Path | None = None
    title: str = ""
    #: As `PaginaExtraida` em que EPUB e DOCX se escrevem, **já com a revisão do
    #: documento aplicada** (`editorial_legacy.aplicar_revisao`): quem tem as
    #: páginas do leitor à mão é a fachada, e é ela que aplica. Vazio, as páginas
    #: voltam do próprio IR (PD-21) — o mesmo arquivo, byte a byte, quando o IR
    #: veio do leitor.
    paginas: Sequence[Any] = ()
    #: Como redesenhar o diagrama cujo FEN mudou ou que veio sem desenho
    #: (`editorial_legacy.OpcoesDeFigura`); `None` é o padrão do livro.
    figura: Any = None
    #: O que `exportar.exportar` recebe além das páginas: `titulo`, `autor`,
    #: `diagramas`, `corpo_pt`, `moldura`, `cantos`, `idioma`. Sem `titulo`, vale
    #: o do PDF de origem, e sem PDF o do documento.
    escritor: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        formato = str(self.format).casefold().lstrip(".")
        modo = str(self.mode).casefold()
        if formato not in EXPORT_FORMATS:
            raise ValueError(f"formato editorial não suportado: {formato!r}")
        if modo not in EXPORT_MODES:
            raise ValueError(f"modo editorial não suportado: {modo!r}")
        object.__setattr__(self, "format", formato)
        object.__setattr__(self, "mode", modo)
        object.__setattr__(self, "paginas", tuple(self.paginas))
        object.__setattr__(self, "escritor", dict(self.escritor))


@dataclass(frozen=True)
class ExportReport:
    format: str
    files: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


def _text(value: Any) -> str:
    if isinstance(value, Mapping):
        if "text" in value:
            return str(value["text"])
        if "fen" in value:
            return str(value["fen"])
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "" if value is None else str(value)


def _fen(value: Any) -> str:
    return str(value.get("fen", "")) if isinstance(value, Mapping) else ""


def texto_do_bloco(block: EditorialBlock) -> str:
    """
    A face de texto de um bloco: o que o PDF pesquisável põe na camada
    invisível e o TXT escreve (item 10 da revisão de 2026-09-18).

    O parágrafo e o título são o texto; o diagrama, `FEN: <posição>`; a tabela,
    uma fila por linha, com as células separadas por espaço — a mesma forma da
    evidência do adapter. A figura sem posição (o cabeçalho impresso, a página
    que virou imagem) não tem texto, e sai vazia. Era o `json.dumps` do valor:
    a tabela ia para a camada que a busca lê como `{"rows": [["W", "Win"], …]}`,
    e a figura, com o PNG inteiro em base64.
    """
    value = block.decision.value
    if block.kind == "diagram":
        fen = _fen(value)
        return f"FEN: {fen}" if fen else ""
    if block.kind == "table" and isinstance(value, Mapping):
        return "\n".join(" ".join(_text(celula).replace("\n", " ") for celula in fila)
                         for fila in value.get("rows", ()))
    if isinstance(value, Mapping):
        return str(value.get("text") or "")
    return _text(value)


#: Lado do tabuleiro desenhado quando o diagrama chega sem imagem, em pixels.
#: Oito casas de 24 px: 1 KB de PNG, e legível no tablet e no papel.
LADO_DO_DIAGRAMA_PX = 192

#: O nome da fonte de xadrez na página do PDF pesquisável (ver `_pdf`).
FONTE_DA_CAMADA = "pyboxchess"


def imagem_do_diagrama(block: EditorialBlock) -> tuple[str, str]:
    """
    O PNG da figura em base64, e de onde ele veio — ``(imagem, origem)``.

    **Nenhum diagrama sai sem imagem** (item 3 da revisão de 2026-09-18). O
    caminho legado traz o recorte ou o desenho prontos, no bloco ou no valor;
    a Fase 4 não traz imagem nenhuma — o ``DiagramResult`` guarda a posição e
    os *hashes* do recorte, não os pixels —, e até aqui o `<figure>` dela saía
    com legenda e sem figura. Um FEN, porém, é tudo que o desenho precisa:
    `render_diagrama.desenhar` é o mesmo código que escreve o livro, e custa um
    quilobyte por diagrama.

    ``origem`` é ``"recorte"`` (o que veio da página), ``"desenho"`` (feito do
    FEN) ou ``"nenhuma"`` — e a última vira aviso no relatório da exportação.
    """
    value = block.decision.value
    candidatos = [block.metadata.get("png_base64")]
    if isinstance(value, Mapping):
        candidatos.append(value.get("png_base64"))
    for encoded in candidatos:
        if not encoded:
            continue
        try:
            base64.b64decode(str(encoded), validate=True)
        except (ValueError, TypeError):
            continue
        return str(encoded), "recorte"
    fen = _fen(value)
    if not fen:
        return "", "nenhuma"
    try:
        from core import lado_a_jogar as lado_jogar
        from core import render_diagrama
        png, _largura, _altura = render_diagrama.desenhar(
            fen, lado_px=LADO_DO_DIAGRAMA_PX,
            # O indicador de quem joga só entra quando o lado foi **lido**:
            # desenhá-lo a partir da convenção seria pôr no papel a afirmação
            # que o resto deste módulo existe para não fazer.
            lado_a_jogar=(lado_jogar.do_fen(fen)
                          if origem_do_lado(block) != "assumed" else None))
    except Exception as erro:  # noqa: BLE001 — fonte ausente ou FEN torto não derruba a exportação
        log.warning("diagrama %s sem imagem na exportação: %s", block.id, erro)
        return "", "nenhuma"
    return base64.b64encode(png).decode("ascii"), "desenho"


def origem_do_lado(block: EditorialBlock) -> str:
    """``legend``, ``manual``, ``explicit`` ou ``assumed`` — a convenção."""
    value = block.decision.value
    if isinstance(value, Mapping):
        origem = value.get("side_to_move_source")
        if origem:
            return str(origem)
    return str(block.metadata.get("side_to_move_source", "assumed"))


def legenda_do_diagrama(block: EditorialBlock) -> str:
    """
    O que a legenda do diagrama diz além do FEN: de quem é a vez, e se sobrou
    revisão.

    Os dois são **carimbo, e não diagnóstico**: saem em todos os modos,
    inclusive no limpo. O modo limpo tira a proveniência e o histórico de
    hipóteses, que são para quem revisa; um diagrama cuja posição ninguém
    conferiu, ou cujo lado a jogar é convenção, continua sendo isso no arquivo
    entregue ao leitor — esconder a ressalva é o que transformaria uma leitura
    de 94,5% de casas certas em afirmação.
    """
    from core import lado_a_jogar as lado_jogar

    fen = _fen(block.decision.value)
    partes = [lado_jogar.marca(lado_jogar.do_fen(fen), origem_do_lado(block))]
    if revisao_pendente(block):
        partes.append(lado_jogar.NAO_REVISADO)
    return "; ".join(partes)


def revisao_pendente(block: EditorialBlock) -> bool:
    """O diagrama ainda espera olho humano?"""
    value = block.decision.value
    estado = ""
    if isinstance(value, Mapping):
        estado = str(value.get("review_status", ""))
        if value.get("review_required"):
            return True
    estado = estado or str(block.metadata.get("review_status", ""))
    return (estado in {"review_required", "unresolved"}
            or block.decision.status == "unresolved")


def _audit(block: EditorialBlock, options: ExportOptions) -> str:
    if options.mode == "clean":
        return ""
    provenance = ", ".join(f"p{ref.page_index + 1}" for ref in block.source_refs)
    original = _text(block.decision.original_value)
    return (f'<details class="audit"><summary>Proveniência e auditoria</summary>'
            f'<span data-status="{html.escape(block.decision.status, quote=True)}">'
            f"Origem: {html.escape(provenance or 'desconhecida')}.</span>"
            f"<span>Hipótese original: {html.escape(original or _text(block.decision.value))}</span>"
            f"</details>")


def trechos_em_negrito(texto: str, block: EditorialBlock) -> list[tuple[str, bool]]:
    """
    O texto partido nos trechos em negrito e nos de fora deles.

    O adapter guarda o negrito como faixas de índice em `style["bold_spans"]`
    (é como `core/negrito.py` o mede, caractere a caractere), e os escritores
    daqui o ignoravam: o parágrafo saía inteiro em redondo, e a ênfase que o
    livro imprimiu sumia do HTML, do EPUB e do DOCX. Faixa fora do texto é
    cortada, e faixa vazia não vira `run` nenhum.
    """
    faixas = []
    for item in block.style.get("bold_spans") or []:
        try:
            inicio, fim = int(item[0]), int(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        faixas.append((inicio, fim))
    saida: list[tuple[str, bool]] = []
    anterior = 0
    for inicio, fim in sorted(faixas):
        inicio, fim = max(inicio, anterior), min(fim, len(texto))
        if fim <= inicio:
            continue
        if inicio > anterior:
            saida.append((texto[anterior:inicio], False))
        saida.append((texto[inicio:fim], True))
        anterior = fim
    if anterior < len(texto):
        saida.append((texto[anterior:], False))
    return saida


def _faixas(block: EditorialBlock, chave: str) -> list[tuple[int, int]]:
    faixas = []
    for item in block.style.get(chave) or []:
        try:
            faixas.append((int(item[0]), int(item[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return faixas


def trechos_com_estilo(texto: str, block: EditorialBlock
                       ) -> list[tuple[str, bool, bool]]:
    """`(trecho, negrito, itálico)`, cortado onde qualquer um dos dois muda
    (PD-06). Sem `italic_spans` é o `trechos_em_negrito` de sempre."""
    from core.exportar import trechos_com_estilo as cortar

    inclinados = _faixas(block, "italic_spans")
    if not inclinados:
        return [(t, forte, False) for t, forte in trechos_em_negrito(texto, block)]
    return cortar(texto, _faixas(block, "bold_spans"), inclinados)


def _com_negrito(texto: str, block: EditorialBlock) -> str:
    """O texto escapado, com `<strong>` onde o livro imprimiu negrito e `<em>`
    onde imprimiu itálico (PD-06)."""
    partes = trechos_com_estilo(texto, block)
    if not partes:
        return html.escape(texto)
    saida = []
    for trecho, forte, inclinado in partes:
        pedaco = html.escape(trecho)
        if inclinado:
            pedaco = f"<em>{pedaco}</em>"
        if forte:
            pedaco = f"<strong>{pedaco}</strong>"
        saida.append(pedaco)
    return "".join(saida)


def _block_html(block: EditorialBlock, options: ExportOptions) -> str:
    value = block.decision.value
    anchor = html.escape(block.id, quote=True)
    common = f' id="{anchor}" data-kind="{html.escape(block.kind, quote=True)}"'
    if block.kind == "heading":
        body = f"<h2{common}>{html.escape(_text(value))}</h2>"
    elif block.kind == "chess_sequence":
        body = (f'<div{common} class="chess-sequence" aria-label="Sequência de xadrez">'
                f"{html.escape(_text(value))}</div>")
    elif block.kind == "diagram":
        fen = _fen(value)
        data_fen = html.escape(fen, quote=True)
        ressalva = legenda_do_diagrama(block)
        alt = html.escape(str(block.metadata.get(
            "alt", f"Diagrama de xadrez: {fen} — {ressalva}")), quote=True)
        encoded, origem_da_imagem = imagem_do_diagrama(block)
        image = (f'<img alt="{alt}" src="data:image/png;base64,{encoded}">'
                 if encoded else "")
        body = (f'<figure{common} data-fen="{data_fen}" '
                f'data-side-source="{html.escape(origem_do_lado(block), quote=True)}" '
                f'data-image="{origem_da_imagem}"'
                + (' data-review="pending"' if revisao_pendente(block) else "")
                + ' aria-label="Diagrama de xadrez">'
                f"{image}<figcaption>{html.escape(fen or _text(value))}"
                f" <span class=\"ressalva\">({html.escape(ressalva)})</span>"
                f"</figcaption></figure>")
    elif block.kind in ("figure", "caption") and isinstance(value, Mapping):
        # A figura que **não** é tabuleiro: a faixa impressa acima do diagrama
        # e a página inteira que virou imagem (item 4 da revisão de
        # 2026-09-18). Saíam como `<figure data-fen="None">` com a legenda
        # cheia de JSON, porque toda `livro.Figura` chegava aqui como diagrama.
        encoded, origem_da_imagem = imagem_do_diagrama(block)
        rotulo = html.escape(str(value.get("warning") or "") or (
            "Cabeçalho do diagrama" if block.kind == "caption" else "Figura"),
            quote=True)
        corpo = (f'<img alt="{rotulo}" src="data:image/png;base64,{encoded}">'
                 if encoded else f"<figcaption>{rotulo}</figcaption>")
        body = f'<figure{common} data-image="{origem_da_imagem}">{corpo}</figure>'
    elif block.kind == "caption":
        body = f'<p{common} class="caption">{html.escape(_text(value))}</p>'
    elif block.kind == "table" and isinstance(value, Mapping):
        rows = value.get("rows", ())
        body = (f"<table{common}>" + "".join(
            "<tr>" + "".join(
                "<td>" + "<br/>".join(html.escape(linha) for linha in _text(cell).split("\n"))
                + "</td>" for cell in row) + "</tr>"
            for row in rows) + "</table>")
    elif block.kind == "page_break":
        body = f'<hr{common} class="page-break">'
    else:
        body = f"<p{common}>{_com_negrito(_text(value), block)}</p>"
    return body + _audit(block, options)


def _html_body(document: EditorialDocument, options: ExportOptions) -> str:
    pages = []
    for page in sorted(document.pages, key=lambda item: item.page_index):
        blocks = "\n".join(_block_html(block, options)
                             for block in sorted(page.blocks, key=lambda item: item.order))
        pages.append(f'<section id="page-{page.page_index + 1}" data-page="{page.page_index + 1}">{blocks}</section>')
    title = html.escape(options.title or document.title)
    language = html.escape(document.language or "und", quote=True)
    return (f'<!doctype html><html lang="{language}"><head><meta charset="utf-8">'
            f"<title>{title}</title><meta name=\"export-mode\" content=\"{options.mode}\">"
            "<link rel=\"stylesheet\" href=\"styles.css\"></head><body>"
            f'<main data-mode="{options.mode}"><h1>{title}</h1>{"".join(pages)}</main>'
            "</body></html>\n")


def _text_document(document: EditorialDocument) -> str:
    lines: list[str] = []
    for page in sorted(document.pages, key=lambda item: item.page_index):
        for block in sorted(page.blocks, key=lambda item: item.order):
            texto = texto_do_bloco(block)
            if texto:
                lines.append(texto)
    return "\n\n".join(lines) + "\n"


def avisos_dos_diagramas(document: EditorialDocument) -> tuple[str, ...]:
    """
    Os diagramas que saíram sem imagem, e os que saíram sem revisão.

    O primeiro é defeito — uma figura vazia no livro entregue —, e o segundo é
    estado: o relatório da exportação é onde quem operou o livro descobre
    quantas posições ninguém conferiu, sem ter de abrir o arquivo.
    """
    sem_imagem: list[str] = []
    pendentes = 0
    for page in document.pages:
        for block in page.blocks:
            if block.kind != "diagram":
                continue
            if not imagem_do_diagrama(block)[0]:
                sem_imagem.append(block.id)
            pendentes += revisao_pendente(block)
    avisos = []
    if sem_imagem:
        avisos.append(f"{len(sem_imagem)} diagrama(s) sem imagem: "
                      + ", ".join(sem_imagem[:5])
                      + ("…" if len(sem_imagem) > 5 else ""))
    if pendentes:
        avisos.append(f"{pendentes} diagrama(s) exportados sem revisão")
    return tuple(avisos)


def _gravar_atomico(caminho: Path, conteudo: str) -> None:
    """Grava num temporário ao lado e troca: uma falha no meio não deixa meio
    arquivo no lugar do que havia (era como a fachada gravava o TXT)."""
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(conteudo, encoding="utf-8")
    temporario.replace(caminho)


class EditorialExporter:
    """Exportador único: todos os destinos percorrem a mesma ordem de blocos."""

    def export(self, document: EditorialDocument, target: str | Path,
               options: ExportOptions | None = None) -> ExportReport:
        options = options or ExportOptions()
        caminho = Path(target)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        if options.format == "html":
            _gravar_atomico(caminho, _html_body(document, options))
            return ExportReport("html", (str(caminho),),
                                warnings=avisos_dos_diagramas(document),
                                metadata={"mode": options.mode})
        if options.format == "txt":
            _gravar_atomico(caminho, _text_document(document))
            return ExportReport("txt", (str(caminho),))
        if options.format == "json":
            document.save_json(caminho)
            return ExportReport("json", (str(caminho),), metadata={"schema": document.schema})
        if options.format in ("epub", "docx"):
            return self._pelo_escritor_de_producao(document, caminho, options)
        return self._pdf(document, caminho, options)

    def _pelo_escritor_de_producao(self, document: EditorialDocument, target: Path,
                                   options: ExportOptions) -> ExportReport:
        """
        EPUB e DOCX pelo escritor de produção, `exportar.exportar` (PD-21).

        As páginas vêm de `options.paginas` — as do leitor, com a revisão do
        documento já aplicada pela fachada — ou de volta do IR
        (`aplicar_revisao` sem páginas: a volta sem perdas do adapter, mais o
        redesenho do diagrama cujo FEN a revisão trocou ou que chegou sem
        desenho), que é o caminho do documento gravado noutra sessão e do IR que
        não veio do leitor. É o mesmo escritor da exportação de livro: embute a
        fonte dos símbolos, redesenha os diagramas, numera as páginas em
        arquivos próprios e carimba no `alt` e na legenda o lado a jogar e o
        "não revisado" (`Figura.revisao_pendente`). O título e o autor saem do
        PDF de origem quando `escritor` não os traz.
        """
        from core import exportar, livro
        from core.editorial_legacy import aplicar_revisao

        paginas = list(options.paginas) or aplicar_revisao([], document, opcoes=options.figura)
        escritor = dict(options.escritor)
        if "titulo" not in escritor:
            titulo, autor = options.title or document.title, ""
            origem = str(document.metadata.get("source_path") or "")
            if origem.lower().endswith(".pdf"):
                try:
                    titulo, autor = livro.titulo_e_autor(origem)
                except (OSError, RuntimeError, ValueError) as erro:
                    log.info("título e autor não lidos de %s (%s); fica o do documento",
                             origem, erro)
            escritor["titulo"] = titulo
            escritor.setdefault("autor", autor)
        escritor.setdefault("idioma", document.language)
        exportar.exportar(paginas, str(target), formato=options.format, **escritor)
        return ExportReport(options.format, (str(target),),
                            warnings=avisos_dos_diagramas(document),
                            metadata={"mode": options.mode, "escritor": "exportar",
                                      "paginas": "leitor" if options.paginas else "ir"})

    def _pdf(self, document: EditorialDocument, target: Path,
             options: ExportOptions) -> ExportReport:
        source = options.source_pdf or document.metadata.get("source_path")
        source_path = Path(source) if source else None
        if source_path and source_path.exists() and source_path.suffix.casefold() == ".pdf":
            pdf = fitz.open(source_path)
            while len(pdf) < len(document.pages):
                pdf.new_page()
        else:
            pdf = fitz.open()
            for _ in document.pages:
                pdf.new_page(width=612, height=792)
        text_items = 0
        failed_items = 0
        warnings: list[str] = []
        # A camada é escrita na fonte de xadrez do `searchable_pdf`, e não na
        # Helvetica padrão: nela o PyMuPDF troca cada figurina por `·` sem
        # avisar, e `2.♘f3` não era achado pela busca do PDF (item 10).
        try:
            from core.chess_pdf_processor import resolve_chess_font
            fonte_da_camada = resolve_chess_font()
        except Exception as error:  # noqa: BLE001 — sem fonte, a camada sai assim mesmo
            fonte_da_camada = None
            warnings.append(f"sem fonte de xadrez para a camada de texto ({error}); "
                            "as figurinas saem como ·")
        escrita = {"fontname": FONTE_DA_CAMADA} if fonte_da_camada else {}
        for page_model in sorted(document.pages, key=lambda item: item.page_index):
            if page_model.page_index >= len(pdf):
                # Página fora do PDF: contada como falha e anunciada — o
                # `continue` mudo deixava página em branco com "0 falhas".
                failed_items += len(page_model.blocks)
                warnings.append(f"página {page_model.page_index} fora do PDF "
                                f"({len(pdf)} páginas)")
                continue
            page = pdf[page_model.page_index]
            if fonte_da_camada:
                page.insert_font(fontname=FONTE_DA_CAMADA, fontfile=fonte_da_camada)
            # As caixas do IR estão em **pixels do raster**; a página do PDF
            # está em pontos. A escala é a largura da página sobre a largura da
            # imagem, e `72/dpi` quando a largura não foi gravada. Sem ela a
            # caixa a 300 dpi caía 4,17× fora da página.
            largura_imagem = page_model.metadata.get("image_width")
            dpi = float(page_model.metadata.get("dpi") or 300)
            escala = (page.rect.width / float(largura_imagem)
                      if largura_imagem else 72.0 / dpi)
            y = 40.0
            for block in sorted(page_model.blocks, key=lambda item: item.order):
                text = texto_do_bloco(block)
                if not text:
                    continue
                ref = block.source_refs[0] if block.source_refs else None
                try:
                    if ref and ref.bbox and source_path:
                        x, y0, x2, y2 = (float(v) * escala for v in ref.bbox)
                        rect = fitz.Rect(x, y0, x2, y2) & page.rect
                        if rect.is_empty:
                            raise ValueError("caixa fora da página")
                        # O bloco é um parágrafo inteiro numa caixa: a camada
                        # tem de caber **dentro** dela, em várias linhas, senão
                        # a busca só acha o que sobrou na primeira. O corpo é o
                        # maior em que o texto cabe; `insert_textbox` devolve
                        # negativo quando não coube.
                        for tamanho in (14, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3):
                            if page.insert_textbox(rect, text, fontsize=tamanho,
                                                   render_mode=3, **escrita) >= 0:
                                break
                        else:
                            # A caixa veio da altura do glifo na imagem. Em
                            # linhas muito curtas, a conversão de pixels para
                            # pontos pode deixá-la menor que a altura mínima
                            # do PDF, embora o texto ainda seja válido. A
                            # camada é invisível: aumentá-la para baixo
                            # preserva a busca sem alterar um pixel da página.
                            altura_minima = min(
                                max(rect.y1, rect.y0 + 8.0), page.rect.y1)
                            caixa_fallback = fitz.Rect(
                                rect.x0, rect.y0, rect.x1, altura_minima)
                            for tamanho in (3, 2, 1):
                                if page.insert_textbox(
                                        caixa_fallback, text,
                                        fontsize=tamanho, render_mode=3,
                                        **escrita) >= 0:
                                    break
                            else:
                                raise ValueError(
                                    "texto não coube na caixa do bloco")
                        y = max(y, rect.y1 + 8)
                    else:
                        # Sem caixa a camada continua **invisível** (`render_mode=3`)
                        # sobre o scan: texto visível por cima da imagem original
                        # é o que o formato "pesquisável" existe para não fazer.
                        # Só o PDF criado do zero, sem imagem, recebe texto visível.
                        page.insert_text((40, y), text, fontsize=11,
                                         render_mode=3 if source_path else 0, **escrita)
                        y += 18 * max(1, text.count("\n") + 1)
                except Exception as error:  # noqa: BLE001 — contada, e o resto segue
                    failed_items += 1
                    warnings.append(f"bloco {block.id}: {type(error).__name__}: {error}")
                    continue
                text_items += 1
        pdf.save(target)
        pdf.close()
        return ExportReport("pdf", (str(target),), warnings=tuple(warnings), metadata={
            "pages": len(document.pages), "text_items": text_items,
            "failed_items": failed_items, "mode": options.mode,
        })

    @staticmethod
    def validate_output(path: str | Path, format: str) -> tuple[str, ...]:
        """Validação estrutural barata para CI e pré-visualização."""
        target = Path(path)
        formato = format.casefold().lstrip(".")
        errors: list[str] = []
        if not target.exists() or target.stat().st_size == 0:
            errors.append("arquivo de saída inexistente ou vazio")
        elif formato == "epub":
            try:
                with zipfile.ZipFile(target) as archive:
                    if archive.namelist()[0] != "mimetype":
                        errors.append("EPUB deve iniciar com mimetype")
                    nomes = archive.namelist()
                    if "OEBPS/content.opf" not in nomes or not any(
                            nome.endswith(".xhtml") for nome in nomes):
                        errors.append("EPUB sem content.opf ou sem página XHTML")
            except zipfile.BadZipFile:
                errors.append("EPUB inválido")
        elif formato == "pdf":
            try:
                doc = fitz.open(target)
                if not len(doc):
                    errors.append("PDF sem páginas")
                doc.close()
            except Exception:
                errors.append("PDF inválido")
        return tuple(errors)
