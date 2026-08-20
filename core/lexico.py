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
    #: O índice por (comprimento, inicial) que o reparo da F66 usa, construído
    #: sob demanda. Campo declarado, e não atributo posto de fora: quem lê o
    #: dataclass tem de ver tudo que ele carrega.
    _forma: Optional[Dict] = field(default=None, repr=False, compare=False)

    def __len__(self) -> int:
        return len(self.palavras | self.do_usuario)

    @property
    def vazio(self) -> bool:
        """Sem dicionário, nada acontece — como `separar_colados="auto"`."""
        return not self.palavras and not self.do_usuario

    @property
    def sinaliza(self) -> bool:
        """
        Dá para acusar palavra desconhecida? **Só com a lista geral.**

        A do usuário sozinha não serve, e o caso é alcançável desde a F9.2: um
        livro com `.lexico.txt` ao lado e sem `assets/lexico/` instalado tem
        dezenas de palavras contra centenas na página, e `the` e `with` também
        ficariam "fora do dicionário" — a tela inteira acesa, que é o modo de
        morte de qualquer alarme.

        As duas fronteiras (`juntar_hifenizadas`, `partir_colada`) continuam
        olhando `vazio`, e não isto: elas só agem quando o resultado **é**
        palavra conhecida, então uma lista curta as deixa quietas em vez de
        barulhentas.
        """
        return bool(self.palavras)

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


# ----------------------------------------------------------------------
# A lista deste livro (F9.2)
# ----------------------------------------------------------------------

#: Sufixo do arquivo que guarda o que o usuário confirmou neste documento.
SUFIXO_USUARIO = ".lexico.txt"

#: Nome do arquivo quando o "documento" é uma imagem solta: a lista é da
#: **pasta**, e não da página. Um livro digitalizado é uma pasta de JPEGs, e uma
#: lista por página não seria dicionário de livro nenhum.
NOME_NA_PASTA = "lexico.txt"


def caminho_do_usuario(documento: Optional[str], e_pdf: bool = True) -> Optional[str]:
    """
    Onde fica a lista deste livro. `None` se não há documento aberto.

    **Não é no perfil, e a F9.2 previa que fosse.** O `config/profiles/*.json` da
    F2.4 é escolhido por **padrão de fonte**, não por livro: `escolher()` casa
    `font_patterns` contra o nome da fonte do PDF, e dois livros compostos na
    mesma fonte caem no mesmo perfil. Guardar ali daria a um livro do Kasparov o
    vocabulário de um do Yusupov, que é exatamente o contrário do motivo da fase.
    Os dois perfis que existem também são versionados e comentados à mão — o
    programa reescrevê-los a cada palavra aprendida encheria o `git status` do
    usuário de ruído.

    Ao lado do documento, então, como o rascunho da F3.4:

        livro.pdf              -> livro.lexico.txt
        pasta/pagina-0012.jpg  -> pasta/lexico.txt

    Texto puro, uma palavra por linha, que é o formato que `_ler` já abre e que o
    usuário edita à mão quando uma palavra entrou errada. Sem esse escape, tirar
    uma palavra da lista exigiria uma tela.
    """
    if not documento:
        return None
    if e_pdf:
        return os.path.splitext(documento)[0] + SUFIXO_USUARIO
    return os.path.join(os.path.dirname(documento) or ".", NOME_NA_PASTA)


def salvar_do_usuario(caminho: str, palavras: Iterable[str]) -> int:
    """
    Grava a lista do usuário, ordenada. Devolve quantas foram gravadas.

    Ordenada e uma por linha porque o arquivo é para ser lido e corrigido por
    gente: numa lista em ordem de chegada, achar a palavra que entrou errada
    seria varredura.
    """
    lista = sorted({p.strip().lower() for p in palavras if p.strip()})
    pasta = os.path.dirname(caminho)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    # Arquivo temporário e `os.replace`, como o autosave da F3.4: travar no meio
    # da escrita não pode deixar o vocabulário do livro pela metade.
    temporario = caminho + ".tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        f.write("\n".join(lista) + ("\n" if lista else ""))
    os.replace(temporario, caminho)
    return len(lista)


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
    if not lex.sinaliza:
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


