"""
Léxico do texto corrido (F9): dicionário de palavras e o que ele consegue decidir.

**O que este módulo não faz, e é a primeira coisa a saber:** não toca em notação.
Quem separa lance de prosa é `notacao._fatiar`, e o léxico só vê os pedaços tipados
`outro`. Aplicar lista de palavras a `Bxf6` ou `exd5` destruiria justamente a parte
do livro que o programa existe para ler — e a legalidade (F1.7) já é um dicionário
melhor para ela, porque depende de contexto: `Nf3` é válido numa posição e
impossível na seguinte.

**Fora do dicionário significa "não mexer".** Palavra desconhecida é sinalizada,
nunca aproximada da mais parecida. `Nimzowitsch` não está em lista alguma, e forçar
a troca entregaria prosa limpa e falsa — a forma de falha do `·` da F0.2 e do
separador da F1.5, que estragavam em silêncio. Medido: dos 18 lances tão maltratados
que escapam de `parece_lance` e caem aqui, nenhum está no dicionário; com esta regra
eles viram alarme falso, e com correção automática seriam 18 lances reescritos como
palavra.

O que o dicionário **decide** hoje são as duas fronteiras de palavra, porque nas duas
ele é o próprio critério e não precisa de limiar:

    juntar_hifenizadas   "em-" no fim da linha + "barrassment" na seguinte
    partir_coladas       "ofthe" que devia ser "of" "the"

Medido nas 10 páginas rotuladas, sobre a **verdade** e sem envolver o modelo
(`medir_lexico.py`): o hífen acerta 6 de 6 junções e recusa as 2 que não devem
juntar (`Xue-Fierro`, que é nome próprio, e `30.b3!+-` seguido de um número de
página). A junção acerta 7 de 7 e não parte nenhuma das 51 palavras boas que também
decomporiam — `some` em `so`+`me`, `opening` em `open`+`ing` —, porque a primeira
condição é a palavra **não** estar no dicionário.
"""

import gzip
import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from core import notacao


# As duas listas empacotadas, produzidas por `importar_lexico.py` a partir do
# dicionário que o usuário mantinha para o ABBYY FineReader. Ficam separadas porque
# a troca entre elas está medida (ROADMAP F9.1, medida 3): só o idioma dá 58,5% de
# recall com 12,1% de alarme falso; com os nomes, 53,8% e 5,8%. Nome próprio baixa
# o alarme e esconde erro, e quem escolhe é o perfil do livro.
CAMINHO_PADRAO = os.path.join("assets", "lexico", "en.txt.gz")
CAMINHO_NOMES = os.path.join("assets", "lexico", "nomes.txt.gz")

# Pontuação que cerca palavra e não faz parte dela. O apóstrofo tipográfico entra
# porque é o que estes livros usam ("Black's").
BORDAS = ".,;:!?()[]{}\"'‘’“”–—-*+"

# Hifens que quebram palavra no fim da linha.
HIFENS = "-‐‑"

# Menor pedaço que uma junção pode produzir. Com 1 letra, "a"+"way" tornaria
# qualquer coisa partível.
MIN_PARTE = 2


def nucleo(texto: str) -> Tuple[str, int]:
    """(núcleo, deslocamento) — o que vai a uma consulta de dicionário.

    Tira o que não é letra das **pontas**, nunca do meio: `p1ay` precisa sobrar
    inteiro, porque o `1` no meio é justamente o que se quer alcançar.
    """
    i, j = 0, len(texto)
    while i < j and not texto[i].isalpha():
        i += 1
    while j > i and not texto[j - 1].isalpha():
        j -= 1
    return texto[i:j], i


