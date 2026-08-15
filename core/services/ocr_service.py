import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple
from PIL import Image

from core.box_model import SEM_MARGEM


@dataclass
class Leitura:
    """
    O que a cadeia respondeu, com as duas escalas separadas (F44).

    `confianca` é a que **roteia** — detector de novidade, e é ela que vira
    `b.confidence` e a cor do box. `margem` é a que serve à **revisão**, e só
    vem preenchida quando a fonte é o k-NN. A F43 mediu por que são duas: o
    roteamento gasta a informação da primeira, e o que sobra por decidir na
    fila é ambiguidade, que é o que a segunda mede.
    """

    char: str
    fonte: str
    confianca: float
    margem: float = SEM_MARGEM

    def como_tupla(self) -> Tuple[str, str, float]:
        """O contrato antigo de `fallback_chain`, para quem não quer a margem."""
        return self.char, self.fonte, self.confianca


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
    Mantém os readers do EasyOCR em cache, um por (idiomas, gpu).
    """

    def __init__(self):
        # Um reader por (idiomas, gpu). Era um só, guardado sem chave: a segunda
        # chamada com outro idioma recebia calada o reader da primeira.
        self._readers = {}

    # ------------------------------------------------------------------
    # Tesseract
    # ------------------------------------------------------------------
    def tesseract_ocr(self, crop: Image.Image, whitelist: Optional[str] = None) -> str:
        """Roda Tesseract num recorte PIL. Retorna string (pode ser vazia)."""
        return self.tesseract_ocr_conf(crop, whitelist)[0]

    def tesseract_ocr_conf(self, crop: Image.Image,
                           whitelist: Optional[str] = None) -> Tuple[str, float]:
        """
        Como tesseract_ocr, mas devolve (char, confiança 0..1).

        image_to_data expõe a confiança por token, que image_to_string descarta.
        O Tesseract reporta -1 quando não classificou nada; nesse caso vale 0.
        """
        import pytesseract

        config = "--psm 10"
        if whitelist:
            config += f" -c tessedit_char_whitelist={whitelist}"

        try:
            dados = pytesseract.image_to_data(
                crop, config=config, output_type=pytesseract.Output.DICT)
        except Exception:
            return "", 0.0

        melhor, melhor_conf = "", 0.0
        for texto, conf in zip(dados.get("text", []), dados.get("conf", [])):
            texto = (texto or "").strip()
            if not texto:
                continue
            try:
                conf = float(conf)
            except (TypeError, ValueError):
                conf = -1.0
            if conf > melhor_conf:
                melhor, melhor_conf = texto[0], conf

        if not melhor:
            return "", 0.0
        return melhor, max(0.0, melhor_conf) / 100.0

    # ------------------------------------------------------------------
    # EasyOCR
    # ------------------------------------------------------------------
    def _init_easyocr(self, languages: Tuple[str, ...] = ("en",), gpu: bool = False):
        """
        Inicializa (e cacheia) o reader do EasyOCR.

        `quantize=False` contraria o padrão da biblioteca, que quantiza o
        reconhecedor em int8 na CPU. Medido nos 2.278 caracteres rotulados, a
        quantização não paga o que cobra: 66,7% contra 66,9% sem ela — e neste
        torch ela ainda saiu **duas vezes mais lenta** (30,5 contra 15,8 ms por
        caractere), provavelmente caindo num kernel de referência.

        **O remendo de SSL é restaurado.** Ele era global e permanente: a
        primeira chamada de OCR desligava a verificação de certificado do
        processo inteiro, para toda requisição HTTPS do programa, e nunca a
        religava. Continua valendo onde era preciso — o download do modelo em
        rede corporativa — e só ali.
        """
        chave = (tuple(languages), bool(gpu))
        reader = self._readers.get(chave)
        if reader is None:
            import ssl
            import easyocr
            anterior = ssl._create_default_https_context
            ssl._create_default_https_context = ssl._create_unverified_context
            try:
                reader = easyocr.Reader(list(languages), gpu=gpu, quantize=False)
            finally:
                ssl._create_default_https_context = anterior
            self._readers[chave] = reader
        return reader

    def easyocr_ocr(self, crop_np: np.ndarray, languages: Tuple[str, ...] = ("en",),
                    gpu: bool = False) -> str:
        """Primeiro caractere reconhecido (ou string vazia)."""
        return self.easyocr_ocr_conf(crop_np, languages, gpu)[0]

    @staticmethod
    def _primeiro_char_easyocr(resultados) -> Tuple[str, float]:
        """
        Extrai (char, confiança) de uma saída de `recognize(detail=1)`.

        Cada item é (bbox, texto, confiança). A confiança era descartada, e o
        fallback_chain devolvia 0.0 fixo para tudo que viesse do EasyOCR — o
        que apagava justamente o dado mais útil para revisão. Como se pede uma
        caixa só, a confiança dela é a do caractere.
        """
        if not resultados:
            return "", 0.0
        item = resultados[0]
        texto = (item[1] or "").strip()
        if not texto:
            return "", 0.0
        conf = float(item[2]) if len(item) > 2 else 0.0
        return texto[0], max(0.0, min(1.0, conf))

    @staticmethod
    def _cinza(img: np.ndarray) -> np.ndarray:
        if img.ndim == 2:
            return img
        if img.shape[2] == 4:
            return cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
        return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    @classmethod
    def _ler_easyocr(cls, reader, imagem: np.ndarray) -> Tuple[str, float]:
        """
        Reconhece **sem detectar**: o box já veio do OpenCV.

        Era `readtext`, que roda o detector CRAFT antes de reconhecer. Pagava-se
        a detecção duas vezes e a segunda só atrapalhava — o CRAFT é detector de
        texto em cena e num recorte de um caractere ele frequentemente não acha
        nada. Medido nos 2.278 caracteres rotulados, a tabela de confusão do
        `readtext` era dominada por leitura **vazia**: `.` 123, `t` 81, `o` 64 e
        `l` 51 lidos como nada — cerca de 410 casos, 18% da amostra, em que o
        caractere estava lá e a resposta foi "não há texto aqui".

        Dizer ao `recognize` que a caixa é a imagem inteira leva o acerto de
        53,6% para 66,7% e corta o custo pela metade.
        """
        img = preprocess_for_easyocr(imagem)
        cinza = cls._cinza(img)
        h, w = cinza.shape[:2]
        return cls._primeiro_char_easyocr(
            reader.recognize(cinza, horizontal_list=[[0, w, 0, h]],
                             free_list=[], detail=1))

    def easyocr_ocr_conf(self, crop_np: np.ndarray, languages: Tuple[str, ...] = ("en",),
                         gpu: bool = False,
                         contexto: Optional[np.ndarray] = None) -> Tuple[str, float]:
        """
        Roda EasyOCR num recorte numpy. Retorna (char, confiança 0..1).

        `contexto` é o mesmo box esticado até a **faixa vertical da linha**. Ele
        existe por causa da F14: normalizar a altura do recorte apaga a
        diferença entre `c` e `C`, que é de tamanho e não de traço, e o modelo
        recebe as duas como a mesma imagem. Com a faixa da linha o glifo mantém
        a altura *relativa* e a caixa volta a ser legível — medido, 66,9% para
        74,2%, e as confusões `s` por `S` (79), `c` por `C` (40) e `w` por `W`
        (25) somem da lista. Quem não tem a faixa passa `None` e fica como
        estava.
        """
        reader = self._init_easyocr(languages, gpu)
        return self._ler_easyocr(
            reader, crop_np if contexto is None else contexto)

    def easyocr_linha_conf(self, faixa_np: np.ndarray,
                           languages: Tuple[str, ...] = ("en",),
                           gpu: bool = False) -> Tuple[str, float]:
        """
        Lê uma **faixa de linha inteira**. Retorna (texto, confiança 0..1).

        É para isto que o `english_g2` foi treinado — palavra e linha, com o
        modelo de linguagem implícito do CRNN —, e é o que a leitura caractere a
        caractere joga fora. Medido, 72,8% para 91,2% (F17).

        Aqui o texto **não** é truncado no primeiro caractere: a string inteira
        é o resultado, e quem a distribui pelos boxes é `leitura_de_linha`.
        """
        reader = self._init_easyocr(languages, gpu)
        cinza = self._cinza(faixa_np)
        h, w = cinza.shape[:2]
        resultados = reader.recognize(cinza, horizontal_list=[[0, w, 0, h]],
                                      free_list=[], detail=1)
        if not resultados:
            return "", 0.0
        texto = "".join((r[1] or "") for r in resultados).strip()
        confs = [float(r[2]) for r in resultados if len(r) > 2]
        conf = min(confs) if confs else 0.0
        return texto, max(0.0, min(1.0, conf))

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
        # 0,70 e não 0,80 desde a F22: o 0,80 estava afinado para o modelo sem
        # calibração, e a temperatura de 2,1916 baixou a escala inteira sem
        # mudar qual classe vence. Medido, 0,80 manda 60 boxes a mais para o
        # k-NN e custa 0,08 ponto. Ver `NEURAL_THRESHOLD` em `ui/main_window`,
        # que é onde a tabela está.
        neural_threshold: float = 0.70,
        learner_threshold: float = 0.9,
        easyocr_languages: Tuple[str, ...] = ("en",),
        easyocr_gpu: bool = False,
        contexto: Optional[np.ndarray] = None,
    ) -> Tuple[str, str, float]:
        """
        Executa a cadeia de fallback:
          1. Neural (se conf > neural_threshold)
          2. Learner k-NN (se conf > learner_threshold)
          3. EasyOCR

        Retorna (char, source, confidence).
        source pode ser: "neural", "learner", "easyocr", "none".

        **É `fallback_chain_detalhado` sem a margem**, e não uma segunda
        implementação da cadeia: dois caminhos que deveriam rotear igual acabam
        divergindo, e é o defeito que a F1.5 registrou.
        """
        return self.fallback_chain_detalhado(
            crop_np, predictor=predictor, learner=learner, reader=reader,
            neural_threshold=neural_threshold,
            learner_threshold=learner_threshold,
            easyocr_languages=easyocr_languages, easyocr_gpu=easyocr_gpu,
            contexto=contexto).como_tupla()

    def fallback_chain_detalhado(
        self,
        crop_np: np.ndarray,
        *,
        predictor=None,
        learner=None,
        reader=None,
        neural_threshold: float = 0.70,
        learner_threshold: float = 0.9,
        easyocr_languages: Tuple[str, ...] = ("en",),
        easyocr_gpu: bool = False,
        contexto: Optional[np.ndarray] = None,
    ) -> Leitura:
        """
        A mesma cadeia, devolvendo também a **margem** do k-NN (F44).

        O k-NN é consultado por `predict_e_margem`, que faz a busca **uma vez** e
        devolve as duas escalas — chamar `predict` e `margem_de_confianca` em
        seguida dobraria o custo da ação, e é o custo que a F7.2 existe para
        conter. Quando quem responde não é o k-NN, a margem sai `SEM_MARGEM`.
        """
        # 1. Neural
        if predictor is not None and getattr(predictor, "loaded", False):
            char, conf = predictor.predict(crop_np)
            if conf > neural_threshold:
                return Leitura(char, "neural", conf)

        # 2. Learner
        if learner is not None:
            char, conf, margem = learner.predict_e_margem(crop_np)
            if conf > learner_threshold:
                return Leitura(char, "learner", conf, margem)

        # 3. EasyOCR (último elo: aceita o que vier, com a confiança real).
        # A rede e o k-NN querem o recorte justo, em que foram treinados; só
        # este elo se beneficia da faixa da linha (ver `easyocr_ocr_conf`).
        if reader is None:
            reader = self._init_easyocr(easyocr_languages, easyocr_gpu)

        char, conf = self._ler_easyocr(
            reader, crop_np if contexto is None else contexto)
        if char:
            return Leitura(char, "easyocr", conf)

        return Leitura("", "none", 0.0)
