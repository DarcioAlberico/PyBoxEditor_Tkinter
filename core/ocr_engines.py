"""Adapters opcionais e normalização das respostas dos engines OCR."""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, Protocol

import numpy as np
from PIL import Image

from core.ocr_result import OCRHypothesis


class OCRAdapter(Protocol):
    name: str

    def recognize(self, image: Any, *, level: str = "line") -> OCRHypothesis:
        """Reconhece uma imagem como linha ou palavra."""


def _resultado(valor: Any, source: str, *, level: str) -> OCRHypothesis:
    if isinstance(valor, OCRHypothesis):
        return valor
    if isinstance(valor, tuple) and len(valor) >= 2:
        texto, confianca = valor[:2]
    else:
        texto, confianca = valor, 0.0
    return OCRHypothesis(str(texto or "").strip(), float(confianca or 0.0), source,
                         metadata={"level": level})


def _caminhos_de_linha(model_path: str | None,
                       meta_path: str | None) -> tuple[str, str]:
    """O modelo de linha pedido, ou o de `config.paths` (`completar_modelo_linha`)
    no que faltar — o que veio passa como veio."""
    if model_path is None or meta_path is None:
        from config.paths import completar_modelo_linha
        modelo, meta = completar_modelo_linha(model_path, meta_path)
        model_path = str(modelo) if model_path is None else model_path
        meta_path = str(meta) if meta_path is None else meta_path
    return str(model_path), str(meta_path)


class CallableAdapter:
    """Adapter pequeno para funções reais e doubles de teste."""

    def __init__(self, name: str, recognizer: Callable[..., Any], *,
                 line_recognizer: Callable[..., Any] | None = None,
                 metadata: dict[str, Any] | None = None):
        self.name = name
        self._recognizer = recognizer
        self._line_recognizer = line_recognizer
        self.metadata = dict(metadata or {})

    def recognize(self, image: Any, *, level: str = "line") -> OCRHypothesis:
        func = self._line_recognizer if level == "line" and self._line_recognizer else self._recognizer
        resultado = _resultado(func(image), self.name, level=level)
        resultado.metadata.update(self.metadata)
        return resultado


