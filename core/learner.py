import os
import cv2
import numpy as np
import uuid
import glob
from typing import Tuple, List, Optional


#: Não alfanuméricos que ainda cabem num nome de pasta legível.
#:
#: São os que este material cola no caractere seguinte: o hífen da notação longa
#: (`Rf1-g1`) e o par de avaliação `+-` / `-+`. Sem eles a base guardava
#: `ligature_hex_002d0067` no lugar de `ligature_-g` — e quem revisa a base a
#: olho lê o nome da pasta, não este arquivo.
#:
#: **A lista é fechada de propósito**, e é curta porque um candidato novo tem de
#: passar por três filtros:
#:
#: - **legal no Windows**: `\ / : * ? " < > |` não são nome de pasta, e ponto ou
#:   espaço no fim somem sem aviso;
#: - **inerte no `glob`**: o `_pngs` do `dataset_check` monta o padrão com o
#:   caminho inteiro, então `*`, `?`, `[` e `]` no nome da pasta virariam
#:   curinga e a classe apareceria vazia;
#: - **nunca `_`**: é o que garante que um nome legível não comece por `hex_` e
#:   seja lido de volta como hexadecimal.
EXTRAS_LEGIVEIS = "+-"


def char_to_folder(char: str) -> str:
    """
    Converte um caractere em um nome de pasta seguro para Windows,
    diferenciando maiusculas de minusculas.
    Mantem apenas alfanumericos ASCII puros como legiveis.
    Todo o resto vira 'sym_{ord}'.
    Ligaduras (len > 1) viram 'ligature_{char}'.
    """
    if not char:
        return "unknown"

    # Ligaduras (ex: 'fi', 'ffi', 'f7', '-g')
    if len(char) > 1:
        # Cabe no nome da pasta e fica legível. O teste já foi `isalpha()`, que
        # jogava 'f7' — casa de xadrez, comum como box único nestes livros — no
        # ramo hexadecimal; depois `isalnum()`, que fazia o mesmo com '-g'.
        if char.isascii() and all(c.isalnum() or c in EXTRAS_LEGIVEIS
                                  for c in char):
            return f"ligature_{char}"
        # Hex de largura fixa: com largura variável a volta é ambígua
        # ('ab' + 'c' e 'a' + 'bc' geram a mesma cadeia).
        hex_str = "".join(f"{ord(c):04x}" for c in char)
        return f"ligature_hex_{hex_str}"

    # Apenas A-Z, a-z e 0-9 sao mantidos "legíveis"
    if 'A' <= char <= 'Z':
        return f"upper_{char}"
    elif 'a' <= char <= 'z':
        return f"lower_{char}"
    elif '0' <= char <= '9':
        return f"digit_{char}"
    else:
        # Qualquer outro (acentos, simbolos, pontuacao, espaco) vira codigo ASCII
        return f"sym_{ord(char)}"


class NomeDePastaInvalido(ValueError):
    """O nome da pasta não corresponde a nenhum caractere conhecido."""


# Pastas de formatos antigos cujo caractere real foi confirmado olhando as
# amostras. 'sym_f7' guardava 127 imagens da casa de xadrez "f7"; como
# chr(int("f7")) levanta ValueError, elas viravam "?" e colidiam com sym_63,
# que é o "?" de verdade — duas classes distintas ensinando o mesmo símbolo.
LEGADO = {
    "sym_f7": "f7",
}


def folder_to_char(folder_name: str, strict: bool = False) -> str:
    """
    Converte um nome de pasta de volta para o caractere original.
    Ex: 'upper_A' -> 'A', 'lower_a' -> 'a', 'digit_1' -> '1', 'sym_46' -> '.'

    Com strict=True, levanta NomeDePastaInvalido em vez de devolver "?".
    Devolver "?" em silêncio é o que permitiu 127 amostras treinarem a classe
    errada sem ninguém notar; a validação do dataset usa o modo estrito.
    """
    def falhar():
        if strict:
            raise NomeDePastaInvalido(folder_name)
        return "?"

    if folder_name in LEGADO:
        return LEGADO[folder_name]

    if folder_name.startswith("ligature_hex_"):
        hex_str = folder_name[13:]
        if len(hex_str) % 4 != 0:
            return falhar()
        try:
            return "".join(chr(int(hex_str[i:i + 4], 16))
                           for i in range(0, len(hex_str), 4))
        except ValueError:
            return falhar()

    if folder_name.startswith("ligature_"):
        return folder_name[9:]

    if folder_name.startswith(("upper_", "lower_", "digit_")):
        return folder_name[6:]

    if folder_name.startswith("sym_"):
        try:
            return chr(int(folder_name[4:]))
        except ValueError:
            return falhar()

    if folder_name.startswith("ASCII_"):
        # Compatibilidade com formato antigo
        try:
            return chr(int(folder_name[6:]))
        except ValueError:
            return falhar()

    # Formato antigo (pasta = caractere diretamente)
    return folder_name


