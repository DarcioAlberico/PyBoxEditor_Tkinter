import cv2
import numpy as np
from typing import Optional, Tuple
from PIL import Image


def preprocess_for_easyocr(crop_np: np.ndarray, pad: int = 10, min_h: int = 64) -> np.ndarray:
    """
    Pré-processa um recorte numpy para o EasyOCR:
    - adiciona padding branco
    - garante altura mínima (resize proporcional)
    """
    if len(crop_np.shape) == 2:  # Grayscale
        crop_padded = np.pad(crop_np, ((pad, pad), (pad, pad)), mode="constant", constant_values=255)
    else:  # RGB
        crop_padded = np.pad(crop_np, ((pad, pad), (pad, pad), (0, 0)), mode="constant", constant_values=255)

    H, W = crop_padded.shape[:2]
    if H < min_h:
        scale = min_h / H
        new_W = int(W * scale)
        crop_padded = cv2.resize(crop_padded, (new_W, min_h), interpolation=cv2.INTER_LINEAR)

    return crop_padded


class OCRService:
    """
    Serviço puro para execução de OCR com Tesseract, EasyOCR e Rede Neural.
    Mantém o reader do EasyOCR em cache (instância única).
    """

    def __init__(self):
        self._reader = None  # cache EasyOCR

    # ------------------------------------------------------------------
    # Tesseract
    # ------------------------------------------------------------------
    def tesseract_ocr(self, crop: Image.Image, whitelist: Optional[str] = None) -> str:
        """Roda Tesseract num recorte PIL. Retorna string (pode ser vazia)."""
        import pytesseract

        config = "--psm 10"
        if whitelist:
            config += f" -c tessedit_char_whitelist={whitelist}"

        try:
            text = pytesseract.image_to_string(crop, config=config)
        except Exception:
            text = ""

        text = text.strip()
        if len(text) == 1:
            return text
        elif len(text) > 1:
            return text[0]
        return ""

    # ------------------------------------------------------------------
    # EasyOCR
    # ------------------------------------------------------------------
    def _init_easyocr(self, languages: Tuple[str, ...] = ("en",), gpu: bool = False):
        """Inicializa (e cacheia) o reader do EasyOCR."""
        if self._reader is None:
            import ssl
            # Bypass SSL — necessário em alguns ambientes Windows/Corp
            ssl._create_default_https_context = ssl._create_unverified_context
            import easyocr
            self._reader = easyocr.Reader(list(languages), gpu=gpu)
        return self._reader

    def easyocr_ocr(self, crop_np: np.ndarray, languages: Tuple[str, ...] = ("en",), gpu: bool = False) -> str:
        """
        Roda EasyOCR num recorte numpy.
        Retorna o primeiro caractere do resultado (ou string vazia).
        """
        reader = self._init_easyocr(languages, gpu)
        processed = preprocess_for_easyocr(crop_np)
        results = reader.readtext(processed, detail=1)

        if results:
            text = results[0][1].strip()
            if text:
                return text[0]
        return ""

    # ------------------------------------------------------------------
    # Neural (Custom CNN)
    # ------------------------------------------------------------------
    def neural_ocr(self, crop_np: np.ndarray, predictor) -> Tuple[str, float]:
        """
        Roda a rede neural customizada.
        predictor: instância de core.neural_trainer.NeuralPredictor (já loadada).
        Retorna (char, confidence).
        """
        if predictor is None or not getattr(predictor, "loaded", False):
            return "", 0.0
        return predictor.predict(crop_np)

    # ------------------------------------------------------------------
    # Learner (k-NN)
    # ------------------------------------------------------------------
    def learner_ocr(self, crop_np: np.ndarray, learner) -> Tuple[str, float]:
        """
        Roda o k-NN learner.
        learner: instância de core.learner.CharacterLearner.
        Retorna (char, confidence).
        """
        if learner is None:
            return "", 0.0
        return learner.predict(crop_np)

    # ------------------------------------------------------------------
    # Fallback chain: Neural -> Learner -> EasyOCR
    # ------------------------------------------------------------------
    def fallback_chain(
        self,
        crop_np: np.ndarray,
        *,
        predictor=None,
        learner=None,
        reader=None,  # se None, usa self._init_easyocr internamente
        neural_threshold: float = 0.8,
        learner_threshold: float = 0.9,
        easyocr_languages: Tuple[str, ...] = ("en",),
        easyocr_gpu: bool = False,
    ) -> Tuple[str, str, float]:
        """
        Executa a cadeia de fallback:
          1. Neural (se conf > neural_threshold)
          2. Learner k-NN (se conf > learner_threshold)
          3. EasyOCR

        Retorna (char, source, confidence).
        source pode ser: "neural", "learner", "easyocr", "none".
        """
        # 1. Neural
        if predictor is not None and getattr(predictor, "loaded", False):
            char, conf = predictor.predict(crop_np)
            if conf > neural_threshold:
                return char, "neural", conf

        # 2. Learner
        if learner is not None:
            char, conf = learner.predict(crop_np)
            if conf > learner_threshold:
                return char, "learner", conf

        # 3. EasyOCR
        if reader is not None:
            text = reader.readtext(preprocess_for_easyocr(crop_np), detail=1)
            if text:
                txt = text[0][1].strip()
                if txt:
                    return txt[0], "easyocr", 0.0  # EasyOCR não dá confiabilidade por caractere aqui
        else:
            # fallback: inicializa reader interno
            reader = self._init_easyocr(easyocr_languages, easyocr_gpu)
            text = reader.readtext(preprocess_for_easyocr(crop_np), detail=1)
            if text:
                txt = text[0][1].strip()
                if txt:
                    return txt[0], "easyocr", 0.0

        return "", "none", 0.0
