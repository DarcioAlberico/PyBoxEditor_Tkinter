"""
Avaliação de uma página inteira contra um `.box` rotulado à mão.

O `core/avaliacao.py` mede o **classificador** sobre recortes já segmentados. Ele
não enxerga o erro que aparece antes disso: um box a mais, um box a menos, um
glifo partido no meio. Foi exatamente esse o defeito que passou pela validação da
F1.5 — a propriedade verificada era "zero pedaços estreitos novos", e as duas
metades de uma figurina partida são largas demais para caírem nela.

Aqui a unidade é a página: emparelha os boxes gerados com os rotulados e mede

    recall     rotulados recuperados com o caractere certo / rotulados
    precisão   idem / boxes gerados
    espúrios   gerados que não casaram com rotulado nenhum

**Precisão e recall dizem coisas diferentes aqui, e é preciso os dois.** Uma
segmentação que parte glifos ao meio quase não mexe no recall — o pedaço da
esquerda ainda casa com o rotulado — mas despeja um caractere inventado no texto
a cada corte, e isso só aparece na precisão. Medindo a página 0108 só por recall,
o separador de glifos parecia inofensivo (87,0% contra 86,8%); pela precisão ele
custa 5,8 pontos (82,1% contra 87,9%).

Formato do `.box`: o do Tesseract, `char x1 y1 x2 y2 página`, com **y medido a
partir da base** da imagem. `carregar_box` converte para o topo, que é o que o
`BoxEntry` usa.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from core import formato_box
from core.box_model import BoxEntry


# O livro usa um conjunto de figurinas só para os dois lados (F1.1) e quem
# rotulou à mão escreveu a letra do lance. Comparar o glifo cru marcaria como
# erro uma leitura que está certa.
EQUIVALENTES = {
    "♔": "K", "♕": "Q", "♖": "R", "♗": "B",
    "♘": "N", "♙": "P",
    "♚": "K", "♛": "Q", "♜": "R", "♝": "B",
    "♞": "N", "♟": "P",
}


def normalizar(char: str) -> str:
    return EQUIVALENTES.get(char, char)


def carregar_box(caminho: str, altura: int,
                 origem_inferior: bool = True) -> List[BoxEntry]:
    """Lê um `.box` do Tesseract. `altura` é a da imagem, para inverter o y.

    Reexportado de `core.formato_box` para não quebrar quem já importava daqui;
    o formato mora lá desde a F5.2.
    """
    return formato_box.ler(caminho, altura, origem_inferior)


def _centro_dentro(gerado: BoxEntry, rotulado: BoxEntry) -> bool:
    cx = (gerado.x1 + gerado.x2) / 2
    cy = (gerado.y1 + gerado.y2) / 2
    return (rotulado.x1 <= cx <= rotulado.x2
            and rotulado.y1 <= cy <= rotulado.y2)


def _iou(a: BoxEntry, b: BoxEntry) -> float:
    ix = max(0, min(a.x2, b.x2) - max(a.x1, b.x1))
    iy = max(0, min(a.y2, b.y2) - max(a.y1, b.y1))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    uniao = ((a.x2 - a.x1) * (a.y2 - a.y1)
             + (b.x2 - b.x1) * (b.y2 - b.y1) - inter)
    return inter / uniao if uniao > 0 else 0.0


@dataclass
class Resultado:
    gerados: int
    rotulados: int
    casados: int
    certos: int
    espurios: int
    perdidos: int
    pares: List[Tuple[int, int]]

    @property
    def recall(self) -> float:
        return 100.0 * self.certos / self.rotulados if self.rotulados else 0.0

    @property
    def precisao(self) -> float:
        return 100.0 * self.certos / self.gerados if self.gerados else 0.0

    @property
    def f1(self) -> float:
        r, p = self.recall, self.precisao
        return 2 * r * p / (r + p) if r + p else 0.0

    def __str__(self):
        return (f"recall {self.recall:5.1f}%  precisão {self.precisao:5.1f}%  "
                f"F1 {self.f1:5.1f}  espúrios {self.espurios:>4}")


def comparar(gerados: Sequence[BoxEntry],
             rotulados: Sequence[BoxEntry]) -> Resultado:
    """
    Emparelha por **centro dentro do rotulado**, desempatando por IoU.

    Centro em vez de IoU puro porque a fronteira do box gerado nunca bate com a
    do rotulado à mão, e um limiar de IoU alto marcaria como espúrio um box que
    está certo. O que interessa é "existe um box para este caractere e ele foi
    lido certo", não a fidelidade da moldura.
    """
    usados: set = set()
    pares: List[Tuple[int, int]] = []

    for j, rotulado in enumerate(rotulados):
        melhor, melhor_iou = None, -1.0
        for i, gerado in enumerate(gerados):
            if i in usados or not _centro_dentro(gerado, rotulado):
                continue
            v = _iou(gerado, rotulado)
            if v > melhor_iou:
                melhor, melhor_iou = i, v
        if melhor is not None:
            usados.add(melhor)
            pares.append((melhor, j))

    certos = sum(1 for i, j in pares
                 if normalizar(gerados[i].char) == normalizar(rotulados[j].char))

    return Resultado(gerados=len(gerados), rotulados=len(rotulados),
                     casados=len(pares), certos=certos,
                     espurios=len(gerados) - len(pares),
                     perdidos=len(rotulados) - len(pares), pares=pares)


def classificar_cortes(pais: Sequence[BoxEntry], filhos: Sequence[BoxEntry],
                       rotulados: Sequence[BoxEntry]) -> Dict[str, int]:
    """
    Cada corte foi legítimo?

    Um box **pai** que cobre o centro de dois ou mais rotulados estava mesmo
    colado, e cortá-lo é o objetivo da F1.5. Um pai que cobre um só rotulado é
    um glifo inteiro, e cortá-lo é estrago. É a distinção que a validação
    original não fazia — ela só contava se os pedaços tinham ficado estreitos.
    """
    def cobertos(pai):
        return sum(1 for r in rotulados
                   if pai.x1 <= (r.x1 + r.x2) / 2 <= pai.x2
                   and pai.y1 <= (r.y1 + r.y2) / 2 <= pai.y2)

    # um pai foi cortado se não sobreviveu idêntico na saída
    intactos = {(b.x1, b.y1, b.x2, b.y2) for b in filhos}

    conta = {"cortes_legitimos": 0, "cortes_falsos": 0, "cortes_sem_rotulo": 0,
             "colados_intactos": 0}
    for pai in pais:
        n = cobertos(pai)
        if (pai.x1, pai.y1, pai.x2, pai.y2) in intactos:
            if n >= 2:
                conta["colados_intactos"] += 1
            continue
        if n >= 2:
            conta["cortes_legitimos"] += 1
        elif n == 1:
            conta["cortes_falsos"] += 1
        else:
            conta["cortes_sem_rotulo"] += 1
    return conta
