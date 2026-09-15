"""Recursos linguísticos leves para OCR e treinamento de linhas."""

from __future__ import annotations

import json
import math
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from core.ocr_benchmark import distancia_edicao


TERMOS_XADREZ = frozenset({
    "chess", "king", "queen", "rook", "bishop", "knight", "pawn", "check",
    "checkmate", "castle", "castling", "opening", "gambit", "endgame",
    "middlegame", "variation", "novelty", "zugzwang", "sacrifice", "draw",
    "win", "loss", "white", "black", "equality", "attack", "defence",
    "defense", "strategy", "tactic", "tactics",
})


def normalizar_palavra(texto: str) -> str:
    return unicodedata.normalize("NFKC", str(texto)).strip().casefold()


def palavras_do_texto(texto: str) -> list[str]:
    return [normalizar_palavra(item) for item in str(texto).split()
            if any(char.isalpha() for char in item)]


@dataclass
class LanguageModel:
    idioma: str = "en"
    palavras: set[str] = field(default_factory=set)
    dominio: set[str] = field(default_factory=set)
    frequencia_palavras: Counter[str] = field(default_factory=Counter)
    frequencia_caracteres: Counter[str] = field(default_factory=Counter)

    @classmethod
    def from_texts(cls, textos: Iterable[str], *, idioma: str = "en",
                   dominio: Iterable[str] = ()) -> "LanguageModel":
        modelo = cls(idioma=idioma, dominio={normalizar_palavra(item) for item in dominio})
        for texto in textos:
            modelo.add_text(texto)
        return modelo

    @classmethod
    def from_lexico(cls, lexico: object, *, dominio: Iterable[str] = ()) -> "LanguageModel":
        """Adapta o `core.lexico.Lexico` existente sem duplicar sua carga."""
        palavras = set(getattr(lexico, "palavras", set()))
        palavras.update(getattr(lexico, "do_usuario", set()))
        return cls(idioma=str(getattr(lexico, "idioma", "en")),
                   palavras={normalizar_palavra(item) for item in palavras},
                   dominio={normalizar_palavra(item) for item in dominio})

    def add_text(self, texto: str) -> None:
        palavras = palavras_do_texto(texto)
        self.palavras.update(palavras)
        self.frequencia_palavras.update(palavras)
        for palavra in palavras:
            self.frequencia_caracteres.update(palavra)

    def conhece(self, palavra: str) -> bool:
        chave = normalizar_palavra(palavra)
        return chave in self.palavras or chave in self.dominio

    def score(self, palavra: str) -> float:
        chave = normalizar_palavra(palavra)
        if not chave:
            return 0.0
        if chave in self.dominio:
            return 1.0
        frequencia = self.frequencia_palavras.get(chave, 0)
        if frequencia:
            total = max(1, sum(self.frequencia_palavras.values()))
            return min(1.0, 0.5 + math.log1p(frequencia) / math.log1p(total))
        return 0.0

    def sugerir(self, palavra: str, *, limite: int = 5,
                distancia_maxima: int | None = None) -> list[str]:
        chave = normalizar_palavra(palavra)
        if not chave or limite < 1:
            return []
        teto = distancia_maxima if distancia_maxima is not None else max(1, len(chave) // 3)
        candidatos = []
        for candidato in self.palavras | self.dominio:
            distancia = distancia_edicao(chave, candidato)
            if distancia <= teto:
                candidatos.append((distancia, -self.score(candidato), candidato))
        candidatos.sort()
        return [item[2] for item in candidatos[:limite]]

    def save_json(self, caminho: str | Path) -> None:
        destino = Path(caminho)
        destino.parent.mkdir(parents=True, exist_ok=True)
        dados = {
            "idioma": self.idioma,
            "palavras": sorted(self.palavras),
            "dominio": sorted(self.dominio),
            "frequencia_palavras": dict(self.frequencia_palavras),
            "frequencia_caracteres": dict(self.frequencia_caracteres),
        }
        destino.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

    @classmethod
    def load_json(cls, caminho: str | Path) -> "LanguageModel":
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        return cls(str(dados.get("idioma", "en")), set(dados.get("palavras", [])),
                   set(dados.get("dominio", [])),
                   Counter(dados.get("frequencia_palavras", {})),
                   Counter(dados.get("frequencia_caracteres", {})))


@dataclass(frozen=True)
class LineSample:
    text: str
    image_path: str = ""
    source: str = "manual"
    metadata: dict[str, object] = field(default_factory=dict)


class LineDataset:
    """Dataset JSONL para linhas reais ou sintéticas, sem acoplar ao trainer."""

    def __init__(self, samples: Iterable[LineSample] = ()):
        self.samples = list(samples)

    def add(self, text: str, image_path: str = "", *, source: str = "manual",
            metadata: dict[str, object] | None = None) -> None:
        if not str(text).strip():
            raise ValueError("amostra precisa de texto")
        self.samples.append(LineSample(str(text), str(image_path), source,
                                       dict(metadata or {})))

    def save_jsonl(self, caminho: str | Path) -> None:
        destino = Path(caminho)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("w", encoding="utf-8") as arquivo:
            for sample in self.samples:
                arquivo.write(json.dumps({"text": sample.text,
                                          "image_path": sample.image_path,
                                          "source": sample.source,
                                          "metadata": sample.metadata},
                                         ensure_ascii=False) + "\n")

    @classmethod
    def load_jsonl(cls, caminho: str | Path) -> "LineDataset":
        samples = []
        with Path(caminho).open(encoding="utf-8") as arquivo:
            for linha in arquivo:
                if linha.strip():
                    dados = json.loads(linha)
                    samples.append(LineSample(str(dados["text"]),
                                              str(dados.get("image_path", "")),
                                              str(dados.get("source", "manual")),
                                              dict(dados.get("metadata", {}))))
        return cls(samples)
