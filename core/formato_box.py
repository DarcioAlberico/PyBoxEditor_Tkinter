"""
Leitura e escrita do formato `.box` do Tesseract — um lugar só.

Uma linha é `char x1 y1 x2 y2 página`, separada por espaços, com **y medido a
partir da base** da imagem. O `BoxEntry` mede a partir do topo, então toda
conversão de eixo acontece aqui.

Havia dois leitores divergentes (`main_window._load_box_from_path` e
`avaliacao_pagina.carregar_box`) e um escritor que perdia dado calado. O que a
F5.2 corrigiu:

- **Ligadura truncada.** O escritor gravava `char[0]`. Um box marcado como `fi`
  voltava do disco como `f`. O Tesseract aceita mais de um caractere no primeiro
  campo — é assim que ele próprio representa ligadura —, então gravar a string
  inteira é *mais* compatível com o formato, não menos.

- **`~` real virava vazio.** O `~` é o marcador de "box sem caractere", e um `~`
  digitado pelo usuário era indistinguível dele.

- **Espaço quebrava a linha.** Um caractere que é espaço deixava a linha com 5
  campos; o leitor descartava a linha inteira e o box sumia.

O escape resolve os dois últimos: na escrita, `\\`, `~`, espaço e tabulação
saem como `\\\\`, `\\~`, `\\s` e `\\t`. O primeiro campo fica, por construção,
sem espaço em branco — a linha sempre tem 6 campos.

**Arquivo antigo continua lendo igual.** Nenhum `.box` já gravado contém `\\`,
porque nada nunca o escreveu; um `~` sozinho segue significando vazio, que é o
que os arquivos antigos queriam dizer. A ambiguidade do `~` real não tem como
ser desfeita retroativamente — só deixa de ser criada daqui em diante.

## O sétimo campo, do texto girado (F8.1)

Um box de texto vertical guarda o ângulo num **sétimo campo**, depois do número
da página. Ele só é escrito quando o ângulo não é zero: uma página sem texto
girado continua gravando o arquivo byte a byte igual ao de antes, e quem lê só
os seis campos do Tesseract não vê diferença nenhuma.

## O oitavo campo, do texto em negativo (F10)

Mesma regra, um campo adiante: `1` quando o glifo está impresso claro sobre
escuro, e nada quando não está. Escrever o oitavo obriga a escrever o sétimo —
um `0` de ângulo aparece nessa linha para o campo seguinte ter onde ficar, e é
a única situação em que ele é gravado.
"""

from typing import List, Optional, Sequence

from core.box_model import BoxEntry


#: Primeiro campo de um box sem caractere.
VAZIO = "~"

_ESCAPAR = {"\\": "\\\\", "~": "\\~", " ": "\\s", "\t": "\\t"}
_DESESCAPAR = {"\\": "\\", "~": "~", "s": " ", "t": "\t"}


def codificar_char(char: str) -> str:
    """Caractere do box -> primeiro campo da linha."""
    if not char:
        return VAZIO
    return "".join(_ESCAPAR.get(c, c) for c in char)


def decodificar_char(campo: str) -> str:
    """Primeiro campo da linha -> caractere do box."""
    if campo == VAZIO:
        return ""

    saida = []
    i = 0
    while i < len(campo):
        c = campo[i]
        if c == "\\" and i + 1 < len(campo):
            seguinte = campo[i + 1]
            if seguinte in _DESESCAPAR:
                saida.append(_DESESCAPAR[seguinte])
                i += 2
                continue
            # Barra invertida solta: preserva o par como veio, em vez de
            # engolir a barra. Ler é sempre menos destrutivo que adivinhar.
            saida.append(c)
            i += 1
            continue
        saida.append(c)
        i += 1
    return "".join(saida)


def formatar_linha(box: BoxEntry, altura: int, pagina: int = 0) -> str:
    """Uma linha do `.box`, com o y já invertido para a base da imagem."""
    linha = (f"{codificar_char(box.char)} {box.x1} {altura - box.y2} "
             f"{box.x2} {altura - box.y1} {pagina}")
    angulo = getattr(box, "angulo", 0) % 360
    if getattr(box, "negativo", False):
        return f"{linha} {angulo} 1"
    return f"{linha} {angulo}" if angulo else linha


def analisar_linha(linha: str, altura: int,
                   origem_inferior: bool = True) -> Optional[BoxEntry]:
    """
    Uma linha -> `BoxEntry`, ou None se a linha não for um box.

    Cinco campos numéricos significam que o primeiro campo era um espaço
    literal — é como o Tesseract grava o caractere espaço. Antes a linha era
    descartada e o box sumia.

    O sétimo campo, quando existe, é o ângulo do texto girado (F8.1), e o
    oitavo é a polaridade do texto em negativo (F10). Um valor que não seja 0,
    90, 180 ou 270 no sétimo — ou que não seja `1` no oitavo — é ignorado em vez
    de rejeitar a linha: os campos são extensão nossa, e um arquivo de terceiro
    pode usá-los para outra coisa. Perder o ângulo custa menos do que perder o
    box.
    """
    campos = linha.strip().split()
    if not campos:
        return None

    angulo, negativo = 0, False
    if len(campos) >= 6:
        char, coords = decodificar_char(campos[0]), campos[1:5]
        if len(campos) >= 7:
            try:
                candidato = int(campos[6]) % 360
            except ValueError:
                candidato = 0
            angulo = candidato if candidato in (0, 90, 180, 270) else 0
        if len(campos) >= 8:
            negativo = campos[7] == "1"
    elif len(campos) == 5:
        char, coords = " ", campos[0:4]
    else:
        return None

    try:
        x1, y1, x2, y2 = (int(v) for v in coords)
    except ValueError:
        return None

    if origem_inferior:
        y1, y2 = altura - y2, altura - y1
    return BoxEntry(char, x1, y1, x2, y2, angulo=angulo, negativo=negativo)


def ler(caminho: str, altura: int,
        origem_inferior: bool = True) -> List[BoxEntry]:
    """Lê um `.box` inteiro. `altura` é a da imagem, para inverter o y."""
    with open(caminho, encoding="utf-8") as f:
        return ler_texto(f.read(), altura, origem_inferior)


def ler_texto(texto: str, altura: int,
              origem_inferior: bool = True) -> List[BoxEntry]:
    """Igual a `ler`, a partir do conteúdo já em memória."""
    saida = []
    for linha in texto.splitlines():
        box = analisar_linha(linha, altura, origem_inferior)
        if box is not None:
            saida.append(box)
    return saida


def escrever_texto(boxes: Sequence[BoxEntry], altura: int,
                   pagina: int = 0) -> str:
    """Conteúdo de um `.box`, terminado em quebra de linha."""
    if not boxes:
        return ""
    return "\n".join(formatar_linha(b, altura, pagina) for b in boxes) + "\n"


def escrever(caminho: str, boxes: Sequence[BoxEntry], altura: int,
             pagina: int = 0) -> None:
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(escrever_texto(boxes, altura, pagina))