@dataclass
class Lexico:
    """
    As palavras conhecidas, e nada mais que isso.

    `palavras` é a lista geral (idioma) e `do_usuario` é a da F9.2 — separadas de
    propósito: na medição, 42,5% das palavras ausentes eram Capitalizadas
    (`Benko`, `Tromso`, `Gavilov`), e saber de qual das duas veio o acerto é o que
    permite dizer se a lista do usuário está fazendo trabalho.
    """
    palavras: Set[str] = field(default_factory=set)
    do_usuario: Set[str] = field(default_factory=set)
    idioma: str = "en"

    def __len__(self) -> int:
        return len(self.palavras | self.do_usuario)

    @property
    def vazio(self) -> bool:
        """Sem dicionário, nada acontece — como `separar_colados="auto"`."""
        return not self.palavras and not self.do_usuario

    def conhece(self, palavra: str) -> bool:
        b = palavra.lower()
        return b in self.palavras or b in self.do_usuario

    def procedencia(self, palavra: str) -> Optional[str]:
        """"usuario" | "idioma" | None — para o relatório saber a quem creditar."""
        b = palavra.lower()
        if b in self.do_usuario:
            return "usuario"
        if b in self.palavras:
            return "idioma"
        return None

    def acrescentar(self, palavra: str) -> bool:
        """Entra na lista do usuário. Devolve se era nova.

        Só palavra digitada à mão entra — silêncio não é confirmação, a mesma
        regra da F8.3. Quem chama é a UI, depois de o usuário corrigir.
        """
        nuc, _ = nucleo(palavra)
        if len(nuc) < MIN_PARTE or not nuc.isalpha():
            return False
        b = nuc.lower()
        if b in self.do_usuario:
            return False
        self.do_usuario.add(b)
        return True


def _ler(caminho: str) -> Set[str]:
    # `.gz` porque as listas empacotadas cabem em 0,94 MB comprimidas contra 3,01
    # em texto, e o tamanho era a objeção registrada contra pôr a lista no
    # repositório (ROADMAP F9.1, medida 2). Abrir texto puro continua valendo — é
    # o formato de quem edita a lista à mão.
    #
    # `errors="replace"` porque uma lista de palavras de terceiro não é confiável
    # quanto a encoding, e derrubar a carga por um byte torto seria pior que
    # perder uma palavra.
    abrir = gzip.open if caminho.endswith(".gz") else open
    with abrir(caminho, "rt", encoding="utf-8", errors="replace") as f:
        return {ln.strip().lower() for ln in f if ln.strip()}


def carregar(caminho: Optional[str] = None,
             caminho_usuario: Optional[str] = None,
             idioma: str = "en",
             nomes: bool = True) -> Lexico:
    """
    Carrega o léxico. **Arquivo ausente devolve léxico vazio, não erro.**

    Vazio significa que nada acontece, que é o padrão certo aqui (contrato 6 da
    SPEC §5.8) — e a alternativa, falhar alto, deixaria o programa inutilizável
    para quem nunca vai usar dicionário.

    `nomes` traz as 237 mil Capitalizadas do ABBYY para junto do idioma. Elas
    entram em `palavras`, e não em `do_usuario`, porque vêm empacotadas: o que
    `do_usuario` guarda é o que **este** usuário digitou (F9.2), e misturar as duas
    apagaria a única pergunta que `procedencia` existe para responder.
    """
    lex = Lexico(idioma=idioma)
    fontes = [("palavras", caminho or CAMINHO_PADRAO),
              ("do_usuario", caminho_usuario)]
    if nomes and caminho is None:
        fontes.append(("palavras", CAMINHO_NOMES))
    for alvo, cx in fontes:
        if cx and os.path.exists(cx):
            getattr(lex, alvo).update(_ler(cx))
    return lex


# ----------------------------------------------------------------------
# Fronteira de palavra — as duas coisas que o dicionário decide sozinho
# ----------------------------------------------------------------------

@dataclass
class Juncao:
    """Uma palavra partida pelo hífen de fim de linha, e como remontá-la."""
    linha: int
    palavra: int          # índice da palavra na linha (a que termina em hífen)
    texto: str            # a palavra remontada, sem o hífen
    de: str
    para: str

    def __str__(self):
        return f"linha {self.linha}: {self.de!r} + {self.para!r} -> {self.texto!r}"