# ----------------------------------------------------------------------
# Reparo da colagem (F66)
# ----------------------------------------------------------------------

#: Largura acima da qual o box é suspeito de esconder mais de um glifo, em
#: larguras de referência da linha (`BoxService._largura_de_referencia`).
#:
#: Medido nas 10 páginas rotuladas, com o rótulo à mão dizendo quantos
#: caracteres cada box de produção realmente cobre:
#:
#:     limiar   pega dos 96 colados   marca dos 10.416 bons
#:      1,3          89%                     10,01%
#:      1,5          82%                      7,57%
#:      1,8          61%                      2,44%
#:      2,0          50%                      0,90%
#:
#: **As duas populações se sobrepõem, e o limiar não é o que dá segurança** —
#: quem dá é o dicionário. Marcar um box bom só acrescenta uma posição mascarada
#: numa palavra que **já está fora do dicionário**; se a máscara passar a casar
#: com mais de uma palavra, o reparo desiste. Por isso o limiar fica onde a
#: colheita é alta: 1,5 alcança 82% das colagens.
SUSPEITA_DE_COLAGEM = 1.5

#: Quantos caracteres a mais a colagem pode esconder.
#:
#: Uma colagem lida como um caractere esconde 1 (`wn` lido `m`); lida como
#: ligadura de dois, esconde 1 a mais que isso. Medido, o pior caso das 10
#: páginas é `enk` lido `xf6` — três glifos num box —, e ali a conta de
#: caracteres nem muda. Dois basta e limita a busca.
MAX_ESCONDIDOS = 2

#: Quanto o desenho precisa sustentar o candidato para a troca valer, de 0 a 1
#: (F69).
#:
#: Medido nas 7 páginas rotuladas do Kasparov, com os 18 reparos propostos
#: conferidos **no impresso** um a um — o rótulo à mão não serve de verdade
#: aqui, porque em três daquelas páginas ele está incompleto:
#:
#:     nota da prova    reparos      certos
#:     0,611 – 0,976       7            7
#:     0,000 – 0,082      11            5
#:
#: O vão vai de **0,027** (a maior nota de um reparo errado) a **0,611** (a
#: menor de um certo), e nada cai dentro dele — fator 23. Qualquer limiar ali
#: dá o mesmo resultado; 0,5 é o que também se lê em voz alta ("o papel
#: concorda mais do que discorda").
#:
#: **O que ele recusa é metade dos acertos, e é o preço combinado**: `Dynamic`,
#: `Wandering` e `compensation` estão certos e ficam de fora, porque a prova não
#: os enxergou. Reescrever texto em silêncio só se paga com precisão alta; para
#: recall há a fila de revisão, que continua vendo todos eles.
NOTA_MINIMA = 0.5

#: Menor palavra que se repara — mais longa que a que se sinaliza.
#:
#: Sinalizar `p1ay` é barato e útil; **reparar** um núcleo de duas letras é
#: adivinhar, porque quase não sobra âncora fora da máscara. Medido, os 5 piores
#: reparos propostos são lance de xadrez que escapou do `notacao._fatiar` porque
#: a figurina foi lida como letra — `♗f1` virando `Bf`, `♕c2` virando `Qc` —, e
#: todos têm núcleo de **duas** letras.
#:
#: **É 3 e não 4, e a diferença foi medida.** A 4 o `fow` → `few` se perde, e ele
#: está certo e tira 0,950 na prova; a 3 nada de errado volta, porque o que a
#: `NOTA_MINIMA` barra continua barrado. Régua que custa acerto e não compra
#: recusa não fica — é a conta da F24 e da F36.
MIN_PARA_REPARAR = 3

#: Quantos trechos mascarados uma palavra pode ter para valer a busca.
#:
#: Com dois já são nove combinações de comprimento por palavra; com três, a
#: máscara sobra tão pouca letra conhecida que o dicionário casa com qualquer
#: coisa — e o reparo desiste de qualquer jeito, depois de pagar a busca.
MAX_TRECHOS = 2


