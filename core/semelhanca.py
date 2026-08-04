"""
Quais boxes da página são o mesmo glifo que este? (F3.6)

Corrigir um `e` lido como `c` e ter de repetir a correção nos outros 300 é o que
faz a revisão de uma página custar horas. Aqui está o critério que responde
"quais são os outros 300".

**O critério é a imagem, não o caractere.** Casar por caractere lido acharia os
300 `c` errados, mas junto viriam os `c` legítimos — e o lote os estragaria.

Medido nas 9 páginas rotuladas à mão (Kasparov + Aagaard, ~9.400 caracteres),
sobre todos os pares de boxes de cada página, com o `?` do rotulador — que ali é
"não sei", não o glifo — fora da conta:

| critério | limiar | precisão | cobertura |
|---|---:|---:|---:|
| imagem | 0,20 | 98,91% | 64,6% |
| imagem | 0,30 | 92,77% | 69,1% |
| imagem + mesma leitura | 0,20 | **99,29%** | 64,5% |
| imagem + mesma leitura | 0,30 | **99,30%** | 69,1% |

`precisão` = dos pares que o critério aceita, quantos são mesmo o mesmo
caractere. `cobertura` = dos pares do mesmo caractere, quantos ele acha.

**O que a segunda linha do par muda: ela segura a precisão quando se afrouxa o
limiar.** Só com imagem, ir de 0,20 a 0,30 troca 4,5 pontos de cobertura por 6
de precisão. Com a leitura junto, a precisão não se move e a cobertura sobe de
graça. A razão é simples: dois glifos parecidos que o OCR já leu diferente
(`0`/`o` quando um saiu certo) deixam de ser candidatos.

**A precisão não passa de ~99,3%, e isso não é ajuste de limiar que resolva.** O
que sobra são homóglifos de verdade — `0`×`o`, `9`×`g`, `1`×`i`, `P`×`p`,
`T`×`t`, `B`×`b`, `C`×`c` — em que as duas imagens *são* quase iguais e o OCR
leu as duas igual. Nenhum descritor de imagem os separa; quem os separa é o
contexto, que é trabalho da F1.7.

Consequência de projeto, e é a decisão principal desta fase: **um em cada ~145
boxes do lote sairia errado**, então aplicar em silêncio está fora de questão. O
resultado vai para uma pré-visualização com os recortes à vista, e a lista sai
**ordenada por distância** — o duvidoso fica no fim, que é onde o olho deve
parar.
"""

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from core.box_model import BoxEntry


#: Lado do descritor. 24 porque é o menor que ainda separa `e` de `c` nas
#: páginas medidas; 32 (o do `CharacterLearner`) não muda a precisão e custa
#: 78% mais memória por box.
LADO = 24

#: Um `.` e um `O` preenchem o mesmo quadrado depois do redimensionamento — a
#: proporção precisa entrar no critério por fora. A altura entra junto porque
#: estes livros misturam corpo de fonte na mesma página (F1.5).
TOL_PROPORCAO = 1.15
TOL_ALTURA = 1.20

#: Quanto se afrouxa o casamento. Com a mesma-leitura ligada a precisão fica
#: estável nos três, então o rigor é escolha de cobertura, não de risco.
RIGOR = {"estrito": 0.10, "normal": 0.20, "amplo": 0.30}
LIMIAR_PADRAO = RIGOR["normal"]


def _cinza(imagem) -> np.ndarray:
    arr = np.asarray(imagem)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    return arr


def descritor(recorte: np.ndarray) -> Optional[np.ndarray]:
    """
    Recorte do glifo -> vetor de LADO*LADO em [0,1], tinta alta.

    Devolve None para recorte vazio. Trabalha em tom de cinza, não no
    binarizado: medido, o cinza cobre 64,5% dos pares contra 54,5% do
    binarizado com a mesma precisão — a binarização joga fora a espessura do
    traço, que é justamente o que distingue dois glifos parecidos.
    """
    if recorte is None or recorte.size == 0:
        return None
    r = cv2.resize(_cinza(recorte).astype(np.float32), (LADO, LADO),
                   interpolation=cv2.INTER_AREA)
    return (255.0 - r).reshape(-1) / 255.0


def distancia(a: np.ndarray, b: np.ndarray) -> float:
    """L2 normalizada pelo número de células, para o limiar não depender de LADO."""
    return float(np.linalg.norm(a - b) / np.sqrt(a.size))


def _geometria_compativel(a: BoxEntry, b: BoxEntry) -> bool:
    la, ha = max(1, a.width), max(1, a.height)
    lb, hb = max(1, b.width), max(1, b.height)
    pa, pb = la / ha, lb / hb
    return (max(pa / pb, pb / pa) <= TOL_PROPORCAO
            and max(ha / hb, hb / ha) <= TOL_ALTURA)


def encontrar_semelhantes(imagem, boxes: Sequence[BoxEntry], indice: int,
                          limiar: float = LIMIAR_PADRAO,
                          leitura: Optional[str] = None
                          ) -> List[Tuple[int, float]]:
    """
    Índices dos boxes que são o mesmo glifo que `boxes[indice]`, com a distância.

    `leitura` é o caractere que os candidatos devem estar mostrando agora. É o
    segundo filtro da tabela do módulo, e quem chama tem de passar a leitura
    **anterior à correção**: o box de referência já foi corrigido para `e`; os
    outros 300 ainda estão em `c`. Com None, casa só pela imagem.

    A saída sai ordenada por distância — o casamento mais seguro primeiro, o
    duvidoso por último. O box de referência não entra.
    """
    if not (0 <= indice < len(boxes)):
        return []

    arr = _cinza(imagem)
    referencia = boxes[indice]
    alvo = descritor(_recortar(arr, referencia))
    if alvo is None:
        return []

    achados = []
    for i, b in enumerate(boxes):
        if i == indice:
            continue
        if leitura is not None and b.char != leitura:
            continue
        if not _geometria_compativel(referencia, b):
            continue
        d = descritor(_recortar(arr, b))
        if d is None:
            continue
        dist = distancia(alvo, d)
        if dist <= limiar:
            achados.append((i, dist))

    achados.sort(key=lambda p: p[1])
    return achados


def _recortar(arr: np.ndarray, b: BoxEntry) -> np.ndarray:
    h, w = arr.shape[:2]
    y1, y2 = max(0, b.y1), min(h, b.y2)
    x1, x2 = max(0, b.x1), min(w, b.x2)
    if y2 <= y1 or x2 <= x1:
        return np.empty((0, 0), dtype=arr.dtype)
    return arr[y1:y2, x1:x2]
