from dataclasses import dataclass, replace


#: `margem` de um box que não tem margem. Só o k-NN a produz; a rede e o EasyOCR
#: não têm o conceito, e um box carregado de um `.box` não traz nada.
#:
#: **Não é zero.** Margem zero quer dizer "duas classes exatamente à mesma
#: distância", que é o box mais ambíguo que existe — confundir os dois estados
#: mandaria toda página carregada de arquivo para o topo da fila de revisão.
SEM_MARGEM = -1.0


@dataclass
class BoxEntry:
    """
    Caixa de um caractere na página.

    IMPORTANTE: isto é um dataclass, NÃO um dicionário.
    Acesse sempre por atributo (b.x1), nunca por b["x1"] ou b.get("x1").
    """

    char: str
    x1: int
    y1: int
    x2: int
    y2: int

    # De onde veio o caractere e o quanto se confia nele. É o que permite
    # colorir os boxes por confiança e revisar só os duvidosos.
    #   source == ""  -> sem informação (box novo, ou carregado de um .box,
    #                    que não guarda confiança). Não é o mesmo que confiança
    #                    baixa: é "não avaliado".
    #   source == "manual" -> o usuário digitou; confiança 1.0, é autoridade.
    confidence: float = 0.0
    source: str = ""

    # Graus anti-horários do TEXTO impresso, não do recorte (F8.1):
    #   0    normal
    #   90   o texto sobe  (lê-se de baixo para cima)
    #   270  o texto desce (lê-se de cima para baixo)
    # Quem classifica precisa do glifo de pé — `core.vertical.endireitar` faz
    # essa volta num lugar só.
    angulo: int = 0

    # O glifo está impresso claro sobre escuro — o nome dos jogadores na tarja
    # preta (F10). Quem classifica precisa dele escuro sobre claro, e
    # `core.negativo.positivar` faz essa volta no mesmo funil do ângulo.
    negativo: bool = False

    # A segunda escala, e ela responde outra pergunta (F43/F44). `confidence` é
    # distância absoluta e detecta **novidade**: "isto se parece com algo que eu
    # já vi?". É ela que roteia a cadeia e é ela que colore o box. `margem` é a
    # razão de Lowe e detecta **ambiguidade**: "o vencedor estava claramente à
    # frente?". Só o k-NN a produz; nas outras fontes fica `SEM_MARGEM`.
    #
    # São duas porque o roteamento **gasta** a primeira: quando o box chega à
    # fila de revisão, a pergunta da novidade já foi feita e respondida por quem
    # escolheu o classificador, e o que sobra por decidir é ambiguidade.
    #
    # **Entra no fim da lista, e isso não é arrumação.** `from_state` carrega o
    # estado por posição, então um campo enfiado no meio faria um estado de nove
    # campos gravado antes desta versão virar outro box em silêncio — o `angulo`
    # lido como margem. Campo novo entra por último, sempre.
    margem: float = SEM_MARGEM

    def as_tuple(self):
        return (self.char, self.x1, self.y1, self.x2, self.y2)

    def as_state(self) -> tuple:
        """
        Todos os campos, na ordem do construtor.

        Não é o `as_tuple`, e a diferença importa: aquele devolve só caractere e
        coordenadas, para quem desenha e mede. Este serve para guardar e
        restaurar **sem perder nada** — confiança, origem, ângulo e polaridade
        inclusive.

        Estado gravado antes da F8.1 tem sete campos e continua carregando; o
        de antes da F10 tem oito, e o de antes da F44 tem nove. Os campos que
        faltam ficam no valor padrão, que é o que aquele box queria dizer.
        """
        return (self.char, self.x1, self.y1, self.x2, self.y2,
                self.confidence, self.source, self.angulo, self.negativo,
                self.margem)

    @classmethod
    def from_state(cls, estado) -> "BoxEntry":
        return cls(*estado)

    def center(self):
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)

    def copy(self) -> "BoxEntry":
        """Cópia rasa — os campos são todos imutáveis, então basta."""
        return replace(self)

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1
