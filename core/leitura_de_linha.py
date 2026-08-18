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

- **Linha com box girado (F8.1) ou em negativo (F10)** — a faixa da linha deixa
  de ser um retângulo em pé na página, e endireitar a faixa inteira é outro
  problema. Uma linha assim não é lida em bloco.

E só. **A linha com figurina (♗, ♘) ou ligadura não fica de fora**, embora esta
seção tenha dito por muito tempo que ficava: o filtro estava escrito e ninguém o
alimentava, e a F36 o alimentou, mediu e desligou. A razão está em `em_bloco` e
é a mesma que justifica o alinhamento: um glifo que o reconhecedor troca por
duas letras é o caso `+1` que o `_alinhar` já absorvia desde a F17. Quase metade
das linhas destes livros carrega figurina — filtrá-las custa as correções do
resto de cada uma.
"""

from typing import (Callable, Container, List, Optional, Sequence, Tuple)

import numpy as np

from core.box_model import BoxEntry
from core.notacao import _alinhar

#: Ocupa o lugar de uma leitura vazia na âncora, para o índice do alinhamento
#: continuar sendo o índice do box. Não existe em página nenhuma.
MARCA_DE_VAZIO = "\x00"

#: Margem branca em volta da faixa. O reconhecedor foi treinado em recorte com
#: folga; colar no glifo da ponta corta traço.
MARGEM = 8

#: Abaixo disto a caixa é curta demais para dizer onde fica a linha de base, em
#: alturas medianas de caractere da página (F63).
#:
#: Medido nas 17 páginas rotuladas, com o rótulo à mão como verdade e a altura
#: normalizada pela mediana da própria página (p05 – p95):
#:
#:     hífen e travessão           0,11 – 0,38   (76 casos)
#:     ponto e vírgula             0,15 – 0,54   (925)
#:     apóstrofo e aspa simples    0,31 – 0,58   (50)
#:     minúscula sem ascendente    0,68 – 1,00   (8.147)
#:     minúscula com ascendente    0,85 – 1,67   (3.798)
#:     maiúscula                   1,00 – 1,67   (838)
#:
#: O vão é de 0,58 a 0,68, e o limiar fica dentro dele. **Fica em 0,65 e não no
#: meio porque os dois erros não custam o mesmo**: letra tomada por curta só
#: deixa de atualizar a base — que as outras letras da linha dão igual —,
#: enquanto apóstrofo tomado por letra crava a base na altura de x e devolve o
#: defeito que esta constante existe para tirar.
CAIXA_CURTA = 0.65

#: Quanto a caixa nova precisa passar da base para ter descido de linha, em
#: alturas medianas de caractere da página (F63).
#:
#: **Existe porque a vírgula raspa a base.** Ela desce um fio abaixo da linha de
#: base, então o centro dela fica **meio pixel** abaixo do fundo das letras — e
#: sem folga isso é "desceu uma linha". Medido nas 10 páginas rotuladas, os 26
#: cortes que sobravam depois da régua da linha se separam em dois montes, e
#: entre eles não há nada:
#:
#:     vírgula raspando a base    0,02   (11 casos, todos vírgula)
#:     quebra de linha de verdade 0,66 – 4,88   (15 casos)
#:
#: O limiar fica no vão: 12× acima do maior raspão e 2,6× abaixo da menor quebra
#: de verdade. As quebras de 0,66 a 1,07 são apóstrofo abrindo a linha seguinte,
#: e as de 1,44 para cima são número de página e cabeçalho `Game N` centrado —
#: nenhuma delas volta para a esquerda, então é esta régua que as corta.
#:
#: Varrido (`medir_quebra_de_linha.py`), o platô é largo: de 0,10 a 0,60 o
#: resultado não muda (15 cortes no meio, 68 linhas altas). A 0,90 começa a
#: comer quebra de verdade — 13 cortes e **69** linhas altas.
FOLGA_DE_LINHA = 0.25

#: Os glifos que o reconhecedor de linha não escreve casa a casa (F36).
#:
#: **O critério não é "o EasyOCR sabe escrever", é "o EasyOCR gasta uma casa".**
#: Quem poderia quebrar o alinhamento é o glifo que sai do reconhecedor com um
#: número de caracteres diferente de um: a figurina, que ele não tem no alfabeto
#: e troca por nada ou por duas letras, e a ligadura, que ocupa uma casa da
#: âncora e duas da linha. Um `±` ou uma aspa curva também estão fora do
#: alfabeto dele e **não** entram aqui: saem como um caractere errado numa casa
#: certa, que é o erro comum.
#:
#: A ligadura não está nesta lista porque não é um glifo e sim um comprimento —
#: `em_bloco` a reconhece por `len(char) > 1`.
#:
#: **Nada em produção passa isto**, e a F36 mediu que tem de ser assim — ver a
#: tabela em `em_bloco`.
GLIFOS_QUE_DESLOCAM = frozenset("♔♕♖♗♘♙♚♛♜♝♞♟")

#: O que o `english_g2` sabe escrever: os 96 caracteres em que ele foi treinado,
#: copiados de `easyocr.config`
#: (`recognition_models["gen2"]["english_g2"]["characters"]`).
#:
#: É o filtro **largo**, o primeiro que a F36 tentou, e mede igual ou pior que o
#: estreito nos dois caminhos. Fica porque sem ele `medir_cadeia.py --alfabeto`
#: não reproduz a comparação que decidiu, e `test_o_alfabeto_e_o_do_easyocr`
#: confere a cópia contra a biblioteca.
ALFABETO_EASYOCR = (
    "0123456789!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~ €"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")


def quebrar_em_linhas(boxes: Sequence[BoxEntry]) -> List[List[BoxEntry]]:
    """
    Corta uma sequência **já em ordem de leitura** em linhas.

    A linha sai da ordem de leitura, e não da geometria da página: o
    `sort_boxes_reading_order` já resolveu coluna, elemento transversal e pilha
    girada, e refazer isso aqui por coordenada desfaria o trabalho dele —
    voltaria a intercalar as duas colunas. Basta cortar onde a sequência desce,
    volta para a esquerda **ou sobe**.

    **Subir é o fim de uma coluna** (F61). Ao passar da última linha da coluna
    da esquerda para a primeira da direita, a sequência não desce (sobe para o
    topo da página) e não volta para a esquerda (vai para bem mais à direita):
    as duas regras de antes deixavam passar, e as duas linhas saíam coladas numa
    só. Medido na página 118 do Nunn, o fim de `...followed by ♔f7.` saía preso
    ao cabeçalho `ROOK ENDINGS`, que é a primeira coisa da coluna vizinha.

    **Subir é contra a linha inteira, e não contra a caixa anterior.** Medido na
    mesma página, a régua contra a anterior corta dentro da linha: a vírgula
    mora na base, e a letra seguinte começa acima do topo dela — `Gurgenidze,` e
    `1981` viravam duas linhas. Contra o topo do que já entrou na linha, a letra
    depois da vírgula continua sendo da linha, e a coluna vizinha, que está
    inteira acima, não.

    **Descer também é contra a linha, e pela mesma razão** (F63). A régua era
    contra a caixa anterior, e por isso o apóstrofo e o hífen — caixas curtas
    plantadas *no alto* — faziam a letra seguinte parecer ter descido uma linha:
    o fundo de um apóstrofo fica acima da altura de x, e qualquer letra normal
    tem o centro abaixo dele. Medido nas 10 páginas rotuladas
    (`medir_quebra_de_linha.py`), **69 cortes no meio de linha em 532 (13%)**
    contra 15 em 476 depois — e no arquivo exportado isso é a prosa picada:
    `following fresh` / `, high-` / `quality encounter` em três parágrafos.

    **E a caixa curta não fixa a base.** Uma linha que *começa* com aspas teria
    a régua no fundo das aspas, e o defeito voltaria pela porta dos fundos.
    Enquanto só houver caixa curta na linha, `desceu` não opina — quem corta ali
    é o `voltou`, que é o fim de linha de verdade e dispara nos mesmos pontos.

    **E descer é passar da base com folga**, porque a vírgula desce um fio
    abaixo dela: sem `FOLGA_DE_LINHA` o centro da vírgula fica meio pixel abaixo
    do fundo das letras, e isso contava como linha nova — `On the whole` e
    `, the author tries to` saíam separados.

    **A pilha girada fica de fora, e não é detalhe**: a 90° o texto se lê de
    baixo para cima (`vertical.ordenar`), então subir ali é o andamento normal
    da linha — cortar faria de cada letra uma linha.
    """
    if not boxes:
        return []

    alturas = sorted(b.y2 - b.y1 for b in boxes)
    mediana = alturas[len(alturas) // 2] or 1
    curto = mediana * CAIXA_CURTA
    folga = mediana * FOLGA_DE_LINHA

    linhas: List[List[BoxEntry]] = []
    atual: List[BoxEntry] = []
    base: Optional[int] = None          # o fundo do que já é letra nesta linha
    for b in boxes:
        if atual:
            ant = atual[-1]
            desceu = base is not None and (b.y1 + b.y2) / 2 > base + folga
            voltou = b.x1 < ant.x1 - (ant.y2 - ant.y1)
            girado = getattr(b, "angulo", 0) or getattr(ant, "angulo", 0)
            subiu = not girado and b.y2 < min(a.y1 for a in atual)
            if desceu or voltou or subiu:
                linhas.append(atual)
                atual, base = [], None
        atual.append(b)
        if (b.y2 - b.y1) >= curto:
            base = b.y2 if base is None else max(base, b.y2)
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


def em_bloco(linha: Sequence[BoxEntry],
             deslocam: Optional[Container[str]] = None,
             chars: Optional[Sequence[str]] = None) -> bool:
    """
    A linha pode ser lida de uma vez?

    Girado e negativo não têm faixa retangular em pé, e por isso ficam de fora
    sempre. **`deslocam` fica de fora do filtro em produção**, e o resto deste
    texto é o porquê — ele foi medido na F36, e não passa.

    **`chars` é a leitura da âncora**, um item por box e na ordem de `linha`. Sem
    ela sobra `b.char`, que é o que já estava gravado no box — e nas ações
    «Detectar e Preencher» isso é sempre vazio, porque a ação acabou de gerar os
    boxes e ainda não leu nada. Era esse o furo que a F36 foi consertar: o filtro
    existia desde a F17, ninguém o alimentava, e passar a lista sozinha **não o
    teria acordado**. A leitura, essa existe — o `ler_pagina` a calcula antes de
    decidir, e o `searchable_pdf` também.

    **E, alimentado, ele custa.** Medido em 10.484 caracteres de 10 páginas,
    contra a mesma corrida sem filtro (`medir_cadeia.py --alfabeto`):

        filtro                    linhas tiradas   híbrido   neural   quebras
        nenhum                                 0    97,65%   97,58%         0
        estreito (figurina+ligadura)  207 de 441    97,64%   97,54%       1/6
        largo (fora do alfabeto)      224 de 441    97,64%   97,53%       1/7

    A hipótese era que a figurina desloca o alinhamento da linha inteira. **Ela
    não desloca: o `_alinhar` absorve.** É para isso que a distância de edição
    entrou na F17 — o desvio mais comum já era a linha trazer caractere a mais
    (+1 em 34 linhas de 275), e um glifo que o reconhecedor troca por duas letras
    é exatamente esse caso. O filtro joga fora as correções do **resto** da linha
    para evitar um estrago que não acontece, e no caminho neural isso é 6 quebras
    contra 1 conserto.

    Fica porque `medir_cadeia.py --alfabeto` precisa dele para reproduzir a
    tabela, pela mesma razão que `margem_de_confianca` ficou na F24.
    """
    if len(linha) < 2:
        return False
    for i, b in enumerate(linha):
        if getattr(b, "angulo", 0) or getattr(b, "negativo", False):
            return False
        if deslocam is None:
            continue
        ch = (b.char if chars is None else chars[i]) or ""
        if len(ch) > 1 or ch in deslocam:
            return False
    return True


def distribuir(por_caractere: Sequence[str], texto: str) -> List[str]:
    """
    Espalha `texto` sobre os boxes, com `por_caractere` de âncora.

    Devolve uma lista do tamanho de `por_caractere`. Onde a linha não tem o que
    dizer, o que já estava fica.

    **A âncora é um caractere por box, e nunca menos nem mais.** É a invariante
    de que tudo aqui depende: o `pos` que o alinhamento devolve é o índice do
    box, e qualquer descompasso desloca a linha inteira em silêncio. Os dois
    jeitos de quebrá-la aparecem em produção:

    - **leitura vazia**, que `"".join` faria sumir — vira `MARCA_DE_VAZIO`, um
      caractere que não existe em página nenhuma, nunca casa com nada e por isso
      sempre cede a vez para o que a linha leu;
    - **ligadura**, que ocupa duas casas. A cadeia neural emite `fi` e `♗x` num
      box só (SPEC §5.2), e foi a asserção deste módulo que pegou isso quando o
      `searchable_pdf` passou a chamar por aqui. Entra na âncora pela primeira
      letra, para o alinhamento ter onde encaixar, e **fica de fora da troca**:
      um box que a cadeia leu como ligadura é justamente o que o EasyOCR não
      sabe escrever, e deixá-lo ser sobrescrito trocaria `♗x` por `B`.
    """
    ancora = "".join(c[0] if c else MARCA_DE_VAZIO for c in por_caractere)
    assert len(ancora) == len(por_caractere), "a âncora perdeu o índice do box"

    saida = list(por_caractere)
    for pos, ch in _alinhar(ancora, texto):
        if pos is not None and ch and len(por_caractere[pos]) <= 1:
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
    ler_caractere: Callable[[BoxEntry], Tuple[str, float, str]],
    deslocam: Optional[Container[str]] = None,
    conf_maxima_para_trocar: Optional[float] = None,
    cancelado: Optional[Callable[[], bool]] = None,
    progresso: Optional[Callable[[int, int], None]] = None,
) -> List[Tuple[BoxEntry, str, float, str]]:
    """
    `(box, char, confiança, fonte)` para cada box de `linhas`, em ordem.

    `ler_caractere(box) -> (char, confiança, fonte)` é a âncora: um item por
    box, e é dela que sai a `fonte` de quem não foi trocado.

    `fonte` sai `easyocr_linha` **só onde a linha trocou o caractere**. Quem ela
    confirmou fica com a fonte de quem leu — foi a rede que respondeu aquele
    box, e dizer `easyocr_linha` esconderia isso da revisão. Que a linha tenha
    corroborado está na confiança, que sobe quando as duas concordam.

    `deslocam` são os glifos que tiram a linha do modo bloco
    (`GLIFOS_QUE_DESLOCAM`), e o padrão `None` desliga o filtro. Quem decide se a
    linha tem um deles é a **âncora**, que já foi lida quando `em_bloco` é
    chamado — ver `em_bloco`.

    `conf_maxima_para_trocar` é a trava da F18, e o padrão `None` quer dizer
    "sem trava" — a linha manda sempre, que é o certo quando a âncora é o
    EasyOCR sozinho (F17: 72,9% para 89,5%). Com uma cadeia forte de âncora ela
    é obrigatória: a rede acerta 97,6% e a linha 89,5%, então deixá-la mandar em
    tudo **regride 7,3 pontos**. Passando `0.70`, ela só toca no que a cadeia
    não soube responder.
    """
    saida = []
    for i, linha in enumerate(linhas):
        if cancelado is not None and cancelado():
            break

        por_char = [ler_caractere(b) for b in linha]
        chars = [c for c, _cf, _fo in por_char]
        confs = [cf for _c, cf, _fo in por_char]
        fontes = [fo for _c, _cf, fo in por_char]

        texto, conf_linha = "", 0.0
        if em_bloco(linha, deslocam, chars):
            tira = faixa_da_linha(pagina, linha)
            if tira is not None:
                texto, conf_linha = ler_faixa(tira)
                texto = texto.replace(" ", "")

        final = distribuir(chars, texto) if texto else list(chars)
        for b, sugerido, antes, cf, fonte in zip(linha, final, chars,
                                                 confs, fontes):
            travado = (conf_maxima_para_trocar is not None
                       and cf >= conf_maxima_para_trocar)
            trocou = bool(texto) and not travado and sugerido != antes
            ch = sugerido if trocou else antes
            if not ch:
                saida.append((b, "", 0.0, "vazio"))
            elif trocou:
                saida.append((b, ch, confianca(False, conf_linha, cf),
                              "easyocr_linha"))
            else:
                saida.append((b, ch, confianca(bool(texto), conf_linha, cf)
                              if texto and not travado else cf, fonte))

        if progresso is not None:
            progresso(i + 1, len(linhas))
    return saida