class OCRServiceAdapters:
    """Fábrica dos adapters que usam os métodos já existentes de OCRService."""

    @staticmethod
    def easyocr(service: Any, *, languages: tuple[str, ...] = ("en",), gpu: bool = False) -> CallableAdapter:
        return CallableAdapter(
            "easyocr",
            lambda image: service.easyocr_ocr_conf(image, languages, gpu),
            line_recognizer=lambda image: service.easyocr_linha_conf(image, languages, gpu),
            metadata={"engine": "easyocr", "line_model": True},
        )

    @staticmethod
    def paddleocr(service: Any, *, language: str = "en", gpu: bool = False) -> CallableAdapter:
        return CallableAdapter(
            "paddleocr",
            lambda image: service.paddleocr_ocr_conf(image, language, gpu),
            # TextRecognition é usado aqui em recorte controlado. A versão atual
            # do serviço ainda devolve um caractere; o metadata impede que a
            # fusão confunda isso com uma leitura de linha completa.
            line_recognizer=lambda image: service.paddleocr_linha_conf(image, language, gpu),
            metadata={"engine": "paddleocr", "line_model": True,
                      "line_mode": "full_line"},
        )

    @staticmethod
    def tesseract(service: Any, *, language: str = "en") -> CallableAdapter:
        # O idioma chega ao Tesseract como chega ao EasyOCR e ao PaddleOCR:
        # sem ele, `registry(language="pt")` configurava os dois em portugues
        # e o Tesseract lia sempre em ingles, sem aviso.
        return CallableAdapter(
            "tesseract",
            lambda image: service.tesseract_ocr_conf(
                image if isinstance(image, Image.Image) else Image.fromarray(np.asarray(image))),
            line_recognizer=lambda image: service.tesseract_linha_conf(
                np.asarray(image), language),
            metadata={"engine": "tesseract", "line_model": True,
                      "line_mode": "full_line", "language": language},
        )

    @staticmethod
    def neural(service: Any, predictor: Any) -> CallableAdapter:
        return CallableAdapter(
            "neural",
            lambda image: service.neural_ocr(np.asarray(image), predictor),
            metadata={"engine": "custom_neural", "line_model": False},
        )

    @staticmethod
    def trained_line(service: Any, *, model_path: str | None = None,
                     meta_path: str | None = None) -> CallableAdapter:
        """Adapta o CRNN/CTC local ao contrato comum de linha."""
        model_path, meta_path = _caminhos_de_linha(model_path, meta_path)
        return CallableAdapter(
            "trained_line",
            lambda image: service.linha_treinada_conf(image, model_path, meta_path),
            line_recognizer=lambda image: service.linha_treinada_conf(
                image, model_path, meta_path),
            metadata={"engine": "custom_neural", "line_model": True,
                      "line_mode": "full_line", "model_path": model_path},
        )

    @staticmethod
    def learner(service: Any, learner: Any) -> CallableAdapter:
        return CallableAdapter(
            "learner",
            lambda image: service.learner_ocr(np.asarray(image), learner),
            metadata={"engine": "knn", "line_model": False},
        )

    @staticmethod
    def registry(service: Any, *, languages: tuple[str, ...] = ("en",),
                 language: str = "en", gpu: bool = False,
                 trained_line: bool | None = None,
                 model_path: str | None = None,
                 meta_path: str | None = None) -> "EngineRegistry":
        """Cria o conjunto padrão de adapters sem inicializar engines ainda.

        A inicialização continua tardia: instalar apenas Tesseract, por
        exemplo, não faz o lote falhar por falta de PaddleOCR/EasyOCR.

        `trained_line=None` (o padrão) inclui o modelo de linha próprio **só
        se ele passa no portão de produção** (`linha_trainer.modelo_utilizavel`:
        CER de validação abaixo do limite). `True` força a inclusão — é para
        teste e diagnóstico, não para a fusão —, e `False` o deixa fora.
        """
        adapters: list[OCRAdapter] = [
            OCRServiceAdapters.tesseract(service, language=language),
            OCRServiceAdapters.easyocr(service, languages=languages, gpu=gpu),
            OCRServiceAdapters.paddleocr(service, language=language, gpu=gpu),
        ]
        model_path, meta_path = _caminhos_de_linha(model_path, meta_path)
        if trained_line is None:
            from core.linha_trainer import modelo_utilizavel
            trained_line, _motivo = modelo_utilizavel(meta_path, model_path)
        if trained_line:
            adapters.append(OCRServiceAdapters.trained_line(
                service, model_path=model_path, meta_path=meta_path))
        return EngineRegistry(adapters)


@dataclass
class EngineRun:
    hypotheses: list[OCRHypothesis] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    def consolidate(self, *, minimum_support: int = 2) -> "ConsensusResult":
        """Consolida leituras sem descartar as hipóteses originais.

        O suporte é contado por engine, não por quantidade de chamadas. Uma
        única engine muito confiante não vence duas fontes independentes que
        concordam; empate entre leituras concorrentes permanece revisável.
        """
        return consolidate_hypotheses(self.hypotheses,
                                      minimum_support=minimum_support,
                                      errors=self.errors)


@dataclass(frozen=True)
class ConsensusResult:
    chosen: OCRHypothesis
    alternatives: tuple[str, ...]
    support: int
    consensus: bool
    review_required: bool
    reason_codes: tuple[str, ...]
    hypotheses: tuple[OCRHypothesis, ...]
    errors: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "chosen": asdict(self.chosen),
            "alternatives": list(self.alternatives),
            "support": self.support,
            "consensus": self.consensus,
            "review_required": self.review_required,
            "reason_codes": list(self.reason_codes),
            "hypotheses": [asdict(item) for item in self.hypotheses],
            "errors": dict(self.errors),
        }


def _texto_consenso(texto: str) -> str:
    return unicodedata.normalize("NFKC", str(texto or "")).strip().casefold()


