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

    def as_tuple(self):
        return (self.char, self.x1, self.y1, self.x2, self.y2)

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