@dataclass
class Reparo:
    """Uma palavra que a colagem estragou, e o que o dicionário diz que era."""
    palavra: str                #: como saiu do OCR
    corrigida: str
    indices: List[int]          #: os boxes que a compõem, na ordem
    #: Quanto o desenho sustenta o candidato escolhido, de 0 a 1 (F69), e
    #: quanto ele ficou à frente do segundo colocado. São os dois números que
    #: decidem se a troca vale, e ficam guardados para o relatório poder dizer
    #: **por que** cada palavra foi trocada — sem eles a fase não tem tabela.
    nota: float = 0.0
    vantagem: float = 0.0

    def __str__(self):
        return f"{self.palavra!r} -> {self.corrigida!r}"


def _indice_por_forma(lex: Lexico) -> dict:
    """
    {(comprimento, inicial): [palavras]} — construído uma vez, sob demanda.

    Sem ele a busca varre 310 mil palavras por suspeita. O balde médio tem ~460,
    e a inicial é conhecida quase sempre: a colagem raramente está na primeira
    letra, porque ela precisa de um vizinho à esquerda para colar.
    """
    if getattr(lex, "_forma", None) is None:
        forma: dict = {}
        for p in lex.palavras | lex.do_usuario:
            forma.setdefault((len(p), p[0]), []).append(p)
            forma.setdefault((len(p), None), []).append(p)
        lex._forma = forma
    return lex._forma


def _trechos(mascara: Sequence[bool]) -> List[Tuple[int, int]]:
    """Os intervalos contíguos de posição mascarada."""
    saida, inicio = [], None
    for i, m in enumerate(list(mascara) + [False]):
        if m and inicio is None:
            inicio = i
        elif not m and inicio is not None:
            saida.append((inicio, i))
            inicio = None
    return saida


def _casa(palavra: str, lido: str, trechos: Sequence[Tuple[int, int]],
          extras: Sequence[int]) -> bool:
    """A palavra do dicionário bate com o lido fora dos trechos mascarados?"""
    pos_lido = pos_pal = 0
    for (ini, fim), extra in zip(trechos, extras):
        n = ini - pos_lido
        if palavra[pos_pal:pos_pal + n] != lido[pos_lido:ini]:
            return False
        pos_lido, pos_pal = fim, pos_pal + n + (fim - ini) + extra
    return palavra[pos_pal:] == lido[pos_lido:]


def _com_a_inicial_do_lido(texto: str, lido: str) -> str:
    """
    `texto` com a caixa que a inicial tinha no papel (F69).

    **O dicionário é todo minúsculo**, e por isso `_remontar` remonta em vez de
    devolver a palavra dele: `Dynamic` viraria `dynamic` e o livro perderia a
    maiúscula. Isso resolve enquanto a máscara começa depois da inicial — que é
    o caso comum, porque colar exige um vizinho à esquerda. Quando ela **pega**
    a inicial, a letra vem do dicionário e a maiúscula some assim mesmo:
    `Wandering` lido `Whndering` saía `wandering`.

    A inicial é a única posição cuja caixa se conhece sem adivinhar, e é por
    isso que a regra para aqui: o candidato pode ter comprimento diferente do
    lido, então posição interna nenhuma corresponde à outra. Palavra toda em
    maiúscula sairia meio a meio, e não há nenhuma no material medido.
    """
    if lido[:1].isupper() and texto[:1].islower():
        return texto[0].upper() + texto[1:]
    return texto


def _remontar(palavra: str, lido: str, trechos: Sequence[Tuple[int, int]],
              extras: Sequence[int]) -> str:
    """O lido com os trechos mascarados trocados pelos do dicionário."""
    saida, pos_lido, pos_pal = [], 0, 0
    for (ini, fim), extra in zip(trechos, extras):
        n = ini - pos_lido
        saida.append(lido[pos_lido:ini])
        pos_pal += n
        saida.append(palavra[pos_pal:pos_pal + (fim - ini) + extra])
        pos_pal += (fim - ini) + extra
        pos_lido = fim
    saida.append(lido[pos_lido:])
    return _com_a_inicial_do_lido("".join(saida), lido)