def juntar_hifenizadas(linhas: Sequence[Sequence[str]],
                       lex: Lexico) -> List[Juncao]:
    """
    Palavra partida no fim da linha: propõe as junções, não altera nada.

    **O dicionário é o próprio critério, e é por isso que esta regra não tem
    limiar:** junta só se o resultado for palavra conhecida. Medido, isso aceita
    `com-`+`promised` e `em-`+`barrassment` e recusa `Xue-`+`Fierro` — que tem
    hífen de verdade, é nome próprio e não deve juntar. Um hífen no fim da linha
    não diz por si se é quebra ou parte do nome; a junção formar palavra, sim.

    `linhas` são as palavras já segmentadas, por linha, em ordem de leitura.
    """
    achados: List[Juncao] = []
    if lex.vazio:
        return achados

    for k in range(len(linhas) - 1):
        atual, seguinte = linhas[k], linhas[k + 1]
        if not atual or not seguinte:
            continue
        ultima = atual[-1]
        if not ultima.endswith(tuple(HIFENS)):
            continue
        esquerda = ultima.rstrip(HIFENS)
        nuc_e, _ = nucleo(esquerda)
        nuc_d, _ = nucleo(seguinte[0])
        if not nuc_e or not nuc_d:
            continue
        remontada = nuc_e + nuc_d
        # **A única condição é a junção formar palavra**, e a primeira versão
        # tinha uma segunda que estragava tudo: exigia que a esquerda *não* fosse
        # palavra, para proteger "well-"+"known". Medido, isso matou 5 das 6
        # junções reais — numa lista de 370 mil, `com`, `con`, `pre` e `em` são
        # todas palavras. E a proteção era desnecessária: "wellknown" não está na
        # lista, então o teste do resultado já recusa o composto.
        if lex.conhece(remontada):
            achados.append(Juncao(linha=k, palavra=len(atual) - 1,
                                  texto=remontada, de=ultima, para=seguinte[0]))
    return achados


def cortes_possiveis(palavra: str, lex: Lexico) -> List[int]:
    """Posições onde `palavra` se parte em duas palavras conhecidas."""
    b = palavra.lower()
    return [i for i in range(MIN_PARTE, len(b) - MIN_PARTE + 1)
            if lex.conhece(b[:i]) and lex.conhece(b[i:])]


def partir_colada(palavra: str, lacunas: Sequence[float],
                  lex: Lexico) -> Optional[int]:
    """
    Onde faltou um espaço — ou `None`.

    Três condições, e cada uma tira uma população de falso positivo:

    1. **A palavra não está no dicionário.** Sozinha, esta condição já descarta
       as 51 palavras boas que também decomporiam nas páginas medidas: `some` em
       `so`+`me`, `opening` em `open`+`ing`, `against` em `again`+`st`.
    2. **Parte em duas palavras conhecidas** — uma só não basta para nada.
    3. **A lacuna no ponto de corte é a maior de dentro da palavra.** É o que
       separa junção de nome próprio: medido, nas junções reais a lacuna do corte
       (0,18–0,50 da largura mediana) supera a maior das outras (0,00–0,27) em 7
       de 7; `Benko`, se `ben` e `ko` estivessem na lista, não tem lacuna interna
       que se destaque.

    `lacunas` tem um valor por par de caracteres vizinhos, em larguras medianas —
    `len(lacunas) == len(palavra) - 1`.
    """
    if lex.vazio or lex.conhece(palavra) or len(lacunas) != len(palavra) - 1:
        return None
    candidatos = cortes_possiveis(palavra, lex)
    if not candidatos:
        return None

    melhor = max(candidatos, key=lambda i: lacunas[i - 1])
    aqui = lacunas[melhor - 1]
    outras = [v for i, v in enumerate(lacunas, 1) if i != melhor]
    if outras and aqui <= max(outras):
        return None
    return melhor


