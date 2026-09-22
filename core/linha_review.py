"""Operações seguras de revisão para o manifesto de linhas anotadas."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class LinhaAmostra:
    caminho: str
    texto: str


def ler_manifesto(pasta: str | Path = "training_data_linhas") -> list[LinhaAmostra]:
    raiz = Path(pasta)
    arquivo = raiz / "rec_gt.txt"
    if not arquivo.exists():
        return []
    resultado = []
    for bruto in arquivo.read_text(encoding="utf-8").splitlines():
        if "\t" not in bruto:
            continue
        caminho, texto = bruto.split("\t", 1)
        if caminho.strip() and (raiz / caminho).exists():
            resultado.append(LinhaAmostra(caminho.strip(), texto.strip()))
    return resultado


def _salvar(pasta: Path, amostras: list[LinhaAmostra]) -> None:
    destino = pasta / "rec_gt.txt"
    temporario = destino.with_suffix(".txt.tmp")
    conteudo = "".join(f"{item.caminho}\t{item.texto}\n" for item in amostras)
    temporario.write_text(conteudo, encoding="utf-8")
    temporario.replace(destino)


def corrigir(pasta: str | Path, caminho: str, texto: str,
             origem: str = "manual") -> bool:
    """Atualiza uma amostra e registra a alteração no histórico JSONL."""
    texto = " ".join(str(texto).split())
    if not texto:
        raise ValueError("a transcrição não pode ser vazia")
    raiz = Path(pasta)
    amostras = ler_manifesto(raiz)
    for indice, item in enumerate(amostras):
        if item.caminho.replace("\\", "/") == caminho.replace("\\", "/"):
            if item.texto == texto:
                return False
            amostras[indice] = LinhaAmostra(item.caminho, texto)
            _salvar(raiz, amostras)
            historico = raiz / "correcoes_linhas.jsonl"
            evento = {"data": datetime.now().isoformat(timespec="seconds"),
                      "caminho": item.caminho, "antes": item.texto,
                      "depois": texto, "origem": origem}
            with historico.open("a", encoding="utf-8") as arquivo:
                arquivo.write(json.dumps(evento, ensure_ascii=False) + "\n")
            return True
    raise FileNotFoundError(f"linha não encontrada no manifesto: {caminho}")


def adicionar_ou_corrigir(pasta: str | Path, caminho: str, texto: str,
                          origem: str = "rotulagem") -> bool:
    """Insere uma amostra nova ou atualiza a existente sem duplicá-la."""
    texto = " ".join(str(texto).split())
    if not texto:
        raise ValueError("a transcrição não pode ser vazia")
    raiz = Path(pasta)
    amostras = ler_manifesto(raiz)
    normalizado = caminho.replace("\\", "/")
    for indice, item in enumerate(amostras):
        if item.caminho.replace("\\", "/") == normalizado:
            if item.texto == texto:
                return False
            return corrigir(raiz, item.caminho, texto, origem)
    amostras.append(LinhaAmostra(normalizado, texto))
    _salvar(raiz, amostras)
    return True


def descartar(pasta: str | Path, caminho: str, motivo: str = "revisao") -> bool:
    """Retira a linha do treino, preservando imagem e registro de descarte."""
    raiz = Path(pasta)
    amostras = ler_manifesto(raiz)
    for indice, item in enumerate(amostras):
        if item.caminho.replace("\\", "/") == caminho.replace("\\", "/"):
            amostras.pop(indice)
            _salvar(raiz, amostras)
            rejeitadas = raiz / "linhas_descartadas.jsonl"
            evento = {"data": datetime.now().isoformat(timespec="seconds"),
                      **asdict(item), "motivo": motivo}
            with rejeitadas.open("a", encoding="utf-8") as arquivo:
                arquivo.write(json.dumps(evento, ensure_ascii=False) + "\n")
            return True
    return False