def _candidatos(nuc: str, trechos, forma, total: int):
    """As palavras do dicionário que casam com a máscara neste comprimento."""
    baixo = nuc.lower()
    inicial = None if trechos and trechos[0][0] == 0 else baixo[0]
    reparticoes = ([(total,)] if len(trechos) == 1
                   else [(a, total - a) for a in range(total + 1)])
    achados = {}
    for extras in reparticoes:
        for p in forma.get((len(baixo) + total, inicial), ()):
            if _casa(p, baixo, trechos, extras):
                achados[_remontar(p, nuc, trechos, extras)] = (p, extras)
    achados.pop(nuc, None)
    return achados


def _letras_do_trecho(palavra: str, nuc: str, trechos, extras) -> List[str]:
    """
    O que o candidato diz que está escrito em cada trecho mascarado.

    **Com a caixa do papel, e não a do dicionário** (F69). O modelo tem `W` e
    `w` em classes separadas — são desenhos diferentes —, e perguntar por `w`
    sobre um `W` impresso é perguntar pela classe errada. `Whndering` ->
    `wandering` é o caso: a prova pontuava a inicial contra o minúsculo e
    tirava a pior nota aceita da tabela.
    """
    saida, pos_lido, pos_pal = [], 0, 0
    for (ini, fim), extra in zip(trechos, extras):
        n = ini - pos_lido
        pos_pal += n
        pedaco = palavra[pos_pal:pos_pal + (fim - ini) + extra]
        saida.append(_com_a_inicial_do_lido(pedaco, nuc) if ini == 0 else pedaco)
        pos_pal += (fim - ini) + extra
        pos_lido = fim
    return saida


def reparar(simbolos: Sequence[Tuple[str, int]], largos: Set[int],
            lex: Lexico, provar=None,
            nota_minima: float = NOTA_MINIMA) -> Optional[Reparo]:
    """
    A palavra estragada pela colagem, corrigida — ou `None`.

    **A geometria é a prova, e o dicionário é o juiz.** Só entra a palavra que
    (i) o dicionário não conhece e (ii) tem caractere vindo de um box largo
    demais para um glifo. O que veio do box largo é apagado; o resto é âncora.
    `Dmamic` vira `D` + máscara + `amic`, e o dicionário tem uma palavra só
    nesse molde: `dynamic`.

    **Desiste no empate, e é o que torna o reparo seguro.** Duas palavras no
    molde significam que a geometria não estreitou o bastante, e trocar por uma
    delas seria inventar. Medir isso é a razão de o `Reparo` guardar as duas
    formas: o relatório diz quantas foram trocadas e por quê.
    """
    if not lex.sinaliza or not largos:
        return None

    nuc, indices = boxes_do_nucleo(simbolos)
    if len(nuc) < MIN_PARA_REPARAR or lex.conhece(nuc):
        return None

    # Cada caractere do núcleo sabe de que box veio: um box pode ter trazido
    # dois caracteres (as classes de ligadura), e cortar por deslocamento faria
    # a máscara cair na letra errada.
    texto = "".join(c for c, _ in simbolos)
    _n, ini = nucleo(texto)
    de_qual, pos = [], 0
    for c, i in simbolos:
        for _ in c:
            if ini <= pos < ini + len(nuc):
                de_qual.append(i)
            pos += 1

    mascara = [i in largos for i in de_qual]
    trechos = _trechos(mascara)
    if not trechos or len(trechos) > MAX_TRECHOS:
        return None

    forma = _indice_por_forma(lex)
    # Os boxes de **cada** trecho, e não os da palavra: é a esse pedaço de papel
    # que a prova visual vai perguntar o que está escrito.
    caixas_do_trecho = []
    for principio, fim in trechos:      # não `ini`: o do núcleo ainda vale
        vistos = []
        for i in de_qual[principio:fim]:
            if i not in vistos:
                vistos.append(i)
        caixas_do_trecho.append(vistos)

    # **Sem prova visual, o Occam da geometria é tudo que há** (F66): do menos
    # escondido para o mais, e desiste no primeiro empate. Com ela, o
    # comprimento deixa de decidir sozinho — o `Dmamic` do cabeçalho perdia
    # `dynamic` para `drazic` justamente aqui, porque `drazic` não precisa
    # esconder caractere nenhum e o papel não era consultado (F69).
    todos = {}
    for total in range(0, MAX_ESCONDIDOS + 1):
        achados = _candidatos(nuc, trechos, forma, total)
        if provar is None:
            if len(achados) == 1:
                return Reparo(palavra=nuc, corrigida=achados.popitem()[0],
                              indices=indices)
            if achados:
                return None
            continue
        todos.update(achados)

    if provar is None or not todos:
        return None

    # A nota de um candidato é a do trecho mais fraco dele, pelo mesmo motivo
    # que a de um trecho é a da letra mais fraca: a palavra só está ali se
    # **todos** os pedaços estiverem.
    notas = []
    for corrigida, (palavra, extras) in todos.items():
        letras = _letras_do_trecho(palavra, nuc, trechos, extras)
        nota = min((provar(caixas, letra)
                    for caixas, letra in zip(caixas_do_trecho, letras)),
                   default=0.0)
        notas.append((nota, corrigida))
    notas.sort(reverse=True)

    melhor, corrigida = notas[0]
    if melhor < nota_minima:
        return None
    return Reparo(palavra=nuc, corrigida=corrigida, indices=indices,
                  nota=melhor,
                  vantagem=melhor - (notas[1][0] if len(notas) > 1 else 0.0))