# ----------------------------------------------------------------------
# Sinalização
# ----------------------------------------------------------------------

@dataclass
class Suspeita:
    """Uma palavra que o dicionário não reconhece. **Não é uma correção.**"""
    palavra: str
    indices: List[int]          # boxes que a compõem, para a UI destacar
    motivo: str = "fora-do-dicionario"

    def __str__(self):
        return f"{self.palavra!r} ({self.motivo})"


def boxes_do_nucleo(simbolos: Sequence[Tuple[str, int]]) -> Tuple[str, List[int]]:
    """
    (núcleo, boxes que o compõem) a partir de pares (caractere, índice do box).

    **Um box não vale um caractere**, e é por isso que esta função existe: com as
    16 classes de ligadura da SPEC §5.2 item 6, um box devolve `fi` ou `f7`. Cortar
    a lista de boxes por deslocamento de caractere faria a UI destacar o box
    errado — e errar o destaque numa ferramenta de revisão é pior que não destacar.
    """
    texto = "".join(c for c, _ in simbolos)
    nuc, ini = nucleo(texto)
    fim = ini + len(nuc)
    indices, pos = [], 0
    for c, i in simbolos:
        # O box entra se qualquer caractere dele cai dentro do núcleo.
        if pos < fim and pos + len(c) > ini:
            indices.append(i)
        pos += len(c)
    return nuc, indices


def sinalizar(palavras: Iterable[Sequence[Tuple[str, int]]],
              lex: Lexico) -> List[Suspeita]:
    """
    As palavras de prosa que o dicionário não conhece.

    **É triagem, e é o produto principal da fase.** A F1.9 mediu que a confiança
    do modelo só ordena: no corte 0,90 o revisor revisa 2,4% da página e acha
    39,7% dos erros, e não há corte que ache o resto por preço aceitável. "Fora do
    dicionário" é um sinal **independente da confiança** — pega o erro lido com
    confiança 1,000, que é a mediana de um erro.

    Cada palavra é uma sequência de pares (caractere, índice do box). Quem filtra
    para só prosa é o chamador, com `notacao._fatiar`: o contrato é que notação não
    chega aqui.
    """
    fora: List[Suspeita] = []
    if lex.vazio:
        return fora
    for simbolos in palavras:
        nuc, indices = boxes_do_nucleo(simbolos)
        # **Sem `isalpha()` aqui, e não é esquecimento.** A primeira versão exigia
        # núcleo todo alfabético e com isso pulava `follow1ng` e `p1ay` — que são
        # o caso canônico da fase, a confusão `1`↔`l` que a F1.3 mediu. O núcleo
        # já começa e termina em letra por construção, então `len >= 2` garante
        # duas letras; "2010" tem núcleo vazio e cai no mesmo teste.
        if len(nuc) < MIN_PARTE:
            continue
        if lex.conhece(nuc):
            continue
        fora.append(Suspeita(palavra=nuc, indices=indices))
    return fora


def suspeitas_da_pagina(boxes: Sequence, lex: Lexico) -> List[Suspeita]:
    """
    As suspeitas de uma página inteira de boxes — a cola que a UI consome.

    **Existe para o contrato 1 da SPEC §5.8 ter um lugar só.** Quem separa lance
    de prosa é `notacao._fatiar`, e só o que ele tipa `outro` chega ao dicionário;
    escrever esse filtro de novo em cada chamador é como a F1.5 acabou medindo uma
    coisa e a aplicação fazendo outra. `medir_lexico.py` monta a mesma população.

    O privado `_fatiar` é usado de propósito, e pela mesma razão: é o código que a
    F1.7 roda em produção.
    """
    if lex.vazio:
        return []
    palavras = []
    for linha in notacao.palavras_da_pagina(boxes):
        for palavra in linha:
            for pedaco in notacao._fatiar(palavra):
                if pedaco.tipo == "outro":
                    palavras.append([(s.char, s.indice) for s in pedaco.simbolos])
    return sinalizar(palavras, lex)
