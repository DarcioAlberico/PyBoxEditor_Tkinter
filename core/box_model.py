from dataclasses import dataclass


@dataclass
class BoxEntry:
    char: str
    x1: int
    y1: int
    x2: int
    y2: int

    def as_tuple(self):
        return (self.char, self.x1, self.y1, self.x2, self.y2)

    def center(self):
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)
