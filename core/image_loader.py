from PIL import Image


def load_image(path: str) -> Image.Image:
    img = Image.open(path)
    return img.convert("RGB")
