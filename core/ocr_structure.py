"""Reconstrução geométrica de linhas, palavras e parágrafos.

O módulo recebe glifos já detectados, mas não depende do classificador. Assim,
o texto reconhecido pode ser substituído depois sem perder a estrutura espacial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any, Mapping, Optional, Sequence

from core.ocr_layout import PageLayout
from core.ocr_result import LineResult, WordResult


@dataclass(frozen=True)
class StructureConfig:
    line_tolerance: float = 0.55
    word_gap_factor: float = 0.75
    min_word_gap: float = 2.0
    paragraph_gap_factor: float = 1.8

    def __post_init__(self) -> None:
        if self.line_tolerance <= 0 or self.word_gap_factor <= 0:
            raise ValueError("tolerâncias devem ser positivas")
        if self.min_word_gap < 0 or self.paragraph_gap_factor <= 0:
            raise ValueError("limites devem ser válidos")


@dataclass
class TextStructure:
    lines: list[LineResult] = field(default_factory=list)
    words: list[WordResult] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    paragraph_line_ids: list[list[str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lines": [item.__dict__.copy() for item in self.lines],
            "words": [item.__dict__.copy() for item in self.words],
            "paragraphs": list(self.paragraphs),
            "paragraph_line_ids": [list(item) for item in self.paragraph_line_ids],
            "warnings": list(self.warnings),
        }


def _valor(box: Any, nome: str, padrao: Any = None) -> Any:
    if isinstance(box, Mapping):
        return box.get(nome, padrao)
    return getattr(box, nome, padrao)


def _bbox(box: Any) -> tuple[int, int, int, int]:
    valores = tuple(int(round(float(_valor(box, nome))))
                  for nome in ("x1", "y1", "x2", "y2"))
    if valores[2] <= valores[0] or valores[3] <= valores[1]:
        raise ValueError("box possui bounding box degenerada")
    return valores


def _char(box: Any) -> str:
    return str(_valor(box, "char", _valor(box, "text", "")) or "")


def _confianca(box: Any) -> float:
    valor = float(_valor(box, "confidence", 1.0) or 0.0)
    return min(1.0, max(0.0, valor))


def _centro_y(box: Any) -> float:
    _, y1, _, y2 = _bbox(box)
    return (y1 + y2) / 2


def agrupar_glifos_em_linhas(boxes: Sequence[Any],
                             config: Optional[StructureConfig] = None,
                             layout: Optional[PageLayout] = None
                             ) -> list[list[Any]]:
    """Agrupa boxes por linha usando centro vertical e altura de referência."""
    config = config or StructureConfig()
    validos = [box for box in boxes if _char(box)]
    if not validos:
        return []
    if layout is not None and len(layout.columns) > 1:
        # Uma linha visual pode conter texto em duas colunas com o mesmo y.
        # Divide antes de comparar os centros verticais para que as colunas
        # nunca sejam fundidas numa única linha.
        por_coluna: dict[int, list[Any]] = {}
        for box in validos:
            x1, _, x2, _ = _bbox(box)
            centro = (x1 + x2) / 2
            coluna = min(range(len(layout.columns)),
                         key=lambda i: abs(centro - sum(layout.columns[i]) / 2))
            por_coluna.setdefault(coluna, []).append(box)
        resultado: list[list[Any]] = []
        for coluna in sorted(por_coluna):
            resultado.extend(agrupar_glifos_em_linhas(por_coluna[coluna], config))
        return resultado
    alturas = [_bbox(box)[3] - _bbox(box)[1] for box in validos]
    altura = median(alturas) or 1.0
    linhas: list[list[Any]] = []
    centros: list[float] = []
    for box in sorted(validos, key=lambda item: (_centro_y(item), _bbox(item)[0])):
        centro = _centro_y(box)
        limite = altura * config.line_tolerance
        candidatos = [i for i, base in enumerate(centros)
                      if abs(centro - base) <= limite]
        if not candidatos:
            linhas.append([box])
            centros.append(centro)
            continue
        indice = min(candidatos, key=lambda i: abs(centro - centros[i]))
        linhas[indice].append(box)
        centros[indice] = sum(_centro_y(item) for item in linhas[indice]) / len(linhas[indice])
    for linha in linhas:
        linha.sort(key=lambda item: _bbox(item)[0])
    linhas.sort(key=lambda linha: min(_bbox(item)[1] for item in linha))
    return linhas


def _limiar_espaco(linha: Sequence[Any], config: StructureConfig) -> float:
    larguras = [_bbox(box)[2] - _bbox(box)[0] for box in linha]
    return max(config.min_word_gap, median(larguras) * config.word_gap_factor)


def agrupar_glifos_em_palavras(linha: Sequence[Any], line_id: str,
                               config: Optional[StructureConfig] = None,
                               *, inicio: int = 0
                               ) -> list[WordResult]:
    """Separa palavras por vãos horizontais relativos ao tamanho do glifo."""
    config = config or StructureConfig()
    if not linha:
        return []
    ordenada = sorted(linha, key=lambda item: _bbox(item)[0])
    limiar = _limiar_espaco(ordenada, config)
    grupos: list[list[Any]] = [[]]
    for box in ordenada:
        if grupos[-1]:
            anterior = _bbox(grupos[-1][-1])
            atual = _bbox(box)
            if atual[0] - anterior[2] > limiar:
                grupos.append([])
        grupos[-1].append(box)
    palavras = []
    for numero, grupo in enumerate(grupos, inicio):
        caixas = [_bbox(box) for box in grupo]
        texto = "".join(_char(box) for box in grupo)
        confiancas = [_confianca(box) for box in grupo]
        palavras.append(WordResult(
            id=f"{line_id}-word-{numero:03d}", text=texto,
            confidence=sum(confiancas) / len(confiancas),
            bbox=(min(c[0] for c in caixas), min(c[1] for c in caixas),
                  max(c[2] for c in caixas), max(c[3] for c in caixas)),
            line_id=line_id, source="geometry",
            glyph_ids=[str(_valor(box, "id", f"glyph-{numero}-{pos}"))
                       for pos, box in enumerate(grupo)],
        ))
    return palavras


def _linha_resultado(linha: Sequence[Any], indice: int,
                     palavras: Sequence[WordResult],
                     region_id: Optional[str] = None) -> LineResult:
    caixas = [_bbox(box) for box in linha]
    confiancas = [_confianca(box) for box in linha]
    line_id = f"line-{indice:04d}"
    return LineResult(
        id=line_id, text=" ".join(palavra.text for palavra in palavras),
        confidence=sum(confiancas) / len(confiancas),
        bbox=(min(c[0] for c in caixas), min(c[1] for c in caixas),
              max(c[2] for c in caixas), max(c[3] for c in caixas)),
        region_id=region_id,
        word_ids=[palavra.id for palavra in palavras],
        glyph_ids=[str(_valor(box, "id", f"glyph-{indice}-{pos}"))
                   for pos, box in enumerate(linha)],
    )


def _mesma_coluna(a: LineResult, b: LineResult, layout: Optional[PageLayout]) -> bool:
    if layout is None or not layout.columns:
        return True
    def coluna(line: LineResult) -> int:
        centro = ((line.bbox or (0, 0, 0, 0))[0] + (line.bbox or (0, 0, 0, 0))[2]) / 2
        return min(range(len(layout.columns)),
                   key=lambda i: abs(centro - sum(layout.columns[i]) / 2))
    return coluna(a) == coluna(b)


def construir_estrutura(boxes: Sequence[Any], *,
                        layout: Optional[PageLayout] = None,
                        config: Optional[StructureConfig] = None,
                        trace: Any = None) -> TextStructure:
    """Constrói linhas, palavras e parágrafos em ordem de leitura."""
    config = config or StructureConfig()
    linhas_boxes = agrupar_glifos_em_linhas(boxes, config, layout)
    linhas: list[LineResult] = []
    palavras: list[WordResult] = []
    for indice, linha_boxes in enumerate(linhas_boxes):
        linha_palavras = agrupar_glifos_em_palavras(
            linha_boxes, f"line-{indice:04d}", config)
        palavras.extend(linha_palavras)
        linhas.append(_linha_resultado(linha_boxes, indice, linha_palavras))

    paragrafos: list[str] = []
    ids_paragrafos: list[list[str]] = []
    if linhas:
        alturas = [((linha.bbox or (0, 0, 0, 0))[3]
                    - (linha.bbox or (0, 0, 0, 0))[1]) for linha in linhas]
        altura = median(alturas) or 1.0
        atual: list[LineResult] = []
        for linha in linhas:
            deve_iniciar = bool(atual)
            if atual:
                anterior = atual[-1]
                gap = (linha.bbox or (0, 0, 0, 0))[1] - (anterior.bbox or (0, 0, 0, 0))[3]
                deve_iniciar = (gap > altura * config.paragraph_gap_factor
                                or not _mesma_coluna(anterior, linha, layout))
            if deve_iniciar:
                paragrafos.append(" ".join(item.text for item in atual))
                ids_paragrafos.append([item.id for item in atual])
                atual = []
            atual.append(linha)
        if atual:
            paragrafos.append(" ".join(item.text for item in atual))
            ids_paragrafos.append([item.id for item in atual])
    resultado = TextStructure(linhas, palavras, paragrafos, ids_paragrafos)
    if not boxes:
        resultado.warnings.append("nenhum glifo reconhecido para estruturar")
    if trace is not None:
        trace.event("text_structure", lines=len(linhas), words=len(palavras),
                    paragraphs=len(paragrafos))
        trace.save_json("text_structure.json", resultado.to_dict())
    return resultado
