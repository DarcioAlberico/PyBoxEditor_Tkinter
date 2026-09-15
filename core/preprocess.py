"""
Pré-processamento de imagem para detecção de caracteres.

Substitui o threshold fixo em 180 que estava replicado por três módulos. Um
valor fixo funciona numa página limpa e falha em scan com iluminação irregular
— o caso normal em livro digitalizado, onde a borda da página costuma ficar
mais escura que o miolo.

A binarização Otsu daqui veio de `core/opencv_autobox.py`, módulo que nunca foi
importado por ninguém e caiu na F5.1 (`git show 6a4b7a1:core/opencv_autobox.py`).
Ele já tinha a lógica melhor que a em uso.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

import cv2
import numpy as np


METODOS = ("auto", "otsu", "adaptive", "fixed")


@dataclass(frozen=True)
class PreprocessConfig:
    """Configuração do gerador de variantes de uma página."""

    target_dpi: int = 300
    source_dpi: int = 0
    deskew: bool = True
    max_angle: float = 15.0
    denoise: bool = True
    illumination: bool = True
    methods: tuple[str, ...] = ("auto", "adaptive", "otsu")

    def __post_init__(self) -> None:
        if self.target_dpi <= 0:
            raise ValueError("target_dpi deve ser positivo")
        invalidos = set(self.methods) - set(METODOS)
        if invalidos:
            raise ValueError(f"métodos inválidos: {sorted(invalidos)}")


@dataclass
class PageEvidence:
    """Evidências usadas para escolher a variante mais promissora."""

    ink_fraction: float
    plausible_ink: bool
    components: int
    median_height: float


@dataclass
class ImageVariant:
    """Imagem candidata e as evidências que justificaram sua seleção."""

    name: str
    image: np.ndarray
    binary: np.ndarray
    angle: float = 0.0
    method: str = "auto"
    score: float = 0.0
    evidence: Optional[PageEvidence] = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _cinza(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    return img


# Fração de pixels de tinta que uma página de texto pode plausivelmente ter.
# Texto corrido fica em torno de 3–15%; acima de 35% não é texto, é mancha.
TINTA_PLAUSIVEL = (0.0005, 0.35)


def fracao_de_tinta(img_bin: np.ndarray) -> float:
    return float((img_bin > 0).mean())


def tinta_plausivel(img_bin: np.ndarray) -> bool:
    """
    O resultado da binarização parece texto?

    Este é o critério de escolha do modo "auto", e ele avalia o **resultado**,
    não o histograma. A primeira versão testava bimodalidade do histograma e
    errava justamente no caso que interessa: numa página com sombra de
    encadernação, o Otsu separa "metade escura" de "metade clara" — duas
    classes perfeitamente bimodais — e devolve 47% de tinta, o que não segmenta
    nada. Medido nesse cenário: limiar fixo 61%, Otsu 48%, adaptativo 3%.
    """
    return TINTA_PLAUSIVEL[0] <= fracao_de_tinta(img_bin) <= TINTA_PLAUSIVEL[1]


def binarize(img: np.ndarray, method: str = "auto",
             fixed_threshold: int = 180) -> np.ndarray:
    """
    Binariza deixando a tinta em branco (255) e o fundo em preto — o formato
    que `cv2.findContours` espera.

    auto     — Otsu se o histograma for bimodal, senão adaptativo
    otsu     — sempre Otsu
    adaptive — threshold adaptativo gaussiano (iluminação irregular)
    fixed    — limiar fixo (comportamento antigo, mantido para comparação)
    """
    if method not in METODOS:
        raise ValueError(f"método inválido: {method!r} (use um de {METODOS})")

    cinza = _cinza(img)

    if method == "auto":
        # Tenta o Otsu e confere se o que saiu parece texto. Se não parece,
        # cai no adaptativo, que lida com iluminação irregular.
        _, otsu = cv2.threshold(cinza, 0, 255,
                                cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        if tinta_plausivel(otsu):
            return otsu
        method = "adaptive"

    if method == "otsu":
        _, th = cv2.threshold(cinza, 0, 255,
                              cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return th

    if method == "adaptive":
        # Janela ímpar e proporcional à página: pequena demais recorta o miolo
        # dos glifos, grande demais volta a se comportar como limiar global.
        lado = max(15, (min(cinza.shape[:2]) // 20) | 1)
        return cv2.adaptiveThreshold(
            cinza, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, lado, 10)

    _, th = cv2.threshold(cinza, fixed_threshold, 255, cv2.THRESH_BINARY_INV)
    return th


def deskew(img: np.ndarray, max_angle: float = 15.0) -> Tuple[np.ndarray, float]:
    """
    Corrige inclinação da página. Devolve (imagem, ângulo aplicado em graus).

    Mede pelo retângulo de área mínima que envolve os pixels de tinta. Só
    corrige dentro de `max_angle`: acima disso a estimativa provavelmente pegou
    um diagrama ou a borda da página, e girar pioraria.
    """
    cinza = _cinza(img)
    tinta = binarize(cinza, "otsu")

    pontos = cv2.findNonZero(tinta)
    if pontos is None or len(pontos) < 50:
        return img, 0.0

    angulo = cv2.minAreaRect(pontos)[-1]
    if angulo < -45:
        angulo += 90
    elif angulo > 45:
        angulo -= 90

    if abs(angulo) < 0.1 or abs(angulo) > max_angle:
        return img, 0.0

    h, w = cinza.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angulo, 1.0)
    girada = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC,
                            borderMode=cv2.BORDER_REPLICATE)
    return girada, float(angulo)


def denoise(img_bin: np.ndarray, fracao_minima: float = 0.02) -> np.ndarray:
    """
    Remove partículas pequenas demais para serem caractere.

    O limiar é relativo à altura mediana dos componentes da própria página, não
    um número absoluto: o mesmo livro escaneado a 150 e a 300 dpi tem sujeira
    de tamanhos diferentes.
    """
    n, _, stats, _ = cv2.connectedComponentsWithStats(img_bin, connectivity=8)
    if n <= 2:
        return img_bin

    alturas = sorted(stats[1:, cv2.CC_STAT_HEIGHT])
    mediana = alturas[len(alturas) // 2] or 1
    area_minima = max(2.0, (mediana * fracao_minima) ** 2)

    saida = img_bin.copy()
    _, labels, stats, _ = cv2.connectedComponentsWithStats(img_bin, connectivity=8)
    for i in range(1, len(stats)):
        if stats[i, cv2.CC_STAT_AREA] < area_minima:
            saida[labels == i] = 0
    return saida


# Fração da página que a caixa de um componente pode ocupar e ele ainda contar
# como caractere na hora de medir a escala. Um 'M' a 300 dpi ocupa 0,05% de uma
# página A5; um tabuleiro ocupa 6%, e uma trama soldada, 20%.
FRACAO_MAXIMA_DE_CARACTERE = 0.01

# Altura de componente, em frações da escala de texto, abaixo da qual ele é
# candidato a trama. Não decide sozinho — ver `remover_textura`.
TEXTURA_ALTURA = 0.25

# Quanto mais claro que o texto o componente tem de ser para ser trama.
# **Foi lido de uma tabela, não escolhido.** Medido em 6 páginas do Yusupov, com
# o corte em tom_do_texto + X:
#
#     X    componentes de trama removidos   componentes do tamanho de letra
#     20              20.603 (pág 17)                   25, 83, 22, 39, 149
#     40              16.708                             9,  0,  0,  0,   0
#     60              11.560                             3,  0,  0,  0,   0
#
# Em 40 a trama já foi e o tamanho de letra deixa de ser tocado; abaixo disso a
# margem começa a alcançar glifo de verdade.
TEXTURA_FOLGA_DE_TOM = 40.0


def escala_de_texto(img_bin: np.ndarray) -> int:
    """
    Altura de caractere da página, medida por **massa de tinta**.

    A mediana simples das alturas não serve, e a página do "Scoring" mostra por
    quê: o painel de meio-tom põe 22 mil pontos de 1–3 px na conta e a mediana
    desce para **1**. Todo limiar relativo do pipeline desaba junto — com
    mediana 1, `descartar_blocos_nao_texto` joga fora tudo acima de 4 px, isto
    é, o texto.

    A mediana ponderada pela área de tinta é estável porque o ponto de trama tem
    ~4 px de tinta e uma letra tem ~200: medido nas mesmas 6 páginas, ela dá 31,
    39, 43, 37, 36 e 58 px onde a simples dá 1, 1, 8, 4, 7 e 4.

    **Sobre componentes conexos, e não sobre os contornos externos.** Naquela
    população o diagrama é *um* componente com dezenas de milhares de pixels de
    tinta, e a mediana ponderada aterrissa nele: medido, 390 e 579 px.

    **Bloco fica de fora, e a regra é do domínio: caractere não ocupa 1% de uma
    página.** Sem essa exclusão a ponderação tem um furo — uma trama que soldou
    numa malha só é *um* componente com centenas de milhares de pixels, e ela
    passa a ser a mediana. Nas páginas reais o texto ainda pesava mais que a
    malha (31 px contra os 250 de uma montagem onde ela domina), mas depender
    disso é depender de a página ter texto suficiente em volta.
    """
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(img_bin, connectivity=8)
    if n <= 1:
        return 0

    caixas = (stats[1:, cv2.CC_STAT_WIDTH].astype(np.int64)
              * stats[1:, cv2.CC_STAT_HEIGHT].astype(np.int64))
    de_texto = caixas <= img_bin.size * FRACAO_MAXIMA_DE_CARACTERE
    if not de_texto.any():
        de_texto = np.ones(len(caixas), bool)

    alturas = stats[1:, cv2.CC_STAT_HEIGHT][de_texto]
    areas = stats[1:, cv2.CC_STAT_AREA].astype(np.int64)[de_texto]
    ordem = np.argsort(alturas)
    acumulado = np.cumsum(areas[ordem])
    if acumulado[-1] <= 0:
        return 0
    return int(alturas[ordem][np.searchsorted(acumulado, acumulado[-1] / 2)])


def remover_textura(img: np.ndarray, img_bin: np.ndarray,
                    fator_altura: float = TEXTURA_ALTURA,
                    folga_de_tom: float = TEXTURA_FOLGA_DE_TOM) -> np.ndarray:
    """
    Apaga a trama de meio-tom: o componente que é **pequeno e claro**.

    Livro de xadrez traz painel chapado — o quadro de pontuação no fim de cada
    capítulo, a tarja de cabeçalho — e o escaneamento devolve esse chapado como
    uma nuvem de pontos. Medido na página 18 do *Chess Evolution 1*: 6.765
    contornos, **95,8% deles de 6x6 px ou menos**, e o texto do painel sem um
    box sequer, porque a mediana envenenada fez o descarte de bloco não-texto
    comer os caracteres.

    **As duas condições juntas, e nenhuma sozinha.** Pequeno sozinho apagaria o
    ponto final, o pingo do 'i' e o acento — que medem o mesmo que um ponto de
    trama. Claro sozinho apagaria o texto de tarja cinza e o glifo de tinta
    fraca. Medido, o ponto de trama tem tom mediano de 77–112 contra 20–23 do
    texto da mesma página, e a pontuação de verdade fica em 6–29: ela é pequena,
    mas é **escura**, e é isso que a salva.

    Devolve uma binarização nova; a de entrada não é tocada.
    """
    if img_bin.size == 0:
        return img_bin

    escala = escala_de_texto(img_bin)
    if escala <= 0:
        return img_bin

    cinza = _cinza(img)
    if cinza.shape[:2] != img_bin.shape[:2]:
        return img_bin

    n, labels, stats, _ = cv2.connectedComponentsWithStats(img_bin, connectivity=8)
    if n <= 1:
        return img_bin

    # Tom médio de cada componente, pelos pixels dele — não pela caixa, que
    # traria o papel em volta e apagaria a diferença (medido: 145 contra 150).
    soma = np.bincount(labels.ravel(), weights=cinza.ravel().astype(np.float64),
                       minlength=n)
    quantos = np.bincount(labels.ravel(), minlength=n)
    tom = soma[1:] / np.maximum(quantos[1:], 1)

    alturas = stats[1:, cv2.CC_STAT_HEIGHT]
    larguras = stats[1:, cv2.CC_STAT_WIDTH]
    piso = escala * fator_altura
    pequeno = (alturas <= piso) & (larguras <= piso)
    if not pequeno.any() or pequeno.all():
        # Página só de trama não tem texto com que comparar: não mexer.
        return img_bin

    tom_do_texto = float(np.median(tom[~pequeno]))
    trama = pequeno & (tom >= tom_do_texto + folga_de_tom)
    if not trama.any():
        return img_bin

    manter = np.ones(n, dtype=np.uint8)
    manter[1:][trama] = 0
    return img_bin * manter[labels]


def normalize_dpi(img: np.ndarray, source_dpi: int,
                  target_dpi: int = 300) -> np.ndarray:
    """Reamostra para o DPI em que o modelo foi treinado."""
    if source_dpi <= 0 or source_dpi == target_dpi:
        return img
    escala = target_dpi / source_dpi
    interp = cv2.INTER_AREA if escala < 1 else cv2.INTER_CUBIC
    return cv2.resize(img, None, fx=escala, fy=escala, interpolation=interp)


def preparar_pagina(img: np.ndarray, method: str = "auto",
                    corrigir_inclinacao: bool = True,
                    limpar_ruido: bool = True) -> Tuple[np.ndarray, float]:
    """
    Pipeline completo. Devolve (imagem binária, ângulo corrigido).

    Ordem: deskew → binarize → denoise. O deskew vem antes porque gira a imagem
    em tons de cinza, onde a interpolação não cria degraus na tinta.
    """
    angulo = 0.0
    if corrigir_inclinacao:
        img, angulo = deskew(img)

    binaria = binarize(img, method)

    if limpar_ruido:
        binaria = denoise(binaria)

    return binaria, angulo


def normalizar_iluminacao(img: np.ndarray, tamanho_fundo: int = 51) -> np.ndarray:
    """Remove variações lentas de iluminação preservando a tinta.

    A estimativa do fundo é obtida por um blur gaussiano grande e a imagem é
    corrigida por divisão. O tamanho é sempre ímpar e limitado para que páginas
    pequenas não produzam uma janela inválida.
    """
    cinza = _cinza(img)
    if cinza.size == 0:
        return cinza.copy()
    lado = max(3, int(tamanho_fundo) | 1)
    limite = min(cinza.shape[:2])
    if limite < 3:
        return cinza.copy()
    lado = min(lado, limite if limite % 2 else limite - 1)
    fundo = cv2.GaussianBlur(cinza, (lado, lado), 0).astype(np.float32)
    corrigida = cinza.astype(np.float32) * 190.0 / np.maximum(fundo, 1.0)
    return np.clip(corrigida, 0, 255).astype(np.uint8)


def corrigir_perspectiva(img: np.ndarray,
                         pontos: Optional[Sequence[Sequence[float]]] = None
                         ) -> np.ndarray:
    """Retifica um quadrilátero, quando seus quatro cantos forem conhecidos.

    Sem pontos, a função é deliberadamente um no-op: detectar bordas da página
    automaticamente sem confiança pode cortar diagramas e margens. A detecção
    automática de cantos pertence à fase de layout.
    """
    if pontos is None:
        return img
    if len(pontos) != 4:
        raise ValueError("perspectiva exige exatamente quatro pontos")
    src = np.asarray(pontos, dtype=np.float32)
    if src.shape != (4, 2):
        raise ValueError("pontos devem ter formato 4x2")
    largura = int(max(np.linalg.norm(src[1] - src[0]),
                      np.linalg.norm(src[2] - src[3])))
    altura = int(max(np.linalg.norm(src[3] - src[0]),
                     np.linalg.norm(src[2] - src[1])))
    if largura < 2 or altura < 2:
        raise ValueError("quadrilátero degenerado")
    destino = np.array([[0, 0], [largura - 1, 0],
                        [largura - 1, altura - 1], [0, altura - 1]],
                       dtype=np.float32)
    matriz = cv2.getPerspectiveTransform(src, destino)
    return cv2.warpPerspective(img, matriz, (largura, altura),
                               flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)


def evidencias(img_bin: np.ndarray) -> PageEvidence:
    """Extrai sinais baratos e independentes do reconhecedor."""
    if img_bin.size == 0:
        return PageEvidence(0.0, False, 0, 0.0)
    n, _labels, stats, _centros = cv2.connectedComponentsWithStats(
        img_bin, connectivity=8)
    alturas = stats[1:, cv2.CC_STAT_HEIGHT] if n > 1 else np.array([])
    positivas = alturas[alturas > 0]
    mediana = float(np.median(positivas)) if len(positivas) else 0.0
    return PageEvidence(fracao_de_tinta(img_bin), tinta_plausivel(img_bin),
                        max(0, n - 1), mediana)


def pontuar_evidencias(ev: PageEvidence) -> float:
    """Pontua uma máscara sem favorecer páginas excessivamente fragmentadas."""
    if not ev.plausible_ink:
        return -1.0
    # O pico fica no centro da faixa plausível. O termo de componentes evita
    # aceitar uma nuvem de ruído que por acaso tenha fração de tinta adequada.
    centro = sum(TINTA_PLAUSIVEL) / 2
    faixa = (TINTA_PLAUSIVEL[1] - TINTA_PLAUSIVEL[0]) / 2
    tinta = max(0.0, 1.0 - abs(ev.ink_fraction - centro) / faixa)
    componentes = min(1.0, ev.components / 20_000) if ev.components else 0.0
    altura = min(1.0, ev.median_height / 10.0) if ev.median_height else 0.0
    return 0.55 * tinta + 0.30 * componentes + 0.15 * altura


def gerar_variantes(img: np.ndarray, config: Optional[PreprocessConfig] = None,
                    pontos_perspectiva: Optional[Sequence[Sequence[float]]] = None
                    ) -> List[ImageVariant]:
    """Gera variantes controladas, sem executar OCR.

    Todas as variantes mantêm a mesma orientação e resolução. A transformação
    geométrica ocorre antes da binarização para não criar degraus artificiais.
    """
    config = config or PreprocessConfig()
    if not isinstance(img, np.ndarray) or img.size == 0:
        raise ValueError("imagem precisa ser um ndarray não vazio")
    normalizada = normalize_dpi(img, config.source_dpi, config.target_dpi)
    normalizada = corrigir_perspectiva(normalizada, pontos_perspectiva)
    if config.deskew:
        alinhada, angulo = deskew(normalizada, config.max_angle)
    else:
        alinhada, angulo = normalizada, 0.0
    cinza = _cinza(alinhada)
    variantes: List[ImageVariant] = []
    fontes = [("base", cinza)]
    if config.illumination:
        fontes.append(("illumination", normalizar_iluminacao(cinza)))
    for nome, fonte in fontes:
        for metodo in config.methods:
            binaria = binarize(fonte, metodo)
            if config.denoise:
                binaria = denoise(binaria)
            ev = evidencias(binaria)
            variantes.append(ImageVariant(
                name=f"{nome}_{metodo}", image=fonte, binary=binaria,
                angle=angulo, method=metodo, score=pontuar_evidencias(ev),
                evidence=ev,
                metadata={"target_dpi": config.target_dpi,
                          "source_dpi": config.source_dpi,
                          "illumination": nome == "illumination"},
            ))
    return variantes


def selecionar_variante(variantes: Sequence[ImageVariant]) -> ImageVariant:
    """Seleciona a variante por score, preservando a ordem em caso de empate."""
    if not variantes:
        raise ValueError("nenhuma variante disponível")
    return max(variantes, key=lambda variante: variante.score)


def preparar_adaptativo(img: np.ndarray, config: Optional[PreprocessConfig] = None,
                        pontos_perspectiva: Optional[Sequence[Sequence[float]]] = None,
                        trace: Any = None) -> ImageVariant:
    """Atalho do pipeline adaptativo: gera, pontua e escolhe uma variante."""
    variantes = gerar_variantes(img, config, pontos_perspectiva)
    if trace is not None:
        trace.event("preprocess_start", variants=len(variantes),
                    target_dpi=(config or PreprocessConfig()).target_dpi)
        for indice, variante in enumerate(variantes):
            ev = variante.evidence
            trace.event("variant", index=indice, variant_name=variante.name,
                        method=variante.method, angle=variante.angle,
                        score=variante.score,
                        evidence=(vars(ev) if ev is not None else None))
            trace.save_image(f"variants/{indice:02d}_{variante.name}.png",
                             variante.binary)
    escolhida = selecionar_variante(variantes)
    if trace is not None:
        trace.event("variant_selected", variant_name=escolhida.name,
                    score=escolhida.score, angle=escolhida.angle)
    return escolhida