#: Lado do recorte normalizado. Não mexer sem refazer o cache: ele guarda a
#: matriz já nesse tamanho.
LADO = 32

#: Onde a matriz de referências fica guardada, dentro da própria base.
NOME_DO_CACHE = ".learner_cache.npz"


class CharacterLearner:
    """
    Vizinho mais próximo sobre os recortes já rotulados.

    É o elo do meio da cadeia da `ocr_service` (rede -> k-NN -> EasyOCR) e ele
    **se paga**: medido nas 9 páginas rotuladas, a rede fica abaixo de 0,8 em
    3,5% dos caracteres, e nesses 366 casos difíceis a cadeia com o k-NN acerta
    88,5% contra 72,4% da rede sozinha — 59 caracteres a mais.

    O que custava caro era a implementação, não a ideia. Medido antes:

    | | antes | agora |
    |---|---:|---:|
    | carregar as referências | 141 s (a frio) | **0,2 s** |
    | uma predição | 415 ms | **3,7 ms** |
    | memória | 155 MB | 89 MB |

    Três mudanças, e nenhuma altera a resposta:

    - **86% das referências eram duplicata byte a byte** — 151.114 imagens,
      21.823 distintas. Texto impresso na mesma fonte e no mesmo corpo cai no
      mesmo PNG de 32x32 depois do redimensionamento; é o mesmo achado do
      rascunho da F3.8 e da `training_data_2`. Tirar a repetição não muda o
      vizinho mais próximo, só para de compará-lo sete vezes.
    - **A busca virou uma conta de matriz**, com `||a-b||² = ||a||² + ||b||² -
      2a·b` e as normas das referências pré-calculadas. O laço com `cv2.norm`
      por referência era o grosso dos 415 ms.
    - **A matriz fica em cache** ao lado da base. Reconstruí-la é ler 151 mil
      PNGs, que é de onde vinham os 141 s.

    **O ROADMAP sugeria FAISS ou KD-tree, e não é preciso.** Medido, um índice
    aproximado (PCA para 32 dimensões) desce de 3,7 ms para 0,1 ms — mas muda a
    resposta em 4 de 200 consultas. A 3,7 ms uma página de 2.000 caracteres
    gasta 0,25 s de k-NN; não há o que comprar com uma dependência nova e uma
    aproximação.
    """

    def __init__(self, data_dir="training_data", usar_cache=True):
        self.data_dir = data_dir
        self.usar_cache = usar_cache
        self._X = np.zeros((0, LADO * LADO), dtype=np.float32)
        self._chars: List[str] = []
        self._normas = np.zeros((0,), dtype=np.float32)
        self._cache_sujo = False
        self.ensure_dir()
        self.load_references()

    def ensure_dir(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    @property
    def total(self) -> int:
        return len(self._chars)

    # ------------------------------------------------------------------
    # Carga
    # ------------------------------------------------------------------

    @property
    def caminho_do_cache(self) -> str:
        return os.path.join(self.data_dir, NOME_DO_CACHE)

    def _impressao_digital(self) -> np.ndarray:
        """
        Quantos PNGs há em cada pasta de classe.

        É o que diz se o cache envelheceu. Contar custa 0,2 s nas 151 mil
        amostras; olhar a data de cada arquivo custaria 5,2 s, e a única coisa
        a mais que pegaria é um arquivo **substituído** sem mudar a contagem —
        que nada neste projeto faz (`learn` só acrescenta, com nome novo).
        """
        linhas = []
        if os.path.isdir(self.data_dir):
            for pasta in sorted(os.listdir(self.data_dir)):
                caminho = os.path.join(self.data_dir, pasta)
                if os.path.isdir(caminho):
                    n = sum(1 for f in os.listdir(caminho) if f.endswith(".png"))
                    linhas.append(f"{pasta}={n}")
        return np.array(linhas)

    def load_references(self):
        """Carrega a matriz de referências, do cache quando ele serve."""
        digital = self._impressao_digital()

        if self.usar_cache and os.path.isfile(self.caminho_do_cache):
            try:
                z = np.load(self.caminho_do_cache, allow_pickle=False)
                if np.array_equal(z["digital"], digital):
                    self._instalar([str(c) for c in z["chars"]],
                                   z["X"].astype(np.float32))
                    print(f"Loaded {self.total} reference samples (cache).")
                    return
            except (OSError, ValueError, KeyError):
                pass        # cache ilegível é motivo para refazer, não para parar

        chars, X = self._ler_do_disco()
        self._instalar(chars, X)
        print(f"Loaded {self.total} reference samples.")
        if self.usar_cache:
            self.salvar_cache(digital)

    def _ler_do_disco(self):
        """(rótulos, matriz) a partir dos PNGs, sem duplicata byte a byte."""
        vistos, chars, linhas = set(), [], []
        if not os.path.exists(self.data_dir):
            return chars, np.zeros((0, LADO * LADO), dtype=np.float32)

        for pasta in sorted(os.listdir(self.data_dir)):
            caminho = os.path.join(self.data_dir, pasta)
            if not os.path.isdir(caminho):
                continue
            char = folder_to_char(pasta)
            for arquivo in sorted(glob.glob(os.path.join(caminho, "*.png"))):
                img = cv2.imread(arquivo, cv2.IMREAD_GRAYSCALE)
                if img is None:
                    continue
                if img.shape != (LADO, LADO):
                    img = cv2.resize(img, (LADO, LADO))
                chave = img.tobytes()
                if chave in vistos:
                    continue
                vistos.add(chave)
                chars.append(char)
                linhas.append(img.reshape(-1))

        X = (np.stack(linhas).astype(np.float32) if linhas
             else np.zeros((0, LADO * LADO), dtype=np.float32))
        return chars, X

    def _instalar(self, chars, X):
        self._chars = list(chars)
        self._X = np.ascontiguousarray(X, dtype=np.float32)
        self._normas = (self._X * self._X).sum(axis=1)

    def salvar_cache(self, digital=None):
        """Grava a matriz. Instantâneo — são 23 MB de uint8."""
        if not self.usar_cache:
            return
        if digital is None:
            digital = self._impressao_digital()
        try:
            np.savez(self.caminho_do_cache,
                     X=self._X.astype(np.uint8),
                     chars=np.array(self._chars), digital=digital)
            self._cache_sujo = False
        except OSError:
            pass        # sem cache o programa só fica lento, não quebra

    def learn(self, crop_np: np.ndarray, char: str):
        """
        Grava uma amostra nova e a torna consultável na hora.

        **Ligadura passou a ser aceita.** A guarda era `len(char) != 1`, então
        um box marcado como `fi` era descartado em silêncio — apesar de o
        `char_to_folder` ter um ramo `ligature_*` justamente para isso. É a
        mesma classe de perda calada que a F5.2 corrigiu no `.box`.
        """
        if not char:
            return

        # Usar codificacao segura para o nome da pasta
        safe_folder = char_to_folder(char)

        save_dir = os.path.join(self.data_dir, safe_folder)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # Grayscale
        if len(crop_np.shape) == 3:
             img_gray = cv2.cvtColor(crop_np, cv2.COLOR_RGB2GRAY)
        else:
             img_gray = crop_np

        img_resized = cv2.resize(img_gray, (LADO, LADO))

        filename = f"{uuid.uuid4()}.png"
        path = os.path.join(save_dir, filename)

        # cv2.imwrite devolve False em vez de levantar quando não consegue
        # gravar — notoriamente em caminhos não-ASCII no Windows. Foi assim que
        # a pasta 'lower_ä' da base ficou vazia: as amostras eram descartadas em
        # silêncio. Os nomes gerados por char_to_folder são só-ASCII justamente
        # por isso, mas conferir aqui evita perder amostra sem ninguém saber.
        if not cv2.imwrite(path, img_resized):
            raise IOError(f"Não foi possível gravar a amostra em {path}")

        linha = img_resized.reshape(1, -1).astype(np.float32)
        if self.total and (linha == self._X).all(axis=1).any():
            return          # já existe igual; entra no disco, não na matriz

        self._chars.append(char)
        self._X = np.ascontiguousarray(np.vstack([self._X, linha]))
        self._normas = np.append(self._normas, float((linha * linha).sum()))
        self._cache_sujo = True

    def predict(self, crop_np: np.ndarray, threshold=2000.0) -> Tuple[str, float]:
        """
        O vizinho mais próximo, e o quanto ele está perto.

        A distância é a mesma L2 de sempre, calculada por
        `||a-b||² = ||a||² + ||b||² - 2a·b` com `||b||²` pré-calculado. **A
        resposta é idêntica à do laço anterior** — não é aproximação: medido em
        200 consultas reais, mesmo caractere e diferença de confiança 0,000.
        """
        if self.total == 0:
            return "?", 0.0

        if len(crop_np.shape) == 3:
            img_gray = cv2.cvtColor(crop_np, cv2.COLOR_RGB2GRAY)
        else:
            img_gray = crop_np

        alvo = cv2.resize(img_gray, (LADO, LADO)).reshape(-1).astype(np.float32)
        d2 = self._normas - 2.0 * (self._X @ alvo) + float(alvo @ alvo)
        i = int(np.argmin(d2))
        distancia = float(np.sqrt(max(float(d2[i]), 0.0)))

        confianca = 0.0
        if distancia < threshold:
            confianca = max(0.0, 1.0 - distancia / threshold)
        return self._chars[i], confianca
