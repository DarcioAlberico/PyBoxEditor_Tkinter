import cv2
import json
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple
from PIL import Image

from core import alfabeto, preprocess, proporcao
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
        self._paddle_readers = {}

    # ------------------------------------------------------------------
    # Tesseract
    # ------------------------------------------------------------------
    @staticmethod
    def _configurar_tesseract(pytesseract) -> None:
        """Localiza o executável no Windows quando ele não está no PATH."""
        import os

        atual = getattr(pytesseract.pytesseract, "tesseract_cmd", "")
        if atual and os.path.exists(atual):
            return
        candidatos = (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        )
        for caminho in candidatos:
            if os.path.exists(caminho):
                pytesseract.pytesseract.tesseract_cmd = caminho
                return

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

        self._configurar_tesseract(pytesseract)

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

    @staticmethod
    def _idioma_tesseract(idioma: str = "en") -> str:
        """Converte o idioma curto do aplicativo para o pacote do Tesseract."""
        return {
            "en": "eng",
            "pt": "por",
            "eng": "eng",
            "por": "por",
        }.get(str(idioma or "en").lower(), str(idioma or "eng"))

    def _linhas_do_tesseract(self, imagem_np: np.ndarray, idioma: str,
                             psm: int) -> list[tuple]:
        """`[(texto, confiança, caixa, detalhes)]`, uma linha do Tesseract por
        item, com `detalhes` sendo as palavras dela como `(texto, confiança,
        caixa)`. É o formato que `core.livro` casa com as linhas dele; o `psm`
        diz se a imagem é a página (3) ou a faixa de uma linha só (7)."""
        import pytesseract

        self._configurar_tesseract(pytesseract)
        imagem = np.asarray(imagem_np)
        if imagem.size == 0:
            return []
        if imagem.ndim == 3:
            imagem = self._cinza(imagem)
        imagem = np.ascontiguousarray(imagem, dtype=np.uint8)
        try:
            dados = pytesseract.image_to_data(
                Image.fromarray(imagem),
                lang=self._idioma_tesseract(idioma),
                config=f"--psm {psm} -c preserve_interword_spaces=1",
                output_type=pytesseract.Output.DICT,
            )
        except Exception:
            return []
        return self._agrupar_dados_do_tesseract(dados)

    @staticmethod
    def _agrupar_dados_do_tesseract(registros) -> list[tuple]:
        grupos = {}
        for i, bruto in enumerate(registros.get("text", [])):
            texto = str(bruto or "").strip()
            if not texto:
                continue
            try:
                confianca = max(0.0, min(1.0,
                                         float(registros["conf"][i]) / 100.0))
            except (KeyError, TypeError, ValueError, IndexError):
                confianca = 0.0
            try:
                x = int(registros["left"][i])
                y = int(registros["top"][i])
                w = int(registros["width"][i])
                h = int(registros["height"][i])
            except (KeyError, TypeError, ValueError, IndexError):
                continue
            chave = tuple(
                int(registros.get(nome, [0])[i])
                for nome in ("block_num", "par_num", "line_num")
            )
            item = grupos.setdefault(
                chave, {"palavras": [], "confs": [], "caixas": [],
                        "detalhes": []})
            item["palavras"].append(texto)
            item["confs"].append(confianca)
            caixa = (x, y, x + max(1, w), y + max(1, h))
            item["caixas"].append(caixa)
            item["detalhes"].append((texto, confianca, caixa))

        linhas = []
        for item in grupos.values():
            caixas = item["caixas"]
            x1 = min(c[0] for c in caixas)
            y1 = min(c[1] for c in caixas)
            x2 = max(c[2] for c in caixas)
            y2 = max(c[3] for c in caixas)
            confs = item["confs"]
            linhas.append((" ".join(item["palavras"]),
                           sum(confs) / len(confs), (x1, y1, x2, y2),
                           tuple(item["detalhes"])))
        return sorted(linhas, key=lambda item: (item[2][1], item[2][0]))

    def tesseract_faixa_detalhada_conf(
        self, faixa_np: np.ndarray, idioma: str = "en"
    ) -> list[tuple]:
        """Reconhece a faixa de **uma** linha, no mesmo formato da página.

        É o fallback da fusão por palavra para a linha que a passada de página
        não devolveu — o `--psm 3` às vezes pula um cabeçalho em negrito
        inteiro. Custa uma chamada de processo por linha (F114: ~140 ms), e
        por isso só roda para essas linhas, nunca para a página. As caixas
        são relativas à faixa; quem chama desloca.
        """
        return self._linhas_do_tesseract(faixa_np, idioma, psm=7)

    def tesseract_pagina_detalhada_conf(
        self, pagina_np: np.ndarray, idioma: str = "en",
        _segunda_passada: bool = True
    ) -> list[tuple]:
        """Reconhece uma página inteira e devolve linhas com suas coordenadas.

        A chamada única por página é importante: iniciar o Tesseract uma vez
        para cada glifo ou linha torna um livro impraticavelmente lento. As
        coordenadas permitem que ``core.livro`` use o contexto da palavra sem
        perder a segmentação e a ordem de leitura que o programa já calculou.
        """
        linhas = self._linhas_do_tesseract(pagina_np, idioma, psm=3)
        imagem = np.asarray(pagina_np)
        if imagem.ndim == 3:
            imagem = self._cinza(imagem)
        imagem = np.ascontiguousarray(imagem, dtype=np.uint8)
        if _segunda_passada and imagem.size:
            alternativas = self._ocr_de_recuperacao_da_trama(imagem, idioma)
            if alternativas:
                def sobrepoe(a, b):
                    horizontal = min(a[2], b[2]) - max(a[0], b[0])
                    vertical = min(a[3], b[3]) - max(a[1], b[1])
                    return horizontal > 0 and vertical > 0

                linhas.extend(
                    linha for linha in alternativas
                    if not any(sobrepoe(linha[2], atual[2])
                               for atual in linhas))
                linhas.sort(key=lambda item: (item[2][1], item[2][0]))
        return linhas

    def _ocr_de_recuperacao_da_trama(self, imagem: np.ndarray,
                                     idioma: str) -> list[tuple]:
        """Segunda leitura do scan quando o fundo pontilhado oculta texto.

        A primeira passada continua sendo a fonte preferida. Só se ativa para
        páginas com mais de 20 mil componentes após Otsu; nesses scans, remover
        componentes muito pequenos antes do Tesseract recupera textos impressos
        sobre a textura sem piorar páginas limpas.
        """
        mascara = preprocess.binarize(imagem, "otsu")
        n, labels, stats, _ = cv2.connectedComponentsWithStats(
            mascara, connectivity=8)
        if n <= 20000:
            return []

        limpa = np.zeros_like(mascara)
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] >= 8:
                limpa[labels == i] = 255
        recuperada = 255 - limpa
        # O PSM de página inteira ainda pode ignorar a coluna texturizada por
        # considerá-la um fundo. Lê-la como uma página independente preserva as
        # linhas e as coordenadas; o recorte cobre a coluna esquerda típica
        # destes livros e um pouco de margem, sem entrar no corpo da direita.
        largura = recuperada.shape[1]
        x1, x2 = min(80, largura // 4), max(1, int(largura * 0.47))
        coluna = self.tesseract_pagina_detalhada_conf(
            recuperada[:, x1:x2], idioma, _segunda_passada=False)

        def deslocar(registro):
            texto, conf, caixa, detalhes = registro
            x_a, y_a, x_b, y_b = caixa
            nova_caixa = (x_a + x1, y_a, x_b + x1, y_b)
            novos_detalhes = tuple(
                (palavra, palavra_conf,
                 (a + x1, b, c + x1, d))
                for palavra, palavra_conf, (a, b, c, d) in detalhes)
            return texto, conf, nova_caixa, novos_detalhes

        return [deslocar(registro) for registro in coluna]

    def tesseract_pagina_conf(
        self, pagina_np: np.ndarray, idioma: str = "en"
    ) -> list[Tuple[str, float, Tuple[int, int, int, int]]]:
        """Versão compatível: linhas sem os detalhes internos das palavras."""
        return [registro[:3]
                for registro in self.tesseract_pagina_detalhada_conf(pagina_np, idioma)]

    def tesseract_linha_conf(
        self, faixa_np: np.ndarray, idioma: str = "en"
    ) -> Tuple[str, float]:
        """Reconhece uma faixa isolada; mantido para ferramentas e testes."""
        pagina = self.tesseract_pagina_conf(faixa_np, idioma)
        if not pagina:
            return "", 0.0
        texto, conf, _caixa = max(pagina, key=lambda item: item[2][2] - item[2][0])
        return texto, conf

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
    # PaddleOCR
    # ------------------------------------------------------------------
    def _init_paddleocr(self, language: str = "en", gpu: bool = False):
        """Inicializa e cacheia o reconhecedor do PaddleOCR.

        O import é tardio porque PaddleOCR é opcional e pesado. A integração
        usa o módulo de reconhecimento, sem detector: o editor já possui o
        recorte exato do box e rodar detecção novamente só acrescentaria custo
        e uma segunda fonte de coordenadas.
        """
        chave = (str(language or "en"), bool(gpu))
        model = self._paddle_readers.get(chave)
        if model is not None:
            return model

        # PaddleOCR 3.x pode importar ModelScope, que por sua vez carrega
        # Torch. No Windows, carregar as DLLs do Paddle antes das DLLs do Torch
        # produz WinError 127; pré-carregar Torch mantém os dois backends no
        # mesmo processo. Torch continua opcional para quem só usa PaddleOCR.
        try:
            import torch  # noqa: F401
        except ImportError:
            pass
        try:
            from paddleocr import TextRecognition
        except ModuleNotFoundError as exc:
            modulo = exc.name or "paddleocr"
            raise RuntimeError(
                "PaddleOCR não está disponível neste interpretador "
                f"(módulo ausente: {modulo}). Instale com: "
                "python -m pip install -e \".[paddle]\""
            ) from exc

        kwargs = {"engine": "paddle"}
        if gpu:
            kwargs["device"] = "gpu:0"
        try:
            model = TextRecognition(**kwargs)
        except TypeError:
            # Compatibilidade com versões que ainda não aceitam `engine` ou
            # `device`; a API 3.x documenta ambos, mas o fallback mantém o
            # backend utilizável em instalações 2.x.
            kwargs.pop("device", None)
            kwargs.pop("engine", None)
            model = TextRecognition(**kwargs)
        self._paddle_readers[chave] = model
        return model

    @staticmethod
    def _resultado_paddle(resultado) -> Tuple[str, float]:
        """Extrai texto/confiança das respostas 2.x e 3.x do PaddleOCR."""
        if resultado is None:
            return "", 0.0

        # API 3.x: objeto com `json` ou dicionário dentro da chave `res`.
        dados = getattr(resultado, "json", None)
        if callable(dados):
            dados = dados()
        if dados is None and isinstance(resultado, dict):
            dados = resultado
        if isinstance(dados, str):
            try:
                dados = json.loads(dados)
            except (TypeError, ValueError):
                dados = None
        if isinstance(dados, dict):
            dados = dados.get("res", dados)
            texto = dados.get("rec_text", dados.get("text", dados.get("rec_texts", "")))
            confianca = dados.get(
                "rec_score", dados.get("score", dados.get("rec_scores", 0.0))
            )
            # TextRecognition 3.x usa listas, mesmo quando recebe um único
            # recorte. Não indexar diretamente antes de conferir o tamanho:
            # uma resposta vazia é válida e deve virar OCR não resolvido.
            if isinstance(texto, (list, tuple, np.ndarray)):
                texto = texto[0] if len(texto) else ""
            if isinstance(confianca, (list, tuple, np.ndarray)):
                confianca = confianca[0] if len(confianca) else 0.0
            try:
                return str(texto or "").strip()[:1], max(0.0, min(1.0, float(confianca)))
            except (TypeError, ValueError):
                return str(texto or "").strip()[:1], 0.0

        # API 2.x: [[box, (texto, confiança)], ...].
        if isinstance(resultado, (list, tuple)) and resultado:
            item = resultado[0]
            if isinstance(item, (list, tuple)) and len(item) > 1:
                leitura = item[1]
                if isinstance(leitura, (list, tuple)) and leitura:
                    texto = str(leitura[0] or "").strip()
                    try:
                        confianca = float(leitura[1]) if len(leitura) > 1 else 0.0
                    except (TypeError, ValueError):
                        confianca = 0.0
                    return texto[:1], max(0.0, min(1.0, confianca))
        return "", 0.0

    def paddleocr_ocr(self, crop_np: np.ndarray, language: str = "en",
                      gpu: bool = False) -> str:
        return self.paddleocr_ocr_conf(crop_np, language, gpu)[0]

    def paddleocr_ocr_conf(self, crop_np: np.ndarray, language: str = "en",
                           gpu: bool = False) -> Tuple[str, float]:
        """Reconhece um box já segmentado usando o módulo TextRecognition."""
        model = self._init_paddleocr(language, gpu)
        imagem = np.asarray(crop_np)
        if imagem.ndim == 2:
            imagem = cv2.cvtColor(imagem, cv2.COLOR_GRAY2BGR)
        elif imagem.ndim == 3 and imagem.shape[2] == 4:
            imagem = cv2.cvtColor(imagem, cv2.COLOR_BGRA2BGR)
        try:
            try:
                resultados = model.predict(input=imagem, batch_size=1)
            except TypeError:
                resultados = model.predict(imagem)
        except (IndexError, KeyError, TypeError, ValueError):
            # Um recorte vazio/incompatível não pode abortar o preenchimento da
            # página inteira; os outros boxes continuam sendo processados.
            return "", 0.0
        try:
            primeiro = next(iter(resultados))
        except StopIteration:
            return "", 0.0
        return self._resultado_paddle(primeiro)

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
        altura_de_referencia: Optional[float] = None,
        idioma: Optional[str] = None,
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
            contexto=contexto,
            altura_de_referencia=altura_de_referencia,
            idioma=idioma).como_tupla()

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
        altura_de_referencia: Optional[float] = None,
        idioma: Optional[str] = None,
    ) -> Leitura:
        """
        A mesma cadeia, devolvendo também a **margem** do k-NN (F44).

        O k-NN é consultado por `predict_e_margem`, que faz a busca **uma vez** e
        devolve as duas escalas — chamar `predict` e `margem_de_confianca` em
        seguida dobraria o custo da ação, e é o custo que a F7.2 existe para
        conter. Quando quem responde não é o k-NN, a margem sai `SEM_MARGEM`.

        `altura_de_referencia` é a mediana da altura dos boxes da página, e serve
        ao veto geométrico da F106 — sem ela, o veto roda só pela proporção. Quem
        tem a página à mão a tira de `proporcao.altura_de_referencia`.

        `idioma` liga a máscara de alfabeto da F109 (`core.alfabeto`), que é o
        outro veto com a mesma forma: a letra acentuada que o idioma não escreve
        é impossível como o travessão num recorte em pé é impossível, e o mesmo
        elo dá a candidata seguinte que passe **nos dois crivos**. `None` é a
        cadeia de antes. É a mesma regra de `LearningService.ler_texto`, que a
        aplica só à rede para quem lê o livro inteiro; aqui ela vale também
        para o k-NN, cujas classes são as mesmas pastas de `training_data` e
        trazem as mesmas letras acentuadas.
        """
        # Os dois elos que classificam esticam o recorte para 32×32 sem
        # preservar proporção, então nenhum dos dois enxerga se a barra de tinta
        # está em pé ou deitada (F106). O recorte é o do box, então os lados dele
        # são exatamente o que o esticão apagou.
        largura, altura = proporcao.lados(crop_np)

        def cabe(char):
            return (alfabeto.permitido(char, idioma)
                    and proporcao.cabe(char, largura, altura,
                                       altura_de_referencia))

        def escolher(candidatas):
            return proporcao.escolher(alfabeto.filtrar(candidatas, idioma),
                                      largura, altura, altura_de_referencia)

        # 1. Neural
        if predictor is not None and getattr(predictor, "loaded", False):
            char, conf = predictor.predict(crop_np)
            if not cabe(char):
                # Segunda passada pela rede, e só aqui: medido, o veto pega 2
                # leituras em 10.641 numa página normal. O caminho de sempre não
                # paga nada por isto existir.
                escolhida = escolher(
                    predictor.predict_topk(crop_np, k=proporcao.CANDIDATAS))
                if escolhida is not None:
                    char, conf = escolhida
            if conf > neural_threshold:
                return Leitura(char, "neural", conf)

        # 2. Learner
        if learner is not None:
            char, conf, margem = learner.predict_e_margem(crop_np)
            if not cabe(char):
                escolhida = escolher(
                    learner.candidatas(crop_np, n=proporcao.CANDIDATAS))
                if escolhida is not None:
                    # A margem media o vencedor que o veto derrubou, e não este.
                    # `SEM_MARGEM` é o que ela quer dizer agora; ela não decide
                    # nada desde a F47, então isto não desarruma fila nenhuma.
                    char, conf = escolhida
                    margem = SEM_MARGEM
            if conf > learner_threshold:
                return Leitura(char, "learner", conf, margem)

        # 3. EasyOCR (último elo: aceita o que vier, com a confiança real).
        # A rede e o k-NN querem o recorte justo, em que foram treinados; só
        # este elo se beneficia da faixa da linha (ver `easyocr_ocr_conf`).
        #
        # **Sem veto geométrico aqui**, e não por esquecimento: este elo devolve
        # um caractere e nenhuma candidata, então não há entre o que escolher.
        # Vetar sem substituta seria apagar a leitura, que é pior que a leitura
        # improvável — o elo existe justamente para o box que os outros dois não
        # souberam ler.
        if reader is None:
            reader = self._init_easyocr(easyocr_languages, easyocr_gpu)

        char, conf = self._ler_easyocr(
            reader, crop_np if contexto is None else contexto)
        if char:
            return Leitura(char, "easyocr", conf)

        return Leitura("", "none", 0.0)
