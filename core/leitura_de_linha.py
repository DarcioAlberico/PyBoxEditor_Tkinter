"""
Ler a **linha**, e não o caractere (F17).

O `english_g2` do EasyOCR é um CRNN treinado em palavra e linha. Usá-lo caractere
a caractere descarta o modelo de linguagem implícito que é a força dele, e é
esse modelo que resolve justamente o que sobra depois da F16 — o par que só o
contexto separa. Medido em 6.953 caracteres de 275 linhas rotuladas:

    por caractere (o melhor da F16)   72,8%
    por linha, com alinhamento        91,2%

Os exemplos dizem o mecanismo melhor que a tabela: `Bib1i0g[aPhY` vira
`Bibliography`, `F0reW0rd` vira `Foreword`, `LeVe1` vira `Level`. Nenhum desses
é decidível olhando um glifo de cada vez — `0` e `o` da mesma fonte diferem em
altura, e `1` e `l` em quase nada.

## O problema: a linha devolve uma string, o programa precisa de um char por box

Não há de onde tirar a posição de cada caractere: o `recognize` devolve uma
caixa só para a faixa inteira, e a saída do CTC não expõe o passo de tempo.

**A regra estrita — aceitar só quando o comprimento bate — cobre pouco.** Medido,
o comprimento bate em 151 das 275 linhas (54,9%), e a política que cai no modo
por caractere nas outras dá 80,4%. Nas linhas em que bate, a leitura por linha
acerta 91,1%; o que falta é como aproveitar isso nas outras 45%.

**A leitura por caractere é a âncora.** Ela tem, por construção, exatamente um
item por box. Alinhar a string da linha contra ela (`notacao._alinhar`, a mesma
distância de edição da F1.7) distribui os caracteres sobre os boxes sem precisar
de posição na imagem: 91,2%, quase o mesmo que nas linhas que batem, agora sobre
todas. O desvio mais comum é a linha trazer caractere **a mais** que boxes (+1 em
34 linhas, +2 em 29), e o alinhamento simplesmente os descarta.

**O buraco na âncora, e ele não é teórico.** Uma leitura por caractere pode vir
vazia, e `"".join` de uma lista com vazio encurta a string: o índice devolvido
pelo alinhamento deixa de ser o índice do box e tudo depois dele anda uma casa.
Por isso o vazio vira `MARCA_DE_VAZIO` antes de juntar — um caractere que não
existe em página nenhuma, que nunca casa com nada e por isso sempre cede a vez
para o que a linha leu.

## A confiança de um caractere que ninguém leu sozinho

O `recognize` devolve **uma** confiança para a faixa inteira, e distribuí-la
igual por todos os boxes seria inventar precisão que não foi medida. O que existe
de verdade é a concordância entre as duas leituras, e é ela que vira confiança:
quando linha e caractere dizem o mesmo, uma corrobora a outra e vale a maior;
quando divergem, a linha venceu mas há dúvida real, e vale a **menor** — que é o
que põe o box na fila de revisão. Medido, a divergência é o sinal que se espera
dela: onde as duas concordam o acerto é alto, e onde divergem é onde o erro se
concentra (ver F17 no ROADMAP).

## O que fica de fora, e volta para o modo por caractere

- **Linha com glifo fora do alfabeto do EasyOCR** — figurinha (♗, ♘) e ligadura.
  São 19% das linhas, e são as de notação, que é o coração do livro; ali a rede
  própria já vai bem. O módulo não sabe disso sozinho: quem chama informa por
  `alfabeto`.
- **Linha com box girado (F8.1) ou em negativo (F10)** — a faixa da linha deixa
  de ser um retângulo em pé na página, e endireitar a faixa inteira é outro
  problema. Uma linha assim não é lida em bloco.
"""

from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from core.box_model import BoxEntry
from core.notacao import _alinhar

#: Ocupa o lugar de uma leitura vazia na âncora, para o índice do alinhamento
#: continuar sendo o índice do box. Não existe em página nenhuma.
MARCA_DE_VAZIO = "\x00"

#: Margem branca em volta da faixa. O reconhecedor foi treinado em recorte com
#: folga; colar no glifo da ponta corta traço.
MARGEM = 8


def quebrar_em_linhas(boxes: Sequence[BoxEntry]) -> List[List[BoxEntry]]:
    """
    Corta uma sequência **já em ordem de leitura** em linhas.

    A linha sai da ordem de leitura, e não da geometria da página: o
    `sort_boxes_reading_order` já resolveu coluna, elemento transversal e pilha
    girada, e refazer isso aqui por coordenada desfaria o trabalho dele —
    voltaria a intercalar as duas colunas. Basta cortar onde a sequência desce
    ou volta para a esquerda.
    """
    linhas: List[List[BoxEntry]] = []
    atual: List[BoxEntry] = []
    for b in boxes:
        if atual:
            ant = atual[-1]
            desceu = (b.y1 + b.y2) / 2 > ant.y2
            voltou = b.x1 < ant.x1 - (ant.y2 - ant.y1)
            if desceu or voltou:
                linhas.append(atual)
                atual = []
        atual.append(b)
    if atual:
        linhas.append(atual)
    return linhas


