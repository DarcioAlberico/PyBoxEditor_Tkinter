"""Adapters opcionais e normalização das respostas dos engines OCR."""

from __future__ import annotations

from dataclasses import dataclass, field
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
            line_recognizer=lambda image: service.paddleocr_ocr_conf(image, language, gpu),
            metadata={"engine": "paddleocr", "line_model": False,
                      "line_mode": "segmented_crop"},
        )

    @staticmethod
    def tesseract(service: Any) -> CallableAdapter:
        return CallableAdapter(
            "tesseract",
            lambda image: service.tesseract_ocr_conf(
                image if isinstance(image, Image.Image) else Image.fromarray(np.asarray(image))),
            metadata={"engine": "tesseract", "line_model": False},
        )

    @staticmethod
    def neural(service: Any, predictor: Any) -> CallableAdapter:
        return CallableAdapter(
            "neural",
            lambda image: service.neural_ocr(np.asarray(image), predictor),
            metadata={"engine": "custom_neural", "line_model": False},
        )

    @staticmethod
    def learner(service: Any, learner: Any) -> CallableAdapter:
        return CallableAdapter(
            "learner",
            lambda image: service.learner_ocr(np.asarray(image), learner),
            metadata={"engine": "knn", "line_model": False},
        )


@dataclass
class EngineRun:
    hypotheses: list[OCRHypothesis] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


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
