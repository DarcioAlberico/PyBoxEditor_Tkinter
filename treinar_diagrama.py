"""
Constrói o modelo que lê as peças dos diagramas (F7.1).

    python treinar_diagrama.py

Lê as amostras rotuladas de `training_data_diagrama/` e grava
`core/dados/diagrama_modelo.npz`. As amostras são **resíduos** — a casa menos o
fundo estimado daquele diagrama —, gravadas deslocadas de 128 para poderem ser
olhadas como imagem. Ver `core/diagrama.py` para o porquê do resíduo.

O modelo é um banco de vizinhos, não uma rede: são 361 amostras de um livro só,
e uma rede treinada nisso decoraria. O HOG descreve a silhueta, o PCA corta a
dimensão de 1.764 para 32 sem perder acerto (medido: 94,5% nas duas), e a
classificação é o voto dos 3 vizinhos mais próximos.
"""

import os
import sys

import cv2
import numpy as np

DADOS = "training_data_diagrama"
DESTINO = os.path.join("core", "dados", "diagrama_modelo.npz")

LADO = 48
#: HOG de célula 6 e 9 orientações. Medido contra célula 8 e 12 e contra 12
#: orientações: 94,5% nas melhores de cada, então ficou a mais barata.
HOG = cv2.HOGDescriptor((LADO, LADO), (12, 12), (6, 6), (6, 6), 9)
#: 32 componentes. Com 64 e 128 o acerto é o mesmo e o arquivo cresce.
COMPONENTES = 32


def descritor(residuo: np.ndarray) -> np.ndarray:
    """Resíduo da casa -> vetor HOG normalizado."""
    if residuo.shape != (LADO, LADO):
        residuo = cv2.resize(residuo, (LADO, LADO), interpolation=cv2.INTER_AREA)
    normal = cv2.normalize(residuo, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    v = HOG.compute(normal).ravel()
    return v / (np.linalg.norm(v) + 1e-6)


def carregar_amostras(pasta=DADOS):
    """[(simbolo, residuo)] a partir de `<pasta>/<cor>/<LETRA>/*.png`."""
    saida = []
    for cor in ("branca", "preta"):
        base = os.path.join(pasta, cor)
        if not os.path.isdir(base):
            continue
        for letra in sorted(os.listdir(base)):
            simbolo = letra.upper() if cor == "branca" else letra.lower()
            for nome in sorted(os.listdir(os.path.join(base, letra))):
                if not nome.endswith(".png"):
                    continue
                img = cv2.imread(os.path.join(base, letra, nome),
                                 cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    saida.append((simbolo, img.astype(np.float32) - 128.0))
    return saida


def main():
    amostras = carregar_amostras()
    if not amostras:
        print(f"nenhuma amostra em {DADOS}/")
        return 1

    simbolos = np.array([s for s, _ in amostras])
    X = np.stack([descritor(r) for _, r in amostras]).astype(np.float32)

    media = X.mean(axis=0)
    # SVD e não uma lib de PCA: numpy já está aqui e são 361 x 1764.
    _, _, Vt = np.linalg.svd(X - media, full_matrices=False)
    base = Vt[:COMPONENTES].astype(np.float32)

    reduzido = (X - media) @ base.T
    reduzido /= np.linalg.norm(reduzido, axis=1, keepdims=True) + 1e-6

    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    np.savez_compressed(DESTINO, media=media, base=base,
                        amostras=reduzido.astype(np.float32), simbolos=simbolos)

    import collections
    conta = collections.Counter(simbolos.tolist())
    print(f"{len(amostras)} amostras, {X.shape[1]} dimensões -> {COMPONENTES}")
    print("  " + "  ".join(f"{s}:{conta[s]}" for s in "PNBRQKpnbrqk"))
    print(f"gravado em {DESTINO} ({os.path.getsize(DESTINO)/1e3:.0f} KB)")

    magras = [s for s in "PNBRQKpnbrqk" if conta[s] < 12]
    if magras:
        print(f"\nclasses com menos de 12 amostras: {' '.join(magras)}")
        print("são as que mais erram; colher mais diagramas ajuda essas primeiro.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
