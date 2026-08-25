"""
A proporção do recorte, que o esticão para 32×32 joga fora (F106).

## O que a rede recebe

`NeuralPredictor._probabilidades` e `CharacterLearner._quadrados_ate` fazem a
mesma coisa com o recorte antes de olhar para ele:

    img = cv2.resize(img_gray, (32, 32))

Sem preservar proporção. Uma barra de tinta em pé de 5×20 e uma deitada de 20×5
saem **do mesmo jeito** — não parecidas, iguais byte a byte (ver
`test_a_barra_em_pe_e_a_deitada_viram_o_mesmo_recorte`). A proporção e o tamanho
do glifo são descartados antes de qualquer classificador ver alguma coisa, e os
dois elos da cadeia são cegos a eles pelo mesmo motivo.

Enquanto o glifo tem branco por dentro, isso não custa nada: o desenho sobrevive
ao esticão. O que quebra é o recorte que é **só tinta**. Um ponto, um `I` de
haste grossa, um travessão, um `|`, um quadrado: todos viram o mesmo quadrado
preto de 32×32, e a rede responde a ele sempre a mesma coisa, na mesma ordem —

    '■' 0,3823   '—' 0,2758   'l' 0,1015   '-' 0,0543   '–' 0,0452
    'I' 0,0397   '.' 0,0230

— porque é literalmente a mesma entrada. Um ponto de 2×2 e um de 8×8 devolvem
`0.3822762072086334` os dois, até o último dígito. Não é a rede hesitando entre
as classes: é ela lendo a *frequência de treino* delas, que é o único sinal que
sobrou. Das 1.111 amostras de `—` da base, 338 já são o quadrado maciço; das 790
de `I`, 12. Foi isso que ela aprendeu a responder.

É por isso que o mesmo ponto sai ora `—`, ora `I`, e que o `I` **quanto mais
grosso** pior é lido: o que salva o `I` são os vãos brancos entre as serifas, e
tinta pesada os fecha. Medido no `I` de *Introduction* do Aagaard, engrossando o
traço: `I` 0,966 → `I` 0,882 → `1` 0,480 → `]` 0,127.

## A regra: veto, e não voto

O que separa a família inteira está no recorte e foi jogado fora. `ENVELOPE`
guarda, por classe, a faixa de larg/alt em que ela existe, e `cabe` responde se
a leitura é geometricamente possível. **A geometria nunca escolhe o caractere —
ela só recusa o impossível**, e quem escolhe entre as que sobram continua sendo
o elo que leu, pela ordem dele. Um travessão num recorte três vezes mais alto
que largo não é uma leitura duvidosa, é uma leitura que não pode estar certa.

Isso é o contrário do canal que a F19 mediu e descartou. Lá o desempate opinava
onde o classificador tinha sinal e discordava dele — e, com âncora forte, esse
conjunto é quase todo erro do desempate (0 acertos em 72). Aqui a regra só fala
onde a entrada **provadamente não carrega** a distinção: ela não sabe mais que a
rede sobre o glifo, sabe do recorte o que a rede não recebeu.

Por isso também a fonte da leitura não muda. A geometria não lê nada; ela veta
uma resposta e o mesmo elo dá a seguinte. Trocar `fonte` para "geometria" diria
ao roteamento e à fila de revisão que apareceu um classificador novo, e não
apareceu.

## O que ela alcança, e o que não

Escolhe a **família**, não o membro. Num recorte maciço, `I`, `l`, `1` e `|` são
o mesmo desenho e nada no recorte os separa; a regra derruba o travessão e deixa
os quatro para quem já os ordenava. Ler `lntroduction` continua errado, mas é um
erro de caixa — `—ntroduction` era um erro de família.

O `.` e o `■` são o caso que a proporção não fecha sozinha: os dois são
quadrados, e o que os separa é o tamanho. `TAMANHO` mede o maior lado contra
`altura_de_referencia` — a mediana da altura dos boxes da página, o mesmo
denominador que `preprocess.denoise` usa e pela mesma razão (o mesmo livro a 150
e a 300 dpi tem pontos de tamanhos diferentes). **Sem a referência, o teste de
tamanho não roda**: quem não a tem passa `None` e fica só com a proporção. É o
caso do PDF pesquisável, que reconhece recorte a recorte sem a página à mão.

## Medido

`medir_proporcao.py`, nas 11 páginas rotuladas — 10.641 caracteres.

**Segurança, na página como ela é.** A regra muda 2 leituras em 10.641:

    certo  -> errado      0
    errado -> certo       1     '.' lido '—'  ->  '.'
    errado -> errado      1     'I' lido '-'  ->  'l'

Os dois casos que a queixa descreve estão no material rotulado, e a regra não
encosta em mais nada.

**Ganho, na mesma página com a tinta engrossada** (dilatação de 1 a 4, que é o
que uma digitalização pesada faz). "Família" são os 1.306 caracteres rotulados
com uma classe de `ENVELOPE`:

    engrossa  tinta   todos: antes → depois   família: antes → depois   mexidas
       0      0,48       93,98% → 93,99%         97,55% → 97,63%             2
       1      0,60       91,15% → 93,08%         80,55% → 96,32%           213
       2      0,69       85,03% → 87,70%         60,41% → 80,09%           321
       3      0,76       73,87% → 77,30%         55,74% → 75,50%           638
       4      0,81       54,68% → 57,19%         56,81% → 76,57%          1247

Em nenhum dos cinco níveis, e em nenhum dos 53.205 recortes medidos, a regra
transformou uma leitura certa em errada. Não é sorte: ela só dispara sobre
resposta que o envelope diz ser impossível, e leitura certa cabe no envelope por
construção — o risco todo está em o envelope estar apertado demais, e é por isso
que ele é medido e folgado, e não escolhido.

## De onde vêm os números do envelope

Dos `.box` rotulados, larg/alt por classe:

    classe    n     mín    p10   mediana   p90    máx
    'l'     213    0,25   0,28    0,30    0,33   0,44
    '1'     343    0,28   0,30    0,41    0,48   0,61
    'I'      26    0,26   0,37    0,40    0,52   1,50
    '.'     665    0,71   1,00    1,00    1,25   1,50
    '-'      53    1,03   2,00    3,67    6,50   8,67

Os dois extremos que encostam são recortes de 30×20 e 34×33 rotulados `I` e `-`
numa página que tem seis `■` de 33×33 ao lado; são o quadrado, e não a letra nem
o traço. Fora deles, `.` não passa de 1,50 e `-` não desce de 1,67 — o corte em
**1,6** separa os 665 pontos dos 53 traços sem erro nenhum.

Para o tamanho, maior lado ÷ altura mediana da página: `.` vai de 0,15 a 0,50 e
`■` de 1,22 a 1,55. O corte em 0,7 fica no meio do vão, longe dos dois.

Nenhum `—`, `–`, `|` ou `_` aparece nas páginas rotuladas. Eles entram no
envelope pela mesma faixa dos seus pares medidos — `—` e `–` são o `-` mais
longo, e `|` é o `l` sem cabeça —, e não por medição própria.
"""

