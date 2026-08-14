"""
A calibração medida **na página real**, e não no split de validação (F27).

`core/calibracao.py` é a matemática — temperatura, ECE, AUROC — e não importa
torch nem cv2. Aqui fica o que falta para aplicá-la: achar as páginas rotuladas,
segmentá-las como a aplicação segmenta, e colher os logits do modelo sobre elas.

**Por que na página e não no split.** O split sai de `training_data`, que é
recorte já segmentado e limpo: ali o modelo acerta 99,93% e o ECE é 0,0003 — não
há o que calibrar, e a temperatura ajustada dá 0,995. Em página real a acurácia
cai para ~93% e o ECE sobe para ~0,033. É na página que a confiança é consumida,
então é na página que ela tem de estar certa.

**Este módulo existia dentro de `calibrar_modelo.py`.** Saiu de lá na F27, para
o treino poder calibrar sozinho no fim — e o núcleo não pode importar um script
de medição do diretório raiz. `calibrar_modelo.py` passou a consumi-lo, e
continua sendo quem mostra as tabelas.

Custo, medido nas 10 páginas rotuladas e 10.549 caracteres: 8,6 s para colher e
11,6 s para ajustar. Contra os minutos de um treino, é o que tornou a F27
possível.
"""

import glob
import os
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
from PIL import Image

from core import calibracao
from core.avaliacao_pagina import carregar_box, comparar, normalizar
from core.services.box_service import BoxService

#: Onde as páginas rotuladas à mão moram. É conhecimento do projeto, não do
#: script de medição: quem quiser calibrar precisa saber disto tanto quanto
#: quem quiser medir.
PASTAS_DE_IMAGEM = ("ilovepdf_pages-to-jpg", "Box")

#: Abaixo disto a página é um retalho e não uma amostra — entra com peso e não
#: paga o ruído que traz.
MIN_ROTULADOS = 50


def paginas_rotuladas(raiz: str = ".") -> List[Tuple[str, str]]:
    """[(imagem, .box)] — a imagem pode estar na pasta do `.box` ou na do PDF."""
    achados = []
    for pasta in PASTAS_DE_IMAGEM:
        for cx in sorted(glob.glob(os.path.join(raiz, pasta, "*.box"))):
            nome = os.path.splitext(os.path.basename(cx))[0]
            for onde in ((os.path.dirname(cx),)
                         + tuple(os.path.join(raiz, p) for p in PASTAS_DE_IMAGEM)):
                imagem = next(
                    (p for p in (os.path.join(onde, nome + e)
                                 for e in (".jpg", ".png", ".jpeg"))
                     if os.path.exists(p)), None)
                if imagem:
                    achados.append((imagem, cx))
                    break
    return achados


@torch.no_grad()
def _logits(model, device, recortes, lote=512) -> np.ndarray:
    import cv2

    imgs = np.stack([cv2.resize(r, (32, 32)) for r in recortes])
    x = torch.from_numpy(imgs).float().div_(255.0).unsqueeze(1).to(device)
    saida = [model(x[i:i + lote]).cpu().numpy() for i in range(0, len(x), lote)]
    return np.concatenate(saida)


