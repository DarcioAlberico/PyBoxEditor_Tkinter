"""Gera amostras sintéticas de linhas para reforçar o treino CRNN/CTC."""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


def _fontes() -> list[Path | str]:
    raiz = Path(__file__).resolve().parent.parent
    fontes = list((raiz / "assets" / "fonts").glob("*.ttf"))
    fontes += [Path(r"C:\Windows\Fonts\segoeui.ttf"),
               Path(r"C:\Windows\Fonts\seguisym.ttf"), "DejaVuSans.ttf"]
    return [fonte for fonte in fontes if isinstance(fonte, str) or fonte.exists()]


def _fonte(tamanho: int, rng: random.Random):
    fontes = _fontes()
    rng.shuffle(fontes)
    for caminho in fontes:
        try:
            return ImageFont.truetype(str(caminho), tamanho)
        except (OSError, TypeError):
            continue
    return ImageFont.load_default()


def _amostra(texto: str, rng: random.Random) -> Image.Image:
    fonte = _fonte(rng.randint(28, 42), rng)
    medida = Image.new("L", (64, 64), 255)
    caixa = ImageDraw.Draw(medida).textbbox((0, 0), texto or " ", font=fonte)
    largura = min(640, max(32, caixa[2] - caixa[0] + 24))
    altura = rng.randint(56, 78)
    imagem = Image.new("L", (largura, altura), rng.randint(242, 255))
    draw = ImageDraw.Draw(imagem)
    caixa = draw.textbbox((0, 0), texto or " ", font=fonte)
    y = max(2, (altura - (caixa[3] - caixa[1])) // 2 - caixa[1])
    draw.text((12, y), texto, fill=rng.randint(0, 45), font=fonte)
    if rng.random() < 0.45:
        imagem = imagem.rotate(rng.uniform(-1.5, 1.5), resample=Image.Resampling.BICUBIC,
                               expand=True, fillcolor=255)
    if rng.random() < 0.5:
        imagem = imagem.filter(ImageFilter.GaussianBlur(rng.uniform(0.0, 0.8)))
    imagem = ImageEnhance.Contrast(imagem).enhance(rng.uniform(0.75, 1.25))
    matriz = np.asarray(imagem, dtype=np.int16)
    matriz += np.random.default_rng(rng.randrange(2**32)).normal(
        0, rng.uniform(0.0, 7.0), matriz.shape).astype(np.int16)
    return Image.fromarray(np.uint8(np.clip(matriz, 0, 255)), mode="L")


def gerar(pasta_origem: str | Path = "training_data_linhas",
          pasta_destino: str | Path = "training_data_linhas_sintetico",
          por_linha: int = 4, semente: int = 42) -> dict:
    """Gera ``por_linha`` variações para cada transcrição do manifesto."""
    if por_linha < 1:
        raise ValueError("por_linha deve ser maior que zero")
    from core.linha_trainer import _ler_manifesto

    registros = _ler_manifesto(pasta_origem)
    destino = Path(pasta_destino)
    imagens = destino / "images"
    imagens.mkdir(parents=True, exist_ok=True)
    rng = random.Random(semente)
    manifesto = []
    for indice, (_caminho, texto) in enumerate(registros):
        for variacao in range(por_linha):
            nome = f"sintetica_{indice:06d}_{variacao:02d}.png"
            _amostra(texto, rng).save(imagens / nome)
            manifesto.append(f"images/{nome}\t{texto}")
    (destino / "rec_gt.txt").write_text("\n".join(manifesto) + "\n", encoding="utf-8")
    return {"linhas_origem": len(registros), "linhas_geradas": len(manifesto),
            "pasta": str(destino), "semente": semente}


def gerar_caracteres_faltantes(caracteres: str | set[str],
                               pasta_destino: str | Path,
                               *, semente: int = 42) -> list[tuple[Path, str]]:
    """Gera uma amostra visual para cada classe ausente na base de treino."""
    destino = Path(pasta_destino)
    imagens = destino / "images"
    imagens.mkdir(parents=True, exist_ok=True)
    rng = random.Random(semente)
    resultado = []
    for caractere in sorted(set(caracteres)):
        if not caractere:
            continue
        caminho = imagens / f"charset_{ord(caractere):04x}.png"
        if not caminho.exists():
            _amostra(caractere, rng).save(caminho)
        resultado.append((caminho, caractere))
    return resultado