from typing import Dict, Iterable, Optional, Sequence, Tuple

INFINITO = float("inf")

#: Faixa de **larg/alt** em que cada classe da família existe. Fora dela, a
#: leitura não é duvidosa: é impossível. Quem não está na tabela nunca é vetado
#: — a regra só fala do que o recorte maciço confunde.
ENVELOPE: Dict[str, Tuple[float, float]] = {
    # Deitadas. O `-` medido não desce de 1,67 (fora do quadrado de 34×33
    # rotulado `-`), e o mais largo dos 665 pontos mede 1,50.
    "-": (1.6, INFINITO),
    "–": (1.6, INFINITO),
    "—": (1.6, INFINITO),
    "_": (1.6, INFINITO),
    # Em pé. Medido: `l` não passa de 0,44, `1` de 0,61 e `I` de 0,52 fora do
    # recorte de 30×20. O teto em 0,8 é folga sobre o maior deles.
    "I": (0.0, 0.8),
    "l": (0.0, 0.8),
    "1": (0.0, 0.8),
    "|": (0.0, 0.8),
    # Quadradas. Medido nos 665 pontos: de 0,71 a 1,50.
    ".": (0.5, 1.6),
    "•": (0.5, 1.6),
    "■": (0.5, 1.6),
}

#: Faixa do **maior lado do recorte ÷ `altura_de_referencia`**. Só para o que a
#: proporção não separa: o ponto e o quadrado são os dois quadrados, e o que os
#: distingue é serem pequeno e grande. Sem referência, não é testado.
TAMANHO: Dict[str, Tuple[float, float]] = {
    ".": (0.0, 0.7),
    "•": (0.0, 0.7),
    "■": (0.7, INFINITO),
}