def linhas_da_pagina(boxes: Sequence[BoxEntry]) -> List[List[BoxEntry]]:
    """
    Os boxes agrupados em linhas, em ordem de leitura.

    O import é tardio de propósito: quem só quer `distribuir` ou `confianca`
    não precisa carregar o `box_service` atrás.
    """
    if not boxes:
        return []
    from core.services.box_service import BoxService

    return quebrar_em_linhas(BoxService.sort_boxes_reading_order(list(boxes)))


def faixa_da_linha(pagina: np.ndarray,
                   linha: Sequence[BoxEntry]) -> Optional[np.ndarray]:
    """A tira da página que cobre a linha inteira, com margem branca."""
    if not linha:
        return None
    topo = max(0, min(b.y1 for b in linha))
    base = min(pagina.shape[0], max(b.y2 for b in linha))
    x1 = max(0, min(b.x1 for b in linha))
    x2 = min(pagina.shape[1], max(b.x2 for b in linha))
    if base <= topo or x2 <= x1:
        return None

    tira = pagina[topo:base, x1:x2]
    if tira.size == 0:
        return None
    pad = ((MARGEM, MARGEM), (MARGEM, MARGEM)) + ((0, 0),) * (tira.ndim - 2)
    return np.pad(tira, pad, mode="constant", constant_values=255)


def em_bloco(linha: Sequence[BoxEntry], alfabeto: Optional[str] = None) -> bool:
    """
    A linha pode ser lida de uma vez?

    Ver o cabeçalho do módulo: girado e negativo não têm faixa retangular em pé,
    e glifo fora do alfabeto do reconhecedor faz a linha ler outra coisa no
    lugar dele — o que desloca o alinhamento em vez de errar um caractere só.
    """
    if len(linha) < 2:
        return False
    for b in linha:
        if getattr(b, "angulo", 0) or getattr(b, "negativo", False):
            return False
        if alfabeto is not None and (len(b.char or "") > 1
                                     or (b.char and b.char not in alfabeto)):
            return False
    return True


def distribuir(por_caractere: Sequence[str], texto: str) -> List[str]:
    """
    Espalha `texto` sobre os boxes, com `por_caractere` de âncora.

    Devolve uma lista do tamanho de `por_caractere`. Onde a linha não tem o que
    dizer, o que já estava fica.
    """
    ancora = "".join(c if c else MARCA_DE_VAZIO for c in por_caractere)
    assert len(ancora) == len(por_caractere), "a âncora perdeu o índice do box"

    saida = list(por_caractere)
    for pos, ch in _alinhar(ancora, texto):
        if pos is not None and ch:
            saida[pos] = ch
    return saida


def confianca(concordam: bool, conf_linha: float, conf_char: float) -> float:
    """
    A concordância entre as duas leituras é o que se mede; a confiança sai dela.

    Concordar é corroborar, e vale a maior. Divergir é dúvida de verdade — a
    linha venceu, mas a leitura do glifo dizia outra coisa —, e vale a menor,
    que é o que manda o box para a revisão em vez de escondê-lo.
    """
    a, b = max(0.0, conf_linha), max(0.0, conf_char)
    return max(a, b) if concordam else min(a, b)


def ler_pagina(
    pagina: np.ndarray,
    linhas: Sequence[Sequence[BoxEntry]],
    ler_faixa: Callable[[np.ndarray], Tuple[str, float]],
    ler_caractere: Callable[[BoxEntry], Tuple[str, float]],
    alfabeto: Optional[str] = None,
    cancelado: Optional[Callable[[], bool]] = None,
    progresso: Optional[Callable[[int, int], None]] = None,
) -> List[Tuple[BoxEntry, str, float, str]]:
    """
    `(box, char, confiança, fonte)` para cada box de `linhas`, em ordem.

    `fonte` é `easyocr_linha` quando a linha decidiu e `easyocr` quando a
    leitura por caractere respondeu sozinha.
    """
    saida = []
    for i, linha in enumerate(linhas):
        if cancelado is not None and cancelado():
            break

        por_char = [ler_caractere(b) for b in linha]
        chars = [c for c, _ in por_char]
        confs = [f for _, f in por_char]

        texto, conf_linha = "", 0.0
        if em_bloco(linha, alfabeto):
            tira = faixa_da_linha(pagina, linha)
            if tira is not None:
                texto, conf_linha = ler_faixa(tira)
                texto = texto.replace(" ", "")

        if texto:
            final = distribuir(chars, texto)
            for b, ch, antes, cf in zip(linha, final, chars, confs):
                saida.append((b, ch,
                              confianca(ch == antes, conf_linha, cf),
                              "easyocr_linha" if ch else "vazio"))
        else:
            for b, ch, cf in zip(linha, chars, confs):
                saida.append((b, ch, cf, "easyocr" if ch else "vazio"))

        if progresso is not None:
            progresso(i + 1, len(linhas))
    return saida
