from dataclasses import dataclass, replace


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

    def as_tuple(self):
        return (self.char, self.x1, self.y1, self.x2, self.y2)

    def as_state(self) -> tuple:
        """
        Todos os campos, na ordem do construtor.

        Não é o `as_tuple`, e a diferença importa: aquele devolve só caractere e
        coordenadas, para quem desenha e mede. Este serve para guardar e
        restaurar **sem perder nada** — confiança, origem e ângulo inclusive.

        Estado gravado antes da F8.1 tem sete campos e continua carregando: o
        `angulo` fica no valor padrão, que é o que aquele box queria dizer.
        """
        return (self.char, self.x1, self.y1, self.x2, self.y2,
                self.confidence, self.source, self.angulo)

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
