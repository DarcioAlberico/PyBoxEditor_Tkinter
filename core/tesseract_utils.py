import subprocess
from typing import Optional
from config.settings import Settings


def get_tesseract_path(settings: Settings) -> Optional[str]:
    return settings.get("tesseract_path")


def set_tesseract_path(settings: Settings, path: str):
    settings.set("tesseract_path", path)
    settings.save()


def test_tesseract(path: str) -> bool:
    try:
        out = subprocess.check_output([path, "--version"], text=True)
        print("Tesseract versão:\n", out)
        return True
    except Exception as e:
        print("Erro ao testar tesseract:", e)
        return False