def reparos_da_pagina(boxes: Sequence, largos: Set[int], lex: Lexico,
                      provar=None,
                      nota_minima: float = NOTA_MINIMA) -> List[Reparo]:
    """
    Os reparos de uma página inteira — a mesma população que `suspeitas_da_pagina`.

    **Só prosa chega aqui**, pelo mesmo `notacao._fatiar`: um lance não é palavra
    de dicionário, e procurar `Bxf` no inglês acharia alguma coisa mais cedo ou
    mais tarde.
    """
    if not lex.sinaliza or not largos:
        return []
    saida = []
    for simbolos in _palavras_de_prosa(boxes):
        reparo = reparar(simbolos, largos, lex, provar, nota_minima)
        if reparo is not None:
            saida.append(reparo)
    return saida


def boxes_largos(boxes: Sequence,
                    limiar: float = SUSPEITA_DE_COLAGEM) -> Set[int]:
    """
    Os índices dos boxes largos demais para caber um glifo só.

    A régua é a largura de referência **da linha** (F1.7), e não a da página:
    uma página que mistura corpo 9 com corpo 12 transformaria toda a linha maior
    em suspeita.
    """
    from core.services.box_service import BoxService

    referencia = BoxService._largura_de_referencia(list(boxes))
    return {i for i, b in enumerate(boxes)
            if (b.x2 - b.x1) > referencia[id(b)] * limiar}


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
    if not lex.sinaliza:
        return []
    return sinalizar(_palavras_de_prosa(boxes), lex)


def _palavras_de_prosa(boxes: Sequence) -> List[List[Tuple[str, int]]]:
    """As palavras tipadas `outro` da página, como pares (caractere, box)."""
    palavras = []
    for linha in notacao.palavras_da_pagina(boxes):
        for palavra in linha:
            for pedaco in notacao._fatiar(palavra):
                if pedaco.tipo == "outro":
                    palavras.append([(s.char, s.indice) for s in pedaco.simbolos])
    return palavras


# ----------------------------------------------------------------------
# O que o usuário confirmou (F9.2)
# ----------------------------------------------------------------------

#: Origem que marca "o usuário digitou" — a autoridade do `BoxEntry` (§2.1).
ORIGEM_MANUAL = "manual"


