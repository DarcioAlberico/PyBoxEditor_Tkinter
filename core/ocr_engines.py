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
    def trained_line(service: Any, *, model_path: str = "text_line_model.pth",
                     meta_path: str = "text_line_model.json") -> CallableAdapter:
        """Adapta o CRNN/CTC local ao contrato comum de linha."""
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
                 model_path: str = "text_line_model.pth",
                 meta_path: str = "text_line_model.json") -> "EngineRegistry":
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
