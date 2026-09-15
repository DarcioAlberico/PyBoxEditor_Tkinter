"""Análise geométrica inicial do layout de uma página OCR.

Este módulo trabalha antes do reconhecimento de texto. Ele detecta linhas a
partir da máscara de tinta, agrupa linhas em blocos, identifica colunas e
produz uma ordem de leitura determinística. A classificação semântica é
conservadora: quando a geometria não permite decidir, a região fica como
``body`` ou ``unknown`` em vez de inventar uma tabela ou diagrama.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import cv2
import numpy as np

from core.ocr_result import RegionResult


@dataclass(frozen=True)
class LayoutConfig:
    min_line_width: int = 8
    min_line_height: int = 2
    horizontal_kernel_fraction: float = 0.025
    max_gap_lines: float = 2.2
    column_gap_fraction: float = 0.04
    header_fraction: float = 0.10
    footer_fraction: float = 0.90

    def __post_init__(self) -> None:
        if self.min_line_width < 1 or self.min_line_height < 1:
            raise ValueError("limites mínimos devem ser positivos")
        if not 0.0 < self.horizontal_kernel_fraction <= 1.0:
            raise ValueError("fração do kernel deve estar entre 0 e 1")
        if self.max_gap_lines <= 0:
            raise ValueError("max_gap_lines deve ser positivo")


@dataclass(frozen=True)
class DetectedLine:
    x1: int
    y1: int
    x2: int
    y2: int
    column: int = 0

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2


@dataclass
class PageLayout:
    width: int
    height: int
    regions: list[RegionResult] = field(default_factory=list)
    lines: list[DetectedLine] = field(default_factory=list)
    columns: list[tuple[int, int]] = field(default_factory=list)
    reading_order: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "regions": [region.__dict__.copy() for region in self.regions],
            "lines": [line.__dict__.copy() for line in self.lines],
            "columns": [list(coluna) for coluna in self.columns],
            "reading_order": list(self.reading_order),
            "warnings": list(self.warnings),
        }


def _mascara(binaria: np.ndarray) -> np.ndarray:
    if not isinstance(binaria, np.ndarray) or binaria.size == 0:
        raise ValueError("máscara precisa ser um ndarray não vazio")
    if binaria.ndim == 3:
        binaria = cv2.cvtColor(binaria, cv2.COLOR_RGB2GRAY)
    if binaria.ndim != 2:
        raise ValueError("máscara precisa ser 2D")
    return np.where(binaria > 0, 255, 0).astype(np.uint8)


def detectar_linhas(binaria: np.ndarray,
                    config: Optional[LayoutConfig] = None) -> list[DetectedLine]:
    """Detecta linhas por conexão horizontal de glifos próximos."""
    config = config or LayoutConfig()
    mascara = _mascara(binaria)
    altura, largura = mascara.shape
    kernel_largura = max(config.min_line_width,
                         int(largura * config.horizontal_kernel_fraction))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT,
                                       (kernel_largura, max(1, altura // 300)))
    conectada = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, kernel)
    conectada = cv2.dilate(conectada, np.ones((2, 3), np.uint8), iterations=1)
    n, _labels, stats, _centros = cv2.connectedComponentsWithStats(conectada, 8)
    linhas = []
    for stat in stats[1:]:
        x, y, w, h, area = map(int, stat)
        if w >= config.min_line_width and h >= config.min_line_height and area >= w:
            linhas.append(DetectedLine(x, y, x + w, y + h))
    linhas.sort(key=lambda linha: (linha.y1, linha.x1))
    return linhas


def detectar_colunas(linhas: Sequence[DetectedLine], largura: int,
                     config: Optional[LayoutConfig] = None) -> list[tuple[int, int]]:
    """Encontra vãos verticais entre os intervalos das linhas detectadas."""
    config = config or LayoutConfig()
    if not linhas:
        return []
    intervalos = sorted((linha.x1, linha.x2) for linha in linhas)
    unidos: list[list[int]] = []
    for inicio, fim in intervalos:
        if unidos and inicio <= unidos[-1][1]:
            unidos[-1][1] = max(unidos[-1][1], fim)
        else:
            unidos.append([inicio, fim])
    # Um intervalo por coluna pode aparecer fragmentado por linhas curtas.
    # Só abrimos coluna em vãos grandes o bastante para não transformar espaço
    # entre palavras em coluna.
    limiar = max(12, int(largura * config.column_gap_fraction))
    cortes = [0]
    for anterior, atual in zip(unidos, unidos[1:]):
        if atual[0] - anterior[1] >= limiar:
            cortes.append((anterior[1] + atual[0]) // 2)
    if len(cortes) == 1:
        return [(0, largura)]
    cortes.append(largura)
    return [(cortes[i], cortes[i + 1]) for i in range(len(cortes) - 1)]


def atribuir_colunas(linhas: Sequence[DetectedLine],
                     colunas: Sequence[tuple[int, int]]) -> list[DetectedLine]:
    resultado = []
    for linha in linhas:
        centro = linha.center_x
        coluna = min(range(len(colunas)),
                     key=lambda indice: abs(centro - (sum(colunas[indice]) / 2)))
        resultado.append(DetectedLine(linha.x1, linha.y1, linha.x2, linha.y2, coluna))
    return resultado


def _agrupar_regioes(linhas: Sequence[DetectedLine], largura: int,
                     altura: int, config: LayoutConfig) -> list[list[DetectedLine]]:
    por_coluna: dict[int, list[DetectedLine]] = {}
    for linha in linhas:
        por_coluna.setdefault(linha.column, []).append(linha)
    alturas_linhas = [linha.height for linha in linhas]
    referencia = float(np.median(alturas_linhas)) if alturas_linhas else 1.0
    regioes: list[list[DetectedLine]] = []
    for coluna in sorted(por_coluna):
        atual: list[DetectedLine] = []
        for linha in sorted(por_coluna[coluna], key=lambda item: item.y1):
            if atual and linha.y1 - atual[-1].y2 > referencia * config.max_gap_lines:
                regioes.append(atual)
                atual = []
            atual.append(linha)
        if atual:
            regioes.append(atual)
    return regioes


def _tipo_regiao(linhas: Sequence[DetectedLine], altura: int,
                 altura_referencia: float, config: LayoutConfig) -> str:
    topo = min(linha.y1 for linha in linhas)
    base = max(linha.y2 for linha in linhas)
    if topo <= altura * config.header_fraction and len(linhas) <= 2:
        return "header"
    if base >= altura * config.footer_fraction and len(linhas) <= 2:
        return "footer"
    if len(linhas) == 1 and linhas[0].height >= altura_referencia * 1.35:
        return "heading"
    return "body"


def _regiao(linhas: Sequence[DetectedLine], indice: int, altura: int,
            altura_referencia: float, config: LayoutConfig) -> RegionResult:
    x1 = min(linha.x1 for linha in linhas)
    y1 = min(linha.y1 for linha in linhas)
    x2 = max(linha.x2 for linha in linhas)
    y2 = max(linha.y2 for linha in linhas)
    tipo = _tipo_regiao(linhas, altura, altura_referencia, config)
    return RegionResult(
        id=f"region-{indice:04d}", type=tipo, order=indice,
        confidence=0.75, bbox=(x1, y1, x2, y2),
        line_ids=[f"line-{indice:04d}-{pos:03d}" for pos in range(len(linhas))],
        metadata={"column": linhas[0].column, "line_count": len(linhas)},
    )


class LayoutAnalyzer:
    def __init__(self, config: Optional[LayoutConfig] = None):
        self.config = config or LayoutConfig()

    def analyze(self, binaria: np.ndarray, *, trace: Any = None) -> PageLayout:
        mascara = _mascara(binaria)
        altura, largura = mascara.shape
        linhas = detectar_linhas(mascara, self.config)
        colunas = detectar_colunas(linhas, largura, self.config)
        linhas = atribuir_colunas(linhas, colunas)
        regioes_linhas = _agrupar_regioes(linhas, largura, altura, self.config)
        referencia = float(np.median([linha.height for linha in linhas])) if linhas else 1.0
        # A ordem é por coluna e, dentro dela, de cima para baixo. Para regiões
        # de cabeçalho/rodapé, o y continua sendo o desempate dentro da coluna.
        regioes_linhas.sort(key=lambda grupo: (grupo[0].column, grupo[0].y1))
        regioes = [_regiao(grupo, i, altura, referencia, self.config)
                   for i, grupo in enumerate(regioes_linhas)]
        layout = PageLayout(largura, altura, regioes, linhas, colunas,
                            [regiao.id for regiao in regioes])
        if not linhas:
            layout.warnings.append("nenhuma linha textual detectada")
        if trace is not None:
            trace.event("layout_analyzed", width=largura, height=altura,
                        lines=len(linhas), regions=len(regioes),
                        columns=len(colunas), reading_order=layout.reading_order)
            trace.save_json("layout.json", layout.to_dict())
        return layout


def analisar_layout(binaria: np.ndarray, config: Optional[LayoutConfig] = None,
                    *, trace: Any = None) -> PageLayout:
    return LayoutAnalyzer(config).analyze(binaria, trace=trace)