#: Quantas candidatas pedir ao elo quando a primeira não cabe. Medido nas cinco
#: rodadas de engrossamento, a substituta está entre as 5 primeiras em todos os
#: 2.421 vetos; 12 é folga para o dia em que uma classe nova estreitar o topo.
CANDIDATAS = 12


def altura_de_referencia(boxes: Sequence) -> Optional[float]:
    """
    A mediana da altura dos boxes da página, ou `None` se não há de quê.

    É o denominador de `TAMANHO`, e é relativo à página de propósito: o mesmo
    livro digitalizado a 150 e a 300 dpi tem ponto de tamanhos diferentes, e
    qualquer número absoluto aqui valeria para uma resolução só. É a mesma
    escolha que `preprocess.denoise` faz para o limiar de sujeira.

    Mediana, e não média: uma página com diagrama tem componentes de centenas de
    pixels no meio do texto, e a média os deixaria entrar.
    """
    alturas = sorted(b.y2 - b.y1 for b in boxes if b.y2 > b.y1)
    if not alturas:
        return None
    return float(alturas[len(alturas) // 2])


def cabe(char: str, largura: float, altura: float,
         referencia: Optional[float] = None) -> bool:
    """
    A geometria do recorte admite esta leitura?

    `True` para tudo que não está em `ENVELOPE` — a regra não tem opinião sobre
    o resto do alfabeto, e não ter opinião é responder que sim. `True` também
    para recorte degenerado (lado zero), que é problema de quem o recortou.
    """
    if largura <= 0 or altura <= 0:
        return True

    faixa = ENVELOPE.get(char)
    if faixa is None:
        return True
    if not faixa[0] <= largura / altura <= faixa[1]:
        return False

    faixa = TAMANHO.get(char)
    if faixa is None or not referencia or referencia <= 0:
        return True
    return faixa[0] <= max(largura, altura) / referencia <= faixa[1]


def escolher(candidatas: Iterable[Tuple[str, float]],
             largura: float, altura: float,
             referencia: Optional[float] = None
             ) -> Optional[Tuple[str, float]]:
    """
    A primeira candidata que a geometria admite, ou `None` se nenhuma admite.

    A ordem é a de quem leu — a regra não reordena nada, só pula o que não cabe.
    `None` quer dizer "não tenho substituta", e quem chama fica com a leitura que
    já tinha: inventar uma classe que o elo não ofereceu seria o voto que a F19
    mediu e descartou.
    """
    for char, confianca in candidatas:
        if cabe(char, largura, altura, referencia):
            return char, confianca
    return None


def lados(crop) -> Tuple[int, int]:
    """`(largura, altura)` de um recorte numpy, em cinza ou em cor."""
    altura, largura = crop.shape[:2]
    return int(largura), int(altura)