def coletar(model, meta: Dict, device, separar_colados: bool = True,
            raiz: str = ".") -> List[Tuple[str, np.ndarray, np.ndarray]]:
    """
    `[(nome, logits, máscara de classes aceitáveis)]` por página rotulada.

    A máscara, e não o índice da classe certa, porque **mais de uma classe pode
    estar certa**: `normalizar` junta equivalentes (o traço e o travessão, por
    exemplo), e cravar um índice contaria como erro uma leitura que a avaliação
    da página aceita.
    """
    idx_to_char = {int(k): v for k, v in meta["idx_to_char"].items()}
    num_classes = meta["num_classes"]

    aceitaveis_de: Dict[str, List[int]] = {}
    for k, c in idx_to_char.items():
        aceitaveis_de.setdefault(normalizar(c), []).append(k)

    paginas = []
    for imagem, caminho_box in paginas_rotuladas(raiz):
        img = Image.open(imagem).convert("L")
        rotulados = carregar_box(caminho_box, img.size[1])
        if len(rotulados) < MIN_ROTULADOS:
            continue

        arr = np.array(img)
        boxes = BoxService.generate_boxes_opencv(
            img, separar_colados=separar_colados)
        if not boxes:
            continue
        lg = _logits(model, device, [arr[b.y1:b.y2, b.x1:b.x2] for b in boxes])
        previsto = lg.argmax(axis=1)
        for i, b in enumerate(boxes):
            b.char = idx_to_char.get(int(previsto[i]), "?")

        linhas, mascaras = [], []
        for i, j in comparar(boxes, rotulados).pares:
            classes = aceitaveis_de.get(normalizar(rotulados[j].char))
            if not classes:
                continue        # rótulo que o modelo nem tem como classe
            m = np.zeros(num_classes, dtype=bool)
            m[classes] = True
            linhas.append(lg[i])
            mascaras.append(m)

        if linhas:
            paginas.append((os.path.basename(imagem), np.stack(linhas),
                            np.stack(mascaras)))
    return paginas


#: O intervalo em que a temperatura é procurada. Explícito aqui, e não deixado
#: no padrão de `ajustar_temperatura`, porque `no_limite` compara contra ele:
#: os dois têm de ser o mesmo número ou a verificação mente.
LIMITES = (0.4, 10.0)


def no_limite(T: float, tol: float = 1e-6) -> bool:
    """
    A busca parou na borda do intervalo?

    Quando para, o ajuste **não convergiu dentro dele** — e o valor da borda não
    é uma temperatura medida, é o fim da régua. Acontece quando o modelo e as
    páginas rotuladas não combinam: um modelo de outra base erra quase tudo com
    confiança alta, e a busca empurra a temperatura para o teto tentando
    amaciá-la.

    Isto importa desde a F27, em que a calibração passou a rodar sozinha. Antes,
    quem rodava `calibrar_modelo.py` via as tabelas e julgava; automatizada, ela
    gravaria o valor de borda calada — e T no teto esmaga toda a confiança,
    então nada mais passaria pelo `NEURAL_THRESHOLD` e a cadeia inteira mudaria
    de comportamento sem ninguém pedir.
    """
    return T <= LIMITES[0] * (1 + tol) or T >= LIMITES[1] * (1 - tol)


class SemPaginasRotuladas(Exception):
    """Não há em que calibrar. Não é falha do modelo nem do treino."""


def ajustar(model, meta: Dict, device, criterio: str = "ece",
            raiz: str = ".") -> Tuple[float, int, int]:
    """
    `(temperatura, páginas, caracteres)` para o modelo dado.

    Levanta `SemPaginasRotuladas` quando não há nada em que medir — que é o
    estado normal de quem nunca rotulou uma página, e não um erro.
    """
    paginas = coletar(model, meta, device, raiz=raiz)
    if not paginas:
        raise SemPaginasRotuladas(
            "nenhuma página rotulada encontrada em "
            + " ou ".join(PASTAS_DE_IMAGEM))

    logits = np.concatenate([l for _n, l, _m in paginas])
    mascaras = np.concatenate([m for _n, _l, m in paginas])
    T = calibracao.ajustar_temperatura(logits, mascaras, criterio=criterio,
                                       limites=LIMITES)
    return float(T), len(paginas), int(len(logits))


def gravar_temperatura(meta_path: str, temperatura: float) -> None:
    """
    Reescreve **só** a temperatura, preservando o resto do metadado.

    Reler e regravar, em vez de o chamador montar o dicionário: o metadado tem
    `modelo_sha256` e `classes_sha256` amarrados ao par de arquivos, e remontá-lo
    de fora é o caminho para dessincronizá-los sem ninguém notar (F7.3).
    """
    import json

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    meta["temperatura"] = float(temperatura)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
