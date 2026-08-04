import os
import cv2
import numpy as np
import uuid
import glob
from typing import Tuple, List, Optional


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

    # Ligaduras (ex: 'fi', 'ffi', 'f7')
    if len(char) > 1:
        # Alfanumérico ASCII cabe no nome da pasta e fica legível.
        # Antes o teste era isalpha(), o que jogava 'f7' — casa de xadrez,
        # comum como box único nestes livros — no ramo hexadecimal.
        if char.isalnum() and char.isascii():
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


class CharacterLearner:
    def __init__(self, data_dir="training_data"):
        self.data_dir = data_dir
        self.reference_images = []  # List of (char, image_array)
        self.ensure_dir()
        self.load_references()

    def ensure_dir(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def load_references(self):
        """Loads all reference images into memory."""
        self.reference_images = []
        if not os.path.exists(self.data_dir):
            return

        for char_folder in os.listdir(self.data_dir):
            folder_path = os.path.join(self.data_dir, char_folder)
            if not os.path.isdir(folder_path):
                continue
            
            # Decodificar nome da pasta para o caractere real
            char = folder_to_char(char_folder)

            for img_file in glob.glob(os.path.join(folder_path, "*.png")):
                try:
                    img = cv2.imread(img_file, cv2.IMREAD_GRAYSCALE)
                    if img is not None:
                        img = cv2.resize(img, (32, 32))
                        self.reference_images.append((char, img))
                except Exception as e:
                    print(f"Error loading {img_file}: {e}")
        
        print(f"Loaded {len(self.reference_images)} reference samples.")

    def learn(self, crop_np: np.ndarray, char: str):
        """Saves a new reference sample."""
        if not char or len(char) != 1:
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

        img_resized = cv2.resize(img_gray, (32, 32))

        filename = f"{uuid.uuid4()}.png"
        path = os.path.join(save_dir, filename)

        # cv2.imwrite devolve False em vez de levantar quando não consegue
        # gravar — notoriamente em caminhos não-ASCII no Windows. Foi assim que
        # a pasta 'lower_ä' da base ficou vazia: as amostras eram descartadas em
        # silêncio. Os nomes gerados por char_to_folder são só-ASCII justamente
        # por isso, mas conferir aqui evita perder amostra sem ninguém saber.
        if not cv2.imwrite(path, img_resized):
            raise IOError(f"Não foi possível gravar a amostra em {path}")

        self.reference_images.append((char, img_resized))

    def predict(self, crop_np: np.ndarray, threshold=2000.0) -> Tuple[str, float]:
        """
        Finds the nearest neighbor.
        Returns (character, confidence). 
        """
        if not self.reference_images:
            return "?", 0.0

        if len(crop_np.shape) == 3:
             img_gray = cv2.cvtColor(crop_np, cv2.COLOR_RGB2GRAY)
        else:
             img_gray = crop_np

        target = cv2.resize(img_gray, (32, 32))
        
        best_dist = float('inf')
        best_char = "?"

        for char, ref_img in self.reference_images:
            dist = cv2.norm(target, ref_img, cv2.NORM_L2)
            if dist < best_dist:
                best_dist = dist
                best_char = char
        
        confidence = 0.0
        if best_dist < threshold:
             confidence = 1.0 - (best_dist / threshold)
             confidence = max(0.0, confidence)
        
        return best_char, confidence