def _tem_buraco(da_palavra: Sequence, vazios: Sequence) -> bool:
    """
    Há box sem caractere **dentro** do trecho que a palavra ocupa?

    Pela geometria, e não pelo texto: box vazio não vira símbolo, então quando a
    palavra chega aqui o buraco já não aparece nela. Um box vazio conta se o
    centro dele cai entre a primeira e a última caixa da palavra e ele divide a
    linha com elas — o mesmo par de testes (faixa em x, sobreposição em y) que a
    `notacao` usa para montar a linha.
    """
    if not da_palavra or not vazios:
        return False
    x1 = min(b.x1 for b in da_palavra)
    x2 = max(b.x2 for b in da_palavra)
    topo = min(b.y1 for b in da_palavra)
    base = max(b.y2 for b in da_palavra)

    for v in vazios:
        cx, cy = (v.x1 + v.x2) / 2, (v.y1 + v.y2) / 2
        if x1 <= cx <= x2 and topo <= cy <= base:
            return True
    return False


def palavras_confirmadas(boxes: Sequence, lex: Lexico) -> List[str]:
    """
    As palavras desta página que o usuário sustentou, e que a lista não tem.

    **Silêncio não é confirmação**, a regra da F8.3: entra a palavra que tem pelo
    menos um box digitado à mão, não a que passou batido. É o que separa
    `Nimzowitsch` — que o revisor leu, corrigiu e sustenta — de `Kdinovsb`, que o
    OCR inventou e ninguém olhou. Sem essa regra, aprender a página inteira
    ensinaria o dicionário a calar justamente os erros que ele existe para
    apontar.

    As outras duas condições saem do mesmo raciocínio:

    - **Nenhum box vazio dentro da palavra.** Box sem caractere não vira símbolo
      em `notacao._palavras_da_linha`, então a palavra chega aqui já remontada
      sem ele: `Kalinovsky` com um buraco vira `Kalinvsky`, que entraria na
      lista e calaria `Kalinvsky` para sempre. Quem acha o buraco é a geometria
      (`_tem_buraco`), porque o texto já não o mostra.

      **Isso recusa também o box esvaziado de propósito**, e é escolha, não
      descuido: esvaziar é como a correção remove um glifo fantasma, e
      `apply_char` grava `source=""` nos dois casos — o box apagado a mão e o
      nunca tocado são indistinguíveis. Entre não aprender uma palavra boa e
      aprender uma furada, o barato é o primeiro: a palavra volta a aparecer na
      página seguinte, e a lista errada não avisa que está errada.
    - **Núcleo alfabético**, que é o que `Lexico.acrescentar` já cobra: `p1ay`
      com o `1` no meio é o erro canônico da fase, e blindá-lo seria o oposto do
      que a lista faz.

    Devolve os núcleos na ordem da página, sem repetir. Quem grava é o chamador.

    Sem a lista geral não recolhe nada (`Lexico.sinaliza`): não havendo com que
    comparar, `the` e `with` também seriam "palavras que a lista não tem", e o
    vocabulário do livro nasceria cheio de idioma.
    """
    vistas, saida = set(), []
    if not lex.sinaliza:
        return saida

    vazios = [b for b in boxes if not b.char]
    for simbolos in _palavras_de_prosa(boxes):
        indices = [i for _c, i in simbolos]
        if not any(getattr(boxes[i], "source", "") == ORIGEM_MANUAL
                   for i in indices):
            continue
        if _tem_buraco([boxes[i] for i in indices], vazios):
            continue

        nuc, _ = boxes_do_nucleo(simbolos)
        chave = nuc.lower()
        if len(nuc) < MIN_PARTE or not nuc.isalpha() or chave in vistas:
            continue
        if lex.conhece(nuc):
            continue
        vistas.add(chave)
        saida.append(nuc)
    return saida


def aprender_da_pagina(boxes: Sequence, lex: Lexico,
                       caminho: Optional[str] = None) -> List[str]:
    """
    Recolhe as palavras confirmadas, põe no léxico e grava. Devolve as novas.

    Grava a lista **inteira** a cada vez, e não só o acréscimo: o arquivo é a
    verdade, e reescrevê-lo ordenado é o que permite ao usuário editá-lo à mão
    entre uma página e outra sem que o programa desfaça a edição.
    """
    novas = [p for p in palavras_confirmadas(boxes, lex) if lex.acrescentar(p)]
    if novas and caminho:
        salvar_do_usuario(caminho, lex.do_usuario)
    return novas
