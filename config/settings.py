import json
from pathlib import Path


class Settings:
    """
    Configuração simples persistida em JSON.
    Ex.: tesseract_path, último diretório, etc.
    """
    def __init__(self, path: str | None = None):
        if path is None:
            base = Path(__file__).resolve().parent
            self.path = base / "settings.json"
        else:
            self.path = Path(path)

        self.data: dict = {}
        self.load()

    def load(self):
        if self.path.is_file():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value):
        self.data[key] = value