def consolidate_hypotheses(hypotheses: Iterable[OCRHypothesis], *,
                           minimum_support: int = 2,
                           errors: dict[str, str] | None = None) -> ConsensusResult:
    """Escolhe apenas com evidência de fontes distintas e mantém o conflito."""
    minimum_support = int(minimum_support)
    if minimum_support < 1:
        raise ValueError("minimum_support deve ser positivo")
    originais = tuple(item for item in hypotheses if item.text.strip())
    erros = tuple((str(name), str(message))
                  for name, message in (errors or {}).items())
    if not originais:
        vazio = OCRHypothesis("", 0.0, "ensemble",
                              metadata={"support": 0, "sources": [],
                                        "engine_errors": dict(erros)})
        return ConsensusResult(vazio, (), 0, False, True, ("no_text",), (), erros)

    grupos: dict[str, list[OCRHypothesis]] = {}
    for item in originais:
        grupos.setdefault(_texto_consenso(item.text), []).append(item)

    ranqueados = []
    for chave, items in grupos.items():
        fontes = tuple(dict.fromkeys(str(item.source) for item in items))
        media = sum(item.confidence for item in items) / len(items)
        representante = max(items, key=lambda item: item.confidence)
        ranqueados.append((len(fontes), media, representante.confidence,
                           chave, fontes, representante, items))
    ranqueados.sort(key=lambda item: (item[0], item[1], item[2], item[3]),
                    reverse=True)
    suporte, media, _maxima, chave, fontes, representante, _items = ranqueados[0]
    segundo = ranqueados[1] if len(ranqueados) > 1 else None
    # Suporte é a evidência independente que autoriza o consenso. Quando dois
    # textos têm o mesmo suporte mínimo, a média de confiança não é uma prova
    # independente para desempatar: escolher o maior valor transformaria uma
    # discordância entre engines em decisão automática silenciosa.
    conflito = (segundo is not None and segundo[0] >= minimum_support
                and segundo[0] == suporte)
    consensus = suporte >= minimum_support and not conflito
    reasons = ("consensus",) if consensus else ("no_consensus",)
    if conflito:
        reasons = ("conflicting_consensus", "no_consensus")
    if erros:
        reasons = (*reasons, "engine_unavailable")
    chosen = OCRHypothesis(
        representante.text, media, "ensemble", bbox=representante.bbox,
        model_version=representante.model_version,
        preprocessing=representante.preprocessing,
        metadata={**representante.metadata, "support": suporte,
                  "sources": list(fontes), "consensus": consensus,
                  "engine_errors": dict(erros)},
    )
    alternativas = tuple(dict.fromkeys(item.text for item in originais
                                      if _texto_consenso(item.text) != chave))
    return ConsensusResult(chosen, alternativas, suporte, consensus,
                           not consensus or bool(erros), reasons, originais, erros)


class EnsembleLineReader:
    """Adapter de faixa que só emite texto apoiado por consenso.

    O formato retornado é compatível com `livro._registro_da_faixa`; o quinto
    campo é evidência serializável do ensemble e não interfere em adapters
    legados que só conhecem os quatro primeiros campos.
    """

    def __init__(self, registry: "EngineRegistry", *, minimum_support: int = 2):
        self.registry = registry
        self.minimum_support = int(minimum_support)
        if self.minimum_support < 1:
            raise ValueError("minimum_support deve ser positivo")
        self.last_result: ConsensusResult | None = None

    def __call__(self, image: Any) -> list[tuple[Any, ...]]:
        run = self.registry.recognize(image, level="line")
        result = run.consolidate(minimum_support=self.minimum_support)
        self.last_result = result
        if not result.consensus:
            return []
        matriz = np.asarray(image)
        altura, largura = (matriz.shape[:2] if matriz.ndim >= 2 else (1, 1))
        return [(result.chosen.text, result.chosen.confidence,
                 (0, 0, int(largura), int(altura)), (), result.to_dict())]


class EngineRegistry:
    def __init__(self, adapters: Iterable[OCRAdapter] = ()):
        self.adapters = list(adapters)

    def recognize(self, image: Any, *, level: str = "line") -> EngineRun:
        resultado = EngineRun()
        for adapter in self.adapters:
            try:
                hipotese = adapter.recognize(image, level=level)
            except Exception as erro:  # engine opcional não pode derrubar o lote
                resultado.errors[str(adapter.name)] = f"{type(erro).__name__}: {erro}"
                continue
            if not isinstance(hipotese, OCRHypothesis):
                resultado.errors[str(adapter.name)] = "adapter retornou tipo inválido"
                continue
            resultado.hypotheses.append(hipotese)
        return resultado
