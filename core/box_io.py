from pathlib import Path
from typing import List
from .box_model import BoxEntry


def load_box_file(path: str) -> List[BoxEntry]:
    boxes: List[BoxEntry] = []
    p = Path(path)

    if not p.is_file():
        return boxes

    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 5:
                continue
            ch, x1, y1, x2, y2 = parts
            try:
                boxes.append(BoxEntry(ch, int(x1), int(y1), int(x2), int(y2)))
            except ValueError:
                continue
    return boxes


def save_box_file(path: str, boxes: List[BoxEntry]):
    p = Path(path)
    with p.open("w", encoding="utf-8") as f:
        for b in boxes:
            f.write(f"{b.char} {b.x1} {b.y1} {b.x2} {b.y2}\n")
